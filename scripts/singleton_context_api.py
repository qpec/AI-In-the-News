"""Prepare/execute only the authorized expanded-context singleton follow-up."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

from newsresearch.common import Config, ResearchError
from newsresearch.singleton_context_api import SingletonContextResearch, USER_INSTRUCTION


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--phase", choices=("prepare", "execute"), required=True)
    parser.add_argument("--plan")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    paid = args.phase == "execute"
    if paid and (not args.allow_paid_execution or not args.plan or not os.environ.get("OPENAI_API_KEY")):
        raise ResearchError("Expanded-context execution requires the frozen plan, explicit flag and stored key")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=not paid)
    engine = SingletonContextResearch(args.workspace, config=config)
    try:
        data = {"phase": "singleton_context_" + args.phase}
        if paid:
            data.update(plan=args.plan, user_instruction=USER_INSTRUCTION)
        result = engine.execute("luna_group_validation", data,
            objective="Resolve the 41 uncertain and retry 3 incomplete singleton cases using expanded retained context and the same three candidates",
            actor="codex:singleton-expanded-context-api")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
