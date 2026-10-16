"""Build the full offline vector snapshot from a complete audited embedding checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import default_workspace
from newsresearch.runtime import Research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--execution", required=True)
    parser.add_argument("--key", required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    engine = Research(args.workspace)
    append = engine.ledger.append

    def progress(session: str, kind: str, payload: dict[str, Any], projection: Any = None) -> int:
        event = append(session, kind, payload, projection)
        if kind == "retrieval.index.progress":
            current = payload["indexed_vectors"]
            if current <= 4096 or current % 32768 == 0 or current == payload["expected_vectors"]:
                print(json.dumps({"stage": kind, **payload}), flush=True)
        return event

    setattr(engine.ledger, "append", progress)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "operation": "index_catalog_embeddings", "model_calls": 0}), flush=True)
        value = engine.execute("index_catalog_embeddings", {"execution": args.execution, "key": args.key,
            "instruction": "Complete the authorized full-corpus vector-store expansion, including saved cybercrime sources, without new inference or changed groups"},
            objective="Index every completed authorized full-corpus embedding shard and preserve exact article/catalog/group provenance",
            actor="codex:full-corpus-vector-indexing")
        print(value["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": value["id"], "presentation": value["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
