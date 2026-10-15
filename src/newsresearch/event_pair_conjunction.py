"""Pure exploratory two-feature screens with unchanged selective-link criteria.

All parameter combinations are retained in a compact table. Metric objects are
deduplicated by their exact selected-pair bitmask, not by rounded performance.
Research registration, protected retention, held-out sealing and the original
attempt budget remain the audited caller's responsibility.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from . import event_pair_selection as selection

FEATURE_PAIRS = tuple(itertools.combinations(selection.FEATURES, 2))
MAX_DEVELOPMENT_ROWS = 100
POLICY: dict[str, Any] = {
    "method": "selective-event-link-conjunction-v1",
    "branch": "exploratory after all 20 single-feature variants had no eligible candidate",
    "parent_result": "caller must bind the exact immutable single-feature comparison result",
    "feature_pairs": [list(pair) for pair in FEATURE_PAIRS],
    "publication_gates_days": list(selection.PUBLICATION_GATES),
    "variant_count": 40,
    "fixed_cosine_grid": list(selection.THRESHOLDS),
    "additional_boundaries": "all unique DEVELOPMENT feature cosines; declared before execution",
    "predicate": "both feature cosines >= their thresholds, and optional publication gap <= gate",
    "nonselected_outcome": "review",
    "eligibility_policy": deepcopy(selection.POLICY),
    "eligibility_relaxed": False,
    "maximum_development_rows": MAX_DEVELOPMENT_ROWS,
    "ranking": ["weighted known-same coverage", "observed known-same coverage",
                "weighted pessimistic precision", "observed pessimistic precision",
                "publication gate None/30/7/1", "fixed feature-pair order",
                "stricter threshold sum", "stricter lexicographic thresholds"],
    "diagnostic_ranking": ["at least 8 selected known-same pairs", "weighted pessimistic precision",
                           "weighted known-same coverage", "stricter threshold sum",
                           "stricter lexicographic thresholds"],
    "metric_cache_key": "exact selected-pair bitmask in sorted row_order_pair_ids",
    "population_estimate": False, "human_validated": False, "accepted_dossiers": 0,
    "new_attempt_budget": False,
}


def _candidate(value: Mapping[str, Any]) -> dict[str, Any]:
    features = value.get("features")
    thresholds = value.get("thresholds")
    if not isinstance(features, (tuple, list)) or tuple(features) not in FEATURE_PAIRS:
        raise ValueError("features must be one registered ordered pair of different features")
    if not isinstance(thresholds, (tuple, list)) or len(thresholds) != 2:
        raise ValueError("exactly two cosine thresholds are required")
    normalized = [selection._number(number, "threshold") for number in thresholds]
    if any(not -1 <= number <= 1 for number in normalized):
        raise ValueError("cosine thresholds must be in [-1, 1]")
    gate = value.get("publication_gap_days")
    if isinstance(gate, bool) or gate not in selection.PUBLICATION_GATES:
        raise ValueError("unregistered publication gate")
    return {"features": list(features), "thresholds": normalized, "publication_gap_days": gate}


def predicts(row: Mapping[str, Any], candidate: Mapping[str, Any]) -> bool:
    """Label-blind provisional AUTO-LINK predicate; False means REVIEW."""
    candidate = _candidate(candidate)
    for feature, threshold in zip(candidate["features"], candidate["thresholds"], strict=True):
        value = selection._feature(row, feature)
        if value is None or value < threshold:
            return False
    gate = candidate["publication_gap_days"]
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


def _masked_metrics(rows: list[dict[str, Any]], mask: int, phase: str,
                    errors: list[dict[str, str]], include_ids: bool = False) -> dict[str, Any]:
    masked = [{**row, "features": {"pooled_cosine": float(bool(mask & (1 << index)))}}
              for index, row in enumerate(rows)]
    return selection._metrics(masked, {"feature": "pooled_cosine", "threshold": 1.,
                                       "publication_gap_days": None}, phase, errors, include_ids)


def _rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    metrics = candidate["metrics"]
    quality = [metrics[key] if metrics[key] is not None else -1. for key in (
        "known_same_coverage_weighted", "known_same_coverage_observed",
        "precision_pessimistic_weighted", "precision_pessimistic_observed")]
    return (*quality, -selection.PUBLICATION_GATES.index(candidate["publication_gap_days"]),
            -FEATURE_PAIRS.index(tuple(candidate["features"])), sum(candidate["thresholds"]),
            *candidate["thresholds"])


def _diagnostic_rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    metrics = candidate["metrics"]
    precision = metrics["precision_pessimistic_weighted"]
    coverage = metrics["known_same_coverage_weighted"]
    return (precision if precision is not None else -1., coverage if coverage is not None else -1.,
            sum(candidate["thresholds"]), *candidate["thresholds"])


def _with_ids(candidate: dict[str, Any] | None, rows: list[dict[str, Any]], phase: str,
              errors: list[dict[str, str]]) -> dict[str, Any] | None:
    if candidate is None:
        return None
    mask = int(candidate["mask_id"], 16)
    return {**candidate, "metrics": _masked_metrics(rows, mask, phase, errors, True)}


def evaluate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any],
             phase: str = "development") -> dict[str, Any]:
    """Enumerate all 40 fixed variants; held-out rows/labels never select boundaries."""
    if phase != "development":
        raise ValueError("conjunction selection is development-only; use validate for a frozen screen")
    prepared, errors = selection._prepare(rows, judgments, phase, selection.FEATURES)
    if len(prepared) > MAX_DEVELOPMENT_ROWS:
        raise ValueError("at most 100 development rows are permitted")
    axes = {feature: sorted(set(selection.THRESHOLDS) | {
        value for row in prepared if (value := selection._feature(row, feature)) is not None})
        for feature in selection.FEATURES}
    feature_masks: dict[str, list[int]] = {}
    for feature, thresholds in axes.items():
        feature_masks[feature] = [sum(1 << index for index, row in enumerate(prepared)
                                     if (value := selection._feature(row, feature)) is not None
                                     and value >= threshold) for threshold in thresholds]
    all_mask = (1 << len(prepared)) - 1
    gate_masks = {gate: all_mask if gate is None else sum(
        1 << index for index, row in enumerate(prepared)
        if row["publication_gap_days"] is not None and row["publication_gap_days"] <= gate)
        for gate in selection.PUBLICATION_GATES}
    metrics_map: dict[str, dict[str, Any]] = {}
    grid: list[list[Any]] = []
    variants: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for pair in FEATURE_PAIRS:
        for gate in selection.PUBLICATION_GATES:
            variant_id = len(variants)
            best: dict[str, Any] | None = None
            diagnostic: dict[str, Any] | None = None
            eligible_count = 0
            for left_index, left_mask in enumerate(feature_masks[pair[0]]):
                for right_index, right_mask in enumerate(feature_masks[pair[1]]):
                    mask_id = hex(left_mask & right_mask & gate_masks[gate])
                    if mask_id not in metrics_map:
                        metrics_map[mask_id] = _masked_metrics(prepared, int(mask_id, 16), phase, errors)
                    metrics = metrics_map[mask_id]
                    grid.append([variant_id, left_index, right_index, mask_id])
                    candidate: dict[str, Any] = {
                        "features": list(pair), "thresholds": [axes[pair[0]][left_index],
                                                                axes[pair[1]][right_index]],
                        "publication_gap_days": gate, "mask_id": mask_id, "metrics": metrics,
                    }
                    if metrics["eligible"]:
                        eligible_count += 1
                        if best is None or _rank(candidate) > _rank(best):
                            best = candidate
                    if metrics["selected_label_counts"]["same_event"] >= 8:
                        if diagnostic is None or _diagnostic_rank(candidate) > _diagnostic_rank(diagnostic):
                            diagnostic = candidate
            best = _with_ids(best, prepared, phase, errors)
            if best is not None:
                eligible.append(best)
            variants.append({"variant_id": variant_id, "features": list(pair),
                             "publication_gap_days": gate,
                             "evaluated_count": len(axes[pair[0]]) * len(axes[pair[1]]),
                             "eligible_count": eligible_count, "best_candidate": best,
                             "diagnostic_best_candidate": _with_ids(diagnostic, prepared, phase, errors)})
    counts, _ = selection._counts(prepared)
    return {
        "phase": phase, "policy": deepcopy(POLICY), "row_count": len(prepared),
        "row_order_pair_ids": [row["pair_id"] for row in prepared],
        "all_label_counts": counts, "feature_errors": errors,
        "processing_complete": bool(prepared) and not errors and not any(counts[x] for x in selection.LABELS[3:]),
        "thresholds_by_feature": axes, "candidates": variants,
        "best_candidate": max(eligible, key=_rank) if eligible else None,
        "metrics_map": metrics_map,
        "full_grid": {"columns": ["variant_id", "left_threshold_index", "right_threshold_index", "mask_id"],
                      "rows": grid},
        "evaluated_parameter_combinations": len(grid), "distinct_prediction_masks": len(metrics_map),
        "limitations": [*selection.LIMITATIONS,
                        "Two-feature exploration follows a failed single-feature study without relaxing eligibility.",
                        "All parameter combinations and failed eligibility checks are retained via exact mask references."],
    }


def validate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any],
             candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one frozen conjunction under the unchanged validation policy."""
    parameters = _candidate(candidate)
    prepared, errors = selection._prepare(rows, judgments, "validation", parameters["features"])
    mask = sum(1 << index for index, row in enumerate(prepared) if predicts(row, parameters))
    metrics = _masked_metrics(prepared, mask, "validation", errors, True)
    return {"phase": "validation", "candidate": parameters, "metrics": metrics,
            "feature_errors": errors, "policy": deepcopy(POLICY),
            "status": "provisional_model_reference_pass" if metrics["eligible"] else "inconclusive",
            "limitations": list(selection.LIMITATIONS)}
