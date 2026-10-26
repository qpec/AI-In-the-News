"""Synthetic Standard-only continuation; no network or paid requests."""
import json
import sqlite3

import pytest

import test_luna_standard_api as fixture
import luna_standard_finish as module
import check_luna_standard_finish as checker
from newsresearch.common import AuditError


def setup(tmp_path, monkeypatch, failure=None):
    plan, _, fake = fixture.setup(tmp_path, monkeypatch, failure)
    source = tmp_path / "standard"
    (source / "STOP").write_text("New explicit Standard-only continuation")
    check = fixture.checker.BatchIntegrity(tmp_path / "standard-seal-check")
    try:
        fixture.fixture.fixture.execute(check, {"source_owner": str(source), "plan": plan["id"]})
    finally:
        check.close()
    jobs = []
    with sqlite3.connect(source / "state.sqlite3") as db:
        for row in db.execute("SELECT job_id,payload FROM jobs WHERE reconciled=0"):
            job = json.loads(row[1])
            n = len(job["request_ids"])
            jobs.append({"job_id": row[0], "observed_status": "completed", "http_status": 200,
                "request_counts": {"total": n, "completed": n, "failed": 0}})
    status = tmp_path / "batch-status.json"
    status.write_text(json.dumps({"source_owner": str(source), "source_state_unchanged": True,
        "all_remote_jobs_terminal": True, "jobs": jobs}))
    engine = module.FinishMigration(tmp_path / "finish-migration")
    try:
        fixture.fixture.fixture.execute(engine, {"source_owner": str(source), "destination": str(tmp_path / "finish"),
            "plan": plan["id"], "integrity_report": str(tmp_path / "standard-seal-check/latest-integrity.json"),
            "batch_status": str(status), "user_instruction": module.AUTHORIZATION, "latest_steering": module.STEERING})
    finally:
        engine.close()
    return plan, json.loads((tmp_path / "finish/finish-plan.json").read_text()), fake


def test_start_standard_before_batch_collection_preserve_counts_and_restart(tmp_path, monkeypatch):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    original = (tmp_path / "standard/state.sqlite3").read_bytes()
    fake.terminal = True
    clock = fixture.Clock()
    engine = module.FinishResearch(tmp_path / "finish", transport=fake, clock=clock)
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]}
    counts = fake.calls.count(module.batch.COUNT_ROUTE)
    try:
        first = fixture.fixture.fixture.execute(engine, {**run, "test_stop_after": 1})
        assert first["standard_saved"] == 1 and first["pending_jobs"] == 1
        assert first["new_returned"] == 1 and first["standard_worker_ceiling"] == 64
        assert first["standard_control"]["tpm"] == 1_000_000
        assert first["standard_control"]["rpm"] == 4000
        clock.value = 100
        second = fixture.fixture.fixture.execute(engine, run)
        assert second["standard_saved"] == 2 and second["pending_jobs"] == 0
        assert second["new_returned"] == 4 and second["reason"] == "eligible_queue_exhausted"
        assert second["reserved_nanousd"] == 1402432
        assert fake.calls.count(module.batch.COUNT_ROUTE) == counts
        assert len(fake.standard_ids) == 2 and len(fake.jobs) == 1
        assert (tmp_path / "standard/state.sqlite3").read_bytes() == original
        assert (tmp_path / "standard/STOP").exists()
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "finish-check")
    try:
        result = fixture.fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "finish"), "plan": plan["id"]})
        assert result["integrity_passed"] and result["new_results_replayed"] == 4
        assert result["created_article_intents"] == 4 and result["operational_state_matches_latest_checkpoint"]
    finally:
        integrity.close()


def test_new_standard_failure_is_retained_and_cannot_resume(tmp_path, monkeypatch):
    plan, amendment, fake = setup(tmp_path, monkeypatch, "429")
    engine = module.FinishResearch(tmp_path / "finish", transport=fake, clock=lambda: 30)
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"], "test_stop_after": 1}
    try:
        result = fixture.fixture.fixture.execute(engine, run)
        assert result["standard_saved"] == 1 and result["unknown_cost_holds"] == 2
        with pytest.raises(AuditError, match="new_failed_gateway_action_no_retry"):
            fixture.fixture.fixture.execute(engine, run)
        assert len(fake.standard_ids) == 1
    finally:
        engine.close()


def records(kind, members):
    payload = module.canonical({"members": members})
    artifact = module.hashlib.sha256(payload.encode()).hexdigest()
    return {"id": module.digest({"kind": kind, "key": kind, "payload": artifact, "supersedes": None}),
        "kind": kind, "logical_key": kind, "payload": payload, "artifact": artifact, "supersedes": None}


@pytest.mark.parametrize("phase,unknown,accepted", [("count", False, True), ("count", True, False), ("create", False, False)])
def test_only_closed_parent_count_502_can_be_quarantined(phase, unknown, accepted):
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE actions(action_id TEXT,phase TEXT,status TEXT,request_json TEXT,receipt_json TEXT);
        CREATE TABLE requests(custom_id TEXT,submitted INTEGER,status TEXT);
        CREATE TABLE counts(custom_id TEXT);
        CREATE TABLE budget_entries(custom_id TEXT,payload TEXT,status TEXT);
        CREATE TABLE results(custom_id TEXT,payload TEXT);
    """)
    receipt = {"action_id": "test-count", "status": 502, "unknown": unknown,
        "retention_error": None, "error_type": "http_error", "body_sha256": "a" * 64}
    db.execute("INSERT INTO actions VALUES(?,?,'unknown',?,?)", ("test-count", phase,
        module.canonical({"custom_ids": ["held-one"]}), module.canonical(receipt)))
    db.execute("INSERT INTO requests VALUES('held-one',0,'logged')")
    class Journal:
        def execute(self, *_):
            return [records(module.lean.INTENT, [{"action_id": "test-count", "request": module.batch.COUNT_ROUTE, "custom_ids": ["held-one"]}]),
                records(module.lean.RECEIPT, [receipt])]
    try:
        if accepted:
            result = module.pin_parent_exceptions(db, Journal())
            assert result["quarantined_custom_ids"] == ["held-one"]
            assert set(result["held_actions"]) == set(result["failed_receipts"]) == {"test-count"}
            assert db.execute("SELECT status FROM actions").fetchone()[0] == "unknown"
        else:
            with pytest.raises(AuditError, match="not_a_closed_count_502"):
                module.pin_parent_exceptions(db, Journal())
    finally:
        db.close()


@pytest.mark.parametrize("block", ["STOP", "deadline"])
def test_stop_and_deadline_prevent_standard_admission(tmp_path, monkeypatch, block):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    fake.terminal = True
    if block == "STOP":
        (tmp_path / "finish/STOP").write_text("Stop")
    engine = module.FinishResearch(tmp_path / "finish", transport=fake,
        clock=lambda: plan["deadline_epoch"] + 1 if block == "deadline" else 30)
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]}
    try:
        if block == "STOP":
            with pytest.raises(module.state.StateError, match="user_stop"):
                fixture.fixture.fixture.execute(engine, run)
        else:
            result = fixture.fixture.fixture.execute(engine, {**run, "collect_only": True})
            assert result["new_returned"] == 2 and result["standard_saved"] == 0
        assert not fake.standard_ids
    finally:
        engine.close()


def test_inherited_final_batch_error_keeps_full_reservation_and_does_not_retry(tmp_path, monkeypatch):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    # This tests the admission predicate independently of unchanged Batch parsing.
    engine = module.FinishResearch(tmp_path / "finish", transport=fake, clock=lambda: 30)
    runner = module.FinishBatch(tmp_path / "finish/state.sqlite3", plan=plan, plan_id=plan["id"],
        amendment=amendment, engine=engine, transport=fake, clock=lambda: 30)
    try:
        custom, inherited = next(iter(amendment["pending_batch_members"].items()))
        job_id = inherited["job_id"]
        amendment["completed_batch_jobs"][job_id]["request_counts"]["failed"] = 1
        result = {"custom_id": custom, "raw_status": "error", "status": "error", "usage_complete": False,
            "usage": None, "technical_failure": True, "lean_new_result": True}
        original = inherited["reservation"]
        cost = {**original, "status": "unknown", "settlement": None}
        runner.db.execute("UPDATE jobs SET reconciled=1 WHERE job_id=?", (job_id,))
        runner.db.execute("INSERT INTO results VALUES(?,'error',?)", (custom, module.canonical(result)))
        runner.db.execute("UPDATE budget_entries SET status='unknown',payload=? WHERE custom_id=?", (module.canonical(cost), custom))
        runner.admission_checks()
        assert runner.preserved_batch_error(custom, cost, result)
        assert not runner.preserved_batch_error(custom, {**cost, "reserved_nanousd": 0}, result)
        amendment["completed_batch_jobs"][job_id]["request_counts"]["failed"] = 0
        with pytest.raises(AuditError, match="new_unknown_or_frozen_cost"):
            runner.admission_checks()
        assert not fake.standard_ids
    finally:
        runner.close()
        engine.close()
