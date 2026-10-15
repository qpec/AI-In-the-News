"""Composed app requests keep one preflight and explicit retrieval boundaries."""
from __future__ import annotations

from typing import Any
import uuid

import pytest

from newsresearch.common import ResearchError
from test_conversation import conversation_state as _conversation_state, rag_workflow as _rag_workflow
from test_conversation import prepared_query as _prepared_query, indexed as _indexed, embedding_plan as _embedding_plan

conversation_state = _conversation_state
rag_workflow = _rag_workflow
prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


def test_app_followup_search_reuse_and_request_replay_share_one_preflight(conversation_state: Any, monkeypatch: Any) -> None:
    state = conversation_state
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Interactive follow-ups must not embed or rescore")
    monkeypatch.setattr(state["engine"].gateway, "embed", forbidden)
    preflights = []
    verify = state["engine"].ledger.verify
    def counted_verify() -> Any:
        preflights.append(True)
        return verify()
    monkeypatch.setattr(state["engine"].ledger, "verify", counted_verify)
    payload = {"result": state["original"]["id"], "key": "synthetic-reader", "request_id": str(uuid.uuid4()),
        "question": "What do these sources report?", "scope": "current", "query": "",
        "run_approval": state["approval"], "codex_model": "synthetic-conversation"}
    first = state["run"](payload, "conversation_chat")
    assert len(preflights) == 1 and first["retrieval"] is None
    searched_input = {**payload, "request_id": str(uuid.uuid4()), "scope": "search", "query": "Synthetic",
        "question": "What does the new keyword evidence say?"}
    searched = state["run"](searched_input, "conversation_chat")
    assert len(preflights) == 2 and searched["retrieval"]["returned_articles"] > 0
    assert searched["turn"]["definition"] != first["turn"]["definition"]
    followup = state["run"]({**payload, "request_id": str(uuid.uuid4()), "question": "Explain that evidence further."},
        "conversation_chat")
    assert followup["turn"]["definition"] == searched["turn"]["definition"]
    assert followup["retrieval"] is None and len(state["provider"].calls) == 3
    replayed = state["run"](searched_input, "conversation_chat")
    assert replayed["turn"]["id"] == searched["turn"]["id"]
    assert len(preflights) == 4 and len(state["provider"].calls) == 3
    assert len(replayed["state"]["turns"]) == 3
    assert state["engine"].ledger.db.execute("SELECT count(*) FROM records WHERE kind='conversation_retrieval'").fetchone()[0] == 1
    assert replayed["embedding_requests"] == 0
    with pytest.raises(ResearchError, match="request ID cannot change"):
        state["run"]({**searched_input, "question": "Changed instructions"}, "conversation_chat")


def test_app_zero_search_has_a_visible_overview_and_no_model(conversation_state: Any) -> None:
    state = conversation_state
    result = state["run"]({"result": state["original"]["id"], "key": "synthetic-empty-reader",
        "request_id": str(uuid.uuid4()), "question": "What happened?", "scope": "search", "query": "impossiblekeyword",
        "run_approval": state["approval"], "codex_model": "synthetic-conversation"}, "conversation_chat")
    assert result["retrieval"]["returned_articles"] == 0
    assert "No keyword matches" in result["retrieval"]["presentation"]["markdown"]
    assert result["turn"]["result"]["status"] == "needs_retrieval"
    assert result["turn"]["codex_attempts"] == 0 and not state["provider"].calls
