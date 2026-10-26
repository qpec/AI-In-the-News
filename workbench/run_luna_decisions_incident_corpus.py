"""Audited incident-only continuation after the user excluded cybercrime."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, utc
from newsresearch.runtime import audited_handler
import run_luna_decisions_full_corpus as base
import run_luna_decisions_full_corpus_paced as paced

METHOD = "luna-decisions-incident-reports-20261021-v1"
CORPUS = "incident-reports"
EXCLUSION = "Dont do the cybercrieme ones."
core, pilot = base.core, base.pilot


def implementation():
    paths = base.implementation()
    for path in (Path(__file__), Path(paced.__file__)):
        paths[str(path.relative_to(pilot.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths


def parent_state(owner):
    source = pilot.Source(owner)
    try:
        if not (source.owner / "STOP").is_file():
            raise AuditError("incident_parent_must_remain_stopped")
        plan = source.one("full_screen_plan")
        if plan["implementation"] != base.implementation():
            raise AuditError("incident_parent_implementation_changed")
        ends, launches = source.rows("full_screen_run_end"), source.rows("full_screen_launch")
        reports = source.rows("full_screen_report")
        if not ends or not launches or not reports or ends[-1]["stop_reason"] != "user_stop":
            raise AuditError("incident_parent_stop_not_finalized")
        rows = source.rows("full_screen_decision")
        # This continuation was designed after verifying that dispatch had not
        # reached this corpus. Fail closed if the historical premise changes.
        if any(r["corpus"] != "cybercrime" for r in rows):
            raise AuditError("incident_parent_contains_incident_attempts")
        intended, completed = {}, set()
        for event in source.db.execute("SELECT kind,payload FROM events WHERE kind IN ('model.attempt.intended','model.attempt.completed') ORDER BY seq"):
            value = json.loads(event[1])
            if event[0] == "model.attempt.intended":
                if value["corpus"] != "cybercrime":
                    raise AuditError("incident_parent_contains_incident_attempts")
                intended[value["attempt"]] = value
            else:
                completed.add(value["attempt"])
        unresolved = {k: v for k, v in intended.items() if k not in completed}
        settled = sum(r["cost_nanousd"] for r in rows if not r["unknown_or_billing_hold"])
        held = sum(r["reserved_nanousd"] for r in unresolved.values())
        if (len(rows) != len(intended) or ends[-1]["settled_nanousd"] != settled
                or ends[-1]["held_nanousd"] != held or reports[-1]["new_responses"] != len(rows)
                or any((r["attempt"] in unresolved) != r["unknown_or_billing_hold"] for r in rows)):
            raise AuditError("incident_parent_accounting_mismatch")
        previous, _ = base.prior_state(Path(plan["base"]))
        if previous != plan["prior_state"]:
            raise AuditError("incident_earlier_budget_changed")
        authorizations = source.rows("full_screen_authorization")
        if not authorizations or authorizations[-1]["total_budget_nanousd"] > 100_000_000_000:
            raise AuditError("incident_parent_budget_authorization_missing")
        state = {"owner": str(source.owner), "head": source.head(), "plan": plan["_record_id"],
            "run_end": ends[-1]["_record_id"], "report": reports[-1]["_record_id"],
            "budget_authorization_record": authorizations[-1]["_record_id"],
            "total_budget_nanousd": authorizations[-1]["total_budget_nanousd"],
            "original_deadline": launches[0]["expires_at"],
            "earlier_cost_nanousd": previous["cost_nanousd"], "parent_cost_nanousd": settled,
            "cost_nanousd": previous["cost_nanousd"] + settled,
            "held_nanousd": held, "unresolved_attempts": unresolved,
            "parent_decisions": [r["_record_id"] for r in rows],
            "screen_owner": previous["screen_owner"]}
        return state, plan
    finally:
        source.close()


class Study(base.Study):
    @audited_handler
    def _status(self, session, context, data):
        if data["action"] == "prepare":
            return self.prepare_incidents(session, context, data)
        plan = self.one("full_screen_plan")
        if plan["implementation"] != implementation():
            raise AuditError("incident_implementation_changed")
        if data["action"] == "run":
            return self.run_incidents(session, plan, data)
        if data["action"] in {"report", "status"}:
            return self.report_full(session, plan)
        raise AuditError("incident_unknown_action")

    def prepare_incidents(self, session, context, data):
        self.absent("full_screen_preparation")
        content = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "Continue only incident-reports from the frozen full-corpus preparation after user exclusion of cybercrime. Verify and copy exact protected requests, descriptors and matching pilot labels without collecting sources or re-extracting. Keep the parent stopped. Preserve all earlier costs, unknown reservations and the original launch deadline. Shared audited gateway, one attempt per untouched article, no retries, same two questions and routing. Stop after three failed waves; unresolved outcomes never become exclusions.",
                "limitations": "Exploratory model classifications, not accepted dossiers or measured accuracy. Stored article completeness is not publisher-page completeness. Parent unknown holds are inherited liabilities, not proven spend."},
            "question": {"text": "Screen every eligible incident-report article for one focal event and actual or alleged AI-related harm."},
            "selection": {"rules": "Exact corpus_id incident-reports only from the prepared parent. Exclude all cybercrime. Retain order, identities, missingness and exact-request pilot reuse. No semantic filtering."},
            "dossier_definition": {"unit": "One focal real-world event with actual or alleged material AI-related harm; article screening does not establish event identity."},
            "prompt": {"instructions": core.GENERAL, "questions": core.QUESTIONS, "input": "Exact retained title and full body."},
            "codebook": {"labels": sorted(set(v for values in core.LABELS.values() for v in values)),
                "questions": core.QUESTIONS, "routing": "keep if single_event AND yes; exclude if multiple_events/no_event OR no; otherwise review. Refusals review."},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
            "policy": {"approved_by": "user:current-chat", "scope_instruction": EXCLUSION,
                "execution_instruction": base.AUTHORIZATION, "budget_instruction": "Budget may be100 dollar",
                "inherit_parent_budget_deadline_and_holds": True, "retries": 0,
                "maximum_concurrency": base.MAX_WORKERS, "reservation_nanousd": base.RESERVATION,
                "tokens_per_minute_estimate_cap": paced.TOKENS_PER_MINUTE, "requests_per_minute_cap": paced.REQUESTS_PER_MINUTE,
                "rate_nanousd_per_input_token_with_margin": base.RATE}}
        versions = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"]
                    for k, v in content.items()}
        self.ledger.record(session, "full_screen_preparation", METHOD, {"versions": versions, "at": utc()})
        previous, parent = parent_state(Path(data["parent"]))
        self.ledger.record(session, "incident_parent_snapshot", METHOD, previous)
        source = pilot.Source(previous["owner"])
        chunks, reused, counts, identities = [], [], Counter(), set()
        proxy_new = proxy_reused = weighted_proxy = position = 0
        try:
            prior = {r["custom_id"]: r for r in source.artifacts.json(parent["reused_rows"])
                     if r["corpus"] == CORPUS}
            for chunk in parent["chunks"]:
                tasks = source.artifacts.json(chunk["artifact"])
                if len(tasks) != chunk["count"]:
                    raise AuditError("incident_parent_chunk_changed")
                selected = []
                for original in tasks:
                    if original["corpus"] != CORPUS:
                        continue
                    task = dict(original)
                    if task["custom_id"] in identities or task["descriptor"]["corpus_id"] != CORPUS:
                        raise AuditError("incident_frame_identity_invalid")
                    identities.add(task["custom_id"])
                    position += 1
                    task.update(parent_position=task["position"], position=position)
                    if task["request"] is not None:
                        evidence = json.loads(task["request"]["input"])
                        if (base.request_for(evidence["title"], evidence["body"]) != task["request"]
                                or digest(task["request"]) != task["request_hash"]
                                or hashlib.sha256(evidence["body"].encode()).hexdigest() != task["descriptor"]["retained_body_sha256"]):
                            raise AuditError("incident_request_or_source_changed")
                    if task["disposition"] == "reused":
                        row = prior.pop(task["custom_id"])
                        if row["request"] != task["request_hash"] or row["_record_id"] != task["prior_record"]:
                            raise AuditError("incident_reused_request_changed")
                        reused.append(row)
                        proxy_reused += task["input_tokens_proxy"]
                    elif task["disposition"] == "ready":
                        proxy_new += task["input_tokens_proxy"]
                        weighted_proxy += task["input_tokens_proxy"] * (2 if task["input_tokens_proxy"] > 272000 else 1)
                    counts[task["disposition"]] += 1
                    selected.append(task)
                if selected:
                    ref = self.ledger.artifacts.put(selected)
                    entry = {"artifact": ref, "count": len(selected), "parent_artifact": chunk["artifact"]}
                    self.ledger.record(session, "full_screen_prepared_chunk", str(len(chunks)), entry)
                    chunks.append(entry)
                    if position % 10000 < len(selected):
                        print(json.dumps({"phase": "preparing_incident_only", "articles": position}), flush=True)
            if position != parent["frame_counts"][CORPUS] or prior or dict(counts) != parent["by_corpus"][CORPUS]:
                raise AuditError("incident_preparation_coverage_mismatch")
        finally:
            source.close()
        ratio = parent["cost_estimate"]["observed_to_proxy_ratio"]
        forecast = weighted_proxy * ratio * base.RATE / 1e9
        baseline = (previous["cost_nanousd"] + previous["held_nanousd"]) / 1e9
        plan = {"method": METHOD, "implementation": implementation(), "versions": versions,
            "parent": previous, "prior_state": previous, "chunks": chunks,
            "reused_rows": self.ledger.artifacts.put(reused), "selected_articles": position,
            "frame_counts": {CORPUS: position}, "dispositions": dict(counts), "by_corpus": {CORPUS: dict(counts)},
            "initial_total_budget_nanousd": previous["total_budget_nanousd"],
            "cost_estimate": {"exact_provider_count": False, "observed_to_proxy_ratio": ratio,
                "new_input_tokens_proxy": proxy_new, "reused_input_tokens_proxy": proxy_reused,
                "estimated_new_cost_usd_with_margin": forecast,
                "planning_total_usd_with_20_percent_buffer_and_inherited_holds": forecast * 1.2 + baseline},
            "api_calls_at_preparation": 0, "human_validated": False}
        identifier = self.ledger.record(session, "full_screen_plan", METHOD, plan)
        result = {"id": identifier, "selected_articles": position, "corpus": CORPUS,
            "dispositions": dict(counts), "cost_estimate": plan["cost_estimate"],
            "earlier_cost_usd_with_margin": previous["cost_nanousd"] / 1e9,
            "inherited_holds_usd": previous["held_nanousd"] / 1e9,
            "budget_usd": previous["total_budget_nanousd"] / 1e9,
            "original_deadline": previous["original_deadline"], "new_api_calls": 0}
        self.save("preparation-report.json", result)
        return result

    def tasks(self, plan):
        for task in super().tasks(plan):
            if task["corpus"] != CORPUS or task["descriptor"]["corpus_id"] != CORPUS:
                raise AuditError("incident_cybercrime_dispatch_forbidden")
            yield task

    def run_incidents(self, session, plan, data):
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("incident_explicit_online_execution_and_saved_key_required")
        if parent_state(Path(plan["parent"]["owner"]))[0] != plan["parent"]:
            raise AuditError("incident_parent_state_changed")
        previous = plan["parent"]
        cap, expires = self.budget(plan), previous["original_deadline"]
        if plan["cost_estimate"]["planning_total_usd_with_20_percent_buffer_and_inherited_holds"] > cap / 1e9:
            raise AuditError("incident_forecast_exceeds_budget")
        if (self.ledger.root / "STOP").exists() or datetime.now(timezone.utc) >= datetime.fromisoformat(expires):
            raise AuditError("incident_stopped_or_expired")
        launches = self.rows("full_screen_launch")
        self.ledger.record(session, "full_screen_launch", str(len(launches) + 1),
            {"plan": plan["_record_id"], "total_budget_nanousd": cap, "expires_at": expires, "started_at": utc()})
        provider = paced.PacedTransport(paced.Pacer(plan["cost_estimate"]["observed_to_proxy_ratio"]),
            plan["versions"]["policy"], self.ledger.root, expires)
        existing = self.rows("full_screen_decision")
        attempted = {r["custom_id"] for r in existing} | {r["custom_id"] for r in self.ledger.unresolved.values()}
        ready = (t for t in self.tasks(plan) if t["disposition"] == "ready" and t["custom_id"] not in attempted)
        settled = sum(r["cost_nanousd"] for r in existing if not r["unknown_or_billing_hold"])
        held = sum(r["reserved_nanousd"] for r in self.ledger.unresolved.values())
        baseline = previous["cost_nanousd"] + previous["held_nanousd"]
        sent, stop, failures = len(existing), "manifest_exhausted", 0
        began = time.perf_counter()
        while True:
            if (self.ledger.root / "STOP").exists():
                stop = "user_stop"
                break
            if datetime.now(timezone.utc) >= datetime.fromisoformat(expires):
                stop = "deadline"
                break
            workers = min(base.MAX_WORKERS if sent >= 16 and not failures else 4,
                          (cap - baseline - settled - held) // base.RESERVATION)
            if workers < 1:
                stop = "budget_bound"
                break
            wave = []
            for _ in range(workers):
                task = next(ready, None)
                if task is None:
                    break
                if digest(task["request"]) != task["request_hash"]:
                    raise AuditError("incident_request_hash_changed")
                request_ref = self.ledger.artifacts.put(task["request"])
                attempt = str(uuid.uuid4())
                key = digest([plan["_record_id"], task["corpus"], task["custom_id"], request_ref])
                invocation = base.Invocation(task["request"], attempt)
                intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": plan["_record_id"],
                    "request": request_ref, "custom_id": task["custom_id"], "corpus": task["corpus"],
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc(),
                    "reserved_nanousd": base.RESERVATION}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((task, intended, invocation, time.perf_counter()))
            if not wave:
                break
            failed = False
            for index, response in self.gateway.codex_dispatch(session, provider,
                    [(w[2], w[1]["attempt"]) for w in wave], len(wave)):
                task, intended, _, started = wave[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "full_screen.response.received", {"attempt": intended["attempt"], "response": response_ref})
                tokens = (response.usage or {}).get("input_tokens")
                usage_valid = type(tokens) is int and 0 <= tokens <= 1_050_000
                cost = tokens * base.RATE * (2 if tokens > 272000 else 1) if usage_valid else None
                decision = error_type = None
                if response.payload is not None:
                    try:
                        decision = core.parse_response(response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError, RuntimeError) as error:
                        error_type = type(error).__name__
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > base.RESERVATION or response.model != "gpt-6-luna"
                value = {"plan": plan["_record_id"], "custom_id": task["custom_id"], "corpus": CORPUS,
                    "position": task["position"], "descriptor": task["descriptor"], "request": intended["request"],
                    "attempt": intended["attempt"], "response": response_ref, "decision": decision,
                    "input_tokens": tokens if usage_valid else None, "cost_nanousd": cost,
                    "reserved_nanousd": base.RESERVATION if hold else 0, "unknown_or_billing_hold": hold,
                    "http_status": raw.get("http_status"), "validation_error": error_type, "seconds": time.perf_counter() - started}
                identifier = self.ledger.record(session, "full_screen_decision", intended["task_key"], value)
                sent += 1
                if hold:
                    held += base.RESERVATION
                else:
                    self.complete(session, intended, response_ref, identifier, decision["status"] if decision else "invalid")
                    settled += cost
                failed |= hold or bool(error_type) or raw.get("http_status") != 200 or not decision
            progress = {"phase": "screening", "corpus": CORPUS, "new_responses": sent,
                "planned": plan["dispositions"].get("ready", 0), "new_cost_usd_with_margin": settled / 1e9,
                "new_holds_usd": held / 1e9, "inherited_holds_usd": previous["held_nanousd"] / 1e9,
                "total_committed_usd": (baseline + settled + held) / 1e9,
                "elapsed_seconds": round(time.perf_counter() - began, 2), "at": utc()}
            self.save("progress.json", progress)
            if sent <= 16 or sent % 1024 < len(wave) or failed:
                print(json.dumps(progress), flush=True)
            failures = failures + 1 if failed else 0
            if failures >= 3:
                stop = "three_consecutive_failed_waves"
                break
            if failed:
                time.sleep(5)
        self.ledger.record(session, "full_screen_run_end", METHOD,
            {"plan": plan["_record_id"], "new_responses": sent, "stop_reason": stop,
             "settled_nanousd": settled, "held_nanousd": held, "finished_at": utc(),
             "elapsed_seconds": time.perf_counter() - began})
        return self.report_full(session, plan)

    def report_full(self, session, plan):
        new = self.rows("full_screen_decision")
        reused = self.ledger.artifacts.read(plan["reused_rows"])
        if len({r["custom_id"] for r in new + reused}) != len(new) + len(reused):
            raise AuditError("incident_duplicate_identity")
        if any(r["corpus"] != CORPUS for r in new + reused):
            raise AuditError("incident_cross_corpus_result")
        settled = sum(r["cost_nanousd"] for r in new if not r["unknown_or_billing_hold"])
        held = sum(r["reserved_nanousd"] for r in self.ledger.unresolved.values())
        attempted = {r["custom_id"] for r in new} | {r["custom_id"] for r in self.ledger.unresolved.values()}
        all_rows = {r["custom_id"]: r for r in reused + new}
        export_path = self.ledger.root / "article-decisions.jsonl"
        temporary = export_path.with_suffix(".writing")
        with temporary.open("w", encoding="utf-8") as stream:
            for task in self.tasks(plan):
                row = all_rows.get(task["custom_id"])
                hold = row["unknown_or_billing_hold"] if row else task["custom_id"] in attempted
                status = ("unknown_outcome" if hold else (row.get("decision") or {}).get("status", "invalid") if row else
                          "not_attempted" if task["disposition"] == "ready" else task["disposition"])
                stream.write(canonical({"custom_id": task["custom_id"], "corpus": CORPUS, "status": status,
                    "reused": task["disposition"] == "reused", "request_hash": task["request_hash"],
                    "source_locator": task["descriptor"]["source_locator"], "decision": row.get("decision") if row else None,
                    "record_id": row["_record_id"] if row else None,
                    "record_owner": plan["prior_state"]["screen_owner"] if task["disposition"] == "reused" else str(self.ledger.root),
                    "unknown_or_billing_hold": hold, "human_validated": False}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, export_path)
        previous = plan["parent"]
        result = {"plan": plan["_record_id"], "corpus": CORPUS, "excluded_corpus": "cybercrime",
            "selected_articles": plan["selected_articles"], "input_dispositions": plan["dispositions"],
            "reused_results": len(reused), "new_responses": len(new),
            "not_attempted": plan["dispositions"].get("ready", 0) - len(attempted),
            "attempts_without_response": len(attempted) - len(new),
            "new_valid_results": sum((r.get("decision") or {}).get("status") == "valid" for r in new),
            "unresolved_attempts": len(self.ledger.unresolved), "labels": core.describe(reused + new),
            "new_input_tokens_observed": sum(r["input_tokens"] or 0 for r in new),
            "new_cost_usd_with_margin": settled / 1e9, "new_holds_usd": held / 1e9,
            "earlier_cost_usd_with_margin": previous["cost_nanousd"] / 1e9,
            "inherited_holds_usd": previous["held_nanousd"] / 1e9,
            "inherited_unresolved_attempts": len(previous["unresolved_attempts"]),
            "total_cost_usd_with_margin": (previous["cost_nanousd"] + settled) / 1e9,
            "total_budget_committed_usd": (previous["cost_nanousd"] + previous["held_nanousd"] + settled + held) / 1e9,
            "budget_usd": self.budget(plan) / 1e9, "original_deadline": previous["original_deadline"],
            "run_end": self.rows("full_screen_run_end"),
            "dispatch_complete": len(new) == plan["dispositions"].get("ready", 0) and not self.ledger.unresolved,
            "article_results_path": str(export_path), "article_results_artifact": self.ledger.artifacts.put_file(export_path),
            "human_validated": False, "accepted_dossiers": 0, "new_collection": 0}
        identifier = self.ledger.record(session, "full_screen_report", digest(result), result)
        self.save("screening-report.json", {"id": identifier, **result})
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "run", "report", "status"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--parent", type=Path, default=pilot.BASE / base.METHOD)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {**vars(args), "workspace": str(args.workspace), "parent": str(args.parent)}
        print(json.dumps(study.execute("status", data,
            objective="Continue the authorized two-question Luna Decisions screen for incident reports only, excluding cybercrime",
            actor="codex:luna-decisions-incident-only"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
