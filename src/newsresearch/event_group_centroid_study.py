"""Audited offline group-centroid mapping, speed and reused-reference diagnostic."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import time
from typing import TYPE_CHECKING

import faiss
import numpy as np

from . import event_group_centroids as numeric
from . import event_group_evidence as baseline
from . import event_group_evidence_judging as judged
from .common import AuditError, Context, Json, ResearchError, require_active, utc
from .event_pair_answers import validate_answer

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "fast-collective-vector-cross-window-group-mapping-v1"
CODE = ("event_group_centroid_study.py", "event_group_centroids.py", *judged.CODE)
SQL = "SELECT json_extract(value,'$.reference.label') AS label,count(*) AS pairs,coalesce(sum(json_extract(value,'$.together')=1),0) AS together,coalesce(sum(json_extract(value,'$.together')=0),0) AS separate,sum(json_extract(value,'$.together') IS NULL) AS unprocessed FROM json_each(?) GROUP BY label ORDER BY label"


def _parent(engine: Research, identifier: str) -> Json:
    parent = engine.ledger.get(identifier, "event_group_evidence_judgment_result")
    manifest = engine.ledger.get(parent["manifest"], "event_group_evidence_judging_manifest")
    if (parent["status"] != "completed_provisional_model_references" or parent["actual_group_merges"] != 0
            or parent["accepted_dossiers"] != 0 or parent["versions"] != manifest["versions"]
            or parent["prepared_result"] != manifest["binding"]["prepared_result"]
            or manifest["binding"]["implementation"] != judged.preparation.links.base._hashes(judged.CODE)
            or parent["failed_pairs"] or parent["pending_pairs"] or parent["unknown_pairs"]):
        raise AuditError("Centroid diagnostic requires the unchanged completed bounded review")
    return parent


def _inputs(engine: Research, session: str, parent: Json) -> Json:
    prepared, frozen, queue, packets, plan, metadata = judged._load(engine, session, parent["prepared_result"])
    _, comparison, temporal, current, original = judged.preparation._parents(engine, prepared["previous_result"])
    groups = engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    scored = engine.ledger.artifacts.read(temporal["feature_artifact"])
    mapped = engine.ledger.artifacts.read(plan["mapping_artifact"])
    index = engine.ledger.get(plan["index"], "vector_index")
    raw = engine.ledger.artifacts.read_bytes(plan["pooled_vectors_artifact"])
    pooled = np.frombuffer(raw, dtype="<f4").reshape(len(mapped), index["dimensions"])
    frame = engine.ledger.artifacts.read(plan["frame_artifact"])
    if (len(mapped) != plan["processed_articles"] or len(scored) != temporal["pooled_candidates"]
            or len(judged.preparation.links.windows.temporal.refinement._owners(groups)) != comparison["dated_vector_articles"]
            or set(metadata) != set(engine.ledger.get(parent["versions"]["dataset"], "dataset")["source_versions"])):
        raise AuditError("Centroid vector, feature or selected group coverage differs")
    engine.ledger.append(session, "analysis.cache_reused", {"pooled_vectors": plan["pooled_vectors_artifact"],
        "mapping": plan["mapping_artifact"], "groups": current["exports"]["groups"]["artifact"],
        "features": temporal["feature_artifact"], "basis": "exact_version_existing_article_vectors_and_seven_day_groups"})
    folds = {row["body_sha256"]: row["fold"] for row in frame["representatives"]}
    allowed = {source for source in metadata if folds.get(metadata[source]["body_sha256"]) == "development"}
    return {"prepared": prepared, "queue": queue, "packets": packets, "plan": plan, "metadata": metadata,
        "groups": groups, "scored": scored, "pooled": pooled, "article_ids": [row["source_version"] for row in mapped],
        "comparison": comparison, "temporal": temporal, "current": current, "original": original, "allowed": allowed}


def _warm(representation: Json, mapped: Json) -> Json:
    rows = {row["group_id"]: row for row in representation["rows"]}
    positions = [n for n, key in enumerate(representation["group_ids"]) if rows[key]["member_count"] > 1][:64]
    durations = []
    old_threads = faiss.omp_get_max_threads()
    try:
        faiss.omp_set_num_threads(4)
        for position in positions:
            vector = representation["centroids"][position:position + 1]
            mapped["index"].search(vector, min(32, len(representation["group_ids"])))
            started = time.perf_counter()
            mapped["index"].search(vector, min(32, len(representation["group_ids"])))
            durations.append(1000 * (time.perf_counter() - started))
    finally:
        faiss.omp_set_num_threads(old_threads)
    return {"queries": len(durations), "median_ms": float(np.median(durations)) if durations else None,
        "p95_ms": float(np.percentile(durations, 95)) if durations else None,
        "scope": "warm exact vector retrieval only; excludes evidence gates, article reads, full preflight and durable writes",
        "samples": durations, "faiss_threads": 4, "restored_faiss_threads": old_threads}


def _compute(engine: Research, session: str, inputs: Json, manifest_id: str, versions: Json, key: str) -> Json:
    started = time.perf_counter()
    legacy = baseline.prepare(inputs["groups"], inputs["scored"], inputs["metadata"], inputs["current"]["rule"],
        review_source_ids=inputs["allowed"])
    baseline_seconds = time.perf_counter() - started
    started = time.perf_counter()
    representation = numeric.build_centroids(inputs["groups"], inputs["article_ids"], inputs["pooled"], inputs["metadata"])
    mapped = numeric.map_candidates(representation)
    gated = numeric.gate_candidates(inputs["current"]["rule"], inputs["scored"], mapped)
    variants = {"0.975": numeric.select(inputs["current"]["rule"], [], mapped, .975, gated=gated)}
    single_seconds = time.perf_counter() - started
    for cut in (.90, .95):
        variants[str(cut)] = numeric.select(inputs["current"]["rule"], [], mapped, cut, gated=gated)
    grid_seconds = time.perf_counter() - started
    save = judged.preparation.links.base._save
    binary = engine.ledger.artifacts.put_bytes(representation["centroids"].astype("<f4").tobytes())
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": binary, "purpose": "Exact cached collective group vectors", "dtype": "<f4", "shape": list(representation["centroids"].shape)})
    value = {"representation_rows": representation["rows"], "group_ids": representation["group_ids"],
        "centroid_artifact": binary, "centroid_shape": list(representation["centroids"].shape), "frame": mapped["candidates"],
        "mapping_diagnostics": mapped["diagnostics"], "gated": gated, "variants": variants,
        "legacy_diagnostics": legacy["diagnostics"], "legacy_frame": legacy["candidates"],
        "timings": {**representation["timings"], **mapped["timings"], **gated["timings"],
            "default_selection_seconds": variants["0.975"]["timings"]["selection_seconds"],
            "default_full_algorithm_seconds": single_seconds, "whole_grid_seconds": grid_seconds,
            "legacy_full_frame_seconds": baseline_seconds,
            "legacy_to_default_ratio": baseline_seconds / single_seconds if single_seconds else None,
            "benchmark_limit": "One process/order and one timed full-frame run per route; old exhaustive cached-feature frame versus new bounded centroid frame, not identical retrieval coverage"},
        "warm_retrieval": _warm(representation, mapped)}
    artifact = save(engine, session, value, "All centroid variants and benchmark outputs frozen before model-reference evaluation")
    record = {"manifest": manifest_id, "versions": versions, "artifact": artifact, "frozen_before_reference_evaluation": True}
    identifier = engine.ledger.record(session, "event_group_centroid_frozen", key, record)
    return {"id": identifier, **record, "value": value}


def _references(engine: Research, session: str, parent_id: str, parent: Json, inputs: Json) -> Json:
    windows = judged.preparation.links.windows
    development = engine.ledger.artifacts.read(inputs["plan"]["development_sample_artifact"])
    old = windows._references(engine, session, inputs["temporal"], inputs["original"], inputs["plan"], development)
    rows = [{**row, "reference_origin": "original_development"} for row in old["rows"]]
    labels = dict(old["judged"])
    duplicates = []
    for packet in inputs["packets"]:
        value = parent["judgements"].get(packet["pair_id"])
        if not value or value["status"] != "completed":
            raise AuditError("Completed cross-window reference is unavailable")
        assessment = engine.ledger.get(value["assessment"], "event_pair_judgement")
        request = engine.ledger.artifacts.read(packet["request_ref"])
        if (assessment["request_ref"] != packet["request_ref"] or assessment["versions"] != parent["versions"]
                or assessment["result"]["label"] != value["label"] or assessment["plan"] != parent["manifest"]):
            raise AuditError("Cross-window reference request, versions or task lineage differs")
        validate_answer(request, assessment["result"])
        if packet["pair_id"] in labels:
            duplicates.append(packet["pair_id"])
            if labels[packet["pair_id"]]["label"] != value["label"]:
                raise AuditError("Repeated reference pair has conflicting labels; explicit amendment required")
        else:
            rows.append({"pair_id": packet["pair_id"], "left": packet["left"], "right": packet["right"],
                "reference_origin": "bounded_cross_window", "weight": 1., "inclusion_probability": None})
            labels[packet["pair_id"]] = value
        engine.ledger.append(session, "model.cache_reused", {"assessment": value["assessment"], "result": parent_id,
            "request": packet["request_ref"], "basis": "exact_version_saved_cross_window_judgment_for_exploratory_evaluation_only"})
    return {"rows": rows, "judged": labels, "failed_ids": old["failed_ids"], "versions": parent["versions"],
        "original_result": old["original_result"], "cross_window_result": parent_id,
        "original_reference_versions": old["versions"], "duplicate_pair_ids": duplicates,
        "weights_note": "Original probability weights preserved; new purposive references have descriptive weight1, never combined for population inference"}


def _partition(groups: list[Json], proposals: list[Json]) -> list[Json]:
    consumed = [group for proposal in proposals for group in proposal["old_group_ids"]]
    if len(consumed) != len(set(consumed)):
        raise AuditError("Disjoint centroid proposals reused an old group")
    output = [row for row in groups if row["group_id"] not in set(consumed)] + [
        {"group_id": row["proposal_id"], "members": row["article_members"]} for row in proposals]
    if set(judged.preparation.links.windows.temporal.refinement._owners(output)) != set(judged.preparation.links.windows.temporal.refinement._owners(groups)):
        raise AuditError("Centroid simulation changes article coverage")
    return output


def _sql(engine: Research, session: str, quality: Json, versions: Json) -> str:
    saved = judged.preparation.links.base._save(engine, session, quality["rows"], "Complete included pair IDs, denominators and reference rows for SQL check")
    calculation = judged.preparation.links.base._save(engine, session, {"sql": SQL,
        "parameters": [{"artifact": saved, "encoding": "exact_UTF8_JSON"}], "versions": versions,
        "unit": "Reused model-reference pairs; descriptive diagnostics, not independent dossiers"}, "Reference-count SQL before execution")
    observed = [dict(row) for row in engine.ledger.db.execute(SQL, (engine.ledger.artifacts.read_bytes(saved).decode("utf-8"),))]
    for row in observed:
        expected = quality["labels"][row["label"]]
        if any(row[field] != expected["total" if field == "pairs" else field] for field in ("pairs", "together", "separate", "unprocessed")):
            raise AuditError("SQL reference counts differ from frozen diagnostic rows")
    engine.ledger.append(session, "centroid_merge.sql.completed", {"calculation_artifact": calculation, "counts": observed})
    return calculation


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_group_centroid_result", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"reference_result", "study_key", "instruction", "output_directory"} or not engine.config.offline
            or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare exact saved reference result, immutable offline study, instruction and protected output")
    parent = _parent(engine, data["reference_result"])
    if context.versions and context.versions != parent["versions"]:
        raise ResearchError("Centroid context differs from original pilot")
    method = {"method": METHOD, "implementation": judged.preparation.links.base._hashes(CODE),
        "reference_result": data["reference_result"], "input_versions": parent["versions"], "instruction": data["instruction"],
        "representation": "Normalized mean of exact-body-deduplicated existing article unit vectors; retain all aliases, member dates and angular radius",
        "retrieval": "Exact float32 Faiss index; multi-article group queries against all valid group centroids; bounded32 oversample then float64 rerank to8 other groups",
        "gates": "Cross-window span>7, fixed centroid cutoffs0.90/0.95/0.975, all5 unchanged saved cross-article features; angularbound onlycertifies pooledcondition, inconclusivebounds fallback to cache",
        "proposals": "One strongest-center-first disjoint pair pass, no chain, iteration or active adoption; singleton-singleton omitted",
        "default_cutoff": .975, "thresholds": list(numeric.THRESHOLDS), "threshold_validated": False,
        "evaluation": "Freeze all variants before evaluating all54+30 reused references and10 judgedunions; no label-basedveto or winnerselection",
        "benchmark": "Separate cold artifact reads, centroidbuild/index/search/cachegate/defaultselection, wholegrid, priorcachedframe, warm64queries; audit overhead separate",
        "count_sql": SQL, "acceptance": "No new models, embeddings, accepted findings or membership changes",
        "output_directory": str(Path(data["output_directory"]).absolute())}
    key = data["study_key"]
    prior = judged.original._records(engine, "event_group_centroid_manifest", key)
    if prior and (len(prior) != 1 or prior[0][1]["method"] != method):
        raise ResearchError("Study key already binds another immutable centroid experiment")
    if prior:
        manifest_id, manifest = prior[0]
        versions = manifest["versions"]
    else:
        versions = dict(parent["versions"])
        for kind in ("protocol", "question", "selection", "dossier_definition", "profile", "retrieval_profile"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, parent["versions"]), {
                "kind": kind, "key": key, "content": {**method, "binding_role": kind,
                    "text": "Can collective group vectors produce fast conservative cross-window event-link proposals?",
                    "rules": "Reuse complete original pilot; uncertain and missing evidence never negative",
                    "unit": "Provisional same-event group links, not accepted event counts", "mode": "exploratory", "population_estimate": False},
                "amend_latest": True, "reason": "User requests a fast collective-vector method based on original grouping",
                "branch": "exploratory-fast-group-vector-mapping"})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_group_centroid_manifest", key, manifest)
    finished = judged.original._records(engine, "event_group_centroid_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Completed centroid result differs from exact method")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_centroid_diagnostic"})
        return _present(engine, session, context, *finished[0])
    intent = {"manifest": manifest_id, "new_models": 0, "new_embeddings": 0}
    engine.ledger.append(session, "centroid_merge.intended", intent)
    started = time.perf_counter()
    inputs = _inputs(engine, session, parent)
    load_seconds = time.perf_counter() - started
    frozen = judged.original._records(engine, "event_group_centroid_frozen", key)
    if frozen:
        if len(frozen) != 1 or frozen[0][1]["manifest"] != manifest_id or frozen[0][1]["versions"] != versions:
            raise AuditError("Frozen centroid candidates differ from method")
        frozen_id, saved = frozen[0]
        value = engine.ledger.artifacts.read(saved["artifact"])
        engine.ledger.append(session, "analysis.cache_reused", {"artifact": saved["artifact"], "basis": "frozen_label_blind_centroid_variants"})
    else:
        computed = _compute(engine, session, inputs, manifest_id, versions, key)
        frozen_id, value = computed["id"], computed["value"]
    engine.ledger.append(session, "centroid_merge.frozen", {"frozen": frozen_id, "mapping": value["mapping_diagnostics"]})
    refs = _references(engine, session, data["reference_result"], parent, inputs)
    windows = judged.preparation.links.windows
    missing = set(refs["failed_ids"])
    before = windows.quality(refs, inputs["groups"], missing)
    table, private = [], {}
    source_examples = []
    for cut in numeric.THRESHOLDS:
        variant = value["variants"][str(cut)]
        proposed = _partition(inputs["groups"], variant["proposals"])
        quality = windows.quality(refs, proposed, missing)
        calculation = _sql(engine, session, quality, versions)
        selected = {tuple(row["old_group_ids"]) for row in variant["proposals"]}
        nominated = {tuple(row["old_group_ids"]) for row in value["frame"] if row["status"] == "cross_window_nominated"}
        known = []
        for row in parent["proposals"]:
            pair = tuple(sorted(row["old_group_ids"]))
            known.append({"candidate_id": row["candidate_id"], "review_status": row["review_status"],
                "selected": pair in selected, "nominated": pair in nominated, "old_group_ids": list(pair)})
        count = dict(Counter(row["review_status"] for row in known if row["selected"]))
        oldquality = {row["pair_id"]: row for row in before["rows"]}
        changed = [row for row in quality["rows"] if row["together"] != oldquality[row["pair_id"]]["together"]]
        record = {"cutoff": cut, "proposed_group_pairs": len(variant["proposals"]),
            "judged_unions_selected": sum(row["selected"] for row in known), "judged_unions_total": len(known),
            "judged_unions_not_nominated": sum(not row["nominated"] for row in known),
            "selected_supported": count.get("provisional_pairwise_support_requires_cluster_review", 0),
            "selected_conflicting": count.get("conflicting_model_references", 0), "selected_uncertain": count.get("uncertain", 0),
            "proposed_groups_with_different_reference": quality["groups_with_different_event_reference"],
            "new_different_pair_comemberships": sum(row["reference"]["label"] == "different_event" and row["together"] is True for row in changed),
            "reference_labels": quality["labels"], "unprocessed_references": quality["unprocessed_references"],
            "counts": windows.numeric.stats(proposed, inputs["metadata"]), "calculation_artifact": calculation,
            "dispositions": variant["diagnostics"]["candidate_status_counts"]}
        table.append(record)
        private[str(cut)] = {"variant": variant, "partition": proposed, "quality": quality, "known_unions": known, "changed_references": changed}
        if cut == .975:
            for row in sorted(variant["proposals"], key=lambda p: (-p["centroid_cosine"], p["old_group_ids"]))[:3]:
                source_examples.append({"cosine": row["centroid_cosine"], "span_days": row["publication_span_days"],
                    "article_count": len(row["article_members"]), "articles": [inputs["metadata"][source] for source in row["article_members"]],
                    "reference_flags": quality["group_flags"][row["proposal_id"]], "semantic_status": "unjudged_proposal"})
    baseline_pairs = {tuple(row["old_group_ids"]) for row in value["legacy_frame"] if row.get("qualified")}
    nominated_pairs = {tuple(row["old_group_ids"]) for row in value["frame"]}
    directory = Path(data["output_directory"])
    exports = {"comparisons": windows.temporal.application._export(engine, session, directory, "centroid-variant-comparisons.json", private),
        "table": windows.temporal.application._export(engine, session, directory, "centroid-metrics.json", table),
        "mapping": windows.temporal.application._export(engine, session, directory, "collective-vector-mapping.json",
            {"centroid_artifact": value["centroid_artifact"], "shape": value["centroid_shape"], "group_ids": value["group_ids"], "rows": value["representation_rows"]})}
    unprocessed_groups = sum(row["status"] != "completed" for row in value["representation_rows"])
    result = {"versions": versions, "manifest": manifest_id, "reference_result": data["reference_result"], "frozen_candidates": frozen_id,
        "status": "completed_with_unprocessed_groups" if unprocessed_groups else "completed_offline_centroid_comparison", "default_cutoff": .975, "threshold_validated": False,
        "mapping_diagnostics": value["mapping_diagnostics"], "table": table, "timings": value["timings"],
        "cold_input_load_seconds": load_seconds, "preflight_and_registration_seconds": intent.get("preflight_and_registration_seconds"),
        "warm_retrieval": value["warm_retrieval"], "unprocessed_groups": unprocessed_groups,
        "original_cosine_qualified_group_pairs": len(baseline_pairs), "original_qualified_pairs_nominated": len(baseline_pairs & nominated_pairs),
        "reference_pairs": len(refs["rows"]), "duplicate_reference_pairs": len(refs["duplicate_pair_ids"]), "baseline_quality": before,
        "dataset_articles": inputs["comparison"]["dataset_articles"], "missing_vector_articles": inputs["comparison"]["missing_vector_articles"],
        "missing_date_articles": inputs["comparison"]["missing_date_articles"], "saved_feature_failures": inputs["temporal"]["failed_feature_pairs"],
        "examples": source_examples, "exports": exports, "new_model_calls": 0, "new_embedding_requests": 0,
        "actual_group_merges": 0, "accepted_dossiers": 0, "current_memberships_changed": False, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_group_centroid_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    from .rag_answers import _link
    t, m, warm = result["timings"], result["mapping_diagnostics"], result["warm_retrieval"]
    latency = "unavailable" if warm["median_ms"] is None else f"median {warm['median_ms']:.2f}ms, p95 {warm['p95_ms']:.2f}ms"
    lines = ["**Tested: fast collective-vector mapping between seven-day groups.**", "",
        "Method: cache one normalized, duplicate-discounted mean vector per group; retrieve eight nearby groups; "
        "apply the original five saved similarity checks only to those candidates; propose disjoint pairs in one pass. "
        "No new article judging, embeddings or LLM calls. Audit validation still checks stored source/request payloads.", "",
        f"Scope: {result['dataset_articles']:,} pilot articles; {m['valid_centroids']:,} collective vectors, "
        f"{m['multi_group_queries']:,} multi-article group queries, {m['candidate_pairs']:,} nominated pairs. "
        f"Recovered {result['original_qualified_pairs_nominated']}/{result['original_cosine_qualified_group_pairs']} earlier cosine-qualified cross-window pairs. "
        "Top-eight retrieval is bounded and omits singleton-to-singleton searches.", "",
        "| Collective cosine cutoff | Proposed links | Of ten judged unions: supported / conflicting / uncertain selected | Newly joined different-event reference pairs |",
        "| --- | ---: | --- | ---: |"]
    for row in result["table"]:
        lines.append(f"| {row['cutoff']:.3f} | {row['proposed_group_pairs']} | {row['selected_supported']} / {row['selected_conflicting']} / {row['selected_uncertain']} | {row['new_different_pair_comemberships']} |")
    lines += ["", f"Prospective strict default: **0.975, unvalidated**. All three options were frozen before evaluation against "
        f"{result['reference_pairs']} reused model-reference pairs and the ten previously judged unions. "
        "These selected development references are not independent accuracy estimates, human gold or calibrated probabilities.", "",
        f"**Speed:** full default numerical route {t['default_full_algorithm_seconds']:.3f}s; prior cached-feature full-frame route "
        f"{t['legacy_full_frame_seconds']:.3f}s ({t['legacy_to_default_ratio']:.2f}× ratio). The new route searches a smaller bounded frame, "
        "so this is not an equal-coverage speed comparison. "
        f"Warm retrieval: {latency} across {warm['queries']} queries; "
        "retrieval only, excluding gates, preflight and durable writes.", "",
        f"Input loading {result['cold_input_load_seconds']:.2f}s; full audit/preparation overhead "
        + (f"{result['preflight_and_registration_seconds']:.2f}s" if result['preflight_and_registration_seconds'] is not None else "unavailable")
        + ". Cached numerical speed does not make the full audited invocation instantaneous.", "",
        "Default candidate dispositions: " + str(next(row["dispositions"] for row in result["table"] if row["cutoff"] == .975))
        + f". All {result['reference_pairs']} reference-pair diagnostics retain together/separate/unprocessed states; unselected or unprocessed cases are not negative labels."]
    for n, example in enumerate(result["examples"], 1):
        flags = example["reference_flags"]
        lines += ["", f"{n}. Provisional link: collective cosine {example['cosine']:.5f}, {example['article_count']} articles, "
            f"{example['span_days']} publication days; saved reference flags: "
            f"same {len(flags['same_event'])}, different {len(flags['different_event'])}, uncertain {len(flags['uncertain'])}. "
            + "; ".join(_link(article.get("title") or article["source_version"], article.get("url")) for article in example["articles"])]
    lines += ["", f"Coverage gaps: {result['missing_vector_articles']} missing article vectors, {result['missing_date_articles']} unusable publication dates; "
        f"{result['unprocessed_groups']} unprocessed current groups; {result['saved_feature_failures']} saved-feature failures; "
        f"{m['tie_truncation_queries']} queries with boundary-tie ambiguity. Missing scores are unresolved, never different-event findings. "
        "Current memberships unchanged; actual merges/accepted dossiers/new models/new embeddings: 0.", "",
        "[All comparisons](" + result["exports"]["comparisons"]["path"].replace("\\", "/") + ")"]
    return "\n".join(lines)
