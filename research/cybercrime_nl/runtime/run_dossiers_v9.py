"""Registered operational continuation, with unchanged research requests/parsers."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import dossier_transport_v9 as observed_transport
import run_dossiers_v8 as parent
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import audited_handler

BASE, ROOT, CAP = parent.BASE, parent.ROOT, parent.CAP
PipelineStop = parent.PipelineStop
METHOD = "cybercrime-four-process-dossiers-20261023-v9"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V9.md"
PARENT_AMENDMENT = "05c1d6dfb30ff428d38a1e04f81d50625030089c3755eeb5735e5e87dc528a7e"
PARENT_REPORT = "92bf8d1677746097fa68fffec142a647b435507efa58bffdbce593e92e5b14f4"
DIAGNOSTIC = "d3ffce1597571dd687845da0b8880290ad94bd50d2f58f7b0822d8869bb53bbd"
DIAGNOSTIC_OWNER = BASE.preparation.OWNER.parent / "cybercrime-v8-failure-technical-view-20261023-v2"
POLICY = {"version": "settled-wave-continuation-with-durable-health-v1", "window": 32,
    "consecutive_failure_limit": 8, "window_transport_unknown_limit": 8, "window_failure_limit": 16,
    "automatic_provider_retries": 0, "automatic_process_restarts": 0,
    "baseline_holds_excluded_from_new_health_window": True, "legacy_guard_cooldown_seconds": 30}
FATAL_HTTP = {400, 401, 403, 404, 405, 413, 415, 422}
FATAL_TRANSPORT = {"request_preflight_rejected", "dispatch_stopped", "redirect_rejected", "http_status_unavailable", "response_byte_capacity"}
FATAL_VALIDATION = {"dossier_card_decision_binding_mismatch", "dossier_card_quality_binding_mismatch",
    "dossier_card_audit_binding_mismatch", "dossier_decision_model_or_request_mismatch", "dossier_card_binding_mismatch",
    "dossier_card_sources_changed", "dossier_card_membership_binding", "dossier_document_hash_mismatch",
    "dossier_input_hash_mismatch", "dossier_pair_not_in_packet_or_repeated", "dossier_passage_expansion_mismatch",
    "dossier_card_decision_phase_invalid", "dossier_card_control_type_mismatch"}


def require(value, message):
    if not value:
        raise AuditError("dossier_v9_" + message)


def implementation():
    paths = [Path(__file__), Path(observed_transport.__file__), METHOD_DOCUMENT,
             ROOT / "research/cybercrime_nl/runtime/run_dossiers_v9_with_key.ps1"]
    return {**parent.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def classify_outcome(row, packet, envelope):
    """Fixed technical categories only; no labels/prose or payload repairs."""
    raw = envelope.get("raw_response") or {}
    status, code = raw.get("http_status"), raw.get("failure_code")
    error = row.get("validation_error") or ""
    model, expected = envelope.get("model"), packet["request"]["model"]
    fatal = None
    if status in FATAL_HTTP:
        fatal = "http_auth_configuration_or_request"
    elif code in FATAL_TRANSPORT:
        fatal = "transport_local_safety_or_dispatch"
    elif isinstance(model, str) and model and model != expected:
        fatal = "returned_model_mismatch"
    elif error.startswith("AuditError:") or error in {"KeyError", "TypeError", "ValueError"} or error.removeprefix("ResearchError:") in FATAL_VALIDATION:
        fatal = "local_binding_or_integrity"
    elif raw.get("dispatch_started") is False:
        fatal = "dispatch_not_started"
    failed = bool(row["hold"] or not row.get("parsed"))
    unknown = bool(row["hold"] or raw.get("unknown_outcome") or status in {408, 429} or isinstance(status, int) and status >= 500)
    return {"at": row["at"], "failed": failed, "transport_unknown": unknown, "held": bool(row["hold"]),
            "parsed": bool(row.get("parsed")) and not row["hold"], "unreturned": False, "fatal": fatal}


def health(outcomes):
    ordered = sorted(outcomes, key=lambda r: r["at"])
    recent = ordered[-POLICY["window"]:]
    consecutive = 0
    for row in reversed(ordered):
        if not row["failed"]:
            break
        consecutive += 1
    unknown = sum(row["transport_unknown"] for row in recent)
    failures = sum(row["failed"] for row in recent)
    fatal = next((row["fatal"] for row in ordered if row["fatal"]), None)
    reason = ("fatal_" + fatal) if fatal else (
        "sustained_consecutive_failures" if consecutive >= POLICY["consecutive_failure_limit"] else
        "sustained_transport_unknown_window" if unknown >= POLICY["window_transport_unknown_limit"] else
        "sustained_failed_window" if failures >= POLICY["window_failure_limit"] else None)
    return {"outcomes": len(ordered), "provider_responses": sum(not r["unreturned"] for r in ordered),
        "unreturned_intents": sum(r["unreturned"] for r in ordered), "mechanically_parsed": sum(r["parsed"] for r in ordered),
        "invalid": sum(r["failed"] and not r["transport_unknown"] for r in ordered),
        "held_or_transport_unknown": sum(r["transport_unknown"] for r in ordered),
        "window_size": len(recent), "window_failures": failures, "window_transport_unknown": unknown,
        "consecutive_failures": consecutive, "guard_reason": reason, "policy_sha256": digest(POLICY),
        "scope": "All v9 outcomes across phases and process restarts; original holds remain outside this health window."}


class Study(parent.Study):
    @audited_handler
    def _status(self, session, context, data):
        self._v9_active, self._loading_v8 = False, True
        try:
            parent.Study._status(self, session, context, {"action": "report"})
        finally:
            self._loading_v8 = False
        self.v8_amendment = self.amendment
        require(self.v8_amendment["_record_id"] == PARENT_AMENDMENT, "parent_amendment_mismatch")
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment_v9")
        require(self.amendment["implementation"] == implementation()
            and self.amendment["parent_implementation"] == parent.implementation()
            and self.amendment["parent_execution_amendment"] == PARENT_AMENDMENT
            and self.amendment["parent_report"] == PARENT_REPORT and self.amendment["operational_policy"] == POLICY
            and all(self.amendment[k] == self.v8_amendment[k] for k in ("parent_plan", "original_deadline", "passed_pilot_report",
                "passed_gate_record", "seed_capacity_census", "seed_packet_plan_artifact", "seed_proposals_sha256",
                "v6_pilot_budget_baseline", "derived_revalidation_records", "seed_order_integrity")), "amendment_binding_mismatch")
        self.hold_lineage()
        self._v9_active, self._operational_cache = True, {}
        continuations = [r for r in self.rows("cyber_dossier_operational_continuation")
            if r["execution_amendment"] == self.amendment["_record_id"]]
        self._legacy_continuations = len(continuations)
        self._cooldown_until = continuations[-1]["cooldown_until"] if continuations else None
        if data["action"] == "report":
            return self.report(session)
        require(data["action"] == "run" and not self.config.offline and data.get("allow_paid_execution")
                and os.environ.get("OPENAI_API_KEY"), "explicit_paid_execution_required")
        self.deadline = self.amendment["original_deadline"]
        self.provider = observed_transport.UnifiedTransport(before_dispatch=self.before_dispatch)
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

    def register_amendment(self, session, context):
        require(self.config.offline, "amendment_must_be_offline")
        self.absent("cyber_dossier_execution_amendment_v9")
        self.hold_lineage()
        report = self.ledger.get(PARENT_REPORT, "cyber_dossier_report")
        budget = BASE.accounting(list(self.results.values()), self.ledger.unresolved)
        require(report["execution_amendment"] == PARENT_AMENDMENT and report["plan"] == self.plan["_record_id"]
            and report["pilot_gate"] == self.phase(session, "pilot_v6_gate") and report["pilot_gate"]["passed"]
            and len(self.results) == report["stored_responses"]
            and all(budget[k] == report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds")),
            "stopped_parent_state_changed")
        code = implementation()
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": code, "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
            "operational_policy": POLICY, "procedure": "Continue only untouched tasks after isolated fully settled mixed failures. Persist all unknown holds and strict invalid results; exact requests and parsers remain inherited. Durable response-based health, no retries/process restarts; fixed safe transport diagnostics."}})["id"]
        source = BASE.Source(DIAGNOSTIC_OWNER)
        try:
            rows = [r for r in source.rows("cyber_dossier_v8_failure_technical_view_v2") if r["_record_id"] == DIAGNOSTIC]
            require(len(rows) == 1 and rows[0]["execution_amendment"] == PARENT_AMENDMENT
                    and rows[0]["provider_responses_after"] == len(self.results) and rows[0]["new_model_calls"] == 0,
                    "diagnostic_binding_changed")
        finally:
            source.close()
        amendment = {**{k: v for k, v in self.v8_amendment.items() if not k.startswith("_")},
            "method": METHOD, "parent_execution_amendment": PARENT_AMENDMENT, "parent_report": PARENT_REPORT,
            "parent_implementation": parent.implementation(), "implementation": code, "versions": {"protocol": protocol},
            "ancestor_execution_amendments": {**self.v8_amendment["ancestor_execution_amendments"], "v8": PARENT_AMENDMENT},
            "operational_policy": POLICY, "transport_observability": observed_transport.OBSERVABILITY,
            "technical_diagnostic": {"owner": str(DIAGNOSTIC_OWNER), "record_id": DIAGNOSTIC},
            "legacy_budget": budget, "legacy_unresolved_attempts": sorted(self.ledger.unresolved),
            "legacy_response_keys": sorted(self.results), "at": utc()}
        identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v9", METHOD, amendment)
        return {"id": identity, "parent_plan": self.plan["_record_id"], "parent_report": PARENT_REPORT,
            "passed_gate_preserved": True, "original_deadline": amendment["original_deadline"], "legacy_budget": budget,
            "operational_policy": POLICY, "paid_calls": 0, "provider_retries": 0}

    def operational_health(self):
        amendment = self.amendment["_record_id"]
        outcomes = []
        for key, row in self.results.items():
            if row.get("execution_amendment") != amendment:
                continue
            if key not in self._operational_cache:
                self._operational_cache[key] = classify_outcome(row, self.ledger.artifacts.read(row["packet"]),
                    self.ledger.artifacts.read(row["response"]))
            outcomes.append(self._operational_cache[key])
        for item in self.ledger.unresolved.values():
            if item.get("execution_amendment") == amendment and item["task_key"] not in self.results:
                outcomes.append({"at": item["started_at"], "failed": True, "transport_unknown": True,
                    "held": True, "parsed": False, "unreturned": True, "fatal": None})
        value = health(outcomes)
        cooldown = getattr(self, "_cooldown_until", None)
        waiting = bool(cooldown and datetime.now(timezone.utc) < datetime.fromisoformat(cooldown))
        return {**value, "legacy_guard_continuations": self._legacy_continuations,
            "baseline_unresolved_holds": len(self.amendment["legacy_unresolved_attempts"]),
            "operational_status": "stopped" if value["guard_reason"] else "cooldown" if waiting else "ready",
            "cooldown_until": cooldown}

    def check_operational_guard(self):
        current = self.operational_health()
        if current["guard_reason"]:
            raise PipelineStop("v9_" + current["guard_reason"])
        return current

    def checkpoint(self, **extra):
        if not getattr(self, "_v9_active", False):
            return super().checkpoint(**extra)
        current = self.operational_health()
        super().checkpoint(**extra, operational_continuation=current)
        if "stop_reason" not in extra and current["guard_reason"]:
            raise PipelineStop("v9_" + current["guard_reason"])

    def calls(self, session, packets):
        while True:
            before = len(self.results)
            self.check_operational_guard()
            self.wait_cooldown()
            try:
                return super().calls(session, packets)
            except PipelineStop as error:
                if str(error) != "repeated_provider_or_validation_failure":
                    raise
                require(len(self.results) > before, "legacy_guard_without_response_progress")
                current = self.check_operational_guard()
                cooldown = (datetime.now(timezone.utc) + timedelta(seconds=POLICY["legacy_guard_cooldown_seconds"])).isoformat()
                self.ledger.record(session, "cyber_dossier_operational_continuation", digest([utc(), len(self.results)]), {
                    "execution_amendment": self.amendment["_record_id"], "phase": self.current_phase,
                    "responses_before": before, "responses_after": len(self.results), "health": current,
                    "reason": "isolated_mixed_wave_untouched_work_continues", "cooldown_until": cooldown, "at": utc()})
                self._legacy_continuations += 1
                self._cooldown_until = cooldown

    def wait_cooldown(self):
        until = getattr(self, "_cooldown_until", None)
        if not until or datetime.now(timezone.utc) >= datetime.fromisoformat(until):
            return
        self.checkpoint()
        while datetime.now(timezone.utc) < datetime.fromisoformat(until):
            self.before_dispatch()
            time.sleep(min(1., max(0., (datetime.fromisoformat(until) - datetime.now(timezone.utc)).total_seconds())))
        self.before_dispatch()
        self.checkpoint()

    def category_budget(self):
        result = {}
        for category, limit in (("main", BASE.PARAMETERS["non_audit_cap_nanousd"]),
                                ("audit", BASE.PARAMETERS["audit_cap_nanousd"])):
            rows = [r for r in self.results.values() if r["category"] == category]
            pending = {a: r for a, r in self.ledger.unresolved.items() if r.get("category") == category}
            budget = BASE.accounting(rows, pending)
            result[category] = {**budget, "cap_nanousd": limit,
                               "remaining_nanousd": max(0, limit - budget["committed_nanousd"])}
        return result

    def report(self, session):
        if getattr(self, "_loading_v8", False):
            return None
        previous = super().report(session)
        report = {k: v for k, v in previous.items() if k != "id"}
        report.update(parent_report=PARENT_REPORT, technical_extension_version=9, base_report_record=previous["id"],
                      operational_continuation=self.operational_health(), category_budget=self.category_budget())
        identity = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results), METHOD]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identity, **report}, indent=2), encoding="utf-8")
        return {"id": identity, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=BASE.preparation.OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Continue untouched dossier work under durable operational guards and the unchanged USD50 cap", actor="codex:cybercrime-dossiers")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
