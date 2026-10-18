"""Finite chained acknowledgments; synthetic stores and fake provider only."""
from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.event_batch_budget import InputTokenReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_failure_chain as chain
    import run_luna_budget_recovery_chain as runner
finally:
    sys.path.pop(0)

import test_luna_budget_failure_ack as fixture


@pytest.mark.parametrize("values", [None, [], ["a" * 64] * 2, ["x"], [1], [["a"]]])
def test_explicit_nonempty_distinct_finite_ids_required(values):
    with pytest.raises(AuditError, match="explicit_distinct"):
        chain.finite_ids(values)


def prior_value(plan="p"):
    return {"plan": plan, "authorization_id": chain.STUDY, "original_run": "root-run", "original_finish": "root-finish",
        "phase_continuation_ref": "phase", "deadline_epoch": 9_999_999_999,
        "queue_token_cap": 20_000_000, "count_workers": 16, "assessment_ids": ["a" * 64, "b" * 64],
        "failures": [{"assessment": value, "custom_id": value, "manifest": value, "attempt": value,
                      "request": value, "response": value, "errors": ["response:not_completed"]}
                     for value in ("a" * 64, "b" * 64)]}


def test_chain_appends_exact_ids_preserves_prior_and_rejects_overlap():
    prior = prior_value()
    before = deepcopy(prior)
    new = [{"assessment": "c" * 64}]
    merged = chain.merge_failures(prior, ["c" * 64], new)
    assert [item["assessment"] for item in merged] == ["a" * 64, "b" * 64, "c" * 64]
    assert prior == before
    with pytest.raises(AuditError, match="disjoint"):
        chain.merge_failures(prior, ["a" * 64], [{"assessment": "a" * 64}])
    with pytest.raises(AuditError, match="disjoint"):
        chain.merge_failures(prior, ["c" * 64], [{"assessment": "d" * 64}])


def history_values(prior):
    run = {"plan": prior["plan"], "authorization_id": chain.STUDY, "ack_ref": prior["id"], "protocol": "protocol",
           "implementation": chain.base.implementation_hashes(), **{key: prior[key] for key in chain.INHERITED}}
    finish = {"plan": prior["plan"], "run": "run", "reason": "technical_stop", "ack_ref": prior["id"],
              "original_finish": prior["original_finish"], "budget_state": "old-budget",
              "blockers": ["prior_technical_or_unknown_assessment"]}
    stop = {"plan": prior["plan"], "run": "run", "protocol": "protocol", "finished_reason": "technical_stop",
            "budget_state": "old-budget", "deadline_epoch": prior["deadline_epoch"], "queue_token_cap": prior["queue_token_cap"],
            "submitted": 4, "assessments": 2, "pending_requests": 2, "pending_jobs": 1}
    protocol = {"method": chain.recovery.METHOD, **run}
    return {"prior_kind": chain.base.ACK_KIND, "run_kind": chain.recovery.RUN_KIND, "run_id": "run",
            "finish_id": "finish", "run": run, "finish": finish, "stop": stop}, protocol


@pytest.mark.parametrize("mutation", [None, "ack", "deadline", "stop", "blocker", "namespace", "implementation"])
def test_stop_proof_requires_exact_parent_finish_deadline_and_code(mutation):
    prior = {**prior_value(), "id": "prior"}
    records, protocol = history_values(prior)
    latest = ("run", records["run"])
    if mutation == "ack":
        records["run"]["ack_ref"] = "other"
    elif mutation == "deadline":
        records["run"]["deadline_epoch"] += 1
    elif mutation == "stop":
        records["stop"]["budget_state"] = "different"
    elif mutation == "blocker":
        records["finish"]["blockers"].append("unknown_cost")
    elif mutation == "namespace":
        latest = ("different-run", {})
    elif mutation == "implementation":
        records["run"]["implementation"] = {}
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: {"content": protocol}), latest=lambda *args: latest)
    if mutation:
        with pytest.raises(AuditError):
            chain.check_stopped_history(engine, "p", prior, records)
    else:
        chain.check_stopped_history(engine, "p", prior, records)


def diagnostic_values(prior, ids, state="state"):
    value = {"stop_result_ref": "stop", "stopped_run": "run", "stopped_finish": "finish", "prior_ack_ref": prior["id"],
             "budget_state_at_ack": state, "new_assessment_ids": ids}
    diagnostic = {"plan": prior["plan"], "protocol": "diagnostic-protocol", "budget_state": state, "budget_frozen": False,
        "pending_jobs": 0, "reserved_usd": 0, "drain_obstacles": [], "drain_timed_out": False,
        "stop_result_ref": "stop", "recovery_run": "run", "recovery_finish": "finish", "prior_ack_ref": prior["id"],
        "phase_continuation_ref": prior["phase_continuation_ref"],
        "previously_acknowledged_assessment_ids": sorted(prior["assessment_ids"] + ["phase-assessment"]),
        "newly_unacknowledged_technical_assessment_ids": ids}
    protocol = {**diagnostic, "method": chain.drain.METHOD + ":retained-diagnostic", "implementation": chain.drain.implementation_hashes()}
    return value, diagnostic, protocol


@pytest.mark.parametrize("field,value", [("pending_jobs", 1), ("reserved_usd", 1), ("budget_frozen", True),
    ("drain_obstacles", ["error"]), ("drain_timed_out", True), ("stop_result_ref", "different"),
    ("budget_state", "different"), ("newly_unacknowledged_technical_assessment_ids", []),
    ("previously_acknowledged_assessment_ids", [])])
def test_pending_unknown_stale_or_incomplete_diagnostic_cannot_create_ack(field, value):
    prior = {**prior_value(), "id": "prior"}
    binding, diagnostic, protocol = diagnostic_values(prior, ["c" * 64])
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: {"content": protocol}))
    chain.check_diagnostic(engine, "p", diagnostic, binding, prior, {"assessment": "phase-assessment"})
    diagnostic[field] = value
    with pytest.raises(AuditError, match="exact_drained"):
        chain.check_diagnostic(engine, "p", diagnostic, binding, prior, {"assessment": "phase-assessment"})


def test_new_loop_is_identical_to_frozen_recovery_except_its_obstacle_record_kind():
    def loop(path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = next(item for item in ast.walk(tree) if isinstance(item, ast.While))
        for item in ast.walk(node):
            if isinstance(item, ast.Constant) and item.value == "luna_budget_chained_recovery_obstacle":
                item.value = "luna_budget_failure_recovery_obstacle"
        return ast.dump(node, include_attributes=False)
    assert loop(chain.ROOT / "scripts/run_luna_budget_recovery.py") == loop(chain.ROOT / "scripts/run_luna_budget_recovery_chain.py")
    assert runner.ChainedRecoveryResearch.dispatch is chain.base.fast.FastResearch.dispatch
    assert runner.ChainedRecoveryResearch.stage is chain.base.fast.FastResearch.stage
    kwargs = dict(startup_pending=True, pending=True, staged=True, unmanifested=True, pressure=None, poll_due=True)
    assert runner.cycle_operation(startup_observed=False, **kwargs) == "reconcile"
    assert runner.cycle_operation(startup_observed=True, **kwargs) == "submit"


def test_cumulative_gate_still_stops_on_any_new_or_changed_error():
    prior = prior_value()
    proofs = chain.merge_failures(prior, ["c" * 64], [{**prior["failures"][0], "assessment": "c" * 64}])
    ack = {**prior, "failures": proofs}
    rows = [{"id": proof["assessment"], "plan": "p", "status": "error", "technical_failure": True,
             **{key: proof[key] for key in ("custom_id", "manifest", "attempt", "request", "response", "errors")}} for proof in proofs]
    blockers = ["prior_technical_or_unknown_assessment", "unrelated_blocker"]
    assert chain.recovery.recovery_gate(blockers, rows, {}, ack) == ["unrelated_blocker"]
    assert chain.recovery.recovery_gate(blockers, rows + [{**rows[0], "id": "d" * 64}], {}, ack) == blockers
    rows[0]["response"] = "changed"
    assert chain.recovery.recovery_gate(blockers, rows, {}, ack) == blockers


class ChainHarness(fixture.VerifyHarness):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("load_after_deadline"):
            return chain.load_chain_ack(self, session, data["plan"], data["ack_ref"])
        if not data.get("chain"):
            return super()._status(session, context, data)
        plan_id = data["plan"]
        book, state = chain.base.known_budget(self, session, plan_id)
        rows = chain.base._rows(self, session, chain.base.ASSESSMENT_KIND, plan_id)
        ids = sorted(row["id"] for row in rows if row["status"] == "error")
        proofs = [chain.base.verify_failure(self, session, plan_id, value, book) for value in ids]
        prior = prior_value(plan_id)
        prior_id = self.ledger.record(session, chain.base.ACK_KIND, "synthetic-prior", prior)
        self.synthetic_prior = {**prior, "id": prior_id}
        records, protocol = history_values(self.synthetic_prior)
        protocol_id = self._version(session, context, {"kind": "protocol", "key": "synthetic-recovery", "content": protocol})["id"]
        records["run"]["protocol"] = protocol_id
        run = self.ledger.record(session, chain.recovery.RUN_KIND, plan_id + ":" + prior_id + ":recovery-v1", records["run"])
        finish = self.ledger.record(session, chain.recovery.FINISH_KIND, run, {**records["finish"], "run": run})
        stop = self.ledger.record(session, "luna_budget_fast_status", "synthetic-stop", {**records["stop"], "run": run, "protocol": protocol_id})
        _, diagnostic, diagnostic_protocol = diagnostic_values(self.synthetic_prior, ids, state)
        diagnostic.update(stop_result_ref=stop, recovery_run=run, recovery_finish=finish,
            technical_rows=[{"id": proof["assessment"], "custom_id": proof["custom_id"], "errors": proof["errors"],
                             "current_cost_status": "settled", "retained_provider_metadata": {"receipt": proof["download_receipt"]}} for proof in proofs])
        diagnostic_protocol.update(stop_result_ref=stop, recovery_run=run, recovery_finish=finish)
        diagnostic["protocol"] = self._version(session, context, {"kind": "protocol", "key": "synthetic-diagnostic", "content": diagnostic_protocol})["id"]
        diagnostic_id = self.ledger.record(session, chain.base.DIAGNOSTIC_KIND, "synthetic-drained", diagnostic)
        arguments = {"plan": plan_id, "prior_ack_ref": prior_id, "stop_result_ref": stop,
                     "diagnostic_ref": diagnostic_id, "assessment_ids": ids}
        reference = runner.resolve_ack_reference(self, session, context, arguments)
        loaded = chain.load_chain_ack(self, session, plan_id, reference)
        # A later reservation must not cause a reset or require replaying the
        # now-historical diagnostic as though it described the current book.
        book.reserve(request_id="synthetic-future", task_id="synthetic-future", corpus_id="incident-reports", plan_id=plan_id,
            request_sha256="c" * 64, input_count=InputTokenReceipt(123, "gpt-6-luna", "c" * 64, "d" * 64, "provider_responses_input_tokens"),
            max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
        next_state = self.gateway.save_book(session, book, state)
        reused = runner.resolve_ack_reference(self, session, context, arguments)
        changed = {**arguments, "assessment_ids": ["f" * 64]}
        with pytest.raises(AuditError, match="existing_registration_inputs_changed"):
            runner.resolve_ack_reference(self, session, context, changed)
        return {"ack_ref": reference, "reused": reused, "prior": self.synthetic_prior, "stop": stop, "finish": finish,
                "ack": loaded, "state": state, "next_state": next_state,
                "errors_still_failed": [row["status"] for row in rows if row["id"] in ids]}


class DeadlineHarness(runner.ChainedRecoveryResearch):
    def report(self, session, plan_id, plan, view, book, state, *, reason=None):
        return {"markdown": "Synthetic controller report.", "finished_reason": reason, "pending_jobs": 0}


def test_actual_retained_failures_chain_in_one_session_and_resume_without_reset(tmp_path, monkeypatch):
    submitter, original, plan, _ = fixture.fast_fixture.fixture(tmp_path, monkeypatch)
    owner = submitter.ledger.root
    fixture.fast_fixture.execute(submitter, plan)
    submitter.close()
    transport = fixture.FailureTransport()
    transport.files, transport.jobs, transport.calls = original.files, original.jobs, original.calls
    phase = {"id": "phase", "assessment": "phase-assessment", "plan": plan["id"],
             "custom_id": "phase-custom", "deadline_epoch": 9_999_999_999}
    monkeypatch.setattr(fixture.poll_fixture.poll, "load_continuation", lambda *args, **kwargs: phase)
    monkeypatch.setattr(chain, "load_continuation", lambda *args, **kwargs: phase)
    monkeypatch.setattr(runner, "load_continuation", lambda *args, **kwargs: phase)
    # The frozen predecessor's own proof suite already verifies its two raw
    # failures. Isolate only that predecessor here; all NEW raw failure proofs,
    # cost/attempt checks, stop/diagnostic bindings and durable writes are real.
    monkeypatch.setattr(chain.base, "load_failure_ack", lambda engine, *args: engine.synthetic_prior)
    engine = ChainHarness(owner, config=Config(offline=False), transport=transport)
    try:
        engine.execute("status", {"plan": plan["id"], "continuation_ref": "phase", "allow_paid_execution": True},
            objective="Reconcile fictional completed jobs", actor="test:software")
        calls = len(transport.calls)
        result = engine.execute("status", {"plan": plan["id"], "chain": True},
            objective="Append fictional exact failures without retry or acceptance", actor="test:software")
        assert result["ack_ref"] == result["reused"]
        assert len(result["ack"]["failures"]) == 4 and len(result["ack"]["new_failures"]) == 2
        assert result["errors_still_failed"] == ["error", "error"]
        assert result["state"] != result["next_state"] and len(transport.calls) == calls
        assert engine.ledger.get(result["finish"], chain.recovery.FINISH_KIND)["reason"] == "technical_stop"
        monkeypatch.setattr(chain, "time", SimpleNamespace(time=lambda: 10_000_000_000))
        monkeypatch.setattr(chain.base, "time", SimpleNamespace(time=lambda: 10_000_000_000))
        late = engine.execute("status", {"plan": plan["id"], "ack_ref": result["ack_ref"], "load_after_deadline": True},
            objective="Verify retained proof loading after admission expiry", actor="test:software")
        assert late["id"] == result["ack_ref"] and len(transport.calls) == calls
    finally:
        engine.close()
    # New namespace reaches the original deadline without calling the provider;
    # exact restart reuses that finish and cannot acquire a new scheduling day.
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 10_000_000_000, sleep=lambda _: pytest.fail("no sleep")))
    controller = DeadlineHarness(owner, config=Config(offline=False), transport=transport)
    controller.synthetic_prior = result["prior"]
    try:
        data = {"plan": plan["id"], "ack_ref": result["ack_ref"], "allow_paid_execution": True}
        first = controller.execute("status", data, objective="Check original deadline in new synthetic namespace", actor="test:software")
        run = controller.fast_run
        again = controller.execute("status", data, objective="Check exact terminal synthetic restart", actor="test:software")
        assert first["finished_reason"] == again["finished_reason"] == "deadline"
        assert controller.fast_run == run and len(transport.calls) == calls
        assert controller.ledger.get(run, chain.RUN_KIND)["deadline_epoch"] == result["prior"]["deadline_epoch"]
        assert controller.ledger.get(result["finish"], chain.recovery.FINISH_KIND)["reason"] == "technical_stop"
    finally:
        controller.close()
