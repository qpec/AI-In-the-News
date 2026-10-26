"""Offline integrity replay with saved results, incremental checkpoints and tampering."""
import json
import sqlite3

import pytest

import test_luna_batch_remainder as fixture
import check_luna_batch_remainder as check
from newsresearch.common import AuditError


def test_operational_snapshot_releases_live_lock_and_preserves_view(tmp_path):
    path = tmp_path / "state.sqlite3"
    with sqlite3.connect(path, timeout=0) as live:
        live.execute("CREATE TABLE example(value INTEGER)")
        live.execute("INSERT INTO example VALUES(1)")
    snapshot, original_hash = check.operational_snapshot(path)
    try:
        with sqlite3.connect(path, timeout=0) as live:
            assert original_hash == check.handoff.state_hash(live)
            live.execute("UPDATE example SET value=2")
        assert snapshot.execute("SELECT value FROM example").fetchone()[0] == 1
    finally:
        snapshot.close()


def test_incremental_replay_preserves_invalid_results_and_rejects_tampering(tmp_path, monkeypatch):
    worker, fake, plan, _ = fixture.setup(tmp_path, monkeypatch)
    checker = check.BatchIntegrity(tmp_path / "checker")
    data = {"source_owner": str(worker.ledger.root), "plan": plan["id"]}
    try:
        fixture.execute(worker, {"phase": "run", "plan": plan["id"], "test_stop_after_submissions": 2})
        first = fixture.execute(checker, data)
        assert first["integrity_passed"] and first["created_article_intents"] == 2
        assert first["new_results_replayed"] == 0
        fake.terminal = True
        fixture.execute(worker, {"phase": "run", "plan": plan["id"]})
        second = fixture.execute(checker, data)
        assert second["new_results_replayed"] == 2 and second["new_files_replayed"] == 2
        assert all(row["status"] == "invalid" for row in second["new_raw_counts"])
        assert second["operational_state_matches_latest_checkpoint"]
        third = fixture.execute(checker, data)
        assert third["new_results_replayed"] == 0 and third["new_events_verified"] == 0
        # The production schema itself rejects edits to sealed journal events.
        with sqlite3.connect(worker.ledger.root / "research.sqlite3") as db:
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                db.execute("UPDATE events SET event_hash=? WHERE seq=?", ("1" * 64, third["head_seq"]))
        with sqlite3.connect(worker.ledger.root / "state.sqlite3") as db:
            db.execute("UPDATE budget_entries SET payload='{}' WHERE status='unknown'")
        with pytest.raises(AuditError, match="imported_hold_changed"):
            fixture.execute(checker, data)
        assert len(fake.calls) > 0
    finally:
        checker.close()
        worker.close()


def test_changed_raw_artifact_is_rejected(tmp_path, monkeypatch):
    worker, fake, plan, _ = fixture.setup(tmp_path, monkeypatch)
    checker = check.BatchIntegrity(tmp_path / "checker")
    try:
        fixture.execute(worker, {"phase": "run", "plan": plan["id"], "test_stop_after_submissions": 2})
        fake.terminal = True
        fixture.execute(worker, {"phase": "run", "plan": plan["id"]})
        row = worker.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_batch_remainder_file_result' LIMIT 1").fetchone()
        ref = json.loads(row[0])["raw_files"]["output_file_id"]
        (worker.ledger.root / "objects" / ref).write_bytes(b"changed")
        before = len(fake.calls)
        with pytest.raises(check.state.StateError, match="hash_mismatch"):
            fixture.execute(checker, {"source_owner": str(worker.ledger.root), "plan": plan["id"]})
        assert len(fake.calls) == before
    finally:
        checker.close()
        worker.close()
