"""Pacing and its explicit audit profile preserve the prepared requests."""
import pytest

from newsresearch.common import AuditError, Config
import test_luna_incident_screening as fixture
import test_luna_decisions_full_corpus as full_fixture
import run_luna_decisions_full_corpus as base
import run_luna_decisions_full_corpus_paced as paced


def test_weighted_spacing_charges_before_dispatch():
    now, delays = [0.0], []

    def sleep(delay):
        delays.append(delay)
        now[0] += delay

    pacer = paced.Pacer(1, clock=lambda: now[0], sleep=sleep)
    large = base.request_for("Fictional title", "Synthetic words " * 10000)
    small = base.request_for("Fictional title", "Synthetic article.")
    tokens = pacer.acquire(large)
    assert delays[0] >= 60 * tokens / paced.TOKENS_PER_MINUTE
    pacer.acquire(small)
    assert delays[1] >= 60 / paced.REQUESTS_PER_MINUTE
    assert now[0] == pytest.approx(sum(delays))


def test_profile_is_frozen_and_exact_requests_use_shared_gateway(tmp_path, monkeypatch):
    full_fixture.seed(tmp_path, monkeypatch)
    preparation = base.Study(tmp_path / "full", config=Config(offline=True))
    try:
        fixture.call(preparation, "prepare", base=str(tmp_path))
    finally:
        preparation.close()

    class ImmediatePacer:
        def __init__(self, ratio):
            assert ratio > 0

        def acquire(self, request):
            return 1000

    monkeypatch.setattr(paced, "Pacer", ImmediatePacer)
    monkeypatch.setattr(paced, "ORIGINAL_TRANSPORT", fixture.Fake)
    study = paced.Study(tmp_path / "full", config=Config(offline=False))
    try:
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["dispatch_complete"] and len(fixture.Fake.calls) == 8
        profile = study.one("full_screen_execution_profile")
        for row in study.rows("full_screen_decision"):
            response = study.ledger.artifacts.read(row["response"])
            assert response["raw_response"]["pacing_profile"] == profile["_record_id"]
        fixture.call(study, "run", allow_paid_execution=True)
        assert len(fixture.Fake.calls) == 8 and len(study.rows("full_screen_execution_profile")) == 1
        monkeypatch.setattr(paced, "TOKENS_PER_MINUTE", 100)
        with pytest.raises(AuditError, match="profile_changed"):
            fixture.call(study, "run", allow_paid_execution=True)
    finally:
        study.close()
