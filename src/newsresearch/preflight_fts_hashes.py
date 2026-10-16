"""Complete FTS projection verification with a private, compact scratch lookup.

Both tables' complete UTF-8 text bytes are hashed afresh. This is a content
comparison, not a metadata cache. The caller must still verify FTS internals.
Only the temporary scratch connection receives performance pragmas; the main
research connection remains read-only here. No source text enters scratch.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sqlite3
import uuid

from .common import AuditError, Json
from .storage import check_permissions, prepare_root

METHOD = "full-fts-utf8-sha256-scratch-v1"


def _row(identifier: object, text: object) -> tuple[str, bytes]:
    if not isinstance(identifier, str) or not isinstance(text, str):
        raise AuditError("Search index projection contains a non-text identifier or body")
    try:
        return identifier, hashlib.sha256(text.encode("utf-8")).digest()
    except UnicodeError as error:
        raise AuditError("Search index projection contains invalid Unicode") from error


def verify_hashes(db: sqlite3.Connection, scratch_root: Path) -> Json:
    """Stream both complete projections; reject changed, duplicate or missing IDs.

    Scratch uses a 64 MiB SQLite page-cache budget plus individual input rows;
    this is not a hard process-RSS limit. Disk use grows with compact IDs and
    digests, never body bytes. One uncommitted transaction avoids per-row sync.
    """
    root = prepare_root(Path(scratch_root))
    path = root / ("preflight-fts-" + uuid.uuid4().hex + ".sqlite3")
    if path.parent.resolve() != root or path.resolve().parent != root:
        raise AuditError("FTS scratch path escaped its private workspace")
    created = False
    scratch = None
    source_rows = fts_rows = 0
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        created = True
        os.close(descriptor)
        check_permissions(path)
        scratch = sqlite3.connect(path)
        scratch.execute("PRAGMA cache_size=-65536")
        scratch.execute("PRAGMA journal_mode=OFF")
        scratch.execute("BEGIN")
        scratch.execute("CREATE TABLE expected(id TEXT PRIMARY KEY, sha BLOB NOT NULL) WITHOUT ROWID")
        for identifier, text in db.execute("SELECT id,text FROM passages ORDER BY rowid"):
            scratch.execute("INSERT INTO expected VALUES (?,?)", _row(identifier, text))
            source_rows += 1
        for identifier, text in db.execute("SELECT id,text FROM passage_fts ORDER BY rowid"):
            if scratch.execute("DELETE FROM expected WHERE id=? AND sha=?", _row(identifier, text)).rowcount != 1:
                raise AuditError("Search index content differs from passages")
            fts_rows += 1
        if source_rows != fts_rows or scratch.execute("SELECT count(*) FROM expected").fetchone()[0] != 0:
            raise AuditError("Search index coverage differs from passages")
    except (sqlite3.Error, OSError) as error:
        raise AuditError("FTS projection verification or private scratch storage failed") from error
    finally:
        try:
            if scratch is not None:
                scratch.close()
        finally:
            if created:
                # Delete only this invocation's exact file, after closing SQLite.
                # Never enumerate/delete paths or remove a pre-existing collision.
                try:
                    if path.parent.resolve() != root:
                        raise AuditError("FTS scratch cleanup escaped its private workspace")
                    check_permissions(path)
                    path.unlink()
                except OSError as error:
                    raise AuditError("Private FTS verification scratch cleanup failed") from error
    return {"method": METHOD, "rows": source_rows, "passages": source_rows, "fts_rows": fts_rows,
        "full_text_hash": "sha256-over-complete-utf8-bytes", "scratch_cache_mib": 64,
        "scratch_deleted": True, "main_connection_pragmas_changed": False,
        "fts_internal_integrity_check": "Caller still required"}
