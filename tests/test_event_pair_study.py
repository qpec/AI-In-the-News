"""Synthetic audited planner checks; no actual source or model research."""
from __future__ import annotations

from typing import Any

import pytest

from newsresearch import event_pair_study as study
from newsresearch.common import AuditError, Context, ResearchError
from test_event_clustering_evaluation import execute as comparison_execute
from test_aws_clustering_evaluation import execute as aws_execute, attempts
from test_retrieval import embedding_plan as _embedding_plan, indexed as _indexed

embedding_plan = _embedding_plan
indexed = _indexed


@pytest.fixture
def previous(indexed: Any) -> Any:
    return comparison_execute(indexed, aws_execute(indexed, limit=5))


def prepare(indexed: Any, previous: Any, monkeypatch: Any, **extra: Any) -> Any:
    engine, _, _ = indexed
    return engine.execute("plan_event_pairs", {"previous_result": previous["id"], "seed": "synthetic-study", **extra},
        objective="Verify a source-free constructed event-pair planner", actor="test:software")


def test_full_dataset_pool_reuses_prior_overlap_and_retains_missing(indexed: Any, previous: Any, monkeypatch: Any) -> None:
    engine, _, _ = indexed
    before = attempts(engine)
    monkeypatch.setattr(engine.gateway.provider, "complete", lambda *args, **kwargs: pytest.fail("No models in preparation"))
    result = prepare(indexed, previous, monkeypatch)
    assert (result["dataset_articles"], result["processed_articles"], result["missing_articles"]) == (11, 9, 2)
    assert result["overlap_vectors_checked"] == previous["processed_articles"]
    assert result["overlap_vectors_byte_equal"] is True
    assert result["candidate_cutoff"] is None
    assert attempts(engine) == before
    assert result["model_calls"] == result["network_calls"] == result["new_embedding_requests"] == 0
    assert "no article judging executed" in study.render(result)
    assert "Candidate cutoff: unavailable" in study.render(result)
    monkeypatch.setattr(engine, "_status", lambda session, context, data: study.load_plan(engine, session, result["id"]))
    plan, frame, development = engine.execute("status", objective="Verify frozen synthetic plan", actor="test")
    assert plan["frame_hash"] == frame["frame_hash"] == development["frame_hash"]
    assert plan["development_pairs"] == len(development["rows"])
    assert "body_sha256" in next(iter(engine.ledger.artifacts.read(plan["metadata_artifact"]).values()))


def test_stable_key_reuses_same_plan_but_rejects_changed_seed(indexed: Any, previous: Any, monkeypatch: Any) -> None:
    first = prepare(indexed, previous, monkeypatch, key="frozen-study")
    second = prepare(indexed, previous, monkeypatch, key="frozen-study")
    assert second["id"] == first["id"] and second["reused"] is True
    with pytest.raises(ResearchError, match="cannot reseal validation"):
        prepare(indexed, previous, monkeypatch, key="frozen-study", seed="changed-seed")


def test_audit_failure_stops_preparation_before_vector_pooling(indexed: Any, previous: Any, monkeypatch: Any) -> None:
    engine, _, _ = indexed
    called = []
    monkeypatch.setattr(study, "aggregate", lambda *args: called.append(True))
    engine.ledger.fail_event = "event_pair.preparation.intended"
    with pytest.raises(AuditError, match="Injected audit failure"):
        prepare(indexed, previous, monkeypatch)
    assert called == []
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_plan'").fetchone()[0] == 0


def test_handlers_require_runtime_and_disallow_model_fields(indexed: Any, previous: Any, monkeypatch: Any) -> None:
    engine, _, _ = indexed
    with pytest.raises(AuditError, match="active audited"):
        study.prepare(engine, "not-active", Context("Bypass", "test"), {"previous_result": previous["id"]})
    with pytest.raises(ResearchError, match="no model execution fields"):
        prepare(indexed, previous, monkeypatch, approval="forbidden")
