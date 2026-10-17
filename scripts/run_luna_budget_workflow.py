"""One-process, bounded admission and reconciliation of the authorized Luna queue.

Every research read/write enters Research.execute. The 24-hour window limits new
local phases, not provider execution; unfinished jobs and reservations survive.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable
import hashlib
import json
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, digest, utc
from newsresearch.event_batch_budget import PricePolicy
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import ExecutionResearch, JOB_KIND, MANIFEST_KIND, PLAN_KIND
from execute_luna_budget_wave import BulkExecutionResearch, action_blockers, reserved_input_tokens
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
import luna_event_contract_v2 as contract
from poll_luna_budget_batch import ReconciliationResearch
from prepare_luna_budget_wave import MAX_PER_CORPUS, WaveResearch
from project_luna_budget_results import ProjectionResearch

METHOD = "luna-budget-bounded-controller-v1"
RUN_KIND = "luna_budget_controller_run"
FINISH_KIND = "luna_budget_controller_finish"
MAX_RUNTIME_SECONDS = 24 * 60 * 60
MIN_BACKOFF = 30.0
MAX_BACKOFF = 120.0
BUDGET_DEFER = "shared_operational_budget_admission_deferred"
TOKEN_DEFER = "own_reserved_input_token_guard_deferred"
ACTOR = "codex:luna-batch-budget"


def implementation_hashes() -> dict[str, str]:
    names = (
        "scripts/run_luna_budget_workflow.py", "scripts/execute_luna_budget_wave.py",
        "scripts/execute_luna_budget_batch.py", "scripts/poll_luna_budget_batch.py",
        "scripts/luna_batch_results.py", "scripts/prepare_luna_budget_wave.py",
        "scripts/project_luna_budget_results.py", "scripts/luna_batch_literal_projection.py",
        "src/newsresearch/event_batch_budget.py", "src/newsresearch/event_batch_live_gateway.py",
        "src/newsresearch/event_batch_transport.py",
    )
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}


class ControlResearch(ExecutionResearch):
    """Audited, offline control metadata; never opens source text or sends HTTP."""

    def rows(self, session: str, kind: str) -> list[Json]:
        sql = "SELECT id FROM records WHERE kind=? ORDER BY created_event"
        self.ledger.append(session, "budget.controller.records.inspection.intended",
                           {"sql": sql, "parameters": [kind]})
        return [{**self.ledger.get(row["id"], kind), "id": row["id"]}
                for row in self.ledger.db.execute(sql, (kind,))]

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() or not self.config.offline:
            raise AuditError("budget_controller_requires_original_owner_offline")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != contract.contract_digest():
            raise AuditError("budget_controller_plan_or_contract_changed")
        current_code = implementation_hashes()
        if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value
               for name, value in plan["implementation"].items()):
            raise AuditError("budget_controller_frozen_preparation_changed")
        runtime = data.get("max_runtime_seconds", MAX_RUNTIME_SECONDS)
        limit = data.get("max_per_corpus", MAX_PER_CORPUS)
        if type(runtime) is not int or not 1 <= runtime <= MAX_RUNTIME_SECONDS:
            raise ResearchError("budget_controller_runtime_outside_bounds")
        if type(limit) is not int or not 1 <= limit <= MAX_PER_CORPUS:
            raise ResearchError("budget_controller_wave_outside_bounds")
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":controller",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"],
                "implementation": current_code, "max_runtime_seconds": runtime, "max_per_corpus": limit,
                "rules": "One sequential controller; same authorization, corpus-isolated fixed queue and budget. Poll and project retained outputs; stage only without an unsubmitted manifest. Stop admission at budget deferral but drain existing jobs. Local queue deferral waits for changed budget state. Stop technical/unknown/frozen failures. No retry, cancellation, reset, new embeddings or event acceptance. Fixed deadline survives restart; in-flight provider work survives deadline."},
            "amend_latest": True, "reason": "Bind bounded scheduler and all invoked implementations"})["id"]
        previous = self.latest(RUN_KIND, plan_id)
        if previous:
            run_id, run = previous
            if (run["protocol"] != protocol or run["max_runtime_seconds"] != runtime
                    or run["max_per_corpus"] != limit or run["implementation"] != current_code):
                raise AuditError("budget_controller_run_binding_changed_no_reset")
        else:
            start = time.time()
            run = {"plan": plan_id, "protocol": protocol, "implementation": current_code,
                   "started_at": utc(), "started_epoch": start, "deadline_epoch": start + runtime,
                   "max_runtime_seconds": runtime, "max_per_corpus": limit, "authorization_id": STUDY}
            run_id = self.ledger.record(session, RUN_KIND, plan_id, run)
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("budget_controller_existing_budget_required")
        book, state = saved
        if (book.price_policy.fingerprint != PricePolicy(**plan["price_policy"]).fingerprint
                or book.ceiling_nanousd != 150_000_000_000
                or book.operational_limit_nanousd != 120_000_000_000):
            raise AuditError("budget_controller_original_budget_changed")

        def selected(kind: str) -> list[Json]:
            return [row for row in self.rows(session, kind) if row.get("plan") == plan_id]

        manifests = selected(MANIFEST_KIND)
        jobs = selected(JOB_KIND)
        reconciled = {row["manifest"] for row in selected("luna_budget_job_reconciled")}
        assessments = selected("luna_budget_assessment")
        projected = {row["original_assessment"] for row in selected("luna_budget_literal_projection")}
        manifest_ids = {row["id"] for row in manifests}
        job_ids = {row["manifest"] for row in jobs}
        custom_ids = [task["custom_id"] for row in manifests for task in row["tasks"]]
        if (len(custom_ids) != len(set(custom_ids)) or len(job_ids) != len(jobs)
                or not job_ids <= manifest_ids or not reconciled <= job_ids):
            raise AuditError("budget_controller_manifest_or_job_identity_invalid")
        staged = [row["id"] for row in manifests if row.get("phase") == "bulk" and row["id"] not in job_ids]
        deferrals = selected("luna_budget_bulk_deferral")
        admission_closed = any(row["reason"] == BUDGET_DEFER for row in deferrals) or book.available_nanousd <= 0
        current_deferrals = {row["manifest"]: row for row in deferrals if row["manifest"] in staged}
        token_wait = any(row["reason"] == TOKEN_DEFER and row["budget_state"] == state
                         for row in current_deferrals.values())
        obstacles = selected("luna_budget_execution_obstacle") + selected("luna_budget_bulk_obstacle")
        blockers = action_blockers(self.rows(session, ACTION_KIND), self.rows(session, RECEIPT_KIND), obstacles)
        if self.latest(STOP_KIND, STUDY):
            blockers.append("shared_gateway_stopped")
        if book.frozen:
            blockers.append("shared_budget_frozen")
        if any(row.get("technical_failure") or row["status"] not in {"valid", "invalid"} for row in assessments):
            blockers.append("technical_or_unknown_assessment")
        for event in book.to_dict()["events"]:
            if event["action"] == "reserve" and book.entry(event["value"]["request_id"])["status"] in {"unknown", "frozen", "overrun"}:
                blockers.append("unknown_or_frozen_budget_reservation")
                break
        submitted = sum(row["request_count"] for row in jobs)
        unmanifested = plan["pending_requests"] - len(custom_ids)
        if unmanifested < 0 or submitted > plan["pending_requests"] or len(assessments) > submitted:
            raise AuditError("budget_controller_coverage_exceeds_frozen_queue")
        finished = self.latest(FINISH_KIND, run_id)
        value = {"plan": plan_id, "protocol": protocol, "run": run_id,
            "deadline_epoch": run["deadline_epoch"], "max_per_corpus": limit,
            "submitted": submitted, "assessments": len(assessments),
            "status_counts": dict(Counter(row["status"] for row in assessments)),
            "pending_jobs": len(job_ids - reconciled),
            "pending_requests": submitted - len(assessments),
            "staged_unsubmitted": staged, "unmanifested": unmanifested,
            "unprojected": sum(row["id"] not in projected for row in assessments),
            "admission_closed": admission_closed, "token_wait": token_wait,
            "blockers": sorted(set(blockers)), "budget_state": state,
            "charged_estimate_usd": book.charged_nanousd / 1e9, "reserved_usd": book.reserved_nanousd / 1e9,
            "own_reserved_input_tokens": reserved_input_tokens(book),
            "eligible_not_submitted": plan["pending_requests"] - submitted,
            "finished_reason": finished[1]["reason"] if finished else None}
        if data.get("finish_reason"):
            reason = data["finish_reason"]
            if reason not in {"complete", "budget_deferred", "deadline", "technical_stop", "capacity_blocked_without_pending_jobs", "stalled"}:
                raise ResearchError("budget_controller_invalid_finish_reason")
            if finished and finished[1]["reason"] != reason:
                raise AuditError("budget_controller_terminal_state_changed")
            if not finished:
                self.ledger.record(session, FINISH_KIND, run_id,
                    {"plan": plan_id, "run": run_id, "protocol": protocol, "reason": reason,
                     "ended_at": utc(), "snapshot": value})
            value["finished_reason"] = reason
        markdown = (f"Luna controller: {value['submitted']:,} submitted; {value['assessments']:,} assessed "
            f"({value['status_counts']}); {value['pending_requests']:,} unassessed in {value['pending_jobs']} unfinished jobs. "
            f"{len(staged)} staged files await submission; {unmanifested:,} requests are unmanifested. "
            f"Conservative charge ${value['charged_estimate_usd']:.6f}; reserved ${value['reserved_usd']:.6f}. "
            f"Admission closed: {admission_closed}; token-cap wait: {token_wait}; stop: {value['finished_reason'] or 'none'}. "
            f"Blockers: {', '.join(value['blockers']) or 'none'}. "
            "The 24-hour local scheduling window does not cancel provider jobs or release reservations. "
            "Missing/deferred work is unprocessed, not a negative finding. Original and derived results remain separate. "
            "No retries, embeddings or accepted dossiers. Protected exact presentation retained; record_presentation does not support this technical kind.")
        return present(self, session, "luna_budget_controller_status", value, markdown)


def step_failure(stage: str, result: Json) -> bool:
    if stage == "reconcile":
        return bool(result.get("obstacles") or result.get("budget_frozen")
                    or any(result.get("status_counts", {}).get(key, 0) for key in ("error", "unknown")))
    if stage == "stage":
        return result.get("status") == "blocked"
    if stage == "submit":
        return bool(result.get("obstacle") or result.get("gate_blockers")
                    or result.get("counts", {}).get("unconfirmed_create_bulk", 0))
    return False


def run_loop(step: Callable[[str, Json], Json], *, plan: str,
             max_runtime_seconds: int = MAX_RUNTIME_SECONDS, max_per_corpus: int = MAX_PER_CORPUS,
             now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep,
             emit: Callable[[str], None] = print) -> Json:
    """Pure scheduling boundary; injected steps own all audited effects."""
    common = {"plan": plan, "max_runtime_seconds": max_runtime_seconds, "max_per_corpus": max_per_corpus}
    state = step("control", common)
    deadline = state["deadline_epoch"]
    next_poll = 0.0
    backoff = MIN_BACKOFF
    previous_progress = ""
    forced_stop: str | None = None
    while True:
        if state.get("finished_reason"):
            return state
        reason = forced_stop
        if not reason and state.get("blockers"):
            reason = "technical_stop"
        if not reason and now() >= deadline:
            reason = "deadline"
        if not reason and not state["pending_jobs"] and not state["unprojected"]:
            if state["admission_closed"]:
                reason = "budget_deferred"
            elif not state["staged_unsubmitted"] and not state["unmanifested"]:
                reason = "complete"
            elif state["token_wait"]:
                reason = "capacity_blocked_without_pending_jobs"
        if reason:
            return step("control", {**common, "finish_reason": reason})
        progress = digest({key: state[key] for key in (
            "submitted", "assessments", "staged_unsubmitted", "unmanifested", "budget_state", "unprojected")})
        if progress != previous_progress:
            backoff = MIN_BACKOFF
            previous_progress = progress
        emit(json.dumps({"controller_cycle": {key: state[key] for key in (
            "submitted", "assessments", "pending_jobs", "unmanifested", "admission_closed", "token_wait")}}, sort_keys=True))
        stage: str | None = None
        data: Json = {"plan": plan}
        if state["pending_jobs"] and now() >= next_poll:
            stage = "reconcile"
        elif state["unprojected"]:
            stage = "project"
        elif not state["admission_closed"] and not state["token_wait"]:
            stage = "submit" if state["staged_unsubmitted"] else "stage" if state["unmanifested"] else None
        if stage:
            if now() >= deadline:
                forced_stop = "deadline"
                continue
            if stage in {"reconcile", "submit"}:
                data["allow_paid_execution"] = True
            if stage == "stage":
                data["max_per_corpus"] = max_per_corpus
            result = step(stage, data)
            if step_failure(stage, result):
                forced_stop = "technical_stop"
            elif stage == "stage" and not result.get("manifests") and state["unmanifested"]:
                forced_stop = "stalled"
            if stage == "reconcile":
                next_poll = now() + backoff
                backoff = min(MAX_BACKOFF, backoff * 2)
            # A deadline reached inside a phase allows only audited finalization.
            if now() >= deadline and not forced_stop:
                forced_stop = "deadline"
            state = step("control", {**common, **({"finish_reason": forced_stop} if forced_stop else {})})
            continue
        duration = min(backoff, max(0.0, next_poll - now()), max(0.0, deadline - now()))
        if duration <= 0:
            forced_stop = "stalled"
            continue
        sleep(duration)
        if now() >= deadline:
            forced_stop = "deadline"
            continue
        state = step("control", common)


def execute_step(stage: str, data: Json) -> Json:
    classes: dict[str, Any] = {"control": ControlResearch, "reconcile": ReconciliationResearch,
        "project": ProjectionResearch, "stage": WaveResearch, "submit": BulkExecutionResearch}
    # This is launch telemetry, not a research result; preflight can be lengthy.
    print(json.dumps({"starting_audited_phase": stage, "plan": data["plan"]}), flush=True)
    engine = classes[stage](OWNER, config=Config(offline=stage not in {"reconcile", "submit"}))
    try:
        result = engine.execute("status", data,
            objective=f"Bounded authorized Luna Batch workflow: {stage}; preserve shared costs and incomplete coverage",
            actor=ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({"step": stage, "result": result["id"], "presentation": result.get("presentation")}), flush=True)
        return result
    finally:
        engine.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    parser.add_argument("--max-runtime-seconds", type=int, default=MAX_RUNTIME_SECONDS)
    parser.add_argument("--max-per-corpus", type=int, default=MAX_PER_CORPUS)
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required for the existing authorized run")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = run_loop(execute_step, plan=args.plan, max_runtime_seconds=args.max_runtime_seconds,
                      max_per_corpus=args.max_per_corpus, emit=lambda value: print(value, flush=True))
    return 0 if result["finished_reason"] in {"complete", "budget_deferred", "deadline"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
