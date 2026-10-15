from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
import sqlite3
from typing import Any

import numpy as np
import pytest

from newsresearch import similarity_tags
from newsresearch.common import AuditError, Context, ResearchError
from test_retrieval import indexed as _indexed, embedding_plan as _embedding_plan
from test_embeddings import approval, mock_transport, run as embed

indexed = _indexed
embedding_plan = _embedding_plan


def prepare(indexed: Any, monkeypatch: Any, *, change: Any = None) -> tuple[Any, ...]:
    engine, index, _ = indexed
    record = engine.ledger.get(index["id"], "vector_index")
    rows = engine.ledger.artifacts.read(record["rows_artifact"])
    values = np.frombuffer(engine.ledger.artifacts.read_bytes(record["vectors_artifact"]), dtype="<f4").reshape(-1, 4)
    # Independent synthetic oracle: the scripted query embedding is the unit x-axis.
    expected: dict[str, float] = {}
    for row, vector in zip(rows, values, strict=True):
        source = row["source_version"]
        expected[source] = max(expected.get(source, -1.0), float(vector[0]))
    ordered = sorted(expected, key=lambda s: expected[s])
    examples = [(ordered[-2], "calibration", True), (ordered[1], "calibration", False),
                (ordered[-1], "test", True), (ordered[0], "test", False)]
    evaluation = {"method": "query-tag-calibration-v1", "priority": "balanced", "minimum_per_class_per_split": 1,
                  "minimum_test_precision": 0.8, "minimum_test_recall": 0.8,
                  "items": [{"source_version": s, "split": split, "relevant": label, "group": str(n),
                             "reviewer": "synthetic:test", "reviewer_type": "human",
                             "reason": "Developer-visible synthetic oracle; not scientific evaluation"}
                            for n, (s, split, label) in enumerate(examples)]}
    if change:
        change(evaluation)
    plan = engine.execute("similarity_setup", {"index": index["id"], "query": "AI 'outages'; -- fixture",
        "question": "Is this synthetic report relevant to outages?", "tag": "fixture_outage", "evaluation": evaluation},
        versions={"dataset": index["versions"]["dataset"]}, objective="Test offline query embedding plan", actor="test:setup")
    sent = mock_transport(engine, monkeypatch)
    engine.config = replace(engine.config, offline=False)
    query_run = embed(engine, plan, approval(engine, plan))
    engine.config = replace(engine.config, offline=True)

    def run(operation: str, data: dict[str, Any]) -> Any:
        return engine.execute(operation, data, versions=plan["versions"],
                              objective="Test audited exhaustive local query scoring", actor="test:local")

    return engine, index, plan, query_run, expected, sent, run


@pytest.fixture
def prepared_query(indexed: Any, monkeypatch: Any) -> tuple[Any, ...]:
    return prepare(indexed, monkeypatch)


def score(fixture: Any, **extra: Any) -> Any:
    engine, index, plan, query_run, expected, sent, run = fixture
    return run("similarity_score", {"plan": plan["id"], "embedding_run": query_run["id"], **extra})


def test_single_query_call_and_exhaustive_exact_sql_scores(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    assert plan["expected_chunks"] == 1 and len(sent) == 1
    assert plan["network_calls"] == plan["model_calls"] == 0
    scored = score(prepared_query)
    assert scored["expected_articles"] == 11 and scored["scored_articles"] == 9 and scored["missing_articles"] == 2
    assert scored["chunks_scored"] == index["vector_count"]
    assert len(sent) == 1 and scored["network_calls"] == scored["model_calls"] == 0
    read = run("article_query_rows", {"run": scored["run"]})
    assert len(read["rows"]) == 11
    for row in read["rows"]:
        assert row["query"] == "AI 'outages'; -- fixture" and row["question"].endswith("outages?")
        assert row["answer"] is None and row["threshold"] is None
        assert row["actor"] == "test:local" and row["audit_event"] and row["audit_hash"]
        assert row["query_embedding_result"] and row["query_request_id"]
        assert row["query_attempt_id"]
        assert (row["query_planned_at"] <= row["query_request_started_at"] <= row["query_response_received_at"]
                <= row["score_run_started_at"] <= row["score_run_completed_at"] <= row["recorded_at"])
        assert datetime.fromisoformat(row["query_request_started_at"]).utcoffset().total_seconds() == 0
        assert row["tag_applied_at"] is None
        assert json.loads(row["query_usage_json"])["total_tokens"] > 0
        assert row["article_model_calls"] == 0 and "do not sum" in row["query_usage_scope"]
        assert json.loads(row["session_audit_json"])["context"]["actor"] == "test:local"
        if row["source_version"] in expected:
            assert row["score"] == pytest.approx(expected[row["source_version"]], abs=1e-7)
            assert row["chunks_scored"] > 0 and row["evidence_json"]
        else:
            assert row["score"] is None and row["status"] == "unprocessed_no_vector"
    assert engine.ledger.verify()["status"] == "verified"


def test_threshold_creates_append_only_answer_for_each_article(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    calibration = run("similarity_calibrate", {"scores": scored["id"]})
    assert calibration["passed"] and calibration["test"]["precision"] == calibration["test"]["recall"] == 1
    applied = run("similarity_apply", {"scores": scored["id"], "calibration": calibration["id"]})
    rows = run("article_query_rows", {"run": applied["run"]})["rows"]
    assert len(rows) == 11 and applied["classified_articles"] == 9
    for row in rows:
        assert row["threshold"] == calibration["threshold"]
        assert row["calibration_id"] == calibration["id"] and row["parent_result"]
        if row["score"] is None:
            assert row["answer"] is None
        else:
            assert row["answer"] == ("yes" if row["score"] >= row["threshold"] else "no")
    old = run("article_query_rows", {"run": scored["run"]})["rows"]
    assert all(row["answer"] is None for row in old)
    previous = {row["source_version"]: row for row in old}
    for row in rows:
        original = previous[row["source_version"]]
        for key in ("query_planned_at", "query_request_started_at", "query_response_received_at",
                    "score_run_started_at", "score_run_completed_at"):
            assert row[key] == original[key]
        assert row["score_run_completed_at"] <= row["tag_application_started_at"] <= row["tag_applied_at"] <= row["recorded_at"]
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_result'").fetchone()[0] == 22
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        engine.ledger.db.execute("UPDATE records SET payload='{}' WHERE id=?", (rows[0]["result_id"],))
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert len(sent) == 1 and not engine.ledger.verify()["unresolved_model_attempts"]


def test_explicit_cache_reuse_preserves_original_row_provenance(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    first = score(prepared_query)
    with pytest.raises(ResearchError, match="reuse_cache"):
        score(prepared_query)
    repeated = score(prepared_query, reuse_cache=True)
    assert first["run"] == repeated["run"] and first["id"] == repeated["id"]
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_result'").fetchone()[0] == 11
    assert len(sent) == 1


@pytest.mark.parametrize("filters", [{"limit": 1}, {"source_ids": []}])
def test_no_target_filter_is_allowed(prepared_query: Any, filters: Any) -> None:
    with pytest.raises(ResearchError, match="filters"):
        score(prepared_query, **filters)


def test_sql_inspection_checks_versions_and_pages(prepared_query: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    scored = score(prepared_query)
    page = run("article_query_rows", {"run": scored["run"], "limit": 3, "offset": 1})
    assert len(page["rows"]) == 3 and page["expected_articles"] == 11
    with pytest.raises(ResearchError, match="exact version"):
        engine.execute("article_query_rows", {"run": scored["run"]}, versions=index["versions"], objective="Test wrong context", actor="test")


def test_heldout_labels_cannot_select_threshold(indexed: Any, monkeypatch: Any) -> None:
    def change(evaluation: Any) -> None:
        for item in evaluation["items"][2:]:
            item["relevant"] = not item["relevant"]
    fixture = prepare(indexed, monkeypatch, change=change)
    scored = score(fixture)
    run = fixture[-1]
    calibration = run("similarity_calibrate", {"scores": scored["id"]})
    assert calibration["threshold"] == sorted(fixture[4].values())[-2]
    assert not calibration["passed"]
    with pytest.raises(ResearchError, match="passing"):
        run("similarity_apply", {"scores": scored["id"], "calibration": calibration["id"]})


def test_audit_failure_leaves_manifest_and_no_success(prepared_query: Any, monkeypatch: Any) -> None:
    engine, index, plan, query_run, expected, sent, run = prepared_query
    original = engine.ledger.record
    def fail(session: str, kind: str, key: str, payload: Any, *args: Any, **kwargs: Any) -> Any:
        if kind == "article_query_result":
            raise AuditError("Synthetic row write failure")
        return original(session, kind, key, payload, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", fail)
    with pytest.raises(AuditError, match="row write"):
        score(prepared_query)
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_manifest'").fetchone()[0] == 1
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_run'").fetchone()[0] == 0
    assert len(sent) == 1


def test_query_paid_execution_still_needs_explicit_authorization(indexed: Any) -> None:
    engine, index, _ = indexed
    planned = engine.execute("similarity_setup", {"index": index["id"], "query": "test", "question": "Test?", "tag": "test"},
        versions={"dataset": index["versions"]["dataset"]}, objective="Plan without permission for a call", actor="test")
    assert planned["expected_chunks"] == 1 and planned["model_calls"] == 0
    with pytest.raises(ResearchError, match="offline"):
        embed(engine, planned)


def test_direct_handlers_cannot_bypass_runtime(indexed: Any) -> None:
    with pytest.raises(AuditError):
        similarity_tags.score(indexed[0], "invalid", Context("test", "test"), {})


def test_recall_is_registered_as_default_priority(indexed: Any, monkeypatch: Any) -> None:
    fixture = prepare(indexed, monkeypatch, change=lambda evaluation: evaluation.pop("priority"))
    engine, _, plan, *_ = fixture
    evaluation = engine.ledger.get(plan["versions"]["evaluation"], "evaluation")["content"]
    assert evaluation["priority"] == "recall"
    scored = score(fixture)
    calibrated = fixture[-1]("similarity_calibrate", {"scores": scored["id"]})
    assert calibrated["calibration"]["beta"] == 2.0
