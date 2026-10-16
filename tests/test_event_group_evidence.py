"""Focused synthetic preparation tests; no sources, models or acceptance."""
from copy import deepcopy
from itertools import combinations, product

import pytest

from newsresearch.common import digest
from newsresearch.event_group_evidence import prepare
from newsresearch.event_pair_selection import FEATURES

RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def group(name, members):
    return {"group_id": name, "members": list(members)}


def scores(pairs):
    return [{"pair_id": digest(sorted((a, b))), "left": a, "right": b, "status": "completed",
             "features": dict.fromkeys(FEATURES, .9)} for a, b in pairs]


def metadata(names, far=""):
    return {name: {"published_at": "2026-02-15" if name in far else "2026-01-01",
                   "url": f"https://{name}.example/article", "body_sha256": name,
                   "body": "MUST NOT ENTER A PACKET"} for name in names}


def test_singletons_and_internal_pairs_get_complete_packets_without_chain_merges():
    groups = [group("A", "a"), group("B", "bc"), group("C", "d")]
    rows = scores([("a", "b"), ("a", "c"), ("b", "c"), ("b", "d"), ("c", "d")])
    result = prepare(groups, rows, metadata("abcd", "bc"), RULE)
    assert result["diagnostics"]["frame_pairs"] == 2
    assert result["diagnostics"]["selected_candidates"] == 1
    selected = result["selected"][0]
    assert selected["article_members"] == list("abc") and len(selected["pair_task_ids"]) == 3
    assert digest(["b", "c"]) in selected["pair_task_ids"]
    assert all("body" not in item for item in selected["articles"])
    assert result["diagnostics"]["candidate_status_counts"]["old_group_already_selected"] == 1
    assert result["diagnostics"]["current_memberships_changed"] == 0
    single = prepare([group("A", "a"), group("B", "b")], scores([("a", "b")]), metadata("ab", "b"), RULE)
    assert single["selected"][0]["candidate_type"] == "both_singletons"
    assert len(single["tasks"]) == 1
    assert prepare(groups, [], metadata("abcd", "bc"), RULE)["diagnostics"]["frame_pairs"] == 0


def test_missing_failed_pending_invalid_and_below_cutoff_are_not_negative_findings():
    groups = [group("A", "ab"), group("B", "cd")]
    complete = scores(product("ab", "cd"))
    for reason in ("missing_row", "failed", "pending", "unknown", "invalid_or_missing_features", "below_cutoff"):
        rows = deepcopy(complete)
        if reason == "missing_row":
            rows.pop()
        elif reason == "invalid_or_missing_features":
            rows[-1]["features"].pop(FEATURES[0])
        elif reason == "below_cutoff":
            rows[-1]["features"][FEATURES[0]] = .49
        else:
            rows[-1]["status"] = reason
        result = prepare(groups, rows, metadata("abcd", "cd"), RULE)
        assert result["selected"] == [] and reason in result["candidates"][0]["reasons"]
        assert result["candidates"][0]["semantic_review_status"] == "unjudged"
    with pytest.raises(ValueError, match="duplicate"):
        prepare(groups, complete + complete[:1], metadata("abcd", "cd"), RULE)
    close = prepare(groups, complete, metadata("abcd"), RULE)
    assert close["diagnostics"]["same_window_excluded"] == 1 and not close["selected"]


def test_atomic_deterministic_budgets_size_and_diversity_exclusions():
    groups = [group("A", "ab"), group("B", "cd"), group("C", "e"), group("D", "f")]
    rows = scores(list(combinations("abcd", 2)) + [("e", "f")])
    meta = metadata("abcdef", "cdf")
    result = prepare(groups, rows, meta, RULE, max_tasks=5)
    assert [item["old_group_ids"] for item in result["selected"]] == [["C", "D"]]
    assert result["diagnostics"]["candidate_status_counts"]["atomic_task_budget_excluded"] == 1
    assert len(result["tasks"]) == 1
    assert prepare(groups[::-1], rows[::-1], meta, RULE, max_tasks=5) == result
    limited = prepare(groups, rows, meta, RULE, max_union=3)
    assert limited["diagnostics"]["candidate_status_counts"]["union_size_excluded"] == 1
    mono = {key: {**value, "url": "https://one.example", "body_sha256": "one"} for key, value in meta.items()}
    assert not prepare(groups, rows, mono, RULE)["selected"]
    heldout = prepare(groups, rows, meta, RULE, review_source_ids=set("abef"))
    assert heldout["diagnostics"]["candidate_status_counts"]["heldout_or_unmapped_excluded"] == 1
    assert [row["old_group_ids"] for row in heldout["selected"]] == [["C", "D"]]
    with pytest.raises(ValueError, match="36-task"):
        prepare(groups, rows, meta, RULE, max_tasks=37)
