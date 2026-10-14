#!/usr/bin/env python3
"""Verify the private source inventory and article bundles without extracting them."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile
from .common import Json


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def within(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Path is outside the data repository: {relative}")
    return path


def verify(data_root: Path) -> Json:
    inventory = json.loads((data_root / "metadata/source-inventory.json").read_text(encoding="utf-8"))
    if not inventory.get("complete") or inventory.get("pending"):
        raise ValueError("The source import is incomplete.")
    files = inventory["files"]
    paths = [entry["path"] for entry in files]
    if len(paths) != len(set(paths)):
        raise ValueError("Duplicate paths in the source inventory.")
    for entry in files:
        path = within(data_root, entry["path"])
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Missing file or incorrect size: {entry['path']}")
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"SHA-256 mismatch: {entry['path']}")
    print(f"Verified {len(files)} source file checksums.", flush=True)

    bundles = [entry for entry in files if entry["kind"] == "article-bundle"]
    upstream_paths = [
        entry
        for entry in files
        if entry["kind"] == "upstream-manifest" and Path(entry["path"]).name == "bestand_manifest.json"
    ]
    if len(upstream_paths) != 1:
        raise ValueError("Expected one upstream article manifest.")
    upstream = json.loads(within(data_root, upstream_paths[0]["path"]).read_text(encoding="utf-8-sig"))
    expected = {entry["bestand"]: entry for entry in upstream if "deelcollectie" in entry}
    if {Path(entry["path"]).name for entry in bundles} != set(expected):
        raise ValueError("The imported article bundles differ from the upstream manifest.")

    seen = set()
    duplicates = 0
    bundle_reports = []
    totals: Counter[str] = Counter()
    languages: Counter[str] = Counter()
    for entry in sorted(bundles, key=lambda item: item["path"]):
        name = Path(entry["path"]).name
        declared = expected[name]
        if entry["sha256"] != declared["sha256"]:
            raise ValueError(f"Inventory differs from the upstream checksum: {name}")
        counts: Counter[str] = Counter()
        with zipfile.ZipFile(within(data_root, entry["path"])) as archive:
            with archive.open("artikelen.jsonl") as stream:
                for line_number, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    article = row.get("article")
                    if not isinstance(article, dict) or not article.get("uri"):
                        raise ValueError(f"Missing article identifier: {name}, line {line_number}")
                    if row.get("collection_cohort") != declared["deelcollectie"]:
                        raise ValueError(f"Incorrect cohort: {name}, line {line_number}")
                    identifier = str(article["uri"])
                    duplicates += identifier in seen
                    seen.add(identifier)
                    counts["records"] += 1
                    body = article.get("body")
                    counts["with_text" if isinstance(body, str) and body.strip() else "without_text"] += 1
                    languages[str(article.get("lang") or "missing")] += 1
        for actual_key, expected_key in [
            ("records", "records"),
            ("with_text", "met_tekst"),
            ("without_text", "zonder_tekst"),
        ]:
            if counts[actual_key] != declared[expected_key]:
                raise ValueError(
                    f"{actual_key} differs from upstream manifest for {name}: {counts[actual_key]} != {declared[expected_key]}"
                )
        totals.update(counts)
        bundle_reports.append({"path": entry["path"], "cohort": declared["deelcollectie"], **dict(counts)})
        print(f"{name}: {counts['records']} records verified.", flush=True)
    if duplicates:
        raise ValueError(f"Found {duplicates} duplicate article identifiers across bundles.")

    return {
        "status": "passed",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "unit": "article records; not validated incidents",
        "source_files": len(files),
        "source_bytes": sum(entry["bytes"] for entry in files),
        "article_bundles": len(bundles),
        "article_records": totals["records"],
        "unique_article_ids": len(seen),
        "duplicate_article_ids": duplicates,
        "with_text": totals["with_text"],
        "without_text": totals["without_text"],
        "languages": dict(languages),
        "bundles": bundle_reports,
    }
