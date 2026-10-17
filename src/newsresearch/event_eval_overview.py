"""Compact audited reporting of an existing frozen pair evaluation; no judging."""
from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from .common import Context, Json, ResearchError, digest, require_active
from .event_eval_workflow import METHOD as EVALUATION_METHOD, EventEvaluationResearch
from .event_pair_reference import validate_answer, validate_request
from .runtime import audited_handler

METHOD = "fast-event-pair-target-overview-v2"
TARGET_METHOD = "event-pair-precision-90-target-v1"
CANDIDATE_PREPARATION_METHOD = "coverage-guarded-candidate-pair-preparation-v2"
FINE_PREPARATION_METHOD = "coverage-guarded-fine-candidate-pair-preparation-v3"
FROZEN_CANDIDATE_TARGET = {
    "target": .90,
    "decision": "Point target passes only with complete decisive within-group references and pair precision >= .90",
    "missingness": "Unresolved references stay null; show pessimistic and optimistic same-event counts and fractions",
    "confidence": "Report the 95% conditional sampling interval separately; point target does not require or imply a 95% lower bound of .90",
    "human_accuracy_established": False,
}
LABELS = ("same_event", "different_event", "uncertain", "invalid", "unknown", "unavailable", "pending")


def _counts(tasks: list[Json], outcomes: Json) -> Json:
    counts: Counter[str] = Counter({label: 0 for label in LABELS})
    for task in tasks:
        outcome = outcomes.get(task["pair_id"])
        label = "pending" if outcome is None else outcome["label"] if outcome["status"] == "valid" else outcome["status"]
        if label not in counts:
            raise ResearchError("event_eval_overview_outcome_invalid")
        counts[label] += 1
    return {"total": len(tasks), **counts}


def _target_status(counts: Json, precision: Json, target: float) -> Json:
    complete = bool(counts["total"]) and counts["same_event"] + counts["different_event"] == counts["total"]
    point = precision["point"]
    if (point is not None) != complete:
        raise ResearchError("event_eval_overview_point_or_missingness_inconsistent")
    interval = precision["confidence_interval"]
    missingness = precision["weighted_missingness_bounds"]
    return {"target": target, "status": "unresolved" if not complete else
            "met_for_model_references" if point >= target else "below_target",
            "complete_decisive_within_references": complete,
            "confidence_lower_at_target": interval is not None and interval[0] >= target,
            "optimistic_sample_bound_below_target": missingness is not None and missingness[1] < target,
            "human_accuracy_established": False}


def _escape(text: Any) -> str:
    result = str(text).replace("\n", " ").replace("\r", " ")
    for char in ("\\", "`", "*", "_", "[", "]", "<", ">"):
        result = result.replace(char, "\\" + char)
    return result


def _example(engine: Any, session: str, plan: Json, task: Json, outcome: Json) -> Json:
    request = engine.ledger.artifacts.read(task["request"])
    validate_request(request)
    if (request["versions"] != plan["versions"]
            or [article["source_version"] for article in request["articles"]] != [task["left"], task["right"]]):
        raise ResearchError("event_eval_overview_request_binding_invalid")
    validation = validate_answer(request, outcome["answer"])
    engine.ledger.append(session, "event.eval.overview.evidence.inspected", {
        "request": task["request"], "assessment": outcome["assessment"], "pair_id": task["pair_id"],
        "passages": [span["parent_ref"] for span in request["evidence"]],
        "purpose": "Mechanical transcription of retained model labels and exact cited lead prefixes; no new inference"})
    articles = []
    for article in request["articles"]:
        sql = "SELECT json_extract(payload,'$.url') AS url FROM sources WHERE id=?"
        engine.ledger.append(session, "event.eval.overview.source_metadata.inspected", {
            "sql": sql, "parameters": [article["source_version"]], "purpose": "Retained source link only"})
        row = engine.ledger.db.execute(sql, (article["source_version"],)).fetchone()
        if row is None:
            raise ResearchError("event_eval_overview_source_metadata_unavailable")
        articles.append({"source_version": article["source_version"], "title": article["title"], "url": row[0]})
    return {"pair_id": task["pair_id"], "phase": task["phase"], "assessment": outcome["assessment"],
        "request": task["request"], "label": outcome["answer"]["label"], "reason": outcome["answer"]["reason"],
        "articles": articles, "support": [{"span_id": ref["span_id"], "source_version": ref["source_version"],
            "parent_ref": ref["parent_ref"], "exact_prefix": ref["quote"][:160], "clipped": len(ref["quote"]) > 160}
            for ref in validation["evidence_references"]]}


def _percent(value: Any) -> str:
    return "unavailable" if value is None else f"{100 * value:.1f}%"


def _range(value: Any) -> str:
    if isinstance(value, dict):
        suffix = "; nonzero-denominator conditional"
        if value["zero_denominator_possible"]:
            suffix += "; zero denominator possible"
        return "–".join(_percent(value[key]) for key in ("lower", "upper")) + suffix
    return "unavailable (null)" if value is None else "–".join(_percent(x) for x in value)


def render(value: Json) -> str:
    precision, recall = value["pair_precision"], value["pair_recall"]
    target = value["target_status"]
    interval = precision["confidence_interval"]
    bounds = precision["weighted_missingness_bounds"]
    status = {"met_for_model_references": "met on model references", "below_target": "below target",
        "unresolved": "not demonstrated: unresolved references"}[target["status"]]
    count_rows = []
    for name, key in (("Canaries (excluded)", "canary_counts"), ("All evaluation pairs", "evaluation_counts"),
                      ("Within-group evaluation", "within_counts")):
        counts = value[key]
        count_rows.append("| " + " | ".join([name, str(counts["total"]), *[str(counts[label]) for label in LABELS]]) + " |")
    count_table = ("| Scope | Total | Same | Different | Uncertain | Invalid | Unknown | Unavailable | Pending |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n" + "\n".join(count_rows))
    text = (f"**90% pair-precision target: {status}.** Frozen run: {value['execution_status']}.\n\n"
        f"{count_table}\n\n"
        "| Metric | Point | 95% conditional sampling interval | Missingness plug-in bounds |\n"
        "| --- | ---: | --- | --- |\n"
        f"| Pair precision | {_percent(precision['point'])} | {_range(interval)} | {_range(bounds)} |\n"
        f"| Full-frame pair recall | {_percent(recall['point'])} | {_range(recall['confidence_interval'])} | {_range(recall['weighted_missingness_bounds'])} |\n\n"
        f"Complete decisive within-group references: {'yes' if target['complete_decisive_within_references'] else 'no'}. "
        f"Confidence lower bound reaches 90%: {'yes' if target['confidence_lower_at_target'] else 'no'}. "
        f"Optimistic sample missingness bound below 90%: {'yes' if target['optimistic_sample_bound_below_target'] else 'no'}. "
        f"Retrieved-pool recall point: {_percent(value['candidate_pool_recall']['point'])}; "
        f"scope: {value['retrieved_scope']}. The small random-tail sample can leave recall very uncertain.\n\n"
        f"Recorded run: {value['attempts']} calls, {value['article_exposures']} article exposures, "
        f"{value['retries']} retries. Stop/obstacle: {value['obstacle']}. "
        "This overview made zero new model calls. Model lead references are not human gold; citation checks do not prove event identity. "
        "Pair precision does not measure whole-group purity. Intervals condition on correct reference labels; "
        "missingness bounds are sample plug-in diagnostics, not confidence bounds. Memberships remain unchanged.")
    for example in value["examples"]:
        links = []
        for article in example["articles"]:
            url = article["url"]
            title = _escape(article["title"] or article["source_version"])
            links.append(f"[{title}](<{url}>)" if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"}
                         and not any(char in url for char in "<>\n\r") else title)
        text += f"\n\n- Retained model `{example['label']}` ({example['phase']}): {'; '.join(links)}. "
        text += f"Model reason: {_escape(example['reason'])}"
        for span in example["support"]:
            text += f"\n  - {span['span_id']} exact cited prefix: “{_escape(span['exact_prefix'])}”"
            if span["clipped"]:
                text += " (clipped)"
    if not value["examples"]:
        text += "\n\nNo valid retained model answer is available for a source-linked example."
    return text


def overview(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    from_plan = set(data) == {"phase", "result", "target_from_plan"} and data["target_from_plan"] is True
    if not from_plan and set(data) != {"phase", "result", "target_protocol"}:
        raise ResearchError("event_eval_overview_fields_invalid")
    protocol = engine._version(session, context, {"kind": "protocol", "key": METHOD,
        "content": {"method": METHOD, "result": data["result"],
            "target_source": "frozen_result_versions_protocol" if from_plan else data["target_protocol"],
            "procedure": "Verify frozen plan and version bindings, transcribe existing metrics, counts and up to two retained examples",
            "model_calls": 0, "new_evaluations": 0, "memberships_changed": False},
        "amend_latest": True, "reason": "Register compact exact reporting before reading any result, target, or evidence"})["id"]
    result = engine.ledger.get(data["result"], "luna_group_validation_result")
    if result.get("method") != EVALUATION_METHOD:
        raise ResearchError("event_eval_overview_target_or_result_binding_invalid")
    plan = engine.ledger.get(result["plan"], "luna_group_validation_plan")
    if (plan.get("method") != EVALUATION_METHOD or result["versions"] != plan["versions"]
            or result["study_key"] != plan["study_key"] or (context.versions and context.versions != plan["versions"])):
        raise ResearchError("event_eval_overview_plan_or_versions_invalid")
    target_protocol = result["versions"]["protocol"] if from_plan else data["target_protocol"]
    target = engine.ledger.get(target_protocol, "protocol")["content"]
    if from_plan:
        if (target.get("method") not in {CANDIDATE_PREPARATION_METHOD, FINE_PREPARATION_METHOD}
                or plan.get("preparation_method") != target.get("method")
                or not plan.get("candidate_result") or not plan.get("original_plan")
                or target.get("candidate_result") != plan["candidate_result"]
                or target.get("original_plan") != plan["original_plan"]
                or digest(target.get("precision_target")) != digest(FROZEN_CANDIDATE_TARGET)):
            raise ResearchError("event_eval_overview_frozen_target_binding_invalid")
    elif (target.get("method") != TARGET_METHOD or type(target.get("target")) not in {float, int}
            or target["target"] != .90 or target.get("frozen_plan") != result.get("plan")):
        raise ResearchError("event_eval_overview_target_or_result_binding_invalid")
    tasks = plan["tasks"]
    expected = {task["pair_id"]: task for task in tasks}
    outcomes = result["outcomes"]
    if len(expected) != len(tasks) or set(outcomes) - set(expected):
        raise ResearchError("event_eval_overview_frame_invalid")
    for identifier, outcome in outcomes.items():
        task = expected[identifier]
        if "assessment" not in outcome:
            if outcome.get("status") not in {"unknown", "unavailable"}:
                raise ResearchError("event_eval_overview_assessment_required")
            continue
        retained = engine.ledger.get(outcome["assessment"], "event_pair_eval_assessment")
        if (retained != {key: val for key, val in outcome.items() if key != "assessment"}
                or retained["pair_id"] != identifier or retained["request"] != task["request"]
                or retained["phase"] != task["phase"]):
            raise ResearchError("event_eval_overview_assessment_binding_invalid")
    canaries = [task for task in tasks if task["phase"] == "canary"]
    evaluation = [task for task in tasks if task["phase"] == "evaluation"]
    within = [task for task in evaluation if task["stratum"] == "within_group"]
    metrics = result["metrics"]
    if (metrics["reference_kind"] != "model" or metrics["expected_pairs"] != len(evaluation)
            or metrics["within"]["n"] != len(within)):
        raise ResearchError("event_eval_overview_metrics_frame_invalid")
    within_counts = _counts(within, outcomes)
    examples = []
    pool = [task for task in evaluation if outcomes.get(task["pair_id"], {}).get("status") == "valid"]
    if not pool:
        pool = [task for task in canaries if outcomes.get(task["pair_id"], {}).get("status") == "valid"]
    seen = set()
    for task in pool:
        outcome = outcomes[task["pair_id"]]
        if outcome["label"] in seen:
            continue
        examples.append(_example(engine, session, plan, task, outcome))
        seen.add(outcome["label"])
        if len(examples) == 2:
            break
    value = {"method": METHOD, "versions": plan["versions"], "overview_protocol": protocol,
        "target_protocol": target_protocol, "original_result": data["result"], "plan": result["plan"],
        "execution_status": result["status"], "target_status": _target_status(within_counts, metrics["pair_precision"], .90),
        "canary_counts": _counts(canaries, outcomes), "evaluation_counts": _counts(evaluation, outcomes),
        "within_counts": within_counts, "pair_precision": metrics["pair_precision"], "pair_recall": metrics["pair_recall"],
        "candidate_pool_recall": metrics["candidate_pool_recall"], "confidence": metrics["confidence"],
        "retrieved_scope": "not sampled in this candidate evaluation" if from_plan else "saved 100-anchor retrieval union",
        "attempts": result["workflow_model_attempts"], "article_exposures": result["workflow_article_exposures"],
        "retries": result["automatic_retries"], "obstacle": result["obstacle"], "examples": examples,
        "new_model_calls": 0, "new_evaluations": 0, "human_validated": False, "memberships_changed": False}
    bound = Context(context.objective, context.actor, plan["versions"])
    identifier = engine.ledger.record(session, "luna_group_validation_diagnostic", digest(value), value)
    presentation = engine._record_presentation(session, bound, {"results": [
        {"kind": "luna_group_validation_diagnostic", "id": identifier},
        {"kind": "luna_group_validation_result", "id": data["result"]}],
        "markdown": render(value), "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **value, "presentation": presentation}


class EventEvaluationOverviewResearch(EventEvaluationResearch):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data.get("phase") == "pair_target_overview":
            return overview(self, session, context, data)
        return super()._luna_group_validation(session, context, data)
