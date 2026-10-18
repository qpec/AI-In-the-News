"""Reconcile only existing jobs after a terminal held-cost controller run.

This new diagnostic entry point verifies historical identities, not current
admission. Later unknown costs or technical errors remain visible and blocking.
The original deadline may have passed; it is never changed or reauthorized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, require_active
from newsresearch.event_batch_budget import BudgetBook
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import require_receipt
import diagnose_luna_budget_costs as diagnostic
import drain_luna_budget_recovery as drain
import luna_budget_held_cost as held
from luna_batch_budget_run import OWNER, ROOT, STUDY, present

METHOD = "luna-budget-terminal-held-cost-get-diagnostic-v1"
TERMINAL_REASONS = {"technical_stop", "deadline", "complete", "stalled", "budget_deferred", "capacity_deferred"}
BINDINGS = ("plan", "stop_result_ref", "held_ack_ref", "held_run_ref", "held_finish_ref")
EXPLICIT_BINDINGS = ("plan", "stop_result_ref", "held_ack_ref")


def implementation_hashes() -> dict[str, str]:
    result = held.implementation_hashes()
    for name in ("drain_luna_budget_held_cost.py", "drain_luna_budget_held_cost_with_key.ps1"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def validate_terminal_binding(plan_id: str, stop: Json, run_id: str, run: Json,
                              finish: Json, ack_ref: str, ack: Json) -> None:
    reason = finish.get("reason")
    if (reason not in TERMINAL_REASONS or stop.get("finished_reason") != reason
            or stop.get("plan") != plan_id or stop.get("run") != run_id
            or run.get("plan") != plan_id or run.get("authorization_id") != STUDY
            or run.get("ack_ref") != ack_ref or stop.get("held_ack_ref") != ack_ref
            or stop.get("protocol") != run.get("protocol") or not run.get("protocol")
            or finish.get("plan") != plan_id or finish.get("run") != run_id
            or finish.get("ack_ref") != ack_ref or not finish.get("ended_at")
            or not stop.get("budget_state") or stop["budget_state"] != finish.get("budget_state")
            or ack.get("plan") != plan_id or ack.get("authorization_id") != STUDY):
        raise AuditError("held_drain_exact_terminal_run_finish_result_required")
    for key in (*held.chain.INHERITED, "prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref"):
        if key not in ack or run.get(key) != ack[key]:
            raise AuditError("held_drain_original_history_or_deadline_changed")
    if (any(finish.get(key) != ack[key] for key in ("prior_ack_ref", "original_finish", "stopped_finish"))
            or any(stop.get(key) != run[key] for key in ("deadline_epoch", "queue_token_cap"))
            or stop.get("finite_assessment_ids") != ack.get("assessment_ids")
            or stop.get("held_assessment") != ack["held_failure"]["assessment"]
            or stop.get("held_custom_id") != ack["held_failure"]["custom_id"]
            or stop.get("held_cost_status") != "unknown"
            or any(stop.get(key) != ack["held_failure"]["entry"]["reserved_nanousd"]
                   for key in ("held_reserved_nanousd", "held_expected_nanousd"))):
        raise AuditError("held_drain_stopped_hold_or_schedule_changed")
    if (any(type(stop.get(key)) is not int or stop[key] < 0
            for key in ("submitted", "assessments", "pending_requests", "pending_jobs"))
            or stop["submitted"] - stop["assessments"] != stop["pending_requests"]):
        raise AuditError("held_drain_stop_coverage_mismatch")


def verify_held_identity(engine: Any, session: str, plan_id: str, ack: Json, book: BudgetBook) -> None:
    """Check this unchanged historical liability without inspecting other entries."""
    require_active(engine, session)
    proof = ack["held_failure"]
    entry = book.entry(proof["custom_id"])
    events = [event for event in book.to_dict()["events"]
              if event["value"].get("request_id") == proof["custom_id"]]
    request, settlement = entry["request"], entry.get("settlement") or {}
    if (entry != proof["entry"] or events != proof["event_history"]
            or entry["status"] != "unknown" or entry["accepted"] is not False
            or entry["charged_nanousd"] != 0 or entry["reason"] != "missing_or_incomplete_usage"
            or request["plan_id"] != plan_id or request["request_id"] != proof["custom_id"]
            or request["request_sha256"] != proof["request"] or request["max_output_tokens"] != 4096
            or request["price_fingerprint"] != book.price_policy.fingerprint
            or entry["reserved_nanousd"] != book.price_policy.cost(request["input_count"]["input_tokens"], 4096)
            or settlement.get("complete") is not False
            or any(settlement.get(key) is not None for key in ("model", "input_tokens", "output_tokens"))
            or settlement.get("receipt_sha256") != proof["response"]
            or settlement.get("request_sha256") != proof["request"]
            or [event["action"] for event in events] != ["reserve", "settle"]
            or proof.get("retry_allowed") is not False or proof.get("accepted_output") is not False
            or proof.get("failure_kind") != "terminal_invalid_prompt_still_failed_full_cost_unknown"):
        raise AuditError("held_drain_original_full_unknown_hold_changed")
    engine.ledger.append(session, "budget.held_drain.raw_identity.inspection.intended", {
        "assessment": proof["assessment"], "provider_file_ref": proof["provider_file_ref"],
        "download_receipt": proof["download_receipt"], "raw_line_sha256": proof["raw_line_sha256"],
        "scope": "Exact retained historical rejection identity; no admission, output acceptance or cost release"})
    assessment = engine.ledger.get(proof["assessment"], held.base.ASSESSMENT_KIND)
    if (assessment.get("plan") != plan_id or any(assessment.get(key) != proof[key]
            for key in ("custom_id", "manifest", "attempt", "request", "response", "errors"))):
        raise AuditError("held_drain_historical_assessment_changed")
    receipt = engine.ledger.get(proof["download_receipt"], held.base.RECEIPT_KIND)
    raw = engine.ledger.artifacts.read_bytes(proof["provider_file_ref"])
    if (receipt.get("plan_id") != plan_id or receipt.get("authorization_id") != STUDY
            or receipt.get("status") != 200 or receipt.get("unknown") is not False
            or receipt.get("body_ref") != proof["provider_file_ref"]
            or receipt.get("body_sha256") != hashlib.sha256(raw).hexdigest()):
        raise AuditError("held_drain_historical_download_changed")
    rows = [line for line in raw.splitlines() if line.strip()
            and json.loads(line).get("custom_id") == proof["custom_id"]]
    if len(rows) != 1 or hashlib.sha256(rows[0]).hexdigest() != proof["raw_line_sha256"]:
        raise AuditError("held_drain_exact_rejection_row_changed")
    row = json.loads(rows[0])
    held.validate_terminal_rejection(row, assessment)
    if settlement.get("provider_request_id") != row["response"]["request_id"]:
        raise AuditError("held_drain_original_request_identity_changed")


class HeldDiagnosticResearch(diagnostic.CostDiagnosticResearch):
    def resolve_terminal_refs(self, session: str, data: Json) -> Json:
        """Resolve optional IDs from one explicit result inside the audited session."""
        require_active(self, session)
        sql = "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1"
        self.ledger.append(session, "budget.held_drain.terminal_resolution.inspection.intended", {
            **{key: data[key] for key in EXPLICIT_BINDINGS},
            "explicit_overrides": {key: data.get(key) for key in ("held_run_ref", "held_finish_ref")},
            "stop_kind": "luna_budget_fast_status", "run_kind": held.RUN_KIND,
            "finish_lookup_sql": sql, "finish_lookup_kind": held.FINISH_KIND,
            "finish_lookup_key_rule": "Exactly the immutable explicit wrapped stop result's run"})
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_fast_status")
        run_id = stop.get("run")
        if (stop.get("plan") != data["plan"] or stop.get("held_ack_ref") != data["held_ack_ref"]
                or not isinstance(run_id, str) or not run_id
                or data.get("held_run_ref") not in (None, run_id)):
            raise AuditError("held_drain_stop_run_resolution_mismatch")
        # Reading the exact kind prevents a different controller namespace from
        # being used even before the full historical check below.
        self.ledger.get(run_id, held.RUN_KIND)
        self.ledger.append(session, "budget.held_drain.finish_resolution.inspection.intended", {
            "sql": sql, "parameters": [held.FINISH_KIND, run_id], "stop_result_ref": data["stop_result_ref"]})
        finish = self.latest(held.FINISH_KIND, run_id)
        if finish is None:
            raise AuditError("held_drain_resolved_terminal_finish_required")
        if (data.get("held_finish_ref") not in (None, finish[0])
                or finish[1].get("run") != run_id or finish[1].get("plan") != data["plan"]
                or finish[1].get("ack_ref") != data["held_ack_ref"]
                or finish[1].get("reason") not in TERMINAL_REASONS
                or stop.get("finished_reason") != finish[1]["reason"]):
            raise AuditError("held_drain_stop_finish_resolution_mismatch")
        provenance = {**{key: data[key] for key in EXPLICIT_BINDINGS}, "held_run_ref": run_id,
            "held_finish_ref": finish[0], "run_kind": held.RUN_KIND, "finish_kind": held.FINISH_KIND,
            "run_origin": "explicit_override_checked" if data.get("held_run_ref") else "immutable_stop_result.run",
            "finish_origin": "explicit_override_checked" if data.get("held_finish_ref") else "latest_exact_run_finish",
            "finish_lookup_sql": sql, "finish_lookup_parameters": [held.FINISH_KIND, run_id],
            "implementation": implementation_hashes(), "historical_validation_still_required": True,
            "network_calls": 0, "inference_continuation_permitted": False}
        reference = self.ledger.record(session, "luna_budget_held_drain_reference_resolution", data["stop_result_ref"], provenance)
        return {**data, "held_run_ref": run_id, "held_finish_ref": finish[0], "terminal_reference_resolution": reference}

    def action(self, session: str, plan_id: str, policy: str, key: str,
               request: Json, body: bytes | None = None, **kwargs: Any) -> Json:
        if getattr(self, "existing_gateway_stop_ids", []):
            raise ResearchError("held_drain_gateway_stop_preserved_no_get")
        path = request.get("path", "")
        if isinstance(path, str) and path.startswith("/v1/files/"):
            job = getattr(self, "held_current_job", None)
            if not job or job["job_id"] not in getattr(self, "drain_job_ids", set()):
                raise AuditError("held_drain_file_requires_current_existing_job")
            self.ledger.append(session, "budget.held_drain.file_scope.inspection.intended", {
                "job_id": job["job_id"], "kind": "luna_budget_job_observation", "path": path})
            observation = self.latest("luna_budget_job_observation", job["job_id"])
            if observation is None or observation[1].get("plan") != plan_id:
                raise AuditError("held_drain_retained_job_observation_required")
            answer = require_receipt(self.ledger.get(observation[1]["receipt"], held.base.RECEIPT_KIND), self)
            allowed = {"/v1/files/" + answer[name] + "/content" for name in ("output_file_id", "error_file_id")
                       if isinstance(answer.get(name), str) and answer[name]}
            if answer.get("id") != job["job_id"] or path not in allowed:
                raise AuditError("held_drain_file_not_bound_to_existing_job")
        return super().action(session, plan_id, policy, key, request, body, **kwargs)

    def reconcile(self, session: str, plan_id: str, policy: str, job: Json) -> Json:
        self.held_current_job = job
        try:
            return super().reconcile(session, plan_id, policy, job)
        finally:
            self.held_current_job = None

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("held_drain_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("held_drain_explicit_existing_job_reads_required")
        if (any(not isinstance(data.get(key), str) or not data[key] for key in EXPLICIT_BINDINGS)
                or any(data.get(key) is not None and (not isinstance(data[key], str) or not data[key])
                       for key in ("held_run_ref", "held_finish_ref"))):
            raise AuditError("held_drain_exact_explicit_terminal_bindings_required")
        data = self.resolve_terminal_refs(session, data)
        plan = self.ledger.get(data["plan"], drain.PLAN_KIND)
        self.cost_diagnostic_protocol = self._version(session, context, {"kind": "protocol",
            "key": STUDY + ":terminal-held-cost-get-diagnostic", "content": {
                "method": METHOD, **{key: data[key] for key in BINDINGS}, "versions": plan["versions"],
                "terminal_reference_resolution": data["terminal_reference_resolution"],
                "implementation": implementation_hashes(),
                "rules": "After the sole held-cost controller has a retained terminal finish, bind exact run/finish/result/ack and original deadline. Historical identity verification grants no admission and does not call current admission predicates. Existing known-job GETs only, including after deadline; unchanged raw retention, parser and settlement. Existing Gateway STOP forbids GETs. Preserve the original full unknown hold, every later unknown/frozen cost and every failed output. No count/upload/create/retry, new inference acknowledgment, cost release, deadline extension, stop clearing or configuration mutation. Diagnostic phase is retained reads only."},
            "amend_latest": True, "reason": "Separate existing-job reconciliation for the terminal held-cost run"})["id"]
        return drain.DrainResearch._status(self, session, context, data)

    def bind_stop(self, session: str, data: Json) -> Json:
        require_active(self, session)
        plan_id, ack_ref = data["plan"], data["held_ack_ref"]
        self.ledger.append(session, "budget.held_drain.history.inspection.intended", {
            "protocol": self.cost_diagnostic_protocol, **{key: data[key] for key in BINDINGS},
            "scope": "Retained historical identity only, not current cost or technical-failure admission"})
        ack = self.ledger.get(ack_ref, held.ACK_KIND)
        inputs = held.exact_inputs(self, ack)
        implementation = held.implementation_hashes()
        protocol = self.ledger.get(ack["protocol"], "protocol")["content"]
        if (ack.get("plan") != plan_id or ack.get("authorization_id") != STUDY
                or ack.get("implementation") != implementation or protocol.get("method") != held.METHOD
                or protocol.get("implementation") != implementation
                or any(protocol.get(key) != value for key, value in inputs.items())
                or ack.get("unknown_cost_released") is not False or ack.get("paid_retries") != 0):
            raise AuditError("held_drain_registered_ack_or_code_changed")
        # The old diagnostic's identity-only checker never loads admission approvals.
        old = diagnostic.CostDiagnosticResearch.bind_stop(self, session, {
            "plan": plan_id, "stop_result_ref": ack["stop_result_ref"],
            "prior_ack_ref": ack["prior_ack_ref"], "phase_continuation_ref": ack["phase_continuation_ref"]})
        prior = self.ledger.get(ack["prior_ack_ref"], held.base.ACK_KIND)
        phase = self.ledger.get(ack["phase_continuation_ref"], diagnostic.phase_history.CONTINUATION_KIND)
        failures = sorted([*prior["failures"], ack["new_settled_failure"], ack["held_failure"]], key=lambda row: row["assessment"])
        if (ack.get("stopped_run") != old["recovery_run"] or ack.get("stopped_finish") != old["recovery_finish"]
                or any(ack.get(key) != prior[key] for key in held.chain.INHERITED)
                or ack.get("phase") != {**phase, "id": ack["phase_continuation_ref"]}
                or ack["held_failure"].get("assessment") != inputs["held_assessment_id"]
                or ack["new_settled_failure"].get("assessment") != inputs["settled_assessment_id"]
                or ack.get("failures") != failures or ack.get("assessment_ids") != [row["assessment"] for row in failures]
                or len(ack["assessment_ids"]) != len(set(ack["assessment_ids"]))):
            raise AuditError("held_drain_historical_proof_identity_changed")
        historical = self.ledger.get(ack["diagnostic_ref"], held.base.DIAGNOSTIC_KIND)
        historical_protocol = self.ledger.get(historical["protocol"], "protocol")["content"]
        expected = {"plan": plan_id, "stop_result_ref": ack["stop_result_ref"], "recovery_run": ack["stopped_run"],
            "recovery_finish": ack["stopped_finish"], "prior_ack_ref": ack["prior_ack_ref"],
            "phase_continuation_ref": ack["phase_continuation_ref"], "budget_state": ack["budget_state_at_ack"]}
        if (any(historical.get(key) != value for key, value in expected.items())
                or historical.get("pending_jobs") != 0 or historical.get("drain_obstacles") != []
                or historical.get("drain_timed_out") is not False or historical.get("gateway_stop_ids") != []
                or historical.get("cost_diagnostics", {}).get("anomalous_entries") != [ack["held_failure"]["entry"]]
                or historical.get("cost_diagnostics", {}).get("anomalous_event_history") != ack["held_failure"]["event_history"]
                or historical.get("newly_unacknowledged_technical_assessment_ids") != sorted([inputs["held_assessment_id"], inputs["settled_assessment_id"]])
                or historical_protocol.get("method") != diagnostic.METHOD
                or historical_protocol.get("implementation") != diagnostic.implementation_hashes()
                or any(historical_protocol.get(key) != expected[key] for key in ("plan", "stop_result_ref", "prior_ack_ref", "phase_continuation_ref"))):
            raise AuditError("held_drain_original_diagnostic_changed")
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("held_drain_real_current_budget_required")
        verify_held_identity(self, session, plan_id, ack, saved[0])
        settled = held.base.verify_failure(self, session, plan_id, inputs["settled_assessment_id"], saved[0])
        if settled != ack["new_settled_failure"]:
            raise AuditError("held_drain_original_settled_proof_changed")
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_fast_status")
        run = self.ledger.get(data["held_run_ref"], held.RUN_KIND)
        finish = self.ledger.get(data["held_finish_ref"], held.FINISH_KIND)
        validate_terminal_binding(plan_id, stop, data["held_run_ref"], run, finish, ack_ref, ack)
        latest_run = self.latest(held.RUN_KIND, plan_id + ":" + ack_ref + ":held-cost-recovery-v1")
        latest_finish = self.latest(held.FINISH_KIND, data["held_run_ref"])
        run_protocol = self.ledger.get(run["protocol"], "protocol")["content"]
        if (latest_run is None or latest_run[0] != data["held_run_ref"]
                or latest_finish is None or latest_finish[0] != data["held_finish_ref"]
                or run.get("implementation") != implementation or run_protocol.get("implementation") != implementation
                or run_protocol.get("method") != held.RECOVERY_METHOD
                or any(run_protocol.get(key) != run[key] for key in (
                    "plan", "ack_ref", *held.chain.INHERITED, "prior_ack_ref", "stopped_run", "stopped_finish", "stop_result_ref"))):
            raise AuditError("held_drain_exact_latest_frozen_controller_required")
        self.held_ack = ack
        return {**{key: data[key] for key in BINDINGS}, "recovery_run": data["held_run_ref"],
            "terminal_reference_resolution": data.get("terminal_reference_resolution"),
            "recovery_finish": data["held_finish_ref"], "prior_ack_ref": ack_ref,
            "historical_prior_ack_ref": ack["prior_ack_ref"], "phase_continuation_ref": ack["phase_continuation_ref"],
            "submitted_at_stop": stop["submitted"], "budget_state_at_stop": stop["budget_state"],
            "original_stop_unchanged": True, "terminal_reason": finish["reason"], "original_deadline_epoch": ack["deadline_epoch"],
            "previously_acknowledged_assessment_ids": sorted(set(ack["assessment_ids"]) | {phase["assessment"]}),
            "cost_diagnostic_extension_protocol": self.cost_diagnostic_protocol,
            "cost_diagnostic_extension_implementation": implementation_hashes(),
            "historical_acknowledgments_reused_for_identity_only": True, "inference_continuation_permitted": False,
            "existing_gateway_stop_ids": self.existing_gateway_stop_ids}

    @audited_handler
    def retained_report(self, session: str, context: Context, plan_id: str, binding: Json) -> Json:
        original = super().retained_report(session, context, plan_id, binding)
        saved = self.gateway.load_book(session, STUDY)
        if saved is None or saved[1] != original["budget_state"]:
            raise AuditError("held_drain_budget_changed_during_report")
        verify_held_identity(self, session, plan_id, self.held_ack, saved[0])
        finishes = self.rows(session, held.FINISH_KIND, plan_id)
        proof = self.held_ack["held_failure"]
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown"}}
        value.update(held_diagnostic_base_ref=original["id"], held_controller_finishes=finishes,
            controller_finishes=[*original["controller_finishes"], *finishes],
            original_held_assessment=proof["assessment"], original_held_custom_id=proof["custom_id"],
            original_held_entry=saved[0].entry(proof["custom_id"]), original_held_cost_unchanged=True)
        text = original["markdown"] + "\nHeld-cost controller finishes: " + json.dumps(finishes, ensure_ascii=False)
        text += (f"\nOriginal held rejection {proof['assessment']} / {proof['custom_id']} remains unknown with "
            f"{proof['entry']['reserved_nanousd']} nanoUSD fully reserved. Original deadline {binding['original_deadline_epoch']} "
            "is unchanged. Historical acknowledgment identities do not grant admission: every new error and unknown cost remains explicit. "
            "This post-stop adapter performs no inference or retries, even after the deadline.")
        return present(self, session, "luna_budget_progress_report", value, text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in BINDINGS:
        parser.add_argument("--" + field.replace("_", "-"), required=field in EXPLICIT_BINDINGS)
    parser.add_argument("--allow-existing-job-reads", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.allow_existing_job_reads:
        parser.error("--allow-existing-job-reads is required; inference continuation is forbidden")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = HeldDiagnosticResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Reconcile only existing jobs after the exact held-cost controller stopped and diagnose all retained costs", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "held_ack_ref", "held_run_ref", "held_finish_ref", "terminal_reference_resolution", "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "current_cost_admission_blocked")}), flush=True)
        return 2 if result["current_cost_admission_blocked"] else int(bool(result["pending_jobs"] or result["drain_obstacles"]))
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
