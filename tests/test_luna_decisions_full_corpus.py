"""Synthetic full-frame reuse, spend, unknown holds and exact-input checks."""
import json

import pytest

from newsresearch.common import AuditError, Config, ResearchError
import test_luna_incident_screening as fixture
import run_luna_incident_screening_v2 as screening
import run_luna_decisions_full_corpus as full


def seed(tmp_path, monkeypatch):
    fixture.parents(tmp_path)
    fixture.Fake.calls, fixture.Fake.mode = [], "valid"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    monkeypatch.setattr(screening.transport, "DecisionsTransport", fixture.Fake)
    monkeypatch.setattr(full, "DecisionsTransport", fixture.Fake)
    monkeypatch.setattr(full.time, "sleep", lambda seconds: None)
    parent = screening.Study(tmp_path / full.SCREEN_PILOT, config=Config(offline=False))
    try:
        fixture.call(parent, "prepare", base=str(tmp_path), count=2)
        fixture.call(parent, "run", allow_paid_execution=True)
        fixture.call(parent, "report")
    finally:
        parent.close()


def test_exact_pilot_instruction_and_complete_long_body():
    text = "Fictional retained body é 😀.\r\n" * 3000
    request = full.request_for("Fictional title", text)
    assert json.loads(request["input"]) == {"title": "Fictional title", "body": text}
    assert request["questions"] == full.core.QUESTIONS
    with pytest.raises(ResearchError, match="byte_cap"):
        full.core.request("Fictional title", text)
    with pytest.raises(ResearchError, match="byte_cap"):
        full.request_for("Fictional title", "x" * full.MAX_WIRE_BYTES)


def test_transport_one_attempt_exact_input_and_no_credential_logging(monkeypatch):
    calls = []

    class FailingOpener:
        def open(self, request, timeout):
            calls.append((request.full_url, request.data, timeout))
            raise TimeoutError("untrusted diagnostic containing a credential")

    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    monkeypatch.setattr(full.urllib.request, "build_opener", lambda *args: FailingOpener())
    request = full.request_for("Fictional title", "x" * 70000)
    invocation = full.Invocation(request, "synthetic-request")
    response = full.DecisionsTransport().complete_prepared(invocation)
    assert len(calls) == 1 and json.loads(calls[0][1]) == request
    assert response.raw_response == {"unknown_outcome": True, "error_type": "TimeoutError"}
    assert "synthetic-secret" not in json.dumps(invocation.manifest())
    assert "untrusted diagnostic" not in json.dumps(response.raw_response)


def test_full_frame_reuses_pilot_and_never_repeats_completed_calls(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    study = full.Study(tmp_path / "full", config=Config(offline=False))
    try:
        prepared = fixture.call(study, "prepare", base=str(tmp_path))
        assert prepared["selected_articles"] == 8
        assert prepared["dispositions"] == {"ready": 6, "reused": 2}
        assert len(fixture.Fake.calls) == 2
        plan = study.one("full_screen_plan")
        for task in study.tasks(plan):
            assert set(json.loads(task["request"]["input"])) == {"title", "body"}
            assert task["request"]["questions"] == full.core.QUESTIONS
        fixture.call(study, "authorize", total_budget_usd=100, authorization_text="Synthetic user grants total $100")
        with pytest.raises(AuditError, match="explicit_online"):
            fixture.call(study, "run", allow_paid_execution=False)
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["dispatch_complete"] and result["new_responses"] == 6
        assert result["new_valid_results"] == 6 and result["reused_results"] == 2
        assert result["labels"]["routes"] == {"keep": 8, "exclude": 0, "review": 0}
        assert result["new_cost_usd_with_margin"] == pytest.approx(.00066)
        assert len(fixture.Fake.calls) == 8
        exported = [json.loads(line) for line in (study.ledger.root / "article-decisions.jsonl").read_text().splitlines()]
        assert len(exported) == 8 and sum(r["reused"] for r in exported) == 2
        assert all(r["status"] == "valid" and not r["unknown_or_billing_hold"] for r in exported)
        first_deadline = study.rows("full_screen_launch")[0]["expires_at"]
        fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == 8
        assert all(r["expires_at"] == first_deadline for r in study.rows("full_screen_launch"))
    finally:
        study.close()


def test_unknown_attempts_stay_reserved_and_are_not_retried(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    study = full.Study(tmp_path / "full", config=Config(offline=False))
    try:
        fixture.call(study, "prepare", base=str(tmp_path))
        fixture.Fake.mode = "unknown"
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["new_responses"] == result["unresolved_attempts"] == 6
        assert result["held_reservations_usd"] == 1.5
        assert not result["dispatch_complete"] and result["labels"]["routes"]["exclude"] == 0
        assert len(fixture.Fake.calls) == 8
    finally:
        study.close()
    study = full.Study(tmp_path / "full", config=Config(offline=False))
    try:
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == 8 and result["held_reservations_usd"] == 1.5
        assert result["attempts_without_response"] == result["not_attempted"] == 0
    finally:
        study.close()


def test_reservations_and_stop_prevent_dispatch(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    study = full.Study(tmp_path / "full", config=Config(offline=False))
    try:
        fixture.call(study, "prepare", base=str(tmp_path))
        monkeypatch.setattr(full, "RESERVATION", 20_000_000_000)
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["run_end"][-1]["stop_reason"] == "budget_bound"
        assert result["not_attempted"] == 6 and len(fixture.Fake.calls) == 2
        (study.ledger.root / "STOP").write_text("Synthetic user stop", encoding="utf-8")
        with pytest.raises(AuditError, match="stopped_or_expired"):
            fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == 2
    finally:
        study.close()


def test_changed_archive_blocks_preparation(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    archive = tmp_path / screening.STANDARD / "synthetic-archives/cybercrime.zip"
    archive.write_bytes(archive.read_bytes() + b"synthetic tamper")
    study = full.Study(tmp_path / "full", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="archive_hash_mismatch"):
            fixture.call(study, "prepare", base=str(tmp_path))
        assert len(fixture.Fake.calls) == 2
    finally:
        study.close()
