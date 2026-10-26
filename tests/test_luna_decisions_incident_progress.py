"""Operational ETA distinguishes cumulative counts, restarts and stopped work."""
from datetime import datetime, timedelta, timezone
import os

import pytest

from newsresearch.common import Config
import test_luna_incident_screening as fixture
import test_luna_decisions_incident_corpus as incident_fixture
import check_luna_decisions_incident_progress as monitor


@pytest.mark.skipif(os.name != "nt", reason="Windows native process query")
def test_process_probe_parses_and_rejects_unrelated_owner(tmp_path):
    assert monitor.workers(tmp_path / "fictional-no-worker") == []


def test_progress_reader_preserves_exact_checkpoint_bytes(tmp_path):
    path = tmp_path / "progress.json"
    raw = b'{"new_responses": 12}\r\n'
    path.write_bytes(raw)
    assert monitor.read_progress(path) == raw


def test_restart_fallback_uses_current_execution_increment():
    now = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
    progress = {"at": now.isoformat(), "new_responses": 10000, "planned": 20000, "elapsed_seconds": 100}
    result = monitor.rate_and_eta(progress, [], now, True, 9900)
    assert result["saved_responses_per_minute"] == 60
    assert result["eta_seconds"] == 10000
    assert result["rate_basis"] == "current_execution_average_fallback"
    assert monitor.rate_and_eta(progress, [], now, False, 9900)["eta_seconds"] is None
    assert monitor.rate_and_eta(progress, [], now + timedelta(minutes=6), True, 9900)["eta_seconds"] is None


def test_recent_cumulative_window_includes_downtime():
    now = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
    progress = {"at": now.isoformat(), "new_responses": 10000, "planned": 20000, "elapsed_seconds": 100}
    previous = [{"progress": {"at": (now - timedelta(minutes=30)).isoformat(), "new_responses": 7000}}]
    result = monitor.rate_and_eta(progress, previous, now, True, 9900)
    assert result["saved_responses_per_minute"] == pytest.approx(100)
    assert result["eta_seconds"] == pytest.approx(6000)
    assert result["rate_basis"] == "observed_cumulative_change_over_recent_window"
    assert result["estimated_finish_amsterdam"] == "2026-10-21T21:40:00+02:00"


def test_new_process_preflight_does_not_make_old_checkpoint_live():
    launch = {"started_at": "2026-10-21T17:00:00+00:00"}
    progress = {"at": "2026-10-21T18:00:00+00:00"}
    processes = [{"created_at": "2026-10-21T18:01:00Z"}]
    assert not monitor.checkpoint_is_current(progress, [launch], processes)
    launch["started_at"] = "2026-10-21T18:02:00+00:00"
    assert not monitor.checkpoint_is_current(progress, [launch], processes)
    progress["at"] = "2026-10-21T18:03:00+00:00"
    assert monitor.checkpoint_is_current(progress, [launch], processes)


def test_restart_downtime_is_not_projected_as_future_processing_speed():
    now = datetime(2026, 10, 21, 18, tzinfo=timezone.utc)
    progress = {"at": now.isoformat(), "new_responses": 10000, "planned": 20000, "elapsed_seconds": 100}
    previous = [{"progress": {"at": (now - timedelta(minutes=30)).isoformat(), "new_responses": 9900}}]
    result = monitor.rate_and_eta(progress, previous, now, True, 9900,
                                 (now - timedelta(seconds=110)).isoformat())
    assert result["saved_responses_per_minute"] == 60
    assert result["eta_seconds"] == 10000
    assert result["rate_basis"] == "current_execution_average_fallback"


def test_audited_observation_preserves_errors_and_never_calls_provider(tmp_path, monkeypatch):
    worker, _, before = incident_fixture.prepare(tmp_path, monkeypatch)
    fixture.Fake.mode = "unknown"
    try:
        fixture.call(worker, "run", allow_paid_execution=True)
    finally:
        worker.close()
    count = len(fixture.Fake.calls)
    assert count > before
    monkeypatch.setattr(monitor, "workers", lambda owner: [])
    study = monitor.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = study.execute("status", {"owner": str(tmp_path / "incident")},
            objective="Verify synthetic operational observation", actor="test:synthetic")
        assert result["processed_including_reuse"] == result["total_articles"] == 4
        assert result["new_unresolved_holds_reported"] > 0
        assert result["state"] == "stopped" and result["eta_seconds"] is None
        assert result["final_coverage"]["unresolved_attempts"] > 0
        assert not result["final_coverage"]["dispatch_complete"]
        assert len(fixture.Fake.calls) == count
        assert (study.ledger.root / "latest-progress.json").is_file()
    finally:
        study.close()
