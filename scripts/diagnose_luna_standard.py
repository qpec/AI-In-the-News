"""Audited, source-free diagnostics of retained standard Luna failures."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace

from newsresearch.common import AuditError, Config, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state
import luna_standard_recovery as recovery

METHOD = "luna-standard-transport-diagnostics-v2"
UNKNOWN_SQL = "SELECT * FROM records WHERE kind='luna_standard_assessment' AND json_extract(payload,'$.status')='unknown' ORDER BY created_event"


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value) else None


def message_shape(message):
    text = message if isinstance(message, str) else json.dumps(message, sort_keys=True)
    lower = text.lower()
    labels = [key for key, needle in {
        "websocket": "websocket", "websocket_url": "wss://", "reconnect": "reconnecting",
        "https_fallback": "falling back", "quota": "quota", "usage_limit": "usage limit",
        "rate_limit": "rate limit", "capacity": "capacity", "timeout": "timed out",
        "connection": "connection", "stream_disconnect": "stream disconnected",
        "authentication": "authentication", "unauthorized": "unauthorized",
        "token_expired": "token has expired", "refresh_token": "refresh token",
        "audit_hook": "supplementary audit", "schema": "schema",
        "os_error": "os error", "invalid_request": "invalid request",
    }.items() if needle in lower]
    return {"characters": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "labels": labels, "http_statuses": sorted(set(re.findall(r"\b[45]\d\d\b", text)))}


def response_metadata(saved):
    raw = saved.get("raw_response") or {}
    events = raw.get("events") or []
    errors = []
    finals = []
    for event in events:
        item = event.get("item") or {}
        if event.get("type") in {"error", "turn.failed"}:
            errors.append(message_shape(event.get("message") or event.get("error") or {}))
        if item.get("type") == "error":
            errors.append(message_shape(item.get("message") or {}))
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            try:
                finals.append(isinstance(json.loads(item.get("text", "")), dict))
            except (ValueError, TypeError):
                finals.append(False)
    return {"failure": safe_code(raw.get("failure")), "exit_code": raw.get("exit_code"),
            "admission_recovery_category": recovery.capacity_failure(SimpleNamespace(payload=saved.get("payload"), raw_response=raw)),
            "terminal_replay_failure": safe_code(raw.get("terminal_replay_failure")),
            "event_types": dict(Counter(safe_code(e.get("type")) or "unrecognized" for e in events)),
            "item_types": dict(Counter(safe_code((e.get("item") or {}).get("type")) or "unrecognized"
                                       for e in events if e.get("item"))),
            "final_json_objects": finals, "errors": errors,
            "stderr": message_shape(raw.get("stderr") or ""),
            "stdout_characters": len(raw.get("stdout") or ""),
            "timeout_seconds": raw.get("timeout_seconds"), "started_at": raw.get("started_at"),
            "ended_at": raw.get("ended_at"), "original_hold_unchanged": True}


class DiagnosticResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "recovery_classifier_implementation": recovery.implementation(),
            "scope": "Consistent read-only snapshot of unknown assessments in one authorized standard Luna plan lineage. Verify selected record identities and artifact hashes. Return error categories, lifecycle shapes and lengths only; no article/model text, new inference, retry or original-result changes.",
            "full_history_replayed": False, "model_calls": 0}})["id"]
        self.ledger.append(session, "standard.diagnosis.inspection.intended", {
            "source_owner": str(owner), "plan": data["plan"], "protocol": protocol, "sql": UNKNOWN_SQL})
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        try:
            row = conn.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone()
            plan = state.row_value(row, "luna_standard_plan")
            artifacts.check(row["artifact"])
            lineage = {data["plan"], *plan.get("capacity_lineage", [])}
            head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            failures = []
            for row in conn.execute(UNKNOWN_SQL):
                value = state.row_value(row, "luna_standard_assessment")
                if value["plan"] not in lineage:
                    continue
                artifacts.check(row["artifact"])
                saved = artifacts.json(value["response"])
                raw = saved.get("raw_response") or {}
                if raw.get("attempt") != value["attempt"] or raw.get("task_key") != value["task_key"]:
                    raise AuditError("standard_diagnostic_response_binding_mismatch")
                failures.append({"assessment": row["id"], "attempt": value["attempt"],
                    "execution": value["execution"], "corpus": value["corpus_id"],
                    "response": value["response"], **response_metadata(saved)})
        finally:
            conn.close()
        result = {"protocol": protocol, "source_owner": str(owner), "plan": data["plan"],
            "snapshot_head": head, "unknown_count": len(failures), "failures": failures,
            "artifacts_hashed": len(artifacts.checked), "model_calls": 0, "retries": 0,
            "status_changes": 0, "checked_at": utc()}
        require_no_credentials(result)
        identifier = self.ledger.record(session, "luna_standard_transport_diagnosis", data["plan"], result)
        report = self.ledger.root / "latest-diagnosis.json"
        report.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, **result, "report_path": str(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    engine = DiagnosticResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner), "plan": args.plan},
            objective="Diagnose repeated standard Luna transport stops without model calls or retries",
            actor="codex:luna-transport-repair")
        print(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
