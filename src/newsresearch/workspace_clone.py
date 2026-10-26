"""Audited online workspace snapshots; never resume inherited model work."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
from typing import TYPE_CHECKING

from .common import AuditError, Context, Json, ResearchError, require_active, utc
from .storage import check_permissions, prepare_root

if TYPE_CHECKING:
    from .runtime import Research


def clone_workspace(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    source = Path(data["source"]).absolute()
    destination = Path(data["destination"]).absolute()
    # Keep maintenance audit, source and destination disjoint. Never overwrite.
    roots = [source, destination, engine.ledger.root]
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise ResearchError("Clone roots must be disjoint")
    if destination.exists():
        raise ResearchError("Clone destination must not already exist")
    for parent in (source, *source.parents):
        if parent.is_symlink() or parent.is_junction() or (parent / ".git").exists():
            raise AuditError("Clone source must be protected storage outside Git")
    check_permissions(source, root=True)
    check_permissions(source / "objects")
    check_permissions(source / "research.sqlite3")
    method = engine._version(session, context, {
        "kind": "protocol", "key": "online-workspace-clone-v1",
        "content": {"method": "SQLite online backup followed by immutable object copy and full runtime preflight",
                    "limits": "Independent exploratory branch; inherited inference runs and approvals must not be resumed. Original writer remains untouched."},
    })["id"]
    engine.ledger.append(session, "workspace.clone.intended", {
        "source": str(source), "destination": str(destination), "protocol": method,
        "inherited_model_execution_authorized": False,
    })
    prepare_root(destination)
    started = utc()
    database = destination / "research.sqlite3"
    # SQLite supplies a transactionally consistent database even with an active
    # WAL writer. Artifacts are immutable and durably written before references.
    original = sqlite3.connect((source / "research.sqlite3").as_uri() + "?mode=ro", uri=True)
    copied = sqlite3.connect(database)
    try:
        original.backup(copied, pages=4096)
        head = copied.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    finally:
        copied.close()
        original.close()
    if os.name != "nt":
        database.chmod(0o600)
    with database.open("r+b") as stream:
        os.fsync(stream.fileno())
    objects = destination / "objects"
    objects.mkdir(mode=0o700)
    files, size = 0, 0
    for item in (source / "objects").iterdir():
        check_permissions(item)
        if not item.is_file() or len(item.name) != 64 or any(c not in "0123456789abcdef" for c in item.name):
            raise AuditError("Unexpected source artifact")
        target = objects / item.name
        with item.open("rb") as incoming, target.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if os.name != "nt":
            target.chmod(0o600)
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != item.name:
                raise AuditError("Cloned artifact hash mismatch")
        files += 1
        size += target.stat().st_size
    result = {
        "source": str(source), "destination": str(destination), "protocol": method,
        "snapshot_started_at": started, "copied_at": utc(),
        "parent_head_seq": head[0] if head else 0,
        "parent_head_hash": head[1] if head else "0" * 64,
        "artifacts_copied": files, "artifact_bytes": size,
        "maintenance_workspace": str(engine.ledger.root),
        "inherited_model_execution_authorized": False,
    }
    # Opening the copy performs no source operation. execute() checks the entire
    # copied history, references, ACLs, source versions, passages and index.
    from .runtime import Research

    fork = Research(destination, project=engine.project)
    try:
        lineage = fork.execute("version", {
            "kind": "note", "key": "workspace-clone-lineage", "content": result,
            "branch": "organizational-decisions-exploration",
        }, objective="Verify the online snapshot and preserve its independent branch lineage", actor=context.actor)
        result["lineage_note"] = lineage["id"]
        result["verified"] = True
    finally:
        fork.close()
    identifier = engine.ledger.record(session, "workspace_clone", str(destination), result)
    return {"id": identifier, **result}
