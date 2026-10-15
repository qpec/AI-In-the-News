from __future__ import annotations

import json
from statistics import median
from typing import Any

import pytest

from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.query_overview import overview
from test_similarity_tags import prepared_query as _prepared_query, indexed as _indexed, embedding_plan as _embedding_plan, score

prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


def test_overview_freezes_full_denominator_scores_top_sources_and_chart(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    result = run("article_query_overview", {"run": scored["run"], "top": 3})
    values = sorted(expected.values())
    assert result["expected_articles"] == result["logged_articles"] == 11
    assert result["scored_articles"] == 9 and result["unprocessed_articles"] == 2 and not result["pending_articles"]
    assert result["score_statistics"]["minimum"] == values[0]
    assert result["score_statistics"]["maximum"] == values[-1]
    assert result["score_statistics"]["median"] == median(values)
    assert result["score_statistics"]["mean"] == pytest.approx(sum(values)/len(values))
    assert sum(b["articles"] for b in result["score_bands"]) == 9
    assert [a["score"] for a in result["top_articles"]] == sorted(values, reverse=True)[:3]
    for article in result["top_articles"]:
        source = json.loads(engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (article["source_version"],)).fetchone()[0])
        assert article["title"] == source["title"] and article["passage_id"]
    assert result["answer_counts"] == {"None": 11}
    snapshot = engine.ledger.artifacts.read(result["snapshot_artifact"])
    assert len(snapshot) == 11 and all(row["result_id"] for row in snapshot)
    chart = engine.ledger.get(result["chart"], "article_query_chart")
    assert chart["table"] == result["id"]
    assert engine.ledger.artifacts.read_bytes(chart["image"]).startswith(b"\x89PNG")
    assert len(sent) == 1 and result["network_calls"] == result["model_calls"] == 0
    assert engine.ledger.verify()["status"] == "verified"


def test_overview_rejects_wrong_versions_and_invalid_limit(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    with pytest.raises(ResearchError, match="exact version"):
        engine.execute("article_query_overview", {"run": scored["run"]},
                       versions=index["versions"], objective="Test incorrect overview context", actor="test")
    with pytest.raises(ResearchError, match="limit"):
        run("article_query_overview", {"run": scored["run"], "top": 0})


def test_overview_preserves_partial_run_pending_coverage(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    engine.ledger.fail_event = "record.created"
    with pytest.raises(AuditError):
        score(prepared_query)
    engine.ledger.fail_event = None
    # Use a fresh runtime operation to register a valid intended manifest, then fault before rows.
    original = engine.ledger.record
    def fail(session: str, kind: str, key: str, payload: Any, *extra: Any, **options: Any) -> str:
        if kind == "article_query_result":
            raise AuditError("Synthetic row failure")
        return original(session, kind, key, payload, *extra, **options)
    engine.ledger.record = fail
    with pytest.raises(AuditError):
        score(prepared_query)
    engine.ledger.record = original
    manifest = engine.ledger.db.execute("SELECT id FROM records WHERE kind='article_query_manifest'").fetchone()[0]
    result = run("article_query_overview", {"run": manifest})
    assert result["expected_articles"] == result["pending_articles"] == 11
    assert result["logged_articles"] == result["scored_articles"] == 0
    assert result["score_statistics"]["median"] is None
    assert result["top_articles"] == []


def test_overview_requires_runtime(prepared_query: Any) -> None:
    with pytest.raises(AuditError):
        overview(prepared_query[0], "invalid", Context("test", "test"), {})
