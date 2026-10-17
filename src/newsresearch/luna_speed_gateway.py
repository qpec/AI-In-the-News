"""Bounded Codex throughput scheduling with a single audited coordinator.

Only ``complete_prepared`` runs in worker threads. The owning research handler
freezes its queue and authorization, creates durable invocation intents, and
retains/validates responses through the callbacks on the caller's thread.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import math
import time
from typing import Any, Callable

from .codex_provider import PreparedCodexInvocation
from .common import AuditError, Json, ResearchError, require_active, utc
from .gateway import Gateway, ProviderResponse

NextCall = Callable[[float, float], tuple[PreparedCodexInvocation, str] | None]
RecordResponse = Callable[[str, ProviderResponse, float | None, float], bool]


class SpeedGateway(Gateway):
    """Two sequential canaries followed by rolling, at-most-four workers."""

    def run_window(
        self,
        session: str,
        provider: Any,
        *,
        next_call: NextCall,
        record_response: RecordResponse,
        seconds: float = 600,
        workers: int = 4,
        canaries: int = 2,
        cap: int = 2000,
        clock: Callable[[], float] = time.perf_counter,
    ) -> Json:
        """Run one window, including preparation, CLI startup and retention.

        ``next_call`` receives remaining seconds and elapsed seconds and must
        bind a per-invocation timeout no larger than that remaining budget. It
        persists the exact request/dispatch and intended attempt before return.
        The gateway rechecks the deadline after this callback and verifies the
        durable intent immediately before submission. It never retries.

        If preparation crosses the deadline, ``record_response`` receives a
        local not-dispatched response and a null dispatch offset. That callback
        must resolve the reserved intent without claiming provider execution.
        For submitted calls, offsets are measured inside the provider worker.
        A return before the deadline and validation persisted before the
        deadline are separate counts. Draining can extend beyond the window;
        a local timeout does not establish provider-side cancellation.

        Callback/audit exceptions abort scheduling immediately. Already-issued
        work keeps its durable unknown intent; worker threads never write to
        the research store after the coordinator has failed.
        """
        require_active(self.engine, session)
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or not 0 < seconds <= 600):
            raise ResearchError("luna_speed_invalid_window")
        if type(workers) is not int or not 1 <= workers <= 4:
            raise ResearchError("luna_speed_invalid_workers")
        if type(cap) is not int or not 1 <= cap <= 2000:
            raise ResearchError("luna_speed_invalid_cap")
        if type(canaries) is not int or not 0 <= canaries <= cap:
            raise ResearchError("luna_speed_invalid_canaries")

        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="luna-speed")
        pending: dict[Future[tuple[ProviderResponse, float | None, float]], str] = {}
        seen: set[str] = set()
        observations: list[Json] = []
        submitted = 0
        canary_valid = 0
        not_dispatched = 0
        peak_in_flight = 0
        stop_reason: str | None = None
        # The first measured action is preparation of the first invocation.
        started = clock()

        def elapsed() -> float:
            return max(0.0, clock() - started)

        def provider_call(call: PreparedCodexInvocation) -> tuple[ProviderResponse, float | None, float]:
            dispatch_offset = elapsed()
            if dispatch_offset >= seconds:
                return ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": False,
                    "dispatched": False,
                    "failure": "deadline_before_dispatch",
                    "observed_at": utc(),
                }), None, dispatch_offset
            try:
                response = provider.complete_prepared(call)
            except Exception as error:
                response = ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": True,
                    "dispatched": True,
                    "error_type": type(error).__name__,
                    "failure": "provider_exception_with_unobserved_outcome",
                    "observed_at": utc(),
                })
            return response, dispatch_offset, elapsed()

        def retain(attempt: str, response: ProviderResponse, dispatched: float | None,
                   returned: float) -> bool:
            valid = record_response(attempt, response, dispatched, returned)
            if type(valid) is not bool:
                raise AuditError("luna_speed_response_callback_must_return_bool")
            persisted = elapsed()
            observations.append({
                "attempt_id": attempt,
                "dispatched": dispatched is not None,
                "dispatch_offset_seconds": dispatched,
                "return_offset_seconds": returned,
                "persisted_offset_seconds": persisted,
                "provider_returned_within_window": dispatched is not None and returned <= seconds,
                "mechanically_valid": valid and dispatched is not None,
                "valid_persisted_within_window": valid and dispatched is not None and persisted <= seconds,
            })
            return valid

        def submit_one() -> bool:
            nonlocal submitted, not_dispatched, peak_in_flight, stop_reason
            require_active(self.engine, session)
            now = elapsed()
            if now >= seconds:
                stop_reason = "deadline"
                return False
            if submitted >= cap:
                stop_reason = "attempt_cap"
                return False
            prepared = next_call(seconds - now, now)
            if prepared is None:
                stop_reason = "queue_exhausted"
                return False
            invocation, attempt = prepared
            if not isinstance(invocation, PreparedCodexInvocation) or not isinstance(attempt, str) or not attempt:
                raise AuditError("luna_speed_invalid_prepared_call")
            if attempt in seen:
                raise AuditError("luna_speed_duplicate_attempt_forbidden")
            seen.add(attempt)
            invocation_timeout = getattr(invocation, "timeout_seconds", None)
            if invocation_timeout is not None and (
                    isinstance(invocation_timeout, bool) or not isinstance(invocation_timeout, (int, float))
                    or not math.isfinite(invocation_timeout) or not 0 < invocation_timeout <= seconds - now):
                raise AuditError("luna_speed_invocation_timeout_exceeds_remaining_window")
            intended = self.engine.ledger.unresolved.get(attempt)
            if not intended or self.engine.ledger.artifacts.read(intended["dispatch"]) != invocation.manifest():
                raise AuditError("Codex dispatch must match a durable exact invocation intent")
            if self.engine.ledger.artifacts.read(intended["request"]) != invocation.request:
                raise AuditError("Codex evidence differs from durable request")
            now = elapsed()
            if now >= seconds:
                not_dispatched += 1
                stop_reason = "deadline"
                retain(attempt, ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": False,
                    "dispatched": False,
                    "failure": "deadline_before_dispatch",
                    "observed_at": utc(),
                }), None, now)
                return False
            pending[pool.submit(provider_call, invocation)] = attempt
            submitted += 1
            peak_in_flight = max(peak_in_flight, len(pending))
            return True

        try:
            while True:
                # Consume all known completions before preparing another call,
                # so an observed failed canary/response cannot be bypassed.
                completed = [future for future in pending if future.done()]
                for future in completed:
                    attempt = pending.pop(future)
                    response, dispatched, returned = future.result()
                    valid = retain(attempt, response, dispatched, returned)
                    if dispatched is None:
                        not_dispatched += 1
                        if stop_reason != "first_invalid_response":
                            stop_reason = "deadline"
                    elif not valid:
                        stop_reason = "first_invalid_response"
                    elif canary_valid < canaries:
                        canary_valid += 1
                if stop_reason is None:
                    if any(future.done() for future in pending):
                        continue
                    capacity = 1 if canary_valid < canaries else workers
                    if len(pending) < capacity:
                        if submit_one():
                            continue
                if not pending:
                    break
                # Once stopped, only drain existing calls. All callbacks still
                # run on this coordinator thread and retain late responses.
                wait(tuple(pending), return_when=FIRST_COMPLETED)
        except BaseException:
            # There is no claim that an in-flight provider operation can be
            # cancelled. Its existing intent remains unresolved for audit.
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        total_elapsed = elapsed()
        attempted_rows = [row for row in observations if row["dispatched"]]
        return {
            "window_seconds": seconds,
            "elapsed_seconds": total_elapsed,
            "elapsed_including_drain_seconds": total_elapsed,
            "drain_overrun_seconds": max(0.0, total_elapsed - seconds),
            "stop_reason": stop_reason,
            "deadline_reached": total_elapsed >= seconds,
            "attempt_cap_reached": submitted >= cap,
            "workers": workers,
            "peak_in_flight": peak_in_flight,
            "canaries_required": canaries,
            "canaries_valid": canary_valid,
            "attempt_cap": cap,
            "submitted": submitted,
            "attempted": len(attempted_rows),
            "reserved_not_dispatched": not_dispatched,
            "responses_recorded": len(attempted_rows),
            "provider_returns_within_window": sum(row["provider_returned_within_window"] for row in attempted_rows),
            "valid_total": sum(row["mechanically_valid"] for row in attempted_rows),
            "valid_persisted_within_window": sum(row["valid_persisted_within_window"] for row in attempted_rows),
            "invalid_or_unknown_total": sum(not row["mechanically_valid"] for row in attempted_rows),
            "observations": observations,
            "timings": [{"attempt": row["attempt_id"], "persistence_offset": row["persisted_offset_seconds"],
                         "dispatch_offset": row["dispatch_offset_seconds"], "return_offset": row["return_offset_seconds"]}
                        for row in observations],
            "retries": 0,
            "provider_cancellation_proven": False,
        }
