#!/usr/bin/env python3
"""Execute only an explicitly approved embedding plan with a process-local online override."""

import argparse
from dataclasses import replace
import getpass
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research


def report_durable_progress(engine: Any) -> None:
    """Observe completed audit writes; never replace their validation or transaction."""
    append = engine.ledger.append
    completed = 0

    def observed_append(session: str, kind: str, payload: dict[str, Any], projection: Any = None) -> int:
        nonlocal completed
        event = append(session, kind, payload, projection)
        if kind == "model.attempt.completed":
            completed += 1
            if completed == 1 or completed % 25 == 0 or payload["status"] != "valid":
                print(
                    json.dumps(
                        {
                            "event": "embedding_progress",
                            "new_requests_completed": completed,
                            "last_status": payload["status"],
                            "http_status": payload.get("http_status"),
                        }
                    ),
                    flush=True,
                )
        return event

    engine.ledger.append = observed_append


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approval-policy", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required in addition to a plan-bound approval policy")
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    project = Path(__file__).resolve().parents[1]
    config = replace(Config.load(project / "research.toml"), offline=False)
    engine = Research(args.workspace, config=config)
    report_durable_progress(engine)
    try:
        result = engine.execute(
            "embed",
            {"plan": args.plan, "approval_policy": args.approval_policy, "max_requests": args.max_requests},
            objective="Execute the specifically authorized OpenAI embedding plan through the shared gateway",
            actor=args.actor,
            versions=context["versions"],
        )
        summary = {key: value for key, value in result.items() if key not in {"items", "missing_task_keys"}}
        summary["missing_task_count"] = len(result["missing_task_keys"])
        print(json.dumps(summary, indent=2), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
