"""Synthetic HTTP cases only; no credentials, protected stores or live service."""
from __future__ import annotations

import hashlib
from email.message import Message
from io import BytesIO
import json
from typing import Any
import urllib.error

import pytest

from newsresearch.common import ResearchError, canonical
from newsresearch.event_batch_transport import (
    MODEL, ORIGIN, NoBatchRedirect, OpenAIBatchTransport, count_request_body, prepare_request,
)


def response_body() -> dict[str, Any]:
    return {"model": MODEL, "instructions": "Synthetic fixture only.",
            "input": [{"role": "user", "content": "Synthetic article."}],
            "text": {"format": {"type": "json_schema", "name": "fixture", "strict": True,
                                "schema": {"type": "object", "properties": {}, "additionalProperties": False}}},
            "max_output_tokens": 256, "reasoning": {"effort": "low"}, "store": False}


def create_body() -> bytes:
    return canonical({"input_file_id": "file-fixture", "endpoint": "/v1/responses",
                      "completion_window": "24h", "metadata": {"plan": "fixture-plan"}}).encode()


class FakeResponse:
    def __init__(self, raw: bytes = b'{"id":"batch_fixture"}', status: int = 200,
                 headers: dict[str, str] | None = None, read_error: Exception | None = None) -> None:
        self.raw, self.status = raw, status
        self.headers = headers or {"x-request-id": "req-fixture", "content-type": "application/json"}
        self.read_error = read_error
        self.closed = False

    def read(self, limit: int) -> bytes:
        if self.read_error:
            raise self.read_error
        return self.raw[:limit]

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[tuple[Any, float]] = []

    def open(self, request: Any, *, timeout: float) -> Any:
        self.calls.append((request, timeout))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-placeholder")
    for name in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_HOST", "OPENAI_ENDPOINT",
                 "AZURE_OPENAI_ENDPOINT", "OPENAI_ORG_ID", "OPENAI_ORGANIZATION", "OPENAI_PROJECT_ID"):
        monkeypatch.delenv(name, raising=False)


def test_count_preserves_exact_model_evidence_instructions_and_schema() -> None:
    original = response_body()
    count = count_request_body(original)
    assert set(count) == {"model", "instructions", "input", "text"}
    assert all(count[key] == original[key] for key in count)
    count["text"]["format"]["name"] = "changed"
    assert original["text"]["format"]["name"] == "fixture"
    prepared = prepare_request({"method": "POST", "path": "/v1/responses/input_tokens"},
                               canonical(count).encode(), "count-fixture")
    assert prepared.url == ORIGIN + "/v1/responses/input_tokens"
    assert json.loads(prepared.body or b"null") == count
    assert "Authorization" not in prepared.headers


@pytest.mark.parametrize("extra", [{"tools": []}, {"previous_response_id": "resp_1"},
                                  {"conversation": "conv_1"}, {"unrecognized": "value"},
                                  {"model": "another-model"}])
def test_count_rejects_unsupported_or_changed_input(extra: dict[str, Any]) -> None:
    with pytest.raises(ResearchError):
        count_request_body({**response_body(), **extra})


def test_upload_preparation_deterministic_and_fixed_model() -> None:
    line = canonical({"custom_id": "fixture-1", "method": "POST", "url": "/v1/responses",
                      "body": response_body()}).encode() + b"\n"
    request = {"method": "POST", "path": "/v1/files", "purpose": "batch", "filename": "fixture.jsonl",
               "content_sha256": hashlib.sha256(line).hexdigest()}
    first = prepare_request(request, line, "upload-fixture")
    assert first == prepare_request(request, line, "upload-fixture")
    assert first.body is not None and line in first.body
    assert b'name="purpose"\r\n\r\nbatch\r\n' in first.body
    assert first.url == ORIGIN + "/v1/files"
    assert first.headers["Content-Type"].startswith("multipart/form-data; boundary=newsresearch-")
    with pytest.raises(ResearchError, match="descriptor"):
        prepare_request({**request, "content_sha256": "different"}, line, "upload-fixture")
    with pytest.raises(ResearchError, match="descriptor"):
        prepare_request({**request, "filename": "../../outside.jsonl"}, line, "upload-fixture")


@pytest.mark.parametrize("kind", ["wrong_model", "duplicate", "tools", "blank", "wrong_endpoint"])
def test_upload_rejects_contract_violation(kind: str) -> None:
    row = {"custom_id": "fixture-1", "method": "POST", "url": "/v1/responses", "body": response_body()}
    if kind == "wrong_model":
        row["body"]["model"] = "another-model"  # type: ignore[index]
    elif kind == "tools":
        row["body"]["tools"] = []  # type: ignore[index]
    elif kind == "wrong_endpoint":
        row["url"] = "/v1/chat/completions"
    raw = canonical(row).encode() + b"\n"
    raw = raw + raw if kind == "duplicate" else raw
    raw = raw + b"\n" if kind == "blank" else raw
    request = {"method": "POST", "path": "/v1/files", "purpose": "batch", "filename": "fixture.jsonl",
               "content_sha256": hashlib.sha256(raw).hexdigest()}
    with pytest.raises(ResearchError):
        prepare_request(request, raw, "fixture")


def test_create_and_get_routes() -> None:
    assert prepare_request({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture").body == create_body()
    assert prepare_request({"method": "GET", "path": "/v1/batches", "query": {"after": "batch_previous", "limit": 17}},
                           None, "fixture").url == ORIGIN + "/v1/batches?after=batch_previous&limit=17"
    for path in ("/v1/batches/batch_fixture", "/v1/files/file-fixture/content"):
        assert prepare_request({"method": "GET", "path": path}, None, "fixture").url == ORIGIN + path


@pytest.mark.parametrize("descriptor", [
    {"method": "POST", "path": "/v1/responses"},
    {"method": "GET", "path": "https://evil.example/v1/batches"},
    {"method": "GET", "path": "/v1/batches/batch_x/../../files"},
    {"method": "GET", "path": "/v1/batches/batch_x?limit=10"},
    {"method": "GET", "path": "/v1/batches/batch_x", "job_id": "batch_y"},
    {"method": "GET", "path": "/v1/files/file-x/content", "file_id": "file-y"},
    {"method": "GET", "path": "/v1/batches", "query": {"limit": 101}},
    {"method": "GET", "path": "/v1/batches", "query": {"status": "in_progress"}},
    {"method": "GET", "path": "/v1/batches", "base_url": "https://evil.example"},
])
def test_routes_fail_closed_without_dispatch(descriptor: dict[str, Any]) -> None:
    opener = FakeOpener(FakeResponse())
    with pytest.raises(ResearchError):
        OpenAIBatchTransport(opener=opener).perform(descriptor, None, "fixture")
    assert not opener.calls


def test_exact_permitted_receipt_and_authentication_not_returned() -> None:
    response = FakeResponse(headers={"X-Request-ID": "req-fixture", "Date": "Sat, 17 Oct 2026 12:00:00 GMT",
                                    "Set-Cookie": "unretained", "x-ratelimit-remaining-tokens": "42"})
    opener = FakeOpener(response)
    receipt = OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert len(opener.calls) == 1
    wire, timeout = opener.calls[0]
    assert wire.full_url == ORIGIN + "/v1/batches" and timeout == 60
    assert wire.get_header("Authorization") == "Bearer synthetic-key-placeholder"
    assert receipt.body == response.raw and receipt.status == 200 and not receipt.unknown
    assert receipt.request_id == "req-fixture"
    assert receipt.body_sha256 == hashlib.sha256(response.raw).hexdigest()
    assert "set-cookie" not in receipt.headers and "Authorization" not in repr(receipt)
    assert "synthetic-key-placeholder" not in repr(receipt)
    assert response.closed


@pytest.mark.parametrize("status,unknown", [(429, False), (400, False), (500, True), (503, True), (302, False)])
def test_http_errors_retained_without_retry(status: int, unknown: bool) -> None:
    raw = b'{"error":{"code":"synthetic-error"}}'
    headers = Message()
    headers["x-request-id"] = "req-error"
    error = urllib.error.HTTPError(ORIGIN + "/v1/batches", status, "synthetic", headers, BytesIO(raw))
    opener = FakeOpener(error)
    receipt = OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert len(opener.calls) == 1 and receipt.status == status and receipt.body == raw
    assert receipt.error_type == "http_error" and receipt.unknown is unknown


def test_timeout_is_unknown_and_never_retried_or_logged_as_text() -> None:
    opener = FakeOpener(TimeoutError("Bearer do-not-log"))
    receipt = OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert len(opener.calls) == 1 and receipt.body is None and receipt.status is None and receipt.unknown
    assert receipt.error_type == "TimeoutError" and "do-not-log" not in repr(receipt)


@pytest.mark.parametrize("raw", [b'{"authorization":"forbidden"}', b'{"text":"Bearer forbidden"}',
                               b'{"ok":1}\n{"password":"forbidden"}\n'])
def test_prohibited_receipt_is_omitted_not_redacted_or_success(raw: bytes) -> None:
    opener = FakeOpener(FakeResponse(raw))
    receipt = OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert len(opener.calls) == 1 and receipt.body is None and receipt.unknown
    assert receipt.retention_error == "credential_guard" and receipt.body_sha256 == hashlib.sha256(raw).hexdigest()


def test_oversized_receipt_and_failed_read_remain_unknown() -> None:
    for response in (FakeResponse(b"x" * 11), FakeResponse(read_error=OSError("do-not-log"))):
        opener = FakeOpener(response)
        receipt = OpenAIBatchTransport(opener=opener, max_response_bytes=10).perform(
            {"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
        assert receipt.body is None and receipt.unknown and receipt.retention_error
        assert len(opener.calls) == 1 and response.closed and "do-not-log" not in repr(receipt)


def test_header_retention_failure_omits_prohibited_header() -> None:
    opener = FakeOpener(FakeResponse(headers={"x-request-id": "Bearer forbidden"}))
    receipt = OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert receipt.body is None and receipt.request_id is None and receipt.headers == {}
    assert receipt.retention_error == "credential_guard" and receipt.unknown


def test_count_and_list_are_one_shot_and_not_inference_or_auto_pagination() -> None:
    for request, raw in [({"method": "POST", "path": "/v1/responses/input_tokens"}, canonical(count_request_body(response_body())).encode()),
                         ({"method": "GET", "path": "/v1/batches"}, None)]:
        opener = FakeOpener(FakeResponse(b'{"input_tokens":42,"has_more":true}'))
        receipt = OpenAIBatchTransport(opener=opener).perform(request, raw, "fixture")
        assert receipt.status == 200 and not receipt.unknown and len(opener.calls) == 1


def test_missing_key_and_endpoint_override_fail_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    opener = FakeOpener(FakeResponse())
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ResearchError, match="key_unavailable"):
        OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key-placeholder")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://evil.example")
    with pytest.raises(ResearchError, match="override_forbidden"):
        OpenAIBatchTransport(opener=opener).perform({"method": "POST", "path": "/v1/batches"}, create_body(), "fixture")
    assert not opener.calls


def test_redirect_handler_never_authorizes_redirect() -> None:
    NoBatchRedirect().redirect_request(None, None, 302, "redirect", {}, "https://evil.example")
