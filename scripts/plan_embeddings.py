#!/usr/bin/env python3
"""Prepare exact OpenAI embedding requests and a local token/cost estimate; never call a model."""

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
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--preparation", required=True)
    parser.add_argument("--actor", default=getpass.getuser())
    args = parser.parse_args()
    context = json.loads(args.context.read_text(encoding="utf-8-sig"))
    engine = Research(args.workspace)
    try:
        result = engine.execute(
            "plan_embeddings",
            {"preparation": args.preparation},
            objective="Register OpenAI embedding method and calculate an offline, version-bound pilot cost plan",
            actor=args.actor,
            versions=context["versions"],
        )
        result["context_path"] = str(engine.ledger.artifacts.root / result["context_artifact"])
        print(json.dumps(result, indent=2))
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
