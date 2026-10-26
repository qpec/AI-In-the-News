"""Pure fixed-look reference aggregation; no sources, ledger or provider access.

The audited adapter must verify exact task/source/response bindings and project
strict contract parses into the normalized observation rows below. A row is not
verified merely because this arithmetic helper accepts its shape.
"""
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json

from final_validation_candidate_metrics import joint_pair_and_candidate_metrics
from final_validation_frame import ProbabilityFrame
from final_validation_policy import qc_manifest

VERSION = "final-validation-fixed-look-reference-aggregation-v1"
ROLES = {"primary", "qc", "qc_adjudication", "uncertain_adjudication"}
STATUSES = {"resolved", "epistemic_unknown", "technical_unavailable", "provenance_unavailable", "invalid"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def _sha(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("reference_record_sha256_required")


def _validate_row(row):
    if not isinstance(row, dict) or set(row) != {"pair_rank", "role", "record_id", "status", "positive"}:
        raise ValueError("reference_projection_fields")
    if type(row["pair_rank"]) is not int or row["pair_rank"] < 0 or row["role"] not in ROLES:
        raise ValueError("reference_projection_identity")
    _sha(row["record_id"])
    if row["status"] not in STATUSES:
        raise ValueError("reference_projection_status")
    if row["status"] == "resolved":
        if type(row["positive"]) is not int or row["positive"] not in (0, 1):
            raise ValueError("resolved_binary_reference_required")
    elif row["positive"] is not None:
        raise ValueError("unavailable_reference_cannot_be_binary")


def _resolved(row):
    return row is not None and row["status"] == "resolved"


def effective_primary(primary, qc, *, qc_selected):
    """Conservative missingness; diagnostic judgments never enter this reducer."""
    if primary is None:
        return None, "primary_not_attempted_or_unavailable"
    if not _resolved(primary):
        return None, "primary_" + primary["status"]
    if not qc_selected:
        return primary["positive"], "resolved_without_selected_qc"
    if qc is None:
        return None, "selected_qc_not_attempted_or_unavailable"
    if not _resolved(qc):
        return None, "selected_qc_" + qc["status"]
    if primary["positive"] != qc["positive"]:
        return None, "primary_qc_disagreement"
    return primary["positive"], "resolved_with_qc_agreement"


def summarize_look(frame: ProbabilityFrame, sample: dict, qc: dict, observations: list[dict], *,
                   look: int, reference_projection_binding: str) -> dict:
    """Project one COMPLETE fixed-look sample, including pending/failed units.

    Observations are unique normalized durable primary/QC/diagnostic records.
    Missing rows stay unknown; missing selected QC makes a known primary unknown.
    No replacement, adjudication-majority repair or complete-case deletion occurs.
    The coordinator, not this helper, checks exact permitted conditional tasks,
    account limits, source/provenance fidelity and transport attempts. This may
    show conservative partial coverage at a fixed look, but is never an estimate
    based on the smaller QC-dependent initial operational prefix alone.
    """
    _sha(reference_projection_binding)
    if type(look) is not int or look not in (1, 2, 3) or not isinstance(qc, dict):
        raise ValueError("declared_fixed_look_required")
    try:
        expected_qc = qc_manifest(frame, sample, qc_seed=qc["qc_seed"])
    except KeyError as exc:
        raise ValueError("qc_manifest_binding") from exc
    if qc != expected_qc:
        raise ValueError("qc_manifest_binding")
    if not isinstance(observations, list):
        raise ValueError("reference_observations_required")
    flags = {u["pair_rank"]: u["qc"] for cell in qc["strata"] for u in cell["units"]}
    selected = {u["pair_rank"] for cell in sample["strata"]
                for u in cell["selected_order"][:cell["looks"][look - 1]["sample_size"]]}
    rows, record_ids = {}, set()
    for row in observations:
        _validate_row(row)
        rank, role = row["pair_rank"], row["role"]
        if rank not in selected:
            raise ValueError("reference_outside_declared_look")
        if (role in {"qc", "qc_adjudication"} and not flags[rank]
                or role == "uncertain_adjudication" and flags[rank]):
            raise ValueError("reference_role_outside_qc_design")
        key = (rank, role)
        if key in rows or row["record_id"] in record_ids:
            raise ValueError("duplicate_reference_observation")
        rows[key] = row
        record_ids.add(row["record_id"])
    strata, coverage, qc_coverage, reasons = [], [], [], Counter()
    # Each projected QC unit's fixed-look design weight is 5*N_h/n_h.
    qc_mass = {key: Fraction(0) for key in ("agree", "disagree", "unresolved")}
    observed_confusion = Counter({key: 0 for key in ("TP", "FP", "FN", "TN")})
    total_primary_observed = total_qc_observed = 0
    for cell in sample["strata"]:
        n = cell["looks"][look - 1]["sample_size"]
        units = cell["selected_order"][:n]
        positives = unresolved = primary_observed = 0
        qcounts = Counter({key: 0 for key in ("selected", "observed", "agree", "disagree", "unresolved")})
        statuses = Counter()
        for unit in units:
            rank = unit["pair_rank"]
            primary, secondary = rows.get((rank, "primary")), rows.get((rank, "qc"))
            primary_observed += primary is not None
            statuses[primary["status"] if primary is not None else "not_attempted_or_unavailable"] += 1
            value, reason = effective_primary(primary, secondary, qc_selected=flags[rank])
            reasons[reason] += 1
            positives += value == 1
            unresolved += value is None
            if value is not None:
                label = ("TP" if value else "FP") if cell["coassigned"] else ("FN" if value else "TN")
                observed_confusion[label] += 1
            if flags[rank]:
                qcounts["selected"] += 1
                qcounts["observed"] += secondary is not None
                comparison = ("agree" if primary["positive"] == secondary["positive"] else "disagree") \
                    if _resolved(primary) and _resolved(secondary) else "unresolved"
                qcounts[comparison] += 1
                qc_mass[comparison] += Fraction(5 * cell["population"], n)
        strata.append({"stratum": cell["stratum"], "population": cell["population"],
            "coassigned": cell["coassigned"], "candidate_exposure": cell["candidate_exposure"],
            "sample_size": n, "positives": positives, "unresolved": unresolved})
        coverage.append({"stratum": cell["stratum"], "selected": n, "primary_records": primary_observed,
            "effective_resolved": n - unresolved, "effective_unknown": unresolved, "primary_statuses": dict(statuses)})
        qc_coverage.append({"stratum": cell["stratum"], **dict(qcounts),
            "fixed_look_weight_numerator": 5 * cell["population"], "fixed_look_weight_denominator": n})
        total_primary_observed += primary_observed
        total_qc_observed += qcounts["observed"]
    metrics = joint_pair_and_candidate_metrics(strata, documents=len(frame.index.inputs), looks=3)
    result = {"version": VERSION, "status": "unregistered_fixed_look_projection", "look": look,
        "frame_digest": frame.digest, "sample_manifest_sha256": sample["manifest_sha256"],
        "qc_manifest_sha256": qc["qc_manifest_sha256"],
        "reference_projection_binding": reference_projection_binding,
        "observations_sha256": _digest(sorted(observations, key=lambda r: (r["pair_rank"], r["role"]))),
        "selected_primary_units": len(selected), "primary_records": total_primary_observed,
        "selected_qc_units": sum(flags[r] for r in selected), "qc_records": total_qc_observed,
        "effective_resolved": sum(row["sample_size"] - row["unresolved"] for row in strata),
        "effective_unknown": sum(row["unresolved"] for row in strata), "resolution_reasons": dict(reasons),
        "unweighted_sample_confusion_counts": dict(observed_confusion),
        "coverage_by_stratum": coverage, "qc_coverage_by_stratum": qc_coverage,
        "qc_design_weighted_masses": {key: {"numerator": value.numerator, "denominator": value.denominator}
                                     for key, value in qc_mass.items()},
        "qc_inference_note": "Fixed-look design-weighted masses, no independent QC confidence claim; unavailable comparisons retained.",
        "diagnostic_records_retained_but_not_used_for_primary": sum(role not in {"primary", "qc"} for _, role in rows),
        "metrics": metrics, "reference_source_bindings_verified_by_this_helper": False,
        "human_validated": False, "candidate_recall_integration": "same_joint_count_region",
        "secondary_join_and_dossier_metrics": "not_integrated"}
    return {**result, "result_sha256": _digest(result)}
