"""Prepare missing full-corpus embeddings offline; never dispatches inference."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import default_workspace
from newsresearch.runtime import Research


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--instruction", required=True)
    args = parser.parse_args()
    engine = Research(args.workspace)
    original = engine.ledger.append

    def progress(session: str, kind: str, value: dict, *rest: Any) -> int:
        number = original(session, kind, value, *rest)
        if kind in {"catalog_embedding.preparation.intended", "catalog_embedding.batch.completed", "catalog_embedding.batch.reused"}:
            print(json.dumps({"stage": kind, **value}), flush=True)
        return number

    setattr(engine.ledger, "append", progress)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "paid_calls": 0}), flush=True)
        result = engine.execute("plan_catalog_embeddings", {"snapshot": args.snapshot, "key": args.key,
            "instruction": args.instruction, "batch_size": 20000},
            objective="Prepare all missing full-corpus embeddings through bounded core imports and existing audited gateway plans without paid execution",
            actor="codex:full-corpus-embedding-planning")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "batches": len(result["batches"]),
            "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
