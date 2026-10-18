"""GET-only diagnosis of a terminal held chain; never grants admission."""
from __future__ import annotations

import argparse
import json
import sys

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, require_active
from newsresearch.runtime import audited_handler

import drain_luna_budget_held_cost as previous
import luna_budget_held_chain as chain
from luna_batch_budget_run import OWNER, STUDY, present

METHOD = "luna-budget-terminal-held-chain-get-diagnostic-v1"
BINDINGS = previous.BINDINGS
EXPLICIT_BINDINGS = previous.EXPLICIT_BINDINGS


class HeldChainDiagnosticResearch(previous.HeldDiagnosticResearch):
    def resolve_terminal_refs(self, session: str, data: Json) -> Json:
        require_active(self, session)
        self.ledger.append(session, "budget.held_chain_drain.resolve.inspection.intended", {
            **{key: data[key] for key in EXPLICIT_BINDINGS}, "run_kind": chain.RUN_KIND,
            "finish_kind": chain.FINISH_KIND, "lookup": "latest finish for exact wrapped result run"})
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_fast_status")
        run_id = stop.get("run")
        if (stop.get("plan") != data["plan"] or stop.get("held_ack_ref") != data["held_ack_ref"]
                or not isinstance(run_id, str) or data.get("held_run_ref") not in (None, run_id)):
            raise AuditError("held_chain_drain_exact_stop_run_required")
        self.ledger.get(run_id, chain.RUN_KIND)
        finish = self.latest(chain.FINISH_KIND, run_id)
        if finish is None or data.get("held_finish_ref") not in (None, finish[0]):
            raise AuditError("held_chain_drain_exact_stop_finish_required")
        binding = {**data, "held_run_ref": run_id, "held_finish_ref": finish[0]}
        reference = self.ledger.record(session, "luna_budget_held_chain_drain_resolution", data["stop_result_ref"], {
            **{key: binding[key] for key in BINDINGS}, "implementation": chain.implementation_hashes(),
            "historical_validation_still_required": True, "inference_continuation_permitted": False})
        return {**binding, "terminal_reference_resolution": reference}

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("held_chain_drain_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("held_chain_drain_explicit_existing_job_reads_required")
        if any(not isinstance(data.get(key), str) or not data[key] for key in EXPLICIT_BINDINGS):
            raise AuditError("held_chain_drain_explicit_bindings_required")
        data = self.resolve_terminal_refs(session, data)
        plan = self.ledger.get(data["plan"], chain.base.PLAN_KIND)
        self.cost_diagnostic_protocol = self._version(session, context, {"kind": "protocol",
            "key": STUDY + ":terminal-held-chain-get-diagnostic", "content": {
                "method": METHOD, **{key: data[key] for key in BINDINGS}, "versions": plan["versions"],
                "terminal_reference_resolution": data["terminal_reference_resolution"],
                "implementation": chain.implementation_hashes(),
                "rules": "Bind an exact terminal held-chain run and replay only historical identities. Preserve the original hold and any new unknown/frozen costs. GET only for existing submitted jobs, including after the original deadline; retained diagnostic reads thereafter. No count/upload/create/retry, new failure acknowledgment, cost release, deadline reset or inference permission. Gateway stops prevent GET; all failures remain visible."},
            "amend_latest": True, "reason": "Existing-job reconciliation and retained diagnosis of a later finite held-chain stop"})["id"]
        return previous.drain.DrainResearch._status(self, session, context, data)

    def bind_stop(self, session: str, data: Json) -> Json:
        require_active(self, session)
        plan_id, reference = data["plan"], data["held_ack_ref"]
        if chain.kind(self, session, reference) != chain.ACK_KIND:
            raise AuditError("held_chain_drain_own_ack_namespace_required")
        ack = chain.load_history(self, session, plan_id, reference, identity_only=True)
        records = chain.stopped_records(self, session, plan_id, ack, data["stop_result_ref"], technical_only=False)
        if records["run_id"] != data["held_run_ref"] or records["finish_id"] != data["held_finish_ref"]:
            raise AuditError("held_chain_drain_resolved_identity_changed")
        sql = "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event"
        self.ledger.append(session, "budget.held_chain_drain.gateway_stop.inspection.intended", {
            "sql": sql, "parameters": [chain.base.STOP_KIND, STUDY]})
        self.existing_gateway_stop_ids = [row["id"] for row in self.ledger.db.execute(sql, (chain.base.STOP_KIND, STUDY))]
        self.held_ack = ack
        return {**{key: data[key] for key in BINDINGS}, "recovery_run": records["run_id"],
            "recovery_finish": records["finish_id"], "prior_ack_ref": reference,
            "historical_prior_ack_ref": ack["prior_ack_ref"], "phase_continuation_ref": ack["phase_continuation_ref"],
            "terminal_reference_resolution": data["terminal_reference_resolution"],
            "submitted_at_stop": records["stop"]["submitted"], "budget_state_at_stop": records["stop"]["budget_state"],
            "original_stop_unchanged": True, "terminal_reason": records["finish"]["reason"],
            "original_deadline_epoch": ack["deadline_epoch"],
            "previously_acknowledged_assessment_ids": sorted(set(ack["assessment_ids"]) | {ack["phase"]["assessment"]}),
            "cost_diagnostic_extension_protocol": self.cost_diagnostic_protocol,
            "cost_diagnostic_extension_implementation": chain.implementation_hashes(),
            "historical_acknowledgments_reused_for_identity_only": True,
            "inference_continuation_permitted": False, "existing_gateway_stop_ids": self.existing_gateway_stop_ids}

    @audited_handler
    def retained_report(self, session: str, context: Context, plan_id: str, binding: Json) -> Json:
        original = super().retained_report(session, context, plan_id, binding)
        finishes = self.rows(session, chain.FINISH_KIND, plan_id)
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown"}}
        value.update(held_chain_diagnostic_base_ref=original["id"], held_chain_finishes=finishes,
            controller_finishes=[*original["controller_finishes"], *finishes])
        return present(self, session, "luna_budget_progress_report", value, original["markdown"] +
            "\nHeld-chain terminal history: " + json.dumps(finishes, ensure_ascii=False) +
            "\nThis GET-only diagnostic grants no acknowledgment or inference admission. New unknown costs remain held and blocking.")


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
    engine = HeldChainDiagnosticResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Diagnose a stopped finite held chain using only existing jobs and retained results", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "current_cost_admission_blocked")}), flush=True)
        return 2 if result["current_cost_admission_blocked"] else int(bool(result["pending_jobs"] or result["drain_obstacles"]))
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
