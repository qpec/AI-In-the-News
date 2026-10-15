"""Compare retained passage features and optionally use the original remaining holdout budget."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def configure_output() -> None:
    """Keep saved and printed research presentations faithful on Windows pipes."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


def main() -> int:
    configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--parent-result", required=True)
    parser.add_argument("--experiment-key", required=True)
    parser.add_argument("--continuation-instruction", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-if-qualified", action="store_true")
    parser.add_argument("--conjunction", action="store_true", help="Explicit amendment after a failed single-feature result; parent is that result")
    parser.add_argument("--monotone", action="store_true", help="Final offline five-signal existence amendment; parent is the failed two-feature result")
    args = parser.parse_args()
    if args.monotone and (args.conjunction or args.validate_if_qualified):
        parser.error("Monotone mode is a separate offline screen; do not combine it with conjunction or validation flags")
    project = Path(__file__).resolve().parents[1]
    config = replace(Config.load(project / "research.toml"), offline=not args.validate_if_qualified)
    engine = Research(args.workspace, config=config)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            parser.error("Output must remain inside protected research storage")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind in {"event_pair.features.batch_saved", "model.attempt.intended", "model.attempt.completed", "model.attempt.unobserved"}:
                print(json.dumps({"stage": kind, "phase": value.get("phase"), "offset": value.get("offset"),
                                  "status": value.get("status")}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_embedding_requests": 0}), flush=True)
        operation = "event_pair_conjunction_experiment" if args.conjunction else "event_pair_feature_experiment"
        parent_field = "parent_feature_result" if args.conjunction else "parent_result"
        if args.monotone:
            operation, parent_field = "event_pair_monotone_screen", "parent_conjunction_result"
        result = engine.execute(operation, {
            parent_field: args.parent_result, "experiment_key": args.experiment_key,
            "continuation_instruction": args.continuation_instruction, "reuse_cache": True,
            "execute_validation": args.validate_if_qualified, "workers": 4},
            objective="Compare registered passage features for same-event links; validate at most one frozen candidate within the original budget",
            actor="codex:event-pair-feature-experiment")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "output": str(output)}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
