"""Audited Standard Responses continuation, collecting existing Batch jobs.

Only untouched identities are eligible. The frozen prompts, no-retry rule,
shared caps, deadline and all historical liabilities remain unchanged.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import urllib.error
import urllib.request

from newsresearch import event_batch_transport as http
from newsresearch.common import AuditError, Config, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions, prepare_root

import luna_batch_parallel as parallel
from luna_batch_results import _loads

parent, batch, lean, state = parallel.parent, parallel.parent.batch, parallel.parent.lean, parallel.parent.state
canonical, digest = parent.canonical, parent.digest
METHOD = "luna-standard-api-two-million-tpm-v1"
AMENDMENT = "luna_standard_api_amendment"
RESULT = "luna_standard_api_result_bundle"
AUTHORIZATION = "Should be 2m per minute. Fix"
ROUTE = {"method": "POST", "path": "/v1/responses"}
TPM, RPM, WORKERS = 2_000_000, 5_000, 64


def require(value, code):
    if not value:
        raise AuditError("standard_api_" + code)


def implementation():
    return {**parallel.implementation(), "scripts/luna_standard_api.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def standard_price(plan):
    return {**plan["budget_config"]["price_policy"], "batch_multiplier": [1, 1]}


def prepare_standard(body, identifier):
    require(isinstance(body, bytes) and http._ID.fullmatch(identifier), "invalid_wire")
    value = http._object(body)
    http.count_request_body(value)
    require(value.get("max_output_tokens") == 4096 and not value.get("tools")
        and not value.get("stream") and not value.get("background")
        and value.get("service_tier", "auto") in ("auto", "default"), "standard_request_contract")
    # Service selection is the sole wire-level addition; frozen scientific input
    # and its hash remain unchanged and are retained alongside the wire hash.
    wire_body = canonical({**value, "service_tier": "default"}).encode()
    return http.PreparedBatchRequest("POST", http.ORIGIN + ROUTE["path"], wire_body,
        {"Content-Type": "application/json", "X-Client-Request-Id": identifier})


class StandardTransport(http.OpenAIBatchTransport):
    def perform(self, request, body, client_request_id):
        if request != ROUTE:
            return super().perform(request, body, client_request_id)
        prepared = prepare_standard(body, client_request_id)
        require(not any(os.environ.get(name) for name in http._OVERRIDES), "environment_override_forbidden")
        key = os.environ.get("OPENAI_API_KEY")
        require(key and key.strip() == key and "\r" not in key and "\n" not in key, "key_unavailable")
        wire = urllib.request.Request(prepared.url, data=prepared.body, method="POST",
            headers={**prepared.headers, "Authorization": "Bearer " + key})
        opener = self._opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), http.NoBatchRedirect())
        try:
            response = opener.open(wire, timeout=self.timeout_seconds)
        except urllib.error.HTTPError as error:
            response = error
        except Exception as error:
            return http.BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)
        status = getattr(response, "status", None) or getattr(response, "code", None)
        headers = {}
        try:
            headers = {str(k).lower(): str(v) for k, v in response.headers.items()
                if str(k).lower() in http._SAFE_HEADERS or str(k).lower().startswith("x-ratelimit-")}
            require_no_credentials(headers)
            raw = response.read(self.max_response_bytes + 1)
            require(len(raw) <= self.max_response_bytes, "response_byte_limit")
            http._safe_raw(raw)
            return http.BatchReceipt(raw, status, headers.get("x-request-id"), headers,
                "http_error" if status != 200 else None, status is None or status >= 500,
                body_sha256=hashlib.sha256(raw).hexdigest())
        except Exception as error:
            return http.BatchReceipt(None, status, headers.get("x-request-id"), headers,
                type(error).__name__, True, "response_read_or_retention_failed")
        finally:
            response.close()


def parse_standard(task, body, receipt, snapshot):
    malformed = False
    try:
        value = _loads(receipt.body) if receipt.body is not None else None
    except (ValueError, UnicodeError, TypeError):
        value, malformed = None, True
    # An explicitly derived adapter envelope lets the unchanged Batch parser
    # validate Standard's original Responses body; it is not a provider file.
    envelope = {"custom_id": task["custom_id"], "error": None if receipt.status == 200 else {"type": receipt.error_type},
        "response": {"status_code": receipt.status, "request_id": receipt.request_id, "body": value}}
    parser_task = {"body": body, "packet": batch.packet_from_prompt(body, task["descriptor"], snapshot),
        "source_refs": task["descriptor"]["source_locator"], "request_ref": task["request_body_ref"],
        "packet_ref": task["descriptor"]["packet_sha256"]}
    if receipt.body is None or malformed:
        parsed = batch.parse_batch_results_phase_aware(None, None, {task["custom_id"]: parser_task})["items"][0]
        if malformed:
            parsed["errors"] = ["standard:malformed_response"]
    else:
        parsed = batch.parse_batch_results_phase_aware((canonical(envelope) + "\n").encode(), None,
            {task["custom_id"]: parser_task})["items"][0]
    return parsed, envelope


def settle_standard(plan, entry, parsed, envelope):
    value = json.loads(canonical(entry))
    status, charged, reserved = "unknown", 0, value["reserved_nanousd"]
    usage = parsed.get("usage")
    if parsed.get("usage_complete") is True and usage is not None:
        amount = state.cost(standard_price(plan), usage["input_tokens"], usage["output_tokens"])
        if parsed.get("observed_model") != "gpt-6-luna":
            status = "frozen"
        elif amount > reserved:
            status, charged, reserved = "overrun", amount, 0
        elif usage["input_tokens"] != value["request"]["input_count"]["input_tokens"] or usage["output_tokens"] > 4096:
            status = "frozen"
        else:
            status, charged, reserved = "settled", amount, 0
    value.update(status=status, charged_nanousd=charged, reserved_nanousd=reserved, settlement=usage)
    item = {**parsed, "lean_new_result": True, "processing_route": "standard_responses",
        "lean_qualifying_truncation": batch.qualifying_truncation(parsed, envelope) and status == "settled"}
    return item, value


class StandardGateway(parallel.PackingGateway):
    def prepare_standard(self, manifest, task, body, action):
        self.assert_active()
        require(self.network and not self.stopped and action not in self.handles and action not in self.old_actions,
            "duplicate_or_disabled_permit")
        binding = self.retain_manifest(manifest)
        self.runner.validate_standard(task, body, action)
        wire = prepare_standard(body, action)
        attempt = self.runner.db.execute("SELECT intended_epoch,rate_tokens FROM standard_attempts WHERE action_id=?", (action,)).fetchone()
        member = {"action_id": action, "request": ROUTE, "standard_custom_id": task["custom_id"],
            "body_sha256": hashlib.sha256(body).hexdigest(), "body_ref": self.engine.ledger.artifacts.put_bytes(body),
            "method": wire.method, "url": wire.url, "headers_excluding_authentication": wire.headers,
            "wire_body_sha256": hashlib.sha256(wire.body).hexdigest(), "admission": True,
            "standard_rate": {"epoch": attempt[0], "tokens": attempt[1], **self.runner.control()}}
        reference = self.engine.ledger.record(self.session, lean.INTENT, digest([action]), {
            "baseline": self.baseline, "protocol": self.protocol, "manifest": binding["record_id"],
            "members": [member], "intended_at": utc()})
        handle = lean.PreparedAction(action, canonical(ROUTE), body, True, reference)
        self.handles[action] = handle
        return handle


class StandardBatch(parallel.PackingBatch):
    def __init__(self, *args, **kwargs):
        self.standard_futures = {}
        super().__init__(*args, **kwargs)

    def initialize_standard(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS standard_attempts(
            custom_id TEXT PRIMARY KEY, action_id TEXT UNIQUE NOT NULL,
            intended_epoch REAL NOT NULL, rate_tokens INTEGER NOT NULL, status TEXT NOT NULL)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS standard_control(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        self.db.execute("CREATE INDEX IF NOT EXISTS standard_rate_time ON standard_attempts(intended_epoch)")
        for key, value in {"tpm": TPM, "rpm": RPM, "next_admission": 0, "probe_complete": False}.items():
            self.db.execute("INSERT OR IGNORE INTO standard_control VALUES(?,?)", (key, canonical(value)))

    def control(self):
        return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT * FROM standard_control")}

    def update_control(self, key, value):
        self.db.execute("UPDATE standard_control SET value=? WHERE key=?", (canonical(value), key))

    def rate_ready(self, tokens):
        values, now = self.control(), self.clock()
        if tokens > values["tpm"]:
            self.stop_reason = "single_request_exceeds_observed_tpm"
            return False
        count, used = self.db.execute("SELECT COUNT(*),COALESCE(SUM(rate_tokens),0) FROM standard_attempts WHERE intended_epoch>?", (now - 60,)).fetchone()
        return (now >= values["next_admission"] and count < values["rpm"] and used + tokens <= values["tpm"])

    def validate_standard(self, task, raw, action):
        self.admission_checks()
        require(self.clock() < self.meta["deadline_epoch"], "deadline")
        require(self.allowed.get(task["custom_id"]) == task["descriptor"]
            and digest(json.loads(raw)) == task["request_body_ref"], "packet_binding")
        row = self.db.execute("SELECT * FROM requests WHERE custom_id=?", (task["custom_id"],)).fetchone()
        count = self.db.execute("SELECT * FROM counts WHERE custom_id=?", (task["custom_id"],)).fetchone()
        intent = self.db.execute("SELECT * FROM standard_attempts WHERE custom_id=?", (task["custom_id"],)).fetchone()
        entry = self.db.execute("SELECT * FROM budget_entries WHERE custom_id=?", (task["custom_id"],)).fetchone()
        require(row and row["submitted"] == 1 and row["status"] == "standard_inflight" and count and intent
            and intent["action_id"] == action and intent["status"] == "intended" and entry, "missing_reservation")
        evidence, cost = json.loads(count["payload"]), json.loads(entry["payload"])
        require(evidence["input_tokens"] == count["input_tokens"] and evidence["request_body_ref"] == task["request_body_ref"]
            and evidence["corpus_id"] == task["corpus_id"]
            and self.gateway.imported_counts.get(task["custom_id"]) == evidence
            and cost["processing_route"] == "standard_responses"
            and cost["request"]["request_sha256"] == task["request_body_ref"]
            and cost["request"]["input_count"]["input_tokens"] == count["input_tokens"]
            and entry["status"] == "reserved" and entry["charged_nanousd"] == 0
            and cost["reserved_nanousd"] == entry["reserved_nanousd"]
            == state.cost(standard_price(self.plan), count["input_tokens"], 4096), "count_or_budget_binding")
        require(self.totals()["committed_nanousd"] <= state.OPERATING_CAP, "budget")
        count_recent, tokens_recent = self.db.execute("SELECT COUNT(*),SUM(rate_tokens) FROM standard_attempts WHERE intended_epoch>?", (intent["intended_epoch"] - 60,)).fetchone()
        require(count_recent <= self.control()["rpm"] <= RPM and tokens_recent <= self.control()["tpm"] <= TPM,
            "rate_reservation")

    def start_standard(self, pool, manifest, task, body):
        self.admission_checks()
        custom = task["custom_id"]
        require(self.clock() < self.meta["deadline_epoch"], "deadline")
        row = self.db.execute("SELECT submitted,status FROM requests WHERE custom_id=?", (custom,)).fetchone()
        count = self.db.execute("SELECT input_tokens,payload FROM counts WHERE custom_id=?", (custom,)).fetchone()
        require(row and not row[0] and row[1] == "logged" and count, "identity_not_untouched")
        require(not self.db.execute("SELECT 1 FROM budget_entries WHERE custom_id=?", (custom,)).fetchone(), "prior_cost_intent")
        evidence = json.loads(count[1])
        require(evidence["request_body_ref"] == task["request_body_ref"] and evidence["input_tokens"] == count[0], "count_binding")
        tokens = count[0] + 4096
        if not self.rate_ready(tokens):
            return "rate"
        amount = state.cost(standard_price(self.plan), count[0], 4096)
        if self.totals()["committed_nanousd"] + amount > state.OPERATING_CAP:
            return "budget"
        raw = canonical(body).encode()
        action = digest([METHOD, self.plan_id, custom, "standard_once"])
        entry = {"processing_route": "standard_responses", "price_policy": standard_price(self.plan),
            "status": "reserved", "charged_nanousd": 0, "reserved_nanousd": amount,
            "request": {"request_id": custom, "task_id": custom, "corpus_id": task["corpus_id"],
                "plan_id": self.meta["plan_id"], "request_sha256": task["request_body_ref"], "max_output_tokens": 4096,
                "input_count": {"input_tokens": count[0], "request_sha256": task["request_body_ref"], "model": "gpt-6-luna"}}}
        with batch.transaction(self.db):
            self.db.execute("INSERT INTO budget_entries VALUES(?, 'reserved',0,?,?)", (custom, amount, canonical(entry)))
            self.db.execute("UPDATE requests SET submitted=1,status='standard_inflight' WHERE custom_id=?", (custom,))
            self.db.execute("INSERT INTO standard_attempts VALUES(?,?,?,?, 'intended')", (custom, action, self.clock(), tokens))
            self.update_control("next_admission", self.clock() + max(60 * tokens / self.control()["tpm"], 60 / self.control()["rpm"]))
        handle = self.gateway.prepare_standard(manifest, task, raw, action)
        self.standard_futures[pool.submit(self.gateway.perform_prepared, handle)] = (manifest, task, body, entry)
        return None

    def pump_standard(self):
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
                parsed, envelope = parse_standard(task, body, receipt, self.snapshot)
                item, cost = settle_standard(self.plan, entry, parsed, envelope)
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
                else:
                    self.stop_reason = "standard_result_requires_review"
        self.engine.ledger.record(self.gateway.session, RESULT, digest([row["action_id"] for row in saved]), {
            "method": METHOD, "plan": self.plan_id, "amendment": self.amendment["id"],
            "items": saved, "saved_at": utc(), "semantic_accuracy_confirmed": False})
        if self.gateway.stopped:
            self.stop_reason = self.stop_reason or "standard_http_failure_no_retry"
        self.prune_completed()

    def prune_completed(self):
        # Keep durable identities, release large completed wire/response buffers.
        for action in list(self.gateway.retained):
            self.gateway.old_actions.add(action)
            self.gateway.handles.pop(action, None)
            self.gateway.receipts.pop(action, None)
            self.prepared_actions.pop(action, None)
            self.gateway.retained.discard(action)
            self.gateway.used.discard(action)

    def summary(self):
        value = super().summary()
        exists = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='standard_attempts'").fetchone()
        if exists:
            sent, saved = self.db.execute("SELECT COUNT(*),COALESCE(SUM(status='saved'),0) FROM standard_attempts").fetchone()
            value.update(standard_submitted=sent, standard_saved=saved, standard_inflight=sent - saved,
                standard_control=self.control(), standard_worker_ceiling=WORKERS,
                standard_rate_basis="Persisted rolling 60-second input count plus 4096 output-token reservations; paced admissions. Published ceiling, lowered by observed response headers. Not measured throughput.")
        return value

    def run_standard(self, session, *, collect_only=False, test_stop_after=None):
        self.require_runtime()
        self.allow_network = True
        self.admission_checks()
        require(not self.db.execute("SELECT 1 FROM standard_attempts WHERE status!='saved'").fetchone(), "prior_intent_requires_reconciliation")
        require(not self.db.execute("SELECT 1 FROM actions WHERE status!='complete'").fetchone(), "prior_http_action")
        waiting, tasks, bodies, next_poll, last_checkpoint = None, [], {}, 0, self.clock()
        admitted, pressure = 0, None
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            def tick():
                self.pump_standard()
                self.progress("standard_running")
            try:
                while True:
                    tick()
                    if (self.database.parent / "STOP").exists():
                        self.stop_reason = "user_stop"
                        self.gateway.stopped = True
                    if self.stop_reason:
                        break
                    if self.clock() >= next_poll:
                        self.collect()
                        next_poll = self.clock() + 30
                    if self.stop_reason:
                        break
                    admission = not collect_only and self.clock() < self.meta["deadline_epoch"]
                    width = WORKERS if self.control()["probe_complete"] else 1
                    if admission and len(self.standard_futures) < width:
                        if waiting is None:
                            waiting = self.log_next()
                            if waiting is not None:
                                self.progress("standard_counting", force=True)
                                self.count_file(waiting, tick)
                                self.gateway.imported_counts.update({r[0]: json.loads(r[1]) for r in self.db.execute("SELECT custom_id,payload FROM counts WHERE custom_id IN (SELECT custom_id FROM requests WHERE manifest_id=?)", (waiting["id"],))})
                                self.prune_completed()
                                tasks = [t for t in waiting["tasks"] if self.db.execute("SELECT status FROM requests WHERE custom_id=?", (t["custom_id"],)).fetchone()[0] == "logged"]
                                bodies = {r["custom_id"]: r["body"] for r in map(json.loads, self.raw(waiting).splitlines())}
                        if waiting is not None and tasks:
                            pressure = self.start_standard(pool, waiting, tasks[0], bodies[tasks[0]["custom_id"]])
                            if pressure is None:
                                tasks.pop(0)
                                admitted += 1
                                if not tasks:
                                    waiting = None
                                if test_stop_after and admitted >= test_stop_after:
                                    self.stop_reason = "test_bounded_stop"
                                    break
                    if self.clock() - last_checkpoint >= 600:
                        self.checkpoint(session, "standard_periodic")
                        last_checkpoint = self.clock()
                    pending = self.db.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone()
                    if not self.standard_futures and not pending and (not admission or waiting is None or pressure == "budget"):
                        self.stop_reason = "deadline_or_collect_complete" if not admission else "budget" if pressure == "budget" else "queue_exhausted"
                        break
                    self.progress("standard_rate_wait" if pressure == "rate" else "standard_running")
                    time.sleep(0.025)
            finally:
                # Retain every launched response even after STOP/failure.
                while self.standard_futures:
                    self.pump_standard()
                    if self.standard_futures:
                        time.sleep(0.05)
                self.checkpoint(session, self.stop_reason or "standard_exception")
        return {"reason": self.stop_reason, **self.summary()}


class StandardResearch(parent.RemainderResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "register":
            value = data["amendment"]
            require(value["implementation"] == implementation() and value["authorization_text"] == AUTHORIZATION, "registration_binding")
            parallel.verify_parent_seal(value)
            identifier = self.ledger.record(session, AMENDMENT, METHOD, value)
            result = {"id": identifier, **value}
            parent.atomic_json(self.ledger.root / "standard-api-plan.json", result)
            plan = self.ledger.get(value["plan"], parent.PLAN)
            parent.atomic_json(self.ledger.root / "plan.json", {"id": value["plan"], **plan, "standard_api_amendment": identifier})
            return result
        amendment = self.ledger.get(data["amendment"], AMENDMENT)
        plan = self.ledger.get(data["plan"], parent.PLAN)
        require(amendment["implementation"] == implementation() and amendment["plan"] == data["plan"]
            and amendment["authorization_text"] == AUTHORIZATION and amendment["deadline_epoch"] == plan["deadline_epoch"], "execution_binding")
        require(not self.config.offline or getattr(self.transport, "synthetic", False) is True, "online_permission")
        gateway = StandardGateway(self)
        self.gateway = gateway
        runner = StandardBatch(self.ledger.root / "state.sqlite3", plan=plan, plan_id=data["plan"], engine=self,
            amendment={"id": data["amendment"], **amendment}, gateway=gateway,
            transport=self.transport or StandardTransport(timeout_seconds=120), clock=self.clock)
        try:
            checkpoint = lean.latest(self, parent.CHECKPOINT, data["plan"])
            require(checkpoint and parent.state_hash(runner.db) == checkpoint[1]["state_sha256"], "checkpoint_mismatch")
            gateway.bind(session, runner, data["plan"], amendment["protocol"], network=True)
            require(runner.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "wal_required")
            runner.initialize_standard()
            gateway.imported_counts = {r[0]: json.loads(r[1]) for r in runner.db.execute("SELECT custom_id,payload FROM counts")}
            runner.checkpoint(session, "standard_startup_ready")
            print(canonical({"phase": "execution_started", "pid": os.getpid(), "plan": data["plan"], "amendment": data["amendment"], "at": utc()}), flush=True)
            result = runner.run_standard(session, collect_only=data.get("collect_only", False), test_stop_after=data.get("test_stop_after"))
            identifier = self.ledger.record(session, "luna_standard_api_execution", data["amendment"], result)
            return {"id": identifier, **result}
        finally:
            gateway.network = False
            gateway.session = None
            runner.close()


class StandardMigration(Research):
    method = METHOD
    authorization = AUTHORIZATION
    code_binding = staticmethod(implementation)
    child_class = StandardResearch

    def extra_amendment(self, data):
        return {}

    @audited_handler
    def _status(self, session, context, data):
        source, destination = Path(data["source_owner"]).resolve(), Path(data["destination"]).resolve()
        require(data["authorization_text"] == self.authorization and not destination.exists(), "new_destination_and_permission")
        require(source != self.ledger.root and destination != self.ledger.root, "separate_owner")
        check_permissions(source, root=True)
        require((source / "STOP").exists(), "sealed_parent_required")
        protocol = self._version(session, context, {"kind": "protocol", "key": self.method, "content": {
            "method": self.method, "implementation": self.code_binding(),
            "continuation": self.extra_amendment(data),
            "procedure": "Preserve all prior Batch/Codex identities, journal, costs and deadline in a sealed-parent child. Collect accepted Batch jobs unchanged. Send only never-submitted frozen full-text articles once to Standard Responses via audited gateway. Preserve exact prompts and raw/phase-aware validators. Reserve Standard pricing at twice Batch's bound rates within the unchanged shared USD120 operating and USD150 hard caps. Persist 2M TPM rolling input-plus-max-output reservations and paced admission deadlines; start with one real untouched-article probe, then at most 64 concurrent calls, lowering limits from observed response headers. Never retry any prior count/article/write intent. Retain/drain all calls on failure or STOP.",
            "limits": "Published TPM is admission capacity, not promised throughput or project-specific entitlement. No semantic-accuracy claim. Unknowns keep reservations and stop admission.",
            "sources": ["https://developers.openai.com/api/docs/models/gpt-6-luna", "https://developers.openai.com/api/docs/guides/rate-limits"]}})["id"]
        with ExitStack() as locks:
            locks.enter_context(state.StateLock(source / "workspace"))
            locks.enter_context(state.StateLock(source / "state.sqlite3"))
            journal = state.read_only_database(source)
            database = sqlite3.connect((source / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
            locks.callback(journal.close)
            locks.callback(database.close)
            head = list(journal.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            checkpoint = state.row_value(journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (parent.CHECKPOINT,)).fetchone())
            require(parent.state_hash(database) == checkpoint["state_sha256"], "parent_checkpoint")
            report = json.loads(Path(data["integrity_report"]).read_text())
            require(report["integrity_passed"] and [report["head_seq"], report["head_hash"]] == head, "sealed_integrity")
            plan = state.row_value(journal.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone(), parent.PLAN)
            prior = state.row_value(journal.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (parallel.AMENDMENT,)).fetchone(), parallel.AMENDMENT)
            require(prior["implementation"] == parallel.implementation() and plan["implementation"] == parent.implementation(), "parent_code_binding")
            parallel.verify_parent_seal(prior)
            require(not database.execute("SELECT 1 FROM actions WHERE status!='complete'").fetchone(), "prior_http_hold")
            require(not database.execute("SELECT 1 FROM requests WHERE status IN ('admitted','creating','unknown_create')").fetchone(), "prior_admission_hold")
            prepare_root(destination)
            (destination / "objects").mkdir()
            child_db = sqlite3.connect(destination / "research.sqlite3")
            try:
                journal.backup(child_db)
            finally:
                child_db.close()
            with (destination / "state.sqlite3").open("xb") as output:
                output.write(database.serialize())
                output.flush()
                os.fsync(output.fileno())
            for item in (source / "objects").iterdir():
                require(item.is_file() and len(item.name) == 64, "artifact_name")
                target = destination / "objects" / item.name
                with item.open("rb") as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                with target.open("rb") as stream:
                    require(hashlib.file_digest(stream, "sha256").hexdigest() == item.name, "artifact_hash")
            amendment = {"method": self.method, "plan": data["plan"], "implementation": self.code_binding(),
                "authorization_text": self.authorization, "parent_owner": str(source), "parent_head": head,
                "parent_amendment": prior["_record_id"], "parent_state_sha256": checkpoint["state_sha256"],
                "deadline_epoch": plan["deadline_epoch"], "tpm": TPM, "rpm": RPM, "max_workers": WORKERS,
                "hard_cap_usd": 150, "operating_cap_usd": 120, "price_policy": standard_price(plan),
                "protocol": protocol, "prepared_at": utc(), **self.extra_amendment(data)}
            child = self.child_class(destination)
            try:
                result = child.execute("status", {"phase": "register", "amendment": amendment},
                    objective="Register Standard API continuation under the same global caps", actor=context.actor)
            finally:
                child.close()
        return self.ledger.record(session, "luna_standard_api_migration", str(destination), result)


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
    engine = StandardMigration(args.workspace) if args.phase == "migrate" else StandardResearch(args.workspace, config=Config(offline=False))
    try:
        data = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        data["collect_only"] = args.phase == "collect"
        print(canonical(engine.execute("status", data, objective="Use Standard API capacity for untouched articles within the shared budget", actor="codex:luna-standard-api")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
