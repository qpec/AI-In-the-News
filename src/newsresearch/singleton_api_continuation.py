"""Finish only untouched requests of the already authorized singleton sample.

Original failed attempts, stop record and raw-response retention guard remain.
No retry, redraw, changed prompt, new candidate or expanded study budget.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Any
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, digest, utc
from .event_eval_workflow import present, save
from .event_pair_reference import validate_answer, validate_request
from .runtime import audited_handler
from .singleton_luna_api import (METHOD, MODEL, OUTPUT_CAP, STUDY, USER_INSTRUCTION, SingletonResearch,
    _outcome, classify, implementation, render_results, wire_body)

PARENT_RESULT = "b35ecce5f1bd3d59b1a083af54dbeafa7b388ae460edaffda8ff4509a8f218a5"
CONTINUATION = METHOD + ":untouched-continuation-v1"


def continuation_code() -> Json:
    return {**implementation(), Path(__file__).name: __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest()}


def execute_remaining(engine: Any, session: str, context: Context) -> Json:
    ledger = engine.ledger
    method = {"method": CONTINUATION, "parent_result": PARENT_RESULT,
              "reason": "Isolated HTTP 200 response could not pass the retention guard; the 59 valid responses establish a working contract, not semantic accuracy",
              "scope": "Only the exact 240 previously unattempted pairs in the original 100-source frozen sample; no retry or sample replacement",
              "counter": "All attempts across original and continuation policies share the original maximum 300 requests / 600 exposures / USD2 planning reservations",
              "retention_failure": "Reject and retain null classification; never log flagged material. Individual response-retention exclusions do not invalidate unrelated prepared requests",
              "stop": "Original stop remains immutable. Stop this continuation on HTTP, unknown transport or schema/citation failure; reject isolated output-retention failures without semantic acceptance",
              "model_and_prompt": "Original exact OpenAI Luna request bodies and versions, unchanged",
              "authority": "Existing explicit user request for these same 100 singletons, not a new run or expanded budget",
              "implementation": continuation_code()}
    protocol = engine._version(session, context, {"kind": "protocol", "key": CONTINUATION, "content": method})["id"]
    parent = ledger.get(PARENT_RESULT, "luna_group_validation_result")
    plan_id = parent["plan"]
    plan = ledger.get(plan_id, "luna_group_validation_plan")
    if plan["implementation"] != implementation() or parent["method"] != METHOD or parent["model_attempts"] != 60:
        raise ResearchError("singleton_continuation_parent_or_code_changed")
    failures = [row for row in parent["outcomes"].values() if row["status"] != "valid"]
    if len(failures) != 1 or failures[0]["http_status"] != 200 or failures[0]["response"] is not None or failures[0]["status"] != "invalid":
        raise ResearchError("singleton_continuation_requires_exact_isolated_retention_failure")
    bound = Context(context.objective, context.actor, plan["versions"])
    selected = [task for task in plan["tasks"] if task["pair"] not in parent["outcomes"]]
    if len(selected) != 240:
        raise AuditError("singleton_continuation_untouched_scope_changed")
    manifest_value = {"method": CONTINUATION, "protocol": protocol, "parent_result": PARENT_RESULT, "plan": plan_id,
                      "tasks": selected, "original_outcomes": parent["outcomes"], "implementation": continuation_code()}
    manifest = ledger.record(session, "singleton_api_continuation_manifest", CONTINUATION, manifest_value)
    existing = ledger.db.execute("SELECT id FROM records WHERE kind='singleton_api_continuation_policy' AND logical_key=?", (CONTINUATION,)).fetchone()
    if existing:
        saved_policy = ledger.get(existing[0], "singleton_api_continuation_policy")
        if saved_policy["manifest"] != manifest:
            raise ResearchError("singleton_continuation_frozen_manifest_changed")
        policy_id = saved_policy["policy"]
        if ledger.get(policy_id, "policy")["content"]["execution_protocol"] != protocol:
            raise ResearchError("singleton_continuation_execution_protocol_changed")
    else:
        policy_id = engine._version(session, bound, {"kind": "policy", "key": CONTINUATION, "content": {
            "method": METHOD + ":approval", "plan": plan_id, "execution_protocol": protocol, "manifest": manifest,
            "approved_by": "user:current-chat-original-100-singleton-request", "authorization_text": USER_INSTRUCTION,
            "allow_paid_inference": True, "allow_external_processing": True, "shared_max_requests": 300,
            "additional_max_requests": 240, "retries": 0, "parent_result": PARENT_RESULT,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
            "scope_basis": "Untouched tasks only within the user's original explicit 100-singleton scope; no reset of original stop or spent counters"}})["id"]
        ledger.record(session, "singleton_api_continuation_policy", CONTINUATION, {"policy": policy_id, "manifest": manifest})
    tasks = {task["pair"]: task for task in plan["tasks"]}
    history = [json.loads(row[0]) for row in ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.singleton_study')=?", (STUDY,))]
    if len(history) > 300 or len({item["pair"] for item in history}) != len(history):
        raise AuditError("singleton_continuation_shared_budget_or_retry_violation")
    outcomes = dict(parent["outcomes"])
    stopped = bool(ledger.db.execute("SELECT 1 FROM records WHERE kind='singleton_api_continuation_stop' AND logical_key=?", (CONTINUATION,)).fetchone())
    for item in history:
        if item["pair"] in parent["outcomes"]:
            if item["attempt"] != parent["outcomes"][item["pair"]]["attempt"]:
                raise AuditError("singleton_continuation_original_attempt_changed")
            continue
        task = tasks[item["pair"]]
        if item["approval_policy"] != policy_id or item["request"] != task["request"] or item["batch"] != plan_id:
            raise AuditError("singleton_continuation_attempt_binding_changed")
        row = ledger.db.execute("SELECT result_id,status FROM attempts WHERE id=?", (item["attempt"],)).fetchone()
        if row is None or row["result_id"] is None:
            outcomes[item["pair"]] = {"status": "unknown", "label": None, "attempt": item["attempt"]}
            stopped = True
        else:
            outcome = ledger.get(row["result_id"], "singleton_api_assessment")
            if outcome["status"] != row["status"] or outcome["request"] != task["request"]:
                raise AuditError("singleton_continuation_cached_assessment_changed")
            if outcome["status"] == "valid":
                validate_answer(ledger.artifacts.read(task["request"]), outcome["answer"])
            outcomes[item["pair"]] = {**outcome, "assessment": row["result_id"]}
            ledger.append(session, "model.cache_reused", {"assessment": row["result_id"], "basis": "Exact original body and continuation attempt; no repeat"})
    reservation = sum(float(item["reserved_cost_usd"]) for item in history)
    spent = len(history)
    remaining = [task for task in selected if task["pair"] not in outcomes]
    start = time.perf_counter()
    for offset in range(0, len(remaining), 4):
        if stopped:
            break
        blocked = {source for row in ledger.unresolved.values() for source in row.get("source_versions", [])}
        calls = []
        for task in remaining[offset:offset + 4]:
            if task["status"] != "prepared" or blocked & {task["left"], task["right"]}:
                outcomes[task["pair"]] = {"status": "unavailable", "label": None}
                continue
            request = ledger.artifacts.read(task["request"])
            validate_request(request)
            body = ledger.artifacts.read(task["body"])
            if body != wire_body(request) or request["versions"] != plan["versions"]:
                raise AuditError("singleton_continuation_wire_changed")
            reserve = ((len(canonical(body).encode()) + 4096) * .10 + OUTPUT_CAP * .50) / 1000000
            if spent >= 300 or reservation + reserve > 2:
                raise ResearchError("singleton_continuation_shared_limit_reached")
            attempt = str(uuid.uuid4())
            dispatch_body = {"transport": "openai-responses-event-pair-v1", "endpoint": "https://api.openai.com/v1/responses", "body": body,
                             "client_request_id": attempt, "started_at": utc(), "retries": 0}
            dispatch = save(engine, session, dispatch_body, "Exact untouched API dispatch, no authentication headers")
            task_key = digest({"plan": plan_id, "policy": policy_id, "pair": task["pair"]})
            intent = {"attempt": attempt, "task_key": task_key, "number": 1, "batch": plan_id, "request": task["request"], "dispatch": dispatch,
                      "started_at": dispatch_body["started_at"], "singleton_study": STUDY, "pair": task["pair"], "approval_policy": policy_id,
                      "continuation": manifest, "source_versions": [task["left"], task["right"]], "article_exposures": 2, "reserved_cost_usd": reserve}
            ledger.append(session, "model.attempt.intended", intent)
            ledger.unresolved[attempt] = intent
            calls.append({"attempt": attempt, "task_key": task_key, "manifest": dispatch_body, "request": request, "pair": task["pair"]})
            spent += 1
            reservation += reserve
        if not calls:
            continue
        for call, response in engine.gateway.singleton_api_dispatch(session, plan_id, policy_id, calls):
            # Retain non-content receipt metadata even when raw content cannot
            # pass the unchanged credential guard. Never retain matched values.
            if "raw_bytes" in response:
                ledger.record(session, "singleton_api_http_receipt", call["attempt"], {
                    "attempt": call["attempt"], "http_status": response["http_status"], "request_id": response.get("request_id"),
                    "body_sha256": __import__("hashlib").sha256(response["raw_bytes"]).hexdigest(), "body_bytes": len(response["raw_bytes"]),
                    "observed_at": response["ended_at"]})
            outcome = _outcome(engine, session, plan_id, tasks[call["pair"]], call, response)
            outcomes[call["pair"]] = outcome
            retention_excluded = outcome["status"] == "invalid" and outcome["http_status"] == 200 and outcome["response"] is None and outcome["error"] == "ResearchError"
            if retention_excluded:
                ledger.record(session, "singleton_api_retention_exclusion", call["attempt"], {
                    "assessment": outcome["assessment"], "scope": "Only this response; no classification, raw flagged content, retry or negative finding",
                    "usage_unavailable": True, "billing_usd": None, "billing_status": "Unavailable, never assumed zero"})
            elif outcome["status"] != "valid":
                stopped = True
                ledger.record(session, "singleton_api_continuation_stop", CONTINUATION, {"attempt": call["attempt"], "assessment": outcome["assessment"]})
        print(f"Luna API continuation: {len(outcomes)}/300 pair outcomes retained; total attempts {spent}/300; stop={stopped}", flush=True)
    rows = [{**row, "category": classify([outcomes.get(candidate["pair"], {}).get("label") for candidate in row["candidates"]])} for row in plan["rows"]]
    counts = {category: sum(row["category"] == category for row in rows) for category in ("supported_match", "uncertain", "unmatched_among_top3", "incomplete")}
    usages = [row["usage"] for row in outcomes.values() if isinstance(row.get("usage"), dict)]
    tokens = {key: sum(row.get(key, 0) for row in usages) for key in ("input_tokens", "output_tokens", "total_tokens")}
    gap_counts: Counter[str] = Counter()
    for row in rows:
        if row["category"] != "supported_match":
            continue
        gaps = []
        for candidate in row["candidates"]:
            if outcomes[candidate["pair"]]["label"] != "same_event":
                continue
            try:
                left, right = [datetime.fromisoformat(plan["source_metadata"][source]["published_at"].replace("Z", "+00:00")) for source in (row["source"], candidate["source"])]
                gaps.append(abs((left - right).total_seconds()) / 86400 if left.tzinfo and right.tzinfo else None)
            except (TypeError, ValueError, AttributeError, KeyError):
                gaps.append(None)
        gap_counts["within_seven_days" if any(gap is not None and gap <= 7 for gap in gaps) else
                   "beyond_seven_days_only_dated_support" if any(gap is not None and gap > 7 for gap in gaps) else "publication_gap_unavailable"] += 1
    result = {"method": CONTINUATION, "versions": plan["versions"], "execution_protocol": protocol, "parent_result": PARENT_RESULT,
              "plan": plan_id, "study_key": STUDY, "rows": rows, "outcomes": outcomes, "counts": counts,
              "pair_statuses": dict(Counter(row["status"] for row in outcomes.values())),
              "pair_labels": dict(Counter(row["label"] for row in outcomes.values() if row["status"] == "valid")),
              "model_attempts": spent, "article_exposures": 2 * spent, "pending_pairs": len(plan["tasks"]) - len(outcomes),
              "usage": tokens, "responses_with_usage": len(usages), "standard_uncached_usage_cost_usd": (tokens["input_tokens"] * .10 + tokens["output_tokens"] * .50) / 1000000,
              "planning_reservation_usd": reservation, "automatic_retries": 0, "memberships_changed": False, "human_validated": False,
              "stopped": stopped, "publication_gap_support": dict(gap_counts), "continuation_seconds": time.perf_counter() - start,
              "requested_model": MODEL, "observed_models": sorted({row["observed_model"] for row in outcomes.values() if row.get("observed_model")}),
              "original_stop_preserved": True, "full_sample_replaced": False}
    text = render_results(result, plan)
    text += (f"\n\nSupported-match publication-gap breakdown: {dict(gap_counts)}. Publication gaps are not event dates. "
             f"Requested model {MODEL}; observed models {result['observed_models']}. Original stop and failed attempt preserved; no repeats or new sample. "
             f"Usage/billing remains unavailable for {spent - len(usages)} attempted responses; this is not zero cost for those attempts.")
    return present(engine, session, bound, "luna_group_validation_result", result, text)


class SingletonContinuationResearch(SingletonResearch):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data != {"phase": "singleton_api_continue_untouched"}:
            raise ResearchError("singleton_continuation_exact_phase_required")
        return execute_remaining(self, session, context)
