"""Offline, audited passage retrieval. Similarity never establishes event identity."""

from __future__ import annotations

import base64
from collections import defaultdict
from contextlib import contextmanager
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import TYPE_CHECKING, Any, Iterator

import faiss
import numpy as np

from .common import AuditError, Context, Json, ResearchError, digest, require_active
from .embeddings import validate_response

if TYPE_CHECKING:
    from .runtime import Research


METHOD: Json = {
    "method": "passage-candidates-hnsw-sq8-v1",
    "index": "Faiss IndexHNSWSQ; QT_8bit; inner product",
    "normalization": "L2 normalize retained float32 embeddings; cosine scores",
    "M": 16,
    "ef_construction": 80,
    "threads": 4,
    "training_rows": 16384,
    "training_selection": "Evenly spaced ordinals in the immutable embedding-plan order",
    "add_batch_rows": 4096,
    "ef_search": 128,
    "chunk_neighbors": 64,
    "article_pool": 40,
    "article_limit": 20,
    "evidence_limit": 3,
    "aggregation": "Maximum approximate passage score per other article; retain three distinct passage pairs; "
    "rerank the best forty articles using full precision cosine for those retained pairs; return twenty",
    "overlap_rule": "At most one match for each (query paragraph, target paragraph) pair",
    "filters": "Exclude same source; no language, publication-date or similarity-threshold filter",
    "provider_signal": "Exact populated eventUri equality; separately listed, uncapped, unconfirmed candidates",
    "missingness": "Retain every selected source; unindexed text is unprocessed, never a negative finding",
    "purpose": "Exploratory candidate retrieval, not event coreference, dossier assignment or measurement",
    "evaluation": "Deterministic sample of 32 indexed chunks; exact full-corpus cosine top-20 excluding "
    "same-source chunks; compare ANN top-64 after full-precision reranking. Recall is numerical, not event recall",
    "evaluation_seed": "candidate-index-check-v1",
    "evaluation_queries": 32,
    "evaluation_k": 20,
    "evaluation_tie_tolerance": 0.000001,
    "determinism": "Parallel HNSW construction can vary; exact saved index bytes and outputs are retained",
}


@contextmanager
def threads(count: int) -> Iterator[None]:
    previous = faiss.omp_get_max_threads()
    faiss.omp_set_num_threads(count)
    try:
        yield
    finally:
        faiss.omp_set_num_threads(previous)


def implementation(engine: Research) -> str:
    return digest(
        {k: v for k, v in engine.identity()["code_files"].items() if k.startswith("src/") or k == "uv.lock"}
    )


def save(engine: Research, session: str, value: Any, *, binary_file: bool = False) -> str:
    reference = engine.ledger.artifacts.put_file(value) if binary_file else engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": reference})
    return reference


def summary(identifier: str, record: Json) -> Json:
    return {
        "id": identifier,
        **{
            k: record[k]
            for k in (
                "versions",
                "context_artifact",
                "vector_count",
                "source_records",
                "indexed_sources",
                "text_unavailable_records",
                "dimensions",
                "network_calls",
                "model_calls",
            )
        },
    }


def build(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    plan = ledger.get(data["plan"], "embedding_plan")
    run = ledger.get(data["embedding_run"], "embedding_run")
    if context.versions != plan["versions"] or run["versions"] != plan["versions"]:
        raise ResearchError("Vector index requires the original embedding version bindings")
    if (
        run["plan"] != data["plan"]
        or run["missing_task_keys"]
        or run["completed_chunks"] != plan["expected_chunks"]
        or len(run["items"]) != len(plan["items"])
    ):
        raise ResearchError("Vector index requires a complete reconciled embedding run")
    profile = {
        **METHOD,
        "faiss_version": importlib.metadata.version("faiss-cpu"),
        "numpy_version": np.__version__,
    }
    registered = engine._version(
        session,
        context,
        {
            "kind": "retrieval_profile",
            "key": "passage-candidate-retrieval",
            "content": profile,
            "amend_latest": True,
            "reason": "Register offline index, candidate and numerical evaluation rules",
        },
    )
    versions = {**context.versions, "retrieval_profile": registered["id"]}
    key = digest(
        {
            "plan": data["plan"],
            "embedding_run": data["embedding_run"],
            "versions": versions,
            "implementation": implementation(engine),
        }
    )
    previous = ledger.db.execute(
        "SELECT id FROM records WHERE kind='vector_index' AND logical_key=?", (key,)
    ).fetchone()
    if previous:
        record = ledger.get(previous[0], "vector_index")
        ledger.append(session, "retrieval.index.reused", {"index": previous[0]})
        return summary(previous[0], record)
    count, dimensions = plan["expected_chunks"], plan["profile"]["dimensions"]
    if shutil.disk_usage(ledger.root).free < count * dimensions * 12 + 512 * 1024**2:
        raise ResearchError("Insufficient disk space for protected vectors, index and staging")
    allowed = set(ledger.get(versions["dataset"], "dataset")["source_versions"])
    rows: list[Json] = []
    seen: set[str] = set()
    # The full intended input manifest precedes binary construction and existing-result reuse.
    ledger.append(
        session,
        "retrieval.index.intended",
        {
            "key": key,
            "plan": data["plan"],
            "embedding_run": data["embedding_run"],
            "versions": versions,
            "expected_vectors": count,
        },
    )
    with tempfile.TemporaryDirectory(dir=ledger.root, prefix="index-stage-") as directory:
        raw_path = Path(directory) / "normalized.f32"
        with raw_path.open("wb") as output:
            for planned, completed in zip(plan["items"], run["items"], strict=True):
                if any(completed.get(k) != v for k, v in planned.items()) or completed["status"] not in {
                    "valid",
                    "cached",
                }:
                    raise ResearchError("Embedding run does not reconcile to its exact manifest")
                result = ledger.get(completed["result"], "embedding_result")
                if any(
                    result[k] != v
                    for k, v in {
                        "plan": data["plan"],
                        "task_key": planned["task_key"],
                        "request_ref": planned["request_ref"],
                        "versions": plan["versions"],
                    }.items()
                ):
                    raise ResearchError("Embedding result provenance differs from the plan")
                attempt = ledger.db.execute(
                    "SELECT 1 FROM attempts WHERE id=? AND result_id=? AND status='valid' AND task_key=?",
                    (result["attempt"], completed["result"], planned["task_key"]),
                ).fetchone()
                if not attempt or any(
                    x["task_key"] == planned["task_key"] for x in ledger.unresolved.values()
                ):
                    raise ResearchError("Embedding result lacks a completed valid attempt")
                request = ledger.artifacts.read(planned["request_ref"])
                if digest(request) != planned["task_key"] or request["versions"] != plan["versions"]:
                    raise AuditError("Embedding request identity mismatch")
                response = ledger.artifacts.read(result["raw_response_ref"])
                validate_response(request, response)
                vectors = sorted(response["data"], key=lambda item: item["index"])
                for chunk, vector in zip(request["chunks"], vectors, strict=True):
                    if chunk["id"] in seen or chunk["source_version"] not in allowed:
                        raise ResearchError("Duplicate or out-of-frame vector")
                    seen.add(chunk["id"])
                    values = np.frombuffer(base64.b64decode(vector["embedding"], validate=True), dtype="<f4")
                    norm = float(np.linalg.norm(values.astype(np.float64)))
                    if not np.isfinite(norm) or norm <= 0:
                        raise ResearchError("Invalid vector norm")
                    output.write((values / norm).astype("<f4").tobytes())
                    rows.append(chunk)
                ledger.append(
                    session,
                    "retrieval.embedding.reused",
                    {
                        "result": completed["result"],
                        "request": planned["request_ref"],
                        "vectors": len(vectors),
                    },
                )
        if len(rows) != count:
            raise ResearchError("Vector count differs from the complete embedding plan")
        if os.name != "nt":
            raw_path.chmod(0o600)
        raw_ref = save(engine, session, raw_path, binary_file=True)
        matrix = np.memmap(raw_path, mode="r", dtype="<f4", shape=(count, dimensions))
        try:
            training_ids = np.linspace(0, count - 1, min(count, profile["training_rows"]), dtype=np.int64)
            index = faiss.IndexHNSWSQ(
                dimensions,
                faiss.ScalarQuantizer.QT_8bit,  # type: ignore[arg-type]
                profile["M"],
                faiss.METRIC_INNER_PRODUCT,
            )
            index.hnsw.efConstruction = profile["ef_construction"]
            index.hnsw.efSearch = profile["ef_search"]
            with threads(profile["threads"]):
                index.train(np.asarray(matrix[training_ids], dtype=np.float32))
                for start in range(0, count, profile["add_batch_rows"]):
                    index.add(np.asarray(matrix[start : start + profile["add_batch_rows"]]))
                    ledger.append(
                        session,
                        "retrieval.index.progress",
                        {
                            "indexed_vectors": int(index.ntotal),
                            "expected_vectors": count,
                        },
                    )
            index_path = Path(directory) / "candidates.faiss"
            faiss.write_index(index, str(index_path))
            if os.name != "nt":
                index_path.chmod(0o600)
            index_ref = save(engine, session, index_path, binary_file=True)
            del index
        finally:
            getattr(matrix, "_mmap").close()
    rows_ref = save(engine, session, rows)
    indexed = {row["source_version"] for row in rows}
    sources = []
    for source_id in sorted(allowed):
        source = json.loads(
            ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source_id,)).fetchone()[0]
        )
        raw = source.get("raw_record", {})
        event = raw.get("eventUri")
        state = (
            "not_retained"
            if source.get("retention") == "metadata_only"
            else "absent"
            if "eventUri" not in raw
            else "null"
            if event is None
            else "invalid"
            if not isinstance(event, str)
            else "empty"
            if not event.strip()
            else "populated"
        )
        sources.append(
            {
                "source_version": source_id,
                "indexed": source_id in indexed,
                "event_uri_state": state,
                "event_uri": event if state == "populated" else None,
            }
        )
    context_ref = save(engine, session, {"versions": versions})
    record = {
        "plan": data["plan"],
        "embedding_run": data["embedding_run"],
        "versions": versions,
        "profile": profile,
        "implementation": implementation(engine),
        "context_artifact": context_ref,
        "index_artifact": index_ref,
        "vectors_artifact": raw_ref,
        "rows_artifact": rows_ref,
        "sources_artifact": save(engine, session, sources),
        "vector_count": count,
        "source_records": len(allowed),
        "indexed_sources": len(indexed),
        "dimensions": dimensions,
        "text_unavailable_records": plan["text_unavailable_records"],
        "network_calls": 0,
        "model_calls": 0,
        "layer": "retrieval representations; no event or dossier judgements",
    }
    identifier = ledger.record(session, "vector_index", key, record)
    return summary(identifier, record)


@contextmanager
def opened(engine: Research, context: Context, identifier: str) -> Iterator[Any]:
    record = engine.ledger.get(identifier, "vector_index")
    if context.versions != record["versions"]:
        raise ResearchError("Retrieval requires the exact index version bindings")
    profile = engine.ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"]
    if profile != record["profile"] or profile["method"] != METHOD["method"]:
        raise ResearchError("Retrieval profile differs from the saved index")
    artifacts = engine.ledger.artifacts
    index = faiss.read_index(str(artifacts.verified_path(record["index_artifact"])))
    rows = artifacts.read(record["rows_artifact"])
    path = artifacts.verified_path(record["vectors_artifact"])
    if (
        len(rows) != record["vector_count"]
        or index.ntotal != len(rows)
        or index.d != record["dimensions"]
        or index.metric_type != faiss.METRIC_INNER_PRODUCT
        or path.stat().st_size != len(rows) * index.d * 4
    ):
        raise AuditError("Saved index, mappings and full precision vectors differ")
    matrix = np.memmap(path, mode="r", dtype="<f4", shape=(len(rows), index.d))
    try:
        yield record, profile, index, rows, matrix
    finally:
        getattr(matrix, "_mmap").close()


def pair_key(pair: Json, rows: list[Json]) -> tuple[Any, ...]:
    return (-pair["approximate_score"], rows[pair["query_row"]]["id"], rows[pair["target_row"]]["id"])


def article_candidates(
    index: Any, matrix: Any, rows: list[Json], query_rows: list[int], profile: Json
) -> list[Json]:
    grouped: dict[str, dict[tuple[str, str], Json]] = defaultdict(dict)
    index.hnsw.efSearch = profile["ef_search"]
    # Bound temporary distance matrices even for unusually long articles.
    for start in range(0, len(query_rows), 128):
        query_ids = query_rows[start : start + 128]
        scores, neighbors = index.search(
            np.asarray(matrix[query_ids]), min(len(rows), profile["chunk_neighbors"])
        )
        for query_row, distances, targets in zip(query_ids, scores, neighbors, strict=True):
            for approximate, target in zip(distances, targets, strict=True):
                target = int(target)
                if target < 0 or rows[target]["source_version"] == rows[query_row]["source_version"]:
                    continue
                source = rows[target]["source_version"]
                key = (rows[query_row]["passage_id"], rows[target]["passage_id"])
                pair: Json = {
                    "query_row": query_row,
                    "target_row": target,
                    "approximate_score": float(approximate),
                }
                if key not in grouped[source] or pair_key(pair, rows) < pair_key(grouped[source][key], rows):
                    grouped[source][key] = pair
                    if len(grouped[source]) > profile["evidence_limit"]:
                        worst = max(grouped[source], key=lambda p: pair_key(grouped[source][p], rows))
                        del grouped[source][worst]
    ordered = sorted(
        grouped, key=lambda source: (min(pair_key(p, rows) for p in grouped[source].values()), source)
    )
    candidates = []
    for source in ordered[: profile["article_pool"]]:
        evidence = []
        for pair in sorted(grouped[source].values(), key=lambda p: pair_key(p, rows))[
            : profile["evidence_limit"]
        ]:
            left, right = pair["query_row"], pair["target_row"]
            score = float(np.dot(matrix[left], matrix[right]))
            evidence.append(
                {
                    "query_chunk": rows[left],
                    "target_chunk": rows[right],
                    "cosine": score,
                    "approximate_score": pair["approximate_score"],
                }
            )
        evidence.sort(key=lambda p: (-p["cosine"], p["query_chunk"]["id"], p["target_chunk"]["id"]))
        candidates.append(
            {
                "source_version": source,
                "score": evidence[0]["cosine"],
                "matches": evidence,
                "signal": "vector_similarity",
                "event_identity": "unassessed",
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["source_version"]))[
        : profile["article_limit"]
    ]


def search(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    with opened(engine, context, data["index"]) as (record, profile, index, rows, matrix):
        sources = engine.ledger.artifacts.read(record["sources_artifact"])
        source_map = {item["source_version"]: item for item in sources}
        requested = data.get("source_ids")
        if requested == "all":
            requested = sorted(source_map)
        if (
            not isinstance(requested, list)
            or not requested
            or len(set(requested)) != len(requested)
            or any(source not in source_map for source in requested)
        ):
            raise ResearchError("Select distinct source IDs in the index frame, or source_ids='all'")
        selection = data.get("limit")
        if selection is not None:
            if type(selection) is not int or selection < 1:
                raise ResearchError("A retrieval limit must be a positive integer")
            requested = requested[:selection]
        by_source: dict[str, list[int]] = defaultdict(list)
        provider_groups: dict[str, list[str]] = defaultdict(list)
        for ordinal, row in enumerate(rows):
            by_source[row["source_version"]].append(ordinal)
        for item in sources:
            if item["event_uri"] is not None:
                provider_groups[item["event_uri"]].append(item["source_version"])
        binding = {
            "index": data["index"],
            "versions": context.versions,
            "implementation": implementation(engine),
        }
        manifest = {
            **binding,
            "source_ids": requested,
            "profile": profile,
            "unselected_sources": len(source_map) - len(requested),
        }
        manifest_ref = save(engine, session, manifest)
        engine.ledger.append(session, "retrieval.search.intended", {"manifest": manifest_ref})
        results = []
        computed = reused = missing = vector_pairs = provider_pairs = 0
        with threads(profile["threads"]):
            for source in requested:
                key = digest({**binding, "source": source})
                previous = engine.ledger.db.execute(
                    "SELECT id FROM records WHERE kind='article_candidates' AND logical_key=?", (key,)
                ).fetchone()
                if previous:
                    result_id = previous[0]
                    result = engine.ledger.get(result_id, "article_candidates")
                    engine.ledger.append(session, "retrieval.result.reused", {"result": result_id})
                    reused += 1
                else:
                    candidates = article_candidates(index, matrix, rows, by_source[source], profile)
                    provider = [
                        peer
                        for peer in provider_groups.get(source_map[source]["event_uri"], [])
                        if peer != source
                    ]
                    result = {
                        **binding,
                        "source_version": source,
                        "query_chunks": len(by_source[source]),
                        "status": "searched" if by_source[source] else "unprocessed_text",
                        "vector_candidates": candidates,
                        "provider_candidates": provider,
                        "provider_signal": "exact_eventUri_equality; event identity unassessed",
                        "event_uri_state": source_map[source]["event_uri_state"],
                        "short_vector_result": bool(by_source[source])
                        and len(candidates) < profile["article_limit"],
                        "coverage": "Bounded approximate neighbors; no negative event judgements",
                    }
                    result_id = engine.ledger.record(session, "article_candidates", key, result)
                    computed += 1
                results.append(result_id)
                missing += result["status"] == "unprocessed_text"
                vector_pairs += len(result["vector_candidates"])
                provider_pairs += len(result["provider_candidates"])
                if len(results) == 1 or len(results) % 100 == 0:
                    engine.ledger.append(
                        session,
                        "retrieval.search.progress",
                        {
                            "completed_sources": len(results),
                            "expected_sources": len(requested),
                        },
                    )
        result = {
            **binding,
            "manifest": manifest_ref,
            "result_ids": results,
            "selected_sources": len(requested),
            "searched_sources": len(requested) - missing,
            "unprocessed_text_sources": missing,
            "unselected_sources": len(source_map) - len(requested),
            "new_results": computed,
            "reused_results": reused,
            "directed_vector_candidates": vector_pairs,
            "directed_provider_candidates": provider_pairs,
            "counting_unit": "Directed retrieval candidates; overlapping signals, not events or dossiers",
            "network_calls": 0,
            "model_calls": 0,
        }
        identifier = engine.ledger.record(session, "candidate_run", digest(manifest), result)
        return {"id": identifier, **{k: v for k, v in result.items() if k != "result_ids"}}


def evaluate(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    with opened(engine, context, data["index"]) as (record, profile, index, rows, matrix):
        selected = sorted(
            range(len(rows)),
            key=lambda n: hashlib.sha256((profile["evaluation_seed"] + rows[n]["id"]).encode()).digest(),
        )[: profile["evaluation_queries"]]
        manifest = {
            "index": data["index"],
            "query_rows": selected,
            "versions": context.versions,
            "profile": profile,
            "purpose": "Numerical ANN check, not human-labelled event evaluation",
        }
        manifest_ref = save(engine, session, manifest)
        engine.ledger.append(session, "retrieval.evaluation.intended", {"manifest": manifest_ref})
        query = np.asarray(matrix[selected])
        k = min(profile["evaluation_k"], len(rows))
        exact_scores = np.full((len(selected), k), -np.inf, dtype=np.float32)
        exact_ids = np.full((len(selected), k), -1, dtype=np.int64)
        source_ids = np.array([row["source_version"] for row in rows])
        # Small exact indexes keep memory bounded and provide an independent exhaustive baseline.
        with threads(profile["threads"]):
            for start in range(0, len(rows), 4096):
                block = np.asarray(matrix[start : start + 4096])
                local_sources = source_ids[start : start + len(block)]
                extra = max(
                    int(np.count_nonzero(local_sources == rows[n]["source_version"])) for n in selected
                )
                flat = faiss.IndexFlatIP(index.d)
                flat.add(block)
                distances, ids = flat.search(query, min(len(block), k + extra))
                ids += start
                for q in range(len(query)):
                    distances[q, source_ids[ids[q]] == rows[selected[q]]["source_version"]] = -np.inf
                    scores = np.concatenate((exact_scores[q], distances[q]))
                    ordinals = np.concatenate((exact_ids[q], ids[q]))
                    order = np.lexsort((ordinals, -scores))[:k]
                    exact_scores[q], exact_ids[q] = scores[order], ordinals[order]
                del flat
            index.hnsw.efSearch = profile["ef_search"]
            _, approximate_ids = index.search(query, min(len(rows), profile["chunk_neighbors"]))
        items = []
        hits = tie_hits = expected = 0
        for q, query_id in enumerate(selected):
            exact = [
                (int(n), float(s))
                for n, s in zip(exact_ids[q], exact_scores[q], strict=True)
                if n >= 0 and np.isfinite(s)
            ]
            candidates = [
                int(n)
                for n in approximate_ids[q]
                if n >= 0 and rows[n]["source_version"] != rows[query_id]["source_version"]
            ]
            reranked = sorted(
                ((n, float(np.dot(matrix[query_id], matrix[n]))) for n in candidates),
                key=lambda item: (-item[1], item[0]),
            )[:k]
            overlap = len({n for n, _ in exact} & {n for n, _ in reranked})
            tied = (
                sum(s >= exact[-1][1] - profile["evaluation_tie_tolerance"] for _, s in reranked)
                if exact
                else 0
            )
            hits += overlap
            tie_hits += min(tied, len(exact))
            expected += len(exact)
            items.append(
                {
                    "query_chunk": rows[query_id],
                    "exact": exact,
                    "retrieved": reranked,
                    "hits": overlap,
                    "tie_aware_hits": min(tied, len(exact)),
                    "expected": len(exact),
                }
            )
        record = {
            "index": data["index"],
            "versions": context.versions,
            "manifest": manifest_ref,
            "details_artifact": save(engine, session, items),
            "queries": len(selected),
            "expected_neighbors": expected,
            "retrieved_exact_neighbors": hits,
            "recall_at_k": hits / expected if expected else None,
            "tie_aware_recall_at_k": tie_hits / expected if expected else None,
            "k": k,
            "scope": "Exploratory numerical search recall only; semantic/event recall unmeasured",
            "network_calls": 0,
            "model_calls": 0,
        }
        identifier = engine.ledger.record(session, "retrieval_evaluation", digest(manifest), record)
        return {"id": identifier, **record}


def inspect_candidates(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    run = engine.ledger.get(data["run"], "candidate_run")
    if context.versions != run["versions"]:
        raise ResearchError("Candidate inspection requires the run's exact version bindings")
    requested = data.get("source_ids")
    if requested is not None and (
        not isinstance(requested, list) or not requested or len(set(requested)) != len(requested)
    ):
        raise ResearchError("Candidate inspection requires distinct source IDs")
    limit = data.get("limit", 10)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ResearchError("Candidate inspection limit must be between 1 and 100")
    wanted = set(requested) if requested is not None else None
    selected: list[Json] = []
    found = set()
    for identifier in run["result_ids"]:
        item = engine.ledger.get(identifier, "article_candidates")
        source = item["source_version"]
        if wanted is None or source in wanted:
            found.add(source)
            if len(selected) < limit:
                selected.append({"id": identifier, **item})
        if wanted is None and len(selected) == limit:
            break
    if wanted is not None and found != wanted:
        raise ResearchError("Requested source has no result in this candidate run")
    return {
        "run": data["run"],
        "results": selected,
        "returned_sources": len(selected),
        "truncated": len(found) > len(selected) if wanted is not None else len(run["result_ids"]) > limit,
        "scope": "Stored exploratory candidates; passage IDs can be supplied to audited inspect",
    }
