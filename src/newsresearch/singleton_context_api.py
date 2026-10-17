"""Audited, user-requested expanded-context follow-up of frozen singleton cases."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .event_eval_workflow import present, save
from .gateway import BOUNDARY, Gateway
from .runtime import Research, audited_handler
from .singleton_context_contract import INSTRUCTION, build_request, make_context, validate_answer, validate_request
from .singleton_luna_api import ENDPOINT, MODEL, OUTPUT_CAP, _link, classify, parse_response
from .tag_gateway import OpenAITagTransport

STUDY = "singleton-luna-expanded-context-20261017-v1"
PARENT = "63ded06fabfb4878605e858cfba50e5c22f39daa3410550a6a32d3af7eb61e12"
USER_INSTRUCTION = "Use Luna via the OpenAI API to read more context for the 41 uncertain cases, retry the 3 incomplete cases, and show me the updated grouping results."
CATEGORIES = ("supported_match", "uncertain", "unmatched_among_top3", "incomplete")


def implementation() -> Json:
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in
            ("singleton_context_api.py", "singleton_context_contract.py", "singleton_luna_api.py", "tag_gateway.py", "gateway.py")}


def wire_body(request: Json) -> Json:
    validate_request(request)
    schema = deepcopy(request["schema"])
    schema["properties"]["support_span_ids"].pop("uniqueItems", None)
    packet = {k: request[k] for k in ("inclusion", "articles")}
    packet["evidence"] = [{k: s[k] for k in ("id", "source_id", "text")} for s in request["evidence"]]
    return {"model": MODEL, "store": False, "reasoning": {"effort": "low"}, "max_output_tokens": OUTPUT_CAP,
            "input": [{"role": "developer", "content": BOUNDARY}, {"role": "user", "content": canonical(packet)}],
            "text": {"format": {"type": "json_schema", "name": "event_pair_context_reference", "strict": True, "schema": schema}}}


def inspect_context(engine: Any, session: str, source_id: str) -> Json | None:
    source_sql = "SELECT payload FROM sources WHERE id=?"
    paragraph_sql = "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start,id"
    engine.ledger.append(session, "singleton.context.inspection.intended", {
        "source_version": source_id, "source_sql": source_sql, "paragraph_sql": paragraph_sql, "parameters": [source_id]})
    row = engine.ledger.db.execute(source_sql, (source_id,)).fetchone()
    if row is None:
        raise AuditError("context_retained_source_missing")
    source = json.loads(row[0])
    if source.get("retention") != "permitted" or not (source.get("body") or "").strip():
        engine.ledger.append(session, "singleton.context.unavailable", {"source_version": source_id})
        return None
    paragraphs = [dict(p) for p in engine.ledger.db.execute(paragraph_sql, (source_id,))]
    context = make_context(source_id, source.get("title"), source.get("published_at"), source["body"], paragraphs)
    engine.ledger.append(session, "singleton.context.inspected", {
        "source_version": source_id, "coverage": context["coverage"],
        "spans": [{k: s[k] for k in ("span_version", "start", "end", "text_hash", "parent_ref")} for s in context["passages"]]})
    return context if context["passages"] else None


def prepare(engine: Any, session: str, context: Context) -> Json:
    ledger = engine.ledger
    existing = ledger.db.execute("SELECT id FROM records WHERE kind='luna_group_validation_plan' AND logical_key=?", (STUDY,)).fetchone()
    if existing:
        plan_id = existing[0]
        plan = ledger.get(plan_id, "luna_group_validation_plan")
        if plan["implementation"] != implementation() or plan["parent_result"] != PARENT:
            raise ResearchError("context_frozen_code_or_parent_changed")
    else:
        method = {"method": STUDY, "parent_result": PARENT, "implementation": implementation(),
                  "selection": "Exactly the 41 uncertain and 3 incomplete anchors; retain their original top-three candidates, no new retrieval or sample",
                  "context": "All stored paragraphs up to 24,000 body characters; otherwise head18,000/tail6,000, max128 spans (first96/last32)",
                  "judging": INSTRUCTION, "aggregation": "All three valid; any same -> supported; else any uncertain -> uncertain; else unmatched-top3; missing -> incomplete",
                  "reuse": "Keep 56 other anchor results unchanged with exact parent lineage; preserve all earlier judgments",
                  "limits": {"cases": 44, "requests": 132, "article_exposures": 264, "automatic_retries": 0, "workers": 4},
                  "failure": "Quarantine individually unretainable responses as null; stop on unknown transport, HTTP, schema or citation failure; audit storage failure propagates",
                  "canary": "First four actual requests sequential, then at most four in parallel; no additional canary calls",
                  "transport": "User explicitly selects OpenAI API and expanded context, overriding the skill default for this study only",
                  "user_instruction": USER_INSTRUCTION, "membership_changes": False, "human_validated": False}
        protocol = engine._version(session, context, {"kind": "protocol", "key": STUDY, "content": method})["id"]
        parent = ledger.get(PARENT, "luna_group_validation_result")
        original = ledger.get(parent["plan"], "luna_group_validation_plan")
        selected = [r for r in parent["rows"] if r["category"] in {"uncertain", "incomplete"}]
        if (len(parent["rows"]) != 100 or parent["counts"] != dict(zip(CATEGORIES, (14, 41, 42, 3), strict=True))
                or len(selected) != 44 or any(len(r["candidates"]) != 3 for r in selected)):
            raise AuditError("context_parent_scope_changed")
        versions = {**parent["versions"], "protocol": protocol}
        amendments = {"selection": {"rules": method["selection"]}, "prompt": {"instructions": INSTRUCTION},
                      "profile": {"mode": "exploratory", "population_estimate": False, "adaptive_followup": True},
                      "model_profile": {"model": MODEL, "transport": ENDPOINT, "reasoning": "low", "max_output_tokens": OUTPUT_CAP,
                                        "price_per_million_input": "0.10", "price_per_million_output": "0.50", "price_checked_on": "2026-10-17"}}
        for kind, content in amendments.items():
            versions[kind] = engine._version(session, Context(context.objective, context.actor, versions),
                                             {"kind": kind, "key": STUDY, "content": content})["id"]
        pairs = {c["pair"] for r in selected for c in r["candidates"]}
        original_tasks = {t["pair"]: t for t in original["tasks"]}
        if len(pairs) != 132 or not pairs <= original_tasks.keys():
            raise AuditError("context_original_candidate_mapping_changed")
        sources = sorted({original_tasks[p][k] for p in pairs for k in ("left", "right")})
        contexts = {s: inspect_context(engine, session, s) for s in sources}
        tasks = []
        for pair in sorted(pairs):
            prior_task, prior = original_tasks[pair], parent["outcomes"][pair]
            left, right = prior_task["left"], prior_task["right"]
            task = {"pair": pair, "left": left, "right": right, "prior_assessment": prior["assessment"],
                    "prior_attempt": prior["attempt"], "retry_of": prior["attempt"] if prior["status"] != "valid" else None,
                    "status": "source_unavailable", "request": None, "body": None}
            left_context, right_context = contexts[left], contexts[right]
            if left_context and right_context:
                request = build_request(left_context, right_context, versions)
                task.update(status="prepared", request=save(engine, session, request, "Expanded exact source context and instruction"),
                            body=save(engine, session, wire_body(request), "Exact expanded-context API body without authentication"))
            tasks.append(task)
        if sum(t["retry_of"] is not None for t in tasks) != 3:
            raise AuditError("context_requires_three_explicit_retry_links")
        plan = {"method": STUDY, "study_key": STUDY, "implementation": implementation(), "versions": versions,
                "parent_result": PARENT, "parent_plan": parent["plan"], "selected_rows": selected,
                "preserved_rows": [r for r in parent["rows"] if r not in selected], "tasks": tasks,
                "source_metadata": original["source_metadata"], "context_coverage": {s: c["coverage"] if c else None for s, c in contexts.items()},
                "limits": method["limits"], "models_run": 0, "memberships_changed": False}
        plan_id = ledger.record(session, "luna_group_validation_plan", STUDY, plan)
    text = render_preparation(plan)
    presentation = engine._record_presentation(session, Context(context.objective, context.actor, plan["versions"]), {
        "results": [{"kind": "luna_group_validation_plan", "id": plan_id}], "markdown": text,
        "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": plan_id, **plan, "presentation": presentation}


def render_preparation(plan: Json) -> str:
    coverage = [c for c in plan["context_coverage"].values() if c]
    return (f"Expanded-context follow-up prepared for the same **41 uncertain + 3 incomplete singletons**: "
            f"**{sum(t['status'] == 'prepared' for t in plan['tasks'])}/132 comparisons ready**; "
            f"{sum(t['status'] != 'prepared' for t in plan['tasks'])} unavailable, 132 judgments pending; zero new model calls. "
            f"{len(coverage)} distinct retained articles; all stored paragraph text supplied for "
            f"{sum(c['all_stored_paragraph_text_supplied'] for c in coverage)}, context capped for "
            f"{sum(not c['all_stored_paragraph_text_supplied'] for c in coverage)}. "
            "Up to 24,000 body characters/article, compared with the earlier 3,000-character/three-paragraph limit. "
            "The other 56 results, the random sample and all candidate lists are preserved. "
            "Three retry links retained; maximum 132 new API calls/264 article exposures, zero automatic retries. "
            "No new retrieval, embeddings or grouping changes. This is preparation, not updated judgments.")


class ContextGateway(Gateway):
    def context_dispatch(self, session: str, plan_id: str, policy_id: str, calls: list[Json]) -> Any:
        require_active(self.engine, session)
        ledger = self.engine.ledger
        policy = ledger.get(policy_id, "policy")["content"]
        plan = ledger.get(plan_id, "luna_group_validation_plan")
        if (self.engine.config.offline or policy.get("plan") != plan_id or policy.get("method") != STUDY
                or not policy.get("allow_paid_inference") or not policy.get("allow_external_processing")
                or datetime.fromisoformat(policy["expires_at"]) <= datetime.now(timezone.utc)):
            raise ResearchError("context_gateway_bound_approval_required")
        tasks = {t["pair"]: t for t in plan["tasks"]}
        history = [json.loads(r[0]) for r in ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.context_study')=?", (STUDY,))]
        if (not 1 <= len(calls) <= 4 or len({c["attempt"] for c in calls}) != len(calls)
                or len(history) > 132 or len({i["pair"] for i in history}) != len(history)
                or sum(float(i["reserved_cost_usd"]) for i in history) > 2):
            raise AuditError("context_gateway_budget_violation")
        for call in calls:
            intent = ledger.unresolved.get(call["attempt"])
            task = tasks.get(call["pair"])
            if (not intent or not task or task["status"] != "prepared" or intent["batch"] != plan_id
                    or intent["approval_policy"] != policy_id or intent["request"] != task["request"]
                    or ledger.artifacts.read(intent["dispatch"]) != call["manifest"]
                    or ledger.artifacts.read(task["request"]) != call["request"]
                    or call["request"]["versions"] != plan["versions"]
                    or call["manifest"]["endpoint"] != ENDPOINT
                    or call["manifest"]["body"] != wire_body(call["request"])):
                raise AuditError("context_gateway_durable_intent_mismatch")
        transport = getattr(self.engine, "context_transport", None) or OpenAITagTransport()

        def send(call: Json) -> Json:
            try:
                response = transport.send(canonical(call["manifest"]["body"]).encode(), call["attempt"])
                return {"raw_bytes": response.body, "http_status": response.status,
                        "request_id": response.request_id, "ended_at": utc()}
            except Exception as failure:
                return {"unknown": True, "error_type": type(failure).__name__, "ended_at": utc()}

        with ThreadPoolExecutor(max_workers=len(calls)) as pool:
            futures = {pool.submit(send, call): call for call in calls}
            for future in as_completed(futures):
                yield futures[future], future.result()


def outcome(engine: Any, session: str, plan_id: str, task: Json, call: Json, response: Json) -> Json:
    ledger = engine.ledger
    status = "unknown" if response.get("unknown") else "invalid"
    answer, validation, parsed, response_ref, retention_excluded = None, {}, {}, None, False
    error = response.get("error_type")
    if "raw_bytes" in response:
        raw = response.pop("raw_bytes")
        ledger.record(session, "singleton_context_http_receipt", call["attempt"], {
            "attempt": call["attempt"], **response, "body_sha256": hashlib.sha256(raw).hexdigest(), "body_bytes": len(raw)})
        try:
            require_no_credentials(raw.decode("utf-8", errors="replace"))
        except ResearchError:
            retention_excluded = True
            error = "context_response_retention_exclusion"
        if not retention_excluded:
            raw_ref = ledger.artifacts.put_bytes(raw)
            ledger.append(session, "singleton.context.raw_response.saved", {"artifact": raw_ref, "attempt": call["attempt"]})
            response_ref = save(engine, session, {**response, "raw_response": raw_ref}, "Observable API response before acceptance")
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    parsed = {}
                    raise ResearchError("context_response_not_object")
                require_no_credentials(parsed)
                if response["http_status"] != 200:
                    raise ResearchError("context_http_error")
                answer = parse_response(parsed)
                validation = validate_answer(call["request"], answer)
                status = "valid"
            except AuditError:
                raise
            except Exception as failure:
                error = type(failure).__name__
                answer = None
    value = {"pair": task["pair"], "attempt": call["attempt"], "request": task["request"], "response": response_ref,
             "prior_assessment": task["prior_assessment"], "prior_attempt": task["prior_attempt"], "retry_of": task["retry_of"],
             "status": status, "label": answer["label"] if answer else None, "answer": answer, "validation": validation,
             "observed_model": parsed.get("model"), "response_id": parsed.get("id"), "request_id": response.get("request_id"),
             "usage": parsed.get("usage"), "http_status": response.get("http_status"), "error": error,
             "retention_excluded": retention_excluded, "started_at": call["manifest"]["started_at"],
             "ended_at": response["ended_at"], "human_validated": False}
    assessment = ledger.record(session, "singleton_context_assessment", call["attempt"], value)

    def project(event: int) -> None:
        ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (call["attempt"], call["task_key"], plan_id, 1,
                          task["request"], response_ref, status, assessment, error, event))

    ledger.append(session, "model.attempt.unobserved" if status == "unknown" else "model.attempt.completed", {
        "attempt": call["attempt"], "status": status, "response": response_ref, "assessment": assessment,
        "ended_at": response["ended_at"]}, project)
    if status != "unknown":
        ledger.unresolved.pop(call["attempt"], None)
    return {**value, "assessment": assessment}


def execute(engine: Any, session: str, context: Context, data: Json) -> Json:
    ledger = engine.ledger
    plan_id = data["plan"]
    plan = ledger.get(plan_id, "luna_group_validation_plan")
    if (plan["method"] != STUDY or plan["implementation"] != implementation() or plan["parent_result"] != PARENT
            or len(plan["tasks"]) != 132 or len(plan["selected_rows"]) != 44 or len(plan["preserved_rows"]) != 56):
        raise ResearchError("context_frozen_plan_changed")
    parent = ledger.get(PARENT, "luna_group_validation_result")
    bound = Context(context.objective, context.actor, plan["versions"])
    saved = ledger.db.execute("SELECT id FROM records WHERE kind='singleton_context_permission' AND logical_key=?", (STUDY,)).fetchone()
    if saved:
        permission = ledger.get(saved[0], "singleton_context_permission")
        if permission["plan"] != plan_id:
            raise AuditError("context_permission_plan_changed")
        policy_id = permission["policy"]
    else:
        if data.get("user_instruction") != USER_INSTRUCTION:
            raise ResearchError("context_explicit_user_request_required")
        policy_id = engine._version(session, bound, {"kind": "policy", "key": STUDY, "content": {
            "method": STUDY, "plan": plan_id, "parent_result": PARENT, "approved_by": "user:current-chat",
            "authorization_text": USER_INSTRUCTION, "observed_chat_timestamp": None,
            "allow_paid_inference": True, "allow_external_processing": True, "max_requests": 132,
            "max_article_exposures": 264, "max_planning_reservation_usd": 2, "automatic_retries": 0,
            "scope": "Rejudge all three original candidates for the 41 uncertain and 3 incomplete anchors; three explicit retry links; earlier300 attempts preserved separately",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()}})["id"]
        ledger.record(session, "singleton_context_permission", STUDY, {"plan": plan_id, "policy": policy_id})
    history = [json.loads(r[0]) for r in ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.context_study')=?", (STUDY,))]
    tasks = {t["pair"]: t for t in plan["tasks"]}
    if len(history) > 132 or len({h["pair"] for h in history}) != len(history):
        raise AuditError("context_retry_or_limit_violation")
    outcomes: Json = {}
    stopped = bool(ledger.db.execute("SELECT 1 FROM records WHERE kind='singleton_context_stop' AND logical_key=?", (STUDY,)).fetchone())
    for intent in history:
        task = tasks.get(intent["pair"])
        if (not task or intent["request"] != task["request"] or intent["approval_policy"] != policy_id
                or intent["batch"] != plan_id or intent["retry_of"] != task["retry_of"]):
            raise AuditError("context_attempt_binding_changed")
        previous = ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?", (intent["attempt"],)).fetchone()
        if previous is None or previous["result_id"] is None:
            outcomes[task["pair"]] = {"status": "unknown", "label": None, "attempt": intent["attempt"]}
            stopped = True
            continue
        cached = ledger.get(previous["result_id"], "singleton_context_assessment")
        if cached["status"] != previous["status"] or cached["request"] != task["request"] or cached["attempt"] != intent["attempt"]:
            raise AuditError("context_cached_result_changed")
        if cached["status"] == "valid":
            validate_answer(ledger.artifacts.read(task["request"]), cached["answer"])
        elif not cached["retention_excluded"] or cached["http_status"] != 200:
            stopped = True
        outcomes[task["pair"]] = {**cached, "assessment": previous["result_id"]}
        ledger.append(session, "model.cache_reused", {"assessment": previous["result_id"], "request": task["request"],
                                                    "basis": "Exact frozen expanded-context plan; no repeated call"})
    ledger.record(session, "singleton_context_batch", str(uuid.uuid4()), {"plan": plan_id, "policy": policy_id,
                                                                       "tasks": plan["tasks"], "previous_attempts": len(history)})
    spent, reservation = len(history), sum(float(h["reserved_cost_usd"]) for h in history)
    remaining = [t for t in plan["tasks"] if t["pair"] not in outcomes]
    cursor = 0
    while cursor < len(remaining) and not stopped:
        width = 1 if spent < 4 else 4
        block = remaining[cursor:cursor + width]
        cursor += len(block)
        blocked = {s for h in ledger.unresolved.values() for s in h.get("source_versions", [])}
        calls = []
        for task in block:
            if task["status"] != "prepared" or blocked & {task["left"], task["right"]}:
                outcomes[task["pair"]] = {"status": "unavailable", "label": None}
                continue
            request, body = ledger.artifacts.read(task["request"]), ledger.artifacts.read(task["body"])
            if body != wire_body(request) or request["versions"] != plan["versions"]:
                raise AuditError("context_frozen_wire_changed")
            reserve = ((len(canonical(body).encode()) + 4096) * .10 + OUTPUT_CAP * .50) / 1000000
            if spent >= 132 or reservation + reserve > 2:
                stopped = True
                ledger.record(session, "singleton_context_stop", STUDY, {"plan": plan_id, "reason": "Planning reservation limit"})
                break
            attempt = str(uuid.uuid4())
            manifest = {"transport": "openai-responses-expanded-context-v1", "endpoint": ENDPOINT, "body": body,
                        "client_request_id": attempt, "started_at": utc(), "automatic_retries": 0}
            dispatch = save(engine, session, manifest, "Exact expanded-context dispatch without authentication")
            task_key = digest({"plan": plan_id, "policy": policy_id, "pair": task["pair"]})
            intent = {"attempt": attempt, "task_key": task_key, "number": 1, "batch": plan_id, "request": task["request"],
                      "dispatch": dispatch, "started_at": manifest["started_at"], "context_study": STUDY,
                      "pair": task["pair"], "approval_policy": policy_id, "retry_of": task["retry_of"],
                      "source_versions": [task["left"], task["right"]], "article_exposures": 2, "reserved_cost_usd": reserve}
            ledger.append(session, "model.attempt.intended", intent)
            ledger.unresolved[attempt] = intent
            calls.append({"attempt": attempt, "task_key": task_key, "manifest": manifest, "request": request, "pair": task["pair"]})
            spent += 1
            reservation += reserve
        if not calls:
            continue
        for call, response in engine.gateway.context_dispatch(session, plan_id, policy_id, calls):
            value = outcome(engine, session, plan_id, tasks[call["pair"]], call, response)
            outcomes[call["pair"]] = value
            if value["status"] != "valid" and not (value["retention_excluded"] and value["http_status"] == 200):
                stopped = True
                ledger.record(session, "singleton_context_stop", STUDY, {"plan": plan_id, "assessment": value["assessment"]})
        print(f"Expanded-context Luna: {len(outcomes)}/132 outcomes; {spent} attempts; stop={stopped}", flush=True)
    combined = {**parent["outcomes"], **outcomes}
    # Missing expanded judgments must not silently fall back to the old evidence.
    for pair in tasks:
        if pair not in outcomes:
            combined[pair] = {"status": "pending", "label": None}
    selected_ids = {r["source"] for r in plan["selected_rows"]}
    rows = [{**r, "category": classify([combined[c["pair"]]["label"] for c in r["candidates"]])}
            if r["source"] in selected_ids else r for r in parent["rows"]]
    if [r for r in rows if r["source"] not in selected_ids] != plan["preserved_rows"]:
        raise AuditError("context_unselected_rows_changed")
    counts = {k: sum(r["category"] == k for r in rows) for k in CATEGORIES}
    transitions: Json = {before: {after: 0 for after in CATEGORIES} for before in ("uncertain", "incomplete")}
    old = {r["source"]: r["category"] for r in parent["rows"]}
    for row in rows:
        if row["source"] in selected_ids:
            transitions[old[row["source"]]][row["category"]] += 1
    usages = [v["usage"] for v in outcomes.values() if isinstance(v.get("usage"), dict)]
    usage = {k: sum(u.get(k, 0) for u in usages) for k in ("input_tokens", "output_tokens", "total_tokens")}
    result = {"method": STUDY, "versions": plan["versions"], "plan": plan_id, "parent_result": PARENT,
              "rows": rows, "outcomes": combined, "new_outcomes": outcomes, "counts": counts, "before": parent["counts"],
              "transitions": transitions, "model_attempts": spent, "article_exposures": spent * 2,
              "pending_pairs": 132 - len(outcomes), "new_pair_statuses": dict(Counter(v["status"] for v in outcomes.values())),
              "new_pair_labels": dict(Counter(v["label"] for v in outcomes.values() if v["status"] == "valid")),
              "explicit_retry_attempts": sum(tasks[p]["retry_of"] is not None for p in outcomes if outcomes[p].get("attempt")),
              "automatic_retries": 0, "usage": usage, "responses_with_usage": len(usages),
              "standard_uncached_usage_cost_usd": (usage["input_tokens"] * .10 + usage["output_tokens"] * .50) / 1000000,
              "planning_reservation_usd": reservation, "stopped": stopped, "memberships_changed": False, "human_validated": False,
              "requested_model": MODEL, "observed_models": sorted({v["observed_model"] for v in outcomes.values() if v.get("observed_model")})}
    return present(engine, session, bound, "luna_group_validation_result", result, render_results(result, plan))


def render_results(result: Json, plan: Json) -> str:
    names = dict(zip(CATEGORIES, ("Supported same-event match (proposal)", "Uncertain", "Unmatched among original top three", "Incomplete"), strict=True))
    text = "Luna expanded-context follow-up: same original 100 singleton articles.\n\n| Outcome | Before | Updated |\n|---|---:|---:|\n"
    for category in CATEGORIES:
        text += f"| {names[category]} | {result['before'][category]} | {result['counts'][category]} |\n"
    text += f"\nChanges among the 44 rechecked cases: {result['transitions']}. The other 56 results are unchanged.\n\n"
    text += (f"New work: {result['model_attempts']}/132 API attempts, {result['article_exposures']} article exposures, "
             f"{result['explicit_retry_attempts']}/3 explicitly requested retry attempts, zero automatic retries. "
             f"Pair statuses: {result['new_pair_statuses']}; labels: {result['new_pair_labels']}; "
             f"pending {result['pending_pairs']}; stopped {result['stopped']}. "
             f"Requested model {MODEL}; observed {result['observed_models']}. "
             f"Observed usage on {result['responses_with_usage']} responses: {result['usage']}; "
             f"USD {result['standard_uncached_usage_cost_usd']:.6f} at uncached Standard rates, not an invoice. "
             f"Usage/billing for {result['model_attempts']-result['responses_with_usage']} responses is unavailable, not zero.\n\n"
             "These are provisional model pair references, not human-validated accuracy or adopted dossiers. "
             "Unmatched is limited to the three tested candidates, not proof of uniqueness or corpus recall. "
             "Publication time is not event time; links beyond seven publication days require the separate review tier. "
             "No memberships, embeddings or candidate lists changed. Source/attempt history and exact context remain in protected storage.\n\n"
             "Examples from the expanded-context judgments:\n")
    selected = {r["source"] for r in plan["selected_rows"]}
    for category, desired in zip(CATEGORIES[:3], ("same_event", "uncertain", "different_event"), strict=True):
        row = next((r for r in result["rows"] if r["source"] in selected and r["category"] == category), None)
        if row is None:
            text += f"\n- {names[category]}: none among rechecked cases.\n"
            continue
        candidate = next(c for c in row["candidates"] if result["outcomes"][c["pair"]]["label"] == desired)
        answer = result["outcomes"][candidate["pair"]]["answer"]
        text += (f"\n- {names[category]}: {_link(plan['source_metadata'], row['source'])} ↔ "
                 f"{_link(plan['source_metadata'], candidate['source'])}; saved cosine {candidate['score']:.4f}; "
                 f"Luna: {answer['reason']} Citations: {', '.join(answer['support_span_ids']) or 'none'}.\n")
    return text


class SingletonContextResearch(Research):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gateway = ContextGateway(self, self.gateway.provider)

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data == {"phase": "singleton_context_prepare"}:
            return prepare(self, session, context)
        if data.get("phase") == "singleton_context_execute" and set(data) == {"phase", "plan", "user_instruction"}:
            return execute(self, session, context, data)
        raise ResearchError("context_exact_phase_required")
