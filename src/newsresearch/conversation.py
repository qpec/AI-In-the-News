"""Audited conversational reuse of a frozen set of already-retrieved passages."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit
import uuid

from .codex_provider import CodexCLIProvider
from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .conversation_answers import TASK_INSTRUCTION, TASK_KIND, answer_schema, build_request, validate_answer

if TYPE_CHECKING:
    from .runtime import Research

EVIDENCE_BYTES = 180_000
HISTORY_BYTES = 40_000
METHOD: Json = {"method": "frozen-retrieval-conversation-v1",
    "scope": "Follow-up over immutable selected retrieved passages, not full articles or corpus prevalence",
    "selection": "Original winning and cited whole passages; deterministic round-robin ordering, 180000 UTF-8 serialized evidence bytes",
    "history": "At most six completed earlier turns and 40000 UTF-8 serialized history bytes; previous model answers are not primary evidence",
    "models": "One fresh Codex account CLI attempt per explicitly authorized turn, through the shared gateway",
    "retrieval": "No query embedding or new search; explicit search creates a new linked evidence definition",
    "failure": "Unknown outcomes remain unresolved; no automatic retries; failed processing is never a negative finding"}


def _register(engine: Research, session: str, context: Context, kind: str, key: str, content: Json) -> str:
    return str(engine._version(session, context, {"kind": kind, "key": key, "content": content,
        "amend_latest": True, "reason": "Register conversational reuse of immutable retrieved evidence before execution"})["id"])


def _definition(engine: Research, identifier: str) -> tuple[Json, str]:
    value = engine.ledger.get(identifier, "conversation_definition")
    return value, value.get("root_conversation") or identifier


def _summary(identifier: str, value: Json) -> Json:
    return {"id": identifier, **{k: v for k, v in value.items() if k != "evidence"}}


def _saved_presentation(engine: Research, kind: str, identifier: str) -> Json | None:
    row = engine.ledger.db.execute("SELECT p.id,p.payload FROM records p WHERE p.kind='result_presentation' "
        "AND EXISTS (SELECT 1 FROM json_each(p.payload,'$.results') x "
        "WHERE json_extract(x.value,'$.kind')=? AND json_extract(x.value,'$.id')=?) "
        "ORDER BY p.created_event DESC LIMIT 1", (kind, identifier)).fetchone()
    return {"id": row["id"], **json.loads(row["payload"])} if row else None


def _origin_material(engine: Research, origin: Json) -> tuple[Json, list[Json], list[Json]]:
    if set(origin) != {"kind", "id"} or origin["kind"] not in {"rag_query_result", "conversation_retrieval"}:
        raise ResearchError("Conversation origin must be an immutable RAG result or explicit retrieval")
    result = engine.ledger.get(origin["id"], origin["kind"])
    if origin["kind"] == "conversation_retrieval":
        return result, result["source_rows"], result["evidence"]
    rows = result["rows"]
    ordered: list[list[str]] = []
    for row in rows:
        identifiers = [row["passage_id"]] if row.get("passage_id") else []
        answer = row.get("answer")
        if isinstance(answer, dict):
            identifiers += [claim["passage_id"] for claim in answer.get("claims", [])]
        ordered.append(list(dict.fromkeys(identifiers)))
    evidence = []
    seen = set()
    for offset in range(max((len(ids) for ids in ordered), default=0)):
        for row, identifiers in zip(rows, ordered, strict=True):
            if offset >= len(identifiers) or identifiers[offset] in seen:
                continue
            passage = engine._evidence(identifiers[offset])
            if passage["source_id"] != row["source_version"]:
                raise AuditError("Original conversation passage belongs to a different selected source")
            evidence.append({**passage, "title": row.get("title"), "url": row.get("url")})
            seen.add(identifiers[offset])
    source_rows = [{k: row.get(k) for k in ("rank", "source_version", "title", "url", "score")} for row in rows]
    return result, source_rows, evidence


def start_from_evidence(engine: Research, session: str, context: Context, data: Json) -> Json:
    """Freeze an immutable retrieval; caller-supplied material must match its origin exactly."""
    require_active(engine, session)
    if not isinstance(data.get("key"), str) or not data["key"].strip():
        raise ResearchError("Conversation needs a stable key")
    origin, source_rows, supplied = _origin_material(engine, data["origin"])
    if any(name in data and data[name] != origin.get(name) for name in ("query", "question")):
        raise AuditError("Conversation retrieval text differs from its immutable origin")
    if (canonical(data.get("source_rows", source_rows)) != canonical(source_rows)
            or canonical(data.get("evidence", supplied)) != canonical(supplied)):
        raise AuditError("Conversation evidence or sources differ from their immutable retrieval origin")
    if context.versions.get("dataset") != origin["versions"]["dataset"]:
        raise ResearchError("Conversation and retrieval must bind the same exact dataset")
    source_ids = [row["source_version"] for row in source_rows]
    if len(source_ids) != len(set(source_ids)):
        raise ResearchError("Conversation selected article identities must be unique")
    allowed_sources = set(engine.ledger.get(context.versions["dataset"], "dataset")["source_versions"])
    if not set(source_ids) <= allowed_sources:
        raise AuditError("Conversation source lies outside the bound dataset")
    versions = dict(origin["versions"])
    versions["protocol"] = _register(engine, session, context, "protocol", "frozen-retrieval-conversation-v1", METHOD)
    verified = []
    seen = set()
    for item in supplied:
        identifier = item.get("id", item.get("passage_id"))
        if not isinstance(identifier, str) or not identifier:
            raise ResearchError("Conversation passage needs its original identifier")
        actual = engine._evidence(identifier)
        if item.get("source_id", item.get("source_version")) != actual["source_id"]:
            raise AuditError("Conversation passage source identity differs from its origin")
        if actual["source_id"] not in source_ids:
            raise AuditError("Conversation passage lies outside the selected article frame")
        for field in ("start", "end", "text", "text_hash"):
            if item.get(field) != actual[field]:
                raise AuditError("Conversation passage differs from its immutable source version")
        if identifier in seen:
            continue
        seen.add(identifier)
        metadata = next(row for row in source_rows if row["source_version"] == actual["source_id"])
        verified.append({**actual, "title": metadata.get("title"), "url": metadata.get("url")})
    question = data.get("question") or origin.get("question") or origin.get("query")
    if not isinstance(question, str) or not question.strip():
        raise ResearchError("Conversation start requires its original retrieval question")
    normalized = build_request(question=question, evidence=verified, versions=versions)["evidence"]
    by_source: dict[str, list[Json]] = {source: [] for source in source_ids}
    for item in normalized:
        by_source[item["source_id"]].append(item)
    normalized = [items[offset] for offset in range(max((len(v) for v in by_source.values()), default=0))
        for items in by_source.values() if offset < len(items)]
    included: list[Json] = []
    excluded = []
    for item in normalized:
        if len(canonical(included + [item]).encode("utf-8")) <= EVIDENCE_BYTES:
            included.append(item)
        else:
            excluded.append({"passage_id": item["id"], "source_version": item["source_id"], "reason": "frozen_context_byte_limit"})
    parent = data.get("parent_conversation")
    root = None
    if parent:
        prior, root = _definition(engine, parent)
        if prior["versions"]["dataset"] != versions["dataset"]:
            raise ResearchError("A linked retrieval cannot change the conversation dataset")
    value = {"versions": versions, "origin": data["origin"], "query": data.get("query", origin.get("query")),
        "question": question, "source_rows": source_rows, "evidence": included,
        "root_conversation": root, "parent_definition": parent, "selected_articles": len(source_rows),
        "evidence_source_count": len({p["source_id"] for p in included}), "included_passages": len(included),
        "available_passages": len(normalized), "excluded_passages": excluded, "evidence_bytes": len(canonical(included).encode("utf-8")),
        "human_validated": False, "model_calls": 0, "new_embedding_requests": 0, "method": METHOD}
    prior = engine.ledger.db.execute("SELECT payload FROM records WHERE kind='conversation_definition' AND logical_key=? "
        "ORDER BY created_event LIMIT 1", (data["key"],)).fetchone()
    if prior and json.loads(prior[0]) != value:
        raise ResearchError("Conversation start key is immutable; use an explicit linked retrieval for a new evidence set")
    identifier = engine.ledger.record(session, "conversation_definition", data["key"], value)
    engine.ledger.append(session, "conversation.evidence.frozen", {"definition": identifier, "origin": data["origin"],
        "passage_ids": [p["id"] for p in included], "excluded_passages": excluded, "versions": versions})
    return {"conversation": root or identifier, "definition": identifier, "versions": versions,
        "status": "ready", **{k: value[k] for k in ("selected_articles", "evidence_source_count", "included_passages",
            "available_passages", "excluded_passages", "evidence_bytes", "new_embedding_requests", "model_calls")}}


def read(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    definition, root = _definition(engine, data["conversation"])
    if context.versions.get("dataset") != definition["versions"]["dataset"]:
        raise ResearchError("Conversation read must bind the original dataset")
    definitions = []
    for row in engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='conversation_definition' "
            "AND (id=? OR json_extract(payload,'$.root_conversation')=?) ORDER BY created_event", (root, root)):
        item = _summary(row["id"], json.loads(row["payload"]))
        if item["origin"]["kind"] == "conversation_retrieval":
            item["presentation"] = _saved_presentation(engine, "conversation_retrieval", item["origin"]["id"])
        definitions.append(item)
    turns = [{"id": row["id"], **json.loads(row["payload"])} for row in engine.ledger.db.execute(
        "SELECT id,payload FROM records WHERE kind='conversation_turn' AND json_extract(payload,'$.conversation')=? ORDER BY created_event", (root,))]
    for turn in turns:
        turn["presentation"] = _saved_presentation(engine, "conversation_turn", turn["id"])
    latest = definitions[-1]
    result = {"conversation": root, "definition": latest["id"], "versions": latest["versions"],
        "definitions": definitions, "turns": turns, "new_embedding_requests": 0, "model_calls": 0}
    engine.ledger.append(session, "conversation.read", {"conversation": root, "definition": latest["id"],
        "turn_ids": [turn["id"] for turn in turns], "versions": latest["versions"]})
    return result


def _history(engine: Research, root: str) -> tuple[list[Json], int]:
    rows = engine.ledger.db.execute("SELECT payload FROM records WHERE kind='conversation_turn' "
        "AND json_extract(payload,'$.conversation')=? ORDER BY created_event", (root,))
    completed = [json.loads(row[0]) for row in rows]
    completed = [row for row in completed if row.get("processing_status") in {"valid", "deterministic"} and row.get("result")]
    selected = completed[-6:]
    messages: list[Json] = []
    for turn in selected:
        messages.extend([{"role": "user", "content": turn["question"]},
            {"role": "assistant", "content": turn["result"]["answer"]}])
    while messages and len(canonical(messages).encode("utf-8")) > HISTORY_BYTES:
        messages = messages[2:]
    return messages, len(completed) - len(messages) // 2


def provider_factory(engine: Research, data: Json) -> CodexCLIProvider:
    return CodexCLIProvider(engine.ledger.root / "codex-workers", executable=data.get("codex_executable", "codex"),
        model=data["codex_model"], timeout_seconds=180, max_input_bytes=250_000, max_output_bytes=2_000_000)


def _approval(data: Json) -> Json:
    value = data.get("run_approval", {})
    try:
        expires = datetime.fromisoformat(value["expires_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError, TypeError, AttributeError):
        raise ResearchError("Conversation turn needs a timezone-aware approval expiry") from None
    if (not value.get("approved_by") or not value.get("instruction")
            or value.get("allow_codex_account") is not True or value.get("allow_external_processing") is not True
            or type(value.get("max_attempts")) is not int or value["max_attempts"] != 1
            or expires.tzinfo is None or expires <= datetime.now(timezone.utc)):
        raise ResearchError("Conversation approval must bind one concrete Codex attempt and external processing")
    return {**value, "method": "codex-conversation-turn-approval-v1"}


def _present(engine: Research, session: str, context: Context, identifier: str, value: Json, destination: str) -> Json:
    from .presentation import record
    return record(engine, session, context, {"results": [{"kind": "conversation_turn", "id": identifier}],
        "markdown": render(value), "destination": destination})


def ask(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    definition, root = _definition(engine, data["conversation"])
    if context.versions.get("dataset") != definition["versions"]["dataset"]:
        raise ResearchError("Conversation turn must bind its original dataset")
    for field in ("key", "question"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ResearchError("Conversation turn requires a stable key and nonblank question")
    if len(data["question"].encode("utf-8")) > 16000:
        raise ResearchError("Conversation question exceeds its registered UTF-8 byte limit")
    if data.get("scope", "current") not in {"current", "search"}:
        raise ResearchError("Conversation answer scope must be current or an explicit search")
    destination = data.get("presentation_destination", "codex_chat")
    logical_key = digest({"conversation": root, "key": data["key"]})
    previous = engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='conversation_turn' AND logical_key=? "
        "ORDER BY created_event LIMIT 1", (logical_key,)).fetchone()
    if previous:
        old = json.loads(previous["payload"])
        if old["question"] != data["question"] or old["definition"] != data["conversation"]:
            raise ResearchError("Turn key is immutable; changed question or evidence requires a new turn")
        if (data.get("codex_model") is not None and old.get("configured_model") != data["codex_model"]
                or data.get("codex_executable") is not None and old.get("host_executable") != data["codex_executable"]):
            raise ResearchError("A replay cannot change the pinned model or executable")
        if data.get("reuse_cache") is not True:
            raise ResearchError("Reusing an existing conversation turn requires explicit reuse_cache")
        turn_context = Context(context.objective, context.actor, old["versions"])
        engine.ledger.append(session, "conversation.turn.reused", {"turn": previous["id"], "conversation": root,
            "basis": "explicit immutable turn replay; no new model dispatch"})
        return {"id": previous["id"], **old, "cached": True,
            "presentation": _present(engine, session, turn_context, previous["id"], old, destination)}
    versions = dict(definition["versions"])
    versions["question"] = _register(engine, session, context, "question", logical_key, {"text": data["question"],
        "scope": "Only the frozen retrieved evidence", "definition": data["conversation"]})
    versions["prompt"] = _register(engine, session, context, "prompt", "conversation-answer-v1", {
        "instructions": TASK_INSTRUCTION, "schema": answer_schema(), "method": METHOD})
    versions["profile"] = _register(engine, session, context, "profile", "conversation-answer-v1", {
        "mode": "exploratory", "population_estimate": False, "scope": METHOD["scope"]})
    executable = data.get("codex_executable", "codex")
    executable_path = Path(executable)
    executable_hash = None
    if executable_path.is_file():
        with executable_path.open("rb") as stream:
            executable_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    versions["model_profile"] = _register(engine, session, context, "model_profile", logical_key, {
        "provider": "codex-cli", "configured_model": data.get("codex_model"),
        "host_executable": executable, "host_executable_sha256": executable_hash,
        "timeout_seconds": 180, "input_bytes_max": 250000, "output_acceptance_bytes_max": 2000000,
        "fresh_context": True, "model_request_id_and_billing": "Unavailable unless observed",
        "isolation_limitations": "No-tools instruction and read-only fresh CLI do not prove filesystem isolation"})
    turn_context = Context(context.objective, context.actor, versions)
    history, omitted = _history(engine, root)
    request = build_request(question=data["question"], evidence=definition["evidence"], versions=versions, history=history)
    request["transport_code_sha256"] = hashlib.sha256(Path(__file__).with_name("codex_provider.py").read_bytes()).hexdigest()
    request["conversation_contract_sha256"] = hashlib.sha256(Path(__file__).with_name("conversation_answers.py").read_bytes()).hexdigest()
    request_ref = engine.ledger.artifacts.put(request)
    value: Json = {"versions": versions, "conversation": root, "definition": data["conversation"], "turn_key": data["key"],
        "question": data["question"], "request_ref": request_ref, "task_key": digest(request), "history_omitted_turns": omitted,
        "selected_articles": definition["selected_articles"], "evidence_source_count": definition["evidence_source_count"],
        "included_passages": definition["included_passages"], "excluded_passages": definition["excluded_passages"],
        "new_embedding_requests": 0, "new_search_performed": False, "human_validated": False, "codex_attempts": 0,
        "scope": data.get("scope", "current"), "evidence_mode": definition["origin"]["kind"],
        "actor": context.actor, "session": session,
        "configured_model": data.get("codex_model"), "host_executable": executable,
        "result": None, "processing_status": "not_executed", "attempt": None, "observed_model": None, "usage": None,
        "model_request_count": None, "provider_billing": None, "started_at": utc()}
    if not definition["evidence"] or data.get("new_search") is True:
        value.update(processing_status="deterministic", result={"status": "needs_retrieval",
            "answer": "The current retrieved context cannot answer this request. An explicit new search is required.",
            "citations": [], "inspected_passage_ids": [], "suggested_query": data["question"]})
    elif data.get("execute") is True:
        _dispatch(engine, session, turn_context, data, logical_key, request, value)
    value["completed_at"] = utc()
    identifier = engine.ledger.record(session, "conversation_turn", logical_key, value)
    return {"id": identifier, **value, "presentation": _present(engine, session, turn_context, identifier, value, destination)}


def _dispatch(engine: Research, session: str, context: Context, data: Json, logical_key: str, request: Json, value: Json) -> None:
    ledger = engine.ledger
    if engine.config.offline:
        raise ResearchError("Conversation dispatch requires explicit process-local online configuration")
    if not isinstance(data.get("codex_model"), str) or not data["codex_model"].strip():
        raise ResearchError("Pin the configured Codex model for this conversation turn")
    approval = _approval(data)
    approval_id = _register(engine, session, context, "policy", logical_key, approval)
    value["run_approval_version"] = approval_id
    if any(v["task_key"] == value["task_key"] or (v.get("conversation") == value["conversation"]
            and v.get("question_sha256") == hashlib.sha256(data["question"].encode()).hexdigest()) for v in ledger.unresolved.values()):
        value.update(processing_status="unknown", error="An earlier outcome is unresolved; no automatic retry")
        return
    if ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended' "
            "AND json_extract(payload,'$.authorization_key')=? LIMIT 1", (logical_key,)).fetchone():
        value.update(processing_status="failed", error="This turn's authorized attempt was already spent")
        return
    try:
        provider = provider_factory(engine, data)
        invocation = provider.prepare(request)
    except AuditError:
        raise
    except ResearchError as error:
        value.update(processing_status="failed", error="Codex preparation failed; no model attempt was dispatched",
            error_type=type(error).__name__)
        return
    dispatch_ref = ledger.artifacts.put(invocation.manifest())
    batch = ledger.record(session, "codex_batch_manifest", logical_key, {"versions": context.versions,
        "task_kind": TASK_KIND, "conversation": value["conversation"], "definition": value["definition"],
        "items": [{"task_key": value["task_key"], "request_ref": value["request_ref"], "dispatch_ref": dispatch_ref}]})
    attempt = str(uuid.uuid4())
    intent = {"attempt": attempt, "task_key": value["task_key"], "number": 1, "batch": batch,
        "request": value["request_ref"], "dispatch": dispatch_ref, "authorization_key": logical_key,
        "conversation": value["conversation"], "question_sha256": hashlib.sha256(data["question"].encode()).hexdigest(),
        "approval_policy": approval_id, "reserved_attempts": 1, "started_at": utc()}
    ledger.append(session, "model.attempt.intended", intent)
    ledger.unresolved[attempt] = intent
    value["attempt"] = attempt
    value["codex_attempts"] = 1
    for _, response in engine.gateway.codex_dispatch(session, provider, [(invocation, attempt)], 1):
        response_ref = ledger.artifacts.put(asdict(response))
        ledger.append(session, "codex.response.received", {"artifact": response_ref, "attempt": attempt})
        unknown = bool((response.raw_response or {}).get("unknown_outcome"))
        status = "unknown" if unknown else "invalid"
        validation: Json = {"status": status}
        error_type = None
        if response.payload is not None and not unknown:
            try:
                validation = validate_answer(request, response.payload)
                value["result"] = validation["normalized_answer"]
                status = "valid"
            except AuditError:
                raise
            except ResearchError as error:
                error_type = type(error).__name__
                validation = {"status": "invalid", "reason_code": str(error)}
        assessment = ledger.record(session, "conversation_model_answer", attempt, {
            "versions": context.versions, "request_ref": value["request_ref"], "response_ref": response_ref,
            "attempt": attempt, "raw_result": response.payload, "validation": validation,
            "human_validated": False, "reference_type": "provisional_model_interpretation"})
        def project(event: int) -> None:
            ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                attempt, value["task_key"], batch, 1, value["request_ref"], response_ref, status,
                assessment, error_type, event))
        ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
            "attempt": attempt, "status": status, "response": response_ref, "assessment": assessment,
            "validation": validation, "ended_at": utc()}, project)
        if not unknown:
            ledger.unresolved.pop(attempt, None)
        value.update(processing_status=status, assessment=assessment, response_ref=response_ref,
            observed_model=response.model, usage=response.usage)
        if status != "valid":
            value["error"] = "Model outcome unobserved; retry blocked" if unknown else "Answer failed citation/schema/coverage validation"


def render(value: Json) -> str:
    from .provisional_tags import literal
    result = value.get("result")
    lines = [f"**Question:** {literal(value['question'])}", "", f"**Processing:** {value['processing_status']}.", ""]
    if result:
        lines += [f"**Answer status:** {result['status']}.", "", literal(result["answer"]), ""]
        for citation in result["citations"]:
            title = literal(citation.get("title") or "Source")
            url = citation.get("url")
            try:
                if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and urlsplit(url).netloc:
                    title = f"[{title}]({quote(url, safe=':/?#=&%+-._~')})"
            except ValueError:
                pass
            words = list(re.finditer(r"\S+", citation["quote"]))
            excerpt = citation["quote"] if len(words) <= 25 else citation["quote"][:words[24].end()] + "…"
            lines.append(f"- {title}: “{literal(excerpt)}” (passage `{citation['passage_id']}`).")
        if result["suggested_query"]:
            lines += ["", f"Suggested follow-up search: {literal(result['suggested_query'])}. This suggested search has not been performed."]
    else:
        lines.append(literal(value.get("error", "No model answer was executed.")))
    retrieval = ("Evidence came from the explicit local keyword search for this turn. " if value.get("scope") == "search"
        else "No new search for this follow-up. ")
    lines += ["", f"Scope: {value['evidence_source_count']} of {value['selected_articles']} selected articles; "
        f"{value['included_passages']} supplied passages; {len(value['excluded_passages'])} passages excluded by the context limit. "
        + retrieval + "Answer reused this exact evidence definition; no embedding. Selected passages are not complete articles or the entire corpus. "
        "Provisional model interpretation; no human validation. Exact instructions, evidence, response and presentation are audited."]
    return "\n".join(lines)


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    action = data.get("action", "ask")
    if action == "start":
        origin = {"kind": "rag_query_result", "id": data["result"]}
        return start_from_evidence(engine, session, context, {"key": data["key"], "origin": origin})
    if action == "read":
        return read(engine, session, context, data)
    if action == "ask":
        return ask(engine, session, context, data)
    raise ResearchError("Unsupported conversation action")
