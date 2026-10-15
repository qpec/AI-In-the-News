"""Synthetic integration checks; never evidence of real-event clustering accuracy."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np
import pytest

from newsresearch import aws_clustering_core as core
from newsresearch import aws_clustering_evaluation as evaluation
from newsresearch.common import AuditError, Context, ResearchError, canonical
from test_retrieval import embedding_plan as _embedding_plan, indexed as _indexed


embedding_plan = _embedding_plan
indexed = _indexed


def execute(fixture: Any, **data: Any) -> Any:
    engine, index, _ = fixture
    return engine.execute("evaluate_aws_clustering", {"index": index["id"], "limit": 11,
        "seed": "synthetic-aws-pilot", **data}, versions={},
        objective="Check the audited AWS adapter with constructed sources and vectors", actor="test:software")


def attempts(engine: Any) -> int:
    return engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0]


def test_runtime_guards_context_and_strict_pilot_limits_before_any_fit(indexed: Any, monkeypatch: Any) -> None:
    engine, index, _ = indexed
    called = []
    monkeypatch.setattr(core, "load_upstream", lambda: called.append(True))
    with pytest.raises(AuditError, match="active audited"):
        evaluation.execute(engine, "not-active", Context("Bypass", "test"), {"index": index["id"]})
    for limit in (True, 1, 2001, 2.5, "11"):
        with pytest.raises(ResearchError, match="2 through 2000"):
            execute(indexed, limit=limit)
    other = engine.execute("version", {"kind": "question", "key": "unrelated-aws-context",
        "content": {"text": "A different synthetic question"}}, objective="Set up a wrong version fixture", actor="test")["id"]
    with pytest.raises(ResearchError, match="context differs"):
        engine.execute("evaluate_aws_clustering", {"index": index["id"], "limit": 11},
            versions={**index["versions"], "question": other}, objective="Reject context substitution", actor="test")
    assert called == []
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='aws_clustering_manifest'").fetchone()[0] == 0


def test_selection_is_reproducible_and_never_replaces_selected_missing_vectors(indexed: Any) -> None:
    engine, index, _ = indexed
    record = engine.ledger.get(index["id"], "vector_index")
    frame = engine.ledger.get(index["versions"]["dataset"], "dataset")["source_versions"]
    indexed_ids = {row["source_version"] for row in engine.ledger.artifacts.read(record["rows_artifact"])}
    missing = set(frame) - indexed_ids
    # Deliberately construct the software branch with a selected unavailable
    # article. This seed choice establishes no scientific sampling result.
    for n in range(100):
        seed = f"synthetic-missing-branch-{n}"
        ranked = sorted(frame, key=lambda source: (
            hashlib.sha256(canonical({"seed": seed, "source_version": source}).encode()).hexdigest(), source))
        if set(ranked[:5]) & missing:
            break
    else:
        raise AssertionError("Could not construct the synthetic missing-vector branch")
    before = attempts(engine)
    first, second = execute(indexed, limit=5, seed=seed), execute(indexed, limit=5, seed=seed)
    first_manifest = engine.ledger.get(first["manifest"], "aws_clustering_manifest")
    second_manifest = engine.ledger.get(second["manifest"], "aws_clustering_manifest")
    assert first_manifest["selected_sources"] == second_manifest["selected_sources"] == ranked[:5]
    assert set(first_manifest["excluded_sources"]) == set(frame) - set(ranked[:5])
    assert first["selected_articles"] == 5 and first["excluded_articles"] == 6
    assert first["missing_articles"] == len(set(ranked[:5]) & missing) > 0
    assert first["processed_articles"] + first["missing_articles"] == 5
    assert first["pooled_vectors_artifact"] == second["pooled_vectors_artifact"]
    assert first["mapping_artifact"] == second["mapping_artifact"]
    assert attempts(engine) == before


def test_checkpoint_preserves_original_embedding_lineage_despite_a_later_query_plan(indexed: Any, monkeypatch: Any) -> None:
    from newsresearch import embeddings, similarity_tags

    engine, index, inputs = indexed
    record = engine.ledger.get(index["id"], "vector_index")
    monkeypatch.setattr(similarity_tags, "offline_tokenizer", embeddings.offline_tokenizer)
    later = engine.execute("similarity_setup", {"index": index["id"], "query": "Later synthetic query",
        "question": "Does this report match a later question?", "tag": "later-aws-fixture"},
        versions={"dataset": index["versions"]["dataset"]}, objective="Create a later query-only plan without inference", actor="test")
    assert later["id"] != inputs["plan"]
    before_sources = [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM sources ORDER BY id")]
    before_passages = [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM passages ORDER BY id")]
    original_hashes = {name: engine.ledger.artifacts.read_bytes(record[name]) for name in
        ("index_artifact", "vectors_artifact", "rows_artifact", "sources_artifact")}
    before_attempts = attempts(engine)

    def forbidden(*args: Any, **kwargs: Any):
        raise AssertionError("The offline evaluation must never call a model or transport")

    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", forbidden)
    monkeypatch.setattr(engine.gateway.provider, "complete", forbidden)
    result = execute(indexed)
    checkpoint = engine.ledger.get(result["checkpoint"], "embedding_checkpoint_result")
    assert checkpoint["index"] == index["id"]
    assert checkpoint["embedding_plan"] == inputs["plan"] != later["id"]
    assert checkpoint["embedding_run"] == inputs["embedding_run"]
    assert checkpoint["dataset"] == index["versions"]["dataset"]
    assert checkpoint["retained_artifacts"] == {key: record[key] for key in original_hashes}
    assert [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM sources ORDER BY id")] == before_sources
    assert [tuple(row) for row in engine.ledger.db.execute("SELECT * FROM passages ORDER BY id")] == before_passages
    assert all(engine.ledger.artifacts.read_bytes(record[key]) == value for key, value in original_hashes.items())
    assert result["model_calls"] == result["network_calls"] == result["new_embedding_requests"] == 0
    assert result["aws_resources_created"] == 0 and result["summarization"] == "not_executed"
    assert attempts(engine) == before_attempts
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    presentation = result["presentation"]
    assert presentation["versions"] == result["versions"] == checkpoint["versions"]
    assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode()
    assert {item["kind"] for item in presentation["results"]} == {"aws_clustering_evaluation", "embedding_checkpoint_result"}
    assert presentation["ui_delivery_verified"] is False


def test_manifest_source_code_and_pooled_inputs_are_durable_before_real_fixture_fits(indexed: Any, monkeypatch: Any) -> None:
    engine, index, _ = indexed
    source_ids = set(engine.ledger.get(index["versions"]["dataset"], "dataset")["source_versions"])
    original_upstream, original_baseline = core.UpstreamRunner.run_batches, core.offline_baseline
    observed = []

    def inspect(values: Any, ids: Any, mode: str):
        if not set(ids) <= source_ids:
            return  # Source-free, separately identified software probes.
        manifest_row = engine.ledger.db.execute("SELECT id,payload,created_event FROM records "
            "WHERE kind='aws_clustering_manifest' ORDER BY created_event DESC LIMIT 1").fetchone()
        assert manifest_row is not None
        manifest = json.loads(manifest_row["payload"])
        intended = engine.ledger.db.execute("SELECT seq FROM events WHERE kind='aws_evaluation.intended' "
            "AND json_extract(payload,'$.manifest')=?", (manifest_row["id"],)).fetchone()
        prepared = engine.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='aws_evaluation.vectors.prepared' "
            "AND json_extract(payload,'$.manifest')=?", (manifest_row["id"],)).fetchone()
        assert manifest_row["created_event"] < intended[0] < prepared[0]
        prepared_payload = json.loads(prepared["payload"])
        assert engine.ledger.artifacts.read_bytes(prepared_payload["artifact"]) == np.asarray(values, dtype="<f4").tobytes()
        mapping = engine.ledger.artifacts.read(prepared_payload["mapping_artifact"])
        assert [item["source_version"] for item in mapping] == list(ids)
        for name, reference in manifest["source_artifacts"].items():
            assert hashlib.sha256(engine.ledger.artifacts.read_bytes(reference)).hexdigest() == reference
            assert reference == manifest["upstream"]["verified_fragment_files"][name]
        observed.append(mode)

    def upstream(self: Any, values: Any, ids: Any, sizes: Any, **kwargs: Any):
        inspect(values, ids, "upstream")
        return original_upstream(self, values, ids, sizes, **kwargs)

    def baseline(values: Any, ids: Any, *args: Any, **kwargs: Any):
        inspect(values, ids, "baseline")
        return original_baseline(values, ids, *args, **kwargs)

    monkeypatch.setattr(core.UpstreamRunner, "run_batches", upstream)
    monkeypatch.setattr(core, "offline_baseline", baseline)
    result = execute(indexed)
    assert set(observed) == {"upstream", "baseline"}
    mapping = engine.ledger.artifacts.read(result["mapping_artifact"])
    raw = engine.ledger.artifacts.read_bytes(result["pooled_vectors_artifact"])
    assert len(raw) == len(mapping) * index["dimensions"] * 4
    assert hashlib.sha256(raw).hexdigest() == result["pooled_vectors_artifact"]
    for mode, artifact in result["mode_artifacts"].items():
        assert canonical(engine.ledger.artifacts.read(artifact)) == canonical(result["outputs"][mode])
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='aws_evaluation.mode.completed' "
            "AND json_extract(payload,'$.artifact')=?", (artifact,)).fetchone()[0] == 1


def test_failed_required_intent_prevents_all_clustering_work(indexed: Any, monkeypatch: Any) -> None:
    engine, _, _ = indexed
    called = []
    monkeypatch.setattr(core, "synthetic_probes", lambda runner: called.append("probe"))
    monkeypatch.setattr(evaluation, "aggregate", lambda *args: called.append("aggregate"))
    engine.ledger.fail_event = "aws_evaluation.intended"
    with pytest.raises(AuditError, match="Injected audit failure"):
        execute(indexed)
    assert called == []
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='aws_clustering_evaluation'").fetchone()[0] == 0


def test_partial_fit_stays_pending_and_separate_from_missing_vectors(indexed: Any, monkeypatch: Any) -> None:
    engine, index, _ = indexed
    source_ids = set(engine.ledger.get(index["versions"]["dataset"], "dataset")["source_versions"])
    original = core.UpstreamRunner.run_batches

    def interrupted(self: Any, values: Any, ids: Any, sizes: Any, **kwargs: Any):
        if not set(ids) <= source_ids:
            return original(self, values, ids, sizes, **kwargs)
        # Inject a software failure after processing all but one input; do not
        # fabricate a negative/noise assignment for the interrupted article.
        output = original(self, values[:-1], ids[:-1], [len(ids) - 1], **kwargs)
        output["batch_sizes"] = list(sizes)
        output["complete"] = False
        output["errors"] = [{"error_type": "SyntheticFitInterruption", "batch": 1}]
        output["coverage"].update({"input_occurrences": len(ids), "unique_input_ids": len(ids),
            "completed_input_occurrences": len(ids) - 1, "pending_input_occurrences": 1,
            "missing_pool_ids": [ids[-1]],
            "never_emitted_ids": sorted(set(output["coverage"]["never_emitted_ids"]) | {ids[-1]})})
        return output

    monkeypatch.setattr(core.UpstreamRunner, "run_batches", interrupted)
    result = execute(indexed)
    assert result["status"] == "partial"
    assert result["pending_articles"] == 1 and result["missing_articles"] == 2
    assert set(result["failed_modes"]) == {"upstream_one_batch", "upstream_streaming_500"}
    for mode in result["failed_modes"]:
        output, summary = result["outputs"][mode], result["summaries"][mode]
        pending = output["coverage"]["missing_pool_ids"][0]
        assert pending not in output["singletons"]
        assert not any(pending in group for group in output["partition"])
        assert summary["complete"] is False and summary["coverage"]["pending_input_occurrences"] == 1
        assert summary["errors"][0]["error_type"] == "SyntheticFitInterruption"
    for mode, output in result["outputs"].items():
        if mode.startswith("baseline_"):
            assert output["complete"] is True
            assert sum(map(len, output["partition"])) == result["processed_articles"]
    persisted = engine.ledger.get(result["id"], "aws_clustering_evaluation")
    assert persisted["pending_articles"] == 1 and persisted["summaries"] == result["summaries"]
    assert "Pending: 1." in result["presentation"]["markdown"]
    assert "| False |" in result["presentation"]["markdown"]


def test_pooling_keeps_groups_noise_and_missing_vectors_distinct() -> None:
    rows = [{"source_version": source, "id": "chunk-" + source, "passage_id": "passage-" + source}
        for source in ("a", "b", "noise", "cancel", "cancel")]
    angle = np.radians(1)
    matrix = np.array([[1, 0], [np.cos(angle), np.sin(angle)], [-1, 0], [0, 1], [0, -1]], dtype=np.float32)
    ids, pooled, missing, mapping = evaluation.aggregate(rows, matrix, ["a", "b", "noise", "no-vector", "cancel"])
    assert ids == ["a", "b", "noise"] and [item["source_version"] for item in mapping] == ids
    assert {item["source_version"]: item["reason"] for item in missing} == {
        "no-vector": "no_saved_vectors", "cancel": "zero_pooled_vector"}
    output = core.offline_baseline(pooled, ids)
    assert output["partition"] == [["a", "b"], ["noise"]]
    assert output["singletons"] == ["noise"]
    summary = evaluation._summary(output)
    assert summary["groups"] == 1 and summary["grouped_articles"] == 2 and summary["singletons"] == 1


def test_centroid_retention_is_byte_exact_and_covered_by_integrity_checks(indexed: Any) -> None:
    engine, _, _ = indexed
    result = execute(indexed)
    pools = []
    for mode, output in result["outputs"].items():
        if mode.startswith("upstream_"):
            pools.append(output["pool"])
            pools.extend(batch["pool"] for batch in output["batches"] if "pool" in batch)
    assert pools and all(pool for pool in pools)
    mapping = engine.ledger.artifacts.read(result["mapping_artifact"])
    inputs = np.frombuffer(engine.ledger.artifacts.read_bytes(result["pooled_vectors_artifact"]), dtype="<f4")
    inputs = inputs.reshape((len(mapping), -1))
    ids = [item["source_version"] for item in mapping]
    original = core.load_upstream().run_batches(inputs, ids, [len(ids)])
    packed = result["outputs"]["upstream_one_batch"]["pool"]
    for expected, actual in zip(original["pool"], packed, strict=True):
        ref = actual["centroid"]
        raw = engine.ledger.artifacts.read_bytes(ref["artifact"])
        reconstructed = np.frombuffer(raw, dtype=ref["dtype"]).reshape(ref["shape"])[ref["row"]]
        assert reconstructed.tobytes() == np.asarray(expected["centroid"], dtype="<f8").tobytes()
        assert actual["members"] == expected["members"]
        anchored = engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='preparation.artifact.saved' "
            "AND json_extract(payload,'$.artifact')=?", (ref["artifact"],)).fetchone()[0]
        assert anchored > 0
