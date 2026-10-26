"""Audited technical timing/error diagnosis; no article text or model calls."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
from statistics import median

from newsresearch.common import AuditError, Config, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state
import luna_standard_recovery as recovery
from diagnose_luna_standard import response_metadata

METHOD = "luna-standard-admission-diagnosis-20261019-v1"
SQL = "SELECT * FROM records WHERE kind='luna_standard_assessment' AND json_extract(payload,'$.execution')=? ORDER BY created_event"


def timestamp(value):
    return datetime.fromisoformat(value).timestamp()


def summarize(calls):
    starts = sorted(timestamp(c["started_at"]) for c in calls if c["started_at"])
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    peak = max((sum(start <= other < start + 60 for other in starts) for start in starts), default=0)
    bursts = []
    for call in calls:
        if not call["started_at"]:
            continue
        if not bursts or timestamp(call["started_at"]) - timestamp(bursts[-1]["ended_at"]) > 30:
            bursts.append({"started_at": call["started_at"], "ended_at": call["ended_at"],
                           "returned": 0, "unknown": 0, "valid": 0})
        burst = bursts[-1]
        burst["ended_at"] = call["ended_at"]
        burst["returned"] += 1
        burst["unknown"] += call["status"] == "unknown"
        burst["valid"] += call["status"] == "valid"
    for burst in bursts:
        burst["elapsed_seconds"] = timestamp(burst["ended_at"]) - timestamp(burst["started_at"])
    return {"saved": len(calls), "peak_starts_in_60_seconds": peak,
            "median_start_gap_seconds": median(gaps) if gaps else None,
            "minimum_start_gap_seconds": min(gaps) if gaps else None, "bursts": bursts,
            "failure_categories": dict(Counter(c["category"] for c in calls if c["category"]))}


class AdmissionDiagnosis(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "sql": SQL, "execution": data["execution"],
            "procedure": "Read a consistent snapshot of one saved execution. Verify selected record, response and dispatch artifact hashes and attempt/task bindings. Report only corpus, technical times/status, invocation configuration, usage totals and exact errors matching the existing two observed service-message hashes. Group calls separated by more than 30 seconds after the preceding return. No source or model answer text, credentials, new model calls, retries, or original-state changes.",
            "limits": "Timing associations do not establish a service rate entitlement or causal diagnosis. Missing provider headers remain unavailable."}})["id"]
        self.ledger.append(session, "standard.admission_diagnosis.intended", {**data, "protocol": protocol, "sql": SQL})
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        calls, messages, configurations = [], {}, {}
        try:
            row = conn.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone()
            plan = state.row_value(row, "luna_standard_plan")
            artifacts.check(row["artifact"])
            head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            for row in conn.execute(SQL, (data["execution"],)):
                value = state.row_value(row, "luna_standard_assessment")
                artifacts.check(row["artifact"])
                if value["plan"] not in {data["plan"], *plan.get("capacity_lineage", [])}:
                    raise AuditError("admission_diagnosis_plan_mismatch")
                saved = artifacts.json(value["response"])
                raw = saved.get("raw_response") or {}
                dispatch = artifacts.json(value["dispatch"])
                if raw.get("attempt") != value["attempt"] or raw.get("task_key") != value["task_key"]:
                    raise AuditError("admission_diagnosis_response_binding_mismatch")
                meta = response_metadata(saved)
                for event in raw.get("events", []):
                    message = event.get("message")
                    if isinstance(message, str):
                        digest = hashlib.sha256(message.encode()).hexdigest()
                        if digest in recovery.CAPACITY_MESSAGES:
                            messages[digest] = message
                command = dispatch.get("command", [])
                # These are application-controlled argv, never input/output payloads.
                config = {"executable": command[0] if command else None,
                          "configured_model": dispatch.get("configured_model"),
                          "fast_mode": dispatch.get("fast_mode"),
                          "configured_service_tier": dispatch.get("configured_service_tier")}
                configurations[json.dumps(config, sort_keys=True)] = config
                calls.append({"assessment": row["id"], "attempt": value["attempt"],
                    "corpus": value["corpus_id"], "status": value["status"],
                    "started_at": raw.get("started_at"), "ended_at": raw.get("ended_at"),
                    "category": meta["admission_recovery_category"],
                    "usage": saved.get("usage"), "error_shapes": meta["errors"]})
        finally:
            conn.close()
        result = {"protocol": protocol, **data, "snapshot_head": head, **summarize(calls),
                  "calls": calls, "verified_service_messages": messages,
                  "configurations": list(configurations.values()), "artifacts_hashed": len(artifacts.checked),
                  "checked_at": utc(), "model_calls": 0, "retries": 0, "status_changes": 0}
        require_no_credentials(result)
        identifier = self.ledger.record(session, "luna_admission_diagnosis", data["execution"], result)
        target = self.ledger.root / "latest-admission-diagnosis.json"
        target.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **{k: v for k, v in result.items() if k != "calls"}, "report_path": str(target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--execution", required=True)
    args = parser.parse_args()
    engine = AdmissionDiagnosis(args.workspace, config=Config(offline=True))
    try:
        data = {key: getattr(args, key) for key in ("source_owner", "plan", "execution")}
        print(json.dumps(engine.execute("status", data,
            objective="Diagnose repeated Luna capacity failures and admission timing without new model calls",
            actor="codex:luna-admission-repair"), indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
