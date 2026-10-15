"""Synthetic follow-up checks; no production store, network or real models."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any

import pytest

from newsresearch.codex_provider import CodexCLIProvider
from newsresearch.common import AuditError, Context, ResearchError, digest
from newsresearch.gateway import ProviderResponse
from test_rag_query import workflow as _rag_workflow
from test_similarity_tags import prepared_query as _prepared_query
from test_similarity_tags import indexed as _indexed, embedding_plan as _embedding_plan

rag_workflow = _rag_workflow
prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


class SyntheticConversation(CodexCLIProvider):
    def __init__(self, root: Any, engine: Any) -> None:
        super().__init__(root, model="synthetic-conversation")
        self.engine = engine
        self.database = engine.ledger.db.execute("PRAGMA database_list").fetchone()[2]
        self.calls: list[Any] = []
        self.unknown = False
        self.invalid = False
        self.needs_retrieval = False

    def complete_prepared(self, prepared: Any) -> ProviderResponse:
        self._check_auth_environment()
        assert self.engine._active
        with sqlite3.connect(self.database) as db:
            # The dispatched request and complete batch must already be durable.
            intended = db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' "
                "AND json_extract(payload,'$.task_key')=? ORDER BY seq DESC LIMIT 1", (digest(prepared.request),)).fetchone()
            assert intended is not None
            intent = json.loads(intended[1])
            batch = db.execute("SELECT created_event FROM records WHERE id=?", (intent["batch"],)).fetchone()
            assert batch[0] < intended[0]
        assert self.engine.ledger.artifacts.read(intent["request"]) == prepared.request
        packet = json.loads(prepared.stdin)
        assert "conversation" in packet["task"].lower()
        assert prepared.request["task_kind"] == "rag_conversation_answer"
        self.calls.append(prepared.request)
        evidence = prepared.request["evidence"]
        result = {"status": "needs_retrieval" if self.needs_retrieval else "answered",
            "answer": "Synthetic answer from frozen supplied evidence; software fixture only.",
            "citations": [] if self.needs_retrieval else [{"passage_id": evidence[0]["id"],
                "quote": "Nonmatching synthetic quote" if self.invalid else evidence[0]["text"]}],
            "inspected_passage_ids": [item["id"] for item in evidence],
            "suggested_query": "Synthetic additional evidence" if self.needs_retrieval else ""}
        return ProviderResponse(None if self.unknown else result, "codex-cli", "synthetic-conversation", None,
            {"input_tokens": 2, "output_tokens": 2}, {**prepared.manifest(), "unknown_outcome": self.unknown})


@pytest.fixture
def conversation_state(rag_workflow: Any, monkeypatch: Any, tmp_path: Any) -> dict[str, Any]:
    from newsresearch import conversation
    result = rag_workflow["run"]()
    engine = rag_workflow["engine"]
    versions = {"dataset": result["versions"]["dataset"]}
    provider = SyntheticConversation(tmp_path / "conversation-workers", engine)
    monkeypatch.setattr(conversation, "provider_factory", lambda research, data: provider)
    def run(data: Any, operation: str = "conversation") -> Any:
        return engine.execute(operation, data, versions=versions,
            objective="Verify source-free audited follow-up reuse", actor="test:conversation")
    approval = {"approved_by": "synthetic:test", "instruction": "Run this single synthetic follow-up attempt",
        "allow_codex_account": True, "allow_external_processing": True, "max_attempts": 1,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    return {"module": conversation, "engine": engine, "original": result, "versions": versions, "run": run,
        "provider": provider, "sent": rag_workflow["sent"], "approval": approval}


def start(state: Any, key: str = "synthetic-chat") -> Any:
    return state["run"]({"action": "start", "result": state["original"]["id"], "key": key})


def ask(state: Any, definition: str, key: str = "turn-one", question: str = "What happened in the synthetic evidence?", **changes: Any) -> Any:
    return state["run"]({"action": "ask", "conversation": definition, "key": key, "question": question,
        "execute": True, "run_approval": state["approval"], "codex_model": "synthetic-conversation",
        "reuse_cache": True, **changes})


def test_direct_handler_cannot_bypass_runtime(conversation_state: Any) -> None:
    state = conversation_state
    with pytest.raises(AuditError, match="active audited"):
        state["module"].execute(state["engine"], "invalid", Context("Bypass", "test"), {"action": "read"})


def test_start_freezes_original_passages_and_followups_reuse_without_embedding(conversation_state: Any, monkeypatch: Any) -> None:
    state = conversation_state
    sent_before = len(state["sent"])
    def forbidden_embedding(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("Conversation must never request a query embedding")
    monkeypatch.setattr(state["engine"].gateway, "embed", forbidden_embedding)
    selected = start(state)
    assert selected["included_passages"] > 0 and selected["selected_articles"] == 5
    first = ask(state, selected["definition"])
    second = ask(state, selected["definition"], "turn-two", "And what happened next?")
    assert first["processing_status"] == second["processing_status"] == "valid"
    assert first["result"]["status"] == "answered" and first["result"]["citations"]
    assert first["codex_attempts"] == 1 and first["new_embedding_requests"] == 0
    assert first["human_validated"] is False and first["actor"] == "test:conversation"
    assert len(state["sent"]) == sent_before
    assert state["provider"].calls[1]["evidence"] == state["provider"].calls[0]["evidence"]
    assert state["provider"].calls[1]["history"] == [{"role": "user", "content": first["question"]},
        {"role": "assistant", "content": first["result"]["answer"]}]
    citation = first["result"]["citations"][0]
    assert citation["source_version"] and citation["passage_hash"] and citation["source_end"] > citation["source_start"]
    assert state["engine"].ledger.verify()["status"] == "verified"


def test_replay_is_idempotent_and_read_restores_exact_presentation(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    first = ask(state, selected["definition"])
    cached = ask(state, selected["definition"])
    assert cached["id"] == first["id"] and cached["cached"] is True and len(state["provider"].calls) == 1
    restored = state["run"]({"action": "read", "conversation": selected["conversation"]})
    assert len(restored["turns"]) == 1
    assert restored["turns"][0]["presentation"]["markdown"] == first["presentation"]["markdown"]
    assert restored["definition"] == selected["definition"]
    with pytest.raises(ResearchError, match="immutable"):
        ask(state, selected["definition"], question="Changed question under the same turn key")


def test_unknown_outcome_blocks_retry_even_with_new_turn_key(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    state["provider"].unknown = True
    first = ask(state, selected["definition"])
    assert first["processing_status"] == "unknown" and first["result"] is None
    cached = ask(state, selected["definition"])
    other = ask(state, selected["definition"], key="turn-two")
    assert cached["processing_status"] == other["processing_status"] == "unknown"
    assert other["codex_attempts"] == 0 and len(state["provider"].calls) == 1
    assert len(state["engine"].ledger.unresolved) == 1


def test_invalid_answer_remains_failure_and_is_not_automatically_retried(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    state["provider"].invalid = True
    first = ask(state, selected["definition"])
    assert first["processing_status"] == "invalid" and first["result"] is None
    assert not state["engine"].ledger.unresolved
    ask(state, selected["definition"])
    assert len(state["provider"].calls) == 1


def test_needs_retrieval_does_not_silently_search(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    state["provider"].needs_retrieval = True
    result = ask(state, selected["definition"])
    assert result["processing_status"] == "valid" and result["result"]["status"] == "needs_retrieval"
    assert result["new_search_performed"] is False
    assert state["engine"].ledger.db.execute("SELECT count(*) FROM records WHERE kind='conversation_retrieval'").fetchone()[0] == 0


def test_empty_frozen_context_requests_explicit_search_without_model(conversation_state: Any, monkeypatch: Any) -> None:
    state = conversation_state
    monkeypatch.setattr(state["module"], "EVIDENCE_BYTES", 2)
    selected = start(state)
    assert selected["included_passages"] == 0 and selected["excluded_passages"]
    state["engine"].config = replace(state["engine"].config, offline=True)
    result = ask(state, selected["definition"])
    assert result["processing_status"] == "deterministic" and result["result"]["status"] == "needs_retrieval"
    assert result["codex_attempts"] == 0 and not state["provider"].calls


def test_explicit_new_search_links_evidence_and_preserves_old_turns(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    first = ask(state, selected["definition"])
    searched = state["run"]({"query": "Synthetic", "question": "What does this new selection say?",
        "key": "synthetic-linked-search", "parent_conversation": selected["definition"]}, "conversation_search")
    child = searched["selection"]
    assert child["conversation"] == selected["conversation"] and child["definition"] != selected["definition"]
    second = ask(state, child["definition"], "turn-two", "What does the explicit new evidence say?", scope="search")
    assert second["evidence_mode"] == "conversation_retrieval" and second["scope"] == "search"
    read = state["run"]({"action": "read", "conversation": selected["conversation"]})
    assert len(read["definitions"]) == len(read["turns"]) == 2
    assert read["definition"] == child["definition"] and read["turns"][0]["id"] == first["id"]
    assert read["definitions"][1]["presentation"]["markdown"] == searched["presentation"]["markdown"]


def test_helper_rejects_evidence_injection_before_dispatch(conversation_state: Any, monkeypatch: Any) -> None:
    state = conversation_state
    def injected_start(session: str, context: Any, data: Any) -> Any:
        return state["module"].start_from_evidence(state["engine"], session, context, data)
    monkeypatch.setattr(state["engine"], "_conversation", injected_start)
    with pytest.raises(AuditError, match="differ from their immutable"):
        state["run"]({"key": "injected", "origin": {"kind": "rag_query_result", "id": state["original"]["id"]},
            "evidence": [{"id": "fabricated", "text": "Injected material"}]})
    assert not state["provider"].calls


def test_known_preparation_failure_is_audited_without_spending_attempt(conversation_state: Any, monkeypatch: Any) -> None:
    state = conversation_state
    selected = start(state)
    def fail_prepare(request: Any) -> Any:
        raise ResearchError("codex_api_key_environment_forbidden")
    monkeypatch.setattr(state["provider"], "prepare", fail_prepare)
    result = ask(state, selected["definition"])
    assert result["processing_status"] == "failed" and result["codex_attempts"] == 0
    assert result["presentation"]["markdown"] and not state["provider"].calls
    assert not state["engine"].ledger.unresolved


def test_replay_cannot_silently_change_model(conversation_state: Any) -> None:
    state = conversation_state
    selected = start(state)
    ask(state, selected["definition"])
    with pytest.raises(ResearchError, match="pinned model"):
        ask(state, selected["definition"], codex_model="different-model")
