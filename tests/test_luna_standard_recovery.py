"""Synthetic capacity backoff, immutable holds and cross-plan no-retry checks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.luna_speed_provider import SpeedProvider
from newsresearch.runtime import audited_handler
import test_luna_speed_workflow as prior
from test_luna_standard_integrity import BoundFixture
from test_luna_standard_capacity import FixtureCapacity, metric
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_standard_recovery as recovery
    import check_luna_standard_integrity as integrity
finally:
    sys.path.pop(0)

MESSAGE = "Fictional service capacity rejection for software tests"


def failed_events(message=MESSAGE):
    return [{"type": "thread.started"}, {"type": "turn.started"},
            {"type": "error", "message": message},
            {"type": "turn.failed", "error": {"message": message}}]


def rejection(events=None, **overrides):
    return SimpleNamespace(payload=None, raw_response={
        "failure": "codex_turn_failed_unknown_outcome", "exit_code": 1,
        "unknown_outcome": True, "events": failed_events() if events is None else events, **overrides})


@pytest.fixture(autouse=True)
def synthetic_environment(monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(recovery.CAPACITY_MESSAGES, hashlib.sha256(MESSAGE.encode()).hexdigest(), "service_capacity")


def test_classifier_requires_exact_failed_lifecycle_without_output_or_tools():
    assert recovery.capacity_failure(rejection()) == "service_capacity"
    assert recovery.capacity_failure(rejection(failed_events("Unrelated article mentions 429 and capacity"))) is None
    for changes in ({"unknown_outcome": False}, {"exit_code": 0}, {"failure": "other"}):
        assert recovery.capacity_failure(rejection(**changes)) is None
    for extra in ({"type": "turn.completed"}, {"type": "item.completed", "item": {"type": "web_search"}}):
        assert recovery.capacity_failure(rejection(failed_events() + [extra])) is None
    response = rejection()
    response.payload = {"unexpected": "answer"}
    assert recovery.capacity_failure(response) is None
    events = failed_events()
    events[3]["error"]["message"] = "different"
    assert recovery.capacity_failure(rejection(events)) is None


def test_backoff_survives_restart_and_ceiling_requires_sustained_clean_windows():
    control = recovery.RecoveryState(7)
    assert control.width == 1 and control.probe
    for delay in (300, 900, 1800, 3600, 3600):
        assert control.rejected(100) == delay
        resumed = recovery.RecoveryState(7, control.snapshot())
        assert resumed.not_before == 100 + delay and resumed.failures == control.failures
    control.healthy({"elapsed_seconds": 1, "observations": [{}]})
    assert control.width == 1 and not control.probe and control.failures == 5
    control.healthy({"elapsed_seconds": 599, "observations": [{}] * 25})
    assert control.width == 1
    control.healthy({"elapsed_seconds": 600, "observations": [{}] * 24})
    assert control.width == 1
    for width in (2, 4, 7, 7):
        control.healthy({"elapsed_seconds": 600, "observations": [{}] * 25})
        assert control.width == width and control.failures == 0


def test_stop_interrupts_backoff_without_sleep_or_dispatch(tmp_path, monkeypatch):
    engine = object.__new__(recovery.RecoveryResearch)
    engine.ledger = SimpleNamespace(root=tmp_path)
    control = recovery.RecoveryState(7)
    control.rejected(time.time())
    (tmp_path / "STOP").write_text("Synthetic user stop")
    monkeypatch.setattr(recovery.time, "sleep", lambda _: pytest.fail("STOP must interrupt wait"))
    assert engine.wait_for_capacity(control, lambda _: pytest.fail("No progress needed")) is False


class FixtureSelection(FixtureCapacity):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "fixture_selection":
            identifier = self.ledger.record(session, "luna_capacity_selection", "fictional-selection", {
                "plan": data["plan"], "workers": 7,
                "stages": [metric(4, 30), metric(6, 42), metric(7, 48)], "synthetic": True})
            return {"id": identifier}
        return super()._status(session, context, data)


class FixtureRecovery(recovery.RecoveryResearch, BoundFixture):
    packets = BoundFixture.packets


def prepare_parent(root, monkeypatch):
    old = BoundFixture(root, config=Config(offline=True))
    old_seen = prior.mock_runner(monkeypatch, unknown=True)
    try:
        original = prior.call(old, "status", {"phase": "prepare"})["id"]
        old.config = replace(old.config, offline=False)
        stopped = prior.call(old, "status", {"phase": "run", "plan": original,
                             "authorization_text": "Synthetic original queues"})
    finally:
        old.close()
    selected = FixtureSelection(root, config=Config(offline=True))
    try:
        parent = prior.call(selected, "status", {"phase": "amend", "plan": original,
                            "authorization_text": "Synthetic capacity amendment"})["id"]
        prior.call(selected, "status", {"phase": "fixture_selection", "plan": parent})
    finally:
        selected.close()
    return original, parent, stopped, old_seen


@pytest.mark.parametrize("interrupt_wait,recognized", [(False, True), (True, True), (False, False)])
def test_capacity_pause_then_untouched_only_across_restart_and_parent_holds(tmp_path, monkeypatch, interrupt_wait, recognized):
    original, parent, stopped, old_seen = prepare_parent(tmp_path / "source", monkeypatch)
    _, output = recovery.contract.fictional_example()
    new_seen, waits = [], []
    def runner(*args, **kwargs):
        new_seen.append(kwargs)
        events = failed_events(MESSAGE if recognized else "Fictional unrelated transport failure") if len(new_seen) == 1 else [
            {"type": "thread.started"}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
            {"type": "turn.completed"}]
        return SimpleNamespace(stdout="\n".join(json.dumps(e) for e in events), stderr="", returncode=1 if len(new_seen) == 1 else 0)
    # Replace the injected constructor's runner while retaining real preparation,
    # parsing, shared gateway, intent writes, projection and integrity replay.
    original_init = SpeedProvider.__init__
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.runner = runner
    monkeypatch.setattr(SpeedProvider, "__init__", init)
    def wait(self, control, progress):
        if control.not_before:
            snapshot = progress("capacity_backoff")
            assert snapshot["in_flight"] == 0
            assert snapshot["unknown_holds"] == stopped["unknown_holds"] + 1
            waits.append(control.not_before)
            if interrupt_wait and len(waits) == 1:
                (self.ledger.root / "STOP").write_text("Synthetic stop during wait")
                return False
        return True
    monkeypatch.setattr(FixtureRecovery, "wait_for_capacity", wait)
    engine = FixtureRecovery(tmp_path / "source", config=Config(offline=False))
    verifier = integrity.IntegrityResearch(tmp_path / "check", config=Config(offline=True))
    payload = {"phase": "continue", "plan": parent, "authorization_text": "Fix and continue synthetic queues"}
    try:
        result = prior.call(engine, "status", payload)
        if not recognized:
            assert result["stop_reason"] == "transport_or_unknown_stop"
            assert len(new_seen) == 1 and waits == []
            assert result["unknown_holds"] == stopped["unknown_holds"] + 1
            assert result["unattempted"] > 0
            return
        if interrupt_wait:
            assert result["stop_reason"] == "user_stop" and len(new_seen) == 1
            engine.close()
            (tmp_path / "source" / "STOP").unlink()
            engine = FixtureRecovery(tmp_path / "source", config=Config(offline=False))
            result = prior.call(engine, "status", payload)
            assert len(waits) == 2 and waits[0] == waits[1]
        else:
            assert len(waits) == 1
        assert result["reserved"] == 12 and result["unattempted"] == 0
        assert len(new_seen) + len(old_seen) == 12
        assert result["unknown_holds"] == stopped["unknown_holds"] + 1
        amended = json.loads((engine.ledger.root / "recovery-plan.json").read_text())["id"]
        plan = engine.ledger.get(amended, "luna_standard_plan")
        assert plan["capacity_lineage"] == [original, parent]
        assert plan["queues"] == engine.ledger.get(parent, "luna_standard_plan")["queues"]
        assert plan["selected_ceiling"] == 7
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='luna_capacity_stage_intent'").fetchone()[0] == 0
        report = prior.call(verifier, "status", {"source_owner": str(engine.ledger.root), "plan": amended})
        assert report["integrity_passed"] and report["reserved"] == 12
        prior.call(engine, "status", payload)
        assert len(new_seen) + len(old_seen) == 12
        with pytest.raises(AuditError, match="authorization_changed"):
            prior.call(engine, "status", {**payload, "authorization_text": "changed"})
        monkeypatch.setattr(recovery, "implementation", lambda: {})
        with pytest.raises(AuditError, match="implementation_changed"):
            prior.call(engine, "status", payload)
        engine.ledger.verify()
    finally:
        engine.close()
        verifier.close()


@pytest.mark.parametrize("mixed_failure", [False, True])
def test_recovery_waits_for_all_active_calls_and_mixed_failures_stop(tmp_path, monkeypatch, mixed_failure):
    _, parent, stopped, _ = prepare_parent(tmp_path / "source", monkeypatch)
    _, output = recovery.contract.fictional_example()
    second_started = threading.Event()
    calls, backoffs = [], []
    mutex = threading.Lock()
    def runner(*args, **kwargs):
        with mutex:
            calls.append(kwargs)
            number = len(calls)
        if number == 1:
            assert second_started.wait(5), "Fixture must exercise overlapping active calls"
            events, code = failed_events(), 1
        else:
            second_started.set()
            time.sleep(.05)
            if mixed_failure:
                events, code = failed_events("Fictional authentication failure"), 1
            else:
                events, code = [{"type": "thread.started"}, {"type": "turn.started"},
                    {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}},
                    {"type": "turn.completed"}], 0
        return SimpleNamespace(stdout="\n".join(json.dumps(e) for e in events), stderr="", returncode=code)
    original_init = SpeedProvider.__init__
    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.runner = runner
    monkeypatch.setattr(SpeedProvider, "__init__", init)
    state_init = recovery.RecoveryState.__init__
    def resumed_width(self, *args, **kwargs):
        state_init(self, *args, **kwargs)
        # Exercise the production state after a successful clean window.
        self.width, self.probe = 2, False
    monkeypatch.setattr(recovery.RecoveryState, "__init__", resumed_width)
    def wait(self, control, progress):
        if control.not_before:
            backoffs.append(progress("capacity_backoff"))
            assert len(calls) == 2 and backoffs[-1]["in_flight"] == 0
            (self.ledger.root / "STOP").write_text("Synthetic stop after drained capacity window")
            return False
        return True
    monkeypatch.setattr(FixtureRecovery, "wait_for_capacity", wait)
    engine = FixtureRecovery(tmp_path / "source", config=Config(offline=False))
    try:
        result = prior.call(engine, "status", {"phase": "continue", "plan": parent,
                            "authorization_text": "Synthetic recovery with overlapping calls"})
        assert len(calls) == 2
        assert result["reserved"] == stopped["reserved"] + 2
        assert result["unknown_holds"] == stopped["unknown_holds"] + (2 if mixed_failure else 1)
        assert len(backoffs) == (0 if mixed_failure else 1)
        assert result["stop_reason"] == ("transport_or_unknown_stop" if mixed_failure else "user_stop")
        engine.ledger.verify()
    finally:
        engine.close()
