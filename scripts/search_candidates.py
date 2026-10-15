#!/usr/bin/env python3
"""Build, search or check the local candidate index through the audited offline runtime."""

import argparse
import getpass
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import default_workspace
from newsresearch.runtime import Research


def report_progress(engine: Research) -> None:
    append = engine.ledger.append

    def observed(session: str, kind: str, payload: dict[str, Any], projection: Any = None) -> int:
        event = append(session, kind, payload, projection)
        if kind == "retrieval.index.progress":
            current, expected = payload["indexed_vectors"], payload["expected_vectors"]
            if current <= 4096 or current % 32768 == 0 or current == expected:
                print(json.dumps({"event": kind, **payload}), flush=True)
        elif kind == "retrieval.search.progress":
            current, expected = payload["completed_sources"], payload["expected_sources"]
            if current == 1 or current % 500 == 0 or current == expected:
                print(json.dumps({"event": kind, **payload}), flush=True)
        return event

    engine.ledger.append = observed  # type: ignore[method-assign]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["build", "search", "evaluate"])
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--actor", default=getpass.getuser())
    parser.add_argument("--plan")
    parser.add_argument("--embedding-run")
    parser.add_argument("--index")
    parser.add_argument("--source", action="append")
    parser.add_argument(
        "--limit", type=int, help="Explicitly limit sorted source IDs; omissions remain recorded"
    )
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    if args.operation == "build":
        if not args.plan or not args.embedding_run:
            parser.error("build requires --plan and --embedding-run")
        operation = "build_vector_index"
        payload = {"plan": args.plan, "embedding_run": args.embedding_run}
    else:
        if not args.index:
            parser.error("search/evaluate requires --index and its saved --context")
        operation = "vector_search" if args.operation == "search" else "evaluate_vector_index"
        payload = {"index": args.index}
        if args.operation == "search":
            payload["source_ids"] = args.source or "all"
            if args.limit is not None:
                payload["limit"] = args.limit
    engine = Research(args.workspace)
    report_progress(engine)
    try:
        print(json.dumps({"stage": "audit_preflight", "operation": operation}), flush=True)
        result = engine.execute(
            operation,
            payload,
            versions=context.get("versions", context),
            objective="Offline passage candidate retrieval and numerical index verification",
            actor=args.actor,
        )
        if "context_artifact" in result:
            result["context_path"] = str(engine.ledger.artifacts.root / result["context_artifact"])
        print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
