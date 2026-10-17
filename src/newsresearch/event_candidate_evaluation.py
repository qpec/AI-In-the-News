"""Offline preparation of an independent fixed-allocation candidate pair draw."""
from __future__ import annotations

from collections import Counter
import hashlib
from pathlib import Path
from typing import Any

from .common import Context, Json, ResearchError, digest, require_active
from .event_eval_math import build_pair_design, pair_id
from .event_eval_provider import build_prompt
from .event_eval_workflow import METHOD as EXECUTION_METHOD, EventEvaluationResearch, implementation, present, save
from .event_pair_reference import build_request
from .luna_validation_study import _lead
from .runtime import audited_handler

METHOD = "coverage-guarded-candidate-pair-preparation-v2"
CANDIDATE_METHOD = "coverage-guarded-event-split-v2"
DELTA_GRID = (.025, .05, .075, .1, .15, .2, .25)
SEED = "coverage-guarded-candidate-pair-evaluation-20261017-v2"
SIZES = {"within_group": 56, "between:random_tail": 8}
STUDY = "coverage-guarded-candidate-pair-evaluation-20261017-v2"


def _coverage(candidate: Json) -> Json:
    delta = candidate.get("delta")
    if type(delta) not in {int, float} or delta not in DELTA_GRID:
        raise ResearchError("candidate_eval_positive_fixed_grid_delta_required")
    baseline, current = candidate["baseline"], candidate["candidate"]
    if any(type(row.get(key)) is not int or row[key] <= 0 for row in (baseline, current)
           for key in ("within_pairs", "grouped_articles")):
        raise ResearchError("candidate_eval_grouping_counts_invalid")
    pairs = current["within_pairs"] / baseline["within_pairs"]
    articles = current["grouped_articles"] / baseline["grouped_articles"]
    if not .60 <= pairs <= 1 or not .70 <= articles <= 1:
        raise ResearchError("candidate_eval_grouping_coverage_guards_failed")
    if abs(candidate["retained_pairs_fraction"] - pairs) > 1e-12:
        raise ResearchError("candidate_eval_pair_retention_inconsistent")
    return {"minimum_pair_retention": .60, "minimum_grouped_article_retention": .70,
        "pair_retention": pairs, "grouped_article_retention": articles,
        "delta_grid": [0, *DELTA_GRID], "delta_selection": "Largest positive fixed-grid delta passing both guards, chosen without labels"}


def frozen_draw(membership: Json, previous_tasks: list[Json]) -> Json:
    """One prospectively fixed draw; overlap is reported, never rejected/replaced."""
    groups: dict[str, list[str]] = {}
    for source, group in membership.items():
        if not isinstance(source, str) or not source or not isinstance(group, str) or not group:
            raise ResearchError("candidate_eval_membership_invalid")
        groups.setdefault(group, []).append(source)
    design = build_pair_design(groups, {}, sample_sizes=SIZES, seed=SEED)
    if len(design["selected_pairs"]) != 64:
        raise ResearchError("candidate_eval_requires_56_within_and_8_tail_pairs")
    old_pairs = {task["pair_id"] for task in previous_tasks}
    evaluation_ids = {row["pair_id"] for row in design["selected_pairs"]}
    canaries = []
    for group in sorted(groups):
        members = sorted(groups[group])
        if len(members) < 2:
            continue
        left, right = members[:2]
        identifier = pair_id(left, right)
        if identifier not in evaluation_ids:
            canaries.append({"pair_id": identifier, "left": left, "right": right,
                "stratum": "development_canary", "pi": None})
        if len(canaries) == 4:
            break
    if len(canaries) != 4:
        raise ResearchError("candidate_eval_four_separate_canaries_unavailable")
    return {"design": design, "canaries": canaries,
        "overlap": {"previous_task_pairs": len(old_pairs),
            "evaluation_pair_ids": sorted(evaluation_ids & old_pairs),
            "canary_pair_ids": sorted({row["pair_id"] for row in canaries} & old_pairs),
            "excluded_pairs": 0, "replacements": 0, "reseeded": False,
            "strict_unseen_pair_holdout": not bool(evaluation_ids & old_pairs),
            "meaning": "Independent full-frame SRS; chance overlap is retained, disclosed, and never replaced. No old labels enter metrics."}}


def prepare(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) != {"phase", "candidate_result", "original_plan"}:
        raise ResearchError("candidate_eval_preparation_fields_invalid")
    own_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    content = {"method": METHOD, "candidate_result": data["candidate_result"], "original_plan": data["original_plan"],
        "seed": SEED, "sample_sizes": SIZES, "canaries": 4, "implementation_sha256": own_hash,
        "sampling": "One full-support fixed-seed pair SRS draw; within candidate groups and entire between-group complement",
        "overlap": "Read previous pair IDs only after registration; retain and disclose overlap without reseeding, replacement, or label reuse",
        "estimand": "Unordered-pair precision/recall over all candidate-frame articles; no pair exclusions",
        "evaluation": "Largest positive prospectively fixed-grid delta preserving >=60% of pairs and >=70% of grouped articles; no old model labels read or used as new references",
        "candidate_method": CANDIDATE_METHOD, "delta_grid": [0, *DELTA_GRID],
        "precision_target": {"target": .90,
            "decision": "Point target passes only with complete decisive within-group references and pair precision >= .90",
            "missingness": "Unresolved references stay null; show pessimistic and optimistic same-event counts and fractions",
            "confidence": "Report the 95% conditional sampling interval separately; point target does not require or imply a 95% lower bound of .90",
            "human_accuracy_established": False},
        "limitations": "Model-reference intervals condition on correct fixed labels; random-tail recall may remain uninformative; no human gold or whole-group claim",
        "model_calls": 0, "approval_created": False, "original_memberships_changed": False}
    protocol = engine._version(session, context, {"kind": "protocol", "key": STUDY,
        "content": content, "amend_latest": True,
        "reason": "Freeze independent seed, allocation, overlap policy and candidate result before reading pair IDs or membership"})["id"]
    candidate = engine.ledger.get(data["candidate_result"], "event_group_refinement_result")
    old = engine.ledger.get(data["original_plan"], "luna_group_validation_plan")
    if (candidate.get("method") != CANDIDATE_METHOD
            or candidate.get("original_evaluation_plan") != data["original_plan"]
            or candidate.get("baseline_group_result") != old.get("group_result")
            or candidate.get("unchanged_original_memberships") is not True
            or old.get("method") != EXECUTION_METHOD
            or (context.versions and context.versions != old["versions"])):
        raise ResearchError("candidate_eval_candidate_or_baseline_binding_invalid")
    coverage = _coverage(candidate)
    membership = engine.ledger.artifacts.read(candidate["candidate_membership"])
    original_sources = {source for members in old["design"]["groups"].values() for source in members}
    if not isinstance(membership, dict) or set(membership) != original_sources:
        raise ResearchError("candidate_eval_complete_original_article_frame_required")
    engine.ledger.append(session, "event.candidate.eval.frame.inspected", {
        "candidate_result": data["candidate_result"], "membership_artifact": candidate["candidate_membership"],
        "original_plan": data["original_plan"], "fields": ["design.groups", "tasks.pair_id"],
        "model_assessments_or_labels_read": False})
    draw = frozen_draw(membership, old["tasks"])
    binding = digest({"candidate_result": data["candidate_result"], "original_plan": data["original_plan"],
        "protocol": protocol, "implementation": implementation(), "preparation_sha256": own_hash})
    rows = engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='luna_group_validation_plan' AND logical_key=?", (STUDY,)).fetchall()
    if rows:
        prior = engine.ledger.get(rows[-1]["id"], "luna_group_validation_plan")
        if prior.get("study_binding") != binding:
            raise ResearchError("candidate_eval_existing_plan_cannot_rebind_or_reseed")
        return {"id": rows[-1]["id"], **prior, "presentation": engine._record_presentation(session,
            Context(context.objective, context.actor, prior["versions"]), {
                "results": [{"kind": "luna_group_validation_plan", "id": rows[-1]["id"]}],
                "markdown": render(prior), "destination": "codex_chat", "status": "prepared_for_delivery"}), "reused": True}
    versions = {**old["versions"], "protocol": protocol}
    for kind, value in {
        "question": {"text": "Does the prospectively fixed margin .25 split candidate reach 90% unordered-pair model-reference precision, with explicit unresolved references and recall uncertainty?"},
        "selection": {"rules": {"candidate_result": data["candidate_result"], "frame": candidate["candidate_membership"],
            "seed": SEED, "sample_sizes": SIZES, "pair_exclusions": [], "overlap": draw["overlap"]}},
        "profile": {"mode": "systematic", "population_estimate": False,
            "purpose": "Conditional candidate-frame model-reference pair diagnostics; no accepted population finding"},
    }.items():
        versions[kind] = engine._version(session, Context(context.objective, context.actor, versions), {
            "kind": kind, "key": STUDY, "content": value})["id"]
    leads: dict[str, Json | None] = {}
    tasks = []
    quarantine = set(old.get("quarantined_source_versions", []))
    for pair in [*draw["canaries"], *draw["design"]["selected_pairs"]]:
        task = {**pair, "phase": "canary" if pair["stratum"] == "development_canary" else "evaluation",
            "status": "prepared", "request": None}
        if {pair["left"], pair["right"]} & quarantine:
            task["status"] = "quarantined_unknown_source"
        else:
            for source in (pair["left"], pair["right"]):
                if source not in leads:
                    leads[source] = _lead(engine, session, source, {})
            left, right = leads[pair["left"]], leads[pair["right"]]
            if left is None or right is None:
                task["status"] = "source_unavailable"
            else:
                request = build_request(left=left, right=right, versions=versions)
                task["wire_bytes"] = len(build_prompt(request).encode("utf-8"))
                if task["wire_bytes"] > 32768:
                    task["status"] = "oversize"
                task["request"] = save(engine, session, request, "New candidate pair request; no old answer reuse or model approval")
        tasks.append(task)
    plan = {"method": EXECUTION_METHOD, "preparation_method": METHOD, "versions": versions,
        "study_key": STUDY, "study_binding": binding, "original_plan": data["original_plan"],
        "candidate_result": data["candidate_result"], "group_result": data["candidate_result"],
        "baseline_group_result": candidate["baseline_group_result"], "candidate_delta": candidate["delta"],
        "candidate_method": CANDIDATE_METHOD, "coverage_guards": coverage,
        "candidate_rule": candidate["rule"], "original_rule": candidate["original_rule"],
        "baseline_counts": candidate["baseline"], "candidate_counts": candidate["candidate"],
        "retained_pairs_fraction": candidate["retained_pairs_fraction"],
        "grouped_article_fraction": candidate["grouped_article_fraction"],
        "candidate_membership": candidate["candidate_membership"], "implementation": implementation(),
        "preparation_implementation_sha256": own_hash, "config": old["config"], "design": draw["design"],
        "tasks": tasks, "overlap": draw["overlap"], "quarantined_source_versions": sorted(quarantine),
        "limits": {"max_requests": 68, "max_article_exposures": 136, "max_retries": 0},
        "source_count": len(membership), "pair_estimand_not_whole_group_purity": True,
        "model_authorized": False, "new_model_calls": 0, "original_groups_unchanged": True,
        "review_required": True, "examples": []}
    return present(engine, session, Context(context.objective, context.actor, versions),
        "luna_group_validation_plan", plan, render(plan))


def render(plan: Json) -> str:
    strata = {row["stratum"]: {key: row[key] for key in ("N", "n", "pi")} for row in plan["design"]["strata"]}
    overlap = plan["overlap"]
    cutoffs = "| Feature | Original cutoff | Candidate cutoff |\n| --- | ---: | ---: |\n"
    cutoffs += "\n".join(f"| {feature} | {old!r} | {new!r} |" for feature, old, new in zip(
        plan["original_rule"]["features"], plan["original_rule"]["thresholds"],
        plan["candidate_rule"]["thresholds"], strict=True))
    return ("Coverage-guarded candidate evaluation prepared offline: zero new model calls, no approval and no membership changes.\n\n"
        f"Candidate delta {plan['candidate_delta']}; {plan['source_count']:,} articles. "
        f"Each cutoff uses t + {plan['candidate_delta']} × (1 − t); the seven-day publication gate stays fixed.\n\n"
        f"{cutoffs}\n\n"
        f"Baseline grouping counts: {plan['baseline_counts']}. Candidate grouping counts: {plan['candidate_counts']}. "
        f"Original within-group pairs retained: {100 * plan['retained_pairs_fraction']:.1f}%; "
        f"original grouped articles retained: {100 * plan['coverage_guards']['grouped_article_retention']:.1f}%; "
        f"articles remaining in multi-article groups: {100 * plan['grouped_article_fraction']:.1f}%.\n\n"
        "The candidate uses the largest positive fixed-grid delta retaining at least 60% of original pairs and 70% of original grouped articles, selected without labels.\n\n"
        f"Frozen strata {strata}. Packet coverage {dict(Counter(task['status'] for task in plan['tasks']))}.\n\n"
        "Four separate sequential canaries precede 56 within-group and eight random-tail evaluation pairs. "
        "The proposed maximum is 68 Luna calls / 136 article exposures / zero retries, with first-failure stop and up to four workers.\n\n"
        f"Old 68-pair overlap: {len(overlap['evaluation_pair_ids'])} evaluation pairs {overlap['evaluation_pair_ids']}; "
        f"{len(overlap['canary_pair_ids'])} canaries {overlap['canary_pair_ids']}. "
        "No pairs were excluded, replaced or reseeded. Any overlap remains in the full-frame estimand and would require a new attempt; old labels are not new references. "
        "This is an independently randomized draw, not a guaranteed unseen-pair holdout.\n\n"
        "Every between-group pair has positive inclusion probability. Rare missed matches can leave recall very uncertain. "
        "The .90 precision point target requires complete decisive within-group references; unresolved cases stay null, with pessimistic and optimistic counts shown. "
        "The 95% sampling interval is reported separately and does not establish human accuracy. "
        "The candidate is unjudged: no 90% precision result, human validation or whole-group purity follows from preparation.")


class CandidateEvaluationResearch(EventEvaluationResearch):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data.get("phase") == "prepare_candidate_pairs":
            return prepare(self, session, context, data)
        return super()._luna_group_validation(session, context, data)
