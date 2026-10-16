"""Audited full-corpus catalog and immutable saved-vector snapshots.

The catalog is a source registry, not an oversized core dataset import.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from typing import TYPE_CHECKING, Any
import zipfile

import numpy as np

from . import event_group_centroids as centroids
from . import event_pair_study
from . import event_vector_store as store
from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .embeddings import offline_tokenizer
from .legacy import sha256, within

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "full-corpus-event-vector-catalog-v1"
CODE = ("event_vector_scale.py", "event_vector_store.py")
PARAGRAPHS = r"[^\n]+(?:\n(?!\n)[^\n]+)*"


def _save(engine: Research, session: str, value: Any, purpose: str, *, file: bool = False) -> str:
    reference = engine.ledger.artifacts.put_file(value) if file else engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": purpose})
    return str(reference)


def _code() -> Json:
    return {name: sha256(Path(__file__).with_name(name)) for name in CODE}


def _existing(engine: Research, session: str, plan_id: str, groups_id: str) -> Json:
    plan, _, _ = event_pair_study.load_plan(engine, session, plan_id)
    original = engine.ledger.get(plan["index"], "vector_index")
    embedding = engine.ledger.get(original["plan"], "embedding_plan")
    profile_id = embedding["versions"]["embedding_profile"]
    profile = engine.ledger.get(profile_id, "embedding_profile")["content"]
    if profile["dimensions"] != original["dimensions"] or any(embedding["versions"].get(k) != v for k, v in original["versions"].items() if k != "retrieval_profile"):
        raise AuditError("Original embedding profile/index provenance differs")
    spec = {"embedding_profile": profile_id, "provider": profile["provider"], "model": profile["model"],
        "dimensions": profile["dimensions"], "chunking": "unicode-window-1600-overlap-200-v1",
        "pooling": "L2-normalized float64 sum of every saved unit passage-window vector; float32 output", "normalization": "l2"}
    mapping = engine.ledger.artifacts.read(plan["mapping_artifact"])
    pooled = np.frombuffer(engine.ledger.artifacts.read_bytes(plan["pooled_vectors_artifact"]), dtype="<f4").reshape(len(mapping), spec["dimensions"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    selected = engine.ledger.get(plan["versions"]["dataset"], "dataset")["source_versions"]
    sql = "SELECT id,payload FROM sources WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id"
    parameters = [canonical(selected)]
    engine.ledger.append(session, "event_store.source_identity_read.intended", {"sql": sql, "parameters": parameters, "purpose": "Exact provider ID/body hash mapping; no semantic judgement"})
    identities = {}
    for row in engine.ledger.db.execute(sql, parameters):
        source = json.loads(row["payload"])
        body_hash = hashlib.sha256(source["body"].encode()).hexdigest()
        if body_hash != metadata[row["id"]]["body_sha256"] or not source["source_key"].startswith("eventregistry:"):
            raise AuditError("Saved source identity/body differs from vector plan")
        identities[row["id"]] = (source["source_key"][len("eventregistry:"):], body_hash)
    if len(identities) != len(selected):
        raise AuditError("Original source identities are incomplete")
    groups = engine.ledger.get(groups_id, "event_group_refinement_result")
    if not groups["adopted"] or groups["versions"]["dataset"] != plan["versions"]["dataset"]:
        raise AuditError("Declare the current guarded groups from the original dataset")
    rows = engine.ledger.artifacts.read(groups["exports"]["groups"]["artifact"])
    engine.ledger.append(session, "event_store.vectors.reused", {"plan": plan_id, "index": plan["index"],
        "pooled_vectors": plan["pooled_vectors_artifact"], "mapping": plan["mapping_artifact"], "groups": groups_id,
        "passage_vectors": original["vectors_artifact"], "passage_index": original["index_artifact"], "model_calls": 0})
    return {"plan": plan, "spec": spec, "profile": profile, "mapping": mapping, "pooled": pooled,
        "metadata": metadata, "identities": identities, "groups": rows, "passage_index": original}


def _inventory(engine: Research, session: str, context: Context, root: Path) -> Json:
    verified = engine._verify_legacy(session, context, {"data_root": str(root)})
    original = engine.ledger.artifacts.read(verified["input_inventory"])
    bundles = [{**item, "cohort": "legacy"} for item in original["files"] if item["kind"] == "article-bundle"]
    topic = root / "topics/cybercrime-nl"
    if not topic.is_dir():
        raise ResearchError("The requested Cybercrime NL topic is unavailable")
    checksums: list[Json] = []
    listed: set[str] = set()
    cyber_expected = 0
    for checksum_file in sorted(topic.rglob("SHA256SUMS.txt")):
        entries: list[Json] = []
        for line in checksum_file.read_text(encoding="utf-8").splitlines():
            expected, name = line.split("  ", 1)
            if not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ResearchError("Invalid cybercrime checksum manifest")
            path = within(checksum_file.parent.resolve(), name)
            if not path.is_file() or sha256(path) != expected:
                raise AuditError("Cybercrime file checksum differs")
            entries.append({"path": path.relative_to(root).as_posix(), "sha256": expected, "bytes": path.stat().st_size})
            if path.suffix == ".zip" and path.parent.name == "articles":
                relative = path.relative_to(root).as_posix()
                if relative in listed:
                    raise ResearchError("Cybercrime bundle listed by multiple manifests")
                listed.add(relative)
                bundles.append({**entries[-1], "kind": "article-bundle", "cohort": "cybercrime-nl"})
        if any(Path(entry["path"]).suffix == ".zip" and Path(entry["path"]).parent.name == "articles" for entry in entries):
            missingness = checksum_file.parent / "missingness.json"
            receipt_entry = next((entry for entry in entries if entry["path"] == missingness.relative_to(root).as_posix()), None)
            if receipt_entry is None:
                raise AuditError("Cybercrime missingness receipt must be checksum-bound")
            receipt = json.loads(missingness.read_text(encoding="utf-8"))
            if type(receipt.get("total_records")) is not int or receipt["total_records"] < 0:
                raise AuditError("Cybercrime missingness total_records is unavailable")
            cyber_expected += receipt["total_records"]
        checksums.append({"path": checksum_file.relative_to(root).as_posix(), "sha256": sha256(checksum_file), "entries": entries})
    actual = {p.relative_to(root).as_posix() for p in topic.glob("**/articles/*.zip")}
    if not actual or actual != listed:
        raise ResearchError("Cybercrime article bundles do not reconcile to checksum manifests")
    return {"legacy_verification": verified, "legacy_inventory": verified["input_inventory"], "cyber_checksums": checksums,
        "expected_rows_by_cohort": {"legacy": verified["article_records"], "cybercrime-nl": cyber_expected},
        "bundles": sorted(bundles, key=lambda row: row["path"]),
        "scope": "All inventoried legacy bundles plus all checksummed Cybercrime NL article bundles including2020-2023 extension; metadata-only manifest diagnostics are not extra full-text articles"}


def _article(row: Json, raw: bytes, bundle: Json, line: int) -> tuple[Json, Json, bool]:
    record = row.get("article")
    if not isinstance(record, dict):
        raise ResearchError("Archive article object is missing")
    row_hash = hashlib.sha256(raw).hexdigest()
    if bundle["cohort"] == "cybercrime-nl" and digest(record) != row.get("source_hash"):
        raise AuditError("Cybercrime materialized record hash differs")
    identifier = record.get("uri")
    if identifier is not None and not isinstance(identifier, str):
        raise ResearchError("Provider article ID has an invalid type")
    safe_id = identifier
    try:
        require_no_credentials(safe_id)
    except ResearchError:
        safe_id = None
    body = record.get("body")
    if body is not None and not isinstance(body, str):
        raise ResearchError("Archive body is not text/null")
    body = body or ""
    flagged = record.get("quarantined") is True
    try:
        require_no_credentials(row)
    except ResearchError:
        flagged = True
    occurrence = {"bundle": bundle["path"], "bundle_sha256": bundle["sha256"], "line": line,
        "row_sha256": row_hash, "cohort": row.get("collection_cohort", bundle["cohort"]) if not flagged else bundle["cohort"],
        "collection": bundle["cohort"], "retrieved_at": None,
        "retrieval_time_state": "Not inferred from publication/import time; refer to original archive or receipt"}
    article = {"provider": "eventregistry", "provider_article_id": safe_id or "local-missing-uri:" + row_hash,
        "provider_id_available": bool(safe_id), "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "retention": "metadata_only" if flagged else "permitted", "quarantined": flagged}
    if not flagged:
        article.update(title=record.get("title"), url=record.get("url"),
            published_at=record.get("dateTimePub") or record.get("dateTime") or record.get("date"),
            body=body, raw_record=record, text_quality={"body_characters": len(body), "nonblank_body": bool(body.strip()),
                "short_body_at_most_200": bool(body.strip()) and len(body) <= 200, "semantic_text_fidelity": "unvalidated"})
        occurrence["row_metadata"] = {k: v for k, v in row.items() if k != "article"}
    else:
        article["text_unavailable_reason"] = "credential_pattern_quarantine"
    return article, occurrence, flagged


def _workload(body: str, encoder: Any) -> tuple[int, int, int]:
    passages = chunks = tokens = 0
    for match in re.finditer(PARAGRAPHS, body):
        text = match.group()
        if not text.strip():
            continue
        passages += 1
        offset = 0
        while offset < len(text):
            end = min(offset + 1600, len(text))
            tokens += len(encoder.encode(text[offset:end], disallowed_special=()))
            chunks += 1
            if end == len(text):
                break
            offset = end - 200
    return passages, chunks, tokens


def _catalog(engine: Research, session: str, root: Path, inventory: Json, inputs: Json, directory: Path, batch: int) -> Json:
    catalog = store.Catalog(directory / "catalog.sqlite3", inputs["spec"])
    if os.name != "nt":
        catalog.path.chmod(0o600)
    catalog.db.execute("CREATE TABLE pending_embeddings(article_id TEXT PRIMARY KEY REFERENCES articles,passages INTEGER,chunks INTEGER,input_tokens INTEGER)")
    catalog.db.execute("CREATE TABLE group_members(group_id TEXT,source_version TEXT,article_id TEXT REFERENCES articles,PRIMARY KEY(group_id,source_version))")
    encoder = offline_tokenizer()
    reusable = {inputs["identities"][row["source_version"]] for row in inputs["mapping"]}
    counts: Counter[str] = Counter()
    cohorts: dict[str, Counter[str]] = {}
    raw_artifacts = []
    workload_cache: dict[str, tuple[int, int, int]] = {}
    try:
        for ordinal, bundle in enumerate(inventory["bundles"]):
            path = within(root, bundle["path"])
            if sha256(path) != bundle["sha256"]:
                raise AuditError("Article bundle changed before catalog build")
            cohort = cohorts.setdefault(bundle["cohort"], Counter())
            safe_path = directory / f"permitted-original-rows-{ordinal}.jsonl"
            with safe_path.open("xb") as safe, zipfile.ZipFile(path) as archive:
                if os.name != "nt":
                    safe_path.chmod(0o600)
                with archive.open("artikelen.jsonl") as stream:
                    for number, raw in enumerate(stream, 1):
                        if not raw.strip():
                            continue
                        article, occurrence, flagged = _article(json.loads(raw), raw, bundle, number)
                        result = catalog.append_article(article, occurrence)
                        for counter in (counts, cohort):
                            counter["rows"] += 1
                            counter["quarantined_rows"] += int(flagged)
                            counter["body_rows"] += int(not flagged and bool(article.get("body", "").strip()))
                            counter["new_article_versions"] += int(result["new_article"])
                        if not flagged:
                            safe.write(raw)
                        body = article.get("body", "")
                        if result["new_article"] and not flagged and body.strip() and (article["provider_article_id"], article["body_sha256"]) not in reusable:
                            body_hash = article["body_sha256"]
                            if body_hash not in workload_cache:
                                workload_cache[body_hash] = _workload(body, encoder)
                            catalog.db.execute("INSERT INTO pending_embeddings VALUES (?,?,?,?)", (result["article_id"], *workload_cache[body_hash]))
                        if counts["rows"] % batch == 0:
                            catalog.commit()
                            engine.ledger.append(session, "event_store.catalog.batch_completed", {"rows": counts["rows"], "batch_limit": batch, "bundle": bundle["path"]})
                safe.flush()
                os.fsync(safe.fileno())
            if sha256(path) != bundle["sha256"]:
                raise AuditError("Article bundle changed during catalog build")
            raw_artifacts.append({"bundle": bundle["path"], "artifact": _save(engine, session, safe_path, "Permitted exact original JSONL rows; quarantines excluded with row hashes retained", file=True)})
            safe_path.unlink()
            catalog.commit()
            engine.ledger.append(session, "event_store.catalog.bundle_completed", {"bundle": bundle["path"], "rows": counts["rows"], "cohort": dict(cohort)})
        expected_counts = inventory.get("expected_rows_by_cohort")
        if (not isinstance(expected_counts, dict) or any(type(value) is not int or value < 0 for value in expected_counts.values())
                or sum(expected_counts.values()) != counts["rows"]
                or any((cohorts[cohort]["rows"] if cohort in cohorts else 0) != expected for cohort, expected in expected_counts.items())):
            raise AuditError("Catalog row counts differ from the verified collection receipts")
        source_to_article = {}
        unique: dict[str, tuple[str, int]] = {}
        for vector_row, row in enumerate(inputs["mapping"]):
            source_id = row["source_version"]
            uri, body_hash = inputs["identities"][source_id]
            article_id = catalog.find("eventregistry", uri, body_hash)
            if article_id is None:
                raise AuditError("Original vector source lacks an exact full-corpus provider/body mapping")
            source_to_article[source_id] = article_id
            old = unique.get(article_id)
            if old is None or source_id < old[0]:
                unique[article_id] = (source_id, vector_row)
            catalog.attach_vector(article_id, {"namespace": catalog.namespace, "level": "article", "source_version": source_id,
                "plan": inputs["plan"]["manifest"], "vector_row": vector_row, "index_artifact": inputs["plan"]["pooled_vectors_artifact"],
                "original_passage_index": inputs["plan"]["index"], "reuse": "Exact provider ID/body hash and original model/chunking/pooling profile"})
        for group in inputs["groups"]:
            for source in group["members"]:
                catalog.db.execute("INSERT INTO group_members VALUES (?,?,?)", (group["group_id"], source, source_to_article[source]))
        catalog.commit()
        summary = catalog.verify()
        summary["with_text"] = catalog.db.execute("SELECT count(DISTINCT article_id) FROM records WHERE json_extract(payload,'$.text_quality.nonblank_body')=1").fetchone()[0]
        summary["without_text"] = summary["articles"] - summary["with_text"]
        summary["provider_article_ids"] = catalog.db.execute("SELECT count(DISTINCT provider_article_id) FROM articles").fetchone()[0]
        summary["body_families"] = catalog.db.execute("SELECT count(DISTINCT body_sha256) FROM articles WHERE quarantined=0").fetchone()[0]
        summary["repeated_body_families"] = catalog.db.execute("SELECT count(*) FROM (SELECT body_sha256 FROM articles WHERE quarantined=0 GROUP BY body_sha256 HAVING count(*)>1)").fetchone()[0]
        pending = dict(catalog.db.execute("SELECT count(*) AS articles,coalesce(sum(passages),0) AS passages,coalesce(sum(chunks),0) AS chunks,coalesce(sum(input_tokens),0) AS input_tokens FROM pending_embeddings").fetchone())
        pending.update({"usd_estimate_at_bound_profile_rate": str(Decimal(pending["input_tokens"]) * Decimal(inputs["profile"]["usd_per_million_input_tokens"]) / Decimal(1000000)),
            "usd_per_million_input_tokens": inputs["profile"]["usd_per_million_input_tokens"], "price_checked_on": inputs["profile"]["price_checked_on"],
            "execution_permission": "NOT authorized; no dispatchable gateway plan yet",
            "scope": "Conservative article-by-article inputs; duplicates across different provider IDs not eliminated; retries/query embeddings excluded"})
        catalog.close()
        with (directory / "catalog.sqlite3").open("r+b") as stream:
            os.fsync(stream.fileno())
        artifact = _save(engine, session, directory / "catalog.sqlite3", "Closed SQL+FTS full source registry, exact vector references and pending workload", file=True)
        return {"artifact": artifact, "summary": summary, "counts": dict(counts), "cohorts": {k: dict(v) for k,v in cohorts.items()}, "pending": pending,
            "raw_rows": raw_artifacts, "article_ids": sorted(unique), "vector_rows": [unique[k][1] for k in sorted(unique)]}
    except BaseException:
        try:
            catalog.close()
        except Exception:
            pass
        raise


def _persist(engine: Research, session: str, handle: Json, directory: Path) -> Json:
    manifest = store.save_index(handle, directory)
    for name, item in manifest["files"].items():
        reference = _save(engine, session, Path(item["path"]), "Persistent " + handle["level"] + " " + name, file=True)
        if reference != item["sha256"]:
            raise AuditError("Vector component changed during publication")
        item["path"] = str(engine.ledger.artifacts.root / reference)
    reference = _save(engine, session, manifest, "Persistent vector namespace and canonical mapping")
    started = time.perf_counter()
    restored = store.load_index(manifest, handle["spec"])
    return {"manifest": reference, "restored": restored, "restore_seconds": time.perf_counter()-started,
        "bytes": sum(Path(v["path"]).stat().st_size for v in manifest["files"].values())}


def _benchmark(handle: Json) -> Json:
    positions = sorted(range(len(handle["ids"])), key=lambda n: digest({"seed": METHOD, "id": handle["ids"][n]}))[:16]
    wide = handle["vectors"].astype(np.float64)
    wide /= np.linalg.norm(wide, axis=1)[:, None]
    rows, durations, baseline = [], [], []
    for position in positions:
        value = handle["vectors"][position:position+1]
        started = time.perf_counter()
        actual = store.query(handle, value, top_k=8, candidate_limit=64, exclude_ids=[handle["ids"][position]])["results"][0]
        durations.append(1000*(time.perf_counter()-started))
        started = time.perf_counter()
        scores = wide @ wide[position]
        ranked = sorted((n for n in range(len(wide)) if n != position), key=lambda n: (-float(scores[n]), handle["ids"][n]))[:8]
        baseline.append(1000*(time.perf_counter()-started))
        expected = {handle["ids"][n] for n in ranked}
        cutoff = float(scores[ranked[-1]]) if ranked else None
        rows.append({"query_id": handle["ids"][position], "expected_ids": sorted(expected), "actual": actual,
            "numerator": sum(r["id"] in expected for r in actual), "denominator": len(expected),
            "tie_aware_numerator": sum(cutoff is not None and r["score"] >= cutoff-0.000002 for r in actual), "boundary_score": cutoff})
    denominator = sum(r["denominator"] for r in rows)
    return {"queries": len(rows), "k": 8, "candidate_limit": 64, "numerical_recall_at_8": sum(r["numerator"] for r in rows)/denominator if denominator else None,
        "tie_aware_numerical_recall_at_8": sum(r["tie_aware_numerator"] for r in rows)/denominator if denominator else None,
        "median_ms": float(np.median(durations)), "p95_ms": float(np.percentile(durations,95)), "baseline_full_float64_and_sort_median_ms": float(np.median(baseline)),
        "rows": rows, "latency_samples_ms": durations,
        "scope": "Retrieval/reranking only; excludes preflight, cold restore, catalog reads, durable audit. Numerical neighbor recall, NOT event recall."}


def _queries(engine: Research, session: str, versions: Json, catalog_ref: str, spec: Json) -> list[Json]:
    path = engine.ledger.artifacts.verified_path(catalog_ref)
    catalog = store.Catalog(path, spec, readonly=True)
    output = []
    try:
        for query in ("ransomware", '"artificial intelligence"'):
            sql = "SELECT f.record_id,bm25(record_search) AS score,r.article_id,json_extract(r.payload,'$.title') AS title,json_extract(r.payload,'$.url') AS url FROM record_search f JOIN records r USING(record_id) WHERE record_search MATCH ? ORDER BY score,f.record_id LIMIT ?"
            parameters = [query, 3]
            count_sql = "SELECT count(*) AS records,count(DISTINCT r.article_id) AS article_versions FROM record_search f JOIN records r USING(record_id) WHERE record_search MATCH ?"
            engine.ledger.append(session,"event_store.search.intended",{"catalog":catalog_ref,"query":query,"sql":sql,"parameters":parameters,"count_sql":count_sql,"count_parameters":[query]})
            counts = dict(catalog.db.execute(count_sql,(query,)).fetchone())
            rows = [dict(row) for row in catalog.db.execute(sql,parameters)]
            value = {"versions":versions,"catalog":catalog_ref,"query":query,"counts":counts,"returned":len(rows),"rows":rows,"sql":sql,"parameters":parameters,"count_sql":count_sql,
                "score":"FTS5 BM25 (lower is better), not embedding similarity/relevance probability","cutoff":None,"failures":0,"pending":0}
            identifier = engine.ledger.record(session,"event_vector_store_query",digest(value),value)
            output.append({"id":identifier,**value})
    finally:
        catalog.close()
    return output


def render(value: Json) -> str:
    c,p = value["catalog"]["summary"],value["catalog"]["pending"]
    lines = ["Full-corpus vector-store scale result", "",
        f"Registered {value['catalog']['counts']['rows']:,} saved rows across {len(value['inventory']['bundles'])} bundles: {c['articles']:,} distinct provider/body article versions ({c['provider_article_ids']:,} provider IDs).",
        f"Text available for {c['with_text']:,}; text unavailable for {c['without_text']:,}, including {c['quarantined_articles']:,} quarantined article versions. All rows accounted for; failed/pending catalog rows: 0/0.",
        f"Reused vectors cover {c['available_embeddings']:,}/{c['articles']:,} article versions. Saved {value['article_index']['count']:,} article vectors and {value['group_index']['count']:,} current group vectors; retained the existing {value['passage_vectors']:,}-vector passage index. No new embeddings, model calls, live collection or group merges.",
        "", "| Collection | Saved rows | Rows with text | Quarantined rows |", "| --- | ---: | ---: | ---: |"]
    for cohort,row in sorted(value["catalog"]["cohorts"].items()):
        lines.append(f"| {cohort} | {row['rows']:,} | {row['body_rows']:,} | {row['quarantined_rows']:,} |")
    lines += ["", f"Pending embedding workload: {p['articles']:,} text-bearing article versions, {p['chunks']:,} chunks, {p['input_tokens']:,} input tokens. Estimated input cost USD {p['usd_estimate_at_bound_profile_rate']} at the retained profile rate USD {p['usd_per_million_input_tokens']}/million tokens (price checked {p['price_checked_on']}); no paid run is authorized or dispatched.",
        "", "| Restored index | Numerical recall@8 | Tie-aware recall@8 | Median / p95 query |", "| --- | ---: | ---: | ---: |"]
    for key in ("article_index","group_index"):
        b=value[key]["benchmark"]
        lines.append(f"| {key.replace('_index','')} ({value[key]['count']:,}) | {b['numerical_recall_at_8']:.1%} | {b['tie_aware_numerical_recall_at_8']:.1%} | {b['median_ms']:.2f} / {b['p95_ms']:.2f} ms |")
    lines += ["",f"Numerical checks used {value['article_index']['benchmark']['queries']} article/{value['group_index']['benchmark']['queries']} group queries. Timings exclude audit preflight and durable query logging. Index restores took {value['article_index']['restore_seconds']:.2f}s (article) and {value['group_index']['restore_seconds']:.2f}s (group). Full operation, including preflight: {value['elapsed_seconds']:.1f}s.",
        "The full corpus is keyword searchable; vector retrieval covers only the compatible embedded subset. New corpus records are not yet event grouped. Existing seven-day memberships and held-out references remain unchanged. Similarity is not event identity or probability; semantic quality remains unvalidated."]
    for query in value["queries"]:
        lines += ["", f"Keyword check {query['query']} across the full retained catalog: {query['counts']['article_versions']:,} matching article versions / {query['counts']['records']:,} metadata records; top {query['returned']} returned/scored; failed/pending 0/0. FTS5 BM25, lower is better; no binary cutoff or tags applied."]
        for rank,row in enumerate(query["rows"],1):
            title=str(row.get("title") or row["article_id"]).replace("\n"," ").replace("[","(").replace("]",")")
            label=f"[{title}]({row['url']})" if isinstance(row.get("url"),str) and row['url'].startswith(("https://","http://")) else title
            lines.append(f"{rank}. {label} -- BM25 {row['score']:.6f}.")
    return "\n".join(lines)


def _present(engine: Research, session: str, context: Context, identifier: str, value: Json) -> Json:
    presentation=engine._record_presentation(session,Context(context.objective,context.actor,value["versions"]),{
        "results":[{"kind":"event_vector_store_result","id":identifier}]+[{"kind":"event_vector_store_query","id":q["id"]} for q in value["queries"]],
        "markdown":render(value),"destination":"codex_chat","status":"prepared_for_delivery"})
    return {"id":identifier,**value,"presentation":presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    allowed={"data_root","plan","group_result","key","instruction","retention","batch_size","started_monotonic"}
    if set(data)-allowed or data.get("retention")!="permitted" or not isinstance(data.get("instruction"),str) or not data["instruction"].strip():
        raise ResearchError("Declare exact full-corpus instruction and permitted local retention; no paid execution fields")
    batch=data.get("batch_size",2000)
    if type(batch) is not int or not 1<=batch<=engine.config.max_articles:
        raise ResearchError("Registry staging batch must fit current working limit")
    key=data["key"]
    if not isinstance(key,str) or not key.strip() or len(key)>128:
        raise ResearchError("Declare a bounded stable snapshot key")
    root=Path(data["data_root"]).resolve()
    method={"method":METHOD,"implementation":_code(),"schema":store.SCHEMA,"source_registry_not_core_dataset_import":True,
        "batch_size":batch,"global_config_unchanged":True,
        "architecture":"SQLite FTS5 full source/body-version registry; separate immutable Faiss FlatIP article/group snapshots; existing passage HNSW-SQ8 reused by reference",
        "identity":"Exact provider URI plus UTF8 body hash; metadata records and original occurrences separate; no fuzzy duplicate collapsing",
        "reuse":"Exact original provider/body identity, model profile, dimensions, chunking and pooling; incompatible/missing vectors stay unprocessed",
        "retention":"Permitted rows only; credential-pattern quarantine before persistence; safe locator/hash placeholders remain in denominator",
        "pending_workload":"Unicode paragraphs;1600-character windows with200 overlap; exact cached cl100k_base token counts; no new model calls",
        "numerical_check":"16 fixed SHA-ranked queries/index; normalized float64 full-corpus top8; tie tolerance2e-6; canonical reranking64 Flat candidates; not event evaluation",
        "group_policy":"Current guarded seven-day groups unchanged; new source versions ungrouped; no automatic links/merges or acceptance",
        "operator_instruction":data["instruction"],"model_calls":0,"network_calls":0}
    prior_manifests=engine.ledger.db.execute("SELECT payload FROM records WHERE kind='event_vector_store_manifest' AND logical_key=?",(key,)).fetchall()
    for prior_row in prior_manifests:
        prior=json.loads(prior_row[0])
        before=prior["inputs"]
        if (prior["method"]!=method or before["plan"]!=data["plan"] or before["group_result"]!=data["group_result"]
                or Path(before["data_root"]).resolve()!=root or before["retention"]!=data["retention"]
                or before.get("batch_size",2000)!=batch):
            raise ResearchError("Store key binds different inputs/implementation; use an explicit new snapshot version")
    versions={}
    definitions={"protocol":{"method":method},
        "question":{"text":"Scale offline source registration and saved vector retrieval across the complete preserved archive and latest Cybercrime NL bundles, accounting separately for missing embeddings"},
        "selection":{"rules":{"data_root":str(root),"legacy":"metadata/source-inventory.json article-bundle entries",
            "cyber":"All checksum-listed topics/cybercrime-nl/**/articles/*.zip including2020extension","retention":"permitted"}},
        "dossier_definition":{"unit":"One real-world event across publication times/reporting sources; registry creates no new accepted event dossiers"},
        "profile":{"mode":"exploratory","population_estimate":False,"purpose":"Engineering scale and retrieval coverage; no corpus event estimate"},
        "retrieval_profile":{"method":method}}
    for kind,content in definitions.items():
        versions[kind]=engine._version(session,context,{"kind":kind,"key":key,"content":content,"amend_latest":True,
            "reason":"Register full-corpus local vector-store scale method before source reads"})["id"]
    bound=Context(context.objective,context.actor,versions)
    binding=digest({"versions":versions,"plan":data["plan"],"group_result":data["group_result"],"root":str(root)})
    old=engine.ledger.db.execute("SELECT payload FROM records WHERE kind='event_vector_store_manifest' AND logical_key=?",(key,)).fetchall()
    if any(json.loads(row[0])["binding"]!=binding for row in old):
        raise ResearchError("Store key binds different inputs/implementation; use an explicit new snapshot version")
    manifest=engine.ledger.record(session,"event_vector_store_manifest",key,{"versions":versions,"binding":binding,"method":method,
        "inputs":{k:v for k,v in data.items() if k!="started_monotonic"},"started_at":utc()})
    engine.ledger.append(session,"event_store.build.intended",{"manifest":manifest,"binding":binding,"versions":versions})
    inventory=_inventory(engine,session,bound,root)
    fingerprint=digest({"legacy_inventory":inventory["legacy_inventory"],"cyber_checksums":inventory["cyber_checksums"],"bundles":inventory["bundles"]})
    inventory_ref=_save(engine,session,inventory,"Verified legacy+cybercrime inventory before catalog ingestion")
    completed=engine.ledger.db.execute("SELECT id FROM records WHERE kind='event_vector_store_result' AND logical_key=?",(key,)).fetchone()
    if completed:
        value=engine.ledger.get(completed[0],"event_vector_store_result")
        if value["inventory_fingerprint"]!=fingerprint:
            raise ResearchError("Input files changed; declare a new incremental snapshot key")
        engine.ledger.artifacts.verified_path(value["catalog"]["artifact"])
        engine.ledger.append(session,"event_store.snapshot.reused",{"result":completed[0],"catalog":value["catalog"]["artifact"]})
        return _present(engine,session,context,completed[0],value)
    inputs=_existing(engine,session,data["plan"],data["group_result"])
    versions["embedding_profile"]=inputs["spec"]["embedding_profile"]
    if shutil.disk_usage(engine.ledger.root).free < sum(b["bytes"] for b in inventory["bundles"])*15+2*1024**3:
        raise ResearchError("Insufficient free space for full registry and sealed snapshots")
    with tempfile.TemporaryDirectory(dir=engine.ledger.root,prefix="event-store-stage-") as staging:
        directory=Path(staging)
        catalog=_catalog(engine,session,root,inventory,inputs,directory,batch)
        article=store.build_index(catalog["article_ids"],inputs["pooled"][catalog["vector_rows"]],inputs["spec"],level="article")
        collective=centroids.build_centroids(inputs["groups"],[r["source_version"] for r in inputs["mapping"]],inputs["pooled"],inputs["metadata"])
        if any(row["status"]!="completed" for row in collective["rows"]):
            raise AuditError("Existing group-vector coverage is incomplete")
        group=store.build_index(collective["group_ids"],collective["centroids"],inputs["spec"],level="group")
        snapshots={}
        for level,handle in (("article",article),("group",group)):
            saved=_persist(engine,session,handle,directory/level)
            benchmark=_benchmark(saved.pop("restored"))
            snapshots[level+"_index"]={**saved,"count":len(handle["ids"]),"benchmark":benchmark}
        memberships=_save(engine,session,collective["rows"],"Exact current group memberships, body-deduplicated centroids and angular radii")
    queries=_queries(engine,session,versions,catalog["artifact"],inputs["spec"])
    value={"versions":versions,"manifest":manifest,"binding":binding,"method":METHOD,"inventory_artifact":inventory_ref,"inventory_fingerprint":fingerprint,
        "inventory":inventory,"catalog":{k:v for k,v in catalog.items() if k not in {"article_ids","vector_rows"}},**snapshots,
        "group_memberships":memberships,"spec":inputs["spec"],"queries":queries,
        "passage_vectors":inputs["passage_index"]["vector_count"],"original_passage_index":inputs["plan"]["index"],
        "actual_group_merges":0,"new_model_calls":0,"network_calls":0,"failed_rows":0,"pending_rows":0,
        "status":"full_catalog_ready_vector_coverage_partial","elapsed_seconds":time.perf_counter()-data.get("started_monotonic",time.perf_counter())}
    identifier=engine.ledger.record(session,"event_vector_store_result",key,value)
    return _present(engine,session,context,identifier,value)
