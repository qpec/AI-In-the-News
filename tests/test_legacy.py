from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

import pytest

from newsresearch.runtime import Research


def make_archive(root: Path) -> None:
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
            {"collection_cohort": cohort, "article": {"uri": f"{index}-{number}", **article}}
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
                "met_tekst": 0,
                "zonder_tekst": len(rows),
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
