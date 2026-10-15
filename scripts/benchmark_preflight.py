"""Reproducible source-free engineering benchmark of complete audit verification.

Creates its synthetic fixture only through Research.execute. Verifier timing is
a software check against a frozen synthetic store, never a research measurement
or a production-store shortcut. OS caches are neither cleared nor called cold.
"""
from __future__ import annotations

import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import ModuleType

from newsresearch.common import Context, Json, ResearchError, canonical, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions, prepare_root

FIXTURE_METHOD = "synthetic-preflight-engineering-benchmark-v1"


def write_json(path: Path, value: Json) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        if os.name != "nt":
            path.chmod(0o600)
        stream.write(json.dumps(value, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    check_permissions(path)


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class FixtureResearch(Research):
    @audited_handler
    def _benchmark(self, session: str, context: Context, data: Json) -> Json:
        require_active(self, session)
        versions = {}
        for kind, content in {
            "protocol": {"method": FIXTURE_METHOD, "scope": "Software performance only; no scientific inference",
                "fixture_script_sha256": file_hash(Path(__file__))},
            "selection": {"rules": "All deterministically generated synthetic sources, paragraphs and diagnostic records"},
            "profile": {"mode": "exploratory", "population_estimate": False, "synthetic": True},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": FIXTURE_METHOD + "-" + kind,
                "content": content})["id"]
        bound = Context(context.objective, context.actor, versions)
        articles = []
        for i in range(data["sources"]):
            paragraphs = []
            for j in range(data["paragraphs"]):
                prefix = f"Synthetic engineering source {i:06d}, paragraph {j:03d}. "
                paragraphs.append(prefix + ("Deterministic fictional text for complete audit verification. " *
                    (data["paragraph_chars"] // 50 + 1))[:max(1, data["paragraph_chars"] - len(prefix))])
            body = "\n\n".join(paragraphs)
            articles.append({"source_key": f"synthetic-benchmark-{i:06d}", "title": f"Synthetic benchmark source {i}",
                "body": body, "retention": "permitted", "synthetic": True,
                "raw_record": {"fixture_id": i, "body": body}})
        dataset = self._ingest(session, bound, {"key": FIXTURE_METHOD, "articles": articles,
            "retrieval": {"source": "local deterministic synthetic engineering generator", "retrieved_at": utc(),
                "parameters": {"network": False, "method": FIXTURE_METHOD, **data}}})
        versions["dataset"] = dataset["id"]
        for i in range(data["records"]):
            self.ledger.record(session, "engineering_fixture_record", f"synthetic-{i:06d}", {
                "synthetic": True, "method": FIXTURE_METHOD, "versions": versions, "sequence": i,
                "source_version": dataset["sources"][i % len(dataset["sources"])],
                "diagnostic_payload": [f"value-{i}-{j}" for j in range(12)]})
        self.ledger.append(session, "engineering.fixture.completed", {"method": FIXTURE_METHOD,
            "synthetic": True, "sources": data["sources"], "records": data["records"]})
        return {"method": FIXTURE_METHOD, "synthetic": True, "versions": versions,
            "sources": data["sources"], "passages": data["sources"] * data["paragraphs"],
            "diagnostic_records": data["records"], "model_calls": 0, "network_calls": 0}


def create_fixture(root: Path, *, sources: int, paragraphs: int, records: int, paragraph_chars: int) -> Json:
    root = prepare_root(root)
    store = root / "fixture"
    if store.exists() or (root / "fixture-manifest.json").exists():
        raise ResearchError("Use a fresh engineering root; an existing fixture is immutable")
    if not 1 <= sources <= 20000 or not 1 <= paragraphs <= 100 or not 0 <= records <= 100000 or paragraph_chars < 80:
        raise ResearchError("Synthetic fixture sizes are outside the supported bounds")
    engine = FixtureResearch(store)
    try:
        result = engine.execute("benchmark", {"sources": sources, "paragraphs": paragraphs,
            "records": records, "paragraph_chars": paragraph_chars},
            objective="Create a registered source-free fixture for full audit verification engineering benchmarks",
            actor="codex:preflight-engineering-benchmark")
        counts = {table: engine.ledger.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("events", "records", "sources", "passages", "attempts", "accepted")}
        head = engine.ledger.db.execute("SELECT event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()[0]
    finally:
        engine.close()
    manifest = {**result, "store": str(store), "counts": counts, "head_hash": head,
        "database_sha256": file_hash(store / "research.sqlite3"),
        "artifact_count": sum(1 for _ in (store / "objects").iterdir()), "created_at": utc(),
        "fixture_script_sha256": file_hash(Path(__file__)),
        "limitations": "Synthetic software workload only; no production performance or scientific accuracy claim"}
    write_json(root / "fixture-manifest.json", manifest)
    return manifest


def fixture_manifest(root: Path) -> Json:
    root = prepare_root(root)
    manifest_path = root / "fixture-manifest.json"
    check_permissions(manifest_path)
    result = json.loads(manifest_path.read_text(encoding="utf-8"))
    if result.get("synthetic") is not True or result.get("method") != FIXTURE_METHOD or Path(result["store"]) != root / "fixture":
        raise ResearchError("Only this registered synthetic engineering fixture may be benchmarked")
    if file_hash(root / "fixture" / "research.sqlite3") != result["database_sha256"]:
        raise ResearchError("Frozen synthetic fixture database changed")
    return dict(result)


def load_storage(snapshot: Path | None) -> ModuleType:
    if snapshot is None:
        from newsresearch import storage
        return storage
    check_permissions(snapshot)
    name = "newsresearch._preflight_baseline_storage"
    specification = importlib.util.spec_from_file_location(name, snapshot)
    if specification is None or specification.loader is None:
        raise ResearchError("Cannot load the explicitly selected verifier snapshot")
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


def profile_counts(profile: cProfile.Profile) -> Json:
    counts = {"artifact_read_bytes_calls": 0, "artifact_verified_path_calls": 0,
        "permission_check_calls": 0, "windows_acl_reads": 0, "json_loads_calls": 0, "sqlite_execute_calls": 0}
    for entry in profile.getstats():
        code = entry.code
        if isinstance(code, str):
            if "'execute' of 'sqlite3.Connection'" in code:
                counts["sqlite_execute_calls"] += entry.callcount
            continue
        name, filename = code.co_name, code.co_filename.replace("\\", "/")
        if "storage" in filename and name in {"read_bytes", "verified_path", "check_permissions", "windows_sddl"}:
            key = {"read_bytes": "artifact_read_bytes_calls", "verified_path": "artifact_verified_path_calls",
                "check_permissions": "permission_check_calls", "windows_sddl": "windows_acl_reads"}[name]
            counts[key] += entry.callcount
        elif filename.endswith("json/__init__.py") and name == "loads":
            counts["json_loads_calls"] += entry.callcount
    return counts


def worker(root: Path, *, snapshot: Path | None, repeats: int, label: str, profile_enabled: bool = True) -> Json:
    if not label or not label.replace("-", "").replace("_", "").isalnum():
        raise ResearchError("Profile label must contain only letters, numbers, hyphens or underscores")
    manifest = fixture_manifest(root)
    module = load_storage(snapshot)
    implementation_file = module.__file__
    if implementation_file is None:
        raise ResearchError("Selected verifier has no observable implementation file")
    ledger = module.Ledger(root / "fixture")
    timings = []
    profile_path = None
    calls = None
    try:
        for _ in range(repeats):
            started = time.perf_counter()
            result = ledger.verify()
            timings.append(time.perf_counter() - started)
            if result["head_hash"] != manifest["head_hash"] or result["events"] != manifest["counts"]["events"]:
                raise ResearchError("Verifier result differs from the frozen synthetic journal")
        if profile_enabled:
            profile = cProfile.Profile()
            profile.runcall(ledger.verify)
            profile_path = root / f"{label}-{os.getpid()}.prof"
            profile.dump_stats(str(profile_path))
            if os.name != "nt":
                profile_path.chmod(0o600)
            check_permissions(profile_path)
            calls = profile_counts(profile)
    finally:
        ledger.close()
    fixture_manifest(root)
    return {"label": label, "implementation": implementation_file, "implementation_sha256": file_hash(Path(implementation_file)),
        "seconds": timings, "process_first_seconds": timings[0],
        "warm_seconds_median": statistics.median(timings[1:]) if len(timings) > 1 else None,
        "calls_in_separate_profiled_full_verification": calls, "profile": str(profile_path) if profile_path else None,
        "verified_events": result["events"], "verified_head_hash": result["head_hash"],
        "cache_state": "First call in a fresh worker process, then warm repeats; OS cache uncontrolled and not called cold"}


def compare(root: Path, *, snapshot: Path, repeats: int, order: list[str] | None = None,
            profile_enabled: bool = True) -> Json:
    started_at = utc()
    manifest = fixture_manifest(root)
    order = order or ["baseline", "current"]
    if not 2 <= len(order) <= 8 or set(order) != {"baseline", "current"}:
        raise ResearchError("Comparison order requires both baseline/current labels and 2 through 8 workers")
    rows = []
    for label in order:
        command = [sys.executable, str(Path(__file__).resolve()), "worker", "--root", str(root),
            "--repeats", str(repeats), "--label", label]
        if label == "baseline":
            command.extend(["--snapshot", str(snapshot)])
        if not profile_enabled:
            command.append("--no-profile")
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        rows.append(json.loads(completed.stdout))
    before = [row for row in rows if row["label"] == "baseline"]
    after = [row for row in rows if row["label"] == "current"]
    report = {"method": FIXTURE_METHOD, "synthetic": True, "fixture": manifest,
        "verifications": rows, "worker_order": order, "profile_enabled": profile_enabled,
        "process_first_speedup": statistics.median(r["process_first_seconds"] for r in before) /
            statistics.median(r["process_first_seconds"] for r in after),
        "warm_median_speedup": statistics.median(t for r in before for t in r["seconds"][1:]) /
            statistics.median(t for r in after for t in r["seconds"][1:]) if repeats > 1 else None,
        "started_at": started_at, "recorded_at": utc(), "model_calls": 0, "network_calls": 0,
        "limitations": "Declared sequential worker order; OS caches uncontrolled; synthetic workload cannot establish production speedup"}
    path = root / f"comparison-{time.time_ns()}.json"
    write_json(path, report)
    return {**report, "report_path": str(path)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["create", "compare", "worker"])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--sources", type=int, default=2000)
    parser.add_argument("--paragraphs", type=int, default=12)
    parser.add_argument("--records", type=int, default=4000)
    parser.add_argument("--paragraph-chars", type=int, default=640)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--label", default="current")
    parser.add_argument("--order", default="baseline,current")
    parser.add_argument("--no-profile", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 10:
        parser.error("Use 1 through 10 complete verification repeats")
    if args.operation == "create":
        result = create_fixture(args.root, sources=args.sources, paragraphs=args.paragraphs,
            records=args.records, paragraph_chars=args.paragraph_chars)
    elif args.operation == "worker":
        result = worker(args.root, snapshot=args.snapshot, repeats=args.repeats, label=args.label,
            profile_enabled=not args.no_profile)
    else:
        if args.snapshot is None:
            parser.error("Comparison requires the explicit unmodified verifier snapshot")
        result = compare(args.root, snapshot=args.snapshot, repeats=args.repeats,
            order=args.order.split(","), profile_enabled=not args.no_profile)
    print(canonical(result))


if __name__ == "__main__":
    main()
