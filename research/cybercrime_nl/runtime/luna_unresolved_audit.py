"""One fixed unresolved-article existence audit; no dossier mutation or retry."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
import uuid

import dossier_transport as wire
import dossier_transport_v9 as transport
import luna_quality_audit as prior
import luna_recall_contract as contract
import luna_recall_run_v2 as retained
import luna_unresolved_audit_design as design
import luna_unresolved_audit_source as source_module
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_UNRESOLVED_AUDIT.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-unresolved-audit-20261025-v1"
INTENT, SEED, PLAN, LAUNCH, QUEUE, RESPONSE, CHECKPOINT, RESULT = (
    "luna_unresolved_audit_"+s for s in ("intent", "seed", "plan", "launch", "queue", "response", "checkpoint", "result"))
RECEIVED = "luna_unresolved_audit.response.received"
VALIDATION_CAP, PRIOR_COMMITMENT = 13_991_250_000, 9_998_784_420
PRIOR_SETTLED, PRIOR_HELD = 9_977_722_440, 21_061_980
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
POLICY = {"method": METHOD, "validation_cap_nanousd": VALIDATION_CAP,
    "prior_repair_commitment_nanousd": PRIOR_COMMITMENT, "prior_repair_settled_nanousd": PRIOR_SETTLED,
    "prior_repair_held_nanousd": PRIOR_HELD, "repair_budget_available": False,
    "reserve_budget_available": False, "usd_per_eur_nano": 1_119_300_000,
    "max_workers": MAX_WORKERS, "rpm": RPM, "tpm": TPM, "http_timeout_seconds": 120,
    "technical_retries": 0, "automatic_interrupted_resume": False, "effective_deadline": None,
    "stop_after_first_completed_usable_positive": True, "membership_changes": False,
    "cache_savings_assumed": False, "full_quote_before_admission": True}
APPROVAL = {"sample_search_event": "2d0cd4af07c8e105cc5a76e6",
    "positive_stop_event": "a46a66ea445c55da4795314f", "budget_event": "7d40a2fb94ff60df464f36ac"}


def require(value, reason):
    if not value:
        raise AuditError("luna_unresolved_audit_"+reason)


def implementation():
    files = [Path(__file__), SPEC, Path(__file__).with_name("run_luna_unresolved_audit_with_key.ps1"),
        Path(wire.__file__), Path(transport.__file__), Path(prior.__file__), Path(retained.__file__)]
    return {**source_module.implementation(), **design.implementation(),
        **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def new_seed():
    return secrets.token_hex(32)


def versions(desired):
    return {"protocol": desired, "question": {"text": "Does a sampled unresolved article have any same-event partner in the frozen corpus?"},
        "selection": {"rules": "One uniform sample before eligibility; complete corpus search with positive witness stopping"},
        "dossier_definition": {"unit": "Article-level existence of a same focal event partner"},
        "prompt": {"instructions": canonical(design.SHARED_RULES)},
        "codebook": {"labels": ["same_event", "negative", "unknown"]},
        "profile": {"mode": "systematic", "model_reference_not_human_truth": True, "membership_changes": False}, "policy": POLICY}


def outcome(packet, response):
    raw, parsed, validation_error = response.raw_response or {}, None, None
    cost = prior.observed_cost(response)
    if response.payload is not None:
        try:
            answers, observations = design.parse(packet, response.payload)
            parsed = {"parsed": answers, "observations": observations}
        except (ResearchError, TypeError, KeyError, ValueError, AttributeError) as error:
            validation_error = type(error).__name__
    hold = bool(raw.get("unknown_outcome")) or cost is None or cost > packet["reservation_nanousd"]
    usable = not hold and parsed is not None and response.model == contract.base.MODEL and raw.get("http_status") == 200
    fatal = None
    if raw.get("http_status") in {400, 401, 403, 404, 429}:
        fatal = "provider_authentication_configuration_or_quota"
    elif raw.get("failure_code") in {"request_preflight_rejected", "redirect_rejected", "http_status_unavailable",
            "response_byte_capacity", "response_content_rejected"}:
        fatal = raw["failure_code"]
    elif response.payload is not None and raw.get("http_status") == 200 and response.model != contract.base.MODEL:
        fatal = "complete_payload_model_mismatch"
    elif raw.get("error_type") in {"AuditError", "ResearchError"}:
        fatal = "audited_gateway_exception"
    elif cost is not None and cost > packet["reservation_nanousd"]:
        fatal = "reservation_breach"
    return {"cost_nanousd": cost, "hold": hold, "usable": usable, "validation_error": validation_error,
        "http_status": raw.get("http_status"), "fatal": fatal, "failure_stage": raw.get("failure_stage"),
        "failure_code": raw.get("failure_code"), "dispatch_started": raw.get("dispatch_started")}, parsed


def empty_state():
    return {"intents": {}, "responses": {}, "logical_attempted": set(), "attempted_pairs": {},
        "completed": set(), "observations": {}, "settled_nanousd": 0, "held_nanousd": 0,
        "unknown_holds": 0, "returned_requests": 0, "health": {"stop_reason": None}}


class Audit(Research):
    rows, one, complete, retain = prior.Audit.rows, prior.Audit.one, prior.Audit.complete, retained.Recall.retain

    def __init__(self, root, *, config=None):
        root = Path(root)
        require(root.name == OWNER_NAME, "separate_owner")
        super().__init__(root, config=config or Config(offline=True))
        self._progress_lock, self._pace_lock = threading.Lock(), threading.Lock()
        self._progress_state, self._progress_failures = {}, []
        self._dispatch_stop = threading.Event()
        self._next_dispatch, self._state = time.monotonic(), None

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and data.get("action") in {"prepare", "run", "status", "report"}, "operation")
        require(set(data) == ({"action", "allow_paid_execution"} if data["action"] == "run" else {"action"}), "operation_fields")
        return super().execute(operation, data, objective=objective, actor=actor)

    def progress(self, **values):
        prior.Audit.progress(self, method=METHOD, **values)

    def source_progress(self, values):
        self.progress(**values)

    def guard(self, code=None):
        require(not (self.ledger.root/"STOP").exists(), "stopped")
        require(not self._progress_failures, "progress_unavailable")
        if code is not None:
            require(implementation() == code, "implementation_changed")

    def set_scope(self, imported):
        require(imported["prior_commitment_nanousd"] == PRIOR_COMMITMENT
            and imported["diagnostic"]["scope_admission_allowed"] is True, "import_scope")
        p = imported["provenance"]
        require(p["binding"] == source_module.binding() and p["implementation"] == source_module.implementation()
            and p["source_head_unchanged"] is True and Path(p["owner"]) == source_module.OWNER, "import_provenance")
        self._prior_logical_ids = set(imported["history"].get("logical_ids", [])) | set(imported["history"].get("prior_final_reference_logical_ids", []))
        self._prior_task_keys = set(imported["history"].get("task_keys", []))
        self._quarantine = set(imported["history"]["quarantine_document_ids"])

    @staticmethod
    def counter():
        encoder = offline_tokenizer()
        return lambda text: len(encoder.encode(text, disallowed_special=()))

    def quote(self, source, selection, count, code):
        rows, total, unavailable = [], Counter(), Counter()
        for n, descriptor in enumerate(selection["descriptors"]):
            self.guard(code if n % 32 == 0 else None)
            bundle = design.packet(source, descriptor, count)
            q = dict(bundle["quote"])
            q["measured_token_cost_proxy_nanousd"] = sum(p["input_tokens_proxy"]*138*(2 if p["input_tokens_proxy"] > contract.LONG_THRESHOLD else 1)
                for p in bundle["packets"])
            counts = dict(Counter(r["reason"] for r in bundle["unavailable"]))
            unavailable.update(counts)
            total.update(q)
            rows.append({"descriptor_digest": descriptor["digest"], "quote": q, "unavailable_counts": counts,
                "packet_count": len(bundle["packets"]), "coverage_digest": bundle["coverage_digest"]})
            self.progress(stage="offline_quote", completed_rectangles=n+1, total_rectangles=len(selection["descriptors"]),
                quoted_reservation_nanousd=total["reservation_nanousd"])
            del bundle
        return {"method": METHOD, "selection_digest": selection["digest"], "rectangles": rows, "total": dict(total),
            "unavailable_counts": dict(unavailable), "validation_cap_nanousd": VALIDATION_CAP,
            "full_grid_fits_reservation": total["reservation_nanousd"] <= VALIDATION_CAP,
            "proxy_is_not_invoice_or_guarantee": True, "cache_savings_assumed": False,
            "affordable_prefix_may_leave_selected_articles_unknown": True}

    def prepare(self, session, context):
        require(self.config.offline, "offline_prepare")
        if self.one(PLAN, optional=True):
            plan, imported, selection = self.load_plan()
            self._state = self.census(plan, selection)
            return self.summary(plan)
        require(not self.one(INTENT, optional=True), "partial_prepare_requires_review")
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY, "approval": APPROVAL,
            "method_artifact": self.ledger.artifacts.put_bytes(SPEC.read_bytes()), "source_binding": source_module.binding()}
        intent = self.retain(session, INTENT, METHOD, desired)
        registered = {kind: self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"]
            for kind, value in versions(desired).items()}
        seed = {"method": METHOD, "intent": intent, "seed": new_seed(), "draw_performed": False}
        seed_record = self.retain(session, SEED, intent, seed)
        imported = source_module.collect(self, session)
        self.set_scope(imported)
        selection = design.build_plan(imported, seed["seed"], stop_after_positive=True)
        quote = self.quote(imported["source"], selection, self.counter(), desired["implementation"])
        self.guard(desired["implementation"])
        value = {**desired, "intent": intent, "seed_record": seed_record, "versions": registered,
            "import_artifact": self.ledger.artifacts.put(imported), "selection_artifact": self.ledger.artifacts.put(selection),
            "quote_artifact": self.ledger.artifacts.put(quote), "diagnostic_artifact": self.ledger.artifacts.put(imported["diagnostic"])}
        plan = {"id": self.retain(session, PLAN, METHOD, value), **value}
        self._state = empty_state()
        return self.summary(plan)

    def load_plan(self):
        plan, intent, seed = self.one(PLAN), self.one(INTENT), self.one(SEED)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY and plan["approval"] == APPROVAL,
            "plan_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k,v in intent.items() if k != "id"), "intent_binding")
        require(seed["intent"] == intent["id"] and seed["method"] == METHOD and seed["draw_performed"] is False
            and plan["seed_record"] == seed["id"], "seed_binding")
        require(self.ledger.artifacts.read_bytes(plan["method_artifact"]) == SPEC.read_bytes(), "method_changed")
        imported = self.ledger.artifacts.read(plan["import_artifact"])
        self.set_scope(imported)
        selection = self.ledger.artifacts.read(plan["selection_artifact"])
        require(selection == design.build_plan(imported, seed["seed"], stop_after_positive=True), "selection_changed")
        require(self.ledger.artifacts.read(plan["diagnostic_artifact"]) == imported["diagnostic"], "diagnostic_changed")
        quote = self.ledger.artifacts.read(plan["quote_artifact"])
        totals = Counter()
        for row in quote["rectangles"]:
            totals.update(row["quote"])
        require(quote["method"] == METHOD and quote["selection_digest"] == selection["digest"]
            and [r["descriptor_digest"] for r in quote["rectangles"]] == [d["digest"] for d in selection["descriptors"]]
            and quote["total"] == dict(totals), "quote_binding")
        self.completed_prepare(plan)
        return plan, imported, selection

    def completed_prepare(self, plan):
        created = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (plan["id"],)).fetchone()[0]
        session = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (created,)).fetchone()[0]
        events = [dict(e) for e in self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session,))]
        selected = {k: [e for e in events if e["kind"] == k] for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
        require(not selected["operation.failed"] and all(len(selected[k]) == 1 for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended")), "prepare_not_completed")
        start, incoming, done, ended = (selected[k][0] for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended"))
        seed_seq = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (plan["seed_record"],)).fetchone()[0]
        require(start["seq"] < incoming["seq"] < seed_seq < created < done["seq"] < ended["seq"]
            and json.loads(ended["payload"]) == {"status": "completed"}, "prepare_chronology")
        intended, completed = json.loads(incoming["payload"]), json.loads(done["payload"])
        require(intended["operation"] == completed["operation"] == "status"
            and self.ledger.artifacts.read(intended["input"]) == {"action": "prepare"}, "prepare_operation")
        result = self.ledger.artifacts.read(completed["result"])
        require(result.get("method") == METHOD and result.get("plan") == plan["id"] and result.get("prepared") is True
            and result.get("attempted_requests") == 0, "prepare_result")
        identity = self.ledger.artifacts.read(json.loads(start["payload"])["identity"])
        require(all(identity["code_files"].get(p) == h for p,h in plan["implementation"].items()
            if p.startswith("src/") and p.endswith(".py")), "prepare_runtime_identity")
        expected = versions({k:v for k,v in self.one(INTENT).items() if k != "id"})
        require(set(plan["versions"]) == set(expected), "version_scope")
        for kind, reference in plan["versions"].items():
            require(self.ledger.get(reference, kind)["content"] == expected[kind], "version_content")
            seq = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (reference,)).fetchone()[0]
            require(incoming["seq"] < seq < seed_seq, "version_chronology")

    def summary(self, plan):
        s = self._state
        quote = self.ledger.artifacts.read(plan["quote_artifact"])
        return {"method": METHOD, "plan": plan["id"], "prepared": True, "observed_at": utc(), "policy": POLICY,
            "attempted_requests": len(s["intents"]), "returned_requests": s["returned_requests"],
            "usable_requests": sum(r["usable"] and r["attempt"] in s["completed"] for r in s["responses"].values()),
            "attempted_unique_pairs": len(s["attempted_pairs"]), "usable_pair_observations": len(s["observations"]),
            "new_settled_nanousd": s["settled_nanousd"], "new_held_nanousd": s["held_nanousd"],
            "new_committed_nanousd": s["settled_nanousd"]+s["held_nanousd"], "unknown_holds": s["unknown_holds"],
            "prior_repair_commitment_nanousd": PRIOR_COMMITMENT,
            "validation_remaining_nanousd": VALIDATION_CAP-s["settled_nanousd"]-s["held_nanousd"],
            "health": s["health"], "quote_artifact": plan["quote_artifact"],
            "offline_quote": {k:v for k,v in quote.items() if k != "rectangles"},
            "selection_artifact": plan["selection_artifact"], "diagnostic_artifact": plan["diagnostic_artifact"],
            "membership_changes": 0}

    @staticmethod
    def active(selection, state):
        positive = {i for r in state["observations"].values() if r["label"] == "same_event" for i in r["pair"]}
        return set(selection["selection"]["sample_ids"]) - positive

    @staticmethod
    def execution_descriptor(parent, attempted_pairs):
        keys = {contract.pair_key(*pair) for pair in design.descriptor_pairs(parent)}
        excluded = sorted(keys & set(attempted_pairs))
        value = {k:v for k,v in parent.items() if k != "digest"}
        value.update(parent_descriptor_digest=parent["digest"], already_attempted_pair_keys=excluded,
            prior_blocked_pair_keys=sorted(set(parent["prior_blocked_pair_keys"]) | set(excluded)))
        return {**value, "digest": digest(value)}

    def admission_scope(self, packet, selection):
        require(packet["kind"] == "decisions" and packet["role"] == "final_reference"
            and not {b["document_id"] for b in packet["source_bindings"].values()} & self._quarantine, "quarantined_packet")
        require(not set(packet["logical_ids"]) & (self._prior_logical_ids | self._state["logical_attempted"])
            and packet["task_key"] not in self._prior_task_keys, "logical_retry")
        require(packet["request_sha256"] == digest(packet["request"])
            and packet["reservation_nanousd"] == contract.reservation(packet), "packet_binding")
        require(all(selection["selection"]["source_bindings"].get(b["document_id"]) == b["input_sha256"]
            for b in packet["source_bindings"].values()), "source_binding")

    def provider(self, session, plan, packets):
        known = {p["request_sha256"]: p for p in packets}
        def before(invocation):
            try:
                with self._pace_lock:
                    require_active(self, session)
                    self.guard(plan["implementation"])
                    require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                    p = known.get(digest(invocation.request))
                    require(p is not None and invocation.kind == "decisions", "wire_binding")
                    while time.monotonic() < self._next_dispatch:
                        self.guard()
                        require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                        time.sleep(min(.2, max(0, self._next_dispatch-time.monotonic())))
                    self.guard()
                    require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                    self._next_dispatch = time.monotonic()+max(60/RPM, p["input_tokens_proxy"]*1.25*60/TPM)
                    return True
            except AuditError:
                self._dispatch_stop.set()
                raise
        return transport.UnifiedTransport(before_dispatch=before)

    def dispatch_wave(self, session, plan, selection, queues, packets):
        s, wave, intended = self._state, [], []
        for p, queue in zip(packets, queues, strict=True):
            self.guard(plan["implementation"])
            self.admission_scope(p, selection)
            require(s["settled_nanousd"]+s["held_nanousd"]+p["reservation_nanousd"] <= VALIDATION_CAP, "validation_budget")
            attempt = str(uuid.uuid4())
            call = wire.Invocation(p["request"], attempt, kind="decisions")
            i = {"method": METHOD, "attempt": attempt, "task_key": p["task_key"], "number": 1, "batch": plan["id"],
                "queue": queue["id"], "category": "validation", "started_at": utc(),
                "packet": self.ledger.artifacts.put(p), "request": self.ledger.artifacts.put(p["request"]),
                "dispatch": self.ledger.artifacts.put(call.manifest()), "reserved_nanousd": p["reservation_nanousd"]}
            self.ledger.append(session, "model.attempt.intended", i)
            self.ledger.unresolved[attempt] = i
            s["intents"][p["task_key"]] = i
            s["logical_attempted"].update(p["logical_ids"])
            s["attempted_pairs"].update({r["pair_key"]: {**r, "attempt": attempt} for r in p["pair_entries"]})
            s["held_nanousd"] += p["reservation_nanousd"]
            s["unknown_holds"] += 1
            wave.append((call, attempt))
            intended.append(i)
        provider = self.provider(session, plan, packets)
        for n, response in self.gateway.codex_dispatch(session, provider, wave, workers=MAX_WORKERS):
            i, p = intended[n], packets[n]
            raw = self.ledger.artifacts.put(asdict(response))
            self.ledger.append(session, RECEIVED, {"attempt": i["attempt"], "response": raw})
            derived, parsed = outcome(p, response)
            value = {"plan": plan["id"], "attempt": i["attempt"], "task_key": i["task_key"], "response": raw,
                "parsed": self.ledger.artifacts.put(parsed) if parsed is not None else None, **derived}
            identity = self.ledger.record(session, RESPONSE, i["attempt"], value)
            s["responses"][i["task_key"]] = {"id": identity, **value}
            s["returned_requests"] += 1
            if not derived["hold"]:
                self.complete(session, i, raw, identity, "valid" if derived["usable"] else "invalid")
                s["completed"].add(i["attempt"])
                s["held_nanousd"] -= i["reserved_nanousd"]
                s["settled_nanousd"] += derived["cost_nanousd"]
                s["unknown_holds"] -= 1
                if derived["usable"]:
                    s["observations"].update({r["pair_key"]: {**r, "physical_attempt": i["attempt"],
                        "assessment": identity, "response": raw} for r in parsed["observations"]})
            else:
                s["held_nanousd"] += max(0, (derived["cost_nanousd"] or 0)-i["reserved_nanousd"])
            if derived["fatal"]:
                self._dispatch_stop.set()
        s["health"] = prior.health_state(s["intents"], s["responses"])
        self.progress(stage="search", attempted_requests=len(s["intents"]), returned_requests=s["returned_requests"],
            active_sampled_articles=len(self.active(selection, s)), settled_nanousd=s["settled_nanousd"], held_nanousd=s["held_nanousd"])

    def run(self, session, plan, imported, selection):
        require(not self.one(LAUNCH, optional=True) and not self._state["intents"], "interrupted_run_requires_review")
        self.retain(session, LAUNCH, plan["id"], {"method": METHOD, "plan": plan["id"], "implementation": plan["implementation"],
            "started_at": utc(), "validation_cap_nanousd": VALIDATION_CAP})
        count, stop, position, wave_number = self.counter(), "all_rectangles_processed", 0, 0
        unavailable = {}
        while position < len(selection["descriptors"]):
            self.guard(plan["implementation"])
            active = self.active(selection, self._state)
            if not active:
                stop = "all_sampled_articles_have_positive_witness"
                break
            if self._state["health"]["stop_reason"]:
                stop = self._state["health"]["stop_reason"]
                break
            packets, queues, earmark, budget_blocked = [], [], 0, False
            limit = MAX_WORKERS if self._state["intents"] else 1
            # One active snapshot applies to all intents reserved before this wave.
            # Pack consecutive rectangles together; complete earlier waves first.
            while position < len(selection["descriptors"]) and len(packets) < limit:
                parent = selection["descriptors"][position]
                descriptor = self.execution_descriptor(parent, self._state["attempted_pairs"])
                bundle = design.packet(imported["source"], descriptor, count, active_sample_ids=active)
                known = unavailable.setdefault(parent["digest"], {})
                known.update({r["pair_key"]: r for r in bundle["unavailable"]
                    if r["pair_key"] not in self._state["attempted_pairs"]})
                selected = []
                for p in bundle["packets"][:limit-len(packets)]:
                    if self._state["settled_nanousd"]+self._state["held_nanousd"]+earmark+p["reservation_nanousd"] > VALIDATION_CAP:
                        budget_blocked = True
                        break
                    selected.append(p)
                    earmark += p["reservation_nanousd"]
                if selected:
                    value = {"method": METHOD, "plan": plan["id"], "parent_descriptor_digest": parent["digest"],
                        "execution_descriptor": descriptor, "active_sample_ids": sorted(active),
                        "packet_artifacts": [self.ledger.artifacts.put(p) for p in selected], "wave": wave_number}
                    q = {"id": self.retain(session, QUEUE, digest([plan["id"], parent["digest"], wave_number]), value), **value}
                    packets.extend(selected)
                    queues.extend([q]*len(selected))
                complete_rectangle = len(selected) == len(bundle["packets"])
                del bundle, selected
                if complete_rectangle:
                    position += 1
                else:
                    break
            if packets:
                self.dispatch_wave(session, plan, selection, queues, packets)
                wave_number += 1
            if self._state["health"]["stop_reason"]:
                stop = self._state["health"]["stop_reason"]
                break
            if not self.active(selection, self._state):
                stop = "all_sampled_articles_have_positive_witness"
                break
            if budget_blocked and not packets:
                stop = "validation_budget_bound"
                break
            if not packets and position < len(selection["descriptors"]):
                raise AuditError("luna_unresolved_audit_search_made_no_progress")
        for descriptor_digest, rows in unavailable.items():
            self.retain(session, CHECKPOINT, descriptor_digest, {"plan": plan["id"], "descriptor_digest": descriptor_digest,
                "unavailable": list(rows.values())})
        return self.report(session, plan, imported, selection, stop)

    def census(self, plan, selection):
        """Replay executed evidence only; never load an unattempted packet matrix."""
        s, attempts, receipts, assessments, completions = empty_state(), {}, {}, {}, {}
        parents = {d["digest"]: d for d in selection["descriptors"]}
        queues = {q["id"]: q for q in self.rows(QUEUE)}
        launch = self.one(LAUNCH, optional=True)
        launch_session, launch_seq = None, None
        if launch:
            require(launch["method"] == METHOD and launch["plan"] == plan["id"]
                and launch["implementation"] == plan["implementation"] and launch["validation_cap_nanousd"] == VALIDATION_CAP,
                "launch_binding")
            launch_seq = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (launch["id"],)).fetchone()[0]
            launch_session = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (launch_seq,)).fetchone()[0]
            starts = self.ledger.db.execute("SELECT seq,payload FROM events WHERE session_id=? AND kind='session.started'", (launch_session,)).fetchall()
            operations = self.ledger.db.execute("SELECT seq,payload FROM events WHERE session_id=? AND kind='operation.intended'", (launch_session,)).fetchall()
            require(len(starts) == len(operations) == 1 and starts[0][0] < operations[0][0] < launch_seq, "launch_prefix")
            incoming = json.loads(operations[0][1])
            require(incoming["operation"] == "status" and self.ledger.artifacts.read(incoming["input"]) ==
                {"action": "run", "allow_paid_execution": True}, "launch_operation")
            identity = self.ledger.artifacts.read(json.loads(starts[0][1])["identity"])
            require(all(identity["code_files"].get(p) == h for p,h in plan["implementation"].items()
                if p.startswith("src/") and p.endswith(".py")), "launch_runtime_identity")
        for q in queues.values():
            event = self.ledger.db.execute("SELECT r.created_event,e.session_id FROM records r JOIN events e ON e.seq=r.created_event WHERE r.id=?", (q["id"],)).fetchone()
            require(launch and q["method"] == METHOD and q["plan"] == plan["id"] and q["parent_descriptor_digest"] in parents
                and event[0] > launch_seq and event[1] == launch_session, "queue_prefix")
        for e in self.ledger.db.execute("SELECT seq,session_id,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            i = json.loads(e[2])
            require(i["method"] == METHOD and i["batch"] == plan["id"] and i["category"] == "validation" and i["number"] == 1
                and i["attempt"] not in attempts and i["task_key"] not in s["intents"]
                and launch and e[0] > launch_seq and e[1] == launch_session, "intent_scope_or_retry")
            attempts[i["attempt"]], s["intents"][i["task_key"]] = i, i
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind=? ORDER BY seq", (RECEIVED,)):
            r = json.loads(e[0])
            require(r["attempt"] in attempts and r["attempt"] not in receipts, "receipt_scope")
            receipts[r["attempt"]] = r
        for r in self.rows(RESPONSE):
            require(r["attempt"] in attempts and r["attempt"] not in assessments and r["plan"] == plan["id"]
                and r["task_key"] == attempts[r["attempt"]]["task_key"], "assessment_scope")
            assessments[r["attempt"]] = r
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.completed' ORDER BY seq"):
            r = json.loads(e[0])
            require(r["attempt"] in attempts and r["attempt"] not in completions, "completion_scope")
            completions[r["attempt"]] = r
        # Snapshot active state for each physical wave, before consuming its results.
        seen_queues, wave_active, health_rows = set(), {}, {}
        for attempt, i in attempts.items():
            q = queues.get(i["queue"])
            require(q is not None and q["method"] == METHOD and q["plan"] == plan["id"]
                and q["parent_descriptor_digest"] in parents and i["packet"] in q["packet_artifacts"], "queue_binding")
            if q["id"] not in seen_queues:
                if q["wave"] not in wave_active:
                    require(type(q["wave"]) is int and q["wave"] == len(wave_active), "wave_order")
                    wave_active[q["wave"]] = sorted(self.active(selection, s))
                require(q["execution_descriptor"] == self.execution_descriptor(parents[q["parent_descriptor_digest"]], s["attempted_pairs"])
                    and q["active_sample_ids"] == wave_active[q["wave"]], "execution_descriptor_derivation")
                seen_queues.add(q["id"])
            p = self.ledger.artifacts.read(i["packet"])
            self.admission_for_replay(p, selection, s)
            eligible = {contract.pair_key(*pair) for pair in design.descriptor_pairs(q["execution_descriptor"])
                if set(pair) & set(q["active_sample_ids"])} - set(q["execution_descriptor"]["prior_blocked_pair_keys"])
            require(i["task_key"] == p["task_key"] and i["request"] == p["request_sha256"] and i["packet"] == digest(p)
                and i["reserved_nanousd"] == p["reservation_nanousd"] and p["descriptor_digest"] == q["execution_descriptor"]["digest"]
                and p["active_sample_ids"] == q["active_sample_ids"] and set(p["pair_keys"]) <= eligible,
                "intent_packet_binding")
            require(self.ledger.artifacts.read(i["request"]) == p["request"] and self.ledger.artifacts.read(i["dispatch"]) ==
                wire.Invocation(p["request"], attempt, kind="decisions").manifest(), "physical_wire")
            s["logical_attempted"].update(p["logical_ids"])
            s["attempted_pairs"].update({r["pair_key"]: {**r, "attempt": attempt} for r in p["pair_entries"]})
            receipt, a, derived, parsed = receipts.get(attempt), assessments.get(attempt), None, None
            if receipt:
                derived, parsed = outcome(p, ProviderResponse(**self.ledger.artifacts.read(receipt["response"])))
                health_rows[i["task_key"]] = {**derived, "usable": False}
            if a:
                require(receipt and a["response"] == receipt["response"] and a["parsed"] == (digest(parsed) if parsed is not None else None)
                    and all(digest(a.get(k)) == digest(v) for k,v in derived.items()), "assessment_replay")
                if a["parsed"]:
                    require(self.ledger.artifacts.read(a["parsed"]) == parsed, "parsed_bytes")
                s["responses"][i["task_key"]], health_rows[i["task_key"]] = a, a
            cost = derived["cost_nanousd"] if derived else None
            if attempt in completions:
                c = completions[attempt]
                require(a and not a["hold"] and c["assessment"] == a["id"] and c["response"] == a["response"], "completion_binding")
                s["completed"].add(attempt)
                s["settled_nanousd"] += cost
                if a["usable"]:
                    s["observations"].update({r["pair_key"]: {**r, "physical_attempt": attempt,
                        "assessment": a["id"], "response": a["response"]} for r in parsed["observations"]})
            else:
                s["held_nanousd"] += max(i["reserved_nanousd"], cost or 0)
                s["unknown_holds"] += 1
                if i["task_key"] in health_rows:
                    health_rows[i["task_key"]] = {**health_rows[i["task_key"]], "usable": False}
        require(set(self.ledger.unresolved) == set(attempts)-s["completed"], "orphan_inventory")
        ordered_health = {attempts[a]["task_key"]: health_rows[attempts[a]["task_key"]] for a in receipts}
        s["returned_requests"], s["health"] = len(receipts), prior.health_state(s["intents"], ordered_health)
        return s

    def admission_for_replay(self, p, selection, state):
        require(p["kind"] == "decisions" and p["role"] == "final_reference" and p["method"] == design.METHOD
            and p["request_sha256"] == digest(p["request"]) and p["reservation_nanousd"] == contract.reservation(p)
            and p["selection_digest"] == selection["selection"]["digest"], "replayed_packet_contract")
        require(not set(p["logical_ids"]) & (state["logical_attempted"] | self._prior_logical_ids)
            and p["task_key"] not in self._prior_task_keys, "replayed_logical_retry")
        require(not {b["document_id"] for b in p["source_bindings"].values()} & self._quarantine
            and all(selection["selection"]["source_bindings"].get(b["document_id"]) == b["input_sha256"]
                for b in p["source_bindings"].values()), "replayed_source_scope")
        require(p["task_key"] == digest([design.METHOD, p["descriptor_digest"], p["logical_ids"], p["request_sha256"]]), "replayed_task_identity")
        encoded = canonical(p["request"])
        require(p["wire_bytes"] == len(encoded.encode("utf-8")) <= design.MAX_WIRE_BYTES
            and p["input_tokens_proxy"] == self.counter()(encoded) <= design.MAX_TOKENS, "replayed_capacity")
        # The strict helper checks the entire immutable request before inspecting answers.
        # A valid synthetic unknown response validates that structure without creating evidence.
        answers = [{"name": q["name"], "type": "choice", "choice": q["choices"][-1]["value"],
            "confidence": 1.0, "probabilities": [{"value": c["value"], "probability": float(c == q["choices"][-1])} for c in q["choices"]]}
            for q in p["request"]["questions"]]
        design.parse(p, {"model": contract.base.MODEL, "answers": answers})

    def completed_result(self, result):
        created = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (result["id"],)).fetchone()[0]
        session = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (created,)).fetchone()[0]
        events = [dict(e) for e in self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session,))]
        kinds = ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")
        rows = {k: [r for r in events if r["kind"] == k] for k in kinds}
        require(not rows["operation.failed"] and all(len(rows[k]) == 1 for k in kinds[:-1]), "report_not_completed")
        start, intended, completed, ended = (rows[k][0] for k in kinds[:-1])
        require(start["seq"] < intended["seq"] < created < completed["seq"] < ended["seq"]
            and json.loads(ended["payload"]) == {"status": "completed"}, "report_chronology")
        incoming, output = json.loads(intended["payload"]), json.loads(completed["payload"])
        data = self.ledger.artifacts.read(incoming["input"])
        require(incoming["operation"] == output["operation"] == "status" and data in
            ({"action": "run", "allow_paid_execution": True}, {"action": "report"})
            and self.ledger.artifacts.read(output["result"]) == result, "report_completion_binding")
        identity = self.ledger.artifacts.read(json.loads(start["payload"])["identity"])
        require(all(identity["code_files"].get(p) == h for p,h in self.one(PLAN)["implementation"].items()
            if p.startswith("src/") and p.endswith(".py")), "report_runtime_identity")
        for field in ("new_settled_nanousd", "new_held_nanousd", "new_committed_nanousd", "attempted_requests", "returned_requests"):
            require(result[field] == self.summary(self.one(PLAN))[field], "report_accounting_changed")
        for field in ("statistical_summary_artifact", "observations_artifact", "pair_coverage_artifact"):
            self.ledger.artifacts.read(result[field])

    def report(self, session, plan, imported, selection, stop="operator_report_without_continuation"):
        s, coverage_index = self._state, []
        checkpoints = {r["descriptor_digest"]: r for r in self.rows(CHECKPOINT)}
        active = self.active(selection, s)
        coverage_counts = {i: Counter() for i in selection["selection"]["sample_ids"]}
        for descriptor in selection["descriptors"]:
            self.guard()
            saved = checkpoints.get(descriptor["digest"], {})
            unavailable = {r["pair_key"]: r for r in saved.get("unavailable", [])}
            rows = []
            for pair in design.descriptor_pairs(descriptor):
                pair = sorted(pair)
                key = contract.pair_key(*pair)
                observed, physical = s["observations"].get(key), s["attempted_pairs"].get(key)
                if observed:
                    reason = "observed_"+observed["label"]
                elif physical:
                    reason = "physical_outcome_unknown_or_unusable"
                elif set(pair) & self._quarantine:
                    reason = "quarantined_source"
                elif key in descriptor["prior_blocked_pair_keys"]:
                    reason = "prior_final_reference_attempt"
                elif key in unavailable:
                    reason = unavailable[key]["reason"]
                elif not active.intersection(pair):
                    reason = "not_needed_after_positive"
                else:
                    reason = stop if stop != "all_rectangles_processed" else "unasked_unknown"
                row = {"pair": pair, "pair_key": key, "reason": reason,
                    "physical_attempt": physical["attempt"] if physical else None}
                rows.append(row)
                for i in set(pair) & set(coverage_counts):
                    coverage_counts[i][reason] += 1
            reference = self.ledger.artifacts.put(rows)
            coverage_index.append({"descriptor_digest": descriptor["digest"], "artifact": reference, "pairs": len(rows)})
        require(sum(r["pairs"] for r in coverage_index) == selection["expected_unique_pairs"], "coverage_partition")
        statistics = design.summarize(selection["selection"], s["observations"])
        for i, row in statistics["articles"].items():
            row["coverage_reasons"] = dict(sorted(coverage_counts[i].items()))
            row["positive_witnesses"] = [{k: s["observations"][contract.pair_key(i, partner)][k]
                for k in ("pair_key", "physical_attempt", "assessment", "response")} for partner in row["positive_partners"]]
        result = {**self.summary(plan), "audit_finished": True, "stop_reason": stop,
            "statistical_summary_artifact": self.ledger.artifacts.put(statistics), "statistical_summary": statistics["summary"],
            "sample_identification_interval": statistics["sample_identification_interval"],
            "confidence_interval_95": statistics["confidence_interval_95"], "point_estimate": statistics["point_estimate"],
            "sample_outcomes": statistics["articles"],
            "observations_artifact": self.ledger.artifacts.put(s["observations"]),
            "pair_coverage_artifact": self.ledger.artifacts.put({"selection_digest": selection["digest"], "rectangles": coverage_index,
                "unique_pairs": sum(r["pairs"] for r in coverage_index)}),
            "historical_fatal_preserved": imported["diagnostic"]["fatal_cases"],
            "quarantined_inputs": len(self._quarantine), "source_state_sha256": digest(imported["state"]),
            "model_reference_not_human_truth": True, "whole_pipeline_recall": None}
        self.guard(plan["implementation"])
        identity = self.retain(session, RESULT, plan["id"], result)
        self.progress(stage="report", audit_finished=True, statistical_summary=statistics["summary"],
            committed_nanousd=result["new_committed_nanousd"])
        return {"id": identity, **result}

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        finished, started = threading.Event(), time.monotonic()
        self.progress(stage=data["action"], elapsed_seconds=0)
        def heartbeat():
            while not finished.wait(30):
                try:
                    self.progress(elapsed_seconds=round(time.monotonic()-started, 3))
                except Exception as error:
                    self._progress_failures.append(type(error).__name__)
                    break
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if data["action"] == "prepare":
                return self.prepare(session, context)
            plan, imported, selection = self.load_plan()
            self._state = self.census(plan, selection)
            result = self.one(RESULT, optional=True)
            if result:
                self.completed_result(result)
                return result
            if data["action"] == "status":
                return self.summary(plan)
            if data["action"] == "report":
                return self.report(session, plan, imported, selection)
            require(not self.config.offline and data["allow_paid_execution"] is True and bool(os.environ.get("OPENAI_API_KEY")), "paid_authority_and_key")
            self.guard(plan["implementation"])
            return self.run(session, plan, imported, selection)
        finally:
            finished.set()
            thread.join(timeout=2)
            self._state = None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "status", "report"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require(args.action == "run" or not args.allow_paid_execution, "paid_flag_scope")
    engine = Audit(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {"action": args.action}
        if args.action == "run":
            data["allow_paid_execution"] = args.allow_paid_execution
        print(json.dumps(engine.execute("status", data, objective="Measure same-event partner existence for a fixed random unresolved sample",
            actor="codex:luna-unresolved-audit")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
