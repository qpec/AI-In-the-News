"""Synthetic migration, queue packing, preserved accounting and single-writer checks."""
import json
from pathlib import Path
import sqlite3

import pytest

import test_luna_batch_remainder as fixture
import luna_batch_parallel as module
import check_luna_batch_remainder as checker
from newsresearch.common import AuditError, Config


def prepare(tmp_path, monkeypatch, record_count=5):
    data, _ = fixture.seed(tmp_path)
    records = [fixture.fixture.record(n, "incident-reports") for n in range(1001, 1001 + record_count)]
    data["codex_owner"] = str(tmp_path / "codex-expanded")
    source = fixture.SeedResearch(Path(data["codex_owner"]))
    try:
        result = fixture.execute(source, {"kind": "source", "queues": {"incident-reports": [r["descriptor"] for r in records]}, "spent": [records[-1]["descriptor"]["custom_id"]]})
        head = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    (Path(data["codex_owner"]) / "STOP").write_text("Synthetic stop")
    (Path(data["codex_owner"]) / "progress.json").write_text(json.dumps({"state": "user_stop", "in_flight": 0, "reserved": 1}))
    data["codex_plan"] = result["plan"]
    Path(data["integrity_report"]).write_text(json.dumps({"integrity_passed": True, "plan": result["plan"], "head_seq": head[0], "head_hash": head[1], "checked_at": "1970-01-01T00:00:10+00:00"}))
    original = module.parent.RemainderResearch(tmp_path / "original", transport=fixture.Transport(), clock=lambda: 20)
    plan = fixture.execute(original, data)
    mapping = {r["descriptor"]["custom_id"]: r for r in records}
    monkeypatch.setattr(module.parent.RemainderBatch, "materialize", lambda self, rows, partition: [mapping[r["custom_id"]] for r in rows])
    original.close()
    (tmp_path / "original" / "STOP").write_text("Synthetic versioned handoff")
    integrity = checker.BatchIntegrity(tmp_path / "integrity")
    try:
        fixture.execute(integrity, {"source_owner": str(tmp_path / "original"), "plan": plan["id"]})
    finally:
        integrity.close()
    migrate = module.MigrationResearch(tmp_path / "migration")
    try:
        fixture.execute(migrate, {"source_owner": str(tmp_path / "original"), "destination": str(tmp_path / "parallel"),
            "plan": plan["id"], "integrity_report": str(tmp_path / "integrity" / "latest-integrity.json"), "authorization_text": module.AUTHORIZATION})
    finally:
        migrate.close()
    amendment = json.loads((tmp_path / "parallel" / "parallel-plan.json").read_text())
    return plan, amendment


def test_capacity_prefix_migration_and_restart_never_recount_or_resend(tmp_path, monkeypatch):
    # Four 100-token tasks: the queue initially fits exactly two, then frees
    # capacity on settlement. The unchanged runner must preserve the tail.
    monkeypatch.setattr(module.parent, "QUEUE_TOKENS", 250)
    monkeypatch.setattr(module.parent.batch, "QUEUE_TOKENS", 250)
    plan, amendment = prepare(tmp_path, monkeypatch)
    before = (tmp_path / "original" / "state.sqlite3").read_bytes()
    fake = fixture.Transport()
    engine = module.PackingResearch(tmp_path / "parallel", transport=fake, clock=lambda: 21, config=Config(offline=True))
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"], "test_stop_after_submissions": 1}
    try:
        first = fixture.execute(engine, run)
        assert first["new_submitted"] == 2 and first["queued_input_tokens"] == 200
        assert first["corpora"]["incident-reports"]["unsubmitted"] == 2
        counts = sum(call == module.parent.batch.COUNT_ROUTE for call in fake.calls)
        assert counts == 4
        fake.terminal = True
        second = fixture.execute(engine, run)
        assert second["new_submitted"] == 4 and second["new_returned"] == 2
        third = fixture.execute(engine, {**run, "test_stop_after_submissions": None})
        assert third["new_submitted"] == third["new_returned"] == 4
        assert third["reserved_nanousd"] == 1402432
        assert sum(call == module.parent.batch.COUNT_ROUTE for call in fake.calls) == counts
        assert len(fake.jobs) == 2
        assert (tmp_path / "original" / "state.sqlite3").read_bytes() == before
        assert (tmp_path / "original" / "STOP").exists()
        assert plan["deadline_epoch"] == amendment["deadline_epoch"]
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "parallel-integrity")
    try:
        verified = fixture.execute(integrity, {"source_owner": str(tmp_path / "parallel"), "plan": plan["id"]})
        assert verified["integrity_passed"] and verified["new_results_replayed"] == 4
    finally:
        integrity.close()


def test_admission_memo_invalidates_on_change_and_still_honors_stop(tmp_path, monkeypatch):
    plan, amendment = prepare(tmp_path, monkeypatch)
    fake = fixture.Transport()
    engine = module.PackingResearch(tmp_path / "parallel", transport=fake, clock=lambda: 21)
    original = module.parent.RemainderBatch.admission_checks
    calls = []
    def counted(self):
        calls.append(self.db.total_changes)
        return original(self)
    monkeypatch.setattr(module.parent.RemainderBatch, "admission_checks", counted)
    runner = module.PackingBatch(tmp_path / "parallel" / "state.sqlite3", plan=plan, plan_id=plan["id"],
        amendment=amendment, engine=engine, transport=fake, clock=lambda: 21)
    try:
        runner.admission_bundle = True
        runner.admission_checks()
        runner.admission_checks()
        assert len(calls) == 1
        runner.db.execute("UPDATE meta SET value=value WHERE key='deadline_epoch'")
        runner.admission_checks()
        assert len(calls) == 2
        (tmp_path / "parallel" / "STOP").write_text("stop")
        with pytest.raises(module.parent.state.StateError, match="user_stop"):
            runner.admission_checks()
    finally:
        runner.close()
        engine.close()


def test_migration_rejects_uncheckpointed_parent_changes(tmp_path, monkeypatch):
    plan, _ = prepare(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "original" / "state.sqlite3") as db:
        db.execute("UPDATE budget_entries SET reserved_nanousd=0")
    migration = module.MigrationResearch(tmp_path / "second-migration")
    try:
        with pytest.raises(AuditError, match="checkpoint_mismatch"):
            fixture.execute(migration, {"source_owner": str(tmp_path / "original"), "destination": str(tmp_path / "rejected"),
                "plan": plan["id"], "integrity_report": str(tmp_path / "integrity" / "latest-integrity.json"), "authorization_text": module.AUTHORIZATION})
    finally:
        migration.close()
