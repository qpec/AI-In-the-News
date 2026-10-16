"""Three focused synthetic checks for strong cross-window group proposals."""
from copy import deepcopy
from itertools import product

from newsresearch.common import digest
from newsresearch.event_group_links import propose
from newsresearch.event_pair_selection import FEATURES

RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}
GROUPS = [{"group_id": "A", "members": ["a", "b"]}, {"group_id": "B", "members": ["c", "d"]},
          {"group_id": "C", "members": ["e", "f"]}]
META = {item: {"published_at": f"2026-01-{day:02d}", "body_sha256": item,
               "url": f"https://{'www.one' if index % 2 else 'two'}.example/article"}
        for index, (item, day) in enumerate(zip("abcdef", [1, 2, 15, 16, 29, 30], strict=True))}
PROVIDER = dict.fromkeys("abcdef", "event-1")


def scores(first, second, value=.9):
    return [{"left": a, "right": b, "pair_id": digest(sorted((a, b))),
             "features": dict.fromkeys(FEATURES, value), "status": "completed"}
            for a, b in product(first, second)]


def test_fully_anchored_diverse_long_pair_proposes_without_mutating_groups():
    original = deepcopy(GROUPS[:2])
    result = propose(original, scores("ab", "cd"), META, PROVIDER, RULE)
    assert original == GROUPS[:2]
    assert result["diagnostics"]["qualified_pairs"] == 1
    assert result["candidate_rows"][0]["distinct_domains"] == ["one.example", "two.example"]
    assert result["candidate_rows"][0]["completed_cross_pair_count"] == 4
    proposal = result["proposals"][0]
    assert proposal["old_group_ids"] == ["A", "B"] and proposal["article_members"] == list("abcd")
    assert proposal["publication_span_days"] == 15 and not proposal["accepted"]
    assert proposal["status"] == "unjudged"


def test_partial_conflicting_anchors_and_missing_cross_features_stay_separate():
    provider = {**PROVIDER, "a": None, "e": "other"}
    result = propose(GROUPS, [], META, provider, RULE)
    assert result["diagnostics"]["partial_groups"] == result["diagnostics"]["conflicting_groups"] == 1
    assert result["diagnostics"]["frame_pairs"] == 0
    rows = scores("ab", "cd")
    rows[0]["features"].pop(FEATURES[0])
    rows[1]["status"] = "failed"
    rows.pop()
    result = propose(GROUPS[:2], rows, META, PROVIDER, RULE)
    candidate = result["candidate_rows"][0]
    assert set(candidate["reasons"]) == {"missing_or_invalid_features", "failed", "missing_row"}
    assert candidate["completed_cross_pair_count"] == 1 and result["proposals"] == []
    monochrome = {item: {**value, "url": "https://www.one.example/a", "body_sha256": "same"}
                  for item, value in META.items()}
    assert propose(GROUPS[:2], scores("ab", "cd"), monochrome, PROVIDER, RULE)["diagnostics"]["diversity_failed_pairs"] == 1


def test_passing_ab_bc_cannot_create_unsupported_abc_proposal():
    rows = scores("ab", "cd") + scores("cd", "ef") + scores("ab", "ef")
    rows[-1]["features"][FEATURES[2]] = .49
    first = propose(GROUPS, rows, META, PROVIDER, RULE)
    assert first["diagnostics"]["qualified_pairs"] == 2
    assert first["diagnostics"]["qualified_bridges_retained"] == 1
    assert len(first["proposals"]) == 1 and len(first["proposals"][0]["old_group_ids"]) == 2
    assert propose(list(reversed(GROUPS)), list(reversed(rows)), META, PROVIDER, RULE) == first
