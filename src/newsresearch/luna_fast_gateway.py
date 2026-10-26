"""Bounded adaptive concurrency; only the coordinator writes research records."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import math
import time
from typing import Any, Callable

from .codex_provider import PreparedCodexInvocation
from .common import AuditError, Json, ResearchError, require_active, utc
from .gateway import Gateway, ProviderResponse


def percentile(values: list[float], fraction: float) -> float | None:
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def clean_return(response: ProviderResponse) -> bool:
    raw = response.raw_response
    return (isinstance(raw, dict) and raw.get("transport_status") == "returned"
            and raw.get("failure") is None and raw.get("unknown_outcome") is False
            and response.payload is not None)


def stage_metrics(rows: list[Json], elapsed: float) -> Json:
    valid = sum(row["mechanically_valid"] for row in rows)
    latencies = [row["return_offset_seconds"] - row["dispatch_offset_seconds"] for row in rows]
    return {"returned": len(rows), "valid": valid, "seconds": elapsed,
            "valid_per_minute": 60 * valid / elapsed if elapsed > 0 else 0,
            "valid_fraction": valid / len(rows) if rows else None,
            "p50_seconds": percentile(latencies, .5), "p95_seconds": percentile(latencies, .95)}


def improvement(candidate: Json, previous: Json) -> bool:
    return (candidate["valid_per_minute"] >= 1.15 * previous["valid_per_minute"]
            and candidate["valid_per_minute"] > 0
            and candidate["valid_fraction"] >= previous["valid_fraction"] - .05
            and candidate["p95_seconds"] < 2 * previous["p95_seconds"])


class FastGateway(Gateway):
    def run_window(self, session: str, provider: Any, *, next_call: Callable,
                   record_response: Callable, seconds: float = 600, drain_seconds: float = 180,
                   widths: tuple[int, ...] = (4, 8, 16, 32), canaries: int = 2, cap: int = 2000,
                   stage_seconds: float = 90, min_returns: int = 30,
                   clock: Callable[[], float] = time.perf_counter) -> Json:
        require_active(self.engine, session)
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0
                for v in (seconds, drain_seconds, stage_seconds)) or seconds > 600 or drain_seconds > 180
                or not widths or any(type(w) is not int or not 1 <= w <= 32 for w in widths)
                or tuple(sorted(set(widths))) != widths or type(cap) is not int or not 1 <= cap <= 2000
                or type(canaries) is not int or not 0 <= canaries <= cap
                or type(min_returns) is not int or min_returns < 1):
            raise ResearchError("fast_invalid_window_or_limits")
        pool = ThreadPoolExecutor(max_workers=max(widths), thread_name_prefix="luna-fast")
        pending: dict[Any, tuple[str, int]] = {}
        seen: set[str] = set()
        rows: list[Json] = []
        stages: list[Json] = []
        submitted = peak = canary_returned = canary_valid = 0
        stop: str | None = None
        started = clock()
        stage = -1
        candidate_index = 0
        width = 1
        best: Json | None = None
        exploring = True

        def elapsed() -> float:
            return max(0., clock() - started)

        def begin_stage(new_width: int, purpose: str) -> None:
            nonlocal stage, width
            now = elapsed()
            if stages:
                stages[-1]["end_offset"] = now
            stage = len(stages)
            width = new_width
            stages.append({"stage": stage, "workers": width, "start_offset": now,
                           "end_offset": None, "purpose": purpose,
                           "carryover_in_flight": len(pending), "decision": None})
            print(json.dumps({"stage_started": stage, "workers": width,
                                           "purpose": purpose, "elapsed_seconds": round(now, 3)}), flush=True)

        def invoke(call: PreparedCodexInvocation) -> tuple[ProviderResponse, float | None, float]:
            at = elapsed()
            if at >= seconds:
                return ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": False, "dispatched": False,
                    "failure": "deadline_before_dispatch", "observed_at": utc()}), None, at
            try:
                response = provider.complete_prepared(call)
            except Exception as error:
                response = ProviderResponse(None, "codex-cli", None, raw_response={
                    "unknown_outcome": True, "dispatched": True,
                    "failure": "provider_exception_with_unobserved_outcome",
                    "error_type": type(error).__name__, "observed_at": utc()})
            return response, at, elapsed()

        def retain(attempt: str, response: ProviderResponse, dispatched: float | None,
                   returned: float, dispatch_stage: int) -> None:
            nonlocal stop, canary_returned, canary_valid
            valid = record_response(attempt, response, dispatched, returned)
            if type(valid) is not bool:
                raise AuditError("fast_response_callback_must_return_bool")
            persisted = elapsed()
            rows.append({"attempt_id": attempt, "stage": dispatch_stage,
                         "dispatched": dispatched is not None, "dispatch_offset_seconds": dispatched,
                         "return_offset_seconds": returned, "persisted_offset_seconds": persisted,
                         "mechanically_valid": valid and dispatched is not None,
                         "valid_persisted_within_window": valid and dispatched is not None and persisted <= seconds,
                         "clean_transport_return": clean_return(response)})
            if dispatch_stage == -1 and dispatched is not None:
                canary_returned += int(clean_return(response))
                canary_valid += int(valid)
            if dispatched is None:
                stop = stop or "admission_deadline"
            elif not clean_return(response):
                stop = stop or "transport_or_unknown_stop"

        try:
            while True:
                for future in [f for f in pending if f.done()]:
                    attempt, dispatch_stage = pending.pop(future)
                    response, dispatched, returned = future.result()
                    retain(attempt, response, dispatched, returned, dispatch_stage)
                now = elapsed()
                if stop is None and now >= seconds:
                    stop = "admission_deadline"
                if stop is None and submitted >= cap:
                    stop = "attempt_cap"
                if stop is None and canary_returned >= canaries:
                    if stage == -1:
                        begin_stage(widths[0], "baseline")
                    current = stages[stage]
                    observations = [r for r in rows if r["stage"] == stage and r["dispatched"]]
                    duration = now - current["start_offset"]
                    if exploring and duration >= stage_seconds and len(observations) >= min_returns:
                        metrics = stage_metrics(observations, duration)
                        accept = best is None or improvement(metrics, best["metrics"])
                        current["decision"] = {"accepted": accept, "metrics": metrics,
                                               "comparison_stage": best["stage"] if best else None,
                                               "criterion": "gain_15pct_valid_drop_at_most_5pp_p95_less_than_2x"}
                        if accept:
                            best = {"workers": width, "stage": stage, "metrics": metrics}
                        if accept and metrics["valid"] > 0 and candidate_index + 1 < len(widths):
                            candidate_index += 1
                            begin_stage(widths[candidate_index], "candidate")
                        else:
                            exploring = False
                            if best is not None and width != best["workers"]:
                                begin_stage(best["workers"], "selected_width")
                if stop is None and len(pending) < width:
                    require_active(self.engine, session)
                    if any(f.done() for f in pending):
                        continue
                    now = elapsed()
                    prepared = next_call(min(180., seconds + drain_seconds - now), now)
                    if prepared is None:
                        stop = "queue_exhausted"
                    else:
                        call, attempt = prepared
                        if (not isinstance(call, PreparedCodexInvocation) or not isinstance(attempt, str)
                                or not attempt or attempt in seen):
                            raise AuditError("fast_invalid_or_duplicate_invocation")
                        seen.add(attempt)
                        timeout = getattr(call, "timeout_seconds", None)
                        if timeout is not None and (type(timeout) not in (int, float) or not math.isfinite(timeout)
                                or not 0 < timeout <= min(180., seconds + drain_seconds - now)):
                            raise AuditError("fast_invocation_timeout_exceeds_settling_bound")
                        intended = self.engine.ledger.unresolved.get(attempt)
                        if (not intended or self.engine.ledger.artifacts.read(intended["dispatch"]) != call.manifest()
                                or self.engine.ledger.artifacts.read(intended["request"]) != call.request):
                            raise AuditError("fast_invocation_differs_from_durable_intent")
                        if elapsed() >= seconds:
                            retain(attempt, ProviderResponse(None, "codex-cli", None, raw_response={
                                "unknown_outcome": False, "dispatched": False,
                                "failure": "deadline_before_dispatch"}), None, elapsed(), stage)
                        else:
                            pending[pool.submit(invoke, call)] = (attempt, stage)
                            submitted += 1
                            peak = max(peak, len(pending))
                            continue
                if not pending:
                    break
                # Timed wakeup makes admission stop independent of provider completion.
                wait(tuple(pending), timeout=max(.001, min(.25, seconds - elapsed()))
                     if stop is None else .25, return_when=FIRST_COMPLETED)
        except BaseException:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        total = elapsed()
        for item in stages:
            end = item["end_offset"] if item["end_offset"] is not None else min(total, seconds)
            item["end_offset"] = end
            matched = [r for r in rows if r["stage"] == item["stage"] and r["dispatched"]]
            in_stage = [r for r in matched if r["persisted_offset_seconds"] <= end]
            item["window_metrics"] = stage_metrics(in_stage, max(0., end - item["start_offset"]))
            item["returned_after_stage"] = len(matched) - len(in_stage)
        return {"window_seconds": seconds, "settling_budget_seconds": drain_seconds,
                "elapsed_seconds": total, "drain_overrun_seconds": max(0., total - seconds),
                "stop_reason": stop, "peak_in_flight": peak, "submitted": submitted,
                "canaries_returned": canary_returned, "canaries_valid": canary_valid,
                "stages": stages, "selected_workers": best["workers"] if best else None,
                "selected_workers_confirmed": False, "observations": rows,
                "timings": [{"attempt": r["attempt_id"], "stage": r["stage"],
                             "persistence_offset": r["persisted_offset_seconds"],
                             "dispatch_offset": r["dispatch_offset_seconds"],
                             "return_offset": r["return_offset_seconds"]} for r in rows],
                "retries": 0, "provider_cancellation_proven": False}
