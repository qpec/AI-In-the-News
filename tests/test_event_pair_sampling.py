"""Synthetic software checks only; labels below are constructed, never source judgements."""
import hashlib

import numpy as np
import pytest

from newsresearch.common import ResearchError
from newsresearch.event_pair_sampling import (
    GRID, _unrank_pair, build_frame, evaluate_grid, evaluate_validation,
    sample_development, sample_validation,
)


def fixture_frame(count=100):
    values = np.random.default_rng(5).normal(size=(count, 8))
    values /= np.linalg.norm(values, axis=1)[:, None]
    ids = [f"article-{index:03}" for index in range(count)]
    hashes = {item: hashlib.sha256(item.encode()).hexdigest() for item in ids}
    hashes[ids[1]] = hashes[ids[0]]
    return values, ids, hashes


def constructed_rows(fold="development", same_distance=.02, different_distance=.25):
    rows, labels = [], {}
    for index in range(20):
        pair_id = str(index)
        same = index < 10
        rows.append({"pair_id": pair_id, "left": f"a{index}", "right": f"b{index}",
                     "fold": fold, "distance": same_distance if same else different_distance,
                     "inclusion_probability": .5})
        labels[pair_id] = {"status": "completed", "label": "same_event" if same else "different_event"}
    return rows, labels


def test_pair_unranking_complete():
    for size in range(2, 30):
        expected = [(left, right) for left in range(size) for right in range(left + 1, size)]
        assert [_unrank_pair(rank, size) for rank in range(len(expected))] == expected


def test_reproducible_disjoint_folds_and_duplicate_aliases():
    values, ids, hashes = fixture_frame()
    first = build_frame(values, ids, hashes, seed="software-test")
    second = build_frame(values, ids, hashes, seed="software-test")
    assert first == second
    reordered = build_frame(values[::-1], ids[::-1], hashes, seed="software-test")
    assert first["rows"] == reordered["rows"]
    assert first["excluded_duplicate_copies"] == 1
    alias = next(row for row in first["aliases"] if row["representative"] == ids[0])
    assert alias["aliases"] == [ids[1]]
    folds = {row["article_id"]: row["fold"] for row in first["representatives"]}
    for row in first["rows"]:
        assert row["left"] < row["right"]
        assert folds[row["left"]] == folds[row["right"]] == row["fold"]
        assert ids[1] not in (row["left"], row["right"])
        assert 0 <= row["distance"] <= 2
    assert len({row["pair_id"] for row in first["rows"]}) == len(first["rows"])
    for counts in first["fold_counts"].values():
        assert counts["background_pairs"] == min(512, counts["all_possible_pairs"])


def test_strata_reallocate_before_labels_with_full_frame_support():
    frame = build_frame(*fixture_frame(), seed="software-test")
    sample = sample_development(frame, seed="sample-test")
    assert sample == sample_development(frame, seed="sample-test")
    assert sample["selected_pairs"] == 54
    for stratum in sample["strata"]:
        assert stratum["n"] > 0 if stratum["N"] else stratum["n"] == 0
        if stratum["N"]:
            assert stratum["inclusion_probability"] == stratum["n"] / stratum["N"]
    assert all(row["weight"] == 1 / row["inclusion_probability"] for row in sample["rows"])


def test_validation_no_deficit_replacement():
    rows, _ = constructed_rows("validation")
    frame = {"rows": rows, "frame_hash": "synthetic"}
    sample = sample_validation(frame, .05, seed="test")
    assert len(sample["rows"]) == 16
    assert [row["n"] for row in sample["strata"]] == [10, 6]
    assert not sample["deficit_replacement"]


def test_grid_selects_strictest_equal_best_and_validates_fixed_cutoff():
    rows, labels = constructed_rows()
    result = evaluate_grid(rows, labels)
    assert result["candidate_cutoff"] == .02
    assert len(result["grid"]) >= len(GRID)
    assert result["selection_rule"] == "fixed grid plus observed development distance boundaries"
    validation_rows, validation_labels = constructed_rows("validation")
    validation = evaluate_validation(validation_rows, validation_labels, .025)
    assert validation["status"] == "passed_model_reference"
    assert validation["human_validated"] is False


def test_no_separable_cutoff_and_false_split_or_merge():
    rows, labels = constructed_rows(same_distance=.25, different_distance=.02)
    result = evaluate_grid(rows, labels)
    assert result["candidate_cutoff"] is None
    assert any(row["weighted"]["FP"] and row["weighted"]["FN"] for row in result["grid"])


@pytest.mark.parametrize("status", ["failed", "pending", "absent", "invalid"])
def test_unprocessed_labels_never_become_negative(status):
    rows, labels = constructed_rows()
    if status == "absent":
        del labels["0"]
    else:
        labels["0"] = {"status": status, "label": "different_event"}
    result = evaluate_grid(rows, labels)
    assert result["candidate_cutoff"] is None
    for metric in result["grid"]:
        assert metric["weighted"]["FP"] + metric["weighted"]["TN"] == 20
        assert "incomplete_processing" in metric["failures"]


def test_uncertainty_is_separate_and_pessimistic_metrics_bounded():
    rows, labels = constructed_rows()
    labels["0"]["label"] = "uncertain"
    result = evaluate_grid(rows, labels)
    for metric in result["grid"]:
        assert metric["counts"]["uncertain"] == 1
        assert metric["observed_uncertain_fraction"] == .05
        assert metric["weighted_uncertain_fraction"] == .05
        for name in ("pessimistic_precision", "pessimistic_recall"):
            assert metric[name] is None or 0 <= metric[name] <= 1


def test_sparse_and_cross_fold_validation_rejected():
    rows, labels = constructed_rows("validation")
    result = evaluate_validation(rows[:12], {key: labels[key] for key in map(str, range(12))}, .025)
    assert "sparse_validation_strata" in result["failures"]
    with pytest.raises(ResearchError):
        evaluate_grid(rows, labels)
    with pytest.raises(ResearchError):
        evaluate_validation(constructed_rows()[0], labels, .025)


def test_weighted_uncertainty_cannot_hide_behind_small_observed_fraction():
    rows, labels = constructed_rows()
    labels["0"]["label"] = "uncertain"
    rows[0]["inclusion_probability"] = .001
    result = evaluate_grid(rows, labels)
    assert result["candidate_cutoff"] is None
    assert all("excessive_or_unidentified_uncertainty" in row["failures"] for row in result["grid"])


def test_small_frame_exhaustion_keeps_positive_sampling_probabilities():
    frame = build_frame(*fixture_frame(5), seed="small-test")
    result = sample_development(frame, seed="small-sample")
    assert all(row["inclusion_probability"] == 1 for row in result["rows"])
    assert result["selected_pairs"] < 54


@pytest.mark.parametrize("bad", [np.zeros((3, 2)), np.full((3, 2), np.nan), np.ones((3, 2))])
def test_invalid_vectors_rejected(bad):
    with pytest.raises(ResearchError):
        build_frame(bad, ["a", "b", "c"], {item: "0" * 64 for item in "abc"}, seed="test")
