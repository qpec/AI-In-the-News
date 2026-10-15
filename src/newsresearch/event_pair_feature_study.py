"""Append-only passage-feature experiment under the original event-pair budget."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import event_pair_experiment as original
from . import event_pair_features as features
from . import event_pair_sampling as sampling
from . import event_pair_selection as selection
from .aws_clustering_evaluation import vectors
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_answers import validate_answer
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "event-pair-passage-selective-experiment-v1"
CODE = ("event_pair_feature_study.py", "event_pair_features.py", "event_pair_selection.py")


def _hashes(names: tuple[str, ...]) -> Json:
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names}


def _save(engine: Research, session: str, value: Any, purpose: str) -> str:
    artifact = engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": artifact, "purpose": purpose})
    return artifact


def parent_binding(engine: Research, parent: Json, plan_id: str, plan: Json) -> tuple[str, Json]:
    records = original._records(engine, "event_pair_run_authorization", plan["study_key"])
    if len(records) != 1:
        raise AuditError("Child requires exactly one immutable original authorization")
    identifier, saved = records[0]
    binding = saved["binding"]
    if (binding["plan"] != plan_id or binding["study_binding"] != plan["study_binding"]
            or binding["versions"] != parent["versions"] or binding["config"] != parent["config"]
            or binding["implementation"] != _hashes(("event_pair_experiment.py", "codex_provider.py", "event_pair_answers.py"))
            or parent["study_key"] != plan["study_key"] or parent["plan"] != plan_id
            or engine.ledger.get(parent["run_approval"], "policy")["content"] != binding["approval"]):
        raise ResearchError("Original plan, authorization, configuration, judge versions or implementation changed")
    return identifier, binding


def references(engine: Research, session: str, parent: Json, plan: Json, rows: list[Json]) -> dict[str, Json]:
    judgments = parent["development_judgements"]
    if set(judgments) != {row["pair_id"] for row in rows}:
        raise ResearchError("Child must retain exactly the original development references")
    for row in rows:
        value = judgments[row["pair_id"]]
        if value.get("status") != "completed":
            raise ResearchError("Incomplete development processing blocks feature selection")
        saved = engine.ledger.get(value["assessment"], "event_pair_judgement")
        request = engine.ledger.artifacts.read(saved["request_ref"])
        key = digest({"plan": parent["plan"], "request": request, "config": parent["config"], "method": original.METHOD})
        if (saved["versions"] != parent["versions"] or request["versions"] != parent["versions"]
                or saved["plan"] != parent["plan"] or saved["event_pair_study"] != plan["study_key"]
                or saved["pair_id"] != row["pair_id"] or saved["task_key"] != key
                or [article["source_version"] for article in request["articles"]] != [row["left"], row["right"]]
                or saved["result"]["label"] != value["label"]
                or not engine.ledger.db.execute("SELECT 1 FROM attempts WHERE result_id=? AND task_key=? AND status='valid'",
                                               (value["assessment"], key)).fetchone()):
            raise AuditError("Development reference differs from frozen source-bound judge contract")
        validate_answer(request, saved["result"])
        engine.ledger.append(session, "model.cache_reused", {"task_key": key, "assessment": value["assessment"],
            "plan": parent["plan"], "basis": "explicit_exact_version_reference_reuse_for_child_feature_comparison"})
    return judgments


def predicts(row: Json, candidate: Json) -> bool:
    value, gate = row.get("features", {}).get(candidate["feature"]), candidate["publication_gap_days"]
    return bool(value is not None and value >= candidate["threshold"]
                and (gate is None or row.get("publication_gap_days") is not None and row["publication_gap_days"] <= gate))


def validation_sample(rows: list[Json], frame_hash: str, candidate: Json, seed: str) -> Json:
    if any(row["fold"] != "validation" for row in rows):
        raise ResearchError("Held-out sampling accepts only the frozen validation fold")
    groups: list[list[Json]] = [[], []]
    for row in rows:
        groups[0 if predicts(row, candidate) else 1].append(row)
    return sampling._sample_strata({"frame_hash": frame_hash}, groups, [30, 6], ["auto_link", "review"],
        seed=seed, purpose=METHOD + ":single-heldout:" + digest(candidate))


def _compute(engine: Research, session: str, matrix: Any, mapping: dict[str, list[int]],
             rows: list[Json], metadata: Json, phase: str) -> list[Json]:
    output: list[Json] = []
    ordered = sorted(rows, key=lambda row: (row["left"], row["right"], row["pair_id"]))
    published = {source: item.get("published_at") for source, item in metadata.items()}
    for offset in range(0, len(ordered), features.MAX_PAIRS):
        batch = ordered[offset:offset + features.MAX_PAIRS]
        try:
            computed = features.pair_features(matrix, mapping, batch, published)
        except ResearchError:
            computed = []
            for pair in batch:
                try:
                    computed.extend(features.pair_features(matrix, mapping, [pair], published))
                except ResearchError as error:
                    computed.append({"pair_id": pair["pair_id"], "status": "failed",
                        "features": {name: None for name in selection.FEATURES},
                        "publication_gap_days": None, "failure_reason": str(error)})
        merged = []
        for source, value in zip(batch, computed, strict=True):
            if source["pair_id"] != value["pair_id"]:
                raise AuditError("Feature computation changed pair identity")
            value["features"]["pooled_cosine"] = 1. - source["distance"]
            value["pooled_basis"] = "exact frozen article-pair distance; no numerical reaggregation"
            merged.append({**source, **value})
        artifact = _save(engine, session, merged, "Required complete feature batch, including failed/null rows")
        engine.ledger.append(session, "event_pair.features.batch_saved", {"artifact": artifact, "phase": phase,
            "offset": offset, "pairs": len(merged), "pair_ids": [row["pair_id"] for row in merged]})
        output.extend(merged)
    return sorted(output, key=lambda row: row["pair_id"])


def _descriptive(metrics: Json) -> list[Json]:
    output = []
    for variant in metrics["candidates"]:
        pool = [item for item in metrics["full_grid"] if item["feature"] == variant["feature"]
                and item["publication_gap_days"] == variant["publication_gap_days"]
                and item["metrics"]["selected_label_counts"]["same_event"] >= 8]
        best = max(pool, key=lambda item: (item["metrics"]["precision_pessimistic_weighted"] or -1,
            item["metrics"]["known_same_coverage_weighted"] or -1, item["threshold"])) if pool else None
        output.append({**variant, "descriptive_best_with_eight_same": best})
    return output


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) - {"parent_result", "experiment_key", "execute_validation", "reuse_cache", "workers", "continuation_instruction"}
            or data.get("reuse_cache") is not True or type(data.get("execute_validation", False)) is not bool
            or type(data.get("workers", 4)) is not int or not 1 <= data.get("workers", 4) <= 4
            or any(not isinstance(data.get(k), str) or not data[k].strip()
                   for k in ("parent_result", "experiment_key", "continuation_instruction"))):
        raise ResearchError("Declare parent, experiment key, exact reuse and continuation instruction; workers 1..4")
    started = utc()
    parent = engine.ledger.get(data["parent_result"], "event_pair_experiment")
    plan, frame, development = load_plan(engine, session, parent["plan"])
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("Child context must match frozen plan versions")
    auth_id, auth = parent_binding(engine, parent, parent["plan"], plan)
    if parent.get("frozen_candidate") or parent.get("validation_pairs"):
        raise ResearchError("Original holdout already selected or opened; cannot retune")
    key = data["experiment_key"]
    policy = {"method": METHOD, "parent": data["parent_result"], "original_authorization": auth_id,
        "selection": selection.POLICY, "feature_method": features.METHOD, "implementation": _hashes(CODE),
        "reference_reuse": "All original development references including uncertain; original sampling probabilities",
        "predictors": "Retained embedding vectors and publication metadata only; no judge-produced facts or labels",
        "descriptive_variant_table": "Highest weighted pessimistic precision with at least eight same references, then coverage, then stricter threshold",
        "holdout": "One child candidate frozen before label-blind held-out features; shared opening registry; 30 links plus six review pairs",
        "budget": "Original study-wide 100 intended pairs/200 exposures, 90 primary plus ten known-invalid retries; never reset",
        "continuation_instruction": data["continuation_instruction"], "observed_chat_timestamp": None,
        "no_new_embeddings": True, "no_collection": True, "accepted_dossiers": 0}
    prior = original._records(engine, "event_pair_feature_manifest", plan["study_key"])
    if prior and (len(prior) != 1 or prior[0][1]["method"] != policy or prior[0][1]["experiment_key"] != key):
        raise ResearchError("One immutable child feature experiment per study; cannot reset, retune or reseal")
    child_versions = dict(plan["versions"])
    for kind in ("protocol", "profile", "selection"):
        child_versions[kind] = engine._version(session, Context(context.objective, context.actor, plan["versions"]),
            {"kind": kind, "key": key, "content": {**policy, "binding_role": kind, "mode": "exploratory",
                 "rules": "Frozen pair frame; all original references and n/N weights; registered selective-link policy",
                 "population_estimate": False}, "amend_latest": True,
             "reason": "Append registered selective passage-feature branch; original inconclusive result unchanged"})["id"]
    manifest = engine.ledger.record(session, "event_pair_feature_manifest", plan["study_key"],
        {"versions": child_versions, "method": policy, "experiment_key": key, "original_judge_versions": parent["versions"]})
    judged = references(engine, session, parent, plan, development["rows"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    mapped = engine.ledger.artifacts.read(plan["mapping_artifact"])
    mapping = {item["source_version"]: [chunk["row"] for chunk in item["chunks"]] for item in mapped}
    old_attempts = len(original._spent(engine, plan["study_key"]))
    index = engine.ledger.get(plan["index"], "vector_index")
    validation_rows: list[Json] = []
    validation_judgments: dict[str, Json] = {}
    validation: Json | None = None
    heldout_features: list[Json] = []
    holdout_obstacle: str | None = None
    frozen_id: str | None = None
    stop = False
    with vectors(engine, session, index) as (passages, matrix):
        for item in mapped:
            for chunk in item["chunks"]:
                row = passages[chunk["row"]]
                if (row["source_version"] != item["source_version"] or row["id"] != chunk["chunk"]
                        or row["passage_id"] != chunk["passage"]):
                    raise AuditError("Frozen passage mapping differs from retained index")
        dev_rows = _compute(engine, session, matrix, mapping, development["rows"], metadata, "development")
        metrics = selection.evaluate(dev_rows, judged)
        candidate = metrics["best_candidate"]
        dev_artifact = _save(engine, session, dev_rows, "Required frozen development features")
        metrics_artifact = _save(engine, session, metrics, "Required complete development grid and all failures")
        frozen = original._records(engine, "event_pair_feature_candidate", plan["study_key"])
        if len(frozen) > 1:
            raise AuditError("More than one frozen child candidate")
        candidate_binding = {"versions": child_versions, "manifest": manifest, "parent": data["parent_result"],
            "original_authorization": auth_id, "candidate": candidate, "development_features": dev_artifact,
            "development_metrics": metrics_artifact}
        if frozen:
            frozen_id, saved = frozen[0]
            if saved["binding"] != candidate_binding:
                raise ResearchError("Frozen child candidate cannot be retuned")
        elif candidate is not None:
            frozen_id = engine.ledger.record(session, "event_pair_feature_candidate", plan["study_key"],
                {"versions": child_versions, "binding": candidate_binding, "frozen_at": utc()})
        opened = original._records(engine, "event_pair_holdout_opened", plan["study_key"])
        if opened and (len(opened) != 1 or opened[0][1]["frozen_candidate"] != frozen_id
                       or opened[0][1].get("child_manifest") != manifest):
            raise ResearchError("Shared holdout already opened by another candidate; no retuning")
        if candidate is not None and data.get("execute_validation") is True:
            if engine.config.offline:
                raise ResearchError("Held-out judging requires process-local online configuration")
            approval = original._approval({"run_approval": auth["approval"]}, parent["plan"], plan)
            config_input = {k: auth["config"][k] for k in ("codex_model", "codex_executable")}
            current = original._config(engine, config_input)
            if any(current[k] != v for k, v in auth["config"].items() if k != "configuration_origin"):
                raise ResearchError("Original Codex binary/configuration changed")
            if opened:
                sample = engine.ledger.artifacts.read(opened[0][1]["sample_artifact"])
            else:
                heldout = [row for row in frame["rows"] if row["fold"] == "validation"]
                heldout_features = _compute(engine, session, matrix, mapping, heldout, metadata, "validation_frame")
                feature_ref = _save(engine, session, heldout_features, "Required label-blind held-out frame features")
                sample = None
                if any(row["status"] != "completed" or row["features"].get(candidate["feature"]) is None for row in heldout_features):
                    holdout_obstacle = "incomplete_validation_features; labels remain sealed"
                else:
                    proposed = validation_sample(heldout_features, frame["frame_hash"], candidate, plan["seed"])
                    if proposed["strata"][0]["n"] < selection.POLICY["validation"]["minimum_selected_pairs"]:
                        holdout_obstacle = "insufficient_available_validation_auto_links; labels remain sealed"
                    else:
                        sample = proposed
                        sample_ref = _save(engine, session, sample, "Required frozen held-out sample before first dispatch")
                        engine.ledger.record(session, "event_pair_holdout_opened", plan["study_key"], {
                            "binding": digest(auth), "versions": parent["versions"], "plan": parent["plan"],
                            "frozen_candidate": frozen_id, "child_manifest": manifest, "sample_artifact": sample_ref,
                            "frame_features_artifact": feature_ref, "opened_at": utc(), "branch": METHOD})
            if sample is not None:
                validation_rows = sample["rows"]
                validation_judgments, stop = original._phase(engine, session, validation_rows, parent["plan"], plan,
                    parent["versions"], approval, auth["config"], {"workers": data.get("workers", 4), "reuse_cache": True})
                validation = selection.validate(validation_rows, validation_judgments, candidate)
    spent = original._spent(engine, plan["study_key"])
    all_judgments = {**judged, **validation_judgments}
    counts = Counter(v.get("label") for v in all_judgments.values() if v["status"] == "completed")
    statuses = Counter(v["status"] for v in all_judgments.values())
    example_rows = {row["pair_id"]: row for row in dev_rows + validation_rows}
    examples = list(parent["examples"])
    for pair_id, value in list(validation_judgments.items())[:3]:
        if value["status"] != "completed":
            continue
        assessment = engine.ledger.get(value["assessment"], "event_pair_judgement")
        examples.append({"pair_id": pair_id, **value, "rationale": assessment["result"]["rationale"],
            "articles": [{**metadata[event["source_version"]], "event": event,
                "claims": [claim for claim in assessment["result"]["claims"]
                           if claim["source_version"] == event["source_version"]]}
                for event in assessment["result"]["events"]]})
    for example in examples:
        row = example_rows.get(example["pair_id"], {})
        example["feature_values"] = row.get("features")
        example["publication_gap_days"] = row.get("publication_gap_days")
        example["candidate_decision"] = ("auto_link" if predicts(row, candidate) else "review") if candidate else None
    result = {"versions": child_versions, "original_judge_versions": parent["versions"], "manifest": manifest,
        "parent": data["parent_result"], "plan": parent["plan"], "study_key": plan["study_key"],
        "original_authorization": auth_id, "development_features": dev_artifact, "development_metrics": metrics_artifact,
        "development_pairs": len(dev_rows), "variant_summaries": _descriptive(metrics), "candidate": candidate,
        "frozen_candidate": frozen_id, "validation": validation, "validation_pairs": len(validation_rows),
        "validation_judgements": validation_judgments, "development_judgements": judged,
        "development_counts": metrics["all_label_counts"],
        "development_feature_errors": metrics["feature_errors"], "holdout_obstacle": holdout_obstacle,
        "validation_frame_feature_pairs": len(heldout_features),
        "failed_validation_feature_pairs": sum(row["status"] != "completed" for row in heldout_features),
        "counts": {label: counts[label] for label in ("same_event", "different_event", "uncertain")},
        "failed_pairs": statuses["failed"], "pending_pairs": statuses["pending"],
        "unknown_pairs": sum(v.get("outcome") == "unknown" for v in all_judgments.values()),
        "pair_attempts": len(spent), "new_pair_attempts": len(spent) - old_attempts,
        "article_exposures": len(spent) * 2, "retry_attempts": sum(v["event_pair_retry"] for v in spent),
        "remaining_pair_attempts": 100 - len(spent), "status": "partial" if stop or statuses["failed"] or statuses["pending"] or metrics["feature_errors"] or holdout_obstacle
            else validation["status"] if validation else "candidate_unvalidated" if candidate else "inconclusive_development",
        "original_global_screen_status": parent["status"], "original_global_screen_changed": False,
        "dataset_articles": plan["selected_articles"], "vector_articles": plan["processed_articles"],
        "missing_vector_articles": plan["missing_articles"], "validation_frame_pairs": sum(r["fold"] == "validation" for r in frame["rows"]),
        "new_embedding_requests": 0, "accepted_dossiers": 0, "applied_tags": 0, "human_validated": False,
        "provider_billing": None, "provider_internal_request_count": None,
        "primary_attempts": sum(not v["event_pair_retry"] for v in spent),
        "unresolved_attempts": [identifier for identifier, v in engine.ledger.unresolved.items()
                                if v.get("event_pair_study") == plan["study_key"]],
        "examples": examples, "limitations": selection.LIMITATIONS + sampling.LIMITATIONS,
        "started_at": started, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_pair_feature_experiment", key, result)
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, child_versions), {
        "results": [{"kind": "event_pair_feature_experiment", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    def percent(value: Any) -> str:
        return "unavailable" if value is None else f"{value:.1%}"
    lines = [f"Passage-feature event-link experiment: **{result['status']}**.", "",
        f"Reused all {result['development_pairs']} development references: same event {result['development_counts']['same_event']}, "
        f"different event {result['development_counts']['different_event']}, uncertain {result['development_counts']['uncertain']}. "
        "Compared five embedding features × four publication gates; retained original sampling weights and all uncertain references.",
        f"Dataset: {result['dataset_articles']} articles; {result['vector_articles']} with vectors, {result['missing_vector_articles']} missing. "
        f"Held-out frame: {result['validation_frame_pairs']} candidate pairs; judged {result['validation_pairs']}.", "",
        "Descriptive best per variant with at least eight same-event references (development only; failures remain failures):", "",
        "| Feature | Publication gate | Cosine cutoff | Weighted precision | Known-same coverage | Auto-link / review | Eligible |",
        "|---|---:|---:|---:|---:|---:|---|"]
    for variant in result["variant_summaries"]:
        best = variant["descriptive_best_with_eight_same"]
        gate = variant["publication_gap_days"]
        if best:
            m = best["metrics"]
            lines.append(f"| {variant['feature']} | {gate if gate is not None else 'none'} | {best['threshold']:.9g} | "
                f"{percent(m['precision_pessimistic_weighted'])} | {percent(m['known_same_coverage_weighted'])} | "
                f"{m['auto_link_pairs']} / {m['review_pairs']} | {'yes' if m['eligible'] else 'no'} |")
        else:
            lines.append(f"| {variant['feature']} | {gate if gate is not None else 'none'} | unavailable | — | — | — | no: support |")
    candidate = result["candidate"]
    if candidate:
        m = candidate["metrics"]
        lines += ["", f"Frozen candidate: **{candidate['feature']} ≥ {candidate['threshold']:.17g}**, publication gap "
            f"{candidate['publication_gap_days'] if candidate['publication_gap_days'] is not None else 'unrestricted'} days. "
            f"Development precision observed/weighted: {percent(m['precision_pessimistic_observed'])}/{percent(m['precision_pessimistic_weighted'])}; "
            f"known-same coverage observed/weighted: {percent(m['known_same_coverage_observed'])}/{percent(m['known_same_coverage_weighted'])}. "
            f"Automatic-link candidates {m['auto_link_pairs']}; review {m['review_pairs']}."]
    else:
        lines += ["", "**No candidate met the registered screen. No good cutoff established; holdout remains unopened.**"]
    if result["validation"]:
        v, m = result["validation"], result["validation"]["metrics"]
        lines += [f"Held-out result: **{v['status']}**. Precision observed/weighted: "
            f"{percent(m['precision_pessimistic_observed'])}/{percent(m['precision_pessimistic_weighted'])}. "
            f"Auto-link {m['auto_link_pairs']}; review {m['review_pairs']}; selected labels {m['selected_label_counts']}. "
            f"Screen failures: {', '.join(m['eligibility_reasons']) or 'none'}. No recall pass claimed."]
    lines += ["", f"New pair attempts {result['new_pair_attempts']}; cumulative {result['pair_attempts']}/100, "
        f"article exposures {result['article_exposures']}/200; retries {result['retry_attempts']}/10. "
        f"Failed {result['failed_pairs']}, unknown {result['unknown_pairs']}, pending {result['pending_pairs']}. "
        "No new embeddings, tags or accepted dossiers. Billing and internal request counts unavailable.",
        f"Development feature errors {len(result['development_feature_errors'])}; held-out feature pairs computed "
        f"{result['validation_frame_feature_pairs']}, failed {result['failed_validation_feature_pairs']}; "
        f"holdout obstacle: {result['holdout_obstacle'] or 'none'}.",
        "The original global binary-cutoff study remains inconclusive. This is an exploratory automatic-link/REVIEW screen. "
        "Model references are not human gold; publication dates are not event dates; pair links do not validate complete clusters."]
    from .rag_answers import _cell, _excerpt, _link
    lines += ["", "Stored model-reference examples and evidence (no new chat-level article judging):"]
    for example in result["examples"]:
        lines.append(f"- Pair `{example['pair_id']}`: {example['label']}; {_cell(example['rationale'])}")
        lines.append(f"  Feature cosines: {example.get('feature_values')}; publication gap {example.get('publication_gap_days')}; "
                     f"candidate decision {example.get('candidate_decision')}.")
        for article in example["articles"]:
            lines.append(f"  {_link(article.get('title') or article['source_version'], article.get('url'))}.")
            if article["claims"]:
                claim = article["claims"][0]
                lines.append(f"  Evidence: {_excerpt(claim['quote'])} (passage `{claim['passage_id']}`).")
    return "\n".join(lines)
