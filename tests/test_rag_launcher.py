from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_embedding_key_is_scoped_and_removed_on_failure(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "scripts/run_rag_query.py"
    spec = importlib.util.spec_from_file_location("rag_launcher", path)
    assert spec and spec.loader
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    observed = []

    def embedding(*args, **kwargs):
        observed.append(os.environ.get("OPENAI_API_KEY"))
        raise RuntimeError("synthetic transport failure")

    engine = SimpleNamespace(gateway=SimpleNamespace(embed=embedding))
    launcher.scoped_embedding(engine, "synthetic-test-value")
    assert "OPENAI_API_KEY" not in os.environ
    with pytest.raises(RuntimeError, match="synthetic transport failure"):
        engine.gateway.embed()
    assert observed == ["synthetic-test-value"]
    assert "OPENAI_API_KEY" not in os.environ
