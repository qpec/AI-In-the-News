"""Exact held liability: synthetic provider, real temporary audit store only."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, UsageReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_held_cost as held
    import run_luna_budget_held_cost as runner
finally:
    sys.path.pop(0)

import test_event_batch_budget as budget_fixture
import test_luna_budget_failure_ack as fixture
import test_luna_budget_failure_chain as chain_fixture


def held_book():
    book = BudgetBook(budget_fixture.price(model="gpt-6-luna"), held.STUDY, operational_limit_nanousd=120_000_000_000)
    book.reserve(**budget_fixture.arguments(book, "held", task_id="held", plan_id="p", max_output_tokens=4096,
        input_count=InputTokenReceipt(4015, "gpt-6-luna", "a" * 64, "b" * 64, "provider_responses_input_tokens")))
    book.settle("held", UsageReceipt(None, None, None, "a" * 64, "c" * 64, False, "request-400"))
    proof = {"custom_id": "held", "entry": book.entry("held"), "event_history": book.to_dict()["events"]}
    return book, {"price_fingerprint": book.price_policy.fingerprint}, proof


def test_exact_hold_is_not_released_and_counts_against_every_future_admission():
    book, plan, proof = held_book()
    assert book.reserved_nanousd == 1_402_432
    held.validate_book(book, "p", plan, proof)
    book.reserve(**budget_fixture.arguments(book, "untouched", plan_id="p"))
    held.validate_book(book, "p", plan, proof)
    assert book.entry("held") == proof["entry"]
    assert book.committed_nanousd == 1_402_432 + book.entry("untouched")["reserved_nanousd"]
    book.settle("untouched", budget_fixture.usage(model="gpt-6-luna"))
    held.validate_book(book, "p", plan, proof)
    assert BudgetBook.from_dict(book.to_dict()).entry("held") == proof["entry"]


@pytest.mark.parametrize("change", ["future_unknown", "future_wrong_model", "release", "settle", "hold", "history", "price"])
def test_no_future_unknown_or_hold_mutation_is_allowed(change):
    book, plan, proof = held_book()
    if change.startswith("future"):
        book.reserve(**budget_fixture.arguments(book, "future", plan_id="p"))
        book.settle("future", None if change == "future_unknown" else budget_fixture.usage(model="wrong"))
    elif change == "release":
        book.confirm_unprocessed("held", confirmation_sha256="d" * 64, provider_request_id="confirmation", confirmed_unprocessed=True)
    elif change == "settle":
        book.settle("held", UsageReceipt(4015, 0, "gpt-6-luna", "a" * 64, "d" * 64, True))
    elif change == "hold":
        proof["entry"]["reserved_nanousd"] -= 1
    elif change == "history":
        proof["event_history"] = proof["event_history"][:1]
    else:
        plan["price_fingerprint"] = "wrong"
    with pytest.raises(AuditError):
        held.validate_book(book, "p", plan, proof)


@pytest.mark.parametrize("change", [None, "http", "code", "type", "model", "usage", "output", "missing", "accepted", "status"])
def test_only_the_exact_terminal_rejection_shape_can_be_acknowledged(change):
    row = {"error": None, "response": {"status_code": 400, "request_id": "r",
        "body": {"error": {"code": "invalid_prompt", "type": "invalid_request_error"}}}}
    assessment = {"request_id": "r", "status": "error", "technical_failure": True, "missing": False,
                  "accepted": False, "human_validated": False, "model": None, "usage": None, "output": None}
    if change == "http":
        row["response"]["status_code"] = 500
    elif change in {"code", "type"}:
        row["response"]["body"]["error"][change] = "different"
    elif change in {"model", "usage", "output"}:
        row["response"]["body"][change] = "unexpected"
    elif change in {"missing", "accepted"}:
        assessment[change] = True
    elif change == "status":
        assessment["status"] = "valid"
    if change:
        with pytest.raises(AuditError, match="only_exact_terminal"):
            held.validate_terminal_rejection(row, assessment)
    else:
        before = deepcopy((row, assessment))
        held.validate_terminal_rejection(row, assessment)
        assert (row, assessment) == before


def test_ambiguous_duplicate_create_blocks_before_reading_any_source(monkeypatch):
    actions = [{"phase": "create", "reserved_request_ids": ["custom"]}] * 2
    monkeypatch.setattr(held.base, "_rows", lambda *args: actions if args[2] == held.base.ACTION_KIND else [])
    with pytest.raises(AuditError, match="exactly_one_paid_dispatch"):
        held.verify_dispatch(object(), "session", "plan", "manifest", {}, {"custom_id": "custom"}, "attempt", {}, {})


def test_paid_create_boundary_rechecks_actual_book_and_stops_new_unknown(monkeypatch):
    book, plan, proof = held_book()
    engine = object.__new__(runner.HeldCostRecoveryResearch)
    engine.failure_ack = {"held_failure": proof}
    engine.gateway = SimpleNamespace(load_book=lambda *args: (book, "state"))
    engine.ledger = SimpleNamespace(get=lambda *args: plan)
    called = []
    monkeypatch.setattr(held.base.ExecutionResearch, "action", lambda *args, **kwargs: called.append(args) or {"allowed": True})
    request = {"method": "POST", "path": "/v1/batches"}
    assert engine.action("s", "p", "policy", "create:new", request)["allowed"]
    assert book.entry("held") == proof["entry"]
    book.reserve(**budget_fixture.arguments(book, "new-error", plan_id="p"))
    book.settle("new-error", None)
    with pytest.raises(AuditError, match="new_or_changed_unknown"):
        engine.action("s", "p", "policy", "create:later", request)
    assert len(called) == 1


@pytest.mark.parametrize("mutation", [None, "missing_cost_blocker", "extra_blocker", "deadline", "protocol", "namespace"])
def test_actual_two_blocker_stop_remains_exact_without_normalization(mutation):
    prior = {**chain_fixture.prior_value(), "id": "prior"}
    records, protocol = chain_fixture.history_values(prior)
    records["finish"]["blockers"] = ["prior_technical_or_unknown_assessment", "shared_budget_unknown_or_unresolved_charge"]
    latest = ("run", records["run"])
    if mutation == "missing_cost_blocker":
        records["finish"]["blockers"].pop()
    elif mutation == "extra_blocker":
        records["finish"]["blockers"].append("shared_gateway_stopped")
    elif mutation == "deadline":
        records["run"]["deadline_epoch"] += 1
    elif mutation == "protocol":
        protocol["ack_ref"] = "different"
    elif mutation == "namespace":
        latest = ("different-run", {})
    original = deepcopy(records)
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: {"content": protocol}), latest=lambda *args: latest)
    if mutation:
        with pytest.raises(AuditError):
            held.check_held_stop(engine, "p", prior, records)
    else:
        held.check_held_stop(engine, "p", prior, records)
    assert records == original


class ErrorTransport(fixture.poll_fixture.ResultTransport):
    def result_bytes(self, job_id):
        rows = [json.loads(line) for line in super().result_bytes(job_id).splitlines()]
        if job_id == "batch_1":
            rows[0]["response"].update(status_code=400, body={"error": {
                "message": "Synthetic invalid prompt; no model or billing inferred.",
                "type": "invalid_request_error", "param": None, "code": "invalid_prompt"}})
        else:
            body = rows[0]["response"]["body"]
            body.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
            body["usage"].update(output_tokens=4096, total_tokens=4219)
        return b"".join(canonical(row).encode() + b"\n" for row in rows)


class HeldHarness(runner.HeldCostRecoveryResearch):
    @audited_handler
    def _status(self, session, context, data):
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, held.base.PLAN_KIND)
        if data.get("load"):
            return held.load_ack(self, session, plan_id, data["ack_ref"])
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        self.result_parser = held.base.parse_batch_results_phase_aware
        self.parser_mode = "explicit-final-answer-phase-v1"
        policy, _, _ = self.authorization(session, context, plan_id, plan)
        for job in held.base._rows(self, session, held.base.fast.JOB_KIND, plan_id):
            self.reconcile(session, plan_id, policy, job)
        book, state = self.gateway.load_book(session, held.STUDY)
        rows = held.base._rows(self, session, held.base.ASSESSMENT_KIND, plan_id)
        unknown = next(row for row in rows if row.get("cost_status") == "unknown")
        truncation = next(row for row in rows if row.get("errors") == ["response:not_completed"])
        if data.get("tamper_count_link"):
            link = next(row for row in held.base._rows(self, session, "luna_batch_count_consumer")
                        if row["custom_id"] == unknown["custom_id"])
            link["origin_action_id"] = "different-count-with-same-number"
            self.ledger.record(session, "luna_batch_count_consumer", "synthetic-bad-link", link)
        proof = held.verify_held_failure(self, session, plan_id, unknown["id"], book)
        held.base.verify_failure(self, session, plan_id, truncation["id"], book)
        if not data.get("register"):
            return {"held": proof, "settled": truncation["id"], "calls": len(self.transport.calls)}
        old_ids = []
        for index in range(2):
            value = {"plan": plan_id, "status": "error", "technical_failure": True, "custom_id": "old-" + str(index),
                "manifest": "old", "attempt": "old-" + str(index), "request": "old", "response": "old", "errors": ["response:not_completed"]}
            identifier = self.ledger.record(session, held.base.ASSESSMENT_KIND, value["custom_id"], value)
            old_ids.append({"assessment": identifier, **{key: value[key] for key in ("custom_id", "manifest", "attempt", "request", "response", "errors")}})
        phase_value = {"plan": plan_id, "status": "error", "technical_failure": True, "custom_id": "old-phase",
                       "errors": ["response:not_single_message"]}
        phase_assessment = self.ledger.record(session, held.base.ASSESSMENT_KIND, "old-phase", phase_value)
        prior = {**chain_fixture.prior_value(plan_id), "assessment_ids": sorted(item["assessment"] for item in old_ids),
                 "failures": old_ids}
        prior_ref = self.ledger.record(session, held.base.ACK_KIND, "synthetic-prior", prior)
        prior = {**prior, "id": prior_ref}
        phase = {**phase_value, "id": prior["phase_continuation_ref"], "assessment": phase_assessment,
                 "deadline_epoch": prior["deadline_epoch"]}
        self.synthetic_history = (prior, phase)
        records, protocol = chain_fixture.history_values(prior)
        records["finish"]["blockers"] = ["prior_technical_or_unknown_assessment", "shared_budget_unknown_or_unresolved_charge"]
        protocol_ref = self._version(session, context, {"kind": "protocol", "key": "synthetic-recovery", "content": protocol})["id"]
        records["run"]["protocol"] = protocol_ref
        run = self.ledger.record(session, held.chain.recovery.RUN_KIND, plan_id + ":" + prior_ref + ":recovery-v1", records["run"])
        finish = self.ledger.record(session, held.chain.recovery.FINISH_KIND, run, {**records["finish"], "run": run})
        stop = self.ledger.record(session, "luna_budget_fast_status", "synthetic-stop", {**records["stop"], "run": run, "protocol": protocol_ref})
        diagnostic = {"plan": plan_id, "budget_state": state, "pending_jobs": 0, "drain_obstacles": [],
            "drain_timed_out": False, "gateway_stop_ids": [], "budget_frozen": False, "reserved_usd": book.reserved_nanousd / 1e9,
            "stop_result_ref": stop, "recovery_run": run, "recovery_finish": finish, "prior_ack_ref": prior_ref,
            "phase_continuation_ref": phase["id"], "newly_unacknowledged_technical_assessment_ids": sorted([unknown["id"], truncation["id"]]),
            "previously_acknowledged_assessment_ids": sorted(prior["assessment_ids"] + [phase_assessment]),
            "cost_diagnostics": {"anomalous_entries": [proof["entry"]], "anomalous_event_history": proof["event_history"]}}
        diagnostic["protocol"] = self._version(session, context, {"kind": "protocol", "key": "synthetic-cost-diagnostic", "content": {
            **diagnostic, "method": held.diagnostic_method.METHOD, "implementation": held.diagnostic_method.implementation_hashes()}})["id"]
        diagnostic_ref = self.ledger.record(session, held.base.DIAGNOSTIC_KIND, "synthetic-cost-diagnostic", diagnostic)
        arguments = {"plan": plan_id, "prior_ack_ref": prior_ref, "stop_result_ref": stop, "diagnostic_ref": diagnostic_ref,
                     "held_assessment_id": unknown["id"], "settled_assessment_id": truncation["id"]}
        reference = runner.resolve_ack_reference(self, session, context, arguments)
        loaded = held.load_ack(self, session, plan_id, reference)
        self.failure_ack = loaded
        assert self.check_gate(session, plan_id, plan, self.view(session, plan_id), book, phase) == []
        future = self.view(session, plan_id)
        future["assessments"].append({"id": "future-error", "plan": plan_id, "custom_id": "future-error",
                                      "status": "error", "technical_failure": True})
        assert "prior_technical_or_unknown_assessment" in self.check_gate(session, plan_id, plan, future, book, phase)
        reused = runner.resolve_ack_reference(self, session, context, arguments)
        return {"ack_ref": reference, "reused": reused, "ack": loaded, "held": proof,
                "history": self.synthetic_history, "calls": len(self.transport.calls), "old_finish": finish}


class DeadlineHarness(runner.HeldCostRecoveryResearch):
    def report(self, session, plan_id, plan, view, book, state, *, reason=None):
        return {"markdown": "Synthetic deadline report.", "finished_reason": reason, "pending_jobs": 0}


def test_real_raw_http400_proof_and_audited_finite_registration_preserve_full_hold(tmp_path, monkeypatch):
    submitter, original, plan, _ = fixture.fast_fixture.fixture(tmp_path, monkeypatch)
    owner = submitter.ledger.root
    fixture.fast_fixture.execute(submitter, plan)
    submitter.close()
    transport = ErrorTransport()
    transport.files, transport.jobs, transport.calls = original.files, original.jobs, original.calls
    # Historical phase/settled-proof replay has its own 22 focused checks. This
    # integration isolates that dependency; all NEW dispatch/raw/count/cost
    # proofs, durable registration, real book and finite gate are exercised.
    monkeypatch.setattr(held, "verify_history", lambda engine, *args: engine.synthetic_history)
    engine = HeldHarness(owner, config=Config(offline=False), transport=transport)
    try:
        initial = engine.execute("status", {"plan": plan["id"]}, objective="Verify fictional terminal400 with full unknown hold", actor="test:software")
        calls = len(transport.calls)
        before = deepcopy(initial["held"]["entry"])
        result = engine.execute("status", {"plan": plan["id"], "register": True}, objective="Register exact fictional finite hold", actor="test:software")
        assert result["ack_ref"] == result["reused"] and len(transport.calls) == calls
        assert result["ack"]["held_failure"]["entry"] == before
        assert len(result["ack"]["failures"]) == 4
        monkeypatch.setattr(held, "time", SimpleNamespace(time=lambda: 10_000_000_000))
        late = engine.execute("status", {"plan": plan["id"], "ack_ref": result["ack_ref"], "load": True},
            objective="Load retained finite proof after original deadline", actor="test:software")
        assert late["held_failure"]["entry"] == before and len(transport.calls) == calls
        assert engine.ledger.get(result["old_finish"], held.chain.recovery.FINISH_KIND)["reason"] == "technical_stop"
    finally:
        engine.close()
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 10_000_000_000, sleep=lambda _: pytest.fail("no sleep")))
    controller = DeadlineHarness(owner, config=Config(offline=False), transport=transport)
    controller.synthetic_history = result["history"]
    try:
        arguments = {"plan": plan["id"], "ack_ref": result["ack_ref"], "allow_paid_execution": True}
        first = controller.execute("status", arguments, objective="Verify immutable original scheduling deadline", actor="test:software")
        run_id = controller.fast_run
        second = controller.execute("status", arguments, objective="Verify exact terminal restart with the same hold", actor="test:software")
        assert first["finished_reason"] == second["finished_reason"] == "deadline"
        assert controller.fast_run == run_id and len(transport.calls) == calls
        assert controller.ledger.get(run_id, held.RUN_KIND)["deadline_epoch"] == result["ack"]["deadline_epoch"]
    finally:
        controller.close()
    # Same numeric token count with a different origin cannot authorize reuse.
    verifier = HeldHarness(owner, config=Config(offline=False), transport=transport)
    try:
        with pytest.raises(AuditError, match="count_consumer_changed"):
            verifier.execute("status", {"plan": plan["id"], "tamper_count_link": True},
                objective="Reject a synthetic altered count-origin linkage", actor="test:software")
        assert len(transport.calls) == calls
    finally:
        verifier.close()


def test_existing_data_plane_and_startup_schedule_are_inherited():
    assert runner.HeldCostRecoveryResearch.dispatch is held.base.fast.FastResearch.dispatch
    assert runner.HeldCostRecoveryResearch.stage is held.base.fast.FastResearch.stage
    assert runner.HeldCostRecoveryResearch.reconcile is fixture.poll_fixture.poll.ReconciliationResearch.reconcile
    values = dict(startup_pending=True, pending=True, staged=True, unmanifested=True, pressure=None, poll_due=True)
    assert runner.cycle_operation(startup_observed=False, **values) == "reconcile"
    assert runner.cycle_operation(startup_observed=True, **values) == "submit"
