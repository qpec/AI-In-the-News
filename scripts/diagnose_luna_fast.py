"""Registered source-free execution diagnostics; no model calls or state repair."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from newsresearch.common import Config, require_no_credentials
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import WorkspaceLock, check_permissions

import lean_luna_state as state
import luna_event_contract_v2 as contract


def terminal_replay(raw):
    """Validate a saved terminal output without changing its original held status."""
    events = raw.get("events", [])
    finals = [e.get("item", {}).get("text") for e in events if e.get("type") == "item.completed"
              and e.get("item", {}).get("type") == "agent_message"]
    if (raw.get("exit_code") != 0 or not events or events[-1].get("type") != "turn.completed"
            or sum(e.get("type") == "turn.completed" for e in events) != 1
            or any(e.get("type") == "turn.failed" for e in events) or len(finals) != 1
            or raw.get("contract_digest") != contract.contract_digest()
            or raw.get("configured_model") != "gpt-6-luna"
            or any(e.get("item", {}).get("type") not in {"agent_message", "reasoning"}
                   for e in events if e.get("type", "").startswith("item."))):
        return {"terminal_completion_candidate": False, "original_hold_unchanged": True}
    try:
        output = json.loads(finals[0])
        packet_errors = contract.validate_packet(raw["packet"])
        errors = packet_errors or contract.validate_output(output, raw["packet"],
                    response_status="completed", response_truncated=False)
    except (ValueError, TypeError, KeyError):
        return {"terminal_completion_candidate": False, "original_hold_unchanged": True}
    return {"terminal_completion_candidate": True, "mechanically_valid_candidate": not errors,
            "errors": errors, "focus": output.get("focus") if not errors else None,
            "original_hold_unchanged": True, "remote_attempt_uniqueness_proven": False}


class DiagnosticResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": "luna-fast-execution-diagnostics-v2",
            "content": {"method": "Selected immutable execution record and unknown-response metadata; mechanically validate saved terminal JSON against its exact retained packet, without new inference, retries or state repair. Raw artifacts contain source packets; no source text is returned.",
                        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "parent_full_history_replayed": False}})["id"]
        owner = Path(data["owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        self.ledger.append(session, "fast.diagnostic.read.intended", {
            "owner": str(owner), "result": data["result"], "record_kind": "luna_fast_result",
            "sql": "SELECT * FROM records WHERE id=?", "purpose": "Technical failure metadata only"})
        lock = WorkspaceLock(owner / "workspace.lock")
        try:
            db = state.read_only_database(owner)
            artifacts = state.SelectedArtifacts(owner)
            try:
                row = db.execute("SELECT * FROM records WHERE id=?", (data["result"],)).fetchone()
                value = state.row_value(row, "luna_fast_result")
                artifacts.check(row["artifact"])
            finally:
                db.close()
            unknown = []
            for item in value["outcomes"]:
                if item["status"] != "unknown":
                    continue
                response = artifacts.json(item["response"])
                raw = response.get("raw_response") or {}
                errors = []
                for event in raw.get("events", []):
                    if event.get("type") in {"error", "turn.failed"}:
                        errors.append({key: event[key] for key in ("type", "message", "error", "code") if key in event})
                unknown.append({"attempt": item["attempt"], "response": item["response"],
                    "failure": raw.get("failure"), "exit_code": raw.get("exit_code"),
                    "event_types": dict(Counter(e.get("type") for e in raw.get("events", []))),
                    "errors": errors, "stderr": (raw.get("stderr") or "")[-3000:],
                    "usage_available": response.get("usage") is not None,
                    "dispatch_offset": item["dispatch_offset"], "return_offset": item["return_offset"],
                    "terminal_replay": terminal_replay(raw)})
            result = {"protocol": protocol, "source_owner": str(owner), "source_result": data["result"],
                "counts": value["counts"], "pending": value["pending"], "timing": {
                    key: value["timing"][key] for key in ("elapsed_seconds", "stop_reason", "peak_in_flight", "stages")},
                "unknown_diagnostics": unknown, "verified_artifacts": sorted(artifacts.checked),
                "model_calls": 0, "retries": 0, "status_changes": 0, "parent_full_history_replayed": False}
            require_no_credentials(result)
            identifier = self.ledger.record(session, "luna_fast_execution_diagnosis", data["result"], result)
            markdown = "Luna Fast execution diagnostics\n\n" + json.dumps(result, ensure_ascii=False, indent=2)
            reference = self.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
            self.ledger.append(session, "presentation.artifact.saved", {
                "artifact": reference, "result": identifier, "status": "prepared_for_delivery",
                "record_presentation_supported": False, "destination": "codex_chat"})
            return {"diagnosis": identifier, **result, "presentation_path": str(self.ledger.artifacts.root / reference)}
        finally:
            lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--owner", type=Path, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    engine = DiagnosticResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"owner": str(args.owner), "result": args.result},
            objective="Diagnose saved unknown outcomes of the bounded Luna Fast run without retrying articles",
            actor="codex:luna-fast-diagnostics")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
