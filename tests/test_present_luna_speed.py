"""Fictional saved-result replay tests; no live owner, sources or model calls."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.luna_speed_provider import contract
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import present_luna_speed as reporting
finally:
    sys.path.pop(0)


def fixture_inputs():
    _, single = contract.fictional_example()
    none = {"schema_version": "luna-event-v2", "focus": "none", "reason": "no_particular_occurrence",
            "refs": ["p1"], "excluded": [], "event": None}
    tasks = [{"source_version": f"fictional-source-{i}", "task_key": f"fictional-task-{i}",
              "title": f"Fictional source {i}", "url": f"https://example.invalid/{i}"} for i in range(1, 8)]
    def row(i, status, returned, persisted, output=None, errors=(), usage=None, model=None):
        return {"source_version": tasks[i - 1]["source_version"], "task_key": tasks[i - 1]["task_key"],
                "attempt": f"fictional-attempt-{i}", "status": status, "return_offset": returned,
                "persistence_offset": persisted, "dispatch_offset": None if status == "not_dispatched" else i,
                "output": deepcopy(output), "errors": list(errors), "observed_model": model, "usage": usage,
                "response": f"fictional-response-{i}", "assessment": f"fictional-assessment-{i}"}
    usage = {"input_tokens": 10, "output_tokens": 5}
    rows = [row(1, "valid", 90, 100, single, usage=usage),
            row(2, "invalid", 200, 205, errors=("event.action:surface_not_grounded", "event.participants.0:surface_not_grounded")),
            row(3, "valid", 598, 599, none, usage=usage, model="gpt-6-luna"),
            row(4, "valid", 599, 601, single, usage=usage, model="gpt-6-luna"),
            row(5, "unknown", 610, 611, errors=("response:unknown_outcome",)),
            row(6, "not_dispatched", 600.1, 600.2, errors=("deadline_before_dispatch",))]
    plan = {"method": "luna-fulltext-codex-speed-v2", "failure_policy": "continue_content_invalid_stop_transport",
            "versions": {"protocol": "fictional-protocol"}, "limits": {"seconds": 600}, "tasks": tasks,
            "corpus_id": "incident-reports", "config": {"model": "gpt-6-luna"}, "preparation_seconds": 4.5}
    result = {"method": plan["method"], "versions": plan["versions"], "plan": "fictional-plan",
              "outcomes": list(reversed(rows)), "pending": 2,
              "timing": {"elapsed_seconds": 611.5, "stop_reason": "deadline", "peak_in_flight": 4,
                         "canaries_required": 2, "canaries_returned": 2, "canaries_valid": 1}}
    return result, plan


def test_primary_counts_focus_missingness_and_attempts_are_separate():
    summary = reporting.summarize(*fixture_inputs())
    assert summary["primary_valid"] == 2 and summary["valid_total"] == 3
    assert summary["valid_returned_by_deadline"] == 3
    assert summary["valid_outside_or_unobserved_primary_window"] == 1
    assert summary["focus_primary"] == {"single": 1, "multiple": 0, "none": 1, "uncertain": 0}
    assert summary["provider_calls"] == 5 and summary["attempt_intents"] == 6
    assert summary["invalid"] == summary["unknown"] == summary["not_dispatched"] == 1
    assert summary["pending"] == 2 and summary["late_returns"] == 1
    assert summary["returned_by_deadline"] == 4
    assert summary["usage_reported"] == {"input_tokens": 30, "output_tokens": 15}
    assert summary["usage_missing_responses"] == 2
    assert summary["observed_models"] == {"gpt-6-luna": 2, "unavailable": 3}
    assert summary["error_suffix_counts"]["surface_not_grounded"] == 2
    assert summary["initial_runtime_preflight_seconds"] is None
    assert summary["canaries_required"] == summary["canaries_returned"] == 2
    assert summary["canaries_valid"] == 1


def test_examples_and_outputs_follow_frozen_order_not_completion_order():
    summary = reporting.summarize(*fixture_inputs())
    assert [row["source_version"] for row in summary["single_examples"]] == ["fictional-source-1"]
    assert summary["other_example"]["source_version"] == "fictional-source-3"
    assert [row["source_version"] for row in summary["article_outputs"]] == [f"fictional-source-{i}" for i in range(1, 7)]
    assert summary["article_outputs"][1]["output"] is None
    assert summary["article_outputs"][1]["response"] == "fictional-response-2"
    assert summary["human_validated"] is False and summary["memberships_changed"] is False


def test_missing_timing_is_unavailable_not_imputed_as_within_window():
    result, plan = fixture_inputs()
    by_source = {row["source_version"]: row for row in result["outcomes"]}
    by_source["fictional-source-1"]["persistence_offset"] = None
    by_source["fictional-source-5"]["return_offset"] = None
    summary = reporting.summarize(result, plan)
    assert summary["primary_valid"] == 1
    assert summary["valid_missing_persistence_timing"] == 1
    assert summary["missing_return_timing"] == 1 and summary["late_returns"] == 0
    assert summary["unknown_sources_equal_late_sources"] is None


def test_unknown_late_overlap_uses_article_identity_and_preserves_exact_saved_timings():
    summary = reporting.summarize(*fixture_inputs())
    assert summary["unknown_late_overlap"] == 1
    assert summary["unknown_sources_equal_late_sources"] is True
    assert summary["unknown_timing"] == [{"source_version": "fictional-source-5", "status": "unknown",
                                         "return_offset": 610, "persistence_offset": 611}]
    text = reporting.render(summary)
    assert "Unknown/late overlap: 1; identical article sets: yes" in text
    assert "fictional-source-5: unknown; return 610.000000s; persisted 611.000000s" in text
    assert "do not establish why an outcome is unknown" in text


def test_equal_unknown_and_late_counts_do_not_imply_equal_articles():
    result, plan = fixture_inputs()
    by_source = {row["source_version"]: row for row in result["outcomes"]}
    by_source["fictional-source-5"].update(return_offset=500, persistence_offset=501)
    by_source["fictional-source-4"].update(return_offset=610, persistence_offset=611)
    summary = reporting.summarize(result, plan)
    assert summary["unknown"] == summary["late_returns"] == 1
    assert summary["unknown_late_overlap"] == 0
    assert summary["unknown_sources_equal_late_sources"] is False


def test_absent_canary_metadata_is_unavailable_not_zero():
    result, plan = fixture_inputs()
    for field in ("canaries_required", "canaries_returned", "canaries_valid"):
        result["timing"].pop(field)
    summary = reporting.summarize(result, plan)
    assert all(summary[field] is None for field in ("canaries_required", "canaries_returned", "canaries_valid"))
    assert "unavailable/unavailable clean transport returns" in reporting.render(summary)


@pytest.mark.parametrize("field,value", [("canaries_returned", 3), ("canaries_valid", 3),
                                         ("canaries_valid", True), ("canaries_required", -1)])
def test_invalid_canary_counter_metadata_fails_closed(field, value):
    result, plan = fixture_inputs()
    result["timing"][field] = value
    with pytest.raises(AuditError, match="canary_counters"):
        reporting.summarize(result, plan)


@pytest.mark.parametrize("fault", ["duplicate", "outside_frame", "pending", "method", "versions", "valid_missing_focus"])
def test_inconsistent_result_inputs_fail_closed(fault):
    result, plan = fixture_inputs()
    if fault == "duplicate":
        result["outcomes"].append(result["outcomes"][0])
    elif fault == "outside_frame":
        result["outcomes"][0]["source_version"] = "not-in-frame"
    elif fault == "pending":
        result["pending"] = 0
    elif fault == "method":
        result["method"] = "changed"
    elif fault == "versions":
        result["versions"] = {"protocol": "changed"}
    elif fault == "valid_missing_focus":
        result["outcomes"][-1]["output"].pop("focus")
    with pytest.raises(AuditError):
        reporting.summarize(result, plan)


def test_compact_markdown_contains_actual_counts_examples_and_capture_limit():
    text = reporting.render(reporting.summarize(*fixture_inputs()))
    assert "2 mechanically valid articles durably recorded within 10 minutes" in text
    assert "1 invalid, 1 unknown; 2 pending" in text
    assert "single **1**, multiple **0**, none **1**, uncertain **0**" in text
    assert r"surface\_not\_grounded 2" in text
    assert "Field-validation/transport error occurrences" in text and "not article counts" in text
    assert "One article can contribute several occurrences" in text
    assert "checks schema and literal citation matches" in text
    assert "semantic grounding, accuracy and event identity remain unreviewed" in text
    assert "establishes schema and literal grounding" not in text
    assert "Lumen Council (organization; p1, p2)" in text
    assert "https://example.invalid/1" in text
    assert "record_presentation does not support" in text
    assert "zero new model calls" in text
    assert "2/2 clean transport returns; 1/2 passed content checks" in text
    assert "V2 policy continued after content-invalid outputs" in text
    assert len(text.split()) < 500


def test_zero_primary_has_no_invented_event_examples():
    result, plan = fixture_inputs()
    for row in result["outcomes"]:
        if row["status"] == "valid":
            row["persistence_offset"] = 601
    summary = reporting.summarize(result, plan)
    assert summary["primary_valid"] == 0 and summary["single_examples"] == []
    assert all(value == 0 for value in summary["focus_primary"].values())
    assert "No single-event examples" in reporting.render(summary)


class FixtureResearch(reporting.SpeedPresentationResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("fixture") != "build":
            return super()._status(session, context, data)
        version = self._version(session, context, {"kind": "protocol", "key": "fictional-speed-replay",
            "content": {"method": "invented-result-fixture", "synthetic": True}})["id"]
        result, plan = fixture_inputs()
        plan["versions"] = result["versions"] = {"protocol": version}
        plan_id = self.ledger.record(session, "luna_speed_plan", "fictional-speed", plan)
        result["plan"] = plan_id
        result_id = self.ledger.record(session, "luna_speed_result", "fictional-speed", result)
        return {"result": result_id}


def call(engine, data):
    return engine.execute("status", data, objective="Synthetic compact-report integration check",
                          actor="test:fictional-speed-replay")


def test_offline_replay_registers_first_and_retains_exact_artifacts(tmp_path):
    engine = FixtureResearch(tmp_path / "protected", config=Config(offline=True))
    try:
        fixture = call(engine, {"fixture": "build"})
        report = call(engine, {"result": fixture["result"]})
        assert report["summary"]["primary_valid"] == 2
        assert report["record_presentation_supported"] is False
        assert Path(report["presentation_path"]).read_text(encoding="utf-8") == report["markdown"]
        machine = json.loads(Path(report["machine_outputs_path"]).read_text(encoding="utf-8"))
        assert len(machine["article_outputs"]) == 6
        assert machine["result"] == fixture["result"]
        assert machine["report_versions"] == report["report_versions"]
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        seen = list(engine.ledger.db.execute("SELECT seq,kind,payload FROM events ORDER BY seq"))
        inspection = next(row[0] for row in seen if row[1] == "speed.compact_report.inspection.intended")
        for version in report["report_versions"].values():
            created = engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (version,)).fetchone()[0]
            assert created < inspection
        again = call(engine, {"result": fixture["result"]})
        assert again["summary"] == report["summary"] and again["markdown"] == report["markdown"]
        engine.ledger.verify()
    finally:
        engine.close()


def test_failed_method_registration_prevents_replay(tmp_path, monkeypatch):
    engine = FixtureResearch(tmp_path / "protected", config=Config(offline=True))
    try:
        fixture = call(engine, {"fixture": "build"})
        original_record = engine.ledger.record
        original_get = engine.ledger.get
        gets = []
        def record(session, kind, *args, **kwargs):
            if kind == "protocol":
                raise AuditError("synthetic method-registration failure")
            return original_record(session, kind, *args, **kwargs)
        def get(identifier, *args, **kwargs):
            gets.append(identifier)
            return original_get(identifier, *args, **kwargs)
        monkeypatch.setattr(engine.ledger, "record", record)
        monkeypatch.setattr(engine.ledger, "get", get)
        with pytest.raises(AuditError, match="synthetic method-registration"):
            call(engine, {"result": fixture["result"]})
        assert fixture["result"] not in gets
    finally:
        engine.close()
