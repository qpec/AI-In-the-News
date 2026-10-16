"""Compose ten approved gateway plans without changing their frozen source code.

The subclass extends only the embed handler. Research.execute, its full preflight,
durable intent, active-session enforcement and the original gateway are retained.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from decimal import Decimal, ROUND_DOWN
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, default_workspace, digest
from newsresearch.runtime import Research, audited_handler

MASTER = "be949c88e4be39394612b7677e8c3e0b2396b341649969a7835b5d1c28332abc"
KEY = "full-catalog-embedding-execution-20261016-v1"
CAP = Decimal("25")
EXPIRY = "2026-10-23T23:59:59Z"
MIN_FREE = 65 * 1024**3
SCOPE = (10, 185529, 24902)
INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS embedding_intent_task ON events(json_extract(payload,'$.task_key')) WHERE kind='model.attempt.intended'",
    "CREATE INDEX IF NOT EXISTS embedding_intent_policy ON events(json_extract(payload,'$.approval_policy')) WHERE kind='model.attempt.intended'",
)


def allocate(costs: list[Decimal], cap: Decimal) -> list[Decimal]:
    if not costs or any(not c.is_finite() or c <= 0 for c in costs) or not cap.is_finite() or cap < sum(costs):
        raise ResearchError("The combined cap must cover all positive planned costs")
    total = sum(costs)
    values = [(cap * c / total).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN) for c in costs]
    values[-1] += cap - sum(values)
    if any(v < c for v, c in zip(values, costs, strict=True)):
        raise ResearchError("A child cap does not cover its planned workload")
    return values


def observe_progress(engine: Research) -> None:
    original = engine.ledger.append
    completed = 0

    def append(session: str, kind: str, payload: Json, projection: Any = None) -> int:
        nonlocal completed
        if kind == "model.attempt.intended" and shutil.disk_usage(engine.ledger.root).free < MIN_FREE:
            raise ResearchError("Storage reserve reached before dispatch; retain all completed results")
        event = original(session, kind, payload, projection)
        if kind == "model.attempt.completed":
            completed += 1
            if completed == 1 or completed % 25 == 0 or payload["status"] != "valid":
                print(json.dumps({"stage": "embedding_progress", "completed_this_process": completed,
                    "status": payload["status"], "http_status": payload.get("http_status")}), flush=True)
        return event

    setattr(engine.ledger, "append", append)


class CatalogExecution(Research):
    def identity(self) -> Json:
        value = super().identity()
        value["code_files"]["scripts/run_catalog_embeddings.py"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        value["code_digest"] = digest(value["code_files"])
        return value

    @audited_handler
    def _embed(self, session: str, context: Context, data: Json) -> Json:
        if set(data) != {"catalog_plan", "allow_paid_execution"} or data != {"catalog_plan": MASTER, "allow_paid_execution": True}:
            raise ResearchError("This coordinator accepts only the specifically approved master plan")
        master = self.ledger.get(MASTER, "catalog_embedding_plan_result")
        batches = master["batches"]
        if (len(batches), master["articles"], master["requests"]) != SCOPE:
            raise AuditError("The authorized full-corpus scope differs")
        implementation = digest({k: v for k, v in self.identity()["code_files"].items() if k.startswith("src/") or k == "uv.lock"})
        if implementation != master["implementation_digest"]:
            raise ResearchError("Use the frozen executable source code; paid plans were not refreshed")
        costs = [Decimal(batch["estimated_cost_usd"]) for batch in batches]
        budgets = allocate(costs, CAP)
        script = Path(__file__).read_bytes()
        script_ref = self.ledger.artifacts.put_bytes(script)
        self.ledger.append(session, "preparation.artifact.saved", {"artifact": script_ref, "purpose": "Exact registered paid coordinator extension"})
        declaration = {"method": "full-catalog-authorized-embedding-execution-v1", "master": MASTER,
            "plans": [b["plan"] for b in batches], "implementation_digest": implementation,
            "coordinator_artifact": script_ref, "combined_estimated_cap_usd": str(CAP),
            "child_caps_usd": [str(v) for v in budgets], "expires_at": EXPIRY,
            "expiry_basis": "Operator-selected seven-day narrowing, not a user-specified expiry",
            "approval": {"approved_by": "user:ynhan", "reply": "yes",
                "question": "May I execute all 10 plans through OpenAI with a combined $25 estimated-cost cap?",
                "chat_timestamp": None, "timestamp_basis": "Exact chat time unobserved; journal records receipt time"},
            "external_processing": True, "transport": "Original audited shared gateway, unchanged request bodies/model/profile",
            "resume": "Same master, ordered plans, script, policy IDs and cumulative reservations; no automatic retries",
            "scope": "Retrieval representations only; no event acceptance, judging, new collection or membership changes",
            "storage_reserve_bytes": MIN_FREE, "performance_indexes": list(INDEX_SQL)}
        previous = self.ledger.db.execute("SELECT id FROM records WHERE kind='catalog_embedding_authorization' AND logical_key=?", (KEY,)).fetchone()
        if previous and self.ledger.get(previous[0], "catalog_embedding_authorization") != declaration:
            raise ResearchError("Execution lineage changed; do not reset approval or spend")
        protocol = self._version(session, context, {"kind": "protocol", "key": KEY, "content": {"method": declaration}})["id"]
        authorization = self.ledger.record(session, "catalog_embedding_authorization", KEY, declaration)
        policies = []
        for i, (batch, budget) in enumerate(zip(batches, budgets, strict=True)):
            planned = self.ledger.get(batch["plan"], "embedding_plan")
            if planned["versions"] != batch["plan_versions"] or planned["implementation_digest"] != implementation:
                raise AuditError("Child plan versions or code differ from authorized preparation")
            for kind, ref in planned["versions"].items():
                self.ledger.get(ref, kind)
            policy = self._version(session, context, {"kind": "policy", "key": KEY + f"-{i:03d}", "content": {
                "method": "embedding-run-approval-v1", "plan": batch["plan"], "approved_by": "user:ynhan",
                "allow_external_processing": True, "allow_paid_inference": True,
                "max_estimated_cost_usd": str(budget), "expires_at": EXPIRY,
                "parent_authorization": authorization, "combined_cap_usd": str(CAP)}})["id"]
            policies.append(policy)
            # A different policy for the same plan must not hide historical reservations.
            other = self.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.batch')=? AND json_extract(payload,'$.approval_policy') IS NOT ?", (batch["plan"], policy)).fetchone()[0]
            if other:
                raise ResearchError("Another policy already reserved spend for this plan; reconcile rather than reset")
        manifest = self.ledger.record(session, "catalog_embedding_execution_manifest", KEY,
            {"approval_record": authorization, "protocol": protocol, "master": MASTER,
             "policies": policies, "plans": [b["plan"] for b in batches], "child_caps_usd": [str(v) for v in budgets]})
        self.ledger.append(session, "catalog_embedding.execution.intended", {"manifest": manifest, "approval_record": authorization})
        for sql in INDEX_SQL:
            self.ledger.append(session, "engineering.index.intended", {"sql": sql, "reason": "Accelerate unchanged per-attempt gateway audit lookups"})
            self.ledger.db.execute(sql)
            self.ledger.append(session, "engineering.index.completed", {"sql": sql})
        runs = []
        stop_reason = None
        for i, (batch, policy) in enumerate(zip(batches, policies, strict=True)):
            print(json.dumps({"stage": "batch_started", "batch": i, "articles": batch["articles"], "requests": batch["requests"], "child_budget_usd": str(budgets[i])}), flush=True)
            bound = Context(context.objective, context.actor, batch["plan_versions"])
            planned = self.ledger.get(batch["plan"], "embedding_plan")
            task_keys = {item["task_key"] for item in planned["items"]}
            states = {row["task_key"]: row["status"] for row in self.ledger.db.execute(
                "SELECT task_key,status FROM attempts WHERE batch_id=? ORDER BY number", (batch["plan"],))}
            if any(v["task_key"] in task_keys for v in self.ledger.unresolved.values()):
                stop_reason = "previous_unknown_outcome_requires_explicit_resolution"
                break
            if any(v != "valid" for v in states.values()):
                stop_reason = "previous_failed_attempt_requires_explicit_retry_review"
                break
            try:
                run = super()._embed(session, bound, {"plan": batch["plan"], "approval_policy": policy, "max_requests": batch["requests"]})
            except AuditError:
                raise
            except ResearchError as error:
                self.ledger.append(session, "catalog_embedding.batch.stopped", {"plan": batch["plan"], "error_type": type(error).__name__})
                stop_reason = "gateway_stopped_with_unknown_outcome" if any(v["task_key"] in task_keys for v in self.ledger.unresolved.values()) else "gateway_stopped_before_completion"
                break
            record = {"batch": batch["id"], "plan": batch["plan"], "run": run["id"],
                "articles": batch["articles"], "completed_chunks": run["completed_chunks"],
                "expected_chunks": run["expected_chunks"], "requests_sent": run["requests_sent"],
                "missing_requests": len(run["missing_task_keys"]), "reserved_cost_usd": run["reserved_cost_usd"]}
            runs.append(record)
            self.ledger.record(session, "catalog_embedding_execution_checkpoint", KEY + f"-{i:03d}", record)
            print(json.dumps({"stage": "batch_completed", **record}), flush=True)
            if run["missing_task_keys"]:
                stop_reason = "partial_gateway_result_requires_review"
                break
        reserved = sum((Decimal(json.loads(row[0])["reserved_cost_usd"]) for row in self.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.approval_policy') IN (" + ",".join("?" for _ in policies) + ")", policies)), Decimal(0))
        if reserved > CAP:
            raise AuditError("Combined policy reservation exceeded the registered cap")
        coverage = []
        for batch in batches:
            planned = self.ledger.get(batch["plan"], "embedding_plan")
            states = {row["task_key"]: row["status"] for row in self.ledger.db.execute(
                "SELECT task_key,status FROM attempts WHERE batch_id=? ORDER BY number", (batch["plan"],))}
            unknown = {v["task_key"] for v in self.ledger.unresolved.values()}
            counts = {"valid": 0, "failed": 0, "unknown": 0, "pending": 0}
            completed_chunks = 0
            for item in planned["items"]:
                status = "unknown" if item["task_key"] in unknown else "valid" if states.get(item["task_key"]) == "valid" else "failed" if item["task_key"] in states else "pending"
                counts[status] += 1
                if status == "valid":
                    completed_chunks += item["chunks"]
            if counts["valid"] == len(planned["items"]):
                complete_articles = batch["articles"]
            elif not counts["valid"]:
                complete_articles = 0
            else:
                good: set[str] = set()
                missing: set[str] = set()
                for item in planned["items"]:
                    request = self.ledger.artifacts.read(item["request_ref"])
                    target = good if states.get(item["task_key"]) == "valid" and item["task_key"] not in unknown else missing
                    target.update(c["source_version"] for c in request["chunks"])
                completed_sources = sorted(good - missing)
                ref = self.ledger.artifacts.put(completed_sources)
                self.ledger.append(session, "preparation.artifact.saved", {"artifact": ref, "purpose": "Exact fully embedded source IDs in a partial batch"})
                complete_articles = len(completed_sources)
            coverage.append({"plan": batch["plan"], "requests": counts, "completed_chunks": completed_chunks,
                "completed_articles": complete_articles, "expected_articles": batch["articles"]})
        totals = {kind: sum(c["requests"][kind] for c in coverage) for kind in ("valid", "failed", "unknown", "pending")}
        value = {"versions": master["versions"], "method_version": protocol, "approval_record": authorization,
            "manifest": manifest, "master": MASTER, "runs": runs, "expected_articles": master["articles"],
            "coverage": coverage, "request_totals": totals, "stop_reason": stop_reason,
            "completed_articles": sum(c["completed_articles"] for c in coverage),
            "completed_chunks": sum(c["completed_chunks"] for c in coverage), "expected_chunks": master["chunks"],
            "reserved_estimated_cost_usd": str(reserved), "cap_usd": str(CAP),
            "status": "complete" if totals["valid"] == master["requests"] else "partial",
            "scope": "Embeddings only; no accepted events or changed memberships", "provider_invoice": "unobserved"}
        # Reuse the existing supported representation-checkpoint result kind.
        identifier = self.ledger.record(session, "embedding_checkpoint_result", KEY, value)
        markdown = "\n".join(["Full-corpus embedding execution result", "",
            f"Status: {value['status']}. Fully completed article versions: {value['completed_articles']:,}/{value['expected_articles']:,}; exact chunks: {value['completed_chunks']:,}/{value['expected_chunks']:,}.",
            f"Requests valid/failed/unknown/pending: {totals['valid']:,}/{totals['failed']:,}/{totals['unknown']:,}/{totals['pending']:,}. Stop reason: {stop_reason or 'none'}.",
            f"Completed bounded plans: {sum(c['completed_articles'] == c['expected_articles'] for c in coverage)}/{len(batches)}. Estimated cost reserved across all attempts: USD{reserved}, within the USD25 cap; final invoice unobserved.",
            "Original compatible vectors and seven-day groups remain unchanged. New embeddings still require local indexing before search. Embedding completion does not establish event-grouping accuracy."])
        presentation = self._record_presentation(session, Context(context.objective, context.actor, master["versions"]),
            {"results": [{"kind": "embedding_checkpoint_result", "id": identifier}], "markdown": markdown,
             "destination": "codex_chat", "status": "prepared_for_delivery"})
        return {"id": identifier, **value, "presentation": presentation}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=default_workspace())
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("The explicit user-approved paid execution switch is required")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    project = Path(__file__).resolve().parents[1]
    engine = CatalogExecution(args.workspace, project=project, config=replace(Config.load(project / "research.toml"), offline=False))
    observe_progress(engine)
    try:
        print(json.dumps({"stage": "full_audit_preflight", "master": MASTER, "cap_usd": str(CAP)}), flush=True)
        result = engine.execute("embed", {"catalog_plan": MASTER, "allow_paid_execution": True},
            objective="Execute all ten explicitly authorized full-corpus OpenAI embedding plans under one combined USD25 estimated cap",
            actor="codex:full-corpus-embedding-execution")
        print(result["presentation"]["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "status": result["status"], "presentation": result["presentation"]["content_path"]}), flush=True)
        return 0 if result["status"] == "complete" else 2
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
