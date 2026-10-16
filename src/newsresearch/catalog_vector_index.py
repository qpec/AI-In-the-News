"""Offline immutable full-catalog vector expansion after reconciled paid execution.

Only ``Research.execute`` callers may use this adapter with actual research data.
Article snapshots are sharded to bound construction/restoration memory. Sharding
does not establish fast query latency or semantic event-grouping accuracy.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import TYPE_CHECKING, Any

import numpy as np

from . import event_vector_store as store
from . import retrieval
from .aws_clustering_evaluation import aggregate, vectors
from .common import AuditError, Context, Json, ResearchError, canonical, require_active
from .event_vector_scale import _persist, _save
from .legacy import sha256

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "full-catalog-complete-embedding-index-v1"
CODE = ("catalog_vector_index.py", "event_vector_store.py", "event_vector_scale.py",
        "retrieval.py", "embeddings.py", "aws_clustering_evaluation.py")
SHARD_ROWS = 2048


def _files(engine: Research, manifest_ref: str, spec: Json, level: str) -> tuple[Json, dict[str, Path]]:
    """Hash all components; exact old bytes reuse their prior full validation."""
    manifest = engine.ledger.artifacts.read(manifest_ref)
    if (manifest.get("schema") != store.SCHEMA or manifest.get("namespace") != store.namespace(spec)
            or manifest.get("spec") != spec or manifest.get("level") != level
            or manifest.get("kind") not in {"flat", "hnsw"}
            or manifest.get("dimensions") != spec["dimensions"]
            or type(manifest.get("count")) is not int or manifest["count"] < 0
            or set(manifest.get("files", {})) != {"index", "vectors", "mapping"}):
        raise AuditError("Saved vector manifest differs from its exact namespace")
    paths = {}
    for name, item in manifest["files"].items():
        path = engine.ledger.artifacts.verified_path(item["sha256"])
        if Path(item["path"]).resolve() != path.resolve():
            raise AuditError("Vector manifest path differs from its protected artifact")
        paths[name] = path
    if paths["vectors"].stat().st_size != manifest["count"] * spec["dimensions"] * 4:
        raise AuditError("Saved vector matrix has a different shape")
    return manifest, paths


def _inputs(engine: Research, session: str, execution: str) -> tuple[Json, Json, Json, list[Json]]:
    checkpoint = engine.ledger.get(execution, "embedding_checkpoint_result")
    master = engine.ledger.get(checkpoint["master"], "catalog_embedding_plan_result")
    snapshot = engine.ledger.get(master["snapshot"], "event_vector_store_result")
    if (checkpoint["status"] != "complete" or checkpoint["versions"] != master["versions"]
            or checkpoint["completed_articles"] != master["articles"]
            or checkpoint["expected_articles"] != master["articles"]
            or checkpoint["completed_chunks"] != master["chunks"]
            or checkpoint["expected_chunks"] != master["chunks"]
            or any(checkpoint["request_totals"].get(key, 0) for key in ("failed", "unknown", "pending"))
            or checkpoint["request_totals"].get("valid") != master["requests"]
            or master.get("failed_articles") or master.get("pending_articles")
            or snapshot.get("failed_rows") or snapshot.get("pending_rows")
            or snapshot["catalog"]["summary"].get("status") != "verified"):
        raise ResearchError("Full vector expansion requires the complete exact embedding checkpoint")
    runs = checkpoint["runs"]
    if (len(runs) != len(master["batches"]) or len({row["plan"] for row in runs}) != len(runs)
            or {row["plan"] for row in runs} != {row["plan"] for row in master["batches"]}):
        raise AuditError("Checkpoint runs do not cover the exact master plan frame")
    by_plan = {row["plan"]: row for row in runs}
    bound = []
    for batch in master["batches"]:
        row = by_plan[batch["plan"]]
        plan = engine.ledger.get(batch["plan"], "embedding_plan")
        if (row["batch"] != batch["id"] or row["articles"] != batch["articles"]
                or row["completed_chunks"] != batch["chunks"] or row["expected_chunks"] != batch["chunks"]
                or row["missing_requests"] or batch["snapshot"] != master["snapshot"]
                or batch["plan_versions"] != plan["versions"] or plan["expected_chunks"] != batch["chunks"]
                or batch["dataset"] != plan["versions"]["dataset"]
                or plan["versions"]["embedding_profile"] != snapshot["spec"]["embedding_profile"]
                or any(plan["profile"][key] != snapshot["spec"][key] for key in ("provider", "model", "dimensions"))):
            raise AuditError("Batch, run and original embedding profile bindings differ")
        bound.append({"batch": batch, "run": row["run"]})
    engine.ledger.append(session, "analysis.cache_reused", {"execution": execution,
        "master": checkpoint["master"], "snapshot": master["snapshot"], "model_calls": 0,
        "basis": "Exact original plan/version-bound model outputs; original retrieval.build revalidates complete attempts and raw responses"})
    return checkpoint, master, snapshot, bound


def _source_map(engine: Research, session: str, catalog: store.Catalog, batch: Json) -> dict[str, Json]:
    rows = engine.ledger.artifacts.read(batch["mapping_artifact"])
    mapping = {row["source_version"]: row for row in rows}
    selected = engine.ledger.get(batch["dataset"], "dataset")["source_versions"]
    if (len(mapping) != len(rows) or len(rows) != batch["articles"] or set(mapping) != set(selected)
            or len({row["article_id"] for row in rows}) != len(rows)):
        raise AuditError("Catalog/core-source mapping is not one-to-one and complete")
    sql = "SELECT id,payload FROM sources WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id"
    parameters = [canonical(selected)]
    engine.ledger.append(session, "catalog_vector.sources.inspection.intended", {"sql": sql,
        "parameters": parameters, "mapping": batch["mapping_artifact"],
        "purpose": "Revalidate exact core/catalog provider and retained body identity; no semantic judgement"})
    seen = set()
    for source in engine.ledger.db.execute(sql, parameters):
        value = json.loads(source["payload"])
        row = mapping[source["id"]]
        old = catalog.db.execute("SELECT payload,article_id FROM records WHERE record_id=?", (row["record_id"],)).fetchone()
        if old is None:
            raise AuditError("Mapped catalog source record is absent")
        article = json.loads(old["payload"])
        body = value.get("body")
        provenance = value.get("catalog_provenance", {})
        if (value.get("retention") != "permitted" or article.get("retention") != "permitted"
                or article.get("quarantined") or not isinstance(body, str) or not body.strip()
                or body != article.get("body") or hashlib.sha256(body.encode()).hexdigest() != article["body_sha256"]
                or value["source_key"] != "eventregistry:" + article["provider_article_id"]
                or store.article_identity(article) != row["article_id"] or old["article_id"] != row["article_id"]
                or provenance.get("article_id") != row["article_id"] or provenance.get("record_id") != row["record_id"]
                or provenance.get("snapshot") != batch["snapshot"] or provenance.get("body_sha256") != article["body_sha256"]):
            raise AuditError("Core source differs from its exact permitted catalog version")
        seen.add(source["id"])
    if seen != set(mapping):
        raise AuditError("Core source inspection coverage is incomplete")
    return mapping


def _pool(engine: Research, session: str, catalog: store.Catalog, item: Json, positions: dict[str, int],
          matrix: Any, directory: Path) -> Json:
    batch = item["batch"]
    mapping = _source_map(engine, session, catalog, batch)
    built = retrieval.build(engine, session, Context("Index exact complete full-corpus embedding batch",
        "automatic:registered-offline-vector-expansion", batch["plan_versions"]),
        {"plan": batch["plan"], "embedding_run": item["run"]})
    index = engine.ledger.get(built["id"], "vector_index")
    selected = set(mapping)
    seen = set()
    path = directory / (batch["id"] + "-pooled-mapping.jsonl")
    with path.open("xb") as output, vectors(engine, session, index) as (rows, passage_matrix):
        if os.name != "nt":
            path.chmod(0o600)
        start = 0
        while start < len(rows):
            source = rows[start]["source_version"]
            end = start + 1
            while end < len(rows) and rows[end]["source_version"] == source:
                end += 1
            if source not in selected or source in seen or end-start != mapping[source]["chunks"]:
                raise AuditError("Passage rows are not complete contiguous exact source windows")
            ids, pooled, missing, retained = aggregate(rows[start:end], passage_matrix[start:end], [source])
            if ids != [source] or missing:
                raise AuditError("Complete source vectors did not produce the original pooled representation")
            article = mapping[source]["article_id"]
            if article not in positions:
                raise AuditError("Pooled source is outside the retained-text catalog frame")
            matrix[positions[article]] = pooled[0]
            for chunk in retained[0]["chunks"]:
                chunk["row"] += start
            output.write((canonical({**retained[0], "article_id": article, "passage_index": built["id"]}) + "\n").encode())
            try:
                catalog.db.execute("INSERT INTO expanded_vector_sources VALUES (?,?,?,?,?)",
                    (article, source, batch["plan"], built["id"], end-start))
            except sqlite3.IntegrityError as error:
                raise AuditError("An article occurs more than once in the expansion frame") from error
            seen.add(source)
            start = end
        output.flush()
        os.fsync(output.fileno())
    if seen != selected:
        raise AuditError("Pooled source coverage is incomplete")
    mapping_ref = _save(engine, session, path, "Exact per-article original passage-row pooling map; JSONL", file=True)
    path.unlink()
    matrix.flush()
    catalog.commit()
    value = {"batch": batch["id"], "plan": batch["plan"], "embedding_run": item["run"],
        "index": built["id"], "pooled_sources": len(seen), "passage_vectors": len(rows), "mapping_artifact": mapping_ref,
        "pooling": "Original aggregate per contiguous source; float64 sequential sum; normalized float32 output",
        "model_calls": 0, "network_calls": 0}
    engine.ledger.append(session, "catalog_vector.batch.completed", value)
    return value


def query_shards(engine: Research, session: str, manifest_ref: str, queries: Any, *, top_k: int = 8,
                 candidate_limit: int = 64, exclude_ids: list[str | None] | None = None) -> Json:
    """Load one bounded shard at a time, then merge canonical reranked neighbors.

    This is a technical retrieval primitive. Its calling research operation must
    log query intent and publish the exact results; no standalone search route is
    supplied here. Latency across all shards remains unmeasured.
    """
    require_active(engine, session)
    manifest = engine.ledger.artifacts.read(manifest_ref)
    spec = manifest["spec"]
    if (manifest.get("method") != METHOD or manifest.get("kind") != "sharded_flat"
            or manifest.get("namespace") != store.namespace(spec) or manifest.get("level") != "article"):
        raise AuditError("Require the exact sharded article manifest")
    output: list[list[Json]] | None = None
    count = 0
    previous = None
    for shard in manifest["shards"]:
        current, _ = _files(engine, shard["manifest"], spec, "article")
        handle = store.load_index(current, spec)
        if (len(handle["ids"]) != shard["count"] or handle["ids"][0] != shard["first_id"]
                or handle["ids"][-1] != shard["last_id"] or (previous is not None and previous >= shard["first_id"])):
            raise AuditError("Article shard ranges or coverage differ")
        found = store.query(handle, queries, top_k=top_k, candidate_limit=candidate_limit, exclude_ids=exclude_ids)["results"]
        if output is None:
            output = [[] for _ in found]
        for kept, rows in zip(output, found, strict=True):
            kept.extend(rows)
            kept.sort(key=lambda row: (-row["score"], row["id"]))
            del kept[top_k:]
        count += shard["count"]
        previous = shard["last_id"]
        del handle
    if count != manifest["count"]:
        raise AuditError("Article shard counts do not cover the declared frame")
    return {"results": [[{**row, "rank": rank} for rank, row in enumerate(rows, 1)] for rows in output or []],
        "namespace": manifest["namespace"], "level": "article", "shards": len(manifest["shards"]),
        "candidate_limit_per_shard": candidate_limit, "scanned_vectors": count,
        "latency": "Unmeasured; every shard is restored and checked; no fast-service claim",
        "score": "Canonical float32 vectors; float64 cosine reranking; not event probability"}


def render(value: Json) -> str:
    c = value["catalog"]["summary"]
    return "\n".join(["Full-corpus offline vector-index result", "",
        f"Vector coverage: {c['available_embeddings']:,}/{c['articles']:,} article versions; retained-text versions {c['with_text']:,}.",
        f"Built {len(value['new_passage_indexes']):,} complete passage-index batches from {value['new_passage_vectors']:,} saved vectors. Total retained passage vectors: {value['passage_vectors']:,}.",
        f"The immutable article snapshot has {value['article_index']['count']:,} vectors in {value['article_index']['shards']:,} bounded FlatIP shards. Numerical retrieval benchmarking is pending; all-shard latency is unmeasured.",
        f"Text unavailable: {c['without_text']:,}, including {c['quarantined_articles']:,} quarantines. Retained-text articles still missing vectors: {value['catalog']['pending']['articles']:,}; failed/pending indexing rows: 0/0.",
        f"Preserved {value['group_index']['count']:,} existing group vectors and every seven-day membership. New source versions remain ungrouped; new accepted dossiers and group merges: 0/0.",
        "New model/network calls: 0/0. This step reuses the exact authorized saved embedding results. Similarity is not event identity or probability; semantic event quality remains unvalidated."])


def _present(engine: Research, session: str, context: Context, identifier: str, value: Json) -> Json:
    presentation = engine._record_presentation(session, context, {"results": [{"kind": "event_vector_store_result", "id": identifier}],
        "markdown": render(value), "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **value, "presentation": presentation}


def _reuse(engine: Research, session: str, context: Context, identifier: str, value: Json) -> Json:
    catalog = store.Catalog(engine.ledger.artifacts.verified_path(value["catalog"]["artifact"]), value["spec"], readonly=True)
    try:
        checked = catalog.verify()
        if any(checked[key] != expected for key, expected in value["catalog"]["summary"].items() if key in checked):
            raise AuditError("Completed catalog snapshot coverage changed")
    finally:
        catalog.close()
    manifest = engine.ledger.artifacts.read(value["article_index"]["manifest"])
    if (manifest.get("method") != METHOD or manifest.get("spec") != value["spec"]
            or manifest.get("namespace") != store.namespace(value["spec"])
            or manifest.get("kind") != "sharded_flat" or manifest.get("count") != value["article_index"]["count"]):
        raise AuditError("Completed article shard namespace or count differs")
    count, previous = 0, None
    for shard in manifest["shards"]:
        current, _ = _files(engine, shard["manifest"], value["spec"], "article")
        restored = store.load_index(current, value["spec"])
        if (shard["count"] != len(restored["ids"]) or shard["first_id"] != restored["ids"][0]
                or shard["last_id"] != restored["ids"][-1] or (previous is not None and previous >= shard["first_id"])):
            raise AuditError("Completed article shard coverage differs")
        previous = shard["last_id"]
        count += shard["count"]
        del restored
    if count != manifest["count"]:
        raise AuditError("Completed article shard counts differ")
    engine.ledger.append(session, "analysis.cache_reused", {"result": identifier,
        "basis": "Complete catalog identity/content verification; fresh full component hashes; every bounded article shard restored and reconstructed; exact version-bound reuse"})
    return _present(engine, session, context, identifier, value)


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"execution", "key", "instruction"} or not isinstance(data["instruction"], str)
            or not data["instruction"].strip() or not isinstance(data["key"], str)
            or not 1 <= len(data["key"]) <= 128):
        raise ResearchError("Declare one exact complete execution, stable snapshot key and offline instruction")
    method = {"method": METHOD, "implementation": {name: sha256(Path(__file__).with_name(name)) for name in CODE},
        "execution": data["execution"], "instruction": data["instruction"], "article_shard_rows": SHARD_ROWS,
        "passage_index": retrieval.METHOD, "pooling": "Original aggregate per contiguous source; exact float64 order and f32 output",
        "source_validation": "Complete parent catalog.verify plus every new core/catalog provider/body/map identity; full artifact hashes",
        "immutable_reuse": "Parent catalog backed up to staging; original article vectors byte-preserved; group artifacts/memberships reused by exact hashes",
        "scope": "Offline retrieval representation expansion only; no new source collection, models, grouping, acceptance or semantic quality claim"}
    prior = engine.ledger.db.execute("SELECT id FROM records WHERE kind='catalog_vector_index_manifest' AND logical_key=?", (data["key"],)).fetchone()
    if prior and engine.ledger.get(prior[0], "catalog_vector_index_manifest")["method"] != method:
        raise ResearchError("Snapshot key binds another exact execution or method; register a new version")
    versions = {}
    for kind, content in {"protocol": {"method": method}, "question": {"text": "Index all exact completed full-corpus embeddings while preserving current event groups"},
        "selection": {"rules": {"execution": data["execution"], "scope": "Every complete exact master-plan batch"}},
        "profile": {"mode": "exploratory", "population_estimate": False}}.items():
        versions[kind] = engine._version(session, context, {"kind": kind, "key": data["key"], "content": content,
            "amend_latest": True, "reason": "Register the offline complete-run index expansion before source reads"})["id"]
    manifest_id = engine.ledger.record(session, "catalog_vector_index_manifest", data["key"], {"versions": versions, "method": method})
    engine.ledger.append(session, "catalog_vector.build.intended", {"manifest": manifest_id, "execution": data["execution"], "model_calls": 0})
    checkpoint, master, snapshot, batches = _inputs(engine, session, data["execution"])
    versions.update(embedding_profile=snapshot["spec"]["embedding_profile"], dossier_definition=snapshot["versions"]["dossier_definition"])
    bound = Context(context.objective, context.actor, versions)
    spec = snapshot["spec"]
    source_path = engine.ledger.artifacts.verified_path(snapshot["catalog"]["artifact"])
    article_manifest, article_paths = _files(engine, snapshot["article_index"]["manifest"], spec, "article")
    group_manifest, _ = _files(engine, snapshot["group_index"]["manifest"], spec, "group")
    engine.ledger.artifacts.verified_path(snapshot["group_memberships"])
    if group_manifest["count"] != snapshot["group_index"]["count"]:
        raise AuditError("Preserved group-vector coverage differs")
    engine.ledger.append(session, "analysis.cache_reused", {"snapshot": master["snapshot"],
        "article_manifest": snapshot["article_index"]["manifest"], "group_manifest": snapshot["group_index"]["manifest"],
        "basis": "Fresh complete artifact hashes and namespace/shape checks; exact parent bytes previously fully restored and checked; no old vectors recomputed"})
    completed = engine.ledger.db.execute("SELECT id FROM records WHERE kind='event_vector_store_result' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (data["key"],)).fetchone()
    if completed:
        value = engine.ledger.get(completed[0], "event_vector_store_result")
        if value.get("method") != METHOD or value.get("execution") != data["execution"] or value.get("versions") != versions:
            raise ResearchError("Completed snapshot key differs from exact execution/method versions")
        return _reuse(engine, session, bound, completed[0], value)
    with tempfile.TemporaryDirectory(dir=engine.ledger.root, prefix="catalog-index-stage-") as temporary:
        directory = Path(temporary)
        source = store.Catalog(source_path, spec, readonly=True)
        target = directory / "catalog.sqlite3"
        try:
            parent_summary = source.verify()
            if parent_summary["available_embeddings"] != article_manifest["count"]:
                raise AuditError("Parent catalog and article snapshot coverage differ")
            staging = sqlite3.connect(target)
            try:
                source.db.backup(staging)
            finally:
                staging.close()
        finally:
            source.close()
        catalog = store.Catalog(target, spec)
        if os.name != "nt":
            target.chmod(0o600)
        matrix = None
        try:
            catalog.db.execute("CREATE TABLE expanded_vector_sources(article_id TEXT PRIMARY KEY REFERENCES articles,source_version TEXT,plan TEXT,passage_index TEXT,chunk_count INTEGER)")
            ids = [row[0] for row in catalog.db.execute("SELECT DISTINCT article_id FROM records WHERE json_extract(payload,'$.text_quality.nonblank_body')=1 ORDER BY article_id")]
            positions = {identifier: ordinal for ordinal, identifier in enumerate(ids)}
            expected = article_manifest["count"] + master["articles"]
            if len(ids) != expected:
                raise AuditError("Retained-text frame differs from exact old-plus-new vector coverage")
            # Original passage builds retain their own stricter per-batch guard.
            # Keep global staging bounded by canonical article storage plus copies.
            required = len(ids)*spec["dimensions"]*12 + source_path.stat().st_size*2 + 512*1024**2
            if shutil.disk_usage(engine.ledger.root).free < required:
                raise ResearchError("Insufficient disk space for immutable article/catalog staging")
            matrix_path = directory / "all-article-vectors.f32"
            matrix = np.memmap(matrix_path, mode="w+", dtype="<f4", shape=(len(ids), spec["dimensions"]))
            if os.name != "nt":
                matrix_path.chmod(0o600)
            old_ids = json.loads(article_paths["mapping"].read_text(encoding="utf-8"))
            if (not isinstance(old_ids, list) or len(old_ids) != article_manifest["count"]
                    or old_ids != sorted(set(old_ids)) or any(identifier not in positions for identifier in old_ids)):
                raise AuditError("Original article snapshot mapping differs from the catalog")
            old_matrix = np.memmap(article_paths["vectors"], mode="r", dtype="<f4", shape=(len(old_ids), spec["dimensions"]))
            try:
                for ordinal, identifier in enumerate(old_ids):
                    matrix[positions[identifier]] = old_matrix[ordinal]
            finally:
                getattr(old_matrix, "_mmap").close()
            engine.ledger.append(session, "catalog_vector.original_vectors.reused", {"articles": len(old_ids),
                "manifest": snapshot["article_index"]["manifest"], "byte_preserved": True})
            built = [_pool(engine, session, catalog, item, positions, matrix, directory) for item in batches]
            expanded = {row[0] for row in catalog.db.execute("SELECT article_id FROM expanded_vector_sources")}
            if expanded.intersection(old_ids) or expanded.union(old_ids) != set(ids) or len(expanded) != master["articles"]:
                raise AuditError("Pooled article coverage overlaps or misses the original exact frame")
            matrix.flush()
            shards = []
            for start in range(0, len(ids), SHARD_ROWS):
                selected = ids[start:start+SHARD_ROWS]
                handle = store.build_index(selected, matrix[start:start+len(selected)], spec, level="article")
                saved = _persist(engine, session, handle, directory / ("article-shard-" + str(start)))
                del saved["restored"]
                current = engine.ledger.artifacts.read(saved["manifest"])
                for row, identifier in enumerate(selected):
                    provenance = catalog.db.execute("SELECT * FROM expanded_vector_sources WHERE article_id=?", (identifier,)).fetchone()
                    if provenance is not None:
                        catalog.attach_vector(identifier, {"namespace": catalog.namespace, "level": "article",
                            "source_version": provenance["source_version"], "plan": provenance["plan"],
                            "index_artifact": current["files"]["vectors"]["sha256"], "vector_row": row,
                            "article_manifest": saved["manifest"], "original_passage_index": provenance["passage_index"],
                            "pooling": spec["pooling"], "reuse": "Exact complete saved model output; original source/passage pooling"})
                shards.append({"manifest": saved["manifest"], "count": len(selected), "first_id": selected[0], "last_id": selected[-1]})
                del handle
                shard_path = (directory / ("article-shard-" + str(start))).resolve()
                if shard_path.parent != directory.resolve():
                    raise AuditError("Shard staging cleanup escaped the protected temporary directory")
                shutil.rmtree(shard_path)
            catalog.commit()
            summary = catalog.verify()
            summary.update(with_text=len(ids), without_text=summary["articles"]-len(ids),
                provider_article_ids=catalog.db.execute("SELECT count(DISTINCT provider_article_id) FROM articles").fetchone()[0])
            pending_sql = "SELECT count(*) AS articles,coalesce(sum(p.chunks),0) AS chunks,coalesce(sum(p.input_tokens),0) AS input_tokens FROM pending_embeddings p WHERE NOT EXISTS (SELECT 1 FROM vector_refs v WHERE v.article_id=p.article_id)"
            engine.ledger.append(session, "catalog_vector.coverage.intended", {"sql": pending_sql, "parameters": [], "catalog_parent": snapshot["catalog"]["artifact"]})
            pending = dict(catalog.db.execute(pending_sql).fetchone())
            if summary["available_embeddings"] != len(ids) or pending["articles"]:
                raise AuditError("Final article vector references do not cover every retained-text version")
        finally:
            if matrix is not None:
                getattr(matrix, "_mmap").close()
            catalog.close()
        catalog_ref = _save(engine, session, target, "New immutable catalog preserving original records, occurrences, memberships and references", file=True)
        article_value = {"method": METHOD, "kind": "sharded_flat", "namespace": store.namespace(spec), "spec": spec,
            "level": "article", "count": len(ids), "shard_rows": SHARD_ROWS, "shards": shards,
            "parent_snapshot": master["snapshot"], "execution": data["execution"], "benchmark": "pending; all-shard latency unmeasured"}
        article_ref = _save(engine, session, article_value, "Complete immutable bounded article-shard manifest")
    value = {"versions": versions, "manifest": manifest_id, "method": METHOD, "execution": data["execution"],
        "parent_snapshot": master["snapshot"], "master": checkpoint["master"], "spec": spec,
        "catalog": {**snapshot["catalog"], "artifact": catalog_ref, "summary": summary, "pending": pending,
            "original_pending_queue": snapshot["catalog"]["pending"], "pending_sql": pending_sql},
        "article_index": {"manifest": article_ref, "count": len(ids), "shards": len(shards), "kind": "sharded_flat",
            "benchmark": {"status": "pending", "semantic_quality": "unvalidated", "latency": "unmeasured"}},
        "group_index": snapshot["group_index"], "group_memberships": snapshot["group_memberships"],
        "original_passage_index": snapshot["original_passage_index"], "new_passage_indexes": built,
        "new_passage_vectors": sum(row["passage_vectors"] for row in built),
        "passage_vectors": snapshot["passage_vectors"] + sum(row["passage_vectors"] for row in built),
        "inventory": snapshot["inventory"], "inventory_artifact": snapshot["inventory_artifact"],
        "inventory_fingerprint": snapshot["inventory_fingerprint"], "queries": [],
        "actual_group_merges": 0, "new_model_calls": 0, "network_calls": 0, "failed_rows": 0, "pending_rows": 0,
        "new_sources_ungrouped": master["articles"], "status": "all_retained_text_vectors_ready_event_grouping_pending"}
    identifier = engine.ledger.record(session, "event_vector_store_result", data["key"], value)
    return _present(engine, session, bound, identifier, value)
