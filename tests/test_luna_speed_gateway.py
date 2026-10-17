"""Fictional in-memory transport scheduling checks; no model/research execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from newsresearch.codex_provider import PreparedCodexInvocation
from newsresearch.common import AuditError, ResearchError
from newsresearch.gateway import MockProvider, ProviderResponse
from newsresearch.luna_speed_gateway import SpeedGateway


class MemoryArtifacts:
    def __init__(self) -> None:
        self.values = {}

    def read(self, reference):
        return self.values[reference]


class Harness:
    def __init__(self, count=10, *, preparation=None, retention=None, provider=None):
        self.artifacts = MemoryArtifacts()
        self.engine = SimpleNamespace(_active={"session"}, ledger=SimpleNamespace(
            unresolved={}, artifacts=self.artifacts))
        self.gateway = SpeedGateway(self.engine, MockProvider())
        self.count = count
        self.prepared = []
        self.recorded = []
        self.preparation = preparation
        self.retention = retention
        self.provider = provider or SimpleNamespace(complete_prepared=lambda call: ProviderResponse(
            {"valid": True}, "synthetic-test", None))
        self.main_thread = threading.get_ident()

    def next(self, remaining, elapsed):
        assert threading.get_ident() == self.main_thread
        if len(self.prepared) >= self.count:
            return None
        index = len(self.prepared)
        attempt = f"fictional-attempt-{index}"
        call = PreparedCodexInvocation(("fictional",), Path("fictional"), "{}", {}, {"index": index}, "gpt-6-luna")
        self.prepared.append((remaining, elapsed, call, attempt))
        self.artifacts.values[f"request-{index}"] = call.request
        self.artifacts.values[f"dispatch-{index}"] = call.manifest()
        self.engine.ledger.unresolved[attempt] = {"request": f"request-{index}", "dispatch": f"dispatch-{index}"}
        if self.preparation:
            self.preparation(self, index)
        return call, attempt

    def record(self, attempt, response, dispatch, returned):
        assert threading.get_ident() == self.main_thread
        self.recorded.append((attempt, response, dispatch, returned))
        self.engine.ledger.unresolved.pop(attempt)
        if self.retention:
            return self.retention(self, response)
        return bool(response.payload and response.payload.get("valid"))

    def run(self, **options):
        return self.gateway.run_window("session", self.provider, next_call=self.next,
                                       record_response=self.record, **options)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.lock = threading.Lock()

    def __call__(self):
        with self.lock:
            return self.now

    def advance(self, seconds):
        with self.lock:
            self.now += seconds


def test_sequential_canaries_then_rolling_four_with_coordinator_only_writes():
    lock = threading.Lock()
    release = threading.Event()
    active = 0
    peak = 0
    worker_threads = set()
    completed = []

    def complete(call):
        nonlocal active, peak
        index = call.request["index"]
        with lock:
            worker_threads.add(threading.get_ident())
            if index < 2:
                assert len(completed) == index
                assert active == 0
            else:
                assert {0, 1} <= set(completed)
            active += 1
            peak = max(peak, active)
            if active == 4:
                release.set()
        if index >= 2:
            assert release.wait(timeout=3)
        with lock:
            active -= 1
            completed.append(index)
        return ProviderResponse({"valid": True}, "synthetic-test", None)

    harness = Harness(6, provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run()
    assert peak == 4
    assert harness.main_thread not in worker_threads
    assert result["canaries_valid"] == 2
    assert result["valid_persisted_within_window"] == 6
    assert result["attempted"] == 6
    assert result["stop_reason"] == "queue_exhausted"
    assert not harness.engine.ledger.unresolved


def test_invalid_first_canary_stops_without_retry_or_second_article():
    harness = Harness(provider=SimpleNamespace(complete_prepared=lambda _: ProviderResponse(
        {"valid": False}, "synthetic-test", None)))
    result = harness.run()
    assert result["stop_reason"] == "first_invalid_response"
    assert result["attempted"] == 1
    assert result["canaries_valid"] == 0
    assert result["retries"] == 0


def clean_response(valid):
    return ProviderResponse({"valid": valid}, "synthetic-test", None, raw_response={
        "transport_status": "returned", "failure": None, "unknown_outcome": False})


def test_default_still_stops_for_clean_transport_with_invalid_content():
    harness = Harness(provider=SimpleNamespace(complete_prepared=lambda _: clean_response(False)))
    result = harness.run()
    assert result["attempted"] == 1
    assert result["canaries_returned"] == 1
    assert result["canaries_valid"] == 0
    assert result["continued_validation_failures"] == 0
    assert result["continue_validation_failures"] is False
    assert result["stop_reason"] == "first_invalid_response"


def test_opt_in_transport_canaries_open_four_workers_without_accepting_invalid_outputs():
    barrier = threading.Barrier(4)
    lock = threading.Lock()
    completed = []

    def complete(call):
        index = call.request["index"]
        with lock:
            if index < 2:
                assert len(completed) == index
            else:
                assert {0, 1} <= set(completed)
        if index >= 2:
            barrier.wait(timeout=3)
        with lock:
            completed.append(index)
        return clean_response(index in {1, 4, 5})

    harness = Harness(6, provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run(continue_validation_failures=True)
    assert result["canaries_returned"] == 2
    assert result["canaries_valid"] == 1
    assert result["peak_in_flight"] == 4
    assert result["attempted"] == 6
    assert result["valid_total"] == result["valid_persisted_within_window"] == 3
    assert result["invalid_or_unknown_total"] == result["continued_validation_failures"] == 3
    assert result["stop_reason"] == "queue_exhausted"
    assert result["retries"] == 0
    assert not harness.engine.ledger.unresolved


@pytest.mark.parametrize("raw,payload", [
    ({"transport_status": "returned", "failure": None, "unknown_outcome": True}, {"valid": False}),
    ({"transport_status": "returned", "failure": None}, {"valid": False}),
    ({"transport_status": "returned", "failure": "observed_tool_use", "unknown_outcome": False}, {"valid": False}),
    ({"transport_status": "returned", "failure": "luna_speed_observed_model_mismatch", "unknown_outcome": False}, {"valid": False}),
    ({"transport_status": "invalid_or_unknown", "failure": None, "unknown_outcome": False}, {"valid": False}),
    ({"transport_status": "returned", "failure": None, "unknown_outcome": False}, None),
])
def test_opt_in_does_not_continue_unknown_failed_or_empty_transport(raw, payload):
    harness = Harness(provider=SimpleNamespace(complete_prepared=lambda _: ProviderResponse(
        payload, "synthetic-test", None, raw_response=raw)))
    result = harness.run(continue_validation_failures=True)
    assert result["attempted"] == 1
    assert result["canaries_returned"] == 0
    assert result["continued_validation_failures"] == 0
    assert result["stop_reason"] == "first_invalid_response"


def test_opt_in_still_stops_on_audit_retention_failure():
    def fail(_harness, _response):
        raise AuditError("synthetic retention failure")

    harness = Harness(retention=fail, provider=SimpleNamespace(complete_prepared=lambda _: clean_response(False)))
    with pytest.raises(AuditError):
        harness.run(continue_validation_failures=True)
    assert len(harness.prepared) == 1


def test_failure_drains_already_in_flight_without_refill():
    barrier = threading.Barrier(4)
    failure_retained = threading.Event()

    def complete(call):
        index = call.request["index"]
        if index >= 2:
            barrier.wait(timeout=3)
        if index > 2:
            assert failure_retained.wait(timeout=3)
        return ProviderResponse({"valid": index != 2}, "synthetic-test", None)

    def retain(_harness, response):
        if not response.payload["valid"]:
            failure_retained.set()
        return response.payload["valid"]

    harness = Harness(provider=SimpleNamespace(complete_prepared=complete), retention=retain)
    result = harness.run()
    assert result["stop_reason"] == "first_invalid_response"
    # The failed call is retained first; the three issued calls are then drained.
    assert result["attempted"] == 6
    assert result["responses_recorded"] == 6
    assert result["invalid_or_unknown_total"] == 1
    assert not harness.engine.ledger.unresolved


def test_deadline_includes_preparation_and_resolves_unsent_intent():
    clock = FakeClock()
    harness = Harness(preparation=lambda _h, _i: clock.advance(11))
    result = harness.run(seconds=10, clock=clock)
    assert result["attempted"] == result["submitted"] == 0
    assert result["reserved_not_dispatched"] == 1
    assert result["stop_reason"] == "deadline"
    assert harness.recorded[0][2] is None
    assert harness.recorded[0][1].raw_response["unknown_outcome"] is False
    assert not harness.engine.ledger.unresolved


def test_return_and_persistence_cutoffs_are_distinct():
    clock = FakeClock()

    def complete(_call):
        clock.advance(9)
        return ProviderResponse({"valid": True}, "synthetic-test", None)

    def retain(_harness, _response):
        clock.advance(2)
        return True

    harness = Harness(provider=SimpleNamespace(complete_prepared=complete), retention=retain)
    result = harness.run(seconds=10, clock=clock)
    assert result["attempted"] == 1
    assert result["provider_returns_within_window"] == 1
    assert result["valid_total"] == 1
    assert result["valid_persisted_within_window"] == 0
    assert result["drain_overrun_seconds"] == 1
    assert result["timings"][0]["persistence_offset"] == 11


def test_executor_start_after_deadline_never_invokes_provider():
    clock = FakeClock()
    main_thread = threading.get_ident()
    calls = []

    def delayed_worker_clock():
        if threading.get_ident() != main_thread:
            with clock.lock:
                clock.now = 111.0
        return clock()

    harness = Harness(provider=SimpleNamespace(complete_prepared=calls.append))
    result = harness.run(seconds=10, clock=delayed_worker_clock)
    assert result["submitted"] == 1
    assert result["attempted"] == 0
    assert result["reserved_not_dispatched"] == 1
    assert result["stop_reason"] == "deadline"
    assert not calls
    assert not harness.engine.ledger.unresolved


def test_deadline_stop_is_preserved_when_draining_a_late_unknown_response():
    clock = FakeClock()
    worker_started = threading.Event()
    deadline_recorded = threading.Event()

    def prepare(_harness, index):
        if index == 1:
            assert worker_started.wait(timeout=3)
            clock.advance(10)

    def complete(_call):
        worker_started.set()
        assert deadline_recorded.wait(timeout=3)
        clock.advance(1)
        return ProviderResponse(None, "synthetic-test", None, raw_response={
            "transport_status": "invalid_or_unknown", "failure": "synthetic_timeout",
            "unknown_outcome": True})

    def retain(_harness, response):
        if response.raw_response.get("dispatched") is False:
            deadline_recorded.set()
        return False

    harness = Harness(preparation=prepare, retention=retain,
                      provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run(seconds=10, canaries=0, workers=2, clock=clock,
                         continue_validation_failures=True)
    assert result["stop_reason"] == "deadline"
    assert result["attempted"] == 1
    assert result["invalid_or_unknown_total"] == 1
    assert result["reserved_not_dispatched"] == 1
    assert result["elapsed_seconds"] == 11
    assert result["responses_recorded"] == 1


def test_invocation_timeout_must_fit_remaining_window():
    def change(harness, _index):
        remaining, _elapsed, call, _attempt = harness.prepared[-1]
        object.__setattr__(call, "timeout_seconds", remaining + 1)

    calls = []
    harness = Harness(preparation=change, provider=SimpleNamespace(complete_prepared=calls.append))
    with pytest.raises(AuditError, match="timeout_exceeds"):
        harness.run()
    assert not calls


def test_late_provider_return_is_retained_but_excluded_from_speed_count():
    clock = FakeClock()

    def complete(_call):
        clock.advance(12)
        return ProviderResponse({"valid": True}, "synthetic-test", None)

    harness = Harness(provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run(seconds=10, clock=clock)
    assert result["attempted"] == 1
    assert result["valid_total"] == 1
    assert result["valid_persisted_within_window"] == 0
    assert result["provider_returns_within_window"] == 0
    assert result["elapsed_seconds"] == 12


def test_provider_exception_is_unknown_and_stops_without_secret_message_retention():
    def fail(_call):
        raise RuntimeError("sensitive error message must not be retained")

    harness = Harness(provider=SimpleNamespace(complete_prepared=fail))
    result = harness.run()
    assert result["attempted"] == 1
    assert result["invalid_or_unknown_total"] == 1
    raw = harness.recorded[0][1].raw_response
    assert raw["error_type"] == "RuntimeError"
    assert raw["unknown_outcome"] is True
    assert "sensitive" not in str(raw)


def test_cap_counts_every_submission_and_has_no_refill():
    result = Harness(20).run(cap=5)
    assert result["submitted"] == result["attempted"] == 5
    assert result["stop_reason"] == "attempt_cap"
    assert result["attempt_cap_reached"] is True


@pytest.mark.parametrize("mutation", ["missing", "request", "dispatch"])
def test_no_provider_call_without_exact_durable_intent(mutation):
    calls = []

    def change(harness, index):
        if mutation == "missing":
            harness.engine.ledger.unresolved.clear()
        else:
            harness.artifacts.values[f"{mutation}-{index}"] = {"wrong": True}

    harness = Harness(preparation=change, provider=SimpleNamespace(complete_prepared=calls.append))
    with pytest.raises(AuditError):
        harness.run()
    assert not calls


def test_active_session_required_before_preparation():
    harness = Harness()
    harness.engine._active.clear()
    with pytest.raises(AuditError):
        harness.run()
    assert not harness.prepared


def test_audit_callback_failure_does_not_issue_additional_calls():
    def fail(_harness, _response):
        raise AuditError("synthetic retention failure")

    harness = Harness(retention=fail)
    with pytest.raises(AuditError):
        harness.run()
    assert len(harness.prepared) == 1


def test_duplicate_attempt_is_never_dispatched_again():
    harness = Harness()
    original_next = harness.next

    def repeated(remaining, elapsed):
        call, _attempt = original_next(remaining, elapsed)
        return replace(call, request={"index": 0}), "fictional-attempt-0"

    harness.next = repeated
    with pytest.raises(AuditError, match="duplicate"):
        harness.run()
    assert len(harness.recorded) == 1


@pytest.mark.parametrize("options", [
    {"seconds": 601}, {"seconds": 0}, {"seconds": float("nan")}, {"seconds": True},
    {"workers": 5}, {"workers": 0}, {"workers": True}, {"cap": 2001}, {"cap": 0},
    {"canaries": -1}, {"canaries": 3, "cap": 2},
    {"continue_validation_failures": 1},
])
def test_invalid_limits_never_prepare(options):
    harness = Harness()
    with pytest.raises(ResearchError):
        harness.run(**options)
    assert not harness.prepared
