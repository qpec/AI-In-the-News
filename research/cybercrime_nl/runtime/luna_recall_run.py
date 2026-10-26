"""Separately registered bounded Luna recall successor; root is actual operator."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
from datetime import timedelta, datetime
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import threading
import time
import uuid

import dossier_transport as transport
import luna_quality_audit as prior
import luna_recall_contract as contract
import luna_recall_design as design_module
import luna_recall_repair as repair
import luna_recall_source as source_module
from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_RECALL_UPGRADE.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-recall-upgrade-20261024-v1"
INTENT, SOURCE, PLAN = "luna_recall_intent", "luna_recall_source", "luna_recall_plan"
QUEUE, RESPONSE, LAUNCH = "luna_recall_queue", "luna_recall_response", "luna_recall_first_admission"
CHECKPOINT, FREEZE, REPORT = "luna_recall_checkpoint", "luna_recall_freeze", "luna_recall_report"
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
PREPARE_SECONDS, REPAIR_SECONDS, RUN_SECONDS = 1800, 4500, 7200
FX = 1_119_300_000
REPAIR_CAP, VALIDATION_CAP, PILOT_CAP = 25 * FX, 25 * FX // 2, 5 * FX // 2
PRIOR_COMMITMENT = 1_864_066_740
APPROVAL = {"instruction": "Implement the proposed plan.", "approval_event": "16a419b0b8ed7c2efda4e9e6",
    "approval_payload_sha256": "09059157ae3081e1e803b9d37524da41761b205d717b90057d6652f79ee63f9d",
    "approved_plan_event": "5d570f477c1d13637a2343af", "approved_plan_payload_sha256": "d2da54899f0bbac46e0a382160552592b8a87018f36241c1cc81037cdfbc4ff5",
    "pasted_plan_event": "235dc9bc9055701638b04caa", "pasted_plan_payload_sha256": "e944cb0716d6d14e00c7398b72a878cbab1e6a0c86acf20fbd6ebcd4d7a9b946"}
POLICY = {"repair_including_prior_nanousd": REPAIR_CAP, "validation_nanousd": VALIDATION_CAP,
    "pilot_subcap_nanousd": PILOT_CAP, "prior_audit_commitment_nanousd": PRIOR_COMMITMENT,
    "reserve_eur": 12.5, "usd_per_eur_nano": FX, "input_max_nanousd_per_token": 138,
    "response_output_nanousd_per_token": 550, "decisions_output_nanousd_per_token": 0,
    "long_threshold": 272000, "long_input_multiplier": 2, "long_output_multiplier": 1.5,
    "repair_seconds": REPAIR_SECONDS, "total_seconds": RUN_SECONDS, "rounds": 3,
    "discovery_fraction_of_round_time": .5, "qa_fraction_of_remaining_repair_budget": .25,
    "pair_batch_maximum": 600, "no_technical_retries": True, "final_samples_no_downsize": True}


def require(value, reason):
    if not value:
        raise AuditError("luna_recall_" + reason)


def implementation():
    files = [Path(__file__), Path(contract.__file__), Path(repair.__file__), SPEC,
        Path(design_module.__file__), Path(__file__).with_name("run_luna_recall_with_key.ps1")]
    result = prior.implementation()
    for module in (source_module, design_module):
        if hasattr(module, "implementation"):
            result.update(module.implementation())
    for p in files:
        result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ("dossier_contract_v5.py", "dossier_contract_v3.py", "dossier_candidates.py", "summary_fidelity_contract_v2.py"):
        p = Path(__file__).with_name(name)
        result[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def outcome(packet, response):
    raw = response.raw_response or {}
    cost = prior.observed_cost(response)
    if packet["kind"] == "responses" and cost is not None:
        output = response.usage.get("output_tokens")
        if type(output) is not int or output < 0 or output > 1_050_000:
            cost = None
        else:
            cost += output * contract.OUTPUT_PRICE * (3 if response.usage["input_tokens"] > contract.LONG_THRESHOLD else 2) // 2
    parsed, observations, error = None, [], None
    if response.payload is not None:
        try:
            if packet["role"] == "group_membership":
                parsed = contract.parse_members(packet, response.payload)
            elif packet["kind"] == "decisions":
                parsed, observations = contract.parse_pairs(packet, response.payload)
            else:
                parsed = contract.focal.parse_card_quality(packet, response.payload)
        except (ResearchError, KeyError, TypeError, ValueError, AttributeError) as exc:
            error = type(exc).__name__
    hold = bool(raw.get("unknown_outcome")) or cost is None or cost > packet["reservation_nanousd"]
    usable = not hold and parsed is not None and raw.get("http_status") == 200 and response.model == contract.base.MODEL
    fatal = None
    if raw.get("http_status") in {400, 401, 403, 404, 429}:
        fatal = "provider_authentication_configuration_or_quota"
    elif (raw.get("http_status") == 200 and response.model != contract.base.MODEL) or raw.get("error_type") in {"AuditError", "ResearchError"}:
        fatal = "model_or_dispatch_integrity"
    elif cost is not None and cost > packet["reservation_nanousd"]:
        fatal = "reservation_breach"
    return {"cost_nanousd": cost, "hold": hold, "usable": usable, "fatal": fatal,
        "http_status": raw.get("http_status"), "validation_error": error,
        "observations": observations if usable else [],
        "members_supported": bool(usable and packet["role"] == "group_membership" and parsed["usable"]),
        "group_supported": bool(usable and packet["kind"] == "responses" and parsed["usable"])}, parsed


def versions(desired):
    return {"protocol": desired, "question": {"text": "Bounded focal-event recall repair and matched final reference"},
        "selection": {"rules": "Frozen pilot, disjoint whole-group repair, unchanged matched final probability sample"},
        "dossier_definition": {"unit": "One bounded focal action under complete v5 focal rules"},
        "prompt": {"instructions": contract.focal.FOCUS_RULES, "clarification": contract.ACTION_RULES},
        "codebook": {"labels": list(contract.base.PAIR_LABELS), "threshold": .85},
        "profile": {"mode": "systematic"}, "policy": {"approval": desired["approval"], **POLICY}}


def can_admit(category_commitments, category, reservation, ceiling):
    """Commitments include settled charges and full unresolved high-water holds."""
    used = category_commitments.get("validation", 0) if category == "validation" else PRIOR_COMMITMENT+category_commitments.get("pilot", 0)+category_commitments.get("repair", 0)
    return used+reservation <= ceiling and (category != "pilot" or category_commitments.get("pilot", 0)+reservation <= PILOT_CAP)


def blocked_memberships(source):
    return {r["membership_revision"] for r in source["prior_history"]["membership_attempts"]
        if r.get("phase") in {"summary_quality", "summary_quality_audit", "card_quality", "card_quality_audit"}
        and (r.get("hold") or not r.get("usable"))}


def dispatch_spacing(packet):
    return max(60/RPM, packet["input_tokens_proxy"]*1.25*60/TPM)


def pacing_fits(packet, *, next_at, reserved_spacing, remaining_seconds, monotonic_now):
    # Admit only transmissions that fit the remaining pacing horizon. Responses
    # already admitted may finish later; this never renews a deadline.
    # Transport lock acquisition is not FIFO. Including every packet's spacing
    # (also this candidate) covers any wave order; allow local durable writes.
    return max(monotonic_now, next_at)+reserved_spacing+dispatch_spacing(packet)+2 < monotonic_now+remaining_seconds


class Recall(Research):
    rows = prior.Audit.rows
    one = prior.Audit.one
    complete = prior.Audit.complete

    def __init__(self, root, *, config=None):
        require(Path(root).name == OWNER_NAME, "separate_owner")
        super().__init__(root, config=config or Config(offline=True))
        self._progress_lock = threading.Lock()
        self._progress_state, self._progress_failures = {}, []
        self._dispatch_stop = threading.Event()
        self._next_dispatch = time.monotonic()
        self._state = None

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and data.get("action") in {"prepare", "run", "status", "report"}, "operation_boundary")
        fields = {"action", "audit_owner", "binding", "seed", "approval"} if data["action"] == "prepare" else {"action", "allow_paid_execution"} if data["action"] == "run" else {"action"}
        require(set(data) == fields, "operation_fields")
        return super().execute(operation, data, objective=objective, actor=actor)

    def progress(self, **values):
        # Reuse reviewed atomic, shared-readable writer; replace its method field.
        prior.Audit.progress(self, method=METHOD, **values)

    def source_progress(self, status):
        self.progress(**status)

    def guard(self, *, deadline=None, code=None):
        require(not (self.ledger.root / "STOP").exists(), "stopped")
        require(not self._progress_failures, "progress_unavailable")
        if deadline is not None:
            require(prior.now() < datetime.fromisoformat(deadline), "expired")
        if code is not None:
            require(implementation() == code, "implementation_changed")

    def retain(self, session, kind, key, value):
        rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, key)))
        require(len(rows) <= 1, "duplicate_checkpoint")
        if rows:
            require(digest(self.ledger.get(rows[0][0], kind)) == digest(value), "checkpoint_changed")
            return rows[0][0]
        return self.ledger.record(session, kind, key, value)

    def checkpoint(self, name):
        rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (CHECKPOINT, name)))
        require(len(rows) <= 1, "duplicate_checkpoint")
        return self.ledger.get(rows[0][0], CHECKPOINT) if rows else None

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        finished, started = threading.Event(), time.monotonic()
        self._progress_failures = []
        self.progress(stage=data["action"], elapsed_seconds=0)
        def heartbeat():
            while not finished.wait(30):
                try:
                    self.progress(elapsed_seconds=round(time.monotonic()-started, 3))
                except Exception as error:
                    self._progress_failures.append(error)
                    break
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if data["action"] == "prepare":
                return self.prepare(session, context, data)
            plan, source = self.load_plan()
            self._state = self.census(plan)
            if data["action"] == "run":
                require(not self.config.offline and data["allow_paid_execution"] is True and bool(os.environ.get("OPENAI_API_KEY")), "explicit_paid_permission_and_key")
                self.run(session, plan, source)
                self._state = self.census(plan)
            return self.report(session, plan, source)
        finally:
            finished.set()
            thread.join(timeout=2)
            self._state = None

    def verify_source(self, source, desired):
        p = source["recall_provenance"]
        require(p["method"] == source_module.METHOD and p["implementation"] == source_module.implementation()
            and digest(p["binding"]) == digest(desired["binding"])
            and p["audit_owner"] == str(Path(desired["audit_owner"]).resolve())
            and p["source_heads_stable_during_copy"] is True
            and source["audit"]["commitment_nanousd"] == PRIOR_COMMITMENT, "frozen_source_binding")

    def prepare(self, session, context, data):
        require(self.config.offline, "offline_preparation")
        require(Path(data["audit_owner"]).resolve() != self.ledger.root.resolve(), "source_isolation")
        require(isinstance(data["seed"], str) and len(data["seed"]) >= 16, "seed")
        spec = SPEC.read_bytes()
        require(data["approval"] == {**APPROVAL, "method_sha256": hashlib.sha256(spec).hexdigest()}, "approval")
        previous = self.one(INTENT, optional=True)
        start = previous["started_at"] if previous else prior.now().isoformat()
        expires = (datetime.fromisoformat(start) + timedelta(seconds=PREPARE_SECONDS)).isoformat()
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY, "seed": data["seed"],
            "audit_owner": data["audit_owner"], "binding": data["binding"], "approval": data["approval"],
            "started_at": start, "prepare_expires_at": expires}
        if previous:
            require(digest({k:v for k,v in previous.items() if k != "id"}) == digest(desired), "changed_preparation")
        if self.one(PLAN, optional=True):
            plan, source = self.load_plan()
            self._state = self.census(plan)
            return self.report(session, plan, source)
        self.guard(deadline=expires, code=desired["implementation"])
        require(not self.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone(), "prepare_after_attempt")
        intent = self.retain(session, INTENT, METHOD, desired)
        require(self.ledger.artifacts.put_bytes(spec) == data["approval"]["method_sha256"], "method_snapshot")
        version_ids = {}
        for kind, content in versions(desired).items():
            rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, METHOD)))
            require(len(rows) <= 1, "duplicate_version")
            if rows:
                old = self.ledger.get(rows[0][0], kind)
                require(digest(old["content"]) == digest(content) and old["reason"] is None and old["branch"] == "main", "version_changed")
                version_ids[kind] = rows[0][0]
            else:
                version_ids[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        saved = self.one(SOURCE, optional=True)
        if saved:
            require(saved["intent"] == intent, "source_intent")
            source = self.ledger.artifacts.read(saved["artifact"])
        else:
            source = source_module.collect(self, session, audit_owner=Path(data["audit_owner"]), binding=data["binding"],
                deadline_monotonic=time.monotonic()+max(0, (datetime.fromisoformat(expires)-prior.now()).total_seconds()))
        self.verify_source(source, desired)
        self.guard(deadline=expires, code=desired["implementation"])
        source_ref = self.ledger.artifacts.put(source)
        self.retain(session, SOURCE, intent, {"intent": intent, "artifact": source_ref})
        pilot = repair.pilot(source, data["seed"])
        encoder = offline_tokenizer()
        pilot_packets, pilot_unavailable = contract.build_pair_packets(source, pilot["pair_tasks"],
            lambda text: len(encoder.encode(text, disallowed_special=())), role="development")
        self.guard(deadline=expires, code=desired["implementation"])
        value = {**desired, "intent": intent, "versions": version_ids, "source_artifact": source_ref,
            "pilot_artifact": self.ledger.artifacts.put(pilot), "split_eligibility": repair.split_eligibility(source),
            "pilot_packets_artifact": self.ledger.artifacts.put(pilot_packets), "pilot_unavailable": pilot_unavailable,
            "precheck_artifact": self.ledger.artifacts.put(source["precheck"]),
            "diagnostic_artifact": self.ledger.artifacts.put(source["diagnostic"])}
        identifier = self.retain(session, PLAN, intent, value)
        self._state = self.census({"id": identifier, **value})
        return self.report(session, {"id": identifier, **value}, source)

    def load_plan(self):
        plan, intent, saved = self.one(PLAN), self.one(INTENT), self.one(SOURCE)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY, "implementation_or_policy_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k,v in intent.items() if k != "id"), "plan_intent")
        require(plan["approval"] == {**APPROVAL, "method_sha256": hashlib.sha256(SPEC.read_bytes()).hexdigest()}, "approval")
        for kind, content in versions({k:v for k,v in intent.items() if k != "id"}).items():
            rows = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, METHOD)))
            require(len(rows) == 1 and rows[0][0] == plan["versions"][kind], "version_identity")
            value = self.ledger.get(rows[0][0], kind)
            require(digest(value["content"]) == digest(content) and value["reason"] is None and value["branch"] == "main", "version_changed")
        require(saved["intent"] == plan["intent"] and saved["artifact"] == plan["source_artifact"], "source_checkpoint")
        source = self.ledger.artifacts.read(plan["source_artifact"])
        self.verify_source(source, plan)
        require(self.ledger.artifacts.read(plan["pilot_artifact"]) == repair.pilot(source, plan["seed"])
            and plan["split_eligibility"] == repair.split_eligibility(source), "selection_replay")
        encoder = offline_tokenizer()
        packets, unavailable = contract.build_pair_packets(source, self.ledger.artifacts.read(plan["pilot_artifact"])["pair_tasks"],
            lambda text: len(encoder.encode(text, disallowed_special=())), role="development")
        require(self.ledger.artifacts.read(plan["pilot_packets_artifact"]) == packets and plan["pilot_unavailable"] == unavailable, "offline_pilot_packet_replay")
        return plan, source

    def census(self, plan):
        packets, queues = {}, {}
        for row in self.rows(QUEUE):
            require(row["plan"] == plan["id"] and row["implementation"] == plan["implementation"], "queue_binding")
            items = self.ledger.artifacts.read(row["packets_artifact"])
            require(digest(items) == row["packets_artifact"], "queue_artifact")
            for packet in items:
                key = packet["task_key"]
                require(key not in packets and packet["reservation_nanousd"] == contract.reservation(packet)
                    and packet["request_sha256"] == digest(packet["request"]), "queue_packet")
                packets[key], queues[key] = packet, row
        state = {"intents": {}, "responses": {}, "packets": packets, "queues": queues, "observations": [],
            "settled_nanousd": 0, "held_nanousd": 0, "by_category": defaultdict(int), "logical_attempted": set(),
            "returned_requests": 0, "unknown_holds": 0, "completed": set()}
        byattempt = {}
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            value = json.loads(raw[0])
            key, attempt = value.get("task_key"), value.get("attempt")
            require(key in packets and key not in state["intents"] and attempt not in byattempt, "attempt_scope_or_retry")
            packet, queue = packets[key], queues[key]
            require(value["method"] == METHOD and value["batch"] == plan["id"] and value["queue"] == queue["id"]
                and value["number"] == 1 and value["packet"] == digest(packet) and value["request"] == packet["request_sha256"]
                and value["reserved_nanousd"] == packet["reservation_nanousd"] and value["category"] == queue["category"], "intent_binding")
            require(not state["logical_attempted"].intersection(packet["logical_ids"]), "logical_retry")
            require(self.ledger.artifacts.read(value["dispatch"]) == transport.Invocation(packet["request"], attempt, kind=packet["kind"]).manifest(), "dispatch_binding")
            state["intents"][key], byattempt[attempt] = value, key
            state["logical_attempted"].update(packet["logical_ids"])
        receipts = {}
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='luna_recall.response.received' ORDER BY seq"):
            receipt = json.loads(raw[0])
            attempt = receipt["attempt"]
            require(attempt in byattempt and attempt not in receipts, "receipt_identity")
            response = ProviderResponse(**self.ledger.artifacts.read(receipt["response"]))
            derived, parsed = outcome(packets[byattempt[attempt]], response)
            receipts[attempt] = {"response": receipt["response"], "derived": derived, "parsed": parsed}
        for row in self.rows(RESPONSE):
            key = row["task_key"]
            require(key in state["intents"] and key not in state["responses"] and row["attempt"] == state["intents"][key]["attempt"]
                and row["plan"] == plan["id"] and row["attempt"] in receipts, "response_identity")
            receipt = receipts[row["attempt"]]
            require(row["response"] == receipt["response"] and row["parsed"] == (digest(receipt["parsed"]) if receipt["parsed"] else None)
                and all(digest(row.get(k)) == digest(v) for k,v in receipt["derived"].items()), "response_replay")
            state["responses"][key] = row
        for raw in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.completed'"):
            value = json.loads(raw[0])
            attempt = value["attempt"]
            require(attempt in byattempt and attempt not in state["completed"], "completion_scope")
            row = state["responses"].get(byattempt[attempt])
            require(row and not row["hold"] and row["id"] == value["assessment"] and row["response"] == value["response"], "completion_binding")
            state["completed"].add(attempt)
        health_rows = dict(state["responses"])
        for key, intended in state["intents"].items():
            receipt = receipts.get(intended["attempt"])
            cost = receipt["derived"]["cost_nanousd"] if receipt else None
            if intended["attempt"] in state["completed"]:
                require(type(cost) is int and cost >= 0, "settled_cost")
                state["settled_nanousd"] += cost
                liability = cost
                if state["responses"][key]["usable"]:
                    state["observations"].extend(state["responses"][key]["observations"])
            else:
                liability = max(intended["reserved_nanousd"], cost or 0)
                state["held_nanousd"] += liability
                state["unknown_holds"] += 1
            state["by_category"][intended["category"]] += liability
            if receipt and key not in health_rows:
                health_rows[key] = {**receipt["derived"], "usable": False}
        require(set(self.ledger.unresolved) == set(byattempt)-state["completed"], "orphan_inventory")
        state["returned_requests"] = len(receipts)
        state["health"] = prior.health_state(state["intents"], health_rows)
        return state

    def queue(self, session, plan, name, packets, unavailable, category, *, deadline, budget_ceiling):
        existing = [r for r in self.rows(QUEUE) if r["name"] == name]
        if existing:
            require(len(existing) == 1 and existing[0]["plan"] == plan["id"], "queue_identity")
            return existing[0], self.ledger.artifacts.read(existing[0]["packets_artifact"])
        # Retain every selection even if none can be admitted; no sample resizing.
        value = {"plan": plan["id"], "name": name, "implementation": plan["implementation"], "category": category,
            "packets_artifact": self.ledger.artifacts.put(packets), "unavailable": unavailable,
            "deadline": deadline, "budget_ceiling_nanousd": budget_ceiling,
            "planned_reservation_nanousd": sum(p["reservation_nanousd"] for p in packets)}
        row = {"id": self.retain(session, QUEUE, name, value), **value}
        for packet in packets:
            require(packet["task_key"] not in self._state["packets"], "duplicate_packet_registration")
            self._state["packets"][packet["task_key"]] = packet
            self._state["queues"][packet["task_key"]] = row
        return row, packets

    def first_admission(self, session, plan):
        row = self.one(LAUNCH, optional=True)
        if not row:
            require(not self._state["intents"], "attempt_before_clock")
            start = prior.now()
            value = {"plan": plan["id"], "started_at": start.isoformat(), "policy": POLICY,
                "repair_expires_at": (start+timedelta(seconds=REPAIR_SECONDS)).isoformat(),
                "expires_at": (start+timedelta(seconds=RUN_SECONDS)).isoformat()}
            row = {"id": self.retain(session, LAUNCH, plan["id"], value), **value}
        require(row["plan"] == plan["id"] and row["policy"] == POLICY
            and datetime.fromisoformat(row["expires_at"])-datetime.fromisoformat(row["started_at"]) == timedelta(seconds=RUN_SECONDS)
            and datetime.fromisoformat(row["repair_expires_at"])-datetime.fromisoformat(row["started_at"]) == timedelta(seconds=REPAIR_SECONDS), "immutable_clock")
        return row

    def provider(self, plan, deadline, packets):
        byrequest = {p["request_sha256"]: p for p in packets}
        def before(invocation):
            self.guard(deadline=deadline, code=plan["implementation"])
            require(not self._dispatch_stop.is_set(), "dispatch_stopped")
            require(digest(invocation.request) in byrequest and invocation.kind == byrequest[digest(invocation.request)]["kind"], "dispatch_request")
            while time.monotonic() < self._next_dispatch:
                require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                self.guard(deadline=deadline)
                time.sleep(min(.2, max(0, self._next_dispatch-time.monotonic())))
            self.guard(deadline=deadline)
            require(not self._dispatch_stop.is_set(), "dispatch_stopped")
            p = byrequest[digest(invocation.request)]
            self._next_dispatch = time.monotonic()+dispatch_spacing(p)
            return True
        return transport.UnifiedTransport(before_dispatch=before)

    def dispatch(self, session, plan, queue, packets):
        state = self._state
        ready = [p for p in packets if not set(p["logical_ids"]) & state["logical_attempted"]]
        if not ready or state["health"]["stop_reason"]:
            return state["health"]["stop_reason"] or "queue_complete"
        if not can_admit(state["by_category"], queue["category"], ready[0]["reservation_nanousd"], queue["budget_ceiling_nanousd"]):
            return "budget_bound"
        if queue["deadline"] == "first_paid_repair_window":
            require(queue["category"] == "pilot", "relative_window_scope")
            self.guard(code=plan["implementation"])
            deadline = self.first_admission(session, plan)["repair_expires_at"]
        else:
            deadline = queue["deadline"]
        self._dispatch_stop.clear()
        provider = self.provider(plan, deadline, packets)
        position = 0
        while position < len(ready):
            if state["health"]["stop_reason"]:
                return state["health"]["stop_reason"]
            try:
                self.guard(deadline=deadline, code=plan["implementation"])
            except AuditError as error:
                if str(error) not in {"luna_recall_expired", "luna_recall_stopped"}:
                    raise
                return str(error)
            wave, intended_rows = [], []
            reserved_spacing = 0
            for packet in ready[position:position+(MAX_WORKERS if state["intents"] else 1)]:
                if not pacing_fits(packet, next_at=self._next_dispatch, reserved_spacing=reserved_spacing,
                        remaining_seconds=(datetime.fromisoformat(deadline)-prior.now()).total_seconds(), monotonic_now=time.monotonic()):
                    if not wave:
                        return "stage_pacing_window_bound"
                    break
                cost = packet["reservation_nanousd"]
                if not can_admit(state["by_category"], queue["category"], cost, queue["budget_ceiling_nanousd"]):
                    if not wave:
                        return "budget_bound"
                    break
                self.guard(deadline=deadline, code=plan["implementation"])
                attempt = str(uuid.uuid4())
                invocation = transport.Invocation(packet["request"], attempt, kind=packet["kind"])
                intended = {"method": METHOD, "attempt": attempt, "task_key": packet["task_key"], "number": 1,
                    "batch": plan["id"], "queue": queue["id"], "category": queue["category"],
                    "request": self.ledger.artifacts.put(packet["request"]), "packet": self.ledger.artifacts.put(packet),
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "reserved_nanousd": cost, "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                state["intents"][packet["task_key"]] = intended
                state["logical_attempted"].update(packet["logical_ids"])
                state["held_nanousd"] += cost
                state["by_category"][queue["category"]] += cost
                state["unknown_holds"] += 1
                wave.append((invocation, attempt))
                intended_rows.append(intended)
                reserved_spacing += dispatch_spacing(packet)
            if not wave:
                break
            for index, response in self.gateway.codex_dispatch(session, provider, wave, workers=MAX_WORKERS):
                intended = intended_rows[index]
                packet = state["packets"][intended["task_key"]]
                ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "luna_recall.response.received", {"attempt": intended["attempt"], "response": ref})
                derived, parsed = outcome(packet, response)
                value = {"plan": plan["id"], "attempt": intended["attempt"], "task_key": intended["task_key"],
                    "response": ref, "parsed": self.ledger.artifacts.put(parsed) if parsed else None, **derived}
                record = self.ledger.record(session, RESPONSE, intended["attempt"], value)
                state["responses"][intended["task_key"]] = {"id": record, **value}
                state["returned_requests"] += 1
                if not derived["hold"]:
                    self.complete(session, intended, ref, record, "valid" if derived["usable"] else "invalid")
                    state["completed"].add(intended["attempt"])
                    state["held_nanousd"] -= intended["reserved_nanousd"]
                    state["settled_nanousd"] += derived["cost_nanousd"]
                    state["by_category"][queue["category"]] += derived["cost_nanousd"]-intended["reserved_nanousd"]
                    state["unknown_holds"] -= 1
                    state["observations"].extend(derived["observations"])
                else:
                    extra = max(0, (derived["cost_nanousd"] or 0)-intended["reserved_nanousd"])
                    state["held_nanousd"] += extra
                    state["by_category"][queue["category"]] += extra
                if derived["fatal"]:
                    self._dispatch_stop.set()
            state["health"] = prior.health_state(state["intents"], state["responses"])
            position += len(wave)
            self.progress(stage=queue["name"], queued_requests=len(packets), attempted_requests=len(state["intents"]),
                returned_requests=state["returned_requests"], unknown_holds=state["unknown_holds"],
                settled_nanousd=state["settled_nanousd"], held_nanousd=state["held_nanousd"],
                repair_remaining_nanousd=max(0, REPAIR_CAP-PRIOR_COMMITMENT-state["by_category"]["pilot"]-state["by_category"]["repair"]),
                validation_remaining_nanousd=max(0, VALIDATION_CAP-state["by_category"]["validation"]), expires_at=deadline)
        return "queue_complete"

    def pair_stage(self, session, plan, source, name, tasks, *, role, category, deadline, ceiling, roundplan=None):
        done = self.checkpoint(name)
        if done:
            return
        encoder = offline_tokenizer()
        def count(text):
            return len(encoder.encode(text, disallowed_special=()))
        # Register consecutive bounded batches. Exact logical attempts are global.
        for offset in range(0, len(tasks), repair.BATCH_PAIRS):
            selected = tasks[offset:offset+repair.BATCH_PAIRS]
            if roundplan is not None:
                known = repair.observations_by_pair(self.development(source))
                supported = defaultdict(set)
                anchors = defaultdict(set)
                for proposal in roundplan["proposals"]:
                    key = contract.pair_key(*proposal["pair"])
                    anchors[key].add(proposal["anchor"])
                    if contract.combine(known.get(key, [])) == "same_event":
                        supported[proposal["anchor"]].add(proposal["target"])
                selected = [t for t in selected if any(len(supported[a]) < repair.MAX_TARGETS for a in anchors[t["pair_key"]])]
            name0 = name + f"/batch-{offset}"
            old = [r for r in self.rows(QUEUE) if r["name"] == name0]
            registered = {i for p in self._state["packets"].values() for i in p["logical_ids"]}
            fresh = [t for t in selected if contract.identity(source, (t["left"], t["right"]), role) not in registered]
            if name == "pilot" and not old:
                require(offset == 0 and fresh == selected, "offline_pilot_partition")
                packets, unavailable = self.ledger.artifacts.read(plan["pilot_packets_artifact"]), plan["pilot_unavailable"]
            else:
                packets, unavailable = contract.build_pair_packets(source, fresh, count, role=role) if not old else ([], {})
            queue, packets = self.queue(session, plan, name0, packets, unavailable, category, deadline=deadline, budget_ceiling=ceiling)
            reason = self.dispatch(session, plan, queue, packets)
            keys = {t["pair_key"] for t in selected}
            observations = [r for r in self._state["observations"] if r["role"] == role and not r["clarification"] and r["pair_key"] in keys]
            unknown = {r["pair_key"] for r in observations if r["semantic_unknown"]}
            registered = {i for p in self._state["packets"].values() for i in p["logical_ids"]}
            clarification_tasks = [t for t in selected if t["pair_key"] in unknown and contract.identity(source, (t["left"], t["right"]), role, True) not in registered]
            cname = name0 + "/clarification"
            old = [r for r in self.rows(QUEUE) if r["name"] == cname]
            packets, unavailable = contract.build_pair_packets(source, clarification_tasks, count, role=role, clarification=True) if not old else ([], {})
            queue, packets = self.queue(session, plan, cname, packets, unavailable, category, deadline=deadline, budget_ceiling=ceiling)
            clarification_reason = self.dispatch(session, plan, queue, packets)
            launch = self.one(LAUNCH, optional=True)
            effective = launch["repair_expires_at"] if deadline == "first_paid_repair_window" and launch else deadline
            if reason != "queue_complete" or clarification_reason != "queue_complete" or (effective != "first_paid_repair_window" and prior.now() >= datetime.fromisoformat(effective)) or self._state["health"]["stop_reason"]:
                break
        self.retain(session, CHECKPOINT, name, {"plan": plan["id"], "tasks_artifact": self.ledger.artifacts.put(tasks),
            "selected_pairs": len(tasks), "completed_stage_at": utc(), "unattempted_remain_missing": True})

    def qa(self, session, plan, source, name, proposals, deadline):
        encoder = offline_tokenizer()
        def count(text):
            return len(encoder.encode(text, disallowed_special=()))
        proposals = [p for p in proposals if not p.get("negative_veto")]
        prior_memberships = blocked_memberships(source)
        member_name = name+"/members"
        old_members = [r for r in self.rows(QUEUE) if r["name"] == member_name]
        member_packets, member_unavailable, seen = [], {}, set()
        if not old_members:
            registered = {i for p in self._state["packets"].values() for i in p["logical_ids"]}
            for p in proposals:
                revision = p["membership_revision"]
                if revision in seen:
                    continue
                seen.add(revision)
                if revision in prior_memberships:
                    member_unavailable[revision] = "previous_failed_or_held_exact_membership"
                    continue
                try:
                    packet = contract.member_packet(source, p["members"], count)
                except ResearchError as error:
                    if str(error) != "dossier_packet_capacity":
                        raise
                    member_unavailable[revision] = "full_union_capacity"
                    continue
                if not set(packet["logical_ids"]) & registered:
                    member_packets.append(packet)
        member_queue, member_packets = self.queue(session, plan, member_name, member_packets, member_unavailable, "repair",
            deadline=deadline, budget_ceiling=REPAIR_CAP)
        self.dispatch(session, plan, member_queue, member_packets)
        member_supported = {self._state["packets"][key]["membership_revision"] for key,row in self._state["responses"].items()
            if row["attempt"] in self._state["completed"] and row["members_supported"]}
        proposals = [p for p in proposals if p["membership_revision"] in member_supported]
        old = [r for r in self.rows(QUEUE) if r["name"] == name]
        packets, unavailable = [], {}
        if not old:
            registered = {i for p in self._state["packets"].values() for i in p["logical_ids"]}
            seen = set()
            for p in proposals:
                revision = p["membership_revision"]
                if revision in seen:
                    continue
                seen.add(revision)
                if revision in prior_memberships:
                    unavailable[revision] = "previous_failed_or_held_exact_membership"
                    continue
                try:
                    packet = contract.group_packet(source, p["members"], count)
                except ResearchError as error:
                    if str(error) != "dossier_packet_capacity":
                        raise
                    unavailable[revision] = "full_union_capacity"
                    continue
                if not set(packet["logical_ids"]) & registered:
                    packets.append(packet)
        queue, packets = self.queue(session, plan, name, packets, unavailable, "repair", deadline=deadline, budget_ceiling=REPAIR_CAP)
        self.dispatch(session, plan, queue, packets)
        supported = {}
        for key, row in self._state["responses"].items():
            packet = self._state["packets"][key]
            if packet["kind"] == "responses" and row["attempt"] in self._state["completed"] and row["group_supported"] and packet["membership_revision"] in member_supported:
                supported[packet["membership_revision"]] = packet["card"]
        return supported

    def development(self, source):
        return [*repair.compatible_prior(source), *[r for r in self._state["observations"] if r["role"] == "development"]]

    def run(self, session, plan, source):
        self.guard(code=plan["implementation"])
        launch = self.one(LAUNCH, optional=True)
        frozen = self.one(FREEZE, optional=True)
        if frozen:
            require(launch is not None, "freeze_before_admission")
            launch = self.first_admission(session, plan)
            self.validate(session, plan, source, launch, frozen)
            return
        pilot = self.ledger.artifacts.read(plan["pilot_artifact"])
        self.pair_stage(session, plan, source, "pilot", pilot["pair_tasks"], role="development", category="pilot",
            deadline="first_paid_repair_window", ceiling=REPAIR_CAP)
        launch = self.one(LAUNCH, optional=True)
        if launch is None:
            return
        launch = self.first_admission(session, plan)
        state = repair.initial_state(source)
        # Targeted split eligibility is fixed before the pilot; no validation feedback.
        split_done = self.checkpoint("split-commit")
        if split_done:
            state = self.ledger.artifacts.read(split_done["state_artifact"])
        elif plan["split_eligibility"]:
            tasks = {contract.pair_key(a,b): repair.task((a,b)) for members in plan["split_eligibility"].values() for a,b in combinations(members,2)}
            self.pair_stage(session, plan, source, "split-pairs", list(tasks.values()), role="development", category="repair",
                deadline=launch["repair_expires_at"], ceiling=PRIOR_COMMITMENT+(REPAIR_CAP-PRIOR_COMMITMENT)*3//4)
            changes, proposals = [], []
            for g, members in plan["split_eligibility"].items():
                parts = repair.split_components(members, self.development(source))
                children = parts["groups"] + [[i] for i in parts["excluded_ids"]]
                if len(children) <= 1:
                    continue
                changes.append({"original_members": members, "children": [{"members": ids, "supported": False, "card": None} for ids in children]})
                proposals.extend({"members": ids, "membership_revision": digest(sorted(ids))} for ids in children)
            supported = self.qa(session, plan, source, "split-qa", proposals, launch["repair_expires_at"])
            for change in changes:
                for child in change["children"]:
                    ref = digest(sorted(child["members"]))
                    child.update(supported=ref in supported, card=supported.get(ref))
            state = repair.commit(state, changes, reason="targeted_complete_link_split")
            self.retain(session, CHECKPOINT, "split-commit", {"plan": plan["id"], "state_artifact": self.ledger.artifacts.put(state)})
        for number in range(1, repair.MAX_ROUNDS+1):
            name = f"round-{number}"
            done = self.checkpoint(name+"/commit")
            if done:
                state = self.ledger.artifacts.read(done["state_artifact"])
                if done["accepted_changes"] == 0:
                    break
                continue
            if prior.now() >= datetime.fromisoformat(launch["repair_expires_at"]) or self._state["health"]["stop_reason"]:
                break
            saved = self.checkpoint(name+"/plan")
            if saved:
                roundplan = self.ledger.artifacts.read(saved["artifact"])
                require(roundplan["state_digest"] == digest(state), "round_membership_stale")
            else:
                start = prior.now()
                remaining = max(0, (datetime.fromisoformat(launch["repair_expires_at"])-start).total_seconds())
                duration = remaining/(repair.MAX_ROUNDS-number+1)
                used = PRIOR_COMMITMENT+self._state["by_category"]["pilot"]+self._state["by_category"]["repair"]
                roundplan = {**repair.round_plan(source, state, self.development(source), number),
                    "discovery_expires_at": (start+timedelta(seconds=duration/2)).isoformat(),
                    "qa_expires_at": (start+timedelta(seconds=duration)).isoformat(),
                    "discovery_ceiling_nanousd": used+max(0, REPAIR_CAP-used)*3//4}
                self.retain(session, CHECKPOINT, name+"/plan", {"plan": plan["id"], "artifact": self.ledger.artifacts.put(roundplan)})
            self.pair_stage(session, plan, source, name+"/discovery", roundplan["pair_tasks"], role="development", category="repair",
                deadline=roundplan["discovery_expires_at"], ceiling=roundplan["discovery_ceiling_nanousd"], roundplan=roundplan)
            proposals = repair.union_proposals(roundplan, self.development(source))
            supported = self.qa(session, plan, source, name+"/qa", proposals, roundplan["qa_expires_at"])
            alternatives = [p for p in proposals if p["membership_revision"] in supported]
            fallbacks = [f for p in proposals if p["membership_revision"] not in supported for f in repair.fallback(p, roundplan["units"], self.development(source))]
            fallback_supported = self.qa(session, plan, source, name+"/fallback", fallbacks, roundplan["qa_expires_at"])
            supported.update(fallback_supported)
            alternatives.extend(p for p in fallbacks if p["membership_revision"] in supported)
            alternatives.sort(key=lambda p: (-p["minimum_support"], -p["new_pairs"], p["membership_revision"]))
            changes, occupied = [], set()
            for p in alternatives:
                if occupied.intersection(p["members"]):
                    continue
                occupied.update(p["members"])
                changes.append({"original_members": p["members"], "children": [{"members": p["members"],
                    "supported": True, "card": supported[p["membership_revision"]]}]})
            state = repair.commit(state, changes, reason=name)
            self.retain(session, CHECKPOINT, name+"/commit", {"plan": plan["id"], "state_artifact": self.ledger.artifacts.put(state), "accepted_changes": len(changes)})
            self.progress(stage=name+"/committed", accepted_changes=len(changes), accepted_groups=len(state["accepted_group_ids"]))
            if not changes:
                break
        frozen = self.one(FREEZE, optional=True)
        if not frozen:
            exposed = {i for row in source["audit"]["source_pairs"].values() for i in row}
            exposed |= {i for r in source["prior_history"]["pair_observations"] for i in r.get("pair", [])}
            exposed |= {r["document_id"] for r in source["prior_history"].get("clarity_observations", []) if r.get("document_id") in source["documents"]}
            exposed |= {i for p in self._state["packets"].values() if p["role"] != "final_reference" and p["task_key"] in self._state["intents"]
                for i in (p.get("members") or [v["document_id"] for v in p.get("source_bindings", {}).values()])}
            proposals = [r["pair"] for c in self.rows(CHECKPOINT) if "artifact" in c for r in self.ledger.artifacts.read(c["artifact"]).get("proposals", [])]
            risk = {"repair_proposal": proposals, "development_positive_or_uncertain": [r["pair"] for r in self.development(source) if r["label"] != "negative"]}
            self.progress(stage="freezing_successor_and_validation")
            self.retain(session, CHECKPOINT, "successor-before-draw", {"plan": plan["id"], "state_artifact": self.ledger.artifacts.put(state),
                "source_artifact": plan["source_artifact"], "seed": plan["seed"], "exposed_documents": sorted(exposed),
                "risk_pairs": risk, "design_method": design_module.METHOD,
                "frame_summary_artifact": self.ledger.artifacts.put(design_module.frame_summary(source, state,
                    exposed_documents=sorted(exposed), risk_pairs=risk))})
            design = design_module.build_design(source, state, plan["seed"], exposed_documents=sorted(exposed), risk_pairs=risk)
            value = {"plan": plan["id"], "state_artifact": self.ledger.artifacts.put(state), "exposed_documents": sorted(exposed),
                "risk_pairs": risk, "design_artifact": self.ledger.artifacts.put(design), "frozen_before_final_reference": True}
            frozen = {"id": self.retain(session, FREEZE, plan["id"], value), **value}
        self.validate(session, plan, source, launch, frozen)

    def validate(self, session, plan, source, launch, frozen):
        design = self.frozen_design(plan, source, frozen)
        self.pair_stage(session, plan, source, "validation", design["pair_tasks"], role="final_reference", category="validation",
            deadline=launch["expires_at"], ceiling=VALIDATION_CAP)

    def frozen_design(self, plan, source, frozen):
        require(frozen["plan"] == plan["id"], "freeze_plan")
        state = self.ledger.artifacts.read(frozen["state_artifact"])
        design = self.ledger.artifacts.read(frozen["design_artifact"])
        scope = self.checkpoint("successor-before-draw")
        require(scope and scope["state_artifact"] == frozen["state_artifact"] and scope["seed"] == plan["seed"]
            and scope["plan"] == plan["id"] and scope["design_method"] == design_module.METHOD
            and scope["frame_summary_artifact"] == digest(design["frame"])
            and scope["source_artifact"] == plan["source_artifact"] and scope["risk_pairs"] == frozen["risk_pairs"]
            and scope["exposed_documents"] == frozen["exposed_documents"], "prospective_sample_scope")
        require(design == design_module.build_design(source, state, plan["seed"], exposed_documents=frozen["exposed_documents"], risk_pairs=frozen["risk_pairs"]), "frozen_design_replay")
        return design

    def report(self, session, plan, source):
        state = self._state
        frozen = self.one(FREEZE, optional=True)
        analysis = None
        successor = repair.initial_state(source)
        if frozen:
            successor = self.ledger.artifacts.read(frozen["state_artifact"])
            design = self.frozen_design(plan, source, frozen)
            rows = repair.observations_by_pair([r for r in state["observations"] if r["role"] == "final_reference"])
            analysis = design_module.compute_report(design, {k:contract.combine(v) for k,v in rows.items()})
        value = {"method": METHOD, "plan": plan["id"], "frozen_record": frozen["id"] if frozen else None,
            "successor_artifact": self.ledger.artifacts.put(successor), "analysis": analysis,
            "precheck_artifact": plan["precheck_artifact"], "diagnostic_artifact": plan["diagnostic_artifact"],
            "attempted_requests": len(state["intents"]), "returned_requests": state["returned_requests"],
            "queued_requests": len(state["packets"]), "unattempted_requests": len(set(state["packets"])-set(state["intents"])),
            "settled_nanousd": state["settled_nanousd"], "held_nanousd": state["held_nanousd"], "unknown_holds": state["unknown_holds"],
            "prior_audit_commitment_nanousd": PRIOR_COMMITMENT,
            "committed_including_prior_nanousd": PRIOR_COMMITMENT+state["settled_nanousd"]+state["held_nanousd"],
            "category_commitments_nanousd": dict(state["by_category"]), "response_health": state["health"],
            "accepted_groups": len(successor["accepted_group_ids"]), "changes": len(successor["lineage"]),
            "merge_changes": sum(r["reason"].startswith("round-") for r in successor["lineage"]),
            "split_changes": sum(r["reason"] == "targeted_complete_link_split" for r in successor["lineage"]),
            "source_artifact": plan["source_artifact"], "source_provenance": source["recall_provenance"],
            "policy": POLICY, "first_admission": self.one(LAUNCH, optional=True),
            "dependent_model_reference_not_human_truth": True, "cost_is_conservative_estimate_not_invoice": True,
            "original_dossiers_and_budgets_unchanged": True}
        identifier = self.ledger.record(session, REPORT, digest(value), value)
        self.progress(stage="report", attempted_requests=value["attempted_requests"], returned_requests=value["returned_requests"],
            unknown_holds=value["unknown_holds"], changes=value["changes"], committed_including_prior_nanousd=value["committed_including_prior_nanousd"])
        return {"id": identifier, **value}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "status", "report"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require((args.input is not None) == (args.action == "prepare"), "cli_input")
    data = json.loads(args.input.read_text(encoding="utf-8")) if args.input else {}
    data["action"] = args.action
    if args.action == "run":
        data["allow_paid_execution"] = args.allow_paid_execution
    engine = Recall(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(engine.execute("status", data, objective="Approved bounded Luna recall successor", actor="codex:luna-recall")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
