"""Source-free engineering comparison of complete FTS projection checks.

Only generated fictional strings enter these temporary SQLite fixtures. This is
not a research measurement or a production-store inspection. Fixture creation,
index integrity checking and result writing are excluded from verifier timings.
No OS cache is flushed; alternating order reduces, but cannot remove, cache bias.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from typing import Any, Callable


def baseline_projection(db: sqlite3.Connection) -> None:
    """The existing full count and id-join checks, without FTS index internals."""
    if db.execute("SELECT count(*) FROM passage_fts").fetchone()[0] != db.execute(
        "SELECT count(*) FROM passages"
    ).fetchone()[0]:
        raise RuntimeError("Search index coverage differs from passages")
    if db.execute(
        "SELECT 1 FROM passage_fts f LEFT JOIN passages p ON p.id=f.id "
        "WHERE p.id IS NULL OR p.text != f.text LIMIT 1"
    ).fetchone():
        raise RuntimeError("Search index content differs from passages")


def create_fixture(path: Path, rows: int, characters: int) -> dict[str, Any]:
    """Insert unique hashed IDs in generation order, not primary-key order."""
    db = sqlite3.connect(path)
    try:
        db.executescript(
            "CREATE TABLE passages(id TEXT PRIMARY KEY, text TEXT NOT NULL);"
            "CREATE VIRTUAL TABLE passage_fts USING fts5(id UNINDEXED,text);"
        )
        content = hashlib.sha256()
        for number in range(rows):
            identifier = hashlib.sha256(f"fictional-fts-{number}".encode()).hexdigest()
            prefix = f"Constructed engineering paragraph {number:09d}. "
            text = prefix + ("Fictional generated text for complete FTS projection verification. " *
                (characters // 50 + 1))[:characters - len(prefix)]
            content.update(identifier.encode())
            content.update(text.encode())
            db.execute("INSERT INTO passages(id,text) VALUES (?,?)", (identifier, text))
            db.execute("INSERT INTO passage_fts(id,text) VALUES (?,?)", (identifier, text))
        db.commit()
        db.execute("INSERT INTO passage_fts(passage_fts) VALUES('integrity-check')")
        db.commit()
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise RuntimeError("Constructed fixture failed SQLite integrity checking")
        return {"rows": rows, "text_characters_per_row": characters,
            "generated_id_text_sha256": content.hexdigest(), "database_bytes": path.stat().st_size,
            "insertion_order": "generation order; IDs are unique SHA-256 values",
            "synthetic": True, "network_calls": 0, "model_calls": 0}
    finally:
        db.close()


def benchmark_fixture(path: Path, *, cache_mib: int, repeats: int,
                      current: Callable[[sqlite3.Connection], None]) -> dict[str, Any]:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        db.execute(f"PRAGMA cache_size={-cache_mib * 1024}")
        observations: list[dict[str, Any]] = []
        methods = {"baseline": baseline_projection, "current": current}
        for repetition in range(repeats):
            order = ["baseline", "current"] if repetition % 2 == 0 else ["current", "baseline"]
            for name in order:
                started = time.perf_counter()
                methods[name](db)
                observations.append({"method": name, "repetition": repetition,
                    "seconds": time.perf_counter() - started, "status": "passed"})
        medians = {name: statistics.median(item["seconds"] for item in observations
            if item["method"] == name) for name in methods}
        return {"sqlite_cache_mib_requested": cache_mib,
            "sqlite_cache_size_observed": db.execute("PRAGMA cache_size").fetchone()[0],
            "observations": observations, "median_seconds": medians,
            "median_speed_ratio_baseline_over_current": medians["baseline"] / medians["current"],
            "cache_boundary": "Fresh SQLite connection per cache setting; same connection per alternating pass; OS cache uncontrolled",
            "timed_boundary": "Complete projection coverage/content checks only; FTS internal integrity-check excluded from both"}
    finally:
        db.close()


def integers(value: str) -> list[int]:
    try:
        result = [int(item) for item in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected comma-separated integers") from error
    if not result or any(item < 1 for item in result):
        raise argparse.ArgumentTypeError("All fixture sizes must be positive")
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=integers, default=[2000, 100000])
    parser.add_argument("--characters", type=int, default=512)
    parser.add_argument("--caches-mib", type=integers, default=[2, 64])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10 or not 80 <= args.characters <= 4096 or max(args.rows) > 200000:
        parser.error("Use 1–10 repeats, 80–4096 characters and at most 200000 fixture rows")
    from newsresearch.preflight_fts import verify_projection

    reports = []
    with tempfile.TemporaryDirectory(prefix="newsresearch-fts-engineering-") as directory:
        root = Path(directory).resolve()
        if any((parent / ".git").exists() for parent in [root, *root.parents]):
            raise RuntimeError("Synthetic working databases must remain outside Git")
        for count in args.rows:
            path = root / f"synthetic-{count}.sqlite3"
            fixture = create_fixture(path, count, args.characters)
            reports.append({"fixture": fixture, "comparisons": [benchmark_fixture(path,
                cache_mib=cache, repeats=args.repeats, current=verify_projection)
                for cache in args.caches_mib]})
    report = {"method": "synthetic-full-fts-projection-engineering-v1", "synthetic": True,
        "python": sys.version, "sqlite": sqlite3.sqlite_version, "platform": platform.platform(),
        "repeats_per_method": args.repeats, "reports": reports, "model_calls": 0, "network_calls": 0,
        "limitations": ["Synthetic projection performance does not establish production or total-preflight speed.",
            "OS caches and competing machine activity are uncontrolled; no observation is called cold.",
            "Baseline is the historical count/join check; current also rejects duplicate/missing FTS IDs.",
            "Fixture databases are temporary and removed after comparison; report contains no real sources."]}
    rendered = json.dumps(report, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
