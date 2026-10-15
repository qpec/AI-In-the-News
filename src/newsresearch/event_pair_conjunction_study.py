"""Explicit bounded amendment after the failed single-feature event-link branch."""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from . import event_pair_conjunction as rules
from . import event_pair_experiment as original
from . import event_pair_feature_study as base
from . import event_pair_sampling as sampling
from . import event_pair_selection as selection
from .aws_clustering_evaluation import vectors
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "event-pair-conjunction-amendment-v2"
CODE = ("event_pair_conjunction_study.py", "event_pair_conjunction.py", *base.CODE)


def sample_validation(rows: list[Json], frame_hash: str, candidate: Json, seed: str) -> Json:
    if any(row["fold"] != "validation" for row in rows):
        raise ResearchError("Conjunction holdout requires validation-only rows")
    strata: list[list[Json]] = [[], []]
    for row in rows:
        strata[0 if rules.predicts(row, candidate) else 1].append(row)
    parameters = {key: candidate[key] for key in ("features", "thresholds", "publication_gap_days")}
    return sampling._sample_strata({"frame_hash": frame_hash}, strata, [30, 6], ["auto_link", "review"],
        seed=seed, purpose=METHOD + ":single-heldout:" + digest(parameters))


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) - {"parent_feature_result", "experiment_key", "continuation_instruction", "reuse_cache", "execute_validation", "workers"}
            or data.get("reuse_cache") is not True or type(data.get("execute_validation", False)) is not bool
            or type(data.get("workers", 4)) is not int or not 1 <= data.get("workers", 4) <= 4
            or any(not isinstance(data.get(key), str) or not data[key].strip()
                   for key in ("parent_feature_result", "experiment_key", "continuation_instruction"))):
        raise ResearchError("Declare failed feature parent, immutable amendment key, exact reuse and continuation instruction")
    started = utc()
    failed = engine.ledger.get(data["parent_feature_result"], "event_pair_feature_experiment")
    if failed["status"] != "inconclusive_development" or failed["candidate"] is not None or failed["validation_pairs"]:
        raise ResearchError("Amendment requires a completed failed single-feature branch with no frozen candidate or validation")
    parent = engine.ledger.get(failed["parent"], "event_pair_experiment")
    plan, frame, development = load_plan(engine, session, parent["plan"])
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("Conjunction context differs from original plan")
    auth_id, auth = base.parent_binding(engine, parent, parent["plan"], plan)
    old_manifest = engine.ledger.get(failed["manifest"], "event_pair_feature_manifest")
    if (old_manifest["method"]["implementation"] != base._hashes(base.CODE)
            or old_manifest["method"]["parent"] != failed["parent"] or failed["study_key"] != plan["study_key"]):
        raise ResearchError("Failed branch implementation or original lineage changed")
    for kind in ("event_pair_candidate", "event_pair_feature_candidate"):
        if original._records(engine, kind, plan["study_key"]):
            raise ResearchError("An older candidate was frozen; no later variant selection is permitted")
    previous = original._records(engine, "event_pair_conjunction_manifest", plan["study_key"])
    opened = original._records(engine, "event_pair_holdout_opened", plan["study_key"])
    frozen = original._records(engine, "event_pair_conjunction_candidate", plan["study_key"])
    if not previous and (opened or frozen):
        raise ResearchError("Initial amendment requires no frozen candidates and a sealed shared holdout")
    method = {"method": METHOD, "failed_parent": data["parent_feature_result"], "failed_manifest": failed["manifest"],
        "failed_method": old_manifest["method"], "original_authorization": auth_id, "study_binding": plan["study_binding"],
        "original_judge_versions": parent["versions"], "implementation": base._hashes(CODE), "search": rules.POLICY,
        "amendment": "Retain v1 one-child restriction for v1; permit exactly one later offline conjunction branch after its documented failure, only before any candidate freeze or holdout opening",
        "unchanged": "Same focal-event criterion, all original references and n/N weights, eligibility requirements, original authorization and 100/200 cumulative budget",
        "overfitting": "Expanded development search increases overfitting; one frozen winner and one shared held-out check only",
        "continuation_instruction": data["continuation_instruction"], "observed_chat_timestamp": None,
        "experiment_key": data["experiment_key"], "mode": "exploratory", "population_estimate": False,
        "rules": "Finite forty conjunction/publication variants; no changed eligibility, new allowance, retuning after freeze or resealing"}
    if previous and (len(previous) != 1 or previous[0][1]["method"] != method):
        raise ResearchError("Conjunction amendment is immutable; no fresh key, changed code or reset")
    versions = dict(plan["versions"])
    for kind in ("protocol", "selection", "profile"):
        versions[kind] = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
            "kind": kind, "key": data["experiment_key"], "content": {**method, "binding_role": kind},
            "amend_latest": True, "reason": "Explicit append-only method amendment after failed single-feature comparison; holdout still sealed"})["id"]
    manifest = engine.ledger.record(session, "event_pair_conjunction_manifest", plan["study_key"], {"versions": versions, "method": method})
    if opened and (len(opened) != 1 or opened[0][1].get("child_manifest") != manifest):
        raise ResearchError("Shared holdout belongs to another branch; cannot retune")
    judged = base.references(engine, session, parent, plan, development["rows"])
    dev_rows = engine.ledger.artifacts.read(failed["development_features"])
    originals = {row["pair_id"]: row for row in development["rows"]}
    if (len(dev_rows) != len(originals) or {row["pair_id"] for row in dev_rows} != set(originals)
            or any(any(row.get(key) != value for key, value in originals[row["pair_id"]].items()) for row in dev_rows)):
        raise AuditError("Reused feature rows differ from original pair identities, folds or sampling probabilities")
    before = len(original._spent(engine, plan["study_key"]))
    saved_development = original._records(engine, "event_pair_conjunction_development", plan["study_key"])
    if saved_development:
        if len(saved_development) != 1 or saved_development[0][1]["manifest"] != manifest:
            raise ResearchError("Stored conjunction development differs from amendment")
        metrics_ref = saved_development[0][1]["metrics_artifact"]
        metrics = engine.ledger.artifacts.read(metrics_ref)
        engine.ledger.append(session, "analysis.cache_reused", {"manifest": manifest, "artifact": metrics_ref,
            "basis": "explicit_exact_method_version_bound_resume; no variant retuning"})
    else:
        if frozen or opened:
            raise AuditError("Frozen conjunction lacks durable development metrics")
        metrics = rules.evaluate(dev_rows, judged)
        metrics_ref = base._save(engine, session, metrics, "Required full conjunction parameter grid, exact masks and every failed variant")
        engine.ledger.record(session, "event_pair_conjunction_development", plan["study_key"], {
            "versions": versions, "manifest": manifest, "features_artifact": failed["development_features"], "metrics_artifact": metrics_ref})
    candidate = metrics["best_candidate"]
    candidate_binding = {"manifest": manifest, "candidate": candidate, "development_metrics": metrics_ref,
                         "original_authorization": auth_id, "versions": versions}
    frozen_id = None
    if len(frozen) > 1:
        raise AuditError("More than one frozen conjunction")
    if frozen:
        frozen_id, record = frozen[0]
        if record["binding"] != candidate_binding:
            raise ResearchError("Frozen conjunction cannot be retuned")
    elif candidate is not None:
        frozen_id = engine.ledger.record(session, "event_pair_conjunction_candidate", plan["study_key"], {
            "versions": versions, "binding": candidate_binding, "frozen_at": utc()})
    if opened and opened[0][1]["frozen_candidate"] != frozen_id:
        raise ResearchError("Shared opening differs from frozen conjunction")
    validation_rows: list[Json] = []
    validation_judgments: dict[str, Json] = {}
    validation = None
    obstacle = None
    validation_feature_count = 0
    failed_features = 0
    stopped = False
    if candidate is not None and data.get("execute_validation") is True:
        if engine.config.offline:
            raise ResearchError("Held-out Codex judging requires process-local online configuration")
        approval = original._approval({"run_approval": auth["approval"]}, parent["plan"], plan)
        current = original._config(engine, {key: auth["config"][key] for key in ("codex_model", "codex_executable")})
        if any(current[key] != value for key, value in auth["config"].items() if key != "configuration_origin"):
            raise ResearchError("Original Codex binary/configuration changed")
        sample = None
        if opened:
            sample = engine.ledger.artifacts.read(opened[0][1]["sample_artifact"])
        else:
            metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
            mapped = engine.ledger.artifacts.read(plan["mapping_artifact"])
            mapping = {item["source_version"]: [chunk["row"] for chunk in item["chunks"]] for item in mapped}
            with vectors(engine, session, engine.ledger.get(plan["index"], "vector_index")) as (passages, matrix):
                for item in mapped:
                    for chunk in item["chunks"]:
                        row = passages[chunk["row"]]
                        if (row["source_version"] != item["source_version"] or row["id"] != chunk["chunk"]
                                or row["passage_id"] != chunk["passage"]):
                            raise AuditError("Frozen passage mapping changed")
                heldout = base._compute(engine, session, matrix, mapping,
                    [row for row in frame["rows"] if row["fold"] == "validation"], metadata, "conjunction_validation_frame")
            validation_feature_count = len(heldout)
            failed_features = sum(row["status"] != "completed" or any(row["features"].get(feature) is None for feature in candidate["features"])
                                  for row in heldout)
            feature_ref = base._save(engine, session, heldout, "Required conjunction held-out frame features before labels")
            if failed_features:
                obstacle = "incomplete_validation_features; labels remain sealed"
            else:
                proposed = sample_validation(heldout, frame["frame_hash"], candidate, plan["seed"])
                if proposed["strata"][0]["n"] < selection.POLICY["validation"]["minimum_selected_pairs"]:
                    obstacle = "insufficient_available_validation_auto_links; labels remain sealed"
                else:
                    sample = proposed
                    sample_ref = base._save(engine, session, sample, "Required complete frozen conjunction sample before first held-out dispatch")
                    engine.ledger.record(session, "event_pair_holdout_opened", plan["study_key"], {
                        "binding": digest(auth), "versions": parent["versions"], "plan": parent["plan"],
                        "frozen_candidate": frozen_id, "child_manifest": manifest, "sample_artifact": sample_ref,
                        "frame_features_artifact": feature_ref, "opened_at": utc(), "branch": METHOD})
        if sample is not None:
            validation_rows = sample["rows"]
            validation_judgments, stopped = original._phase(engine, session, validation_rows, parent["plan"], plan,
                parent["versions"], approval, auth["config"], {"workers": data.get("workers", 4), "reuse_cache": True})
            validation = rules.validate(validation_rows, validation_judgments, candidate)
    spent = original._spent(engine, plan["study_key"])
    statuses = Counter(value["status"] for value in validation_judgments.values())
    result = {"versions": versions, "original_judge_versions": parent["versions"], "manifest": manifest,
        "parent_feature_result": data["parent_feature_result"], "original_parent": failed["parent"], "plan": parent["plan"],
        "study_key": plan["study_key"], "original_authorization": auth_id, "development_metrics": metrics_ref,
        "candidate": candidate, "frozen_candidate": frozen_id, "development_pairs": len(dev_rows),
        "development_counts": metrics["all_label_counts"], "variant_summaries": metrics["candidates"],
        "parameter_combinations": metrics["evaluated_parameter_combinations"], "distinct_prediction_masks": metrics["distinct_prediction_masks"],
        "development_feature_errors": metrics["feature_errors"], "validation": validation,
        "validation_pairs": len(validation_rows), "validation_judgements": validation_judgments,
        "validation_frame_feature_pairs": validation_feature_count, "failed_validation_feature_pairs": failed_features,
        "holdout_obstacle": obstacle, "pair_attempts": len(spent), "new_pair_attempts": len(spent) - before,
        "primary_attempts": sum(not value["event_pair_retry"] for value in spent),
        "retry_attempts": sum(value["event_pair_retry"] for value in spent), "article_exposures": 2 * len(spent),
        "failed_pairs": statuses["failed"], "pending_pairs": statuses["pending"],
        "unknown_pairs": sum(value.get("outcome") == "unknown" for value in validation_judgments.values()),
        "unresolved_attempts": [key for key, value in engine.ledger.unresolved.items() if value.get("event_pair_study") == plan["study_key"]],
        "status": "partial" if stopped or statuses["failed"] or statuses["pending"] or metrics["feature_errors"] or obstacle
            else validation["status"] if validation else "candidate_unvalidated" if candidate else "inconclusive_development",
        "dataset_articles": plan["selected_articles"], "vector_articles": plan["processed_articles"],
        "missing_vector_articles": plan["missing_articles"], "validation_frame_pairs": sum(row["fold"] == "validation" for row in frame["rows"]),
        "new_embedding_requests": 0, "accepted_dossiers": 0, "applied_tags": 0, "human_validated": False,
        "provider_billing": None, "provider_internal_request_count": None,
        "original_global_screen_changed": False, "examples": failed["examples"][:2],
        "started_at": started, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_pair_conjunction_experiment", data["experiment_key"], result)
    from .presentation import record as present
    presentation = present(engine, session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "event_pair_conjunction_experiment", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    def pct(value: float | None) -> str:
        return "unavailable" if value is None else f"{value:.1%}"
    lines = [f"Two-signal event-link experiment: **{result['status']}**.", "",
        f"Reused all {result['development_pairs']} model references: {result['development_counts']['same_event']} same event, "
        f"{result['development_counts']['different_event']} different event, {result['development_counts']['uncertain']} uncertain. "
        f"Tested 40 registered conjunction/publication-filter variants and {result['parameter_combinations']} threshold combinations. "
        "Quality requirements were unchanged; all tested settings and failed checks are retained.", ""]
    candidate = result["candidate"]
    if candidate:
        m = candidate["metrics"]
        lines += [f"Frozen rule: **{candidate['features'][0]} ≥ {candidate['thresholds'][0]:.17g} AND "
            f"{candidate['features'][1]} ≥ {candidate['thresholds'][1]:.17g}**, publication gap "
            f"{candidate['publication_gap_days'] if candidate['publication_gap_days'] is not None else 'unrestricted'} days. "
            "Other pairs require REVIEW.",
            f"Development precision observed/weighted: {pct(m['precision_pessimistic_observed'])}/{pct(m['precision_pessimistic_weighted'])}; "
            f"known-same coverage: {pct(m['known_same_coverage_observed'])}/{pct(m['known_same_coverage_weighted'])}. "
            f"Auto-link {m['auto_link_pairs']}, review {m['review_pairs']}; selected labels {m['selected_label_counts']}. "
            f"Positive article support {m['distinct_positive_articles']}; disjoint positive pairs {m['disjoint_positive_pair_lower_bound']}."]
    else:
        lines.append("**No two-threshold rule qualified. No good cutoff established; the holdout remains unopened.**")
    diagnostics = [item["diagnostic_best_candidate"] for item in result["variant_summaries"] if item["diagnostic_best_candidate"]]
    diagnostics.sort(key=lambda item: (item["metrics"]["precision_pessimistic_weighted"] or -1,
                                       item["metrics"]["known_same_coverage_weighted"] or -1), reverse=True)
    lines += ["", "Top three development diagnostics with at least eight same-event references (not validation):", "",
        "| Features | Cutoffs | Publication gap | Precision observed / weighted | Known-same coverage weighted | Eligible |",
        "|---|---|---:|---:|---:|---|"]
    for item in diagnostics[:3]:
        m = item["metrics"]
        lines.append(f"| {' + '.join(item['features'])} | {item['thresholds'][0]:.9g} / {item['thresholds'][1]:.9g} | "
            f"{item['publication_gap_days'] if item['publication_gap_days'] is not None else 'none'} | "
            f"{pct(m['precision_pessimistic_observed'])} / {pct(m['precision_pessimistic_weighted'])} | "
            f"{pct(m['known_same_coverage_weighted'])} | {'yes' if m['eligible'] else 'no'} |")
    if result["validation"]:
        v, m = result["validation"], result["validation"]["metrics"]
        lines += ["", f"Held-out result: **{v['status']}**, {result['validation_pairs']} pairs. Precision observed/weighted "
            f"{pct(m['precision_pessimistic_observed'])}/{pct(m['precision_pessimistic_weighted'])}; auto-link {m['auto_link_pairs']}, "
            f"review {m['review_pairs']}. Selected labels: {m['selected_label_counts']}. "
            f"Failures: {', '.join(m['eligibility_reasons']) or 'none'}. No recall pass claimed."]
    else:
        lines += ["", f"Held-out judgments: 0; obstacle: {result['holdout_obstacle'] or 'no eligible candidate or validation not requested'}."]
    lines += ["", f"Scope: {result['dataset_articles']} articles, {result['vector_articles']} with vectors, {result['missing_vector_articles']} missing; "
        f"{result['validation_frame_pairs']} held-out candidate pairs. Development feature errors {len(result['development_feature_errors'])}; "
        f"held-out feature pairs computed {result['validation_frame_feature_pairs']}, failed {result['failed_validation_feature_pairs']}.",
        f"New pair attempts {result['new_pair_attempts']}; cumulative {result['pair_attempts']}/100 and {result['article_exposures']}/200 article exposures, "
        f"including {result['retry_attempts']}/10 retries. Failed {result['failed_pairs']}, unknown {result['unknown_pairs']}, pending {result['pending_pairs']}; "
        f"unresolved {len(result['unresolved_attempts'])}.",
        "The original global-cutoff result and failed single-feature branch remain unchanged. This is exploratory model-reference screening, "
        "not human validation or established population accuracy. Publication dates are not event dates; pair links do not establish cluster identity. "
        "No new embeddings, tags or accepted dossiers. Billing/internal request counts unavailable.", "",
        "Previously stored model-reference examples (no new chat-level article judging):", ""]
    from .rag_answers import _excerpt, _link
    for example in result["examples"]:
        lines.append(f"- {example['label']}: {example['rationale']}")
        for article in example["articles"]:
            lines.append(f"  {_link(article.get('title') or article['source_version'], article.get('url'))}.")
            if article["claims"]:
                claim = article["claims"][0]
                lines.append(f"  Evidence: {_excerpt(claim['quote'])} (passage `{claim['passage_id']}`).")
    return "\n".join(lines)
