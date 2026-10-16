"""Check saved event grouping across wider publication windows, entirely offline."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

# Process-local numerical thread limits; never change machine/user settings.
for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[name] = "1"

from newsresearch.common import Config, default_workspace  # noqa: E402
from newsresearch.runtime import Research  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--parent-result", required=True)
    parser.add_argument("--diagnostic-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append
        last = 0.

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            nonlocal last
            sequence = original(session, kind, value, *rest)
            if kind in {"event_temporal.intended", "event_temporal.metadata.completed", "event_temporal.summary.intended"} or (
                    kind == "event_temporal.batch.completed" and time.monotonic() - last >= 10):
                print(json.dumps({"stage": kind, **value}), flush=True)
                last = time.monotonic()
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_model_calls": 0, "new_embeddings": 0}), flush=True)
        result = engine.execute("check_event_time_spans", {"parent_result": args.parent_result,
            "diagnostic_key": args.diagnostic_key, "user_instruction": args.user_instruction,
            "output_directory": str(args.output_directory)},
            objective="Check whether the seven-day publication gate excludes plausible event-report links using saved vectors, original references and provider IDs",
            actor="codex:offline-event-temporal-diagnostic")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
