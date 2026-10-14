"""Audited OpenAI embedding plans and a bounded transport used only by the shared gateway."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import TYPE_CHECKING, Any
import urllib.error
import urllib.request
import uuid

import tiktoken

from .common import (
    AuditError,
    Context,
    Json,
    ResearchError,
    canonical,
    digest,
    require_active,
    require_no_credentials,
    utc,
)

if TYPE_CHECKING:
    from .runtime import Research

VOCAB_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
VOCAB_HASH = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
ENDPOINT = "https://api.openai.com/v1/embeddings"
PROFILE = {
    "method": "openai-embedding-candidates-v1",
    "provider": "openai",
    "model": "text-embedding-3-large",
    "dimensions": 3072,
    "encoding_format": "base64",
    "tokenizer": "cl100k_base",
    "vocabulary_sha256": VOCAB_HASH,
    "max_inputs_per_request": 128,
    "max_tokens_per_request": 100000,
    "max_tokens_per_input": 8192,
    "usd_per_million_input_tokens": "0.13",
    "price_checked_on": "2026-10-14",
    "pricing_source": "https://developers.openai.com/api/docs/models/text-embedding-3-large",
    "api_source": "https://developers.openai.com/api/reference/python/resources/embeddings/methods/create",
    "purpose": "Find candidate related reporting; similarity is not event identity or an incident finding",
    "model_version_limit": "Provider alias; no separately pinned dated snapshot is documented",
}


def offline_tokenizer() -> tiktoken.Encoding:
    cache = Path(
        os.environ.get(
            "TIKTOKEN_CACHE_DIR",
            os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache")),
        )
    )
    path = cache / hashlib.sha1(VOCAB_URL.encode()).hexdigest()
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != VOCAB_HASH:
        raise ResearchError("Cache the verified public cl100k_base vocabulary before offline planning")
    # The hash-verified local cache satisfies tiktoken's own check without downloading.
    return tiktoken.get_encoding("cl100k_base")


def cost(tokens: int, rate: str = "0.13") -> Decimal:
    return Decimal(tokens) * Decimal(rate) / Decimal(1000000)


def plan(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    preparation = engine.ledger.get(data["preparation"], "corpus_preparation")
    if preparation["dataset"] != context.versions["dataset"]:
        raise ResearchError("Embedding preparation and dataset bindings differ")
    if any(context.versions.get(key) != value for key, value in preparation["versions"].items()):
        raise ResearchError("Embedding plan must retain the preparation's method bindings")
    encoder = offline_tokenizer()
    profile: Json = {**PROFILE, "tiktoken_version": importlib.metadata.version("tiktoken")}
    registered = engine._version(
        session,
        context,
        {
            "kind": "embedding_profile",
            "key": "openai-embedding-candidates",
            "content": profile,
            "amend_latest": True,
            "reason": "Select OpenAI embeddings; concrete paid execution remains separately authorized",
        },
    )
    versions = {**context.versions, "embedding_profile": registered["id"]}
    implementation = digest(
        {
            key: value
            for key, value in engine.identity()["code_files"].items()
            if key.startswith("src/") or key == "uv.lock"
        }
    )
    allowed = set(engine.ledger.get(context.versions["dataset"], "dataset")["source_versions"])
    pending: list[Json] = []
    pending_tokens = total_tokens = chunk_count = max_input = 0
    seen: set[str] = set()
    items = []

    def flush() -> None:
        nonlocal pending, pending_tokens
        if not pending:
            return
        body = {
            "model": profile["model"],
            "dimensions": profile["dimensions"],
            "encoding_format": "base64",
            "input": [chunk["text"] for chunk in pending],
        }
        wire_ref = engine.ledger.artifacts.put_bytes(canonical(body).encode("utf-8"))
        request = {
            "gateway_contract": "embedding-v1",
            "task_kind": "embedding",
            "endpoint": ENDPOINT,
            "instructions": [],
            "instruction_semantics": "Embedding endpoint receives text, not instruction messages",
            "provider": "openai",
            "model": profile["model"],
            "versions": versions,
            "implementation_digest": implementation,
            "preparation": data["preparation"],
            "profile": profile,
            "body": body,
            "wire_body_ref": wire_ref,
            "chunks": [{key: value for key, value in chunk.items() if key != "text"} for chunk in pending],
            "input_tokens": pending_tokens,
        }
        reference = engine.ledger.artifacts.put(request)
        engine.ledger.append(
            session, "embedding.request.prepared", {"request": reference, "wire_body": wire_ref}
        )
        items.append(
            {
                "task_key": digest(request),
                "request_ref": reference,
                "chunks": len(pending),
                "input_tokens": pending_tokens,
            }
        )
        pending, pending_tokens = [], 0

    for reference in preparation["chunk_artifacts"]:
        for chunk in engine.ledger.artifacts.read(reference):
            if chunk["id"] in seen or chunk["source_version"] not in allowed:
                raise ResearchError("Duplicate or out-of-dataset embedding chunk")
            passage = engine.ledger.db.execute(
                "SELECT * FROM passages WHERE id=?", (chunk["passage_id"],)
            ).fetchone()
            if not passage or passage["source_id"] != chunk["source_version"]:
                raise ResearchError("Embedding chunk has no matching source passage")
            start, end = chunk["source_start"], chunk["source_end"]
            if (
                not passage["start"] <= start < end <= passage["end"]
                or passage["text"][start - passage["start"] : end - passage["start"]] != chunk["text"]
            ):
                raise ResearchError("Embedding chunk differs from its exact source offsets")
            identity = {
                key: chunk[key]
                for key in [
                    "method",
                    "source_version",
                    "passage_id",
                    "source_start",
                    "source_end",
                    "text_hash",
                ]
            }
            if (
                digest(identity) != chunk["id"]
                or hashlib.sha256(chunk["text"].encode()).hexdigest() != chunk["text_hash"]
            ):
                raise ResearchError("Embedding chunk integrity check failed")
            tokens = len(encoder.encode_ordinary(chunk["text"]))
            if not chunk["text"].strip() or not 1 <= tokens <= profile["max_tokens_per_input"]:
                raise ResearchError("Embedding input is empty or exceeds the model limit")
            if pending and (
                len(pending) == profile["max_inputs_per_request"]
                or pending_tokens + tokens > profile["max_tokens_per_request"]
            ):
                flush()
            pending.append(chunk)
            pending_tokens += tokens
            total_tokens += tokens
            max_input = max(max_input, tokens)
            chunk_count += 1
            seen.add(chunk["id"])
    flush()
    if chunk_count != preparation["embedding_input_chunks"] or not items:
        raise ResearchError("Embedding preparation coverage is incomplete")
    context_artifact = engine.ledger.artifacts.put({"versions": versions})
    engine.ledger.append(session, "embedding.context.saved", {"artifact": context_artifact})
    manifest = {
        "items": items,
        "versions": versions,
        "profile": profile,
        "preparation": data["preparation"],
        "implementation_digest": implementation,
        "expected_chunks": chunk_count,
        "request_count": len(items),
        "input_tokens": total_tokens,
        "largest_input_tokens": max_input,
        "estimated_cost_usd": str(cost(total_tokens, profile["usd_per_million_input_tokens"])),
        "estimate_scope": "One successful request per batch; excludes retries, tax and any future price changes",
        "float32_vector_bytes": chunk_count * profile["dimensions"] * 4,
        "base64_vector_bytes": chunk_count * ((profile["dimensions"] * 4 + 2) // 3 * 4),
        "text_unavailable_records": preparation["text_unavailable_records"],
        "source_records": preparation["selected_records"],
        "context_artifact": context_artifact,
        "status": "planned; paid execution not authorized",
        "network_calls": 0,
        "model_calls": 0,
    }
    identifier = engine.ledger.record(
        session,
        "embedding_plan",
        digest({"versions": versions, "preparation": data["preparation"], "implementation": implementation}),
        manifest,
    )
    return {"id": identifier, **{key: value for key, value in manifest.items() if key != "items"}}


@dataclass(frozen=True)
class EmbeddingHTTPResponse:
    body: bytes
    status: int
    request_id: str | None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: Any, msg: Any, headers: Any, newurl: Any) -> None:
        raise ResearchError("Embedding transport redirects are forbidden")


class OpenAIEmbeddingTransport:
    """No SDK retry, configurable destination or credential-bearing logging."""

    def send(self, body: bytes, client_request_id: str) -> EmbeddingHTTPResponse:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ResearchError("OPENAI_API_KEY is unavailable")
        request = urllib.request.Request(
            ENDPOINT,
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "X-Client-Request-Id": client_request_id,
            },
        )
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=60) as response:
                return EmbeddingHTTPResponse(
                    response.read(), response.status, response.headers.get("x-request-id")
                )
        except urllib.error.HTTPError as error:
            return EmbeddingHTTPResponse(error.read(), error.code, error.headers.get("x-request-id"))


def validate_response(request: Json, response: Json) -> Json:
    require_no_credentials(response)
    if response.get("object") != "list" or response.get("model") != request["model"]:
        raise ResearchError("embedding_response_model_invalid")
    items = response.get("data")
    if not isinstance(items, list) or len(items) != len(request["chunks"]):
        raise ResearchError("embedding_response_coverage_invalid")
    seen = set()
    for item in items:
        index = item.get("index")
        if (
            type(index) is not int
            or not 0 <= index < len(items)
            or index in seen
            or item.get("object") != "embedding"
        ):
            raise ResearchError("embedding_response_index_invalid")
        seen.add(index)
        try:
            raw = base64.b64decode(item["embedding"], validate=True)
            dimensions = request["profile"]["dimensions"]
            if len(raw) != dimensions * 4:
                raise ValueError("dimensions")
            values = struct.unpack("<" + "f" * dimensions, raw)
            if not all(math.isfinite(value) for value in values) or not any(values):
                raise ValueError("non-finite or zero vector")
        except (ValueError, TypeError, KeyError) as error:
            raise ResearchError("embedding_response_vector_invalid") from error
    usage = response.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(field)) is not int or usage[field] < 0 for field in ["prompt_tokens", "total_tokens"]
    ):
        raise ResearchError("embedding_response_usage_invalid")
    return {
        "status": "valid",
        "vectors": len(items),
        "dimensions": request["profile"]["dimensions"],
        "model": response["model"],
        "usage": usage,
        "layer": "retrieval representation; not an accepted research finding",
    }


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    if engine.config.offline:
        raise ResearchError("Paid embeddings are blocked by the default offline configuration")
    planned = ledger.get(data["plan"], "embedding_plan")
    if planned["versions"] != context.versions:
        raise ResearchError("Embedding execution requires the exact planned version bindings")
    current = digest(
        {
            key: value
            for key, value in engine.identity()["code_files"].items()
            if key.startswith("src/") or key == "uv.lock"
        }
    )
    if current != planned["implementation_digest"]:
        raise ResearchError("Embedding implementation changed; create and approve a new plan")
    policy_id = data.get("approval_policy")
    if not policy_id:
        raise ResearchError("A concrete registered paid-run approval is required")
    policy = ledger.get(policy_id, "policy")["content"]
    if (
        policy.get("method") != "embedding-run-approval-v1"
        or policy.get("plan") != data["plan"]
        or not policy.get("approved_by")
        or policy.get("allow_external_processing") is not True
        or policy.get("allow_paid_inference") is not True
    ):
        raise ResearchError("Paid-run approval must bind this plan and external processing")
    expiry = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ResearchError("Paid-run approval expired or has no timezone")
    budget = Decimal(str(policy["max_estimated_cost_usd"]))
    if not budget.is_finite() or budget <= 0:
        raise ResearchError("Paid-run approval needs a positive finite estimated-cost budget")
    limit = data.get("max_requests", len(planned["items"]))
    if type(limit) is not int or not 0 <= limit <= len(planned["items"]):
        raise ResearchError("Invalid embedding request limit")
    # Read only inside the authorized operation. The key never enters an artifact or journal input.
    transport = OpenAIEmbeddingTransport()
    if not os.environ.get("OPENAI_API_KEY"):
        raise ResearchError("OPENAI_API_KEY is unavailable; no embedding request was sent")
    reserved = sum(
        (
            Decimal(json.loads(row[0])["reserved_cost_usd"])
            for row in ledger.db.execute(
                "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.approval_policy')=?",
                (policy_id,),
            )
        ),
        Decimal(0),
    )
    results = []
    sent = 0
    stopped = False
    for item in planned["items"]:
        request = ledger.artifacts.read(item["request_ref"])
        unresolved = any(value["task_key"] == item["task_key"] for value in ledger.unresolved.values())
        if unresolved:
            raise ResearchError(
                "An embedding attempt has an unknown outcome; explicitly resolve it before retrying"
            )
        cached = ledger.db.execute(
            "SELECT result_id,id FROM attempts WHERE task_key=? AND status='valid' ORDER BY number DESC LIMIT 1",
            (item["task_key"],),
        ).fetchone()
        if cached:
            previous = ledger.get(cached["result_id"], "embedding_result")
            validate_response(request, json.loads(ledger.artifacts.read_bytes(previous["raw_response_ref"])))
            ledger.append(
                session,
                "model.cache_reused",
                {
                    "task_key": item["task_key"],
                    "attempt": cached["id"],
                    "result": cached["result_id"],
                    "batch": data["plan"],
                },
            )
            results.append({**item, "status": "cached", "result": cached["result_id"]})
            continue
        estimate = cost(item["input_tokens"], planned["profile"]["usd_per_million_input_tokens"])
        if stopped or sent >= limit or reserved + estimate > budget or expiry <= datetime.now(timezone.utc):
            results.append({**item, "status": "not_processed", "result": None})
            continue
        wire = ledger.artifacts.read_bytes(request["wire_body_ref"])
        if wire != canonical(request["body"]).encode("utf-8"):
            raise AuditError("Embedding wire body differs from the registered request")
        prior = ledger.db.execute(
            "SELECT max(CAST(json_extract(payload,'$.number') AS INTEGER)) FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.task_key')=?",
            (item["task_key"],),
        ).fetchone()[0]
        number = (prior or 0) + 1
        attempt, started = str(uuid.uuid4()), utc()
        intent = {
            "attempt": attempt,
            "task_key": item["task_key"],
            "number": number,
            "batch": data["plan"],
            "request": item["request_ref"],
            "started_at": started,
            "client_request_id": attempt,
            "approval_policy": policy_id,
            "reserved_cost_usd": str(estimate),
        }
        ledger.append(session, "model.attempt.intended", intent)
        reserved += estimate
        sent += 1
        try:
            response = transport.send(wire, attempt)
        except Exception as error:
            # A timeout/disconnection can follow remote execution: do not invent a failed outcome or retry.
            ledger.append(
                session,
                "model.attempt.unobserved",
                {"attempt": attempt, "error_type": type(error).__name__, "observed_at": utc()},
            )
            ledger.unresolved[attempt] = intent
            raise ResearchError(
                "Embedding response unavailable; outcome unknown and automatic retry blocked"
            ) from None
        response_ref = result_id = raw_ref = None
        error_type = None
        status = "invalid"
        validation: Json = {}
        try:
            parsed = json.loads(response.body)
            require_no_credentials(parsed)
            raw_ref = ledger.artifacts.put_bytes(response.body)
            ledger.append(session, "embedding.response.received", {"artifact": raw_ref, "attempt": attempt})
            response_ref = ledger.artifacts.put(
                {
                    "raw_response_ref": raw_ref,
                    "request_id": response.request_id,
                    "http_status": response.status,
                    "started_at": started,
                    "ended_at": utc(),
                    "model": parsed.get("model"),
                    "usage": parsed.get("usage"),
                }
            )
            if response.status != 200:
                raise ResearchError("embedding_http_error")
            validation = validate_response(request, parsed)
            result_id = ledger.record(
                session,
                "embedding_result",
                attempt,
                {
                    "attempt": attempt,
                    "task_key": item["task_key"],
                    "plan": data["plan"],
                    "request_ref": item["request_ref"],
                    "raw_response_ref": raw_ref,
                    "response_ref": response_ref,
                    "validation": validation,
                    "versions": context.versions,
                    "mapping": "Each response item's index maps to request chunks[index]; raw base64 float32 vectors retained exactly",
                },
            )
            status = "valid"
        except AuditError:
            raise
        except Exception as error:
            error_type = type(error).__name__
            validation = {
                "status": "invalid",
                "error_type": error_type,
                "response_not_retained": raw_ref is None,
            }
            stopped = True

        def project(event: int) -> None:
            ledger.db.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    attempt,
                    item["task_key"],
                    data["plan"],
                    number,
                    item["request_ref"],
                    response_ref,
                    status,
                    result_id,
                    error_type,
                    event,
                ),
            )

        ledger.append(
            session,
            "model.attempt.completed",
            {
                "attempt": attempt,
                "status": status,
                "response": response_ref,
                "assessment": result_id,
                "validation": validation,
                "http_status": response.status,
                "request_id": response.request_id,
                "ended_at": utc(),
            },
            project,
        )
        results.append({**item, "status": status, "result": result_id})
    output = {
        "plan": data["plan"],
        "approval_policy": policy_id,
        "items": results,
        "expected_chunks": planned["expected_chunks"],
        "completed_chunks": sum(item["chunks"] for item in results if item["status"] in {"valid", "cached"}),
        "requests_sent": sent,
        "reserved_cost_usd": str(reserved),
        "versions": context.versions,
        "missing_task_keys": [
            item["task_key"] for item in results if item["status"] not in {"valid", "cached"}
        ],
        "scope": "Embedding representations only; event matching and retrieval evaluation remain separate",
    }
    identifier = ledger.record(session, "embedding_run", str(uuid.uuid4()), output)
    return {"id": identifier, **output}
