#!/usr/bin/env python3
"""Execute only an explicitly approved query-tagging plan, with a process-local online override."""
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
    parser.add_argument("--reuse-cache", action="store_true")
    parser.add_argument("--max-requests", type=int, default=1)
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution and a plan-bound approval policy are required")
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=False)
    engine = Research(args.workspace, config=config)
    try:
        print(json.dumps({"stage": "audit_preflight", "operation": "tag"}), flush=True)
        result = engine.execute("tag", {"plan": args.plan, "approval_policy": args.approval_policy,
            "max_requests": args.max_requests, "reuse_cache": args.reuse_cache},
            versions=context.get("versions", context), actor=args.actor,
            objective="Execute the explicitly authorized corpus-wide query tagging plan through the shared gateway")
        summary = {k: v for k, v in result.items() if k not in {"items", "source_ids", "missing_task_keys"}}
        summary["missing_task_count"] = len(result["missing_task_keys"])
        print(json.dumps(summary, indent=2), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
