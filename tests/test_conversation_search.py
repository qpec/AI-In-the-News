"""Source-free tests for explicit conversation corpus retrieval."""
from __future__ import annotations

from typing import Any

import pytest

from newsresearch.common import AuditError, Context, ResearchError, utc
from newsresearch.conversation_search import execute, query_expression
from newsresearch.demo import source


def test_literal_keyword_expression_never_accepts_operators() -> None:
    assert query_expression('AI OR "outage"; DROP --') == '"ai" OR "or" OR "outage" OR "drop"'
    assert query_expression("Éthique éthique AI") == '"éthique" OR "ai"'
    with pytest.raises(ResearchError):
        query_expression("!!!")
    with pytest.raises(ResearchError):
        query_expression(" ".join(f"word{n}" for n in range(41)))


def test_direct_handler_cannot_retrieve(prepared: Any) -> None:
    engine, versions, _ = prepared
    with pytest.raises(AuditError):
        execute(engine, "bypass", Context("Synthetic test", "test", versions), {"query": "outage"})


def test_local_search_filters_dataset_and_captures_ranked_overview(prepared: Any) -> None:
    engine, versions, run = prepared
    # A separate dataset contains an otherwise matching source: it must never
    # enter this result's source frame or matching denominator.
    outside = run("ingest", {"articles": [source("outside", "outage outage outside corpus")],
        "retrieval": {"source": "synthetic", "retrieved_at": utc(), "parameters": {}}, "key": "outside"})
    result = engine.execute("conversation_search", {"query": "outage", "question": "What was reported?",
        "key": "synthetic-conversation-search"}, objective="Test local conversational retrieval",
        actor="synthetic:test", versions={"dataset": versions["dataset"]})
    assert result["dataset_articles"] == 3 and result["matching_articles"] == 2
    assert result["returned_articles"] == 2 and result["returned_passages"] == 2
    assert not set(outside["sources"]) & {r["source_version"] for r in result["source_rows"]}
    assert result["embedding_requests"] == result["model_calls"] == 0
    assert result["cutoff"] is None
    assert "BM25" in result["presentation"]["markdown"]
    assert result["presentation"]["destination"] == "local_app"
    assert result["presentation"]["ui_delivery_verified"] is False
    definition = engine.ledger.get(result["selection"]["definition"], "conversation_definition")
    assert definition["origin"] == {"kind": "conversation_retrieval", "id": result["id"]}
    assert engine.ledger.verify()["status"] == "verified"


def test_zero_matches_retained_not_a_negative_finding(prepared: Any) -> None:
    engine, versions, _ = prepared
    result = engine.execute("conversation_search", {"query": "absentkeyword", "question": "Any matching evidence?",
        "key": "synthetic-zero-search"}, objective="Test zero match capture", actor="synthetic:test",
        versions={"dataset": versions["dataset"]})
    assert result["matching_articles"] == result["returned_articles"] == 0
    assert result["evidence"] == []
    assert "No keyword matches" in result["presentation"]["markdown"]
    assert result["selection"]["included_passages"] == 0
