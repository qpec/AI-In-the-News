"""Synthetic archive metadata checks; no production sources or model inference."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

from newsresearch.common import AuditError, Config, ResearchError

SPEC = importlib.util.spec_from_file_location("article_scope_metadata",
    Path(__file__).resolve().parents[1] / "scripts/audit_article_scope_metadata.py")
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def fixture(root, articles=None):
    articles = articles or [
        {"uri": "a", "url": "https://one.example/a", "eventUri": "event", "source": {"uri": "one"},
         "categories": [{"uri": "category-do-not-save", "wgt": 2}], "body": "Fictional article text: do not retain."},
        {"uri": "b", "url": "https://two.example/b", "eventUri": "event", "source": {"uri": "two"}},
    ]
    registry = {"cross_corpus_grouping": "forbidden_by_default", "corpora": []}
    for corpus in audit.CORPORA:
        relative = "incident.zip" if corpus == "incident-reports" else "topics/cybercrime-nl/articles/articles-2024.zip"
        archive = root / relative
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr("artikelen.jsonl", "\n".join(json.dumps({"article": article}) for article in articles))
        bundle = {"path": relative, "sha256": audit.sha256(archive), "cohort": "fixture" if corpus == "incident-reports" else "cybercrime-nl",
                  "declared_records": len(articles), "declared_with_text": sum(audit.nonblank(row.get("body")) for row in articles)}
        metadata = []
        if corpus == "incident-reports":
            path = root / "metadata/source-inventory.json"
            write_json(path, {"complete": True, "pending": [], "files": [{"kind": "article-bundle", **bundle}]})
            metadata.append({"path": "metadata/source-inventory.json", "sha256": audit.sha256(path)})
        else:
            bundle.update({"snapshot": "2023-2026", "date_start": "2024-01-01", "date_end": "2024-12-31"})
            for base in ("topics/cybercrime-nl", "topics/cybercrime-nl/extensions/2020-2023"):
                directory = root / base
                directory.mkdir(parents=True, exist_ok=True)
                csv = "year,date_start,date_end,returned,body_present\n"
                if base == "topics/cybercrime-nl":
                    csv += f"2024,2024-01-01,2024-12-31,{len(articles)},{bundle['declared_with_text']}\n"
                coverage = directory / "coverage-by-year.csv"
                coverage.write_text(csv, encoding="utf-8")
                sums = directory / "SHA256SUMS.txt"
                sums.write_text(f"{audit.sha256(coverage)}  coverage-by-year.csv\n" +
                    (f"{bundle['sha256']}  articles/articles-2024.zip\n" if base == "topics/cybercrime-nl" else ""), encoding="utf-8")
                metadata.extend({"path": str(path.relative_to(root)).replace("\\", "/"), "sha256": audit.sha256(path)} for path in (sums, coverage))
        manifest = {"corpus_id": corpus, "dossier_namespace": corpus + ":", "bundles": [bundle],
                    "metadata_sources": metadata, "summary": {"bundles": 1, "declared_article_records": len(articles)}}
        relative_manifest = f"corpora/{corpus}/manifest.json"
        write_json(root / relative_manifest, manifest)
        registry["corpora"].append({"corpus_id": corpus, "manifest": relative_manifest, "dossier_namespace": corpus + ":"})
    write_json(root / "corpora/registry.json", registry)
    return root


def test_field_state_type_and_bounded_value_histograms():
    counts = audit.MetadataCounts()
    counts.add({"article": {"uri": "a", "dataType": "news", "source": {"dataType": "blog"},
        "eventUri": None, "categories": [], "concepts": [{"type": "org", "score": 100}, {"type": "org"}, {"type": "private-unknown"}],
        "isDuplicate": False, "lang": "eng", "unexpected-sensitive-key": "do-not-save"}})
    counts.add({"article": {"dataType": "private-unknown", "categories": None, "concepts": {}, "eventUri": " "}})
    counts.add({"article": {"eventUri": 123, "categories": [{"wgt": 7, "score": False}, "invalid"]}})
    result = counts.result()
    assert result["fields"]["article.categories"]["states"] == {"absent": 0, "null": 1, "empty": 1, "populated": 1}
    assert result["fields"]["article.categories"]["types"]["array"] == 2
    assert result["fields"]["article.eventUri"]["types"]["number"] == 1
    assert result["controlled_value_histograms"]["article.dataType"] == {"news": 1, "other_populated": 1, "absent": 1}
    assert result["controlled_value_histograms"]["article.source.dataType"]["blog"] == 1
    assert result["controlled_value_histograms"]["article.isDuplicate"]["false"] == 1
    assert result["concept_type_item_histogram"]["org"] == 2
    assert result["concept_type_article_presence"]["org"] == 1
    assert result["list_item_fields"]["category.score"]["types"]["boolean"] == 1
    assert result["list_item_counts"]["category.non_object_items"] == 1
    assert "private-unknown" not in json.dumps(result)
    assert "unexpected-sensitive-key" not in json.dumps(result)


def test_multiplicity_deduplicates_provider_versions_and_keeps_unknowns():
    counts = audit.MetadataCounts()
    for article in (
        {"uri": "a", "eventUri": "e", "url": "https://one.example/a#x", "source": {"uri": "one"}},
        {"uri": "a", "eventUri": "e", "url": "https://one.example/a#y", "source": {"uri": "one"}},
        {"uri": "b", "eventUri": "e", "url": "https://two.example/b", "source": {"uri": "two"}},
        {"uri": "a", "eventUri": "other", "source": {"uri": "changed"}},
        {"eventUri": "unknown"}, {"uri": "missing-event"},
    ):
        counts.add({"article": article})
    result = counts.result()
    events = result["provider_event_multiplicity"]
    assert events["groups_with_2plus_identities_and_source_uris"] == 1
    assert events["rows_in_groups_with_2plus_identities_and_source_uris"] == 3
    assert events["event_id_groups"] == 3
    assert events["rows_with_event_id_unknown_article_identity"] == 1
    assert result["provider_ids_with_multiple_nonblank_event_uris"] == 1
    assert result["provider_ids_with_multiple_nonblank_source_uris"] == 1
    assert result["distinct_provider_ids"] == 3
    assert result["distinct_canonical_urls"] == 2
    assert result["article_identity_rows"]["unknown"] == 1


def test_conservative_url_identity_and_no_raw_values():
    assert audit.canonical_url("HTTPS://Example.Org/P?q=1#x") == "https://example.org/P?q=1"
    assert audit.canonical_url("https://example.org/P?q=1") != audit.canonical_url("https://example.org/P?q=2")
    assert audit.canonical_url("file:///secret") is None
    assert audit.canonical_url("https://user:password@example.org/a") is None
    counts = audit.MetadataCounts()
    counts.add({"article": {"url": "https://private.example/specific", "eventUri": "secret-event", "title": "secret-title",
        "body": "secret-body", "source": {"uri": "secret-publisher"}, "concepts": [{"uri": "secret-concept"}]}})
    serialized = json.dumps(counts.result())
    for secret in ("secret-", "private.example"):
        assert secret not in serialized
    assert counts.result()["article_identity_rows"]["url_fallback"] == 1


@pytest.mark.parametrize("corpus", audit.CORPORA)
def test_partition_inventory_validation(tmp_path, corpus):
    root = fixture(tmp_path / "data")
    result = audit.read_partition(root, corpus)
    assert result["corpus_id"] == corpus
    assert result["manifest_sha256"] == hashlib.sha256((root / f"corpora/{corpus}/manifest.json").read_bytes()).hexdigest()


def test_partition_overlap_rejected(tmp_path):
    root = fixture(tmp_path / "data")
    path = root / "corpora/cybercrime/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["bundles"][0]["path"] = "incident.zip"
    write_json(path, manifest)
    with pytest.raises(ResearchError, match="overlap_or_missing"):
        audit.read_partition(root, "incident-reports")


def test_manifest_cannot_silently_change_declared_inventory(tmp_path):
    root = fixture(tmp_path / "data")
    path = root / "corpora/incident-reports/manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["bundles"][0]["cohort"] = "changed"
    write_json(path, manifest)
    with pytest.raises(ResearchError, match="differs_from_inventory"):
        audit.read_partition(root, "incident-reports")


def test_full_audited_scan_registers_before_stream_and_retains_only_aggregates(tmp_path, monkeypatch):
    root = fixture(tmp_path / "data")
    engine = audit.MetadataAuditResearch(tmp_path / audit.WORKSPACE_NAME)
    original_scan = audit.scan_archive
    calls = []

    def checked(path, counts):
        kinds = {row[0] for row in engine.ledger.db.execute("SELECT kind FROM records")}
        assert {"protocol", "question", "selection", "dossier_definition", "profile"} <= kinds
        calls.append(path)
        return original_scan(path, counts)

    monkeypatch.setattr(audit, "scan_archive", checked)
    try:
        result = engine.execute("status", {"data_root": str(root), "corpus_id": "incident-reports"},
            objective="Verify synthetic metadata scope", actor="test:software")
        assert len(calls) == 1
        assert result["aggregate"]["rows"] == 2
        assert result["aggregate"]["provider_event_multiplicity"]["groups_with_2plus_identities_and_source_uris"] == 1
        assert result["model_calls"] == result["new_embeddings"] == result["membership_changes"] == 0
        assert result["failed_archives"] == result["pending_archives"] == 0
        assert Path(result["content_path"]).read_text(encoding="utf-8") == result["markdown"]
        assert result["record_presentation_supported"] is False
        assert "not same-event truth" in result["markdown"]
        for table in ("sources", "passages", "attempts"):
            assert engine.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        assert "category-do-not-save" not in json.dumps(result)
        assert "Fictional article text" not in json.dumps(result)
    finally:
        engine.close()


def test_preflight_failure_prevents_archive_stream(tmp_path, monkeypatch):
    root = fixture(tmp_path / "data")
    engine = audit.MetadataAuditResearch(tmp_path / audit.WORKSPACE_NAME)
    append = engine.ledger.append

    def fail(session, kind, data, *args, **kwargs):
        if kind == "metadata.scan.intended":
            raise AuditError("Synthetic audit storage failure")
        return append(session, kind, data, *args, **kwargs)

    def forbid(*args):
        raise AssertionError("No archive scan after intent failure")

    monkeypatch.setattr(engine.ledger, "append", fail)
    monkeypatch.setattr(audit, "scan_archive", forbid)
    try:
        with pytest.raises(AuditError, match="Synthetic audit"):
            engine.execute("status", {"data_root": str(root), "corpus_id": "incident-reports"},
                objective="Test failed durable metadata intent", actor="test:software")
    finally:
        engine.close()


def test_modified_archive_fails_before_stream(tmp_path, monkeypatch):
    root = fixture(tmp_path / "data")
    with (root / "incident.zip").open("ab") as stream:
        stream.write(b"changed")
    engine = audit.MetadataAuditResearch(tmp_path / audit.WORKSPACE_NAME)

    def forbid(*args):
        raise AssertionError("Hash mismatch must stop before parsing")

    monkeypatch.setattr(audit, "scan_archive", forbid)
    try:
        with pytest.raises(ResearchError, match="pre_scan_hash_mismatch"):
            engine.execute("status", {"data_root": str(root), "corpus_id": "incident-reports"},
                objective="Test changed archive protection", actor="test:software")
    finally:
        engine.close()


def test_online_and_original_owner_rejected(tmp_path):
    with pytest.raises(ResearchError, match="dedicated_owner"):
        audit.MetadataAuditResearch(tmp_path / "luna-seven-day-validation-20261016-v1")
    with pytest.raises(ResearchError, match="offline_configuration"):
        audit.MetadataAuditResearch(tmp_path / audit.WORKSPACE_NAME, config=Config(offline=False))


def test_direct_handler_call_rejected(tmp_path):
    engine = audit.MetadataAuditResearch(tmp_path / audit.WORKSPACE_NAME)
    try:
        with pytest.raises(AuditError):
            engine._status("not-active", None, {})
    finally:
        engine.close()
