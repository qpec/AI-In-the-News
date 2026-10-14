from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from newsresearch.common import AuditError


def launcher() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts/run_embeddings.py"
    spec = importlib.util.spec_from_file_location("embedding_launcher", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_progress_follows_audit_and_omits_payload(capsys: Any) -> None:
    calls = []

    def append(*args: Any) -> int:
        assert capsys.readouterr().out == ""
        calls.append(args)
        return 123

    engine = SimpleNamespace(ledger=SimpleNamespace(append=append))
    launcher().report_durable_progress(engine)
    payload = {"status": "valid", "http_status": 200, "private": "synthetic-unpublished-payload"}
    projection = object()
    assert engine.ledger.append("session", "model.attempt.completed", payload, projection) == 123
    assert calls == [("session", "model.attempt.completed", payload, projection)]
    output = capsys.readouterr().out
    assert json.loads(output)["new_requests_completed"] == 1
    assert "private" not in output and "synthetic-unpublished-payload" not in output


def test_failed_audit_is_never_reported_as_progress(capsys: Any) -> None:
    def append(*args: Any) -> int:
        raise AuditError("Synthetic durable-write failure")

    engine = SimpleNamespace(ledger=SimpleNamespace(append=append))
    launcher().report_durable_progress(engine)
    with pytest.raises(AuditError):
        engine.ledger.append("session", "model.attempt.completed", {"status": "valid"})
    assert capsys.readouterr().out == ""
