"""Focused source-free catalog/index persistence and namespace checks."""
import hashlib
from pathlib import Path

import numpy as np
import pytest

from newsresearch.event_vector_store import Catalog, build_index, load_index, namespace, query, save_index

SPEC = {"embedding_profile": "constructed-profile", "provider": "constructed", "model": "unit-test",
        "dimensions": 2, "chunking": "constructed", "pooling": "mean-unit", "normalization": "l2"}


def test_catalog_dedup_occurrences_missingness_fts_and_restore(tmp_path: Path):
    path = tmp_path / "catalog.sqlite3"
    catalog = Catalog(path, SPEC)
    body = "Constructed cybercrime report."
    article = {"provider": "constructed", "provider_article_id": "1", "body": body,
               "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "title": "Fixture", "retention": "permitted"}
    first = catalog.append_article(article, {"bundle_sha256": "A", "row_sha256": "R", "line": 1, "cohort": "archive"})
    other = catalog.append_article(article, {"bundle_sha256": "B", "row_sha256": "R", "line": 3, "cohort": "cyber"})
    assert first["article_id"] == other["article_id"] and not other["new_article"]
    revised = catalog.append_article({**article, "title": "Revised metadata"}, {"line": 4})
    assert revised["article_id"] == first["article_id"] and revised["record_id"] != first["record_id"]
    catalog.append_article({"provider": "constructed", "provider_article_id": "2", "body_sha256": "quarantine-hash",
                            "quarantined": True, "retention": "metadata_only"}, {"line": 5})
    assert catalog.summary()["missing_embeddings"] == 1
    catalog.attach_vector(first["article_id"], {"namespace": namespace(SPEC), "level": "article", "source_version": "old-source",
                                                "plan": "old-plan", "vector_row": 3, "index_artifact": "old-index"})
    assert catalog.summary()["available_embeddings"] == 1 and len(catalog.search("cybercrime")) == 2
    catalog.close()
    restored = Catalog(path, SPEC, readonly=True)
    assert restored.verify()["occurrences"] == 4
    assert restored.summary()["missing_embeddings"] == 0
    restored.close()
    with pytest.raises(ValueError, match="namespace"):
        Catalog(path, {**SPEC, "embedding_profile": "different"}, readonly=True)


def test_flat_snapshot_exact_reranking_restore_and_tamper(tmp_path: Path):
    values = np.array([[1., 0.], [.8, .6], [0., 1.]], dtype=np.float32)
    handle = build_index(["z", "b", "a"], values, SPEC)
    manifest = save_index(handle, tmp_path / "snapshot")
    restored = load_index(manifest, SPEC)
    result = query(restored, [[1., 0.]], top_k=2, candidate_limit=3)
    assert [row["id"] for row in result["results"][0]] == ["z", "b"]
    assert result["results"][0][1]["score"] == pytest.approx(.8)
    assert not result["approximate_candidates"]
    with pytest.raises(ValueError, match="namespace"):
        load_index(manifest, {**SPEC, "pooling": "other"})
    vector_path = Path(manifest["files"]["vectors"]["path"])
    vector_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash"):
        load_index(manifest, SPEC)


def test_hnsw_level_bounds_and_no_fake_missing_vectors(tmp_path: Path):
    handle = build_index(["a", "b"], [[1., 0.], [0., 1.]], SPEC, kind="hnsw", level="group")
    restored = load_index(save_index(handle, tmp_path / "group"), SPEC)
    result = query(restored, [[1., 0.]], top_k=1, candidate_limit=2, exclude_ids=["a"])
    assert result["results"][0][0]["id"] == "b" and result["approximate_candidates"]
    assert result["level"] == "group"
    for invalid in ([[0., 0.]], [[float("nan"), 0.]], [[2., 0.]]):
        with pytest.raises(ValueError):
            build_index(["missing"], invalid, SPEC)
    with pytest.raises(ValueError, match="bounded"):
        query(restored, [[1., 0.]], candidate_limit=513)
