"""Finite final exploratory search over five-feature monotone AND rules.

This pure module performs no source access, model calls or budget allocation.
The audited caller binds the failed earlier branches, preserves the sealed
holdout and freezes at most one candidate across the authorization lineage.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from . import event_pair_selection as selection
from .event_pair_conjunction import _masked_metrics

MAX_DEVELOPMENT_ROWS = 100
MAX_KNOWN_POSITIVES = 14
POLICY: dict[str, Any] = {
    "method": "selective-event-link-final-monotone-v1",
    "branch": "final finite exploratory branch after failed single-feature and two-feature searches",
    "features": list(selection.FEATURES),
    "publication_gates_days": list(selection.PUBLICATION_GATES),
    "eligibility_policy": deepcopy(selection.POLICY), "eligibility_relaxed": False,
    "maximum_development_rows": MAX_DEVELOPMENT_ROWS,
    "maximum_known_positive_references": MAX_KNOWN_POSITIVES,
    "enumeration": "Every publication-eligible known-positive subset of size at least 8; each threshold is its coordinate minimum.",
    "existence_proof": (
        "For any eligible development AND box, let S be ALL its selected known-positive pairs. "
        "Tightening every feature threshold to its minimum on S preserves exactly S, including "
        "its original weights, coverage and positive support, and selects a subset of the original "
        "box. Observed and weighted pessimistic precision cannot decrease. This representative "
        "is enumerated under the same publication gate. No eligible representative therefore "
        "means no eligible rule in this fixed development family."
    ),
    "proof_scope": "Complete development references and features only; NOT validation eligibility or generalization.",
    "validation_proof_exception": "Tightening can remove nonpositive pairs required by the validation minimum of 20 links.",
    "nonselected_outcome": "review", "simpler_cutoff_claim": False,
    "population_estimate": False, "human_validated": False, "accepted_dossiers": 0,
    "new_attempt_budget": False,
    "ranking": ["weighted known-same coverage", "observed known-same coverage",
                "weighted pessimistic precision", "observed pessimistic precision",
                "publication gate None/30/7/1", "stricter threshold sum", "stricter lexicographic thresholds"],
    "diagnostic_ranking": ["minimum of observed and weighted pessimistic precision",
                           "weighted known-same coverage", "observed known-same coverage",
                           "publication gate None/30/7/1", "stricter threshold sum",
                           "stricter lexicographic thresholds"],
}


def _candidate(value: Mapping[str, Any]) -> dict[str, Any]:
    features = value.get("features")
    thresholds = value.get("thresholds")
    if not isinstance(features, (tuple, list)) or tuple(features) != selection.FEATURES:
        raise ValueError("the complete fixed five-feature order is required")
    if not isinstance(thresholds, (tuple, list)) or len(thresholds) != len(selection.FEATURES):
        raise ValueError("exactly five thresholds are required")
    cuts = [selection._number(value, "threshold") for value in thresholds]
    if any(not -1 <= value <= 1 for value in cuts):
        raise ValueError("cosine thresholds must be in [-1, 1]")
    gate = value.get("publication_gap_days")
    if isinstance(gate, bool) or gate not in selection.PUBLICATION_GATES:
        raise ValueError("unregistered publication gate")
    return {"features": list(selection.FEATURES), "thresholds": cuts, "publication_gap_days": gate}


def predicts(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """Label-blind AUTO-LINK predicate; False means REVIEW."""
    parameters = _candidate(candidate)
    for feature, cut in zip(selection.FEATURES, parameters["thresholds"], strict=True):
        value = selection._feature(row, feature)
        if value is None or value < cut:
            return False
    gate = parameters["publication_gap_days"]
    if gate is None:
        return True
    gap = row.get("publication_gap_days")
    if gap is None:
        return False
    try:
        gap = selection._number(gap, "publication gap")
    except ValueError:
        return False
    return 0 <= gap <= gate


def _rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    metrics = candidate["metrics"]
    return (*(metrics[key] if metrics[key] is not None else -1. for key in (
        "known_same_coverage_weighted", "known_same_coverage_observed",
        "precision_pessimistic_weighted", "precision_pessimistic_observed")),
        -selection.PUBLICATION_GATES.index(candidate["publication_gap_days"]),
        sum(candidate["thresholds"]), *candidate["thresholds"])


def _diagnostic_rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    metrics = candidate["metrics"]
    precision = min(metrics["precision_pessimistic_observed"], metrics["precision_pessimistic_weighted"])
    return (precision, metrics["known_same_coverage_weighted"], metrics["known_same_coverage_observed"],
            -selection.PUBLICATION_GATES.index(candidate["publication_gap_days"]),
            sum(candidate["thresholds"]), *candidate["thresholds"])


def _with_ids(candidate: dict[str, Any] | None, rows: list[dict[str, Any]], phase: str,
              errors: list[dict[str, str]]) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return {**candidate, "metrics": _masked_metrics(rows, int(candidate["mask_id"], 16), phase, errors, True)}


def evaluate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any]) -> dict[str, Any]:
    """Exhaust the fixed development family without opening or scoring holdout labels."""
    prepared, errors = selection._prepare(rows, judgments, "development", selection.FEATURES)
    if len(prepared) > MAX_DEVELOPMENT_ROWS:
        raise ValueError("at most 100 development references are permitted")
    positives = [row for row in prepared if row["reference_label"] == "same_event"]
    if len(positives) > MAX_KNOWN_POSITIVES:
        raise ValueError("at most 14 known-positive references are permitted")
    counts, _ = selection._counts(prepared)
    incomplete_references = any(counts[name] for name in selection.LABELS[3:])
    complete = bool(prepared) and not errors and not incomplete_references
    metrics_map: dict[str, dict[str, Any]] = {}
    vectors: list[list[float]] = []
    vector_ids: dict[tuple[float, ...], int] = {}
    grid: list[list[Any]] = []
    gates: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    diagnostic: dict[str, Any] | None = None
    coverage_diagnostic: dict[str, Any] | None = None
    minimum = selection.POLICY["development"]["minimum_selected_same"]
    if complete:
        all_mask = (1 << len(prepared)) - 1
        feature_masks: dict[str, dict[float, int]] = {}
        for feature in selection.FEATURES:
            levels = {float(row["features"][feature]) for row in positives}
            feature_masks[feature] = {cut: sum(1 << index for index, row in enumerate(prepared)
                                              if float(row["features"][feature]) >= cut)
                                      for cut in levels}
        for gate_index, gate in enumerate(selection.PUBLICATION_GATES):
            eligible_positive_indexes = [index for index, row in enumerate(positives)
                                         if gate is None or row["publication_gap_days"] is not None
                                         and row["publication_gap_days"] <= gate]
            gate_mask = all_mask if gate is None else sum(
                1 << index for index, row in enumerate(prepared)
                if row["publication_gap_days"] is not None and row["publication_gap_days"] <= gate)
            gate_count = 0
            gate_eligible_count = 0
            for size in range(minimum, len(eligible_positive_indexes) + 1):
                for subset in itertools.combinations(eligible_positive_indexes, size):
                    cuts = tuple(min(float(positives[index]["features"][feature]) for index in subset)
                                 for feature in selection.FEATURES)
                    if cuts not in vector_ids:
                        vector_ids[cuts] = len(vectors)
                        vectors.append(list(cuts))
                    mask = gate_mask
                    for feature, cut in zip(selection.FEATURES, cuts, strict=True):
                        mask &= feature_masks[feature][cut]
                    mask_id = hex(mask)
                    if mask_id not in metrics_map:
                        metrics_map[mask_id] = _masked_metrics(prepared, mask, "development", errors)
                    metrics = metrics_map[mask_id]
                    subset_mask = hex(sum(1 << index for index in subset))
                    grid.append([gate_index, subset_mask, vector_ids[cuts], mask_id])
                    gate_count += 1
                    candidate: dict[str, Any] = {
                        "features": list(selection.FEATURES), "thresholds": list(cuts),
                        "publication_gap_days": gate, "mask_id": mask_id,
                        "generating_positive_subset_mask": subset_mask, "metrics": metrics,
                    }
                    if metrics["eligible"]:
                        gate_eligible_count += 1
                        if best is None or _rank(candidate) > _rank(best):
                            best = candidate
                    if diagnostic is None or _diagnostic_rank(candidate) > _diagnostic_rank(diagnostic):
                        diagnostic = candidate
                    support_ok = (metrics["known_same_coverage_observed"] >= .5
                                  and metrics["known_same_coverage_weighted"] >= .5
                                  and metrics["distinct_positive_articles"] >= 12
                                  and metrics["disjoint_positive_pair_lower_bound"] >= 4)
                    if support_ok and (coverage_diagnostic is None
                                       or _diagnostic_rank(candidate) > _diagnostic_rank(coverage_diagnostic)):
                        coverage_diagnostic = candidate
            gates.append({"publication_gap_days": gate,
                          "eligible_known_positives": len(eligible_positive_indexes),
                          "evaluated_subsets": gate_count, "eligible_subsets": gate_eligible_count})
    if errors:
        status = "incomplete_features"
    elif not complete:
        status = "incomplete_references"
    elif len(positives) < minimum:
        status = "insufficient_positive_support"
    else:
        status = "eligible_candidate" if best is not None else "no_eligible_rule"
    return {
        "policy": deepcopy(POLICY), "phase": "development", "status": status,
        "row_count": len(prepared), "all_label_counts": counts, "feature_errors": errors,
        "processing_complete": complete, "search_complete": complete,
        "row_order_pair_ids": [row["pair_id"] for row in prepared],
        "positive_subset_row_order": [row["pair_id"] for row in positives],
        "threshold_vectors": vectors, "publication_gates_days": list(selection.PUBLICATION_GATES),
        "full_grid": {"columns": ["publication_gate_index", "positive_subset_mask",
                                  "threshold_vector_index", "mask_id"], "rows": grid},
        "metrics_map": metrics_map, "gate_summaries": gates,
        "evaluated_generating_subsets": len(grid), "distinct_prediction_masks": len(metrics_map),
        "best_candidate": _with_ids(best, prepared, "development", errors),
        "best_at_required_coverage": _with_ids(coverage_diagnostic, prepared, "development", errors),
        "best_precision_overall": _with_ids(diagnostic, prepared, "development", errors),
        "limitations": [*selection.LIMITATIONS,
                        "This final exhaustive existence screen concerns only this five-feature development family.",
                        "A selected five-constraint rule is not a universally correct cutoff or validated event clustering.",
                        "All 54 references and original weights remain in closure evaluation; seed subsets are not evaluation samples."],
    }


def validate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any],
             candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one previously frozen five-feature rule with unchanged held-out policy."""
    parameters = _candidate(candidate)
    prepared, errors = selection._prepare(rows, judgments, "validation", selection.FEATURES)
    mask = sum(1 << index for index, row in enumerate(prepared) if predicts(row, parameters))
    metrics = _masked_metrics(prepared, mask, "validation", errors, True)
    return {"phase": "validation", "candidate": parameters, "metrics": metrics,
            "feature_errors": errors, "policy": deepcopy(POLICY),
            "status": "provisional_model_reference_pass" if metrics["eligible"] else "inconclusive",
            "limitations": list(selection.LIMITATIONS)}
