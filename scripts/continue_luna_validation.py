"""Diagnose and continue untouched Luna tasks in one audited operation."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--result", required=True)
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--continue-untouched", action="store_true")
    parser.add_argument("--authorization-instruction", required=True)
    parser.add_argument("--actor", default="codex:luna-group-validation")
    parser.add_argument("--quarantine-local-timeouts", action="store_true")
    parser.add_argument("--supersedes-control")
    args = parser.parse_args()
    if not args.continue_untouched:
        parser.error("Explicit --continue-untouched is required; failed calls are never retried")
    if args.supersedes_control and not args.quarantine_local_timeouts:
        parser.error("--supersedes-control requires explicit --quarantine-local-timeouts")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    config = replace(Config.load(project / "research.toml"), offline=False)
    engine = Research(args.workspace, config=config)
    append = engine.ledger.append
    present = engine._record_presentation

    def progress(session: str, kind: str, value: dict[str, Any], projection: Any = None) -> int:
        event = append(session, kind, value, projection)
        if kind == "luna.continuation.task.completed":
            print(json.dumps({"stage": kind, **value}), flush=True)
        return event

    def display(session: str, context: Any, data: dict[str, Any]) -> dict[str, Any]:
        saved = present(session, context, data)
        print(saved["markdown"], flush=True)
        print(json.dumps({"stage": "saved_presentation", "result": data["results"][0],
            "presentation": saved["content_path"]}), flush=True)
        return saved

    setattr(engine.ledger, "append", progress)
    setattr(engine, "_record_presentation", display)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "phase": "continue_untouched"}), flush=True)
        payload = {
            "result": args.result, "study_key": args.study_key, "continue_untouched": True,
            "authorization_instruction": args.authorization_instruction, "reuse_cache": True, "workers": 4}
        if args.quarantine_local_timeouts:
            payload["quarantine_local_timeouts"] = True
            if args.supersedes_control:
                payload["supersedes_control"] = args.supersedes_control
        result = engine.execute("luna_group_validation_continue", payload,
            objective="Diagnose failed Luna responses and evaluate untouched frozen group and anchor tasks in parallel within the original cumulative budget; no retries",
            actor=args.actor)
        print(json.dumps({"result": result["id"], "status": result["status"],
            "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
