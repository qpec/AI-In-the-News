"""Compare corrected event-vector candidates using an exact previous pilot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from newsresearch.common import default_workspace
from newsresearch.runtime import Research
from newsresearch.storage import check_permissions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--previous-result", required=True)
    parser.add_argument("--actor", default="codex:corrected-event-clustering")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = Research(args.workspace)
    try:
        output = args.output.absolute()
        if not output.resolve().is_relative_to(engine.ledger.root):
            parser.error("Evaluation output must remain inside the protected workspace")
        output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        check_permissions(output.parent)
        original = engine.ledger.append

        def progress(session: str, kind: str, payload: dict, *rest: Any) -> int:
            sequence = original(session, kind, payload, *rest)
            if kind in {"event_clustering.intended", "event_clustering.inputs.reused", "event_clustering.mode.completed"}:
                print(json.dumps({"stage": kind, "mode": payload.get("mode")}), flush=True)
            return sequence

        engine.ledger.append = progress  # type: ignore[method-assign, assignment]
        print(json.dumps({"stage": "full_audit_preflight", "new_model_calls": 0}), flush=True)
        result = engine.execute("evaluate_event_clustering", {"previous_result": args.previous_result},
            objective="Compare corrected retained-vector and compact candidate groups on the exact preserved AWS pilot",
            actor=args.actor)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output.with_suffix(".md").write_text(result["presentation"]["markdown"], encoding="utf-8")
        print(json.dumps({"stage": "completed", "result": result["id"], "status": result["status"],
            "selected": result["selected_articles"], "processed": result["processed_articles"],
            "missing": result["missing_articles"], "summaries": result["summaries"],
            "partition_agreement": result["partition_agreement"], "output": str(output)}, ensure_ascii=True), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
