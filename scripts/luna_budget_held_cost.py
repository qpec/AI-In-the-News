"""Finite terminal-rejection exception with its entire unknown liability held.

No cost or extraction is repaired. The real shared book, immutable attempts and
old stops remain unchanged; every future anomaly still blocks admission.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from newsresearch.common import AuditError, Context, Json, canonical, require_active
from newsresearch.event_batch_budget import BudgetBook
from newsresearch.event_batch_transport import count_request_body
from newsresearch.runtime import audited_handler

import diagnose_luna_budget_costs as diagnostic_method
import luna_budget_failure_ack as base
import luna_budget_failure_chain as chain
from luna_budget_held_history import verify_history
from luna_batch_budget_run import ROOT, STUDY, present

ACK_KIND = "luna_budget_exact_held_cost_ack"
METHOD = "finite-terminal-rejection-full-liability-hold-v1"
RUN_KIND = "luna_budget_held_cost_recovery_run"
FINISH_KIND = "luna_budget_held_cost_recovery_finish"
RECOVERY_METHOD = "luna-budget-exact-held-cost-recovery-v1"
INPUTS = ("plan", "prior_ack_ref", "stop_result_ref", "diagnostic_ref", "held_assessment_id", "settled_assessment_id")
PRODUCTION = {
    "plan": "5ca47b44989d35bd364dc8a23b04a2509382085641e646ac3a9f5ca01032335f",
    "prior_ack_ref": "7134a16ccfc8ef7a906755595177e2c9db77c25090d7009b407e5357a3e24db9",
    "stop_result_ref": "198722a934de72a2bd47664e0815e8b56cc1775cff2e3301dfd94e55e5102e4d",
    "diagnostic_ref": "971b73162158ebd7eec35c073ea28bf8c3d3a325fe98e25ade1806ef1b14f304",
    "held_assessment_id": "a4ce76d3976b0db7d5efab9fc994092731e0ce201a5a3197c8817b5972452472",
    "settled_assessment_id": "b5bea8f050d313c543dcf803a2d8b57dcd6f286f65cb20316c18f7d7d86158e5",
}


def implementation_hashes() -> dict[str, str]:
    result = diagnostic_method.implementation_hashes()
    for name in ("luna_budget_held_history.py", "luna_budget_held_cost.py", "run_luna_budget_held_cost.py",
                 "run_luna_budget_held_cost_with_key.ps1", "luna_budget_failure_chain.py"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def exact_inputs(engine: Any, value: Json) -> Json:
    inputs = {key: value.get(key) for key in INPUTS}
    if any(not isinstance(item, str) or len(item) != 64 or any(c not in "0123456789abcdef" for c in item)
           for item in inputs.values()) or inputs["held_assessment_id"] == inputs["settled_assessment_id"]:
        raise AuditError("held_cost_exact_explicit_inputs_required")
    if not getattr(engine.transport, "synthetic", False) and inputs != PRODUCTION:
        raise AuditError("held_cost_only_exact_authorized_production_case")
    return inputs


def validate_book(book: BudgetBook, plan_id: str, plan: Json, held: Json) -> None:
    """Allow this one unchanged liability; do not alter or sanitize the book."""
    if (book.frozen or book.authorization_id != STUDY or book.ceiling_nanousd != 150_000_000_000
            or book.operational_limit_nanousd != 120_000_000_000
            or book.price_policy.fingerprint != plan.get("price_fingerprint")
            or book.committed_nanousd > book.operational_limit_nanousd):
        raise AuditError("held_cost_budget_binding_frozen_or_exceeded")
    events = book.to_dict()["events"]
    entries = [book.entry(key) for key in {event["value"]["request_id"] for event in events if event["action"] == "reserve"}]
    anomalies = [entry for entry in entries if entry["status"] in {"unknown", "frozen", "overrun"}]
    if (any(entry["request"]["plan_id"] != plan_id for entry in entries)
            or len(anomalies) != 1 or anomalies[0] != held["entry"]
            or anomalies[0]["request"]["request_id"] != held["custom_id"]):
        raise AuditError("held_cost_new_or_changed_unknown_blocks")
    entry = anomalies[0]
    request, settlement = entry["request"], entry.get("settlement") or {}
    history = [event for event in events if event["value"].get("request_id") == held["custom_id"]]
    if (entry["status"] != "unknown" or entry["accepted"] is not False or entry["charged_nanousd"] != 0
            or entry["reason"] != "missing_or_incomplete_usage" or request["max_output_tokens"] != 4096
            or request["price_fingerprint"] != book.price_policy.fingerprint
            or request["input_count"]["model"] != book.price_policy.model
            or settlement.get("complete") is not False
            or any(settlement.get(key) is not None for key in ("model", "input_tokens", "output_tokens"))
            or entry["reserved_nanousd"] != book.price_policy.cost(request["input_count"]["input_tokens"], 4096)
            or history != held["event_history"] or [event["action"] for event in history] != ["reserve", "settle"]):
        raise AuditError("held_cost_original_full_reservation_must_remain_unchanged")


def check_held_stop(engine: Any, plan_id: str, prior: Json, records: Json) -> None:
    """Preserve both actual old blockers; this is not the settled-only chain."""
    stop, run, finish = records["stop"], records["run"], records["finish"]
    chain.drain.validate_stop_binding(plan_id, stop, records["run_id"], run, finish,
                                     prior["id"], prior, prior["phase_continuation_ref"])
    protocol = engine.ledger.get(run["protocol"], "protocol")["content"]
    latest = engine.latest(chain.recovery.RUN_KIND, plan_id + ":" + prior["id"] + ":recovery-v1")
    implementation = base.implementation_hashes()
    if (records["prior_kind"] != base.ACK_KIND or records["run_kind"] != chain.recovery.RUN_KIND
            or run.get("implementation") != implementation or protocol.get("method") != chain.recovery.METHOD
            or protocol.get("implementation") != implementation
            or any(protocol.get(key) != run.get(key) for key in ("plan", "ack_ref", *chain.INHERITED))
            or latest is None or latest[0] != records["run_id"]
            or finish.get("blockers") != ["prior_technical_or_unknown_assessment", "shared_budget_unknown_or_unresolved_charge"]):
        raise AuditError("held_cost_exact_original_two_blocker_stop_required")


def receipt_json(engine: Any, receipt: Json, action: Json, plan_id: str, policy_id: str) -> Json:
    if (action.get("plan_id") != plan_id or action.get("authorization_id") != STUDY
            or action.get("policy_id") != policy_id or receipt.get("plan_id") != plan_id
            or receipt.get("authorization_id") != STUDY or receipt.get("action_id") != action["action_id"]
            or receipt.get("unknown") is not False or receipt.get("error_type") is not None
            or type(receipt.get("status")) is not int or not 200 <= receipt["status"] < 300 or not receipt.get("body_ref")):
        raise AuditError("held_cost_confirmed_retained_action_required")
    raw = engine.ledger.artifacts.read_bytes(receipt["body_ref"])
    if hashlib.sha256(raw).hexdigest() != receipt["body_sha256"]:
        raise AuditError("held_cost_receipt_hash_changed")
    answer = json.loads(raw)
    if not isinstance(answer, dict):
        raise AuditError("held_cost_object_receipt_required")
    return answer


def verify_dispatch(engine: Any, session: str, plan_id: str, manifest_id: str, manifest: Json,
                    task: Json, attempt: str, entry: Json, checkpoint: Json) -> Json:
    """Trace unique paid dispatch and exact full count evidence, never just N."""
    actions = base._rows(engine, session, base.ACTION_KIND)
    receipts = base._rows(engine, session, base.RECEIPT_KIND)
    creates = [row for row in actions if row.get("phase") == "create"
               and task["custom_id"] in row.get("reserved_request_ids", [])]
    if len(creates) != 1:
        raise AuditError("held_cost_exactly_one_paid_dispatch_required")
    create = creates[0]
    policy = create["policy_id"]
    if (create["action_key"] != "create:" + manifest_id
            or create["reserved_request_ids"] != [row["custom_id"] for row in manifest["tasks"]]
            or create["attempt_ids"] != manifest["attempt_ids"]
            or create["attempt_ids"][create["reserved_request_ids"].index(task["custom_id"])] != attempt):
        raise AuditError("held_cost_exact_create_manifest_attempts_required")
    matching = [row for row in receipts if row["action_id"] == create["action_id"]]
    if len(matching) != 1:
        raise AuditError("held_cost_one_create_receipt_required")
    create_receipt = matching[0]
    answer = receipt_json(engine, create_receipt, create, plan_id, policy)
    exact = engine.ledger.artifacts.read(create["exact_request_ref"])
    body = engine.ledger.artifacts.read(exact["original_body_ref"])
    jobs = [row for row in base._rows(engine, session, base.fast.JOB_KIND, plan_id) if row["manifest"] == manifest_id]
    if (len(jobs) != 1 or jobs[0]["receipt"] != create_receipt["id"] or jobs[0]["job_id"] != answer.get("id")
            or checkpoint["job_id"] != answer.get("id")
            or exact["logical_request"] != {"method": "POST", "path": "/v1/batches"}
            or body.get("endpoint") != "/v1/responses" or body.get("completion_window") != "24h"
            or body.get("metadata") != {"study": STUDY, "plan": plan_id, "corpus": manifest["corpus_id"], "manifest": manifest_id}
            or any(answer.get(key) != body[key] for key in ("input_file_id", "endpoint", "completion_window", "metadata"))):
        raise AuditError("held_cost_create_job_identity_changed")
    uploads = []
    for action in actions:
        if action.get("phase") != "upload" or action.get("plan_id") != plan_id or action.get("policy_id") != policy:
            continue
        for receipt in receipts:
            if receipt["action_id"] != action["action_id"]:
                continue
            result = receipt_json(engine, receipt, action, plan_id, policy)
            if result.get("id") == body["input_file_id"]:
                uploads.append((action, receipt, result))
    if len(uploads) != 1:
        raise AuditError("held_cost_one_exact_upload_required")
    upload, upload_receipt, uploaded = uploads[0]
    exact_upload = engine.ledger.artifacts.read(upload["exact_request_ref"])
    raw = engine.ledger.artifacts.read_bytes(exact_upload["original_body_ref"])
    if (raw != engine.ledger.artifacts.read_bytes(manifest["jsonl_ref"])
            or hashlib.sha256(raw).hexdigest() != exact_upload["logical_request"].get("content_sha256")
            or uploaded.get("bytes") != len(raw) or uploaded.get("purpose") != "batch"):
        raise AuditError("held_cost_uploaded_bytes_changed")
    rows = [json.loads(line) for line in raw.splitlines()]
    if len(rows) != len(manifest["tasks"]) or [row["custom_id"] for row in rows] != create["reserved_request_ids"]:
        raise AuditError("held_cost_uploaded_request_set_changed")
    for row, frozen in zip(rows, manifest["tasks"], strict=True):
        if (set(row) != {"custom_id", "method", "url", "body"} or row["method"] != "POST" or row["url"] != "/v1/responses"
                or canonical(row["body"]).encode() != engine.ledger.artifacts.read_bytes(frozen["request_body_ref"])):
            raise AuditError("held_cost_uploaded_request_bytes_changed")
    paid = engine.ledger.artifacts.read(task["request_body_ref"])
    count_body = canonical(count_request_body(paid)).encode()
    links = [row for row in base._rows(engine, session, "luna_batch_count_consumer") if row.get("custom_id") == task["custom_id"]]
    linked_origins = {link.get("origin_action_id") for link in links}
    counts = []
    for action in actions:
        if action.get("phase") != "count" or action.get("plan_id") != plan_id or action.get("policy_id") != policy:
            continue
        if links and action["action_id"] not in linked_origins:
            continue
        exact_count = engine.ledger.artifacts.read(action["exact_request_ref"])
        if engine.ledger.artifacts.read_bytes(exact_count["original_body_ref"]) != count_body:
            continue
        for receipt in receipts:
            if receipt["action_id"] != action["action_id"] or receipt["body_sha256"] != entry["request"]["input_count"]["receipt_sha256"]:
                continue
            counted = receipt_json(engine, receipt, action, plan_id, policy)
            if (type(counted.get("input_tokens")) is int and counted["input_tokens"] == entry["request"]["input_count"]["input_tokens"]
                    and receipt["provider_request_id"] == entry["request"]["input_count"]["provider_request_id"]):
                counts.append((action, receipt))
    if len(counts) != 1:
        raise AuditError("held_cost_one_exact_count_origin_required")
    count_action, count_receipt = counts[0]
    for link in links:
        if any(link.get(key) != value for key, value in {
                "authorization_id": STUDY, "plan_id": plan_id, "policy_id": policy, "corpus_id": task["corpus_id"],
                "request_body_ref": task["request_body_ref"], "origin_action_id": count_action["action_id"],
                "origin_receipt_id": count_receipt["id"], "input_tokens": entry["request"]["input_count"]["input_tokens"],
                "model_output_reused": False}.items()):
            raise AuditError("held_cost_count_consumer_changed")
    poll_receipt = {**engine.ledger.get(checkpoint["poll_receipt"], base.RECEIPT_KIND), "id": checkpoint["poll_receipt"]}
    poll_actions = [row for row in actions if row["action_id"] == poll_receipt["action_id"]]
    if len(poll_actions) != 1:
        raise AuditError("held_cost_terminal_poll_action_missing")
    terminal = receipt_json(engine, poll_receipt, poll_actions[0], plan_id, policy)
    if (terminal.get("status") != "completed" or terminal.get("id") != jobs[0]["job_id"]
            or any(terminal.get(key) != answer.get(key) for key in ("input_file_id", "endpoint", "completion_window", "metadata"))):
        raise AuditError("held_cost_completed_provider_job_required")
    return {"create_action": create["id"], "create_receipt": create_receipt["id"], "upload_receipt": upload_receipt["id"],
            "count_action": count_action["id"], "count_receipt": count_receipt["id"], "poll_receipt": poll_receipt["id"],
            "job_id": jobs[0]["job_id"], "policy_id": policy, "terminal": terminal}


def validate_terminal_rejection(row: Json, assessment: Json) -> None:
    response = row.get("response") or {}
    body = response.get("body") or {}
    error = body.get("error") or {}
    if (row.get("error") is not None or response.get("status_code") != 400
            or error.get("code") != "invalid_prompt" or error.get("type") != "invalid_request_error"
            or not response.get("request_id") or response["request_id"] != assessment.get("request_id")
            or any(body.get(key) is not None for key in ("model", "usage", "output", "status", "incomplete_details"))
            or assessment.get("status") != "error" or assessment.get("technical_failure") is not True
            or assessment.get("missing") is not False or assessment.get("accepted") is not False
            or assessment.get("human_validated") is not False
            or any(assessment.get(key) is not None for key in ("model", "usage", "output"))):
        raise AuditError("held_cost_only_exact_terminal_invalid_prompt_without_usage")


def verify_held_failure(engine: Any, session: str, plan_id: str, assessment_id: str, book: BudgetBook) -> Json:
    require_active(engine, session)
    engine.ledger.append(session, "budget.held_cost.raw_proof.inspection.intended", {"plan": plan_id, "assessment": assessment_id,
        "scope": "Unique retained HTTP400 invalid_prompt, terminal attempt/job, exact dispatch/count/body and full unchanged unknown reservation"})
    assessment = engine.ledger.get(assessment_id, base.ASSESSMENT_KIND)
    manifest_id = assessment["manifest"]
    manifest = engine.ledger.get(manifest_id, base.MANIFEST_KIND)
    matches = [(task, attempt) for task, attempt in zip(manifest["tasks"], manifest["attempt_ids"], strict=True)
               if task["custom_id"] == assessment["custom_id"]]
    if len(matches) != 1 or manifest.get("plan") != plan_id or manifest.get("phase") != "bulk":
        raise AuditError("held_cost_exact_bulk_task_required")
    task, attempt = matches[0]
    entry = book.entry(task["custom_id"])
    request = engine.ledger.artifacts.read(task["request_body_ref"])
    request_bytes = engine.ledger.artifacts.read_bytes(task["request_body_ref"])
    if (assessment.get("plan") != plan_id or assessment.get("attempt") != attempt
            or assessment.get("corpus_id") != task["corpus_id"] or assessment.get("request") != task["request_body_ref"]
            or assessment.get("packet_ref") != task["packet_ref"] or attempt in engine.ledger.unresolved
            or hashlib.sha256(request_bytes).hexdigest() != task["request_body_ref"]
            or entry["request"]["request_sha256"] != task["request_body_ref"]
            or entry["request"]["corpus_id"] != task["corpus_id"] or entry["request"]["plan_id"] != plan_id
            or entry["request"]["task_id"] != task["custom_id"]
            or request.get("model") != book.price_policy.model or request.get("model") != "gpt-6-luna"
            or request.get("max_output_tokens") != 4096):
        raise AuditError("held_cost_request_attempt_or_model_binding_changed")
    sql = "SELECT * FROM attempts WHERE task_key=?"
    engine.ledger.append(session, "budget.held_cost.attempt.inspection.intended", {"sql": sql, "parameters": [task["custom_id"]]})
    attempts = engine.ledger.db.execute(sql, (task["custom_id"],)).fetchall()
    if (len(attempts) != 1 or attempts[0]["id"] != attempt or attempts[0]["status"] != "error"
            or attempts[0]["result_id"] != assessment_id or attempts[0]["response_ref"] != assessment["response"]
            or any(value.get("task_key") == task["custom_id"] for value in engine.ledger.unresolved.values())):
        raise AuditError("held_cost_unique_completed_attempt_required")
    saved = engine.latest(base.PARSE_KIND, manifest_id)
    if saved is None:
        raise AuditError("held_cost_parse_checkpoint_required")
    checkpoint = saved[1]
    if (checkpoint.get("status") != "completed" or checkpoint.get("plan") != plan_id
            or checkpoint.get("manifest") != manifest_id or checkpoint.get("parsed_result") != assessment["parsed_result"]
            or checkpoint.get("job_id") != assessment["job_id"]):
        raise AuditError("held_cost_completed_parse_binding_required")
    dispatch = verify_dispatch(engine, session, plan_id, manifest_id, manifest, task, attempt, entry, checkpoint)
    found = []
    for field, receipt_id in checkpoint["download_receipts"].items():
        receipt = {**engine.ledger.get(receipt_id, base.RECEIPT_KIND), "id": receipt_id}
        action = [row for row in base._rows(engine, session, base.ACTION_KIND) if row["action_id"] == receipt["action_id"]]
        if (len(action) != 1 or receipt.get("status") != 200 or receipt.get("unknown") is not False
                or receipt.get("plan_id") != plan_id or receipt.get("authorization_id") != STUDY
                or action[0].get("policy_id") != dispatch["policy_id"]):
            raise AuditError("held_cost_download_receipt_invalid")
        exact = engine.ledger.artifacts.read(action[0]["exact_request_ref"])
        if exact["logical_request"] != {"method": "GET", "path": "/v1/files/" + dispatch["terminal"][field] + "/content"}:
            raise AuditError("held_cost_download_terminal_file_changed")
        raw = engine.ledger.artifacts.read_bytes(receipt["body_ref"])
        if hashlib.sha256(raw).hexdigest() != receipt["body_sha256"]:
            raise AuditError("held_cost_download_hash_changed")
        for line in raw.splitlines():
            row = json.loads(line)
            if row.get("custom_id") == task["custom_id"]:
                found.append((row, line, receipt))
    if len(found) != 1:
        raise AuditError("held_cost_unique_provider_error_row_required")
    row, line, receipt = found[0]
    validate_terminal_rejection(row, assessment)
    response = row["response"]
    original = engine.ledger.artifacts.read(assessment["response"])
    parsed = base.parse_batch_results_phase_aware(line + b"\n", None, {task["custom_id"]: {
        "packet": engine.ledger.artifacts.read(task["packet_ref"]), "body": request}})["items"][0]
    if (parsed != original or parsed.get("errors") != assessment.get("errors") or parsed.get("usage_complete") is not False
            or entry["settlement"].get("receipt_sha256") != assessment["response"]
            or entry["settlement"].get("request_sha256") != assessment["request"]
            or entry["settlement"].get("provider_request_id") != response["request_id"]):
        raise AuditError("held_cost_retained_parse_or_unknown_settlement_changed")
    history = [event for event in book.to_dict()["events"] if event["value"].get("request_id") == task["custom_id"]]
    proof = {"assessment": assessment_id, "custom_id": task["custom_id"], "manifest": manifest_id, "attempt": attempt,
        "request": task["request_body_ref"], "response": assessment["response"], "errors": assessment["errors"],
        "provider_file_ref": receipt["body_ref"], "download_receipt": receipt["id"],
        "raw_line_sha256": hashlib.sha256(line).hexdigest(), "dispatch": dispatch, "entry": entry, "event_history": history,
        "failure_kind": "terminal_invalid_prompt_still_failed_full_cost_unknown", "retry_allowed": False, "accepted_output": False}
    validate_book(book, plan_id, engine.ledger.get(plan_id, base.PLAN_KIND), proof)
    if not getattr(engine.transport, "synthetic", False) and (
            proof["assessment"] != PRODUCTION["held_assessment_id"]
            or task["custom_id"] != "luna_d50e412c3a62ecf3899e5f2981146f0d245ee1fe22125549ed0f47e61d82648b"
            or task["request_body_ref"] != "0cc065e90dff38d051eab8733bb5993f7df6d030b58e6739aee4643559d60fd5"
            or entry["reserved_nanousd"] != 1_402_432 or entry["request"]["input_count"]["input_tokens"] != 4015
            or book.price_policy.fingerprint != "d5e85da46d6ca73d9e4065dc4306f03374738337cca3963e9f39ca3e1129ea6d"):
        raise AuditError("held_cost_authorized_exact_request_or_hold_changed")
    return proof


def verify_case(engine: Any, session: str, inputs: Json, *, historical: Json | None = None) -> Json:
    require_active(engine, session)
    plan_id = inputs["plan"]
    plan = engine.ledger.get(plan_id, base.PLAN_KIND)
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None:
        raise AuditError("held_cost_existing_shared_book_required")
    book, state = saved
    held = verify_held_failure(engine, session, plan_id, inputs["held_assessment_id"], book)
    prior, phase = verify_history(engine, session, plan_id, inputs["prior_ack_ref"], book)
    records = chain.stopped_records(engine, session, inputs["prior_ack_ref"], inputs["stop_result_ref"])
    check_held_stop(engine, plan_id, prior, records)
    settled = base.verify_failure(engine, session, plan_id, inputs["settled_assessment_id"], book)
    if settled["failure_kind"] != "terminal_output_cap_truncation_still_failed":
        raise AuditError("held_cost_exact_new_settled_truncation_required")
    diagnostic = engine.ledger.get(inputs["diagnostic_ref"], base.DIAGNOSTIC_KIND)
    expected = {"plan": plan_id, "stop_result_ref": inputs["stop_result_ref"], "recovery_run": records["run_id"],
        "recovery_finish": records["finish_id"], "prior_ack_ref": prior["id"], "phase_continuation_ref": phase["id"]}
    protocol = engine.ledger.get(diagnostic["protocol"], "protocol")["content"]
    diag_state = historical["budget_state_at_ack"] if historical else state
    if (any(diagnostic.get(key) != value for key, value in expected.items())
            or diagnostic.get("budget_state") != diag_state or diagnostic.get("pending_jobs") != 0
            or diagnostic.get("drain_obstacles") != [] or diagnostic.get("drain_timed_out") is not False
            or diagnostic.get("gateway_stop_ids") != [] or diagnostic.get("budget_frozen") is not False
            or diagnostic.get("reserved_usd") != held["entry"]["reserved_nanousd"] / 1e9
            or diagnostic.get("newly_unacknowledged_technical_assessment_ids") != sorted([held["assessment"], settled["assessment"]])
            or diagnostic.get("previously_acknowledged_assessment_ids") != sorted(prior["assessment_ids"] + [phase["assessment"]])
            or protocol.get("method") != diagnostic_method.METHOD
            or protocol.get("implementation") != diagnostic_method.implementation_hashes()
            or any(protocol.get(key) != expected[key] for key in ("plan", "stop_result_ref", "prior_ack_ref", "phase_continuation_ref"))
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_entries") != [held["entry"]]
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_event_history") != held["event_history"]):
        raise AuditError("held_cost_exact_completed_diagnostic_required")
    failures = sorted([*prior["failures"], settled, held], key=lambda item: item["assessment"])
    ids = [row["assessment"] for row in failures]
    if len(ids) != len(set(ids)) or {held["custom_id"], settled["custom_id"]} & {row["custom_id"] for row in plan["canary_tasks"]}:
        raise AuditError("held_cost_new_noncanary_disjoint_failures_required")
    assessments = base._rows(engine, session, base.ASSESSMENT_KIND, plan_id)
    bad = {row["id"] for row in assessments if row.get("technical_failure") or row.get("status") not in {"valid", "invalid"}}
    if bad != set(ids) | {phase["assessment"]}:
        raise AuditError("held_cost_every_future_or_unacknowledged_error_blocks")
    obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle", "luna_budget_fast_obstacle",
        "luna_budget_failure_recovery_obstacle", "luna_budget_held_cost_obstacle") for row in base._rows(engine, session, kind, plan_id)]
    if (engine.latest(base.STOP_KIND, STUDY) or base.action_blockers(base._rows(engine, session, base.ACTION_KIND),
            base._rows(engine, session, base.RECEIPT_KIND), obstacles)):
        raise AuditError("held_cost_shared_action_failure_or_gateway_stop")
    if not historical:
        jobs = base._rows(engine, session, base.fast.JOB_KIND, plan_id)
        reconciled = {row["manifest"] for row in base._rows(engine, session, "luna_budget_job_reconciled", plan_id)}
        if book.reserved_nanousd != held["entry"]["reserved_nanousd"] or any(row["manifest"] not in reconciled for row in jobs):
            raise AuditError("held_cost_initial_jobs_must_all_be_reconciled")
        if time.time() >= prior["deadline_epoch"]:
            raise AuditError("held_cost_original_admission_deadline_expired")
    return {**inputs, **{key: prior[key] for key in chain.INHERITED}, "stopped_run": records["run_id"],
        "stopped_finish": records["finish_id"], "held_failure": held, "new_settled_failure": settled,
        "failures": failures, "assessment_ids": ids, "budget_state_at_ack": diag_state, "phase": phase}


def load_ack(engine: Any, session: str, plan_id: str, reference: str) -> Json:
    value = engine.ledger.get(reference, ACK_KIND)
    inputs = exact_inputs(engine, value)
    if (inputs["plan"] != plan_id or value.get("implementation") != implementation_hashes()
            or value.get("authorization_id") != STUDY):
        raise AuditError("held_cost_ack_immutable_binding_changed")
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (protocol.get("method") != METHOD or protocol.get("implementation") != implementation_hashes()
            or any(protocol.get(key) != item for key, item in inputs.items())):
        raise AuditError("held_cost_registered_ack_protocol_changed")
    checked = verify_case(engine, session, inputs, historical=value)
    if any(value.get(key) != item for key, item in checked.items()):
        raise AuditError("held_cost_registered_exact_proof_changed")
    return {**value, "id": reference}


class HeldAcknowledgmentResearch(base.ExecutionResearch):
    @audited_handler
    def register_acknowledgment(self: base.ExecutionResearch, session: str, context: Context, data: Json) -> Json:
        inputs = exact_inputs(self, data)
        plan = self.ledger.get(inputs["plan"], base.PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != base.fast.core.contract_digest():
            raise AuditError("held_cost_original_frozen_plan_required")
        key = inputs["plan"] + ":" + inputs["stop_result_ref"]
        existing = self.latest(ACK_KIND, key)
        if existing:
            if any(existing[1].get(name) != value for name, value in inputs.items()):
                raise AuditError("held_cost_exact_existing_ack_inputs_changed")
            load_ack(self, session, inputs["plan"], existing[0])
            return present(self, session, "luna_budget_held_cost_registration", {"ack_ref": existing[0], **existing[1], "reused": True},
                "Reused the exact held-cost acknowledgment. Full unknown liability, failed outputs, all prior stops and the original deadline remain unchanged; zero new calls or retries.")
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":exact-held-liability",
            "content": {"method": METHOD, **inputs, "versions": plan["versions"], "implementation": implementation_hashes(),
                "rules": "One exact confirmed terminal HTTP400 invalid_prompt remains failed with unavailable model/usage and its full original worst-case reservation held unchanged. Independently verify the one new settled truncation and all prior historical proofs. No release, zero-cost inference, retry, reformulation, rerouting, acceptance, future-error exemption, budget reset or deadline extension. Untouched requests only; every other anomaly blocks."}})["id"]
        value = verify_case(self, session, inputs)
        value.update(authorization_id=STUDY, protocol=protocol, implementation=implementation_hashes(),
            approved_by="user:current-chat", instruction="keep running and fix problems", new_models=0, paid_retries=0,
            unknown_cost_released=False, original_errors_and_stops_unchanged=True, accepted_events=0)
        reference = self.ledger.record(session, ACK_KIND, key, value)
        return present(self, session, "luna_budget_held_cost_registration", {"ack_ref": reference, **value},
            f"Registered exactly one historical terminal HTTP400 rejection with its full ${value['held_failure']['entry']['reserved_nanousd'] / 1e9:.9f} unknown liability still reserved, plus one fully charged terminal truncation. Both remain failed and unusable. No model/usage was inferred, no cost released and no article retried or reformulated. All older stops and the same $120 operating/$150 maximum and original deadline remain. Every new technical/unknown failure still stops. Zero provider calls in registration. Exact protected presentation retained; record_presentation does not support this technical kind.")
