"""Closed failed-row acknowledgment; real temporary ledger plus pure guards."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_budget import InputTokenReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_failure_ack as ack
    import run_luna_budget_recovery as recovery
finally:
    sys.path.pop(0)

import test_run_luna_budget_fast as fast_fixture
import test_poll_luna_budget_batch as poll_fixture


def fictional_fields(kind="truncation"):
    usage = {"input_tokens": 123, "output_tokens": 4096 if kind == "truncation" else 12}
    usage["total_tokens"] = sum(usage.values())
    body = {"model": "gpt-6-luna", "error": None, "usage": usage,
        "status": "incomplete" if kind == "truncation" else "completed",
        "incomplete_details": {"reason": "max_output_tokens"} if kind == "truncation" else None,
        "output": [{"type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "refusal", "refusal": "Fictional refusal."}]}]}
    assessment = {"status": "error", "model": "gpt-6-luna", "technical_failure": True, "missing": False, "output": None,
        "accepted": False, "human_validated": False, "request": "a" * 64, "response": "b" * 64,
        "usage": usage, "errors": ["response:not_completed"] if kind == "truncation" else
        ["response:refusal", "response:not_single_output_text"]}
    entry = {"request": {"max_output_tokens": 4096, "input_count": {"input_tokens": 123}},
        "status": "settled", "accepted": True, "reserved_nanousd": 0,
        "settlement": {"complete": True, "model": "gpt-6-luna", "request_sha256": assessment["request"],
            "receipt_sha256": assessment["response"], "input_tokens": 123, "output_tokens": usage["output_tokens"]}}
    return {"error": None, "response": {"status_code": 200, "body": body}}, assessment, entry, {"model": "gpt-6-luna", "max_output_tokens": 4096}


@pytest.mark.parametrize("kind,expected", [("truncation", "terminal_output_cap_truncation_still_failed"),
                                           ("refusal", "terminal_refusal_still_failed")])
def test_terminal_failure_stays_failed_not_repaired_or_accepted(kind, expected):
    fields = fictional_fields(kind)
    before = deepcopy(fields)
    assert ack.terminal_failure_kind(*fields) == expected
    assert fields == before and fields[1]["status"] == "error" and fields[1]["accepted"] is False


@pytest.mark.parametrize("change", ["wrong_model", "unknown_usage", "overrun", "mismatched_input", "wrong_cap",
                                    "nonterminal", "different_incomplete_reason", "not_at_cap", "ordinary_parser_error"])
def test_other_faults_and_uncertain_costs_are_not_acknowledgeable(change):
    row, assessment, entry, request = fictional_fields()
    body = row["response"]["body"]
    if change == "wrong_model":
        body["model"] = "other"
    elif change == "unknown_usage":
        entry["settlement"]["complete"] = False
    elif change == "overrun":
        entry["status"] = "overrun"
    elif change == "mismatched_input":
        entry["request"]["input_count"]["input_tokens"] = 124
    elif change == "wrong_cap":
        request["max_output_tokens"] = 8192
    elif change == "nonterminal":
        body["status"] = "in_progress"
    elif change == "different_incomplete_reason":
        body["incomplete_details"] = {"reason": "other"}
    elif change == "not_at_cap":
        body["usage"].update(output_tokens=4095, total_tokens=4218)
        entry["settlement"]["output_tokens"] = 4095
    else:
        assessment["errors"] = ["response:output_missing_or_invalid"]
    with pytest.raises(AuditError):
        ack.terminal_failure_kind(row, assessment, entry, request)


@pytest.mark.parametrize("values", [[], ["a" * 64], ["a" * 64] * 2, ["a" * 64, "b" * 64, "c" * 64], ["x", "y"]])
def test_exact_two_explicit_distinct_ids_required(values):
    with pytest.raises(AuditError, match="exact_two"):
        ack.exact_ids(values)


def test_finite_gate_preserves_errors_other_blockers_and_future_stop():
    row = {"id": "a" * 64, "plan": "p", "status": "error", "technical_failure": True,
           "custom_id": "custom", "manifest": "m", "attempt": "attempt", "request": "req", "response": "resp",
           "errors": ["response:not_completed"]}
    proof = {"assessment": row["id"], **{key: row[key] for key in ("custom_id", "manifest", "attempt", "request", "response", "errors")}}
    acknowledgment = {"plan": "p", "failures": [proof]}
    blockers = ["prior_technical_or_unknown_assessment", "shared_budget_unknown_or_unresolved_charge"]
    original = deepcopy(row)
    assert recovery.recovery_gate(blockers, [row], {}, acknowledgment) == ["shared_budget_unknown_or_unresolved_charge"]
    assert row == original
    future = {**row, "id": "b" * 64}
    assert recovery.recovery_gate(blockers, [row, future], {}, acknowledgment) == blockers
    changed = {**row, "response": "changed"}
    assert recovery.recovery_gate(blockers, [changed], {}, acknowledgment) == blockers


def test_startup_successful_observation_admits_while_original_job_still_pending():
    kwargs = dict(startup_pending=True, pending=True, staged=True, unmanifested=True, pressure=None, poll_due=True)
    assert recovery.cycle_operation(startup_observed=False, **kwargs) == "reconcile"
    assert recovery.cycle_operation(startup_observed=True, **kwargs) == "submit"
    assert recovery.cycle_operation(startup_observed=True, **{**kwargs, "pressure": "budget_pressure"}) == "reconcile"


@pytest.mark.parametrize("field,new_value", [("deadline_epoch", 200), ("ack_ref", "another"), ("queue_token_cap", 30_000_000)])
def test_restart_cannot_reset_deadline_or_change_bound_ack_and_capacity(field, new_value):
    binding = {"deadline_epoch": 100, "ack_ref": "original", "queue_token_cap": 20_000_000}
    recovery.validate_run_binding(binding, binding)
    with pytest.raises(AuditError, match="no_deadline_or_budget_reset"):
        recovery.validate_run_binding(binding, {**binding, field: new_value})


@pytest.mark.parametrize("mutation", [None, "deadline", "stop", "code"])
def test_original_fast_stop_and_phase_deadline_are_preserved(monkeypatch, mutation):
    phase = {"deadline_epoch": 100}
    original = {"plan": "p", "authorization_id": ack.STUDY, "continuation_ref": "phase",
                "deadline_epoch": 100, "implementation": ack.fast.implementation_hashes()}
    finish = {"plan": "p", "run": "run", "reason": "technical_stop"}
    if mutation == "deadline":
        original["deadline_epoch"] = 101
    elif mutation == "stop":
        finish["reason"] = "complete"
    elif mutation == "code":
        original["implementation"] = {}
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda identifier, kind: original if identifier == "run" else finish))
    monkeypatch.setattr(ack, "load_continuation", lambda *args: phase)
    if mutation:
        with pytest.raises(AuditError, match="original_stop_or_deadline_changed"):
            ack.check_history(engine, "session", "p", "phase", "run", "finish")
    else:
        assert ack.check_history(engine, "session", "p", "phase", "run", "finish") == phase


class FailureTransport(poll_fixture.ResultTransport):
    def result_bytes(self, job_id):
        rows = [json.loads(line) for line in super().result_bytes(job_id).splitlines()]
        body = rows[0]["response"]["body"]
        if job_id == "batch_1":
            body.update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
            body["usage"].update(output_tokens=4096, total_tokens=4219)
        else:
            body["output"][0]["content"] = [{"type": "refusal", "refusal": "Synthetic refusal."}]
        return b"".join(canonical(row).encode() + b"\n" for row in rows)


class VerifyHarness(poll_fixture.poll.ReconciliationResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("verify"):
            book, state = ack.known_budget(self, session, data["plan"])
            rows = ack._rows(self, session, ack.ASSESSMENT_KIND, data["plan"])
            errors = [row for row in rows if row["status"] == "error"]
            proofs = [ack.verify_failure(self, session, data["plan"], row["id"], book) for row in errors]
            if data.get("register"):
                phase_ref = "synthetic-phase"
                run = self.ledger.record(session, ack.fast.RUN_KIND, data["plan"] + ":" + phase_ref + ":fast-v1",
                    {"plan": data["plan"], "deadline_epoch": time.time() + 600, "queue_token_cap": 20_000_000, "count_workers": 16})
                self.ledger.record(session, ack.fast.FINISH_KIND, run,
                    {"plan": data["plan"], "run": run, "reason": "technical_stop"})
                diagnostic = self.ledger.record(session, ack.DIAGNOSTIC_KIND, "synthetic-progress",
                    {"plan": data["plan"], "budget_state": state, "budget_frozen": False, "pending_jobs": 0,
                     "technical_rows": [{"id": proof["assessment"], "custom_id": proof["custom_id"], "errors": proof["errors"],
                        "current_cost_status": "settled", "retained_provider_metadata": {"receipt": proof["download_receipt"]}}
                        for proof in proofs]})
                registration = {"plan": data["plan"], "diagnostic_ref": diagnostic, "phase_continuation_ref": phase_ref,
                                "assessment_ids": [proof["assessment"] for proof in proofs]}
                first = recovery.resolve_ack_reference(self, session, context, registration)
                # A later unrelated, wholly synthetic reservation changes the
                # book state; exact acknowledgment reuse must not reset it or
                # demand the now-historical diagnostic be current again.
                book.reserve(request_id="synthetic-future", task_id="synthetic-future", corpus_id="incident-reports",
                    plan_id=data["plan"], request_sha256="c" * 64,
                    input_count=InputTokenReceipt(123, "gpt-6-luna", "c" * 64, "d" * 64, "provider_responses_input_tokens"),
                    max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
                new_state = self.gateway.save_book(session, book, state)
                again = recovery.resolve_ack_reference(self, session, context, registration)
                return {"ack_ref": first, "reused_ref": again, "old_state": state, "new_state": new_state}
            return {"proofs": proofs, "state": state, "errors_still_failed": [row["status"] for row in errors]}
        # Seeded canaries deliberately omit display text. Exercise the real
        # reconciliation data path without rendering that synthetic seed.
        plan = self.ledger.get(data["plan"], fast_fixture.fast.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, data["plan"], plan)
        self.result_parser = ack.parse_batch_results_phase_aware
        self.parser_mode = "explicit-final-answer-phase-v1"
        policy, _, _ = self.authorization(session, context, data["plan"], plan)
        for job in ack._rows(self, session, fast_fixture.fast.JOB_KIND, data["plan"]):
            self.reconcile(session, data["plan"], policy, job)
        book, _ = ack.known_budget(self, session, data["plan"])
        rows = ack._rows(self, session, ack.ASSESSMENT_KIND, data["plan"])
        return {"status_counts": {"error": sum(row["status"] == "error" for row in rows)},
                "reserved_usd": book.reserved_nanousd / 1e9, "budget_frozen": book.frozen}


def test_real_audited_bulk_failures_replay_and_settle_without_new_calls(tmp_path, monkeypatch):
    submitter, original, plan, _ = fast_fixture.fixture(tmp_path, monkeypatch)
    owner = submitter.ledger.root
    fast_fixture.execute(submitter, plan)
    submitter.close()
    transport = FailureTransport()
    transport.files, transport.jobs, transport.calls = original.files, original.jobs, original.calls
    # The separate phase authorization is already covered by its own tests;
    # this test exercises actual retained rows and accounting, not that proof.
    monkeypatch.setattr(poll_fixture.poll, "load_continuation", lambda *args, **kwargs: {"id": "synthetic-phase"})
    engine = VerifyHarness(owner, config=Config(offline=False), transport=transport)
    try:
        observed = engine.execute("status", {"plan": plan["id"], "allow_paid_execution": True, "continuation_ref": "synthetic-phase"},
            objective="Reconcile fictional terminal failures without retries", actor="test:software")
        assert observed["status_counts"]["error"] == 2
        assert observed["reserved_usd"] == 0 and not observed["budget_frozen"]
        calls = len(transport.calls)
        verified = engine.execute("status", {"plan": plan["id"], "verify": True},
            objective="Verify fictional raw failures and settled cost without acceptance", actor="test:software")
        assert {proof["failure_kind"] for proof in verified["proofs"]} == {
            "terminal_output_cap_truncation_still_failed", "terminal_refusal_still_failed"}
        assert verified["errors_still_failed"] == ["error", "error"]
        assert all(proof["accepted_output"] is False and proof["retry_allowed"] is False for proof in verified["proofs"])
        assert len(transport.calls) == calls
        # Exact historical phase/run checking has dedicated tests. Isolate it
        # here to exercise the shared builder inside the existing active online
        # session: actual raw proof, current-cost checks and durable ack all run.
        monkeypatch.setattr(ack, "check_history", lambda *args: {"deadline_epoch": 9_999_999_999,
            "assessment": "synthetic-old-phase", "plan": plan["id"], "custom_id": "synthetic-old-phase"})
        registered = engine.execute("status", {"plan": plan["id"], "verify": True, "register": True},
            objective="Test combined durable failure acknowledgment and immutable reuse in one audited session", actor="test:software")
        assert registered["ack_ref"] == registered["reused_ref"]
        assert registered["old_state"] != registered["new_state"]
        assert len(transport.calls) == calls
    finally:
        engine.close()
