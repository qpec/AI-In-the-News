"""Submit already-staged bulk manifests under the original shared USD150 cap.

No source selection, prompt changes, model retries, unknown-charge releases or
new authorization is created. Count receipts and worst-case reservations precede
each immutable file. The local 2M queued-token guard is not an account limit.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, canonical, digest, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError, InputTokenReceipt
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.event_batch_transport import count_request_body
from newsresearch.legacy import sha256
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import ExecutionResearch, JOB_KIND, PLAN_KIND, require_receipt
from luna_batch_budget_run import OWNER, ROOT, STUDY, present, save
import luna_multibatch as core
from prepare_luna_budget_wave import ASSESSMENT_KIND, MANIFEST_KIND, MAX_PER_CORPUS, canary_gate

METHOD = "luna-fulltext-budget-bulk-execution-v1"
OWN_QUEUE_TOKEN_CAP = 2_000_000


def reserved_input_tokens(book: BudgetBook) -> int:
    """Count all reserved/unknown own work, including waiting unsubmitted files."""
    identifiers = {event["value"]["request_id"] for event in book.to_dict()["events"] if event["action"] == "reserve"}
    return sum(book.entry(identifier)["request"]["input_count"]["input_tokens"]
               for identifier in identifiers if book.entry(identifier)["status"] in {"reserved", "unknown", "frozen"})


def action_blockers(actions: list[Json], receipts: list[Json], obstacles: list[Json]) -> list[str]:
    """Unknown or technically failed actions block new identities as well as retries."""
    blockers = []
    receipt_map: dict[str, list[Json]] = {}
    for receipt in receipts:
        if receipt.get("authorization_id") == STUDY:
            receipt_map.setdefault(receipt["action_id"], []).append(receipt)
    for action in actions:
        if action.get("authorization_id") != STUDY:
            continue
        rows = receipt_map.get(action["action_id"], [])
        if len(rows) != 1 or rows[0].get("unknown") is not False or not rows[0].get("body_ref"):
            blockers.append("shared_action_unknown_or_missing_receipt")
        elif type(rows[0].get("status")) is not int or not 200 <= rows[0]["status"] < 300:
            blockers.append("shared_action_technical_http_failure")
    if obstacles:
        blockers.append("prior_execution_technical_obstacle")
    return sorted(set(blockers))


def validate_manifest(engine: ExecutionResearch, session: str, plan_id: str, plan: Json,
                      manifest_id: str, manifest: Json, snapshot: core.ContractSnapshot) -> bytes:
    tasks, attempts = manifest.get("tasks"), manifest.get("attempt_ids")
    corpus = manifest.get("corpus_id")
    if (manifest.get("plan") != plan_id or manifest.get("authorization_id") != STUDY
            or manifest.get("phase") != "bulk" or corpus not in plan["corpora"]
            or not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_PER_CORPUS
            or not isinstance(attempts, list) or len(attempts) != len(tasks)
            or len(set(attempts)) != len(attempts)
            or len({task["custom_id"] for task in tasks}) != len(tasks)):
        raise AuditError("bulk_manifest_shape_or_scope_invalid")
    try:
        for attempt in attempts:
            if str(uuid.UUID(attempt)) != attempt:
                raise ValueError("noncanonical UUID")
    except (TypeError, ValueError, AttributeError):
        raise AuditError("bulk_attempt_ids_invalid") from None
    engine.ledger.append(session, "budget.bulk.retained_requests.inspection.intended", {
        "manifest": manifest_id, "custom_ids": [task["custom_id"] for task in tasks],
        "purpose": "Verify exact retained full-text requests and packets before any provider action"})
    lines = []
    for task in tasks:
        descriptor = task["descriptor"]
        if (task.get("corpus_id") != corpus or descriptor.get("corpus_id") != corpus
                or descriptor.get("manifest_sha256") != plan["corpora"][corpus]["manifest_sha256"]
                or descriptor.get("contract_sha256") != plan["contract_sha256"]
                or descriptor.get("max_output_tokens") != 4096 or descriptor.get("model") != core.MODEL
                or descriptor.get("custom_id") != task["custom_id"]
                or task.get("request_body_ref") != descriptor.get("request_body_sha256")
                or task.get("request_ref") != descriptor.get("request_sha256")
                or task.get("packet_ref") != descriptor.get("packet_sha256")):
            raise AuditError("bulk_request_descriptor_binding_changed")
        request = engine.ledger.artifacts.read(task["request_ref"])
        body = engine.ledger.artifacts.read(task["request_body_ref"])
        packet = engine.ledger.artifacts.read(task["packet_ref"])
        if core.contract.validate_packet(packet):
            raise AuditError("bulk_fulltext_packet_invalid")
        model_input = {key: value for key, value in packet["model_input"].items() if key != "instructions"}
        expected_body = {"model": core.MODEL, "reasoning": {"effort": "none"}, "store": False,
            "max_output_tokens": 4096, "instructions": snapshot.prompt,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": canonical(model_input)}]}],
            "text": {"format": {"type": "json_schema", "name": "luna_event_v2", "strict": True,
                                "schema": json.loads(snapshot.schema_json)}}}
        if (body != expected_body or digest(body) != task["request_body_ref"]
                or packet["model_input"]["instructions"] != snapshot.prompt
                or request != {"custom_id": task["custom_id"], "method": "POST", "url": "/v1/responses", "body": body}):
            raise AuditError("bulk_exact_request_contract_changed")
        line = canonical(request).encode() + b"\n"
        import hashlib
        if len(line) != descriptor["line_bytes"] or hashlib.sha256(line).hexdigest() != descriptor["line_sha256"]:
            raise AuditError("bulk_exact_jsonl_line_changed")
        lines.append(line)
    raw = b"".join(lines)
    if len(raw) >= core.PROVIDER_BYTE_CEILING_EXCLUSIVE or engine.ledger.artifacts.read_bytes(manifest["jsonl_ref"]) != raw:
        raise AuditError("bulk_exact_file_changed_or_oversized")
    return raw


class BulkExecutionResearch(ExecutionResearch):
    def rows(self, session: str, kind: str) -> list[Json]:
        self.ledger.append(session, "budget.bulk.record_inspection.intended", {
            "sql": "SELECT id FROM records WHERE kind=? ORDER BY created_event", "parameters": [kind]})
        return [{"id": row["id"], **self.ledger.get(row["id"], kind)} for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def submit_manifest(self, session: str, plan_id: str, plan: Json, policy: str, book: BudgetBook,
                        state: str, manifest_id: str, manifest: Json, raw: bytes) -> tuple[BudgetBook, str, str | None]:
        corpus, tasks = manifest["corpus_id"], manifest["tasks"]
        for task in tasks:
            custom = task["custom_id"]
            body = self.ledger.artifacts.read(task["request_body_ref"])
            receipt = self.action(session, plan_id, policy, "count:" + custom,
                {"method": "POST", "path": "/v1/responses/input_tokens"}, canonical(count_request_body(body)).encode())
            answer = require_receipt(receipt, self)
            count = answer.get("input_tokens")
            if type(count) is not int or count <= 0:
                raise ResearchError("bulk_provider_exact_count_missing")
            counted = InputTokenReceipt(count, body["model"], task["request_body_ref"], receipt["body_sha256"],
                "provider_responses_input_tokens", receipt.get("provider_request_id"))
            try:
                existing = book.entry(custom)
            except BudgetError:
                existing = None
            if existing is not None:
                if (existing["request"]["request_sha256"] != task["request_body_ref"]
                        or existing["request"]["plan_id"] != plan_id or existing["status"] != "reserved"):
                    raise AuditError("bulk_existing_request_cannot_be_redispatched")
            else:
                try:
                    book.reserve(request_id=custom, task_id=custom, corpus_id=corpus, plan_id=plan_id,
                        request_sha256=task["request_body_ref"], input_count=counted,
                        max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
                except BudgetError as error:
                    if str(error) != "budget_operational_limit_reached":
                        raise
                    state = self.gateway.save_book(session, book, state)
                    return book, state, "shared_operational_budget_admission_deferred"
        state = self.gateway.save_book(session, book, state)
        if reserved_input_tokens(book) > OWN_QUEUE_TOKEN_CAP:
            return book, state, "own_reserved_input_token_guard_deferred"
        upload = self.action(session, plan_id, policy, "upload:" + manifest_id,
            {"method": "POST", "path": "/v1/files", "purpose": "batch",
             "filename": corpus + "-" + manifest_id[:16] + ".jsonl", "content_sha256": manifest["jsonl_ref"]}, raw)
        file = require_receipt(upload, self)
        if file.get("purpose") != "batch" or file.get("bytes") != len(raw) or not file.get("id"):
            raise ResearchError("bulk_upload_receipt_invalid")
        create_body = {"input_file_id": file["id"], "endpoint": "/v1/responses", "completion_window": "24h",
            "metadata": {"study": STUDY, "plan": plan_id, "corpus": corpus, "manifest": manifest_id}}
        dispatch = save(self, session, create_body, "Exact reserved bulk Batch create request")
        for task, attempt in zip(tasks, manifest["attempt_ids"], strict=True):
            if attempt in self.ledger.unresolved:
                continue
            if self.ledger.db.execute("SELECT id FROM attempts WHERE id=?", (attempt,)).fetchone():
                raise AuditError("bulk_completed_attempt_cannot_redispatch")
            intended = {"attempt": attempt, "task_key": task["custom_id"], "number": 1, "batch": manifest_id,
                "plan": plan_id, "request": task["request_body_ref"], "request_sha256": task["request_body_ref"],
                "dispatch": dispatch, "budget_authorization_id": STUDY, "budget_request_id": task["custom_id"],
                "source_versions": [], "source_descriptor": task["descriptor"], "article_exposures": 1,
                "approval_policy": policy, "started_at": utc(), "execution_protocol": self.execution_protocol,
                "preparation_versions": plan["versions"]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
        receipt = self.action(session, plan_id, policy, "create:" + manifest_id,
            {"method": "POST", "path": "/v1/batches"}, canonical(create_body).encode(),
            reserved_request_ids=[task["custom_id"] for task in tasks], attempt_ids=manifest["attempt_ids"])
        answer = require_receipt(receipt, self)
        if (not str(answer.get("id", "")).startswith("batch_") or answer.get("input_file_id") != file["id"]
                or answer.get("endpoint") != "/v1/responses" or answer.get("completion_window") != "24h"):
            raise ResearchError("bulk_create_receipt_invalid")
        self.ledger.record(session, JOB_KIND, manifest_id, {"plan": plan_id, "manifest": manifest_id,
            "corpus_id": corpus, "job_id": answer["id"], "receipt": receipt["id"],
            "provider_status": answer.get("status"), "created_at": utc(), "request_count": len(tasks)})
        return book, state, None

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("bulk_execution_wrong_owner")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("bulk_explicit_execution_required")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY:
            raise AuditError("bulk_plan_authorization_changed")
        self.execution_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":bulk-submit",
            "content": {"method": METHOD, "plan": plan_id, "preparation_versions": plan["versions"],
                "implementation": {str(path.relative_to(ROOT)): sha256(path) for path in (
                    Path(__file__), ROOT / "scripts/execute_luna_budget_batch.py", ROOT / "scripts/prepare_luna_budget_wave.py",
                    ROOT / "src/newsresearch/event_batch_live_gateway.py", ROOT / "src/newsresearch/event_batch_budget.py",
                    ROOT / "src/newsresearch/event_batch_transport.py")},
                "own_reserved_input_token_guard": OWN_QUEUE_TOKEN_CAP,
                "rules": "Use same original authorization and budget. Recheck completed/accounted canaries and no shared unknown or technical action. Dispatch only staged bulk manifests <=250 requests per corpus, immutable fulltext4096 contract. Obtain provider exact counts; reserve full output and persist before paid create. Keep all unknown and deferred reservations, no retries. Local2M guard does not establish account capacity."},
            "amend_latest": True, "reason": "Bind separate bulk execution implementation before provider actions"})["id"]
        if any(sha256(ROOT / file) != expected for file, expected in plan["implementation"].items()):
            raise AuditError("bulk_frozen_preparation_implementation_changed")
        snapshot = core.load_contract_snapshot()
        if snapshot.contract_sha256 != plan["contract_sha256"]:
            raise AuditError("bulk_contract_changed")
        policy, book, state = self.authorization(session, context, plan_id, plan)
        assessments = self.rows(session, ASSESSMENT_KIND)
        gate = canary_gate(plan_id, plan, assessments, book)
        obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle")
                     for row in self.rows(session, kind) if row.get("plan") == plan_id]
        blockers = gate["blockers"] + action_blockers(self.rows(session, ACTION_KIND), self.rows(session, RECEIPT_KIND), obstacles)
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind=? AND logical_key=?", (STOP_KIND, STUDY)).fetchone():
            blockers.append("shared_gateway_stopped")
        all_manifests = [row for row in self.rows(session, MANIFEST_KIND) if row.get("plan") == plan_id]
        custom_ids = [task["custom_id"] for row in all_manifests for task in row["tasks"]]
        if len(custom_ids) != len(set(custom_ids)):
            raise AuditError("bulk_request_appears_in_multiple_manifests")
        manifests = [row for row in all_manifests if row.get("phase") == "bulk"]
        gate_ref = save(self, session, {"plan": plan_id, "gate": gate, "blockers": sorted(set(blockers)),
            "budget_state": state, "manifest_ids": [row["id"] for row in manifests]}, "Bulk execution gate before network actions")
        deferred = []
        obstacle = None
        if not blockers:
            for manifest in manifests:
                manifest_id = manifest["id"]
                if self.latest(JOB_KIND, manifest_id):
                    continue
                try:
                    raw = validate_manifest(self, session, plan_id, plan, manifest_id, manifest, snapshot)
                    book, state, reason = self.submit_manifest(session, plan_id, plan, policy, book, state,
                                                              manifest_id, manifest, raw)
                    if reason:
                        value = {"plan": plan_id, "manifest": manifest_id, "reason": reason,
                                 "requests": len(manifest["tasks"]), "budget_state": state,
                                 "own_reserved_input_tokens": reserved_input_tokens(book), "observed_at": utc()}
                        self.ledger.record(session, "luna_budget_bulk_deferral", manifest_id, value)
                        deferred.append(value)
                        break
                except AuditError:
                    raise
                except (ResearchError, BudgetError) as error:
                    # Retain any newly admitted known-unsubmitted reservations too.
                    latest_budget = self.gateway.load_book(session, STUDY)
                    if latest_budget is None:
                        raise AuditError("bulk_shared_budget_disappeared") from error
                    state = self.gateway.save_book(session, book, latest_budget[1])
                    obstacle = str(error)
                    self.ledger.record(session, "luna_budget_bulk_obstacle", plan_id,
                        {"plan": plan_id, "manifest": manifest_id, "reason": obstacle, "observed_at": utc()})
                    break
        current = self.gateway.load_book(session, STUDY)
        if current:
            book, state = current
        jobs = [row for row in self.rows(session, JOB_KIND) if row.get("plan") == plan_id]
        bulk_ids = {row["id"] for row in manifests}
        bulk_jobs = [row for row in jobs if row["manifest"] in bulk_ids]
        submitted_ids = {task["custom_id"] for row in manifests if row["id"] in {job["manifest"] for job in bulk_jobs}
                         for task in row["tasks"]}
        bulk_customs = {task["custom_id"] for row in manifests for task in row["tasks"]}
        output_rows = [row for row in assessments if row.get("plan") == plan_id and row.get("custom_id") in bulk_customs]
        valid = sum(row.get("status") == "valid" for row in output_rows)
        invalid = sum(row.get("status") == "invalid" for row in output_rows)
        attempted_unknown = {task["custom_id"] for row in manifests for task, attempt in zip(row["tasks"], row["attempt_ids"], strict=True)
                             if attempt in self.ledger.unresolved and task["custom_id"] not in submitted_ids}
        counts = {"prepared_bulk": len(bulk_customs), "submitted_bulk": len(submitted_ids),
            "valid_bulk": valid, "invalid_bulk": invalid,
            "pending_submitted_bulk": len(submitted_ids - {row["custom_id"] for row in output_rows}),
            "unconfirmed_create_bulk": len(attempted_unknown),
            "unsubmitted_bulk": len(bulk_customs - submitted_ids - attempted_unknown)}
        value = {"plan": plan_id, "policy": policy, "execution_protocol": self.execution_protocol,
            "gate_ref": gate_ref, "gate_blockers": sorted(set(blockers)), "obstacle": obstacle,
            "counts": counts, "deferrals": deferred, "jobs": bulk_jobs, "budget_state": state,
            "charged_estimate_usd": book.charged_nanousd / 1e9, "reserved_usd": book.reserved_nanousd / 1e9,
            "committed_usd": book.committed_nanousd / 1e9, "operating_limit_usd": 120, "ceiling_usd": 150,
            "own_reserved_input_tokens": reserved_input_tokens(book), "own_queue_guard_tokens": OWN_QUEUE_TOKEN_CAP,
            "account_queue_capacity_verified": False, "model_retries": 0, "embeddings": 0, "memberships_changed": 0}
        markdown = (f"Bulk Luna Batch: **{counts['submitted_bulk']} confirmed submitted**, {valid} valid/{invalid} invalid returned, "
            f"{counts['pending_submitted_bulk']} submitted pending; {counts['unconfirmed_create_bulk']} unconfirmed creation outcomes and "
            f"{counts['unsubmitted_bulk']} unsubmitted. Conservative shared charge estimate ${value['charged_estimate_usd']:.6f}; "
            f"reserved ${value['reserved_usd']:.6f}. Shared operating limit $120, ceiling $150. "
            "Corpora remain separate; complete text and 4,096-token output cap unchanged. "
            "The local 2M reserved-input-token guard is not verified account capacity. Zero retries, embeddings or membership changes. "
            + (f"Gate blockers: {', '.join(blockers)}. " if blockers else "")
            + (f"Deferred manifests: {len(deferred)} ({', '.join(row['reason'] for row in deferred)}). " if deferred else "")
            + (f"Execution obstacle: {obstacle}. " if obstacle else "")
            + "Missing and deferred requests remain unprocessed, not negative findings. Exact report retained in protected storage; "
            "record_presentation does not support this technical kind.")
        return present(self, session, "luna_budget_bulk_status", value, markdown)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=OWNER)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = BulkExecutionResearch(args.workspace, config=Config(offline=False))
    try:
        result = engine.execute("status", {"plan": args.plan, "allow_paid_execution": args.allow_paid_execution},
            objective="Submit exact staged full-text Batch files within the original shared USD150 authorization",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}), flush=True)
        return 1 if result["obstacle"] or result["gate_blockers"] else 0
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
