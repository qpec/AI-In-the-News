"""Technical v8 extension: restore retained request question order without retries."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import run_dossiers_v7 as parent
from newsresearch.common import AuditError, Config, ResearchError, canonical, digest, utc
from newsresearch.runtime import audited_handler

BASE, ROOT, CAP = parent.BASE, parent.ROOT, parent.CAP
METHOD = "cybercrime-four-process-dossiers-20261023-v8"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V8.md"
PARENT_AMENDMENT = "d4cdbc4d8ced670cb991353e1b05a441439ccbc2ca6afa75f46cc1675e9d93c8"
PARENT_REPORT = "f51b4ce032d817f0143c4706dda0a7de4287b44b762a5de8645ab7d76e179e20"
DIAGNOSTIC = "0f75fa4b4cccc9f60930dd8a7e3ff0429b9014c536a1a04983831a9bf29bc166"
DIAGNOSTIC_OWNER = BASE.preparation.OWNER.parent / "cybercrime-v7-seed-technical-view-20261023-v1"
SOURCE_RESPONSES = (
    "a1e204ed2ef0f53206010ccef7651690390abc0948733a75c34d02c6b9832058",
    "4bcaddab4935178f1cf58425b8243b43992c1d0f1c56d1a400d6c62cfbc74166",
    "c316137bea2e6619086598bf83a6272a7e1a0fcb6580a0bf9838b44fc1d27ade",
)
ERROR = "ResearchError:dossier_card_decision_binding_mismatch"
NORMALIZATION = "seed-question-map-in-retained-request-list-order-v1"
PipelineStop = parent.PipelineStop


def require(value, message):
    if not value:
        raise AuditError("dossier_v8_" + message)


def implementation():
    paths = [Path(__file__), METHOD_DOCUMENT, ROOT / "research/cybercrime_nl/runtime/run_dossiers_v8_with_key.ps1"]
    return {**parent.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def normalize_seed_packet(packet):
    """Only change dictionary iteration order, using the retained ordered wire."""
    require(packet.get("phase") == "seed", "normalization_requires_seed")
    try:
        names = [q["name"] for q in packet["request"]["questions"]]
        mapping = packet["question_map"]
        require(all(isinstance(n, str) for n in names) and len(names) == len(set(names))
                and isinstance(mapping, dict) and set(names) == set(mapping), "question_name_coverage")
        normalized = {**packet, "question_map": {name: mapping[name] for name in names}}
        require(canonical(normalized) == canonical(packet)
                and normalized["request"] == packet["request"]
                and digest(packet["request"]) == packet["request_sha256"], "canonical_identity_changed")
        return normalized
    except (KeyError, TypeError, ValueError) as error:
        raise AuditError("dossier_v8_question_map_invalid") from error


def revalidate_retained(row, packet, envelope, stored_request):
    """Full frozen checks before/after ordering only; never fix model output."""
    require(row["phase"] == "seed" and row["validation_error"] == ERROR and not row["hold"]
            and not row["parsed"] and 200 <= (row["http_status"] or 0) < 300
            and type(row["cost_nanousd"]) is int and row["cost_nanousd"] >= 0
            and row["reserved_nanousd"] == 0, "response_not_eligible_settled_failure")
    require(packet["request"] == stored_request and digest(stored_request) == packet["request_sha256"], "original_request_changed")
    payload = envelope.get("payload")
    require(isinstance(payload, dict), "original_payload_missing")
    try:
        BASE.contract.parse_decisions(packet, payload)
    except ResearchError as error:
        require(type(error).__name__ + ":" + str(error) == ERROR, "old_parser_failure_changed")
    else:
        raise AuditError("dossier_v8_old_parser_did_not_reproduce_failure")
    normalized = normalize_seed_packet(packet)
    parsed = BASE.contract.parse_decisions(normalized, payload)
    require(parsed.get("status") == "valid", "revalidation_not_fully_valid")
    return normalized, parsed


class Study(parent.Study):
    @audited_handler
    def _status(self, session, context, data):
        self._loading_v7 = True
        try:
            parent.Study._status(self, session, context, {"action": "report"})
        finally:
            self._loading_v7 = False
        self.v7_amendment = self.amendment
        require(self.v7_amendment["_record_id"] == PARENT_AMENDMENT, "parent_amendment_mismatch")
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment_v8")
        require(self.amendment["implementation"] == implementation()
            and self.amendment["parent_implementation"] == parent.implementation()
            and self.amendment["parent_execution_amendment"] == PARENT_AMENDMENT
            and self.amendment["parent_report"] == PARENT_REPORT
            and self.amendment["eligible_source_response_ids"] == sorted(SOURCE_RESPONSES)
            and self.amendment["normalization_version"] == NORMALIZATION
            and all(self.amendment[k] == self.v7_amendment[k] for k in ("parent_plan", "original_deadline",
                "passed_pilot_report", "passed_gate_record", "seed_capacity_census", "seed_packet_plan_artifact",
                "seed_proposals_sha256", "v6_pilot_budget_baseline")), "amendment_binding_mismatch")
        self.hold_lineage()
        self.load_revalidations()
        if data["action"] == "report":
            return self.report(session)
        require(data["action"] == "run" and not self.config.offline and data.get("allow_paid_execution")
                and os.environ.get("OPENAI_API_KEY"), "explicit_paid_execution_required")
        self.deadline = self.amendment["original_deadline"]
        self.provider = BASE.transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        try:
            if not self.phase(session, "pilot_v6_gate")["passed"]:
                raise PipelineStop("pilot_v6_gate_not_passed")
            self.full_pipeline(session)
            stop = "phase_complete"
        except PipelineStop as error:
            stop = str(error)
            self.ledger.record(session, "cyber_dossier_stopped", digest([utc(), stop]), {
                "execution_amendment": self.amendment["_record_id"], "reason": stop,
                "phase": self.current_phase, "at": utc()})
        self.checkpoint(stop_reason=stop)
        return self.report(session)

    def diagnostic_binding(self):
        source = BASE.preparation.screening.original.base.pilot.Source(DIAGNOSTIC_OWNER)
        try:
            rows = [r for r in source.rows("cyber_dossier_seed_v7_technical_view") if r["_record_id"] == DIAGNOSTIC]
            require(len(rows) == 1, "fixed_diagnostic_missing")
            row = rows[0]
            require(row["execution_amendment"] == PARENT_AMENDMENT and row["source_report"] == PARENT_REPORT
                and sorted(c["record"] for c in row["cases"] if c["validation_error"] == ERROR) == sorted(SOURCE_RESPONSES)
                and row["new_model_calls"] == 0 and row["new_holds"] == 0, "diagnostic_scope_changed")
            return {"owner": str(DIAGNOSTIC_OWNER), "record_id": DIAGNOSTIC}
        finally:
            source.close()

    def register_amendment(self, session, context):
        require(self.config.offline, "amendment_must_be_offline")
        self.absent("cyber_dossier_execution_amendment_v8")
        require(not self.rows("cyber_dossier_seed_revalidation"), "partial_revalidation_requires_diagnosis")
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
            "procedure": "Check every retained seed packet's exact question coverage/canonical identity. Normalize map iteration only from retained request list. For exactly three fixed settled failures reproduce the frozen error then retain separately versioned fully checked derived parsing. No model calls/retries/changed outputs or original rows; same semantic gate, capacity, cost, holds and deadline."}})["id"]
        diagnostic = self.diagnostic_binding()
        entries = self.ledger.artifacts.read(self.v7_amendment["seed_packet_plan_artifact"])
        packets = [self.ledger.artifacts.read(r["packet_artifact"]) for r in entries if r["packet_artifact"]]
        reordered = 0
        for packet in packets:
            normalized = normalize_seed_packet(packet)
            reordered += list(packet["question_map"]) != list(normalized["question_map"])
        require(len(packets) == self.v7_amendment["seed_capacity_census"]["proposed_packets"]
                - self.v7_amendment["seed_capacity_census"]["deferred_unjudged_packets"], "seed_frame_count_changed")
        derived = []
        eligible = sorted((r for r in self.results.values() if r["_record_id"] in SOURCE_RESPONSES), key=lambda r: r["_record_id"])
        require(len(eligible) == len(SOURCE_RESPONSES), "fixed_response_frame_missing")
        for row in eligible:
            require(row["execution_amendment"] == PARENT_AMENDMENT and row["attempt"] not in self.ledger.unresolved, "source_attempt_not_settled")
            packet = self.ledger.artifacts.read(row["packet"])
            require(self.task_key(packet) == row["task_key"], "source_task_binding_changed")
            normalized, parsed = revalidate_retained(row, packet, self.ledger.artifacts.read(row["response"]), self.ledger.artifacts.read(row["request"]))
            value = {"method": METHOD, "versions": {"protocol": protocol}, "parent_plan": self.plan["_record_id"],
                "parent_execution_amendment": PARENT_AMENDMENT, "source_response_record": row["_record_id"],
                "source_response_record_sha256": digest(row), "task_key": row["task_key"], "source_attempt": row["attempt"],
                "source_packet": row["packet"], "source_request": row["request"], "source_response": row["response"],
                "source_validation_error": ERROR, "normalization_version": NORMALIZATION,
                "canonical_packet_sha256": digest(normalized), "request_sha256": packet["request_sha256"],
                "parsed": self.ledger.artifacts.put(parsed), "status": "valid", "model_calls": 0,
                "cost_nanousd": 0, "original_rows_unchanged": True, "at": utc()}
            identity = self.ledger.record(session, "cyber_dossier_seed_revalidation", row["_record_id"], value)
            derived.append(identity)
        amendment = {**{k: v for k, v in self.v7_amendment.items() if not k.startswith("_")},
            "method": METHOD, "parent_execution_amendment": PARENT_AMENDMENT, "parent_report": PARENT_REPORT,
            "parent_implementation": parent.implementation(), "implementation": code, "versions": {"protocol": protocol},
            "ancestor_execution_amendments": {**self.v7_amendment["ancestor_execution_amendments"], "v7": PARENT_AMENDMENT},
            "diagnostic": diagnostic, "eligible_source_response_ids": sorted(SOURCE_RESPONSES), "source_validation_error": ERROR,
            "normalization_version": NORMALIZATION, "derived_revalidation_records": derived,
            "seed_order_integrity": {"checked_packets": len(packets), "map_order_restored_packets": reordered,
                "canonical_packet_changes": 0, "request_changes": 0, "deferred_packets": len(entries) - len(packets), "model_calls": 0},
            "legacy_budget": budget, "legacy_unresolved_attempts": sorted(self.ledger.unresolved),
            "legacy_response_keys": sorted(self.results), "at": utc()}
        identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v8", METHOD, amendment)
        return {"id": identity, "parent_plan": self.plan["_record_id"], "parent_report": PARENT_REPORT,
            "passed_gate_preserved": True, "original_deadline": amendment["original_deadline"], "legacy_budget": budget,
            "seed_order_integrity": amendment["seed_order_integrity"], "seed_capacity_census": amendment["seed_capacity_census"],
            "seed_revalidation": {"attempted": len(eligible), "valid": len(derived), "still_invalid": 0, "model_calls": 0,
                                  "original_rows_unchanged": True, "derived_record_ids": derived}, "paid_calls": 0}

    def load_revalidations(self):
        rows = self.rows("cyber_dossier_seed_revalidation")
        require({r["_record_id"] for r in rows} == set(self.amendment["derived_revalidation_records"])
                and len(rows) == len(SOURCE_RESPONSES), "derived_record_set_changed")
        self.derived_parsed = {}
        for value in rows:
            row = self.results.get(value["task_key"])
            require(row and row["_record_id"] in SOURCE_RESPONSES and row["_record_id"] == value["source_response_record"]
                and digest(row) == value["source_response_record_sha256"] and row["attempt"] not in self.ledger.unresolved
                and value["parent_plan"] == self.plan["_record_id"] and value["parent_execution_amendment"] == PARENT_AMENDMENT
                and value["normalization_version"] == NORMALIZATION and value["status"] == "valid"
                and value["model_calls"] == value["cost_nanousd"] == 0 and value["original_rows_unchanged"] is True
                and all(value["source_" + key] == row[key] for key in ("packet", "request", "response")), "derived_source_binding_changed")
            normalized, parsed = revalidate_retained(row, self.ledger.artifacts.read(row["packet"]),
                self.ledger.artifacts.read(row["response"]), self.ledger.artifacts.read(row["request"]))
            require(digest(normalized) == value["canonical_packet_sha256"] and normalized["request_sha256"] == value["request_sha256"]
                    and self.ledger.artifacts.read(value["parsed"]) == parsed, "derived_parse_changed")
            self.derived_parsed[value["task_key"]] = parsed
        require(len(self.derived_parsed) == len(SOURCE_RESPONSES), "duplicate_derived_task")

    def calls(self, session, packets):
        return super().calls(session, [normalize_seed_packet(p) if p["phase"] == "seed" else p for p in packets])

    def parsed(self, packet):
        return getattr(self, "derived_parsed", {}).get(self.task_key(packet)) or super().parsed(packet)

    def report(self, session):
        if any(getattr(self, key, False) for key in ("_loading_v7", "_loading_v6", "_loading_parent")):
            return None
        previous = super().report(session)
        report = {k: v for k, v in previous.items() if k != "id"}
        report.update(parent_report=PARENT_REPORT, technical_extension_version=8, base_report_record=previous["id"],
            seed_order_integrity=self.amendment["seed_order_integrity"],
            seed_revalidation={"attempted": len(SOURCE_RESPONSES), "valid": len(self.derived_parsed),
                "still_invalid": len(SOURCE_RESPONSES) - len(self.derived_parsed), "model_calls": 0,
                "original_rows_unchanged": True, "derived_record_ids": self.amendment["derived_revalidation_records"]})
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
            objective="Restore exact retained seed question ordering within the unchanged USD50 study", actor="codex:cybercrime-dossiers")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
