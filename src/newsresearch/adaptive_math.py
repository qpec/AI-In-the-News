"""Pure calculations for the registered, bounded adaptive cutoff method.

These functions do not access sources, storage, models, or the network. The
audited workflow must freeze their inputs and save their outputs before the
next research operation. Labels are model references, never human gold.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class FrameItem:
    source_id: str
    score: float
    group_id: str


@dataclass(frozen=True)
class Draw:
    source_id: str
    probability: float
    round_index: int = 0
    draw_index: int = 0


Frame = Sequence[FrameItem]
Labels = Mapping[str, str | None]


def _frame(frame: Frame) -> list[FrameItem]:
    ordered = sorted(frame, key=lambda item: item.source_id)
    if not ordered:
        raise ValueError("The scored frame must not be empty")
    if len({item.source_id for item in ordered}) != len(ordered):
        raise ValueError("Source IDs must be unique")
    for item in ordered:
        if not item.source_id or not item.group_id or not math.isfinite(item.score):
            raise ValueError("Frame items require nonempty IDs/groups and finite scores")
    return ordered


def _rng(seed: int, state: Mapping[str, Any] | None) -> np.random.Generator:
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ValueError("The registered seed must be a nonnegative integer")
    generator = np.random.Generator(np.random.PCG64(seed))
    if state is not None:
        if state.get("bit_generator") != "PCG64":
            raise ValueError("Only registered PCG64 state can be resumed")
        generator.bit_generator.state = copy.deepcopy(dict(state))
    return generator


def split_frame(frame: Frame, heldout_size: int, seed: int) -> dict[str, Any]:
    """Reserve SRS articles, then exclude their whole groups from development.

    ``heldout_draw_ids`` preserves selection order; ``heldout_ids`` and the
    development IDs use the registered lexicographic source order. No labels
    are accepted here. A group is a frozen leakage-control group, not an event
    coreference finding.
    """
    ordered = _frame(frame)
    if (
        not isinstance(heldout_size, int) or isinstance(heldout_size, bool)
        or not 0 < heldout_size < len(ordered)
    ):
        raise ValueError("The holdout must contain at least one and fewer than all articles")
    generator = _rng(seed, None)
    state_before = copy.deepcopy(generator.bit_generator.state)
    indices = generator.choice(len(ordered), size=heldout_size, replace=False)
    selected = [ordered[int(index)] for index in indices]
    heldout = {item.source_id for item in selected}
    groups = {item.group_id for item in selected}
    development = [item.source_id for item in ordered if item.group_id not in groups]
    if not development:
        raise ValueError("Held-out reporting groups leave no development frame")
    extra = [item.source_id for item in ordered if item.group_id in groups and item.source_id not in heldout]
    return {
        "selection": "SRS_without_replacement_before_labels",
        "source_order": [item.source_id for item in ordered],
        "frame_size": len(ordered),
        "heldout_draw_ids": [item.source_id for item in selected],
        "heldout_ids": sorted(heldout),
        "heldout_group_ids": sorted(groups),
        "development_ids": development,
        "extra_development_exclusions": extra,
        "heldout_size": len(heldout),
        "development_size": len(development),
        "seed": seed,
        "rng": "numpy.random.Generator(PCG64)",
        "numpy_version": np.__version__,
        "rng_state_before": state_before,
        "rng_state_after": copy.deepcopy(generator.bit_generator.state),
    }


def sample_round(
    development: Frame,
    draws: int,
    seed: int,
    round_index: int,
    candidate: float | None = None,
    window_size: int | None = None,
    *,
    rng_state: Mapping[str, Any] | None = None,
    starting_draw_index: int = 0,
) -> dict[str, Any]:
    """Freeze a complete with-replacement round and exact marginal q values.

    Without a candidate/window the round is uniform. An explicitly empty
    window also falls back to uniform. Chain ``rng_state_after`` into the
    next call, including the state returned by ``split_frame`` initially.
    Previously judged articles must remain in ``development``.
    """
    ordered = _frame(development)
    for value in (draws, round_index, starting_draw_index):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError("Draw count and round/draw indices must be nonnegative integers")
    if candidate is not None and not math.isfinite(candidate):
        raise ValueError("The prior candidate must be finite")
    if window_size is not None and (
        not isinstance(window_size, int) or isinstance(window_size, bool) or window_size < 0
    ):
        raise ValueError("Window size must be a nonnegative integer")
    window: list[FrameItem] = []
    if candidate is not None and window_size:
        window = sorted(ordered, key=lambda item: (abs(item.score - candidate), item.source_id))[
            :window_size
        ]
    window_ids = {item.source_id for item in window}
    generator = _rng(seed, rng_state)
    state_before = copy.deepcopy(generator.bit_generator.state)
    sampled: list[dict[str, Any]] = []
    population_size = len(ordered)
    for offset in range(draws):
        if window and generator.random() < 0.5:
            item = window[int(generator.integers(len(window)))]
        else:
            item = ordered[int(generator.integers(population_size))]
        probability = 1.0 / population_size
        if window:
            probability = 0.5 / population_size
            if item.source_id in window_ids:
                probability += 0.5 / len(window)
        sampled.append(asdict(Draw(item.source_id, probability, round_index, starting_draw_index + offset)))
    return {
        "round_index": round_index,
        "draws": sampled,
        "draw_count": draws,
        "replacement": True,
        "source_order": [item.source_id for item in ordered],
        "population_size": population_size,
        "window_ids": [item.source_id for item in window],
        "window_size": len(window),
        "requested_window_size": window_size,
        "prior_candidate": candidate,
        "global_mixture_weight": 0.5 if window else 1.0,
        "window_mixture_weight": 0.5 if window else 0.0,
        "probability_kind": "marginal_mixture_probability",
        "seed": seed,
        "rng": "numpy.random.Generator(PCG64)",
        "numpy_version": np.__version__,
        "rng_state_before": state_before,
        "rng_state_after": copy.deepcopy(generator.bit_generator.state),
    }


def _label(labels: Labels, source_id: str) -> str:
    label = labels.get(source_id)
    if label is None or label == "missing":
        return "missing"
    if label not in {"yes", "no", "uncertain"}:
        raise ValueError("Reference labels must be yes, no, uncertain, missing, or null")
    return label


def _metrics(tp: float, fp: float, fn: float, tn: float) -> dict[str, float | None]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f2": 5 * tp / (5 * tp + 4 * fn + fp) if 5 * tp + 4 * fn + fp else None,
    }


def _rules(recall_target: float, f2_tolerance: float, min_positive: int, min_negative: int) -> None:
    if not math.isfinite(recall_target) or not 0 < recall_target <= 1:
        raise ValueError("Recall target must be in (0, 1]")
    if not math.isfinite(f2_tolerance) or not 0 <= f2_tolerance <= 1:
        raise ValueError("F2 tolerance must be in [0, 1]")
    for minimum in (min_positive, min_negative):
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            raise ValueError("Class minimums must be positive integer counts of unique articles")


def select_cutoff(
    frame: Frame,
    draws: Sequence[Draw | Mapping[str, Any]],
    labels: Labels,
    recall_target: float = 0.95,
    f2_tolerance: float = 0.01,
    min_positive: int = 5,
    min_negative: int = 5,
) -> dict[str, Any]:
    """Select lower cutoff among near-best, recall-eligible pessimistic HH F2.

    The grid comes from the entire frozen scorerun frame, while q refers to
    its fixed development subset. Every draw, including duplicate and unknown
    draws, contributes with denominator m. Class minima count unique articles,
    preventing repeated draws from manufacturing reference-class coverage.
    Neither the selected ratio nor its maximum is an unbiased performance
    estimate. This function performs no independent validation.
    """
    ordered = _frame(frame)
    _rules(recall_target, f2_tolerance, min_positive, min_negative)
    lookup = {item.source_id: item for item in ordered}
    normalized: list[Draw] = []
    for index, draw in enumerate(draws):
        item = draw if isinstance(draw, Draw) else Draw(
            str(draw["source_id"]), float(draw["probability"]),
            int(draw.get("round_index", 0)), int(draw.get("draw_index", index)),
        )
        if item.source_id not in lookup:
            raise ValueError("Every sampled source must belong to the frozen scorerun frame")
        if not math.isfinite(item.probability) or not 0 < item.probability <= 1:
            raise ValueError("Every draw requires its strictly positive marginal probability")
        normalized.append(item)
    if not normalized:
        raise ValueError("At least one registered draw is required")
    unique_counts = Counter(_label(labels, source_id) for source_id in {d.source_id for d in normalized})
    draw_counts = Counter(_label(labels, draw.source_id) for draw in normalized)
    score_weights: dict[float, dict[str, list[float]]] = {}
    for draw in normalized:
        score = lookup[draw.source_id].score
        label = _label(labels, draw.source_id)
        category = label if label in {"yes", "no"} else "unknown"
        buckets = score_weights.setdefault(score, {"yes": [], "no": [], "unknown": []})
        buckets[category].append(1.0 / draw.probability / len(normalized))
    bins = {
        score: {label: math.fsum(weights) for label, weights in categories.items()}
        for score, categories in score_weights.items()
    }
    totals = {label: math.fsum(bucket[label] for bucket in bins.values()) for label in ("yes", "no", "unknown")}
    below = {"yes": 0.0, "no": 0.0, "unknown": 0.0}
    grid_counts = Counter(item.score for item in ordered)
    predicted_yes_count = len(ordered)
    sufficient = unique_counts["yes"] >= min_positive and unique_counts["no"] >= min_negative
    curve: list[dict[str, Any]] = []
    for cutoff in sorted(grid_counts):
        above = {label: max(0.0, totals[label] - below[label]) for label in totals}
        known = _metrics(above["yes"], above["no"], below["yes"], below["no"])
        pessimistic = _metrics(
            above["yes"], above["no"] + above["unknown"],
            below["yes"] + below["unknown"], below["no"],
        )
        optimistic = _metrics(
            above["yes"] + above["unknown"], above["no"],
            below["yes"], below["no"] + below["unknown"],
        )
        recall = pessimistic["recall"]
        curve.append({
            "cutoff": cutoff,
            "predicted_yes_count": predicted_yes_count,
            "predicted_no_count": len(ordered) - predicted_yes_count,
            "known_reference": known,
            "pessimistic": pessimistic,
            "optimistic": optimistic,
            "unknown_above_weight": above["unknown"],
            "unknown_below_weight": below["unknown"],
            "eligible": sufficient and recall is not None and recall >= recall_target,
        })
        for label in below:
            below[label] += bins.get(cutoff, {}).get(label, 0.0)
        predicted_yes_count -= grid_counts[cutoff]
    eligible = [point for point in curve if point["eligible"] and point["pessimistic"]["f2"] is not None]
    selected: dict[str, Any] | None = None
    best_f2: float | None = None
    if eligible:
        best_f2 = max(float(point["pessimistic"]["f2"]) for point in eligible)
        equivalent = [
            point for point in eligible
            if float(point["pessimistic"]["f2"]) >= best_f2 - f2_tolerance - 1e-12
        ]
        selected = min(equivalent, key=lambda point: point["cutoff"])
    reason = "candidate_selected_from_development_only"
    if not sufficient:
        reason = "insufficient_unique_clear_positive_or_negative_references"
    elif selected is None:
        reason = "no_candidate_meets_pessimistic_recall_target"
    return {
        "status": "candidate" if selected is not None else "inconclusive",
        "reason": reason,
        "cutoff": selected["cutoff"] if selected else None,
        "selected": selected,
        "best_eligible_pessimistic_f2": best_f2,
        "curve": curve,
        "grid_count": len(curve),
        "draw_count": len(normalized),
        "unique_drawn_count": sum(unique_counts.values()),
        "unique_reference_counts": {key: unique_counts[key] for key in ("yes", "no", "uncertain", "missing")},
        "draw_reference_counts": {key: draw_counts[key] for key in ("yes", "no", "uncertain", "missing")},
        "weighted_reference_totals": totals,
        "recall_target": recall_target,
        "f2_equivalence_tolerance": f2_tolerance,
        "minimum_unique_positive": min_positive,
        "minimum_unique_negative": min_negative,
        "comparison": "score >= cutoff",
        "estimator": "Hansen-Hurwitz mean of g / marginal_q over every draw",
        "reference_type": "model",
        "human_validated": False,
        "independently_validated": False,
    }


def _binomial_cdf(k: int, n: int, probability: float) -> float:
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if probability <= 0:
        return 1.0
    if probability >= 1:
        return 0.0
    log_p, log_q = math.log(probability), math.log1p(-probability)
    terms = [
        math.exp(
            math.lgamma(n + 1) - math.lgamma(x + 1) - math.lgamma(n - x + 1)
            + x * log_p + (n - x) * log_q
        )
        for x in range(k + 1)
    ]
    return min(1.0, max(0.0, math.fsum(terms)))


def binomial_interval(successes: int, trials: int, confidence: float = 0.95) -> list[float] | None:
    """Two-sided Clopper-Pearson interval by exact binomial-tail inversion.

    These are conservative binomial proportion intervals, not F2 intervals,
    simultaneous intervals, or human-validity estimates. A zero denominator
    is undefined, not perfect performance.
    """
    if not 0 < confidence < 1 or not math.isfinite(confidence):
        raise ValueError("Confidence must lie strictly between zero and one")
    if (
        not isinstance(successes, int) or isinstance(successes, bool)
        or not isinstance(trials, int) or isinstance(trials, bool)
        or not 0 <= successes <= trials
    ):
        raise ValueError("Binomial counts must be integers with 0 <= successes <= trials")
    if trials == 0:
        return None
    tail = (1 - confidence) / 2
    lower = 0.0
    if successes:
        left, right = 0.0, 1.0
        for _ in range(80):
            midpoint = (left + right) / 2
            survival = 1 - _binomial_cdf(successes - 1, trials, midpoint)
            if survival < tail:
                left = midpoint
            else:
                right = midpoint
        lower = (left + right) / 2
    upper = 1.0
    if successes < trials:
        left, right = 0.0, 1.0
        for _ in range(80):
            midpoint = (left + right) / 2
            if _binomial_cdf(successes, trials, midpoint) > tail:
                left = midpoint
            else:
                right = midpoint
        upper = (left + right) / 2
    return [lower, upper]


def _metric_intervals(metrics: Mapping[str, float | None], confidence: float) -> dict[str, Any]:
    tp, fp, fn = (int(metrics[name] or 0) for name in ("tp", "fp", "fn"))
    return {
        "precision": binomial_interval(tp, tp + fp, confidence),
        "recall": binomial_interval(tp, tp + fn, confidence),
        "f2": None,
        "f2_unavailable_reason": "No registered F2 interval is produced by this method",
    }


def evaluate_holdout(
    frame: Frame,
    labels: Labels,
    cutoff: float,
    recall_target: float = 0.95,
    confidence: float = 0.95,
    min_positive: int = 5,
    min_negative: int = 5,
    max_recall_interval_width: float = 0.25,
    *,
    max_unknown_fraction: float = 0.1,
    required_recall_lower_bound: float | None = None,
) -> dict[str, Any]:
    """Evaluate one already frozen cutoff without selecting another cutoff.

    Only the held-out frame belongs here. The caller enforces sealing and
    prior registration; this pure function cannot prove their timing. A point
    target and a lower-confidence-bound target are distinct registered rules.
    """
    ordered = _frame(frame)
    _rules(recall_target, 0.0, min_positive, min_negative)
    if not math.isfinite(cutoff):
        raise ValueError("The frozen cutoff must be finite")
    for proportion in (max_recall_interval_width, max_unknown_fraction):
        if not math.isfinite(proportion) or not 0 <= proportion <= 1:
            raise ValueError("Width and unknown-fraction limits must be in [0, 1]")
    if required_recall_lower_bound is not None and (
        not math.isfinite(required_recall_lower_bound) or not 0 <= required_recall_lower_bound <= 1
    ):
        raise ValueError("Required recall lower bound must be in [0, 1] or null")
    counts = Counter(_label(labels, item.source_id) for item in ordered)
    tp = fp = fn = tn = unknown_above = unknown_below = 0
    for item in ordered:
        label = _label(labels, item.source_id)
        predicted = item.score >= cutoff
        if label not in {"yes", "no"}:
            if predicted:
                unknown_above += 1
            else:
                unknown_below += 1
        elif predicted and label == "yes":
            tp += 1
        elif predicted:
            fp += 1
        elif label == "yes":
            fn += 1
        else:
            tn += 1
    known = _metrics(tp, fp, fn, tn)
    pessimistic = _metrics(tp, fp + unknown_above, fn + unknown_below, tn)
    optimistic = _metrics(tp + unknown_above, fp, fn, tn + unknown_below)
    intervals = {
        "known_reference_only": _metric_intervals(known, confidence),
        "pessimistic": _metric_intervals(pessimistic, confidence),
        "optimistic": _metric_intervals(optimistic, confidence),
    }
    interval = intervals["pessimistic"]["recall"]
    width = interval[1] - interval[0] if interval else None
    unknown_fraction = (unknown_above + unknown_below) / len(ordered)
    reasons: list[str] = []
    if counts["yes"] < min_positive or counts["no"] < min_negative:
        reasons.append("insufficient_clear_reference_classes")
    if unknown_fraction > max_unknown_fraction:
        reasons.append("too_many_uncertain_or_missing_references")
    if width is None or width > max_recall_interval_width:
        reasons.append("recall_interval_missing_or_too_wide")
    if required_recall_lower_bound is not None and (
        interval is None or interval[0] < required_recall_lower_bound
    ):
        reasons.append("recall_lower_bound_target_not_established")
    point_passes = pessimistic["recall"] is not None and pessimistic["recall"] >= recall_target
    status = "inconclusive" if reasons else "passed_model_reference" if point_passes else "failed"
    if not point_passes:
        reasons.append("pessimistic_recall_point_target_not_met")
    return {
        "status": status,
        "reasons": reasons,
        "cutoff": cutoff,
        "comparison": "score >= cutoff",
        "heldout_size": len(ordered),
        "reference_counts": {key: counts[key] for key in ("yes", "no", "uncertain", "missing")},
        "clear_reference_count": counts["yes"] + counts["no"],
        "processing_count": len(ordered) - counts["missing"],
        "clear_reference_coverage": (counts["yes"] + counts["no"]) / len(ordered),
        "unknown_above": unknown_above,
        "unknown_below": unknown_below,
        "unknown_fraction": unknown_fraction,
        "known_reference_only": known,
        "pessimistic": pessimistic,
        "optimistic": optimistic,
        "intervals": intervals,
        "interval_method": "two_sided_Clopper_Pearson_exact_binomial_tail_inversion",
        "confidence": confidence,
        "interval_assumptions": (
            "Fixed reference and cutoff; marginal binomial proportion intervals. "
            "The SRS-without-replacement design is treated conservatively without a finite-population "
            "correction. No simultaneous coverage, model-error correction, or human gold is claimed."
        ),
        "recall_target": recall_target,
        "point_recall_target_met": point_passes,
        "required_recall_lower_bound": required_recall_lower_bound,
        "max_recall_interval_width": max_recall_interval_width,
        "recall_interval_width": width,
        "max_unknown_fraction": max_unknown_fraction,
        "minimum_positive": min_positive,
        "minimum_negative": min_negative,
        "reference_type": "model",
        "human_validated": False,
        "cutoff_retuned": False,
    }
