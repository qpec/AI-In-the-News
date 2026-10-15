"""Source-free corruption regressions for every complete preflight verification.

All data are synthetic Research.execute fixtures. Direct SQL/file changes below
deliberately simulate damaged protected storage; they are never research writes.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

import pytest

from newsresearch.common import AuditError, canonical, digest, utc
from newsresearch.demo import baseline, source
from newsresearch.runtime import Research


def corrupt_projection(
    engine: Research, table: str, statement: str, parameters: tuple[Any, ...], *, verb: str = "update"
) -> None:
    """Restore the protection so failure cannot merely mean a missing trigger."""
    assert table in {"records", "sources", "passages", "events", "attempts", "accepted"}
    assert verb in {"update", "delete"}
    db = engine.ledger.db
    name = f"immutable_{table}_{verb}"
    trigger = db.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
    assert trigger is not None
    db.execute(f"DROP TRIGGER {name}")
    try:
        db.execute(statement, parameters)
    finally:
        db.execute(trigger[0])


@pytest.mark.parametrize("damage", ["payload", "identifier", "anchor"])
def test_record_integrity_and_journal_anchor_survive_optimization(prepared: Any, damage: str) -> None:
    engine, versions, _ = prepared
    identifier = versions["protocol"]
    assert engine.ledger.verify()["status"] == "verified"
    if damage == "payload":
        statement, value = "UPDATE records SET payload=? WHERE id=?", canonical({"changed": True})
    elif damage == "identifier":
        statement, value = "UPDATE records SET id=? WHERE id=?", "0" * 64
    else:
        statement, value = "UPDATE records SET created_event=? WHERE id=?", 1
    corrupt_projection(engine, "records", statement, (value, identifier))
    with pytest.raises(AuditError, match="record|Record"):
        engine.ledger.verify()


@pytest.mark.parametrize("damage", ["payload_hash", "raw_index", "anchor"])
def test_source_version_raw_correspondence_and_anchor(prepared: Any, damage: str) -> None:
    engine, _, _ = prepared
    row = engine.ledger.db.execute("SELECT * FROM sources ORDER BY raw_index LIMIT 1").fetchone()
    if damage == "payload_hash":
        value = json.loads(row["payload"])
        value["body"] += "\n\nUnrecorded synthetic text."
        statement, replacement = "UPDATE sources SET payload=? WHERE id=?", canonical(value)
    elif damage == "raw_index":
        statement, replacement = "UPDATE sources SET raw_index=? WHERE id=?", row["raw_index"] + 1
    else:
        statement, replacement = "UPDATE sources SET created_event=? WHERE id=?", 1
    corrupt_projection(engine, "sources", statement, (replacement, row["id"]))
    with pytest.raises(AuditError, match="Source"):
        engine.ledger.verify()


@pytest.mark.parametrize("damage", ["text", "hash", "identifier", "start", "end", "source", "coverage"])
def test_passage_evidence_hash_identity_offsets_and_coverage(prepared: Any, damage: str) -> None:
    engine, _, _ = prepared
    row = engine.ledger.db.execute("SELECT * FROM passages ORDER BY source_id,start LIMIT 1").fetchone()
    if damage == "coverage":
        corrupt_projection(engine, "passages", "DELETE FROM passages WHERE id=?", (row["id"],), verb="delete")
    else:
        changes = {
            "text": ("text", "A changed synthetic quotation."),
            "hash": ("text_hash", "0" * 64),
            "identifier": ("id", "0" * 64),
            "start": ("start", row["start"] + 1),
            "end": ("end", row["end"] - 1),
            "source": (
                "source_id",
                engine.ledger.db.execute("SELECT id FROM sources WHERE id!=? LIMIT 1", (row["source_id"],)).fetchone()[0],
            ),
        }
        column, value = changes[damage]
        corrupt_projection(engine, "passages", f"UPDATE passages SET {column}=? WHERE id=?", (value, row["id"]))
    with pytest.raises(AuditError, match="Passage|passage"):
        engine.ledger.verify()


def test_multiple_sources_empty_body_unicode_and_repeated_paragraphs_are_valid(engine: Research) -> None:
    versions = baseline(engine, "test:preflight")
    data = engine.execute(
        "ingest",
        {
            "articles": [
                source("last-key", "First paragraph.\nA wrapped line.\n\nRepeated.\n\nRepeated."),
                source("empty-key", ""),
                source("unicode-key", "Unicode café and a newspaper 📰."),
                source("first-key", "\n\nLeading paragraph.\n\nTrailing paragraph.\n"),
            ],
            "retrieval": {"source": "synthetic integrity fixtures", "retrieved_at": utc(), "parameters": {}},
        },
        objective="Verify source and passage coverage in synthetic mixed input",
        actor="test:preflight",
        versions=versions,
    )
    assert len(data["sources"]) == 4
    assert engine.ledger.db.execute("SELECT count(*) FROM passages").fetchone()[0] == 6
    assert engine.ledger.verify()["status"] == "verified"
    assert engine.ledger.verify()["status"] == "verified"
    assert engine.gateway.provider.calls == 0


@pytest.mark.parametrize("position", ["below", "between", "above"])
def test_orphan_passage_at_every_source_cursor_boundary(prepared: Any, position: str) -> None:
    engine, _, _ = prepared
    db = engine.ledger.db
    source_ids = [row[0] for row in db.execute("SELECT id FROM sources ORDER BY id")]
    if position == "below":
        orphan_source = "0" * 64
        assert orphan_source < source_ids[0]
    elif position == "above":
        orphan_source = "f" * 64
        assert orphan_source > source_ids[-1]
    else:
        orphan_source = f"{(int(source_ids[0], 16) + int(source_ids[1], 16)) // 2:064x}"
        assert source_ids[0] < orphan_source < source_ids[1]
    assert orphan_source not in source_ids
    text = "Synthetic orphan passage with no corresponding source."
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    identifier = digest({"source": orphan_source, "start": 0, "end": len(text), "sha256": text_hash})
    original_count = db.execute("SELECT count(*) FROM passages").fetchone()[0]
    db.execute("PRAGMA foreign_keys=OFF")
    try:
        db.execute("INSERT INTO passages VALUES (?,?,?,?,?,?)", (identifier, orphan_source, 0, len(text), text, text_hash))
        db.execute("INSERT INTO passage_fts VALUES (?,?)", (identifier, text))
    finally:
        db.execute("PRAGMA foreign_keys=ON")
    assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM passages").fetchone()[0] == original_count + 1
    # All real sources retain complete passage coverage; the FTS projection also
    # matches. Failure must identify the extra orphan at the merge boundary.
    with pytest.raises(AuditError, match="Passage references a missing source"):
        engine.ledger.verify()


def test_valid_json_change_to_journal_payload_breaks_hash_chain(prepared: Any) -> None:
    engine, _, _ = prepared
    assert engine.ledger.verify()["status"] == "verified"
    corrupt_projection(engine, "events", "UPDATE events SET payload=? WHERE seq=?", (canonical({"changed": True}), 1))
    with pytest.raises(AuditError, match="journal chain"):
        engine.ledger.verify()


@pytest.mark.parametrize("damage", ["missing", "text", "identifier"])
def test_fts_projection_coverage_and_content(prepared: Any, damage: str) -> None:
    engine, _, _ = prepared
    row = engine.ledger.db.execute("SELECT rowid,id,text FROM passage_fts LIMIT 1").fetchone()
    if damage == "missing":
        engine.ledger.db.execute("DELETE FROM passage_fts WHERE rowid=?", (row["rowid"],))
    elif damage == "text":
        engine.ledger.db.execute("UPDATE passage_fts SET text=? WHERE rowid=?", ("Corrupted index text.", row["rowid"]))
    else:
        engine.ledger.db.execute("UPDATE passage_fts SET id=? WHERE rowid=?", ("0" * 64, row["rowid"]))
    with pytest.raises(AuditError, match="Search index"):
        engine.ledger.verify()


def test_fts_internal_corruption_cannot_pass_verification(prepared: Any) -> None:
    engine, _, _ = prepared
    # Damage an actual FTS index block while leaving the content projection alone.
    row = engine.ledger.db.execute("SELECT id FROM passage_fts_data WHERE id>10 LIMIT 1").fetchone()
    assert row is not None
    engine.ledger.db.execute("UPDATE passage_fts_data SET block=? WHERE id=?", (b"\x00", row[0]))
    with pytest.raises((AuditError, sqlite3.DatabaseError)):
        engine.ledger.verify()


def test_missing_journal_required_artifact_is_detected(prepared: Any) -> None:
    engine, _, _ = prepared
    row = engine.ledger.db.execute("SELECT payload FROM events WHERE kind='session.started' LIMIT 1").fetchone()
    reference = json.loads(row[0])["identity"]
    (engine.ledger.artifacts.root / reference).unlink()
    with pytest.raises(AuditError, match="missing"):
        engine.ledger.verify()


@pytest.mark.parametrize("damage", ["corrupt", "invalid_name"])
def test_unreferenced_artifacts_still_receive_full_checks(engine: Research, damage: str) -> None:
    engine.execute("status", objective="Initialize synthetic integrity fixture", actor="test:preflight")
    reference = engine.ledger.artifacts.put_bytes(b"unreferenced synthetic artifact")
    assert engine.ledger.verify()["status"] == "verified"
    path = engine.ledger.artifacts.root / reference
    if damage == "corrupt":
        path.write_bytes(b"changed detached artifact")
    else:
        path.rename(path.with_name("not-a-content-address"))
    with pytest.raises(AuditError, match="integrity|reference"):
        engine.ledger.verify()


def test_every_invocation_rechecks_even_same_size_same_mtime_artifacts(prepared: Any) -> None:
    engine, versions, run = prepared
    reference = engine.ledger.db.execute("SELECT artifact FROM records WHERE id=?", (versions["protocol"],)).fetchone()[0]
    path = engine.ledger.artifacts.root / reference
    original = path.read_bytes()
    before = path.stat()
    assert engine.ledger.verify()["status"] == "verified"
    replacement = (b"X" if original[:1] != b"X" else b"Y") + original[1:]
    assert len(replacement) == len(original)
    path.write_bytes(replacement)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    with pytest.raises(AuditError, match="integrity"):
        engine.ledger.verify()
    with pytest.raises(AuditError, match="integrity"):
        run("search", {"query": "outage"})
    assert engine.gateway.provider.calls == 0


def test_artifact_link_is_rejected(engine: Research, tmp_path: Path) -> None:
    target = tmp_path / "synthetic-outside-object"
    content = b"synthetic linked artifact"
    target.write_bytes(content)
    target.chmod(0o600)
    link = engine.ledger.artifacts.root / hashlib.sha256(content).hexdigest()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Creating symbolic links is unavailable for this test account")
    with pytest.raises(AuditError, match="symbolic"):
        engine.ledger.verify()


def test_unsafe_artifact_permissions_are_rejected(engine: Research) -> None:
    reference = engine.ledger.artifacts.put_bytes(b"synthetic permission fixture")
    path = engine.ledger.artifacts.root / reference
    if os.name == "nt":
        subprocess.run(["icacls", str(path), "/grant", "*S-1-1-0:R"], check=True, capture_output=True)
    else:
        path.chmod(0o644)
    with pytest.raises(AuditError, match="unsafe|owner-only"):
        engine.ledger.verify()


def test_repeated_verification_preserves_unresolved_and_explicit_resolution(prepared: Any) -> None:
    engine, _, run = prepared
    request = engine.ledger.artifacts.put({"synthetic": True, "purpose": "unknown outcome recovery test"})
    attempt = "synthetic-uncompleted-attempt"
    engine.ledger.append(
        "synthetic-interrupted-session",
        "model.attempt.intended",
        {"attempt": attempt, "request": request, "task_key": "synthetic-interrupted-task", "number": 1},
    )
    for _ in range(2):
        assert engine.ledger.verify()["unresolved_model_attempts"] == [attempt]
        assert attempt in engine.ledger.unresolved
    status = run("status")
    assert status["journal"]["unresolved_model_attempts"] == [attempt]
    resolved = run("resolve_attempt", {"attempt": attempt, "reason": "Abandon interrupted synthetic attempt; outcome unknown"})
    assert resolved == {"resolved": attempt, "outcome": "unknown"}
    for _ in range(2):
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
        assert engine.ledger.unresolved == {}
    assert engine.gateway.provider.calls == 0
