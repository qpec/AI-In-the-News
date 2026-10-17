"""Synthetic retrieval calculations only; no corpus, model, or research run."""
from __future__ import annotations

import numpy as np
import pytest

from newsresearch.common import ResearchError
from newsresearch.event_rag_retrieval import rank_saved_vectors, render


def test_exact_cosine_normalization_self_exclusion_and_retained_matrix():
    result = rank_saved_vectors(
        ["a", "b", "c", "d"],
        np.array([[10.0, 0.0], [3.0, 4.0], [0.0, 2.0], [-5.0, 0.0]]),
        ["a"],
        ["a", "b", "c", "d"],
        top_k=3,
    )
    assert result["rows"] == [{
        "source_version": "a",
        "status": "complete",
        "candidates": [
            {"source_version": "b", "score": pytest.approx(0.6), "rank": 1},
            {"source_version": "c", "score": pytest.approx(0.0), "rank": 2},
            {"source_version": "d", "score": pytest.approx(-1.0), "rank": 3},
        ],
    }]
    assert result["eligible_vector_sources"] == ["a", "b", "c", "d"]
    assert result["missing_vector_sources"] == []
    assert result["scored_pairs"] == 3
    assert result["candidate_slots"] == 3
    assert result["pending_slots"] == 0
    assert result["score_row_ids"] == ["a"]
    assert result["score_column_ids"] == ["a", "b", "c", "d"]
    assert result["scores"].dtype == np.float32
    np.testing.assert_allclose(result["scores"], [[1.0, 0.6, 0.0, -1.0]], atol=1e-6)


def test_eligible_frame_excludes_sealed_sources_even_when_they_rank_first():
    result = rank_saved_vectors(
        ["anchor", "sealed", "candidate"],
        np.array([[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
        ["anchor"],
        ["anchor", "candidate"],
        top_k=1,
    )
    assert result["rows"][0]["candidates"] == [
        {"source_version": "candidate", "score": 0.0, "rank": 1},
    ]
    assert result["score_column_ids"] == ["anchor", "candidate"]
    assert result["scored_pairs"] == 1


def test_tied_scores_use_source_id_order_independent_of_input_order():
    result = rank_saved_vectors(
        ["z", "anchor", "b", "a"],
        np.array([[1.0, 0.0]] * 4),
        ["anchor"],
        ["z", "b", "anchor", "a"],
        top_k=2,
    )
    assert [candidate["source_version"] for candidate in result["rows"][0]["candidates"]] == ["a", "b"]
    assert result["scored_pairs"] == 3
    assert result["eligible_vector_sources"] == ["a", "anchor", "b", "z"]


def test_missing_vectors_remain_unavailable_and_never_negative_candidates():
    result = rank_saved_vectors(
        ["b", "a"],
        np.array([[0.0, 1.0], [1.0, 0.0]]),
        ["a", "missing-anchor"],
        ["missing-eligible", "b", "missing-anchor", "a"],
        top_k=3,
    )
    assert result["rows"][0]["status"] == "short_candidates"
    assert result["rows"][0]["candidates"] == [
        {"source_version": "b", "score": 0.0, "rank": 1},
    ]
    assert result["rows"][1] == {
        "source_version": "missing-anchor", "status": "vector_unavailable", "candidates": [],
    }
    assert result["missing_vector_sources"] == ["missing-anchor", "missing-eligible"]
    assert result["eligible_vector_sources"] == ["a", "b"]
    assert result["scored_pairs"] == 1
    assert result["candidate_slots"] == 1
    assert result["pending_slots"] == 5


def test_all_scored_candidates_are_counted_when_only_top_one_is_returned():
    result = rank_saved_vectors(
        ["a", "b", "c"],
        np.array([[1.0, 0.0], [0.8, 0.6], [-1.0, 0.0]]),
        ["a", "b"],
        ["c", "a", "b"],
        top_k=1,
    )
    assert result["scored_pairs"] == 4
    assert result["candidate_slots"] == 2
    assert result["pending_slots"] == 0
    assert [row["source_version"] for row in result["rows"]] == ["a", "b"]
    assert result["rows"][0]["candidates"][0]["source_version"] == "b"
    assert result["rows"][1]["candidates"][0]["source_version"] == "a"


def test_only_anchor_available_does_not_manufacture_neighbors():
    result = rank_saved_vectors(["a"], np.array([[1.0, 0.0]]), ["a"], ["a"], top_k=3)
    assert result["rows"] == [{"source_version": "a", "status": "short_candidates", "candidates": []}]
    assert result["scored_pairs"] == result["candidate_slots"] == 0
    assert result["pending_slots"] == 3


def test_ranking_does_not_mutate_saved_vectors():
    vectors = np.array([[9.0, 12.0], [0.0, 5.0]], dtype=np.float32)
    before = vectors.copy()
    rank_saved_vectors(["a", "b"], vectors, ["a"], ["a", "b"], top_k=1)
    np.testing.assert_array_equal(vectors, before)


def test_anchor_outside_eligible_frame_is_rejected():
    with pytest.raises(ResearchError):
        rank_saved_vectors(["a", "b"], np.eye(2), ["a"], ["b"], top_k=1)


@pytest.mark.parametrize("field", ["ids", "anchors", "eligible"])
def test_duplicate_source_mappings_are_rejected(field):
    values = {
        "ids": ["a", "b"], "vectors": np.eye(2), "anchors": ["a"], "eligible": ["a", "b"],
    }
    values[field] = ["a", "a"]
    with pytest.raises(ResearchError):
        rank_saved_vectors(**values, top_k=1)


@pytest.mark.parametrize("vectors", [
    np.array([1.0, 2.0]),
    np.zeros((2, 2, 1)),
    np.eye(3),
    np.empty((2, 0)),
    np.array([[0.0, 0.0], [1.0, 0.0]]),
    np.array([[np.nan, 0.0], [1.0, 0.0]]),
    np.array([[np.inf, 0.0], [1.0, 0.0]]),
    np.array([[-np.inf, 0.0], [1.0, 0.0]]),
])
def test_invalid_saved_vectors_are_rejected(vectors):
    with pytest.raises(ResearchError):
        rank_saved_vectors(["a", "b"], vectors, ["a"], ["a", "b"], top_k=1)


@pytest.mark.parametrize("top_k", [0, -1, 21, 1.5, True])
def test_invalid_top_k_is_rejected(top_k):
    with pytest.raises(ResearchError):
        rank_saved_vectors(["a", "b"], np.eye(2), ["a"], ["a", "b"], top_k=top_k)


def presentation_fixture():
    return {
        "rows": [
            {"source_version": "a", "status": "short_candidates", "candidates": [
                {"source_version": "b", "score": 0.625, "rank": 1},
            ]},
            {"source_version": "missing", "status": "vector_unavailable", "candidates": []},
        ],
        "top_k": 3, "eligible_vector_sources": ["a", "b"], "scored_pairs": 1,
        "candidate_slots": 1, "distinct_candidates": 1, "original_frame_count": 5,
        "exclusion_counts": {"sealed_held_out_body": 2}, "missing_vector_sources": ["missing"],
        "pending_slots": 5, "ranking_seconds": 0.125,
        "text": {"available": 2, "requested": 3, "passages": 7, "missing": ["missing"]},
        "metadata": {
            "a": {"source_version": "a", "title": "Synthetic anchor", "url": "https://example.test/a"},
            "b": {"source_version": "b", "title": "Synthetic candidate", "url": "https://example.test/b"},
            "missing": {"source_version": "missing", "title": "Missing vector", "url": None},
        },
    }


def test_presentation_reports_ranked_links_coverage_and_score_limitations():
    text = render(presentation_fixture())
    for expected in (
        "2 article queries", "top 3 each", "2 development articles", "1 nonself cosine scores",
        "1 ranked candidates", "Missing vectors: 1", "pending candidate slots: 5",
        "Saved full text: 2/3", "7 passages; missing text: 1", "0.125 seconds",
        "excludes storage preflight, vector loading and durable audit",
        "Zero new embeddings, LLM calls or network calls", "No date filter or score cutoff",
        "cosine is similarity, not event identity probability", "No relevance yes/no tags or memberships",
        "Extraction and event grouping remain unprocessed",
        "1. [Synthetic candidate](<https://example.test/b>)", "cosine **0.6250**",
        "[Synthetic anchor](<https://example.test/a>)", "No candidates returned; status: vector_unavailable",
    ):
        assert expected in text


def test_presentation_does_not_create_links_from_unsafe_source_urls():
    value = presentation_fixture()
    value["metadata"]["a"].update(title="Title [brackets]\nsecond line", url="javascript:alert(1)")
    value["metadata"]["b"]["url"] = "https://example.test/b\nunsafe"
    text = render(value)
    assert "javascript:" not in text
    assert "https://example.test/b" not in text
    assert "Title \\[brackets\\] second line" in text
