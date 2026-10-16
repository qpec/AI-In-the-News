"""Compare and apply one offline refinement using the saved event-pair scores."""
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
    parser.add_argument("--parent-result", required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind in {"event_groups.refinement.intended", "event_groups.refinement.frozen"}:
                print(json.dumps({"stage": kind, **value}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_model_calls": 0, "new_embeddings": 0}), flush=True)
        result = engine.execute("refine_event_groups", {"parent_result": args.parent_result,
            "comparison_key": args.comparison_key, "user_instruction": args.user_instruction,
            "output_directory": str(args.output_directory)},
            objective="Improve provisional event-group packing using saved scores and compare against the unchanged baseline and original development references",
            actor="codex:offline-event-group-refinement")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
