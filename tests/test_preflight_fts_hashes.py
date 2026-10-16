"""Source-free integrity and cleanup checks; no production-store access."""
import sqlite3
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError
from newsresearch import preflight_fts_hashes as verifier
from newsresearch.storage import prepare_root


def fixture_db(rows=None, order=None):
    rows = rows or [("a", "Fictional é paragraph"), ("b", "Constructed 界 text"), ("c", "")]
    db = sqlite3.connect(":memory:")
    db.executescript("CREATE TABLE passages(id TEXT PRIMARY KEY,text TEXT NOT NULL);"
        "CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text);")
    db.executemany("INSERT INTO passages VALUES (?,?)", rows)
    db.executemany("INSERT INTO passage_fts VALUES (?,?)", rows if order is None else order)
    db.commit()
    return db


def test_full_unicode_content_order_independence_and_main_connection_unchanged(tmp_path):
    rows = [("a", "Fictional é paragraph"), ("b", "Constructed 界 text"), ("c", "")]
    db = fixture_db(rows, list(reversed(rows)))
    root = tmp_path / "private-scratch"
    try:
        before = (db.total_changes, db.execute("PRAGMA cache_size").fetchone()[0],
            db.execute("PRAGMA journal_mode").fetchone()[0], db.in_transaction)
        result = verifier.verify_hashes(db, root)
        assert result["passages"] == result["fts_rows"] == 3
        assert result["scratch_deleted"] and result["main_connection_pragmas_changed"] is False
        assert not list(root.iterdir())
        assert before == (db.total_changes, db.execute("PRAGMA cache_size").fetchone()[0],
            db.execute("PRAGMA journal_mode").fetchone()[0], db.in_transaction)
    finally:
        db.close()


@pytest.mark.parametrize("corruption", ["duplicate_and_missing", "wrong_id", "wrong_text", "missing"])
def test_complete_projection_mismatch_fails_closed_and_removes_only_scratch(tmp_path, corruption):
    db = fixture_db()
    try:
        if corruption == "duplicate_and_missing":
            db.execute("DELETE FROM passage_fts WHERE id='b'")
            db.execute("INSERT INTO passage_fts VALUES ('a','Fictional é paragraph')")
        elif corruption == "wrong_id":
            db.execute("UPDATE passage_fts SET id='wrong' WHERE id='b'")
        elif corruption == "wrong_text":
            db.execute("UPDATE passage_fts SET text='Constructed 界 texx' WHERE id='b'")
        else:
            db.execute("DELETE FROM passage_fts WHERE id='b'")
        db.commit()
        root = tmp_path / "private-scratch"
        with pytest.raises(AuditError, match="Search index"):
            verifier.verify_hashes(db, root)
        assert not list(root.iterdir())
    finally:
        db.close()


def test_sql_failure_cleans_up_and_preexisting_uuid_collision_is_preserved(tmp_path, monkeypatch):
    root = prepare_root(tmp_path / "private-scratch")
    db = sqlite3.connect(":memory:")
    try:
        with pytest.raises(AuditError, match="scratch storage failed"):
            verifier.verify_hashes(db, root)
        assert not list(root.iterdir())
        monkeypatch.setattr(verifier.uuid, "uuid4", lambda: SimpleNamespace(hex="0" * 32))
        existing = root / ("preflight-fts-" + "0" * 32 + ".sqlite3")
        existing.write_bytes(b"Unrelated generated file must survive a UUID collision")
        if verifier.os.name != "nt":
            existing.chmod(0o600)
        with pytest.raises(AuditError, match="scratch storage failed"):
            verifier.verify_hashes(db, root)
        assert existing.read_bytes() == b"Unrelated generated file must survive a UUID collision"
    finally:
        db.close()
