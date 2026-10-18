"""Candidate scheduling tested with the actual shared dispatch and fake HTTP."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

import pytest

from newsresearch.common import Config, Context, Json, canonical
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import audited_handler

import test_run_luna_budget_fast as fixture
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    from luna_budget_fill_scheduler_candidate import FillFirstScheduler, MAX_SUBMISSIONS_BEFORE_POLL
finally:
    sys.path.pop(0)

fast, wave = fixture.fast, fixture.bulk.wave


def choose(scheduler: FillFirstScheduler, **changes: Any) -> str:
    values = dict(pending=True, staged=True, unmanifested=True, startup=False, pressure=None, poll_due=True)
    return scheduler.choose(**{**values, **changes})


def test_due_poll_does_not_preempt_available_capacity() -> None:
    scheduler = FillFirstScheduler()
    for _ in range(MAX_SUBMISSIONS_BEFORE_POLL):
        assert choose(scheduler) == "submit"
        scheduler.submitted()
    assert choose(scheduler) == "reconcile"
    scheduler.reconciled()
    assert choose(scheduler) == "submit"


@pytest.mark.parametrize("pressure", ["queue_pressure", "budget_pressure", "file_exceeds_provisional_queue_cap"])
def test_exact_admission_pressure_reconciles_before_further_submission(pressure: str) -> None:
    scheduler = FillFirstScheduler()
    assert choose(scheduler, pressure=pressure) == "reconcile"
    assert choose(scheduler, pressure=pressure, poll_due=False) == "wait"


def test_startup_observes_existing_work_before_new_creates() -> None:
    scheduler = FillFirstScheduler()
    assert choose(scheduler, startup=True) == "reconcile"
    assert choose(scheduler, startup=True, poll_due=False) == "wait"


def test_staging_can_fill_capacity_and_exhausted_queue_is_drained() -> None:
    scheduler = FillFirstScheduler()
    assert choose(scheduler, staged=False) == "stage"
    assert choose(scheduler, staged=False, unmanifested=False) == "reconcile"
    assert choose(scheduler, staged=False, unmanifested=False, poll_due=False) == "wait"
    assert choose(scheduler, pending=False, staged=False, unmanifested=False) == "wait"


class FillHarness(fast.FastResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, fast.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        self.fast_run = "synthetic-fill-first"
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        scheduler = FillFirstScheduler()
        decisions, pressure = [], None
        for manifest in [row for row in view["manifests"] if row["phase"] == "bulk"]:
            # Simulate counts/validation taking longer than a poll interval:
            # every decision is due, as in the reported underfilling case.
            decision = scheduler.choose(pending=bool(view["jobs"]), staged=True, unmanifested=False,
                startup=False, pressure=pressure, poll_due=True)
            decisions.append(decision)
            if decision == "reconcile":
                break
            assert decision == "submit"
            raw = fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest,
                fast.core.load_contract_snapshot())
            book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                active_tokens=fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
                queue_cap=20_000_000, workers=16, deadline=data["deadline"])
            if pressure == "deadline":
                break  # The unchanged outer controller makes this terminal.
            if job:
                view["jobs"].append(job)
                scheduler.submitted()
        active = fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"])
        return {"decisions": decisions, "jobs": len(view["jobs"]), "active_tokens": active,
            "pressure": pressure, "reserved": book.reserved_nanousd, "book": book.to_dict(),
            "manifest_ids": [row["manifest"] for row in view["jobs"]],
            "submission_count": scheduler.submissions_since_poll}


def setup_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Json, Any]:
    original = wave.fixture_module.synthetic_export
    monkeypatch.setattr(wave.fixture_module, "synthetic_export", lambda root, corpus: original(root, corpus, count=12))
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    seed = wave.SeededWaveResearch(owner)
    try:
        seed.execute("status", {"plan": plan["id"], "seed": True}, objective="Seed fictional settled canaries", actor="test:software")
        for _ in range(4):
            seed.execute("status", {"plan": plan["id"], "max_per_corpus": 1},
                objective="Stage separate fictional one-request files", actor="test:software")
    finally:
        seed.close()
    transport = fixture.bulk.base.SyntheticTransport()
    original_perform = transport.perform
    def perform(request: Json, body: bytes | None, client_request_id: str) -> BatchReceipt:
        if request["path"] == "/v1/responses/input_tokens":
            transport.calls.append((request, body, client_request_id))
            raw = canonical({"input_tokens": 5_000_000}).encode()
            return BatchReceipt(raw, 200, "synthetic-count-" + str(len(transport.calls)),
                body_sha256=hashlib.sha256(raw).hexdigest())
        return original_perform(request, body, client_request_id)
    transport.perform = perform
    return owner, plan, transport


def test_shared_gateway_fills_four_simultaneous_jobs_before_poll_without_partial_fifth_reservation(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner, plan, transport = setup_owner(tmp_path, monkeypatch)
    engine = FillHarness(owner, config=Config(offline=False), transport=transport)
    try:
        result = engine.execute("status", {"plan": plan["id"], "deadline": 10_000_000_000},
            objective="Test fictional fill-first shared queue admission", actor="test:software")
        assert result["jobs"] == result["submission_count"] == 4
        assert result["active_tokens"] == 20_000_000 and result["pressure"] == "queue_pressure"
        assert result["decisions"] == ["submit"] * 5 + ["reconcile"]
        assert len(set(result["manifest_ids"])) == 4
        assert len(transport.files) == len(transport.jobs) == 4
        assert all(request["method"] == "POST" for request, _, _ in transport.calls)
        reserved = [event for event in result["book"]["events"] if event["action"] == "reserve"]
        assert len(reserved) == 16 + 4  # The blocked fifth file reserves nothing.
        assert len({event["value"]["request_id"] for event in reserved}) == 20
        assert all(event["value"]["max_output_tokens"] == 4096 for event in reserved)
        assert result["book"]["config"]["ceiling_nanousd"] == 150_000_000_000
        assert result["book"]["config"]["operational_limit_nanousd"] == 120_000_000_000
    finally:
        engine.close()


def test_fill_priority_cannot_dispatch_past_original_deadline(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner, plan, transport = setup_owner(tmp_path, monkeypatch)
    engine = FillHarness(owner, config=Config(offline=False), transport=transport)
    try:
        result = engine.execute("status", {"plan": plan["id"], "deadline": 0},
            objective="Test fictional fill scheduling at original deadline", actor="test:software")
        assert result["jobs"] == result["active_tokens"] == result["submission_count"] == 0
        assert result["pressure"] == "deadline" and transport.calls == []
        assert result["reserved"] == 0
    finally:
        engine.close()
