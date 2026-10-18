"""Synthetic full held lineage, later raw truncations and real audit/accounting."""
import ast
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, utc
from newsresearch.event_batch_budget import InputTokenReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_held_chain as chain
    import run_luna_budget_held_chain as runner
    import drain_luna_budget_held_chain as drain
finally:
    sys.path.pop(0)

import test_luna_budget_held_cost as old
import test_drain_luna_budget_held_cost as stop_fixture


@pytest.mark.parametrize("mutation", [None, "extra_cost_blocker", "empty_blockers", "deadline", "parent", "latest", "protocol"])
def test_actual_held_stop_has_only_new_error_blocker_but_hold_stays_unknown(monkeypatch, mutation):
    records, book, _ = stop_fixture.fixture()
    prior = {**records[stop_fixture.ACK], "id": stop_fixture.ACK}
    records["held-finish"]["blockers"] = ["prior_technical_or_unknown_assessment"]
    if mutation == "extra_cost_blocker":
        records["held-finish"]["blockers"].append("shared_budget_unknown_or_unresolved_charge")
    elif mutation == "empty_blockers":
        records["held-finish"]["blockers"] = []
    elif mutation == "deadline":
        records["held-run"]["deadline_epoch"] += 1
    elif mutation == "parent":
        records["held-run"]["stopped_finish"] = "wrong"
    elif mutation == "protocol":
        records["held-run-protocol"]["content"]["prior_ack_ref"] = "wrong"
    latest = ("wrong" if mutation == "latest" else "held-run", records["held-run"])
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda ref, kind: records[ref], append=lambda *args: None),
        latest=lambda kind, key: ("held-finish", records["held-finish"]) if kind == chain.held.FINISH_KIND else latest)
    monkeypatch.setattr(chain, "kind", lambda *args: chain.held.ACK_KIND)
    before = deepcopy(records)
    if mutation:
        with pytest.raises(AuditError):
            chain.stopped_records(engine, "s", stop_fixture.PLAN, prior, "held-stop", technical_only=True)
    else:
        result = chain.stopped_records(engine, "s", stop_fixture.PLAN, prior, "held-stop", technical_only=True)
        assert result["finish"]["blockers"] == ["prior_technical_or_unknown_assessment"]
        assert book.entry("held")["status"] == "unknown" and book.reserved_nanousd == 1_402_432
    assert before == records


def diagnostic_fixture():
    records, book, _ = stop_fixture.fixture()
    prior = {**records[stop_fixture.ACK], "id": stop_fixture.ACK}
    ids = ["6" * 64, "7" * 64]
    value = {"stop_result_ref": "held-stop", "budget_state_at_ack": "state", "new_assessment_ids": ids}
    diagnostic = {"plan": stop_fixture.PLAN, "stop_result_ref": "held-stop", "prior_ack_ref": prior["id"],
        "held_ack_ref": prior["id"], "held_run_ref": "held-run", "held_finish_ref": "held-finish",
        "recovery_run": "held-run", "recovery_finish": "held-finish", "phase_continuation_ref": prior["phase_continuation_ref"],
        "budget_state": "state", "pending_jobs": 0, "drain_obstacles": [], "drain_timed_out": False,
        "gateway_stop_ids": [], "budget_frozen": False, "reserved_usd": book.reserved_nanousd / 1e9,
        "previously_acknowledged_assessment_ids": sorted(prior["assessment_ids"] + [prior["phase"]["assessment"]]),
        "newly_unacknowledged_technical_assessment_ids": ids, "original_held_entry": prior["held_failure"]["entry"],
        "original_held_cost_unchanged": True, "cost_diagnostics": {"anomalous_entries": [prior["held_failure"]["entry"]],
            "anomalous_event_history": prior["held_failure"]["event_history"]}, "protocol": "diagnostic-protocol"}
    protocol = {"content": {**diagnostic, "method": chain.held_drain.METHOD, "implementation": chain.held_drain.implementation_hashes()}}
    return prior, value, diagnostic, protocol, {"legacy": True, "run_id": "held-run", "finish_id": "held-finish"}


@pytest.mark.parametrize("field,value", [("pending_jobs", 1), ("reserved_usd", 0), ("budget_frozen", True),
    ("gateway_stop_ids", ["stop"]), ("drain_obstacles", ["unknown"]), ("drain_timed_out", True),
    ("budget_state", "stale"), ("prior_ack_ref", "wrong"), ("newly_unacknowledged_technical_assessment_ids", []),
    ("previously_acknowledged_assessment_ids", []), ("original_held_cost_unchanged", False), ("cost_diagnostics", {})])
def test_diagnostic_must_bind_exact_finite_set_current_hold_and_drained_state(field, value):
    prior, binding, diagnostic, protocol, records = diagnostic_fixture()
    engine = SimpleNamespace(ledger=SimpleNamespace(get=lambda *args: protocol))
    chain.check_diagnostic(engine, stop_fixture.PLAN, diagnostic, binding, prior, records)
    diagnostic[field] = value
    with pytest.raises(AuditError, match="exact_drained"):
        chain.check_diagnostic(engine, stop_fixture.PLAN, diagnostic, binding, prior, records)


def test_refusal_is_not_part_of_the_new_truncation_only_method(monkeypatch):
    monkeypatch.setattr(chain.held.chain, "checked_new_failures", lambda *args: [{"failure_kind": "terminal_refusal_still_failed"}])
    with pytest.raises(AuditError, match="only_exact_settled_output_cap"):
        chain.checked_truncations(None, "s", "p", ["a" * 64], None, {})


def test_loop_and_paid_data_plane_remain_identical_to_frozen_held_controller():
    def loop(path):
        node = next(item for item in ast.walk(ast.parse(path.read_text())) if isinstance(item, ast.While))
        for item in ast.walk(node):
            if isinstance(item, ast.Constant) and item.value == "luna_budget_held_cost_chain_obstacle":
                item.value = "luna_budget_held_cost_obstacle"
        return ast.dump(node, include_attributes=False)
    assert loop(chain.ROOT / "scripts/run_luna_budget_held_chain.py") == loop(chain.ROOT / "scripts/run_luna_budget_held_cost.py")
    assert runner.HeldChainRecoveryResearch.action is old.runner.HeldCostRecoveryResearch.action
    assert runner.HeldChainRecoveryResearch.dispatch is old.runner.HeldCostRecoveryResearch.dispatch
    assert runner.HeldChainRecoveryResearch.reconcile is old.runner.HeldCostRecoveryResearch.reconcile
    kwargs = dict(startup_pending=True, pending=True, staged=True, unmanifested=True, pressure=None, poll_due=True)
    assert runner.cycle_operation(startup_observed=False, **kwargs) == "reconcile"
    assert runner.cycle_operation(startup_observed=True, **kwargs) == "submit"


def terminal_records(engine, session, context, plan_id, prior, state, *, legacy=True, reason="technical_stop", blockers=None):
    method = chain.held.RECOVERY_METHOD if legacy else chain.RECOVERY_METHOD
    implementation = chain.held.implementation_hashes() if legacy else chain.implementation_hashes()
    run_kind, finish_kind = (chain.held.RUN_KIND, chain.held.FINISH_KIND) if legacy else (chain.RUN_KIND, chain.FINISH_KIND)
    suffix = ":held-cost-recovery-v1" if legacy else ":held-cost-chain-v1"
    binding = {"plan": plan_id, "authorization_id": chain.STUDY, "ack_ref": prior["id"],
        "implementation": implementation, **{key: prior[key] for key in (*chain.held.chain.INHERITED, *chain.PARENTS)}}
    protocol = engine._version(session, context, {"kind": "protocol", "key": "fictional-terminal-" + method,
        "content": {"method": method, **binding}})["id"]
    run = engine.ledger.record(session, run_kind, plan_id + ":" + prior["id"] + suffix,
        {**binding, "protocol": protocol, "started_at": utc(), "startup_pending_manifests": []})
    finish = engine.ledger.record(session, finish_kind, run, {"plan": plan_id, "run": run, "reason": reason,
        "ended_at": utc(), "budget_state": state, "blockers": ["prior_technical_or_unknown_assessment"] if blockers is None else blockers,
        "ack_ref": prior["id"], **{key: prior[key] for key in ("prior_ack_ref", "original_finish", "stopped_finish")}})
    view = engine.view(session, plan_id)
    submitted = sum(row["request_count"] for row in view["jobs"])
    stop = engine.ledger.record(session, "luna_budget_fast_status", "fictional-wrapped-stop-" + run, {
        "plan": plan_id, "run": run, "protocol": protocol, "budget_state": state, "finished_reason": reason,
        "held_ack_ref": prior["id"], "finite_assessment_ids": prior["assessment_ids"],
        "held_assessment": prior["held_failure"]["assessment"], "held_custom_id": prior["held_failure"]["custom_id"],
        "held_cost_status": "unknown", "held_reserved_nanousd": prior["held_failure"]["entry"]["reserved_nanousd"],
        "held_expected_nanousd": prior["held_failure"]["entry"]["reserved_nanousd"],
        "deadline_epoch": prior["deadline_epoch"], "queue_token_cap": prior["queue_token_cap"],
        "submitted": submitted, "assessments": submitted, "pending_requests": 0, "pending_jobs": 0})
    return run, finish, stop


class ChainHarness(runner.HeldChainRecoveryResearch):
    @audited_handler
    def _status(self, session, context, data):
        plan_id = data["plan"]
        if data.get("load"):
            return chain.load_ack(self, session, plan_id, data["ack_ref"])
        if data.get("terminal"):
            ack = chain.load_ack(self, session, plan_id, data["ack_ref"])
            book, state = self.gateway.load_book(session, chain.STUDY)
            if data.get("future_unknown"):
                book.reserve(request_id="later-unknown", task_id="later-unknown", corpus_id="cybercrime", plan_id=plan_id,
                    request_sha256="c" * 64, input_count=InputTokenReceipt(123, "gpt-6-luna", "c" * 64, "d" * 64,
                        "provider_responses_input_tokens"), max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
                book.settle("later-unknown", None)
                state = self.gateway.save_book(session, book, state)
            run, finish, stop = terminal_records(self, session, context, plan_id, ack, state, legacy=False, reason="deadline", blockers=[])
            return {"run": run, "finish": finish, "stop": stop}
        plan = self.ledger.get(plan_id, chain.base.PLAN_KIND)
        prior = chain.load_history(self, session, plan_id, data["prior_ack_ref"])
        self.failure_ack = prior
        self.fast_run = "fictional-later-held-run"
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        snapshot = runner.fast.core.load_contract_snapshot()
        self.stage(session, plan_id, plan, view, state, snapshot)
        prior_jobs = {row["manifest"] for row in view["jobs"]}
        for manifest in view["manifests"]:
            if manifest["id"] in prior_jobs or manifest["phase"] != "bulk":
                continue
            raw = runner.fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, snapshot)
            book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                active_tokens=0, queue_cap=20_000_000, workers=2, deadline=prior["deadline_epoch"])
            assert pressure is None and job
        self.result_parser = chain.base.parse_batch_results_phase_aware
        self.parser_mode = "explicit-final-answer-phase-v1"
        for job in self.view(session, plan_id)["jobs"]:
            self.reconcile(session, plan_id, policy, job)
        book, state = self.gateway.load_book(session, chain.STUDY)
        view = self.view(session, plan_id)
        blockers = self.check_gate(session, plan_id, plan, view, book, prior["phase"])
        assert blockers == ["prior_technical_or_unknown_assessment"]
        ids = sorted(row["id"] for row in view["assessments"] if row.get("technical_failure")
            and row["id"] not in prior["assessment_ids"] and row["id"] != prior["phase"]["assessment"])
        assert len(ids) == 2
        proofs = [chain.base.verify_failure(self, session, plan_id, ref, book) for ref in ids]
        run, finish, stop = terminal_records(self, session, context, plan_id, prior, state, blockers=blockers)
        diagnostic = {"plan": plan_id, "stop_result_ref": stop, "prior_ack_ref": prior["id"], "held_ack_ref": prior["id"],
            "held_run_ref": run, "held_finish_ref": finish, "recovery_run": run, "recovery_finish": finish,
            "phase_continuation_ref": prior["phase_continuation_ref"], "budget_state": state,
            "pending_jobs": 0, "drain_obstacles": [], "drain_timed_out": False, "gateway_stop_ids": [],
            "budget_frozen": False, "reserved_usd": book.reserved_nanousd / 1e9,
            "previously_acknowledged_assessment_ids": sorted(prior["assessment_ids"] + [prior["phase"]["assessment"]]),
            "newly_unacknowledged_technical_assessment_ids": ids, "original_held_entry": prior["held_failure"]["entry"],
            "original_held_cost_unchanged": True, "cost_diagnostics": {"anomalous_entries": [prior["held_failure"]["entry"]],
                "anomalous_event_history": prior["held_failure"]["event_history"]},
            "technical_rows": [{"id": proof["assessment"], "custom_id": proof["custom_id"], "errors": proof["errors"],
                "current_cost_status": "settled", "retained_provider_metadata": {"receipt": proof["download_receipt"]}} for proof in proofs]}
        diagnostic["protocol"] = self._version(session, context, {"kind": "protocol", "key": "fictional-held-drain",
            "content": {**diagnostic, "method": chain.held_drain.METHOD, "implementation": chain.held_drain.implementation_hashes()}})["id"]
        diag = self.ledger.record(session, chain.base.DIAGNOSTIC_KIND, "fictional-held-drain", diagnostic)
        arguments = {"plan": plan_id, "prior_ack_ref": prior["id"], "stop_result_ref": stop,
            "diagnostic_ref": diag, "assessment_ids": ids}
        with pytest.raises(AuditError, match="every_future_or_unacknowledged"):
            chain.held.load_ack(self, session, plan_id, prior["id"])
        reference = runner.resolve_ack_reference(self, session, context, arguments)
        ack = chain.load_ack(self, session, plan_id, reference)
        self.failure_ack = ack
        assert self.check_gate(session, plan_id, plan, view, book, ack["phase"]) == []
        view["assessments"].append({"id": "future", "plan": plan_id, "status": "error", "technical_failure": True})
        assert "prior_technical_or_unknown_assessment" in self.check_gate(session, plan_id, plan, view, book, ack["phase"])
        reused = runner.resolve_ack_reference(self, session, context, arguments)
        return {"ack_ref": reference, "reused": reused, "ack": ack, "stop": stop, "finish": finish, "calls": len(self.transport.calls)}


class DeadlineHarness(runner.HeldChainRecoveryResearch):
    def report(self, session, plan_id, plan, view, book, state, *, reason=None):
        return {"markdown": "Fictional controller deadline.", "finished_reason": reason, "pending_jobs": 0}


class DiagnosticHarness(drain.HeldChainDiagnosticResearch):
    @audited_handler
    def retained_report(self, session, context, plan_id, binding):
        # Presentation mechanics are unchanged and separately tested. This
        # fixture's old phase history was seeded, not a real source assessment.
        book, state = self.gateway.load_book(session, chain.STUDY)
        value = {**binding, "plan": plan_id, "pending_jobs": 0, "budget_state": state,
            "original_hold": book.entry(self.held_ack["held_failure"]["custom_id"]),
            "later_unknown": book.entry("later-unknown"), "network_calls": len(self.transport.calls)}
        return chain.present(self, session, "fictional_held_chain_diagnostic", value, "Synthetic GET-only identity check.")


def test_real_prior_hold_later_two_raw_truncations_append_resume_and_deadline(tmp_path, monkeypatch):
    fast_fixture = old.fixture.fast_fixture
    wave = fast_fixture.bulk.wave
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    seed = wave.SeededWaveResearch(owner)
    try:
        seed.execute("status", {"seed": True, "plan": plan["id"]}, objective="Seed fictional canary usage", actor="test:software")
        seed.execute("status", {"plan": plan["id"], "max_per_corpus": 1}, objective="Stage first fictional wave", actor="test:software")
    finally:
        seed.close()
    transport = old.ErrorTransport()
    submitter = fast_fixture.DispatchHarness(owner, config=Config(offline=False), transport=transport)
    try:
        fast_fixture.execute(submitter, plan)
    finally:
        submitter.close()
    # Only the separately tested original phase/two-settled-history dependency is
    # isolated. Original held raw/dispatch/count proof, its settled peer, all NEW
    # raw failures, the real book and every new lineage/diagnostic check are real.
    monkeypatch.setattr(chain.held, "verify_history", lambda engine, *args: engine.synthetic_history)
    engine = old.HeldHarness(owner, config=Config(offline=False), transport=transport)
    try:
        initial = engine.execute("status", {"plan": plan["id"], "register": True}, objective="Seed exact fictional held predecessor", actor="test:software")
    finally:
        engine.close()
    monkeypatch.setattr(runner.fast, "read_partition", wave.runner.read_partition)
    next_engine = ChainHarness(owner, config=Config(offline=False), transport=transport)
    next_engine.synthetic_history = initial["history"]
    try:
        result = next_engine.execute("status", {"plan": plan["id"], "prior_ack_ref": initial["ack_ref"]},
            objective="Verify later exact settled failures with the original unknown hold", actor="test:software")
        assert result["ack_ref"] == result["reused"]
        assert len(result["ack"]["assessment_ids"]) == 6 and len(result["ack"]["new_failures"]) == 2
        assert result["ack"]["held_failure"] == initial["held"]
        assert next_engine.ledger.get(result["finish"], chain.held.FINISH_KIND)["blockers"] == ["prior_technical_or_unknown_assessment"]
        calls = len(transport.calls)
        monkeypatch.setattr(chain, "time", SimpleNamespace(time=lambda: 10_000_000_000))
        loaded = next_engine.execute("status", {"plan": plan["id"], "ack_ref": result["ack_ref"], "load": True},
            objective="Load retained chained history after admission expiry", actor="test:software")
        assert loaded["deadline_epoch"] == initial["ack"]["deadline_epoch"] and len(transport.calls) == calls
    finally:
        next_engine.close()
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 10_000_000_000, sleep=lambda _: pytest.fail("must not wait")))
    controller = DeadlineHarness(owner, config=Config(offline=False), transport=transport)
    controller.synthetic_history = initial["history"]
    try:
        args = {"plan": plan["id"], "ack_ref": result["ack_ref"], "allow_paid_execution": True}
        first = controller.execute("status", args, objective="Preserve original admission deadline", actor="test:software")
        run = controller.fast_run
        again = controller.execute("status", args, objective="Preserve terminal chained restart", actor="test:software")
        assert first["finished_reason"] == again["finished_reason"] == "deadline" and run == controller.fast_run
        assert len(transport.calls) == calls
    finally:
        controller.close()
    # GET-only historical validation remains available after deadline and with
    # a later unknown. That later liability still makes paid admission fail.
    stopped = ChainHarness(owner, config=Config(offline=False), transport=transport)
    stopped.synthetic_history = initial["history"]
    try:
        terminal = stopped.execute("status", {"plan": plan["id"], "ack_ref": result["ack_ref"],
            "terminal": True, "future_unknown": True}, objective="Seed fictional later unknown terminal diagnostic", actor="test:software")
        with pytest.raises(AuditError, match="new_or_changed_unknown"):
            stopped.execute("status", {"plan": plan["id"], "ack_ref": result["ack_ref"], "load": True},
                objective="Reject new unknown paid admission", actor="test:software")
    finally:
        stopped.close()
    diagnostic = DiagnosticHarness(owner, config=Config(offline=False), transport=transport)
    diagnostic.synthetic_history = initial["history"]
    try:
        retained = diagnostic.execute("status", {"plan": plan["id"], "stop_result_ref": terminal["stop"],
            "held_ack_ref": result["ack_ref"], "allow_existing_job_reads": True, "max_wait_seconds": 0},
            objective="Test post-deadline GET-only held-chain diagnosis", actor="test:software")
        assert retained["original_hold"] == initial["held"]["entry"]
        assert retained["later_unknown"]["status"] == "unknown" and retained["inference_continuation_permitted"] is False
        assert retained["network_calls"] == calls and retained["original_deadline_epoch"] == initial["ack"]["deadline_epoch"]
    finally:
        diagnostic.close()


def test_get_diagnostic_forbids_mutations_even_before_network():
    engine = object.__new__(drain.HeldChainDiagnosticResearch)
    engine.drain_phase = "reconcile"
    for path in ("/v1/responses/input_tokens", "/v1/files", "/v1/batches"):
        with pytest.raises((AuditError, ResearchError)):
            engine.action("s", "p", "policy", "forbidden", {"method": "POST", "path": path}, b"{}")
