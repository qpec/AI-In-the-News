"""Separate, audited Netherlands cybercrime Decisions screen, capped at USD20."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "workbench"))
sys.path.insert(0, str(Path(__file__).parent))
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, utc  # noqa: E402
from newsresearch.runtime import audited_handler  # noqa: E402
import run_luna_decisions_full_corpus as base  # noqa: E402
import run_luna_decisions_full_corpus_paced as paced  # noqa: E402
from prepare_luna_multibatch import offline_tokenizer  # noqa: E402
import screening_contract as core  # noqa: E402

METHOD = "luna-decisions-cybercrime-nl-20261023-v1"
CORPUS = "cybercrime"
CAP = 20_000_000_000
OPERATIONAL_COUNT = 100
MAX_WORKERS = 16
DEFAULT_PARENT = base.pilot.BASE / "luna-fulltext-multibatch-cybercrime-20261017-v1"
DEFAULT_SEALED_OWNER = base.pilot.BASE / "luna-seven-day-validation-20261016-v1"
DEFAULT_OWNER = base.pilot.BASE / METHOD
AUTHORIZATION = "Also run cybercrime screening, capped at $20"


def implementation():
    paths = base.implementation()
    for path in (Path(__file__), Path(core.__file__), Path(paced.__file__)):
        paths[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths


@dataclass(frozen=True)
class Invocation:
    request: dict
    client_id: str

    def manifest(self):
        return {"transport": METHOD, "url": "https://api.openai.com/v1/decisions", "method": "POST",
                "wire_sha256": digest(self.request), "client_id": self.client_id,
                "automatic_retries": 0, "timeout_seconds": 60, "maximum_wire_bytes": core.MAX_WIRE_BYTES}


class Study(base.pilot.Study):
    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "prepare":
            return self.prepare_cyber(session, context, data)
        plan = self.one("cyber_screen_plan")
        if plan["implementation"] != implementation():
            raise AuditError("cyber_implementation_changed_after_freeze")
        if action in {"operational", "run"}:
            return self.run_cyber(session, plan, data)
        if action == "approve-operational":
            return self.approve_operational(session, plan)
        if action in {"report", "status"}:
            return self.report_cyber(session, plan)
        raise AuditError("cyber_unknown_action")

    def prepare_cyber(self, session, context, data):
        self.absent("cyber_screen_preparation")
        definitions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "Freeze all original cybercrime archive rows from the protected fulltext preparation, including previously processed articles. Preserve retention-unavailable rows and sealed validation body exclusions; reconstruct only permitted unsealed inputs after whole-archive and exact descriptor checks. Use exact retained title/body in new cybercrime questions. Deduplicate only identical new request hashes, retaining every article alias. Do not reuse AI labels. Hash-ranked first100 form an operational check; the remaining frozen queue needs a clean recorded operational gate. One model attempt per article through the shared gateway; no retry, no truncation, no replacement. Preserve all old owners, costs, holds, STOPs and deadlines unchanged. Independent new USD20 budget includes this check and all reservations. Full local preflight every execution; selected artifact integrity rather than complete replay of historic source owner. Provisional classifications, no accepted dossiers.",
                "limits": "Stored article completeness is not publisher completeness. Historical eligibility/retention exclusions limit the frame. Operational schema/billing success is not semantic validation. Neither Dutch language nor publisher proves Netherlands relevance."},
            "question": {"text": "Which existing cybercrime-frame articles clearly report one actual or alleged cybercrime occurrence with a direct Netherlands nexus?"},
            "selection": {"rules": "All corpus_id=cybercrime rows in original fulltext preparation; no incident-reports. Prior extraction completion does not exclude a row from these new questions. Preserve retention guards and the previously sealed cross-corpus body frame. Retain every source identity and explicit unavailable/alias state; no body-only dedup. SHA256 method/custom_id/source_sha256 order; first100 unique ready requests are operational, then every remaining ready request."},
            "dossier_definition": {"unit": "One specific reported occurrence or explicitly bounded continuing episode; this screen establishes eligibility, not dossier membership or factual truth."},
            "prompt": {"instructions": core.GENERAL, "questions": core.QUESTIONS,
                       "input": "Exact retained title/body only; no previous labels, summaries, source/corpus/provider ID hints.",
                       "cache": "Explicit mode without marked breakpoints disables input caching."},
            "codebook": {"labels": sorted({v for labels in core.LABELS.values() for v in labels}),
                         "questions": core.QUESTIONS, "routing": "keep only single_event + yes + direct; decisive no/multiple_events/no_event/other_only/none excludes; otherwise review; refusal and failures unresolved, never negative"},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
            "policy": {"approved_by": "user:current-chat", "instruction": AUTHORIZATION,
                       "total_budget_nanousd": CAP, "reservation_nanousd": core.RESERVATION_NANOUSD,
                       "maximum_workers": MAX_WORKERS, "provider_retries": 0, "new_deadline_hours": 24,
                       "old_deadlines_unchanged": True, "operational_count": OPERATIONAL_COUNT,
                       "price_checked": "2026-10-23", "price_source": "https://developers.openai.com/api/docs/guides/decisions",
                       "input_rate_nanousd_with_10_percent_margin": core.RATE_NANOUSD,
                       "unexpected_cache_write_rate_nanousd_maximum": core.MAX_CACHE_WRITE_RATE_NANOUSD,
                       "long_context_multiplier": 2, "long_context_threshold": 272000,
                       "tokens_per_minute_estimate_cap": paced.TOKENS_PER_MINUTE,
                       "requests_per_minute_cap": paced.REQUESTS_PER_MINUTE}}
        versions = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"]
                    for k, v in definitions.items()}
        self.ledger.record(session, "cyber_screen_preparation", METHOD, {"versions": versions, "at": utc()})
        parent = base.pilot.Source(data["parent"])
        encoding = offline_tokenizer()
        selected, identities, counts = [], set(), Counter()
        proxy = weighted = 0
        sealed_owner = base.pilot.Source(data["sealed_owner"])
        try:
            sealed_record = sealed_owner.one("luna_batch_eligibility_export")
            sealed = sealed_owner.artifacts.json(sealed_record["export"])
            sealed_hashes = set(sealed["sealed_body_hashes"])
            sealed_provenance = {"owner": str(sealed_owner.owner), "head": sealed_owner.head(),
                                 "record": sealed_record["_record_id"], "artifact": sealed_record["export"],
                                 "sealed_body_hash_count": len(sealed_hashes)}
        finally:
            sealed_owner.close()
        try:
            note = parent.one("note")
            old = note["content"]
            if old["corpus_id"] != CORPUS:
                raise AuditError("cyber_source_corpus_invalid")
            manifest = parent.artifacts.json(old["manifest_artifact"])
            partition = old["binding"]["partition"]
            snapshot = base.pilot.materializer.core.load_contract_snapshot()
            base.pilot.materializer.materialize.validate_preparation_binding(old, manifest, partition, snapshot)
            provenance = {"owner": str(parent.owner), "head": parent.head(), "preparation": note["_record_id"],
                          "manifest_artifact": old["manifest_artifact"], "source_totals": old["totals"],
                          "source_frame_count": old["totals"]["rows"], "historic_labels_reused": 0,
                          "sealed_validation": sealed_provenance, "archive_checks": []}
            root = Path(partition["resolved_root"]).resolve(strict=True)
            canonical_requests = {}
            for chunk in manifest["descriptor_chunks"]:
                source_rows = parent.artifacts.json(chunk["artifact"])["rows"]
                if len(source_rows) != chunk["rows"]:
                    raise AuditError("cyber_source_chunk_changed")
                wanted = {}
                for row in source_rows:
                    descriptor = row.get("descriptor")
                    custom_id = descriptor["custom_id"] if descriptor else row["id"]
                    if custom_id in identities or row["corpus_id"] != CORPUS:
                        raise AuditError("cyber_source_identity_invalid")
                    identities.add(custom_id)
                    task = {"custom_id": custom_id, "corpus": CORPUS, "source_row_id": row["id"],
                            "descriptor": descriptor or {"corpus_id": CORPUS, "source_locator": row["source_locator"]},
                            "request": None, "request_hash": None, "disposition": row["state"]}
                    selected.append(task)
                    if descriptor is None:
                        if row["state"] not in {"retention_unavailable", "body_unavailable", "record_unavailable"}:
                            raise AuditError("cyber_missing_descriptor_unexplained")
                        continue
                    if descriptor["retained_body_sha256"] in sealed_hashes:
                        task["disposition"] = "sealed_validation"
                        continue
                    line = descriptor["source_locator"]["line"]
                    if line in wanted:
                        raise AuditError("cyber_duplicate_locator")
                    wanted[line] = task
                relative = chunk["archive_path"]
                path = (root / relative).resolve(strict=True)
                expected = next(b["sha256"] for b in partition["manifest"]["bundles"] if b["path"] == relative)
                if not path.is_relative_to(root):
                    raise AuditError("cyber_archive_path_outside_partition")
                def check_archive():
                    with path.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                            raise AuditError("cyber_archive_hash_mismatch")
                self.ledger.append(session, "cyber_screen.source_read.intended",
                    {"corpus": CORPUS, "archive": relative, "sha256": expected, "permitted_unsealed_rows": len(wanted),
                     "descriptor_chunk": chunk["artifact"], "versions": versions})
                check_archive()
                with zipfile.ZipFile(path) as archive:
                    if archive.namelist().count("artikelen.jsonl") != 1:
                        raise AuditError("cyber_archive_stream_ambiguous")
                    with archive.open("artikelen.jsonl") as stream:
                        for number, raw in enumerate(stream, 1):
                            if number not in wanted:
                                continue
                            task = wanted.pop(number)
                            descriptor = task["descriptor"]
                            record = base.pilot.materializer.materialize.materialize_descriptor(descriptor, raw,
                                partition=partition, contract_snapshot=snapshot,
                                count_tokens=lambda text: int(descriptor["input_tokens_proxy"]) - 32)
                            packet = record["packet"]
                            title = packet["model_input"]["evidence"]["title"]["text"]
                            body = packet["source_map"]["source_fields"]["body"]["text"]
                            try:
                                request = core.request_for(title, body)
                            except ResearchError as error:
                                if str(error) not in {"cyber_request_exceeds_byte_cap", "cyber_body_or_title_unavailable"}:
                                    raise
                                task["disposition"] = str(error)
                            else:
                                request_hash = digest(request)
                                task["request_hash"] = request_hash
                                canonical_id = canonical_requests.get(request_hash)
                                if canonical_id is not None:
                                    task.update(disposition="exact_input_alias", canonical_custom_id=canonical_id)
                                else:
                                    tokens = len(encoding.encode(canonical(request), disallowed_special=())) + 32
                                    task.update(request=request, disposition="ready", input_tokens_proxy=tokens)
                                    canonical_requests[request_hash] = task["custom_id"]
                                    proxy += tokens
                                    weighted += tokens * (2 if tokens > 272000 else 1)
                if wanted:
                    raise AuditError("cyber_archive_rows_missing")
                check_archive()
                provenance["archive_checks"].append({"path": relative, "sha256": expected, "before_and_after": True})
                print(json.dumps({"phase": "preparing_cybercrime", "rows": len(selected),
                                  "unique_requests": len(canonical_requests)}), flush=True)
            if len(selected) != old["totals"]["rows"]:
                raise AuditError("cyber_frame_coverage_mismatch")
            provenance["selected_artifacts_verified"] = sorted(parent.artifacts.checked)
            ratio = 1.0
        finally:
            parent.close()
        counts.update(t["disposition"] for t in selected)
        selected.sort(key=lambda t: (digest([METHOD, t["custom_id"], t["descriptor"].get("source_sha256", t["source_row_id"])]), t["custom_id"]))
        for position, task in enumerate(selected, 1):
            task["position"] = position
        chunks = [{"artifact": self.ledger.artifacts.put(selected[i:i + 500]), "count": len(selected[i:i + 500])}
                  for i in range(0, len(selected), 500)]
        check_ids = [t["custom_id"] for t in selected if t["disposition"] == "ready"][:OPERATIONAL_COUNT]
        plan = {"method": METHOD, "implementation": implementation(), "versions": versions,
                "provenance": provenance, "chunks": chunks, "selected_articles": len(selected),
                "dispositions": dict(counts), "operational_ids": check_ids, "budget_nanousd": CAP,
                "cost_estimate": {"input_tokens_proxy": proxy, "weighted_input_tokens_proxy": weighted,
                                  "maximum_input_tokens_proxy": max((t.get("input_tokens_proxy", 0) for t in selected), default=0),
                                  "planning_proxy_ratio": ratio,
                                  "exact_provider_count": False,
                                  "estimated_usd_with_margin": weighted * ratio * core.RATE_NANOUSD / 1e9,
                                  "planning_usd_with_20_percent_buffer": weighted * ratio * core.RATE_NANOUSD * 1.2 / 1e9},
                "api_calls_at_preparation": 0, "human_validated": False}
        identifier = self.ledger.record(session, "cyber_screen_plan", METHOD, plan)
        result = {"id": identifier, "selected_articles": len(selected), "dispositions": dict(counts),
                  "operational_count": len(check_ids), "cost_estimate": plan["cost_estimate"],
                  "budget_usd": CAP / 1e9, "new_api_calls": 0}
        self.save("preparation-report.json", result)
        return result

    def tasks(self, plan):
        for chunk in plan["chunks"]:
            values = self.ledger.artifacts.read(chunk["artifact"])
            if len(values) != chunk["count"]:
                raise AuditError("cyber_chunk_count_changed")
            for task in values:
                if task["corpus"] != CORPUS or task["descriptor"]["corpus_id"] != CORPUS:
                    raise AuditError("cyber_other_corpus_forbidden")
                yield task

    def save(self, name, value):
        path = self.ledger.root / name
        temporary = self.ledger.root / (name + "." + uuid.uuid4().hex + ".writing")
        with temporary.open("w", encoding="utf-8") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2))
            stream.flush()
            os.fsync(stream.fileno())
        for number in range(101):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if number == 100:
                    raise
                time.sleep(.2)

    def approve_operational(self, session, plan):
        self.absent("cyber_operational_gate")
        rows = self.rows("cyber_screen_decision")
        if ({r["custom_id"] for r in rows} != set(plan["operational_ids"])
                or self.ledger.unresolved
                or any(r["unknown_or_billing_hold"] or (r.get("decision") or {}).get("status") != "valid" for r in rows)):
            raise AuditError("cyber_operational_gate_not_clean")
        elapsed_cost = sum(r["cost_nanousd"] for r in rows)
        proxy = sum(r["input_tokens_proxy"] for r in rows)
        input_tokens = sum(r["input_tokens"] for r in rows)
        ratio = input_tokens / proxy if proxy else 1
        estimate = plan["cost_estimate"]
        token_forecast = estimate["weighted_input_tokens_proxy"] * ratio * core.RATE_NANOUSD
        if estimate["maximum_input_tokens_proxy"] * ratio > 272000:
            token_forecast = max(token_forecast, estimate["input_tokens_proxy"] * ratio * core.RATE_NANOUSD * 2)
        observed_cost_forecast = estimate["input_tokens_proxy"] * elapsed_cost / proxy if proxy else 0
        forecast = max(token_forecast, observed_cost_forecast) * 1.2
        if forecast > CAP:
            raise AuditError("cyber_operational_forecast_over_budget")
        value = {"plan": plan["_record_id"], "checked_rows": [r["_record_id"] for r in rows],
                 "schema_and_billing_passed": True, "semantic_accuracy_measured": False,
                 "observed_to_proxy_ratio": ratio, "observed_cost_nanousd": elapsed_cost,
                 "forecast_nanousd_with_20_percent_buffer": round(forecast), "at": utc()}
        identifier = self.ledger.record(session, "cyber_operational_gate", METHOD, value)
        return {"id": identifier, **value}

    def run_cyber(self, session, plan, data):
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("cyber_explicit_online_execution_and_saved_key_required")
        operational = data["action"] == "operational"
        if not operational:
            gate = self.one("cyber_operational_gate")
            ratio = gate["observed_to_proxy_ratio"]
        else:
            ratio = plan["cost_estimate"]["planning_proxy_ratio"]
        launches = self.rows("cyber_screen_launch")
        deadline = launches[0]["expires_at"] if launches else (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        if (self.ledger.root / "STOP").exists() or datetime.now(timezone.utc) >= datetime.fromisoformat(deadline):
            raise AuditError("cyber_stopped_or_expired")
        self.ledger.record(session, "cyber_screen_launch", str(len(launches) + 1),
                           {"plan": plan["_record_id"], "operational": operational,
                            "started_at": utc(), "expires_at": deadline, "budget_nanousd": CAP})
        provider = paced.PacedTransport(paced.Pacer(ratio), plan["versions"]["policy"], self.ledger.root, deadline)
        existing = self.rows("cyber_screen_decision")
        attempted = {r["custom_id"] for r in existing} | {r["custom_id"] for r in self.ledger.unresolved.values()}
        allowed = set(plan["operational_ids"]) if operational else None
        ready = (t for t in self.tasks(plan) if t["disposition"] == "ready" and t["custom_id"] not in attempted
                 and (allowed is None or t["custom_id"] in allowed))
        settled = sum(r["cost_nanousd"] for r in existing if not r["unknown_or_billing_hold"])
        held = sum(r["reserved_nanousd"] for r in self.ledger.unresolved.values())
        sent, failures, stop = len(existing), 0, "operational_exhausted" if operational else "manifest_exhausted"
        began = time.perf_counter()
        while True:
            if (self.ledger.root / "STOP").exists():
                stop = "user_stop"
                break
            if datetime.now(timezone.utc) >= datetime.fromisoformat(deadline):
                stop = "deadline"
                break
            workers = min(4 if operational or failures else MAX_WORKERS, (CAP - settled - held) // core.RESERVATION_NANOUSD)
            if workers < 1:
                stop = "budget_bound"
                break
            wave = []
            for _ in range(workers):
                task = next(ready, None)
                if task is None:
                    break
                if digest(task["request"]) != task["request_hash"]:
                    raise AuditError("cyber_request_hash_changed")
                request_ref = self.ledger.artifacts.put(task["request"])
                attempt = str(uuid.uuid4())
                invocation = Invocation(task["request"], attempt)
                intended = {"attempt": attempt, "task_key": digest([plan["_record_id"], task["custom_id"], request_ref]),
                            "number": 1, "batch": plan["_record_id"], "request": request_ref,
                            "custom_id": task["custom_id"], "corpus": CORPUS,
                            "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc(),
                            "reserved_nanousd": core.RESERVATION_NANOUSD}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((task, intended, invocation, time.perf_counter()))
            if not wave:
                break
            failed = False
            for index, response in self.gateway.codex_dispatch(session, provider, [(w[2], w[1]["attempt"]) for w in wave], len(wave)):
                task, intended, _, started = wave[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "cyber_screen.response.received", {"attempt": intended["attempt"], "response": response_ref})
                cost = core.observed_cost(response.usage)
                decision = error_type = None
                if response.payload is not None:
                    try:
                        decision = core.parse_response(response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as error:
                        error_type = type(error).__name__
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > core.RESERVATION_NANOUSD or response.model != "gpt-6-luna"
                value = {"plan": plan["_record_id"], "custom_id": task["custom_id"], "corpus": CORPUS,
                         "position": task["position"], "descriptor": task["descriptor"],
                         "request": intended["request"], "attempt": intended["attempt"], "response": response_ref,
                         "decision": decision, "input_tokens": (response.usage or {}).get("input_tokens") if cost is not None else None,
                         "input_tokens_proxy": task["input_tokens_proxy"], "cost_nanousd": cost,
                         "reserved_nanousd": core.RESERVATION_NANOUSD if hold else 0, "unknown_or_billing_hold": hold,
                         "http_status": raw.get("http_status"), "validation_error": error_type, "seconds": time.perf_counter() - started}
                record = self.ledger.record(session, "cyber_screen_decision", intended["task_key"], value)
                sent += 1
                if hold:
                    held += core.RESERVATION_NANOUSD
                else:
                    self.complete(session, intended, response_ref, record, decision["status"] if decision else "invalid")
                    settled += cost
                failed |= hold or bool(error_type) or raw.get("http_status") != 200 or not decision or decision["status"] != "valid"
            progress = {"phase": "operational" if operational else "screening", "new_responses": sent,
                        "planned": plan["dispositions"].get("ready", 0), "settled_cost_usd_with_margin": settled / 1e9,
                        "held_reservations_usd": held / 1e9, "total_committed_usd": (settled + held) / 1e9,
                        "budget_usd": CAP / 1e9, "expires_at": deadline, "at": utc(),
                        "execution_response_baseline": len(existing), "elapsed_seconds": round(time.perf_counter() - began, 2)}
            self.save("progress.json", progress)
            if operational or sent % 256 < len(wave) or failed:
                print(json.dumps(progress), flush=True)
            failures = failures + 1 if failed else 0
            if failures >= 3 or (operational and failed):
                stop = "operational_failure" if operational else "three_consecutive_failed_waves"
                break
            if failed:
                time.sleep(5)
        self.ledger.record(session, "cyber_screen_run_end", str(uuid.uuid4()),
                           {"plan": plan["_record_id"], "stop_reason": stop, "new_responses": sent,
                            "settled_nanousd": settled, "held_nanousd": held, "finished_at": utc()})
        return self.report_cyber(session, plan)

    def report_cyber(self, session, plan):
        rows = self.rows("cyber_screen_decision")
        mapped = {r["custom_id"]: r for r in rows}
        if len(mapped) != len(rows):
            raise AuditError("cyber_duplicate_response_identity")
        attempted = set(mapped) | {r["custom_id"] for r in self.ledger.unresolved.values()}
        settled = sum(r["cost_nanousd"] for r in rows if not r["unknown_or_billing_hold"])
        held = sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values())
        path = self.ledger.root / "article-decisions.jsonl"
        temporary = path.with_suffix(".writing")
        coverage = Counter()
        article_rows = []
        with temporary.open("w", encoding="utf-8") as stream:
            for task in self.tasks(plan):
                canonical_id = task.get("canonical_custom_id", task["custom_id"])
                row = mapped.get(canonical_id)
                status = ((row.get("decision") or {}).get("status", "unknown_outcome" if row["unknown_or_billing_hold"] else "invalid") if row else
                          "unknown_outcome" if canonical_id in attempted else
                          "not_attempted" if task["disposition"] in {"ready", "exact_input_alias"} else task["disposition"])
                coverage[status] += 1
                if row:
                    article_rows.append(row)
                entry = {"custom_id": task["custom_id"], "corpus": CORPUS, "status": status,
                         "request_hash": task["request_hash"], "canonical_custom_id": canonical_id,
                         "exact_input_reuse": task["disposition"] == "exact_input_alias", "source_locator": task["descriptor"]["source_locator"],
                         "decision": row.get("decision") if row else None, "record_id": row["_record_id"] if row else None,
                         "record_owner": str(self.ledger.root), "unknown_or_billing_hold":
                         row["unknown_or_billing_hold"] if row else canonical_id in attempted,
                         "human_validated": False}
                stream.write(canonical(entry) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        result = {"plan": plan["_record_id"], "selected_articles": plan["selected_articles"],
                  "input_dispositions": plan["dispositions"], "new_responses": len(rows),
                  "not_attempted": plan["dispositions"].get("ready", 0) - len(attempted),
                  "attempts_without_response": len(attempted) - len(rows), "coverage": dict(coverage),
                  "unresolved_attempts": len(self.ledger.unresolved), "labels": core.describe(rows),
                  "article_labels_including_exact_input_aliases": core.describe(article_rows),
                  "settled_cost_usd_with_margin": settled / 1e9, "held_reservations_usd": held / 1e9,
                  "total_budget_committed_usd": (settled + held) / 1e9, "budget_usd": CAP / 1e9,
                  "run_end": self.rows("cyber_screen_run_end"),
                  "dispatch_complete": len(attempted) == plan["dispositions"].get("ready", 0),
                  "all_outcomes_resolved": not self.ledger.unresolved,
                  "article_results_path": str(path), "article_results_artifact": self.ledger.artifacts.put_file(path),
                  "human_validated": False, "accepted_dossiers": 0, "new_collection": 0}
        identifier = self.ledger.record(session, "cyber_screen_report", digest(result), result)
        self.save("screening-report.json", {"id": identifier, **result})
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "operational", "approve-operational", "run", "report", "status"])
    parser.add_argument("--workspace", type=Path, default=DEFAULT_OWNER)
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--sealed-owner", type=Path, default=DEFAULT_SEALED_OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action not in {"run", "operational"}))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "parent": str(args.parent), "sealed_owner": str(args.sealed_owner),
            "allow_paid_execution": args.allow_paid_execution}, objective="Execute the separately authorized USD20 Netherlands cybercrime screening study",
            actor="codex:cybercrime-nl-screening"), ensure_ascii=False))
    finally:
        study.close()


if __name__ == "__main__":
    main()
