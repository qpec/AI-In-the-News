#!/usr/bin/env python3
"""Compatibility command: source verification now enters the audited runtime."""

import argparse
import getpass
import json
from pathlib import Path
import sys

# Keep direct "python scripts/verify_sources.py" usable after uv sync.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from newsresearch.common import default_workspace
from newsresearch.runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument(
        "--actor", default=getpass.getuser(), help="Identifiable operator; Codex must name itself"
    )
    parser.add_argument("--report", help="Deprecated: reports now remain in audited protected storage")
    args = parser.parse_args()
    engine = Research(args.workspace)
    actor = args.actor
    try:
        versions = {}
        for kind, content in [
            (
                "protocol",
                {
                    "method": "Verify original source hashes, bundle counts, missing text and identifiers; "
                    "event-uri-metadata-v1 checks article.eventUri on every archive record, distinguishing "
                    "absent, null, empty/whitespace, non-string and populated values. Count exact distinct "
                    "populated strings across the archive and per bundle; no dossier or incident inference.",
                },
            ),
            ("selection", {"rules": "All files in the existing source-inventory manifest"}),
            (
                "question",
                {"text": "Is article.eventUri present and populated in the preserved archive metadata?"},
            ),
        ]:
            versions[kind] = engine.execute(
                "version",
                {"kind": kind, "key": "legacy-verification-" + kind, "content": content},
                objective="Register the legacy verification method",
                actor=actor,
            )["id"]
        result = engine.execute(
            "verify_legacy",
            {"data_root": str(args.data_root)},
            objective="Verify the existing private archive without changing its files",
            actor=actor,
            versions=versions,
        )
        print(json.dumps(result, indent=2))
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
