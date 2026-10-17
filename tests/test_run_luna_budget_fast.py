"""Synthetic audited dispatch tests; no production owner, sources or HTTP."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical
from newsresearch.event_batch_live_gateway import ACTION_IDENTITY_KIND, ACTION_KIND, RECEIPT_KIND
from newsresearch.event_batch_transport import BatchReceipt, count_request_body
from newsresearch.runtime import audited_handler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import run_luna_budget_fast as fast
finally:
    sys.path.pop(0)

spec = importlib.util.spec_from_file_location("fast_bulk_fixture", ROOT / "tests/test_execute_luna_budget_wave.py")
assert spec and spec.loader
bulk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bulk)


class DispatchHarness(fast.FastResearch):
    @audited_handler
    def _status(self, session, context, data):
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, fast.PLAN_KIND)
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        self.fast_run = "synthetic-fast-run"
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        jobs = {row["manifest"] for row in view["jobs"]}
        manifests = [row for row in view["manifests"] if row["phase"] == "bulk" and row["id"] not in jobs]
        if data.get("seed_alias"):
            task = manifests[0]["tasks"][0]
            body = self.ledger.artifacts.read(task["request_body_ref"])
            self.action(session, plan_id, policy, "count:previous-other-custom-id",
                {"method": "POST", "path": "/v1/responses/input_tokens"}, canonical(count_request_body(body)).encode())
        if data.get("diagnostic"):
            manifest, task = manifests[0], manifests[0]["tasks"][0]
            rows = {name: self.rows(session, kind) for name, kind in
                    (("actions", ACTION_KIND), ("identities", ACTION_IDENTITY_KIND), ("receipts", RECEIPT_KIND))}
            items = fast.diagnose_counts(plan_id, [{**task, "manifest": manifest["id"]}], rows, self.ledger.artifacts.read_bytes)
            items[0].update(frozen_attempt_id=manifest["attempt_ids"][0], unresolved_paid_intent=False,
                            projected_attempt_status=None)
            if data.get("tamper"):
                items[0]["request_body_ref"] = "a" * 64
            proof = self.ledger.record(session, fast.DIAGNOSTIC_KIND, "synthetic-diagnostic", {
                "plan": plan_id, "budget_state": state, "budget_frozen": False,
                "unknown_or_frozen_budget_entries": 0, "count_diagnostics": items})
            return self.validate_diagnostic(session, plan_id, proof, view, policy, state)
        submitted = []
        reason = None
        for manifest in manifests:
            raw = fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, fast.core.load_contract_snapshot())
            book, state, reason, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                active_tokens=fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
                queue_cap=data.get("queue_cap", fast.MAX_QUEUE), workers=4,
                deadline=data.get("deadline", time.time() + 600))
            if job:
                submitted.append(job)
                view["jobs"].append(job)
            if reason:
                break
        return {"reason": reason, "submitted": len(submitted), "reserved": book.reserved_nanousd,
                "state": state, "events": len(book.to_dict()["events"]),
                "active_input_tokens": fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"])}


def fixture(tmp_path, monkeypatch, failure=None):
    original, transport, plan, stage = bulk.fixture(tmp_path, monkeypatch, failure=failure)
    owner = original.ledger.root
    original.close()
    return DispatchHarness(owner, config=Config(offline=False), transport=transport), transport, plan, stage


def execute(engine, plan, **kwargs):
    return engine.execute("status", {"plan": plan["id"], **kwargs},
        objective="Test bounded fast dispatch with synthetic evidence and HTTP", actor="test:software")


def test_exact_existing_count_reused_and_real_gateway_accepts_new_files(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        result = execute(engine, plan, seed_alias=True)
        assert result["submitted"] == 2 and result["reason"] is None
        assert result["active_input_tokens"] == 4 * 123
        assert len([call for call in transport.calls if call[0]["path"] == "/v1/responses/input_tokens"]) == 4
        assert len(transport.jobs) == len(transport.files) == 2
        for raw in transport.files.values():
            assert all(json.loads(line)["body"]["max_output_tokens"] == 4096 for line in raw.splitlines())
        again = execute(engine, plan)
        assert again["submitted"] == 0 and again["state"] == result["state"]
        assert len(transport.calls) == 8  # Four distinct counts, two uploads, two creates, no retries.
    finally:
        engine.close()


def test_queue_pressure_creates_no_partial_new_reservations_and_cached_counts_resume(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        first = execute(engine, plan, queue_cap=200)
        assert first["reason"] == "file_exceeds_provisional_queue_cap"
        assert first["reserved"] == 0 and first["active_input_tokens"] == 0
        assert len(transport.calls) == 2 and not transport.files
        again = execute(engine, plan, queue_cap=200)
        assert again["state"] == first["state"] and len(transport.calls) == 2
        resumed = execute(engine, plan)
        assert resumed["submitted"] == 2 and len(transport.calls) == 8
    finally:
        engine.close()


def test_active_provider_tokens_exclude_unsubmitted_reservations(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    original = transport.perform
    clock = [time.time()]

    def upload_ends_admission(request, body, client_request_id):
        result = original(request, body, client_request_id)
        if request["path"] == "/v1/files":
            clock[0] += 1000
        return result

    transport.perform = upload_ends_admission
    monkeypatch.setattr(fast.time, "time", lambda: clock[0])
    try:
        result = execute(engine, plan, deadline=clock[0] + 100)
        assert result["reason"] == "deadline" and result["reserved"] > 0
        assert result["active_input_tokens"] == 0
        assert len(transport.files) == 1 and not transport.jobs
        assert len(engine.ledger.unresolved) == 2
        assert all(call[0]["path"] != "/v1/batches" for call in transport.calls)
    finally:
        engine.close()


def test_budget_pressure_does_not_reserve_partial_file(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    original = transport.perform

    def costly(request, body, client_request_id):
        if request["path"] == "/v1/responses/input_tokens":
            transport.calls.append((request, body, client_request_id))
            return BatchReceipt(canonical({"input_tokens": 2_000_000_000}).encode(), 200, "test-count")
        return original(request, body, client_request_id)

    transport.perform = costly
    try:
        result = execute(engine, plan, queue_cap=10_000_000_000)
        assert result["reason"] == "budget_pressure" and result["reserved"] == 0
        assert not transport.files and not transport.jobs and not engine.ledger.unresolved
    finally:
        engine.close()


def test_unknown_create_retains_reserve_and_cannot_be_redispatched(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch, "create_unknown")
    try:
        with pytest.raises(ResearchError, match="unknown_no_retry"):
            execute(engine, plan)
        calls = len(transport.calls)
        assert len(engine.ledger.unresolved) == 2
        with pytest.raises(AuditError, match="unknown_action_no_retry"):
            execute(engine, plan)
        assert len(transport.calls) == calls
    finally:
        engine.close()


def test_pre_dispatch_collision_proof_is_recomputed_against_exact_saved_actions(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        result = execute(engine, plan, seed_alias=True, diagnostic=True)
        assert len(result["verified_collisions"]) == 1
        assert len(transport.calls) == 1 and not transport.jobs
        with pytest.raises(AuditError, match="task_or_paid_attempt_changed"):
            execute(engine, plan, diagnostic=True, tamper=True)
    finally:
        engine.close()


@pytest.mark.parametrize("pressure,pending,expected", [
    ("budget_pressure", 1, None), ("queue_pressure", 2, None),
    ("budget_pressure", 0, "budget_deferred"), ("queue_pressure", 0, "capacity_deferred"),
])
def test_reservation_pressure_waits_while_paid_jobs_can_release_known_unused_reserve(pressure, pending, expected):
    assert fast.terminal_reason(pressure, pending) == expected


def test_full_file_admission_counts_both_active_input_and_incremental_money():
    values = dict(active_tokens=10, candidate_tokens=20, queue_cap=30, incremental_nanousd=5, available_nanousd=5)
    assert fast.admission_reason(**values) is None
    assert fast.admission_reason(**{**values, "active_tokens": 11}) == "queue_pressure"
    assert fast.admission_reason(**{**values, "available_nanousd": 4}) == "budget_pressure"
