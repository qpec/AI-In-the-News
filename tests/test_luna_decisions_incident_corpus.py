"""Synthetic corpus exclusion, inherited liabilities and no-retry checks."""
import json
from datetime import datetime, timedelta

import pytest

from newsresearch.common import AuditError, Config
import test_luna_incident_screening as fixture
import test_luna_decisions_full_corpus as full_fixture
import run_luna_decisions_full_corpus as base
import run_luna_decisions_full_corpus_paced as paced
import run_luna_decisions_incident_corpus as incident


def prepare(tmp_path, monkeypatch):
    full_fixture.seed(tmp_path, monkeypatch)
    parent_path = tmp_path / "full"

    class Parent(base.Study):
        def tasks(self, plan):
            return (t for t in super().tasks(plan) if t["corpus"] == "cybercrime")

    class StopProvider(fixture.Fake):
        mode = "unknown"

        def complete_prepared(self, invocation):
            (parent_path / "STOP").write_text("Synthetic user excludes cybercrime", encoding="utf-8")
            return super().complete_prepared(invocation)

    monkeypatch.setattr(base, "DecisionsTransport", StopProvider)
    parent = Parent(parent_path, config=Config(offline=False))
    try:
        fixture.call(parent, "prepare", base=str(tmp_path))
        fixture.call(parent, "authorize", total_budget_usd=100, authorization_text="Synthetic user budget $100")
        stopped = fixture.call(parent, "run", allow_paid_execution=True)
        assert stopped["run_end"][-1]["stop_reason"] == "user_stop"
        assert stopped["held_reservations_usd"] > 0
        deadline = parent.rows("full_screen_launch")[0]["expires_at"]
    finally:
        parent.close()

    class ImmediatePacer:
        def __init__(self, ratio):
            assert ratio > 0

        def acquire(self, request):
            assert "incident-reports" in json.loads(request["input"])["body"]
            return 1000

    monkeypatch.setattr(paced, "Pacer", ImmediatePacer)
    monkeypatch.setattr(paced, "ORIGINAL_TRANSPORT", fixture.Fake)
    study = incident.Study(tmp_path / "incident", config=Config(offline=False))
    count = len(fixture.Fake.calls)
    prepared = fixture.call(study, "prepare", parent=str(parent_path))
    assert len(fixture.Fake.calls) == count
    assert prepared["selected_articles"] == 4
    assert prepared["inherited_holds_usd"] == stopped["held_reservations_usd"]
    assert prepared["original_deadline"] == deadline
    assert prepared["budget_usd"] == 100
    return study, prepared, count


@pytest.mark.parametrize("mode", ["valid", "unknown"])
def test_incident_only_reuses_pilot_and_preserves_parent_holds_and_deadline(tmp_path, monkeypatch, mode):
    study, prepared, before = prepare(tmp_path, monkeypatch)
    fixture.Fake.mode = mode
    try:
        result = fixture.call(study, "run", allow_paid_execution=True)
        needed = prepared["dispositions"]["ready"]
        assert len(fixture.Fake.calls) == before + needed
        assert result["selected_articles"] == 4 and result["new_responses"] == needed
        assert result["reused_results"] + needed == 4
        assert result["inherited_holds_usd"] == prepared["inherited_holds_usd"]
        assert result["total_budget_committed_usd"] == pytest.approx(
            result["total_cost_usd_with_margin"] + result["inherited_holds_usd"] + result["new_holds_usd"])
        assert result["dispatch_complete"] == (mode == "valid")
        assert result["new_holds_usd"] == (0 if mode == "valid" else needed * .25)
        exported = [json.loads(line) for line in (study.ledger.root / "article-decisions.jsonl").read_text().splitlines()]
        assert len(exported) == 4 and {r["corpus"] for r in exported} == {"incident-reports"}
        assert all(r["status"] == ("valid" if mode == "valid" or r["reused"] else "unknown_outcome") for r in exported)
        assert (tmp_path / "full/STOP").is_file()
        assert study.rows("full_screen_launch")[0]["expires_at"] == prepared["original_deadline"]
    finally:
        study.close()
    study = incident.Study(tmp_path / "incident", config=Config(offline=False))
    try:
        again = fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == before + needed
        assert again["new_holds_usd"] == result["new_holds_usd"]
        assert all(r["expires_at"] == prepared["original_deadline"] for r in study.rows("full_screen_launch"))
        (study.ledger.root / "STOP").write_text("Synthetic stop", encoding="utf-8")
        with pytest.raises(AuditError, match="stopped_or_expired"):
            fixture.call(study, "run", allow_paid_execution=True)
    finally:
        study.close()


def test_budget_and_original_deadline_block_untouched_dispatch(tmp_path, monkeypatch):
    study, prepared, before = prepare(tmp_path, monkeypatch)
    try:
        monkeypatch.setattr(base, "RESERVATION", 100_000_000_000)
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["run_end"][-1]["stop_reason"] == "budget_bound"
        assert result["not_attempted"] == prepared["dispositions"]["ready"]
        assert result["new_responses"] == 0 and len(fixture.Fake.calls) == before

        class ExpiredClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromisoformat(prepared["original_deadline"]) + timedelta(seconds=1)

        monkeypatch.setattr(incident, "datetime", ExpiredClock)
        with pytest.raises(AuditError, match="stopped_or_expired"):
            fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == before
    finally:
        study.close()
