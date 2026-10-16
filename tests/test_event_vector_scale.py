"""Real SQLite/Faiss with two constructed archives; no actual sources/models."""
from pathlib import Path
import hashlib
import importlib.metadata
import zipfile

import faiss
import numpy as np
import pytest

from newsresearch import event_vector_scale as scale
from newsresearch import embeddings
from newsresearch import event_vector_store as store
from newsresearch.common import AuditError, ResearchError, canonical, digest
from newsresearch.runtime import Research


def test_full_registry_versions_occurrences_fts_snapshot_resume_and_audit(tmp_path, monkeypatch):
    engine = Research(tmp_path / "research")
    root = tmp_path / "archives"
    root.mkdir()
    first = {"uri": "a", "title": "Artificial intelligence fixture", "body": "Artificial intelligence and ransomware at a café.", "url": "https://example.test/a"}
    second = {"uri": "b", "title": "Second", "body": "Another constructed ransomware record.", "url": "https://example.test/b"}
    records = [first, second, {"uri": "meta", "title": "Metadata only", "body": "\n\t"},
               {"uri": "pending", "body": "Pending constructed artificial intelligence text."},
               {"uri": "quarantine", "body": "Unretained fixture text", "secret": "synthetic-value"}]
    other = [first, {**first, "body": "Changed ransomware article body."}, {**second, "title": "Revised metadata"}]
    bundles = []
    for name, cohort, articles in (("legacy.zip", "legacy", records), ("cyber.zip", "cybercrime-nl", other)):
        path = root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("artikelen.jsonl", "".join(canonical({"article": value,
                **({"source_hash": digest(value)} if cohort == "cybercrime-nl" else {})}) + "\n" for value in articles))
        bundles.append({"path": name, "sha256": scale.sha256(path), "bytes": path.stat().st_size,
                        "kind": "article-bundle", "cohort": cohort})
    inventory = {"legacy_inventory": "constructed-inventory", "cyber_checksums": [], "bundles": bundles,
                 "expected_rows_by_cohort": {"legacy": 5, "cybercrime-nl": 3}}
    profile = engine.execute("version", {"kind": "embedding_profile", "key": "openai-embedding-candidates", "content": {
        **embeddings.PROFILE, "tiktoken_version": importlib.metadata.version("tiktoken")}}, objective="Register synthetic vector profile", actor="test")["id"]
    spec = {"embedding_profile": profile, "provider": "openai", "model": "text-embedding-3-large", "dimensions": 3072,
            "chunking": "unicode-window-1600-overlap-200-v1", "pooling": "constructed", "normalization": "l2"}
    metadata = {f"s-{row['uri']}": {"source_version": f"s-{row['uri']}", "body_sha256": hashlib.sha256(row["body"].encode()).hexdigest(),
        "published_at": "2026-01-01"} for row in (first, second)}
    inputs = {"spec": spec, "profile": {"usd_per_million_input_tokens": ".13", "price_checked_on": "synthetic-fixture"},
        "mapping": [{"source_version": key} for key in metadata], "pooled": np.eye(2, 3072, dtype=np.float32),
        "identities": {f"s-{row['uri']}": (row["uri"], hashlib.sha256(row["body"].encode()).hexdigest()) for row in (first, second)},
        "metadata": metadata, "groups": [{"group_id": "G-a", "members": ["s-a"]}, {"group_id": "G-b", "members": ["s-b"]}],
        "plan": {"manifest": "constructed-plan", "pooled_vectors_artifact": "constructed-vectors", "index": "constructed-passage-index"},
        "passage_index": {"vector_count": 2}}
    monkeypatch.setattr(scale, "_existing", lambda *args: inputs)
    monkeypatch.setattr(scale, "_inventory", lambda *args: inventory)
    class Tokenizer:
        def encode(self, text, **kwargs):
            return list(text.encode("utf-8"))
        def encode_ordinary(self, text):
            return self.encode(text)
    monkeypatch.setattr(scale, "offline_tokenizer", Tokenizer)
    monkeypatch.setattr(embeddings, "offline_tokenizer", Tokenizer)
    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", lambda *args: pytest.fail("No paid requests allowed"))
    monkeypatch.setattr(engine.gateway.provider, "complete", lambda *args: pytest.fail("No models allowed"))
    data = {"data_root": str(root), "plan": "constructed-plan", "group_result": "constructed-groups",
            "key": "constructed-store", "instruction": "Constructed offline registry test", "retention": "permitted", "batch_size": 2}
    def run(**extra):
        return engine.execute("scale_event_vector_store", {**data, **extra}, objective="Verify synthetic full catalog coverage and restore", actor="test:software")
    try:
        engine.ledger.fail_event = "event_store.build.intended"
        with pytest.raises(AuditError):
            run()
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_vector_store_result'").fetchone()[0] == 0
        engine.ledger.fail_event = None
        result = run()
        summary = result["catalog"]["summary"]
        assert result["catalog"]["counts"]["rows"] == summary["occurrences"] == 8
        assert summary["articles"] == 6 and summary["available_embeddings"] == 2
        assert summary["quarantined_articles"] == 1 and summary["missing_embeddings"] == 3
        assert summary["with_text"] == 4 and summary["without_text"] == 2
        assert result["catalog"]["pending"]["articles"] == 2
        assert result["article_index"]["count"] == result["group_index"]["count"] == 2
        assert all(index["benchmark"]["numerical_recall_at_8"] == 1. for index in (result["article_index"], result["group_index"]))
        catalog = store.Catalog(engine.ledger.artifacts.verified_path(result["catalog"]["artifact"]), spec, readonly=True)
        try:
            assert catalog.verify()["occurrences"] == 8 and len(catalog.search("cafe")) == 1
            assert catalog.db.execute("SELECT count(*) FROM articles WHERE provider_article_id='a'").fetchone()[0] == 2
            assert catalog.db.execute("SELECT count(*) FROM records WHERE article_id IN (SELECT article_id FROM articles WHERE provider_article_id='b')").fetchone()[0] == 2
            assert catalog.db.execute("SELECT count(*) FROM records WHERE body LIKE '%Unretained%'").fetchone()[0] == 0
        finally:
            catalog.close()
        assert result["queries"][0]["counts"]["article_versions"] == 3
        assert result["presentation"]["markdown"] == scale.render(result)
        assert len(result["presentation"]["results"]) == 3
        assert result["new_model_calls"] == result["actual_group_merges"] == result["network_calls"] == 0
        planned = engine.execute("plan_catalog_embeddings", {"snapshot":result["id"],"key":"fixture-full-plan",
            "instruction":"Prepare exact bounded offline gateway plans", "batch_size":2},
            objective="Verify actual gateway planning from synthetic catalog sources",actor="test:software")
        assert planned["articles"] == planned["selected_articles"] == 2 and len(planned["batches"]) == 1
        assert planned["input_tokens"] == result["catalog"]["pending"]["input_tokens"]
        assert planned["chunks"] == result["catalog"]["pending"]["chunks"]
        assert planned["model_calls"] == planned["paid_calls"] == planned["pending_articles"] == 0
        for batch in planned["batches"]:
            plan = engine.ledger.get(batch["plan"],"embedding_plan")
            assert plan["versions"]["embedding_profile"] == spec["embedding_profile"]
            assert plan["source_records"] <= 2
            assert plan["status"] == "planned; paid execution not authorized"
        assert engine.execute("plan_catalog_embeddings", {"snapshot":result["id"],"key":"fixture-full-plan",
            "instruction":"Prepare exact bounded offline gateway plans", "batch_size":2},
            objective="Reuse exact synthetic gateway plans",actor="test:software")["batches"] == planned["batches"]
        engine.ledger.verify()
        monkeypatch.setattr(scale, "_existing", lambda *args: pytest.fail("Snapshot rebuilt"))
        assert run()["id"] == result["id"]
        with pytest.raises(ResearchError, match="different inputs"):
            run(instruction="Changed method needs another snapshot")
        inventory["bundles"][0] = {**inventory["bundles"][0], "sha256": "changed"}
        with pytest.raises(ResearchError, match="Input files changed"):
            run()
    finally:
        engine.close()


def test_restore_rejects_index_canonical_vector_disagreement(tmp_path):
    spec = {"embedding_profile": "fixture", "provider": "fixture", "model": "fixture", "dimensions": 2,
            "chunking": "fixture", "pooling": "fixture", "normalization": "l2"}
    manifest = store.save_index(store.build_index(["a", "b"], [[1., 0.], [0., 1.]], spec), tmp_path / "snapshot")
    path = Path(manifest["files"]["index"]["path"])
    other = faiss.IndexFlatIP(2)
    other.add(np.array([[0., 1.], [1., 0.]], dtype=np.float32))
    path.write_bytes(faiss.serialize_index(other).tobytes())
    manifest["files"]["index"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="canonical"):
        store.load_index(manifest, spec)
