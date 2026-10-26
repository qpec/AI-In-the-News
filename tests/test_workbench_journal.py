"""Synthetic checks for private, incremental conversation capture and reporting."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

SPEC = importlib.util.spec_from_file_location("workbench_journal", Path(__file__).parents[1] / "workbench/journal.py")
assert SPEC and SPEC.loader
j = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(j)


def row(number, kind, payload, stamp="2026-10-18T12:00:00Z"):
    return json.dumps({"ordinal": number, "timestamp": stamp, "type": kind, "payload": payload}) + "\n"


@pytest.fixture
def setup(tmp_path):
    repo, source, private = [tmp_path / name for name in ("repo", "codex", "private")]
    for path in (repo, source / "sessions", private):
        path.mkdir(parents=True)
    engine = j.Journal(private, repo, source)
    path = source / "sessions/rollout.jsonl"
    path.write_text(row(0, "session_meta", {"id": "session-a", "cwd": str(repo)}), encoding="utf-8")
    yield engine, path
    engine.close()


def append(path, *rows):
    with path.open("a", encoding="utf-8") as stream:
        stream.write("".join(rows))


def test_incremental_capture_dedup_scope_and_private_reasoning(setup):
    engine, path = setup
    append(path,
           row(1, "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
           row(2, "response_item", {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Check a batch"}]}),
           row(3, "response_item", {"type": "reasoning", "summary": ["private thought"], "encrypted_content": "secret"}),
           row(4, "response_item", {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "private instructions"}]}),
           row(5, "response_item", {"type": "function_call", "name": "check", "call_id": "call-1", "arguments": "{}"}),
           row(6, "response_item", {"type": "function_call_output", "call_id": "call-1", "output": "complete\nline two"}),
           row(7, "response_item", {"type": "message", "role": "assistant", "phase": "final_answer", "content": [{"type": "output_text", "text": "Done"}]}))
    other = path.with_name("unrelated.jsonl")
    other.write_text(row(0, "session_meta", {"id": "other", "cwd": str(engine.repo.parent / "other")}) + row(1, "response_item", {"type": "message", "role": "user", "content": [{"type": "text", "text": "unrelated"}]}))
    assert engine.sync()["new_events"] == 4
    assert engine.sync()["new_events"] == 0
    result = engine.day("2026-10-18")
    assert result["calls_without_retained_output"] == 0
    captured = (engine.root / "days/2026-10-18/events.jsonl").read_text(encoding="utf-8")
    assert "private thought" not in captured and "private instructions" not in captured and "unrelated" not in captured
    assert "line two" in captured and "turn-1" in captured
    archive = engine.source / "archived_sessions"
    archive.mkdir()
    shutil.move(path, archive / path.name)
    assert engine.sync()["new_events"] == 0
    assert engine.status()["sessions"] == 1


def test_partial_tail_secret_omissions_and_missing_output(setup):
    engine, path = setup
    fake = "sk-" + "a" * 25
    complete = row(1, "response_item", {"type": "custom_tool_call", "call_id": "pending", "input": "api_key='abcdefghijklmnop'"})
    with path.open("ab") as stream:
        stream.write(complete[:60].encode())
    assert engine.sync()["partial_transcripts"] == 1
    with path.open("ab") as stream:
        stream.write(complete[60:].encode())
    append(path, row(2, "response_item", {"type": "function_call_output", "call_id": "other", "output": {"api_key": fake, "text": fake, "count": 12}}))
    assert engine.sync()["new_events"] == 2
    assert engine.day("2026-10-18")["calls_without_retained_output"] == 1
    rows = engine.db.execute("SELECT payload,omissions FROM events").fetchall()
    assert fake not in str([dict(x) for x in rows])
    assert sum(x["omissions"] for x in rows) >= 3
    assert engine.status()["partial_transcripts"] == 0


def test_malformed_unknown_and_shrunk_transcript_are_visible(setup):
    engine, path = setup
    append(path, "not-json\n", row(1, "response_item", {"type": "future_output_format"}), row(2, "response_item", {"type": "message", "role": "user", "content": [{"type": "text", "text": "original"}]}))
    engine.sync()
    path.write_text(row(0, "session_meta", {"id": "session-a", "cwd": str(engine.repo)}) + row(2, "response_item", {"type": "message", "role": "user", "content": [{"type": "text", "text": "changed"}]}))
    engine.sync()
    codes = {x["code"] for x in engine.status()["issues"]}
    assert {"unreadable_complete_record", "unsupported_response_item", "transcript_shrank_reimport_retained_events", "source_record_changed_original_preserved"} <= codes
    assert "original" in engine.db.execute("SELECT payload FROM events").fetchone()[0]


def test_local_day_dst_and_capture_boundary(setup):
    engine, path = setup
    for ordinal, stamp in enumerate(("2026-10-17T21:59:59Z", "2026-10-17T22:00:00Z", "2026-10-18T22:00:00Z"), 1):
        append(path, row(ordinal, "response_item", {"type": "message", "role": "user", "content": [{"type": "text", "text": stamp}]}, stamp))
    assert engine.sync()["new_events"] == 2
    assert engine.day("2026-10-18")["events"] == 1
    assert engine.day("2026-10-19")["events"] == 1
    assert j.local_time("2026-10-25T00:30:00Z").utcoffset().total_seconds() == 7200
    assert j.local_time("2026-10-25T01:30:00Z").utcoffset().total_seconds() == 3600


def test_reports_require_evidence_and_labeled_rationale_and_catch_up(setup):
    engine, path = setup
    append(path, row(1, "response_item", {"type": "message", "role": "user", "content": [{"type": "text", "text": "Keep it lean"}]}))
    engine.sync()
    engine.day("2026-10-18")
    identifier = engine.db.execute("SELECT id FROM events").fetchone()[0]
    report = {"overview": "Administrative setup", "method": [{"description": "Incremental capture", "evidence": [identifier]}],
              "decisions": [{"description": "Keep the setup small", "basis": "stated", "evidence": [identifier]}],
              "steps": [], "results": [], "limitations": ["No research run"], "next_steps": []}
    assert engine.pending() == ["2026-10-18"]
    report_path = engine.publish("2026-10-18", report)
    assert identifier in report_path.read_text(encoding="utf-8")
    assert engine.pending() == []
    report["decisions"][0]["basis"] = "private_chain_of_thought"
    with pytest.raises(ValueError, match="Rationale"):
        engine.publish("2026-10-18", report)
    report["decisions"][0]["basis"] = "inferred"
    report["decisions"][0]["evidence"] = ["invented"]
    with pytest.raises(ValueError, match="evidence"):
        engine.publish("2026-10-18", report)
    append(path, row(2, "response_item", {"type": "message", "role": "assistant", "content": [{"type": "text", "text": "Late response"}]}))
    engine.sync()
    assert engine.pending() == ["2026-10-18"]


def test_install_refuses_changed_config_before_moving_anything(tmp_path, monkeypatch):
    repo, archive = tmp_path / "repo", tmp_path / "repo/archive"
    (repo / ".codex").mkdir(parents=True)
    (repo / "workbench").mkdir()
    archive.mkdir()
    (repo / ".codex/config.toml").write_text("changed")
    (archive / "codex-config.original.toml").write_text("original")
    (repo / "workbench/codex-config.toml").write_text("replacement")
    monkeypatch.setattr(j, "REPO", repo)
    monkeypatch.setattr(j, "ARCHIVE", archive)
    with pytest.raises(ValueError, match="changed since snapshot"):
        j.install()
    assert (repo / ".codex/config.toml").read_text() == "changed"


def test_no_activity_is_explicit(setup):
    engine, _ = setup
    engine.sync()
    assert engine.day("2026-10-18")["events"] == 0
    assert engine.pending() == []
    assert engine.status()["last_sync"] is not None
    assert datetime.fromisoformat(engine.status()["last_sync"]).tzinfo == timezone.utc


def test_install_preserves_archive_and_is_idempotent(tmp_path, monkeypatch):
    repo, archive = tmp_path / "repo", tmp_path / "repo/archive"
    (repo / ".codex").mkdir(parents=True)
    (repo / "workbench").mkdir()
    archive.mkdir()
    entries = ((".codex/config.toml", "codex-config.original.toml", "codex-config.toml"),
               ("AGENTS.md", "AGENTS.pre-activation.md", "AGENTS.active.md"),
               ("README.md", "README.original.md", "README.active.md"))
    for target, snapshot, candidate in entries:
        (repo / target).write_text("old:" + target)
        (archive / snapshot).write_text("old:" + target)
        (repo / "workbench" / candidate).write_text("new:" + target)
    for name in ("luna-speed-test", "research-operations", "research-review", "research-measurement"):
        directory = repo / ".agents/skills" / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text("preserve:" + name)
    monkeypatch.setattr(j, "REPO", repo)
    monkeypatch.setattr(j, "ARCHIVE", archive)
    monkeypatch.setattr(j, "initialize", lambda root: None)
    assert j.install()["archived_skill_directories"] == 4
    assert j.install()["archived_skill_directories"] == 0
    for target, snapshot, _ in entries:
        assert (repo / target).read_text() == "new:" + target
        assert (archive / snapshot).read_text() == "old:" + target
    assert (archive / "skills/research-operations/SKILL.md").read_text() == "preserve:research-operations"
    assert not (repo / ".agents/skills/research-operations").exists()


def test_unavailable_session_store_is_not_zero_activity(setup):
    engine, path = setup
    path.unlink()
    path.parent.rmdir()
    with pytest.raises(ValueError, match="coverage is unknown"):
        engine.sync()
