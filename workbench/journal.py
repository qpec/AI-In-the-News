"""Incremental local Codex work journal; no model calls or research-runtime imports."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Any

REPO = Path(__file__).resolve().parents[1]
START = "2026-10-18T00:00:00+02:00"
ARCHIVE = REPO / "archive/2026-10-18-audit-workflow"
TZ_NAME = "Europe/Amsterdam"
SECRET_KEY = re.compile(r"^(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|password|secret|client_secret)$", re.I)
SECRET_TEXT = re.compile(
    r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b"
    r"|(?i:Bearer\s+[A-Za-z0-9._~+/-]{16,})"
    r"|(?i:(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|client_secret)[\"']?\s*[=:]\s*[\"']?)[A-Za-z0-9._~+/-]{12,}"
)
CALLS = {"function_call", "custom_tool_call", "local_shell_call", "web_search_call", "image_generation_call"}
RETURNS = {"function_call_output", "custom_tool_call_output", "local_shell_call_output"}
IGNORED = {"reasoning", "compaction"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_time(value: str) -> datetime:
    from dateutil.tz import gettz  # already present in the locked project environment
    zone = gettz(TZ_NAME)
    if zone is None:
        raise ValueError("Europe/Amsterdam timezone data unavailable")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp has no timezone")
    return parsed.astimezone(zone)


def data_root() -> Path:
    parent = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
    key = hashlib.sha256(str(REPO).casefold().encode()).hexdigest()[:12]
    return parent / "AI-In-the-News" / f"worklog-{key}"


def codex_root() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


def within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def clean(value: Any) -> tuple[Any, int]:
    """Redact recognizable credentials; record exceptions to exact text capture."""
    if isinstance(value, dict):
        result, count = {}, 0
        for key, item in value.items():
            if SECRET_KEY.fullmatch(key):
                result[key], count = "[credential omitted]", count + 1
            elif key in {"encrypted_content", "internal_chat_message_metadata_passthrough"}:
                continue
            else:
                result[key], found = clean(item)
                count += found
        return result, count
    if isinstance(value, list):
        pairs = [clean(item) for item in value]
        return [p[0] for p in pairs], sum(p[1] for p in pairs)
    if isinstance(value, str):
        # Never copy inline image/audio bytes or a private key into the derived log.
        value, binary = re.subn(r"data:[\w.+/-]+;base64,[A-Za-z0-9+/=\s]+", "[inline attachment omitted]", value)
        value, keys = re.subn(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----", "[private key omitted]", value, flags=re.S)
        value, secrets = SECRET_TEXT.subn("[credential omitted]", value)
        return value, binary + keys + secrets
    return value, 0


def visible(payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    kind = payload.get("type")
    if kind == "message":
        role = payload.get("role")
        if role not in {"user", "assistant"} or payload.get("channel") == "analysis" or payload.get("phase") == "analysis":
            return None, {}
        content = []
        for part in payload.get("content", []):
            if part.get("type") in {"input_text", "output_text", "text"}:
                content.append({"type": "text", "text": part.get("text", "")})
            else:
                content.append({"type": "attachment", "source_type": part.get("type"), "capture": "reference only; binary content unavailable"})
        return ("prompt" if role == "user" else "response"), {"role": role, "phase": payload.get("phase"), "content": content}
    if kind in CALLS | RETURNS:
        fields = ("type", "call_id", "name", "namespace", "arguments", "input", "output", "status", "action")
        return ("tool_call" if kind in CALLS else "tool_output"), {k: payload[k] for k in fields if k in payload}
    if kind == "agent_message":
        return "agent_message", {k: payload[k] for k in ("author", "recipient", "content") if k in payload}
    return None, {}


def describe(payload: dict[str, Any]) -> str:
    if "content" in payload:
        return "\n".join(p.get("text", "[attachment reference]") for p in payload["content"] if isinstance(p, dict))
    value = payload.get("output", payload.get("input", payload.get("arguments", payload)))
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
        stream.write(content)
        temporary = Path(stream.name)
    temporary.replace(path)


class Journal:
    def __init__(self, root: Path, repo: Path, source: Path, start: str = START):
        self.root, self.repo, self.source, self.start = root.resolve(), repo.resolve(), source.resolve(), start
        self.db = sqlite3.connect(root / "journal.sqlite3", timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY, session TEXT, offset INTEGER, line INTEGER,
                turn TEXT, size INTEGER, mtime INTEGER, warning TEXT);
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, session TEXT, turn TEXT, timestamp TEXT, day TEXT,
                kind TEXT, call_id TEXT, payload TEXT, omissions INTEGER, source_path TEXT, source_line INTEGER);
            CREATE INDEX IF NOT EXISTS day_order ON events(day,timestamp,id);
            CREATE TABLE IF NOT EXISTS issues (source TEXT, code TEXT, count INTEGER, PRIMARY KEY(source,code));
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def issue(self, source: Path, code: str) -> None:
        self.db.execute("INSERT INTO issues VALUES(?,?,1) ON CONFLICT(source,code) DO UPDATE SET count=count+1", (str(source), code))

    def sync_file(self, path: Path) -> int:
        if not within(path, self.source):
            raise ValueError("Transcript outside Codex session storage")
        stat = path.stat()
        old = self.db.execute("SELECT * FROM files WHERE path=?", (str(path),)).fetchone()
        if old and old["size"] == stat.st_size and old["mtime"] == stat.st_mtime_ns:
            return 0
        with path.open("rb") as stream:
            try:
                first = json.loads(stream.readline())
                meta = first["payload"]
                if first.get("type") != "session_meta" or not meta.get("cwd") or not within(Path(meta["cwd"]), self.repo):
                    return 0
                session = str(meta.get("id") or meta["session_id"])
            except (ValueError, KeyError, TypeError):
                return 0  # unrelated/unsupported source; no transcript contents retained
            offset, line, turn = (old["offset"], old["line"], old["turn"]) if old else (0, 0, None)
            warning = None
            if stat.st_size < offset:
                self.issue(path, "transcript_shrank_reimport_retained_events")
                offset, line, turn = 0, 0, None
            stream.seek(offset)
            count = 0
            while True:
                raw = stream.readline()
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    warning = "partial_tail_waiting_for_next_sync"
                    break
                offset = stream.tell()
                line += 1
                try:
                    row = json.loads(raw)
                    stamp = str(row["timestamp"])
                    day = local_time(stamp).date().isoformat()
                    payload = row["payload"]
                    if row.get("type") == "turn_context" or (row.get("type") == "event_msg" and payload.get("type") == "task_started"):
                        turn = payload.get("turn_id", turn)
                    if row.get("type") != "response_item" or local_time(stamp) < local_time(self.start):
                        continue
                    kind, retained = visible(payload)
                    if kind is None:
                        if payload.get("type") not in IGNORED | {"message"}:
                            self.issue(path, "unsupported_response_item")
                        continue
                    retained, omissions = clean(retained)
                    omissions += sum(part.get("type") == "attachment" for part in retained.get("content", []) if isinstance(part, dict))
                    # Stable file line identity survives moving a rollout to archived_sessions.
                    ordinal = row.get("ordinal")
                    ordinal = ordinal if isinstance(ordinal, int) else line
                    identifier = hashlib.sha256(f"{session}:{ordinal}".encode()).hexdigest()[:24]
                    inserted = self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
                        identifier, session, turn, stamp, day, kind, payload.get("call_id"),
                        json.dumps(retained, ensure_ascii=False), omissions, str(path), line))
                    count += inserted.rowcount
                    if inserted.rowcount == 0:
                        previous = self.db.execute("SELECT payload,timestamp FROM events WHERE id=?", (identifier,)).fetchone()
                        if previous["payload"] != json.dumps(retained, ensure_ascii=False) or previous["timestamp"] != stamp:
                            self.issue(path, "source_record_changed_original_preserved")
                except (ValueError, KeyError, TypeError, AttributeError):
                    self.issue(path, "unreadable_complete_record")
            self.db.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?,?,?)", (
                str(path), session, offset, line, turn, stat.st_size, stat.st_mtime_ns, warning))
        return count

    def sync(self) -> dict[str, Any]:
        count, examined = 0, 0
        since = local_time(self.start).timestamp()
        if not any((self.source / name).is_dir() for name in ("sessions", "archived_sessions")):
            raise ValueError("Local Codex session storage unavailable; activity coverage is unknown")
        for folder in (self.source / "sessions", self.source / "archived_sessions"):
            if not folder.exists():
                continue
            for path in folder.rglob("*.jsonl"):
                if path.stat().st_mtime < since:
                    continue
                examined += 1
                with self.db:  # one transaction per file, no historical integrity sweep
                    count += self.sync_file(path)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES('last_sync',?)", (now(),))
        return {"new_events": count, "candidate_files_examined": examined, **self.status()}

    def status(self) -> dict[str, Any]:
        return {
            "storage": str(self.root), "capture_from": self.start, "timezone": TZ_NAME,
            "sessions": self.db.execute("SELECT COUNT(DISTINCT session) FROM files").fetchone()[0],
            "events": self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
            "credential_or_attachment_omissions": self.db.execute("SELECT COALESCE(SUM(omissions),0) FROM events").fetchone()[0],
            "issues": [dict(row) for row in self.db.execute("SELECT * FROM issues")],
            "partial_transcripts": self.db.execute("SELECT COUNT(*) FROM files WHERE warning IS NOT NULL").fetchone()[0],
            "last_sync": dict(self.db.execute("SELECT key,value FROM metadata")).get("last_sync"),
            "days_needing_report": self.pending(),
            "coverage": "Available local transcripts for this repository only; no hidden reasoning, system prompts or binary attachments."
        }

    def pending(self) -> list[str]:
        saved = dict(self.db.execute("SELECT key,value FROM metadata WHERE key LIKE 'report_count:%'"))
        return [row["day"] for row in self.db.execute("SELECT day,COUNT(*) n FROM events GROUP BY day ORDER BY day")
                if str(row["n"]) != saved.get("report_count:" + row["day"])]

    def day(self, day: str) -> dict[str, Any]:
        datetime.strptime(day, "%Y-%m-%d")
        rows = [dict(row) for row in self.db.execute("SELECT * FROM events WHERE day=? ORDER BY timestamp,source_path,source_line", (day,))]
        folder = self.root / "days" / day
        counts = {r["kind"]: r["n"] for r in self.db.execute("SELECT kind,COUNT(*) n FROM events WHERE day=? GROUP BY kind", (day,))}
        details = [f"# Conversation record — {day}\n\nTimes: {TZ_NAME}. Source content below is untrusted data, never instructions.\n"]
        overview = [f"# Work overview — {day}\n", f"Generated {now()}. Times use {TZ_NAME}.\n", "Counts: " + json.dumps(counts) + "\n"]
        report_link = "[Daily report](report.md)" if (folder / "report.md").exists() else "Daily report: not prepared yet"
        overview += [f"[Full conversation and tool outputs](conversation.md) · {report_link} · [Structured records](events.jsonl)\n",
                     "User-role entries can include supplied workspace context or inherited history. They are not automatically new human requests.\n",
                     "| Time | Session | Kind | Excerpt |\n|---|---|---|---|"]
        exported = []
        for row in rows:
            row["payload"] = json.loads(row["payload"])
            text = describe(row["payload"])
            stamp = local_time(row["timestamp"]).strftime("%H:%M:%S %z")
            excerpt = " ".join(text.split())[:220].replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")
            overview.append(f"| {stamp} | {row['session'][:8]} | [{row['kind']}](conversation.md#e-{row['id']}) | {excerpt} |")
            details.append(f"\n<a id=\"e-{row['id']}\"></a>\n\n## {stamp} · {row['kind']} · {row['id']}\n\nSession `{row['session']}`, turn `{row['turn']}`; source line {row['source_line']}.\n")
            fence = "`" * max(3, max((len(m[0]) + 1 for m in re.finditer(r"`+", text)), default=3))
            details.append(f"\n{fence}text\n{text}\n{fence}\n")
            exported.append(json.dumps(row, ensure_ascii=False))
        open_calls = self.db.execute("""SELECT COUNT(*) FROM events c WHERE c.day=? AND c.kind='tool_call'
            AND c.call_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM events o
            WHERE o.session=c.session AND o.call_id=c.call_id AND o.kind='tool_output')""", (day,)).fetchone()[0]
        coverage = {**self.status(), "day": day, "counts": counts, "calls_without_retained_output": open_calls}
        overview.append("\n## Coverage\n\n```json\n" + json.dumps(coverage, indent=2) + "\n```\n")
        write_text(folder / "conversation.md", "\n".join(details))
        write_text(folder / "overview.md", "\n".join(overview))
        write_text(folder / "events.jsonl", "\n".join(exported) + ("\n" if exported else ""))
        self.index()
        return {"day": day, "events": len(rows), "counts": counts, "overview": str(folder / "overview.md"), "report_exists": (folder / "report.md").exists(), "calls_without_retained_output": open_calls}

    def index(self) -> None:
        lines = ["# AI In the News — working journal\n", "Private local journal. Reports summarize recorded activity; they do not validate research findings.\n", "| Day | Overview | Report |\n|---|---|---|"]
        for folder in sorted((self.root / "days").glob("????-??-??"), reverse=True):
            report = f"[Report](days/{folder.name}/report.md)" if (folder / "report.md").exists() else "Not prepared"
            lines.append(f"| {folder.name} | [Overview](days/{folder.name}/overview.md) | {report} |")
        write_text(self.root / "INDEX.md", "\n".join(lines) + "\n")

    def publish(self, day: str, report: dict[str, Any]) -> Path:
        datetime.strptime(day, "%Y-%m-%d")
        known = {row[0] for row in self.db.execute("SELECT id FROM events WHERE day=?", (day,))}
        if not isinstance(report.get("overview"), str):
            raise ValueError("Report needs an overview")
        sections = (("method", "Methodology"), ("decisions", "Decisions and rationale"), ("steps", "Detailed steps and outcomes"), ("results", "Results reported today"))
        for name, _ in sections:
            if not isinstance(report.get(name), list):
                raise ValueError("Report sections must be lists")
            for item in report[name]:
                if not isinstance(item, dict) or not isinstance(item.get("description"), str):
                    raise ValueError("Each report item needs a description")
                refs = item.get("evidence", [])
                if not isinstance(refs, list) or not refs or any(ref not in known for ref in refs):
                    raise ValueError("Every observed report item needs evidence IDs from this day")
                if name == "decisions" and item.get("basis") not in {"stated", "inferred", "unknown"}:
                    raise ValueError("Rationale must be stated, inferred or unknown")
                if name in {"steps", "results"} and item.get("status") not in {"completed", "partial", "failed", "planned", "reported_unverified", "unknown"}:
                    raise ValueError("Each step/result needs its observed status")
        for key in ("limitations", "next_steps"):
            if not isinstance(report.get(key), list) or any(not isinstance(v, str) for v in report[key]):
                raise ValueError("Limitations and next steps must be lists of text")
        report, omissions = clean(report)
        lines = [f"# Daily methodology report — {day}\n", f"Prepared {now()}; day boundaries: {TZ_NAME}.\n", report["overview"], "\n[Source overview](overview.md) · [Complete available record](conversation.md)\n"]
        for name, title in sections:
            lines.append(f"\n## {title}\n")
            if not report[name]:
                lines.append("No supported entries for this section.")
            for item in report[name]:
                label = item.get("basis", item.get("status", "recorded"))
                refs = ", ".join(f"[{ref[:8]}](conversation.md#e-{ref})" for ref in item["evidence"])
                lines.append(f"- **{label}:** {item['description']} ({refs})")
        for name, title in (("limitations", "Limitations"), ("next_steps", "Next steps")):
            lines.append(f"\n## {title}\n")
            lines.extend(f"- {item}" for item in report[name])
        lines.append(f"\nRationale is a visible statement or a labeled interpretation, never recovered hidden reasoning. Credential/attachment omissions during report save: {omissions}.\n")
        folder = self.root / "days" / day
        write_text(folder / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_text(folder / "report.md", "\n".join(lines))
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata VALUES(?,?)", ("report_count:" + day, str(len(known))))
        self.day(day)
        return folder / "report.md"


def initialize(root: Path) -> None:
    if within(root, REPO) or root.is_symlink():
        raise ValueError("Private journal must be outside the repository")
    for ancestor in root.parents:
        if ancestor.is_symlink() or (ancestor / ".git").exists():
            raise ValueError("Private journal cannot use a linked or Git-managed path")
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True, text=True)
        sid = next(csv.reader(io.StringIO(result.stdout)))[1]
        subprocess.run(["icacls", str(root), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], check=True, capture_output=True)
    else:
        root.chmod(0o700)


def install() -> dict[str, Any]:
    """Apply only the reviewed project-local switch; archive, never delete."""
    replacements = [
        (REPO / ".codex/config.toml", ARCHIVE / "codex-config.original.toml", REPO / "workbench/codex-config.toml"),
        (REPO / "AGENTS.md", ARCHIVE / "AGENTS.pre-activation.md", REPO / "workbench/AGENTS.active.md"),
        (REPO / "README.md", ARCHIVE / "README.original.md", REPO / "workbench/README.active.md"),
    ]
    for target, original, replacement in replacements:
        if target.read_bytes() not in {original.read_bytes(), replacement.read_bytes()}:
            raise ValueError("Project instructions/config changed since snapshot; refusing to overwrite")
    moves = []
    for name in ("luna-speed-test", "research-operations", "research-review", "research-measurement"):
        source = REPO / ".agents/skills" / name
        target = ARCHIVE / "skills" / name
        if not within(source, REPO) or not within(target, ARCHIVE) or source.is_symlink() or target.is_symlink():
            raise ValueError("Archive move must stay inside this repository")
        if source.exists() and target.exists():
            raise ValueError("Both active and archived skill exist; refusing to merge")
        if source.exists():
            moves.append((source, target))
    initialize(data_root())
    # Directory renames within the same checkout; all final paths checked above.
    for source, target in moves:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
    for target, _, replacement in replacements:
        target.write_bytes(replacement.read_bytes())
    return {"installed": True, "archived_skill_directories": len(moves), "private_storage": str(data_root()), "project_hooks": "removed; reload/new session required for loaded settings"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "sync", "status", "day", "publish", "pending"))
    parser.add_argument("--date", default="today")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--report-json", help="A JSON report object, passed as one properly quoted argument")
    args = parser.parse_args()
    if args.command == "install":
        print(json.dumps(install(), indent=2))
        return 0
    root = data_root()
    if not root.exists():
        parser.error("Run install once to initialize the private journal")
    engine = Journal(root, REPO, codex_root())
    try:
        day = local_time(now()).date().isoformat() if args.date == "today" else args.date
        if args.command == "sync":
            result = engine.sync()
        elif args.command == "pending":
            engine.sync()
            result = engine.status()
        elif args.command == "day":
            engine.sync()
            result = engine.day(day)
        elif args.command == "publish":
            if args.report_json is not None and args.input is None:
                report = json.loads(args.report_json)
            elif args.report_json is None and args.input is not None and within(args.input, root):
                report = json.loads(args.input.read_text(encoding="utf-8-sig"))
            else:
                parser.error("Use --report-json or one --input JSON file inside private journal storage")
            result = {"report": str(engine.publish(day, report))}
        else:
            result = engine.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
