"""A later chain drain reuses the frozen GET-only mechanics, even after expiry."""
from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import drain_luna_budget_recovery_chain as drain
finally:
    sys.path.pop(0)

import test_luna_budget_failure_chain as fixture


def history(reason="technical_stop"):
    prior = {**fixture.prior_value(), "id": "prior", "prior_ack_ref": "root-ack", "deadline_epoch": 1,
             "stopped_run": "parent-run", "stopped_finish": "parent-finish", "stop_result_ref": "parent-stop"}
    records, protocol = fixture.history_values(prior)
    records.update(prior_kind=drain.chain.ACK_KIND, run_kind=drain.chain.RUN_KIND)
    records["run"]["implementation"] = drain.chain.implementation_hashes()
    parent_fields = {key: prior[key] for key in ("prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref")}
    records["run"].update(parent_fields)
    protocol.update(parent_fields)
    records["finish"].update({key: prior[key] for key in ("prior_ack_ref", "stopped_finish")})
    records["stop"]["finished_reason"] = records["finish"]["reason"] = reason
    records["finish"]["blockers"] = [] if reason == "deadline" else ["prior_technical_or_unknown_assessment"]
    protocol.update(method=drain.chain.RECOVERY_METHOD, implementation=drain.chain.implementation_hashes())
    return prior, records, protocol


@pytest.mark.parametrize("reason", ["technical_stop", "deadline"])
@pytest.mark.parametrize("target,field", [
    (target, field) for target in ("run", "protocol")
    for field in ("prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref")
] + [("finish", "prior_ack_ref"), ("finish", "stopped_finish")])
def test_every_immediate_parent_reference_remains_bound(reason, target, field):
    prior, records, protocol = history(reason)
    item = protocol if target == "protocol" else records[target]
    item[field] = "different-parent-history"
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: {"content": protocol}),
                             latest=lambda *args: ("run", records["run"]))
    with pytest.raises(AuditError, match="immediate_parent_history"):
        drain.chain.check_stopped_history(engine, "p", prior, records, allow_deadline_drain=True)


@pytest.mark.parametrize("reason", ["technical_stop", "deadline"])
def test_expired_chain_stop_allows_only_bound_retained_get_drain(monkeypatch, reason):
    prior, records, protocol = history(reason)
    engine = object.__new__(drain.ChainedDrainResearch)
    engine.chain_binding_protocol = "new-binding-protocol"
    engine.ledger = SimpleNamespace(get=lambda *args: {"content": protocol})
    engine.latest = lambda *args: ("run", records["run"])
    calls = []
    monkeypatch.setattr(drain.chain, "load_chain_ack", lambda *args: calls.append("verified_chain") or prior)
    monkeypatch.setattr(drain.chain, "stopped_records", lambda *args: records)
    monkeypatch.setattr(drain, "load_continuation", lambda *args: {"deadline_epoch": 1, "assessment": "phase-assessment"})
    value = engine.bind_stop("session", {"plan": "p", "prior_ack_ref": "prior", "stop_result_ref": "stop"})
    assert calls == ["verified_chain"] and value["recovery_run"] == "run"
    assert value["chain_binding_protocol"] == "new-binding-protocol"
    assert value["previously_acknowledged_assessment_ids"] == sorted(prior["assessment_ids"] + ["phase-assessment"])
    assert records["stop"]["finished_reason"] == records["finish"]["reason"] == reason
    if reason == "deadline":
        # The read exception cannot be used to acknowledge a deadline as an
        # extraction error or open another admission period.
        with pytest.raises(AuditError):
            drain.chain.check_stopped_history(engine, "p", prior, records)


@pytest.mark.parametrize("change", ["ack", "deadline", "budget", "run", "reason", "blocker"])
def test_read_only_deadline_exception_does_not_relax_history_bindings(change):
    prior, records, protocol = history("deadline")
    if change == "ack":
        records["run"]["ack_ref"] = "other"
    elif change == "deadline":
        records["run"]["deadline_epoch"] += 1
    elif change == "budget":
        records["stop"]["budget_state"] = "other"
    elif change == "run":
        records["finish"]["run"] = "other"
    elif change == "reason":
        records["finish"]["reason"] = "technical_stop"
    else:
        records["finish"]["blockers"] = ["unknown_cost"]
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: {"content": protocol}), latest=lambda *args: ("run", records["run"]))
    with pytest.raises(AuditError):
        drain.chain.check_stopped_history(engine, "p", prior, records, allow_deadline_drain=True)


@pytest.mark.parametrize("action_request", [
    {"method": "POST", "path": "/v1/responses/input_tokens"},
    {"method": "POST", "path": "/v1/files"},
    {"method": "POST", "path": "/v1/batches"},
    {"method": "GET", "path": "/v1/batches/foreign"},
])
def test_chain_drain_inherits_closed_network_gate(action_request):
    engine = object.__new__(drain.ChainedDrainResearch)
    engine.drain_phase = "reconcile"
    engine.drain_job_ids = {"known"}
    with pytest.raises(AuditError, match="only_existing_job"):
        engine.action("session", "plan", "policy", "key", action_request)


def test_network_policy_reconciliation_and_reporting_are_frozen_inherited_methods():
    for name in ("action", "existing_policy", "reconcile", "retained_report"):
        assert getattr(drain.ChainedDrainResearch, name) is getattr(drain.frozen.DrainResearch, name)
