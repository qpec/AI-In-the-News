"""Same-owner bounded Astra fidelity diagnostic; no summary generation or retry."""
from collections import Counter
from dataclasses import asdict
import argparse
import hashlib
import json
import os
from pathlib import Path
import uuid

import inspect_summary_fidelity_v3 as census
import run_dossiers_v3 as runner
import summary_fidelity_contract as contract
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import audited_handler

METHOD = "cybercrime-summary-fidelity-astra-diagnostic-20261023-v1"
CENSUS = "73390191b1d4bc221388100de299a74af164cfc5f365addeb7b2fc9b66535f59"
PHASE = "summary_fidelity_audit"
DIAGNOSTIC_CAP = 2_000_000_000
WEAK_COUNT, CONTROL_COUNT = 6, 6
OUTPUT_TOKENS = 2000


def implementation():
    paths = [Path(__file__), Path(contract.__file__), Path(census.__file__),
             runner.ROOT / "research/cybercrime_nl/SUMMARY_DIAGNOSTIC.md",
             runner.ROOT / "research/cybercrime_nl/runtime/run_summary_fidelity_with_key.ps1"]
    return {**runner.implementation(), **{str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


class Study(runner.Study):
    @audited_handler
    def _status(self, session, context, data):
        code = implementation()
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "registered_specification": (runner.ROOT / "research/cybercrime_nl/SUMMARY_DIAGNOSTIC.md").read_text(encoding="utf-8"),
                "procedure": "New independent Astra fidelity question on exactly6 weak valid summaries and6 hash-ranked usable controls. Same study owner, plan task namespace, all costs/holds and original deadline. Full exact article evidence and unchanged summary claims; hide earlier labels/probabilities/selection stratum. Known passage IDs expand mechanically. No generation, source replacement, changed old parser, retry, gate relaxation or automatic finding acceptance. Save new response rows in shared cyber_dossier_response/category audit with exact diagnostic plan binding. Additional2USD subcap on this diagnostic's costs+reservations inside prior10audit/50total caps. Up to4 concurrent requests, stop after a wave with an unknown hold or3 invalid responses; persisted failures block unreviewed continuation."},
            "selection": {"rules": "Fixed census73390191…35f59: all6 mechanically valid summaries excluded by original faithfulness threshold, plus6 deterministic usable controls. Mechanically invalid summary is excluded and explicitly counted, never replaced."},
            "question": {"text": "Does each supplied dossier summary faithfully preserve the full articles' claims, status and event identity, and if not, what specific defect is supported by the articles?"},
            "prompt": {"instructions": contract.INSTRUCTIONS,
                       "implementation": code[str(Path(contract.__file__).relative_to(runner.ROOT))]},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        self.init_state()
        self.plan = self.one("cyber_dossier_plan")
        self.amendment = self.one("cyber_dossier_execution_amendment_v3")
        if (self.plan["_record_id"] != runner.PARENT_PLAN or self.plan["implementation"] != runner.original.implementation()
                or self.amendment["implementation"] != runner.implementation()):
            raise AuditError("summary_diagnostic_parent_changed")
        self.hold_lineage()
        self.deadline = self.one("cyber_dossier_first_launch")["deadline"]
        if self.deadline != self.amendment["original_deadline"]:
            raise AuditError("summary_diagnostic_deadline_changed")
        if data["action"] == "prepare":
            return self.prepare_diagnostic(session, code, versions)
        self.diagnostic = self.one("cyber_summary_fidelity_diagnostic_plan")
        if (self.diagnostic["implementation"] != code or self.diagnostic["parent_plan"] != self.plan["_record_id"]
                or self.diagnostic["execution_amendment"] != self.amendment["_record_id"]
                or self.diagnostic["original_deadline"] != self.deadline
                or self.diagnostic["diagnostic_cap_nanousd"] != DIAGNOSTIC_CAP):
            raise AuditError("summary_diagnostic_frozen_plan_changed")
        baseline = self.diagnostic["baseline_budget"]
        current = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        if (not set(self.diagnostic["baseline_hold_attempts"]) <= set(self.ledger.unresolved)
                or current["held_nanousd"] < baseline["held_nanousd"]
                or current["settled_nanousd"] < baseline["settled_nanousd"]):
            raise AuditError("summary_diagnostic_prior_liability_reduced")
        if data["action"] == "report":
            return self.diagnostic_report(session)
        if data["action"] != "run" or self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("summary_diagnostic_explicit_paid_execution_required")
        self.provider = runner.transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        self.current_phase = PHASE
        try:
            if any(v.get("diagnostic_plan") == self.diagnostic["_record_id"] for v in self.ledger.unresolved.values()):
                raise runner.PipelineStop("summary_diagnostic_unresolved_attempt_requires_review")
            invalid = [r for r in self.results.values() if r.get("diagnostic_plan") == self.diagnostic["_record_id"] and not r["parsed"]]
            if len(invalid) >= 3:
                raise runner.PipelineStop("summary_diagnostic_repeated_invalid_requires_review")
            self.dispatch_diagnostic(session)
            stop = "diagnostic_queue_exhausted"
        except runner.PipelineStop as error:
            stop = str(error)
        self.ledger.record(session, "cyber_summary_fidelity_diagnostic_stopped", digest([utc(), stop]),
            {"diagnostic_plan": self.diagnostic["_record_id"], "reason": stop, "at": utc()})
        self.checkpoint(stop_reason=stop, diagnostic_plan=self.diagnostic["_record_id"])
        return self.diagnostic_report(session)

    def prepare_diagnostic(self, session, code, versions):
        if not self.config.offline:
            raise AuditError("summary_diagnostic_prepare_offline_required")
        self.absent("cyber_summary_fidelity_diagnostic_plan")
        source = runner.preparation.screening.original.base.pilot.Source(census.OWNER)
        try:
            selected = source.one("cyber_summary_fidelity_census")
            if (selected["_record_id"] != CENSUS or selected["source_report"] != census.REPORT
                    or selected["execution_amendment"] != self.amendment["_record_id"]
                    or selected["weak_selected"] != WEAK_COUNT or selected["controls_selected"] != CONTROL_COUNT
                    or len(selected["selected"]) != WEAK_COUNT + CONTROL_COUNT
                    or len(selected["selected"]) > 12):
                raise AuditError("summary_diagnostic_selection_changed")
        finally:
            source.close()
        report = self.ledger.get(census.REPORT, "cyber_dossier_report")
        if report["execution_amendment"] != self.amendment["_record_id"]:
            raise AuditError("summary_diagnostic_wrong_report")
        manifest = self.ledger.get(self.plan["input_manifest"], "cyber_dossier_input_manifest")
        documents = {r["document_id"]: r for r in self.ledger.artifacts.read(manifest["documents_artifact"])}
        tasks = []
        for entry in selected["selected"]:
            response = self.ledger.get(entry["summary_record"], "cyber_dossier_response")
            if response["parsed"] != entry["summary_parsed_artifact"] or response["hold"]:
                raise AuditError("summary_diagnostic_snapshot_changed")
            snapshot = self.ledger.artifacts.read(response["parsed"])
            if snapshot["summary_version"] != entry["summary_version"] or snapshot["membership_revision"] != entry["membership_revision"]:
                raise AuditError("summary_diagnostic_snapshot_binding")
            docs = [self.ledger.artifacts.read(documents[i]["document_artifact"]) for i in snapshot["summary"]["source_document_ids"]]
            packet = contract.request(docs, snapshot, count_tokens=self.count, max_output_tokens=OUTPUT_TOKENS)
            packet.update(phase=PHASE, kind="responses")
            tasks.append({"selection": entry, "packet": self.ledger.artifacts.put(packet),
                          "task_key": self.task_key(packet), "reservation_nanousd": runner.reserve(packet),
                          "input_tokens_proxy": packet["input_tokens_proxy"]})
        if len({t["task_key"] for t in tasks}) != len(tasks):
            raise AuditError("summary_diagnostic_duplicate_task")
        budget = runner.accounting(list(self.results.values()), self.ledger.unresolved)
        reservation = sum(t["reservation_nanousd"] for t in tasks)
        audit_used = self.audit_commitment()
        value = {"method": METHOD, "implementation": code, "versions": versions, "parent_plan": self.plan["_record_id"],
            "execution_amendment": self.amendment["_record_id"], "source_census": CENSUS, "source_report": census.REPORT,
            "tasks": tasks, "original_deadline": self.deadline, "baseline_budget": budget,
            "baseline_hold_attempts": sorted(self.ledger.unresolved), "cap_nanousd": runner.CAP,
            "diagnostic_cap_nanousd": DIAGNOSTIC_CAP,
            "max_output_tokens": OUTPUT_TOKENS,
            "audit_cap_nanousd": runner.PARAMETERS["audit_cap_nanousd"], "main_cap_nanousd": runner.PARAMETERS["non_audit_cap_nanousd"],
            "conservative_reservation_nanousd": reservation, "audit_committed_nanousd": audit_used,
            "all_requests_fit_existing_caps": budget["committed_nanousd"] + reservation <= runner.CAP
                and audit_used + reservation <= runner.PARAMETERS["audit_cap_nanousd"],
            "all_future_reservations_fit_diagnostic_subcap": reservation <= DIAGNOSTIC_CAP,
            "maximum_single_reservation_nanousd": max(t["reservation_nanousd"] for t in tasks),
            "mechanically_invalid_summary_not_selected": 1, "at": utc()}
        identifier = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_plan", METHOD, value)
        return {"id": identifier, "selected": len(tasks), "weak": WEAK_COUNT, "controls": CONTROL_COUNT,
                **{k: value[k] for k in ("original_deadline", "baseline_budget", "conservative_reservation_nanousd",
                                       "audit_committed_nanousd", "all_requests_fit_existing_caps", "diagnostic_cap_nanousd",
                                       "all_future_reservations_fit_diagnostic_subcap", "maximum_single_reservation_nanousd")},
                "input_tokens_proxy_total": sum(t["input_tokens_proxy"] for t in tasks),
                "input_tokens_proxy_max": max(t["input_tokens_proxy"] for t in tasks), "paid_calls": 0}

    def audit_commitment(self):
        used = sum((max(r["reserved_nanousd"], r["cost_nanousd"] or 0) if r["hold"] else r["cost_nanousd"] or 0)
                   for r in self.results.values() if r["category"] == "audit")
        return used + sum(v["reserved_nanousd"] for v in self.ledger.unresolved.values()
                          if v.get("category") == "audit" and v["task_key"] not in self.results)

    def diagnostic_commitment(self):
        identifier = self.diagnostic["_record_id"]
        rows = [r for r in self.results.values() if r.get("diagnostic_plan") == identifier]
        pending = {key: v for key, v in self.ledger.unresolved.items() if v.get("diagnostic_plan") == identifier}
        return runner.accounting(rows, pending)

    def dispatch_diagnostic(self, session):
        tasks = self.diagnostic["tasks"]
        seen = set(self.results) | {v["task_key"] for v in self.ledger.unresolved.values()}
        remaining = [t for t in tasks if t["task_key"] not in seen]
        self.phase_tasks_planned = len(tasks)
        for start in range(0, len(remaining), 4):
            self.before_dispatch()
            wave, metadata = [], []
            for task in remaining[start:start+4]:
                packet = self.ledger.artifacts.read(task["packet"])
                if self.task_key(packet) != task["task_key"] or runner.reserve(packet) != task["reservation_nanousd"]:
                    raise AuditError("summary_diagnostic_packet_changed")
                reserve = task["reservation_nanousd"]
                budget = runner.accounting(list(self.results.values()), self.ledger.unresolved)
                if (budget["committed_nanousd"] + reserve > runner.CAP
                        or self.audit_commitment() + reserve > runner.PARAMETERS["audit_cap_nanousd"]
                        or self.diagnostic_commitment()["committed_nanousd"] + reserve > DIAGNOSTIC_CAP):
                    if not wave:
                        raise runner.PipelineStop("summary_diagnostic_budget_bound")
                    break
                attempt = str(uuid.uuid4())
                invocation = runner.transport.Invocation(packet["request"], attempt, kind="responses")
                intended = {"attempt": attempt, "task_key": task["task_key"], "number": 1, "batch": self.plan["_record_id"],
                    "execution_amendment": self.amendment["_record_id"], "diagnostic_plan": self.diagnostic["_record_id"],
                    "request": self.ledger.artifacts.put(packet["request"]), "packet": task["packet"],
                    "dispatch": self.ledger.artifacts.put(invocation.manifest()), "phase": PHASE, "category": "audit",
                    "reserved_nanousd": reserve, "started_at": utc()}
                self.ledger.append(session, "model.attempt.intended", intended)
                self.ledger.unresolved[attempt] = intended
                wave.append((invocation, attempt))
                metadata.append((task, packet, intended))
            failures, new_hold = 0, False
            for index, response in self.gateway.codex_dispatch(session, self.provider, wave, len(wave)):
                task, packet, intended = metadata[index]
                response_ref = self.ledger.artifacts.put(asdict(response))
                cost = runner.billed(packet, response)
                raw = response.raw_response or {}
                hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intended["reserved_nanousd"]
                parsed, error = None, None
                if response.payload is not None:
                    try:
                        parsed = contract.parse(packet, response.payload)
                    except (KeyError, TypeError, ValueError, ResearchError) as caught:
                        error = type(caught).__name__ + ":" + str(caught)[:180]
                row = {"plan": self.plan["_record_id"], "task_key": task["task_key"], "phase": PHASE, "category": "audit",
                    "execution_amendment": self.amendment["_record_id"], "diagnostic_plan": self.diagnostic["_record_id"],
                    "packet": task["packet"], "request": intended["request"], "response": response_ref, "attempt": intended["attempt"],
                    "parsed": self.ledger.artifacts.put(parsed) if parsed else None, "cost_nanousd": cost,
                    "reserved_nanousd": intended["reserved_nanousd"] if hold else 0, "hold": hold, "validation_error": error,
                    "http_status": raw.get("http_status"), "at": utc()}
                identifier = self.ledger.record(session, "cyber_dossier_response", task["task_key"], row)
                self.results[task["task_key"]] = {**row, "_record_id": identifier}
                if hold:
                    self.ledger.unresolved[intended["attempt"]]["cost_nanousd"] = cost
                else:
                    self.complete(session, intended, response_ref, identifier, "valid" if parsed else "invalid")
                failures += int(parsed is None)
                new_hold |= hold
            self.phase_tasks_completed = sum(t["task_key"] in self.results for t in tasks)
            self.checkpoint(diagnostic_plan=self.diagnostic["_record_id"], phase_tasks_planned=len(tasks),
                phase_tasks_completed=self.phase_tasks_completed, phase_task_set_sha256=digest([t["task_key"] for t in tasks]))
            if new_hold or failures >= 3:
                raise runner.PipelineStop("summary_diagnostic_unknown_or_repeated_invalid")
            if len(wave) != len(remaining[start:start+4]):
                raise runner.PipelineStop("summary_diagnostic_partial_budget_wave")

    def diagnostic_report(self, session):
        details, counts = [], {}
        pending = {v["task_key"]: v for v in self.ledger.unresolved.values()}
        for task in self.diagnostic["tasks"]:
            row = self.results.get(task["task_key"])
            parsed = self.ledger.artifacts.read(row["parsed"]) if row and row["parsed"] and not row["hold"] else None
            unresolved = pending.get(task["task_key"])
            label = parsed["label"] if parsed else "unknown_hold" if unresolved or (row and row["hold"]) else "invalid" if row else "not_attempted"
            stratum = task["selection"]["stratum"]
            counts.setdefault(stratum, Counter())[label] += 1
            details.append({"selection": task["selection"], "response_record": row["_record_id"] if row else None,
                            "unresolved_attempt": unresolved["attempt"] if unresolved else None,
                            "outcome": label, "parsed": parsed, "validation_error": row.get("validation_error") if row else None})
        result = {"at": utc(), "plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "diagnostic_plan": self.diagnostic["_record_id"], "selected": len(details),
            "stored_diagnostic_responses": sum(t["task_key"] in self.results for t in self.diagnostic["tasks"]),
            "attempted_diagnostic_tasks": sum(t["task_key"] in self.results or t["task_key"] in pending for t in self.diagnostic["tasks"]),
            "stratum_labels": {k: dict(v) for k, v in counts.items()}, "details_artifact": self.ledger.artifacts.put(details),
            **runner.accounting(list(self.results.values()), self.ledger.unresolved), **self.hold_lineage(),
            "diagnostic_budget": self.diagnostic_commitment(), "diagnostic_cap_nanousd": DIAGNOSTIC_CAP,
            "original_deadline": self.deadline, "old_gates_modified": False, "summaries_regenerated": 0,
            "human_validated": False, "population_accuracy_estimate": False,
            "limitations": "Fixed adaptive diagnostic, not an independent population sample or permission to relax a failed gate. Source examination is self-reported; exact citations do not establish entailment.",
            "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_summary_fidelity_diagnostic_report", digest(result), result)
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
            objective="Independently diagnose retained summary fidelity within the original dossier budget",
            actor="codex:astra-summary-fidelity-diagnostic")))
    finally:
        study.close()
