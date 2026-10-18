"""Versioned ongoing policy for fully accounted output-cap failures only.

This policy never repairs an extraction. Raw errors remain errors. The original
unknown liability stays fully held, and every other new anomaly still blocks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from newsresearch.common import AuditError, Context, Json, canonical, digest, require_active
from newsresearch.event_batch_budget import BudgetBook
from newsresearch.runtime import audited_handler

import luna_budget_held_chain as chain
from luna_batch_budget_run import ROOT, STUDY, present

POLICY_KIND = "luna_budget_settled_truncation_policy"
PROOF_KIND = "luna_budget_settled_truncation_policy_proof"
METHOD = "retained-failed-settled-output-cap-throughput-v1"
USER_AMENDMENT = "Fix and do it now. Ensure maximum speed. Remove blocks"
INTERPRETATION = ("After exact baseline diagnostic/proof verification, a newly observed HTTP200 gpt-6-luna terminal "
    "max_output_tokens truncation at the unchanged 4096 cap may remain failed without globally stopping unrelated "
    "untouched requests, only after independent retained raw evidence, exact observed usage and final settlement proof. "
    "Never retry, accept, reword or reroute failed work. Preserve the original full unknown hold, USD120 operational/" 
    "USD150 maximum, same owner/plan/original deadline, exact full-text inputs and shared gateway. Every other new "
    "unknown/frozen/overrun, ambiguous dispatch, unqualified technical failure or audit fault stops admission.")
_SEAL = object()


def implementation_hashes() -> dict[str, str]:
    result = chain.implementation_hashes()
    path = "scripts/luna_budget_truncation_policy.py"
    result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def proof_fingerprint() -> str:
    """Small hot-path fingerprint; full predecessor code is verified at load."""
    names = ("scripts/luna_budget_truncation_policy.py", "scripts/luna_budget_failure_ack.py",
        "scripts/luna_batch_phase_projection.py", "scripts/luna_batch_results.py", "scripts/luna_event_contract_v2.py",
        "scripts/luna_budget_held_cost.py", "src/newsresearch/event_batch_budget.py")
    return digest({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names})


@dataclass(frozen=True)
class VerifiedPolicy:
    """Immutable baseline with a private, same-engine/session proof cache."""
    policy_ref: str
    _engine_id: int
    _session: str
    _serialized: str
    _fingerprint: str
    _seal: object
    _cache: dict[str, tuple[str, str, Json]] = field(default_factory=dict, repr=False, compare=False)

    @property
    def value(self) -> Json:
        return dict(json.loads(self._serialized))

    @property
    def baseline(self) -> Json:
        return dict(self.value["baseline"])


def _real_book(engine: Any, session: str, plan_id: str, baseline: Json, book: BudgetBook | None = None) -> tuple[BudgetBook, str]:
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None or (book is not None and (not isinstance(book, BudgetBook) or saved[0].to_dict() != book.to_dict())):
        raise AuditError("truncation_policy_real_current_shared_book_required")
    current, state = saved
    chain.held.validate_book(current, plan_id, engine.ledger.get(plan_id, chain.base.PLAN_KIND), baseline["held_failure"])
    if engine.latest(chain.base.STOP_KIND, STUDY):
        raise AuditError("truncation_policy_gateway_stop_preserved")
    return current, state


def load_policy(engine: Any, session: str, plan_id: str, policy_ref: str) -> VerifiedPolicy:
    """Full historical replay once per locked runtime session, never per cycle."""
    require_active(engine, session)
    engine.ledger.append(session, "budget.truncation_policy.load.intended", {
        "plan": plan_id, "policy_ref": policy_ref, "scope": "Historical proof replay and immutable session binding; no inference"})
    value = engine.ledger.get(policy_ref, POLICY_KIND)
    cached = getattr(engine, "_verified_truncation_policy", None)
    if (isinstance(cached, VerifiedPolicy) and cached._seal is _SEAL
            and cached.policy_ref == policy_ref and cached._engine_id == id(engine) and cached._session == session):
        if (cached._serialized != canonical(value) or value.get("plan") != plan_id
                or cached._fingerprint != proof_fingerprint()):
            raise AuditError("truncation_policy_same_session_registered_value_changed")
        _real_book(engine, session, plan_id, cached.baseline)
        engine.ledger.append(session, "budget.truncation_policy.session_reuse", {
            "plan": plan_id, "policy_ref": policy_ref, "raw_history_replayed_again": False,
            "retained_policy_and_code_unchanged": True, "current_real_book_checked": True})
        return cached
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("method") != METHOD or value.get("implementation") != implementation_hashes()
            or value.get("user_amendment") != USER_AMENDMENT or value.get("interpretation") != INTERPRETATION
            or value.get("paid_retries") != 0 or value.get("unknown_cost_released") is not False
            or value.get("accepted_events") != 0
            or protocol.get("method") != METHOD or protocol.get("implementation") != value["implementation"]
            or any(protocol.get(key) != value[key] for key in ("plan", "inputs", "user_amendment", "interpretation"))):
        raise AuditError("truncation_policy_exact_registered_amendment_required")
    baseline = chain.load_history(engine, session, plan_id, value["baseline_ack_ref"])
    expected = {key: value["inputs"][key] for key in chain.INPUTS}
    if (any(baseline.get(key) != item for key, item in expected.items())
            or value.get("baseline") != baseline
            or any(value.get(key) != baseline[key] for key in chain.held.chain.INHERITED)):
        raise AuditError("truncation_policy_baseline_history_or_deadline_changed")
    _real_book(engine, session, plan_id, baseline)
    return _seal_policy(engine, session, policy_ref, value)


def _seal_policy(engine: Any, session: str, policy_ref: str, value: Json) -> VerifiedPolicy:
    result = VerifiedPolicy(policy_ref, id(engine), session, canonical(value), proof_fingerprint(), _SEAL)
    engine._verified_truncation_policy = result
    return result


@audited_handler
def register_policy(engine: Any, session: str, context: Context, data: Json) -> Json:
    """One explicit baseline registration; no network or paid retry is performed."""
    plan_id = data["plan"]
    inputs = {key: data[key] for key in chain.INPUTS if key != "new_assessment_ids"}
    inputs["new_assessment_ids"] = chain.held.chain.finite_ids(data.get("assessment_ids"))
    key = plan_id + ":" + inputs["stop_result_ref"] + ":" + METHOD
    existing = engine.latest(POLICY_KIND, key)
    if existing:
        if existing[1].get("inputs") != inputs:
            raise AuditError("truncation_policy_existing_inputs_changed")
        verified = load_policy(engine, session, plan_id, existing[0])
        return _registration(engine, session, verified.policy_ref, verified.value, reused=True)
    plan = engine.ledger.get(plan_id, chain.base.PLAN_KIND)
    protocol = engine._version(session, context, {"kind": "protocol", "key": STUDY + ":settled-truncation-throughput",
        "content": {"method": METHOD, "plan": plan_id, "inputs": inputs, "versions": plan["versions"],
            "implementation": implementation_hashes(), "user_amendment": USER_AMENDMENT,
            "interpretation": INTERPRETATION, "amendment_source": "explicit user instruction in the current chat"},
        "amend_latest": True, "reason": "User requested removal of avoidable throughput stops; preserve all audit and monetary safeguards"})["id"]
    # This unchanged finite method independently binds the exact latest stop,
    # drained diagnostic and complete current failed-ID set before our new rule.
    registered = chain.HeldChainAcknowledgmentResearch.register_acknowledgment(engine, session, context, data)
    # The unchanged audited registration just verified this exact immutable
    # acknowledgment (including its existing-record reuse path). Do not replay
    # that full predecessor a second time in the same locked operation.
    baseline = {**engine.ledger.get(registered["ack_ref"], chain.ACK_KIND), "id": registered["ack_ref"]}
    book, state = _real_book(engine, session, plan_id, baseline)
    value = {"method": METHOD, "plan": plan_id, "authorization_id": STUDY, "protocol": protocol,
        "inputs": inputs, "baseline_ack_ref": baseline["id"], "baseline_registration": registered["id"],
        "baseline": baseline, **{key: baseline[key] for key in chain.held.chain.INHERITED},
        "implementation": implementation_hashes(), "user_amendment": USER_AMENDMENT, "interpretation": INTERPRETATION,
        "budget_state_at_registration": state, "original_held_nanousd": book.entry(baseline["held_failure"]["custom_id"])["reserved_nanousd"],
        "paid_retries": 0, "unknown_cost_released": False, "accepted_events": 0, "new_models": 0,
        "approved_by": "user:current-chat", "raw_failures_and_stops_unchanged": True}
    reference = engine.ledger.record(session, POLICY_KIND, key, value)
    _seal_policy(engine, session, reference, value)
    return _registration(engine, session, reference, value, reused=False)


def _registration(engine: Any, session: str, reference: str, value: Json, *, reused: bool) -> Json:
    return present(engine, session, "luna_budget_truncation_policy_registration", {
        "policy_ref": reference, **value, "reused": reused},
        f"{'Reused' if reused else 'Registered'} the explicit throughput amendment after verifying the exact baseline diagnostic. "
        "Only independently proved, fully settled 4096-token truncations may remain failed without stopping untouched requests. "
        f"The original unknown liability remains fully reserved at ${value['original_held_nanousd']/1e9:.9f}. "
        "Every other new technical/unknown/frozen/ambiguous/audit failure still stops. Raw statuses, stops, full-text inputs, "
        "original deadline, USD120 operating/USD150 maximum and no-retry rule are unchanged. Zero provider calls in registration. "
        "Exact protected presentation retained; record_presentation does not support this technical kind.")


def _candidate(row: Json, entry: Json) -> bool:
    usage = row.get("usage")
    return bool(row.get("status") == "error" and row.get("technical_failure") is True
        and row.get("errors") == ["response:not_completed"] and row.get("model") == "gpt-6-luna"
        and row.get("missing") is False and row.get("accepted") is False and row.get("human_validated") is False
        and row.get("output") is None and isinstance(usage, dict) and usage.get("output_tokens") == 4096
        and entry.get("status") == "settled" and entry.get("accepted") is True and entry.get("reserved_nanousd") == 0)


def classify_failures(engine: Any, session: str, verified: VerifiedPolicy, assessments: list[Json], book: BudgetBook) -> Json:
    """Return exact proven failed IDs for the gate; never change source outcomes.

    Caller supplies the complete current assessment view used by its unchanged
    global gate. Every technical row is compared with its retained record. All
    other global/action/capacity/deadline checks remain the controller's duty.
    """
    require_active(engine, session)
    if (not isinstance(verified, VerifiedPolicy) or verified._seal is not _SEAL
            or verified._engine_id != id(engine) or verified._session != session
            or proof_fingerprint() != verified._fingerprint):
        raise AuditError("truncation_policy_verified_same_session_and_code_required")
    value, baseline = verified.value, verified.baseline
    plan_id = value["plan"]
    current, state = _real_book(engine, session, plan_id, baseline, book)
    if len({row["id"] for row in assessments}) != len(assessments) or any(row.get("plan") != plan_id for row in assessments):
        raise AuditError("truncation_policy_unique_current_plan_assessments_required")
    technical = [row for row in assessments if row.get("technical_failure") or row.get("status") not in {"valid", "invalid"}]
    engine.ledger.append(session, "budget.truncation_policy.classification.intended", {
        "policy_ref": verified.policy_ref, "plan": plan_id, "budget_state": state,
        "assessment_ids": [row["id"] for row in technical], "assessed_rows": len(assessments),
        "proof_fingerprint": verified._fingerprint, "acceptance": False})
    failures = {proof["assessment"]: proof for proof in baseline["failures"]}
    proof_refs, created, reused, unqualified = [], [], [], []
    for row in technical:
        identifier = row["id"]
        retained = {**engine.ledger.get(identifier, chain.base.ASSESSMENT_KIND), "id": identifier}
        if row != retained:
            raise AuditError("truncation_policy_current_assessment_changed")
        if chain.base.acknowledged_assessment(row, baseline["phase"]) or chain.base.acknowledged_failure(row, baseline):
            continue
        entry = current.entry(row["custom_id"])
        if not _candidate(row, entry):
            unqualified.append({"assessment": identifier, "custom_id": row["custom_id"], "errors": row.get("errors"),
                "cost_status": entry["status"], "reason": "not_a_fully_settled_4096_terminal_truncation_candidate"})
            continue
        cache = verified._cache.get(identifier)
        saved = engine.latest(PROOF_KIND, verified.policy_ref + ":" + identifier)
        if cache:
            fingerprint, proof_ref, proof = cache
            if saved is None or saved[0] != proof_ref:
                raise AuditError("truncation_policy_cached_proof_record_changed")
            receipt = engine.ledger.get(proof["download_receipt"], chain.base.RECEIPT_KIND)
            expected = digest({"assessment": row, "entry": entry, "receipt": receipt, "proof": proof,
                               "code": verified._fingerprint})
            if fingerprint != expected or saved[1] != _proof_value(verified, row, entry, receipt, proof):
                raise AuditError("truncation_policy_cached_evidence_or_entry_changed")
            reused.append(proof_ref)
        else:
            proof = chain.base.verify_failure(engine, session, plan_id, identifier, current)
            if proof.get("failure_kind") != "terminal_output_cap_truncation_still_failed":
                raise AuditError("truncation_policy_raw_terminal_type_not_eligible")
            plan = engine.ledger.get(plan_id, chain.base.PLAN_KIND)
            if row["custom_id"] in {task["custom_id"] for task in plan["canary_tasks"]}:
                raise AuditError("truncation_policy_canary_failure_not_eligible")
            receipt = engine.ledger.get(proof["download_receipt"], chain.base.RECEIPT_KIND)
            content = _proof_value(verified, row, entry, receipt, proof)
            if saved:
                if saved[1] != content:
                    raise AuditError("truncation_policy_retained_proof_binding_changed")
                proof_ref = saved[0]
                reused.append(proof_ref)
            else:
                proof_ref = engine.ledger.record(session, PROOF_KIND, verified.policy_ref + ":" + identifier, content)
                created.append(proof_ref)
            fingerprint = digest({"assessment": row, "entry": entry, "receipt": receipt, "proof": proof,
                                  "code": verified._fingerprint})
            verified._cache[identifier] = (fingerprint, proof_ref, proof)
        failures[identifier] = proof
        proof_refs.append(proof_ref)
    # Every baseline row must still be visible, including the separate phase
    # exception. This also prevents a partial view from hiding old evidence.
    if not set(baseline["assessment_ids"] + [baseline["phase"]["assessment"]]) <= {row["id"] for row in technical}:
        raise AuditError("truncation_policy_baseline_assessments_missing_from_current_view")
    ordered = [failures[key] for key in sorted(failures)]
    acknowledgment = {**baseline, "failures": ordered, "assessment_ids": sorted(failures)}
    result = {"plan": plan_id, "policy_ref": verified.policy_ref, "budget_state": state,
        "acknowledgment": acknowledgment, "proof_record_ids": sorted(proof_refs),
        "new_proof_record_ids": sorted(created), "reused_proof_record_ids": sorted(reused),
        "unqualified_failures": unqualified, "qualifying_failures": len(proof_refs),
        "raw_statuses_changed": False, "accepted_events": 0, "paid_retries": 0, "unknown_cost_released": False}
    result["classification_ref"] = engine.ledger.record(session, "luna_budget_truncation_policy_classification",
        verified.policy_ref, {key: item for key, item in result.items() if key != "acknowledgment"})
    return result


def _proof_value(verified: VerifiedPolicy, row: Json, entry: Json, receipt: Json, proof: Json) -> Json:
    return {"method": METHOD, "policy_ref": verified.policy_ref, "plan": verified.value["plan"],
        "assessment": row["id"], "retained_assessment": row, "entry": entry, "receipt": receipt,
        "proof": proof, "proof_fingerprint": verified._fingerprint,
        "original_status": "error", "accepted_output": False, "retry_allowed": False, "cost_released_by_policy": False}
