"""Audited full eligible-corpus Decisions screen; exact pilot questions, no retries."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, require_no_credentials, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import audited_handler
import run_luna_incident_screening_v2 as pilot

core, transport = pilot.core, pilot.transport
METHOD = "luna-decisions-full-eligible-corpus-20261021-v1"
SCREEN_PILOT = "luna-incident-screening-1000-20261020-v2"
MAX_WIRE_BYTES = 1_000_000
CHUNK_SIZE = 500
MAX_WORKERS = 16
RESERVATION = transport.RESERVATION_NANOUSD
RATE = transport.RATE_NANOUSD_PER_TOKEN
AUTHORIZATION = "Lets run this instruction on luna decision for all articles"


def implementation():
    paths = pilot.implementation()
    for path in (Path(__file__), pilot.ROOT / "scripts/audit_luna_excerpts.py"):
        paths[str(path.relative_to(pilot.ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return paths


def request_for(title, body):
    if not isinstance(title, str) or not isinstance(body, str) or not body.strip():
        raise ResearchError("body_or_title_unavailable")
    request = {"model": "gpt-6-luna", "input": canonical({"title": title, "body": body}),
               "questions": core.QUESTIONS}
    require_no_credentials(request)
    if len(canonical(request).encode("utf-8")) > MAX_WIRE_BYTES:
        raise ResearchError("full_request_exceeds_byte_cap")
    return request


@dataclass(frozen=True)
class Invocation:
    request: dict
    client_id: str

    def manifest(self):
        return {"transport": METHOD, "url": "https://api.openai.com/v1/decisions", "method": "POST",
                "wire_sha256": digest(self.request), "client_id": self.client_id,
                "automatic_retries": 0, "timeout_seconds": 60, "maximum_wire_bytes": MAX_WIRE_BYTES}


class DecisionsTransport:
    """Same one-attempt HTTP path, with a larger local byte cap for intact articles."""
    def complete_prepared(self, invocation):
        key = os.environ.get("OPENAI_API_KEY")
        if not key or any(c in key for c in "\r\n"):
            raise ResearchError("decision_key_unavailable")
        require_no_credentials(invocation.request)
        wire = canonical(invocation.request).encode("utf-8")
        if len(wire) > MAX_WIRE_BYTES:
            raise ResearchError("full_request_exceeds_byte_cap")
        request = urllib.request.Request("https://api.openai.com/v1/decisions", data=wire,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                     "X-Client-Request-Id": invocation.client_id}, method="POST")
        response = None
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), transport.NoRedirect())
            try:
                response = opener.open(request, timeout=60)
            except urllib.error.HTTPError as error:
                response = error
            status = response.status
            if type(status) is not int:
                raise ResearchError("decision_http_status_unavailable")
            raw = response.read(262145)
            if len(raw) > 262144:
                raise ResearchError("decision_response_too_large")
            text = raw.decode("utf-8")
            require_no_credentials(text)
            payload = json.loads(text)
            return ProviderResponse(payload if status == 200 else None, "openai-decisions", payload.get("model"),
                response.headers.get("x-request-id"), payload.get("usage") if status == 200 else None,
                {"http_status": status, "response_text": text, "unknown_outcome": status >= 500})
        except Exception as error:
            return ProviderResponse(None, "openai-decisions", None,
                raw_response={"unknown_outcome": True, "error_type": type(error).__name__})
        finally:
            if response is not None:
                response.close()


def prior_state(base):
    budget = pilot.prior_budget(base)
    source = pilot.Source(base / SCREEN_PILOT)
    try:
        plan = source.one("incident_screen_plan")
        report = source.one("incident_screen_report")
        rows = source.rows("incident_screen_decision")
        if (not report["dispatch_complete"] or report["unresolved_attempts"] or report["held_reservations_usd"]
                or len(rows) != report["coverage"]["valid"]):
            raise AuditError("full_pilot_not_settled")
        reused, tokens, cost = {}, 0, 0
        for row in rows:
            if (row["plan"] != plan["_record_id"] or row["unknown_or_billing_hold"] or row["reserved_nanousd"]
                    or type(row["cost_nanousd"]) is not int or row["cost_nanousd"] < 0
                    or row["decision"]["status"] != "valid"):
                raise AuditError("full_prior_result_invalid")
            request = source.artifacts.json(row["request"])
            evidence = json.loads(request["input"])
            if (request_for(evidence["title"], evidence["body"]) != request
                    or core.parse_response(source.artifacts.json(row["response"])["payload"]) != row["decision"]):
                raise AuditError("full_prior_request_or_response_changed")
            original = source.artifacts.json(row["source"])
            if (original["packet"]["source_map"]["source_fields"]["body"]["text"] != evidence["body"]
                    or original["packet"]["model_input"]["evidence"]["title"]["text"] != evidence["title"]):
                raise AuditError("full_prior_source_changed")
            if row["custom_id"] in reused:
                raise AuditError("full_prior_duplicate")
            reused[row["custom_id"]] = row
            tokens += row["input_tokens"]
            cost += row["cost_nanousd"]
        state = {"budget": budget, "screen_owner": str(source.owner), "screen_plan": plan["_record_id"],
                 "screen_report": report["_record_id"], "screen_records": [r["_record_id"] for r in rows],
                 "cost_nanousd": budget["cost_nanousd"] + cost,
                 "pilot_input_tokens": tokens, "pilot_calls": len(rows)}
        return state, reused
    finally:
        source.close()


class Study(pilot.Study):
    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        if action == "prepare":
            return self.prepare_full(session, context, data)
        plan = self.one("full_screen_plan")
        if plan["implementation"] != implementation():
            raise AuditError("full_implementation_changed")
        if action == "authorize":
            return self.authorize(session, context, plan, data)
        if action == "run":
            return self.run_full(session, plan, data)
        if action in {"status", "report"}:
            return self.report_full(session, plan)
        raise AuditError("full_unknown_action")

    def prepare_full(self, session, context, data):
        self.absent("full_screen_preparation")
        versions = {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "procedure": "Freeze all existing eligible Standard queue articles; stream exact original archive rows through the unchanged materializer. Preserve all prior source hashes and both corpus identities. Reuse valid identical pilot requests, including original decisions. Build intact title/body requests in protected chunks. Estimate input cost offline with a local tokenizer proxy calibrated to observed pilot usage, not an exact API count. Dispatch only after preparation and budget preflight, through the audited shared gateway. Never retry an attempted article. Preserve isolated unknown liabilities and continue only distinct untouched articles with reduced concurrency after an error; stop after three consecutive failed waves. Continuations retain every prior intended request, cost, hold and the first launch deadline. STOP is never removed automatically.",
                "scope": "The two exact pilot screening questions, unchanged. No added harm-type labels, source collection, old-controller restart, grouping or dossier acceptance.",
                "limits": "Inherited eligibility exclusions remain excluded. Stored body completeness is not publisher-page completeness. Model labels are provisional. Byte cap is raised from 64000 to 1000000 without changing model input content or questions; over-cap and unavailable articles remain explicit missingness. Protected held-out articles and prior extraction holds stay unchanged."},
            "question": {"text": "Classify every eligible frozen article for event scope and AI-related harm using the validated pilot instruction."},
            "selection": {"rules": "All entries of both frozen eligible Standard queues, not a sample. Stable corpus/archive/line order; no filtering on semantic outputs. No replacement or cross-corpus deduplication. Reuse only identical request hashes for the same custom_id and corpus."},
            "dossier_definition": {"unit": "One focal real-world occurrence with actual or alleged material AI-related harm; article labels do not establish dossier membership."},
            "codebook": {"labels": sorted(set(v for values in core.LABELS.values() for v in values)), "questions": core.QUESTIONS,
                         "routing": "keep if single_event AND yes; exclude if multiple_events/no_event OR no; otherwise review. Refusals review; missing inputs never negative."},
            "prompt": {"instructions": core.GENERAL, "questions": core.QUESTIONS, "input": "Exact retained title and full body, no extraction or metadata."},
            "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
            "policy": {"scope": AUTHORIZATION, "approved_by": "user:current-chat", "existing_budget_instruction": "Budget 20$",
                       "initial_total_budget_nanousd": pilot.TOTAL_BUDGET, "maximum_concurrency": MAX_WORKERS,
                       "reservation_nanousd_per_attempt": RESERVATION, "retries": 0,
                       "new_run_deadline_hours": 24, "original_deadlines_unchanged": True,
                       "price_checked": "2026-10-21", "price_source": "https://developers.openai.com/api/docs/guides/decisions",
                       "rate_nanousd_per_input_token_including_margin": RATE,
                       "long_context_threshold": 272000, "long_context_multiplier": 2}}
        bound = {k: self._version(session, context, {"kind": k, "key": METHOD, "content": v})["id"] for k, v in versions.items()}
        self.ledger.record(session, "full_screen_preparation", METHOD, {"versions": bound, "started_at": utc()})
        base = Path(data["base"]).resolve()
        previous, reuse = prior_state(base)
        source = pilot.Source(base / pilot.STANDARD)
        try:
            if not (source.owner / "STOP").is_file():
                raise AuditError("full_standard_must_remain_stopped")
            parent = source.one("luna_standard_plan")
            queues = {c: source.artifacts.json(ref) for c, ref in parent["queues"].items()}
            frame = [d for c, queue in sorted(queues.items()) for d in queue if d["corpus_id"] == c]
            if len(frame) != sum(map(len, queues.values())) or len({d["custom_id"] for d in frame}) != len(frame):
                raise AuditError("full_frame_identity_invalid")
            if not set(reuse) <= {d["custom_id"] for d in frame}:
                raise AuditError("full_reuse_outside_frame")
            provenance = {"owner": str(source.owner), "head": source.head(), "plan": parent["_record_id"],
                          "queues": parent["queues"], "partitions": {c: p["partition"] for c, p in parent["corpora"].items()}}
        finally:
            source.close()
        selection = self.ledger.record(session, "full_screen_selection", METHOD,
            {"versions": bound, "provenance": provenance, "frame_counts": {c: len(q) for c, q in queues.items()},
             "descriptors": self.ledger.artifacts.put(frame)})
        from prepare_luna_multibatch import offline_tokenizer
        encoding = offline_tokenizer()
        snapshot = pilot.materializer.core.load_contract_snapshot()
        chunks, buffer, archive_checks, reused_rows = [], [], [], []
        dispositions, by_corpus = Counter(), defaultdict(Counter)
        proxy_new, proxy_reused, long_proxy_new = 0, 0, 0
        position = 0

        def flush():
            if buffer:
                ref = self.ledger.artifacts.put(buffer)
                self.ledger.record(session, "full_screen_prepared_chunk", str(len(chunks)),
                    {"selection": selection, "artifact": ref, "count": len(buffer)})
                chunks.append({"artifact": ref, "count": len(buffer)})
                buffer.clear()

        for corpus, queue in sorted(queues.items()):
            grouped = defaultdict(dict)
            for descriptor in queue:
                loc = descriptor["source_locator"]
                if loc["line"] in grouped[loc["archive_path"]]:
                    raise AuditError("full_duplicate_archive_locator")
                grouped[loc["archive_path"]][loc["line"]] = descriptor
            partition = parent["corpora"][corpus]["partition"]
            root = Path(partition["resolved_root"]).resolve()
            for relative, wanted in sorted(grouped.items()):
                path = (root / relative).resolve(strict=True)
                hashes = {d["source_locator"]["archive_sha256"] for d in wanted.values()}
                if len(hashes) != 1 or not path.is_relative_to(root):
                    raise AuditError("full_archive_binding_invalid")
                expected = next(iter(hashes))

                def check_archive():
                    with path.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                            raise AuditError("full_archive_hash_mismatch")

                self.ledger.append(session, "full_screen.source_read.intended",
                    {"selection": selection, "corpus": corpus, "archive": relative, "sha256": expected, "rows": len(wanted)})
                check_archive()
                with zipfile.ZipFile(path) as archive:
                    if archive.namelist().count("artikelen.jsonl") != 1:
                        raise AuditError("full_archive_stream_ambiguous")
                    with archive.open("artikelen.jsonl") as stream:
                        for number, raw in enumerate(stream, 1):
                            if number not in wanted:
                                continue
                            descriptor = wanted.pop(number)
                            record = pilot.materializer.materialize.materialize_descriptor(descriptor, raw,
                                partition=partition, contract_snapshot=snapshot,
                                count_tokens=lambda text: int(descriptor["input_tokens_proxy"]) - 32)
                            packet = record["packet"]
                            title = packet["model_input"]["evidence"]["title"]["text"]
                            body = packet["source_map"]["source_fields"]["body"]["text"]
                            if hashlib.sha256(body.encode("utf-8")).hexdigest() != descriptor["retained_body_sha256"]:
                                raise AuditError("full_body_hash_mismatch")
                            position += 1
                            task = {"position": position, "custom_id": descriptor["custom_id"], "corpus": corpus,
                                    "descriptor": descriptor, "request": None, "request_hash": None, "disposition": "ready"}
                            try:
                                request = request_for(title, body)
                            except ResearchError as error:
                                if str(error) not in {"body_or_title_unavailable", "full_request_exceeds_byte_cap",
                                                       "Credential-like content is forbidden in persistent research payloads"}:
                                    raise
                                task["disposition"] = "credential_like_content" if str(error).startswith("Credential") else str(error)
                            else:
                                task.update(request=request, request_hash=digest(request))
                                proxy = len(encoding.encode(canonical(request), disallowed_special=())) + 32
                                task["input_tokens_proxy"] = proxy
                                prior = reuse.get(task["custom_id"])
                                if prior:
                                    if task["request_hash"] != prior["request"] or task["corpus"] != prior["corpus"]:
                                        raise AuditError("full_reuse_request_changed")
                                    task["disposition"] = "reused"
                                    task["prior_record"] = prior["_record_id"]
                                    reused_rows.append(prior)
                                    proxy_reused += proxy
                                else:
                                    proxy_new += proxy
                                    long_proxy_new += proxy * (2 if proxy > 272000 else 1)
                            dispositions[task["disposition"]] += 1
                            by_corpus[corpus][task["disposition"]] += 1
                            buffer.append(task)
                            if len(buffer) >= CHUNK_SIZE:
                                flush()
                            if position % 5000 == 0:
                                print(json.dumps({"phase": "preparing", "articles": position, "total": len(frame),
                                                  "dispositions": dict(dispositions)}), flush=True)
                            if not wanted:
                                break
                if wanted:
                    raise AuditError("full_archive_rows_missing")
                check_archive()
                archive_checks.append({"corpus": corpus, "archive": relative, "sha256": expected, "before_and_after": True})
            flush()
        if position != len(frame) or len(reused_rows) != len(reuse) or not proxy_reused:
            raise AuditError("full_preparation_coverage_mismatch")
        ratio = previous["pilot_input_tokens"] / proxy_reused
        forecast = long_proxy_new * ratio * RATE / 1e9
        plan = {"method": METHOD, "implementation": implementation(), "versions": bound, "selection": selection,
                "base": str(base), "prior_state": previous, "chunks": chunks, "archive_checks": archive_checks,
                "reused_rows": self.ledger.artifacts.put(reused_rows), "selected_articles": position,
                "frame_counts": {c: len(q) for c, q in queues.items()}, "dispositions": dict(dispositions),
                "by_corpus": {c: dict(v) for c, v in by_corpus.items()}, "initial_total_budget_nanousd": pilot.TOTAL_BUDGET,
                "cost_estimate": {"method": "cl100k_base_serialized_request_plus_32_scaled_by_observed_pilot_token_ratio",
                    "exact_provider_count": False, "new_input_tokens_proxy": proxy_new, "reused_input_tokens_proxy": proxy_reused,
                    "observed_to_proxy_ratio": ratio, "estimated_new_cost_usd_with_margin": forecast,
                    "estimated_total_cost_usd_with_margin": forecast + previous["cost_nanousd"] / 1e9,
                    "planning_total_usd_with_20_percent_buffer": forecast * 1.2 + previous["cost_nanousd"] / 1e9},
                "api_calls_at_preparation": 0, "human_validated": False}
        identifier = self.ledger.record(session, "full_screen_plan", METHOD, plan)
        result = {"id": identifier, **{k: plan[k] for k in ("selected_articles", "frame_counts", "dispositions", "by_corpus", "cost_estimate")},
                  "prior_cost_usd": previous["cost_nanousd"] / 1e9,
                  "remaining_authorized_usd": (pilot.TOTAL_BUDGET - previous["cost_nanousd"]) / 1e9,
                  "new_api_calls": 0}
        self.save("preparation-report.json", result)
        return result

    def save(self, name, value):
        path = self.ledger.root / name
        temporary = path.with_suffix(".writing")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    def budget(self, plan):
        amendments = self.rows("full_screen_authorization")
        return amendments[-1]["total_budget_nanousd"] if amendments else plan["initial_total_budget_nanousd"]

    def authorize(self, session, context, plan, data):
        amount = data["total_budget_usd"]
        instruction = data.get("authorization_text")
        if type(amount) not in (int, float) or not 0 < amount <= 100 or not isinstance(instruction, str) or not instruction.strip():
            raise AuditError("full_explicit_budget_instruction_required")
        content = {"plan": plan["_record_id"], "approved_by": "user:current-chat", "instruction": instruction,
                   "total_budget_nanousd": round(amount * 1e9), "retries": 0, "prior_deadlines_unchanged": True}
        version = self._version(session, context, {"kind": "policy", "key": METHOD + "-budget", "content": content,
            "amend_latest": True, "reason": "Explicit user budget decision for the prepared full-corpus run"})
        identifier = self.ledger.record(session, "full_screen_authorization", digest(content), {**content, "version": version["id"]})
        return {"id": identifier, "total_budget_usd": amount, "api_calls": 0}

    def tasks(self, plan):
        for chunk in plan["chunks"]:
            values = self.ledger.artifacts.read(chunk["artifact"])
            if len(values) != chunk["count"]:
                raise AuditError("full_chunk_count_changed")
            yield from values

    def run_full(self, session, plan, data):
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("full_explicit_online_execution_and_saved_key_required")
        if prior_state(Path(plan["base"]))[0] != plan["prior_state"]:
            raise AuditError("full_prior_budget_or_results_changed")
        launches = self.rows("full_screen_launch")
        cap = self.budget(plan)
        if plan["cost_estimate"]["planning_total_usd_with_20_percent_buffer"] > cap / 1e9:
            raise AuditError("full_prepared_forecast_exceeds_authorized_budget")
        expires = launches[0]["expires_at"] if launches else (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        if (self.ledger.root / "STOP").exists() or datetime.now(timezone.utc) >= datetime.fromisoformat(expires):
            raise AuditError("full_stopped_or_expired")
        self.ledger.record(session, "full_screen_launch", str(len(launches) + 1),
            {"plan": plan["_record_id"], "total_budget_nanousd": cap, "expires_at": expires, "started_at": utc()})
        existing = self.rows("full_screen_decision")
        attempted = {r["custom_id"] for r in existing} | {r["custom_id"] for r in self.ledger.unresolved.values()}
        ready = (task for task in self.tasks(plan) if task["disposition"] == "ready" and task["custom_id"] not in attempted)
        settled = sum(r["cost_nanousd"] for r in existing if not r["unknown_or_billing_hold"])
        held = sum(r["reserved_nanousd"] for r in self.ledger.unresolved.values())
        sent, stop, consecutive_failed_waves = len(existing), "manifest_exhausted", 0
        began = time.perf_counter()
        while True:
            if (self.ledger.root / "STOP").exists():
                stop = "user_stop"
                break
            if datetime.now(timezone.utc) >= datetime.fromisoformat(expires):
                stop = "deadline"
                break
            remaining = cap - plan["prior_state"]["cost_nanousd"] - settled - held
            workers = min(MAX_WORKERS if sent >= 16 and not consecutive_failed_waves else 4, remaining // RESERVATION)
            if workers < 1:
                stop = "budget_bound"
                break
            wave = []
            for _ in range(workers):
                task = next(ready, None)
                if task is None:
                    break
                if digest(task["request"]) != task["request_hash"]:
                    raise AuditError("full_request_hash_changed")
                request_ref = self.ledger.artifacts.put(task["request"])
                attempt = str(uuid.uuid4())
                key = digest([plan["_record_id"], task["corpus"], task["custom_id"], request_ref])
                invocation = Invocation(task["request"], attempt)
                intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": plan["_record_id"],
                    "request": request_ref, "custom_id": task["custom_id"], "corpus": task["corpus"],
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "started_at": utc(), "reserved_nanousd": RESERVATION}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((task, invocation, intended, time.perf_counter()))
            if not wave:
                break
            failure_in_wave = False
            for index, response in self.gateway.codex_dispatch(session, DecisionsTransport(),
                    [(w[1], w[2]["attempt"]) for w in wave], len(wave)):
                task, invocation, intended, started = wave[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                self.ledger.append(session, "full_screen.response.received", {"attempt": intended["attempt"], "response": response_ref})
                tokens = (response.usage or {}).get("input_tokens")
                usage_valid = type(tokens) is int and 0 <= tokens <= 1_050_000
                cost = tokens * RATE * (2 if tokens > 272000 else 1) if usage_valid else None
                decision, failure = None, None
                if response.payload is not None:
                    try:
                        decision = core.parse_response(response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError, RuntimeError) as error:
                        failure = type(error).__name__
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > RESERVATION or response.model != "gpt-6-luna"
                value = {"plan": plan["_record_id"], "custom_id": task["custom_id"], "corpus": task["corpus"],
                    "position": task["position"], "descriptor": task["descriptor"], "request": intended["request"],
                    "attempt": intended["attempt"], "response": response_ref, "decision": decision,
                    "input_tokens": tokens if usage_valid else None, "cost_nanousd": cost,
                    "reserved_nanousd": RESERVATION if hold else 0, "unknown_or_billing_hold": hold,
                    "http_status": raw.get("http_status"), "validation_error": failure, "seconds": time.perf_counter() - started}
                identifier = self.ledger.record(session, "full_screen_decision", intended["task_key"], value)
                sent += 1
                if hold:
                    held += RESERVATION
                else:
                    self.complete(session, intended, response_ref, identifier, decision["status"] if decision else "invalid")
                    settled += cost
                failure_in_wave |= hold or bool(failure) or raw.get("http_status") != 200 or not decision
            progress = {"phase": "screening", "new_responses": sent, "planned": plan["dispositions"].get("ready", 0),
                        "new_cost_usd_with_margin": settled / 1e9, "held_reservations_usd": held / 1e9,
                        "total_committed_usd": (plan["prior_state"]["cost_nanousd"] + settled + held) / 1e9,
                        "elapsed_seconds": round(time.perf_counter() - began, 2), "at": utc()}
            self.save("progress.json", progress)
            if sent <= 16 or sent % 256 < len(wave) or failure_in_wave:
                print(json.dumps(progress), flush=True)
            consecutive_failed_waves = consecutive_failed_waves + 1 if failure_in_wave else 0
            if consecutive_failed_waves >= 3:
                stop = "three_consecutive_failed_waves"
                break
            if failure_in_wave:
                time.sleep(5)
        result = {"plan": plan["_record_id"], "new_responses": sent, "stop_reason": stop,
                  "settled_nanousd": settled, "held_nanousd": held, "finished_at": utc(), "elapsed_seconds": time.perf_counter() - began}
        self.ledger.record(session, "full_screen_run_end", METHOD, result)
        return self.report_full(session, plan)

    def report_full(self, session, plan):
        new = self.rows("full_screen_decision")
        reused = self.ledger.artifacts.read(plan["reused_rows"])
        if len({r["custom_id"] for r in new + reused}) != len(new) + len(reused):
            raise AuditError("full_report_duplicate_identity")
        settled = sum(r["cost_nanousd"] for r in new if not r["unknown_or_billing_hold"])
        held = sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values())
        attempted = {r["custom_id"] for r in new} | {r["custom_id"] for r in self.ledger.unresolved.values()}
        all_rows = {r["custom_id"]: r for r in reused + new}
        export_path = self.ledger.root / "article-decisions.jsonl"
        temporary = export_path.with_suffix(".writing")
        with temporary.open("w", encoding="utf-8") as stream:
            for task in self.tasks(plan):
                row = all_rows.get(task["custom_id"])
                status = ((row.get("decision") or {}).get("status", "invalid") if row else
                          "unknown_outcome" if task["custom_id"] in attempted else
                          "not_attempted" if task["disposition"] == "ready" else task["disposition"])
                entry = {"custom_id": task["custom_id"], "corpus": task["corpus"], "status": status,
                    "reused": task["disposition"] == "reused", "request_hash": task["request_hash"],
                    "source_locator": task["descriptor"]["source_locator"],
                    "decision": row.get("decision") if row else None,
                    "record_id": row["_record_id"] if row else None,
                    "record_owner": plan["prior_state"]["screen_owner"] if task["disposition"] == "reused" else str(self.ledger.root),
                    "unknown_or_billing_hold": row["unknown_or_billing_hold"] if row else task["custom_id"] in attempted,
                    "human_validated": False}
                stream.write(canonical(entry) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, export_path)
        export_ref = self.ledger.artifacts.put_file(export_path)
        result = {"plan": plan["_record_id"], "selected_articles": plan["selected_articles"],
            "input_dispositions": plan["dispositions"], "reused_results": len(reused), "new_responses": len(new),
            "not_attempted": plan["dispositions"].get("ready", 0) - len(attempted),
            "attempts_without_response": len(attempted) - len(new),
            "new_valid_results": sum((r.get("decision") or {}).get("status") == "valid" for r in new),
            "unresolved_attempts": len(self.ledger.unresolved), "labels": core.describe(reused + new),
            "by_corpus": {c: core.describe([r for r in reused + new if r["corpus"] == c]) for c in plan["frame_counts"]},
            "new_input_tokens_observed": sum(r["input_tokens"] or 0 for r in new),
            "new_cost_usd_with_margin": settled / 1e9, "held_reservations_usd": held / 1e9,
            "total_budget_committed_usd": (plan["prior_state"]["cost_nanousd"] + settled + held) / 1e9,
            "budget_usd": self.budget(plan) / 1e9, "run_end": self.rows("full_screen_run_end"),
            "dispatch_complete": len(new) == plan["dispositions"].get("ready", 0) and not self.ledger.unresolved,
            "article_results_path": str(export_path), "article_results_artifact": export_ref,
            "human_validated": False, "accepted_dossiers": 0, "new_collection": 0}
        identifier = self.ledger.record(session, "full_screen_report", digest(result), result)
        self.save("screening-report.json", {"id": identifier, **result})
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "authorize", "run", "report", "status"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=pilot.BASE)
    parser.add_argument("--allow-paid-execution", action="store_true")
    parser.add_argument("--total-budget-usd", type=float)
    parser.add_argument("--authorization-text")
    args = parser.parse_args()
    engine = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        data = {**vars(args), "workspace": str(args.workspace), "base": str(args.base)}
        print(json.dumps(engine.execute("status", data,
            objective="Apply the same two-question Luna Decisions screen to the entire frozen eligible corpus within the user's budget",
            actor="codex:luna-decisions-full-corpus"), ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
