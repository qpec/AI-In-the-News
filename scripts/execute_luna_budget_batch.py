"""One-shot audited Batch submission and reconciliation under a shared budget.

The preparation fixes scientific inputs. This runner never retries an article,
changes its output cap, releases unknown costs or adopts an event membership.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import uuid
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, canonical, digest, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError, InputTokenReceipt, PricePolicy
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, EventBatchLiveGateway
from newsresearch.event_batch_transport import OpenAIBatchTransport, count_request_body
from newsresearch.runtime import Research, audited_handler

from luna_batch_budget_run import OWNER, STUDY, USER_INSTRUCTION, present, save

PLAN_KIND = "luna_budget_execution_plan"
MANIFEST_KIND = "luna_budget_dispatch_manifest"
JOB_KIND = "luna_budget_provider_job"
TERMINAL = {"completed", "failed", "expired", "cancelled"}


def require_receipt(receipt: Json, engine: Research) -> Json:
    if receipt.get("unknown") or not receipt.get("body_ref"):
        raise ResearchError("batch_action_unknown_no_retry")
    raw = engine.ledger.artifacts.read_bytes(receipt["body_ref"])
    if not 200 <= (receipt.get("status") or 0) < 300:
        raise ResearchError("batch_action_http_" + str(receipt.get("status")))
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ResearchError("batch_action_json_invalid") from None
    if not isinstance(value, dict):
        raise ResearchError("batch_action_object_required")
    return value


class ExecutionResearch(Research):
    gateway: EventBatchLiveGateway

    def __init__(self, *args: Any, transport: Any = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gateway = EventBatchLiveGateway(self, self.gateway.provider)
        self.transport = transport or OpenAIBatchTransport()
        self.execution_protocol: str | None = None

    def register_execution(self, session: str, context: Context, plan_id: str, plan: Json) -> str:
        root = Path(__file__).resolve().parents[1]
        files = ("scripts/execute_luna_budget_batch.py", "src/newsresearch/event_batch_transport.py",
                 "src/newsresearch/event_batch_live_gateway.py", "src/newsresearch/event_batch_budget.py")
        implementation = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
        versions = plan.get("versions", {})
        for kind, identifier in versions.items():
            self.ledger.get(identifier, kind)
        value = {"method": "luna-budget-canary-execution-v1", "plan": plan_id,
            "preparation_versions": versions, "implementation": implementation,
            "authorization_id": STUDY, "price_fingerprint": PricePolicy(**plan["price_policy"]).fingerprint,
            "rules": "Same frozen full-text requests; two separate eight-article corpus files. Exact provider counts, shared USD120 operating/USD150 maximum reservation, durable model intents, one-shot upload/create, no automatic retries, unknown charges retained, no semantic acceptance."}
        return self._version(session, context, {"kind": "protocol", "key": STUDY + ":execution",
            "content": value, "amend_latest": True,
            "reason": "Bind exact execution implementation before provider actions; preserve prior versions"})["id"]

    def latest(self, kind: str, key: str) -> tuple[str, Json] | None:
        row = self.ledger.db.execute(
            "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
            (kind, key)).fetchone()
        return (row["id"], self.ledger.get(row["id"], kind)) if row else None

    def action(self, session: str, plan_id: str, policy: str, key: str,
               request: Json, body: bytes | None = None, **kwargs: Any) -> Json:
        if self.execution_protocol is None:
            raise AuditError("batch_execution_protocol_not_registered")
        self.ledger.append(session, "batch.execution.action.bound", {"execution_protocol": self.execution_protocol,
            "plan": plan_id, "policy": policy, "action_key": key,
            "request_sha256": digest({"request": request, "body_sha256": hashlib.sha256(body).hexdigest() if body is not None else None})})
        return self.gateway.execute_action(session, plan_id=plan_id, policy_id=policy,
            authorization_id=STUDY, action_key=key, request=request, body=body,
            transport=self.transport, **kwargs)

    def authorization(self, session: str, context: Context, plan_id: str, plan: Json) -> tuple[str, BudgetBook, str]:
        price = PricePolicy(**plan["price_policy"])
        content = {"authorization_id": STUDY, "plan_ids": [plan_id],
            "allow_external_processing": True, "allow_paid_inference": True,
            "approved_by": "user:current-chat", "instruction": USER_INSTRUCTION,
            "ceiling_nanousd": 150_000_000_000, "operational_limit_nanousd": 120_000_000_000,
            "price_fingerprint": price.fingerprint, "automatic_retries": 0,
            "scope": "Current full-text prompt in separate corpora, shared budget; no embeddings or membership adoption",
            "canary_policy": "First eight frozen eligible articles per corpus. Content-invalid outputs remain invalid; bulk requires all terminal results with complete accounting and at least one valid output per corpus. No quality claim.",
            "invoice_limitations": "Conservative API usage estimate; tax and unrelated account spending unavailable"}
        policy = self._version(session, context, {"kind": "policy", "key": STUDY,
            "content": content})["id"]
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            book = BudgetBook(price_policy=price, authorization_id=STUDY,
                ceiling_nanousd=content["ceiling_nanousd"],
                operational_limit_nanousd=content["operational_limit_nanousd"])
            state = self.gateway.save_book(session, book)
        else:
            book, state = saved
            if (book.price_policy.fingerprint != price.fingerprint
                    or book.operational_limit_nanousd != content["operational_limit_nanousd"]):
                raise AuditError("batch_frozen_budget_mismatch")
        return policy, book, state

    def manifest(self, session: str, plan_id: str, corpus: str, tasks: list[Json]) -> tuple[str, Json]:
        key = plan_id + ":canary:" + corpus
        old = self.latest(MANIFEST_KIND, key)
        if old:
            if old[1]["tasks"] != tasks:
                raise AuditError("batch_manifest_changed")
            return old
        jsonl = b"".join(canonical(self.ledger.artifacts.read(t["request_ref"])).encode() + b"\n" for t in tasks)
        reference = save(self, session, jsonl, "Exact immutable Batch file before counting or dispatch")
        value = {"plan": plan_id, "corpus_id": corpus, "phase": "canary", "tasks": tasks,
            "jsonl_ref": reference, "attempt_ids": [str(uuid.uuid4()) for _ in tasks],
            "authorization_id": STUDY, "execution_protocol": self.execution_protocol, "created_at": utc()}
        identifier = self.ledger.record(session, MANIFEST_KIND, key, value)
        return identifier, value

    def submit(self, session: str, plan_id: str, plan: Json, policy: str,
               book: BudgetBook, state: str) -> tuple[BudgetBook, str]:
        for corpus in ("incident-reports", "cybercrime"):
            tasks = [t for t in plan["canary_tasks"] if t["corpus_id"] == corpus]
            if len(tasks) != 8:
                raise AuditError("batch_exact_canary_count_required")
            manifest_id, manifest = self.manifest(session, plan_id, corpus, tasks)
            if self.latest(JOB_KIND, manifest_id):
                continue
            for task in tasks:
                custom = task["custom_id"]
                body = self.ledger.artifacts.read(task["request_body_ref"])
                if digest(body) != task["request_body_ref"]:
                    raise AuditError("batch_noncanonical_body")
                receipt = self.action(session, plan_id, policy, "count:" + custom,
                    {"method": "POST", "path": "/v1/responses/input_tokens"},
                    canonical(count_request_body(body)).encode())
                answer = require_receipt(receipt, self)
                counted = answer.get("input_tokens")
                if type(counted) is not int or counted <= 0:
                    raise ResearchError("batch_provider_count_missing")
                token_receipt = InputTokenReceipt(input_tokens=counted, model=body["model"],
                    request_sha256=task["request_body_ref"], receipt_sha256=receipt["body_sha256"],
                    method="provider_responses_input_tokens", provider_request_id=receipt["provider_request_id"])
                try:
                    existing = book.entry(custom)
                except BudgetError:
                    existing = None
                if existing is None:
                    book.reserve(request_id=custom, task_id=custom, corpus_id=corpus, plan_id=plan_id,
                        request_sha256=task["request_body_ref"], input_count=token_receipt,
                        max_output_tokens=body["max_output_tokens"], price_fingerprint=book.price_policy.fingerprint)
                elif existing["request"]["request_sha256"] != task["request_body_ref"]:
                    raise AuditError("batch_existing_reservation_changed")
            # The entire file must be reserved durably before any paid intent.
            state = self.gateway.save_book(session, book, state)
            raw = self.ledger.artifacts.read_bytes(manifest["jsonl_ref"])
            upload = self.action(session, plan_id, policy, "upload:" + manifest_id,
                {"method": "POST", "path": "/v1/files", "purpose": "batch",
                 "filename": corpus + "-" + manifest_id[:16] + ".jsonl",
                 "content_sha256": manifest["jsonl_ref"]}, raw)
            file = require_receipt(upload, self)
            if file.get("purpose") != "batch" or file.get("bytes") != len(raw) or not file.get("id"):
                raise ResearchError("batch_upload_receipt_invalid")
            create_body = {"input_file_id": file["id"], "endpoint": "/v1/responses", "completion_window": "24h",
                "metadata": {"study": STUDY, "plan": plan_id, "corpus": corpus, "manifest": manifest_id}}
            dispatch = save(self, session, create_body, "Exact Batch create request binding retained upload")
            for task, attempt in zip(tasks, manifest["attempt_ids"], strict=True):
                if attempt in self.ledger.unresolved:
                    continue
                if self.ledger.db.execute("SELECT id FROM attempts WHERE id=?", (attempt,)).fetchone():
                    raise AuditError("batch_completed_attempt_cannot_dispatch")
                intended = {"attempt": attempt, "task_key": task["custom_id"], "number": 1,
                    "batch": manifest_id, "plan": plan_id, "request": task["request_body_ref"],
                    "request_sha256": task["request_body_ref"], "dispatch": dispatch,
                    "budget_authorization_id": STUDY, "budget_request_id": task["custom_id"],
                    "source_versions": [], "source_descriptor": task["descriptor"],
                    "article_exposures": 1, "approval_policy": policy, "started_at": utc()}
                intended["execution_protocol"] = self.execution_protocol
                intended["preparation_versions"] = plan.get("versions", {})
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
            receipt = self.action(session, plan_id, policy, "create:" + manifest_id,
                {"method": "POST", "path": "/v1/batches"}, canonical(create_body).encode(),
                reserved_request_ids=[t["custom_id"] for t in tasks], attempt_ids=manifest["attempt_ids"])
            answer = require_receipt(receipt, self)
            if (not str(answer.get("id", "")).startswith("batch_")
                    or answer.get("input_file_id") != file["id"]
                    or answer.get("endpoint") != "/v1/responses" or answer.get("completion_window") != "24h"):
                raise ResearchError("batch_create_receipt_invalid")
            self.ledger.record(session, JOB_KIND, manifest_id, {"plan": plan_id,
                "manifest": manifest_id, "corpus_id": corpus, "job_id": answer["id"],
                "receipt": receipt["id"], "provider_status": answer.get("status"),
                "created_at": utc(), "request_count": len(tasks)})
        return book, state

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("batch_execution_owner_mismatch")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("batch_explicit_execution_required")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY:
            raise AuditError("batch_plan_authorization_mismatch")
        self.execution_protocol = self.register_execution(session, context, plan_id, plan)
        policy, book, state = self.authorization(session, context, plan_id, plan)
        obstacle = None
        try:
            if data["phase"] == "submit":
                book, state = self.submit(session, plan_id, plan, policy, book, state)
            elif data["phase"] != "status":
                raise ResearchError("batch_execution_phase_unimplemented")
        except AuditError:
            # An audit failure is not a recoverable provider outcome. Do not
            # continue into further writes, status reads or HTTP operations.
            raise
        except (ResearchError, BudgetError) as error:
            # Persist partial progress; never dispatch a replacement or release cost.
            obstacle = str(error)
            self.ledger.record(session, "luna_budget_execution_obstacle", plan_id,
                {"plan": plan_id, "phase": data["phase"], "reason": obstacle, "observed_at": utc()})
        saved = self.gateway.load_book(session, STUDY)
        if saved:
            book, state = saved
        jobs = [self.ledger.get(r["id"], JOB_KIND) for r in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (JOB_KIND,))]
        jobs = [j for j in jobs if j["plan"] == plan_id]
        submitted = sum(j["request_count"] for j in jobs)
        unknown_create_requests = rejected_create_requests = 0
        successful_create_ids = set()
        for job in jobs:
            successful_create_ids.add(self.ledger.get(job["receipt"], RECEIPT_KIND)["action_id"])
        for row in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (ACTION_KIND,)):
            action = self.ledger.get(row["id"], ACTION_KIND)
            if (action.get("plan_id") != plan_id or action.get("phase") != "create"
                    or action["action_id"] in successful_create_ids):
                continue
            receipt = self.latest(RECEIPT_KIND, action["action_id"])
            if (receipt and receipt[1].get("unknown") is False
                    and type(receipt[1].get("status")) is int and receipt[1]["status"] >= 400):
                rejected_create_requests += len(action["reserved_request_ids"])
            else:
                unknown_create_requests += len(action["reserved_request_ids"])
        prepared = len(plan["canary_tasks"])
        counts = {"prepared": prepared, "submitted": submitted, "valid": 0, "invalid": 0,
                  "pending": submitted + unknown_create_requests,
                  "unknown_create_requests": unknown_create_requests,
                  "rejected_create_requests": rejected_create_requests,
                  "unsubmitted": prepared - submitted - unknown_create_requests - rejected_create_requests,
                  "new_embeddings": 0, "automatic_retries": 0}
        value = {"plan": plan_id, "policy": policy, "execution_protocol": self.execution_protocol,
            "preparation_versions": plan.get("versions", {}), "budget_state": state,
            "ceiling_usd": 150, "operational_limit_usd": 120,
            "charged_estimate_usd": book.charged_nanousd / 1e9,
            "reserved_usd": book.reserved_nanousd / 1e9, "committed_usd": book.committed_nanousd / 1e9,
            "budget_frozen": book.frozen, "counts": counts, "jobs": jobs, "obstacle": obstacle,
            "human_validated": False, "memberships_changed": 0}
        markdown = (f"Full-text Luna Batch: **{submitted} confirmed submitted**, 0 valid/0 invalid received, {counts['pending']} pending; "
            f"{unknown_create_requests} requests have unknown creation outcomes, {rejected_create_requests} creation-rejected, "
            f"{counts['unsubmitted']} unsubmitted. "
            f"Conservative API estimate ${value['charged_estimate_usd']:.6f}; reserved ${value['reserved_usd']:.6f}. "
            "One shared $120 operating limit and $150 maximum; taxes/unrelated account use are outside this ledger. "
            "Incident reports and cybercrime use separate files. No embeddings, retries, event acceptance or membership changes. "
            + (f"Execution obstacle: `{obstacle}`. " if obstacle else "")
            + "No completed extraction results are available from these new jobs yet. "
            "Exact report retained as a protected artifact; record_presentation does not support this technical result kind.")
        return present(self, session, "luna_budget_execution_status", value, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("submit", "status"))
    parser.add_argument("--workspace", type=Path, default=OWNER)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ExecutionResearch(args.workspace, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args) | {"workspace": str(args.workspace)},
            objective="Execute authorized full-text Luna Batch with one shared USD150 maximum and USD120 operating ceiling",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}), flush=True)
        return 1 if result["obstacle"] else 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
