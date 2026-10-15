"""Pure, exploratory selective-link comparison; never corpus-wide calibration.

The caller must register this policy and use the audited research runtime.  This
module reads no files, dispatches no models and changes no accepted dossiers.
Labels are model references, not human gold. Non-selected pairs require REVIEW.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

FEATURES = (
    "pooled_cosine", "first_passage_cosine", "symmetric_mean_best_cosine",
    "top3_mutual_best_mean_cosine", "max_passage_cosine",
)
THRESHOLDS = (
    .60, .65, .70, .75, .80, .825, .85, .875, .90, .925, .95,
    .96, .97, .98, .99, .995, 1.0,
)
PUBLICATION_GATES: tuple[int | None, ...] = (None, 30, 7, 1)
LABELS = ("same_event", "different_event", "uncertain", "failed", "pending", "unknown", "invalid")
POLICY: dict[str, Any] = {
    "method": "selective-event-link-screen-v1",
    "features": list(FEATURES), "fixed_cosine_grid": list(THRESHOLDS),
    "additional_boundaries": "all unique development feature cosines, before labels",
    "publication_gates_days": list(PUBLICATION_GATES),
    "comparison": "feature_cosine >= threshold; optional publication gap <= gate",
    "nonselected_outcome": "review", "population_estimate": False,
    "human_validated": False, "accepted_dossiers": 0,
    "development": {"minimum_pessimistic_precision_observed_and_weighted": .90,
                    "minimum_known_same_coverage_observed_and_weighted": .50,
                    "minimum_selected_same": 8, "minimum_distinct_positive_articles": 12,
                    "minimum_greedy_disjoint_positive_pairs": 4},
    "validation": {"minimum_pessimistic_precision_observed_and_weighted": .90,
                   "minimum_selected_pairs": 20, "minimum_selected_same": 5,
                   "minimum_distinct_positive_articles": 20,
                   "minimum_greedy_disjoint_positive_pairs": 8,
                   "recall_pass_claim": False},
    "ranking": ["weighted known-same coverage", "observed known-same coverage",
                "weighted pessimistic precision", "observed pessimistic precision",
                "publication gate preference None/30/7/1", "fixed feature order",
                "stricter cosine threshold"],
}
LIMITATIONS = [
    "Exploratory branch after a failed baseline; it does not change the original result.",
    "Model references are not human gold; candidate links are not accepted event dossiers.",
    "Non-selected, missing-date and uncertain pairs require review, not a different-event label.",
    "Sampling weights describe the registered pair frame, not validated population inference.",
    "Publication gaps are reporting-time filters, never event dates or event-identity evidence.",
    "Pair-link performance does not establish complete-link cluster event identity or recall.",
    "Greedy disjoint-pair support is a deterministic lower bound, not a maximum matching.",
    "Development selection is adaptive; validation must be opened once after freezing one candidate.",
]


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be finite numeric")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be finite numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite numeric")
    return result


def _rows(rows: Sequence[Mapping[str, Any]], phase: str) -> list[dict[str, Any]]:
    if phase not in {"development", "validation"}:
        raise ValueError("phase must be development or validation")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    edges: set[tuple[str, str]] = set()
    for source in rows:
        if source.get("fold") != phase:
            continue
        row = dict(source)
        for name in ("pair_id", "left", "right"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError(f"{name} must be a nonempty string")
        edge = tuple(sorted((row["left"], row["right"])))
        if edge[0] == edge[1] or row["pair_id"] in seen or edge in edges:
            raise ValueError("self-pairs and duplicate pair identities are forbidden")
        seen.add(row["pair_id"])
        edges.add(edge)
        probability = _number(row.get("inclusion_probability"), "inclusion_probability")
        if not 0 < probability <= 1 or not math.isfinite(1 / probability):
            raise ValueError("inclusion_probability must be in (0, 1] with finite weight")
        row["weight"] = 1 / probability
        gap = row.get("publication_gap_days")
        row["publication_gap_days"] = None if gap is None else _number(gap, "publication gap")
        if row["publication_gap_days"] is not None and row["publication_gap_days"] < 0:
            raise ValueError("publication gap must be nonnegative")
        result.append(row)
    return sorted(result, key=lambda row: row["pair_id"])


def _label(judgment: Any) -> str:
    if not isinstance(judgment, Mapping):
        return "pending" if judgment is None else "invalid"
    status = judgment.get("status")
    if status == "completed":
        label = judgment.get("label")
        return str(label) if label in LABELS[:3] else "invalid"
    return status if isinstance(status, str) and status in {"failed", "pending", "unknown"} else "invalid"


def _feature(row: Mapping[str, Any], name: str) -> float | None:
    features = row.get("features")
    if not isinstance(features, Mapping):
        return None
    try:
        value = _number(features.get(name), name)
    except ValueError:
        return None
    return value if -1 <= value <= 1 else None


def _candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    feature = candidate.get("feature")
    if feature not in FEATURES:
        raise ValueError("unregistered feature")
    threshold = _number(candidate.get("threshold"), "threshold")
    if not -1 <= threshold <= 1:
        raise ValueError("cosine threshold must be in [-1, 1]")
    gate = candidate.get("publication_gap_days")
    if isinstance(gate, bool) or gate not in PUBLICATION_GATES:
        raise ValueError("unregistered publication gate")
    return {"feature": feature, "threshold": threshold, "publication_gap_days": gate}


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _weights(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"sum": 0., "effective_sample_size": 0., "maximum_weight_share": None}
    values = [row["weight"] for row in rows]
    largest = max(values)
    scaled = [value / largest for value in values]
    total = math.fsum(values)
    if not math.isfinite(total):
        raise ValueError("sampling weight total is not finite")
    return {"sum": total,
            "effective_sample_size": math.fsum(scaled) ** 2 / math.fsum(x*x for x in scaled),
            "maximum_weight_share": largest / total}


def _counts(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, int], dict[str, float]]:
    observed = Counter(row["reference_label"] for row in rows)
    return ({label: observed[label] for label in LABELS},
            {label: math.fsum(row["weight"] for row in rows if row["reference_label"] == label)
             for label in LABELS})


def _metrics(rows: list[dict[str, Any]], candidate: dict[str, Any], phase: str,
             feature_errors: list[dict[str, str]], include_ids: bool = True) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    gate = candidate["publication_gap_days"]
    for row in rows:
        value = _feature(row, candidate["feature"])
        gap = row["publication_gap_days"]
        accepted = (value is not None and value >= candidate["threshold"]
                    and (gate is None or gap is not None and gap <= gate))
        (selected if accepted else review).append(row)
    counts, weighted = _counts(rows)
    selected_counts, selected_weighted = _counts(selected)
    review_counts, review_weighted = _counts(review)
    support = [row for row in selected if row["reference_label"] == "same_event"]
    positive_articles = {row[key] for row in support for key in ("left", "right")}
    used: set[str] = set()
    matching: list[str] = []
    for row in sorted(support, key=lambda x: (min(x["left"], x["right"]),
                                             max(x["left"], x["right"]), x["pair_id"])):
        if not used.intersection((row["left"], row["right"])):
            used.update((row["left"], row["right"]))
            matching.append(row["pair_id"])
    observed_precision = _ratio(selected_counts["same_event"], len(selected))
    weighted_precision = _ratio(selected_weighted["same_event"], _weights(selected)["sum"])
    observed_coverage = _ratio(selected_counts["same_event"], counts["same_event"])
    weighted_coverage = _ratio(selected_weighted["same_event"], weighted["same_event"])
    complete = bool(rows) and not feature_errors and not any(counts[x] for x in LABELS[3:])
    reasons: list[str] = []
    if not complete:
        reasons.append("incomplete_features_or_references")
    for name, value in (("observed", observed_precision), ("weighted", weighted_precision)):
        if value is None or value + 1e-12 < .90:
            reasons.append(f"pessimistic_precision_{name}_below_0.90")
    if phase == "development":
        for name, value in (("observed", observed_coverage), ("weighted", weighted_coverage)):
            if value is None or value + 1e-12 < .50:
                reasons.append(f"known_same_coverage_{name}_below_0.50")
    minimum = POLICY[phase]
    if selected_counts["same_event"] < minimum["minimum_selected_same"]:
        reasons.append("insufficient_selected_same_support")
    if len(positive_articles) < minimum["minimum_distinct_positive_articles"]:
        reasons.append("insufficient_distinct_positive_articles")
    if len(matching) < minimum["minimum_greedy_disjoint_positive_pairs"]:
        reasons.append("insufficient_disjoint_positive_pairs")
    if phase == "validation" and len(selected) < minimum["minimum_selected_pairs"]:
        reasons.append("insufficient_validation_auto_links")
    result: dict[str, Any] = {
        "phase": phase, "processing_complete": complete, "eligible": not reasons,
        "eligibility_reasons": reasons, "total_pairs": len(rows), "auto_link_pairs": len(selected),
        "review_pairs": len(review), "all_label_counts": counts,
        "selected_label_counts": selected_counts, "review_label_counts": review_counts,
        "all_weighted_label_totals": weighted, "selected_weighted_label_totals": selected_weighted,
        "review_weighted_label_totals": review_weighted,
        "precision_pessimistic_observed": observed_precision,
        "precision_pessimistic_weighted": weighted_precision,
        "known_same_coverage_observed": observed_coverage,
        "known_same_coverage_weighted": weighted_coverage,
        "selected_uncertain": selected_counts["uncertain"],
        "uncertain_reference_coverage": _ratio(selected_counts["uncertain"], counts["uncertain"]),
        "distinct_positive_articles": len(positive_articles),
        "disjoint_positive_pair_lower_bound": len(matching),
        "all_sampling_weights": _weights(rows), "selected_sampling_weights": _weights(selected),
        "unknown_publication_gap_pairs": sum(row["publication_gap_days"] is None for row in rows),
        "recall_pass_claim": False, "population_estimate": False,
        "human_validated": False, "accepted_dossiers": 0,
    }
    if include_ids:
        result.update(selected_pair_ids=[row["pair_id"] for row in selected],
                      review_pair_ids=[row["pair_id"] for row in review],
                      disjoint_positive_pair_ids=matching)
    return result


def _rank(candidate: dict[str, Any]) -> tuple[float, ...]:
    metrics = candidate["metrics"]
    values = [metrics[key] if metrics[key] is not None else -1. for key in (
        "known_same_coverage_weighted", "known_same_coverage_observed",
        "precision_pessimistic_weighted", "precision_pessimistic_observed")]
    return (*values, -PUBLICATION_GATES.index(candidate["publication_gap_days"]),
            -FEATURES.index(candidate["feature"]), candidate["threshold"])


def _prepare(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any], phase: str,
             features: Sequence[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    prepared = _rows(rows, phase)
    errors = []
    for row in prepared:
        row["reference_label"] = _label(judgments.get(row["pair_id"]))
        for feature in features:
            if _feature(row, feature) is None:
                errors.append({"pair_id": row["pair_id"], "feature": feature,
                               "reason": "missing_nonfinite_or_invalid_cosine"})
    return prepared, errors


def evaluate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any],
             phase: str = "development", candidate: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compare all registered development variants; never inspect held-out labels."""
    if phase == "validation":
        if candidate is None:
            raise ValueError("validation requires a previously frozen candidate")
        return validate(rows, judgments, candidate)
    if phase != "development" or candidate is not None:
        raise ValueError("development selection does not accept a candidate")
    prepared, errors = _prepare(rows, judgments, phase, FEATURES)
    grid: list[dict[str, Any]] = []
    variants: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    for feature in FEATURES:
        boundaries = sorted(set(THRESHOLDS) | {value for row in prepared
                                             if (value := _feature(row, feature)) is not None})
        for gate in PUBLICATION_GATES:
            choices = []
            for threshold in boundaries:
                parameters = {"feature": feature, "threshold": threshold,
                              "publication_gap_days": gate}
                item: dict[str, Any] = {
                    **parameters, "metrics": _metrics(prepared, parameters, phase, errors, False),
                }
                grid.append(item)
                if item["metrics"]["eligible"]:
                    choices.append(item)
            best = max(choices, key=_rank) if choices else None
            if best is not None:
                best = {**best, "metrics": _metrics(prepared, best, phase, errors)}
                eligible.append(best)
            variants.append({"feature": feature, "publication_gap_days": gate,
                             "evaluated_count": len(boundaries), "eligible_count": len(choices),
                             "best_candidate": best})
    counts, _ = _counts(prepared)
    return {"phase": phase, "policy": deepcopy(POLICY), "row_count": len(prepared),
            "all_label_counts": counts, "feature_errors": errors,
            "processing_complete": bool(prepared) and not errors and not any(counts[x] for x in LABELS[3:]),
            "candidates": variants, "best_candidate": max(eligible, key=_rank) if eligible else None,
            "full_grid": grid, "limitations": list(LIMITATIONS)}


def validate(rows: Sequence[Mapping[str, Any]], judgments: Mapping[str, Any],
             candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate one frozen screen. This has no holdout-opening or budget side effects."""
    parameters = _candidate(candidate)
    prepared, errors = _prepare(rows, judgments, "validation", [parameters["feature"]])
    metrics = _metrics(prepared, parameters, "validation", errors)
    return {"phase": "validation", "candidate": parameters, "metrics": metrics,
            "feature_errors": errors, "policy": deepcopy(POLICY), "limitations": list(LIMITATIONS),
            "status": "provisional_model_reference_pass" if metrics["eligible"] else "inconclusive"}
