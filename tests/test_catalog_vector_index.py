"""One source-free integration: immutable expansion, exact pooling and sharded merge.

The completed gateway/index records are constructed fixtures. This test exercises
the offline bridge, not API service access or original embedding execution.
"""
import hashlib

import numpy as np
import pytest

from newsresearch import catalog_vector_index as bridge
from newsresearch import event_vector_store as store
from newsresearch import retrieval
from newsresearch.common import Context, ResearchError
from newsresearch.event_vector_scale import _persist, _save
from newsresearch.runtime import Research


def test_complete_catalog_expansion_preserves_parent_and_exact_pooling(tmp_path, monkeypatch):
    engine = Research(tmp_path / "research")
    state = {}
    calls = []
    monkeypatch.setattr(bridge, "SHARD_ROWS", 2)

    def setup(session, context, data):
        def version(kind, content):
            return engine._version(session, context, {"kind": kind, "key": "fixture-" + kind, "content": content})["id"]
        versions = {"protocol": version("protocol", {"method": "source-free-fixture"}),
            "selection": version("selection", {"rules": {"synthetic": True}}),
            "question": version("question", {"text": "Constructed offline representation test"}),
            "profile": version("profile", {"mode": "exploratory"}),
            "dossier_definition": version("dossier_definition", {"unit": "Constructed event"}),
            "embedding_profile": version("embedding_profile", {"provider": "synthetic", "model": "constructed", "dimensions": 3})}
        spec = {"embedding_profile": versions["embedding_profile"], "provider": "synthetic", "model": "constructed", "dimensions": 3,
            "chunking": "unicode-window-1600-overlap-200-v1", "pooling": "L2-normalized float64 sum of every saved unit passage-window vector; float32 output", "normalization": "l2"}
        path = engine.ledger.root / "fixture-catalog.sqlite3"
        catalog = store.Catalog(path, spec)
        articles = []
        for name, body, quarantine in (("old", "Old constructed source.", False),
                ("new-a", "First new paragraph.\n\nSecond new paragraph.", False),
                ("new-b", "Another new constructed source.", False), ("blank", "", False), ("quarantine", None, True)):
            article = {"provider": "eventregistry", "provider_article_id": name,
                "body_sha256": hashlib.sha256((body or "").encode()).hexdigest(),
                "retention": "metadata_only" if quarantine else "permitted", "quarantined": quarantine}
            if body is not None:
                article.update(body=body, title=name, text_quality={"nonblank_body": bool(body.strip())})
            record = catalog.append_article(article, {"fixture": name})
            articles.append({**article, **record})
        catalog.db.execute("CREATE TABLE pending_embeddings(article_id TEXT PRIMARY KEY REFERENCES articles,passages INTEGER,chunks INTEGER,input_tokens INTEGER)")
        catalog.db.execute("CREATE TABLE group_members(group_id TEXT,source_version TEXT,article_id TEXT REFERENCES articles,PRIMARY KEY(group_id,source_version))")
        catalog.db.execute("INSERT INTO group_members VALUES (?,?,?)", ("fixture-group", "fixture-old-source", articles[0]["article_id"]))
        old = store.build_index([articles[0]["article_id"]], np.array([[1., 0., 0.]], dtype=np.float32), spec)
        saved_old = _persist(engine, session, old, engine.ledger.root / "fixture-old-article-index")
        del saved_old["restored"]
        saved_old["count"] = 1
        group = store.build_index(["fixture-group"], np.array([[1., 0., 0.]], dtype=np.float32), spec, level="group")
        saved_group = _persist(engine, session, group, engine.ledger.root / "fixture-group-index")
        del saved_group["restored"]
        saved_group["count"] = 1
        old_manifest = engine.ledger.artifacts.read(saved_old["manifest"])
        catalog.attach_vector(articles[0]["article_id"], {"namespace": catalog.namespace, "level": "article", "source_version": "fixture-old-source",
            "plan": "fixture-old-plan", "vector_row": 0, "index_artifact": old_manifest["files"]["vectors"]["sha256"]})
        for article, count in zip(articles[1:3], (2, 1), strict=True):
            catalog.db.execute("INSERT INTO pending_embeddings VALUES (?,?,?,?)", (article["article_id"], count, count, count))
        catalog.commit()
        summary = catalog.verify()
        summary.update(with_text=3, without_text=2)
        catalog.close()
        catalog_ref = _save(engine, session, path, "Constructed source-free catalog", file=True)
        state["parent_hash"] = bridge.sha256(path)
        memberships = _save(engine, session, [{"group_id": "fixture-group", "members": ["fixture-old-source"]}], "Constructed memberships")
        snapshot = {"versions": versions, "spec": spec, "catalog": {"artifact": catalog_ref, "summary": summary,
                "pending": {"articles": 2, "chunks": 3, "input_tokens": 3}, "counts": {"rows": 5}},
            "article_index": saved_old, "group_index": saved_group, "group_memberships": memberships,
            "failed_rows": 0, "pending_rows": 0, "original_passage_index": "fixture-old-passage-index", "passage_vectors": 1,
            "inventory": {"fixture": True}, "inventory_artifact": _save(engine, session, {"fixture": True}, "Constructed inventory"),
            "inventory_fingerprint": "source-free-fixture"}
        snapshot_id = engine.ledger.record(session, "event_vector_store_result", "fixture-parent", snapshot)
        imported = engine._ingest(session, Context("Construct source-free data", "test", versions), {"key": "fixture-new-sources",
            "articles": [{"source_key": "eventregistry:" + article["provider_article_id"], "body": article["body"], "retention": "permitted", "synthetic": True,
                "catalog_provenance": {"snapshot": snapshot_id, "article_id": article["article_id"], "record_id": article["record_id"], "body_sha256": article["body_sha256"]}}
                for article in articles[1:3]], "retrieval": {"source": "Constructed fixture", "retrieved_at": "2026-01-01T00:00:00+00:00", "parameters": {"synthetic": True}}})
        plan_versions = {**versions, "dataset": imported["id"]}
        retrieval_profile = version("retrieval_profile", retrieval.METHOD)
        index_versions = {**plan_versions, "retrieval_profile": retrieval_profile}
        source_rows = []
        for source_id in imported["sources"]:
            for passage in engine.ledger.db.execute("SELECT id FROM passages WHERE source_id=? ORDER BY start", (source_id,)):
                source_rows.append({"id": "fixture-chunk-" + passage[0], "source_version": source_id, "passage_id": passage[0]})
        raw_path = engine.ledger.root / "fixture-new-passages.f32"
        values = np.array([[0., 1., 0.], [0., 0., 1.], [1., 0., 0.]], dtype="<f4")
        raw_path.write_bytes(values.tobytes())
        vector_index = {"versions": index_versions, "profile": retrieval.METHOD, "rows_artifact": _save(engine, session, source_rows, "Constructed passage mapping"),
            "vectors_artifact": _save(engine, session, raw_path, "Constructed normalized passages", file=True), "vector_count": 3, "dimensions": 3}
        index_id = engine.ledger.record(session, "vector_index", "fixture-passage-index", vector_index)
        plan_id = engine.ledger.record(session, "embedding_plan", "fixture-plan", {"versions": plan_versions,
            "profile": {"provider": "synthetic", "model": "constructed", "dimensions": 3}, "expected_chunks": 3})
        run_id = engine.ledger.record(session, "embedding_run", "fixture-run", {"versions": plan_versions, "plan": plan_id})
        mapping = [{"source_version": source_id, "article_id": article["article_id"], "record_id": article["record_id"], "chunks": count}
            for source_id, article, count in zip(imported["sources"], articles[1:3], (2, 1), strict=True)]
        batch = {"snapshot": snapshot_id, "plan": plan_id, "dataset": imported["id"], "plan_versions": plan_versions,
            "mapping_artifact": _save(engine, session, mapping, "Constructed catalog/core map"), "articles": 2, "chunks": 3}
        batch_id = engine.ledger.record(session, "catalog_embedding_batch", "fixture-batch", batch)
        batch["id"] = batch_id
        master = {"versions": versions, "snapshot": snapshot_id, "articles": 2, "chunks": 3, "requests": 1, "batches": [batch], "failed_articles": 0, "pending_articles": 0}
        master_id = engine.ledger.record(session, "catalog_embedding_plan_result", "fixture-master", master)
        checkpoint = {"versions": versions, "status": "complete", "master": master_id, "completed_articles": 2, "expected_articles": 2,
            "completed_chunks": 3, "expected_chunks": 3, "request_totals": {"valid": 1, "failed": 0, "unknown": 0, "pending": 0},
            "runs": [{"batch": batch_id, "plan": plan_id, "run": run_id, "articles": 2, "completed_chunks": 3, "expected_chunks": 3, "missing_requests": 0}]}
        execution_id = engine.ledger.record(session, "embedding_checkpoint_result", "fixture-execution", checkpoint)
        state.update(execution=execution_id, snapshot=snapshot, snapshot_id=snapshot_id, index=index_id, plan=plan_id, run=run_id,
            new_a=articles[1]["article_id"], new_b=articles[2]["article_id"], old=articles[0]["article_id"])
        return {"fixture_ready": True}

    monkeypatch.setattr(engine, "_status", setup)
    engine.execute("status", objective="Set up constructed source-free bridge fixture", actor="test:software")
    def build(engine_, session, context, data):
        assert data == {"plan": state["plan"], "embedding_run": state["run"]}
        calls.append(data)
        return {"id": state["index"]}
    monkeypatch.setattr(retrieval, "build", build)
    monkeypatch.setattr(engine.gateway.provider, "complete", lambda *args: pytest.fail("No models allowed"))
    monkeypatch.setattr(engine, "_status", lambda session, context, data: bridge.execute(engine, session, context, data))
    arguments = {"execution": state["execution"], "key": "fixture-expanded", "instruction": "Constructed offline expansion only"}
    try:
        result = engine.execute("status", arguments, objective="Verify source-free immutable expansion", actor="test:software")
        assert len(calls) == 1
        assert result["catalog"]["summary"]["available_embeddings"] == 3
        assert result["catalog"]["summary"]["articles"] == 5
        assert result["catalog"]["summary"]["without_text"] == 2
        assert result["catalog"]["pending"]["articles"] == 0
        assert result["article_index"]["shards"] == 2
        assert result["group_index"] == state["snapshot"]["group_index"]
        assert result["group_memberships"] == state["snapshot"]["group_memberships"]
        assert result["new_model_calls"] == result["network_calls"] == result["actual_group_merges"] == 0
        assert result["new_sources_ungrouped"] == 2
        assert bridge.sha256(engine.ledger.artifacts.verified_path(state["snapshot"]["catalog"]["artifact"])) == state["parent_hash"]
        assert result["presentation"]["markdown"] == bridge.render(result)
        manifest = engine.ledger.artifacts.read(result["article_index"]["manifest"])
        actual = {}
        for shard in manifest["shards"]:
            handle = store.load_index(engine.ledger.artifacts.read(shard["manifest"]), result["spec"])
            actual.update(zip(handle["ids"], handle["vectors"], strict=True))
        np.testing.assert_array_equal(actual[state["old"]], [1., 0., 0.])
        np.testing.assert_array_equal(actual[state["new_b"]], [1., 0., 0.])
        np.testing.assert_array_equal(actual[state["new_a"]], np.array([0., 1./np.sqrt(2), 1./np.sqrt(2)], dtype=np.float32))
        monkeypatch.setattr(engine, "_status", lambda session, context, data: bridge.query_shards(engine, session,
            result["article_index"]["manifest"], np.array([[0., 1., 1.]], dtype=np.float32) / np.sqrt(2), top_k=2))
        neighbors = engine.execute("status", objective="Verify constructed all-shard neighbor merge", actor="test:software")
        assert neighbors["results"][0][0]["id"] == state["new_a"]
        assert neighbors["scanned_vectors"] == 3
        monkeypatch.setattr(engine, "_status", lambda session, context, data: bridge.execute(engine, session, context, data))
        repeated = engine.execute("status", arguments, objective="Verify constructed version-bound reuse", actor="test:software")
        assert repeated["id"] == result["id"] and len(calls) == 1
        with pytest.raises(ResearchError):
            engine.execute("status", {**arguments, "instruction": "Changed instruction"}, objective="Reject changed snapshot binding", actor="test:software")
    finally:
        engine.close()
