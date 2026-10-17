"""Prepare a fixed offline coverage grid from the already retained capsule."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_coverage_candidate import CoverageCandidateResearch, PARENT_CANDIDATE


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = CoverageCandidateResearch(args.workspace, config=config)
    try:
        result = engine.execute("refine_event_groups", {"phase": "prepare_coverage_grid", "parent_candidate": PARENT_CANDIDATE,
            "comparison_key": args.comparison_key, "user_instruction": args.user_instruction},
            objective="Freeze a predeclared label-blind margin grid and select one candidate preserving pair and article coverage",
            actor="codex:coverage-guarded-event-candidate")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "candidate_membership": result["candidate_membership"],
                          "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
