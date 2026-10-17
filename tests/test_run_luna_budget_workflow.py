"""Synthetic controller scheduling and audited restart checks; no live calls."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import audited_handler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import run_luna_budget_workflow as runner
finally:
    sys.path.pop(0)


class Simulation:
    def __init__(self, **changes):
        self.clock, self.calls, self.sleeps = 0.0, [], []
        self.state = {"deadline_epoch": 300.0, "finished_reason": None, "blockers": [],
            "pending_jobs": 0, "unprojected": 0, "admission_closed": False, "token_wait": False,
            "staged_unsubmitted": [], "unmanifested": 2, "submitted": 0, "assessments": 0,
            "budget_state": "initial"}
        self.state.update(changes)
        self.hooks = {}

    def step(self, stage, data):
        self.calls.append((stage, deepcopy(data), self.clock))
        if stage == "control":
            if data.get("finish_reason"):
                self.state["finished_reason"] = data["finish_reason"]
            return deepcopy(self.state)
        if stage in self.hooks:
            return self.hooks[stage](data)
        if stage == "stage":
            self.state.update(staged_unsubmitted=["frozen-file"], unmanifested=0)
            return {"status": "staged", "manifests": ["frozen-file"]}
        if stage == "submit":
            self.state.update(staged_unsubmitted=[], pending_jobs=1, submitted=2, budget_state="reserved")
            return {"counts": {"unconfirmed_create_bulk": 0}, "jobs": ["job"]}
        if stage == "reconcile":
            self.state.update(pending_jobs=0, assessments=self.state["submitted"], unprojected=2,
                              budget_state="settled", token_wait=False)
            return {"status_counts": {"valid": 1, "invalid": 1}}
        if stage == "project":
            self.state["unprojected"] = 0
            return {"derived_valid": 2}
        raise AssertionError(stage)

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds

    def run(self):
        return runner.run_loop(self.step, plan="synthetic", now=lambda: self.clock,
                               sleep=self.sleep, emit=lambda _: None)

    def stages(self):
        return [name for name, _, _ in self.calls if name != "control"]


def test_full_lifecycle_stages_then_submits_polls_projects_without_retry():
    sim = Simulation()
    assert sim.run()["finished_reason"] == "complete"
    assert sim.stages() == ["stage", "submit", "reconcile", "project"]
    assert sim.sleeps == []


def test_existing_staged_file_submitted_without_staging_another():
    sim = Simulation(staged_unsubmitted=["frozen-file"], unmanifested=0)
    assert sim.run()["finished_reason"] == "complete"
    assert sim.stages()[0] == "submit"
    assert "stage" not in sim.stages()


def test_budget_deferral_closes_admission_but_drains_and_projects():
    sim = Simulation(admission_closed=True, pending_jobs=1, submitted=2,
                     staged_unsubmitted=["deferred-file"], unmanifested=900)
    assert sim.run()["finished_reason"] == "budget_deferred"
    assert sim.stages() == ["reconcile", "project"]
    assert sim.state["staged_unsubmitted"] == ["deferred-file"]
    assert sim.state["unmanifested"] == 900


def test_token_deferral_waits_for_accounting_before_same_manifest_submission():
    sim = Simulation(pending_jobs=1, submitted=2, token_wait=True,
                     staged_unsubmitted=["deferred-file"], unmanifested=0)
    polls = []

    def poll(_):
        polls.append(sim.clock)
        if len(polls) == 2:
            sim.state.update(pending_jobs=0, assessments=2, token_wait=False, budget_state="settled-old")
        elif len(polls) == 3:
            sim.state.update(pending_jobs=0, assessments=4, token_wait=False, budget_state="settled-new")
        return {"status_counts": {}}

    sim.hooks["reconcile"] = poll
    assert sim.run()["finished_reason"] == "complete"
    assert polls[:2] == [0.0, 30.0]
    assert sim.stages() == ["reconcile", "reconcile", "submit", "reconcile"]
    assert sim.sleeps and min(sim.sleeps) >= 30


def test_unchanged_jobs_use_capped_backoff_and_preserve_pending_at_deadline():
    sim = Simulation(pending_jobs=1, submitted=2, admission_closed=True, deadline_epoch=300)
    sim.hooks["reconcile"] = lambda _: {"status_counts": {}}
    result = sim.run()
    assert result["finished_reason"] == "deadline" and result["pending_jobs"] == 1
    assert sim.sleeps == [30.0, 60.0, 120.0, 90.0]
    assert [at for name, _, at in sim.calls if name == "reconcile"] == [0.0, 30.0, 90.0, 210.0]


@pytest.mark.parametrize("failure", ["unknown", "obstacle", "frozen"])
def test_technical_poll_failure_stops_without_admission(failure):
    sim = Simulation(pending_jobs=1, submitted=2)
    sim.hooks["reconcile"] = lambda _: {"status_counts": {"unknown": int(failure == "unknown")},
        "obstacles": ["synthetic"] if failure == "obstacle" else [], "budget_frozen": failure == "frozen"}
    assert sim.run()["finished_reason"] == "technical_stop"
    assert sim.stages() == ["reconcile"]


def test_deadline_inside_staging_prevents_submission():
    sim = Simulation(deadline_epoch=10)

    def stage(_):
        sim.clock = 15
        sim.state.update(staged_unsubmitted=["new"], unmanifested=0)
        return {"manifests": ["new"]}

    sim.hooks["stage"] = stage
    assert sim.run()["finished_reason"] == "deadline"
    assert sim.stages() == ["stage"]


def test_terminal_resume_does_no_work_and_orphan_token_deferral_stops():
    sim = Simulation(finished_reason="deadline")
    assert sim.run()["finished_reason"] == "deadline" and sim.stages() == []
    sim = Simulation(token_wait=True, staged_unsubmitted=["waiting"])
    assert sim.run()["finished_reason"] == "capacity_blocked_without_pending_jobs"
    assert sim.stages() == []


def test_audit_failure_propagates_without_any_fallback_or_retry():
    sim = Simulation(staged_unsubmitted=["frozen"], unmanifested=0)

    def fail(_):
        raise AuditError("synthetic_storage_failure")

    sim.hooks["submit"] = fail
    with pytest.raises(AuditError, match="synthetic_storage_failure"):
        sim.run()
    assert sim.stages() == ["submit"]


def test_continuation_keeps_raw_error_total_but_checks_current_audited_blockers():
    sim = Simulation(pending_jobs=1, submitted=2, unmanifested=0)

    def poll(_):
        sim.state.update(pending_jobs=0, assessments=2)
        return {"status_counts": {"error": 1, "valid": 1}}

    sim.hooks["reconcile"] = poll
    result = runner.run_loop(sim.step, plan="synthetic", continuation_ref="verified-proof",
                             now=lambda: sim.clock, sleep=sim.sleep, emit=lambda _: None)
    assert result["finished_reason"] == "complete"
    assert sim.stages() == ["reconcile"]
    assert all(data.get("continuation_ref") == "verified-proof" for _, data, _ in sim.calls)


def test_new_technical_failure_stops_continuation_before_any_admission():
    sim = Simulation(pending_jobs=1, submitted=2)

    def poll(_):
        sim.state.update(pending_jobs=0, assessments=2, blockers=["technical_or_unknown_assessment"])
        return {"status_counts": {"error": 2}}

    sim.hooks["reconcile"] = poll
    result = runner.run_loop(sim.step, plan="synthetic", continuation_ref="verified-proof",
                             now=lambda: sim.clock, sleep=sim.sleep, emit=lambda _: None)
    assert result["finished_reason"] == "technical_stop"
    assert sim.stages() == ["reconcile"]


def fixture_module():
    spec = importlib.util.spec_from_file_location("controller_fixture", ROOT / "tests/test_execute_luna_budget_batch.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("failure", [None, "count_unknown"])
def test_audited_controller_resume_preserves_deadline_budget_and_unknown_block(tmp_path, monkeypatch, failure):
    base = fixture_module()

    class Seed(base.FixtureResearch):
        @audited_handler
        def _status(self, session, context, data):
            result = super()._status(session, context, data)
            if data["phase"] == "fixture":
                plan = self.ledger.get(result["plan"], runner.PLAN_KIND)
                result["plan"] = self.ledger.record(session, runner.PLAN_KIND, "synthetic-controller-plan",
                                                     {**plan, "implementation": {}})
            return result

    owner = tmp_path / "protected"
    transport = base.SyntheticTransport(failure)
    engine = Seed(owner, config=Config(offline=False), transport=transport)
    try:
        plan = base.execute(engine, "fixture")["plan"]
        submission = base.execute(engine, "submit", plan)
    finally:
        engine.close()
    monkeypatch.setattr(runner, "OWNER", owner)
    clock = [1000.0]
    monkeypatch.setattr(runner.time, "time", lambda: clock[0])
    data = {"plan": plan, "max_runtime_seconds": 100, "max_per_corpus": 250}

    def read(**extra):
        engine = runner.ControlResearch(owner, config=Config(offline=True))
        try:
            return engine.execute("status", {**data, **extra}, objective="Synthetic audited scheduler status",
                                  actor="test:synthetic")
        finally:
            engine.close()

    first = read()
    clock[0] = 1050
    second = read()
    assert first["deadline_epoch"] == second["deadline_epoch"] == 1100
    assert first["run"] == second["run"]
    assert first["budget_state"] == second["budget_state"] == submission["budget_state"]
    assert second["pending_jobs"] == (2 if failure is None else 0)
    assert bool(second["blockers"]) == bool(failure)
    assert len(transport.calls) == (20 if failure is None else 1)
    terminal = read(finish_reason="technical_stop" if failure else "deadline")
    assert read()["finished_reason"] == terminal["finished_reason"]
    with pytest.raises(AuditError, match="binding_changed_no_reset"):
        read(max_runtime_seconds=101)
