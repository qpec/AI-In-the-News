import hashlib
import io
import json
from pathlib import Path

import pytest

from newsresearch import hooks
from newsresearch.common import AuditError


BUSY = "Workspace is already open; concurrent research processes are blocked"


class RecordingEngine:
    def __init__(self):
        self.records = []
        self.closed = False

    def execute(self, operation, payload, **context):
        self.records.append((operation, payload, context))

    def close(self):
        self.closed = True


def install_clock(monkeypatch):
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(hooks.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(hooks.time, "sleep", sleep)
    return now, sleeps


def assert_denied(result):
    assert result
    assert "deny" in json.dumps(result)


def test_hook_waits_for_busy_workspace_then_records(monkeypatch, tmp_path):
    engine = RecordingEngine()
    attempts = []
    now, sleeps = install_clock(monkeypatch)

    def open_runtime(workspace):
        attempts.append(workspace)
        if len(attempts) == 1:
            raise AuditError(BUSY)
        return engine

    monkeypatch.setattr(hooks, "Research", open_runtime)
    result = hooks.observe({"hook_event_name": "PreToolUse"}, tmp_path)

    assert result == {}
    assert attempts == [tmp_path, tmp_path]
    assert sleeps == [0.25]
    assert now[0] == 0.25
    assert len(engine.records) == 1
    operation, metadata, context = engine.records[0]
    assert operation == "hook"
    assert metadata["hook_event_name"] == "PreToolUse"
    assert context["objective"] == "Observe Codex lifecycle event PreToolUse"
    assert context["actor"].startswith("local-user:")
    assert engine.closed


def test_hook_denies_when_workspace_remains_busy(monkeypatch, tmp_path):
    attempts = []
    now, sleeps = install_clock(monkeypatch)

    def open_runtime(workspace):
        attempts.append(workspace)
        raise AuditError(BUSY)

    monkeypatch.setattr(hooks, "Research", open_runtime)
    result = hooks.observe({"hook_event_name": "PreToolUse"}, tmp_path)

    assert_denied(result)
    assert len(attempts) > 1
    assert 0 < now[0] <= 15.0
    assert sum(sleeps) == now[0]
    assert all(0 < pause <= 0.25 for pause in sleeps)


@pytest.mark.parametrize(
    "message",
    [
        "Audit journal chain is invalid",
        BUSY + ".",
    ],
)
def test_hook_denies_other_audit_failures_without_retry(monkeypatch, tmp_path, message):
    attempts = []
    now, sleeps = install_clock(monkeypatch)

    def open_runtime(workspace):
        attempts.append(workspace)
        raise AuditError(message)

    monkeypatch.setattr(hooks, "Research", open_runtime)
    result = hooks.observe({"hook_event_name": "PreToolUse"}, tmp_path)

    assert_denied(result)
    assert attempts == [tmp_path]
    assert sleeps == []
    assert now[0] == 0


def test_hook_does_not_retry_failure_after_workspace_acquisition(monkeypatch, tmp_path):
    attempts = []
    now, sleeps = install_clock(monkeypatch)

    class FailingEngine(RecordingEngine):
        def execute(self, operation, payload, **context):
            super().execute(operation, payload, **context)
            raise AuditError(BUSY)

    engine = FailingEngine()

    def open_runtime(workspace: Path):
        attempts.append(workspace)
        return engine

    monkeypatch.setattr(hooks, "Research", open_runtime)
    result = hooks.observe({"hook_event_name": "PreToolUse"}, tmp_path)

    assert_denied(result)
    assert attempts == [tmp_path]
    assert len(engine.records) == 1
    assert sleeps == []
    assert now[0] == 0
    assert engine.closed


def test_hook_workspaces_are_deterministic_and_separate_sessions(monkeypatch, tmp_path):
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    first = hooks.hook_workspace({"session_id": "session-a"})
    assert first == tmp_path / "codex-hook-sessions" / hashlib.sha256(b"session-a").hexdigest()
    assert hooks.hook_workspace({"session_id": "session-a"}) == first
    assert hooks.hook_workspace({"session_id": "session-b"}) != first


@pytest.mark.parametrize("session", ["../elsewhere", "C:\\outside\\folder", "/root/file", "a/b\\c", "\u2603"])
def test_hook_workspace_hashes_session_paths(monkeypatch, tmp_path, session):
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    selected = hooks.hook_workspace({"session_id": session})
    assert selected.parent == tmp_path / "codex-hook-sessions"
    assert selected.name == hashlib.sha256(session.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("session", [None, "", " \t\n", 42, [], {}, "\ud800"])
def test_hook_workspace_falls_back_for_missing_or_invalid_session(monkeypatch, tmp_path, session):
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    assert hooks.hook_workspace({"session_id": session}) == tmp_path / "codex-hooks"
    assert hooks.hook_workspace({}) == tmp_path / "codex-hooks"


@pytest.mark.parametrize("override", ["", "relative/path", Path("explicit-workspace")])
def test_hook_workspace_preserves_explicit_override(override):
    assert hooks.hook_workspace({"session_id": "session-a"}, override) == Path(override)


def test_hook_main_prepares_private_session_namespace(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NEWSRESEARCH_HOOK_WORKSPACE", raising=False)
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    monkeypatch.setattr(hooks.sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "PreToolUse", "session_id": "session-a"})))
    prepared, observed = [], []
    monkeypatch.setattr(hooks, "prepare_root", lambda path: prepared.append(path))
    monkeypatch.setattr(hooks, "observe", lambda event, workspace: observed.append((event, workspace)) or {})

    assert hooks.main() == 0
    assert prepared == [tmp_path / "codex-hook-sessions"]
    assert observed[0][1] == hooks.hook_workspace(observed[0][0])
    assert json.loads(capsys.readouterr().out) == {}


@pytest.mark.parametrize("override", [None, "explicit-hook-workspace"])
def test_hook_main_preserves_fallback_and_override(monkeypatch, tmp_path, capsys, override):
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    if override is None:
        monkeypatch.delenv("NEWSRESEARCH_HOOK_WORKSPACE", raising=False)
        event = {"hook_event_name": "PreToolUse"}
    else:
        monkeypatch.setenv("NEWSRESEARCH_HOOK_WORKSPACE", override)
        event = {"hook_event_name": "PreToolUse", "session_id": "session-a"}
    monkeypatch.setattr(hooks.sys, "stdin", io.StringIO(json.dumps(event)))
    prepared, observed = [], []
    monkeypatch.setattr(hooks, "prepare_root", lambda path: prepared.append(path))
    monkeypatch.setattr(hooks, "observe", lambda event, workspace: observed.append(workspace) or {})

    assert hooks.main() == 0
    assert prepared == []
    assert observed == [Path(override) if override is not None else tmp_path / "codex-hooks"]
    assert json.loads(capsys.readouterr().out) == {}


def test_hook_main_denies_session_namespace_security_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("NEWSRESEARCH_HOOK_WORKSPACE", raising=False)
    monkeypatch.setattr(hooks, "default_workspace", lambda: tmp_path / "research")
    monkeypatch.setattr(hooks.sys, "stdin", io.StringIO(json.dumps({"hook_event_name": "PreToolUse", "session_id": "session-a"})))

    def fail(_):
        raise AuditError("Unsafe namespace permissions")

    monkeypatch.setattr(hooks, "prepare_root", fail)
    monkeypatch.setattr(hooks, "observe", lambda *_: pytest.fail("Unsafe namespace must prevent observation"))
    assert hooks.main() == 0
    assert_denied(json.loads(capsys.readouterr().out))
