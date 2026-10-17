"""Synthetic tests of full-source inspection provenance, not entity accuracy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from newsresearch.common import AuditError, Config, ResearchError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import inspect_cyber_entity_design as runner
finally:
    sys.path.pop(0)

SPEC = importlib.util.spec_from_file_location("cyber_inspection_fixture", ROOT / "tests/test_article_scope_metadata.py")
assert SPEC is not None and SPEC.loader is not None
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
CYBER_PATH = "topics/cybercrime-nl/articles/articles-2024.zip"


def article(**changes):
    value = {"uri": "synthetic-one", "url": "https://example.test/one", "title": "Synthetic title",
             "body": "First exact paragraph.\n\nSecond exact paragraph.", "dateTimePub": "2026-01-01T12:00:00Z",
             "lang": "nld", "source": {"uri": "example.test"}}
    value.update(changes)
    return value


def execute(engine, root):
    return engine.execute("status", {"data_root": str(root)}, objective="Test synthetic source inspection",
                          actor="test:software")


def test_prior_versions_scan_intent_freeze_ingest_and_inspection_order(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article(), article(uri="second", body="Different full body.")])
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    original_zip = zipfile.ZipFile
    original_ingest = engine._ingest

    def checked_zip(path, *args, **kwargs):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "profile"} <= kinds
        events = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM events")}
        assert "cyber_inspection.bundle_scan.intended" in events
        assert "cyber_inspection.archive_verification.intended" in events
        assert str(path).endswith("articles-2024.zip")
        return original_zip(path, *args, **kwargs)

    def checked_ingest(session, context, data):
        frozen = engine.ledger.db.execute("SELECT id FROM records WHERE kind='note'").fetchall()
        assert len(frozen) == 1
        frozen_value = engine.ledger.get(frozen[0][0], "note")["content"]
        assert len(frozen_value["selected"]) == 1
        assert frozen_value["archives"][0]["rows"] == 2
        return original_ingest(session, context, data)

    monkeypatch.setattr(runner.zipfile, "ZipFile", checked_zip)
    monkeypatch.setattr(engine, "_ingest", checked_ingest)
    try:
        result = execute(engine, root)
        assert result["rows_scanned"] == result["usable_rows"] == 2
        assert len(result["selected_sources"]) == 1
        source = json.loads(engine.ledger.db.execute("SELECT payload FROM sources").fetchone()[0])
        inspection = engine.ledger.get(result["inspection"], "inspection")
        assert {p["id"] for p in inspection["passages"]} == set(result["passage_ids"])
        assert source["body"] in result["markdown"]
        assert source["url"] in result["markdown"]
        assert source["retrieval"]["retrieved_at"] is None
        assert source["raw_record"]["body"] == source["body"]
        locator = source["archive_provenance"]
        raw = engine.ledger.artifacts.read_bytes(source["exact_archive_row_artifact"])
        assert hashlib.sha256(raw).hexdigest() == locator["exact_row_bytes_sha256"]
        assert json.loads(raw)["article"] == source["raw_record"]
        assert result["model_calls"] == result["new_embeddings"] == 0
    finally:
        engine.close()


def test_guard_and_explicit_retention_exclusions_never_persist_forbidden_text(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article(), article(body="FORBIDDEN_METADATA", metadata_only=True),
        article(body="FORBIDDEN_QUARANTINE", quarantined=True), article(body=None),
        article(body="FORBIDDEN_CREDENTIAL_ROW", unknown="Bearer synthetic-sensitive-fixture")])
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        assert result["rows_scanned"] == 5
        assert result["usable_rows"] == 1
        assert result["unavailable_rows"] == 4
        assert result["row_states"] == {"usable": 1, "explicit_retention_excluded": 2,
                                        "missing_or_blank_body": 1, "credential_guard": 1}
        for path in engine.ledger.artifacts.root.iterdir():
            if path.is_file():
                raw = path.read_bytes()
                assert b"FORBIDDEN_" not in raw
                assert b"synthetic-sensitive-fixture" not in raw
    finally:
        engine.close()


def test_hash_rank_is_fixed_minimum_and_replay_does_not_redraw(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article(uri=str(i), body=f"Unique synthetic body {i}") for i in range(7)])
    with zipfile.ZipFile(root / CYBER_PATH) as archive:
        raws = archive.read("artikelen.jsonl").splitlines(keepends=True)
    archive_hash = runner.sha256(root / CYBER_PATH)
    expected = min(range(len(raws)), key=lambda index: runner.candidate_rank(
        archive_hash, index + 1, hashlib.sha256(raws[index]).hexdigest()))
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        frozen = engine.ledger.get(result["frozen_selection"], "note")["content"]
        assert frozen["selected"][0]["locator"]["jsonl_line"] == expected + 1

        def forbid(*args, **kwargs):
            raise AssertionError("Reuse must not parse article rows again")

        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
        assert execute(engine, root) == result
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='inspection'").fetchone()[0] == 2
    finally:
        engine.close()


def test_cross_archive_exact_title_body_collision_has_no_refill():
    first = {"article": article(), "locator": {"path": "a.zip"}, "selection_hash": "2"}
    second = {"article": article(uri="elsewhere", url="https://different.test"),
              "locator": {"path": "b.zip"}, "selection_hash": "1"}
    unique = {"article": article(title="Different title"), "locator": {"path": "c.zip"}, "selection_hash": "3"}
    selected, collisions = runner.deduplicate_selected([unique, second, first])
    assert selected == [first, unique]
    assert len(collisions) == 1
    assert collisions[0]["excluded_locator"] == second["locator"]
    assert collisions[0]["retained_locator"] == first["locator"]


def test_hash_failure_prevents_parsing(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    with (root / CYBER_PATH).open("ab") as stream:
        stream.write(b"archive change")
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)

    def forbid(*args, **kwargs):
        raise AssertionError("No parse after archive mismatch")

    monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    finally:
        engine.close()


def test_durable_intent_failure_prevents_parsing(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    original_append = engine.ledger.append

    def failed(session, kind, data, *args, **kwargs):
        if kind == "cyber_inspection.bundle_scan.intended":
            raise AuditError("Synthetic intent persistence failure")
        return original_append(session, kind, data, *args, **kwargs)

    def forbid(*args, **kwargs):
        raise AssertionError("No parse without durable scan intent")

    monkeypatch.setattr(engine.ledger, "append", failed)
    monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic intent"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 0
    finally:
        engine.close()


def test_all_unavailable_is_reported_and_reusable_without_fabricated_dataset(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article(body=None)])
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        assert result["selected_sources"] == []
        assert result["dataset"] is result["inspection"] is None
        assert result["unavailable_rows"] == 1
        assert "Selected 0 distinct full-text articles" in result["markdown"]
        assert execute(engine, root) == result
    finally:
        engine.close()


def test_owner_online_and_direct_handler_rejected(tmp_path):
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.CyberInspectionResearch(tmp_path / "wrong")
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.CyberInspectionResearch(tmp_path / runner.OWNER, config=Config(offline=False))
    engine = runner.CyberInspectionResearch(tmp_path / runner.OWNER)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {})
    finally:
        engine.close()
