"""Two source-free checks for coverage choice and split-only consistency."""
from copy import deepcopy

from newsresearch.common import digest
from newsresearch.event_coverage_candidate import DELTAS, coverage_grid
from newsresearch.event_pair_selection import FEATURES


RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def edge(left: str, right: str, value: float) -> dict:
    return {"left": left, "right": right, "pair_id": digest(sorted((left, right))), "status": "completed",
            "publication_gap_days": 7, "features": dict.fromkeys(FEATURES, value)}


def test_largest_delta_requires_both_coverage_floors() -> None:
    groups = {"triple": ["a", "b", "c"], "pair": ["d", "e"]}
    rows = [edge("a", "b", .61), edge("a", "c", .61), edge("b", "c", .61), edge("d", "e", .53)]
    result = coverage_grid(groups, rows, RULE)
    assert [row["delta"] for row in result["variants"]] == list(DELTAS)
    assert result["selected"]["delta"] == .05
    # At .075 the pair floor passes, but grouped-article retention rejects it.
    rejected = next(row for row in result["variants"] if row["delta"] == .075)
    assert rejected["retained_pairs_fraction"] == .75
    assert rejected["grouped_article_retention_fraction"] == .6 and not rejected["eligible"]


def test_every_variant_splits_only_and_ignores_cross_group_bridges() -> None:
    groups = {"first": ["a", "b"], "second": ["c", "d"]}
    rows = [edge("a", "b", .6), edge("c", "d", .6), edge("b", "c", .99)]
    original = deepcopy((groups, rows, RULE))
    result = coverage_grid(groups, rows, RULE)
    assert (groups, rows, RULE) == original
    for variant in result["variants"]:
        assert sorted(source for group in variant["groups"] for source in group["members"]) == ["a", "b", "c", "d"]
        assert all(set(group["members"]) <= set(groups[group["parent_group"]]) for group in variant["groups"])
        assert variant["rule"]["publication_gap_days"] == 7
