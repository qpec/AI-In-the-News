"""Source-free probability sampling and finite-population pair evaluation.

These functions neither inspect sources nor run research. An audited adapter must
freeze the article frame, disjoint retrieval strata, allocation, seed and reference
protocol before drawing/judging, and persist inputs/results through Research.execute.
The estimand is the micro-average over *unordered article pairs*, not event counts,
equal-event recall, or whole-group purity. Multi-event articles require a separately
registered binary pair relation; these helpers cannot validate its semantics.

Each nonempty stratum receives independent SRS without replacement. Retrieval
channels enrich the between-group sample; their entire complement remains a
positive-probability random tail. Unranking avoids enumerating O(articles**2)
pairs. Seeded PRNG draws assume a preregistered seed chosen independently of labels;
they are reproducible computational randomization, not certified random entropy.

Exact hypergeometric inversion plus Bonferroni provides conservative simultaneous
count intervals. It does not mistake an all-negative tail sample for proof of no
misses. It conditions on fixed, correct reference labels: correlated model error,
human disagreement, adaptive label selection, and cluster/anchor sampling need
separate methods. Shared articles do not invalidate pair-SRS design inference for
fixed labels; they do invalidate treating judgments as independent Bernoulli trials.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, cast

from scipy.stats import hypergeom

METHOD = "event-pair-stratified-srswor-v1"
WITHIN = "within_group"
TAIL = "between:random_tail"
PAIR_LABELS = frozenset({"same_event", "different_event", "uncertain", "failed", "pending", "unknown"})
Json = dict[str, Any]
Pair = tuple[str, str]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def pair_id(left: str, right: str) -> str:
    """Stable ID of a canonical unordered non-self pair (not an evidence ID)."""
    if any(not isinstance(item, str) or not item.strip() for item in (left, right)) or left == right:
        raise ValueError("Pair endpoints must be distinct nonblank strings")
    return hashlib.sha256(_json(sorted((left, right))).encode("utf-8")).hexdigest()


def _frame(groups: Mapping[str, Sequence[str]], channels: Mapping[str, Sequence[Sequence[str]]]) -> Json:
    if not isinstance(groups, Mapping) or not isinstance(channels, Mapping):
        raise ValueError("Groups and candidate channels must be mappings")
    if any(not isinstance(key, str) or not key.strip() for key in groups):
        raise ValueError("Group identifiers must be nonblank strings")
    membership: dict[str, str] = {}
    canonical: dict[str, list[str]] = {}
    for group in sorted(groups):
        values = groups[group]
        if isinstance(values, (str, bytes)) or not isinstance(values, Sequence) or not values:
            raise ValueError("Every group must have a nonempty sequence of members")
        if any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError("Article identifiers must be nonblank strings")
        for item in values:
            if item in membership:
                raise ValueError("Articles must occur in exactly one frozen group")
            membership[item] = group
        canonical[group] = sorted(values)
    if any(not isinstance(key, str) or not key.strip() or key == "random_tail" for key in channels):
        raise ValueError("Channel identifiers must be nonblank and cannot be random_tail")
    pairs: dict[str, list[Pair]] = {}
    frozen_channels: dict[str, list[list[str]]] = {}
    assigned: set[Pair] = set()
    for channel in sorted(channels):
        channel_values = channels[channel]
        if isinstance(channel_values, (str, bytes)) or not isinstance(channel_values, Sequence):
            raise ValueError("Each channel must contain endpoint pairs")
        unique: set[Pair] = set()
        for endpoints in channel_values:
            if (isinstance(endpoints, (str, bytes)) or not isinstance(endpoints, Sequence)
                    or len(endpoints) != 2):
                raise ValueError("Each candidate must contain exactly two endpoints")
            left, right = endpoints
            pair_id(left, right)
            if left not in membership or right not in membership:
                raise ValueError("Candidate endpoint outside the frozen article frame")
            unique.add((min(left, right), max(left, right)))
        frozen_channels[channel] = [list(pair) for pair in sorted(unique)]
        # Within-group candidates already belong to the exhaustive within stratum.
        selected = {pair for pair in unique if membership[pair[0]] != membership[pair[1]]} - assigned
        pairs["between:" + channel] = sorted(selected)
        assigned.update(selected)
    article_ids = sorted(membership)
    sizes = {WITHIN: sum(len(items) * (len(items) - 1) // 2 for items in canonical.values()),
             **{name: len(items) for name, items in pairs.items()}}
    sizes[TAIL] = len(article_ids) * (len(article_ids) - 1) // 2 - sum(sizes.values())
    return {"groups": canonical, "membership": membership, "article_ids": article_ids,
            "channels": frozen_channels, "retrieved_pairs": pairs, "assigned": assigned, "sizes": sizes}


def pair_stratum_sizes(
    groups: Mapping[str, Sequence[str]], candidate_channels: Mapping[str, Sequence[Sequence[str]]] | None = None,
) -> dict[str, int]:
    """Exact sizes of disjoint within/retrieval/tail strata, without pair expansion."""
    return dict(_frame(groups, candidate_channels or {})["sizes"])


def _unrank_pair(ids: Sequence[str], rank: int) -> Pair:
    size = len(ids)
    low, high = 0, size - 2
    while low < high:
        middle = (low + high + 1) // 2
        start = middle * (2 * size - middle - 1) // 2
        if start <= rank:
            low = middle
        else:
            high = middle - 1
    start = low * (2 * size - low - 1) // 2
    return ids[low], ids[low + 1 + rank - start]


def _tail_unranker(frame: Json) -> Any:
    ids, membership = frame["article_ids"], frame["membership"]
    positions = {item: index for index, item in enumerate(ids)}
    group_positions = {group: sorted(positions[item] for item in members)
                       for group, members in frame["groups"].items()}
    excluded: dict[int, list[int]] = {}
    for left, right in frame["assigned"]:
        excluded.setdefault(positions[left], []).append(positions[right])
    for values in excluded.values():
        values.sort()
    cumulative = [0]
    for i, item in enumerate(ids):
        mates = group_positions[membership[item]]
        count = len(ids) - i - 1 - (len(mates) - bisect.bisect_right(mates, i)) - len(excluded.get(i, []))
        cumulative.append(cumulative[-1] + count)

    def unrank(rank: int) -> Pair:
        i = bisect.bisect_right(cumulative, rank) - 1
        position = rank - cumulative[i]
        mates, candidates = group_positions[membership[ids[i]]], excluded.get(i, [])
        before = bisect.bisect_right(mates, i)
        low, high = i + 1, len(ids) - 1
        while low < high:
            middle = (low + high) // 2
            available = middle - i - (bisect.bisect_right(mates, middle) - before)
            available -= bisect.bisect_right(candidates, middle)
            if available > position:
                high = middle
            else:
                low = middle + 1
        return ids[i], ids[low]

    return unrank


def build_pair_design(
    groups: Mapping[str, Sequence[str]], candidate_channels: Mapping[str, Sequence[Sequence[str]]] | None = None,
    *, sample_sizes: Mapping[str, int], seed: str,
) -> Json:
    """Draw complete-support pair-SRS strata; no source text, I/O or authorization.

    ``sample_sizes`` must name every nonempty stratum with n >= 1. Values above
    N become a census. Unknown strata are rejected, even when their allocation
    is zero. Retrieval overlap is resolved by lexicographic channel precedence.
    A noncensus stratum with n=1 supports count intervals, but not variance
    estimation. Allocation must be fixed before inspecting evaluation labels.
    """
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("A preregistered nonblank seed is required")
    frame = _frame(groups, candidate_channels or {})
    sizes = frame["sizes"]
    if not isinstance(sample_sizes, Mapping) or set(sample_sizes) - set(sizes):
        raise ValueError("Allocation contains an unknown stratum")
    if any(type(value) is not int or value < 0 for value in sample_sizes.values()):
        raise ValueError("Sample sizes must be nonnegative integers")
    if any(size and sample_sizes.get(name, 0) < 1 for name, size in sizes.items()):
        raise ValueError("Every nonempty stratum needs positive inclusion probability")
    group_lists = [items for items in frame["groups"].values() if len(items) >= 2]
    cumulative = [0]
    for items in group_lists:
        cumulative.append(cumulative[-1] + len(items) * (len(items) - 1) // 2)
    tail_unrank = _tail_unranker(frame)
    strata: list[Json] = []
    selected: list[Json] = []
    for name, size in sizes.items():
        requested = sample_sizes.get(name, 0)
        drawn = min(requested, size)
        random_seed = hashlib.sha256(_json([METHOD, seed, name]).encode("utf-8")).digest()
        ranks = sorted(random.Random(random_seed).sample(range(size), drawn))
        pi = drawn / size if size else None
        strata.append({"stratum": name, "N": size, "n": drawn, "requested_n": requested,
                       "pi": pi, "sampled_ranks": ranks,
                       "pairwise_pi": drawn * (drawn - 1) / (size * (size - 1)) if size > 1 else None})
        for rank in ranks:
            if name == WITHIN:
                group_index = bisect.bisect_right(cumulative, rank) - 1
                left, right = _unrank_pair(group_lists[group_index], rank - cumulative[group_index])
            elif name == TAIL:
                left, right = tail_unrank(rank)
            else:
                left, right = frame["retrieved_pairs"][name][rank]
            selected.append({"pair_id": pair_id(left, right), "left": left, "right": right,
                             "stratum": name, "pi": pi})
    return {"method": METHOD, "seed": seed, "groups": frame["groups"],
            "candidate_channels": frame["channels"], "sample_sizes": dict(sample_sizes),
            "article_count": len(frame["article_ids"]), "population_pairs": sum(sizes.values()),
            "strata": strata, "selected_pairs": selected, "full_support": True,
            "sampling_unit": "unordered_article_pair", "randomization": "preregistered-seeded-PRNG-SRSWOR",
            "retrieval_overlap": "lexicographic channel precedence; within_group first",
            "authorization_granted": False}


def finite_population_positive_interval(N: int, n: int, positives: int, *, tail_alpha: float) -> list[int]:
    """Invert SRSWOR hypergeometric tails for an integer positive population total.

    Both excluded tails have probability at most ``tail_alpha``. This is
    finite-population sampling uncertainty, conditional on correct fixed labels.
    No normal/binomial approximation or zero-count variance shortcut is used.
    """
    if any(type(value) is not int for value in (N, n, positives)) or not 0 <= positives <= n <= N:
        raise ValueError("Require integer 0 <= positives <= n <= N")
    if not isinstance(tail_alpha, (int, float)) or not math.isfinite(tail_alpha) or not 0 < tail_alpha < .5:
        raise ValueError("tail_alpha must be finite and between zero and one half")
    if n == 0:
        return [0, N]
    if n == N:
        return [positives, positives]
    threshold = math.log(tail_alpha)
    low, high = positives, N - n + positives
    # P_M(X >= observed) increases with population positives M.
    while low < high:
        middle = (low + high) // 2
        if float(hypergeom.logsf(positives - 1, N, middle, n)) >= threshold:
            high = middle
        else:
            low = middle + 1
    lower = low
    low, high = positives, N - n + positives
    # P_M(X <= observed) decreases with M.
    while low < high:
        middle = (low + high + 1) // 2
        if float(hypergeom.logcdf(positives, N, middle, n)) >= threshold:
            low = middle
        else:
            high = middle - 1
    return [lower, low]


def _ratio_bounds(inside: Sequence[float], outside: Sequence[float]) -> Json:
    li, ui = inside
    lo, uo = outside
    if ui + uo == 0:
        lower = upper = None
    else:
        lower = li / (li + uo) if li + uo else 1.0
        upper = ui / (ui + lo) if ui + lo else 0.0
    return {"lower": lower, "upper": upper, "conditional_on_nonzero_same_event_denominator": True,
            "zero_denominator_possible": li + lo == 0}


def estimate_pair_metrics(
    design: Mapping[str, Any], judgments: Sequence[Mapping[str, Any]], *, reference_kind: str,
    confidence_level: float = .95,
) -> Json:
    """HT pair totals/precision and a ratio-of-HT-totals recall, with uncertainty.

    Judgment rows contain ``pair_id,label`` or ``left,right,label``; absent
    selected pairs are pending. Human/model runs must be analyzed separately;
    reference_kind records provenance, not authenticated adjudication. No point
    estimate silently drops unresolved references. Weighted missingness bounds
    are plug-in bounds, *not population identification or confidence intervals*.
    Joint confidence intervals also cover unsampled pairs and remain useful
    when rare missed positives have not been observed in the random tail.
    """
    if reference_kind not in {"human", "model"}:
        raise ValueError("Declare separate human or model references")
    if (not isinstance(confidence_level, (int, float)) or not math.isfinite(confidence_level)
            or not 0 < confidence_level < 1):
        raise ValueError("confidence_level must be finite and between zero and one")
    expected = build_pair_design(design["groups"], design["candidate_channels"],
                                 sample_sizes=design["sample_sizes"], seed=design["seed"])
    if dict(design) != expected:
        raise ValueError("Frozen design differs from its frame, allocation or seeded sample")
    selected = {row["pair_id"]: row for row in expected["selected_pairs"]}
    outcomes: dict[str, str] = {}
    for row in judgments:
        if not isinstance(row, Mapping) or set(row) - {"pair_id", "left", "right", "label"}:
            raise ValueError("Judgments need only pair identity and label")
        identifier = row.get("pair_id")
        if "left" in row or "right" in row:
            actual_id = pair_id(cast(str, row.get("left")), cast(str, row.get("right")))
            if identifier is not None and identifier != actual_id:
                raise ValueError("Judgment pair identifiers disagree")
            identifier = actual_id
        if not isinstance(identifier, str) or identifier not in selected:
            raise ValueError("Judgment outside the selected pair frame")
        if identifier in outcomes:
            raise ValueError("Duplicate unordered pair judgment")
        if row.get("label") not in PAIR_LABELS:
            raise ValueError("Unsupported pair judgment label")
        outcomes[identifier] = row["label"]
    counts = Counter({label: 0 for label in PAIR_LABELS})
    strata_results: list[Json] = []
    active_count = sum(bool(item["N"]) for item in expected["strata"])
    alpha = (1 - confidence_level) / (2 * max(active_count, 1))
    by_stratum: dict[str, list[str]] = {item["stratum"]: [] for item in expected["strata"]}
    for identifier, pair in selected.items():
        label = outcomes.get(identifier, "pending")
        by_stratum[pair["stratum"]].append(label)
        counts[label] += 1
    for stratum in expected["strata"]:
        name, N, n = stratum["stratum"], stratum["N"], stratum["n"]
        labels = Counter(by_stratum[name])
        same, different = labels["same_event"], labels["different_event"]
        unresolved = n - same - different
        weight = N / n if n else 0.0
        variance = None
        if not unresolved:
            if n == N:
                variance = 0.0
            elif n > 1:
                fraction = same / n
                variance = N * N * (1 - n / N) * fraction * (1 - fraction) / (n - 1)
        lower = finite_population_positive_interval(N, n, same, tail_alpha=alpha)[0]
        upper = finite_population_positive_interval(N, n, same + unresolved, tail_alpha=alpha)[1]
        strata_results.append({"stratum": name, "N": N, "n": n, "pi": stratum["pi"],
            "counts": {label: labels[label] for label in sorted(PAIR_LABELS)},
            "ht_same": same * weight, "ht_different": different * weight,
            "ht_unresolved": unresolved * weight, "ht_total_variance_estimate": variance,
            "positive_count_confidence_interval": [lower, upper],
            "finite_population_correction": 1 - n / N if N else None})

    def aggregate(rows: Sequence[Json]) -> Json:
        N, n = sum(row["N"] for row in rows), sum(row["n"] for row in rows)
        same = sum(row["ht_same"] for row in rows)
        unknown = sum(row["ht_unresolved"] for row in rows)
        different = sum(row["ht_different"] for row in rows)
        squared_weights = sum(row["n"] * (row["N"] / row["n"]) ** 2 for row in rows if row["n"])
        variances = [row["ht_total_variance_estimate"] for row in rows]
        return {"N": N, "n": n, "ht_same": same, "ht_different": different, "ht_unresolved": unknown,
                "weighted_missingness_count_bounds": [same, same + unknown],
                "positive_count_confidence_interval": [sum(row["positive_count_confidence_interval"][0] for row in rows),
                                                       sum(row["positive_count_confidence_interval"][1] for row in rows)],
                "ht_total_variance_estimate": sum(variances) if all(item is not None for item in variances) else None,
                "kish_weight_effective_n": N * N / squared_weights if squared_weights else None,
                "complete_case_positive_fraction_diagnostic": same / (same + different) if same + different else None}

    inside = aggregate([row for row in strata_results if row["stratum"] == WITHIN])
    outside = aggregate([row for row in strata_results if row["stratum"] != WITHIN])
    candidate = aggregate([row for row in strata_results if row["stratum"] not in {WITHIN, TAIL}])
    tail = aggregate([row for row in strata_results if row["stratum"] == TAIL])
    complete = not (inside["ht_unresolved"] + outside["ht_unresolved"])
    point_precision = (inside["ht_same"] / inside["N"]
                       if not inside["ht_unresolved"] and inside["N"] else None)
    denominator = inside["ht_same"] + outside["ht_same"]
    point_recall = inside["ht_same"] / denominator if complete and denominator else None
    recall_variance = None
    if point_recall is not None and all(part["ht_total_variance_estimate"] is not None for part in (inside, outside)):
        recall_variance = ((1 - point_recall) ** 2 * inside["ht_total_variance_estimate"]
                           + point_recall ** 2 * outside["ht_total_variance_estimate"]) / denominator ** 2
    return {"method": METHOD, "reference_kind": reference_kind,
        "human_validated": False,
        "human_validation_status": "Not established by this arithmetic; human provenance/adjudication is external",
        "estimand": "Micro precision/recall over unordered article pairs in the complete frozen article frame",
        "expected_pairs": len(selected), "returned_judgments": len(outcomes), "counts": dict(sorted(counts.items())),
        "complete_references": complete, "within": inside, "between": outside, "retrieved_between": candidate,
        "random_tail": tail, "strata": strata_results,
        "pair_precision": {"point": point_precision,
            "weighted_missingness_bounds": [value / inside["N"] for value in inside["weighted_missingness_count_bounds"]]
                if inside["N"] else None,
            "confidence_interval": [value / inside["N"] for value in inside["positive_count_confidence_interval"]]
                if inside["N"] else None,
            "design_variance_estimate": inside["ht_total_variance_estimate"] / inside["N"] ** 2
                if inside["N"] and inside["ht_total_variance_estimate"] is not None else None},
        "pair_recall": {"point": point_recall,
            "complete_case_ratio_diagnostic": inside["ht_same"] / denominator if denominator else None,
            "weighted_missingness_bounds": _ratio_bounds(inside["weighted_missingness_count_bounds"],
                                                         outside["weighted_missingness_count_bounds"]),
            "confidence_interval": _ratio_bounds(inside["positive_count_confidence_interval"],
                                                 outside["positive_count_confidence_interval"]),
            "linearized_design_variance_diagnostic": recall_variance,
            "zero_observed_between_positives": outside["ht_same"] == 0,
            "corpus_recall_status": "Frozen-frame pair recall only; no claim outside this frame; interval width determines informativeness"},
        "candidate_pool_recall": {"point": inside["ht_same"] / (inside["ht_same"] + candidate["ht_same"])
                if not (inside["ht_unresolved"] + candidate["ht_unresolved"])
                and inside["ht_same"] + candidate["ht_same"] else None,
            "scope": "Within pairs plus retrieved between pairs, excludes random-tail population",
            "not_corpus_recall": True},
        "whole_group_purity": None, "whole_group_purity_status": "Requires a separate complete-group reference design",
        "confidence": {"level": confidence_level,
            "method": "Exact hypergeometric count inversion; Bonferroni simultaneous stratum bounds",
            "tail_alpha_per_stratum": alpha, "conditional_on_correct_fixed_reference_labels": True},
        "limitations": ["Ratio of HT totals is not exactly design-unbiased; HT component totals are",
            "Weighted missingness bounds are plug-in sample estimates, not population identified bounds",
            "Variance and Kish size are diagnostics; zero sample variance is not certainty and Kish size is not independent events",
            "Model references are not human gold; intervals omit reference error and event-definition uncertainty",
            "Inference requires registered pair-SRS; anchor/cluster/adaptive samples need joint inclusion probabilities",
            "Article-pair metrics weight large events quadratically; they do not estimate equal-event or whole-group quality",
            "A rare-positive random tail may leave corpus recall nearly uninformative; no fixed small budget guarantees precision"]}
