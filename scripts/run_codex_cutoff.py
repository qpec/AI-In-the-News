"""Run an explicitly authorized Codex calibration with process-local online mode."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from newsresearch.common import default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--actor", default="codex:adaptive-cutoff")
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    supplied = json.loads(args.versions.read_text(encoding="utf-8-sig"))
    engine = Research(args.workspace)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            raise ValueError("Result output must remain in the protected research workspace")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        if payload.get("execute") is True:
            engine.config = replace(engine.config, offline=False)
        result = engine.execute("adaptive_cutoff", payload,
            versions=supplied.get("versions", supplied), actor=args.actor,
            objective="Execute the user-authorized bounded Codex calibration of the existing AI-incident query and present its actual cutoff/results")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(result["presentation"]["markdown"], flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
