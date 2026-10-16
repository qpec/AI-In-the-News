"""Prepare full-source cross-window event review offline; never dispatch a model."""
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
    parser.add_argument("--previous-result", required=True)
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind in {"event_group_evidence.intended", "event_group_evidence.frozen"}:
                print(json.dumps({"stage": kind, **value}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_models": 0, "new_embeddings": 0}), flush=True)
        result = engine.execute("prepare_cross_window_event_review", {
            "previous_result": args.previous_result, "study_key": args.study_key,
            "output_directory": str(args.output_directory)},
            objective="Prepare bounded complete-source same-event review between separate seven-day groups while retaining sealed holdout and original cumulative attempt limits",
            actor="codex:cross-window-event-evidence-preparation")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
