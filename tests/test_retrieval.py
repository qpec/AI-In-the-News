from __future__ import annotations

from dataclasses import replace
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import pytest

from newsresearch.common import AuditError, Context, ResearchError
from newsresearch import embeddings, retrieval
from test_embeddings import approval, embedding_plan as _embedding_plan, mock_transport, run

embedding_plan = _embedding_plan


@pytest.fixture
def indexed(embedding_plan: Any, monkeypatch: Any) -> tuple[Any, Any, Any]:
    engine, plan = embedding_plan
    sent = mock_transport(engine, monkeypatch)
    original = embeddings.OpenAIEmbeddingTransport.send

    def varied(self: Any, body: bytes, client_request_id: str) -> Any:
        response = original(self, body, client_request_id)
        content = json.loads(response.body)
        for item in content["data"]:
            raw = hashlib.sha256(f"{len(sent)}:{item['index']}".encode()).digest()[:16]
            values = (np.frombuffer(raw, dtype="<u4").astype(np.float64) / 2**32 - 0.5).astype("<f4")
            item["embedding"] = base64.b64encode(values.tobytes()).decode()
        return replace(response, body=json.dumps(content).encode())

    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", varied)
    engine.config = replace(engine.config, offline=False)
    completed = run(engine, plan, approval(engine, plan))
    engine.config = replace(engine.config, offline=True)
    built = engine.execute(
        "build_vector_index",
        {"plan": plan["id"], "embedding_run": completed["id"]},
        versions=plan["versions"],
        objective="Index synthetic stored embeddings",
        actor="test",
    )
    return engine, built, {"plan": plan["id"], "embedding_run": completed["id"]}


def execute(engine: Any, index: Any, op: str, **data: Any) -> Any:
    return engine.execute(
        op,
        {"index": index["id"], **data},
        versions=index["versions"],
        objective="Verify synthetic retrieval invariants",
        actor="test",
    )


def test_full_index_coverage_provenance_and_reuse(indexed: Any) -> None:
    engine, index, inputs = indexed
    assert index["vector_count"] > 0 and index["indexed_sources"] == 9
    assert index["source_records"] == 11 and index["text_unavailable_records"] == 2
    assert index["network_calls"] == index["model_calls"] == 0
    versions = {k: v for k, v in index["versions"].items() if k != "retrieval_profile"}
    repeated = engine.execute(
        "build_vector_index",
        inputs,
        versions=versions,
        objective="Explicitly reuse exact synthetic index",
        actor="test",
    )
    assert repeated["id"] == index["id"]
    record = engine.ledger.get(index["id"], "vector_index")
    rows = engine.ledger.artifacts.read(record["rows_artifact"])
    assert len({r["id"] for r in rows}) == len(rows)
    for row in rows:
        passage = engine.ledger.db.execute(
            "SELECT * FROM passages WHERE id=?", (row["passage_id"],)
        ).fetchone()
        assert passage["source_id"] == row["source_version"]
        assert passage["start"] <= row["source_start"] < row["source_end"] <= passage["end"]
    engine.execute("status", objective="Verify binary index audit", actor="test")


def test_search_retains_missingness_distinct_passages_and_provider_candidates(indexed: Any) -> None:
    engine, index, _ = indexed
    report = execute(engine, index, "vector_search", source_ids="all")
    assert report["selected_sources"] == 11 and report["searched_sources"] == 9
    assert report["unprocessed_text_sources"] == 2 and report["directed_provider_candidates"] == 2
    stored = engine.ledger.get(report["id"], "candidate_run")
    for identifier in stored["result_ids"]:
        result = engine.ledger.get(identifier, "article_candidates")
        for candidate in result["vector_candidates"]:
            assert candidate["source_version"] != result["source_version"]
            assert candidate["event_identity"] == "unassessed"
            assert -1.000001 <= candidate["score"] <= 1.000001
            pairs = {
                (m["query_chunk"]["passage_id"], m["target_chunk"]["passage_id"])
                for m in candidate["matches"]
            }
            assert len(pairs) == len(candidate["matches"])
        if result["status"] == "unprocessed_text":
            assert result["vector_candidates"] == []
    resumed = execute(engine, index, "vector_search", source_ids="all")
    assert resumed["new_results"] == 0 and resumed["reused_results"] == 11
    inspection = execute(engine, index, "inspect_candidates", run=report["id"], limit=2)
    assert len(inspection["results"]) == 2 and inspection["truncated"]
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0


def test_numerical_recall_matches_independent_bruteforce(indexed: Any) -> None:
    engine, index, _ = indexed
    result = execute(engine, index, "evaluate_vector_index")
    assert result["expected_neighbors"] > 0
    assert result["tie_aware_recall_at_k"] == 1
    assert "semantic/event recall unmeasured" in result["scope"]
    assert result["network_calls"] == result["model_calls"] == 0
    record = engine.ledger.get(index["id"], "vector_index")
    rows = engine.ledger.artifacts.read(record["rows_artifact"])
    matrix = np.frombuffer(engine.ledger.artifacts.read_bytes(record["vectors_artifact"]), dtype="<f4")
    matrix = matrix.reshape(len(rows), record["dimensions"])
    for item in engine.ledger.artifacts.read(result["details_artifact"]):
        query = next(n for n, row in enumerate(rows) if row["id"] == item["query_chunk"]["id"])
        actual = matrix @ matrix[query]
        order = sorted(
            (n for n in range(len(rows)) if rows[n]["source_version"] != rows[query]["source_version"]),
            key=lambda n: (-actual[n], n),
        )[: result["k"]]
        assert [pair[0] for pair in item["exact"]] == order


def test_search_rejects_wrong_versions_and_out_of_frame_queries(indexed: Any) -> None:
    engine, index, _ = indexed
    with pytest.raises(ResearchError, match="distinct source"):
        execute(engine, index, "vector_search", source_ids=["unknown"])
    wrong = {k: v for k, v in index["versions"].items() if k != "embedding_profile"}
    with pytest.raises(ResearchError, match="exact index"):
        engine.execute(
            "vector_search",
            {"index": index["id"], "source_ids": "all"},
            versions=wrong,
            objective="Reject unrelated version context",
            actor="test",
        )
    with pytest.raises(AuditError, match="active audited"):
        retrieval.search(engine, "invalid", Context("Direct bypass", "test", index["versions"]), {})


def test_incomplete_embeddings_cannot_create_index(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    mock_transport(engine, monkeypatch)
    engine.config = replace(engine.config, offline=False)
    partial = run(engine, plan, approval(engine, plan), limit=1)
    with pytest.raises(ResearchError, match="complete reconciled"):
        engine.execute(
            "build_vector_index",
            {"plan": plan["id"], "embedding_run": partial["id"]},
            versions=plan["versions"],
            objective="Reject incomplete vector coverage",
            actor="test",
        )


def test_missing_index_artifact_fails_preflight(indexed: Any) -> None:
    engine, index, _ = indexed
    record = engine.ledger.get(index["id"], "vector_index")
    (engine.ledger.artifacts.root / record["index_artifact"]).unlink()
    with pytest.raises(AuditError, match="artifact is missing"):
        execute(engine, index, "vector_search", source_ids="all")


def test_durable_intent_failure_stops_index(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    mock_transport(engine, monkeypatch)
    engine.config = replace(engine.config, offline=False)
    completed = run(engine, plan, approval(engine, plan))
    engine.ledger.fail_event = "retrieval.index.intended"
    with pytest.raises(AuditError):
        engine.execute(
            "build_vector_index",
            {"plan": plan["id"], "embedding_run": completed["id"]},
            versions=plan["versions"],
            objective="Stop on failed durable intent",
            actor="test",
        )
    assert (
        engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='vector_index'").fetchone()[0] == 0
    )


def test_full_precision_reranking_excludes_self_and_collapses_overlaps() -> None:
    matrix = np.array([[1, 0], [0.9, 0.1], [0.8, 0.2], [0, 1], [-1, 0]], dtype=np.float32)
    faiss.normalize_L2(matrix)
    rows = [
        {"id": str(n), "source_version": s, "passage_id": p}
        for n, (s, p) in enumerate([("a", "a1"), ("b", "b1"), ("b", "b1"), ("c", "c1"), ("a", "a2")])
    ]

    class Approximate:
        hnsw = type("HNSW", (), {"efSearch": 0})()

        def search(self, query: Any, k: int) -> Any:
            # Deliberately put c ahead of b. Exact cosine must reverse their order.
            return np.array([[1, 0.99, 0.8, 0.7, -0.1]]), np.array([[0, 3, 1, 2, 4]])

    result = retrieval.article_candidates(Approximate(), matrix, rows, [0], retrieval.METHOD)
    assert [r["source_version"] for r in result] == ["b", "c"]
    assert len(result[0]["matches"]) == 1
    assert result[0]["score"] == pytest.approx(float(matrix[0] @ matrix[1]))


def test_streamed_artifacts_detect_corruption_without_bulk_reads(engine: Any, monkeypatch: Any) -> None:
    source = engine.ledger.root / "synthetic-binary"
    source.write_bytes(b"test binary" * 1000)
    source.chmod(0o600)
    reference = engine.ledger.artifacts.put_file(source)
    source.unlink()
    path = engine.ledger.artifacts.verified_path(reference)
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(AssertionError("bulk read")))
    assert engine.ledger.artifacts.verified_path(reference) == path
    with path.open("r+b") as stream:
        stream.write(b"X")
    with pytest.raises(AuditError, match="integrity"):
        engine.ledger.artifacts.verified_path(reference)
