"""Source-free engineering benchmark of the embedding gateway's exact SQL.

Only synthetic rows in an in-memory SQLite database are read or written. These
lookup timings do not measure research preflight, provider latency or a full run.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import random
import sqlite3
from statistics import median
from time import perf_counter
from typing import Any


TASK_SQL = (
    "SELECT max(CAST(json_extract(payload,'$.number') AS INTEGER)) FROM events "
    "WHERE kind='model.attempt.intended' AND json_extract(payload,'$.task_key')=?"
)
POLICY_SQL = (
    "SELECT payload FROM events WHERE kind='model.attempt.intended' "
    "AND json_extract(payload,'$.approval_policy')=?"
)
INTENTS = 25_000
UNRELATED = 75_000
TASKS = 20_000
POLICIES = 10


def declared_sql(root: Path) -> tuple[str, ...]:
    """Reject drift instead of benchmarking approximations of production SQL."""
    gateway = ast.parse((root / "src/newsresearch/embeddings.py").read_text(encoding="utf-8"))
    literals = {node.value for node in ast.walk(gateway) if isinstance(node, ast.Constant)
                and isinstance(node.value, str)}
    if TASK_SQL not in literals or POLICY_SQL not in literals:
        raise ValueError("Gateway SQL changed; update and review the benchmark before running")
    coordinator = ast.parse((root / "scripts/run_catalog_embeddings.py").read_text(encoding="utf-8"))
    definitions = [node.value for node in coordinator.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "INDEX_SQL"
                           for target in node.targets)]
    if len(definitions) != 1:
        raise ValueError("Expected exactly one coordinator INDEX_SQL declaration")
    indexes = ast.literal_eval(definitions[0])
    if not isinstance(indexes, tuple) or len(indexes) != 2 or not all(
        isinstance(value, str) for value in indexes
    ):
        raise ValueError("Expected the coordinator's two literal expression indexes")
    return indexes


def fixture(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE events (
            seq INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, session_id TEXT NOT NULL,
            kind TEXT NOT NULL, time TEXT NOT NULL, payload TEXT NOT NULL, previous_hash TEXT NOT NULL,
            event_hash TEXT UNIQUE NOT NULL
        );
        CREATE INDEX events_kind ON events(kind);
    """)

    def rows() -> Any:
        for seq in range(1, INTENTS + UNRELATED + 1):
            if seq % 4 == 0:
                ordinal = seq // 4 - 1
                kind = "model.attempt.intended"
                payload = {"task_key": f"synthetic-task-{ordinal % TASKS:05d}",
                           "number": str(ordinal // TASKS + 1),
                           "approval_policy": f"synthetic-policy-{ordinal % POLICIES:02d}",
                           "reserved_cost_usd": "0.0009", "batch": "synthetic-plan"}
            else:
                kind = ("model.attempt.completed", "operation.intended", "operation.completed")[seq % 3]
                payload = {"synthetic": True, "ordinal": seq, "status": "synthetic-only"}
            yield (seq, f"synthetic-event-{seq}", "synthetic-session", kind,
                   "2000-01-01T00:00:00Z", json.dumps(payload, sort_keys=True),
                   "synthetic-previous", f"synthetic-hash-{seq}")

    db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", rows())
    db.commit()


def lookups(db: sqlite3.Connection, sql: str, parameters: list[str]) -> list[list[tuple[Any, ...]]]:
    return [db.execute(sql, (parameter,)).fetchall() for parameter in parameters]


def measure(db: sqlite3.Connection, sql: str, parameters: list[str], repetitions: int,
            expected: list[list[tuple[Any, ...]]]) -> dict[str, Any]:
    if lookups(db, sql, parameters) != expected:
        raise AssertionError("Warm-up lookup results differ")
    elapsed = []
    for _ in range(repetitions):
        started = perf_counter()
        observed = lookups(db, sql, parameters)
        elapsed.append((perf_counter() - started) * 1000)
        if observed != expected:
            raise AssertionError("Timed lookup results differ")
    total = median(elapsed)
    return {"repetition_total_ms": elapsed, "median_total_ms": total,
            "median_per_lookup_ms": total / len(parameters)}


def benchmark(repetitions: int) -> dict[str, Any]:
    indexes = declared_sql(Path(__file__).resolve().parents[1])
    generator = random.Random(20261016)
    task_keys = [f"synthetic-task-{number:05d}" for number in generator.sample(range(TASKS), 225)]
    task_keys.extend(f"synthetic-missing-task-{number}" for number in range(25))
    generator.shuffle(task_keys)
    policy_keys = [f"synthetic-policy-{number:02d}" for number in range(POLICIES)]
    queries = {"task": (TASK_SQL, task_keys), "policy": (POLICY_SQL, policy_keys)}
    with sqlite3.connect(":memory:") as db:
        fixture(db)
        expected = {name: lookups(db, sql, parameters) for name, (sql, parameters) in queries.items()}
        before_plans = {name: [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + sql,
                                                            (parameters[0],))]
                        for name, (sql, parameters) in queries.items()}
        before = {name: measure(db, sql, parameters, repetitions, expected[name])
                  for name, (sql, parameters) in queries.items()}
        started = perf_counter()
        for statement in indexes:
            db.execute(statement)
        db.commit()
        build_ms = (perf_counter() - started) * 1000
        after_plans = {name: [row[3] for row in db.execute("EXPLAIN QUERY PLAN " + sql,
                                                           (parameters[0],))]
                       for name, (sql, parameters) in queries.items()}
        if not any("embedding_intent_task" in row for row in after_plans["task"]):
            raise AssertionError("SQLite did not select the task expression index")
        if not any("embedding_intent_policy" in row for row in after_plans["policy"]):
            raise AssertionError("SQLite did not select the policy expression index")
        after = {name: measure(db, sql, parameters, repetitions, expected[name])
                 for name, (sql, parameters) in queries.items()}
    return {
        "benchmark": "source-free-synthetic-embedding-intent-indexes-v1",
        "scope": "In-memory synthetic SQLite lookup timings only; no protected data or model calls",
        "limitations": "Does not measure preflight, artifact reads, API latency or full-run speedup",
        "sqlite_version": sqlite3.sqlite_version,
        "fixture": {"intent_events": INTENTS, "unrelated_events": UNRELATED,
                    "distinct_task_keys": TASKS, "policies": POLICIES,
                    "task_lookups": len(task_keys), "missing_task_lookups": 25,
                    "policy_lookups": len(policy_keys), "warmup_passes_per_phase": 1,
                    "timed_repetitions": repetitions},
        "exact_gateway_sql_verified": True,
        "sql": {"task": TASK_SQL, "policy": POLICY_SQL, "indexes": indexes},
        "identical_results": {"task": True, "policy": True},
        "query_plans": {"before": before_plans, "after": after_plans},
        "index_build_ms": build_ms,
        "before": before,
        "after": after,
        "median_lookup_speed_ratio": {
            name: before[name]["median_total_ms"] / after[name]["median_total_ms"]
            for name in queries
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, choices=range(1, 11), default=3)
    arguments = parser.parse_args()
    print(json.dumps(benchmark(arguments.repetitions), indent=2))


if __name__ == "__main__":
    main()
