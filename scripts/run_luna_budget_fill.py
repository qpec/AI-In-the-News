"""Fill the existing Luna Batch queue before polling, within its original budget.

Existing staged files and exact requests remain unchanged. New files contain
up to 1000 same-corpus requests, capped at 64 MB. No inference retries occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any
import uuid
import zipfile

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, canonical, digest, utc
from newsresearch.event_batch_budget import BudgetBook, BudgetError
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.legacy import sha256, within
from newsresearch.runtime import audited_handler

from audit_luna_excerpts import offline_tokenizer
from drain_luna_budget_recovery import DrainResearch
from execute_luna_budget_wave import action_blockers, validate_manifest
from luna_batch_budget_run import OWNER, ROOT, STUDY, present, save
from luna_batch_phase_projection import parse_batch_results_phase_aware
import luna_batch_materialize as materialize
import luna_budget_truncation_policy as truncation
import luna_budget_scheduler_handoff as handoff
from luna_budget_fill_scheduler_candidate import FillFirstScheduler
import run_luna_budget_throughput as predecessor
from prepare_luna_budget_execution import queued_row
from run_luna_budget_recovery import recovery_gate
import run_luna_budget_fast as fast

METHOD = "luna-budget-fill-first-v1"
RUN_KIND = "luna_budget_throughput_run"
FINISH_KIND = "luna_budget_throughput_finish"
OBSTACLE_KIND = "luna_budget_throughput_obstacle"
MAX_NEW_REQUESTS = 1000
MAX_NEW_BYTES = 64_000_000
COUNT_WORKERS = 16
QUEUE_CAP = 20_000_000
TRACKED = (fast.MANIFEST_KIND, fast.JOB_KIND, fast.ASSESSMENT_KIND,
    "luna_budget_job_reconciled", "luna_budget_literal_projection", ACTION_KIND, RECEIPT_KIND, STOP_KIND,
    *truncation.chain.OBSTACLES, OBSTACLE_KIND)


def implementation_hashes() -> dict[str, str]:
    result = truncation.implementation_hashes()
    for name in ("run_luna_budget_throughput.py", "run_luna_budget_throughput_with_key.ps1",
                 "run_luna_budget_fill.py", "run_luna_budget_fill_with_key.ps1",
                 "luna_budget_fill_scheduler_candidate.py", "luna_budget_scheduler_handoff.py",
                 "luna_budget_worker_control.py"):
        path = "scripts/" + name
        result[path] = sha256(ROOT / path)
    return result


class AdmissionDeadlineTransport:
    """Final local no-send deadline check at the actual provider boundary."""
    def __init__(self, original: Any, deadline: float) -> None:
        self.original, self.deadline = original, deadline
        self.synthetic = bool(getattr(original, "synthetic", False))
        self.max_retries = 0
        self.deadline_blocked = False

    def perform(self, request: Json, body: bytes | None, client_request_id: str) -> BatchReceipt:
        if request.get("method") == "POST" and request.get("path") == "/v1/batches" and time.time() >= self.deadline:
            self.deadline_blocked = True
            return BatchReceipt(None, None, error_type="AdmissionDeadlineExpiredBeforeNetwork", unknown=False)
        return self.original.perform(request, body, client_request_id)


def projection_value(row: Any) -> Json:
    """Hash exact SQLite bytes verified by this session's full preflight.

    The owner is single-writer and projections are append-only. No disk artifact
    is reopened: preflight verified all existing artifacts, and new records use
    the same runtime's durable record writer. This is never a cross-session seal.
    """
    if (row["kind"] not in TRACKED or not isinstance(row["logical_key"], str)
            or not isinstance(row["payload"], str) or type(row["created_event"]) is not int
            or row["created_event"] <= 0 or row["supersedes"] is not None and not isinstance(row["supersedes"], str)):
        raise AuditError("fill_record_projection_type_changed")
    if (hashlib.sha256(row["payload"].encode("utf-8")).hexdigest() != row["artifact"]
            or digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"],
                       "supersedes": row["supersedes"]}) != row["id"]):
        raise AuditError("fill_record_projection_integrity_changed")
    value = json.loads(row["payload"])
    if not isinstance(value, dict):
        raise AuditError("fill_record_projection_not_object")
    return value


def timing(phase: str, started: float, **details: Any) -> None:
    print(json.dumps({"phase": phase, "elapsed_seconds": round(time.perf_counter() - started, 3), **details}), flush=True)


class IncrementalIndex:
    """Only new immutable record projections are read after the first snapshot."""
    def __init__(self) -> None:
        self.cursor = 0
        self.records: dict[str, dict[str, Json]] = {kind: {} for kind in TRACKED}
        self.assessment_revision = 0

    def refresh(self, engine: Any, session: str, plan_id: str) -> None:
        truncation.require_active(engine, session)
        sql = "SELECT id,kind,logical_key,payload,artifact,supersedes,created_event FROM records WHERE created_event>? AND kind IN (" + ",".join("?" for _ in TRACKED) + ") ORDER BY created_event"
        parameters = [self.cursor, *TRACKED]
        engine.ledger.append(session, "budget.throughput.incremental_read.intended", {"sql": sql, "parameters": parameters,
            "plan": plan_id, "previous_cursor": self.cursor, "authorization_id": STUDY})
        for row in engine.ledger.db.execute(sql, parameters):
            self.cursor = max(self.cursor, row["created_event"])
            value = {**projection_value(row), "id": row["id"]}
            if not (value.get("plan") == plan_id or value.get("plan_id") == plan_id
                    or value.get("authorization_id") == STUDY or row["kind"] == STOP_KIND and row["logical_key"] == STUDY):
                continue
            if row["id"] in self.records[row["kind"]]:
                raise AuditError("throughput_incremental_record_repeated")
            self.records[row["kind"]][row["id"]] = value
            if row["kind"] == fast.ASSESSMENT_KIND:
                self.assessment_revision += 1

    def rows(self, kind: str) -> list[Json]:
        return list(self.records[kind].values())

    def view(self) -> Json:
        manifests, jobs, assessments = (self.rows(kind) for kind in (fast.MANIFEST_KIND, fast.JOB_KIND, fast.ASSESSMENT_KIND))
        customs = [task["custom_id"] for row in manifests for task in row["tasks"]]
        attempts = [attempt for row in manifests for attempt in row["attempt_ids"]]
        manifest_ids, submitted = {row["id"] for row in manifests}, {row["manifest"] for row in jobs}
        reconciled = {row["manifest"] for row in self.rows("luna_budget_job_reconciled")}
        if (len(customs) != len(set(customs)) or len(attempts) != len(set(attempts))
                or len(jobs) != len(submitted) or not submitted <= manifest_ids or not reconciled <= submitted
                or len({row["custom_id"] for row in assessments}) != len(assessments)
                or any(row["manifest"] not in submitted for row in assessments)):
            raise AuditError("throughput_duplicate_or_unbound_stable_work")
        return {"manifests": manifests, "jobs": jobs, "assessments": assessments, "reconciled": reconciled,
            "projected": {row["original_assessment"] for row in self.rows("luna_budget_literal_projection")}}


def select_prefix(items: list[Json], export: Json, manifested: set[str]) -> list[Json]:
    selected: list[Json] = []
    size = 0
    for item in items:
        if item["custom_id"] in manifested:
            continue
        count = queued_row(export, item)["descriptor"]["line_bytes"]
        if type(count) is not int or count <= 0 or count > MAX_NEW_BYTES:
            raise AuditError("throughput_single_record_byte_bound_invalid")
        if len(selected) == MAX_NEW_REQUESTS or size + count > MAX_NEW_BYTES:
            break
        selected.append(item)
        size += count
    return selected


def validate_large_manifest(engine: Any, session: str, plan_id: str, plan: Json,
                            manifest: Json, snapshot: fast.core.ContractSnapshot) -> bytes:
    """Apply the unchanged exact contract validator to contiguous <=250 slices."""
    if manifest.get("throughput_method") == predecessor.METHOD:
        return predecessor.validate_large_manifest(engine, session, plan_id, plan, manifest, snapshot)
    tasks, attempts = manifest.get("tasks"), manifest.get("attempt_ids")
    if (not isinstance(tasks, list) or not 1 <= len(tasks) <= MAX_NEW_REQUESTS
            or not isinstance(attempts, list) or len(attempts) != len(tasks)
            or len(set(attempts)) != len(attempts)
            or len({task["custom_id"] for task in tasks}) != len(tasks)):
        raise AuditError("throughput_large_manifest_invalid")
    if len(tasks) <= 250 and manifest.get("throughput_method") is None:
        return validate_manifest(engine, session, plan_id, plan, manifest["id"], manifest, snapshot)
    if manifest.get("throughput_method") != METHOD or not manifest.get("protocol"):
        raise AuditError("throughput_large_manifest_unregistered")
    protocol = engine.ledger.get(manifest["protocol"], "protocol")["content"]
    if (protocol.get("method") != METHOD or protocol.get("plan") != plan_id
            or protocol.get("implementation") != implementation_hashes()
            or protocol.get("max_new_requests") != MAX_NEW_REQUESTS or protocol.get("max_new_bytes") != MAX_NEW_BYTES):
        raise AuditError("throughput_large_manifest_protocol_changed")
    engine.ledger.append(session, "budget.throughput.file_validation.intended", {"manifest": manifest["id"],
        "protocol": manifest["protocol"], "tasks": len(tasks), "validator": "unchanged contiguous250 contract slices"})
    chunks = []
    for start in range(0, len(tasks), 250):
        chunk = tasks[start:start + 250]
        raw = b"".join(canonical(engine.ledger.artifacts.read(task["request_ref"])).encode() + b"\n" for task in chunk)
        reference = save(engine, session, raw, "Exact contiguous validation slice of larger unchanged request file")
        sliced = {**manifest, "tasks": chunk, "attempt_ids": attempts[start:start + 250], "jsonl_ref": reference}
        chunks.append(validate_manifest(engine, session, plan_id, plan, manifest["id"], sliced, snapshot))
    raw = b"".join(chunks)
    if len(raw) > MAX_NEW_BYTES or engine.ledger.artifacts.read_bytes(manifest["jsonl_ref"]) != raw:
        raise AuditError("throughput_large_file_bytes_changed_or_oversized")
    return raw


class FillResearch(fast.FastResearch):
    queues: dict[str, tuple[Json, Json]]
    classification: Json
    def current(self, session: str, plan_id: str) -> tuple[Json, BudgetBook, str]:
        started, first = time.perf_counter(), self.index.cursor == 0
        self.index.refresh(self, session, plan_id)
        if first:
            timing("initial_index", started, records=sum(len(rows) for rows in self.index.records.values()))
        saved = self.gateway.load_book(session, STUDY)
        if saved is None:
            raise AuditError("throughput_current_book_missing")
        return self.index.view(), saved[0], saved[1]

    def gate(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook) -> list[str]:
        # Exact current hold/book validation remains independent of cached history.
        held = self.verified.baseline["held_failure"]
        history = [event for event in book.to_dict()["events"]
                   if event["value"].get("request_id") == held["custom_id"]]
        if book.entry(held["custom_id"]) != held["entry"] or history != held["event_history"]:
            raise AuditError("throughput_original_held_cost_changed")
        try:
            truncation.chain.held.validate_book(book, plan_id, plan, held)
        except AuditError as error:
            if str(error) in {"held_cost_new_or_changed_unknown_blocks", "held_cost_budget_binding_frozen_or_exceeded"}:
                # Preserve the real anomalous book and emit a terminal report.
                # This return never authorizes a provider action.
                return [str(error)]
            raise
        # A stable assessment revision is insufficient: the current settlement,
        # retained receipt/proof and code must also match on every admission.
        self.classification = truncation.classify_failures(self, session, self.verified, view["assessments"], book)
        gate = fast.canary_gate(plan_id, plan, view["assessments"], book, self.verified.baseline["phase"])
        blockers = [item for item in gate["blockers"] if item not in {
            "shared_operating_budget_exhausted", "shared_budget_unknown_or_unresolved_charge"}]
        blockers = recovery_gate(blockers, view["assessments"], self.verified.baseline["phase"], self.classification["acknowledgment"])
        obstacles = [row for kind in (*truncation.chain.OBSTACLES, OBSTACLE_KIND) for row in self.index.rows(kind)]
        blockers += action_blockers(self.index.rows(ACTION_KIND), self.index.rows(RECEIPT_KIND), obstacles)
        if self.index.rows(STOP_KIND):
            blockers.append("shared_gateway_stopped")
        if self.classification["unqualified_failures"]:
            blockers.append("unqualified_technical_failure")
        return sorted(set(blockers))

    def action(self, session: str, plan_id: str, policy: str, key: str, request: Json,
               body: bytes | None = None, **kwargs: Any) -> Json:
        if request.get("method") == "POST" and request.get("path") in {"/v1/files", "/v1/batches"}:
            if time.time() >= self.deadline:
                raise ResearchError("throughput_deadline_before_provider_write")
            view, book, _ = self.current(session, plan_id)
            blockers = self.gate(session, plan_id, self.plan, view, book)
            if blockers:
                raise ResearchError("throughput_admission_blocked:" + ",".join(blockers))
        return super().action(session, plan_id, policy, key, request, body, **kwargs)

    def stage(self, session: str, plan_id: str, plan: Json, view: Json, book_state: str,
              snapshot: fast.core.ContractSnapshot) -> Json:
        manifested = {task["custom_id"] for row in view["manifests"] for task in row["tasks"]}
        if not {task["custom_id"] for task in plan["canary_tasks"]} <= manifested:
            raise AuditError("throughput_canary_manifests_missing")
        number = 1 + max((row.get("wave_number", 0) for row in view["manifests"]), default=0)
        created = []
        for corpus in fast.CORPORA:
            binding, partition = plan["corpora"][corpus], plan["corpora"][corpus]["partition"]
            if time.time() >= self.deadline:
                break
            if corpus not in self.queues:
                self.ledger.append(session, "budget.throughput.frozen_queue.inspection.intended", {
                    "corpus_id": corpus, "queue_ref": binding["queue_ref"], "export_ref": binding["preparation_export_ref"]})
                queue = self.ledger.artifacts.read(binding["queue_ref"])
                export = self.ledger.artifacts.read(binding["preparation_export_ref"])
                if queue.get("corpus_id") != corpus or queue.get("manifest_sha256") != binding["manifest_sha256"]:
                    raise AuditError("throughput_queue_partition_changed")
                fast.choose_next(queue, set(), 1)  # Verify complete frozen order once.
                materialize.validate_preparation_binding(export["result"], export["manifest"], partition, snapshot)
                self.queues[corpus] = (queue, export)
            queue, export = self.queues[corpus]
            selected = select_prefix(queue["items"], export, manifested)
            if not selected:
                continue
            if fast.read_partition(Path(partition["resolved_root"]), corpus) != partition:
                raise AuditError("throughput_partition_changed_before_read")
            tasks = materialize_larger(self, session, export, selected, partition, snapshot)
            if [task["custom_id"] for task in tasks] != [item["custom_id"] for item in selected]:
                raise AuditError("throughput_materialized_prefix_changed")
            raw = b"".join(canonical(self.ledger.artifacts.read(task["request_ref"])).encode() + b"\n" for task in tasks)
            if len(raw) > MAX_NEW_BYTES or len(raw) >= fast.core.PROVIDER_BYTE_CEILING_EXCLUSIVE:
                raise AuditError("throughput_staged_file_too_large")
            if fast.read_partition(Path(partition["resolved_root"]), corpus) != partition:
                raise AuditError("throughput_partition_changed_after_read")
            reference = save(self, session, raw, "Exact larger separate-corpus full-text file before count/upload/create")
            value = {"plan": plan_id, "corpus_id": corpus, "phase": "bulk", "tasks": tasks,
                "jsonl_ref": reference, "attempt_ids": [str(uuid.uuid4()) for _ in tasks], "authorization_id": STUDY,
                "created_at": utc(), "wave_number": number, "protocol": self.execution_protocol,
                "throughput_method": METHOD, "throughput_run": self.fast_run, "budget_state_at_staging": book_state}
            identifier = self.ledger.record(session, fast.MANIFEST_KIND, f"{plan_id}:fill-first:{number}:{corpus}", value)
            manifested.update(task["custom_id"] for task in tasks)
            created.append({"manifest": identifier, "corpus_id": corpus, "requests": len(tasks), "bytes": len(raw)})
        if any(sha256(ROOT / name) != expected for name, expected in plan["implementation"].items()):
            raise AuditError("throughput_frozen_preparation_changed")
        return {"manifests": created, "new_requests_staged": sum(row["requests"] for row in created)}

    def report(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook, state: str,
               *, reason: str | None = None) -> Json:
        original = fast.FastResearch.report(self, session, plan_id, plan, view, book, state, reason=reason)
        value = {key: item for key, item in original.items() if key not in {"id", "presentation", "markdown"}}
        value.update(base_status_ref=original["id"], method=METHOD, policy_ref=self.verified.policy_ref,
            migration_ref=self.migration_ref,
            baseline_ack_ref=self.verified.value["baseline_ack_ref"], classification_ref=self.classification.get("classification_ref"),
            truncation_proof_record_ids=self.classification.get("proof_record_ids", []),
            qualifying_truncations=self.classification.get("qualifying_failures", 0),
            original_held_entry=book.entry(self.verified.baseline["held_failure"]["custom_id"]),
            max_new_requests=MAX_NEW_REQUESTS, max_new_bytes=MAX_NEW_BYTES, count_workers=COUNT_WORKERS,
            incremental_record_cursor=self.index.cursor, finish_ref=getattr(self, "finish_ref", None))
        return present(self, session, "luna_budget_throughput_status", value, original["markdown"] +
            f"\nThroughput policy {self.verified.policy_ref}; {value['qualifying_truncations']} independently proved settled truncations remain failed. "
            "The original unknown hold remains fully reserved. New files have at most 1000 requests/64 MB, separate corpora; existing files unchanged. "
            "Registered baseline cache, hash-checked incremental records, fill-first scheduling, original deadline, 16 counters and provisional 20M active tokens. "
            "Literal projections remain a separate retained-output step; no accepted events or paid retries.")

    def progress(self, view: Json, book: BudgetBook, *, reason: str | None = None) -> None:
        print(json.dumps({"phase": "progress", "run": self.fast_run, "migration_ref": self.migration_ref,
            "submitted_requests": sum(row["request_count"] for row in view["jobs"]),
            "assessed_requests": len(view["assessments"]),
            "pending_jobs": len({row["manifest"] for row in view["jobs"]} - view["reconciled"]),
            "active_input_tokens": fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
            "queue_token_cap": QUEUE_CAP, "charged_nanousd": book.charged_nanousd,
            "reserved_nanousd": book.reserved_nanousd, "reason": reason}), flush=True)

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() and not getattr(self.transport, "synthetic", False):
            raise AuditError("throughput_original_owner_required")
        if self.config.offline or data.get("allow_paid_execution") is not True:
            raise ResearchError("throughput_explicit_online_authorization_required")
        started = time.perf_counter()
        if hasattr(self, "startup_clock"):
            timing("runtime_preflight", self.startup_clock)
        plan_id, reference = data["plan"], data.get("policy_ref")
        if not reference:
            raise ResearchError("fill_existing_policy_ref_required")
        implementation = implementation_hashes()
        if data.get("migration_ref"):
            if data.get("handoff_ref") or data.get("handoff_workspace"):
                raise ResearchError("fill_migration_and_handoff_inputs_exclusive")
            migration = handoff.load_migration(self, session, plan_id, reference, data["migration_ref"], METHOD, implementation)
        else:
            if not data.get("handoff_ref") or not data.get("handoff_workspace"):
                raise ResearchError("fill_exact_migration_or_handoff_required")
            migration = handoff.register_migration(self, session, context, {**data,
                "successor_method": METHOD, "successor_implementation": implementation})
        self.migration_ref = migration["id"]
        print(json.dumps({"migration_ref": self.migration_ref, "policy_ref": reference}), flush=True)
        self.verified = handoff.load_registered_policy_cache(self, session, plan_id, reference)
        if migration["deadline_epoch"] != self.verified.value["deadline_epoch"]:
            raise AuditError("fill_migration_deadline_changed")
        timing("startup_policy_and_migration", started)
        self.plan = plan = self.ledger.get(plan_id, fast.PLAN_KIND)
        if plan.get("authorization_id") != STUDY or any(sha256(ROOT / name) != expected for name, expected in plan["implementation"].items()):
            raise AuditError("throughput_frozen_plan_changed")
        snapshot = fast.core.load_contract_snapshot()
        if snapshot.contract_sha256 != plan["contract_sha256"]:
            raise AuditError("throughput_frozen_contract_changed")
        self.deadline, self.queue_cap = self.verified.value["deadline_epoch"], QUEUE_CAP
        self.transport = AdmissionDeadlineTransport(self.transport, self.deadline)
        self.index, self.queues = IncrementalIndex(), {}
        self.classification = {}
        implementation = implementation_hashes()
        binding = {"plan": plan_id, "policy_ref": reference, "implementation": implementation, "migration_ref": self.migration_ref,
            "authorization_id": STUDY, "deadline_epoch": self.deadline, "queue_token_cap": QUEUE_CAP,
            "count_workers": COUNT_WORKERS, "max_new_requests": MAX_NEW_REQUESTS, "max_new_bytes": MAX_NEW_BYTES,
            "baseline_ack_ref": self.verified.value["baseline_ack_ref"]}
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":fill-first",
            "content": {"method": METHOD, **binding, "versions": plan["versions"], "account_capacity_verified": False,
                "rules": "One execute/full preflight and explicit registered policy cache bound to exact quiescent migration. Single ledger writer,16 exact counters. Incremental immutable record index and raw-derived failed truncation proofs. New same-corpus1000-request/64MB files preserve fulltext4096 request bytes and frozen order; existing manifests untouched. Existing gateway validates count/upload/create, complete file reserved before create. Real book/held/new technical/action/canary guards before provider writes. Fill staged files before polling up to the same queue/cost cap; force due reconciliation after eight submissions, drain launched counters on errors, no automatic retries. Original deadline also checked at actual transport create boundary. Only exact independently proved fully settled truncations are exempted; every other unknown/frozen/error/audit fault stops."},
            "amend_latest": True, "reason": "Explicit request for maximum throughput without weakening audit, cost or no-retry guarantees"})["id"]
        self.fast_protocol = self.execution_protocol = protocol
        self.result_parser, self.parser_mode = parse_batch_results_phase_aware, "explicit-final-answer-phase-v1"
        policy = DrainResearch.existing_policy(self, session, plan_id, plan)
        view, book, state = self.current(session, plan_id)
        key = plan_id + ":" + reference + ":fill-first-v1"
        old = self.latest(RUN_KIND, key)
        if old:
            self.fast_run, run = old
            if any(run.get(name) != item for name, item in binding.items()):
                raise AuditError("throughput_existing_run_binding_changed")
        else:
            self.fast_run = self.ledger.record(session, RUN_KIND, key, {**binding, "protocol": protocol, "started_at": utc()})
        finished = self.latest(FINISH_KIND, self.fast_run)
        if finished:
            self.finish_ref = finished[0]
            return self.report(session, plan_id, plan, view, book, state, reason=finished[1]["reason"])
        blockers = self.gate(session, plan_id, plan, view, book)
        reason = "technical_stop" if blockers else None
        startup = bool({job["manifest"] for job in view["jobs"]} - view["reconciled"])
        next_poll, backoff, pressure = 0.0, 30.0, None
        scheduler = FillFirstScheduler()
        print(self.report(session, plan_id, plan, view, book, state)["markdown"], flush=True)
        validated: dict[str, bytes] = {}
        while reason is None:
            if time.time() >= self.deadline:
                reason = "deadline"
                break
            pending = [job for job in view["jobs"] if job["manifest"] not in view["reconciled"]]
            submitted = {job["manifest"] for job in view["jobs"]}
            staged = [row for row in view["manifests"] if row["id"] not in submitted]
            unmanifested = plan["pending_requests"] - sum(len(row["tasks"]) for row in view["manifests"])
            if not pending and not staged and not unmanifested:
                reason = "complete"
                break
            if pressure and not pending:
                reason = fast.terminal_reason(pressure, 0)
                break
            selected = scheduler.choose(pending=bool(pending), staged=bool(staged), unmanifested=bool(unmanifested),
                startup=startup, pressure=pressure, poll_due=time.time() >= next_poll)
            try:
                if selected == "reconcile":
                    started = time.perf_counter()
                    observed = len(view["assessments"])
                    for job in pending:
                        self.reconcile(session, plan_id, policy, job)
                        view, book, state = self.current(session, plan_id)
                        blockers = self.gate(session, plan_id, plan, view, book)
                        if blockers:
                            reason = "technical_stop"
                            break
                    scheduler.reconciled()
                    startup, pressure = False, None
                    changed = len(view["assessments"]) != observed
                    backoff = 30.0 if changed else min(120.0, backoff * 2)
                    next_poll = time.time() + backoff
                    timing("reconciliation", started, jobs=len(pending), new_assessments=len(view["assessments"]) - observed)
                    if changed or reason:
                        self.progress(view, book, reason=reason)
                    continue
                if selected == "wait":
                    time.sleep(min(30.0, max(0.0, next_poll - time.time()), max(0.0, self.deadline - time.time())))
                    continue
                blockers = self.gate(session, plan_id, plan, view, book)
                if blockers:
                    reason = "technical_stop"
                    break
                if selected == "stage":
                    started = time.perf_counter()
                    result = self.stage(session, plan_id, plan, view, state, snapshot)
                    view, book, state = self.current(session, plan_id)
                    timing("stage", started, requests=result["new_requests_staged"])
                    if not result["manifests"]:
                        reason = "deadline" if time.time() >= self.deadline else "stalled"
                    continue
                started = time.perf_counter()
                manifest = staged[0]
                if manifest["id"] not in validated:
                    validated[manifest["id"]] = validate_large_manifest(self, session, plan_id, plan, manifest, snapshot)
                book, state, pressure, job = self.dispatch(session, plan_id, plan, policy, book, state, manifest, validated[manifest["id"]],
                    active_tokens=fast.active_input_tokens(book, view["manifests"], view["jobs"], view["reconciled"]),
                    queue_cap=QUEUE_CAP, workers=COUNT_WORKERS, deadline=self.deadline)
                view, book, state = self.current(session, plan_id)
                timing("dispatch_count_validate", started, requests=len(manifest["tasks"]), submitted=bool(job), pressure=pressure)
                if pressure == "deadline":
                    reason = "deadline"
                if job:
                    scheduler.submitted()
                    validated.pop(manifest["id"], None)
                    self.progress(view, book)
            except AuditError:
                raise
            except (ResearchError, BudgetError) as error:
                reason = "deadline" if (str(error) == "throughput_deadline_before_provider_write"
                    or self.transport.deadline_blocked) else "technical_stop"
                self.ledger.record(session, OBSTACLE_KIND, self.fast_run, {"plan": plan_id, "run": self.fast_run,
                    "reason": str(error), "operation": selected, "terminal_reason": reason, "observed_at": utc()})
                view, book, state = self.current(session, plan_id)
                blockers = [str(error)]
        self.finish_ref = self.ledger.record(session, FINISH_KIND, self.fast_run, {**binding, "run": self.fast_run,
            "reason": reason, "ended_at": utc(), "budget_state": state, "blockers": blockers,
            "classification_ref": self.classification.get("classification_ref"),
            "truncation_proof_record_ids": self.classification.get("proof_record_ids", [])})
        return self.report(session, plan_id, plan, view, book, state, reason=reason)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--policy-ref", required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--migration-ref")
    choice.add_argument("--handoff-ref")
    parser.add_argument("--handoff-workspace")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if not args.allow_paid_execution:
        parser.error("--allow-paid-execution is required")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({"starting_audited_throughput": args.plan, "count_workers": COUNT_WORKERS,
        "max_new_requests": MAX_NEW_REQUESTS, "provisional_queue_cap": QUEUE_CAP}), flush=True)
    engine = FillResearch(OWNER, config=Config(offline=False))
    engine.startup_clock = time.perf_counter()
    try:
        result = engine.execute("status", vars(args), objective="Maximize authorized Luna throughput with exact full costs held and failed settled truncations preserved", actor=fast.ACTOR)
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "run", "finish_ref", "policy_ref", "migration_ref", "finished_reason", "pending_jobs")}), flush=True)
        return 0 if result["finished_reason"] in {"complete", "budget_deferred", "deadline"} else 1
    finally:
        engine.close()


# The larger materializer below preserves the frozen source/hash/descriptor
# algorithm; only the separately registered size bound and audit labels differ.

def materialize_larger(engine: Any, session: str, export: Json, selected: list[Json],
                      partition: Json, snapshot: fast.core.ContractSnapshot) -> list[Json]:
    """Rebuild a bounded arbitrary frozen prefix without modifying old code."""
    if len(selected) > MAX_NEW_REQUESTS:
        raise ResearchError("budget_wave_selected_limit_exceeded")
    rows = [queued_row(export, item) for item in selected]
    engine.ledger.append(session, "budget.throughput.sources.inspection.intended", {
        "corpus_id": partition["corpus_id"], "row_ids": [row["id"] for row in rows],
        "request_count": len(rows), "contract_sha256": snapshot.contract_sha256,
        "full_text": True, "max_output_tokens": 4096})
    encoding = offline_tokenizer()
    grouped: dict[str, dict[int, Json]] = {}
    for row in rows:
        locator = row["source_locator"]
        wanted = grouped.setdefault(locator["archive_path"], {})
        if locator["line"] in wanted:
            raise AuditError("budget_wave_duplicate_source_locator")
        wanted[locator["line"]] = row
    tasks = {}
    for archive_path, wanted in grouped.items():
        bundle = next(item for item in partition["manifest"]["bundles"] if item["path"] == archive_path)
        path = within(Path(partition["resolved_root"]), archive_path)
        if sha256(path) != bundle["sha256"]:
            raise AuditError("budget_wave_archive_precheck_changed")
        engine.ledger.append(session, "budget.throughput.archive.inspection.intended", {
            "archive_path": archive_path, "archive_sha256": bundle["sha256"], "lines": sorted(wanted)})
        seen = set()
        with zipfile.ZipFile(path) as archive:
            if archive.namelist().count("artikelen.jsonl") != 1:
                raise AuditError("budget_wave_article_stream_invalid")
            with archive.open("artikelen.jsonl") as stream:
                for number, raw in enumerate(stream, 1):
                    if number not in wanted:
                        continue
                    row = wanted[number]
                    record = materialize.materialize_descriptor(row["descriptor"], raw, partition=partition,
                        contract_snapshot=snapshot,
                        count_tokens=lambda text: len(encoding.encode(text, disallowed_special=())))
                    body_ref = save(engine, session, record["request"]["body"], "Exact throughput Responses request body")
                    if body_ref != row["descriptor"]["request_body_sha256"]:
                        raise AuditError("budget_wave_body_artifact_mismatch")
                    request_ref = save(engine, session, record["request"], "Exact throughput Batch request record")
                    packet_ref = save(engine, session, record["packet"], "Exact throughput full-text source map")
                    article = json.loads(raw)["article"]
                    tasks[row["id"]] = {"row_id": row["id"], "corpus_id": partition["corpus_id"],
                        "custom_id": row["descriptor"]["custom_id"], "request_body_ref": body_ref,
                        "request_ref": request_ref, "packet_ref": packet_ref,
                        "title": article.get("title"), "url": article.get("url"), "descriptor": row["descriptor"]}
                    seen.add(number)
        if seen != set(wanted) or sha256(path) != bundle["sha256"]:
            raise AuditError("budget_wave_archive_postcheck_or_coverage_changed")
        engine.ledger.append(session, "budget.throughput.archive.inspection.completed", {
            "archive_path": archive_path, "archive_sha256": bundle["sha256"], "lines": sorted(seen)})
    return [tasks[row["id"]] for row in rows]



if __name__ == "__main__":
    raise SystemExit(main())
