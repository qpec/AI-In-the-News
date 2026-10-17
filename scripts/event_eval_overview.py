"""Print an exact audited overview of a completed or partial frozen pair run."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_eval_overview import EventEvaluationOverviewResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--target-protocol", required=True)
    parser.add_argument("--actor", default="codex:fast-pair-result-overview")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = EventEvaluationOverviewResearch(args.workspace, config=replace(config, offline=True))
    try:
        result = engine.execute("luna_group_validation", {"phase": "pair_target_overview",
            "result": args.result, "target_protocol": args.target_protocol},
            objective="Present the frozen pair-evaluation results against the preregistered 90% model-reference precision target",
            actor=args.actor)
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "original_result": args.result,
            "presentation": result["presentation"]["id"], "target_status": result["target_status"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
