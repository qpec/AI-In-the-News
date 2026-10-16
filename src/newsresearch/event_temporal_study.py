"""Audited offline time-window diagnostic; never changes the active partition."""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING

from . import event_group_refinement_study as refinement
from . import event_pair_feature_study as base
from . import event_pair_monotone as rules
from . import event_rule_application_study as application
from . import event_temporal as numeric
from . import event_temporal_summary as summary
from .aws_clustering_evaluation import vectors
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_experiment import _records
from .event_pair_selection import FEATURES
from .event_rule_application import publication_coverage

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "offline-event-publication-window-sensitivity-v1"
CODE = ("event_temporal_study.py", "event_temporal.py", "event_temporal_summary.py", *refinement.CODE)
PROVIDER_SQL = """SELECT id, json_type(payload,'$.raw_record.eventUri') AS uri_type,
json_extract(payload,'$.raw_record.eventUri') AS event_uri
FROM sources WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id"""


def _parent(engine: Research, identifier: str) -> tuple[Json, Json]:
    current = engine.ledger.get(identifier, "event_group_refinement_result")
    manifest = engine.ledger.get(current["manifest"], "event_group_refinement_manifest")
    if (current["status"] != "adopted_provisional_refinement" or not current["adopted"]
            or current["versions"] != manifest["versions"]
            or current["parent_result"] != manifest["method"]["parent"]
            or manifest["method"]["implementation"] != base._hashes(refinement.CODE)
            or current["accepted_dossiers"] != 0 or current["pending_pairs"] != 0):
        raise AuditError("Temporal check requires the unchanged completed provisional refinement")
    parent = refinement._parent(engine, current["parent_result"])
    if current["rule"] != parent["rule"] or current["plan"] != parent["plan"]:
        raise AuditError("Refinement changed the original rule or pilot")
    return current, parent


def _providers(engine: Research, session: str, ids: list[str], versions: Json) -> tuple[Json, Json, str]:
    query: Json = {"sql": PROVIDER_SQL, "parameters": [json.dumps(ids)], "versions": versions,
             "purpose": "Exact retained provider event identifiers, without article bodies"}
    query_ref = base._save(engine, session, query, "Required provider metadata query before execution")
    engine.ledger.append(session, "event_temporal.metadata.intended", {"query_artifact": query_ref})
    rows = [dict(zip(("source_version", "uri_type", "event_uri"), row, strict=True))
            for row in engine.ledger.db.execute(PROVIDER_SQL, query["parameters"]).fetchall()]
    if [row["source_version"] for row in rows] != sorted(ids):
        raise AuditError("Provider query did not cover the exact pilot")
    counts: Counter[str] = Counter()
    providers = {}
    for row in rows:
        kind, value = row["uri_type"], row["event_uri"]
        status = "missing" if kind is None else "null" if kind == "null" else (
            "populated" if kind == "text" and isinstance(value, str) and value.strip() else "empty_string" if kind == "text" else "nonstring")
        counts[status] += 1
        providers[row["source_version"]] = value if status == "populated" else None
        row["coverage_status"] = status
    artifact = base._save(engine, session, {"query_artifact": query_ref, "rows": rows}, "Required provider metadata snapshot")
    engine.ledger.append(session, "event_temporal.metadata.completed", {"artifact": artifact, "rows": len(rows), "counts": dict(counts)})
    return providers, dict(counts), artifact


def _reference_comparison(engine: Research, session: str, parent: Json, final: Json,
                          plan: Json, metadata: Json, rule: Json) -> Json:
    # The original feature table covers ALL development references, including
    # those below the pooled threshold or beyond the old seven-day gate.
    feature = engine.ledger.get(final["parent_feature_result"], "event_pair_feature_experiment")
    feature_manifest = engine.ledger.get(feature["manifest"], "event_pair_feature_manifest")
    if (feature["plan"] != parent["plan"] or feature["versions"] != feature_manifest["versions"]
            or feature_manifest["method"]["implementation"] != base._hashes(base.CODE)):
        raise AuditError("Reference feature method or pilot changed")
    # The already validated plan can be reused, but its probability sample must
    # remain bound to its immutable original artifact.
    development = engine.ledger.artifacts.read(plan["development_sample_artifact"])
    original_rows = development["rows"]
    features = engine.ledger.artifacts.read(feature["development_features"])
    by_id = {row["pair_id"]: row for row in features}
    if len(by_id) != len(features) or set(by_id) != {row["pair_id"] for row in original_rows}:
        raise AuditError("Temporal comparison must preserve every development reference")
    for row in original_rows:
        if any(by_id[row["pair_id"]].get(key) != row.get(key) for key in
               ("left", "right", "distance", "fold", "weight", "inclusion_probability")):
            raise AuditError("Reference feature source or probability binding changed")
    judged, reference_versions, original_id = refinement._references(engine, session, parent, plan, original_rows)
    engine.ledger.append(session, "analysis.cache_reused", {"artifact": feature["development_features"],
        "source_result": final["parent_feature_result"], "versions": feature["versions"],
        "basis": "all_original_probability_bound_development_features_no_new_model_calls"})
    dated = publication_coverage(list(metadata), {source: row.get("published_at") for source, row in metadata.items()})["valid_dates"]
    rows = []
    for row in original_rows:
        value = by_id[row["pair_id"]]
        gap = abs((dated[row["left"]] - dated[row["right"]]).days) if row["left"] in dated and row["right"] in dated else None
        complete = value["status"] == "completed" and all(value["features"].get(name) is not None for name in FEATURES)
        cosine_pass = rules.predicts(value, {**rule, "publication_gap_days": None}) if complete else None
        rows.append({**row, "reference": judged[row["pair_id"]], "features": value["features"],
            "publication_gap_days": gap, "band": numeric.pair_band(gap), "cosine_pass": cosine_pass,
            "processing_status": "completed" if complete else "unprocessed",
            "articles": [metadata[source] for source in (row["left"], row["right"])]})
    caps = []
    for cap in numeric.CAPS:
        counts = {}
        for label in ("same_event", "different_event", "uncertain"):
            selected = [row for row in rows if row["reference"]["label"] == label]
            passing = [row for row in selected if row["cosine_pass"] is True and row["publication_gap_days"] is not None
                       and (cap is None or row["publication_gap_days"] <= cap)]
            counts[label] = {"total": len(selected), "passing": len(passing), "weight": math.fsum(row["weight"] for row in selected),
                "passing_weight": math.fsum(row["weight"] for row in passing),
                "unknown_dates": sum(row["publication_gap_days"] is None for row in selected),
                "unprocessed": sum(row["cosine_pass"] is None for row in selected)}
        caps.append({"cap_days": cap, "labels": counts})
    return {"rows": rows, "caps": caps, "reference_versions": reference_versions, "original_reference_result": original_id,
        "held_out": False, "human_gold": False, "rows_unprocessed": sum(row["cosine_pass"] is None for row in rows)}


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_temporal_result", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"parent_result", "diagnostic_key", "user_instruction", "output_directory"}
            or not engine.config.offline or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare an offline temporal diagnostic, parent, exact instruction and protected output")
    current, parent = _parent(engine, data["parent_result"])
    if context.versions and context.versions != current["versions"]:
        raise ResearchError("Temporal context differs from the current grouping")
    method = {"method": METHOD, "implementation": base._hashes(CODE), "parent": data["parent_result"],
        "input_versions": current["versions"], "rule": parent["rule"], "plan": parent["plan"],
        "caps": list(numeric.CAPS), "bands": list(numeric.BANDS), "user_instruction": data["user_instruction"],
        "observed_chat_timestamp": None, "selection": "All unordered vector-bearing article pairs; no date or neighbor cap",
        "comparison": "Same dated vector cohort for all caps; unknown dates separate even in unlimited comparison",
        "features": "Unchanged full precision five-feature rule; exact version-bound reuse of original <=7-day features; same passage implementation for new candidates",
        "provider_sql": PROVIDER_SQL, "provider_interpretation": "Exact populated eventUri equality is metadata, not event-identity ground truth",
        "references": "Every original probability-weighted development reference, uncertain included; no held-out labels or new judges",
        "acceptance": "Diagnostic only; no active grouping changes; no accepted dossiers or new event-identity findings",
        "output_directory": str(Path(data["output_directory"]).absolute()), "new_model_calls": 0, "new_embeddings": 0}
    key = data["diagnostic_key"]
    old = _records(engine, "event_temporal_manifest", key)
    if old and (len(old) != 1 or old[0][1]["method"] != method):
        raise ResearchError("Diagnostic key already binds another immutable method")
    if old:
        manifest_id, manifest = old[0]
        versions = manifest["versions"]
    else:
        versions = dict(current["versions"])
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, current["versions"]), {
                "kind": kind, "key": key, "branch": "exploratory-temporal-sensitivity", "amend_latest": True,
                "reason": "Check publication windows without retuning similarities or adopting new groups",
                "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                    "text": "Does the seven-day publication gate omit plausible same-event report candidates?",
                    "rules": "Retain every pilot article and unknown processing; no source collection or inference",
                    "unit": "One real-world event, not incident-with-timeline; similarity candidates remain unjudged"}})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_temporal_manifest", key, manifest)
    finished = _records(engine, "event_temporal_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Completed temporal result differs from the immutable manifest")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_temporal_check"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_temporal.intended", {"manifest": manifest_id, "versions": versions})
    final, plan, index, metadata, mapped, pooled = application._inputs(engine, session, parent["parent_result"])
    ids = [row["source_version"] for row in mapped]
    coverage = publication_coverage(ids, {source: row.get("published_at") for source, row in metadata.items()})
    dates, missing_dates = coverage["valid_dates"], coverage["missing_date_ids"]
    all_dates = publication_coverage(list(metadata), {source: row.get("published_at") for source, row in metadata.items()})["valid_dates"]
    groups = engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    if (set(refinement._owners(groups)) != set(dates) or len(dates) != parent["date_eligible_articles"]
            or len(missing_dates) != parent["missing_date_articles"] or len(ids) != parent["vector_articles"]):
        raise AuditError("Temporal scan changed the original vector/date/group coverage")
    providers, provider_coverage, provider_artifact = _providers(engine, session, sorted(metadata), plan["versions"])
    original = engine.ledger.artifacts.read(parent["score_artifact"])
    cache = {row["pair_id"]: row for row in original}
    if len(cache) != len(original) or len(cache) != parent["pooled_candidates"]:
        raise AuditError("Original feature cache has duplicate or missing candidates")
    engine.ledger.append(session, "analysis.cache_reused", {"artifact": parent["score_artifact"],
        "source_result": current["parent_result"], "versions": parent["versions"], "basis": "exact_pair_distance_and_method_bound_feature_reuse"})
    mapping = {row["source_version"]: [chunk["row"] for chunk in row["chunks"]] for row in mapped}
    stored = _records(engine, "event_temporal_batch", manifest_id)
    cached = {row["ordinal"]: row for _, row in stored}
    if len(cached) != len(stored):
        raise AuditError("Duplicate temporal batch ordinals")
    scored, batches = [], []
    checked = 0
    reused: set[str] = set()
    with vectors(engine, session, index) as (passages, matrix):
        for item in mapped:
            for chunk in item["chunks"]:
                value = passages[chunk["row"]]
                if (value["source_version"], value["id"], value["passage_id"]) != (item["source_version"], chunk["chunk"], chunk["passage"]):
                    raise AuditError("Temporal passage mapping differs from the retained index")
        for ordinal, (rows, stats) in enumerate(numeric.candidate_batches(pooled, ids, parent["rule"]["thresholds"][0])):
            checked += stats["checked_vector_pairs"]
            known, fresh = [], []
            for row in rows:
                prior = cache.get(row["pair_id"])
                if prior is None:
                    fresh.append(row)
                else:
                    if any(prior.get(field) != row[field] for field in ("left", "right", "distance", "pair_id")):
                        raise AuditError("Temporal candidate differs from its exact cached original pair")
                    known.append(prior)
                    reused.add(row["pair_id"])
            binding = {"manifest": manifest_id, "ordinal": ordinal, "input_hash": digest(rows), "stats": stats,
                       "versions": versions, "reused_pair_ids": sorted(row["pair_id"] for row in known)}
            if ordinal in cached:
                saved = cached[ordinal]
                if any(saved.get(field) != value for field, value in binding.items()):
                    raise AuditError("Resumed temporal batch changed its immutable binding")
                computed = engine.ledger.artifacts.read(saved["features_artifact"])
                engine.ledger.append(session, "analysis.cache_reused", {"artifact": saved["features_artifact"], "basis": "exact_version_temporal_batch"})
            else:
                input_ref = base._save(engine, session, rows, "Required exact temporal candidates before feature execution")
                engine.ledger.append(session, "event_temporal.batch.intended", {**binding, "candidates_artifact": input_ref})
                computed = known + (base._compute(engine, session, matrix, mapping, fresh, metadata, "temporal_new_pairs") if fresh else [])
                computed.sort(key=lambda row: row["pair_id"])
                feature_ref = base._save(engine, session, computed, "Required complete temporal feature batch including failures")
                saved = {**binding, "candidates_artifact": input_ref, "features_artifact": feature_ref}
                engine.ledger.record(session, "event_temporal_batch", manifest_id, saved)
            if len(computed) != len(rows) or {row["pair_id"] for row in computed} != {row["pair_id"] for row in rows}:
                raise AuditError("Temporal feature batch changed pair coverage")
            scored.extend(computed)
            batches.append(saved["features_artifact"])
            engine.ledger.append(session, "event_temporal.batch.completed", {"manifest": manifest_id, "ordinal": ordinal,
                "checked_vector_pairs": checked, "scored_pairs": len(scored), "reused_pairs": len(reused)})
    if reused != set(cache) or checked != len(ids) * (len(ids) - 1) // 2 or any(n >= len(batches) for n in cached):
        raise AuditError("Temporal enumeration omitted original candidates, vector pairs or saved batches")
    engine.ledger.append(session, "event_temporal.summary.intended", {"manifest": manifest_id, "scored_pairs": len(scored)})
    overview = summary.summarize(scored, parent["rule"], all_dates, metadata, groups, providers)
    if (overview["bands"][0]["pooled_candidates"] != len(cache)
            or overview["caps"][0]["dated_passing_pairs"] != parent["proposed_link_pairs"]):
        raise AuditError("Temporal seven-day replay changed the original score application")
    references = _reference_comparison(engine, session, parent, final, plan, metadata, parent["rule"])
    directory = Path(data["output_directory"])
    long_pairs = overview.pop("long_passing_pairs")
    spans = {name: overview[name].pop("rows") for name in ("current_group_spans", "provider_group_spans")}
    exports = {"long_pairs": application._export(engine, session, directory, "long-gap-pairs.json", long_pairs),
        "spans": application._export(engine, session, directory, "publication-spans.json", spans),
        "references": application._export(engine, session, directory, "reference-comparison.json", references)}
    feature_artifact = base._save(engine, session, scored, "Required complete date-free candidate score table")
    failures = sum(row["status"] != "completed" or any(row["features"].get(name) is None for name in FEATURES) for row in scored)
    result = {"versions": versions, "manifest": manifest_id, "parent_result": data["parent_result"],
        "plan": parent["plan"], "rule": parent["rule"], "status": "completed_with_failed_pairs" if failures else "completed_temporal_diagnostic",
        "dataset_articles": len(metadata), "vector_articles": len(ids), "dated_vector_articles": len(dates),
        "missing_vector_articles": len(metadata) - len(ids), "missing_date_articles": len(missing_dates),
        "checked_vector_pairs": checked, "pooled_candidates": len(scored), "reused_feature_pairs": len(reused),
        "new_feature_pairs": len(scored) - len(reused), "failed_feature_pairs": failures, "pending_pairs": 0,
        "feature_artifact": feature_artifact, "batch_artifacts": batches, "provider_coverage": provider_coverage,
        "provider_artifact": provider_artifact, "reference_caps": references["caps"], "reference_pairs": len(references["rows"]),
        "reference_unprocessed": references["rows_unprocessed"], "long_reference_examples": [row for row in references["rows"]
            if row["publication_gap_days"] is not None and row["publication_gap_days"] > 7],
        "exports": exports, **overview, "active_partition_changed": False, "accepted_dossiers": 0,
        "new_model_calls": 0, "new_embedding_requests": 0, "network_calls": 0,
        "started_at": manifest["started_at"], "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_temporal_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    from .rag_answers import _link
    current, provider = result["current_group_spans"], result["provider_group_spans"]
    lines = ["**The seven-day limit is a method-imposed ceiling, not an observed event boundary.**", "",
        f"Offline check: {result['dataset_articles']:,} pilot articles; {result['vector_articles']:,} saved vectors; "
        f"{result['checked_vector_pairs']:,} unordered vector pairs checked without a time limit. "
        f"{result['pooled_candidates']:,} candidates scored, including {result['reused_feature_pairs']:,} reused feature rows. "
        f"Missing vectors: {result['missing_vector_articles']:,}; unusable dates among vector articles: {result['missing_date_articles']:,}; "
        f"feature failures: {result['failed_feature_pairs']:,}; pending: {result['pending_pairs']:,}.", "",
        "Unchanged five similarity thresholds; all date caps use the same " + f"{result['dated_vector_articles']:,} dated-vector articles:", "",
        "| Publication gap cap | Pairs passing all five similarities | Articles in those pairs |",
        "|---|---:|---:|"]
    for row in result["caps"]:
        lines.append(f"| {str(row['cap_days']) + ' days' if row['cap_days'] is not None else 'Unlimited'} | {row['dated_passing_pairs']:,} | {row['distinct_articles']:,} |")
    lines += ["", f"Unknown-gap pairs passing the similarities: {result['unknown_gap_cosine_passing_pairs']:,}, reported separately. "
        "These are unjudged candidates, not established same-event links.", "",
        f"Current {current['multi_article_groups']:,} multi-article groups: median publication span {current['median_days']} days; "
        f"90th percentile {current['p90_days']} days; maximum {current['max_days']} days. Complete-link plus the seven-day pair rule forces that ceiling.", "",
        f"Provider eventUri coverage: {provider['articles_with_provider_id']:,}/{provider['corpus_articles']:,} articles. "
        f"Of {provider['multi_article_groups']:,} repeated provider IDs, {provider['groups_with_two_or_more_dates']:,} have at least two dates; "
        f"{provider['groups_beyond_7_days']:,} span more than seven days; maximum observed span "
        f"{str(provider['max_days']) + ' days' if provider['max_days'] is not None else 'unavailable'}. "
        "Provider IDs are independent metadata signals, not validated event identity.", "",
        f"All {result['reference_pairs']} original development model references were retained; unprocessed: {result['reference_unprocessed']}. "
        "Pair-rule passes by reference label (same / different / uncertain):"]
    for row in result["reference_caps"]:
        labels = row["labels"]
        lines.append(f"- {row['cap_days'] if row['cap_days'] is not None else 'Unlimited'} days: " + " / ".join(
            f"{labels[label]['passing']}/{labels[label]['total']}" for label in ("same_event", "different_event", "uncertain")))
    long_refs = result["long_reference_examples"]
    lines += ["", "Original model references beyond seven days: " + ", ".join(
        f"{sum(row['reference']['label'] == label for row in long_refs)} {label}" for label in ("same_event", "different_event", "uncertain"))
        + ". These labels are reused, not fresh assessments."]
    for label in ("same_event", "different_event"):
        sample = next((row for row in sorted(long_refs, key=lambda row: -row["publication_gap_days"])
                       if row["reference"]["label"] == label), None)
        if sample is not None:
            lines.append(f"- {sample['publication_gap_days']} days; original label {label}; similarities "
                f"{'pass' if sample['cosine_pass'] is True else 'fail' if sample['cosine_pass'] is False else 'unprocessed'}: "
                + " ↔ ".join(_link(item.get("title") or item["source_version"], item.get("url")) for item in sample["articles"]))
    lines += ["", "Long-gap numerical examples—**unjudged**; dates are publication dates:"]
    for row in result["examples"]:
        links = " ↔ ".join(_link(item.get("title") or item["source"], item.get("url")) + f" ({item['published_at']})" for item in row["articles"])
        lines.append(f"- {row['publication_gap_days']} days; pooled cosine {row['features']['pooled_cosine']:.3f}; "
            f"all five similarities pass; provider IDs {row['provider_equality']}: {links}")
    if not result["examples"]:
        lines.append("- No longer-gap pair passed all five similarities.")
    lines += ["", "**Recommendation:** use time to prioritize candidate review, rather than define an event. "
        "Long-gap links need event-specific evidence; recurring similar events and later developments can be distinct events. "
        "This check does not validate a wider cutoff. The existing rule remains unvalidated; development model references are not human gold. "
        "Active groups unchanged; accepted dossiers: 0; new model calls and embeddings: 0.", "",
        "[All longer-gap candidates](" + result["exports"]["long_pairs"]["path"].replace("\\", "/") + ") · "
        "[Span and reference details](" + result["exports"]["spans"]["path"].replace("\\", "/") + ")"]
    return "\n".join(lines)
