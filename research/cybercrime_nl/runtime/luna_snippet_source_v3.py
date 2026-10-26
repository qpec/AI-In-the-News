"""Preflight-bounded import of the unchanged physical recall history.

The size manifest is a conservative metadata-derived allowlist, not a claim that
every listed payload was consumed. Bulk queue bodies remain outside the scope.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time

import luna_snippet_source_v2 as previous
from newsresearch.common import require_active
from newsresearch.storage import check_permissions

base, recall, retained = previous.base, previous.recall, previous.retained
REPORT, PLAN, FREEZE, SUCCESSOR, OWNER = previous.REPORT, previous.PLAN, previous.FREEZE, previous.SUCCESSOR, previous.OWNER
PRIOR_COMMITMENT = previous.PRIOR_COMMITMENT
METHOD = "cybercrime-luna-snippet-retained-recall-v3"
PREFLIGHT = "luna_snippet_selected_byte_preflight_v3"
POLICY = {**previous.POLICY, "maximum_selected_bytes": 3 * 1024**3,
    "size_preflight_before_payload_reads": True, "every_read_requires_allowlisted_reference": True,
    "projected_bytes_are_conservative_allowlist": True, "raw_and_decoded_reader_caches_retained": False}
require = base.require
executed_census = previous.executed_census
membership_history = base.membership_history


def implementation():
    return {**previous.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Reader(retained.Reader):
    """Preserve the live Source capability, with an explicit new byte boundary."""
    def __init__(self, *args, **kwargs):
        self.allowed = None
        self.read_progress = None
        super().__init__(*args, **kwargs)

    def artifact_bytes(self, reference):
        self._active()
        retained.frozen.source_api._sha(reference)
        require(self.allowed is not None and reference in self.allowed, "reference_not_allowlisted")
        expected = self.allowed[reference]
        check_permissions(self.owner / "objects" / reference)
        if reference in self.copied:
            require(self.copied[reference] == expected, "copied_size_manifest")
            raw = self.engine.ledger.artifacts.read_bytes(reference)
        else:
            require(self.artifact_size(reference) == expected, "preflight_size_changed")
            require(self.unique_bytes + expected <= POLICY["maximum_selected_bytes"], "selected_byte_limit")
            # Deliberately bypass both frozen Reader 1-GiB limits, preserving
            # SelectedSource's ACL, source hash, protected copy and live guards.
            try:
                raw = retained.frozen.SelectedSource.artifact_bytes(self, reference)
            finally:
                self.cache.pop(reference, None)
            require(self.unique_bytes <= POLICY["maximum_selected_bytes"], "selected_byte_limit")
            if self.read_progress and (len(self.copied) % 50 == 0 or expected >= 16 * 1024**2):
                self.read_progress("snippet_v3_copying_selected_evidence", selected_references=len(self.copied),
                    unique_source_artifact_bytes_read=self.unique_bytes)
        require(len(raw) == expected, "preflight_size_changed")
        require(hashlib.sha256(raw).hexdigest() == reference, "retained_artifact_hash")
        return raw

    def artifact(self, reference):
        # The caller owns the decoded value. The Reader keeps neither a second
        # raw representation nor a decoded cache; copied refs reuse local bytes.
        return json.loads(self.artifact_bytes(reference))


def reference_manifest(reader, metadata):
    """Select only fixed native fields from the already verified SQL projection."""
    reader._active()
    require(metadata["source_head"] == reader.head(), "preflight_head")
    refs = defaultdict(list)

    def add(ref, category, anchor, field):
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"category": category, "anchor": anchor, "field": field})

    for row in reader.db.execute("SELECT id,kind,artifact,payload FROM records ORDER BY created_event"):
        add(row["artifact"], "record_payload", row["id"], "artifact")
        value = json.loads(row["payload"])
        if row["id"] == PLAN:
            require(row["kind"] == recall.PLAN, "preflight_plan_kind")
            add(value["source_artifact"], "frozen_full_source", row["id"], "source_artifact")
        if row["id"] == FREEZE:
            require(row["kind"] == recall.FREEZE, "preflight_freeze_kind")
            add(value["state_artifact"], "frozen_successor", row["id"], "state_artifact")
        if row["kind"] == recall.RESPONSE:
            add(value["response"], "physical_response", row["id"], "response")
            if value["parsed"] is not None:
                add(value["parsed"], "physical_assessment", row["id"], "parsed")
    fields = {"session.started": ("identity",), "operation.intended": ("input",),
        "operation.completed": ("result",), "model.attempt.intended": ("packet", "request", "dispatch"),
        "luna_recall.response.received": ("response",)}
    for event in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        if event["kind"] not in fields:
            continue
        value = json.loads(event["payload"])
        for field in fields[event["kind"]]:
            category = "physical_" + field if event["kind"].startswith(("model.", "luna_recall.")) else "producer_" + field
            add(value[field], category, event["event_hash"], field)
    categories = defaultdict(lambda: {"distinct_references": 0, "bytes": 0})
    entries = []
    for ref, anchors in sorted(refs.items()):
        size = reader.artifact_size(ref)
        require(type(size) is int and size >= 0, "preflight_size")
        category = min(a["category"] for a in anchors)
        categories[category]["distinct_references"] += 1
        categories[category]["bytes"] += size
        entries.append({"reference": ref, "bytes": size, "accounting_category": category, "anchors": anchors})
    total = sum(e["bytes"] for e in entries)
    return {"method": METHOD, "owner": str(reader.owner), "head": metadata["source_head"],
        "plan_record": PLAN, "report_record": REPORT, "freeze_record": FREEZE,
        "entries": entries, "distinct_references": len(entries), "total_distinct_bytes": total,
        "categories": dict(sorted(categories.items())), "category_accounting": "one_lexicographically_first_category_per_sha",
        "maximum_selected_bytes": POLICY["maximum_selected_bytes"], "fits": total <= POLICY["maximum_selected_bytes"],
        "scope": "fixed_metadata_reference_superset_not_payload_consumption", "bulk_queue_bodies_selected": False}


def collect(engine, session, *, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "offline_only")
    start = time.monotonic()
    deadline = start + POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (float, int)) and math.isfinite(deadline)
        and 0 < deadline-start <= POLICY["maximum_seconds"], "bounded_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    observations = []

    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-start, 3), **values})

    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("snippet_v3_opening_retained_recall")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest = reference_manifest(reader, metadata)
        manifest_ref = engine.ledger.artifacts.put(manifest)
        preflight_record = engine.ledger.record(session, PREFLIGHT, manifest_ref,
            {"method": METHOD, "implementation": code, "manifest_artifact": manifest_ref,
                "owner": str(owner), "head": head, "fits": manifest["fits"]})
        progress("size_preflight", total_distinct_bytes=manifest["total_distinct_bytes"],
            refcount=manifest["distinct_references"], cap=POLICY["maximum_selected_bytes"], fits=manifest["fits"])
        require(manifest["fits"], "preflight_selected_byte_limit")
        reader.allowed = {e["reference"]: e["bytes"] for e in manifest["entries"]}
        reader.read_progress = progress
        plan, report, source, state, proof = base.authority(reader)
        progress("snippet_v3_replaying_physical_attempts", metadata_events=len(metadata["events"]))
        census, queues, evidence = executed_census(reader, plan, report)
        history = membership_history(reader, source, census, head)
        history.update(queue_metadata=queues, physical_census=evidence,
            prepared_only_summary={"enumerated": False, "individual_memberships": "unknown",
                "reported_queued_requests": report["queued_requests"],
                "reported_unattempted_requests": report["unattempted_requests"],
                "authority": "completed_native_report", "report_record": REPORT})
        require(history["prepared_only"] == [], "physical_only_partition")
        physical_count = len(census["intents"])
        census.clear()  # history now owns the small verified facts/cards; release full packets.
        reader._active()
        require(set(reader.copied) <= set(reader.allowed)
            and all(size == reader.allowed[ref] for ref, size in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "copied_manifest_partition")
        check_permissions(owner, root=True)
        check_permissions(owner / "objects")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "source_changed")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "implementation_changed")
        progress("snippet_v3_source_complete", physical_attempts=physical_count,
            selected_references=len(reader.copied), unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history,
            "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY,
                "owner": str(owner), "head": head, "plan_record": PLAN, "plan_artifact": plan["_artifact"],
                "report_record": REPORT, "report_artifact": report["_artifact"], "state_artifact": SUCCESSOR,
                "source_artifact": plan["source_artifact"], **proof,
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata),
                "size_preflight_record": preflight_record, "size_manifest_artifact": manifest_ref,
                "projected_allowlisted_bytes": manifest["total_distinct_bytes"],
                "projected_allowlisted_references": manifest["distinct_references"],
                "copied_artifacts": dict(reader.copied), "unique_source_artifact_bytes_read": reader.unique_bytes,
                "liveness": observations, "historical_stop": stop, "source_head_unchanged": True,
                "elapsed_seconds": round(time.monotonic()-start, 3)}}
