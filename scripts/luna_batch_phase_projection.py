"""Pure explicit-phase envelope projection of already-retained Responses rows.

The caller registers this as a separate parser/derivation version and preserves
the original bytes, assessments and statuses. Only explicit completed assistant
commentary preceding exactly one final_answer may be removed. Text, reasoning,
usage, instructions and the event contract are unchanged. Hashes of dictionaries
are canonical-JSON hashes, not claims about original provider-file whitespace.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from typing import Any, Mapping

from newsresearch.common import Json, ResearchError, canonical
from luna_batch_results import _joined, parse_batch_results

METHOD = "luna-event-v2-explicit-response-phase-projection-v1"


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _project(row: Json, task: Json, raw_assessment: Json) -> Json:
    derived = deepcopy(row)
    assessment = deepcopy(raw_assessment)
    body = row.get("response", {}).get("body") if isinstance(row.get("response"), dict) else None
    output = body.get("output") if isinstance(body, dict) else None
    message_indices = [index for index, item in enumerate(output) if isinstance(item, dict) and item.get("type") == "message"] if isinstance(output, list) else []
    source_indices: Json = {"final_message_index": None, "commentary_message_indices": [],
                           "retained_output_indices": list(range(len(output))) if isinstance(output, list) else [],
                           "removed_output_indices": []}
    phase_errors: list[str] = []
    changed = False
    # Preserve the existing parser's single-message behavior. Technical failures
    # unrelated to multiplicity are never repaired by removing an envelope.
    eligible = len(message_indices) > 1 and set(raw_assessment["errors"]) == {"response:not_single_message"}
    if eligible:
        assert isinstance(output, list)
        finals, commentary = [], []
        for index in message_indices:
            item = output[index]
            if item.get("role") != "assistant" or item.get("status") != "completed":
                phase_errors.append("phase:message_not_explicit_completed_assistant")
            phase = item.get("phase")
            if phase == "final_answer":
                finals.append(index)
            elif phase == "commentary":
                commentary.append(index)
            else:
                phase_errors.append("phase:unknown_or_missing_message_phase")
            parts = item.get("content")
            if isinstance(parts, list) and any(isinstance(part, dict) and part.get("type") == "refusal" for part in parts):
                phase_errors.append("phase:refusal")
            if (not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict)
                    or parts[0].get("type") != "output_text" or not isinstance(parts[0].get("text"), str)):
                phase_errors.append("phase:message_not_single_output_text")
        if len(finals) != 1:
            phase_errors.append("phase:multiple_final_answers" if finals else "phase:missing_final_answer")
        elif any(index > finals[0] for index in commentary):
            phase_errors.append("phase:commentary_after_final")
        if phase_errors:
            assessment.update(status="error", technical_failure=True, result=None, rejected_output=None,
                              errors=list(dict.fromkeys([*raw_assessment["errors"], *phase_errors])))
        else:
            removed = set(commentary)
            derived["response"]["body"]["output"] = [item for index, item in enumerate(derived["response"]["body"]["output"])
                                                       if index not in removed]
            source_indices = {"final_message_index": finals[0], "commentary_message_indices": list(commentary),
                              "retained_output_indices": [index for index in range(len(output)) if index not in removed],
                              "removed_output_indices": list(commentary)}
            assessment = parse_batch_results((canonical(derived) + "\n").encode(), None,
                                             {row["custom_id"]: task})["items"][0]
            changed = True
    texts = []
    if isinstance(output, list):
        for index in message_indices:
            item = output[index]
            parts = item.get("content")
            text_hashes = [hashlib.sha256(part["text"].encode("utf-8")).hexdigest()
                           for part in parts if isinstance(part, dict) and part.get("type") == "output_text"
                           and isinstance(part.get("text"), str)] if isinstance(parts, list) else []
            texts.append({"output_index": index, "item_canonical_sha256": _sha(item),
                          "output_text_utf8_sha256": text_hashes})
    return {"method": METHOD, "derived_row": derived, "assessment": assessment,
            "changed": changed, "valid": assessment["status"] == "valid", "errors": list(assessment["errors"]),
            "raw_status": raw_assessment["status"], "raw_errors": list(raw_assessment["errors"]),
            "phase_errors": list(dict.fromkeys(phase_errors)), "source_indices": source_indices,
            "provenance": {"original_envelope_canonical_sha256": _sha(row),
                           "derived_envelope_canonical_sha256": _sha(derived), "messages": texts,
                           "envelope_hash_basis": "canonical_json_not_original_raw_file_bytes",
                           "output_text_changed": False, "reasoning_changed": False, "usage_changed": False},
            "original_output_changed": False, "semantic_accuracy_validated": False, "new_model_calls": 0}


def project_final_answer_phase(row: Json, task: Json) -> Json:
    """Project one retained row and validate through the unchanged original parser."""
    if not isinstance(row, dict) or not isinstance(row.get("custom_id"), str) or not row["custom_id"]:
        raise ResearchError("phase_projection_custom_id_required")
    baseline = parse_batch_results((canonical(row) + "\n").encode(), None, {row["custom_id"]: task})
    return _project(row, task, baseline["items"][0])


def parse_batch_results_phase_aware(output_bytes: bytes | None, error_bytes: bytes | None,
                                   tasks: Mapping[str, Json]) -> Json:
    """Separately versioned drop-in parser; original join and schema guards apply.

    The same strict complete-file join runs first. Per-item raw_status/raw_errors
    preserve the original interpretation. Changed or rejected phase projections
    carry separate derived envelopes; originals must remain retained by caller.
    """
    baseline = parse_batch_results(output_bytes, error_bytes, tasks)
    observed = _joined(output_bytes, error_bytes, set(tasks))
    items, projections = [], []
    for original in baseline["items"]:
        custom_id = original["custom_id"]
        if custom_id not in observed:
            items.append({**original, "raw_status": original["status"], "raw_errors": list(original["errors"]),
                          "phase_projection": None})
            continue
        projected = _project(observed[custom_id], tasks[custom_id], original)
        metadata = {key: projected[key] for key in ("method", "changed", "source_indices", "provenance", "phase_errors")}
        items.append({**projected["assessment"], "raw_status": projected["raw_status"],
                      "raw_errors": projected["raw_errors"], "phase_projection": metadata})
        if projected["changed"] or projected["phase_errors"]:
            projections.append({"custom_id": custom_id, **projected})
    counts = Counter(item["status"] for item in items)
    focuses = Counter(item["result"]["focus"] for item in items if item["status"] == "valid")
    return {**baseline, "items": items,
            "counts": {status: counts[status] for status in ("valid", "invalid", "error", "unknown")},
            "focus_counts": {name: focuses[name] for name in ("single", "multiple", "none", "uncertain")},
            "technical_failures": sum(item["technical_failure"] for item in items),
            "parser_method": METHOD, "phase_projections": projections,
            "phase_projection_count": sum(projection["changed"] for projection in projections),
            "phase_recovered_valid_count": sum(projection["changed"] and projection["valid"] for projection in projections),
            "original_statuses_changed": False}
