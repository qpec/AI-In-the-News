"""Prospective deadline-only continuation; activate only after the v9 writer exits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import run_dossiers_v9 as parent
from newsresearch.common import AuditError, Config, digest, require_no_credentials, utc
from newsresearch.runtime import audited_handler

BASE, ROOT, CAP = parent.BASE, parent.ROOT, parent.CAP
PipelineStop = parent.PipelineStop
METHOD = "cybercrime-four-process-dossiers-20261023-v10"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V10.md"
DEADLINE_POLICY = {"version": "user-authorized-frozen-pipeline-completion-v1",
    "mode": "finish_frozen_pipeline_within_existing_guards", "effective_admission_deadline": None,
    "original_deadline_immutable": True, "budget_reset": False, "provider_retries": 0}
HEALTH_SCOPE = "All outcomes under the v9 operational policy, including this deadline-only continuation; the original v9 health baseline is preserved."
PRESERVED = ("parent_plan", "original_deadline", "passed_pilot_report", "passed_gate_record", "seed_capacity_census",
    "seed_packet_plan_artifact", "seed_proposals_sha256", "v6_pilot_budget_baseline", "derived_revalidation_records",
    "seed_order_integrity", "operational_policy", "transport_observability", "cap_nanousd", "main_cap_nanousd",
    "audit_cap_nanousd", "contingency_nanousd")


def require(value, message):
    if not value:
        raise AuditError("dossier_v10_" + message)


def implementation():
    paths = [Path(__file__), METHOD_DOCUMENT, ROOT / "research/cybercrime_nl/runtime/run_dossiers_v10_with_key.ps1"]
    return {**parent.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


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


class Study(parent.Study):
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
            return self.register_deadline_amendment(session, context, data)
        self.amendment = self.one("cyber_dossier_execution_amendment_v10")
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

    def register_deadline_amendment(self, session, context, data):
        require(self.config.offline and data.get("parent_report") and data.get("authorization_file"), "offline_explicit_registration_required")
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
        code = implementation()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
                "procedure": "Deadline-only user-authorized continuation of the same frozen queue. Preserve original cutoff, all costs/holds, requests/parsers, STOP, no retry and durable v9 health/cooldown. No date cutoff replaces the old admission cutoff only after the prior writer closes; budget remains unchanged."},
            "policy": {"deadline_policy": DEADLINE_POLICY, "deadline_evidence": authorization,
                "parent_execution_amendment": self.v9_amendment["_record_id"], "original_deadline": self.v9_amendment["original_deadline"],
                "cap_nanousd": CAP, "new_models_or_questions_authorized": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        amendment = {**{k: v for k, v in self.v9_amendment.items() if not k.startswith("_")},
            "method": METHOD, "parent_execution_amendment": self.v9_amendment["_record_id"], "parent_report": report["_record_id"],
            "parent_implementation": parent.implementation(), "implementation": code, "versions": versions,
            "ancestor_execution_amendments": {**self.v9_amendment["ancestor_execution_amendments"], "v9": self.v9_amendment["_record_id"]},
            "deadline_policy": DEADLINE_POLICY, "effective_admission_deadline": None, "deadline_authorization": authorization,
            "operational_origin_amendment": self.v9_amendment["_record_id"], "health_ancestor_amendments": [self.v9_amendment["_record_id"]],
            "operational_health_baseline_unresolved_attempts": self.v9_amendment["legacy_unresolved_attempts"],
            "legacy_budget": budget, "legacy_unresolved_attempts": sorted(self.ledger.unresolved),
            "legacy_response_keys": sorted(self.results), "at": utc()}
        identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v10", METHOD, amendment)
        return {"id": identity, "parent_plan": self.plan["_record_id"], "parent_report": report["_record_id"],
            "original_deadline": amendment["original_deadline"], "effective_admission_deadline": None,
            "deadline_policy": DEADLINE_POLICY, "deadline_authorization": authorization, "legacy_budget": budget,
            "operational_origin_amendment": amendment["operational_origin_amendment"], "paid_calls": 0}

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
        return super().checkpoint(**extra)

    def report(self, session):
        if getattr(self, "_loading_v9", False):
            return None
        previous = super().report(session)
        report = {k: v for k, v in previous.items() if k != "id"}
        report.update(parent_report=self.amendment["parent_report"], technical_extension_version=10,
            base_report_record=previous["id"], **self.deadline_metadata())
        identity = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results), METHOD]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identity, **report}, indent=2), encoding="utf-8")
        return {"id": identity, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=BASE.preparation.OWNER)
    parser.add_argument("--parent-report")
    parser.add_argument("--authorization-file", type=Path)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution,
            "parent_report": args.parent_report, "authorization_file": str(args.authorization_file) if args.authorization_file else None},
            objective="Register or continue the same budget-bound dossier pipeline under explicit deadline-extension authority", actor="codex:cybercrime-dossiers")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
