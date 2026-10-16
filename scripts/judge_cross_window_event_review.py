"""Execute a concretely authorized frozen review request through audited Codex."""
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
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--request", type=Path, required=True, help="Private request JSON with explicit fresh human authorization")
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding="utf-8"))
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=False)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind == "event_group_evidence.judging_intended":
                print(json.dumps({"stage": kind, "new_primary_tasks": value["new_primary_tasks"]}), flush=True)
            elif kind in {"model.attempt.completed", "model.attempt.unobserved"}:
                print(json.dumps({"stage": kind, "attempt": value["attempt"], "status": value["status"]}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "authorization": "checked by audited operation before dispatch"}), flush=True)
        result = engine.execute("judge_cross_window_event_review", request,
            objective="Judge every pair in a frozen cross-window event-review queue through the authorized Codex gateway while preserving original cumulative limits",
            actor="codex:authorized-cross-window-event-review")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
