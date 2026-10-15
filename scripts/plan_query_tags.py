#!/usr/bin/env python3
"""Register a query study and prepare all-article requests offline, without loading a credential."""
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
    parser.add_argument("--candidate-run", help="Optional saved vector candidates for context only")
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    study = json.loads(args.study.read_text(encoding="utf-8-sig"))
    engine = Research(args.workspace)
    try:
        print(json.dumps({"stage": "audit_preflight", "operation": "tag_setup"}), flush=True)
        result = engine.execute("tag_setup", {"study": study, "candidate_run": args.candidate_run},
            versions={"dataset": context.get("versions", context)["dataset"]}, actor=args.actor,
            objective="Register a query, retrieve every article and plan exhaustive relevance tagging offline")
        result["context_path"] = str(engine.ledger.artifacts.root / result["context_artifact"])
        print(json.dumps(result, indent=2), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
