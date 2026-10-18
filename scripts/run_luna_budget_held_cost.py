"""Exact finite held-cost recovery; old stops and the full unknown hold remain.

The scheduling loop is deliberately unchanged from frozen recovery-v1. Inherited
request, reservation and gateway methods remain the sole paid data path.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError
from newsresearch.legacy import sha256
from newsresearch.runtime import audited_handler

from luna_batch_budget_run import OWNER, ROOT, STUDY, present
from luna_budget_held_cost import (HeldAcknowledgmentResearch, FINISH_KIND, RUN_KIND,
    RECOVERY_METHOD as METHOD, implementation_hashes, load_ack, validate_book)
from luna_batch_phase_projection import parse_batch_results_phase_aware
from project_luna_budget_results import ProjectionResearch
import run_luna_budget_fast as fast
from run_luna_budget_recovery import RecoveryResearch, cycle_operation, validate_run_binding, recovery_gate


def resolve_ack_reference(engine: fast.FastResearch, session: str, context: Context, data: Json) -> str:
    fields = ("prior_ack_ref", "stop_result_ref", "diagnostic_ref", "held_assessment_id", "settled_assessment_id")
    if data.get("ack_ref"):
        if any(data.get(key) for key in fields):
            raise ResearchError("chained_recovery_ack_and_registration_inputs_are_exclusive")
        return str(data["ack_ref"])
    if any(not data.get(key) for key in fields):
        raise ResearchError("chained_recovery_exact_ack_or_registration_inputs_required")
    registered = HeldAcknowledgmentResearch.register_acknowledgment(engine, session, context,
        {key: data[key] for key in ("plan", *fields)})
    print(registered["markdown"], flush=True)
    print(json.dumps({"ack_result": registered["id"], "ack_ref": registered["ack_ref"]}), flush=True)
    return str(registered["ack_ref"])


class HeldCostRecoveryResearch(RecoveryResearch):
    def check_gate(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook,
                   continuation: Json) -> list[str]:
        blockers = fast.FastResearch.check_gate(self, session, plan_id, plan, view, book, continuation)
        try:
            validate_book(book, plan_id, plan, self.failure_ack["held_failure"])
        except AuditError as error:
            return sorted(set([*blockers, str(error)]))
        blockers = [item for item in blockers if item != "shared_budget_unknown_or_unresolved_charge"]
        return recovery_gate(blockers, view["assessments"], continuation, self.failure_ack)

    def action(self, session: str, plan_id: str, policy: str, key: str, request: Json,
               body: bytes | None = None, **kwargs: Any) -> Json:
        if request.get("method") == "POST" and request.get("path") == "/v1/batches":
            saved = self.gateway.load_book(session, STUDY)
            if saved is None:
                raise AuditError("held_cost_current_book_missing_before_create")
            validate_book(saved[0], plan_id, self.ledger.get(plan_id, fast.PLAN_KIND), self.failure_ack["held_failure"])
        return super().action(session, plan_id, policy, key, request, body, **kwargs)

    def report(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook, state: str,
               *, reason: str | None = None) -> Json:
        original = fast.FastResearch.report(self, session, plan_id, plan, view, book, state, reason=reason)
        held = self.failure_ack["held_failure"]
        actual = book.entry(held["custom_id"])
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown"}}
        value.update(base_status_ref=original["id"], held_assessment=held["assessment"], held_custom_id=held["custom_id"],
            held_cost_status=actual["status"], held_reserved_nanousd=actual["reserved_nanousd"],
            held_expected_nanousd=held["entry"]["reserved_nanousd"], finite_assessment_ids=self.failure_ack["assessment_ids"],
            held_ack_ref=self.failure_ack["id"])
        return present(self, session, "luna_budget_fast_status", value, original["markdown"] +
            f"\nHistorical rejection remains failed: cost status {actual['status']}; ${actual['reserved_nanousd'] / 1e9:.9f} still reserved, with model/usage unavailable. This is not a confirmed charge or zero-cost claim. The finite acknowledgment covers {len(self.failure_ack['assessment_ids'])} exact failed rows plus the separate old phase proof; every new technical/unknown error still stops.")

    @audited_handler
    def reconcile_held(self, session: str, context: Context, data: Json) -> Json:
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, fast.PLAN_KIND)
        self.execution_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":held-cost-reconcile",
            "content": {"method": METHOD + ":reconcile", "plan": plan_id, "versions": plan["versions"],
                "implementation": implementation_hashes(), "ack_ref": self.failure_ack["id"],
                "rules": "Inside the active audited handler call unchanged ReconciliationResearch.reconcile with the same gateway/policy. Retain exact files, parsing and real settlement. Never mask the held unknown or new failures; no strict admission-loader substitution, new inference, cost release or retries."}})["id"]
        self.result_parser = parse_batch_results_phase_aware
        self.parser_mode = "explicit-final-answer-phase-v1"
        policy, _, _ = self.authorization(session, context, plan_id, plan)
        obstacles = []
        for job in self.view(session, plan_id)["jobs"]:
            try:
                self.reconcile(session, plan_id, policy, job)
            except AuditError:
                raise
            except ResearchError as error:
                obstacles.append({"job_id": job["job_id"], "reason": str(error)})
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("held_cost_reconciliation_book_missing")
        book, state = saved
        report = self.report(session, plan_id, plan, self.view(session, plan_id), book, state)
        return present(self, session, "luna_budget_held_reconciliation", {"plan": plan_id,
            "protocol": self.execution_protocol, "status_ref": report["id"], "obstacles": obstacles},
            report["markdown"] + "\nReconciliation obstacles: " + json.dumps(obstacles))

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("recovery_original_owner_required")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("recovery_explicit_online_execution_required")
        plan_id = data["plan"]
        data = {**data, "ack_ref": resolve_ack_reference(self, session, context, data)}
        self.failure_ack = load_ack(self, session, plan_id, data["ack_ref"])
        ack = self.failure_ack
        reference = ack["phase_continuation_ref"]
        phase = ack["phase"]
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
        self.fast_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":exact-held-cost-recovery",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"], "implementation": implementation,
                "ack_ref": data["ack_ref"], "prior_ack_ref": ack["prior_ack_ref"],
                "stopped_run": ack["stopped_run"], "stopped_finish": ack["stopped_finish"], "stop_result_ref": ack["stop_result_ref"],
                "original_run": ack["original_run"], "original_finish": ack["original_finish"],
                "phase_continuation_ref": reference, "deadline_epoch": self.deadline,
                "queue_token_cap": self.queue_cap, "account_capacity_verified": False, "count_workers": workers,
                "rules": "Reuse frozen fast-v1 staging/count/admission/dispatch/reports under a new run namespace. Only the exact historical failed IDs are acknowledged. One terminal invalid_prompt rejection retains its full original unknown liability permanently; no observed billing or model is invented. Every other unknown/error blocks. Reconciliation invokes unchanged reconcile inside this active audited handler with this versioned protocol and original gateway, avoiding old admission-loader entry points; no masking of raw rows or costs. One writer, <=16 exact counters, original250files and own provisional20M queue. Same shared cap, prompt,4096 output and original deadline. Observe startup pending jobs once before filling. Never retry submitted work or clear old stops. Unknown cost/retention/action/new technical errors stop. Project retained outputs only at a drained normal terminal."}})["id"]
        self.execution_protocol = self.fast_protocol
        if self.gateway.load_book(session, STUDY) is None:
            raise AuditError("recovery_existing_shared_budget_required")
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        binding = {"plan": plan_id, "protocol": self.fast_protocol, "implementation": implementation,
            "ack_ref": data["ack_ref"], "prior_ack_ref": ack["prior_ack_ref"],
                "stopped_run": ack["stopped_run"], "stopped_finish": ack["stopped_finish"], "stop_result_ref": ack["stop_result_ref"],
                "original_run": ack["original_run"], "original_finish": ack["original_finish"],
            "phase_continuation_ref": reference, "authorization_id": STUDY, "deadline_epoch": self.deadline,
            "queue_token_cap": self.queue_cap, "count_workers": workers}
        key = plan_id + ":" + data["ack_ref"] + ":held-cost-recovery-v1"
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
                result = self.reconcile_held(session, context,
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
                self.ledger.record(session, "luna_budget_held_cost_obstacle", self.fast_run,
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
            "ack_ref": data["ack_ref"], "prior_ack_ref": ack["prior_ack_ref"],
            "original_finish": ack["original_finish"], "stopped_finish": ack["stopped_finish"]})
        return self.report(session, plan_id, plan, view, book, state, reason=reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--ack-ref")
    choice.add_argument("--diagnostic-ref")
    parser.add_argument("--prior-ack-ref")
    parser.add_argument("--stop-result-ref")
    parser.add_argument("--held-assessment-id")
    parser.add_argument("--settled-assessment-id")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required for the existing authorized recovery")
    if args.diagnostic_ref and (not args.prior_ack_ref or not args.stop_result_ref or not args.held_assessment_id or not args.settled_assessment_id):
        parser.error("combined registration requires --prior-ack-ref, --stop-result-ref and exact --held-assessment-id / --settled-assessment-id arguments")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"starting_audited_exact_held_cost_recovery": args.plan, "ack_ref": args.ack_ref}), flush=True)
    engine = HeldCostRecoveryResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Continue untouched Luna Batch work after an exact historical rejection with its full unknown cost held without retry, budget or deadline reset", actor=fast.ACTOR)
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
