"""Transport tests use fake openers only; no network or research owner access."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_transport as t  # noqa: E402
from newsresearch.common import ResearchError, canonical, digest  # noqa: E402


class Response:
    status = 200
    headers = {"x-request-id": "fake-receipt"}

    def __init__(self, value):
        self.raw = value
        self.closed = False

    def read(self, count):
        return self.raw[:count]

    def close(self):
        self.closed = True


class Opener:
    def __init__(self, raw):
        self.calls = []
        self.response = Response(raw)

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        return self.response


def test_all_endpoints_exact_wire_receipt_and_no_auth_retention(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-only")
    for kind in t.PATHS:
        model = "text-embedding-3-large" if kind == "embeddings" else "gpt-6-luna"
        body = {"model": model, "input": [[1, 2, 3]] if kind == "embeddings" else "synthetic"}
        invocation = t.Invocation(body, "request-1", kind)
        opener = Opener(json.dumps({"model": model, "usage": {"input_tokens": 3}}).encode())
        calls = []
        result = t.UnifiedTransport(lambda call: calls.append(call), opener).complete_prepared(invocation)
        assert calls == [invocation]
        assert opener.calls[0][0].data == canonical(body).encode()
        assert opener.calls[0][0].full_url == t.ORIGIN + t.PATHS[kind]
        assert invocation.manifest()["wire_sha256"] == digest(body)
        assert invocation.manifest()["kind"] == kind
        assert result.request_id == "fake-receipt"
        assert "synthetic-test-only" not in canonical(result.raw_response)
        assert opener.response.closed


def test_stop_before_http_is_not_an_unknown_dispatch(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-only")
    opener = Opener(b"{}")

    def stopped(invocation):
        assert invocation.kind == "decisions"
        raise ResearchError("stop_requested")

    result = t.UnifiedTransport(stopped, opener).complete_prepared(t.Invocation({"model": "gpt-6-luna"}, "id"))
    assert opener.calls == []
    assert result.raw_response["dispatch_started"] is False
    assert result.raw_response["unknown_outcome"] is False


def test_safe_non_json_saved_without_retry(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-only")
    opener = Opener(b"temporary service message")
    result = t.UnifiedTransport(opener=opener).complete_prepared(t.Invocation({"model": "gpt-6-luna"}, "id"))
    assert len(opener.calls) == 1
    assert result.payload is None
    assert result.raw_response["response_text"] == "temporary service message"
    assert result.raw_response["unknown_outcome"] is True


def test_large_embedding_responses_and_usage_accounting(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-only")
    raw = json.dumps({"model": "text-embedding-3-large", "data": "x" * 8_500_000}).encode()
    opener = Opener(raw)
    result = t.UnifiedTransport(opener=opener).complete_prepared(t.Invocation(
        {"model": "text-embedding-3-large", "dimensions": 1536, "input": [[1]], "encoding_format": "float"}, "id", "embeddings"))
    assert len(result.payload["data"]) == 8_500_000
    assert t.usage_metadata("decisions", {"input_tokens": 1000})["cost_nanousd_upper"] == 110_000
    assert t.usage_metadata("responses", {"input_tokens": 1000, "output_tokens": 100})["cost_nanousd_upper"] == 192_500
    assert t.usage_metadata("responses", {"input_tokens": 1000, "output_tokens": 100}, model="gpt-6-astra")["cost_nanousd_upper"] == 19_250_000


@pytest.mark.parametrize("kind,usage", [("decisions", {}), ("responses", {"input_tokens": 5}),
    ("decisions", {"input_tokens": 5, "input_tokens_details": {"cache_write_tokens": 1}}),
    ("embeddings", {"prompt_tokens": True})])
def test_missing_or_conflicting_usage_requires_existing_hold(kind, usage):
    with pytest.raises(ResearchError):
        t.usage_metadata(kind, usage)
