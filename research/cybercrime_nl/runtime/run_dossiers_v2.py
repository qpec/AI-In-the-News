"""Registered dossier continuation; preserves v1 requests, liabilities and deadline."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

import numpy as np

import prepare_dossiers as preparation
import dossier_contract_v2 as contract
import dossier_candidates as candidates
import dossier_transport as transport
import run_dossiers as original
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, utc
from newsresearch.embeddings import offline_tokenizer
from newsresearch.runtime import audited_handler

ROOT = preparation.ROOT
METHOD = "cybercrime-four-process-dossiers-20261023-v2"
PARENT_PLAN = "99b3342e67b46d64f7e291acdda0b68a4c3be23f9660b2132dc7082818db65a2"
CAP = 50_000_000_000
PARAMETERS = {"embedding_model": "text-embedding-3-large", "dimensions": 1536,
    "chunk_tokens": 6000, "embedding_batch_inputs": 32, "embedding_batch_tokens": 100000,
    "vector_k": 40, "seed_similarity": .85, "max_seed_size": 8, "packet_tokens": 32000,
    "positive_confidence": .85, "pilot_packets": 16, "pilot_assignments": 24,
    "assignment_candidates": 5, "recovery_candidates": 15, "workers": 8,
    "embedding_tpm": 800000, "luna_tpm": 800000, "astra_tpm": 100000, "rpm": 500,
    "non_audit_cap_nanousd": 35_000_000_000, "audit_cap_nanousd": 10_000_000_000,
    "embedding_cap_nanousd": 5_000_000_000, "deadline_hours": 24,
    "pilot_reference_pairs": 12, "final_reference_pairs_per_stratum": 50}


class PipelineStop(ResearchError):
    pass


def implementation():
    paths = [Path(__file__), Path(contract.__file__), Path(candidates.__file__), Path(transport.__file__),
        Path(preparation.__file__), ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V2.md",
        ROOT / "src/newsresearch/gateway.py", ROOT / "src/newsresearch/runtime.py",
        ROOT / "src/newsresearch/storage.py", ROOT / "src/newsresearch/common.py", ROOT / "uv.lock"]
    return {**original.implementation(),
            **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def next_pilot_packets(packets, prior_documents, count=16):
    ordered = sorted(packets, key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
    excluded = set(prior_documents) | {i for p in ordered[:count] for i in p["document_ids"]}
    selected = [p for p in ordered[count:] if not excluded.intersection(p["document_ids"])][:count]
    return {"packets": selected, "excluded_document_ids": sorted(excluded),
            "excluded_initial_packet_count": min(count, len(ordered)), "selected_packet_count": len(selected),
            "rule": "Next hash-ranked packets after the original first16, excluding all previous summary-source articles; no replacement after execution."}


def reserve(packet):
    """Conservative proxy, bounded output and no assumed cache discount."""
    kind, request = packet["kind"], packet["request"]
    tokens = packet["input_tokens_proxy"]
    if kind == "embeddings":
        return math.ceil((tokens + 128) * 143 * 1.25)
    output = request.get("max_output_tokens", 0)
    incoming, outgoing = (11000, 55000) if request["model"] == "gpt-6-astra" else (110, 550)
    # Extra margin covers tokenizer mismatch, framing and possible cache writes.
    return math.ceil((tokens * 2 + 2048) * incoming * 1.25 + output * outgoing)


def billed(packet, response):
    expected = packet["request"]["model"]
    if not isinstance(response.model, str) or not (response.model == expected or response.model.startswith(expected + "-")):
        return None
    try:
        usage = transport.usage_metadata(packet["kind"], response.usage, model=expected)
    except ResearchError:
        return None
    if usage["input_tokens"] > 272000 and packet["kind"] != "embeddings":
        return None  # Contract limits should prevent long-context pricing; retain hold if violated.
    return usage["cost_nanousd_upper"]


def accounting(rows, pending):
    settled = sum(r["cost_nanousd"] or 0 for r in rows if not r["hold"])
    by_attempt = {r["attempt"]: r for r in rows}
    held = sum(max(r.get("reserved_nanousd", 0), r.get("cost_nanousd") or 0,
                   by_attempt.get(key, {}).get("cost_nanousd") or 0) for key, r in pending.items())
    return {"settled_nanousd": settled, "held_nanousd": held,
            "committed_nanousd": settled + held, "unresolved_holds": len(pending)}


def embedding_packets(documents, encoder):
    packets, batch, locators, total = [], [], [], 0

    def flush():
        nonlocal batch, locators, total
        if not batch:
            return
        request = {"model": PARAMETERS["embedding_model"], "dimensions": PARAMETERS["dimensions"],
                   "encoding_format": "float", "input": batch}
        packets.append({"phase": "embeddings", "kind": "embeddings", "request": request,
                        "input_tokens_proxy": total, "chunks": locators})
        batch, locators, total = [], [], 0

    for document in documents:
        text = canonical({"title": document["title"], "body": document["body"]})
        tokens = encoder.encode(text, disallowed_special=())
        for start in range(0, len(tokens), PARAMETERS["chunk_tokens"]):
            part = tokens[start:start + PARAMETERS["chunk_tokens"]]
            if len(batch) >= PARAMETERS["embedding_batch_inputs"] or total + len(part) > PARAMETERS["embedding_batch_tokens"]:
                flush()
            batch.append(part)
            locators.append({"document_id": document["document_id"], "token_start": start,
                             "token_end": start + len(part), "full_tokens": len(tokens),
                             "exact_input_sha256": digest({"title": document["title"], "body": document["body"]})})
            total += len(part)
    flush()
    return packets


def parse_embeddings(packet, payload):
    entries = payload.get("data", []) if isinstance(payload, dict) else []
    if len(entries) != len(packet["chunks"]) or sorted(e.get("index") for e in entries) != list(range(len(entries))):
        raise ResearchError("dossier_embedding_coverage_mismatch")
    matrix = np.asarray([e["embedding"] for e in sorted(entries, key=lambda e: e["index"])], dtype=np.float32)
    if matrix.shape != (len(entries), PARAMETERS["dimensions"]) or not np.isfinite(matrix).all() or (np.linalg.norm(matrix, axis=1) == 0).any():
        raise ResearchError("dossier_embedding_vector_invalid")
    return {"status": "valid", "vectors": matrix.tolist()}


class Study(preparation.Study):
    def init_state(self):
        self.encoder = offline_tokenizer()
        rows = self.rows("cyber_dossier_response")
        self.results = {r["task_key"]: r for r in rows}
        if len(self.results) != len(rows):
            raise AuditError("dossier_duplicate_response_task_key")
        self.phases = {r["name"]: r for r in self.rows("cyber_dossier_phase")}
        self.started = time.perf_counter()
        self.last_dispatch = 0.
        self.pacing_lock = threading.Lock()
        self.next_dispatch = {}
        self.current_phase = "preflight_complete"

    def summary_attempts(self):
        """A source-membership summary is attempted once even after a prompt amendment."""
        entries = {r["attempt"]: r for r in self.results.values() if r["phase"] == "summary"}
        for attempt, intended in self.ledger.unresolved.items():
            if intended.get("phase") == "summary":
                entries.setdefault(attempt, intended)
        versions = {}
        for attempt, row in entries.items():
            packet = self.ledger.artifacts.read(row["packet"])
            binding = packet["bindings"]
            key = (binding["dossier_id"], binding["membership_revision"])
            if key in versions:
                raise AuditError("dossier_repeated_summary_membership_attempt")
            versions[key] = {"attempt": attempt, "task_key": row["task_key"], "packet": row["packet"],
                "dossier_id": key[0], "membership_revision": key[1], "document_ids": packet["document_ids"],
                "parsed": row.get("parsed"), "hold": attempt in self.ledger.unresolved,
                "response_record": row.get("_record_id")}
        return versions

    def hold_lineage(self):
        legacy = set(self.amendment["legacy_unresolved_attempts"])
        current = set(self.ledger.unresolved)
        if not legacy <= current:
            raise AuditError("dossier_legacy_hold_was_removed")
        old = accounting(list(self.results.values()), {a: v for a, v in self.ledger.unresolved.items() if a in legacy})
        new = accounting(list(self.results.values()), {a: v for a, v in self.ledger.unresolved.items() if a not in legacy})
        if old["held_nanousd"] < self.amendment["legacy_budget"]["held_nanousd"]:
            raise AuditError("dossier_legacy_liability_reduced")
        return {"legacy_unresolved_holds": len(legacy), "new_unresolved_holds": len(current - legacy),
                "legacy_held_nanousd": old["held_nanousd"], "new_held_nanousd": new["held_nanousd"]}

    def count(self, value):
        return len(self.encoder.encode(value if isinstance(value, str) else canonical(value), disallowed_special=()))

    def task_key(self, packet):
        return digest([self.plan["_record_id"], packet["kind"], packet["request"]])

    def checkpoint(self, **extra):
        value = {"observed_at": utc(), "pid": os.getpid(), "phase": self.current_phase,
                 "execution_amendment": self.amendment["_record_id"], **self.hold_lineage(),
                 "input_manifest": self.plan["input_manifest"], "unique_documents": self.plan["unique_documents"],
                 "selected_articles": self.plan["eligible_articles"], "responses": len(self.results),
                 **accounting(list(self.results.values()), self.ledger.unresolved),
                 "cap_nanousd": CAP, "deadline": getattr(self, "deadline", None),
                 "elapsed_seconds": time.perf_counter() - self.started, **extra}
        temporary = self.ledger.root / f"progress.{os.getpid()}.tmp"
        temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
        for attempt in range(20):
            try:
                os.replace(temporary, self.ledger.root / "progress.json")
                break
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(.1)
        print(json.dumps(value), flush=True)

    @audited_handler
    def _status(self, session, context, data):
        self.init_state()
        self.plan = self.one("cyber_dossier_plan")
        if self.plan["_record_id"] != PARENT_PLAN or self.plan["implementation"] != original.implementation():
            raise AuditError("dossier_frozen_parent_implementation_changed")
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment")
        if (self.amendment["implementation"] != implementation()
                or self.amendment["parent_plan"] != self.plan["_record_id"]
                or self.amendment["original_deadline"] != self.one("cyber_dossier_first_launch")["deadline"]):
            raise AuditError("dossier_frozen_amendment_changed")
        self.hold_lineage()
        manifest = self.ledger.get(self.plan["input_manifest"], "cyber_dossier_input_manifest")
        self.document_rows = self.ledger.artifacts.read(manifest["documents_artifact"])
        self.documents = {r["document_id"]: self.ledger.artifacts.read(r["document_artifact"]) for r in self.document_rows}
        self.articles = self.ledger.artifacts.read(manifest["articles_artifact"])
        if data["action"] == "report":
            return self.report(session)
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("dossier_explicit_paid_execution_required")
        self.deadline = self.one("cyber_dossier_first_launch")["deadline"]
        self.provider = transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        try:
            if data["action"] == "pilot":
                self.pipeline(session, pilot=True)
            elif data["action"] == "run":
                gate = self.phases.get("pilot_v2_gate")
                if not gate or not self.ledger.artifacts.read(gate["artifact"])["passed"]:
                    raise PipelineStop("pilot_v2_gate_not_passed")
                self.pipeline(session, pilot=False)
            else:
                raise AuditError("dossier_unknown_action")
            stop = "phase_complete"
        except PipelineStop as error:
            stop = str(error)
            self.ledger.record(session, "cyber_dossier_stopped", digest([utc(), stop]), {
                "execution_amendment": self.amendment["_record_id"], "reason": stop, "phase": self.current_phase, "at": utc()})
        self.checkpoint(stop_reason=stop)
        return self.report(session)

    def register_amendment(self, session, context):
        if not self.config.offline:
            raise AuditError("dossier_amendment_must_be_offline")
        self.absent("cyber_dossier_execution_amendment")
        code = implementation()
        if self.plan["cap_nanousd"] != CAP or self.plan["parameters"] != PARAMETERS:
            raise AuditError("dossier_original_budget_or_parameters_changed")
        deadline = self.one("cyber_dossier_first_launch")["deadline"]
        summaries = list(self.summary_attempts().values())
        proposals = self.phase(session, "seed_proposals")
        if not proposals or not self.phase(session, "embeddings"):
            raise AuditError("dossier_v2_requires_retained_embeddings_and_seed_frame")
        selection = next_pilot_packets(proposals["packets"], {i for s in summaries for i in s["document_ids"]}, PARAMETERS["pilot_packets"])
        if len(selection["packets"]) != PARAMETERS["pilot_packets"]:
            raise AuditError("dossier_v2_insufficient_untouched_pilot_packets")
        versions = {}
        for kind, value in {
            "protocol": {"method": METHOD, "implementation": code, "parent_plan": self.plan["_record_id"],
                "registered_specification": (ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V2.md").read_text(encoding="utf-8"),
                "procedure": "Continue the same study after the first summary wave exposed incomplete output. Keep original plan IDs/task keys, source frame, embeddings, seed decisions, costs, unknown reservations, STOP and first deadline. Use short source aliases only in new summary/audit request wires and restore immutable identities after validation. Raise untouched summary output capacity to min(16000,8000+160*members), audit output to4000. Never resend any attempted summary for the same dossier_id and membership_revision, including a changed prompt. Reuse valid prior summaries, defer failed/unknown versions. Test the next16 seed packets excluding the first16 and all previous summary-source articles. New pilot/full phase names preserve old records. Gate requires zero new holds; the legacy hold remains budgeted and its source group is excluded from the continuation pilot.",
                "limitations": "Adaptive development continuation, not a new held-out validity claim. Alias normalization and software checks do not establish semantic accuracy."},
            "policy": {"method": METHOD, "total_cap_nanousd": CAP, "main_cap_nanousd": PARAMETERS["non_audit_cap_nanousd"],
                "audit_cap_nanousd": PARAMETERS["audit_cap_nanousd"], "budget_reset": False, "deadline_extended": False,
                "original_deadline": deadline, "provider_retries": 0, "summary_membership_retries": 0},
            "selection": {"rules": selection["rule"], "selected_packet_count": len(selection["packets"]),
                "input_manifest": self.plan["input_manifest"], "prior_summary_versions": len(summaries)},
            "prompt": {"instructions": "Short source aliases preserve full original article text; expand and revalidate all output source identities. Untouched requests only.",
                "contract_implementation": code[str(Path(contract.__file__).relative_to(ROOT))]},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": value})["id"]
        amendment = {"method": METHOD, "parent_plan": self.plan["_record_id"], "parent_implementation": self.plan["implementation"],
            "implementation": code, "versions": versions, "original_deadline": deadline,
            "legacy_unresolved_attempts": sorted(self.ledger.unresolved),
            "legacy_budget": accounting(list(self.results.values()), self.ledger.unresolved),
            "legacy_response_keys": sorted(self.results), "legacy_summary_versions_artifact": self.ledger.artifacts.put(summaries),
            "pilot_selection_artifact": self.ledger.artifacts.put(selection), "cap_nanousd": CAP, "at": utc()}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment", METHOD, amendment)
        return {"id": identifier, "parent_plan": self.plan["_record_id"], "original_deadline": deadline,
                "pilot_packets": len(selection["packets"]), "legacy_budget": amendment["legacy_budget"], "paid_calls": 0}

    def before_dispatch(self, invocation=None):
        if (self.ledger.root / "STOP").exists():
            raise PipelineStop("user_stop")
        if datetime.now(timezone.utc) >= datetime.fromisoformat(self.deadline):
            raise PipelineStop("deadline")
        if invocation is None:
            return
        model = invocation.request["model"]
        if invocation.kind == "embeddings":
            tokens = sum(len(v) for v in invocation.request["input"])
            tpm = PARAMETERS["embedding_tpm"]
        else:
            tokens = self.count(invocation.request) * 1.5
            tpm = PARAMETERS["astra_tpm"] if model == "gpt-6-astra" else PARAMETERS["luna_tpm"]
        with self.pacing_lock:
            delay = self.next_dispatch.get(model, 0) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.before_dispatch()  # Recheck STOP/deadline after a pacing wait.
            self.next_dispatch[model] = time.monotonic() + max(60 / PARAMETERS["rpm"], 60 * tokens / tpm)

    def phase(self, session, name, value=None):
        existing = self.phases.get(name)
        if existing:
            return self.ledger.artifacts.read(existing["artifact"])
        if value is None:
            return None
        ref = self.ledger.artifacts.put(value)
        record = {"name": name, "artifact": ref, "plan": self.plan["_record_id"],
                  "execution_amendment": self.amendment["_record_id"], "at": utc()}
        identifier = self.ledger.record(session, "cyber_dossier_phase", name, record)
        self.phases[name] = {**record, "_record_id": identifier}
        return value

    def calls(self, session, packets):
        """One attempt per exact wire request, with liabilities shared across every stage."""
        tasks = []
        seen = {v["task_key"] for v in self.ledger.unresolved.values()}
        seen.update(self.results)
        summaries = {key: value["task_key"] for key, value in self.summary_attempts().items()}
        for packet in packets:
            packet.setdefault("kind", "responses" if packet["phase"] in {"summary", "audit"} else "decisions")
            key = self.task_key(packet)
            if packet["phase"] == "summary":
                binding = packet["bindings"]
                version = (binding["dossier_id"], binding["membership_revision"])
                if version in summaries and summaries[version] != key:
                    raise AuditError("dossier_summary_version_already_attempted_no_retry")
                summaries[version] = key
            if key not in seen:
                tasks.append((key, packet))
                seen.add(key)
        self.phase_tasks_planned = len(packets)
        self.phase_tasks_completed = sum(self.task_key(p) in self.results for p in packets)
        task_set = digest(sorted(self.task_key(p) for p in packets))
        self.checkpoint(phase_tasks_planned=self.phase_tasks_planned, phase_tasks_completed=self.phase_tasks_completed,
                        phase_task_set_sha256=task_set)
        for start in range(0, len(tasks), PARAMETERS["workers"]):
            self.before_dispatch()
            wave, metadata = [], []
            for key, packet in tasks[start:start + PARAMETERS["workers"]]:
                budget = accounting(list(self.results.values()), self.ledger.unresolved)
                reservation = reserve(packet)
                is_audit = packet["request"].get("model") == "gpt-6-astra"
                category = "audit" if is_audit else "main"
                used = sum((max(r["reserved_nanousd"], r["cost_nanousd"] or 0) if r["hold"] else r["cost_nanousd"] or 0)
                           for r in self.results.values() if r["category"] == category)
                unreturned = sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values()
                                 if v.get("category") == category and v["task_key"] not in self.results)
                limit = PARAMETERS["audit_cap_nanousd"] if is_audit else PARAMETERS["non_audit_cap_nanousd"]
                if budget["committed_nanousd"] + reservation > CAP or used + unreturned + reservation > limit:
                    if not wave:
                        raise PipelineStop("budget_bound_" + category)
                    break
                attempt = str(uuid.uuid4())
                invocation = transport.Invocation(packet["request"], attempt, kind=packet["kind"])
                intended = {"attempt": attempt, "task_key": key, "number": 1, "batch": self.plan["_record_id"],
                    "execution_amendment": self.amendment["_record_id"],
                    "request": self.ledger.artifacts.put(packet["request"]), "packet": self.ledger.artifacts.put(packet),
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "phase": packet["phase"], "category": category,
                    "reserved_nanousd": reservation, "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((invocation, attempt))
                metadata.append((key, packet, intended))
            failures = 0
            for index, response in self.gateway.codex_dispatch(session, self.provider, wave, len(wave)):
                key, packet, intended = metadata[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                cost = billed(packet, response)
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intended["reserved_nanousd"]
                result, error = None, None
                if response.payload is not None:
                    try:
                        if packet["kind"] == "embeddings":
                            result = parse_embeddings(packet, response.payload)
                        elif packet["phase"] == "summary":
                            result = contract.parse_summary(packet, response.payload)
                        elif packet["phase"] == "audit":
                            result = contract.parse_audit(packet, response.payload)
                        else:
                            result = contract.parse_decisions(packet, response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as caught:
                        error = type(caught).__name__ + ":" + str(caught)[:180] if isinstance(caught, ResearchError) else type(caught).__name__
                row = {"plan": self.plan["_record_id"], "task_key": key, "phase": packet["phase"], "category": intended["category"],
                       "execution_amendment": self.amendment["_record_id"],
                       "packet": intended["packet"], "request": intended["request"], "response": response_ref, "attempt": intended["attempt"],
                       "parsed": self.ledger.artifacts.put(result) if result is not None else None,
                       "cost_nanousd": cost, "reserved_nanousd": intended["reserved_nanousd"] if hold else 0,
                       "hold": hold, "validation_error": error, "http_status": raw.get("http_status"), "at": utc()}
                identifier = self.ledger.record(session, "cyber_dossier_response", key, row)
                self.results[key] = {**row, "_record_id": identifier}
                if hold:
                    self.ledger.unresolved[intended["attempt"]]["cost_nanousd"] = cost
                else:
                    self.complete(session, intended, response_ref, identifier, "valid" if result else "invalid")
                failures += hold or result is None
            self.phase_tasks_completed = sum(self.task_key(p) in self.results for p in packets)
            self.checkpoint(phase_tasks_planned=self.phase_tasks_planned, phase_tasks_completed=self.phase_tasks_completed,
                            phase_task_set_sha256=task_set)
            if failures >= 3:
                raise PipelineStop("repeated_provider_or_validation_failure")
            if len(wave) < len(tasks[start:start + PARAMETERS["workers"]]):
                raise PipelineStop("budget_bound_partial_wave")
        return [self.parsed(packet) for packet in packets]

    def parsed(self, packet):
        row = self.results.get(self.task_key(packet))
        return self.ledger.artifacts.read(row["parsed"]) if row and row["parsed"] and not row["hold"] else None

    def vectors(self, session):
        self.current_phase = "1_embeddings"
        saved = self.phase(session, "embeddings")
        if saved:
            return saved
        packets = embedding_packets(list(self.documents.values()), self.encoder)
        if sum(reserve(p) for p in packets) > PARAMETERS["embedding_cap_nanousd"]:
            raise PipelineStop("embedding_forecast_over_allocation")
        replies = self.calls(session, packets)
        pieces = {}
        for packet, reply in zip(packets, replies, strict=True):
            if not reply:
                continue
            for locator, vector in zip(packet["chunks"], reply["vectors"], strict=True):
                pieces.setdefault(locator["document_id"], []).append((locator, vector))
        ids, vectors, missing = [], [], []
        for identifier in sorted(self.documents):
            values = sorted(pieces.get(identifier, []), key=lambda x: x[0]["token_start"])
            cursor, sums = 0, np.zeros(PARAMETERS["dimensions"], dtype=np.float64)
            for locator, vector in values:
                if locator["token_start"] != cursor:
                    break
                length = locator["token_end"] - cursor
                sums += np.asarray(vector) * length
                cursor = locator["token_end"]
            if not values or cursor != values[-1][0]["full_tokens"] or np.linalg.norm(sums) == 0:
                missing.append(identifier)
                continue
            ids.append(identifier)
            vectors.append((sums / np.linalg.norm(sums)).tolist())
        return self.phase(session, "embeddings", {"document_ids": ids, "vectors": vectors, "missing": missing,
            "purpose": "Candidate retrieval; full contiguous token coverage; similarity is not event identity."})

    def seed_results(self, session, packets, label):
        self.current_phase = "2_full_article_seed_verification_" + label
        saved = self.phase(session, label + "_seeds")
        if saved:
            return saved
        requests = [contract.seed_request([self.documents[i] for i in p["document_ids"]], count_tokens=self.count,
                                          max_tokens=PARAMETERS["packet_tokens"]) for p in packets]
        replies = self.calls(session, requests)
        pair_answers, clarity, covered = [], {}, set()
        for packet, reply in zip(requests, replies, strict=True):
            covered.update(packet["document_ids"])
            for answer in (reply or {}).get("answers", {}).values():
                if answer.get("kind") == "pair":
                    pair_answers.append(answer)
                elif answer.get("kind") == "clarity":
                    clarity[answer["document_id"]] = answer
        partition = candidates.complete_link_partition(sorted(covered), pair_answers,
                    clarity=clarity, threshold=PARAMETERS["positive_confidence"])
        groups = {digest(["seed", sorted(members)]): sorted(members) for members in partition["groups"] if len(members) > 1}
        return self.phase(session, label + "_seeds", {"groups": groups, "pair_answers": pair_answers,
            "clarity": clarity, "covered": sorted(covered), "partition": partition,
            "failed_packets": sum(r is None for r in replies), "packets": len(packets)})

    def summarize(self, session, groups, label):
        self.current_phase = "3_summaries_" + label
        saved = self.phase(session, label + "_summaries")
        if saved:
            return saved
        requests, deferred, summaries = [], [], {}
        prior = self.summary_attempts()
        for dossier, members in sorted(groups.items()):
            revision = digest(sorted(members))
            previous = prior.get((dossier, revision))
            if previous:
                if set(previous["document_ids"]) != set(members):
                    raise AuditError("dossier_prior_summary_member_conflict")
                reply = self.ledger.artifacts.read(previous["parsed"]) if previous["parsed"] and not previous["hold"] else None
                if reply and reply.get("status") == "valid":
                    if (reply["dossier_id"] != dossier or reply["membership_revision"] != revision
                            or reply["summary_version"] != digest(reply["summary"])):
                        raise AuditError("dossier_prior_summary_binding_changed")
                    contract.validate_summary(reply["summary"], [self.documents[i] for i in members])
                    summaries[dossier] = reply
                else:
                    deferred.append({"dossier_id": dossier, "membership_revision": revision,
                                     "reason": "previous_summary_attempt_unusable_no_retry", "attempt": previous["attempt"]})
                continue
            try:
                packet = contract.summary_request([self.documents[i] for i in members], dossier,
                    revision, count_tokens=self.count, max_tokens=96000,
                    max_output_tokens=min(16000, 8000 + len(members) * 160))
                packet["prior_summary_versions_for_dossier"] = [
                    {k: previous[k] for k in ("attempt", "membership_revision", "response_record")}
                    for (old_dossier, _), previous in prior.items() if old_dossier == dossier]
                requests.append(packet)
            except ResearchError as error:
                deferred.append({"dossier_id": dossier, "reason": type(error).__name__})
        replies = self.calls(session, requests)
        for request, reply in zip(requests, replies, strict=True):
            if reply and reply.get("status") == "valid":
                summaries[reply["dossier_id"]] = reply
            else:
                deferred.append({"dossier_id": request.get("bindings", {}).get("dossier_id"), "reason": "invalid_or_unknown_summary"})
        # A second independent typed decision checks groundedness against full sources.
        checks, checked = [], []
        for dossier, summary in sorted(summaries.items()):
            try:
                checks.append(contract.summary_faithfulness_request([self.documents[i] for i in groups[dossier]], summary,
                    count_tokens=self.count, max_tokens=96000))
                checked.append((dossier, summary))
            except ResearchError:
                deferred.append({"dossier_id": dossier, "reason": "faithfulness_packet_capacity"})
        judgments = self.calls(session, checks)
        usable = {}
        for (dossier, summary), reply in zip(checked, judgments, strict=True):
            answers = list((reply or {}).get("answers", {}).values())
            if len(answers) == 1 and clear(answers[0], "supported"):
                usable[dossier] = summary
            else:
                deferred.append({"dossier_id": dossier, "reason": "summary_grounding_not_clear"})
        return self.phase(session, label + "_summaries", {"usable": usable, "deferred": deferred,
            "generated": len(summaries), "human_validated": False})

    def assignments(self, session, index, document_ids, groups, summaries, label, recovery=False):
        self.current_phase = "4_summary_assignment_" + label
        saved = self.phase(session, label + "_assignments")
        if saved:
            return saved
        requests, shortlists, empty = [], {}, []
        valid_groups = {d: m for d, m in groups.items() if d in summaries}
        for identifier in document_ids:
            shortlist = candidates.shortlist_dossiers(index, identifier, valid_groups,
                limit=PARAMETERS["assignment_candidates"], recovery_limit=PARAMETERS["recovery_candidates"])
            route = shortlist["candidates"] if recovery else shortlist["primary"]
            chosen = []
            for item in route:
                dossier = item["dossier_id"] if isinstance(item, dict) else item
                if identifier not in valid_groups[dossier]:
                    chosen.append(dossier)
            chosen = chosen[:PARAMETERS["recovery_candidates"] if recovery else PARAMETERS["assignment_candidates"]]
            shortlists[identifier] = shortlist
            if not chosen:
                empty.append(identifier)
                continue
            try:
                for offset in range(0, len(chosen), PARAMETERS["assignment_candidates"]):
                    requests.append(contract.assignment_request(self.documents[identifier],
                        [summaries[d] for d in chosen[offset:offset + PARAMETERS["assignment_candidates"]]], count_tokens=self.count))
            except ResearchError:
                empty.append(identifier)
        replies = self.calls(session, requests)
        proposals, unresolved = {}, {i: "no_usable_candidate_or_packet_limit" for i in empty}
        decisions = {}
        accumulated, failed = {}, set(empty)
        for packet, reply in zip(requests, replies, strict=True):
            identifier = packet["document_ids"][0]
            answers = list((reply or {}).get("answers", {}).values())
            accumulated.setdefault(identifier, []).extend(answers)
            if reply is None:
                failed.add(identifier)
        for identifier, answers in accumulated.items():
            decisions[identifier] = answers
            clarity = [a for a in answers if a.get("kind") == "clarity"]
            matches = [a for a in answers if a.get("kind") == "assignment" and clear(a, "same_event")]
            uncertain = [a for a in answers if a.get("kind") == "assignment" and not any(clear(a, label) for label in ("same_event", "related_event", "different_event"))]
            if identifier in failed:
                unresolved[identifier] = "incomplete_candidate_evaluation"
            elif not clarity or not all(clear(a, "clear_single_event") for a in clarity):
                unresolved[identifier] = "focal_event_not_clear"
            elif len(matches) == 1 and not uncertain:
                answer = matches[0]
                expected = summaries[answer["dossier_id"]]
                if answer["summary_version"] != expected["summary_version"]:
                    raise AuditError("dossier_stale_summary_proposal")
                proposals[identifier] = {"dossier_id": answer["dossier_id"], "summary_version": answer["summary_version"],
                    "membership_revision": answer["membership_revision"],
                    "task_keys": [self.task_key(p) for p in requests if p["document_ids"][0] == identifier]}
            else:
                unresolved[identifier] = "competing_or_uncertain_candidates" if matches or uncertain else "no_match_in_shortlist"
        return self.phase(session, label + "_assignments", {"proposals": proposals, "unresolved": unresolved,
            "decisions": decisions, "shortlists": shortlists, "all_potential_matches_guaranteed": False})

    def reference(self, session, pair_ids, label):
        self.current_phase = "reference_" + label
        saved = self.phase(session, label + "_reference")
        if saved:
            return saved
        packets, retained, results = [], [], []
        for left, right in pair_ids:
            try:
                packets.append(contract.audit_request([self.documents[left], self.documents[right]], count_tokens=self.count,
                               max_output_tokens=4000))
                retained.append((left, right))
            except ResearchError:
                results.append({"left": left, "right": right, "reference": None, "available": False,
                                "reason": "reference_packet_capacity"})
        replies = self.calls(session, packets)
        for pair, reply in zip(retained, replies, strict=True):
            answer = next((a for a in (reply or {}).get("answers", {}).values() if a.get("kind") == "pair"), None)
            clarity = [a for a in (reply or {}).get("answers", {}).values() if a.get("kind") == "clarity"]
            results.append({"left": pair[0], "right": pair[1], "reference": answer, "available": answer is not None,
                            "clarity": clarity, "reference_both_clear": len(clarity) == 2 and all(a["label"] == "clear_single_event" for a in clarity)})
        return self.phase(session, label + "_reference", {"items": results, "reference_model": "gpt-6-astra",
            "blinded_to_luna": True, "human_validated": False, "sampling": label,
            "independence_limit": "Pairs may share events or articles; model reference is not adjudicated truth."})

    def pipeline(self, session, pilot):
        label = "pilot_v2" if pilot else "full_v2"
        vectors = self.vectors(session)
        if len(vectors["document_ids"]) < .99 * len(self.documents):
            raise PipelineStop("embedding_coverage_below_99_percent")
        self.current_phase = "1_candidate_retrieval"
        ids = vectors["document_ids"]
        index = candidates.build_index(ids, np.asarray(vectors["vectors"], dtype=np.float32), self.documents,
                                       vector_k=PARAMETERS["vector_k"], lexical_k=40)
        self.phase(session, "candidate_index", index.manifest())
        proposals = self.phase(session, "seed_proposals")
        if proposals is None:
            proposals = self.phase(session, "seed_proposals", candidates.propose_seed_packets(index, self.documents,
                count_tokens=self.count, cosine_threshold=PARAMETERS["seed_similarity"],
                max_articles=PARAMETERS["max_seed_size"], max_tokens=PARAMETERS["packet_tokens"]))
        packets = sorted(proposals["packets"], key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
        if pilot:
            selection = self.ledger.artifacts.read(self.amendment["pilot_selection_artifact"])
            packets = selection["packets"]
        seeds = self.seed_results(session, packets, label)
        groups = seeds["groups"]
        if pilot and not groups:
            raise PipelineStop("pilot_no_verified_seed_groups")
        summaries = self.summarize(session, groups, label + "_seed")
        members = {i for g in groups.values() for i in g}
        unclear = {i for i, answer in seeds["clarity"].items() if not clear(answer, "clear_single_event")}
        remaining = [i for i in ids if i not in members and i not in unclear]
        if pilot:
            excluded = set(selection["excluded_document_ids"])
            remaining = [i for i in remaining if i not in excluded]
            # Include likely matches rather than a random distant collection for this functional canary.
            remaining = sorted(remaining, key=lambda i: (-max((float(np.dot(index.vectors[index.positions[i]], index.vectors[index.positions[j]]))
                            for j in members), default=0), i))[:PARAMETERS["pilot_assignments"]]
        assigned = self.assignments(session, index, remaining, groups, summaries["usable"], label + "_seed")
        final_groups, applied, conflicts = commit_proposals(groups, assigned["proposals"])
        if pilot:
            group_membership = {i: d for d, group in groups.items() for i in group}
            positive_pairs = sorted({tuple(sorted((a["left"], a["right"]))) for a in seeds["pair_answers"]
                                     if clear(a, "same_event") and a["left"] in group_membership
                                     and group_membership[a["left"]] == group_membership.get(a["right"])},
                                     key=lambda pair: digest(["pilot-reference", pair]))[:PARAMETERS["pilot_reference_pairs"]]
            reference = self.reference(session, positive_pairs, "pilot_v2_positive")
            assignment_pairs = sorted({tuple(sorted((identifier, groups[value["dossier_id"]][0])))
                for identifier, value in applied.items()}, key=lambda pair: digest(["pilot-assignment-reference", pair]))[:6]
            assignment_reference = self.reference(session, assignment_pairs, "pilot_v2_assignments")
            judgments = [r["reference"] for r in reference["items"] + assignment_reference["items"]]
            same = sum(a is not None and a.get("label") == "same_event" for a in judgments)
            false_merge = sum(a is not None and a.get("label") in {"related_event", "different_event"} for a in judgments)
            summary_fraction = len(summaries["usable"]) / len(groups) if groups else 0
            reference_clarity = all(r.get("reference_both_clear", False) for r in reference["items"] + assignment_reference["items"])
            costs_by_phase = {}
            for phase_name in ("seed", "summary", "summary_faithfulness", "assignment"):
                values = [r["cost_nanousd"] for r in self.results.values()
                          if r["phase"] == phase_name and not r["hold"] and r["cost_nanousd"] is not None
                          and r["task_key"] not in self.amendment["legacy_response_keys"]]
                costs_by_phase[phase_name] = sum(values) / len(values) if values else None
            n = len(ids)
            seed_packet_count = len(proposals["packets"])
            # Deliberately pessimistic: two summary/grounding generations per original
            # input; four five-candidate assignment packets per input. Exact reuse lowers it.
            projected_main = (sum(r["cost_nanousd"] or 0 for r in self.results.values() if r["phase"] == "embeddings")
                + (costs_by_phase["seed"] or 0) * seed_packet_count
                + 2 * n * ((costs_by_phase["summary"] or 0) + (costs_by_phase["summary_faithfulness"] or 0))
                + 4 * n * (costs_by_phase["assignment"] or 0))
            forecast = {"basis": "Observed pilot usage per request, two summaries/grounding rounds and four assignment packets per input; exploratory forecast, not guaranteed cost.",
                "mean_request_cost_nanousd": costs_by_phase, "projected_main_nanousd": math.ceil(projected_main),
                "projected_total_with_full_audit_allocation_nanousd": math.ceil(projected_main) + PARAMETERS["audit_cap_nanousd"],
                "exact_admission_cap_enforced": True, "unknown_holds_included_in_current_commitment": True}
            passed = (len(judgments) >= 6 and same == len(judgments) and false_merge == 0
                      and seeds["failed_packets"] == 0 and summary_fraction >= .9
                      and bool(assignment_pairs) and reference_clarity and self.hold_lineage()["new_unresolved_holds"] == 0)
            self.phase(session, "pilot_v2_gate", {"passed": passed, "reference_pairs": len(judgments), "reference_same": same,
                "execution_amendment": self.amendment["_record_id"], **self.hold_lineage(),
                "reference_clear_false_merges": false_merge, "summary_usable_fraction": summary_fraction,
                "assignment_articles": len(assigned["decisions"]), "proposed_assignments": len(applied),
                "assignment_reference_pairs": len(assignment_pairs),
                "reference_all_articles_clear": reference_clarity,
                "cost_forecast": forecast,
                "limitation": "Small functional/model-reference gate, not a statistically established precision or recall claim."})
            self.phase(session, "pilot_v2_outcome", {"groups": final_groups, "applied": applied, "conflicts": conflicts})
            return
        # Preserve provisional single-source dossiers and use them as additional recovery references.
        assigned_ids = {i for g in final_groups.values() for i in g}
        residual = [i for i in remaining if i not in assigned_ids and assigned["unresolved"].get(i) != "focal_event_not_clear"]
        provisional = {digest(["singleton", i]): [i] for i in residual}
        singleton_summaries = self.summarize(session, provisional, "full_v2_singleton")
        # Freeze the wave's references; a summary never silently inherits new member evidence.
        updated = self.summarize(session, final_groups, "full_v2_updated_seed")
        recovery_groups = {**final_groups, **provisional}
        recovery_summaries = {**updated["usable"], **singleton_summaries["usable"]}
        recovery_ids = sorted(i for group in recovery_groups.values() for i in group)
        recovery = self.assignments(session, index, recovery_ids, recovery_groups, recovery_summaries, "full_v2_recovery", recovery=True)
        final_groups, recovery_applied, recovery_conflicts = commit_group_proposals(recovery_groups, recovery["proposals"])
        final_summaries = self.summarize(session, final_groups, "full_v2_final")
        accepted_pairs = set()
        for group in final_groups.values():
            if len(group) > 1:
                for identifier in group[1:]:
                    accepted_pairs.add(tuple(sorted((group[0], identifier))))
        selected_positive = sorted(accepted_pairs, key=lambda p: digest(["final-positive", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        self.reference(session, selected_positive, "full_v2_retained_memberships")
        membership = {i: d for d, group in final_groups.items() for i in group}
        potential_misses = []
        for pair in index.manifest()["pairs"]:
            left, right = pair["left"], pair["right"]
            if left in membership and right in membership and membership[left] != membership[right]:
                potential_misses.append((left, right))
        selected_negative = sorted(set(potential_misses), key=lambda p: digest(["final-nonjoined-candidate", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        self.reference(session, selected_negative, "full_v2_nonjoined_candidates")
        self.phase(session, "full_v2_outcome", {"groups": final_groups, "summaries": final_summaries,
            "initial_assignments": applied, "recovery_assignments": recovery_applied,
            "conflicts": {**conflicts, **recovery_conflicts}, "unclear": sorted(unclear),
            "unembedded": vectors["missing"], "human_validated": False,
            "accepted_as_scientific_findings": False, "all_potential_matches_guaranteed": False})

    def report(self, session):
        outcome = self.phase(session, "full_v2_outcome")
        gate = self.phase(session, "pilot_v2_gate")
        covered, memberships = {}, []
        if outcome:
            for dossier, group in outcome["groups"].items():
                for identifier in group:
                    if identifier in covered:
                        raise AuditError("dossier_multiple_membership")
                    covered[identifier] = dossier
            for article in self.articles:
                dossier = covered.get(article["document_id"])
                memberships.append({**article, "dossier_id": dossier,
                    "state": ("provisional_single_source" if len(outcome["groups"][dossier]) == 1 else "model_supported_group") if dossier else "unresolved",
                    "human_validated": False})
        counts = Counter(r["phase"] for r in self.results.values())
        reference_summary = {}
        for name in self.phases:
            if name.endswith("_reference"):
                value = self.phase(session, name)
                tally = Counter((item["reference"] or {}).get("label", "unavailable") for item in value["items"])
                reference_summary[name] = {"selected": len(value["items"]), "counts": dict(tally),
                    "interpretation": "Model-reference pair judgments; not independent event samples or population accuracy."}
        report = {"plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "legacy_budget_at_amendment": self.amendment["legacy_budget"], **self.hold_lineage(),
            "at": utc(), "articles": len(self.articles), "distinct_inputs": len(self.documents),
            "responses_by_phase": dict(counts), "stored_responses": len(self.results),
            **accounting(list(self.results.values()), self.ledger.unresolved), "budget_usd": 50,
            "pilot_gate": gate, "pipeline_finished": outcome is not None,
            "four_processes_complete": bool(outcome and len(outcome["summaries"]["usable"]) == len(outcome["groups"]) and len(covered) == len(self.documents)),
            "groups": len(outcome["groups"]) if outcome else None,
            "multi_article_groups": sum(len(v) > 1 for v in outcome["groups"].values()) if outcome else None,
            "unique_inputs_grouped": len(covered), "unresolved_inputs": len(self.documents) - len(covered),
            "groups_with_usable_summary": len(outcome["summaries"]["usable"]) if outcome else None,
            "article_routes": dict(Counter(r["state"] for r in memberships)),
            "memberships_artifact": self.ledger.artifacts.put(memberships) if outcome else None,
            "reference_records": {k: v["_record_id"] for k, v in self.phases.items() if k.endswith("_reference")},
            "reference_summary": reference_summary,
            "limitations": "Model-supported exploratory dossiers; screening precision, exhaustive event recall and human validity are unestablished. No text published.",
            "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results)]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identifier, **report}, indent=2), encoding="utf-8")
        return {"id": identifier, **report}


def clear(answer, label):
    if not answer or answer.get("status", "valid") != "valid" or answer.get("label") != label:
        return False
    probabilities = answer.get("probabilities") or {}
    probability = probabilities.get(label, answer.get("confidence"))
    return type(probability) in (float, int) and math.isfinite(probability) and PARAMETERS["positive_confidence"] <= probability <= 1


def commit_group_proposals(groups, proposals):
    """Every source member must support one frozen target; no moving-target chains."""
    moves, conflicts = {}, {}
    for source, members in groups.items():
        targets = {proposals[i]["dossier_id"] for i in members if i in proposals}
        if len(targets) == 1 and all(i in proposals for i in members):
            target = next(iter(targets))
            if target in groups and target != source:
                moves[source] = target
        elif targets:
            conflicts[source] = "not_all_members_support_same_target"
    result, applied, handled = {d: list(m) for d, m in groups.items()}, {}, set()
    for source, target in sorted(moves.items()):
        if source in handled:
            continue
        if target in moves:
            if moves[target] == source:
                chosen, removed = sorted((source, target))
                result[chosen] = sorted(groups[source] + groups[target])
                result.pop(removed, None)
                applied[source] = {"target": chosen, "rule": "all_members_reciprocal_group_support"}
                handled.update((source, target))
            else:
                conflicts[source] = "moving_reference_chain_or_cycle"
        else:
            result[target].extend(groups[source])
            result.pop(source, None)
            applied[source] = {"target": target, "rule": "all_members_static_reference_support"}
            handled.add(source)
    return {d: sorted(set(m)) for d, m in result.items()}, applied, conflicts


def commit_proposals(groups, proposals):
    """No chain closure: static targets, explicit mutual singleton pairs only."""
    result = {d: list(members) for d, members in groups.items()}
    owner = {i: d for d, members in groups.items() for i in members}
    applied, conflicts = {}, {}
    handled = set()
    for identifier, proposal in sorted(proposals.items()):
        if identifier in handled:
            continue
        target = proposal["dossier_id"]
        source = owner.get(identifier)
        if target not in groups or target == source or (source and len(groups[source]) != 1):
            conflicts[identifier] = "invalid_target_or_already_grouped"
            continue
        target_moves = [i for i in groups[target] if i in proposals]
        if target_moves:
            if (len(groups[target]) == 1 and len(target_moves) == 1 and source
                    and proposals[target_moves[0]]["dossier_id"] == source):
                other = target_moves[0]
                chosen = min(source, target)
                removed = max(source, target)
                result[chosen] = sorted([identifier, other])
                result.pop(removed, None)
                applied[identifier] = {**proposal, "dossier_id": chosen, "rule": "reciprocal_singleton_pair"}
                handled.update((identifier, other))
            else:
                conflicts[identifier] = "moving_reference_chain_or_cycle"
            continue
        if source:
            result.pop(source, None)
        result[target].append(identifier)
        applied[identifier] = {**proposal, "rule": "immutable_reference_wave"}
        handled.add(identifier)
    return {d: sorted(set(m)) for d, m in result.items()}, applied, conflicts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "pilot", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=preparation.OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action in {"amend", "report"}))
    try:
        result = study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Execute separately authorized USD50 four-process Cybercrime NL dossier experiment",
            actor="codex:cybercrime-dossiers")
        print(json.dumps(result), flush=True)
    finally:
        study.close()


if __name__ == "__main__":
    main()

