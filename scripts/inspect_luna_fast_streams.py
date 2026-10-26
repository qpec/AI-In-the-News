"""Registered inspection of saved CLI event shapes; no source text or model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from newsresearch.common import Config, require_no_credentials
from newsresearch.gateway import ProviderResponse
from newsresearch.luna_fast_provider_v2 import recover_terminal
from newsresearch.luna_speed_provider import contract, validate_response
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import WorkspaceLock, check_permissions

import lean_luna_state as state


class StreamResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": "luna-fast-stream-shapes-v3",
            "content": {"method": "Inspect CLI event shapes and operational errors; replay saved terminal outputs through the tested v2 recovery parser and unchanged mechanical validator. Return no agent-message text or article content; no model calls, retries or original status changes.",
                        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        "parser_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "src/newsresearch/luna_fast_provider_v2.py").read_bytes()).hexdigest(),
                        "contract_digest": contract.contract_digest(),
                        "parent_full_history_replayed": False}})["id"]
        owner = Path(data["owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        self.ledger.append(session, "fast.stream.inspection.intended", {
            "owner": str(owner), "result": data["result"], "sql": "SELECT * FROM records WHERE id=?"})
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
            streams = []
            for outcome in value["outcomes"]:
                if outcome["status"] != "unknown":
                    continue
                saved = artifacts.json(outcome["response"])
                raw = saved["raw_response"]
                if raw.get("contract_digest") != contract.contract_digest() or raw.get("configured_model") != "gpt-6-luna":
                    raise ValueError("saved response contract/model binding differs")
                replay = recover_terminal(ProviderResponse(**saved))
                errors = contract.validate_packet(raw["packet"]) or validate_response(replay, raw["packet"])
                shapes = []
                for event in raw.get("events", []):
                    item = event.get("item") or {}
                    shape = {"type": event.get("type"), "event_keys": sorted(event)}
                    if item:
                        shape.update(item_type=item.get("type"), item_keys=sorted(item),
                                     phase=item.get("phase"), channel=item.get("channel"), id=item.get("id"))
                        if item.get("type") == "error":
                            shape["error_message"] = item.get("message")
                        text = item.get("text") or ""
                        try:
                            decoded = json.loads(text)
                            shape["message_is_json_object"] = isinstance(decoded, dict)
                            shape["json_keys"] = sorted(decoded) if isinstance(decoded, dict) else []
                        except ValueError:
                            shape["message_is_json_object"] = False
                        shape["text_characters"] = len(text)
                    if event.get("type") == "error":
                        message = event.get("message") or ""
                        shape["reconnecting"] = message.startswith("Reconnecting...")
                        shape["websocket_403"] = "403 Forbidden" in message and "wss://" in message
                    shapes.append(shape)
                streams.append({"attempt": outcome["attempt"], "response": outcome["response"],
                                "exit_code": raw.get("exit_code"), "events": shapes,
                                "recovered_transport": replay.raw_response.get("recovered_transport"),
                                "mechanically_valid_replay": not errors, "replay_errors": errors,
                                "focus": replay.payload.get("focus") if not errors else None,
                                "original_hold_unchanged": True})
            result = {"protocol": protocol, "source_result": data["result"], "streams": streams,
                      "counts": dict(Counter(r["status"] for r in value["outcomes"])),
                      "model_calls": 0, "status_changes": 0, "parent_full_history_replayed": False,
                      "verified_artifacts": sorted(artifacts.checked)}
            require_no_credentials(result)
            identifier = self.ledger.record(session, "luna_fast_stream_shapes", data["result"], result)
            return {"id": identifier, **result}
        finally:
            lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--owner", type=Path, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    engine = StreamResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"owner": str(args.owner), "result": args.result},
            objective="Inspect held Fast response event shapes to implement correct terminal completion handling",
            actor="codex:luna-fast-stream-repair")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
