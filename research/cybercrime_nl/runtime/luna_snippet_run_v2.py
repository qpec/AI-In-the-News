"""Audited five-packet snippet pilot; no old study restart or automatic rollout."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

import dossier_transport as wire
import dossier_transport_v9 as transport
import luna_quality_audit as prior
import luna_recall_contract as contract
import luna_recall_repair as repair
import luna_recall_run_v2 as old
import luna_snippet_grouping as grouping
import luna_snippet_source_v2 as source_module
from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_SNIPPET_GROUPING_V2.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-snippet-pilot-20261025-v2"
INTENT, PLAN, QUEUE, RESPONSE, CHECKPOINT, RESULT = ("luna_snippet_"+s for s in
    ("intent", "plan", "queue", "response", "checkpoint", "result"))
FX, PRIOR_COMMITMENT = 1_119_300_000, 3_605_901_656
PILOT_CAP, REPAIR_CAP = 2*FX, 25*FX
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
POLICY = {"pilot_cap_nanousd": PILOT_CAP, "repair_cap_nanousd": REPAIR_CAP,
    "prior_commitment_nanousd": PRIOR_COMMITMENT, "usd_per_eur_nano": FX,
    "max_proposal_packets": 5, "max_article_occurrences": 500, "max_workers": MAX_WORKERS,
    "effective_deadline": None, "automatic_full_rollout": False, "technical_retries": 0,
    "threshold": .85, "threshold_validated": False, "input_max_nanousd_per_token": 138,
    "response_output_nanousd_per_token": 550, "validation_eur_reserved": 12.5, "reserve_eur": 12.5}
APPROVAL = {"instruction": "Implement the proposed plan.",
    "approval_event": "0e0729dca3f2eb10843f8fcd",
    "approval_payload_sha256": "09059157ae3081e1e803b9d37524da41761b205d717b90057d6652f79ee63f9d",
    "approved_plan_event": "f55ee78d80e0c0184d8e99ed",
    "approved_plan_payload_sha256": "5d969edda0768c74a32d9c29548f9f01fb654e083b298b3d6c72fe755ccf4863",
    "pilot_first_no_deadline_event": "622aa68cf083e1e8677e6855"}


def require(value, reason):
    if not value:
        raise AuditError("luna_snippet_"+reason)


def implementation():
    files = [Path(__file__), Path(grouping.__file__), Path(source_module.__file__), Path(transport.__file__),
        SPEC, SPEC.with_name("LUNA_SNIPPET_GROUPING.md"), Path(__file__).with_name("luna_snippet_run.py"),
        Path(__file__).with_name("run_luna_snippet_v2_with_key.ps1"), ROOT / "scripts/windows_key_store.cs"]
    return {**old.implementation(), **source_module.implementation(),
        **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def safe_code(error):
    text = str(error)
    return text if re.fullmatch(r"[a-z][a-z0-9_]{1,120}", text) else type(error).__name__


def outcome(packet, response):
    raw, parsed, error = response.raw_response or {}, None, None
    cost = prior.observed_cost(response)
    if packet["kind"] == "responses" and cost is not None:
        output = response.usage.get("output_tokens")
        cost = (cost + output*contract.OUTPUT_PRICE*(3 if response.usage["input_tokens"] > contract.LONG_THRESHOLD else 2)//2
            if type(output) is int and 0 <= output <= 1_050_000 else None)
    if response.payload is not None:
        try:
            if packet["role"] == "snippet_proposal":
                parsed = grouping.parse(packet, response.payload)
            elif packet["role"] == "group_membership":
                parsed = contract.parse_members(packet, response.payload)
            else:
                parsed = contract.focal.parse_card_quality(packet, response.payload)
        except (ResearchError, AuditError, KeyError, TypeError, ValueError, AttributeError) as exc:
            error = safe_code(exc)
    hold = bool(raw.get("unknown_outcome")) or cost is None or cost > packet["reservation_nanousd"]
    usable = not hold and parsed is not None and raw.get("http_status") == 200 and response.model == contract.base.MODEL
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
    return {"cost_nanousd": cost, "hold": hold, "usable": usable, "fatal": fatal,
        "validation_error": error, "failure_stage": raw.get("failure_stage"), "failure_code": raw.get("failure_code"),
        "http_status": raw.get("http_status"), "dispatch_started": raw.get("dispatch_started"),
        "members_supported": bool(usable and packet["role"] == "group_membership" and parsed["usable"]),
        "group_supported": bool(usable and packet["kind"] == "responses" and parsed["usable"])}, parsed


def fits(committed, reservation):
    return committed+reservation <= PILOT_CAP and PRIOR_COMMITMENT+committed+reservation <= REPAIR_CAP


def versions(desired):
    return {"protocol": desired, "question": {"text": "Pilot snippet assignment for atomic dossier and unassigned units"},
        "selection": {"rules": "Five deterministic overlapping menus, at most 500 article appearances; no rollout"},
        "dossier_definition": {"unit": "One bounded focal occurrence under unchanged complete production rules"},
        "prompt": {"instructions": contract.focal.FOCUS_RULES}, "codebook": {"labels": ["keep", "unknown", "visible_unit_id"]},
        "profile": {"mode": "exploratory", "population_estimate": False}, "policy": POLICY}


def development_comparison(imported, selection, links, successor):
    """Selected retained evidence only; model proposal choices are not pair truth."""
    unit_by_doc = {i: u for u,v in selection["units"].items() for i in v["members"]}
    visible = {tuple(sorted(pair)) for p in selection["packets"] for pair in p["visible_unit_pairs"]}
    direct = {tuple(sorted((r["source"], r["target"]))) for r in links}
    final = {i: g for g,members in successor["groups"].items() if g in successor["accepted_group_ids"] for i in members}
    labels = {}
    for row in imported["history"].get("pair_observations", []):
        if row.get("compatible_focal_rubric") and row.get("label") in {"same_event", "negative"}:
            pair = tuple(sorted(row["pair"]))
            labels.setdefault(pair, set()).add(row["label"])
    counts = Counter()
    for pair, outcomes in labels.items():
        a,b = pair
        units = tuple(sorted((unit_by_doc[a], unit_by_doc[b])))
        if units[0] == units[1]:
            continue
        label = "negative" if "negative" in outcomes else "positive"
        counts["retained_cross_unit_"+label] += 1
        if units in visible:
            counts["visible_"+label] += 1
            if units in direct:
                counts["directly_proposed_"+label] += 1
            if final.get(a) is not None and final.get(a) == final.get(b):
                counts["accepted_"+label] += 1
    return {"counts": dict(counts), "independent_evaluation": False,
        "population_recall_estimated": False, "negative_conflicts_preserved": True}


def statistics(state):
    accepted = set(state["accepted_group_ids"])
    sizes = Counter(len(state["groups"][g]) for g in accepted)
    provisional = Counter(len(m) for g,m in state["groups"].items() if g not in accepted)
    return {"accepted_groups": len(accepted), "accepted_singletons": sizes.get(1, 0),
        "accepted_multi": sum(n for k,n in sizes.items() if k > 1),
        "accepted_inputs": sum(len(state["groups"][g]) for g in accepted),
        "provisional_groups": len(state["groups"])-len(accepted), "unresolved_inputs": len(state["unresolved_ids"]),
        "provisional_singletons": provisional.get(1, 0), "provisional_multi": sum(n for k,n in provisional.items() if k > 1),
        "accepted_size_histogram": dict(sorted(sizes.items())),
        "coassigned_pairs": sum(len(state["groups"][g])*(len(state["groups"][g])-1)//2 for g in accepted)}


class Pilot(Research):
    rows, one, complete, retain, checkpoint = prior.Audit.rows, prior.Audit.one, prior.Audit.complete, old.Recall.retain, old.Recall.checkpoint

    def __init__(self, root, *, config=None):
        root = Path(root)
        require(root.name == OWNER_NAME, "separate_owner")
        super().__init__(root, config=config or Config(offline=True))
        self._progress_lock = threading.Lock()
        self._progress_state, self._progress_failures = {}, []
        self._dispatch_stop = threading.Event()
        self._next_dispatch, self._state = time.monotonic(), None

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and data.get("action") in {"prepare", "run", "status"}, "operation")
        expected = {"action", "allow_paid_execution"} if data["action"] == "run" else {"action"}
        require(set(data) == expected, "operation_fields")
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
            self._state = self.census(plan)
            result = self.one(RESULT, optional=True)
            if result:
                return result
            if data["action"] == "status":
                return self.summary(plan)
            require(not self.config.offline and data["allow_paid_execution"] is True and bool(os.environ.get("OPENAI_API_KEY")), "paid_authority_and_key")
            require(not self._state["intents"], "interrupted_pilot_requires_review")
            return self.run(session, plan, imported, selection)
        finally:
            finished.set()
            thread.join(timeout=2)
            self._state = None

    def prepare(self, session, context):
        require(self.config.offline, "offline_prepare")
        previous = self.one(PLAN, optional=True)
        if previous:
            plan, _, _ = self.load_plan()
            self._state = self.census(plan)
            return self.summary(plan)
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY, "approval": APPROVAL,
            "method_artifact": self.ledger.artifacts.put_bytes(SPEC.read_bytes()), "source_report": source_module.REPORT}
        intent = self.retain(session, INTENT, METHOD, desired)
        registered = {}
        for kind, value in versions(desired).items():
            registered[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"]
        imported = source_module.collect(self, session)
        require(imported["prior_commitment_nanousd"] == PRIOR_COMMITMENT, "prior_cost_binding")
        encoder = offline_tokenizer()
        selection = grouping.prepare(imported["source"], imported["state"], lambda t: len(encoder.encode(t, disallowed_special=())))
        self.verify_selection(selection)
        self.guard(desired["implementation"])
        value = {**desired, "intent": intent, "versions": registered,
            "import_artifact": self.ledger.artifacts.put(imported), "selection_artifact": self.ledger.artifacts.put(selection)}
        plan = {"id": self.retain(session, PLAN, METHOD, value), **value}
        self._state = self.census(plan)
        return self.summary(plan)

    @staticmethod
    def verify_selection(selection):
        packets = selection["packets"]
        require(0 < len(packets) <= 5, "proposal_packet_limit")
        # Every packet supplies exact article snippet rows once, even across repeated windows.
        occurrences = 0
        keys = set()
        for packet in packets:
            displayed = json.loads(packet["request"]["input"])["units"]
            ids = [a["document_id"] for u in displayed for a in u["articles"]]
            require(len(ids) == len(set(ids)) and sorted(ids) == packet["article_ids"]
                and len(ids) == packet["article_occurrences"], "article_binding")
            require(packet["task_key"] not in keys, "duplicate_packet")
            keys.add(packet["task_key"])
            occurrences += len(ids)
        require(occurrences <= 500, "article_occurrence_limit")
        for packet in packets:
            require(packet["role"] == "snippet_proposal" and packet["kind"] == "decisions"
                and packet["request_sha256"] == digest(packet["request"])
                and packet["reservation_nanousd"] == contract.reservation(packet), "proposal_binding")
            require(packet["article_occurrences"] <= 100 and packet["input_tokens_proxy"] <= 32_000, "packet_capacity")
        require(fits(0, sum(p["reservation_nanousd"] for p in packets)), "proposal_reservation_limit")

    def load_plan(self):
        plan, intent = self.one(PLAN), self.one(INTENT)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY and plan["approval"] == APPROVAL, "plan_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k,v in intent.items() if k != "id"), "intent_binding")
        require(self.ledger.artifacts.read_bytes(plan["method_artifact"]) == SPEC.read_bytes(), "method_changed")
        imported = self.ledger.artifacts.read(plan["import_artifact"])
        selection = self.ledger.artifacts.read(plan["selection_artifact"])
        require(imported["prior_commitment_nanousd"] == PRIOR_COMMITMENT, "prior_cost_binding")
        self.verify_selection(selection)
        self.completed_prepare(plan)
        return plan, imported, selection

    def completed_prepare(self, plan):
        row = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (plan["id"],)).fetchone()
        require(row is not None, "plan_record")
        created = row[0]
        session = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (created,)).fetchone()[0]
        events = [dict(e) for e in self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (session,))]
        selected = {kind: [e for e in events if e["kind"] == kind] for kind in
            ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
        require(not selected["operation.failed"] and all(len(selected[k]) == 1 for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended")), "prepare_not_completed")
        start, incoming, done, ended = (selected[k][0] for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended"))
        require(start["seq"] < incoming["seq"] < created < done["seq"] < ended["seq"]
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
        expected_versions = versions({k:v for k,v in self.one(INTENT).items() if k != "id"})
        require(set(plan["versions"]) == set(expected_versions), "version_scope")
        for kind, reference in plan["versions"].items():
            version = self.ledger.get(reference, kind)
            require(version["content"] == expected_versions[kind], "version_content")
            sequence = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (reference,)).fetchone()[0]
            require(incoming["seq"] < sequence < created, "version_chronology")

    def census(self, plan):
        state = {"intents": {}, "responses": {}, "packets": {}, "queues": {}, "logical_attempted": set(),
            "settled_nanousd": 0, "held_nanousd": 0, "unknown_holds": 0, "returned_requests": 0,
            "completed": set(), "health": {"stop_reason": None}}
        for q in self.rows(QUEUE):
            require(q["plan"] == plan["id"] and q["implementation"] == plan["implementation"], "queue_binding")
            for p in self.ledger.artifacts.read(q["packets_artifact"]):
                key = p["task_key"]
                require(key not in state["packets"] and p["reservation_nanousd"] == contract.reservation(p)
                    and p["request_sha256"] == digest(p["request"]), "packet_binding")
                state["packets"][key], state["queues"][key] = p, q
        attempts = {}
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            i = json.loads(e[0])
            key = i["task_key"]
            require(key in state["packets"] and key not in state["intents"] and i["attempt"] not in attempts, "no_retry")
            p, q = state["packets"][key], state["queues"][key]
            require(i["method"] == METHOD and i["batch"] == plan["id"] and i["queue"] == q["id"] and i["number"] == 1
                and i["packet"] == digest(p) and i["request"] == p["request_sha256"] and i["reserved_nanousd"] == p["reservation_nanousd"], "intent_binding")
            require(not state["logical_attempted"].intersection(p["logical_ids"]), "logical_retry")
            require(self.ledger.artifacts.read(i["dispatch"]) == wire.Invocation(p["request"], i["attempt"], kind=p["kind"]).manifest(), "dispatch_binding")
            state["intents"][key], attempts[i["attempt"]] = i, key
            state["logical_attempted"].update(p["logical_ids"])
        receipts = {}
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='luna_snippet.response.received' ORDER BY seq"):
            r = json.loads(e[0])
            attempt = r["attempt"]
            require(attempt in attempts and attempt not in receipts, "receipt_binding")
            derived, parsed = outcome(state["packets"][attempts[attempt]], ProviderResponse(**self.ledger.artifacts.read(r["response"])))
            receipts[attempt] = {"response": r["response"], "derived": derived, "parsed": parsed}
        for r in self.rows(RESPONSE):
            key = r["task_key"]
            require(key in state["intents"] and key not in state["responses"] and r["plan"] == plan["id"]
                and r["attempt"] == state["intents"][key]["attempt"] and r["attempt"] in receipts, "assessment_binding")
            raw = receipts[r["attempt"]]
            require(r["response"] == raw["response"] and r["parsed"] == (digest(raw["parsed"]) if raw["parsed"] is not None else None)
                and all(digest(r.get(k)) == digest(v) for k,v in raw["derived"].items()), "assessment_replay")
            state["responses"][key] = r
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.completed' ORDER BY seq"):
            r = json.loads(e[0])
            attempt = r["attempt"]
            require(attempt in attempts and attempt not in state["completed"], "completion_scope")
            a = state["responses"].get(attempts[attempt])
            require(a and not a["hold"] and a["id"] == r["assessment"] and a["response"] == r["response"], "completion_binding")
            state["completed"].add(attempt)
        health_rows = dict(state["responses"])
        for key, i in state["intents"].items():
            raw = receipts.get(i["attempt"])
            cost = raw["derived"]["cost_nanousd"] if raw else None
            if i["attempt"] in state["completed"]:
                require(type(cost) is int and cost >= 0, "settled_cost")
                state["settled_nanousd"] += cost
            else:
                state["held_nanousd"] += max(i["reserved_nanousd"], cost or 0)
                state["unknown_holds"] += 1
            if raw and key not in health_rows:
                health_rows[key] = {**raw["derived"], "usable": False}
        require(set(self.ledger.unresolved) == set(attempts)-state["completed"], "orphan_inventory")
        state["returned_requests"] = len(receipts)
        state["health"] = prior.health_state(state["intents"], health_rows)
        return state

    def queue(self, session, plan, name, packets, unavailable=None):
        require(not any(r["name"] == name for r in self.rows(QUEUE)), "duplicate_queue")
        value = {"name": name, "plan": plan["id"], "implementation": plan["implementation"],
            "packets_artifact": self.ledger.artifacts.put(packets), "unavailable": unavailable or {}}
        q = {"id": self.retain(session, QUEUE, name, value), **value}
        for p in packets:
            require(p["task_key"] not in self._state["packets"], "duplicate_packet")
            self._state["packets"][p["task_key"]], self._state["queues"][p["task_key"]] = p, q
        return q

    def provider(self, session, plan, packets):
        known = {p["request_sha256"]: p for p in packets}
        def before(invocation):
            try:
                require_active(self, session)
                self.guard(plan["implementation"])
                require(not self._dispatch_stop.is_set(), "dispatch_stopped")
                p = known.get(digest(invocation.request))
                require(p is not None and invocation.kind == p["kind"], "wire_binding")
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

    def dispatch(self, session, plan, queue, packets):
        s = self._state
        ready = [p for p in packets if not set(p["logical_ids"]) & s["logical_attempted"]]
        provider = self.provider(session, plan, packets)
        position = 0
        while position < len(ready):
            if s["health"]["stop_reason"]:
                return s["health"]["stop_reason"]
            self.guard(plan["implementation"])
            wave, intended = [], []
            for p in ready[position:position+(MAX_WORKERS if s["intents"] else 1)]:
                if not fits(s["settled_nanousd"]+s["held_nanousd"], p["reservation_nanousd"]):
                    break
                attempt = str(uuid.uuid4())
                call = wire.Invocation(p["request"], attempt, kind=p["kind"])
                i = {"method": METHOD, "attempt": attempt, "task_key": p["task_key"], "number": 1,
                    "batch": plan["id"], "queue": queue["id"], "category": "pilot", "started_at": utc(),
                    "packet": self.ledger.artifacts.put(p), "request": self.ledger.artifacts.put(p["request"]),
                    "dispatch": self.ledger.artifacts.put(call.manifest()), "reserved_nanousd": p["reservation_nanousd"]}
                self.ledger.append(session, "model.attempt.intended", i)
                self.ledger.unresolved[attempt] = i
                s["intents"][p["task_key"]] = i
                s["logical_attempted"].update(p["logical_ids"])
                s["held_nanousd"] += p["reservation_nanousd"]
                s["unknown_holds"] += 1
                wave.append((call, attempt))
                intended.append(i)
            if not wave:
                return "pilot_budget_bound"
            for n, response in self.gateway.codex_dispatch(session, provider, wave, workers=MAX_WORKERS):
                i = intended[n]
                p = s["packets"][i["task_key"]]
                raw = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "luna_snippet.response.received", {"attempt": i["attempt"], "response": raw})
                derived, parsed = outcome(p, response)
                value = {"plan": plan["id"], "attempt": i["attempt"], "task_key": i["task_key"],
                    "response": raw, "parsed": self.ledger.artifacts.put(parsed) if parsed is not None else None, **derived}
                identity = self.ledger.record(session, RESPONSE, i["attempt"], value)
                s["responses"][i["task_key"]] = {"id": identity, **value}
                s["returned_requests"] += 1
                if not derived["hold"]:
                    self.complete(session, i, raw, identity, "valid" if derived["usable"] else "invalid")
                    s["completed"].add(i["attempt"])
                    s["held_nanousd"] -= i["reserved_nanousd"]
                    s["settled_nanousd"] += derived["cost_nanousd"]
                    s["unknown_holds"] -= 1
                else:
                    s["held_nanousd"] += max(0, (derived["cost_nanousd"] or 0)-i["reserved_nanousd"])
                if derived["fatal"]:
                    self._dispatch_stop.set()
            s["health"] = prior.health_state(s["intents"], s["responses"])
            position += len(wave)
            self.progress(stage=queue["name"], queued=len(packets), attempted=len(s["intents"]), returned=s["returned_requests"],
                settled_nanousd=s["settled_nanousd"], held_nanousd=s["held_nanousd"],
                pilot_remaining_nanousd=max(0, PILOT_CAP-s["settled_nanousd"]-s["held_nanousd"]), unknown_holds=s["unknown_holds"])
        return "queue_complete"

    def qa(self, session, plan, imported, name, proposals, supported, attempted_stages):
        source = imported["source"]
        history = imported["history"]["membership_attempts"]
        encoder = offline_tokenizer()
        def count(t):
            return len(encoder.encode(t, disallowed_special=()))
        negatives = {tuple(sorted(r["pair"])) for r in imported["history"].get("pair_observations", [])
            if r.get("label") == "negative" and r.get("compatible_focal_rubric")}
        member_pass, unavailable, packets, rejected = set(), {}, [], set()
        for p in proposals:
            revision = p["membership_revision"]
            if revision in supported:
                continue
            h = history.get(revision, {})
            if h.get("blocked") or any(tuple(sorted(pair)) in negatives for pair in combinations(p["members"], 2)):
                unavailable[revision] = "historical_attempt_or_negative_block"
                continue
            if h.get("member_supported"):
                member_pass.add(revision)
                if h.get("card_supported"):
                    supported[revision] = h["card"]
                continue
            if (revision, "members") in attempted_stages or h.get("member_attempted"):
                unavailable[revision] = "exact_member_task_already_attempted"
                continue
            try:
                packet = contract.member_packet(source, p["members"], count)
            except ResearchError as error:
                if str(error) not in {"dossier_packet_capacity", "dossier_card_quality_token_limit"}:
                    raise
                unavailable[revision] = "full_source_capacity"
                continue
            packets.append(packet)
            attempted_stages.add((revision, "members"))
        q = self.queue(session, plan, name+"/members", packets, unavailable)
        self.dispatch(session, plan, q, packets)
        for key, row in self._state["responses"].items():
            if row["members_supported"] and row["attempt"] in self._state["completed"]:
                member_pass.add(self._state["packets"][key]["membership_revision"])
            if row["usable"] and row["attempt"] in self._state["completed"] and self._state["packets"][key]["role"] == "group_membership" and not row["members_supported"]:
                rejected.add(self._state["packets"][key]["membership_revision"])
        cards, card_unavailable = [], {}
        for p in proposals:
            revision = p["membership_revision"]
            if revision not in member_pass or revision in supported:
                continue
            h = history.get(revision, {})
            if h.get("card_attempted") or (revision, "card") in attempted_stages:
                card_unavailable[revision] = "exact_card_task_already_attempted"
                continue
            try:
                packet = contract.group_packet(source, p["members"], count)
            except ResearchError as error:
                if str(error) not in {"dossier_packet_capacity", "dossier_card_quality_token_limit"}:
                    raise
                card_unavailable[revision] = "full_source_capacity"
                continue
            cards.append(packet)
            attempted_stages.add((revision, "card"))
        q = self.queue(session, plan, name+"/cards", cards, card_unavailable)
        self.dispatch(session, plan, q, cards)
        for packet in cards:
            row = self._state["responses"].get(packet["task_key"])
            if row and row["attempt"] in self._state["completed"] and row["group_supported"]:
                supported[packet["membership_revision"]] = packet["card"]
            elif row and row["attempt"] in self._state["completed"] and row["usable"]:
                rejected.add(packet["membership_revision"])
        return rejected

    def run(self, session, plan, imported, selection):
        self.guard(plan["implementation"])
        q = self.queue(session, plan, "proposals", selection["packets"])
        self.dispatch(session, plan, q, selection["packets"])
        links, answer_counts = [], Counter()
        for packet in selection["packets"]:
            row = self._state["responses"].get(packet["task_key"])
            if row and row["usable"] and row["attempt"] in self._state["completed"]:
                parsed = self.ledger.artifacts.read(row["parsed"])
                links.extend(parsed["links"])
                answer_counts.update({"usable_packets": 1, "direct_links": len(parsed["links"]),
                    "keep_answers": len(parsed["keep"]), "unknown_answers": len(parsed["unknown"])})
        proposals = grouping.proposals(links, selection["units"])
        self.retain(session, CHECKPOINT, "proposals", {"plan": plan["id"], "artifact": self.ledger.artifacts.put(proposals),
            "links_artifact": self.ledger.artifacts.put(links)})
        supported, attempted_stages = {}, set()
        rejected = self.qa(session, plan, imported, "primary", proposals["primary"], supported, attempted_stages)
        fallbacks = [p for p in proposals["fallbacks"] if set(p["parent_revisions"]) & rejected]
        self.qa(session, plan, imported, "fallback", fallbacks, supported, attempted_stages)
        all_proposals = {p["membership_revision"]: p for p in [*proposals["primary"], *fallbacks]}
        changes = grouping.select_supported(list(all_proposals.values()), supported, imported["state"])
        successor = repair.commit(imported["state"], changes, reason=METHOD)
        change_types = Counter()
        for change in changes:
            original_units = all_proposals[change["proposal_revision"]]["unit_bindings"].values()
            existing = sum(u["source_group_id"] is not None for u in original_units)
            change_types["new_all_loose_dossiers" if existing == 0 else "extended_existing_dossiers" if existing == 1 else "combined_existing_dossiers"] += 1
        self._state = self.census(plan)
        result = {**self.summary(plan), "pilot_finished": True, "full_rollout_authorized": False,
            "before": statistics(imported["state"]), "after": statistics(successor), "changes": len(changes),
            "new_dossiers_from_unassigned": sum(all(i in set(imported["state"]["unresolved_ids"]) for i in c["original_members"]) for c in changes),
            "successor_artifact": self.ledger.artifacts.put(successor), "change_manifest_artifact": self.ledger.artifacts.put(changes),
            "change_types": dict(change_types),
            "development_comparison": development_comparison(imported, selection, links, successor),
            "proposal_counts": {"primary": len(proposals["primary"]), "fallback": len(fallbacks), "supported_memberships": len(supported)},
            "proposal_answers": dict(answer_counts), "coverage": selection.get("coverage", {}),
            "queues": [{"name": row["name"], "queued": len(self.ledger.artifacts.read(row["packets_artifact"])),
                "unavailable_reasons": dict(Counter(row["unavailable"].values()))} for row in self.rows(QUEUE)],
            "precision_recall_certified": False, "interpretation": "Selected development pilot; no independent population validation"}
        self.guard(plan["implementation"])
        identity = self.retain(session, RESULT, plan["id"], result)
        self.progress(stage="pilot_report", changes=len(changes), pilot_finished=True)
        return {"id": identity, **result}

    def summary(self, plan):
        s = self._state
        committed = s["settled_nanousd"]+s["held_nanousd"]
        return {"method": METHOD, "plan": plan["id"], "observed_at": utc(), "policy": POLICY,
            "prepared": True, "queued_requests": len(s["packets"]), "attempted_requests": len(s["intents"]),
            "returned_requests": s["returned_requests"], "usable_requests": sum(r["usable"] for r in s["responses"].values()),
            "unattempted_requests": len(s["packets"])-len(s["intents"]), "unknown_holds": s["unknown_holds"],
            "new_settled_nanousd": s["settled_nanousd"], "new_held_nanousd": s["held_nanousd"],
            "new_committed_nanousd": committed, "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "combined_commitment_nanousd": PRIOR_COMMITMENT+committed,
            "pilot_remaining_nanousd": max(0, PILOT_CAP-committed),
            "repair_remaining_nanousd": max(0, REPAIR_CAP-PRIOR_COMMITMENT-committed), "health": s["health"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "status"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require(args.action == "run" or not args.allow_paid_execution, "paid_flag_scope")
    engine = Pilot(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {"action": args.action}
        if args.action == "run":
            data["allow_paid_execution"] = args.allow_paid_execution
        print(json.dumps(engine.execute("status", data, objective="Five-packet snippet grouping pilot with full-source confirmation", actor="codex:luna-snippet-pilot")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
