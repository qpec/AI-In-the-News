"""Source-free timeout recognition and prospective quarantine integrity."""
import copy
from types import SimpleNamespace

import pytest

from newsresearch import luna_timeout_quarantine as quarantine
from newsresearch.common import AuditError, Context, digest
from test_luna_validation_gateway import MemoryLedger


def timeout_raw():
    return {"failure": "codex_timeout_unknown_outcome", "unknown_outcome": True,
        "exit_code": None, "timeout_seconds": 180, "stdout": "Constructed incomplete output",
        "stderr": "", "transport_status": "invalid_or_unknown"}


def unknown(ledger, number, sources):
    attempt = "constructed-attempt-" + str(number)
    request = ledger.put({"synthetic": True, "articles": [{"source_version": source} for source in sources]})
    response = ledger.put({"payload": None, "raw_response": timeout_raw()})
    assessment_value = {"status": "unknown", "request": request, "response": response, "answer": None}
    assessment = ledger.record("test", "luna_lead_assessment", attempt, assessment_value)
    history = {"attempt": attempt, "luna_validation_study": "constructed-study", "request": request,
        "source_versions": sources, "article_exposures": len(sources)}
    outcome = {**assessment_value, "attempt": attempt, "assessment": assessment,
        "error": "codex_timeout_unknown_outcome"}
    return history, outcome


@pytest.mark.parametrize("fault", [None, "unrecognized", "retention", "answer", "exit_code", "changed_timeout"])
def test_only_exact_retained_local_timeout_is_recognized(tmp_path, fault):
    ledger = MemoryLedger(tmp_path)
    _, outcome = unknown(ledger, 1, [digest("source-a")])
    assessment = copy.deepcopy(ledger.get(outcome["assessment"], "luna_lead_assessment"))
    response = copy.deepcopy(ledger.read(outcome["response"]))
    configured = 180
    if fault == "unrecognized":
        response["raw_response"]["failure"] = "provider_exception_with_unobserved_outcome"
    elif fault == "retention":
        response["raw_response"]["output_retention"] = "prohibited"
    elif fault == "answer":
        assessment["answer"] = {"invented": True}
    elif fault == "exit_code":
        response["raw_response"]["exit_code"] = 0
    elif fault == "changed_timeout":
        configured = 181
    assert quarantine.recognize_timeout(outcome, assessment, response,
        timeout_seconds=configured) is (fault is None)


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(quarantine, "require_active", lambda *args: None)
    ledger = MemoryLedger(tmp_path)
    control = ledger.record("test", "protocol", "constructed-control", {"method": "constructed-opt-in-only"})
    return SimpleNamespace(ledger=ledger), Context("Source-free timeout policy verification", "test", {}), control


def apply(engine, context, control, history, outcomes, tasks, **extra):
    return quarantine.apply_quarantine(engine, "test", context, control_id=control,
        study_key="constructed-study", plan_id=digest("frozen-plan"), config={"timeout_seconds": 180},
        history=history, outcomes=outcomes, tasks=tasks, **extra)


def test_complete_overlap_exclusions_precede_completion_event_and_inputs_are_immutable(tmp_path, monkeypatch):
    engine, context, control = fixture(tmp_path, monkeypatch)
    a, b, c = [digest(name) for name in ("source-a", "source-b", "source-c")]
    intended, outcome = unknown(engine.ledger, 1, [a, b])
    tasks = [{"logical_id": "overlap-a", "source_versions": [a, c], "request_ref": digest("request-a")},
        {"logical_id": "overlap-b", "source_versions": [b], "request_ref": digest("request-b")},
        {"logical_id": "disjoint", "source_versions": [c], "request_ref": digest("request-c")}]
    before = copy.deepcopy(([intended], {"old": outcome}, tasks))
    result = apply(engine, context, control, [intended], {"old": outcome}, tasks)
    assert result["safe"] and not result["health_stop"] and result["observed_timeout_count"] == 1
    assert result["source_versions"] == sorted([a, b])
    assert {item["logical_id"] for item in result["excluded_tasks"]} == {"overlap-a", "overlap-b"}
    assert len(result["exclusions"]) == 2
    for identifier in result["exclusions"]:
        excluded = engine.ledger.get(identifier, "luna_timeout_execution_exclusion")
        assert excluded["answer"] is None and excluded["replacement"] is False and excluded["retry"] is False
    event = engine.ledger.db.execute("SELECT payload FROM events WHERE kind='luna.timeout.quarantine.applied'").fetchone()
    assert event is not None  # Both exclusion records already exist when this event is saved.
    assert ([intended], {"old": outcome}, tasks) == before


def test_observed_health_threshold_and_authorized_inflight_outcomes_are_distinct(tmp_path, monkeypatch):
    engine, context, control = fixture(tmp_path, monkeypatch)
    pairs = [unknown(engine.ledger, n, [digest("source-" + str(n))]) for n in range(4)]
    history = [pair[0] for pair in pairs]
    outcomes = {str(n): pair[1] for n, pair in enumerate(pairs[:3])}
    result = apply(engine, context, control, history, outcomes, [],
        in_flight_attempt_ids={pairs[3][0]["attempt"]})
    assert result["safe"] and result["health_stop"] and result["observed_timeout_count"] == 3
    outcomes["3"] = pairs[3][1]
    result = apply(engine, context, control, history, outcomes, [])
    assert result["safe"] and result["health_stop"] and result["observed_timeout_count"] == 4
    assert len(result["cause_attempt_ids"]) == 4


def test_unrecognized_unknown_missing_outcome_and_failed_audit_remain_fail_closed(tmp_path, monkeypatch):
    engine, context, control = fixture(tmp_path, monkeypatch)
    intended, outcome = unknown(engine.ledger, 1, [digest("source-a")])
    assert not apply(engine, context, control, [intended], {}, [])["safe"]
    bad_response = engine.ledger.put({"payload": None,
        "raw_response": {**timeout_raw(), "failure": "unrecognized_provider_failure"}})
    assessment = engine.ledger.record("test", "luna_lead_assessment", "bad", {
        "status": "unknown", "request": intended["request"], "response": bad_response, "answer": None})
    unexplained = {**outcome, "response": bad_response, "assessment": assessment}
    assert not apply(engine, context, control, [intended], {"old": unexplained}, [])["safe"]
    monkeypatch.setattr(engine.ledger, "record", lambda *args: (_ for _ in ()).throw(AuditError("constructed audit failure")))
    with pytest.raises(AuditError, match="constructed audit failure"):
        apply(engine, context, control, [intended], {"old": outcome}, [])
