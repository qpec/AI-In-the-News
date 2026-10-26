"""Read-only, audited operational progress and ETA for the incident-only run."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess

from dateutil.tz import gettz

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import audited_handler
import run_luna_decisions_incident_corpus as runner

METHOD = "luna-decisions-incident-progress-20261021-v1"


def amsterdam(value):
    zone = gettz("Europe/Amsterdam")
    if zone is None:
        raise AuditError("monitor_amsterdam_timezone_unavailable")
    return value.astimezone(zone).isoformat()


def workers(owner):
    script = r"""$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object {
    $_.CommandLine -match 'run_luna_decisions_incident_(corpus\.py[\" ]+run|resilient\.py)[\" ]+'
} | ForEach-Object { @{pid=$_.ProcessId; parent_pid=$_.ParentProcessId;
    created_at=$_.CreationDate.ToUniversalTime().ToString('o'); command_line=$_.CommandLine} })
ConvertTo-Json -InputObject $items -Compress
"""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, timeout=20, check=True)
    needle = str(owner.resolve()).replace("\\", "/").lower()
    return [r for r in json.loads(result.stdout) if needle in r["command_line"].replace("\\", "/").lower()]


def rate_and_eta(progress, previous, now, live, baseline, execution_started=None):
    observed = datetime.fromisoformat(progress["at"])
    seconds = (now - observed).total_seconds()
    remaining = max(0, progress["planned"] - progress["new_responses"])
    candidates = []
    for old in previous:
        old_time = datetime.fromisoformat(old["progress"]["at"])
        if execution_started and old_time < datetime.fromisoformat(execution_started):
            continue
        span = (observed - old_time).total_seconds()
        delta = progress["new_responses"] - old["progress"]["new_responses"]
        if 900 <= span <= 5400 and delta >= 0:
            candidates.append((abs(span - 1800), span, delta))
    if candidates:
        _, span, delta = min(candidates)
        rate, basis = delta / span, "observed_cumulative_change_over_recent_window"
    else:
        span = progress["elapsed_seconds"]
        delta = progress["new_responses"] - baseline
        rate = delta / span if span > 0 and delta >= 0 else None
        basis = "current_execution_average_fallback"
    eta_seconds = remaining / rate if live and seconds <= 300 and rate and rate > 0 else None
    finish = now + timedelta(seconds=eta_seconds) if eta_seconds is not None else None
    return {"checkpoint_age_seconds": round(seconds, 2), "remaining_to_attempt": remaining,
        "saved_responses_per_minute": rate * 60 if rate is not None else None,
        "rate_basis": basis, "rate_window_seconds": span, "eta_seconds": eta_seconds,
        "estimated_finish_amsterdam": amsterdam(finish) if finish else None,
        "eta_scope": "Time to process the remaining queue at similar throughput; unresolved outcomes are not retried or predicted to resolve."}


def checkpoint_is_current(progress, launches, matched):
    if not matched or not launches:
        return False
    started = max(datetime.fromisoformat(r["created_at"]) for r in matched)
    launched = datetime.fromisoformat(launches[-1]["started_at"])
    return started <= launched <= datetime.fromisoformat(progress["at"])


def read_progress(path):
    if os.name != "nt":
        return path.read_bytes()
    # Permit atomic replacement while this monitor holds the read handle.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = create(str(path), 0x80000000, 7, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(descriptor, "rb") as stream:
        return stream.read()


class Study(runner.base.Study):
    @audited_handler
    def _status(self, session, context, data):
        code = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation_sha256": code,
                "procedure": "Read verified selected plan/launch/end/report records and the mutable operational progress checkpoint in a separate monitor owner. Record checkpoint bytes/hash and actual matching Python process identities. Report cumulative saved responses plus pilot reuse, errors/holds, budget, deadline and ETA. Prefer comparable 15-90 minute cumulative deltas within the current execution; otherwise use its count increment divided by its elapsed time. After a restart, exclude earlier checkpoints from the live forecast so one completed recovery does not get projected indefinitely. Cumulative counts still preserve all prior work. Never divide lifetime cumulative counts by restarted elapsed time. No worker mutation or provider calls.",
                "limitations": "Live checkpoint totals are reported operational state, not an independent replay of result integrity or classification accuracy. Read-only selected records are not a full worker-store preflight. Stopped or stale workers have no live ETA."},
            "question": {"text": "Is the incident-only worker progressing, how many items are processed, and when might its remaining queue finish?"},
            "selection": {"rules": "Only the authorized incident-reports worker's operational metadata, no original article text or new model calls."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD,
                "content": content, "amend_latest": True, "reason": "Register the operational status method before observation"})["id"]
        owner = Path(data["owner"]).resolve(strict=True)
        source = runner.pilot.Source(owner)
        try:
            plan = source.one("full_screen_plan")
            if plan["method"] != runner.METHOD or plan["implementation"] != runner.implementation():
                raise AuditError("monitor_worker_plan_or_code_changed")
            launches, ends, reports, starts = (source.rows(k) for k in
                ("full_screen_launch", "full_screen_run_end", "full_screen_report", "incident_execution_start"))
            provenance = {"owner": str(owner), "head": source.head(), "plan": plan["_record_id"],
                "launch_records": [r["_record_id"] for r in launches],
                "run_end_records": [r["_record_id"] for r in ends],
                "latest_report": reports[-1]["_record_id"] if reports else None}
        finally:
            source.close()
        raw = read_progress(owner / "progress.json")
        progress = json.loads(raw)
        if progress["corpus"] != runner.CORPUS or progress["planned"] != plan["dispositions"]["ready"]:
            raise AuditError("monitor_checkpoint_scope_mismatch")
        matched = workers(owner)
        now = datetime.now(timezone.utc)
        stop = (owner / "STOP").exists()
        previous = [r for r in self.rows("incident_progress_observation") if r["provenance"]["plan"] == plan["_record_id"]]
        latest_launch = launches[-1] if launches else None
        prior_ends = [r for r in ends if latest_launch and r["finished_at"] < latest_launch["started_at"]]
        baseline = prior_ends[-1]["new_responses"] if prior_ends else 0
        matching_starts = [r for r in starts if r["next_launch_number"] == len(launches)]
        if matching_starts:
            baseline = matching_starts[-1]["saved_response_baseline"]
        current_execution = checkpoint_is_current(progress, launches, matched)
        timing = rate_and_eta(progress, previous, now, current_execution, baseline,
                              latest_launch["started_at"] if latest_launch else None)
        report_current = bool(reports and reports[-1]["new_responses"] >= progress["new_responses"] and
                              (not latest_launch or (ends and ends[-1]["finished_at"] >= latest_launch["started_at"])))
        deadline = plan["parent"]["original_deadline"]
        unknown = round(progress["new_holds_usd"] * 1e9 / runner.base.RESERVATION)
        result = {"versions": versions, "observed_at": utc(), "observed_amsterdam": amsterdam(now),
            "provenance": provenance, "progress": progress, "checkpoint_sha256": hashlib.sha256(raw).hexdigest(),
            "checkpoint_artifact": self.ledger.artifacts.put_bytes(raw),
            "live_python_processes": matched, "user_stop_present": stop,
            "processed_including_reuse": progress["new_responses"] + plan["dispositions"]["reused"],
            "total_articles": plan["selected_articles"], "reused_results": plan["dispositions"]["reused"],
            "percent_processed": 100 * (progress["new_responses"] + plan["dispositions"]["reused"]) / plan["selected_articles"],
            "new_unresolved_holds_reported": unknown,
            "total_cost_usd_with_margin": progress["new_cost_usd_with_margin"] + plan["parent"]["cost_nanousd"] / 1e9,
            "total_holds_usd": progress["new_holds_usd"] + progress["inherited_holds_usd"],
            "budget_usd": plan["initial_total_budget_nanousd"] / 1e9,
            "original_deadline": deadline, "deadline_expired": now >= datetime.fromisoformat(deadline),
            "latest_report_current": report_current,
            "final_coverage": {k: reports[-1][k] for k in ("new_valid_results", "unresolved_attempts", "not_attempted", "dispatch_complete", "labels")} if report_current else None,
            "state": "starting_or_waiting_first_checkpoint" if matched and not current_execution else
                     "running" if matched and timing["checkpoint_age_seconds"] <= 300 else
                     "running_needs_investigation" if matched else "stopped",
            "restart_requires_fresh_full_worker_preflight": True,
            "count_meaning": "Saved responses including errors/unknowns, plus reused pilot results; not a count of validated classifications.",
            **timing}
        identifier = self.ledger.record(session, "incident_progress_observation", digest(result), result)
        temporary = self.ledger.root / "latest-progress.writing"
        temporary.write_text(json.dumps({"id": identifier, **result}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.ledger.root / "latest-progress.json")
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=runner.pilot.BASE / METHOD)
    parser.add_argument("--owner", type=Path, default=runner.pilot.BASE / runner.METHOD)
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {"owner": str(args.owner)},
            objective="Observe the authorized incident-only run, cumulative progress, costs and provisional completion ETA",
            actor="codex:incident-progress-monitor"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
