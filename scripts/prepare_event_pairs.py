"""Prepare a frozen event-pair study from saved vectors, without model calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from newsresearch.common import default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--previous-result", required=True)
    parser.add_argument("--key", default="event-pair-cutoff-study-20261015-v1")
    parser.add_argument("--seed", default="event-pair-cutoff-study-20261015-v1")
    parser.add_argument("--actor", default="codex:event-pair-cutoff-experiments")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = Research(args.workspace)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            parser.error("Study output must remain inside the protected research workspace")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        original = engine.ledger.append

        def progress(session: str, kind: str, payload: dict, *rest: Any) -> int:
            sequence = original(session, kind, payload, *rest)
            if kind.startswith("event_pair.") or kind == "preparation.artifact.saved":
                print(json.dumps({"stage": kind, "purpose": payload.get("purpose")}), flush=True)
            return sequence

        setattr(engine.ledger, "append", progress)
        print(json.dumps({"stage": "full_audit_preflight", "model_calls": 0}), flush=True)
        result = engine.execute("plan_event_pairs", {"previous_result": args.previous_result,
            "key": args.key, "seed": args.seed},
            objective="Prepare a frozen, probability-logged comparison of same-event article-pair distance cutoffs using existing embeddings",
            actor=args.actor)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(json.dumps({"stage": "completed", "result": result["id"], "status": result["status"],
            "dataset": result["dataset_articles"], "vectors": result["processed_articles"],
            "missing": result["missing_articles"], "unique_bodies": result["unique_bodies"],
            "development_pairs": result["development_pairs"], "output": str(output)}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
