"""Audited frozen-worker inspection and version-bound scheduler migration.

The operational inspector has its own metadata-only workspace. It never opens
the production Ledger or writes production records; SQLite is mode=ro. The
replacement scheduler alone imports a confirmed handoff after normal preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, digest, require_active, utc
from newsresearch.event_batch_live_gateway import ACTION_KIND, ACTION_IDENTITY_KIND, BUDGET_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.legacy import sha256
from newsresearch.runtime import Research, audited_handler

from execute_luna_budget_wave import action_blockers
from luna_batch_budget_run import BASE, OWNER, ROOT, STUDY, present
import luna_budget_truncation_policy as policy
import run_luna_budget_throughput as predecessor
from luna_budget_worker_control import WindowsWorker

METHOD = "luna-budget-suspended-operational-handoff-v1"
HANDOFF_KIND = "luna_budget_scheduler_handoff"
METADATA_OWNER = BASE / "luna-throughput-handoff-audit-v1"
KINDS = (ACTION_KIND, ACTION_IDENTITY_KIND, RECEIPT_KIND, STOP_KIND, BUDGET_KIND,
    predecessor.RUN_KIND, predecessor.FINISH_KIND, predecessor.fast.JOB_KIND,
    predecessor.fast.MANIFEST_KIND, policy.POLICY_KIND)
SQL = "SELECT id,kind,logical_key,payload,artifact,supersedes,created_event FROM records WHERE kind IN (" + ",".join("?" for _ in KINDS) + ") ORDER BY created_event"


def implementation_hashes() -> dict[str, str]:
    result = predecessor.implementation_hashes()
    for name in ("luna_budget_scheduler_handoff.py", "luna_budget_worker_control.py"):
        result["scripts/" + name] = sha256(ROOT / "scripts" / name)
    return result


def snapshot(connection: sqlite3.Connection, plan_id: str, policy_ref: str) -> Json:
    """One frozen read transaction; no artifacts, article text or credentials."""
    rows, values = list(connection.execute(SQL, KINDS)), {}
    for row in rows:
        if hashlib.sha256(row["payload"].encode()).hexdigest() != row["artifact"] or row["id"] != digest({
                "kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]}):
            raise AuditError("handoff_operational_projection_hash_mismatch")
        values[row["id"]] = json.loads(row["payload"])
    def selected(kind: str) -> list[tuple[sqlite3.Row, Json]]:
        return [(row, values[row["id"]]) for row in rows if row["kind"] == kind]
    actions = [value for _, value in selected(ACTION_KIND)]
    receipts = [value for _, value in selected(RECEIPT_KIND)]
    blockers = action_blockers(actions, receipts, [])
    action_ids = {value["action_id"] for value in actions if value.get("authorization_id") == STUDY}
    if any(value.get("authorization_id") == STUDY and value["action_id"] not in action_ids
           for _, value in selected(ACTION_IDENTITY_KIND)):
        blockers.append("action_identity_without_dispatch_record")
    stops = [row["id"] for row, _ in selected(STOP_KIND) if row["logical_key"] == STUDY]
    if stops:
        blockers.append("gateway_stop_preserved")
    runs = [(row, value) for row, value in selected(predecessor.RUN_KIND) if value.get("plan") == plan_id]
    if not runs:
        raise AuditError("handoff_existing_predecessor_run_required")
    run_row, run = runs[-1]
    if (run.get("policy_ref") != policy_ref or run.get("authorization_id") != STUDY
            or run.get("implementation") != predecessor.implementation_hashes()
            or run_row["logical_key"] != plan_id + ":" + policy_ref + ":throughput-v1"):
        raise AuditError("handoff_exact_latest_predecessor_required")
    if any(value.get("run") == run_row["id"] for _, value in selected(predecessor.FINISH_KIND)):
        raise AuditError("handoff_predecessor_already_terminal_use_existing_drain")
    if policy_ref not in values or values[policy_ref].get("plan") != plan_id:
        raise AuditError("handoff_exact_registered_policy_required")
    budgets = [(row, value) for row, value in selected(BUDGET_KIND) if row["logical_key"] == STUDY]
    if not budgets:
        raise AuditError("handoff_existing_shared_budget_required")
    budget_row, budget = budgets[-1]
    jobs = [(row, value) for row, value in selected(predecessor.fast.JOB_KIND) if value.get("plan") == plan_id]
    receipts_by_id = {row["id"]: value for row, value in selected(RECEIPT_KIND)}
    create_ids = {receipts_by_id[value["receipt"]]["action_id"] for _, value in jobs}
    if any(value.get("plan_id") == plan_id and value.get("phase") == "create" and value["action_id"] not in create_ids for value in actions):
        blockers.append("create_not_yet_bound_to_retained_job")
    if len({value["manifest"] for _, value in jobs}) != len(jobs) or len({value["job_id"] for _, value in jobs}) != len(jobs):
        raise AuditError("handoff_duplicate_existing_jobs")
    head = connection.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
    return {"plan": plan_id, "policy_ref": policy_ref, "predecessor_run": run_row["id"], "predecessor_protocol": run["protocol"],
        "deadline_epoch": run["deadline_epoch"], "budget_state": budget_row["id"],
        "budget_metadata": {key: budget[key] for key in ("state_ref", "committed_nanousd", "charged_nanousd", "reserved_nanousd", "frozen", "price_fingerprint")},
        "record_projection_digest": digest([{key: row[key] for key in ("id", "kind", "logical_key", "artifact", "created_event")} for row in rows]),
        "operational_record_count": len(rows), "journal_head": dict(head),
        "job_record_ids": [row["id"] for row, _ in jobs], "submitted_requests": sum(value["request_count"] for _, value in jobs),
        "action_count": len(action_ids), "gateway_stop_ids": stops, "blockers": sorted(set(blockers)),
        "quiescent": not blockers, "article_text_read": False, "production_records_written": 0}


class HandoffResearch(Research):
    process_factory = WindowsWorker

    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        source = Path(data.get("production_workspace", OWNER)).resolve()
        if not self.config.offline or self.ledger.root.resolve() == source:
            raise AuditError("handoff_requires_separate_offline_metadata_owner")
        if source != OWNER.resolve() and not getattr(self.process_factory, "synthetic", False):
            raise AuditError("handoff_exact_production_owner_required")
        if data.get("allow_process_handoff") is not True:
            raise AuditError("handoff_explicit_process_authorization_required")
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":scheduler-handoff",
            "content": {"method": METHOD, "implementation": implementation_hashes(), "plan": data["plan"],
                "policy_ref": data["policy_ref"], "source": str(source), "sql": SQL, "parameters": list(KINDS),
                "rules": "Verify exact process creation/parent/script/command. Suspend all worker threads; one read-only snapshot. Stop only if every dispatch has one successful retained receipt, each create has its durable job, and no gateway stop exists. Otherwise resume the exact held process handle in finally. Preserve original run as interrupted, all jobs, policy, budget, unknown model costs and original deadline. No provider calls or source text. Replacement requires its own normal preflight and exact snapshot match."}})["id"]
        process = self.process_factory(data)
        suspended, terminated, inspected = False, False, None
        try:
            identity = process.identity()
            self.ledger.append(session, "scheduler.worker_suspend.intended", {"protocol": protocol, "identity": identity})
            process.suspend()
            suspended = True
            if process.identity() != identity:
                raise AuditError("handoff_identity_changed_after_suspend")
            self.ledger.append(session, "scheduler.operational_snapshot.intended", {"source": str(source), "mode": "ro", "sql": SQL, "parameters": list(KINDS)})
            connection = sqlite3.connect((source / "research.sqlite3").as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=0)
            connection.row_factory = sqlite3.Row
            try:
                connection.execute("PRAGMA query_only=ON")
                connection.execute("BEGIN")
                inspected = snapshot(connection, data["plan"], data["policy_ref"])
                connection.execute("ROLLBACK")
            finally:
                connection.close()
            inspection_ref = self.ledger.record(session, "luna_budget_scheduler_inspection", inspected["predecessor_run"], {
                "protocol": protocol, "identity": identity, "source": str(source), **inspected,
                "worker_suspended_during_snapshot": True, "inspected_at": utc()})
            if inspected["quiescent"] and data.get("stop_when_quiescent") is True:
                self.ledger.append(session, "scheduler.worker_stop.intended", {"inspection_ref": inspection_ref,
                    "identity": identity, "meaning": "operator interruption, never predecessor terminal completion"})
                process.terminate()
                terminated = True
            else:
                process.resume()
                suspended = False
            result = {"method": METHOD, "protocol": protocol, "implementation": implementation_hashes(),
                "inspection_ref": inspection_ref, "identity": identity, "source": str(source), **inspected,
                "worker_terminated": terminated, "worker_resumed": not terminated,
                "predecessor_status": "operator_interrupted" if terminated else "still_running",
                "old_finish_fabricated": False, "new_inference": False}
            return present(self, session, HANDOFF_KIND, result,
                f"Operational handoff: worker {'stopped at a verified quiescent point' if terminated else 'resumed; no handoff'}. "
                f"{inspected['action_count']} provider action identities; blockers {inspected['blockers']}. "
                f"{len(inspected['job_record_ids'])} retained remote jobs carry forward; submitted requests {inspected['submitted_requests']}. "
                "No provider calls or article text reads. Original run is not marked complete; all budget liabilities and deadline remain unchanged.")
        finally:
            try:
                if suspended and not terminated:
                    process.resume()
            finally:
                process.close()


def load_registered_policy_cache(engine: Any, session: str, plan_id: str, reference: str) -> policy.VerifiedPolicy:
    """Explicit version-bound reuse of previously registered deterministic proof.

    Normal runtime preflight already verifies immutable journal/projection/artifact
    hashes. This new cache method checks exact prior successful registration and
    current book/held identity; it never imports a previous in-memory seal.
    """
    require_active(engine, session)
    engine.ledger.append(session, "scheduler.baseline_cache.inspection.intended", {"policy_ref": reference,
        "method": METHOD + ":registered-baseline-cache", "implementation": implementation_hashes()})
    value = engine.ledger.get(reference, policy.POLICY_KIND)
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    baseline_ref = value["baseline_ack_ref"]
    baseline = {**engine.ledger.get(baseline_ref, policy.chain.ACK_KIND), "id": baseline_ref}
    registered = engine.ledger.get(value["baseline_registration"], "luna_budget_held_chain_registration")
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY or value.get("method") != policy.METHOD
            or value.get("implementation") != policy.implementation_hashes() or protocol.get("method") != policy.METHOD
            or value.get("user_amendment") != policy.USER_AMENDMENT or value.get("interpretation") != policy.INTERPRETATION
            or any(protocol.get(key) != value[key] for key in ("plan", "inputs", "implementation", "user_amendment", "interpretation"))
            or value.get("baseline") != baseline or registered.get("ack_ref") != baseline_ref
            or any(registered.get(key) != item for key, item in baseline.items() if key != "id")
            or baseline.get("implementation") != policy.chain.implementation_hashes()
            or any(baseline.get(key) != value["inputs"].get(key) for key in policy.chain.INPUTS)
            or any(value.get(key) != baseline[key] for key in policy.chain.held.chain.INHERITED)
            or any(value.get(key) != expected for key, expected in {"paid_retries": 0, "unknown_cost_released": False, "accepted_events": 0}.items())):
        raise AuditError("handoff_registered_baseline_cache_binding_changed")
    # Require a real predecessor that already used this registered baseline.
    predecessor_run = engine.latest(predecessor.RUN_KIND, plan_id + ":" + reference + ":throughput-v1")
    if (predecessor_run is None or predecessor_run[1].get("implementation") != predecessor.implementation_hashes()
            or predecessor_run[1].get("baseline_ack_ref") != baseline_ref):
        raise AuditError("handoff_existing_verified_predecessor_required")
    book, state = policy._real_book(engine, session, plan_id, baseline)
    engine.ledger.record(session, "luna_budget_scheduler_baseline_cache", reference, {
        "plan": plan_id, "policy_ref": reference, "baseline_ack_ref": baseline_ref,
        "baseline_registration": value["baseline_registration"], "predecessor_run": predecessor_run[0],
        "method": METHOD + ":registered-baseline-cache", "implementation": implementation_hashes(),
        "budget_state": state, "held_entry": book.entry(baseline["held_failure"]["custom_id"]),
        "normal_preflight_required": True, "recursive_history_replayed": False, "old_memory_seal_reused": False})
    return policy._seal_policy(engine, session, reference, value)


def register_migration(engine: Any, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    source = Path(data["handoff_workspace"]).resolve()
    if source == engine.ledger.root.resolve() or (source != METADATA_OWNER.resolve() and not getattr(engine.transport, "synthetic", False)):
        raise AuditError("handoff_separate_metadata_proof_required")
    successor = data.get("successor_implementation")
    if (not isinstance(data.get("successor_method"), str) or not data["successor_method"]
            or not isinstance(successor, dict) or "scripts/run_luna_budget_fill.py" not in successor
            or any(not (ROOT / name).resolve().is_relative_to(ROOT.resolve()) or sha256(ROOT / name) != value
                   for name, value in successor.items())):
        raise AuditError("handoff_exact_successor_implementation_required")
    engine.ledger.append(session, "scheduler.handoff_import.intended", {"workspace": str(source), "handoff_ref": data["handoff_ref"],
        "sql": "SELECT kind,logical_key,payload,artifact,supersedes,created_event FROM records WHERE id=?"})
    connection = sqlite3.connect((source / "research.sqlite3").as_uri() + "?mode=ro", uri=True, timeout=0)
    connection.row_factory = sqlite3.Row
    try:
        previous_hash, sequence = "0" * 64, 0
        for event in connection.execute("SELECT * FROM events ORDER BY seq"):
            sequence += 1
            item = {key: event[key] for key in ("seq", "event_id", "session_id", "kind", "time", "previous_hash")}
            item["payload"] = json.loads(event["payload"])
            if event["seq"] != sequence or event["previous_hash"] != previous_hash or digest(item) != event["event_hash"]:
                raise AuditError("handoff_metadata_journal_not_verified")
            previous_hash = event["event_hash"]
        row = connection.execute("SELECT kind,logical_key,payload,artifact,supersedes,created_event FROM records WHERE id=?", (data["handoff_ref"],)).fetchone()
        anchor = connection.execute("SELECT kind,payload FROM events WHERE seq=?", (row[5],)).fetchone() if row else None
        if (anchor is None or anchor[0] != "record.created"
                or json.loads(anchor[1]).get("record") != data["handoff_ref"]
                or json.loads(anchor[1]).get("artifact") != row[3]):
            raise AuditError("handoff_metadata_record_not_journal_anchored")
    finally:
        connection.close()
    if row is None or row[0] != HANDOFF_KIND or hashlib.sha256(row[2].encode()).hexdigest() != row[3] or digest({
            "kind": row[0], "key": row[1], "payload": row[3], "supersedes": row[4]}) != data["handoff_ref"]:
        raise AuditError("handoff_exact_retained_operator_result_required")
    proof = json.loads(row[2])
    if (proof.get("worker_terminated") is not True or proof.get("quiescent") is not True or proof.get("blockers") != []
            or proof.get("plan") != data["plan"] or proof.get("policy_ref") != data["policy_ref"]
            or Path(proof["source"]).resolve() != engine.ledger.root.resolve()
            or proof.get("implementation") != implementation_hashes() or proof.get("old_finish_fabricated") is not False):
        raise AuditError("handoff_confirmed_quiescent_interruption_required")
    current = snapshot(engine.ledger.db, data["plan"], data["policy_ref"])
    if any(current[key] != proof[key] for key in current if key != "journal_head"):
        raise AuditError("handoff_production_snapshot_changed_before_migration")
    head = engine.ledger.db.execute("SELECT event_hash FROM events WHERE seq=?", (proof["journal_head"]["seq"],)).fetchone()
    if head is None or head[0] != proof["journal_head"]["event_hash"]:
        raise AuditError("handoff_inspected_journal_prefix_changed")
    protocol = engine._version(session, context, {"kind": "protocol", "key": STUDY + ":scheduler-migration",
        "content": {"method": METHOD + ":migration", "implementation": implementation_hashes(), "plan": data["plan"],
            "policy_ref": data["policy_ref"], "handoff_ref": data["handoff_ref"], "predecessor_run": proof["predecessor_run"],
            "successor_method": data["successor_method"], "successor_implementation": successor,
            "rules": "Preserve interrupted run without fabricated finish; same real book, policy, original deadline and stable manifests/actions/jobs. No retry or unknown release. Only untouched requests can be admitted after the unchanged current-state gate."}})["id"]
    identifier = engine.ledger.record(session, "luna_budget_scheduler_migration", data["handoff_ref"], {
        "protocol": protocol, "handoff_ref": data["handoff_ref"], **current, "predecessor_status": "operator_interrupted",
        "successor_method": data["successor_method"], "successor_implementation": successor,
        "old_finish_fabricated": False, "new_budget": False, "new_inference": False})
    return {"id": identifier, "protocol": protocol, **current}


def load_migration(engine: Any, session: str, plan_id: str, policy_ref: str, migration_ref: str,
                   successor_method: str, successor_implementation: dict[str, str]) -> Json:
    """Resume the exact registered successor without a second process handoff.

    No admission is granted here. The current real budget, actions, failures and
    deadline must still pass the successor's unchanged gate before any dispatch.
    """
    require_active(engine, session)
    engine.ledger.append(session, "scheduler.migration_reuse.intended", {"plan": plan_id, "policy_ref": policy_ref,
        "migration_ref": migration_ref, "successor_method": successor_method, "implementation": successor_implementation})
    value = engine.ledger.get(migration_ref, "luna_budget_scheduler_migration")
    protocol = engine.ledger.get(value["protocol"], "protocol")["content"]
    if (value.get("plan") != plan_id or value.get("policy_ref") != policy_ref
            or value.get("successor_method") != successor_method or value.get("successor_implementation") != successor_implementation
            or any(not (ROOT / name).resolve().is_relative_to(ROOT.resolve()) or sha256(ROOT / name) != expected
                   for name, expected in successor_implementation.items())
            or protocol.get("method") != METHOD + ":migration" or protocol.get("implementation") != implementation_hashes()
            or any(protocol.get(key) != value[key] for key in
                   ("plan", "policy_ref", "handoff_ref", "predecessor_run", "successor_method", "successor_implementation"))
            or value.get("predecessor_status") != "operator_interrupted" or value.get("old_finish_fabricated") is not False
            or value.get("new_budget") is not False or value.get("new_inference") is not False or value.get("quiescent") is not True
            or value.get("blockers") != []):
        raise AuditError("handoff_exact_registered_migration_required")
    old = engine.ledger.get(value["predecessor_run"], predecessor.RUN_KIND)
    baseline = engine.ledger.get(policy_ref, policy.POLICY_KIND)
    if (old.get("plan") != plan_id or old.get("policy_ref") != policy_ref
            or old.get("protocol") != value["predecessor_protocol"] or old.get("implementation") != predecessor.implementation_hashes()
            or old.get("deadline_epoch") != value["deadline_epoch"] or value["deadline_epoch"] != baseline.get("deadline_epoch")
            or engine.latest(predecessor.FINISH_KIND, value["predecessor_run"])):
        raise AuditError("handoff_interrupted_predecessor_history_changed")
    # Normal full preflight has already checked immutable projections/artifacts.
    # Existing jobs remain identical; new jobs/cost events are never reset.
    for reference in value["job_record_ids"]:
        if engine.ledger.get(reference, predecessor.fast.JOB_KIND).get("plan") != plan_id:
            raise AuditError("handoff_existing_job_identity_changed")
    engine.ledger.get(value["budget_state"], BUDGET_KIND)
    return {"id": migration_ref, **value}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "policy-ref", "worker-image", "command-line-sha256"):
        parser.add_argument("--" + name, required=True)
    for name in ("worker-pid", "worker-created-100ns", "parent-pid", "parent-created-100ns"):
        parser.add_argument("--" + name, type=int, required=True)
    parser.add_argument("--allow-process-handoff", action="store_true")
    parser.add_argument("--stop-when-quiescent", action="store_true")
    args = parser.parse_args()
    engine = HandoffResearch(METADATA_OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args), objective="Inspect exact suspended Luna worker operational metadata and perform only a proved quiescent scheduler handoff", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "inspection_ref", "worker_terminated", "worker_resumed", "predecessor_run", "policy_ref", "blockers")}), flush=True)
        return 0 if result["worker_terminated"] else 2
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
