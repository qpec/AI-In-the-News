"""One-owner retained pilot import for the separately registered rollout."""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import math
import re
from pathlib import Path
import time

import luna_snippet_run_v3 as pilot
import luna_snippet_source_v3 as bounded
import luna_snippet_rollout_grouping as rollout_grouping
from newsresearch.common import digest, require_active
from newsresearch.embeddings import offline_tokenizer
from newsresearch.storage import check_permissions

base, retained = bounded.base, bounded.retained
Reader = bounded.Reader
METHOD = "luna-snippet-rollout-retained-pilot-v2"
PREFLIGHT = "luna_snippet_rollout_import_preflight_v2"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-pilot-20261025-v3")
PLAN = "a4c8a08945197913a0b57511ca92eefe537e800ebf5c52940708c45204089cda"
REPORT = "c14bab274541525cc3e0e300dbf08cb296c80f3537f64dd9ccc2199693b5d97a"
SUCCESSOR = "54cce2b394cc82cb00603e280cf3cb565d1bf0bce007c2ca104c14e1dbb5e257"
PRIOR_COMMITMENT = 3_708_647_448
POLICY = {**bounded.POLICY, "owners": 1, "maximum_manifest_bytes": 16*1024**2,
    "historical_parent_sources_reopened": False, "all_displayed_snippets_are_development_exposure": True,
    "proposal_choices_are_reference_labels": False}
require = base.require
question_identity = rollout_grouping.normalized_question_identity


def implementation():
    return {**pilot.implementation(), **{p.relative_to(base.ROOT).as_posix():
        hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), Path(__file__).with_name("luna_snippet_rollout_source.py"), Path(rollout_grouping.__file__))}}


class View(retained.AuditView):
    def __init__(self, reader):
        super().__init__(reader)
        self.ledger.get = lambda identity, kind=None: base.plain(reader.record(identity, kind))
        self.ledger.artifacts.read_bytes = reader.artifact_bytes

    def one(self, kind):
        rows = self.rows(kind)
        require(len(rows) == 1, "pilot_unique_record")
        return rows[0]

    completed_prepare = pilot.Pilot.completed_prepare
    verify_selection = staticmethod(pilot.Pilot.verify_selection)


def preflight(reader, metadata, engine, session, progress):
    """Bound a small native manifest bootstrap, then the entire selected graph."""
    rows = [dict(r) for r in reader.db.execute("SELECT * FROM records ORDER BY created_event")]
    selected = {r["id"]: r for r in rows}
    require(PLAN in selected and REPORT in selected and selected[PLAN]["kind"] == pilot.PLAN
        and selected[REPORT]["kind"] == pilot.RESULT, "pilot_fixed_records")
    plan, report = (json.loads(selected[i]["payload"]) for i in (PLAN, REPORT))
    imports = [r for r in rows if r["kind"] == bounded.PREFLIGHT]
    require(len(imports) == 1, "pilot_import_preflight")
    parent = json.loads(imports[0]["payload"])
    require(parent["method"] == bounded.METHOD and parent["implementation"] == bounded.implementation()
        and parent["fits"] is True and imports[0]["created_event"] < selected[PLAN]["created_event"], "pilot_import_preflight_binding")
    bootref = parent["manifest_artifact"]
    size = reader.artifact_size(bootref)
    require(size <= POLICY["maximum_manifest_bytes"], "pilot_manifest_bootstrap_limit")
    reader.allowed = {bootref: size}
    old_manifest = reader.artifact(bootref)
    require(old_manifest["method"] == bounded.METHOD and old_manifest["owner"] == parent["owner"]
        and old_manifest["head"] == parent["head"] and old_manifest["plan_record"] == bounded.PLAN
        and old_manifest["freeze_record"] == bounded.FREEZE and old_manifest["report_record"] == bounded.REPORT
        and old_manifest["fits"] is True, "pilot_manifest_parent")
    refs = defaultdict(list)
    def add(ref, category):
        retained.frozen.source_api._sha(ref)
        refs[ref].append(category)
    add(bootref, "prior_manifest")
    old_records = {}
    for entry in old_manifest["entries"]:
        for anchor in entry["anchors"]:
            if anchor["category"] == "physical_packet":
                add(entry["reference"], "prior_physical_packet")
            if anchor["category"] == "record_payload" and anchor["anchor"] in {bounded.PLAN, bounded.FREEZE}:
                require(anchor["anchor"] not in old_records, "prior_record_ambiguity")
                old_records[anchor["anchor"]] = entry["reference"]
                add(entry["reference"], "prior_scope_record")
    require(set(old_records) == {bounded.PLAN, bounded.FREEZE}, "prior_scope_records_missing")
    for row in rows:
        add(row["artifact"], "pilot_record")
        value = json.loads(row["payload"])
        if row["kind"] == pilot.QUEUE:
            add(value["packets_artifact"], "pilot_queue")
        if row["kind"] == pilot.RESPONSE:
            add(value["response"], "pilot_response")
            if value["parsed"] is not None:
                add(value["parsed"], "pilot_parsed")
    for field in ("import_artifact", "selection_artifact", "method_artifact"):
        add(plan[field], field)
    for field in ("successor_artifact", "change_manifest_artifact"):
        add(report[field], field)
    fields = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",),
        "model.attempt.intended": ("packet", "request", "dispatch"), "luna_snippet.response.received": ("response",)}
    for row in reader.db.execute("SELECT kind,payload FROM events ORDER BY seq"):
        if row["kind"] in fields:
            value = json.loads(row["payload"])
            for field in fields[row["kind"]]:
                add(value[field], row["kind"]+":"+field)
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "categories": sorted(set(kinds))}
        for ref, kinds in sorted(refs.items())]
    total = sum(e["bytes"] for e in entries)
    manifest = {"method": METHOD, "owner": str(reader.owner), "head": metadata["source_head"],
        "plan_record": PLAN, "report_record": REPORT, "entries": entries, "distinct_references": len(entries),
        "total_distinct_bytes": total, "maximum_selected_bytes": POLICY["maximum_selected_bytes"],
        "fits": total <= POLICY["maximum_selected_bytes"], "prior_manifest_artifact": bootref,
        "scope": "exact_pilot_graph_plus_prior_physical_packets_and_scope_metadata"}
    ref = engine.ledger.artifacts.put(manifest)
    record = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "manifest_artifact": ref, "fits": manifest["fits"]})
    progress("size_preflight", total_distinct_bytes=total, refcount=len(entries), cap=POLICY["maximum_selected_bytes"], fits=manifest["fits"])
    require(manifest["fits"], "rollout_preflight_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
    require(reader.copied[bootref] == reader.allowed[bootref], "bootstrap_size_changed")
    return manifest, ref, record, old_records, imports[0]


def statistics_equal(derived, saved):
    """Normalize only fresh histogram keys to their persisted JSON spelling.

    Source artifact hashes still verify the original bytes. The saved report is
    validated and compared unchanged; counts and all other fields stay exact.
    """
    fresh, retained_histogram = derived["accepted_size_histogram"], saved["accepted_size_histogram"]
    require(isinstance(fresh, dict) and isinstance(retained_histogram, dict), "statistics_histogram_shape")
    require(all(type(k) is int and k > 0 and type(v) is int and v > 0 for k, v in fresh.items()), "statistics_fresh_histogram")
    require(all(type(k) is str and re.fullmatch(r"[1-9][0-9]*", k) is not None
        and type(v) is int and v > 0 for k, v in retained_histogram.items()), "statistics_saved_histogram")
    normalized = {**derived, "accepted_size_histogram": {str(k): v for k, v in fresh.items()}}
    return digest(normalized) == digest(saved)


def authority(reader, import_row):
    plan = base.one(reader, pilot.PLAN, PLAN)
    intent = base.one(reader, pilot.INTENT)
    report = reader.record(REPORT, pilot.RESULT)
    reader.ensure_report_last(report)
    base.keyed(reader, plan, pilot.METHOD)
    base.keyed(reader, intent, pilot.METHOD)
    base.keyed(reader, report, PLAN)
    require(report["plan"] == PLAN and report["method"] == plan["method"] == pilot.METHOD
        and report["successor_artifact"] == SUCCESSOR and report["pilot_finished"] is True, "pilot_result_binding")
    view = View(reader)
    public_plan, imported, selection = pilot.Pilot.load_plan(view)
    require(public_plan["id"] == PLAN and plan["source_report"] == bounded.REPORT
        and intent["_created_event"] < import_row["created_event"] < plan["_created_event"], "pilot_plan_identity")
    expected = pilot.versions(base.plain(intent))
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, pilot.METHOD))]
        require(ids == [plan["versions"][kind]], "pilot_version_identity")
        row = reader.record(ids[0], kind)
        require(row["content"] == content and row["branch"] == "main" and row["reason"] is None
            and intent["_created_event"] < row["_created_event"] < import_row["created_event"], "pilot_version_binding")
    completed = retained.completed(reader, report, plan["implementation"])
    require(reader.artifact(completed["input"]) == {"action": "run", "allow_paid_execution": True}, "pilot_completed_run")
    prefix, _ = base.session_prefix(reader, plan["_created_event"], plan["implementation"], {"action": "prepare"})
    require(import_row["created_event"] in {r["seq"] for r in prefix}, "pilot_import_producer")
    provenance = imported["provenance"]
    require(provenance["method"] == bounded.METHOD and provenance["implementation"] == bounded.implementation()
        and provenance["report_record"] == bounded.REPORT and provenance["plan_record"] == bounded.PLAN
        and provenance["state_artifact"] == digest(imported["state"]) == bounded.SUCCESSOR
        and provenance["source_head_unchanged"] is True and provenance["size_preflight_record"] == import_row["id"], "pilot_import_binding")
    state = reader.artifact(SUCCESSOR)
    changes = reader.artifact(report["change_manifest_artifact"])
    require(digest(pilot.repair.commit(imported["state"], changes, reason=pilot.METHOD)) == SUCCESSOR
        and statistics_equal(pilot.statistics(imported["state"]), report["before"])
        and statistics_equal(pilot.statistics(state), report["after"]) and report["changes"] == len(changes), "pilot_successor_replay")
    return public_plan, report, imported, selection, state, view, completed


def physical_census(reader, view, plan, report):
    census = pilot.Pilot.census(view, plan)
    for row in reader.rows(pilot.QUEUE):
        base.keyed(reader, row, row["name"])
        require(plan["_created_event"] < row["_created_event"] < report["_created_event"], "pilot_queue_chronology")
        base.session_prefix(reader, row["_created_event"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
    intended, receipt, assessed = {}, {}, {}
    for row in reader.db.execute("SELECT * FROM events ORDER BY seq"):
        value = json.loads(row["payload"])
        if row["kind"] == "model.attempt.intended":
            base.session_prefix(reader, row["seq"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
            packet = census["packets"][value["task_key"]]
            require(digest(reader.artifact(value["packet"])) == digest(packet)
                and digest(reader.artifact(value["request"])) == digest(packet["request"]), "pilot_attempt_bytes")
            q = reader.record(value["queue"], pilot.QUEUE)
            require(q["_created_event"] < row["seq"] < report["_created_event"], "pilot_intent_chronology")
            intended[value["attempt"]] = {"seq": row["seq"], "event_hash": row["event_hash"]}
        elif row["kind"] == "luna_snippet.response.received":
            require(value["attempt"] in intended and intended[value["attempt"]]["seq"] < row["seq"] < report["_created_event"], "pilot_receipt_chronology")
            receipt[value["attempt"]] = row["seq"]
    for row in reader.rows(pilot.RESPONSE):
        base.keyed(reader, row, row["attempt"])
        require(row["attempt"] in receipt and receipt[row["attempt"]] < row["_created_event"] < report["_created_event"], "pilot_assessment_chronology")
        if row["parsed"] is not None:
            reader.artifact_bytes(row["parsed"])
        assessed[row["attempt"]] = row["_created_event"]
    for row in reader.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.completed'"):
        value = json.loads(row["payload"])
        require(value["attempt"] in assessed and assessed[value["attempt"]] < row["seq"] < report["_created_event"], "pilot_completion_chronology")
    view._state = census
    expected = pilot.Pilot.summary(view, plan)
    require(all(digest(report[k]) == digest(v) for k, v in expected.items() if k != "observed_at")
        and expected["combined_commitment_nanousd"] == PRIOR_COMMITMENT, "pilot_cost_census")
    return census, intended


def project_history(reader, imported, census, intended, selection, prior_records):
    source = imported["source"]
    history = dict(imported["history"])
    memberships = deepcopy(history["membership_attempts"])
    history["membership_attempts"] = memberships
    history["physical_attempts"] = list(history.get("physical_attempts", []))
    prior_plan = reader.artifact(prior_records[bounded.PLAN])
    prior_scope = reader.artifact(prior_records[bounded.FREEZE])
    require(digest(prior_plan) == prior_records[bounded.PLAN] and prior_plan["source_artifact"] == imported["provenance"]["source_artifact"]
        and prior_scope["plan"] == bounded.PLAN and prior_scope["state_artifact"] == bounded.SUCCESSOR
        and prior_scope["frozen_before_final_reference"] is True, "prior_validation_scope")
    exposed = set(prior_scope["exposed_documents"])
    logical, final_ids, tasks = set(), set(), set(source.get("prior_history", {}).get("task_keys", []))
    for fact in history.get("physical_attempts", []):
        packet = reader.artifact(fact["artifact_refs"]["packet"])
        require(packet["task_key"] == fact["task_key"] and packet["role"] == fact["role"], "prior_physical_scope")
        logical.update(packet["logical_ids"])
        tasks.add(fact["task_key"])
        if fact["role"] == "final_reference":
            final_ids.update(packet["logical_ids"])
        else:
            exposed.update(packet.get("members") or [v["document_id"] for v in packet.get("source_bindings", {}).values()])
    for row in source.get("prior_history", {}).get("pair_observations", []):
        exposed.update(row.get("pair", []))
    for row in source.get("prior_history", {}).get("clarity_observations", []):
        if row.get("document_id") in source["documents"]:
            exposed.add(row["document_id"])
    questions, proposal_packets = {}, []
    encoder = offline_tokenizer()
    def count(text):
        return len(encoder.encode(text, disallowed_special=()))
    for key, attempt in census["intents"].items():
        packet, response = census["packets"][key], census["responses"].get(key)
        done = attempt["attempt"] in census["completed"]
        tasks.add(key)
        logical.update(packet["logical_ids"])
        refs = {k: attempt[k] for k in ("packet", "request", "dispatch")}
        if response:
            refs.update(response_record=response["id"], response=response["response"], parsed=response["parsed"])
        fact = {"owner": str(reader.owner), "head": reader.head(), "physical_attempt": attempt["attempt"],
            "task_key": key, "logical_ids": packet["logical_ids"], "role": packet["role"],
            "completed": done, "hold": not done, "usable": bool(done and response and response["usable"]),
            "artifact_refs": refs, "intended_event": intended[attempt["attempt"]]}
        history.setdefault("physical_attempts", []).append(fact)
        if packet["role"] == "snippet_proposal":
            require(any(digest(packet) == digest(p) for p in selection["packets"]), "proposal_selected_packet")
            displayed = json.loads(packet["request"]["input"])["units"]
            for unit in displayed:
                binding = packet["unit_bindings"][unit["unit_id"]]
                require(binding["input_bindings"] == [[i, source["documents"][i]["input_sha256"]] for i in binding["members"]], "proposal_full_input_binding")
                require(unit["articles"] == [{k: pilot.grouping.snippet(i, source["documents"][i])[k]
                    for k in ("document_id", "title", "first_sentence", "last_sentence")} for i in binding["members"]], "proposal_snippet_binding")
            exposed.update(packet["article_ids"])
            proposal_packets.append({**fact, "displayed_document_ids": packet["article_ids"]})
            for name in packet["question_map"]:
                identity = question_identity(packet, name)
                questions.setdefault(identity, []).append({**fact, "question_name": name,
                    "source_unit": packet["question_map"][name], "menus": packet["menus"],
                    "displayed_document_ids": packet["article_ids"]})
            continue
        require(packet["role"] in {"group_membership", "group_quality"}, "pilot_role")
        exposed.update(packet["members"])
        builder = pilot.contract.member_packet if packet["role"] == "group_membership" else pilot.contract.group_packet
        require(digest(packet) == digest(builder(source, packet["members"], count)), "pilot_full_member_packet")
        revision = packet["membership_revision"]
        item = memberships.setdefault(revision, {"members": packet["members"], "member_attempted": False,
            "card_attempted": False, "member_supported": False, "card_supported": False, "blocked": False,
            "member_result_ref": None, "card_result_ref": None, "card": None, "provenance": []})
        stage = "member" if packet["role"] == "group_membership" else "card"
        require(item["members"] == packet["members"] and not item[stage+"_attempted"], "pilot_prior_membership_retry")
        supported = bool(done and response and response["usable"] and response["members_supported" if stage == "member" else "group_supported"])
        item.update({stage+"_attempted": True, stage+"_supported": supported, stage+"_result_ref": response["id"] if response else None})
        item["blocked"] |= not supported
        if stage == "card" and supported:
            item["card"] = packet["card"]
        item["provenance"].append({**fact, "stage": stage, "supported": supported})
    require(exposed <= set(source["documents"]), "exposure_population")
    history.update(proposal_questions=questions, proposal_packets=proposal_packets, logical_ids=sorted(logical),
        task_keys=sorted(tasks), prior_final_reference_logical_ids=sorted(final_ids),
        original_validation_seed=prior_plan["seed"], development_exposed_documents=sorted(exposed),
        pilot_unknown_holds=census["unknown_holds"], pilot_response_health=census["health"],
        pilot_settled_nanousd=census["settled_nanousd"], pilot_held_nanousd=census["held_nanousd"],
        active_stop_inherited=False, global_history_complete=False)
    return history


def collect(engine, session, *, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "offline_only")
    start = time.monotonic()
    deadline = start+900 if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline) and 0 < deadline-start <= 900, "bounded_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-start, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        observations = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest, manifest_ref, preflight_record, prior_records, import_row = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, state, view, proof = authority(reader, import_row)
        plan["_created_event"] = reader.db.execute("SELECT created_event FROM records WHERE id=?", (PLAN,)).fetchone()[0]
        census, events = physical_census(reader, view, plan, report)
        history = project_history(reader, imported, census, events, selection, prior_records)
        source = imported["source"]
        count = len(census["intents"])
        census.clear()
        reader._active()
        require(set(reader.copied) <= set(reader.allowed) and all(v == reader.allowed[k] for k, v in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "rollout_copy_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "implementation_changed")
        progress("rollout_source_complete", pilot_physical_attempts=count, unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history, "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "owner": str(owner), "head": head,
                "plan_record": PLAN, "report_record": REPORT, "state_artifact": SUCCESSOR,
                "pilot_import_artifact": plan["import_artifact"], "pilot_selection_artifact": plan["selection_artifact"],
                "completed_producer": proof, "prior_import_provenance": imported["provenance"],
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata), "size_manifest_artifact": manifest_ref,
                "size_preflight_record": preflight_record, "copied_artifacts": dict(reader.copied),
                "unique_source_artifact_bytes_read": reader.unique_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": observations, "elapsed_seconds": round(time.monotonic()-start, 3)}}
