"""Cost-blocked diagnostics use fictional data and the real temporary runtime."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, PricePolicy, UsageReceipt
from newsresearch.runtime import audited_handler

import test_drain_luna_budget_recovery as prior

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import diagnose_luna_budget_costs as diagnostic
finally:
    sys.path.pop(0)


def book_with(status):
    policy = PricePolicy("gpt-6-luna", 100_000_000, 125_000_000, 500_000_000,
        (1, 2), (1, 1), (2, 1), (3, 2), 272_000, "https://example.test/prices", "2026-01-01T00:00:00Z")
    book = BudgetBook(policy, diagnostic.STUDY, operational_limit_nanousd=120_000_000_000)
    book.reserve(request_id="fictional", task_id="fictional", corpus_id="incident-reports", plan_id="plan",
        request_sha256="a" * 64, input_count=InputTokenReceipt(100, policy.model, "a" * 64, "b" * 64,
            "provider_responses_input_tokens"), max_output_tokens=512, price_fingerprint=policy.fingerprint)
    if status != "reserved":
        usage = None if status == "unknown" else UsageReceipt(100, 1000 if status == "overrun" else 12,
            "wrong-model" if status == "frozen" else policy.model, "a" * 64, "c" * 64, True)
        book.settle("fictional", usage)
    return book


@pytest.mark.parametrize("status", ["reserved", "settled", "unknown", "frozen", "overrun"])
def test_real_budget_classification_never_changes_accounting(status):
    book = book_with(status)
    before, entry = deepcopy(book.to_dict()), book.entry("fictional")
    value = diagnostic.budget_anomalies(book, "plan")
    assert book.to_dict() == before and book.entry("fictional") == entry
    assert value["entry_status_counts"] == {status: 1}
    blocked = status in {"unknown", "frozen", "overrun"}
    assert value["cost_admission_blocked"] is blocked
    assert value["anomalous_request_ids"] == (["fictional"] if blocked else [])
    if blocked:
        assert value["anomalous_entries"] == [entry]
        assert value["anomalous_entries"][0]["reason"]
    assert value["reserved_nanousd"] == book.reserved_nanousd


def test_other_plan_entries_cannot_be_reported_as_this_plan():
    with pytest.raises(AuditError, match="plan_mismatch"):
        diagnostic.budget_anomalies(book_with("unknown"), "other")


def retained_history():
    stop, run, finish, ack = prior.stop_fields()
    failures = []
    records = {}
    for index in range(2):
        identifier = str(index + 1) * 64
        row = {"plan": "plan", "custom_id": "old-" + str(index), "manifest": "old-manifest",
            "attempt": "old-attempt-" + str(index), "request": "request", "response": "response",
            "status": "error", "technical_failure": True, "errors": ["response:not_completed"]}
        records[identifier] = row
        failures.append({"assessment": identifier, **{key: row[key] for key in
            ("custom_id", "manifest", "attempt", "request", "response", "errors")}})
    ack.update(implementation=diagnostic.base.recovery_hashes(), assessment_ids=[p["assessment"] for p in failures],
        failures=failures, protocol="ack-protocol", diagnostic_ref="old-diagnostic")
    phase = {"plan": "plan", "authorization_id": diagnostic.STUDY,
        "implementation": diagnostic.phase_history.code_hashes(), "deadline_epoch": 100,
        "protocol": "phase-protocol", "original_run": "phase-run", "original_stop": "phase-stop",
        "proof": "phase-proof", "assessment": "3" * 64, "custom_id": "phase-custom",
        "phase_implementation_sha256": "phase-sha", "max_per_corpus": 250, "max_runtime_seconds": 1800}
    run["implementation"] = diagnostic.base.recovery_hashes()
    records.update({"stop": stop, "run": run, "finish": finish, "ack": ack, "phase": phase,
        "protocol": {"content": {"method": diagnostic.base.RECOVERY_METHOD, **run}},
        "ack-protocol": {"content": {"method": diagnostic.failure_history.METHOD, **ack}},
        "phase-protocol": {"content": {"method": "exact-settled-phase-error-continuation-v1", **phase}},
        "phase-run": {"plan": "plan", "deadline_epoch": 100, "max_per_corpus": 250, "max_runtime_seconds": 1800},
        "phase-stop": {"plan": "plan", "run": "phase-run", "reason": "technical_stop"},
        "first-run": {"plan": "plan", "authorization_id": diagnostic.STUDY, "continuation_ref": "phase",
            "deadline_epoch": 100, "implementation": diagnostic.failure_history.fast.implementation_hashes()},
        "first-finish": {"plan": "plan", "run": "first-run", "reason": "technical_stop"},
        "phase-proof": {"plan": "plan", "original_assessment": "3" * 64, "custom_id": "phase-custom",
            "derived_status": "valid", "phase_implementation_sha256": "phase-sha"},
        "3" * 64: {"plan": "plan", "status": "error", "errors": ["response:not_single_message"], "custom_id": "phase-custom"}})
    return records


def history_engine(records):
    engine = object.__new__(diagnostic.CostDiagnosticResearch)
    engine.cost_diagnostic_protocol = "diagnostic-protocol"
    engine.ledger = SimpleNamespace(get=lambda key, *args: deepcopy(records[key]), append=lambda *args: None,
        db=SimpleNamespace(execute=lambda *args: []))
    engine.latest = lambda kind, key: ("finish", records["finish"]) if kind == diagnostic.base.FINISH_KIND else ("run", records["run"])
    return engine


def history_data():
    return {"plan": "plan", "stop_result_ref": "stop", "prior_ack_ref": "ack", "phase_continuation_ref": "phase"}


def test_history_binding_never_invokes_admission_loaders(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("An admission prerequisite must never gate GET-only diagnostic scope")
    monkeypatch.setattr(diagnostic.failure_history, "load_failure_ack", forbidden)
    monkeypatch.setattr(diagnostic.phase_history, "load_continuation", forbidden)
    engine = history_engine(retained_history())
    value = engine.bind_stop("session", history_data())
    assert value["historical_acknowledgments_reused_for_identity_only"] is True
    assert value["inference_continuation_permitted"] is False
    assert value["previously_acknowledged_assessment_ids"] == ["1" * 64, "2" * 64, "3" * 64]


@pytest.mark.parametrize("reference,key,value", [
    ("run", "implementation", {}), ("ack", "implementation", {}), ("phase", "implementation", {}),
    ("first-run", "deadline_epoch", 101), ("phase-stop", "reason", "complete"),
    ("phase-proof", "derived_status", "invalid"), ("1" * 64, "errors", ["changed"]),
    ("stop", "budget_state", "changed")])
def test_changed_historical_binding_fails_closed(reference, key, value):
    records = retained_history()
    records[reference][key] = value
    with pytest.raises(AuditError):
        history_engine(records).bind_stop("session", history_data())


class Harness(diagnostic.CostDiagnosticResearch):
    @audited_handler
    def _status(self, session, context, data):
        if not data.get("seed_partial"):
            return super()._status(session, context, data)
        plan = self.ledger.get(data["plan"], diagnostic.base.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, data["plan"], plan)
        policy, _, _ = self.authorization(session, context, data["plan"], plan)
        jobs = self.rows(session, diagnostic.base.JOB_KIND, data["plan"])
        self.drain_phase, self.drain_job_ids = "reconcile", {job["job_id"] for job in jobs}
        self.reconcile(session, data["plan"], policy, jobs[0])
        book, _ = self.gateway.load_book(session, diagnostic.STUDY)
        return diagnostic.budget_anomalies(book, data["plan"])


def prepare_partial(tmp_path, monkeypatch, mode="usage_missing"):
    old, transport, plan = prior.prepared(tmp_path, monkeypatch, mode)
    owner, project = old.ledger.root, old.project
    old.close()
    engine = Harness(owner, project=project, config=Config(offline=False), transport=transport)
    seeded = engine.execute("status", {"plan": plan, "seed_partial": True},
        objective="Seed fictional existing unknown-cost result and pending job", actor="test:software")
    monkeypatch.setattr(engine, "bind_stop", lambda session, data: {
        "stop_result_ref": "synthetic-stop", "recovery_run": "synthetic-run", "recovery_finish": "synthetic-finish",
        "prior_ack_ref": "synthetic-ack", "phase_continuation_ref": "synthetic-phase", "submitted_at_stop": 16,
        "budget_state_at_stop": "synthetic-old-budget", "previously_acknowledged_assessment_ids": [],
        "original_stop_unchanged": True, "cost_diagnostic_extension_protocol": engine.cost_diagnostic_protocol,
        "historical_acknowledgments_reused_for_identity_only": True, "inference_continuation_permitted": False})
    return engine, transport, plan, seeded


@pytest.mark.parametrize("mode,expected_status", [("usage_missing", "unknown"), ("wrong_model", "frozen")])
def test_existing_cost_anomaly_survives_other_job_settlement_and_is_diagnosed(tmp_path, monkeypatch, mode, expected_status):
    engine, transport, plan, seeded = prepare_partial(tmp_path, monkeypatch, mode)
    calls = len(transport.calls)
    try:
        result = prior.execute(engine, plan)
        assert result["pending_jobs"] == 0 and result["drain_obstacles"] == []
        assert result["current_cost_admission_blocked"] is True
        assert result["inference_continuation_permitted"] is False
        assert result["cost_diagnostics"]["anomalous_entries"] == seeded["anomalous_entries"]
        anomaly = result["cost_anomaly_details"][0]
        assert anomaly["entry"]["status"] == expected_status
        if mode == "usage_missing":
            assert anomaly["retained_provider_usage"][0]["usage"] is None
        else:
            assert anomaly["retained_provider_usage"][0]["model"] == "fictional-wrong-model"
        assert anomaly["assessments"][0]["response"]
        assert result["reserved_usd"] > 0
        assert result["budget_frozen"] is (mode == "wrong_model")
        assert len(transport.calls) == calls + 2
        assert all(call[0]["method"] == "GET" for call in transport.calls[calls:])
        assert engine.config.offline is False
        assert engine.ledger.get(result["base_diagnostic_ref"], "luna_budget_progress_report")["technical_rows"] == result["technical_rows"]
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
        assert result["new_models"] == result["new_projections"] == 0
        assert expected_status in result["markdown"] and anomaly["custom_id"] in result["markdown"]
    finally:
        engine.close()


def test_gateway_stop_stays_blocking_and_retained_diagnostic_still_exists(tmp_path, monkeypatch):
    engine, transport, plan, seeded = prepare_partial(tmp_path, monkeypatch)
    engine.existing_gateway_stop_ids = ["synthetic-retained-stop"]
    calls = len(transport.calls)
    try:
        result = prior.execute(engine, plan)
        assert len(transport.calls) == calls
        assert result["pending_jobs"] == 1
        assert result["gateway_stop_ids"] == ["synthetic-retained-stop"]
        assert result["drain_obstacles"][0]["reason"] == "cost_diagnostic_gateway_stop_preserved_no_get"
        assert result["cost_diagnostics"]["anomalous_entries"] == seeded["anomalous_entries"]
        assert result["current_cost_admission_blocked"] is True
        assert result["inference_continuation_permitted"] is False
    finally:
        engine.close()
