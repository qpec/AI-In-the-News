"""Audit-only diagnosis of the completed expanded-context singleton run."""
from pathlib import Path
import argparse
import json
import sys

from newsresearch.common import Config
from newsresearch.singleton_context_report import ContextReportResearch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    engine = ContextReportResearch(args.workspace, config=Config.load(Path(__file__).resolve().parents[1] / "research.toml"))
    try:
        result = engine.execute("status", {}, objective="Diagnose the invalid retained comparison and flag literal positive-label/reason warnings without new model inference",
                                actor="codex:singleton-output-diagnostic")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"]}), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
