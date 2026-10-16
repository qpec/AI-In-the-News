"""Focused synthetic geometry and frozen-gate proposal checks."""
from itertools import combinations
import math

import numpy as np
import pytest

from newsresearch.common import digest
from newsresearch.event_group_centroids import build_centroids, gate_candidates, map_candidates, select
from newsresearch.event_pair_selection import FEATURES

RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def metadata(ids):
    return {item: {"body_sha256": item, "published_at": "2026-01-01" if item < "c" else "2026-02-01"} for item in ids}


def test_body_dedup_radius_all_aliases_and_unprocessed_members():
    ids = ["a", "alias", "b", "z1", "z2", "invalid"]
    vectors = np.array([[1., 0.], [-1., 0.], [0., 1.], [1., 0.], [-1., 0.], [2., 0.]])
    meta = metadata(ids + ["missing"])
    meta["alias"]["body_sha256"] = "a"
    groups = [{"group_id": "G", "members": ["a", "alias", "b"]},
              {"group_id": "Z", "members": ["z1", "z2"]},
              {"group_id": "M", "members": ["missing"]}, {"group_id": "I", "members": ["invalid"]}]
    rep = build_centroids(groups, ids, vectors, meta)
    assert rep["group_ids"] == ["G"]
    assert rep["centroids"][0] == pytest.approx([2 ** -.5, 2 ** -.5])
    row = next(row for row in rep["rows"] if row["group_id"] == "G")
    assert row["distinct_body_representatives"] == ["a", "b"]
    assert row["angular_radius_radians"] == pytest.approx(3 * math.pi / 4)
    assert row["min_member_cosine"] == pytest.approx(-2 ** -.5)
    assert sum(row["status"] == "unprocessed" for row in rep["rows"]) == 3


def test_multi_queries_map_to_all_centroids_deterministically_and_restore_threads():
    import faiss
    ids = list("abcdef")
    angles = [0., 0., .01, .01, .04, .05]
    values = np.array([[math.cos(angle), math.sin(angle)] for angle in angles], dtype=np.float32)
    groups = [{"group_id": "A", "members": list("ab")}, {"group_id": "B", "members": list("cd")},
              {"group_id": "C", "members": ["e"]}, {"group_id": "D", "members": ["f"]}]
    rep = build_centroids(groups, ids, values, metadata(ids))
    before = faiss.omp_get_max_threads()
    frame = map_candidates(rep, top_k=1)
    assert faiss.omp_get_max_threads() == before
    assert frame["diagnostics"]["multi_group_queries"] == 2
    assert [row["old_group_ids"] for row in frame["candidates"]] == [["A", "B"]]
    assert frame["candidates"][0]["pooled_angular_lower_bound"] == pytest.approx(math.cos(.01), abs=1e-6)
    reversed_rep = build_centroids(groups[::-1], ids[::-1], values[::-1], metadata(ids))
    assert map_candidates(reversed_rep, top_k=1)["candidates"] == frame["candidates"]


def test_saved_all_five_gates_thresholds_missingness_and_disjoint_proposals():
    ids = list("abcd")
    rows = [{"left": a, "right": b, "pair_id": digest([a, b]), "status": "completed",
             "features": dict.fromkeys(FEATURES, .9)} for a, b in combinations(ids, 2)]
    frame = {"candidates": [{"candidate_id": first + second, "old_group_ids": [first, second],
              "left_members": list(left), "right_members": list(right), "article_members": sorted(left + right),
              "centroid_cosine": cosine, "pooled_angular_lower_bound": .4,
              "publication_span_days": 30, "status": "cross_window_nominated"}
             for first, second, left, right, cosine in (("A", "B", "ab", "c", .99),
                                                       ("A", "C", "ab", "d", .98),
                                                       ("B", "C", "c", "d", .96))]}
    result = select(RULE, rows, frame)
    gated = gate_candidates(RULE, rows, frame)
    assert select(RULE, [], frame, gated=gated)["proposals"] == result["proposals"]
    assert len(result["proposals"]) == 1 and result["proposals"][0]["old_group_ids"] == ["A", "B"]
    assert not result["proposals"][0]["pooled_certificate_passes"]
    assert result["diagnostics"]["candidate_status_counts"]["old_group_already_proposed"] == 1
    assert result["diagnostics"]["candidate_status_counts"]["below_centroid_cutoff_review"] == 1
    broken = [row for row in rows if (row["left"], row["right"]) != ("a", "c")]
    checked = select(RULE, broken, frame, .9)
    assert checked["candidates"][0]["cross_pair_counts"]["missing_row"] == 1
    assert checked["candidates"][0]["status"] == "cross_evidence_requires_review"
    assert checked["diagnostics"]["actual_group_merges"] == 0
