"""Source-free numeric software fixtures; no semantic event validation."""
from itertools import combinations

import numpy as np
import pytest

from newsresearch.common import ResearchError, digest
from newsresearch.event_temporal import candidate_batches, pair_band


def test_all_pair_scan_matches_original_float32_scalar_formula():
    rng = np.random.default_rng(483)
    raw = rng.normal(size=(35, 9)).astype(np.float32)
    raw /= np.linalg.norm(raw, axis=1)[:, None]
    ids = [f"source-{index}" for index in range(len(raw))]
    norms = np.sqrt(np.einsum("ij,ij->i", raw, raw, dtype=np.float64))
    expected = {}
    for a, b in combinations(range(len(raw)), 2):
        distance = float(np.clip(1. - np.dot(raw[a].astype(np.float64), raw[b].astype(np.float64))
                                / (norms[a] * norms[b]), 0., 2.))
        if 1. - distance >= .2:
            expected[digest(sorted((ids[a], ids[b])))] = distance
    batches = list(candidate_batches(raw, ids, .2, 5))
    actual = {row["pair_id"]: row["distance"] for rows, _ in batches for row in rows}
    assert actual == expected
    assert sum(stats["checked_vector_pairs"] for _, stats in batches) == len(raw) * (len(raw) - 1) // 2
    assert sum(stats["query_rows"] for _, stats in batches) == len(raw)
    assert sum(stats["emitted_pairs"] for _, stats in batches) == len(actual)


def test_date_free_scan_keeps_every_identity_and_bounds_batches():
    raw = np.tile(np.array([[1., 0.]], dtype=np.float32), (24, 1))
    ids = ["unknown-date", "report-from-long-ago", *[f"copy-{index}" for index in range(22)]]
    batches = list(candidate_batches(raw, ids, 1., 24))
    rows = [row for batch, _ in batches for row in batch]
    assert len(rows) == 276
    assert all(len(batch) <= 200 for batch, _ in batches)
    assert {source for row in rows for source in (row["left"], row["right"])} == set(ids)
    assert all(row["distance"] == 0. and row["origin"] == ["all_vector_pairs_no_date_gate"] for row in rows)
    assert sum(stats["checked_vector_pairs"] for _, stats in batches) == 276
    assert sum(stats["query_rows"] for _, stats in batches) == 24


def test_prefilter_margin_does_not_relax_exact_threshold_and_empty_blocks_count():
    raw = np.array([[1., 0.], [.8, .6], [-1., 0.]], dtype=np.float32)
    norms = np.sqrt(np.einsum("ij,ij->i", raw, raw, dtype=np.float64))
    exact = 1. - float(np.clip(1. - np.dot(raw[0].astype(np.float64), raw[1].astype(np.float64))
                             / (norms[0] * norms[1]), 0., 2.))
    at_cutoff = list(candidate_batches(raw, ["a", "b", "c"], exact, 1))
    assert [(row["left"], row["right"]) for batch, _ in at_cutoff for row in batch] == [("a", "b")]
    above = list(candidate_batches(raw, ["a", "b", "c"], exact + 1e-12, 1))
    assert sum(len(batch) for batch, _ in above) == 0
    assert sum(stats["checked_vector_pairs"] for _, stats in above) == 3
    assert sum(stats["query_rows"] for _, stats in above) == 3


def test_band_boundaries_and_invalid_inputs_fail_closed():
    assert [pair_band(gap) for gap in (0, 7, 8, 14, 15, 30, 31, 90, 91, None)] == [
        "0-7", "0-7", "8-14", "8-14", "15-30", "15-30", "31-90", "31-90", ">90", "unknown"]
    for gap in (-1, True, 7.1, "7"):
        with pytest.raises(ResearchError):
            pair_band(gap)
    for raw, ids, cutoff in (([[2., 0.]], ["a"], .8), ([[float("nan"), 0.]], ["a"], .8),
                             ([[1., 0.], [1., 0.]], ["a", "a"], .8), ([[1., 0.]], ["a"], True)):
        with pytest.raises(ResearchError):
            list(candidate_batches(raw, ids, cutoff))


def test_temporal_summary_retains_unknown_failed_provider_and_group_spans():
    from datetime import date
    import json

    from newsresearch.event_pair_selection import FEATURES
    from newsresearch.event_temporal_summary import summarize

    ids = ["a", "b", "c", "d", "missing", "unscored"]
    metadata = {source: {"title": source, "url": f"https://example.org/{source}"} for source in ids}
    dates = {"a": date(2026, 1, 1), "b": date(2026, 1, 8), "c": date(2026, 1, 22),
             "d": date(2026, 5, 1), "unscored": date(2026, 6, 1)}
    groups = [{"group_id": "ab", "members": ["a", "b"]},
              *[{"group_id": source, "members": [source]} for source in ids[2:]]]
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}
    def row(left, right, score=.9):
        return {"pair_id": digest(sorted((left, right))), "left": left, "right": right,
                "status": "completed", "features": dict.fromkeys(FEATURES, score)}
    scored = [row("a", "b"), row("a", "c"), row("a", "d"), row("a", "missing"),
              {**row("a", "unscored"), "features": {}}, row("b", "c", .4)]
    result = summarize(scored, rule, dates, metadata, groups,
                       {"a": "provider", "c": "provider", "d": "other"})
    assert [cap["dated_passing_pairs"] for cap in result["caps"]] == [1, 1, 2, 2, 3]
    assert result["unknown_gap_cosine_passing_pairs"] == 1
    assert sum(band["failed"] for band in result["bands"]) == 1
    assert result["caps"][-1]["long_passing_cross_group"]["singleton_group"] == 2
    assert result["current_group_spans"]["max_days"] == 7
    assert result["provider_group_spans"]["groups_beyond_7_days"] == 1
    assert [item["provider_equality"] for item in result["examples"]] == ["same", "different"]
    assert len(result["long_passing_pairs"]) == 2
    assert result["semantic_validation"] is False and result["new_partitions"] is False
    json.dumps(result, allow_nan=False)
