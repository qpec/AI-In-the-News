"""Pure parsing of already-retained Batch receipts; no I/O or model inference.

The caller must use Research.execute and the shared gateway to retrieve and
retain the complete provider files before calling this helper. It does not
settle money, authenticate receipts, accept findings or retry missing records.
Content validity establishes the frozen contract's mechanical checks only.
"""
from __future__ import annotations

from collections import Counter
import json
from typing import Any, Mapping

from newsresearch.common import Json, ResearchError, require_no_credentials
from luna_event_contract_v2 import validate_output, validate_packet

MODEL = "gpt-6-luna"


def _unique_object(pairs: list[tuple[str, Any]]) -> Json:
    result: Json = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise ValueError("nonfinite_json_number")


def _loads(raw: str | bytes) -> Any:
    return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _joined(output_bytes: bytes | None, error_bytes: bytes | None,
            expected: set[str]) -> dict[str, Json]:
    observed: dict[str, Json] = {}
    for raw in (output_bytes, error_bytes):
        if raw is None:
            continue
        if not isinstance(raw, bytes):
            raise ResearchError("batch_result_file_requires_bytes")
        try:
            lines = raw.decode("utf-8").splitlines()
        except UnicodeError:
            raise ResearchError("batch_result_file_invalid_utf8") from None
        for line in lines:
            if not line.strip():
                continue
            try:
                row = _loads(line)
            except (ValueError, TypeError):
                raise ResearchError("batch_result_malformed_jsonl") from None
            if not isinstance(row, dict):
                raise ResearchError("batch_result_row_not_object")
            require_no_credentials(row)
            custom_id = row.get("custom_id")
            if not isinstance(custom_id, str) or custom_id not in expected:
                raise ResearchError("batch_result_foreign_custom_id")
            if custom_id in observed:
                raise ResearchError("batch_result_duplicate_custom_id")
            observed[custom_id] = row
    return observed


def _usage_complete(usage: Any) -> bool:
    if (not isinstance(usage, dict)
            or type(usage.get("input_tokens")) is not int or usage["input_tokens"] < 0
            or type(usage.get("output_tokens")) is not int or usage["output_tokens"] < 0):
        return False
    total = usage.get("total_tokens")
    return total is None or (type(total) is int and total == usage["input_tokens"] + usage["output_tokens"])


def _nullable_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_row(custom_id: str, task: Json, row: Json | None) -> Json:
    result: Json = {
        "custom_id": custom_id, "status": "unknown", "technical_failure": True,
        "result": None, "rejected_output": None, "errors": [], "usage": None,
        "usage_complete": False, "observed_model": None, "response_id": None,
        "provider_request_id": None, "provider_status": None, "http_status": None,
        "source_id": task.get("source_id"), "source_refs": task.get("source_refs"),
        "packet_ref": task.get("packet_ref"), "request_ref": task.get("request_ref"),
        "missing": row is None,
    }
    if row is None:
        result["errors"] = ["batch:missing_custom_id"]
        return result
    response = row.get("response")
    body = response.get("body") if isinstance(response, dict) else None
    if isinstance(response, dict):
        result.update(provider_request_id=_nullable_string(response.get("request_id")),
                      http_status=response.get("status_code"))
    if isinstance(body, dict):
        usage = body.get("usage")
        result.update(usage=usage if isinstance(usage, dict) else None,
                      usage_complete=_usage_complete(usage),
                      observed_model=_nullable_string(body.get("model")),
                      response_id=_nullable_string(body.get("id")),
                      provider_status=_nullable_string(body.get("status")))

    technical: list[str] = []
    if row.get("error") is not None:
        technical.append("batch:provider_request_error")
    if not isinstance(response, dict) or type(response.get("status_code")) is not int or response["status_code"] != 200:
        technical.append("response:http_not_200")
    if not isinstance(body, dict):
        technical.append("response:body_missing_or_invalid")
    else:
        if body.get("model") != MODEL or body.get("model") != task["body"]["model"]:
            technical.append("response:model_unavailable_or_mismatch")
        if body.get("status") != "completed" or body.get("error") is not None or body.get("incomplete_details") is not None:
            technical.append("response:not_completed")
        if not result["usage_complete"]:
            technical.append("response:usage_missing_or_invalid")
        if body.get("tools"):
            technical.append("response:unexpected_tools")
    if technical:
        result.update(status="error", errors=technical)
        return result

    assert isinstance(body, dict)
    output = body.get("output")
    text: str | None = None
    if not isinstance(output, list) or not output:
        technical.append("response:output_missing_or_invalid")
    else:
        messages = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") not in {"message", "reasoning"}:
                technical.append("response:unexpected_output_or_tool")
                continue
            if item.get("status", "completed") != "completed":
                technical.append("response:output_not_completed")
            if item["type"] == "message":
                messages.append(item)
        if len(messages) != 1:
            technical.append("response:not_single_message")
        else:
            message = messages[0]
            parts = message.get("content")
            if message.get("role", "assistant") != "assistant":
                technical.append("response:unexpected_message_role")
            if isinstance(parts, list) and any(isinstance(part, dict) and part.get("type") == "refusal" for part in parts):
                technical.append("response:refusal")
            if (not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict)
                    or parts[0].get("type") != "output_text" or not isinstance(parts[0].get("text"), str)):
                technical.append("response:not_single_output_text")
            else:
                text = parts[0]["text"]
    if technical:
        result.update(status="error", errors=technical)
        return result

    try:
        parsed = _loads(text or "")
    except (ValueError, TypeError):
        result.update(status="invalid", technical_failure=False, errors=["content:invalid_json"])
        return result
    require_no_credentials(parsed)
    errors = validate_output(parsed, task["packet"], response_status=body["status"], response_truncated=False)
    result.update(status="invalid" if errors else "valid", technical_failure=False, errors=errors,
                  result=None if errors else parsed, rejected_output=parsed if errors else None)
    return result


def parse_batch_results(output_bytes: bytes | None, error_bytes: bytes | None,
                        tasks: Mapping[str, Json]) -> Json:
    """Join two retained files to the complete frozen task manifest.

    ``tasks`` maps custom ID to ``{packet, body}`` with optional source_id,
    source_refs, packet_ref and request_ref. Foreign IDs, duplicate IDs/JSON keys
    or malformed file rows fail the whole join; caller keeps budget reservations.
    Missing expected IDs remain explicit unknown rows. Output syntax, schema or
    literal failures are ``invalid``; transport/model/completion/usage/refusal/
    tool failures are ``error``. No status is an event or eligibility finding.
    """
    if not isinstance(tasks, Mapping) or not tasks:
        raise ResearchError("batch_result_frozen_tasks_required")
    for custom_id, task in tasks.items():
        if (not isinstance(custom_id, str) or not custom_id or not isinstance(task, dict)
                or not isinstance(task.get("body"), dict) or task["body"].get("model") != MODEL
                or validate_packet(task.get("packet"))):
            raise ResearchError("batch_result_frozen_task_contract_invalid")
        require_no_credentials(task)
    observed = _joined(output_bytes, error_bytes, set(tasks))
    items = [_parse_row(custom_id, task, observed.get(custom_id)) for custom_id, task in tasks.items()]
    counts = Counter(item["status"] for item in items)
    focus = Counter(item["result"]["focus"] for item in items if item["status"] == "valid")
    return {
        "items": items, "counts": {status: counts[status] for status in ("valid", "invalid", "error", "unknown")},
        "focus_counts": {name: focus[name] for name in ("single", "multiple", "none", "uncertain")},
        "expected": len(tasks), "returned": len(observed), "missing": len(tasks) - len(observed),
        "technical_failures": sum(item["technical_failure"] for item in items),
        "usage_complete_count": sum(item["usage_complete"] for item in items),
        "mechanical_validation_only": True, "semantic_accuracy_validated": False,
        "human_reviewed": False, "memberships_changed": False,
    }
