"""Versioned, same-budget API Batch handoff of the drained Codex remainder.

All provider operations use Research.execute and the shared audited LeanGateway.
The old Batch owner/state/deadline and the stopped Codex owner remain unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_batch as batch
import lean_luna_runtime as lean
import lean_luna_state as state
from review_luna_batch_remainder import select_remaining

METHOD = "luna-batch-remainder-20261019-v1"
AUTHORIZATION = "Approve, stop luna codex start batch. Ensure max parralel and check and or autofox 15 minute cycle."
PLAN = "luna_batch_remainder_plan"
CHECKPOINT = "luna_batch_remainder_checkpoint"
QUEUE_TOKENS = 20_000_000
canonical, digest = state.canonical, state.digest


def implementation():
    root = Path(__file__).resolve().parents[1]
    paths = [Path(__file__), Path(batch.__file__), Path(lean.__file__), Path(state.__file__),
        root / "scripts/review_luna_batch_remainder.py", root / "scripts/luna_batch_materialize.py",
        root / "scripts/luna_multibatch.py", root / "scripts/luna_event_contract_v2.py",
        root / "scripts/luna_batch_phase_projection.py", root / "scripts/luna_batch_results.py",
        root / "src/newsresearch/event_batch_transport.py"]
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + ".writing")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def state_hash(connection):
    return hashlib.sha256(connection.serialize()).hexdigest()


def verify_codex_seal(plan):
    owner = Path(plan["codex_owner"])
    if not (owner / "STOP").is_file():
        raise AuditError("batch_handoff_codex_stop_missing")
    connection = state.read_only_database(owner)
    try:
        head = connection.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        if list(head) != plan["codex_head"]:
            raise AuditError("batch_handoff_codex_head_changed")
    finally:
        connection.close()


class RemainderGateway(lean.LeanGateway):
    def retain_manifest(self, manifest):
        assert self.runner is not None
        if manifest.get("remainder_plan") != self.baseline:
            raise AuditError("batch_manifest_outside_remainder_plan")
        for task in manifest["tasks"]:
            if self.runner.allowed.get(task["custom_id"]) != task["descriptor"]:
                raise AuditError("batch_manifest_outside_untouched_selection")
        return super().retain_manifest(manifest)


class RemainderBatch(batch.LeanBatch):
    def __init__(self, database, *, plan, plan_id, engine, **kwargs):
        self.plan, self.plan_id, self.engine = plan, plan_id, engine
        self.queues = {k: engine.ledger.artifacts.read(ref) for k, ref in plan["queues"].items()}
        self.allowed = {d["custom_id"]: d for rows in self.queues.values() for d in rows}
        self.last_progress, self.last_poll = 0.0, 0.0
        super().__init__(database, **kwargs)
        try:
            self.locks.enter_context(state.StateLock(Path(plan["codex_owner"]) / "workspace"))
            self.locks.enter_context(state.StateLock(Path(plan["parent_state"])))
            verify_codex_seal(plan)
            if (self.meta["deadline_epoch"] != plan["deadline_epoch"]
                    or self.meta["handoff_plan"] != plan_id or len(self.allowed) != plan["count_cap"]):
                raise AuditError("batch_handoff_state_binding_changed")
        except BaseException:
            self.close()
            raise

    def preparations(self):
        known = {r[0] for r in self.db.execute("SELECT custom_id FROM requests")}
        remaining = {k: [d for d in rows if d["custom_id"] not in known] for k, rows in self.queues.items()}
        offsets = {k: 0 for k in remaining}
        while any(offsets[k] < len(v) for k, v in remaining.items()):
            for corpus, rows in remaining.items():
                selected, size = [], 0
                while offsets[corpus] < len(rows) and len(selected) < batch.MAX_REQUESTS:
                    descriptor = rows[offsets[corpus]]
                    if selected and size + descriptor["line_bytes"] > batch.MAX_BYTES:
                        break
                    selected.append(descriptor)
                    offsets[corpus] += 1
                    size += descriptor["line_bytes"]
                if selected:
                    partition = self.meta["corpora"][corpus]["partition"]
                    yield corpus, self.materialize(selected, partition)

    def log_next(self):
        self.require_runtime()
        row = self.db.execute("""SELECT m.payload FROM manifests m WHERE json_extract(m.payload,'$.remainder_plan')=?
            AND EXISTS(SELECT 1 FROM requests r WHERE r.manifest_id=m.id AND r.status='logged') ORDER BY m.rowid LIMIT 1""", (self.plan_id,)).fetchone()
        if row:
            return json.loads(row[0])
        selected = next(self.preparation, None)
        if selected is None:
            return None
        manifest = {**batch.prompt_file(self.database.parent, *selected, self.snapshot), "remainder_plan": self.plan_id}
        with batch.transaction(self.db):
            for task in manifest["tasks"]:
                if self.allowed.get(task["custom_id"]) != task["descriptor"]:
                    raise AuditError("batch_preparation_selection_changed")
                value = {**task, "manifest_id": manifest["id"], "submitted": False}
                self.db.execute("INSERT INTO requests VALUES(?,?,?,0,'logged',?)", (task["custom_id"], task["corpus_id"], manifest["id"], canonical(value)))
            self.db.execute("INSERT INTO manifests VALUES(?,?,?)", (manifest["id"], manifest["corpus_id"], canonical(manifest)))
        print(canonical({"phase": "prompt_log", "corpus": manifest["corpus_id"], "requests": len(manifest["tasks"]), "bytes": manifest["bytes"]}), flush=True)
        return manifest

    def admission_checks(self):
        super().admission_checks()
        if (self.database.parent / "STOP").exists():
            raise state.StateError("user_stop")

    def settle(self, job_id, items):
        super().settle(job_id, items)
        job = json.loads(self.db.execute("SELECT payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()[0])
        saved = [json.loads(self.db.execute("SELECT payload FROM results WHERE custom_id=?", (custom,)).fetchone()[0]) for custom in job["request_ids"]]
        costs = [json.loads(self.db.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()[0]) for custom in job["request_ids"]]
        files = {}
        for field in ("output_file_id", "error_file_id"):
            path = self.database.parent / "results" / (job_id + "-" + field + ".jsonl")
            files[field] = self.engine.ledger.artifacts.put_bytes(path.read_bytes()) if path.exists() else None
        self.engine.ledger.record(self.gateway.session, "luna_batch_remainder_file_result", job_id, {
            "plan": self.plan_id, "job_id": job_id, "manifest_id": job["manifest_id"], "corpus_id": job["corpus_id"],
            "results_ref": self.engine.ledger.artifacts.put(saved), "costs_ref": self.engine.ledger.artifacts.put(costs),
            "raw_files": files, "returned": len(saved), "raw_counts": dict(Counter(item["status"] for item in saved)),
            "saved_at": utc(), "semantic_accuracy_confirmed": False})

    def summary(self):
        result = super().summary()
        counts = {k: {"total": len(v), "submitted": 0, "returned": 0, "raw_counts": {}} for k, v in self.queues.items()}
        rows = self.db.execute("""SELECT r.custom_id,r.corpus_id,r.submitted,v.status FROM requests r
            JOIN manifests m ON m.id=r.manifest_id LEFT JOIN results v USING(custom_id)
            WHERE json_extract(m.payload,'$.remainder_plan')=?""", (self.plan_id,))
        raw = {k: Counter() for k in counts}
        for row in rows:
            value = counts[row["corpus_id"]]
            value["submitted"] += bool(row["submitted"])
            if row["status"] is not None:
                value["returned"] += 1
                raw[row["corpus_id"]][row["status"]] += 1
        for corpus, value in counts.items():
            value["raw_counts"] = dict(raw[corpus])
            value["unsubmitted"] = value["total"] - value["submitted"]
            value["pending"] = value["submitted"] - value["returned"]
        result.update(corpora=counts, new_submitted=sum(v["submitted"] for v in counts.values()),
            new_returned=sum(v["returned"] for v in counts.values()),
            unknown_cost_holds=self.db.execute("SELECT COUNT(*) FROM budget_entries WHERE status='unknown'").fetchone()[0])
        return result

    def checkpoint(self, session, label):
        value = {"plan": self.plan_id, "state_sha256": state_hash(self.db), "label": label,
            "checked_at": utc(), "summary": self.summary()}
        reference = self.engine.ledger.record(session, CHECKPOINT, self.plan_id, value)
        self.progress(label, checkpoint=reference, force=True)
        return reference

    def progress(self, status, *, checkpoint=None, force=False):
        if not force and self.clock() - self.last_progress < 15:
            return
        self.last_progress = self.clock()
        value = {"plan": self.plan_id, "pid": os.getpid(), "updated_at": utc(), "state": status,
            "deadline_epoch": self.plan["deadline_epoch"], "deadline": self.plan["deadline"],
            "queue_token_limit": QUEUE_TOKENS, "queue_limit_basis": self.plan["queue_limit_basis"],
            "count_workers": batch.COUNT_WORKERS, "transfer_workers": batch.TRANSFER_WORKERS,
            "prior_codex_spent": self.plan["prior_codex_spent"], "semantic_accuracy_confirmed": False,
            **self.summary()}
        if checkpoint:
            value["checkpoint"] = checkpoint
        atomic_json(self.database.parent / "progress.json", value)
        print(canonical(value), flush=True)

    def run_remainder(self, session, *, collect_only=False, stop_after_submissions=None):
        self.require_runtime()
        self.allow_network = True
        if not collect_only:
            self.admission_checks()
            if self.db.execute("SELECT 1 FROM actions WHERE phase IN ('upload','create') AND status!='complete' LIMIT 1").fetchone():
                raise state.StateError("prior_remote_write_requires_reconciliation")
            if self.db.execute("SELECT 1 FROM requests WHERE status IN ('admitted','creating','unknown_create') LIMIT 1").fetchone():
                raise state.StateError("prior_admission_requires_reconciliation")
        waiting, admitted, next_poll = None, 0, 0.0
        admission_open = not collect_only
        with ThreadPoolExecutor(max_workers=batch.TRANSFER_WORKERS) as pool:
            def tick():
                self.pump(pool)
                self.progress("running")
            try:
                while True:
                    self.pump(pool)
                    if (self.database.parent / "STOP").exists():
                        self.stop_reason = "user_stop"
                        break
                    if self.clock() >= next_poll:
                        completed = self.collect()
                        next_poll = self.clock() + 30
                        if completed:
                            self.checkpoint(session, "results_saved")
                    if self.stop_reason:
                        break
                    if self.clock() >= self.meta["deadline_epoch"]:
                        admission_open = False
                    if len(self.remote) >= batch.TRANSFER_WORKERS:
                        self.progress("uploading")
                        time.sleep(0.1)
                        continue
                    pressure = "empty"
                    if admission_open:
                        if waiting is None:
                            waiting = self.log_next()
                            if waiting is not None:
                                self.progress("counting", force=True)
                                self.count_file(waiting, tick)
                                self.checkpoint(session, "counted")
                        if self.stop_reason:
                            break
                        pressure = self.reserve(waiting) if waiting is not None else "empty"
                        if pressure is None:
                            raw = self.raw(waiting)
                            self.start_remote(pool, "upload", waiting, {"method": "POST", "path": "/v1/files", "purpose": "batch",
                                "filename": waiting["id"] + ".jsonl", "content_sha256": waiting["sha256"]}, raw)
                            waiting = None
                            admitted += 1
                            if stop_after_submissions is not None and admitted >= stop_after_submissions:
                                break
                            continue
                        if pressure == "deadline":
                            admission_open = False
                    pending = self.db.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone()
                    if not pending and not self.remote:
                        self.stop_reason = "queue_exhausted" if admission_open and pressure == "empty" else "deadline" if not admission_open else pressure + "_deferred"
                        break
                    self.progress("waiting_for_capacity" if admission_open and pressure == "queue" else "collecting")
                    time.sleep(0.2)
            except Exception as error:
                self.stop_reason = self.stop_reason or (str(error) if isinstance(error, (state.StateError, AuditError)) else type(error).__name__)
                raise
            finally:
                while self.remote:
                    self.pump(pool)
                    if self.remote:
                        time.sleep(0.05)
                self.checkpoint(session, self.stop_reason or "submitted")
        return {"reason": self.stop_reason or "submitted", **self.summary()}


class RemainderResearch(Research):
    def __init__(self, workspace, *, transport=None, clock=time.time, config=None):
        super().__init__(workspace, config=config or Config(offline=True))
        self.transport, self.clock = transport, clock
        self.gateway = RemainderGateway(self)

    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "prepare":
            return self.prepare_handoff(session, context, data)
        return self.execute_handoff(session, context, data)

    def prepare_handoff(self, session, context, data):
        existing = lean.latest(self, PLAN, METHOD)
        if existing:
            raise AuditError("batch_handoff_already_prepared_reuse_plan")
        if data.get("authorization_text") != AUTHORIZATION:
            raise AuditError("batch_handoff_explicit_approval_required")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": implementation(),
            "procedure": "Drain and seal the Codex owner. Preserve all original Batch charges, reservations, unknown liabilities and identities in a checkpoint-bound child. Select only the frozen Codex queue minus every prior lineage intent; separate corpora. Renew the admission window for 24 hours under the same USD150 hard cap and USD120 operating limit. Keep original deadline in provenance. Audited exact provider counts precede full cost reservations, uploads and one-shot Batch creates. Fill available queued-token capacity with concurrent jobs; reconcile results and refill. No per-job serial wait, article retry, changed prompt, lowered validation or accepted findings.",
            "limits": "Queue token limit is initially the published Build-tier 20M and historical provisional ceiling; actual project maximum is not verified. No claim of maximizing an unknown account limit. New unknown writes/costs or integrity mismatch stop admission. Read-only job reconciliation may continue after deadline."}})["id"]
        codex = Path(data["codex_owner"]).resolve()
        parent_state = Path(data["parent_state"]).resolve()
        if not (codex / "STOP").is_file():
            raise AuditError("batch_handoff_codex_stop_required")
        progress = json.loads((codex / "progress.json").read_text())
        integrity = json.loads(Path(data["integrity_report"]).read_text())
        if progress["state"] != "user_stop" or progress["in_flight"] != 0 or not integrity["integrity_passed"]:
            raise AuditError("batch_handoff_requires_drained_verified_codex")
        check_permissions(codex, root=True)
        check_permissions(parent_state.parent, root=True)
        with ExitStack() as locks:
            locks.enter_context(state.StateLock(codex / "workspace"))
            locks.enter_context(state.StateLock(parent_state))
            source = state.read_only_database(codex)
            legacy = sqlite3.connect(parent_state.as_uri() + "?mode=ro", uri=True)
            legacy.row_factory = sqlite3.Row
            legacy.execute("PRAGMA query_only=ON")
            legacy.execute("BEGIN")
            parent_runtime = state.read_only_database(parent_state.parent / "runtime")
            locks.callback(source.close)
            locks.callback(legacy.close)
            locks.callback(parent_runtime.close)
            row = source.execute("SELECT * FROM records WHERE id=?", (data["codex_plan"],)).fetchone()
            source_plan = state.row_value(row, "luna_standard_plan")
            artifacts = state.SelectedArtifacts(codex)
            artifacts.check(row["artifact"])
            head = list(source.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            if (head != [integrity["head_seq"], integrity["head_hash"]] or integrity["plan"] != data["codex_plan"]
                    or self.clock() - datetime.fromisoformat(integrity["checked_at"]).timestamp() > 3600):
                raise AuditError("batch_handoff_integrity_not_at_drained_head")
            lineage = {data["codex_plan"], *source_plan.get("capacity_lineage", [])}
            intents = [v["custom_id"] for r in source.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'")
                if (v := json.loads(r[0])).get("plan") in lineage]
            queues = {k: artifacts.json(ref) for k, ref in source_plan["queues"].items()}
            meta = {r["key"]: json.loads(r["value"]) for r in legacy.execute("SELECT * FROM meta")}
            locks.enter_context(state.StateLock(Path(meta["source_owner"]) / "workspace"))
            row = parent_runtime.execute("SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (meta["snapshot_id"],)).fetchone()
            checkpoint = state.row_value(row, "lean_luna_checkpoint")
            state.SelectedArtifacts(parent_state.parent / "runtime").check(row["artifact"])
            if state_hash(legacy) != checkpoint["state_sha256"] or meta["blockers"] or meta["budget"]["frozen"]:
                raise AuditError("batch_handoff_parent_state_changed_or_blocked")
            old_ids = {r[0] for r in legacy.execute("SELECT custom_id FROM requests UNION SELECT custom_id FROM budget_entries")}
            remaining = select_remaining(queues, intents, old_ids)
            if sum(map(len, queues.values())) != source_plan["max_attempts"] or len(intents) != progress["reserved"]:
                raise AuditError("batch_handoff_source_coverage_changed")
            if legacy.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone():
                raise AuditError("batch_handoff_old_jobs_not_settled")
            queue_refs = {k: self.ledger.artifacts.put(v) for k, v in remaining.items()}
            contract = batch.core.load_contract_snapshot()
            versions = {"protocol": protocol}
            for kind, content in {
                "selection": {"rules": "The drained frozen Codex queues minus every prior lineage intent; no prior Batch reserved identities; preserve corpus and SHA order.", "queues": queue_refs, "codex_head": head},
                "prompt": {"instructions": contract.prompt, "details_schema": json.loads(contract.schema_json)},
                "question": {"text": "Extract provisional single-focus event mentions from complete retained articles."},
                "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
                "dossier_definition": {"unit": "A real-world event across reports; this article extraction creates no accepted dossiers."},
            }.items():
                versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
            deadline = self.clock() + 24 * 3600
            value = {"method": METHOD, "protocol": protocol, "versions": versions, "implementation": implementation(), "authorization_text": AUTHORIZATION,
                "codex_owner": str(codex), "codex_plan": data["codex_plan"], "codex_head": head,
                "integrity_report": integrity, "prior_codex_spent": len(intents), "queues": queue_refs,
                "corpus_counts": {k: len(v) for k, v in remaining.items()}, "count_cap": sum(map(len, remaining.values())),
                "parent_state": str(parent_state), "parent_state_sha256": checkpoint["state_sha256"],
                "parent_checkpoint": row["id"], "parent_baseline": checkpoint["baseline"],
                "authorization_id": meta["authorization_id"], "original_batch_plan": meta["plan_id"],
                "original_deadline_epoch": meta["deadline_epoch"], "initial_totals": checkpoint["totals"],
                "budget_config": meta["budget"]["config"], "imported_unknown_entry_hashes": meta["imported_unknown_entry_hashes"],
                "started_at": utc(), "deadline_epoch": deadline,
                "deadline": datetime.fromtimestamp(deadline, timezone.utc).isoformat(),
                "queue_token_limit": QUEUE_TOKENS,
                "queue_limit_basis": "Published GPT-6 Luna Build-tier 20M queued tokens; actual project maximum unverified. Fill capacity without an additional job-count cap.",
                "retries": 0, "hard_cap_usd": 150, "operating_cap_usd": 120, "human_validated": False}
            policy = self._version(session, context, {"kind": "policy", "key": METHOD, "content": {
                "instruction": AUTHORIZATION, "prior_approval": "New 24-hour Batch submission window under the same USD150 total cap",
                "scope_sha256": digest(value), "approved_by": "user:current-chat", "new_budget": False,
                "original_deadline_preserved_as_history": True, "deadline_epoch": deadline,
                "allow_paid_execution": True, "no_article_retries": True}})["id"]
            value["policy"] = policy
            identifier = self.ledger.record(session, PLAN, METHOD, value)
            destination = self.ledger.root / "state.sqlite3"
            if destination.exists():
                raise AuditError("batch_handoff_child_state_already_exists")
            child = sqlite3.connect(destination)
            try:
                legacy.backup(child)
                child.execute("UPDATE meta SET value=? WHERE key='deadline_epoch'", (canonical(deadline),))
                for key, item in {"handoff_plan": identifier, "original_deadline_epoch": meta["deadline_epoch"], "parent_state_sha256": checkpoint["state_sha256"]}.items():
                    child.execute("INSERT INTO meta VALUES(?,?)", (key, canonical(item)))
                child.commit()
                ref = self.ledger.record(session, CHECKPOINT, identifier, {"plan": identifier, "state_sha256": state_hash(child),
                    "label": "inherited", "checked_at": utc(), "parent_state_sha256": checkpoint["state_sha256"], "summary": checkpoint["summary"]})
            finally:
                child.close()
        result = {"id": identifier, **value, "checkpoint": ref, "http_calls": 0}
        atomic_json(self.ledger.root / "plan.json", result)
        return result

    def execute_handoff(self, session, context, data):
        plan = self.ledger.get(data["plan"], PLAN)
        if plan["implementation"] != implementation() or plan["authorization_text"] != AUTHORIZATION:
            raise AuditError("batch_handoff_implementation_or_authorization_changed")
        policy = self.ledger.get(plan["policy"], "policy")["content"]
        if (policy["instruction"] != AUTHORIZATION or policy["scope_sha256"] != digest({k: v for k, v in plan.items() if k != "policy"})
                or policy["deadline_epoch"] != plan["deadline_epoch"]):
            raise AuditError("batch_handoff_permission_binding_changed")
        if self.config.offline and getattr(self.transport, "synthetic", False) is not True:
            raise AuditError("batch_handoff_online_mode_required")
        checkpoint = lean.latest(self, CHECKPOINT, data["plan"])
        gateway = RemainderGateway(self)
        self.gateway = gateway
        runner = RemainderBatch(self.ledger.root / "state.sqlite3", plan=plan, plan_id=data["plan"], engine=self,
            gateway=gateway, transport=self.transport, clock=self.clock)
        try:
            if checkpoint is None or state_hash(runner.db) != checkpoint[1]["state_sha256"]:
                raise AuditError("batch_handoff_state_requires_receipt_reconciliation")
            gateway.bind(session, runner, data["plan"], plan["protocol"], network=True)
            gateway.imported_counts = {r["custom_id"]: json.loads(r["payload"]) for r in runner.db.execute("SELECT * FROM counts")}
            print(canonical({"phase": "execution_started", "pid": os.getpid(), "plan": data["plan"], "at": utc()}), flush=True)
            result = runner.run_remainder(session, collect_only=data.get("collect_only", False), stop_after_submissions=data.get("test_stop_after_submissions"))
            result.update(plan=data["plan"], http_calls=gateway.http_calls, semantic_accuracy_confirmed=False, record_presentation_supported=False)
            reference = self.ledger.record(session, "luna_batch_remainder_result", data["plan"], result)
            return {"id": reference, **result}
        finally:
            gateway.network = False
            gateway.session = None
            runner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "run", "collect"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--codex-owner", type=Path)
    parser.add_argument("--codex-plan")
    parser.add_argument("--parent-state", type=Path)
    parser.add_argument("--integrity-report", type=Path)
    parser.add_argument("--plan")
    parser.add_argument("--authorization-text")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if args.phase != "prepare" and (not args.allow_paid_execution or not args.plan):
        parser.error("run/collect requires the exact plan and --allow-paid-execution")
    if args.phase == "prepare" and not all((args.codex_owner, args.codex_plan, args.parent_state, args.integrity_report, args.authorization_text)):
        parser.error("prepare requires source bindings and the exact authorization")
    print(canonical({"phase": "startup_preflight", "pid": os.getpid(), "workspace": str(args.workspace), "at": utc()}), flush=True)
    engine = RemainderResearch(args.workspace, config=Config(offline=args.phase == "prepare"))
    try:
        data = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        data["collect_only"] = args.phase == "collect"
        result = engine.execute("status", data, objective="Execute the user-approved same-budget Batch handoff of untouched articles from both corpora",
            actor="codex:luna-batch-remainder")
        print(canonical(result), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
