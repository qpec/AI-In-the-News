"""Apply the recorded best-coverage event rule to the entire saved pilot, offline."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

# Process-local numerical limits; small passage products otherwise oversubscribe BLAS.
for variable in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "OMP_NUM_THREADS"):
    os.environ[variable] = "1"

from newsresearch.common import Config, default_workspace  # noqa: E402
from newsresearch.runtime import Research  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--parent-result", required=True)
    parser.add_argument("--application-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    try:
        original = engine.ledger.append
        last_print = 0.

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            nonlocal last_print
            sequence = original(session, kind, value, *rest)
            if kind == "event_rule.application.intended" or kind == "event_rule.batch.completed" and time.monotonic() - last_print >= 10:
                print(json.dumps({"stage": kind, **value}), flush=True)
                last_print = time.monotonic()
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_embeddings": 0, "model_calls": 0}), flush=True)
        result = engine.execute("apply_event_rule", {"parent_result": args.parent_result,
            "application_key": args.application_key, "user_instruction": args.user_instruction,
            "apply_unvalidated": True, "output_directory": str(args.output_directory)},
            objective="Apply the best coverage-focused saved rule to every pilot article; preserve unvalidated groups, missingness and full provenance",
            actor="codex:offline-event-rule-application")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["content_path"], "status": result["status"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
