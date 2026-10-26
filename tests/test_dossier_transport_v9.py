"""Exact-wire, no-retry transport and fixed safe failure metadata."""
from io import BytesIO
import json
from pathlib import Path
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import dossier_transport_v9 as transport  # noqa: E402
from newsresearch.common import ResearchError, canonical  # noqa: E402


class Response(BytesIO):
    def __init__(self, body, status=200):
        super().__init__(body)
        self.status, self.headers = status, {"x-request-id": "synthetic-id"}


class Opener:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def open(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return self.response


def invocation():
    return transport.original.Invocation({"model": "gpt-6-luna", "input": "Exact synthetic content",
                                          "max_output_tokens": 2000}, "synthetic-id", "responses")


def test_exact_wire_headers_timeout_and_payload_equal_original(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    payload = {"model": "gpt-6-luna", "status": "completed", "usage": {"input_tokens": 3, "output_tokens": 2}}
    body = json.dumps(payload).encode()
    old, new = Opener(Response(body)), Opener(Response(body))
    old_reply = transport.original.UnifiedTransport(opener=old).complete_prepared(invocation())
    new_reply = transport.UnifiedTransport(opener=new).complete_prepared(invocation())
    a, b = old.calls[0], new.calls[0]
    assert a[0].data == b[0].data == canonical(invocation().request).encode()
    assert a[0].full_url == b[0].full_url and a[0].headers == b[0].headers and a[1] == b[1] == 120
    assert new_reply.payload == old_reply.payload and new_reply.usage == old_reply.usage
    extra = {"observability_version", "failure_stage", "failure_code"}
    assert {k: v for k, v in new_reply.raw_response.items() if k not in extra} == old_reply.raw_response


@pytest.mark.parametrize("kind,stage,code", [
    ("url", "open", "network_url_error"), ("timeout", "open", "network_timeout"),
    ("redirect", "open", "redirect_rejected"), ("status", "status", "http_status_unavailable"),
    ("size", "read", "response_byte_capacity"), ("decode", "decode", "response_decode_failed"),
    ("credential", "response_credentials", "response_content_rejected"),
])
def test_failures_preserve_unknown_without_exception_message_or_rejected_body(monkeypatch, kind, stage, code):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    marker = "UNLOGGABLE private error or response content"
    response, error = Response(b"{}"), None
    if kind == "url":
        error = urllib.error.URLError(marker)
    elif kind == "timeout":
        error = TimeoutError(marker)
    elif kind == "redirect":
        error = transport.FixedFailure("redirect_rejected")
    elif kind == "status":
        response = Response(b"{}", marker)
    elif kind == "size":
        monkeypatch.setattr(transport.original, "MAX_RESPONSE_BYTES", 2)
        response = Response(marker.encode())
    elif kind == "decode":
        response = Response(b"\xff")
    elif kind == "credential":
        response = Response(marker.encode())
        original = transport.require_no_credentials
        def guard(value):
            if isinstance(value, str):
                raise ResearchError(marker)
            return original(value)
        monkeypatch.setattr(transport, "require_no_credentials", guard)
    opener = Opener(response, error)
    result = transport.UnifiedTransport(opener=opener).complete_prepared(invocation())
    assert len(opener.calls) == 1 and result.payload is result.model is result.usage is None
    assert result.raw_response["unknown_outcome"] and result.raw_response["dispatch_started"]
    assert result.raw_response["failure_stage"] == stage and result.raw_response["failure_code"] == code
    assert marker not in canonical(result.raw_response) and "response_text" not in result.raw_response


@pytest.mark.parametrize("kind", ["stop", "key", "request_guard"])
def test_pre_dispatch_rejection_does_not_call_http_or_expose_credentials(monkeypatch, kind):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    if kind == "key":
        monkeypatch.delenv("OPENAI_API_KEY")
    elif kind == "request_guard":
        monkeypatch.setattr(transport, "require_no_credentials", lambda _: (_ for _ in ()).throw(ResearchError("UNLOGGABLE")))
    opener = Opener(Response(b"{}"))
    result = transport.UnifiedTransport(opener=opener, before_dispatch=lambda _: False if kind == "stop" else True).complete_prepared(invocation())
    assert not opener.calls and not result.raw_response["dispatch_started"] and not result.raw_response["unknown_outcome"]
    assert result.raw_response["failure_code"] in {"dispatch_stopped", "request_preflight_rejected"}
    assert "UNLOGGABLE" not in canonical(result.raw_response)


def test_redirect_handler_never_forwards_url_or_exception_text():
    with pytest.raises(transport.FixedFailure, match="^redirect_rejected$"):
        transport.NoRedirect().redirect_request(None, None, 302, "UNLOGGABLE", None, "https://private.invalid/?secret=UNLOGGABLE")
