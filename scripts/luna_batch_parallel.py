"""Versioned scheduling amendment: fit spare queue capacity and reuse checks.

Full-text, model, validation, budget, deadline, identities and no-retry rules
remain those of the original remainder plan. Old owners remain sealed.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root, check_permissions

import luna_batch_remainder as parent

METHOD = "luna-batch-capacity-packing-v1"
AMENDMENT = "luna_batch_parallel_amendment"
AUTHORIZATION = "Cant you do more parallel maximize"
canonical, digest = parent.canonical, parent.digest


def implementation():
    return {**parent.implementation(), "scripts/luna_batch_parallel.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def require(value, code):
    if not value:
        raise AuditError("batch_parallel_" + code)


def verify_parent_seal(amendment):
    owner = Path(amendment["parent_owner"])
    require((owner / "STOP").is_file(), "parent_stop_missing")
    conn = parent.state.read_only_database(owner)
    try:
        head = list(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
        require(head == amendment["parent_head"], "parent_head_changed")
    finally:
        conn.close()


class PackingGateway(parent.RemainderGateway):
    def prepare_many(self, actions, manifest=None):
        # The one writer cannot change operational state while this synchronous
        # method prepares a bundle. Reuse only unchanged-state admission checks.
        self.runner.admission_bundle = True
        self.runner.admission_snapshot = None
        try:
            return super().prepare_many(actions, manifest=manifest)
        finally:
            self.runner.admission_bundle = False
            self.runner.admission_snapshot = None


class PackingBatch(parent.RemainderBatch):
    def __init__(self, *args, amendment, **kwargs):
        self.amendment = amendment
        self.admission_bundle = False
        self.admission_snapshot = None
        self.queue_wait_snapshot = None
        super().__init__(*args, **kwargs)
        self.db.execute("PRAGMA busy_timeout=15000")
        try:
            self.locks.enter_context(parent.state.StateLock(Path(amendment["parent_owner"]) / "workspace"))
            self.locks.enter_context(parent.state.StateLock(Path(amendment["parent_owner"]) / "state.sqlite3"))
            verify_parent_seal(amendment)
        except BaseException:
            self.close()
            raise

    def state_generation(self):
        return (self.db.total_changes, self.db.execute("PRAGMA data_version").fetchone()[0])

    def admission_checks(self):
        if (self.database.parent / "STOP").exists():
            raise parent.state.StateError("user_stop")
        generation = self.state_generation()
        if self.admission_bundle and self.admission_snapshot == generation:
            return
        super().admission_checks()
        if self.admission_bundle:
            self.admission_snapshot = generation

    def split_to_fit(self, manifest):
        available = parent.QUEUE_TOKENS - self.queued_tokens()
        budget = parent.state.OPERATING_CAP - self.totals()["committed_nanousd"]
        take, tokens, amount = 0, 0, 0
        for task in manifest["tasks"]:
            row = self.db.execute("SELECT r.submitted,r.status,c.input_tokens,c.payload FROM requests r JOIN counts c USING(custom_id) WHERE r.custom_id=?", (task["custom_id"],)).fetchone()
            require(row is not None and not row[0] and row[1] == "logged", "split_requires_unsubmitted")
            evidence = json.loads(row[3])
            require(evidence["request_body_ref"] == task["request_body_ref"] and evidence["input_tokens"] == row[2], "split_count_binding")
            cost = parent.state.cost(self.price, row[2], 4096)
            if tokens + row[2] > available or amount + cost > budget:
                break
            take += 1
            tokens += row[2]
            amount += cost
        if take == 0 or take == len(manifest["tasks"]):
            return False
        require(not self.db.execute("SELECT 1 FROM actions WHERE phase IN ('upload','create') AND json_extract(request_json,'$.manifest_id')=?", (manifest["id"],)).fetchone(), "split_prior_remote_write")
        raw = self.raw(manifest)
        lines = raw.splitlines(keepends=True)
        require(len(lines) == len(manifest["tasks"]), "split_line_coverage")
        parts = []
        for start, stop in ((0, take), (take, len(lines))):
            content = b"".join(lines[start:stop])
            identifier = hashlib.sha256(content).hexdigest()
            path = self.database.parent / "prompts" / manifest["corpus_id"] / (identifier + ".jsonl")
            parent.batch.write_once(path, content)
            tasks = manifest["tasks"][start:stop]
            parts.append({**manifest, "id": identifier, "sha256": identifier, "prompt_path": str(path),
                "bytes": len(content), "tasks": tasks, "request_ids": [t["custom_id"] for t in tasks],
                "split_parent": manifest["id"]})
        self.engine.ledger.record(self.gateway.session, "luna_batch_manifest_split", manifest["id"], {
            "method": METHOD, "plan": self.plan_id, "original_manifest": manifest["id"],
            "original_jsonl": self.engine.ledger.artifacts.put_bytes(raw),
            "parts": [{"manifest": p["id"], "request_ids": p["request_ids"], "jsonl": self.engine.ledger.artifacts.put_bytes(b"".join(lines[:take] if i == 0 else lines[take:]))} for i, p in enumerate(parts)],
            "reason": "Fill available queue tokens with already-counted, never-submitted identities", "at": utc()})
        with parent.batch.transaction(self.db):
            for part in parts:
                self.db.execute("INSERT INTO manifests VALUES(?,?,?)", (part["id"], part["corpus_id"], canonical(part)))
                for task in part["tasks"]:
                    old = json.loads(self.db.execute("SELECT payload FROM requests WHERE custom_id=?", (task["custom_id"],)).fetchone()[0])
                    self.db.execute("UPDATE requests SET manifest_id=?,payload=? WHERE custom_id=? AND status='logged' AND submitted=0",
                        (part["id"], canonical({**old, "manifest_id": part["id"]}), task["custom_id"]))
        original = manifest["id"]
        manifest.clear()
        manifest.update(parts[0])
        self.checkpoint(self.gateway.session, "queue_capacity_split")
        print(canonical({"phase": "queue_capacity_split", "original_manifest": original,
            "admit_requests": take, "deferred_requests": len(parts[1]["tasks"]), "input_tokens": tokens,
            "queue_space_before": available}), flush=True)
        return True

    def reserve(self, manifest):
        if manifest is None:
            return "empty"
        # Polling and settlement change the generation, so capacity is rechecked
        # as soon as anything changes. STOP and deadline remain live on each tick.
        if (self.database.parent / "STOP").exists():
            raise parent.state.StateError("user_stop")
        if self.clock() >= self.meta["deadline_epoch"]:
            return "deadline"
        generation = (manifest["id"], self.state_generation())
        if self.queue_wait_snapshot == generation:
            return "queue"
        result = super().reserve(manifest)
        if result == "queue" and self.split_to_fit(manifest):
            result = super().reserve(manifest)
        self.queue_wait_snapshot = (manifest["id"], self.state_generation()) if result == "queue" else None
        return result


class MigrationResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        source, destination = Path(data["source_owner"]).resolve(), Path(data["destination"]).resolve()
        require(data["authorization_text"] == AUTHORIZATION, "explicit_permission_required")
        require(not destination.exists() and source != self.ledger.root and destination != self.ledger.root, "destination_must_be_new")
        check_permissions(source, root=True)
        require((source / "STOP").exists(), "parent_must_be_stopped")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": implementation(),
            "procedure": "Seal and preserve the previous Batch owner, copy its small complete journal and artifacts plus exact operational checkpoint into a new protected child, explicitly authorize continuation under unchanged selection, budget and deadline. Enable WAL in the child after checkpoint verification so offline readers cannot block operational commits. Split only counted, never-uploaded/submitted manifest prefixes to fill spare queue capacity. Reuse admission checks only inside a synchronous one-writer permit bundle while SQLite change/data-version counters are unchanged; STOP checked every call. No article/count/remote-write retries or validation changes.",
            "limits": "Conservative 20M input-token queue ceiling remains unchanged. Scheduling improvements are not an increase in provider quota or a semantic accuracy claim."}})["id"]
        with ExitStack() as locks:
            locks.enter_context(parent.state.StateLock(source / "workspace"))
            locks.enter_context(parent.state.StateLock(source / "state.sqlite3"))
            journal = parent.state.read_only_database(source)
            database = sqlite3.connect((source / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
            locks.callback(journal.close)
            locks.callback(database.close)
            head = list(journal.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            checkpoint_row = journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (parent.CHECKPOINT,)).fetchone()
            checkpoint = parent.state.row_value(checkpoint_row, parent.CHECKPOINT)
            require(parent.state_hash(database) == checkpoint["state_sha256"], "parent_checkpoint_mismatch")
            report = json.loads(Path(data["integrity_report"]).read_text())
            require(report["integrity_passed"] and [report["head_seq"], report["head_hash"]] == head, "integrity_not_at_sealed_head")
            plan = parent.state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone(), parent.PLAN)
            require(plan["implementation"] == parent.implementation(), "parent_implementation_changed")
            require(not database.execute("SELECT 1 FROM actions WHERE status!='complete' LIMIT 1").fetchone(), "unresolved_parent_action")
            require(not database.execute("SELECT 1 FROM requests WHERE status IN ('admitted','creating','unknown_create') LIMIT 1").fetchone(), "unresolved_parent_admission")
            prepare_root(destination)
            (destination / "objects").mkdir()
            for name, connection in (("research.sqlite3", journal),):
                copied = sqlite3.connect(destination / name)
                try:
                    connection.backup(copied)
                finally:
                    copied.close()
            # SQLite backup rewrites database-header counters. Preserve the
            # checkpoint's exact serialized state bytes under the source lock.
            with (destination / "state.sqlite3").open("xb") as stream:
                stream.write(database.serialize())
                stream.flush()
                os.fsync(stream.fileno())
            for item in (source / "objects").iterdir():
                require(item.is_file() and len(item.name) == 64, "unexpected_parent_artifact")
                target = destination / "objects" / item.name
                with item.open("rb") as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                with target.open("rb") as stream:
                    require(hashlib.file_digest(stream, "sha256").hexdigest() == item.name, "copied_artifact_hash")
            amendment = {"method": METHOD, "plan": data["plan"], "implementation": implementation(),
                "authorization_text": AUTHORIZATION, "parent_owner": str(source), "parent_head": head,
                "parent_checkpoint": checkpoint_row["id"], "parent_state_sha256": checkpoint["state_sha256"],
                "deadline_epoch": plan["deadline_epoch"], "queue_token_limit": parent.QUEUE_TOKENS,
                "hard_cap_usd": 150, "operating_cap_usd": 120, "article_retries": 0,
                "protocol": protocol, "migration_owner": str(self.ledger.root), "prepared_at": utc()}
            child = PackingResearch(destination)
            try:
                result = child.execute("status", {"phase": "register", "amendment": amendment},
                    objective="Register explicit continuation with capacity packing and unchanged spending", actor=context.actor)
            finally:
                child.close()
        return self.ledger.record(session, "luna_batch_parallel_migration", str(destination), result)


class PackingResearch(parent.RemainderResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "register":
            value = data["amendment"]
            require(value["implementation"] == implementation() and value["authorization_text"] == AUTHORIZATION, "amendment_binding")
            verify_parent_seal(value)
            identifier = self.ledger.record(session, AMENDMENT, METHOD, value)
            result = {"id": identifier, **value}
            parent.atomic_json(self.ledger.root / "parallel-plan.json", result)
            plan = self.ledger.get(value["plan"], parent.PLAN)
            parent.atomic_json(self.ledger.root / "plan.json", {"id": value["plan"], **plan, "scheduler_amendment": identifier})
            return result
        return self.execute_parallel(session, context, data)

    def execute_parallel(self, session, context, data):
        amendment = self.ledger.get(data["amendment"], AMENDMENT)
        plan = self.ledger.get(data["plan"], parent.PLAN)
        require(amendment["implementation"] == implementation() and amendment["plan"] == data["plan"]
            and amendment["authorization_text"] == AUTHORIZATION and plan["implementation"] == parent.implementation(), "execution_binding")
        require(amendment["deadline_epoch"] == plan["deadline_epoch"] and amendment["queue_token_limit"] == parent.QUEUE_TOKENS, "limit_changed")
        if self.config.offline and getattr(self.transport, "synthetic", False) is not True:
            raise AuditError("batch_handoff_online_mode_required")
        checkpoint = parent.lean.latest(self, parent.CHECKPOINT, data["plan"])
        gateway = PackingGateway(self)
        self.gateway = gateway
        runner = PackingBatch(self.ledger.root / "state.sqlite3", plan=plan, plan_id=data["plan"], engine=self,
            amendment=amendment, gateway=gateway, transport=self.transport, clock=self.clock)
        try:
            require(checkpoint is not None and parent.state_hash(runner.db) == checkpoint[1]["state_sha256"], "state_requires_reconciliation")
            gateway.bind(session, runner, data["plan"], plan["protocol"], network=True)
            require(runner.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "concurrent_reader_mode")
            runner.checkpoint(session, "parallel_wal_ready")
            gateway.imported_counts = {r["custom_id"]: json.loads(r["payload"]) for r in runner.db.execute("SELECT * FROM counts")}
            print(canonical({"phase": "execution_started", "pid": os.getpid(), "plan": data["plan"], "amendment": data["amendment"], "at": utc()}), flush=True)
            result = runner.run_remainder(session, collect_only=data.get("collect_only", False), stop_after_submissions=data.get("test_stop_after_submissions"))
            result.update(plan=data["plan"], amendment=data["amendment"], http_calls=gateway.http_calls, semantic_accuracy_confirmed=False)
            reference = self.ledger.record(session, "luna_batch_parallel_result", data["amendment"], result)
            return {"id": reference, **result}
        finally:
            gateway.network = False
            gateway.session = None
            runner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("migrate", "run", "collect"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--integrity-report", type=Path)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--amendment")
    parser.add_argument("--authorization-text")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if args.phase != "migrate" and (not args.amendment or not args.allow_paid_execution):
        parser.error("Exact amendment and explicit execution flag required")
    print(canonical({"phase": "startup_preflight", "pid": os.getpid(), "workspace": str(args.workspace), "at": utc()}), flush=True)
    engine = MigrationResearch(args.workspace) if args.phase == "migrate" else PackingResearch(args.workspace, config=Config(offline=False))
    try:
        data = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        data["collect_only"] = args.phase == "collect"
        result = engine.execute("status", data, objective="Maximize parallel Batch work within existing limits and preserve all history", actor="codex:batch-parallel")
        print(canonical(result), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
