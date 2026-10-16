"""Audited continuation of untouched Luna tasks without retrying rejected attempts.

This execution-control amendment preserves the original packets, authorization,
model and cumulative study budget. It does not relax answer validation.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from .common import AuditError, Context, Json, ResearchError, digest, require_active, require_no_credentials, utc
from .codex_provider import _parse_events
from . import luna_validation_gateway as original


METHOD = "luna-untouched-primary-continuation-v1"
OUTPUT_CAP_ERROR = "codex_output_acceptance_limit_exceeded"
REPARSE_BYTE_CAP = 2 * 1024 * 1024
CONTENT_VALIDATION_ERRORS = frozenset({
    "luna_schema_invalid", "luna_incomplete_passage_coverage", "luna_incomplete_source_coverage",
    "luna_blank_rationale", "luna_quote_invalid", "luna_single_article_group_claim_invalid",
    "luna_partition_coverage_invalid", "luna_anchor_coverage_invalid", "luna_blank_or_padded_field",
    "luna_invalid_actor", "luna_uncited_factual_field", "luna_decisive_event_anchors_required",
})


def _totals(history: list[Json]) -> tuple[int, int]:
    if any(type(item["article_exposures"]) is not int or item["article_exposures"] < 1 for item in history):
        raise ResearchError("luna_historical_budget_exceeded")
    spent, exposures = len(history), sum(item["article_exposures"] for item in history)
    if spent > 400 or exposures > 6000:
        raise ResearchError("luna_historical_budget_exceeded")
    return spent, exposures


def _classification(engine: Any, outcome: Json) -> str:
    if outcome["status"] == "valid":
        return "valid"
    if outcome["status"] == "failed":
        return "preparation_unavailable"
    if outcome["status"] == "unknown":
        return "unknown"
    if outcome["status"] == "invalid" and outcome.get("error") in CONTENT_VALIDATION_ERRORS:
        if outcome.get("retained_transport_revalidated") is True and outcome.get("revalidation"):
            check = engine.ledger.get(outcome["revalidation"], "luna_lead_revalidation")
            if (check["status"] == "invalid" and check["error"] == outcome["error"]
                    and check["request"] == outcome["request"] and check["response"] == outcome["response"]
                    and check["transport_verified"] is True):
                return "known_content_validation_failure"
        response = engine.ledger.artifacts.read(outcome["response"])
        transport = response.get("raw_response")
        if (response.get("payload") is not None and isinstance(transport, dict)
                and transport.get("transport_status") == "returned"
                and transport.get("failure") is None and not transport.get("unknown_outcome")):
            return "known_content_validation_failure"
    return "transport_or_unrecognized_failure"


def _recover_output_cap(engine: Any, session: str, context: Context, task: Json,
                        outcome: Json, amendment: str) -> Json:
    """Reparse permitted retained bytes only; never redispatch or alter old records."""
    if outcome.get("status") != "invalid" or outcome.get("error") != OUTPUT_CAP_ERROR:
        return outcome
    response = engine.ledger.artifacts.read(outcome["response"])
    raw = response.get("raw_response")
    if (not isinstance(raw, dict) or response.get("payload") is not None
            or raw.get("failure") != OUTPUT_CAP_ERROR or raw.get("unknown_outcome") is not False
            or type(raw.get("exit_code")) is not int or raw["exit_code"] != 0
            or not isinstance(raw.get("stdout"), str) or not isinstance(raw.get("stderr"), str)):
        return outcome
    stdout, stderr = raw["stdout"], raw["stderr"]
    if len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")) > REPARSE_BYTE_CAP:
        return outcome
    try:
        require_no_credentials({"stdout": stdout, "stderr": stderr})
    except AuditError:
        raise
    except ResearchError:
        return outcome
    events, payload, failure, observed_model, usage = _parse_events(stdout)
    if failure is not None or payload is None or not any(event.get("type") == "turn.completed" for event in events):
        return outcome
    request = engine.ledger.artifacts.read(task["request_ref"])
    if request.get("versions") != context.versions:
        raise ResearchError("luna_revalidation_request_versions_changed")
    validation, error = {}, None
    try:
        validation = original.validate_answer(request, payload)
    except AuditError:
        raise
    except ResearchError as problem:
        error = str(problem)
    value = {"method": "retained-output-cap-reparse-v1", "versions": context.versions,
        "control_amendment": amendment, "original_attempt": outcome["attempt"],
        "original_assessment": outcome["assessment"], "request": task["request_ref"],
        "response": outcome["response"], "original_status": outcome["status"], "original_error": outcome["error"],
        "transport_verified": True, "retained_bytes": len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")),
        "byte_cap": REPARSE_BYTE_CAP, "status": "valid" if error is None else "invalid", "error": error,
        "answer": payload if error is None else None, "validation": validation,
        "observed_model": observed_model, "usage": usage, "human_validated": False,
        "model_calls": 0, "retry": False, "old_attempt_projection_unchanged": True}
    identifier = engine.ledger.record(session, "luna_lead_revalidation", digest(value), value)
    engine.ledger.append(session, "luna.continuation.response.revalidated", {
        "attempt": outcome["attempt"], "assessment": outcome["assessment"], "revalidation": identifier,
        "status": value["status"], "error": error, "control_amendment": amendment, "model_calls": 0})
    return {**outcome, "status": value["status"], "error": error, "answer": value["answer"],
        "validation": validation, "original_status": outcome["status"], "original_error": outcome["error"],
        "revalidation": identifier, "retained_transport_revalidated": True}


def render_diagnostic(value: Json) -> str:
    lines = ["Luna continuation technical diagnostic — no new model calls yet.",
        f"Original result: {value['original_result']}; frozen plan: {value['plan']}.",
        f"Existing attempts {value['workflow_model_attempts']}/400; article exposures "
        f"{value['workflow_article_exposures']}/6,000; untouched tasks {value['untouched_tasks']}; automatic retries 0.",
        "Retained outcomes by mode and recorded validation/transport code:"]
    lines.extend(f"- {row['mode']}: {row['status']}; {row['error'] or 'none'}; {row['classification']}: {row['count']}"
                 for row in value["outcome_codes"])
    lines.append(f"Retained byte-cap responses revalidated without new model calls: {len(value['revalidations'])}. "
        "Original invalid attempt projections and responses remain unchanged; recovered outcomes link separate revalidation records.")
    lines.append(f"Dispatch guard: {value['obstacle'] or 'only previously untouched primary tasks may continue'}. "
        "No rejected attempt is retried, no packet or inclusion criterion changes, and missing judgments remain missing.")
    return "\n\n".join(lines)


def run(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    allowed = {"result", "study_key", "continue_untouched", "authorization_instruction", "workers", "reuse_cache"}
    if (set(data) - allowed or data.get("continue_untouched") is not True
            or data.get("reuse_cache", True) is not True
            or any(not isinstance(data.get(key), str) or not data[key].strip()
                   for key in ("result", "study_key", "authorization_instruction"))):
        raise ResearchError("luna_explicit_untouched_continuation_authorization_required")
    workers = data.get("workers", 4)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ResearchError("luna_workers_outside_1_4")
    if engine.config.offline:
        raise ResearchError("luna_codex_execution_requires_explicit_online_mode")
    source_bytes = Path(__file__).read_bytes()
    implementation = hashlib.sha256(source_bytes).hexdigest()
    implementation_artifact = original._artifact(engine, session, {
        "module": Path(__file__).name, "sha256": implementation, "source_utf8": source_bytes.decode("utf-8")},
        "Exact continuation implementation source bytes before control registration or prior-result reads")
    control = {"method": METHOD, "original_result": data["result"], "study_key": data["study_key"],
        "authorization_instruction": data["authorization_instruction"], "implementation_sha256": implementation,
        "implementation_artifact": implementation_artifact,
        "untouched_primary_tasks_only": True, "answer_validation_unchanged": True,
        "continue_after_only": sorted(CONTENT_VALIDATION_ERRORS),
        "max_requests": 400, "max_article_exposures": 6000, "automatic_retries": 0,
        "stop_on": ["transport failure", "unknown outcome", "unrecognized validation error", "audit failure"],
        "execution_order": ["group audit", "group held_out", "anchor audit", "anchor held_out"],
        "no_label_tuning": True, "interim_group_result_before_anchors": True,
        "heldout_policy": "All packets already frozen; held-out groups precede audit anchors without adaptation",
        "retained_output_revalidation": {"only_error": OUTPUT_CAP_ERROR, "byte_cap": REPARSE_BYTE_CAP,
            "require_exit_code": 0, "require_unknown_false": True, "require_complete_single_payload": True,
            "unchanged_answer_validator": True, "new_model_calls": 0, "retry": False,
            "old_response_payloads_and_attempt_projections_unchanged": True},
        "criteria_or_membership_changes": False}
    # Register the control change before reading prior research results or packets.
    amendment = engine._version(session, context, {"kind": "protocol",
        "key": data["study_key"] + "-untouched-continuation-control", "content": control})["id"]
    old = engine.ledger.get(data["result"], "luna_group_validation_result")
    plan_id, study = old["plan"], data["study_key"]
    plan = engine.ledger.get(plan_id, "luna_group_validation_plan")
    if old["study_key"] != study or plan["study_key"] != study or old["versions"] != plan["versions"]:
        raise ResearchError("luna_plan_study_or_versions_mismatch")
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("luna_plan_study_or_versions_mismatch")
    bound = Context(context.objective, context.actor, plan["versions"])
    for kind, reference in bound.versions.items():
        engine.ledger.get(reference, kind)
    engine.ledger.append(session, "luna.continuation.versions.bound",
        {"original_result": data["result"], "plan": plan_id, "versions": bound.versions,
         "control_amendment": amendment})
    rows = engine.ledger.db.execute(
        "SELECT payload FROM events WHERE kind='luna.validation.authorization.bound' "
        "AND json_extract(payload,'$.study_key')=?", (study,)).fetchall()
    if not rows:
        raise ResearchError("luna_original_authorization_missing")
    binding = json.loads(rows[0][0])["binding"]
    if (binding["plan"] != plan_id or binding["study_key"] != study
            or binding["versions"] != bound.versions or binding["config"] != plan["config"]
            or binding["implementation"] != original._implementation() or binding["automatic_retries"] != 0):
        raise ResearchError("luna_study_authorization_or_implementation_changed")
    original._bind(engine, session, binding)
    policy_id = binding["approval_policy"]
    policy = engine.ledger.get(policy_id, "policy")["content"]
    if policy != binding["approval"]:
        raise ResearchError("luna_study_authorization_or_implementation_changed")
    original._approval(policy, plan_id, study)
    config = plan["config"]
    executable = Path(config["codex_executable"])
    if (not executable.is_absolute() or not executable.is_file()
            or hashlib.sha256(executable.read_bytes()).hexdigest() != config["executable_sha256"]):
        raise ResearchError("luna_codex_executable_changed")
    if not plan["workload"]["within_budget"]:
        raise ResearchError("luna_prepared_workload_exceeds_budget")
    history = original._history(engine, study)
    spent, exposures = _totals(history)
    initial_spent = spent
    tasks = sorted(plan["tasks"], key=lambda task: (task["mode"] != "group", task["fold"] == "held_out", task["logical_id"]))
    if len({task["logical_id"] for task in tasks}) != len(tasks):
        raise ResearchError("luna_duplicate_logical_task_id")
    outcomes: dict[str, Json] = {}
    pending: list[Json] = []
    known_keys: set[str] = set()
    codes: Counter[tuple[str, str, str | None, str]] = Counter()
    blocked = None
    for task in tasks:
        key = digest({"binding": binding, "task": task})
        known_keys.add(key)
        previous = [item for item in history if item["task_key"] == key]
        if len(previous) > 1:
            raise ResearchError("luna_duplicate_attempt_history")
        if task["status"] != "prepared":
            if previous:
                raise ResearchError("luna_unprepared_task_has_dispatch_history")
            outcome = {"status": "failed", "error": task["status"], "answer": None}
        elif not previous:
            pending.append(task)
            continue
        else:
            intended = previous[0]
            if (intended["article_exposures"] != len(task["source_versions"])
                    or intended["source_versions"] != task["source_versions"]
                    or intended["request"] != task["request_ref"]
                    or intended["approval_policy"] != policy_id or intended["number"] != 1):
                raise ResearchError("luna_prior_attempt_binding_changed")
            row = engine.ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?",
                                           (intended["attempt"],)).fetchone()
            if row is None or row[1] is None:
                outcome = {"status": "unknown", "answer": None, "error": "luna_prior_attempt_unresolved",
                           "attempt": intended["attempt"]}
            else:
                value = engine.ledger.get(row[1], "luna_lead_assessment")
                if (value["status"] != row[0] or value["task"] != task["logical_id"]
                        or value["request"] != task["request_ref"]):
                    raise ResearchError("luna_prior_assessment_binding_changed")
                outcome = {**value, "assessment": row[1], "attempt": intended["attempt"]}
                request = engine.ledger.artifacts.read(task["request_ref"])
                original.validate_request(request)
                if row[0] == "valid":
                    original.validate_answer(request, value["answer"])
                    engine.ledger.append(session, "model.cache.reused", {"task_key": key,
                        "attempt": intended["attempt"], "versions": bound.versions,
                        "assessment": row[1], "luna_validation_study": study,
                        "continuation_control_amendment": amendment})
        outcome = _recover_output_cap(engine, session, bound, task, outcome, amendment)
        outcomes[task["logical_id"]] = outcome
        classification = _classification(engine, outcome)
        codes[(task["mode"], outcome["status"], outcome.get("error"), classification)] += 1
        if classification in {"unknown", "transport_or_unrecognized_failure"}:
            blocked = "Prior unknown, transport or unrecognized failure; no new dispatch allowed"
    if any(item["task_key"] not in known_keys for item in history):
        raise ResearchError("luna_dispatch_history_outside_frozen_plan")
    diagnostic = {"method": METHOD, "versions": bound.versions, "original_result": data["result"],
        "plan": plan_id, "study_key": study, "control_amendment": amendment,
        "workflow_model_attempts": spent, "workflow_article_exposures": exposures,
        "untouched_tasks": len(pending), "new_model_calls": 0, "automatic_retries": 0,
        "outcome_codes": [{"mode": key[0], "status": key[1], "error": key[2],
            "classification": key[3], "count": count} for key, count in sorted(codes.items())],
        "revalidations": [{"attempt": outcome["attempt"], "revalidation": outcome["revalidation"],
            "original_status": outcome["original_status"], "original_error": outcome["original_error"],
            "status": outcome["status"], "error": outcome.get("error")}
            for outcome in outcomes.values() if outcome.get("revalidation")],
        "obstacle": blocked, "source_text_included": False}
    diagnostic_id = engine.ledger.record(session, "luna_group_validation_diagnostic", digest(diagnostic), diagnostic)
    diagnostic_presentation = engine._record_presentation(session, bound, {
        "results": [{"kind": "luna_group_validation_diagnostic", "id": diagnostic_id}],
        "markdown": render_diagnostic(diagnostic), "destination": "codex_chat", "status": "prepared_for_delivery"})
    manifest = original._artifact(engine, session, {"binding": binding, "control_amendment": amendment,
        "continuation_implementation_sha256": implementation, "original_result": data["result"],
        "continuation_implementation_artifact": implementation_artifact,
        "untouched_tasks": pending, "existing_attempts": [item["attempt"] for item in history],
        "diagnostic": diagnostic_id, "scope": {"max_requests": 400, "max_article_exposures": 6000, "automatic_retries": 0}},
        "Continuation control, original bindings, existing spend and untouched request manifest before dispatch")
    batch = engine.ledger.record(session, "luna_validation_batch", digest({"binding": binding, "control": amendment}),
        {"manifest": manifest, "binding": binding, "control_amendment": amendment})
    heldout_open = bool(engine.ledger.db.execute(
        "SELECT 1 FROM events WHERE kind='luna.validation.holdout.opened' "
        "AND json_extract(payload,'$.study_key')=? LIMIT 1", (study,)).fetchone())
    provider = original.LunaProvider(engine.ledger.root / "codex-workers", config) if pending and not blocked else None
    def capture_result(interim: bool = False) -> Json:
        counts = {status: sum(outcome["status"] == status for outcome in outcomes.values())
                  for status in ("valid", "invalid", "unknown", "failed")}
        result = {"versions": bound.versions, "plan": plan_id, "study_key": study,
            "group_result": plan["group_result"], "manifest": manifest, "batch": batch,
            "status": "complete" if counts["valid"] == len(tasks) else "partial",
            "obstacle": ("Group screen finished; anchor screening remains pending" if interim else blocked)
                or ("Rejected or unavailable frozen tasks remain unjudged; no retries"
                    if counts["invalid"] + counts["failed"] else None),
            "expected_tasks": len(tasks), "task_counts": {**counts, "pending": len(tasks) - len(outcomes)},
            "preparation_missing_counts": {status: sum(task["status"] == status for task in tasks)
                                           for status in ("source_unavailable", "oversize")},
            "workflow_model_attempts": spent, "workflow_article_exposures": exposures,
            "automatic_retries": 0, "outcomes": dict(outcomes), **original._metrics(plan, outcomes),
            "examples": plan.get("examples", []), "configured_model": "gpt-6-luna", "reasoning_effort": "low",
            "human_validated": False, "full_articles_read": False, "accepted_dossiers": 0, "membership_changes": 0,
            "holdout_scope": "Frozen group audit then held-out tasks before anchors; no label tuning; anchor overlap retained",
            "historical_study_budget_changed": False,
            "model_metadata": "Observed identity and usage retained per attempt; unavailable stays null",
            "continuation_method": METHOD, "control_amendment": amendment, "original_result": data["result"],
            "new_model_attempts": spent - initial_spent, "interim_group_result": interim,
            "retained_output_revalidation_counts": {
                "attempted": sum(bool(item.get("revalidation")) for item in outcomes.values()),
                "valid": sum(bool(item.get("revalidation")) and item["status"] == "valid" for item in outcomes.values()),
                "invalid": sum(bool(item.get("revalidation")) and item["status"] == "invalid" for item in outcomes.values()),
                "original_attempt_projections_changed": False},
            "diagnostic": {"id": diagnostic_id, "presentation": diagnostic_presentation}}
        identifier = engine.ledger.record(session, "luna_group_validation_result", digest(result), result)
        presentation = engine._record_presentation(session, bound, {
            "results": [{"kind": "luna_group_validation_result", "id": identifier}],
            "markdown": original.render_result(result) + f"\n\nContinuation control {amendment}: "
                f"{spent - initial_spent} previously untouched primary attempts; rejected attempts retained without retry. "
                f"Retained byte-cap revalidation counts: {result['retained_output_revalidation_counts']}. "
                + ("Interim whole-group result, saved before the anchor phase." if interim else "Frozen group-first execution; no label tuning."),
            "destination": "codex_chat", "status": "prepared_for_delivery"})
        return {"id": identifier, **result, "presentation": presentation}

    group_capture = False
    phase = None
    cursor = 0
    while cursor < len(pending) and not blocked:
        mode, fold = pending[cursor]["mode"], pending[cursor]["fold"]
        if mode == "anchor" and not group_capture:
            if not all(task["logical_id"] in outcomes for task in tasks if task["mode"] == "group"):
                raise ResearchError("luna_group_first_barrier_incomplete")
            capture_result(interim=True)
            group_capture = True
        if phase != (mode, fold):
            engine.ledger.append(session, "luna.continuation.phase.started", {"mode": mode, "fold": fold,
                "control_amendment": amendment, "all_packets_frozen": True, "label_tuning": False,
                "heldout_groups_may_precede_audit_anchors": True})
            phase = (mode, fold)
        prepared: list[tuple[Any, str]] = []
        dispatched: list[tuple[Json, Json]] = []
        while (cursor < len(pending) and len(prepared) < workers
               and (pending[cursor]["mode"], pending[cursor]["fold"]) == (mode, fold)):
            task = pending[cursor]
            if spent + 1 > 400 or exposures + len(task["source_versions"]) > 6000:
                blocked = "Workflow-wide request/article-exposure cap reached"
                break
            original._approval(policy, plan_id, study)
            request = engine.ledger.artifacts.read(task["request_ref"])
            original.validate_request(request)
            if ([article["source_version"] for article in request["articles"]] != task["source_versions"]
                    or request.get("versions") != bound.versions):
                raise ResearchError("luna_task_sources_or_versions_changed")
            if task["fold"] == "held_out" and not heldout_open:
                engine.ledger.append(session, "luna.validation.holdout.opened", {"study_key": study,
                    "plan": plan_id, "frozen_manifest": manifest, "control_amendment": amendment,
                    "purpose": "Original frozen lead-study validation; no new sampling or historical holdout use"})
                heldout_open = True
            if provider is None:
                raise ResearchError("luna_continuation_provider_unavailable")
            invocation = provider.prepare(request)
            dispatch = original._artifact(engine, session, invocation.manifest(), "Exact untouched Luna invocation before dispatch")
            intended = {"attempt": str(uuid.uuid4()), "task_key": digest({"binding": binding, "task": task}),
                "number": 1, "batch": batch, "request": task["request_ref"], "dispatch": dispatch, "started_at": utc(),
                "luna_validation_study": study, "article_exposures": len(task["source_versions"]),
                "source_versions": task["source_versions"], "approval_policy": policy_id,
                "continuation_control_amendment": amendment, "continuation_implementation_sha256": implementation}
            engine.ledger.append(session, "model.attempt.intended", intended)
            engine.ledger.unresolved[intended["attempt"]] = intended
            history.append(intended)
            spent, exposures = _totals(history)
            prepared.append((invocation, intended["attempt"]))
            dispatched.append((task, intended))
            cursor += 1
        for index, response in engine.gateway.codex_dispatch(session, provider, prepared, workers):
            task, intended = dispatched[index]
            outcome = original._complete(engine, session, task, intended, response)
            outcome = _recover_output_cap(engine, session, bound, task, outcome, amendment)
            outcomes[task["logical_id"]] = outcome
            engine.ledger.append(session, "luna.continuation.task.completed", {"mode": task["mode"],
                "status": outcome["status"], "error": outcome.get("error"),
                "logical_id": task["logical_id"], "attempt": intended["attempt"],
                "original_status": outcome.get("original_status"), "original_error": outcome.get("original_error"),
                "revalidation": outcome.get("revalidation")})
            if _classification(engine, outcome) in {"unknown", "transport_or_unrecognized_failure"}:
                blocked = "New unknown, transport or unrecognized failure; further dispatch stopped"
    return capture_result()
