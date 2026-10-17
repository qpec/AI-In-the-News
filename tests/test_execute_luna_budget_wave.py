"""Synthetic end-to-end bulk admission and one-shot dispatch integration."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_live_gateway import BUDGET_KIND
from newsresearch.event_batch_transport import BatchReceipt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import execute_luna_budget_wave as runner
finally:
    sys.path.pop(0)


def load_fixture(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tests" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wave = load_fixture("bulk_wave_fixture", "test_prepare_luna_budget_wave.py")
base = load_fixture("bulk_transport_fixture", "test_execute_luna_budget_batch.py")


def fixture(tmp_path, monkeypatch, *, failure=None):
    owner, plan = wave.prepared_fixture(tmp_path, monkeypatch)
    engine = wave.SeededWaveResearch(owner)
    try:
        engine.execute("status", {"seed": True, "plan": plan["id"]}, objective="Seed software-only canary accounting", actor="test:software")
        stage = engine.execute("status", {"plan": plan["id"], "max_per_corpus": 250},
                               objective="Stage software-only requests", actor="test:software")
    finally:
        engine.close()
    monkeypatch.setattr(runner, "OWNER", owner)
    transport = base.SyntheticTransport(failure)
    engine = runner.BulkExecutionResearch(owner, config=Config(offline=False), transport=transport)
    return engine, transport, plan, stage


def execute(engine, plan):
    return engine.execute("status", {"plan": plan["id"], "allow_paid_execution": True},
        objective="Test synthetic shared-budget bulk submission", actor="test:software")


def test_bulk_fulltext_submission_retains_same_budget_and_resume_never_repeats(tmp_path, monkeypatch):
    engine, transport, plan, stage = fixture(tmp_path, monkeypatch)
    try:
        result = execute(engine, plan)
        assert result["obstacle"] is None and result["gate_blockers"] == []
        assert result["counts"] == {"prepared_bulk": 4, "submitted_bulk": 4, "valid_bulk": 0,
            "invalid_bulk": 0, "pending_submitted_bulk": 4, "unconfirmed_create_bulk": 0, "unsubmitted_bulk": 0}
        assert len(transport.calls) == 8
        assert len(transport.files) == len(transport.jobs) == 2
        assert result["charged_estimate_usd"] > 0  # Existing canary spending remains.
        assert result["reserved_usd"] > 0
        assert result["own_reserved_input_tokens"] == 4 * 123
        for raw in transport.files.values():
            rows = [json.loads(line) for line in raw.splitlines()]
            assert len(rows) == 2
            assert all(row["body"]["max_output_tokens"] == 4096 for row in rows)
            assert all("Entire second paragraph" in row["body"]["input"][0]["content"][0]["text"] for row in rows)
        again = execute(engine, plan)
        assert len(transport.calls) == 8
        assert again["counts"] == result["counts"]
        assert again["budget_state"] == result["budget_state"]
        assert {job["manifest"] for job in result["jobs"]} == {item["manifest"] for item in stage["manifests"]}
    finally:
        engine.close()


def test_queue_guard_defers_without_upload_and_retains_reservations_and_receipts(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "OWN_QUEUE_TOKEN_CAP", 100)
    try:
        result = execute(engine, plan)
        assert result["obstacle"] is None
        assert result["deferrals"][0]["reason"] == "own_reserved_input_token_guard_deferred"
        assert result["counts"]["unsubmitted_bulk"] == 4
        assert result["reserved_usd"] > 0
        assert len(transport.calls) == 2 and not transport.files and not transport.jobs
        assert not engine.ledger.unresolved
        again = execute(engine, plan)
        assert len(transport.calls) == 2
        assert again["budget_state"] == result["budget_state"]
        assert again["reserved_usd"] == result["reserved_usd"]
    finally:
        engine.close()


def test_expensive_exact_count_defers_before_paid_inference(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    original = transport.perform

    def costly_count(request, body, client_request_id):
        if request["path"] == "/v1/responses/input_tokens":
            transport.calls.append((request, body, client_request_id))
            raw = canonical({"input_tokens": 2_000_000_000}).encode()
            return BatchReceipt(raw, 200, "synthetic-costly-count", body_sha256=hashlib.sha256(raw).hexdigest())
        return original(request, body, client_request_id)

    transport.perform = costly_count
    try:
        result = execute(engine, plan)
        assert result["deferrals"][0]["reason"] == "shared_operational_budget_admission_deferred"
        assert len(transport.calls) == 1 and not transport.files and not transport.jobs
        assert result["counts"]["submitted_bulk"] == 0
        assert result["committed_usd"] < 120
        assert not engine.ledger.unresolved
    finally:
        engine.close()


def test_unknown_create_blocks_other_manifest_and_all_future_dispatch(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch, failure="create_unknown")
    try:
        first = execute(engine, plan)
        assert first["obstacle"] == "batch_action_unknown_no_retry"
        assert first["counts"]["unconfirmed_create_bulk"] == 2
        assert first["counts"]["unsubmitted_bulk"] == 2
        assert first["reserved_usd"] > 0
        assert len(transport.calls) == 4
        second = execute(engine, plan)
        assert "shared_action_unknown_or_missing_receipt" in second["gate_blockers"]
        assert "prior_execution_technical_obstacle" in second["gate_blockers"]
        assert len(transport.calls) == 4
        assert second["reserved_usd"] == first["reserved_usd"]
    finally:
        engine.close()


def test_contract_drift_cannot_reach_provider(tmp_path, monkeypatch):
    engine, transport, plan, stage = fixture(tmp_path, monkeypatch)
    original = runner.validate_manifest

    def changed(engine, session, plan_id, plan, manifest_id, manifest, snapshot):
        manifest["tasks"][0]["descriptor"]["max_output_tokens"] = 2048
        return original(engine, session, plan_id, plan, manifest_id, manifest, snapshot)

    monkeypatch.setattr(runner, "validate_manifest", changed)
    try:
        with pytest.raises(AuditError, match="descriptor_binding_changed"):
            execute(engine, plan)
        assert transport.calls == []
    finally:
        engine.close()


def test_reservations_and_attempt_intents_precede_paid_create(tmp_path, monkeypatch):
    engine, transport, plan, _ = fixture(tmp_path, monkeypatch)
    original = transport.perform
    checked = []

    def guarded(request, body, client_request_id):
        if request["path"] == "/v1/batches":
            row = engine.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (BUDGET_KIND,)).fetchone()
            state = engine.ledger.get(row["id"], BUDGET_KIND)
            assert state["reserved_nanousd"] > 0
            assert len(engine.ledger.unresolved) >= 2
            checked.append(True)
        return original(request, body, client_request_id)

    transport.perform = guarded
    try:
        execute(engine, plan)
        assert checked == [True, True]
    finally:
        engine.close()
