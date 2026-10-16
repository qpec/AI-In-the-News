"""Complete, bounded-memory verification of the derived passage FTS projection."""
from __future__ import annotations

from itertools import zip_longest
import sqlite3

from .common import AuditError


def _count(db: sqlite3.Connection, sql: str) -> int:
    cursor = db.execute(sql)
    try:
        return int(cursor.fetchone()[0])
    finally:
        cursor.close()


def verify_projection(db: sqlite3.Connection) -> dict[str, int | str | bool]:
    """Compare every ID/text pair; use the full join if valid row order differs.

    The caller must still run the FTS internal integrity check. No verification
    result, permission decision or file metadata is cached by this helper.
    """
    try:
        expected = _count(db, "SELECT COUNT(*) FROM passages")
        actual = _count(db, "SELECT COUNT(*) FROM passage_fts")
        if expected != actual:
            raise AuditError("FTS passage coverage mismatch")
        source = db.execute("SELECT id,text FROM passages ORDER BY rowid")
        aligned, checked = True, 0
        try:
            indexed = db.execute("SELECT id,text FROM passage_fts ORDER BY rowid")
            try:
                for passage, projection in zip_longest(source, indexed):
                    if passage is None or projection is None:
                        raise AuditError("FTS passage coverage changed during verification")
                    if passage[0] != projection[0] or passage[1] != projection[1]:
                        aligned = False
                        break
                    checked += 1
            finally:
                indexed.close()
        finally:
            source.close()
        if aligned:
            if checked != expected:
                raise AuditError("FTS passage coverage changed during verification")
            return {"method": "streaming-row-order", "rows": checked, "fallback": False}
        # Both streaming cursors are closed before these complete fallback checks.
        duplicates = db.execute("SELECT 1 FROM passage_fts GROUP BY id HAVING COUNT(*) != 1 LIMIT 1")
        try:
            if duplicates.fetchone() is not None:
                raise AuditError("FTS contains duplicate passage IDs")
        finally:
            duplicates.close()
        content = db.execute(
            "SELECT 1 FROM passage_fts f LEFT JOIN passages p ON p.id=f.id "
            "WHERE p.id IS NULL OR p.text IS NOT f.text LIMIT 1")
        try:
            if content.fetchone() is not None:
                raise AuditError("FTS passage content mismatch")
        finally:
            content.close()
        return {"method": "complete-content-join", "rows": expected, "fallback": True}
    except sqlite3.DatabaseError as error:
        raise AuditError("FTS projection verification failed") from error
