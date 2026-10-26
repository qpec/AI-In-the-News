from pathlib import Path
from typing import Any

import pytest

from newsresearch.common import ResearchError
from newsresearch.runtime import Research


def test_clone_active_writer_preserves_sources_and_branch(prepared: Any, tmp_path: Path) -> None:
    original, versions, run = prepared
    before = original.ledger.db.execute("SELECT max(seq) FROM events").fetchone()[0]
    maintenance = Research(tmp_path / "maintenance")
    try:
        result = maintenance.execute("clone_workspace", {
            "source": str(original.ledger.root), "destination": str(tmp_path / "copy"),
        }, objective="Test consistent online copy", actor="codex:test")
        assert result["verified"]
        assert result["parent_head_seq"] == before
        assert result["inherited_model_execution_authorized"] is False
        assert original.ledger.db.execute("SELECT max(seq) FROM events").fetchone()[0] == before
        copy = Research(tmp_path / "copy")
        try:
            assert copy.ledger.get(versions["dataset"]) == original.ledger.get(versions["dataset"])
            search = copy.execute("search", {"query": "outage"}, versions=versions,
                                  objective="Search copied evidence", actor="codex:test")
            assert search["hits"]
        finally:
            copy.close()
        assert run("search", {"query": "outage"})["hits"]
    finally:
        maintenance.close()


def test_clone_never_overwrites_or_nests(engine: Research, tmp_path: Path) -> None:
    for target in (engine.ledger.root, engine.ledger.root / "child", tmp_path):
        with pytest.raises(ResearchError):
            engine.execute("clone_workspace", {"source": str(engine.ledger.root),
                           "destination": str(target)}, objective="Reject unsafe clone", actor="codex:test")
