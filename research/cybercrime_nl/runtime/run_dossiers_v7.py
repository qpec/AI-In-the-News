"""Technical v7 extension: explicitly defer untouched oversized seed packets."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path

import run_dossiers_v6 as parent
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import audited_handler

BASE = parent.parent
ROOT, CAP, PARAMETERS = parent.ROOT, parent.CAP, parent.PARAMETERS
METHOD = "cybercrime-four-process-dossiers-20261023-v7"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V7.md"
PARENT_AMENDMENT = "464b6c795b8c9bee7930b150c3343e19cc65c50b36e649d297bc95510d253ce6"
PARENT_REPORT = "bb860bb5ca35cc5a80d0684b20aa6db5be56550f9bac33325d6edde5794f1f5b"
PASSED_REPORT = "4f8a3c089cca17c3bfce3ced418a96553837fe402d271b39cc0f965cbe6c71cf"
PipelineStop = parent.PipelineStop


def implementation():
    paths = [Path(__file__), METHOD_DOCUMENT, ROOT / "research/cybercrime_nl/runtime/run_dossiers_v7_with_key.ps1"]
    return {**parent.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def classify_seed_packets(proposals, prior, documents, count_tokens):
    """Pure preparation: old article sets first, exact untouched wire at 32k."""
    entries, seen = [], set()
    for proposal in proposals:
        members = list(proposal["document_ids"])
        identities = tuple(sorted(members))
        if not members or len(members) != len(set(members)) or identities in seen:
            raise AuditError("dossier_v7_seed_proposal_identity")
        seen.add(identities)
        pairs = [list(pair) for pair in combinations(members, 2)]
        item = {"proposal_sha256": digest(proposal), "document_ids": members,
                "intended_pairs": pairs, "intended_pair_count": len(pairs), "packet": None}
        if identities in prior:
            # Do not construct an amended request for an already attempted set,
            # even if its old wire would now fail a newly constructed prompt.
            packet = prior[identities]
            if sorted(packet["document_ids"]) != sorted(members):
                raise AuditError("dossier_v7_prior_seed_identity_changed")
            entries.append({**item, "state": "reused_prior_attempt", "packet": packet,
                            "input_tokens_proxy": packet["input_tokens_proxy"], "wire_bytes": packet.get("wire_bytes")})
            continue
        observed = {}

        def counted(wire):
            value = count_tokens(wire)
            observed.update(input_tokens_proxy=value, wire_bytes=len(wire.encode("utf-8")))
            return value

        try:
            packet = BASE.contract.seed_request([documents[i] for i in members], count_tokens=counted,
                                               max_tokens=PARAMETERS["packet_tokens"])
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity":
                raise
            entries.append({**item, "state": "deferred_capacity_unjudged", "reason": str(error),
                "provider_attempted": False, "provider_unknown": False, "billing_hold": False,
                "token_limit": PARAMETERS["packet_tokens"], "wire_byte_limit": BASE.contract.MAX_WIRE_BYTES,
                **observed})
            continue
        entries.append({**item, "state": "untouched_request_fits", "packet": packet, **observed})
    return entries


def seed_census(entries):
    counts = Counter(row["state"] for row in entries)
    deferred = [r for r in entries if r["state"] == "deferred_capacity_unjudged"]
    fitting_ids = {i for r in entries if r["state"] != "deferred_capacity_unjudged" for i in r["document_ids"]}
    deferred_ids = {i for r in deferred for i in r["document_ids"]}
    return {"proposed_packets": len(entries), "reused_prior_attempt_packets": counts["reused_prior_attempt"],
        "untouched_fitting_packets": counts["untouched_request_fits"], "deferred_unjudged_packets": len(deferred),
        "proposed_distinct_articles": len({i for r in entries for i in r["document_ids"]}),
        "fitting_or_reused_distinct_articles": len(fitting_ids), "deferred_distinct_articles": len(deferred_ids),
        "fitting_and_deferred_article_overlap": len(fitting_ids & deferred_ids),
        "intended_within_packet_pairs": sum(r["intended_pair_count"] for r in entries),
        "deferred_unasked_within_packet_pairs": sum(r["intended_pair_count"] for r in deferred),
        "distinct_intended_within_packet_pairs": len({tuple(sorted(p)) for r in entries for p in r["intended_pairs"]}),
        "distinct_deferred_unasked_within_packet_pairs": len({tuple(sorted(p)) for r in deferred for p in r["intended_pairs"]}),
        "deferred_maximum_input_tokens_proxy": max((r.get("input_tokens_proxy", 0) for r in deferred), default=0),
        "token_limit": PARAMETERS["packet_tokens"], "wire_byte_limit": BASE.contract.MAX_WIRE_BYTES,
        "article_inputs_or_questions_changed": False, "packets_split": False,
        "deferred_are_provider_unknowns": False, "deferred_billing_holds": 0,
        "later_assignment_and_recovery_eligible": True, "model_calls": 0}


class Study(parent.Study):
    @audited_handler
    def _status(self, session, context, data):
        self._loading_v6 = True
        try:
            parent.Study._status(self, session, context, {"action": "report"})
        finally:
            self._loading_v6 = False
        self.v6_amendment = self.amendment
        if self.v6_amendment["_record_id"] != PARENT_AMENDMENT:
            raise AuditError("dossier_v7_parent_amendment_mismatch")
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment_v7")
        if (self.amendment["implementation"] != implementation()
                or self.amendment["parent_implementation"] != parent.implementation()
                or self.amendment["parent_execution_amendment"] != PARENT_AMENDMENT
                or self.amendment["parent_report"] != PARENT_REPORT
                or self.amendment["passed_pilot_report"] != PASSED_REPORT
                or self.amendment["passed_gate_record"] != self.phases["pilot_v6_gate"]["_record_id"]
                or self.amendment["parent_plan"] != self.plan["_record_id"]
                or self.amendment["original_deadline"] != self.v6_amendment["original_deadline"]):
            raise AuditError("dossier_v7_amendment_binding_mismatch")
        self.hold_lineage()
        if data["action"] == "report":
            return self.report(session)
        if data["action"] != "run" or self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("dossier_explicit_paid_execution_required")
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

    def register_amendment(self, session, context):
        if not self.config.offline:
            raise AuditError("dossier_amendment_must_be_offline")
        self.absent("cyber_dossier_execution_amendment_v7")
        if self.hold_lineage()["new_unresolved_holds"]:
            raise AuditError("dossier_v7_new_hold_before_registration")
        report = self.ledger.get(PARENT_REPORT, "cyber_dossier_report")
        passed = self.ledger.get(PASSED_REPORT, "cyber_dossier_report")
        gate = self.phase(session, "pilot_v6_gate")
        budget = BASE.accounting(list(self.results.values()), self.ledger.unresolved)
        if (not gate or not gate["passed"] or any(r["execution_amendment"] != PARENT_AMENDMENT
            or r["plan"] != self.plan["_record_id"] or r["pilot_gate"] != gate for r in (report, passed))
                or any(budget[k] < report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))):
            raise AuditError("dossier_v7_parent_report_or_gate_changed")
        code = implementation()
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": code, "parent_plan": self.plan["_record_id"],
            "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
            "procedure": "Zero-model complete seed request fit census; reuse old attempts, defer only untouched exact capacity failures; unchanged semantics and passed gate."}})["id"]
        proposals = self.phase(session, "seed_proposals")
        if not proposals:
            raise AuditError("dossier_v7_retained_seed_frame_required")
        packets = sorted(proposals["packets"], key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
        entries = classify_seed_packets(packets, self.seed_attempts(), self.documents, self.count)
        for row in entries:
            packet = row.pop("packet")
            row["packet_artifact"] = self.ledger.artifacts.put(packet) if packet else None
        census = seed_census(entries)
        amendment = {"method": METHOD, "parent_plan": self.plan["_record_id"], "parent_implementation": parent.implementation(),
            "parent_execution_amendment": PARENT_AMENDMENT, "parent_report": PARENT_REPORT,
            "passed_pilot_report": PASSED_REPORT, "passed_gate_record": self.phases["pilot_v6_gate"]["_record_id"],
            "ancestor_execution_amendments": {**self.v6_amendment["ancestor_execution_amendments"], "v6": PARENT_AMENDMENT},
            **{k: self.v6_amendment[k] for k in ("diagnostic_plan", "diagnostic_amendment", "diagnostic_report", "v4_diagnostic",
                "v5_diagnostic", "quarantined_document_ids", "quarantined_group_ids", "main_cap_nanousd", "audit_cap_nanousd",
                "contingency_nanousd", "pilot_main_cap_nanousd", "pilot_audit_cap_nanousd", "minimum_incoming_articles",
                "pilot_selection_artifact", "original_deadline")},
            "v6_pilot_budget_baseline": {"legacy_response_keys": self.v6_amendment["legacy_response_keys"],
                "legacy_unresolved_attempts": self.v6_amendment["legacy_unresolved_attempts"]},
            "seed_capacity_census": census, "seed_packet_plan_artifact": self.ledger.artifacts.put(entries),
            "seed_proposals_sha256": digest(packets), "implementation": code, "versions": {"protocol": protocol},
            "legacy_unresolved_attempts": sorted(self.ledger.unresolved), "legacy_budget": budget,
            "legacy_response_keys": sorted(self.results), "cap_nanousd": CAP, "at": utc()}
        identity = self.ledger.record(session, "cyber_dossier_execution_amendment_v7", METHOD, amendment)
        return {"id": identity, "parent_plan": self.plan["_record_id"], "parent_report": PARENT_REPORT,
                "passed_gate_preserved": True, "original_deadline": amendment["original_deadline"],
                "legacy_budget": budget, "seed_capacity_census": census, "paid_calls": 0}

    def pilot_budget(self, category):
        baseline = getattr(self, "v6_amendment", self.amendment)
        legacy = set(baseline["legacy_response_keys"])
        rows = [r for k, r in self.results.items() if k in self.pilot_task_keys and k not in legacy and r["category"] == category]
        pending = {a: r for a, r in self.ledger.unresolved.items()
            if a not in baseline["legacy_unresolved_attempts"] and r["task_key"] in self.pilot_task_keys
            and r["task_key"] not in legacy and r.get("category") == category}
        return BASE.accounting(rows, pending)

    def seed_results(self, session, packets, label):
        self.current_phase = "2_full_article_seed_verification_" + label
        saved = self.phase(session, label + "_seeds")
        if saved:
            return saved
        if label != "full_v6" or digest(packets) != self.amendment["seed_proposals_sha256"]:
            raise AuditError("dossier_v7_seed_frame_changed")
        entries = self.ledger.artifacts.read(self.amendment["seed_packet_plan_artifact"])
        if [digest(p) for p in packets] != [r["proposal_sha256"] for r in entries]:
            raise AuditError("dossier_v7_seed_order_changed")
        requests = [self.ledger.artifacts.read(row["packet_artifact"]) for row in entries if row["packet_artifact"]]
        replies = self.calls(session, requests)
        pair_answers, clarity, covered = [], {}, set()
        for packet, reply in zip(requests, replies, strict=True):
            covered.update(packet["document_ids"])
            for answer in (reply or {}).get("answers", {}).values():
                if answer.get("kind") == "pair":
                    pair_answers.append(answer)
                elif answer.get("kind") == "clarity":
                    clarity[answer["document_id"]] = answer
        partition = BASE.candidates.complete_link_partition(sorted(covered), pair_answers,
                    clarity=clarity, threshold=PARAMETERS["positive_confidence"])
        groups = {digest(["seed", sorted(m)]): sorted(m) for m in partition["groups"] if len(m) > 1}
        quarantine = set(self.amendment["quarantined_document_ids"])
        quarantined = {d: m for d, m in groups.items() if d in self.amendment["quarantined_group_ids"] or quarantine.intersection(m)}
        deferred = [r for r in entries if r["state"] == "deferred_capacity_unjudged"]
        return self.phase(session, label + "_seeds", {"groups": {d: m for d, m in groups.items() if d not in quarantined},
            "pair_answers": pair_answers, "clarity": clarity, "covered": sorted(covered), "partition": partition,
            "quarantined_groups": quarantined,
            "reused_seed_packets": sum(r["state"] == "reused_prior_attempt" for r in entries),
            "failed_packets": sum(r is None for r in replies), "packets": len(requests),
            "proposed_packets": len(entries), "capacity_deferred_packets": deferred,
            "capacity_deferred_document_ids": sorted({i for r in deferred for i in r["document_ids"]}),
            "unasked_within_deferred_pairs": sum(r["intended_pair_count"] for r in deferred),
            "capacity_deferral_is_provider_unknown": False, "deferred_articles_remain_assignment_eligible": True})

    def report(self, session):
        if getattr(self, "_loading_v6", False) or getattr(self, "_loading_parent", False):
            return None
        # The v6 public report remains source-free and cumulative. Preserve that
        # immutable intermediate projection, then add the technical extension's
        # explicit capacity denominator in a separately retained final report.
        previous = super().report(session)
        seeds = self.phase(session, "full_v6_seeds")
        report = {k: v for k, v in previous.items() if k != "id"}
        report.update(parent_report=PARENT_REPORT, technical_extension_version=7,
            base_report_record=previous["id"], passed_pilot_report=PASSED_REPORT,
            seed_capacity={"frozen_census": self.amendment["seed_capacity_census"],
                "execution_summary": {"constructed_or_reused_requests": seeds["packets"],
                    "capacity_deferred_packets": len(seeds["capacity_deferred_packets"]),
                    "capacity_deferred_distinct_articles": len(seeds["capacity_deferred_document_ids"]),
                    "unasked_within_deferred_pairs": seeds["unasked_within_deferred_pairs"],
                    "stored_invalid_or_unknown_seed_packets": seeds["failed_packets"],
                    "covered_seed_article_ids_count": len(seeds["covered"]),
                    "valid_seed_clarity_answers": sum(a.get("status") == "valid" for a in seeds["clarity"].values()),
                    "valid_seed_pair_answers": sum(a.get("status") == "valid" for a in seeds["pair_answers"]),
                    "deferred_are_provider_unknowns": False} if seeds else None})
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
        result = study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Prepare or execute technical seed-capacity deferral within the unchanged USD50 dossier study",
            actor="codex:cybercrime-dossiers")
        print(json.dumps(result), flush=True)
    finally:
        study.close()


if __name__ == "__main__":
    main()
