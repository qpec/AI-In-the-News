"""Synthetic software fixtures only; no event-identity validation."""
from itertools import combinations

import numpy as np
import pytest

from newsresearch.common import ResearchError, digest
from newsresearch.event_rule_application import candidate_batches, complete_link_groups, publication_coverage


def test_candidate_batches_equal_all_pairs_and_are_bounded():
    rng = np.random.default_rng(21)
    matrix = rng.normal(size=(35, 6))
    matrix /= np.linalg.norm(matrix, axis=1)[:, None]
    ids = [str(index) for index in range(len(matrix))]
    published = {source: f"2026-10-{int(source) % 20 + 1:02d}" for source in ids}
    rule = {"thresholds": [-.2], "publication_gap_days": 7}
    batches = list(candidate_batches(matrix, ids, published, rule, 5))
    actual = {(row["left"], row["right"]): row["distance"] for rows, _ in batches for row in rows}
    expected = {}
    checked = 0
    norms = np.sqrt(np.einsum("ij,ij->i", matrix, matrix, dtype=np.float64))
    for a, b in combinations(range(len(ids)), 2):
        if abs(a % 20 - b % 20) <= 7:
            checked += 1
            distance = float(np.clip(1 - np.dot(matrix[a], matrix[b])
                                    / (norms[a] * norms[b]), 0, 2))
            if 1 - distance >= -.2:
                expected[tuple(sorted((ids[a], ids[b])))] = distance
    assert actual == expected
    assert sum(stats["checked_date_pairs"] for _, stats in batches) == checked
    assert sum(stats["query_rows"] for _, stats in batches) == len(ids)
    assert all(len(rows) <= 200 for rows, _ in batches)
    assert sum(stats["emitted_pairs"] for _, stats in batches) == len(actual)


def test_missing_dates_duplicate_vectors_and_exact_cutoff():
    matrix = np.array([[1., 0.], [.8, .6], [1., 0.], [1., 0.]])
    ids = ["a", "b", "copy", "missing"]
    published = {"a": "2026-10-01", "b": "2026-10-08", "copy": "2026-10-16"}
    rule = {"thresholds": [.8], "publication_gap_days": 7}
    rows = [row for rows, _ in candidate_batches(matrix, ids, published, rule, 1) for row in rows]
    assert [(row["left"], row["right"]) for row in rows] == [("a", "b")]
    assert rows[0]["distance"] == pytest.approx(.2)
    assert publication_coverage(ids, published)["missing_date_ids"] == ["missing"]


def test_complete_link_rejects_transitive_bridge_and_keeps_singletons():
    def edge(a, b, score):
        return {"left": a, "right": b, "pair_id": digest(sorted((a, b))),
                "features": {"pooled_cosine": score}, "status": "completed"}
    edges = [edge("b", "c", .9), edge("a", "b", .95)]
    result = complete_link_groups(["a", "b", "c", "d"], edges)
    assert [group["members"] for group in result["groups"]] == [["a", "b"], ["c"], ["d"]]
    assert result["bridges"] == [edges[0]]
    assert result["counts"] == {"groups": 3, "multi_article_groups": 1, "singletons": 2,
                                "passing_edges": 2, "bridge_edges": 1}
    assert complete_link_groups(["d", "c", "b", "a"], list(reversed(edges))) == result


def test_invalid_vectors_and_duplicate_or_unscored_edges_fail_closed():
    with pytest.raises(ResearchError):
        list(candidate_batches([[2., 0.]], ["a"], {"a": "2026-10-01"},
                               {"thresholds": [.8], "publication_gap_days": 7}))
    missing = {"left": "a", "right": "b", "pair_id": "x"}
    with pytest.raises(ResearchError):
        complete_link_groups(["a", "b"], [missing])
    scored = {**missing, "pooled_cosine": .9}
    with pytest.raises(ResearchError):
        complete_link_groups(["a", "b"], [scored, scored])
