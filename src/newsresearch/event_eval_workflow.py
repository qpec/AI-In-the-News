"""A bounded replacement evaluator; original Luna attempts remain immutable.

All store access and model dispatch enter through Research.execute. Pair metrics
are model-reference diagnostics until independently reviewed; they are not
accepted event counts, whole-group purity, or proof of corpus recall.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import median
import time
from typing import Any
import uuid

from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .runtime import Research, audited_handler

METHOD = "fast-event-pair-evaluation-v1"
APPROVAL_METHOD = "fast-event-pair-evaluation-approval-v1"
OLD_RESULT = "da480ad8c3fa87ca41ddfe11530695f22246581419412193a2580d60dc4bc19a"
DEFAULT_STUDY = "fast-event-pair-evaluation-20261017-v1"
DEFAULT_SIZES = {"within_group": 32, "between:retrieved": 24, "between:random_tail": 8}
CANARIES = 4


def implementation() -> Json:
    names = ("event_eval_workflow.py", "event_eval_math.py", "event_eval_provider.py",
             "event_pair_reference.py", "event_eval_diagnostics.py", "event_eval_reviews.py", "codex_provider.py", "gateway.py",
             "luna_lead_answers.py", "luna_validation_study.py", "luna_group_validation.py")
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in names}


def save(engine: Any, session: str, value: Any, purpose: str) -> str:
    reference = str(engine.ledger.artifacts.put(value))
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": purpose})
    return reference


def present(engine: Any, session: str, context: Context, kind: str, value: Json, text: str) -> Json:
    identifier = engine.ledger.record(session, kind, digest(value), value)
    presentation = engine._record_presentation(session, context, {"results": [{"kind": kind, "id": identifier}],
        "markdown": text, "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **value, "presentation": presentation}


def _quarantined(engine: Any, old: Json) -> set[str]:
    """Unknown original sources stay unavailable across changed task keys."""
    plan = engine.ledger.get(old["plan"], "luna_group_validation_plan")
    tasks = {task["logical_id"]: task for task in plan["tasks"]}
    return {source for key, outcome in old["outcomes"].items() if outcome["status"] == "unknown"
            for source in tasks[key]["source_versions"]}


def _diagnose(engine: Any, session: str, context: Context, old: Json) -> Json:
    from .event_eval_diagnostics import technical_failure_details, replay_anchor_pairs
    from .luna_group_validation import candidate_pool_recall

    plan = engine.ledger.get(old["plan"], "luna_group_validation_plan")
    by_task = {task["logical_id"]: task for task in plan["tasks"]}
    errors: Counter[str] = Counter()
    sizes: dict[str, list[int]] = {"group": [], "anchor": []}
    details, projected, relations = [], [], []
    for key, outcome in old["outcomes"].items():
        task = by_task[key]
        if task.get("request_ref") is None:
            errors[task["mode"] + ":" + str(outcome.get("error") or "preparation_unavailable")] += 1
            continue
        request = engine.ledger.artifacts.read(task["request_ref"])
        response = engine.ledger.artifacts.read(outcome["response"]) if outcome.get("response") else {}
        engine.ledger.append(session, "event.eval.retained_response.inspected", {
            "request": task["request_ref"], "response": outcome.get("response"), "assessment": outcome.get("assessment"),
            "purpose": "Mechanical failure diagnosis and separately versioned pair projection; no new judging"})
        detail = technical_failure_details(request, response, outcome)
        details.append({"logical_id": key, "mode": task["mode"], **detail})
        errors[task["mode"] + ":" + str(outcome.get("error") or "valid")] += 1
        sizes[task["mode"]].append(len(request["articles"]))
        if task["mode"] == "anchor":
            replayed = replay_anchor_pairs(request, response, outcome, versions=context.versions)
            projected.extend(replayed["relations"])
    indexed = {(row["anchor"], row["candidate"]): row for row in projected}
    frames = plan["anchor_frames"]
    if isinstance(frames, dict):
        frames = list(frames.values())
    for frame in frames:
        for candidate in frame["candidates"]:
            row = indexed.get((frame["anchor"], candidate["candidate"]))
            relations.append({"anchor": frame["anchor"], "candidate": candidate["candidate"],
                "label": row["label"] if row is not None and row.get("label") is not None else
                    "failed" if frame["anchor"] in old["outcomes"] else "pending"})
    replay_ref = save(engine, session, projected, "Exact mechanical projections from retained original model responses; new pair prompts were not executed")
    detail_ref = save(engine, session, details, "Complete per-request technical validation diagnostics; no new semantic judgments")
    recall = candidate_pool_recall([frame["anchor"] for frame in frames], relations, plan["membership"],
        bootstrap_seed=METHOD)
    field_counts = {field: sum(row["unsupported_event_fields"][field] for row in details)
                    for field in ("description", "action", "actors", "event_date", "location")}
    latency = {mode: [row["latency_seconds"] for row in details if row["mode"] == mode and row["latency_seconds"] is not None]
               for mode in sizes}
    examples = []
    for row in sorted(projected, key=lambda item: item["label"] not in {"same_event", "different_event"}):
        if row.get("label") is None:
            continue
        articles = []
        for source in (row["anchor"], row["candidate"]):
            engine.ledger.append(session, "event.eval.example_metadata.inspected", {
                "sql": "SELECT payload FROM sources WHERE id=?", "parameters": [source], "purpose": "Source links for exact result presentation"})
            source_row = engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()
            if source_row:
                metadata = json.loads(source_row[0])
                articles.append({"source_version": source, "title": metadata.get("title"), "url": metadata.get("url")})
        examples.append({"label": row["label"], "articles": articles})
        if len(examples) == 2:
            break
    value = {"method": METHOD + ":retained-diagnostic", "versions": context.versions,
        "original_result": old["id"] if "id" in old else OLD_RESULT,
        "original_attempt_statuses_unchanged": True, "error_counts": dict(sorted(errors.items())),
        "request_article_counts": {mode: {"min": min(v) if v else None, "max": max(v) if v else None,
            "mean": sum(v) / len(v) if v else None} for mode, v in sizes.items()},
        "details_artifact": detail_ref, "pair_projection_artifact": replay_ref,
        "projected_labels": dict(Counter(row["label"] for row in relations)),
        "unsupported_field_counts": field_counts,
        "median_observed_request_seconds": {mode: median(values) if values else None for mode, values in latency.items()},
        "examples": examples,
        "candidate_pool_recall": recall, "new_model_calls": 0, "retries": 0,
        "human_validated": False, "new_pair_prompt_executed": False,
        "provenance": "Labels originate in the original batched context. Projection changes only mechanical acceptance; it does not rejudge or validate semantics.",
        "whole_group_result_unchanged": True}
    text = ("Retained Luna failure diagnosis and structural pair replay — zero new model calls.\n\n"
        f"Original statuses remain {old['task_counts']}; original spend {old['workflow_model_attempts']} calls / "
        f"{old['workflow_article_exposures']} article exposures. Failure codes: {value['error_counts']}.\n\n"
        f"Articles per original request: {value['request_article_counts']}. "
        f"Median observed request seconds {value['median_observed_request_seconds']}. "
        f"Uncited factual fields across returned outputs: {field_counts}.\n\n"
        f"All {len(relations):,} original candidate relations retained; projected labels {value['projected_labels']}. "
        f"Complete-case candidate-pool recall {recall['complete_case_candidate_pool_recall']}; "
        f"missingness bounds {recall['identified_bounds']}; known same-event inside/outside "
        f"{recall['same_event_inside']}/{recall['same_event_outside']}; unknown inside/outside "
        f"{recall['unknown_inside']}/{recall['unknown_outside']}.\n\n"
        "These are deterministic projections of original batched model outputs under a new registered citation contract. "
        "The new pair prompt was not executed. Original failed attempts remain failed; source/semantic correctness is unvalidated. "
        "This cannot establish whole-group purity or full-corpus recall. Unusable or unavailable pairs remain unknown.")
    for example in examples:
        article_links = "; ".join(f"[{a.get('title') or a['source_version']}]({a['url']})" if a.get("url") else a["source_version"] for a in example["articles"])
        text += f"\n\n- Replayed {example['label']}: {article_links}"
    return present(engine, session, context, "luna_group_validation_diagnostic", value, text)


def prepare(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_eval_math import build_pair_design, pair_id
    from .event_pair_reference import build_request
    from .event_eval_provider import build_prompt
    from .luna_validation_study import _lead

    allowed = {"phase", "original_result", "study_key", "seed", "sample_sizes"}
    if set(data) - allowed:
        raise ResearchError("event_eval_prepare_fields_invalid")
    key = data.get("study_key", DEFAULT_STUDY)
    seed = data.get("seed", METHOD)
    if any(not isinstance(x, str) or not x.strip() or len(x) > 160 for x in (key, seed)):
        raise ResearchError("event_eval_study_seed_invalid")
    original_id = data.get("original_result", OLD_RESULT)
    sizes = data.get("sample_sizes", DEFAULT_SIZES)
    code = implementation()
    binding = digest({"original": original_id, "study": key, "seed": seed, "sizes": sizes, "code": code})
    row = engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='luna_group_validation_plan' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (key,)).fetchone()
    if row:
        previous = json.loads(row["payload"])
        if previous.get("study_binding") != binding or previous.get("method") != METHOD:
            raise ResearchError("event_eval_existing_plan_binding_changed")
        return {"id": row["id"], **previous, "presentation": engine._record_presentation(session, Context(context.objective, context.actor, previous["versions"]),
            {"results": [{"kind": "luna_group_validation_plan", "id": row["id"]}], "markdown": render_plan(previous),
             "destination": "codex_chat", "status": "prepared_for_delivery"}), "reused": True}
    protocol = {"method": METHOD, "implementation": code, "original_result": original_id,
        "change": "Two bounded article leads per task; stable span IDs instead of exhaustive factual extraction",
        "sampling": {"method": "disjoint stratified SRSWOR unordered pairs", "sizes": sizes, "seed": seed,
            "full_support_random_tail": True, "candidate_channel": "Original frozen 100-anchor retrieval union, not all corpus nearest neighbors"},
        "canary": {"tasks": CANARIES, "separate_from_estimates": True, "order": "sequential before evaluation", "require_all_valid": True},
        "stop": "Latch first invalid or unknown result; finish already dispatched calls; no retries or replacement",
        "references": "Lead-only provisional model references; human review needed for accuracy claims",
        "no_membership_or_cutoff_changes": True, "new_models_authorized": False,
        "replay": "Original batched relation labels may be mechanically projected with exact valid bilateral source quotes; no new model prompt is claimed",
        "limitations": ["Pair precision is not entire-group purity", "Small rare-tail samples may leave corpus recall unidentified",
                        "No semantic entailment is proved by citation validation", "Retrospective frame; not independent event-disjoint human gold"]}
    registered = engine._version(session, context, {"kind": "protocol", "key": key, "content": protocol})["id"]
    old = engine.ledger.get(original_id, "luna_group_validation_result")
    old_plan = engine.ledger.get(old["plan"], "luna_group_validation_plan")
    if key == old_plan["study_key"] or old_plan["study_key"] != old["study_key"]:
        raise ResearchError("event_eval_requires_new_independent_study")
    owner_row = engine.ledger.db.execute("SELECT id FROM records WHERE kind='study_execution_ownership' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (old_plan["study_key"],)).fetchone()
    if owner_row:
        owner = engine.ledger.get(owner_row[0], "study_execution_ownership")
        if owner.get("status") != "imported_owner" or Path(owner.get("owner_workspace", "")).resolve() != engine.ledger.root.resolve():
            raise ResearchError("event_eval_use_original_study_owning_workspace")
    versions = {**old["versions"], "protocol": registered}
    contents = {"question": {"text": "Pair precision and missed same-event links of frozen seven-day event groups, with sampling and missingness uncertainty"},
        "selection": {"rules": protocol["sampling"]},
        "dossier_definition": {"unit": "One focal real-world event; pairs are evaluation units, not event counts"},
        "codebook": {"labels": ["same_event", "different_event", "uncertain"]},
        "prompt": {"instructions": __import__("newsresearch.event_pair_reference", fromlist=["TASK_INSTRUCTION"]).TASK_INSTRUCTION},
        "profile": {"mode": "systematic", "population_estimate": False, "human_validated": False,
            "purpose": "Conditional model-reference design diagnostics; no accepted population findings"}}
    for kind, content in contents.items():
        versions[kind] = engine._version(session, Context(context.objective, context.actor, versions), {"kind": kind, "key": key, "content": content})["id"]
    bound = Context(context.objective, context.actor, versions)
    diagnosis = _diagnose(engine, session, bound, {"id": original_id, **old})
    groups: dict[str, list[str]] = {}
    for source, group in old_plan["membership"].items():
        groups.setdefault(group, []).append(source)
    frames = old_plan["anchor_frames"]
    if isinstance(frames, dict):
        frames = list(frames.values())
    channels = {"retrieved": [[frame["anchor"], row["candidate"]] for frame in frames for row in frame["candidates"]]}
    design = build_pair_design(groups, channels, sample_sizes=sizes, seed=seed)
    if len(design["selected_pairs"]) > 64:
        raise ResearchError("event_eval_sample_exceeds_fixed_64_pair_bound")
    selected = {row["pair_id"] for row in design["selected_pairs"]}
    quarantine = _quarantined(engine, old)
    canaries = []
    for group in sorted(groups):
        members = sorted(groups[group])
        if len(members) < 2:
            continue
        a, b = members[:2]
        identifier = pair_id(a, b)
        if identifier not in selected and not ({a, b} & quarantine):
            canaries.append({"pair_id": identifier, "left": a, "right": b, "stratum": "development_canary", "pi": None})
            selected.add(identifier)
        if len(canaries) == CANARIES:
            break
    if len(canaries) != CANARIES:
        raise ResearchError("event_eval_separate_canary_frame_unavailable")
    leads, metadata = {}, {}
    tasks = []
    for row in [*canaries, *design["selected_pairs"]]:
        task = {**row, "phase": "canary" if row["stratum"] == "development_canary" else "evaluation",
            "status": "prepared", "request": None}
        if {row["left"], row["right"]} & quarantine:
            task["status"] = "quarantined_unknown_source"
        else:
            for source in (row["left"], row["right"]):
                if source not in leads:
                    leads[source] = _lead(engine, session, source, {})
                    metadata[source] = json.loads(engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()[0])
            if any(leads[source] is None for source in (row["left"], row["right"])):
                task["status"] = "source_unavailable"
            else:
                left, right = leads[row["left"]], leads[row["right"]]
                assert left is not None and right is not None
                request = build_request(left=left, right=right, versions=versions)
                task["wire_bytes"] = len(build_prompt(request).encode("utf-8"))
                if task["wire_bytes"] > 32768:
                    task["status"] = "oversize"
                task["request"] = save(engine, session, request, "Frozen blinded two-article pair request before any model approval")
        tasks.append(task)
    config = {**old_plan["config"], "timeout_seconds": 90, "max_input_bytes": 32768, "max_output_bytes": 16384}
    examples = [{"pair_id": task["pair_id"], "stratum": task["stratum"], "articles": [
        {"title": metadata[source].get("title"), "url": metadata[source].get("url"), "source_version": source}
        for source in (task["left"], task["right"]) if source in metadata]} for task in tasks[CANARIES:CANARIES + 3]]
    plan = {"method": METHOD, "versions": versions, "study_key": key, "study_binding": binding,
        "original_result": original_id, "original_plan": old["plan"], "group_result": old_plan["group_result"],
        "implementation": code, "config": config, "design": design, "tasks": tasks,
        "diagnostic": diagnosis["id"], "quarantined_source_versions": sorted(quarantine),
        "limits": {"max_requests": len(tasks), "max_article_exposures": 2 * len(tasks), "max_retries": 0},
        "source_count": len(old_plan["membership"]), "pair_estimand_not_whole_group_purity": True,
        "model_authorized": False, "new_model_calls": 0, "examples": examples,
        "original_groups_unchanged": True, "review_required": True}
    return present(engine, session, bound, "luna_group_validation_plan", plan, render_plan(plan))


def render_plan(plan: Json) -> str:
    counts = dict(Counter(task["status"] for task in plan["tasks"]))
    strata = {row["stratum"]: {key: row[key] for key in ("N", "n", "pi")} for row in plan["design"]["strata"]}
    text = ("Fast pair-evaluation preparation — zero new model calls.\n\n"
        f"Frozen articles {plan['source_count']:,}; sampling strata {strata}. Task coverage {counts}. "
        f"Four separate sequential contract canaries precede {len(plan['design']['selected_pairs'])} frozen evaluation pairs. "
        f"Maximum new run: {plan['limits']['max_requests']} Luna calls, {plan['limits']['max_article_exposures']} article exposures, zero retries; up to four evaluation workers.\n\n"
        "Each request supplies exactly two titles and first-three-paragraph leads, with short source-bound span IDs. "
        "First invalid/unknown response latches a stop across resume; in-flight responses are retained. "
        "The old 399-call study and all group memberships remain unchanged. No new model run is authorized.\n\n"
        "Metrics separate pair precision, retrieval-pool recall and full-frame pair recall. Every between-group pair has nonzero sampling support. "
        "A small random-tail sample can still leave recall very uncertain; zero observed tail positives never proves perfect recall. "
        "Citation checks do not prove semantics; independent human references are required for validated accuracy. Pair accuracy does not validate entire groups.\n\n"
        "Available prepared examples:")
    for row in plan["examples"]:
        articles = "; ".join(f"[{a.get('title') or a['source_version']}]({a['url']})" if a.get("url") else a["source_version"] for a in row["articles"])
        text += f"\n\n- {row['stratum']}: {articles}"
    return text


def _policy(policy: Json, plan_id: str, plan: Json) -> None:
    expected = {"method": APPROVAL_METHOD, "plan": plan_id, "study_key": plan["study_key"],
        **plan["limits"], "allow_codex_account_execution": True, "allow_external_processing": True}
    if any(policy.get(key) != val or type(policy.get(key)) is not type(val) for key, val in expected.items()):
        raise ResearchError("event_eval_new_plan_bound_approval_required")
    if any(not isinstance(policy.get(key), str) or not policy[key].strip() for key in ("approved_by", "instruction")):
        raise ResearchError("event_eval_approval_identity_required")
    try:
        expiry = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("expired")
    except (KeyError, ValueError, TypeError, AttributeError) as error:
        raise ResearchError("event_eval_approval_expired_or_invalid") from error


def execute(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_eval_math import estimate_pair_metrics, pair_id
    from .event_pair_reference import validate_answer, validate_request
    from .event_eval_provider import PairProvider

    require_active(engine, session)
    if set(data) - {"phase", "plan", "study_key", "approval_policy", "reuse_cache"} or data.get("reuse_cache") is not True:
        raise ResearchError("event_eval_exact_execution_fields_required")
    plan_id = data["plan"]
    plan = engine.ledger.get(plan_id, "luna_group_validation_plan")
    if plan.get("method") != METHOD or plan["study_key"] != data["study_key"] or plan["implementation"] != implementation():
        raise ResearchError("event_eval_execution_binding_changed")
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("event_eval_context_versions_changed")
    bound = Context(context.objective, context.actor, plan["versions"])
    canaries = [task for task in plan["tasks"] if task["phase"] == "canary"]
    evaluation = [task for task in plan["tasks"] if task["phase"] == "evaluation"]
    if (len(canaries) != CANARIES or len(canaries) + len(evaluation) != len(plan["tasks"])
            or len({task["pair_id"] for task in plan["tasks"]}) != len(plan["tasks"])
            or not 1 <= len(evaluation) <= 64
            or plan["limits"] != {"max_requests": len(plan["tasks"]), "max_article_exposures": 2 * len(plan["tasks"]), "max_retries": 0}
            or any(task["pair_id"] != pair_id(task["left"], task["right"]) for task in plan["tasks"])
            or {task["pair_id"]: (task["left"], task["right"], task["stratum"], task["pi"]) for task in evaluation}
                != {row["pair_id"]: (row["left"], row["right"], row["stratum"], row["pi"]) for row in plan["design"]["selected_pairs"]}):
        raise ResearchError("event_eval_plan_frame_or_canary_barrier_changed")
    # Validate full-support probabilities and the frozen draw before any dispatch.
    estimate_pair_metrics(plan["design"], [], reference_kind="model")
    policy_id = data["approval_policy"]
    policy = engine.ledger.get(policy_id, "policy")["content"]
    _policy(policy, plan_id, plan)
    executable = Path(plan["config"]["codex_executable"])
    if not executable.is_absolute() or not executable.is_file() or hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]:
        raise ResearchError("event_eval_executable_changed")
    binding = {"plan": plan_id, "policy": policy_id, "approval": policy, "implementation": plan["implementation"], "config": plan["config"]}
    previous = engine.ledger.db.execute("SELECT payload FROM records WHERE kind='event_pair_eval_authorization' AND logical_key=?", (plan["study_key"],)).fetchall()
    if any(json.loads(row[0]) != binding for row in previous):
        raise ResearchError("event_eval_approval_cannot_reset_budget")
    if not previous:
        engine.ledger.record(session, "event_pair_eval_authorization", plan["study_key"], binding)
    history = [json.loads(row[0]) for row in engine.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.event_pair_evaluation_study')=?", (plan["study_key"],))]
    if len({row["attempt"] for row in history}) != len(history) or len({row["pair_id"] for row in history}) != len(history):
        raise ResearchError("event_eval_duplicate_history")
    expected = {task["pair_id"]: task for task in plan["tasks"]}
    outcomes, obstacle = {}, None

    def request_for(task: Json) -> Json:
        request = engine.ledger.artifacts.read(task["request"])
        validate_request(request)
        if (request["versions"] != plan["versions"]
                or [a["source_version"] for a in request["articles"]] != [task["left"], task["right"]]):
            raise ResearchError("event_eval_request_task_or_versions_changed")
        return request

    for intended in history:
        task = expected.get(intended["pair_id"])
        if (task is None or intended["request"] != task["request"] or intended["approval_policy"] != policy_id
                or intended["article_exposures"] != 2 or intended.get("number") != 1
                or intended.get("source_versions") != [task["left"], task["right"]]
                or intended.get("task_key") != digest({"binding": binding, "pair": task["pair_id"]})):
            raise ResearchError("event_eval_history_binding_changed")
        row = engine.ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?", (intended["attempt"],)).fetchone()
        if row is None or row[1] is None:
            outcomes[task["pair_id"]] = {"status": "unknown", "label": "unknown", "attempt": intended["attempt"]}
            obstacle = "Historical unresolved attempt; no redispatch"
        else:
            outcome = engine.ledger.get(row[1], "event_pair_eval_assessment")
            if outcome["status"] != row[0] or outcome["request"] != task["request"] or outcome["pair_id"] != task["pair_id"]:
                raise ResearchError("event_eval_result_binding_changed")
            if outcome["status"] == "valid":
                validate_answer(request_for(task), outcome["answer"])
                engine.ledger.append(session, "model.cache.reused", {"attempt": intended["attempt"], "assessment": row[1], "versions": bound.versions})
            else:
                obstacle = "Prior technical failure latches execution stop"
            outcomes[task["pair_id"]] = {**outcome, "assessment": row[1]}
    prior_latch = engine.ledger.db.execute("SELECT id FROM records WHERE kind='event_pair_eval_stop' AND logical_key=?", (plan["study_key"],)).fetchone()
    if prior_latch:
        obstacle = "Durable technical-failure stop remains latched"
    spent = len(history)
    if spent > plan["limits"]["max_requests"]:
        raise ResearchError("event_eval_cumulative_budget_exceeded")
    for row in engine.ledger.db.execute("SELECT payload FROM records WHERE kind='event_pair_eval_exclusion' AND logical_key=?", (plan["study_key"],)):
        exclusion = json.loads(row[0])
        if exclusion["plan"] != plan_id or exclusion["pair_id"] not in expected:
            raise ResearchError("event_eval_exclusion_binding_changed")
        outcomes.setdefault(exclusion["pair_id"], {"status": "unavailable", "label": "unknown", "exclusion": exclusion})
    provider = None
    if any(task["pair_id"] not in outcomes and task["status"] == "prepared" for task in plan["tasks"]) and not obstacle:
        if engine.config.offline:
            raise ResearchError("event_eval_online_mode_and_concrete_approval_required")
        provider = PairProvider(engine.ledger.root / "event-pair-workers", plan["config"])
    manifest = save(engine, session, {"binding": binding, "tasks": plan["tasks"], "existing_attempts": history}, "Exact pair-evaluation batch before dispatch")
    batch = engine.ledger.record(session, "event_pair_eval_batch", digest(binding), {"manifest": manifest, "binding": binding})
    timings = []
    for phase, workers in (("canary", 1), ("evaluation", 4)):
        if obstacle:
            break
        if phase == "evaluation" and not all(outcomes.get(task["pair_id"], {}).get("status") == "valid" for task in plan["tasks"] if task["phase"] == "canary"):
            obstacle = "All four sequential canaries must pass before evaluation opens"
            break
        phase_tasks = [task for task in plan["tasks"] if task["phase"] == phase and task["pair_id"] not in outcomes]
        for offset in range(0, len(phase_tasks), workers):
            if obstacle:
                break
            prepared, reserved = [], []
            quarantined_sources = set(plan.get("quarantined_source_versions", []))
            for prior in engine.ledger.unresolved.values():
                quarantined_sources.update(prior.get("source_versions", []))
            for task in phase_tasks[offset:offset + workers]:
                quarantined_overlap = sorted({task["left"], task["right"]} & quarantined_sources)
                if task["status"] != "prepared" or quarantined_overlap:
                    exclusion = {"plan": plan_id, "pair_id": task["pair_id"], "request": task["request"],
                        "reason": "unresolved_source_quarantine" if quarantined_overlap else task["status"],
                        "source_overlap": quarantined_overlap, "answer": None, "replacement": False}
                    excluded_id = engine.ledger.record(session, "event_pair_eval_exclusion", plan["study_key"], exclusion)
                    outcomes[task["pair_id"]] = {"status": "unavailable", "label": "unknown", "exclusion": excluded_id}
                    if phase == "canary":
                        obstacle = "Canary source or packet unavailable"
                        engine.ledger.record(session, "event_pair_eval_stop", plan["study_key"], {"plan": plan_id,
                            "policy": policy_id, "exclusion": excluded_id, "stop_remains_latched": True})
                    continue
                _policy(policy, plan_id, plan)
                if spent >= plan["limits"]["max_requests"] or 2 * (spent + 1) > plan["limits"]["max_article_exposures"]:
                    raise ResearchError("event_eval_cumulative_budget_exceeded")
                request = request_for(task)
                if provider is None:
                    raise ResearchError("event_eval_provider_unavailable")
                invocation = provider.prepare(request)
                dispatch = save(engine, session, invocation.manifest(), "Exact pair CLI invocation before intended attempt")
                intended = {"attempt": str(uuid.uuid4()), "task_key": digest({"binding": binding, "pair": task["pair_id"]}),
                    "number": 1, "batch": batch, "request": task["request"], "dispatch": dispatch, "started_at": utc(),
                    "event_pair_evaluation_study": plan["study_key"], "pair_id": task["pair_id"],
                    "source_versions": [task["left"], task["right"]], "article_exposures": 2, "approval_policy": policy_id}
                engine.ledger.append(session, "model.attempt.intended", intended)
                engine.ledger.unresolved[intended["attempt"]] = intended
                spent += 1
                prepared.append((invocation, intended["attempt"]))
                reserved.append((task, intended))
            started = time.perf_counter()
            for index, response in engine.gateway.codex_dispatch(session, provider, prepared, workers):
                task, intended = reserved[index]
                response_ref = save(engine, session, asdict(response), "Exact observed pair response before validation")
                unknown = bool((response.raw_response or {}).get("unknown_outcome"))
                answer, validation, error = None, {}, None
                try:
                    if unknown or response.payload is None:
                        raise ResearchError("event_eval_transport_unknown" if unknown else "event_eval_response_unavailable")
                    validation = validate_answer(engine.ledger.artifacts.read(task["request"]), response.payload)
                    answer = response.payload
                except AuditError:
                    raise
                except ResearchError as failure:
                    error = str(failure)
                status = "unknown" if unknown else "valid" if answer is not None else "invalid"
                value = {"pair_id": task["pair_id"], "phase": phase, "request": task["request"], "response": response_ref,
                    "attempt": intended["attempt"], "status": status, "label": answer["label"] if answer is not None else "unknown",
                    "answer": answer, "validation": validation, "error": error, "observed_model": response.model,
                    "request_id": response.request_id, "usage": response.usage, "human_validated": False}
                assessment = engine.ledger.record(session, "event_pair_eval_assessment", intended["attempt"], value)

                def projection(event: int, intended: Json = intended, assessment: str = assessment, status: str = status, response_ref: str = response_ref) -> None:
                    engine.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (intended["attempt"], intended["task_key"],
                        batch, 1, task["request"], response_ref, status, assessment, None, event))

                engine.ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                    "attempt": intended["attempt"], "status": status, "response": response_ref, "assessment": assessment, "ended_at": utc()}, projection)
                if not unknown:
                    engine.ledger.unresolved.pop(intended["attempt"], None)
                outcomes[task["pair_id"]] = {**value, "assessment": assessment}
                if status != "valid":
                    obstacle = "Technical failure: new dispatch stopped; in-flight calls retained; no retry"
                    engine.ledger.record(session, "event_pair_eval_stop", plan["study_key"], {"attempt": intended["attempt"], "assessment": assessment,
                        "plan": plan_id, "policy": policy_id, "error": error, "stop_remains_latched": True})
            timings.append({"phase": phase, "attempts": len(reserved), "wall_seconds": time.perf_counter() - started})
    judgments = [{"pair_id": task["pair_id"], "label": outcomes.get(task["pair_id"], {}).get("label", "pending")} for task in plan["tasks"] if task["phase"] == "evaluation"]
    metrics = estimate_pair_metrics(plan["design"], judgments, reference_kind="model")
    value = {"method": METHOD, "versions": plan["versions"], "plan": plan_id, "study_key": plan["study_key"],
        "status": "complete" if len(outcomes) == len(plan["tasks"]) and all(x["status"] == "valid" for x in outcomes.values()) else "partial",
        "outcomes": outcomes, "outcome_counts": dict(Counter(row["status"] for row in outcomes.values())),
        "pending": len(plan["tasks"]) - len(outcomes), "workflow_model_attempts": spent, "workflow_article_exposures": 2 * spent,
        "automatic_retries": 0, "obstacle": obstacle, "metrics": metrics, "batch_timings": timings,
        "human_validated": False, "memberships_changed": False, "canary_count": CANARIES}
    return present(engine, session, bound, "luna_group_validation_result", value,
        f"Fast pair evaluation: {value['status']}. Attempts {spent}/{plan['limits']['max_requests']}; exposures {2 * spent}; retries 0. "
        f"Outcomes {value['outcome_counts']}; pending {value['pending']}; obstacle {obstacle}.\n\n"
        f"Conditional model-reference metrics: {metrics}.\n\n"
        "Canaries are excluded from estimates. Full-frame pair recall can remain uninformative because missed matches are rare in the random tail. "
        "No independent human validation, whole-group purity claim or membership change follows.")


class EventEvaluationResearch(Research):
    """Explicit versioned phases inside the audited Luna evaluation operation."""

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data.get("phase") == "prepare_pairs":
            return prepare(self, session, context, data)
        if data.get("phase") == "execute_pairs":
            return execute(self, session, context, data)
        if data.get("phase") == "review_template":
            from .event_eval_reviews import review_template

            if set(data) != {"phase", "plan"}:
                raise ResearchError("event_eval_review_template_fields_invalid")
            return review_template(self, session, context, {"plan": data["plan"]})
        if data.get("phase") == "import_reviews":
            from .event_eval_reviews import import_reviews

            if set(data) != {"phase", "plan", "reviewer", "reviews_file"}:
                raise ResearchError("event_eval_review_import_fields_invalid")
            return import_reviews(self, session, context, data)
        if data.get("phase") == "approve_pairs":
            if set(data) != {"phase", "plan", "study_key", "approval", "reuse_cache"}:
                raise ResearchError("event_eval_composed_approval_fields_invalid")
            plan = self.ledger.get(data["plan"], "luna_group_validation_plan")
            if plan.get("method") != METHOD or plan["study_key"] != data["study_key"]:
                raise ResearchError("event_eval_new_plan_bound_approval_required")
            _policy(data["approval"], data["plan"], plan)
            policy = self._version(session, context, {"kind": "policy", "key": data["study_key"] + "-approval",
                "content": data["approval"]})["id"]
            return execute(self, session, context, {"phase": "execute_pairs", "plan": data["plan"],
                "study_key": data["study_key"], "approval_policy": policy, "reuse_cache": data["reuse_cache"]})
        return super()._luna_group_validation(session, context, data)
