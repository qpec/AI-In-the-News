"""Technical categories and separate-owner read-only audit; no model inference."""
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import diagnose_dossier_failures_v8 as diagnostic  # noqa: E402


def case(mode, phase="card_quality"):
    packet = {"kind": "decisions" if phase == "seed" else "responses", "input_tokens_proxy": 5000,
        "document_ids": ["private-source"], "request": {"model": "gpt-6-luna", "input": "UNPROJECTED source",
        "max_output_tokens": 2000 if phase == "card_quality" else 0}}
    usage = {"input_tokens": 100, "output_tokens": 2000, "output_tokens_details": {"reasoning_tokens": 1900}}
    envelope = {"model": "gpt-6-luna", "usage": usage, "payload": {"status": "completed", "output": [
        {"type": "message", "content": [{"type": "output_text", "text": "UNPROJECTED output"}]}]},
        "raw_response": {"http_status": 200, "dispatch_started": True, "unknown_outcome": False}}
    error, http, parsed = None, 200, "valid-artifact"
    if mode == "timeout":
        envelope.update(model=None, usage=None, payload=None, raw_response={"dispatch_started": True,
            "unknown_outcome": True, "error_type": "TimeoutError"})
        error, http, parsed = "dossier_http_not_success", None, None
    elif mode == "incomplete":
        envelope["payload"].update(status="incomplete", incomplete_details={"reason": "max_output_tokens"})
        error, parsed = "ResearchError:dossier_card_quality_incomplete", None
    elif mode == "usage":
        envelope["usage"] = {"input_tokens": 100}
    elif mode == "http":
        envelope.update(model=None, usage=None, payload=None, raw_response={"http_status": 400,
            "dispatch_started": True, "unknown_outcome": False, "response_text": canonical({"error": {
                "type": "invalid_request_error", "code": "invalid_json_schema", "param": "text.format",
                "message": "UNPROJECTED provider prose"}})})
        error, http, parsed = "dossier_http_not_success", 400, None
    billed = diagnostic.runner.BASE.billed(packet, SimpleNamespace(model=envelope["model"], usage=envelope["usage"]))
    hold = billed is None or envelope["raw_response"].get("unknown_outcome", False)
    item = {"_record_id": mode + phase, "task_key": mode + phase, "at": "2026-10-23T17:34:27+00:00", "phase": phase,
        "http_status": http, "parsed": parsed, "hold": hold, "validation_error": error, "cost_nanousd": billed,
        "reserved_nanousd": diagnostic.runner.BASE.reserve(packet) if hold else 0}
    return item, packet, envelope


@pytest.mark.parametrize("mode,held", [("valid", False), ("timeout", True), ("incomplete", False), ("usage", True), ("http", True)])
def test_technical_cause_separates_incomplete_known_cost_from_unknown_billing(mode, held):
    item, packet, envelope = case(mode)
    result = diagnostic.technical_view(item, packet, envelope)
    assert result["hold"] is held and "UNPROJECTED" not in canonical(result)
    if mode == "timeout":
        assert result["transport_error_type"] == "TimeoutError"
        assert set(result["hold_causes"]) == {"transport_unknown_outcome", "response_model_missing_or_mismatch", "dossier_usage_missing"}
    elif mode == "incomplete":
        assert result["incomplete_reason"] == "max_output_tokens" and not result["hold_causes"]
        assert result["observed_usage"]["output_tokens_details"]["reasoning_tokens"] == 1900
    elif mode == "usage":
        assert result["usage_error"] == "dossier_output_usage_missing"
    elif mode == "http":
        assert result["provider_error_code"] == "invalid_json_schema" and result["provider_error_message_sha256"]


def test_numeric_usage_drops_untrusted_extra_content_and_changed_billing_fails():
    assert diagnostic.numeric_usage({"input_tokens": 7, "comment": "UNPROJECTED", "output_tokens_details": {
        "reasoning_tokens": 2, "reason": "UNPROJECTED"}}) == {"input_tokens": 7, "output_tokens_details": {"reasoning_tokens": 2}}
    item, packet, envelope = case("valid")
    item["cost_nanousd"] += 1
    with pytest.raises(AuditError, match="billing_estimate_changed"):
        diagnostic.technical_view(item, packet, envelope)


class Fixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment_v8", "fixture", {
            "implementation": diagnostic.runner.implementation(), "parent_plan": "plan"})
        for mode, phase in (("timeout", "seed"), ("timeout", "card_quality"), ("incomplete", "card_quality"), ("valid", "card_quality")):
            item, packet, envelope = case(mode, phase)
            self.ledger.record(session, "cyber_dossier_response", mode + phase, {
                **{k: v for k, v in item.items() if not k.startswith("_")}, "execution_amendment": amendment,
                "plan": "plan", "packet": self.ledger.artifacts.put(packet), "response": self.ledger.artifacts.put(envelope)})
        report = self.ledger.record(session, "cyber_dossier_report", "fixture", {
            "execution_amendment": amendment, "stored_responses": 4, "new_unresolved_holds": 2, "at": "2026-10-23T17:34:27+00:00"})
        return amendment, report


def test_registered_observer_keeps_case_ids_private_and_source_head_unchanged(tmp_path, monkeypatch):
    active, owner = tmp_path / "active", tmp_path / "observer"
    fixture = Fixture(active, config=Config(offline=True))
    try:
        amendment, report = fixture.execute("status", {}, objective="Synthetic technical responses", actor="test")
    finally:
        fixture.close()
    for key, value in {"ACTIVE_OWNER": active, "AMENDMENT": amendment, "REPORT": report,
                       "EXPECTED_TOTAL": 4, "EXPECTED_NEW_HOLDS": 2}.items():
        monkeypatch.setattr(diagnostic, key, value)
    source = diagnostic.Source(active)
    before = source.head()
    source.close()
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        diagnostic.Diagnostic(active, config=Config(offline=True))
    study = diagnostic.Diagnostic(owner, config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Synthetic diagnosis", actor="test")
        assert result["all_new_holds"]["responses"] == 2 and result["all_new_seed_failures"]["responses"] == 1
        assert result["all_new_card_quality_failures"]["responses"] == 2
        assert result["last_card_quality_wave"]["responses"] == 3
        assert result["new_model_calls"] == result["new_cost_nanousd"] == 0 and not result["holds_released"]
        assert "cases" not in result and "UNPROJECTED" not in canonical(result)
        cases = study.ledger.artifacts.read(result["protected_cases_artifact"])
        assert len(cases) == 4 and "UNPROJECTED" not in canonical(cases)
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()
    source = diagnostic.Source(active)
    assert source.head() == before
    source.close()
