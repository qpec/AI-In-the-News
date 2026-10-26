"""Source-free technical diagnosis, with a read-only audited fixture."""
from pathlib import Path
import json
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import diagnose_dossier_seed_v7 as diagnostic  # noqa: E402


def packet_and_reply(n):
    packet = diagnostic.runner.BASE.contract.seed_request([
        {"document_id": str(i), "title": "UNPROJECTED PRIVATE TITLE", "body": "UNPROJECTED PRIVATE BODY"}
        for i in range(n)], count_tokens=lambda _: 100)
    payload = {"model": packet["request"]["model"], "answers": [
        {"name": q["name"], "type": "choice", "choice": q["choices"][0]["value"], "confidence": 1,
         "probabilities": [{"value": choice["value"], "probability": int(index == 0)} for index, choice in enumerate(q["choices"])]}
        for q in packet["request"]["questions"]]}
    return json.loads(canonical(packet)), payload


def row(n):
    return {"_record_id": "record", "task_key": "key", "phase": "seed", "http_status": 200, "hold": False,
        "parsed": "parsed" if n < 6 else None, "validation_error": "ResearchError:dossier_card_decision_binding_mismatch" if n >= 6 else None,
        "cost_nanousd": 100, "reserved_nanousd": 0}


@pytest.mark.parametrize("n,valid", [(2, True), (5, True), (6, False), (8, False)])
def test_projects_exact_technical_parser_failure_without_private_text(n, valid):
    packet, payload = packet_and_reply(n)
    result = diagnostic.response_view(row(n), packet, {"payload": payload})
    assert result["mapping_iteration_matches_request_question_order"] is valid
    assert (result["frozen_parser_reproduced_status"] == "valid") is valid
    assert result["answer_identity_matches"] and result["answer_anomalies"] == {}
    assert "UNPROJECTED" not in canonical(result)
    assert result["frozen_parser_reproduced_error"] == (None if valid else "ResearchError:dossier_card_decision_binding_mismatch")


def test_untrusted_error_prose_is_hashed_and_probability_faults_are_numeric_only():
    packet, payload = packet_and_reply(2)
    payload["answers"][0]["probabilities"][0]["probability"] = .5
    result = diagnostic.response_view({**row(2), "validation_error": "private prose: UNPROJECTED"}, packet, {"payload": payload})
    assert result["answer_anomalies"] == {"probability_sum": 1}
    assert result["validation_error"].startswith("unprojected_text_sha256:") and "UNPROJECTED" not in canonical(result)


class Fixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment_v7", "fixture", {
            "parent_plan": "plan", "implementation": diagnostic.runner.implementation()})
        for n in (2, 6):
            packet, payload = packet_and_reply(n)
            item = {k: v for k, v in row(n).items() if k != "_record_id"}
            self.ledger.record(session, "cyber_dossier_response", str(n), {**item, "plan": "plan",
                "execution_amendment": amendment, "packet": self.ledger.artifacts.put(packet),
                "response": self.ledger.artifacts.put({"payload": payload})})
        report = self.ledger.record(session, "cyber_dossier_report", "fixture", {
            "execution_amendment": amendment, "stored_responses": 2, "at": "2026-10-23T16:00:00+00:00"})
        return amendment, report


def test_registered_separate_owner_reads_only_and_retains_no_text(tmp_path, monkeypatch):
    active, owner = tmp_path / "active", tmp_path / "diagnostic"
    fixture = Fixture(active, config=Config(offline=True))
    try:
        amendment, report = fixture.execute("status", {}, objective="Synthetic parser failure", actor="test")
    finally:
        fixture.close()
    for key, value in {"ACTIVE_OWNER": active, "AMENDMENT": amendment, "REPORT": report, "EXPECTED_NEW": 2}.items():
        monkeypatch.setattr(diagnostic, key, value)
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        diagnostic.Diagnostic(active, config=Config(offline=True))
    source = diagnostic.Source(active)
    before = source.head()
    source.close()
    study = diagnostic.Diagnostic(owner, config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Synthetic diagnosis", actor="test")
        assert result["selected_new_responses"] == 2 and result["stored_parsed"] == 1
        assert result["new_holds"] == result["new_model_calls"] == result["new_cost_nanousd"] == 0
        assert not result["outputs_modified"] and not result["parser_policy_changed"]
        assert "UNPROJECTED" not in canonical(result)
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()
    source = diagnostic.Source(active)
    assert source.head() == before
    source.close()
