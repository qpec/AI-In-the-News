"""Synthetic pacing, recovery lineage and audited continuation regressions."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.luna_paced_gateway import PacedGateway
from newsresearch.luna_speed_provider import SpeedProvider
from newsresearch.runtime import audited_handler
from test_luna_fast_iteration import clean
from test_luna_speed_gateway import Harness
import test_luna_speed_workflow as prior
from test_luna_standard_integrity import BoundFixture
from test_luna_standard_recovery import (
    FixtureRecovery, failed_events, prepare_parent, synthetic_environment as synthetic_environment,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_standard_paced as paced
    import check_luna_standard_integrity as integrity
finally:
    sys.path.pop(0)

pytestmark = pytest.mark.usefixtures("synthetic_environment")


def window(seconds=600, count=25):
    return {"elapsed_seconds": seconds, "observations": [
        {"clean_transport_return": True, "dispatched": True}] * count}


def test_rate_guard_preserves_parent_deadline_streak_and_per_intent_spacing():
    state = paced.PacingState(7, {"capacity_streak": 4, "resume_not_before_epoch": 1234})
    assert state.interval == 15 and state.not_before == 1234 and state.failures == 4
    state.healthy(window(1, 1))
    assert not state.probe and state.failures == 4 and state.interval == 15
    state.healthy(window(599, 100))
    assert state.width == 1 and state.interval == 15
    state.healthy(window(600, 15))
    assert state.width == 1
    state.healthy(window(600, 10))
    assert state.width == 2 and state.interval == 12 and state.failures == 0
    state.mark_admission()
    resumed = paced.PacingState(7, state.snapshot())
    assert resumed.probe and resumed.width == 1 and resumed.delay() > 11
    with pytest.raises(AuditError, match="before_deadline"):
        resumed.mark_admission()
    for interval, delay in ((24, 300), (48, 900), (60, 1800), (60, 3600)):
        assert resumed.rejected(100) == delay
        assert resumed.interval == interval and resumed.not_before == 100 + delay
    resumed.healthy(window(1, 1))
    resumed.healthy({"elapsed_seconds": 600, "observations": [
        {"clean_transport_return": False, "dispatched": True}] * 25})
    assert resumed.interval == 60 and resumed.failures == 4


def paced_harness(count=5, interval=.06, provider=None):
    harness = Harness(count=count, provider=provider or SimpleNamespace(complete_prepared=lambda _: clean()))
    harness.gateway = PacedGateway(harness.engine, harness.gateway.provider)
    control = paced.PacingState(7)
    control.interval = interval  # Test clock scale; production constructor remains bounded.
    original_next = harness.next
    admissions = []
    def next_call(*args):
        result = original_next(*args)
        if result is not None:
            admissions.append(control.mark_admission()["admitted_at_epoch"])
        return result
    harness.next = next_call
    return harness, control, admissions


def test_aggregate_spacing_across_parallel_workers_and_separate_windows():
    harness, control, admissions = paced_harness()
    first = harness.run(widths=(4,), canaries=0, cap=1, admission=control)
    assert first["submitted"] == 1
    second = harness.run(widths=(4,), canaries=0, cap=4, admission=control)
    assert second["submitted"] == 4 and len(admissions) == 5
    assert min(b - a for a, b in zip(admissions, admissions[1:])) >= .059


@pytest.mark.parametrize("reason", ["stop", "deadline"])
def test_waiting_for_spacing_spends_no_identity_and_is_interruptible(reason, tmp_path):
    harness, control, admissions = paced_harness(interval=15)
    control.next_admission = time.time() + 15
    control.stop_file = tmp_path / "STOP"
    def tick():
        if reason == "stop":
            control.stop_file.write_text("Fictional stop")
    result = harness.run(widths=(1,), canaries=0, seconds=.04, admission=control, progress_tick=tick)
    assert result["submitted"] == 0 and admissions == []
    assert result["stop_reason"] == ("user_stop" if reason == "stop" else "admission_deadline")
    assert result["elapsed_seconds"] < 1


def test_failed_response_is_retained_before_next_paced_admission():
    response = clean()
    response.raw_response["unknown_outcome"] = True
    harness, control, admissions = paced_harness(provider=SimpleNamespace(complete_prepared=lambda _: response))
    result = harness.run(widths=(7,), canaries=0, admission=control)
    assert result["submitted"] == len(admissions) == 1
    assert result["stop_reason"] == "transport_or_unknown_stop"
    assert len(result["observations"]) == 1


def test_binding_mismatch_prevents_dispatch():
    harness, control, _ = paced_harness(provider=SimpleNamespace(
        complete_prepared=lambda _: pytest.fail("No call after a binding mismatch")))
    original_next = harness.next
    def changed(*args):
        call, attempt = original_next(*args)
        return replace(call, stdin=call.stdin + " "), attempt
    harness.next = changed
    with pytest.raises(AuditError, match="differs_from_durable_intent"):
        harness.run(widths=(1,), canaries=0, admission=control)


def test_parallel_failure_drains_other_started_call_and_stops_admission():
    second_started = threading.Event()
    def complete(call):
        response = clean()
        if call.request["index"] == 0:
            assert second_started.wait(3)
            response.raw_response["unknown_outcome"] = True
        else:
            second_started.set()
            time.sleep(.12)
        return response
    harness, control, admissions = paced_harness(provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run(widths=(2,), canaries=0, admission=control)
    assert result["submitted"] == len(admissions) == 2
    assert len(result["observations"]) == 2 and result["peak_in_flight"] == 2
    assert result["stop_reason"] == "transport_or_unknown_stop"


def test_failed_audit_write_prevents_further_calls():
    harness, control, admissions = paced_harness()
    def fail(*args):
        raise AuditError("synthetic_disk_failure")
    harness.retention = fail
    with pytest.raises(AuditError, match="synthetic_disk_failure"):
        harness.run(widths=(7,), canaries=0, admission=control)
    assert len(admissions) == 1


def test_deadline_retains_late_response_without_admitting_next_article():
    def complete(call):
        time.sleep(.12)
        return clean()
    harness, control, admissions = paced_harness(provider=SimpleNamespace(complete_prepared=complete))
    result = harness.run(widths=(7,), canaries=0, seconds=.03, admission=control)
    assert result["submitted"] == len(admissions) == 1
    assert result["observations"][0]["mechanically_valid"]
    assert not result["observations"][0]["valid_persisted_within_window"]


class ParentWithBackoff(FixtureRecovery):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "fixture_backoff":
            state = paced.parent_recovery.RecoveryState(7)
            for _ in range(4):
                state.rejected(time.time())
            identifier = self.ledger.record(session, "luna_standard_recovery_state", "fixture", {
                "plan": data["plan"], "synthetic": True, **state.snapshot()})
            return {"id": identifier, **state.snapshot()}
        return super()._status(session, context, data)


class FixturePaced(paced.PacedRecoveryResearch, BoundFixture):
    packets = BoundFixture.packets


@pytest.mark.parametrize("recognized", [True, False])
def test_versioned_child_preserves_parent_deadline_holds_and_never_retries(tmp_path, monkeypatch, recognized):
    original, capacity_plan, stopped, old_seen = prepare_parent(tmp_path / "source", monkeypatch)
    parent = ParentWithBackoff(tmp_path / "source", config=Config(offline=True))
    try:
        parent_plan = prior.call(parent, "status", {"phase": "amend", "plan": capacity_plan,
            "authorization_text": "Synthetic recovery parent"})["id"]
        parent_state = prior.call(parent, "status", {"phase": "fixture_backoff", "plan": parent_plan})
    finally:
        parent.close()
    monkeypatch.setitem(paced.POLICY, "initial_interval_seconds", .06)
    monkeypatch.setitem(paced.POLICY, "minimum_interval_seconds", .001)
    _, output = paced.contract.fictional_example()
    calls, waits = [], []
    def runner(*args, **kwargs):
        calls.append(time.time())
        failed = len(calls) == 1
        events = (failed_events() if recognized else failed_events("Fictional unrelated transport failure")) if failed else [
            {"type": "thread.started"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
            {"type": "turn.completed"}]
        return SimpleNamespace(stdout="\n".join(json.dumps(e) for e in events), stderr="", returncode=int(failed))
    original_init = SpeedProvider.__init__
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.runner = runner
    monkeypatch.setattr(SpeedProvider, "__init__", init)
    def wait(self, control, progress):
        if control.not_before:
            waits.append(control.snapshot())
            if len(waits) == 1:
                assert control.not_before == parent_state["resume_not_before_epoch"]
                assert control.failures == 4 and not calls
            elif len(waits) == 2:
                assert control.failures == 5 and len(calls) == 1
                assert progress("capacity_backoff")["unknown_holds"] == stopped["unknown_holds"] + 1
                (self.ledger.root / "STOP").write_text("Synthetic stop during capacity wait")
                return False
            control.not_before = 0  # Simulated expiry only in this fictional fixture.
        return True
    monkeypatch.setattr(FixturePaced, "wait_for_capacity", wait)
    source = FixturePaced(tmp_path / "source", config=Config(offline=False))
    verifier = integrity.IntegrityResearch(tmp_path / "check", config=Config(offline=True))
    payload = {"phase": "continue", "plan": parent_plan, "authorization_text": "Fix synthetic pacing and continue"}
    try:
        result = prior.call(source, "status", payload)
        assert len(calls) == 1 and result["unknown_holds"] == stopped["unknown_holds"] + 1
        assert result["stop_reason"] == ("user_stop" if recognized else "transport_or_unknown_stop")
        if not recognized:
            assert len(waits) == 1
            return
        source.close()
        (tmp_path / "source" / "STOP").unlink()
        source = FixturePaced(tmp_path / "source", config=Config(offline=False))
        result = prior.call(source, "status", payload)
        assert result["reserved"] == 12 and result["unattempted"] == 0
        assert len(calls) + len(old_seen) == 12
        assert waits[1]["resume_not_before_epoch"] == waits[2]["resume_not_before_epoch"]
        assert waits[2]["admission_interval_seconds"] == .12
        child_id = json.loads((source.ledger.root / "pacing-plan.json").read_text())["id"]
        child = source.ledger.get(child_id, "luna_standard_plan")
        assert child["capacity_lineage"] == [original, capacity_plan, parent_plan]
        assert child["queues"] == source.ledger.get(parent_plan, "luna_standard_plan")["queues"]
        report = prior.call(verifier, "status", {"source_owner": str(source.ledger.root), "plan": child_id})
        assert report["integrity_passed"] and report["reserved"] == 12
        again = prior.call(verifier, "status", {"source_owner": str(source.ledger.root), "plan": child_id})
        assert again["new_results_verified"] == 0
        prior.call(source, "status", payload)
        assert len(calls) + len(old_seen) == 12
        with pytest.raises(AuditError, match="authorization_changed"):
            prior.call(source, "status", {**payload, "authorization_text": "Changed permission"})
        source.ledger.verify()
    finally:
        source.close()
        verifier.close()
