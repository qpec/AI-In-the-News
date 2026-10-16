"""Focused synthetic partition-comparison checks; no real articles or labels."""
import math

import pytest

from newsresearch.common import digest
from newsresearch.event_pair_selection import FEATURES
from newsresearch.event_window_groups import build, lineage, stats

RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def row(a, b, score=.9, weakest=None):
    features = dict.fromkeys(FEATURES, score)
    if weakest is not None:
        features[FEATURES[1]] = weakest
    return {"left": a, "right": b, "pair_id": digest(sorted((a, b))),
            "features": features, "status": "completed"}


def metadata():
    return {item: {"published_at": f"2026-01-{day:02d}", "body_sha256": item}
            for item, day in zip("abcde", [1, 2, 21, 22, 23], strict=True)}


def test_widening_can_merge_and_rearrange_cliques_with_exact_lineage():
    edges = [row("a", "b", .99, .51), row("b", "c"), row("b", "d"), row("c", "d")]
    narrow = build(list("abcd"), edges, metadata(), RULE, 7)
    wide = build(list("abcd"), edges, metadata(), RULE, 30)
    assert sorted(group["members"] for group in narrow["groups"]) == [["a", "b"], ["c", "d"]]
    assert sorted(group["members"] for group in wide["groups"]) == [["a"], ["b", "c", "d"]]
    change = lineage(narrow["groups"], wide["groups"])
    assert change["split_old_groups"] == change["merged_new_groups"] == 1
    assert change["gained_copairs"] == 2 and change["lost_copairs"] == 1
    assert change["membership_changed_articles"] == 4
    assert build(list("dcba"), edges[::-1], metadata(), RULE, None)["groups"] == wide["groups"]
    assert wide["statistics"]["publication_spans"]["maximum_days"] == 20


def test_missing_dates_and_unprocessed_features_remain_explicitly_excluded():
    meta = metadata()
    meta["c"]["published_at"] = None
    with pytest.raises(ValueError, match="usable UTC-calendar"):
        build(list("abc"), [], meta, RULE, None)
    edges = [{**row("a", "b"), "status": "unknown"},
             {**row("a", "b"), "features": {**row("a", "b")["features"], FEATURES[0]: math.nan}},
             row("a", "b", .49)]
    result = build(list("ab"), edges, meta, RULE, None)
    assert result["counts"]["singletons"] == 2 and result["passing_pair_ids"] == []
    assert result["diagnostics"]["excluded_rows"] == {
        "failed_or_missing_feature_condition": 2, "incomplete_processing": 1}
    assert result["statistics"]["multi_article_size"]["mean"] is None
    assert stats([], {})["publication_spans"]["maximum_days"] is None


def test_sizes_spans_quantiles_and_lineage_do_not_depend_on_group_ids():
    groups = [{"group_id": "pair", "members": ["a", "b"]},
              {"group_id": "triple", "members": ["c", "d", "e"]}]
    result = stats(groups, metadata())
    assert result["size_histogram"] == {"2": 1, "3-5": 1, "6-10": 0, "11-20": 0, "21+": 0}
    assert result["multi_article_size"] == {"mean": 2.5, "median": 2.5, "p90": 3, "maximum": 3}
    assert result["all_internal_pair_count"] == 4 and result["grouped_articles"] == 5
    assert result["publication_spans"]["median_days"] == 1.5
    renamed = [{**group, "group_id": group["group_id"] + "-renamed"} for group in reversed(groups)]
    result = lineage(groups, renamed)
    assert result["unchanged_groups"] == 2
    assert result["gained_copairs"] == result["lost_copairs"] == result["membership_changed_articles"] == 0
