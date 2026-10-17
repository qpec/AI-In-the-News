"""Fill concurrent Luna Batch capacity in one audited session, with no paid retries.

This is an append-only operational amendment. Original files, stops, prompts,
reservations and the original admission deadline remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
import uuid

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, canonical, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError, InputTokenReceipt
from newsresearch.event_batch_live_gateway import ACTION_IDENTITY_KIND, ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.legacy import sha256
from newsresearch.runtime import audited_handler

from audit_article_scope_metadata import read_partition
from diagnose_luna_batch_capacity import diagnose_counts
from execute_luna_budget_batch import JOB_KIND, PLAN_KIND, require_receipt
from execute_luna_budget_wave import BulkExecutionResearch, action_blockers, validate_manifest
from luna_batch_budget_run import OWNER, ROOT, STUDY, present, save
from luna_batch_count_cache import count_many
import luna_batch_materialize as materialize
from luna_budget_continuation import load_continuation
import luna_multibatch as core
from poll_luna_budget_batch import ReconciliationResearch
from prepare_luna_budget_wave import ASSESSMENT_KIND, CORPORA, MANIFEST_KIND, canary_gate, choose_next, materialize_tasks
from project_luna_budget_results import ProjectionResearch

METHOD = "luna-budget-single-writer-capacity-fill-v1"
RUN_KIND = "luna_budget_fast_run"
FINISH_KIND = "luna_budget_fast_finish"
DIAGNOSTIC_KIND = "luna_batch_capacity_diagnostic"
MAX_QUEUE = 20_000_000
ACTOR = "codex:luna-batch-budget"


def implementation_hashes() -> dict[str, str]:
    names = ("run_luna_budget_fast.py", "luna_batch_count_cache.py", "diagnose_luna_batch_capacity.py",
        "execute_luna_budget_batch.py", "execute_luna_budget_wave.py", "prepare_luna_budget_wave.py",
        "poll_luna_budget_batch.py", "luna_budget_continuation.py", "luna_batch_results.py",
        "luna_batch_phase_projection.py", "luna_batch_materialize.py", "luna_multibatch.py",
        "project_luna_budget_results.py", "luna_batch_literal_projection.py", "luna_event_contract_v2.py")
    paths = ["scripts/" + name for name in names] + ["src/newsresearch/" + name for name in
        ("event_batch_budget.py", "event_batch_live_gateway.py", "event_batch_transport.py")]
    return {name: sha256(ROOT / name) for name in paths}


def active_input_tokens(book: BudgetBook, manifests: list[Json], jobs: list[Json], reconciled: set[str]) -> int:
    """Provider occupancy counts submitted unfinished files, never staged files."""
    active = {job["manifest"] for job in jobs if job["manifest"] not in reconciled}
    by_id = {row["id"]: row for row in manifests}
    if not active <= by_id.keys():
        raise AuditError("fast_active_job_manifest_missing")
    return sum(book.entry(task["custom_id"])["request"]["input_count"]["input_tokens"]
        for identifier in active for task in by_id[identifier]["tasks"])


def admission_reason(*, active_tokens: int, candidate_tokens: int, queue_cap: int,
                     incremental_nanousd: int, available_nanousd: int) -> str | None:
    if candidate_tokens > queue_cap:
        return "file_exceeds_provisional_queue_cap"
    if active_tokens + candidate_tokens > queue_cap:
        return "queue_pressure"
    if incremental_nanousd > available_nanousd:
        return "budget_pressure"
    return None


def terminal_reason(reason: str | None, pending_jobs: int) -> str | None:
    if reason is None or pending_jobs:
        return None
    return "budget_deferred" if reason == "budget_pressure" else "capacity_deferred"


class FastResearch(BulkExecutionResearch, ReconciliationResearch):
    """One Research.execute, one owner lock and writer; only count HTTP is threaded."""

    def selected(self, session: str, kind: str, plan_id: str) -> list[Json]:
        sql = "SELECT id FROM records WHERE kind=? AND json_extract(payload,'$.plan')=? ORDER BY created_event"
        self.ledger.append(session, "budget.fast.records.inspection.intended", {"sql": sql, "parameters": [kind, plan_id]})
        return [{**self.ledger.get(row["id"], kind), "id": row["id"]}
                for row in self.ledger.db.execute(sql, (kind, plan_id))]

    def view(self, session: str, plan_id: str) -> Json:
        manifests = self.selected(session, MANIFEST_KIND, plan_id)
        jobs = self.selected(session, JOB_KIND, plan_id)
        assessments = self.selected(session, ASSESSMENT_KIND, plan_id)
        reconciled = {row["manifest"] for row in self.selected(session, "luna_budget_job_reconciled", plan_id)}
        customs = [task["custom_id"] for manifest in manifests for task in manifest["tasks"]]
        job_ids = {job["manifest"] for job in jobs}
        if (len(customs) != len(set(customs)) or len(job_ids) != len(jobs)
                or not job_ids <= {row["id"] for row in manifests} or not reconciled <= job_ids
                or len({row["custom_id"] for row in assessments}) != len(assessments)):
            raise AuditError("fast_duplicate_or_unbound_work")
        projected = {row["original_assessment"] for row in self.selected(session, "luna_budget_literal_projection", plan_id)}
        return {"manifests": manifests, "jobs": jobs, "assessments": assessments, "reconciled": reconciled,
                "projected": projected}

    def check_gate(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook,
                   continuation: Json) -> list[str]:
        gate = canary_gate(plan_id, plan, view["assessments"], book, continuation)
        # Full reservations can temporarily consume the operating allowance.
        # The shared BudgetBook still decides admission; no reservation is freed here.
        blockers = [value for value in gate["blockers"] if value != "shared_operating_budget_exhausted"]
        obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle")
                     for row in self.selected(session, kind, plan_id)]
        blockers += action_blockers(self.rows(session, ACTION_KIND), self.rows(session, RECEIPT_KIND), obstacles)
        if self.latest(STOP_KIND, STUDY):
            blockers.append("shared_gateway_stopped")
        return sorted(set(blockers))

    def validate_diagnostic(self, session: str, plan_id: str, reference: str, view: Json,
                            policy: str, book_state: str) -> Json:
        proof = self.ledger.get(reference, DIAGNOSTIC_KIND)
        if (proof.get("plan") != plan_id or proof.get("budget_state") != book_state
                or proof.get("budget_frozen") is not False or proof.get("unknown_or_frozen_budget_entries") != 0):
            raise AuditError("fast_diagnostic_plan_or_current_budget_mismatch")
        collisions = [row for row in proof["count_diagnostics"] if row.get("changed_key_collision")]
        if not collisions:
            raise AuditError("fast_exact_count_collision_proof_required")
        rows = {name: self.rows(session, kind) for name, kind in
                (("actions", ACTION_KIND), ("identities", ACTION_IDENTITY_KIND), ("receipts", RECEIPT_KIND))}
        by_manifest = {row["id"]: row for row in view["manifests"]}
        submitted = {row["manifest"] for row in view["jobs"]}
        verified = []
        for item in collisions:
            manifest = by_manifest.get(item["manifest"])
            if manifest is None or item["manifest"] in submitted:
                raise AuditError("fast_collision_manifest_already_submitted")
            matches = [(task, attempt) for task, attempt in zip(manifest["tasks"], manifest["attempt_ids"], strict=True)
                       if task["custom_id"] == item["custom_id"]]
            if len(matches) != 1:
                raise AuditError("fast_collision_task_not_in_manifest")
            task, attempt = matches[0]
            if (task["request_body_ref"] != item["request_body_ref"] or task["corpus_id"] != item["corpus_id"]
                    or attempt != item["frozen_attempt_id"] or attempt in self.ledger.unresolved
                    or self.ledger.db.execute("SELECT id FROM attempts WHERE id=?", (attempt,)).fetchone()):
                raise AuditError("fast_collision_task_or_paid_attempt_changed")
            self.ledger.append(session, "budget.fast.diagnostic.exact_artifacts.inspection.intended", {
                "diagnostic": reference, "manifest": manifest["id"], "task": task["custom_id"],
                "request_body_ref": task["request_body_ref"], "candidates": item["candidates"]})
            recomputed = diagnose_counts(plan_id, [{**task, "manifest": manifest["id"]}], rows,
                                          self.ledger.artifacts.read_bytes)[0]
            if any(recomputed[key] != item[key] for key in recomputed):
                raise AuditError("fast_collision_diagnostic_not_reproducible")
            if (not recomputed["gateway_dispatch_intent_absent"] or not recomputed["successful_exact_count_available"]
                    or len(recomputed["candidates"]) != 1):
                raise AuditError("fast_collision_not_known_successful_pre_dispatch")
            candidate = recomputed["candidates"][0]
            action = self.ledger.get(candidate["action_record"], ACTION_KIND)
            receipt = self.ledger.get(candidate["receipt_record"], RECEIPT_KIND)
            if (action.get("policy_id") != policy or action.get("authorization_id") != STUDY
                    or receipt.get("authorization_id") != STUDY or receipt.get("status") != 200
                    or receipt.get("error_type") is not None):
                raise AuditError("fast_collision_receipt_scope_mismatch")
            verified.append({"custom_id": task["custom_id"], "manifest": manifest["id"],
                             "attempt": attempt, "count_receipt": candidate["receipt_record"]})
        return {"diagnostic_ref": reference, "verified_collisions": verified, "new_provider_calls": 0}

    def stage(self, session: str, plan_id: str, plan: Json, view: Json, book_state: str,
              snapshot: core.ContractSnapshot) -> Json:
        manifested = {task["custom_id"] for row in view["manifests"] for task in row["tasks"]}
        if not {task["custom_id"] for task in plan["canary_tasks"]} <= manifested:
            raise AuditError("fast_canary_manifests_missing")
        number = 1 + max((row.get("wave_number", 0) for row in view["manifests"]), default=0)
        created = []
        for corpus in CORPORA:
            binding = plan["corpora"][corpus]
            partition = binding["partition"]
            self.ledger.append(session, "budget.fast.queue.inspection.intended", {
                "corpus_id": corpus, "queue_ref": binding["queue_ref"], "protocol": self.execution_protocol})
            if read_partition(Path(partition["resolved_root"]), corpus) != partition:
                raise AuditError("fast_partition_changed")
            queue = self.ledger.artifacts.read(binding["queue_ref"])
            if queue.get("corpus_id") != corpus or queue.get("manifest_sha256") != binding["manifest_sha256"]:
                raise AuditError("fast_queue_partition_changed")
            selected = choose_next(queue, manifested, 250)
            if not selected:
                continue
            export = self.ledger.artifacts.read(binding["preparation_export_ref"])
            materialize.validate_preparation_binding(export["result"], export["manifest"], partition, snapshot)
            tasks = materialize_tasks(self, session, export, selected, partition, snapshot)
            raw = b"".join(canonical(self.ledger.artifacts.read(task["request_ref"])).encode() + b"\n" for task in tasks)
            if len(raw) >= core.PROVIDER_BYTE_CEILING_EXCLUSIVE:
                raise AuditError("fast_file_exceeds_provider_byte_ceiling")
            reference = save(self, session, raw, "Exact unchanged250-file before count/upload/create")
            if read_partition(Path(partition["resolved_root"]), corpus) != partition:
                raise AuditError("fast_partition_changed_after_materialization")
            value = {"plan": plan_id, "corpus_id": corpus, "phase": "bulk", "tasks": tasks,
                "jsonl_ref": reference, "attempt_ids": [str(uuid.uuid4()) for _ in tasks],
                "authorization_id": STUDY, "created_at": utc(), "wave_number": number,
                "protocol": self.execution_protocol, "fast_run": self.fast_run, "budget_state_at_staging": book_state}
            identifier = self.ledger.record(session, MANIFEST_KIND, f"{plan_id}:bulk:{number}:{corpus}", value)
            view["manifests"].append({**value, "id": identifier})
            created.append({"manifest": identifier, "corpus_id": corpus, "requests": len(tasks)})
        if any(sha256(ROOT / name) != value for name, value in plan["implementation"].items()):
            raise AuditError("fast_preparation_changed_during_materialization")
        return present(self, session, "luna_budget_fast_staging", {"plan": plan_id, "manifests": created,
            "new_requests_staged": sum(row["requests"] for row in created), "new_model_calls": 0},
            f"Staged {sum(row['requests'] for row in created)} exact full-text requests in {len(created)} separate corpus files. "
            "Zero model calls in staging; files still require exact counts and whole-file cost admission. "
            "Protected exact presentation retained; record_presentation does not support this technical kind.")

    def dispatch(self, session: str, plan_id: str, plan: Json, policy: str, book: BudgetBook, state: str,
                 manifest: Json, raw: bytes, *, active_tokens: int, queue_cap: int,
                 workers: int, deadline: float) -> tuple[BudgetBook, str, str | None, Json | None]:
        if time.time() >= deadline:
            return book, state, "deadline", None
        tasks, manifest_id, corpus = manifest["tasks"], manifest["id"], manifest["corpus_id"]
        self.ledger.append(session, "budget.fast.parallel_count.bound", {"protocol": self.execution_protocol,
            "run": self.fast_run, "plan": plan_id, "manifest": manifest_id, "workers": workers})
        if not hasattr(self, "retained_counts"):
            self.retained_counts: dict[str, dict[str, Json]] = {}
        if manifest_id not in self.retained_counts:
            self.retained_counts[manifest_id] = count_many(self, session, plan_id=plan_id, policy_id=policy, authorization_id=STUDY,
                tasks=[{"custom_id": task["custom_id"], "body_ref": task["request_body_ref"], "corpus_id": corpus} for task in tasks],
                max_workers=workers, transport=self.transport)
        receipts = self.retained_counts[manifest_id]
        needed = 0
        counts = {}
        for task in tasks:
            custom = task["custom_id"]
            receipt = receipts[custom]
            counted = InputTokenReceipt(receipt["input_tokens"], core.MODEL, task["request_body_ref"],
                receipt["body_sha256"], "provider_responses_input_tokens", receipt.get("provider_request_id"))
            counts[custom] = counted
            try:
                old = book.entry(custom)
            except BudgetError:
                old = None
            if old is None:
                needed += book.price_policy.cost(counted.input_tokens, 4096)
            elif (old["status"] != "reserved" or old["request"]["plan_id"] != plan_id
                    or old["request"]["corpus_id"] != corpus or old["request"]["request_sha256"] != task["request_body_ref"]
                    or old["request"]["max_output_tokens"] != 4096
                    or old["request"]["input_count"]["receipt_sha256"] != counted.receipt_sha256
                    or old["request"]["input_count"]["input_tokens"] != counted.input_tokens):
                raise AuditError("fast_reserved_request_changed_or_already_spent")
        tokens = sum(value.input_tokens for value in counts.values())
        reason = admission_reason(active_tokens=active_tokens, candidate_tokens=tokens, queue_cap=queue_cap,
            incremental_nanousd=needed, available_nanousd=book.available_nanousd)
        if reason:
            self.ledger.record(session, "luna_budget_fast_deferral", manifest_id, {"plan": plan_id,
                "run": self.fast_run, "manifest": manifest_id, "reason": reason, "active_input_tokens": active_tokens,
                "candidate_input_tokens": tokens, "needed_nanousd": needed, "budget_state": state, "observed_at": utc()})
            return book, state, reason, None
        if time.time() >= deadline:
            return book, state, "deadline", None
        # Copy first: even an unexpected reservation validation failure cannot
        # persist a new partial reservation of this whole frozen file.
        candidate_book = BudgetBook.from_dict(book.to_dict())
        for task in tasks:
            candidate_book.reserve(request_id=task["custom_id"], task_id=task["custom_id"], corpus_id=corpus,
                plan_id=plan_id, request_sha256=task["request_body_ref"], input_count=counts[task["custom_id"]],
                max_output_tokens=4096, price_fingerprint=book.price_policy.fingerprint)
        book = candidate_book
        state = self.gateway.save_book(session, book, state)
        upload = self.action(session, plan_id, policy, "upload:" + manifest_id,
            {"method": "POST", "path": "/v1/files", "purpose": "batch", "filename": corpus + "-" + manifest_id[:16] + ".jsonl",
             "content_sha256": manifest["jsonl_ref"]}, raw)
        file = require_receipt(upload, self)
        if file.get("purpose") != "batch" or file.get("bytes") != len(raw) or not file.get("id"):
            raise ResearchError("fast_upload_receipt_invalid")
        create = {"input_file_id": file["id"], "endpoint": "/v1/responses", "completion_window": "24h",
            "metadata": {"study": STUDY, "plan": plan_id, "corpus": corpus, "manifest": manifest_id}}
        dispatch_ref = save(self, session, create, "Exact unchanged reserved Batch create")
        for task, attempt in zip(tasks, manifest["attempt_ids"], strict=True):
            if attempt in self.ledger.unresolved:
                intended = self.ledger.unresolved[attempt]
                if intended.get("request") != task["request_body_ref"] or intended.get("dispatch") != dispatch_ref:
                    raise AuditError("fast_existing_attempt_intent_changed")
                continue
            if self.ledger.db.execute("SELECT id FROM attempts WHERE id=?", (attempt,)).fetchone():
                raise AuditError("fast_completed_attempt_no_retry")
            intended = {"attempt": attempt, "task_key": task["custom_id"], "number": 1, "batch": manifest_id,
                "plan": plan_id, "request": task["request_body_ref"], "request_sha256": task["request_body_ref"],
                "dispatch": dispatch_ref, "budget_authorization_id": STUDY, "budget_request_id": task["custom_id"],
                "source_versions": [], "source_descriptor": task["descriptor"], "article_exposures": 1,
                "approval_policy": policy, "started_at": utc(), "execution_protocol": self.execution_protocol,
                "preparation_versions": plan["versions"]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
        if time.time() >= deadline:
            self.ledger.record(session, "luna_budget_fast_deadline_before_dispatch", manifest_id,
                {"plan": plan_id, "run": self.fast_run, "manifest": manifest_id, "attempt_ids": manifest["attempt_ids"],
                 "deadline_epoch": deadline, "provider_create_called": False, "observed_at": utc()})
            return book, state, "deadline", None
        receipt = self.action(session, plan_id, policy, "create:" + manifest_id,
            {"method": "POST", "path": "/v1/batches"}, canonical(create).encode(),
            reserved_request_ids=[task["custom_id"] for task in tasks], attempt_ids=manifest["attempt_ids"])
        answer = require_receipt(receipt, self)
        if (not str(answer.get("id", "")).startswith("batch_") or answer.get("input_file_id") != file["id"]
                or answer.get("endpoint") != "/v1/responses" or answer.get("completion_window") != "24h"):
            raise ResearchError("fast_create_receipt_invalid")
        value = {"plan": plan_id, "manifest": manifest_id, "corpus_id": corpus, "job_id": answer["id"],
            "receipt": receipt["id"], "provider_status": answer.get("status"), "created_at": utc(), "request_count": len(tasks)}
        identifier = self.ledger.record(session, JOB_KIND, manifest_id, value)
        return book, state, None, {**value, "id": identifier}

    def report(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook, state: str,
               *, reason: str | None = None) -> Json:
        jobs = view["jobs"]
        submitted = sum(row["request_count"] for row in jobs)
        assessments = view["assessments"]
        job_ids = {row["manifest"] for row in jobs}
        manifested = sum(len(row["tasks"]) for row in view["manifests"])
        if not len(assessments) <= submitted <= manifested <= plan["pending_requests"]:
            raise AuditError("fast_coverage_exceeds_frozen_queue")
        value = {"plan": plan_id, "run": self.fast_run, "protocol": self.fast_protocol,
            "submitted": submitted, "assessments": len(assessments),
            "status_counts": dict(Counter(row["status"] for row in assessments)),
            "raw_status_counts": dict(Counter(row.get("raw_status", row["status"]) for row in assessments)),
            "pending_jobs": len(job_ids - view["reconciled"]), "pending_requests": submitted - len(assessments),
            "staged_files": sum(row["id"] not in job_ids for row in view["manifests"]),
            "unmanifested": plan["pending_requests"] - manifested, "eligible_not_submitted": plan["pending_requests"] - submitted,
            "active_input_tokens": active_input_tokens(book, view["manifests"], jobs, view["reconciled"]),
            "queue_token_cap": self.queue_cap, "account_capacity_verified": False,
            "charged_estimate_usd": book.charged_nanousd / 1e9, "reserved_usd": book.reserved_nanousd / 1e9,
            "budget_state": state, "deadline_epoch": self.deadline, "finished_reason": reason,
            "automatic_retries": 0,
            "unprojected_assessments": sum(row["id"] not in view["projected"] for row in assessments),
            "human_validated": False}
        markdown = (f"Luna fast workflow: **{submitted:,} submitted / {len(assessments):,} assessed**; "
            f"parser statuses {value['status_counts']}; raw statuses {value['raw_status_counts']}. "
            f"{value['pending_requests']:,} unassessed in {value['pending_jobs']} unfinished jobs; "
            f"{value['active_input_tokens']:,}/{self.queue_cap:,} own queued input tokens (account capacity unverified). "
            f"{value['staged_files']} staged files; {value['unmanifested']:,} unmanifested requests. "
            f"Conservative charge ${value['charged_estimate_usd']:.6f}; reserved ${value['reserved_usd']:.6f}; "
            f"same $120 operating/$150 maximum. Stop: {reason or 'none'}. "
            "Original and derived interpretations remain separate; invalid/missing work is not negative eligibility. "
            f"{value['unprojected_assessments']:,} assessments await literal projection, deferred until normal drained completion. "
            "No retries, embeddings, semantic validation or accepted dossiers. "
            "Protected exact presentation retained; record_presentation does not support this technical kind.")
        return present(self, session, "luna_budget_fast_status", value, markdown)

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("fast_original_owner_required")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("fast_explicit_online_execution_required")
        plan_id, reference = data["plan"], data["continuation_ref"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        continuation = load_continuation(self, session, plan_id, reference)
        if continuation is None or plan.get("authorization_id") != STUDY:
            raise AuditError("fast_existing_phase_continuation_required")
        self.deadline = continuation["deadline_epoch"]
        self.queue_cap, workers = data.get("queue_token_cap", MAX_QUEUE), data.get("count_workers", 16)
        if (type(self.queue_cap) is not int or not 1 <= self.queue_cap <= MAX_QUEUE
                or type(workers) is not int or not 1 <= workers <= 16):
            raise ResearchError("fast_capacity_or_workers_outside_bounds")
        implementation = implementation_hashes()
        if any(sha256(ROOT / name) != value for name, value in plan["implementation"].items()):
            raise AuditError("fast_frozen_preparation_changed")
        snapshot = core.load_contract_snapshot()
        if snapshot.contract_sha256 != plan["contract_sha256"]:
            raise AuditError("fast_frozen_contract_changed")
        self.fast_protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":fast-fill",
            "content": {"method": METHOD, "plan": plan_id, "versions": plan["versions"], "implementation": implementation,
                "continuation_ref": reference, "diagnostic_ref": data["diagnostic_ref"], "deadline_epoch": self.deadline,
                "queue_token_cap": self.queue_cap, "account_capacity_verified": False, "count_workers": workers,
                "user_instruction": "I want all processed asap, do as much at once as possible", "follow_up": "Parallel?",
                "rules": "One active audited owner/session/writer. Reconcile startup jobs first. Preserve original stops and deadline. Count exact inputs with explicit same-byte successful receipt reuse and <=16 HTTP workers. Fill unchanged separate-corpus250files until provisional20M own active provider tokens or full-file budget pressure. All staged and unknown money stays held. On capacity/budget pressure wait for active jobs and settle observed usage; otherwise defer coverage. No paid retries, queue resets, prompt/output changes or semantic acceptance. Fail closed on technical/unknown/audit errors. Literal projection once at normal drained terminal."}})["id"]
        self.execution_protocol = self.fast_protocol
        if self.gateway.load_book(session, STUDY) is None:
            raise AuditError("fast_existing_shared_budget_required")
        policy, book, state = self.authorization(session, context, plan_id, plan)
        view = self.view(session, plan_id)
        key = plan_id + ":" + reference + ":fast-v1"
        old = self.latest(RUN_KIND, key)
        run_binding = {"plan": plan_id, "protocol": self.fast_protocol, "implementation": implementation,
            "continuation_ref": reference, "diagnostic_ref": data["diagnostic_ref"], "deadline_epoch": self.deadline,
            "queue_token_cap": self.queue_cap, "count_workers": workers, "authorization_id": STUDY,
            "original_run": continuation["original_run"], "original_stop": continuation["original_stop"]}
        if old:
            self.fast_run, run = old
            if any(run.get(name) != value for name, value in run_binding.items()):
                raise AuditError("fast_run_binding_changed_no_reset")
        else:
            proof = self.validate_diagnostic(session, plan_id, data["diagnostic_ref"], view, policy, state)
            run = {**run_binding, "started_at": utc(), "diagnostic_validation": proof,
                "startup_pending_manifests": [row["manifest"] for row in view["jobs"] if row["manifest"] not in view["reconciled"]]}
            self.fast_run = self.ledger.record(session, RUN_KIND, key, run)
        finished = self.latest(FINISH_KIND, self.fast_run)
        if finished:
            return self.report(session, plan_id, plan, view, book, state, reason=finished[1]["reason"])
        blockers = self.check_gate(session, plan_id, plan, view, book, continuation)
        reason = "technical_stop" if blockers else None
        next_poll = 0.0
        backoff = 30.0
        pressure: str | None = None
        startup_observed = False
        initial = self.report(session, plan_id, plan, view, book, state)
        print(initial["markdown"], flush=True)
        while reason is None:
            if time.time() >= self.deadline:
                reason = "deadline"
                break
            pending = {row["manifest"] for row in view["jobs"]} - view["reconciled"]
            startup = not startup_observed and bool(pending & set(run["startup_pending_manifests"]))
            job_ids = {row["manifest"] for row in view["jobs"]}
            staged = [row for row in view["manifests"] if row["id"] not in job_ids]
            unmanifested = plan["pending_requests"] - sum(len(row["tasks"]) for row in view["manifests"])
            if not pending and not staged and not unmanifested:
                reason = "complete"
                break
            if pressure and not pending:
                reason = terminal_reason(pressure, 0)
                break
            if pending and (startup or pressure or not staged and not unmanifested) and time.time() >= next_poll:
                print(json.dumps({"fast_phase": "reconcile", "unfinished_jobs": len(pending)}), flush=True)
                result = ReconciliationResearch._status(self, session, context,
                    {"plan": plan_id, "continuation_ref": reference, "allow_paid_execution": True})
                print(result["markdown"], flush=True)
                self.execution_protocol = self.fast_protocol
                view = self.view(session, plan_id)
                saved = self.gateway.load_book(session, STUDY)
                if saved is None:
                    raise AuditError("fast_shared_budget_disappeared")
                book, state = saved
                blockers = self.check_gate(session, plan_id, plan, view, book, continuation)
                if result["obstacles"] or blockers:
                    reason = "technical_stop"
                    break
                startup_observed = True
                next_poll = time.time() + backoff
                backoff = min(120.0, backoff * 2)
                pressure = None  # One fresh admission opportunity after polling.
                continue
            if startup or pressure or not staged and not unmanifested:
                duration = min(30.0, max(0.0, next_poll - time.time()), max(0.0, self.deadline - time.time()))
                print(json.dumps({"fast_wait_seconds": duration, "pending_jobs": len(pending), "reason": pressure or "startup_or_completion"}), flush=True)
                time.sleep(duration)
                continue
            if not staged:
                print(json.dumps({"fast_phase": "stage", "max_per_corpus": 250}), flush=True)
                result = self.stage(session, plan_id, plan, view, state, snapshot)
                print(result["markdown"], flush=True)
                if not result["manifests"]:
                    reason = "stalled"
                continue
            manifest = staged[0]
            print(json.dumps({"fast_phase": "count_admit_submit", "corpus": manifest["corpus_id"],
                              "requests": len(manifest["tasks"]), "count_workers": workers}), flush=True)
            raw = validate_manifest(self, session, plan_id, plan, manifest["id"], manifest, snapshot)
            try:
                book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, raw,
                    active_tokens=active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
                    queue_cap=self.queue_cap, workers=workers, deadline=self.deadline)
            except AuditError:
                raise
            except (ResearchError, BudgetError) as error:
                self.ledger.record(session, "luna_budget_fast_obstacle", self.fast_run,
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
            result = self.report(session, plan_id, plan, view, book, state)
            print(result["markdown"], flush=True)
        self.ledger.record(session, FINISH_KIND, self.fast_run, {"plan": plan_id, "run": self.fast_run,
            "reason": reason, "ended_at": utc(), "budget_state": state, "blockers": blockers})
        return self.report(session, plan_id, plan, view, book, state, reason=reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--continuation-ref", required=True)
    parser.add_argument("--diagnostic-ref", required=True)
    parser.add_argument("--queue-token-cap", type=int, default=MAX_QUEUE)
    parser.add_argument("--count-workers", type=int, default=16)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required for this authorized continuation")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"starting_audited_fast_workflow": args.plan, "count_workers": args.count_workers,
                      "provisional_queue_cap": args.queue_token_cap, "account_capacity_verified": False}), flush=True)
    engine = FastResearch(OWNER, config=Config(offline=False))
    try:
        result = engine.execute("status", vars(args), objective="Fill authorized Luna Batch capacity quickly under unchanged shared costs and deadline", actor=ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "presentation": result.get("presentation"), "reason": result["finished_reason"]}), flush=True)
    finally:
        engine.close()
    if result["finished_reason"] in {"complete", "budget_deferred"} and not result["pending_jobs"]:
        print(json.dumps({"fast_phase": "final_offline_literal_projection"}), flush=True)
        projector = ProjectionResearch(OWNER, config=Config(offline=True))
        try:
            projection = projector.execute("status", {"plan": args.plan},
                objective="Finish deterministic retained-output projection after drained fast workflow", actor=ACTOR)
            print(projection["markdown"], flush=True)
        finally:
            projector.close()
    return 0 if result["finished_reason"] in {"complete", "budget_deferred", "deadline"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
