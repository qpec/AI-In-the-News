"""Composed, audited query embedding, exhaustive retrieval and Codex RAG answers."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING
import uuid

from .codex_provider import CodexCLIProvider
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .rag_answers import TASK_INSTRUCTION, TASK_KIND, answer_schema, build_request, render_answers, validate_answer

if TYPE_CHECKING:
    from .runtime import Research

METHOD: Json = {
    "method": "organizational-decisions-codex-rag-v1",
    "retrieval": "One new query/question embedding; exhaustive maximum passage cosine per article; descending score then source version",
    "answers": "Fresh Codex context with complete permitted stored article and exact source quotations; no score or rank supplied",
    "interpretation": "Provisional source-grounded model answers, not accepted findings or confirmed incident counts",
    "failure_policy": "Continue independent items; retry known-invalid answers once within 120 total attempts; unknown outcomes remain unresolved and never automatically retry",
    "threshold": "Ranked top candidates only; no binary cutoff or new relevance tags",
    "billing": "One OpenAI query embedding under concrete plan-bound permission; Codex existing ChatGPT account, no API-key fallback",
    "limits": "At most 100 ranked articles, 120 article attempts and one embedding dispatch across the authorization key",
}


def provider_factory(engine: Research, data: Json) -> CodexCLIProvider:
    return CodexCLIProvider(engine.ledger.root / "codex-workers", executable=data.get("codex_executable", "codex"),
        model=data["codex_model"], timeout_seconds=180, max_input_bytes=250_000, max_output_bytes=2_000_000)


def _register(engine: Research, session: str, context: Context, kind: str, key: str, content: Json) -> str:
    return str(engine._version(session, context, {"kind": kind, "key": key, "content": content,
        "amend_latest": True, "reason": "Register the user-authorized source-grounded corpus question before execution"})["id"])


def _expiry(value: Json) -> datetime:
    try:
        result = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ResearchError("RAG run requires a concrete timezone-aware approval expiry") from None
    if result.tzinfo is None or result <= datetime.now(timezone.utc):
        raise ResearchError("RAG run approval expired or lacks a timezone")
    return result


def _approval(data: Json) -> Json:
    value = data.get("run_approval", {})
    _expiry(value)
    try:
        budget = Decimal(str(value["max_embedding_usd"]))
    except (KeyError, InvalidOperation):
        raise ResearchError("RAG run requires an explicit query embedding budget") from None
    if (not value.get("approved_by") or not value.get("instruction")
            or value.get("allow_external_processing") is not True or value.get("allow_codex_account") is not True
            or value.get("allow_paid_inference") is not True
            or type(value.get("max_article_attempts")) is not int or value["max_article_attempts"] != 120
            or type(value.get("max_embedding_requests")) is not int or value["max_embedding_requests"] != 1
            or not budget.is_finite() or not 0 < budget <= Decimal("0.01")):
        raise ResearchError("RAG approval must bind external processing, Codex account, 120 attempts and one <=0.01 USD embedding")
    return {**value, "method": "organizational-decisions-rag-run-approval-v1", "authorization_key": data["key"],
        "provider_billing": None, "provider_billing_unavailable_reason": "Codex account billing unobserved",
        "hard_provider_token_cost_cap": None}


def _binary_hash(executable: str) -> str | None:
    path = Path(executable)
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _budget(engine: Research, key: str) -> tuple[int, set[str]]:
    rows = engine.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' "
        "AND json_extract(payload,'$.authorization_key')=?", (key,))
    values = [json.loads(row[0]) for row in rows]
    return len(values), {value["source_version"] for value in values}


def _embedding_budget(engine: Research, run_approval: str) -> int:
    return int(engine.ledger.db.execute("SELECT count(*) FROM events e JOIN records p "
        "ON p.id=json_extract(e.payload,'$.approval_policy') AND p.kind='policy' "
        "WHERE e.kind='model.attempt.intended' "
        "AND json_extract(p.payload,'$.content.parent_run_approval')=?", (run_approval,)).fetchone()[0])


def _request(engine: Research, session: str, source: str, question: str, versions: dict[str, str]) -> Json:
    row = engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()
    if row is None:
        raise AuditError("Selected RAG source is missing")
    value = json.loads(row[0])
    if value.get("retention") != "permitted":
        raise ResearchError("rag_source_retention_not_permitted")
    passages = [engine._evidence(item[0]) for item in engine.ledger.db.execute(
        "SELECT id FROM passages WHERE source_id=? ORDER BY start,id", (source,))]
    result = build_request(question=question, source_version=source, body=value.get("body", ""),
        evidence=passages, versions=versions)
    result["transport_code_sha256"] = hashlib.sha256(Path(__file__).with_name("codex_provider.py").read_bytes()).hexdigest()
    result["answer_contract_code_sha256"] = hashlib.sha256(Path(__file__).with_name("rag_answers.py").read_bytes()).hexdigest()
    engine.ledger.append(session, "codex.evidence.prepared", {"source_version": source,
        "passage_ids": [p["id"] for p in passages], "source_text_sha256": hashlib.sha256(value.get("body", "").encode()).hexdigest(),
        "coverage": "Complete permitted stored article; publisher completeness unobserved", "task_kind": TASK_KIND})
    return result


def _assess(engine: Research, session: str, context: Context, data: Json, plan_id: str,
            rows: list[Json], versions: dict[str, str]) -> None:
    ledger = engine.ledger
    provider = provider_factory(engine, data)
    tasks = []
    for row in rows:
        source = row["source_version"]
        try:
            request = _request(engine, session, source, f"Query: {data['query']}\nQuestion: {data['question']}", versions)
        except AuditError:
            raise
        except ResearchError:
            row.update(status="unprocessed", error="Full permitted stored article is unavailable or incomplete", answer=None)
            continue
        task_key = digest(request)
        row["task_key"] = task_key
        if any(v["task_key"] == task_key or (v.get("authorization_key") == data["key"]
                and v.get("source_version") == source) for v in ledger.unresolved.values()):
            row.update(status="unknown", error="Prior outcome unresolved; no automatic retry", answer=None)
            continue
        cached = ledger.db.execute("SELECT result_id,id FROM attempts WHERE task_key=? AND status='valid' "
            "ORDER BY number LIMIT 1", (task_key,)).fetchone()
        if cached:
            if data.get("reuse_cache") is not True:
                raise ResearchError("Existing RAG answer requires explicit version-bound reuse_cache")
            prior = ledger.get(cached["result_id"], "codex_rag_answer")
            validate_answer(request, prior["result"])
            ledger.append(session, "model.cache_reused", {"task_key": task_key, "attempt": cached["id"],
                "assessment": cached["result_id"], "plan": plan_id, "basis": "explicit_exact_version_bound_resume"})
            row.update(status="cached", answer=prior["result"], assessment=cached["result_id"])
            row.pop("error", None)
            continue
        request_ref = ledger.artifacts.put(request)
        try:
            invocation = provider.prepare(request)
        except AuditError:
            raise
        except ResearchError as error:
            # Preparation has no model dispatch. Known limit/contract failures remain explicit.
            if str(error) != "codex_input_too_large_no_dispatch":
                raise
            row.update(status="unprocessed", error="Stored article exceeds registered full-input byte limit", answer=None)
            continue
        dispatch_ref = ledger.artifacts.put(invocation.manifest())
        tasks.append({"row": row, "source": source, "task_key": task_key, "request_ref": request_ref,
            "request": request, "invocation": invocation, "dispatch_ref": dispatch_ref})
    batch = ledger.record(session, "codex_batch_manifest", digest({"plan": plan_id, "tasks": [t["task_key"] for t in tasks]}), {
        "versions": versions, "plan": plan_id, "task_kind": TASK_KIND,
        "items": [{k: t[k] for k in ("source", "task_key", "request_ref", "dispatch_ref")} for t in tasks]})
    width = data.get("workers", 4)
    pending = list(tasks)
    retry = []
    for retry_round in range(2):
        for start in range(0, len(pending), width):
            prepared = []
            for task in pending[start:start + width]:
                spent, _ = _budget(engine, data["key"])
                if spent >= data["run_approval"]["max_article_attempts"]:
                    task["row"].update(status="pending", error="Authorized article-attempt budget exhausted", answer=None)
                    continue
                _expiry(data["run_approval"])
                prior_count = ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended' "
                    "AND json_extract(payload,'$.task_key')=?", (task["task_key"],)).fetchone()[0]
                # One automatic known-invalid retry across resumes, never a reset per invocation.
                if prior_count >= 2:
                    task["row"].update(status="failed", error="Two known attempts used; no further automatic retry", answer=None)
                    continue
                attempt, number = str(uuid.uuid4()), prior_count + 1
                intent = {"attempt": attempt, "task_key": task["task_key"], "number": number,
                    "batch": batch, "plan": plan_id, "request": task["request_ref"], "dispatch": task["dispatch_ref"],
                    "source_version": task["source"], "authorization_key": data["key"], "reserved_article_attempts": 1,
                    "retry_round": retry_round, "started_at": utc()}
                ledger.append(session, "model.attempt.intended", intent)
                ledger.unresolved[attempt] = intent
                prepared.append((task, attempt, number))
            for index, response in engine.gateway.codex_dispatch(session, provider,
                    [(t["invocation"], attempt) for t, attempt, _ in prepared], width):
                task, attempt, number = prepared[index]
                response_ref = ledger.artifacts.put(asdict(response))
                ledger.append(session, "codex.response.received", {"artifact": response_ref, "attempt": attempt})
                unknown = bool((response.raw_response or {}).get("unknown_outcome"))
                status = "unknown" if unknown else "invalid"
                validation: Json = {"status": status}
                assessment = None
                error_type = None
                if response.payload is not None and not unknown:
                    try:
                        validation = validate_answer(task["request"], response.payload)
                        supplied = {p["id"]: p for p in task["request"]["evidence"]}
                        references = []
                        for claim in response.payload["claims"]:
                            passage = supplied[claim["passage_id"]]
                            offset = passage["text"].index(claim["quote"])
                            references.append({**claim, "source_version": task["source"], "passage_hash": passage["text_hash"],
                                "source_start": passage["start"] + offset,
                                "source_end": passage["start"] + offset + len(claim["quote"])})
                        assessment = ledger.record(session, "codex_rag_answer", attempt, {
                            "attempt": attempt, "task_key": task["task_key"], "request_ref": task["request_ref"],
                            "response_ref": response_ref, "plan": plan_id, "source_version": task["source"],
                            "versions": versions, "result": response.payload, "validation": validation,
                            "evidence_references": references, "human_validated": False, "review_status": "provisional_model_answer",
                            "observed_model": response.model, "usage": response.usage, "recorded_at": utc()})
                        task["row"].update(status="valid", answer=response.payload, assessment=assessment)
                        task["row"].pop("error", None)
                        status = "valid"
                    except AuditError:
                        raise
                    except ResearchError as error:
                        error_type = type(error).__name__
                        validation = {"status": "invalid", "reason_code": str(error)}
                if status != "valid":
                    task["row"].update(status="unknown" if unknown else "failed", answer=None,
                        error="Outcome unobserved; not retried" if unknown else "Answer failed citation/schema/coverage validation")
                    if not unknown and number < 2 and retry_round == 0:
                        retry.append(task)
                def project(event: int) -> None:
                    ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        attempt, task["task_key"], batch, number, task["request_ref"], response_ref,
                        status, assessment, error_type, event))
                ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                    "attempt": attempt, "status": status, "response": response_ref, "assessment": assessment,
                    "validation": validation, "ended_at": utc()}, project)
                if not unknown:
                    ledger.unresolved.pop(attempt, None)
            counts = Counter(row["answer"]["status"] if row.get("answer") else row.get("status", "pending") for row in rows)
            print(f"Codex RAG: {dict(counts)}", file=sys.stderr, flush=True)
        pending, retry = retry, []


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    started_at = utc()
    allowed = {"reference_scores", "query", "question", "key", "top", "execute", "run_approval", "codex_model",
        "codex_executable", "reuse_cache", "workers"}
    if set(data) - allowed:
        raise ResearchError("Unsupported composed RAG input")
    if any(not isinstance(data.get(k), str) or not data[k].strip() for k in ("key", "query", "question", "codex_model")):
        raise ResearchError("RAG requires a stable key, exact query/question and pinned Codex model")
    if type(data.get("top", 100)) is not int or not 1 <= data.get("top", 100) <= 100:
        raise ResearchError("RAG ranked selection must be 1 through 100")
    if type(data.get("workers", 4)) is not int or not 1 <= data.get("workers", 4) <= 4:
        raise ResearchError("RAG Codex workers must be 1 through 4")
    if data.get("execute") is True and engine.config.offline:
        raise ResearchError("RAG execution requires process-local online configuration")
    approval = _approval(data)
    ledger = engine.ledger
    reference = ledger.get(data["reference_scores"], "article_query_run")
    engine._require(context, {"dataset"})
    if reference["versions"]["dataset"] != context.versions["dataset"]:
        raise ResearchError("RAG reference scores must bind the selected dataset")
    if reference.get("phase") != "scores":
        raise ResearchError("Reference must identify original corpus scores, not thresholded decisions")
    index = ledger.get(reference["index"], "vector_index")
    binding = {"reference_scores": data["reference_scores"], "index": reference["index"], "query": data["query"],
        "question": data["question"], "top": data.get("top", 100), "approval": approval,
        "codex_model": data["codex_model"], "codex_executable": data.get("codex_executable", "codex"),
        "executable_sha256": _binary_hash(data.get("codex_executable", "codex")), "method": METHOD}
    previous = ledger.db.execute("SELECT payload FROM records WHERE kind='rag_query_authorization' AND logical_key=? "
        "ORDER BY created_event LIMIT 1", (data["key"],)).fetchone()
    if previous and json.loads(previous[0])["binding"] != binding:
        raise ResearchError("RAG workflow query, approval, model and selection are immutable under the same authorization key")
    ledger.record(session, "rag_query_authorization", data["key"], {"binding": binding, "versions": context.versions})
    authorization = _register(engine, session, context, "policy", data["key"] + "-run", approval)
    from . import similarity_tags
    planned = similarity_tags.setup(engine, session, context, {"index": reference["index"], "query": data["query"],
        "question": data["question"], "tag": data["key"]})
    query_context = Context(context.objective, context.actor, planned["versions"])
    judge_versions = dict(query_context.versions)
    judge_versions["protocol"] = _register(engine, session, query_context, "protocol", data["key"] + "-rag", METHOD)
    judge_versions["prompt"] = _register(engine, session, query_context, "prompt", data["key"] + "-answer", {
        "instructions": TASK_INSTRUCTION, "schema": answer_schema(), "question": data["question"], "task_kind": TASK_KIND})
    judge_versions["codebook"] = _register(engine, session, query_context, "codebook", data["key"] + "-answers", {
        "labels": ["supported", "insufficient", "uncertain"], "definition": TASK_INSTRUCTION})
    judge_versions["model_profile"] = _register(engine, session, query_context, "model_profile", data["key"] + "-codex", {
        "provider": "codex-cli", "configured_model": data["codex_model"], "executable": binding["codex_executable"],
        "executable_sha256": binding["executable_sha256"], "fresh_context": True, "input_bytes_max": 250000,
        "timeout_seconds": 180, "output_acceptance_bytes_max": 2000000,
        "isolation_limitations": "Fresh read-only CLI and no-tools instructions do not prove filesystem isolation",
        "authentication": "Existing ChatGPT account only; no API-key fallback"})
    prior_plan = ledger.db.execute("SELECT payload FROM records WHERE kind='rag_query_plan' AND logical_key=? "
        "ORDER BY created_event LIMIT 1", (data["key"],)).fetchone()
    if prior_plan and (json.loads(prior_plan[0])["embedding_plan"] != planned["id"]
            or json.loads(prior_plan[0])["judge_versions"] != judge_versions):
        raise ResearchError("RAG implementation and planned versions are immutable under the existing authorization key")
    plan_id = ledger.record(session, "rag_query_plan", data["key"], {"versions": query_context.versions,
        "judge_versions": judge_versions, "run_approval_version": authorization, "binding": binding, "embedding_plan": planned["id"]})
    expected = index["source_records"]
    rows: list[Json] = []
    scored: Json | None = None
    embedded: Json | None = None
    embedding_approval = None
    if data.get("execute") is True:
        if Decimal(planned["estimated_cost_usd"]) > Decimal(str(approval["max_embedding_usd"])):
            raise ResearchError("Planned query embedding exceeds authorized estimated cost")
        embedding_approval = _register(engine, session, query_context, "policy", data["key"] + "-query-embedding", {
            "method": "embedding-run-approval-v1", "plan": planned["id"], "approved_by": approval["approved_by"],
            "instruction": approval["instruction"], "allow_external_processing": True, "allow_paid_inference": True,
            "max_estimated_cost_usd": approval["max_embedding_usd"], "expires_at": approval["expires_at"],
            "parent_run_approval": authorization, "max_requests": 1,
            "price_verification": {"checked_at": approval.get("embedding_price_checked_at"),
                "usd_per_million_input_tokens": approval.get("embedding_usd_per_million_input_tokens"),
                "source": approval.get("embedding_price_source"),
                "basis": "Caller-reported current price check; saved profile retained"}})
        requests = _embedding_budget(engine, authorization)
        if requests and data.get("reuse_cache") is not True:
            raise ResearchError("Existing query embedding requires explicit reuse_cache")
        embedded = engine.gateway.embed(session, query_context, {"plan": planned["id"],
            "approval_policy": embedding_approval, "max_requests": 0 if requests else 1})
        if not embedded["missing_task_keys"]:
            scored = similarity_tags.score(engine, session, query_context, {"plan": planned["id"],
                "embedding_run": embedded["id"], "reuse_cache": data.get("reuse_cache", False)})
            from .query_overview import TOP_SQL
            rows = [dict(row) for row in ledger.db.execute(TOP_SQL, (scored["run"], data.get("top", 100)))]
            for rank, row in enumerate(rows, 1):
                row.update(rank=rank, answer=None, status="pending")
            ledger.record(session, "rag_query_retrieval", plan_id, {"versions": query_context.versions,
                "plan": plan_id, "scores": scored["id"], "sql": TOP_SQL,
                "parameters": [scored["run"], data.get("top", 100)], "rows": rows,
                "selection": "Descending maximum passage cosine; deterministic source-version tie break"})
            _assess(engine, session, query_context, data, plan_id, rows, judge_versions)
    spent, unique = _budget(engine, data["key"])
    counts = Counter(row["answer"]["status"] for row in rows if row.get("answer"))
    failed = sum(row.get("status") in {"failed", "unknown", "unprocessed"} for row in rows)
    pending = sum(row.get("status") == "pending" for row in rows)
    examples = []
    for row in rows:
        if row.get("answer") and row["answer"]["status"] == "supported":
            for claim in row["answer"]["claims"][:2]:
                examples.append({"title": row["title"], "url": row["url"], **claim})
            break
    result = {"versions": query_context.versions, "judge_versions": judge_versions, "plan": plan_id,
        "query": data["query"], "question": data["question"], "expected_articles": expected,
        "scored_articles": scored["scored_articles"] if scored else 0,
        "missing_scores": scored["missing_articles"] if scored else expected,
        "selected_articles": len(rows), "attempted_articles": len(unique), "article_attempts": spent,
        "counts": {k: counts[k] for k in ("supported", "insufficient", "uncertain")},
        "failed_articles": failed, "pending_articles": pending, "rows": rows, "examples": examples,
        "status": "planned_not_executed" if data.get("execute") is not True else "embedding_incomplete" if scored is None
            else "partial" if failed or pending else "completed",
        "scores": scored["id"] if scored else None, "embedding_plan": planned["id"],
        "embedding_run": embedded["id"] if embedded else None, "embedding_approval": embedding_approval,
        "new_embedding_requests": embedded["requests_sent"] if embedded else 0,
        "cutoff": None, "tag_counts": {"yes": 0, "no": 0, "null": expected}, "human_validated": False,
        "model_request_count": None, "model_request_count_unavailable_reason": "Internal Codex requests unobserved",
        "provider_billing": None, "provider_billing_unavailable_reason": "Codex account billing unobserved",
        "unresolved_attempts": [k for k, v in ledger.unresolved.items() if v.get("authorization_key") == data["key"]],
        "started_at": started_at, "completed_at": utc(), "recorded_at": utc(),
        "scope": "Ranked article answers, not counts of unique incidents or dossier measurements"}
    identifier = ledger.record(session, "rag_query_result", plan_id, result)
    from .presentation import record
    presentation = record(engine, session, query_context, {"results": [{"kind": "rag_query_result", "id": identifier}],
        "markdown": render_answers(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}
