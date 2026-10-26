"""Focused technical-projection checks; no production owner or network."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_diagnosis as diag


def fixture():
    queue = {"_record_id": "q", "name": "round-1/qa/members", "plan": diag.PLAN,
        "implementation": {}, "category": "repair", "deadline": "2026-10-24T21:23:19+00:00",
        "budget_ceiling_nanousd": 1000, "packets_artifact": "packets", "unavailable": {"x": "full_union_capacity"}}
    packets, responses, artifacts = [], [], {}
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT,payload TEXT)")
    for i in range(4):
        packet = {"task_key": str(i), "request": {"synthetic": i}, "request_sha256": digest({"synthetic": i}),
            "role": "group_membership", "kind": "decisions"}
        packets.append(packet)
        if i == 3:
            continue
        intent = {"batch": diag.PLAN, "attempt": str(i), "task_key": str(i), "queue": "q", "packet": digest(packet),
            "started_at": "2026-10-24T21:23:18+00:00", "reserved_nanousd": 10}
        db.execute("INSERT INTO events(kind,payload) VALUES(?,?)", ("model.attempt.intended", json.dumps(intent)))
        row = {"_record_id": str(i), "task_key": str(i), "attempt": str(i), "plan": diag.PLAN,
            "response": "response" + str(i), "parsed": "parsed" + str(i) if i < 2 else None,
            "usable": i < 2, "hold": i == 2, "members_supported": i == 0, "group_supported": False,
            "fatal": "model_or_dispatch_integrity" if i == 2 else None, "cost_nanousd": None if i == 2 else 2,
            "observations": []}
        responses.append(row)
    artifacts.update(packets=packets, parsed1={"answers": {
        "c": {"kind": "clarity", "status": "valid", "label": "clear_single_event", "probability": .84},
        "m": {"kind": "membership", "status": "valid", "label": "different_event", "probability": .92}}},
        response2={"model": None, "payload": None, "raw_response": {"http_status": 200, "failure_stage": "read",
            "failure_code": "transport_timeout", "response_text": "NEVER RETURN THIS SOURCE TEXT"}})
    class Reader:
        def rows(self, kind):
            return {diag.run.QUEUE: [queue], diag.run.RESPONSE: responses, diag.run.CHECKPOINT: []}[kind]
        def artifact(self, ref):
            return artifacts[ref]
        def release(self, ref):
            pass
    reader = Reader()
    reader.db = db
    report = {"attempted_requests": 3, "returned_requests": 3, "queued_requests": 4,
        "response_health": {"stop_reason": "model_or_dispatch_integrity"}, "changes": 1,
        "analysis": {"unique_pair_outcomes": {"unknown": 3}}}
    return reader, {"implementation": {}}, report


def test_funnel_separates_semantic_failure_technical_hold_and_unattempted():
    reader, plan, report = fixture()
    result = diag.inspect(reader, plan, report)
    q = result["queues"][0]
    assert q["counts"] == {"queued": 4, "attempted": 3, "returned": 3, "usable": 2, "hold": 1,
        "members_supported": 1, "group_supported": 0, "technical_unusable": 1, "unattempted": 1}
    assert q["unsupported_group_reasons_overlapping"] == {"clarity:positive_below_085": 1, "membership:label:different_event": 1}
    assert q["unavailable_reasons"] == {"full_union_capacity": 1}
    assert result["technical_cases"][0]["failure_stage"] == "read"
    assert "NEVER RETURN" not in json.dumps(result)


def test_report_count_mismatch_fails_closed():
    reader, plan, report = fixture()
    report["attempted_requests"] = 4
    with pytest.raises(AuditError, match="report_counts"):
        diag.inspect(reader, plan, report)


def test_duplicate_attempt_is_not_accepted():
    reader, plan, report = fixture()
    first = reader.db.execute("SELECT payload FROM events LIMIT 1").fetchone()[0]
    reader.db.execute("INSERT INTO events(kind,payload) VALUES(?,?)", ("model.attempt.intended", first))
    with pytest.raises(AuditError, match="attempt_binding"):
        diag.inspect(reader, plan, report)


def test_exact_threshold_and_safe_fields():
    assert diag.answer_failures({"answers": {"a": {"kind": "clarity", "label": "clear_single_event", "status": "valid", "probability": .85}}}) == {}
    assert diag.safe_code("possibly private prose with spaces") is None
    assert diag.safe_code("read_timeout") == "read_timeout"


@pytest.mark.parametrize("field,value", [("plan", "wrong"), ("method", "wrong")])
def test_report_binding_guard(field, value):
    report = {"plan": diag.PLAN, "method": diag.run.METHOD}
    diag.bound_report({"method": diag.run.METHOD}, report)
    report[field] = value
    with pytest.raises(AuditError, match="report_method_plan"):
        diag.bound_report({"method": diag.run.METHOD}, report)
