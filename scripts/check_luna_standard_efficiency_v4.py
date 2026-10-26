"""Audited, read-only Standard admission utilization and recorded output pace."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "luna-standard-efficiency-v4"
QUERY = """SELECT a.intended_epoch,a.rate_tokens,c.input_tokens
    FROM standard_attempts a LEFT JOIN counts c USING(custom_id)
    WHERE a.intended_epoch>? AND a.intended_epoch<=? ORDER BY a.intended_epoch"""


def require(condition, code):
    if not condition:
        raise AuditError(code)


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def utilization(rows, now, started, seconds, tpm, initial_tpm):
    """Reservations, not consumed or generated tokens; (start, end] windows."""
    start = max(started, now - seconds)
    elapsed = now - start
    require(elapsed > 0 and 0 < tpm <= initial_tpm <= 2_000_000, "efficiency_window_or_ceiling")
    selected = [r for r in rows if start < r[0] <= now]
    require(all(r[2] is not None and r[1] == r[2] + 4096 for r in selected), "reservation_count_mismatch")
    reserved = sum(r[1] for r in selected)
    exact_input = sum(r[2] for r in selected)
    lower, upper = [reserved / (ceiling * elapsed / 60) * 100 for ceiling in (initial_tpm, tpm)]
    # The registered runner only lowers limits. Identical beginning/current
    # ceilings therefore establish an unchanged denominator. Otherwise retain
    # bounds until a later check has a comparable unchanged observation window.
    exact = lower if initial_tpm == tpm else None
    return {"requested_seconds": seconds, "observed_seconds": elapsed,
        "start_epoch": start, "end_epoch": now, "warmup": elapsed < seconds,
        "admissions": len(selected), "reserved_tokens": reserved,
        "exact_input_tokens": exact_input, "maximum_output_tokens": reserved - exact_input,
        "reserved_tokens_per_minute": reserved * 60 / elapsed,
        "utilization_percent": exact, "utilization_bounds_percent": [lower, upper],
        "target_percent": 80, "target_met": None if exact is None else exact >= 80}


def output_pace(progresses):
    """Comparable cumulative handoff saves, never run-local return counters."""
    require(bool(progresses), "missing_progress_history")
    latest = progresses[-1]
    now = epoch(latest["updated_at"])
    options = [p for p in progresses[:-1] if 900 <= now - epoch(p["updated_at"]) <= 3600]
    baseline = options[-1] if options else progresses[0]
    elapsed = now - epoch(baseline["updated_at"])
    delta = latest["new_returned"] - baseline["new_returned"]
    require(elapsed >= 0 and delta >= 0, "nonmonotonic_progress")
    rate = delta * 60 / elapsed if elapsed else None
    remaining = sum(c["unsubmitted"] + c["pending"] for c in latest["corpora"].values()) - latest["count_held"]
    return {"basis": "recent_recorded_progress" if options else "overall_current_execution_fallback",
        "from": baseline["updated_at"], "to": latest["updated_at"], "elapsed_seconds": elapsed,
        "new_saved": delta, "saved_per_minute": rate, "remaining_eligible_including_pending": remaining,
        "held_count_excluded": latest["count_held"],
        "remaining_runtime_hours": remaining / rate / 60 if rate and rate > 0 else None,
        "new_saved_by_corpus": {c: v["returned"] - baseline["corpora"][c]["returned"] for c, v in latest["corpora"].items()}}


def read_progress(owner, launch, plan, amendment):
    path = Path(launch["stdout"]).resolve()
    require(path.parent == owner.resolve(), "log_outside_owner")
    check_permissions(path)
    observations = []
    startup = execution = False
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            if not line.endswith("\n"):
                break  # A live writer can have an unfinished final line.
            value = json.loads(line)
            if value.get("phase") == "startup_preflight":
                startup = value["pid"] == launch["worker_pid"] and Path(value["workspace"]).resolve() == owner.resolve()
            if value.get("phase") == "execution_started":
                execution = (value["pid"], value["plan"], value["amendment"]) == (launch["worker_pid"], plan, amendment)
            if all(k in value for k in ("updated_at", "corpora", "new_returned", "standard_control")):
                require((value["pid"], value["plan"], value["amendment"]) == (launch["worker_pid"], plan, amendment), "progress_execution_binding")
                observations.append(value)
    require(startup and execution and observations, "missing_current_execution")
    return observations


class Efficiency(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve()
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "source_owner": str(owner), "plan": data["plan"], "amendment": data["amendment"],
            "query": QUERY, "procedure": "Short read-only operational transaction; preserve exact selected time/token rows. Measure exact input plus frozen 4096 maximum-output reservations against effective TPM over 60/900 seconds. Limits only decrease; if denominator changed, report bounds. Compare cumulative recorded handoff saves over 15-60 minutes, with labeled execution fallback. Diagnose new cost holds from saved result/receipt metadata and hash-verified provider errors. No model calls, source changes, inference, or semantic-quality claim."}})["id"]
        check_permissions(owner, root=True)
        def read(name):
            path = owner / name
            check_permissions(path)
            return json.loads(path.read_text(encoding="utf-8-sig"))
        launch, amendment = read("launch.json"), read("finish-plan.json")
        require(launch["runner"] == "scripts/luna_standard_finish_v3.py"
            and launch["plan"] == amendment["plan"] == data["plan"]
            and launch["amendment"] == amendment["id"] == data["amendment"]
            and amendment["method"] == "luna-standard-finish-v3", "owner_binding")
        observations = read_progress(owner, launch, data["plan"], data["amendment"])
        started = epoch(launch["launched_at"])  # Include startup preparation in elapsed utilization.
        database = owner / "state.sqlite3"
        check_permissions(database)
        db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            control = {r[0]: json.loads(r[1]) for r in db.execute("SELECT key,value FROM standard_control")}
            observed = time.time()
            rows = list(db.execute(QUERY, (max(started, observed - 900), observed)))
            inflight = db.execute("SELECT COUNT(*) FROM standard_attempts WHERE status!='saved'").fetchone()[0]
            holds = [dict(zip(("custom_id", "status", "charged_nanousd", "reserved_nanousd"), row, strict=True))
                for row in db.execute("SELECT custom_id,status,charged_nanousd,reserved_nanousd FROM budget_entries WHERE status IN ('unknown','frozen','overrun')")]
        finally:
            db.close()
        new_holds = [row for row in holds if row["custom_id"] not in amendment["inherited_cost_holds"]]
        diagnostics = []
        if new_holds:
            journal = owner / "research.sqlite3"
            check_permissions(journal)
            source = sqlite3.connect(journal.as_uri() + "?mode=ro", uri=True, timeout=2)
            try:
                source.execute("PRAGMA query_only=ON")
                for held in new_holds:
                    for row in source.execute("""SELECT records.id,json_extract(j.value,'$.receipt'),
                        json_extract(j.value,'$.item.errors'),json_extract(j.value,'$.item.usage'),
                        json_extract(j.value,'$.item.usage_complete'),json_extract(j.value,'$.item.observed_model'),
                        json_extract(j.value,'$.item.technical_failure'),json_extract(j.value,'$.cost.request.input_count.input_tokens')
                        FROM records,json_each(records.payload,'$.items') AS j
                        WHERE records.kind='luna_standard_api_result_bundle' AND json_extract(j.value,'$.custom_id')=?""", (held["custom_id"],)):
                        diagnostics.append({**held, "result_record": row[0], "receipt": json.loads(row[1]),
                            "errors": json.loads(row[2]) if row[2] else None,
                            "usage": json.loads(row[3]) if row[3] else None,
                            "usage_complete": row[4], "observed_model": row[5], "technical_failure": row[6], "exact_input_tokens": row[7]})
            finally:
                source.close()
            for diagnostic in diagnostics:
                receipt = diagnostic["receipt"]
                reference = receipt.get("body_ref")
                if reference and receipt.get("status") != 200:
                    require(len(reference) == 64 and all(c in "0123456789abcdef" for c in reference), "invalid_error_artifact")
                    path = owner / "objects" / reference
                    check_permissions(path)
                    raw = path.read_bytes()
                    require(hashlib.sha256(raw).hexdigest() == reference == receipt["body_sha256"], "error_artifact_hash")
                    if len(raw) <= 4096:
                        try:
                            error = json.loads(raw).get("error")
                        except (ValueError, UnicodeError, AttributeError):
                            error = None
                        if isinstance(error, dict):
                            diagnostic["provider_error"] = {k: error.get(k) for k in ("code", "type", "param", "message")}
        initial_tpm = observations[0]["standard_control"]["tpm"]
        windows = []
        for seconds in (60, 900):
            previous = [p for p in observations if epoch(p["updated_at"]) <= observed - seconds]
            ceiling = previous[-1]["standard_control"]["tpm"] if previous else initial_tpm
            windows.append(utilization(rows, observed, started, seconds, control["tpm"], ceiling))
        inputs = {"columns": ["intended_epoch", "rate_tokens", "input_tokens"], "rows": rows,
            "snapshot_epoch": observed, "control": control, "launch": launch,
            "recorded_progress": observations}
        source_record = self.ledger.record(session, "luna_standard_efficiency_inputs", data["plan"], inputs)
        result = {"checked_at": utc(), "protocol": protocol, "source_owner": str(owner),
            "plan": data["plan"], "amendment": data["amendment"], "inputs": source_record,
            "worker_pid": launch["worker_pid"], "worker_created_at": launch.get("worker_created_at"),
            "process_identity_requires_os_check": True, "source_state_modified": False, "new_model_calls": 0,
            "effective_tpm": control["tpm"], "effective_rpm": control["rpm"], "inflight": inflight,
            "worker_ceiling": 64, "windows": windows, "recorded_output_pace": output_pace(observations),
            "new_cost_holds": diagnostics, "policy_quarantined": observations[-1].get("policy_quarantined", 0), "all_cost_holds": holds,
            "latest_recorded_progress": observations[-1], "stop_present": (owner / "STOP").exists(),
            "semantic_accuracy_confirmed": False,
            "basis": "Admitted token reservations, not actual provider token consumption or saved-output throughput. Checks observe intervals; they cannot guarantee continuous 80% efficiency."}
        identifier = self.ledger.record(session, "luna_standard_efficiency", data["plan"], result)
        output = {"id": identifier, **result}
        temporary = self.ledger.root / "latest-efficiency.tmp"
        temporary.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.ledger.root / "latest-efficiency.json")
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source-owner", required=True, type=Path)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--amendment", required=True)
    args = parser.parse_args()
    engine = Efficiency(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner), "plan": args.plan, "amendment": args.amendment},
            objective="Measure the authorized Standard run against the user's 80 percent efficiency target", actor="codex:efficiency-monitor")
        print(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
