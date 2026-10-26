"""One audited writer for five Codex workers, API Batch and Standard Responses."""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

from newsresearch.common import AuditError, Config, require_no_credentials, utc
from newsresearch.event_extraction_workflow import save
from newsresearch.gateway import ProviderResponse
from newsresearch.luna_fast_gateway import clean_return
from newsresearch.luna_standard_provider import StandardProvider
from newsresearch.luna_speed_provider import validate_response
from newsresearch.runtime import audited_handler

import luna_standard_api as api
from luna_batch_literal_projection import project_literal_refs
from luna_standard_recovery import capacity_failure

parent, parallel, batch, lean, state, http = api.parent, api.parallel, api.batch, api.lean, api.state, api.http
canonical, digest = api.canonical, api.digest
METHOD = "luna-three-route-parallel-v1"
AMENDMENT = "luna_all_routes_amendment"
CODEX_INTENT = "luna_all_routes_codex_intent"
CODEX_RESULT = "luna_all_routes_codex_result"
ASSIGNMENT = "luna_all_routes_assignment"
AUTHORIZATION = "Do them all in parralel, 5 luna codex, batch, and processing luna via api"
CODEX_WORKERS = 5
ROUTE_SIZES = {"codex": 100, "standard": 250, "batch": 1000}
ROOT = Path(__file__).resolve().parents[1]


def require(value, code):
    if not value:
        raise AuditError("all_routes_" + code)


def implementation():
    paths = [Path(__file__), ROOT / "src/newsresearch/gateway.py",
        ROOT / "src/newsresearch/codex_provider.py", ROOT / "src/newsresearch/luna_speed_provider.py",
        ROOT / "src/newsresearch/luna_standard_provider.py", ROOT / "src/newsresearch/luna_fast_gateway.py",
        ROOT / "scripts/luna_standard_recovery.py", ROOT / "scripts/luna_batch_literal_projection.py",
        ROOT / "prompts/luna_event_v2_execution_notes.txt"]
    return {**api.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


class PrivateKeyTransport(http.OpenAIBatchTransport):
    """API key stays in this transport, absent from every Codex child environment."""
    def __init__(self, key, **kwargs):
        super().__init__(**kwargs)
        require(isinstance(key, str) and key and key.strip() == key and "\n" not in key and "\r" not in key,
            "api_key_unavailable")
        self._api_key = key

    def perform(self, request, body, client_request_id):
        prepared = api.prepare_standard(body, client_request_id) if request == api.ROUTE else http.prepare_request(request, body, client_request_id)
        require(not any(os.environ.get(name) for name in http._OVERRIDES), "endpoint_override")
        wire = urllib.request.Request(prepared.url, data=prepared.body, method=prepared.method,
            headers={**prepared.headers, "Authorization": "Bearer " + self._api_key})
        opener = self._opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), http.NoBatchRedirect())
        mutation = prepared.method == "POST" and request != batch.COUNT_ROUTE
        limit = self.max_download_bytes if request["path"].endswith("/content") else self.max_response_bytes
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
            raw = response.read(limit + 1)
            require(len(raw) <= limit, "response_byte_limit")
            http._safe_raw(raw)
            return http.BatchReceipt(raw, status, headers.get("x-request-id"), headers,
                "http_error" if status is None or not 200 <= status < 300 else None,
                mutation and (status is None or status >= 500), body_sha256=hashlib.sha256(raw).hexdigest())
        except Exception as error:
            return http.BatchReceipt(None, status, headers.get("x-request-id"), headers,
                type(error).__name__, True, "response_read_or_retention_failed")
        finally:
            response.close()


def assess_codex(custom, packet, response):
    errors = validate_response(response, packet)
    raw = response.raw_response or {}
    status = "not_dispatched" if raw.get("dispatched") is False else "unknown" if raw.get("unknown_outcome") else "invalid" if errors else "valid"
    projection = project_literal_refs(response.payload, packet,
        response_status="completed" if not any(e.startswith("response:") for e in errors) else None)
    derived = "valid" if projection["valid"] else status if status in {"unknown", "not_dispatched"} else "invalid"
    return {"custom_id": custom, "raw_status": status, "status": derived, "errors": errors,
        "projection": projection, "usage": response.usage, "observed_model": response.model,
        "observed_service_tiers": raw.get("observed_service_tiers", []),
        "technical_failure": not clean_return(response), "processing_route": "codex",
        "lean_new_result": False, "all_routes_new_result": True, "accepted": False, "human_validated": False}


class CombinedGateway(api.StandardGateway):
    def codex_once(self, provider, invocation, attempt):
        # The inherited shared gateway checks durable request/dispatch bindings.
        # Only the coordinator creates them and saves the response.
        return list(self.codex_dispatch(self.session, provider, [(invocation, attempt)], workers=1))[0][1]


class CombinedBatch(api.StandardBatch):
    def __init__(self, *args, codex_provider, **kwargs):
        self.codex_provider, self.codex_futures = codex_provider, {}
        self.ready = {"standard": None, "codex": None, "batch": None}
        self.route_cursor = {route: 0 for route in ROUTE_SIZES}
        self.available = {}
        super().__init__(*args, **kwargs)

    def initialize_routes(self):
        self.initialize_standard()
        self.db.execute("CREATE TABLE IF NOT EXISTS route_assignments(manifest_id TEXT PRIMARY KEY,route TEXT NOT NULL)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS codex_attempts(
            custom_id TEXT PRIMARY KEY,attempt TEXT UNIQUE NOT NULL,intended_epoch REAL NOT NULL,status TEXT NOT NULL)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS codex_control(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        for key, value in {"paused": None, "resume_not_before": 0, "capacity_streak": 0, "probe": False}.items():
            self.db.execute("INSERT OR IGNORE INTO codex_control VALUES(?,?)", (key, canonical(value)))
        known = {r[0] for r in self.db.execute("SELECT custom_id FROM requests")}
        self.available = {k: deque(d for d in rows if d["custom_id"] not in known) for k, rows in self.queues.items()}
        # Every previously logged Batch file keeps its route and prior counts.
        for row in self.db.execute("""SELECT m.payload FROM manifests m WHERE json_extract(m.payload,'$.remainder_plan')=?
            AND EXISTS(SELECT 1 FROM requests r WHERE r.manifest_id=m.id AND r.status='logged')
            AND NOT EXISTS(SELECT 1 FROM route_assignments a WHERE a.manifest_id=m.id)""", (self.plan_id,)).fetchall():
            self.assign(json.loads(row[0]), "batch", "Inherited never-submitted Batch preparation")

    def codex_control(self):
        return {r[0]: json.loads(r[1]) for r in self.db.execute("SELECT * FROM codex_control")}

    def set_codex(self, key, value):
        self.db.execute("UPDATE codex_control SET value=? WHERE key=?", (canonical(value), key))

    def assign(self, manifest, route, reason):
        require(route in ROUTE_SIZES, "unknown_route")
        binding = self.gateway.retain_manifest(manifest)
        self.engine.ledger.record(self.gateway.session, ASSIGNMENT, manifest["id"], {
            "plan": self.plan_id, "amendment": self.amendment["id"], "manifest": binding["record_id"],
            "route": route, "reason": reason, "at": utc()})
        self.db.execute("INSERT INTO route_assignments VALUES(?,?)", (manifest["id"], route))

    def log_route(self, route):
        self.require_runtime()
        existing = self.db.execute("""SELECT m.payload FROM manifests m JOIN route_assignments a ON a.manifest_id=m.id
            WHERE a.route=? AND EXISTS(SELECT 1 FROM requests r WHERE r.manifest_id=m.id AND r.status='logged')
            ORDER BY m.rowid LIMIT 1""", (route,)).fetchone()
        if existing:
            return json.loads(existing[0])
        corpora = list(self.available)
        selected, corpus, size = [], None, 0
        for offset in range(len(corpora)):
            index = (self.route_cursor[route] + offset) % len(corpora)
            candidate = corpora[index]
            if self.available[candidate]:
                corpus = candidate
                self.route_cursor[route] = (index + 1) % len(corpora)
                break
        if corpus is None:
            return None
        while self.available[corpus] and len(selected) < ROUTE_SIZES[route]:
            descriptor = self.available[corpus][0]
            if selected and size + descriptor["line_bytes"] > batch.MAX_BYTES:
                break
            selected.append(self.available[corpus].popleft())
            size += descriptor["line_bytes"]
        records = self.materialize(selected, self.meta["corpora"][corpus]["partition"])
        manifest = {**batch.prompt_file(self.database.parent, corpus, records, self.snapshot), "remainder_plan": self.plan_id}
        with batch.transaction(self.db):
            for task in manifest["tasks"]:
                require(self.allowed.get(task["custom_id"]) == task["descriptor"], "foreign_identity")
                value = {**task, "manifest_id": manifest["id"], "submitted": False}
                self.db.execute("INSERT INTO requests VALUES(?,?,?,0,'logged',?)",
                    (task["custom_id"], corpus, manifest["id"], canonical(value)))
            self.db.execute("INSERT INTO manifests VALUES(?,?,?)", (manifest["id"], corpus, canonical(manifest)))
        self.assign(manifest, route, "Disjoint untouched identities claimed by one writer")
        print(canonical({"phase": "route_prepared", "route": route, "corpus": corpus, "articles": len(selected)}), flush=True)
        return manifest

    def load_ready(self, route, tick):
        manifest = self.log_route(route)
        if manifest is None:
            return None
        if route != "codex":
            self.progress(route + "_counting", force=True)
            self.count_file(manifest, tick)
            self.gateway.imported_counts.update({r[0]: json.loads(r[1]) for r in self.db.execute(
                "SELECT custom_id,payload FROM counts WHERE custom_id IN (SELECT custom_id FROM requests WHERE manifest_id=?)", (manifest["id"],))})
        tasks = deque(t for t in manifest["tasks"] if self.db.execute("SELECT status FROM requests WHERE custom_id=?", (t["custom_id"],)).fetchone()[0] == "logged")
        bodies = {r["custom_id"]: r["body"] for r in map(json.loads, self.raw(manifest).splitlines())}
        self.ready[route] = (manifest, tasks, bodies)
        return self.ready[route]

    def split_to_fit(self, manifest):
        changed = super().split_to_fit(manifest)
        if changed:
            for row in self.db.execute("SELECT payload FROM manifests WHERE json_extract(payload,'$.split_parent')=?", (manifest["split_parent"],)).fetchall():
                part = json.loads(row[0])
                if not self.db.execute("SELECT 1 FROM route_assignments WHERE manifest_id=?", (part["id"],)).fetchone():
                    self.assign(part, "batch", "Preserved Batch capacity split")
        return changed

    def start_codex(self, pool):
        control = self.codex_control()
        if control["paused"] or self.clock() < control["resume_not_before"]:
            return False
        width = 1 if control["probe"] else CODEX_WORKERS
        if len(self.codex_futures) >= width or self.ready["codex"] is None:
            return False
        require(not (self.database.parent / "STOP").exists(), "stop_before_codex")
        require(self.clock() < self.meta["deadline_epoch"], "codex_deadline")
        manifest, tasks, bodies = self.ready["codex"]
        if not tasks:
            self.ready["codex"] = None
            return False
        task = tasks[0]
        custom = task["custom_id"]
        row = self.db.execute("SELECT submitted,status FROM requests WHERE custom_id=?", (custom,)).fetchone()
        require(row and not row[0] and row[1] == "logged", "codex_identity_spent")
        require(not self.db.execute("SELECT 1 FROM budget_entries WHERE custom_id=?", (custom,)).fetchone(), "codex_api_reservation")
        packet = batch.packet_from_prompt(bodies[custom], task["descriptor"], self.snapshot)
        attempt, task_key = str(uuid.uuid4()), digest([self.amendment["id"], custom, "codex_once"])
        call = self.codex_provider.prepare(task_key, attempt, packet, timeout_seconds=180)
        request = save(self.engine, self.gateway.session, call.request, "Exact Codex request before dispatch")
        dispatch = save(self.engine, self.gateway.session, call.manifest(), "Exact Codex invocation before dispatch")
        binding = self.gateway.retain_manifest(manifest)
        intended = {"attempt": attempt, "task_key": task_key, "custom_id": custom, "corpus_id": task["corpus_id"],
            "plan": self.plan_id, "amendment": self.amendment["id"], "number": 1, "batch": self.amendment["id"],
            "request": request, "dispatch": dispatch, "manifest": binding["record_id"], "started_at": utc(),
            "source_versions": [], "body_sha256": task["descriptor"]["retained_body_sha256"],
            "source_sha256": task["descriptor"]["source_sha256"], "source_locator": task["descriptor"]["source_locator"],
            "intended_epoch": self.clock(), "codex_control": control}
        with batch.transaction(self.db):
            self.db.execute("UPDATE requests SET submitted=1,status='codex_inflight' WHERE custom_id=?", (custom,))
            self.db.execute("INSERT INTO codex_attempts VALUES(?,?,?,'intended')", (custom, attempt, self.clock()))
        self.engine.ledger.record(self.gateway.session, CODEX_INTENT, attempt, intended)
        self.engine.ledger.append(self.gateway.session, "model.attempt.intended", intended)
        self.engine.ledger.unresolved[attempt] = intended
        self.codex_futures[pool.submit(self.gateway.codex_once, self.codex_provider, call, attempt)] = (task, packet, intended)
        tasks.popleft()
        if not tasks:
            self.ready["codex"] = None
        return True

    def pump_codex(self):
        for future in [f for f in self.codex_futures if f.done()]:
            task, packet, intended = self.codex_futures.pop(future)
            try:
                response = future.result()
            except Exception as error:
                response = ProviderResponse(None, "codex-cli", None, raw_response={"unknown_outcome": True,
                    "failure": "codex_gateway_outcome_unobserved", "error_type": type(error).__name__})
            response_ref = save(self.engine, self.gateway.session, asdict(response), "Exact Codex response before validation")
            item = assess_codex(task["custom_id"], packet, response)
            # Publish immutable final results only after their operational
            # projection commits; live integrity snapshots may safely lead it.
            with batch.transaction(self.db):
                self.db.execute("INSERT INTO results VALUES(?,?,?)", (task["custom_id"], item["status"], canonical(item)))
                self.db.execute("UPDATE requests SET status=? WHERE custom_id=?", (item["status"], task["custom_id"]))
                self.db.execute("UPDATE codex_attempts SET status='saved' WHERE custom_id=?", (task["custom_id"],))
            record = self.engine.ledger.record(self.gateway.session, CODEX_RESULT, intended["attempt"], {
                "plan": self.plan_id, "amendment": self.amendment["id"], "attempt": intended["attempt"],
                "custom_id": task["custom_id"], "corpus_id": task["corpus_id"], "response": response_ref,
                "request": intended["request"], "dispatch": intended["dispatch"], "item": item, "saved_at": utc()})
            unknown = item["raw_status"] == "unknown"
            def project(event):
                self.engine.ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    intended["attempt"], intended["task_key"], self.amendment["id"], 1, intended["request"], response_ref,
                    item["raw_status"], record, item["errors"][0] if item["errors"] else None, event))
            self.engine.ledger.append(self.gateway.session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
                "attempt": intended["attempt"], "response": response_ref, "assessment": record,
                "status": item["raw_status"], "ended_at": utc()}, project)
            if not unknown:
                self.engine.ledger.unresolved.pop(intended["attempt"], None)
            with batch.transaction(self.db):
                if capacity_failure(response):
                    streak = self.codex_control()["capacity_streak"] + 1
                    self.set_codex("capacity_streak", streak)
                    self.set_codex("resume_not_before", self.clock() + (300, 900, 1800, 3600)[min(streak - 1, 3)])
                    self.set_codex("probe", True)
                elif not clean_return(response):
                    self.set_codex("paused", "codex_transport_requires_review")
                elif self.codex_control()["probe"] and not self.codex_futures and self.clock() >= self.codex_control()["resume_not_before"]:
                    self.set_codex("probe", False)
            self.engine.ledger.record(self.gateway.session, "luna_all_routes_codex_control", intended["attempt"], {
                "plan": self.plan_id, "amendment": self.amendment["id"], "control": self.codex_control(), "at": utc()})

    def summary(self):
        result = super().summary()
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='codex_attempts'").fetchone():
            sent, saved = self.db.execute("SELECT COUNT(*),COALESCE(SUM(status='saved'),0) FROM codex_attempts").fetchone()
            result.update(codex_workers=CODEX_WORKERS, codex_submitted=sent, codex_saved=saved,
                codex_inflight=sent - saved, codex_control=self.codex_control(),
                codex_saved_unknowns=self.db.execute("SELECT COUNT(*) FROM results WHERE json_extract(payload,'$.processing_route')='codex' AND json_extract(payload,'$.raw_status')='unknown'").fetchone()[0],
                amendment=self.amendment["id"], configured_codex_model="gpt-6-luna", configured_codex_fast=False)
        return result

    def run_all(self, session, *, collect_only=False, test_stop_after=None):
        self.require_runtime()
        self.allow_network = True
        self.admission_checks()
        require(not self.db.execute("SELECT 1 FROM standard_attempts WHERE status!='saved'").fetchone()
            and not self.db.execute("SELECT 1 FROM codex_attempts WHERE status!='saved'").fetchone()
            and not self.db.execute("SELECT 1 FROM actions WHERE status!='complete'").fetchone(), "prior_action_requires_reconciliation")
        started_submissions = self.summary()["new_submitted"]
        next_poll, next_batch, last_checkpoint = 0, 0, self.clock()
        api_pressure, batch_pressure = None, None
        with ThreadPoolExecutor(max_workers=api.WORKERS) as api_pool, ThreadPoolExecutor(max_workers=CODEX_WORKERS) as codex_pool, ThreadPoolExecutor(max_workers=batch.TRANSFER_WORKERS) as batch_pool:
            def tick():
                self.pump(batch_pool)
                self.pump_standard()
                self.pump_codex()
                if not self.stop_reason and not collect_only and self.clock() < self.meta["deadline_epoch"] and not (self.database.parent / "STOP").exists():
                    while self.start_codex(codex_pool):
                        pass
                self.progress("three_routes_running")
            try:
                while True:
                    tick()
                    if (self.database.parent / "STOP").exists():
                        self.stop_reason = "user_stop"
                    if self.stop_reason:
                        break
                    if self.clock() >= next_poll:
                        self.collect()
                        next_poll = self.clock() + 30
                    if self.stop_reason:
                        break
                    admission = not collect_only and self.clock() < self.meta["deadline_epoch"]
                    if admission:
                        codex_control = self.codex_control()
                        if not codex_control["paused"] and self.clock() >= codex_control["resume_not_before"] and self.ready["codex"] is None:
                            self.load_ready("codex", tick)
                        while self.start_codex(codex_pool):
                            pass
                        width = api.WORKERS if self.control()["probe_complete"] else 1
                        if len(self.standard_futures) < width:
                            if self.ready["standard"] is None:
                                self.load_ready("standard", tick)
                            if self.ready["standard"]:
                                manifest, tasks, bodies = self.ready["standard"]
                                if tasks:
                                    api_pressure = self.start_standard(api_pool, manifest, tasks[0], bodies[tasks[0]["custom_id"]])
                                    if api_pressure is None:
                                        tasks.popleft()
                                if not tasks:
                                    self.ready["standard"] = None
                        if self.clock() >= next_batch and len(self.remote) < batch.TRANSFER_WORKERS:
                            next_batch = self.clock() + 2
                            if self.ready["batch"] is None:
                                self.load_ready("batch", tick)
                            if self.ready["batch"]:
                                manifest = self.ready["batch"][0]
                                batch_pressure = self.reserve(manifest)
                                if batch_pressure is None:
                                    self.start_remote(batch_pool, "upload", manifest, {"method": "POST", "path": "/v1/files",
                                        "purpose": "batch", "filename": manifest["id"] + ".jsonl", "content_sha256": manifest["id"]}, self.raw(manifest))
                                    self.ready["batch"] = None
                    if test_stop_after and self.summary()["new_submitted"] - started_submissions >= test_stop_after:
                        self.stop_reason = "test_bounded_stop"
                        break
                    if self.clock() - last_checkpoint >= 600:
                        self.checkpoint(session, "three_routes_periodic")
                        last_checkpoint = self.clock()
                    pending = self.db.execute("SELECT 1 FROM jobs WHERE reconciled=0 LIMIT 1").fetchone()
                    busy = self.codex_futures or self.standard_futures or self.remote or pending
                    untouched = self.db.execute("SELECT COUNT(*) FROM requests WHERE submitted=0 AND custom_id IN (SELECT custom_id FROM requests WHERE manifest_id IN (SELECT manifest_id FROM route_assignments))").fetchone()[0] + sum(len(v) for v in self.available.values())
                    if not busy and (not admission or untouched == 0):
                        self.stop_reason = "queue_exhausted" if untouched == 0 else "admission_closed_collect_complete"
                        break
                    if not busy and not any(self.available.values()) and self.ready["standard"] is None and self.ready["batch"] is None and self.codex_control()["paused"]:
                        self.stop_reason = "codex_paused_with_untouched_work"
                        break
                    if not busy and api_pressure == "budget" and batch_pressure == "budget" and self.codex_control()["paused"]:
                        self.stop_reason = "budget_and_codex_paused"
                        break
                    time.sleep(0.025)
            finally:
                # No resubmission or cancellation: retain all already launched work.
                while self.codex_futures or self.standard_futures or self.remote:
                    self.pump(batch_pool)
                    self.pump_standard()
                    self.pump_codex()
                    time.sleep(0.05)
                self.checkpoint(session, self.stop_reason or "three_routes_exception")
        return {"reason": self.stop_reason, **self.summary()}


class CombinedResearch(parent.RemainderResearch):
    def __init__(self, *args, codex_provider=None, **kwargs):
        self.codex_provider = codex_provider
        super().__init__(*args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "register":
            value = data["amendment"]
            require(value["implementation"] == implementation() and value["authorization_text"] == AUTHORIZATION, "registration_binding")
            parallel.verify_parent_seal(value)
            identifier = self.ledger.record(session, AMENDMENT, METHOD, value)
            result = {"id": identifier, **value}
            parent.atomic_json(self.ledger.root / "all-routes-plan.json", result)
            plan = self.ledger.get(value["plan"], parent.PLAN)
            parent.atomic_json(self.ledger.root / "plan.json", {"id": value["plan"], **plan, "all_routes_amendment": identifier})
            return result
        amendment = self.ledger.get(data["amendment"], AMENDMENT)
        plan = self.ledger.get(data["plan"], parent.PLAN)
        require(amendment["implementation"] == implementation() and amendment["plan"] == data["plan"]
            and amendment["authorization_text"] == AUTHORIZATION and amendment["deadline_epoch"] == plan["deadline_epoch"], "execution_binding")
        require(not self.config.offline or getattr(self.transport, "synthetic", False), "online_permission")
        executable = Path(amendment["codex_executable"])
        require(hashlib.sha256(executable.read_bytes()).hexdigest() == amendment["codex_executable_sha256"], "codex_binary_changed")
        provider = self.codex_provider or StandardProvider(self.ledger.root / "workers", executable=str(executable),
            timeout_seconds=180, max_input_bytes=1_000_000, max_output_bytes=262144)
        provider._check_auth_environment()
        gateway = CombinedGateway(self)
        self.gateway = gateway
        runner = CombinedBatch(self.ledger.root / "state.sqlite3", plan=plan, plan_id=data["plan"], engine=self,
            amendment={"id": data["amendment"], **amendment}, gateway=gateway,
            transport=self.transport, codex_provider=provider, clock=self.clock)
        try:
            checkpoint = lean.latest(self, parent.CHECKPOINT, data["plan"])
            require(checkpoint and parent.state_hash(runner.db) == checkpoint[1]["state_sha256"], "checkpoint_mismatch")
            gateway.bind(session, runner, data["plan"], amendment["protocol"], network=True)
            require(runner.db.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal", "wal_required")
            runner.initialize_routes()
            gateway.imported_counts = {r[0]: json.loads(r[1]) for r in runner.db.execute("SELECT custom_id,payload FROM counts")}
            runner.checkpoint(session, "three_routes_ready")
            print(canonical({"phase": "execution_started", "pid": os.getpid(), "plan": data["plan"], "amendment": data["amendment"], "at": utc()}), flush=True)
            result = runner.run_all(session, collect_only=data.get("collect_only", False), test_stop_after=data.get("test_stop_after"))
            identifier = self.ledger.record(session, "luna_all_routes_execution", data["amendment"], result)
            return {"id": identifier, **result}
        finally:
            gateway.network = False
            gateway.session = None
            runner.close()


class CombinedMigration(api.StandardMigration):
    method = METHOD
    authorization = AUTHORIZATION
    code_binding = staticmethod(implementation)
    child_class = CombinedResearch

    def extra_amendment(self, data):
        executable = Path(data["codex_executable"]).resolve(strict=True)
        return {"codex_workers": CODEX_WORKERS, "codex_executable": str(executable),
            "codex_executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "routes": ["codex", "standard", "batch"], "route_preparation_sizes": ROUTE_SIZES,
            "queue_token_limit": parent.QUEUE_TOKENS, "migration_owner": str(self.ledger.root),
            "combined_procedure": "This explicit three-route amendment supersedes Standard-only collection and the earlier one-worker Codex ceiling. One writer assigns disjoint untouched article manifests to five rolling standard-speed/low-reasoning Codex workers (Fast disabled), Standard API with the persisted 2M TPM/5000 RPM ceiling, and new parallel API Batch jobs filling the separate 20M queued-token ceiling. All accepted jobs remain. API prices and reservations share the unchanged total cap/deadline. Codex uses existing account allowance, no API charge and no usage reset. API key lives only in private transport memory, absent from Codex environments. Exact known Codex capacity/429 failures retain unknowns, drain and wait 5/15/30/60 minutes then probe a different untouched article; successful probe restores five, never resets rejection history. Other Codex transport failures pause that route, with saved unknowns preserved; API work can continue independently. Other API/transport/integrity failures stop admission and drain. No retries, no hold erasure, no automatic raising of route limits, no change to source/prompt/schema/validators. All routes close new admissions at the preserved API deadline. Mechanical validity only; no accepted findings."}


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
    parser.add_argument("--codex-executable", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    if args.phase != "migrate" and (not args.amendment or not args.allow_paid_execution):
        parser.error("Exact amendment and explicit execution flag required")
    print(canonical({"phase": "startup_preflight", "pid": os.getpid(), "workspace": str(args.workspace), "at": utc()}), flush=True)
    transport = None if args.phase == "migrate" else PrivateKeyTransport(os.environ.pop("OPENAI_API_KEY", None), timeout_seconds=120)
    engine = CombinedMigration(args.workspace) if args.phase == "migrate" else CombinedResearch(args.workspace, transport=transport, config=Config(offline=False))
    try:
        data = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        data["collect_only"] = args.phase == "collect"
        print(canonical(engine.execute("status", data, objective="Run five Codex workers, Batch and Standard API concurrently without duplicate identities", actor="codex:luna-all-routes")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
