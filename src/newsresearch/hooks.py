"""Supplementary Codex lifecycle observations; never a substitute for the gateway."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any

import time

from .common import AuditError, ResearchError, default_workspace
from .runtime import Research
from .storage import prepare_root

FIELDS = ("hook_event_name", "session_id", "turn_id", "tool_name", "tool_use_id", "model")
EVENTS = {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}


def hook_workspace(payload: dict[str, Any], override: str | Path | None = None) -> Path:
    """Select independent session journals without interpreting session IDs as paths."""
    if override is not None:
        return Path(override)
    parent = default_workspace().parent
    session = payload.get("session_id")
    if isinstance(session, str) and session.strip():
        try:
            identifier = hashlib.sha256(session.encode("utf-8")).hexdigest()
        except UnicodeError:
            pass
        else:
            return parent / "codex-hook-sessions" / identifier
    return parent / "codex-hooks"


def _storage_failure(event: Any) -> dict[str, Any]:
    reason = "Supplementary audit storage failed. Stop research and repair the audited runtime."
    if event == "PreToolUse":
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    return {"continue": False, "stopReason": reason, "systemMessage": reason}


def _open_runtime(workspace: Path) -> Research:
    """Wait briefly for another supplementary hook without masking audit failures."""
    deadline = time.monotonic() + 15.0
    while True:
        try:
            return Research(workspace)
        except AuditError as exc:
            if str(exc) != "Workspace is already open; concurrent research processes are blocked":
                raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.25, remaining))


def observe(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    event = payload.get("hook_event_name")
    engine = None
    try:
        if event not in EVENTS:
            raise ResearchError("Unsupported hook event")
        # Do not retain commands, tool results, prompts, transcript paths or environment variables.
        metadata = {key: value for key in FIELDS if isinstance(value := payload.get(key), str)}
        engine = _open_runtime(workspace)
        engine.execute(
            "hook",
            metadata,
            objective=f"Observe Codex lifecycle event {event}",
            actor=f"local-user:{getpass.getuser()}",
        )
        if event == "SessionStart":
            return {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "Research requires newsresearch CLI / Research.execute, registered methods and protected storage. "
                    "These hooks record lifecycle metadata only. All model research must use the audited gateway. "
                    "Read AGENTS.md, docs/RESEARCH_PROTOCOL.md and docs/AUDITABILITY.md.",
                }
            }
        return {}
    except Exception:
        # Do not echo exception messages or raw incoming payloads; they may contain secrets.
        return _storage_failure(event)
    finally:
        if engine:
            engine.close()


def main() -> int:
    event: dict[str, Any] = {}
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("Expected an event object")
        override = os.environ.get("NEWSRESEARCH_HOOK_WORKSPACE")
        workspace = hook_workspace(event, override)
        namespace = default_workspace().parent / "codex-hook-sessions"
        if override is None and workspace.parent == namespace:
            try:
                # Protect the namespace too: prepare_root(child) otherwise creates
                # missing ancestors with their inherited platform permissions.
                prepare_root(namespace)
            except Exception:
                print(json.dumps(_storage_failure(event.get("hook_event_name"))))
                return 0
        print(json.dumps(observe(event, workspace)))
        return 0
    except Exception:
        # A malformed event cannot reliably be denied using an event-specific contract.
        print("Hook input unavailable; runtime audit remains mandatory.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
