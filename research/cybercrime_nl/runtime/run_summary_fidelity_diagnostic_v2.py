"""Bounded schema repair on untouched fixed diagnostic cases, with serial probe."""
from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

import run_summary_fidelity_diagnostic as original
import summary_fidelity_contract_v2 as contract
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import audited_handler

runner = original.runner
METHOD = "cybercrime-summary-fidelity-astra-diagnostic-20261023-v2"
PARENT_PLAN = "3b7ebce9c31a20f8e483dbd583c2036658371bfe362546cfc69ee28f4fe1edb3"
PARENT_REPORT = "aec4fce4a641e2c59eba65cd715d8a02987be744c3bdf7ef850963b407ae2231"
PHASE = original.PHASE
REPAIR_CAP = 2_000_000_000
COMBINED_CAP = 4_000_000_000
EXPECTED_PARENT_ATTEMPTS, EXPECTED_UNTOUCHED = 3, 9
OUTPUT_TOKENS = 2000
METHOD_DOCUMENT = runner.ROOT / "research/cybercrime_nl/SUMMARY_DIAGNOSTIC_AMENDMENT_V2.md"


def implementation():
    paths = [Path(__file__), Path(contract.__file__), METHOD_DOCUMENT,
             runner.ROOT / "research/cybercrime_nl/runtime/run_summary_fidelity_v2_with_key.ps1"]
    return {**original.implementation(), **{str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


class Study(original.Study):
    def diagnostic_attempts(self):
        """Summary-version blocking survives a changed schema or task key."""
        entries = {r["attempt"]: r for r in self.results.values() if r["phase"] == PHASE}
        for attempt, intended in self.ledger.unresolved.items():
            if intended.get("phase") == PHASE:
                entries.setdefault(attempt, intended)
        by_version = {}
        for attempt, row in entries.items():
            packet = self.ledger.artifacts.read(row["packet"])
            version = packet["bindings"]["summary_version"]
            if version in by_version:
                raise AuditError("summary_fidelity_repeated_version_attempt")
            by_version[version] = {**row, "attempt": attempt}
        return by_version

    def assert_baseline(self, baseline, holds):
        now = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        if (not set(holds) <= set(self.ledger.unresolved)
                or any(now[k] < baseline[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd"))):
            raise AuditError("summary_fidelity_repair_prior_liability_reduced")

    @audited_handler
    def _status(self, session, context, data):
        code = implementation()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "registered_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
                "procedure": "Repair unsupported strict wire-schema keywords only. Keep all12 original selected summaries and source/question attribution, never retry any summary version with a durable old attempt. Prepare the9 untouched versions only. Preserve all old costs/holds and deadline, permit2USD new repair commitment inside4USD combined diagnostic/10audit/50total. First request is a serial valid-settled probe, then at most3 simultaneous requests. Stop on any new HTTP/schema/invalid/unknown outcome. Persist attempted-but-unreturned tasks as unknown. Settle partial budget waves and continue only untouched tasks while unchanged admission permits."},
            "selection": {"rules": "Exact parent diagnostic plan/report;3 attempted versions permanently blocked and9 untouched fixed cases, no replacement."},
            "question": {"text": "Does the unchanged saved summary faithfully represent what all supplied articles report?"},
            "prompt": {"instructions": contract.INSTRUCTIONS,
                       "contract_implementation": code[str(Path(contract.__file__).relative_to(runner.ROOT))]},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        self.init_state()
        self.plan = self.one("cyber_dossier_plan")
        self.amendment = self.one("cyber_dossier_execution_amendment_v3")
        self.parent_diagnostic = self.one("cyber_summary_fidelity_diagnostic_plan")
        if (self.plan["_record_id"] != runner.PARENT_PLAN or self.plan["implementation"] != runner.original.implementation()
                or self.amendment["implementation"] != runner.implementation()
                or self.parent_diagnostic["_record_id"] != PARENT_PLAN
                or self.parent_diagnostic["implementation"] != original.implementation()):
            raise AuditError("summary_fidelity_repair_parent_changed")
        self.hold_lineage()
        self.deadline = self.one("cyber_dossier_first_launch")["deadline"]
        if self.deadline != self.parent_diagnostic["original_deadline"] or self.deadline != self.amendment["original_deadline"]:
            raise AuditError("summary_fidelity_repair_deadline_changed")
        self.assert_baseline(self.parent_diagnostic["baseline_budget"], self.parent_diagnostic["baseline_hold_attempts"])
        if data["action"] == "prepare":
            return self.prepare_repair(session, code, versions)
        self.diagnostic = self.one("cyber_summary_fidelity_diagnostic_amendment_v2")
        if (self.diagnostic["implementation"] != code or self.diagnostic["parent_diagnostic_plan"] != PARENT_PLAN
                or self.diagnostic["original_deadline"] != self.deadline
                or self.diagnostic["repair_cap_nanousd"] != REPAIR_CAP
                or self.diagnostic["combined_diagnostic_cap_nanousd"] != COMBINED_CAP):
            raise AuditError("summary_fidelity_repair_frozen_amendment_changed")
        self.assert_baseline(self.diagnostic["baseline_budget"], self.diagnostic["baseline_hold_attempts"])
        if data["action"] == "report":
            return self.repair_report(session)
        if data["action"] != "run" or self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("summary_fidelity_repair_explicit_paid_execution_required")
        self.provider = runner.transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        self.current_phase = PHASE + "_v2"
        try:
            prior = [r for r in self.results.values() if r.get("diagnostic_plan") == self.diagnostic["_record_id"]]
            if (any(v.get("diagnostic_plan") == self.diagnostic["_record_id"] for v in self.ledger.unresolved.values())
                    or any(not r["parsed"] or r["hold"] or not 200 <= (r.get("http_status") or 0) < 300 for r in prior)):
                raise runner.PipelineStop("summary_fidelity_repair_failure_requires_review")
            self.dispatch_repair(session)
            stop = "diagnostic_repair_queue_exhausted"
        except runner.PipelineStop as error:
            stop = str(error)
        self.ledger.record(session, "cyber_summary_fidelity_diagnostic_stopped_v2", digest([utc(), stop]),
            {"diagnostic_plan": self.diagnostic["_record_id"], "reason": stop, "at": utc()})
        self.checkpoint(stop_reason=stop, diagnostic_plan=self.diagnostic["_record_id"])
        return self.repair_report(session)

    def prepare_repair(self, session, code, versions):
        if not self.config.offline:
            raise AuditError("summary_fidelity_repair_prepare_offline_required")
        self.absent("cyber_summary_fidelity_diagnostic_amendment_v2")
        report = self.ledger.get(PARENT_REPORT, "cyber_summary_fidelity_diagnostic_report")
        if report["diagnostic_plan"] != PARENT_PLAN:
            raise AuditError("summary_fidelity_repair_wrong_parent_report")
        attempts = self.diagnostic_attempts()
        parents = self.parent_diagnostic["tasks"]
        parent_versions = {t["selection"]["summary_version"] for t in parents}
        if len(parent_versions) != len(parents) or set(attempts) - parent_versions or len(attempts) != EXPECTED_PARENT_ATTEMPTS:
            raise AuditError("summary_fidelity_repair_parent_attempt_frame_changed")
        parent_details = self.ledger.artifacts.read(report["details_artifact"])
        reported_holds = {d["unresolved_attempt"] for d in parent_details if d["outcome"] == "unknown_hold"}
        required_holds = reported_holds | {r["attempt"] for r in attempts.values() if r.get("hold") or not r.get("_record_id")}
        if None in required_holds or len(required_holds) != EXPECTED_PARENT_ATTEMPTS:
            raise AuditError("summary_fidelity_repair_parent_holds_changed")
        self.assert_baseline(report, required_holds)
        tasks, excluded = [], []
        for parent in parents:
            version = parent["selection"]["summary_version"]
            if version in attempts:
                excluded.append({"summary_version": version, "attempt": attempts[version]["attempt"],
                                 "original_task_key": parent["task_key"], "reason": "prior_attempt_never_retried"})
                continue
            old_packet = self.ledger.artifacts.read(parent["packet"])
            packet = contract.request(old_packet["original_documents"], old_packet["summary_snapshot"],
                                      count_tokens=self.count, max_output_tokens=OUTPUT_TOKENS)
            packet.update(phase=PHASE, kind="responses")
            if packet["bindings"] != old_packet["bindings"] or packet["document_ids"] != old_packet["document_ids"]:
                raise AuditError("summary_fidelity_repair_evidence_changed")
            tasks.append({"selection": parent["selection"], "original_packet": parent["packet"],
                "original_task_key": parent["task_key"], "packet": self.ledger.artifacts.put(packet),
                "task_key": self.task_key(packet), "reservation_nanousd": runner.reserve(packet),
                "input_tokens_proxy": packet["input_tokens_proxy"]})
        if len(tasks) != EXPECTED_UNTOUCHED or len({t["task_key"] for t in tasks}) != len(tasks):
            raise AuditError("summary_fidelity_repair_untouched_frame_changed")
        baseline = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        parent_budget = self.budget_for({PARENT_PLAN})
        reservations = sum(t["reservation_nanousd"] for t in tasks)
        value = {"method": METHOD, "implementation": code, "versions": versions,
            "parent_diagnostic_plan": PARENT_PLAN, "parent_diagnostic_report": PARENT_REPORT,
            "parent_implementation": self.parent_diagnostic["implementation"],
            "parent_plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "original_tasks": parents, "tasks": tasks, "excluded_attempts": excluded,
            "required_parent_hold_attempts": sorted(required_holds),
            "probe_task_key": tasks[0]["task_key"], "original_deadline": self.deadline,
            "baseline_budget": baseline, "baseline_hold_attempts": sorted(self.ledger.unresolved),
            "parent_diagnostic_budget": parent_budget, "repair_cap_nanousd": REPAIR_CAP,
            "combined_diagnostic_cap_nanousd": COMBINED_CAP, "total_cap_nanousd": runner.CAP,
            "audit_cap_nanousd": runner.PARAMETERS["audit_cap_nanousd"],
            "conservative_reservation_nanousd": reservations, "max_output_tokens": OUTPUT_TOKENS,
            "maximum_single_reservation_nanousd": max(t["reservation_nanousd"] for t in tasks), "at": utc()}
        identifier = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_amendment_v2", METHOD, value)
        return {"id": identifier, "fixed_frame": len(parents), "blocked_prior_attempts": len(excluded),
            "untouched_requests": len(tasks), "baseline_budget": baseline, "parent_diagnostic_budget": parent_budget,
            "conservative_reservation_nanousd": reservations, "first_probe_reservation_nanousd": tasks[0]["reservation_nanousd"],
            "maximum_single_reservation_nanousd": value["maximum_single_reservation_nanousd"],
            "all_future_reservations_fit_repair_subcap": reservations <= REPAIR_CAP,
            "input_tokens_proxy_total": sum(t["input_tokens_proxy"] for t in tasks),
            "original_deadline": self.deadline, "repair_cap_nanousd": REPAIR_CAP,
            "combined_diagnostic_cap_nanousd": COMBINED_CAP, "paid_calls": 0}

    def budget_for(self, identifiers):
        rows = [r for r in self.results.values() if r.get("diagnostic_plan") in identifiers]
        pending = {a: v for a, v in self.ledger.unresolved.items() if v.get("diagnostic_plan") in identifiers}
        return runner.accounting(rows, pending)

    def repair_budget(self):
        return self.budget_for({self.diagnostic["_record_id"]})

    def combined_budget(self):
        return self.budget_for({PARENT_PLAN, self.diagnostic["_record_id"]})

    def dispatch_repair(self, session):
        tasks = self.diagnostic["tasks"]
        self.phase_tasks_planned = len(tasks)
        while True:
            attempts = self.diagnostic_attempts()
            remaining = [t for t in tasks if t["selection"]["summary_version"] not in attempts]
            if not remaining:
                return
            probe = self.results.get(self.diagnostic["probe_task_key"])
            probe_valid = bool(probe and probe["parsed"] and not probe["hold"] and 200 <= (probe.get("http_status") or 0) < 300)
            if not probe_valid and remaining[0]["task_key"] != self.diagnostic["probe_task_key"]:
                raise runner.PipelineStop("summary_fidelity_repair_probe_not_valid")
            width = 3 if probe_valid else 1
            self.before_dispatch()
            wave, metadata = [], []
            for task in remaining[:width]:
                packet = self.ledger.artifacts.read(task["packet"])
                if self.task_key(packet) != task["task_key"] or runner.reserve(packet) != task["reservation_nanousd"]:
                    raise AuditError("summary_fidelity_repair_packet_changed")
                reserve = task["reservation_nanousd"]
                total = runner.accounting(list(self.results.values()), self.ledger.unresolved)
                if (total["committed_nanousd"] + reserve > runner.CAP
                        or self.audit_commitment() + reserve > runner.PARAMETERS["audit_cap_nanousd"]
                        or self.repair_budget()["committed_nanousd"] + reserve > REPAIR_CAP
                        or self.combined_budget()["committed_nanousd"] + reserve > COMBINED_CAP):
                    if not wave:
                        raise runner.PipelineStop("summary_fidelity_repair_budget_bound")
                    break
                attempt = str(uuid.uuid4())
                invocation = runner.transport.Invocation(packet["request"], attempt, kind="responses")
                intended = {"attempt": attempt, "task_key": task["task_key"], "number": 1, "batch": self.plan["_record_id"],
                    "execution_amendment": self.amendment["_record_id"], "diagnostic_plan": self.diagnostic["_record_id"],
                    "parent_diagnostic_plan": PARENT_PLAN, "request": self.ledger.artifacts.put(packet["request"]),
                    "packet": task["packet"], "dispatch": self.ledger.artifacts.put(invocation.manifest()),
                    "phase": PHASE, "category": "audit", "reserved_nanousd": reserve, "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((invocation, attempt))
                metadata.append((task, packet, intended))
            failure = False
            for index, response in self.gateway.codex_dispatch(session, self.provider, wave, len(wave)):
                task, packet, intended = metadata[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                cost = runner.billed(packet, response)
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intended["reserved_nanousd"]
                parsed, error = None, None
                http_ok = 200 <= (raw.get("http_status") or 0) < 300
                if response.payload is not None and http_ok:
                    try:
                        parsed = contract.parse(packet, response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as caught:
                        error = type(caught).__name__ + ":" + str(caught)[:180]
                elif not http_ok:
                    error = "summary_fidelity_repair_http_not_success"
                row = {"plan": self.plan["_record_id"], "task_key": task["task_key"], "phase": PHASE, "category": "audit",
                    "execution_amendment": self.amendment["_record_id"], "diagnostic_plan": self.diagnostic["_record_id"],
                    "parent_diagnostic_plan": PARENT_PLAN, "packet": task["packet"], "request": intended["request"],
                    "response": response_ref, "attempt": intended["attempt"],
                    "parsed": self.ledger.artifacts.put(parsed) if parsed else None, "cost_nanousd": cost,
                    "reserved_nanousd": intended["reserved_nanousd"] if hold else 0, "hold": hold,
                    "validation_error": error, "http_status": raw.get("http_status"), "at": utc()}
                identifier = self.ledger.record(session, "cyber_dossier_response", task["task_key"], row)
                self.results[task["task_key"]] = {**row, "_record_id": identifier}
                if hold:
                    self.ledger.unresolved[intended["attempt"]]["cost_nanousd"] = cost
                else:
                    self.complete(session, intended, response_ref, identifier, "valid" if parsed else "invalid")
                failure |= bool(hold or not parsed or not 200 <= (row["http_status"] or 0) < 300)
            self.phase_tasks_completed = sum(t["task_key"] in self.results for t in tasks)
            self.checkpoint(diagnostic_plan=self.diagnostic["_record_id"], phase_tasks_planned=len(tasks),
                phase_tasks_completed=self.phase_tasks_completed, phase_task_set_sha256=digest([t["task_key"] for t in tasks]))
            if failure:
                raise runner.PipelineStop("summary_fidelity_repair_invalid_http_or_unknown")

    def repair_report(self, session):
        attempts = self.diagnostic_attempts()
        details, counts = [], {}
        for task in self.diagnostic["original_tasks"]:
            row = attempts.get(task["selection"]["summary_version"])
            saved = self.results.get(row["task_key"]) if row else None
            held = bool(row and row["attempt"] in self.ledger.unresolved)
            parsed = self.ledger.artifacts.read(saved["parsed"]) if saved and saved["parsed"] and not held else None
            label = "unknown_hold" if held else parsed["label"] if parsed else "invalid" if row else "not_attempted"
            stratum = task["selection"]["stratum"]
            counts.setdefault(stratum, Counter())[label] += 1
            details.append({"selection": task["selection"], "response_record": saved["_record_id"] if saved else None,
                "unresolved_attempt": row["attempt"] if held else None, "outcome": label, "parsed": parsed,
                "validation_error": saved.get("validation_error") if saved else None})
        result = {"at": utc(), "plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "diagnostic_plan": self.diagnostic["_record_id"], "parent_diagnostic_plan": PARENT_PLAN,
            "selected": len(details), "repair_selected": len(self.diagnostic["tasks"]),
            "attempted_diagnostic_tasks": len(attempts),
            "stored_diagnostic_responses": sum(d["response_record"] is not None for d in details),
            "repair_stored_responses": sum(t["task_key"] in self.results for t in self.diagnostic["tasks"]),
            "stratum_labels": {k: dict(v) for k, v in counts.items()}, "details_artifact": self.ledger.artifacts.put(details),
            **runner.accounting(list(self.results.values()), self.ledger.unresolved), **self.hold_lineage(),
            "repair_budget": self.repair_budget(), "combined_diagnostic_budget": self.combined_budget(),
            "repair_cap_nanousd": REPAIR_CAP, "combined_diagnostic_cap_nanousd": COMBINED_CAP,
            "original_deadline": self.deadline, "old_gates_modified": False, "summaries_regenerated": 0,
            "human_validated": False, "population_accuracy_estimate": False,
            "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_report_v2", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=runner.preparation.OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action != "run"))
    try:
        print(json.dumps(study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Diagnose only untouched summaries after a strict-schema compatibility repair",
            actor="codex:summary-fidelity-schema-repair")))
    finally:
        study.close()
