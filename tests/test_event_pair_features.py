"""Constructed vector checks only; no news judgements or event accuracy."""
import numpy as np
import pytest

from newsresearch.common import ResearchError
from newsresearch.event_pair_features import FEATURES, pair_features


def pair():
    return {"pair_id": "synthetic", "left": "a", "right": "b"}


def test_identical_passage_sets_have_matching_mutual_features_and_original_row_refs():
    values = np.array([[1., 0.], [0., 1.], [0., 1.], [1., 0.]])
    result = pair_features(values, {"a": [1, 0], "b": [3, 2]}, [pair()], {})[0]
    assert result["status"] == "completed"
    for name in FEATURES:
        assert result["features"][name] == pytest.approx(0 if name == "first_passage_cosine" else 1)
    assert result["diagnostics"]["best_pair_rows"] == [0, 3]
    assert result["diagnostics"]["first_pair_rows"] == [0, 2]
    assert result["diagnostics"]["top_mutual_pairs_used"] == 2


def test_passage_features_can_differ_from_whole_article_pooling():
    values = np.array([[1., 0.], [-1., 0.], [0., 1.], [0., 1.], [0., -1.], [1., 0.]])
    row = pair_features(values, {"a": [0, 1, 2], "b": [3, 4, 5]}, [pair()], {})[0]
    assert row["features"]["pooled_cosine"] == pytest.approx(0)
    assert row["features"]["max_passage_cosine"] == pytest.approx(1)
    assert row["features"]["top3_mutual_best_mean_cosine"] == pytest.approx(1)
    assert row["features"]["symmetric_mean_best_cosine"] == pytest.approx(2 / 3)
    assert row["features"]["first_passage_cosine"] == pytest.approx(0)


def test_negative_cosines_and_ties_are_preserved():
    row = pair_features(np.array([[1., 0.], [-1., 0.]]), {"a": [0], "b": [1]}, [pair()], {})[0]
    assert all(value == pytest.approx(-1) for value in row["features"].values())
    tied = pair_features(np.array([[1., 0.]] * 4), {"a": [1, 0], "b": [3, 2]}, [pair()], {})[0]
    assert tied["diagnostics"]["best_pair_rows"] == [0, 2]
    assert tied["diagnostics"]["top_mutual_rows"] == [[0, 2]]


def test_zero_pooled_sum_is_unavailable_but_passage_features_still_available():
    row = pair_features(np.array([[1., 0.], [-1., 0.], [1., 0.]]),
                        {"a": [0, 1], "b": [2]}, [pair()], {})[0]
    assert row["status"] == "completed"
    assert row["features"]["pooled_cosine"] is None
    assert row["features"]["max_passage_cosine"] == 1


def test_missing_vectors_are_explicit_and_never_negative():
    row = pair_features(np.array([[1., 0.]]), {"a": [0]}, [pair()], {})[0]
    assert row["status"] == "missing_vectors" and row["missing_articles"] == ["b"]
    assert all(value is None for value in row["features"].values())


def test_publication_gap_is_descriptive_utc_calendar_dates_without_gates():
    matrix = np.array([[1., 0.], [1., 0.]])
    rows = {"a": [0], "b": [1]}
    result = pair_features(matrix, rows, [pair()], {"a": "2026-10-01T23:00:00-02:00", "b": "2026-10-03"})[0]
    assert result["publication_gap_days"] == 1
    assert not any("gate" in key for key in result)
    missing = pair_features(matrix, rows, [pair()], {"a": "2026-10-01T12:00:00", "b": "invalid"})[0]
    assert missing["publication_gap_days"] is None
    assert missing["publication_status"] == {"left": "timezone_unavailable", "right": "invalid"}


@pytest.mark.parametrize("rows", [[0, 0], [-1], [2], [True], list(range(2049))])
def test_invalid_or_oversize_rows_are_not_truncated(rows):
    with pytest.raises(ResearchError):
        pair_features(np.array([[1., 0.], [1., 0.]]), {"a": rows, "b": [1]}, [pair()], {})


@pytest.mark.parametrize("values", [np.array([[2., 0.], [1., 0.]]), np.array([[np.nan, 0.], [1., 0.]])])
def test_invalid_selected_vectors_fail(values):
    with pytest.raises(ResearchError):
        pair_features(values, {"a": [0], "b": [1]}, [pair()], {})


def test_judge_fields_and_oversize_batches_are_rejected():
    values = np.array([[1., 0.], [1., 0.]])
    with pytest.raises(ResearchError, match="never judge"):
        pair_features(values, {"a": [0], "b": [1]}, [{**pair(), "label": "same_event"}], {})
    with pytest.raises(ResearchError, match="200"):
        pair_features(values, {"a": [0], "b": [1]}, [pair()] * 201, {})
