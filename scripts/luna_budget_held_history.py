"""Reverify historical evidence without granting current cost admission.

The caller supplies the real current BudgetBook and must separately enforce its
registered finite held-cost policy. This helper never sends, settles, reserves,
releases, accepts an extraction, or invokes an inference-admission loader.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from newsresearch.common import AuditError, Json, require_active
from newsresearch.event_batch_budget import BudgetBook

from luna_batch_budget_run import ROOT, STUDY
import luna_budget_continuation as phase
import luna_budget_failure_ack as failure

METHOD = "luna-budget-historical-proof-only-v1"


def replay_implementation() -> dict[str, str]:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
        "scripts/replay_luna_budget_phase.py", "scripts/luna_batch_phase_projection.py",
        "scripts/luna_batch_results.py", "scripts/luna_event_contract_v2.py")}


def verify_history(engine: Any, session: str, plan_id: str, prior_ack_ref: str,
                   book: BudgetBook) -> tuple[Json, Json]:
    """Return exact old ack/phase records with IDs; confer no admission permission."""
    require_active(engine, session)
    if not isinstance(book, BudgetBook):
        raise AuditError("held_history_real_current_budget_required")
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None or saved[0].to_dict() != book.to_dict():
        raise AuditError("held_history_current_budget_snapshot_mismatch")
    snapshot, state = book.to_dict(), saved[1]
    if (book.authorization_id != STUDY or book.ceiling_nanousd != 150_000_000_000
            or book.operational_limit_nanousd != 120_000_000_000):
        raise AuditError("held_history_original_budget_binding_changed")
    engine.ledger.append(session, "budget.held_history.inspection.intended", {
        "method": METHOD, "implementation_sha256": hashlib.sha256((ROOT / "scripts/luna_budget_held_history.py").read_bytes()).hexdigest(),
        "plan": plan_id, "prior_ack_ref": prior_ack_ref, "current_budget_state": state,
        "scope": "Exact historical phase and finite-failure evidence/protocols/stops/deadlines; no current admission granted"})
    acknowledgment = engine.ledger.get(prior_ack_ref, failure.ACK_KIND)
    if (acknowledgment.get("plan") != plan_id or acknowledgment.get("authorization_id") != STUDY
            or acknowledgment.get("implementation") != failure.implementation_hashes()
            or failure.exact_ids(acknowledgment.get("assessment_ids")) != sorted(proof["assessment"] for proof in acknowledgment["failures"])):
        raise AuditError("held_history_failure_ack_binding_changed")
    ack_protocol = engine.ledger.get(acknowledgment["protocol"], "protocol")["content"]
    if (ack_protocol.get("method") != failure.METHOD
            or ack_protocol.get("implementation") != acknowledgment["implementation"]
            or any(ack_protocol.get(key) != acknowledgment[key] for key in
                ("plan", "assessment_ids", "diagnostic_ref", "original_run", "original_finish"))):
        raise AuditError("held_history_failure_protocol_changed")
    phase_ref = acknowledgment["phase_continuation_ref"]
    continuation = engine.ledger.get(phase_ref, phase.CONTINUATION_KIND)
    if (continuation.get("plan") != plan_id or continuation.get("authorization_id") != STUDY
            or continuation.get("implementation") != phase.code_hashes()):
        raise AuditError("held_history_phase_binding_changed")
    phase_protocol = engine.ledger.get(continuation["protocol"], "protocol")["content"]
    if (phase_protocol.get("method") != "exact-settled-phase-error-continuation-v1"
            or phase_protocol.get("implementation") != continuation["implementation"]
            or any(phase_protocol.get(key) != continuation[key] for key in ("plan", "proof", "original_run", "original_stop"))):
        raise AuditError("held_history_phase_protocol_changed")
    proof = engine.ledger.get(continuation["proof"], phase.PROOF_KIND)
    assessment_id = proof["original_assessment"]
    assessment = engine.ledger.get(assessment_id, phase.ASSESSMENT_KIND)
    entry = book.entry(proof["custom_id"])
    phase_hash = phase.code_hashes()["luna_batch_phase_projection.py"]
    phase.validate_proof_fields(plan_id, proof, assessment_id, assessment, entry, phase_hash)
    if (continuation.get("assessment") != assessment_id or continuation.get("custom_id") != proof["custom_id"]
            or continuation.get("phase_implementation_sha256") != phase_hash
            or entry.get("reserved_nanousd") != 0
            or entry["settlement"].get("receipt_sha256") != proof["original_response"]
            or entry["settlement"].get("request_sha256") != proof["request_body_ref"]):
        raise AuditError("held_history_phase_exact_settlement_changed")
    proof_protocol = engine.ledger.get(proof["protocol"], "protocol")["content"]
    if (proof_protocol.get("method") != "retained-final-answer-phase-replay-v1"
            or proof_protocol.get("plan") != plan_id or proof_protocol.get("original_assessment") != assessment_id
            or proof_protocol.get("implementation") != replay_implementation()):
        raise AuditError("held_history_replay_protocol_changed")
    engine.ledger.append(session, "budget.held_history.phase_evidence.inspection.intended", {
        "proof": continuation["proof"], "assessment": assessment_id,
        "artifacts": [proof[key] for key in ("original_response", "provider_file_ref", "packet_ref", "request_body_ref", "projection_ref")],
        "purpose": "Exact original raw-line replay under unchanged phase and literal contracts"})
    original = engine.ledger.artifacts.read(proof["original_response"])
    if (original.get("usage_complete") is not True or original.get("errors") != ["response:not_single_message"]
            or original.get("observed_model") != book.price_policy.model):
        raise AuditError("held_history_original_phase_response_changed")
    raw = engine.ledger.artifacts.read_bytes(proof["provider_file_ref"])
    lines = [line for line in raw.splitlines() if hashlib.sha256(line).hexdigest() == proof["raw_line_sha256"]]
    if len(lines) != 1:
        raise AuditError("held_history_exact_phase_line_not_unique")
    row = json.loads(lines[0])
    if row.get("custom_id") != proof["custom_id"]:
        raise AuditError("held_history_phase_custom_id_changed")
    task = {"packet": engine.ledger.artifacts.read(proof["packet_ref"]),
        "body": engine.ledger.artifacts.read(proof["request_body_ref"])}
    projection = phase.project_final_answer_phase(row, task)
    if (projection != engine.ledger.artifacts.read(proof["projection_ref"])
            or projection.get("valid") is not True or projection.get("assessment", {}).get("status") != "valid"
            or projection["assessment"].get("result") != proof.get("derived_output")
            or projection["assessment"].get("usage") != original.get("usage")
            or any(entry["settlement"].get(key) != original.get("usage", {}).get(key) for key in ("input_tokens", "output_tokens"))):
        raise AuditError("held_history_phase_replay_changed")
    original_run = engine.ledger.get(continuation["original_run"], phase.RUN_KIND)
    original_stop = engine.ledger.get(continuation["original_stop"], phase.FINISH_KIND)
    if (original_run.get("plan") != plan_id or original_stop.get("plan") != plan_id
            or original_stop.get("run") != continuation["original_run"] or original_stop.get("reason") != "technical_stop"
            or any(continuation[key] != original_run.get(key) for key in ("deadline_epoch", "max_per_corpus", "max_runtime_seconds"))):
        raise AuditError("held_history_phase_stop_or_deadline_changed")
    fast_run = engine.ledger.get(acknowledgment["original_run"], failure.fast.RUN_KIND)
    fast_stop = engine.ledger.get(acknowledgment["original_finish"], failure.fast.FINISH_KIND)
    if (fast_run.get("plan") != plan_id or fast_run.get("authorization_id") != STUDY
            or fast_run.get("continuation_ref") != phase_ref
            or fast_run.get("implementation") != failure.fast.implementation_hashes()
            or fast_stop.get("plan") != plan_id or fast_stop.get("run") != acknowledgment["original_run"]
            or fast_stop.get("reason") != "technical_stop"
            or acknowledgment["deadline_epoch"] != continuation["deadline_epoch"]
            or fast_run.get("deadline_epoch") != continuation["deadline_epoch"]
            or any(acknowledgment.get(key) != fast_run.get(key) for key in ("queue_token_cap", "count_workers"))):
        raise AuditError("held_history_fast_stop_or_schedule_changed")
    diagnostic = engine.ledger.get(acknowledgment["diagnostic_ref"], failure.DIAGNOSTIC_KIND)
    if (diagnostic.get("plan") != plan_id or diagnostic.get("budget_state") != acknowledgment["budget_state_at_ack"]
            or diagnostic.get("pending_jobs") != 0 or diagnostic.get("budget_frozen") is not False
            or not set(acknowledgment["assessment_ids"]) <= {item["id"] for item in diagnostic["technical_rows"]}):
        raise AuditError("held_history_original_diagnostic_changed")
    verified = [failure.verify_failure(engine, session, plan_id, identifier, book)
        for identifier in acknowledgment["assessment_ids"]]
    if verified != acknowledgment["failures"]:
        raise AuditError("held_history_original_failure_proofs_changed")
    latest = engine.gateway.load_book(session, STUDY)
    if book.to_dict() != snapshot or latest is None or latest[1] != state or latest[0].to_dict() != snapshot:
        raise AuditError("held_history_budget_changed_during_verification")
    engine.ledger.append(session, "budget.held_history.verified", {
        "method": METHOD, "plan": plan_id, "prior_ack_ref": prior_ack_ref, "phase_ref": phase_ref,
        "current_budget_state": state, "budget_unchanged": True, "admission_granted": False,
        "original_deadline_epoch": continuation["deadline_epoch"], "new_models": 0})
    return {**acknowledgment, "id": prior_ack_ref}, {**continuation, "id": phase_ref}
