"""Only the new executed-scope adapter; shared compact synthetic native owner."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_source_v2 as subject
import test_luna_snippet_source as previous_tests
from test_final_validation_inventory import bytes_snapshot

native = previous_tests.native


class Consumer(Research):
    imported = None

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": subject.METHOD,
            "content": {"method": subject.METHOD, "implementation": subject.implementation(),
                "plan": subject.PLAN, "report": subject.REPORT, "policy": subject.POLICY}})
        self.imported = subject.collect(self, session)
        return {"artifact": self.ledger.artifacts.put(self.imported)}


@pytest.fixture
def bound(native, monkeypatch):
    for key in ("OWNER", "PLAN", "REPORT", "FREEZE", "SUCCESSOR", "PRIOR_COMMITMENT"):
        monkeypatch.setattr(subject, key, getattr(subject.base, key))
    return native


def run_import(tmp_path):
    engine = Consumer(tmp_path / "v2-consumer", config=Config(offline=True))
    try:
        engine.execute("status", {}, objective="Synthetic finite attempted-packet import", actor="test")
        return engine.imported
    finally:
        engine.close()


def test_attempted_only_import_never_reads_oversized_bulk_queues(tmp_path, bound, monkeypatch):
    before = bytes_snapshot(bound["owner"])
    queue_lists, read_refs = set(), set()
    original = subject.Reader
    class Selected(original):
        def rows(self, kind):
            rows = super().rows(kind)
            if kind == subject.recall.QUEUE:
                queue_lists.update(r["packets_artifact"] for r in rows)
            return rows
        def artifact_size(self, reference):
            if reference in queue_lists:
                return subject.POLICY["maximum_selected_bytes"]+1
            return super().artifact_size(reference)
        def artifact_bytes(self, reference):
            assert reference not in queue_lists, "bulk queue packet body was opened"
            read_refs.add(reference)
            return super().artifact_bytes(reference)
    monkeypatch.setattr(subject, "Reader", Selected)
    monkeypatch.setattr(subject.recall.Recall, "census", lambda *a: pytest.fail("old full-queue census invoked"))
    imported = run_import(tmp_path)
    history = imported["history"]
    assert imported["source"] == bound["source"] and digest(imported["state"]) == subject.SUCCESSOR
    assert imported["prior_commitment_nanousd"] == bound["report"]["committed_including_prior_nanousd"]
    assert history["historical_unknown_holds"] == 2 and history["historical_response_health"]["stop_reason"]
    assert not history["active_stop_inherited"] and history["baseline"] == bound["source"]["prior_history"]
    assert history["prepared_only"] == [] and history["prepared_only_summary"]["enumerated"] is False
    assert history["prepared_only_summary"]["reported_unattempted_requests"] > 0
    assert digest(bound["untouched"]) not in history["membership_attempts"]
    assert all(history["membership_attempts"][digest(pair)]["blocked"] for pair in (bound["held"], bound["orphan"]))
    assert any(r["member_supported"] and r["card_supported"] and r["card"] and not r["blocked"]
        for r in history["membership_attempts"].values())
    assert len(history["physical_census"]["intended_events"]) == len(history["physical_attempts"]) == bound["report"]["attempted_requests"]
    assert len(history["physical_census"]["orphan_attempts"]) == 2
    assert history["physical_census"]["complete_physical_intent_partition"]
    assert not history["physical_census"]["bulk_queue_membership_independently_replayed"]
    assert queue_lists and not queue_lists.intersection(read_refs)
    assert all(not row["packet_list_read"] for row in history["queue_metadata"])
    assert before == bytes_snapshot(bound["owner"])


@pytest.mark.parametrize("case", ["queue_plan", "dispatch", "receipt", "assessment", "packet", "reported_total"])
def test_selected_physical_evidence_mismatch_is_fatal(tmp_path, bound, monkeypatch, case):
    original = subject.Reader
    class Changed(original):
        def _row(self, row):
            value = super()._row(row)
            if case == "queue_plan" and row["kind"] == subject.recall.QUEUE:
                return {**value, "plan": "f"*64}
            if case == "assessment" and row["kind"] == subject.recall.RESPONSE:
                return {**value, "cost_nanousd": (value["cost_nanousd"] or 0)+1}
            if case == "reported_total" and row["id"] == subject.REPORT:
                return {**value, "held_nanousd": value["held_nanousd"]+1}
            return value
        def artifact(self, reference):
            value = super().artifact(reference)
            if not isinstance(value, dict):
                return value
            if case == "packet" and value.get("role") == "group_membership" and "task_key" in value:
                return {**value, "task_key": "f"*64}
            if case == "receipt" and "raw_response" in value and "provider" in value:
                return {**value, "usage": {"input_tokens": 999999}}
            if case == "dispatch" and "wire_sha256" in value and "client_id" in value:
                return {**value, "wire_sha256": "f"*64}
            return value
    monkeypatch.setattr(subject, "Reader", Changed)
    with pytest.raises(AuditError):
        run_import(tmp_path)


def test_original_registered_source_and_one_gib_cap_unchanged():
    assert hashlib.sha256(Path(subject.base.__file__).read_bytes()).hexdigest() == "45a8aafc09d335d550748eda182319f818efe2ae111d6263df1f5ad49bf6bf65"
    assert subject.POLICY["maximum_selected_bytes"] == 1024**3
    assert subject.POLICY["bulk_queue_packet_artifacts_read"] is False
    assert subject.METHOD != subject.base.METHOD


def test_generic_no_retry_preserved_without_bulk_queue_scan(tmp_path, bound, monkeypatch):
    # Observe the independently derived finite partition, then deliberately
    # duplicate a logical intention through its selected packet. No queue scan.
    original = subject.Reader
    seen = []
    class Changed(original):
        def artifact(self, reference):
            value = super().artifact(reference)
            if isinstance(value, dict) and value.get("role") == "group_membership" and "task_key" in value:
                if not seen:
                    seen.append(deepcopy(value["logical_ids"]))
                else:
                    value = deepcopy(value)
                    value["logical_ids"] = seen[0]
            return value
    monkeypatch.setattr(subject, "Reader", Changed)
    with pytest.raises(AuditError, match="intent_binding|logical_retry"):
        run_import(tmp_path)


def test_no_unattempted_identity_absence_claim_from_queue_counts(bound):
    # A report is a count anchor, not a membership enumeration or no-retry proof.
    assert subject.POLICY["prepared_only_packet_inventory_verified"] is False
    assert subject.POLICY["global_history_complete"] is False
    assert bound["report"]["queued_requests"] > bound["report"]["attempted_requests"]


def test_receipt_without_assessment_keeps_observed_highwater(monkeypatch):
    # Isolate the new census arithmetic. The real fixture above separately
    # verifies the native producer/record authority used by this read facade.
    monkeypatch.setattr(subject.base, "keyed", lambda *a: None)
    monkeypatch.setattr(subject.base, "session_prefix", lambda *a: None)
    packet = subject.recall.contract.member_packet(previous_tests.source(), ["d000", "d001"], lambda _: 100)
    plan = {"_record_id": "p"*64, "_created_event": 1, "implementation": subject.recall.implementation()}
    queue = {"_record_id": "q"*64, "_artifact": "a"*64, "_created_event": 2, "plan": plan["_record_id"],
        "implementation": plan["implementation"], "name": "one", "category": "repair", "packets_artifact": "z"*64,
        "planned_reservation_nanousd": packet["reservation_nanousd"], "unavailable": {}}
    attempt = "synthetic-receipt-only"
    response = ProviderResponse(None, "synthetic", "gpt-6-luna", usage={"input_tokens": 1_000_000}, raw_response={"http_status": 200})
    derived, parsed = subject.recall.outcome(packet, response)
    assert parsed is None and derived["cost_nanousd"] > packet["reservation_nanousd"]
    artifacts = {}
    def save(value):
        reference = digest(value)
        artifacts[reference] = value
        return reference
    intended = {"method": subject.recall.METHOD, "attempt": attempt, "task_key": packet["task_key"], "number": 1,
        "batch": plan["_record_id"], "queue": queue["_record_id"], "category": "repair",
        "packet": save(packet), "request": save(packet["request"]),
        "dispatch": save(subject.recall.transport.Invocation(packet["request"], attempt).manifest()),
        "reserved_nanousd": packet["reservation_nanousd"]}
    receipt = {"attempt": attempt, "response": save(asdict(response))}
    health = subject.recall.prior.health_state({packet["task_key"]: intended}, {packet["task_key"]: {**derived, "usable": False}})
    report = {"_created_event": 5, "attempted_requests": 1, "returned_requests": 1, "settled_nanousd": 0,
        "held_nanousd": derived["cost_nanousd"], "unknown_holds": 1,
        "category_commitments_nanousd": {"repair": derived["cost_nanousd"]}, "response_health": health,
        "prior_audit_commitment_nanousd": subject.recall.PRIOR_COMMITMENT,
        "committed_including_prior_nanousd": subject.recall.PRIOR_COMMITMENT+derived["cost_nanousd"],
        "queued_requests": 1, "unattempted_requests": 0}
    monkeypatch.setattr(subject, "PRIOR_COMMITMENT", report["committed_including_prior_nanousd"])
    class Memory:
        db = None
        def rows(self, kind):
            return [queue] if kind == subject.recall.QUEUE else []
        def execute(self, sql):
            if "model.attempt.intended" in sql:
                return [{"seq": 3, "event_hash": "i"*64, "payload": json.dumps(intended)}]
            if "luna_recall.response.received" in sql:
                return [{"seq": 4, "event_hash": "r"*64, "payload": json.dumps(receipt)}]
            return []
        def artifact(self, ref):
            assert ref != queue["packets_artifact"]
            return deepcopy(artifacts[ref])
    reader = Memory()
    reader.db = reader
    census, _, evidence = subject.executed_census(reader, plan, report)
    assert census["held_nanousd"] == derived["cost_nanousd"] and census["settled_nanousd"] == 0
    assert census["responses"] == {} and census["unknown_holds"] == 1
    assert evidence["orphan_attempts"] == [attempt] and health["stop_reason"]
