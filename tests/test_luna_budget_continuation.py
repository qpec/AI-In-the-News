"""Synthetic exact-proof continuation; original history and charges are retained."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path
import sys
import time

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, PricePolicy, UsageReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_continuation as runner
    import run_luna_budget_workflow as controller
    import luna_event_contract_v2 as contract
    from luna_batch_budget_run import save
    from luna_batch_results import parse_batch_results
    from luna_batch_phase_projection import project_final_answer_phase
finally:
    sys.path.pop(0)


def fields():
    proof = {"plan": "plan", "original_assessment": "assessment", "custom_id": "custom",
        "manifest": "manifest", "packet_ref": "packet", "request_body_ref": "request",
        "original_response": "response", "derived_status": "valid", "cost_status": "settled",
        "new_models": 0, "original_status_unchanged": True, "phase_implementation_sha256": "phase"}
    assessment = {"id": "assessment", "plan": "plan", "custom_id": "custom", "manifest": "manifest",
        "packet_ref": "packet", "request": "request", "response": "response", "status": "error",
        "errors": ["response:not_single_message"], "technical_failure": True, "model": "model"}
    entry = {"status": "settled", "accepted": True,
        "request": {"request_id": "custom", "plan_id": "plan", "request_sha256": "request",
                    "input_count": {"input_tokens": 100}, "max_output_tokens": 512},
        "settlement": {"complete": True, "model": "model", "input_tokens": 100, "output_tokens": 90}}
    return proof, assessment, entry


@pytest.mark.parametrize("target,key,value", [
    ("proof", "derived_status", "invalid"), ("proof", "original_status_unchanged", False),
    ("proof", "phase_implementation_sha256", "changed"), ("proof", "request_body_ref", "other"),
    ("assessment", "errors", ["response:refusal"]), ("assessment", "technical_failure", False),
    ("entry", "status", "unknown"), ("entry", "accepted", False),
])
def test_exact_proof_rejects_scope_status_identity_and_unknown_cost(target, key, value):
    proof, assessment, entry = fields()
    runner.validate_proof_fields("plan", proof, "assessment", assessment, entry, "phase")
    {"proof": proof, "assessment": assessment, "entry": entry}[target][key] = value
    with pytest.raises(AuditError):
        runner.validate_proof_fields("plan", proof, "assessment", assessment, entry, "phase")


def test_acknowledgment_never_matches_another_error_or_plan():
    _, assessment, _ = fields()
    ack = {"plan": "plan", "assessment": "assessment", "custom_id": "custom"}
    assert runner.acknowledged_assessment(assessment, ack)
    for changed in ({"id": "other"}, {"plan": "other"}, {"status": "invalid"}, {"errors": ["response:refusal"]}):
        assert not runner.acknowledged_assessment({**assessment, **changed}, ack)
    assert not runner.acknowledged_assessment(assessment, None)


class Seed(runner.ContinuationResearch):
    @audited_handler
    def _status(self, session, context, data):
        packet, final = contract.fictional_example()
        body = {"model": "gpt-6-luna", "max_output_tokens": 512}
        packet_ref, body_ref = save(self, session, packet, "Fictional packet"), save(self, session, body, "Fictional request")
        price = PricePolicy("gpt-6-luna", 100_000_000, 125_000_000, 500_000_000,
            (1, 2), (11, 10), (2, 1), (3, 2), 272_000, "https://example.invalid/price", "2026-10-17T00:00:00Z")
        plan = self.ledger.record(session, runner.PLAN_KIND, "fixture", {"authorization_id": runner.STUDY,
            "contract_sha256": contract.contract_digest(), "implementation": {}, "versions": {},
            "pending_requests": 1, "price_policy": asdict(price), "canary_tasks": [{"custom_id": "other-canary"}]})
        protocol = self._version(session, context, {"kind": "protocol", "key": "fictional",
            "content": {"method": "synthetic-only"}})["id"]
        task = {"packet": packet, "body": body}
        messages = [{"type": "message", "role": "assistant", "status": "completed", "phase": phase,
            "content": [{"type": "output_text", "text": text}]} for phase, text in
            (("commentary", "Preparing fictional JSON."), ("final_answer", canonical(final)))]
        raw = {"custom_id": "bulk-only", "error": None, "response": {"status_code": 200,
            "request_id": "fictional-request", "body": {"id": "fictional-response", "model": price.model,
                "status": "completed", "error": None, "incomplete_details": None,
                "usage": {"input_tokens": 100, "output_tokens": 90, "total_tokens": 190}, "output": messages}}}
        line = canonical(raw).encode()
        raw_ref = save(self, session, line + b"\n", "Fictional provider line")
        parsed = parse_batch_results(line + b"\n", None, {"bulk-only": task})["items"][0]
        response_ref = save(self, session, parsed, "Original rejected fictional response")
        projected = project_final_answer_phase(raw, task)
        projection_ref = save(self, session, projected, "Separate fictional phase derivation")
        manifest = self.ledger.record(session, "luna_budget_dispatch_manifest", "manifest", {
            "plan": plan, "phase": "bulk", "tasks": [{"custom_id": "bulk-only"}]})
        self.ledger.record(session, "luna_budget_provider_job", manifest,
            {"plan": plan, "manifest": manifest, "request_count": 1})
        self.ledger.record(session, "luna_budget_job_reconciled", manifest, {"plan": plan, "manifest": manifest})
        book = BudgetBook(price, runner.STUDY, ceiling_nanousd=150_000_000_000, operational_limit_nanousd=120_000_000_000)
        state = self.gateway.save_book(session, book)
        book.reserve(request_id="bulk-only", task_id="bulk-only", corpus_id="cybercrime", plan_id=plan,
            request_sha256=body_ref, input_count=InputTokenReceipt(100, price.model, body_ref, "a" * 64, "provider_responses_input_tokens"),
            max_output_tokens=512, price_fingerprint=price.fingerprint)
        book.settle("bulk-only", UsageReceipt(100, 90, price.model, body_ref, response_ref, True))
        state = self.gateway.save_book(session, book, state)
        assessment = self.ledger.record(session, runner.ASSESSMENT_KIND, "bulk-only", {
            "plan": plan, "custom_id": "bulk-only", "manifest": manifest, "packet_ref": packet_ref,
            "request": body_ref, "response": response_ref, "status": "error", "technical_failure": True,
            "errors": ["response:not_single_message"], "model": price.model})
        run = self.ledger.record(session, runner.RUN_KIND, plan, {"plan": plan, "protocol": protocol,
            "implementation": {"frozen-original": "unchanged"}, "deadline_epoch": time.time() + 3600,
            "max_runtime_seconds": 86400, "max_per_corpus": 250})
        stop = self.ledger.record(session, runner.FINISH_KIND, run, {"plan": plan, "run": run, "reason": "technical_stop"})
        proof = self.ledger.record(session, runner.PROOF_KIND, "fixture-proof", {"plan": plan, "protocol": protocol,
            "original_assessment": assessment, "custom_id": "bulk-only", "manifest": manifest,
            "packet_ref": packet_ref, "request_body_ref": body_ref, "original_response": response_ref,
            "provider_file_ref": raw_ref, "raw_line_sha256": hashlib.sha256(line).hexdigest(),
            "projection_ref": projection_ref, "derived_status": "valid", "derived_output": projected["assessment"]["result"],
            "phase_implementation_sha256": runner.code_hashes()["luna_batch_phase_projection.py"],
            "budget_state": state, "cost_status": "settled", "new_models": 0, "original_status_unchanged": True})
        return {"plan": plan, "proof": proof, "run": run, "stop": stop, "assessment": assessment, "budget_state": state}


def test_audited_registration_and_separate_controller_preserve_history_and_deadline(tmp_path, monkeypatch):
    owner = tmp_path / "protected"
    monkeypatch.setattr(runner, "OWNER", owner)
    monkeypatch.setattr(controller, "OWNER", owner)
    engine = Seed(owner, config=Config(offline=True))
    try:
        seeded = engine.execute("status", {}, objective="Seed fictional settled phase failure", actor="test:synthetic")
    finally:
        engine.close()
    engine = runner.ContinuationResearch(owner, config=Config(offline=True))
    try:
        original = {key: deepcopy(engine.ledger.get(seeded[key])) for key in ("run", "stop", "assessment")}
        result = engine.execute("status", {"plan": seeded["plan"], "proof": seeded["proof"]},
            objective="Register synthetic exact continuation", actor="test:synthetic")
        again = engine.execute("status", {"plan": seeded["plan"], "proof": seeded["proof"]},
            objective="Replay synthetic exact continuation", actor="test:synthetic")
        assert again["continuation_ref"] == result["continuation_ref"]
        for key in original:
            assert engine.ledger.get(seeded[key]) == original[key]
    finally:
        engine.close()
    engine = controller.ControlResearch(owner, config=Config(offline=True))
    try:
        status = engine.execute("status", {"plan": seeded["plan"], "continuation_ref": result["continuation_ref"]},
            objective="Check separate synthetic continuation controller", actor="test:synthetic")
        assert status["run"] != seeded["run"] and status["blockers"] == []
        assert status["deadline_epoch"] == original["run"]["deadline_epoch"]
        assert status["budget_state"] == seeded["budget_state"]
        assert status["status_counts"] == {"error": 1}
        assert engine.ledger.get(seeded["stop"])["reason"] == "technical_stop"
    finally:
        engine.close()
