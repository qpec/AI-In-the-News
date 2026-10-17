"""Prepare an audited provider-metadata split candidate without model dispatch."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from newsresearch.common import Config
from newsresearch.event_provider_candidate import ProviderCandidateResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--comparison-key", required=True)
    parser.add_argument("--user-instruction", required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = ProviderCandidateResearch(args.workspace, config=config)
    try:
        result = engine.execute("refine_event_groups", {"phase": "prepare_provider_candidate", "comparison_key": args.comparison_key,
            "user_instruction": args.user_instruction}, objective="Prepare an exact provider-event metadata split inside frozen guarded seven-day groups",
            actor="codex:provider-anchor-candidate")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
