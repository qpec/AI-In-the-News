"""Prepare or execute the new audited pair evaluator; old queues are never resumed."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any

from newsresearch.common import Config
from newsresearch.event_eval_workflow import APPROVAL_METHOD, DEFAULT_STUDY, EventEvaluationResearch, OLD_RESULT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "review-template", "import-reviews"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--original-result", default=OLD_RESULT)
    parser.add_argument("--study-key", default=DEFAULT_STUDY)
    parser.add_argument("--plan")
    parser.add_argument("--approval-policy")
    parser.add_argument("--approve-codex-run", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--approval-instruction")
    parser.add_argument("--expires-at")
    parser.add_argument("--reviewer")
    parser.add_argument("--reviews-file", type=Path)
    parser.add_argument("--actor", default="codex:fast-event-evaluation")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = EventEvaluationResearch(args.workspace, config=replace(config, offline=args.phase != "run"))
    original = engine._record_presentation

    def display(session: str, context: Any, data: dict[str, Any]) -> dict[str, Any]:
        saved = original(session, context, data)
        print(saved["markdown"], flush=True)
        print(json.dumps({"result": data["results"][0], "presentation": saved["content_path"]}), flush=True)
        return saved

    setattr(engine, "_record_presentation", display)
    try:
        started = time.perf_counter()
        if args.phase == "prepare":
            if args.approve_codex_run or args.approval_policy:
                parser.error("Preparation is offline; no model permission is accepted")
            payload = {"phase": "prepare_pairs", "original_result": args.original_result, "study_key": args.study_key}
        elif args.phase in {"review-template", "import-reviews"}:
            if not args.plan or args.approve_codex_run or args.approval_policy:
                parser.error("Review needs an exact plan and accepts no model authorization")
            payload = {"phase": "review_template", "plan": args.plan}
            if args.phase == "import-reviews":
                if not args.reviewer or not args.reviews_file or not args.actor.startswith("human:"):
                    parser.error("Human import needs --reviewer, --reviews-file and explicit --actor human:NAME")
                payload = {"phase": "import_reviews", "plan": args.plan,
                    "reviewer": args.reviewer, "reviews_file": str(args.reviews_file)}
        else:
            if not args.plan:
                parser.error("Run needs the exact prepared --plan")
            if args.approval_policy and args.approve_codex_run:
                parser.error("Reuse an exact approval policy or supply one concrete approval, not both")
            payload = {"phase": "execute_pairs", "plan": args.plan, "study_key": args.study_key,
                "approval_policy": args.approval_policy, "reuse_cache": True}
            if args.approve_codex_run:
                if not all((args.approved_by, args.approval_instruction, args.expires_at)):
                    parser.error("Explicit approval needs --approved-by, --approval-instruction and --expires-at")
                # These fixed maxima bind the reviewed 64-pair + four-canary plan;
                # the adapter rejects a different actual plan or approval envelope.
                payload = {"phase": "approve_pairs", "plan": args.plan, "study_key": args.study_key,
                    "reuse_cache": True, "approval": {"method": APPROVAL_METHOD, "plan": args.plan,
                        "study_key": args.study_key, "max_requests": 68, "max_article_exposures": 136,
                        "max_retries": 0, "allow_codex_account_execution": True, "allow_external_processing": True,
                        "approved_by": args.approved_by, "instruction": args.approval_instruction,
                        "expires_at": args.expires_at}}
            elif not args.approval_policy:
                parser.error("A new run needs concrete approval; old Luna approvals cannot be reused")
        result = engine.execute("luna_group_validation", payload,
            objective="Repair event-group evaluation with mechanically audited replay and a frozen full-support pair sample; preserve uncertainty and original groups",
            actor=args.actor)
        print(json.dumps({"id": result["id"], "method": result["method"], "status": result.get("status"),
            "wall_seconds": time.perf_counter() - started, "model_authorized": result.get("model_authorized", False)}), flush=True)
        return 0 if args.phase != "run" or result["status"] == "complete" else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
