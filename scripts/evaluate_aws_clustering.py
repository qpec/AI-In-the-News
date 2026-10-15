"""Run the bounded offline AWS-core pilot inside the audited runtime."""
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
    anchor = parser.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--reference-result")
    anchor.add_argument("--index")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--seed", default="aws-event-pilot-20261015-v1")
    parser.add_argument("--actor", default="codex:aws-event-clustering-test")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = Research(args.workspace)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            parser.error("Evaluation output must remain inside the protected workspace")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        original = engine.ledger.append
        def progress(session: str, kind: str, payload: dict, *rest: Any) -> int:
            sequence = original(session, kind, payload, *rest)
            if kind in {"aws_evaluation.context.bound", "aws_evaluation.intended", "aws_evaluation.vectors.prepared"}:
                print(json.dumps({"stage": kind}), flush=True)
            return sequence
        engine.ledger.append = progress  # type: ignore[method-assign, assignment]
        print(json.dumps({"stage": "full_audit_preflight", "new_model_calls": 0}), flush=True)
        result = engine.execute("evaluate_aws_clustering", {"reference_result": args.reference_result,
            "index": args.index, "limit": args.limit, "seed": args.seed,
            "key": "aws-core-pilot-20261015-v1"}, objective=
            "Archive retained embedding lineage and test the AWS DBSCAN core for same-event grouping candidates",
            actor=args.actor)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(json.dumps({"stage": "completed", "result": result["id"], "status": result["status"],
            "selected": result["selected_articles"], "processed": result["processed_articles"],
            "missing": result["missing_articles"], "summaries": {name: {key: value for key, value in summary.items()
                if key not in {"coverage", "errors"}} for name, summary in result["summaries"].items()},
            "output": str(output)}, ensure_ascii=True), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
