"""Standard-speed Luna adapter with bound notes and terminal recovery.

No retries, endpoint changes or old-state repair. Raw streams remain intact.
Only the observed CLI WebSocket-403 recovery messages may precede a successful
terminal turn; arbitrary errors, tools, incomplete streams and mismatches fail.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re

from .codex_provider import PreparedCodexInvocation, _parse_events
from .common import Json, ResearchError
from .gateway import ProviderResponse
from .luna_speed_provider import PreparedSpeedInvocation, SpeedProvider
from .luna_speed_provider import BOUNDARY, _OBSERVED_MODEL, build_prompt as original_prompt

NOTES_PATH = Path(__file__).resolve().parents[2] / "prompts/luna_event_v2_execution_notes.txt"
PARSER = "luna-standard-terminal-recovery-v1"
_DETAIL = (r"unexpected status 403 Forbidden: Unknown error, url: "
           r"wss://chatgpt\.com/backend-api/codex/responses, cf-ray: [0-9a-f]+-[A-Z]+")
_RECONNECT = re.compile(r"Reconnecting\.\.\. [1-5]/5 \(" + _DETAIL + r"\)\Z")
_FALLBACK = re.compile(r"Falling back from WebSockets to HTTPS transport\. " + _DETAIL + r"\Z")


def execution_notes() -> str:
    return NOTES_PATH.read_text(encoding="utf-8")


def build_prompt(request: Json) -> str:
    original_prompt(request)  # Validate the unchanged packet/contract first.
    return json.dumps({"boundary": BOUNDARY, "execution_notes": execution_notes(),
                       "schema": request["schema"], "article": request["packet"]["model_input"]},
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def recover_terminal(response: ProviderResponse) -> ProviderResponse:
    """Reparse retained bytes; ignore only identified nonterminal CLI warnings."""
    raw = dict(response.raw_response or {})
    raw.update(terminal_parser=PARSER, recovered_transport=False,
               remote_attempt_uniqueness_proven=False, coordinator_retries=0)
    prior_failure = raw.get("failure")
    if prior_failure not in {None, "codex_turn_failed_unknown_outcome", "codex_tool_or_unrecognized_activity"}:
        return replace(response, raw_response=raw)
    if raw.get("exit_code") != 0 or not isinstance(raw.get("stdout"), str):
        return replace(response, raw_response=raw)
    try:
        events = [json.loads(line) for line in raw["stdout"].splitlines() if line.strip()]
    except ValueError:
        return replace(response, raw_response=raw)
    if not events or any(not isinstance(e, dict) for e in events):
        return replace(response, raw_response=raw)
    types = [e.get("type") for e in events]
    if (types[0] != "thread.started" or types[-1] != "turn.completed"
            or any(types.count(kind) != 1 for kind in ("thread.started", "turn.started", "turn.completed"))
            or "turn.failed" in types or types.index("turn.started") != 1):
        raw.update(failure="luna_terminal_lifecycle_invalid", unknown_outcome=True,
                   transport_status="invalid_or_unknown")
        return replace(response, payload=None, raw_response=raw)
    models = {e["model"] for e in events if isinstance(e.get("model"), str)}
    tiers = {e["service_tier"] for e in events if isinstance(e.get("service_tier"), str)}
    if any(not _OBSERVED_MODEL.fullmatch(model) for model in models) or tiers - {"default", "standard"}:
        raw.update(failure="luna_terminal_identity_mismatch", transport_status="invalid_or_unknown")
        return replace(response, payload=None, raw_response=raw)
    filtered, warnings = [], []
    final_seen = False
    for event in events:
        item = event.get("item")
        reconnect = (event.get("type") == "error" and isinstance(event.get("message"), str)
                     and _RECONNECT.fullmatch(event["message"]))
        fallback = (event.get("type") == "item.completed" and isinstance(item, dict)
                    and item.get("type") == "error" and isinstance(item.get("message"), str)
                    and _FALLBACK.fullmatch(item["message"]))
        if (reconnect or fallback) and not final_seen:
            warnings.append(event)
        else:
            filtered.append(event)
        if (event.get("type") == "item.completed" and isinstance(item, dict)
                and item.get("type") == "agent_message"):
            final_seen = True
    _, payload, failure, model, usage = _parse_events("\n".join(json.dumps(e) for e in filtered))
    if failure is not None or not isinstance(payload, dict):
        raw["terminal_replay_failure"] = failure or "luna_terminal_nonobject_output"
        return replace(response, raw_response=raw)
    if prior_failure is not None and not warnings:
        return replace(response, raw_response=raw)
    raw.update(original_parser_failure=prior_failure, recovered_transport=bool(warnings),
               transport_warnings=warnings, transport_warning_count=len(warnings),
               failure=None, unknown_outcome=False, transport_status="returned")
    return replace(response, payload=payload, model=model, usage=usage, raw_response=raw)


@dataclass(frozen=True)
class StandardInvocation(PreparedSpeedInvocation):
    def manifest(self) -> Json:
        return {**super().manifest(), "transport": "codex-cli-luna-standard-v1",
                "configured_service_tier": "standard", "fast_mode": False,
                "terminal_parser": PARSER, "execution_notes": execution_notes(),
                "execution_notes_sha256": hashlib.sha256(NOTES_PATH.read_bytes()).hexdigest()}


class StandardProvider(SpeedProvider):
    def _command(self, cwd: Path) -> tuple[str, ...]:
        # Base uses --ignore-user-config. Omit service_tier to use standard;
        # disable Fast explicitly for this invocation, without global changes.
        command = super()._command(cwd)
        return (*command[:-1], "-c", "features.fast_mode=false", command[-1])

    def prepare(self, task_key: str, attempt: str, packet: Json, *,  # type: ignore[override]
                timeout_seconds: float | None = None) -> StandardInvocation:
        prepared = super().prepare(task_key, attempt, packet, timeout_seconds=timeout_seconds)
        guided = build_prompt(prepared.request)
        if len(guided.encode("utf-8")) > prepared.max_input_bytes:
            raise ResearchError("codex_input_too_large_no_dispatch")
        return StandardInvocation(**{**vars(prepared), "stdin": guided})

    def _validate_prepared(self, prepared: PreparedCodexInvocation) -> None:
        if not isinstance(prepared, StandardInvocation) or prepared.stdin != build_prompt(prepared.request):
            raise ResearchError("luna_standard_guided_invocation_changed")
        if len(prepared.stdin.encode("utf-8")) > prepared.max_input_bytes:
            raise ResearchError("codex_input_too_large_no_dispatch")
        super()._validate_prepared(replace(prepared, stdin=original_prompt(prepared.request)))

    def complete_prepared(self, prepared: PreparedCodexInvocation) -> ProviderResponse:
        response = recover_terminal(super().complete_prepared(prepared))
        raw = dict(response.raw_response)
        observed = {e["service_tier"] for e in raw.get("events", [])
                    if isinstance(e.get("service_tier"), str)}
        raw.update(configured_service_tier="standard", fast_mode=False,
                   observed_service_tiers=sorted(observed), service_tier_verified=bool(observed))
        if observed - {"default", "standard"}:
            raw.update(failure="luna_standard_observed_tier_mismatch", transport_status="invalid_or_unknown")
            return replace(response, payload=None, raw_response=raw)
        return replace(response, raw_response=raw)
