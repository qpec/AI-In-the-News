"""Prospective packet-local disposition; credential and transport guards are unchanged.

The caller must verify retained receipts/physical identities before passing carried
history. A discarded body is unavailable evidence, never proof of a false positive.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import dossier_transport_v9 as transport
import luna_quality_audit as prior
import luna_title_summary_run as original
from newsresearch.common import AuditError
from newsresearch.gateway import ProviderResponse

METHOD = "luna-title-summary-packet-local-continuation-v1"
RAW_FIELDS = {"unknown_outcome", "dispatch_started", "kind", "http_status",
    "observability_version", "failure_stage", "failure_code"}
ROLES = {"article_summary", "title_search", "development", "group_membership", "group_quality"}


def implementation():
    path = Path(__file__)
    return {**original.implementation(), path.relative_to(original.ROOT).as_posix():
        hashlib.sha256(path.read_bytes()).hexdigest()}


def qualifies_local_guard(response: ProviderResponse) -> bool:
    """Recognize only the complete, body-discarded V9 HTTP-200 envelope."""
    if not isinstance(response, ProviderResponse):
        return False
    raw = response.raw_response
    return (isinstance(raw, dict) and set(raw) == RAW_FIELDS
        and isinstance(raw["kind"], str) and raw["kind"] in {"responses", "decisions"}
        and response.provider == "openai-"+raw["kind"]
        and type(raw["http_status"]) is int and raw["http_status"] == 200
        and raw["unknown_outcome"] is True and raw["dispatch_started"] is True
        and raw["observability_version"] == transport.OBSERVABILITY
        and raw["failure_stage"] == "response_credentials"
        and raw["failure_code"] == "response_content_rejected"
        and response.payload is None and response.model is None
        and response.usage is None and response.request_id is None)


def outcome(packet, response):
    derived, parsed = original.outcome(packet, response)
    qualified = (qualifies_local_guard(response)
        and packet["kind"] == response.raw_response["kind"] and packet["role"] in ROLES)
    if qualified:
        if not (derived["fatal"] == "response_content_rejected" and derived["hold"] is True
                and derived["usable"] is False and derived["cost_nanousd"] is None and parsed is None):
            raise AuditError("title_summary_continuation_outcome_invariant")
        derived = {**derived, "fatal": None}
    return {**derived, "local_guard_unavailable": qualified, "continuation_scope": METHOD,
        "original_fatal": "response_content_rejected" if qualified else derived["fatal"]}, parsed


def _validate(intents, responses):
    if not isinstance(intents, dict) or not isinstance(responses, dict) or set(responses)-set(intents):
        raise AuditError("title_summary_continuation_health_partition")
    attempts = []
    for key, row in intents.items():
        if not isinstance(key, str) or not key or not isinstance(row, dict):
            raise AuditError("title_summary_continuation_health_identity")
        attempt = row.get("attempt")
        if not isinstance(attempt, str) or not attempt or row.get("task_key", key) != key:
            raise AuditError("title_summary_continuation_health_identity")
        attempts.append(attempt)
    if len(attempts) != len(set(attempts)):
        raise AuditError("title_summary_continuation_duplicate_physical_attempt")
    for key, row in responses.items():
        if (not isinstance(row, dict) or type(row.get("usable")) is not bool or "fatal" not in row
                or row.get("attempt", intents[key]["attempt"]) != intents[key]["attempt"]
                or row.get("task_key", key) != key
                or (row["fatal"] is not None and not isinstance(row["fatal"], str))):
            raise AuditError("title_summary_continuation_health_response")
        if row.get("local_guard_unavailable") and not (
                row.get("continuation_scope") == METHOD and row.get("original_fatal") == "response_content_rejected"
                and row["fatal"] is None and row["usable"] is False
                and row.get("hold") is True and row.get("cost_nanousd") is None):
            raise AuditError("title_summary_continuation_local_disposition")
    return set(attempts)


def health_state(intents, responses, *, carried_intents=None, carried_responses=None):
    """Carry all physical failures, then enforce the first NEW request gate.

Only a qualified old first-request guard disposition can release the historical
first-request gate. The unchanged 8 consecutive / 16 of last32 guards still run.
    """
    carried_intents = {} if carried_intents is None else carried_intents
    carried_responses = {} if carried_responses is None else carried_responses
    old_attempts = _validate(carried_intents, carried_responses)
    new_attempts = _validate(intents, responses)
    if set(carried_intents) & set(intents) or old_attempts & new_attempts:
        raise AuditError("title_summary_continuation_duplicate_history")
    combined_intents = {**carried_intents, **intents}
    combined_responses = {**carried_responses, **responses}
    result = prior.health_state(combined_intents, combined_responses)
    if (result["stop_reason"] == "first_fixed_packet_operational_gate_failed" and carried_intents
            and carried_responses.get(next(iter(carried_intents)), {}).get("local_guard_unavailable") is True):
        result = {**result, "stop_reason": None}
    gate = "pending"
    if intents:
        first = next(iter(intents))
        gate = "passed" if responses.get(first, {}).get("usable") is True else "failed"
        if gate == "failed" and not result["stop_reason"]:
            result = {**result, "stop_reason": "first_new_request_operational_gate_failed"}
    return {**result, "first_new_request_gate": gate,
        "carried_physical_attempts": len(carried_intents), "new_physical_attempts": len(intents)}
