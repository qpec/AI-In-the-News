"""Read-only observer distinguishing administrative writers from paid workers.

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
MONITOR_OWNER = BASE / "cybercrime-nl-dossier-writer-progress-20261024-v1"
METHOD = "cybercrime-nl-dossier-progress-administrative-writers-20261024-v1"
RUN_METHOD = "cybercrime-four-process-dossiers-20261023-v1"
EXPECTED_PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
EXPECTED_V2 = "08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282"
EXPECTED_V3 = "b8f46bf8d8c509c36ba9077cbffcd973f7ac6f585f2483bdb8d2996ec1c78d10"
EXPECTED_V4 = "10c535b6968fd657e49e2c68fceb83ba9c37be569991b58d553eaf0a20657512"
EXPECTED_V5 = "9f531f9473e28f2773b820b1e5fbdf15eb9a44ce6fedab9ba1f2aad538d50375"
EXPECTED_V5_REPORT = "60d21154865be8e8a093b96236da56074c40d6d88a62f783f9284ee9c205ade1"
EXPECTED_V6 = "464b6c795b8c9bee7930b150c3343e19cc65c50b36e649d297bc95510d253ce6"
EXPECTED_V6_PASSED_REPORT = "4f8a3c089cca17c3bfce3ced418a96553837fe402d271b39cc0f965cbe6c71cf"
EXPECTED_V6_STOPPED_REPORT = "bb860bb5ca35cc5a80d0684b20aa6db5be56550f9bac33325d6edde5794f1f5b"
DEADLINE_POLICY = {"version": "user-authorized-frozen-pipeline-completion-v1",
    "mode": "finish_frozen_pipeline_within_existing_guards", "effective_admission_deadline": None,
    "original_deadline_immutable": True, "budget_reset": False, "provider_retries": 0}
EXPECTED_V9 = "1c917387c42b7d6951c343ba3a6b845219b6d8b852d2a99bfb08b6d63d649ef9"
EXPECTED_V8_STOPPED_REPORT = "92bf8d1677746097fa68fffec142a647b435507efa58bffdbce593e92e5b14f4"
EXPECTED_V8_DIAGNOSTIC = "d3ffce1597571dd687845da0b8880290ad94bd50d2f58f7b0822d8869bb53bbd"
EXPECTED_V8_DIAGNOSTIC_OWNER = BASE / "cybercrime-v8-failure-technical-view-20261023-v2"
EXPECTED_V9_BASELINE_HOLDS = 19
OPERATIONAL_POLICY = {"version": "settled-wave-continuation-with-durable-health-v1", "window": 32,
    "consecutive_failure_limit": 8, "window_transport_unknown_limit": 8, "window_failure_limit": 16,
    "automatic_provider_retries": 0, "automatic_process_restarts": 0,
    "baseline_holds_excluded_from_new_health_window": True, "legacy_guard_cooldown_seconds": 30}
V10_HEALTH_SCOPE = "All outcomes under the v9 operational policy, including this deadline-only continuation; the original v9 health baseline is preserved."
V11_HEALTH_SCOPE = "All outcomes under the v9 operational policy, including this cumulative-budget and deadline continuation; the original v9 health baseline is preserved."
OPERATIONAL_SCOPE = "All v9 outcomes across phases and process restarts; original holds remain outside this health window."
FATAL_GUARD_REASONS = {"fatal_http_auth_configuration_or_request", "fatal_transport_local_safety_or_dispatch",
    "fatal_returned_model_mismatch", "fatal_local_binding_or_integrity", "fatal_dispatch_not_started"}
EXPECTED_V8 = "05c1d6dfb30ff428d38a1e04f81d50625030089c3755eeb5735e5e87dc528a7e"
EXPECTED_V7 = "d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8"
EXPECTED_V7_STOPPED_REPORT = "f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20"
EXPECTED_V7_DIAGNOSTIC = "0f75fa4b4cccc9f60930dd8a7e3ff0429b9014c536a1a04983831a9bf29bc166"
EXPECTED_V7_DIAGNOSTIC_OWNER = BASE / "cybercrime-v7-seed-technical-view-20261023-v1"
EXPECTED_REVALIDATION_RESPONSES = sorted((
    "a1e204ed2ef0f53206010ccef7651690390abc0948733a75c34d02c6b9832058",
    "4bcaddab4935178f1cf58425b8243b43992c1d0f1c56d1a400d6c62cfbc74166",
    "c316137bea2e6619086598bf83a6272a7e1a0fcb6580a0bf9838b44fc1d27ade"))
EXPECTED_NORMALIZATION = "seed-question-map-in-retained-request-list-order-v1"
EXPECTED_SOURCE_ERROR = "ResearchError:dossier_card_decision_binding_mismatch"
EXPECTED_V5_DIAGNOSTIC = "c3f0fc25655d655566371c9cbc0d1446ae7615c1681721d5cf22fe6c5bef1ea9"
EXPECTED_DIAGNOSTIC = "3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3"
EXPECTED_DIAGNOSTIC_REPAIR = "d96adb1244b7d101c5a90ec5c1b607e55aca8c1c971dbb51d788a9f06c30dd05"
EXPECTED_DOCUMENTS = 6691
EXPECTED_ARTICLES = 7743
CAP_NANOUSD = 50_000_000_000
V4_ALLOCATION = {"main_cap_nanousd": 35_000_000_000, "audit_cap_nanousd": 15_000_000_000,
                 "prior_audit_cap_nanousd": 10_000_000_000, "contingency_to_audit_nanousd": 5_000_000_000,
                 "contingency_nanousd": 0}
V5_ALLOCATION = {"main_cap_nanousd": 35_000_000_000, "audit_cap_nanousd": 15_000_000_000,
                 "contingency_nanousd": 0}
V6_ALLOCATION = {**V5_ALLOCATION, "pilot_main_cap_nanousd": 1_000_000_000,
                 "pilot_audit_cap_nanousd": 2_500_000_000}
FRESH_SECONDS = 300
ALLOWED_RECORDS = {"cyber_dossier_plan", "cyber_dossier_first_launch", "cyber_dossier_report",
                   "cyber_dossier_execution_amendment", "cyber_dossier_execution_amendment_v3",
                   "cyber_dossier_execution_amendment_v4", "cyber_summary_fidelity_diagnostic_plan",
                   "cyber_dossier_execution_amendment_v5",
                   "cyber_dossier_execution_amendment_v6",
                   "cyber_dossier_execution_amendment_v7",
                   "cyber_dossier_execution_amendment_v8",
                   "cyber_dossier_execution_amendment_v9",
                   "cyber_dossier_execution_amendment_v10",
                   "cyber_dossier_execution_amendment_v11",
                   "cyber_summary_fidelity_diagnostic_report",
                   "cyber_summary_fidelity_diagnostic_amendment_v2",
                   "cyber_summary_fidelity_diagnostic_report_v2"}
DIAGNOSTIC_RUNNER = "run_summary_fidelity_diagnostic.py"
DIAGNOSTIC_REPAIR_RUNNER = "run_summary_fidelity_diagnostic_v2.py"
DIAGNOSTIC_RUNNERS = {DIAGNOSTIC_RUNNER, DIAGNOSTIC_REPAIR_RUNNER}
DIAGNOSTIC_PHASES = {DIAGNOSTIC_RUNNER: "summary_fidelity_audit",
                     DIAGNOSTIC_REPAIR_RUNNER: "summary_fidelity_audit_v2"}
ADMINISTRATIVE_ACTIONS = {"prepare", "amend", "report"}


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
        # CIM supplies actual Python processes; reject code/module arguments that
        # merely contain a quoted example of one of these script commands.
        executable = re.match(r"^\s*(?:\"[^\"]*python\.exe\"|'[^']*python\.exe'|[^\s\"']*python\.exe)\s+", command)
        if not executable:
            continue
        arguments = command[executable.end():]
        invocation = re.match(r"^(?:(?:-u|-b|-i|-e|-s)\s+)*(?:\"([^\"]+)\"|'([^']+)'|([^\s\"']+))\s+(prepare|amend|report|pilot|run)(?:\s|$)", arguments)
        if not invocation:
            continue
        script = next(v for v in invocation.groups()[:3] if v is not None).rsplit("/", 1)[-1]
        run = re.fullmatch(r"(run_dossiers(?:_v(?:[23456789]|10|11))?\.py|run_summary_fidelity_diagnostic(?:_v2)?\.py):(prepare|amend|report|pilot|run)", script + ":" + invocation.group(4))
        if run and (run.group(1) in DIAGNOSTIC_RUNNERS or run.group(1) in {"run_dossiers_v7.py", "run_dossiers_v8.py", "run_dossiers_v9.py", "run_dossiers_v10.py", "run_dossiers_v11.py"}) and run.group(2) == "pilot":
            continue
        if run and ((run.group(2) == "prepare" and run.group(1) not in {"run_dossiers.py", *DIAGNOSTIC_RUNNERS})
                    or (run.group(2) == "amend" and run.group(1) in {"run_dossiers.py", *DIAGNOSTIC_RUNNERS})):
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
            administrative = run.group(2) in ADMINISTRATIVE_ACTIONS
            matched.append({**item, "action": run.group(2), "runner": run.group(1), "uses_default_owner": default,
                            "administrative_writer": administrative, "paid_worker": not administrative,
                            "worker_kind": "administrative" if administrative else "summary_diagnostic" if run.group(1) in DIAGNOSTIC_RUNNERS else "dossier"})
    parents = {item["parent_pid"] for item in matched}
    for item in matched:
        item["worker_leaf"] = item["pid"] not in parents
    return sorted(matched, key=lambda item: (item["created_at"], item["pid"]))


def workers(owner):
    script = r"""$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'run_dossiers(?:_v(?:[23456789]|10|11))?\.py|run_summary_fidelity_diagnostic(?:_v2)?\.py'
} | ForEach-Object { @{pid=$_.ProcessId; parent_pid=$_.ParentProcessId;
    created_at=$_.CreationDate.ToUniversalTime().ToString('o');
    executable_path=$_.ExecutablePath; command_line=$_.CommandLine} })
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True,
                            text=True, timeout=20, check=True)
    return matching_processes(json.loads(result.stdout), owner)


def validate_progress(progress, plan, *, cap_nanousd=CAP_NANOUSD):
    if progress is None:
        return
    if (progress.get("input_manifest") != plan["input_manifest"]
            or progress.get("unique_documents") != EXPECTED_DOCUMENTS
            or progress.get("selected_articles") != EXPECTED_ARTICLES
            or progress.get("cap_nanousd") != cap_nanousd
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
    administrative = [p for p in leaves if p.get("action") in ADMINISTRATIVE_ACTIONS]
    if administrative:
        remaining_runtime = max(0, (timestamp(deadline) - now).total_seconds()) if deadline else None
        return {"state": "administrative_writer_active" if len(leaves) == 1 else "multiple_writers_needs_investigation",
            "checkpoint_matches_current_execution": False, "execution_identity": identity,
            "checkpoint_age_seconds": round(age, 2) if age is not None else None,
            "checkpoint_fresh": age is not None and -5 <= age <= FRESH_SECONDS,
            "phase_tasks_completed": None, "phase_tasks_planned": None, "phase_tasks_remaining": None,
            "phase_tasks_per_minute": None, "phase_rate_window_seconds": None,
            "phase_eta_seconds": None, "phase_estimated_finish_amsterdam": None,
            "phase_eta_blocker": "administrative_writer_active" if len(leaves) == 1 else "multiple_matching_python_writers",
            "whole_pipeline_eta_seconds": None, "whole_pipeline_eta_blocker": "administrative_operation_is_not_pipeline_progress",
            "deadline": deadline, "remaining_runtime_seconds": remaining_runtime,
            "deadline_expired": remaining_runtime == 0, "phase_finish_after_deadline": None,
            "eta_scope": "Administrative preparation/amendment/report has no paid-worker phase rate or ETA; retained checkpoint is historical."}
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
    operational = progress.get("operational_continuation") if progress else None
    if current and not diagnostic_active and operational:
        if operational.get("guard_reason") or operational.get("operational_status") == "stopped":
            blocker = "operational_guard_stopped"
            if status == "running":
                status = "operational_guard_worker_exiting"
        elif operational.get("operational_status") == "cooldown":
            blocker = "operational_cooldown"
            if status == "running":
                status = "running_operational_cooldown"
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


def effective_deadline_context(original_deadline, v10, processes, now, v11=None):
    """A later registration cannot change the behavior of a still-running older executable."""
    leaves = [p for p in processes if p["worker_leaf"]]
    v10_applies = bool(v10 and not any(p.get("runner") != "run_dossiers_v10.py" for p in leaves))
    v11_applies = bool(v11 and not any(p.get("runner") != "run_dossiers_v11.py" for p in leaves))
    applies = v11_applies or v10_applies
    return {
        "original_admission_deadline": original_deadline,
        "original_deadline_elapsed": bool(original_deadline and timestamp(original_deadline) <= now),
        "effective_admission_deadline": None if applies else original_deadline,
        "effective_deadline_mode": DEADLINE_POLICY["mode"] if applies else "original_fixed_deadline",
        "registered_deadline_policy": (v11 or v10 or {}).get("deadline_policy"),
        "v10_deadline_policy_applies": v10_applies,
        "v11_deadline_policy_applies": v11_applies,
        "deadline_meaning": ("No date cutoff for the frozen pipeline under its registered cumulative budget, STOP, no-retry and operational guards. Original deadline is historical only." if applies else
            "The actual earlier worker remains governed by its original fixed deadline; later registration does not alter that process.")}


def report_is_current(report, plan, response_state, progress, processes):
    if not report or processes:
        return False
    return bool(report.get("plan") == plan["_record_id"]
        and report.get("stored_responses") == response_state["responses"]
        and report.get("_created_event", -1) > (response_state["last_response_event"] or -1)
        and report.get("_created_event", -1) > (response_state.get("last_attempt_event") or -1)
        and report.get("_created_event", -1) > (response_state.get("last_revalidation_event") or -1)
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
                   diagnostic_repair=None, repair_report=None, v5=None, parent_report=None,
                   v6=None, parent_v5_report=None, v7=None, passed_v6_report=None, stopped_v6_report=None,
                   passed_v6_gate=None, v8=None, stopped_v7_report=None, v9=None, stopped_v8_report=None, v10=None, stopped_v9_report=None):
    if plan["_record_id"] != EXPECTED_PLAN:
        raise AuditError("dossier_monitor_original_plan_identity")
    validate_amendment(v2, plan, deadline)
    if v2 and v2["_record_id"] != EXPECTED_V2:
        raise AuditError("dossier_monitor_v2_identity")
    if v3 and v3["_record_id"] != EXPECTED_V3:
        raise AuditError("dossier_monitor_v3_identity")
    if v4 and v4["_record_id"] != EXPECTED_V4:
        raise AuditError("dossier_monitor_v4_identity")
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
    if v5 and (v4 is None or parent_report is None
            or v5.get("ancestor_execution_amendments") != {
                "v2": v2["_record_id"], "v3": v3["_record_id"], "v4": v4["_record_id"]}
            or v5.get("parent_report") != parent_report["_record_id"]
            or parent_report.get("execution_amendment") != v4["_record_id"]
            or parent_report.get("plan") != plan["_record_id"]
            or any(v5.get(k) != expected for k, expected in V5_ALLOCATION.items())
            or v5.get("card_reference_minimum") != 6 or v5.get("card_reference_target") != 10
            or any(v5.get(k) != v4.get(k) for k in ("diagnostic_plan", "diagnostic_amendment", "diagnostic_report"))):
        raise AuditError("dossier_monitor_v5_parent_or_allocation_scope")
    if v6 and (v5 is None or v5["_record_id"] != EXPECTED_V5 or parent_v5_report is None
            or parent_v5_report["_record_id"] != EXPECTED_V5_REPORT
            or v6.get("parent_report") != parent_v5_report["_record_id"]
            or parent_v5_report.get("execution_amendment") != v5["_record_id"]
            or parent_v5_report.get("plan") != plan["_record_id"]
            or v6.get("ancestor_execution_amendments") != {
                "v2": v2["_record_id"], "v3": v3["_record_id"], "v4": v4["_record_id"], "v5": v5["_record_id"]}
            or any(v6.get(key) != value for key, value in V6_ALLOCATION.items())
            or v6.get("minimum_incoming_articles") != 6
            or (v6.get("v5_diagnostic") or {}).get("record_id") != EXPECTED_V5_DIAGNOSTIC
            or not isinstance((v6.get("v5_diagnostic") or {}).get("owner"), str)):
        raise AuditError("dossier_monitor_v6_parent_or_reanalysis_scope")
    if v7:
        if (v6 is None or v6["_record_id"] != EXPECTED_V6
                or passed_v6_report is None or passed_v6_report["_record_id"] != EXPECTED_V6_PASSED_REPORT
                or stopped_v6_report is None or stopped_v6_report["_record_id"] != EXPECTED_V6_STOPPED_REPORT
                or v7.get("passed_pilot_report") != passed_v6_report["_record_id"]
                or v7.get("parent_report") != stopped_v6_report["_record_id"]
                or any(r.get("plan") != plan["_record_id"] or r.get("execution_amendment") != v6["_record_id"]
                       for r in (passed_v6_report, stopped_v6_report))
                or v7.get("ancestor_execution_amendments") != {
                    "v2": v2["_record_id"], "v3": v3["_record_id"], "v4": v4["_record_id"],
                    "v5": v5["_record_id"], "v6": v6["_record_id"]}
                or any(v7.get(key) != value for key, value in V6_ALLOCATION.items())
                or v7.get("minimum_incoming_articles") != 6
                or not isinstance(v7.get("seed_capacity_census"), dict)
                or not isinstance(v7.get("seed_packet_plan_artifact"), str)
                or v7.get("v6_pilot_budget_baseline") != {"legacy_response_keys": v6.get("legacy_response_keys"),
                    "legacy_unresolved_attempts": v6["legacy_unresolved_attempts"]}):
            raise AuditError("dossier_monitor_v7_parent_or_capacity_scope")
        validate_seed_capacity(v7["seed_capacity_census"])
        gate = passed_v6_report.get("pilot_gate")
        if (not isinstance(gate, dict) or gate.get("passed") is not True
                or stopped_v6_report.get("pilot_gate") != gate or passed_v6_gate is None
                or v7.get("passed_gate_record") != passed_v6_gate["record"]["_record_id"]
                or passed_v6_gate["record"].get("name") != "pilot_v6_gate"
                or passed_v6_gate["record"].get("plan") != plan["_record_id"]
                or passed_v6_gate["record"].get("execution_amendment") != v6["_record_id"]
                or passed_v6_gate["value"] != gate):
            raise AuditError("dossier_monitor_v7_passed_gate_binding")
    validate_v8_extension(v8, v7, stopped_v7_report, plan)
    validate_v9_extension(v9, v8, stopped_v8_report, plan)
    validate_v10_extension(v10, v9, stopped_v9_report, plan)
    previous = None
    for amendment, parent in ((v2, None), (v3, v2), (v4, v3), (v5, v4), (v6, v5), (v7, v6), (v8, v7), (v9, v8), (v10, v9)):
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
    if v5:
        validate_current_liabilities(parent_report, v4)
        if any(v5["legacy_budget"][key] < parent_report[key] for key in
               ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
            raise AuditError("dossier_monitor_v5_parent_report_liability_reduced")
    if v6:
        validate_current_liabilities(parent_v5_report, v5)
        if any(v6["legacy_budget"][key] < parent_v5_report[key] for key in
               ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
            raise AuditError("dossier_monitor_v6_parent_report_liability_reduced")
    if v7:
        for report in (passed_v6_report, stopped_v6_report):
            validate_current_liabilities(report, v6)
            if any(v7["legacy_budget"][key] < report[key] for key in
                   ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
                raise AuditError("dossier_monitor_v7_parent_report_liability_reduced")
    if v8:
        validate_current_liabilities(stopped_v7_report, v7)
        if any(v8["legacy_budget"][key] < stopped_v7_report[key] for key in
               ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
            raise AuditError("dossier_monitor_v8_parent_report_liability_reduced")
    if v9:
        validate_current_liabilities(stopped_v8_report, v8)
        if any(v9["legacy_budget"][key] < stopped_v8_report[key] for key in
               ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
            raise AuditError("dossier_monitor_v9_parent_report_liability_reduced")
    return verify_implementations(plan, v2, v3, v4, v5, v6, v7, v8, v9, v10, diagnostic, diagnostic_repair)


def validate_v10_extension(v10, v9, parent_report, plan, *, cumulative_budget=False):
    if v10 is None:
        return
    preserved = ("seed_capacity_census", "seed_packet_plan_artifact", "seed_proposals_sha256",
        "passed_pilot_report", "passed_gate_record", "v6_pilot_budget_baseline", "diagnostic", "technical_diagnostic",
        "eligible_source_response_ids", "source_validation_error", "normalization_version",
        "derived_revalidation_records", "seed_order_integrity", "operational_policy", "transport_observability")
    if (v9 is None or v9["_record_id"] != EXPECTED_V9 or parent_report is None
            or v10.get("parent_report") != parent_report["_record_id"]
            or parent_report.get("plan") != plan["_record_id"]
            or parent_report.get("execution_amendment") != v9["_record_id"]
            or parent_report.get("technical_extension_version") != 9
            or v10.get("ancestor_execution_amendments") != {
                **v9["ancestor_execution_amendments"], "v9": v9["_record_id"]}
            or any(v10.get(key) != v9.get(key) for key in preserved)
            or any(v10.get(key) != value for key, value in V6_ALLOCATION.items()
                   if not cumulative_budget or key not in {"main_cap_nanousd", "audit_cap_nanousd"})
            or v10.get("minimum_incoming_articles") != 6
            or digest(v10.get("deadline_policy")) != digest(DEADLINE_POLICY)
            or "effective_admission_deadline" not in v10 or v10["effective_admission_deadline"] is not None
            or v10.get("operational_origin_amendment") != v9["_record_id"]
            or v10.get("health_ancestor_amendments") != [v9["_record_id"]]
            or v10.get("operational_health_baseline_unresolved_attempts") != v9["legacy_unresolved_attempts"]):
        raise AuditError("dossier_monitor_v10_parent_or_deadline_scope")
    if (parent_report.get("seed_order_integrity") != v9["seed_order_integrity"]
            or (parent_report.get("seed_capacity") or {}).get("frozen_census") != v9["seed_capacity_census"]):
        raise AuditError("dossier_monitor_v10_parent_technical_scope_changed")
    validate_seed_revalidation(parent_report.get("seed_revalidation"), v9,
                               len(v9["derived_revalidation_records"]))
    validate_current_liabilities(parent_report, v9)
    validate_operational_continuation(parent_report.get("operational_continuation"), v9,
                                     parent_report["stored_responses"])
    validate_category_budget(parent_report.get("category_budget"), parent_report)
    if any(v10.get("legacy_budget", {}).get(key) != parent_report.get(key) for key in
           ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")):
        raise AuditError("dossier_monitor_v10_baseline_not_parent_report")
    authorization = v10.get("deadline_authorization")
    if (not isinstance(authorization, dict)
            or set(authorization) != {"artifact", "sha256", "source_reference", "source_timestamp", "registered_at"}
            or not isinstance(authorization["artifact"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", authorization["artifact"])
            or authorization["artifact"] != authorization["sha256"]
            or not isinstance(authorization["source_reference"], str) or not authorization["source_reference"].strip()
            or not isinstance(v10.get("versions", {}).get("policy"), str) or not v10["versions"]["policy"]):
        raise AuditError("dossier_monitor_v10_authorization_binding")
    timestamp(authorization["registered_at"])
    if authorization["source_timestamp"] is not None:
        timestamp(authorization["source_timestamp"])


def validate_v10_snapshot(value, v10, *, checkpoint=False):
    if (value.get("original_deadline") != v10["original_deadline"]
            or "effective_admission_deadline" not in value or value["effective_admission_deadline"] is not None
            or digest(value.get("deadline_policy")) != digest(DEADLINE_POLICY)
            or value.get("deadline_authorization_policy") != v10["versions"]["policy"]
            or value.get("operational_origin_amendment") != v10["operational_origin_amendment"]
            or value.get("health_response_amendments") != [*v10["health_ancestor_amendments"], v10["_record_id"]]
            or checkpoint and ("deadline" not in value or value["deadline"] is not None)):
        raise AuditError("dossier_monitor_v10_snapshot_policy_or_health_binding")


HISTORICAL_CAPS = {"total": CAP_NANOUSD, "main": 35_000_000_000, "audit": 15_000_000_000}
V11_METHOD = "cybercrime-four-process-dossiers-20261023-v11"


def validate_budget_policy(policy):
    caps = policy.get("effective_caps_nanousd") if isinstance(policy, dict) else None
    if (not isinstance(caps, dict) or set(caps) != set(HISTORICAL_CAPS)
            or any(type(caps[k]) is not int or caps[k] < HISTORICAL_CAPS[k] for k in caps)
            or caps["total"] <= CAP_NANOUSD or caps["main"] + caps["audit"] != caps["total"]):
        raise AuditError("dossier_monitor_v11_numeric_allocation")
    expected = {"version": "cumulative-user-budget-amendment-v1",
        "historical_caps_nanousd": HISTORICAL_CAPS, "effective_caps_nanousd": caps,
        "cumulative": True, "reset_costs_or_holds": False, "automatic_reallocation": False,
        "new_models_or_questions_authorized": False}
    if digest(policy) != digest(expected):
        raise AuditError("dossier_monitor_v11_budget_policy_changed")
    return caps


def validate_v11_extension(v11, v9, parent_report, plan):
    if v11 is None:
        return
    caps = validate_budget_policy(v11.get("budget_policy"))
    validate_v10_extension(v11, v9, parent_report, plan, cumulative_budget=True)
    if (v11.get("method") != V11_METHOD or v11.get("parent_plan") != plan["_record_id"]
            or v11.get("parent_execution_amendment") != v9["_record_id"]
            or v11.get("parent_implementation") != v9["implementation"]
            or v11.get("original_deadline") != v9["original_deadline"]
            or v11.get("cap_nanousd") != caps["total"]
            or v11.get("main_cap_nanousd") != caps["main"]
            or v11.get("audit_cap_nanousd") != caps["audit"]
            or any(type(v11.get(k)) is not int for k in ("cap_nanousd", "main_cap_nanousd", "audit_cap_nanousd"))
            or {"total": v9.get("cap_nanousd"), "main": v9.get("main_cap_nanousd"),
                "audit": v9.get("audit_cap_nanousd")} != HISTORICAL_CAPS
            or v11.get("legacy_category_budget") != parent_report.get("category_budget")):
        raise AuditError("dossier_monitor_v11_parent_or_budget_scope")
    attempts, budget = v11.get("legacy_unresolved_attempts"), v11.get("legacy_budget")
    if (not isinstance(attempts, list) or any(not isinstance(a, str) or not a for a in attempts)
            or len(set(attempts)) != len(attempts) or not isinstance(budget, dict)):
        raise AuditError("dossier_monitor_v11_liability_identity")
    validate_budget(budget)
    if (len(attempts) != budget["unresolved_holds"]
            or not set(v9["legacy_unresolved_attempts"]) <= set(attempts)
            or budget["committed_nanousd"] > caps["total"]
            or any(parent_report["category_budget"][k]["committed_nanousd"] > caps[k]
                   for k in ("main", "audit"))):
        raise AuditError("dossier_monitor_v11_liability_reduced_or_over_cap")
    auth = v11.get("budget_authorization")
    if (not isinstance(auth, dict) or set(auth) != {
            "artifact", "sha256", "source_reference", "source_timestamp", "registered_at", "caps_nanousd"}
            or not isinstance(auth["artifact"], str) or not re.fullmatch(r"[0-9a-f]{64}", auth["artifact"])
            or auth["artifact"] != auth["sha256"] or digest(auth["caps_nanousd"]) != digest(caps)
            or not isinstance(auth["source_reference"], str) or not auth["source_reference"].strip()):
        raise AuditError("dossier_monitor_v11_budget_authorization_binding")
    timestamp(auth["registered_at"])
    if auth["source_timestamp"] is not None:
        timestamp(auth["source_timestamp"])


def validate_v11_snapshot(value, amendment, *, checkpoint=False):
    validate_v10_snapshot(value, amendment, checkpoint=checkpoint)
    caps = validate_budget_policy(value.get("budget_policy"))
    if (digest(value["budget_policy"]) != digest(amendment["budget_policy"])
            or digest(value.get("historical_caps_nanousd")) != digest(HISTORICAL_CAPS)
            or digest(value.get("effective_caps_nanousd")) != digest(caps)
            or value.get("cap_nanousd") != caps["total"]
            or value.get("budget_authorization_policy") != amendment["versions"]["policy"]):
        raise AuditError("dossier_monitor_v11_snapshot_budget_binding")


def effective_budget_context(v11, processes):
    leaves = [p for p in processes if p.get("worker_leaf")]
    applies = bool(v11 and not any(p.get("runner") != "run_dossiers_v11.py" for p in leaves))
    registered = v11["budget_policy"]["effective_caps_nanousd"] if v11 else None
    caps = registered if applies else HISTORICAL_CAPS
    return {"historical_caps_nanousd": HISTORICAL_CAPS, "effective_caps_nanousd": caps,
        "registered_effective_caps_nanousd": registered, "v11_budget_policy_applies": applies,
        "budget_usd": caps["total"] / 1e9, "historical_budget_usd": CAP_NANOUSD / 1e9}


def validate_v9_extension(v9, v8, parent_report, plan):
    """Operational policy can change neither the inherited study nor its liabilities."""
    if v9 is None:
        return
    preserved = ("seed_capacity_census", "seed_packet_plan_artifact", "seed_proposals_sha256",
        "passed_pilot_report", "passed_gate_record", "v6_pilot_budget_baseline", "diagnostic",
        "eligible_source_response_ids", "source_validation_error", "normalization_version",
        "derived_revalidation_records", "seed_order_integrity")
    diagnostic = v9.get("technical_diagnostic") or {}
    if (v8 is None or v8["_record_id"] != EXPECTED_V8
            or parent_report is None or parent_report["_record_id"] != EXPECTED_V8_STOPPED_REPORT
            or v9.get("parent_report") != parent_report["_record_id"]
            or parent_report.get("plan") != plan["_record_id"]
            or parent_report.get("execution_amendment") != v8["_record_id"]
            or parent_report.get("technical_extension_version") != 8
            or v9.get("ancestor_execution_amendments") != {
                **v8["ancestor_execution_amendments"], "v8": v8["_record_id"]}
            or any(v9.get(key) != v8.get(key) for key in preserved)
            or any(v9.get(key) != value for key, value in V6_ALLOCATION.items())
            or v9.get("minimum_incoming_articles") != 6
            or v9.get("operational_policy") != OPERATIONAL_POLICY
            or v9.get("transport_observability") != "dossier-transport-fixed-stage-codes-v1"
            or diagnostic.get("record_id") != EXPECTED_V8_DIAGNOSTIC
            or not isinstance(diagnostic.get("owner"), str)
            or Path(diagnostic["owner"]).resolve() != EXPECTED_V8_DIAGNOSTIC_OWNER.resolve()
            or v9.get("legacy_budget", {}).get("unresolved_holds") != EXPECTED_V9_BASELINE_HOLDS
            or parent_report.get("unresolved_holds") != EXPECTED_V9_BASELINE_HOLDS):
        raise AuditError("dossier_monitor_v9_parent_or_operational_scope")
    if (parent_report.get("seed_order_integrity") != v8["seed_order_integrity"]
            or (parent_report.get("seed_capacity") or {}).get("frozen_census") != v8["seed_capacity_census"]):
        raise AuditError("dossier_monitor_v9_parent_technical_scope_changed")
    validate_seed_revalidation(parent_report.get("seed_revalidation"), v8,
                               len(v8["derived_revalidation_records"]))
    for key in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"):
        if v9["legacy_budget"].get(key) != parent_report.get(key):
            raise AuditError("dossier_monitor_v9_baseline_not_parent_report")


def validate_operational_continuation(value, amendment, provider_responses):
    """Strict metadata projection; technical categories are not semantic judgments."""
    numeric = {"outcomes", "provider_responses", "unreturned_intents", "mechanically_parsed", "invalid",
        "held_or_transport_unknown", "window_size", "window_failures", "window_transport_unknown",
        "consecutive_failures", "legacy_guard_continuations", "baseline_unresolved_holds"}
    keys = numeric | {"guard_reason", "policy_sha256", "scope", "operational_status", "cooldown_until"}
    extended = "health_ancestor_amendments" in amendment
    expected_scope = (V11_HEALTH_SCOPE if amendment.get("method") == "cybercrime-four-process-dossiers-20261023-v11"
                      else V10_HEALTH_SCOPE if extended else OPERATIONAL_SCOPE)
    baseline = amendment["operational_health_baseline_unresolved_attempts"] if extended else amendment["legacy_unresolved_attempts"]
    if (not isinstance(value, dict) or set(value) != keys
            or any(type(value[k]) is not int or value[k] < 0 for k in numeric)
            or value["policy_sha256"] != digest(amendment["operational_policy"])
            or value["scope"] != expected_scope
            or value["baseline_unresolved_holds"] != len(baseline)
            or value["baseline_unresolved_holds"] != EXPECTED_V9_BASELINE_HOLDS
            or value["outcomes"] != value["provider_responses"] + value["unreturned_intents"]
            or value["provider_responses"] > provider_responses
            or value["mechanically_parsed"] + value["invalid"] > value["provider_responses"]
            or value["mechanically_parsed"] + value["invalid"] + value["held_or_transport_unknown"] != value["outcomes"]
            or value["held_or_transport_unknown"] > value["outcomes"]
            or value["held_or_transport_unknown"] < value["unreturned_intents"]
            or value["window_size"] != min(value["outcomes"], OPERATIONAL_POLICY["window"])
            or value["window_failures"] > value["window_size"]
            or value["window_transport_unknown"] > min(value["window_size"], value["held_or_transport_unknown"])
            or value["consecutive_failures"] > value["outcomes"] - value["mechanically_parsed"]
            or value["legacy_guard_continuations"] > value["provider_responses"]):
        raise AuditError("dossier_monitor_operational_projection_invalid")
    expected = (
        "sustained_consecutive_failures" if value["consecutive_failures"] >= OPERATIONAL_POLICY["consecutive_failure_limit"] else
        "sustained_transport_unknown_window" if value["window_transport_unknown"] >= OPERATIONAL_POLICY["window_transport_unknown_limit"] else
        "sustained_failed_window" if value["window_failures"] >= OPERATIONAL_POLICY["window_failure_limit"] else None)
    if value["guard_reason"] not in FATAL_GUARD_REASONS and value["guard_reason"] != expected:
        raise AuditError("dossier_monitor_operational_guard_inconsistent")
    status, cooldown = value["operational_status"], value["cooldown_until"]
    if (status not in {"ready", "cooldown", "stopped"}
            or (status == "stopped") != bool(value["guard_reason"])
            or status == "cooldown" and cooldown is None
            or cooldown is not None and not isinstance(cooldown, str)):
        raise AuditError("dossier_monitor_operational_status_invalid")
    if cooldown is not None:
        timestamp(cooldown)
    return value


def validate_category_budget(value, totals, allocation=None):
    if not isinstance(value, dict) or set(value) != {"main", "audit"}:
        raise AuditError("dossier_monitor_category_budget_invalid")
    amounts = {"settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"}
    allocation = allocation or V5_ALLOCATION
    for category, cap in (("main", allocation["main_cap_nanousd"]), ("audit", allocation["audit_cap_nanousd"])):
        item = value[category]
        if (not isinstance(item, dict) or set(item) != amounts | {"cap_nanousd", "remaining_nanousd"}
                or any(type(v) is not int or v < 0 for v in item.values())
                or item["cap_nanousd"] != cap
                or item["remaining_nanousd"] != max(0, cap - item["committed_nanousd"])):
            raise AuditError("dossier_monitor_category_budget_invalid")
        validate_budget(item)
    if any(sum(value[cat][key] for cat in value) != totals[key] for key in amounts):
        raise AuditError("dossier_monitor_category_budget_sum")
    return value


def validate_v8_extension(v8, v7, parent_report, plan):
    """Bind the local parser repair without reading packets or provider outputs."""
    if v8 is None:
        return
    preserved = ("seed_capacity_census", "seed_packet_plan_artifact", "seed_proposals_sha256",
                 "passed_pilot_report", "passed_gate_record", "v6_pilot_budget_baseline")
    diagnostic = v8.get("diagnostic") or {}
    originals = v8.get("eligible_source_response_ids")
    if (v7 is None or v7["_record_id"] != EXPECTED_V7
            or parent_report is None or parent_report["_record_id"] != EXPECTED_V7_STOPPED_REPORT
            or v8.get("parent_report") != parent_report["_record_id"]
            or parent_report.get("plan") != plan["_record_id"]
            or parent_report.get("execution_amendment") != v7["_record_id"]
            or parent_report.get("technical_extension_version") != 7
            or v8.get("ancestor_execution_amendments") != {
                **v7["ancestor_execution_amendments"], "v7": v7["_record_id"]}
            or any(v8.get(key) != v7.get(key) for key in preserved)
            or any(v8.get(key) != value for key, value in V6_ALLOCATION.items())
            or v8.get("minimum_incoming_articles") != 6
            or diagnostic.get("record_id") != EXPECTED_V7_DIAGNOSTIC
            or not isinstance(diagnostic.get("owner"), str)
            or Path(diagnostic["owner"]).resolve() != EXPECTED_V7_DIAGNOSTIC_OWNER.resolve()
            or not isinstance(originals, list) or len(originals) != 3
            or any(not isinstance(value, str) or not value for value in originals)
            or len(set(originals)) != 3 or originals != EXPECTED_REVALIDATION_RESPONSES
            or v8.get("source_validation_error") != EXPECTED_SOURCE_ERROR
            or v8.get("normalization_version") != EXPECTED_NORMALIZATION
            or not isinstance(v8.get("derived_revalidation_records"), list)
            or len(v8["derived_revalidation_records"]) != 3
            or any(not isinstance(value, str) or not value for value in v8["derived_revalidation_records"])
            or len(set(v8["derived_revalidation_records"])) != 3):
        raise AuditError("dossier_monitor_v8_parent_or_revalidation_scope")
    validate_seed_order_integrity(v8.get("seed_order_integrity"), v7["seed_capacity_census"])
    capacity = parent_report.get("seed_capacity") or {}
    if capacity.get("frozen_census") != v7["seed_capacity_census"]:
        raise AuditError("dossier_monitor_v8_parent_capacity_changed")
    validate_seed_capacity(capacity["frozen_census"], capacity.get("execution_summary"))


def validate_seed_order_integrity(value, census):
    keys = {"checked_packets", "map_order_restored_packets", "canonical_packet_changes",
            "request_changes", "deferred_packets", "model_calls"}
    if (not isinstance(value, dict) or set(value) != keys
            or any(type(count) is not int or count < 0 for count in value.values())
            or value["checked_packets"] != census["proposed_packets"] - census["deferred_unjudged_packets"]
            or value["map_order_restored_packets"] > value["checked_packets"]
            or value["deferred_packets"] != census["deferred_unjudged_packets"]
            or any(value[key] != 0 for key in ("canonical_packet_changes", "request_changes", "model_calls"))):
        raise AuditError("dossier_monitor_seed_order_integrity_scope")


def validate_seed_revalidation(value, amendment, stored_count):
    """Local derived checks never create provider-response or spending counts."""
    keys = {"attempted", "valid", "still_invalid", "model_calls", "original_rows_unchanged",
            "derived_record_ids"}
    if not isinstance(value, dict) or set(value) != keys:
        raise AuditError("dossier_monitor_seed_revalidation_projection")
    counts = ("attempted", "valid", "still_invalid", "model_calls")
    ids = value["derived_record_ids"]
    if (any(type(value[key]) is not int or value[key] < 0 for key in counts)
            or value["attempted"] != value["valid"] + value["still_invalid"]
            or value["attempted"] > len(amendment["eligible_source_response_ids"])
            or value["model_calls"] != 0 or value["original_rows_unchanged"] is not True
            or not isinstance(ids, list) or len(ids) != value["attempted"]
            or any(not isinstance(identifier, str) or not identifier for identifier in ids)
            or len(set(ids)) != len(ids)
            or ids != amendment["derived_revalidation_records"]
            or type(stored_count) is not int or stored_count != value["attempted"]):
        raise AuditError("dossier_monitor_seed_revalidation_counts_or_scope")


def bound_report(reports, identifier):
    """Select an immutable binding separately from a later observational report."""
    matches = [r for r in reports if r["_record_id"] == identifier]
    if len(matches) != 1:
        raise AuditError("dossier_monitor_bound_diagnostic_report_missing")
    return matches[0]


def validate_seed_capacity(census, execution=None):
    """Only source-free counters and fixed operational meaning may be exposed."""
    fixed = {"token_limit": 32000, "wire_byte_limit": 2097152,
        "article_inputs_or_questions_changed": False, "packets_split": False,
        "deferred_are_provider_unknowns": False, "deferred_billing_holds": 0,
        "later_assignment_and_recovery_eligible": True, "model_calls": 0}
    counts = ("proposed_packets", "reused_prior_attempt_packets", "untouched_fitting_packets",
        "deferred_unjudged_packets", "proposed_distinct_articles", "fitting_or_reused_distinct_articles",
        "deferred_distinct_articles", "intended_within_packet_pairs", "deferred_unasked_within_packet_pairs",
        "deferred_maximum_input_tokens_proxy", "fitting_and_deferred_article_overlap",
        "distinct_intended_within_packet_pairs", "distinct_deferred_unasked_within_packet_pairs")
    if (not isinstance(census, dict) or any(type(value) not in (int, bool) or value < 0 for value in census.values())
            or any(type(census.get(key)) is not type(value) or census.get(key) != value for key, value in fixed.items())
            or any(type(census.get(key)) is not int or census[key] < 0 for key in counts)
            or census["proposed_packets"] != sum(census[key] for key in
                ("reused_prior_attempt_packets", "untouched_fitting_packets", "deferred_unjudged_packets"))
            or census["deferred_unasked_within_packet_pairs"] > census["intended_within_packet_pairs"]
            or census["proposed_distinct_articles"] != census["fitting_or_reused_distinct_articles"]
                + census["deferred_distinct_articles"] - census["fitting_and_deferred_article_overlap"]
            or census["fitting_and_deferred_article_overlap"] > min(census["fitting_or_reused_distinct_articles"], census["deferred_distinct_articles"])
            or census["distinct_intended_within_packet_pairs"] > census["intended_within_packet_pairs"]
            or census["distinct_deferred_unasked_within_packet_pairs"] > min(census["distinct_intended_within_packet_pairs"], census["deferred_unasked_within_packet_pairs"])
            or max(census["fitting_or_reused_distinct_articles"], census["deferred_distinct_articles"])
                > census["proposed_distinct_articles"]):
        raise AuditError("dossier_monitor_seed_capacity_census_scope")
    if execution is not None:
        expected = {"constructed_or_reused_requests": census["proposed_packets"] - census["deferred_unjudged_packets"],
            "capacity_deferred_packets": census["deferred_unjudged_packets"],
            "capacity_deferred_distinct_articles": census["deferred_distinct_articles"],
            "unasked_within_deferred_pairs": census["deferred_unasked_within_packet_pairs"],
            "covered_seed_article_ids_count": census["fitting_or_reused_distinct_articles"],
            "deferred_are_provider_unknowns": False}
        if (not isinstance(execution, dict) or any(type(value) not in (int, bool) or value < 0 for value in execution.values())
                or any(type(execution.get(key)) is not type(value) or execution.get(key) != value for key, value in expected.items())
                or type(execution.get("stored_invalid_or_unknown_seed_packets")) is not int
                or not 0 <= execution["stored_invalid_or_unknown_seed_packets"] <= expected["constructed_or_reused_requests"]):
            raise AuditError("dossier_monitor_seed_capacity_execution_scope")


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

    def passed_v6_gate(self, identifier):
        """Read exactly the source-free gate phase bound by the technical repair."""
        row = self.db.execute("SELECT * FROM records WHERE id=? AND kind=?", (identifier, "cyber_dossier_phase")).fetchone()
        record = state.row_value(row, "cyber_dossier_phase")
        self.artifacts.check(row["artifact"])
        if record.get("name") != "pilot_v6_gate":
            raise AuditError("dossier_monitor_gate_phase_scope")
        value = json.loads(self.artifacts.read(record["artifact"]))
        return {"record": record, "value": value}

    def verify_deadline_policy(self, amendment):
        """Verify only the bound policy and authorization bytes, without projecting private instruction text."""
        identifier = amendment["versions"]["policy"]
        row = self.db.execute("SELECT * FROM records WHERE id=? AND kind=?", (identifier, "policy")).fetchone()
        record = state.row_value(row, "policy")
        self.artifacts.check(row["artifact"])
        content = record.get("content") or {}
        if (digest(content.get("deadline_policy")) != digest(DEADLINE_POLICY)
                or content.get("deadline_evidence") != amendment["deadline_authorization"]
                or content.get("parent_execution_amendment") != amendment["parent_execution_amendment"]
                or content.get("original_deadline") != amendment["original_deadline"]
                or content.get("cap_nanousd") != CAP_NANOUSD
                or content.get("new_models_or_questions_authorized") is not False):
            raise AuditError("dossier_monitor_v10_registered_policy_changed")
        self.artifacts.check(amendment["deadline_authorization"]["artifact"])

    def verify_v11_policy(self, amendment):
        """Bound numeric authority is read privately; only artifact identities leave this reader."""
        row = self.db.execute("SELECT * FROM records WHERE id=? AND kind='policy'",
                              (amendment["versions"]["policy"],)).fetchone()
        record = state.row_value(row, "policy")
        self.artifacts.check(row["artifact"])
        content = record.get("content") or {}
        if (digest(content.get("deadline_policy")) != digest(DEADLINE_POLICY)
                or digest(content.get("budget_policy")) != digest(amendment["budget_policy"])
                or content.get("deadline_evidence") != amendment["deadline_authorization"]
                or content.get("budget_evidence") != amendment["budget_authorization"]
                or content.get("parent_execution_amendment") != amendment["parent_execution_amendment"]
                or content.get("original_deadline") != amendment["original_deadline"]
                or content.get("cap_nanousd") != amendment["cap_nanousd"]
                or content.get("new_models_or_questions_authorized") is not False):
            raise AuditError("dossier_monitor_v11_registered_policy_changed")
        for field in ("deadline_authorization", "budget_authorization"):
            auth = amendment[field]
            raw = self.artifacts.read(auth["artifact"])
            parsed = json.loads(raw)
            expected_keys = {"instruction", "source_reference", "source_timestamp"}
            if field == "budget_authorization":
                expected_keys.add("caps_nanousd")
            if (hashlib.sha256(raw).hexdigest() != auth["sha256"]
                    or not isinstance(parsed, dict) or set(parsed) != expected_keys
                    or not isinstance(parsed["instruction"], str) or not parsed["instruction"].strip()
                    or any(digest(parsed[key]) != digest(auth[key])
                           for key in expected_keys - {"instruction"})):
                raise AuditError("dossier_monitor_v11_private_evidence_changed")

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
        paths = [Path(__file__), ROOT / "research/cybercrime_nl/runtime/check_dossier_progress_v11.py",
                 ROOT / "scripts/lean_luna_state.py",
                 ROOT / "workbench/check_luna_decisions_incident_progress.py"]
        code = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        versions = {}
        definitions = {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Read only fixed owner's source-free operational records via read-only SQLite, verifying selected projection and artifact hashes. Recognize exact original/v2-v11 and diagnostic Python commands, owner, PID creation times and leaf processes. Prepare/amend/report are administrative writers, including amendment preflight before registration; they suppress current-report claims and all phase timing. Run/pilot retain registration requirements. Administrative recognition does not authorize model dispatch. The frozen V11 observer remains unchanged; this separate version binds its copied implementation and corrections. An active diagnostic is a writer, prevents current dossier-report claims and suppresses dossier ETA. Verify original/v2/v3/v4/v5 identity, v5/v6 parent-report and diagnostic-plan chain, unchanged implementation files, original deadline/total cap and cumulative hold/cost lineage including diagnostic costs. Preserve the explicit35main/15audit allocation and all old subcaps; the v5/v6 baselines cannot be below their bound parent reports. Preserve v6 pilot subcaps of USD1 main and USD2.50 audit inside the unchanged category limits. Never replace plans or release holds. Read mutable checkpoints with Windows share-read/write/delete. When stopped, validate latest reports against response and attempt event boundaries, amendment and published report ID. Expose the current amendment gate/outcome only from its current report. V6 is adaptive fixed-v5 reanalysis; distinguish new expanded-group primary review and descriptive secondary hypotheses from reused historical v5 evidence. Group-dependent accepted article counts are not independent accuracy cases. Distinguish usable exact-source cards from historical generated summaries and keep the separate full-bundle control descriptive, with no acceptance effect. Expose processing completion separately from final audit completion. Retain observation in a distinct protected monitor owner with this new method version. No worker writes, packet/source reads, model calls or restart. Phase ETA needs comparable deltas in the same PID/creation/phase/queue/amendment; whole-pipeline ETA remains unknown. V7 binds the passed v6 report and later stopped report, preserves the semantic v6 gate and phases, and exposes explicit local seed-capacity deferrals as unjudged/not attempted rather than provider unknowns or holds; no new semantic pilot. V8 binds the stopped v7 report and technical diagnosis, preserves that census and gate, and projects local derived revalidation separately from provider response counts, costs, holds and phase throughput. Original response rows and artifacts remain unchanged. V9 additionally binds the stopped v8 report, recurrence diagnosis and fixed operational health policy. It exposes durable source-free v9 outcome counts including orphan intents, separately from provider-response counts and all19 baseline holds. Cooldown and sustained/fatal guard states suppress ETA; no worker restart or retry is performed. V10 preserves the original deadline historically and binds an explicit private user authorization and policy to complete the frozen queue without a date cutoff under unchanged budget/STOP/no-retry guards. Only a registered v10 executable or stopped v10 state uses that effective policy; an actual older worker retains its historical cutoff. Durable health includes both v9 and v10 with the original19-hold health baseline, separately from the later v10 admission-liability baseline. Verify the exact authorization policy and artifact hash without projecting private instruction text. V11 is a direct V9 continuation with independently retained numeric budget evidence: historical USD50/35main/15audit remains immutable, effective cumulative caps are read only from that evidence, costs/holds never reset and there is no automatic category transfer. No V10 registration is invented. The original19-hold health baseline remains separate from the complete V11 admission-liability baseline. Older actual workers retain their original cap and deadline; registration alone does not prove an active continuation.",
                "limitations": "Selected metadata verification is not full active-store replay. Live checkpoint excludes newly admitted work since its last write. Process and database observations are not atomic. Stored responses include invalid/unknown outputs. Dossier assignments and summaries remain model-supported, not human truth."},
            "question": {"text": "Is the authorized Cybercrime NL dossier workflow running, what is its current phase coverage and budget, and is a phase ETA supported?"},
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
            amendments_v5 = source.rows("cyber_dossier_execution_amendment_v5")
            amendments_v6 = source.rows("cyber_dossier_execution_amendment_v6")
            amendments_v7 = source.rows("cyber_dossier_execution_amendment_v7")
            amendments_v8 = source.rows("cyber_dossier_execution_amendment_v8")
            amendments_v9 = source.rows("cyber_dossier_execution_amendment_v9")
            amendments_v10 = source.rows("cyber_dossier_execution_amendment_v10")
            amendments_v11 = source.rows("cyber_dossier_execution_amendment_v11")
            diagnostics = source.rows("cyber_summary_fidelity_diagnostic_plan")
            if len(amendments_v4) > 1 or len(amendments_v5) > 1 or len(diagnostics) > 1:
                raise AuditError("dossier_monitor_unsupported_v4_v5_or_diagnostic_count")
            v4 = amendments_v4[0] if amendments_v4 else None
            v5 = amendments_v5[0] if amendments_v5 else None
            if len(amendments_v6) > 1:
                raise AuditError("dossier_monitor_unsupported_v6_amendment_count")
            v6 = amendments_v6[0] if amendments_v6 else None
            if len(amendments_v7) > 1:
                raise AuditError("dossier_monitor_unsupported_v7_amendment_count")
            v7 = amendments_v7[0] if amendments_v7 else None
            if len(amendments_v8) > 1:
                raise AuditError("dossier_monitor_unsupported_v8_amendment_count")
            v8 = amendments_v8[0] if amendments_v8 else None
            if len(amendments_v9) > 1:
                raise AuditError("dossier_monitor_unsupported_v9_amendment_count")
            v9 = amendments_v9[0] if amendments_v9 else None
            if len(amendments_v10) > 1:
                raise AuditError("dossier_monitor_unsupported_v10_amendment_count")
            v10 = amendments_v10[0] if amendments_v10 else None
            if len(amendments_v11) > 1 or amendments_v11 and v10:
                raise AuditError("dossier_monitor_unsupported_v11_amendment_or_branch")
            v11 = amendments_v11[0] if amendments_v11 else None
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
            all_reports = source.rows("cyber_dossier_report")
            parent_v4_report = bound_report(all_reports, v5["parent_report"]) if v5 else None
            parent_v5_report = bound_report(all_reports, v6["parent_report"]) if v6 else None
            passed_v6_report = bound_report(all_reports, v7["passed_pilot_report"]) if v7 else None
            stopped_v6_report = bound_report(all_reports, v7["parent_report"]) if v7 else None
            passed_v6_gate = source.passed_v6_gate(v7["passed_gate_record"]) if v7 else None
            stopped_v7_report = bound_report(all_reports, v8["parent_report"]) if v8 else None
            stopped_v8_report = bound_report(all_reports, v9["parent_report"]) if v9 else None
            stopped_v9_report = bound_report(all_reports, v10["parent_report"]) if v10 else None
            v11_parent_report = bound_report(all_reports, v11["parent_report"]) if v11 else None
            amendment = v11 or v10 or v9 or v8 or v7 or v6 or v5 or v4 or v3 or v2
            deadline = launches[0]["deadline"] if launches else None
            implementation_verification = validate_chain(plan, v2, v3, deadline, v4, diagnostic, parent_report,
                                                          diagnostic_repair, repair_report, v5, parent_v4_report,
                                                          v6, parent_v5_report, v7, passed_v6_report, stopped_v6_report,
                                                          passed_v6_gate, v8, stopped_v7_report, v9, stopped_v8_report, v10, stopped_v9_report)
            if v10:
                source.verify_deadline_policy(v10)
            if v11:
                validate_v11_extension(v11, v9, v11_parent_report, plan)
                source.verify_v11_policy(v11)
                implementation_verification = verify_implementations(
                    plan, v2, v3, v4, v5, v6, v7, v8, v9, v11, diagnostic, diagnostic_repair)
            if any(p.get("runner") == "run_dossiers_v2.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v2:
                raise AuditError("dossier_monitor_amended_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v3.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v3:
                raise AuditError("dossier_monitor_v3_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v4.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v4:
                raise AuditError("dossier_monitor_v4_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v5.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v5:
                raise AuditError("dossier_monitor_v5_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v6.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v6:
                raise AuditError("dossier_monitor_v6_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v7.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v7:
                raise AuditError("dossier_monitor_v7_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v8.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v8:
                raise AuditError("dossier_monitor_v8_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v9.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v9:
                raise AuditError("dossier_monitor_v9_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v10.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v10:
                raise AuditError("dossier_monitor_v10_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v11.py" for p in processes if p.get("action") in {"run", "pilot"}) and not v11:
                raise AuditError("dossier_monitor_v11_worker_without_registration")
            if any(p.get("runner") == DIAGNOSTIC_RUNNER for p in processes if p.get("action") in {"run", "pilot"}) and not diagnostic:
                raise AuditError("dossier_monitor_diagnostic_worker_without_registration")
            if any(p.get("runner") == DIAGNOSTIC_REPAIR_RUNNER for p in processes if p.get("action") in {"run", "pilot"}) and not diagnostic_repair:
                raise AuditError("dossier_monitor_diagnostic_repair_worker_without_registration")
            reports = all_reports if not processes else []
            count_sql = "SELECT count(*) AS responses,max(created_event) AS last_response_event FROM records WHERE kind=?"
            phase_sql = "SELECT json_extract(payload,'$.phase') AS phase,count(*) AS responses FROM records WHERE kind=? GROUP BY json_extract(payload,'$.phase')"
            attempt_sql = "SELECT max(seq) FROM events WHERE kind='model.attempt.intended'"
            revalidation_sql = "SELECT count(*) AS derived_revalidations,max(created_event) AS last_revalidation_event FROM records WHERE kind=?"
            diagnostic_sql = "SELECT count(*) FROM records WHERE kind=? AND json_extract(payload,'$.diagnostic_plan') IN (?,?)"
            diagnostic_ids = [diagnostic["_record_id"] if diagnostic else None,
                              diagnostic_repair["_record_id"] if diagnostic_repair else None]
            self.ledger.append(session, "dossier_monitor.count.intended", {"sql": count_sql,
                "phase_sql": phase_sql, "attempt_sql": attempt_sql, "diagnostic_sql": diagnostic_sql,
                "revalidation_sql": revalidation_sql, "revalidation_kind": "cyber_dossier_seed_revalidation",
                "parameters": ["cyber_dossier_response", *diagnostic_ids], "owner": str(ACTIVE_OWNER)})
            response_state = dict(source.db.execute(count_sql, ("cyber_dossier_response",)).fetchone())
            response_state["last_attempt_event"] = source.db.execute(attempt_sql).fetchone()[0]
            response_state.update(dict(source.db.execute(revalidation_sql, ("cyber_dossier_seed_revalidation",)).fetchone()))
            diagnostic_responses = source.db.execute(diagnostic_sql,
                ("cyber_dossier_response", *diagnostic_ids)).fetchone()[0]
            phase_counts = {row["phase"] or "unavailable": row["responses"]
                            for row in source.db.execute(phase_sql, ("cyber_dossier_response",))}
            head = list(source.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        finally:
            source.close()
        raw = read_progress(ACTIVE_OWNER / "progress.json") if (ACTIVE_OWNER / "progress.json").is_file() else None
        progress = json.loads(raw) if raw else None
        known_amendments = {r["_record_id"]: r for r in (v2, v3, v4, v5, v6, v7, v8, v9, v10, v11) if r}
        checkpoint_amendment = progress.get("execution_amendment") if progress else None
        if checkpoint_amendment is not None and checkpoint_amendment not in known_amendments:
            raise AuditError("dossier_monitor_checkpoint_amendment_mismatch")
        validate_progress(progress, plan, cap_nanousd=(v11["cap_nanousd"]
            if v11 and checkpoint_amendment == v11["_record_id"] else CAP_NANOUSD))
        checkpoint_diagnostic = progress.get("diagnostic_plan") if progress else None
        if checkpoint_diagnostic is not None and checkpoint_diagnostic not in diagnostic_ids:
            raise AuditError("dossier_monitor_checkpoint_diagnostic_mismatch")
        if checkpoint_diagnostic is not None:
            checkpoint_diagnostic_plan = next(r for r in (diagnostic, diagnostic_repair)
                                              if r and r["_record_id"] == checkpoint_diagnostic)
            validate_diagnostic_snapshot(progress, checkpoint_diagnostic_plan)
        validate_current_liabilities(progress, known_amendments.get(checkpoint_amendment))
        if v11 and checkpoint_amendment == v11["_record_id"]:
            validate_v11_snapshot(progress, v11, checkpoint=True)
            validate_operational_continuation(progress.get("operational_continuation"), v11, response_state["responses"])
        elif v10 and checkpoint_amendment == v10["_record_id"]:
            validate_v10_snapshot(progress, v10, checkpoint=True)
            validate_operational_continuation(progress.get("operational_continuation"), v10, response_state["responses"])
        elif v9 and checkpoint_amendment == v9["_record_id"]:
            validate_operational_continuation(progress.get("operational_continuation"), v9, response_state["responses"])
        if progress and progress.get("deadline") is not None and progress["deadline"] != deadline:
            raise AuditError("dossier_monitor_deadline_mismatch")
        previous = [self.ledger.get(row[0], "cyber_dossier_progress_observation") for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='cyber_dossier_progress_observation' ORDER BY created_event")]
        previous = [r for r in previous if r["provenance"]["plan"] == plan["_record_id"]]
        now = datetime.now(timezone.utc)
        stop = (ACTIVE_OWNER / "STOP").exists()
        deadline_context = effective_deadline_context(deadline, v10, processes, now, v11)
        budget_context = effective_budget_context(v11, processes)
        measured = phase_timing(progress, previous, now, processes, stop,
                                deadline_context["effective_admission_deadline"])
        expected_worker_amendment = {"run_dossiers.py": None,
            "run_dossiers_v2.py": v2["_record_id"] if v2 else None,
            "run_dossiers_v3.py": v3["_record_id"] if v3 else None,
            "run_dossiers_v4.py": v4["_record_id"] if v4 else None,
            "run_dossiers_v5.py": v5["_record_id"] if v5 else None,
            "run_dossiers_v6.py": v6["_record_id"] if v6 else None,
            "run_dossiers_v7.py": v7["_record_id"] if v7 else None,
            "run_dossiers_v8.py": v8["_record_id"] if v8 else None,
            "run_dossiers_v9.py": v9["_record_id"] if v9 else None,
            "run_dossiers_v10.py": v10["_record_id"] if v10 else None,
            "run_dossiers_v11.py": v11["_record_id"] if v11 else None,
            DIAGNOSTIC_RUNNER: v3["_record_id"] if v3 else None,
            DIAGNOSTIC_REPAIR_RUNNER: v3["_record_id"] if v3 else None}
        leaves = [p for p in processes if p["worker_leaf"]]
        administrative = [p for p in leaves if p.get("action") in ADMINISTRATIVE_ACTIONS]
        paid_workers = [p for p in leaves if p.get("action") in {"run", "pilot"}]
        diagnostic_active = any(p["runner"] in DIAGNOSTIC_RUNNERS for p in paid_workers)
        checkpoint_version_matches_worker = bool(progress and len(leaves) == 1 and not administrative
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
        if current and v7:
            if report.get("technical_extension_version") != (11 if v11 else 10 if v10 else 9 if v9 else 8 if v8 else 7):
                current = False  # The inherited intermediate report lacks capacity coverage.
            else:
                capacity = report.get("seed_capacity") or {}
                if capacity.get("frozen_census") != v7["seed_capacity_census"]:
                    raise AuditError("dossier_monitor_capacity_census_changed")
                validate_seed_capacity(capacity["frozen_census"], capacity.get("execution_summary"))
                if v8:
                    if report.get("seed_revalidation") is None:
                        current = False  # An inherited intermediate report cannot hide local revalidation.
                    else:
                        if report.get("seed_order_integrity") != v8["seed_order_integrity"]:
                            raise AuditError("dossier_monitor_report_seed_order_integrity_changed")
                        validate_seed_revalidation(report["seed_revalidation"], v8,
                                                   response_state["derived_revalidations"])
        if current and v9:
            if report.get("operational_continuation") is None:
                current = False  # An inherited report is not the final v9 operational report.
            else:
                if v11:
                    validate_v11_snapshot(report, v11)
                elif v10:
                    validate_v10_snapshot(report, v10)
                validate_operational_continuation(report["operational_continuation"], v11 or v10 or v9, response_state["responses"])
                allocation = ({"main_cap_nanousd": v11["main_cap_nanousd"],
                    "audit_cap_nanousd": v11["audit_cap_nanousd"]} if v11 else None)
                validate_category_budget(report.get("category_budget"), report, allocation)
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
        operational = (report.get("operational_continuation") if current and v9 else
            progress.get("operational_continuation") if progress and checkpoint_amendment in {r["_record_id"] for r in (v9, v10, v11) if r} else None)
        operational_basis = ("current_audited_stopped_report" if current and v9 else
            "current_execution_checkpoint" if operational is not None and measured["checkpoint_matches_current_execution"] and checkpoint_version_matches_worker else
            "historical_checkpoint" if operational is not None else "unavailable")
        coverage_keys = ("pipeline_finished", "pipeline_processing_complete", "final_audit_completion", "final_audit_complete",
                         "pilot_summary_reference", "pilot_card_reference", "pilot_full_bundle_control",
                         "four_processes_complete", "groups", "multi_article_groups",
                         "unique_inputs_grouped", "unresolved_inputs", "groups_with_usable_summary",
                         "groups_with_usable_card", "provisional_card_incomplete_groups",
                         "quality_rejected_or_unavailable_groups", "quality_rejected_or_unavailable_articles",
                         "nonjoined_audit_candidate_pool", "nonjoined_audit_selected_endpoint_status_counts",
                         "nonjoined_audit_frame_counts",
                         "quarantined_groups", "quarantined_articles", "article_routes",
                         "pilot_primary", "pilot_secondary", "pilot_budget",
                         "rejected_expansion_groups", "unresolved_rival_relations",
                         "globally_unique_dossiers_established", "all_potential_matches_guaranteed",
                         "seed_capacity", "seed_revalidation", "seed_order_integrity", "technical_extension_version", "operational_continuation", "category_budget")
        result = {"versions": versions, "observed_at": now.isoformat(), "observed_amsterdam": amsterdam(now),
            "provenance": {"owner": str(ACTIVE_OWNER), "plan": plan["_record_id"], "head": head,
                           "latest_report": report["_record_id"] if report else None,
                           "execution_amendment": amendment["_record_id"] if amendment else None,
                           "amendment_parent_plan": amendment["parent_plan"] if amendment else None,
                           "v2_execution_amendment": v2["_record_id"] if v2 else None,
                           "v3_execution_amendment": v3["_record_id"] if v3 else None,
                           "v4_execution_amendment": v4["_record_id"] if v4 else None,
                           "v5_execution_amendment": v5["_record_id"] if v5 else None,
                           "v5_parent_report": v5.get("parent_report") if v5 else None,
                           "v5_declared_v4_diagnostic": v5.get("v4_diagnostic") if v5 else None,
                           "v6_execution_amendment": v6["_record_id"] if v6 else None,
                           "v6_parent_report": v6.get("parent_report") if v6 else None,
                           "v6_declared_v5_diagnostic": v6.get("v5_diagnostic") if v6 else None,
                           "v6_pilot_selection_artifact": v6.get("pilot_selection_artifact") if v6 else None,
                           "v7_execution_amendment": v7["_record_id"] if v7 else None,
                           "v7_parent_report": v7.get("parent_report") if v7 else None,
                           "v7_passed_pilot_report": v7.get("passed_pilot_report") if v7 else None,
                           "v7_passed_gate_record": v7.get("passed_gate_record") if v7 else None,
                           "v7_seed_packet_plan_artifact": v7.get("seed_packet_plan_artifact") if v7 else None,
                           "v10_execution_amendment": v10["_record_id"] if v10 else None,
                           "v10_parent_report": v10.get("parent_report") if v10 else None,
                           "v10_deadline_authorization_policy": v10["versions"]["policy"] if v10 else None,
                           "v10_authorization_artifact": v10["deadline_authorization"]["artifact"] if v10 else None,
                           "v11_execution_amendment": v11["_record_id"] if v11 else None,
                           "v11_parent_report": v11.get("parent_report") if v11 else None,
                           "v11_authorization_policy": v11["versions"]["policy"] if v11 else None,
                           "v11_deadline_evidence_artifact": v11["deadline_authorization"]["artifact"] if v11 else None,
                           "v11_budget_evidence_artifact": v11["budget_authorization"]["artifact"] if v11 else None,
                           "v9_execution_amendment": v9["_record_id"] if v9 else None,
                           "v9_parent_report": v9.get("parent_report") if v9 else None,
                           "v9_declared_technical_diagnostic": v9.get("technical_diagnostic") if v9 else None,
                           "v8_execution_amendment": v8["_record_id"] if v8 else None,
                           "v8_parent_report": v8.get("parent_report") if v8 else None,
                           "v8_declared_v7_diagnostic": v8.get("diagnostic") if v8 else None,
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
            "phase": "administrative_writer" if administrative else "independent_summary_fidelity_diagnostic" if diagnostic_active else progress.get("phase") if progress else "awaiting_first_checkpoint",
            "checkpoint_phase": progress.get("phase") if progress else None,
            "diagnostic_worker_active": diagnostic_active, "writer_active": bool(leaves),
            "administrative_writer_active": bool(administrative), "administrative_python_processes": administrative,
            "paid_worker_active": bool(paid_workers), "paid_worker_python_processes": paid_workers,
            "administrative_registration_required_for_observation": False,
            "writer_leaf_count": len(leaves), "stored_diagnostic_responses": diagnostic_responses,
            "latest_diagnostic_report_current": diagnostic_current,
            "stored_responses": response_state["responses"], "responses_by_phase": phase_counts,
            "selected_articles": EXPECTED_ARTICLES, "unique_documents": EXPECTED_DOCUMENTS,
            **costs, **holds, "settled_cost_usd": costs["settled_nanousd"] / 1e9 if costs["settled_nanousd"] is not None else None,
            "held_cost_usd": costs["held_nanousd"] / 1e9 if costs["held_nanousd"] is not None else None,
            "committed_cost_usd": costs["committed_nanousd"] / 1e9 if costs["committed_nanousd"] is not None else None,
            **budget_context, "budget_scope": "Audited stopped dossier report" if current else "Audited stopped diagnostic report including all dossier costs" if diagnostic_current else "Last checkpoint; subsequent admissions may add reservations",
            "registered_budget_policy": v11["budget_policy"] if v11 else None,
            "v4_budget_allocation_nanousd": {key: v4[key] for key in V4_ALLOCATION} if v4 else None,
            "v4_summary_reference_requirement": {"minimum": v4["summary_reference_minimum"],
                "target": v4["summary_reference_target"], "all_selected_must_be_valid_supported": True} if v4 else None,
            "v5_budget_allocation_nanousd": {key: v5[key] for key in V5_ALLOCATION} if v5 else None,
            "v5_card_reference_requirement": {"minimum": v5["card_reference_minimum"],
                "target": v5["card_reference_target"], "all_selected_must_be_valid_supported": True} if v5 else None,
            "v6_budget_allocation_nanousd": {key: v6[key] for key in V6_ALLOCATION} if v6 else None,
            "v6_evidence_scope": ("Adaptive reanalysis of the fixed v5 assignments. Prior card/pair evidence is reused; primary expanded-group judgments are new only where not previously attempted. Incoming articles may share expanded groups, so their count is not a count of independent validation cases. Secondary withheld hypotheses are descriptive and cannot change acceptance." if v6 else None),
            "technical_extension_version": 11 if v11 else 10 if v10 else 9 if v9 else 8 if v8 else 7 if v7 else None,
            "operational_continuation": operational,
            "operational_observation_basis": operational_basis,
            "category_budget": report.get("category_budget") if current and v9 else None,
            "registered_operational_policy": v9.get("operational_policy") if v9 else None,
            "v9_baseline_unresolved_holds": len(v9["legacy_unresolved_attempts"]) if v9 else None,
            "v9_baseline_held_nanousd": v9["legacy_budget"]["held_nanousd"] if v9 else None,
            "v10_admission_baseline_unresolved_holds": len(v10["legacy_unresolved_attempts"]) if v10 else None,
            "v11_admission_baseline_unresolved_holds": len(v11["legacy_unresolved_attempts"]) if v11 else None,
            "v11_admission_baseline_held_nanousd": v11["legacy_budget"]["held_nanousd"] if v11 else None,
            "operational_origin_amendment": (v11 or v10)["operational_origin_amendment"] if v11 or v10 else v9["_record_id"] if v9 else None,
            "health_response_amendments": [*(v11 or v10)["health_ancestor_amendments"], (v11 or v10)["_record_id"]] if v11 or v10 else [v9["_record_id"]] if v9 else None,
            "operational_count_meaning": ("Durable v9 and any registered deadline-continuation outcomes across phases/restarts include orphan intents. They are separate from provider responses and semantic judgments. All19 pre-v9 holds remain reserved; earlier holds are not new v9 failures." if v9 else None),
            "derived_seed_revalidations": response_state["derived_revalidations"],
            "registered_seed_order_integrity": v8.get("seed_order_integrity") if v8 else None,
            "seed_revalidation": report.get("seed_revalidation") if current and v8 else None,
            "revalidation_meaning": ("Derived local checks of existing immutable responses; no model request, response, new charge, hold release or change to prior rows. Excluded from provider-response counts and throughput." if v8 else None),
            "seed_capacity": report.get("seed_capacity") if current and v7 else None,
            "registered_seed_capacity_census": v7.get("seed_capacity_census") if v7 else None,
            "capacity_deferral_meaning": ("Local capacity deferrals are unjudged/not attempted comparisons. They are not provider failures, unknown outcomes, billing holds or semantic exclusions. The complete input denominator remains unchanged." if v7 else None),
            "reused_v6_gate": ({"report": passed_v6_report["_record_id"], "pilot_gate": passed_v6_report.get("pilot_gate"), "new_semantic_pilot": False} if v7 else None),
            "latest_report_current": current, "published_report_status": published_status,
            "pilot_gate": report.get("pilot_gate") if current else None,
            "pilot_summary_reference": report.get("pilot_summary_reference") if current and v4 and not v5 else None,
            "pilot_card_reference": report.get("pilot_card_reference") if current and v5 and not v6 else None,
            "pilot_full_bundle_control": report.get("pilot_full_bundle_control") if current and v5 and not v6 else None,
            "reused_v5_evidence": ({"report": parent_v5_report["_record_id"], "historical_failed_gate": parent_v5_report.get("pilot_gate"),
                "card_reference": parent_v5_report.get("pilot_card_reference"),
                "full_bundle_control": parent_v5_report.get("pilot_full_bundle_control"),
                "new_independent_validation": False} if v6 else None),
            "pilot_primary": report.get("pilot_primary") if current and v6 else None,
            "pilot_secondary": report.get("pilot_secondary") if current and v6 else None,
            "pilot_budget": report.get("pilot_budget") if current and v6 else None,
            "pilot_gate_phase": "pilot_v6_gate" if v6 else "pilot_v5_gate" if v5 else "pilot_v4_gate" if v4 else "pilot_v3_gate" if v3 else "pilot_v2_gate" if v2 else "pilot_gate",
            "full_outcome_phase": "full_v6_outcome" if v6 else "full_v5_outcome" if v5 else "full_v4_outcome" if v4 else "full_v3_outcome" if v3 else "full_v2_outcome" if v2 else "full_outcome",
            "pilot_v3_gate": report.get("pilot_gate") if current and v3 and not v4 else None,
            "full_v3_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v3 and not v4 and report.get("pipeline_finished") else None),
            "pilot_v4_gate": report.get("pilot_gate") if current and v4 and not v5 else None,
            "full_v4_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v4 and not v5 and report.get("pipeline_finished") else None),
            "full_v4_processing_outcome": ({key: report.get(key) for key in coverage_keys}
                                           if current and v4 and not v5 and report.get("pipeline_processing_complete") else None),
            "pilot_v5_gate": report.get("pilot_gate") if current and v5 and not v6 else None,
            "full_v5_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v5 and not v6 and report.get("pipeline_finished") else None),
            "full_v5_processing_outcome": ({key: report.get(key) for key in coverage_keys}
                                           if current and v5 and not v6 and report.get("pipeline_processing_complete") else None),
            "pilot_v6_gate": report.get("pilot_gate") if current and v6 else None,
            "full_v6_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v6 and report.get("pipeline_finished") else None),
            "full_v6_processing_outcome": ({key: report.get(key) for key in coverage_keys}
                                           if current and v6 and report.get("pipeline_processing_complete") else None),
            "checkpoint_execution_amendment": checkpoint_amendment,
            "checkpoint_version_matches_worker": checkpoint_version_matches_worker,
            "final_coverage": {key: report.get(key) for key in coverage_keys} if current else None,
            "count_meaning": "Saved provider responses across embeddings, decisions, summaries and audit, including invalid/unknown responses; not articles classified or dossiers validated.",
            "new_model_calls": 0, "worker_mutations": 0, **measured, **deadline_context}
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
        print(json.dumps(study.execute("status", {}, objective="Observe the separate Cybercrime dossier workflow without changing its worker",
                                      actor="codex:cybercrime-dossier-monitor"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
