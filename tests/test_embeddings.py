from __future__ import annotations

import base64
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import struct
from typing import Any

import pytest

from newsresearch import embeddings
from newsresearch.common import AuditError, ResearchError, canonical
from newsresearch.runtime import Research
from test_legacy import make_archive, pilot_versions, run_pilot


@pytest.fixture
def embedding_plan(engine: Research, tmp_path: Path, monkeypatch: Any) -> tuple[Research, dict[str, Any]]:
    class SyntheticTokenizer:
        def encode_ordinary(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    monkeypatch.setattr(embeddings, "offline_tokenizer", lambda: SyntheticTokenizer())
    monkeypatch.setitem(embeddings.PROFILE, "dimensions", 4)
    monkeypatch.setitem(embeddings.PROFILE, "max_inputs_per_request", 3)
    root = tmp_path / "archive"
    make_archive(root, with_text=True)
    versions = pilot_versions(engine, 11)
    prepared = run_pilot(engine, root, versions)
    planned = engine.execute(
        "plan_embeddings",
        {"preparation": prepared["id"]},
        objective="Plan synthetic embedding requests without a network",
        actor="test",
        versions={**versions, "dataset": prepared["dataset"]},
    )
    return engine, planned


def approval(engine: Research, plan: dict[str, Any], budget: str = "1.00") -> str:
    return engine.execute(
        "version",
        {
            "kind": "policy",
            "key": "synthetic-paid-run-approval",
            "content": {
                "method": "embedding-run-approval-v1",
                "plan": plan["id"],
                "approved_by": "test:synthetic-operator",
                "allow_external_processing": True,
                "allow_paid_inference": True,
                "max_estimated_cost_usd": budget,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            },
        },
        objective="Register synthetic run permission; transport is mocked",
        actor="test",
    )["id"]


def run(engine: Research, plan: dict[str, Any], policy: str | None = None, limit: int | None = None) -> Any:
    payload: dict[str, Any] = {"plan": plan["id"]}
    if policy:
        payload["approval_policy"] = policy
    if limit is not None:
        payload["max_requests"] = limit
    return engine.execute(
        "embed",
        payload,
        objective="Exercise mocked embedding gateway",
        actor="test",
        versions=plan["versions"],
    )


def mock_transport(engine: Research, monkeypatch: Any, invalid: bool = False) -> list[str]:
    sent: list[str] = []
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key-no-real-access")

    def send(self: Any, body: bytes, client_request_id: str) -> embeddings.EmbeddingHTTPResponse:
        assert engine.ledger.db.execute(
            "SELECT 1 FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.attempt')=?",
            (client_request_id,),
        ).fetchone()
        request = json.loads(body)
        assert body == canonical(request).encode()
        sent.append(client_request_id)
        vector = base64.b64encode(struct.pack("<ffff", 1.0, 0.0, 0.0, 0.0)).decode()
        payload = {
            "object": "list",
            "model": request["model"],
            "data": [
                {"object": "embedding", "index": 999 if invalid else index, "embedding": vector}
                for index in range(len(request["input"]))
            ],
            "usage": {
                "prompt_tokens": sum(len(text.encode()) for text in request["input"]),
                "total_tokens": sum(len(text.encode()) for text in request["input"]),
            },
        }
        return embeddings.EmbeddingHTTPResponse(
            json.dumps(payload).encode(), 200, "synthetic-request-" + client_request_id
        )

    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", send)
    return sent


def test_plan_is_offline_complete_and_retains_wire_inputs(embedding_plan: Any) -> None:
    engine, plan = embedding_plan
    assert plan["network_calls"] == plan["model_calls"] == 0
    assert plan["text_unavailable_records"] == 2
    manifest = engine.ledger.get(plan["id"], "embedding_plan")
    assert sum(item["chunks"] for item in manifest["items"]) == plan["expected_chunks"]
    assert sum(item["input_tokens"] for item in manifest["items"]) == plan["input_tokens"]
    for item in manifest["items"]:
        request = engine.ledger.artifacts.read(item["request_ref"])
        assert (
            engine.ledger.artifacts.read_bytes(request["wire_body_ref"])
            == canonical(request["body"]).encode()
        )
        assert len(request["body"]["input"]) <= 3
        assert request["instructions"] == []
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_paid_run_requires_online_mode_and_exact_approval(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    sent = mock_transport(engine, monkeypatch)
    with pytest.raises(ResearchError, match="offline"):
        run(engine, plan)
    engine.config = replace(engine.config, offline=False)
    with pytest.raises(ResearchError, match="approval"):
        run(engine, plan)
    assert sent == []


def test_embedding_results_resume_and_cache_without_repaying(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    sent = mock_transport(engine, monkeypatch)
    partial = run(engine, plan, policy, limit=1)
    assert partial["requests_sent"] == 1 and partial["missing_task_keys"]
    complete = run(engine, plan, policy)
    assert complete["completed_chunks"] == plan["expected_chunks"] and not complete["missing_task_keys"]
    assert len(sent) == plan["request_count"]
    repeated = run(engine, plan, policy)
    assert repeated["requests_sent"] == 0 and len(sent) == plan["request_count"]
    assert repeated["reserved_cost_usd"] == complete["reserved_cost_usd"]
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    for path in engine.ledger.artifacts.root.iterdir():
        assert b"synthetic-test-key-no-real-access" not in path.read_bytes()
    engine.execute("status", objective="Check durable embedding responses and attempts", actor="test")


def test_budget_does_not_send_an_unfunded_request(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    sent = mock_transport(engine, monkeypatch)
    result = run(engine, plan, approval(engine, plan, "0.000000001"))
    assert result["requests_sent"] == 0 and result["completed_chunks"] == 0
    assert len(result["missing_task_keys"]) == plan["request_count"]
    assert sent == []


def test_timeout_stays_unknown_and_blocks_retry(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    calls = []

    def timeout(*args: Any) -> Any:
        calls.append(True)
        raise TimeoutError("Potentially sensitive transport details must not be logged")

    monkeypatch.setattr(embeddings.OpenAIEmbeddingTransport, "send", timeout)
    with pytest.raises(ResearchError, match="unknown"):
        run(engine, plan, policy)
    with pytest.raises(ResearchError, match="unknown"):
        run(engine, plan, policy)
    assert calls == [True]
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert len(engine.ledger.unresolved) == 1


def test_invalid_vector_indices_are_retained_but_not_accepted(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    sent = mock_transport(engine, monkeypatch, invalid=True)
    result = run(engine, plan, approval(engine, plan))
    assert len(sent) == 1 and result["completed_chunks"] == 0
    assert result["items"][0]["status"] == "invalid"
    assert engine.ledger.db.execute("SELECT response_ref FROM attempts").fetchone()[0]
    assert (
        engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='embedding_result'").fetchone()[0]
        == 0
    )


def test_missing_prepared_wire_body_fails_preflight(embedding_plan: Any) -> None:
    engine, plan = embedding_plan
    item = engine.ledger.get(plan["id"], "embedding_plan")["items"][0]
    request = engine.ledger.artifacts.read(item["request_ref"])
    (engine.ledger.artifacts.root / request["wire_body_ref"]).unlink()
    with pytest.raises(AuditError, match="artifact is missing"):
        engine.execute("status", objective="Detect missing embedding payload", actor="test")


def test_tokenizer_rejects_missing_cache_without_download(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path / "absent"))
    with pytest.raises(ResearchError, match="Cache the verified"):
        embeddings.offline_tokenizer()


def test_transport_sends_exact_bytes_to_fixed_endpoint_without_redirects(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    body = b'{"input":["synthetic transport fixture"]}'
    calls = []

    class Response:
        status = 200
        headers = {"x-request-id": "synthetic-request-id"}

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def read(self) -> bytes:
            return b'{"synthetic":true}'

    class Opener:
        def open(self, request: Any, timeout: int) -> Response:
            calls.append(request)
            assert request.full_url == "https://api.openai.com/v1/embeddings"
            assert request.method == "POST" and request.data == body
            assert request.get_header("Authorization") == "Bearer synthetic-test-key"
            assert request.get_header("X-client-request-id") == "synthetic-client-id"
            assert timeout == 60
            return Response()

    def build_opener(handler: Any) -> Opener:
        assert handler is embeddings.NoRedirect
        return Opener()

    monkeypatch.setattr(embeddings.urllib.request, "build_opener", build_opener)
    response = embeddings.OpenAIEmbeddingTransport().send(body, "synthetic-client-id")
    assert len(calls) == 1 and response.request_id == "synthetic-request-id"
    assert response.body == b'{"synthetic":true}' and response.status == 200
    with pytest.raises(ResearchError, match="redirects"):
        embeddings.NoRedirect().redirect_request(None, None, 307, None, None, "https://example.test/")


def test_embedding_intent_failure_prevents_send(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    sent = mock_transport(engine, monkeypatch)
    append = engine.ledger.append

    def fail_intent(session: str, kind: str, *args: Any, **kwargs: Any) -> Any:
        if kind == "model.attempt.intended":
            raise AuditError("Synthetic audit failure")
        return append(session, kind, *args, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", fail_intent)
    with pytest.raises(AuditError, match="Synthetic audit"):
        run(engine, plan, policy)
    assert sent == []


def test_embedding_response_audit_failure_blocks_retry(embedding_plan: Any, monkeypatch: Any) -> None:
    engine, plan = embedding_plan
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    sent = mock_transport(engine, monkeypatch)
    append = engine.ledger.append

    def fail_response(session: str, kind: str, *args: Any, **kwargs: Any) -> Any:
        if kind == "embedding.response.received":
            raise AuditError("Synthetic response audit failure")
        return append(session, kind, *args, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", fail_response)
    with pytest.raises(AuditError, match="Synthetic response"):
        run(engine, plan, policy)
    monkeypatch.setattr(engine.ledger, "append", append)
    with pytest.raises(ResearchError, match="unknown"):
        run(engine, plan, policy)
    assert len(sent) == 1
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("vector", [[float("nan"), 1, 0, 0], [0, 0, 0, 0], [1, 0]])
def test_invalid_vector_values_or_dimensions(vector: list[float]) -> None:
    request = {"model": "synthetic-model", "chunks": [{}], "profile": {"dimensions": 4}}
    response = {
        "object": "list",
        "model": "synthetic-model",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": base64.b64encode(struct.pack("<" + "f" * len(vector), *vector)).decode(),
            }
        ],
        "usage": {"prompt_tokens": 1, "total_tokens": 1},
    }
    with pytest.raises(ResearchError, match="vector_invalid"):
        embeddings.validate_response(request, response)
