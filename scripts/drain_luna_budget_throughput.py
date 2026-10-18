"""GET-only reconciliation and retained diagnosis of an exact throughput finish.

Historical policy identity is not inference permission. New unknown/frozen costs
remain visible; no admission predicate, classification, retry or cost release runs.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, require_active
from newsresearch.legacy import sha256
from newsresearch.runtime import audited_handler

import drain_luna_budget_held_cost as previous
import luna_budget_truncation_policy as policy
import run_luna_budget_throughput as throughput
from luna_batch_budget_run import OWNER, ROOT, STUDY, present

METHOD = "luna-budget-terminal-throughput-get-diagnostic-v1"
BINDINGS = ("plan", "stop_result_ref", "policy_ref")
RUN_FIELDS = ("plan", "policy_ref", "implementation", "authorization_id", "deadline_epoch",
    "queue_token_cap", "count_workers", "max_new_requests", "max_new_bytes", "baseline_ack_ref")


def implementation_hashes() -> dict[str, str]:
    result = throughput.implementation_hashes()
    for name in ("drain_luna_budget_throughput.py", "drain_luna_budget_throughput_with_key.ps1"):
        path = "scripts/" + name
        result[path] = sha256(ROOT / path)
    return result


def load_policy_identity(engine: Any, session: str, plan_id: str, reference: str) -> tuple[Json, Json]:
    """Replay historical identity on the real book, without granting admission."""
    require_active(engine, session)
    engine.ledger.append(session, "budget.throughput_drain.policy_identity.intended", {
        "plan": plan_id, "policy_ref": reference, "mode": "identity only; no current admission or classification"})
    value = engine.ledger.get(reference, policy.POLICY_KIND)
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("method") != policy.METHOD or value.get("implementation") != policy.implementation_hashes()
            or value.get("user_amendment") != policy.USER_AMENDMENT or value.get("interpretation") != policy.INTERPRETATION
            or value.get("paid_retries") != 0 or value.get("unknown_cost_released") is not False
            or value.get("accepted_events") != 0 or protocol.get("method") != policy.METHOD
            or any(protocol.get(key) != value[key] for key in
                   ("plan", "inputs", "implementation", "user_amendment", "interpretation"))):
        raise AuditError("throughput_drain_registered_policy_identity_changed")
    before = engine.gateway.load_book(session, STUDY)
    if before is None:
        raise AuditError("throughput_drain_existing_book_required")
    baseline = policy.chain.load_history(engine, session, plan_id, value["baseline_ack_ref"], identity_only=True)
    if (baseline != value.get("baseline") or any(baseline.get(key) != value["inputs"].get(key) for key in policy.chain.INPUTS)
            or any(value.get(key) != baseline[key] for key in policy.chain.held.chain.INHERITED)
            or value.get("original_held_nanousd") != baseline["held_failure"]["entry"]["reserved_nanousd"]):
        raise AuditError("throughput_drain_original_baseline_or_deadline_changed")
    after = engine.gateway.load_book(session, STUDY)
    if after is None or before[1] != after[1] or before[0].to_dict() != after[0].to_dict():
        raise AuditError("throughput_drain_history_changed_current_book")
    previous.verify_held_identity(engine, session, plan_id, baseline, after[0])
    return value, baseline


class ThroughputDiagnosticResearch(previous.HeldDiagnosticResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("throughput_drain_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("throughput_drain_explicit_existing_job_reads_required")
        if any(not isinstance(data.get(key), str) or not data[key] for key in BINDINGS):
            raise AuditError("throughput_drain_explicit_bindings_required")
        plan = self.ledger.get(data["plan"], previous.drain.PLAN_KIND)
        self.cost_diagnostic_protocol = self._version(session, context, {"kind": "protocol",
            "key": STUDY + ":terminal-throughput-get-diagnostic", "content": {
                "method": METHOD, **{key: data[key] for key in BINDINGS}, "versions": plan["versions"],
                "implementation": implementation_hashes(),
                "rules": "Exact terminal wrapped result, latest run/finish and historical throughput policy before GET. Identity-only baseline replay preserves the real book, original held liability and every later unknown/frozen charge. Existing-job status and its observed output/error-file GETs only, including after the unchanged admission deadline. Gateway stops suppress GET. No count, upload, create, retry, new inference authorization, new failure classification, cost release, projection or acceptance."},
            "amend_latest": True, "reason": "Separate read-only diagnosis of the exact terminal throughput run"})["id"]
        return previous.drain.DrainResearch._status(self, session, context, data)

    def bind_stop(self, session: str, data: Json) -> Json:
        require_active(self, session)
        plan_id, reference = data["plan"], data["policy_ref"]
        self.ledger.append(session, "budget.throughput_drain.stop.inspection.intended", {
            **{key: data[key] for key in BINDINGS}, "run_kind": throughput.RUN_KIND,
            "finish_kind": throughput.FINISH_KIND, "lookup": "exact wrapped result run and latest finish; latest plan run"})
        value, baseline = load_policy_identity(self, session, plan_id, reference)
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_throughput_status")
        run_id = stop.get("run")
        if not isinstance(run_id, str) or not run_id or not stop.get("finish_ref") or not stop.get("base_status_ref"):
            raise AuditError("throughput_drain_terminal_wrapped_result_required")
        run = self.ledger.get(run_id, throughput.RUN_KIND)
        finish = self.latest(throughput.FINISH_KIND, run_id)
        latest = self.latest(throughput.RUN_KIND, plan_id + ":" + reference + ":throughput-v1")
        runs = self.rows(session, throughput.RUN_KIND, plan_id)
        protocol = self.ledger.get(run["protocol"], "protocol")["content"]
        base = self.ledger.get(stop["base_status_ref"], "luna_budget_fast_status")
        if (finish is None or finish[0] != stop["finish_ref"] or latest is None or latest[0] != run_id
                or not runs or runs[-1]["id"] != run_id
                or stop.get("plan") != plan_id or stop.get("policy_ref") != reference
                or stop.get("method") != throughput.METHOD or stop.get("protocol") != run.get("protocol")
                or run.get("implementation") != throughput.implementation_hashes()
                or run.get("authorization_id") != STUDY or run.get("policy_ref") != reference
                or run.get("plan") != plan_id or protocol.get("method") != throughput.METHOD
                or any(protocol.get(key) != run[key] for key in RUN_FIELDS)
                or any(stop.get(key) != item for key, item in base.items())):
            raise AuditError("throughput_drain_exact_latest_run_code_and_base_required")
        ended = finish[1]
        if (any(ended.get(key) != run[key] for key in RUN_FIELDS)
                or ended.get("run") != run_id or not ended.get("ended_at")
                or ended.get("reason") not in previous.TERMINAL_REASONS
                or stop.get("finished_reason") != ended["reason"]
                or not stop.get("budget_state") or stop["budget_state"] != ended.get("budget_state")
                or run.get("deadline_epoch") != value["deadline_epoch"]
                or run.get("queue_token_cap") != throughput.QUEUE_CAP or run.get("count_workers") != throughput.COUNT_WORKERS
                or run.get("max_new_requests") != throughput.MAX_NEW_REQUESTS or run.get("max_new_bytes") != throughput.MAX_NEW_BYTES
                or run.get("baseline_ack_ref") != value["baseline_ack_ref"]
                or any(stop.get(key) != run[key] for key in
                    ("deadline_epoch", "queue_token_cap", "count_workers", "max_new_requests", "max_new_bytes", "baseline_ack_ref"))
                or stop.get("original_held_entry") != baseline["held_failure"]["entry"]
                or any(type(stop.get(key)) is not int or stop[key] < 0 for key in
                       ("submitted", "assessments", "pending_requests", "pending_jobs"))
                or stop["submitted"] - stop["assessments"] != stop["pending_requests"]):
            raise AuditError("throughput_drain_exact_finish_hold_schedule_or_coverage_required")
        proof_ids = stop.get("truncation_proof_record_ids")
        classification_ref = stop.get("classification_ref")
        if (not isinstance(proof_ids, list) or len(proof_ids) != len(set(proof_ids))
                or proof_ids != ended.get("truncation_proof_record_ids")
                or classification_ref != ended.get("classification_ref")
                or stop.get("qualifying_truncations") != len(proof_ids)):
            raise AuditError("throughput_drain_exact_failed_proof_scope_required")
        if classification_ref:
            classification = self.ledger.get(classification_ref, "luna_budget_truncation_policy_classification")
            if (classification.get("plan") != plan_id or classification.get("policy_ref") != reference
                    or classification.get("proof_record_ids") != proof_ids
                    or classification.get("raw_statuses_changed") is not False
                    or classification.get("accepted_events") != 0 or classification.get("paid_retries") != 0
                    or classification.get("unknown_cost_released") is not False):
                raise AuditError("throughput_drain_retained_classification_changed")
        elif proof_ids:
            raise AuditError("throughput_drain_classification_required_for_proof_ids")
        current = self.gateway.load_book(session, STUDY)[0]
        historical_ids = set(baseline["assessment_ids"]) | {baseline["phase"]["assessment"]}
        for proof_ref in proof_ids:
            saved = self.ledger.get(proof_ref, policy.PROOF_KIND)
            proof = saved["proof"]
            original = {**self.ledger.get(saved["assessment"], policy.chain.base.ASSESSMENT_KIND), "id": saved["assessment"]}
            if (saved.get("method") != policy.METHOD or saved.get("policy_ref") != reference or saved.get("plan") != plan_id
                    or saved.get("proof_fingerprint") != policy.proof_fingerprint()
                    or saved.get("retained_assessment") != original or saved.get("entry") != current.entry(original["custom_id"])
                    or saved.get("receipt") != self.ledger.get(proof["download_receipt"], policy.chain.base.RECEIPT_KIND)
                    or proof.get("assessment") != saved["assessment"] or proof.get("failure_kind") != "terminal_output_cap_truncation_still_failed"
                    or saved.get("original_status") != "error" or original.get("status") != "error"
                    or any(saved.get(key) is not False for key in ("accepted_output", "retry_allowed", "cost_released_by_policy"))):
                raise AuditError("throughput_drain_prior_failed_proof_identity_changed")
            if original["id"] in historical_ids:
                raise AuditError("throughput_drain_duplicate_historical_failed_identity")
            historical_ids.add(original["id"])
        sql = "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event"
        self.ledger.append(session, "budget.throughput_drain.gateway_stop.inspection.intended", {
            "sql": sql, "parameters": [policy.chain.base.STOP_KIND, STUDY]})
        self.existing_gateway_stop_ids = [row["id"] for row in self.ledger.db.execute(sql, (policy.chain.base.STOP_KIND, STUDY))]
        self.held_ack = baseline
        return {**{key: data[key] for key in BINDINGS}, "throughput_run": run_id, "throughput_finish": finish[0],
            "throughput_base_status_ref": stop["base_status_ref"], "recovery_run": run_id, "recovery_finish": finish[0],
            "prior_ack_ref": value["baseline_ack_ref"], "phase_continuation_ref": baseline["phase_continuation_ref"],
            "submitted_at_stop": stop["submitted"], "budget_state_at_stop": stop["budget_state"],
            "original_stop_unchanged": True, "terminal_reason": ended["reason"], "original_deadline_epoch": value["deadline_epoch"],
            "previously_acknowledged_assessment_ids": sorted(historical_ids),
            "retained_truncation_proof_record_ids": proof_ids, "retained_classification_ref": classification_ref,
            "cost_diagnostic_extension_protocol": self.cost_diagnostic_protocol,
            "cost_diagnostic_extension_implementation": implementation_hashes(),
            "historical_acknowledgments_reused_for_identity_only": True, "inference_continuation_permitted": False,
            "existing_gateway_stop_ids": self.existing_gateway_stop_ids, "new_failure_classifications": 0}

    @audited_handler
    def retained_report(self, session: str, context: Context, plan_id: str, binding: Json) -> Json:
        original = super().retained_report(session, context, plan_id, binding)
        finishes = self.rows(session, throughput.FINISH_KIND, plan_id)
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown"}}
        value.update(throughput_diagnostic_base_ref=original["id"], throughput_finishes=finishes,
            controller_finishes=[*original["controller_finishes"], *finishes])
        return present(self, session, "luna_budget_progress_report", value, original["markdown"] +
            "\nThroughput finishes: " + json.dumps(finishes, ensure_ascii=False) +
            "\nHistorical throughput policy proofs remain failed; this read-only adapter performs no new failure classification or inference admission. Later unknown/frozen costs remain visible and fully retained.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for field in BINDINGS:
        parser.add_argument("--" + field.replace("_", "-"), required=True)
    parser.add_argument("--allow-existing-job-reads", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.allow_existing_job_reads:
        parser.error("--allow-existing-job-reads is required; new inference is forbidden")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ThroughputDiagnosticResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Reconcile existing jobs of the exact terminal throughput run and preserve all failed and unknown outcomes", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "throughput_run", "throughput_finish", "policy_ref",
            "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "current_cost_admission_blocked")}), flush=True)
        return 2 if result["current_cost_admission_blocked"] else int(bool(result["pending_jobs"] or result["drain_obstacles"]))
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
