"""Synthetic saved-job drain: real runtime and ledger, no external API/owner."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import audited_handler

import test_execute_luna_budget_batch as submit_fixture
import test_poll_luna_budget_batch as poll_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import drain_luna_budget_recovery as drain
finally:
    sys.path.pop(0)


def stop_fields():
    ack = {"plan": "plan", "authorization_id": drain.STUDY, "phase_continuation_ref": "phase",
        "original_run": "first-run", "original_finish": "first-finish", "deadline_epoch": 100,
        "queue_token_cap": 20_000_000, "count_workers": 16}
    run = {**ack, "ack_ref": "ack", "protocol": "protocol"}
    stop = {"plan": "plan", "run": "run", "protocol": "protocol", "finished_reason": "technical_stop",
        "budget_state": "budget", "deadline_epoch": 100, "queue_token_cap": 20_000_000,
        "submitted": 16, "assessments": 8, "pending_requests": 8, "pending_jobs": 1}
    finish = {"plan": "plan", "run": "run", "reason": "technical_stop", "ack_ref": "ack",
        "budget_state": "budget", "original_finish": "first-finish"}
    return stop, run, finish, ack


def test_exact_stop_binding_is_read_only_and_keeps_expired_deadline():
    fields = stop_fields()
    prior = deepcopy(fields)
    stop, run, finish, ack = fields
    drain.validate_stop_binding("plan", stop, "run", run, finish, "ack", ack, "phase")
    assert fields == prior


@pytest.mark.parametrize("which,key,value", [
    (0, "plan", "other"), (0, "run", "other"), (0, "protocol", "other"),
    (0, "finished_reason", None), (0, "budget_state", "other"), (0, "pending_requests", 7),
    (0, "submitted", True), (1, "ack_ref", "other"), (1, "phase_continuation_ref", "other"),
    (1, "original_run", "other"), (1, "count_workers", 17), (1, "deadline_epoch", 101),
    (2, "reason", "complete"), (2, "original_finish", "other"), (3, "plan", "other")])
def test_changed_binding_is_blocked(which, key, value):
    fields = stop_fields()
    fields[which][key] = value
    stop, run, finish, ack = fields
    with pytest.raises(AuditError):
        drain.validate_stop_binding("plan", stop, "run", run, finish, "ack", ack, "phase")


@pytest.mark.parametrize("http_request,body", [
    ({"method": "POST", "path": "/v1/batches"}, b"{}"),
    ({"method": "POST", "path": "/v1/files"}, b"data"),
    ({"method": "POST", "path": "/v1/responses/input_tokens"}, b"{}"),
    ({"method": "GET", "path": "/v1/batches/batch_other"}, None),
    ({"method": "GET", "path": "/v1/batches"}, None),
    ({"method": "GET", "path": "/v1/files/file-1/content?extra=1"}, None),
    ({"method": "GET", "path": "/v1/batches/batch_existing"}, b""),
    ({"method": "GET", "path": "/v1/batches/batch_existing", "query": {}}, None)])
def test_gate_rejects_all_dispatch_or_unrelated_calls_before_gateway(http_request, body):
    engine = object.__new__(drain.DrainResearch)
    engine.drain_phase, engine.drain_job_ids = "reconcile", {"batch_existing"}
    with pytest.raises(AuditError, match="only_existing_job"):
        engine.action("session", "plan", "policy", "key", http_request, body)


def test_diagnostic_phase_forbids_even_get():
    engine = object.__new__(drain.DrainResearch)
    engine.drain_phase, engine.drain_job_ids = "diagnostic", {"batch_existing"}
    with pytest.raises(AuditError, match="only_existing_job"):
        engine.action("session", "plan", "policy", "key", {"method": "GET", "path": "/v1/batches/batch_existing"})


class Seeder(submit_fixture.FixtureResearch):
    @audited_handler
    def _status(self, session, context, data):
        result = super()._status(session, context, data)
        if data["phase"] == "fixture":
            plan = self.ledger.get(result["plan"], drain.PLAN_KIND)
            plan["corpora"] = {corpus: {"summary": {"eligible_requests": 8}}
                               for corpus in ("incident-reports", "cybercrime")}
            return {"plan": self.ledger.record(session, drain.PLAN_KIND, "synthetic-drain-plan", plan)}
        return result


def prepared(tmp_path, monkeypatch, mode="valid"):
    project = tmp_path / "project"
    project.mkdir()
    transport = poll_fixture.ResultTransport(mode)
    seeder = Seeder(tmp_path / "owner", project=project, config=Config(offline=False), transport=transport)
    plan = submit_fixture.execute(seeder, "fixture")["plan"]
    submit_fixture.execute(seeder, "submit", plan)
    seeder.close()
    engine = drain.DrainResearch(tmp_path / "owner", project=project, config=Config(offline=False), transport=transport)
    # The full stop proof has pure closed-binding tests above. Isolate historical
    # approval replay so this test exercises real GET intents, bytes, settlement,
    # original reconciliation and retained diagnostics in one runtime session.
    monkeypatch.setattr(engine, "bind_stop", lambda session, data: {
        "stop_result_ref": "synthetic-stop", "recovery_run": "synthetic-run", "recovery_finish": "synthetic-finish",
        "prior_ack_ref": "synthetic-ack", "phase_continuation_ref": "synthetic-phase", "submitted_at_stop": 16,
        "budget_state_at_stop": "synthetic-old-budget", "previously_acknowledged_assessment_ids": [],
        "original_stop_unchanged": True})
    return engine, transport, plan


def execute(engine, plan, **extra):
    return engine.execute("status", {"plan": plan, "stop_result_ref": "synthetic-stop", "prior_ack_ref": "synthetic-ack",
        "phase_continuation_ref": "synthetic-phase", "allow_existing_job_reads": True, "max_wait_seconds": 0, **extra},
        objective="Synthetic existing-job drain and retained diagnostic", actor="test:software")


def test_one_audited_session_drains_settles_reports_and_replays_without_http(tmp_path, monkeypatch):
    engine, transport, plan = prepared(tmp_path, monkeypatch)
    calls = len(transport.calls)
    try:
        result = execute(engine, plan)
        assert result["pending_jobs"] == 0 and result["drain_obstacles"] == []
        assert result["reserved_usd"] == 0 and result["charged_estimate_usd"] > 0
        assert result["new_models"] == result["new_projections"] == 0
        assert result["new_inference_authorized"] is False and engine.config.offline is False
        assert sum(row["assessed"] for row in result["corpora"].values()) == 16
        assert sum(row["projection_uncovered"] for row in result["corpora"].values()) == 16
        assert len(transport.calls) == calls + 4
        assert all(call[0]["method"] == "GET" for call in transport.calls[calls:])
        assert engine.ledger.get(result["id"], "luna_budget_progress_report")["technical_rows"] == []
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
        # All phases are ledger records inside the same completed execute.
        assert len(result["reconciliation_passes"]) == 1
        repeated = execute(engine, plan)
        assert repeated["budget_state"] == result["budget_state"]
        assert repeated["corpora"] == result["corpora"]
        assert len(transport.calls) == calls + 4
    finally:
        engine.close()


@pytest.mark.parametrize("mode,expected_assessed,expected_pending", [("pending", 0, 2), ("wrong_identity", 0, 2), ("usage_missing", 16, 0)])
def test_pending_and_failed_rows_remain_explicit_without_retry(tmp_path, monkeypatch, mode, expected_assessed, expected_pending):
    engine, transport, plan = prepared(tmp_path, monkeypatch, mode)
    calls = len(transport.calls)
    try:
        result = execute(engine, plan)
        assert result["pending_jobs"] == expected_pending
        assert sum(row["assessed"] for row in result["corpora"].values()) == expected_assessed
        assert result["reserved_usd"] > 0
        if mode == "wrong_identity":
            assert len(transport.calls) == calls + 1
            assert result["drain_obstacles"][0]["reason"] == "batch_poll_identity_mismatch"
        elif mode == "pending":
            assert result["drain_timed_out"] is True
            assert len(transport.calls) == calls + 2
        else:
            assert len(result["technical_rows"]) == 1
            row = result["technical_rows"][0]
            assert row["current_cost_status"] == "unknown"
            assert row["retained_provider_metadata"]["model"] == "gpt-6-luna"
            assert result["newly_unacknowledged_technical_assessment_ids"] == [row["id"]]
            assert row["id"] in result["markdown"]
    finally:
        engine.close()


def test_stop_binding_failure_prevents_any_get(tmp_path, monkeypatch):
    engine, transport, plan = prepared(tmp_path, monkeypatch)
    calls = len(transport.calls)
    def rejected(*args):
        raise AuditError("fictional_invalid_stop")
    monkeypatch.setattr(engine, "bind_stop", rejected)
    try:
        with pytest.raises(AuditError, match="invalid_stop"):
            execute(engine, plan)
        assert len(transport.calls) == calls
    finally:
        engine.close()


def test_changed_submitted_scope_prevents_any_get(tmp_path, monkeypatch):
    engine, transport, plan = prepared(tmp_path, monkeypatch)
    original = engine.bind_stop
    monkeypatch.setattr(engine, "bind_stop", lambda *args: {**original(*args), "submitted_at_stop": 17})
    calls = len(transport.calls)
    try:
        with pytest.raises(AuditError, match="submitted_job_scope_changed"):
            execute(engine, plan)
        assert len(transport.calls) == calls
    finally:
        engine.close()
