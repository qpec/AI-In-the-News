"""Audited offline final existence screen; any winner still needs sealed validation."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import event_pair_conjunction_study as previous
from . import event_pair_experiment as original
from . import event_pair_feature_study as base
from . import event_pair_monotone as rules
from .common import AuditError, Context, Json, ResearchError, require_active, utc
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "event-pair-final-monotone-amendment-v3"
CODE = ("event_pair_monotone_study.py", "event_pair_monotone.py", *previous.CODE)


def select_hypothesis(metrics: Json) -> tuple[Json | None, str | None]:
    if metrics["best_candidate"] is not None:
        return metrics["best_candidate"], "qualified_development"
    diagnostic = metrics["best_at_required_coverage"]
    if metrics["search_complete"] and metrics["status"] == "no_eligible_rule" and diagnostic:
        values = diagnostic["metrics"]
        if all(values[key] is not None and values[key] >= .85 for key in (
                "precision_pessimistic_observed", "precision_pessimistic_weighted")):
            return diagnostic, "exploratory_below_development_target"
    return None, None


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) - {"parent_conjunction_result", "experiment_key", "continuation_instruction", "reuse_cache", "execute_validation", "workers"}
            or data.get("reuse_cache") is not True or data.get("execute_validation", False) is not False
            or any(not isinstance(data.get(key), str) or not data[key].strip()
                   for key in ("parent_conjunction_result", "experiment_key", "continuation_instruction"))):
        raise ResearchError("Final screen is offline only; declare failed parent, immutable key, exact reuse and continuation instruction")
    started = utc()
    failed = engine.ledger.get(data["parent_conjunction_result"], "event_pair_conjunction_experiment")
    if failed["status"] != "inconclusive_development" or failed["candidate"] is not None or failed["validation_pairs"]:
        raise ResearchError("Final screen requires a failed two-feature result with no candidate or opened validation")
    first = engine.ledger.get(failed["parent_feature_result"], "event_pair_feature_experiment")
    parent = engine.ledger.get(first["parent"], "event_pair_experiment")
    plan, frame, development = load_plan(engine, session, parent["plan"])
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("Final screen context differs from frozen plan")
    auth_id, _ = base.parent_binding(engine, parent, parent["plan"], plan)
    old_manifest = engine.ledger.get(failed["manifest"], "event_pair_conjunction_manifest")
    if (old_manifest["method"]["implementation"] != base._hashes(previous.CODE)
            or old_manifest["method"]["failed_parent"] != failed["parent_feature_result"]
            or old_manifest["method"]["failed_method"]["implementation"] != base._hashes(base.CODE)
            or failed["original_parent"] != first["parent"] or failed["study_key"] != plan["study_key"]
            or first["candidate"] is not None or first["status"] != "inconclusive_development"):
        raise ResearchError("Earlier failed method hashes or authorization lineage changed")
    for kind in ("event_pair_candidate", "event_pair_feature_candidate", "event_pair_conjunction_candidate"):
        if original._records(engine, kind, plan["study_key"]):
            raise ResearchError("An earlier candidate was frozen; further development selection is forbidden")
    if original._records(engine, "event_pair_holdout_opened", plan["study_key"]):
        raise ResearchError("Shared holdout already opened; final development search is forbidden")
    method = {"method": METHOD, "parent": data["parent_conjunction_result"], "parent_manifest": failed["manifest"],
        "prior_method": old_manifest["method"], "original_authorization": auth_id, "study_binding": plan["study_binding"],
        "implementation": base._hashes(CODE), "search": rules.POLICY,
        "amendment": "Keep earlier immutable branch restrictions; permit one final offline existence search only after both completed failures and before any candidate or holdout opening",
        "original_judge_versions": parent["versions"], "continuation_instruction": data["continuation_instruction"],
        "observed_chat_timestamp": None, "experiment_key": data["experiment_key"],
        "mode": "exploratory", "population_estimate": False,
        "rules": "Preserve all original references/weights/uncertainty and quality requirements; finite final five-dimensional family; no new model budget",
        "validation": "Freeze one eligible rule, or one best-at-required-coverage diagnostic only if both precision measures reach 0.85; a sub-0.90 development result remains failed. One unchanged 0.90 held-out screen only, under original budget; never retune after opening",
        "exploratory_probe_floor": .85, "development_quality_target_unchanged": .90,
        "external_calls": 0}
    manifests = original._records(engine, "event_pair_monotone_manifest", plan["study_key"])
    if manifests and (len(manifests) != 1 or manifests[0][1]["method"] != method):
        raise ResearchError("Final amendment is immutable; no changed method, fresh key or reset")
    versions = dict(plan["versions"])
    for kind in ("protocol", "selection", "profile"):
        versions[kind] = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
            "kind": kind, "key": data["experiment_key"], "content": {**method, "binding_role": kind},
            "amend_latest": True, "reason": "Register final finite monotone existence amendment after two retained failures"})["id"]
    manifest = engine.ledger.record(session, "event_pair_monotone_manifest", plan["study_key"], {"versions": versions, "method": method})
    judged = base.references(engine, session, parent, plan, development["rows"])
    rows = engine.ledger.artifacts.read(first["development_features"])
    expected = {row["pair_id"]: row for row in development["rows"]}
    if (len(rows) != len(expected) or {row["pair_id"] for row in rows} != set(expected)
            or any(any(row.get(key) != value for key, value in expected[row["pair_id"]].items()) for row in rows)):
        raise AuditError("Final feature reuse differs from original pairs, folds or sampling probabilities")
    saved = original._records(engine, "event_pair_monotone_development", plan["study_key"])
    frozen = original._records(engine, "event_pair_monotone_candidate", plan["study_key"])
    if saved:
        if len(saved) != 1 or saved[0][1]["manifest"] != manifest:
            raise ResearchError("Stored final search differs from manifest")
        metrics_ref = saved[0][1]["metrics_artifact"]
        metrics = engine.ledger.artifacts.read(metrics_ref)
        engine.ledger.append(session, "analysis.cache_reused", {"manifest": manifest, "artifact": metrics_ref,
            "basis": "exact_version_resume; no retuning of frozen rule"})
    else:
        if frozen:
            raise AuditError("Frozen final rule lacks durable development search")
        metrics = rules.evaluate(rows, judged)
        metrics_ref = base._save(engine, session, metrics, "Required exhaustive final grid, generating subsets, exact masks and failures")
        engine.ledger.record(session, "event_pair_monotone_development", plan["study_key"], {
            "versions": versions, "manifest": manifest, "metrics_artifact": metrics_ref,
            "features_artifact": first["development_features"]})
    candidate, candidate_basis = select_hypothesis(metrics)
    binding = {"manifest": manifest, "candidate": candidate, "development_metrics": metrics_ref,
               "candidate_basis": candidate_basis, "original_authorization": auth_id, "versions": versions}
    if len(frozen) > 1 or frozen and frozen[0][1]["binding"] != binding:
        raise ResearchError("Final frozen candidate cannot be retuned")
    frozen_id = frozen[0][0] if frozen else None
    if candidate is not None and not frozen:
        frozen_id = engine.ledger.record(session, "event_pair_monotone_candidate", plan["study_key"], {
            "versions": versions, "binding": binding, "frozen_at": utc()})
    spent = original._spent(engine, plan["study_key"])
    result = {"versions": versions, "original_judge_versions": parent["versions"], "manifest": manifest,
        "parent_conjunction_result": data["parent_conjunction_result"], "parent_feature_result": failed["parent_feature_result"],
        "original_parent": first["parent"], "plan": parent["plan"], "study_key": plan["study_key"],
        "original_authorization": auth_id, "development_metrics": metrics_ref,
        "candidate": candidate, "candidate_basis": candidate_basis, "frozen_candidate": frozen_id, "best_at_required_coverage": metrics["best_at_required_coverage"],
        "best_precision_overall": metrics["best_precision_overall"], "search_status": metrics["status"],
        "search_complete": metrics["search_complete"], "development_pairs": len(rows),
        "development_counts": metrics["all_label_counts"], "development_feature_errors": metrics["feature_errors"],
        "evaluated_generating_subsets": metrics["evaluated_generating_subsets"], "distinct_prediction_masks": metrics["distinct_prediction_masks"],
        "gate_summaries": metrics["gate_summaries"], "pair_attempts": len(spent), "article_exposures": 2 * len(spent),
        "primary_attempts": sum(not value["event_pair_retry"] for value in spent),
        "retry_attempts": sum(value["event_pair_retry"] for value in spent), "new_pair_attempts": 0,
        "unresolved_attempts": [key for key, value in engine.ledger.unresolved.items() if value.get("event_pair_study") == plan["study_key"]],
        "validation_pairs": 0, "holdout_opened": False, "status": ("probe_candidate_unvalidated" if candidate_basis == "exploratory_below_development_target"
            else "candidate_unvalidated") if candidate else metrics["status"],
        "dataset_articles": plan["selected_articles"], "vector_articles": plan["processed_articles"], "missing_vector_articles": plan["missing_articles"],
        "validation_frame_pairs": sum(row["fold"] == "validation" for row in frame["rows"]),
        "new_embedding_requests": 0, "accepted_dossiers": 0, "applied_tags": 0, "human_validated": False,
        "provider_billing": None, "examples": failed["examples"], "started_at": started, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_pair_monotone_result", data["experiment_key"], result)
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "event_pair_monotone_result", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    def pct(value: float | None) -> str:
        return "unavailable" if value is None else f"{value:.1%}"
    lines = [f"Final five-signal cutoff screen: **{result['status']}**.", "",
        f"Completed search: {result['search_complete']}; evaluated {result['evaluated_generating_subsets']} generating boxes "
        f"({result['distinct_prediction_masks']} distinct prediction sets), using all {result['development_pairs']} references: "
        f"{result['development_counts']['same_event']} same event, {result['development_counts']['different_event']} different event, "
        f"{result['development_counts']['uncertain']} uncertain. Original sampling weights and quality requirements were unchanged.", ""]
    if result["search_status"] == "no_eligible_rule" and result["search_complete"]:
        lines.append("**No monotone AND rule using these five saved features and four publication gates meets the registered development requirements on these references.**")
        if result["candidate"]:
            lines.append("One best available hypothesis with precision ≥85% and required coverage/support is frozen for one untouched held-out test. "
                         "It still failed the 90% development target and remains unvalidated; no good cutoff is established.")
    elif result["candidate"]:
        lines.append("**One eligible five-threshold candidate is frozen; it is unvalidated. No good cutoff is established yet.**")
    else:
        lines.append("**No cutoff established. Processing or positive support is insufficient for a feature-family conclusion.**")
    lines += ["", "Requirements: precision ≥90% and known-same coverage ≥50%, both observed and weighted; "
        "at least eight selected same-event references, twelve positive articles and four disjoint positive pairs.", "",
        "| Development diagnostic | Precision observed / weighted | Known-same coverage observed / weighted | Link / review |",
        "|---|---:|---:|---:|"]
    for label, item in (("Best precision with required coverage/support", result["best_at_required_coverage"]),
                        ("Best precision overall (coverage may fail)", result["best_precision_overall"])):
        if item:
            m = item["metrics"]
            lines.append(f"| {label} | {pct(m['precision_pessimistic_observed'])} / {pct(m['precision_pessimistic_weighted'])} | "
                f"{pct(m['known_same_coverage_observed'])} / {pct(m['known_same_coverage_weighted'])} | {m['auto_link_pairs']} / {m['review_pairs']} |")
    chosen = result["candidate"] or result["best_at_required_coverage"]
    if chosen:
        lines += ["", "Frozen candidate thresholds:" if result["candidate"] else "Best diagnostic thresholds, unvalidated and not applied:", ""]
        for feature, threshold in zip(chosen["features"], chosen["thresholds"], strict=True):
            lines.append(f"- {feature} ≥ {threshold:.17g}")
        m = chosen["metrics"]
        lines += ["", f"Publication gap: {chosen['publication_gap_days'] if chosen['publication_gap_days'] is not None else 'unrestricted'} days. "
            f"Selected model labels: {m['selected_label_counts']}. Screen failures: {', '.join(m['eligibility_reasons']) or 'none'}."]
    lines += ["", f"Scope: {result['dataset_articles']} articles; {result['vector_articles']} with vectors, {result['missing_vector_articles']} missing. "
        f"Held-out frame {result['validation_frame_pairs']} pairs; labels opened 0. Development feature errors {len(result['development_feature_errors'])}.",
        f"Reference processing: failed {result['development_counts']['failed']}, pending {result['development_counts']['pending']}, "
        f"unknown {result['development_counts']['unknown']}; uncertain remains a separate label.",
        f"New model pair attempts 0; cumulative {result['pair_attempts']}/100, article exposures {result['article_exposures']}/200, "
        f"including {result['retry_attempts']}/10 retries; unresolved attempts {len(result['unresolved_attempts'])}. "
        "No new embeddings, tags or accepted dossiers. Billing unavailable.",
        "This is a final development-family result, not a statement about all embeddings or independently reviewed event labels. "
        "Model references are not human gold; no population accuracy, held-out pass or valid clusters are established. "
        "Earlier failures remain preserved. Other pairs require review, not a different-event verdict.", "",
        "Previously recorded development examples:", ""]
    from .rag_answers import _link, _excerpt
    for example in result["examples"][:2]:
        lines.append(f"- {example['label']}: {example['rationale']}")
        for article in example["articles"]:
            lines.append(f"  {_link(article.get('title') or article['source_version'], article.get('url'))}.")
            if article["claims"]:
                claim = article["claims"][0]
                lines.append(f"  Evidence: {_excerpt(claim['quote'])} (passage `{claim['passage_id']}`).")
    return "\n".join(lines)
