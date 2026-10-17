"""Audited download, validation and conservative cost settlement of saved jobs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import uuid

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, utc
from newsresearch.event_batch_budget import UsageReceipt
from newsresearch.event_batch_live_gateway import RECEIPT_KIND
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import ExecutionResearch, JOB_KIND, MANIFEST_KIND, PLAN_KIND, TERMINAL, require_receipt
from luna_batch_budget_run import OWNER, STUDY, present, save
from luna_batch_results import parse_batch_results
import luna_event_contract_v2 as contract

ASSESSMENT_KIND = "luna_budget_assessment"
PARSE_KIND = "luna_budget_job_parsed"


class ReconciliationResearch(ExecutionResearch):
    def reconcile(self, session: str, plan_id: str, policy: str, job: Json) -> Json:
        manifest_id = job["manifest"]
        old = self.latest("luna_budget_job_reconciled", manifest_id)
        if old:
            return old[1]
        manifest = self.ledger.get(manifest_id, MANIFEST_KIND)
        prior_parse = self.latest(PARSE_KIND, manifest_id)
        if prior_parse:
            parse_checkpoint = prior_parse[1]
            if parse_checkpoint["plan"] != plan_id or parse_checkpoint["job_id"] != job["job_id"]:
                raise AuditError("batch_parsed_job_identity_changed")
            status, parsed_ref = parse_checkpoint["status"], parse_checkpoint["parsed_result"]
            parsed = self.ledger.artifacts.read(parsed_ref)
            self.ledger.append(session, "batch.parsed_result.reused", {
                "record": prior_parse[0], "parsed_result": parsed_ref, "exact_version_bound_reuse": True})
        else:
            receipt = self.action(session, plan_id, policy, "poll:" + job["job_id"] + ":" + str(uuid.uuid4()),
                {"method": "GET", "path": "/v1/batches/" + job["job_id"]})
            answer = require_receipt(receipt, self)
            created = require_receipt(self.ledger.get(job["receipt"], RECEIPT_KIND), self)
            if (answer.get("id") != job["job_id"] or answer.get("metadata") != created.get("metadata")
                    or answer.get("input_file_id") != created.get("input_file_id")
                    or answer.get("endpoint") != "/v1/responses"
                    or answer.get("completion_window") != "24h"):
                raise ResearchError("batch_poll_identity_mismatch")
            status = answer.get("status")
            self.ledger.record(session, "luna_budget_job_observation", job["job_id"], {
                "plan": plan_id, "job_id": job["job_id"], "receipt": receipt["id"], "status": status,
                "request_counts": answer.get("request_counts"), "observed_at": utc()})
            if status not in TERMINAL:
                return {"job_id": job["job_id"], "status": status, "reconciled": False}
            files: dict[str, bytes] = {}
            file_receipts = {}
            for name in ("output_file_id", "error_file_id"):
                file_id = answer.get(name)
                if not file_id:
                    files[name] = b""
                    continue
                download = self.action(session, plan_id, policy, "download:" + file_id,
                    {"method": "GET", "path": "/v1/files/" + file_id + "/content"})
                if download.get("unknown") or download.get("status") != 200 or not download.get("body_ref"):
                    raise ResearchError("batch_download_unavailable")
                files[name] = self.ledger.artifacts.read_bytes(download["body_ref"])
                file_receipts[name] = download["id"]
            tasks = {task["custom_id"]: {"packet": self.ledger.artifacts.read(task["packet_ref"]),
                "body": self.ledger.artifacts.read(task["request_body_ref"])} for task in manifest["tasks"]}
            # The parser is pure; all provider bytes above have already been retained.
            parsed = parse_batch_results(files["output_file_id"], files["error_file_id"], tasks)
            parsed_ref = save(self, session, parsed, "Batch output parsing before provisional result projection")
            self.ledger.record(session, PARSE_KIND, manifest_id, {"plan": plan_id, "job_id": job["job_id"],
                "manifest": manifest_id, "status": status, "parsed_result": parsed_ref,
                "execution_protocol": self.execution_protocol, "poll_receipt": receipt["id"],
                "download_receipts": file_receipts, "parsed_at": utc()})
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("batch_reconciliation_budget_missing")
        book, state = saved
        joined = {row["custom_id"]: row for row in parsed["items"]}
        for task in manifest["tasks"]:
            row = joined[task["custom_id"]]
            usage = row.get("usage") or {}
            raw_ref = save(self, session, row, "Exact parsed per-request receipt with raw line provenance")
            complete = row.get("usage_complete") is True
            receipt_usage = UsageReceipt(input_tokens=usage.get("input_tokens") if complete else None,
                output_tokens=usage.get("output_tokens") if complete else None,
                model=row.get("observed_model"), request_sha256=task["request_body_ref"],
                receipt_sha256=raw_ref, complete=complete, provider_request_id=row.get("provider_request_id"))
            book.settle(task["custom_id"], receipt_usage)
        state = self.gateway.save_book(session, book, state)
        for task, attempt in zip(manifest["tasks"], manifest["attempt_ids"], strict=True):
            row = joined[task["custom_id"]]
            response_ref = save(self, session, row, "Parsed result and exact response-line provenance")
            value = {"plan": plan_id, "custom_id": task["custom_id"], "corpus_id": task["corpus_id"],
                "attempt": attempt, "manifest": manifest_id, "job_id": job["job_id"],
                "request": task["request_body_ref"], "response": response_ref, "parsed_result": parsed_ref,
                "status": row["status"], "technical_failure": row.get("technical_failure", False),
                "missing": row.get("missing", False),
                "errors": row.get("errors", []), "output": row.get("result") if row["status"] == "valid" else None,
                "model": row.get("observed_model"), "usage": row.get("usage"), "request_id": row.get("provider_request_id"),
                "title": task.get("title"), "url": task.get("url"), "packet_ref": task["packet_ref"],
                "budget_state": state, "cost_status": book.entry(task["custom_id"])["status"],
                "accepted": False, "human_validated": False}
            existing = self.latest(ASSESSMENT_KIND, task["custom_id"])
            if existing:
                identifier, stored = existing
                if any(stored.get(key) != value.get(key) for key in (
                        "plan", "attempt", "manifest", "request", "response", "parsed_result", "status")):
                    raise AuditError("batch_existing_assessment_changed")
                value = stored
            else:
                identifier = self.ledger.record(session, ASSESSMENT_KIND, task["custom_id"], value)
            projected = self.ledger.db.execute("SELECT * FROM attempts WHERE id=?", (attempt,)).fetchone()
            if projected:
                if (projected["task_key"] != task["custom_id"] or projected["response_ref"] != response_ref
                        or projected["status"] != row["status"] or projected["result_id"] != identifier):
                    raise AuditError("batch_existing_attempt_projection_changed")
                continue
            def project(event: int, task: Json = task, attempt: str = attempt,
                        response_ref: str = response_ref, row: Json = row, identifier: str = identifier) -> None:
                self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                    attempt, task["custom_id"], manifest_id, 1, task["request_body_ref"], response_ref,
                    row["status"], identifier, row.get("errors", [None])[0] if row.get("errors") else None, event))
            unknown = row["status"] in {"unknown", "missing"}
            self.ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed",
                {"attempt": attempt, "response": response_ref, "assessment": identifier,
                 "status": row["status"], "ended_at": utc()}, project)
            if not unknown:
                self.ledger.unresolved.pop(attempt, None)
        value = {"plan": plan_id, "job_id": job["job_id"], "manifest": manifest_id,
            "status": status, "reconciled": True, "parsed_result": parsed_ref,
            "counts": parsed["counts"], "budget_state": state}
        self.ledger.record(session, "luna_budget_job_reconciled", manifest_id, value)
        return value

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("batch_reconciliation_owner_mismatch")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("batch_reconciliation_explicit_scope_required")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY:
            raise AuditError("batch_plan_authorization_mismatch")
        if plan.get("contract_sha256") != contract.contract_digest():
            raise AuditError("batch_reconciliation_contract_changed")
        policy, book, state = self.authorization(session, context, plan_id, plan)
        root = Path(__file__).resolve().parents[1]
        implementation = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in (
            Path(__file__), Path(__file__).with_name("luna_batch_results.py"),
            Path(__file__).with_name("execute_luna_budget_batch.py"),
            root / "src/newsresearch/event_batch_live_gateway.py", root / "src/newsresearch/event_batch_transport.py",
            root / "src/newsresearch/event_batch_budget.py")}
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":reconcile",
            "content": {"method": "luna-budget-batch-reconciliation-v1", "implementation": implementation,
                "plan": plan_id, "versions": plan["versions"], "rules": "Retain provider files before parsing. Join exact custom IDs. Settle known usage even if content invalid; unknowns stay reserved. No new inference or membership adoption."},
            "amend_latest": True, "reason": "Bind exact reconciliation implementation"})["id"]
        self.execution_protocol = protocol
        jobs = [self.ledger.get(row["id"], JOB_KIND) for row in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (JOB_KIND,))]
        jobs = [job for job in jobs if job["plan"] == plan_id]
        observations, obstacles = [], []
        for job in jobs:
            try:
                observations.append(self.reconcile(session, plan_id, policy, job))
            except AuditError:
                raise
            except ResearchError as error:
                obstacles.append({"job_id": job["job_id"], "reason": str(error)})
        assessments = [self.ledger.get(row["id"], ASSESSMENT_KIND) for row in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (ASSESSMENT_KIND,))]
        assessments = [row for row in assessments if row["plan"] == plan_id]
        counts = Counter({name: 0 for name in ("valid", "invalid", "error", "unknown")})
        counts.update(row["status"] for row in assessments)
        submitted = sum(job["request_count"] for job in jobs)
        missing = sum(row.get("missing") is True for row in assessments)
        unassessed = submitted - len(assessments)
        pending = unassessed + counts["unknown"]
        saved = self.gateway.load_book(session, STUDY)
        if saved:
            book, state = saved
        focuses = Counter(row["output"]["focus"] for row in assessments if row["status"] == "valid")
        value = {"plan": plan_id, "protocol": protocol, "policy": policy, "jobs": observations,
            "submitted": submitted, "assessments": len(assessments), "status_counts": dict(counts),
            "pending": pending, "unassessed": unassessed, "missing_response_rows": missing,
            "observed_response_rows": len(assessments) - missing,
            "focus_counts": dict(focuses), "obstacles": obstacles,
            "charged_estimate_usd": book.charged_nanousd / 1e9, "reserved_usd": book.reserved_nanousd / 1e9,
            "budget_frozen": book.frozen, "budget_state": state,
            "eligible_not_submitted": plan["pending_requests"] - submitted,
            "human_validated": False, "accepted_events": 0, "new_embeddings": 0}
        lines = [f"Luna Batch reconciliation: **{submitted} submitted**, {len(assessments) - missing} provider response rows, "
                 f"{missing} missing response rows and {unassessed} unassessed requests; "
                 f"statuses {dict(counts)}, {pending} pending. Valid focus labels: {dict(focuses)}.", "",
                 f"Conservative API usage estimate **${value['charged_estimate_usd']:.6f}**; "
                 f"**${value['reserved_usd']:.6f} reserved**. Budget frozen: {book.frozen}. "
                 f"{value['eligible_not_submitted']:,} eligible requests remain unsubmitted. "
                 "One $120 operating limit within the $150 ceiling, shared across separate corpora.", ""]
        for row in [r for r in assessments if r["status"] == "valid"][:4]:
            output = row["output"]
            event = output.get("event") or {}
            entities = ", ".join(p["surface"] for p in event.get("participants", [])) or "none extracted"
            lines.append(f"- [{row.get('title') or row['custom_id']}](<{row.get('url') or ''}>) — "
                f"{output['focus']}; {event.get('summary') or output['reason']}. Entities: {entities}.")
        if obstacles:
            lines.extend(["", "Obstacles: " + canonical_obstacles(obstacles)])
        lines.extend(["", "Outputs are provisional model interpretations with syntax/literal-grounding checks, not human accuracy or accepted event dossiers. "
            "Missing and invalid outputs are not negative findings. No retries, new embeddings or memberships. "
            "Exact report retained in a protected artifact; record_presentation does not support this technical result kind."])
        return present(self, session, "luna_budget_reconciliation_status", value, "\n".join(lines))


def canonical_obstacles(values: list[Json]) -> str:
    return "; ".join(row["job_id"] + ": " + row["reason"] for row in values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ReconciliationResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Reconcile authorized Luna Batch jobs and preserve shared cost reservations", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}), flush=True)
        return 1 if result["obstacles"] else 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
