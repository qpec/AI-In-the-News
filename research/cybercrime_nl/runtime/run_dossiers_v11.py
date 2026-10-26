"""Prospective cumulative-budget and deadline continuation of the exact v9 pipeline."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import timedelta
import uuid
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import run_dossiers_v9 as parent
import run_dossiers_v10 as deadline
import run_dossiers_v6 as pilot
from newsresearch.common import AuditError, Config, ResearchError, digest, require_no_credentials, utc
from newsresearch.runtime import audited_handler

BASE, ROOT, CAP = parent.BASE, parent.ROOT, parent.CAP
PipelineStop = parent.PipelineStop
METHOD = "cybercrime-four-process-dossiers-20261023-v11"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V11.md"
DEADLINE_POLICY = {"version": "user-authorized-frozen-pipeline-completion-v1",
    "mode": "finish_frozen_pipeline_within_existing_guards", "effective_admission_deadline": None,
    "original_deadline_immutable": True, "budget_reset": False, "provider_retries": 0}
HEALTH_SCOPE = "All outcomes under the v9 operational policy, including this cumulative-budget and deadline continuation; the original v9 health baseline is preserved."
PRESERVED = ("parent_plan", "original_deadline", "passed_pilot_report", "passed_gate_record", "seed_capacity_census",
    "seed_packet_plan_artifact", "seed_proposals_sha256", "v6_pilot_budget_baseline", "derived_revalidation_records",
    "seed_order_integrity", "operational_policy", "transport_observability", "contingency_nanousd")
HISTORICAL_CAPS = {"total": 50_000_000_000, "main": 35_000_000_000, "audit": 15_000_000_000}
BUDGET_POLICY_VERSION = "cumulative-user-budget-amendment-v1"


def require(value, message):
    if not value:
        raise AuditError("dossier_v11_" + message)


def implementation():
    paths = [Path(__file__), METHOD_DOCUMENT, ROOT / "research/cybercrime_nl/runtime/run_dossiers_v11_with_key.ps1"]
    return {**deadline.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def parse_authorization(raw):
    """Exact user instruction and available source metadata, never invented time."""
    value = json.loads(raw.decode("utf-8"))
    require(isinstance(value, dict) and set(value) == {"instruction", "source_reference", "source_timestamp"}
        and all(isinstance(value[k], str) and value[k].strip() for k in ("instruction", "source_reference")), "authorization_shape")
    if value["source_timestamp"] is not None:
        require(isinstance(value["source_timestamp"], str), "authorization_timestamp")
        require(datetime.fromisoformat(value["source_timestamp"]).tzinfo is not None, "authorization_timezone_missing")
    require_no_credentials(value)
    return value


def parse_budget_authorization(raw):
    """Retain the numeric allocation and exact human evidence; never infer a choice."""
    value = json.loads(raw.decode("utf-8"))
    require(isinstance(value, dict) and set(value) == {
        "instruction", "source_reference", "source_timestamp", "caps_nanousd"}, "budget_evidence_shape")
    parse_authorization(json.dumps({k: v for k, v in value.items() if k != "caps_nanousd"}).encode())
    caps = value["caps_nanousd"]
    require(isinstance(caps, dict) and set(caps) == set(HISTORICAL_CAPS)
        and all(type(caps[k]) is int and HISTORICAL_CAPS[k] <= caps[k] for k in caps)
        and caps["main"] + caps["audit"] == caps["total"]
        and caps["total"] > HISTORICAL_CAPS["total"], "budget_allocation_invalid")
    require_no_credentials(value)
    return value


def budget_policy(caps):
    return {"version": BUDGET_POLICY_VERSION, "historical_caps_nanousd": HISTORICAL_CAPS,
        "effective_caps_nanousd": caps, "cumulative": True, "reset_costs_or_holds": False,
        "automatic_reallocation": False, "new_models_or_questions_authorized": False}


class Study(deadline.Study):
    @audited_handler
    def _status(self, session, context, data):
        self._deadline_policy_enabled, self._loading_v9 = False, True
        try:
            parent.Study._status(self, session, context, {"action": "report"})
        finally:
            self._loading_v9 = False
        self.v9_amendment = self.amendment
        require(self.v9_amendment["method"] == parent.METHOD, "parent_method_mismatch")
        if data["action"] == "amend":
            return self.register_budget_amendment(session, context, data)
        self.amendment = self.one("cyber_dossier_execution_amendment_v11")
        self.validate_amendment()
        self.hold_lineage()
        self._deadline_policy_enabled, self._v9_active, self._operational_cache = True, True, {}
        cohort = set(self.amendment["health_ancestor_amendments"]) | {self.amendment["_record_id"]}
        continuations = [r for r in self.rows("cyber_dossier_operational_continuation") if r["execution_amendment"] in cohort]
        self._legacy_continuations = len(continuations)
        self._cooldown_until = continuations[-1]["cooldown_until"] if continuations else None
        self.deadline = None
        if data["action"] == "report":
            return self.report(session)
        require(data["action"] == "run" and not self.config.offline and data.get("allow_paid_execution")
                and os.environ.get("OPENAI_API_KEY"), "explicit_paid_execution_required")
        self.provider = parent.observed_transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        try:
            if not self.phase(session, "pilot_v6_gate")["passed"]:
                raise PipelineStop("pilot_v6_gate_not_passed")
            self.check_operational_guard()
            self.full_pipeline(session)
            stop = "phase_complete"
        except PipelineStop as error:
            stop = str(error)
            self.ledger.record(session, "cyber_dossier_stopped", digest([utc(), stop]), {
                "execution_amendment": self.amendment["_record_id"], "reason": stop, "phase": self.current_phase, "at": utc()})
        self.checkpoint(stop_reason=stop)
        return self.report(session)

    def validate_amendment(self):
        amendment, old = self.amendment, self.v9_amendment
        require(amendment["implementation"] == implementation() and amendment["parent_implementation"] == parent.implementation()
            and amendment["parent_execution_amendment"] == old["_record_id"]
            and amendment["operational_origin_amendment"] == old["_record_id"]
            and amendment["health_ancestor_amendments"] == [old["_record_id"]]
            and amendment["operational_health_baseline_unresolved_attempts"] == old["legacy_unresolved_attempts"]
            and amendment["deadline_policy"] == DEADLINE_POLICY and amendment["effective_admission_deadline"] is None
            and all(amendment[k] == old[k] for k in PRESERVED), "amendment_binding_mismatch")
        report = self.ledger.get(amendment["parent_report"], "cyber_dossier_report")
        require(report["execution_amendment"] == old["_record_id"] and report["technical_extension_version"] == 9
            and report["plan"] == self.plan["_record_id"], "bound_parent_report_changed")
        authorization = amendment["deadline_authorization"]
        raw = self.ledger.artifacts.read_bytes(authorization["artifact"])
        parsed = parse_authorization(raw)
        require(hashlib.sha256(raw).hexdigest() == authorization["sha256"]
                and parsed["source_reference"] == authorization["source_reference"]
                and parsed["source_timestamp"] == authorization["source_timestamp"], "authorization_changed")
        policy = self.ledger.get(amendment["versions"]["policy"], "policy")
        require(policy["content"]["deadline_policy"] == DEADLINE_POLICY
            and policy["content"]["deadline_evidence"] == authorization
            and policy["content"]["parent_execution_amendment"] == old["_record_id"], "authorization_policy_changed")
        budget_evidence = amendment["budget_authorization"]
        raw = self.ledger.artifacts.read_bytes(budget_evidence["artifact"])
        parsed = parse_budget_authorization(raw)
        caps = parsed["caps_nanousd"]
        require(hashlib.sha256(raw).hexdigest() == budget_evidence["sha256"]
            and all(parsed[k] == budget_evidence[k] for k in ("source_reference", "source_timestamp", "caps_nanousd"))
            and amendment["budget_policy"] == budget_policy(caps)
            and amendment["cap_nanousd"] == caps["total"]
            and amendment["main_cap_nanousd"] == caps["main"] and amendment["audit_cap_nanousd"] == caps["audit"]
            and policy["content"]["budget_policy"] == amendment["budget_policy"]
            and policy["content"]["budget_evidence"] == budget_evidence, "budget_evidence_changed")
        protocol = self.ledger.get(amendment["versions"]["protocol"], "protocol")["content"]
        require(protocol["method"] == METHOD and protocol["implementation"] == implementation(), "protocol_changed")

    def register_budget_amendment(self, session, context, data):
        require(self.config.offline and data.get("parent_report") and data.get("authorization_file")
            and data.get("budget_authorization_file"), "offline_explicit_registration_required")
        self.absent("cyber_dossier_execution_amendment_v11")
        self.absent("cyber_dossier_execution_amendment_v10")
        self.hold_lineage()
        reports = self.rows("cyber_dossier_report")
        require(reports and reports[-1]["_record_id"] == data["parent_report"], "latest_stopped_parent_report_required")
        report = reports[-1]
        budget = BASE.accounting(list(self.results.values()), self.ledger.unresolved)
        require(report["execution_amendment"] == self.v9_amendment["_record_id"] and report["technical_extension_version"] == 9
            and report["plan"] == self.plan["_record_id"] and report["stored_responses"] == len(self.results)
            and report["pilot_gate"] == self.phase(session, "pilot_v6_gate") and report["pilot_gate"]["passed"]
            and all(budget[k] == report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")),
            "stopped_parent_state_changed")
        raw = Path(data["authorization_file"]).read_bytes()
        evidence = parse_authorization(raw)
        authorization = {"artifact": self.ledger.artifacts.put_bytes(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "source_reference": evidence["source_reference"], "source_timestamp": evidence["source_timestamp"], "registered_at": utc()}
        raw_budget = Path(data["budget_authorization_file"]).read_bytes()
        numeric = parse_budget_authorization(raw_budget)
        caps = numeric["caps_nanousd"]
        old_caps = {"total": self.v9_amendment["cap_nanousd"], "main": self.v9_amendment["main_cap_nanousd"],
                    "audit": self.v9_amendment["audit_cap_nanousd"]}
        require(old_caps == HISTORICAL_CAPS, "historical_caps_changed")
        categories = parent.Study.category_budget(self)
        require(budget["committed_nanousd"] <= caps["total"]
            and all(categories[k]["committed_nanousd"] <= caps[k] for k in ("main", "audit")), "new_caps_below_liabilities")
        budget_evidence = {"artifact": self.ledger.artifacts.put_bytes(raw_budget), "sha256": hashlib.sha256(raw_budget).hexdigest(),
            **{k: numeric[k] for k in ("source_reference", "source_timestamp", "caps_nanousd")}, "registered_at": utc()}
        allocation = budget_policy(caps)
        code = implementation()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
                "procedure": "User-authorized cumulative budget and no-date continuation of the same frozen queue. Preserve original cutoff/allocation, all costs/holds, requests/parsers, STOP, no retry and durable v9 health/cooldown. Only immutable numeric evidence supplies effective caps; no reset or automatic reallocation."},
            "policy": {"deadline_policy": DEADLINE_POLICY, "deadline_evidence": authorization,
                "parent_execution_amendment": self.v9_amendment["_record_id"], "original_deadline": self.v9_amendment["original_deadline"],
                "budget_policy": allocation, "budget_evidence": budget_evidence,
                "cap_nanousd": caps["total"], "new_models_or_questions_authorized": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        amendment = {**{k: v for k, v in self.v9_amendment.items() if not k.startswith("_")},
            "method": METHOD, "parent_execution_amendment": self.v9_amendment["_record_id"], "parent_report": report["_record_id"],
            "parent_implementation": parent.implementation(), "implementation": code, "versions": versions,
            "ancestor_execution_amendments": {**self.v9_amendment["ancestor_execution_amendments"], "v9": self.v9_amendment["_record_id"]},
            "deadline_policy": DEADLINE_POLICY, "effective_admission_deadline": None, "deadline_authorization": authorization,
            "budget_policy": allocation, "budget_authorization": budget_evidence,
            "cap_nanousd": caps["total"], "main_cap_nanousd": caps["main"], "audit_cap_nanousd": caps["audit"],
            "operational_origin_amendment": self.v9_amendment["_record_id"], "health_ancestor_amendments": [self.v9_amendment["_record_id"]],
            "operational_health_baseline_unresolved_attempts": self.v9_amendment["legacy_unresolved_attempts"],
            "legacy_budget": budget, "legacy_unresolved_attempts": sorted(self.ledger.unresolved),
            "legacy_category_budget": categories,
            "legacy_response_keys": sorted(self.results), "at": utc()}
        identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v11", METHOD, amendment)
        return {"id": identity, "parent_plan": self.plan["_record_id"], "parent_report": report["_record_id"],
            "original_deadline": amendment["original_deadline"], "effective_admission_deadline": None,
            "deadline_policy": DEADLINE_POLICY, "deadline_authorization": authorization, "legacy_budget": budget,
            "budget_policy": allocation, "budget_authorization": budget_evidence, "legacy_category_budget": categories,
            "operational_origin_amendment": amendment["operational_origin_amendment"], "paid_calls": 0}

    def calls(self, session, packets):
        # Exact v9 continuation, v8 local ordering repair and v6 pilot guards.
        while True:
            before = len(self.results)
            self.check_operational_guard()
            self.wait_cooldown()
            try:
                normalized = [parent.parent.normalize_seed_packet(p) if p["phase"] == "seed" else p for p in packets]
                return self._pilot_calls(session, normalized)
            except PipelineStop as error:
                if str(error) != "repeated_provider_or_validation_failure":
                    raise
                require(len(self.results) > before, "legacy_guard_without_response_progress")
                current = self.check_operational_guard()
                cooldown = (datetime.now(timezone.utc) + timedelta(seconds=parent.POLICY["legacy_guard_cooldown_seconds"])).isoformat()
                self.ledger.record(session, "cyber_dossier_operational_continuation", digest([utc(), len(self.results)]), {
                    "execution_amendment": self.amendment["_record_id"], "phase": self.current_phase,
                    "responses_before": before, "responses_after": len(self.results), "health": current,
                    "reason": "isolated_mixed_wave_untouched_work_continues", "cooldown_until": cooldown, "at": utc()})
                self._legacy_continuations += 1
                self._cooldown_until = cooldown

    def _pilot_calls(self, session, packets):
        if not getattr(self, "pilot_task_keys", set()).intersection(self.task_key(p) for p in packets):
            return self._calls_with_budget(session, packets)
        replies = []
        for packet in packets:
            key = self.task_key(packet)
            seen = key in self.results or any(v["task_key"] == key for v in self.ledger.unresolved.values())
            if key in self.pilot_task_keys and not seen:
                category = "audit" if packet["request"]["model"] == "gpt-6-astra" else "main"
                budget = self.pilot_budget(category)
                cap = pilot.PILOT_AUDIT_CAP if category == "audit" else pilot.PILOT_MAIN_CAP
                if budget["committed_nanousd"] + BASE.reserve(packet) > cap:
                    raise PipelineStop("v6_pilot_subcap_" + category)
            replies.extend(self._calls_with_budget(session, [packet]))
            if key in self.pilot_task_keys and replies[-1] is None:
                raise PipelineStop("v6_pilot_new_unknown_or_invalid")
        return replies

    def _calls_with_budget(self, session, packets):
        """One attempt per exact wire request, with liabilities shared across every stage."""
        caps = self.amendment["budget_policy"]["effective_caps_nanousd"]
        tasks = []
        seen = {v["task_key"] for v in self.ledger.unresolved.values()}
        seen.update(self.results)
        seed_attempts = self.seed_attempts()
        audit_attempts = self.article_set_attempts("audit")
        for packet in packets:
            if packet["phase"] == "summary":
                raise AuditError("dossier_v5_generation_prohibited")
            packet.setdefault("kind", "responses" if packet["phase"] in {"audit", "card_quality", "card_quality_audit"} else "decisions")
            key = self.task_key(packet)
            if packet["phase"] == "seed":
                old = seed_attempts.get(tuple(sorted(packet["document_ids"])))
                if old and self.task_key(old) != key:
                    raise AuditError("dossier_seed_article_set_already_attempted_no_retry")
                seed_attempts[tuple(sorted(packet["document_ids"]))] = packet
            if packet["phase"] == "audit":
                old = audit_attempts.get(tuple(sorted(packet["document_ids"])))
                if old and self.task_key(old) != key:
                    raise AuditError("dossier_audit_article_set_already_attempted_no_retry")
                audit_attempts[tuple(sorted(packet["document_ids"]))] = packet
            if key not in seen:
                tasks.append((key, packet))
                seen.add(key)
        self.phase_tasks_planned = len(packets)
        self.phase_tasks_completed = sum(self.task_key(p) in self.results for p in packets)
        task_set = digest(sorted(self.task_key(p) for p in packets))
        self.checkpoint(phase_tasks_planned=self.phase_tasks_planned, phase_tasks_completed=self.phase_tasks_completed,
                        phase_task_set_sha256=task_set)
        for start in range(0, len(tasks), BASE.PARAMETERS["workers"]):
            self.before_dispatch()
            wave, metadata = [], []
            for key, packet in tasks[start:start + BASE.PARAMETERS["workers"]]:
                budget = BASE.accounting(list(self.results.values()), self.ledger.unresolved)
                reservation = BASE.reserve(packet)
                is_audit = packet["request"].get("model") == "gpt-6-astra"
                category = "audit" if is_audit else "main"
                used = sum((max(r["reserved_nanousd"], r["cost_nanousd"] or 0) if r["hold"] else r["cost_nanousd"] or 0)
                           for r in self.results.values() if r["category"] == category)
                unreturned = sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values()
                                 if v.get("category") == category and v["task_key"] not in self.results)
                limit = caps[category]
                if budget["committed_nanousd"] + reservation > caps["total"] or used + unreturned + reservation > limit:
                    if not wave:
                        raise PipelineStop("budget_bound_" + category)
                    break
                attempt = str(uuid.uuid4())
                invocation = BASE.transport.Invocation(packet["request"], attempt, kind=packet["kind"])
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
                cost = BASE.billed(packet, response)
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intended["reserved_nanousd"]
                result, error = None, None
                http_ok = 200 <= (raw.get("http_status") or 0) < 300
                if response.payload is not None and http_ok:
                    try:
                        if packet["kind"] == "embeddings":
                            result = BASE.parse_embeddings(packet, response.payload)
                        elif packet["phase"] == "audit":
                            result = BASE.contract.parse_audit(packet, response.payload)
                        elif packet["phase"] == "card_quality":
                            result = BASE.contract.parse_card_quality(packet, response.payload)
                        elif packet["phase"] == "card_quality_audit":
                            result = BASE.contract.parse_card_quality_audit(packet, response.payload)
                        else:
                            result = BASE.contract.parse_decisions(packet, response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as caught:
                        error = type(caught).__name__ + ":" + str(caught)[:180] if isinstance(caught, ResearchError) else type(caught).__name__
                elif not http_ok:
                    error = "dossier_http_not_success"
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
            if len(wave) < len(tasks[start:start + BASE.PARAMETERS["workers"]]):
                raise PipelineStop("budget_bound_partial_wave")
        return [self.parsed(packet) for packet in packets]

    def before_dispatch(self, invocation=None):
        if not getattr(self, "_deadline_policy_enabled", False):
            return super().before_dispatch(invocation)
        # Exact inherited STOP and pacing behavior, with only the date condition removed.
        if (self.ledger.root / "STOP").exists():
            raise PipelineStop("user_stop")
        if invocation is None:
            return
        model = invocation.request["model"]
        if invocation.kind == "embeddings":
            tokens = sum(len(v) for v in invocation.request["input"])
            tpm = BASE.PARAMETERS["embedding_tpm"]
        else:
            tokens = self.count(invocation.request) * 1.5
            tpm = BASE.PARAMETERS["astra_tpm"] if model == "gpt-6-astra" else BASE.PARAMETERS["luna_tpm"]
        with self.pacing_lock:
            delay = self.next_dispatch.get(model, 0) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.before_dispatch()
            self.next_dispatch[model] = time.monotonic() + max(60 / BASE.PARAMETERS["rpm"], 60 * tokens / tpm)

    def operational_health(self):
        if not getattr(self, "_deadline_policy_enabled", False):
            return super().operational_health()
        cohort = set(self.amendment["health_ancestor_amendments"]) | {self.amendment["_record_id"]}
        outcomes = []
        for key, row in self.results.items():
            if row.get("execution_amendment") not in cohort:
                continue
            if key not in self._operational_cache:
                self._operational_cache[key] = parent.classify_outcome(row, self.ledger.artifacts.read(row["packet"]),
                    self.ledger.artifacts.read(row["response"]))
            outcomes.append(self._operational_cache[key])
        for item in self.ledger.unresolved.values():
            if item.get("execution_amendment") in cohort and item["task_key"] not in self.results:
                outcomes.append({"at": item["started_at"], "failed": True, "transport_unknown": True,
                    "held": True, "parsed": False, "unreturned": True, "fatal": None})
        value = parent.health(outcomes)
        cooldown = getattr(self, "_cooldown_until", None)
        waiting = bool(cooldown and datetime.now(timezone.utc) < datetime.fromisoformat(cooldown))
        return {**value, "scope": HEALTH_SCOPE, "legacy_guard_continuations": self._legacy_continuations,
            "baseline_unresolved_holds": len(self.amendment["operational_health_baseline_unresolved_attempts"]),
            "operational_status": "stopped" if value["guard_reason"] else "cooldown" if waiting else "ready",
            "cooldown_until": cooldown}

    def deadline_metadata(self):
        return {"original_deadline": self.amendment["original_deadline"], "effective_admission_deadline": None,
            "deadline_policy": DEADLINE_POLICY, "deadline_authorization_policy": self.amendment["versions"]["policy"],
            "operational_origin_amendment": self.amendment["operational_origin_amendment"],
            "health_response_amendments": [*self.amendment["health_ancestor_amendments"], self.amendment["_record_id"]]}

    def checkpoint(self, **extra):
        if getattr(self, "_deadline_policy_enabled", False):
            extra.update(self.deadline_metadata())
            extra.update(self.budget_metadata())
        return super().checkpoint(**extra)

    def budget_metadata(self):
        policy = self.amendment["budget_policy"]
        return {"budget_policy": policy, "historical_caps_nanousd": policy["historical_caps_nanousd"],
            "effective_caps_nanousd": policy["effective_caps_nanousd"],
            "cap_nanousd": policy["effective_caps_nanousd"]["total"],
            "budget_authorization_policy": self.amendment["versions"]["policy"]}

    def category_budget(self):
        if not getattr(self, "_deadline_policy_enabled", False):
            return parent.Study.category_budget(self)
        caps = self.amendment["budget_policy"]["effective_caps_nanousd"]
        result = {}
        for category in ("main", "audit"):
            rows = [r for r in self.results.values() if r["category"] == category]
            pending = {a: r for a, r in self.ledger.unresolved.items() if r.get("category") == category}
            budget = BASE.accounting(rows, pending)
            result[category] = {**budget, "cap_nanousd": caps[category],
                "remaining_nanousd": max(0, caps[category] - budget["committed_nanousd"])}
        return result

    def report(self, session):
        if getattr(self, "_loading_v9", False):
            return None
        previous = parent.Study.report(self, session)
        report = {k: v for k, v in previous.items() if k != "id"}
        report.update(parent_report=self.amendment["parent_report"], technical_extension_version=11,
            base_report_record=previous["id"], **self.deadline_metadata(), **self.budget_metadata(),
            budget_usd=self.amendment["cap_nanousd"] / 1_000_000_000,
            historical_budget_usd=CAP / 1_000_000_000)
        identity = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results), METHOD]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identity, **report}, indent=2), encoding="utf-8")
        return {"id": identity, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=BASE.preparation.OWNER)
    parser.add_argument("--parent-report")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--budget-authorization-file", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution,
            "parent_report": args.parent_report, "authorization_file": str(args.authorization_file) if args.authorization_file else None,
            "budget_authorization_file": str(args.budget_authorization_file) if args.budget_authorization_file else None},
            objective="Register or continue the same dossier pipeline under exact cumulative-budget and deadline authority", actor="codex:cybercrime-dossiers")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
