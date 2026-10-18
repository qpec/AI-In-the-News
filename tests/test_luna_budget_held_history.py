"""Actual raw phase replay and real accounting; finite-proof delegation is spied."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, canonical
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, UsageReceipt

import test_diagnose_luna_budget_costs as metadata_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_held_history as history
    import luna_event_contract_v2 as contract
    from luna_batch_results import parse_batch_results
finally:
    sys.path.pop(0)


def fixture(monkeypatch):
    records = metadata_fixture.retained_history()
    values, byte_values = {}, {}
    def put(value):
        encoded = canonical(value).encode()
        reference = hashlib.sha256(encoded).hexdigest()
        values[reference], byte_values[reference] = deepcopy(value), encoded
        return reference
    def put_bytes(value):
        reference = hashlib.sha256(value).hexdigest()
        byte_values[reference] = value
        return reference
    packet, final = contract.fictional_example()
    body = {"model": "gpt-6-luna", "max_output_tokens": 4096}
    packet_ref, body_ref = put(packet), put(body)
    raw = {"custom_id": "phase-custom", "error": None, "response": {"status_code": 200,
        "request_id": "fictional-request", "body": {"id": "fictional-response", "model": "gpt-6-luna",
        "status": "completed", "error": None, "incomplete_details": None,
        "usage": {"input_tokens": 100, "output_tokens": 90, "total_tokens": 190},
        "output": [{"type": "message", "role": "assistant", "status": "completed", "phase": phase,
            "content": [{"type": "output_text", "text": text}]} for phase, text in
            (("commentary", "Preparing fictional response."), ("final_answer", canonical(final)))]}}}
    line = canonical(raw).encode()
    raw_ref = put_bytes(line + b"\n")
    parsed = parse_batch_results(line + b"\n", None, {"phase-custom": {"packet": packet, "body": body}})["items"][0]
    response_ref = put(parsed)
    projection = history.phase.project_final_answer_phase(raw, {"packet": packet, "body": body})
    projection_ref = put(projection)
    phase_hash = history.phase.code_hashes()["luna_batch_phase_projection.py"]
    records["phase-proof"].update(protocol="replay-protocol", original_response=response_ref,
        manifest="phase-manifest", packet_ref=packet_ref, request_body_ref=body_ref,
        provider_file_ref=raw_ref, raw_line_sha256=hashlib.sha256(line).hexdigest(), projection_ref=projection_ref,
        derived_output=projection["assessment"]["result"], phase_implementation_sha256=phase_hash,
        cost_status="settled", new_models=0, original_status_unchanged=True)
    records["3" * 64].update(manifest="phase-manifest", packet_ref=packet_ref, request=body_ref,
        response=response_ref, technical_failure=True, model="gpt-6-luna")
    records["phase"].update(phase_implementation_sha256=phase_hash)
    records["phase-protocol"]["content"] = {"method": "exact-settled-phase-error-continuation-v1", **records["phase"]}
    records["replay-protocol"] = {"content": {"method": "retained-final-answer-phase-replay-v1",
        "plan": "plan", "original_assessment": "3" * 64, "implementation": history.replay_implementation()}}
    records["first-run"].update(queue_token_cap=20_000_000, count_workers=16)
    records["ack"]["budget_state_at_ack"] = "old-clean-budget"
    records["old-diagnostic"] = {"plan": "plan", "budget_state": "old-clean-budget", "pending_jobs": 0,
        "budget_frozen": False, "technical_rows": [{"id": identifier} for identifier in records["ack"]["assessment_ids"]]}
    book = metadata_fixture.book_with("unknown")
    book.reserve(request_id="phase-custom", task_id="phase-custom", corpus_id="cybercrime", plan_id="plan",
        request_sha256=body_ref, input_count=InputTokenReceipt(100, "gpt-6-luna", body_ref, "d" * 64,
            "provider_responses_input_tokens"), max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
    book.settle("phase-custom", UsageReceipt(100, 90, "gpt-6-luna", body_ref, response_ref, True))
    events, verified = [], []
    engine = SimpleNamespace(_active={"s"}, ledger=SimpleNamespace(
        get=lambda key, *args: deepcopy(records[key]), append=lambda *args: events.append(args),
        artifacts=SimpleNamespace(read=lambda key: deepcopy(values[key]), read_bytes=lambda key: byte_values[key])),
        gateway=SimpleNamespace(load_book=lambda *args: (BudgetBook.from_dict(book.to_dict()), "current-budget")))
    def verify_failure(received_engine, session, plan_id, identifier, received_book):
        assert received_engine is engine and session == "s" and plan_id == "plan" and received_book is book
        verified.append(identifier)
        return deepcopy(next(proof for proof in records["ack"]["failures"] if proof["assessment"] == identifier))
    monkeypatch.setattr(history.failure, "verify_failure", verify_failure)
    return engine, book, records, values, byte_values, events, verified


def test_raw_phase_replay_preserves_unrelated_unknown_real_book_and_original_deadline(monkeypatch):
    engine, book, records, _, _, events, verified = fixture(monkeypatch)
    before = deepcopy(book.to_dict())
    def forbidden(*args, **kwargs):
        raise AssertionError("Current inference admission must remain the caller's separate decision")
    monkeypatch.setattr(history.phase, "load_continuation", forbidden)
    monkeypatch.setattr(history.failure, "load_failure_ack", forbidden)
    monkeypatch.setattr(history.failure, "known_budget", forbidden)
    acknowledgment, phase = history.verify_history(engine, "s", "plan", "ack", book)
    assert acknowledgment == {**records["ack"], "id": "ack"}
    assert phase == {**records["phase"], "id": "phase"} and phase["deadline_epoch"] == 100
    assert verified == ["1" * 64, "2" * 64]
    assert book.to_dict() == before and book.entry("fictional")["status"] == "unknown"
    assert book.entry("fictional")["reserved_nanousd"] > 0
    assert events[-1][2]["admission_granted"] is False


def test_requires_active_session(monkeypatch):
    engine, book, *_ = fixture(monkeypatch)
    with pytest.raises(AuditError, match="active audited"):
        history.verify_history(engine, "inactive", "plan", "ack", book)


def test_rejects_different_or_fake_current_book_before_any_proof(monkeypatch):
    engine, book, _, _, _, _, verified = fixture(monkeypatch)
    with pytest.raises(AuditError, match="real_current"):
        history.verify_history(engine, "s", "plan", "ack", SimpleNamespace())
    other = metadata_fixture.book_with("reserved")
    with pytest.raises(AuditError, match="snapshot_mismatch"):
        history.verify_history(engine, "s", "plan", "ack", other)
    assert verified == []


@pytest.mark.parametrize("reference,key,value", [
    ("ack", "implementation", {}), ("phase", "implementation", {}),
    ("phase", "deadline_epoch", 101), ("first-run", "deadline_epoch", 101),
    ("first-run", "count_workers", 15), ("first-finish", "reason", "complete"),
    ("phase-stop", "reason", "complete"), ("old-diagnostic", "budget_state", "changed"),
    ("old-diagnostic", "pending_jobs", 1), ("phase-proof", "cost_status", "unknown"),
    ("phase-proof", "derived_output", {}), ("phase-proof", "raw_line_sha256", "0" * 64),
    ("3" * 64, "model", "wrong-model")])
def test_changed_history_or_raw_proof_rejected(monkeypatch, reference, key, value):
    engine, book, records, *_ = fixture(monkeypatch)
    records[reference][key] = value
    with pytest.raises(AuditError):
        history.verify_history(engine, "s", "plan", "ack", book)


@pytest.mark.parametrize("reference", ["replay-protocol", "phase-protocol", "ack-protocol"])
def test_protocol_hash_or_method_change_is_rejected(monkeypatch, reference):
    engine, book, records, *_ = fixture(monkeypatch)
    records[reference]["content"]["implementation"] = {}
    with pytest.raises(AuditError):
        history.verify_history(engine, "s", "plan", "ack", book)


def test_duplicate_raw_phase_line_is_rejected(monkeypatch):
    engine, book, records, _, byte_values, *_ = fixture(monkeypatch)
    reference = records["phase-proof"]["provider_file_ref"]
    byte_values[reference] *= 2
    with pytest.raises(AuditError, match="not_unique"):
        history.verify_history(engine, "s", "plan", "ack", book)


def test_original_finite_raw_proof_failure_propagates(monkeypatch):
    engine, book, *_ = fixture(monkeypatch)
    def rejected(*args):
        raise AuditError("failure_ack_retained_parser_result_changed")
    monkeypatch.setattr(history.failure, "verify_failure", rejected)
    with pytest.raises(AuditError, match="retained_parser_result_changed"):
        history.verify_history(engine, "s", "plan", "ack", book)


def test_budget_change_during_proof_is_rejected(monkeypatch):
    engine, book, *_ = fixture(monkeypatch)
    original = engine.gateway.load_book
    calls = 0
    def changed(*args):
        nonlocal calls
        calls += 1
        loaded, state = original(*args)
        return loaded, state if calls == 1 else "changed-state"
    engine.gateway.load_book = changed
    with pytest.raises(AuditError, match="budget_changed"):
        history.verify_history(engine, "s", "plan", "ack", book)
