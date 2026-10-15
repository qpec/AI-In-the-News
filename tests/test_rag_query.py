"""Synthetic RAG integration checks; no real sources or inference."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any

import pytest

from newsresearch.codex_provider import CodexCLIProvider
from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.gateway import ProviderResponse
from newsresearch.rag_answers import ANSWER_FIELDS
from test_similarity_tags import prepared_query as _prepared_query, score
from test_similarity_tags import indexed as _indexed, embedding_plan as _embedding_plan

prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


class SyntheticAnswers(CodexCLIProvider):
    def __init__(self, workspace: Any, engine: Any) -> None:
        super().__init__(workspace, model="synthetic-rag-fixture")
        self.engine = engine
        self.database = engine.ledger.db.execute("PRAGMA database_list").fetchone()[2]
        self.calls: list[str] = []
        self.invalid_once = False
        self.always_invalid = False
        self.unknown_once = False

    def complete_prepared(self, prepared: Any) -> ProviderResponse:
        self._check_auth_environment()
        assert self.engine._active
        with sqlite3.connect(self.database) as db:
            intended = db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' "
                "AND json_extract(payload,'$.source_version')=? ORDER BY seq DESC LIMIT 1",
                (prepared.request["source_version"],)).fetchone()
            assert intended is not None
            intent = json.loads(intended[1])
            batch = db.execute("SELECT created_event FROM records WHERE id=? AND kind='codex_batch_manifest'",
                (intent["batch"],)).fetchone()
            assert batch[0] < intended[0]
        assert self.engine.ledger.artifacts.read(intent["request"]) == prepared.request
        packet = json.loads(prepared.stdin)
        assert not {"score", "rank", "cutoff", "prior_label"}.intersection(packet)
        assert "specific decision" in packet["task"]
        source = prepared.request["source_version"]
        self.calls.append(source)
        evidence = prepared.request["evidence"]
        result = {"status": "supported", "answer": "Synthetic decision and harm example, not a scientific finding.",
            "organization": "Synthetic organization", "actors": ["Synthetic member"],
            "decisions": ["Synthetic decision"], "incident": "Synthetic incident", "negative_impact": "Synthetic harm",
            "timing": "before", "claims": [{"passage_id": evidence[0]["id"], "quote": evidence[0]["text"],
                "supports": list(ANSWER_FIELDS)}], "inspected_passage_ids": [p["id"] for p in evidence]}
        unknown = self.unknown_once
        self.unknown_once = False
        if self.always_invalid or self.invalid_once:
            result["claims"] = []
            self.invalid_once = False
        return ProviderResponse(None if unknown else result, "codex-cli", "synthetic-rag-fixture", None,
            {"input_tokens": 2, "output_tokens": 2}, {**prepared.manifest(), "unknown_outcome": unknown})


@pytest.fixture
def workflow(prepared_query: Any, monkeypatch: Any, tmp_path: Any) -> dict[str, Any]:
    from newsresearch import rag_query

    engine, _, _, _, _, sent, _ = prepared_query
    scored = score(prepared_query)
    engine.config = replace(engine.config, offline=False)
    # This fixture models the launcher's temporary credential scope. It is a
    # synthetic string; the Codex transport must observe its complete removal.
    original_embed = engine.gateway.embed
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def scoped_embed(*args: Any, **kwargs: Any) -> Any:
        monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key-no-real-access")
        try:
            return original_embed(*args, **kwargs)
        finally:
            monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(engine.gateway, "embed", scoped_embed)
    for variable in ("CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    provider = SyntheticAnswers(tmp_path / "rag-workers", engine)
    monkeypatch.setattr(rag_query, "provider_factory", lambda research, data: provider)
    data = {"reference_scores": scored["id"], "query": "Synthetic organization decision and harm",
        "question": "What specific synthetic decision preceded or followed an AI incident with harm?",
        "key": "synthetic-rag", "top": 5, "execute": True, "codex_model": "synthetic-rag-fixture",
        "workers": 1, "reuse_cache": True,
        "run_approval": {"approved_by": "synthetic:test", "instruction": "Run this synthetic RAG software check",
            "allow_external_processing": True, "allow_codex_account": True, "allow_paid_inference": True,
            "max_article_attempts": 120, "max_embedding_requests": 1, "max_embedding_usd": "0.01",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}}
    versions = {"dataset": scored["versions"]["dataset"]}
    def run(payload: Any = None) -> Any:
        return engine.execute("rag_query", data if payload is None else payload, versions=versions,
            objective="Verify composed synthetic retrieval and answer provenance", actor="test:rag")
    return {"engine": engine, "module": rag_query, "data": data, "versions": versions,
        "run": run, "provider": provider, "sent": sent, "original_scores": scored}


def test_direct_handler_requires_audited_operation(workflow: Any) -> None:
    with pytest.raises(AuditError, match="active audited"):
        workflow["module"].execute(workflow["engine"], "invalid", Context("Bypass test", "test"), workflow["data"])
    assert not workflow["provider"].calls


def test_new_question_is_new_embedding_full_scoring_and_ranked_grounded_answers(workflow: Any) -> None:
    engine = workflow["engine"]
    sent_before = len(workflow["sent"])
    result = workflow["run"]()
    assert result["status"] == "completed"
    assert result["expected_articles"] == 11 and result["scored_articles"] == 9 and result["missing_scores"] == 2
    assert result["selected_articles"] == result["attempted_articles"] == result["article_attempts"] == 5
    assert result["counts"] == {"supported": 5, "insufficient": 0, "uncertain": 0}
    assert len(workflow["sent"]) == sent_before + 1 and result["new_embedding_requests"] == 1
    assert result["scores"] != workflow["original_scores"]["id"]
    plan = engine.ledger.get(result["embedding_plan"], "embedding_plan")
    canonical = f"Query: {workflow['data']['query']}\nQuestion: {workflow['data']['question']}"
    request = engine.ledger.artifacts.read(plan["items"][0]["request_ref"])
    assert request["body"]["input"] == [canonical]
    rows = result["rows"]
    assert [row["rank"] for row in rows] == [1, 2, 3, 4, 5]
    assert rows == sorted(rows, key=lambda row: (-row["score"], row["source_version"]))
    for row in rows:
        answer = engine.ledger.get(row["assessment"], "codex_rag_answer")
        supplied = engine.ledger.artifacts.read(answer["request_ref"])
        assert supplied["inclusion"]["instruction"] == canonical
        assert answer["human_validated"] is False and answer["evidence_references"]
    assert result["cutoff"] is None and result["tag_counts"] == {"yes": 0, "no": 0, "null": 11}
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert result["presentation"]["markdown"].count("Synthetic decision and harm example") >= 5
    assert result["presentation"]["ui_delivery_verified"] is False
    assert engine.ledger.verify()["status"] == "verified"


def test_known_invalid_answer_retries_once_and_does_not_stop_other_articles(workflow: Any) -> None:
    workflow["provider"].invalid_once = True
    result = workflow["run"]()
    assert result["status"] == "completed" and result["counts"]["supported"] == 5
    assert result["article_attempts"] == 6 and result["attempted_articles"] == 5
    assert workflow["provider"].calls.count(workflow["provider"].calls[0]) == 2
    assert not result["unresolved_attempts"]


def test_unknown_answer_continues_other_items_and_resume_never_redispatches_unknown(workflow: Any) -> None:
    workflow["provider"].unknown_once = True
    first = workflow["run"]()
    assert first["status"] == "partial" and first["article_attempts"] == 5
    assert first["counts"]["supported"] == 4 and first["failed_articles"] == 1
    assert len(first["unresolved_attempts"]) == 1
    sent_before, calls_before = len(workflow["sent"]), len(workflow["provider"].calls)
    resumed = workflow["run"]()
    assert resumed["article_attempts"] == 5 and len(workflow["provider"].calls) == calls_before
    assert resumed["counts"]["supported"] == 4 and resumed["failed_articles"] == 1
    assert len(workflow["sent"]) == sent_before and resumed["new_embedding_requests"] == 0


def test_known_failure_retry_limit_survives_resume(workflow: Any) -> None:
    workflow["provider"].always_invalid = True
    first = workflow["run"]()
    assert first["status"] == "partial" and first["article_attempts"] == 10 and first["failed_articles"] == 5
    assert not first["unresolved_attempts"] and first["counts"]["supported"] == 0
    resumed = workflow["run"]()
    assert resumed["article_attempts"] == 10 and len(workflow["provider"].calls) == 10


@pytest.mark.parametrize("field", ["query", "question", "codex_model"])
def test_same_authorization_cannot_change_query_model_or_approval(workflow: Any, field: str) -> None:
    workflow["run"]()
    sent_before = len(workflow["sent"])
    changed = {**workflow["data"], field: "Changed method under old approval"}
    with pytest.raises(ResearchError, match="immutable"):
        workflow["run"](changed)
    assert len(workflow["sent"]) == sent_before


def test_same_authorization_cannot_change_expiry(workflow: Any) -> None:
    workflow["run"]()
    changed = {**workflow["data"], "run_approval": {**workflow["data"]["run_approval"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()}}
    with pytest.raises(ResearchError, match="immutable"):
        workflow["run"](changed)


def test_offline_default_blocks_execution(workflow: Any) -> None:
    workflow["engine"].config = replace(workflow["engine"].config, offline=True)
    with pytest.raises(ResearchError, match="online"):
        workflow["run"]()
    assert not workflow["provider"].calls


def test_existing_embedding_requires_explicit_reuse(workflow: Any) -> None:
    workflow["run"]()
    with pytest.raises(ResearchError, match="reuse_cache"):
        workflow["run"]({**workflow["data"], "reuse_cache": False})


def test_plan_only_never_embeds_or_answers(workflow: Any) -> None:
    sent_before = len(workflow["sent"])
    result = workflow["run"]({**workflow["data"], "execute": False})
    assert result["status"] == "planned_not_executed" and result["article_attempts"] == 0
    assert len(workflow["sent"]) == sent_before and not workflow["provider"].calls
    assert result["presentation"]["markdown"]


def test_embedding_budget_spans_policy_versions(workflow: Any, monkeypatch: Any) -> None:
    first = workflow["run"]()
    module = workflow["module"]
    original_register = module._register
    original_embed = workflow["engine"].gateway.embed
    observed = []
    def amended_policy(engine: Any, session: str, context: Any, kind: str, key: str, content: Any) -> str:
        if content.get("method") == "embedding-run-approval-v1":
            content = {**content, "synthetic_policy_revision": "defense-in-depth budget regression"}
        return str(original_register(engine, session, context, kind, key, content))
    def observed_embed(session: str, context: Any, data: Any) -> Any:
        observed.append(data["max_requests"])
        return original_embed(session, context, data)
    monkeypatch.setattr(module, "_register", amended_policy)
    monkeypatch.setattr(workflow["engine"].gateway, "embed", observed_embed)
    sent_before = len(workflow["sent"])
    resumed = workflow["run"]()
    assert resumed["embedding_approval"] != first["embedding_approval"]
    assert observed == [0] and len(workflow["sent"]) == sent_before


def test_code_identity_change_cannot_create_new_query_plan_under_old_approval(workflow: Any, monkeypatch: Any) -> None:
    workflow["run"]()
    engine = workflow["engine"]
    original_identity = engine.identity
    def changed_identity() -> Any:
        value = original_identity()
        value["code_files"] = {**value["code_files"], "src/synthetic-changed.py": "a" * 64}
        return value
    monkeypatch.setattr(engine, "identity", changed_identity)
    sent_before = len(workflow["sent"])
    with pytest.raises(ResearchError, match="implementation and planned versions are immutable"):
        workflow["run"]()
    assert len(workflow["sent"]) == sent_before


def test_embedding_failure_remains_incomplete_and_one_request_cap_blocks_resend(workflow: Any, monkeypatch: Any) -> None:
    from newsresearch import embeddings
    original = embeddings.OpenAIEmbeddingTransport.send
    def failed_response(self: Any, body: bytes, client_request_id: str) -> Any:
        return replace(original(self, body, client_request_id), status=500)
    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", failed_response)
    sent_before = len(workflow["sent"])
    first = workflow["run"]()
    assert first["status"] == "embedding_incomplete" and first["selected_articles"] == 0
    assert first["missing_scores"] == 11 and not workflow["provider"].calls
    assert len(workflow["sent"]) == sent_before + 1
    resumed = workflow["run"]()
    assert resumed["status"] == "embedding_incomplete" and resumed["new_embedding_requests"] == 0
    assert len(workflow["sent"]) == sent_before + 1


def test_article_attempt_budget_continues_counting_previous_intents(workflow: Any, monkeypatch: Any) -> None:
    module = workflow["module"]
    original_budget = module._budget
    def nearly_exhausted(engine: Any, key: str) -> Any:
        attempts, unique = original_budget(engine, key)
        return attempts + 118, unique
    monkeypatch.setattr(module, "_budget", nearly_exhausted)
    result = workflow["run"]()
    assert result["status"] == "partial" and result["article_attempts"] == 120
    assert len(workflow["provider"].calls) == 2 and result["pending_articles"] == 3
    assert result["counts"]["supported"] == 2
