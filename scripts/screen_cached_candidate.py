"""Describe cached pair references surviving one frozen provider candidate; offline only."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_cached_screen import CachedReferenceScreenResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--candidate-result", required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = CachedReferenceScreenResearch(args.workspace, config=replace(config, offline=True))
    try:
        result = engine.execute("luna_group_validation", {"candidate_result": args.candidate_result},
            objective="Describe retained model references surviving the already frozen provider candidate, separately by prior study without new inference",
            actor="codex:cached-provider-candidate-screen")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"], "new_model_calls": 0}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
