"""SQLite catalog and immutable Faiss snapshots for audited research adapters.

This module does not ingest archives, call models or invent missing vectors.
Real operations must run inside Research.execute and protected staging storage.
Catalog writes are staging work; the caller anchors complete sealed snapshots.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

import faiss
import numpy as np

from .common import canonical, digest, require_no_credentials

Json = dict[str, Any]
SCHEMA = 1


def namespace(spec: Json) -> str:
    required = ("embedding_profile", "provider", "model", "chunking", "pooling", "normalization")
    if (any(not isinstance(spec.get(key), str) or not spec[key].strip() for key in required)
            or type(spec.get("dimensions")) is not int or not 1 <= spec["dimensions"] <= 8192
            or spec["normalization"] != "l2"):
        raise ValueError("exact model/profile/chunking/pooling and l2 dimension namespace required")
    require_no_credentials(spec)
    return digest({"schema": SCHEMA, "spec": spec})


def article_identity(article: Json) -> str:
    keys = ("provider", "provider_article_id", "body_sha256")
    if any(not isinstance(article.get(key), str) or not article[key] for key in keys):
        raise ValueError("provider identity and exact body hash are required")
    return digest({key: article[key] for key in keys})


class Catalog:
    def __init__(self, path: Path, spec: Json, *, readonly: bool = False):
        self.path, self.spec, self.namespace = Path(path), dict(spec), namespace(spec)
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        if not readonly:
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS articles(article_id TEXT PRIMARY KEY,provider TEXT NOT NULL,
                  provider_article_id TEXT NOT NULL,body_sha256 TEXT NOT NULL,quarantined INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS provider_body ON articles(provider,provider_article_id,body_sha256);
                CREATE TABLE IF NOT EXISTS records(record_id TEXT PRIMARY KEY,article_id TEXT NOT NULL REFERENCES articles,
                  title TEXT,body TEXT,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS occurrences(occurrence_id TEXT PRIMARY KEY,article_id TEXT NOT NULL REFERENCES articles,
                  record_id TEXT NOT NULL REFERENCES records,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS vector_refs(ref_id TEXT PRIMARY KEY,article_id TEXT NOT NULL REFERENCES articles,payload TEXT NOT NULL);
                CREATE VIRTUAL TABLE IF NOT EXISTS record_search USING fts5(record_id UNINDEXED,title,body);
            """)
            self.db.execute("INSERT OR IGNORE INTO meta VALUES ('binding',?)", (canonical({"schema": SCHEMA, "namespace": self.namespace, "spec": spec}),))
            self.db.commit()
        binding = self.db.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
        if binding is None or json.loads(binding[0]) != {"schema": SCHEMA, "namespace": self.namespace, "spec": spec}:
            self.db.close()
            raise ValueError("catalog namespace/schema mismatch")

    def append_article(self, article: Json, occurrence: Json) -> Json:
        require_no_credentials(article)
        require_no_credentials(occurrence)
        article_id = article_identity(article)
        quarantined = article.get("quarantined", False)
        retention = article.get("retention", "permitted")
        if type(quarantined) is not bool or retention not in {"permitted", "metadata_only"}:
            raise ValueError("explicit permitted/metadata_only retention and quarantine status required")
        if (quarantined or retention == "metadata_only") and (article.get("body") or article.get("raw_record")):
            raise ValueError("quarantined/metadata-only rows cannot retain body or raw record")
        body = article.get("body")
        if body is not None and (not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != article["body_sha256"]):
            raise ValueError("retained body differs from exact body hash")
        record_id = digest(article)
        occurrence_id = digest({"article_id": article_id, "record_id": record_id, "occurrence": occurrence})
        new_article = self.db.execute("INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?)", (
            article_id, article["provider"], article["provider_article_id"], article["body_sha256"], int(quarantined))).rowcount == 1
        new_record = self.db.execute("INSERT OR IGNORE INTO records VALUES (?,?,?,?,?)", (
            record_id, article_id, article.get("title"), body, canonical(article))).rowcount == 1
        if new_record:
            self.db.execute("INSERT INTO record_search VALUES (?,?,?)", (record_id, article.get("title"), body))
        new_occurrence = self.db.execute("INSERT OR IGNORE INTO occurrences VALUES (?,?,?,?)", (
            occurrence_id, article_id, record_id, canonical(occurrence))).rowcount == 1
        return {"article_id": article_id, "record_id": record_id, "occurrence_id": occurrence_id,
                "new_article": new_article, "new_record": new_record, "new_occurrence": new_occurrence}

    def attach_vector(self, article_id: str, reference: Json) -> str:
        require_no_credentials(reference)
        if (reference.get("namespace") != self.namespace or reference.get("level") != "article"
                or type(reference.get("vector_row")) is not int or reference["vector_row"] < 0
                or any(not isinstance(reference.get(key), str) or not reference[key]
                       for key in ("source_version", "plan", "index_artifact"))):
            raise ValueError("vector provenance requires exact namespace, source, plan, index and row")
        article = self.db.execute("SELECT quarantined FROM articles WHERE article_id=?", (article_id,)).fetchone()
        if article is None or article[0]:
            raise ValueError("unknown/quarantined article cannot acquire an embedding reference")
        identifier = digest({"article_id": article_id, "reference": reference})
        self.db.execute("INSERT OR IGNORE INTO vector_refs VALUES (?,?,?)", (identifier, article_id, canonical(reference)))
        return identifier

    def find(self, provider: str, provider_article_id: str, body_sha256: str) -> str | None:
        row = self.db.execute("SELECT article_id FROM articles WHERE provider=? AND provider_article_id=? AND body_sha256=?",
                              (provider, provider_article_id, body_sha256)).fetchone()
        return row[0] if row else None

    def summary(self) -> Json:
        counts = {name: self.db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                  for name in ("articles", "records", "occurrences", "vector_refs")}
        available = self.db.execute("SELECT count(DISTINCT article_id) FROM vector_refs").fetchone()[0]
        quarantine = self.db.execute("SELECT count(*) FROM articles WHERE quarantined=1").fetchone()[0]
        return {**counts, "namespace": self.namespace, "available_embeddings": available,
                "missing_embeddings": counts["articles"] - available - quarantine, "quarantined_articles": quarantine}

    def search(self, query: str, limit: int = 20) -> list[Json]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("lexical query limit must be within1..100")
        return [dict(row) for row in self.db.execute("SELECT record_id,bm25(record_search) AS score FROM record_search WHERE record_search MATCH ? ORDER BY score,record_id LIMIT ?", (query, limit))]

    def commit(self) -> None:
        self.db.commit()

    def verify(self) -> Json:
        if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or self.db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("catalog SQLite integrity failed")
        for row in self.db.execute("SELECT * FROM articles"):
            if (article_identity(dict(row)) != row["article_id"] or row["quarantined"] not in (0, 1)):
                raise ValueError("catalog article identity differs")
        for row in self.db.execute("SELECT record_id,article_id,payload FROM records"):
            payload = json.loads(row["payload"])
            body = payload.get("body")
            if body is not None and hashlib.sha256(body.encode()).hexdigest() != payload["body_sha256"]:
                raise ValueError("catalog body hash differs")
            if digest(payload) != row["record_id"] or article_identity(payload) != row["article_id"]:
                raise ValueError("catalog record content differs")
        for row in self.db.execute("SELECT occurrence_id,article_id,record_id,payload FROM occurrences"):
            if digest({"article_id": row["article_id"], "record_id": row["record_id"], "occurrence": json.loads(row["payload"])}) != row["occurrence_id"]:
                raise ValueError("catalog occurrence content differs")
        if self.db.execute("SELECT 1 FROM occurrences o JOIN records r USING(record_id) WHERE o.article_id!=r.article_id LIMIT 1").fetchone():
            raise ValueError("catalog occurrence points to another article record")
        for row in self.db.execute("SELECT ref_id,article_id,payload FROM vector_refs"):
            reference = json.loads(row["payload"])
            if reference.get("namespace") != self.namespace or digest({"article_id": row["article_id"], "reference": reference}) != row["ref_id"]:
                raise ValueError("catalog vector reference content differs")
        if self.db.execute("SELECT count(*) FROM record_search").fetchone()[0] != self.db.execute("SELECT count(*) FROM records").fetchone()[0]:
            raise ValueError("catalog FTS coverage differs")
        if self.db.execute("SELECT 1 FROM record_search f LEFT JOIN records r USING(record_id) WHERE r.record_id IS NULL OR coalesce(r.title,'')!=coalesce(f.title,'') OR coalesce(r.body,'')!=coalesce(f.body,'') LIMIT 1").fetchone():
            raise ValueError("catalog FTS content differs")
        if self.db.execute("SELECT record_id FROM records EXCEPT SELECT record_id FROM record_search LIMIT 1").fetchone():
            raise ValueError("catalog FTS record coverage differs")
        return {"status": "verified", **self.summary()}

    def close(self) -> None:
        if not self.readonly:
            self.db.commit()
        self.db.close()


def _matrix(values: Any, dimensions: int) -> Any:
    if np.asarray(values).dtype.kind not in "fi":
        raise ValueError("numeric vectors required; booleans are not embeddings")
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim != 2 or matrix.shape[1] != dimensions or not np.isfinite(matrix).all():
        raise ValueError("index vectors must be finite rows in the exact namespace dimension")
    norms = np.linalg.norm(matrix.astype(np.float64), axis=1)
    if np.any(np.abs(norms - 1.) > 1e-4):
        raise ValueError("index vectors must have unit norm; missing/zero rows are not embeddings")
    return np.ascontiguousarray(matrix, dtype="<f4")


def build_index(ids: list[str], vectors: Any, spec: Json, *, kind: str = "flat", level: str = "article") -> Json:
    identifier = namespace(spec)
    matrix = _matrix(vectors, spec["dimensions"])
    if (len(ids) != len(matrix) or len(set(ids)) != len(ids)
            or any(not isinstance(value, str) or not value for value in ids)
            or kind not in {"flat", "hnsw"} or level not in {"article", "group"}):
        raise ValueError("index requires unique mapped IDs, flat/hnsw kind and article/group level")
    order = sorted(range(len(ids)), key=lambda n: ids[n])
    matrix = matrix[order]
    previous_threads = faiss.omp_get_max_threads()
    try:
        faiss.omp_set_num_threads(4)
        index: Any
        if kind == "flat":
            index = faiss.IndexFlatIP(spec["dimensions"])
        else:
            index = faiss.IndexHNSWFlat(spec["dimensions"], 32, faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = 200
            index.hnsw.efSearch = 64
        index.add(matrix)
    finally:
        faiss.omp_set_num_threads(previous_threads)
    return {"namespace": identifier, "spec": dict(spec), "kind": kind, "level": level,
            "ids": [ids[n] for n in order], "vectors": matrix, "index": index}


def _write(path: Path, value: bytes) -> None:
    with path.open("xb") as stream:
        if os.name != "nt":
            path.chmod(0o600)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())


def _hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_index(handle: Json, directory: Path) -> Json:
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = {"index": directory / "index.faiss", "vectors": directory / "vectors.f32", "mapping": directory / "mapping.json"}
    _write(paths["index"], faiss.serialize_index(handle["index"]).tobytes())
    _write(paths["vectors"], handle["vectors"].astype("<f4", copy=False).tobytes())
    _write(paths["mapping"], canonical(handle["ids"]).encode())
    manifest = {key: handle[key] for key in ("namespace", "spec", "kind", "level")}
    manifest.update(schema=SCHEMA, count=len(handle["ids"]), dimensions=handle["spec"]["dimensions"],
                    files={key: {"path": str(path), "sha256": _hash(path)} for key, path in paths.items()},
                    canonical_vectors="little-endian float32; float64 cosine reranking")
    _write(directory / "manifest.json", canonical(manifest).encode())
    return manifest


def load_index(manifest: Json, spec: Json) -> Json:
    if manifest.get("schema") != SCHEMA or manifest.get("namespace") != namespace(spec) or manifest.get("spec") != spec:
        raise ValueError("persisted index namespace/schema mismatch")
    if (manifest.get("kind") not in {"flat", "hnsw"} or manifest.get("level") not in {"article", "group"}
            or type(manifest.get("count")) is not int or manifest["count"] < 0
            or manifest.get("dimensions") != spec["dimensions"]):
        raise ValueError("persisted index kind, level or dimensions differ")
    paths = {key: Path(value["path"]) for key, value in manifest["files"].items()}
    if set(paths) != {"index", "vectors", "mapping"} or any(_hash(paths[key]) != value["sha256"] for key, value in manifest["files"].items()):
        raise ValueError("persisted index component hash differs")
    ids = json.loads(paths["mapping"].read_text(encoding="utf-8"))
    vectors = np.fromfile(paths["vectors"], dtype="<f4").reshape(-1, spec["dimensions"])
    index = faiss.read_index(str(paths["index"]))
    if (not isinstance(ids, list) or any(not isinstance(value, str) or not value for value in ids)
            or manifest["count"] != len(ids) or len(set(ids)) != len(ids) or ids != sorted(ids)
            or index.ntotal != len(ids) or index.d != spec["dimensions"] or len(vectors) != len(ids)
            or index.metric_type != faiss.METRIC_INNER_PRODUCT):
        raise ValueError("persisted index mapping/count/dimensions differ")
    _matrix(vectors, spec["dimensions"])
    expected_type = faiss.IndexFlatIP if manifest["kind"] == "flat" else faiss.IndexHNSWFlat
    if not isinstance(index, expected_type) or (len(ids) and not np.array_equal(index.reconstruct_n(0, len(ids)), vectors)):
        raise ValueError("persisted Faiss vectors differ from canonical vector rows or declared kind")
    return {**{key: manifest[key] for key in ("namespace", "spec", "kind", "level")},
            "ids": ids, "vectors": vectors, "index": index}


def query(handle: Json, queries: Any, *, top_k: int = 8, candidate_limit: int = 64,
          exclude_ids: list[str | None] | None = None) -> Json:
    values = _matrix(queries, handle["spec"]["dimensions"])
    if (len(values) > 512 or type(top_k) is not int or type(candidate_limit) is not int
            or not 1 <= top_k <= 100 or not top_k <= candidate_limit <= 512
            or (exclude_ids is not None and len(exclude_ids) != len(values))):
        raise ValueError("bounded query requires at most512 rows, topK<=100 and candidate_limit<=512")
    previous_threads = faiss.omp_get_max_threads()
    try:
        faiss.omp_set_num_threads(4)
        neighbors = handle["index"].search(values, min(len(handle["ids"]), candidate_limit))[1] if handle["ids"] else np.empty((len(values), 0), dtype=np.int64)
    finally:
        faiss.omp_set_num_threads(previous_threads)
    results = []
    for n, candidates in enumerate(neighbors):
        q = values[n].astype(np.float64)
        q /= np.linalg.norm(q)
        ranked = []
        for position in candidates:
            if position < 0 or (exclude_ids is not None and handle["ids"][int(position)] == exclude_ids[n]):
                continue
            vector = handle["vectors"][int(position)].astype(np.float64)
            score = float(np.clip(np.dot(q, vector) / np.linalg.norm(vector), -1., 1.))
            ranked.append({"id": handle["ids"][int(position)], "score": score})
        ranked.sort(key=lambda row: (-row["score"], row["id"]))
        results.append([{**row, "rank": rank} for rank, row in enumerate(ranked[:top_k], 1)])
    return {"results": results, "namespace": handle["namespace"], "level": handle["level"],
            "candidate_limit": candidate_limit, "approximate_candidates": handle["kind"] == "hnsw",
            "truncated_candidate_pool": len(handle["ids"]) > candidate_limit,
            "reranking": "canonical saved float32 rows; normalized float64 dot; stable IDs break ties"}
