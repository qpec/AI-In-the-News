"""Audited local evaluation of the pinned AWS sample; no cloud/model calls."""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
import importlib.metadata
import json
import time
from typing import TYPE_CHECKING, Any, Iterator

import numpy as np

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "aws-dbscan-saved-passage-pilot-v1"
DEFAULT_LIMIT = 1000
MAX_LIMIT = 2000
CHECKPOINT_TAG = "codex/embedding-progress-20261015"


def register(engine: Research, session: str, context: Context, kind: str, key: str, content: Json) -> str:
    return str(engine._version(session, context, {"kind": kind, "key": key, "content": content,
        "amend_latest": True, "reason": "Register the archived-input AWS clustering evaluation before execution"})["id"])


@contextmanager
def vectors(engine: Research, session: str, index: Json) -> Iterator[tuple[list[Json], Any]]:
    """Check retained matrix/mapping without loading the unused Faiss graph."""
    require_active(engine, session)
    from .retrieval import METHOD as retrieval_method
    profile = engine.ledger.get(index["versions"]["retrieval_profile"], "retrieval_profile")["content"]
    if profile != index["profile"] or profile["method"] != retrieval_method["method"]:
        raise AuditError("Original vector-index method bindings differ")
    rows = engine.ledger.artifacts.read(index["rows_artifact"])
    path = engine.ledger.artifacts.verified_path(index["vectors_artifact"])
    count, dimensions = index["vector_count"], index["dimensions"]
    if not isinstance(rows, list) or len(rows) != count or path.stat().st_size != count * dimensions * 4:
        raise AuditError("Original vector matrix and row mapping differ")
    matrix = np.memmap(path, mode="r", dtype="<f4", shape=(count, dimensions))
    try:
        yield rows, matrix
    finally:
        getattr(matrix, "_mmap").close()


def aggregate(rows: list[Json], matrix: Any, selected: list[str]) -> tuple[list[str], np.ndarray, list[Json], list[Json]]:
    """Declared adaptation: normalize the mean of all retained passage windows."""
    wanted = set(selected)
    sums: dict[str, Any] = {}
    chunks: dict[str, list[Json]] = defaultdict(list)
    for ordinal, row in enumerate(rows):
        source = row["source_version"]
        if source not in wanted:
            continue
        vector = np.asarray(matrix[ordinal], dtype=np.float64)
        if not np.all(np.isfinite(vector)) or not np.isclose(np.linalg.norm(vector), 1, atol=1e-4):
            raise AuditError("Retained passage vector is not finite and normalized")
        sums[source] = sums.get(source, np.zeros(matrix.shape[1], dtype=np.float64)) + vector
        chunks[source].append({"row": ordinal, "chunk": row["id"], "passage": row["passage_id"]})
    ids, output, missing, mapping = [], [], [], []
    for source in selected:
        total = sums.get(source)
        if total is None or np.linalg.norm(total) < 1e-12:
            missing.append({"source_version": source, "reason": "no_saved_vectors" if total is None else "zero_pooled_vector"})
            continue
        ids.append(source)
        output.append(total / np.linalg.norm(total))
        mapping.append({"source_version": source, "chunks": chunks[source], "chunk_count": len(chunks[source])})
    return ids, np.asarray(output, dtype=np.float32).reshape((-1, matrix.shape[1])), missing, mapping


def _summary(output: Json) -> Json:
    groups = [group for group in output.get("partition", []) if len(group) > 1]
    return {"groups": len(groups), "grouped_articles": len({item for group in groups for item in group}),
        "grouped_memberships": sum(len(g) for g in groups),
        "unemitted_ids": len(output.get("coverage", {}).get("never_emitted_ids", []))
            if "coverage" in output else None,
        "singletons": len(output.get("singletons", [])), "complete": output.get("complete"),
        "coverage": output.get("coverage"), "errors": output.get("errors", [])}


def pack_centroids(engine: Research, session: str, output: Json) -> None:
    """Retain exact centroid values once per pool state, outside JSON payloads."""
    require_active(engine, session)
    visited_pools: set[int] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                if name in {"pool", "mutated_failure_pool"} and isinstance(child, list) and child:
                    if id(child) in visited_pools:
                        continue
                    visited_pools.add(id(child))
                    matrix = np.asarray([entry["centroid"] for entry in child], dtype="<f8")
                    if matrix.ndim != 2 or not np.isfinite(matrix).all():
                        raise AuditError("Cannot retain invalid upstream centroid state")
                    artifact = engine.ledger.artifacts.put_bytes(matrix.tobytes())
                    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": artifact,
                        "purpose": "Exact upstream pool centroid state", "dtype": "<f8", "shape": list(matrix.shape)})
                    for row, entry in enumerate(child):
                        entry["centroid"] = {"artifact": artifact, "row": row,
                            "dtype": "<f8", "shape": list(matrix.shape)}
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(output)


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"reference_result", "index", "limit", "seed", "key"}:
        raise ResearchError("Unsupported AWS evaluation fields; no cloud/model execution is available")
    if bool(data.get("index")) == bool(data.get("reference_result")):
        raise ResearchError("Select exactly one immutable saved index or RAG result anchor")
    limit = data.get("limit", DEFAULT_LIMIT)
    if type(limit) is not int or not 2 <= limit <= MAX_LIMIT:
        raise ResearchError("The local clustering pilot must select 2 through 2000 articles")
    seed = data.get("seed", "aws-event-pilot-20261015-v1")
    if not isinstance(seed, str) or not seed.strip() or len(seed) > 128:
        raise ResearchError("Declare a bounded fixed pilot seed")
    key = data.get("key", METHOD)
    if not isinstance(key, str) or not key.strip():
        raise ResearchError("Declare an evaluation key")
    ledger = engine.ledger
    index_id = data.get("index")
    if data.get("reference_result"):
        reference = ledger.get(data["reference_result"], "rag_query_result")
        score = ledger.get(reference["scores"], "article_query_run")
        index_id = score["index"]
    if not isinstance(index_id, str) or not index_id:
        raise ResearchError("The saved index anchor must be an immutable ID")
    index = ledger.get(index_id, "vector_index")
    for kind, identifier in context.versions.items():
        if index["versions"].get(kind) != identifier:
            raise ResearchError("Caller context differs from the original saved index")
    bound = Context(context.objective, context.actor, dict(index["versions"]))
    ledger.append(session, "aws_evaluation.context.bound", {"index": index_id,
        "reference_result": data.get("reference_result"), "input_index_versions": bound.versions})
    from .aws_clustering_core import load_upstream, offline_baseline, synthetic_probes
    runner = load_upstream()
    versions = dict(bound.versions)
    versions["protocol"] = register(engine, session, bound, "protocol", METHOD, {
        "method": METHOD, "upstream": runner.manifest, "offline": True,
        "representation": "L2-normalized sum of all saved unit passage-window vectors per article, float32",
        "representation_limitations": "Not the AWS title/summary/body embedding; overlapping windows and longer passages get repeated weight; multi-event articles collapse into one vector",
        "pilot": "Hash-ranked source-version SRS without replacement, selected before vector availability checks",
        "execution": "Pinned upstream core, one batch and consecutive batches of 500; full-precision offline baseline at eps .10/.20/.30",
        "centroid_retention": "Exact little-endian float64 matrices per pool state; JSON keeps artifact/row/shape references, with content-addressed deduplication",
        "limits": "At most 2000 selected articles; no hard whole-process memory cap; row mapping remains corpus-sized",
        "interpretation": "Exploratory unvalidated cluster candidates only; no semantic accuracy or event-count claim",
        "models": "No new embedding, LLM, AWS or summarization call"})
    versions["question"] = register(engine, session, bound, "question", key, {
        "text": "Does the pinned AWS clustering core preserve memberships and provide usable candidates for same-event dossiers using retained vectors?"})
    versions["selection"] = register(engine, session, bound, "selection", key, {"rules": {
        "dataset": bound.versions["dataset"], "limit": limit, "seed": seed,
        "ranking": "SHA256(canonical({seed,source_version})), then source_version",
        "replacement": False, "missing": "Selected sources without valid vectors remain unprocessed"}})
    versions["dossier_definition"] = register(engine, session, bound, "dossier_definition", key, {
        "unit": "One real-world event across reporting sources and publication times; candidate clusters are not confirmed dossiers"})
    versions["profile"] = register(engine, session, bound, "profile", key, {
        "mode": "exploratory", "population_estimate": False, "method": METHOD,
        "evaluation": "Synthetic engineering probes and unlabelled real-vector structure; human same-event gold unavailable"})
    result_context = Context(context.objective, context.actor, versions)
    dataset = ledger.get(bound.versions["dataset"], "dataset")
    all_sources = dataset["source_versions"]
    ordered = sorted(all_sources, key=lambda source: (digest({"seed": seed, "source_version": source}), source))
    selected, excluded = ordered[:limit], ordered[limit:]
    checkpoint = {"versions": versions, "archive_tag": CHECKPOINT_TAG, "index": index_id,
        "input_index_versions": bound.versions, "embedding_plan": index["plan"], "embedding_run": index["embedding_run"],
        "dataset": bound.versions["dataset"], "retained_artifacts": {name: index[name] for name in
            ("index_artifact", "vectors_artifact", "rows_artifact", "sources_artifact")},
        "preservation": "Additive checkpoint; no source/vector/index/audit deletion, move, overwrite or new embedding",
        "backup": "No independent physical backup created", "recorded_at": utc()}
    checkpoint_id = ledger.record(session, "embedding_checkpoint_result", key, checkpoint)
    source_refs = {}
    for name, content in runner.source_payloads.items():
        source_refs[name] = ledger.artifacts.put_bytes(content)
        ledger.append(session, "preparation.artifact.saved", {"artifact": source_refs[name], "name": name,
            "purpose": "Pinned reviewed upstream clustering source"})
    manifest = {"versions": versions, "input_index_versions": bound.versions, "index": index_id,
        "checkpoint": checkpoint_id, "upstream": runner.manifest, "source_artifacts": source_refs,
        "selected_sources": selected, "excluded_sources": excluded, "seed": seed,
        "source_count": len(all_sources), "selected_count": len(selected),
        "library_versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn", "joblib")},
        "started_at": utc(), "model_calls": 0, "network_calls": 0}
    manifest_id = ledger.record(session, "aws_clustering_manifest", key, manifest)
    ledger.append(session, "aws_evaluation.intended", {"manifest": manifest_id, "versions": versions})
    probes = synthetic_probes(runner)
    with vectors(engine, session, index) as (rows, matrix):
        ids, pooled, missing, mapping = aggregate(rows, matrix, selected)
    pooled_artifact = ledger.artifacts.put_bytes(pooled.astype("<f4").tobytes())
    mapping_artifact = ledger.artifacts.put(mapping)
    for artifact in (pooled_artifact, mapping_artifact):
        ledger.append(session, "preparation.artifact.saved", {"artifact": artifact,
            "purpose": "Retained derived article-vector input and mapping"})
    ledger.append(session, "aws_evaluation.vectors.prepared", {"artifact": pooled_artifact,
        "mapping_artifact": mapping_artifact, "manifest": manifest_id, "shape": list(pooled.shape), "missing": missing})
    outputs: dict[str, Json] = {}
    timings: dict[str, float] = {}
    mode_artifacts: dict[str, str] = {}

    def retain_mode(name: str) -> None:
        artifact = ledger.artifacts.put(outputs[name])
        ledger.append(session, "preparation.artifact.saved", {"artifact": artifact,
            "purpose": "Completed clustering mode output", "manifest": manifest_id, "mode": name})
        ledger.append(session, "aws_evaluation.mode.completed", {"artifact": artifact,
            "manifest": manifest_id, "mode": name, "fit_seconds": timings[name], "summary": _summary(outputs[name])})
        mode_artifacts[name] = artifact

    if len(ids) >= 2:
        schedules = {"upstream_one_batch": [len(ids)], "upstream_streaming_500":
            [min(500, len(ids) - start) for start in range(0, len(ids), 500)]}
        for name, sizes in schedules.items():
            begin = time.perf_counter()
            outputs[name] = runner.run_batches(pooled, ids, sizes)
            timings[name] = time.perf_counter() - begin
            pack_centroids(engine, session, outputs[name])
            retain_mode(name)
        for eps in (.10, .20, .30):
            name = f"baseline_float64_eps_{eps:.2f}"
            begin = time.perf_counter()
            outputs[name] = offline_baseline(pooled, ids, eps=eps)
            timings[name] = time.perf_counter() - begin
            retain_mode(name)
    # Copy metadata only, through the active runtime. No native article judging.
    metadata_sql = "SELECT id,payload FROM sources WHERE id IN (SELECT value FROM json_each(?))"
    metadata_parameters = [canonical(selected)]
    metadata = {row["id"]: json.loads(row["payload"]) for row in ledger.db.execute(metadata_sql, metadata_parameters)}
    ledger.append(session, "aws_evaluation.metadata.inspected", {"sql": metadata_sql,
        "parameters": metadata_parameters, "source_ids": selected,
        "observation": "Copied stored source metadata for the candidate overview; no body/passage judgement"})
    examples = {}
    for name, output in outputs.items():
        groups = sorted((group for group in output.get("partition", []) if len(group) > 1),
            key=lambda group: (-len(group), sorted(group)))
        examples[name] = [{"candidate_id": digest({"manifest": manifest_id, "mode": name, "members": sorted(group)}),
            "members": [{"source_version": source, "title": metadata[source].get("title"),
                "url": metadata[source].get("url"), "published_at": metadata[source].get("published_at")} for source in group]}
            for group in groups[:5]]
    result = {"versions": versions, "input_index_versions": bound.versions, "index": index_id,
        "manifest": manifest_id, "checkpoint": checkpoint_id, "upstream": runner.manifest,
        "dataset_articles": len(all_sources), "selected_articles": len(selected), "processed_articles": len(ids),
        "missing_articles": len(missing), "missing": missing, "excluded_articles": len(excluded),
        "pooled_vectors_artifact": pooled_artifact, "mapping_artifact": mapping_artifact,
        "synthetic_probes": probes, "outputs": outputs, "summaries": {name: _summary(out) for name, out in outputs.items()},
        "fit_seconds": timings, "mode_artifacts": mode_artifacts,
        "examples": examples, "model_calls": 0, "new_embedding_requests": 0,
        "network_calls": 0, "aws_resources_created": 0, "summarization": "not_executed",
        "human_event_labels": 0, "event_accuracy": None, "accepted_dossiers": 0,
        "pending_articles": max((out.get("coverage", {}).get("pending_input_occurrences", 0)
            for out in outputs.values()), default=0),
        "failed_modes": [name for name, out in outputs.items() if not out.get("complete")],
        "status": "insufficient_vectors" if not outputs else
            "partial" if any(not out.get("complete") for out in outputs.values()) else "completed",
        "started_at": manifest["started_at"], "completed_at": utc(),
        "limitations": "Hash-sampled unlabelled pilot; representation adapted; epsilon sensitivity is not calibration; no true-event count established"}
    identifier = ledger.record(session, "aws_clustering_evaluation", manifest_id, result)
    from .presentation import record
    presentation = record(engine, session, result_context, {"results": [
        {"kind": "aws_clustering_evaluation", "id": identifier}, {"kind": "embedding_checkpoint_result", "id": checkpoint_id}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    from .provisional_tags import literal
    from urllib.parse import quote, urlsplit
    lines = ["### AWS clustering evaluation", "", f"Pilot: {result['selected_articles']} selected articles from "
        f"{result['dataset_articles']}; {result['processed_articles']} with pooled saved vectors; "
        f"{result['missing_articles']} unprocessed; {result['excluded_articles']} outside the pilot. "
        f"Pending: {result['pending_articles']}.", "", "| Mode | Candidate groups | Grouped articles | Singletons | Complete |",
        "|---|---:|---:|---:|---|"]
    for name, summary in result["summaries"].items():
        lines.append(f"| {name} | {summary['groups']} | {summary['grouped_articles']} | {summary['singletons']} | {summary['complete']} |")
    lines += ["", "Upstream uses eps 0.10 cosine distance and min_samples 2. The float64 baselines at "
        "0.10/0.20/0.30 are declared sensitivity tests, not validated cutoffs. Passage pooling differs from the "
        "AWS article embedding. Noise/singletons and missing vectors are not negative event findings.", "",
        "Captured upstream delta omissions: " + "; ".join(f"{name}: {summary['unemitted_ids']} IDs not emitted"
            for name, summary in result["summaries"].items() if summary["unemitted_ids"] is not None) +
        ". These are returned-delta diagnostics, not a deployed database test.", "",
        "Synthetic engineering probes:"]
    for probe in result["synthetic_probes"]:
        out = probe["upstream"]
        observed = {"batches": out["batch_sizes"], "partition": out["partition"],
            "errors": [e["error_type"] for e in out["errors"]],
            "never_emitted": out["coverage"]["never_emitted_ids"],
            "duplicate_memberships": out["coverage"]["duplicate_pool_ids"]}
        lines.append("- " + literal(probe["name"]) + ": " + literal(json.dumps(observed, separators=(",", ":"))))
    for name, groups in result["examples"].items():
        lines += ["", "Candidate examples — " + literal(name) + ":"]
        if not groups:
            lines.append("No multi-article groups at this setting.")
        for group in groups[:1]:
            lines.append(f"- Candidate `{group['candidate_id'][:12]}`: {len(group['members'])} articles.")
            for member in group["members"][:3]:
                title = literal(member.get("title") or member["source_version"])
                url = member.get("url")
                try:
                    if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).netloc:
                        title = f"[{title}]({quote(url, safe=':/?#=&%+-._~')})"
                except ValueError:
                    pass
                lines.append("  - " + title)
    lines += ["", "No new embeddings, LLM calls, AWS resources or summaries. Human same-event labels: 0; "
        "event accuracy unmeasured; accepted event dossiers: 0. Existing data/vectors and audit foundation retained. "
        "This is a technical clustering pilot, not a count of true events. The sample needs correction and "
        "independent same-event evaluation before it can support trusted event counts."]
    return "\n".join(lines)
