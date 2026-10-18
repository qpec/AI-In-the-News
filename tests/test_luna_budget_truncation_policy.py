"""Ongoing policy on synthetic raw responses and a real temporary ledger."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from newsresearch.common import AuditError, Config, Context, Json, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt
from newsresearch.runtime import audited_handler

import test_luna_budget_held_chain_recursive as recursive
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_truncation_policy as policy
finally:
    sys.path.pop(0)

fixture, chain, runner = recursive.fixture, recursive.chain, recursive.runner
old = recursive.old


class FutureTransport(recursive.RecursiveTransport):
    def __init__(self, future_mode: str = "truncation") -> None:
        super().__init__()
        self.future_mode = future_mode

    def result_bytes(self, job_id: str) -> bytes:
        rows = [json.loads(line) for line in super().result_bytes(job_id).splitlines()]
        if job_id == "batch_8":
            body = rows[0]["response"]["body"]
            if self.future_mode == "refusal":
                body.update(status="completed", incomplete_details=None,
                    output=[{"type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "refusal", "refusal": "Synthetic refusal remains unqualified."}]}])
                body["usage"].update(output_tokens=12, total_tokens=4027)
            elif self.future_mode == "unknown":
                body["usage"] = None
            elif self.future_mode == "wrong_model":
                body["model"] = "synthetic-wrong-model"
        return b"".join(canonical(row).encode() + b"\n" for row in rows)


def prepared_policy_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                          future_mode: str = "truncation") -> tuple[Path, Json, FutureTransport, Json, Json]:
    """Real held+two finite generations; two untouched future requests remain."""
    fast_fixture = old.fixture.fast_fixture
    wave = fast_fixture.bulk.wave
    original_export = wave.fixture_module.synthetic_export
    monkeypatch.setattr(wave.fixture_module, "synthetic_export", lambda root, corpus: original_export(root, corpus, count=12))
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    seed = wave.SeededWaveResearch(owner)
    try:
        seed.execute("status", {"seed": True, "plan": plan["id"]}, objective="Seed synthetic canary accounting", actor="test:software")
        seed.execute("status", {"plan": plan["id"], "max_per_corpus": 1}, objective="Stage first synthetic wave", actor="test:software")
    finally:
        seed.close()
    transport = FutureTransport(future_mode)
    submitter = fast_fixture.DispatchHarness(owner, config=Config(offline=False), transport=transport)
    try:
        fast_fixture.execute(submitter, plan)
    finally:
        submitter.close()
    # The older phase/two-settled history helper is independently tested; every
    # held/raw/count/dispatch/proof and each later generation here is real.
    def historical(engine: Any, *args: Any) -> Any:
        engine.historical_replays = getattr(engine, "historical_replays", 0) + 1
        return engine.synthetic_history
    monkeypatch.setattr(chain.held, "verify_history", historical)
    engine = old.HeldHarness(owner, config=Config(offline=False), transport=transport)
    try:
        initial = engine.execute("status", {"plan": plan["id"], "register": True}, objective="Retain synthetic held baseline", actor="test:software")
    finally:
        engine.close()
    monkeypatch.setattr(runner.fast, "read_partition", wave.runner.read_partition)
    choose = runner.fast.choose_next
    monkeypatch.setattr(runner.fast, "choose_next", lambda queue, manifested, limit: choose(queue, manifested, 1))
    first = fixture.ChainHarness(owner, config=Config(offline=False), transport=transport)
    first.synthetic_history = initial["history"]
    try:
        generation = first.execute("status", {"plan": plan["id"], "prior_ack_ref": initial["ack_ref"]},
            objective="Retain first synthetic finite generation", actor="test:software")
    finally:
        first.close()
    second = recursive.RecursiveHarness(owner, config=Config(offline=False), transport=transport)
    second.synthetic_history = initial["history"]
    try:
        baseline = second.execute("status", {"plan": plan["id"], "prior_ack_ref": generation["ack_ref"]},
            objective="Retain exact one-failure baseline diagnostic", actor="test:software")
    finally:
        second.close()
    return owner, plan, transport, initial, baseline


class PolicyHarness(runner.HeldChainRecoveryResearch):
    saved_verified: policy.VerifiedPolicy

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        if data.get("policy_ref"):
            if data.get("stale_context"):
                book, _ = self.gateway.load_book(session, chain.STUDY)
                with pytest.raises(AuditError, match="same_session"):
                    policy.classify_failures(self, session, self.saved_verified, self.view(session, plan_id)["assessments"], book)
            verified = policy.load_policy(self, session, plan_id, data["policy_ref"])
        else:
            registered = policy.register_policy(self, session, context, data)
            before_load = self.historical_replays
            verified = policy.load_policy(self, session, plan_id, registered["policy_ref"])
            assert self.historical_replays == before_load  # No second startup replay.
        self.saved_verified = verified
        before_classification = self.historical_replays
        baseline = verified.baseline
        copy = verified.baseline
        copy["held_failure"]["entry"]["reserved_nanousd"] = 0
        assert verified.baseline["held_failure"]["entry"]["reserved_nanousd"] == 1_402_432
        self.failure_ack = baseline
        plan = self.ledger.get(plan_id, chain.base.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        api_policy, book, state = self.authorization(session, context, plan_id, plan)
        if data.get("dispatch"):
            self.fast_run = "fictional-throughput-run"
            view = self.view(session, plan_id)
            snapshot = runner.fast.core.load_contract_snapshot()
            self.stage(session, plan_id, plan, view, state, snapshot)
            submitted = {row["manifest"] for row in view["jobs"]}
            for manifest in view["manifests"]:
                if manifest["id"] in submitted or manifest["phase"] != "bulk":
                    continue
                raw = runner.fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, snapshot)
                book, state, pressure, job = self.dispatch(session, plan_id, plan, api_policy, book, state, manifest, raw,
                    active_tokens=0, queue_cap=baseline["queue_token_cap"], workers=2, deadline=baseline["deadline_epoch"])
                assert pressure is None and job
            self.result_parser = chain.base.parse_batch_results_phase_aware
            self.parser_mode = "explicit-final-answer-phase-v1"
            for job in self.view(session, plan_id)["jobs"]:
                self.reconcile(session, plan_id, api_policy, job)
        book, state = self.gateway.load_book(session, chain.STUDY)
        view = self.view(session, plan_id)
        proof_reads = len(self.raw_proof_reads)
        if self.transport.future_mode in {"unknown", "wrong_model"}:
            with pytest.raises(AuditError, match="new_or_changed_unknown|frozen_or_exceeded"):
                policy.classify_failures(self, session, verified, view["assessments"], book)
            assert self.historical_replays == before_classification and len(self.raw_proof_reads) == proof_reads
            assert not chain.base._rows(self, session, policy.PROOF_KIND, plan_id)
            return {"blocked": True, "book_frozen": book.frozen, "held": book.entry(baseline["held_failure"]["custom_id"])}
        first = policy.classify_failures(self, session, verified, view["assessments"], book)
        raw_reads = len(self.raw_proof_reads) - proof_reads
        second = policy.classify_failures(self, session, verified, view["assessments"], book)
        assert len(self.raw_proof_reads) - proof_reads == raw_reads
        assert self.historical_replays == before_classification
        assert first["proof_record_ids"] == second["proof_record_ids"]
        assert second["new_proof_record_ids"] == []
        self.failure_ack = first["acknowledgment"]
        blockers = self.check_gate(session, plan_id, plan, view, book, baseline["phase"])
        assert blockers == (["prior_technical_or_unknown_assessment"] if self.transport.future_mode == "refusal" else [])
        assert book.entry(baseline["held_failure"]["custom_id"]) == baseline["held_failure"]["entry"]
        assert self.gateway.load_book(session, chain.STUDY)[1] == state
        if data.get("tamper"):
            candidate = next(row for row in view["assessments"] if row["id"] in verified._cache)
            changed = [{**row, "usage": {}} if row["id"] == candidate["id"] else row for row in view["assessments"]]
            with pytest.raises(AuditError, match="current_assessment_changed"):
                policy.classify_failures(self, session, verified, changed, book)
            original = verified._cache[candidate["id"]]
            fingerprint, reference, proof = original
            verified._cache[candidate["id"]] = (fingerprint, reference, {**proof, "charged_nanousd": proof["charged_nanousd"] + 1})
            with pytest.raises(AuditError, match="cached_evidence_or_entry_changed"):
                policy.classify_failures(self, session, verified, view["assessments"], book)
            verified._cache[candidate["id"]] = original
            fake = BudgetBook.from_dict(book.to_dict())
            fake.reserve(request_id="fake", task_id="fake", corpus_id="cybercrime", plan_id=plan_id,
                request_sha256="a" * 64, input_count=InputTokenReceipt(1, "gpt-6-luna", "a" * 64, "b" * 64,
                    "provider_responses_input_tokens"), max_output_tokens=4096, price_fingerprint=fake.price_policy.fingerprint)
            with pytest.raises(AuditError, match="real_current_shared_book"):
                policy.classify_failures(self, session, verified, view["assessments"], fake)
        return {"policy_ref": verified.policy_ref, "first": first, "second": second, "raw_proof_reads": raw_reads,
            "held": book.entry(baseline["held_failure"]["custom_id"]), "blockers": blockers, "calls": len(self.transport.calls)}


@pytest.mark.parametrize("future_mode", ["truncation", "refusal", "unknown", "wrong_model"])
def test_only_independently_proved_settled_cap_failures_avoid_global_stop(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, future_mode: str) -> None:
    owner, plan, transport, initial, baseline = prepared_policy_owner(tmp_path, monkeypatch, future_mode)
    original_verify = chain.base.verify_failure
    def counted(engine: Any, *args: Any) -> Json:
        engine.raw_proof_reads.append(args[2])
        return dict(original_verify(engine, *args))
    monkeypatch.setattr(chain.base, "verify_failure", counted)
    engine = PolicyHarness(owner, config=Config(offline=False), transport=transport)
    engine.synthetic_history = initial["history"]
    engine.raw_proof_reads = []
    ack = baseline["ack"]
    arguments = {key: ack[key] for key in ("plan", "prior_ack_ref", "stop_result_ref", "diagnostic_ref")}
    arguments.update(assessment_ids=ack["new_assessment_ids"], dispatch=True, tamper=future_mode == "truncation")
    try:
        result = engine.execute("status", arguments, objective="Test explicit synthetic ongoing truncation policy", actor="test:software")
        assert result["held"] == initial["held"]["entry"] and result["held"]["reserved_nanousd"] == 1_402_432
        if future_mode in {"unknown", "wrong_model"}:
            assert result["blocked"]
            return
        expected = 1 if future_mode == "refusal" else 2
        assert result["raw_proof_reads"] == expected and len(result["first"]["new_proof_record_ids"]) == expected
        assert len(result["first"]["unqualified_failures"]) == (1 if future_mode == "refusal" else 0)
        calls = len(transport.calls)
        # New execute session: old sealed context is unusable. Durable proofs
        # replay their raw files once, then become the new session's exact cache.
        resumed = engine.execute("status", {"plan": plan["id"], "policy_ref": result["policy_ref"], "stale_context": True},
            objective="Test cross-session proof replay without model retry", actor="test:software")
        assert resumed["raw_proof_reads"] == expected and resumed["first"]["new_proof_record_ids"] == []
        assert resumed["first"]["proof_record_ids"] == result["first"]["proof_record_ids"]
        assert len(transport.calls) == calls
    finally:
        engine.close()


def test_same_session_context_is_required_before_any_book_read() -> None:
    engine = SimpleNamespace(_active={"new-session"})
    context = policy.VerifiedPolicy("ref", id(engine), "old-session", canonical({}), "hash", object())
    # Active-session enforcement is an independent runtime prerequisite; the
    # context guard additionally prevents crossing sessions in the integration.
    with pytest.raises(AuditError):
        policy.classify_failures(engine, "new-session", context, [], None)
