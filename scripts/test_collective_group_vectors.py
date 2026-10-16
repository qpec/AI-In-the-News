"""Test collective group-vector mapping offline through the audited runtime."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
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
    parser.add_argument("--reference-result", required=True)
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append
        started = time.perf_counter()

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            if kind == "centroid_merge.intended":
                value["preflight_and_registration_seconds"] = time.perf_counter() - started
            sequence = original(session, kind, value, *rest)
            if kind in {"centroid_merge.intended", "centroid_merge.frozen"}:
                print(json.dumps({"stage": kind, **value}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_models": 0, "new_embeddings": 0}), flush=True)
        result = engine.execute("test_collective_group_vectors", {"reference_result": args.reference_result,
            "study_key": args.study_key, "instruction": args.instruction, "output_directory": str(args.output_directory)},
            objective="Test fast collective group-vector mapping on all current seven-day groups using existing embeddings and frozen model references without new inference",
            actor="codex:offline-collective-group-vector-test")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
