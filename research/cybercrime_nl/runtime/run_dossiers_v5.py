"""Prepared v5 extractive-card continuation; unregistered until reviewed."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

import numpy as np

import prepare_dossiers as preparation
import dossier_contract_v5 as contract
import dossier_candidates as candidates
import dossier_transport as transport
import run_dossiers as original
import run_dossiers_v4 as previous
import run_dossiers_v3 as third
import run_dossiers_v2 as older
import run_summary_fidelity_diagnostic_v2 as fidelity
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.runtime import audited_handler

ROOT = preparation.ROOT
METHOD = "cybercrime-four-process-dossiers-20261023-v5"
PARENT_PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
V2_AMENDMENT = "08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282"
PARENT_AMENDMENT = "10c535b6968fd657e49e2c68fceb83ba9c37be569991b58d553eaf0a20657512"
V3_AMENDMENT = "b8f46bf8d8c509c36ba9077cbffcd973f7ac6f585f2483bdb8d2996ec1c78d10"
PARENT_REPORT = "7b612a25a8c8b89c46dd25732f43f04ca544057845743dbf407e6490e948cb6a"
V4_DIAGNOSTIC = "5dc87aa4c10c29b47768161142164f6b6af9e59a4b0b2913dbfba4def2058fde"
DIAGNOSTIC_OWNER = preparation.OWNER.parent / "cybercrime-v4-pilot-reason-view-20261023-v1"
Source = preparation.screening.original.base.pilot.Source
DIAGNOSTIC_PLAN = "3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3"
DIAGNOSTIC_REPAIR = "d96adb1244b7d101c5a90ec5c1b607e55aca8c1c971dbb51d788a9f06c30dd05"
DIAGNOSTIC_REPORT = "9e0853806fb3398d7e7a493bcee53d854fd32c37a901d177e5412f812e0bb38a"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V5.md"
CARD_AUDIT_MIN, CARD_AUDIT_MAX = 6, 10
CAP = 50_000_000_000
PARAMETERS = {"embedding_model": "text-embedding-3-large", "dimensions": 1536,
    "chunk_tokens": 6000, "embedding_batch_inputs": 32, "embedding_batch_tokens": 100000,
    "vector_k": 40, "seed_similarity": .85, "max_seed_size": 8, "packet_tokens": 32000,
    "positive_confidence": .85, "pilot_packets": 16, "pilot_assignments": 24,
    "assignment_candidates": 5, "recovery_candidates": 15, "workers": 8,
    "embedding_tpm": 800000, "luna_tpm": 800000, "astra_tpm": 100000, "rpm": 500,
    "non_audit_cap_nanousd": 35_000_000_000, "audit_cap_nanousd": 15_000_000_000,
    "embedding_cap_nanousd": 5_000_000_000, "deadline_hours": 24,
    "pilot_reference_pairs": 12, "final_reference_pairs_per_stratum": 50}


class PipelineStop(ResearchError):
    pass


def implementation():
    paths = [Path(__file__), Path(contract.__file__), Path(candidates.__file__), Path(transport.__file__),
        Path(preparation.__file__), METHOD_DOCUMENT,
        ROOT / "research/cybercrime_nl/runtime/run_dossiers_v5_with_key.ps1",
        ROOT / "src/newsresearch/gateway.py", ROOT / "src/newsresearch/runtime.py",
        ROOT / "src/newsresearch/storage.py", ROOT / "src/newsresearch/common.py", ROOT / "uv.lock"]
    return {**previous.implementation(), **fidelity.implementation(),
            **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def next_pilot_packets(packets, prior_documents, previous_packets, count=16):
    ordered = sorted(packets, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
    excluded = set(prior_documents) | {i for p in ordered[:count] + previous_packets for i in p["document_ids"]}
    selected = [p for p in ordered if not excluded.intersection(p["document_ids"])][:count]
    return {"packets": selected, "excluded_document_ids": sorted(excluded),
            "excluded_initial_packet_count": min(count, len(ordered)), "selected_packet_count": len(selected),
            "rule": "Next hash-ranked packets excluding all original, v2, v3 and v4 pilot packet sets and every previously attempted summary-source article; no replacement after execution."}


def positive_challenge(groups, limit=12):
    """Withhold one full source before card creation; seed labels are not gold."""
    training = {d: list(m) for d, m in groups.items()}
    held_out = {}
    chosen = sorted((d for d, members in groups.items() if len(members) >= 2),
                    key=lambda d: digest(["pilot-v5-positive-challenge", d]))[:limit]
    for dossier in chosen:
        member = min(groups[dossier], key=lambda i: digest(["pilot-v5-withheld-source", dossier, i]))
        training[dossier].remove(member)
        held_out[member] = {"dossier_id": dossier, "full_seed_membership_revision": digest(sorted(groups[dossier])),
                            "card_membership_revision": digest(sorted(training[dossier]))}
    return {"groups": training, "held_out": held_out,
            "limitation": "Functional positives derived from Luna seed decisions, not independent gold labels."}


def pack_assignment(document, summaries, count_tokens, request_factory=None):
    """Preserve candidate order/coverage, splitting only at exact packet capacity."""
    packets, pending = [], []
    request_factory = request_factory or contract.assignment_request
    for summary in summaries:
        try:
            request_factory(document, [*pending, summary], count_tokens=count_tokens)
            pending.append(summary)
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity" or not pending:
                raise
            packets.append(request_factory(document, pending, count_tokens=count_tokens))
            pending = [summary]
            request_factory(document, pending, count_tokens=count_tokens)
    if pending:
        packets.append(request_factory(document, pending, count_tokens=count_tokens))
    expected = [s["dossier_id"] for s in summaries]
    actual = [key for packet in packets for key in packet["bindings"]]
    if expected != actual or len(actual) != len(set(actual)):
        raise AuditError("dossier_assignment_candidate_coverage_changed")
    return packets


def reserve(packet):
    """Conservative proxy, bounded output and no assumed cache discount."""
    kind, request = packet["kind"], packet["request"]
    tokens = packet["input_tokens_proxy"]
    if kind == "embeddings":
        return math.ceil((tokens + 128) * 143 * 1.25)
    output = request.get("max_output_tokens", 0)
    incoming, outgoing = (11000, 55000) if request["model"] == "gpt-6-astra" else (110, 550)
    # Extra margin covers tokenizer mismatch, framing and possible cache writes.
    return math.ceil((tokens * 2 + 2048) * incoming * 1.25 + output * outgoing)


def billed(packet, response):
    expected = packet["request"]["model"]
    if not isinstance(response.model, str) or not (response.model == expected or response.model.startswith(expected + "-")):
        return None
    try:
        usage = transport.usage_metadata(packet["kind"], response.usage, model=expected)
    except ResearchError:
        return None
    if usage["input_tokens"] > 272000 and packet["kind"] != "embeddings":
        return None  # Contract limits should prevent long-context pricing; retain hold if violated.
    return usage["cost_nanousd_upper"]


def accounting(rows, pending):
    settled = sum(r["cost_nanousd"] or 0 for r in rows if not r["hold"])
    by_attempt = {r["attempt"]: r for r in rows}
    held = sum(max(r.get("reserved_nanousd", 0), r.get("cost_nanousd") or 0,
                   by_attempt.get(key, {}).get("cost_nanousd") or 0) for key, r in pending.items())
    return {"settled_nanousd": settled, "held_nanousd": held,
            "committed_nanousd": settled + held, "unresolved_holds": len(pending)}


def quality_partition(groups, result):
    """A focus/coherence rejection invalidates membership, not merely a card."""
    accepted, provisional, unresolved = {}, {}, {}
    for dossier, members in groups.items():
        reply = result["quality"].get(dossier)
        label = reply.get("label") if reply and reply.get("status") == "valid" else None
        if label == "supported" and dossier in result["usable"]:
            accepted[dossier] = members
        elif label == "identity_missing":
            provisional[dossier] = members
        else:
            unresolved[dossier] = {"document_ids": members, "reason": label or "card_quality_unavailable",
                                   "membership_accepted": False}
    return accepted, provisional, unresolved


def embedding_packets(documents, encoder):
    packets, batch, locators, total = [], [], [], 0

    def flush():
        nonlocal batch, locators, total
        if not batch:
            return
        request = {"model": PARAMETERS["embedding_model"], "dimensions": PARAMETERS["dimensions"],
                   "encoding_format": "float", "input": batch}
        packets.append({"phase": "embeddings", "kind": "embeddings", "request": request,
                        "input_tokens_proxy": total, "chunks": locators})
        batch, locators, total = [], [], 0

    for document in documents:
        text = canonical({"title": document["title"], "body": document["body"]})
        tokens = encoder.encode(text, disallowed_special=())
        for start in range(0, len(tokens), PARAMETERS["chunk_tokens"]):
            part = tokens[start:start + PARAMETERS["chunk_tokens"]]
            if len(batch) >= PARAMETERS["embedding_batch_inputs"] or total + len(part) > PARAMETERS["embedding_batch_tokens"]:
                flush()
            batch.append(part)
            locators.append({"document_id": document["document_id"], "token_start": start,
                             "token_end": start + len(part), "full_tokens": len(tokens),
                             "exact_input_sha256": digest({"title": document["title"], "body": document["body"]})})
            total += len(part)
    flush()
    return packets


def parse_embeddings(packet, payload):
    entries = payload.get("data", []) if isinstance(payload, dict) else []
    if len(entries) != len(packet["chunks"]) or sorted(e.get("index") for e in entries) != list(range(len(entries))):
        raise ResearchError("dossier_embedding_coverage_mismatch")
    matrix = np.asarray([e["embedding"] for e in sorted(entries, key=lambda e: e["index"])], dtype=np.float32)
    if matrix.shape != (len(entries), PARAMETERS["dimensions"]) or not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any():
        raise ResearchError("dossier_embedding_vector_invalid")
    return {"status": "valid", "vectors": matrix.tolist()}


class Study(preparation.Study):
    def init_state(self):
        self.encoder = offline_tokenizer()
        rows = self.rows("cyber_dossier_response")
        self.results = {r["task_key"]: r for r in rows}
        if len(self.results) != len(rows):
            raise AuditError("dossier_duplicate_response_task_key")
        self.phases = {r["name"]: r for r in self.rows("cyber_dossier_phase")}
        self.started = time.perf_counter()
        self.last_dispatch = 0.
        self.pacing_lock = threading.Lock()
        self.next_dispatch = {}
        self.current_phase = "preflight_complete"

    def summary_attempts(self):
        """A source-membership summary is attempted once even after a prompt amendment."""
        entries = {r["attempt"]: r for r in self.results.values() if r["phase"] == "summary"}
        for attempt, intended in self.ledger.unresolved.items():
            if intended.get("phase") == "summary":
                entries.setdefault(attempt, intended)
        versions = {}
        for attempt, row in entries.items():
            packet = self.ledger.artifacts.read(row["packet"])
            binding = packet["bindings"]
            key = (binding["dossier_id"], binding["membership_revision"])
            if key in versions:
                raise AuditError("dossier_repeated_summary_membership_attempt")
            versions[key] = {"attempt": attempt, "task_key": row["task_key"], "packet": row["packet"],
                "dossier_id": key[0], "membership_revision": key[1], "document_ids": packet["document_ids"],
                "parsed": row.get("parsed"), "hold": attempt in self.ledger.unresolved,
                "response_record": row.get("_record_id")}
        return versions

    def seed_attempts(self):
        return self.article_set_attempts("seed")

    def article_set_attempts(self, phase):
        entries = {r["attempt"]: r for r in self.results.values() if r["phase"] == phase}
        for attempt, row in self.ledger.unresolved.items():
            if row.get("phase") == phase:
                entries.setdefault(attempt, row)
        selected = {}
        for row in entries.values():
            packet = self.ledger.artifacts.read(row["packet"])
            key = tuple(sorted(packet["document_ids"]))
            if key in selected:
                raise AuditError("dossier_" + phase + "_article_set_repeated")
            selected[key] = packet
        return selected

    def hold_lineage(self):
        legacy = set(self.amendment["legacy_unresolved_attempts"])
        current = set(self.ledger.unresolved)
        if not legacy <= current:
            raise AuditError("dossier_legacy_hold_was_removed")
        old = accounting(list(self.results.values()), {a: v for a, v in self.ledger.unresolved.items() if a in legacy})
        new = accounting(list(self.results.values()), {a: v for a, v in self.ledger.unresolved.items() if a not in legacy})
        if old["held_nanousd"] < self.amendment["legacy_budget"]["held_nanousd"]:
            raise AuditError("dossier_legacy_liability_reduced")
        return {"legacy_unresolved_holds": len(legacy), "new_unresolved_holds": len(current - legacy),
                "legacy_held_nanousd": old["held_nanousd"], "new_held_nanousd": new["held_nanousd"]}

    def count(self, value):
        return len(self.encoder.encode(value if isinstance(value, str) else canonical(value), disallowed_special=()))

    def task_key(self, packet):
        return digest([self.plan["_record_id"], packet["kind"], packet["request"]])

    def checkpoint(self, **extra):
        value = {"observed_at": utc(), "pid": os.getpid(), "phase": self.current_phase,
                 "execution_amendment": self.amendment["_record_id"], **self.hold_lineage(),
                 "input_manifest": self.plan["input_manifest"], "unique_documents": self.plan["unique_documents"],
                 "selected_articles": self.plan["eligible_articles"], "responses": len(self.results),
                 **accounting(list(self.results.values()), self.ledger.unresolved),
                 "cap_nanousd": CAP, "deadline": getattr(self, "deadline", None),
                 "elapsed_seconds": time.perf_counter() - self.started, **extra}
        temporary = self.ledger.root / f"progress.{os.getpid()}.tmp"
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(temporary, self.ledger.root / "progress.json")
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.1)
        print(json.dumps(value), flush=True)

    @audited_handler
    def _status(self, session, context, data):
        self.init_state()
        self.plan = self.one("cyber_dossier_plan")
        if self.plan["_record_id"] != PARENT_PLAN or self.plan["implementation"] != original.implementation():
            raise AuditError("dossier_frozen_parent_implementation_changed")
        v2 = self.one("cyber_dossier_execution_amendment")
        if v2["_record_id"] != V2_AMENDMENT or v2["implementation"] != older.implementation():
            raise AuditError("dossier_frozen_v2_amendment_changed")
        v3 = self.one("cyber_dossier_execution_amendment_v3")
        if (v3["_record_id"] != V3_AMENDMENT or v3["implementation"] != third.implementation()
                or v3["parent_execution_amendment"] != v2["_record_id"]
                or v3["parent_implementation"] != v2["implementation"]):
            raise AuditError("dossier_frozen_v3_amendment_changed")
        diagnostic = self.one("cyber_summary_fidelity_diagnostic_plan")
        diagnostic_repair = self.one("cyber_summary_fidelity_diagnostic_amendment_v2")
        diagnostic_report = self.ledger.get(DIAGNOSTIC_REPORT, "cyber_summary_fidelity_diagnostic_report_v2") if DIAGNOSTIC_REPORT else None
        if (not diagnostic_report
                or diagnostic["_record_id"] != DIAGNOSTIC_PLAN or diagnostic["implementation"] != fidelity.original.implementation()
                or diagnostic_repair["_record_id"] != DIAGNOSTIC_REPAIR
                or diagnostic_repair["implementation"] != fidelity.implementation()
                or diagnostic_repair["parent_diagnostic_plan"] != diagnostic["_record_id"]
                or diagnostic["parent_plan"] != self.plan["_record_id"]
                or diagnostic["execution_amendment"] != v3["_record_id"]
                or diagnostic_report["diagnostic_plan"] != DIAGNOSTIC_REPAIR):
            raise AuditError("dossier_v4_reviewed_diagnostic_binding_required")
        parent = self.one("cyber_dossier_execution_amendment_v4")
        if (parent["_record_id"] != PARENT_AMENDMENT or parent["implementation"] != previous.implementation()
                or parent["parent_execution_amendment"] != v3["_record_id"]
                or parent["parent_implementation"] != v3["implementation"]):
            raise AuditError("dossier_frozen_v4_amendment_changed")
        manifest = self.ledger.get(self.plan["input_manifest"], "cyber_dossier_input_manifest")
        self.document_rows = self.ledger.artifacts.read(manifest["documents_artifact"])
        self.documents = {r["document_id"]: self.ledger.artifacts.read(r["document_artifact"]) for r in self.document_rows}
        self.articles = self.ledger.artifacts.read(manifest["articles_artifact"])
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment_v5")
        if (self.amendment["implementation"] != implementation()
                or self.amendment["parent_plan"] != self.plan["_record_id"]
                or self.amendment["parent_execution_amendment"] != parent["_record_id"]
                or self.amendment["ancestor_execution_amendments"] != {"v2": v2["_record_id"], "v3": v3["_record_id"], "v4": parent["_record_id"]}
                or self.amendment["parent_report"] != PARENT_REPORT
                or self.amendment["v4_diagnostic"]["record_id"] != V4_DIAGNOSTIC
                or self.amendment["diagnostic_plan"] != diagnostic["_record_id"]
                or self.amendment["diagnostic_amendment"] != diagnostic_repair["_record_id"]
                or self.amendment["diagnostic_report"] != DIAGNOSTIC_REPORT
                or self.amendment["original_deadline"] != self.one("cyber_dossier_first_launch")["deadline"]):
            raise AuditError("dossier_frozen_amendment_changed")
        self.hold_lineage()
        manifest = self.ledger.get(self.plan["input_manifest"], "cyber_dossier_input_manifest")
        self.document_rows = self.ledger.artifacts.read(manifest["documents_artifact"])
        self.documents = {r["document_id"]: self.ledger.artifacts.read(r["document_artifact"]) for r in self.document_rows}
        self.articles = self.ledger.artifacts.read(manifest["articles_artifact"])
        if data["action"] == "report":
            return self.report(session)
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("dossier_explicit_paid_execution_required")
        self.deadline = self.one("cyber_dossier_first_launch")["deadline"]
        self.provider = transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        try:
            if data["action"] == "pilot":
                self.pipeline(session, pilot=True)
            elif data["action"] == "run":
                gate = self.phases.get("pilot_v5_gate")
                if not gate or not self.ledger.artifacts.read(gate["artifact"])["passed"]:
                    raise PipelineStop("pilot_v5_gate_not_passed")
                self.pipeline(session, pilot=False)
            else:
                raise AuditError("dossier_unknown_action")
            stop = "phase_complete"
        except PipelineStop as error:
            stop = str(error)
            self.ledger.record(session, "cyber_dossier_stopped", digest([utc(), stop]), {
                "execution_amendment": self.amendment["_record_id"], "reason": stop, "phase": self.current_phase, "at": utc()})
        self.checkpoint(stop_reason=stop)
        return self.report(session)

    def read_focus_quarantine(self):
        source = Source(DIAGNOSTIC_OWNER)
        try:
            head = source.head()
            record = source.one("cyber_dossier_pilot_v4_reason_view")
            if (record["_record_id"] != V4_DIAGNOSTIC or record["source_report"] != PARENT_REPORT
                    or record["plan"] != self.plan["_record_id"] or record["execution_amendment"] != PARENT_AMENDMENT):
                raise AuditError("dossier_v5_diagnostic_binding_changed")
            flagged = set()
            for case in record["pair_references"]["exceptions"]:
                flagged.update(a["document_id"] for a in case["clarity"]
                               if a.get("status") == "valid" and a.get("label") == "multiple_focal_events")
                if case.get("pair_label") in {"related_event", "different_event"}:
                    flagged.update((case["left"], case["right"]))
            if not flagged <= set(self.documents):
                raise AuditError("dossier_v5_unknown_quarantine_source")
            fresh = Source(DIAGNOSTIC_OWNER)
            try:
                if fresh.head() != head:
                    raise AuditError("dossier_v5_diagnostic_changed_during_read")
            finally:
                fresh.close()
            return {"owner": str(DIAGNOSTIC_OWNER), "record_id": V4_DIAGNOSTIC,
                    "record_kind": "cyber_dossier_pilot_v4_reason_view", "head": head,
                    "snapshot_artifact": self.ledger.artifacts.put(record), "flagged_document_ids": sorted(flagged)}
        finally:
            source.close()

    def representation_census(self, proposals):
        rows = [contract.card_source_census(document, count_tokens=self.count) for document in self.documents.values()]
        packet_tokens, artifact_tokens, unavailable = [], [], 0
        for packet in proposals["packets"]:
            ids = packet["document_ids"]
            try:
                card = contract.build_evidence_card([self.documents[i] for i in ids], digest(["census", ids]),
                    digest(sorted(ids)), count_tokens=self.count, max_tokens=32000)
                packet_tokens.append(self.count(contract.card_matching_view(card)))
                artifact_tokens.append(self.count(card["card"]))
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                unavailable += 1
        return {"documents": len(rows), "sources": {key: sum(row[key] for row in rows) for key in rows[0]} if rows else {},
                "seed_proposal_card_tokens": {"count": len(packet_tokens), "capacity_deferred": unavailable,
                    "minimum": min(packet_tokens, default=0), "maximum": max(packet_tokens, default=0),
                    "total": sum(packet_tokens), "median": float(np.median(packet_tokens)) if packet_tokens else 0,
                    "p95": float(np.percentile(packet_tokens, 95)) if packet_tokens else 0,
                    "basis": "Compact source-exact model projection; no source text removed from the selected card.",
                    "full_audit_artifact_token_total": sum(artifact_tokens)},
                "limitation": "Zero-cost representation census; seed packets are proposals, not verified dossiers.",
                "model_calls": 0}

    def register_amendment(self, session, context):
        if not self.config.offline:
            raise AuditError("dossier_amendment_must_be_offline")
        self.absent("cyber_dossier_execution_amendment_v5")
        parent = self.one("cyber_dossier_execution_amendment_v4")
        self.amendment = parent
        self.hold_lineage()
        report = self.ledger.get(PARENT_REPORT, "cyber_dossier_report")
        budget = accounting(list(self.results.values()), self.ledger.unresolved)
        if (report["plan"] != self.plan["_record_id"] or report["execution_amendment"] != parent["_record_id"]
                or any(budget[key] < report[key] for key in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))):
            raise AuditError("dossier_prior_report_or_liability_changed")
        if (self.plan["cap_nanousd"] != CAP or PARAMETERS != previous.PARAMETERS):
            raise AuditError("dossier_registered_budget_or_parameters_changed")
        code = implementation()
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": code, "parent_plan": self.plan["_record_id"],
            "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
            "diagnostic_source": {"owner": str(DIAGNOSTIC_OWNER), "record_id": V4_DIAGNOSTIC},
            "limitation": "Adaptive functional/model-reference pilot, not population precision or recall."}})["id"]
        diagnostic = self.read_focus_quarantine()
        quarantined = set(diagnostic["flagged_document_ids"])
        blocked_groups = set()
        for name in self.phases:
            if name.endswith("_seeds"):
                phase = self.phase(session, name)
                blocked_groups.update(d for d, members in phase.get("groups", {}).items() if quarantined.intersection(members))
        proposals = self.phase(session, "seed_proposals")
        if not proposals or not self.phase(session, "embeddings"):
            raise AuditError("dossier_v5_retained_candidate_frame_required")
        summaries = list(self.summary_attempts().values())
        ancestors = [self.one(kind) for kind in ("cyber_dossier_execution_amendment", "cyber_dossier_execution_amendment_v3", "cyber_dossier_execution_amendment_v4")]
        prior_packets = [p for ancestor in ancestors for p in self.ledger.artifacts.read(ancestor["pilot_selection_artifact"])["packets"]]
        selection = next_pilot_packets(proposals["packets"], quarantined | {i for row in summaries for i in row["document_ids"]},
                                       prior_packets, PARAMETERS["pilot_packets"])
        if len(selection["packets"]) != PARAMETERS["pilot_packets"]:
            raise AuditError("dossier_v5_insufficient_untouched_pilot_packets")
        versions = {"protocol": protocol}
        deadline = self.one("cyber_dossier_first_launch")["deadline"]
        for kind, value in {
            "policy": {"method": METHOD, "total_cap_nanousd": CAP, "main_cap_nanousd": PARAMETERS["non_audit_cap_nanousd"],
                "audit_cap_nanousd": PARAMETERS["audit_cap_nanousd"], "budget_reset": False,
                "original_deadline": deadline, "deadline_extended": False, "provider_retries": 0, "generation_calls": 0},
            "selection": {"rules": selection["rule"], "input_manifest": self.plan["input_manifest"],
                "selected_packet_count": len(selection["packets"]), "quarantine_reference": diagnostic},
            "prompt": {"instructions": "Deterministic source-exact evidence cards; independent full-source focus/coverage QA, supported-only matching, blinded Astra quality checks. Full-member control never influences joins.",
                "contract_implementation": code[str(Path(contract.__file__).relative_to(ROOT))]},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"]
        # Registered procedure precedes the actual deterministic representation census.
        census = self.representation_census(proposals)
        amendment = {"method": METHOD, "parent_plan": self.plan["_record_id"], "parent_implementation": parent["implementation"],
            "parent_execution_amendment": parent["_record_id"], "parent_report": PARENT_REPORT,
            "ancestor_execution_amendments": {key: row["_record_id"] for key, row in zip(("v2", "v3", "v4"), ancestors, strict=True)},
            "diagnostic_plan": DIAGNOSTIC_PLAN, "diagnostic_amendment": DIAGNOSTIC_REPAIR, "diagnostic_report": DIAGNOSTIC_REPORT,
            "v4_diagnostic": diagnostic, "quarantined_document_ids": sorted(quarantined), "quarantined_group_ids": sorted(blocked_groups),
            "main_cap_nanousd": PARAMETERS["non_audit_cap_nanousd"], "audit_cap_nanousd": PARAMETERS["audit_cap_nanousd"],
            "contingency_nanousd": 0, "card_reference_minimum": CARD_AUDIT_MIN, "card_reference_target": CARD_AUDIT_MAX,
            "implementation": code, "versions": versions, "original_deadline": deadline,
            "legacy_unresolved_attempts": sorted(self.ledger.unresolved), "legacy_budget": budget,
            "legacy_response_keys": sorted(self.results), "legacy_summary_versions_artifact": self.ledger.artifacts.put(summaries),
            "pilot_selection_artifact": self.ledger.artifacts.put(selection), "representation_census": census,
            "cap_nanousd": CAP, "at": utc()}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment_v5", METHOD, amendment)
        return {"id": identifier, "parent_plan": self.plan["_record_id"], "original_deadline": deadline,
                "pilot_packets": len(selection["packets"]), "legacy_budget": budget, "paid_calls": 0,
                "quarantined_articles": len(quarantined), "quarantined_groups": len(blocked_groups), "representation_census": census}

    def before_dispatch(self, invocation=None):
        if (self.ledger.root / "STOP").exists():
            raise PipelineStop("user_stop")
        if datetime.now(timezone.utc) >= datetime.fromisoformat(self.deadline):
            raise PipelineStop("deadline")
        if invocation is None:
            return
        model = invocation.request["model"]
        if invocation.kind == "embeddings":
            tokens = sum(len(v) for v in invocation.request["input"])
            tpm = PARAMETERS["embedding_tpm"]
        else:
            tokens = self.count(invocation.request) * 1.5
            tpm = PARAMETERS["astra_tpm"] if model == "gpt-6-astra" else PARAMETERS["luna_tpm"]
        with self.pacing_lock:
            delay = self.next_dispatch.get(model, 0) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.before_dispatch()  # Recheck STOP/deadline after a pacing wait.
            self.next_dispatch[model] = time.monotonic() + max(60 / PARAMETERS["rpm"], 60 * tokens / tpm)

    def phase(self, session, name, value=None):
        existing = self.phases.get(name)
        if existing:
            return self.ledger.artifacts.read(existing["artifact"])
        if value is None:
            return None
        ref = self.ledger.artifacts.put(value)
        record = {"name": name, "artifact": ref, "plan": self.plan["_record_id"],
                  "execution_amendment": self.amendment["_record_id"], "at": utc()}
        identifier = self.ledger.record(session, "cyber_dossier_phase", name, record)
        self.phases[name] = {**record, "_record_id": identifier}
        return value

    def calls(self, session, packets):
        """One attempt per exact wire request, with liabilities shared across every stage."""
        tasks = []
        seen = {v["task_key"] for v in self.ledger.unresolved.values()}
        seen.update(self.results)
        seed_attempts = self.seed_attempts()
        audit_attempts = self.article_set_attempts("audit")
        for packet in packets:
            if packet["phase"] == "summary":
                raise AuditError("dossier_v5_generation_prohibited")
            packet.setdefault("kind", "responses" if packet["phase"] in {"audit", "card_quality", "card_quality_audit"} else "decisions")
            key = self.task_key(packet)
            if packet["phase"] == "seed":
                old = seed_attempts.get(tuple(sorted(packet["document_ids"])))
                if old and self.task_key(old) != key:
                    raise AuditError("dossier_seed_article_set_already_attempted_no_retry")
                seed_attempts[tuple(sorted(packet["document_ids"]))] = packet
            if packet["phase"] == "audit":
                old = audit_attempts.get(tuple(sorted(packet["document_ids"])))
                if old and self.task_key(old) != key:
                    raise AuditError("dossier_audit_article_set_already_attempted_no_retry")
                audit_attempts[tuple(sorted(packet["document_ids"]))] = packet
            if key not in seen:
                tasks.append((key, packet))
                seen.add(key)
        self.phase_tasks_planned = len(packets)
        self.phase_tasks_completed = sum(self.task_key(p) in self.results for p in packets)
        task_set = digest(sorted(self.task_key(p) for p in packets))
        self.checkpoint(phase_tasks_planned=self.phase_tasks_planned, phase_tasks_completed=self.phase_tasks_completed,
                        phase_task_set_sha256=task_set)
        for start in range(0, len(tasks), PARAMETERS["workers"]):
            self.before_dispatch()
            wave, metadata = [], []
            for key, packet in tasks[start:start + PARAMETERS["workers"]]:
                budget = accounting(list(self.results.values()), self.ledger.unresolved)
                reservation = reserve(packet)
                is_audit = packet["request"].get("model") == "gpt-6-astra"
                category = "audit" if is_audit else "main"
                used = sum((max(r["reserved_nanousd"], r["cost_nanousd"] or 0) if r["hold"] else r["cost_nanousd"] or 0)
                           for r in self.results.values() if r["category"] == category)
                unreturned = sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values()
                                 if v.get("category") == category and v["task_key"] not in self.results)
                limit = PARAMETERS["audit_cap_nanousd"] if is_audit else PARAMETERS["non_audit_cap_nanousd"]
                if budget["committed_nanousd"] + reservation > CAP or used + unreturned + reservation > limit:
                    if not wave:
                        raise PipelineStop("budget_bound_" + category)
                    break
                attempt = str(uuid.uuid4())
                invocation = transport.Invocation(packet["request"], attempt, kind=packet["kind"])
                intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": self.plan["_record_id"],
                    "execution_amendment": self.amendment["_record_id"],
                    "request": self.ledger.artifacts.put(packet["request"]), "packet": self.ledger.artifacts.put(packet),
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "phase": packet["phase"], "category": category,
                    "reserved_nanousd": reservation, "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((invocation, attempt))
                metadata.append((key, packet, intended))
            failures = 0
            for index, response in self.gateway.codex_dispatch(session, self.provider, wave, len(wave)):
                key, packet, intended = metadata[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                cost = billed(packet, response)
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intended["reserved_nanousd"]
                result, error = None, None
                http_ok = 200 <= (raw.get("http_status") or 0) < 300
                if response.payload is not None and http_ok:
                    try:
                        if packet["kind"] == "embeddings":
                            result = parse_embeddings(packet, response.payload)
                        elif packet["phase"] == "audit":
                            result = contract.parse_audit(packet, response.payload)
                        elif packet["phase"] == "card_quality":
                            result = contract.parse_card_quality(packet, response.payload)
                        elif packet["phase"] == "card_quality_audit":
                            result = contract.parse_card_quality_audit(packet, response.payload)
                        else:
                            result = contract.parse_decisions(packet, response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as caught:
                        error = type(caught).__name__ + ":" + str(caught)[:180] if isinstance(caught, ResearchError) else type(caught).__name__
                elif not http_ok:
                    error = "dossier_http_not_success"
                row = {"plan": self.plan["_record_id"], "task_key": key, "phase": packet["phase"], "category": intended["category"],
                       "execution_amendment": self.amendment["_record_id"],
                       "packet": intended["packet"], "request": intended["request"], "response": response_ref, "attempt": intended["attempt"],
                       "parsed": self.ledger.artifacts.put(result) if result is not None else None,
                       "cost_nanousd": cost, "reserved_nanousd": intended["reserved_nanousd"] if hold else 0,
                       "hold": hold, "validation_error": error, "http_status": raw.get("http_status"), "at": utc()}
                identifier = self.ledger.record(session, "cyber_dossier_response", key, row)
                self.results[key] = {**row, "_record_id": identifier}
                if hold:
                    self.ledger.unresolved[intended["attempt"]]["cost_nanousd"] = cost
                else:
                    self.complete(session, intended, response_ref, identifier, "valid" if result else "invalid")
                failures += hold or result is None
            self.phase_tasks_completed = sum(self.task_key(p) in self.results for p in packets)
            self.checkpoint(phase_tasks_planned=self.phase_tasks_planned, phase_tasks_completed=self.phase_tasks_completed,
                            phase_task_set_sha256=task_set)
            if failures >= 3:
                raise PipelineStop("repeated_provider_or_validation_failure")
            if len(wave) < len(tasks[start:start + PARAMETERS["workers"]]):
                raise PipelineStop("budget_bound_partial_wave")
        return [self.parsed(packet) for packet in packets]

    def parsed(self, packet):
        row = self.results.get(self.task_key(packet))
        return self.ledger.artifacts.read(row["parsed"]) if row and row["parsed"] and not row["hold"] else None

    def vectors(self, session):
        self.current_phase = "1_embeddings"
        saved = self.phase(session, "embeddings")
        if saved:
            return saved
        packets = embedding_packets(list(self.documents.values()), self.encoder)
        if sum(reserve(p) for p in packets) > PARAMETERS["embedding_cap_nanousd"]:
            raise PipelineStop("embedding_forecast_over_allocation")
        replies = self.calls(session, packets)
        pieces = {}
        for packet, reply in zip(packets, replies, strict=True):
            if not reply:
                continue
            for locator, vector in zip(packet["chunks"], reply["vectors"], strict=True):
                pieces.setdefault(locator["document_id"], []).append((locator, vector))
        ids, vectors, missing = [], [], []
        for identifier in sorted(self.documents):
            values = sorted(pieces.get(identifier, []), key=lambda x: x[0]["token_start"])
            cursor, sums = 0, np.zeros(PARAMETERS["dimensions"], dtype=np.float64)
            for locator, vector in values:
                if locator["token_start"] != cursor:
                    break
                length = locator["token_end"] - cursor
                sums += np.asarray(vector) * length
                cursor = locator["token_end"]
            if not values or cursor != values[-1][0]["full_tokens"] or np.linalg.norm(sums) == 0:
                missing.append(identifier)
                continue
            ids.append(identifier)
            vectors.append((sums / np.linalg.norm(sums)).tolist())
        return self.phase(session, "embeddings", {"document_ids": ids, "vectors": vectors, "missing": missing,
            "purpose": "Candidate retrieval; full contiguous token coverage; similarity is not event identity."})

    def seed_results(self, session, packets, label):
        self.current_phase = "2_full_article_seed_verification_" + label
        saved = self.phase(session, label + "_seeds")
        if saved:
            return saved
        prior = self.seed_attempts()
        requests = [prior[tuple(sorted(p["document_ids"]))] if tuple(sorted(p["document_ids"])) in prior else
                    contract.seed_request([self.documents[i] for i in p["document_ids"]], count_tokens=self.count,
                                          max_tokens=PARAMETERS["packet_tokens"]) for p in packets]
        replies = self.calls(session, requests)
        pair_answers, clarity, covered = [], {}, set()
        for packet, reply in zip(requests, replies, strict=True):
            covered.update(packet["document_ids"])
            for answer in (reply or {}).get("answers", {}).values():
                if answer.get("kind") == "pair":
                    pair_answers.append(answer)
                elif answer.get("kind") == "clarity":
                    clarity[answer["document_id"]] = answer
        partition = candidates.complete_link_partition(sorted(covered), pair_answers,
                    clarity=clarity, threshold=PARAMETERS["positive_confidence"])
        groups = {digest(["seed", sorted(members)]): sorted(members) for members in partition["groups"] if len(members) > 1}
        quarantine = set(self.amendment["quarantined_document_ids"])
        quarantined_groups = {d: m for d, m in groups.items() if d in self.amendment["quarantined_group_ids"] or quarantine.intersection(m)}
        groups = {d: m for d, m in groups.items() if d not in quarantined_groups}
        return self.phase(session, label + "_seeds", {"groups": groups, "pair_answers": pair_answers,
            "clarity": clarity, "covered": sorted(covered), "partition": partition,
            "quarantined_groups": quarantined_groups,
            "reused_seed_packets": sum(tuple(sorted(p["document_ids"])) in prior for p in packets),
            "failed_packets": sum(r is None for r in replies), "packets": len(packets)})

    def make_cards(self, session, groups, label):
        self.current_phase = "3_evidence_cards_" + label
        saved = self.phase(session, label + "_cards")
        if saved:
            return saved
        old_summaries = self.summary_attempts()
        retained = {(row["dossier_id"], row["membership_revision"]): row
                    for row in self.rows("cyber_dossier_evidence_card")}
        cards, deferred, checks, checked = {}, [], [], []
        for dossier, members in sorted(groups.items()):
            revision = digest(sorted(members))
            if len(members) > 64:
                deferred.append({"dossier_id": dossier, "membership_revision": revision,
                                 "reason": "complete_group_exceeds_64_source_capacity", "members": len(members)})
                continue
            if (dossier, revision) in old_summaries:
                deferred.append({"dossier_id": dossier, "membership_revision": revision,
                                 "reason": "previous_summary_binding_no_card_replacement"})
                continue
            if dossier in self.amendment["quarantined_group_ids"] or set(members) & set(self.amendment["quarantined_document_ids"]):
                deferred.append({"dossier_id": dossier, "reason": "prior_reference_focus_quarantine"})
                continue
            try:
                row = retained.get((dossier, revision))
                if row:
                    card = self.ledger.artifacts.read(row["artifact"])
                    expected = contract.build_evidence_card([self.documents[i] for i in members], dossier,
                        revision, count_tokens=self.count, max_tokens=32000)
                    if card != expected:
                        raise AuditError("dossier_frozen_evidence_card_changed")
                else:
                    card = contract.build_evidence_card([self.documents[i] for i in members], dossier,
                        revision, count_tokens=self.count, max_tokens=32000)
                    self.ledger.record(session, "cyber_dossier_evidence_card", digest([dossier, revision]), {
                        "dossier_id": dossier, "membership_revision": revision, "card_version": card["card_version"],
                        "document_ids": sorted(members), "artifact": self.ledger.artifacts.put(card),
                        "execution_amendment": self.amendment["_record_id"], "model_generation_calls": 0})
                cards[dossier] = card
                checks.append(contract.card_quality_request([self.documents[i] for i in members], card,
                    count_tokens=self.count, max_tokens=32000, max_output_tokens=2000))
                checked.append(dossier)
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                deferred.append({"dossier_id": dossier, "reason": "card_or_full_source_quality_packet_capacity"})
        replies = self.calls(session, checks)
        usable, quality = {}, {}
        for dossier, reply in zip(checked, replies, strict=True):
            quality[dossier] = reply
            if reply and reply.get("status") == "valid" and reply.get("label") == "supported":
                usable[dossier] = cards[dossier]
            else:
                deferred.append({"dossier_id": dossier, "reason": "card_quality_not_supported"})
        return self.phase(session, label + "_cards", {"usable": usable, "quality": quality,
            "deferred": deferred, "constructed": len(cards), "model_generation_calls": 0, "human_validated": False})

    def card_reference(self, session, cards, groups):
        name = "pilot_v5_card_quality_reference"
        saved = self.phase(session, name)
        if saved:
            return saved
        selected = sorted(cards.items(), key=lambda item: digest(["pilot-v5-card-quality", item[1]["card_version"]]))[:CARD_AUDIT_MAX]
        selection = self.phase(session, name + "_selection", {"cards": [
            {"dossier_id": dossier, "card_version": snapshot["card_version"],
             "membership_revision": snapshot["membership_revision"]} for dossier, snapshot in selected],
            "replacement_allowed": False, "target": CARD_AUDIT_MAX, "minimum": CARD_AUDIT_MIN})
        if [v["card_version"] for v in selection["cards"]] != [s["card_version"] for _, s in selected]:
            raise AuditError("dossier_card_reference_selection_changed")
        packets, retained, items = [], [], []
        for dossier, snapshot in selected:
            try:
                packets.append(contract.card_quality_audit_request([self.documents[i] for i in groups[dossier]], snapshot,
                    count_tokens=self.count, max_tokens=32000, max_output_tokens=2000))
                retained.append((dossier, snapshot))
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                items.append({"dossier_id": dossier, "card_version": snapshot["card_version"], "reference": None,
                              "reason": "card_reference_packet_capacity"})
        planned = [{"dossier_id": dossier, "card_version": snapshot["card_version"], "task_key": self.task_key(packet)}
                   for (dossier, snapshot), packet in zip(retained, packets, strict=True)]
        planned += [{"dossier_id": item["dossier_id"], "card_version": item["card_version"], "task_key": None}
                    for item in items]
        self.phase(session, name + "_plan", {"items": planned})
        for (dossier, snapshot), reply in zip(retained, self.calls(session, packets), strict=True):
            items.append({"dossier_id": dossier, "card_version": snapshot["card_version"], "reference": reply})
        return self.phase(session, name, {"items": items, **self.card_reference_status(session), "blinded_to_luna": True,
            "human_validated": False, "replacement_allowed": False})

    def card_reference_status(self, session):
        name = "pilot_v5_card_quality_reference"
        selection = self.phase(session, name + "_selection")
        if selection is None:
            return None
        plan = self.phase(session, name + "_plan")
        planned = plan["items"] if plan else [{"task_key": None} for _ in selection["cards"]]
        pending = {v["task_key"] for v in self.ledger.unresolved.values()}
        labels, states = Counter(), Counter()
        for item in planned:
            row = self.results.get(item["task_key"])
            if item["task_key"] in pending or (row and row["hold"]):
                states["unknown"] += 1
            elif row:
                reply = self.ledger.artifacts.read(row["parsed"]) if row["parsed"] else None
                if reply and reply.get("status") == "valid":
                    labels[reply["label"]] += 1
                    states["valid"] += 1
                else:
                    states["invalid"] += 1
            else:
                states["not_attempted"] += 1
        selected = len(selection["cards"])
        return {"target": CARD_AUDIT_MAX, "minimum": CARD_AUDIT_MIN, "selected": selected,
            "attempted": selected - states["not_attempted"], "valid": states["valid"],
            **{label: labels[label] for label in ("supported", "identity_missing", "unclear_focus", "incoherent_group", "uncertain")},
            "unavailable": selected - states["valid"], "invalid": states["invalid"], "unknown": states["unknown"],
            "not_attempted": states["not_attempted"], "selection_frozen": True,
            "passed": selected >= CARD_AUDIT_MIN and labels["supported"] == selected,
            "human_validated": False, "replacement_allowed": False}

    def assignments(self, session, index, document_ids, groups, cards, label, recovery=False):
        self.current_phase = "4_card_assignment_" + label
        saved = self.phase(session, label + "_assignments")
        if saved:
            return saved
        requests, shortlists, empty, packet_coverage = [], {}, [], {}
        valid_groups = {d: m for d, m in groups.items() if d in cards}
        for identifier in document_ids:
            shortlist = candidates.shortlist_dossiers(index, identifier, valid_groups,
                limit=PARAMETERS["assignment_candidates"], recovery_limit=PARAMETERS["recovery_candidates"])
            route = shortlist["candidates"] if recovery else shortlist["primary"]
            chosen = []
            for item in route:
                dossier = item["dossier_id"] if isinstance(item, dict) else item
                if identifier not in valid_groups[dossier]:
                    chosen.append(dossier)
            chosen = chosen[:PARAMETERS["recovery_candidates"] if recovery else PARAMETERS["assignment_candidates"]]
            shortlists[identifier] = shortlist
            if not chosen:
                empty.append(identifier)
                continue
            try:
                packed = pack_assignment(self.documents[identifier], [cards[d] for d in chosen], self.count)
                requests.extend(packed)
                packet_coverage[identifier] = {"chosen_dossiers": chosen, "packets": len(packed),
                    "candidate_counts": [len(p["bindings"]) for p in packed], "coverage_complete": True}
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                empty.append(identifier)
                packet_coverage[identifier] = {"chosen_dossiers": chosen, "packets": 0,
                    "coverage_complete": False, "reason": "full_article_single_candidate_exceeds_capacity"}
        replies = self.calls(session, requests)
        proposals, unresolved = {}, {i: "no_usable_candidate_or_packet_limit" for i in empty}
        decisions = {}
        accumulated, failed = {}, set(empty)
        for packet, reply in zip(requests, replies, strict=True):
            identifier = packet["document_ids"][0]
            answers = list((reply or {}).get("answers", {}).values())
            accumulated.setdefault(identifier, []).extend(answers)
            if reply is None:
                failed.add(identifier)
        for identifier, answers in accumulated.items():
            decisions[identifier] = answers
            clarity = [a for a in answers if a.get("kind") == "clarity"]
            matches = [a for a in answers if a.get("kind") == "assignment" and contract.assignment_route(a) == "positive"]
            uncertain = [a for a in answers if a.get("kind") == "assignment" and contract.assignment_route(a) == "unresolved"]
            if identifier in failed:
                unresolved[identifier] = "incomplete_candidate_evaluation"
            elif not clarity or not all(clear(a, "clear_single_event") for a in clarity):
                unresolved[identifier] = "focal_event_not_clear"
            elif len(matches) == 1 and not uncertain:
                answer = matches[0]
                expected = cards[answer["dossier_id"]]
                if answer["card_version"] != expected["card_version"]:
                    raise AuditError("dossier_stale_card_proposal")
                proposals[identifier] = {"dossier_id": answer["dossier_id"], "card_version": answer["card_version"],
                    "membership_revision": answer["membership_revision"],
                    "task_keys": [self.task_key(p) for p in requests if p["document_ids"][0] == identifier]}
            else:
                unresolved[identifier] = "competing_or_uncertain_candidates" if matches or uncertain else "no_match_in_shortlist"
        return self.phase(session, label + "_assignments", {"proposals": proposals, "unresolved": unresolved,
            "decisions": decisions, "shortlists": shortlists, "packet_coverage": packet_coverage,
            "all_potential_matches_guaranteed": False})

    def full_bundle_control(self, session, withheld, assigned, groups):
        """Fixed matched candidates; diagnostic outcomes never enter membership."""
        name = "pilot_v5_full_bundle_control"
        saved = self.phase(session, name)
        if saved:
            return saved
        plans, requests, unavailable = [], [], {}
        for identifier in sorted(withheld):
            coverage = assigned["packet_coverage"].get(identifier, {})
            chosen = coverage.get("chosen_dossiers", [])
            entry = {"document_id": identifier, "chosen_dossiers": chosen, "task_keys": [],
                     "card_coverage_complete": coverage.get("coverage_complete", False)}
            if not chosen:
                unavailable[identifier] = "no_card_arm_candidates"
                plans.append(entry)
                continue
            try:
                if any(len(groups[d]) > 64 for d in chosen):
                    raise ResearchError("dossier_packet_capacity")
                bundles = [contract.full_member_bundle([self.documents[i] for i in groups[d]], d,
                    digest(sorted(groups[d])), count_tokens=self.count, max_tokens=32000) for d in chosen]
                packets = pack_assignment(self.documents[identifier], bundles, self.count,
                                          request_factory=contract.full_member_assignment_request)
                entry["task_keys"] = [self.task_key(packet) for packet in packets]
                requests.extend(packets)
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                unavailable[identifier] = "full_source_control_capacity"
            plans.append(entry)
        plan = self.phase(session, name + "_plan", {"queries": plans, "unavailable": unavailable,
            "replacement_allowed": False, "diagnostic_only": True, "candidate_selection_from_card_arm": True})
        if plan["queries"] != plans or plan["unavailable"] != unavailable:
            raise AuditError("dossier_control_fixed_candidates_changed")
        replies = self.calls(session, requests)
        accumulated, failures = {}, set(unavailable)
        for packet, reply in zip(requests, replies, strict=True):
            identifier = packet["document_ids"][0]
            accumulated.setdefault(identifier, []).extend((reply or {}).get("answers", {}).values())
            if reply is None:
                failures.add(identifier)
        compared, labels_agree, match_agree, clear_matches = 0, 0, 0, 0
        details = []
        for entry in plans:
            identifier, chosen = entry["document_id"], entry["chosen_dossiers"]
            answers = accumulated.get(identifier, [])
            control_map = {a["dossier_id"]: contract.assignment_route(a) for a in answers if a.get("kind") == "assignment"}
            card_answers = assigned["decisions"].get(identifier, [])
            card_map = {a["dossier_id"]: contract.assignment_route(a) for a in card_answers if a.get("kind") == "assignment"}
            control_clarity = [a for a in answers if a.get("kind") == "clarity"]
            card_clarity = [a for a in card_answers if a.get("kind") == "clarity"]
            control_complete = bool(chosen) and identifier not in failures and set(control_map) == set(chosen)
            card_complete = bool(entry["card_coverage_complete"] and chosen) and set(card_map) == set(chosen)
            control_clear = bool(control_clarity) and all(clear(a, "clear_single_event") for a in control_clarity)
            card_clear = bool(card_clarity) and all(clear(a, "clear_single_event") for a in card_clarity)
            positives = [d for d, route in control_map.items() if route == "positive"]
            match = positives[0] if control_complete and control_clear and len(positives) == 1 and "unresolved" not in control_map.values() else None
            clear_matches += match is not None
            if control_complete and card_complete:
                compared += 1
                labels_agree += control_map == card_map and control_clear == card_clear
                match_agree += match == (assigned["proposals"].get(identifier) or {}).get("dossier_id")
            details.append({**entry, "control_complete": control_complete, "card_complete": card_complete,
                "control_routes": control_map, "card_routes": card_map, "control_match": match,
                "control_clear": control_clear, "card_clear": card_clear})
        keys = {self.task_key(packet) for packet in requests}
        rows = [row for key, row in self.results.items() if key in keys]
        pending = {a: row for a, row in self.ledger.unresolved.items() if row["task_key"] in keys}
        budget = accounting(rows, pending)
        return self.phase(session, name, {"selected_queries": len(plans), "planned_requests": len(keys),
            "stored_responses": len(rows), "complete_control_queries": sum(d["control_complete"] for d in details),
            "complete_card_queries": sum(d["card_complete"] for d in details), "compared_queries": compared,
            "route_and_clarity_agreements": labels_agree, "match_agreements": match_agree,
            "control_clear_unique_matches": clear_matches,
            "card_clear_unique_matches": sum(i in assigned["proposals"] for i in withheld),
            "unavailable_queries": dict(Counter(unavailable.values())), **budget,
            "details_artifact": self.ledger.artifacts.put(details), "diagnostic_only": True,
            "candidate_selection_from_card_arm": True, "replacement_allowed": False,
            "changes_membership": False, "independent_gold": False})

    def reference_plan(self, session, pair_ids, label):
        pair_ids = [list(pair) for pair in pair_ids]
        saved = self.phase(session, label + "_reference_plan")
        if saved:
            if saved["selected_pairs"] != pair_ids:
                raise AuditError("dossier_reference_selection_changed")
            return saved
        items = []
        attempted = self.article_set_attempts("audit")
        for left, right in pair_ids:
            try:
                old = attempted.get(tuple(sorted((left, right))))
                packet = old or contract.audit_request([self.documents[left], self.documents[right]], count_tokens=self.count,
                                                       max_output_tokens=4000)
                packet["kind"] = "responses"
                items.append({"left": left, "right": right, "task_key": self.task_key(packet),
                              "packet": self.ledger.artifacts.put(packet), "reason": None,
                              "reused_prior_reference": old is not None, "packet_method": packet.get("method")})
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                items.append({"left": left, "right": right, "task_key": None, "packet": None,
                              "reason": "reference_packet_capacity"})
        return self.phase(session, label + "_reference_plan", {"selected_pairs": pair_ids, "items": items,
            "sampling": label, "replacement_allowed": False,
            "target_per_stratum": PARAMETERS["final_reference_pairs_per_stratum"] if label.startswith("full_v5_") else len(pair_ids)})

    def reference(self, session, pair_ids, label):
        self.current_phase = "reference_" + label
        plan = self.reference_plan(session, pair_ids, label)
        saved = self.phase(session, label + "_reference")
        if saved:
            return saved
        retained = [item for item in plan["items"] if item["packet"]]
        packets = [self.ledger.artifacts.read(item["packet"]) for item in retained]
        results = [{"left": item["left"], "right": item["right"], "reference": None, "available": False,
                    "reason": item["reason"]} for item in plan["items"] if not item["packet"]]
        replies = self.calls(session, packets)
        for item, reply in zip(retained, replies, strict=True):
            answer = next((a for a in (reply or {}).get("answers", {}).values() if a.get("kind") == "pair"), None)
            clarity = [a for a in (reply or {}).get("answers", {}).values() if a.get("kind") == "clarity"]
            results.append({"left": item["left"], "right": item["right"], "reference": answer, "available": answer is not None,
                            "reused_prior_reference": item.get("reused_prior_reference", False),
                            "packet_method": item.get("packet_method"),
                            "clarity": clarity, "reference_both_clear": len(clarity) == 2 and all(a["label"] == "clear_single_event" for a in clarity)})
        return self.phase(session, label + "_reference", {"items": results, "reference_model": "gpt-6-astra",
            "blinded_to_luna": True, "human_validated": False, "sampling": label,
            "independence_limit": "Pairs may share events or articles; model reference is not adjudicated truth."})

    def pipeline(self, session, pilot):
        label = "pilot_v5" if pilot else "full_v5"
        vectors = self.vectors(session)
        if len(vectors["document_ids"]) < .99 * len(self.documents):
            raise PipelineStop("embedding_coverage_below_99_percent")
        self.current_phase = "1_candidate_retrieval"
        ids = vectors["document_ids"]
        index = candidates.build_index(ids, np.asarray(vectors["vectors"], dtype=np.float32), self.documents,
                                       vector_k=PARAMETERS["vector_k"], lexical_k=40)
        self.phase(session, "candidate_index", index.manifest())
        proposals = self.phase(session, "seed_proposals")
        if proposals is None:
            proposals = self.phase(session, "seed_proposals", candidates.propose_seed_packets(index, self.documents,
                count_tokens=self.count, cosine_threshold=PARAMETERS["seed_similarity"],
                max_articles=PARAMETERS["max_seed_size"], max_tokens=PARAMETERS["packet_tokens"]))
        packets = sorted(proposals["packets"], key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
        if pilot:
            selection = self.ledger.artifacts.read(self.amendment["pilot_selection_artifact"])
            packets = selection["packets"]
        seeds = self.seed_results(session, packets, label)
        groups = seeds["groups"]
        if pilot and not groups:
            raise PipelineStop("pilot_no_verified_seed_groups")
        if pilot:
            challenge = self.phase(session, "pilot_v5_positive_challenge")
            if challenge is None:
                challenge = self.phase(session, "pilot_v5_positive_challenge", positive_challenge(groups))
            groups = challenge["groups"]
        cards = self.make_cards(session, groups, label + "_seed")
        members = {i for g in groups.values() for i in g}
        unclear = {i for i, answer in seeds["clarity"].items() if not clear(answer, "clear_single_event")}
        unclear.update(self.amendment["quarantined_document_ids"])
        rejected_members = {i for d, members in groups.items() if d not in cards["usable"] for i in members}
        unclear.update(rejected_members)
        remaining = [i for i in ids if i not in members and i not in unclear]
        if pilot:
            excluded = set(selection["excluded_document_ids"])
            whole_seed_members = {i for group in seeds["groups"].values() for i in group}
            natural = [i for i in remaining if i not in excluded and i not in whole_seed_members]
            usable_members = {i for d, group in groups.items() if d in cards["usable"] for i in group}
            natural = sorted(natural, key=lambda i: (-max((float(np.dot(index.vectors[index.positions[i]], index.vectors[index.positions[j]]))
                            for j in usable_members), default=0), i))[:PARAMETERS["pilot_assignments"]] if usable_members else []
            withheld = sorted(challenge["held_out"])
            remaining = withheld + natural
            self.phase(session, "pilot_v5_assignment_selection", {"withheld": withheld, "natural": natural,
                "natural_ranked_only_to_usable_cards": True, "withheld_source_absent_from_card": True})
        assigned = self.assignments(session, index, remaining, groups, cards["usable"], label + "_seed")
        verified_groups, seed_provisional, seed_rejected = quality_partition(groups, cards)
        final_groups, applied, conflicts = commit_proposals(verified_groups, assigned["proposals"])
        if pilot:
            self.full_bundle_control(session, withheld, assigned, groups)
            group_membership = {i: d for d, group in groups.items() for i in group}
            positive_pairs = sorted({tuple(sorted((a["left"], a["right"]))) for a in seeds["pair_answers"]
                                     if clear(a, "same_event") and a["left"] in group_membership
                                     and group_membership[a["left"]] == group_membership.get(a["right"])},
                                     key=lambda pair: digest(["pilot-reference", pair]))[:PARAMETERS["pilot_reference_pairs"]]
            reference = self.reference(session, positive_pairs, "pilot_v5_positive")
            assignment_pairs = sorted({tuple(sorted((identifier, groups[value["dossier_id"]][0])))
                for identifier, value in applied.items()}, key=lambda pair: digest(["pilot-assignment-reference", pair]))[:6]
            assignment_reference = self.reference(session, assignment_pairs, "pilot_v5_assignments")
            card_reference = self.card_reference(session, cards["usable"], groups)
            judgments = [r["reference"] for r in reference["items"] + assignment_reference["items"]]
            same = sum(a is not None and a.get("label") == "same_event" for a in judgments)
            false_merge = sum(a is not None and a.get("label") in {"related_event", "different_event"} for a in judgments)
            card_fraction = len(cards["usable"]) / len(groups) if groups else 0
            reference_clarity = all(r.get("reference_both_clear", False) for r in reference["items"] + assignment_reference["items"])
            costs_by_phase = {}
            for phase_name in ("seed", "card", "card_quality", "assignment"):
                values = [r["cost_nanousd"] for r in self.results.values()
                          if r["phase"] == phase_name and not r["hold"] and r["cost_nanousd"] is not None
                          and r["task_key"] not in self.amendment["legacy_response_keys"]]
                costs_by_phase[phase_name] = sum(values) / len(values) if values else None
            n = len(ids)
            seed_packet_count = len(proposals["packets"])
            # Explicit scenarios, not a guessed dossier count or increased admission cap.
            current_budget = accounting(list(self.results.values()), self.ledger.unresolved)
            audit_budget = accounting([r for r in self.results.values() if r["category"] == "audit"],
                                      {a: v for a, v in self.ledger.unresolved.items() if v.get("category") == "audit"})
            current_main = current_budget["committed_nanousd"] - audit_budget["committed_nanousd"]
            unasked_seeds = max(0, seed_packet_count - sum(r["phase"] == "seed" for r in self.results.values()))
            scenarios = {}
            for scenario, card_rounds, assignment_packets in (("one_card_per_input_two_assignment_packets", 1, 2),
                    ("two_cards_per_input_four_assignment_packets", 2, 4)):
                main = current_main + (costs_by_phase["seed"] or 0) * unasked_seeds + n * (
                    card_rounds * ((costs_by_phase["card"] or 0) + (costs_by_phase["card_quality"] or 0))
                    + assignment_packets * (costs_by_phase["assignment"] or 0))
                scenarios[scenario] = {"main_nanousd": math.ceil(main),
                    "total_with_full_audit_nanousd": math.ceil(main) + PARAMETERS["audit_cap_nanousd"],
                    "within_main_allocation": main <= PARAMETERS["non_audit_cap_nanousd"]}
            forecast = {"basis": "Pilot mean cost scenarios, not guaranteed bounds; recovery may contain15 cards in one packet and costs more than a5-candidate pilot packet. Exact per-request reservations and registered category caps govern admission. Final dossier count is not inferred from seed packets.",
                "mean_request_cost_nanousd": costs_by_phase, "scenarios": scenarios,
                "seed_packets": seed_packet_count, "maximum_within_packet_multiarticle_groups": sum(len(p["document_ids"]) // 2 for p in proposals["packets"]),
                "current_committed_nanousd": current_budget["committed_nanousd"],
                "current_main_committed_nanousd": current_main,
                "current_audit_committed_nanousd": audit_budget["committed_nanousd"],
                "exact_admission_cap_enforced": True, "main_cap_nanousd": PARAMETERS["non_audit_cap_nanousd"],
                "audit_cap_nanousd": PARAMETERS["audit_cap_nanousd"], "total_cap_nanousd": CAP,
                "unknown_holds_included_in_current_commitment": True}
            passed = (len(judgments) >= 6 and same == len(judgments) and false_merge == 0
                      and seeds["failed_packets"] == 0 and card_fraction >= .9
                      and card_reference["passed"] and bool(assignment_pairs) and reference_clarity
                      and self.hold_lineage()["new_unresolved_holds"] == 0)
            self.phase(session, "pilot_v5_gate", {"passed": passed, "reference_pairs": len(judgments), "reference_same": same,
                "execution_amendment": self.amendment["_record_id"], **self.hold_lineage(),
                "reference_clear_false_merges": false_merge, "card_usable_fraction": card_fraction,
                "assignment_articles": len(assigned["decisions"]), "proposed_assignments": len(applied),
                "assignment_reference_pairs": len(assignment_pairs),
                "positive_challenge_articles": len(challenge["held_out"]),
                "positive_challenge_evaluated": sum(i in assigned["decisions"] for i in challenge["held_out"]),
                "positive_challenge_proposals": sum(i in applied for i in challenge["held_out"]),
                "natural_query_articles": len(natural),
                "natural_query_evaluated": sum(i in assigned["decisions"] for i in natural),
                "natural_query_proposals": sum(i in applied for i in natural),
                "reference_all_articles_clear": reference_clarity,
                "card_reference_selected": card_reference["selected"],
                "card_reference_supported": card_reference["supported"],
                "card_reference_passed": card_reference["passed"],
                "card_reference_all_selected_supported": card_reference["selected"] == card_reference["supported"],
                "cost_forecast": forecast,
                "limitation": "Small functional/model-reference gate, not a statistically established precision or recall claim."})
            self.phase(session, "pilot_v5_outcome", {"groups": final_groups, "applied": applied, "conflicts": conflicts})
            return
        # Preserve provisional single-source dossiers and use them as additional recovery references.
        assigned_ids = {i for g in final_groups.values() for i in g}
        residual = [i for i in remaining if i not in assigned_ids and assigned["unresolved"].get(i) != "focal_event_not_clear"]
        provisional = {digest(["singleton", i]): [i] for i in residual}
        singleton_cards = self.make_cards(session, provisional, "full_v5_singleton")
        # Freeze each reference; a card never silently inherits new member evidence.
        updated = self.make_cards(session, final_groups, "full_v5_updated_seed")
        updated_accepted, updated_provisional, updated_rejected = quality_partition(final_groups, updated)
        singleton_accepted, singleton_provisional, singleton_rejected = quality_partition(provisional, singleton_cards)
        recovery_groups = {**updated_accepted, **singleton_accepted}
        recovery_cards = {**updated["usable"], **singleton_cards["usable"]}
        recovery_ids = sorted(i for group in recovery_groups.values() for i in group)
        recovery = self.assignments(session, index, recovery_ids, recovery_groups, recovery_cards, "full_v5_recovery", recovery=True)
        final_groups, recovery_applied, recovery_conflicts = commit_group_proposals(recovery_groups, recovery["proposals"])
        final_cards = self.make_cards(session, final_groups, "full_v5_final")
        final_accepted, final_provisional, final_rejected = quality_partition(final_groups, final_cards)
        provisional_groups = {**seed_provisional, **updated_provisional, **singleton_provisional, **final_provisional}
        final_groups = {**provisional_groups, **final_accepted}
        rejected_groups = {**seed_rejected, **updated_rejected, **singleton_rejected, **final_rejected}
        accepted_pairs = set()
        for group in final_accepted.values():
            if len(group) > 1:
                for identifier in group[1:]:
                    accepted_pairs.add(tuple(sorted((group[0], identifier))))
        selected_positive = sorted(accepted_pairs, key=lambda p: digest(["final-positive", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        membership = {i: d for d, group in final_accepted.items() for i in group}
        potential_misses = []
        for pair in index.manifest()["pairs"]:
            left, right = pair["left"], pair["right"]
            if left not in membership or right not in membership or membership[left] != membership[right]:
                potential_misses.append((left, right))
        selected_negative = sorted(set(potential_misses), key=lambda p: digest(["final-nonjoined-candidate", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        provisional_ids = {i for group in provisional_groups.values() for i in group}

        def endpoint_state(identifier):
            return ("quarantined" if identifier in self.amendment["quarantined_document_ids"] else
                    "card_supported_group" if identifier in membership else
                    "provisional_card_incomplete" if identifier in provisional_ids else "unresolved")

        outcome = self.phase(session, "full_v5_processing_outcome", {"groups": final_groups, "cards": final_cards,
            "group_states": {d: "provisional_card_incomplete" for d in provisional_groups},
            "card_supported_group_ids": sorted(final_accepted), "unresolved_groups": rejected_groups,
            "initial_assignments": applied, "recovery_assignments": recovery_applied,
            "conflicts": {**conflicts, **recovery_conflicts}, "unclear": sorted(unclear),
            "reference_selection": {"full_v5_retained_memberships": selected_positive,
                                    "full_v5_nonjoined_candidates": selected_negative},
            "nonjoined_audit_frame": {"candidate_pool": len(set(potential_misses)),
                "retrieval_pairs": len(index.manifest()["pairs"]), "selection_count": len(selected_negative),
                "rule": "All retrieved pairs not coassigned to the same card-supported group, including unresolved/provisional/quarantined endpoints.",
                "selection_statuses": [{"left": a, "right": b, "left_state": endpoint_state(a),
                                        "right_state": endpoint_state(b)} for a, b in selected_negative],
                "changes_membership": False},
            "unembedded": vectors["missing"], "human_validated": False,
            "accepted_as_scientific_findings": False, "all_potential_matches_guaranteed": False})
        # Both fixed strata are retained before the first final reference request.
        for label, pairs in outcome["reference_selection"].items():
            self.reference_plan(session, pairs, label)
        for label, pairs in outcome["reference_selection"].items():
            self.reference(session, pairs, label)
        self.phase(session, "full_v5_outcome", outcome)

    def final_audit_status(self, session, outcome):
        strata = {}
        pending = {v["task_key"] for v in self.ledger.unresolved.values()}
        for label, selected in (outcome or {}).get("reference_selection", {}).items():
            plan = self.phase(session, label + "_reference_plan")
            items = plan["items"] if plan else [{"task_key": None, "reason": "plan_not_constructed"} for _ in selected]
            states, labels = Counter(), Counter()
            for item in items:
                row = self.results.get(item["task_key"])
                if item["task_key"] in pending or (row and row["hold"]):
                    states["unknown"] += 1
                    continue
                if not row:
                    states["not_attempted"] += 1
                    continue
                parsed = self.ledger.artifacts.read(row["parsed"]) if row["parsed"] else None
                answer = next((a for a in (parsed or {}).get("answers", {}).values() if a.get("kind") == "pair"), None)
                states["available" if answer else "invalid"] += 1
                if answer:
                    labels[answer["label"]] += 1
            strata[label] = {"target": PARAMETERS["final_reference_pairs_per_stratum"], "selected": len(selected),
                "attempted": len(selected) - states["not_attempted"], "available": states["available"],
                "reused_prior_references": sum(item.get("reused_prior_reference", False) for item in items),
                "reference_packet_methods": dict(Counter(item.get("packet_method", "unavailable") for item in items)),
                "unavailable": len(selected) - states["available"], "invalid": states["invalid"],
                "unknown": states["unknown"], "not_attempted": states["not_attempted"], "labels": dict(labels),
                "processing_finished": self.phase(session, label + "_reference") is not None}
        total = {key: sum(s[key] for s in strata.values()) for key in
                 ("selected", "attempted", "available", "unavailable", "invalid", "unknown", "not_attempted")}
        target = 2 * PARAMETERS["final_reference_pairs_per_stratum"]
        return {"target": target, **total, "strata": strata, "selection_frozen": len(strata) == 2,
            "reused_prior_references": sum(s["reused_prior_references"] for s in strata.values()),
            "processing_finished": len(strata) == 2 and all(s["processing_finished"] for s in strata.values()),
            "complete": len(strata) == 2 and total["selected"] == target and total["available"] == target,
            "human_validated": False, "replacement_allowed": False}

    def report(self, session):
        completed = self.phase(session, "full_v5_outcome")
        outcome = completed or self.phase(session, "full_v5_processing_outcome")
        audit_completion = self.final_audit_status(session, outcome)
        gate = self.phase(session, "pilot_v5_gate")
        covered, memberships = {}, []
        if outcome:
            for dossier, group in outcome["groups"].items():
                for identifier in group:
                    if identifier in covered:
                        raise AuditError("dossier_multiple_membership")
                    covered[identifier] = dossier
            for article in self.articles:
                dossier = covered.get(article["document_id"])
                memberships.append({**article, "dossier_id": dossier,
                    "state": (outcome.get("group_states", {}).get(dossier) or
                              ("provisional_single_source" if len(outcome["groups"][dossier]) == 1 else "model_supported_group")) if dossier else "unresolved",
                    "human_validated": False})
        counts = Counter(r["phase"] for r in self.results.values())
        reference_card = {}
        for name in self.phases:
            if name.endswith("_reference"):
                value = self.phase(session, name)
                tally = Counter((item["reference"] or {}).get("label", "unavailable") for item in value["items"])
                reference_card[name] = {"selected": len(value["items"]), "counts": dict(tally),
                    "interpretation": ("Blinded model-reference card focus and coverage judgments; not human gold or a population sample."
                        if name == "pilot_v5_card_quality_reference" else
                        "Historical model-reference summary quality judgments; not human gold."
                        if "summary_quality_reference" in name else
                        "Model-reference pair judgments; not independent event samples or population accuracy.")}
        report = {"plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "legacy_budget_at_amendment": self.amendment["legacy_budget"], **self.hold_lineage(),
            "at": utc(), "articles": len(self.articles), "distinct_inputs": len(self.documents),
            "responses_by_phase": dict(counts), "stored_responses": len(self.results),
            **accounting(list(self.results.values()), self.ledger.unresolved), "budget_usd": 50,
            "pilot_gate": gate, "pipeline_finished": completed is not None,
            "pilot_card_reference": self.card_reference_status(session),
            "pilot_full_bundle_control": self.phase(session, "pilot_v5_full_bundle_control"),
            "quarantined_articles": len(self.amendment["quarantined_document_ids"]),
            "quarantined_groups": len(self.amendment["quarantined_group_ids"]),
            "pipeline_processing_complete": outcome is not None,
            "final_audit_completion": audit_completion, "final_audit_complete": audit_completion["complete"],
            "four_processes_complete": bool(outcome and len(outcome["cards"]["usable"]) == len(outcome["groups"]) and len(covered) == len(self.documents)),
            "groups": len(outcome["groups"]) if outcome else None,
            "multi_article_groups": sum(len(v) > 1 for v in outcome["groups"].values()) if outcome else None,
            "unique_inputs_grouped": len(covered), "unresolved_inputs": len(self.documents) - len(covered),
            "groups_with_usable_card": len(outcome["cards"]["usable"]) if outcome else None,
            "provisional_card_incomplete_groups": len(outcome.get("group_states", {})) if outcome else None,
            "quality_rejected_or_unavailable_groups": len(outcome.get("unresolved_groups", {})) if outcome else None,
            "quality_rejected_or_unavailable_articles": len({i for group in outcome.get("unresolved_groups", {}).values()
                                                           for i in group["document_ids"]}) if outcome else None,
            "nonjoined_audit_candidate_pool": outcome.get("nonjoined_audit_frame", {}).get("candidate_pool") if outcome else None,
            "nonjoined_audit_selected_endpoint_status_counts": dict(Counter(
                status for row in outcome.get("nonjoined_audit_frame", {}).get("selection_statuses", [])
                for status in (row["left_state"], row["right_state"]))) if outcome else None,
            "article_routes": dict(Counter(r["state"] for r in memberships)),
            "memberships_artifact": self.ledger.artifacts.put(memberships) if outcome else None,
            "reference_records": {k: v["_record_id"] for k, v in self.phases.items() if k.endswith("_reference")},
            "reference_card": reference_card,
            "limitations": "Model-supported exploratory dossiers; screening precision, exhaustive event recall and human validity are unestablished. No text published.",
            "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results)]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identifier, **report}, indent=2), encoding="utf-8")
        return {"id": identifier, **report}


def clear(answer, label):
    if not answer or answer.get("status", "valid") != "valid" or answer.get("label") != label:
        return False
    probabilities = answer.get("probabilities") or {}
    probability = probabilities.get(label, answer.get("confidence"))
    return type(probability) in (float, int) and math.isfinite(probability) and PARAMETERS["positive_confidence"] <= probability <= 1


def commit_group_proposals(groups, proposals):
    """Every source member must support one frozen target; no moving-target chains."""
    moves, conflicts = {}, {}
    for source, members in groups.items():
        targets = {proposals[i]["dossier_id"] for i in members if i in proposals}
        if len(targets) == 1 and all(i in proposals for i in members):
            target = next(iter(targets))
            if target in groups and target != source:
                moves[source] = target
        elif targets:
            conflicts[source] = "not_all_members_support_same_target"
    result, applied, handled = {d: list(m) for d, m in groups.items()}, {}, set()
    for source, target in sorted(moves.items()):
        if source in handled:
            continue
        if target in moves:
            if moves[target] == source:
                chosen, removed = sorted((source, target))
                result[chosen] = sorted(groups[source] + groups[target])
                result.pop(removed, None)
                applied[source] = {"target": chosen, "rule": "all_members_reciprocal_group_support"}
                handled.update((source, target))
            else:
                conflicts[source] = "moving_reference_chain_or_cycle"
        else:
            result[target].extend(groups[source])
            result.pop(source, None)
            applied[source] = {"target": target, "rule": "all_members_static_reference_support"}
            handled.add(source)
    return {d: sorted(set(m)) for d, m in result.items()}, applied, conflicts


def commit_proposals(groups, proposals):
    """No chain closure: static targets, explicit mutual singleton pairs only."""
    result = {d: list(members) for d, members in groups.items()}
    owner = {i: d for d, members in groups.items() for i in members}
    applied, conflicts = {}, {}
    handled = set()
    for identifier, proposal in sorted(proposals.items()):
        if identifier in handled:
            continue
        target = proposal["dossier_id"]
        source = owner.get(identifier)
        if target not in groups or target == source or (source and len(groups[source]) != 1):
            conflicts[identifier] = "invalid_target_or_already_grouped"
            continue
        target_moves = [i for i in groups[target] if i in proposals]
        if target_moves:
            if (len(groups[target]) == 1 and len(target_moves) == 1 and source
                    and proposals[target_moves[0]]["dossier_id"] == source):
                other = target_moves[0]
                chosen = min(source, target)
                removed = max(source, target)
                result[chosen] = sorted([identifier, other])
                result.pop(removed, None)
                applied[identifier] = {**proposal, "dossier_id": chosen, "rule": "reciprocal_singleton_pair"}
                handled.update((identifier, other))
            else:
                conflicts[identifier] = "moving_reference_chain_or_cycle"
            continue
        if source:
            result.pop(source, None)
        result[target].append(identifier)
        applied[identifier] = {**proposal, "rule": "immutable_reference_wave"}
        handled.add(identifier)
    return {d: sorted(set(m)) for d, m in result.items()}, applied, conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "pilot", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=preparation.OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action in {"amend", "report"}))
    try:
        result = study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Execute separately authorized USD50 four-process Cybercrime NL dossier experiment",
            actor="codex:cybercrime-dossiers")
        print(json.dumps(result), flush=True)
    finally:
        study.close()


if __name__ == "__main__":
    main()

