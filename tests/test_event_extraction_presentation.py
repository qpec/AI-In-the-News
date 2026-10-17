"""Synthetic saved-result presentation checks; no corpus, network or models."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from newsresearch.common import AuditError, Context, ResearchError
from test_event_extraction_workflow import (
    OBJECTIVE, approve_and_run, fixture, install_transport,
)


SPEC = importlib.util.spec_from_file_location(
    "present_event_extraction", Path(__file__).resolve().parents[1] / "scripts/present_event_extraction.py")
assert SPEC is not None and SPEC.loader is not None
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def report(engine, result):
    root = engine.ledger.root
    engine.close()
    reader = reporter.EventExtractionReportResearch(root)
    try:
        value = reader.execute("luna_group_validation", {"phase": "report", "result": result["id"]},
            objective=OBJECTIVE, actor="test:synthetic")
        return value, reader
    except Exception:
        reader.close()
        raise


@pytest.mark.parametrize("failure", [None, "incomplete", "invalid", "unknown"])
def test_audited_report_preserves_saved_outputs_and_missingness(tmp_path, monkeypatch, failure):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    calls, _ = install_transport(engine, monkeypatch, plan, failure)
    result = approve_and_run(engine, plan)
    before = len(calls)
    value, reader = report(engine, result)
    try:
        assert len(calls) == before
        assert value["model_calls"] == value["embeddings_created"] == 0
        full, compact = (value["presentations"][name] for name in ("full", "compact"))
        for presentation in (full, compact):
            assert presentation["versions"] == plan["versions"]
            assert presentation["results"] == [
                {"kind": "luna_group_validation_result", "id": result["id"]},
                {"kind": "luna_group_validation_plan", "id": plan["id"]}]
            assert Path(presentation["content_path"]).read_text(encoding="utf-8") == presentation["markdown"]
            assert presentation["ui_delivery_verified"] is False
            assert "No memberships changed" in presentation["markdown"]
            assert "not accepted events or dossier counts" in presentation["markdown"]
            assert "12." in presentation["markdown"]
        if failure in {"invalid", "unknown"}:
            assert "0 provisional event mentions" in compact["markdown"]
            assert "11 pending" in compact["markdown"]
            assert "Entities:" not in compact["markdown"]
            assert "No usable extracted event or entity output" in compact["markdown"]
            assert "they carry no accepted supporting evidence" in compact["markdown"]
            assert "one exact supporting quote per mention" not in compact["markdown"]
        else:
            assert "Entities: Aster" in compact["markdown"]
            assert "Model V2" in compact["markdown"]
            assert "Delft" in compact["markdown"]
            assert "Evidence:" in compact["markdown"]
            assert "Mention ID:" in full["markdown"]
            assert ".participants" in full["markdown"]
            assert "2026-01-02" in compact["markdown"]
            assert ("1 incomplete" in compact["markdown"]) == (failure == "incomplete")
        assert reader.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == before
        reader.ledger.verify()
    finally:
        reader.close()


def test_mechanical_report_rejects_changed_source_and_summary_counts(tmp_path, monkeypatch):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    install_transport(engine, monkeypatch, plan)
    result = approve_and_run(engine, plan)
    root = engine.ledger.root
    engine.close()
    reader = reporter.EventExtractionReportResearch(root)
    try:
        changed = deepcopy(result)
        changed["event_count"] += 1
        actual_get = reader.ledger.get

        def changed_get(identifier, kind):
            return changed if identifier == result["id"] else actual_get(identifier, kind)

        monkeypatch.setattr(reader.ledger, "get", changed_get)
        with pytest.raises(ResearchError, match="coverage_changed"):
            reader.execute("luna_group_validation", {"phase": "report", "result": result["id"]},
                objective=OBJECTIVE, actor="test:synthetic")
    finally:
        reader.close()


def test_report_cannot_bypass_audited_entry(tmp_path):
    engine = reporter.EventExtractionReportResearch(tmp_path / "protected")
    try:
        with pytest.raises(AuditError, match="active audited"):
            engine._luna_group_validation("fake", Context(OBJECTIVE, "test:synthetic"),
                                          {"phase": "report", "result": "not-real"})
    finally:
        engine.close()


def test_safe_links_and_missing_time_are_explicit():
    assert reporter.source_link({"source_version": "id", "title": "[fake]", "url": "javascript:fake"}) == "\\[fake\\]"
    assert reporter.render_time(None) == "unavailable"
    assert "unresolved dates" in reporter.render_time({"text": "last year", "start": None,
        "end": None, "precision": "year", "basis": "unresolved"})


def test_no_event_is_unreviewed_outcome_not_confirmed_absence(tmp_path, monkeypatch):
    import test_event_extraction_workflow as fixture_module

    original_answer = fixture_module.answer

    def no_event(request):
        value = original_answer(request)
        value.update(status="no_event", events=[], limitation="Synthetic generic discussion only")
        return value

    monkeypatch.setattr(fixture_module, "answer", no_event)
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    install_transport(engine, monkeypatch, plan)
    result = approve_and_run(engine, plan)
    value, reader = report(engine, result)
    try:
        markdown = value["presentations"]["compact"]["markdown"]
        assert "12 complete articles" in markdown
        assert "0 provisional event mentions" in markdown
        assert "not a verified absence of events" in markdown
        assert "Synthetic generic discussion only" in markdown
    finally:
        reader.close()


def test_rejected_transport_payload_is_preview_only_not_promoted():
    from test_event_extraction import answer, packet

    payload = answer()
    raw = {"failure": "codex_output_acceptance_limit_exceeded", "stdout": "retained stdout",
           "stderr": "retained stderr", "events": [{"type": "item.completed",
           "item": {"type": "agent_message", "text": json.dumps(payload)}}]}
    diagnostic = reporter.rejected_diagnostic({"payload": None, "raw_response": raw, "model": None}, packet())
    assert diagnostic["payload_origin"] == "recovered_rejected_agent_message"
    assert diagnostic["replay_code"] == "mechanically_valid_but_original_rejection_preserved"
    assert diagnostic["accepted_or_provisional_mentions_added"] == 0
    assert diagnostic["preview"][0]["summary"] == payload["events"][0]["summary"]
    assert diagnostic["observed_model"] is None
    assert diagnostic["transport_failure"] == "codex_output_acceptance_limit_exceeded"


def test_rejected_contract_diagnostics_locate_schema_and_quote_errors():
    from test_event_extraction import answer, packet

    payload = answer()
    payload["events"][0]["evidence"][0]["quote"] = "An invented quotation."
    diagnostic = reporter.rejected_diagnostic({"payload": payload}, packet())
    assert diagnostic["replay_code"] == "event_extraction_literal_not_grounded"
    assert diagnostic["quote_failures"] == [{"path": "output.events[0].evidence[0]",
        "passage_exists": True, "exact_occurrences": 0}]
    payload["events"][0]["participants"][0]["type"] = "bad-type"
    diagnostic = reporter.rejected_diagnostic({"payload": payload}, packet())
    assert diagnostic["schema_errors"] == [{"path": ["events", 0, "participants", 0, "type"], "validator": "enum"}]
    assert diagnostic["replay_code"] == "event_extraction_output_schema_invalid"


def test_rejected_quote_diagnostic_counts_overlapping_matches():
    from test_event_extraction import answer, packet

    request, payload = packet(), answer()
    request["evidence"][0]["text"] = "aaaa"
    payload["events"][0]["evidence"][0]["quote"] = "aaa"
    diagnostic = reporter.rejected_diagnostic({"payload": payload}, request)
    assert {"path": "output.events[0].evidence[0]", "passage_exists": True,
            "exact_occurrences": 2} in diagnostic["quote_failures"]


@pytest.mark.parametrize(("collection", "field", "literal", "path"), [
    (None, "trigger", "revealed", "output.events[0].trigger"),
    ("participants", "name", "Aster Incorporated", "output.events[0].participants[0].name"),
    ("locations", "name", "Rotterdam", "output.events[0].locations[0].name"),
    ("attribution", "name", "Spokesperson", "output.events[0].attribution[0].name"),
    ("identifiers", "value", "V3", "output.events[0].identifiers[0].value"),
    ("time", "text", "next month", "output.events[0].time.text"),
])
def test_literal_diagnostics_cover_each_contract_field(collection, field, literal, path):
    from test_event_extraction import answer, packet

    payload = answer()
    item = payload["events"][0]
    if collection == "attribution":
        item["attribution"] = [{"name": literal, "evidence": deepcopy(item["evidence"])}]
    elif collection == "time":
        item["time"][field] = literal
    elif collection:
        item[collection][0][field] = literal
    else:
        item[field] = literal
    diagnostic = reporter.rejected_diagnostic({"payload": payload}, packet())
    assert diagnostic["replay_code"] == "event_extraction_literal_not_grounded"
    assert diagnostic["quote_failures"] == []
    assert diagnostic["literal_failures"] == [{"path": path, "literal": literal,
        "supporting_quotes": item["evidence"]}]


def test_report_hash_uses_module_load_snapshot_and_correction_is_append_only(tmp_path, monkeypatch):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    calls, _ = install_transport(engine, monkeypatch, plan)
    result = approve_and_run(engine, plan)
    original_read = Path.read_bytes

    def edited_script(path):
        return b"different file after module import" if path == Path(reporter.__file__) else original_read(path)

    monkeypatch.setattr(Path, "read_bytes", edited_script)
    value, reader = report(engine, result)
    try:
        profile = reader.ledger.get(value["profile"], "profile")["content"]
        assert profile["script_sha256"] == reporter.SCRIPT_SHA256
        assert profile["script_sha256"] != hashlib.sha256(b"different file after module import").hexdigest()
        prior = [item["id"] for item in value["presentations"].values()]
        corrected = reader.execute("luna_group_validation", {"phase": "report", "result": result["id"],
            "supersedes_presentations": prior, "correction_reason": "Synthetic presentation identity correction"},
            objective=OBJECTIVE, actor="test:synthetic")
        note = reader.ledger.get(corrected["correction_note"], "note")["content"]
        assert note["supersedes_presentations"] == prior
        assert note["prior_presentations_preserved"] is True
        assert note["model_results_changed"] is False
        assert len(calls) == 12
        for identifier in prior:
            assert reader.ledger.get(identifier, "result_presentation")["versions"] == plan["versions"]
        with pytest.raises(ResearchError, match="correction_result_changed"):
            reader.execute("luna_group_validation", {"phase": "report", "result": result["id"],
                "supersedes_presentations": [plan["presentation"]["id"]], "correction_reason": "Wrong result"},
                objective=OBJECTIVE, actor="test:synthetic")
    finally:
        reader.close()


def test_concise_chat_preserves_all_rejected_proposals_without_pending_titles(tmp_path, monkeypatch):
    import test_event_extraction_workflow as fixture_module

    original_answer = fixture_module.answer

    def rejected_answer(request):
        payload = original_answer(request)
        seed = payload["events"][0]
        payload["events"] = []
        for number in range(15):
            event = deepcopy(seed)
            event.update(local_id=f"e{number}", summary=f"Verbatim synthetic proposal {number}.")
            event["participants"][0]["name"] = f"Aster Incorporated {number}"
            payload["events"].append(event)
        return payload

    monkeypatch.setattr(fixture_module, "answer", rejected_answer)
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    calls, _ = install_transport(engine, monkeypatch, plan)
    result = approve_and_run(engine, plan)
    value, reader = report(engine, result)
    try:
        chat = value["presentations"]["chat"]
        text = chat["markdown"]
        assert len(calls) == 1
        assert "1/12 article attempts" in text
        assert "0 complete" in text and "1 invalid" in text and "11 pending" in text
        assert "0 usable provisional event mentions; 15 rejected raw proposals" in text
        assert "0 new embeddings" in text
        assert "Rejected, unvalidated raw model output" in text
        assert "Literal mismatches: **15**" in text
        assert "output.events[0].participants[0].name" in text
        assert "output.events[1].participants[0].name" not in text
        assert text.count("Supplied quote:") == 1
        assert text.count("https://example.test/extraction/") == 1
        assert "not dispatched" not in text
        for number in range(15):
            assert f"Verbatim synthetic proposal {number}." in text
            assert f"Aster Incorporated {number} [organization; announcer]" in text
        assert Path(chat["content_path"]).read_text(encoding="utf-8") == text
        assert chat["versions"] == plan["versions"]
        assert chat["ui_delivery_verified"] is False
        assert {"full", "compact", "chat"} == set(value["presentations"])
    finally:
        reader.close()
