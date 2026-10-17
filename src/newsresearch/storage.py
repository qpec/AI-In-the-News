from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import uuid
from typing import Any, Callable

from .common import AuditError, Json, canonical, digest, require_no_credentials, utc


@lru_cache(maxsize=1)
def windows_sid() -> str:
    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True, text=True, check=True
    )
    match = re.search(r"S-1-\d+(?:-\d+)+", result.stdout)
    if not match:
        raise AuditError("Cannot establish the Windows storage owner")
    return match.group()


@lru_cache(maxsize=1)
def _windows_security_api() -> tuple[Any, Any, Any]:
    """Reuse API bindings, never an ACL or a permission decision."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_security = advapi.GetNamedSecurityInfoW
    get_security.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    get_security.restype = wintypes.DWORD
    convert = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.c_void_p,
    ]
    convert.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    return get_security, convert, kernel.LocalFree


def windows_sddl(path: Path) -> str:
    get_security, convert, free = _windows_security_api()
    descriptor = ctypes.c_void_p()
    output = wintypes.LPWSTR()
    if get_security(str(path), 1, 5, None, None, None, None, ctypes.byref(descriptor)):
        raise AuditError("Cannot read storage ACL")
    try:
        if not convert(descriptor, 1, 5, ctypes.byref(output), None):
            raise AuditError("Cannot decode storage ACL")
        return output.value or ""
    finally:
        if output:
            free(output)
        free(descriptor)


def check_permissions(path: Path, root: bool = False) -> None:
    if path.is_symlink() or path.is_junction():
        raise AuditError("Protected storage cannot contain symbolic links")
    if os.name == "nt":
        sddl = windows_sddl(path)
        principals = re.findall(r"\(A;[^;]*;[^;]*;[^;]*;[^;]*;([^;)]+)\)", sddl)
        allowed = {windows_sid(), "SY", "BA", "S-1-5-18", "S-1-5-32-544"}
        owner = re.search(r"^O:(.*?)(?=G:|D:|S:|$)", sddl)
        if owner and owner.group(1) in allowed:
            allowed.add("OW")
        if not principals or set(principals) - allowed or (root and "D:P" not in sddl):
            raise AuditError("Protected storage has an unsafe Windows ACL")
    else:
        info = path.stat()
        if info.st_uid != getattr(os, "getuid")() or info.st_mode & 0o077:
            raise AuditError("Protected storage requires owner-only permissions")


def prepare_root(root: Path) -> Path:
    root = root.expanduser().absolute()
    for parent in [root, *root.parents]:
        if parent.is_symlink() or parent.is_junction() or (parent / ".git").exists():
            raise AuditError("Research storage must be outside Git and symbolic-link paths")
    existed = root.exists()
    if existed:
        check_permissions(root, root=True)
    else:
        root.mkdir(parents=True, mode=0o700)
        if os.name == "nt":
            subprocess.run(
                [
                    "icacls",
                    str(root),
                    "/inheritance:r",
                    "/grant:r",
                    f"*{windows_sid()}:(OI)(CI)F",
                    "*S-1-5-18:(OI)(CI)F",
                ],
                check=True,
                capture_output=True,
            )
        else:
            root.chmod(0o700)
        check_permissions(root, root=True)
    return root.resolve()


class WorkspaceLock:
    """Single writer process, held for the lifetime of a research runtime."""

    def __init__(self, path: Path) -> None:
        self.stream = path.open("a+b")
        if os.name != "nt":
            path.chmod(0o600)
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                getattr(fcntl, "flock")(
                    self.stream.fileno(), getattr(fcntl, "LOCK_EX") | getattr(fcntl, "LOCK_NB")
                )
        except OSError as error:
            self.stream.close()
            raise AuditError(
                "Workspace is already open; concurrent research processes are blocked"
            ) from error

    def close(self) -> None:
        if not self.stream.closed:
            if os.name == "nt":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()


class Artifacts:
    def __init__(self, root: Path) -> None:
        self.root = root / "objects"
        self.root.mkdir(mode=0o700, exist_ok=True)
        check_permissions(self.root)

    def put(self, value: Any) -> str:
        require_no_credentials(value)
        return self.put_bytes(canonical(value).encode("utf-8"))

    def put_bytes(self, data: bytes) -> str:
        reference = hashlib.sha256(data).hexdigest()
        target = self.root / reference
        if target.exists():
            if self.read_bytes(reference) != data:
                raise AuditError("Artifact collision or corruption")
            return reference
        try:
            with target.open("xb") as stream:
                if os.name != "nt":
                    target.chmod(0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                fd = os.open(self.root, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        except OSError as error:
            raise AuditError("Required artifact write failed") from error
        return reference

    def read_bytes(self, reference: str) -> bytes:
        if not re.fullmatch(r"[a-f0-9]{64}", reference):
            raise AuditError("Invalid artifact reference")
        path = self.root / reference
        check_permissions(path)
        try:
            content = path.read_bytes()
        except OSError as error:
            raise AuditError("Required artifact is missing") from error
        if hashlib.sha256(content).hexdigest() != reference:
            raise AuditError("Artifact integrity failure")
        return content

    def read(self, reference: str) -> Any:
        return json.loads(self.read_bytes(reference))

    def verified_path(self, reference: str) -> Path:
        """Verify large binary artifacts with bounded memory before a native reader opens them."""
        if not re.fullmatch(r"[a-f0-9]{64}", reference):
            raise AuditError("Invalid artifact reference")
        path = self.root / reference
        try:
            check_permissions(path)
            with path.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise AuditError("Required artifact is missing") from error
        if actual != reference:
            raise AuditError("Artifact integrity failure")
        return path

    def put_file(self, source: Path) -> str:
        """Copy a protected binary file into content-addressed storage without loading it."""
        check_permissions(source)
        staging: Path | None = None
        try:
            with source.open("rb") as incoming, tempfile.NamedTemporaryFile(
                dir=self.root.parent, prefix="artifact-", delete=False
            ) as outgoing:
                staging = Path(outgoing.name)
                if os.name != "nt":
                    staging.chmod(0o600)
                checksum = hashlib.sha256()
                while block := incoming.read(1024 * 1024):
                    checksum.update(block)
                    outgoing.write(block)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            reference = checksum.hexdigest()
            target = self.root / reference
            if target.exists():
                self.verified_path(reference)
            else:
                os.replace(staging, target)
                if os.name != "nt":
                    fd = os.open(self.root, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
            return reference
        except OSError as error:
            raise AuditError("Required artifact write failed") from error
        finally:
            if staging is not None and staging.exists():
                staging.unlink()


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
 seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
 kind TEXT NOT NULL, time TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL,
 event_hash TEXT UNIQUE NOT NULL);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind);
CREATE TABLE IF NOT EXISTS records (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, logical_key TEXT NOT NULL, payload TEXT NOT NULL,
 artifact TEXT NOT NULL, supersedes TEXT, created_event INTEGER NOT NULL REFERENCES events(seq));
CREATE INDEX IF NOT EXISTS records_kind ON records(kind, logical_key);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, source_key TEXT NOT NULL, payload TEXT NOT NULL, raw_ref TEXT NOT NULL,
 raw_index INTEGER NOT NULL, created_event INTEGER NOT NULL REFERENCES events(seq));
CREATE INDEX IF NOT EXISTS sources_key ON sources(source_key);
CREATE TABLE IF NOT EXISTS passages (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), start INTEGER NOT NULL,
 end INTEGER NOT NULL, text TEXT NOT NULL, text_hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS passage_source ON passages(source_id);
CREATE VIRTUAL TABLE IF NOT EXISTS passage_fts USING fts5(id UNINDEXED, text);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, task_key TEXT NOT NULL, batch_id TEXT NOT NULL, number INTEGER NOT NULL,
 request_ref TEXT NOT NULL, response_ref TEXT, status TEXT NOT NULL,
 result_id TEXT, error_type TEXT, created_event INTEGER NOT NULL REFERENCES events(seq));
CREATE INDEX IF NOT EXISTS attempt_task ON attempts(task_key, number);
CREATE TABLE IF NOT EXISTS accepted (
 id TEXT PRIMARY KEY REFERENCES records(id), claim_key TEXT NOT NULL, revision INTEGER NOT NULL,
 dossier_id TEXT NOT NULL, dossier_version TEXT NOT NULL, dataset_version TEXT NOT NULL,
 question_version TEXT NOT NULL, codebook_version TEXT NOT NULL,
 label TEXT NOT NULL, assessment_id TEXT NOT NULL, UNIQUE(claim_key,revision));
"""


class Ledger:
    """SQLite FULL-synchronous, append-only hash journal and immutable projections."""

    def __init__(self, root: Path) -> None:
        self.root = prepare_root(root)
        self.lock = WorkspaceLock(self.root / "workspace.lock")
        self.artifacts = Artifacts(self.root)
        database = self.root / "research.sqlite3"
        new_database = not database.exists()
        self.db = sqlite3.connect(database, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        if os.name != "nt":
            database.chmod(0o600)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        if new_database:
            self.db.executescript(SCHEMA)
            for table in ["events", "records", "sources", "passages", "attempts", "accepted"]:
                for verb in ["UPDATE", "DELETE"]:
                    self.db.execute(
                        f"CREATE TRIGGER immutable_{table}_{verb.lower()} "
                        f"BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT,'append-only'); END"
                    )
            self.db.execute("PRAGMA user_version=1")
        elif self.db.execute("PRAGMA user_version").fetchone()[0] != 1:
            self.db.close()
            self.lock.close()
            raise AuditError("Unsupported or incomplete database schema; automatic repair is forbidden")
        self.unresolved: dict[str, Json] = {}
        self.fail_event: str | None = (
            None  # Deterministic fault injection; never configured by research input.
        )

    def close(self) -> None:
        self.db.close()
        self.lock.close()

    def append(
        self, session: str, kind: str, payload: Json, projection: Callable[[int], None] | None = None
    ) -> int:
        require_no_credentials(payload)
        if self.fail_event == kind:
            raise AuditError(f"Injected audit failure at {kind}")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            last = self.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            number = last["seq"] + 1 if last else 1
            previous = last["event_hash"] if last else "0" * 64
            item = {
                "seq": number,
                "event_id": str(uuid.uuid4()),
                "session_id": session,
                "kind": kind,
                "time": utc(),
                "payload": payload,
                "previous_hash": previous,
            }
            self.db.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?,?,?)",
                (
                    number,
                    item["event_id"],
                    session,
                    kind,
                    item["time"],
                    canonical(payload),
                    previous,
                    digest(item),
                ),
            )
            if projection:
                projection(number)
            self.db.commit()
            return number
        except Exception as error:
            self.db.rollback()
            if isinstance(error, AuditError):
                raise
            raise AuditError("Required journal transaction failed") from error

    def record(
        self,
        session: str,
        kind: str,
        key: str,
        payload: Json,
        supersedes: str | None = None,
        extra: Callable[[int, str], None] | None = None,
    ) -> str:
        if supersedes:
            self.get(supersedes, kind)
        reference = self.artifacts.put(payload)
        identifier = digest({"kind": kind, "key": key, "payload": reference, "supersedes": supersedes})
        if self.db.execute("SELECT 1 FROM records WHERE id=?", (identifier,)).fetchone():
            self.append(session, "record.reused", {"record": identifier})
            return identifier

        def project(event: int) -> None:
            self.db.execute(
                "INSERT INTO records VALUES (?,?,?,?,?,?,?)",
                (identifier, kind, key, canonical(payload), reference, supersedes, event),
            )
            if extra:
                extra(event, identifier)

        self.append(
            session, "record.created", {"record": identifier, "kind": kind, "artifact": reference}, project
        )
        return identifier

    def get(self, identifier: str, kind: str | None = None) -> Json:
        row = self.db.execute("SELECT * FROM records WHERE id=?", (identifier,)).fetchone()
        if not row or (kind and row["kind"] != kind):
            raise AuditError(f"Missing or wrong version type: {kind or 'record'}")
        data = self.artifacts.read(row["artifact"])
        # JSON converts integer object keys to strings. Re-canonicalizing the
        # parsed value can therefore reorder valid keys (2, 10 -> "10", "2").
        # read() fully hashes the artifact bytes; hash the exact projection bytes
        # too, as verify() does, rather than comparing a lossy parsed round trip.
        if hashlib.sha256(row["payload"].encode("utf-8")).hexdigest() != row["artifact"]:
            raise AuditError("Record projection differs from its artifact")
        return dict(data)

    def verify(self) -> Json:
        if any(
            (parent / ".git").exists() or parent.is_symlink() or parent.is_junction()
            for parent in [self.root, *self.root.parents]
        ):
            raise AuditError("Protected storage was placed inside Git or a symbolic-link path")
        check_permissions(self.root, root=True)
        check_permissions(self.artifacts.root)
        for path in self.root.glob("research.sqlite3*"):
            check_permissions(path)
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise AuditError("SQLite integrity check failed")
        expected_triggers = {
            f"immutable_{table}_{verb}"
            for table in ["events", "records", "sources", "passages", "attempts", "accepted"]
            for verb in ["update", "delete"]
        }
        actual = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not expected_triggers <= actual:
            raise AuditError("Append-only protections are missing")
        previous = "0" * 64
        count = 0
        event_payloads: dict[int, Json] = {}
        unresolved: dict[str, Json] = {}
        required_artifacts: set[str] = set()
        artifact_fields = {
            "session.started": ["identity"],
            "operation.intended": ["input"],
            "operation.completed": ["result"],
            "record.created": ["artifact"],
            "sources.imported": ["raw_ref"],
            "model.attempt.intended": ["request", "dispatch"],
            "model.attempt.completed": ["response"],
            "export.write_intended": ["artifact"],
            "preparation.artifact.saved": ["artifact"],
            "embedding.request.prepared": ["request", "wire_body"],
            "embedding.context.saved": ["artifact"],
            "embedding.response.received": ["artifact"],
            "retrieval.artifact.saved": ["artifact"],
            "tagging.artifact.saved": ["artifact"],
            "presentation.artifact.saved": ["artifact"],
            "codex.response.received": ["artifact"],
        }
        for row in self.db.execute("SELECT * FROM events ORDER BY seq"):
            count += 1
            item = dict(row)
            event_hash = item.pop("event_hash")
            item["payload"] = json.loads(item["payload"])
            if item["seq"] != count or item["previous_hash"] != previous or digest(item) != event_hash:
                raise AuditError("Audit journal chain failed verification")
            previous = event_hash
            event_payloads[count] = item["payload"]
            for key in artifact_fields.get(item["kind"], []):
                if item["payload"].get(key):
                    required_artifacts.add(item["payload"][key])
            if item["kind"] == "model.attempt.intended":
                unresolved[item["payload"]["attempt"]] = item["payload"]
            elif item["kind"] in {"model.attempt.completed", "model.attempt.resolved"}:
                unresolved.pop(item["payload"]["attempt"], None)
        self.unresolved = unresolved
        for row in self.db.execute("SELECT * FROM records"):
            # Byte equality follows from the payload digest and the full file hash
            # below. No metadata-only trust or cross-invocation cache is used.
            required_artifacts.add(row["artifact"])
            if hashlib.sha256(row["payload"].encode("utf-8")).hexdigest() != row["artifact"] or row["id"] != digest(
                {
                    "kind": row["kind"],
                    "key": row["logical_key"],
                    "payload": row["artifact"],
                    "supersedes": row["supersedes"],
                }
            ):
                raise AuditError("Immutable record integrity failure")
            if event_payloads.get(row["created_event"], {}).get("record") != row["id"]:
                raise AuditError("Record is not anchored to the journal")
        raw_cache: dict[str, Any] = {}
        # Both cursors use existing indexes; source bodies are parsed once and
        # never repeated in a joined row for each paragraph.
        passages = iter(self.db.execute("SELECT * FROM passages ORDER BY source_id"))
        passage = next(passages, None)
        for row in self.db.execute("SELECT * FROM sources ORDER BY id"):
            if row["raw_ref"] not in raw_cache:
                raw_cache[row["raw_ref"]] = self.artifacts.read(row["raw_ref"])
            original = raw_cache[row["raw_ref"]][row["raw_index"]]
            source_payload = canonical(original)
            if hashlib.sha256(source_payload.encode("utf-8")).hexdigest() != row["id"]:
                raise AuditError("Source version integrity failure")
            if (
                source_payload != row["payload"]
                or event_payloads.get(row["created_event"], {}).get("raw_ref") != row["raw_ref"]
            ):
                raise AuditError("Source differs from its journal-anchored raw version")
            if original.get("original_artifact"):
                required_artifacts.add(original["original_artifact"])
            expected_passages: set[str] = set()
            for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", original["body"]):
                expected_passages.add(
                    digest(
                        {
                            "source": row["id"],
                            "start": match.start(),
                            "end": match.end(),
                            "sha256": hashlib.sha256(match.group().encode()).hexdigest(),
                        }
                    )
                )
            if passage is not None and passage["source_id"] < row["id"]:
                raise AuditError("Passage references a missing source")
            while passage is not None and passage["source_id"] == row["id"]:
                if (
                    original["body"][passage["start"] : passage["end"]] != passage["text"]
                    or hashlib.sha256(passage["text"].encode()).hexdigest() != passage["text_hash"]
                ):
                    raise AuditError("Passage evidence integrity failure")
                if passage["id"] not in expected_passages:
                    raise AuditError("Passage identifier or source segmentation differs")
                expected_passages.remove(passage["id"])
                passage = next(passages, None)
            if expected_passages:
                raise AuditError("Source passage coverage is incomplete")
        if passage is not None:
            raise AuditError("Passage references a missing source")
        from .preflight_fts import verify_projection

        try:
            verify_projection(self.db)
        except AuditError as error:
            raise AuditError("Search index coverage or content differs from passages") from error
        self.db.execute("INSERT INTO passage_fts(passage_fts) VALUES('integrity-check')")
        for row in self.db.execute("SELECT a.*,r.payload FROM accepted a JOIN records r ON r.id=a.id"):
            value = json.loads(row["payload"])
            if any(
                row[column] != value[key]
                for column, key in [
                    ("claim_key", "claim_key"),
                    ("revision", "revision"),
                    ("dossier_id", "dossier_id"),
                    ("label", "label"),
                    ("assessment_id", "assessment"),
                ]
            ):
                raise AuditError("Acceptance projection differs from its immutable record")
        for row in self.db.execute("SELECT * FROM attempts"):
            anchor = event_payloads.get(row["created_event"], {})
            if (
                anchor.get("attempt") != row["id"]
                or anchor.get("status") != row["status"]
                or anchor.get("assessment") != row["result_id"]
            ):
                raise AuditError("Model attempt projection differs from the journal")
        artifact_names = {path.name for path in self.artifacts.root.iterdir()}
        if required_artifacts - artifact_names:
            raise AuditError("A journal-referenced artifact is missing")
        # Recheck shared raw imports too: they were parsed earlier, and the final
        # full hash/ACL sweep must still detect changes made during verification.
        for reference in artifact_names:
            self.artifacts.verified_path(reference)
        return {
            "events": count,
            "head_hash": previous,
            "status": "verified",
            "unresolved_model_attempts": list(unresolved),
        }
