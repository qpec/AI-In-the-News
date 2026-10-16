"""Four focused synthetic graph tests; no scientific accuracy claims."""

import math
from itertools import combinations

import pytest

from newsresearch.common import digest
from newsresearch.event_group_refinement import refine
from newsresearch.event_pair_selection import FEATURES

RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def edge(a, b, score, weakest=None):
    features = dict.fromkeys(FEATURES, score)
    if weakest is not None:
        features["first_passage_cosine"] = weakest
    return {"left": a, "right": b, "pair_id": digest(sorted((a, b))),
            "features": features, "publication_gap_days": 0, "status": "completed"}


def groups(*members):
    return [{"group_id": digest(sorted(group)), "members": list(group)} for group in members]


def test_repairs_pooled_greedy_trap_using_all_five_signals():
    edges = [edge("a", "b", .99, .51), edge("b", "c", .9),
             edge("b", "d", .9), edge("c", "d", .9)]
    result = refine(list("abcd"), edges, groups("ab", "cd"), RULE, dict(zip("abcd", "abcd")))
    assert [group["members"] for group in result["groups"]] == [["a"], ["b", "c", "d"]]
    assert result["diagnostics"]["objective_gain"] > 1.5
    assert result["diagnostics"]["converged"]
    assert result["bridges"] == [edges[0]]


def test_chain_and_overlapping_cliques_are_deterministic_and_keep_old_ids():
    edges = [edge("a", "b", .9), edge("b", "c", .8), edge("c", "d", .9), edge("b", "d", .8)]
    baseline = groups("ab", "cd", "e")
    body_ids = dict(zip("abcde", "abcde"))
    first = refine(list("abcde"), edges, baseline, RULE, body_ids)
    reversed_baseline = [{**group, "members": group["members"][::-1]} for group in baseline[::-1]]
    assert refine(list("edcba"), edges[::-1], reversed_baseline, RULE, body_ids) == first
    assert next(group for group in first["groups"] if group["members"] == ["e"]) == baseline[2]
    present = {tuple(sorted((row["left"], row["right"]))) for row in edges}
    assert all(tuple(pair) in present for group in first["groups"] for pair in combinations(group["members"], 2))
    assert sorted(item for group in first["groups"] for item in group["members"]) == list("abcde")


def test_invalid_or_incomplete_edges_and_nonclique_baselines_fail_closed():
    valid = edge("a", "b", .8)
    for broken in ({**valid, "status": "pending"},
                   {**valid, "features": {**valid["features"], FEATURES[0]: math.nan}},
                   {**valid, "publication_gap_days": 8},
                   {**valid, "features": {**valid["features"], FEATURES[0]: .49}}):
        with pytest.raises(ValueError):
            refine(["a", "b"], [broken], groups("a", "b"), RULE, {"a": "a", "b": "b"})
    with pytest.raises(ValueError, match="complete passing clique"):
        refine(list("abc"), [valid], groups("abc"), RULE, dict(zip("abc", "abc")))
    with pytest.raises(ValueError, match="cover every"):
        refine(list("abc"), [valid], groups("ab"), RULE, dict(zip("abc", "abc")))


def test_duplicate_body_copies_do_not_multiply_cross_family_objective():
    single = refine(["a", "b"], [edge("a", "b", .9)], groups("ab"), RULE, {"a": "A", "b": "B"})
    names = ["a1", "a2", "a3", "b1", "b2"]
    copies = {name: name[0].upper() for name in names}
    rows = [edge(a, b, .9) for a in names[:3] for b in names[3:]]
    baseline = groups(*[[name] for name in names])
    result = refine(names, rows, baseline, RULE, copies)
    assert result["diagnostics"]["duplicate_body_families"] == 2
    assert result["diagnostics"]["objective"] <= single["diagnostics"]["objective"]
    assert result["diagnostics"]["objective"] == pytest.approx((.8 + 1e-9) / 3)
    assert result["diagnostics"]["objective_gain"] >= 0
