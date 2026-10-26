"""Synthetic source-free operational monitor checks; no production owner access."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_dossier_progress_v5 as m  # noqa: E402
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
    for number, suffix in enumerate(("", "_v2", "_v3", "_v4", "_v5", "_v6"), 1):
        row = process(tmp_path, pid=number)
        row["command_line"] = row["command_line"].replace("run_dossiers.py", "run_dossiers" + suffix + ".py")
        rows.append(row)
    assert [r["runner"] for r in m.matching_processes(rows, tmp_path)] == [
        "run_dossiers.py", "run_dossiers_v2.py", "run_dossiers_v3.py", "run_dossiers_v4.py", "run_dossiers_v5.py"]


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
