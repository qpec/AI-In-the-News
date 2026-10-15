"""Model-free, audited preparation of a frozen event-pair development study."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import event_pair_sampling as sampling
from .aws_clustering_evaluation import aggregate, vectors
from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .event_clustering_evaluation import saved_inputs
from .event_pair_answers import TASK_INSTRUCTION

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "event-pair-frozen-reference-study-v1"
INSTRUCTIONS = TASK_INSTRUCTION
CRITERION: Json = {
    "labels": ["same_event", "different_event", "uncertain"],
    "instructions": INSTRUCTIONS,
    "minimum_clear_same": 5, "minimum_clear_different": 5,
    "maximum_observed_uncertain_fraction": .20, "maximum_weighted_uncertain_fraction": .20,
    "minimum_pessimistic_weighted_precision": .90, "minimum_pessimistic_weighted_recall": .80,
    "complete_processing_required": True, "validation_minimum_links": 10, "validation_minimum_nonlinks": 5,
    "cutoff_selection": "fixed grid plus observed development distance boundaries in (0,0.40]",
    "winner": "maximum pessimistic weighted F1; ties choose smaller cosine distance",
    "interpretation": "Pragmatic model-reference screen only; not human event validity or population accuracy",
}
BUDGET: Json = {"development_primary_pairs": 54, "validation_link_pairs": 30,
    "validation_nonlink_pairs": 6, "primary_pairs": 90, "shared_known_invalid_retry_reserve": 10,
    "maximum_pair_attempts": 100, "maximum_article_exposures": 200,
    "unknown_outcomes": "Count as spent; never retry automatically", "automatic_replicates": 0,
    "approval": "No model execution permission is granted or reused by this offline plan"}
LIMITATIONS = [*sampling.LIMITATIONS,
    "Exact-body-disjoint folds are not proven event-disjoint: different reporting of one event may cross folds.",
    "Six sampled predicted nonlinks provide weak recall information; no confident corpus recall claim is justified.",
    "A pairwise distance cutoff is a proxy, not validation of complete-link or DBSCAN clusters.",
    "Mean passage vectors blend multi-event reports and repeated overlapping windows.",
    "Missing vectors and excluded duplicate copies are not different-event findings."]


def _method() -> Json:
    return {"method": METHOD, "criterion": CRITERION, "budget": BUDGET,
        "representation": "L2-normalized float64 sum of every saved unit passage-window vector; float32 output",
        "frame": "Full original dataset vector-bearing sources; lowest-ID exact-body representatives; body-hash 70/30 folds; K8 exact float32 Faiss IP plus 512 uniform unordered background pairs per fold; float64 cosine reranking",
        "development": {"pairs": 54, "bands": list(sampling.BANDS), "quotas": list(sampling.QUOTAS),
            "redistribution": "Before labels, ascending-band round-robin; retain n/N in every nonempty band"},
        "validation": "Freeze full validation frame before judging; candidate chosen only from development; SRS30 links plus6 nonlinks, no deficit replacement, no held-out reuse",
        "grid": list(sampling.GRID), "limitations": LIMITATIONS,
        "implementation_hashes": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in
            (Path(__file__), Path(sampling.__file__), Path(__file__).with_name("event_pair_answers.py"))},
        "libraries": {name: importlib.metadata.version(name) for name in ("numpy", "faiss-cpu")}}


def _save(engine: Research, session: str, value: Any, purpose: str, *, binary: bool = False) -> str:
    artifact = engine.ledger.artifacts.put_bytes(value) if binary else engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": artifact, "purpose": purpose})
    return str(artifact)


def _diagnostics(frame: Json, development: Json) -> Json:
    origins = {}
    for fold in ("development", "validation"):
        rows = [row for row in frame["rows"] if row["fold"] == fold]
        origins[fold] = {"pairs": len(rows), "nearest_neighbor_only": sum(row["origin"] == ["nearest_neighbor"] for row in rows),
            "background_only": sum(row["origin"] == ["background"] for row in rows),
            "both_origins": sum(len(row["origin"]) == 2 for row in rows)}
    reuse = Counter(source for row in development["rows"] for source in (row["left"], row["right"]))
    weights = [row["weight"] for row in development["rows"]]
    return {"frame_origins": origins, "development_article_exposures": sum(reuse.values()),
        "development_unique_articles": len(reuse), "maximum_development_article_reuse": max(reuse.values(), default=0),
        "kish_weight_size_diagnostic": sum(weights) ** 2 / sum(weight ** 2 for weight in weights) if weights else 0.,
        "interpretation": "Descriptive reuse/weight diagnostics only; not independent sample size or confidence"}


def load_plan(engine: Research, session: str, plan_id: str) -> tuple[Json, Json, Json]:
    """Verify frozen artifacts/bindings; no labels, model execution or resampling."""
    require_active(engine, session)
    ledger = engine.ledger
    plan = ledger.get(plan_id, "event_pair_plan")
    manifest = ledger.get(plan["manifest"], "event_pair_study_manifest")
    index = ledger.get(plan["index"], "vector_index")
    if (plan["versions"] != manifest["versions"] or plan["study_binding"] != manifest["study_binding"]
            or plan["input_index_versions"] != index["versions"]
            or plan["versions"]["dataset"] != index["versions"]["dataset"]
            or plan["criterion_hash"] != digest(CRITERION)
            or manifest["method"] != _method()
            or ledger.get(plan["versions"]["prompt"], "prompt")["content"]["instructions"] != INSTRUCTIONS
            or ledger.get(plan["versions"]["protocol"], "protocol")["content"] != manifest["method"]):
        raise AuditError("Event-pair plan method, criterion or original index bindings differ")
    frame = ledger.artifacts.read(plan["frame_artifact"])
    development = ledger.artifacts.read(plan["development_sample_artifact"])
    raw = ledger.artifacts.read_bytes(plan["pooled_vectors_artifact"])
    mapping = ledger.artifacts.read(plan["mapping_artifact"])
    if (digest(frame["rows"]) != frame["frame_hash"] or frame["frame_hash"] != plan["frame_hash"]
            or frame["configuration"]["seed"] != plan["seed"]
            or frame["vector_sha256"] != hashlib.sha256(raw).hexdigest()
            or len(raw) != plan["processed_articles"] * index["dimensions"] * 4
            or frame["vector_article_order"] != [row["source_version"] for row in mapping]
            or canonical(development) != canonical(sampling.sample_development(frame, seed=plan["seed"]))):
        raise AuditError("Event-pair frozen frame, vector mapping or sample differs")
    folds = {row["article_id"]: row["fold"] for row in frame["representatives"]}
    if any(folds[row["left"]] != row["fold"] or folds[row["right"]] != row["fold"] for row in frame["rows"]):
        raise AuditError("Event-pair frame crosses source-disjoint folds")
    return plan, frame, development


def prepare(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"previous_result", "seed", "key"} or not isinstance(data.get("previous_result"), str):
        raise ResearchError("Declare an immutable corrected event-clustering result; no model execution fields are allowed")
    seed, key = data.get("seed", METHOD), data.get("key", METHOD)
    if any(not isinstance(value, str) or not value.strip() or len(value) > 128 for value in (seed, key)):
        raise ResearchError("Declare nonempty bounded study seed and stable key")
    ledger = engine.ledger
    comparison = ledger.get(data["previous_result"], "event_clustering_evaluation")
    previous, _, old_ids, old_values = saved_inputs(engine, session, comparison["previous_result"])
    if (comparison["index"] != previous["index"]
            or comparison["pooled_vectors_artifact"] != previous["pooled_vectors_artifact"]
            or comparison["mapping_artifact"] != previous["mapping_artifact"]
            or comparison["input_index_versions"] != previous["input_index_versions"]):
        raise AuditError("Corrected comparison differs from its exact AWS input lineage")
    index = ledger.get(previous["index"], "vector_index")
    if any(index["versions"].get(kind) != identifier for kind, identifier in context.versions.items()):
        raise ResearchError("Study context differs from original index")
    method = _method()
    binding = digest({"previous_result": data["previous_result"], "seed": seed, "method": method,
                      "index": previous["index"], "input_index_versions": index["versions"]})
    existing = list(ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_pair_study_manifest' AND logical_key=?", (key,)))
    if any(json.loads(row["payload"])["study_binding"] != binding for row in existing):
        raise ResearchError("Stable study key already binds another parent, seed, method or selection; cannot reseal validation")
    completed = ledger.db.execute("SELECT id FROM records WHERE kind='event_pair_plan' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (key,)).fetchone()
    if completed:
        plan, _, _ = load_plan(engine, session, completed["id"])
        ledger.append(session, "event_pair.plan.reused", {"plan": completed["id"], "study_binding": binding})
        return {"id": completed["id"], **plan, "reused": True}
    bound = Context(context.objective, context.actor, dict(index["versions"]))
    versions = dict(bound.versions)
    contents = {"protocol": method,
        "question": {"text": "Can saved article-vector cosine distance support a provisional same-real-world-event linking screen?"},
        "selection": {"rules": {"dataset": versions["dataset"], "all_original_sources": True,
            "selection_before_vector_availability": True, "seed": seed, "exact_body_representatives": True}},
        "dossier_definition": {"unit": "One real-world event across reporting sources/publication times, without incident or harm requirement; no dossiers accepted by this study"},
        "codebook": {"labels": CRITERION["labels"], "definitions": INSTRUCTIONS},
        "prompt": {"instructions": INSTRUCTIONS, "criterion_hash": digest(CRITERION)},
        "profile": {"mode": "exploratory", "population_estimate": False, "method": METHOD,
            "human_validated": False, "models_in_preparation": False}}
    for kind, content in contents.items():
        versions[kind] = engine._version(session, bound, {"kind": kind, "key": key, "content": content,
            "amend_latest": True, "reason": "Register an offline frozen event-pair study before preparation"})["id"]
    dataset = ledger.get(index["versions"]["dataset"], "dataset")
    selected = list(dataset["source_versions"])
    if not 2 <= len(selected) <= min(20000, engine.config.max_articles) or len(set(selected)) != len(selected):
        raise ResearchError("Full original study dataset must contain 2..20000 unique sources")
    manifest = {"versions": versions, "input_index_versions": index["versions"], "index": previous["index"],
        "previous_result": data["previous_result"], "original_aws_result": comparison["previous_result"],
        "seed": seed, "study_key": key, "study_binding": binding, "method": method,
        "selected_sources": selected, "started_at": utc(), "budget": BUDGET, "model_calls": 0}
    manifest_id = ledger.record(session, "event_pair_study_manifest", key, manifest)
    ledger.append(session, "event_pair.preparation.intended", {"manifest": manifest_id, "study_binding": binding,
        "versions": versions, "selection": selected, "model_calls": 0})
    metadata_sql = "SELECT id,payload FROM sources WHERE id IN (SELECT value FROM json_each(?))"
    parameters = [canonical(selected)]
    ledger.append(session, "event_pair.sources.inspection.intended", {"sql": metadata_sql, "parameters": parameters,
        "purpose": "Exact body SHA256 and stored metadata only, no semantic interpretation"})
    metadata = {}
    unavailable_text = set()
    for row in ledger.db.execute(metadata_sql, parameters):
        source = json.loads(row["payload"])
        body = source.get("body") or ""
        if source.get("retention") != "permitted" or not body.strip():
            unavailable_text.add(row["id"])
        metadata[row["id"]] = {"source_version": row["id"],
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "title": source.get("title"), "url": source.get("url"), "published_at": source.get("published_at")}
    if set(metadata) != set(selected):
        raise AuditError("Study metadata coverage differs from full dataset")
    metadata_artifact = _save(engine, session, metadata, "Source summaries and exact body hashes, without article text")
    ledger.append(session, "event_pair.sources.inspected", {"sql": metadata_sql, "parameters": parameters,
        "source_ids": selected, "metadata_artifact": metadata_artifact, "semantic_judgements": 0})
    with vectors(engine, session, index) as (rows, matrix):
        ids, pooled, missing, mapping = aggregate(rows, matrix, selected)
    if unavailable_text.intersection(ids):
        raise ResearchError("Vector-bearing study articles require complete permitted stored text; preparation stopped")
    positions = {source: ordinal for ordinal, source in enumerate(ids)}
    if any(source not in positions or pooled[positions[source]].astype("<f4").tobytes() != old_values[ordinal].astype("<f4").tobytes()
           for ordinal, source in enumerate(old_ids)):
        raise AuditError("Full-frame pooling differs byte-for-byte from saved overlapping pilot vectors")
    ledger.append(session, "event_pair.vectors.overlap.verified", {"manifest": manifest_id,
        "compared_articles": len(old_ids), "byte_equal": True, "previous_pooled_vectors_artifact": previous["pooled_vectors_artifact"]})
    if len(ids) < 2:
        raise ResearchError("Fewer than two articles have saved vectors; no pair frame can be prepared")
    pooled_artifact = _save(engine, session, pooled.astype("<f4").tobytes(), "Full original article-vector matrix", binary=True)
    mapping_artifact = _save(engine, session, mapping, "Full article-to-original-passage vector mapping")
    frame = sampling.build_frame(pooled, ids, {source: metadata[source]["body_sha256"] for source in ids}, seed=seed)
    frame_artifact = _save(engine, session, frame, "Frozen disjoint development and sealed validation pair frames")
    development = sampling.sample_development(frame, seed=seed)
    development_artifact = _save(engine, session, development, "Frozen probability-logged development sample; no labels")
    examples = [{"pair_id": row["pair_id"], "distance": row["distance"], "stratum": row["stratum"],
                 "inclusion_probability": row["inclusion_probability"],
                 "articles": [metadata[row["left"]], metadata[row["right"]]]} for row in development["rows"][:5]]
    result = {"versions": versions, "input_index_versions": index["versions"], "index": previous["index"],
        "manifest": manifest_id, "previous_result": data["previous_result"], "study_key": key, "study_binding": binding,
        "seed": seed, "criterion_hash": digest(CRITERION), "budget": BUDGET,
        "frame_artifact": frame_artifact, "frame_hash": frame["frame_hash"],
        "development_sample_artifact": development_artifact, "metadata_artifact": metadata_artifact,
        "pooled_vectors_artifact": pooled_artifact, "mapping_artifact": mapping_artifact,
        "dataset_articles": len(selected), "selected_articles": len(selected), "processed_articles": len(ids),
        "missing_articles": len(missing), "missing": missing, "outside_dataset_exclusions": 0,
        "unique_bodies": frame["unique_bodies"], "excluded_duplicate_copies": frame["excluded_duplicate_copies"],
        "fold_counts": frame["fold_counts"], "diagnostics": _diagnostics(frame, development),
        "development_pairs": len(development["rows"]), "development_strata": development["strata"],
        "sealed_validation_pairs": sum(row["fold"] == "validation" for row in frame["rows"]),
        "overlap_vectors_checked": len(old_ids), "overlap_vectors_byte_equal": True,
        "examples": examples, "model_calls": 0, "new_embedding_requests": 0, "network_calls": 0,
        "human_event_labels": 0, "model_pair_labels": 0, "candidate_cutoff": None, "accepted_dossiers": 0,
        "pending_model_pairs": len(development["rows"]), "pending_preparation_articles": 0,
        "status": "prepared_no_model_authorization", "started_at": manifest["started_at"], "completed_at": utc(),
        "limitations": LIMITATIONS}
    identifier = ledger.record(session, "event_pair_plan", key, result)
    return {"id": identifier, **result}


def render(plan: Json) -> str:
    """Concrete preparation results, explicitly distinct from judged research."""
    from .provisional_tags import literal
    from urllib.parse import quote, urlsplit
    lines = ["Frozen event-pair study prepared — no article judging executed.", "",
        f"Full original dataset: {plan['dataset_articles']} articles; saved pooled vectors: {plan['processed_articles']}; "
        f"missing vectors: {plan['missing_articles']}; duplicate-body copies excluded from the primary frame: {plan['excluded_duplicate_copies']}; "
        f"unique bodies: {plan['unique_bodies']}. Preparation pending: {plan['pending_preparation_articles']}.",
        f"Prior pilot overlap: {plan['overlap_vectors_checked']} vectors checked byte-for-byte; equal={plan['overlap_vectors_byte_equal']}.", "",
        "| Fold | Representative articles | Frozen candidate pairs | Background pairs sampled |",
        "|---|---:|---:|---:|"]
    for fold, counts in plan["fold_counts"].items():
        lines.append(f"| {fold} | {counts['representatives']} | {plan['diagnostics']['frame_origins'][fold]['pairs']} | {counts['background_pairs']} |")
    lines += ["", f"Development sample: {plan['development_pairs']} pairs; pending model judgements: {plan['pending_model_pairs']}. "
        f"Sealed held-out frame: {plan['sealed_validation_pairs']} pairs; no held-out judgements or candidate-dependent sample yet.", "",
        "| Distance band | Frame pairs N | Sampled n | Inclusion probability |", "|---|---:|---:|---:|"]
    for index, row in enumerate(plan["development_strata"]):
        lines.append(f"| {sampling.BANDS[index]:g}–{sampling.BANDS[index+1]:g} | {row['N']} | {row['n']} | {row['inclusion_probability']:.8g} |")
    lines += ["", "Unjudged development examples:", ""]
    if not plan["examples"]:
        lines.append("No development pairs available.")
    shown: set[str] = set()
    for example in plan["examples"]:
        if example["stratum"] in shown or len(shown) >= 3:
            continue
        shown.add(example["stratum"])
        lines.append(f"- Pair `{example['pair_id'][:12]}`: cosine distance {example['distance']:.8g}; {example['stratum']}; unjudged.")
        for article in example["articles"]:
            title = literal(article.get("title") or article["source_version"])
            url = article.get("url")
            try:
                if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).netloc:
                    title = f"[{title}]({quote(url, safe=':/?#=&%+-._~')})"
            except ValueError:
                pass
            lines.append("  - " + title + "; publication time: " + literal(str(article.get("published_at") or "unavailable")))
    lines += ["", "Candidate cutoff: unavailable; same/different/uncertain labels: 0/0/0; accepted dossiers: 0. "
        "No new embeddings, model calls or network calls. The proposed budget is 90 primary pair attempts plus 10 shared known-invalid retries "
        "(100 pairs / 200 article exposures maximum); this plan grants no model permission.", "",
        "Limits: " + " ".join(plan["limitations"])]
    return "\n".join(lines)
