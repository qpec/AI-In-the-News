"""Synthetic policy quarantine and safe scheduled recovery, with no network."""
import hashlib
import json
import sqlite3
from dataclasses import asdict

import pytest

import test_luna_standard_finish_v2 as previous_fixture
import luna_standard_finish_v2 as previous
import check_luna_standard_finish_v2 as previous_checker
import luna_standard_finish_v3 as module
import check_luna_standard_finish_v3 as checker
import luna_policy_quarantine as quarantine
from newsresearch.common import AuditError

execute = previous_fixture.fixture.fixture.fixture.execute
POLICY = {"error": {"code": "invalid_prompt", "type": "invalid_request_error", "param": None,
    "message": "Invalid prompt: your prompt was flagged as potentially violating our usage policy."}}


def policy_receipt():
    raw = module.canonical(POLICY).encode()
    return module.api.http.BatchReceipt(raw, 400, request_id="req-synthetic-policy",
        headers={"x-request-id": "req-synthetic-policy"}, error_type="http_error",
        unknown=False, body_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("change", [None, "status", "unknown", "retention", "hash", "code", "type", "param", "message", "duplicate"])
def test_classifier_only_accepts_complete_terminal_policy_receipt(change):
    receipt = asdict(policy_receipt())
    raw = receipt.pop("body")
    if change == "status":
        receipt["status"] = 429
    elif change == "unknown":
        receipt["unknown"] = True
    elif change == "retention":
        receipt["retention_error"] = "failed"
    elif change == "hash":
        receipt["body_sha256"] = "0" * 64
    elif change in ("code", "type", "param", "message"):
        value = json.loads(raw)
        value["error"][change] = "different"
        raw = module.canonical(value).encode()
        receipt["body_sha256"] = hashlib.sha256(raw).hexdigest()
    elif change == "duplicate":
        raw = b'{"error":{},"error":' + module.canonical(POLICY["error"]).encode() + b'}'
        receipt["body_sha256"] = hashlib.sha256(raw).hexdigest()
    assert quarantine.is_policy_rejection(receipt, raw) is (change is None)


def setup(tmp_path, monkeypatch):
    original_prepare = previous_fixture.fixture.fixture.prepare
    monkeypatch.setattr(previous_fixture.fixture.fixture, "prepare",
        lambda path, patch: original_prepare(path, patch, record_count=9))
    plan, old_amendment, fake = previous_fixture.setup(tmp_path, monkeypatch)
    fake.terminal = True
    original_perform = fake.perform
    mode = {"value": "success"}

    def perform(request, body, identifier):
        result = original_perform(request, body, identifier)
        if request == module.api.ROUTE and mode["value"] == "policy":
            return policy_receipt()
        return result

    monkeypatch.setattr(fake, "perform", perform)
    clock = previous_fixture.fixture.Clock()
    parent = previous.FinishResearch(tmp_path / "finish", transport=fake, clock=clock)
    try:
        run = {"phase": "run", "plan": plan["id"], "amendment": old_amendment["id"]}
        collected = execute(parent, {**run, "collect_only": True})
        assert collected["pending_jobs"] == 0
        mode["value"] = "policy"
        stopped = execute(parent, {**run, "test_stop_after": 1})
        assert stopped["standard_saved"] == 1 and stopped["reason"] == "standard_result_requires_review"
    finally:
        parent.close()
    (tmp_path / "finish/STOP").write_text("Explicitly authorized error-handling child")
    integrity = previous_checker.BatchIntegrity(tmp_path / "v2-check")
    try:
        assert execute(integrity, {"source_owner": str(tmp_path / "finish"), "plan": plan["id"]})["integrity_passed"]
    finally:
        integrity.close()
    migration = module.FinishMigration(tmp_path / "v3-migration")
    try:
        execute(migration, {"source_owner": str(tmp_path / "finish"), "destination": str(tmp_path / "finish-v3"),
            "plan": plan["id"], "integrity_report": str(tmp_path / "v2-check/latest-integrity.json"),
            "user_instruction": module.AUTHORIZATION, "latest_steering": module.STEERING})
    finally:
        migration.close()
    amendment = json.loads((tmp_path / "finish-v3/finish-plan.json").read_text())
    return plan, amendment, fake, mode, clock


def test_policy_quarantine_continues_restart_keeps_costs_then_unclassified_error_blocks(tmp_path, monkeypatch):
    plan, amendment, fake, mode, clock = setup(tmp_path, monkeypatch)
    sealed = (tmp_path / "finish/state.sqlite3").read_bytes()
    assert len(amendment["inherited_policy_rejections"]) == 1
    assert amendment["deadline_epoch"] == plan["deadline_epoch"]
    counts = fake.calls.count(module.batch.COUNT_ROUTE)
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"], "test_stop_after": 1}
    engine = module.FinishResearch(tmp_path / "finish-v3", transport=fake, clock=clock)
    try:
        clock.value = 100
        second = execute(engine, run)
        assert second["reason"] == "test_bounded_stop" and second["policy_quarantined"] == 2
        assert second["standard_saved"] == 2 and second["unknown_cost_holds"] == 3
        assert not engine.gateway.stopped
        mode["value"] = "success"
        clock.value = 200
        third = execute(engine, run)
        assert third["standard_saved"] == 3 and third["policy_quarantined"] == 2
        assert third["standard_worker_ceiling"] == 64
        assert third["standard_control"]["tpm"] == 1_000_000
        assert third["standard_control"]["rpm"] == 4000
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "v3-check")
    try:
        report = execute(integrity, {"source_owner": str(tmp_path / "finish-v3"), "plan": plan["id"]})
        assert report["integrity_passed"] and report["policy_quarantined"] == 2
        # Synthetic plan clocks have expired relative to wall time; collection's
        # common gate remains open and admission must still honor that deadline.
        assert report["recovery_gates"]["collect_allowed"]
        assert report["recovery_gates"]["common_blockers"] == []
    finally:
        integrity.close()
    with sqlite3.connect(tmp_path / "finish-v3/state.sqlite3") as db:
        saved_policies = [json.loads(r[0]) for r in db.execute("SELECT payload FROM finish_policy_quarantine")]
        for value in saved_policies:
            cost = json.loads(db.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (value["custom_id"],)).fetchone()[0])
            assert cost["status"] == "unknown" and cost["reserved_nanousd"] > 0
            assert cost["charged_nanousd"] == 0 and module.digest(cost) == value["cost_sha256"]
    fake.failure = "429"
    clock.value = 300
    engine = module.FinishResearch(tmp_path / "finish-v3", transport=fake, clock=clock)
    try:
        fourth = execute(engine, run)
        assert fourth["reason"] == "standard_result_requires_review"
        attempts = len(fake.standard_ids)
        with pytest.raises(AuditError, match="new_failed_gateway_action_no_retry"):
            execute(engine, run)
        assert len(fake.standard_ids) == attempts == 4
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "v3-check")
    try:
        report = execute(integrity, {"source_owner": str(tmp_path / "finish-v3"), "plan": plan["id"]})
        assert report["integrity_passed"] and not report["recovery_gates"]["collect_allowed"]
        assert "unclassified_or_changed_cost_hold" in report["recovery_gates"]["common_blockers"]
    finally:
        integrity.close()
    assert fake.calls.count(module.batch.COUNT_ROUTE) == counts
    assert sealed == (tmp_path / "finish/state.sqlite3").read_bytes()
    assert (tmp_path / "finish/STOP").exists()
    # Tampering with a saved quarantine fails replay, even if counts are unchanged.
    with sqlite3.connect(tmp_path / "finish-v3/state.sqlite3") as db:
        value = saved_policies[0]
        value["cost_sha256"] = "0" * 64
        db.execute("UPDATE finish_policy_quarantine SET payload=? WHERE custom_id=?",
            (module.canonical(value), value["custom_id"]))
    integrity = checker.BatchIntegrity(tmp_path / "v3-check")
    try:
        with pytest.raises(AuditError, match="quarantine_projection_changed"):
            execute(integrity, {"source_owner": str(tmp_path / "finish-v3"), "plan": plan["id"]})
    finally:
        integrity.close()


def test_stop_remains_absolute_for_error_handling_child(tmp_path, monkeypatch):
    plan, amendment, fake, mode, clock = setup(tmp_path, monkeypatch)
    owner = tmp_path / "finish-v3"
    (owner / "STOP").write_text("User stopped")
    engine = module.FinishResearch(owner, transport=fake, clock=clock)
    count = len(fake.standard_ids)
    try:
        with pytest.raises(module.state.StateError, match="user_stop"):
            execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert len(fake.standard_ids) == count
        assert (owner / "STOP").read_text() == "User stopped"
    finally:
        engine.close()
