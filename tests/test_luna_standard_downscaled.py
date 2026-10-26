"""Synthetic fixed downscale, durable pacing and untouched-only continuation."""
import json
import time
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.luna_speed_provider import SpeedProvider
from newsresearch.runtime import audited_handler
import test_luna_speed_workflow as prior
from test_luna_standard_integrity import BoundFixture
from test_luna_standard_paced import FixturePaced, window
from test_luna_standard_recovery import (
    FixtureRecovery, failed_events, prepare_parent, synthetic_environment as synthetic_environment,
)
from test_luna_standard_paced import paced, integrity

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_standard_downscaled as downscale
finally:
    sys.path.pop(0)

pytestmark = pytest.mark.usefixtures("synthetic_environment")


def test_clean_windows_never_accelerate_or_erase_rejection_history():
    state = downscale.DownscaledState(1, {"workers": 7, "admission_interval_seconds": 6.144,
        "capacity_streak": 3, "resume_not_before_epoch": 1234})
    assert state.widths == [1] and state.width == 1 and state.probe
    assert state.interval == 15 and state.not_before == 1234
    for _ in range(100):
        state.healthy(window())
    assert state.width == 1 and state.interval == 15 and state.failures == 3
    assert state.rejected(100) == 3600 and state.interval == 30
    for _ in range(100):
        state.healthy(window())
    assert state.interval == 30 and state.failures == 4
    assert state.rejected(200) == 3600 and state.interval == 60
    assert downscale.DownscaledState(1, state.snapshot()).snapshot()["capacity_streak"] == 5
    assert state.rejected(300) == 3600 and state.interval == 60
    with pytest.raises(AuditError, match="one_worker"):
        downscale.DownscaledState(7)


def test_parent_and_child_intents_preserve_spacing_after_restart(monkeypatch):
    now = 1000.
    monkeypatch.setattr(downscale.time, "time", lambda: now)
    state = downscale.DownscaledState(1, {"next_admission_epoch": 1002})
    state.restore_admission({"admitted_at_epoch": 999., "interval_seconds": 6.144,
                             "next_admission_epoch": 1005.144})
    assert state.interval == 15 and state.next_admission == 1014 and state.delay() == 14
    with pytest.raises(AuditError, match="before_deadline"):
        state.mark_admission()
    state.restore_admission({"admitted_at_epoch": 990., "interval_seconds": 60.,
                             "next_admission_epoch": 1050.})
    assert state.interval == 60 and state.next_admission == 1050
    resumed = downscale.DownscaledState(1, state.snapshot())
    now = 1050.
    intent = resumed.mark_admission()
    assert intent["next_admission_epoch"] == 1110 and resumed.width == 1


@pytest.mark.parametrize("previous", [
    {"admission_interval_seconds": 0}, {"admission_interval_seconds": float("nan")},
    {"admission_interval_seconds": 61}, {"capacity_streak": -1}, {"capacity_streak": True},
    {"resume_not_before_epoch": float("inf")}, {"next_admission_epoch": -1},
])
def test_corrupt_persisted_control_fails_closed(previous):
    with pytest.raises(AuditError):
        downscale.DownscaledState(1, previous)


@pytest.mark.parametrize("admission", [
    {"admitted_at_epoch": 10, "interval_seconds": 15, "next_admission_epoch": 24},
    {"admitted_at_epoch": 10, "interval_seconds": 61, "next_admission_epoch": 71},
    {"admitted_at_epoch": float("nan"), "interval_seconds": 15, "next_admission_epoch": 25},
    {"admitted_at_epoch": 10, "interval_seconds": 15},
])
def test_invalid_prior_intent_pacing_fails_closed(admission):
    with pytest.raises(AuditError):
        downscale.DownscaledState(1).restore_admission(admission)


class ParentPaced(FixturePaced):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "fixture_backoff":
            state = paced.PacingState(7)
            for _ in range(4):
                state.rejected(time.time())
            state.interval = .06  # Scaled synthetic clock only.
            identifier = self.ledger.record(session, "luna_standard_recovery_state", "fixture", {
                "plan": data["plan"], "synthetic": True, **state.snapshot()})
            return {"id": identifier, **state.snapshot()}
        return super()._status(session, context, data)


class FixtureDownscaled(downscale.DownscaledResearch, BoundFixture):
    packets = BoundFixture.packets


@pytest.mark.parametrize("recognized", [True, False])
def test_child_preserves_queue_holds_deadlines_and_never_retries(tmp_path, monkeypatch, recognized):
    original, capacity_plan, stopped, old_seen = prepare_parent(tmp_path / "source", monkeypatch)
    recovery = FixtureRecovery(tmp_path / "source", config=Config(offline=True))
    try:
        recovery_plan = prior.call(recovery, "status", {"phase": "amend", "plan": capacity_plan,
            "authorization_text": "Synthetic recovery parent"})["id"]
    finally:
        recovery.close()
    monkeypatch.setitem(paced.POLICY, "minimum_interval_seconds", .001)
    monkeypatch.setitem(downscale.POLICY, "initial_interval_seconds", .03)
    monkeypatch.setitem(downscale.POLICY, "minimum_interval_seconds", .03)
    parent = ParentPaced(tmp_path / "source", config=Config(offline=True))
    try:
        pacing_plan = prior.call(parent, "status", {"phase": "amend", "plan": recovery_plan,
            "authorization_text": "Synthetic paced parent"})["id"]
        parent_state = prior.call(parent, "status", {"phase": "fixture_backoff", "plan": pacing_plan})
    finally:
        parent.close()
    _, output = paced.contract.fictional_example()
    calls, waits = [], []
    def runner(*args, **kwargs):
        calls.append(time.time())
        failed = len(calls) == 1
        events = (failed_events() if recognized else failed_events("Unrecognized synthetic failure")) if failed else [
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
        assert control.width == 1 and control.widths == [1]
        if control.not_before:
            waits.append(control.snapshot())
            if len(waits) == 1:
                assert control.not_before == parent_state["resume_not_before_epoch"]
                assert control.failures == 4 and control.interval == .06 and not calls
            elif len(waits) == 2:
                assert control.failures == 5 and control.interval == .12 and len(calls) == 1
                assert progress("capacity_backoff")["unknown_holds"] == stopped["unknown_holds"] + 1
                (self.ledger.root / "STOP").write_text("Synthetic stop during wait")
                return False
            control.not_before = 0  # Simulated expiry in fictional fixture only.
        return True
    monkeypatch.setattr(FixtureDownscaled, "wait_for_capacity", wait)
    source = FixtureDownscaled(tmp_path / "source", config=Config(offline=False))
    verifier = integrity.IntegrityResearch(tmp_path / "check", config=Config(offline=True))
    payload = {"phase": "continue", "plan": pacing_plan, "authorization_text": "Downscale synthetic queues"}
    try:
        result = prior.call(source, "status", payload)
        assert len(calls) == 1 and result["unknown_holds"] == stopped["unknown_holds"] + 1
        assert result["stop_reason"] == ("user_stop" if recognized else "transport_or_unknown_stop")
        if not recognized:
            assert len(waits) == 1
            return
        source.close()
        (tmp_path / "source" / "STOP").unlink()
        source = FixtureDownscaled(tmp_path / "source", config=Config(offline=False))
        result = prior.call(source, "status", payload)
        assert result["reserved"] == 12 and result["unattempted"] == 0
        assert len(calls) + len(old_seen) == 12
        assert min(b - a for a, b in zip(calls[1:], calls[2:])) >= .119
        assert waits[1]["resume_not_before_epoch"] == waits[2]["resume_not_before_epoch"]
        child_id = json.loads((source.ledger.root / "downscale-plan.json").read_text())["id"]
        child = source.ledger.get(child_id, "luna_standard_plan")
        assert child["capacity_lineage"] == [original, capacity_plan, recovery_plan, pacing_plan]
        assert child["queues"] == source.ledger.get(pacing_plan, "luna_standard_plan")["queues"]
        assert child["max_attempts"] == 12 and child["selected_ceiling"] == 7
        assert child["operational_ceiling"] == 1 and child["config"]["allowed_workers"] == [1]
        assert source.ledger.db.execute("SELECT count(*) FROM records WHERE kind='luna_capacity_stage_intent'").fetchone()[0] == 0
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
