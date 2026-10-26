"""Audited, offline metadata inspection of incomplete exact-count actions."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions
import lean_luna_state as state
import luna_batch_remainder as handoff

METHOD = "luna-count-action-diagnostic-v2"


class Diagnostic(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD,
            "content": {"method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_owner": str(owner), "plan": data["plan"],
                "procedure": "Read-only incomplete count-action metadata and exact retained receipt hashes. No source text, model calls, retries, action changes or research inference."}})["id"]
        db = sqlite3.connect((owner / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        journal = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        try:
            actions = []
            for row in db.execute("SELECT * FROM actions WHERE phase='count' AND status!='complete'"):
                action = dict(row)
                item = {"action_id": action["action_id"], "action_sha256": digest(action),
                    "status": action["status"], "intent_metadata": json.loads(action["request_json"])}
                found = []
                for saved in journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (handoff.lean.RECEIPT,)):
                    for member in state.row_value(saved)["members"]:
                        if member["action_id"] != action["action_id"]:
                            continue
                        raw = artifacts.read(member["raw_body_ref"]) if member.get("raw_body_ref") else member.get("raw_body_utf8", "").encode()
                        if raw and hashlib.sha256(raw).hexdigest() != member["body_sha256"]:
                            raise AuditError("count_diagnostic_receipt_hash")
                        receipt = {key: member.get(key) for key in ("status", "unknown", "error_type", "retention_error", "body_sha256", "request_id", "intent")}
                        receipt.update(record_id=saved["id"], receipt_sha256=digest(member), retained_bytes=len(raw))
                        try:
                            error = json.loads(raw).get("error")
                        except (ValueError, UnicodeError, AttributeError):
                            error = None
                        if isinstance(error, dict):
                            receipt["provider_error"] = {key: error.get(key) for key in ("code", "type", "param")}
                        found.append(receipt)
                item["receipts"] = found
                actions.append(item)
            result = {"checked_at": utc(), "protocol": protocol, "source_owner": str(owner),
                "plan": data["plan"], "actions": actions, "new_model_calls": 0, "source_state_modified": False}
            identifier = self.ledger.record(session, "luna_count_action_diagnostic", data["plan"], result)
            return {"id": identifier, **result}
        finally:
            journal.close()
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source-owner", required=True, type=Path)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    engine = Diagnostic(args.workspace, config=Config(offline=True))
    try:
        print(json.dumps(engine.execute("status", {"source_owner": str(args.source_owner), "plan": args.plan},
            objective="Diagnose the stopped exact-count action without retry or source mutation", actor="codex:luna-monitor"), indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
