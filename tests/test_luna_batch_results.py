"""Synthetic parser checks, not model quality or corpus observations."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from newsresearch.common import ResearchError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_event_contract_v2 as contract
    from luna_batch_results import parse_batch_results
finally:
    sys.path.pop(0)


def fixture(custom_id: str = "task-1") -> tuple[dict[str, Any], dict[str, Any]]:
    packet, output = contract.fictional_example()
    task = {"packet": packet, "body": {"model": "gpt-6-luna"}, "source_id": "fictional-source",
            "source_refs": {"p1": "fictional-passage"}, "packet_ref": "fixture-packet", "request_ref": "fixture-request"}
    row = {"id": "batch_req_fixture", "custom_id": custom_id, "error": None,
           "response": {"status_code": 200, "request_id": "req_fixture", "body": {
               "id": "resp_fixture", "model": "gpt-6-luna", "status": "completed", "error": None,
               "incomplete_details": None, "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
               "output": [{"type": "reasoning", "summary": []}, {"type": "message", "role": "assistant", "status": "completed",
                          "content": [{"type": "output_text", "text": json.dumps(output)}]}]}}}
    return task, row


def wire(*rows: dict[str, Any]) -> bytes:
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def test_valid_result_preserves_usage_identity_and_source_provenance() -> None:
    task, row = fixture()
    result = parse_batch_results(wire(row), None, {"task-1": task})
    item = result["items"][0]
    assert result["counts"] == {"valid": 1, "invalid": 0, "error": 0, "unknown": 0}
    assert result["focus_counts"] == {"single": 1, "multiple": 0, "none": 0, "uncertain": 0}
    assert item["result"]["event"]["summary"] and not item["technical_failure"]
    assert item["usage"] == row["response"]["body"]["usage"] and item["usage_complete"]
    assert item["response_id"] == "resp_fixture" and item["provider_request_id"] == "req_fixture"
    assert item["source_refs"] == task["source_refs"] and item["packet_ref"] == "fixture-packet"
    assert result["semantic_accuracy_validated"] is False and result["memberships_changed"] is False


def test_join_uses_custom_ids_and_preserves_frozen_task_order() -> None:
    task1, row1 = fixture("task-1")
    task2, row2 = fixture("task-2")
    result = parse_batch_results(wire(row2, row1), None, {"task-1": task1, "task-2": task2})
    assert [item["custom_id"] for item in result["items"]] == ["task-1", "task-2"]
    assert result["counts"]["valid"] == 2


def test_missing_ids_are_unknown_not_negative_or_invalid() -> None:
    task, _ = fixture()
    result = parse_batch_results(None, b"", {"task-1": task})
    assert result["missing"] == 1 and result["returned"] == 0 and result["expected"] == 1
    assert result["technical_failures"] == 1 and result["counts"]["unknown"] == 1
    item = result["items"][0]
    assert item["result"] is None and item["usage"] is None and item["missing"] is True


@pytest.mark.parametrize("mutation", ["literal", "schema", "json", "duplicate_json_key"])
def test_content_invalid_is_distinct_from_technical_and_keeps_usage(mutation: str) -> None:
    task, row = fixture()
    text_part = row["response"]["body"]["output"][1]["content"][0]
    output = json.loads(text_part["text"])
    if mutation == "literal":
        output["event"]["participants"][0]["surface"] = "Not present in fictional evidence"
        text_part["text"] = json.dumps(output)
    elif mutation == "schema":
        output["unexpected"] = "extra"
        text_part["text"] = json.dumps(output)
    elif mutation == "json":
        text_part["text"] = "not-json"
    else:
        text_part["text"] = '{"focus":"none","focus":"single"}'
    result = parse_batch_results(wire(row), None, {"task-1": task})
    item = result["items"][0]
    assert item["status"] == "invalid" and not item["technical_failure"]
    assert item["result"] is None and item["errors"] and item["usage_complete"]
    assert result["counts"]["invalid"] == 1 and result["usage_complete_count"] == 1


@pytest.mark.parametrize("mutation,expected", [
    ("wrong_model", "response:model_unavailable_or_mismatch"),
    ("missing_model", "response:model_unavailable_or_mismatch"),
    ("incomplete", "response:not_completed"),
    ("incomplete_details", "response:not_completed"),
    ("response_error", "response:not_completed"),
    ("http_error", "response:http_not_200"),
    ("refusal", "response:refusal"),
    ("tool_call", "response:unexpected_output_or_tool"),
    ("tools_enabled", "response:unexpected_tools"),
    ("multiple_messages", "response:not_single_message"),
    ("unfinished_message", "response:output_not_completed"),
    ("wrong_role", "response:unexpected_message_role"),
    ("missing_output", "response:output_missing_or_invalid"),
])
def test_technical_failures_do_not_become_valid_content(mutation: str, expected: str) -> None:
    task, row = fixture()
    body = row["response"]["body"]
    if mutation == "wrong_model":
        body["model"] = "gpt-6-luna-other-snapshot"
    elif mutation == "missing_model":
        body.pop("model")
    elif mutation == "incomplete":
        body["status"] = "incomplete"
    elif mutation == "incomplete_details":
        body["incomplete_details"] = {"reason": "max_output_tokens"}
    elif mutation == "response_error":
        body["error"] = {"code": "server_error"}
    elif mutation == "http_error":
        row["response"]["status_code"] = 429
    elif mutation == "refusal":
        body["output"][1]["content"] = [{"type": "refusal", "refusal": "Synthetic refusal."}]
    elif mutation == "tool_call":
        body["output"].append({"type": "function_call", "name": "unexpected"})
    elif mutation == "tools_enabled":
        body["tools"] = [{"type": "web_search"}]
    elif mutation == "multiple_messages":
        body["output"].append(deepcopy(body["output"][1]))
    elif mutation == "unfinished_message":
        body["output"][1]["status"] = "in_progress"
    elif mutation == "wrong_role":
        body["output"][1]["role"] = "user"
    else:
        body["output"] = None
    item = parse_batch_results(wire(row), None, {"task-1": task})["items"][0]
    assert item["status"] == "error" and item["technical_failure"] and item["result"] is None
    assert expected in item["errors"]
    assert item["usage"] == body["usage"]


@pytest.mark.parametrize("usage", [None, {}, {"input_tokens": True, "output_tokens": 1},
                                  {"input_tokens": 10, "output_tokens": -1},
                                  {"input_tokens": 10, "output_tokens": 1, "total_tokens": 99}])
def test_missing_or_malformed_usage_is_technical(usage: Any) -> None:
    task, row = fixture()
    row["response"]["body"]["usage"] = usage
    item = parse_batch_results(wire(row), None, {"task-1": task})["items"][0]
    assert item["status"] == "error" and item["technical_failure"] and not item["usage_complete"]
    assert "response:usage_missing_or_invalid" in item["errors"]


def test_error_file_joins_with_output_file_without_filling_missing() -> None:
    task, row = fixture()
    error = {"custom_id": "task-2", "response": None, "error": {"code": "batch_expired", "message": "Synthetic."}}
    result = parse_batch_results(wire(row), wire(error), {"task-1": task, "task-2": task, "task-3": task})
    assert result["counts"] == {"valid": 1, "invalid": 0, "error": 1, "unknown": 1}
    assert result["missing"] == 1 and result["returned"] == 2
    assert result["items"][1]["usage"] is None and result["items"][1]["technical_failure"]


@pytest.mark.parametrize("problem", ["duplicate", "foreign", "malformed", "nonobject", "invalid_utf8", "duplicate_key", "nan"])
def test_bad_file_join_fails_as_a_whole_without_partial_acceptance(problem: str) -> None:
    task, row = fixture()
    output = wire(row)
    if problem == "duplicate":
        error = wire(row)
    elif problem == "foreign":
        row["custom_id"] = "foreign"
        error = wire(row)
    else:
        error = {"malformed": b"{broken", "nonobject": b"[]", "invalid_utf8": b"\xff",
                 "duplicate_key": b'{"custom_id":"task-2","custom_id":"task-1"}',
                 "nan": b'{"custom_id":"task-2","value":NaN}'}[problem]
    with pytest.raises(ResearchError, match="batch_result_"):
        parse_batch_results(output, error, {"task-1": task})


def test_frozen_packet_and_expected_model_checked_before_interpreting_output() -> None:
    task, row = fixture()
    task["packet"]["model_input"]["coverage"]["truncated"] = True
    with pytest.raises(ResearchError, match="frozen_task_contract"):
        parse_batch_results(wire(row), None, {"task-1": task})
    task, row = fixture()
    task["body"]["model"] = "different-model"
    with pytest.raises(ResearchError, match="frozen_task_contract"):
        parse_batch_results(wire(row), None, {"task-1": task})


def test_nonsingle_valid_focus_counts_and_no_mutation() -> None:
    task, row = fixture()
    body = row["response"]["body"]
    output = json.loads(body["output"][1]["content"][0]["text"])
    output.update(focus="none", reason="no_particular_occurrence", event=None)
    body["output"][1]["content"][0]["text"] = json.dumps(output)
    original = deepcopy(task)
    result = parse_batch_results(wire(row), None, {"task-1": task})
    assert result["focus_counts"]["none"] == 1 and result["items"][0]["result"]["event"] is None
    assert task == original
