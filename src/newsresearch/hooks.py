"""Supplementary Codex lifecycle observations; never a substitute for the gateway."""

from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import sys
from typing import Any

from .common import ResearchError, default_workspace
from .runtime import Research

FIELDS = ("hook_event_name", "session_id", "turn_id", "tool_name", "tool_use_id", "model")
EVENTS = {"SessionStart", "PreToolUse", "PostToolUse", "Stop"}


def observe(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    event = payload.get("hook_event_name")
    engine = None
    try:
        if event not in EVENTS:
            raise ResearchError("Unsupported hook event")
        # Do not retain commands, tool results, prompts, transcript paths or environment variables.
        metadata = {key: value for key in FIELDS if isinstance(value := payload.get(key), str)}
        engine = Research(workspace)
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
    finally:
        if engine:
            engine.close()


def main() -> int:
    event: dict[str, Any] = {}
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            raise ValueError("Expected an event object")
        workspace = Path(
            os.environ.get("NEWSRESEARCH_HOOK_WORKSPACE", default_workspace().parent / "codex-hooks")
        )
        print(json.dumps(observe(event, workspace)))
        return 0
    except Exception:
        # A malformed event cannot reliably be denied using an event-specific contract.
        print("Hook input unavailable; runtime audit remains mandatory.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
