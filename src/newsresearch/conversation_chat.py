"""Compose reader requests in one fully audited runtime session."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .common import Context, Json, ResearchError, digest, require_active

if TYPE_CHECKING:
    from .runtime import Research


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    allowed = {"result", "key", "request_id", "question", "scope", "query", "run_approval",
        "codex_model", "codex_executable"}
    if set(data) - allowed:
        raise ResearchError("Unsupported reader conversation fields")
    engine._require(context, {"dataset"})
    original = engine.ledger.get(data["result"], "rag_query_result")
    if original["versions"]["dataset"] != context.versions["dataset"]:
        raise ResearchError("Reader result and dataset differ")
    if data.get("scope") not in {"current", "search"}:
        raise ResearchError("Choose current evidence or an explicit new search")
    if not isinstance(data.get("question"), str) or not data["question"].strip():
        raise ResearchError("A follow-up requires a question")
    for name in ("key", "request_id", "codex_model"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ResearchError("Conversation requires stable identity and a pinned model")
    request_key = digest({"result": data["result"], "request_id": data["request_id"]})
    binding = {**{name: data.get(name) for name in allowed - {"run_approval"}}, "actor": context.actor}
    prior_request = engine.ledger.db.execute("SELECT payload FROM records WHERE kind='conversation_chat_request' "
        "AND logical_key=? ORDER BY created_event LIMIT 1", (request_key,)).fetchone()
    if prior_request and json.loads(prior_request[0])["binding"] != binding:
        raise ResearchError("A reader request ID cannot change its question, scope, actor or configured model")
    engine.ledger.record(session, "conversation_chat_request", request_key, {
        "binding": binding, "versions": context.versions})
    from . import conversation
    root = engine.ledger.db.execute("SELECT id FROM records WHERE kind='conversation_definition' "
        "AND logical_key=? ORDER BY created_event LIMIT 1", (data["key"],)).fetchone()
    if root is None:
        started = conversation.execute(engine, session, context, {"action": "start", "result": data["result"],
            "key": data["key"]})
        root_id = started["conversation"]
    else:
        root_id = root[0]
        root_definition = engine.ledger.get(root_id, "conversation_definition")
        if root_definition["origin"] != {"kind": "rag_query_result", "id": data["result"]}:
            raise ResearchError("The conversation key belongs to a different immutable reader result")
    state = conversation.execute(engine, session, context, {"action": "read", "conversation": root_id})
    definition = state["definition"]
    retrieval = None
    turn_key = data["key"] + "-turn-" + data["request_id"]
    existing_turn = engine.ledger.db.execute("SELECT payload FROM records WHERE kind='conversation_turn' "
        "AND logical_key=? ORDER BY created_event LIMIT 1", (digest({"conversation": root_id, "key": turn_key}),)).fetchone()
    existing_selection = engine.ledger.db.execute("SELECT id FROM records WHERE kind='conversation_definition' "
        "AND logical_key=? ORDER BY created_event LIMIT 1", (data["key"] + "-search-" + data["request_id"],)).fetchone()
    if existing_turn:
        definition = json.loads(existing_turn[0])["definition"]
    elif data["scope"] == "search" and existing_selection:
        # A crash may leave retrieval durably complete before an answer starts.
        # Reuse that exact evidence definition instead of searching again.
        definition = existing_selection[0]
    elif data["scope"] == "search":
        from .conversation_search import execute as search
        retrieval = search(engine, session, context, {"query": data.get("query") or data["question"],
            "question": data["question"], "key": data["key"] + "-search-" + data["request_id"],
            "parent_conversation": definition})
        definition = retrieval["selection"]["definition"]
    turn = conversation.execute(engine, session, context, {"action": "ask", "conversation": definition,
        "key": turn_key, "question": data["question"],
        "execute": True, "run_approval": data["run_approval"], "codex_model": data["codex_model"],
        "codex_executable": data.get("codex_executable", "codex"), "reuse_cache": True,
        "scope": data["scope"],
        "presentation_destination": "local_app"})
    state = conversation.execute(engine, session, context, {"action": "read", "conversation": root_id})
    return {"turn": turn, "state": state, "retrieval": retrieval,
        "scope": data["scope"], "embedding_requests": 0}
