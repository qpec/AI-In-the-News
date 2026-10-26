"""Read-only audited progress for the separate full Cybercrime NL screen."""
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
sys.path.insert(0, str(ROOT / "workbench"))
from newsresearch.common import AuditError, Config, digest  # noqa: E402
from newsresearch.runtime import audited_handler  # noqa: E402
import run_screening_v2 as screening  # noqa: E402
from check_luna_decisions_incident_progress import amsterdam, read_progress  # noqa: E402

METHOD = "luna-decisions-cybercrime-nl-progress-20261023-v1"
ACTIVE_OWNER = screening.OWNER
MONITOR_OWNER = screening.original.base.pilot.BASE / METHOD
EXPECTED_REQUESTS = 57_002
EXPECTED_ARTICLES = 61_089
FRESH_SECONDS = 300


def matching_processes(items, owner):
    """Keep exact workspace + v2 run commands, separating venv wrapper/child."""
    expected = str(owner.resolve()).replace("\\", "/").casefold()
    matched = []
    for item in items:
        command = item.get("command_line") or ""
        normalized = command.replace("\\", "/").casefold()
        run = re.search(r"(?:^|[/\s\"'])run_screening_v2\.py[\"']?\s+run(?:\s|$)", normalized)
        workspace = re.search(r"--workspace\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))", normalized)
        actual = next((v for v in workspace.groups() if v is not None), None) if workspace else None
        if run and actual and actual.rstrip("/") == expected.rstrip("/"):
            datetime.fromisoformat(item["created_at"])
            matched.append(dict(item))
    parents = {r["parent_pid"] for r in matched}
    for item in matched:
        item["worker_leaf"] = item["pid"] not in parents
    return sorted(matched, key=lambda r: (r["created_at"], r["pid"]))


def workers(owner):
    script = r"""$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'run_screening_v2\.py'
} | ForEach-Object { @{pid=$_.ProcessId; parent_pid=$_.ParentProcessId;
    created_at=$_.CreationDate.ToUniversalTime().ToString('o');
    executable_path=$_.ExecutablePath; command_line=$_.CommandLine} })
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=20, check=True)
    return matching_processes(json.loads(result.stdout), owner)


def timing(progress, previous, now, processes, launch, stop_present, ended=False):
    observed = datetime.fromisoformat(progress["at"])
    age = (now - observed).total_seconds()
    leaves = [r for r in processes if r["worker_leaf"]]
    baseline = progress.get("execution_response_baseline", 100)
    if type(baseline) is not int or not 0 <= baseline <= progress["new_responses"]:
        raise AuditError("cyber_monitor_invalid_execution_baseline")
    identity = {"launch": launch["_record_id"], "started_at": launch["started_at"],
                "response_baseline": baseline} if launch else None
    current = bool(len(leaves) == 1 and launch and not launch["operational"]
                   and datetime.fromisoformat(leaves[0]["created_at"])
                   <= datetime.fromisoformat(launch["started_at"]) <= observed
                   and progress["phase"] == "screening")
    remaining = progress["planned"] - progress["new_responses"]
    candidates = []
    for old in previous:
        if not old.get("checkpoint_matches_current_execution") or old.get("execution_identity") != identity:
            continue
        old_progress = old["progress"]
        span = (observed - datetime.fromisoformat(old_progress["at"])).total_seconds()
        delta = progress["new_responses"] - old_progress["new_responses"]
        if 900 <= span <= 5400 and delta >= 0:
            candidates.append((abs(span - 1800), span, delta))
    if candidates:
        _, span, delta = min(candidates)
        basis = "comparable_cumulative_15_to_90_minute_delta"
    else:
        span, delta = progress["elapsed_seconds"], progress["new_responses"] - baseline
        basis = "current_execution_average_fallback"
    rate = delta / span if span > 0 else None
    if not leaves:
        state, blocker = "stopped", "no_matching_python_worker"
    elif len(leaves) != 1:
        state, blocker = "multiple_workers_needs_investigation", "multiple_matching_python_workers"
    elif not current:
        state, blocker = "starting_or_waiting_first_checkpoint", "checkpoint_from_prior_execution"
    elif stop_present:
        state, blocker = "stop_present_worker_exiting", "user_stop_present"
    elif ended:
        state, blocker = "finishing_report", "execution_has_ended"
    elif age < -5:
        state, blocker = "clock_mismatch", "checkpoint_timestamp_in_future"
    elif age > FRESH_SECONDS:
        state, blocker = "running_needs_investigation", "checkpoint_over_five_minutes_old"
    elif remaining == 0:
        state, blocker = "finishing_report", "queue_exhausted"
    elif not rate or rate <= 0:
        state, blocker = "running", "no_positive_observed_throughput"
    else:
        state, blocker = "running", None
    eta = remaining / rate if blocker is None else None
    finish = now + timedelta(seconds=eta) if eta is not None else None
    deadline = datetime.fromisoformat(progress["expires_at"])
    runtime = max(0, (deadline - now).total_seconds())
    if runtime == 0:
        eta, finish, blocker = None, None, "admission_deadline_reached"
    return {"state": state, "checkpoint_matches_current_execution": current,
            "execution_identity": identity, "execution_response_baseline": baseline,
            "checkpoint_age_seconds": round(age, 2), "checkpoint_fresh": -5 <= age <= FRESH_SECONDS,
            "remaining_requests": remaining, "saved_responses_per_minute": rate * 60 if current and rate is not None else None,
            "rate_basis": basis if current else None, "rate_window_seconds": span if current else None,
            "eta_seconds": eta, "estimated_finish_amsterdam": amsterdam(finish) if finish else None,
            "eta_blocker": blocker, "original_deadline": progress["expires_at"],
            "remaining_runtime_seconds": runtime, "deadline_expired": runtime == 0,
            "projected_finish_after_deadline": finish > deadline if finish else None,
            "eta_scope": "Provisional time to exhaust remaining unique requests at similar throughput; unknown outcomes are not retried or predicted to resolve."}


class Study(screening.original.base.pilot.Study):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == ACTIVE_OWNER.resolve():
            raise AuditError("cyber_monitor_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        if self.ledger.root.resolve() == ACTIVE_OWNER.resolve():
            raise AuditError("cyber_monitor_owner_must_be_separate")
        code = {str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "workbench/check_luna_decisions_incident_progress.py": hashlib.sha256(
                    (ROOT / "workbench/check_luna_decisions_incident_progress.py").read_bytes()).hexdigest()}
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Read verified source-free plan/continuation/launch/end/report records through a read-only Source, never a writer on the active owner. Read progress with Windows share-read/write/delete and dispose immediately. Capture actual matching Python command/PID/creation time, separate wrapper from worker leaf. Save observation in a separate protected monitor owner. Prefer comparable same-execution cumulative deltas of 15–90 minutes; otherwise subtract execution baseline before dividing by its elapsed time. No ETA while stopped, stale, starting, stopped by user, ended or expired. No process mutation or model calls.",
                "limitations": "Checkpoint costs and counts are reported operational state, not a fresh replay of every result or semantic validity. The checkpoint excludes the next wave's in-flight reservations. Selected source metadata reads are not a full active-store preflight."},
            "question": {"text": "Is the separately authorized full Cybercrime NL screen progressing, at what cost, and when might its remaining queue finish?"},
            "selection": {"rules": "Only the fixed v2 owner's operational metadata: 61,089 source rows and 57,002 unique requests; no article text, request bodies or new inference."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register read-only monitoring before observation"})["id"]
        source = screening.original.base.pilot.Source(ACTIVE_OWNER)
        try:
            plan = source.one("cyber_screen_plan")
            continuation = source.one("cyber_preparation_continuation")
            if (plan["implementation"] != screening.original.implementation()
                    or continuation["implementation"] != screening.implementation()
                    or plan["selected_articles"] != EXPECTED_ARTICLES
                    or plan["dispositions"].get("ready") != EXPECTED_REQUESTS):
                raise AuditError("cyber_monitor_frozen_plan_changed")
            launches, ends, reports = (source.rows(kind) for kind in
                ("cyber_screen_launch", "cyber_screen_run_end", "cyber_screen_report"))
            provenance = {"owner": str(ACTIVE_OWNER), "head": source.head(), "plan": plan["_record_id"],
                          "continuation": continuation["_record_id"],
                          "latest_launch": launches[-1]["_record_id"] if launches else None,
                          "latest_end": ends[-1]["_record_id"] if ends else None,
                          "latest_report": reports[-1]["_record_id"] if reports else None}
        finally:
            source.close()
        raw = read_progress(ACTIVE_OWNER / "progress.json")
        progress = json.loads(raw)
        if (progress["planned"] != EXPECTED_REQUESTS or type(progress["new_responses"]) is not int
                or not 0 <= progress["new_responses"] <= progress["planned"]
                or progress["budget_usd"] != 20 or progress["phase"] not in {"operational", "screening"}
                or (launches and progress["expires_at"] != launches[0]["expires_at"])):
            raise AuditError("cyber_monitor_checkpoint_scope_changed")
        matched = workers(ACTIVE_OWNER)
        now = datetime.now(timezone.utc)
        stop = (ACTIVE_OWNER / "STOP").exists()
        previous = [r for r in self.rows("cyber_progress_observation") if r["provenance"]["plan"] == plan["_record_id"]]
        launch = launches[-1] if launches else None
        ended = bool(launch and ends and datetime.fromisoformat(ends[-1]["finished_at"])
                     >= datetime.fromisoformat(launch["started_at"]))
        measured = timing(progress, previous, now, matched, launch, stop, ended)
        report_current = bool(reports and reports[-1]["new_responses"] >= progress["new_responses"] and ended
                              and reports[-1].get("run_end")
                              and reports[-1]["run_end"][-1]["_record_id"] == ends[-1]["_record_id"])
        held = progress["held_reservations_usd"]
        result = {"versions": versions, "observed_at": now.isoformat(), "observed_amsterdam": amsterdam(now),
                  "provenance": provenance, "progress": progress,
                  "checkpoint_sha256": hashlib.sha256(raw).hexdigest(), "checkpoint_artifact": self.ledger.artifacts.put_bytes(raw),
                  "matching_python_processes": matched, "worker_python_processes": [r for r in matched if r["worker_leaf"]],
                  "user_stop_present": stop, "phase": progress["phase"],
                  "new_responses": progress["new_responses"], "planned_requests": progress["planned"],
                  "percent_responses": 100 * progress["new_responses"] / progress["planned"],
                  "selected_articles": plan["selected_articles"], "input_dispositions": plan["dispositions"],
                  "settled_cost_usd_with_margin": progress["settled_cost_usd_with_margin"],
                  "held_reservations_usd": held,
                  "unresolved_holds_reported": round(held * 1e9 / screening.original.core.RESERVATION_NANOUSD),
                  "total_committed_usd": progress["total_committed_usd"], "budget_usd": progress["budget_usd"],
                  "budget_counts_scope": "Last completed-wave checkpoint; next-wave in-flight reservations are additional and enforced by the worker.",
                  "latest_report_current": report_current,
                  "final_coverage": {k: reports[-1][k] for k in ("coverage", "labels", "article_labels_including_exact_input_aliases",
                      "unresolved_attempts", "not_attempted", "dispatch_complete", "all_outcomes_resolved")} if report_current else None,
                  "count_meaning": "Stored unique-request responses, including errors or unknowns; not successful classifications or verified articles.",
                  "new_model_calls": 0, "worker_mutations": 0, **measured}
        identifier = self.ledger.record(session, "cyber_progress_observation", digest(result), result)
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
    if args.workspace.resolve() == ACTIVE_OWNER.resolve():
        raise AuditError("cyber_monitor_owner_must_be_separate")
    study = Study(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Observe full Cybercrime NL screening progress and provisional ETA without changing the worker",
                                      actor="codex:cybercrime-progress-monitor"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
