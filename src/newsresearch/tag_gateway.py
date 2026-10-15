"""Plan-authorized Responses transport, invoked exclusively by the shared research gateway."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
import os
from typing import TYPE_CHECKING
import urllib.error
import urllib.request
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc
from .embeddings import EmbeddingHTTPResponse, NoRedirect
from .tagging import implementation, same_versions, validate

if TYPE_CHECKING:
    from .runtime import Research


class OpenAITagTransport:
    def send(self, body: bytes, client_request_id: str) -> EmbeddingHTTPResponse:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ResearchError("OPENAI_API_KEY is unavailable")
        request = urllib.request.Request(
            "https://api.openai.com/v1/responses", data=body, method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                     "X-Client-Request-Id": client_request_id})
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
                return EmbeddingHTTPResponse(response.read(), response.status, response.headers.get("x-request-id"))
        except urllib.error.HTTPError as error:
            return EmbeddingHTTPResponse(error.read(), error.code, error.headers.get("x-request-id"))


def parse_response(request: Json, parsed: Json) -> Json:
    if (parsed.get("status") != "completed" or parsed.get("model") != request["profile"]["model"]
            or parsed.get("error") or parsed.get("incomplete_details")):
        raise ResearchError("Response incomplete, failed or from an unexpected model")
    content = [part for item in parsed.get("output", []) if item.get("type") == "message"
               for part in item.get("content", [])]
    if len(content) != 1 or content[0].get("type") != "output_text":
        raise ResearchError("Response refused or lacks a single structured output")
    return json.loads(content[0]["text"])


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    if engine.config.offline:
        raise ResearchError("Paid tagging is blocked by the default offline configuration")
    planned = ledger.get(data["plan"], "tag_plan")
    same_versions(planned, context)
    if planned["implementation_digest"] != implementation(engine):
        raise ResearchError("Tag implementation changed; create and approve a new plan")
    policy_id = data.get("approval_policy")
    if not policy_id:
        raise ResearchError("A concrete registered paid-run approval is required")
    policy = ledger.get(policy_id, "policy")["content"]
    if (policy.get("method") != "tag-run-approval-v1" or policy.get("plan") != data["plan"]
            or not policy.get("approved_by") or policy.get("allow_external_processing") is not True
            or policy.get("allow_paid_inference") is not True):
        raise ResearchError("Paid-run approval must bind this exact tag plan and external processing")
    expiry = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
    budget = Decimal(str(policy["max_estimated_cost_usd"]))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc) or not budget.is_finite() or budget <= 0:
        raise ResearchError("Approval needs a future timezone-aware expiry and positive finite budget")
    limit = data.get("max_requests", 1)
    if type(limit) is not int or not 0 <= limit <= len(planned["items"]):
        raise ResearchError("Invalid request limit")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ResearchError("OPENAI_API_KEY unavailable; no request sent")
    reserved = sum((Decimal(json.loads(row[0])["reserved_cost_usd"]) for row in ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.approval_policy')=?",
        (policy_id,))), Decimal(0))
    results, sent, stopped = [], 0, False
    for item in planned["items"]:
        request = ledger.artifacts.read(item["request_ref"])
        if any(v["task_key"] == item["task_key"] for v in ledger.unresolved.values()):
            raise ResearchError("Unknown outcome: explicitly resolve the attempt before retrying")
        cached = ledger.db.execute(
            "SELECT result_id,id FROM attempts WHERE task_key=? AND status='valid' ORDER BY number DESC LIMIT 1",
            (item["task_key"],)).fetchone()
        if cached:
            if data.get("reuse_cache") is not True:
                raise ResearchError("Successful task exists; explicit reuse_cache is required")
            previous = ledger.get(cached["result_id"], "tag_assessment")
            validate(engine, request, previous["result"])
            ledger.append(session, "model.cache_reused", {"task_key": item["task_key"], "attempt": cached["id"],
                          "result": cached["result_id"], "batch": data["plan"]})
            results.append({**item, "status": "cached", "result": cached["result_id"]})
            continue
        estimate = Decimal(item["reserved_cost_usd"])
        if stopped or sent >= limit or reserved + estimate > budget or expiry <= datetime.now(timezone.utc):
            results.append({**item, "status": "not_processed", "result": None})
            continue
        prior = ledger.db.execute(
            "SELECT max(CAST(json_extract(payload,'$.number') AS INTEGER)) FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.task_key')=?",
            (item["task_key"],)).fetchone()[0]
        number, attempt, started = (prior or 0) + 1, str(uuid.uuid4()), utc()
        intent = {"attempt": attempt, "task_key": item["task_key"], "number": number,
                  "batch": data["plan"], "request": item["request_ref"], "started_at": started,
                  "client_request_id": attempt, "approval_policy": policy_id, "reserved_cost_usd": str(estimate)}
        ledger.append(session, "model.attempt.intended", intent)
        reserved += estimate
        sent += 1
        try:
            response = OpenAITagTransport().send(canonical(request["body"]).encode(), attempt)
        except Exception as error:
            ledger.append(session, "model.attempt.unobserved", {
                "attempt": attempt, "error_type": type(error).__name__, "observed_at": utc()})
            ledger.unresolved[attempt] = intent
            raise ResearchError("Tag response unavailable; outcome unknown and automatic retry blocked") from None
        response_ref = result_id = raw_ref = None
        error_type = None
        status, validation = "invalid", {}
        try:
            require_no_credentials(response.body.decode("utf-8", errors="replace"))
            raw_ref = ledger.artifacts.put_bytes(response.body)
            ledger.append(session, "tagging.artifact.saved", {"artifact": raw_ref})
            # Preserve observable HTTP metadata even if JSON is malformed.
            response_ref = ledger.artifacts.put({"raw_response_ref": raw_ref, "request_id": response.request_id,
                "http_status": response.status, "started_at": started, "ended_at": utc()})
            ledger.append(session, "tagging.artifact.saved", {"artifact": response_ref})
            parsed = json.loads(response.body)
            require_no_credentials(parsed)
            if response.status != 200:
                raise ResearchError("Tag HTTP error")
            result = parse_response(request, parsed)
            validation = validate(engine, request, result)
            result_id = ledger.record(session, "tag_assessment", attempt, {
                "attempt": attempt, "task_key": item["task_key"], "plan": data["plan"],
                "request_ref": item["request_ref"], "raw_response_ref": raw_ref, "response_ref": response_ref,
                "provider": "openai", "model": parsed.get("model"), "request_id": response.request_id,
                "response_id": parsed.get("id"), "usage": parsed.get("usage"),
                "result": result, "validation": validation, "versions": context.versions,
                "status": "provisional; not an accepted research finding"})
            status = "valid"
        except AuditError:
            raise
        except Exception as error:
            error_type = type(error).__name__
            validation = {"status": "invalid", "error_type": error_type, "response_not_retained": raw_ref is None}
            stopped = True

        def project(event: int) -> None:
            ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                attempt, item["task_key"], data["plan"], number, item["request_ref"], response_ref,
                status, result_id, error_type, event))

        ledger.append(session, "model.attempt.completed", {
            "attempt": attempt, "status": status, "response": response_ref, "assessment": result_id,
            "validation": validation, "http_status": response.status, "request_id": response.request_id,
            "ended_at": utc()}, project)
        results.append({**item, "status": status, "result": result_id})
    output = {"plan": data["plan"], "approval_policy": policy_id, "items": results,
              "source_ids": planned["source_ids"], "expected_sources": planned["expected_sources"],
              "unprocessed_sources": planned["unprocessed_sources"], "requests_sent": sent,
              "reserved_cost_usd": str(reserved), "versions": context.versions,
              "missing_task_keys": [i["task_key"] for i in results if i["status"] not in {"valid", "cached"}]}
    identifier = ledger.record(session, "tag_run", str(uuid.uuid4()), output)
    return {"id": identifier, **output}
