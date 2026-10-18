"""GET-only stopped-job diagnostics that remain available when costs are unknown.

Historical acknowledgment records bind identity and parser provenance only.
They are not loaded as current inference-admission approvals. The unchanged
gateway, accounting, and paid-controller guards continue to block admission.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys

from newsresearch.common import AuditError, Config, Context, Json, ResearchError
from newsresearch.event_batch_budget import BudgetBook
from newsresearch.event_batch_live_gateway import STOP_KIND
from newsresearch.runtime import audited_handler

import drain_luna_budget_recovery as base
import luna_budget_continuation as phase_history
import luna_budget_failure_ack as failure_history
from luna_batch_budget_run import OWNER, ROOT, STUDY, present

METHOD = "luna-budget-cost-blocked-get-diagnostic-v1"


def implementation_hashes() -> dict[str, str]:
    result = base.implementation_hashes()
    for name in ("diagnose_luna_budget_costs.py", "diagnose_luna_budget_costs_with_key.ps1"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def budget_anomalies(book: BudgetBook, plan_id: str) -> Json:
    """Read the real projection; never settle, release, or replace any entry."""
    events = book.to_dict()["events"]
    entries = [book.entry(key) for key in sorted({event["value"]["request_id"]
        for event in events if event["action"] == "reserve"})]
    if any(entry["request"]["plan_id"] != plan_id for entry in entries):
        raise AuditError("cost_diagnostic_budget_plan_mismatch")
    anomalous = [entry for entry in entries if entry["status"] in {"unknown", "frozen", "overrun"}]
    identifiers = {entry["request"]["request_id"] for entry in anomalous}
    return {"book_frozen": book.frozen, "entry_status_counts": dict(Counter(entry["status"] for entry in entries)),
        "anomalous_entries": anomalous, "anomalous_request_ids": sorted(identifiers),
        "anomalous_event_history": [event for event in events if event["value"].get("request_id") in identifiers],
        "charged_nanousd": book.charged_nanousd, "reserved_nanousd": book.reserved_nanousd,
        "cost_admission_blocked": book.frozen or bool(anomalous), "ordinary_reserved_is_not_unknown": True}


class CostDiagnosticResearch(base.DrainResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("cost_diagnostic_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("cost_diagnostic_explicit_existing_job_reads_required")
        plan = self.ledger.get(data["plan"], base.PLAN_KIND)
        self.cost_diagnostic_protocol = self._version(session, context, {"kind": "protocol",
            "key": STUDY + ":cost-blocked-get-diagnostic", "content": {"method": METHOD,
                "plan": data["plan"], "versions": plan["versions"], "implementation": implementation_hashes(),
                "stop_result_ref": data["stop_result_ref"], "prior_ack_ref": data["prior_ack_ref"],
                "phase_continuation_ref": data["phase_continuation_ref"],
                "rules": "Distinct GET-only diagnostic authorization. Historical immutable stop/run/ack/phase/protocol records bind existing-job and parser identity, not current inference admission. Do not call admission continuation loaders. No new inference, count, upload, create, retry, reservation release, stop clearing, clean-book substitution or configuration change. Keep original Gateway and BudgetBook behavior. A retained Gateway STOP skips all GETs but permits retained diagnosis. Enumerate exact unknown/frozen/overrun costs and raw provider usage; they continue blocking inference."},
            "amend_latest": True, "reason": "Explicit diagnostic scope after admission prerequisite prevented the original GET-only drain"})["id"]
        return super()._status(session, context, data)

    def bind_stop(self, session: str, data: Json) -> Json:
        plan_id, ack_ref, phase_ref = data["plan"], data["prior_ack_ref"], data["phase_continuation_ref"]
        self.ledger.append(session, "budget.cost_diagnostic.history.inspection.intended", {
            "protocol": self.cost_diagnostic_protocol, "plan": plan_id, "stop_result_ref": data["stop_result_ref"],
            "prior_ack_ref": ack_ref, "phase_continuation_ref": phase_ref,
            "purpose": "Exact retained historical identities only; no current inference admission proof",
            "lookups": ["exact stopped-result run and latest recovery finish", "original phase and failure acknowledgment protocols", "original stopped controller records", "historical assessment/proof identities", "gateway stops"]})
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_fast_status")
        run_id = stop["run"]
        run = self.ledger.get(run_id, base.RUN_KIND)
        finish = self.latest(base.FINISH_KIND, run_id)
        if finish is None:
            raise AuditError("cost_diagnostic_terminal_finish_required")
        ack = self.ledger.get(ack_ref, failure_history.ACK_KIND)
        phase = self.ledger.get(phase_ref, phase_history.CONTINUATION_KIND)
        base.validate_stop_binding(plan_id, stop, run_id, run, finish[1], ack_ref, ack, phase_ref)
        if (ack.get("implementation") != base.recovery_hashes()
                or phase.get("implementation") != phase_history.code_hashes()
                or phase.get("plan") != plan_id or phase.get("authorization_id") != STUDY
                or phase.get("deadline_epoch") != ack["deadline_epoch"]
                or failure_history.exact_ids(ack.get("assessment_ids")) != sorted(proof["assessment"] for proof in ack["failures"])):
            raise AuditError("cost_diagnostic_historical_binding_changed")
        ack_protocol = self.ledger.get(ack["protocol"], "protocol")["content"]
        phase_protocol = self.ledger.get(phase["protocol"], "protocol")["content"]
        run_protocol = self.ledger.get(run["protocol"], "protocol")["content"]
        if (ack_protocol.get("method") != failure_history.METHOD
                or any(ack_protocol.get(key) != ack[key] for key in ("plan", "assessment_ids", "diagnostic_ref", "original_run", "original_finish"))
                or phase_protocol.get("method") != "exact-settled-phase-error-continuation-v1"
                or phase_protocol.get("implementation") != phase["implementation"]
                or any(phase_protocol.get(key) != phase[key] for key in ("plan", "proof", "original_run", "original_stop"))
                or run.get("implementation") != base.recovery_hashes()
                or run_protocol.get("method") != base.RECOVERY_METHOD
                or run_protocol.get("implementation") != run["implementation"]
                or any(run_protocol.get(key) != run[key] for key in ("plan", "ack_ref", "original_run", "original_finish", "phase_continuation_ref", "deadline_epoch", "queue_token_cap", "count_workers"))):
            raise AuditError("cost_diagnostic_registered_history_changed")
        latest = self.latest(base.RUN_KIND, plan_id + ":" + ack_ref + ":recovery-v1")
        if latest is None or latest[0] != run_id:
            raise AuditError("cost_diagnostic_exact_latest_recovery_required")
        original_phase_run = self.ledger.get(phase["original_run"], phase_history.RUN_KIND)
        original_phase_stop = self.ledger.get(phase["original_stop"], phase_history.FINISH_KIND)
        original_fast_run = self.ledger.get(ack["original_run"], failure_history.fast.RUN_KIND)
        original_fast_stop = self.ledger.get(ack["original_finish"], failure_history.fast.FINISH_KIND)
        if (original_phase_run.get("plan") != plan_id or original_phase_stop.get("plan") != plan_id
                or original_phase_stop.get("run") != phase["original_run"] or original_phase_stop.get("reason") != "technical_stop"
                or any(original_phase_run.get(key) != phase[key] for key in ("deadline_epoch", "max_per_corpus", "max_runtime_seconds"))
                or original_fast_run.get("plan") != plan_id or original_fast_run.get("authorization_id") != STUDY
                or original_fast_run.get("continuation_ref") != phase_ref
                or original_fast_run.get("deadline_epoch") != phase["deadline_epoch"]
                or original_fast_run.get("implementation") != failure_history.fast.implementation_hashes()
                or original_fast_stop.get("plan") != plan_id or original_fast_stop.get("run") != ack["original_run"]
                or original_fast_stop.get("reason") != "technical_stop"):
            raise AuditError("cost_diagnostic_original_stop_or_deadline_changed")
        proof = self.ledger.get(phase["proof"], phase_history.PROOF_KIND)
        original = self.ledger.get(phase["assessment"], phase_history.ASSESSMENT_KIND)
        if (proof.get("plan") != plan_id or proof.get("original_assessment") != phase["assessment"]
                or proof.get("custom_id") != phase["custom_id"] or proof.get("derived_status") != "valid"
                or proof.get("phase_implementation_sha256") != phase["phase_implementation_sha256"]
                or original.get("plan") != plan_id or original.get("status") != "error"
                or original.get("errors") != ["response:not_single_message"]
                or original.get("custom_id") != phase["custom_id"]):
            raise AuditError("cost_diagnostic_historical_phase_identity_changed")
        for failure in ack["failures"]:
            original = {**self.ledger.get(failure["assessment"], phase_history.ASSESSMENT_KIND), "id": failure["assessment"]}
            if not failure_history.acknowledged_failure(original, ack):
                raise AuditError("cost_diagnostic_historical_failure_identity_changed")
        self.ledger.append(session, "budget.cost_diagnostic.gateway_stops.inspection.intended", {
            "sql": "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event",
            "parameters": [STOP_KIND, STUDY]})
        self.existing_gateway_stop_ids = [row["id"] for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event", (STOP_KIND, STUDY))]
        return {"stop_result_ref": data["stop_result_ref"], "recovery_run": run_id, "recovery_finish": finish[0],
            "prior_ack_ref": ack_ref, "phase_continuation_ref": phase_ref, "submitted_at_stop": stop["submitted"],
            "budget_state_at_stop": stop["budget_state"], "original_stop_unchanged": True,
            "previously_acknowledged_assessment_ids": sorted(set(ack["assessment_ids"]) | {phase["assessment"]}),
            "cost_diagnostic_extension_protocol": self.cost_diagnostic_protocol,
            "cost_diagnostic_extension_implementation": implementation_hashes(),
            "historical_acknowledgments_reused_for_identity_only": True, "inference_continuation_permitted": False,
            "existing_gateway_stop_ids": self.existing_gateway_stop_ids}

    def reconcile(self, session: str, plan_id: str, policy: str, job: Json) -> Json:
        if getattr(self, "existing_gateway_stop_ids", []):
            raise ResearchError("cost_diagnostic_gateway_stop_preserved_no_get")
        return super().reconcile(session, plan_id, policy, job)

    def provider_usage(self, session: str, assessment: Json) -> list[Json]:
        self.ledger.append(session, "budget.cost_diagnostic.provider_usage.inspection.intended", {
            "assessment": assessment["id"], "custom_id": assessment["custom_id"], "manifest": assessment["manifest"],
            "fields": "retained response identity/status/model/error/incomplete_details/usage only; no output text or source packet"})
        checkpoint = self.latest("luna_budget_job_parsed", assessment["manifest"])
        if checkpoint is None:
            return []
        found = []
        for receipt_id in checkpoint[1].get("download_receipts", {}).values():
            receipt = self.ledger.get(receipt_id, "event_batch_live_receipt")
            for line in self.ledger.artifacts.read_bytes(receipt["body_ref"]).splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("custom_id") != assessment["custom_id"]:
                    continue
                response = row.get("response") or {}
                body = response.get("body") or {}
                found.append({"receipt": receipt_id, "file_ref": receipt["body_ref"],
                    "line_sha256": hashlib.sha256(line).hexdigest(), "custom_id": row["custom_id"],
                    "http_status": response.get("status_code"), "row_error": row.get("error"),
                    "request_id": response.get("request_id"),
                    **{key: body.get(key) for key in ("id", "status", "model", "error", "incomplete_details", "usage")}})
        if len(found) > 1:
            raise AuditError("cost_diagnostic_duplicate_provider_row")
        return found

    @audited_handler
    def retained_report(self, session: str, context: Context, plan_id: str, binding: Json) -> Json:
        # Preserve the frozen base report independently before the new cost view.
        original = super().retained_report(session, context, plan_id, binding)
        self.ledger.append(session, "budget.cost_diagnostic.current_budget.inspection.intended", {
            "protocol": self.cost_diagnostic_protocol, "base_report": original["id"],
            "scope": "All current budget statuses; exact anomalous entries and event histories; related retained response usage"})
        saved = self.gateway.load_book(session, STUDY)
        if saved is None or saved[1] != original["budget_state"]:
            raise AuditError("cost_diagnostic_budget_changed_during_report")
        book, state = saved
        anomalies = budget_anomalies(book, plan_id)
        assessments = self.rows(session, "luna_budget_assessment", plan_id)
        details = []
        for entry in anomalies["anomalous_entries"]:
            custom_id = entry["request"]["request_id"]
            linked = [row for row in assessments if row["custom_id"] == custom_id]
            if len(linked) > 1:
                raise AuditError("cost_diagnostic_duplicate_assessment")
            details.append({"custom_id": custom_id, "entry": entry,
                "assessments": [{key: row.get(key) for key in ("id", "corpus_id", "manifest", "job_id", "request", "response", "status", "errors", "usage", "request_id")} for row in linked],
                "retained_provider_usage": [value for row in linked for value in self.provider_usage(session, row)]})
        profile = self._version(session, context, {"kind": "profile", "key": STUDY + ":cost-blocked-get-diagnostic",
            "content": {"mode": "exploratory", "population_estimate": False, "protocol": self.cost_diagnostic_protocol,
                "plan": plan_id, "versions": original["versions"], "unit": "retained request and budget entry, not dossier",
                "denominators": "All reserved identities, every unknown/frozen/overrun entry, original submitted scope"},
            "amend_latest": True, "reason": "Exact cost missingness and retained raw usage without inference admission"})["id"]
        stops = getattr(self, "existing_gateway_stop_ids", [])
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown", "protocol", "profile"}}
        value.update(protocol=self.cost_diagnostic_protocol, profile=profile, base_diagnostic_ref=original["id"],
            base_diagnostic_protocol=original["protocol"], budget_state=state, cost_diagnostics=anomalies,
            cost_anomaly_details=details, current_cost_admission_blocked=anomalies["cost_admission_blocked"] or bool(stops),
            inference_continuation_permitted=False, gateway_stop_ids=stops)
        lines = [original["markdown"], "", f"Current cost entry statuses: {anomalies['entry_status_counts']}. Book frozen: {book.frozen}. "
            f"Exact anomalous request IDs: {anomalies['anomalous_request_ids']}. Gateway stop IDs: {stops}."]
        lines.extend("Cost anomaly (retained exact metadata): " + json.dumps(row, ensure_ascii=False) for row in details)
        lines.append("This diagnostic grants no inference continuation. Unknown/frozen reservations and admission guards remain unchanged. Ordinary reserved/pending entries alone do not trigger the unknown-cost predicate; the exact statuses above identify its retained causes. No repaired costs, retries, accepted events or human validation.")
        return present(self, session, "luna_budget_progress_report", value, "\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--stop-result-ref", required=True)
    parser.add_argument("--prior-ack-ref", required=True)
    parser.add_argument("--phase-continuation-ref", required=True)
    parser.add_argument("--allow-existing-job-reads", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.allow_existing_job_reads:
        parser.error("--allow-existing-job-reads is required; inference continuation is forbidden")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = CostDiagnosticResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Diagnose exact blocked costs and reconcile only existing jobs without inference admission", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "budget_frozen", "current_cost_admission_blocked")}), flush=True)
        if result["current_cost_admission_blocked"]:
            return 2
        return 0 if not result["pending_jobs"] and not result["drain_obstacles"] else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
