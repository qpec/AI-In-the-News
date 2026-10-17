"""Pure full-text Luna request, shard, scheduling and reconciliation helpers.

This is not a research entry point or a model transport. Production callers
must enter Research.execute(), enforce retention, bind versions, and durably
reserve attempts through the shared gateway before any provider operation.
All packets and outputs containing evidence belong in protected storage.

Token counts here are explicitly supplied proxies, not Luna tokenization or
verified account limits. A reserve multiplier reduces underestimation risk;
it cannot prove provider capacity or establish a hard spending cap.
"""
from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
import hashlib
import json
from typing import Any

import luna_event_contract_v2 as contract

MODEL = "gpt-6-luna"
VERSION = "luna-fulltext-multibatch-v1"
PROVIDER_MAX_REQUESTS = 50_000
PROVIDER_BYTE_CEILING_EXCLUSIVE = 200_000_000
DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_TARGET_INPUT_TOKENS = 2_000_000
TOKEN_FRAMING_PROXY = 32
contract_digest = contract.contract_digest
CONTEXT_FIELDS = {"title", "lang", "date", "time", "dateTime", "dateTimePub", "source.uri", "source.title"}


def canonical_json(value: Any) -> str:
    """Exact serialization used for IDs, token proxies and request bytes."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContractSnapshot:
    """Explicit immutable contract bytes for one bounded preparation operation.

    Canonical JSON strings avoid shared mutable schema/codebook dictionaries.
    The audited caller binds this digest and verifies the contract plus its own
    implementation hashes again at scan completion. There is no global cache.
    """

    prompt: str
    schema_json: str
    codebook_json: str
    contract_sha256: str


def load_contract_snapshot() -> ContractSnapshot:
    """Read the registered contract once; loading alone performs no research."""
    before = contract_digest()
    snapshot = ContractSnapshot(
        prompt=contract.load_prompt(), schema_json=canonical_json(contract.load_schema()),
        codebook_json=canonical_json(contract.CODEBOOK), contract_sha256=contract_digest(),
    )
    if snapshot.contract_sha256 != before:
        raise ValueError("contract_changed_while_loading_snapshot")
    return snapshot


def _integer(value: Any, name: str, *, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}_must_be_integer_at_least_{minimum}")
    return value


def _nonblank(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name}_must_be_nonblank")
    return value


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{name}_must_be_lowercase_sha256")
    return value


def _multiplier(value: Any) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("reserve_multiplier_must_be_finite_at_least_one")
    try:
        multiplier = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("reserve_multiplier_must_be_finite_at_least_one") from error
    if not multiplier.is_finite() or multiplier < 1:
        raise ValueError("reserve_multiplier_must_be_finite_at_least_one")
    return multiplier


def reserved_input_tokens(input_tokens_proxy: int, reserve_multiplier: float | Decimal = 1.25) -> int:
    """Provisional conservative reservation, never an exact provider count."""
    proxy = _integer(input_tokens_proxy, "input_tokens_proxy", minimum=0)
    return int((Decimal(proxy) * _multiplier(reserve_multiplier)).to_integral_value(rounding=ROUND_CEILING))


def adaptive_shard_token_target(
    available_queue_tokens: int | None,
    *,
    reserve_multiplier: float = 1.25,
    target_remote_jobs: int = 8,
    default_target: int = DEFAULT_TARGET_INPUT_TOKENS,
    maximum_target: int = 10_000_000,
) -> int:
    """A planning target; unknown capacity uses the explicit operational default.

    Known capacity returns min(maximum_target, available / jobs / reserve),
    rounded down. Zero means no positive target fits. This makes no claim that
    the allowance is a verified provider limit and cannot authorize dispatch.
    Remote jobs are independent of the number of local HTTP submission workers.
    """
    reserve = _multiplier(reserve_multiplier)
    jobs = _integer(target_remote_jobs, "target_remote_jobs")
    default = _integer(default_target, "default_target")
    maximum = _integer(maximum_target, "maximum_target")
    if available_queue_tokens is None:
        return min(default, maximum)
    available = _integer(available_queue_tokens, "available_queue_tokens", minimum=0)
    target = int((Decimal(available) / jobs / reserve).to_integral_value(rounding=ROUND_FLOOR))
    return min(maximum, target)


def build_request_record(
    article: dict[str, Any],
    *,
    corpus_id: str,
    manifest_sha256: str,
    source_locator: Mapping[str, Any],
    source_sha256: str,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    count_tokens: Callable[[str], int] | None = None,
    token_proxy_method: str | None = None,
    context_availability: Mapping[str, str] | None = None,
    contract_snapshot: ContractSnapshot | None = None,
) -> dict[str, Any]:
    """Build one complete article request; never truncate or change the contract.

    The caller must supply permitted article bytes and provenance. Instructions
    appear only in Responses ``instructions``; ``input`` retains every other
    model-input field. The unchanged local packet retains the original source
    map for later contract validation. When supplied, count_tokens receives the
    exact serialized Responses body once, followed by a +32 framing proxy.
    Missing tokenization remains null and is not eligible for shard planning.
    """
    _nonblank(corpus_id, "corpus_id")
    _sha256(manifest_sha256, "manifest_sha256")
    _sha256(source_sha256, "source_sha256")
    if not isinstance(source_locator, Mapping) or not source_locator:
        raise ValueError("source_locator_must_be_nonempty_object")
    locator = json.loads(canonical_json(dict(source_locator)))
    _integer(max_output_tokens, "max_output_tokens")
    if token_proxy_method is not None:
        _nonblank(token_proxy_method, "token_proxy_method")
    if contract_snapshot is None:
        packet = contract.build_input(article)
        schema = contract.load_schema()
        digest = contract_digest()
    else:
        if not isinstance(contract_snapshot, ContractSnapshot):
            raise ValueError("contract_snapshot_must_be_immutable_snapshot")
        packet = contract.build_structured_input(
            article, instructions=contract_snapshot.prompt, codebook=json.loads(contract_snapshot.codebook_json))
        schema = json.loads(contract_snapshot.schema_json)
        digest = _sha256(contract_snapshot.contract_sha256, "contract_snapshot_sha256")
    availability = None
    if context_availability is not None:
        if not isinstance(context_availability, Mapping):
            raise ValueError("context_availability_must_be_object")
        availability = dict(context_availability)
        for field, state in availability.items():
            allowed = ({"absent", "null", "nonobject", "available"} if field == "source" else
                       {"absent", "null", "nontext", "blank", "available"} if field in CONTEXT_FIELDS else set())
            if state not in allowed:
                raise ValueError("context_availability_field_or_state_invalid")
        packet["model_input"]["context"]["availability"] = availability
    packet_errors = contract.validate_packet(packet)
    if packet_errors:
        raise ValueError("invalid_fulltext_packet:" + ",".join(packet_errors))
    model_input = {key: value for key, value in packet["model_input"].items() if key != "instructions"}
    parameters = {
        "model": MODEL, "reasoning": {"effort": "none"}, "store": False,
        "max_output_tokens": max_output_tokens,
    }
    body = {
        **parameters,
        "instructions": packet["model_input"]["instructions"],
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": canonical_json(model_input)},
        ]}],
        "text": {"format": {
            "type": "json_schema", "name": "luna_event_v2", "strict": True,
            "schema": schema,
        }},
    }
    custom_id = "luna_" + _digest({
        "version": VERSION, "corpus_id": corpus_id, "manifest_sha256": manifest_sha256,
        "source_locator": locator, "source_sha256": source_sha256,
        "contract_sha256": digest, "parameters": parameters, "body": body,
    })
    request = {"custom_id": custom_id, "method": "POST", "url": "/v1/responses", "body": body}
    line = (canonical_json(request) + "\n").encode("utf-8")
    proxy = None
    if count_tokens is not None:
        proxy = _integer(count_tokens(canonical_json(body)), "count_tokens_result", minimum=0) + TOKEN_FRAMING_PROXY
    descriptor = {
        "custom_id": custom_id, "corpus_id": corpus_id, "manifest_sha256": manifest_sha256,
        "source_locator": locator, "source_sha256": source_sha256,
        "contract_sha256": digest, "source_map_sha256": packet["source_map"]["sha256"],
        "packet_sha256": _digest(packet),
        "retained_body_sha256": packet["source_map"]["source_fields"]["body"]["sha256"],
        "line_sha256": hashlib.sha256(line).hexdigest(), "line_bytes": len(line),
        "request_sha256": _digest(request), "request_body_sha256": _digest(body),
        "input_tokens_proxy": proxy,
        "input_token_proxy_method": (token_proxy_method or "caller_tokenizer_serialized_body_plus_32")
        if count_tokens is not None else None,
        "input_tokens_exact": None, "token_proxy_validated_for_luna": False,
        "model": MODEL, "max_output_tokens": max_output_tokens,
    }
    if availability is not None:
        descriptor["context_availability"] = dict(availability)
    return {"packet": packet, "request": request, "jsonl_line": line,
            "descriptor": descriptor, "parameters": parameters}


@dataclass(frozen=True)
class ShardLimits:
    """Local operational ceilings, bounded by the declared provider file limits."""

    max_requests: int = 2500
    max_bytes: int = 64 * 1024 * 1024
    target_input_tokens: int = DEFAULT_TARGET_INPUT_TOKENS

    def __post_init__(self) -> None:
        if _integer(self.max_requests, "max_requests") > PROVIDER_MAX_REQUESTS:
            raise ValueError("max_requests_exceeds_provider_ceiling")
        if _integer(self.max_bytes, "max_bytes") >= PROVIDER_BYTE_CEILING_EXCLUSIVE:
            raise ValueError("max_bytes_must_be_below_provider_ceiling")
        _integer(self.target_input_tokens, "target_input_tokens")


def _descriptor(record: Mapping[str, Any]) -> dict[str, Any]:
    """Copy descriptor metadata only; the packer never receives article bodies."""
    copied = dict(record)
    copied.setdefault("input_tokens_proxy", None)
    for name in ("custom_id", "corpus_id"):
        _nonblank(copied.get(name), name)
    _sha256(copied.get("manifest_sha256"), "manifest_sha256")
    _integer(copied.get("line_bytes"), "line_bytes")
    if copied.get("input_tokens_proxy") is not None:
        _integer(copied["input_tokens_proxy"], "input_tokens_proxy")
    if copied.get("model", MODEL) != MODEL:
        raise ValueError("descriptor_model_mismatch")
    return copied


def _shard(records: list[dict[str, Any]], limits: ShardLimits) -> dict[str, Any]:
    first = records[0]
    contents = {
        "version": VERSION, "corpus_id": first["corpus_id"], "manifest_sha256": first["manifest_sha256"],
        "records": records, "limits": asdict(limits),
    }
    return {
        "state": "READY", "shard_id": "shard_" + _digest(contents),
        "corpus_id": first["corpus_id"], "manifest_sha256": first["manifest_sha256"],
        "model": MODEL, "records": records, "request_count": len(records),
        "line_bytes": sum(row["line_bytes"] for row in records),
        "input_tokens_proxy": sum(row["input_tokens_proxy"] for row in records),
        "input_tokens_exact": None, "limits": asdict(limits),
    }


def iter_shards(
    descriptors: Iterable[Mapping[str, Any]],
    limits: ShardLimits | None = None,
) -> Iterator[dict[str, Any]]:
    """Pack streaming descriptors, retaining only one open shard per partition.

    Input order is retained within each corpus/manifest pair. There is no source
    loading or copying. IDs are checked across the stream to prevent accidental
    duplicate requests. An oversized record is explicit and never truncated,
    discarded, or silently reclassified as a negative finding. Token targets
    are operational limits that may be explicitly changed in another plan.
    """
    limits = limits or ShardLimits()
    open_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    totals: dict[tuple[str, str], tuple[int, int]] = {}
    seen: set[str] = set()
    for incoming in descriptors:
        record = _descriptor(incoming)
        custom_id = record["custom_id"]
        if custom_id in seen:
            raise ValueError("duplicate_request_custom_id")
        seen.add(custom_id)
        partition = (record["corpus_id"], record["manifest_sha256"])
        proxy = record["input_tokens_proxy"]
        reasons = []
        if record["line_bytes"] > limits.max_bytes:
            reasons.append("record_exceeds_shard_byte_limit")
        if proxy is not None and proxy > limits.target_input_tokens:
            reasons.append("record_exceeds_shard_token_proxy_target")
        if proxy is None or reasons:
            if proxy is None:
                reasons.append("input_token_proxy_unavailable")
            yield {"state": "OVERSIZED" if reasons[0] != "input_token_proxy_unavailable" else "UNPLANNABLE",
                   "reasons": reasons, "record": record,
                   "corpus_id": partition[0], "manifest_sha256": partition[1]}
            continue
        rows = open_rows.setdefault(partition, [])
        byte_total, token_total = totals.get(partition, (0, 0))
        if rows and (len(rows) + 1 > limits.max_requests
                     or byte_total + record["line_bytes"] > limits.max_bytes
                     or token_total + proxy > limits.target_input_tokens):
            yield _shard(rows, limits)
            rows = []
            open_rows[partition] = rows
            byte_total = token_total = 0
        rows.append(record)
        totals[partition] = (byte_total + record["line_bytes"], token_total + proxy)
    for rows in open_rows.values():
        if rows:
            yield _shard(rows, limits)


def schedule_ready_shards(
    shards: Iterable[Mapping[str, Any]],
    *,
    queue_token_allowance: int | None,
    existing_inflight: Iterable[Mapping[str, Any]] = (),
    reserve_multiplier: float = 1.25,
    queue_cushion_tokens: int = 0,
    max_active_remote_jobs: int | None = None,
    last_dispatched_corpus_id: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic fair dispatch proposal, without performing I/O.

    queue_token_allowance is a caller-known total allowance for this model,
    before subtracting *all* existing in-flight reservations across corpora.
    Unknown outcomes must remain in existing_inflight until auditably resolved;
    the helper never infers that provider work has ended. Unknown allowance or
    an unknown in-flight reservation blocks all dispatch. The optional remote
    job cap is independent of local HTTP worker concurrency.

    Round-robin corpora each receive their first fitting READY shard. A shard
    too large for remaining capacity does not hide a smaller later shard. The
    result fills remaining capacity under that fair policy, not a knapsack
    optimum or a verified provider admission guarantee.
    """
    reserve = _multiplier(reserve_multiplier)
    cushion = _integer(queue_cushion_tokens, "queue_cushion_tokens", minimum=0)
    if queue_token_allowance is not None:
        _integer(queue_token_allowance, "queue_token_allowance", minimum=0)
    if max_active_remote_jobs is not None:
        _integer(max_active_remote_jobs, "max_active_remote_jobs", minimum=0)
    ready: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for incoming in shards:
        shard = dict(incoming)
        shard_id = _nonblank(shard.get("shard_id"), "shard_id")
        if shard_id in seen_ids:
            raise ValueError("duplicate_shard_id")
        seen_ids.add(shard_id)
        if shard.get("model", MODEL) != MODEL:
            raise ValueError("shard_model_mismatch")
        _nonblank(shard.get("corpus_id"), "corpus_id")
        if shard.get("state") != "READY":
            ignored.append({"shard_id": shard_id, "state": shard.get("state"), "reason": "not_ready"})
            continue
        proxy = shard.get("input_tokens_proxy")
        shard["reserved_input_tokens"] = None if proxy is None else reserved_input_tokens(proxy, reserve)
        ready.append(shard)
    inflight = list(existing_inflight)
    inflight_tokens = 0
    unknown_inflight = False
    for item in inflight:
        if item.get("model", MODEL) != MODEL:
            raise ValueError("inflight_model_mismatch")
        if item.get("shard_id") in seen_ids:
            raise ValueError("inflight_shard_also_supplied_for_scheduling")
        reservation = item.get("reserved_input_tokens")
        if reservation is None:
            proxy = item.get("input_tokens_proxy")
            if proxy is None:
                unknown_inflight = True
                continue
            reservation = reserved_input_tokens(proxy, reserve)
        inflight_tokens += _integer(reservation, "inflight_reserved_input_tokens", minimum=0)
    blocked_reason = None
    if queue_token_allowance is None:
        blocked_reason = "queue_token_allowance_unknown"
    elif unknown_inflight:
        blocked_reason = "inflight_token_reservation_unknown"
    capacity = None
    if blocked_reason is None:
        assert queue_token_allowance is not None
        capacity = max(0, queue_token_allowance - inflight_tokens - cushion)
    remaining = capacity
    selected: list[dict[str, Any]] = []
    pending: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for shard in sorted(ready, key=lambda row: (row["corpus_id"], row["shard_id"])):
        pending[shard["corpus_id"]].append(shard)
    corpora = sorted(pending)
    if last_dispatched_corpus_id in corpora:
        offset = corpora.index(last_dispatched_corpus_id) + 1
        corpora = corpora[offset:] + corpora[:offset]
    if blocked_reason is None:
        while True:
            progress = False
            for corpus_id in corpora:
                if max_active_remote_jobs is not None and len(inflight) + len(selected) >= max_active_remote_jobs:
                    break
                queue = pending[corpus_id]
                fitting = next((index for index, shard in enumerate(queue)
                                if shard["reserved_input_tokens"] is not None
                                and shard["reserved_input_tokens"] <= remaining), None)
                if fitting is None:
                    continue
                shard = queue[fitting]
                del queue[fitting]
                selected.append(shard)
                remaining -= shard["reserved_input_tokens"]
                progress = True
            if not progress:
                break
    blocked = []
    for corpus_id in corpora:
        for shard in pending[corpus_id]:
            reason = blocked_reason
            if reason is None and shard["reserved_input_tokens"] is None:
                reason = "input_token_proxy_unavailable"
            if reason is None and max_active_remote_jobs is not None and len(inflight) + len(selected) >= max_active_remote_jobs:
                reason = "remote_job_slots_exhausted"
            blocked.append({"shard_id": shard["shard_id"], "corpus_id": corpus_id,
                            "reason": reason or "queue_token_capacity_exhausted",
                            "reserved_input_tokens": shard["reserved_input_tokens"]})
    return {
        "state": "BLOCKED" if blocked_reason else "PLANNED", "selected": selected, "blocked": blocked,
        "ignored": ignored, "model": MODEL, "queue_token_allowance": queue_token_allowance,
        "queue_cushion_tokens": cushion, "existing_inflight_count": len(inflight),
        "existing_inflight_reserved_tokens": None if unknown_inflight else inflight_tokens,
        "available_before_selection": capacity, "remaining_queue_tokens": remaining,
        "selected_reserved_tokens": sum(row["reserved_input_tokens"] for row in selected),
        "max_active_remote_jobs": max_active_remote_jobs,
        "reserve_multiplier": str(reserve), "token_accounting": "provisional_proxy_with_configured_reserve",
        "provider_limit_verified": False,
        "next_fairness_cursor": selected[-1]["corpus_id"] if selected else last_dispatched_corpus_id,
    }


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> Any:
    raise ValueError("nonfinite_json_number")


def _candidate(row: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    result = {"custom_id": expected["custom_id"], "descriptor": expected, "raw_output": row,
              "parsed_output": None, "accepted": False, "validation_required": True}
    if row.get("error") is not None:
        return {**result, "state": "ERROR", "reason": "batch_request_error"}
    response = row.get("response")
    if not isinstance(response, dict) or response.get("status_code") != 200:
        return {**result, "state": "ERROR", "reason": "response_missing_or_non_200"}
    body = response.get("body")
    if not isinstance(body, dict):
        return {**result, "state": "INCOMPLETE", "reason": "response_body_unavailable"}
    result.update(observed_model=body.get("model"), response_id=body.get("id"),
                  request_id=response.get("request_id"), usage=body.get("usage"),
                  response_status=body.get("status"))
    if body.get("error") is not None or body.get("status") == "failed":
        return {**result, "state": "ERROR", "reason": "response_error"}
    if body.get("status") != "completed" or body.get("incomplete_details") is not None:
        return {**result, "state": "INCOMPLETE", "reason": "response_not_completed"}
    observed_model = body.get("model")
    if observed_model is not None and (not isinstance(observed_model, str)
                                       or not (observed_model == MODEL or observed_model.startswith(MODEL + "-"))):
        return {**result, "state": "ERROR", "reason": "response_model_mismatch"}
    output = body.get("output")
    if not isinstance(output, list):
        return {**result, "state": "INCOMPLETE", "reason": "response_output_unavailable"}
    texts = []
    for item in output:
        if not isinstance(item, dict):
            return {**result, "state": "INCOMPLETE", "reason": "response_output_shape_invalid"}
        if item.get("type") == "reasoning":
            continue
        if item.get("type") != "message" or not isinstance(item.get("content"), list):
            return {**result, "state": "ERROR", "reason": "unexpected_response_output_type"}
        if item.get("status") not in (None, "completed"):
            return {**result, "state": "INCOMPLETE", "reason": "response_message_not_completed"}
        for content in item["content"]:
            if not isinstance(content, dict):
                return {**result, "state": "INCOMPLETE", "reason": "response_content_shape_invalid"}
            if content.get("type") == "refusal":
                return {**result, "state": "REFUSAL", "reason": "response_refusal"}
            if content.get("type") != "output_text" or not isinstance(content.get("text"), str):
                return {**result, "state": "INCOMPLETE", "reason": "response_text_unavailable"}
            texts.append(content["text"])
    if not texts or not "".join(texts).strip():
        return {**result, "state": "INCOMPLETE", "reason": "response_text_unavailable"}
    try:
        parsed = json.loads("".join(texts), object_pairs_hook=_unique_json_object, parse_constant=_reject_nonfinite)
    except (ValueError, TypeError):
        return {**result, "state": "INVALID_JSON", "reason": "response_json_invalid"}
    return {**result, "state": "CANDIDATE", "parsed_output": parsed,
            "reason": "requires_contract_and_gateway_validation"}


def reconcile_outputs(
    expected_descriptors: Iterable[Mapping[str, Any]],
    output_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Join unordered output/error-file rows by ID without accepting any result.

    Supply both output and error files. Duplicates never resolve by taking the
    first or last response. Missing, failed, foreign and malformed rows remain
    separate. Even CANDIDATE records require original-packet contract checking,
    retained-response identity checks and review in the audited gateway.
    """
    expected: dict[str, dict[str, Any]] = {}
    for incoming in expected_descriptors:
        descriptor = dict(incoming)
        custom_id = _nonblank(descriptor.get("custom_id"), "custom_id")
        if custom_id in expected:
            raise ValueError("duplicate_expected_custom_id")
        expected[custom_id] = descriptor
    joined: dict[str, list[dict[str, Any]]] = defaultdict(list)
    foreign = []
    malformed = []
    observed = 0
    for index, incoming in enumerate(output_rows):
        observed += 1
        if not isinstance(incoming, Mapping) or not isinstance(incoming.get("custom_id"), str) or not incoming["custom_id"]:
            malformed.append({"row_index": index, "state": "MALFORMED", "raw_output": incoming})
            continue
        row = dict(incoming)
        if row["custom_id"] not in expected:
            foreign.append({"row_index": index, "state": "FOREIGN", "custom_id": row["custom_id"], "raw_output": row})
        else:
            joined[row["custom_id"]].append(row)
    results: list[dict[str, Any]] = []
    counts: dict[str, int] = defaultdict(int)
    for custom_id, descriptor in expected.items():
        result: dict[str, Any]
        matching = joined[custom_id]
        if not matching:
            result = {"custom_id": custom_id, "descriptor": descriptor, "state": "MISSING",
                      "parsed_output": None, "accepted": False, "validation_required": True}
        elif len(matching) != 1:
            result = {"custom_id": custom_id, "descriptor": descriptor, "state": "DUPLICATE",
                      "raw_outputs": matching, "parsed_output": None, "accepted": False,
                      "validation_required": True, "observed_count": len(matching)}
        else:
            result = _candidate(matching[0], descriptor)
        counts[result["state"]] += 1
        results.append(result)
    return {
        "expected_count": len(expected), "observed_row_count": observed, "results": results,
        "candidates": [row for row in results if row["state"] == "CANDIDATE"],
        "counts": {state: counts[state] for state in
                   ("CANDIDATE", "ERROR", "INCOMPLETE", "REFUSAL", "INVALID_JSON", "MISSING", "DUPLICATE")},
        "foreign": foreign, "malformed": malformed, "accepted_count": 0,
    }
