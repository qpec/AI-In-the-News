"""Append exact settled truncations without releasing the original unknown hold.

Historical proof loading is distinct from current admission. Every newly named
row is independently replayed; neither a class of errors nor future rows pass.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from newsresearch.common import AuditError, Context, Json, require_active
from newsresearch.runtime import audited_handler

import drain_luna_budget_held_cost as held_drain
import luna_budget_held_cost as held
from luna_batch_budget_run import ROOT, STUDY, present

base = held.base
ACK_KIND = "luna_budget_held_cost_chain_ack"
METHOD = "finite-held-liability-settled-truncation-chain-v1"
RUN_KIND = "luna_budget_held_cost_chain_run"
FINISH_KIND = "luna_budget_held_cost_chain_finish"
RECOVERY_METHOD = "luna-budget-held-cost-chain-recovery-v1"
INPUTS = ("plan", "prior_ack_ref", "stop_result_ref", "diagnostic_ref", "new_assessment_ids")
PARENTS = ("prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref")
OBSTACLES = ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle", "luna_budget_fast_obstacle",
    "luna_budget_failure_recovery_obstacle", "luna_budget_chained_recovery_obstacle",
    "luna_budget_held_cost_obstacle", "luna_budget_held_cost_chain_obstacle")


def implementation_hashes() -> dict[str, str]:
    result = held_drain.implementation_hashes()
    for name in ("luna_budget_held_chain.py", "run_luna_budget_held_chain.py", "run_luna_budget_held_chain_with_key.ps1",
                 "drain_luna_budget_held_chain.py", "drain_luna_budget_held_chain_with_key.ps1"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def kind(engine: Any, session: str, reference: str) -> str:
    require_active(engine, session)
    sql = "SELECT kind FROM records WHERE id=?"
    engine.ledger.append(session, "budget.held_chain.kind.inspection.intended", {"sql": sql, "parameters": [reference]})
    row = engine.ledger.db.execute(sql, (reference,)).fetchone()
    if row is None or row["kind"] not in {held.ACK_KIND, ACK_KIND}:
        raise AuditError("held_chain_exact_predecessor_kind_required")
    return str(row["kind"])


def original_history(engine: Any, session: str, plan_id: str, reference: str, book: Any,
                     *, identity_only: bool) -> Json:
    """Replay the old finite proof, without its old current-wide error predicate."""
    value = engine.ledger.get(reference, held.ACK_KIND)
    inputs = held.exact_inputs(engine, value)
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (inputs["plan"] != plan_id or value.get("authorization_id") != STUDY
            or value.get("implementation") != held.implementation_hashes()
            or protocol.get("method") != held.METHOD or protocol.get("implementation") != value["implementation"]
            or any(protocol.get(key) != item for key, item in inputs.items())
            or value.get("unknown_cost_released") is not False or value.get("paid_retries") != 0):
        raise AuditError("held_chain_original_ack_binding_changed")
    if identity_only:
        held_drain.verify_held_identity(engine, session, plan_id, value, book)
        proof = value["held_failure"]
    else:
        proof = held.verify_held_failure(engine, session, plan_id, inputs["held_assessment_id"], book)
    prior, phase = held.verify_history(engine, session, plan_id, inputs["prior_ack_ref"], book)
    records = held.chain.stopped_records(engine, session, inputs["prior_ack_ref"], inputs["stop_result_ref"])
    held.check_held_stop(engine, plan_id, prior, records)
    settled = base.verify_failure(engine, session, plan_id, inputs["settled_assessment_id"], book)
    if settled["failure_kind"] != "terminal_output_cap_truncation_still_failed":
        raise AuditError("held_chain_original_settled_proof_changed")
    diagnostic = engine.ledger.get(inputs["diagnostic_ref"], base.DIAGNOSTIC_KIND)
    expected = {"plan": plan_id, "stop_result_ref": inputs["stop_result_ref"], "recovery_run": records["run_id"],
        "recovery_finish": records["finish_id"], "prior_ack_ref": prior["id"], "phase_continuation_ref": phase["id"]}
    dp = engine.ledger.get(diagnostic["protocol"], "protocol")["content"]
    if (any(diagnostic.get(key) != item for key, item in expected.items())
            or diagnostic.get("budget_state") != value["budget_state_at_ack"] or diagnostic.get("pending_jobs") != 0
            or diagnostic.get("drain_obstacles") != [] or diagnostic.get("drain_timed_out") is not False
            or diagnostic.get("gateway_stop_ids") != [] or diagnostic.get("budget_frozen") is not False
            or diagnostic.get("reserved_usd") != proof["entry"]["reserved_nanousd"] / 1e9
            or diagnostic.get("newly_unacknowledged_technical_assessment_ids") != sorted([proof["assessment"], settled["assessment"]])
            or diagnostic.get("previously_acknowledged_assessment_ids") != sorted(prior["assessment_ids"] + [phase["assessment"]])
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_entries") != [proof["entry"]]
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_event_history") != proof["event_history"]
            or dp.get("method") != held.diagnostic_method.METHOD
            or dp.get("implementation") != held.diagnostic_method.implementation_hashes()
            or any(dp.get(key) != expected[key] for key in ("plan", "stop_result_ref", "prior_ack_ref", "phase_continuation_ref"))):
        raise AuditError("held_chain_original_diagnostic_changed")
    failures = sorted([*prior["failures"], settled, proof], key=lambda item: item["assessment"])
    checked = {**inputs, **{key: prior[key] for key in held.chain.INHERITED}, "stopped_run": records["run_id"],
        "stopped_finish": records["finish_id"], "held_failure": proof, "new_settled_failure": settled,
        "failures": failures, "assessment_ids": [item["assessment"] for item in failures], "phase": phase}
    if any(value.get(key) != item for key, item in checked.items()):
        raise AuditError("held_chain_original_raw_proof_changed")
    return {**value, "id": reference}


def stopped_records(engine: Any, session: str, plan_id: str, prior: Json, stop_ref: str,
                    *, technical_only: bool) -> Json:
    legacy = kind(engine, session, prior["id"]) == held.ACK_KIND
    run_kind, finish_kind = (held.RUN_KIND, held.FINISH_KIND) if legacy else (RUN_KIND, FINISH_KIND)
    engine.ledger.append(session, "budget.held_chain.stop.inspection.intended", {
        "plan": plan_id, "stop_result_ref": stop_ref, "prior_ack_ref": prior["id"],
        "run_kind": run_kind, "finish_kind": finish_kind, "lookup": "latest finish of exact wrapped result run"})
    stop = engine.ledger.get(stop_ref, "luna_budget_fast_status")
    run_id = stop["run"]
    run = engine.ledger.get(run_id, run_kind)
    saved = engine.latest(finish_kind, run_id)
    if saved is None:
        raise AuditError("held_chain_terminal_finish_required")
    finish_id, finish = saved
    held_drain.validate_terminal_binding(plan_id, stop, run_id, run, finish, prior["id"], prior)
    implementation = held.implementation_hashes() if legacy else implementation_hashes()
    method = held.RECOVERY_METHOD if legacy else RECOVERY_METHOD
    suffix = ":held-cost-recovery-v1" if legacy else ":held-cost-chain-v1"
    latest = engine.latest(run_kind, plan_id + ":" + prior["id"] + suffix)
    protocol = engine.ledger.get(run["protocol"], "protocol")["content"]
    if (run.get("implementation") != implementation or protocol.get("implementation") != implementation
            or protocol.get("method") != method or latest is None or latest[0] != run_id
            or any(protocol.get(key) != run[key] for key in ("plan", "ack_ref", *held.chain.INHERITED, *PARENTS))):
        raise AuditError("held_chain_exact_latest_parent_code_and_lineage_required")
    if technical_only and (finish["reason"] != "technical_stop"
            or finish.get("blockers") != ["prior_technical_or_unknown_assessment"]):
        raise AuditError("held_chain_exact_current_technical_blocker_required")
    return {"stop": stop, "run": run, "run_id": run_id, "finish": finish, "finish_id": finish_id, "legacy": legacy}


def check_diagnostic(engine: Any, plan_id: str, diagnostic: Json, value: Json, prior: Json, records: Json) -> None:
    previous = sorted(set(prior["assessment_ids"]) | {prior["phase"]["assessment"]})
    expected = {"plan": plan_id, "stop_result_ref": value["stop_result_ref"], "prior_ack_ref": prior["id"],
        "held_ack_ref": prior["id"], "held_run_ref": records["run_id"], "held_finish_ref": records["finish_id"],
        "recovery_run": records["run_id"], "recovery_finish": records["finish_id"],
        "phase_continuation_ref": prior["phase_continuation_ref"]}
    proof = prior["held_failure"]
    if (any(diagnostic.get(key) != item for key, item in expected.items())
            or diagnostic.get("budget_state") != value["budget_state_at_ack"]
            or diagnostic.get("pending_jobs") != 0 or diagnostic.get("drain_obstacles") != []
            or diagnostic.get("drain_timed_out") is not False or diagnostic.get("gateway_stop_ids") != []
            or diagnostic.get("budget_frozen") is not False
            or diagnostic.get("reserved_usd") != proof["entry"]["reserved_nanousd"] / 1e9
            or diagnostic.get("previously_acknowledged_assessment_ids") != previous
            or diagnostic.get("newly_unacknowledged_technical_assessment_ids") != value["new_assessment_ids"]
            or diagnostic.get("original_held_entry") != proof["entry"]
            or diagnostic.get("original_held_cost_unchanged") is not True
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_entries") != [proof["entry"]]
            or diagnostic.get("cost_diagnostics", {}).get("anomalous_event_history") != proof["event_history"]):
        raise AuditError("held_chain_exact_drained_diagnostic_required")
    protocol = engine.ledger.get(diagnostic["protocol"], "protocol")["content"]
    method = held_drain.METHOD if records["legacy"] else "luna-budget-terminal-held-chain-get-diagnostic-v1"
    implementation = held_drain.implementation_hashes() if records["legacy"] else implementation_hashes()
    if (protocol.get("method") != method or protocol.get("implementation") != implementation
            or any(protocol.get(key) != expected[key] for key in held_drain.BINDINGS)):
        raise AuditError("held_chain_diagnostic_protocol_changed")


def checked_truncations(engine: Any, session: str, plan_id: str, ids: list[str], book: Any, diagnostic: Json) -> list[Json]:
    proofs = held.chain.checked_new_failures(engine, session, plan_id, ids, book, diagnostic)
    if any(row["failure_kind"] != "terminal_output_cap_truncation_still_failed" for row in proofs):
        raise AuditError("held_chain_only_exact_settled_output_cap_truncations")
    return proofs


def load_history(engine: Any, session: str, plan_id: str, reference: str, *, identity_only: bool = False,
                 seen: set[str] | None = None) -> Json:
    require_active(engine, session)
    visited = set(seen or ())
    if reference in visited:
        raise AuditError("held_chain_cycle_forbidden")
    visited.add(reference)
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None:
        raise AuditError("held_chain_existing_real_book_required")
    book, _ = saved
    if kind(engine, session, reference) == held.ACK_KIND:
        return original_history(engine, session, plan_id, reference, book, identity_only=identity_only)
    value = engine.ledger.get(reference, ACK_KIND)
    ids = held.chain.finite_ids(value.get("new_assessment_ids"))
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("implementation") != implementation_hashes()
            or protocol.get("method") != METHOD or protocol.get("implementation") != value["implementation"]
            or any(protocol.get(key) != value[key] for key in INPUTS)
            or value.get("unknown_cost_released") is not False or value.get("paid_retries") != 0):
        raise AuditError("held_chain_registered_ack_binding_changed")
    prior = load_history(engine, session, plan_id, value["prior_ack_ref"], identity_only=identity_only, seen=visited)
    records = stopped_records(engine, session, plan_id, prior, value["stop_result_ref"], technical_only=True)
    if (value.get("stopped_run") != records["run_id"] or value.get("stopped_finish") != records["finish_id"]
            or any(value.get(key) != prior[key] for key in (*held.chain.INHERITED, "held_failure", "phase"))):
        raise AuditError("held_chain_parent_hold_schedule_changed")
    diagnostic = engine.ledger.get(value["diagnostic_ref"], base.DIAGNOSTIC_KIND)
    check_diagnostic(engine, plan_id, diagnostic, value, prior, records)
    proofs = checked_truncations(engine, session, plan_id, ids, book, diagnostic)
    merged = held.chain.merge_failures(prior, ids, proofs)
    if (value.get("new_failures") != proofs or value.get("failures") != merged
            or value.get("assessment_ids") != [row["assessment"] for row in merged]):
        raise AuditError("held_chain_finite_raw_proof_changed")
    return {**value, "id": reference}


def check_current(engine: Any, session: str, plan_id: str, value: Json, book: Any, *, registration: bool) -> None:
    plan = engine.ledger.get(plan_id, base.PLAN_KIND)
    held.validate_book(book, plan_id, plan, value["held_failure"])
    rows = base._rows(engine, session, base.ASSESSMENT_KIND, plan_id)
    bad = {row["id"] for row in rows if row.get("technical_failure") or row.get("status") not in {"valid", "invalid"}}
    if bad != set(value["assessment_ids"]) | {value["phase"]["assessment"]}:
        raise AuditError("held_chain_every_unacknowledged_error_blocks")
    obstacles = [row for name in OBSTACLES for row in base._rows(engine, session, name, plan_id)]
    if (engine.latest(base.STOP_KIND, STUDY) or base.action_blockers(base._rows(engine, session, base.ACTION_KIND),
            base._rows(engine, session, base.RECEIPT_KIND), obstacles)):
        raise AuditError("held_chain_shared_action_or_execution_failure")
    if registration:
        jobs = base._rows(engine, session, base.fast.JOB_KIND, plan_id)
        reconciled = {row["manifest"] for row in base._rows(engine, session, "luna_budget_job_reconciled", plan_id)}
        if book.reserved_nanousd != value["held_failure"]["entry"]["reserved_nanousd"] or any(row["manifest"] not in reconciled for row in jobs):
            raise AuditError("held_chain_all_existing_jobs_must_be_reconciled")
        if time.time() >= value["deadline_epoch"]:
            raise AuditError("held_chain_original_admission_deadline_expired")


def load_ack(engine: Any, session: str, plan_id: str, reference: str) -> Json:
    if kind(engine, session, reference) != ACK_KIND:
        raise AuditError("held_chain_own_ack_namespace_required")
    value = load_history(engine, session, plan_id, reference)
    book, _ = engine.gateway.load_book(session, STUDY)
    check_current(engine, session, plan_id, value, book, registration=False)
    return value


class HeldChainAcknowledgmentResearch(base.ExecutionResearch):
    @audited_handler
    def register_acknowledgment(self: base.ExecutionResearch, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        ids = held.chain.finite_ids(data.get("assessment_ids"))
        inputs = {key: data[key] for key in INPUTS if key != "new_assessment_ids"}
        inputs["new_assessment_ids"] = ids
        plan = self.ledger.get(plan_id, base.PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != base.fast.core.contract_digest():
            raise AuditError("held_chain_frozen_plan_required")
        key = plan_id + ":" + inputs["stop_result_ref"]
        existing = self.latest(ACK_KIND, key)
        if existing:
            if any(existing[1].get(name) != item for name, item in inputs.items()):
                raise AuditError("held_chain_existing_registration_inputs_changed")
            value = load_ack(self, session, plan_id, existing[0])
            return registration_result(self, session, existing[0], value, reused=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":finite-held-chain",
            "content": {"method": METHOD, **inputs, "implementation": implementation_hashes(), "versions": plan["versions"],
                "rules": "Replay the exact predecessor and original unknown liability; append only explicitly named, fully settled terminal 4096-token truncations in the exact drained diagnostic. All remain failed. Preserve raw outputs, every stop, real shared budget, full held unknown reserve, original deadline and all task identities. Untouched requests only; no retry, semantic repair, release, new error-class exemption or future unknown exception."},
            "amend_latest": True, "reason": "Append an independently proved finite failure set without changing earlier methods"})["id"]
        prior = load_history(self, session, plan_id, inputs["prior_ack_ref"])
        records = stopped_records(self, session, plan_id, prior, inputs["stop_result_ref"], technical_only=True)
        book, state = self.gateway.load_book(session, STUDY)
        value = {**inputs, **{name: prior[name] for name in held.chain.INHERITED}, "held_failure": prior["held_failure"],
            "phase": prior["phase"], "stopped_run": records["run_id"], "stopped_finish": records["finish_id"], "budget_state_at_ack": state}
        diagnostic = self.ledger.get(inputs["diagnostic_ref"], base.DIAGNOSTIC_KIND)
        check_diagnostic(self, plan_id, diagnostic, value, prior, records)
        proofs = checked_truncations(self, session, plan_id, ids, book, diagnostic)
        if {proof["custom_id"] for proof in proofs} & {task["custom_id"] for task in plan["canary_tasks"]}:
            raise AuditError("held_chain_canary_failure_forbidden")
        merged = held.chain.merge_failures(prior, ids, proofs)
        value.update(authorization_id=STUDY, implementation=implementation_hashes(), protocol=protocol,
            new_failures=proofs, failures=merged, assessment_ids=[row["assessment"] for row in merged],
            unknown_cost_released=False, paid_retries=0, accepted_events=0, new_models=0,
            original_errors_and_stops_unchanged=True, approved_by="user:current-chat", instruction="keep running and fix problems")
        check_current(self, session, plan_id, value, book, registration=True)
        reference = self.ledger.record(session, ACK_KIND, key, value)
        return registration_result(self, session, reference, value, reused=False)


def registration_result(engine: Any, session: str, reference: str, value: Json, *, reused: bool) -> Json:
    content = {key: item for key, item in value.items() if key != "id"}
    return present(engine, session, "luna_budget_held_chain_registration", {**content, "ack_ref": reference, "reused": reused},
        f"{'Reused' if reused else 'Registered'} exactly {len(value['new_assessment_ids'])} settled terminal output-cap failures; "
        f"{len(value['assessment_ids'])} finite failed IDs plus the old phase proof. All raw failures remain failed and unaccepted. "
        f"The original unknown liability remains fully held at ${value['held_failure']['entry']['reserved_nanousd']/1e9:.9f}; model and usage remain unavailable. "
        "No retry, inference, cost release, stop clearing, deadline extension or budget reset occurred in registration. Every new error/unknown still stops. "
        "Exact protected presentation retained; record_presentation does not support this technical kind.")
