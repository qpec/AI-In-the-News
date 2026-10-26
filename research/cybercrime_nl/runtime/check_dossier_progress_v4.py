"""Versioned read-only observer for the same-budget dossier execution amendment.

The original monitor and runner remain unchanged. This module reads operational
metadata only and recognizes both original and amended worker commands.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "workbench"))
import lean_luna_state as state  # noqa: E402
from check_luna_decisions_incident_progress import amsterdam, read_progress  # noqa: E402
from newsresearch.common import AuditError, Config, digest  # noqa: E402
from newsresearch.runtime import Research, audited_handler  # noqa: E402
from newsresearch.storage import check_permissions  # noqa: E402

BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
ACTIVE_OWNER = BASE / "cybercrime-nl-dossiers-20261023-v1"
MONITOR_OWNER = BASE / "cybercrime-nl-dossier-progress-20261023-v1"
METHOD = "cybercrime-nl-dossier-progress-20261023-v4"
RUN_METHOD = "cybercrime-four-process-dossiers-20261023-v1"
EXPECTED_PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
EXPECTED_V2 = "08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282"
EXPECTED_V3 = "b8f46bf8d8c509c36ba9077cbffcd973f7ac6f585f2483bdb8d2996ec1c78d10"
EXPECTED_DIAGNOSTIC = "3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3"
EXPECTED_DIAGNOSTIC_REPAIR = "d96adb1244b7d101c5a90ec5c1b607e55aca8c1c971dbb51d788a9f06c30dd05"
EXPECTED_DOCUMENTS = 6691
EXPECTED_ARTICLES = 7743
CAP_NANOUSD = 50_000_000_000
V4_ALLOCATION = {"main_cap_nanousd": 35_000_000_000, "audit_cap_nanousd": 15_000_000_000,
                 "prior_audit_cap_nanousd": 10_000_000_000, "contingency_to_audit_nanousd": 5_000_000_000,
                 "contingency_nanousd": 0}
FRESH_SECONDS = 300
ALLOWED_RECORDS = {"cyber_dossier_plan", "cyber_dossier_first_launch", "cyber_dossier_report",
                   "cyber_dossier_execution_amendment", "cyber_dossier_execution_amendment_v3",
                   "cyber_dossier_execution_amendment_v4", "cyber_summary_fidelity_diagnostic_plan",
                   "cyber_summary_fidelity_diagnostic_report",
                   "cyber_summary_fidelity_diagnostic_amendment_v2",
                   "cyber_summary_fidelity_diagnostic_report_v2"}
DIAGNOSTIC_RUNNER = "run_summary_fidelity_diagnostic.py"
DIAGNOSTIC_REPAIR_RUNNER = "run_summary_fidelity_diagnostic_v2.py"
DIAGNOSTIC_RUNNERS = {DIAGNOSTIC_RUNNER, DIAGNOSTIC_REPAIR_RUNNER}
DIAGNOSTIC_PHASES = {DIAGNOSTIC_RUNNER: "summary_fidelity_audit",
                     DIAGNOSTIC_REPAIR_RUNNER: "summary_fidelity_audit_v2"}


def timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise AuditError("dossier_monitor_naive_timestamp")
    return parsed


def matching_processes(items, owner):
    expected = str(Path(owner).resolve()).replace("\\", "/").casefold().rstrip("/")
    matched = []
    for item in items:
        command = (item.get("command_line") or "").replace("\\", "/").casefold()
        run = re.search(r"(?:^|[/\s\"'])(run_dossiers(?:_v[234])?\.py|run_summary_fidelity_diagnostic(?:_v2)?\.py)[\"']?\s+(pilot|run)(?:\s|$)", command)
        if run and run.group(1) in DIAGNOSTIC_RUNNERS and run.group(2) != "run":
            continue
        workspace = re.search(r"--workspace(?:\s+|=)(?:\"([^\"]+)\"|'([^']+)'|(\S+))", command)
        actual = next((v for v in workspace.groups() if v is not None), None) if workspace else None
        # Default-owner execution is accepted only for the exact declared active owner.
        has_workspace = re.search(r"(?:^|\s)--workspace(?:\s|=|$)", command)
        default = not has_workspace and expected == str(ACTIVE_OWNER.resolve()).replace("\\", "/").casefold().rstrip("/")
        if run and ((actual and actual.rstrip("/") == expected) or default):
            if (type(item.get("pid")) is not int or type(item.get("parent_pid")) is not int
                    or item["pid"] < 1):
                raise AuditError("dossier_monitor_process_identity")
            timestamp(item["created_at"])
            matched.append({**item, "action": run.group(2), "runner": run.group(1), "uses_default_owner": default,
                            "worker_kind": "summary_diagnostic" if run.group(1) in DIAGNOSTIC_RUNNERS else "dossier"})
    parents = {item["parent_pid"] for item in matched}
    for item in matched:
        item["worker_leaf"] = item["pid"] not in parents
    return sorted(matched, key=lambda item: (item["created_at"], item["pid"]))


def workers(owner):
    script = r"""$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'run_dossiers(?:_v[234])?\.py|run_summary_fidelity_diagnostic(?:_v2)?\.py'
} | ForEach-Object { @{pid=$_.ProcessId; parent_pid=$_.ParentProcessId;
    created_at=$_.CreationDate.ToUniversalTime().ToString('o');
    executable_path=$_.ExecutablePath; command_line=$_.CommandLine} })
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                            text=True, timeout=20, check=True)
    return matching_processes(json.loads(result.stdout), owner)


def validate_progress(progress, plan):
    if progress is None:
        return
    if (progress.get("input_manifest") != plan["input_manifest"]
            or progress.get("unique_documents") != EXPECTED_DOCUMENTS
            or progress.get("selected_articles") != EXPECTED_ARTICLES
            or progress.get("cap_nanousd") != CAP_NANOUSD
            or not isinstance(progress.get("phase"), str)):
        raise AuditError("dossier_monitor_checkpoint_scope")
    timestamp(progress["observed_at"])
    for name in ("responses", "settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"):
        if type(progress.get(name)) is not int or progress[name] < 0:
            raise AuditError("dossier_monitor_checkpoint_counter")
    if progress["settled_nanousd"] + progress["held_nanousd"] != progress["committed_nanousd"]:
        raise AuditError("dossier_monitor_checkpoint_accounting")
    for key in ("phase_tasks_completed", "phase_tasks_planned"):
        if progress.get(key) is not None and (type(progress[key]) is not int or progress[key] < 0):
            raise AuditError("dossier_monitor_phase_counter")
    if (progress.get("phase_tasks_completed") is not None and progress.get("phase_tasks_planned") is not None
            and progress["phase_tasks_completed"] > progress["phase_tasks_planned"]):
        raise AuditError("dossier_monitor_phase_counter_order")


def phase_timing(progress, previous, now, processes, stop_present, deadline):
    leaves = [p for p in processes if p["worker_leaf"]]
    observed = timestamp(progress["observed_at"]) if progress else None
    age = (now - observed).total_seconds() if observed else None
    current = bool(progress and len(leaves) == 1 and progress.get("pid") == leaves[0]["pid"]
                   and timestamp(leaves[0]["created_at"]) <= observed)
    identity = {"pid": leaves[0]["pid"], "created_at": leaves[0]["created_at"]} if len(leaves) == 1 else None
    if not leaves:
        status, blocker = "stopped", "no_matching_python_worker"
    elif len(leaves) > 1:
        status, blocker = "multiple_workers_needs_investigation", "multiple_matching_python_workers"
    elif not current:
        status, blocker = "starting_or_waiting_first_checkpoint", "no_current_execution_checkpoint"
    elif stop_present:
        status, blocker = "stop_present_worker_exiting", "user_stop_present"
    elif age < -5:
        status, blocker = "clock_mismatch", "checkpoint_timestamp_in_future"
    elif age > FRESH_SECONDS:
        status, blocker = "running_needs_investigation", "checkpoint_over_five_minutes_old"
    else:
        status, blocker = "running", None
    diagnostic_active = any(p.get("runner") in DIAGNOSTIC_RUNNERS for p in leaves)
    if diagnostic_active and len(leaves) == 1:
        status = "summary_diagnostic_active" if current and -5 <= age <= FRESH_SECONDS else "summary_diagnostic_active_checkpoint_unconfirmed"
        blocker = "independent_summary_diagnostic_active"
    remaining_runtime = max(0, (timestamp(deadline) - now).total_seconds()) if deadline else None
    if remaining_runtime == 0:
        blocker = "admission_deadline_reached"
    rate, span, eta, finish, remaining = None, None, None, None, None
    done = progress.get("phase_tasks_completed") if progress else None
    planned = progress.get("phase_tasks_planned") if progress else None
    queue = progress.get("phase_task_set_sha256") if progress else None
    queue = queue or (progress.get("phase_started_at") if progress else None)
    if done is None or planned is None or not queue:
        blocker = blocker or "phase_workload_or_queue_identity_unavailable"
    else:
        remaining = planned - done
        if remaining == 0:
            blocker = blocker or "phase_queue_complete_next_phase_unknown"
        candidates = []
        for old in previous:
            before = old.get("progress") or {}
            old_queue = before.get("phase_task_set_sha256") or before.get("phase_started_at")
            if (not old.get("checkpoint_matches_current_execution") or old.get("execution_identity") != identity
                    or before.get("phase") != progress["phase"] or old_queue != queue
                    or before.get("execution_amendment") != progress.get("execution_amendment")
                    or before.get("phase_tasks_planned") != planned
                    or type(before.get("phase_tasks_completed")) is not int):
                continue
            duration = (observed - timestamp(before["observed_at"])).total_seconds()
            delta = done - before["phase_tasks_completed"]
            if 30 <= duration <= 5400 and delta > 0:
                candidates.append((abs(duration - 1800), duration, delta))
        if candidates:
            _, span, delta = min(candidates)
            rate = delta / span
        else:
            blocker = blocker or "no_comparable_same_execution_phase_delta"
        if blocker is None:
            eta = remaining / rate
            finish = now + timedelta(seconds=eta)
    return {"state": status, "checkpoint_matches_current_execution": current,
            "execution_identity": identity, "checkpoint_age_seconds": round(age, 2) if age is not None else None,
            "checkpoint_fresh": age is not None and -5 <= age <= FRESH_SECONDS,
            "phase_tasks_completed": done, "phase_tasks_planned": planned, "phase_tasks_remaining": remaining,
            "phase_tasks_per_minute": rate * 60 if rate is not None and blocker is None else None,
            "phase_rate_window_seconds": span if blocker is None else None,
            "phase_eta_seconds": eta, "phase_estimated_finish_amsterdam": amsterdam(finish) if finish else None,
            "phase_eta_blocker": blocker, "whole_pipeline_eta_seconds": None,
            "whole_pipeline_eta_blocker": "remaining_stages_have_different_workloads_and_costs",
            "deadline": deadline, "remaining_runtime_seconds": remaining_runtime,
            "deadline_expired": remaining_runtime == 0, "phase_finish_after_deadline": finish > timestamp(deadline) if finish and deadline else None,
            "eta_scope": "Current fixed phase queue only, using observed task completion deltas; no prediction that unknown outcomes resolve."}


def report_is_current(report, plan, response_state, progress, processes):
    if not report or processes:
        return False
    return bool(report.get("plan") == plan["_record_id"]
        and report.get("stored_responses") == response_state["responses"]
        and report.get("_created_event", -1) > (response_state["last_response_event"] or -1)
        and report.get("_created_event", -1) > (response_state.get("last_attempt_event") or -1)
        and report.get("articles") == EXPECTED_ARTICLES and report.get("distinct_inputs") == EXPECTED_DOCUMENTS
        and (not progress or (report["stored_responses"] >= progress["responses"]
             and timestamp(report["at"]) >= timestamp(progress["observed_at"]))))


def validate_amendment(amendment, plan, deadline):
    """Bind the extension to the original owner, implementation and deadline."""
    if amendment is None:
        return
    if (amendment.get("parent_plan") != plan["_record_id"]
            or amendment.get("parent_implementation") != plan["implementation"]
            or amendment.get("original_deadline") != deadline
            or amendment.get("cap_nanousd") != CAP_NANOUSD
            or not isinstance(amendment.get("implementation"), dict) or not amendment["implementation"]
            or not isinstance(amendment.get("legacy_unresolved_attempts"), list)
            or len(set(amendment["legacy_unresolved_attempts"])) != len(amendment["legacy_unresolved_attempts"])):
        raise AuditError("dossier_monitor_amendment_binding")


def validate_budget(totals):
    for name in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"):
        if type(totals.get(name)) is not int or totals[name] < 0:
            raise AuditError("dossier_monitor_budget_counter")
    if totals["settled_nanousd"] + totals["held_nanousd"] != totals["committed_nanousd"]:
        raise AuditError("dossier_monitor_budget_sum")


def verify_implementations(*records):
    """Hash declared local code/specification files; never read corpus artifacts."""
    files = {}
    for record in records:
        if record is None:
            continue
        implementation = record.get("implementation")
        if not isinstance(implementation, dict) or not implementation:
            raise AuditError("dossier_monitor_implementation_missing")
        for relative, expected in implementation.items():
            if (not isinstance(relative, str) or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected)):
                raise AuditError("dossier_monitor_implementation_identity")
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT.resolve()) or path == ROOT.resolve():
                raise AuditError("dossier_monitor_implementation_path")
            if relative in files and files[relative] != expected:
                raise AuditError("dossier_monitor_frozen_parent_hash_replaced")
            files[relative] = expected
    for relative, expected in files.items():
        path = ROOT / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise AuditError("dossier_monitor_frozen_implementation_changed")
    return {"verified_files": len(files), "implementation_sha256": digest(files)}


def validate_chain(plan, v2, v3, deadline, v4=None, diagnostic=None, diagnostic_report=None,
                   diagnostic_repair=None, repair_report=None):
    if plan["_record_id"] != EXPECTED_PLAN:
        raise AuditError("dossier_monitor_original_plan_identity")
    validate_amendment(v2, plan, deadline)
    if v2 and v2["_record_id"] != EXPECTED_V2:
        raise AuditError("dossier_monitor_v2_identity")
    if v3 and v3["_record_id"] != EXPECTED_V3:
        raise AuditError("dossier_monitor_v3_identity")
    if v4 and (any(v4.get(k) != value for k, value in V4_ALLOCATION.items())
            or v4.get("summary_reference_minimum") != 6 or v4.get("summary_reference_target") != 10):
        raise AuditError("dossier_monitor_v4_allocation_or_summary_reference_scope")
    if v4 and (diagnostic is None or v4.get("diagnostic_plan") != diagnostic["_record_id"]):
        raise AuditError("dossier_monitor_v4_diagnostic_identity")
    if v4 and (v2 is None or v3 is None
            or v4.get("ancestor_execution_amendments") != {"v2": v2["_record_id"], "v3": v3["_record_id"]}
            or diagnostic_repair is None or v4.get("diagnostic_amendment") != diagnostic_repair["_record_id"]
            or repair_report is None or v4.get("diagnostic_report") != repair_report["_record_id"]):
        raise AuditError("dossier_monitor_v4_ancestor_or_diagnostic_report_binding")
    previous = None
    for amendment, parent in ((v2, None), (v3, v2), (v4, v3)):
        if amendment is None:
            continue
        if amendment is not v2 and (parent is None
                or amendment.get("parent_plan") != plan["_record_id"]
                or amendment.get("parent_execution_amendment") != parent["_record_id"]
                or amendment.get("parent_implementation") != parent["implementation"]
                or amendment.get("original_deadline") != deadline
                or amendment.get("cap_nanousd") != CAP_NANOUSD):
            raise AuditError("dossier_monitor_amendment_parent_binding")
        attempts = amendment.get("legacy_unresolved_attempts")
        if (not isinstance(attempts, list) or any(not isinstance(item, str) or not item for item in attempts)
                or len(set(attempts)) != len(attempts)):
            raise AuditError("dossier_monitor_hold_lineage_identity")
        budget = amendment.get("legacy_budget")
        if not isinstance(budget, dict):
            raise AuditError("dossier_monitor_legacy_budget_missing")
        validate_budget(budget)
        if budget["unresolved_holds"] != len(attempts):
            raise AuditError("dossier_monitor_hold_lineage_count")
        if previous and (not set(previous["legacy_unresolved_attempts"]) <= set(attempts)
                or any(budget[k] < previous["legacy_budget"][k]
                       for k in ("settled_nanousd", "held_nanousd", "committed_nanousd"))):
            raise AuditError("dossier_monitor_amendment_liability_reduced")
        previous = amendment
    if diagnostic:
        if (diagnostic["_record_id"] != EXPECTED_DIAGNOSTIC
                or v3 is None or diagnostic.get("parent_plan") != plan["_record_id"]
                or diagnostic.get("execution_amendment") != v3["_record_id"]
                or diagnostic.get("original_deadline") != deadline
                or diagnostic.get("cap_nanousd") != CAP_NANOUSD
                or diagnostic.get("audit_cap_nanousd") != 10_000_000_000
                or diagnostic.get("main_cap_nanousd") != 35_000_000_000
                or diagnostic.get("diagnostic_cap_nanousd") != 2_000_000_000):
            raise AuditError("dossier_monitor_diagnostic_binding")
        baseline = diagnostic.get("baseline_budget")
        attempts = diagnostic.get("baseline_hold_attempts")
        if not isinstance(baseline, dict) or not isinstance(attempts, list):
            raise AuditError("dossier_monitor_diagnostic_baseline_missing")
        validate_budget(baseline)
        if (len(attempts) != len(set(attempts)) or baseline["unresolved_holds"] != len(attempts)
                or not set(v3["legacy_unresolved_attempts"]) <= set(attempts)
                or any(baseline[k] < v3["legacy_budget"][k]
                       for k in ("settled_nanousd", "held_nanousd", "committed_nanousd"))):
            raise AuditError("dossier_monitor_diagnostic_liability_reduced")
        if diagnostic_report:
            if (diagnostic_report.get("diagnostic_plan") != diagnostic["_record_id"]
                    or diagnostic_report.get("plan") != plan["_record_id"]
                    or diagnostic_report.get("execution_amendment") != v3["_record_id"]
                    or diagnostic_report.get("original_deadline") != deadline):
                raise AuditError("dossier_monitor_diagnostic_report_binding")
            validate_current_liabilities(diagnostic_report, v3)
            if any(diagnostic_report[k] < baseline[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd")):
                raise AuditError("dossier_monitor_diagnostic_report_liability_reduced")
        if v4:
            if (not set(attempts) <= set(v4["legacy_unresolved_attempts"])
                    or any(v4["legacy_budget"][k] < baseline[k]
                           for k in ("settled_nanousd", "held_nanousd", "committed_nanousd"))):
                raise AuditError("dossier_monitor_v4_diagnostic_baseline_lost")
            if diagnostic_report and diagnostic_report["_created_event"] < v4["_created_event"]:
                if any(v4["legacy_budget"][k] < diagnostic_report[k]
                       for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
                    raise AuditError("dossier_monitor_v4_diagnostic_costs_lost")
    elif diagnostic_report:
        raise AuditError("dossier_monitor_diagnostic_report_without_plan")
    if diagnostic_repair:
        if (diagnostic is None or diagnostic_report is None
                or diagnostic_repair["_record_id"] != EXPECTED_DIAGNOSTIC_REPAIR
                or diagnostic_repair.get("parent_diagnostic_plan") != diagnostic["_record_id"]
                or diagnostic_repair.get("parent_diagnostic_report") != diagnostic_report["_record_id"]
                or diagnostic_repair.get("parent_implementation") != diagnostic["implementation"]
                or diagnostic_repair.get("parent_plan") != plan["_record_id"]
                or diagnostic_repair.get("execution_amendment") != v3["_record_id"]
                or diagnostic_repair.get("original_deadline") != deadline
                or diagnostic_repair.get("total_cap_nanousd") != CAP_NANOUSD
                or diagnostic_repair.get("audit_cap_nanousd") != 10_000_000_000
                or diagnostic_repair.get("repair_cap_nanousd") != 2_000_000_000
                or diagnostic_repair.get("combined_diagnostic_cap_nanousd") != 4_000_000_000):
            raise AuditError("dossier_monitor_diagnostic_repair_binding")
        baseline = diagnostic_repair.get("baseline_budget")
        attempts = diagnostic_repair.get("baseline_hold_attempts")
        required = diagnostic_repair.get("required_parent_hold_attempts")
        if not isinstance(baseline, dict) or not isinstance(attempts, list) or not isinstance(required, list):
            raise AuditError("dossier_monitor_diagnostic_repair_baseline_missing")
        validate_budget(baseline)
        if (len(attempts) != len(set(attempts)) or baseline["unresolved_holds"] != len(attempts)
                or len(required) != 3 or len(set(required)) != 3 or not set(required) <= set(attempts)
                or not set(diagnostic["baseline_hold_attempts"]) <= set(attempts)
                or any(baseline[k] < diagnostic_report[k] for k in
                       ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))):
            raise AuditError("dossier_monitor_diagnostic_repair_liability_reduced")
        if repair_report:
            if (repair_report.get("diagnostic_plan") != diagnostic_repair["_record_id"]
                    or repair_report.get("parent_diagnostic_plan") != diagnostic["_record_id"]
                    or repair_report.get("plan") != plan["_record_id"]
                    or repair_report.get("execution_amendment") != v3["_record_id"]
                    or repair_report.get("original_deadline") != deadline):
                raise AuditError("dossier_monitor_diagnostic_repair_report_binding")
            validate_current_liabilities(repair_report, v3)
            if any(repair_report[k] < baseline[k] for k in
                   ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
                raise AuditError("dossier_monitor_diagnostic_repair_report_liability_reduced")
        if v4 and (not set(attempts) <= set(v4["legacy_unresolved_attempts"])
                or any(v4["legacy_budget"][k] < repair_report[k] for k in
                       ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))):
            raise AuditError("dossier_monitor_v4_diagnostic_repair_liability_lost")
    elif repair_report:
        raise AuditError("dossier_monitor_diagnostic_repair_report_without_plan")
    return verify_implementations(plan, v2, v3, v4, diagnostic, diagnostic_repair)


def bound_report(reports, identifier):
    """Select an immutable binding separately from a later observational report."""
    matches = [r for r in reports if r["_record_id"] == identifier]
    if len(matches) != 1:
        raise AuditError("dossier_monitor_bound_diagnostic_report_missing")
    return matches[0]


def validate_diagnostic_snapshot(totals, diagnostic):
    """A current diagnostic checkpoint may not drop its admission baseline."""
    validate_budget(totals)
    baseline = diagnostic["baseline_budget"]
    if any(totals[key] < baseline[key] for key in
           ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
        raise AuditError("dossier_monitor_diagnostic_checkpoint_liability_reduced")


def validate_current_liabilities(totals, amendment):
    """Check counters against the amendment explicitly identified by this snapshot."""
    if totals is None:
        return
    validate_budget(totals)
    hold_breakdown(totals)
    if amendment is None:
        return
    legacy = amendment["legacy_budget"]
    if (totals.get("legacy_unresolved_holds") != len(amendment["legacy_unresolved_attempts"])
            or type(totals.get("legacy_held_nanousd")) is not int
            or totals["legacy_held_nanousd"] < legacy["held_nanousd"]
            or totals["settled_nanousd"] < legacy["settled_nanousd"]):
        raise AuditError("dossier_monitor_current_legacy_liability_reduced")


def hold_breakdown(totals):
    """Only expose an explicitly reported current split; never infer releases."""
    keys = ("legacy_unresolved_holds", "new_unresolved_holds")
    values = {key: totals.get(key) if totals else None for key in keys}
    if any(value is not None and (type(value) is not int or value < 0) for value in values.values()):
        raise AuditError("dossier_monitor_hold_split_invalid")
    known = all(value is not None for value in values.values())
    if known and sum(values.values()) != totals["unresolved_holds"]:
        raise AuditError("dossier_monitor_hold_split_sum")
    money = {key: totals.get(key) if totals else None for key in ("legacy_held_nanousd", "new_held_nanousd")}
    if any(value is not None and (type(value) is not int or value < 0) for value in money.values()):
        raise AuditError("dossier_monitor_hold_cost_invalid")
    money_known = all(value is not None for value in money.values())
    if money_known and sum(money.values()) != totals["held_nanousd"]:
        raise AuditError("dossier_monitor_hold_cost_sum")
    return {**values, "hold_split_status": "reported_current" if known else "not_reported",
            **money, "legacy_held_cost_usd": money["legacy_held_nanousd"] / 1e9 if money["legacy_held_nanousd"] is not None else None,
            "new_held_cost_usd": money["new_held_nanousd"] / 1e9 if money["new_held_nanousd"] is not None else None,
            "hold_split_cost_note": "Explicit current worker split" if money_known else "Separate held costs are not reported; do not infer them from old snapshots."}


class Source:
    """Selected operational metadata only, inside the monitor's audited handler."""
    def __init__(self, owner):
        self.owner = Path(owner).resolve(strict=True)
        check_permissions(self.owner, root=True)
        self.artifacts = state.SelectedArtifacts(self.owner)
        self.db = state.read_only_database(self.owner)

    def rows(self, kind):
        if kind not in ALLOWED_RECORDS:
            raise AuditError("dossier_monitor_record_scope")
        values = []
        for row in self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,)):
            self.artifacts.check(row["artifact"])
            values.append({**state.row_value(row, kind), "_created_event": row["created_event"]})
        return values

    def one(self, kind):
        values = self.rows(kind)
        if len(values) != 1:
            raise AuditError("dossier_monitor_exactly_one_" + kind)
        return values[0]

    def close(self):
        self.db.close()


class Study(Research):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == ACTIVE_OWNER.resolve():
            raise AuditError("dossier_monitor_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        if data or not self.config.offline or self.ledger.root.resolve() == ACTIVE_OWNER.resolve():
            raise AuditError("dossier_monitor_offline_separate_owner_required")
        paths = [Path(__file__), ROOT / "scripts/lean_luna_state.py",
                 ROOT / "workbench/check_luna_decisions_incident_progress.py"]
        code = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        versions = {}
        definitions = {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Read only fixed owner's source-free operational records via read-only SQLite, verifying selected projection and artifact hashes. Recognize original/v2/v3/v4 pilot/run commands and the independent summary diagnostic run command, PID creation times and leaf workers. An active diagnostic is a writer, prevents current dossier-report claims and suppresses dossier ETA. Verify original/v2/v3 identity, v4 parent and diagnostic-plan chain, unchanged implementation files, original deadline/cap and cumulative hold/cost lineage including diagnostic costs. Never replace plans or release holds. Read mutable checkpoints with Windows share-read/write/delete. When stopped, validate latest reports against response and attempt event boundaries, amendment and published report ID. Expose current v4 gate/outcome only from a current v4 report. Retain observation in the same separate protected monitor owner with a new method version. No worker writes, packet/source reads, model calls or restart. Phase ETA needs comparable deltas in the same PID/creation/phase/queue/amendment; whole-pipeline ETA remains unknown.",
                "limitations": "Selected metadata verification is not full active-store replay. Live checkpoint excludes newly admitted work since its last write. Process and database observations are not atomic. Stored responses include invalid/unknown outputs. Dossier assignments and summaries remain model-supported, not human truth."},
            "question": {"text": "Is the USD50 Cybercrime NL dossier workflow running, what is its current phase coverage and budget, and is a phase ETA supported?"},
            "selection": {"rules": "Only operational metadata for 6,691 unique inputs / 7,743 selected article rows in the fixed separate dossier owner; no source text, requests or parsed model results."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }
        for kind, content in definitions.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD,
                "content": content, "amend_latest": True, "reason": "Register read-only dossier monitoring before observation"})["id"]
        processes = workers(ACTIVE_OWNER)
        source = Source(ACTIVE_OWNER)
        try:
            plan = source.one("cyber_dossier_plan")
            if (plan["method"] != RUN_METHOD or plan["unique_documents"] != EXPECTED_DOCUMENTS
                    or plan["eligible_articles"] != EXPECTED_ARTICLES or plan["cap_nanousd"] != CAP_NANOUSD):
                raise AuditError("dossier_monitor_frozen_plan_scope")
            launches = source.rows("cyber_dossier_first_launch")
            if len(launches) > 1:
                raise AuditError("dossier_monitor_multiple_first_launches")
            amendments = source.rows("cyber_dossier_execution_amendment")
            if len(amendments) > 1:
                raise AuditError("dossier_monitor_unsupported_amendment_count")
            v2 = amendments[0] if amendments else None
            amendments_v3 = source.rows("cyber_dossier_execution_amendment_v3")
            if len(amendments_v3) > 1:
                raise AuditError("dossier_monitor_unsupported_v3_amendment_count")
            v3 = amendments_v3[0] if amendments_v3 else None
            amendments_v4 = source.rows("cyber_dossier_execution_amendment_v4")
            diagnostics = source.rows("cyber_summary_fidelity_diagnostic_plan")
            if len(amendments_v4) > 1 or len(diagnostics) > 1:
                raise AuditError("dossier_monitor_unsupported_v4_or_diagnostic_count")
            v4 = amendments_v4[0] if amendments_v4 else None
            diagnostic = diagnostics[0] if diagnostics else None
            diagnostic_reports = source.rows("cyber_summary_fidelity_diagnostic_report")
            diagnostic_repairs = source.rows("cyber_summary_fidelity_diagnostic_amendment_v2")
            if len(diagnostic_repairs) > 1:
                raise AuditError("dossier_monitor_unsupported_diagnostic_repair_count")
            diagnostic_repair = diagnostic_repairs[0] if diagnostic_repairs else None
            repair_reports = source.rows("cyber_summary_fidelity_diagnostic_report_v2")
            parent_report = (bound_report(diagnostic_reports, diagnostic_repair["parent_diagnostic_report"])
                             if diagnostic_repair else diagnostic_reports[-1] if diagnostic_reports else None)
            repair_report = (bound_report(repair_reports, v4["diagnostic_report"])
                             if v4 else repair_reports[-1] if repair_reports else None)
            latest_diagnostic_reports = repair_reports if diagnostic_repair else diagnostic_reports
            diagnostic_report = latest_diagnostic_reports[-1] if latest_diagnostic_reports else None
            amendment = v4 or v3 or v2
            deadline = launches[0]["deadline"] if launches else None
            implementation_verification = validate_chain(plan, v2, v3, deadline, v4, diagnostic, parent_report,
                                                          diagnostic_repair, repair_report)
            if any(p.get("runner") == "run_dossiers_v2.py" for p in processes) and not v2:
                raise AuditError("dossier_monitor_amended_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v3.py" for p in processes) and not v3:
                raise AuditError("dossier_monitor_v3_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v4.py" for p in processes) and not v4:
                raise AuditError("dossier_monitor_v4_worker_without_registration")
            if any(p.get("runner") == DIAGNOSTIC_RUNNER for p in processes) and not diagnostic:
                raise AuditError("dossier_monitor_diagnostic_worker_without_registration")
            if any(p.get("runner") == DIAGNOSTIC_REPAIR_RUNNER for p in processes) and not diagnostic_repair:
                raise AuditError("dossier_monitor_diagnostic_repair_worker_without_registration")
            reports = source.rows("cyber_dossier_report") if not processes else []
            count_sql = "SELECT count(*) AS responses,max(created_event) AS last_response_event FROM records WHERE kind=?"
            phase_sql = "SELECT json_extract(payload,'$.phase') AS phase,count(*) AS responses FROM records WHERE kind=? GROUP BY json_extract(payload,'$.phase')"
            attempt_sql = "SELECT max(seq) FROM events WHERE kind='model.attempt.intended'"
            diagnostic_sql = "SELECT count(*) FROM records WHERE kind=? AND json_extract(payload,'$.diagnostic_plan') IN (?,?)"
            diagnostic_ids = [diagnostic["_record_id"] if diagnostic else None,
                              diagnostic_repair["_record_id"] if diagnostic_repair else None]
            self.ledger.append(session, "dossier_monitor.count.intended", {"sql": count_sql,
                "phase_sql": phase_sql, "attempt_sql": attempt_sql, "diagnostic_sql": diagnostic_sql,
                "parameters": ["cyber_dossier_response", *diagnostic_ids], "owner": str(ACTIVE_OWNER)})
            response_state = dict(source.db.execute(count_sql, ("cyber_dossier_response",)).fetchone())
            response_state["last_attempt_event"] = source.db.execute(attempt_sql).fetchone()[0]
            diagnostic_responses = source.db.execute(diagnostic_sql,
                ("cyber_dossier_response", *diagnostic_ids)).fetchone()[0]
            phase_counts = {row["phase"] or "unavailable": row["responses"]
                            for row in source.db.execute(phase_sql, ("cyber_dossier_response",))}
            head = list(source.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        finally:
            source.close()
        raw = read_progress(ACTIVE_OWNER / "progress.json") if (ACTIVE_OWNER / "progress.json").is_file() else None
        progress = json.loads(raw) if raw else None
        validate_progress(progress, plan)
        known_amendments = {r["_record_id"]: r for r in (v2, v3, v4) if r}
        checkpoint_amendment = progress.get("execution_amendment") if progress else None
        if checkpoint_amendment is not None and checkpoint_amendment not in known_amendments:
            raise AuditError("dossier_monitor_checkpoint_amendment_mismatch")
        checkpoint_diagnostic = progress.get("diagnostic_plan") if progress else None
        if checkpoint_diagnostic is not None and checkpoint_diagnostic not in diagnostic_ids:
            raise AuditError("dossier_monitor_checkpoint_diagnostic_mismatch")
        if checkpoint_diagnostic is not None:
            checkpoint_diagnostic_plan = next(r for r in (diagnostic, diagnostic_repair)
                                              if r and r["_record_id"] == checkpoint_diagnostic)
            validate_diagnostic_snapshot(progress, checkpoint_diagnostic_plan)
        validate_current_liabilities(progress, known_amendments.get(checkpoint_amendment))
        if progress and progress.get("deadline") is not None and progress["deadline"] != deadline:
            raise AuditError("dossier_monitor_deadline_mismatch")
        previous = [self.ledger.get(row[0], "cyber_dossier_progress_observation") for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='cyber_dossier_progress_observation' ORDER BY created_event")]
        previous = [r for r in previous if r["provenance"]["plan"] == plan["_record_id"]]
        now = datetime.now(timezone.utc)
        stop = (ACTIVE_OWNER / "STOP").exists()
        measured = phase_timing(progress, previous, now, processes, stop, deadline)
        expected_worker_amendment = {"run_dossiers.py": None,
            "run_dossiers_v2.py": v2["_record_id"] if v2 else None,
            "run_dossiers_v3.py": v3["_record_id"] if v3 else None,
            "run_dossiers_v4.py": v4["_record_id"] if v4 else None,
            DIAGNOSTIC_RUNNER: v3["_record_id"] if v3 else None,
            DIAGNOSTIC_REPAIR_RUNNER: v3["_record_id"] if v3 else None}
        leaves = [p for p in processes if p["worker_leaf"]]
        diagnostic_active = any(p["runner"] in DIAGNOSTIC_RUNNERS for p in leaves)
        checkpoint_version_matches_worker = bool(progress and len(leaves) == 1
            and checkpoint_amendment == expected_worker_amendment[leaves[0]["runner"]])
        if diagnostic_active:
            worker_diagnostic = diagnostic_repair if len(leaves) == 1 and leaves[0]["runner"] == DIAGNOSTIC_REPAIR_RUNNER else diagnostic
            checkpoint_version_matches_worker = bool(checkpoint_version_matches_worker
                and checkpoint_diagnostic == worker_diagnostic["_record_id"]
                and progress["phase"] == DIAGNOSTIC_PHASES[leaves[0]["runner"]])
            if not measured["checkpoint_matches_current_execution"] or not checkpoint_version_matches_worker:
                measured.update(phase_tasks_completed=None, phase_tasks_planned=None, phase_tasks_remaining=None)
        if measured["checkpoint_matches_current_execution"] and not checkpoint_version_matches_worker:
            measured.update(state="summary_diagnostic_active_checkpoint_unconfirmed" if diagnostic_active else "starting_or_waiting_first_checkpoint", checkpoint_matches_current_execution=False,
                phase_eta_seconds=None, phase_estimated_finish_amsterdam=None, phase_tasks_per_minute=None,
                phase_rate_window_seconds=None, phase_finish_after_deadline=None,
                phase_eta_blocker="checkpoint_from_different_execution_amendment")
        report = reports[-1] if reports else None
        current = report_is_current(report, plan, response_state, progress, processes)
        if amendment and report and report.get("execution_amendment") != amendment["_record_id"]:
            current = False
        if current:
            validate_current_liabilities(report, amendment)
        diagnostic_current = bool(diagnostic_report and not processes
            and diagnostic_report["stored_diagnostic_responses"] == diagnostic_responses
            and diagnostic_report["_created_event"] > (response_state["last_response_event"] or -1)
            and diagnostic_report["_created_event"] > (response_state["last_attempt_event"] or -1)
            and (not progress or timestamp(diagnostic_report["at"]) >= timestamp(progress["observed_at"])))
        published_report, published_status = None, "not_read_while_running" if processes else "missing"
        report_path = ACTIVE_OWNER / "dossier-report.json"
        if not processes and report_path.is_file():
            try:
                published_report = json.loads(read_progress(report_path))
                projected = {k: v for k, v in report.items() if not k.startswith("_")} if report else None
                published_status = "matches_latest_audited_record" if report and published_report == {"id": report["_record_id"], **projected} else "stale_or_different_from_audited_record"
            except (json.JSONDecodeError, UnicodeDecodeError):
                published_status = "invalid_partial_file"
        totals = report if current else diagnostic_report if diagnostic_current else progress
        costs = {name: totals.get(name) if totals else None for name in
                 ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")}
        holds = hold_breakdown(totals)
        coverage_keys = ("pipeline_finished", "pipeline_processing_complete", "final_audit_completion", "final_audit_complete",
                         "pilot_summary_reference",
                         "four_processes_complete", "groups", "multi_article_groups",
                         "unique_inputs_grouped", "unresolved_inputs", "groups_with_usable_summary", "article_routes")
        result = {"versions": versions, "observed_at": now.isoformat(), "observed_amsterdam": amsterdam(now),
            "provenance": {"owner": str(ACTIVE_OWNER), "plan": plan["_record_id"], "head": head,
                           "latest_report": report["_record_id"] if report else None,
                           "execution_amendment": amendment["_record_id"] if amendment else None,
                           "amendment_parent_plan": amendment["parent_plan"] if amendment else None,
                           "v2_execution_amendment": v2["_record_id"] if v2 else None,
                           "v3_execution_amendment": v3["_record_id"] if v3 else None,
                           "v4_execution_amendment": v4["_record_id"] if v4 else None,
                           "amendment_parent_execution": amendment.get("parent_execution_amendment") if amendment else None,
                           "diagnostic_plan": diagnostic["_record_id"] if diagnostic else None,
                           "diagnostic_amendment": diagnostic_repair["_record_id"] if diagnostic_repair else None,
                           "bound_diagnostic_report": v4.get("diagnostic_report") if v4 else None,
                           "latest_diagnostic_report": diagnostic_report["_record_id"] if diagnostic_report else None,
                           "implementation_verification": implementation_verification},
            "progress": progress, "checkpoint_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "checkpoint_artifact": self.ledger.artifacts.put_bytes(raw) if raw else None,
            "matching_python_processes": processes, "worker_python_processes": [p for p in processes if p["worker_leaf"]],
            "user_stop_present": stop,
            "phase": "independent_summary_fidelity_diagnostic" if diagnostic_active else progress.get("phase") if progress else "awaiting_first_checkpoint",
            "checkpoint_phase": progress.get("phase") if progress else None,
            "diagnostic_worker_active": diagnostic_active, "writer_active": bool(leaves),
            "writer_leaf_count": len(leaves), "stored_diagnostic_responses": diagnostic_responses,
            "latest_diagnostic_report_current": diagnostic_current,
            "stored_responses": response_state["responses"], "responses_by_phase": phase_counts,
            "selected_articles": EXPECTED_ARTICLES, "unique_documents": EXPECTED_DOCUMENTS,
            **costs, **holds, "settled_cost_usd": costs["settled_nanousd"] / 1e9 if costs["settled_nanousd"] is not None else None,
            "held_cost_usd": costs["held_nanousd"] / 1e9 if costs["held_nanousd"] is not None else None,
            "committed_cost_usd": costs["committed_nanousd"] / 1e9 if costs["committed_nanousd"] is not None else None,
            "budget_usd": 50, "budget_scope": "Audited stopped dossier report" if current else "Audited stopped diagnostic report including all dossier costs" if diagnostic_current else "Last checkpoint; subsequent admissions may add reservations",
            "v4_budget_allocation_nanousd": {key: v4[key] for key in V4_ALLOCATION} if v4 else None,
            "v4_summary_reference_requirement": {"minimum": v4["summary_reference_minimum"],
                "target": v4["summary_reference_target"], "all_selected_must_be_valid_supported": True} if v4 else None,
            "latest_report_current": current, "published_report_status": published_status,
            "pilot_gate": report.get("pilot_gate") if current else None,
            "pilot_summary_reference": report.get("pilot_summary_reference") if current and v4 else None,
            "pilot_gate_phase": "pilot_v4_gate" if v4 else "pilot_v3_gate" if v3 else "pilot_v2_gate" if v2 else "pilot_gate",
            "full_outcome_phase": "full_v4_outcome" if v4 else "full_v3_outcome" if v3 else "full_v2_outcome" if v2 else "full_outcome",
            "pilot_v3_gate": report.get("pilot_gate") if current and v3 and not v4 else None,
            "full_v3_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v3 and not v4 and report.get("pipeline_finished") else None),
            "pilot_v4_gate": report.get("pilot_gate") if current and v4 else None,
            "full_v4_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v4 and report.get("pipeline_finished") else None),
            "full_v4_processing_outcome": ({key: report.get(key) for key in coverage_keys}
                                           if current and v4 and report.get("pipeline_processing_complete") else None),
            "checkpoint_execution_amendment": checkpoint_amendment,
            "checkpoint_version_matches_worker": checkpoint_version_matches_worker,
            "final_coverage": {key: report.get(key) for key in coverage_keys} if current else None,
            "count_meaning": "Saved provider responses across embeddings, decisions, summaries and audit, including invalid/unknown responses; not articles classified or dossiers validated.",
            "new_model_calls": 0, "worker_mutations": 0, **measured}
        identifier = self.ledger.record(session, "cyber_dossier_progress_observation", digest(result), result)
        temporary = self.ledger.root / ("latest-progress." + uuid.uuid4().hex + ".writing")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps({"id": identifier, **result}, ensure_ascii=False, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.ledger.root / "latest-progress.json")
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=MONITOR_OWNER)
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Observe the separate USD50 Cybercrime dossier workflow without changing its worker",
                                      actor="codex:cybercrime-dossier-monitor"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
