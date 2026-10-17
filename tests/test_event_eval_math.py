"""Constructed identifiers/labels only; these tests establish no event accuracy."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from itertools import combinations

import pytest

from newsresearch.event_eval_math import (
    TAIL,
    WITHIN,
    build_pair_design,
    estimate_pair_metrics,
    finite_population_positive_interval,
    pair_id,
    pair_stratum_sizes,
)


def labels(design: dict, same: set[tuple[str, str]]) -> list[dict]:
    return [{"pair_id": row["pair_id"],
             "label": "same_event" if (row["left"], row["right"]) in same else "different_event"}
            for row in design["selected_pairs"]]


def test_disjoint_strata_cover_every_unordered_pair_once_without_direction_bias() -> None:
    groups = {"one": ["d", "a", "c"], "two": ["b", "f"], "singleton": ["e"]}
    channels = {"vector": [["a", "b"], ["b", "a"], ["c", "d"]],
                "keyword": [["a", "b"], ["b", "e"], ["f", "e"]]}
    sizes = pair_stratum_sizes(groups, channels)
    assert sizes == {WITHIN: 4, "between:keyword": 3, "between:vector": 0, TAIL: 8}
    design = build_pair_design(groups, channels, sample_sizes=sizes, seed="before-labels")
    pairs = [(row["left"], row["right"]) for row in design["selected_pairs"]]
    assert set(pairs) == set(combinations("abcdef", 2))
    assert len(pairs) == len(set(pairs)) == 15
    assert all(row["pi"] == 1 and row["left"] < row["right"] for row in design["selected_pairs"])
    assert pair_id("a", "b") == pair_id("b", "a")
    reverse = {name: list(reversed(members)) for name, members in reversed(list(groups.items()))}
    reversed_channels = {name: list(reversed(values)) for name, values in reversed(list(channels.items()))}
    assert design == build_pair_design(reverse, reversed_channels, sample_sizes=sizes, seed="before-labels")


def test_full_support_allocation_and_membership_are_required() -> None:
    groups = {"a": ["a", "b"], "b": ["c", "d"]}
    with pytest.raises(ValueError, match="positive inclusion"):
        build_pair_design(groups, sample_sizes={WITHIN: 1}, seed="fixture")
    with pytest.raises(ValueError, match="unknown stratum"):
        build_pair_design(groups, sample_sizes={WITHIN: 1, TAIL: 1, "mystery": 0}, seed="fixture")
    with pytest.raises(ValueError, match="nonnegative integers"):
        build_pair_design(groups, sample_sizes={WITHIN: True, TAIL: 1}, seed="fixture")
    with pytest.raises(ValueError, match="exactly one"):
        pair_stratum_sizes({"a": ["a", "b"], "b": ["b"]})
    with pytest.raises(ValueError, match="outside"):
        pair_stratum_sizes(groups, {"candidate": [["a", "outside"]]})
    with pytest.raises(ValueError, match="exactly two"):
        pair_stratum_sizes(groups, {"candidate": [7]})


def test_census_recovers_pair_metrics_and_keeps_group_and_candidate_estimands_separate() -> None:
    groups = {"one": ["a", "b", "c"], "two": ["d", "e"]}
    channels = {"retrieved": [["a", "d"], ["b", "e"]]}
    design = build_pair_design(groups, channels, sample_sizes=pair_stratum_sizes(groups, channels), seed="census")
    result = estimate_pair_metrics(design, labels(design, {("a", "b"), ("d", "e"), ("a", "d"), ("c", "e")}),
                                   reference_kind="human")
    assert result["pair_precision"]["point"] == .5
    assert result["pair_precision"]["confidence_interval"] == [.5, .5]
    assert result["pair_recall"]["point"] == .5
    assert result["pair_recall"]["confidence_interval"]["lower"] == .5
    assert result["pair_recall"]["confidence_interval"]["upper"] == .5
    assert result["candidate_pool_recall"]["point"] == pytest.approx(2 / 3)
    assert result["candidate_pool_recall"]["not_corpus_recall"]
    assert result["whole_group_purity"] is None
    assert result["reference_kind"] == "human" and not result["human_validated"]
    assert result["within"]["ht_total_variance_estimate"] == 0


def test_ht_weights_replace_naive_pooling_and_single_draw_has_no_variance_estimate() -> None:
    design = build_pair_design({"one": list("abcd"), "two": ["e"]},
                               sample_sizes={WITHIN: 2, TAIL: 1}, seed="weights")
    judgments = [{"pair_id": row["pair_id"], "label": "same_event" if index != 1 else "different_event"}
                 for index, row in enumerate(design["selected_pairs"])]
    result = estimate_pair_metrics(design, judgments, reference_kind="model")
    # Within: one of two same => HT 3 of 6. Tail: one same => HT 4 of 4.
    assert result["pair_precision"]["point"] == .5
    assert result["pair_recall"]["point"] == pytest.approx(3 / 7)
    assert result["within"]["ht_total_variance_estimate"] == pytest.approx(6)
    assert result["between"]["ht_total_variance_estimate"] is None
    assert result["pair_recall"]["linearized_design_variance_diagnostic"] is None
    assert result["between"]["kish_weight_effective_n"] == 1


def test_failed_missing_and_uncertain_references_stay_in_missingness_and_confidence_bounds() -> None:
    groups = {"one": list("abc"), "two": ["d"]}
    design = build_pair_design(groups, sample_sizes={WITHIN: 3, TAIL: 3}, seed="missing")
    judgments = [{"pair_id": row["pair_id"], "label": label}
                 for row, label in zip(design["selected_pairs"],
                                       ["same_event", "uncertain", "failed", "different_event", "unknown"])]
    result = estimate_pair_metrics(design, judgments, reference_kind="model")
    assert result["counts"] == {"same_event": 1, "different_event": 1, "uncertain": 1,
                                "failed": 1, "unknown": 1, "pending": 1}
    assert result["pair_precision"]["point"] is None
    assert result["pair_recall"]["point"] is None
    assert result["pair_precision"]["confidence_interval"] == pytest.approx([1 / 3, 1])
    assert result["pair_recall"]["confidence_interval"]["lower"] == pytest.approx(1 / 3)
    assert result["pair_recall"]["confidence_interval"]["upper"] == 1
    assert result["pair_recall"]["complete_case_ratio_diagnostic"] == 1


def test_rare_unobserved_tail_positives_do_not_produce_perfect_recall_confidence() -> None:
    groups = {"joined": ["a", "b"], **{f"single{i}": [f"s{i:04}"] for i in range(1000)}}
    design = build_pair_design(groups, sample_sizes={WITHIN: 1, TAIL: 8}, seed="rare-events")
    result = estimate_pair_metrics(design, [{"pair_id": row["pair_id"],
        "label": "same_event" if row["stratum"] == WITHIN else "different_event"}
        for row in design["selected_pairs"]], reference_kind="model")
    assert result["pair_recall"]["point"] == 1
    assert result["pair_recall"]["confidence_interval"]["lower"] < .001
    assert result["pair_recall"]["confidence_interval"]["upper"] == 1
    assert result["random_tail"]["positive_count_confidence_interval"][1] > 100000
    assert result["between"]["ht_total_variance_estimate"] == 0
    assert result["pair_recall"]["zero_observed_between_positives"]


def test_precision_survives_pending_between_references_without_claiming_recall() -> None:
    design = build_pair_design({"one": ["a", "b"], "two": ["c"]},
                               sample_sizes={WITHIN: 1, TAIL: 1}, seed="precision-only")
    within = next(row for row in design["selected_pairs"] if row["stratum"] == WITHIN)
    result = estimate_pair_metrics(design, [{"pair_id": within["pair_id"], "label": "same_event"}],
                                   reference_kind="model")
    assert result["pair_precision"]["point"] == 1
    assert result["pair_recall"]["point"] is None
    assert result["counts"]["pending"] == 1


def test_exact_hypergeometric_intervals_have_finite_population_coverage() -> None:
    # Exhaust every equally likely SRS sample for several small finite populations.
    for N in range(2, 9):
        for n in range(1, N + 1):
            intervals = {x: finite_population_positive_interval(N, n, x, tail_alpha=.025)
                         for x in range(n + 1)}
            for M in range(N + 1):
                outcomes = Counter(sum(i < M for i in sample) for sample in combinations(range(N), n))
                covered = sum(count for x, count in outcomes.items() if intervals[x][0] <= M <= intervals[x][1])
                assert covered / sum(outcomes.values()) >= .95
    assert finite_population_positive_interval(10, 10, 4, tail_alpha=.025) == [4, 4]
    assert finite_population_positive_interval(10, 0, 0, tail_alpha=.025) == [0, 10]


def test_tampered_design_duplicate_or_unselected_labels_are_rejected() -> None:
    design = build_pair_design({"one": ["a", "b"], "two": ["c", "d"]},
                               sample_sizes={WITHIN: 1, TAIL: 1}, seed="integrity")
    changed = deepcopy(design)
    changed["selected_pairs"][0]["pi"] = 1
    with pytest.raises(ValueError, match="Frozen design"):
        estimate_pair_metrics(changed, [], reference_kind="model")
    selected = design["selected_pairs"][0]
    with pytest.raises(ValueError, match="Duplicate unordered"):
        estimate_pair_metrics(design, [{"pair_id": selected["pair_id"], "label": "same_event"},
            {"left": selected["right"], "right": selected["left"], "label": "different_event"}],
            reference_kind="model")
    with pytest.raises(ValueError, match="outside"):
        estimate_pair_metrics(design, [{"left": "outside", "right": "a", "label": "same_event"}],
                              reference_kind="model")
    with pytest.raises(ValueError, match="human or model"):
        estimate_pair_metrics(design, [], reference_kind="gold")


def test_empty_or_no_same_event_frame_keeps_undefined_recall_explicit() -> None:
    design = build_pair_design({}, sample_sizes={}, seed="empty")
    empty = estimate_pair_metrics(design, [], reference_kind="model")
    assert empty["pair_precision"]["point"] is None and empty["pair_recall"]["point"] is None
    assert empty["pair_recall"]["confidence_interval"]["lower"] is None
    design = build_pair_design({"one": ["a", "b"]}, sample_sizes={WITHIN: 1}, seed="zero-positive")
    zero = estimate_pair_metrics(design, labels(design, set()), reference_kind="model")
    assert zero["pair_precision"]["point"] == 0
    assert zero["pair_recall"]["point"] is None
    assert zero["pair_recall"]["confidence_interval"]["zero_denominator_possible"]
