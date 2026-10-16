"""Source-free engineering comparison of complete reordered FTS verification.

Direct SQL constructs fictional data only. This is not a research operation or
a full-preflight benchmark; no production workspace is opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import time
from typing import Any

from newsresearch.preflight_fts import verify_projection
from newsresearch.storage import check_permissions, prepare_root


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def text(seed: str, number: int, size: int) -> tuple[str, str]:
    identifier = hashlib.sha256(f"{seed}/{number}".encode()).hexdigest()
    prefix = f"Constructed fictional passage {number}; identifier {identifier}; café. "
    remaining = size - len(prefix.encode("utf-8"))
    fill = ("Fictional fixture text only. " * (remaining // 27 + 2))[:remaining]
    return identifier, prefix + fill


def create(path: Path, passages: int, text_bytes: int, seed: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    check_permissions(path)
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE passages(id TEXT PRIMARY KEY,text TEXT NOT NULL)")
        db.execute("CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text)")
        db.executemany("INSERT INTO passages VALUES (?,?)", (text(seed, i, text_bytes) for i in range(passages)))
        db.executemany("INSERT INTO passage_fts(id,text) VALUES (?,?)",
            (text(seed, i, text_bytes) for i in reversed(range(passages))))
        db.execute("INSERT INTO passage_fts(passage_fts) VALUES('integrity-check')")
        db.execute("COMMIT")
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Private, empty engineering directory outside Git")
    parser.add_argument("--passages", type=int, default=10000)
    parser.add_argument("--text-bytes", type=int, default=8192)
    parser.add_argument("--cache-kib", type=int, default=2048)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--seed", default="fictional-fts-hash-benchmark-v1")
    args = parser.parse_args()
    if not 2 <= args.passages <= 50000 or not 256 <= args.text_bytes <= 65536:
        parser.error("Use 2–50,000 fictional passages of 256–65,536 UTF-8 bytes")
    if not 64 <= args.cache_kib <= 65536 or not 1 <= args.repetitions <= 6:
        parser.error("Use 64–65,536 KiB main SQLite cache and 1–6 alternating repetitions")
    from newsresearch.preflight_fts_hashes import verify_hashes

    root = prepare_root(args.root)
    if any(root.iterdir()):
        parser.error("Use an empty private directory; existing fixtures are never replaced")
    database = root / "fictional-fts.sqlite3"
    build_start = time.perf_counter()
    create(database, args.passages, args.text_bytes, args.seed)
    build_seconds = time.perf_counter() - build_start
    before = file_hash(database)
    runs: list[dict[str, Any]] = []
    for repetition in range(args.repetitions):
        order = ["content_join", "compact_hash"] if repetition % 2 == 0 else ["compact_hash", "content_join"]
        for label in order:
            db = sqlite3.connect(database)
            try:
                db.execute(f"PRAGMA cache_size=-{args.cache_kib}")
                scratch = prepare_root(root / f"scratch-{len(runs)}") if label == "compact_hash" else None
                started = time.perf_counter()
                if label == "content_join":
                    result = verify_projection(db)
                    if result.get("fallback") is not True:
                        raise RuntimeError("Fixture did not exercise the complete reordered content join")
                else:
                    assert scratch is not None
                    result = verify_hashes(db, scratch_root=scratch)
                seconds = time.perf_counter() - started
                if result["rows"] != args.passages:
                    raise RuntimeError("Complete verification did not cover every fictional passage")
                row = {"method": label, "repetition": repetition, "seconds": seconds,
                    "verified_rows": result["rows"], "metadata": result,
                    "expected_full_text_bytes": 2 * args.passages * args.text_bytes}
                runs.append(row)
                print(json.dumps({"stage": "verification_completed", **row}), flush=True)
            finally:
                db.close()
    after = file_hash(database)
    if before != after:
        raise RuntimeError("The frozen fictional database changed during read verification")
    medians = {label: statistics.median(row["seconds"] for row in runs if row["method"] == label)
               for label in ("content_join", "compact_hash")}
    report = {"method": "fictional-reordered-fts-hash-comparison-v1", "synthetic": True,
        "passages": args.passages, "text_bytes_per_row": args.text_bytes,
        "database_bytes": database.stat().st_size, "database_sha256_before": before,
        "database_sha256_after": after, "database_unchanged": True, "fixture_build_seconds": build_seconds,
        "main_sqlite_cache_kib": args.cache_kib, "compact_hash_scratch_cache_kib": 65536,
        "calls_per_method": args.repetitions, "runs": runs, "median_seconds": medians,
        "median_speedup": medians["content_join"] / medians["compact_hash"],
        "internal_fts_integrity_check": "Performed once during fixture construction; excluded from timed methods",
        "model_calls": 0, "network_calls": 0,
        "limitations": "Source-free software comparison only; fresh SQLite connections, OS caches uncontrolled. "
            "Compact scratch cache is 64 MiB versus the declared main cache. Expected text bytes are logical payload, "
            "not observed disk traffic. Neither timing includes complete runtime preflight or artifact/source checks."}
    report_path = root / "comparison.json"
    with report_path.open("x", encoding="utf-8", newline="\n") as stream:
        if os.name != "nt":
            report_path.chmod(0o600)
        stream.write(json.dumps(report, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    check_permissions(report_path)
    print(json.dumps({**report, "report_path": str(report_path)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
