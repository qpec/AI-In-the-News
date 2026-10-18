"""Offline, one-time import of current Luna operational state; no audit replay.

The legacy database is opened read-only. This module has only stdlib imports,
does not instantiate Research, and never performs network or model operations.
It checks selected hashes and folds the latest budget capsule once into current
balances. Historical journals and source archives are neither scanned nor copied.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import statistics
from typing import Any

Json = dict[str, Any]
VERSION = "lean-luna-state-v1"
CORPORA = {"incident-reports", "cybercrime"}
HARD_CAP = 150_000_000_000
OPERATING_CAP = 120_000_000_000
ACTION = "event_batch_live_action"
RECEIPT = "event_batch_live_receipt"
IDENTITY = "event_batch_live_action_identity"
BUDGET = "event_batch_live_budget"
JOB = "luna_budget_provider_job"
MANIFEST = "luna_budget_dispatch_manifest"
ASSESSMENT = "luna_budget_assessment"
KINDS = (ACTION, RECEIPT, IDENTITY, JOB, MANIFEST, ASSESSMENT,
         "event_batch_live_stop", "luna_batch_count_consumer",
         "luna_budget_job_reconciled", "luna_budget_throughput_run")


class StateError(ValueError):
    """Inspection/import cannot establish the required operational state."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise StateError("invalid_" + name)
    return value


def read_only_database(owner: Path) -> sqlite3.Connection:
    connection = sqlite3.connect((owner.resolve() / "research.sqlite3").as_uri() + "?mode=ro",
        uri=True, isolation_level=None, timeout=0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def row_value(row: sqlite3.Row | None, kind: str | None = None) -> Json:
    if row is None or (kind is not None and row["kind"] != kind):
        raise StateError("missing_or_wrong_operational_record")
    if hashlib.sha256(row["payload"].encode()).hexdigest() != row["artifact"]:
        raise StateError("operational_projection_hash_mismatch")
    if row["id"] != digest({"kind": row["kind"], "key": row["logical_key"],
            "payload": row["artifact"], "supersedes": row["supersedes"]}):
        raise StateError("operational_record_identity_mismatch")
    return {**json.loads(row["payload"]), "_record_id": row["id"], "_logical_key": row["logical_key"]}


class SelectedArtifacts:
    def __init__(self, owner: Path):
        self.root = owner.resolve() / "objects"
        self.checked: set[str] = set()

    def path(self, reference: str) -> Path:
        if not isinstance(reference, str) or not re.fullmatch("[a-f0-9]{64}", reference):
            raise StateError("invalid_artifact_reference")
        path = (self.root / reference).resolve()
        if not path.is_relative_to(self.root):
            raise StateError("artifact_path_escape")
        return path

    def read(self, reference: str) -> bytes:
        raw = self.path(reference).read_bytes()
        if hashlib.sha256(raw).hexdigest() != reference:
            raise StateError("selected_artifact_hash_mismatch")
        self.checked.add(reference)
        return raw

    def check(self, reference: str) -> None:
        if reference in self.checked:
            return
        with self.path(reference).open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != reference:
                raise StateError("selected_artifact_hash_mismatch")
        self.checked.add(reference)

    def json(self, reference: str) -> Any:
        return json.loads(self.read(reference))


def cost(price: Json, inputs: int, outputs: int) -> int:
    integer(inputs, "input_tokens")
    integer(outputs, "output_tokens")
    input_rate = Fraction(max(integer(price["input_nanousd_per_million"], "input_rate", 1),
        integer(price["cache_write_nanousd_per_million"], "cache_write_rate", 1)))
    output_rate = Fraction(integer(price["output_nanousd_per_million"], "output_rate", 1))
    def ratio(name: str) -> Fraction:
        values = price[name]
        return Fraction(integer(values[0], name, 1), integer(values[1], name, 1))
    if inputs > integer(price["long_context_threshold"], "long_context_threshold", 1):
        input_rate *= ratio("long_input_multiplier")
        output_rate *= ratio("long_output_multiplier")
    amount = (inputs * input_rate + outputs * output_rate) / 1_000_000
    amount *= ratio("batch_multiplier") * ratio("regional_multiplier")
    return -(-amount.numerator // amount.denominator)


def fold_budget(state: Json, summary: Json, plan_id: str, authorization_id: str) -> Json:
    """Fold only the latest budget capsule, once; retain no old event chain.

    The capsule contains events rather than a current-entry table. This linear
    conversion checks monetary transitions and source summary equality, without
    invoking BudgetBook or replaying research/audit history on each future action.
    """
    config = state["config"]
    price = config["price_policy"]
    fingerprint = digest(price)
    if (config.get("method") != "event-batch-shared-budget-v1" or config.get("authorization_id") != authorization_id
            or summary.get("authorization_id") != authorization_id or summary.get("price_fingerprint") != fingerprint
            or config.get("ceiling_nanousd") != HARD_CAP or config.get("operational_limit_nanousd") != OPERATING_CAP
            or price.get("model") != "gpt-6-luna"):
        raise StateError("budget_authorization_price_or_caps_changed")
    entries: dict[str, Json] = {}
    task_ids: set[str] = set()
    charged = reserved = 0
    frozen = False
    for event in state["events"]:
        value, action = event["value"], event["action"]
        identifier = value["request_id"]
        if action == "reserve":
            count = value["input_count"]
            if (identifier in entries or value["task_id"] in task_ids or frozen
                    or value["plan_id"] != plan_id or value["corpus_id"] not in CORPORA
                    or value["max_output_tokens"] != 4096 or value["price_fingerprint"] != fingerprint
                    or count["method"] != "provider_responses_input_tokens" or count["model"] != price["model"]
                    or count["request_sha256"] != value["request_sha256"]):
                raise StateError("budget_reservation_identity_or_contract_changed")
            amount = cost(price, integer(count["input_tokens"], "provider_input_tokens", 1), 4096)
            if charged + reserved + amount > OPERATING_CAP:
                raise StateError("budget_operating_cap_exceeded")
            entries[identifier] = {"request": value, "status": "reserved", "reserved_nanousd": amount,
                "charged_nanousd": 0, "accepted": False, "settlement": None}
            task_ids.add(value["task_id"])
            reserved += amount
            continue
        if identifier not in entries:
            raise StateError("budget_transition_without_reservation")
        entry = entries[identifier]
        if entry["status"] not in {"reserved", "unknown"}:
            raise StateError("budget_terminal_transition_repeated")
        request = entry["request"]
        if action == "confirm_unprocessed":
            if value.get("confirmed_unprocessed") is not True or not value.get("confirmation_sha256") or not value.get("provider_request_id"):
                raise StateError("budget_unprocessed_confirmation_missing")
            reserved -= entry["reserved_nanousd"]
            entry.update(status="confirmed_unprocessed", reserved_nanousd=0, settlement=value,
                accepted=False, reason="provider_confirmed_unprocessed")
            continue
        if action != "settle":
            raise StateError("unknown_budget_transition")
        usage = value["usage"]
        if usage is not None and usage.get("request_sha256") != request["request_sha256"]:
            raise StateError("budget_usage_request_mismatch")
        reason: str | None
        status, accepted, charge, reason = "unknown", False, 0, "missing_or_incomplete_usage"
        if usage is not None and usage.get("complete") is True and usage.get("input_tokens") is not None and usage.get("output_tokens") is not None:
            if usage.get("model") != price["model"]:
                status, reason, frozen = "frozen", "unverified_or_wrong_model", True
            else:
                charge = cost(price, usage["input_tokens"], usage["output_tokens"])
                if charge > entry["reserved_nanousd"]:
                    status, reason, frozen = "overrun", "observed_cost_exceeds_reservation", True
                elif usage["input_tokens"] != request["input_count"]["input_tokens"] or usage["output_tokens"] > 4096:
                    status, charge, reason, frozen = "frozen", 0, "provider_token_contract_mismatch", True
                else:
                    status, accepted, reason = "settled", True, None
        if status in {"settled", "overrun"}:
            reserved -= entry["reserved_nanousd"]
            entry["reserved_nanousd"] = 0
            charged += charge
        entry.update(status=status, accepted=accepted, charged_nanousd=charge, settlement=usage, reason=reason)
    actual = {"charged_nanousd": charged, "reserved_nanousd": reserved, "committed_nanousd": charged + reserved, "frozen": frozen}
    if any(summary.get(key) != value for key, value in actual.items()):
        raise StateError("budget_current_totals_mismatch")
    if charged + reserved > HARD_CAP and not frozen:
        raise StateError("budget_hard_cap_exceeded_without_freeze")
    return {"config": config, "price_fingerprint": fingerprint, "entries": entries, **actual,
        "unknown_request_ids": sorted(key for key, value in entries.items() if value["status"] == "unknown"),
        "source_event_count": len(state["events"]), "event_history_imported": False}


def inspect_legacy(owner: Path, *, plan_id: str, authorization_id: str,
                   expected_deadline_epoch: float | None = None) -> Json:
    """One consistent read transaction. This does not grant inference permission."""
    owner = owner.resolve()
    artifacts = SelectedArtifacts(owner)
    connection = read_only_database(owner)
    try:
        def record(reference: str, kind: str | None = None) -> Json:
            return row_value(connection.execute("SELECT * FROM records WHERE id=?", (reference,)).fetchone(), kind)
        plan = record(plan_id, "luna_budget_execution_plan")
        if plan.get("authorization_id") != authorization_id or set(plan.get("corpora", {})) != CORPORA:
            raise StateError("plan_authorization_or_corpora_changed")
        rows = connection.execute("SELECT * FROM records WHERE kind IN (" + ",".join("?" for _ in KINDS) + ") ORDER BY created_event", KINDS)
        selected: dict[str, list[Json]] = {kind: [] for kind in KINDS}
        for row in rows:
            value = row_value(row)
            if value.get("plan", value.get("plan_id", plan_id)) == plan_id and value.get("authorization_id", authorization_id) == authorization_id:
                selected[row["kind"]].append(value)
        blockers: list[str] = []
        actions = selected[ACTION]
        receipts = selected[RECEIPT]
        action_ids = Counter(value["action_id"] for value in actions)
        receipt_ids = Counter(value["action_id"] for value in receipts)
        if any(count != 1 for count in action_ids.values()):
            blockers.append("duplicate_action_identity")
        if any(receipt_ids[key] != 1 for key in action_ids):
            blockers.append("action_missing_or_duplicate_receipt")
        if set(receipt_ids) - set(action_ids):
            blockers.append("orphan_receipt")
        if any(value["action_id"] not in action_ids for value in selected[IDENTITY]):
            blockers.append("identity_without_action")
        uncertain_actions = sorted({value["action_id"] for value in receipts if value.get("unknown") is not False
            or value.get("error_type") or type(value.get("status")) is not int or not 200 <= value["status"] < 300
            or not value.get("body_ref") or value.get("body_sha256") != value.get("body_ref")})
        if uncertain_actions:
            blockers.append("unknown_or_unsuccessful_action")
        if selected["event_batch_live_stop"]:
            blockers.append("legacy_gateway_stop")
        action_map = {value["action_id"]: value for value in actions}
        receipt_map = {value["_record_id"]: value for value in receipts}
        by_action = {value["action_id"]: value for value in receipts}
        for receipt in receipts:
            action = action_map.get(receipt["action_id"])
            if action and any(action.get(key) != receipt.get(key) for key in ("authorization_id", "plan_id", "phase")):
                blockers.append("action_receipt_binding_mismatch")
        submitted: set[str] = set()
        for action in actions:
            if action.get("phase") == "create":
                ids = action.get("reserved_request_ids", [])
                if not ids or len(set(ids)) != len(ids) or submitted.intersection(ids):
                    raise StateError("duplicate_or_empty_paid_request_set")
                submitted.update(ids)
        budgets = connection.execute("SELECT * FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
            (BUDGET, authorization_id)).fetchone()
        budget_record = row_value(budgets, BUDGET)
        budget = fold_budget(artifacts.json(budget_record["state_ref"]), budget_record, plan_id, authorization_id)
        if budget["frozen"]:
            blockers.append("budget_frozen")
        if plan.get("price_fingerprint") != budget["price_fingerprint"] or plan.get("price_policy") != budget["config"]["price_policy"]:
            raise StateError("plan_budget_price_mismatch")
        runs = selected["luna_budget_throughput_run"]
        if not runs:
            raise StateError("original_deadline_unavailable")
        deadline = runs[-1]["deadline_epoch"]
        if (isinstance(deadline, bool) or not isinstance(deadline, (int, float)) or deadline <= 0
                or any(value.get("deadline_epoch") != deadline for value in runs)
                or expected_deadline_epoch is not None and deadline != expected_deadline_epoch):
            raise StateError("original_deadline_mismatch")
        queues: dict[str, Json] = {}
        queue_ids: dict[str, str] = {}
        for corpus, binding in plan["corpora"].items():
            queue = artifacts.json(binding["queue_ref"])
            if queue.get("corpus_id") != corpus or queue.get("manifest_sha256") != binding["manifest_sha256"]:
                raise StateError("queue_partition_mismatch")
            for task in queue["items"]:
                if task["custom_id"] in queue_ids:
                    raise StateError("duplicate_queue_request")
                queue_ids[task["custom_id"]] = corpus
            artifacts.check(binding["preparation_export_ref"])
            queues[corpus] = {**binding, "queue_count": len(queue["items"])}
        manifests, requests = {}, {}
        for manifest in selected[MANIFEST]:
            reference = manifest["_record_id"]
            corpus = manifest["corpus_id"]
            if corpus not in CORPORA or len(manifest["tasks"]) != len(manifest["attempt_ids"]):
                raise StateError("manifest_partition_or_attempt_count_changed")
            ids = []
            for task, attempt in zip(manifest["tasks"], manifest["attempt_ids"], strict=True):
                custom = task["custom_id"]
                if custom in requests or task["corpus_id"] != corpus or queue_ids.get(custom) != corpus:
                    raise StateError("manifest_request_duplicate_or_partition_mismatch")
                requests[custom] = {"custom_id": custom, "corpus_id": corpus, "manifest_id": reference,
                    "attempt_id": attempt, "submitted": custom in submitted,
                    "status": "submitted" if custom in submitted else "staged", "no_retry": True,
                    **{key: task[key] for key in ("row_id", "request_body_ref", "request_ref", "packet_ref", "descriptor") if key in task}}
                if custom not in submitted:
                    for key in ("request_body_ref", "request_ref", "packet_ref"):
                        artifacts.check(task[key])
                ids.append(custom)
            if any(custom not in submitted for custom in ids):
                artifacts.check(manifest["jsonl_ref"])
            manifests[reference] = {"id": reference, "corpus_id": corpus, "jsonl_ref": manifest["jsonl_ref"],
                "request_ids": ids, "phase": manifest["phase"], "submitted": all(custom in submitted for custom in ids)}
        if not submitted <= requests.keys() or not budget["entries"].keys() <= requests.keys():
            raise StateError("paid_or_reserved_request_without_manifest")
        if not submitted <= budget["entries"].keys():
            raise StateError("submitted_request_without_budget_entry")
        for custom, entry in budget["entries"].items():
            request = requests[custom]
            if entry["status"] != "reserved" and custom not in submitted:
                raise StateError("nonreserved_budget_entry_without_submitted_create")
            if entry["request"]["corpus_id"] != request["corpus_id"] or entry["request"]["request_sha256"] != request["request_body_ref"]:
                raise StateError("budget_manifest_binding_mismatch")
        reconciled = {value["manifest"]: value for value in selected["luna_budget_job_reconciled"]}
        jobs: dict[str, Json] = {}
        create_bound: set[str] = set()
        for job in selected[JOB]:
            job_id, manifest_id = job["job_id"], job["manifest"]
            if job_id in jobs or any(value["manifest_id"] == manifest_id for value in jobs.values()):
                raise StateError("duplicate_provider_job")
            manifest = manifests[manifest_id]
            receipt = receipt_map[job["receipt"]]
            action = action_map[receipt["action_id"]]
            if (action["phase"] != "create" or set(action["reserved_request_ids"]) != set(manifest["request_ids"])
                    or job["request_count"] != len(manifest["request_ids"]) or job["corpus_id"] != manifest["corpus_id"]):
                raise StateError("job_create_manifest_mismatch")
            response = artifacts.json(receipt["body_ref"])
            if response.get("id") != job_id:
                raise StateError("job_provider_identity_mismatch")
            create_bound.add(action["action_id"])
            jobs[job_id] = {**job, "manifest_id": manifest_id, "request_ids": manifest["request_ids"],
                "reconciled": manifest_id in reconciled, "reconciliation": reconciled.get(manifest_id),
                "create_action_id": action["action_id"], "provider_create_response": response}
        if {value["action_id"] for value in actions if value.get("phase") == "create"} != create_bound:
            blockers.append("paid_create_without_retained_job")
        results = {}
        for result in selected[ASSESSMENT]:
            custom = result["custom_id"]
            if custom in results or custom not in submitted or result["corpus_id"] != requests[custom]["corpus_id"]:
                raise StateError("duplicate_or_unsubmitted_result")
            if result["request"] != requests[custom]["request_body_ref"] or result["manifest"] != requests[custom]["manifest_id"]:
                raise StateError("result_request_binding_mismatch")
            results[custom] = result
            requests[custom]["status"] = result["status"]
        counts: dict[str, Json] = {}
        for link in selected["luna_batch_count_consumer"]:
            custom = link["custom_id"]
            if custom not in requests:
                raise StateError("count_consumer_without_request")
            task = requests[custom]
            if link["corpus_id"] != task["corpus_id"] or link["request_body_ref"] != task["request_body_ref"]:
                raise StateError("count_consumer_request_mismatch")
            receipt = receipt_map[link["origin_receipt_id"]]
            action = action_map[link["origin_action_id"]]
            if receipt["action_id"] != action["action_id"] or action["phase"] != "count":
                raise StateError("count_consumer_origin_mismatch")
            count = {key: link[key] for key in ("corpus_id", "request_body_ref", "count_body_ref", "origin_action_id",
                "origin_receipt_id", "provider_count_body_sha256", "input_tokens")}
            if custom in counts and counts[custom] != count:
                raise StateError("count_consumer_conflicting_origin")
            if custom not in submitted:
                body = artifacts.json(task["request_body_ref"])
                exact = artifacts.json(action["exact_request_ref"])
                count_body = artifacts.json(link["count_body_ref"])
                response = artifacts.json(receipt["body_ref"])
                if (exact["original_body_ref"] != link["count_body_ref"]
                        or count_body != {key: body[key] for key in ("model", "instructions", "input", "text") if key in body}
                        or response.get("input_tokens") != integer(link["input_tokens"], "exact_input_tokens", 1)
                        or receipt["body_ref"] != link["provider_count_body_sha256"]):
                    raise StateError("staged_exact_count_binding_mismatch")
            counts[custom] = count
        # Only relevant job observations: no source/result-body inspection.
        timing_keys = ("created_at", "in_progress_at", "finalizing_at", "completed_at", "failed_at", "expired_at", "cancelled_at")
        for job in jobs.values():
            job["provider_timestamps"] = {key: job["provider_create_response"].get(key) for key in timing_keys}
            job["provider_observations"] = []
        for action in actions:
            if action.get("phase") != "poll":
                continue
            poll_receipt = by_action.get(action["action_id"])
            if not poll_receipt or poll_receipt["action_id"] in uncertain_actions:
                continue
            exact = artifacts.json(action["exact_request_ref"])
            path = exact.get("logical_request", {}).get("path", "")
            job_id = path.removeprefix("/v1/batches/")
            if job_id not in jobs:
                continue
            response = artifacts.json(poll_receipt["body_ref"])
            if response.get("id") != job_id:
                raise StateError("poll_provider_job_identity_mismatch")
            times = {key: response.get(key) for key in timing_keys}
            jobs[job_id]["provider_observations"].append({"action_id": action["action_id"],
                "received_at": poll_receipt.get("received_at"), "status": response.get("status"), **times})
            jobs[job_id]["provider_timestamps"].update({key: value for key, value in times.items() if value is not None})
        durations = []
        for job in jobs.values():
            times = job["provider_timestamps"]
            started, ended = times.get("created_at"), times.get("completed_at")
            duration = ended - started if type(started) is int and type(ended) is int and ended >= started else None
            job["provider_completed_turnaround_seconds"] = duration
            if duration is not None:
                durations.append(duration)
        ordered = sorted(durations)
        timing = {"completed_jobs_with_both_provider_timestamps": len(ordered), "jobs_missing_completed_duration": len(jobs) - len(ordered),
            "median_seconds": statistics.median(ordered) if ordered else None,
            "p90_nearest_rank_seconds": ordered[max(0, (9 * len(ordered) + 9) // 10 - 1)] if ordered else None,
            "definition": "Provider completed_at minus created_at; no imputation; p90 nearest rank."}
        policies = {reference: record(reference, "policy") for reference in {action["policy_id"] for action in actions}}
        summary = {"actions": len(actions), "unique_actions": len(action_ids), "receipts": len(receipts),
            "paid_create_actions": sum(value.get("phase") == "create" for value in actions),
            "submitted_requests": len(submitted), "assessed_requests": len(results), "jobs": len(jobs),
            "pending_jobs": sum(not value["reconciled"] for value in jobs.values()),
            "staged_requests": sum(not value["submitted"] for value in requests.values()),
            "counted_staged_requests": sum(not requests[key]["submitted"] for key in counts),
            "result_statuses": dict(Counter(value["status"] for value in results.values())),
            "charged_nanousd": budget["charged_nanousd"], "reserved_nanousd": budget["reserved_nanousd"],
            "unknown_cost_requests": len(budget["unknown_request_ids"]), "budget_frozen": budget["frozen"]}
        summary["provider_turnaround"] = timing
        value = {"version": VERSION, "source_owner": str(owner), "plan_id": plan_id, "authorization_id": authorization_id,
            "inspected_at": datetime.now(timezone.utc).isoformat(), "source_execution_stopped_verified": False,
            "deadline_epoch": deadline, "plan": plan, "authorization_policies": policies, "corpora": queues,
            "budget_record_id": budget_record["_record_id"], "budget_state_ref": budget_record["state_ref"], "budget": budget,
            "requests": requests, "manifests": manifests, "jobs": jobs, "results": results, "counts": counts,
            "count_action_cache": {value["logical_hash"]: {"action_id": value["action_id"],
                "exact_request_ref": value["exact_request_ref"], "receipt": by_action.get(value["action_id"])}
                for value in actions if value.get("phase") == "count"},
            "blockers": sorted(set(blockers)), "uncertain_action_ids": uncertain_actions, "summary": summary,
            "selected_artifact_hashes_checked": sorted(artifacts.checked),
            "legacy_result_artifacts_retained_by_reference": True, "historical_journal_replayed": False,
            "source_archives_read": False, "model_or_network_calls": 0, "legacy_database_writes": 0,
            "source_record_set_sha256": digest([{kind: [item["_record_id"] for item in selected[kind]]} for kind in KINDS])}
        return {"snapshot_id": digest(value), **value}
    finally:
        connection.close()


class StateLock(AbstractContextManager["StateLock"]):
    """OS lifetime lock for every writer of the new state, including import."""
    def __init__(self, database: Path):
        self.path = database.resolve().with_suffix(database.suffix + ".lock")
        self.stream: Any = None

    def __enter__(self) -> StateLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                unix_lock: Any = __import__("fcntl")
                unix_lock.flock(self.stream.fileno(), unix_lock.LOCK_EX | unix_lock.LOCK_NB)
        except OSError as error:
            self.stream.close()
            self.stream = None
            raise StateError("lean_state_already_owned") from error
        return self

    def __exit__(self, *args: Any) -> None:
        if self.stream is not None:
            self.stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    unix_lock: Any = __import__("fcntl")
                    unix_lock.flock(self.stream.fileno(), unix_lock.LOCK_UN)
            finally:
                self.stream.close()
                self.stream = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS requests(custom_id TEXT PRIMARY KEY,corpus_id TEXT NOT NULL,manifest_id TEXT NOT NULL,submitted INTEGER NOT NULL,status TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS manifests(id TEXT PRIMARY KEY,corpus_id TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY,manifest_id TEXT NOT NULL UNIQUE,reconciled INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results(custom_id TEXT PRIMARY KEY,status TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budget_entries(custom_id TEXT PRIMARY KEY,status TEXT NOT NULL,charged_nanousd INTEGER NOT NULL,reserved_nanousd INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS counts(custom_id TEXT PRIMARY KEY,input_tokens INTEGER NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS actions(action_id TEXT PRIMARY KEY,phase TEXT NOT NULL,status TEXT NOT NULL,request_json TEXT NOT NULL,receipt_json TEXT);
CREATE INDEX IF NOT EXISTS request_pending ON requests(submitted,corpus_id);
"""


def import_snapshot(snapshot: Json, destination: Path, *, source_execution_stopped: bool = False) -> Json:
    """Create the lean state once; an exact re-import never resets later progress."""
    identifier = snapshot.get("snapshot_id")
    if snapshot.get("version") != VERSION or digest({key: value for key, value in snapshot.items() if key != "snapshot_id"}) != identifier:
        raise StateError("snapshot_hash_or_version_mismatch")
    destination = destination.resolve()
    if destination.is_relative_to(Path(snapshot["source_owner"]).resolve()):
        raise StateError("destination_must_not_modify_legacy_owner")
    if source_execution_stopped is not True:
        raise StateError("explicit_source_execution_stopped_required")
    with StateLock(destination):
        connection = sqlite3.connect(destination, isolation_level=None, timeout=0)
        try:
            connection.executescript(SCHEMA)
            existing = connection.execute("SELECT value FROM meta WHERE key='snapshot_id'").fetchone()
            if existing:
                if json.loads(existing[0]) != identifier:
                    raise StateError("lean_state_already_imported_from_different_snapshot")
                return {"snapshot_id": identifier, "state": str(destination), "reused": True}
            if any(connection.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in
                    ("requests", "manifests", "jobs", "results", "budget_entries", "counts", "actions", "meta")):
                raise StateError("nonempty_destination_without_snapshot_identity")
            connection.execute("BEGIN IMMEDIATE")
            metadata = {key: snapshot[key] for key in ("snapshot_id", "version", "source_owner", "plan_id", "authorization_id",
                "deadline_epoch", "plan", "authorization_policies", "corpora", "budget_record_id", "budget_state_ref",
                "blockers", "uncertain_action_ids", "summary", "count_action_cache", "selected_artifact_hashes_checked")}
            metadata["budget"] = {key: value for key, value in snapshot["budget"].items() if key != "entries"}
            metadata["imported_unknown_entry_hashes"] = {key: digest(value)
                for key, value in snapshot["budget"]["entries"].items() if value["status"] == "unknown"}
            metadata["source_execution_stopped_attested_by_importer"] = True
            metadata["new_inference_authorized"] = False
            for key, value in metadata.items():
                connection.execute("INSERT INTO meta VALUES (?,?)", (key, canonical(value)))
            for custom, row in snapshot["requests"].items():
                connection.execute("INSERT INTO requests VALUES (?,?,?,?,?,?)", (custom, row["corpus_id"], row["manifest_id"], int(row["submitted"]), row["status"], canonical(row)))
            for reference, row in snapshot["manifests"].items():
                connection.execute("INSERT INTO manifests VALUES (?,?,?)", (reference, row["corpus_id"], canonical(row)))
            for job_id, row in snapshot["jobs"].items():
                connection.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job_id, row["manifest_id"], int(row["reconciled"]), canonical(row)))
            for custom, row in snapshot["results"].items():
                connection.execute("INSERT INTO results VALUES (?,?,?)", (custom, row["status"], canonical(row)))
            for custom, row in snapshot["budget"]["entries"].items():
                connection.execute("INSERT INTO budget_entries VALUES (?,?,?,?,?)", (custom, row["status"], row["charged_nanousd"], row["reserved_nanousd"], canonical(row)))
            for custom, row in snapshot["counts"].items():
                connection.execute("INSERT INTO counts VALUES (?,?,?)", (custom, row["input_tokens"], canonical(row)))
            connection.commit()
        finally:
            connection.close()
    return {"snapshot_id": identifier, "state": str(destination), "reused": False, "summary": snapshot["summary"],
        "blockers": snapshot["blockers"], "new_inference_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--owner", type=Path, required=True)
    inspect.add_argument("--plan-id", required=True)
    inspect.add_argument("--authorization-id", required=True)
    inspect.add_argument("--expected-deadline-epoch", type=float)
    inspect.add_argument("--output", type=Path, required=True)
    load = sub.add_parser("import")
    load.add_argument("--snapshot", type=Path, required=True)
    load.add_argument("--destination", type=Path, required=True)
    load.add_argument("--source-execution-stopped", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        if args.output.resolve().is_relative_to(args.owner.resolve()):
            raise StateError("snapshot_output_must_not_modify_legacy_owner")
        value = inspect_legacy(args.owner, plan_id=args.plan_id, authorization_id=args.authorization_id,
            expected_deadline_epoch=args.expected_deadline_epoch)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(canonical(value))
        print(canonical({key: value[key] for key in ("snapshot_id", "summary", "blockers")}))
    else:
        value = import_snapshot(json.loads(args.snapshot.read_text(encoding="utf-8")), args.destination,
            source_execution_stopped=args.source_execution_stopped)
        print(canonical(value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
