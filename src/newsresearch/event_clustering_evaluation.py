"""Audited same-input comparison of corrected, still-unvalidated vector groups."""
from __future__ import annotations

import importlib.metadata
import json
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

import numpy as np

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "retained-event-vector-comparison-v1"
MODES: list[Json] = [
    {"name": "retained_batch_0.10", "strategy": "dbscan", "eps": .10, "batch": 2000, "reverse": False},
    {"name": "retained_stream_0.10", "strategy": "dbscan", "eps": .10, "batch": 500, "reverse": False},
    {"name": "retained_reverse_0.10", "strategy": "dbscan", "eps": .10, "batch": 500, "reverse": True},
    *[{"name": f"compact_complete_link_{eps:.2f}", "strategy": "complete", "eps": eps,
       "batch": 2000, "reverse": False} for eps in (.10, .20, .30)],
]


def partition_key(output: Json) -> list[list[str]]:
    return sorted((sorted(group) for group in output["partition"]), key=tuple)


def summary(output: Json) -> Json:
    groups = [group for group in output["partition"] if len(group) > 1]
    coverage = output["coverage"]
    return {"groups": len(groups), "grouped_articles": sum(map(len, groups)),
        "singletons": len(output["singletons"]), "largest_group": max(map(len, groups), default=0),
        "max_within_cosine_distance": output["max_within_cosine_distance"],
        "groups_beyond_eps": sum(not group["within_eps"] for group in output["groups"]),
        "unemitted_ids": len(coverage["never_emitted_ids"]),
        "pending": coverage["pending_input_occurrences"], "complete": output["complete"],
        "errors": output["errors"]}


def saved_inputs(engine: Research, session: str, previous_id: str) -> tuple[Json, Json, list[str], Any]:
    """Reuse exact prior artifacts, checking coverage and immutable lineage."""
    require_active(engine, session)
    ledger = engine.ledger
    previous = ledger.get(previous_id, "aws_clustering_evaluation")
    manifest = ledger.get(previous["manifest"], "aws_clustering_manifest")
    index = ledger.get(previous["index"], "vector_index")
    checkpoint = ledger.get(previous["checkpoint"], "embedding_checkpoint_result")
    if (manifest["index"] != previous["index"] or manifest["versions"] != previous["versions"]
            or previous["input_index_versions"] != index["versions"]
            or manifest["input_index_versions"] != index["versions"]
            or checkpoint["index"] != previous["index"] or checkpoint["embedding_plan"] != index["plan"]
            or checkpoint["embedding_run"] != index["embedding_run"]
            or previous["versions"]["dataset"] != index["versions"]["dataset"]):
        raise AuditError("Prior comparison and original embedding lineage differ")
    dataset = ledger.get(index["versions"]["dataset"], "dataset")
    selected, excluded = manifest["selected_sources"], manifest["excluded_sources"]
    mapping = ledger.artifacts.read(previous["mapping_artifact"])
    ids = [row["source_version"] for row in mapping]
    missing = [row["source_version"] for row in previous["missing"]]
    if (not 2 <= len(selected) <= 2000 or len(set(selected + excluded)) != len(selected + excluded)
            or set(selected + excluded) != set(dataset["source_versions"])
            or previous["dataset_articles"] != len(dataset["source_versions"])
            or previous["selected_articles"] != len(selected)
            or previous["excluded_articles"] != len(excluded)
            or previous["processed_articles"] != len(ids) or previous["missing_articles"] != len(missing)
            or len(set(ids + missing)) != len(ids + missing) or set(ids + missing) != set(selected)
            or ids != [source for source in selected if source not in set(missing)]
            or any(row["chunk_count"] != len(row["chunks"]) or not row["chunks"] for row in mapping)):
        raise AuditError("Prior selection, vector mapping and missing coverage differ")
    dimensions = index["dimensions"]
    raw = ledger.artifacts.read_bytes(previous["pooled_vectors_artifact"])
    if not 1 <= dimensions <= 8192 or len(raw) != len(ids) * dimensions * 4:
        raise AuditError("Prior pooled vector artifact shape differs")
    values = np.frombuffer(raw, dtype="<f4").reshape((len(ids), dimensions))
    if not np.isfinite(values).all() or (len(ids) and not np.allclose(np.linalg.norm(values, axis=1), 1, atol=1e-4)):
        raise AuditError("Prior pooled vectors must be finite unit vectors")
    return previous, manifest, ids, values


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"previous_result", "key"} or not isinstance(data.get("previous_result"), str):
        raise ResearchError("Declare one immutable previous AWS evaluation; no new selection or model run is available")
    previous_id = data["previous_result"]
    previous, previous_manifest, ids, values = saved_inputs(engine, session, previous_id)
    if any(previous["versions"].get(kind) != identifier for kind, identifier in context.versions.items()):
        raise ResearchError("Comparison context differs from the previous evaluation")
    ledger = engine.ledger
    key = data.get("key", METHOD)
    if not isinstance(key, str) or not key.strip():
        raise ResearchError("Declare a comparison key")
    bound = Context(context.objective, context.actor, dict(previous["versions"]))
    versions = dict(bound.versions)

    def register(kind: str, content: Json) -> None:
        versions[kind] = engine._version(session, bound, {"kind": kind, "key": key, "content": content,
            "amend_latest": True, "reason": "Register a separate corrected-vector comparison; preserve the AWS control"})["id"]

    register("protocol", {"method": METHOD, "previous_result": previous_id, "modes": MODES,
        "inputs": "Explicit exact-version reuse of prior pooled float32 vectors, mapping, selection and missingness; no reaggregation/resampling",
        "retained_dbscan": "Retain all original vectors, sort IDs before float64 cosine DBSCAN min_samples=2 at every batch; full snapshots/assignments and merge/split lineage",
        "complete_link": "Deterministic ID-sorted complete linkage at fixed distance cuts; check all-pairs diameter, no event-identity acceptance",
        "limits": "At most 2000 selected articles; dense all-pairs reference; no whole-process memory cap or production scalability claim",
        "comparison": "Final partition agreement against preserved control/baseline; full memberships and maximum within-group distances",
        "interpretation": "Exploratory geometry/coverage only; no calibrated cutoff, human labels, accepted dossiers or semantic accuracy",
        "models": "No new embedding, model, network, collection or AWS call"})
    register("question", {"text": "Do retained-vector snapshots correct the AWS membership/order problems, and does complete linkage bound candidate-group diameter on the same inputs?"})
    register("profile", {"mode": "exploratory", "population_estimate": False,
        "method": METHOD, "event_accuracy": "Unmeasured; independent held-out human review required"})
    result_context = Context(context.objective, context.actor, versions)
    manifest = {"versions": versions, "previous_result": previous_id, "previous_manifest": previous["manifest"],
        "input_index_versions": previous["input_index_versions"], "index": previous["index"],
        "pooled_vectors_artifact": previous["pooled_vectors_artifact"], "mapping_artifact": previous["mapping_artifact"],
        "selected_sources": previous_manifest["selected_sources"], "processed_sources": ids,
        "missing": previous["missing"], "modes": MODES, "shape": list(values.shape), "dtype": "<f4",
        "library_versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "scikit-learn")},
        "started_at": utc(), "model_calls": 0}
    manifest_id = ledger.record(session, "event_clustering_manifest", key, manifest)
    ledger.append(session, "event_clustering.intended", {"manifest": manifest_id, "versions": versions})
    ledger.append(session, "event_clustering.inputs.reused", {"manifest": manifest_id,
        "previous_result": previous_id, "artifacts": [previous["pooled_vectors_artifact"], previous["mapping_artifact"]],
        "versions": previous["versions"], "shape": list(values.shape), "reaggregation": False})
    from .event_clustering_core import complete_link, retained_dbscan
    outputs: dict[str, Json] = {}
    mode_artifacts: dict[str, str] = {}
    timings: dict[str, float] = {}
    if len(ids) >= 2:
        for mode in MODES:
            name = mode["name"]
            begin = time.perf_counter()
            if mode["strategy"] == "complete":
                output = complete_link(values, ids, eps=mode["eps"])
            else:
                ordered_ids, ordered_values = (ids[::-1], values[::-1]) if mode["reverse"] else (ids, values)
                sizes = [min(mode["batch"], len(ids) - start) for start in range(0, len(ids), mode["batch"])]
                output = retained_dbscan(ordered_values, ordered_ids, sizes, eps=mode["eps"])
            timings[name] = time.perf_counter() - begin
            outputs[name] = output
            mode_artifacts[name] = ledger.artifacts.put(output)
            ledger.append(session, "preparation.artifact.saved", {"artifact": mode_artifacts[name],
                "purpose": "Corrected event-vector mode output", "manifest": manifest_id, "mode": name})
            ledger.append(session, "event_clustering.mode.completed", {"manifest": manifest_id, "mode": name,
                "artifact": mode_artifacts[name], "summary": summary(output), "fit_seconds": timings[name]})
    comparisons = {}
    reference = outputs.get("retained_batch_0.10")
    if reference and reference["complete"]:
        reference_partition = partition_key(reference)
        for name, output in outputs.items():
            if name.startswith("retained_"):
                comparisons[name] = partition_key(output) == reference_partition if output["complete"] else None
        for name in ("upstream_one_batch", "upstream_streaming_500", "baseline_float64_eps_0.10"):
            old = previous["outputs"].get(name)
            comparisons["previous_" + name] = partition_key(old) == reference_partition if old and old["complete"] else None
    metadata_sql = "SELECT id,payload FROM sources WHERE id IN (SELECT value FROM json_each(?))"
    parameters = [canonical(ids)]
    metadata = {row["id"]: json.loads(row["payload"]) for row in ledger.db.execute(metadata_sql, parameters)}
    if set(metadata) != set(ids):
        raise AuditError("Candidate metadata coverage differs from the original sources")
    ledger.append(session, "event_clustering.metadata.inspected", {"sql": metadata_sql, "parameters": parameters,
        "source_ids": ids, "observation": "Stored title/URL/publication metadata copied; no event-date inference or article judging"})
    examples = {}
    for name, output in outputs.items():
        groups = sorted((group for group in output["groups"] if len(group["members"]) > 1),
            key=lambda group: (-len(group["members"]), group["candidate_id"]))
        examples[name] = [{"candidate_id": group["candidate_id"], "max_distance": group["max_within_cosine_distance"],
            "members": [{"source_version": source, "title": metadata[source].get("title"),
                "url": metadata[source].get("url"), "published_at": metadata[source].get("published_at")}
                for source in group["members"]]} for group in groups[:3]]
    result = {"versions": versions, "manifest": manifest_id, "previous_result": previous_id,
        "index": previous["index"], "input_index_versions": previous["input_index_versions"],
        "pooled_vectors_artifact": previous["pooled_vectors_artifact"], "mapping_artifact": previous["mapping_artifact"],
        "dataset_articles": previous["dataset_articles"], "selected_articles": previous["selected_articles"],
        "processed_articles": len(ids), "missing_articles": previous["missing_articles"], "missing": previous["missing"],
        "excluded_articles": previous["excluded_articles"], "outputs": outputs, "mode_artifacts": mode_artifacts,
        "summaries": {name: summary(output) for name, output in outputs.items()},
        "previous_summaries": previous["summaries"], "partition_agreement": comparisons,
        "fit_seconds": timings, "examples": examples, "human_event_labels": 0, "event_accuracy": None,
        "accepted_dossiers": 0, "new_embedding_requests": 0, "model_calls": 0, "network_calls": 0,
        "pending_articles": max((out["coverage"]["pending_input_occurrences"] for out in outputs.values()), default=0),
        "failed_modes": [name for name, output in outputs.items() if not output["complete"]],
        "status": "insufficient_vectors" if not outputs else "partial" if any(not out["complete"] for out in outputs.values()) else "completed",
        "started_at": manifest["started_at"], "completed_at": utc(),
        "limitations": "Unlabelled unchanged pilot; pooled passage representation; geometry/engineering diagnostics only; no calibrated event threshold or production scalability"}
    identifier = ledger.record(session, "event_clustering_evaluation", manifest_id, result)
    from .presentation import record
    presentation = record(engine, session, result_context, {"results": [{"kind": "event_clustering_evaluation", "id": identifier}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    from .provisional_tags import literal
    lines = ["Corrected clustering comparison — same saved pilot.", "",
        f"Selected: {result['selected_articles']} of {result['dataset_articles']}; saved vectors: {result['processed_articles']}; "
        f"inherited unprocessed: {result['missing_articles']}; excluded: {result['excluded_articles']}; pending: {result['pending_articles']}. "
        f"Failed modes: {len(result['failed_modes'])}. Status: {result['status']}; "
        f"modes executed: {len(result['outputs'])}/{len(MODES)}.", "",
        "| Method / cosine-distance limit | Candidate groups | Grouped articles | Singletons | Largest group |",
        "|---|---:|---:|---:|---:|"]
    for name in ("upstream_one_batch", "upstream_streaming_500", "baseline_float64_eps_0.20", "baseline_float64_eps_0.30"):
        old = result["previous_summaries"].get(name)
        if old:
            lines.append(f"| Previous {name} | {old['groups']} | {old['grouped_articles']} | {old['singletons']} | — |")
    for name, stats in result["summaries"].items():
        lines.append(f"| {name} | {stats['groups']} | {stats['grouped_articles']} | {stats['singletons']} | {stats['largest_group']} |")
    lines += ["", "Coverage/geometry diagnostics:", ""]
    for name, stats in result["summaries"].items():
        maximum = "unavailable" if stats["max_within_cosine_distance"] is None else f"{stats['max_within_cosine_distance']:.6f}"
        lines.append(f"- {name}: complete={stats['complete']}; omitted IDs={stats['unemitted_ids']}; pending={stats['pending']}; "
            f"maximum within-group distance={maximum}; groups beyond limit={stats['groups_beyond_eps']}; "
            "errors=" + literal(json.dumps(stats["errors"], separators=(",", ":"))))
    lines += ["", "Final partition agreement with corrected single batch: " +
        literal(json.dumps(result["partition_agreement"], sort_keys=True, separators=(",", ":"))), "",
        "All distance limits are fixed exploratory settings, not calibrated event-identity cutoffs. "
        "Complete linkage bounds geometric diameter; it does not prove a shared event. "
        "Singletons/missing vectors are not negative findings. Memberships remain uncertain; "
        "candidate IDs identify member sets within these result/method versions, not validated event identities."]
    for name in ("compact_complete_link_0.10", "compact_complete_link_0.20", "compact_complete_link_0.30"):
        groups = result["examples"].get(name, [])
        lines += ["", "Candidate example — " + name + ":", ""]
        if not groups:
            lines.append("No multi-article candidate at this setting.")
        for group in groups[:1]:
            lines.append(f"- `{group['candidate_id'][-12:]}`: {len(group['members'])} articles; maximum distance {group['max_distance']:.6f}.")
            for member in group["members"][:3]:
                title = literal(member.get("title") or member["source_version"])
                url = member.get("url")
                try:
                    if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).netloc:
                        title = f"[{title}]({quote(url, safe=':/?#=&%+-._~')})"
                except ValueError:
                    pass
                published = literal(str(member.get("published_at") or "unavailable"))
                lines.append("  - " + title + "; publication time: " + published)
    lines += ["", "Original data, embeddings, AWS control and audit history retained. No new embeddings, model/network calls or accepted dossiers. "
        "Human event labels: 0; event accuracy unmeasured. Publication time is not event time. "
        "This bounded all-pairs reference is not a scalable production streaming implementation."]
    return "\n".join(lines)
