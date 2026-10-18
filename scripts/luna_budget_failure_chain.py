"""Append a finite diagnosed failure set to a verified stopped recovery lineage.

Prior acknowledgments, failed outputs and terminal runs remain unchanged. Every
new named row must independently satisfy the frozen raw/settled-failure proof.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, require_active
from newsresearch.runtime import audited_handler

import drain_luna_budget_recovery as drain
from execute_luna_budget_batch import ExecutionResearch, PLAN_KIND
from execute_luna_budget_wave import action_blockers
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
from luna_budget_continuation import acknowledged_assessment, load_continuation
import luna_budget_failure_ack as base
import run_luna_budget_recovery as recovery

ACK_KIND = "luna_budget_chained_failed_extraction_ack"
METHOD = "finite-settled-terminal-failure-chain-v1"
RUN_KIND = "luna_budget_chained_recovery_run"
FINISH_KIND = "luna_budget_chained_recovery_finish"
RECOVERY_METHOD = "luna-budget-chained-failure-recovery-v1"
INHERITED = ("original_run", "original_finish", "phase_continuation_ref", "deadline_epoch", "queue_token_cap", "count_workers")


def implementation_hashes() -> dict[str, str]:
    result = drain.implementation_hashes()
    for name in ("luna_budget_failure_chain.py", "run_luna_budget_recovery_chain.py", "run_luna_budget_recovery_chain_with_key.ps1",
                 "drain_luna_budget_recovery_chain.py", "drain_luna_budget_recovery_chain_with_key.ps1"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def finite_ids(values: Any) -> list[str]:
    if (not isinstance(values, list) or not values
            or any(not isinstance(value, str) or len(value) != 64
                   or any(char not in "0123456789abcdef" for char in value) for value in values)
            or len(set(values)) != len(values)):
        raise AuditError("failure_chain_explicit_distinct_assessment_ids_required")
    return sorted(values)


def merge_failures(prior: Json, ids: list[str], failures: list[Json]) -> list[Json]:
    old_ids = finite_ids(prior.get("assessment_ids"))
    if (old_ids != sorted(proof["assessment"] for proof in prior["failures"])
            or finite_ids(ids) != sorted(proof["assessment"] for proof in failures)
            or set(old_ids) & set(ids)):
        raise AuditError("failure_chain_new_ids_must_be_exact_and_disjoint")
    return sorted([*prior["failures"], *failures], key=lambda proof: proof["assessment"])


def record_kind(engine: Any, session: str, reference: str) -> str:
    require_active(engine, session)
    sql = "SELECT kind FROM records WHERE id=?"
    engine.ledger.append(session, "budget.failure_chain.kind.inspection.intended", {"sql": sql, "parameters": [reference]})
    row = engine.ledger.db.execute(sql, (reference,)).fetchone()
    if row is None or row["kind"] not in {base.ACK_KIND, ACK_KIND}:
        raise AuditError("failure_chain_verified_predecessor_kind_required")
    return str(row["kind"])


def load_acknowledgment(engine: Any, session: str, plan_id: str, reference: str,
                       seen: set[str] | None = None) -> Json:
    if reference in (seen or set()):
        raise AuditError("failure_chain_cycle_forbidden")
    if record_kind(engine, session, reference) == base.ACK_KIND:
        return base.load_failure_ack(engine, session, plan_id, reference)
    return load_chain_ack(engine, session, plan_id, reference, seen)


def stopped_records(engine: Any, session: str, prior_ref: str, stop_ref: str) -> Json:
    kind = record_kind(engine, session, prior_ref)
    run_kind, finish_kind = (recovery.RUN_KIND, recovery.FINISH_KIND) if kind == base.ACK_KIND else (RUN_KIND, FINISH_KIND)
    engine.ledger.append(session, "budget.failure_chain.stop.inspection.intended",
        {"prior_ack_ref": prior_ref, "stop_result_ref": stop_ref, "run_kind": run_kind, "finish_kind": finish_kind})
    stop = engine.ledger.get(stop_ref, "luna_budget_fast_status")
    run = engine.ledger.get(stop["run"], run_kind)
    finish = engine.latest(finish_kind, stop["run"])
    if finish is None:
        raise AuditError("failure_chain_explicit_terminal_finish_required")
    return {"prior_kind": kind, "stop": stop, "run": run, "run_id": stop["run"],
            "finish": finish[1], "finish_id": finish[0], "run_kind": run_kind}


def check_stopped_history(engine: Any, plan_id: str, prior: Json, records: Json, *, allow_deadline_drain: bool = False) -> None:
    stop, run, finish = records["stop"], records["run"], records["finish"]
    deadline_drain = allow_deadline_drain and stop.get("finished_reason") == "deadline"
    if deadline_drain:
        # A separate GET-only terminal case. Never rewrite/normalize the stored
        # deadline finish into a technical error, or allow it to create an ack.
        if (stop.get("plan") != plan_id or stop.get("run") != records["run_id"]
                or run.get("plan") != plan_id or run.get("authorization_id") != STUDY
                or run.get("ack_ref") != prior["id"] or stop.get("protocol") != run.get("protocol")
                or finish.get("plan") != plan_id or finish.get("run") != records["run_id"]
                or finish.get("reason") != "deadline" or finish.get("ack_ref") != prior["id"]
                or not stop.get("budget_state") or stop["budget_state"] != finish.get("budget_state")
                or prior.get("plan") != plan_id or prior.get("authorization_id") != STUDY
                or any(run.get(key) != prior[key] for key in INHERITED)
                or finish.get("original_finish") != prior["original_finish"]
                or any(stop.get(key) != run[key] for key in ("deadline_epoch", "queue_token_cap"))
                or any(type(stop.get(key)) is not int or stop[key] < 0
                       for key in ("submitted", "assessments", "pending_requests", "pending_jobs"))
                or stop["submitted"] - stop["assessments"] != stop["pending_requests"]):
            raise AuditError("failure_chain_exact_deadline_drain_binding_required")
    else:
        drain.validate_stop_binding(plan_id, stop, records["run_id"], run, finish,
                                    prior["id"], prior, prior["phase_continuation_ref"])
    legacy = records["prior_kind"] == base.ACK_KIND
    implementation = base.implementation_hashes() if legacy else implementation_hashes()
    method = recovery.METHOD if legacy else RECOVERY_METHOD
    suffix = ":recovery-v1" if legacy else ":recovery-chain-v1"
    protocol = engine.ledger.get(run["protocol"], "protocol")["content"]
    latest = engine.latest(records["run_kind"], plan_id + ":" + prior["id"] + suffix)
    if (run.get("implementation") != implementation or protocol.get("method") != method
            or protocol.get("implementation") != implementation
            or any(protocol.get(key) != run.get(key) for key in ("plan", "ack_ref", *INHERITED))
            or latest is None or latest[0] != records["run_id"]
            or finish.get("blockers") != ([] if deadline_drain else ["prior_technical_or_unknown_assessment"])):
        raise AuditError("failure_chain_exact_error_only_stop_and_frozen_code_required")
    if not legacy and (
            any(item.get(key) != prior[key] for item in (run, protocol)
                for key in ("prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref"))
            or any(finish.get(key) != prior[key] for key in ("prior_ack_ref", "stopped_finish"))):
        raise AuditError("failure_chain_immediate_parent_history_changed")


def check_diagnostic(engine: Any, plan_id: str, diagnostic: Json, value: Json, prior: Json, phase: Json) -> None:
    expected = {"stop_result_ref": value["stop_result_ref"], "recovery_run": value["stopped_run"],
        "recovery_finish": value["stopped_finish"], "prior_ack_ref": value["prior_ack_ref"],
        "phase_continuation_ref": prior["phase_continuation_ref"]}
    previous = sorted(set(prior["assessment_ids"]) | {phase["assessment"]})
    if (diagnostic.get("plan") != plan_id or diagnostic.get("budget_state") != value["budget_state_at_ack"]
            or diagnostic.get("pending_jobs") != 0 or diagnostic.get("reserved_usd") != 0
            or diagnostic.get("budget_frozen") is not False or diagnostic.get("drain_obstacles") != []
            or diagnostic.get("drain_timed_out") is not False
            or diagnostic.get("previously_acknowledged_assessment_ids") != previous
            or diagnostic.get("newly_unacknowledged_technical_assessment_ids") != value["new_assessment_ids"]
            or any(diagnostic.get(key) != expected_value for key, expected_value in expected.items())):
        raise AuditError("failure_chain_exact_drained_diagnostic_required")
    protocol = engine.ledger.get(diagnostic["protocol"], "protocol")["content"]
    if (protocol.get("method") != drain.METHOD + ":retained-diagnostic"
            or protocol.get("plan") != plan_id or protocol.get("implementation") != drain.implementation_hashes()
            or any(protocol.get(key) != expected_value for key, expected_value in expected.items())):
        raise AuditError("failure_chain_diagnostic_protocol_changed")
    if prior.get("prior_ack_ref"):
        binding_ref = diagnostic.get("chain_binding_protocol")
        if not binding_ref or protocol.get("chain_binding_protocol") != binding_ref:
            raise AuditError("failure_chain_drain_binding_protocol_required")
        binding = engine.ledger.get(binding_ref, "protocol")["content"]
        if (binding.get("method") != "luna-budget-stopped-chain-drain-v1"
                or binding.get("implementation") != implementation_hashes()
                or any(binding.get(key) != expected_value for key, expected_value in
                       {"plan": plan_id, "prior_ack_ref": prior["id"], "stop_result_ref": value["stop_result_ref"]}.items())):
            raise AuditError("failure_chain_drain_binding_protocol_changed")


def checked_new_failures(engine: Any, session: str, plan_id: str, ids: list[str], book: Any,
                         diagnostic: Json) -> list[Json]:
    technical = {row["id"]: row for row in diagnostic["technical_rows"]}
    failures = [base.verify_failure(engine, session, plan_id, identifier, book) for identifier in ids]
    for proof in failures:
        reported = technical.get(proof["assessment"], {})
        if (reported.get("custom_id") != proof["custom_id"] or reported.get("errors") != proof["errors"]
                or reported.get("current_cost_status") != "settled"
                or (reported.get("retained_provider_metadata") or {}).get("receipt") != proof["download_receipt"]):
            raise AuditError("failure_chain_reported_failure_does_not_match_raw_proof")
    return failures


def load_chain_ack(engine: Any, session: str, plan_id: str, reference: str,
                   seen: set[str] | None = None) -> Json:
    require_active(engine, session)
    visited = set(seen or ())
    if reference in visited:
        raise AuditError("failure_chain_cycle_forbidden")
    visited.add(reference)
    value = engine.ledger.get(reference, ACK_KIND)
    ids = finite_ids(value.get("new_assessment_ids"))
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("implementation") != implementation_hashes()):
        raise AuditError("failure_chain_immutable_binding_changed")
    prior = load_acknowledgment(engine, session, plan_id, value["prior_ack_ref"], visited)
    records = stopped_records(engine, session, value["prior_ack_ref"], value["stop_result_ref"])
    check_stopped_history(engine, plan_id, prior, records)
    if (value.get("stopped_run") != records["run_id"] or value.get("stopped_finish") != records["finish_id"]
            or any(value.get(key) != prior[key] for key in INHERITED)):
        raise AuditError("failure_chain_history_or_deadline_reset_forbidden")
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (protocol.get("method") != METHOD or protocol.get("implementation") != implementation_hashes()
            or any(protocol.get(key) != value[key] for key in
                   ("plan", "prior_ack_ref", "stop_result_ref", "stopped_run", "stopped_finish", "diagnostic_ref", "new_assessment_ids"))):
        raise AuditError("failure_chain_registered_protocol_changed")
    phase = load_continuation(engine, session, plan_id, prior["phase_continuation_ref"])
    if phase is None or phase["deadline_epoch"] != value["deadline_epoch"]:
        raise AuditError("failure_chain_original_phase_deadline_required")
    book, _ = base.known_budget(engine, session, plan_id)
    diagnostic = engine.ledger.get(value["diagnostic_ref"], base.DIAGNOSTIC_KIND)
    check_diagnostic(engine, plan_id, diagnostic, value, prior, phase)
    failures = checked_new_failures(engine, session, plan_id, ids, book, diagnostic)
    merged = merge_failures(prior, ids, failures)
    if (value.get("new_failures") != failures or value.get("failures") != merged
            or value.get("assessment_ids") != [proof["assessment"] for proof in merged]):
        raise AuditError("failure_chain_finite_proof_changed")
    return {**value, "id": reference}


class ChainedAcknowledgmentResearch(ExecutionResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() or not self.config.offline:
            raise AuditError("failure_chain_original_offline_owner_required")
        return self.register_acknowledgment(session, context, data)

    @audited_handler
    def register_acknowledgment(self: ExecutionResearch, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        ids = finite_ids(data["assessment_ids"])
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != base.fast.core.contract_digest():
            raise AuditError("failure_chain_frozen_plan_changed")
        records = stopped_records(self, session, data["prior_ack_ref"], data["stop_result_ref"])
        key = plan_id + ":" + records["finish_id"]
        existing = self.latest(ACK_KIND, key)
        inputs = {"plan": plan_id, "prior_ack_ref": data["prior_ack_ref"], "stop_result_ref": data["stop_result_ref"],
            "diagnostic_ref": data["diagnostic_ref"], "new_assessment_ids": ids,
            "stopped_run": records["run_id"], "stopped_finish": records["finish_id"]}
        if existing:
            if any(existing[1].get(name) != value for name, value in inputs.items()):
                raise AuditError("failure_chain_existing_registration_inputs_changed")
            load_chain_ack(self, session, plan_id, existing[0])
            return present(self, session, "luna_budget_failure_chain_registration", {"ack_ref": existing[0], **existing[1], "reused": True},
                "Reused the exact existing chained acknowledgment. All failed outputs, charges, previous stops and original deadline remain unchanged. Zero new acknowledgments, provider calls, retries or accepted outputs. Exact protected presentation retained; record_presentation does not support this technical kind.")
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":finite-failure-chain",
            "content": {"method": METHOD, **inputs, "versions": plan["versions"], "implementation": implementation_hashes(),
                "rules": "Append only the explicitly named, fully settled terminal failures to the independently verified predecessor. Preserve raw failures and exact stopped result/run/finish. Require drained current diagnostic and exact complete unacknowledged-ID set. No retries, repaired outputs, new future-error exemption, budget reset or deadline extension; untouched requests only."}})["id"]
        prior = load_acknowledgment(self, session, plan_id, data["prior_ack_ref"])
        check_stopped_history(self, plan_id, prior, records)
        phase = load_continuation(self, session, plan_id, prior["phase_continuation_ref"])
        if phase is None or phase["deadline_epoch"] != prior["deadline_epoch"]:
            raise AuditError("failure_chain_original_phase_deadline_required")
        book, state = base.known_budget(self, session, plan_id)
        value = {**inputs, **{name: prior[name] for name in INHERITED}, "budget_state_at_ack": state}
        diagnostic = self.ledger.get(data["diagnostic_ref"], base.DIAGNOSTIC_KIND)
        check_diagnostic(self, plan_id, diagnostic, value, prior, phase)
        jobs = base._rows(self, session, base.fast.JOB_KIND, plan_id)
        if book.reserved_nanousd != 0 or any(not (checkpoint := self.latest(base.PARSE_KIND, job["manifest"]))
                or checkpoint[1].get("status") != "completed" or checkpoint[1].get("job_id") != job["job_id"] for job in jobs):
            raise AuditError("failure_chain_all_existing_jobs_must_be_reconciled")
        assessments = base._rows(self, session, base.ASSESSMENT_KIND, plan_id)
        bad = {row["id"] for row in assessments if (row.get("technical_failure") or row.get("status") not in {"valid", "invalid"})
               and not acknowledged_assessment(row, phase) and not base.acknowledged_failure(row, prior)}
        if bad != set(ids):
            raise AuditError("failure_chain_exact_current_unacknowledged_set_required")
        failures = checked_new_failures(self, session, plan_id, ids, book, diagnostic)
        if {proof["custom_id"] for proof in failures} & {task["custom_id"] for task in plan["canary_tasks"]}:
            raise AuditError("failure_chain_canary_failure_forbidden")
        merged = merge_failures(prior, ids, failures)
        obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle", "luna_budget_fast_obstacle",
                     "luna_budget_failure_recovery_obstacle", "luna_budget_chained_recovery_obstacle")
                     for row in base._rows(self, session, kind, plan_id)]
        if action_blockers(base._rows(self, session, base.ACTION_KIND), base._rows(self, session, base.RECEIPT_KIND), obstacles):
            raise AuditError("failure_chain_shared_action_or_execution_failure")
        if time.time() >= prior["deadline_epoch"]:
            raise AuditError("failure_chain_original_deadline_expired")
        value.update(authorization_id=STUDY, protocol=protocol, implementation=implementation_hashes(),
            new_failures=failures, failures=merged, assessment_ids=[proof["assessment"] for proof in merged],
            approved_by="user:current-chat", instruction="keep running and fix problems", paid_retries=0,
            original_errors_and_stops_unchanged=True, new_models=0, accepted_events=0)
        reference = self.ledger.record(session, ACK_KIND, key, value)
        return present(self, session, "luna_budget_failure_chain_registration", {"ack_ref": reference, **value},
            f"Appended exactly {len(ids)} proved, fully settled terminal extraction failures to the prior acknowledgment ({len(merged)} finite failed-row IDs total, plus the separate historical phase acknowledgment). All remain failed; no usable output was created or accepted. Original raw responses, charges and every stopped run remain unchanged. Untouched requests may continue with the same $120 operating/$150 maximum, prompt, 4096 output cap and original deadline. Every new unacknowledged technical/unknown error still stops. Zero provider calls or retries in this proof-registration step. Exact protected presentation retained; record_presentation does not support this technical kind.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "prior-ack-ref", "stop-result-ref", "diagnostic-ref"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--assessment-id", dest="assessment_ids", action="append", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ChainedAcknowledgmentResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args), objective="Append exact known failed extractions to the preserved recovery lineage without retry or acceptance", actor=base.fast.ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "ack_ref": result["ack_ref"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
