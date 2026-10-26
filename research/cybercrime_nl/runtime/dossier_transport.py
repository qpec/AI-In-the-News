"""Bounded provider transport; caller must use the shared audited gateway."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
import threading
import urllib.error
import urllib.request

from newsresearch.common import ResearchError, canonical, digest, require_no_credentials
from newsresearch.embeddings import NoRedirect
from newsresearch.gateway import ProviderResponse

ORIGIN = "https://api.openai.com"
PATHS = {"decisions": "/v1/decisions", "responses": "/v1/responses", "embeddings": "/v1/embeddings"}
MAX_REQUEST_BYTES = 2_097_152
MAX_RESPONSE_BYTES = 16_777_216


@dataclass(frozen=True)
class Invocation:
    request: dict
    client_id: str
    kind: str = "decisions"

    def manifest(self):
        if self.kind not in PATHS or not isinstance(self.client_id, str) or not self.client_id or any(c in self.client_id for c in "\r\n"):
            raise ResearchError("dossier_invocation_invalid")
        return {"transport": "openai-dossier-http-v1", "kind": self.kind,
                "url": ORIGIN + PATHS[self.kind], "method": "POST", "wire_sha256": digest(self.request),
                "client_id": self.client_id, "automatic_retries": 0,
                "timeout_seconds": 120, "max_response_bytes": MAX_RESPONSE_BYTES}


class UnifiedTransport:
    """No retries/redirects; authentication is never included in retained metadata."""
    def __init__(self, before_dispatch=None, opener=None):
        self.before_dispatch = before_dispatch
        self.opener = opener
        self._dispatch_lock = threading.Lock()

    def complete_prepared(self, invocation):
        manifest = invocation.manifest()
        require_no_credentials(invocation.request)
        model = invocation.request.get("model")
        expected = {"decisions": {"gpt-6-luna"}, "responses": {"gpt-6-luna", "gpt-6-astra"},
                    "embeddings": {"text-embedding-3-large"}}
        if model not in expected[invocation.kind]:
            raise ResearchError("dossier_transport_model_invalid")
        key = os.environ.get("OPENAI_API_KEY")
        if not key or any(c in key for c in "\r\n"):
            raise ResearchError("dossier_key_unavailable")
        wire = canonical(invocation.request).encode("utf-8")
        if len(wire) > MAX_REQUEST_BYTES:
            raise ResearchError("dossier_request_byte_capacity")
        request = urllib.request.Request(manifest["url"], data=wire, method="POST", headers={
            "Authorization": "Bearer " + key, "Content-Type": "application/json",
            "X-Client-Request-Id": invocation.client_id})
        opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        response, started = None, False
        try:
            if self.before_dispatch is not None:
                with self._dispatch_lock:
                    if self.before_dispatch(invocation) is False:
                        raise ResearchError("dossier_dispatch_stopped")
            started = True
            try:
                response = opener.open(request, timeout=120)
            except urllib.error.HTTPError as error:
                response = error
            status = response.status
            if type(status) is not int:
                raise ResearchError("dossier_http_status_unavailable")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ResearchError("dossier_response_byte_capacity")
            text = raw.decode("utf-8")
            require_no_credentials(text)
            # Retain safe non-JSON response text too; its billing remains unknown.
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = None
            if payload is not None and not isinstance(payload, dict):
                payload = None
            metadata = {"http_status": status, "response_text": text, "kind": invocation.kind,
                        "unknown_outcome": status >= 500 or payload is None, "dispatch_started": True}
            return ProviderResponse(payload if status == 200 else None, "openai-" + invocation.kind,
                                    payload.get("model") if payload else None,
                                    response.headers.get("x-request-id"),
                                    payload.get("usage") if status == 200 and payload else None, metadata)
        except Exception as error:
            return ProviderResponse(None, "openai-" + invocation.kind, None, raw_response={
                "unknown_outcome": started, "dispatch_started": started, "error_type": type(error).__name__,
                "kind": invocation.kind})
        finally:
            if response is not None:
                response.close()


def usage_metadata(kind, usage, *, model="gpt-6-luna"):
    """Validate observed counters and return a conservative price upper estimate.

    No invoice claim. Responses input is reserved at cache-write price, including
    10% regional margin; Decisions no-cache input and embeddings use standard
    input plus 10%. Missing/invalid usage raises; the caller preserves its hold.
    """
    if kind not in PATHS or not isinstance(usage, dict):
        raise ResearchError("dossier_usage_missing")
    input_key = "prompt_tokens" if kind == "embeddings" else "input_tokens"
    inputs = usage.get(input_key)
    outputs = usage.get("output_tokens", 0) if kind == "responses" else 0
    if type(inputs) is not int or inputs < 0 or type(outputs) is not int or outputs < 0:
        raise ResearchError("dossier_usage_invalid")
    if kind == "responses" and "output_tokens" not in usage:
        raise ResearchError("dossier_output_usage_missing")
    details = usage.get("input_tokens_details") or {}
    if not isinstance(details, dict):
        raise ResearchError("dossier_usage_details_invalid")
    cached, writes = details.get("cached_tokens", 0), details.get("cache_write_tokens", 0)
    if any(type(n) is not int or n < 0 for n in (cached, writes)) or cached + writes > inputs:
        raise ResearchError("dossier_cache_usage_invalid")
    if kind == "decisions" and (cached or writes):
        raise ResearchError("dossier_explicit_no_cache_usage_conflict")
    if kind == "embeddings":
        rate, output_rate = 143, 0
    elif model == "gpt-6-astra":
        rate, output_rate = 13_750, 55_000
    else:
        rate, output_rate = (110 if kind == "decisions" else 137.5), 550
    return {"input_tokens": inputs, "output_tokens": outputs, "cached_tokens": cached,
            "cache_write_tokens": writes, "cost_nanousd_upper": math.ceil(inputs * rate + outputs * output_rate),
            "price_basis": "2026-10-23 local registered prices; 10% margin and Responses all-input cache-write upper rate",
            "is_provider_invoice": False}
