"""Retrieve saved article candidates locally; no embeddings or LLM calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from newsresearch.event_rag_retrieval import PLAN, STUDY, EventRagResearch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", default=PLAN)
    parser.add_argument("--study-key", default=STUDY)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--actor", default="codex:saved-vector-retrieval")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    started = time.perf_counter()
    engine = EventRagResearch(args.workspace)
    try:
        result = engine.execute("vector_search", {"plan": args.plan, "study_key": args.study_key, "top_k": args.top_k},
            objective="Retrieve nearest development articles and their saved text with existing vectors for the event pilot, without new embeddings or inference", actor=args.actor)
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["id"],
            "saved_text_path": result["text"]["path"], "elapsed_seconds_including_audit": time.perf_counter() - started}), flush=True)
        return 0 if result["status"] == "complete" else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
