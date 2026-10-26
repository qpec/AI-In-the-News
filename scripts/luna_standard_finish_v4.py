"""Versioned Standard-only continuation of a sealed three-route owner.

No old controller is resumed. Failed count identities remain quarantined;
accepted Batch jobs are collected after Standard admissions have started.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import threading
import time

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions, prepare_root

import luna_standard_api as api
import luna_all_routes as routes
import luna_standard_finish as previous_finish
import luna_standard_finish_v3 as previous_v3
import luna_finish_recovery as recovery
import luna_policy_quarantine as quarantine
from dataclasses import asdict
from newsresearch.common import require_no_credentials
from collections import Counter

parent, parallel, batch, lean, state = api.parent, api.parallel, api.batch, api.lean, api.state
canonical, digest = api.canonical, api.digest
METHOD = "luna-standard-finish-v4"
AMENDMENT = "luna_standard_finish_amendment"
ASSIGNMENT = "luna_standard_finish_assignment"
AUTHORIZATION = "Set aside articles where this whent wrong and comtinue with the same speed. So fhis is error handling."
RECOVERY_AUTHORIZATION = "I need you to add self heal to that 15 min cron. Ensure this thing keeps running"
STEERING = "Dont wait on the batched to finish, gogogo 64 concurrent"


def require(condition, reason):
    if not condition:
        raise AuditError("standard_finish_" + reason)


def implementation():
    return {**previous_v3.implementation(), "scripts/luna_standard_finish_v4.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scripts/luna_finish_recovery.py": hashlib.sha256(Path(recovery.__file__).read_bytes()).hexdigest()}


def failed_receipt(member):
    return bool(member.get("unknown") or member.get("retention_error") or member.get("error_type")
        or member.get("status") is None or not 200 <= member["status"] < 300)


def pin_parent_exceptions(database, journal, artifacts, prior, plan):
    """Only the newly authorized, fully retained policy error joins prior holds."""
    actions = {r["action_id"]: digest(dict(r)) for r in database.execute("SELECT * FROM actions WHERE status!='complete'")}
    require(actions == prior["held_actions"], "changed_parent_action")
    local = recovery.local_reservations(database, journal, plan)
    other = [r[0] for r in database.execute("SELECT custom_id FROM requests WHERE status IN ('admitted','creating','unknown_create','standard_inflight','codex_inflight')") if r[0] not in local]
    require(not other, "unresolved_parent_admission")
    intended, receipts = {}, {}
    for row in journal.execute("SELECT * FROM records WHERE kind IN (?,?) ORDER BY created_event", (lean.INTENT, lean.RECEIPT)):
        value = state.row_value(row)
        for member in value["members"]:
            target = intended if row["kind"] == lean.INTENT else receipts
            require(member["action_id"] not in target, "duplicate_parent_http")
            target[member["action_id"]] = member
    require(set(intended) == set(receipts), "unresolved_parent_http")
    policies = {}
    for row in journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (api.RESULT,)):
        for saved in state.row_value(row)["items"]:
            receipt = saved["receipt"]
            if receipt.get("status") == 400 and receipt.get("body_ref"):
                raw = artifacts.read(receipt["body_ref"])
                if quarantine.is_policy_rejection(receipt, raw):
                    require(saved["custom_id"] not in policies and intended[saved["action_id"]]["request"] == api.ROUTE, "policy_identity")
                    policies[saved["custom_id"]] = quarantine.describe(saved, receipts[saved["action_id"]], artifacts, plan)
    approved = {value["action_id"]: value["receipt_sha256"] for value in policies.values()}
    failed = {}
    for action, member in receipts.items():
        if failed_receipt(member):
            require(digest(member) in (prior["failed_receipts"].get(action), approved.get(action)), "new_unclassified_parent_failure")
            failed[action] = digest(member)
    require(all(failed.get(k) == v for k, v in prior["failed_receipts"].items()), "prior_receipt_changed")
    costs = {r[0]: digest(json.loads(r[1])) for r in database.execute("SELECT custom_id,payload FROM budget_entries WHERE status IN ('unknown','frozen','overrun')")}
    failures = {r[0]: digest(json.loads(r[1])) for r in database.execute("SELECT custom_id,payload FROM results WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1")}
    for custom, hashed in costs.items():
        require(hashed in (prior["inherited_cost_holds"].get(custom), policies.get(custom, {}).get("cost_sha256")), "unclassified_parent_cost")
    for custom, hashed in failures.items():
        require(hashed in (prior["inherited_failures"].get(custom), policies.get(custom, {}).get("result_sha256")), "unclassified_parent_result")
    require(all(costs.get(k) == v for k, v in prior["inherited_cost_holds"].items())
        and all(failures.get(k) == v for k, v in prior["inherited_failures"].items()), "missing_prior_hold")
    for custom in prior["quarantined_custom_ids"]:
        request = database.execute("SELECT submitted FROM requests WHERE custom_id=?", (custom,)).fetchone()
        require(request and not request[0] and not database.execute("SELECT 1 FROM counts WHERE custom_id=?", (custom,)).fetchone(), "count_hold_changed")
    quarantine.verify_projection(database, policies)
    return {"held_actions": actions, "failed_receipts": failed,
        "quarantined_custom_ids": prior["quarantined_custom_ids"], "inherited_cost_holds": costs,
        "inherited_failures": failures, "inherited_policy_rejections": policies,
        "local_reservation_quarantine": local}


class FinishGateway(api.StandardGateway):
    def bind(self, session, runner, baseline, protocol, *, network):
        lean.require_active(self.engine, session)
        self.session, self.runner, self.baseline, self.protocol = session, runner, baseline, protocol
        self.writer, self.network = threading.get_ident(), network
        self.policy_receipt_members = {}
        approved = {v["action_id"]: v["receipt_sha256"] for v in runner.policy_quarantines.values()}
        intended, completed = set(), set()
        for row in self.engine.ledger.db.execute("SELECT id,kind FROM records WHERE kind IN (?,?) ORDER BY created_event", (lean.INTENT, lean.RECEIPT)):
            value = self.engine.ledger.get(row["id"], row["kind"])
            for member in value["members"]:
                target = intended if row["kind"] == lean.INTENT else completed
                require(member["action_id"] not in target, "duplicate_http_history")
                target.add(member["action_id"])
                if row["kind"] == lean.RECEIPT and failed_receipt(member):
                    require(digest(member) in (runner.amendment["failed_receipts"].get(member["action_id"]), approved.get(member["action_id"])), "new_failed_gateway_action_no_retry")
        require(intended == completed, "unresolved_gateway_action")
        self.old_actions = intended
        recovery.verify_local_projection(runner.db, runner.amendment.get("local_reservation_quarantine", {}))
        recovery.verify_no_dispatch(self.engine.ledger.db, runner.amendment.get("local_reservation_quarantine", {}))
        # Retain the original immutable manifest record on process restart.
        # A new protocol metadata record must not obscure its existing route.
        for row in self.engine.ledger.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (lean.MANIFEST,)):
            value = state.row_value(row)
            if value["baseline"] == baseline:
                value["record_id"] = row["id"]
                self.manifests.setdefault(value["manifest_id"], value)

    def prepare_many(self, actions, manifest=None):
        require(all(a["request"] == batch.COUNT_ROUTE or a["request"]["method"] == "GET" for a in actions), "no_new_batch_writes")
        return super().prepare_many(actions, manifest)

    def retain_many(self, received):
        self.assert_active()
        assert self.session is not None
        if not received:
            return []
        members, results = [], []
        for item in received:
            handle, result = item.action, item.receipt
            if (self.handles.get(handle.action_id) is not handle or handle.action_id not in self.used
                    or handle.action_id in self.retained):
                raise AuditError("lean_receipt_without_single_dispatch")
            try:
                require_no_credentials(result.headers)
                if result.body is not None:
                    api.http._safe_raw(result.body)
            except Exception as error:
                result = api.http.BatchReceipt(None, result.status, error_type=type(error).__name__, unknown=True,
                    retention_error="credential_guard", body_sha256=lean.sha(result.body) if result.body is not None else None)
            value = asdict(result)
            value.pop("body")
            value["body_sha256"] = lean.sha(result.body) if result.body is not None else result.body_sha256
            if result.body is not None:
                # Counts/small receipts share one bundle artifact; downloads stay raw.
                try:
                    small_text = result.body.decode("utf-8") if len(result.body) < 8192 else None
                except UnicodeDecodeError:
                    small_text = None
                if small_text is None:
                    value["raw_body_ref"] = self.engine.ledger.artifacts.put_bytes(result.body)
                else:
                    value["raw_body_utf8"] = small_text
            value.update(action_id=handle.action_id, intent=handle.intent_ref, completed_at=item.completed_at)
            members.append(value)
            results.append(result)
        self.engine.ledger.record(self.session, lean.RECEIPT, digest([item.action.action_id for item in received]), {"members": members, "protocol": self.protocol})
        for item, result, member in zip(received, results, members, strict=True):
            self.retained.add(item.action.action_id)
            self.receipts[item.action.action_id] = result
            allowed_policy = (json.loads(item.action.request_json) == api.ROUTE
                and quarantine.is_policy_rejection(member, result.body))
            if allowed_policy:
                self.policy_receipt_members[item.action.action_id] = member
            elif result.unknown or result.retention_error or result.body is None or result.status is None or not 200 <= result.status < 300:
                self.stopped = True
            request = json.loads(item.action.request_json)
            if request["method"] == "GET" and request["path"].startswith("/v1/batches/") and not self.stopped:
                answer = json.loads(result.body or b"{}")
                if answer.get("id") != request["path"].split("/")[-1]:
                    self.stopped = True
                    raise AuditError("lean_poll_job_identity_changed")
                self.file_ids.update(answer[key] for key in ("output_file_id", "error_file_id") if answer.get(key))
        return results


class FinishBatch(api.StandardBatch):
    def initialize_finish(self):
        self.initialize_standard()
        self.db.execute("CREATE TABLE IF NOT EXISTS finish_policy_quarantine(custom_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
        for custom, value in self.policy_quarantines.items():
            self.db.execute("INSERT OR IGNORE INTO finish_policy_quarantine VALUES(?,?)", (custom, canonical(value)))
        self.stage_times = {"admission_seconds": 0.0, "save_seconds": 0.0, "admissions": 0, "peak_inflight": 0}
        self.db.execute("CREATE INDEX IF NOT EXISTS finish_technical_failures ON results(custom_id) WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1")
        self.db.execute("CREATE INDEX IF NOT EXISTS finish_request_manifest ON requests(manifest_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS finish_cost_status ON budget_entries(status)")
        self.db.execute("CREATE TEMP TABLE finish_scope(custom_id TEXT PRIMARY KEY,corpus_id TEXT NOT NULL)")
        self.db.executemany("INSERT INTO finish_scope VALUES(?,?)", [(custom, d["corpus_id"]) for custom, d in self.allowed.items()])
        self.db.execute("CREATE TABLE IF NOT EXISTS finish_v2_manifests(manifest_id TEXT PRIMARY KEY,payload TEXT NOT NULL)")
        self.held = set(self.amendment["quarantined_custom_ids"])
        known = {r[0]: r[1] for r in self.db.execute("SELECT custom_id,submitted FROM requests")}
        counted = {r[0] for r in self.db.execute("SELECT custom_id FROM counts")}
        self.available = {k: deque(sorted((d for d in rows if not known.get(d["custom_id"], False)
            and d["custom_id"] not in self.held), key=lambda d: d["custom_id"] not in counted)) for k, rows in self.queues.items()}
        self.cursor = 0

    def preserved_batch_error(self, custom, entry, result):
        # Policy rejects retain unchanged result and full reserved cost.
        policy = self.policy_quarantines.get(custom)
        if policy:
            row = self.db.execute("SELECT payload FROM finish_policy_quarantine WHERE custom_id=?", (custom,)).fetchone()
            return bool(row and json.loads(row[0]) == policy and digest(entry) == policy["cost_sha256"]
                and result and digest(result) == policy["result_sha256"])
        inherited = self.amendment["pending_batch_members"].get(custom)
        if not inherited or not result or result.get("raw_status") != "error" or result.get("usage_complete") is True:
            return False
        job = self.db.execute("SELECT reconciled,payload FROM jobs WHERE job_id=?", (inherited["job_id"],)).fetchone()
        if not job or not job[0] or entry["status"] != "unknown" or entry["charged_nanousd"] != 0:
            return False
        original = inherited["reservation"]
        if entry != {**original, "status": "unknown", "settlement": result.get("usage")}:
            return False
        count = self.db.execute("SELECT COUNT(*) FROM results r JOIN requests q USING(custom_id) WHERE q.manifest_id=? AND json_extract(r.payload,'$.technical_failure')=1 AND COALESCE(json_extract(r.payload,'$.lean_qualifying_truncation'),0)!=1", (json.loads(job[1])["manifest_id"],)).fetchone()[0]
        return count <= self.amendment["completed_batch_jobs"][inherited["job_id"]]["request_counts"]["failed"]

    def admission_checks(self):
        if (self.database.parent / "STOP").exists():
            raise state.StateError("user_stop")
        inherited = self.amendment["inherited_cost_holds"]
        seen = set()
        for row in self.db.execute("SELECT * FROM budget_entries WHERE status IN ('unknown','frozen','overrun')"):
            custom, entry = row["custom_id"], json.loads(row["payload"])
            require((entry["status"], entry["charged_nanousd"], entry["reserved_nanousd"])
                == (row["status"], row["charged_nanousd"], row["reserved_nanousd"]), "cost_projection_changed")
            if custom in inherited:
                require(digest(entry) == inherited[custom], "inherited_cost_hold_changed")
                seen.add(custom)
            else:
                result = self.db.execute("SELECT payload FROM results WHERE custom_id=?", (custom,)).fetchone()
                require(self.preserved_batch_error(custom, entry, json.loads(result[0]) if result else None), "new_unknown_or_frozen_cost")
        require(seen == set(inherited), "missing_inherited_cost_hold")
        for row in self.db.execute("SELECT custom_id,payload FROM results WHERE json_extract(payload,'$.technical_failure')=1 AND COALESCE(json_extract(payload,'$.lean_qualifying_truncation'),0)!=1"):
            result = json.loads(row[1])
            if self.amendment["inherited_failures"].get(row[0]) == digest(result):
                continue
            cost = self.db.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (row[0],)).fetchone()
            require(cost and self.preserved_batch_error(row[0], json.loads(cost[0]), result), "new_technical_failure")

    def check_prior_actions(self):
        actual = {r["action_id"]: digest(dict(r)) for r in self.db.execute("SELECT * FROM actions WHERE status!='complete'")}
        require(actual == self.amendment["held_actions"], "new_or_changed_prior_action")
        require(not recovery.remaining_attempts(self.db, self.amendment.get("local_reservation_quarantine", {})), "prior_standard_intent")

    def log_next(self):
        self.require_runtime()
        row = self.db.execute("SELECT f.payload FROM finish_v2_manifests f WHERE EXISTS(SELECT 1 FROM requests r WHERE r.manifest_id=f.manifest_id AND r.status='logged') ORDER BY f.rowid LIMIT 1").fetchone()
        if row:
            return json.loads(row[0])
        corpora = list(self.available)
        selected, corpus = [], None
        for _ in corpora:
            corpus = corpora[self.cursor % len(corpora)]
            self.cursor += 1
            queue = self.available[corpus]
            while queue and len(selected) < 250:
                descriptor = queue.popleft()
                old = self.db.execute("SELECT submitted FROM requests WHERE custom_id=?", (descriptor["custom_id"],)).fetchone()
                if not old or not old[0]:
                    selected.append(descriptor)
            if selected:
                break
        if not selected:
            return None
        records = self.materialize(selected, self.meta["corpora"][corpus]["partition"])
        manifest = {**batch.prompt_file(self.database.parent, corpus, records, self.snapshot), "remainder_plan": self.plan_id}
        prior = {}
        for task in manifest["tasks"]:
            custom = task["custom_id"]
            old = self.db.execute("SELECT * FROM requests WHERE custom_id=?", (custom,)).fetchone()
            require(custom not in self.held and not self.db.execute("SELECT 1 FROM budget_entries WHERE custom_id=?", (custom,)).fetchone(), "spent_or_held_identity")
            if old:
                value = json.loads(old["payload"])
                require(not old["submitted"] and old["status"] == "logged"
                    and value["request_body_ref"] == task["request_body_ref"] and value["descriptor"] == task["descriptor"], "changed_or_spent_packet")
                prior[custom] = {"manifest_id": old["manifest_id"], "payload_sha256": digest(value)}
        binding = self.gateway.retain_manifest(manifest)
        self.engine.ledger.record(self.gateway.session, ASSIGNMENT, manifest["id"], {
            "plan": self.plan_id, "amendment": self.amendment["id"], "manifest": binding["record_id"],
            "route": "standard", "request_ids": manifest["request_ids"], "prior_unsubmitted_bindings": prior,
            "at": utc(), "reason": "Latest user selected Standard API only; all original bytes, counts and intents retained."})
        with batch.transaction(self.db):
            for task in manifest["tasks"]:
                value = {**task, "manifest_id": manifest["id"], "submitted": False}
                self.db.execute("INSERT INTO requests VALUES(?,?,?,0,'logged',?) ON CONFLICT(custom_id) DO UPDATE SET manifest_id=excluded.manifest_id,payload=excluded.payload",
                    (task["custom_id"], corpus, manifest["id"], canonical(value)))
            self.db.execute("INSERT OR IGNORE INTO manifests VALUES(?,?,?)", (manifest["id"], corpus, canonical(manifest)))
            self.db.execute("INSERT INTO finish_v2_manifests VALUES(?,?)", (manifest["id"], canonical(manifest)))
        return manifest

    def start_standard(self, *args, **kwargs):
        started = time.perf_counter()
        result = super().start_standard(*args, **kwargs)
        self.stage_times["admission_seconds"] += time.perf_counter() - started
        if result is None:
            self.stage_times["admissions"] += 1
            self.stage_times["peak_inflight"] = max(self.stage_times["peak_inflight"], len(self.standard_futures))
        return result

    def pump_standard(self):
        started = time.perf_counter()
        ready = [future for future in self.standard_futures if future.done()]
        if not ready:
            return
        received = [future.result() for future in ready]
        retained = self.gateway.retain_many(received)
        # If parsing or persistence unexpectedly fails, these receipts are already
        # durable. Never attempt to retain/dispatch them a second time in finally.
        work = [self.standard_futures.pop(future) for future in ready]
        saved = []
        with batch.transaction(self.db):
            for details, result, receipt in zip(work, received, retained, strict=True):
                manifest, task, body, entry = details
                parsed, envelope = api.parse_standard(task, body, receipt, self.snapshot)
                item, cost = api.settle_standard(self.plan, entry, parsed, envelope)
                custom = task["custom_id"]
                self.db.execute("UPDATE budget_entries SET status=?,charged_nanousd=?,reserved_nanousd=?,payload=? WHERE custom_id=?",
                    (cost["status"], cost["charged_nanousd"], cost["reserved_nanousd"], canonical(cost), custom))
                self.db.execute("INSERT INTO results VALUES(?,?,?)", (custom, item["status"], canonical(item)))
                self.db.execute("UPDATE requests SET status=? WHERE custom_id=?", (item["status"], custom))
                self.db.execute("UPDATE standard_attempts SET status='saved' WHERE custom_id=?", (custom,))
                receipt_value = asdict(receipt)
                receipt_value.pop("body")
                receipt_value["body_ref"] = self.engine.ledger.artifacts.put_bytes(receipt.body) if receipt.body is not None else None
                saved.append({"custom_id": custom, "action_id": result.action.action_id,
                    "manifest": manifest["id"], "receipt": receipt_value, "item": item, "cost": cost})
                if result.action.action_id in self.gateway.policy_receipt_members:
                    policy = quarantine.describe(saved[-1], self.gateway.policy_receipt_members[result.action.action_id],
                        state.SelectedArtifacts(self.database.parent), self.plan)
                    saved[-1]["policy_quarantine"] = policy
                    self.db.execute("INSERT INTO finish_policy_quarantine VALUES(?,?)", (custom, canonical(policy)))
                    self.policy_quarantines[custom] = policy
                for field, header in (("tpm", "x-ratelimit-limit-tokens"), ("rpm", "x-ratelimit-limit-requests")):
                    observed = receipt.headers.get(header)
                    if observed and observed.isdigit() and int(observed) > 0:
                        self.update_control(field, min(self.control()[field], int(observed)))
                # Respect depleted shared capacity even when other project traffic
                # used it. A failure itself still stops: no retry/probing loop.
                remaining = receipt.headers.get("x-ratelimit-remaining-tokens", "")
                if remaining.isdigit() and int(remaining) < 4096:
                    self.update_control("next_admission", max(self.control()["next_admission"], self.clock() + 60))
                if cost["status"] == "settled" and (not item["technical_failure"] or item["lean_qualifying_truncation"]):
                    self.update_control("probe_complete", True)
                elif "policy_quarantine" not in saved[-1]:
                    self.stop_reason = "standard_result_requires_review"
        self.engine.ledger.record(self.gateway.session, api.RESULT, digest([row["action_id"] for row in saved]), {
            "method": METHOD, "plan": self.plan_id, "amendment": self.amendment["id"],
            "items": saved, "saved_at": utc(), "semantic_accuracy_confirmed": False})
        if self.gateway.stopped:
            self.stop_reason = self.stop_reason or "standard_http_failure_no_retry"
        self.prune_completed()
        self.stage_times["save_seconds"] += time.perf_counter() - started

    def summary(self):
        # Frozen identity membership replaces repeated parsing of large manifest
        # JSON. No interpretation, eligibility, accounting or validation changes.
        result = batch.LeanBatch.summary(self)
        counts = {k: {"total": len(v), "submitted": 0, "returned": 0, "raw_counts": {}} for k, v in self.queues.items()}
        raw = {k: Counter() for k in counts}
        for row in self.db.execute("SELECT s.corpus_id,r.submitted,v.status FROM finish_scope s JOIN requests r USING(custom_id) LEFT JOIN results v USING(custom_id)"):
            counts[row[0]]["submitted"] += bool(row[1])
            if row[2] is not None:
                counts[row[0]]["returned"] += 1
                raw[row[0]][row[2]] += 1
        for corpus, value in counts.items():
            value.update(raw_counts=dict(raw[corpus]), unsubmitted=value["total"] - value["submitted"], pending=value["submitted"] - value["returned"])
        sent, saved = self.db.execute("SELECT COUNT(*),COALESCE(SUM(status='saved'),0) FROM standard_attempts").fetchone()
        result.update(corpora=counts, new_submitted=sum(v["submitted"] for v in counts.values()),
            new_returned=sum(v["returned"] for v in counts.values()),
            unknown_cost_holds=self.db.execute("SELECT COUNT(*) FROM budget_entries WHERE status='unknown'").fetchone()[0],
            standard_submitted=sent, standard_saved=saved, standard_inflight=sent-saved,
            standard_control=self.control(), standard_worker_ceiling=64,
            standard_rate_basis="Persisted input plus maximum-output reservations; lower observed project ceilings win. Not measured throughput.",
            policy_quarantined=len(self.policy_quarantines), method=METHOD, amendment=self.amendment["id"], count_held=len(self.amendment["quarantined_custom_ids"]),
            codex_running=False, new_batch_submissions_enabled=False, local_stage_timings=dict(self.stage_times))
        local = self.amendment.get("local_reservation_quarantine", {})
        recovery.verify_local_projection(self.db, local)
        local_by_corpus = Counter(self.db.execute("SELECT corpus_id FROM requests WHERE custom_id=?", (custom,)).fetchone()[0] for custom in local)
        for corpus, value in counts.items():
            value["local_reservation_quarantined"] = local_by_corpus[corpus]
            value["pending"] -= local_by_corpus[corpus]
        result["standard_inflight"] -= len(local)
        result["local_reservation_quarantined"] = len(local)
        return result

    def run_finish(self, session, *, collect_only=False, test_stop_after=None):
        self.require_runtime()
        self.allow_network = True
        self.admission_checks()
        self.check_prior_actions()
        waiting, tasks, bodies, admitted, pressure = None, [], {}, 0, None
        # Start Standard immediately. Batch completion/collection is no prerequisite.
        next_poll, last_checkpoint = self.clock() + 60, self.clock()
        exhausted = False
        with ThreadPoolExecutor(max_workers=64) as pool:
            def tick():
                self.pump_standard()
                self.progress("standard_running")
            try:
                while True:
                    tick()
                    if (self.database.parent / "STOP").exists():
                        self.stop_reason, self.gateway.stopped = "user_stop", True
                    if self.stop_reason:
                        break
                    admission = not collect_only and self.clock() < self.meta["deadline_epoch"]
                    if admission and not exhausted and len(self.standard_futures) < 64:
                        if waiting is None:
                            waiting = self.log_next()
                            exhausted = waiting is None
                            if waiting:
                                self.progress("standard_counting", force=True)
                                self.count_file(waiting, tick)
                                self.gateway.imported_counts.update({r[0]: json.loads(r[1]) for r in self.db.execute("SELECT custom_id,payload FROM counts WHERE custom_id IN (SELECT custom_id FROM requests WHERE manifest_id=?)", (waiting["id"],))})
                                self.prune_completed()
                                tasks = [t for t in waiting["tasks"] if self.db.execute("SELECT submitted FROM requests WHERE custom_id=?", (t["custom_id"],)).fetchone()[0] == 0]
                                bodies = {r["custom_id"]: r["body"] for r in map(json.loads, self.raw(waiting).splitlines())}
                        if tasks:
                            pressure = self.start_standard(pool, waiting, tasks[0], bodies[tasks[0]["custom_id"]])
                            if pressure is None:
                                tasks.pop(0)
                                admitted += 1
                                if not tasks:
                                    waiting = None
                                if test_stop_after and admitted >= test_stop_after:
                                    self.stop_reason = "test_bounded_stop"
                                    break
                    if collect_only or (admitted >= 64 and self.clock() >= next_poll) or (exhausted and not self.standard_futures) or not admission:
                        self.collect()
                        self.prune_completed()
                        next_poll = self.clock() + 300
                    if self.clock() - last_checkpoint >= 600:
                        self.checkpoint(session, "standard_periodic")
                        last_checkpoint = self.clock()
                    pending = self.db.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone()
                    if not self.standard_futures and not pending and (not admission or exhausted or pressure == "budget"):
                        self.stop_reason = "deadline_or_collect_complete" if not admission else "budget" if pressure == "budget" else "eligible_queue_exhausted"
                        break
                    self.progress("standard_rate_wait" if pressure == "rate" else "standard_running")
                    time.sleep(0.025)
            except BaseException as error:
                self.stop_reason = self.stop_reason or type(error).__name__
                raise
            finally:
                while self.standard_futures:
                    self.pump_standard()
                    if self.standard_futures:
                        time.sleep(0.05)
                self.checkpoint(session, self.stop_reason or "standard_exception")
        return {"reason": self.stop_reason, **self.summary()}


class FinishResearch(parent.RemainderResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "register":
            value = data["amendment"]
            require(value["implementation"] == implementation() and value["user_instruction"] == AUTHORIZATION
                and value["latest_steering"] == STEERING, "registration_binding")
            parallel.verify_parent_seal(value)
            identifier = self.ledger.record(session, AMENDMENT, METHOD, value)
            result = {"id": identifier, **value}
            parent.atomic_json(self.ledger.root / "finish-plan.json", result)
            parent.atomic_json(self.ledger.root / "plan.json", {"id": value["plan"], **self.ledger.get(value["plan"], parent.PLAN), "finish_amendment": identifier})
            return result
        amendment = self.ledger.get(data["amendment"], AMENDMENT)
        plan = self.ledger.get(data["plan"], parent.PLAN)
        require(amendment["implementation"] == implementation() and amendment["plan"] == data["plan"]
            and amendment["deadline_epoch"] == plan["deadline_epoch"], "execution_binding")
        require(not self.config.offline or getattr(self.transport, "synthetic", False), "online_permission")
        gateway = FinishGateway(self)
        self.gateway = gateway
        runner = FinishBatch(self.ledger.root / "state.sqlite3", plan=plan, plan_id=data["plan"], engine=self,
            amendment={"id": data["amendment"], **amendment}, gateway=gateway,
            transport=self.transport or api.StandardTransport(timeout_seconds=120), clock=self.clock)
        try:
            checkpoint = lean.latest(self, parent.CHECKPOINT, data["plan"])
            require(checkpoint and parent.state_hash(runner.db) == checkpoint[1]["state_sha256"], "checkpoint_mismatch")
            runner.policy_quarantines = quarantine.load(self.ledger.db, runner.db, {"id": data["amendment"], **amendment},
                state.SelectedArtifacts(self.ledger.root), plan)
            gateway.bind(session, runner, data["plan"], amendment["protocol"], network=True)
            require(runner.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "wal_required")
            runner.initialize_finish()
            gateway.imported_counts = {r[0]: json.loads(r[1]) for r in runner.db.execute("SELECT custom_id,payload FROM counts")}
            runner.checkpoint(session, "standard_startup_ready")
            print(canonical({"phase": "execution_started", "pid": os.getpid(), "plan": data["plan"], "amendment": data["amendment"], "at": utc()}), flush=True)
            result = runner.run_finish(session, collect_only=data.get("collect_only", False), test_stop_after=data.get("test_stop_after"))
            return {"id": self.ledger.record(session, "luna_standard_finish_execution", data["amendment"], result), **result}
        finally:
            gateway.network, gateway.session = False, None
            runner.close()


class FinishMigration(Research):
    @audited_handler
    def _status(self, session, context, data):
        source, destination = Path(data["source_owner"]).resolve(), Path(data["destination"]).resolve()
        require(not destination.exists() and source != self.ledger.root and destination != self.ledger.root, "new_separate_destination")
        require(data["user_instruction"] == AUTHORIZATION and data["latest_steering"] == STEERING, "explicit_scope")
        check_permissions(source, root=True)
        require((source / "STOP").is_file(), "sealed_parent")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": implementation(), "user_instruction": AUTHORIZATION, "latest_steering": STEERING,
            "procedure": "Repair restart manifest identity by reusing immutable original manifest bindings. Pin fully preserved local reservations without any HTTP intent as permanent no-retry quarantine, leaving original rows and full costs unchanged. Preserve the failed checker and all STOP signals in the sealed parent. Add narrowly classified article error handling under explicit user instruction; preserve partial indexes and frozen membership. Preserve original queries as the reference for synthetic equivalence checks. Clone the sealed parent after matching integrity and checkpoint. Preserve all prior intents, results, costs, deadlines and STOPs. Pin and quarantine closed HTTP502 count failures without retry. Route only never-submitted frozen identities once to Standard Luna, 64 concurrent calls, persisted 2M TPM/5000 RPM ceilings lowered by observed headers, exact input plus 4096 output reservations, shared USD120 operating and USD150 hard caps. Preserve inherited successful Standard probe and pacing controls. Start Standard before collecting inherited completed Batch jobs. Preserve final Batch errors and their full unknown-cost reservations within the same cap; no retry. A fully saved HTTP400 invalid_prompt/invalid_request_error policy rejection is quarantined with unchanged validation, no retry and its full unknown billing reservation. Continue untouched articles at unchanged limits. All unclassified, ambiguous, rate-limit, count, transport or integrity failures still drain and stop. Scheduled recovery resumes only a consistent stopped checkpoint with no unresolved unclassified action or liability; never erase STOP. Retain unchanged scientific packet, parser and validation. No Codex or new Batch submissions.",
            "limits": "64 is a concurrency ceiling, not guaranteed throughput. Mechanical integrity is not semantic accuracy. Count-held articles remain incomplete. Final Batch failures remain unknown-billing liabilities."}})["id"]
        with ExitStack() as locks:
            locks.enter_context(state.StateLock(source / "workspace"))
            locks.enter_context(state.StateLock(source / "state.sqlite3"))
            journal = state.read_only_database(source)
            database = sqlite3.connect((source / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
            database.row_factory = sqlite3.Row
            locks.callback(journal.close)
            locks.callback(database.close)
            head = list(journal.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            checkpoint = state.row_value(journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (parent.CHECKPOINT,)).fetchone())
            require(parent.state_hash(database) == checkpoint["state_sha256"], "parent_checkpoint")
            report = json.loads(Path(data["integrity_report"]).read_text())
            require(report["integrity_passed"] and [report["head_seq"], report["head_hash"]] == head, "sealed_integrity")
            plan = state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone(), parent.PLAN)
            prior_row = journal.execute("SELECT * FROM records WHERE kind IN (?,?,?) ORDER BY created_event DESC LIMIT 1", (previous_finish.AMENDMENT, routes.AMENDMENT, api.AMENDMENT)).fetchone()
            prior = state.row_value(prior_row)
            require(prior["method"] == previous_v3.METHOD and prior["implementation"] == previous_v3.implementation()
                and plan["implementation"] == parent.implementation(), "parent_code_binding")
            parallel.verify_parent_seal(prior)
            exceptions = pin_parent_exceptions(database, journal, state.SelectedArtifacts(source), prior, plan)
            if data.get("batch_status"):
                status = json.loads(Path(data["batch_status"]).read_text())
            else:
                require(not database.execute("SELECT 1 FROM jobs WHERE reconciled=0").fetchone(), "batch_status_required_for_pending_jobs")
                status = {"source_owner": str(source), "source_state_unchanged": True, "all_remote_jobs_terminal": True,
                    "jobs": [], "basis": "Every inherited job is already locally reconciled; no provider calls needed."}
            require(status["source_owner"].replace("\\", "/").lower() == str(source).replace("\\", "/").lower()
                and status["source_state_unchanged"] and status["all_remote_jobs_terminal"], "batch_status_binding")
            jobs = {j["job_id"]: j for j in status["jobs"]}
            pending, members = {}, {}
            for row in database.execute("SELECT job_id,payload FROM jobs WHERE reconciled=0"):
                job, observed = json.loads(row[1]), jobs.get(row[0])
                require(observed and observed["observed_status"] == "completed" and observed["http_status"] == 200
                    and observed["request_counts"]["total"] == len(job["request_ids"])
                    and sum(observed["request_counts"][k] for k in ("completed", "failed")) == len(job["request_ids"]), "completed_batch_binding")
                pending[row[0]] = observed
                for custom in job["request_ids"]:
                    entry = json.loads(database.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()[0])
                    require(entry["status"] == "reserved", "inherited_batch_reservation")
                    members[custom] = {"job_id": row[0], "reservation": entry}
            prepare_root(destination)
            (destination / "objects").mkdir()
            child_db = sqlite3.connect(destination / "research.sqlite3")
            try:
                journal.backup(child_db)
            finally:
                child_db.close()
            with (destination / "state.sqlite3").open("xb") as stream:
                stream.write(database.serialize())
                stream.flush()
                os.fsync(stream.fileno())
            for item in (source / "objects").iterdir():
                require(item.is_file() and len(item.name) == 64, "artifact_name")
                target = destination / "objects" / item.name
                with item.open("rb") as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                with target.open("rb") as stream:
                    require(hashlib.file_digest(stream, "sha256").hexdigest() == item.name, "artifact_hash")
            amendment = {"method": METHOD, "plan": data["plan"], "implementation": implementation(),
                "user_instruction": AUTHORIZATION, "latest_steering": STEERING, "parent_owner": str(source), "parent_head": head,
                "parent_amendment": prior["_record_id"], "parent_state_sha256": checkpoint["state_sha256"],
                "parent_integrity": report, "deadline_epoch": plan["deadline_epoch"], "tpm": api.TPM, "rpm": api.RPM,
                "max_workers": 64, "hard_cap_usd": 150, "operating_cap_usd": 120, "price_policy": api.standard_price(plan),
                "recovery_authorization": RECOVERY_AUTHORIZATION, "error_policy": quarantine.REASON, "completed_batch_jobs": pending, "pending_batch_members": members, "batch_status": status,
                "protocol": protocol, "prepared_at": utc(), **exceptions}
            child = FinishResearch(destination)
            try:
                result = child.execute("status", {"phase": "register", "amendment": amendment},
                    objective="Register user-approved Standard-only continuation and preserve all liabilities", actor=context.actor)
            finally:
                child.close()
        return {"id": self.ledger.record(session, "luna_standard_finish_migration", str(destination), result), "amendment": result["id"], "destination": str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("migrate", "run", "collect"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--integrity-report", type=Path)
    parser.add_argument("--batch-status", type=Path)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--amendment")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if args.phase != "migrate" and (not args.amendment or not args.allow_paid_execution):
        parser.error("Exact amendment and explicit execution flag required")
    print(canonical({"phase": "startup_preflight", "pid": os.getpid(), "workspace": str(args.workspace), "at": utc()}), flush=True)
    engine = FinishMigration(args.workspace) if args.phase == "migrate" else FinishResearch(args.workspace, config=Config(offline=False))
    try:
        data = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        data.update(user_instruction=AUTHORIZATION, latest_steering=STEERING, collect_only=args.phase == "collect")
        print(canonical(engine.execute("status", data, objective="Finish pending Batch outputs and process untouched articles on Standard Luna", actor="codex:luna-standard-finish")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
