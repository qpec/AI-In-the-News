"""Synthetic source-free operational monitor checks; no production owner access."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_dossier_progress_v2 as m  # noqa: E402
from newsresearch.common import AuditError, Config, utc  # noqa: E402
from newsresearch.runtime import Research, audited_handler  # noqa: E402


NOW = datetime(2026, 10, 23, 18, tzinfo=timezone.utc)


def process(owner, pid=11, parent=1, action="run", created=None):
    return {"pid": pid, "parent_pid": parent, "created_at": (created or NOW - timedelta(hours=1)).isoformat(),
            "command_line": f'python.exe "C:/repo/run_dossiers.py" {action} --workspace "{owner}"',
            "executable_path": "C:/venv/python.exe"}


def checkpoint(at=NOW, completed=200, phase="seed", queue="queue-a"):
    return {"observed_at": at.isoformat(), "pid": 11, "phase": phase, "input_manifest": "input",
            "unique_documents": m.EXPECTED_DOCUMENTS, "selected_articles": m.EXPECTED_ARTICLES,
            "responses": 9900, "settled_nanousd": 2_000_000_000, "held_nanousd": 100_000_000,
            "committed_nanousd": 2_100_000_000, "unresolved_holds": 1, "cap_nanousd": m.CAP_NANOUSD,
            "phase_tasks_completed": completed, "phase_tasks_planned": 1000,
            "phase_task_set_sha256": queue, "elapsed_seconds": 1}


def test_process_filter_exact_owner_action_and_worker_child(tmp_path):
    owner = tmp_path / "worker"
    rows = [process(owner, 10), process(owner, 11, 10), process(str(owner) + "-other", 12),
            process(owner, 13, action="report"), process(owner, 14, action="prepare")]
    matched = m.matching_processes(rows, owner)
    assert [r["pid"] for r in matched] == [10, 11]
    assert [r["pid"] for r in matched if r["worker_leaf"]] == [11]


def test_equals_workspace_argument_cannot_be_mistaken_for_default_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ACTIVE_OWNER", tmp_path)
    other = process(tmp_path)
    other["command_line"] = 'python.exe run_dossiers.py run --workspace="C:/other"'
    assert m.matching_processes([other], tmp_path) == []
    other["command_line"] = f'python.exe run_dossiers.py run --workspace="{tmp_path}"'
    assert len(m.matching_processes([other], tmp_path)) == 1
    other["command_line"] = 'python.exe run_dossiers.py run --workspace'
    assert m.matching_processes([other], tmp_path) == []


def test_eta_uses_same_phase_delta_not_cumulative_count_or_restarted_timer(tmp_path):
    processes = m.matching_processes([process(tmp_path)], tmp_path)
    identity = {"pid": 11, "created_at": processes[0]["created_at"]}
    previous = [{"checkpoint_matches_current_execution": True, "execution_identity": identity,
                 "progress": checkpoint(NOW - timedelta(minutes=30), completed=100)}]
    result = m.phase_timing(checkpoint(), previous, NOW, processes, False, (NOW + timedelta(hours=10)).isoformat())
    assert result["phase_eta_seconds"] == 14_400
    assert result["phase_tasks_per_minute"] == pytest.approx(100 / 30)
    assert result["whole_pipeline_eta_seconds"] is None
    assert result["phase_tasks_remaining"] == 800


@pytest.mark.parametrize("change", ["stopped", "stale", "restart", "queue", "phase", "deadline", "stop"])
def test_no_eta_across_stale_execution_or_queue_boundaries(tmp_path, change):
    processes = m.matching_processes([process(tmp_path)], tmp_path)
    current = checkpoint()
    prior = {"checkpoint_matches_current_execution": True,
             "execution_identity": {"pid": 11, "created_at": processes[0]["created_at"]},
             "progress": checkpoint(NOW - timedelta(minutes=30), completed=100)}
    deadline, stop, now = (NOW + timedelta(hours=10)).isoformat(), False, NOW
    if change == "stopped":
        processes = []
    elif change == "stale":
        now += timedelta(minutes=6)
    elif change == "restart":
        processes[0]["created_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif change in {"queue", "phase"}:
        current["phase_task_set_sha256" if change == "queue" else "phase"] = "new"
    elif change == "deadline":
        deadline = NOW.isoformat()
    else:
        stop = True
    result = m.phase_timing(current, [prior], now, processes, stop, deadline)
    assert result["phase_eta_seconds"] is None
    assert result["phase_eta_blocker"] is not None


def test_no_eta_without_meaningful_phase_queue_and_startup_not_stall(tmp_path):
    processes = m.matching_processes([process(tmp_path)], tmp_path)
    progress = checkpoint()
    progress.pop("phase_task_set_sha256")
    assert m.phase_timing(progress, [], NOW, processes, False, None)["phase_eta_blocker"] == "phase_workload_or_queue_identity_unavailable"
    result = m.phase_timing(None, [], NOW, processes, False, None)
    assert result["state"] == "starting_or_waiting_first_checkpoint"


def test_report_must_follow_every_response_and_stopped_checkpoint():
    plan = {"_record_id": "plan"}
    report = {"plan": "plan", "stored_responses": 10000, "_created_event": 200,
              "articles": m.EXPECTED_ARTICLES, "distinct_inputs": m.EXPECTED_DOCUMENTS,
              "at": (NOW + timedelta(seconds=5)).isoformat()}
    state = {"responses": 10000, "last_response_event": 199}
    assert m.report_is_current(report, plan, state, checkpoint(), [])
    assert not m.report_is_current(report, plan, {**state, "responses": 10001}, checkpoint(), [])
    assert not m.report_is_current(report, plan, {**state, "last_response_event": 201}, checkpoint(), [])
    assert not m.report_is_current(report, plan, state, checkpoint(), [{"pid": 1}])


def test_counter_scope_and_budget_sum_are_not_assumed():
    progress = checkpoint()
    m.validate_progress(progress, {"input_manifest": "input"})
    progress["committed_nanousd"] = 1
    with pytest.raises(AuditError, match="accounting"):
        m.validate_progress(progress, {"input_manifest": "input"})


class MetadataOwner(Research):
    @audited_handler
    def _status(self, session, context, data):
        plan = {"method": m.RUN_METHOD, "input_manifest": "input", "unique_documents": m.EXPECTED_DOCUMENTS,
                "eligible_articles": m.EXPECTED_ARTICLES, "cap_nanousd": m.CAP_NANOUSD,
                "implementation": {"original.py": "original-hash"}}
        identifier = self.ledger.record(session, "cyber_dossier_plan", "synthetic", plan)
        self.ledger.record(session, "cyber_dossier_first_launch", "synthetic", {"at": utc(), "deadline": "2030-01-01T00:00:00+00:00"})
        self.ledger.record(session, "cyber_dossier_response", "synthetic", {"status": "synthetic-unknown", "hold": True})
        report = {"plan": identifier, "stored_responses": 1, "articles": m.EXPECTED_ARTICLES,
                  "distinct_inputs": m.EXPECTED_DOCUMENTS, "at": utc(), "budget_usd": 50,
                  "settled_nanousd": 0, "held_nanousd": 100_000_000, "committed_nanousd": 100_000_000,
                  "unresolved_holds": 1, "responses_by_phase": {"embeddings": 1},
                  "pipeline_finished": False, "four_processes_complete": False, "unique_inputs_grouped": 0,
                  "unresolved_inputs": m.EXPECTED_DOCUMENTS, "groups": 0, "article_routes": {}}
        report_id = self.ledger.record(session, "cyber_dossier_report", "synthetic", report)
        return {"id": report_id, **report}


def test_audited_monitor_reads_only_metadata_and_ignores_stale_published_report(tmp_path, monkeypatch):
    owner = tmp_path / "active"
    monkeypatch.setattr(m, "ACTIVE_OWNER", owner)
    monkeypatch.setattr(m, "workers", lambda _: [])
    worker = MetadataOwner(owner, config=Config(offline=True))
    try:
        worker.execute("status", {}, objective="Synthetic operational fixture", actor="test:monitor")
        calls = worker.gateway.provider.calls
    finally:
        worker.close()
    (owner / "dossier-report.json").write_text('{"id":"stale"}', encoding="utf-8")
    monitor = m.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = monitor.execute("status", {}, objective="Observe synthetic source-free metadata", actor="test:monitor")
        assert result["latest_report_current"] is True
        assert result["published_report_status"] == "stale_or_different_from_audited_record"
        assert result["final_coverage"]["unresolved_inputs"] == m.EXPECTED_DOCUMENTS
        assert result["held_cost_usd"] == .1 and result["state"] == "stopped"
        assert result["new_model_calls"] == 0 and result["worker_mutations"] == 0
        assert calls == 0 and monitor.gateway.provider.calls == 0
        assert result["phase_eta_seconds"] is None
        saved = json.loads((monitor.ledger.root / "latest-progress.json").read_text(encoding="utf-8"))
        assert saved["id"] == result["id"]
    finally:
        monitor.close()


def test_active_owner_cannot_be_monitor_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "ACTIVE_OWNER", tmp_path)
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        m.Study(tmp_path, config=Config(offline=True))


def test_original_and_amended_workers_both_match_but_report_does_not(tmp_path):
    original = process(tmp_path, pid=11)
    amended = process(tmp_path, pid=12, action="pilot")
    amended["command_line"] = amended["command_line"].replace("run_dossiers.py", "run_dossiers_v2.py")
    report = process(tmp_path, pid=13, action="report")
    report["command_line"] = report["command_line"].replace("run_dossiers.py", "run_dossiers_v2.py")
    assert [p["runner"] for p in m.matching_processes([original, amended, report], tmp_path)] == [
        "run_dossiers.py", "run_dossiers_v2.py"]


@pytest.mark.parametrize("field", ["parent_plan", "parent_implementation", "original_deadline"])
def test_amendment_cannot_change_original_plan_implementation_or_deadline(field):
    plan = {"_record_id": "original", "implementation": {"old.py": "hash"}}
    amendment = {"parent_plan": "original", "parent_implementation": plan["implementation"],
                 "original_deadline": "2030-01-01T00:00:00Z", "implementation": {"new.py": "newhash"},
                 "legacy_unresolved_attempts": ["old-hold"], "cap_nanousd": m.CAP_NANOUSD}
    m.validate_amendment(amendment, plan, amendment["original_deadline"])
    amendment[field] = "changed"
    with pytest.raises(AuditError, match="amendment_binding"):
        m.validate_amendment(amendment, plan, "2030-01-01T00:00:00Z")


def test_hold_split_only_uses_explicit_current_counters():
    assert m.hold_breakdown({"unresolved_holds": 1})["hold_split_status"] == "not_reported"
    totals = {"unresolved_holds": 3, "legacy_unresolved_holds": 1, "new_unresolved_holds": 2}
    result = m.hold_breakdown(totals)
    assert result["legacy_unresolved_holds"] == 1 and result["new_unresolved_holds"] == 2
    assert result["legacy_held_cost_usd"] is None
    with pytest.raises(AuditError, match="hold_split_sum"):
        m.hold_breakdown({**totals, "unresolved_holds": 1})
    money = m.hold_breakdown({**totals, "legacy_held_nanousd": 2_462_350,
                             "new_held_nanousd": 1000, "held_nanousd": 2_463_350})
    assert money["legacy_held_cost_usd"] == .00246235
    with pytest.raises(AuditError, match="hold_cost_sum"):
        m.hold_breakdown({**totals, "legacy_held_nanousd": 2_462_350,
                         "new_held_nanousd": 1000, "held_nanousd": 2_462_350})


class AmendedMetadataOwner(MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        previous = super()._status(session, context, data)
        amendment = {"parent_plan": previous["plan"], "parent_implementation": {"original.py": "original-hash"},
            "implementation": {"amended.py": "amended-hash"}, "original_deadline": "2030-01-01T00:00:00+00:00",
            "legacy_unresolved_attempts": ["old-unknown"], "cap_nanousd": m.CAP_NANOUSD}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment", "synthetic", amendment)
        latest = {k: v for k, v in previous.items() if k != "id"}
        latest.update(execution_amendment=identifier, legacy_unresolved_holds=1, new_unresolved_holds=0,
                      legacy_held_nanousd=100_000_000, new_held_nanousd=0, at=utc())
        report = self.ledger.record(session, "cyber_dossier_report", "synthetic-v2", latest)
        return {"id": report, **latest}


def test_registered_amendment_report_exposes_preserved_legacy_hold(tmp_path, monkeypatch):
    owner = tmp_path / "amended-active"
    monkeypatch.setattr(m, "ACTIVE_OWNER", owner)
    monkeypatch.setattr(m, "workers", lambda _: [])
    worker = AmendedMetadataOwner(owner, config=Config(offline=True))
    try:
        report = worker.execute("status", {}, objective="Synthetic amendment metadata", actor="test:monitor")
    finally:
        worker.close()
    (owner / "dossier-report.json").write_text(json.dumps(report), encoding="utf-8")
    observer = m.Study(tmp_path / "amended-monitor", config=Config(offline=True))
    try:
        result = observer.execute("status", {}, objective="Observe synthetic amended report", actor="test:monitor")
        assert result["latest_report_current"] is True
        assert result["published_report_status"] == "matches_latest_audited_record"
        assert result["provenance"]["execution_amendment"] == report["execution_amendment"]
        assert result["legacy_unresolved_holds"] == 1 and result["new_unresolved_holds"] == 0
        assert result["legacy_held_cost_usd"] == .1 and result["new_held_cost_usd"] == 0
    finally:
        observer.close()
