"""Registered, one-launch Decisions screen of 1,000 frozen original articles."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
import uuid

from newsresearch import luna_decisions_matching as transport
from newsresearch import luna_incident_screening as core
from newsresearch.common import AuditError, Config, ResearchError, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import lean_luna_batch as materializer  # noqa: E402
import lean_luna_state as state  # noqa: E402
import luna_event_contract_v2 as contract  # noqa: E402

BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
STANDARD = "luna-standard-full-corpus-20261018-v2"
PILOT = "luna-matching-pilot-20261020-v1"
COMPARISON = "luna-representation-comparison-20261020-v1"
METHOD = core.METHOD + "-source-plan-v2"
TOTAL_BUDGET = 20_000_000_000
STUDY_BUDGET = 2_000_000_000
AUTHORIZATION_TEXT = "Lets log this method and run it on a small pilot of 1000"


def implementation():
    paths = [Path(__file__), Path(core.__file__), Path(transport.__file__),
             Path(state.__file__), Path(materializer.__file__), Path(contract.__file__),
             ROOT / "scripts/luna_batch_materialize.py", ROOT / "scripts/luna_multibatch.py",
             ROOT / "scripts/prepare_luna_multibatch.py", ROOT / "scripts/structured_article_input.py",
             ROOT / "prompts/luna_event_v2.txt", ROOT / "schemas/luna_event_v2.json", ROOT / "uv.lock",
             ROOT / "src/newsresearch/runtime.py", ROOT / "src/newsresearch/gateway.py",
             ROOT / "src/newsresearch/storage.py", ROOT / "src/newsresearch/common.py"]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


class Source:
    """Verified selected reads, used only inside the new research operation."""
    def __init__(self, owner):
        self.owner = Path(owner).resolve(strict=True)
        check_permissions(self.owner, root=True)
        self.artifacts = state.SelectedArtifacts(self.owner)
        self.db = state.read_only_database(self.owner)

    def rows(self, kind):
        result = []
        for row in self.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", (kind,)):
            self.artifacts.check(row["artifact"])
            result.append(state.row_value(row, kind))
        return result

    def one(self, kind):
        rows = self.rows(kind)
        if kind == "luna_standard_plan" and rows:
            # Execution settings were amended five times, but input queues and
            # archive partitions stayed identical. Choose the earliest plan
            # only when every retained plan binds the exact same source frame.
            bindings = {digest({"queues": r["queues"], "partitions": {
                k: v["partition"] for k, v in r["corpora"].items()}}) for r in rows}
            if len(bindings) != 1:
                raise AuditError("screen_parent_source_frames_disagree")
            return rows[0]
        if len(rows) != 1:
            raise AuditError("screen_parent_one_record_required_" + kind)
        return rows[0]

    def head(self):
        return list(self.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())

    def close(self):
        self.db.close()


def prior_budget(base):
    result, total = {}, 0
    for name, kind, cost_key in ((PILOT, "luna_matching_pilot_decision", "cost_nanousd_with_regional_margin"),
                                (COMPARISON, "representation_decision", "cost_nanousd")):
        source = Source(base / name)
        try:
            rows = source.rows(kind)
            intended, completed = set(), set()
            for event in source.db.execute("SELECT kind,payload FROM events WHERE kind IN ('model.attempt.intended','model.attempt.completed')"):
                (intended if event[0] == "model.attempt.intended" else completed).add(json.loads(event[1])["attempt"])
            if (not rows or intended - completed or any(r["unknown_or_billing_hold"] or r["reserved_nanousd"]
                    or type(r.get(cost_key)) is not int or r[cost_key] < 0 for r in rows)):
                raise AuditError("screen_previous_budget_has_unsettled_attempts")
            subtotal = sum(r[cost_key] for r in rows)
            total += subtotal
            result[name] = {"records": [r["_record_id"] for r in rows], "cost_nanousd": subtotal}
        finally:
            source.close()
    return {"owners": result, "cost_nanousd": total}


class Study(Research):
    def rows(self, kind):
        return [{**self.ledger.get(r[0], kind), "_record_id": r[0]} for r in
                self.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]

    def one(self, kind):
        rows = self.rows(kind)
        if len(rows) != 1:
            raise AuditError("screen_one_record_required_" + kind)
        return rows[0]

    def absent(self, kind):
        if self.rows(kind):
            raise AuditError("screen_already_started_no_retry_" + kind)

    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "prepare":
            return self.prepare(session, context, data)
        plan = self.one("incident_screen_plan")
        if plan["implementation"] != implementation():
            raise AuditError("screen_implementation_changed_after_freeze")
        if data["action"] == "run":
            return self.run_screen(session, plan, data)
        if data["action"] == "report":
            return self.report(session, plan)
        raise AuditError("screen_unknown_action")

    def prepare(self, session, context, data):
        self.absent("incident_screen_preparation")
        count = data["count"]
        if type(count) is not int or not 1 <= count <= 1000:
            raise AuditError("screen_sample_count_out_of_bounds")
        versions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "amendment": "V1 preparation stopped before selection or API dispatch because it required one Standard plan. Metadata-only diagnosis found five historical execution plans with identical queue and partition bindings. V2 explicitly checks equality and uses the earliest verified plan. Same screening prompt, seed, sample size and budget. Preserve the failed V1 owner; no model call is retried.",
                "procedure": "One serial Decisions call per full original article, two independent questions. Log all labels, probabilities and exact input/response artifacts. No previous extraction is a model input or selection criterion. No collection, controller restart, grouping or acceptance.",
                "scope": "One focal event AND actual/alleged AI-related harm. A prevented attempt without harm is excluded. Attributed allegations are reporting, not verified facts. Distinct later lawsuits/rulings remain distinct events. This restriction is a new study branch; earlier all-event methods are unchanged.",
                "limitations": "Unvalidated exploratory screening; no human reference labels, accuracy, recall, precision or population estimate. Retained article completeness is not publisher-page completeness. Earlier eligibility and protected-held-out exclusions limit the frame.",
                "source_validation": "Read selected prior projections/artifacts and freeze owner head; this is not full replay of historical owners. Verify chosen archive bundle bytes before and after exact-row materialization and packet/body identity. No source truncation or sample replacement."},
            "question": {"text": "What provisional single-event and AI-incident labels, uncertainty, coverage, time and cost result from screening 1000 original articles directly with Luna Decisions?"},
            "selection": {"rules": "Rank every entry of both frozen Standard eligible queues by SHA256 canonical [seed,corpus,custom_id,source_sha256]; select first count without replacement. Independent of all previous model outputs. Preserve corpora and selected unavailable/oversized items, with no replacement.",
                          "seed": core.SEED, "count": count, "source_owner": STANDARD},
            "dossier_definition": {"unit": "One specific focal real-world occurrence. Screening does not assign dossier membership or establish incident truth."},
            "codebook": {"labels": sorted(set(v for values in core.LABELS.values() for v in values)),
                         "questions": core.QUESTIONS,
                         "routing": "keep iff single_event and yes; exclude iff multiple_events/no_event or no; otherwise review. Refusal always review. Unprocessed is missing, not negative."},
            "prompt": {"instructions": core.GENERAL, "questions": core.QUESTIONS,
                       "input": "Exact full original title and body only; no metadata or extractions."},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False,
                        "probability_cutoff": None, "diagnostics_only_cutoffs": [.8, .95]},
            "policy": {"scope": AUTHORIZATION_TEXT, "approved_by": "user:current-chat",
                       "maximum_requests": count, "maximum_new_cost_nanousd": STUDY_BUDGET,
                       "total_existing_budget_nanousd": TOTAL_BUDGET, "serial_reservation_nanousd": transport.RESERVATION_NANOUSD,
                       "retries": 0, "maximum_launches": 1, "deadline_hours_after_preparation": 4,
                       "maximum_wire_bytes": transport.MAX_WIRE_BYTES, "price_checked": "2026-10-20",
                       "price_sources": ["https://developers.openai.com/api/docs/guides/decisions"],
                       "rate_nanousd_per_input_token": transport.RATE_NANOUSD_PER_TOKEN,
                       "long_context_threshold_tokens": 272000, "long_context_multiplier": 2},
        }
        bound = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"]
                 for k, v in versions.items()}
        self.ledger.record(session, "incident_screen_preparation", METHOD, {"versions": bound, "started_at": utc()})
        base = Path(data["base"]).resolve()
        prior = prior_budget(base)
        if prior["cost_nanousd"] + STUDY_BUDGET > TOTAL_BUDGET:
            raise AuditError("screen_budget_exceeds_remaining_authorization")
        source = Source(base / STANDARD)
        try:
            if not (source.owner / "STOP").is_file():
                raise AuditError("screen_standard_source_must_remain_stopped")
            parent = source.one("luna_standard_plan")
            queues = {corpus: source.artifacts.json(ref) for corpus, ref in parent["queues"].items()}
            selected = core.select_sample(queues, count)
            provenance = {"owner": str(source.owner), "head": source.head(), "plan": parent["_record_id"],
                          "queue_artifacts": parent["queues"], "selected_artifacts_verified": sorted(source.artifacts.checked)}
        finally:
            source.close()
        selection = {"versions": bound, "provenance": provenance,
                     "frame_counts": {k: len(v) for k, v in queues.items()}, "selected": selected}
        selection_id = self.ledger.record(session, "incident_screen_selection", METHOD, selection)
        snapshot = materializer.core.load_contract_snapshot()
        helper = SimpleNamespace(require_runtime=lambda: require_active(self, session), snapshot=snapshot)
        tasks, archive_checks = {}, []
        for corpus in sorted(queues):
            chosen = [d for d in selected if d["corpus_id"] == corpus]
            if not chosen:
                continue
            partition = parent["corpora"][corpus]["partition"]
            root = Path(partition["resolved_root"]).resolve()
            expected = {}
            for d in chosen:
                loc = d["source_locator"]
                if loc["archive_path"] in expected and expected[loc["archive_path"]] != loc["archive_sha256"]:
                    raise AuditError("screen_archive_binding_conflict")
                expected[loc["archive_path"]] = loc["archive_sha256"]

            def check_archives():
                for relative, sha in sorted(expected.items()):
                    path = (root / relative).resolve(strict=True)
                    if not path.is_relative_to(root):
                        raise AuditError("screen_archive_path_escape")
                    with path.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                            raise AuditError("screen_archive_hash_mismatch")

            self.ledger.append(session, "incident_screen.source_read.intended", {
                "selection": selection_id, "corpus": corpus, "bundles": expected, "count": len(chosen)})
            check_archives()
            records = materializer.LeanBatch.materialize(helper, chosen, partition)
            check_archives()
            archive_checks.append({"corpus": corpus, "archives": expected, "before_and_after": True})
            for record in records:
                descriptor = record["descriptor"]
                packet = materializer.packet_from_prompt(record["request"]["body"], descriptor, snapshot)
                title = packet["model_input"]["evidence"]["title"]["text"]
                body = packet["source_map"]["source_fields"]["body"]["text"]
                if hashlib.sha256(body.encode("utf-8")).hexdigest() != descriptor["retained_body_sha256"]:
                    raise AuditError("screen_complete_body_hash_mismatch")
                task = {"custom_id": descriptor["custom_id"], "corpus": corpus, "descriptor": descriptor,
                        "source": None, "request": None, "disposition": "ready"}
                try:
                    request = core.request(title, body)
                except ResearchError as error:
                    reason = str(error)
                    if reason not in {"screen_body_unavailable", "screen_request_exceeds_byte_cap",
                                      "Credential-like content is forbidden in persistent research payloads"}:
                        raise
                    task["disposition"] = "credential_like_content" if reason.startswith("Credential") else reason
                else:
                    task["source"] = self.ledger.artifacts.put({"descriptor": descriptor, "packet": packet})
                    task["request"] = self.ledger.artifacts.put(request)
                tasks[descriptor["custom_id"]] = task
            print(json.dumps({"phase": "prepared_corpus", "corpus": corpus, "selected": len(chosen)}), flush=True)
        manifest = [{"position": n, **tasks[d["custom_id"]]} for n, d in enumerate(selected, 1)]
        plan = {"method": METHOD, "versions": bound, "implementation": implementation(), "selection": selection_id,
                "manifest": self.ledger.artifacts.put(manifest), "source_provenance": provenance,
                "archive_checks": archive_checks, "selected_articles": len(manifest),
                "planned_requests": sum(t["disposition"] == "ready" for t in manifest),
                "frame_counts": selection["frame_counts"], "selected_by_corpus": dict(Counter(t["corpus"] for t in manifest)),
                "dispositions": dict(Counter(t["disposition"] for t in manifest)), "base": str(base),
                "prior_budget": prior, "maximum_cost_nanousd": STUDY_BUDGET,
                "total_budget_nanousd": TOTAL_BUDGET, "reservation_nanousd": transport.RESERVATION_NANOUSD,
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(), "retries": 0}
        identifier = self.ledger.record(session, "incident_screen_plan", METHOD, plan)
        return {"id": identifier, **{k: plan[k] for k in ("selected_articles", "planned_requests", "frame_counts",
                "selected_by_corpus", "dispositions", "expires_at")}, "prior_cost_usd": prior["cost_nanousd"] / 1e9,
                "new_study_cap_usd": STUDY_BUDGET / 1e9, "model_calls": 0}

    def complete(self, session, intended, response_ref, assessment, status):
        def project(event):
            self.ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (
                intended["attempt"], intended["task_key"], intended["batch"], 1, intended["request"],
                response_ref, status, assessment, None, event))
        self.ledger.append(session, "model.attempt.completed", {"attempt": intended["attempt"], "status": status,
            "assessment": assessment, "response": response_ref, "ended_at": utc()}, project)
        self.ledger.unresolved.pop(intended["attempt"])

    def run_screen(self, session, plan, data):
        self.absent("incident_screen_launch")
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("screen_explicit_online_execution_and_saved_key_required")
        if self.ledger.unresolved:
            raise AuditError("screen_unresolved_attempt_no_retry")
        if prior_budget(Path(plan["base"])) != plan["prior_budget"]:
            raise AuditError("screen_prior_budget_changed")
        self.ledger.record(session, "incident_screen_launch", METHOD, {"plan": plan["_record_id"], "started_at": utc()})
        manifest = self.ledger.artifacts.read(plan["manifest"])
        total, sent, stop = 0, 0, "manifest_exhausted"
        started_all = time.perf_counter()
        for task in manifest:
            if task["disposition"] != "ready":
                continue
            if (self.ledger.root / "STOP").exists():
                stop = "user_stop"
                break
            if datetime.now(timezone.utc) >= datetime.fromisoformat(plan["expires_at"]):
                stop = "deadline"
                break
            if (total + plan["reservation_nanousd"] > plan["maximum_cost_nanousd"]
                    or plan["prior_budget"]["cost_nanousd"] + total + plan["reservation_nanousd"] > plan["total_budget_nanousd"]):
                stop = "budget_bound"
                break
            attempt = str(uuid.uuid4())
            key = digest([plan["_record_id"], task["custom_id"], task["request"]])
            invocation = transport.Invocation(self.ledger.artifacts.read(task["request"]), attempt)
            intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": plan["_record_id"],
                "request": task["request"], "custom_id": task["custom_id"], "corpus": task["corpus"],
                "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc(),
                "reserved_nanousd": plan["reservation_nanousd"]}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[attempt] = intended
            started = time.perf_counter()
            response = next(self.gateway.codex_dispatch(session, transport.DecisionsTransport(), [(invocation, attempt)], 1))[1]
            elapsed = time.perf_counter() - started
            sent += 1
            response_ref = self.ledger.artifacts.put(asdict(response))
            self.ledger.append(session, "incident_screen.response.received", {"attempt": attempt, "response": response_ref})
            tokens = (response.usage or {}).get("input_tokens")
            valid_usage = type(tokens) is int and 0 <= tokens <= 1_050_000
            cost = tokens * transport.RATE_NANOUSD_PER_TOKEN * (2 if tokens > 272000 else 1) if valid_usage else None
            raw, decision, failure = response.raw_response or {}, None, None
            if response.payload is not None:
                try:
                    decision = core.parse_response(response.payload)
                except (KeyError, TypeError, ValueError, ResearchError, RuntimeError) as error:
                    failure = type(error).__name__
            hold = bool(raw.get("unknown_outcome")) or cost is None or cost > plan["reservation_nanousd"] or response.model != "gpt-6-luna"
            result = self.ledger.record(session, "incident_screen_decision", key, {
                "plan": plan["_record_id"], "custom_id": task["custom_id"], "corpus": task["corpus"],
                "position": task["position"], "request": task["request"], "source": task["source"],
                "attempt": attempt, "response": response_ref, "decision": decision,
                "input_tokens": tokens if valid_usage else None, "cost_nanousd": cost,
                "reserved_nanousd": plan["reservation_nanousd"] if hold else 0,
                "unknown_or_billing_hold": hold, "http_status": raw.get("http_status"),
                "validation_error": failure, "seconds": elapsed})
            if not hold:
                self.complete(session, intended, response_ref, result, decision["status"] if decision else "invalid")
                total += cost
            if sent <= 3 or sent % 100 == 0 or hold or failure:
                print(json.dumps({"phase": "screening", "stored_responses": sent, "planned": plan["planned_requests"],
                    "cost_usd_with_margin": total / 1e9, "hold": hold, "elapsed_seconds": round(time.perf_counter() - started_all, 2)}), flush=True)
            if hold or failure or raw.get("http_status") != 200 or not decision:
                stop = "unknown_or_billing_hold" if hold else "invalid_response"
                break
        result = {"plan": plan["_record_id"], "stored_responses": sent, "stop_reason": stop,
                  "unresolved_attempts": len(self.ledger.unresolved), "cost_usd_with_margin": total / 1e9,
                  "elapsed_seconds": time.perf_counter() - started_all, "finished_at": utc()}
        self.ledger.record(session, "incident_screen_run_end", METHOD, result)
        return result

    def report(self, session, plan):
        manifest = self.ledger.artifacts.read(plan["manifest"])
        rows = self.rows("incident_screen_decision")
        identifiers = {t["custom_id"] for t in manifest}
        if len({r["custom_id"] for r in rows}) != len(rows) or any(r["custom_id"] not in identifiers for r in rows):
            raise AuditError("screen_report_manifest_identity_invalid")
        completed_ids = {r["custom_id"] for r in rows}
        reserved_attempts = {r["attempt"] for r in rows if r["reserved_nanousd"]}
        holds = sum(r["reserved_nanousd"] for r in rows) + sum(
            v.get("reserved_nanousd", plan["reservation_nanousd"]) for k, v in self.ledger.unresolved.items() if k not in reserved_attempts)
        settled_cost = sum(r["cost_nanousd"] for r in rows if not r["unknown_or_billing_hold"])
        tokens = sum(r["input_tokens"] or 0 for r in rows)

        def coverage(tasks, responses):
            counts = Counter((r.get("decision") or {}).get("status", "invalid") for r in responses)
            return {"selected": len(tasks), "planned_requests": sum(t["disposition"] == "ready" for t in tasks),
                    "stored_responses": len(responses), "valid": counts["valid"], "refusals": counts["refusal"],
                    "invalid_responses": counts["invalid"], "not_attempted": sum(t["disposition"] == "ready" and t["custom_id"] not in completed_ids for t in tasks),
                    "unavailable_inputs": dict(Counter(t["disposition"] for t in tasks if t["disposition"] != "ready"))}

        review_items = []
        for label in ("keep", "exclude", "review"):
            members = [r for r in rows if (r.get("decision") or {}).get("route") == label]
            for r in sorted(members, key=lambda r: digest([core.SEED, "unreviewed-audit", r["custom_id"]]))[:20]:
                review_items.append({k: r[k] for k in ("custom_id", "corpus", "source", "decision")})
        review = self.ledger.artifacts.put({"status": "unreviewed", "sampling": "Up to 20 per route by fixed hash; labels visible; not an independent reference set.",
                                            "items": review_items, "accuracy_measured": False})
        all_coverage = coverage(manifest, rows)
        results = {"method": METHOD, "plan": plan["_record_id"], "coverage": all_coverage,
                   "dispatch_complete": len(rows) == plan["planned_requests"] and not self.ledger.unresolved,
                   "complete": len(rows) == plan["selected_articles"] and not self.ledger.unresolved and all((r.get("decision") or {}).get("status") == "valid" for r in rows),
                   "labels": core.describe(rows), "by_corpus": {}, "input_tokens_observed": tokens,
                   "cost_usd_with_margin": settled_cost / 1e9,
                   "base_token_cost_usd": sum((r["input_tokens"] or 0) * 100 * (2 if (r["input_tokens"] or 0) > 272000 else 1) for r in rows if not r["unknown_or_billing_hold"]) / 1e9,
                   "held_reservations_usd": holds / 1e9, "unresolved_attempts": len(self.ledger.unresolved),
                   "prior_cost_usd_with_margin": plan["prior_budget"]["cost_nanousd"] / 1e9,
                   "total_budget_committed_usd": (plan["prior_budget"]["cost_nanousd"] + settled_cost + holds) / 1e9,
                   "remaining_budget_usd": (plan["total_budget_nanousd"] - plan["prior_budget"]["cost_nanousd"] - settled_cost - holds) / 1e9,
                   "request_seconds_sum": sum(r["seconds"] for r in rows),
                   "request_seconds_median": statistics.median(r["seconds"] for r in rows) if rows else None,
                   "request_seconds_max": max((r["seconds"] for r in rows), default=None),
                   "run_end": self.rows("incident_screen_run_end"), "review_sample": review,
                   "review_sample_articles": len(review_items), "accuracy_measured": False, "human_validated": False,
                   "new_extractions": 0, "new_collection": 0, "accepted_dossiers": 0}
        for corpus in sorted(plan["selected_by_corpus"]):
            tasks = [t for t in manifest if t["corpus"] == corpus]
            responses = [r for r in rows if r["corpus"] == corpus]
            results["by_corpus"][corpus] = {"coverage": coverage(tasks, responses), "labels": core.describe(responses)}
        identifier = self.ledger.record(session, "incident_screen_report", digest(results), results)
        path = self.ledger.root / "screening-report.json"
        temporary = path.with_suffix(".writing")
        temporary.write_text(json.dumps({"id": identifier, **results}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        return {"id": identifier, "report": str(path), **results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "report"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    engine = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {**vars(args), "workspace": str(args.workspace), "base": str(args.base)}
        print(json.dumps(engine.execute("status", data,
            objective="Screen a frozen 1000-article pilot for one focal event and an AI-related harmful occurrence",
            actor="codex:luna-incident-screening"), ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
