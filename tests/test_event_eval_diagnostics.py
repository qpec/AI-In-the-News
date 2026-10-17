"""Source-free synthetic structural replay tests; no inference or quality claim."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from newsresearch.event_eval_diagnostics import replay_anchor_pairs, technical_failure_details
from newsresearch.luna_lead_answers import EVENT_FIELDS, build_request, make_lead


def fixture() -> tuple[dict, dict, dict]:
    leads = []
    for source in ("source-a", "source-b", "source-c"):
        text = "Aster announced a research model on Monday in Delft."
        passage = {"id": f"{source}-paragraph", "source_id": source, "start": 0, "end": len(text),
                   "text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()}
        leads.append(make_lead(source, "Synthetic title", None, [passage]))
    request = build_request(leads=leads, versions={}, mode="anchor", anchor_source="source-a")
    payload = {"group_label": "uncertain", "rationale": "The supplied synthetic reports describe one announcement.",
               "partitions": [], "inspected_passage_ids": [p["id"] for p in request["evidence"]],
               "events": [{"source_version": lead["source_version"], "description": "research model announcement",
                           "action": "announced", "actors": ["Aster"], "event_date": "unknown",
                           "location": "unknown", "multiple_focal_events": False} for lead in leads],
               "claims": [{"source_version": p["source_id"], "passage_id": p["id"], "quote": p["text"],
                           "supports": list(EVENT_FIELDS)} for p in request["evidence"]],
               "relations": [{"source_version": "source-b", "label": "same_event"},
                             {"source_version": "source-c", "label": "different_event"}]}
    response = {"payload": payload, "raw_response": {
        "transport_status": "returned", "failure": None, "unknown_outcome": False, "exit_code": 0,
        "events": [{"type": "turn.started"}, {"type": "item.completed", "item": {"type": "agent_message"}},
                   {"type": "turn.completed"}],
        "started_at": "2026-10-17T10:00:00+00:00", "ended_at": "2026-10-17T10:00:03+00:00"}}
    outcome = {"status": "invalid", "request": "old-request", "response": "old-response", "attempt": "old-attempt"}
    return request, response, outcome


def test_diagnostics_report_only_counts_bytes_and_raw_iso_times() -> None:
    request, response, outcome = fixture()
    response["payload"]["inspected_passage_ids"].pop()
    response["payload"]["claims"][0]["quote"] = "Quote that never appeared."
    details = technical_failure_details(request, response, outcome)
    assert details["missing_inspected_ids"] == 1
    assert details["invalid_quote_count"] == 1
    assert details["unsupported_event_fields"]["action"] == 1
    assert details["latency_seconds"] == 3
    assert details["input_bytes"] > 0 and details["output_bytes"] > 0
    encoded = json.dumps(details)
    assert "Aster" not in encoded and "source-a" not in encoded and "Synthetic title" not in encoded
    assert "The supplied synthetic" not in encoded


def test_replay_preserves_old_labels_and_context_without_repairing_old_row() -> None:
    request, response, outcome = fixture()
    original = deepcopy((request, response, outcome))
    result = replay_anchor_pairs(request, response, outcome, versions={"protocol": "new-method-v1"})
    assert result["summary"]["eligible_pairs"] == 2
    assert result["summary"]["eligible_label_counts"] == {"same_event": 1, "different_event": 1}
    assert (request, response, outcome) == original
    assert result["summary"]["old_rows_modified"] == 0
    pair = result["relations"][0]
    assert pair["newanswer"]["support_span_ids"] == ["A1", "B1"]
    assert pair["original_refs"]["request"] == "old-request"
    assert pair["newvalidation"]["human_validated"] is False
    assert "source-a" not in json.dumps(result["summary"])


def test_group_diagnostics_do_not_expect_anchor_relations() -> None:
    request, response, outcome = fixture()
    request.update(mode="group", anchor_source=None)
    response["payload"]["relations"] = []
    details = technical_failure_details(request, response, outcome)
    assert details["relation_coverage"] == {"expected": 0, "returned": 0, "missing": 0,
                                            "extra": 0, "duplicates": 0}


@pytest.mark.parametrize("change", ["tool", "unknown", "failed", "uncompleted", "schema", "multiple"])
def test_transport_schema_and_endpoint_failures_are_not_replayed(change: str) -> None:
    request, response, outcome = fixture()
    if change == "tool":
        response["raw_response"]["events"].append({"type": "item.completed", "item": {"type": "command_execution"}})
    elif change == "unknown":
        response["raw_response"]["unknown_outcome"] = True
    elif change == "failed":
        outcome["status"] = "error"
    elif change == "uncompleted":
        response["raw_response"]["events"].pop()
    elif change == "schema":
        response["payload"]["relations"][0]["label"] = "invented"
    else:
        response["payload"]["events"][0]["multiple_focal_events"] = True
    assert replay_anchor_pairs(request, response, outcome, versions={})["summary"]["eligible_pairs"] == 0


def test_decisive_replay_needs_exact_nontrivial_old_quotes_from_both_ends() -> None:
    request, response, outcome = fixture()
    response["payload"]["claims"][0]["quote"] = "Aster"
    result = replay_anchor_pairs(request, response, outcome, versions={})
    assert result["summary"]["eligible_pairs"] == 0
    response["payload"]["relations"][0]["label"] = "uncertain"
    result = replay_anchor_pairs(request, response, outcome, versions={})
    assert result["summary"]["eligible_pairs"] == 1
    assert result["relations"][0]["label"] == "uncertain"
