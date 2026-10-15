"""Execute an authorized corpus question and retain its complete private answer report."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Any

from newsresearch.common import ResearchError, default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def scoped_embedding(engine: Research, credential: str) -> None:
    """Keep the launcher-injected API credential out of Codex worker environments."""
    original = engine.gateway.embed

    def embed(*args: Any, **kwargs: Any) -> Any:
        if "OPENAI_API_KEY" in os.environ:
            raise ResearchError("Unexpected API-key environment before scoped embedding")
        os.environ["OPENAI_API_KEY"] = credential
        try:
            return original(*args, **kwargs)
        finally:
            os.environ.pop("OPENAI_API_KEY", None)

    engine.gateway.embed = embed  # type: ignore[method-assign]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--actor", default="codex:rag-question")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    credential = os.environ.pop("OPENAI_API_KEY", "")
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    versions = json.loads(args.versions.read_text(encoding="utf-8-sig"))
    if payload.get("execute") is True and (not args.allow_paid_execution or not credential):
        raise ResearchError("The concrete RAG run needs explicit execution and a launcher-supplied credential")
    engine = Research(args.workspace)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            raise ResearchError("RAG outputs must remain in protected storage")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        if payload.get("execute") is True:
            engine.config = replace(engine.config, offline=False)
            scoped_embedding(engine, credential)
        print(json.dumps({"stage": "audit_preflight", "operation": "rag_query"}), flush=True)
        result = engine.execute("rag_query", payload, versions=versions.get("versions", versions),
            actor=args.actor, objective="Answer the user's organizational-decision question from the top 100 corpus matches with exact source evidence")
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report = output.with_suffix(".md")
        report.write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(json.dumps({"stage": "completed", "output": str(output), "report": str(report),
                          "status": result.get("status"), "counts": result.get("counts")}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
