"""Source-free FTS coverage checks, including the legitimate reorder fallback."""
import sqlite3

import pytest

from newsresearch.common import AuditError
from newsresearch.preflight_fts import verify_projection


def database(projection):
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE passages(id TEXT PRIMARY KEY,text TEXT NOT NULL);
        CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text);
    """)
    db.executemany("INSERT INTO passages VALUES (?,?)", [("a", "First constructed paragraph."),
        ("b", "Tweede verzonnen alinea met café.")])
    db.executemany("INSERT INTO passage_fts(id,text) VALUES (?,?)", projection)
    return db


def test_empty_projection_and_complete_streaming_match():
    db = database([("a", "First constructed paragraph."), ("b", "Tweede verzonnen alinea met café.")])
    try:
        assert verify_projection(db) == {"method": "streaming-row-order", "rows": 2, "fallback": False}
        db.execute("DELETE FROM passage_fts")
        db.execute("DELETE FROM passages")
        assert verify_projection(db) == {"method": "streaming-row-order", "rows": 0, "fallback": False}
    finally:
        db.close()


@pytest.mark.parametrize("projection,error", [
    ([("a", "First constructed paragraph.")], "coverage mismatch"),
    ([("a", "First constructed paragraph."), ("a", "First constructed paragraph.")], "duplicate passage IDs"),
    ([("a", "Changed constructed paragraph."), ("b", "Tweede verzonnen alinea met café.")], "content mismatch"),
    ([("a", "First constructed paragraph."), ("missing", "Tweede verzonnen alinea met café.")], "content mismatch"),
    ([("a", None), ("b", "Tweede verzonnen alinea met café.")], "content mismatch"),
])
def test_missing_duplicate_changed_and_unknown_projection_rows_fail(projection, error):
    db = database(projection)
    try:
        with pytest.raises(AuditError, match=error):
            verify_projection(db)
    finally:
        db.close()


def test_reordered_valid_projection_uses_complete_fallback_after_closing_streams():
    db = database([("b", "Tweede verzonnen alinea met café."), ("a", "First constructed paragraph.")])
    streams = []

    class Cursor:
        def __init__(self, value):
            self.value, self.closed = value, False

        def __iter__(self):
            return iter(self.value)

        def close(self):
            self.closed = True
            self.value.close()

    class Connection:
        def execute(self, sql):
            if "GROUP BY" in sql or "LEFT JOIN" in sql:
                assert len(streams) == 2 and all(cursor.closed for cursor in streams)
            value = db.execute(sql)
            if "ORDER BY rowid" in sql:
                wrapped = Cursor(value)
                streams.append(wrapped)
                return wrapped
            return value

    try:
        assert verify_projection(Connection()) == {"method": "complete-content-join", "rows": 2, "fallback": True}
    finally:
        db.close()
