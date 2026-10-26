"""Registered complete-title discovery and bounded incremental dossier repair."""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
from itertools import combinations
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
import luna_recall_repair as repair
import luna_recall_run_v2 as old
import luna_snippet_rollout_v2 as predecessor
import luna_title_summary_source as source_module
import luna_title_summary_contract as design
import luna_title_summary_repair as grouping
from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "research/cybercrime_nl/LUNA_TITLE_SUMMARY_MATCHING.md"
METHOD = OWNER_NAME = "cybercrime-nl-luna-title-summary-20261025-v1"
INTENT, SEED, PLAN, LAUNCH, QUEUE, RESPONSE, CHECKPOINT, COMMIT, RESULT = (
    "luna_title_summary_"+s for s in ("intent", "seed", "plan", "launch", "queue", "response", "checkpoint", "commit", "result"))
RECEIVED = "luna_title_summary.response.received"
FX, PRIOR_COMMITMENT = 1_119_300_000, 9_998_784_420
PRIOR_SETTLED, PRIOR_HELD = 9_977_722_440, 21_061_980
REPAIR_CAP, DISCOVERY_CAP, PILOT_CAP = 25*FX, 4*FX, FX
VALIDATION_COMMITMENT, VALIDATION_REMAINING = 6_129_023_256, 7_862_226_744
MAX_WORKERS, RPM, TPM, WORK_UNIT = 8, 500, 800_000, 32
POLICY = {"method": METHOD, "repair_cap_nanousd": REPAIR_CAP, "discovery_cap_nanousd": DISCOVERY_CAP,
    "pilot_cap_nanousd": PILOT_CAP, "prior_commitment_nanousd": PRIOR_COMMITMENT,
    "prior_settled_nanousd": PRIOR_SETTLED, "prior_held_nanousd": PRIOR_HELD,
    "validation_commitment_nanousd": VALIDATION_COMMITMENT, "validation_remaining_nanousd": VALIDATION_REMAINING,
    "validation_admission": False, "reserve_eur": 12.5, "usd_per_eur_nano": FX,
    "max_workers": MAX_WORKERS, "rpm": RPM, "tpm": TPM, "work_unit": WORK_UNIT,
    "technical_retries": 0, "automatic_interrupted_resume": False, "effective_deadline": None,
    "threshold": .85, "threshold_validated": False, "population_estimate": False}
APPROVAL = {"implementation_event": "cba6c41baa11b3eb0cc4d201", "budget_event": "7d40a2fb94ff60df464f36ac",
    "incremental_batches_selected": True, "additional_budget": False}


def require(value, reason):
    if not value:
        raise AuditError("luna_title_summary_"+reason)


def implementation():
    files = [Path(__file__), SPEC, Path(__file__).with_name("run_luna_title_summary_with_key.ps1")]
    return {**source_module.implementation(), **design.implementation(), **grouping.implementation(),
        **predecessor.implementation(), **{p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}


def fits(by_category, category, reservation, earmarked=0):
    require(set(by_category) == {"pilot", "discovery", "verification"} and category in by_category
        and type(reservation) is int and reservation >= 0 and earmarked >= 0, "admission_category")
    if PRIOR_COMMITMENT+sum(by_category.values())+reservation+earmarked > REPAIR_CAP:
        return False
    if category in {"pilot", "discovery"} and by_category["pilot"]+by_category["discovery"]+reservation > DISCOVERY_CAP:
        return False
    return category != "pilot" or by_category["pilot"]+reservation <= PILOT_CAP


def versions(desired):
    return {"protocol": desired, "question": {"text": "Find and verify missed same-event connections across all retained article titles"},
        "selection": {"rules": "Frozen complete-title blocks; pilot20 then unresolved/singletons priority;32-query incremental units"},
        "dossier_definition": {"unit": "One bounded focal occurrence under complete production rules"},
        "prompt": {"instructions": "Source-bound article summaries and permissive candidate discovery; full-source .85verification"},
        "codebook": {"labels": ["candidate", "same_event", "negative", "unknown", "supported", "committed", "deferred"]},
        "profile": {"mode": "exploratory", "population_estimate": False}, "policy": POLICY}


def health_state(intents, responses):
    result = prior.health_state(intents, responses)
    if intents:
        first = next(iter(intents))
        if not responses.get(first, {}).get("usable"):
            result["stop_reason"] = result.get("stop_reason") or "first_request_operational_gate"
    return result


def packet_pairs(packet):
    bindings = packet.get("source_bindings", {})
    pairs = {contract.pair_key(bindings[q["left"]]["document_id"], bindings[q["right"]]["document_id"]):
        sorted([bindings[q["left"]]["document_id"], bindings[q["right"]]["document_id"]])
        for q in packet.get("question_map", {}).values() if q["kind"] == "pair"}
    require(set(pairs) == set(packet.get("pair_keys", [])), "packet_pair_binding")
    return pairs


def statistics(state):
    # Canonical JSON presentation; numerical histogram keys must not be sorted
    # differently before and after native artifact storage.
    return json.loads(json.dumps(predecessor.statistics(state)))


def outcome(packet, response):
    raw, parsed, error = response.raw_response or {}, None, None
    cost = prior.observed_cost(response)
    if packet["kind"] == "responses" and cost is not None:
        output = response.usage.get("output_tokens")
        cost = cost+output*contract.OUTPUT_PRICE*(3 if response.usage["input_tokens"] > contract.LONG_THRESHOLD else 2)//2 if type(output) is int and 0 <= output <= 1_050_000 else None
    if response.payload is not None:
        try:
            if packet["role"] == "article_summary":
                parsed = design.parse_summary(packet, response.payload)
            elif packet["role"] == "title_search":
                parsed = design.parse_search(packet, response.payload)
            elif packet["role"] == "development":
                answers, observations = contract.parse_pairs(packet, response.payload)
                parsed = {"answers": answers, "observations": observations}
            elif packet["role"] == "group_membership":
                parsed = contract.parse_members(packet, response.payload)
            elif packet["role"] == "group_quality":
                parsed = contract.focal.parse_card_quality(packet, response.payload)
            else:
                raise AuditError("unexpected_role")
        except (ResearchError, AuditError, KeyError, TypeError, ValueError, AttributeError) as exc:
            error = predecessor.safe_code(exc)
    hold = bool(raw.get("unknown_outcome")) or cost is None or cost > packet["reservation_nanousd"]
    usable = not hold and parsed is not None and raw.get("http_status") == 200 and response.model == contract.base.MODEL
    fatal = None
    if raw.get("http_status") in {400, 401, 403, 404, 429}:
        fatal = "provider_authentication_configuration_or_quota"
    elif raw.get("failure_code") in {"request_preflight_rejected", "redirect_rejected", "http_status_unavailable", "response_byte_capacity", "response_content_rejected"}:
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
        "group_supported": bool(usable and packet["role"] == "group_quality" and parsed["usable"])}, parsed


class TitleSummary(Research):
    rows, one, complete, retain = prior.Audit.rows, prior.Audit.one, prior.Audit.complete, old.Recall.retain

    @staticmethod
    def counter():
        encoder = offline_tokenizer()
        return lambda text: len(encoder.encode(text, disallowed_special=()))

    def set_scope(self, imported):
        a = imported["accounting"]
        require(a["repair_commitment_nanousd"] == PRIOR_COMMITMENT and a["validation_commitment_nanousd"] == VALIDATION_COMMITMENT, "prior_cost_binding")
        require(imported["diagnostic"]["scope_admission_allowed"] is True, "source_scope")
        self._prior_logical_ids = set(imported["history"].get("logical_ids", [])) | set(imported["history"].get("prior_final_reference_logical_ids", []))
        self._prior_task_keys = set(imported["history"].get("task_keys", []))
        self._quarantine = set(imported["history"]["quarantine_document_ids"])
        self._prior_pair_keys = set(imported["history"].get("pair_attempts", {}))
        self._source_hashes = {i: digest({k: r[k] for k in ("title", "body")}) for i, r in imported["source"]["documents"].items()}
        self._source = imported["source"]
        self._clarification_allowed = set()

    def prior_pair_attempted(self, pair):
        return contract.pair_key(*pair) in self._prior_pair_keys or any(
            contract.identity(self._source, pair, role, clarification) in self._prior_logical_ids
            for role in ("development", "final_reference") for clarification in (False, True))

    def admission_scope(self, packet):
        members = set(packet.get("members", [])) | set(packet.get("document_ids", [])) | {v["document_id"] for v in packet.get("source_bindings", {}).values()}
        require(not members & self._quarantine, "quarantined_packet")
        require(not set(packet["logical_ids"]) & (self._prior_logical_ids | self._state["logical_attempted"])
            and packet["task_key"] not in self._prior_task_keys, "historical_task_retry")
        require(packet["request_sha256"] == digest(packet["request"]) and packet["reservation_nanousd"] == contract.reservation(packet), "packet_binding")
        require(all(self._source_hashes.get(v["document_id"]) == v["input_sha256"] for v in packet.get("source_bindings", {}).values()), "source_binding")
        if packet["role"] == "development":
            require(not any(self.prior_pair_attempted(pair) for pair in packet_pairs(packet).values()), "prior_pair_retry")
            if not packet.get("clarification"):
                require(not set(packet["pair_keys"]) & self._state["attempted_pair_keys"], "pair_retry")
            else:
                require(set(packet["pair_keys"]) <= self._clarification_allowed, "clarification_scope")

    def prepare(self, session, context):
        require(self.config.offline, "offline_prepare")
        require(not self.one(INTENT, optional=True), "prepare_already_attempted")
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY, "approval": APPROVAL,
            "method_artifact": self.ledger.artifacts.put_bytes(SPEC.read_bytes()), "source_binding": source_module.binding()}
        intent = self.retain(session, INTENT, METHOD, desired)
        registered = {kind: self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"] for kind, value in versions(desired).items()}
        seed = {"method": METHOD, "intent": intent, "seed": secrets.token_hex(32), "draw_performed": False}
        seed_id = self.retain(session, SEED, intent, seed)
        imported = source_module.collect(self, session)
        self.set_scope(imported)
        selection = design.build_design(imported, seed["seed"], count_tokens=self.counter())
        quote = selection["quote"]
        self.guard(desired["implementation"])
        value = {**desired, "intent": intent, "seed_record": seed_id, "versions": registered,
            "import_artifact": self.ledger.artifacts.put(imported), "selection_artifact": self.ledger.artifacts.put(selection),
            "quote_artifact": self.ledger.artifacts.put(quote), "diagnostic_artifact": self.ledger.artifacts.put(imported["diagnostic"])}
        plan = {"id": self.retain(session, PLAN, METHOD, value), **value}
        self._state = self.census(plan)
        return self.summary(plan)

    def load_plan(self):
        plan, intent = self.one(PLAN), self.one(INTENT)
        require(plan["implementation"] == implementation() and plan["policy"] == POLICY and plan["approval"] == APPROVAL, "plan_changed")
        require(plan["intent"] == intent["id"] and all(digest(plan.get(k)) == digest(v) for k, v in intent.items() if k != "id"), "intent_binding")
        require(self.ledger.artifacts.read_bytes(plan["method_artifact"]) == SPEC.read_bytes(), "method_changed")
        imported, selection = (self.ledger.artifacts.read(plan[k]) for k in ("import_artifact", "selection_artifact"))
        seed = self.one(SEED)
        require(seed["intent"] == intent["id"] and seed["id"] == plan["seed_record"] and seed["draw_performed"] is False, "seed_binding")
        self.set_scope(imported)
        # Reuse the completed exact producer result. Do not repeat the frozen
        # corpus-wide tokenizer/planner in every run/status invocation.
        require(selection["digest"] == digest({k: v for k, v in selection.items() if k != "digest"})
            and selection["selection"]["seed"] == seed["seed"]
            and selection["selection"]["state_sha256"] == digest(imported["state"]), "selection_binding")
        require(self.ledger.artifacts.read(plan["quote_artifact"]) == selection["quote"] and self.ledger.artifacts.read(plan["diagnostic_artifact"]) == imported["diagnostic"], "derived_binding")
        self.completed_prepare(plan)
        return plan, imported, selection

    def summary(self, plan):
        s = self._state
        committed = s["settled_nanousd"]+s["held_nanousd"]
        return {"method": METHOD, "plan": plan["id"], "prepared": True, "observed_at": utc(), "policy": POLICY,
            "queued_requests": len(s["packets"]), "attempted_requests": len(s["intents"]), "returned_requests": s["returned_requests"],
            "usable_requests": sum(r["usable"] for r in s["responses"].values()), "unknown_holds": s["unknown_holds"],
            "new_settled_nanousd": s["settled_nanousd"], "new_held_nanousd": s["held_nanousd"], "new_committed_nanousd": committed,
            "combined_repair_commitment_nanousd": PRIOR_COMMITMENT+committed,
            "repair_remaining_nanousd": REPAIR_CAP-PRIOR_COMMITMENT-committed,
            "discovery_remaining_nanousd": DISCOVERY_CAP-s["by_category"]["pilot"]-s["by_category"]["discovery"],
            "pilot_remaining_nanousd": PILOT_CAP-s["by_category"]["pilot"],
            "combined_repair_validation_commitment_nanousd": PRIOR_COMMITMENT+VALIDATION_COMMITMENT+committed,
            "validation_commitment_nanousd": VALIDATION_COMMITMENT, "validation_remaining_nanousd": VALIDATION_REMAINING,
            "category_commitments_nanousd": dict(s["by_category"]), "health": s["health"],
            "quote_artifact": plan["quote_artifact"], "diagnostic_artifact": plan["diagnostic_artifact"]}

    def parsed(self, packet):
        row = self._state["responses"].get(packet["task_key"])
        if row and row["usable"] and row["attempt"] in self._state["completed"]:
            return self.ledger.artifacts.read(row["parsed"])
        return None

    def discover(self, session, plan, imported, selection, unit, summaries, search_results, coverage):
        """Exactly one pass over the frozen summary/query-block identities."""
        category = "pilot" if unit == 0 else "discovery"
        ids = selection["work_units"][unit]
        packets, unavailable = [], {}
        for i in ids:
            if i in selection["summary_unavailable"]:
                unavailable[i] = selection["summary_unavailable"][i]
                continue
            p = design.summary_packet(imported["source"], i, self.counter())
            require({k: p[k] for k in selection["summary_quotes"][i]} == selection["summary_quotes"][i], "summary_quote_binding")
            packets.append(p)
        q = self.queue(session, plan, f"unit-{unit}/summaries", packets, unavailable, category=category)
        self.dispatch(session, plan, q, packets)
        for p in packets:
            row = self.parsed(p)
            i = p["bindings"]["document_id"]
            if row:
                summaries[i] = row
            else:
                unavailable[i] = "summary_unknown" if p["task_key"] in self._state["intents"] else "summary_unattempted"
        blocks = [d for d in selection["descriptors"] if d["work_unit"] == unit]
        packets = []
        for descriptor in blocks:
            if any(i not in summaries for i in descriptor["query_ids"]):
                continue
            packets.append(design.search_packet(selection["catalogue"], descriptor, summaries, self.counter()))
        q = self.queue(session, plan, f"unit-{unit}/title-search", packets, category=category)
        self.dispatch(session, plan, q, packets)
        for p in packets:
            row = self.parsed(p)
            if row:
                search_results[p["descriptor"]["digest"]] = row
        candidates = set()
        for i in ids:
            intended = [d for d in blocks if i in d["query_ids"]]
            returned = [search_results[d["digest"]] for d in intended if d["digest"] in search_results]
            outputs = [next(r for r in result["results"] if r["query_id"] == i) for result in returned]
            # Even incomplete search output can suggest a candidate. Its lack of
            # other candidates never establishes absence or search completeness.
            candidates.update(tuple(sorted((i, j))) for row in outputs for j in row["candidate_ids"])
            missing_titles = len(selection["catalogue"]["unavailable"]) - int(i in selection["catalogue"]["unavailable"])
            capacity = any(i in r["query_ids"] for r in selection["capacity_unavailable"])
            coverage[i] = {"work_unit": unit, "summary_usable": i in summaries,
                "planned_blocks": len(intended), "returned_blocks": len(outputs),
                "eligible_title_blocks_complete": bool(intended) and not capacity and len(outputs) == len(intended)
                    and all(row["complete"] for row in outputs),
                "unavailable_other_titles": missing_titles,
                "intended_other_titles": len(imported["source"]["documents"])-1,
                "candidate_count": len({j for row in outputs for j in row["candidate_ids"]}),
                "reason": unavailable.get(i), "uniqueness_established": False}
        checkpoint = {"plan": plan["id"], "work_unit": unit,
            "coverage_artifact": self.ledger.artifacts.put({i: coverage[i] for i in ids}),
            "summaries_artifact": self.ledger.artifacts.put({i: summaries[i] for i in ids if i in summaries}),
            "search_results_artifact": self.ledger.artifacts.put([search_results[d["digest"]] for d in blocks if d["digest"] in search_results]),
            "candidate_pairs_artifact": self.ledger.artifacts.put([list(p) for p in sorted(candidates)])}
        self.retain(session, CHECKPOINT, f"unit-{unit}/discovery", checkpoint)
        self.progress(stage="discover", work_unit=unit, queries_processed=len(coverage),
            complete_eligible_query_coverage=sum(r["eligible_title_blocks_complete"] for r in coverage.values()),
            title_candidate_pairs=len(candidates), new_committed_nanousd=sum(self._state["by_category"].values()))
        return candidates

    def verify_pairs(self, session, plan, imported, unit, candidates, observations, seen_candidates, current_state):
        source = imported["source"]
        fresh, dispositions = [], {}
        membership = repair.membership(current_state)
        for pair in sorted(candidates):
            key = contract.pair_key(*pair)
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            if pair[0] in membership and membership.get(pair[0]) == membership.get(pair[1]):
                dispositions[key] = "already_coassigned"
            elif set(pair) & self._quarantine:
                dispositions[key] = "quarantined"
            elif contract.combine(observations.get(key, [])) != "unknown":
                dispositions[key] = "compatible_evidence_reused"
            elif self.prior_pair_attempted(pair):
                dispositions[key] = "historical_pair_attempt_unknown"
            elif key in self._state["attempted_pair_keys"]:
                dispositions[key] = "already_attempted"
            else:
                fresh.append({"left": pair[0], "right": pair[1], "pair_key": key})
        packets, unavailable = contract.build_pair_packets(source, fresh, self.counter(), role="development")
        q = self.queue(session, plan, f"unit-{unit}/pairs", packets, unavailable, category="verification")
        self.dispatch(session, plan, q, packets)
        clarification = []
        for packet in packets:
            parsed = self.parsed(packet)
            if parsed:
                for row in parsed["observations"]:
                    observations.setdefault(row["pair_key"], []).append(row)
                    if row["label"] == "unknown" and row.get("semantic_unknown"):
                        a, b = row["pair"]
                        clarification.append({"left": a, "right": b, "pair_key": row["pair_key"]})
                        self._clarification_allowed.add(row["pair_key"])
            else:
                for key in packet["pair_keys"]:
                    dispositions[key] = "new_pair_unknown" if packet["task_key"] in self._state["intents"] else "pair_budget_or_health_unattempted"
        packets, unclarified = contract.build_pair_packets(source, clarification, self.counter(), role="development", clarification=True)
        q = self.queue(session, plan, f"unit-{unit}/clarification", packets, unclarified, category="verification")
        self.dispatch(session, plan, q, packets)
        for packet in packets:
            parsed = self.parsed(packet)
            if parsed:
                for row in parsed["observations"]:
                    observations.setdefault(row["pair_key"], []).append(row)
        self.retain(session, CHECKPOINT, f"unit-{unit}/pair-outcomes", {"plan": plan["id"],
            "candidate_count": len(candidates), "fresh_selected_pairs": len(fresh), "clarification_selected_pairs": len(clarification),
            "unavailable": {**unavailable, **unclarified}, "dispositions": dispositions})

    def commit_unit(self, session, plan, imported, unit, state, observations, seen_candidates,
            deferred_keys, deferred_memberships, attempted_stages):
        positives, negatives = [], []
        for key, rows in observations.items():
            label = contract.combine(rows)
            if label == "negative":
                negatives.append(rows[0]["pair"])
            elif label == "same_event" and key in seen_candidates:
                positives.append(rows[0]["pair"])
        attempted = set(imported["history"]["membership_attempts"]) | {r for r, _ in attempted_stages}
        proposal = grouping.build_proposals(imported["source"], state, positives, negatives, work_unit=unit,
            deferred_pair_keys=deferred_keys, deferred_memberships=deferred_memberships, attempted_memberships=attempted)
        self.retain(session, CHECKPOINT, f"unit-{unit}/proposal", {"plan": plan["id"],
            "proposal_artifact": self.ledger.artifacts.put(proposal)})
        supported = {}
        current = {**imported, "history": {**imported["history"], "pair_observations":
            [row for rows in observations.values() for row in rows]}}
        outcomes = self.qa(session, plan, current, f"unit-{unit}/primary", proposal["primary"], supported, attempted_stages, category="verification")
        attempted_now = set(imported["history"]["membership_attempts"]) | {r for r, _ in attempted_stages}
        fallbacks = grouping.eligible_fallbacks(proposal, outcomes, attempted_memberships=attempted_now)
        self.qa(session, plan, current, f"unit-{unit}/fallback", fallbacks, supported, attempted_stages, category="verification")
        chosen = grouping.select_supported(proposal, state, supported,
            eligible_fallback_revisions=[p["membership_revision"] for p in fallbacks])
        self.guard(plan["implementation"])
        require(digest(state) == proposal["state_sha256"], "stale_commit")
        successor = repair.commit(state, chosen["changes"], reason=f"{METHOD}/unit-{unit}")
        value = {"plan": plan["id"], "work_unit": unit, "before_sha256": digest(state),
            "proposal_artifact": self.ledger.artifacts.put(proposal),
            "selection_artifact": self.ledger.artifacts.put(chosen),
            "changes_artifact": self.ledger.artifacts.put(chosen["changes"]),
            "successor_artifact": self.ledger.artifacts.put(successor),
            "after": statistics(successor), "versions": plan["versions"]}
        # One immutable record publishes all changes for this unit atomically.
        identity = self.retain(session, COMMIT, f"unit-{unit}", value)
        self.progress(stage="commit", work_unit=unit, last_commit=identity, changes=len(chosen["changes"]), after=value["after"])
        return successor, chosen["deferred_pair_keys"], chosen["deferred_memberships"]

    def replay_commits(self, plan, initial):
        state, all_changes = deepcopy(initial), []
        previous_unit = -1
        for record in self.rows(COMMIT):
            require(record["plan"] == plan["id"] and record["versions"] == plan["versions"]
                and record["before_sha256"] == digest(state) and record["work_unit"] > previous_unit, "commit_chain")
            changes = self.ledger.artifacts.read(record["changes_artifact"])
            successor = repair.commit(state, changes, reason=f"{METHOD}/unit-{record['work_unit']}")
            require(successor == self.ledger.artifacts.read(record["successor_artifact"])
                and digest(statistics(successor)) == digest(record["after"]), "commit_replay")
            state, previous_unit = successor, record["work_unit"]
            all_changes.extend(changes)
        return state, all_changes

    def run(self, session, plan, imported, selection):
        self.guard(plan["implementation"])
        self.retain(session, LAUNCH, plan["id"], {"plan": plan["id"], "implementation": plan["implementation"],
            "at": utc(), "allow_paid_execution": True, "restart_allowed": False})
        summaries, search_results, coverage = {}, {}, {}
        state = deepcopy(imported["state"])
        observations = repair.observations_by_pair(imported["history"].get("pair_observations", []))
        seen_candidates, attempted_stages, deferred_keys, deferred_memberships = set(), set(), [], []
        pilot = {"passed": False, "reason": "pilot_reservation_exceeds_subcap"}
        stop = pilot["reason"]
        if selection["quote"]["pilot_reservation_nanousd"] <= PILOT_CAP:
            candidates = self.discover(session, plan, imported, selection, 0, summaries, search_results, coverage)
            pilot = design.summarize_pilot(selection, list(search_results.values()), coverage)
            pilot["passed"] = pilot["threshold_met"] and pilot["all_selected_title_coverage_complete"]
            self.retain(session, CHECKPOINT, "pilot", {"plan": plan["id"], "pilot": pilot})
            stop = "pilot_gate_not_passed"
            if pilot["passed"] and not self._state["health"]["stop_reason"]:
                stop = "single_pass_finished"
                for unit in range(len(selection["work_units"])):
                    if unit:
                        if self._state["health"]["stop_reason"]:
                            stop = self._state["health"]["stop_reason"]
                            break
                        if self._state["by_category"]["pilot"]+self._state["by_category"]["discovery"] >= DISCOVERY_CAP:
                            stop = "discovery_budget_bound"
                            break
                        candidates = self.discover(session, plan, imported, selection, unit, summaries, search_results, coverage)
                    self.verify_pairs(session, plan, imported, unit, candidates, observations, seen_candidates, state)
                    state, deferred_keys, deferred_memberships = self.commit_unit(session, plan, imported, unit,
                        state, observations, seen_candidates, deferred_keys, deferred_memberships, attempted_stages)
                    if self._state["health"]["stop_reason"]:
                        stop = self._state["health"]["stop_reason"]
                        break
                    if PRIOR_COMMITMENT+sum(self._state["by_category"].values()) >= REPAIR_CAP:
                        stop = "repair_budget_bound"
                        break
        self._state = self.census(plan)
        replayed, changes = self.replay_commits(plan, imported["state"])
        require(state == replayed, "successor_replay")
        terminal = self._state["health"]["stop_reason"] or stop
        result = {**self.summary(plan), "title_summary_finished": True, "terminal_reason": terminal,
            "pilot": pilot, "before": statistics(imported["state"]), "after": statistics(state),
            "changes": len(changes), "committed_work_units": len(self.rows(COMMIT)),
            "queries_selected": len(selection["query_order"]), "queries_processed": len(coverage),
            "summaries_usable": len(summaries), "title_blocks_usable": len(search_results),
            "eligible_title_coverage_complete": sum(v["eligible_title_blocks_complete"] for v in coverage.values()),
            "queries_not_reached": len(selection["query_order"])-len(coverage),
            "unique_candidate_pairs": len(seen_candidates), "overlap_deferred_memberships": len(deferred_memberships),
            "successor_artifact": self.ledger.artifacts.put(state), "change_manifest_artifact": self.ledger.artifacts.put(changes),
            "coverage_artifact": self.ledger.artifacts.put(coverage), "pair_observations_artifact": self.ledger.artifacts.put(observations),
            "deferred_artifact": self.ledger.artifacts.put({"pair_keys": deferred_keys, "memberships": deferred_memberships}),
            "new_final_reference_judgments": 0, "population_precision_recall_measured": False,
            "singleton_uniqueness_established": False, "quarantined_inputs": len(self._quarantine),
            "interpretation": "Exploratory Luna-reference title discovery and full-source membership/card support"}
        self.guard(plan["implementation"])
        identity = self.retain(session, RESULT, plan["id"], result)
        self.progress(stage="report", title_summary_finished=True, terminal_reason=terminal, after=result["after"],
            changes=len(changes), new_committed_nanousd=result["new_committed_nanousd"])
        return {"id": identity, **result}


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
                self.completed_result(plan, result)
                return result
            if data["action"] == "status":
                return self.summary(plan)
            require(not self.config.offline and data["allow_paid_execution"] is True and bool(os.environ.get("OPENAI_API_KEY")), "paid_authority_and_key")
            require(not self._state["intents"] and not self.one(LAUNCH, optional=True), "interrupted_run_requires_review")
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

    def completed_result(self, plan, result):
        require(result["plan"] == plan["id"] and result["method"] == METHOD, "result_plan")
        row = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (result["id"],)).fetchone()
        require(row is not None, "result_record")
        created = row[0]
        producer = self.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (created,)).fetchone()[0]
        events = [dict(e) for e in self.ledger.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (producer,))]
        selected = {kind: [e for e in events if e["kind"] == kind] for kind in
            ("session.started", "operation.intended", "operation.completed", "session.ended", "operation.failed")}
        require(not selected["operation.failed"] and all(len(selected[k]) == 1 for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended")), "result_producer_not_completed")
        start, incoming, done, ended = (selected[k][0] for k in
            ("session.started", "operation.intended", "operation.completed", "session.ended"))
        require(start["seq"] < incoming["seq"] < created < done["seq"] < ended["seq"]
            and json.loads(ended["payload"]) == {"status": "completed"}, "result_chronology")
        intended, completed = json.loads(incoming["payload"]), json.loads(done["payload"])
        require(intended["operation"] == completed["operation"] == "status"
            and self.ledger.artifacts.read(intended["input"]) == {"action": "run", "allow_paid_execution": True}
            and digest(self.ledger.artifacts.read(completed["result"])) == digest(result), "result_completion_binding")
        identity = self.ledger.artifacts.read(json.loads(start["payload"])["identity"])
        require(all(identity["code_files"].get(p) == h for p, h in plan["implementation"].items()
            if p.startswith("src/") and p.endswith(".py")), "result_runtime_identity")

    def census(self, plan):
        state = {"intents": {}, "responses": {}, "packets": {}, "queues": {}, "logical_attempted": set(), "attempted_pair_keys": set(),
            "settled_nanousd": 0, "held_nanousd": 0, "unknown_holds": 0, "returned_requests": 0,
            "by_category": {"pilot": 0, "discovery": 0, "verification": 0}, "earmarked": 0,
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
                and i["category"] == q["category"] and i["category"] in {"pilot", "discovery", "verification"}
                and i["packet"] == digest(p) and i["request"] == p["request_sha256"] and i["reserved_nanousd"] == p["reservation_nanousd"], "intent_binding")
            require(not state["logical_attempted"].intersection(p["logical_ids"]), "logical_retry")
            require(self.ledger.artifacts.read(i["dispatch"]) == wire.Invocation(p["request"], i["attempt"], kind=p["kind"]).manifest(), "dispatch_binding")
            state["intents"][key], attempts[i["attempt"]] = i, key
            state["logical_attempted"].update(p["logical_ids"])
            state["attempted_pair_keys"].update(p.get("pair_keys", []))
        receipts = {}
        for e in self.ledger.db.execute("SELECT payload FROM events WHERE kind='luna_title_summary.response.received' ORDER BY seq"):
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
        state["health"] = health_state(state["intents"], health_rows)
        return state

    def queue(self, session, plan, name, packets, unavailable=None, *, category):
        require(not any(r["name"] == name for r in self.rows(QUEUE)), "duplicate_queue")
        require(category in {"pilot", "discovery", "verification"}, "queue_category")
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
            limit = MAX_WORKERS if s["intents"] else 1
            while position < len(ready) and len(wave) < limit:
                p = ready[position]
                position += 1
                if not fits(s["by_category"], queue["category"], p["reservation_nanousd"], s["earmarked"]):
                    continue
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
                s["attempted_pair_keys"].update(p.get("pair_keys", []))
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
                self.ledger.append(session, "luna_title_summary.response.received", {"attempt": i["attempt"], "response": raw})
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
            s["health"] = health_state(s["intents"], s["responses"])
            self.progress(stage=queue["name"], queued=len(s["packets"]), queue_queued=len(packets),
                attempted=len(s["intents"]), returned=s["returned_requests"], usable=sum(r["usable"] for r in s["responses"].values()),
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
                if set(p["members"]) & self._quarantine:
                    unavailable[rev] = "quarantined_proposal"
                    continue
                if p.get("blocked_reason") not in {None, "exact_membership_already_attempted"}:
                    unavailable[rev] = p["blocked_reason"]
                    continue
                if rev in supported:
                    continue
                h = history.get(rev, {})
                if h.get("blocked") or any(tuple(sorted(pair)) in negatives for pair in combinations(p["members"], 2)):
                    unavailable[rev] = "negative_conflict" if any(tuple(sorted(pair)) in negatives for pair in combinations(p["members"], 2)) else "historical_attempt_block"
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
                    unavailable[rev] = "preflight_capacity"
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
                    continue
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
        return {**unavailable, **{r: "usable_semantic_rejection" for r in rejected},
            **{r: "supported" for r in supported if r in {p["membership_revision"] for p in proposals}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "run", "status"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    require(args.action == "run" or not args.allow_paid_execution, "paid_flag_scope")
    engine = TitleSummary(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {"action": args.action}
        if args.action == "run":
            data["allow_paid_execution"] = args.allow_paid_execution
        print(json.dumps(engine.execute("status", data,
            objective="Discover title-summary candidates across all retained titles and commit full-source supported repairs",
            actor="codex:luna-title-summary")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
