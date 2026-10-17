"""Prepare saved-text event mentions offline, or execute one separately approved plan."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_extraction_workflow import (
    APPROVAL_METHOD, DEFAULT_STUDY, ORIGINAL_RESULT, EventExtractionResearch,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--original-result", default=ORIGINAL_RESULT)
    parser.add_argument("--study-key", default=DEFAULT_STUDY)
    parser.add_argument("--plan")
    parser.add_argument("--approval-policy")
    parser.add_argument("--approve-codex-run", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--approval-instruction")
    parser.add_argument("--expires-at")
    parser.add_argument("--actor", default="codex:event-extraction-pilot")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.phase == "prepare":
        if any((args.plan, args.approval_policy, args.approve_codex_run, args.approved_by,
                args.approval_instruction, args.expires_at)):
            parser.error("Preparation accepts no model authorization or previous extraction plan")
        payload = {"phase": "prepare", "original_result": args.original_result, "study_key": args.study_key}
    else:
        if not args.plan or bool(args.approval_policy) == args.approve_codex_run:
            parser.error("Run needs --plan and exactly one of --approval-policy or --approve-codex-run")
        payload = {"phase": "execute", "plan": args.plan,
                   "approval_policy": args.approval_policy, "reuse_cache": True}
        if args.approve_codex_run:
            if not all((args.approved_by, args.approval_instruction, args.expires_at)):
                parser.error("Concrete authorization needs --approved-by, --approval-instruction and --expires-at")
            payload = {"phase": "approve", "plan": args.plan, "reuse_cache": True,
                "approval": {"method": APPROVAL_METHOD, "plan": args.plan, "study_key": args.study_key,
                    "max_requests": 12, "max_article_exposures": 12, "max_retries": 0,
                    "allow_codex_account_execution": True, "allow_external_processing": True,
                    "approved_by": args.approved_by, "instruction": args.approval_instruction,
                    "expires_at": args.expires_at}}
        elif any((args.approved_by, args.approval_instruction, args.expires_at)):
            parser.error("Exact approval reuse accepts no replacement approval metadata")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = EventExtractionResearch(args.workspace, config=replace(config, offline=args.phase == "prepare"))
    try:
        result = engine.execute("luna_group_validation", payload,
            objective="Extract evidence-backed event mentions from complete saved articles without re-embedding; prepare a bounded development pilot and preserve uncertainty",
            actor=args.actor)
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"],
            "study_key": result["study_key"], "review_template_path": result.get("review_template_path"),
            "new_embeddings": 0}), flush=True)
        return 0 if args.phase == "prepare" or result["status"] == "complete" else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
