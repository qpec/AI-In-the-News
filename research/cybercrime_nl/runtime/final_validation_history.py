"""Pure prospective reference-history reconciliation; no owner or provider I/O.

The audited parent must certify the normalized historical inventory and its
source/role/attempt provenance. Hashes here bind that projection, not its truth.
Only exact current full-pair contracts are reusable. Incompatible pair-reference
attempts still prevent a same-role replacement; other estimands never supply Y.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import re

import final_validation_contract as contract
from newsresearch.common import ResearchError, digest

VERSION = "final-validation-reference-history-v1"
ROLES = {"primary", "qc", "qc_adjudication", "uncertain_adjudication"}
SOURCE_FIELDS = {"document_id", "title_sha256", "body_sha256", "input_sha256"}
ENTRY_FIELDS = {"version", "role", "source_identity", "source_identity_sha256", "state",
    "positive", "reason_codes", "historical_records", "physical_attempts", "inventory_sha256",
    "catalog_sha256", "entry_sha256", "reference_status", "diagnostic_eligible"}
RECORD_FIELDS = {"record_id", "owner_sha256", "attempt_id", "logical_task_id", "role",
    "scope_kind", "source_identity", "attempt_state", "definition_version", "packet",
    "payload", "provenance"}


def require(value, reason):
    if not value:
        raise ResearchError("final_history_" + reason)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "sha256_required")


def sources(value, *, pair=False):
    require(isinstance(value, list) and len(value) >= 1 and (not pair or len(value) == 2), "source_count")
    for row in value:
        require(isinstance(row, dict) and set(row) == SOURCE_FIELDS, "source_fields")
        require(isinstance(row["document_id"], str) and bool(row["document_id"].strip()), "source_id")
        for key in SOURCE_FIELDS - {"document_id"}:
            sha(row[key])
    require(len({r["document_id"] for r in value}) == len(value), "duplicate_source_id")
    require(len({r["input_sha256"] for r in value}) == len(value), "exact_alias_not_independent_source")
    return sorted(deepcopy(value), key=lambda r: r["document_id"])


def exact_inputs(value):
    return sorted((r["title_sha256"], r["body_sha256"], r["input_sha256"]) for r in value)


def packet_sources(packet):
    contract.validate_packet(packet)
    return sources([{k: r[k] for k in SOURCE_FIELDS} for r in packet["source_bindings"]], pair=True)


def normalize_records(records):
    require(isinstance(records, list), "records_required")
    physical, identifiers = {}, {}
    for row in records:
        require(isinstance(row, dict) and set(row) == RECORD_FIELDS, "record_fields")
        for key in ("record_id", "owner_sha256", "attempt_id", "logical_task_id"):
            sha(row[key])
        require(row["role"] in ROLES, "role")
        require(row["scope_kind"] in {"pair_reference", "group_reference", "card_review", "screening"}, "scope")
        identity = sources(row["source_identity"], pair=row["scope_kind"] == "pair_reference")
        require(row["attempt_state"] in {"prepared", "intent", "returned", "predispatch_failure"}, "attempt_state")
        require(row["definition_version"] is None or isinstance(row["definition_version"], str), "definition")
        require(row["packet"] is None or isinstance(row["packet"], dict), "packet_shape")
        if row["attempt_state"] != "returned":
            require(row["payload"] is None and row["provenance"] is None, "nonreturned_response_conflict")
        # A retained current packet is checked even when another field makes the
        # old reference ineligible. Corrupt bindings are not benign missingness.
        if row["packet"] is not None and row["packet"].get("method") == contract.METHOD:
            require(packet_sources(row["packet"]) == identity, "packet_source_mismatch")
        normalized = {**deepcopy(row), "source_identity": identity}
        previous = identifiers.setdefault(row["record_id"], normalized)
        require(previous == normalized, "conflicting_record_identity")
        key = (row["owner_sha256"], row["attempt_id"])
        comparable = {k: v for k, v in normalized.items() if k != "record_id"}
        if key in physical:
            require(physical[key]["content"] == comparable, "conflicting_physical_attempt_or_role")
            physical[key]["record_ids"].add(row["record_id"])
        else:
            physical[key] = {"content": comparable, "record_ids": {row["record_id"]}}
    return [{**row["content"], "record_ids": sorted(row["record_ids"])}
            for _, row in sorted(physical.items())]


def validate_inventory(value):
    require(isinstance(value, dict) and set(value) == {"binding_sha256", "complete",
        "unknown_input_sha256", "global_gap"}, "inventory_fields")
    sha(value["binding_sha256"])
    require(type(value["complete"]) is bool and type(value["global_gap"]) is bool, "inventory_flags")
    unknown = value["unknown_input_sha256"]
    require(isinstance(unknown, list) and len(unknown) == len(set(unknown)), "inventory_unknown_inputs")
    for item in unknown:
        sha(item)
    # An incomplete inventory can have a localized gap. Without that scope it
    # must conservatively affect every pair, never silently allow fresh work.
    require(value["complete"] or unknown or value["global_gap"], "unlocalized_inventory_gap")


def reference_value(row):
    if row["attempt_state"] != "returned":
        return None, "prior_intent_without_reusable_response", False
    if row["definition_version"] != contract.DEFINITION_VERSION:
        return None, "different_or_missing_definition", False
    packet = row["packet"]
    if packet is None or packet.get("method") != contract.METHOD:
        return None, "incompatible_or_missing_pair_contract", False
    if row["payload"] is None or row["provenance"] is None:
        return None, "missing_response_or_provenance", False
    try:
        result = contract.parse(packet, row["payload"], provenance=row["provenance"])
    except ResearchError:
        return None, "invalid_or_untrusted_reference", False
    if result["provenance_gaps"]:
        return None, "reference_provenance_unavailable", False
    if result["reference_positive"] is None:
        return None, "reference_epistemically_unresolved", True
    return result["reference_positive"], "exact_contract_reference", False


def resolve_history(source_identity, role, records, inventory_certificate):
    """Resolve ONE frozen pair/role; never choose a favorable old judgment.

    All distinct same-role exact-pair attempts must be reusable and agree before
    returning a binary label. Duplicate retained views count once. Prepared-only
    records are not attempts; durable intents/predispatch failures remain blocked.
    An incomplete inventory affecting this pair blocks fresh dispatch and reuse.
    This helper does not derive P and does not itself authorize any request.
    """
    identity = sources(source_identity, pair=True)
    require(role in ROLES, "role")
    validate_inventory(inventory_certificate)
    normalized = normalize_records(records)
    relevant = [r for r in normalized if r["scope_kind"] == "pair_reference" and r["role"] == role
                and exact_inputs(r["source_identity"]) == exact_inputs(identity)
                and r["attempt_state"] != "prepared"]
    gap = inventory_certificate["global_gap"] or bool(
        {r["input_sha256"] for r in identity} & set(inventory_certificate["unknown_input_sha256"]))
    judged = [reference_value(r) for r in relevant]
    reasons = Counter(reason for _, reason, _ in judged)
    values = {value for value, _, _ in judged}
    diagnostic_eligible = not gap and len(judged) == 1 and judged[0][2]
    if gap:
        state, positive = "prior_attempt_unavailable", None
        reasons["historical_inventory_gap"] += 1
    elif not relevant:
        state, positive = "fresh_unattempted", None
        reasons["no_recorded_pair_role_attempt"] += 1
    elif None not in values and len(values) == 1:
        state, positive = "reused_resolved", next(iter(values))
    else:
        state, positive = "prior_attempt_unavailable", None
        if len(values - {None}) > 1:
            reasons["historical_reference_disagreement"] += 1
    result = {"version": VERSION, "role": role, "source_identity": identity,
        "source_identity_sha256": digest(identity), "state": state, "positive": positive,
        "reference_status": ("resolved" if state == "reused_resolved" else
            "unattempted" if state == "fresh_unattempted" else
            "epistemic_unknown" if diagnostic_eligible else "technical_unavailable"),
        "diagnostic_eligible": diagnostic_eligible,
        "reason_codes": sorted(reasons),
        "historical_records": sorted({i for r in relevant for i in r["record_ids"]}),
        "physical_attempts": [{"owner_sha256": r["owner_sha256"], "attempt_id": r["attempt_id"]} for r in relevant],
        "inventory_sha256": digest(inventory_certificate),
        "catalog_sha256": digest({"records": normalized, "inventory": inventory_certificate})}
    return validate_entry({**result, "entry_sha256": digest(result)})


def validate_entry(value):
    require(isinstance(value, dict) and set(value) == ENTRY_FIELDS, "entry_fields")
    require(value["version"] == VERSION and value["role"] in ROLES, "entry_version_role")
    identity = sources(value["source_identity"], pair=True)
    require(identity == value["source_identity"] and digest(identity) == value["source_identity_sha256"], "entry_sources")
    for key in ("entry_sha256", "catalog_sha256", "inventory_sha256"):
        sha(value[key])
    require(value["entry_sha256"] == digest({k: v for k, v in value.items() if k != "entry_sha256"}), "entry_digest")
    require(value["state"] in {"fresh_unattempted", "reused_resolved", "prior_attempt_unavailable"}, "entry_state")
    require(type(value["diagnostic_eligible"]) is bool, "diagnostic_eligibility")
    status = value["reference_status"]
    require(status in {"unattempted", "resolved", "epistemic_unknown", "technical_unavailable"}, "reference_status")
    require(isinstance(value["reason_codes"], list) and value["reason_codes"] == sorted(set(value["reason_codes"]))
            and all(isinstance(v, str) and v for v in value["reason_codes"]), "entry_reasons")
    records, attempts = value["historical_records"], value["physical_attempts"]
    require(isinstance(records, list) and records == sorted(set(records)), "entry_records")
    for record in records:
        sha(record)
    require(isinstance(attempts, list), "entry_attempts")
    for attempt in attempts:
        require(isinstance(attempt, dict) and set(attempt) == {"owner_sha256", "attempt_id"}, "entry_attempt_fields")
        sha(attempt["owner_sha256"])
        sha(attempt["attempt_id"])
    require(len({digest(r) for r in attempts}) == len(attempts), "duplicate_entry_attempt")
    if value["state"] == "reused_resolved":
        require(type(value["positive"]) is int and value["positive"] in (0, 1) and records and attempts,
                "reused_reference_evidence")
        require(status == "resolved" and not value["diagnostic_eligible"], "resolved_status")
    else:
        require(value["positive"] is None, "unavailable_cannot_supply_label")
    if value["state"] == "fresh_unattempted":
        require(not records and not attempts, "fresh_cannot_have_attempts")
        require(status == "unattempted" and not value["diagnostic_eligible"], "fresh_status")
    if value["state"] == "prior_attempt_unavailable":
        require(status in {"epistemic_unknown", "technical_unavailable"}, "unavailable_status")
        require(value["diagnostic_eligible"] == (status == "epistemic_unknown"), "diagnostic_status")
        if value["diagnostic_eligible"]:
            require(len(attempts) == 1 and records, "diagnostic_single_reference_required")
    return deepcopy(value)
