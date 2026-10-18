"""Second finite acknowledgment: one raw truncation, same real unknown hold.

All provider traffic is synthetic. The original phase/two-old-failure history
dependency is isolated as in the existing fixture; the held request, both later
failure generations, proof recursion, real ledger and shared gateway are real.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, Context, Json, canonical
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import audited_handler

import test_luna_budget_held_chain as fixture
import luna_budget_held_chain as chain
import run_luna_budget_held_chain as runner

old = fixture.old


class RecursiveTransport(old.ErrorTransport):
    def perform(self, request: Json, body: bytes | None, client_request_id: str) -> BatchReceipt:
        result = super().perform(request, body, client_request_id)
        if request["path"] == "/v1/responses/input_tokens":
            raw = canonical({"input_tokens": 4015}).encode()
            return BatchReceipt(raw, 200, result.request_id, body_sha256=hashlib.sha256(raw).hexdigest())
        return result

    def result_bytes(self, job_id: str) -> bytes:
        # The second generation consists of batch5/batch6. Only batch5 has a
        # new truncation; batch6 has an ordinary completed response.
        raw = (old.fixture.poll_fixture.ResultTransport.result_bytes(self, job_id)
            if job_id == "batch_6" else super().result_bytes(job_id))
        rows = [json.loads(line) for line in raw.splitlines()]
        for row in rows:
            usage = row["response"]["body"].get("usage")
            if usage is not None:
                usage.update(input_tokens=4015, total_tokens=4015 + usage["output_tokens"])
        return b"".join(canonical(row).encode() + b"\n" for row in rows)


class RecursiveHarness(runner.HeldChainRecoveryResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        if data.get("load"):
            return chain.load_ack(self, session, plan_id, data["ack_ref"])
        if data.get("later_failure"):
            ack = chain.load_ack(self, session, plan_id, data["ack_ref"])
            book, state = self.gateway.load_book(session, chain.STUDY)
            before = book.to_dict()
            self.ledger.record(session, chain.base.ASSESSMENT_KIND, "fictional-future-error", {
                "plan": plan_id, "custom_id": "fictional-future-error", "status": "error", "technical_failure": True})
            with pytest.raises(AuditError, match="every_unacknowledged_error"):
                chain.load_ack(self, session, plan_id, data["ack_ref"])
            self.failure_ack = ack
            plan = self.ledger.get(plan_id, chain.base.PLAN_KIND)
            blockers = self.check_gate(session, plan_id, plan, self.view(session, plan_id), book, ack["phase"])
            assert blockers == ["prior_technical_or_unknown_assessment"]
            saved = self.gateway.load_book(session, chain.STUDY)
            assert saved[0].to_dict() == before and saved[1] == state
            return {"blockers": blockers, "budget_unchanged": True}
        prior = chain.load_ack(self, session, plan_id, data["prior_ack_ref"])
        self.failure_ack = prior
        self.fast_run = "fictional-second-chain-run"
        plan = self.ledger.get(plan_id, chain.base.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        policy, book, state = self.authorization(session, context, plan_id, plan)
        original_hold = deepcopy(book.entry(prior["held_failure"]["custom_id"]))
        view = self.view(session, plan_id)
        snapshot = runner.fast.core.load_contract_snapshot()
        self.stage(session, plan_id, plan, view, state, snapshot)
        submitted = {row["manifest"] for row in view["jobs"]}
        for manifest in view["manifests"]:
            if manifest["id"] in submitted or manifest["phase"] != "bulk":
                continue
            raw = runner.fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, snapshot)
            book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                active_tokens=0, queue_cap=prior["queue_token_cap"], workers=2, deadline=prior["deadline_epoch"])
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
        assert len(ids) == 1
        proofs = [chain.base.verify_failure(self, session, plan_id, identifier, book) for identifier in ids]
        assert proofs[0]["failure_kind"] == "terminal_output_cap_truncation_still_failed"
        assert proofs[0]["settlement"]["input_tokens"] == 4015 and proofs[0]["settlement"]["output_tokens"] == 4096
        run, finish, stop = fixture.terminal_records(self, session, context, plan_id, prior, state, legacy=False, blockers=blockers)
        diagnostic = {"plan": plan_id, "stop_result_ref": stop, "prior_ack_ref": prior["id"], "held_ack_ref": prior["id"],
            "held_run_ref": run, "held_finish_ref": finish, "recovery_run": run, "recovery_finish": finish,
            "phase_continuation_ref": prior["phase_continuation_ref"], "budget_state": state,
            "pending_jobs": 0, "drain_obstacles": [], "drain_timed_out": False, "gateway_stop_ids": [],
            "budget_frozen": False, "reserved_usd": book.reserved_nanousd / 1e9,
            "previously_acknowledged_assessment_ids": sorted(prior["assessment_ids"] + [prior["phase"]["assessment"]]),
            "newly_unacknowledged_technical_assessment_ids": ids, "original_held_entry": original_hold,
            "original_held_cost_unchanged": True, "cost_diagnostics": {"anomalous_entries": [original_hold],
                "anomalous_event_history": prior["held_failure"]["event_history"]},
            "technical_rows": [{"id": proof["assessment"], "custom_id": proof["custom_id"], "errors": proof["errors"],
                "current_cost_status": "settled", "retained_provider_metadata": {"receipt": proof["download_receipt"]}} for proof in proofs]}
        diagnostic["protocol"] = self._version(session, context, {"kind": "protocol", "key": "fictional-second-held-chain-drain",
            "content": {**diagnostic, "method": fixture.drain.METHOD, "implementation": chain.implementation_hashes()}})["id"]
        diag = self.ledger.record(session, chain.base.DIAGNOSTIC_KIND, "fictional-second-held-chain-drain", diagnostic)
        args = {"plan": plan_id, "prior_ack_ref": prior["id"], "stop_result_ref": stop, "diagnostic_ref": diag, "assessment_ids": ids}
        # The first finite acknowledgment remains historically valid but cannot
        # itself authorize continuation over this later error.
        with pytest.raises(AuditError, match="every_unacknowledged_error"):
            chain.load_ack(self, session, plan_id, prior["id"])
        calls = len(self.transport.calls)
        reference = runner.resolve_ack_reference(self, session, context, args)
        ack = chain.load_ack(self, session, plan_id, reference)
        self.failure_ack = ack
        assert self.check_gate(session, plan_id, plan, view, book, ack["phase"]) == []
        reused = runner.resolve_ack_reference(self, session, context, args)
        with pytest.raises(AuditError, match="existing_registration_inputs_changed"):
            runner.resolve_ack_reference(self, session, context, {**args, "assessment_ids": prior["new_assessment_ids"]})
        assert len(self.transport.calls) == calls
        assert book.entry(prior["held_failure"]["custom_id"]) == original_hold
        assert self.gateway.load_book(session, chain.STUDY)[1] == state
        assert book.reserved_nanousd == original_hold["reserved_nanousd"] == 1_402_432
        return {"ack_ref": reference, "reused": reused, "ack": ack, "stop": stop, "finish": finish, "run": run,
            "prior": prior, "calls": calls, "state": state, "original_hold": original_hold}


def test_second_recursive_ack_has_one_raw_failure_and_preserves_hold_resume_and_future_stop(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fast_fixture = old.fixture.fast_fixture
    wave = fast_fixture.bulk.wave
    original_export = wave.fixture_module.synthetic_export
    monkeypatch.setattr(wave.fixture_module, "synthetic_export", lambda root, corpus: original_export(root, corpus, count=11))
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    seed = wave.SeededWaveResearch(owner)
    try:
        seed.execute("status", {"seed": True, "plan": plan["id"]}, objective="Seed fictional accounting", actor="test:software")
        seed.execute("status", {"plan": plan["id"], "max_per_corpus": 1}, objective="Stage first fictional wave", actor="test:software")
    finally:
        seed.close()
    transport = RecursiveTransport()
    submitter = fast_fixture.DispatchHarness(owner, config=Config(offline=False), transport=transport)
    try:
        fast_fixture.execute(submitter, plan)
    finally:
        submitter.close()
    monkeypatch.setattr(chain.held, "verify_history", lambda engine, *args: engine.synthetic_history)
    initial_engine = old.HeldHarness(owner, config=Config(offline=False), transport=transport)
    try:
        initial = initial_engine.execute("status", {"plan": plan["id"], "register": True},
            objective="Establish fictional original hold", actor="test:software")
    finally:
        initial_engine.close()
    monkeypatch.setattr(runner.fast, "read_partition", wave.runner.read_partition)
    choose = runner.fast.choose_next
    monkeypatch.setattr(runner.fast, "choose_next", lambda queue, manifested, limit: choose(queue, manifested, 1))
    first_engine = fixture.ChainHarness(owner, config=Config(offline=False), transport=transport)
    first_engine.synthetic_history = initial["history"]
    try:
        first = first_engine.execute("status", {"plan": plan["id"], "prior_ack_ref": initial["ack_ref"]},
            objective="Establish fictional first finite chain", actor="test:software")
    finally:
        first_engine.close()
    second_engine = RecursiveHarness(owner, config=Config(offline=False), transport=transport)
    second_engine.synthetic_history = initial["history"]
    try:
        second = second_engine.execute("status", {"plan": plan["id"], "prior_ack_ref": first["ack_ref"]},
            objective="Append one proved fictional failure to an existing chain", actor="test:software")
        assert second["ack_ref"] == second["reused"] and second["ack_ref"] != first["ack_ref"]
        assert len(second["ack"]["new_assessment_ids"]) == 1 and len(second["ack"]["assessment_ids"]) == 7
        assert second["ack"]["prior_ack_ref"] == first["ack_ref"]
        assert second["ack"]["stopped_run"] == second["run"] and second["ack"]["stopped_finish"] == second["finish"]
        assert second["ack"]["held_failure"] == first["ack"]["held_failure"] == initial["held"]
        assert second["ack"]["deadline_epoch"] == initial["ack"]["deadline_epoch"]
        assert second_engine.ledger.get(first["finish"], chain.held.FINISH_KIND)["reason"] == "technical_stop"
        assert second_engine.ledger.get(second["finish"], chain.FINISH_KIND)["reason"] == "technical_stop"
        assert second_engine.ledger.get(first["ack_ref"], chain.ACK_KIND) == {key: value for key, value in first["ack"].items() if key != "id"}
        calls = len(transport.calls)
    finally:
        second_engine.close()
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 10_000_000_000, sleep=lambda _: pytest.fail("must not wait")))
    controller = fixture.DeadlineHarness(owner, config=Config(offline=False), transport=transport)
    controller.synthetic_history = initial["history"]
    try:
        args = {"plan": plan["id"], "ack_ref": second["ack_ref"], "allow_paid_execution": True}
        resumed = controller.execute("status", args, objective="Resume second finite chain at original deadline", actor="test:software")
        run_id = controller.fast_run
        again = controller.execute("status", args, objective="Reuse exact second-chain finish", actor="test:software")
        assert resumed["finished_reason"] == again["finished_reason"] == "deadline" and controller.fast_run == run_id
        run = controller.ledger.get(run_id, chain.RUN_KIND)
        assert run["ack_ref"] == second["ack_ref"] and run["prior_ack_ref"] == first["ack_ref"]
        assert run["deadline_epoch"] == initial["ack"]["deadline_epoch"]
        assert len(transport.calls) == calls
    finally:
        controller.close()
    future = RecursiveHarness(owner, config=Config(offline=False), transport=transport)
    future.synthetic_history = initial["history"]
    try:
        result = future.execute("status", {"plan": plan["id"], "ack_ref": second["ack_ref"], "later_failure": True},
            objective="Preserve the stop for a third unacknowledged fictional error", actor="test:software")
        assert result["blockers"] == ["prior_technical_or_unknown_assessment"] and result["budget_unchanged"]
        assert len(transport.calls) == calls
    finally:
        future.close()
