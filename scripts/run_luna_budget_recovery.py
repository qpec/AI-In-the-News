"""Continue untouched Batch work after a finite, proven failed-row acknowledgment.

The frozen fast-v1 implementation and its terminal record are not edited or
hidden. This runner reuses its data-plane methods and owns a new explicit run.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError
from newsresearch.legacy import sha256
from newsresearch.runtime import audited_handler

from luna_batch_budget_run import OWNER, ROOT, STUDY
from luna_budget_continuation import acknowledged_assessment, load_continuation
from luna_budget_failure_ack import FailureAcknowledgmentResearch, acknowledged_failure, implementation_hashes, load_failure_ack
from poll_luna_budget_batch import ReconciliationResearch
from project_luna_budget_results import ProjectionResearch
import run_luna_budget_fast as fast

METHOD = "luna-budget-finite-failure-recovery-v1"
RUN_KIND = "luna_budget_failure_recovery_run"
FINISH_KIND = "luna_budget_failure_recovery_finish"


def recovery_gate(blockers: list[str], assessments: list[Json], phase: Json, ack: Json) -> list[str]:
    """Keep every row and blocker; exempt only precisely identified historical errors."""
    bad = [row for row in assessments if row.get("technical_failure") or row.get("status") not in {"valid", "invalid"}]
    covered = all(acknowledged_assessment(row, phase) or acknowledged_failure(row, ack) for row in bad)
    return [value for value in blockers if not (value == "prior_technical_or_unknown_assessment" and covered)]


def cycle_operation(*, startup_observed: bool, startup_pending: bool, pending: bool,
                    staged: bool, unmanifested: bool, pressure: str | None, poll_due: bool) -> str:
    """The same fill/wait policy as fast-v1, explicitly testable at its boundary."""
    startup = not startup_observed and startup_pending
    if pending and (startup or pressure or not staged and not unmanifested) and poll_due:
        return "reconcile"
    if startup or pressure or not staged and not unmanifested:
        return "wait"
    return "submit" if staged else "stage"


def validate_run_binding(old: Json, binding: Json) -> None:
    if any(old.get(name) != value for name, value in binding.items()):
        raise AuditError("recovery_run_binding_changed_no_deadline_or_budget_reset")


def resolve_ack_reference(engine: fast.FastResearch, session: str, context: Context, data: Json) -> str:
    """No nested execute/preflight: durable proof registration precedes admission."""
    if data.get("ack_ref"):
        if any(data.get(key) for key in ("diagnostic_ref", "phase_continuation_ref", "assessment_ids")):
            raise ResearchError("recovery_ack_and_registration_inputs_are_exclusive")
        return str(data["ack_ref"])
    if not data.get("diagnostic_ref") or not data.get("phase_continuation_ref") or not data.get("assessment_ids"):
        raise ResearchError("recovery_exact_ack_or_registration_inputs_required")
    registered = FailureAcknowledgmentResearch.register_acknowledgment(engine, session, context,
        {key: data[key] for key in ("plan", "diagnostic_ref", "phase_continuation_ref", "assessment_ids")})
    print(registered["markdown"], flush=True)
    print(json.dumps({"ack_result": registered["id"], "ack_ref": registered["ack_ref"]}), flush=True)
    return str(registered["ack_ref"])


class RecoveryResearch(fast.FastResearch):
    def check_gate(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook,
                   continuation: Json) -> list[str]:
        blockers = super().check_gate(session, plan_id, plan, view, book, continuation)
        return recovery_gate(blockers, view["assessments"], continuation, self.failure_ack)

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("recovery_original_owner_required")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("recovery_explicit_online_execution_required")
        plan_id = data["plan"]
        data = {**data, "ack_ref": resolve_ack_reference(self, session, context, data)}
        self.failure_ack = load_failure_ack(self, session, plan_id, data["ack_ref"])
        ack = self.failure_ack
        reference = ack["phase_continuation_ref"]
        phase = load_continuation(self, session, plan_id, reference)
        if phase is None:
            raise AuditError("recovery_original_phase_continuation_required")
        plan = self.ledger.get(plan_id, fast.PLAN_KIND)
        if (plan.get("authorization_id") != STUDY
                or any(sha256(ROOT / name) != value for name, value in plan["implementation"].items())):
            raise AuditError("recovery_frozen_preparation_changed")
        snapshot = fast.core.load_contract_snapshot()
        if snapshot.contract_sha256 != plan["contract_sha256"]:
            raise AuditError("recovery_frozen_contract_changed")
        self.deadline, self.queue_cap = ack["deadline_epoch"], ack["queue_token_cap"]
        workers = ack["count_workers"]
        if (self.deadline != phase["deadline_epoch"] or type(self.queue_cap) is not int
                or not 1 <= self.queue_cap <= fast.MAX_QUEUE or type(workers) is not int or not 1 <= workers <= 16):
            raise AuditError("recovery_ack_schedule_changed")
        implementation = implementation_hashes()
        self.fast_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":finite-failure-recovery",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"], "implementation": implementation,
                "ack_ref": data["ack_ref"], "original_run": ack["original_run"], "original_finish": ack["original_finish"],
                "phase_continuation_ref": reference, "deadline_epoch": self.deadline,
                "queue_token_cap": self.queue_cap, "account_capacity_verified": False, "count_workers": workers,
                "rules": "Reuse frozen fast-v1 staging/count/admission/dispatch/reports under a new run namespace. Exactly two proved terminal failures remain failed and fully charged; finite acknowledgment only, no future error exemption. One writer, <=16 exact counters, original250files and own provisional20M queue. Same shared cap, prompt,4096 output and original deadline. Observe startup pending jobs once before filling. Never retry submitted work or clear old stops. Unknown cost/retention/action/new technical errors stop. Project retained outputs only at a drained normal terminal."}})["id"]
        self.execution_protocol = self.fast_protocol
        if self.gateway.load_book(session, STUDY) is None:
            raise AuditError("recovery_existing_shared_budget_required")
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        binding = {"plan": plan_id, "protocol": self.fast_protocol, "implementation": implementation,
            "ack_ref": data["ack_ref"], "original_run": ack["original_run"], "original_finish": ack["original_finish"],
            "phase_continuation_ref": reference, "authorization_id": STUDY, "deadline_epoch": self.deadline,
            "queue_token_cap": self.queue_cap, "count_workers": workers}
        key = plan_id + ":" + data["ack_ref"] + ":recovery-v1"
        old = self.latest(RUN_KIND, key)
        if old:
            self.fast_run, run = old
            validate_run_binding(run, binding)
        else:
            run = {**binding, "started_at": utc(), "startup_pending_manifests":
                [row["manifest"] for row in view["jobs"] if row["manifest"] not in view["reconciled"]]}
            self.fast_run = self.ledger.record(session, RUN_KIND, key, run)
        finished = self.latest(FINISH_KIND, self.fast_run)
        if finished:
            return self.report(session, plan_id, plan, view, book, state, reason=finished[1]["reason"])
        blockers = self.check_gate(session, plan_id, plan, view, book, phase)
        reason = "technical_stop" if blockers else None
        next_poll, backoff = 0.0, 30.0
        startup_observed = False
        pressure: str | None = None
        print(self.report(session, plan_id, plan, view, book, state)["markdown"], flush=True)
        # Deliberate isolated copy of fast-v1 scheduling only. All request/cost/
        # source mechanics are inherited unchanged and implementation-bound.
        while reason is None:
            if time.time() >= self.deadline:
                reason = "deadline"
                break
            pending = {row["manifest"] for row in view["jobs"]} - view["reconciled"]
            job_ids = {row["manifest"] for row in view["jobs"]}
            staged = [row for row in view["manifests"] if row["id"] not in job_ids]
            unmanifested = plan["pending_requests"] - sum(len(row["tasks"]) for row in view["manifests"])
            if not pending and not staged and not unmanifested:
                reason = "complete"
                break
            if pressure and not pending:
                reason = fast.terminal_reason(pressure, 0)
                break
            operation = cycle_operation(startup_observed=startup_observed,
                startup_pending=bool(pending & set(run["startup_pending_manifests"])), pending=bool(pending),
                staged=bool(staged), unmanifested=bool(unmanifested), pressure=pressure, poll_due=time.time() >= next_poll)
            if operation == "reconcile":
                print(json.dumps({"recovery_phase": "reconcile", "unfinished_jobs": len(pending)}), flush=True)
                result = ReconciliationResearch._status(self, session, context,
                    {"plan": plan_id, "continuation_ref": reference, "allow_paid_execution": True})
                print(result["markdown"], flush=True)
                self.execution_protocol = self.fast_protocol
                view = self.view(session, plan_id)
                saved = self.gateway.load_book(session, STUDY)
                if saved is None:
                    raise AuditError("recovery_shared_budget_disappeared")
                book, state = saved
                blockers = self.check_gate(session, plan_id, plan, view, book, phase)
                if result["obstacles"] or blockers:
                    reason = "technical_stop"
                    break
                startup_observed = True
                next_poll = time.time() + backoff
                backoff = min(120.0, backoff * 2)
                pressure = None
                continue
            if operation == "wait":
                duration = min(30.0, max(0.0, next_poll - time.time()), max(0.0, self.deadline - time.time()))
                print(json.dumps({"recovery_wait_seconds": duration, "pending_jobs": len(pending), "reason": pressure or "startup_or_completion"}), flush=True)
                time.sleep(duration)
                continue
            if operation == "stage":
                print(json.dumps({"recovery_phase": "stage", "max_per_corpus": 250}), flush=True)
                result = self.stage(session, plan_id, plan, view, state, snapshot)
                print(result["markdown"], flush=True)
                if not result["manifests"]:
                    reason = "stalled"
                continue
            manifest = staged[0]
            print(json.dumps({"recovery_phase": "count_admit_submit", "corpus": manifest["corpus_id"],
                              "requests": len(manifest["tasks"]), "count_workers": workers}), flush=True)
            raw = fast.validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, snapshot)
            try:
                book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                    active_tokens=fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
                    queue_cap=self.queue_cap, workers=workers, deadline=self.deadline)
            except AuditError:
                raise
            except (ResearchError, BudgetError) as error:
                self.ledger.record(session, "luna_budget_failure_recovery_obstacle", self.fast_run,
                    {"plan": plan_id, "run": self.fast_run, "manifest": manifest["id"], "reason": str(error), "observed_at": utc()})
                saved = self.gateway.load_book(session, STUDY)
                if saved:
                    book, state = saved
                reason = "technical_stop"
                break
            if pressure == "deadline":
                reason = "deadline"
                break
            if job:
                view["jobs"].append(job)
            print(self.report(session, plan_id, plan, view, book, state)["markdown"], flush=True)
        self.ledger.record(session, FINISH_KIND, self.fast_run, {"plan": plan_id, "run": self.fast_run,
            "reason": reason, "ended_at": utc(), "budget_state": state, "blockers": blockers,
            "ack_ref": data["ack_ref"], "original_finish": ack["original_finish"]})
        return self.report(session, plan_id, plan, view, book, state, reason=reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--ack-ref")
    choice.add_argument("--diagnostic-ref")
    parser.add_argument("--phase-continuation-ref")
    parser.add_argument("--assessment-id", dest="assessment_ids", action="append")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required for the existing authorized recovery")
    if args.diagnostic_ref and (not args.phase_continuation_ref or not args.assessment_ids or len(args.assessment_ids) != 2):
        parser.error("combined registration requires --phase-continuation-ref and exactly two --assessment-id arguments")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"starting_audited_failure_recovery": args.plan, "ack_ref": args.ack_ref}), flush=True)
    engine = RecoveryResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Continue untouched Luna Batch work after exact failed-row acknowledgment without retry, budget or deadline reset", actor=fast.ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result.get("presentation"), "reason": result["finished_reason"]}), flush=True)
    finally:
        engine.close()
    if result["finished_reason"] in {"complete", "budget_deferred"} and not result["pending_jobs"]:
        projector = ProjectionResearch(OWNER, config=Config(offline=True))
        try:
            projection = projector.execute("status", {"plan": args.plan},
                objective="Finish deterministic retained-output projection after drained recovery", actor=fast.ACTOR)
            print(projection["markdown"], flush=True)
        finally:
            projector.close()
    return 0 if result["finished_reason"] in {"complete", "budget_deferred", "deadline"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
