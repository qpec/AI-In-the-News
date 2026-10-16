"""Build the full offline source registry and migrate compatible saved vectors."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.runtime import Research


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--key", required=True)
    parser.add_argument("--instruction", required=True)
    parser.add_argument("--plan", default="ccc83cf9693a219e28b417ae65ebccd7cc77ffe43ab9764d06b15a1a8b139ace")
    parser.add_argument("--group-result", default="1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d")
    args = parser.parse_args()
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = Research(args.workspace, config=config)
    started = time.perf_counter()
    original = engine.ledger.append

    def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
        sequence = original(session, kind, value, *rest)
        if kind in {"event_store.build.intended", "event_store.catalog.bundle_completed"}:
            print(json.dumps({"stage": kind, "elapsed_seconds": time.perf_counter()-started, **value}), flush=True)
        return sequence

    setattr(engine.ledger, "append", progress)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "paid_calls": 0}), flush=True)
        result = engine.execute("scale_event_vector_store", {
            "data_root": str(args.data_root), "plan": args.plan, "group_result": args.group_result,
            "key": args.key, "instruction": args.instruction, "retention": "permitted",
            "batch_size": 2000, "started_monotonic": started},
            objective="Register all preserved legacy and upgraded Cybercrime NL article bundles and migrate compatible saved event-retrieval vectors",
            actor="codex:full-corpus-event-vector-store")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "catalog": result["catalog"]["artifact"],
            "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
