"""Keep the seven-day working groups and propose strongly anchored longer links."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--comparison-result", required=True)
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--superseded-instruction", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind in {"event_group_links.intended", "event_group_links.frozen"}:
                print(json.dumps({"stage": kind, **value}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_models": 0, "new_embeddings": 0}), flush=True)
        result = engine.execute("propose_cross_window_group_links", {
            "comparison_result": args.comparison_result, "study_key": args.study_key, "instruction": args.instruction,
            "superseded_instruction": args.superseded_instruction, "output_directory": str(args.output_directory)},
            objective="Record the user's seven-day working choice and test conservative provider-anchored complete-group links across longer reporting gaps",
            actor="codex:seven-day-choice-and-group-link-proposals")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "policy": result["policy"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
