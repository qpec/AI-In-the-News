"""Synthetic monitoring tests; no production owner or model activity."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import check_progress as monitor  # noqa: E402


def scenario(count=700, elapsed=60):
    now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
    progress = {"at": now.isoformat(), "new_responses": count, "planned": 57002,
                "elapsed_seconds": elapsed, "execution_response_baseline": 100, "phase": "screening",
                "expires_at": (now + timedelta(hours=20)).isoformat()}
    launch = {"_record_id": "launch2", "operational": False,
              "started_at": (now - timedelta(seconds=elapsed + 1)).isoformat()}
    workers = [{"pid": 1, "parent_pid": 0, "worker_leaf": True,
                "created_at": (now - timedelta(seconds=elapsed + 2)).isoformat()}]
    return now, progress, launch, workers


def test_current_execution_baseline_and_comparable_window():
    now, progress, launch, workers = scenario()
    result = monitor.timing(progress, [], now, workers, launch, False)
    assert result["saved_responses_per_minute"] == 600
    assert result["rate_basis"] == "current_execution_average_fallback"
    assert result["eta_seconds"] == (57002 - 700) / 10
    now, progress, launch, workers = scenario(count=15100, elapsed=3600)
    old = {"execution_identity": {"launch": "launch2", "started_at": launch["started_at"], "response_baseline": 100},
           "checkpoint_matches_current_execution": True,
           "progress": {**progress, "new_responses": 6100, "at": (now - timedelta(minutes=30)).isoformat()}}
    result = monitor.timing(progress, [old], now, workers, launch, False)
    assert result["saved_responses_per_minute"] == 300
    assert result["rate_basis"] == "comparable_cumulative_15_to_90_minute_delta"
    old["execution_identity"]["launch"] = "previous-execution"
    result = monitor.timing(progress, [old], now, workers, launch, False)
    assert result["rate_basis"] == "current_execution_average_fallback"
    assert result["saved_responses_per_minute"] == pytest.approx(250)


def test_no_eta_for_stopped_stale_startup_stop_ended_deadline_or_duplicate_workers():
    now, progress, launch, workers = scenario()
    cases = [([], now, False, False, "no_matching_python_worker"),
             (workers, now + timedelta(minutes=6), False, False, "checkpoint_over_five_minutes_old"),
             (workers, now, True, False, "user_stop_present"),
             (workers, now, False, True, "execution_has_ended"),
             (workers * 2, now, False, False, "multiple_matching_python_workers")]
    for processes, observed, stop, ended, expected in cases:
        result = monitor.timing(progress, [], observed, processes, launch, stop, ended)
        assert result["eta_seconds"] is None and result["eta_blocker"] == expected
    newer = [{**workers[0], "created_at": (now + timedelta(seconds=1)).isoformat()}]
    result = monitor.timing(progress, [], now, newer, launch, False)
    assert result["state"] == "starting_or_waiting_first_checkpoint" and result["eta_seconds"] is None
    expired = {**progress, "expires_at": (now - timedelta(seconds=1)).isoformat()}
    assert monitor.timing(expired, [], now, workers, launch, False)["eta_blocker"] == "admission_deadline_reached"


def test_process_matching_exact_owner_action_and_venv_parent_child(tmp_path):
    owner = tmp_path / "owner"
    command = f'python.exe research/cybercrime_nl/runtime/run_screening_v2.py run --workspace "{owner}" --allow-paid-execution'
    rows = [{"pid": 10, "parent_pid": 1, "created_at": "2026-10-23T10:00:00+00:00", "command_line": command},
            {"pid": 20, "parent_pid": 10, "created_at": "2026-10-23T10:00:01+00:00", "command_line": command},
            {"pid": 30, "parent_pid": 1, "created_at": "2026-10-23T10:00:00+00:00", "command_line": command.replace(".py run ", ".py report ")},
            {"pid": 40, "parent_pid": 1, "created_at": "2026-10-23T10:00:00+00:00", "command_line": command.replace(str(owner), str(owner) + "-other")}]
    matched = monitor.matching_processes(rows, owner)
    assert [(r["pid"], r["worker_leaf"]) for r in matched] == [(10, False), (20, True)]


def test_shared_read_allows_atomic_replacement_while_handle_is_short_lived(tmp_path):
    path = tmp_path / "progress.json"
    path.write_bytes(b'{"count": 1}')
    assert monitor.read_progress(path) == b'{"count": 1}'
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(b'{"count": 2}')
    replacement.replace(path)
    assert monitor.read_progress(path) == b'{"count": 2}'


class SyntheticWorker(Research):
    @audited_handler
    def _status(self, session, context, data):
        self.ledger.record(session, "cyber_screen_plan", "fixture", {
            "implementation": monitor.screening.original.implementation(), "selected_articles": 61089,
            "dispositions": {"ready": 57002, "exact_input_alias": 3775, "retention_unavailable": 251, "sealed_validation": 61}})
        self.ledger.record(session, "cyber_preparation_continuation", "fixture", {
            "implementation": monitor.screening.implementation()})
        self.ledger.record(session, "cyber_screen_launch", "fixture", data["launch"])
        (self.ledger.root / "progress.json").write_text(json.dumps(data["progress"]), encoding="utf-8")
        return {}


def test_audited_observation_uses_separate_owner_without_mutating_worker(tmp_path, monkeypatch):
    owner = tmp_path / "worker"
    monkeypatch.setattr(monitor, "ACTIVE_OWNER", owner)
    now = datetime.now(timezone.utc)
    progress = {"at": now.isoformat(), "new_responses": 700, "planned": 57002,
                "elapsed_seconds": 60, "execution_response_baseline": 100, "phase": "screening",
                "expires_at": (now + timedelta(hours=20)).isoformat(), "budget_usd": 20,
                "settled_cost_usd_with_margin": .1, "held_reservations_usd": .6, "total_committed_usd": .7}
    launch = {"operational": False, "started_at": (now - timedelta(seconds=61)).isoformat(),
              "expires_at": progress["expires_at"]}
    worker = SyntheticWorker(owner, config=Config(offline=True))
    try:
        worker.execute("status", {"launch": launch, "progress": progress}, objective="Seed synthetic monitor metadata", actor="test:monitor")
    finally:
        worker.close()
    def head():
        source = monitor.screening.original.base.pilot.Source(owner)
        try:
            return source.head()
        finally:
            source.close()
    before = head()
    checkpoint = (owner / "progress.json").read_bytes()
    monkeypatch.setattr(monitor, "workers", lambda path: [{"pid": 123, "parent_pid": 1, "worker_leaf": True,
        "created_at": (now - timedelta(seconds=62)).isoformat(), "command_line": "synthetic command"}])
    observer = monitor.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = observer.execute("status", {}, objective="Test read-only operational observation", actor="test:monitor")
        assert result["state"] == "running" and result["new_responses"] == 700
        assert result["unresolved_holds_reported"] == 1
        assert result["total_committed_usd"] == .7 and result["remaining_runtime_seconds"] > 0
        assert result["final_coverage"] is None and result["new_model_calls"] == result["worker_mutations"] == 0
        assert (tmp_path / "monitor/latest-progress.json").is_file()
    finally:
        observer.close()
    assert head() == before and (owner / "progress.json").read_bytes() == checkpoint


def test_cli_refuses_active_owner_before_constructing_writer(tmp_path, monkeypatch):
    owner = tmp_path / "active"
    monkeypatch.setattr(monitor, "ACTIVE_OWNER", owner)
    with pytest.raises(AuditError, match="must_be_separate"):
        monitor.Study(owner, config=Config(offline=True))
    assert not owner.exists()
    monkeypatch.setattr(sys, "argv", ["check_progress.py", "--workspace", str(owner)])
    monkeypatch.setattr(monitor, "Study", lambda *a, **k: pytest.fail("writer must not be constructed on active owner"))
    with pytest.raises(AuditError, match="must_be_separate"):
        monitor.main()
