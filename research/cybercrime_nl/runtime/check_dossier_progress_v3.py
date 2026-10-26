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
METHOD = "cybercrime-nl-dossier-progress-20261023-v3"
RUN_METHOD = "cybercrime-four-process-dossiers-20261023-v1"
EXPECTED_PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
EXPECTED_V2 = "08c7ad39990dc926e6e74a04e8758fae4423e88341d056e416bc0b5b29b24282"
EXPECTED_DOCUMENTS = 6691
EXPECTED_ARTICLES = 7743
CAP_NANOUSD = 50_000_000_000
FRESH_SECONDS = 300
ALLOWED_RECORDS = {"cyber_dossier_plan", "cyber_dossier_first_launch", "cyber_dossier_report",
                   "cyber_dossier_execution_amendment", "cyber_dossier_execution_amendment_v3"}


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
        run = re.search(r"(?:^|[/\s\"'])(run_dossiers(?:_v[23])?\.py)[\"']?\s+(pilot|run)(?:\s|$)", command)
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
            matched.append({**item, "action": run.group(2), "runner": run.group(1), "uses_default_owner": default})
    parents = {item["parent_pid"] for item in matched}
    for item in matched:
        item["worker_leaf"] = item["pid"] not in parents
    return sorted(matched, key=lambda item: (item["created_at"], item["pid"]))


def workers(owner):
    script = r"""$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'run_dossiers(?:_v[23])?\.py'
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


def validate_chain(plan, v2, v3, deadline):
    if plan["_record_id"] != EXPECTED_PLAN:
        raise AuditError("dossier_monitor_original_plan_identity")
    validate_amendment(v2, plan, deadline)
    if v2 and v2["_record_id"] != EXPECTED_V2:
        raise AuditError("dossier_monitor_v2_identity")
    previous = None
    for amendment in (v2, v3):
        if amendment is None:
            continue
        if amendment is v3 and (v2 is None
                or amendment.get("parent_plan") != plan["_record_id"]
                or amendment.get("parent_execution_amendment") != v2["_record_id"]
                or amendment.get("parent_implementation") != v2["implementation"]
                or amendment.get("original_deadline") != deadline
                or amendment.get("cap_nanousd") != CAP_NANOUSD):
            raise AuditError("dossier_monitor_v3_parent_binding")
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
    return verify_implementations(plan, v2, v3)


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
                "procedure": "Read only fixed owner's source-free operational records via read-only SQLite, verifying selected projection and artifact hashes. Recognize original, v2 and v3 pilot/run commands, PID creation times and leaf workers. Verify original plan and v2 identity, v3 parent chain, unchanged declared implementation files, original deadline/cap and cumulative hold/cost lineage. Never replace the owner's plan or release old holds. Read mutable checkpoints with Windows share-read/write/delete; identify historical checkpoints during new startup. When stopped, validate latest report against current response row count/event boundary, latest execution amendment and published report ID. Expose current v3 gate/outcome only from a current v3 report; preserve older phase records. Retain observation in the same separate protected monitor owner with a new method version. No worker writes, packet/source reads, model calls or restart. Phase ETA requires positive comparable deltas in the same PID/creation/phase/queue/amendment; whole-pipeline ETA remains unknown.",
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
            amendment = v3 or v2
            deadline = launches[0]["deadline"] if launches else None
            implementation_verification = validate_chain(plan, v2, v3, deadline)
            if any(p.get("runner") == "run_dossiers_v2.py" for p in processes) and not v2:
                raise AuditError("dossier_monitor_amended_worker_without_registration")
            if any(p.get("runner") == "run_dossiers_v3.py" for p in processes) and not v3:
                raise AuditError("dossier_monitor_v3_worker_without_registration")
            reports = source.rows("cyber_dossier_report") if not processes else []
            count_sql = "SELECT count(*) AS responses,max(created_event) AS last_response_event FROM records WHERE kind=?"
            phase_sql = "SELECT json_extract(payload,'$.phase') AS phase,count(*) AS responses FROM records WHERE kind=? GROUP BY json_extract(payload,'$.phase')"
            self.ledger.append(session, "dossier_monitor.count.intended", {"sql": count_sql,
                "phase_sql": phase_sql, "parameters": ["cyber_dossier_response"], "owner": str(ACTIVE_OWNER)})
            response_state = dict(source.db.execute(count_sql, ("cyber_dossier_response",)).fetchone())
            phase_counts = {row["phase"] or "unavailable": row["responses"]
                            for row in source.db.execute(phase_sql, ("cyber_dossier_response",))}
            head = list(source.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        finally:
            source.close()
        raw = read_progress(ACTIVE_OWNER / "progress.json") if (ACTIVE_OWNER / "progress.json").is_file() else None
        progress = json.loads(raw) if raw else None
        validate_progress(progress, plan)
        known_amendments = {r["_record_id"]: r for r in (v2, v3) if r}
        checkpoint_amendment = progress.get("execution_amendment") if progress else None
        if checkpoint_amendment is not None and checkpoint_amendment not in known_amendments:
            raise AuditError("dossier_monitor_checkpoint_amendment_mismatch")
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
            "run_dossiers_v3.py": v3["_record_id"] if v3 else None}
        leaves = [p for p in processes if p["worker_leaf"]]
        checkpoint_version_matches_worker = bool(progress and len(leaves) == 1
            and checkpoint_amendment == expected_worker_amendment[leaves[0]["runner"]])
        if measured["checkpoint_matches_current_execution"] and not checkpoint_version_matches_worker:
            measured.update(state="starting_or_waiting_first_checkpoint", checkpoint_matches_current_execution=False,
                phase_eta_seconds=None, phase_estimated_finish_amsterdam=None, phase_tasks_per_minute=None,
                phase_rate_window_seconds=None, phase_finish_after_deadline=None,
                phase_eta_blocker="checkpoint_from_different_execution_amendment")
        report = reports[-1] if reports else None
        current = report_is_current(report, plan, response_state, progress, processes)
        if amendment and report and report.get("execution_amendment") != amendment["_record_id"]:
            current = False
        if current:
            validate_current_liabilities(report, amendment)
        published_report, published_status = None, "not_read_while_running" if processes else "missing"
        report_path = ACTIVE_OWNER / "dossier-report.json"
        if not processes and report_path.is_file():
            try:
                published_report = json.loads(read_progress(report_path))
                projected = {k: v for k, v in report.items() if not k.startswith("_")} if report else None
                published_status = "matches_latest_audited_record" if report and published_report == {"id": report["_record_id"], **projected} else "stale_or_different_from_audited_record"
            except (json.JSONDecodeError, UnicodeDecodeError):
                published_status = "invalid_partial_file"
        totals = report if current else progress
        costs = {name: totals.get(name) if totals else None for name in
                 ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")}
        holds = hold_breakdown(totals)
        coverage_keys = ("pipeline_finished", "four_processes_complete", "groups", "multi_article_groups",
                         "unique_inputs_grouped", "unresolved_inputs", "groups_with_usable_summary", "article_routes")
        result = {"versions": versions, "observed_at": now.isoformat(), "observed_amsterdam": amsterdam(now),
            "provenance": {"owner": str(ACTIVE_OWNER), "plan": plan["_record_id"], "head": head,
                           "latest_report": report["_record_id"] if report else None,
                           "execution_amendment": amendment["_record_id"] if amendment else None,
                           "amendment_parent_plan": amendment["parent_plan"] if amendment else None,
                           "v2_execution_amendment": v2["_record_id"] if v2 else None,
                           "v3_execution_amendment": v3["_record_id"] if v3 else None,
                           "amendment_parent_execution": v3["parent_execution_amendment"] if v3 else None,
                           "implementation_verification": implementation_verification},
            "progress": progress, "checkpoint_sha256": hashlib.sha256(raw).hexdigest() if raw else None,
            "checkpoint_artifact": self.ledger.artifacts.put_bytes(raw) if raw else None,
            "matching_python_processes": processes, "worker_python_processes": [p for p in processes if p["worker_leaf"]],
            "user_stop_present": stop, "phase": progress.get("phase") if progress else "awaiting_first_checkpoint",
            "stored_responses": response_state["responses"], "responses_by_phase": phase_counts,
            "selected_articles": EXPECTED_ARTICLES, "unique_documents": EXPECTED_DOCUMENTS,
            **costs, **holds, "settled_cost_usd": costs["settled_nanousd"] / 1e9 if costs["settled_nanousd"] is not None else None,
            "held_cost_usd": costs["held_nanousd"] / 1e9 if costs["held_nanousd"] is not None else None,
            "committed_cost_usd": costs["committed_nanousd"] / 1e9 if costs["committed_nanousd"] is not None else None,
            "budget_usd": 50, "budget_scope": "Audited stopped report" if current else "Last checkpoint; subsequent admissions may add reservations",
            "latest_report_current": current, "published_report_status": published_status,
            "pilot_gate": report.get("pilot_gate") if current else None,
            "pilot_gate_phase": "pilot_v3_gate" if v3 else "pilot_v2_gate" if v2 else "pilot_gate",
            "full_outcome_phase": "full_v3_outcome" if v3 else "full_v2_outcome" if v2 else "full_outcome",
            "pilot_v3_gate": report.get("pilot_gate") if current and v3 else None,
            "full_v3_outcome": ({key: report.get(key) for key in coverage_keys}
                                if current and v3 and report.get("pipeline_finished") else None),
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
