"""Bounded saved-text extraction through the audited shared Codex gateway.

This module does not authorize a run, embed text, accept findings or change
memberships. A failed or incomplete first attempt stops the immutable lineage.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid

from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .gateway import ProviderResponse

METHOD = "saved-text-event-extraction-v1"
APPROVAL_METHOD = "event-extraction-run-approval-v1"
LIMITS = {"max_requests": 12, "max_article_exposures": 12, "max_retries": 0}
CANARIES = 2


def validate_approval(policy: Json, plan_id: str, plan: Json) -> None:
    """A fresh concrete permission is distinct from scientific acceptance."""
    expected = {"method": APPROVAL_METHOD, "plan": plan_id, "study_key": plan["study_key"],
                **plan["limits"], "allow_codex_account_execution": True,
                "allow_external_processing": True}
    if any(policy.get(key) != value or type(policy.get(key)) is not type(value)
           for key, value in expected.items()):
        raise ResearchError("event_extraction_new_plan_bound_approval_required")
    if any(not isinstance(policy.get(key), str) or not policy[key].strip()
           for key in ("approved_by", "instruction")):
        raise ResearchError("event_extraction_approval_identity_required")
    try:
        expiry = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise ValueError("expired")
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise ResearchError("event_extraction_approval_expired_or_invalid") from error


def execute(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_extraction_contract import validate_output, validate_request
    from .event_extraction_provider import ExtractionProvider, PreparedExtractionInvocation, build_prompt
    from .event_extraction_workflow import _bound_plan, present, render_result, save

    require_active(engine, session)
    if (set(data) != {"phase", "plan", "approval_policy", "reuse_cache"}
            or data.get("phase") != "execute" or data.get("reuse_cache") is not True):
        raise ResearchError("event_extraction_exact_execution_fields_required")
    plan_id = data["plan"]
    plan, bound = _bound_plan(engine, session, context, plan_id)
    tasks = plan["tasks"]
    if len(tasks) < CANARIES:
        raise ResearchError("event_extraction_insufficient_frame_for_canaries")
    unfilled_slots = plan["selection"]["unfilled_slots"]
    if (plan.get("method") != METHOD or plan.get("limits") != LIMITS
            or not CANARIES <= len(tasks) <= LIMITS["max_requests"]
            or type(unfilled_slots) is not int or unfilled_slots != LIMITS["max_requests"] - len(tasks)
            or len({task["task_id"] for task in tasks}) != len(tasks)
            or len({task["source_version"] for task in tasks}) != len(tasks)
            or [task["phase"] for task in tasks] != ["canary"] * CANARIES + ["pilot"] * (len(tasks) - CANARIES)
            or any(task["status"] not in {"prepared", "source_unavailable", "oversize"} for task in tasks)
            or any((task["status"] != "source_unavailable") != isinstance(task.get("request"), str) for task in tasks)):
        raise ResearchError("event_extraction_frozen_queue_or_canaries_changed")
    fixed_config = {"codex_model": "gpt-6-luna", "reasoning_effort": "low",
                    "max_input_bytes": 131072, "max_output_bytes": 65536}
    if (set(plan["config"]) != {*fixed_config, "codex_executable", "executable_sha256", "timeout_seconds"}
            or any(plan["config"].get(key) != value or type(plan["config"].get(key)) is not type(value)
                   for key, value in fixed_config.items())
            or type(plan["config"].get("timeout_seconds")) not in (int, float)
            or not 0 < plan["config"]["timeout_seconds"] <= 180):
        raise ResearchError("event_extraction_frozen_config_changed")
    policy_id = data["approval_policy"]
    policy = engine.ledger.get(policy_id, "policy")["content"]
    validate_approval(policy, plan_id, plan)
    executable = Path(plan["config"]["codex_executable"])
    if (not executable.is_absolute() or not executable.is_file()
            or hashlib.sha256(executable.read_bytes()).hexdigest() != plan["config"]["executable_sha256"]):
        raise ResearchError("event_extraction_executable_changed")
    binding = {"plan": plan_id, "policy": policy_id, "approval": policy,
               "implementation": plan["implementation"], "config": plan["config"]}
    ledger = engine.ledger
    previous = ledger.db.execute(
        "SELECT payload FROM records WHERE kind='event_extraction_authorization' AND logical_key=?",
        (plan["study_key"],)).fetchall()
    if any(json.loads(row[0]) != binding for row in previous):
        raise ResearchError("event_extraction_approval_cannot_reset_budget")
    if not previous:
        ledger.record(session, "event_extraction_authorization", plan["study_key"], binding)
    expected = {task["task_id"]: task for task in tasks}
    order = {task["task_id"]: index for index, task in enumerate(tasks)}
    requests: dict[str, Json] = {}

    def request_for(task: Json) -> Json:
        if task["task_id"] not in requests:
            request = ledger.artifacts.read(task["request"])
            validate_request(request)
            if (request["versions"] != plan["versions"]
                    or request["source"]["source_version"] != task["source_version"]):
                raise ResearchError("event_extraction_request_binding_changed")
            requests[task["task_id"]] = request
        return requests[task["task_id"]]

    # Verify the entire request manifest before the first possible dispatch.
    for task in tasks:
        if task["status"] == "prepared":
            request_for(task)
    history = [json.loads(row[0]) for row in ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' "
        "AND json_extract(payload,'$.event_extraction_study')=? ORDER BY seq",
        (plan["study_key"],))]
    if (len({row["attempt"] for row in history}) != len(history)
            or len({row["task_id"] for row in history}) != len(history)
            or len(history) > LIMITS["max_requests"]
            or sum(row.get("article_exposures", 0) for row in history) > LIMITS["max_article_exposures"]):
        raise ResearchError("event_extraction_duplicate_history_or_budget_exceeded")
    outcomes: dict[str, Json] = {}
    obstacle = None
    cached = 0
    last_index = -1
    replay_provider = ExtractionProvider(ledger.root / "event-extraction-workers", plan["config"]) if history else None
    for intended in history:
        task = expected.get(intended["task_id"])
        if (task is None or task["status"] != "prepared"
                or intended.get("plan") != plan_id or intended.get("approval_policy") != policy_id
                or intended.get("request") != task["request"] or intended.get("number") != 1
                or intended.get("article_exposures") != 1
                or intended.get("source_versions") != [task["source_version"]]
                or intended.get("task_key") != digest({"binding": binding, "task": task["task_id"]})
                or order[task["task_id"]] <= last_index):
            raise ResearchError("event_extraction_history_binding_changed")
        if obstacle:
            raise ResearchError("event_extraction_historical_dispatch_after_stop")
        if task["phase"] == "pilot" and not all(
                outcomes.get(canary["task_id"], {}).get("processing") == "complete"
                for canary in tasks[:CANARIES]):
            raise ResearchError("event_extraction_historical_canary_barrier_changed")
        last_index = order[task["task_id"]]
        prior_batch = ledger.get(intended["batch"], "event_extraction_batch")
        prior_manifest = ledger.artifacts.read(prior_batch["manifest"])
        if (prior_batch["binding"] != binding or prior_manifest["binding"] != binding
                or prior_manifest["tasks"] != tasks):
            raise ResearchError("event_extraction_history_batch_changed")
        dispatch = ledger.artifacts.read(intended["dispatch"])
        prompt = build_prompt(request_for(task))
        cwd = Path(dispatch["cwd"])
        if (replay_provider is None or not cwd.is_absolute() or cwd.parent != replay_provider.workspace
                or not cwd.name.startswith("codex-extraction-")):
            raise ResearchError("event_extraction_history_worker_changed")
        replay = PreparedExtractionInvocation(replay_provider._command(cwd), cwd, prompt,
            request_for(task)["schema"], request_for(task), "gpt-6-luna")
        if dispatch != replay.manifest():
            raise ResearchError("event_extraction_history_dispatch_changed")
        row = ledger.db.execute(
            "SELECT task_key,batch_id,number,request_ref,response_ref,status,result_id,error_type "
            "FROM attempts WHERE id=?", (intended["attempt"],)).fetchone()
        if row is None:
            outcomes[task["task_id"]] = {"task_id": task["task_id"], "source_version": task["source_version"],
                "phase": task["phase"], "request": task["request"], "status": "unknown",
                "processing": "unavailable", "attempt": intended["attempt"], "events": [],
                "event_count": 0, "output": None, "error": "unresolved_historical_attempt"}
            obstacle = "Historical unresolved attempt; no redispatch"
            continue
        if (tuple(row[:4]) != (intended["task_key"], intended["batch"], 1, task["request"])
                or row[6] is None):
            raise ResearchError("event_extraction_attempt_projection_changed")
        outcome = ledger.get(row[6], "event_extraction_assessment")
        identity = {"task_id": task["task_id"], "source_version": task["source_version"],
                    "phase": task["phase"], "request": task["request"], "attempt": intended["attempt"],
                    "plan": plan_id, "status": row[5], "response": row[4], "error": row[7]}
        if any(outcome.get(key) != value for key, value in identity.items()):
            raise ResearchError("event_extraction_result_binding_changed")
        if outcome["status"] in {"valid", "incomplete"}:
            retained = ledger.artifacts.read(outcome["response"])
            validated = validate_output(outcome["output"], request_for(task))
            processing = "complete" if validated["coverage_complete"] and validated["extraction_status"] != "insufficient_evidence" else "incomplete"
            if (retained["payload"] != outcome["output"] or validated != outcome["validation"]
                    or outcome["events"] != validated["events"] or outcome["event_count"] != validated["event_count"]
                    or outcome["processing"] != processing
                    or outcome["status"] != ("valid" if processing == "complete" else "incomplete")):
                raise ResearchError("event_extraction_cached_output_changed")
            ledger.append(session, "model.cache.reused", {"attempt": intended["attempt"],
                "assessment": row[6], "versions": bound.versions, "plan": plan_id, "request": task["request"]})
            cached += 1
        if outcome["status"] != "valid" or outcome["processing"] != "complete":
            obstacle = "Prior failed or incomplete extraction latches execution stop"
        outcomes[task["task_id"]] = {**outcome, "assessment": row[6]}
    for row in ledger.db.execute(
            "SELECT id,payload FROM records WHERE kind='event_extraction_exclusion' AND logical_key=?",
            (plan["study_key"],)):
        exclusion = json.loads(row[1])
        task = expected.get(exclusion.get("task_id"))
        if (task is None or exclusion.get("plan") != plan_id
                or exclusion.get("request") != task["request"]
                or exclusion.get("source_version") != task["source_version"]
                or exclusion["task_id"] in outcomes):
            raise ResearchError("event_extraction_exclusion_binding_changed")
        outcomes[task["task_id"]] = {"task_id": task["task_id"], "source_version": task["source_version"],
            "phase": task["phase"], "status": "unavailable", "processing": "unavailable",
            "event_count": 0, "events": [], "exclusion": row[0], "error": exclusion["reason"]}
    stop_records = ledger.db.execute(
        "SELECT payload FROM records WHERE kind='event_extraction_stop' AND logical_key=?",
        (plan["study_key"],)).fetchall()
    for row in stop_records:
        stop = json.loads(row[0])
        if stop.get("plan") != plan_id or stop.get("policy") != policy_id or stop.get("stop_remains_latched") is not True:
            raise ResearchError("event_extraction_stop_binding_changed")
    if stop_records:
        obstacle = "Durable extraction stop remains latched"

    def latch(reason: str, **details: Any) -> None:
        nonlocal obstacle
        obstacle = reason
        ledger.record(session, "event_extraction_stop", plan["study_key"], {
            "plan": plan_id, "policy": policy_id, "reason": reason,
            "stop_remains_latched": True, **details})

    if obstacle and not stop_records:
        latch(obstacle)

    def exclude(task: Json, reason: str) -> None:
        value = {"plan": plan_id, "task_id": task["task_id"], "source_version": task["source_version"],
                 "request": task["request"], "phase": task["phase"], "reason": reason,
                 "replacement": False, "output": None}
        identifier = ledger.record(session, "event_extraction_exclusion", plan["study_key"], value)
        outcomes[task["task_id"]] = {"task_id": task["task_id"], "source_version": task["source_version"],
            "phase": task["phase"], "status": "unavailable", "processing": "unavailable",
            "event_count": 0, "events": [], "exclusion": identifier, "error": reason}

    for task in tasks:
        if task["status"] != "prepared" and task["task_id"] not in outcomes:
            exclude(task, task["status"])
    if any(task["status"] != "prepared" for task in tasks[:CANARIES]) and not obstacle:
        latch("A frozen canary is unavailable; no replacement or dispatch")
    provider = None
    if not obstacle and any(task["task_id"] not in outcomes for task in tasks):
        if engine.config.offline:
            raise ResearchError("event_extraction_online_mode_and_concrete_approval_required")
        provider = ExtractionProvider(ledger.root / "event-extraction-workers", plan["config"])
    manifest = save(engine, session, {"binding": binding, "tasks": tasks, "existing_attempts": history},
                    "Exact saved-text extraction batch before dispatch")
    batch = ledger.record(session, "event_extraction_batch", digest(binding), {"manifest": manifest, "binding": binding})
    spent = len(history)
    new_attempts = 0
    timings = []
    for task in tasks:
        if obstacle:
            break
        if task["task_id"] in outcomes:
            continue
        if task["phase"] == "pilot" and not all(
                outcomes.get(canary["task_id"], {}).get("processing") == "complete" for canary in tasks[:CANARIES]):
            latch("Both sequential canaries must complete before the pilot opens")
            break
        unresolved_sources = {source for value in ledger.unresolved.values() for source in value.get("source_versions", [])}
        if task["source_version"] in unresolved_sources:
            exclude(task, "unresolved_source_quarantine")
            latch("An unresolved source cannot be dispatched under a changed task", task_id=task["task_id"])
            break
        validate_approval(policy, plan_id, plan)
        if spent >= LIMITS["max_requests"] or spent + 1 > LIMITS["max_article_exposures"]:
            raise ResearchError("event_extraction_cumulative_budget_exceeded")
        if provider is None:
            raise ResearchError("event_extraction_provider_unavailable")
        try:
            invocation = provider.prepare(request_for(task))
            dispatch = save(engine, session, invocation.manifest(), "Exact extraction CLI invocation before attempt intent")
        except AuditError:
            raise
        except Exception:
            exclude(task, "invocation_preparation_failed_no_dispatch")
            latch("Invocation preparation failed; no replacement or retry", task_id=task["task_id"])
            break
        intended = {"attempt": str(uuid.uuid4()), "task_key": digest({"binding": binding, "task": task["task_id"]}),
            "number": 1, "batch": batch, "plan": plan_id, "request": task["request"], "dispatch": dispatch,
            "started_at": utc(), "event_extraction_study": plan["study_key"], "task_id": task["task_id"],
            "source_versions": [task["source_version"]], "article_exposures": 1, "approval_policy": policy_id}
        ledger.append(session, "model.attempt.intended", intended)
        ledger.unresolved[intended["attempt"]] = intended
        spent += 1
        new_attempts += 1
        started = time.perf_counter()
        try:
            responses = list(engine.gateway.codex_dispatch(session, provider, [(invocation, intended["attempt"])], 1))
            if len(responses) != 1 or responses[0][0] != 0:
                raise ResearchError("event_extraction_dispatch_result_unavailable")
            response = responses[0][1]
        except AuditError:
            raise
        except Exception as failure:
            response = ProviderResponse(None, "codex-cli", None, raw_response={"unknown_outcome": True,
                "error_type": type(failure).__name__, "failure": "dispatch_outcome_unobserved", "observed_at": utc()})
        timings.append({"task_id": task["task_id"], "phase": task["phase"], "wall_seconds": time.perf_counter() - started})
        response_ref = None
        output = None
        validation: Json = {}
        unknown = bool(isinstance(response.raw_response, dict) and response.raw_response.get("unknown_outcome"))
        status, processing, error = "unknown" if unknown else "invalid", "unavailable", None
        retention_excluded = False
        try:
            # Retain exact observable bytes/structures before accepting parsed output.
            response_ref = save(engine, session, asdict(response), "Exact extraction response before validation")
        except AuditError:
            raise
        except ResearchError:
            retention_excluded = True
            status, error = "unknown" if unknown else "unavailable", "response_retention_excluded"
        if not retention_excluded:
            try:
                if unknown or response.payload is None:
                    raise ResearchError("event_extraction_transport_unknown" if unknown else "event_extraction_response_unavailable")
                validation = validate_output(response.payload, request_for(task))
                output = response.payload
                processing = "complete" if validation["coverage_complete"] and validation["extraction_status"] != "insufficient_evidence" else "incomplete"
                status = "valid" if processing == "complete" else "incomplete"
            except AuditError:
                raise
            except Exception:
                # Arbitrary provider/validator strings can contain source text or secrets.
                error = "event_extraction_transport_unknown" if unknown else "event_extraction_output_invalid"
        value = {"plan": plan_id, "task_id": task["task_id"], "source_version": task["source_version"],
            "phase": task["phase"], "request": task["request"], "response": response_ref, "attempt": intended["attempt"],
            "status": status, "processing": processing, "output": output, "validation": validation,
            "events": validation.get("events", []), "event_count": validation.get("event_count", 0),
            "error": error, "retention_excluded": retention_excluded,
            "observed_model": None if retention_excluded else response.model,
            "request_id": None if retention_excluded else response.request_id,
            "usage": None if retention_excluded else response.usage,
            "human_validated": False, "review_status": "provisional_event_mentions",
            "memberships_changed": False, "negative_finding": False if status != "valid" or processing != "complete" else None}
        assessment = ledger.record(session, "event_extraction_assessment", intended["attempt"], value)

        def project(event: int) -> None:
            ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                intended["attempt"], intended["task_key"], batch, 1, task["request"], response_ref,
                status, assessment, error, event))

        ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
            "attempt": intended["attempt"], "status": status, "response": response_ref,
            "assessment": assessment, "ended_at": utc()}, project)
        if not unknown:
            ledger.unresolved.pop(intended["attempt"], None)
        outcomes[task["task_id"]] = {**value, "assessment": assessment}
        if status != "valid" or processing != "complete":
            latch("First failed, unknown or incomplete extraction stops new dispatch; no retries",
                  attempt=intended["attempt"], assessment=assessment, error=error)
    counts = Counter(row["status"] for row in outcomes.values())
    incomplete = sum(row.get("processing") == "incomplete" for row in outcomes.values())
    valid = sum(row["status"] == "valid" and row.get("processing") == "complete" for row in outcomes.values())
    selected_pending = len(tasks) - len(outcomes)
    value = {"method": METHOD, "versions": plan["versions"], "plan": plan_id, "study_key": plan["study_key"],
        "status": "complete" if valid == len(tasks) and unfilled_slots == 0 else "partial", "outcomes": outcomes,
        "outcome_counts": dict(counts), "attempted": spent, "new_attempts": new_attempts, "cached": cached,
        "expected_slots": LIMITS["max_requests"], "selected_slots": len(tasks), "unfilled_slots": unfilled_slots,
        "selected_pending": selected_pending, "pending": selected_pending + unfilled_slots,
        "valid": valid, "mechanically_valid": counts["valid"] + counts["incomplete"],
        "invalid": counts["invalid"], "unknown": counts["unknown"], "unavailable": counts["unavailable"],
        "incomplete": incomplete, "workflow_model_attempts": spent, "workflow_article_exposures": spent,
        "automatic_retries": 0, "obstacle": obstacle, "batch_timings": timings, "canary_count": CANARIES,
        "provisional_event_mentions": sum(row.get("event_count", 0) for row in outcomes.values()),
        "event_count": sum(row.get("event_count", 0) for row in outcomes.values()),
        "complete_article_event_mentions": sum(row.get("event_count", 0) for row in outcomes.values() if row["status"] == "valid"),
        "incomplete_article_event_mentions": sum(row.get("event_count", 0) for row in outcomes.values() if row["status"] == "incomplete"),
        "human_validated": False, "embeddings_created": 0, "memberships_changed": False,
        "coverage_observation": "Complete means mechanically valid declared coverage, not verified event recall",
        "accepted_event_count": None}
    return present(engine, session, bound, "luna_group_validation_result", value, render_result(plan, value))
