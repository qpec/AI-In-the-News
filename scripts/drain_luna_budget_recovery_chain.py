"""GET-only drain of an explicitly stopped chained recovery, including after expiry.

New run-binding protocol; frozen drain network/reconciliation/report mechanics.
This does not acknowledge failures, restart admission or extend its deadline.
"""
from __future__ import annotations

import argparse
import json
import sys

from newsresearch.common import AuditError, Config, Context, Json, ResearchError
from newsresearch.runtime import audited_handler

import drain_luna_budget_recovery as frozen
from execute_luna_budget_batch import PLAN_KIND
from luna_batch_budget_run import OWNER, STUDY
from luna_budget_continuation import load_continuation
import luna_budget_failure_chain as chain

METHOD = "luna-budget-stopped-chain-drain-v1"


class ChainedDrainResearch(frozen.DrainResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("chain_drain_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("chain_drain_explicit_existing_job_reads_required")
        plan = self.ledger.get(data["plan"], PLAN_KIND)
        self.chain_binding_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":stopped-chain-drain-binding",
            "content": {"method": METHOD, "plan": data["plan"], "versions": plan["versions"],
                "implementation": chain.implementation_hashes(), "prior_ack_ref": data["prior_ack_ref"],
                "stop_result_ref": data["stop_result_ref"],
                "rules": "Verify the exact chained acknowledgment and its stopped chained run/finish before inherited GET-only drain. Reuse frozen action, reconciliation, policy and retained-report mechanics. No inference, reservations, retries, acknowledgment, stop clearing or deadline extension. GET-only reconciliation of existing jobs remains allowed after the admission deadline."},
            "amend_latest": True, "reason": "Explicit stopped-chain binding with unchanged existing-job GET-only mechanics"})["id"]
        return super()._status(session, context, data)

    def bind_stop(self, session: str, data: Json) -> Json:
        plan_id = data["plan"]
        prior = chain.load_chain_ack(self, session, plan_id, data["prior_ack_ref"])
        records = chain.stopped_records(self, session, data["prior_ack_ref"], data["stop_result_ref"])
        if records["prior_kind"] != chain.ACK_KIND:
            raise AuditError("chain_drain_chained_predecessor_required")
        chain.check_stopped_history(self, plan_id, prior, records, allow_deadline_drain=True)
        phase = load_continuation(self, session, plan_id, prior["phase_continuation_ref"])
        if phase is None or phase["deadline_epoch"] != prior["deadline_epoch"]:
            raise AuditError("chain_drain_original_phase_deadline_required")
        # Deliberately no wall-clock admission check: retrieving existing results
        # is still necessary after expiry; the inherited action gate forbids POST.
        return {"stop_result_ref": data["stop_result_ref"], "recovery_run": records["run_id"],
            "recovery_finish": records["finish_id"], "prior_ack_ref": data["prior_ack_ref"],
            "phase_continuation_ref": prior["phase_continuation_ref"],
            "submitted_at_stop": records["stop"]["submitted"], "budget_state_at_stop": records["stop"]["budget_state"],
            "original_stop_unchanged": True, "chain_binding_protocol": self.chain_binding_protocol,
            "previously_acknowledged_assessment_ids": sorted(set(prior["assessment_ids"]) | {phase["assessment"]})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "stop-result-ref", "prior-ack-ref"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--allow-existing-job-reads", action="store_true")
    parser.add_argument("--max-wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not args.allow_existing_job_reads:
        parser.error("--allow-existing-job-reads is required; new inference is forbidden")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"starting_audited_chained_drain": args.plan, "new_inference": False}), flush=True)
    engine = ChainedDrainResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Drain only existing stopped-chain jobs and retain their diagnostic without restarting admission", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "budget_frozen")}), flush=True)
        return 0 if not result["pending_jobs"] and not result["drain_obstacles"] else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
