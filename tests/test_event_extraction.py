"""Synthetic extraction mechanics/transport only; no source store or models."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from newsresearch.common import ResearchError
from newsresearch.event_extraction_contract import (
    MAX_EVENTS, TASK_INSTRUCTION, WORKER_RULES, answer_schema, build_request, validate_output, validate_request,
)
from newsresearch.event_extraction_provider import ExtractionProvider, build_prompt


def paragraph(identifier, text, start=0):
    return {"id": identifier, "source_id": "synthetic-source", "ordinal": 0,
            "start": start, "end": start + len(text), "text": text,
            "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def packet():
    first = "Aster announced Model V2 in Delft on 2026-01-02."
    second = "The company said it would launch the product later."
    return build_request({"source_version": "synthetic-source", "body": first + "\n\n" + second,
                          "title": "Aster's announcement", "published_at": "2026-01-03T12:00:00Z"},
                         [paragraph("p1", first), paragraph("p2", second, len(first) + 2)],
                         versions={"protocol": "synthetic-protocol", "prompt": "synthetic-prompt"})


def claim(quote="Aster announced Model V2 in Delft on 2026-01-02.", passage_id="p1"):
    return {"passage_id": passage_id, "quote": quote}


def event():
    return {"local_id": "e1", "event_type": "product announcement", "summary": "Aster announced Model V2.",
            "action": "announced Model V2", "trigger": "announced",
            "participants": [{"name": "Aster", "type": "organization", "role": "announcer", "evidence": [claim()]},
                             {"name": "Model V2", "type": "product", "role": "announced_product", "evidence": [claim()]}],
            "time": {"text": "2026-01-02", "start": "2026-01-02", "end": "2026-01-02", "precision": "day",
                     "basis": "explicit", "evidence": [claim()]},
            "locations": [{"name": "Delft", "evidence": [claim()]}],
            "factuality": {"polarity": "affirmative", "actuality": "occurred", "certainty": "asserted",
                           "conditional": False, "evidence": [claim()]},
            "attribution": [], "identifiers": [{"kind": "product_version", "value": "V2", "evidence": [claim()]}],
            "prominence": "main", "specificity": "specific", "evidence": [claim()]}


def answer():
    return {"source_version": "synthetic-source", "status": "events_found", "inspected_passage_ids": ["p1", "p2"],
            "coverage_complete": True, "limitation": None, "events": [event()]}


def test_full_source_contract_and_exact_field_evidence_offsets():
    request = packet()
    validate_request(request)
    Draft202012Validator.check_schema(answer_schema())
    assert "ordinal" not in request["evidence"][0]
    result = validate_output(answer(), request)
    assert result["status"] == "valid" and result["extraction_status"] == "events_found"
    assert result["event_count"] == 1
    assert result["full_source_supplied"] is True and result["passage_coverage_complete"] is True
    assert result["human_validated"] is False and result["semantic_entailment_validated"] is False
    assert result["memberships_changed"] is False
    assert result["events"][0]["mention_id"] == validate_output(answer(), request)["events"][0]["mention_id"]
    for reference in result["evidence_references"]:
        assert reference["source_version"] == "synthetic-source"
        assert request["body"][reference["source_start"]:reference["source_end"]] == reference["quote"]
        assert reference["passage_hash"] == request["evidence"][0]["text_hash"]
    assert {reference["field"] for reference in result["evidence_references"]} >= {
        "events[0]", "events[0].participants[0]", "events[0].time", "events[0].locations[0]", "events[0].factuality"}


def test_cross_sentence_roles_and_negated_future_event_remain_distinct():
    request = packet()
    output = answer()
    second = event()
    second.update(local_id="e2", event_type="planned product launch", summary="The company reported a future product launch.",
                  action="would launch", trigger="launch", evidence=[claim(request["evidence"][1]["text"], "p2")],
                  participants=[{"name": "Aster", "type": "organization", "role": "planned_launcher", "evidence": [claim()]}],
                  time=None, locations=[], identifiers=[],
                  attribution=[{"name": "company", "evidence": [claim(request["evidence"][1]["text"], "p2")]}])
    second["factuality"] = {"polarity": "affirmative", "actuality": "planned", "certainty": "asserted", "conditional": None,
                            "evidence": [claim(request["evidence"][1]["text"], "p2")]}
    output["events"].append(second)
    result = validate_output(output, request)
    assert len(result["events"]) == 2
    assert result["events"][1]["factuality"]["actuality"] == "planned"
    assert result["events"][1]["evidence"][0]["source_start"] == request["evidence"][1]["start"]
    assert result["events"][0]["mention_id"] != result["events"][1]["mention_id"]


@pytest.mark.parametrize("mutation", ["omitted_paragraph", "overlap", "wrong_source", "wrong_hash", "wrong_offsets", "duplicate_id"])
def test_full_body_integrity_rejects_omissions_and_bad_mapping(mutation):
    request = packet()
    source = {**request["source"], "body": request["body"]}
    paragraphs = deepcopy(request["evidence"])
    if mutation == "omitted_paragraph":
        paragraphs.pop()
    elif mutation == "overlap":
        paragraphs.append({**paragraphs[0], "id": "p3"})
    elif mutation == "wrong_source":
        paragraphs[0]["source_id"] = "foreign-source"
    elif mutation == "wrong_hash":
        paragraphs[0]["text_hash"] = "0" * 64
    elif mutation == "wrong_offsets":
        paragraphs[0]["end"] -= 1
    else:
        paragraphs[1]["id"] = "p1"
    with pytest.raises(ResearchError, match="event_extraction_"):
        build_request(source, paragraphs, versions=request["versions"])


@pytest.mark.parametrize("field", ["instructions", "parameters", "schema", "body", "source", "evidence"])
def test_frozen_request_tampering_is_rejected(field):
    request = packet()
    if field == "instructions":
        request[field] += " changed"
    elif field == "parameters":
        request[field]["codex_model"] = "different"
    elif field == "schema":
        request[field]["properties"]["events"]["maxItems"] = 100
    elif field == "body":
        request[field] += " additional nonwhitespace"
    elif field == "source":
        request[field]["body_sha256"] = "0" * 64
    else:
        request[field][0]["text"] += " altered"
    with pytest.raises(ResearchError, match="event_extraction_"):
        validate_request(request)


@pytest.mark.parametrize("mutation,match", [
    ("missing_coverage", "incomplete_declared_coverage"),
    ("out_of_frame", "unknown_passage"),
    ("wrong_quote", "quote_not_exact_or_ambiguous"),
    ("unsupported_name", "literal_not_grounded"),
    ("unsupported_trigger", "literal_not_grounded"),
    ("duplicate_id", "duplicate_local_id"),
    ("duplicate_quote", "duplicate_evidence"),
    ("unsupported_source", "output_source_mismatch"),
    ("empty_evidence", "output_schema_invalid"),
    ("blank_summary", "blank_field"),
])
def test_invalid_claims_and_coverage_are_not_accepted(mutation, match):
    output = answer()
    item = output["events"][0]
    if mutation == "missing_coverage":
        output["inspected_passage_ids"].pop()
    elif mutation == "out_of_frame":
        item["evidence"][0]["passage_id"] = "foreign"
    elif mutation == "wrong_quote":
        item["evidence"][0]["quote"] += " unsupported"
    elif mutation == "unsupported_name":
        item["participants"][0]["name"] = "Invented Corporation"
    elif mutation == "unsupported_trigger":
        item["trigger"] = "invented launch"
    elif mutation == "duplicate_id":
        output["events"].append(deepcopy(item))
    elif mutation == "duplicate_quote":
        item["evidence"].append(deepcopy(item["evidence"][0]))
    elif mutation == "unsupported_source":
        output["source_version"] = "foreign-source"
    elif mutation == "empty_evidence":
        item["participants"][0]["evidence"] = []
    else:
        item["summary"] = "   "
    with pytest.raises(ResearchError, match=match):
        validate_output(output, packet())


def test_ambiguous_repeated_quote_needs_longer_exact_context():
    text = "Aster announced a model. Aster announced a service."
    request = build_request({"source_version": "synthetic-source", "body": text}, [paragraph("p1", text)],
                            versions={"protocol": "synthetic-protocol"})
    output = answer()
    output["inspected_passage_ids"] = ["p1"]
    output["events"][0]["evidence"] = [claim("Aster announced")]
    with pytest.raises(ResearchError, match="quote_not_exact_or_ambiguous"):
        validate_output(output, request)


@pytest.mark.parametrize("start,end,precision,basis,match", [
    ("2026-02-30", "2026-02-30", "day", "explicit", "time_date_invalid"),
    ("20260102", "20260102", "day", "explicit", "time_date_invalid"),
    ("2026-01-03", "2026-01-02", "range", "explicit", "interval_reversed"),
    ("2026-01-02", None, "range", "explicit", "interval_incomplete"),
    ("2026-01-02", "2026-01-02", "day", "unresolved", "unresolved_time_normalized"),
    ("2026-01-02", "2026-01-02", "unknown", "explicit", "unknown_time_normalized"),
    ("2026-01-02", "2026-01-03", "day", "explicit", "day_interval_invalid"),
])
def test_temporal_mechanics_preserve_ambiguity(start, end, precision, basis, match):
    output = answer()
    output["events"][0]["time"].update(start=start, end=end, precision=precision, basis=basis)
    with pytest.raises(ResearchError, match=match):
        validate_output(output, packet())


def test_partial_dates_and_missing_publication_never_force_normalization():
    output = answer()
    output["events"][0]["time"].update(start=None, end=None, precision="unknown", basis="unresolved")
    assert validate_output(output, packet())["events"][0]["time"]["start"] is None
    request = packet()
    request["source"]["published_at"] = None
    output["events"][0]["time"]["basis"] = "relative_to_publication"
    with pytest.raises(ResearchError, match="relative_time_publication_unavailable"):
        validate_output(output, request)


def test_empty_partial_and_capped_results_have_distinct_processing_states():
    output = answer()
    output.update(status="no_event", events=[], limitation="This hypothetical fixture is generic discussion.")
    assert validate_output(output, packet())["extraction_status"] == "no_event"
    output["coverage_complete"] = False
    with pytest.raises(ResearchError, match="status_inconsistent"):
        validate_output(output, packet())
    output.update(status="insufficient_evidence", events=[event()], limitation="Could not finish all events.")
    partial = validate_output(output, packet())
    assert partial["negative_finding"] is False and partial["coverage_complete"] is False
    output["coverage_complete"] = True
    with pytest.raises(ResearchError, match="status_inconsistent"):
        validate_output(output, packet())
    output["coverage_complete"] = False
    output["status"] = "events_found"
    with pytest.raises(ResearchError, match="status_inconsistent"):
        validate_output(output, packet())
    output.update(status="insufficient_evidence", events=[{**event(), "local_id": f"e{i}"} for i in range(MAX_EVENTS + 1)])
    with pytest.raises(ResearchError, match="output_schema_invalid"):
        validate_output(output, packet())


def test_planned_conditional_and_possible_remain_separate_factuality_axes():
    text = "Aster said it plans to launch if approval is granted; the launch is possible."
    request = build_request({"source_version": "synthetic-source", "body": text}, [paragraph("p1", text)],
                            versions={"protocol": "synthetic-protocol"})
    output = answer()
    output["inspected_passage_ids"] = ["p1"]
    output["events"] = [{**event(), "trigger": "launch", "evidence": [claim(text)], "time": None,
                         "participants": [], "locations": [], "identifiers": [],
                         "factuality": {"polarity": "affirmative", "actuality": "planned", "certainty": "asserted",
                                        "conditional": True, "evidence": [claim(text)]}}]
    result = validate_output(output, request)
    assert result["events"][0]["factuality"]["actuality"] == "planned"
    assert result["events"][0]["factuality"]["conditional"] is True
    output["events"][0]["factuality"]["actuality"] = "possible"
    output["events"][0]["factuality"]["conditional"] = None
    assert validate_output(output, request)["events"][0]["factuality"]["actuality"] == "possible"


@pytest.fixture
def clean_auth(monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def stream(extra=None):
    events = [{"type": "thread.started"}, {"type": "turn.started"}]
    if extra is not None:
        events.append(extra)
    events.extend([{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer())}},
                   {"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 200}}])
    return "\n".join(json.dumps(item) for item in events)


def test_exact_worker_manifest_uses_full_body_once_and_pinned_model(tmp_path, clean_auth):
    calls = []
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=stream(), stderr="", returncode=0)
    request = packet()
    provider = ExtractionProvider(tmp_path / "workers", runner=runner)
    prepared = provider.prepare(request)
    visible = json.loads(prepared.stdin)
    assert set(visible) == {"boundary", "task", "instructions", "source", "evidence", "schema"}
    assert prepared.stdin == build_prompt(request)
    assert visible["instructions"] == TASK_INSTRUCTION
    assert [row["id"] for row in visible["evidence"]] == ["p1", "p2"]
    assert all(prepared.stdin.count(row["text"]) == 1 for row in request["evidence"])
    assert "body" not in visible and "versions" not in visible
    manifest = prepared.manifest()
    assert manifest["worker_rules"] == WORKER_RULES
    assert manifest["configured_model"] == "gpt-6-luna" and manifest["reasoning_effort"] == "low"
    assert manifest["transport"] == "codex-cli-event-extraction-v1"
    assert manifest["schema_file_utf8"] == (prepared.cwd / "response-schema.json").read_text(encoding="utf-8")
    assert (prepared.cwd / "AGENTS.md").read_text(encoding="utf-8") == WORKER_RULES
    assert prepared.command[-3:] == ("-c", 'model_reasoning_effort="low"', "-")
    response = provider.complete_prepared(prepared)
    assert validate_output(response.payload, request)["status"] == "valid"
    assert response.model is None and response.request_id is None
    assert response.usage == {"input_tokens": 100, "output_tokens": 200}
    assert calls[0][1]["input"] == prepared.stdin and calls[0][1]["shell"] is False


@pytest.mark.parametrize("change", ["AGENTS.md", "response-schema.json", "command", "stdin"])
def test_worker_tampering_never_dispatches(tmp_path, clean_auth, change):
    calls = []
    provider = ExtractionProvider(tmp_path / "workers", runner=lambda *args, **kwargs: calls.append(kwargs))
    prepared = provider.prepare(packet())
    if change in {"AGENTS.md", "response-schema.json"}:
        (prepared.cwd / change).write_text("changed", encoding="utf-8")
    elif change == "command":
        prepared = replace(prepared, command=(*prepared.command, "changed"))
    else:
        prepared = replace(prepared, stdin=prepared.stdin + " ")
    with pytest.raises(ResearchError, match="changed"):
        provider.complete_prepared(prepared)
    assert not calls


def test_overlarge_input_keys_and_model_changes_do_not_dispatch(tmp_path, clean_auth, monkeypatch):
    calls = []
    with pytest.raises(ResearchError, match="too_large_no_dispatch"):
        ExtractionProvider(tmp_path / "small", max_input_bytes=1, runner=lambda *args, **kwargs: calls.append(kwargs)).complete(packet())
    with pytest.raises(ResearchError, match="model_or_effort_changed"):
        ExtractionProvider(tmp_path / "model", {"codex_model": "different"})
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-presence-only")
    with pytest.raises(ResearchError, match="api_key_environment_forbidden"):
        ExtractionProvider(tmp_path / "key").prepare(packet())
    assert not calls


def test_timeout_output_cap_and_tool_activity_are_not_valid_extractions(tmp_path, clean_auth):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 180, output=b"", stderr=b"")
    response = ExtractionProvider(tmp_path / "timeout", runner=timeout).complete(packet())
    assert response.payload is None and response.raw_response["unknown_outcome"] is True
    output = stream({"type": "item.started", "item": {"type": "command_execution"}})
    response = ExtractionProvider(tmp_path / "tools", runner=lambda *args, **kwargs:
                                  SimpleNamespace(stdout=output, stderr="", returncode=0)).complete(packet())
    assert response.payload is None and response.raw_response["failure"] == "codex_tool_or_unrecognized_activity"
    response = ExtractionProvider(tmp_path / "output", max_output_bytes=1, runner=lambda *args, **kwargs:
                                  SimpleNamespace(stdout=stream(), stderr="", returncode=0)).complete(packet())
    assert response.payload is None and response.raw_response["failure"] == "codex_output_acceptance_limit_exceeded"
