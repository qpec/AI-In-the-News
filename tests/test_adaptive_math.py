"""Synthetic software checks only; no empirical calibration evidence."""

from __future__ import annotations

import math

import pytest

from newsresearch.adaptive_math import (
    Draw,
    FrameItem,
    binomial_interval,
    evaluate_holdout,
    sample_round,
    select_cutoff,
    split_frame,
)


def make_frame(count: int) -> list[FrameItem]:
    return [FrameItem(f"source-{index:04d}", index / count, f"group-{index:04d}") for index in range(count)]


def test_split_reproducible_independent_of_input_order_and_excludes_entire_groups() -> None:
    frame = [FrameItem(f"s{i}", i / 12, f"g{i // 2}") for i in range(12)]
    split = split_frame(frame, 3, 351)
    assert split == split_frame(list(reversed(frame)), 3, 351)
    assert len(split["heldout_ids"]) == 3
    assert len(set(split["heldout_ids"])) == 3
    development_groups = {item.group_id for item in frame if item.source_id in split["development_ids"]}
    assert not development_groups.intersection(split["heldout_group_ids"])
    assert set(split["heldout_ids"]).isdisjoint(split["extra_development_exclusions"])
    assert sum(map(len, (split["heldout_ids"], split["development_ids"], split["extra_development_exclusions"]))) == 12


def test_split_refuses_empty_development_after_group_exclusion() -> None:
    with pytest.raises(ValueError, match="leave no development"):
        split_frame([FrameItem("a", 0.1, "same"), FrameItem("b", 0.2, "same")], 1, 0)


def test_uniform_round_preserves_repeats_and_rng_can_resume_without_restarting() -> None:
    frame = make_frame(4)
    first = sample_round(frame, 20, 42, 0)
    assert len(first["draws"]) == 20
    assert len({draw["source_id"] for draw in first["draws"]}) < 20
    assert all(draw["probability"] == 0.25 for draw in first["draws"])
    resumed = sample_round(frame, 20, 42, 1, rng_state=first["rng_state_after"], starting_draw_index=20)
    combined = sample_round(frame, 40, 42, 0)
    assert [d["source_id"] for d in first["draws"] + resumed["draws"]] == [
        d["source_id"] for d in combined["draws"]
    ]
    assert resumed["draws"][0]["draw_index"] == 20


def test_adaptive_draws_log_marginal_probability_not_component_probability() -> None:
    frame = make_frame(100)
    result = sample_round(frame, 1000, 1, 1, candidate=0.5, window_size=10)
    window = set(result["window_ids"])
    assert len(window) == 10
    assert any(draw["source_id"] not in window for draw in result["draws"])
    assert any(draw["source_id"] in window for draw in result["draws"])
    for draw in result["draws"]:
        expected = 0.5 / 100 + (0.5 / 10 if draw["source_id"] in window else 0)
        assert draw["probability"] == expected
    assert math.isclose(sum(0.005 + (0.05 if item.source_id in window else 0) for item in frame), 1)


def test_window_ties_use_source_id_and_empty_window_is_uniform() -> None:
    frame = [FrameItem("b", 0.75, "b"), FrameItem("a", 0.25, "a"), FrameItem("c", 1, "c")]
    result = sample_round(frame, 5, 1, 1, candidate=0.5, window_size=1)
    assert result["window_ids"] == ["a"]
    empty = sample_round(frame, 5, 1, 1, candidate=0.5, window_size=0)
    assert empty["window_size"] == 0
    assert all(draw["probability"] == 1 / 3 for draw in empty["draws"])


def test_hansen_hurwitz_uses_every_draw_and_exact_unequal_probabilities() -> None:
    frame = [FrameItem("p", 0.8, "p"), FrameItem("n", 0.2, "n"), FrameItem("u", 0.5, "u")]
    draws = [Draw("p", 0.5), Draw("p", 0.5), Draw("n", 0.25), Draw("u", 0.25)]
    result = select_cutoff(frame, draws, {"p": "yes", "n": "no", "u": "uncertain"}, min_positive=1, min_negative=1)
    point = next(point for point in result["curve"] if point["cutoff"] == 0.5)
    assert point["known_reference"]["tp"] == 1  # (1/.5 + 1/.5)/4
    assert point["known_reference"]["tn"] == 1  # (1/.25)/4
    assert point["unknown_above_weight"] == 1
    assert point["pessimistic"]["fp"] == 1
    assert point["optimistic"]["tp"] == 2
    assert result["draw_count"] == 4
    assert result["unique_drawn_count"] == 3


def test_unknown_draw_below_cutoff_counts_as_possible_false_negative_not_dropped() -> None:
    frame = [FrameItem("p", 0.8, "p"), FrameItem("n", 0.2, "n"), FrameItem("u", 0.1, "u")]
    draws = [Draw(item.source_id, 1 / 3) for item in frame]
    result = select_cutoff(frame, draws, {"p": "yes", "n": "no"}, min_positive=1, min_negative=1)
    point = next(point for point in result["curve"] if point["cutoff"] == 0.8)
    assert point["pessimistic"]["fn"] == 1
    assert point["pessimistic"]["recall"] == 0.5
    assert not point["eligible"]
    assert result["draw_reference_counts"]["missing"] == 1
    assert result["cutoff"] == 0.1


def test_lower_cutoff_tie_rule_only_compares_recall_eligible_candidates() -> None:
    frame = make_frame(11)
    labels = {item.source_id: "yes" if index >= 5 else "no" for index, item in enumerate(frame)}
    draws = [Draw(item.source_id, 1 / len(frame)) for item in frame]
    result = select_cutoff(frame, draws, labels, recall_target=1, f2_tolerance=1, min_positive=1, min_negative=1)
    assert result["cutoff"] == 0
    assert all(point["eligible"] is False for point in result["curve"] if point["cutoff"] > 5 / 11)
    strict = select_cutoff(frame, draws, labels, recall_target=1, f2_tolerance=0, min_positive=1, min_negative=1)
    assert strict["cutoff"] == 5 / 11


def test_repeated_single_positive_does_not_manufacture_class_minimum() -> None:
    frame = [FrameItem("p", 0.9, "p"), FrameItem("n", 0.1, "n")]
    draws = [Draw("p", 0.5)] * 20 + [Draw("n", 0.5)] * 20
    result = select_cutoff(frame, draws, {"p": "yes", "n": "no"}, min_positive=2, min_negative=2)
    assert result["status"] == "inconclusive"
    assert result["cutoff"] is None
    assert result["unique_reference_counts"]["yes"] == 1
    assert result["draw_reference_counts"]["yes"] == 20


def test_grid_includes_unsampled_frame_scores_and_rejects_bad_q() -> None:
    frame = make_frame(3)
    result = select_cutoff(frame, [Draw("source-0000", 1 / 3)], {"source-0000": "no"}, min_positive=1, min_negative=1)
    assert result["grid_count"] == 3
    with pytest.raises(ValueError, match="strictly positive"):
        select_cutoff(frame, [Draw("source-0000", 0)], {})


def test_exact_binomial_interval_matches_known_boundary_and_interior_values() -> None:
    assert binomial_interval(0, 0) is None
    zero = binomial_interval(0, 10)
    perfect = binomial_interval(10, 10)
    assert zero == pytest.approx([0, 1 - 0.025 ** 0.1])
    assert perfect == pytest.approx([0.025 ** 0.1, 1])
    assert binomial_interval(5, 10) == pytest.approx([0.18708602844739852, 0.8129139715526015])


def test_holdout_keeps_unknown_processing_separate_and_never_retunes_cutoff() -> None:
    frame = [
        FrameItem("p", 0.8, "p"), FrameItem("n", 0.2, "n"),
        FrameItem("u", 0.9, "u"), FrameItem("m", 0.1, "m"),
    ]
    result = evaluate_holdout(frame, {"p": "yes", "n": "no", "u": "uncertain"}, 0.5,
                              min_positive=1, min_negative=1)
    assert result["cutoff"] == 0.5
    assert result["cutoff_retuned"] is False
    assert result["reference_counts"] == {"yes": 1, "no": 1, "uncertain": 1, "missing": 1}
    assert result["processing_count"] == 3
    assert result["clear_reference_coverage"] == 0.5
    assert result["pessimistic"]["recall"] == 0.5
    assert result["pessimistic"]["precision"] == 0.5
    assert result["optimistic"]["recall"] == 1
    assert result["status"] == "inconclusive"


def test_perfect_small_holdout_is_inconclusive_for_wide_interval_or_required_lower_bound() -> None:
    frame = make_frame(10)
    labels = {item.source_id: "yes" if index >= 5 else "no" for index, item in enumerate(frame)}
    result = evaluate_holdout(frame, labels, 0.5)
    assert result["pessimistic"]["recall"] == 1
    assert result["status"] == "inconclusive"
    assert "recall_interval_missing_or_too_wide" in result["reasons"]
    larger = make_frame(80)
    larger_labels = {item.source_id: "yes" if index >= 40 else "no" for index, item in enumerate(larger)}
    result = evaluate_holdout(larger, larger_labels, 0.5, required_recall_lower_bound=0.95)
    assert result["point_recall_target_met"] is True
    assert result["status"] == "inconclusive"
    assert "recall_lower_bound_target_not_established" in result["reasons"]


def test_holdout_point_pass_and_failure_are_distinct_from_inferential_claims() -> None:
    frame = make_frame(80)
    labels = {item.source_id: "yes" if index >= 40 else "no" for index, item in enumerate(frame)}
    passed = evaluate_holdout(frame, labels, 0.5)
    assert passed["status"] == "passed_model_reference"
    assert passed["required_recall_lower_bound"] is None
    assert passed["human_validated"] is False
    failed = evaluate_holdout(frame, labels, 0.55)
    assert failed["status"] == "failed"
    assert failed["cutoff"] == 0.55


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_scores_fail_before_sampling(score: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        sample_round([FrameItem("a", score, "a")], 1, 0, 0)
