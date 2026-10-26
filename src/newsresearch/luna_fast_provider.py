"""Plan-bound Fast configuration on the existing audited Luna CLI transport."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from .codex_provider import PreparedCodexInvocation
from .common import Json
from .gateway import ProviderResponse
from .luna_speed_provider import PreparedSpeedInvocation, SpeedProvider


@dataclass(frozen=True)
class FastInvocation(PreparedSpeedInvocation):
    def manifest(self) -> Json:
        return {**super().manifest(), "transport": "codex-cli-luna-fast-v1",
                "configured_service_tier": "fast"}


class FastProvider(SpeedProvider):
    def _command(self, cwd: Path) -> tuple[str, ...]:
        command = super()._command(cwd)
        return (*command[:-1], "-c", 'service_tier="fast"',
                "-c", "features.fast_mode=true", command[-1])

    def prepare(self, task_key: str, attempt: str, packet: Json, *,  # type: ignore[override]
                timeout_seconds: float | None = None) -> FastInvocation:
        prepared = super().prepare(task_key, attempt, packet, timeout_seconds=timeout_seconds)
        return FastInvocation(**vars(prepared))

    def complete_prepared(self, prepared: PreparedCodexInvocation) -> ProviderResponse:
        response = super().complete_prepared(prepared)
        raw = dict(response.raw_response)
        observed = {event.get("service_tier") for event in raw.get("events", [])
                    if isinstance(event.get("service_tier"), str)}
        raw.update(configured_service_tier="fast", observed_service_tiers=sorted(observed),
                   service_tier_verified=bool(observed))
        if observed - {"fast", "priority"}:
            raw.update(failure="luna_fast_observed_tier_mismatch", transport_status="invalid_or_unknown")
            return replace(response, payload=None, raw_response=raw)
        return replace(response, raw_response=raw)
