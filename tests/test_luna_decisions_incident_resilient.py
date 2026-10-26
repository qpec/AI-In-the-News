"""Checkpoint sharing failures must not repeat paid article requests."""
import pytest

from newsresearch.common import Config
import test_luna_incident_screening as fixture
import test_luna_decisions_incident_corpus as incident_fixture
import run_luna_decisions_incident_resilient as resilient


@pytest.mark.parametrize("persistent", [False, True])
def test_checkpoint_retry_or_resume_never_resends_saved_articles(tmp_path, monkeypatch, persistent):
    original, prepared, before = incident_fixture.prepare(tmp_path, monkeypatch)
    original.close()
    original_replace = resilient.os.replace
    blocked = [True]
    failures = []

    def replace(source, destination):
        if destination.name == "progress.json" and blocked[0] and (persistent or len(failures) < 2):
            failures.append((source, destination))
            raise PermissionError("Synthetic Windows file sharing conflict")
        return original_replace(source, destination)

    monkeypatch.setattr(resilient.os, "replace", replace)
    monkeypatch.setattr(resilient, "REPLACE_ATTEMPTS", 3)
    monkeypatch.setattr(resilient, "REPLACE_DELAY_SECONDS", 0)
    study = resilient.Study(tmp_path / "incident", config=Config(offline=False))
    try:
        if persistent:
            with pytest.raises(PermissionError):
                fixture.call(study, "run", allow_paid_execution=True)
        else:
            result = fixture.call(study, "run", allow_paid_execution=True)
            assert result["dispatch_complete"]
        assert len(failures) == (3 if persistent else 2)
        assert len(fixture.Fake.calls) == before + prepared["dispositions"]["ready"]
    finally:
        study.close()
    blocked[0] = False
    study = resilient.Study(tmp_path / "incident", config=Config(offline=False))
    try:
        result = fixture.call(study, "run", allow_paid_execution=True)
        assert result["dispatch_complete"]
        assert len(fixture.Fake.calls) == before + prepared["dispositions"]["ready"]
        assert study.rows("incident_execution_start")[-1]["saved_response_baseline"] == prepared["dispositions"]["ready"]
        assert result["original_deadline"] == prepared["original_deadline"]
        assert result["inherited_holds_usd"] == prepared["inherited_holds_usd"]
    finally:
        study.close()
