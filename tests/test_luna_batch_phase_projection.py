"""Synthetic explicit-phase parsing checks; no source or provider operations."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from newsresearch.common import ResearchError, canonical

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_event_contract_v2 as contract
    from luna_batch_results import parse_batch_results
    from luna_batch_phase_projection import parse_batch_results_phase_aware, project_final_answer_phase
finally:
    sys.path.pop(0)


def fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    packet, initial = contract.fictional_example()
    final = {**deepcopy(initial), "focus": "none", "reason": "no_particular_occurrence", "event": None}
    task = {"packet": packet, "body": {"model": "gpt-6-luna"}, "source_id": "fictional-source"}
    messages = [{"type": "message", "role": "assistant", "status": "completed", "phase": phase,
                 "content": [{"type": "output_text", "text": json.dumps(value, indent=2) + "\n"}]}
                for phase, value in (("commentary", initial), ("final_answer", final))]
    row = {"custom_id": "fixture", "error": None, "response": {"status_code": 200, "request_id": "req_fixture",
           "body": {"id": "resp_fixture", "model": "gpt-6-luna", "status": "completed", "error": None,
                    "incomplete_details": None, "usage": {"input_tokens": 100, "output_tokens": 90, "total_tokens": 190},
                    "output": [{"type": "reasoning", "summary": []}, *messages]}}}
    return row, task


def test_selects_only_explicit_final_without_changing_text_usage_or_original() -> None:
    row, task = fixture()
    original, original_task = deepcopy(row), deepcopy(task)
    before = parse_batch_results((canonical(row) + "\n").encode(), None, {"fixture": task})
    assert before["items"][0]["status"] == "error"
    projected = project_final_answer_phase(row, task)
    assert projected["changed"] and projected["valid"]
    assert projected["assessment"]["result"]["focus"] == "none"
    assert projected["raw_errors"] == ["response:not_single_message"]
    assert projected["source_indices"] == {"final_message_index": 2, "commentary_message_indices": [1],
                                            "retained_output_indices": [0, 2], "removed_output_indices": [1]}
    assert projected["derived_row"]["response"]["body"]["output"] == [original["response"]["body"]["output"][0], original["response"]["body"]["output"][2]]
    assert projected["derived_row"]["response"]["body"]["usage"] == original["response"]["body"]["usage"]
    text = original["response"]["body"]["output"][2]["content"][0]["text"]
    assert projected["provenance"]["messages"][1]["output_text_utf8_sha256"] == [hashlib.sha256(text.encode()).hexdigest()]
    assert projected["provenance"]["original_envelope_canonical_sha256"] == hashlib.sha256(canonical(original).encode()).hexdigest()
    assert row == original and task == original_task


def test_final_content_still_subject_to_unchanged_contract() -> None:
    row, task = fixture()
    final = row["response"]["body"]["output"][2]["content"][0]
    final["text"] = "not valid JSON"
    projected = project_final_answer_phase(row, task)
    assert projected["changed"] and not projected["valid"]
    assert projected["assessment"]["status"] == "invalid" and not projected["assessment"]["technical_failure"]
    assert projected["assessment"]["errors"] == ["content:invalid_json"]
    assert projected["derived_row"]["response"]["body"]["output"][1]["content"][0]["text"] == final["text"]


def test_commentary_text_is_never_concatenated_or_interpreted_as_final() -> None:
    row, task = fixture()
    row["response"]["body"]["output"][1]["content"][0]["text"] = "Intermediate progress, not the requested JSON."
    projected = project_final_answer_phase(row, task)
    assert projected["valid"] and projected["assessment"]["result"]["focus"] == "none"


@pytest.mark.parametrize("mutation", ["two_finals", "no_final", "unlabeled", "unknown_phase", "after_final",
                                      "nonassistant", "missing_role", "missing_status", "not_completed",
                                      "refusal", "two_text_parts", "bad_content"])
def test_ambiguous_or_unsafe_multimessage_shapes_stay_technical_errors(mutation: str) -> None:
    row, task = fixture()
    output = row["response"]["body"]["output"]
    if mutation == "two_finals":
        output[1]["phase"] = "final_answer"
    elif mutation == "no_final":
        output[2]["phase"] = "commentary"
    elif mutation == "unlabeled":
        output[1].pop("phase")
    elif mutation == "unknown_phase":
        output[1]["phase"] = "analysis"
    elif mutation == "after_final":
        output[1], output[2] = output[2], output[1]
    elif mutation == "nonassistant":
        output[1]["role"] = "user"
    elif mutation == "missing_role":
        output[1].pop("role")
    elif mutation == "missing_status":
        output[1].pop("status")
    elif mutation == "not_completed":
        output[1]["status"] = "in_progress"
    elif mutation == "refusal":
        output[1]["content"] = [{"type": "refusal", "refusal": "Synthetic refusal."}]
    elif mutation == "two_text_parts":
        output[1]["content"] *= 2
    else:
        output[1]["content"] = None
    original = deepcopy(row)
    projected = project_final_answer_phase(row, task)
    assert not projected["changed"] and not projected["valid"]
    assert projected["assessment"]["status"] == "error" and projected["assessment"]["technical_failure"]
    assert projected["derived_row"] == original and row == original


@pytest.mark.parametrize("mutation", ["model", "usage", "http", "incomplete", "tool", "unknown_output", "reasoning_incomplete"])
def test_other_original_technical_checks_are_not_repaired(mutation: str) -> None:
    row, task = fixture()
    body = row["response"]["body"]
    if mutation == "model":
        body["model"] = "gpt-6-luna-other"
    elif mutation == "usage":
        body["usage"]["total_tokens"] = 999
    elif mutation == "http":
        row["response"]["status_code"] = 500
    elif mutation == "incomplete":
        body["status"] = "incomplete"
    elif mutation == "tool":
        body["output"].append({"type": "function_call", "name": "unexpected"})
    elif mutation == "unknown_output":
        body["output"].append({"type": "unexpected"})
    else:
        body["output"][0]["status"] = "in_progress"
    projected = project_final_answer_phase(row, task)
    assert not projected["changed"] and not projected["valid"] and projected["assessment"]["technical_failure"]
    assert projected["derived_row"] == row


def test_single_message_behavior_remains_the_original_parser_behavior() -> None:
    row, task = fixture()
    row["response"]["body"]["output"] = row["response"]["body"]["output"][2:]
    row["response"]["body"]["output"][0].pop("phase")
    baseline = parse_batch_results(canonical(row).encode(), None, {"fixture": task})["items"][0]
    projected = project_final_answer_phase(row, task)
    assert not projected["changed"] and projected["assessment"] == baseline
    assert projected["derived_row"] == row


def test_multiple_commentaries_and_reasoning_preserve_order() -> None:
    row, task = fixture()
    output = row["response"]["body"]["output"]
    output.insert(2, deepcopy(output[1]))
    output.append({"type": "reasoning", "summary": [], "status": "completed"})
    projected = project_final_answer_phase(row, task)
    assert projected["valid"] and projected["source_indices"]["removed_output_indices"] == [1, 2]
    assert projected["source_indices"]["retained_output_indices"] == [0, 3, 4]
    assert projected["derived_row"]["response"]["body"]["output"] == [output[0], output[3], output[4]]


def test_batch_wrapper_preserves_missingness_and_original_interpretations() -> None:
    row, task = fixture()
    result = parse_batch_results_phase_aware((canonical(row) + "\n").encode(), None, {"fixture": task, "missing": task})
    assert result["counts"] == {"valid": 1, "invalid": 0, "error": 0, "unknown": 1}
    assert result["missing"] == 1 and result["technical_failures"] == 1
    assert result["items"][0]["raw_status"] == "error" and result["items"][0]["status"] == "valid"
    assert result["items"][1]["status"] == "unknown" and result["items"][1]["phase_projection"] is None
    assert result["phase_projection_count"] == 1 and result["phase_recovered_valid_count"] == 1
    assert result["phase_projections"][0]["derived_row"]["custom_id"] == "fixture"
    assert result["original_statuses_changed"] is False


@pytest.mark.parametrize("mode", ["duplicate", "foreign", "malformed"])
def test_wrapper_preserves_original_strict_file_join(mode: str) -> None:
    row, task = fixture()
    raw = (canonical(row) + "\n").encode()
    if mode == "duplicate":
        other = raw
    elif mode == "foreign":
        row["custom_id"] = "foreign"
        other = canonical(row).encode()
    else:
        other = b"{broken"
    with pytest.raises(ResearchError, match="batch_result_"):
        parse_batch_results_phase_aware(raw, other, {"fixture": task})
