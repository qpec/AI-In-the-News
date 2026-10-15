"""Execute an explicitly approved event-pair study using process-local settings."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--input", type=Path, required=True, help="Protected JSON payload with fresh concrete run approval")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--actor", default="codex:event-pair-cutoff-experiments")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    config = replace(Config.load(project / "research.toml"), offline=False)
    engine = Research(args.workspace, config=config)
    try:
        for path in (args.input, args.output):
            if not path.resolve().is_relative_to(engine.ledger.root):
                parser.error("Input and output must remain inside the protected research workspace")
        check_permissions(args.input)
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        output = args.output.absolute()
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        original = engine.ledger.append

        def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
            sequence = original(session, kind, value, *rest)
            if kind in {"model.attempt.intended", "model.attempt.completed", "model.attempt.unobserved", "model.cache_reused"}:
                print(json.dumps({"stage": kind, "status": value.get("status")}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "new_embedding_requests": 0}), flush=True)
        result = engine.execute("event_pair_experiment", payload,
            objective="Evaluate a provisional same-event article-pair distance cutoff with a single held-out model-reference check",
            actor=args.actor)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "output": str(output)}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
