"""Prepare or execute a bounded Luna lead-screen study through Research.execute."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

from newsresearch.common import Config, default_workspace
from newsresearch.luna_lead_answers import TASK_INSTRUCTION
from newsresearch.runtime import Research

GROUP_RESULT = "1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "execute", "run"])
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--actor", default="codex:luna-group-validation")
    parser.add_argument("--codex-executable")
    parser.add_argument("--seed", default="luna-seven-day-group-validation-20261016-v1")
    parser.add_argument("--plan")
    parser.add_argument("--approval-file", type=Path)
    parser.add_argument("--allow-codex-execution", action="store_true")
    parser.add_argument("--approved-by")
    parser.add_argument("--approval-instruction")
    parser.add_argument("--approval-expires-at")
    args = parser.parse_args()
    if args.phase in {"prepare", "run"}:
        if not args.codex_executable:
            parser.error("Preparation requires an explicit absolute Codex executable")
        payload: dict[str, Any] = {"phase": args.phase, "group_result": GROUP_RESULT,
            "study_key": args.study_key, "codex_executable": args.codex_executable,
            "instruction": TASK_INSTRUCTION, "seed": args.seed}
        if args.phase == "run":
            if (not args.allow_codex_execution or not args.approved_by
                    or not args.approval_instruction or not args.approval_expires_at):
                parser.error("Composed run requires --allow-codex-execution, --approved-by, --approval-instruction and --approval-expires-at")
            payload.update(allow_codex_execution=True, approved_by=args.approved_by,
                approval_instruction=args.approval_instruction, approval_expires_at=args.approval_expires_at)
    else:
        if not args.plan or not args.approval_file or not args.allow_codex_execution:
            parser.error("Execution requires the exact plan, a fresh concrete approval file and --allow-codex-execution")
        payload = {"phase": "execute", "plan": args.plan, "study_key": args.study_key,
            "run_approval": json.loads(args.approval_file.read_text(encoding="utf-8-sig")),
            "reuse_cache": True, "workers": 4}
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    config = Config.load(project / "research.toml")
    if args.phase in {"execute", "run"}:
        config = replace(config, offline=False)
    engine = Research(args.workspace, config=config)
    original = engine.ledger.append

    def progress(session: str, kind: str, value: dict[str, Any], projection: Any = None) -> int:
        event = original(session, kind, value, projection)
        if kind in {"model.attempt.completed", "model.attempt.unobserved"}:
            print(json.dumps({"stage": kind, "status": value.get("status")}), flush=True)
        return event

    setattr(engine.ledger, "append", progress)
    if args.phase == "run":
        original_presentation = engine._record_presentation

        def present_preparation(session: str, context: Any, data: dict[str, Any]) -> dict[str, Any]:
            saved = original_presentation(session, context, data)
            if any(result.get("kind") == "luna_group_validation_plan" for result in data.get("results", [])):
                print(saved["markdown"], flush=True)
                print(json.dumps({"stage": "preparation_saved_before_model_dispatch",
                    "result": data["results"][0]["id"], "presentation": saved["content_path"]}), flush=True)
            return saved

        setattr(engine, "_record_presentation", present_preparation)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "phase": args.phase}), flush=True)
        value = engine.execute("luna_group_validation", payload,
            objective="Evaluate frozen vector-based event groups using bounded Luna article leads, strict group precision and candidate-pool recall",
            actor=args.actor)
        print(value["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": value["id"], "status": value["status"],
            "presentation": value["presentation"]["content_path"]}), flush=True)
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
