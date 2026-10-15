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
