"""Prepare one fixed audited split candidate; never run or approve models."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_precision_candidate import PrecisionCandidateResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    parser.add_argument("--actor", default="codex:fixed-precision-candidate")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = PrecisionCandidateResearch(args.workspace, config=config)
    try:
        result = engine.execute("refine_event_groups", {"phase": "prepare_precision_candidate", "plan": args.plan,
            "comparison_key": args.comparison_key, "user_instruction": args.user_instruction},
            objective="Prepare a fixed stricter seven-day event-group candidate using anchored saved features for future fresh evaluation",
            actor=args.actor)
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "candidate_artifact": result["candidate_artifact"],
                          "frame_artifact": result["frame_artifact"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
