"""Synthetic audited excerpt workload checks, never a corpus/model run."""
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
    import audit_luna_excerpts as runner
finally:
    sys.path.pop(0)

SPEC = importlib.util.spec_from_file_location("excerpt_archive_fixture", ROOT / "tests/test_article_scope_metadata.py")
assert SPEC is not None and SPEC.loader is not None
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)


class SyntheticEncoder:
    name = "synthetic-character-count"

    def encode(self, text, *, disallowed_special):
        assert disallowed_special == ()
        return list(text)


@pytest.fixture(autouse=True)
def no_real_tokenizer(monkeypatch):
    monkeypatch.setattr(runner, "offline_tokenizer", SyntheticEncoder)


def article(**changes):
    value = {"uri": "private-article-one", "url": "https://private.example/one",
             "title": "Private synthetic title", "body": "Private synthetic body evidence.",
             "date": "2026-01-01", "lang": "eng", "eventUri": "private-event-one",
             "source": {"uri": "private-publisher-one"}}
    value.update(changes)
    return value


def execute(engine, root, corpus="incident-reports"):
    return engine.execute("status", {"data_root": str(root), "corpus_id": corpus},
                          objective="Test synthetic excerpt audit", actor="test:software")


def lineage(engine, result):
    return json.loads(engine.ledger.artifacts.read_bytes(result["lineage_artifact"]))


def test_registered_method_and_durable_bundle_intent_precede_source_read(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article(), article(uri="private-second")])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    original_zip = zipfile.ZipFile
    calls = []

    def checked(path, *args, **kwargs):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "prompt", "profile"} <= kinds
        events = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM events")}
        assert {"excerpt.bundle_scan.intended", "excerpt.archive_verification.intended"} <= events
        calls.append(str(path))
        return original_zip(path, *args, **kwargs)

    monkeypatch.setattr(runner.zipfile, "ZipFile", checked)
    try:
        result = execute(engine, root)
        assert calls == [str(root / "incident.zip")]
        saved = lineage(engine, result)
        assert digest(saved["rows"]) == result["metrics"]["lineage_hash"]
        assert {row["id"] for row in saved["rows"]} == set(saved["locators"])
        with original_zip(root / "incident.zip") as archive:
            raw_rows = archive.read("artikelen.jsonl").splitlines(keepends=True)
        for row in saved["rows"]:
            locator = saved["locators"][row["id"]]
            raw = raw_rows[locator["line"] - 1]
            assert hashlib.sha256(raw).hexdigest() == locator["row_bytes_sha256"]
            assert digest(json.loads(raw)) == row["row_hash"]
            assert row["id"] == digest({"corpus": "incident-reports",
                "locator": f"{locator['archive_path']}:{locator['line']}"})
        assert result["binding"]["tokenizer"]["is_model_exact"] is False
        assert result["record_presentation_supported"] is False
    finally:
        engine.close()


def test_guard_and_missing_body_preserve_coverage_without_source_artifacts(tmp_path):
    rows = [article(), article(body=None), article(unknown_metadata="Bearer synthetic-sensitive-fixture")]
    root = fixtures.fixture(tmp_path / "data", rows)
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        totals = result["metrics"]["totals"]
        assert totals["rows"] == 3
        assert totals["usable"] == totals["body_unavailable"] == totals["retention_unavailable"] == 1
        assert result["model_calls"] == result["new_embeddings"] == result["semantic_exclusions"] == 0
        assert result["failed_archives"] == result["pending_archives"] == 0
        assert len(lineage(engine, result)["rows"]) == 3
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


def test_all_unavailable_corpus_has_honest_zero_result_not_render_failure(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article(body=None)])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        result = execute(engine, root)
        assert result["metrics"]["totals"]["rows"] == 1
        assert result["metrics"]["totals"].get("usable", 0) == 0
        assert result["markdown"]
        for variant in result["metrics"]["variants"].values():
            assert variant["mean_input_tokens_proxy"] is None
    finally:
        engine.close()


def test_corpus_partition_preserves_manifest_and_row_identity(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        left = execute(engine, root)
        right = execute(engine, root, "cybercrime")
        assert left["id"] != right["id"]
        assert left["binding"]["partition"]["manifest_sha256"] != right["binding"]["partition"]["manifest_sha256"]
        assert lineage(engine, left)["rows"][0]["id"] != lineage(engine, right)["rows"][0]["id"]
        assert left["metrics"]["totals"]["rows"] == right["metrics"]["totals"]["rows"] == 1
    finally:
        engine.close()


def test_archive_pre_hash_failure_prevents_source_stream(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    with (root / "incident.zip").open("ab") as stream:
        stream.write(b"changed")
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)

    def forbid(*args, **kwargs):
        raise AssertionError("No source parsing after archive hash failure")

    monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("blocked_kind", ["excerpt.partition.read.intended", "excerpt.bundle_scan.intended"])
def test_durable_intent_failure_prevents_dependent_reads(tmp_path, monkeypatch, blocked_kind):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    original_append = engine.ledger.append

    def failed(session, kind, data, *args, **kwargs):
        if kind == blocked_kind:
            raise AuditError("Synthetic durable intent failure")
        return original_append(session, kind, data, *args, **kwargs)

    def forbid(*args, **kwargs):
        raise AssertionError("No dependent reads without durable intent")

    monkeypatch.setattr(engine.ledger, "append", failed)
    if blocked_kind == "excerpt.partition.read.intended":
        monkeypatch.setattr(runner, "read_partition", forbid)
    else:
        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic durable"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_exact_resume_reuses_result_without_source_rescan(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        original = execute(engine, root)

        def forbid(*args, **kwargs):
            raise AssertionError("Exact resume must not rescan source rows")

        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
        repeated = execute(engine, root)
        assert repeated == original
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='excerpt.exact_result.reused'").fetchone()[0] == 1
    finally:
        engine.close()


def test_exact_resume_reverifies_archive_before_reuse(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        execute(engine, root)
        with (root / "incident.zip").open("ab") as stream:
            stream.write(b"changed-after-completion")

        def forbid(*args, **kwargs):
            raise AssertionError("Changed source must not be parsed")

        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='excerpt.exact_result.reused'").fetchone()[0] == 0
    finally:
        engine.close()


def test_post_scan_archive_mutation_cannot_publish_success(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    original_sha = runner.sha256
    calls = 0

    def changed_after_read(path):
        nonlocal calls
        if path == root / "incident.zip":
            calls += 1
            if calls >= 2:
                return "0" * 64
        return original_sha(path)

    monkeypatch.setattr(runner, "sha256", changed_after_read)
    try:
        with pytest.raises(ResearchError, match="archive_postcheck_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_wrong_owner_online_and_direct_handler_are_rejected(tmp_path):
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.ExcerptResearch(tmp_path / "wrong-owner")
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.ExcerptResearch(tmp_path / runner.OWNER, config=Config(offline=False))
    engine = runner.ExcerptResearch(tmp_path / runner.OWNER)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {})
    finally:
        engine.close()
