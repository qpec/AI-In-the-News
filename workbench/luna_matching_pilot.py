"""Audited, bounded Luna-output matching pilot; never restarts extraction."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch import luna_decisions_matching as matching
from newsresearch import luna_output_matching as legacy
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_state as state  # noqa: E402
from check_luna_standard_integrity import inspect_assessment  # noqa: E402

METHOD = "luna-decisions-matching-pilot-20261020-v1"
STANDARD = "luna-standard-full-corpus-20261018-v2"
FINISH = "luna-standard-finish-20261020-v3"
SAMPLE = "provider-event-label-check-20261019-v1"
PREPARATION = "luna-output-pair-method-20261019-v1"
SEED = "luna-matching-pilot-20261020-v1-fixed"
PAIR_CAP = 200
BUDGET_NANOUSD = 1_000_000_000


def implementation():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__), Path(matching.__file__), Path(legacy.__file__))}


def prior_record(owner, kind):
    check_permissions(owner, root=True)
    conn = state.read_only_database(owner)
    try:
        rows = list(conn.execute("SELECT * FROM records WHERE kind=?", (kind,)))
        if len(rows) != 1:
            raise AuditError("pilot_parent_record_not_unique")
        value = state.row_value(rows[0], kind)
        state.SelectedArtifacts(owner).check(rows[0]["artifact"])
        return value
    finally:
        conn.close()


def shape(value, depth=2):
    if isinstance(value, dict) and depth:
        return {k: shape(v, depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        return [shape(value[0], depth - 1)] if value and depth else "list"
    return type(value).__name__


class Pilot(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "prepare":
            return self.prepare(session, context, data)
        if data["action"] in {"run", "report"}:
            row = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_matching_pilot_plan'").fetchall()
            if len(row) != 1:
                raise AuditError("pilot_requires_one_frozen_plan")
            plan = self.ledger.get(row[0][0], "luna_matching_pilot_plan")
            if data["action"] == "report":
                return self.report(session, row[0][0], plan)
            return self.run_pairs(session, row[0][0], plan, data)
        if data["action"] != "inventory":
            raise ValueError("unsupported_pilot_action")
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD + "-inventory",
            "content": {"method": METHOD + "-inventory", "user_request": "Pilot to see if it works. Go",
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "scope": "Read schema, counts and payload shapes from named Luna owners and the earlier 50-pair audit. No semantic inference, raw article output, model calls, retries or writes to parents. Selected journal records are hash checked; full parent history is not replayed."}})["id"]
        result = {"protocol": protocol, "owners": {}, "new_model_calls": 0}
        for name in (STANDARD, FINISH, SAMPLE, PREPARATION):
            owner = Path(data["base"]) / name
            check_permissions(owner, root=True)
            conn = state.read_only_database(owner)
            try:
                head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
                kinds = dict(conn.execute("SELECT kind,count(*) FROM records GROUP BY kind"))
                relevant = {k: n for k, n in kinds.items() if any(s in k for s in ("assessment", "matching", "provider_label", "result_bundle"))}
                samples = {}
                for kind in relevant:
                    row = conn.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (kind,)).fetchone()
                    samples[kind] = shape(state.row_value(row))
                result["owners"][name] = {"head": head, "kinds": relevant, "shapes": samples}
            finally:
                conn.close()
            if name == FINISH:
                db = sqlite3.connect((owner / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
                try:
                    db.execute("PRAGMA query_only=ON")
                    db.execute("BEGIN")
                    row = db.execute("SELECT payload FROM results ORDER BY custom_id LIMIT 1").fetchone()
                    req = db.execute("SELECT payload FROM requests ORDER BY custom_id LIMIT 1").fetchone()
                    result["owners"][name]["operational"] = {"result_shape": shape(json.loads(row[0]), 4),
                        "request_shape": shape(json.loads(req[0]), 4),
                        "result_counts": dict(db.execute("SELECT status,count(*) FROM results GROUP BY status"))}
                finally:
                    db.close()
        identifier = self.ledger.record(session, "luna_matching_pilot_inventory", digest(result), result)
        return {"id": identifier, **result}

    def prepare(self, session, context, data):
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_matching_pilot_plan'").fetchone():
            raise AuditError("pilot_selection_already_frozen")
        definitions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "user_request": "Pilot to see if it works. Go",
                "scope": "Bounded exploratory feasibility pilot: frozen prior 100 article cards plus up to 500 available single-event cards per corpus from the sealed Standard owner. Local lexical retrieval, deterministic baseline and <=200 serial Decisions requests. No extraction, embeddings, collection, controller actions or accepted findings.",
                "limits": "Prior pair reviews are model references, partially read and previously used in development, not independent human gold. No population accuracy, calibrated thresholds or complete clustering claim. Saved original cards inherit their prior mechanical verification. Newly sampled Standard records are mechanically replayed. Full parent history is not replayed. This pilot excludes newer API/Batch owners; coverage is not current full-corpus coverage."},
            "question": {"text": "Does bounded local retrieval recover available earlier matches, and do Decisions pair labels agree with prior model references at low measured cost?"},
            "selection": {"rules": "Fixed seed. Include all frozen original cards. Select up to 500 valid single-event article identities per corpus by stable hash, excluding original body hashes. Preserve every Standard variant of a selected identity. No replacement of newly rejected cards. Judge all ready old reference pairs plus rank-stratified candidates, rank-21-50 neighbors and random ready pairs up to 200. Reference pairs may lie outside retrieved candidates and are counted separately.", "seed": SEED, "base": data["base"]},
            "dossier_definition": {"unit": "One specific focal real-world occurrence. Related distinct actions are different events. Unclear boundaries abstain."},
            "codebook": {"labels": list(matching.LABELS)},
            "prompt": {"instructions": matching.RULES},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
            "policy": {"scope": "User-authorized bounded pilot only", "max_requests": PAIR_CAP,
                "maximum_cost_nanousd": BUDGET_NANOUSD, "serial_full_context_reservation_nanousd": matching.RESERVATION_NANOUSD,
                "reservation_basis": "1.05M context x $0.10/M x2 long-context x1.1 regional=$0.231, rounded up to $0.25 per in-flight request; unknown outcomes keep holds and stop. One choice question, <=64k UTF-8 bytes, no tools or output charge.",
                "price_sources": ["https://developers.openai.com/api/docs/guides/decisions", "https://developers.openai.com/api/docs/models/gpt-6-luna"],
                "price_checked_date": "2026-10-20", "automatic_retries": 0},
        }
        versions = {kind: self._version(session, context, {"kind": kind, "key": METHOD,
                    "content": content})["id"] for kind, content in definitions.items()}
        self.ledger.append(session, "luna.matching.pilot.inspection.intended", {"versions": versions, "read_only_parents": True})
        base = Path(data["base"])
        prepared = prior_record(base / PREPARATION, "luna_output_matching_preparation")
        prior_artifacts = state.SelectedArtifacts(base / PREPARATION)
        cards = prior_artifacts.json(prepared["cards"])
        prior_pairs = {p["pair_id"]: p for p in prior_artifacts.json(prepared["manifest"])}
        mappings = prior_artifacts.json(prepared["original_pair_mapping"])
        excluded_bodies = {(c["corpus"], c["body_sha256"]) for c in cards}
        owner = base / STANDARD
        check_permissions(owner, root=True)
        conn = state.read_only_database(owner)
        artifacts = state.SelectedArtifacts(owner)
        grouped = defaultdict(list)
        try:
            head = dict(conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
            # Snapshot payloads are hash/identity checked before any selection.
            for row in conn.execute("SELECT * FROM records WHERE kind='luna_standard_assessment' ORDER BY id"):
                value = state.row_value(row, "luna_standard_assessment")
                body = value["descriptor"]["retained_body_sha256"]
                if (value["corpus_id"], body) not in excluded_bodies:
                    grouped[(value["corpus_id"], value["custom_id"], body)].append(value)
            eligible = defaultdict(list)
            for identity, variants in grouped.items():
                if any(v["derived_status"] == "valid" and (v["projection"].get("derived_output") or {}).get("focus") == "single" for v in variants):
                    eligible[identity[0]].append(identity)
            selected = [i for corpus in sorted(eligible) for i in sorted(eligible[corpus], key=lambda i: digest([SEED, i]))[:500]]
            provenance = []
            for identity in selected:
                variants = []
                for value in grouped[identity]:
                    inspect_assessment(value, artifacts)
                    raw = artifacts.json(value["response"])["payload"]
                    variants.append({"assessment": value["_record_id"], "raw_status": value["status"],
                        "derived_status": value["derived_status"], "raw_output": raw,
                        "output": value["projection"]["derived_output"]})
                    provenance.append({"assessment": value["_record_id"], "source_owner": str(owner),
                        "request": value["request"], "response": value["response"], "identity": list(identity)})
                cards.append(legacy.make_card(article_id=digest([METHOD, identity]), corpus=identity[0],
                    body_sha256=identity[2], published_at=None, variants=variants))
        finally:
            conn.close()
        by_id = {c["article_id"]: c for c in cards}
        groups = {str(p["original_pair"]): [prior_pairs[p["pair_id"]][side] for side in ("left", "right")] for p in mappings}
        retrieved = matching.retrieve(cards, provider_groups=groups)
        sample_owner = base / SAMPLE
        check_permissions(sample_owner, root=True)
        conn = state.read_only_database(sample_owner)
        try:
            references = {}
            for row in conn.execute("SELECT * FROM records WHERE kind='provider_label_judgment'"):
                value = state.row_value(row, "provider_label_judgment")
                state.SelectedArtifacts(sample_owner).check(row["artifact"])
                references[value["reply"]["pair"]] = {"record": value["_record_id"], "label": value["reply"]["label"]}
        finally:
            conn.close()
        tasks, original = {}, []
        retrieval_sets = {k: {p["pair_id"] for p in rows} for k, rows in retrieved["pairs"].items()}
        for mapping in mappings:
            left, right = [by_id[i] for i in groups[str(mapping["original_pair"])]]
            ready = left["readiness"] == right["readiness"] == "ready"
            item = {"original_pair": mapping["original_pair"], "eligible": ready,
                "reference": references.get(mapping["original_pair"]), "input_states": [left["readiness"], right["readiness"]]}
            if ready:
                key = matching.pair_key(left, right)
                item.update(pair_id=key, retrieved={k: key in ids for k, ids in retrieval_sets.items()})
                tasks[key] = {"pair_id": key, "left": left["article_id"], "right": right["article_id"],
                    "corpus": left["corpus"], "stratum": "prior_reference"}
            original.append(item)
        buckets = defaultdict(list)
        for row in retrieved["pairs"]["50"]:
            left, right = row["left"], row["right"]
            positions = []
            for anchor, other in ((left, right), (right, left)):
                ordered = retrieved["ranks"][anchor]["ranked"]
                if other in ordered:
                    positions.append(ordered.index(other) + 1)
            rank = min(positions)
            stratum = "rank_1_3" if rank <= 3 else "rank_4_20" if rank <= 20 else "rank_21_50"
            buckets[stratum].append({**row, "stratum": stratum})
        for stratum, quota in (("rank_1_3", 70), ("rank_4_20", 40), ("rank_21_50", 20)):
            available = [p for p in sorted(buckets[stratum], key=lambda p: digest([SEED, stratum, p["pair_id"]])) if p["pair_id"] not in tasks]
            for row in available[:quota]:
                tasks[row["pair_id"]] = row
        # Bounded deterministic pseudo-random pairs; never construct N-squared.
        ready_ids = sorted(i for i, c in by_id.items() if c["readiness"] == "ready")
        for trial in range(10000):
            if len(tasks) >= PAIR_CAP or len(ready_ids) < 2:
                break
            left = by_id[ready_ids[int(digest([SEED, trial, 0]), 16) % len(ready_ids)]]
            right = by_id[ready_ids[int(digest([SEED, trial, 1]), 16) % len(ready_ids)]]
            if left["article_id"] == right["article_id"] or left["corpus"] != right["corpus"]:
                continue
            key = matching.pair_key(left, right)
            tasks.setdefault(key, {"pair_id": key, "left": left["article_id"], "right": right["article_id"],
                "corpus": left["corpus"], "stratum": "random_ready"})
        manifest = []
        for key, task in tasks.items():
            left, right = by_id[task["left"]], by_id[task["right"]]
            wire = matching.make_request(left, right)
            manifest.append({**task, "request": self.ledger.artifacts.put(wire),
                "wire_bytes": len(state.canonical(wire).encode()), "rules_label": matching.classify_rules(left, right)})
        if len(manifest) > PAIR_CAP:
            raise AuditError("pilot_pair_cap_exceeded")
        plan = {"method": METHOD, "versions": versions, "implementation": implementation(), "created_at": utc(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
            "cards": self.ledger.artifacts.put(cards), "manifest": self.ledger.artifacts.put(manifest),
            "retrieval": self.ledger.artifacts.put(retrieved), "original_references": original,
            "selected_provenance": self.ledger.artifacts.put(provenance), "standard_snapshot": head,
            "counts": {"cards": len(cards), "ready": retrieved["eligible"], "readiness": retrieved["readiness"],
                "candidate_pairs": {k: len(v) for k, v in retrieved["pairs"].items()},
                "retrieval_seconds": retrieved["elapsed_seconds"], "planned_requests": len(manifest),
                "strata": dict(Counter(t["stratum"] for t in manifest)),
                "ready_original_pairs": sum(p["eligible"] for p in original)},
            "maximum_requests": PAIR_CAP, "maximum_cost_nanousd": BUDGET_NANOUSD,
            "reservation_nanousd": matching.RESERVATION_NANOUSD, "human_validated": False,
            "study_type": "exploratory_feasibility_against_prior_model_references", "clustering_executed": False}
        identifier = self.ledger.record(session, "luna_matching_pilot_plan", METHOD, plan)
        return {"plan": identifier, "counts": plan["counts"], "new_model_calls": 0, "ready_to_run": True}

    def run_pairs(self, session, plan_id, plan, data):
        if not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("pilot_explicit_execution_flag_and_saved_key_required")
        if plan["implementation"] != implementation():
            raise AuditError("pilot_implementation_changed_after_freeze")
        if self.ledger.unresolved:
            raise AuditError("pilot_prior_unknown_attempt_no_retry")
        if self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_matching_pilot_launch'").fetchone():
            raise AuditError("pilot_already_launched_no_automatic_resume")
        manifest = self.ledger.artifacts.read(plan["manifest"])
        self.ledger.record(session, "luna_matching_pilot_launch", plan_id,
            {"plan": plan_id, "started_at": utc(), "requests": len(manifest), "max_cost_nanousd": BUDGET_NANOUSD})
        total = 0
        for task in manifest:
            if datetime.now(timezone.utc) >= datetime.fromisoformat(plan["expires_at"]):
                break
            if total + plan["reservation_nanousd"] > plan["maximum_cost_nanousd"] or (self.ledger.root / "STOP").exists():
                break
            request = self.ledger.artifacts.read(task["request"])
            attempt = str(uuid.uuid4())
            invocation = matching.Invocation(request, attempt)
            intended = {"attempt": attempt, "task_key": task["pair_id"], "number": 1, "batch": plan_id,
                "request": task["request"], "dispatch": self.ledger.artifacts.put(invocation.manifest()),
                "started_at": utc(), "reserved_nanousd": plan["reservation_nanousd"]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            response = next(self.gateway.codex_dispatch(session, matching.DecisionsTransport(), [(invocation, attempt)], 1))[1]
            response_ref = self.ledger.artifacts.put(asdict(response))
            self.ledger.append(session, "luna.matching.response.received", {"attempt": attempt, "response": response_ref})
            usage = response.usage or {}
            tokens = usage.get("input_tokens")
            valid_usage = type(tokens) is int and 0 <= tokens <= 1_050_000
            cost = tokens * matching.RATE_NANOUSD_PER_TOKEN * (2 if tokens > 272000 else 1) if valid_usage else None
            decision, failure = None, None
            if response.payload is not None:
                try:
                    decision = matching.parse_decision(response.payload)
                except (KeyError, TypeError, ValueError, AuditError, RuntimeError) as error:
                    failure = type(error).__name__
            raw = response.raw_response or {}
            hold = (bool(raw.get("unknown_outcome")) or cost is None or cost > plan["reservation_nanousd"]
                    or response.model != "gpt-6-luna")
            value = {"plan": plan_id, "pair_id": task["pair_id"], "attempt": attempt, "response": response_ref,
                "decision": decision, "validation_error_type": failure, "input_tokens": tokens if valid_usage else None,
                "cost_nanousd_with_regional_margin": cost, "reserved_nanousd": plan["reservation_nanousd"] if hold else 0,
                "http_status": raw.get("http_status"), "unknown_or_billing_hold": hold, "human_validated": False}
            result = self.ledger.record(session, "luna_matching_pilot_decision", task["pair_id"], value)
            if not hold:
                status = "valid" if decision else "invalid"
                def project(event):
                    self.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                        attempt, task["pair_id"], plan_id, 1, task["request"], response_ref, status, result, None, event))
                self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "status": status,
                    "assessment": result, "response": response_ref, "ended_at": utc()}, project)
                self.ledger.unresolved.pop(attempt)
                total += cost
            if hold or failure or raw.get("http_status") != 200:
                break
        return self.report(session, plan_id, plan)

    def report(self, session, plan_id, plan):
        values = [self.ledger.get(row[0], "luna_matching_pilot_decision") for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='luna_matching_pilot_decision' ORDER BY created_event")]
        by_pair = {v["pair_id"]: v for v in values}
        agreement, comparisons = Counter(), []
        for ref in plan["original_references"]:
            value = by_pair.get(ref.get("pair_id"))
            if not value or not value["decision"] or not ref["reference"]:
                continue
            expected = ref["reference"]["label"]
            expected = "insufficient_evidence" if expected == "uncertain" else expected
            observed = value["decision"]["label"]
            if observed is not None:
                agreement["compared"] += 1
                agreement["agreed"] += int(observed == expected)
            comparisons.append({"original_pair": ref["original_pair"], "reference": expected,
                "observed": observed, "probabilities": value["decision"]["probabilities"]})
        positive_refs = [r for r in plan["original_references"] if r["eligible"] and r["reference"] and r["reference"]["label"] == "same_event"]
        recovery = {k: {"recovered": sum(r["retrieved"][k] for r in positive_refs), "eligible_positive_references": len(positive_refs)} for k in ("10", "20", "50")}
        result = {"plan": plan_id, "counts": plan["counts"], "completed_requests": len(values),
            "valid_decisions": sum(bool(v["decision"] and v["decision"]["status"] == "valid") for v in values),
            "labels": dict(Counter(v["decision"]["label"] for v in values if v["decision"] and v["decision"]["label"])),
            "settled_cost_usd_with_regional_margin": sum(v["cost_nanousd_with_regional_margin"] or 0 for v in values) / 1e9,
            "held_usd": sum(v["reserved_nanousd"] for v in values) / 1e9,
            "reported_input_tokens": sum(v["input_tokens"] or 0 for v in values),
            "responses_without_usage": sum(v["input_tokens"] is None for v in values),
            "reference_agreement": dict(agreement), "reference_comparisons": comparisons,
            "retrieval_recovery": recovery, "unresolved_attempts": len(self.ledger.unresolved),
            "human_validated": False, "independent_accuracy_test": False,
            "scope": "Frozen prior sample and sealed Standard background only; newer API/Batch work excluded. Prior model labels are development references. No production clustering or calibrated threshold."}
        identifier = self.ledger.record(session, "luna_matching_pilot_report", digest(result), result)
        report = self.ledger.root / "pilot-report.json"
        report.write_text(json.dumps({"id": identifier, **result}, indent=2), encoding="utf-8")
        return {"id": identifier, "report": str(report), **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inventory", "prepare", "run", "report"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=Path.home() / "AppData/Local/AI-In-the-News")
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    engine = Pilot(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(engine.execute("status", {"action": args.action, "base": str(args.base),
            "allow_paid_execution": args.allow_paid_execution},
            objective="Run the user-authorized bounded pilot of Luna-output event matching",
            actor="codex:luna-matching-pilot")))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
