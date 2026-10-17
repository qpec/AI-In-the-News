"""Synthetic audited integration checks; no production corpus or inference."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import run_scope_reduction_experiments as runner
finally:
    sys.path.pop(0)

SPEC = importlib.util.spec_from_file_location("scope_runner_archive_fixture",
    ROOT / "tests/test_article_scope_metadata.py")
assert SPEC is not None and SPEC.loader is not None
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


def article(**changes):
    value = {"uri": "private-article-one", "url": "https://private.example/one",
             "title": "Private synthetic title", "body": "Private synthetic body evidence.",
             "date": "2026-01-01", "lang": "eng", "eventUri": "private-event-one",
             "source": {"uri": "private-publisher-one"}}
    value.update(changes)
    return value


def execute(engine, root, corpus="incident-reports"):
    return engine.execute("status", {"data_root": str(root), "corpus_id": corpus},
        objective="Test synthetic offline reduction provenance", actor="test:software")


def lineage(engine, result):
    return json.loads(engine.ledger.artifacts.read_bytes(result["lineage_artifact"]))


def test_methods_and_bundle_intent_precede_source_read_and_lineage_replays(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article(), article(uri="second", source={"uri": "second-source"})])
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    original_zip = zipfile.ZipFile
    calls = []

    def checked(path, *args, **kwargs):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "profile"} <= kinds
        events = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM events")}
        assert "reduction.bundle_scan.intended" in events
        assert "reduction.archive_verification.intended" in events
        calls.append(str(path))
        return original_zip(path, *args, **kwargs)

    monkeypatch.setattr(runner.zipfile, "ZipFile", checked)
    try:
        result = execute(engine, root)
        assert calls == [str(root / "incident.zip")]
        saved = lineage(engine, result)
        assert digest(saved["rows"]) == result["metrics"]["lineage_sha256"]
        assert {row["locator_hash"] for row in saved["rows"]} == set(saved["locators"])
        with original_zip(root / "incident.zip") as archive:
            raw_rows = archive.read("artikelen.jsonl").splitlines(keepends=True)
        for row in saved["rows"]:
            locator = saved["locators"][row["locator_hash"]]
            raw = raw_rows[locator["jsonl_line"] - 1]
            assert hashlib.sha256(raw).hexdigest() == locator["exact_row_bytes_sha256"]
            assert digest(json.loads(raw)) == row["row_hash"]
            assert row["locator_hash"] == digest({"corpus": "incident-reports",
                "locator": f"{locator['path']}:{locator['jsonl_line']}"})
        assert result["metrics"]["source_neutral_packet_experiment"]["distinct_processing_units"] == 1
        assert result["metrics"]["provider_first_pair_experiment"]["initial_selected_publication_appearances"] == 2
    finally:
        engine.close()


def test_guard_unavailable_no_raw_artifact_and_exhaustive_sample_frame(tmp_path):
    rows = [article(), article(uri="second", source={"uri": "second-source"}),
            article(uri="missing-publisher", source={}), article(uri="missing-event", eventUri=None),
            article(uri="one-source", eventUri="only-one"), article(body=None),
            article(unknown_metadata="Bearer synthetic-sensitive-fixture")]
    root = fixtures.fixture(tmp_path / "data", rows)
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        saved = lineage(engine, result)
        assert result["metrics"]["unavailable_rows"] == 2
        assert result["metrics"]["retention_flags"]["credential_flagged"] == 1
        assert result["metrics"]["usable_body_rows"] == result["sampling"]["population_reports"] == 5
        assert result["sampling"]["planned_sample_reports"] == 5
        selected = [item for stratum in result["sampling"]["strata"] for item in stratum["selected_ids"]]
        assert len(selected) == len(set(selected)) == 5
        assert set(selected) == {row["locator_hash"] for row in saved["rows"] if row["usable"]}
        assert len(result["sampling"]["strata"]) == 4
        assert all(stratum["current_pending"] == stratum["n"] and stratum["current_valid_reference_labels"] == 0
                   for stratum in result["sampling"]["strata"])
        assert result["model_calls"] == result["new_embeddings"] == result["semantic_exclusions"] == 0
        assert result["failed_archives"] == result["pending_archives"] == 0
        for table in ("sources", "passages", "attempts"):
            assert engine.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        for artifact in engine.ledger.artifacts.root.iterdir():
            if artifact.is_file():
                raw = artifact.read_bytes()
                for private in (b"Private synthetic", b"private-article-one", b"private-publisher-one",
                                b"private-event-one", b"https://private.example", b"synthetic-sensitive-fixture"):
                    assert private not in raw
    finally:
        engine.close()


def test_corpus_isolation_preserves_separate_keys_and_frames(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    try:
        left = execute(engine, root, "incident-reports")
        right = execute(engine, root, "cybercrime")
        left_row = lineage(engine, left)["rows"][0]
        right_row = lineage(engine, right)["rows"][0]
        assert left["id"] != right["id"]
        assert left["binding"]["partition"]["manifest_sha256"] != right["binding"]["partition"]["manifest_sha256"]
        for key in ("locator_hash", "reuse_key", "neutral_reuse_key", "focus_reuse_key"):
            assert left_row[key] != right_row[key]
        assert left["metrics"]["rows_total"] == right["metrics"]["rows_total"] == 1
        assert all(row["stratum"].startswith("incident-reports:") for row in left["sampling"]["strata"])
        assert all(row["stratum"].startswith("cybercrime:") for row in right["sampling"]["strata"])
    finally:
        engine.close()


def test_archive_hash_failure_prevents_source_stream(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    with (root / "incident.zip").open("ab") as stream:
        stream.write(b"changed")
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)

    def forbid(*args, **kwargs):
        raise AssertionError("No source parse after hash failure")

    monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_durable_intent_failure_prevents_source_stream(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    original_append = engine.ledger.append

    def failed(session, kind, data, *args, **kwargs):
        if kind == "reduction.bundle_scan.intended":
            raise AuditError("Synthetic durable intent failure")
        return original_append(session, kind, data, *args, **kwargs)

    def forbid(*args, **kwargs):
        raise AssertionError("No source parse without durable intent")

    monkeypatch.setattr(engine.ledger, "append", failed)
    monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic durable"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_exact_resume_preserves_result_and_does_not_scan_again(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    try:
        original = execute(engine, root)

        def forbid(*args, **kwargs):
            raise AssertionError("Exact result reuse must not rescan ZIP rows")

        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
        repeated = execute(engine, root)
        assert repeated == original
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='reduction.exact_result.reused'").fetchone()[0] == 1
    finally:
        engine.close()


def test_exact_resume_rechecks_archive_hash_before_reuse(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    try:
        execute(engine, root)
        with (root / "incident.zip").open("ab") as stream:
            stream.write(b"changed-after-completion")

        def forbid(*args, **kwargs):
            raise AssertionError("Changed archive must not be parsed")

        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='reduction.exact_result.reused'").fetchone()[0] == 0
    finally:
        engine.close()


def test_wrong_owner_online_or_direct_handler_rejected(tmp_path):
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.ReductionResearch(tmp_path / "wrong-owner")
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.ReductionResearch(tmp_path / runner.OWNER, config=Config(offline=False))
    engine = runner.ReductionResearch(tmp_path / runner.OWNER)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {})
    finally:
        engine.close()
