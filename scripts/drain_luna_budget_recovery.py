"""Drain already submitted recovery jobs, then retain their exact diagnostic.

One Research.execute owns both registered phases and their full preflight. The
only network operations permitted here are status/file GETs for existing jobs;
the frozen paid controller, parser, and offline reporting handler stay unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, utc
from newsresearch.event_batch_budget import PricePolicy
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import JOB_KIND, PLAN_KIND
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
from luna_batch_phase_projection import parse_batch_results_phase_aware
from luna_budget_continuation import load_continuation
from luna_budget_failure_ack import implementation_hashes as recovery_hashes, load_failure_ack
from luna_event_contract_v2 import contract_digest
from poll_luna_budget_batch import ReconciliationResearch
from report_luna_budget_progress import KINDS, ProgressResearch, aggregate
from run_luna_budget_recovery import FINISH_KIND, METHOD as RECOVERY_METHOD, RUN_KIND

METHOD = "luna-budget-stopped-recovery-drain-v1"
DRAIN_KIND = "luna_budget_recovery_drain"
HISTORY_KINDS = {**KINDS, "fast_finishes": "luna_budget_fast_finish", "recovery_finishes": FINISH_KIND}


def implementation_hashes() -> dict[str, str]:
    result = recovery_hashes()
    for name in ("drain_luna_budget_recovery.py", "drain_luna_budget_recovery_with_key.ps1"):
        path = "scripts/" + name
        result[path] = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
    return result


def validate_stop_binding(plan_id: str, stop: Json, run_id: str, run: Json,
                          finish: Json, ack_ref: str, ack: Json, phase_ref: str) -> None:
    """A terminal result must name this exact recovery and its old approval."""
    if (stop.get("plan") != plan_id or stop.get("run") != run_id
            or stop.get("finished_reason") != "technical_stop"
            or run.get("plan") != plan_id or run.get("authorization_id") != STUDY
            or run.get("ack_ref") != ack_ref or run.get("phase_continuation_ref") != phase_ref
            or stop.get("protocol") != run.get("protocol") or not run.get("protocol")
            or finish.get("plan") != plan_id or finish.get("run") != run_id
            or finish.get("reason") != "technical_stop" or finish.get("ack_ref") != ack_ref
            or not stop.get("budget_state") or stop["budget_state"] != finish.get("budget_state")
            or ack.get("plan") != plan_id or ack.get("authorization_id") != STUDY
            or ack.get("phase_continuation_ref") != phase_ref):
        raise AuditError("drain_exact_terminal_recovery_binding_required")
    for key in ("original_run", "original_finish", "deadline_epoch", "queue_token_cap", "count_workers"):
        if key not in ack or run.get(key) != ack[key]:
            raise AuditError("drain_recovery_ack_history_changed")
    if (finish.get("original_finish") != ack["original_finish"]
            or any(stop.get(key) != run[key] for key in ("deadline_epoch", "queue_token_cap"))):
        raise AuditError("drain_stop_schedule_or_history_changed")
    for key in ("submitted", "assessments", "pending_requests", "pending_jobs"):
        if type(stop.get(key)) is not int or stop[key] < 0:
            raise AuditError("drain_stop_coverage_missing")
    if stop["submitted"] - stop["assessments"] != stop["pending_requests"]:
        raise AuditError("drain_stop_coverage_mismatch")


class DrainResearch(ReconciliationResearch):
    def action(self, session: str, plan_id: str, policy: str, key: str,
               request: Json, body: bytes | None = None, **kwargs: Any) -> Json:
        path = request.get("path", "")
        job_get = isinstance(path, str) and path in {"/v1/batches/" + value for value in getattr(self, "drain_job_ids", set())}
        file_get = isinstance(path, str) and re.fullmatch(r"/v1/files/[A-Za-z0-9_-]+/content", path)
        if (getattr(self, "drain_phase", None) != "reconcile" or set(request) != {"method", "path"}
                or request["method"] != "GET" or body is not None or kwargs or not (job_get or file_get)):
            raise AuditError("drain_only_existing_job_status_and_file_get_allowed")
        return super().action(session, plan_id, policy, key, request)

    def rows(self, session: str, kind: str, plan_id: str) -> list[Json]:
        sql = "SELECT id FROM records WHERE kind=? ORDER BY created_event"
        self.ledger.append(session, "budget.drain.records.inspection.intended", {"sql": sql, "parameters": [kind], "plan": plan_id})
        return [value for item in self.ledger.db.execute(sql, (kind,))
                if (value := {**self.ledger.get(item["id"], kind), "id": item["id"]}).get("plan") == plan_id]

    def bind_stop(self, session: str, data: Json) -> Json:
        plan_id = data["plan"]
        self.ledger.append(session, "budget.drain.stop.inspection.intended", {
            "plan": plan_id, "stop_result_ref": data["stop_result_ref"], "prior_ack_ref": data["prior_ack_ref"],
            "phase_continuation_ref": data["phase_continuation_ref"],
            "finish_lookup": {"sql": "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1", "kind": FINISH_KIND, "key": "exact stopped result run"}})
        stop = self.ledger.get(data["stop_result_ref"], "luna_budget_fast_status")
        run_id = stop["run"]
        run = self.ledger.get(run_id, RUN_KIND)
        finish = self.latest(FINISH_KIND, run_id)
        if finish is None:
            raise AuditError("drain_terminal_recovery_finish_required")
        ack = load_failure_ack(self, session, plan_id, data["prior_ack_ref"])
        validate_stop_binding(plan_id, stop, run_id, run, finish[1], data["prior_ack_ref"], ack,
                              data["phase_continuation_ref"])
        protocol = self.ledger.get(run["protocol"], "protocol")["content"]
        if (run.get("implementation") != recovery_hashes() or protocol.get("method") != RECOVERY_METHOD
                or protocol.get("implementation") != run["implementation"]
                or any(protocol.get(key) != run[key] for key in ("plan", "ack_ref", "original_run", "original_finish", "phase_continuation_ref", "deadline_epoch", "queue_token_cap", "count_workers"))):
            raise AuditError("drain_frozen_recovery_implementation_changed")
        latest = self.latest(RUN_KIND, plan_id + ":" + data["prior_ack_ref"] + ":recovery-v1")
        if latest is None or latest[0] != run_id:
            raise AuditError("drain_exact_latest_recovery_required")
        phase = load_continuation(self, session, plan_id, data["phase_continuation_ref"])
        if phase is None or phase["deadline_epoch"] != run["deadline_epoch"]:
            raise AuditError("drain_original_phase_binding_required")
        return {"stop_result_ref": data["stop_result_ref"], "recovery_run": run_id,
            "recovery_finish": finish[0], "prior_ack_ref": data["prior_ack_ref"],
            "phase_continuation_ref": data["phase_continuation_ref"], "submitted_at_stop": stop["submitted"],
            "budget_state_at_stop": stop["budget_state"], "original_stop_unchanged": True,
            "previously_acknowledged_assessment_ids": sorted(set(ack["assessment_ids"]) | {phase["assessment"]})}

    def existing_policy(self, session: str, plan_id: str, plan: Json) -> str:
        self.ledger.append(session, "budget.drain.policy.inspection.intended", {
            "sql": "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
            "parameters": ["policy", STUDY], "mode": "reuse original authorization; no new inference permission"})
        stored = self.latest("policy", STUDY)
        saved = self.gateway.load_book(session, STUDY)
        if stored is None or saved is None:
            raise AuditError("drain_existing_policy_and_budget_required")
        policy = stored[1]["content"]
        book, _ = saved
        if (policy.get("authorization_id") != STUDY or policy.get("plan_ids") != [plan_id]
                or policy.get("allow_external_processing") is not True
                or policy.get("allow_paid_inference") is not True
                or policy.get("price_fingerprint") != PricePolicy(**plan["price_policy"]).fingerprint
                or policy.get("price_fingerprint") != book.price_policy.fingerprint
                or policy.get("ceiling_nanousd") != book.ceiling_nanousd
                or policy.get("operational_limit_nanousd") != book.operational_limit_nanousd
                or book.ceiling_nanousd != 150_000_000_000 or book.operational_limit_nanousd != 120_000_000_000):
            raise AuditError("drain_original_policy_or_budget_changed")
        return stored[0]

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("drain_original_owner_required")
        if self.config.offline or data.get("allow_existing_job_reads") is not True:
            raise ResearchError("drain_explicit_existing_job_reads_required")
        wait = data.get("max_wait_seconds", 1800)
        if type(wait) is not int or not 0 <= wait <= 86400:
            raise ResearchError("drain_wait_outside_bounds")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != contract_digest():
            raise AuditError("drain_frozen_plan_contract_required")
        binding = self.bind_stop(session, data)
        jobs = self.rows(session, JOB_KIND, plan_id)
        if (len({job["job_id"] for job in jobs}) != len(jobs)
                or len({job["manifest"] for job in jobs}) != len(jobs)
                or sum(job["request_count"] for job in jobs) != binding["submitted_at_stop"]):
            raise AuditError("drain_submitted_job_scope_changed")
        policy = self.existing_policy(session, plan_id, plan)
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":stopped-recovery-drain",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"],
                "implementation": implementation_hashes(), **binding, "existing_policy": policy,
                "jobs": [job["id"] for job in jobs], "max_wait_seconds": wait,
                "rules": "One full-preflight session; terminal-stop binding before network. Reuse unchanged reconciliation on exactly existing jobs. GET-only action gate; no count, upload, batch creation, inference, reservation, retry or stop clearing. Valid nonterminal status may be polled; first read obstacle ends polling. Retain provider bytes before parse/settlement. Separate subsequent registered retained diagnostic; all failed outputs and reservations remain."},
            "amend_latest": True, "reason": "Bind explicit existing-job drain and its subsequent retained diagnostic"})["id"]
        self.execution_protocol = protocol
        self.result_parser = parse_batch_results_phase_aware
        self.parser_mode = "explicit-final-answer-phase-v1"
        self.drain_phase = "reconcile"
        self.drain_job_ids = {job["job_id"] for job in jobs}
        drain = self.ledger.record(session, DRAIN_KIND, data["stop_result_ref"], {
            "plan": plan_id, "protocol": protocol, **binding, "existing_jobs": [job["id"] for job in jobs],
            "started_at": utc(), "new_inference_authorized": False})
        end = time.monotonic() + wait
        pending, obstacles, passes = list(jobs), [], []
        while pending:
            observations, remaining = [], []
            for index, job in enumerate(pending):
                try:
                    result = self.reconcile(session, plan_id, policy, job)
                    observations.append(result)
                    if result.get("reconciled") is not True:
                        remaining.append(job)
                except AuditError:
                    raise
                except ResearchError as error:
                    obstacles.append({"job_id": job["job_id"], "reason": str(error)})
                    remaining.extend(pending[index:])
                    break
            passes.append(self.ledger.record(session, "luna_budget_recovery_drain_pass", drain, {
                "plan": plan_id, "drain": drain, "observations": observations, "obstacles": obstacles,
                "remaining_job_ids": [job["job_id"] for job in remaining], "observed_at": utc()}))
            pending = remaining
            if not pending or obstacles or time.monotonic() >= end:
                break
            print(json.dumps({"drain_pending_jobs": len(pending), "new_inference": False}), flush=True)
            time.sleep(min(30.0, max(0.0, end - time.monotonic())))
        self.drain_phase = "diagnostic"
        result = self.retained_report(session, context, plan_id, {
            **binding, "drain": drain, "drain_protocol": protocol, "reconciliation_passes": passes,
            "drain_obstacles": obstacles, "drain_timed_out": bool(pending) and not obstacles,
            "new_inference_authorized": False})
        self.ledger.record(session, "luna_budget_recovery_drain_finish", drain, {
            "plan": plan_id, "drain": drain, "diagnostic": result["id"], "pending_jobs": result["pending_jobs"],
            "obstacles": obstacles, "ended_at": utc()})
        return result

    @audited_handler
    def retained_report(self, session: str, context: Context, plan_id: str, binding: Json) -> Json:
        """New online-session diagnostic phase; never calls the offline handler."""
        if getattr(self, "drain_phase", None) != "diagnostic":
            raise AuditError("drain_diagnostic_requires_completed_read_phase")
        plan = self.ledger.get(plan_id, PLAN_KIND)
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":drained-retained-progress",
            "content": {"method": METHOD + ":retained-diagnostic", "plan": plan_id, **binding,
                "implementation": implementation_hashes(), "versions": plan["versions"],
                "rules": "Reuse frozen aggregate/technical-metadata semantics on retained results after the GET-only drain. Separate corpora; exact IDs and costs; preserve raw and derived validity, failed outputs, missing projections, pending work and controller history. This diagnostic phase forbids every network action and source-packet read; no inference, projection or acceptance."},
            "amend_latest": True, "reason": "Bind retained diagnostics to the exact preceding stopped-job drain"})["id"]
        profile = self._version(session, context, {"kind": "profile", "key": STUDY + ":drained-retained-progress",
            "content": {"mode": "exploratory", "population_estimate": False, "protocol": protocol,
                "plan": plan_id, "versions": plan["versions"], "unit": "retained request, not dossier",
                "denominators": "Frozen eligible and submitted identities; original and derived statuses separate"},
            "amend_latest": True, "reason": "Retain coverage and missingness after existing-job reconciliation"})["id"]
        rows = {name: self.rows(session, kind, plan_id) for name, kind in HISTORY_KINDS.items()}
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("progress_existing_budget_required")
        book, state = saved
        entries = [book.entry(key) for key in sorted({event["value"]["request_id"] for event in book.to_dict()["events"] if event["action"] == "reserve"})]
        if any(entry["request"]["plan_id"] != plan_id for entry in entries):
            raise AuditError("progress_budget_plan_mismatch")
        corpora = aggregate(plan, rows, entries)
        if (sum(row["charged_nanousd"] for row in corpora.values()) != book.charged_nanousd
                or sum(row["reserved_submitted_unresolved_nanousd"] + row["reserved_staged_unsubmitted_nanousd"] for row in corpora.values()) != book.reserved_nanousd):
            raise AuditError("progress_budget_totals_do_not_reconcile")
        technical = []
        for row in rows["assessments"]:
            if row.get("technical_failure") or row["status"] not in {"valid", "invalid"}:
                self.ledger.append(session, "budget.progress.response.inspection.intended", {"assessment": row["id"], "artifact": row["response"], "fields": "source-free parser metadata only"})
                parsed = self.ledger.artifacts.read(row["response"])
                technical.append({**{key: row.get(key) for key in ("id", "custom_id", "corpus_id", "title", "url", "errors", "cost_status", "status", "usage", "request_id")},
                    "parsed_metadata": {key: parsed.get(key) for key in ("http_status", "provider_status", "observed_model", "usage_complete", "response_id", "provider_request_id", "missing", "errors")},
                    "retained_provider_metadata": ProgressResearch.technical_metadata(self, session, row),
                    "current_cost_status": book.entry(row["custom_id"])["status"]})
        finishes = rows["finishes"] + rows["fast_finishes"] + rows["recovery_finishes"]
        previously_acknowledged = set(binding["previously_acknowledged_assessment_ids"])
        newly_unacknowledged = sorted(row["id"] for row in technical if row["id"] not in previously_acknowledged)
        value = {"plan": plan_id, "protocol": protocol, "profile": profile, "versions": plan["versions"], "corpora": corpora,
            **binding, "technical_rows": technical, "controller_finishes": finishes,
            "newly_unacknowledged_technical_assessment_ids": newly_unacknowledged,
            "pending_jobs": len({row["manifest"] for row in rows["jobs"]} - {row["manifest"] for row in rows["reconciled"]}),
            "projection_protocols": dict(Counter(row["protocol"] for row in rows["projections"])),
            "phase_replay_protocols": dict(Counter(row["protocol"] for row in rows["phase_replays"])),
            "budget_state": state, "charged_estimate_usd": book.charged_nanousd / 1e9,
            "reserved_usd": book.reserved_nanousd / 1e9, "budget_frozen": book.frozen,
            "new_models": 0, "new_projections": 0, "accepted_events": 0, "human_validated": False}
        lines = [f"Existing-job drain and retained diagnostic: conservative charge **${book.charged_nanousd / 1e9:.6f}**, reserved **${book.reserved_nanousd / 1e9:.6f}**. Budget frozen: {book.frozen}. Pending jobs: {value['pending_jobs']}.",
            f"Exact stopped result {binding['stop_result_ref']}; recovery run {binding['recovery_run']}; finish {binding['recovery_finish']}; prior acknowledgment {binding['prior_ack_ref']}.", ""]
        for corpus, summary in corpora.items():
            lines.extend([f"**{corpus}:** {summary['submitted']:,}/{summary['eligible']:,} eligible submitted; {summary['assessed']} assessed; {summary['unassessed']} unassessed. Raw envelope statuses {summary['raw_status_counts']}; current-parser statuses {summary['status_counts']}. Raw-valid focus: {summary['raw_valid_focus_counts']}.",
                f"Existing literal projections cover {summary['projection_covered']}/{summary['assessed']}; {summary['projection_uncovered']} lack literal projection. Phase recovery: {summary['phase_recovered']} distinct ({summary['phase_current_recovered']} current-parser, {summary['phase_historical_recovered']} historical replay; overlap counted once). {summary['derived_only_recovered']} additional literal-only recoveries; {summary['mechanically_usable']} combined mechanically usable; {summary['remaining_content_invalid']} content-invalid unresolved; {summary['technical_or_unknown']} technical/unknown unresolved.",
                f"Known usage {summary['usage']} across {summary['usage_available_rows']} rows; unavailable for {summary['usage_unavailable_rows']}. Charge ${summary['charged_nanousd']/1e9:.6f}; reserved submitted/unresolved ${summary['reserved_submitted_unresolved_nanousd']/1e9:.6f}; staged/unsubmitted ${summary['reserved_staged_unsubmitted_nanousd']/1e9:.6f}.", ""])
            for example in summary["examples"]:
                event = example["output"]["event"]
                entities = "; ".join(f"{p['surface']} ({p['kind']}; {', '.join(r['role'] for r in p['roles'])})" for p in event["participants"])
                lines.append(f"- [{example['title']}](<{example['url']}>) — {event['summary']} Entities: {entities or 'none extracted'}.")
            lines.append("")
        for row in technical:
            lines.append(f"Technical record [{row['title']}](<{row['url']}>): {json.dumps(row, ensure_ascii=False)}")
        lines.extend([f"Previously acknowledged assessment IDs (original records retained): {sorted(previously_acknowledged)}. Newly unacknowledged technical assessment IDs: {newly_unacknowledged}.",
            f"Retained controller finishes: {[(row['id'], row['reason'], row['ended_at']) for row in finishes]}",
            f"Drain obstacles: {json.dumps(binding['drain_obstacles'], ensure_ascii=False)}. Timed out with pending work: {binding['drain_timed_out']}.", "",
            "These are provisional mechanically checked article extractions, not confirmed events or grouping accuracy. Original statuses and stops remain unchanged; unprocessed/missing/invalid is not negative eligibility. Costs are conservative estimates, not invoices. Only previously submitted jobs were polled/downloaded and their retained responses validated/settled; no new inference, literal projections, embeddings, paid retries or controller restarts. This subsequent diagnostic reads retained outputs only. Exact protected Markdown retained; record_presentation does not support this technical kind."])
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
        parser.error("--allow-existing-job-reads is required; new inference is forbidden")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = DrainResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Drain only existing stopped-recovery jobs and retain their exact diagnostic under one full preflight", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "pending_jobs", "drain_obstacles", "charged_estimate_usd", "reserved_usd", "budget_frozen")}), flush=True)
        return 0 if not result["pending_jobs"] and not result["drain_obstacles"] else 1
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
