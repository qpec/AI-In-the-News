#!/usr/bin/env python3
"""Execute only an explicitly approved embedding plan with a process-local online override."""

import argparse
from dataclasses import replace
import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research


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
    try:
        result = engine.execute(
            "embed",
            {"plan": args.plan, "approval_policy": args.approval_policy, "max_requests": args.max_requests},
            objective="Execute the specifically authorized OpenAI embedding plan through the shared gateway",
            actor=args.actor,
            versions=context["versions"],
        )
        print(json.dumps({key: value for key, value in result.items() if key != "items"}, indent=2))
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
