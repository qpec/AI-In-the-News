"""Acknowledge exactly two settled failed extractions without repairing them.

Only retained terminal output-cap truncation or refusal is eligible. Original
assessments, charges, stops and deadlines remain immutable; no retry is granted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, require_active
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import ExecutionResearch, PLAN_KIND
from execute_luna_budget_wave import action_blockers
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
from luna_batch_phase_projection import parse_batch_results_phase_aware
from luna_budget_continuation import acknowledged_assessment, load_continuation
from poll_luna_budget_batch import ASSESSMENT_KIND, PARSE_KIND
from prepare_luna_budget_wave import MANIFEST_KIND
import run_luna_budget_fast as fast

ACK_KIND = "luna_budget_exact_failed_extraction_ack"
DIAGNOSTIC_KIND = "luna_budget_progress_report"
METHOD = "finite-settled-terminal-failure-ack-v1"


def implementation_hashes() -> dict[str, str]:
    result = fast.implementation_hashes()
    for name in ("luna_budget_failure_ack.py", "run_luna_budget_recovery.py", "report_luna_budget_progress.py"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def exact_ids(values: Any) -> list[str]:
    if (not isinstance(values, list) or len(values) != 2 or len(set(values)) != 2
            or any(not isinstance(value, str) or len(value) != 64
                   or any(char not in "0123456789abcdef" for char in value) for value in values)):
        raise AuditError("failure_ack_exact_two_assessment_ids_required")
    return sorted(values)


def terminal_failure_kind(row: Json, assessment: Json, entry: Json, request: Json) -> str:
    """Pure closed classification. Billing settlement is not content acceptance."""
    response = row.get("response")
    if not isinstance(response, dict) or not isinstance(response.get("body"), dict):
        raise AuditError("failure_ack_response_body_required")
    body = response["body"]
    usage = body.get("usage")
    if not isinstance(usage, dict):
        raise AuditError("failure_ack_complete_usage_required")
    reserved = entry.get("request", {})
    settlement = entry.get("settlement") or {}
    if (row.get("error") is not None or response.get("status_code") != 200
            or body.get("model") != "gpt-6-luna" or request.get("model") != "gpt-6-luna"
            or assessment.get("model") != body.get("model")
            or body.get("error") is not None or body.get("tools")
            or request.get("max_output_tokens") != 4096 or reserved.get("max_output_tokens") != 4096
            or assessment.get("status") != "error" or assessment.get("technical_failure") is not True
            or assessment.get("missing") is True or assessment.get("output") is not None
            or assessment.get("accepted") is not False or assessment.get("human_validated") is not False
            or entry.get("status") != "settled" or entry.get("accepted") is not True
            or entry.get("reserved_nanousd") != 0 or settlement.get("complete") is not True
            or settlement.get("model") != body.get("model")
            or settlement.get("request_sha256") != assessment.get("request")
            or settlement.get("receipt_sha256") != assessment.get("response")
            or type(usage.get("input_tokens")) is not int or type(usage.get("output_tokens")) is not int
            or usage["input_tokens"] != reserved.get("input_count", {}).get("input_tokens")
            or not 0 <= usage["output_tokens"] <= 4096
            or settlement.get("input_tokens") != usage["input_tokens"]
            or settlement.get("output_tokens") != usage["output_tokens"]
            or assessment.get("usage") != usage
            or usage.get("total_tokens", usage["input_tokens"] + usage["output_tokens"]) != usage["input_tokens"] + usage["output_tokens"]):
        raise AuditError("failure_ack_exact_terminal_usage_and_settlement_required")
    if (body.get("status") == "incomplete" and body.get("incomplete_details") == {"reason": "max_output_tokens"}
            and usage["output_tokens"] == 4096 and assessment.get("errors") == ["response:not_completed"]):
        return "terminal_output_cap_truncation_still_failed"
    errors = set(assessment.get("errors", []))
    output = body.get("output")
    messages = [item for item in output if isinstance(item, dict) and item.get("type") == "message"] if isinstance(output, list) else []
    if (body.get("status") == "completed" and body.get("incomplete_details") is None
            and errors == {"response:refusal", "response:not_single_output_text"}
            and messages and all(message.get("status", "completed") == "completed"
                                 and message.get("role", "assistant") == "assistant" for message in messages)
            and any(isinstance(part, dict) and part.get("type") == "refusal"
                    for message in messages for part in message.get("content", []))):
        return "terminal_refusal_still_failed"
    raise AuditError("failure_ack_fault_type_not_allowlisted")


def _rows(engine: Any, session: str, kind: str, plan_id: str | None = None) -> list[Json]:
    sql = "SELECT id FROM records WHERE kind=? ORDER BY created_event"
    engine.ledger.append(session, "budget.failure_ack.records.inspection.intended", {"sql": sql, "parameters": [kind]})
    rows = [{**engine.ledger.get(row["id"], kind), "id": row["id"]} for row in engine.ledger.db.execute(sql, (kind,))]
    return rows if plan_id is None else [row for row in rows if row.get("plan") == plan_id]


def known_budget(engine: Any, session: str, plan_id: str) -> tuple[Any, str]:
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None:
        raise AuditError("failure_ack_existing_budget_required")
    book, state = saved
    if book.frozen or book.ceiling_nanousd != 150_000_000_000 or book.operational_limit_nanousd != 120_000_000_000:
        raise AuditError("failure_ack_frozen_or_changed_budget")
    for event in book.to_dict()["events"]:
        if event["action"] == "reserve":
            entry = book.entry(event["value"]["request_id"])
            if entry["request"]["plan_id"] != plan_id or entry["status"] in {"unknown", "frozen", "overrun"}:
                raise AuditError("failure_ack_unknown_or_other_plan_cost")
    if engine.latest(STOP_KIND, STUDY):
        raise AuditError("failure_ack_gateway_stop_preserved")
    return book, state


def verify_failure(engine: Any, session: str, plan_id: str, assessment_id: str, book: Any) -> Json:
    engine.ledger.append(session, "budget.failure_ack.retained_evidence.inspection.intended",
        {"plan": plan_id, "assessment": assessment_id, "purpose": "Verify exact terminal failure and settled charge; no repair"})
    assessment = engine.ledger.get(assessment_id, ASSESSMENT_KIND)
    manifest = engine.ledger.get(assessment["manifest"], MANIFEST_KIND)
    matches = [(task, attempt) for task, attempt in zip(manifest["tasks"], manifest["attempt_ids"], strict=True)
               if task["custom_id"] == assessment["custom_id"]]
    if len(matches) != 1 or manifest.get("plan") != plan_id or manifest.get("phase") != "bulk":
        raise AuditError("failure_ack_exact_bulk_manifest_required")
    task, attempt = matches[0]
    entry = book.entry(task["custom_id"])
    if (assessment.get("plan") != plan_id or assessment.get("attempt") != attempt
            or assessment.get("corpus_id") != task["corpus_id"]
            or assessment.get("request") != task["request_body_ref"]
            or assessment.get("packet_ref") != task["packet_ref"]
            or entry["request"].get("plan_id") != plan_id
            or entry["request"].get("corpus_id") != task["corpus_id"]
            or entry["request"].get("request_sha256") != task["request_body_ref"]
            or attempt in engine.ledger.unresolved):
        raise AuditError("failure_ack_attempt_or_request_changed")
    projected = engine.ledger.db.execute("SELECT * FROM attempts WHERE id=?", (attempt,)).fetchone()
    if (not projected or projected["status"] != "error" or projected["result_id"] != assessment_id
            or projected["task_key"] != task["custom_id"]
            or projected["response_ref"] != assessment["response"]):
        raise AuditError("failure_ack_attempt_not_terminal")
    checkpoint = engine.latest(PARSE_KIND, assessment["manifest"])
    if (not checkpoint or checkpoint[1]["parsed_result"] != assessment["parsed_result"] or checkpoint[1]["status"] != "completed"
            or checkpoint[1].get("plan") != plan_id or checkpoint[1].get("manifest") != assessment["manifest"]
            or checkpoint[1].get("job_id") != assessment.get("job_id")):
        raise AuditError("failure_ack_completed_batch_checkpoint_required")
    original = engine.ledger.artifacts.read(assessment["response"])
    if original.get("usage_complete") is not True or original.get("missing") is not False:
        raise AuditError("failure_ack_complete_observed_usage_required")
    found = []
    for receipt_id in checkpoint[1]["download_receipts"].values():
        receipt = engine.ledger.get(receipt_id, RECEIPT_KIND)
        if (receipt.get("plan_id") != plan_id or receipt.get("authorization_id") != STUDY
                or receipt.get("status") != 200 or receipt.get("unknown") is not False or not receipt.get("body_ref")):
            raise AuditError("failure_ack_retained_file_receipt_invalid")
        raw = engine.ledger.artifacts.read_bytes(receipt["body_ref"])
        if hashlib.sha256(raw).hexdigest() != receipt["body_sha256"]:
            raise AuditError("failure_ack_provider_file_hash_mismatch")
        for line in raw.splitlines():
            row = json.loads(line)
            if row.get("custom_id") == task["custom_id"]:
                found.append((row, line, receipt_id, receipt["body_ref"]))
    if len(found) != 1:
        raise AuditError("failure_ack_exact_provider_row_not_unique")
    row, line, receipt_id, file_ref = found[0]
    request = engine.ledger.artifacts.read(task["request_body_ref"])
    parsed = parse_batch_results_phase_aware(line + b"\n", None, {task["custom_id"]: {
        "packet": engine.ledger.artifacts.read(task["packet_ref"]), "body": request}})["items"][0]
    if parsed != original or parsed.get("errors") != assessment.get("errors"):
        raise AuditError("failure_ack_retained_parser_result_changed")
    kind = terminal_failure_kind(row, assessment, entry, request)
    return {"assessment": assessment_id, "custom_id": task["custom_id"], "manifest": assessment["manifest"],
        "attempt": attempt, "request": task["request_body_ref"], "response": assessment["response"],
        "provider_file_ref": file_ref, "download_receipt": receipt_id,
        "raw_line_sha256": hashlib.sha256(line).hexdigest(), "failure_kind": kind,
        "errors": assessment["errors"], "settlement": entry["settlement"], "charged_nanousd": entry["charged_nanousd"],
        "original_status": "error", "accepted_output": False, "retry_allowed": False}


def acknowledged_failure(row: Json, acknowledgment: Json | None) -> bool:
    if not acknowledgment or row.get("plan") != acknowledgment.get("plan"):
        return False
    matches = [proof for proof in acknowledgment["failures"] if proof["assessment"] == row.get("id")]
    return bool(len(matches) == 1 and row.get("status") == "error" and row.get("technical_failure") is True
        and all(row.get(key) == matches[0].get(key) for key in ("custom_id", "manifest", "attempt", "request", "response", "errors")))


def check_history(engine: Any, session: str, plan_id: str, phase_ref: str, run_id: str, finish_id: str) -> Json:
    phase = load_continuation(engine, session, plan_id, phase_ref)
    original = engine.ledger.get(run_id, fast.RUN_KIND)
    finish = engine.ledger.get(finish_id, fast.FINISH_KIND)
    if (phase is None or original.get("plan") != plan_id or original.get("authorization_id") != STUDY
            or original.get("continuation_ref") != phase_ref or original.get("deadline_epoch") != phase["deadline_epoch"]
            or original.get("implementation") != fast.implementation_hashes()
            or finish.get("plan") != plan_id or finish.get("run") != run_id or finish.get("reason") != "technical_stop"):
        raise AuditError("failure_ack_original_stop_or_deadline_changed")
    return phase


def load_failure_ack(engine: Any, session: str, plan_id: str, reference: str) -> Json:
    require_active(engine, session)
    value = engine.ledger.get(reference, ACK_KIND)
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("implementation") != implementation_hashes()
            or exact_ids(value.get("assessment_ids")) != sorted(proof["assessment"] for proof in value["failures"])):
        raise AuditError("failure_ack_immutable_binding_changed")
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (protocol.get("method") != METHOD or protocol.get("plan") != plan_id
            or protocol.get("assessment_ids") != value["assessment_ids"]
            or protocol.get("diagnostic_ref") != value["diagnostic_ref"]
            or protocol.get("original_run") != value["original_run"]
            or protocol.get("original_finish") != value["original_finish"]):
        raise AuditError("failure_ack_registered_protocol_binding_changed")
    phase = check_history(engine, session, plan_id, value["phase_continuation_ref"], value["original_run"], value["original_finish"])
    if value["deadline_epoch"] != phase["deadline_epoch"]:
        raise AuditError("failure_ack_deadline_reset_forbidden")
    book, _ = known_budget(engine, session, plan_id)
    diagnostic = engine.ledger.get(value["diagnostic_ref"], DIAGNOSTIC_KIND)
    if (diagnostic.get("plan") != plan_id or diagnostic.get("budget_state") != value["budget_state_at_ack"]
            or diagnostic.get("pending_jobs") != 0 or diagnostic.get("budget_frozen") is not False
            or not set(value["assessment_ids"]) <= {row["id"] for row in diagnostic["technical_rows"]}):
        raise AuditError("failure_ack_original_diagnostic_changed")
    verified = [verify_failure(engine, session, plan_id, identifier, book) for identifier in value["assessment_ids"]]
    if verified != value["failures"]:
        raise AuditError("failure_ack_failure_proof_changed")
    return {**value, "id": reference}


class FailureAcknowledgmentResearch(ExecutionResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() or not self.config.offline:
            raise AuditError("failure_ack_original_offline_owner_required")
        return self.register_acknowledgment(session, context, data)

    @audited_handler
    def register_acknowledgment(self: ExecutionResearch, session: str, context: Context, data: Json) -> Json:
        """Shared proof builder; caller already owns the audited session/owner.

        This sends no provider requests. The recovery runner can register this
        exact acknowledgment before admission within its one online session.
        """
        plan_id, phase_ref = data["plan"], data["phase_continuation_ref"]
        ids = exact_ids(data["assessment_ids"])
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != fast.core.contract_digest():
            raise AuditError("failure_ack_frozen_plan_changed")
        previous = self.latest(fast.RUN_KIND, plan_id + ":" + phase_ref + ":fast-v1")
        finish = self.latest(fast.FINISH_KIND, previous[0]) if previous else None
        if not previous or not finish:
            raise AuditError("failure_ack_original_fast_stop_required")
        key = plan_id + ":" + finish[0]
        existing = self.latest(ACK_KIND, key)
        if existing:
            if (existing[1].get("assessment_ids") != ids or existing[1].get("diagnostic_ref") != data["diagnostic_ref"]
                    or existing[1].get("phase_continuation_ref") != phase_ref):
                raise AuditError("failure_ack_existing_registration_inputs_changed")
            load_failure_ack(self, session, plan_id, existing[0])
            return present(self, session, "luna_budget_failure_ack_registration", {"ack_ref": existing[0], **existing[1], "reused": True},
                "Reused the exact existing two-failure acknowledgment. Both extractions remain failed; original errors, charges, "
                "stop and deadline are preserved. Zero provider calls, new acknowledgments, retries or accepted outputs. "
                "Protected exact presentation retained; record_presentation does not support this technical kind.")
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":finite-failure-ack",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"],
                "implementation": implementation_hashes(), "assessment_ids": ids, "diagnostic_ref": data["diagnostic_ref"],
                "original_run": previous[0], "original_finish": finish[0],
                "rules": "Exactly two identified noncanary terminal max-output/refusal failures, retained raw bytes and complete settled usage. Preserve errors, exclusions, charges and stop; never repair, accept or retry them. Permit untouched requests only under same shared cap, prompt and original deadline. No future error exemption; unknown/frozen costs and shared action failures remain blocking."}})["id"]
        phase = check_history(self, session, plan_id, phase_ref, previous[0], finish[0])
        book, state = known_budget(self, session, plan_id)
        diagnostic = self.ledger.get(data["diagnostic_ref"], DIAGNOSTIC_KIND)
        if (diagnostic.get("plan") != plan_id or diagnostic.get("budget_state") != state
                or diagnostic.get("budget_frozen") is not False or diagnostic.get("pending_jobs") != 0
                or book.reserved_nanousd != 0):
            raise AuditError("failure_ack_current_drained_diagnostic_required")
        technical = {row["id"]: row for row in diagnostic["technical_rows"]}
        assessments = _rows(self, session, ASSESSMENT_KIND, plan_id)
        bad = {row["id"] for row in assessments if (row.get("technical_failure") or row.get("status") not in {"valid", "invalid"})
               and not acknowledged_assessment(row, phase)}
        if bad != set(ids) or not set(ids) <= technical.keys():
            raise AuditError("failure_ack_exact_two_unacknowledged_errors_required")
        canaries = {row["custom_id"] for row in plan["canary_tasks"]}
        failures = [verify_failure(self, session, plan_id, identifier, book) for identifier in ids]
        for proof in failures:
            reported = technical[proof["assessment"]]
            if (proof["custom_id"] in canaries or reported.get("custom_id") != proof["custom_id"]
                    or reported.get("errors") != proof["errors"] or reported.get("current_cost_status") != "settled"
                    or (reported.get("retained_provider_metadata") or {}).get("receipt") != proof["download_receipt"]):
                raise AuditError("failure_ack_diagnostic_or_canary_mismatch")
        obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle", "luna_budget_fast_obstacle")
                     for row in _rows(self, session, kind, plan_id)]
        if action_blockers(_rows(self, session, ACTION_KIND), _rows(self, session, RECEIPT_KIND), obstacles):
            raise AuditError("failure_ack_shared_action_or_execution_failure")
        if time.time() >= phase["deadline_epoch"]:
            raise AuditError("failure_ack_original_deadline_expired")
        value = {"plan": plan_id, "authorization_id": STUDY, "protocol": protocol,
            "implementation": implementation_hashes(), "assessment_ids": ids, "failures": failures,
            "diagnostic_ref": data["diagnostic_ref"], "budget_state_at_ack": state,
            "phase_continuation_ref": phase_ref, "original_run": previous[0], "original_finish": finish[0],
            "deadline_epoch": phase["deadline_epoch"], "queue_token_cap": previous[1]["queue_token_cap"],
            "count_workers": previous[1]["count_workers"], "approved_by": "user:current-chat",
            "instruction": "keep running and fix problems", "paid_retries": 0,
            "original_errors_and_stop_unchanged": True, "new_models": 0, "accepted_events": 0}
        old = self.latest(ACK_KIND, key)
        if old and old[1] != value:
            raise AuditError("failure_ack_registration_changed")
        identifier = old[0] if old else self.ledger.record(session, ACK_KIND, key, value)
        return present(self, session, "luna_budget_failure_ack_registration", {"ack_ref": identifier, **value},
            "Acknowledged exactly two fully settled terminal extraction failures. Both remain failed, with zero usable output, "
            "zero retries and no repaired/accepted interpretation. The original stopped run, raw responses and charges remain. "
            "Untouched requests may continue under the unchanged $120 operating/$150 maximum, prompt, output cap and original deadline; "
            "new technical or unknown failures still stop. This offline step made zero provider/model calls. "
            "Protected exact presentation retained; record_presentation does not support this technical kind.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--phase-continuation-ref", required=True)
    parser.add_argument("--diagnostic-ref", required=True)
    parser.add_argument("--assessment-id", dest="assessment_ids", action="append", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = FailureAcknowledgmentResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args), objective="Acknowledge exactly two known failed and fully charged extractions without retry or acceptance", actor=fast.ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "ack_ref": result["ack_ref"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
