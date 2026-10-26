"""Synthetic source-free operational monitor checks; no production owner access."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_dossier_progress_v11 as m  # noqa: E402
from newsresearch.common import AuditError, Config, utc  # noqa: E402
from newsresearch.runtime import Research, audited_handler  # noqa: E402


NOW = datetime(2026, 10, 23, 18, tzinfo=timezone.utc)


def code_manifest(version=""):
    relative = "research/cybercrime_nl/runtime/check_dossier_progress" + version + ".py"
    return {relative: hashlib.sha256((m.ROOT / relative).read_bytes()).hexdigest()}


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


@pytest.mark.parametrize("change", ["stopped", "stale", "restart", "queue", "phase", "amendment", "deadline", "stop"])
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
    elif change == "amendment":
        current["execution_amendment"] = "new-v3"
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
                "implementation": code_manifest()}
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
        report = worker.execute("status", {}, objective="Synthetic operational fixture", actor="test:monitor")
        monkeypatch.setattr(m, "EXPECTED_PLAN", report["plan"])
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
        amendment = {"parent_plan": previous["plan"], "parent_implementation": code_manifest(),
            "implementation": {**code_manifest(), **code_manifest("_v2")}, "original_deadline": "2030-01-01T00:00:00+00:00",
            "legacy_unresolved_attempts": ["old-unknown"], "cap_nanousd": m.CAP_NANOUSD,
            "legacy_budget": {"settled_nanousd": 0, "held_nanousd": 100_000_000,
                              "committed_nanousd": 100_000_000, "unresolved_holds": 1}}
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
        monkeypatch.setattr(m, "EXPECTED_PLAN", report["plan"])
        monkeypatch.setattr(m, "EXPECTED_V2", report["execution_amendment"])
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


def test_v3_processes_match_but_future_or_other_owner_commands_do_not(tmp_path):
    rows = []
    for number, suffix in enumerate(("", "_v2", "_v3", "_v4", "_v5", "_v6", "_v7", "_v8", "_v9", "_v10", "_v11", "_v12"), 1):
        row = process(tmp_path, pid=number)
        row["command_line"] = row["command_line"].replace("run_dossiers.py", "run_dossiers" + suffix + ".py")
        rows.append(row)
    assert [r["runner"] for r in m.matching_processes(rows, tmp_path)] == [
        "run_dossiers.py", "run_dossiers_v2.py", "run_dossiers_v3.py", "run_dossiers_v4.py", "run_dossiers_v5.py", "run_dossiers_v6.py", "run_dossiers_v7.py", "run_dossiers_v8.py", "run_dossiers_v9.py", "run_dossiers_v10.py", "run_dossiers_v11.py"]


def chain(monkeypatch):
    deadline = "2030-01-01T00:00:00+00:00"
    plan = {"_record_id": "plan", "implementation": code_manifest()}
    v2 = {"_record_id": "v2", "parent_plan": "plan", "parent_implementation": plan["implementation"],
          "implementation": {**code_manifest(), **code_manifest("_v2")},
          "original_deadline": deadline, "cap_nanousd": m.CAP_NANOUSD,
          "legacy_unresolved_attempts": ["old-hold"],
          "legacy_budget": {"settled_nanousd": 10, "held_nanousd": 100, "committed_nanousd": 110, "unresolved_holds": 1}}
    v3 = {**v2, "_record_id": "v3", "parent_execution_amendment": "v2",
          "parent_implementation": v2["implementation"],
          "implementation": {**v2["implementation"], **code_manifest("_v3")},
          "legacy_unresolved_attempts": ["old-hold", "second-hold"],
          "legacy_budget": {"settled_nanousd": 20, "held_nanousd": 200, "committed_nanousd": 220, "unresolved_holds": 2}}
    monkeypatch.setattr(m, "EXPECTED_PLAN", "plan")
    monkeypatch.setattr(m, "EXPECTED_V2", "v2")
    monkeypatch.setattr(m, "EXPECTED_V3", "v3")
    return plan, v2, v3, deadline


@pytest.mark.parametrize("change", ["parent", "implementation", "deadline", "cap", "hold_removed", "settled_reduced", "hash_changed"])
def test_v3_chain_rejects_changed_parent_scope_or_reduced_liability(monkeypatch, change):
    plan, v2, v3, deadline = chain(monkeypatch)
    assert m.validate_chain(plan, v2, v3, deadline)["verified_files"] == 3
    if change == "parent":
        v3["parent_execution_amendment"] = "other"
    elif change == "implementation":
        v3["parent_implementation"] = {}
    elif change == "deadline":
        v3["original_deadline"] = "2031-01-01T00:00:00+00:00"
    elif change == "cap":
        v3["cap_nanousd"] += 1
    elif change == "hold_removed":
        v3["legacy_unresolved_attempts"] = ["replacement", "second-hold"]
    elif change == "settled_reduced":
        v3["legacy_budget"].update(settled_nanousd=9, committed_nanousd=209)
    else:
        key = next(iter(v3["implementation"]))
        v3["implementation"] = {**v3["implementation"], key: "0" * 64}
    with pytest.raises(AuditError):
        m.validate_chain(plan, v2, v3, deadline)


def test_current_v3_checkpoint_cannot_silently_drop_prior_hold(monkeypatch):
    _, _, v3, _ = chain(monkeypatch)
    totals = {**v3["legacy_budget"], "legacy_unresolved_holds": 2, "new_unresolved_holds": 0,
              "legacy_held_nanousd": 200, "new_held_nanousd": 0}
    m.validate_current_liabilities(totals, v3)
    totals.update(legacy_held_nanousd=100, held_nanousd=100, committed_nanousd=120)
    with pytest.raises(AuditError, match="liability_reduced"):
        m.validate_current_liabilities(totals, v3)


class V3MetadataOwner(AmendedMetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        old_report = super()._status(session, context, {})
        parent = self.ledger.get(old_report["execution_amendment"], "cyber_dossier_execution_amendment")
        amendment = {"parent_plan": old_report["plan"], "parent_execution_amendment": old_report["execution_amendment"],
            "parent_implementation": parent["implementation"],
            "implementation": {**parent["implementation"], **code_manifest("_v3")},
            "original_deadline": parent["original_deadline"], "cap_nanousd": m.CAP_NANOUSD,
            "legacy_unresolved_attempts": parent["legacy_unresolved_attempts"], "legacy_budget": parent["legacy_budget"]}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment_v3", "synthetic-v3", amendment)
        if data.get("leave_old_report"):
            return old_report
        latest = {k: v for k, v in old_report.items() if k != "id"}
        latest.update(execution_amendment=identifier, at=utc(), pilot_gate={"passed": False, "reference_pairs": 3})
        report = self.ledger.record(session, "cyber_dossier_report", "synthetic-v3", latest)
        return {"id": report, **latest}


@pytest.mark.parametrize("leave_old_report", [False, True])
def test_audited_v3_report_and_historical_v2_report_have_distinct_currency(tmp_path, monkeypatch, leave_old_report):
    owner = tmp_path / "v3-active"
    monkeypatch.setattr(m, "ACTIVE_OWNER", owner)
    monkeypatch.setattr(m, "workers", lambda _: [])
    worker = V3MetadataOwner(owner, config=Config(offline=True))
    try:
        report = worker.execute("status", {"leave_old_report": leave_old_report}, objective="Synthetic v3 chain", actor="test:monitor")
        v2_id = worker.ledger.db.execute("SELECT id FROM records WHERE kind='cyber_dossier_execution_amendment'").fetchone()[0]
        v3_id = worker.ledger.db.execute("SELECT id FROM records WHERE kind='cyber_dossier_execution_amendment_v3'").fetchone()[0]
        head_before = tuple(worker.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        worker.close()
    monkeypatch.setattr(m, "EXPECTED_PLAN", report["plan"])
    monkeypatch.setattr(m, "EXPECTED_V2", v2_id)
    monkeypatch.setattr(m, "EXPECTED_V3", v3_id)
    (owner / "dossier-report.json").write_text(json.dumps(report), encoding="utf-8")
    observer = m.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = observer.execute("status", {}, objective="Observe synthetic v3", actor="test:monitor")
        assert result["latest_report_current"] is not leave_old_report
        assert result["pilot_v3_gate"] == (None if leave_old_report else {"passed": False, "reference_pairs": 3})
        assert result["full_v3_outcome"] is None
        assert result["pilot_gate_phase"] == "pilot_v3_gate" and result["full_outcome_phase"] == "full_v3_outcome"
        assert result["provenance"]["v2_execution_amendment"] == v2_id
        assert result["provenance"]["implementation_verification"]["verified_files"] == 3
        assert result["state"] == "stopped" and result["phase_eta_seconds"] is None
        assert result["new_model_calls"] == 0 and observer.gateway.provider.calls == 0
        assert tuple(result["provenance"]["head"]) == head_before
        if not leave_old_report:
            assert result["legacy_held_cost_usd"] == .1 and result["new_unresolved_holds"] == 0
    finally:
        observer.close()


def extended_chain(plan, v2, v3, deadline):
    diagnostic = {"_record_id": "diagnostic", "parent_plan": plan["_record_id"],
        "execution_amendment": v3["_record_id"], "original_deadline": deadline,
        "implementation": v3["implementation"], "cap_nanousd": m.CAP_NANOUSD,
        "audit_cap_nanousd": 10_000_000_000, "main_cap_nanousd": 35_000_000_000,
        "diagnostic_cap_nanousd": 2_000_000_000, "baseline_budget": v3["legacy_budget"],
        "baseline_hold_attempts": v3["legacy_unresolved_attempts"]}
    budget = {"settled_nanousd": 30, "held_nanousd": 300 + v3["legacy_budget"]["held_nanousd"],
        "unresolved_holds": len(v3["legacy_unresolved_attempts"]) + 3}
    budget["committed_nanousd"] = budget["settled_nanousd"] + budget["held_nanousd"]
    old_report = {**budget, "_record_id": "diagnostic-report", "_created_event": 15,
        "diagnostic_plan": diagnostic["_record_id"], "plan": plan["_record_id"],
        "execution_amendment": v3["_record_id"], "original_deadline": deadline,
        "legacy_unresolved_holds": len(v3["legacy_unresolved_attempts"]), "new_unresolved_holds": 3,
        "legacy_held_nanousd": v3["legacy_budget"]["held_nanousd"], "new_held_nanousd": 300}
    required = ["schema-a", "schema-b", "schema-c"]
    repair = {"_record_id": "diagnostic-repair", "parent_diagnostic_plan": diagnostic["_record_id"],
        "parent_diagnostic_report": old_report["_record_id"], "parent_implementation": diagnostic["implementation"],
        "implementation": diagnostic["implementation"], "parent_plan": plan["_record_id"],
        "execution_amendment": v3["_record_id"], "original_deadline": deadline,
        "repair_cap_nanousd": 2_000_000_000, "combined_diagnostic_cap_nanousd": 4_000_000_000,
        "total_cap_nanousd": m.CAP_NANOUSD, "audit_cap_nanousd": 10_000_000_000,
        "baseline_budget": budget, "baseline_hold_attempts": [*v3["legacy_unresolved_attempts"], *required],
        "required_parent_hold_attempts": required}
    repaired_report = {**old_report, "_record_id": "repair-report", "_created_event": 20,
        "diagnostic_plan": repair["_record_id"], "parent_diagnostic_plan": diagnostic["_record_id"]}
    v4 = {"_record_id": "v4", "_created_event": 21, "parent_plan": plan["_record_id"],
        "parent_execution_amendment": v3["_record_id"], "parent_implementation": v3["implementation"],
        "implementation": {**v3["implementation"], **code_manifest("_v4")},
        "original_deadline": deadline, "cap_nanousd": m.CAP_NANOUSD, **m.V4_ALLOCATION,
        "summary_reference_minimum": 6, "summary_reference_target": 10,
        "ancestor_execution_amendments": {"v2": v2["_record_id"], "v3": v3["_record_id"]},
        "diagnostic_plan": diagnostic["_record_id"], "diagnostic_amendment": repair["_record_id"],
        "diagnostic_report": repaired_report["_record_id"],
        "legacy_budget": budget, "legacy_unresolved_attempts": repair["baseline_hold_attempts"]}
    return v4, diagnostic, old_report, repair, repaired_report


@pytest.mark.parametrize("change", [None, "repair_parent", "repair_cap", "report_binding", "required_hold",
                                    "cost_carry", "ancestor", "allocation", "summary_reference"])
def test_v4_requires_complete_diagnostic_repair_lineage(monkeypatch, change):
    plan, v2, v3, deadline = chain(monkeypatch)
    v4, diagnostic, old_report, repair, repaired_report = deepcopy(extended_chain(plan, v2, v3, deadline))
    monkeypatch.setattr(m, "EXPECTED_DIAGNOSTIC", diagnostic["_record_id"])
    monkeypatch.setattr(m, "EXPECTED_DIAGNOSTIC_REPAIR", repair["_record_id"])
    monkeypatch.setattr(m, "EXPECTED_V4", v4["_record_id"])
    if change == "repair_parent":
        repair["parent_diagnostic_plan"] = "wrong"
    elif change == "repair_cap":
        repair["repair_cap_nanousd"] += 1
    elif change == "report_binding":
        v4["diagnostic_report"] = "later-unbound-report"
    elif change == "required_hold":
        repair["required_parent_hold_attempts"] = ["replacement", "schema-b", "schema-c"]
    elif change == "cost_carry":
        v4["legacy_budget"] = {**v4["legacy_budget"], "settled_nanousd": 29,
                                "committed_nanousd": v4["legacy_budget"]["committed_nanousd"] - 1}
    elif change == "ancestor":
        v4["ancestor_execution_amendments"] = {"v2": "other", "v3": "v3"}
    elif change == "allocation":
        v4["audit_cap_nanousd"] += 1
    elif change == "summary_reference":
        v4["summary_reference_minimum"] = 5
    if change:
        with pytest.raises(AuditError):
            m.validate_chain(plan, v2, v3, deadline, v4, diagnostic, old_report, repair, repaired_report)
    else:
        assert m.validate_chain(plan, v2, v3, deadline, v4, diagnostic, old_report, repair, repaired_report)["verified_files"] == 4
        later = {**repaired_report, "_record_id": "later", "_created_event": 99}
        assert m.bound_report([repaired_report, later], v4["diagnostic_report"]) == repaired_report


@pytest.mark.parametrize("runner", sorted(m.DIAGNOSTIC_RUNNERS))
def test_both_diagnostic_writers_block_old_dossier_eta_and_detect_duplicates(tmp_path, runner):
    item = process(tmp_path)
    item["command_line"] = item["command_line"].replace("run_dossiers.py", runner)
    matched = m.matching_processes([item], tmp_path)
    assert matched[0]["worker_kind"] == "summary_diagnostic"
    measured = m.phase_timing(checkpoint(), [], NOW, matched, False, None)
    assert measured["state"] == "summary_diagnostic_active"
    assert measured["phase_eta_seconds"] is None
    assert measured["phase_eta_blocker"] == "independent_summary_diagnostic_active"
    both = m.matching_processes([item, process(tmp_path, pid=12)], tmp_path)
    assert m.phase_timing(checkpoint(), [], NOW, both, False, None)["state"] == "multiple_workers_needs_investigation"
    assert not m.report_is_current({}, {}, {}, checkpoint(), matched)
    item["command_line"] = item["command_line"].replace(" run ", " pilot ")
    assert m.matching_processes([item], tmp_path) == []


def test_unresolved_attempt_after_report_prevents_current_claim():
    report = {"plan": "plan", "stored_responses": 1, "_created_event": 20,
        "articles": m.EXPECTED_ARTICLES, "distinct_inputs": m.EXPECTED_DOCUMENTS, "at": NOW.isoformat()}
    state = {"responses": 1, "last_response_event": 19, "last_attempt_event": 21}
    assert not m.report_is_current(report, {"_record_id": "plan"}, state, None, [])


def test_diagnostic_checkpoint_cannot_drop_repair_baseline():
    diagnostic = {"baseline_budget": {"settled_nanousd": 10, "held_nanousd": 40,
                                      "committed_nanousd": 50, "unresolved_holds": 4}}
    m.validate_diagnostic_snapshot(diagnostic["baseline_budget"], diagnostic)
    reduced = {**diagnostic["baseline_budget"], "held_nanousd": 30, "committed_nanousd": 40}
    with pytest.raises(AuditError, match="diagnostic_checkpoint_liability_reduced"):
        m.validate_diagnostic_snapshot(reduced, diagnostic)


class V4MetadataOwner(V3MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        prior = super()._status(session, context, {})

        def one(kind):
            row = self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (kind,)).fetchone()
            return {**self.ledger.get(row[0], kind), "_record_id": row[0]}

        def save(kind, key, row):
            value = {k: v for k, v in row.items() if not k.startswith("_")}
            identifier = self.ledger.record(session, kind, key, value)
            return {**value, "_record_id": identifier}

        plan, v2, v3 = [one(k) for k in ("cyber_dossier_plan", "cyber_dossier_execution_amendment",
                                        "cyber_dossier_execution_amendment_v3")]
        v4, diagnostic, old, repair, new = extended_chain(plan, v2, v3, v3["original_deadline"])
        diagnostic = save("cyber_summary_fidelity_diagnostic_plan", "synthetic", diagnostic)
        for i in range(3):
            save("cyber_dossier_response", f"diag-{i}", {"phase": "summary_fidelity_audit",
                "diagnostic_plan": diagnostic["_record_id"]})
        old.update(diagnostic_plan=diagnostic["_record_id"], stored_diagnostic_responses=3, at=utc())
        old = save("cyber_summary_fidelity_diagnostic_report", "synthetic", old)
        repair.update(parent_diagnostic_plan=diagnostic["_record_id"], parent_diagnostic_report=old["_record_id"])
        repair = save("cyber_summary_fidelity_diagnostic_amendment_v2", "synthetic", repair)
        for i in range(9):
            save("cyber_dossier_response", f"repair-{i}", {"phase": "summary_fidelity_audit",
                "diagnostic_plan": repair["_record_id"]})
        new.update(diagnostic_plan=repair["_record_id"], parent_diagnostic_plan=diagnostic["_record_id"],
                   stored_diagnostic_responses=12, at=utc())
        new = save("cyber_summary_fidelity_diagnostic_report_v2", "synthetic", new)
        v4.update(diagnostic_plan=diagnostic["_record_id"], diagnostic_amendment=repair["_record_id"],
                  diagnostic_report=new["_record_id"])
        v4 = save("cyber_dossier_execution_amendment_v4", "synthetic", v4)
        # A later report must not replace the immutable report bound by the amendment.
        save("cyber_summary_fidelity_diagnostic_report_v2", "later", {**new, "at": utc()})
        report = {k: v for k, v in prior.items() if k != "id"}
        report.update(execution_amendment=v4["_record_id"], stored_responses=13,
            **v4["legacy_budget"], legacy_unresolved_holds=len(v4["legacy_unresolved_attempts"]),
            legacy_held_nanousd=v4["legacy_budget"]["held_nanousd"], new_unresolved_holds=0,
            new_held_nanousd=0, pipeline_processing_complete=True, pipeline_finished=False,
            final_audit_complete=False, final_audit_completion={"selected": 60, "attempted": 10,
                "available": 8, "unavailable": 52, "complete": False},
            pilot_summary_reference={"selected": 10, "attempted": 10, "valid": 10, "supported": 10,
                "unsupported": 0, "uncertain": 0, "unavailable": 0, "passed": True}, at=utc())
        final = save("cyber_dossier_report", "synthetic-v4", report)
        return {"report": final, "plan": plan, "v2": v2, "v3": v3, "v4": v4,
                "diagnostic": diagnostic, "repair": repair}


@pytest.mark.parametrize("diagnostic_running", [False, True])
def test_registered_v4_observer_preserves_diagnostic_costs_and_partial_audit_state(tmp_path, monkeypatch, diagnostic_running):
    owner = tmp_path / "v4-active"
    monkeypatch.setattr(m, "ACTIVE_OWNER", owner)
    worker = V4MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute("status", {}, objective="Synthetic v4 metadata", actor="test:monitor")
        head = tuple(worker.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        worker.close()
    for constant, name in (("EXPECTED_PLAN", "plan"), ("EXPECTED_V2", "v2"), ("EXPECTED_V3", "v3"), ("EXPECTED_V4", "v4"),
                           ("EXPECTED_DIAGNOSTIC", "diagnostic"), ("EXPECTED_DIAGNOSTIC_REPAIR", "repair")):
        monkeypatch.setattr(m, constant, values[name]["_record_id"])
    now = datetime.now(timezone.utc)
    item = process(owner, created=now - timedelta(minutes=1))
    item["command_line"] = item["command_line"].replace("run_dossiers.py", m.DIAGNOSTIC_REPAIR_RUNNER)
    processes = m.matching_processes([item], owner) if diagnostic_running else []
    monkeypatch.setattr(m, "workers", lambda _: processes)
    if diagnostic_running:
        progress = checkpoint(at=now, phase="summary_fidelity_audit_v2")
        progress.update(**values["repair"]["baseline_budget"],
            responses=13, diagnostic_plan=values["repair"]["_record_id"],
            execution_amendment=values["v3"]["_record_id"],
            legacy_unresolved_holds=len(values["v3"]["legacy_unresolved_attempts"]),
            legacy_held_nanousd=values["v3"]["legacy_budget"]["held_nanousd"],
            new_unresolved_holds=3, new_held_nanousd=300)
        (owner / "progress.json").write_text(json.dumps(progress), encoding="utf-8")
    observer = m.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = observer.execute("status", {}, objective="Observe synthetic v4 metadata", actor="test:monitor")
        assert result["stored_diagnostic_responses"] == 12
        assert result["diagnostic_worker_active"] is diagnostic_running
        assert result["latest_report_current"] is not diagnostic_running
        assert result["phase_eta_seconds"] is None
        assert result["full_v4_outcome"] is None
        if diagnostic_running:
            assert result["pilot_gate"] is None and result["final_coverage"] is None
            assert result["full_v4_processing_outcome"] is None
            assert result["state"] == "summary_diagnostic_active"
            assert result["checkpoint_version_matches_worker"] is True
            assert result["checkpoint_matches_current_execution"] is True
        else:
            assert result["final_coverage"]["pipeline_processing_complete"] is True
            assert result["final_coverage"]["final_audit_complete"] is False
            assert result["full_v4_processing_outcome"]["final_audit_completion"]["unavailable"] == 52
            assert result["pilot_summary_reference"]["supported"] == 10
            assert result["legacy_unresolved_holds"] == 4
            assert result["committed_nanousd"] == values["v4"]["legacy_budget"]["committed_nanousd"]
        assert result["v4_budget_allocation_nanousd"] == m.V4_ALLOCATION
        assert result["v4_summary_reference_requirement"] == {"minimum": 6, "target": 10,
            "all_selected_must_be_valid_supported": True}
        assert observer.gateway.provider.calls == 0
        assert tuple(result["provenance"]["head"]) == head
    finally:
        observer.close()


def v5_extension(plan, v2, v3, v4):
    budget = {**v4["legacy_budget"], "settled_nanousd": v4["legacy_budget"]["settled_nanousd"] + 10,
              "committed_nanousd": v4["legacy_budget"]["committed_nanousd"] + 10}
    parent_report = {"_record_id": "v4-report", "plan": plan["_record_id"],
        "execution_amendment": v4["_record_id"], **budget,
        "legacy_unresolved_holds": len(v4["legacy_unresolved_attempts"]),
        "legacy_held_nanousd": budget["held_nanousd"], "new_unresolved_holds": 0, "new_held_nanousd": 0}
    v5 = {"_record_id": "v5", "parent_plan": plan["_record_id"],
        "parent_execution_amendment": v4["_record_id"], "parent_implementation": v4["implementation"],
        "implementation": {**v4["implementation"], **code_manifest("_v5")},
        "ancestor_execution_amendments": {"v2": v2["_record_id"], "v3": v3["_record_id"], "v4": v4["_record_id"]},
        "parent_report": parent_report["_record_id"], "original_deadline": v4["original_deadline"],
        **{key: v4[key] for key in ("diagnostic_plan", "diagnostic_amendment", "diagnostic_report")},
        **m.V5_ALLOCATION, "card_reference_minimum": 6, "card_reference_target": 10,
        "cap_nanousd": m.CAP_NANOUSD, "legacy_budget": budget,
        "legacy_unresolved_attempts": v4["legacy_unresolved_attempts"]}
    return v5, parent_report


@pytest.mark.parametrize("fault", [None, "wrong_parent", "lost_v4_cost", "changed_allocation",
                                   "lowered_card_gate", "wrong_v4_identity", "wrong_diagnostic"])
def test_v5_binds_v4_report_costs_frozen_identity_and_card_gate(monkeypatch, fault):
    plan, v2, v3, deadline = chain(monkeypatch)
    v4, diagnostic, old_report, repair, repaired_report = extended_chain(plan, v2, v3, deadline)
    monkeypatch.setattr(m, "EXPECTED_V4", v4["_record_id"])
    monkeypatch.setattr(m, "EXPECTED_DIAGNOSTIC", diagnostic["_record_id"])
    monkeypatch.setattr(m, "EXPECTED_DIAGNOSTIC_REPAIR", repair["_record_id"])
    v5, parent_report = v5_extension(plan, v2, v3, v4)
    if fault == "wrong_parent":
        v5["parent_report"] = "replacement"
    elif fault == "lost_v4_cost":
        v5["legacy_budget"] = v4["legacy_budget"]
    elif fault == "changed_allocation":
        v5["audit_cap_nanousd"] += 1
    elif fault == "lowered_card_gate":
        v5["card_reference_minimum"] = 5
    elif fault == "wrong_v4_identity":
        monkeypatch.setattr(m, "EXPECTED_V4", "other-v4")
    elif fault == "wrong_diagnostic":
        v5["diagnostic_report"] = "other-diagnostic"
    args = (plan, v2, v3, deadline, v4, diagnostic, old_report, repair, repaired_report, v5, parent_report)
    if fault:
        with pytest.raises(AuditError):
            m.validate_chain(*args)
    else:
        assert m.validate_chain(*args)["verified_files"] == 5


class V5MetadataOwner(V4MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        v5, _ = v5_extension(values["plan"], values["v2"], values["v3"], values["v4"])
        v5["parent_report"] = values["report"]["_record_id"]
        payload = {k: v for k, v in v5.items() if not k.startswith("_")}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment_v5", "synthetic", payload)
        values["v5"] = {**payload, "_record_id": identifier}
        if data.get("leave_old_report"):
            return values
        report = {k: v for k, v in values["report"].items() if not k.startswith("_")}
        report.pop("pilot_summary_reference")
        report.update(execution_amendment=identifier, **v5["legacy_budget"], at=utc(),
            groups_with_usable_card=3, groups_with_usable_summary=None,
            provisional_card_incomplete_groups=1, quality_rejected_or_unavailable_groups=2,
            quality_rejected_or_unavailable_articles=4, quarantined_groups=1, quarantined_articles=2,
            nonjoined_audit_candidate_pool=234,
            nonjoined_audit_selected_endpoint_status_counts={"unresolved": 20, "card_supported_group": 80},
            pilot_card_reference={"selected": 10, "attempted": 10, "valid": 10, "supported": 9,
                "unclear_focus": 1, "identity_missing": 0, "incoherent_group": 0, "uncertain": 0,
                "unavailable": 0, "passed": False},
            pilot_full_bundle_control={"selected": 12, "valid": 12, "matches": 9,
                "acceptance_effect": False}, pilot_gate={"passed": False})
        identifier = self.ledger.record(session, "cyber_dossier_report", "synthetic-v5", report)
        values["report"] = {**report, "_record_id": identifier}
        return values


@pytest.mark.parametrize("leave_old_report", [False, True])
def test_registered_v5_observer_separates_cards_control_and_stale_v4_gate(tmp_path, monkeypatch, leave_old_report):
    owner = tmp_path / "v5-active"
    monkeypatch.setattr(m, "ACTIVE_OWNER", owner)
    monkeypatch.setattr(m, "workers", lambda _: [])
    worker = V5MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute("status", {"leave_old_report": leave_old_report},
                                objective="Synthetic v5 card metadata", actor="test:monitor")
        head = tuple(worker.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        worker.close()
    for constant, name in (("EXPECTED_PLAN", "plan"), ("EXPECTED_V2", "v2"), ("EXPECTED_V3", "v3"),
                           ("EXPECTED_V4", "v4"), ("EXPECTED_DIAGNOSTIC", "diagnostic"),
                           ("EXPECTED_DIAGNOSTIC_REPAIR", "repair")):
        monkeypatch.setattr(m, constant, values[name]["_record_id"])
    observer = m.Study(tmp_path / "monitor", config=Config(offline=True))
    try:
        result = observer.execute("status", {}, objective="Observe synthetic v5 card metadata", actor="test:monitor")
        assert result["latest_report_current"] is not leave_old_report
        assert result["pilot_gate_phase"] == "pilot_v5_gate" and result["full_outcome_phase"] == "full_v5_outcome"
        assert result["pilot_summary_reference"] is None and result["pilot_v4_gate"] is None
        assert result["v5_budget_allocation_nanousd"] == m.V5_ALLOCATION
        if leave_old_report:
            assert result["pilot_card_reference"] is None and result["pilot_full_bundle_control"] is None
            assert result["final_coverage"] is None
        else:
            assert result["pilot_card_reference"]["unclear_focus"] == 1
            assert result["pilot_full_bundle_control"]["acceptance_effect"] is False
            assert result["full_v5_processing_outcome"]["groups_with_usable_card"] == 3
            assert result["full_v5_processing_outcome"]["provisional_card_incomplete_groups"] == 1
            assert result["full_v5_processing_outcome"]["quality_rejected_or_unavailable_groups"] == 2
            assert result["full_v5_processing_outcome"]["quality_rejected_or_unavailable_articles"] == 4
            assert result["full_v5_processing_outcome"]["quarantined_articles"] == 2
            assert result["full_v5_processing_outcome"]["nonjoined_audit_candidate_pool"] == 234
            assert result["full_v5_processing_outcome"]["nonjoined_audit_selected_endpoint_status_counts"]["unresolved"] == 20
            assert result["full_v5_outcome"] is None
            assert result["committed_nanousd"] == values["v5"]["legacy_budget"]["committed_nanousd"]
        assert result["phase_eta_seconds"] is None and observer.gateway.provider.calls == 0
        assert tuple(result["provenance"]["head"]) == head
    finally:
        observer.close()


def v6_extension(plan, v2, v3, v4, v5, parent_report):
    budget = {**v5['legacy_budget'], 'settled_nanousd': v5['legacy_budget']['settled_nanousd'] + 10,
              'committed_nanousd': v5['legacy_budget']['committed_nanousd'] + 10}
    return {'_record_id': 'v6', 'parent_plan': plan['_record_id'],
        'parent_execution_amendment': v5['_record_id'], 'parent_implementation': v5['implementation'],
        'implementation': {**v5['implementation'], **code_manifest('_v6')},
        'ancestor_execution_amendments': {'v2': v2['_record_id'], 'v3': v3['_record_id'],
                                         'v4': v4['_record_id'], 'v5': v5['_record_id']},
        'parent_report': parent_report['_record_id'], 'original_deadline': v5['original_deadline'],
        'v5_diagnostic': {'record_id': m.EXPECTED_V5_DIAGNOSTIC, 'owner': 'separate-private-observer'},
        **m.V6_ALLOCATION, 'minimum_incoming_articles': 6, 'cap_nanousd': m.CAP_NANOUSD, 'legacy_budget': budget,
        'legacy_unresolved_attempts': v5['legacy_unresolved_attempts'],
        'pilot_selection_artifact': 'synthetic-selection', 'legacy_response_keys': ['prior-response']}


@pytest.mark.parametrize('fault', [None, 'parent', 'ancestor', 'report', 'diagnosis', 'cost',
                                   'pilot_main', 'pilot_audit', 'hold', 'deadline', 'gate_minimum'])
def test_v6_reanalysis_preserves_exact_v5_parent_all_liabilities_and_pilot_subcaps(monkeypatch, fault):
    plan, v2, v3, deadline = chain(monkeypatch)
    v4, diagnostic, old_report, repair, repaired_report = extended_chain(plan, v2, v3, deadline)
    v5, v4_report = v5_extension(plan, v2, v3, v4)
    v5_report = {**v4_report, '_record_id': 'v5-report', 'execution_amendment': v5['_record_id']}
    v6 = v6_extension(plan, v2, v3, v4, v5, v5_report)
    for name, value in [('EXPECTED_V4', v4['_record_id']), ('EXPECTED_V5', v5['_record_id']),
                        ('EXPECTED_V5_REPORT', v5_report['_record_id']),
                        ('EXPECTED_DIAGNOSTIC', diagnostic['_record_id']), ('EXPECTED_DIAGNOSTIC_REPAIR', repair['_record_id'])]:
        monkeypatch.setattr(m, name, value)
    if fault == 'parent':
        v6['parent_execution_amendment'] = 'other'
    elif fault == 'ancestor':
        v6['ancestor_execution_amendments']['v3'] = 'other'
    elif fault == 'report':
        v6['parent_report'] = 'other'
    elif fault == 'diagnosis':
        v6['v5_diagnostic']['record_id'] = 'other'
    elif fault == 'cost':
        v6['legacy_budget']['settled_nanousd'] = v5_report['settled_nanousd'] - 1
        v6['legacy_budget']['committed_nanousd'] = v6['legacy_budget']['settled_nanousd'] + v6['legacy_budget']['held_nanousd']
    elif fault in {'pilot_main', 'pilot_audit'}:
        v6[f'{fault}_cap_nanousd'] += 1
    elif fault == 'hold':
        v6['legacy_unresolved_attempts'] = v6['legacy_unresolved_attempts'][1:]
    elif fault == 'gate_minimum':
        v6['minimum_incoming_articles'] = 5
    elif fault == 'deadline':
        v6['original_deadline'] = '2031-01-01T00:00:00+00:00'
    args = (plan, v2, v3, deadline, v4, diagnostic, old_report, repair, repaired_report,
            v5, v4_report, v6, v5_report)
    if fault:
        with pytest.raises(AuditError):
            m.validate_chain(*args)
    else:
        assert m.validate_chain(*args)['verified_files'] == 6


class V6MetadataOwner(V5MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        values['v5_report'] = values['report']
        v6 = v6_extension(values['plan'], values['v2'], values['v3'], values['v4'], values['v5'], values['report'])
        payload = {key: value for key, value in v6.items() if not key.startswith('_')}
        identifier = self.ledger.record(session, 'cyber_dossier_execution_amendment_v6', 'synthetic', payload)
        values['v6'] = {**payload, '_record_id': identifier}
        if data.get('leave_old_report'):
            return values
        report = {key: value for key, value in values['report'].items() if not key.startswith('_')}
        report.update(execution_amendment=identifier, **v6['legacy_budget'], at=utc(),
            pilot_gate={'passed': True, 'incoming_accepted': 6, 'distinct_expanded_groups': 1},
            pilot_primary={'selected': 2, 'normal_valid': 2, 'normal_supported': 1,
                'reference_valid': 2, 'reference_supported': 1,
                'normal_accepted_reference_unsupported_or_unavailable': 0, 'unavailable': 0},
            pilot_secondary={'selected': 12, 'valid': 3, 'labels': {'supported': 2, 'uncertain': 1},
                'unavailable': 9, 'shared_primary_tasks': 1},
            rejected_expansion_groups=1, unresolved_rival_relations=8,
            nonjoined_audit_frame_counts={'base_retrieval_pairs': 234, 'uncertain_rival_pairs': 8,
                'added_uncertain_rival_pairs': 4, 'deduplicated_union_pairs': 238, 'candidate_pool': 220},
            pilot_budget={"main": {"committed_nanousd": 12}, "audit": {"committed_nanousd": 34}})
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v6', report)
        values['report'] = {**report, '_record_id': identifier}
        return values


@pytest.mark.parametrize('leave_old_report', [False, True])
def test_v6_observer_keeps_group_dependence_partial_secondary_and_historical_gate_distinct(tmp_path, monkeypatch, leave_old_report):
    owner = tmp_path / 'v6-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V6MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'leave_old_report': leave_old_report},
                                objective='Synthetic v6 reanalysis metadata', actor='test:monitor')
        head = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
    finally:
        worker.close()
    for constant, name in [('EXPECTED_PLAN', 'plan'), ('EXPECTED_V2', 'v2'), ('EXPECTED_V3', 'v3'),
                           ('EXPECTED_V4', 'v4'), ('EXPECTED_V5', 'v5'), ('EXPECTED_V5_REPORT', 'v5_report'),
                           ('EXPECTED_DIAGNOSTIC', 'diagnostic'), ('EXPECTED_DIAGNOSTIC_REPAIR', 'repair')]:
        monkeypatch.setattr(m, constant, values[name]['_record_id'])
    observer = m.Study(tmp_path / 'monitor', config=Config(offline=True))
    try:
        result = observer.execute('status', {}, objective='Observe synthetic v6 metadata', actor='test:monitor')
        assert result['latest_report_current'] is not leave_old_report
        assert result['pilot_gate_phase'] == 'pilot_v6_gate' and result['full_outcome_phase'] == 'full_v6_outcome'
        assert result['pilot_card_reference'] is None and result['pilot_full_bundle_control'] is None
        assert result['pilot_v5_gate'] is None and result['full_v5_processing_outcome'] is None
        assert result['v6_budget_allocation_nanousd'] == m.V6_ALLOCATION
        assert result['reused_v5_evidence']['historical_failed_gate'] == {'passed': False}
        assert result['reused_v5_evidence']['new_independent_validation'] is False
        assert 'share expanded groups' in result['v6_evidence_scope']
        if leave_old_report:
            assert result['pilot_v6_gate'] is None and result['pilot_primary'] is None and result['pilot_secondary'] is None
            assert result['full_v6_processing_outcome'] is None
        else:
            assert result['pilot_v6_gate'] == {'passed': True, 'incoming_accepted': 6, 'distinct_expanded_groups': 1}
            assert result['pilot_primary']['selected'] == 2 and result['pilot_primary']['reference_valid'] == 2
            assert result['pilot_secondary']['selected'] == 12 and result['pilot_secondary']['unavailable'] == 9
            assert result['full_v6_processing_outcome']['rejected_expansion_groups'] == 1
            assert result['pilot_budget']['audit']['committed_nanousd'] == 34
            assert result['full_v6_processing_outcome']['unresolved_rival_relations'] == 8
            assert result['full_v6_processing_outcome']['nonjoined_audit_frame_counts']['added_uncertain_rival_pairs'] == 4
            assert result['full_v6_outcome'] is None
            assert result['committed_nanousd'] == values['v6']['legacy_budget']['committed_nanousd']
        assert observer.gateway.provider.calls == 0 and result['phase_eta_seconds'] is None
        assert tuple(result['provenance']['head']) == head
    finally:
        observer.close()


@pytest.mark.parametrize('old_checkpoint', [False, True])
def test_v6_active_worker_cannot_reuse_v5_checkpoint_or_stopped_gate(tmp_path, monkeypatch, old_checkpoint):
    owner = tmp_path / 'v6-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    worker = V6MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {}, objective='Synthetic v6 active worker metadata', actor='test:monitor')
    finally:
        worker.close()
    for constant, name in [('EXPECTED_PLAN', 'plan'), ('EXPECTED_V2', 'v2'), ('EXPECTED_V3', 'v3'),
                           ('EXPECTED_V4', 'v4'), ('EXPECTED_V5', 'v5'), ('EXPECTED_V5_REPORT', 'v5_report'),
                           ('EXPECTED_DIAGNOSTIC', 'diagnostic'), ('EXPECTED_DIAGNOSTIC_REPAIR', 'repair')]:
        monkeypatch.setattr(m, constant, values[name]['_record_id'])
    now = datetime.now(timezone.utc)
    row = process(owner, created=now - timedelta(minutes=1))
    row['command_line'] = row['command_line'].replace('run_dossiers.py', 'run_dossiers_v6.py')
    monkeypatch.setattr(m, 'workers', lambda _: m.matching_processes([row], owner))
    amendment = values['v5' if old_checkpoint else 'v6']
    progress = checkpoint(at=now, completed=0, phase='v6_primary_expanded_group_quality')
    progress.update(execution_amendment=amendment['_record_id'], **amendment['legacy_budget'],
        legacy_unresolved_holds=4, new_unresolved_holds=0,
        legacy_held_nanousd=amendment['legacy_budget']['held_nanousd'], new_held_nanousd=0,
        deadline=amendment['original_deadline'])
    (owner / 'progress.json').write_text(json.dumps(progress), encoding='utf-8')
    observer = m.Study(tmp_path / 'monitor', config=Config(offline=True))
    try:
        result = observer.execute('status', {}, objective='Observe synthetic v6 active worker', actor='test:monitor')
        assert not result['latest_report_current'] and result['pilot_gate'] is None
        assert result['pilot_primary'] is None and result['full_v6_processing_outcome'] is None
        assert result['worker_python_processes'][0]['runner'] == 'run_dossiers_v6.py'
        assert result['checkpoint_version_matches_worker'] is not old_checkpoint
        assert result['checkpoint_matches_current_execution'] is not old_checkpoint
        if old_checkpoint:
            assert result['state'] == 'starting_or_waiting_first_checkpoint'
            assert result['phase_eta_blocker'] == 'checkpoint_from_different_execution_amendment'
        else:
            assert result['state'] == 'running'
        assert result['phase_eta_seconds'] is None and observer.gateway.provider.calls == 0
    finally:
        observer.close()


def capacity_fixture():
    return {'proposed_packets': 10, 'reused_prior_attempt_packets': 2, 'untouched_fitting_packets': 6,
        'deferred_unjudged_packets': 2, 'proposed_distinct_articles': 20, 'fitting_or_reused_distinct_articles': 16,
        'deferred_distinct_articles': 4, 'intended_within_packet_pairs': 30, 'deferred_unasked_within_packet_pairs': 6,
        'fitting_and_deferred_article_overlap': 0, 'distinct_intended_within_packet_pairs': 30,
        'distinct_deferred_unasked_within_packet_pairs': 6,
        'deferred_maximum_input_tokens_proxy': 33000, 'token_limit': 32000, 'wire_byte_limit': 2097152,
        'article_inputs_or_questions_changed': False, 'packets_split': False, 'deferred_are_provider_unknowns': False,
        'deferred_billing_holds': 0, 'later_assignment_and_recovery_eligible': True, 'model_calls': 0}


def v7_extension(plan, v2, v3, v4, v5, v6, passed, stopped, gate):
    budget = {**v6['legacy_budget'], 'settled_nanousd': v6['legacy_budget']['settled_nanousd'] + 5,
        'committed_nanousd': v6['legacy_budget']['committed_nanousd'] + 5}
    return {'_record_id': 'v7', 'parent_plan': plan['_record_id'], 'parent_execution_amendment': v6['_record_id'],
        'parent_implementation': v6['implementation'], 'implementation': {**v6['implementation'], **code_manifest('_v7')},
        'ancestor_execution_amendments': {'v2': v2['_record_id'], 'v3': v3['_record_id'], 'v4': v4['_record_id'],
            'v5': v5['_record_id'], 'v6': v6['_record_id']},
        'parent_report': stopped['_record_id'], 'passed_pilot_report': passed['_record_id'],
        'passed_gate_record': gate['record']['_record_id'], 'original_deadline': v6['original_deadline'],
        **m.V6_ALLOCATION, 'minimum_incoming_articles': 6, 'cap_nanousd': m.CAP_NANOUSD,
        'legacy_unresolved_attempts': v6['legacy_unresolved_attempts'], 'legacy_budget': budget,
        'v6_pilot_budget_baseline': {'legacy_response_keys': v6['legacy_response_keys'],
                                   'legacy_unresolved_attempts': v6['legacy_unresolved_attempts']},
        'seed_capacity_census': capacity_fixture(), 'seed_packet_plan_artifact': 'synthetic-seed-plan'}


@pytest.mark.parametrize('fault', [None, 'wrong_parent', 'wrong_passed', 'wrong_stopped', 'wrong_gate',
                                   'failed_gate', 'pilot_reset', 'lost_cost', 'changed_capacity', 'changed_holds'])
def test_v7_chain_preserves_passed_v6_gate_limits_costs_and_pilot_baseline(monkeypatch, fault):
    plan, v2, v3, deadline = chain(monkeypatch)
    v4, diagnostic, old_report, repair, repaired_report = extended_chain(plan, v2, v3, deadline)
    v5, v4_report = v5_extension(plan, v2, v3, v4)
    v5_report = {**v4_report, '_record_id': 'v5-report', 'execution_amendment': v5['_record_id']}
    v6 = v6_extension(plan, v2, v3, v4, v5, v5_report)
    passed = {**v5_report, '_record_id': 'passed-v6', 'execution_amendment': v6['_record_id'],
              **v6['legacy_budget'], 'pilot_gate': {'passed': True, 'incoming_accepted': 18}}
    stopped = {**passed, '_record_id': 'stopped-v6'}
    gate = {'record': {'_record_id': 'gate-v6', 'name': 'pilot_v6_gate', 'plan': plan['_record_id'],
                      'execution_amendment': v6['_record_id']}, 'value': deepcopy(passed['pilot_gate'])}
    v7 = v7_extension(plan, v2, v3, v4, v5, v6, passed, stopped, gate)
    for name, value in [('EXPECTED_V4', v4['_record_id']), ('EXPECTED_V5', v5['_record_id']),
                        ('EXPECTED_V5_REPORT', v5_report['_record_id']), ('EXPECTED_V6', v6['_record_id']),
                        ('EXPECTED_V6_PASSED_REPORT', passed['_record_id']), ('EXPECTED_V6_STOPPED_REPORT', stopped['_record_id']),
                        ('EXPECTED_DIAGNOSTIC', diagnostic['_record_id']), ('EXPECTED_DIAGNOSTIC_REPAIR', repair['_record_id'])]:
        monkeypatch.setattr(m, name, value)
    if fault == 'wrong_parent':
        v7['parent_execution_amendment'] = 'other'
    elif fault == 'wrong_passed':
        v7['passed_pilot_report'] = 'other'
    elif fault == 'wrong_stopped':
        v7['parent_report'] = 'other'
    elif fault == 'wrong_gate':
        gate['value'] = {'passed': True, 'incoming_accepted': 99}
    elif fault == 'failed_gate':
        passed['pilot_gate'] = {'passed': False}
    elif fault == 'pilot_reset':
        v7['v6_pilot_budget_baseline'] = {'legacy_response_keys': ['new'], 'legacy_unresolved_attempts': []}
    elif fault == 'lost_cost':
        v7['legacy_budget'].update(settled_nanousd=0, committed_nanousd=v7['legacy_budget']['held_nanousd'])
    elif fault == 'changed_capacity':
        v7['seed_capacity_census']['token_limit'] = 33000
    elif fault == 'changed_holds':
        v7['seed_capacity_census']['deferred_billing_holds'] = 2
    args = (plan, v2, v3, deadline, v4, diagnostic, old_report, repair, repaired_report,
            v5, v4_report, v6, v5_report, v7, passed, stopped, gate)
    if fault:
        with pytest.raises(AuditError):
            m.validate_chain(*args)
    else:
        assert m.validate_chain(*args)['verified_files'] == 7


@pytest.mark.parametrize('fault', ['source_text', 'negative', 'partition', 'unknown', 'missingness', 'overlap'])
def test_capacity_projection_rejects_text_corruption_and_false_unknowns(fault):
    census = capacity_fixture()
    execution = {'constructed_or_reused_requests': 8, 'capacity_deferred_packets': 2,
        'capacity_deferred_distinct_articles': 4, 'unasked_within_deferred_pairs': 6,
        'stored_invalid_or_unknown_seed_packets': 1, 'covered_seed_article_ids_count': 16,
                    'valid_seed_clarity_answers': 14, 'valid_seed_pair_answers': 20,
        'deferred_are_provider_unknowns': False}
    if fault == 'source_text':
        census['text'] = 'not permitted'
    elif fault == 'negative':
        census['deferred_distinct_articles'] = -1
    elif fault == 'partition':
        census['untouched_fitting_packets'] += 1
    elif fault == 'unknown':
        execution['deferred_are_provider_unknowns'] = True
    elif fault == 'overlap':
        census['fitting_and_deferred_article_overlap'] = 1
    else:
        execution['capacity_deferred_distinct_articles'] = 0
    with pytest.raises(AuditError):
        m.validate_seed_capacity(census, execution)


class V7MetadataOwner(V6MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        passed = values['report']
        gate_value = passed['pilot_gate']
        gate_payload = {'name': 'pilot_v6_gate', 'plan': values['plan']['_record_id'],
            'execution_amendment': values['v6']['_record_id'], 'artifact': self.ledger.artifacts.put(gate_value), 'at': utc()}
        gate_id = self.ledger.record(session, 'cyber_dossier_phase', 'pilot_v6_gate', gate_payload)
        gate = {'record': {**gate_payload, '_record_id': gate_id}, 'value': gate_value}
        stopped_payload = {key: value for key, value in passed.items() if not key.startswith('_')}
        stopped_payload['at'] = utc()
        stopped_id = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v6-stopped', stopped_payload)
        stopped = {**stopped_payload, '_record_id': stopped_id}
        values.update(passed_v6_report=passed, stopped_v6_report=stopped)
        v7 = v7_extension(values['plan'], values['v2'], values['v3'], values['v4'], values['v5'], values['v6'], passed, stopped, gate)
        payload = {key: value for key, value in v7.items() if not key.startswith('_')}
        identifier = self.ledger.record(session, 'cyber_dossier_execution_amendment_v7', 'synthetic', payload)
        values['v7'] = {**payload, '_record_id': identifier}
        if data.get('mode') == 'old':
            return values
        report = {**stopped_payload, 'execution_amendment': identifier, **v7['legacy_budget'], 'at': utc()}
        if data.get('mode') != 'base':
            report.update(technical_extension_version=7, seed_capacity={'frozen_census': v7['seed_capacity_census'],
                'execution_summary': {'constructed_or_reused_requests': 8, 'capacity_deferred_packets': 2,
                    'capacity_deferred_distinct_articles': 4, 'unasked_within_deferred_pairs': 6,
                    'stored_invalid_or_unknown_seed_packets': 1, 'covered_seed_article_ids_count': 16,
                    'valid_seed_clarity_answers': 14, 'valid_seed_pair_answers': 20,
                    'deferred_are_provider_unknowns': False}})
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v7', report)
        values['report'] = {**report, '_record_id': identifier}
        return values


@pytest.mark.parametrize('mode', ['current', 'old', 'base'])
def test_v7_monitor_preserves_v6_gate_and_distinguishes_capacity_from_provider_holds(tmp_path, monkeypatch, mode):
    owner = tmp_path / 'v7-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V7MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'mode': mode}, objective='Synthetic v7 capacity metadata', actor='test:monitor')
        head = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
    finally:
        worker.close()
    for constant, name in [('EXPECTED_PLAN', 'plan'), ('EXPECTED_V2', 'v2'), ('EXPECTED_V3', 'v3'),
        ('EXPECTED_V4', 'v4'), ('EXPECTED_V5', 'v5'), ('EXPECTED_V5_REPORT', 'v5_report'), ('EXPECTED_V6', 'v6'),
        ('EXPECTED_V6_PASSED_REPORT', 'passed_v6_report'), ('EXPECTED_V6_STOPPED_REPORT', 'stopped_v6_report'),
        ('EXPECTED_DIAGNOSTIC', 'diagnostic'), ('EXPECTED_DIAGNOSTIC_REPAIR', 'repair')]:
        monkeypatch.setattr(m, constant, values[name]['_record_id'])
    observer = m.Study(tmp_path / 'monitor', config=Config(offline=True))
    try:
        result = observer.execute('status', {}, objective='Observe synthetic v7 technical continuation', actor='test:monitor')
        assert result['latest_report_current'] is (mode == 'current')
        assert result['pilot_gate_phase'] == 'pilot_v6_gate' and result['full_outcome_phase'] == 'full_v6_outcome'
        assert result['technical_extension_version'] == 7
        assert result['reused_v6_gate']['pilot_gate']['passed'] is True
        assert result['reused_v6_gate']['new_semantic_pilot'] is False
        assert result['registered_seed_capacity_census']['deferred_unjudged_packets'] == 2
        if mode == 'current':
            assert result['pilot_v6_gate']['passed'] is True
            assert result['seed_capacity']['execution_summary']['capacity_deferred_distinct_articles'] == 4
            assert result['unresolved_holds'] == 4 and result['new_unresolved_holds'] == 0
            assert result['full_v6_processing_outcome']['seed_capacity']['frozen_census']['deferred_billing_holds'] == 0
        else:
            assert result['pilot_gate'] is None and result['final_coverage'] is None and result['seed_capacity'] is None
        assert observer.gateway.provider.calls == 0 and result['phase_eta_seconds'] is None
        assert tuple(result['provenance']['head']) == head
    finally:
        observer.close()


def test_v7_has_no_new_pilot_worker_action(tmp_path):
    item = process(tmp_path, action='pilot')
    item['command_line'] = item['command_line'].replace('run_dossiers.py', 'run_dossiers_v7.py')
    assert m.matching_processes([item], tmp_path) == []
    item['command_line'] = item['command_line'].replace(' pilot ', ' run ')
    assert m.matching_processes([item], tmp_path)[0]['runner'] == 'run_dossiers_v7.py'


def revalidation_fixture():
    return {'attempted': 3, 'valid': 3, 'still_invalid': 0, 'model_calls': 0,
            'original_rows_unchanged': True, 'derived_record_ids': ['derived-1', 'derived-2', 'derived-3']}


def v8_extension(v7, report):
    return {**{key: value for key, value in v7.items() if not key.startswith('_')},
        '_record_id': 'v8', 'parent_execution_amendment': v7['_record_id'],
        'parent_implementation': v7['implementation'],
        'implementation': {**v7['implementation'], **code_manifest('_v8')},
        'ancestor_execution_amendments': {**v7['ancestor_execution_amendments'], 'v7': v7['_record_id']},
        'parent_report': report['_record_id'],
        'diagnostic': {'owner': str(m.EXPECTED_V7_DIAGNOSTIC_OWNER), 'record_id': m.EXPECTED_V7_DIAGNOSTIC},
        'eligible_source_response_ids': list(m.EXPECTED_REVALIDATION_RESPONSES),
        'source_validation_error': m.EXPECTED_SOURCE_ERROR, 'normalization_version': m.EXPECTED_NORMALIZATION,
        'derived_revalidation_records': ['derived-1', 'derived-2', 'derived-3'],
        'seed_order_integrity': {'checked_packets': 8, 'map_order_restored_packets': 3,
            'canonical_packet_changes': 0, 'request_changes': 0, 'deferred_packets': 2, 'model_calls': 0}}


class V8MetadataOwner(V7MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        previous = values['report']
        values['stopped_v7_report'] = previous
        extension = v8_extension(values['v7'], previous)
        payload = {key: value for key, value in extension.items() if not key.startswith('_')}
        derived = []
        for original in extension['eligible_source_response_ids']:
            derived.append(self.ledger.record(session, 'cyber_dossier_seed_revalidation', original,
                {'original_response': original, 'parent_execution_amendment': values['v7']['_record_id'], 'model_calls': 0}))
        payload['derived_revalidation_records'] = derived
        identifier = self.ledger.record(session, 'cyber_dossier_execution_amendment_v8', 'synthetic', payload)
        values['v8'] = {**payload, '_record_id': identifier}
        if data.get('mode') == 'old':
            return values
        report = {key: value for key, value in previous.items() if not key.startswith('_')}
        report.update(execution_amendment=identifier, at=utc())
        if data.get('mode') != 'base':
            report.update(technical_extension_version=8, seed_order_integrity=extension['seed_order_integrity'])
        if data.get('mode') != 'missing_revalidation':
            report['seed_revalidation'] = {**revalidation_fixture(), 'derived_record_ids': derived}
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v8', report)
        values['report'] = {**report, '_record_id': identifier}
        if data.get('mode') == 'later_derived':
            self.ledger.record(session, 'cyber_dossier_seed_revalidation', 'late', {'model_calls': 0})
        return values


def patch_v8_constants(monkeypatch, values):
    for constant, name in [('EXPECTED_PLAN', 'plan'), ('EXPECTED_V2', 'v2'), ('EXPECTED_V3', 'v3'),
        ('EXPECTED_V4', 'v4'), ('EXPECTED_V5', 'v5'), ('EXPECTED_V5_REPORT', 'v5_report'), ('EXPECTED_V6', 'v6'),
        ('EXPECTED_V6_PASSED_REPORT', 'passed_v6_report'), ('EXPECTED_V6_STOPPED_REPORT', 'stopped_v6_report'),
        ('EXPECTED_V7', 'v7'), ('EXPECTED_V7_STOPPED_REPORT', 'stopped_v7_report'),
        ('EXPECTED_DIAGNOSTIC', 'diagnostic'), ('EXPECTED_DIAGNOSTIC_REPAIR', 'repair')]:
        monkeypatch.setattr(m, constant, values[name]['_record_id'])


@pytest.mark.parametrize('mode', ['current', 'old', 'base', 'missing_revalidation', 'later_derived'])
def test_v8_local_checks_are_separate_from_provider_counts_and_current_reports(tmp_path, monkeypatch, mode):
    owner = tmp_path / 'v8-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V8MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'mode': mode}, objective='Synthetic v8 local repair', actor='test:monitor')
        head = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
        provider_count = worker.ledger.db.execute("SELECT count(*) FROM records WHERE kind='cyber_dossier_response'").fetchone()[0]
    finally:
        worker.close()
    patch_v8_constants(monkeypatch, values)
    observer = m.Study(tmp_path / 'observer', config=Config(offline=True))
    try:
        result = observer.execute('status', {}, objective='Observe synthetic local revalidation', actor='test:monitor')
        assert result['latest_report_current'] is (mode == 'current')
        assert result['stored_responses'] == provider_count
        assert result['derived_seed_revalidations'] == (4 if mode == 'later_derived' else 3)
        assert result['technical_extension_version'] == 8
        assert result['reused_v6_gate']['pilot_gate']['passed'] is True
        assert result['registered_seed_capacity_census'] == values['v7']['seed_capacity_census']
        if mode == 'current':
            assert result['seed_revalidation']['valid'] == 3 and result['seed_revalidation']['model_calls'] == 0
            assert result['unresolved_holds'] == 4 and result['new_unresolved_holds'] == 0
            assert result['committed_nanousd'] == values['stopped_v7_report']['committed_nanousd']
            assert result['pilot_v6_gate']['passed'] is True
        else:
            assert result['seed_revalidation'] is None and result['pilot_gate'] is None
            assert result['final_coverage'] is None
        assert result['phase_eta_seconds'] is None and result['new_model_calls'] == 0
        assert observer.gateway.provider.calls == 0 and tuple(result['provenance']['head']) == head
    finally:
        observer.close()


@pytest.mark.parametrize('fault', ['negative', 'bool_count', 'count_sum', 'model_calls', 'mutated_rows',
                                  'duplicate_ids', 'too_many', 'stored_count', 'text_projection'])
def test_v8_local_revalidation_projection_rejects_changed_scope(fault):
    value, count = revalidation_fixture(), 3
    if fault == 'negative':
        value['valid'] = -1
    elif fault == 'bool_count':
        value['model_calls'] = False
    elif fault == 'count_sum':
        value['still_invalid'] = 1
    elif fault == 'model_calls':
        value['model_calls'] = 1
    elif fault == 'mutated_rows':
        value['original_rows_unchanged'] = False
    elif fault == 'duplicate_ids':
        value['derived_record_ids'][1] = value['derived_record_ids'][0]
    elif fault == 'too_many':
        value.update(attempted=4, valid=4, derived_record_ids=['a', 'b', 'c', 'd'])
        count = 4
    elif fault == 'stored_count':
        count = 2
    elif fault == 'text_projection':
        value['source_text'] = 'must not be exposed'
    with pytest.raises(AuditError, match='seed_revalidation'):
        m.validate_seed_revalidation(value, {'eligible_source_response_ids': ['1', '2', '3'], 'derived_revalidation_records': ['derived-1', 'derived-2', 'derived-3']}, count)


def test_v8_monitor_recognizes_only_run_and_does_not_project_a_previous_execution(tmp_path):
    item = process(tmp_path, action='pilot')
    item['command_line'] = item['command_line'].replace('run_dossiers.py', 'run_dossiers_v8.py')
    assert m.matching_processes([item], tmp_path) == []
    item['command_line'] = item['command_line'].replace(' pilot ', ' run ')
    matched = m.matching_processes([item], tmp_path)
    assert matched[0]['runner'] == 'run_dossiers_v8.py'
    progress = checkpoint()
    progress['pid'] = matched[0]['pid'] + 100
    result = m.phase_timing(progress, [], datetime.now(timezone.utc), matched, False, None)
    assert result['phase_eta_seconds'] is None and not result['checkpoint_matches_current_execution']


@pytest.mark.parametrize('fault', [None, 'parent_report', 'diagnostic_id', 'diagnostic_owner', 'source_ids',
    'source_error', 'normalization', 'capacity', 'pilot_baseline', 'derived_ids', 'request_changed',
    'census_incomplete', 'parent_census'])
def test_v8_extension_binds_exact_three_diagnosed_rows_and_unchanged_technical_scope(fault):
    v7 = {'_record_id': m.EXPECTED_V7, 'implementation': code_manifest('_v7'),
        'ancestor_execution_amendments': {'v6': m.EXPECTED_V6},
        'seed_capacity_census': capacity_fixture(), 'seed_packet_plan_artifact': 'packets',
        'seed_proposals_sha256': 'proposals', 'passed_pilot_report': m.EXPECTED_V6_PASSED_REPORT,
        'passed_gate_record': 'same-v6-gate', 'minimum_incoming_articles': 6,
        'v6_pilot_budget_baseline': {'legacy_response_keys': ['old'], 'legacy_unresolved_attempts': ['hold']},
        **m.V6_ALLOCATION}
    report = {'_record_id': m.EXPECTED_V7_STOPPED_REPORT, 'plan': 'plan',
        'execution_amendment': m.EXPECTED_V7, 'technical_extension_version': 7,
        'seed_capacity': {'frozen_census': deepcopy(v7['seed_capacity_census']), 'execution_summary': None}}
    v8 = deepcopy(v8_extension(v7, report))
    if fault == 'parent_report':
        v8['parent_report'] = 'replacement'
    elif fault == 'diagnostic_id':
        v8['diagnostic']['record_id'] = 'later-diagnosis'
    elif fault == 'diagnostic_owner':
        v8['diagnostic']['owner'] = str(m.EXPECTED_V7_DIAGNOSTIC_OWNER.parent / 'other')
    elif fault == 'source_ids':
        v8['eligible_source_response_ids'][0] = 'different-old-error'
    elif fault == 'source_error':
        v8['source_validation_error'] = 'refusal'
    elif fault == 'normalization':
        v8['normalization_version'] = 'relaxed-validation'
    elif fault == 'capacity':
        v8['seed_capacity_census']['token_limit'] += 1
    elif fault == 'pilot_baseline':
        v8['v6_pilot_budget_baseline']['legacy_response_keys'] = []
    elif fault == 'derived_ids':
        v8['derived_revalidation_records'][1] = v8['derived_revalidation_records'][0]
    elif fault == 'request_changed':
        v8['seed_order_integrity']['request_changes'] = 1
    elif fault == 'census_incomplete':
        v8['seed_order_integrity']['checked_packets'] -= 1
    elif fault == 'parent_census':
        report['seed_capacity']['frozen_census']['deferred_unjudged_packets'] = 0
    if fault is None:
        m.validate_v8_extension(v8, v7, report, {'_record_id': 'plan'})
    else:
        with pytest.raises(AuditError):
            m.validate_v8_extension(v8, v7, report, {'_record_id': 'plan'})


# V9 adds operational metadata; synthetic owner histories never contain articles.
def operational_fixture(**updates):
    value = {"outcomes": 3, "provider_responses": 2, "unreturned_intents": 1,
        "mechanically_parsed": 1, "invalid": 0, "held_or_transport_unknown": 2,
        "window_size": 3, "window_failures": 2, "window_transport_unknown": 2,
        "consecutive_failures": 2, "guard_reason": None, "policy_sha256": m.digest(m.OPERATIONAL_POLICY),
        "scope": m.OPERATIONAL_SCOPE, "legacy_guard_continuations": 0, "baseline_unresolved_holds": 19,
        "operational_status": "ready", "cooldown_until": None}
    return {**value, **updates}


def v9_extension(v8, report):
    return {**{key: deepcopy(value) for key, value in v8.items() if not key.startswith('_')},
        '_record_id': 'v9', 'parent_execution_amendment': v8['_record_id'],
        'parent_implementation': v8['implementation'],
        'implementation': {**v8['implementation'], **code_manifest('_v9')},
        'ancestor_execution_amendments': {**v8['ancestor_execution_amendments'], 'v8': v8['_record_id']},
        'parent_report': report['_record_id'],
        'technical_diagnostic': {'owner': str(m.EXPECTED_V8_DIAGNOSTIC_OWNER), 'record_id': m.EXPECTED_V8_DIAGNOSTIC},
        'operational_policy': deepcopy(m.OPERATIONAL_POLICY),
        'transport_observability': 'dossier-transport-fixed-stage-codes-v1',
        'legacy_unresolved_attempts': [f'held-{i}' for i in range(19)],
        'legacy_budget': {key: report[key] for key in
            ('settled_nanousd', 'held_nanousd', 'committed_nanousd', 'unresolved_holds')}}


def category_fixture(totals):
    amounts = ('settled_nanousd', 'held_nanousd', 'committed_nanousd', 'unresolved_holds')
    main = {key: totals[key] for key in amounts}
    main.update(cap_nanousd=m.V5_ALLOCATION['main_cap_nanousd'],
                remaining_nanousd=m.V5_ALLOCATION['main_cap_nanousd'] - main['committed_nanousd'])
    audit = {key: 0 for key in amounts}
    audit.update(cap_nanousd=m.V5_ALLOCATION['audit_cap_nanousd'],
                 remaining_nanousd=m.V5_ALLOCATION['audit_cap_nanousd'])
    return {'main': main, 'audit': audit}


class V9MetadataOwner(V8MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        previous = {key: value for key, value in values['report'].items() if not key.startswith('_')}
        previous.update(unresolved_holds=19, new_unresolved_holds=15,
                        held_nanousd=previous['held_nanousd'] + 15_000,
                        new_held_nanousd=15_000,
                        committed_nanousd=previous['committed_nanousd'] + 15_000, at=utc())
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-pre-v9', previous)
        values['stopped_v8_report'] = {**previous, '_record_id': identifier}
        payload = v9_extension(values['v8'], values['stopped_v8_report'])
        payload = {key: value for key, value in payload.items() if not key.startswith('_')}
        payload['legacy_unresolved_attempts'] = values['v8']['legacy_unresolved_attempts'] + [f'new-{i}' for i in range(15)]
        identifier = self.ledger.record(session, 'cyber_dossier_execution_amendment_v9', 'synthetic', payload)
        values['v9'] = {**payload, '_record_id': identifier}
        if data.get('mode') == 'old':
            return values
        for i in range(2):
            self.ledger.record(session, 'cyber_dossier_response', f'new-v9-{i}',
                               {'phase': 'phase2_source_card_quality', 'execution_amendment': identifier})
        report = {**previous, 'at': utc(), 'execution_amendment': identifier,
                  'stored_responses': previous['stored_responses'] + 2,
                  'unresolved_holds': 21, 'legacy_unresolved_holds': 19, 'new_unresolved_holds': 2,
                  'legacy_held_nanousd': previous['held_nanousd'], 'new_held_nanousd': 2000,
                  'held_nanousd': previous['held_nanousd'] + 2000,
                  'committed_nanousd': previous['committed_nanousd'] + 2000}
        if data.get('mode') != 'base':
            report.update(technical_extension_version=9)
        if data.get('mode') != 'missing_operational':
            report.update(operational_continuation=operational_fixture(), category_budget=category_fixture(report))
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v9', report)
        values['report'] = {**report, '_record_id': identifier}
        return values


@pytest.mark.parametrize('mode', ['current', 'base', 'old', 'missing_operational'])
def test_v9_audited_projection_preserves_all_holds_and_excludes_orphans_from_responses(tmp_path, monkeypatch, mode):
    owner = tmp_path / 'v9-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V9MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'mode': mode}, objective='Synthetic operational extension', actor='test:monitor')
        before = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
        stored = worker.ledger.db.execute("SELECT count(*) FROM records WHERE kind='cyber_dossier_response'").fetchone()[0]
    finally:
        worker.close()
    patch_v8_constants(monkeypatch, values)
    monkeypatch.setattr(m, 'EXPECTED_V8', values['v8']['_record_id'])
    monkeypatch.setattr(m, 'EXPECTED_V8_STOPPED_REPORT', values['stopped_v8_report']['_record_id'])
    observer = m.Study(tmp_path / 'observer', config=Config(offline=True))
    try:
        result = observer.execute('status', {}, objective='Observe synthetic operational scope', actor='test:monitor')
        assert result['latest_report_current'] is (mode == 'current')
        assert result['stored_responses'] == stored
        assert result['derived_seed_revalidations'] == 3
        assert result['technical_extension_version'] == 9
        assert result['v9_baseline_unresolved_holds'] == 19
        assert result['reused_v6_gate']['pilot_gate']['passed'] is True
        if mode == 'current':
            assert result['operational_continuation']['outcomes'] == 3
            assert result['operational_continuation']['provider_responses'] == 2
            assert result['unresolved_holds'] == 21
            assert result['legacy_unresolved_holds'] == 19 and result['new_unresolved_holds'] == 2
            assert result['seed_revalidation']['valid'] == 3
            assert result['category_budget']['main']['committed_nanousd'] == result['committed_nanousd']
            assert result['operational_observation_basis'] == 'current_audited_stopped_report'
        else:
            assert result['operational_continuation'] is None and result['pilot_gate'] is None
            assert result['category_budget'] is None
        assert result['phase_eta_seconds'] is None
        assert tuple(result['provenance']['head']) == before
        assert observer.gateway.provider.calls == 0 and result['worker_mutations'] == 0
    finally:
        observer.close()


@pytest.mark.parametrize('fault', [None, 'policy', 'parent', 'diagnostic', 'ancestry', 'old_holds',
    'cost', 'capacity', 'revalidation', 'normalization', 'transport', 'parent_revalidation'])
def test_v9_extension_rejects_changed_scope_or_liability_baseline(fault):
    v8 = {'_record_id': m.EXPECTED_V8, 'implementation': code_manifest('_v8'),
        'ancestor_execution_amendments': {'v7': m.EXPECTED_V7},
        'seed_capacity_census': capacity_fixture(), 'seed_packet_plan_artifact': 'packets',
        'seed_order_integrity': {'checked_packets': 8, 'map_order_restored_packets': 3,
            'canonical_packet_changes': 0, 'request_changes': 0, 'deferred_packets': 2, 'model_calls': 0},
        'derived_revalidation_records': revalidation_fixture()['derived_record_ids'],
        'eligible_source_response_ids': list(m.EXPECTED_REVALIDATION_RESPONSES),
        'normalization_version': m.EXPECTED_NORMALIZATION,
        'minimum_incoming_articles': 6, **m.V6_ALLOCATION}
    report = {'_record_id': m.EXPECTED_V8_STOPPED_REPORT, 'plan': 'plan',
        'execution_amendment': m.EXPECTED_V8, 'technical_extension_version': 8,
        'seed_order_integrity': deepcopy(v8['seed_order_integrity']),
        'seed_capacity': {'frozen_census': deepcopy(v8['seed_capacity_census'])},
        'seed_revalidation': revalidation_fixture(),
        'settled_nanousd': 100, 'held_nanousd': 190, 'committed_nanousd': 290, 'unresolved_holds': 19}
    v9 = v9_extension(v8, report)
    if fault == 'policy':
        v9['operational_policy']['window_failure_limit'] = 17
    elif fault == 'parent':
        v9['parent_report'] = 'replacement'
    elif fault == 'diagnostic':
        v9['technical_diagnostic']['record_id'] = 'replacement'
    elif fault == 'ancestry':
        v9['ancestor_execution_amendments'].pop('v8')
    elif fault == 'old_holds':
        v9['legacy_budget']['unresolved_holds'] = 18
    elif fault == 'cost':
        v9['legacy_budget']['held_nanousd'] -= 1
    elif fault == 'capacity':
        v9['seed_capacity_census']['token_limit'] += 1
    elif fault == 'revalidation':
        v9['derived_revalidation_records'].pop()
    elif fault == 'normalization':
        v9['normalization_version'] = 'new-semantic-parser'
    elif fault == 'transport':
        v9['transport_observability'] = 'unsafe-raw-errors'
    elif fault == 'parent_revalidation':
        report['seed_revalidation']['model_calls'] = 1
    if fault is None:
        m.validate_v9_extension(v9, v8, report, {'_record_id': 'plan'})
    else:
        with pytest.raises(AuditError):
            m.validate_v9_extension(v9, v8, report, {'_record_id': 'plan'})


@pytest.mark.parametrize('fault', [None, 'boolean', 'sum', 'provider_count', 'baseline', 'scope', 'raw_text',
    'window', 'reason', 'missing_guard', 'category_overlap', 'cooldown_missing_time', 'bad_status'])
def test_operational_projection_is_allowlisted_consistent_and_not_semantic(fault):
    value = operational_fixture()
    amendment = {'operational_policy': m.OPERATIONAL_POLICY, 'legacy_unresolved_attempts': list(range(19))}
    if fault == 'boolean':
        value['invalid'] = False
    elif fault == 'sum':
        value['outcomes'] += 1
    elif fault == 'provider_count':
        value['provider_responses'] = 100
    elif fault == 'baseline':
        value['baseline_unresolved_holds'] = 4
    elif fault == 'scope':
        value['scope'] = 'since process restart'
    elif fault == 'raw_text':
        value['error_text'] = 'must not expose'
    elif fault == 'window':
        value['window_size'] = 32
    elif fault == 'reason':
        value['guard_reason'] = 'arbitrary message'
    elif fault == 'missing_guard':
        value.update(outcomes=8, provider_responses=7, mechanically_parsed=0,
                     held_or_transport_unknown=8, window_size=8, window_failures=8,
                     window_transport_unknown=8, consecutive_failures=8)
    elif fault == 'category_overlap':
        value['invalid'] = 1
    elif fault == 'cooldown_missing_time':
        value['operational_status'] = 'cooldown'
    elif fault == 'bad_status':
        value['operational_status'] = 'running-despite-fatal'
    if fault is None:
        assert m.validate_operational_continuation(value, amendment, 2000) == value
    else:
        with pytest.raises(AuditError):
            m.validate_operational_continuation(value, amendment, 2000)


@pytest.mark.parametrize('status', ['cooldown', 'stopped'])
def test_v9_cooldown_and_guard_suppress_eta_despite_fresh_advancing_queue(tmp_path, status):
    item = process(tmp_path)
    item['command_line'] = item['command_line'].replace('run_dossiers.py', 'run_dossiers_v9.py')
    processes = m.matching_processes([item], tmp_path)
    current = checkpoint()
    current['operational_continuation'] = operational_fixture(operational_status=status,
        guard_reason='fatal_local_binding_or_integrity' if status == 'stopped' else None,
        cooldown_until=(NOW + timedelta(seconds=30)).isoformat())
    previous = [{'checkpoint_matches_current_execution': True,
        'execution_identity': {'pid': 11, 'created_at': processes[0]['created_at']},
        'progress': checkpoint(NOW - timedelta(minutes=30), completed=100)}]
    result = m.phase_timing(current, previous, NOW, processes, False, None)
    assert result['phase_eta_seconds'] is None and result['phase_tasks_per_minute'] is None
    assert result['phase_eta_blocker'] == ('operational_cooldown' if status == 'cooldown' else 'operational_guard_stopped')
    item['command_line'] = item['command_line'].replace(' run ', ' pilot ')
    assert m.matching_processes([item], tmp_path) == []


@pytest.mark.parametrize('fault', ['sum', 'cap', 'remaining', 'bool', 'text'])
def test_v9_category_budget_cannot_hide_or_double_count_liabilities(fault):
    totals = {'settled_nanousd': 10, 'held_nanousd': 19, 'committed_nanousd': 29, 'unresolved_holds': 19}
    value = category_fixture(totals)
    m.validate_category_budget(value, totals)
    if fault == 'sum':
        value['audit']['unresolved_holds'] = 1
    elif fault == 'cap':
        value['audit']['cap_nanousd'] += 1
    elif fault == 'remaining':
        value['main']['remaining_nanousd'] += 1
    elif fault == 'bool':
        value['main']['held_nanousd'] = True
    else:
        value['main']['description'] = 'private source text'
    with pytest.raises(AuditError):
        m.validate_category_budget(value, totals)


# V10 is prospective and tested only against synthetic protected owners.
def v10_metadata(extension):
    return {'original_deadline': extension['original_deadline'], 'effective_admission_deadline': None,
        'deadline_policy': deepcopy(m.DEADLINE_POLICY), 'deadline_authorization_policy': extension['versions']['policy'],
        'operational_origin_amendment': extension['operational_origin_amendment'],
        'health_response_amendments': [*extension['health_ancestor_amendments'], extension['_record_id']]}


class V10MetadataOwner(V9MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        old, previous = values['v9'], values['report']
        values['stopped_v9_report'] = previous
        private_text = json.dumps({'instruction': 'synthetic-private-authorization-do-not-project',
            'source_reference': 'synthetic-user-message', 'source_timestamp': None}).encode()
        artifact = self.ledger.artifacts.put_bytes(private_text)
        authorization = {'artifact': artifact, 'sha256': hashlib.sha256(private_text).hexdigest(),
                         'source_reference': 'synthetic-user-message', 'source_timestamp': None, 'registered_at': utc()}
        policy = self._version(session, context, {'kind': 'policy', 'key': 'synthetic-v10', 'content': {
            'deadline_policy': m.DEADLINE_POLICY, 'deadline_evidence': authorization,
            'parent_execution_amendment': old['_record_id'], 'original_deadline': old['original_deadline'],
            'cap_nanousd': m.CAP_NANOUSD, 'new_models_or_questions_authorized': False}})['id']
        extension = {**{key: value for key, value in old.items() if not key.startswith('_')},
            'parent_execution_amendment': old['_record_id'], 'parent_report': previous['_record_id'],
            'parent_implementation': old['implementation'],
            'implementation': {**old['implementation'], **code_manifest('_v10')},
            'versions': {'policy': policy}, 'deadline_authorization': authorization,
            'ancestor_execution_amendments': {**old['ancestor_execution_amendments'], 'v9': old['_record_id']},
            'deadline_policy': deepcopy(m.DEADLINE_POLICY), 'effective_admission_deadline': None,
            'operational_origin_amendment': old['_record_id'], 'health_ancestor_amendments': [old['_record_id']],
            'operational_health_baseline_unresolved_attempts': old['legacy_unresolved_attempts'],
            'legacy_unresolved_attempts': old['legacy_unresolved_attempts'] + ['after-v9-a', 'after-v9-b'],
            'legacy_budget': {key: previous[key] for key in
                ('settled_nanousd', 'held_nanousd', 'committed_nanousd', 'unresolved_holds')}}
        identifier = self.ledger.record(session, 'cyber_dossier_execution_amendment_v10', 'synthetic', extension)
        values['v10'] = {**extension, '_record_id': identifier}
        if data.get('mode') == 'old':
            return values
        self.ledger.record(session, 'cyber_dossier_response', 'new-v10',
            {'phase': '4_card_assignment_full_v6_seed', 'execution_amendment': identifier})
        report = {**{key: value for key, value in previous.items() if not key.startswith('_')},
            'execution_amendment': identifier, 'at': utc(), 'stored_responses': previous['stored_responses'] + 1,
            'legacy_unresolved_holds': 21, 'new_unresolved_holds': 0,
            'legacy_held_nanousd': previous['held_nanousd'], 'new_held_nanousd': 0}
        report['operational_continuation'] = operational_fixture(outcomes=4, provider_responses=3,
            mechanically_parsed=2, window_size=4, consecutive_failures=0, scope=m.V10_HEALTH_SCOPE)
        if data.get('mode') != 'base':
            report.update(technical_extension_version=10)
        if data.get('mode') != 'missing_metadata':
            report.update(v10_metadata(values['v10']))
        report['category_budget'] = category_fixture(report)
        identity = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v10', report)
        values['report'] = {**report, '_record_id': identity}
        return values


def patch_v10_constants(monkeypatch, values):
    patch_v8_constants(monkeypatch, values)
    monkeypatch.setattr(m, 'EXPECTED_V8', values['v8']['_record_id'])
    monkeypatch.setattr(m, 'EXPECTED_V8_STOPPED_REPORT', values['stopped_v8_report']['_record_id'])
    monkeypatch.setattr(m, 'EXPECTED_V9', values['v9']['_record_id'])


@pytest.mark.parametrize('mode', ['current', 'old', 'base', 'missing_metadata'])
def test_v10_audited_policy_and_health_preserve_two_different_hold_baselines(tmp_path, monkeypatch, mode):
    owner = tmp_path / 'v10-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V10MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'mode': mode}, objective='Synthetic deadline policy', actor='test:monitor')
        before = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
        provider_count = worker.ledger.db.execute("SELECT count(*) FROM records WHERE kind='cyber_dossier_response'").fetchone()[0]
    finally:
        worker.close()
    patch_v10_constants(monkeypatch, values)
    observer = m.Study(tmp_path / 'observer', config=Config(offline=True))
    try:
        if mode == 'missing_metadata':
            with pytest.raises(AuditError, match='v10_snapshot_policy_or_health_binding'):
                observer.execute('status', {}, objective='Reject missing continuation identity', actor='test:monitor')
            return
        result = observer.execute('status', {}, objective='Observe synthetic continuation', actor='test:monitor')
        assert result['latest_report_current'] is (mode == 'current')
        assert result['technical_extension_version'] == 10
        assert result['v9_baseline_unresolved_holds'] == 19
        assert result['v10_admission_baseline_unresolved_holds'] == 21
        assert result['original_admission_deadline'] == values['v9']['original_deadline']
        assert result['effective_admission_deadline'] is None and result['deadline'] is None
        assert result['remaining_runtime_seconds'] is None and result['deadline_expired'] is False
        assert result['stored_responses'] == provider_count and result['derived_seed_revalidations'] == 3
        assert result['health_response_amendments'] == [values['v9']['_record_id'], values['v10']['_record_id']]
        if mode == 'current':
            assert result['operational_continuation']['outcomes'] == 4
            assert result['operational_continuation']['baseline_unresolved_holds'] == 19
            assert result['legacy_unresolved_holds'] == 21 and result['new_unresolved_holds'] == 0
        else:
            assert result['operational_continuation'] is None and result['final_coverage'] is None
        assert 'synthetic-private-authorization-do-not-project' not in json.dumps(result)
        assert tuple(result['provenance']['head']) == before
        assert result['new_model_calls'] == 0 and observer.gateway.provider.calls == 0
    finally:
        observer.close()


@pytest.mark.parametrize('runner', ['run_dossiers_v9.py', 'run_dossiers_v10.py', None])
def test_original_deadline_is_historical_only_for_registered_v10_state(tmp_path, runner):
    original = (NOW - timedelta(hours=1)).isoformat()
    item = process(tmp_path)
    item['command_line'] = item['command_line'].replace('run_dossiers.py', runner or 'run_dossiers_v10.py')
    processes = m.matching_processes([item], tmp_path) if runner else []
    context = m.effective_deadline_context(original, {'deadline_policy': m.DEADLINE_POLICY}, processes, NOW)
    assert context['original_admission_deadline'] == original and context['original_deadline_elapsed'] is True
    assert context['v10_deadline_policy_applies'] is (runner != 'run_dossiers_v9.py')
    progress = checkpoint()
    prior = [{'checkpoint_matches_current_execution': True,
        'execution_identity': {'pid': 11, 'created_at': item['created_at']},
        'progress': checkpoint(NOW - timedelta(minutes=30), completed=100)}]
    timing = m.phase_timing(progress, prior, NOW, processes, False, context['effective_admission_deadline'])
    if runner == 'run_dossiers_v9.py':
        assert timing['deadline_expired'] is True and timing['phase_eta_seconds'] is None
    elif runner == 'run_dossiers_v10.py':
        assert timing['deadline_expired'] is False and timing['remaining_runtime_seconds'] is None
        assert timing['phase_eta_seconds'] == 14400
        assert timing['phase_finish_after_deadline'] is None
    else:
        assert timing['state'] == 'stopped' and timing['phase_eta_seconds'] is None


def test_v10_without_registration_and_v10_pilot_are_never_assumed_authorized(tmp_path):
    row = process(tmp_path)
    row['command_line'] = row['command_line'].replace('run_dossiers.py', 'run_dossiers_v10.py')
    processes = m.matching_processes([row], tmp_path)
    assert processes[0]['runner'] == 'run_dossiers_v10.py'
    context = m.effective_deadline_context(NOW.isoformat(), None, processes, NOW)
    assert context['effective_admission_deadline'] == NOW.isoformat()
    row['command_line'] = row['command_line'].replace(' run ', ' pilot ')
    assert m.matching_processes([row], tmp_path) == []


@pytest.mark.parametrize('fault', ['original', 'date_cutoff', 'policy', 'authorization', 'origin', 'cohort', 'checkpoint_cutoff'])
def test_v10_checkpoint_cannot_reset_policy_or_carried_health(fault):
    amendment = {'_record_id': 'v10', 'original_deadline': NOW.isoformat(), 'versions': {'policy': 'policy-id'},
        'operational_origin_amendment': 'v9', 'health_ancestor_amendments': ['v9']}
    value = {**v10_metadata(amendment), 'deadline': None}
    m.validate_v10_snapshot(value, amendment, checkpoint=True)
    if fault == 'original':
        value['original_deadline'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'date_cutoff':
        value['effective_admission_deadline'] = NOW.isoformat()
    elif fault == 'policy':
        value['deadline_policy']['budget_reset'] = True
    elif fault == 'authorization':
        value['deadline_authorization_policy'] = 'another-policy'
    elif fault == 'origin':
        value['operational_origin_amendment'] = 'v10'
    elif fault == 'cohort':
        value['health_response_amendments'] = ['v10']
    else:
        value['deadline'] = NOW.isoformat()
    with pytest.raises(AuditError, match='v10_snapshot'):
        m.validate_v10_snapshot(value, amendment, checkpoint=True)


def test_v10_health_keeps_original_19_holds_separate_from_new_admission_baseline():
    amendment = {'_record_id': 'v10', 'operational_policy': m.OPERATIONAL_POLICY,
        'legacy_unresolved_attempts': list(range(27)), 'health_ancestor_amendments': ['v9'],
        'operational_health_baseline_unresolved_attempts': list(range(19))}
    value = operational_fixture(scope=m.V10_HEALTH_SCOPE)
    m.validate_operational_continuation(value, amendment, 100)
    for altered in (operational_fixture(), {**value, 'baseline_unresolved_holds': 27}):
        with pytest.raises(AuditError, match='operational_projection'):
            m.validate_operational_continuation(altered, amendment, 100)


@pytest.mark.parametrize('fault', [None, 'parent_report', 'parent_version', 'origin', 'health_reset',
    'deadline_policy', 'new_cutoff', 'budget', 'hold_baseline', 'capacity', 'derived', 'evidence_hash', 'missing_policy'])
def test_v10_deadline_amendment_cannot_change_inherited_scope_or_reset_liabilities(fault):
    original_holds = [f'old-{i}' for i in range(19)]
    old = {'_record_id': m.EXPECTED_V9, 'original_deadline': NOW.isoformat(),
        'implementation': code_manifest('_v9'), 'ancestor_execution_amendments': {'v8': m.EXPECTED_V8},
        'seed_capacity_census': capacity_fixture(), 'seed_order_integrity': {'checked_packets': 8},
        'derived_revalidation_records': revalidation_fixture()['derived_record_ids'],
        'eligible_source_response_ids': list(m.EXPECTED_REVALIDATION_RESPONSES),
        'operational_policy': deepcopy(m.OPERATIONAL_POLICY),
        'legacy_unresolved_attempts': original_holds,
        'legacy_budget': {'settled_nanousd': 100, 'held_nanousd': 190, 'committed_nanousd': 290, 'unresolved_holds': 19},
        'minimum_incoming_articles': 6, **m.V6_ALLOCATION}
    report = {'_record_id': 'dynamic-parent', 'plan': 'plan', 'execution_amendment': old['_record_id'],
        'technical_extension_version': 9, 'seed_order_integrity': old['seed_order_integrity'],
        'seed_capacity': {'frozen_census': old['seed_capacity_census']},
        'seed_revalidation': revalidation_fixture(), 'stored_responses': 100,
        'settled_nanousd': 110, 'held_nanousd': 210, 'committed_nanousd': 320, 'unresolved_holds': 21,
        'legacy_unresolved_holds': 19, 'new_unresolved_holds': 2, 'legacy_held_nanousd': 190, 'new_held_nanousd': 20,
        'operational_continuation': operational_fixture()}
    report['category_budget'] = category_fixture(report)
    extension = {**deepcopy(old), '_record_id': 'v10', 'parent_report': report['_record_id'],
        'ancestor_execution_amendments': {**old['ancestor_execution_amendments'], 'v9': old['_record_id']},
        'deadline_policy': deepcopy(m.DEADLINE_POLICY), 'effective_admission_deadline': None,
        'operational_origin_amendment': old['_record_id'], 'health_ancestor_amendments': [old['_record_id']],
        'operational_health_baseline_unresolved_attempts': list(original_holds),
        'legacy_unresolved_attempts': original_holds + ['new-1', 'new-2'],
        'legacy_budget': {key: report[key] for key in old['legacy_budget']}, 'versions': {'policy': 'registered-policy'},
        'deadline_authorization': {'artifact': 'a' * 64, 'sha256': 'a' * 64, 'source_reference': 'user-message',
                                   'source_timestamp': None, 'registered_at': NOW.isoformat()}}
    if fault == 'parent_report':
        extension['parent_report'] = 'replacement'
    elif fault == 'parent_version':
        report['technical_extension_version'] = 8
    elif fault == 'origin':
        extension['operational_origin_amendment'] = 'v10'
    elif fault == 'health_reset':
        extension['operational_health_baseline_unresolved_attempts'] = extension['legacy_unresolved_attempts']
    elif fault == 'deadline_policy':
        extension['deadline_policy']['budget_reset'] = True
    elif fault == 'new_cutoff':
        extension['effective_admission_deadline'] = '2099-01-01T00:00:00Z'
    elif fault == 'budget':
        extension['main_cap_nanousd'] += 1
    elif fault == 'hold_baseline':
        extension['legacy_budget']['held_nanousd'] -= 1
    elif fault == 'capacity':
        extension['seed_capacity_census']['token_limit'] += 1
    elif fault == 'derived':
        extension['derived_revalidation_records'].pop()
    elif fault == 'evidence_hash':
        extension['deadline_authorization']['sha256'] = 'b' * 64
    elif fault == 'missing_policy':
        extension['versions'] = {}
    if fault is None:
        m.validate_v10_extension(extension, old, report, {'_record_id': 'plan'})
    else:
        with pytest.raises(AuditError):
            m.validate_v10_extension(extension, old, report, {'_record_id': 'plan'})


def budget_policy(caps=None):
    return {'version': 'cumulative-user-budget-amendment-v1',
        'historical_caps_nanousd': deepcopy(m.HISTORICAL_CAPS),
        'effective_caps_nanousd': caps or {'total': 75_000_000_000, 'main': 45_000_000_000, 'audit': 30_000_000_000},
        'cumulative': True, 'reset_costs_or_holds': False, 'automatic_reallocation': False,
        'new_models_or_questions_authorized': False}


def v11_metadata(extension):
    policy = extension['budget_policy']
    return {**v10_metadata(extension), 'budget_policy': deepcopy(policy),
        'historical_caps_nanousd': policy['historical_caps_nanousd'],
        'effective_caps_nanousd': policy['effective_caps_nanousd'],
        'cap_nanousd': policy['effective_caps_nanousd']['total'],
        'budget_authorization_policy': extension['versions']['policy']}


class V11MetadataOwner(V9MetadataOwner):
    @audited_handler
    def _status(self, session, context, data):
        values = super()._status(session, context, {})
        old, original = values['v9'], values['report']
        for i in range(97):
            self.ledger.record(session, 'cyber_dossier_response', f'continued-v9-{i}',
                {'phase': 'assignment', 'execution_amendment': old['_record_id']})
        previous = {k: v for k, v in original.items() if not k.startswith('_')}
        previous.update(at=utc(), stored_responses=original['stored_responses'] + 97,
            unresolved_holds=48, new_unresolved_holds=29,
            held_nanousd=original['held_nanousd'] + 27000,
            new_held_nanousd=original['new_held_nanousd'] + 27000,
            committed_nanousd=original['committed_nanousd'] + 27000)
        previous['operational_continuation'] = operational_fixture(outcomes=100, provider_responses=99,
            mechanically_parsed=71, held_or_transport_unknown=29, window_size=32,
            window_failures=0, window_transport_unknown=0, consecutive_failures=0)
        previous['category_budget'] = category_fixture(previous)
        previous['_record_id'] = self.ledger.record(session, 'cyber_dossier_report', 'stopped-v9', previous)
        values['stopped_v9_report'] = previous
        policy = budget_policy(data.get('caps'))
        caps = policy['effective_caps_nanousd']
        evidence = {}
        for kind in ('deadline', 'budget'):
            raw = {'instruction': 'synthetic-private-authority-never-project',
                   'source_reference': 'synthetic-' + kind, 'source_timestamp': None}
            if kind == 'budget':
                raw['caps_nanousd'] = caps
            raw_bytes = json.dumps(raw).encode()
            ref = self.ledger.artifacts.put_bytes(raw_bytes)
            evidence[kind] = {'artifact': ref, 'sha256': ref, 'registered_at': utc(),
                             **{k: v for k, v in raw.items() if k != 'instruction'}}
        content = {'deadline_policy': m.DEADLINE_POLICY, 'deadline_evidence': evidence['deadline'],
            'budget_policy': policy, 'budget_evidence': evidence['budget'],
            'parent_execution_amendment': old['_record_id'], 'original_deadline': old['original_deadline'],
            'cap_nanousd': caps['total'], 'new_models_or_questions_authorized': False}
        if data.get('mode') == 'bad_private_evidence':
            # Metadata is internally consistent, but it disagrees with the actual retained bytes.
            evidence['budget']['source_reference'] = 'invented-source-reference'
        if data.get('mode') == 'bad_policy':
            content['budget_evidence'] = {**evidence['budget'], 'caps_nanousd': m.HISTORICAL_CAPS}
        policy_id = self._version(session, context, {'kind': 'policy', 'key': 'synthetic-v11', 'content': content})['id']
        extension = {**{k: v for k, v in old.items() if not k.startswith('_')},
            'method': m.V11_METHOD, 'parent_execution_amendment': old['_record_id'],
            'parent_implementation': old['implementation'], 'parent_report': previous['_record_id'],
            'implementation': {**old['implementation'], **code_manifest('_v11')},
            'ancestor_execution_amendments': {**old['ancestor_execution_amendments'], 'v9': old['_record_id']},
            'deadline_policy': deepcopy(m.DEADLINE_POLICY), 'effective_admission_deadline': None,
            'deadline_authorization': evidence['deadline'], 'budget_authorization': evidence['budget'],
            'budget_policy': policy, 'versions': {'policy': policy_id}, 'cap_nanousd': caps['total'],
            'main_cap_nanousd': caps['main'], 'audit_cap_nanousd': caps['audit'],
            'operational_origin_amendment': old['_record_id'], 'health_ancestor_amendments': [old['_record_id']],
            'operational_health_baseline_unresolved_attempts': old['legacy_unresolved_attempts'],
            'legacy_unresolved_attempts': old['legacy_unresolved_attempts'] + [f'after-v9-{i}' for i in range(29)],
            'legacy_budget': {k: previous[k] for k in ('settled_nanousd', 'held_nanousd', 'committed_nanousd', 'unresolved_holds')},
            'legacy_category_budget': deepcopy(previous['category_budget'])}
        identity = self.ledger.record(session, 'cyber_dossier_execution_amendment_v11', 'synthetic', extension)
        values['v11'] = {**extension, '_record_id': identity}
        if data.get('mode') == 'old':
            values['report'] = previous
            return values
        self.ledger.record(session, 'cyber_dossier_response', 'continued-v11',
            {'phase': 'assignment', 'execution_amendment': identity})
        report = {**{k: v for k, v in previous.items() if not k.startswith('_')},
            'execution_amendment': identity, 'technical_extension_version': 11, 'at': utc(),
            'stored_responses': previous['stored_responses'] + 1, 'legacy_unresolved_holds': 48,
            'new_unresolved_holds': 0, 'legacy_held_nanousd': previous['held_nanousd'], 'new_held_nanousd': 0,
            **v11_metadata(values['v11'])}
        report['operational_continuation'] = {**previous['operational_continuation'], 'scope': m.V11_HEALTH_SCOPE,
            'outcomes': 101, 'provider_responses': 100, 'mechanically_parsed': 72}
        report['category_budget'] = deepcopy(previous['category_budget'])
        for category in ('main', 'audit'):
            report['category_budget'][category]['cap_nanousd'] = caps[category]
            report['category_budget'][category]['remaining_nanousd'] = caps[category] - report['category_budget'][category]['committed_nanousd']
        if data.get('mode') == 'base':
            report['technical_extension_version'] = 9
        elif data.get('mode') == 'missing_metadata':
            report.pop('budget_authorization_policy')
        identifier = self.ledger.record(session, 'cyber_dossier_report', 'synthetic-v11', report)
        values['report'] = {**report, '_record_id': identifier}
        return values


@pytest.mark.parametrize('mode', ['current', 'old', 'base', 'missing_metadata', 'bad_policy', 'bad_private_evidence'])
def test_v11_actual_observer_binds_numeric_authority_direct_v9_and_all_48_holds(tmp_path, monkeypatch, mode):
    owner = tmp_path / 'v11-active'
    monkeypatch.setattr(m, 'ACTIVE_OWNER', owner)
    monkeypatch.setattr(m, 'workers', lambda _: [])
    worker = V11MetadataOwner(owner, config=Config(offline=True))
    try:
        values = worker.execute('status', {'mode': mode}, objective='Synthetic cumulative authority', actor='test:monitor')
        before = tuple(worker.ledger.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone())
    finally:
        worker.close()
    patch_v10_constants(monkeypatch, values)
    observer = m.Study(tmp_path / 'observer', config=Config(offline=True))
    try:
        if mode in {'missing_metadata', 'bad_policy', 'bad_private_evidence'}:
            with pytest.raises(AuditError, match='v11_(snapshot_budget_binding|registered_policy_changed|private_evidence_changed)'):
                observer.execute('status', {}, objective='Reject altered authority', actor='test:monitor')
            return
        result = observer.execute('status', {}, objective='Observe synthetic v11', actor='test:monitor')
        assert result['latest_report_current'] is (mode == 'current')
        assert result['technical_extension_version'] == 11
        assert result['provenance']['v10_execution_amendment'] is None
        assert result['v9_baseline_unresolved_holds'] == 19
        assert result['v11_admission_baseline_unresolved_holds'] == 48
        assert result['budget_usd'] == 75 and result['historical_budget_usd'] == 50
        assert result['effective_caps_nanousd'] == values['v11']['budget_policy']['effective_caps_nanousd']
        assert result['remaining_runtime_seconds'] is None and result['phase_eta_seconds'] is None
        assert result['health_response_amendments'] == [values['v9']['_record_id'], values['v11']['_record_id']]
        assert result['provenance']['head'] == list(before)
        assert 'synthetic-private-authority-never-project' not in json.dumps(result)
        assert observer.gateway.provider.calls == 0 and result['worker_mutations'] == 0
        if mode == 'current':
            assert result['unresolved_holds'] == 48 and result['new_unresolved_holds'] == 0
            assert result['operational_continuation']['baseline_unresolved_holds'] == 19
            assert result['operational_continuation']['held_or_transport_unknown'] == 29
            assert result['category_budget']['audit']['cap_nanousd'] == 30_000_000_000
            m.validate_v11_extension(values['v11'], values['v9'], values['stopped_v9_report'], values['plan'])
            # Extension validation cannot reset costs, original hold identities or the policy cohort.
            for key, replacement in (
                ('parent_execution_amendment', 'fictional-v10'),
                ('parent_implementation', {}),
                ('original_deadline', '2099-01-01T00:00:00+00:00'),
                ('method', 'another-method'),
                ('cap_nanousd', 75_000_000_000.0),
                ('legacy_category_budget', {}),
                ('legacy_unresolved_attempts', values['v11']['legacy_unresolved_attempts'][1:]),
                ('health_ancestor_amendments', [values['v11']['_record_id']]),
                ('operational_health_baseline_unresolved_attempts', values['v11']['legacy_unresolved_attempts']),
            ):
                changed = {**values['v11'], key: replacement}
                with pytest.raises(AuditError):
                    m.validate_v11_extension(changed, values['v9'], values['stopped_v9_report'], values['plan'])
        else:
            assert result['category_budget'] is None and result['final_coverage'] is None
    finally:
        observer.close()


@pytest.mark.parametrize('fault', [None, 'bool', 'historical', 'sum', 'reduced_main', 'no_increase', 'reset', 'automatic', 'new_models', 'extra'])
def test_v11_caps_require_exact_numeric_cumulative_policy(fault):
    value = budget_policy()
    if fault == 'bool':
        value['effective_caps_nanousd']['main'] = True
    elif fault == 'historical':
        value['historical_caps_nanousd']['main'] += 1
    elif fault == 'sum':
        value['effective_caps_nanousd']['total'] += 1
    elif fault == 'reduced_main':
        value['effective_caps_nanousd'].update(main=30_000_000_000, audit=45_000_000_000)
    elif fault == 'no_increase':
        value['effective_caps_nanousd'] = deepcopy(m.HISTORICAL_CAPS)
    elif fault == 'reset':
        value['reset_costs_or_holds'] = True
    elif fault == 'automatic':
        value['automatic_reallocation'] = True
    elif fault == 'new_models':
        value['new_models_or_questions_authorized'] = True
    elif fault == 'extra':
        value['allow_paid'] = True
    if fault is None:
        assert m.validate_budget_policy(value) == value['effective_caps_nanousd']
        assert m.validate_budget_policy(budget_policy({'total': 100_000_000_000, 'main': 60_000_000_000,
            'audit': 40_000_000_000}))['total'] == 100_000_000_000
    else:
        with pytest.raises(AuditError, match='v11_'):
            m.validate_budget_policy(value)


@pytest.mark.parametrize('runner', ['run_dossiers_v9.py', 'run_dossiers_v10.py', 'run_dossiers_v11.py', None])
def test_v11_registered_caps_do_not_apply_to_an_older_actual_worker(tmp_path, runner):
    amendment = {'budget_policy': budget_policy(), 'deadline_policy': m.DEADLINE_POLICY}
    item = process(tmp_path)
    item['command_line'] = item['command_line'].replace('run_dossiers.py', runner or 'run_dossiers_v11.py')
    rows = m.matching_processes([item], tmp_path) if runner else []
    result = m.effective_budget_context(amendment, rows)
    context = m.effective_deadline_context(NOW.isoformat(), None, rows, NOW, amendment)
    applies = runner in {None, 'run_dossiers_v11.py'}
    assert result['v11_budget_policy_applies'] is applies
    assert result['budget_usd'] == (75 if applies else 50)
    assert context['v11_deadline_policy_applies'] is applies
    assert m.effective_budget_context(None, rows)['budget_usd'] == 50
    if runner == 'run_dossiers_v11.py':
        item['command_line'] = item['command_line'].replace(' run ', ' pilot ')
        assert m.matching_processes([item], tmp_path) == []
