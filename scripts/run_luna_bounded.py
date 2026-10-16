"""Export, import and continue one bounded Luna study through audited operations.

Completed exports resume only with their exact manifest/nonce. This coordinator
never retries a failed operation, repeats a model attempt or reads protected
artifacts directly.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from typing import Any

from newsresearch.common import Config, ResearchError, default_workspace
from newsresearch.runtime import Research


def observe(engine: Research) -> None:
    append, present = engine.ledger.append, engine._record_presentation
    verify = engine.ledger.verify

    def timed_verify() -> dict[str, Any]:
        started = time.perf_counter()
        result = verify()
        print(json.dumps({"stage": "complete_store_verified", "workspace": str(engine.ledger.root),
            "wall_seconds": round(time.perf_counter() - started, 3),
            "events": result["events"], "head_hash": result["head_hash"]}), flush=True)
        return result

    def progress(session: str, kind: str, value: dict[str, Any], projection: Any = None) -> int:
        event = append(session, kind, value, projection)
        if kind == "luna.continuation.task.completed":
            print(json.dumps({"stage": kind, **value}), flush=True)
        return event

    def display(session: str, context: Any, data: dict[str, Any]) -> dict[str, Any]:
        saved = present(session, context, data)
        print(saved["markdown"], flush=True)
        print(json.dumps({"stage": "saved_presentation", "result": data["results"][0],
            "presentation": saved["content_path"]}), flush=True)
        return saved

    setattr(engine.ledger, "append", progress)
    setattr(engine.ledger, "verify", timed_verify)
    setattr(engine, "_record_presentation", display)


def execute(engine: Research, operation: str, data: dict[str, Any], actor: str, objective: str) -> dict[str, Any]:
    started = time.perf_counter()
    print(json.dumps({"stage": "operation_started", "operation": operation,
        "workspace": str(engine.ledger.root), "offline": engine.config.offline}), flush=True)
    try:
        result = engine.execute(operation, data, objective=objective, actor=actor)
    except BaseException as error:
        print(json.dumps({"stage": "operation_stopped", "operation": operation,
            "wall_seconds": round(time.perf_counter() - started, 3), "error_type": type(error).__name__,
            "automatic_retry": False}), flush=True)
        raise
    print(json.dumps({"stage": "operation_completed", "operation": operation, "result": result["id"],
        "state": result.get("state"), "status": result.get("status"),
        "wall_seconds": round(time.perf_counter() - started, 3)}), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace(), help="Parent protected workspace")
    parser.add_argument("--child-workspace", type=Path, required=True)
    parser.add_argument("--result", required=True, help="Exact original Luna result")
    parser.add_argument("--study-key", required=True)
    parser.add_argument("--authorization-instruction", required=True)
    parser.add_argument("--continue-untouched", action="store_true")
    parser.add_argument("--actor", default="codex:luna-group-validation")
    parser.add_argument("--import-manifest", help="Resume an already completed export; do not reopen the parent")
    parser.add_argument("--transfer-nonce", help="Exact nonce returned by the completed export")
    parser.add_argument("--continue-only", action="store_true", help="Continue an already imported child; skip export and import")
    parser.add_argument("--resume-transfer", action="store_true", help="Explicitly resume the exact parent-sealed incomplete export")
    parser.add_argument("--quarantine-local-timeouts", action="store_true")
    parser.add_argument("--supersedes-control")
    args = parser.parse_args()
    if not args.continue_untouched or not args.authorization_instruction.strip():
        parser.error("Explicit --continue-untouched and a nonempty --authorization-instruction are required")
    if args.supersedes_control and not args.quarantine_local_timeouts:
        parser.error("--supersedes-control requires explicit --quarantine-local-timeouts")
    if bool(args.import_manifest) != bool(args.transfer_nonce):
        parser.error("Exact export resume requires both --import-manifest and --transfer-nonce")
    if args.continue_only and (args.import_manifest or args.transfer_nonce):
        parser.error("Choose --continue-only or exact export resume, not both")
    if args.resume_transfer and (args.continue_only or args.import_manifest):
        parser.error("--resume-transfer resumes parent export; it cannot be combined with child-only resume modes")
    parent_path = args.workspace.expanduser().absolute()
    child_path = args.child_workspace.expanduser().absolute()
    if child_path == parent_path or child_path in parent_path.parents or parent_path in child_path.parents:
        parser.error("Parent and child workspaces must be disjoint")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    offline = replace(Config.load(project / "research.toml"), offline=True)
    import_input = {"manifest": args.import_manifest, "study_key": args.study_key,
        "transfer_nonce": args.transfer_nonce}
    if not args.continue_only and not args.import_manifest:
        parent = Research(parent_path, config=offline)
        observe(parent)
        try:
            export_input: dict[str, Any] = {"study_key": args.study_key,
                "original_result": args.result, "child_workspace": str(child_path),
                "authorization_instruction": args.authorization_instruction}
            if args.resume_transfer:
                export_input["resume_transfer"] = True
            exported = execute(parent, "luna_study_export", export_input, args.actor,
                "Transfer the frozen Luna study to a bounded protected workspace, preserve all original audit history and spend, and seal parent execution")
            if exported.get("state") != "exported_parent_execution_sealed":
                raise ResearchError("luna_bounded_export_incomplete_no_following_stage")
            import_input = exported["import_input"]
            print(json.dumps({"stage": "exact_export_resume", "result": exported["id"],
                "child_workspace": str(child_path), "manifest": import_input["manifest"],
                "transfer_nonce": import_input["transfer_nonce"]}), flush=True)
        finally:
            parent.close()
    if not args.continue_only:
        child = Research(child_path, config=offline)
        observe(child)
        try:
            imported = execute(child, "luna_study_import", import_input, args.actor,
                "Verify the complete bounded Luna transfer and restore exact frozen sources, study versions, authorization and historical budget without model calls")
            if imported.get("state") != "imported_verified_owner":
                raise ResearchError("luna_bounded_import_incomplete_no_model_dispatch")
        finally:
            child.close()
    child = Research(child_path, config=replace(offline, offline=False))
    observe(child)
    try:
        continuation_input: dict[str, Any] = {"result": args.result,
            "study_key": args.study_key, "continue_untouched": True,
            "authorization_instruction": args.authorization_instruction, "reuse_cache": True, "workers": 4}
        if args.quarantine_local_timeouts:
            continuation_input["quarantine_local_timeouts"] = True
            if args.supersedes_control:
                continuation_input["supersedes_control"] = args.supersedes_control
        result = execute(child, "luna_group_validation_continue", continuation_input,
            args.actor, "Evaluate untouched frozen Luna group and anchor tasks in parallel within the original cumulative budget; preserve failures and never retry")
        print(json.dumps({"result": result["id"], "status": result["status"],
            "presentation": result["presentation"]["content_path"], "automatic_retry": False}), flush=True)
        return 0 if result["status"] == "complete" else 1
    finally:
        child.close()


if __name__ == "__main__":
    raise SystemExit(main())
