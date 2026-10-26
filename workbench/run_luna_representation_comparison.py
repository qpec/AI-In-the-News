"""Audited paired comparison of original articles and saved Luna representations."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import sys
import time
import uuid

from newsresearch import luna_decisions_matching as transport
from newsresearch import luna_matching_experiments15 as features
from newsresearch import luna_representation_comparison as core
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, require_no_credentials, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402
import luna_event_contract_v2 as contract  # noqa: E402
from check_provider_event_labels import ConversationHandoff, Invocation  # noqa: E402
from run_luna_matching_experiments15 import Source  # noqa: E402

METHOD = core.METHOD
SEED = "luna-representation-comparison-20261020-v1"
BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
PARENT = "luna-fifteen-experiments-20261020-v2"
STANDARD = "luna-standard-full-corpus-20261018-v2"
PILOT = "luna-matching-pilot-20261020-v1"
TOTAL_BUDGET = 20_000_000_000
STUDY_BUDGET = 2_000_000_000


def implementation():
    paths = [Path(__file__), Path(core.__file__), Path(transport.__file__),
        Path(features.__file__), Path(features.base.__file__), Path(contract.__file__),
        Path(state.__file__), Path(__file__).with_name("run_luna_matching_experiments15.py"),
        Path(__file__).resolve().parents[1] / "scripts/check_provider_event_labels.py"]
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class Study(Research):
    def rows(self, kind):
        return [{**self.ledger.get(r[0], kind), "_record_id": r[0]} for r in
            self.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def one(self, kind):
        rows = self.rows(kind)
        if len(rows) != 1:
            raise AuditError("comparison_one_record_required_" + kind)
        return rows[0]

    def absent(self, kind, key=None):
        rows = self.rows(kind)
        if any(key is None or r.get("split") == key for r in rows):
            raise AuditError("comparison_already_frozen_no_retry_" + kind)

    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "prepare":
            return self.prepare(session, context, data)
        plan = self.one("representation_plan")
        if plan["implementation"] != implementation():
            raise AuditError("comparison_implementation_changed_after_freeze")
        if action == "dispatch":
            return self.dispatch(session, plan)
        if action == "read":
            handoff = self.one("representation_handoff")
            packet = self.ledger.artifacts.read(handoff["request"])
            panels = [p for p in packet["panels"] if data["start"] <= p["panel"] <= data["end"]]
            self.ledger.append(session, "representation.inspected", {
                "request": handoff["request"], "panels": [p["panel"] for p in panels]})
            return {"instructions": core.REFERENCE_RULES, "panels": panels}
        if action == "submit":
            return self.submit(session, plan, data)
        if action == "run":
            return self.run_pairs(session, plan, data)
        if action == "calibrate":
            return self.calibrate(session, plan)
        if action == "report":
            return self.report(session, plan)
        raise AuditError("unknown_comparison_action")

    def prepare(self, session, context, data):
        self.absent("representation_plan")
        versions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "scope": "60 matched pairs, 40 articles, three representations, at most 180 serial Decisions calls. Full original retained sources are judged by current Codex through audited handoff before any Decisions run. No Luna fields or Decisions responses in reference packet. These are model references, not human gold. Code uses development responses only to freeze thresholds before dispatch of test requests. Same researcher and closely related models are not independent judges. No extraction, collection, controller restart or production grouping.",
                "measurement": "Report raw labels, fixed .95 and development-selected thresholds for each arm. Threshold grid maximizes supported same-event calls with zero different/ambiguous same calls, ties favor higher threshold; 1.01 abstains. Test comparison is descriptive, not a new deployment selection. Pairs within a panel are dependent; no population accuracy or high-precision certification. No separate full-corpus candidate recall claim.",
                "cost": "Exact provider input tokens at official Decisions $0.10/M; reserve 10% region margin and 2x above 272000 tokens. $0.25 serial reservation. Unknown outcome retains hold and stops without retry. Prior Codex extraction has no per-article dollar bill; report measured marginal Decisions charges and extraction break-even, never invent extraction spend.",
                "source": "Saved Standard originals only; source-map, complete body reconstruction, exact body hash and request provenance verified. Preserve all usable extraction variants; passages are exact referenced units, excluding excluded-boilerplate refs. No article truncation. Reject an oversized panel mechanically before references; record exclusions. Other source inconsistency stops."},
            "question": {"text": "Do saved Luna extractions improve event identity decisions versus full original articles, and do supporting passages alter errors, abstention and marginal cost?"},
            "selection": {"rules": "Fresh exact named-entity families of 4-120 eligible ready cards. Exclude previous 30 panel anchor families/bodies and earlier 1100-pilot IDs/available hashes. Stable hash family/window/card selection. Per corpus five disjoint four-article panels: three publishers within 7 publication days plus a same-family distinct-body article 15-365 days away, otherwise another distinct-body nearby article. All six pairs/panel. First two panels/corpus development, remaining three test. Ready-extraction and wire-size conditional sample, not random corpus sample. All three arms use identical pairs, side assignment, publication metadata, instructions and choices; arm order hash-randomized inside pair.",
                "seed": SEED, "parent": PARENT, "base": data["base"]},
            "dossier_definition": {"unit": "One specific focal occurrence; distinct actions in the same story remain separate, uncertain parent/subevent boundaries abstain."},
            "codebook": {"labels": list(transport.LABELS), "definitions": core.REFERENCE_RULES},
            "prompt": {"instructions": core.RULES, "reference_instructions": core.REFERENCE_RULES},
            "profile": {"mode": "exploratory", "population_estimate": False},
            "policy": {"scope": "User Do that authorizes this comparison within existing $20 matching API ceiling.",
                "maximum_new_cost_nanousd": STUDY_BUDGET, "total_matching_budget_nanousd": TOTAL_BUDGET,
                "maximum_requests": 180, "maximum_wire_bytes": transport.MAX_WIRE_BYTES,
                "reservation_nanousd": transport.RESERVATION_NANOUSD, "retries": 0,
                "price_sources": ["https://developers.openai.com/api/docs/guides/decisions"],
                "price_checked": "2026-10-20"},
        }
        bound = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"] for k, v in versions.items()}
        self.ledger.append(session, "representation.prepare.intended", {"versions": bound})
        base = Path(data["base"]).resolve()
        prior = Source(base / PILOT)
        try:
            previous = prior.rows("luna_matching_pilot_decision")
            if not previous or any(v["unknown_or_billing_hold"] or v["reserved_nanousd"] for v in previous):
                raise AuditError("previous_matching_budget_not_settled")
            prior_spend = sum(v["cost_nanousd_with_regional_margin"] for v in previous)
        finally:
            prior.close()
        if prior_spend + STUDY_BUDGET > TOTAL_BUDGET:
            raise AuditError("comparison_budget_exceeds_remaining_authorization")
        source = Source(base / PARENT)
        try:
            frozen = source.one("matching15_input")
            old_panels = source.one("luna_scalable_panel_plan")
            cards = {c["article_id"]: c for ref in frozen["chunks"] for c in source.artifacts.json(ref)}
        finally:
            source.close()
        excluded = {tuple(v) for v in frozen["excluded_bodies"]}
        families = {tuple(v) for v in frozen["excluded_families"]}
        excluded_ids = set(frozen["excluded_article_ids"])
        for panel in old_panels["mapping"]:
            families.add((panel["corpus"], panel["family_key"]))
            for identifier in panel["cards"].values():
                excluded_ids.add(identifier)
                excluded.add((cards[identifier]["corpus"], cards[identifier]["body_sha256"]))
        field, publishers, groups = {}, {}, defaultdict(list)
        for identifier, card in cards.items():
            if card["readiness"] != "ready" or identifier in excluded_ids or (card["corpus"], card["body_sha256"]) in excluded:
                continue
            value = features.enrich(card)
            pubs = {m["publisher"]["uri"] for m in card["metadata_variants"] if m["publisher"]["uri"]}
            if value.base.day is None or len(pubs) != 1:
                continue
            field[identifier], publishers[identifier] = value, next(iter(pubs))
            for name in value.names:
                groups[(card["corpus"], name)].append(identifier)
        originals = state.SelectedArtifacts(base / STANDARD)

        def load_views(identifier):
            card = cards[identifier]
            provenance = {p["assessment"]: p for p in card["provenance"]}
            packets = {}
            for r in card["records"]:
                if not r["mechanically_usable"]:
                    continue
                p = provenance[r["extraction_id"]]
                if Path(p["owner"]).resolve() != base / STANDARD:
                    raise AuditError("comparison_unexpected_source_owner")
                request = originals.json(p["request"])
                packet = request["packet"]
                if contract.validate_packet(packet):
                    raise AuditError("comparison_original_packet_invalid")
                body = packet["source_map"]["source_fields"]["body"]["text"]
                if hashlib.sha256(body.encode("utf-8")).hexdigest() != card["body_sha256"]:
                    raise AuditError("comparison_original_body_hash_mismatch")
                if digest(r["output"]) != r["output_sha256"]:
                    raise AuditError("comparison_saved_output_hash_mismatch")
                packets[r["extraction_id"]] = packet
            return core.views(card, packets)

        panels, mapping, tasks, used, selected_views, skipped = [], [], [], set(), {}, []
        for corpus in sorted({k[0] for k in groups}):
            selected = 0
            keys = sorted((k for k, ids in groups.items() if k[0] == corpus and 4 <= len(ids) <= 120 and k not in families), key=lambda k: digest([SEED, k]))
            for key in keys:
                if selected == 5:
                    break
                members = sorted((i for i in groups[key] if (corpus, cards[i]["body_sha256"]) not in used), key=lambda i: (field[i].base.day, i))
                windows = []
                for a in members:
                    nearby = [i for i in members if 0 <= field[i].base.day - field[a].base.day <= 7]
                    if len({publishers[i] for i in nearby}) >= 3:
                        windows.append((a, nearby))
                if not windows:
                    continue
                anchor, nearby = min(windows, key=lambda v: digest([SEED, key, v[0]]))
                chosen, pubs, bodies = [], set(), set()
                for i in sorted(nearby, key=lambda i: digest([SEED, key, i])):
                    if publishers[i] not in pubs and cards[i]["body_sha256"] not in bodies:
                        chosen.append(i)
                        pubs.add(publishers[i])
                        bodies.add(cards[i]["body_sha256"])
                    if len(chosen) == 3:
                        break
                if len(chosen) != 3:
                    continue
                distant = [i for i in members if 15 <= abs(field[i].base.day - field[anchor].base.day) <= 365 and cards[i]["body_sha256"] not in bodies]
                extra = distant or [i for i in nearby if cards[i]["body_sha256"] not in bodies]
                if not extra:
                    continue
                chosen.append(min(extra, key=lambda i: digest([SEED, "extra", key, i])))
                view = {i: load_views(i) for i in chosen}
                number, split = len(panels) + 1, "development" if selected < 2 else "test"
                mapped = dict(zip("ABCD", chosen, strict=True))
                panel_tasks = []
                try:
                    for a, b in combinations("ABCD", 2):
                        pair = digest([METHOD, corpus, mapped[a], mapped[b]])
                        for arm in sorted(core.ARMS, key=lambda arm: digest([SEED, pair, arm])):
                            wire = core.request(view[mapped[a]][arm], view[mapped[b]][arm])
                            panel_tasks.append({"pair_id": pair, "panel": number, "split": split, "a": a, "b": b, "arm": arm,
                                "request": self.ledger.artifacts.put(wire), "wire_bytes": len(canonical(wire).encode("utf-8"))})
                except ResearchError as error:
                    if str(error) != "representation_wire_byte_cap":
                        raise
                    skipped.append({"family": key, "articles": chosen, "reason": str(error)})
                    continue
                selected_views.update(view)
                tasks.extend(panel_tasks)
                panels.append({"panel": number, "cards": [{"side": side, **view[i]["article"]} for side, i in mapped.items()]})
                mapping.append({"panel": number, "split": split, "corpus": corpus, "family_key": key[1], "cards": mapped, "distant_fourth": bool(distant)})
                used.update((corpus, cards[i]["body_sha256"]) for i in chosen)
                selected += 1
            if selected != 5:
                raise AuditError("comparison_insufficient_fresh_families")
        if len(tasks) != 180 or len(selected_views) != 40:
            raise AuditError("comparison_unexpected_sample_size")
        result = {"versions": bound, "implementation": implementation(), "created_at": utc(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
            "source_input": frozen["_record_id"], "excluded_previous_panels": old_panels["_record_id"],
            "panels": self.ledger.artifacts.put(panels), "views": self.ledger.artifacts.put(selected_views),
            "cards": self.ledger.artifacts.put([cards[i] for i in selected_views]),
            "manifest": self.ledger.artifacts.put(tasks), "mapping": mapping,
            "mechanical_panel_exclusions": skipped, "prior_cost_nanousd": prior_spend,
            "maximum_cost_nanousd": STUDY_BUDGET, "reservation_nanousd": transport.RESERVATION_NANOUSD,
            "prior_missing_pilot_body_hashes": frozen["pilot_cards_missing_body_hash"],
            "human_validated": False, "new_extractions": 0}
        identifier = self.ledger.record(session, "representation_plan", METHOD, result)
        return {"id": identifier, "panels": len(panels), "articles": len(selected_views), "pairs": len(tasks) // 3,
            "planned_requests": len(tasks), "mechanical_panel_exclusions": len(skipped),
            "prior_matching_cost_usd": prior_spend / 1e9, "new_study_cap_usd": STUDY_BUDGET / 1e9}

    def dispatch(self, session, plan):
        self.absent("representation_handoff")
        packet = {"instructions": core.REFERENCE_RULES, "panels": self.ledger.artifacts.read(plan["panels"])}
        attempt = str(uuid.uuid4())
        invocation = Invocation(packet)
        intended = {"attempt": attempt, "task_key": plan["_record_id"], "number": 1, "batch": plan["_record_id"],
            "request": self.ledger.artifacts.put(packet), "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc()}
        self.ledger.append(session, "model.attempt.intended", intended)
        self.ledger.unresolved[attempt] = intended
        identifier = self.ledger.record(session, "representation_handoff", METHOD, intended)
        response = next(self.gateway.codex_dispatch(session, ConversationHandoff(), [(invocation, attempt)], 1))[1]
        if not (response.raw_response or {}).get("handoff_ready"):
            raise AuditError("comparison_reference_handoff_failed")
        return {"id": identifier, "status": "awaiting_60_full_source_model_references"}

    def complete(self, session, intended, response_ref, assessment, status):
        def project(event):
            self.ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
                intended["attempt"], intended["task_key"], intended["batch"], 1, intended["request"],
                response_ref, status, assessment, None, event))
        self.ledger.append(session, "model.attempt.completed", {"attempt": intended["attempt"], "status": status,
            "assessment": assessment, "response": response_ref, "ended_at": utc()}, project)
        self.ledger.unresolved.pop(intended["attempt"])

    def submit(self, session, plan, data):
        self.absent("representation_references")
        handoff = self.one("representation_handoff")
        if handoff["attempt"] not in self.ledger.unresolved:
            raise AuditError("comparison_handoff_already_completed")
        panels = {p["panel"]: {c["side"]: c for c in p["cards"]} for p in self.ledger.artifacts.read(plan["panels"])}
        inspected = {p for row in self.ledger.db.execute("SELECT payload FROM events WHERE kind='representation.inspected'")
            for p in json.loads(row[0])["panels"]}
        if inspected != set(panels):
            raise AuditError("comparison_all_originals_must_be_read")
        raw = Path(data["input"]).read_text(encoding="utf-8-sig")
        require_no_credentials(raw)
        replies = json.loads(raw)
        expected = {(p, a, b) for p in panels for a, b in combinations("ABCD", 2)}
        if len(replies) != 60 or {(r["panel"], r["a"], r["b"]) for r in replies} != expected:
            raise AuditError("comparison_reference_pair_coverage")
        for r in replies:
            if set(r) != {"panel", "a", "b", "label", "rationale", "evidence_a", "evidence_b"} or r["label"] not in transport.LABELS:
                raise AuditError("comparison_reference_shape")
            if not isinstance(r["rationale"], str) or len(r["rationale"].strip()) < 10:
                raise AuditError("comparison_reference_rationale")
            for side in ("a", "b"):
                card = panels[r["panel"]][r[side]]
                quote = r["evidence_" + side]
                if not isinstance(quote, str) or not 8 <= len(quote) <= 300 or not any(quote in text for text in [card["title"], *(p["text"] for p in card["paragraphs"])]):
                    raise AuditError("comparison_reference_quote_" + str((r["panel"], r["a"], r["b"], side)))
        response = self.ledger.artifacts.put(asdict(ProviderResponse(replies, "codex-current-conversation", None, raw_response=raw)))
        identifier = self.ledger.record(session, "representation_references", METHOD,
            {"plan": plan["_record_id"], "replies": replies, "response": response, "human_validated": False})
        self.complete(session, handoff, response, identifier, "valid")
        return {"id": identifier, "pairs": 60, "labels": dict(Counter(r["label"] for r in replies)), "human_validated": False}

    def run_pairs(self, session, plan, data):
        self.one("representation_references")
        split = data["split"]
        self.absent("representation_launch", split)
        if not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("comparison_explicit_execution_and_saved_key_required")
        if self.ledger.unresolved:
            raise AuditError("comparison_unresolved_attempt_no_retry")
        if split == "test":
            self.one("representation_calibration")
        manifest = [t for t in self.ledger.artifacts.read(plan["manifest"]) if t["split"] == split]
        self.ledger.record(session, "representation_launch", split, {"plan": plan["_record_id"], "split": split, "started_at": utc(), "requests": len(manifest)})
        total = sum(v["cost_nanousd"] or 0 for v in self.rows("representation_decision"))
        for number, task in enumerate(manifest, 1):
            if datetime.now(timezone.utc) >= datetime.fromisoformat(plan["expires_at"]) or (self.ledger.root / "STOP").exists():
                break
            if total + plan["reservation_nanousd"] > plan["maximum_cost_nanousd"]:
                break
            attempt, key = str(uuid.uuid4()), digest([task["pair_id"], task["arm"]])
            invocation = transport.Invocation(self.ledger.artifacts.read(task["request"]), attempt)
            intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": plan["_record_id"],
                "request": task["request"], "dispatch": self.ledger.artifacts.put(invocation.manifest()),
                "started_at": utc(), "reserved_nanousd": plan["reservation_nanousd"]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            started = time.perf_counter()
            response = next(self.gateway.codex_dispatch(session, transport.DecisionsTransport(), [(invocation, attempt)], 1))[1]
            elapsed = time.perf_counter() - started
            response_ref = self.ledger.artifacts.put(asdict(response))
            self.ledger.append(session, "representation.response.received", {"attempt": attempt, "response": response_ref, "seconds": elapsed})
            tokens = (response.usage or {}).get("input_tokens")
            valid_usage = type(tokens) is int and 0 <= tokens <= 1_050_000
            cost = tokens * transport.RATE_NANOUSD_PER_TOKEN * (2 if tokens > 272000 else 1) if valid_usage else None
            raw, decision, failure = response.raw_response or {}, None, None
            if response.payload is not None:
                try:
                    decision = transport.parse_decision(response.payload)
                except (KeyError, TypeError, ValueError, ResearchError, RuntimeError) as error:
                    failure = type(error).__name__
            hold = bool(raw.get("unknown_outcome")) or cost is None or cost > plan["reservation_nanousd"] or response.model != "gpt-6-luna"
            result = self.ledger.record(session, "representation_decision", key, {
                **task, "attempt": attempt, "response": response_ref, "decision": decision,
                "input_tokens": tokens if valid_usage else None, "cost_nanousd": cost,
                "reserved_nanousd": plan["reservation_nanousd"] if hold else 0,
                "unknown_or_billing_hold": hold, "http_status": raw.get("http_status"),
                "validation_error": failure, "seconds": elapsed})
            if not hold:
                self.complete(session, intended, response_ref, result, "valid" if decision else "invalid")
                total += cost
            print(json.dumps({"split": split, "completed": number, "planned": len(manifest), "cost_usd_with_margin": total / 1e9, "hold": hold}), flush=True)
            if hold or failure or raw.get("http_status") != 200 or not decision or decision["status"] != "valid":
                break
        return {"split": split, "stored_responses": len(self.rows("representation_decision")),
            "unresolved_attempts": len(self.ledger.unresolved), "cost_usd_with_margin": total / 1e9}

    def scored(self, split, require_complete=True):
        references = {(r["panel"], r["a"], r["b"]): r["label"] for r in self.one("representation_references")["replies"]}
        records = [v for v in self.rows("representation_decision") if v["split"] == split]
        expected = 72 if split == "development" else 108
        if require_complete and (len(records) != expected or any(v["unknown_or_billing_hold"] or not v["decision"] or v["decision"]["status"] != "valid" for v in records)):
            raise AuditError("comparison_complete_valid_split_required")
        return [{**r, "reference": references[(r["panel"], r["a"], r["b"])]} for r in records]

    def calibrate(self, session, plan):
        self.absent("representation_calibration")
        self.absent("representation_launch", "test")
        rows = self.scored("development")
        result = {"plan": plan["_record_id"], "split": "development", "thresholds": {
            arm: core.calibrate([r for r in rows if r["arm"] == arm]) for arm in core.ARMS}}
        identifier = self.ledger.record(session, "representation_calibration", METHOD, result)
        return {"id": identifier, "selected": {a: v["selected"] for a, v in result["thresholds"].items()}}

    def report(self, session, plan):
        calibration = self.one("representation_calibration")
        result = {"plan": plan["_record_id"], "calibration": calibration["_record_id"], "splits": {},
            "human_validated": False, "extraction_cost_usd": None, "new_extractions": 0}
        all_rows = []
        for split in ("development", "test"):
            rows = self.scored(split)
            all_rows.extend(rows)
            arms = {}
            for arm in core.ARMS:
                subset = [r for r in rows if r["arm"] == arm]
                arms[arm] = {"raw": core.measure(subset, None), "fixed_95": core.measure(subset, .95),
                    "calibrated": core.measure(subset, calibration["thresholds"][arm]["selected"]["threshold"]),
                    "input_tokens": sum(r["input_tokens"] for r in subset),
                    "cost_usd_with_margin": sum(r["cost_nanousd"] for r in subset) / 1e9,
                    "request_seconds": sum(r["seconds"] for r in subset)}
            baseline = {r["pair_id"]: r for r in rows if r["arm"] == "article"}
            paired = {}
            for arm in ("luna", "luna_passages"):
                paired[arm] = dict(Counter(
                    ("both_agree" if good else "both_disagree") if good == base_good else
                    ("only_extraction_arm_agrees" if good else "only_article_arm_agrees")
                    for r in rows if r["arm"] == arm
                    for good, base_good in [(r["decision"]["label"] == r["reference"],
                        baseline[r["pair_id"]]["decision"]["label"] == r["reference"])]))
            result["splits"][split] = {"references": dict(Counter(r["reference"] for r in rows if r["arm"] == "article")),
                "arms": arms, "paired_raw_label_agreement": paired}
        result["cost_usd_with_margin"] = sum(r["cost_nanousd"] for r in all_rows) / 1e9
        result["cost_usd_base_rate"] = sum(r["input_tokens"] * 100 * (2 if r["input_tokens"] > 272000 else 1) for r in all_rows) / 1e9
        result["total_matching_cost_usd_with_margin"] = result["cost_usd_with_margin"] + plan["prior_cost_nanousd"] / 1e9
        result["remaining_matching_budget_usd"] = 20 - result["total_matching_cost_usd_with_margin"]
        totals = {arm: sum(r["cost_nanousd"] for r in all_rows if r["arm"] == arm) / 1e9 for arm in core.ARMS}
        result["arm_costs_usd_with_margin"] = totals
        result["extraction_break_even_usd_for_40_articles"] = {a: totals["article"] - totals[a] for a in ("luna", "luna_passages")}
        result["completed_api_requests"] = len(all_rows)
        result["unresolved_attempts"] = len(self.ledger.unresolved)
        result["disagreements"] = [{k: r[k] for k in ("panel", "a", "b", "arm", "reference", "decision")} for r in all_rows if r["decision"]["label"] != r["reference"]]
        identifier = self.ledger.record(session, "representation_report", digest(result), result)
        path = self.ledger.root / "comparison-report.json"
        path.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(path), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "dispatch", "read", "submit", "run", "calibrate", "report"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--split", choices=["development", "test"], default="development")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=10)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    engine = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {**vars(args), "base": str(args.base), "workspace": str(args.workspace), "input": str(args.input) if args.input else None}
        print(json.dumps(engine.execute("status", data, objective="Compare full articles, saved Luna outputs and supported Luna outputs on identical fresh pairs", actor="codex:luna-representation-comparison")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
