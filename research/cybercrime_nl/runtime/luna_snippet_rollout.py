"""Audited one-pass snippet rollout with bounded QA and matched final validation."""
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
import luna_snippet_rollout_grouping as grouping
import luna_recall_design as design_module
import luna_snippet_rollout_source as source_module
from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_SNIPPET_ROLLOUT.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-snippet-rollout-20261025-v1"
INTENT, PLAN, QUEUE, RESPONSE, CHECKPOINT, RESULT = ("luna_snippet_rollout_"+s for s in
    ("intent", "plan", "queue", "response", "checkpoint", "result"))
FX, PRIOR_COMMITMENT = 1_119_300_000, 3_708_647_448
PROPOSAL_CAP, REPAIR_CAP, VALIDATION_CAP = 4*FX, 25*FX, 25*FX//2
MAX_WORKERS, RPM, TPM = 8, 500, 800_000
VALIDATION_SEED = "snippet-rollout-20261025-original-baseline-final-reference-v1"
POLICY = {"proposal_cap_nanousd": PROPOSAL_CAP, "repair_cap_nanousd": REPAIR_CAP,
    "validation_cap_nanousd": VALIDATION_CAP, "prior_commitment_nanousd": PRIOR_COMMITMENT,
    "usd_per_eur_nano": FX, "max_workers": MAX_WORKERS, "effective_deadline": None,
    "repair_rounds": 1, "technical_retries": 0, "threshold": .85, "threshold_validated": False,
    "input_max_nanousd_per_token": 138, "response_output_nanousd_per_token": 550,
    "reserve_eur": 12.5, "membership_and_card_reserved_together": True,
    "validation_limits": design_module.LIMITS, "validation_seed": VALIDATION_SEED,
    "baseline": "original_frozen_dossier_memberships", "prior_final_reference": "blocked_unknown"}
APPROVAL = {"instruction": "Implement the proposed plan.",
    "approval_event": "7d40a2fb94ff60df464f36ac",
    "approval_payload_sha256": "09059157ae3081e1e803b9d37524da41761b205d717b90057d6652f79ee63f9d",
    "approved_plan_event": "fb5eb93dfc6b34fc9513607d",
    "approved_plan_payload_sha256": "500ab95649da67543ff74b08ba82c26166ce2cdb85b38ee19be76957f715b550"}



def require(value, reason):
    if not value:
        raise AuditError("luna_snippet_"+reason)


def implementation():
    files = [Path(__file__), Path(grouping.__file__), Path(source_module.__file__), Path(transport.__file__),
        Path(design_module.__file__), SPEC, Path(__file__).with_name("run_luna_snippet_rollout_with_key.ps1"),
        ROOT / "scripts/windows_key_store.cs"]
    return {**old.implementation(), **source_module.implementation(), **grouping.implementation(),
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
            elif packet["role"] == "final_reference":
                raw_parsed, observations = contract.parse_pairs(packet, response.payload)
                parsed = {"parsed": raw_parsed, "observations": observations}
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


def fits(by_category, category, reservation, earmarked=0):
    require(category in {"proposal", "qa", "validation"} and reservation >= 0 and earmarked >= 0, "admission_category")
    if category == "validation":
        return by_category["validation"]+reservation <= VALIDATION_CAP
    repair_used = by_category["proposal"]+by_category["qa"]
    return (PRIOR_COMMITMENT+repair_used+reservation+earmarked <= REPAIR_CAP
        and (category != "proposal" or by_category["proposal"]+reservation <= PROPOSAL_CAP))


def versions(desired):
    return {"protocol": desired, "question": {"text": "One-pass snippet grouping and matched candidate-limited validation"},
        "selection": {"rules": "Frozen complete/sharded 10+10 menus; category-balanced multi-anchor packets; one repair pass"},
        "dossier_definition": {"unit": "One bounded focal occurrence under unchanged complete production rules"},
        "prompt": {"instructions": contract.focal.FOCUS_RULES},
        "codebook": {"labels": ["keep", "unknown", "visible_unit_id", "same_event", "negative"]},
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


def quote_selection(selection):
    reservations = [p["reservation_nanousd"] for p in selection["packets"]]
    total, guaranteed = 0, 0
    for value in reservations:
        if total+value > PROPOSAL_CAP:
            break
        total += value
        guaranteed += 1
    return {"packet_count": len(reservations), "proposal_reservation_sum_nanousd": sum(reservations),
        "proposal_cap_nanousd": PROPOSAL_CAP, "guaranteed_packet_prefix_at_full_reservations": guaranteed,
        "all_proposal_reservations_fit": sum(reservations) <= PROPOSAL_CAP,
        "article_appearances": sum(p["article_occurrences"] for p in selection["packets"]),
        "proxy_tokens": sum(p["input_tokens_proxy"] for p in selection["packets"]),
        "coverage_plan": selection["coverage_plan"], "qa_cost_outcome_dependent": True,
        "minimum_qa_allocation_nanousd": REPAIR_CAP-PRIOR_COMMITMENT-PROPOSAL_CAP,
        "validation_cap_nanousd": VALIDATION_CAP, "cache_savings_assumed": False}


def validation_source(source, selection):
    """Explicit common-frame derivation, with unchanged original baseline/ranks."""
    manifest = source["candidate_manifest"]
    pairs = {tuple(sorted((r["left"], r["right"]))) for r in manifest["pairs"]}
    pairs.update(tuple(sorted(row)) for row in selection["candidate_article_pairs"])
    require(all(a != b and a in source["documents"] and b in source["documents"] for a,b in pairs), "candidate_frame_endpoints")
    return {**source, "candidate_manifest": {**manifest,
        "pairs": [{"left": a, "right": b} for a,b in sorted(pairs)]}}


class Rollout(Research):
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
            self._prior_logical_ids = set(imported["history"].get("logical_ids", []))
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
        selection = grouping.prepare(imported["source"], imported["state"], lambda t: len(encoder.encode(t, disallowed_special=())),
            prior_questions=imported["history"].get("proposal_questions", {}))
        self.verify_selection(selection)
        quote = quote_selection(selection)
        self.guard(desired["implementation"])
        value = {**desired, "intent": intent, "versions": registered,
            "import_artifact": self.ledger.artifacts.put(imported), "selection_artifact": self.ledger.artifacts.put(selection),
            "quote_artifact": self.ledger.artifacts.put(quote)}
        plan = {"id": self.retain(session, PLAN, METHOD, value), **value}
        self._state = self.census(plan)
        return self.summary(plan)

    @staticmethod
    def verify_selection(selection):
        keys, logical = set(), set()
        for packet in selection["packets"]:
            displayed = json.loads(packet["request"]["input"])["units"]
            ids = [a["document_id"] for u in displayed for a in u["articles"]]
            require(len(ids) == len(set(ids)) and sorted(ids) == packet["article_ids"]
                and len(ids) == packet["article_occurrences"], "article_binding")
            require(packet["task_key"] not in keys and not logical.intersection(packet["logical_ids"]), "duplicate_packet_or_question")
            keys.add(packet["task_key"])
            logical.update(packet["logical_ids"])
            require(packet["role"] == "snippet_proposal" and packet["kind"] == "decisions"
                and packet["request_sha256"] == digest(packet["request"])
                and packet["reservation_nanousd"] == contract.reservation(packet), "proposal_binding")
            require(packet["article_occurrences"] <= 100 and packet["input_tokens_proxy"] <= 32_000, "packet_capacity")


    def load_plan(self):
        plan, intent = self.one(PLAN), self.one(INTENT)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY and plan["approval"] == APPROVAL, "plan_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k,v in intent.items() if k != "id"), "intent_binding")
        require(self.ledger.artifacts.read_bytes(plan["method_artifact"]) == SPEC.read_bytes(), "method_changed")
        imported = self.ledger.artifacts.read(plan["import_artifact"])
        selection = self.ledger.artifacts.read(plan["selection_artifact"])
        require(imported["prior_commitment_nanousd"] == PRIOR_COMMITMENT, "prior_cost_binding")
        self.verify_selection(selection)
        require(self.ledger.artifacts.read(plan["quote_artifact"]) == quote_selection(selection), "quote_changed")
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
            "by_category": {"proposal": 0, "qa": 0, "validation": 0}, "earmarked": 0,
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
                and i["category"] == q["category"] and i["category"] in {"proposal", "qa", "validation"}
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
        require(category in {"proposal", "qa", "validation"}, "queue_category")
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
        provider = self.provider(session, plan, packets)
        position = 0
        while position < len(ready):
            if s["health"]["stop_reason"]:
                return s["health"]["stop_reason"]
            self.guard(plan["implementation"])
            wave, intended = [], []
            for p in ready[position:position+(MAX_WORKERS if s["intents"] else 1)]:
                if not fits(s["by_category"], queue["category"], p["reservation_nanousd"], s["earmarked"] if queue["category"] == "qa" else 0):
                    break
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

    def qa(self, session, plan, imported, name, proposals, supported, attempted_stages):
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
                amount = card["reservation_nanousd"]+(member["reservation_nanousd"] if member else 0)
                if not fits(self._state["by_category"], "qa", amount, planned):
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
            q = self.queue(session, plan, f"{name}/{wave_number}/members", members, category="qa")
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
            q = self.queue(session, plan, f"{name}/{wave_number}/cards", cards, category="qa")
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

    def reference_observations(self):
        rows = []
        for key, assessment in self._state["responses"].items():
            packet = self._state["packets"][key]
            if packet["role"] == "final_reference" and assessment["usable"] and assessment["attempt"] in self._state["completed"]:
                rows.extend(self.ledger.artifacts.read(assessment["parsed"])["observations"])
        return rows

    def validate(self, session, plan, source, imported, design):
        encoder = offline_tokenizer()
        def count(text):
            return len(encoder.encode(text, disallowed_special=()))
        prior_ids = set(imported["history"].get("prior_final_reference_logical_ids", []))
        tasks = design["pair_tasks"]
        for offset in range(0, len(tasks), 256):
            if self._state["health"]["stop_reason"]:
                break
            selected = tasks[offset:offset+256]
            unavailable = {t["pair_key"]: "prior_final_reference_attempt" for t in selected
                if contract.identity(source, (t["left"], t["right"]), "final_reference") in prior_ids
                or contract.identity(source, (t["left"], t["right"]), "final_reference", True) in prior_ids}
            fresh = [t for t in selected if t["pair_key"] not in unavailable]
            packets, capacity = contract.build_pair_packets(source, fresh, count, role="final_reference")
            q = self.queue(session, plan, f"validation/{offset}", packets, {**unavailable, **capacity}, category="validation")
            reason = self.dispatch(session, plan, q, packets)
            current = {t["pair_key"] for t in fresh}
            ambiguous = {r["pair_key"] for r in self.reference_observations()
                if r["pair_key"] in current and not r["clarification"] and r["semantic_unknown"]}
            clarify = [t for t in fresh if t["pair_key"] in ambiguous]
            packets, unavailable = contract.build_pair_packets(source, clarify, count, role="final_reference", clarification=True)
            q = self.queue(session, plan, f"validation/{offset}/clarification", packets, unavailable, category="validation")
            clarification_reason = self.dispatch(session, plan, q, packets)
            self.progress(stage="validate", selected_pairs=len(tasks),
                observed_pair_judgments=len({r["pair_key"] for r in self.reference_observations()}))
            if reason != "queue_complete" or clarification_reason != "queue_complete":
                break

    def run(self, session, plan, imported, selection):
        self.guard(plan["implementation"])
        q = self.queue(session, plan, "propose", selection["packets"], category="proposal")
        proposal_stop = self.dispatch(session, plan, q, selection["packets"])
        links, answer_counts, shown = [], Counter(), set()
        for packet in selection["packets"]:
            if packet["task_key"] in self._state["intents"]:
                shown.update(packet["article_ids"])
            row = self._state["responses"].get(packet["task_key"])
            if row and row["usable"] and row["attempt"] in self._state["completed"]:
                parsed = self.ledger.artifacts.read(row["parsed"])
                links.extend(parsed["links"])
                answer_counts.update({"usable_packets": 1, "direct_links": len(parsed["links"]),
                    "keep_answers": len(parsed["keep"]), "unknown_answers": len(parsed["unknown"])})
        proposals = grouping.proposals(links, selection["units"])
        self.retain(session, CHECKPOINT, "proposals", {"plan": plan["id"], "artifact": self.ledger.artifacts.put(proposals),
            "links_artifact": self.ledger.artifacts.put(links), "proposal_stage_stop": proposal_stop})
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
        successor_ref = self.ledger.artifacts.put(successor)
        changes_ref = self.ledger.artifacts.put(changes)
        frame_source = validation_source(imported["source"], selection)
        exposed = set(imported["history"].get("development_exposed_documents", [])) | set(selection["planned_shown_article_ids"])
        for key in self._state["intents"]:
            packet = self._state["packets"][key]
            exposed.update(packet.get("members", []))
        risk = {"repair_proposal": selection["candidate_article_pairs"],
            "development_positive_or_uncertain": [r["pair"] for r in imported["history"].get("pair_observations", []) if r.get("label") != "negative"]}
        self.progress(stage="freeze", changes=len(changes), after=statistics(successor))
        frame = design_module.frame_summary(frame_source, successor, exposed_documents=sorted(exposed), risk_pairs=risk)
        frozen = {"plan": plan["id"], "successor_artifact": successor_ref, "change_manifest_artifact": changes_ref,
            "baseline": "original_frozen_dossier_memberships", "derived_candidate_manifest": self.ledger.artifacts.put(frame_source["candidate_manifest"]),
            "frame_summary_artifact": self.ledger.artifacts.put(frame), "seed": VALIDATION_SEED,
            "exposed_documents": sorted(exposed), "actual_proposal_shown_documents": sorted(shown), "risk_pairs": risk}
        freeze_record = self.retain(session, CHECKPOINT, "freeze-before-draw", frozen)
        design = design_module.build_design(frame_source, successor, VALIDATION_SEED, exposed_documents=sorted(exposed), risk_pairs=risk)
        require(design["frame"] == frame, "frame_draw_binding")
        design_ref = self.ledger.artifacts.put(design)
        self.retain(session, CHECKPOINT, "sample-before-reference", {"plan": plan["id"], "freeze_record": freeze_record,
            "design_artifact": design_ref, "preflight": design["preflight"]})
        self.progress(stage="validate", selected_pairs=design["unique_pair_tasks"], certification_preflight=design["preflight"])
        self.validate(session, plan, frame_source, imported, design)
        observations = self.reference_observations()
        by_pair = {}
        for row in observations:
            by_pair.setdefault(row["pair_key"], []).append(row)
        analysis = design_module.compute_report(design, {k: contract.combine(v) for k,v in by_pair.items()})
        self._state = self.census(plan)
        result = {**self.summary(plan), "rollout_finished": True, "repair_rounds_completed": 1,
            "before": statistics(imported["state"]), "after": statistics(successor), "changes": len(changes),
            "successor_artifact": successor_ref, "change_manifest_artifact": changes_ref,
            "freeze_record": freeze_record, "design_artifact": design_ref, "analysis": analysis,
            "change_types": dict(change_types), "proposal_stage_stop": proposal_stop,
            "development_comparison": development_comparison(imported, selection, links, successor),
            "proposal_counts": {"primary": len(proposals["primary"]), "fallback": len(fallbacks), "supported_memberships": len(supported)},
            "proposal_answers": dict(answer_counts), "planned_coverage": selection["coverage_plan"],
            "actual_proposal_shown_documents": len(shown),
            "coverage": grouping.coverage_status(selection,
                set(self._state["intents"]) & {p["task_key"] for p in selection["packets"]},
                {p["task_key"] for p in selection["packets"] if p["task_key"] in self._state["responses"]
                    and self._state["responses"][p["task_key"]]["usable"]
                    and self._state["responses"][p["task_key"]]["attempt"] in self._state["completed"]}),
            "queues": [{"name": row["name"], "category": row["category"],
                "queued": len(self.ledger.artifacts.read(row["packets_artifact"])),
                "unavailable_reasons": dict(Counter(row["unavailable"].values()))} for row in self.rows(QUEUE)],
            "interpretation": "Luna-reference candidate-limited comparison; not human truth or global recall"}
        self.guard(plan["implementation"])
        identity = self.retain(session, RESULT, plan["id"], result)
        self.progress(stage="report", changes=len(changes), rollout_finished=True,
            new_committed_nanousd=result["new_committed_nanousd"], after=result["after"])
        return {"id": identity, **result}

    def summary(self, plan):
        s = self._state
        committed = s["settled_nanousd"]+s["held_nanousd"]
        cats = s["by_category"]
        quote = self.ledger.artifacts.read(plan["quote_artifact"]) if plan.get("quote_artifact") else None
        return {"method": METHOD, "plan": plan["id"], "observed_at": utc(), "policy": POLICY,
            "prepared": True, "queued_requests": len(s["packets"]), "attempted_requests": len(s["intents"]),
            "returned_requests": s["returned_requests"], "usable_requests": sum(r["usable"] for r in s["responses"].values()),
            "unattempted_requests": len(s["packets"])-len(s["intents"]), "unknown_holds": s["unknown_holds"],
            "new_settled_nanousd": s["settled_nanousd"], "new_held_nanousd": s["held_nanousd"],
            "new_committed_nanousd": committed, "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "combined_commitment_nanousd": PRIOR_COMMITMENT+committed,
            "category_commitments_nanousd": dict(cats), "planning_earmark_nanousd": s["earmarked"],
            "proposal_remaining_nanousd": max(0, PROPOSAL_CAP-cats["proposal"]),
            "repair_remaining_nanousd": max(0, REPAIR_CAP-PRIOR_COMMITMENT-cats["proposal"]-cats["qa"]),
            "validation_remaining_nanousd": max(0, VALIDATION_CAP-cats["validation"]),
            "health": s["health"], "offline_quote": quote}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "status"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require(args.action == "run" or not args.allow_paid_execution, "paid_flag_scope")
    engine = Rollout(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {"action": args.action}
        if args.action == "run":
            data["allow_paid_execution"] = args.allow_paid_execution
        print(json.dumps(engine.execute("status", data, objective="Approved one-pass snippet rollout and matched validation", actor="codex:luna-snippet-rollout")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
