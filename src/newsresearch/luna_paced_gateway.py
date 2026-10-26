"""Versioned paced extension of the audited Luna gateway, with one ledger writer."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import math
import time

from .codex_provider import PreparedCodexInvocation
from .common import AuditError, ResearchError, require_active, utc
from .gateway import ProviderResponse
from .luna_fast_gateway import FastGateway, clean_return


class PacedGateway(FastGateway):
    """A fixed-width production window; the registered caller controls ramps."""

    def run_window(self, session, provider, *, next_call, record_response,
                   seconds=600, drain_seconds=180, widths=(1,), canaries=0,
                   cap=2000, admission, progress_tick=lambda: None):
        require_active(self.engine, session)
        if (len(widths) != 1 or type(widths[0]) is not int or not 1 <= widths[0] <= 7
                or canaries != 0 or type(cap) is not int or not 1 <= cap <= 2000
                or any(isinstance(v, bool) or not isinstance(v, (int, float))
                       or not math.isfinite(v) or v <= 0 for v in (seconds, drain_seconds))
                or seconds > 600 or drain_seconds > 180):
            raise ResearchError("paced_invalid_window_or_limits")
        started = time.monotonic()
        def elapsed():
            return time.monotonic() - started
        pending, seen, rows = {}, set(), []
        submitted = peak = 0
        stop = None
        interval = admission.interval
        pool = ThreadPoolExecutor(max_workers=widths[0], thread_name_prefix="luna-paced")

        def invoke(call):
            at = elapsed()
            if at >= seconds or admission.stopped():
                return ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": False, "dispatched": False,
                    "failure": "stop_or_deadline_before_dispatch", "observed_at": utc()}), None, at
            try:
                response = provider.complete_prepared(call)
            except Exception as error:
                response = ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": True, "dispatched": True,
                    "failure": "provider_exception_with_unobserved_outcome",
                    "error_type": type(error).__name__, "observed_at": utc()})
            return response, at, elapsed()

        def retain(attempt, response, dispatched, returned):
            nonlocal stop
            valid = record_response(attempt, response, dispatched, returned)
            if type(valid) is not bool:
                raise AuditError("paced_response_callback_must_return_bool")
            persisted = elapsed()
            rows.append({"attempt_id": attempt, "stage": 0, "dispatched": dispatched is not None,
                         "dispatch_offset_seconds": dispatched, "return_offset_seconds": returned,
                         "persisted_offset_seconds": persisted,
                         "mechanically_valid": valid and dispatched is not None,
                         "valid_persisted_within_window": valid and dispatched is not None and persisted <= seconds,
                         "clean_transport_return": clean_return(response)})
            if dispatched is None:
                stop = stop or "admission_deadline"
            elif not clean_return(response):
                stop = stop or "transport_or_unknown_stop"

        try:
            while True:
                # Retain completed failures before considering any fresh admission.
                for future in [f for f in pending if f.done()]:
                    attempt = pending.pop(future)
                    response, dispatched, returned = future.result()
                    retain(attempt, response, dispatched, returned)
                progress_tick()
                if stop is None and admission.stopped():
                    stop = "user_stop"
                if stop is None and elapsed() >= seconds:
                    stop = "admission_deadline"
                if stop is None and submitted >= cap:
                    stop = "attempt_cap"
                delay = admission.delay()
                if stop is None and len(pending) < widths[0] and delay <= 0:
                    require_active(self.engine, session)
                    if any(f.done() for f in pending):
                        continue
                    now = elapsed()
                    prepared = next_call(min(180., seconds + drain_seconds - now), now)
                    if prepared is None:
                        stop = "user_stop" if admission.stopped() else "queue_exhausted"
                    else:
                        call, attempt = prepared
                        if (not isinstance(call, PreparedCodexInvocation) or not isinstance(attempt, str)
                                or not attempt or attempt in seen):
                            raise AuditError("paced_invalid_or_duplicate_invocation")
                        seen.add(attempt)
                        timeout = getattr(call, "timeout_seconds", None)
                        if timeout is not None and (type(timeout) not in (int, float) or not math.isfinite(timeout)
                                or not 0 < timeout <= min(180., seconds + drain_seconds - now)):
                            raise AuditError("paced_invocation_timeout_exceeds_settling_bound")
                        intended = self.engine.ledger.unresolved.get(attempt)
                        if (not intended or self.engine.ledger.artifacts.read(intended["dispatch"]) != call.manifest()
                                or self.engine.ledger.artifacts.read(intended["request"]) != call.request):
                            raise AuditError("paced_invocation_differs_from_durable_intent")
                        if elapsed() >= seconds or admission.stopped():
                            retain(attempt, ProviderResponse(None, "codex-cli", None, raw_response={
                                "unknown_outcome": False, "dispatched": False,
                                "failure": "stop_or_deadline_before_dispatch"}), None, elapsed())
                        else:
                            pending[pool.submit(invoke, call)] = attempt
                            submitted += 1
                            peak = max(peak, len(pending))
                            continue
                if not pending and stop is not None:
                    break
                # Waiting never blocks draining, STOP, or the window deadline.
                timeout = .25 if stop else max(.001, min(.25, seconds - elapsed(),
                    delay if delay > 0 and len(pending) < widths[0] else .25))
                if pending:
                    wait(tuple(pending), timeout=timeout, return_when=FIRST_COMPLETED)
                else:
                    time.sleep(timeout)
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        total = elapsed()
        return {"window_seconds": seconds, "settling_budget_seconds": drain_seconds,
                "elapsed_seconds": total, "drain_overrun_seconds": max(0., total - seconds),
                "stop_reason": stop, "peak_in_flight": peak, "submitted": submitted,
                "observations": rows, "minimum_admission_interval_seconds": interval,
                "retries": 0, "provider_cancellation_proven": False}
