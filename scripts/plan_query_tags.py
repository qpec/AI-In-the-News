#!/usr/bin/env python3
"""Plan one query embedding by default; optional model mode plans per-article LLM requests."""
import argparse
import getpass
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import default_workspace
from newsresearch.runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--context", type=Path, required=True, help="Existing dataset context")
    parser.add_argument("--study", type=Path, required=True, help="Protected JSON study specification")
    parser.add_argument("--mode", choices=["embeddings", "model"], default="embeddings")
    parser.add_argument("--index", help="Saved article vector index; required in default embedding mode")
    parser.add_argument("--candidate-run", help="Optional saved vector candidates for context only")
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    study = json.loads(args.study.read_text(encoding="utf-8-sig"))
    if args.mode == "embeddings":
        if not args.index or args.candidate_run:
            parser.error("Embedding mode requires --index; it scans all vectors and does not use --candidate-run")
        if set(study) - {"query", "question", "tag", "evaluation"}:
            parser.error("Embedding study fields are query, question, tag and optional evaluation; use --mode model for LLM-specific fields")
        operation, payload = "similarity_setup", {"index": args.index, **study}
    else:
        operation, payload = "tag_setup", {"study": study, "candidate_run": args.candidate_run}
    engine = Research(args.workspace)
    try:
        print(json.dumps({"stage": "audit_preflight", "operation": operation}), flush=True)
        result = engine.execute(operation, payload,
            versions={"dataset": context.get("versions", context)["dataset"]}, actor=args.actor,
            objective="Register the selected query-tagging method and prepare its exact offline plan")
        result["context_path"] = str(engine.ledger.artifacts.root / result["context_artifact"])
        print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
