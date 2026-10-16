"""Audited metadata-only engineering diagnosis of unknown Luna transport outcomes."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

from newsresearch.common import Config, Context, Json, ResearchError, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "luna-unknown-transport-metadata-diagnostic-v1"


def code(value: Any) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_.-]{0,119}", value) else None


def timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


class DiagnosticResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"result"} or not isinstance(data["result"], str) or not data["result"].strip():
            raise ResearchError("Bind one exact Luna result for metadata-only diagnosis")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD + "-" + data["result"][:12],
            "content": {"method": METHOD, "result": data["result"], "model_calls": 0, "network_calls": 0,
                "scope": "Unknown transport metadata only; no source-text output, article judging, retry or acceptance",
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}})["id"]
        old = self.ledger.get(data["result"], "luna_group_validation_result")
        bound = Context(context.objective, context.actor, old["versions"])
        rows = []
        for logical_id, outcome in old["outcomes"].items():
            if outcome.get("status") != "unknown":
                continue
            assessment_id = outcome.get("assessment")
            row: Json = {"logical_id": logical_id, "attempt": outcome.get("attempt"),
                "assessment": assessment_id, "response": None, "metadata_available": False}
            if isinstance(assessment_id, str):
                assessment = self.ledger.get(assessment_id, "luna_lead_assessment")
                if assessment.get("task") != logical_id or assessment.get("status") != "unknown":
                    raise ResearchError("Unknown transport assessment/result binding differs")
                response_id = assessment.get("response")
                row.update(response=response_id, assessment_status=assessment["status"],
                    assessment_error=code(assessment.get("error")))
                if isinstance(response_id, str):
                    self.ledger.append(session, "luna.transport.diagnostic.inspection.intended", {
                        "result": data["result"], "assessment": assessment_id, "response": response_id,
                        "protocol": protocol, "scope": "Safe transport fields and output lengths/types only"})
                    response = self.ledger.artifacts.read(response_id)
                    raw = response.get("raw_response")
                    if isinstance(raw, dict):
                        output = {name: raw.get(name) for name in ("stdout", "stderr")}
                        events = raw.get("events")
                        event_types = Counter(code(event.get("type")) or "unavailable_type"
                            for event in events if isinstance(event, dict)) if isinstance(events, list) else Counter()
                        row.update(metadata_available=True, failure=code(raw.get("failure")),
                            unknown_outcome=raw.get("unknown_outcome") if type(raw.get("unknown_outcome")) is bool else None,
                            exit_code=raw.get("exit_code") if type(raw.get("exit_code")) is int else None,
                            timeout_seconds=raw.get("timeout_seconds") if type(raw.get("timeout_seconds")) in (int, float) else None,
                            started_at=timestamp(raw.get("started_at")), ended_at=timestamp(raw.get("ended_at")),
                            output_lengths={name: {"characters": len(value), "utf8_bytes": len(value.encode("utf-8"))}
                                if isinstance(value, str) else None for name, value in output.items()},
                            retained_event_count=len(events) if isinstance(events, list) else None,
                            retained_event_type_counts=dict(event_types))
            rows.append(row)
        result = {"method": METHOD, "technical_protocol": protocol, "versions": bound.versions,
            "original_result": data["result"], "study_key": old["study_key"], "plan": old["plan"],
            "workflow_model_attempts": old["workflow_model_attempts"],
            "workflow_article_exposures": old["workflow_article_exposures"],
            "original_task_counts": old["task_counts"], "unknown_tasks": rows,
            "metadata_available": sum(row["metadata_available"] for row in rows),
            "model_calls": 0, "network_calls": 0, "retries": 0, "article_judgments": 0,
            "source_or_output_text_presented": False, "unknown_outcomes_resolved": False}
        identifier = self.ledger.record(session, "luna_group_validation_diagnostic", digest(result), result)
        lines = ["Luna transport metadata diagnostic: no model calls, retries or article judgments.",
            f"Study {old['study_key']}; result {data['result']}. Historical attempts {old['workflow_model_attempts']}/400; "
            f"article exposures {old['workflow_article_exposures']}/6,000; task counts {old['task_counts']}.",
            f"Unknown tasks {len(rows)}; retained metadata available for {result['metadata_available']}."]
        lines.extend(f"Attempt {row.get('attempt')}: {json.dumps(row, sort_keys=True)}" for row in rows)
        lines.append("Only recorded transport fields, lengths and event types are shown. Source text, model output and messages are omitted. "
            "This diagnostic does not resolve unknown billing/generation or authorize another attempt.")
        presentation = self._record_presentation(session, bound, {
            "results": [{"kind": "luna_group_validation_diagnostic", "id": identifier}],
            "markdown": "\n\n".join(lines), "destination": "codex_chat", "status": "prepared_for_delivery"})
        return {"id": identifier, **result, "presentation": presentation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = replace(Config.load(Path(__file__).resolve().parents[1] / "research.toml"), offline=True)
    engine = DiagnosticResearch(args.workspace, config=config)
    try:
        result = engine.execute("status", {"result": args.result},
            objective="Engineering diagnosis of an exact stored Luna result using safe transport metadata only; zero model calls and no article judging",
            actor="codex:luna-transport-diagnostic")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result["presentation"]["content_path"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
