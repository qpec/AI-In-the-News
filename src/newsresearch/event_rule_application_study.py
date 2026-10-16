"""Offline application of an explicitly selected, unvalidated event-link rule."""
from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from . import event_pair_feature_study as base
from . import event_pair_monotone as rules
from . import event_pair_monotone_study as prior
from . import event_rule_application as numeric
from .aws_clustering_evaluation import vectors
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_experiment import _records
from .event_pair_selection import FEATURES
from .event_pair_study import load_plan
from .storage import check_permissions

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "unvalidated-event-rule-all-pilot-articles-v1"
CODE = ("event_rule_application_study.py", "event_rule_application.py", *prior.CODE)


def _inputs(engine: Research, session: str, identifier: str) -> tuple[Json, Json, Json, Json, list[Json], Any]:
    parent = engine.ledger.get(identifier, "event_pair_monotone_result")
    manifest = engine.ledger.get(parent["manifest"], "event_pair_monotone_manifest")
    metrics = engine.ledger.artifacts.read(parent["development_metrics"])
    if (parent["status"] != "no_eligible_rule" or not parent["search_complete"]
            or not parent.get("best_at_required_coverage") or parent["candidate"] is not None
            or parent["versions"] != manifest["versions"]
            or parent["best_at_required_coverage"] != metrics["best_at_required_coverage"]
            or manifest["method"]["implementation"] != base._hashes(prior.CODE)):
        raise ResearchError("Declare the completed failed final screen with its unchanged best-coverage diagnostic")
    plan, _, _ = load_plan(engine, session, parent["plan"])
    original = engine.ledger.get(parent["original_parent"], "event_pair_experiment")
    base.parent_binding(engine, original, parent["plan"], plan)
    index = engine.ledger.get(plan["index"], "vector_index")
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    mapped = engine.ledger.artifacts.read(plan["mapping_artifact"])
    raw = engine.ledger.artifacts.read_bytes(plan["pooled_vectors_artifact"])
    pooled = np.frombuffer(raw, dtype="<f4").reshape((len(mapped), index["dimensions"]))
    selected = engine.ledger.get(plan["versions"]["dataset"], "dataset")["source_versions"]
    if (set(metadata) != set(selected) or len(selected) != plan["selected_articles"]
            or len(mapped) != plan["processed_articles"]
            or {item["source_version"] for item in mapped} | {item["source_version"] for item in plan["missing"]} != set(selected)):
        raise AuditError("Application coverage differs from the original full pilot dataset")
    return parent, plan, index, metadata, mapped, pooled


def _export(engine: Research, session: str, directory: Path, name: str, value: Any) -> Json:
    """Audited private convenience copy, backed by an integrity-checked artifact."""
    directory = directory.absolute()
    if not directory.resolve().is_relative_to(engine.ledger.root):
        raise ResearchError("Application exports must remain inside protected research storage")
    for parent in (directory, *directory.parents):
        if parent.is_symlink() or parent.is_junction():
            raise AuditError("Application export paths cannot contain links or junctions")
        if parent == engine.ledger.root:
            break
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    check_permissions(directory)
    artifact = base._save(engine, session, value, f"Required private application export: {name}")
    path = directory / name
    engine.ledger.append(session, "export.write_intended", {"artifact": artifact, "path": str(path), "public": False})
    content = engine.ledger.artifacts.read_bytes(artifact)
    if path.exists() or path.is_symlink() or path.is_junction():
        check_permissions(path)
        if path.read_bytes() != content:
            raise AuditError("Application export already exists with different contents")
    else:
        with path.open("xb") as stream:
            if os.name != "nt":
                path.chmod(0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    check_permissions(path)
    engine.ledger.append(session, "event_rule.private_export.written", {"artifact": artifact, "path": str(path), "public": False})
    return {"artifact": artifact, "path": str(path)}


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_rule_application_result", "id": identifier}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"parent_result", "application_key", "user_instruction", "apply_unvalidated", "output_directory"}
            or data["apply_unvalidated"] is not True or not engine.config.offline
            or any(not isinstance(data.get(key), str) or not data[key].strip() for key in
                   ("parent_result", "application_key", "user_instruction", "output_directory"))):
        raise ResearchError("Offline application requires an explicit unvalidated instruction, parent, key and protected output")
    parent, plan, index, metadata, mapped, pooled = _inputs(engine, session, data["parent_result"])
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("Application context differs from the frozen pilot")
    diagnostic = parent["best_at_required_coverage"]
    rule = {key: diagnostic[key] for key in ("features", "thresholds", "publication_gap_days")}
    if rule["features"] != list(FEATURES) or len(rule["thresholds"]) != len(FEATURES):
        raise AuditError("Application requires the original complete five-feature diagnostic")
    method = {"method": METHOD, "implementation": base._hashes(CODE), "parent": data["parent_result"],
        "plan": parent["plan"], "input_index": plan["index"], "input_versions": plan["versions"],
        "rule": rule, "development_metrics": diagnostic["metrics"], "validation_status": "failed_development_unvalidated",
        "application_permission": {"instruction": data["user_instruction"], "source": "human_reply_in_current_codex_chat",
            "observed_chat_timestamp": None, "apply_unvalidated": True, "paid_inference_authorized": False},
        "selection": "All articles in the original imported pilot, including duplicate reporting copies; no fold barrier",
        "candidate_discovery": "Every unordered pair with available vectors and publication gap within the rule gate; float64 bounded matrix prefilter with 1e-10 margin, exact original scalar cosine reranking; no neighbor cap",
        "scores": "Original retained normalized pooled vectors; 1-clip(1-dot(a,b)/(norm(a)*norm(b)),0,2). Remaining features reuse the unchanged passage implementation.",
        "grouping": "Descending pooled cosine then pair ID; merge only if every cross-group pair passes all five thresholds and date gate. Persist all unmerged passing bridges.",
        "nonmatch": "review; never different_event", "missing_processing": "null, explicitly separate from review",
        "acceptance": "No accepted dossiers or event-identity findings; all groups provisional, singletons do not establish unique events",
        "evaluation_limit": "Rule selected on development references; no held-out labels or new human validation; LLM references are not human gold",
        "model_calls": 0, "new_embeddings": 0, "output_directory": str(Path(data["output_directory"]).absolute())}
    key = data["application_key"]
    previous = _records(engine, "event_rule_application_manifest", key)
    if previous and (len(previous) != 1 or previous[0][1]["method"] != method):
        raise ResearchError("Application key already binds another immutable method, rule or instruction")
    if previous:
        manifest_id, manifest = previous[0]
        versions = manifest["versions"]
    else:
        versions = dict(plan["versions"])
        for kind in ("protocol", "selection", "profile", "dossier_definition", "codebook"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
                "kind": kind, "key": key, "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                    "rules": method["selection"], "unit": "One real-world event reported across sources/times; provisional complete-link group proposals only",
                    "labels": ["provisional", "review_singleton", "unprocessed"]},
                "amend_latest": True, "reason": "Apply explicitly selected failed-development rule as unvalidated group proposals"})["id"]
        manifest = {"method": method, "versions": versions, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_rule_application_manifest", key, manifest)
    finished = _records(engine, "event_rule_application_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id:
            raise AuditError("Application result differs from immutable manifest")
        engine.ledger.append(session, "analysis.cache_reused", {"manifest": manifest_id, "result": finished[0][0], "basis": "exact_version_completed_application"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_rule.application.intended", {"manifest": manifest_id, "versions": versions,
        "articles": len(metadata), "rule": rule, "unvalidated": True, "model_calls": 0})
    ids = [item["source_version"] for item in mapped]
    published = {source: item.get("published_at") for source, item in metadata.items()}
    coverage = numeric.publication_coverage(ids, published)
    missing_dates = set(coverage["missing_date_ids"])
    eligible_ids = [source for source in ids if source not in missing_dates]
    mapping = {item["source_version"]: [chunk["row"] for chunk in item["chunks"]] for item in mapped}
    scored: list[Json] = []
    batch_refs = []
    checked, candidates = 0, 0
    saved_batches = _records(engine, "event_rule_application_batch", manifest_id)
    cached = {item["ordinal"]: item for _, item in saved_batches}
    if len(cached) != len(saved_batches):
        raise AuditError("Application contains duplicate completed batch ordinals")
    with vectors(engine, session, index) as (passages, matrix):
        for item in mapped:
            for chunk in item["chunks"]:
                row = passages[chunk["row"]]
                if (row["source_version"] != item["source_version"] or row["id"] != chunk["chunk"] or row["passage_id"] != chunk["passage"]):
                    raise AuditError("Application passage mapping differs from the retained index")
        for ordinal, (rows, stats) in enumerate(numeric.candidate_batches(pooled, ids, published, rule)):
            checked += stats["checked_date_pairs"]
            candidates += len(rows)
            binding = {"manifest": manifest_id, "ordinal": ordinal, "input_hash": digest(rows), "stats": stats}
            if ordinal in cached:
                saved = cached[ordinal]
                if any(saved.get(field) != value for field, value in binding.items()):
                    raise AuditError("Resumed candidate batch differs from the registered application")
                computed = engine.ledger.artifacts.read(saved["features_artifact"])
                engine.ledger.append(session, "analysis.cache_reused", {"manifest": manifest_id, "artifact": saved["features_artifact"], "basis": "exact_version_application_batch"})
            else:
                input_ref = base._save(engine, session, rows, "Required exact all-pairs prefilter candidates before scoring")
                engine.ledger.append(session, "event_rule.batch.intended", {**binding, "candidates_artifact": input_ref})
                computed = base._compute(engine, session, matrix, mapping, rows, metadata, "all_pilot_application") if rows else []
                artifact = base._save(engine, session, computed, "Required complete application scores, failures and original passage references")
                saved = {**binding, "versions": versions, "candidates_artifact": input_ref, "features_artifact": artifact}
                engine.ledger.record(session, "event_rule_application_batch", manifest_id, saved)
            if len(computed) != len(rows) or {row["pair_id"] for row in computed} != {row["pair_id"] for row in rows}:
                raise AuditError("Application feature batch changed candidate coverage")
            scored.extend(computed)
            batch_refs.append(saved["features_artifact"])
            engine.ledger.append(session, "event_rule.batch.completed", {"manifest": manifest_id, "ordinal": ordinal,
                "checked_date_pairs": checked, "pooled_candidates": candidates, "scored_pairs": len(scored)})
    failures = [row for row in scored if row["status"] != "completed" or any(row["features"].get(name) is None for name in FEATURES)]
    failed_ids = {row["pair_id"] for row in failures}
    edges = [row for row in scored if row["pair_id"] not in failed_ids and rules.predicts(row, rule)]
    grouped = numeric.complete_link_groups(eligible_ids, edges)
    groups = [{**item, "status": "provisional" if len(item["members"]) > 1 else "review_singleton", "accepted": False}
              for item in grouped["groups"]]
    by_source = {source: item for item in groups for source in item["members"]}
    link_degree = Counter(source for row in edges for source in (row["left"], row["right"]))
    bridge_degree = Counter(source for row in grouped["bridges"] for source in (row["left"], row["right"]))
    failure_degree = Counter(source for row in failures for source in (row["left"], row["right"]))
    repetitions = Counter(item["body_sha256"] for item in metadata.values())
    vector_set = set(ids)
    articles = [{**metadata[source], "group_id": by_source[source]["group_id"] if source in by_source else None,
        "status": "missing_vectors" if source not in vector_set else "missing_publication_date" if source in missing_dates else by_source[source]["status"],
        "processing_status": "missing_vectors" if source not in vector_set else "missing_publication_date" if source in missing_dates else "partial_failed_pairs" if failure_degree[source] else "complete",
        "provisional_link_count": link_degree[source], "bridge_count": bridge_degree[source], "failed_pair_count": failure_degree[source],
        "exact_body_copies_in_pilot": repetitions[metadata[source]["body_sha256"]], "same_event_answer": None, "accepted": False}
        for source in sorted(metadata)]
    directory = Path(data["output_directory"])
    exports = {"articles": _export(engine, session, directory, "articles.json", articles),
        "groups": _export(engine, session, directory, "groups.json", groups),
        "bridges": _export(engine, session, directory, "bridges.json", grouped["bridges"])}
    score_ref = base._save(engine, session, scored, "Required complete scored candidate table including null/failed rows")
    example_groups = [item for item in groups if len(item["members"]) > 1][:3]
    examples = [{"group_id": item["group_id"], "article_count": len(item["members"]),
        "articles": [metadata[source] for source in item["members"][:3]]} for item in example_groups]
    result = {"versions": versions, "manifest": manifest_id, "parent_result": data["parent_result"], "plan": parent["plan"],
        "rule": rule, "validation_status": "failed_development_unvalidated", "development_metrics": diagnostic["metrics"],
        "status": "completed_with_failed_pairs" if failures else "completed_provisional_application", "dataset_articles": len(metadata),
        "vector_articles": len(ids), "missing_vector_articles": len(metadata) - len(ids), "missing_date_articles": len(missing_dates),
        "date_eligible_articles": len(eligible_ids), "checked_date_pairs": checked, "pooled_candidates": candidates,
        "completed_feature_pairs": len(scored) - len(failures), "failed_feature_pairs": len(failures), "pending_pairs": 0,
        "proposed_link_pairs": len(edges), "review_candidate_pairs": len(scored) - len(failures) - len(edges),
        "grouped_articles": sum(len(item["members"]) for item in groups if len(item["members"]) > 1),
        **grouped["counts"], "score_artifact": score_ref, "feature_batches": batch_refs, "exports": exports,
        "examples": examples, "new_model_calls": 0, "new_embedding_requests": 0, "network_calls": 0, "accepted_dossiers": 0,
        "started_at": manifest["started_at"], "completed_at": utc(), "human_validated": False}
    identifier = engine.ledger.record(session, "event_rule_application_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    metrics = result["development_metrics"]
    lines = [f"Applied the best coverage-focused rule to **all {result['dataset_articles']:,} pilot articles**.", "",
        f"- **{result['multi_article_groups']:,} provisional groups**, containing {result['grouped_articles']:,} articles; "
        f"{result['singletons']:,} review singletons. Accepted event dossiers: **0**.",
        f"- {result['vector_articles']:,} articles have saved vectors; {result['missing_vector_articles']:,} lack vectors; "
        f"{result['missing_date_articles']:,} vector-bearing articles lack usable publication dates.",
        f"- Checked {result['checked_date_pairs']:,} date-eligible pairs; scored {result['pooled_candidates']:,} pooled-threshold candidates; "
        f"{result['proposed_link_pairs']:,} pairs passed all signals. {result['bridge_edges']:,} passing bridges were kept for review instead of merging incomplete groups.",
        f"- Feature failures: {result['failed_feature_pairs']:,}; pending: {result['pending_pairs']:,}. Missing/failed processing remains unknown. "
        "No new embeddings or model calls.", "",
        f"**Unvalidated:** this rule failed the 90% development precision target (observed {metrics['precision_pessimistic_observed']:.1%}, "
        f"weighted {metrics['precision_pessimistic_weighted']:.1%}; weighted known-same coverage {metrics['known_same_coverage_weighted']:.1%}). "
        "These are development model-reference diagnostics, not corpus accuracy. All groups require review; singletons do not prove distinct events.", "",
        "All five cosine thresholds must pass: " + "; ".join(f"{name} ≥ {cut:.6f}" for name, cut in zip(result['rule']['features'], result['rule']['thresholds'], strict=True))
        + f"; publication gap ≤ {result['rule']['publication_gap_days']} UTC calendar days. The audit retains full precision. "
        "Publication dates are not event dates; this rule can miss reports published farther apart.", "",
        "Largest provisional groups (source titles shown without a new semantic assessment):", ""]
    from .rag_answers import _link
    for example in result["examples"]:
        links = "; ".join(_link(item.get("title") or item["source_version"], item.get("url")) for item in example["articles"])
        lines.append(f"- {example['article_count']} articles: {links}")
    if not result["examples"]:
        lines.append("- No multi-article group was proposed.")
    lines += ["", "[All article dispositions](" + result["exports"]["articles"]["path"].replace('\\', '/') + ") · "
        "[All provisional groups](" + result["exports"]["groups"]["path"].replace('\\', '/') + ")"]
    return "\n".join(lines)
