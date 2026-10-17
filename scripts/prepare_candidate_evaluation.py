"""Freeze the independently randomized coverage-guarded candidate evaluation offline."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_candidate_evaluation import CandidateEvaluationResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--candidate-result", required=True)
    parser.add_argument("--original-plan", default="98f9d19f9345e502685538a1c1bee7435bdeff65e30918ea522f56961c360d3b")
    parser.add_argument("--fine-grid", action="store_true")
    parser.add_argument("--previous-plan", help="Required with --fine-grid: the completed v2 candidate plan; only pair IDs are read")
    args = parser.parse_args()
    if args.fine_grid != bool(args.previous_plan):
        parser.error("--fine-grid and --previous-plan must be supplied together")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = CandidateEvaluationResearch(args.workspace, config=replace(config, offline=True))
    try:
        payload = {"phase": "prepare_fine_candidate_pairs" if args.fine_grid else "prepare_candidate_pairs",
            "candidate_result": args.candidate_result, "original_plan": args.original_plan}
        if args.fine_grid:
            payload["previous_plan"] = args.previous_plan
        result = engine.execute("luna_group_validation", payload,
            objective="Freeze an independent full-support pair evaluation of the fixed-grid coverage-guarded split candidate without old label reads or model execution",
            actor="codex:candidate-pair-preparation")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"plan": result["id"], "study_key": result["study_key"],
            "presentation": result["presentation"]["id"], "model_authorized": False}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
