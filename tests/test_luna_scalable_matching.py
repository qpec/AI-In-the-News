"""Synthetic behavior and resource-bound checks; not news accuracy evidence."""
from dataclasses import replace
import sqlite3

import pytest

from newsresearch.common import ResearchError
from newsresearch import luna_scalable_matching as m


def row(identifier, *, corpus="a", name="Example Labs", day=739600, action="launch", fact="v12"):
    return m.Features(identifier, corpus, day, frozenset({name}), frozenset({"initiator:" + name}),
        frozenset({action}), frozenset({name, action, fact, "service"}),
        frozenset({fact}), (name + " " + action + " " + fact,), frozenset(), 1)


def test_normalization_dates_and_missingness():
    assert m.normalize("  MÜNCHEN — Labs  ") == "munchen labs"
    assert m.publication_day("2026-10-20T04:00:00Z") == m.publication_day("2026-10-20")
    assert m.publication_day("yesterday") is None
    values = m.pair_features(row("a"), row("b", day=None))
    assert values["publication_gap_days"] is None
    assert m.rule_label(values) == "unresolved"
    assert m.rule_label(m.pair_features(row("a"), row("b"))) == "same_event"
    assert m.rule_label(m.pair_features(row("a"), replace(row("b"), variants=2))) == "unresolved"


def test_hot_postings_are_bounded_and_corpora_isolated():
    rows = [row(f"a-{i:04d}") for i in range(1000)] + [row("other", corpus="b")]
    cfg = m.Settings(top_k=10, posting_cap=16)
    index = m.Index(rows, cfg)
    for identifier in ("a-0000", "a-0500", "a-0999"):
        result = index.query(identifier)
        assert len(result["neighbors"]) == 10
        assert result["candidates_scored"] <= cfg.keys_per_article * cfg.posting_cap
        assert result["postings_touched"] <= cfg.keys_per_article * cfg.posting_cap
        assert result["retrieval_incomplete"] is True
        assert all(p["article_id"].startswith("a-") for p in result["neighbors"])
    assert index.query("other")["neighbors"] == []


def test_deterministic_order_and_no_forced_neighbors(tmp_path):
    rows = [row("a"), row("b"), row("c", name="Different Co", action="arrest", fact="z99")]
    a, b = m.Index(rows), m.Index(reversed(rows))
    assert list(a.query_all()) == list(b.query_all())
    assert a.query("c")["neighbors"] == []
    output = tmp_path / "candidates.sqlite3"
    report = m.write_candidates(a, output)
    assert report["unique_pairs"] == 1
    db = sqlite3.connect(output)
    try:
        assert db.execute("SELECT left_id,right_id FROM pairs").fetchall() == [("a", "b")]
        assert db.execute("SELECT value FROM metadata WHERE key='complete'").fetchone()[0] == "true"
    finally:
        db.close()
    with pytest.raises(ResearchError, match="no_overwrite"):
        m.write_candidates(a, output)


def test_no_transitive_merge_and_bounded_verification():
    positive = [{"left": "a", "right": "b", "label": "same_event", "score": 1},
        {"left": "b", "right": "c", "label": "same_event", "score": .9}]
    missing = m.complete_link_groups("abc", positive)
    assert missing["groups"] == [["a", "b"], ["c"]]
    assert missing["verification_queue"] == [["a", "c"]]
    capped = m.complete_link_groups("abc", positive, verification_cap=0)
    assert capped["verification_cap_hit"] and not capped["verification_queue"]
    for label in ("different_event", "unresolved", "insufficient_evidence"):
        result = m.complete_link_groups("abc", positive + [{"left": "a", "right": "c", "label": label}])
        assert result["groups"] == [["a", "b"], ["c"]]
        assert result["blocked_merges"] == 1 and not result["verification_queue"]
    all_same = m.complete_link_groups("abc", positive + [{"left": "a", "right": "c", "label": "same_event"}])
    assert all_same["groups"] == [["a", "b", "c"]]


def test_group_limits_and_conflicting_inputs():
    links = [{"left": a, "right": b, "label": "same_event"} for a, b in (("a", "b"), ("a", "c"), ("b", "c"))]
    assert m.complete_link_groups("abc", links, max_size=2)["oversize_merges"] == 2
    with pytest.raises(ResearchError, match="conflicting"):
        m.complete_link_groups("abc", links + [{"left": "b", "right": "a", "label": "different_event"}])
    with pytest.raises(ResearchError, match="duplicate"):
        m.Index([row("a"), row("a")])
    with pytest.raises(ResearchError, match="invalid_scalable_pair"):
        m.pair_features(row("a"), row("b", corpus="b"))
