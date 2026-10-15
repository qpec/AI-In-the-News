"""Synthetic adapter checks, not measurements of real-event accuracy."""
from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import numpy as np
import pytest

from newsresearch import embeddings, event_clustering_core as core, event_clustering_evaluation as evaluation
from newsresearch.common import AuditError, Context, ResearchError, canonical, digest
from test_aws_clustering_evaluation import attempts, execute as aws_execute
from test_retrieval import embedding_plan as _embedding_plan, indexed as _indexed

embedding_plan = _embedding_plan
indexed = _indexed


@pytest.fixture
def previous(indexed: Any) -> Any:
    return aws_execute(indexed)


def execute(indexed: Any, previous: Any, **data: Any) -> Any:
    engine, _, _ = indexed
    return engine.execute("evaluate_event_clustering", {"previous_result": previous["id"], **data}, versions={},
        objective="Compare corrected clustering with exact synthetic prior inputs", actor="test:software")


def test_runtime_strict_inputs_and_context_are_guarded_before_fits(
    indexed: Any, previous: Any, monkeypatch: Any,
) -> None:
    engine, _, _ = indexed
    called: list[bool] = []
    monkeypatch.setattr(core, "retained_dbscan", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(core, "complete_link", lambda *args, **kwargs: called.append(True))
    with pytest.raises(AuditError, match="active audited"):
        evaluation.execute(engine, "not-active", Context("Bypass", "test"), {"previous_result": previous["id"]})
    for data in ({}, {"previous_result": True}, {"previous_result": previous["id"], "limit": 5}):
        with pytest.raises(ResearchError, match="immutable previous AWS"):
            engine.execute("evaluate_event_clustering", data, versions={}, objective="Reject unsupported input", actor="test")
    for key in (True, "", " "):
        with pytest.raises(ResearchError, match="comparison key"):
            execute(indexed, previous, key=key)
    other = engine.execute("version", {"kind": "question", "key": "unrelated-event-comparison",
        "content": {"text": "Different synthetic question"}}, objective="Build wrong context", actor="test")["id"]
    with pytest.raises(ResearchError, match="context differs"):
        engine.execute("evaluate_event_clustering", {"previous_result": previous["id"]},
            versions={"question": other}, objective="Reject changed context", actor="test")
    assert called == []
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_clustering_manifest'").fetchone()[0] == 0


def test_exact_parent_vectors_mapping_selection_and_missingness_are_reused_without_mutation(
    indexed: Any, previous: Any, monkeypatch: Any,
) -> None:
    engine, _, _ = indexed
    before_sources = [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM sources ORDER BY id")]
    before_passages = [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM passages ORDER BY id")]
    parent = engine.ledger.get(previous["id"], "aws_clustering_evaluation")
    parent_bytes = canonical(parent)
    artifact_bytes = {key: engine.ledger.artifacts.read_bytes(parent[key])
        for key in ("pooled_vectors_artifact", "mapping_artifact")}
    before_attempts = attempts(engine)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Exact saved-vector comparison must not call a model")

    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", forbidden)
    monkeypatch.setattr(engine.gateway.provider, "complete", forbidden)
    result = execute(indexed, previous)
    manifest = engine.ledger.get(result["manifest"], "event_clustering_manifest")
    parent_manifest = engine.ledger.get(parent["manifest"], "aws_clustering_manifest")
    assert manifest["previous_manifest"] == parent["manifest"]
    assert manifest["selected_sources"] == parent_manifest["selected_sources"]
    assert manifest["processed_sources"] == [row["source_version"] for row in engine.ledger.artifacts.read(parent["mapping_artifact"])]
    assert result["input_index_versions"] == parent["input_index_versions"]
    assert result["index"] == parent["index"]
    for key, value in artifact_bytes.items():
        assert result[key] == parent[key]
        assert engine.ledger.artifacts.read_bytes(result[key]) == value
    assert (result["dataset_articles"], result["processed_articles"], result["missing_articles"]) == (11, 9, 2)
    assert result["missing"] == parent["missing"]
    assert result["excluded_articles"] == parent["excluded_articles"]
    assert canonical(engine.ledger.get(previous["id"], "aws_clustering_evaluation")) == parent_bytes
    assert [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM sources ORDER BY id")] == before_sources
    assert [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM passages ORDER BY id")] == before_passages
    assert attempts(engine) == before_attempts
    assert result["model_calls"] == result["network_calls"] == result["new_embedding_requests"] == result["accepted_dossiers"] == 0
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert set(result["outputs"]) == {mode["name"] for mode in evaluation.MODES}
    for name in ("retained_batch_0.10", "retained_stream_0.10", "retained_reverse_0.10", "previous_baseline_float64_eps_0.10"):
        assert result["partition_agreement"][name] is True


def test_manifest_and_reuse_intent_precede_all_six_fits_and_mode_artifacts_are_durable(
    indexed: Any, previous: Any, monkeypatch: Any,
) -> None:
    engine, _, _ = indexed
    original_retained, original_compact = core.retained_dbscan, core.complete_link
    expected_mapping = engine.ledger.artifacts.read(previous["mapping_artifact"])
    expected_ids = [row["source_version"] for row in expected_mapping]
    expected_values = np.frombuffer(engine.ledger.artifacts.read_bytes(previous["pooled_vectors_artifact"]), dtype="<f4").reshape(len(expected_ids), -1)
    observed: list[str] = []

    def inspect(values: Any, ids: list[str], strategy: str) -> None:
        row = engine.ledger.db.execute("SELECT id,payload,created_event FROM records "
            "WHERE kind='event_clustering_manifest' ORDER BY created_event DESC LIMIT 1").fetchone()
        assert row is not None
        manifest = json.loads(row["payload"])
        intended = engine.ledger.db.execute("SELECT seq FROM events WHERE kind='event_clustering.intended' "
            "AND json_extract(payload,'$.manifest')=?", (row["id"],)).fetchone()
        reused = engine.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='event_clustering.inputs.reused' "
            "AND json_extract(payload,'$.manifest')=?", (row["id"],)).fetchone()
        assert row["created_event"] < intended[0] < reused["seq"]
        assert manifest["previous_result"] == previous["id"]
        assert manifest["pooled_vectors_artifact"] == previous["pooled_vectors_artifact"]
        assert manifest["mapping_artifact"] == previous["mapping_artifact"]
        assert json.loads(reused["payload"])["reaggregation"] is False
        assert ids in (expected_ids, expected_ids[::-1])
        expected = expected_values if ids == expected_ids else expected_values[::-1]
        assert np.asarray(values, dtype="<f4").tobytes() == expected.tobytes()
        observed.append(strategy)

    def retained(values: Any, ids: list[str], sizes: list[int], **kwargs: Any) -> Any:
        inspect(values, ids, "retained")
        return original_retained(values, ids, sizes, **kwargs)

    def compact(values: Any, ids: list[str], **kwargs: Any) -> Any:
        inspect(values, ids, "compact")
        return original_compact(values, ids, **kwargs)

    monkeypatch.setattr(core, "retained_dbscan", retained)
    monkeypatch.setattr(core, "complete_link", compact)
    result = execute(indexed, previous)
    assert observed == ["retained"] * 3 + ["compact"] * 3
    for mode, artifact in result["mode_artifacts"].items():
        assert canonical(engine.ledger.artifacts.read(artifact)) == canonical(result["outputs"][mode])
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='preparation.artifact.saved' "
            "AND json_extract(payload,'$.artifact')=?", (artifact,)).fetchone()[0] > 0
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='event_clustering.mode.completed' "
            "AND json_extract(payload,'$.artifact')=?", (artifact,)).fetchone()[0] == 1
    assert result["status"] == "completed"


def test_failed_required_audit_write_prevents_all_fits(indexed: Any, previous: Any, monkeypatch: Any) -> None:
    engine, _, _ = indexed
    called: list[bool] = []
    monkeypatch.setattr(core, "retained_dbscan", lambda *args, **kwargs: called.append(True))
    monkeypatch.setattr(core, "complete_link", lambda *args, **kwargs: called.append(True))
    engine.ledger.fail_event = "event_clustering.inputs.reused"
    with pytest.raises(AuditError, match="Injected audit failure"):
        execute(indexed, previous)
    assert called == []
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_clustering_evaluation'").fetchone()[0] == 0


def test_invalid_parent_coverage_order_shape_and_lineage_are_rejected_without_history_edits(
    indexed: Any, previous: Any, monkeypatch: Any,
) -> None:
    engine, _, _ = indexed
    original_get = engine.ledger.get
    parent = original_get(previous["id"], "aws_clustering_evaluation")
    mapping = engine.ledger.artifacts.read(parent["mapping_artifact"])
    chunks = {row["source_version"]: row for row in mapping}
    manifest = original_get(parent["manifest"], "aws_clustering_manifest")
    candidates: list[tuple[str, dict[str, Any], str]] = []
    bad = deepcopy(parent)
    bad["processed_articles"] += 1
    candidates.append((previous["id"], bad, "coverage differ"))
    bad_manifest = deepcopy(manifest)
    mapped_positions = [index for index, item in enumerate(bad_manifest["selected_sources"]) if item in chunks]
    first, second = mapped_positions[:2]
    bad_manifest["selected_sources"][first], bad_manifest["selected_sources"][second] = (
        bad_manifest["selected_sources"][second], bad_manifest["selected_sources"][first])
    candidates.append((parent["manifest"], bad_manifest, "coverage differ"))
    bad_index = deepcopy(original_get(parent["index"], "vector_index"))
    bad_index["dimensions"] += 1
    candidates.append((parent["index"], bad_index, "shape differs"))
    bad = deepcopy(parent)
    bad["input_index_versions"]["question"] = "different-original-question"
    candidates.append((previous["id"], bad, "lineage differ"))
    called: list[bool] = []
    monkeypatch.setattr(core, "retained_dbscan", lambda *args, **kwargs: called.append(True))
    for target, replacement, message in candidates:
        def substituted(identifier: str, kind: str | None = None) -> Any:
            return deepcopy(replacement) if identifier == target else original_get(identifier, kind)

        monkeypatch.setattr(engine.ledger, "get", substituted)
        with pytest.raises(AuditError, match=message):
            execute(indexed, previous)
        monkeypatch.setattr(engine.ledger, "get", original_get)
    assert called == []
    assert canonical(original_get(previous["id"], "aws_clustering_evaluation")) == canonical(parent)


def test_partial_core_results_keep_pending_separate_from_inherited_missing_and_capture_errors(
    indexed: Any, previous: Any, monkeypatch: Any,
) -> None:
    engine, _, _ = indexed
    original = core.retained_dbscan

    def interrupted(values: Any, ids: list[str], sizes: list[int], **kwargs: Any) -> Any:
        output = original(values[:-1], ids[:-1], [len(ids)-1], **kwargs)
        output["complete"] = False
        output["errors"] = [{"error_type": "SyntheticInterruption", "batch": 1}]
        output["coverage"].update({"input_occurrences": len(ids), "unique_input_ids": len(ids),
            "completed_input_occurrences": len(ids)-1, "pending_input_occurrences": 1,
            "missing_pool_ids": [ids[-1]], "never_emitted_ids": [ids[-1]]})
        return output

    monkeypatch.setattr(core, "retained_dbscan", interrupted)
    result = execute(indexed, previous)
    assert result["status"] == "partial"
    assert result["pending_articles"] == 1 and result["missing_articles"] == 2
    assert result["missing"] == previous["missing"]
    assert set(result["failed_modes"]) == {mode["name"] for mode in evaluation.MODES if mode["strategy"] == "dbscan"}
    for name in result["failed_modes"]:
        output = result["outputs"][name]
        pending = output["coverage"]["missing_pool_ids"][0]
        assert not any(pending in group for group in output["partition"])
        assert pending not in output["singletons"]
        assert result["summaries"][name]["pending"] == 1
    for name, output in result["outputs"].items():
        if name.startswith("compact_"):
            assert output["complete"] is True
            assert sum(map(len, output["partition"])) == result["processed_articles"]
    presentation = result["presentation"]
    assert "pending: 1." in presentation["markdown"]
    assert "inherited unprocessed: 2" in presentation["markdown"]
    assert "SyntheticInterruption" in presentation["markdown"]
    assert presentation["versions"] == result["versions"]
    assert presentation["results"] == [{"kind": "event_clustering_evaluation", "id": result["id"]}]
    assert presentation["ui_delivery_verified"] is False
    assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode()
    persisted = engine.ledger.get(result["id"], "event_clustering_evaluation")
    assert persisted["pending_articles"] == 1 and persisted["summaries"] == result["summaries"]


def test_insufficient_vectors_remain_missing_and_show_skipped_modes(indexed: Any) -> None:
    engine, index, _ = indexed
    record = engine.ledger.get(index["id"], "vector_index")
    frame = engine.ledger.get(index["versions"]["dataset"], "dataset")["source_versions"]
    available = {row["source_version"] for row in engine.ledger.artifacts.read(record["rows_artifact"])}
    for number in range(1000):
        seed = f"constructed-empty-vector-branch-{number}"
        ranked = sorted(frame, key=lambda source: (digest({"seed": seed, "source_version": source}), source))
        if not set(ranked[:2]) & available:
            break
    else:
        raise AssertionError("Could not construct missing-only synthetic branch")
    previous = aws_execute(indexed, limit=2, seed=seed)
    assert previous["processed_articles"] == 0
    result = execute(indexed, previous)
    assert result["status"] == "insufficient_vectors" and result["missing_articles"] == 2
    assert result["outputs"] == {} and result["failed_modes"] == []
    assert result["pending_articles"] == 0
    assert "modes executed: 0/6" in result["presentation"]["markdown"]
    assert "insufficient_vectors" in result["presentation"]["markdown"]
