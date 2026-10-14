from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

import pytest

from newsresearch.runtime import Research
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.preparation import METHOD, RETRIEVAL_UNKNOWN, allocate, chunks


def make_archive(root: Path, with_text: bool = False) -> None:
    """Synthetic provider metadata, including missingness and cross-bundle reuse."""
    root.mkdir()
    files = []
    upstream = []

    def inventory_entry(path: Path, kind: str) -> dict[str, Any]:
        raw = path.read_bytes()
        return {
            "path": path.name,
            "kind": kind,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    cases = [
        [
            {"eventUri": "event-a"},
            {},
            {"eventUri": None},
            {"eventUri": ""},
            {"eventUri": " \t"},
            {"eventUri": 1},
            {"eventUri": []},
            {"eventUri": {}},
        ],
        [{"eventUri": "event-a"}, {"eventUri": "event-b"}, {"eventUri": " event-b "}],
    ]
    for index, articles in enumerate(cases):
        name = f"bundle-{index}.zip"
        cohort = f"synthetic-{index}"
        rows = [
            {
                "collection_cohort": cohort,
                "article": {
                    "uri": f"{index}-{number}",
                    **article,
                    "body": ("Synthetic één 🧪. " * 220 + "\n\nSecond paragraph.")
                    if with_text and number != 1
                    else "",
                    "dateTimePub": "2020-01-01T00:00:00Z",
                },
            }
            for number, article in enumerate(articles)
        ]
        path = root / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("artikelen.jsonl", "\n".join(json.dumps(row) for row in rows))
        entry = inventory_entry(path, "article-bundle")
        files.append(entry)
        upstream.append(
            {
                "bestand": name,
                "deelcollectie": cohort,
                "sha256": entry["sha256"],
                "records": len(rows),
                "met_tekst": sum(bool(row["article"]["body"]) for row in rows),
                "zonder_tekst": sum(not row["article"]["body"] for row in rows),
            }
        )
    manifest = root / "bestand_manifest.json"
    manifest.write_text(json.dumps(upstream), encoding="utf-8")
    files.append(inventory_entry(manifest, "upstream-manifest"))
    (root / "metadata").mkdir()
    (root / "metadata/source-inventory.json").write_text(
        json.dumps({"complete": True, "files": files}), encoding="utf-8"
    )


def verify_archive(engine: Research, root: Path) -> Any:
    versions = {}
    for kind, content in [
        ("protocol", {"method": "Synthetic verification of event-uri-metadata-v1"}),
        ("selection", {"rules": "Every synthetic inventory record"}),
        ("question", {"text": "Which synthetic records contain a populated eventUri?"}),
    ]:
        versions[kind] = engine.execute(
            "version",
            {"kind": kind, "key": "legacy-test", "content": content},
            objective="Register synthetic archive check",
            actor="test",
        )["id"]
    return engine.execute(
        "verify_legacy",
        {"data_root": str(root)},
        versions=versions,
        objective="Verify synthetic eventUri metadata through audit runtime",
        actor="test",
    )


def test_event_uri_coverage_preserves_missingness_and_exact_values(engine: Research, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    make_archive(root)
    report = verify_archive(engine, root)
    summary = report["event_uri"]
    assert summary["denominator"] == report["article_records"] == 11
    assert summary["counts"] == {"populated": 4, "absent": 1, "null": 1, "empty": 2, "invalid_type": 3}
    assert summary["distinct_populated_values"] == 3
    assert [bundle["event_uri"]["distinct_populated_values"] for bundle in report["bundles"]] == [1, 3]
    for bundle in report["bundles"]:
        assert sum(bundle["event_uri"]["counts"].values()) == bundle["records"]
    assert engine.ledger.get(report["id"], "legacy_verification")["event_uri"] == summary
    # Diagnostic reports expose coverage, never the stored event identifiers.
    assert "event-a" not in json.dumps(report) and "event-b" not in json.dumps(report)


def test_event_uri_check_still_rejects_changed_archive(engine: Research, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    make_archive(root)
    path = root / "bundle-0.zip"
    raw = path.read_bytes()
    path.write_bytes(b"X" + raw[1:])
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_archive(engine, root)
    failures = engine.ledger.db.execute(
        "SELECT count(*) FROM events WHERE kind='operation.failed'"
    ).fetchone()[0]
    assert failures == 1


def pilot_versions(engine: Research, limit: int) -> dict[str, str]:
    definitions = {
        "protocol": {
            "method": "Synthetic pilot",
            "preparation_method": METHOD,
            "unavailable_retrieval_reason": RETRIEVAL_UNKNOWN,
        },
        "selection": {
            "rules": "Proportional largest-remainder cohorts and seeded SHA-256 rank",
            "method": METHOD,
            "limit": limit,
            "seed": "synthetic-seed",
        },
        "question": {"text": "Prepare source passages without event inference"},
        "profile": {"mode": "exploratory", "population_estimate": False},
    }
    return {
        kind: engine.execute(
            "version",
            {"kind": kind, "key": "synthetic-pilot-" + kind, "content": content},
            objective="Register synthetic pilot methods",
            actor="test",
        )["id"]
        for kind, content in definitions.items()
    }


def run_pilot(engine: Research, root: Path, versions: dict[str, str], limit: int = 11) -> Any:
    return engine.execute(
        "prepare_legacy_pilot",
        {"data_root": str(root), "limit": limit, "seed": "synthetic-seed", "retention": "permitted"},
        objective="Verify deterministic pilot source preparation",
        actor="test",
        versions=versions,
    )


def test_pilot_preserves_original_rows_passages_and_unknown_retrieval(
    engine: Research, tmp_path: Path
) -> None:
    root = tmp_path / "archive"
    make_archive(root, with_text=True)
    versions = pilot_versions(engine, 11)
    result = run_pilot(engine, root, versions)
    assert result["selected_records"] == 11 and result["excluded_records"] == 0
    assert result["missing_text_records"] == 2
    assert result["model_calls"] == engine.gateway.provider.calls == 0
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='dossiers'").fetchone()[0] == 0
    sources = {}
    for row in engine.ledger.db.execute("SELECT * FROM sources"):
        source = json.loads(row["payload"])
        sources[row["id"]] = source
        assert source["retrieval"]["retrieved_at"] is None
        assert source["retrieval"]["parameters"] is None
        assert source["published_at"] == "2020-01-01T00:00:00Z"
        assert "event_date" not in source
        locator = source["archive_provenance"]
        raw = engine.ledger.artifacts.read_bytes(source["original_artifact"])
        original = raw[locator["original_rows_start"] : locator["original_rows_end"]]
        assert hashlib.sha256(original).hexdigest() == locator["row_sha256"]
        assert json.loads(original)["article"] == source["raw_record"]
    count = 0
    for reference in result["chunk_artifacts"]:
        for chunk in engine.ledger.artifacts.read(reference):
            count += 1
            source = sources[chunk["source_version"]]
            assert source["body"][chunk["source_start"] : chunk["source_end"]] == chunk["text"]
            assert len(chunk["text"]) <= 1600
            assert hashlib.sha256(chunk["text"].encode()).hexdigest() == chunk["text_hash"]
    assert count == result["embedding_input_chunks"] > 0
    repeated = run_pilot(engine, root, versions)
    assert repeated["reused"] is True and repeated["id"] == result["id"]
    assert engine.ledger.db.execute("SELECT count(*) FROM sources").fetchone()[0] == 11
    engine.execute("status", objective="Check prepared evidence and audit", actor="test")


def test_pilot_selection_has_complete_disjoint_frame(engine: Research, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    make_archive(root)
    result = run_pilot(engine, root, pilot_versions(engine, 5), limit=5)
    assert result["cohort_quotas"] == {"synthetic-0": 4, "synthetic-1": 1}
    selected = engine.ledger.artifacts.read(result["selection_manifest"])
    excluded = engine.ledger.artifacts.read(result["exclusion_manifest"])
    selected_ids = {row["article_uri"] for row in selected}
    excluded_ids = {row["article_uri"] for row in excluded}
    assert len(selected_ids) == 5 and len(excluded_ids) == 6
    assert not selected_ids & excluded_ids
    assert len(selected_ids | excluded_ids) == result["frame_records"]
    for cohort, quota in result["cohort_quotas"].items():
        frame = [row for row in selected + excluded if row["cohort"] == cohort]
        frame.sort(
            key=lambda row: (
                digest({"seed": "synthetic-seed", "article_uri": row["article_uri"]}),
                row["article_uri"],
            )
        )
        assert {row["article_uri"] for row in frame[:quota]} <= selected_ids


def test_chunk_overlap_covers_unicode_without_changing_offsets() -> None:
    text = "x🧪é" * 1500
    passage = {"text": text, "source_id": "source", "id": "passage", "start": 7}
    items = list(chunks(passage))
    assert items[0]["source_start"] == 7 and items[-1]["source_end"] == 7 + len(text)
    for previous, current in zip(items, items[1:]):
        assert previous["source_end"] - current["source_start"] == 200
        assert previous["text"][-200:] == current["text"][:200]
    assert list(chunks({**passage, "text": " \n\t"})) == []
    assert allocate({"b": 1, "a": 1}, 1) == {"b": 0, "a": 1}


def test_pilot_requires_registered_selection_and_retention(engine: Research, tmp_path: Path) -> None:
    versions = pilot_versions(engine, 5)
    with pytest.raises(ResearchError, match="exactly match"):
        run_pilot(engine, tmp_path / "not-read", versions, limit=6)
    with pytest.raises(ResearchError, match="retention"):
        engine.execute(
            "prepare_legacy_pilot",
            {"limit": 5, "seed": "synthetic-seed", "retention": "metadata_only"},
            objective="Reject unsupported text retention",
            actor="test",
            versions=versions,
        )


def test_missing_prepared_chunk_fails_preflight(engine: Research, tmp_path: Path) -> None:
    root = tmp_path / "archive"
    make_archive(root, with_text=True)
    result = run_pilot(engine, root, pilot_versions(engine, 11))
    (engine.ledger.artifacts.root / result["chunk_artifacts"][0]).unlink()
    with pytest.raises(AuditError, match="artifact is missing"):
        engine.execute("status", objective="Detect missing prepared chunks", actor="test")


def test_unknown_retrieval_cannot_be_used_without_registered_reason(engine: Research) -> None:
    versions = pilot_versions(engine, 1)
    with pytest.raises(ResearchError, match="matching registered protocol"):
        engine.execute(
            "ingest",
            {
                "articles": [{"source_key": "test", "body": "Synthetic text", "retention": "permitted"}],
                "retrieval": {
                    "source": "test",
                    "retrieved_at": None,
                    "parameters": None,
                    "unavailable_reason": "invented",
                },
            },
            objective="Reject unregistered unknown retrieval",
            actor="test",
            versions=versions,
        )
