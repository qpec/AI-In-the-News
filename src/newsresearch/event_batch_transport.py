"""One-shot, fixed-origin OpenAI Batch HTTP transport.

This module does not authorize, schedule, audit or accept research. Only an
audited gateway may call ``perform`` after retaining its exact request and
durable intent. There are no SDK retries, fallback endpoints or model calls
outside uploaded Batch files. Count requests also disclose evidence and need
their own retained intent. Unknown writes must be reconciled, never retried.

The saved Windows credential is injected into this process by the existing
``scripts/windows_key_store.cs`` wrapper; this module reads OPENAI_API_KEY only.
Authentication headers are never part of returned or prepared audit objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import os
import re
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request

from .common import Json, ResearchError, canonical, require_no_credentials

ORIGIN = "https://api.openai.com"
MODEL = "gpt-6-luna"
MAX_UPLOAD_BYTES = 200_000_000
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_FILE_ID = re.compile(r"file[-_][A-Za-z0-9_-]{1,128}\Z")
_BATCH_ID = re.compile(r"batch_[A-Za-z0-9_-]{1,128}\Z")
_OVERRIDES = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_HOST", "OPENAI_ENDPOINT",
              "AZURE_OPENAI_ENDPOINT", "OPENAI_ORG_ID", "OPENAI_ORGANIZATION", "OPENAI_PROJECT_ID")
_SAFE_HEADERS = frozenset({"x-request-id", "x-client-request-id", "date", "content-type",
                           "content-length", "retry-after", "openai-processing-ms", "openai-version"})
_COUNT_KEYS = frozenset({"model", "instructions", "input", "text"})
_INFERENCE_KEYS = frozenset({"max_output_tokens", "temperature", "top_p", "reasoning", "store",
    "background", "metadata", "service_tier", "stream", "stream_options", "user", "safety_identifier",
    "prompt_cache_key", "prompt_cache_retention", "include", "truncation"})


@dataclass(frozen=True)
class PreparedBatchRequest:
    """Exact permitted HTTP representation, deliberately excluding authentication."""

    method: str
    url: str
    body: bytes | None
    headers: dict[str, str]


@dataclass(frozen=True)
class BatchReceipt:
    """Raw permitted receipt. ``body=None`` is missing evidence, never empty success."""

    body: bytes | None
    status: int | None
    request_id: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    error_type: str | None = None
    unknown: bool = False
    retention_error: str | None = None
    body_sha256: str | None = None


class NoBatchRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any,
                         headers: Any, newurl: Any) -> None:
        # Returning None makes urllib raise HTTPError with the original receipt;
        # the redirected destination never receives evidence or credentials.
        return None


def _object(raw: bytes) -> Json:
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, TypeError):
        raise ResearchError("batch_transport_invalid_json") from None
    if not isinstance(value, dict):
        raise ResearchError("batch_transport_json_object_required")
    require_no_credentials(value)
    return value


def _safe_raw(raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    require_no_credentials(text)
    # JSON keys require the structured credential guard too. Batch downloads
    # are JSONL; preserve original bytes rather than reserialize/redact them.
    try:
        parsed = json.loads(text)
    except ValueError:
        for line in text.splitlines():
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            require_no_credentials(parsed)
    else:
        require_no_credentials(parsed)


def count_request_body(responses_body: Mapping[str, Any]) -> Json:
    """Pure count payload; caller must retain it before sending source evidence.

    Copy the exact model, instructions, input and structured-output schema.
    Only known inference-only parameters are omitted; unknown/tool/context
    parameters fail closed instead of silently undercounting input.
    """
    if (set(responses_body) - _COUNT_KEYS - _INFERENCE_KEYS
            or responses_body.get("model") != MODEL
            or not isinstance(responses_body.get("instructions"), str)
            or not isinstance(responses_body.get("input"), (str, list))
            or not isinstance(responses_body.get("text"), dict)):
        raise ResearchError("batch_count_request_contract_invalid")
    require_no_credentials(dict(responses_body))
    # Round-trip gives a detached copy without changing strings or schema.
    return json.loads(canonical({key: responses_body[key] for key in _COUNT_KEYS}))


def _validate_upload(raw: bytes) -> None:
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ResearchError("batch_upload_size_invalid")
    customs: set[str] = set()
    count = 0
    for line in raw.splitlines():
        if not line.strip():
            raise ResearchError("batch_upload_blank_line")
        row = _object(line)
        body = row.get("body")
        custom = row.get("custom_id")
        if (set(row) != {"custom_id", "method", "url", "body"}
                or not isinstance(custom, str) or not _ID.fullmatch(custom) or custom in customs
                or row.get("method") != "POST" or row.get("url") != "/v1/responses"
                or not isinstance(body, dict) or body.get("model") != MODEL
                or any(key in body for key in ("tools", "conversation", "previous_response_id"))):
            raise ResearchError("batch_upload_request_contract_invalid")
        customs.add(custom)
        count += 1
    if count > 50_000:
        raise ResearchError("batch_upload_request_count_invalid")


def prepare_request(request: Json, body: bytes | None, client_request_id: str) -> PreparedBatchRequest:
    """Pure deterministic HTTP construction for pre-dispatch provenance."""
    require_no_credentials(request)
    if not isinstance(client_request_id, str) or not _ID.fullmatch(client_request_id):
        raise ResearchError("batch_client_request_id_invalid")
    method, path = request.get("method"), request.get("path")
    if method not in {"POST", "GET"} or not isinstance(path, str):
        raise ResearchError("batch_transport_route_invalid")
    headers = {"X-Client-Request-Id": client_request_id}
    allowed = {"method", "path"}
    suffix = ""
    if method == "POST" and path == "/v1/responses/input_tokens":
        if not isinstance(body, bytes) or set(_object(body)) != _COUNT_KEYS:
            raise ResearchError("batch_count_body_invalid")
        count_request_body(_object(body))
        headers["Content-Type"] = "application/json"
    elif method == "POST" and path == "/v1/files":
        allowed |= {"purpose", "filename", "content_sha256"}
        filename = request.get("filename")
        if (not isinstance(body, bytes) or request.get("purpose") != "batch"
                or not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\.jsonl", filename)
                or request.get("content_sha256") != hashlib.sha256(body).hexdigest()):
            raise ResearchError("batch_upload_descriptor_invalid")
        _validate_upload(body)
        boundary = "newsresearch-" + hashlib.sha256((client_request_id + request["content_sha256"]).encode()).hexdigest()
        prefix = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
                  f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                  "Content-Type: application/jsonl\r\n\r\n").encode()
        body = prefix + body + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = "multipart/form-data; boundary=" + boundary
    elif method == "POST" and path == "/v1/batches":
        if not isinstance(body, bytes):
            raise ResearchError("batch_create_body_invalid")
        value = _object(body)
        metadata = value.get("metadata", {})
        if (set(value) - {"input_file_id", "endpoint", "completion_window", "metadata"}
                or not isinstance(value.get("input_file_id"), str) or not _FILE_ID.fullmatch(value["input_file_id"])
                or value.get("endpoint") != "/v1/responses" or value.get("completion_window") != "24h"
                or not isinstance(metadata, dict) or len(metadata) > 16
                or any(not isinstance(k, str) or len(k) > 64 or not isinstance(v, str) or len(v) > 512
                       for k, v in metadata.items())):
            raise ResearchError("batch_create_body_invalid")
        headers["Content-Type"] = "application/json"
    elif method == "GET" and path == "/v1/batches":
        allowed.add("query")
        query = request.get("query", {"limit": 100})
        if (not isinstance(query, dict) or set(query) - {"limit", "after"}
                or type(query.get("limit", 100)) is not int or not 1 <= query.get("limit", 100) <= 100
                or ("after" in query and (not isinstance(query["after"], str) or not _BATCH_ID.fullmatch(query["after"])))):
            raise ResearchError("batch_list_query_invalid")
        suffix = "?" + urllib.parse.urlencode(sorted({"limit": 100, **query}.items()))
    elif method == "GET" and path.startswith("/v1/batches/"):
        allowed.add("job_id")
        job = path.removeprefix("/v1/batches/")
        if not _BATCH_ID.fullmatch(job) or request.get("job_id", job) != job:
            raise ResearchError("batch_retrieve_id_invalid")
    elif method == "GET" and path.startswith("/v1/files/") and path.endswith("/content"):
        allowed.add("file_id")
        file_id = path.removeprefix("/v1/files/").removesuffix("/content")
        if not _FILE_ID.fullmatch(file_id) or request.get("file_id", file_id) != file_id:
            raise ResearchError("batch_download_id_invalid")
    else:
        raise ResearchError("batch_transport_route_invalid")
    if set(request) - allowed or (method == "GET" and body is not None):
        raise ResearchError("batch_transport_unexpected_parameter")
    if body is not None:
        _safe_raw(body)
    return PreparedBatchRequest(method, ORIGIN + path + suffix, body, headers)


class OpenAIBatchTransport:
    """Single HTTP attempt only. The caller owns all durable intent/retention."""

    synthetic = False
    max_retries = 0

    def __init__(self, *, timeout_seconds: float = 60, max_response_bytes: int = 16 * 1024 * 1024,
                 max_download_bytes: int = 256 * 1024 * 1024, opener: Any = None) -> None:
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300
                or type(max_response_bytes) is not int or max_response_bytes < 1
                or type(max_download_bytes) is not int or max_download_bytes < 1):
            raise ResearchError("batch_transport_limits_invalid")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_download_bytes = max_download_bytes
        # An injected opener exists only for deterministic synthetic tests.
        self._opener = opener

    def perform(self, request: Json, body: bytes | None, client_request_id: str) -> BatchReceipt:
        prepared = prepare_request(request, body, client_request_id)
        if any(os.environ.get(name) for name in _OVERRIDES):
            raise ResearchError("batch_transport_environment_override_forbidden")
        key = os.environ.get("OPENAI_API_KEY")
        if not key or key.strip() != key or "\r" in key or "\n" in key:
            raise ResearchError("batch_transport_api_key_unavailable")
        wire = urllib.request.Request(prepared.url, data=prepared.body, method=prepared.method,
                                      headers={**prepared.headers, "Authorization": "Bearer " + key})
        opener = self._opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoBatchRedirect())
        mutation = prepared.method == "POST" and prepared.url != ORIGIN + "/v1/responses/input_tokens"
        limit = self.max_download_bytes if request["path"].endswith("/content") else self.max_response_bytes
        try:
            response = opener.open(wire, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        except Exception as error:
            # Exception messages may contain credentials, URLs or evidence.
            return BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)
        status = getattr(response, "status", None) or getattr(response, "code", None)
        headers: dict[str, str] = {}
        raw: bytes | None = None
        try:
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()
                       if str(k).lower() in _SAFE_HEADERS or str(k).lower().startswith("x-ratelimit-")}
            require_no_credentials(headers)
            raw = response.read(limit + 1)
            if len(raw) > limit:
                return BatchReceipt(None, status, headers.get("x-request-id"), headers,
                                    "response_byte_limit", mutation, "response_byte_limit")
            try:
                _safe_raw(raw)
            except ResearchError:
                return BatchReceipt(None, status, headers.get("x-request-id"), headers,
                                    "response_retention_forbidden", mutation, "credential_guard",
                                    hashlib.sha256(raw).hexdigest())
            return BatchReceipt(raw, status, headers.get("x-request-id"), headers,
                                "http_error" if status is None or not 200 <= status < 300 else None,
                                mutation and (status is None or status >= 500),
                                body_sha256=hashlib.sha256(raw).hexdigest())
        except ResearchError:
            # Even a provider-supplied header can contain prohibited content.
            return BatchReceipt(None, status, error_type="response_retention_forbidden", unknown=mutation,
                                retention_error="credential_guard")
        except Exception as error:
            return BatchReceipt(None, status, headers.get("x-request-id"), headers,
                                type(error).__name__, mutation, "response_read_failed")
        finally:
            response.close()
