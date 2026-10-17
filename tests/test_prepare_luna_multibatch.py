"""Synthetic full-text preparation checks; no real archive/model execution."""
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
    import prepare_luna_multibatch as runner
finally:
    sys.path.pop(0)

SPEC = importlib.util.spec_from_file_location("multibatch_archive_fixture", ROOT / "tests/test_article_scope_metadata.py")
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
             "title": "Private synthetic title", "body": "Private synthetic body evidence.\r\n\r\nFull second paragraph. ",
             "date": "2026-01-01", "lang": "eng", "eventUri": "private-event-one",
             "source": {"uri": "private-publisher-one"}}
    value.update(changes)
    return value


def engine_for(tmp_path, corpus="incident-reports"):
    return runner.MultibatchPreparationResearch(tmp_path / runner.owner_name(corpus))


def execute(engine, root, corpus="incident-reports"):
    return engine.execute("status", {"data_root": str(root), "corpus_id": corpus},
                          objective="Test synthetic full-text preparation", actor="test:software")


def read_artifact(engine, identifier):
    return json.loads(engine.ledger.artifacts.read_bytes(identifier))


@pytest.mark.parametrize("which", ["descriptor", "manifest_artifact", "shard_plan_artifact", "markdown_artifact"])
def test_missing_prepared_artifact_stops_full_preflight(tmp_path, which):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        reference = (result["archives"][0]["descriptor_artifact"]
                     if which == "descriptor" else result[which])
        engine.ledger.artifacts.verified_path(reference).unlink()
        with pytest.raises(AuditError, match="missing"):
            execute(engine, root)
    finally:
        engine.close()


def manifest_rows(engine, result):
    manifest = read_artifact(engine, result["manifest_artifact"])
    return [row for chunk in manifest["descriptor_chunks"]
            for row in read_artifact(engine, chunk["artifact"])["rows"]]


def replace_incident_stream(root, raw, count):
    """Keep synthetic source inventories internally valid after changing rows."""
    path = root / "incident.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("artikelen.jsonl", raw)
    manifest_path = root / "corpora/incident-reports/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["bundles"][0].update(sha256=runner.sha256(path), declared_records=count)
    manifest["summary"]["declared_article_records"] = count
    inventory_path = root / "metadata/source-inventory.json"
    inventory = json.loads(inventory_path.read_bytes())
    inventory["files"][0].update(manifest["bundles"][0])
    fixtures.write_json(inventory_path, inventory)
    manifest["metadata_sources"][0]["sha256"] = runner.sha256(inventory_path)
    fixtures.write_json(manifest_path, manifest)


def test_registration_durable_intent_and_exact_reconstructable_descriptors(tmp_path, monkeypatch):
    articles = [article(), article(uri="private-second", body="Second exact body é 😀\nunchanged.")]
    root = fixtures.fixture(tmp_path / "data", articles)
    engine = engine_for(tmp_path)
    original_zip = zipfile.ZipFile
    calls = []

    def checked(path, *args, **kwargs):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "prompt", "profile", "model_profile", "codebook"} <= kinds
        events = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM events")}
        assert {"multibatch.bundle_scan.intended", "multibatch.archive_verification.intended"} <= events
        calls.append(str(path))
        return original_zip(path, *args, **kwargs)

    monkeypatch.setattr(runner.zipfile, "ZipFile", checked)
    try:
        result = execute(engine, root)
        assert calls == [str(root / "incident.zip")]
        rows = manifest_rows(engine, result)
        with original_zip(root / "incident.zip") as archive:
            raw_rows = archive.read("artikelen.jsonl").splitlines(keepends=True)
        total_line_bytes = 0
        all_lines = hashlib.sha256()
        for index, row in enumerate(rows):
            descriptor = row["descriptor"]
            assert row["state"] == "ready"
            locator = row["source_locator"]
            assert hashlib.sha256(raw_rows[locator["line"] - 1]).hexdigest() == locator["row_bytes_sha256"]
            normalized, states = runner.normalize_context(articles[index])
            rebuilt = runner.core.build_request_record(normalized,
                corpus_id="incident-reports", manifest_sha256=result["binding"]["partition"]["manifest_sha256"],
                source_locator=locator, source_sha256=digest(articles[index]), max_output_tokens=4096,
                count_tokens=len, token_proxy_method="cl100k_base_serialized_body_plus_32",
                context_availability=states)
            assert rebuilt["descriptor"] == descriptor
            assert rebuilt["packet"]["source_map"]["source_fields"]["body"]["text"] == articles[index]["body"]
            assert descriptor["input_tokens_proxy"] == len(runner.core.canonical_json(rebuilt["request"]["body"])) + 32
            total_line_bytes += len(rebuilt["jsonl_line"])
            all_lines.update(rebuilt["jsonl_line"])
        manifest = read_artifact(engine, result["manifest_artifact"])
        assert all_lines.hexdigest() == manifest["all_prospective_request_lines_sha256"]
        assert result["totals"]["line_bytes"] == total_line_bytes
        assert result["model_processing_pending"] == 2
        assert result["model_calls"] == result["uploads"] == result["membership_changes"] == 0
        assert result["upload_ready"] is False
        assert result["binding"]["tokenizer"]["is_model_exact"] is False
        assert set(result["versions"]) == {"protocol", "question", "selection", "dossier_definition", "prompt", "profile", "model_profile", "codebook"}
        plan = read_artifact(engine, result["shard_plan_artifact"])
        assert plan["paid_execution_authorized"] is False
        assert sum(shard["request_count"] for shard in plan["shards"]) == 2
        assert result["record_presentation_supported"] is False
    finally:
        engine.close()


def test_malformed_metadata_never_discards_complete_body(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article(title=9, lang={}, source="malformed", dateTimePub=123)])
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        assert result["totals"]["requests"] == 1
        assert result["totals"]["record_unavailable"] == result["totals"]["body_unavailable"] == 0
        assert result["totals"]["metadata_issue_rows"] == 1
        descriptor = manifest_rows(engine, result)[0]["descriptor"]
        states = descriptor["context_availability"]
        assert states["title"] == states["lang"] == states["dateTimePub"] == "nontext"
        assert states["source"] == "nonobject"
        assert states["source.uri"] == "absent"
    finally:
        engine.close()


def test_exact_body_request_reuse_keeps_all_rows_and_rejects_context_differences(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article(), article(uri="different-provider-id"),
        article(uri="third", date="2026-01-02"), article(uri="fourth", title="Different source title")])
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        totals = result["totals"]
        assert totals["rows"] == totals["fulltext_rows"] == 4
        assert totals["requests"] == totals["ready"] == 3
        assert totals["alias"] == 1
        rows = manifest_rows(engine, result)
        first, alias = rows[:2]
        assert alias["state"] == "alias"
        assert alias["canonical_custom_id"] == first["descriptor"]["custom_id"]
        assert alias["canonical_row_id"] == first["id"]
        assert alias["descriptor"]["custom_id"] != first["descriptor"]["custom_id"]
        assert alias["descriptor"]["source_sha256"] != first["descriptor"]["source_sha256"]
        assert alias["descriptor"]["request_body_sha256"] == first["descriptor"]["request_body_sha256"]
        assert len({row["descriptor"]["request_body_sha256"] for row in rows}) == 3
        assert totals["raw_input_tokens_proxy"] - totals["input_tokens_proxy"] == alias["descriptor"]["input_tokens_proxy"]
        assert all(row["production_eligibility"] == "unassessed" for row in rows)
        assert result["production_eligibility"] == "unassessed"
        plan = read_artifact(engine, result["shard_plan_artifact"])
        ids = {row["custom_id"] for shard in plan["shards"] for row in shard["records"]}
        assert alias["descriptor"]["custom_id"] not in ids
        assert alias["canonical_custom_id"] in ids
    finally:
        engine.close()


def test_whole_row_guard_explicit_retention_and_unavailable_coverage(tmp_path):
    rows = [article(), article(body=None), article(unknown_metadata="Bearer synthetic-sensitive-fixture"),
            article(retention="metadata_only"), article(quarantined=True), article(metadata_only=True)]
    root = fixtures.fixture(tmp_path / "data", rows)
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        totals = result["totals"]
        assert totals["rows"] == 6
        assert totals["requests"] == totals["body_unavailable"] == 1
        assert totals["retention_unavailable"] == 4
        assert result["failed_archives"] == result["pending_archives"] == 0
        assert result["semantic_exclusions"] == 0
        retained = manifest_rows(engine, result)
        assert len(retained) == 6
        assert all("descriptor" not in row for row in retained[1:])
        assert retained[2]["reason"] == "whole_row_credential_guard"
        for table in ("sources", "passages", "attempts"):
            assert engine.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        for artifact_path in engine.ledger.artifacts.root.iterdir():
            if artifact_path.is_file():
                raw = artifact_path.read_bytes()
                for private in (b"Private synthetic", b"private-article-one", b"private-publisher-one",
                                b"private-event-one", b"https://private.example", b"synthetic-sensitive-fixture"):
                    assert private not in raw
    finally:
        engine.close()


def test_bad_json_or_record_shape_remains_unavailable_in_manifest(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article()])
    replace_incident_stream(root, b'{bad json}\nnull\n{"article": null}\n', 3)
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        assert result["totals"]["rows"] == result["totals"]["record_unavailable"] == 3
        assert result["totals"]["requests"] == 0
        assert {row["reason"] for row in manifest_rows(engine, result)} == {"invalid_json", "row_not_object", "article_not_object"}
        assert result["markdown"]
        assert all(row["batch_usd_scenario"] == 0 for row in result["cost_scenarios"])
        assert result["queue_scenarios"][0]["sequential_whole_shard_capacity_tranches"] == 0
    finally:
        engine.close()


def test_large_fulltext_preserved_as_manual_queue_without_truncation(tmp_path):
    body = "long body unchanged " * 2500
    root = fixtures.fixture(tmp_path / "data", [article(body=body)])
    engine = engine_for(tmp_path)
    try:
        result = execute(engine, root)
        assert result["totals"]["requests"] == result["totals"]["manual_context_check"] == 1
        assert result["totals"]["ready"] == 0
        descriptor = manifest_rows(engine, result)[0]["descriptor"]
        assert descriptor["retained_body_sha256"] == hashlib.sha256(body.encode()).hexdigest()
        plan = read_artifact(engine, result["shard_plan_artifact"])
        assert len(plan["manual_queue"]) == 1
        assert plan["shards"] == []
        assert result["cost_scenarios"][-1]["assumed_output_tokens_per_request"] == 4096
        assert result["ready_cost_scenarios"][-1]["batch_usd_scenario"] == 0
    finally:
        engine.close()


def test_separate_corpus_owners_and_cross_corpus_request_rejected(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article()])
    left = engine_for(tmp_path)
    right = engine_for(tmp_path, "cybercrime")
    try:
        first = execute(left, root)
        second = execute(right, root, "cybercrime")
        assert first["id"] != second["id"]
        assert manifest_rows(left, first)[0]["descriptor"]["custom_id"] != manifest_rows(right, second)[0]["descriptor"]["custom_id"]
        assert {shard["corpus_id"] for shard in first["shards"]} == {"incident-reports"}
        assert {shard["corpus_id"] for shard in second["shards"]} == {"cybercrime"}
        with pytest.raises(ResearchError, match="cross_corpus_owner"):
            execute(left, root, "cybercrime")
    finally:
        left.close()
        right.close()


def test_partition_overlap_fails_before_archive_read(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    path = root / "corpora/cybercrime/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["bundles"][0]["path"] = "incident.zip"
    fixtures.write_json(path, manifest)
    engine = engine_for(tmp_path)
    monkeypatch.setattr(runner.zipfile, "ZipFile", lambda *a, **k: pytest.fail("No parsing after partition failure"))
    try:
        with pytest.raises(ResearchError, match="overlap_or_missing"):
            execute(engine, root)
    finally:
        engine.close()


@pytest.mark.parametrize("blocked_kind", ["multibatch.partition.read.intended", "multibatch.bundle_scan.intended"])
def test_audit_intent_failure_prevents_dependent_reads(tmp_path, monkeypatch, blocked_kind):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = engine_for(tmp_path)
    original_append = engine.ledger.append

    def failed(session, kind, data, *args, **kwargs):
        if kind == blocked_kind:
            raise AuditError("Synthetic durable intent failure")
        return original_append(session, kind, data, *args, **kwargs)

    def forbid(*args, **kwargs):
        pytest.fail("No dependent read without durable intent")

    monkeypatch.setattr(engine.ledger, "append", failed)
    if blocked_kind.endswith("partition.read.intended"):
        monkeypatch.setattr(runner, "read_partition", forbid)
    else:
        monkeypatch.setattr(runner.zipfile, "ZipFile", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic durable"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_result_storage_failure_cannot_publish_success(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = engine_for(tmp_path)
    original_append = engine.ledger.append

    def failed(session, kind, data, *args, **kwargs):
        if kind == "multibatch.manifest.saved":
            raise AuditError("Synthetic manifest anchoring failure")
        return original_append(session, kind, data, *args, **kwargs)

    monkeypatch.setattr(engine.ledger, "append", failed)
    try:
        with pytest.raises(AuditError, match="Synthetic manifest"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_archive_pre_hash_mismatch_prevents_text_processing(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    with (root / "incident.zip").open("ab") as stream:
        stream.write(b"changed")
    engine = engine_for(tmp_path)
    monkeypatch.setattr(runner.zipfile, "ZipFile", lambda *a, **k: pytest.fail("No parsing after hash failure"))
    try:
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("bad_call,code", [(2, "archive_postcheck_mismatch"), (3, "archive_final_hash_mismatch")])
def test_post_and_final_archive_hash_failures_prevent_success(tmp_path, monkeypatch, bad_call, code):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = engine_for(tmp_path)
    original_sha = runner.sha256
    calls = 0

    def changed_after_read(path):
        nonlocal calls
        if path == root / "incident.zip":
            calls += 1
            if calls == bad_call:
                return "0" * 64
        return original_sha(path)

    monkeypatch.setattr(runner, "sha256", changed_after_read)
    try:
        with pytest.raises(ResearchError, match=code):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_archive_count_mismatch_fails_instead_of_publishing_partial_success(tmp_path):
    root = fixtures.fixture(tmp_path / "data", [article()])
    replace_incident_stream(root, json.dumps({"article": article()}), 2)
    engine = engine_for(tmp_path)
    try:
        with pytest.raises(ResearchError, match="archive_postcheck_mismatch"):
            execute(engine, root)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 0
    finally:
        engine.close()


def test_exact_resume_rehashes_without_source_or_token_rescan(tmp_path, monkeypatch):
    root = fixtures.fixture(tmp_path / "data", [article()])
    engine = engine_for(tmp_path)
    try:
        original = execute(engine, root)
        monkeypatch.setattr(runner.zipfile, "ZipFile", lambda *a, **k: pytest.fail("Exact resume cannot parse rows"))
        monkeypatch.setattr(SyntheticEncoder, "encode", lambda *a, **k: pytest.fail("Exact resume cannot retokenize"))
        repeated = execute(engine, root)
        assert repeated == original
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='note'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='multibatch.exact_result.reused'").fetchone()[0] == 1
        with (root / "incident.zip").open("ab") as stream:
            stream.write(b"changed-after-completion")
        with pytest.raises(ResearchError, match="archive_pre_hash_mismatch"):
            execute(engine, root)
    finally:
        engine.close()


def test_wrong_owner_online_and_direct_handler_rejected(tmp_path):
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.MultibatchPreparationResearch(tmp_path / "wrong-owner")
    with pytest.raises(ResearchError, match="dedicated_offline_owner"):
        runner.MultibatchPreparationResearch(tmp_path / runner.owner_name("incident-reports"), config=Config(offline=False))
    engine = engine_for(tmp_path)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {})
    finally:
        engine.close()


def test_queue_capacity_illustrations_are_unconfirmed_without_duration():
    rows = runner.queue_scenarios([{"input_tokens_proxy": 15_000_000}, {"input_tokens_proxy": 10_000_000}])
    assert rows[0]["first_capacity_tranche_shards"] == 1
    assert rows[0]["sequential_whole_shard_capacity_tranches"] == 2
    assert rows[1]["sequential_whole_shard_capacity_tranches"] == 1
    assert all(row["user_account_capacity_confirmed"] is False and row["duration_estimate"] is None for row in rows)
