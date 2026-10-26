"""Audited finite resolution of loose articles; singleton status is not uniqueness.

The census/admission/QA core is prospectively bound from the reviewed rollout V2.
No old controller is inherited or invoked; all globals belong to this new owner.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import threading
import time
import uuid

import dossier_transport as wire
import dossier_transport_v9 as transport
import luna_quality_audit as prior
import luna_recall_contract as contract
import luna_recall_repair as repair
import luna_recall_run_v2 as old
import luna_snippet_rollout_v2 as predecessor
import luna_unresolved_source as source_module
import luna_unresolved_resolution as resolution
from newsresearch.common import AuditError, Config, digest, require_active, utc, ResearchError
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_UNRESOLVED_RESOLUTION.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-unresolved-20261025-v1"
INTENT, PLAN, QUEUE, RESPONSE, CHECKPOINT, RESULT = ("luna_unresolved_"+s for s in
    ("intent", "plan", "queue", "response", "checkpoint", "result"))
FX, PRIOR_COMMITMENT = 1_119_300_000, 9_710_343_318
PRIOR_SETTLED, PRIOR_HELD = 9_692_612_660, 17_730_658
JOIN_CAP, REPAIR_CAP, VALIDATION_CAP = 4*FX, 25*FX, 25*FX//2
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
POLICY = {"method": METHOD, "repair_cap_nanousd": REPAIR_CAP, "join_cap_nanousd": JOIN_CAP,
    "prior_commitment_nanousd": PRIOR_COMMITMENT, "prior_settled_nanousd": PRIOR_SETTLED,
    "prior_held_nanousd": PRIOR_HELD, "usd_per_eur_nano": FX, "max_workers": MAX_WORKERS,
    "technical_retries": 0, "threshold": .85, "threshold_validated": False,
    "validation_admission": False, "validation_remaining_nanousd": VALIDATION_CAP,
    "reserve_eur": 12.5, "max_targets_per_anchor": 3, "effective_deadline": None,
    "singleton_dossier_does_not_prove_unique_event": True, "old_fatal_preserved": True,
    "quarantine_every_fatal_packet_article": True, "membership_and_card_reserved_together": True}
APPROVAL = {"instruction": "Los het voor me op", "approval_event": "e50d00c69ed55286ace5727d",
    "existing_budget_authority": "7d40a2fb94ff60df464f36ac", "additional_budget": False}


def require(value, reason):
    if not value:
        raise AuditError("luna_unresolved_"+reason)


def implementation():
    files = [Path(__file__), Path(resolution.__file__), Path(source_module.__file__), SPEC,
        Path(__file__).with_name("run_luna_unresolved_with_key.ps1")]
    return {**predecessor.implementation(), **source_module.implementation(),
        **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def outcome(packet, response):
    require(packet["role"] in {"group_membership", "group_quality"}, "qa_roles_only")
    return predecessor.outcome(packet, response)


def fits(by_category, category, reservation, earmarked=0):
    require(set(by_category) == {"join", "singleton"} and category in by_category
        and type(reservation) is int and reservation >= 0 and earmarked >= 0, "admission_category")
    return (PRIOR_COMMITMENT+sum(by_category.values())+reservation+earmarked <= REPAIR_CAP
        and (category != "join" or by_category["join"]+reservation+earmarked <= JOIN_CAP))


def versions(desired):
    return {"protocol": desired, "question": {"text": "Separate valid standalone dossiers from unresolved event identity"},
        "selection": {"rules": "All current loose inputs; fixed top-three current targets then singleton QA; preserved quarantine"},
        "dossier_definition": {"unit": "One bounded focal occurrence; singleton does not imply global uniqueness"},
        "prompt": {"instructions": contract.focal.FOCUS_RULES},
        "codebook": {"labels": ["joined", "singleton", "uncertain", "quarantined", "unattempted"]},
        "profile": {"mode": "exploratory", "population_estimate": False}, "policy": POLICY}


class Resolution(Research):
    rows, one, complete, retain = prior.Audit.rows, prior.Audit.one, prior.Audit.complete, old.Recall.retain

    def set_scope(self, imported):
        require(imported["prior_commitment_nanousd"] == PRIOR_COMMITMENT, "prior_cost_binding")
        require(imported["diagnostic"]["scope_admission_allowed"] is True, "historical_failure_scope_not_proved")
        self._prior_logical_ids = set(imported["history"].get("logical_ids", []))
        self._prior_task_keys = set(imported["history"].get("task_keys", []))
        self._quarantine = set(imported["history"]["quarantine_document_ids"])

    def admission_scope(self, packet):
        require(packet["role"] in {"group_membership", "group_quality"}
            and not set(packet["members"]) & self._quarantine, "quarantined_or_out_of_scope_packet")
        require(not set(packet["logical_ids"]) & self._prior_logical_ids
            and packet["task_key"] not in self._prior_task_keys, "historical_task_retry")
        require(packet["request_sha256"] == digest(packet["request"])
            and packet["reservation_nanousd"] == contract.reservation(packet), "admission_packet_binding")

    def quote(self, imported, selection):
        encoder = offline_tokenizer()
        def count(text):
            return len(encoder.encode(text, disallowed_special=()))
        result = {"prior_commitment_nanousd": PRIOR_COMMITMENT,
            "remaining_repair_nanousd": REPAIR_CAP-PRIOR_COMMITMENT,
            "join_cap_nanousd": JOIN_CAP, "validation_funds_available": False,
            "cache_savings_assumed": False, "not_a_guarantee_all_cases_fit": True}
        for stage, name in (("join", "union_proposals"), ("singleton", "singleton_proposals")):
            amounts, unavailable, reuse = [], Counter(), 0
            for proposal in selection[name]:
                bundle = resolution.packet_bundle(imported, proposal, count)
                if bundle["unavailable"]:
                    unavailable[bundle["unavailable"]] += 1
                elif bundle["reused_card"] is not None:
                    reuse += 1
                else:
                    amounts.append(bundle["reservation_nanousd"])
            result[stage] = {"selected_memberships": len(selection[name]), "ready_memberships": len(amounts),
                "reusable_supported_memberships": reuse, "unavailable": dict(unavailable),
                "full_reservation_sum_nanousd": sum(amounts)}
        return result

    def prepare(self, session, context):
        require(self.config.offline, "offline_prepare")
        if self.one(PLAN, optional=True):
            plan, _, _ = self.load_plan()
            self._state = self.census(plan)
            return self.summary(plan)
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY, "approval": APPROVAL,
            "method_artifact": self.ledger.artifacts.put_bytes(SPEC.read_bytes()), "source_report": source_module.REPORT}
        intent = self.retain(session, INTENT, METHOD, desired)
        registered = {kind: self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"]
            for kind, value in versions(desired).items()}
        imported = source_module.collect(self, session)
        self.set_scope(imported)
        selection = resolution.build_plan(imported)
        quote = self.quote(imported, selection)
        self.guard(desired["implementation"])
        value = {**desired, "intent": intent, "versions": registered,
            "import_artifact": self.ledger.artifacts.put(imported), "selection_artifact": self.ledger.artifacts.put(selection),
            "quote_artifact": self.ledger.artifacts.put(quote), "diagnostic_artifact": self.ledger.artifacts.put(imported["diagnostic"])}
        plan = {"id": self.retain(session, PLAN, METHOD, value), **value}
        self._state = self.census(plan)
        return self.summary(plan)

    def load_plan(self):
        plan, intent = self.one(PLAN), self.one(INTENT)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY and plan["approval"] == APPROVAL,
            "plan_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k,v in intent.items() if k != "id"),
            "intent_binding")
        require(self.ledger.artifacts.read_bytes(plan["method_artifact"]) == SPEC.read_bytes(), "method_changed")
        imported = self.ledger.artifacts.read(plan["import_artifact"])
        selection = self.ledger.artifacts.read(plan["selection_artifact"])
        self.set_scope(imported)
        require(selection == resolution.build_plan(imported), "frozen_resolution_plan_changed")
        require(self.ledger.artifacts.read(plan["diagnostic_artifact"]) == imported["diagnostic"], "diagnostic_changed")
        self.completed_prepare(plan)
        return plan, imported, selection

    def run(self, session, plan, imported, selection):
        self.guard(plan["implementation"])
        supported, attempted_stages = {}, set()
        self.progress(stage="join_qa", selected_anchors=len(selection["anchors"]))
        self.qa(session, plan, imported, "join", selection["union_proposals"], supported, attempted_stages, category="join")
        joined = resolution.select_changes(selection, imported["state"], supported)
        occupied = set(joined["occupied"])
        remaining = [p for p in selection["singleton_proposals"] if not set(p["members"]) & occupied]
        self.progress(stage="singleton_qa", joined_articles=len(set(selection["anchors"]) & occupied),
            remaining_singleton_memberships=len(remaining))
        self.qa(session, plan, imported, "singleton", remaining, supported, attempted_stages, category="singleton")
        singletons = resolution.select_changes(selection, imported["state"], supported, singletons=True, occupied=occupied)
        changes = joined["changes"]+singletons["changes"]
        successor = repair.commit(imported["state"], changes, reason=METHOD)
        outcomes = {}
        for row in self.rows(CHECKPOINT):
            for rev, reason in row.get("unavailable", {}).items():
                outcomes[rev] = {"status": reason}
            for rev in row.get("rejected", []):
                outcomes[rev] = {"status": "semantic_rejection"}
        for key, intent in self._state["intents"].items():
            packet, response = self._state["packets"][key], self._state["responses"].get(key)
            rev = packet["membership_revision"]
            if not response or intent["attempt"] not in self._state["completed"]:
                outcomes.setdefault(rev, {}).update(status="physical_outcome_unknown")
            elif not response["usable"]:
                outcomes.setdefault(rev, {}).update(status="mechanically_unusable")
            elif packet["role"] == "group_membership":
                item = outcomes.setdefault(rev, {"status": "member_supported_card_pending"})
                item["member_supported"] = response["members_supported"]
                if len(packet["members"]) == 1:
                    parsed = self.ledger.artifacts.read(response["parsed"])
                    clarity = [a for a in parsed["answers"].values() if a["kind"] == "clarity" and a["status"] == "valid"]
                    require(len(clarity) <= 1, "singleton_clarity_bijection")
                    if clarity:
                        item.update(clarity_label=clarity[0]["label"], clarity_probability=clarity[0]["probability"])
        for rev in supported:
            outcomes.setdefault(rev, {}).update(status="supported", member_supported=True)
        dispositions = resolution.dispositions(selection, successor, membership_outcomes=outcomes)
        self._state = self.census(plan)
        result = {**self.summary(plan), "resolution_finished": True,
            "before": predecessor.statistics(imported["state"]), "after": predecessor.statistics(successor),
            "changes": len(changes), "join_changes": len(joined["changes"]), "singleton_changes": len(singletons["changes"]),
            "successor_artifact": self.ledger.artifacts.put(successor),
            "change_manifest_artifact": self.ledger.artifacts.put(changes),
            "dispositions_artifact": self.ledger.artifacts.put(dispositions),
            "disposition_summary": dispositions["summary"], "new_reference_judgments": 0,
            "singleton_uniqueness_established": False, "population_precision_recall_measured": False,
            "historical_failure_preserved": imported["diagnostic"]["fatal_cases"],
            "quarantined_inputs": len(self._quarantine),
            "interpretation": "Exploratory Luna-reference source/card support with separate identity uncertainty"}
        self.guard(plan["implementation"])
        identity = self.retain(session, RESULT, plan["id"], result)
        self.progress(stage="report", resolution_finished=True, after=result["after"], changes=len(changes),
            disposition_summary=result["disposition_summary"], new_committed_nanousd=result["new_committed_nanousd"])
        return {"id": identity, **result}

    def summary(self, plan):
        s = self._state
        committed = s["settled_nanousd"]+s["held_nanousd"]
        return {"method": METHOD, "plan": plan["id"], "observed_at": utc(), "policy": POLICY, "prepared": True,
            "queued_requests": len(s["packets"]), "attempted_requests": len(s["intents"]),
            "returned_requests": s["returned_requests"], "usable_requests": sum(r["usable"] for r in s["responses"].values()),
            "unattempted_requests": len(s["packets"])-len(s["intents"]), "unknown_holds": s["unknown_holds"],
            "new_settled_nanousd": s["settled_nanousd"], "new_held_nanousd": s["held_nanousd"],
            "new_committed_nanousd": committed, "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "combined_commitment_nanousd": PRIOR_COMMITMENT+committed,
            "category_commitments_nanousd": dict(s["by_category"]), "planning_earmark_nanousd": s["earmarked"],
            "repair_remaining_nanousd": REPAIR_CAP-PRIOR_COMMITMENT-committed,
            "validation_remaining_nanousd": VALIDATION_CAP, "health": s["health"],
            "offline_quote": self.ledger.artifacts.read(plan["quote_artifact"]),
            "diagnostic_artifact": plan["diagnostic_artifact"]}

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
            self.set_scope(imported)
            result = self.one(RESULT, optional=True)
            if result:
                return result
            if data["action"] == "status":
                return self.summary(plan)
            require(not self.config.offline and data["allow_paid_execution"] is True and bool(os.environ.get("OPENAI_API_KEY")), "paid_authority_and_key")
            require(not self._state["intents"], "interrupted_rollout_requires_review")
            return self.run(session, plan, imported, selection)
        finally:
            finished.set()
            thread.join(timeout=2)
            self._state = None


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
            "by_category": {"join": 0, "singleton": 0}, "earmarked": 0,
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
                and i["category"] == q["category"] and i["category"] in {"join", "singleton"}
                and i["packet"] == digest(p) and i["request"] == p["request_sha256"] and i["reserved_nanousd"] == p["reservation_nanousd"], "intent_binding")
            require(not state["logical_attempted"].intersection(p["logical_ids"]), "logical_retry")
            require(self.ledger.artifacts.read(i["dispatch"]) == wire.Invocation(p["request"], i["attempt"], kind=p["kind"]).manifest(), "dispatch_binding")
            state["intents"][key], attempts[i["attempt"]] = i, key
            state["logical_attempted"].update(p["logical_ids"])
        receipts = {}
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='luna_unresolved.response.received' ORDER BY seq"):
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
                state["by_category"][i["category"]] += cost
            else:
                state["held_nanousd"] += max(i["reserved_nanousd"], cost or 0)
                state["by_category"][i["category"]] += max(i["reserved_nanousd"], cost or 0)
                state["unknown_holds"] += 1
            if raw and key not in health_rows:
                health_rows[key] = {**raw["derived"], "usable": False}
        require(set(self.ledger.unresolved) == set(attempts)-state["completed"], "orphan_inventory")
        state["returned_requests"] = len(receipts)
        state["health"] = prior.health_state(state["intents"], health_rows)
        return state


    def queue(self, session, plan, name, packets, unavailable=None, *, category):
        require(not any(r["name"] == name for r in self.rows(QUEUE)), "duplicate_queue")
        require(category in {"join", "singleton"}, "queue_category")
        value = {"name": name, "category": category, "plan": plan["id"], "implementation": plan["implementation"],
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
        blocked = s["logical_attempted"] | getattr(self, "_prior_logical_ids", set())
        ready = [p for p in packets if not set(p["logical_ids"]) & blocked]
        for packet in ready:
            self.admission_scope(packet)
        provider = self.provider(session, plan, packets)
        position = 0
        while position < len(ready):
            if s["health"]["stop_reason"]:
                return s["health"]["stop_reason"]
            self.guard(plan["implementation"])
            wave, intended = [], []
            for p in ready[position:position+(MAX_WORKERS if s["intents"] else 1)]:
                if not fits(s["by_category"], queue["category"], p["reservation_nanousd"], s["earmarked"]):
                    break
                self.admission_scope(p)
                attempt = str(uuid.uuid4())
                call = wire.Invocation(p["request"], attempt, kind=p["kind"])
                i = {"method": METHOD, "attempt": attempt, "task_key": p["task_key"], "number": 1,
                    "batch": plan["id"], "queue": queue["id"], "category": queue["category"], "started_at": utc(),
                    "packet": self.ledger.artifacts.put(p), "request": self.ledger.artifacts.put(p["request"]),
                    "dispatch": self.ledger.artifacts.put(call.manifest()), "reserved_nanousd": p["reservation_nanousd"]}
                self.ledger.append(session, "model.attempt.intended", i)
                self.ledger.unresolved[attempt] = i
                s["intents"][p["task_key"]] = i
                s["logical_attempted"].update(p["logical_ids"])
                s["held_nanousd"] += p["reservation_nanousd"]
                s["by_category"][queue["category"]] += p["reservation_nanousd"]
                s["unknown_holds"] += 1
                wave.append((call, attempt))
                intended.append(i)
            if not wave:
                return queue["category"]+"_budget_bound"
            for n, response in self.gateway.codex_dispatch(session, provider, wave, workers=MAX_WORKERS):
                i = intended[n]
                p = s["packets"][i["task_key"]]
                raw = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "luna_unresolved.response.received", {"attempt": i["attempt"], "response": raw})
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
                    s["by_category"][queue["category"]] += derived["cost_nanousd"]-i["reserved_nanousd"]
                    s["unknown_holds"] -= 1
                else:
                    s["held_nanousd"] += max(0, (derived["cost_nanousd"] or 0)-i["reserved_nanousd"])
                    s["by_category"][queue["category"]] += max(0, (derived["cost_nanousd"] or 0)-i["reserved_nanousd"])
                if derived["fatal"]:
                    self._dispatch_stop.set()
            s["health"] = prior.health_state(s["intents"], s["responses"])
            position += len(wave)
            self.progress(stage=queue["name"], queued=len(packets), attempted=len(s["intents"]), returned=s["returned_requests"],
                settled_nanousd=s["settled_nanousd"], held_nanousd=s["held_nanousd"],
                category_commitments_nanousd=dict(s["by_category"]), unknown_holds=s["unknown_holds"])
        return "queue_complete"


    def qa(self, session, plan, imported, name, proposals, supported, attempted_stages, *, category):
        """Bounded waves protect every admitted membership's possible card cost."""
        source, history = imported["source"], imported["history"]["membership_attempts"]
        encoder = offline_tokenizer()
        def count(text):
            return len(encoder.encode(text, disallowed_special=()))
        negatives = {tuple(sorted(r["pair"])) for r in imported["history"].get("pair_observations", [])
            if r.get("label") == "negative" and r.get("compatible_focal_rubric")}
        unavailable, rejected, position, wave_number = {}, set(), 0, 0
        while position < len(proposals) and not self._state["health"]["stop_reason"]:
            selected, planned = [], 0
            while position < len(proposals) and len(selected) < MAX_WORKERS:
                p = proposals[position]
                position += 1
                rev = p["membership_revision"]
                require(not set(p["members"]) & self._quarantine, "quarantined_proposal")
                if rev in supported:
                    continue
                h = history.get(rev, {})
                if h.get("blocked") or any(tuple(sorted(pair)) in negatives for pair in combinations(p["members"], 2)):
                    unavailable[rev] = "historical_attempt_or_negative_block"
                    continue
                if h.get("member_supported") and h.get("card_supported"):
                    supported[rev] = h["card"]
                    continue
                if (not h.get("member_supported") and (h.get("member_attempted") or (rev, "members") in attempted_stages)) or h.get("card_attempted") or (rev, "card") in attempted_stages:
                    unavailable[rev] = "exact_membership_stage_already_attempted"
                    continue
                try:
                    member = None if h.get("member_supported") else contract.member_packet(source, p["members"], count)
                    card = contract.group_packet(source, p["members"], count)
                except ResearchError as error:
                    if str(error) not in {"dossier_packet_capacity", "dossier_card_quality_token_limit"}:
                        raise
                    unavailable[rev] = "full_source_capacity"
                    continue
                if any(set(x["logical_ids"]) & (self._prior_logical_ids | self._state["logical_attempted"]) or x["task_key"] in self._prior_task_keys for x in (member, card) if x):
                    unavailable[rev] = "historical_logical_identity"
                    continue
                amount = card["reservation_nanousd"]+(member["reservation_nanousd"] if member else 0)
                if not fits(self._state["by_category"], category, amount, planned):
                    if selected:
                        position -= 1
                        break
                    unavailable[rev] = "joint_member_card_budget_bound"
                    for remaining in proposals[position:]:
                        unavailable.setdefault(remaining["membership_revision"], "joint_member_card_budget_bound")
                    position = len(proposals)
                    break
                selected.append((p, member, card))
                planned += amount
            if not selected:
                continue
            # This durable planning record is deliberately not model.attempt.intended.
            self.retain(session, CHECKPOINT, f"{name}/earmark-{wave_number}", {"plan": plan["id"],
                "memberships": [p["membership_revision"] for p,_,_ in selected],
                "member_reservations": {p["membership_revision"]: m["reservation_nanousd"] if m else 0 for p,m,_ in selected},
                "card_reservations": {p["membership_revision"]: c["reservation_nanousd"] for p,_,c in selected},
                "planning_only": True})
            self._state["earmarked"] = sum(c["reservation_nanousd"] for _,_,c in selected)
            members = [m for _,m,_ in selected if m]
            q = self.queue(session, plan, f"{name}/{wave_number}/members", members, category=category)
            self.dispatch(session, plan, q, members)
            cards = []
            for p, member, card in selected:
                rev = p["membership_revision"]
                if member and member["task_key"] in self._state["intents"]:
                    attempted_stages.add((rev, "members"))
                row = self._state["responses"].get(member["task_key"]) if member else None
                complete = row and row["attempt"] in self._state["completed"] and row["usable"]
                if member is None or (complete and row["members_supported"]):
                    cards.append(card)
                elif complete:
                    rejected.add(rev)
            # Every card is admitted now, before any further membership wave.
            # All card upper bounds fitted together; unspent planning earmarks are freed.
            self._state["earmarked"] = 0
            q = self.queue(session, plan, f"{name}/{wave_number}/cards", cards, category=category)
            self.dispatch(session, plan, q, cards)
            for card in cards:
                rev = card["membership_revision"]
                if card["task_key"] in self._state["intents"]:
                    attempted_stages.add((rev, "card"))
                row = self._state["responses"].get(card["task_key"])
                if row and row["attempt"] in self._state["completed"] and row["usable"]:
                    if row["group_supported"]:
                        supported[rev] = card["card"]
                    else:
                        rejected.add(rev)
            wave_number += 1
        for p in proposals[position:]:
            unavailable.setdefault(p["membership_revision"], "health_stop_unattempted")
        self.retain(session, CHECKPOINT, name+"/completed", {"plan": plan["id"],
            "unavailable": unavailable, "rejected": sorted(rejected), "supported": sorted(supported)})
        return rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "status"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require(args.action == "run" or not args.allow_paid_execution, "paid_flag_scope")
    engine = Resolution(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {"action": args.action}
        if args.action == "run":
            data["allow_paid_execution"] = args.allow_paid_execution
        print(json.dumps(engine.execute("status", data,
            objective="Resolve loose articles with distinct dossier and identity-link status",
            actor="codex:luna-unresolved-resolution")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()


