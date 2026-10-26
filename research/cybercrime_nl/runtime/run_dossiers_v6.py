"""Prospective retained-decision reanalysis and atomic expanded-group checks.

Frozen v5 supplies preflight, exact request transport, accounting and no-retry.
This explicit subclass adds a registered inference rule and pilot subcaps; it
does not replace functions or mutate any ancestor module.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path

import numpy as np

import run_dossiers_v5 as parent
import dossier_contract_v6 as contract
from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import audited_handler

ROOT, CAP, PARAMETERS = parent.ROOT, parent.CAP, parent.PARAMETERS
METHOD = "cybercrime-four-process-dossiers-20261023-v6"
METHOD_DOCUMENT = ROOT / "research/cybercrime_nl/DOSSIER_AMENDMENT_V6.md"
PARENT_AMENDMENT = "9f531f9473e28f2773b820b1e5fbdf15eb9a44ce6fedab9ba1f2aad538d50375"
PARENT_REPORT = "60d21154865be8e8a093b96236da56074c40d6d88a62f783f9284ee9c205ade1"
DIAGNOSTIC = "c3f0fc25655d655566371c9cbc0d1446ae7615c1681721d5cf22fe6c5bef1ea9"
DIAGNOSTIC_OWNER = parent.preparation.OWNER.parent / "cybercrime-v5-assignment-view-20261023-v1"
PILOT_MAIN_CAP = 1_000_000_000
PILOT_AUDIT_CAP = 2_500_000_000
MIN_INCOMING = 6
PipelineStop = parent.PipelineStop


def implementation():
    paths = [Path(__file__), Path(contract.__file__), METHOD_DOCUMENT,
             ROOT / "research/cybercrime_nl/runtime/run_dossiers_v6_with_key.ps1"]
    return {**parent.implementation(), **{str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                         for p in paths}}


def binding(card):
    return {key: card[key] for key in ("card_version", "membership_revision", "representation_type")}


def atomic_commit(before, plan, accepted):
    """Failed components preserve every original group; no partial expansion."""
    if not set(accepted) <= set(plan["expansions"]):
        raise AuditError("dossier_v6_unknown_accepted_expansion")
    result = {d: list(m) for d, m in before.items()}
    for dossier, expansion in plan["expansions"].items():
        if dossier not in accepted:
            continue
        for original in expansion["original_groups"]:
            result.pop(original, None)
        result[dossier] = list(expansion["document_ids"])
    all_members = [i for group in result.values() for i in group]
    if len(all_members) != len(set(all_members)) or not {i for g in before.values() for i in g} <= set(all_members):
        raise AuditError("dossier_v6_atomic_membership_integrity")
    return result


def bind_rival_edges(edges, groups):
    result = []
    for edge in edges:
        members = sorted(groups[edge["dossier_id"]])
        if edge["original_answer"]["membership_revision"] != digest(members):
            raise AuditError("dossier_v6_uncertain_rival_membership_changed")
        result.append({**edge, "source_document_ids": members,
                       "frozen_membership_revision": digest(members), "treated_as_negative": False})
    return result


def nonjoined_frame(retrieval_pairs, membership, unresolved_edges):
    base = {tuple(sorted((p["left"], p["right"]))) for p in retrieval_pairs}
    rivals = {tuple(sorted((edge["document_id"], member))) for edge in unresolved_edges
              for member in edge["source_document_ids"] if member != edge["document_id"]}
    pool = {pair for pair in base | rivals if pair[0] not in membership or pair[1] not in membership
            or membership[pair[0]] != membership[pair[1]]}
    return pool, {"base_retrieval_pairs": len(base), "uncertain_rival_pairs": len(rivals),
                  "added_uncertain_rival_pairs": len(rivals - base), "deduplicated_union_pairs": len(base | rivals),
                  "candidate_pool": len(pool)}


class Study(parent.Study):
    @audited_handler
    def _status(self, session, context, data):
        # Run the unchanged complete ancestor chain, without emitting a stale
        # ancestor report. No paid branch is entered by this nested operation.
        self._loading_parent = True
        try:
            parent.Study._status(self, session, context, {"action": "report"})
        finally:
            self._loading_parent = False
        self.parent_amendment = self.amendment
        if self.parent_amendment["_record_id"] != PARENT_AMENDMENT:
            raise AuditError("dossier_v6_parent_amendment_mismatch")
        if data["action"] == "amend":
            return self.register_amendment(session, context)
        self.amendment = self.one("cyber_dossier_execution_amendment_v6")
        if (self.amendment["implementation"] != implementation()
                or self.amendment["parent_execution_amendment"] != PARENT_AMENDMENT
                or self.amendment["parent_implementation"] != parent.implementation()
                or self.amendment["parent_report"] != PARENT_REPORT
                or self.amendment["parent_plan"] != self.plan["_record_id"]
                or self.amendment["original_deadline"] != self.one("cyber_dossier_first_launch")["deadline"]
                or self.amendment["pilot_main_cap_nanousd"] != PILOT_MAIN_CAP
                or self.amendment["pilot_audit_cap_nanousd"] != PILOT_AUDIT_CAP):
            raise AuditError("dossier_v6_amendment_binding_mismatch")
        self.hold_lineage()
        self.pilot_selection = self.ledger.artifacts.read(self.amendment["pilot_selection_artifact"])
        self.pilot_task_keys = set(self.pilot_selection["pilot_task_keys"])
        if data["action"] == "report":
            return self.report(session)
        if self.config.offline or not data.get("allow_paid_execution") or not os.environ.get("OPENAI_API_KEY"):
            raise AuditError("dossier_explicit_paid_execution_required")
        self.deadline = self.amendment["original_deadline"]
        self.provider = parent.transport.UnifiedTransport(before_dispatch=self.before_dispatch)
        try:
            if data["action"] == "pilot":
                self.pilot(session)
            elif data["action"] == "run":
                gate = self.phase(session, "pilot_v6_gate")
                if not gate or not gate["passed"] or self.hold_lineage()["new_unresolved_holds"]:
                    raise PipelineStop("pilot_v6_gate_not_passed")
                self.full_pipeline(session)
            else:
                raise AuditError("dossier_unknown_action")
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
        self.absent("cyber_dossier_execution_amendment_v6")
        self.hold_lineage()  # Preserve every old hold before capturing a baseline.
        report = self.ledger.get(PARENT_REPORT, "cyber_dossier_report")
        budget = parent.accounting(list(self.results.values()), self.ledger.unresolved)
        if (report["execution_amendment"] != PARENT_AMENDMENT or report["plan"] != self.plan["_record_id"]
                or any(budget[k] < report[k] for k in ("settled_nanousd", "held_nanousd", "committed_nanousd", "unresolved_holds"))):
            raise AuditError("dossier_v6_parent_liability_changed")
        code = implementation()
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation": code, "parent_plan": self.plan["_record_id"],
            "method_specification": METHOD_DOCUMENT.read_text(encoding="utf-8"),
            "limitation": "Adaptive retained-v5 reanalysis; no independent holdout or population inference."}})["id"]
        diagnostic = self.read_diagnostic()
        selection = self.prepare_pilot(session)
        ancestors = {**self.parent_amendment["ancestor_execution_amendments"], "v5": PARENT_AMENDMENT}
        amendment = {"method": METHOD, "parent_plan": self.plan["_record_id"],
            "parent_execution_amendment": PARENT_AMENDMENT, "parent_implementation": parent.implementation(),
            "parent_report": PARENT_REPORT, "ancestor_execution_amendments": ancestors,
            "v5_diagnostic": diagnostic,
            **{k: self.parent_amendment[k] for k in ("diagnostic_plan", "diagnostic_amendment", "diagnostic_report",
                "v4_diagnostic", "quarantined_document_ids", "quarantined_group_ids")},
            "main_cap_nanousd": PARAMETERS["non_audit_cap_nanousd"], "audit_cap_nanousd": PARAMETERS["audit_cap_nanousd"],
            "contingency_nanousd": 0, "pilot_main_cap_nanousd": PILOT_MAIN_CAP,
            "pilot_audit_cap_nanousd": PILOT_AUDIT_CAP, "minimum_incoming_articles": MIN_INCOMING,
            "implementation": code, "versions": {"protocol": protocol},
            "original_deadline": self.parent_amendment["original_deadline"],
            "legacy_unresolved_attempts": sorted(self.ledger.unresolved), "legacy_budget": budget,
            "legacy_response_keys": sorted(self.results), "pilot_selection_artifact": self.ledger.artifacts.put(selection),
            "preparation_forecast": selection["forecast"], "cap_nanousd": CAP, "at": utc()}
        identifier = self.ledger.record(session, "cyber_dossier_execution_amendment_v6", METHOD, amendment)
        return {"id": identifier, "parent_plan": self.plan["_record_id"], "parent_report": PARENT_REPORT,
                "original_deadline": amendment["original_deadline"], "legacy_budget": budget,
                "paid_calls": 0, **selection["forecast"]}

    def read_diagnostic(self):
        source = parent.Source(DIAGNOSTIC_OWNER)
        try:
            head = source.head()
            selected = [r for r in source.rows("cyber_dossier_assignments_v5_view") if r["_record_id"] == DIAGNOSTIC]
            if (len(selected) != 1 or selected[0]["source_report"] != PARENT_REPORT
                    or selected[0]["execution_amendment"] != PARENT_AMENDMENT
                    or selected[0]["plan"] != self.plan["_record_id"]):
                raise AuditError("dossier_v6_diagnostic_changed")
        finally:
            source.close()
        source = parent.Source(DIAGNOSTIC_OWNER)
        try:
            if source.head() != head:
                raise AuditError("dossier_v6_diagnostic_source_changed")
        finally:
            source.close()
        return {"owner": str(DIAGNOSTIC_OWNER), "record_id": DIAGNOSTIC, "source_head": head}

    def eligibility(self, assigned, cards):
        return contract.eligible_assignments(assigned, {d: binding(card) for d, card in cards.items()})

    def freeze_expansions(self, groups, eligibility, *, recovery=False):
        commit = parent.commit_group_proposals if recovery else parent.commit_proposals
        proposed, applied, conflicts = commit(groups, eligibility["proposals"])
        plan = contract.expansion_plan(groups, proposed, applied, eligibility)
        plan["expansions"] = {d: {**e, "document_ids": e["proposed_document_ids"]} for d, e in plan["expansions"].items()}
        return {**plan, "applied": applied, "conflicts": conflicts, "eligibility": eligibility,
                "uncertainty_edges": bind_rival_edges(eligibility["uncertainty_edges"], groups), "recovery": recovery}

    def prepare_group(self, dossier, members):
        """Construct immutable packets offline; no generation or provider call."""
        members = sorted(members)
        revision = digest(members)
        item = {"dossier_id": dossier, "document_ids": members, "membership_revision": revision,
                "card_artifact": None, "luna_packet": None, "astra_packet": None,
                "luna_task_key": None, "astra_task_key": None, "unavailable": None}
        if (dossier, revision) in self.summary_attempts():
            return {**item, "unavailable": "previous_summary_binding_no_card_replacement"}
        if dossier in self.amendment["quarantined_group_ids"] or set(members) & set(self.amendment["quarantined_document_ids"]):
            return {**item, "unavailable": "prior_reference_focus_quarantine"}
        try:
            card = parent.contract.build_evidence_card([self.documents[i] for i in members], dossier, revision,
                                                       count_tokens=self.count, max_tokens=32000)
            old = [r for r in self.rows("cyber_dossier_evidence_card")
                   if (r["dossier_id"], r["membership_revision"]) == (dossier, revision)]
            if len(old) > 1 or old and self.ledger.artifacts.read(old[0]["artifact"]) != card:
                raise AuditError("dossier_v6_existing_card_changed")
            luna = parent.contract.card_quality_request([self.documents[i] for i in members], card,
                count_tokens=self.count, max_tokens=32000, max_output_tokens=2000)
            astra = parent.contract.card_quality_audit_request([self.documents[i] for i in members], card,
                count_tokens=self.count, max_tokens=32000, max_output_tokens=2000)
        except ResearchError as error:
            if str(error) != "dossier_packet_capacity":
                raise
            return {**item, "unavailable": "expanded_group_complete_source_capacity"}
        return {**item, "card_version": card["card_version"], "card_artifact": self.ledger.artifacts.put(card),
                "luna_packet": self.ledger.artifacts.put(luna), "astra_packet": self.ledger.artifacts.put(astra),
                "luna_task_key": self.task_key(luna), "astra_task_key": self.task_key(astra),
                "input_tokens_proxy": {"luna": luna["input_tokens_proxy"], "astra": astra["input_tokens_proxy"]},
                "reserved_nanousd": {"luna": parent.reserve(luna), "astra": parent.reserve(astra)}}

    def prepare_pilot(self, session):
        assigned = self.phase(session, "pilot_v5_seed_assignments")
        challenge = self.phase(session, "pilot_v5_positive_challenge")
        cards = self.phase(session, "pilot_v5_seed_cards")
        gate = self.phase(session, "pilot_v5_gate")
        if not all((assigned, challenge, cards, gate)):
            raise AuditError("dossier_v6_complete_retained_v5_pilot_required")
        groups = {d: members for d, members in challenge["groups"].items() if d in cards["usable"]}
        eligible = self.eligibility(assigned, cards["usable"])
        expansion = self.freeze_expansions(groups, eligible)
        primary = [{**self.prepare_group(d, e["document_ids"]), "expansion": e}
                   for d, e in sorted(expansion["expansions"].items())]
        secondary = []
        for query in sorted(challenge["held_out"], key=lambda i: digest(["v6-withheld-secondary", i])):
            target = challenge["held_out"][query]["dossier_id"]
            secondary.append({**self.prepare_group(target, [*challenge["groups"][target], query]),
                              "query_document_id": query, "hypothesis_only": True})
        seen = set(self.results) | {v["task_key"] for v in self.ledger.unresolved.values()}
        primary_keys = {i["astra_task_key"] for i in primary if i["astra_task_key"]}
        all_keys = {i[k] for i in primary for k in ("luna_task_key", "astra_task_key") if i[k]}
        all_keys.update(i["astra_task_key"] for i in secondary if i["astra_task_key"])

        def reservations(items, role, exclude=()):
            unique = {i[role + "_task_key"]: i for i in items if i[role + "_task_key"]}
            return {k: row["reserved_nanousd"][role] for k, row in unique.items() if k not in seen and k not in exclude}

        main = reservations(primary, "luna")
        audit = reservations(primary, "astra")
        extra = reservations(secondary, "astra", primary_keys)
        forecast = {"eligible_incoming_articles": len(eligible["proposals"]), "primary_groups": len(primary),
            "primary_incoming_articles": sum(len(i["expansion"]["incoming_document_ids"]) for i in primary),
            "primary_unavailable": sum(bool(i["unavailable"]) for i in primary),
            "secondary_groups": len(secondary), "secondary_shared_primary_tasks": sum(i["astra_task_key"] in primary_keys for i in secondary),
            "new_primary_main_requests": len(main), "new_primary_audit_requests": len(audit),
            "new_secondary_audit_requests": len(extra),
            "primary_main_reservations_nanousd": sum(main.values()), "primary_audit_reservations_nanousd": sum(audit.values()),
            "secondary_additional_reservations_nanousd": sum(extra.values()),
            "primary_main_reservations_fit_subcap": sum(main.values()) <= PILOT_MAIN_CAP,
            "primary_audit_reservations_fit_subcap": sum(audit.values()) <= PILOT_AUDIT_CAP,
            "all_audit_reservations_fit_subcap": sum(audit.values()) + sum(extra.values()) <= PILOT_AUDIT_CAP,
            "individual_reservations_nanousd": {"primary_main": list(main.values()), "primary_audit": list(audit.values()),
                                                "secondary_additional_audit": list(extra.values())},
            "tokens": [{"members": len(i["document_ids"]), "incoming": len(i["expansion"]["incoming_document_ids"]),
                        **(i.get("input_tokens_proxy") or {})} for i in primary],
            "pilot_main_cap_nanousd": PILOT_MAIN_CAP, "pilot_audit_cap_nanousd": PILOT_AUDIT_CAP,
            "functional_sample_not_independent_gold": True, "model_calls": 0}
        return {"before_groups": groups, "before_cards": cards["usable"], "expansion_plan": expansion,
            "primary": primary, "secondary": secondary, "pilot_task_keys": sorted(all_keys), "forecast": forecast,
            "retained_v5_gate": gate, "selection_frozen_before_new_labels": True, "replacement_allowed": False}

    def calls(self, session, packets):
        # Frozen parent remains the global cap/STOP/deadline/no-retry authority.
        # Serial pilot admission additionally enforces its $1/$2.50 subcaps.
        if not getattr(self, "pilot_task_keys", set()).intersection(self.task_key(p) for p in packets):
            return super().calls(session, packets)
        replies = []
        for packet in packets:
            key = self.task_key(packet)
            seen = key in self.results or any(v["task_key"] == key for v in self.ledger.unresolved.values())
            if key in self.pilot_task_keys and not seen:
                category = "audit" if packet["request"]["model"] == "gpt-6-astra" else "main"
                budget = self.pilot_budget(category)
                cap = PILOT_AUDIT_CAP if category == "audit" else PILOT_MAIN_CAP
                if budget["committed_nanousd"] + parent.reserve(packet) > cap:
                    raise PipelineStop("v6_pilot_subcap_" + category)
            replies.extend(super().calls(session, [packet]))
            if key in self.pilot_task_keys and replies[-1] is None:
                raise PipelineStop("v6_pilot_new_unknown_or_invalid")
        return replies

    def pilot_budget(self, category):
        legacy = set(self.amendment["legacy_response_keys"])
        rows = [r for k, r in self.results.items() if k in self.pilot_task_keys and k not in legacy and r["category"] == category]
        pending = {a: r for a, r in self.ledger.unresolved.items()
                   if a not in self.amendment["legacy_unresolved_attempts"] and r["task_key"] in self.pilot_task_keys
                   and r["task_key"] not in legacy and r.get("category") == category}
        return parent.accounting(rows, pending)

    def item_result(self, item, role):
        key = item[role + "_task_key"]
        row = self.results.get(key)
        held = any(v["task_key"] == key for v in self.ledger.unresolved.values())
        if held or row and row["hold"]:
            return "unknown", None
        if not row:
            return ("unavailable" if item["unavailable"] else "not_attempted"), None
        result = self.ledger.artifacts.read(row["parsed"]) if row["parsed"] else None
        if result and result.get("status") == "valid":
            expected = {"dossier_id": item["dossier_id"], "membership_revision": item["membership_revision"],
                "card_version": item["card_version"], "representation_type": "evidence_card",
                "phase": "card_quality" if role == "luna" else "card_quality_audit",
                "reference_model": "gpt-6-luna" if role == "luna" else "gpt-6-astra"}
            if any(result.get(key) != value for key, value in expected.items()):
                raise AuditError("dossier_v6_reviewed_membership_binding_changed")
        return ("valid", result) if result and result.get("status") == "valid" else ("invalid", None)

    def pilot_counts(self):
        primary, secondary = self.pilot_selection["primary"], self.pilot_selection["secondary"]
        counts, secondary_counts = Counter(), Counter()
        normal_accepted, validated = set(), set()
        for item in primary:
            ns, normal = self.item_result(item, "luna")
            rs, reference = self.item_result(item, "astra")
            counts["normal_" + ns] += 1
            counts["reference_" + rs] += 1
            if normal:
                counts["normal_label_" + normal["label"]] += 1
            if reference:
                counts["reference_label_" + reference["label"]] += 1
            if normal and normal["label"] == "supported":
                normal_accepted.add(item["dossier_id"])
                if reference and reference["label"] == "supported":
                    validated.add(item["dossier_id"])
                else:
                    counts["normal_accepted_reference_unsupported_or_unavailable"] += 1
        primary_keys = {i["astra_task_key"] for i in primary if i["astra_task_key"]}
        for item in secondary:
            state, result = self.item_result(item, "astra")
            secondary_counts[state] += 1
            if result:
                secondary_counts["label_" + result["label"]] += 1
            secondary_counts["shared_primary_tasks"] += item["astra_task_key"] in primary_keys
        incoming = sum(len(i["expansion"]["incoming_document_ids"]) for i in primary if i["dossier_id"] in validated)
        normal_incoming = sum(len(i["expansion"]["incoming_document_ids"]) for i in primary if i["dossier_id"] in normal_accepted)
        return ({"selected": len(primary), **dict(counts), "normal_supported": len(normal_accepted),
                 "reference_supported": counts["reference_label_supported"],
                 "unavailable": len(primary) - counts["reference_valid"],
                 "normal_incoming_proposals": normal_incoming, "reference_supported_normal_incoming": incoming,
                 "distinct_normal_supported_groups": len(normal_accepted), "distinct_expanded_groups": len(validated),
                 "independent_reference_is_not_an_acceptance_filter": True},
                {"selected": len(secondary), **dict(secondary_counts),
                 "unavailable": len(secondary) - secondary_counts["valid"], "changes_membership": False},
                {"normal": normal_accepted, "validated": validated})

    def pilot(self, session):
        selection = self.pilot_selection
        if self.phase(session, "pilot_v6_gate"):
            return
        for role, phase in (("luna", "v6_primary_expanded_group_quality"), ("astra", "v6_primary_expanded_group_reference")):
            self.current_phase = phase
            packets = [self.ledger.artifacts.read(i[role + "_packet"]) for i in selection["primary"] if i[role + "_packet"]]
            self.calls(session, packets)
        primary, secondary, sets = self.pilot_counts()
        old = selection["retained_v5_gate"]
        reused_qualified = (old["card_usable_fraction"] >= .9 and old["card_reference_passed"]
            and old["reference_pairs"] >= 6 and old["reference_same"] == old["reference_pairs"]
            and old["reference_clear_false_merges"] == 0 and old["reference_all_articles_clear"])
        quality_passed = (reused_qualified and primary.get("normal_valid", 0) == primary["selected"]
            and primary.get("reference_valid", 0) == primary["selected"]
            and not primary.get("normal_accepted_reference_unsupported_or_unavailable", 0)
            and primary["reference_supported_normal_incoming"] >= MIN_INCOMING)
        outcome = {"hypothetical_normal_groups": atomic_commit(selection["before_groups"], selection["expansion_plan"], sets["normal"]),
                   "independent_validated_groups": atomic_commit(selection["before_groups"], selection["expansion_plan"], sets["validated"]),
                   "normal_supported_expanded_groups": sorted(sets["normal"]),
                   "independent_supported_expanded_groups": sorted(sets["validated"]),
                   "normal_incoming_proposals": primary["normal_incoming_proposals"],
                   "reference_supported_normal_incoming": primary["reference_supported_normal_incoming"],
                   "uncertainty_edges": selection["expansion_plan"]["uncertainty_edges"],
                   "human_validated": False, "globally_unique_dossiers_established": False}
        self.phase(session, "pilot_v6_outcome", outcome)
        self.phase(session, "pilot_v6_primary_quality_gate", {"passed": quality_passed, **primary,
            "qualified_v5_evidence_reused": reused_qualified, "secondary_changes_quality_gate": False})
        self.current_phase = "v6_secondary_withheld_group_diagnostic"
        # Fixed secondary frame never affects gate/joins; no replacement when a
        # request does not fit the remaining subcap.
        for item in selection["secondary"]:
            if item["astra_packet"]:
                try:
                    self.calls(session, [self.ledger.artifacts.read(item["astra_packet"])])
                except PipelineStop as error:
                    if str(error) not in {"v6_pilot_subcap_audit", "v6_pilot_new_unknown_or_invalid", "budget_bound_audit"}:
                        raise
                    self.phase(session, "pilot_v6_secondary_stop", {"reason": str(error), "replacement_allowed": False})
                    break
        self.phase(session, "pilot_v6_secondary_finished", {"counts": self.pilot_counts()[1]})
        passed = quality_passed and self.hold_lineage()["new_unresolved_holds"] == 0
        self.phase(session, "pilot_v6_gate", {"passed": passed, **primary,
            "incoming_accepted": primary["reference_supported_normal_incoming"] if passed else 0,
            "qualified_v5_evidence_reused": reused_qualified, "v5_gate_remains_failed": not old.get("passed", False),
            "minimum_incoming_articles": MIN_INCOMING, **self.hold_lineage(),
            "functional_sample_not_independent_gold": True, "group_dependence_reported": True})

    def assignments(self, session, index, document_ids, groups, cards, label, recovery=False):
        original = super().assignments(session, index, document_ids, groups, cards, label, recovery)
        eligible = self.eligibility(original, cards)
        return {**original, "proposals": eligible["proposals"], "v6_eligibility": eligible}

    def checked_commit(self, session, groups, cards, assigned, label, *, recovery=False):
        saved = self.phase(session, label + "_checked_commit")
        if saved:
            return saved
        plan = self.phase(session, label + "_expansion_plan")
        if plan is None:
            plan = self.phase(session, label + "_expansion_plan",
                              self.freeze_expansions(groups, assigned["v6_eligibility"], recovery=recovery))
        changed = {d: e["document_ids"] for d, e in plan["expansions"].items()}
        reviewed = self.make_cards(session, changed, label + "_expanded")
        accepted = set(reviewed["usable"])
        committed = atomic_commit(groups, plan, accepted)
        retained_cards = {d: c for d, c in cards.items() if d in committed and d not in accepted}
        retained_cards.update(reviewed["usable"])
        rejected = {d: {"document_ids": e["document_ids"], "original_groups": e["original_groups"],
                       "reason": (reviewed["quality"].get(d) or {}).get("label", "expanded_group_quality_unavailable")}
                    for d, e in plan["expansions"].items() if d not in accepted}
        return self.phase(session, label + "_checked_commit", {"groups": committed, "cards": retained_cards,
            "accepted_expanded_groups": sorted(accepted), "rejected_expansions": rejected,
            "uncertainty_edges": plan["uncertainty_edges"], "plan": plan,
            "atomic_rollback": True, "globally_unique_dossiers_established": False})

    def full_pipeline(self, session):
        vectors = self.vectors(session)
        if len(vectors["document_ids"]) < .99 * len(self.documents):
            raise PipelineStop("embedding_coverage_below_99_percent")
        self.current_phase = "1_candidate_retrieval"
        ids = vectors["document_ids"]
        index = parent.candidates.build_index(ids, np.asarray(vectors["vectors"], dtype=np.float32), self.documents,
                                              vector_k=PARAMETERS["vector_k"], lexical_k=40)
        self.phase(session, "candidate_index", index.manifest())
        proposals = self.phase(session, "seed_proposals")
        if not proposals:
            raise AuditError("dossier_v6_retained_seed_frame_required")
        packets = sorted(proposals["packets"], key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))
        seeds = self.seed_results(session, packets, "full_v6")
        seed_cards = self.make_cards(session, seeds["groups"], "full_v6_seed")
        supported, provisional_seed, rejected_seed = parent.quality_partition(seeds["groups"], seed_cards)
        members = {i for g in seeds["groups"].values() for i in g}
        unclear = {i for i, answer in seeds["clarity"].items() if not parent.clear(answer, "clear_single_event")}
        unclear.update(self.amendment["quarantined_document_ids"])
        unclear.update(i for d, group in seeds["groups"].items() if d not in supported for i in group)
        remaining = [i for i in ids if i not in members and i not in unclear]
        assigned = self.assignments(session, index, remaining, supported, seed_cards["usable"], "full_v6_seed")
        initial = self.checked_commit(session, supported, seed_cards["usable"], assigned, "full_v6_seed")
        assigned_ids = {i for group in initial["groups"].values() for i in group}
        residual = [i for i in remaining if i not in assigned_ids
                    and assigned["v6_eligibility"]["exclusions"].get(i) not in {"focal_event_not_clear", "unclear_query"}]
        singletons = {digest(["singleton", i]): [i] for i in residual}
        singleton_cards = self.make_cards(session, singletons, "full_v6_singleton")
        singleton_supported, singleton_provisional, singleton_rejected = parent.quality_partition(singletons, singleton_cards)
        recovery_groups = {**initial["groups"], **singleton_supported}
        recovery_cards = {**initial["cards"], **singleton_cards["usable"]}
        recovery_ids = sorted(i for group in recovery_groups.values() for i in group)
        recovered = self.assignments(session, index, recovery_ids, recovery_groups, recovery_cards, "full_v6_recovery", recovery=True)
        recovery = self.checked_commit(session, recovery_groups, recovery_cards, recovered, "full_v6_recovery", recovery=True)
        # Each accepted changed membership has already received one full-group
        # review. Exact final cards/checks reuse that response, never regenerate.
        final_cards = self.make_cards(session, recovery["groups"], "full_v6_final")
        accepted, final_provisional, final_rejected = parent.quality_partition(recovery["groups"], final_cards)
        provisional = {**provisional_seed, **singleton_provisional, **final_provisional}
        groups = {**provisional, **accepted}
        rejected = {**rejected_seed, **singleton_rejected, **final_rejected}
        positives = {tuple(sorted((group[0], identifier))) for group in accepted.values() for identifier in group[1:]}
        selected_positive = sorted(positives, key=lambda p: digest(["final-positive", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        membership = {i: d for d, group in accepted.items() for i in group}
        unresolved_edges = [*initial["uncertainty_edges"], *recovery["uncertainty_edges"]]
        misses, frame_counts = nonjoined_frame(index.manifest()["pairs"], membership, unresolved_edges)
        selected_negative = sorted(misses, key=lambda p: digest(["final-nonjoined-candidate", p]))[:PARAMETERS["final_reference_pairs_per_stratum"]]
        provisional_ids = {i for group in provisional.values() for i in group}

        def endpoint_state(identifier):
            return ("quarantined" if identifier in self.amendment["quarantined_document_ids"] else
                    "card_supported_group" if identifier in membership else
                    "provisional_card_incomplete" if identifier in provisional_ids else "unresolved")

        outcome = self.phase(session, "full_v6_processing_outcome", {"groups": groups, "cards": final_cards,
            "group_states": {d: "provisional_card_incomplete" for d in provisional},
            "card_supported_group_ids": sorted(accepted), "unresolved_groups": rejected,
            "initial_checked_commit": initial, "recovery_checked_commit": recovery,
            "rejected_expansions": {**initial["rejected_expansions"], **recovery["rejected_expansions"]},
            "uncertainty_edges": unresolved_edges,
            "unclear": sorted(unclear), "unembedded": vectors["missing"],
            "reference_selection": {"full_v6_retained_memberships": selected_positive,
                                    "full_v6_nonjoined_candidates": selected_negative},
            "nonjoined_audit_frame": {**frame_counts, "retrieval_pairs": len(index.manifest()["pairs"]),
                "selection_count": len(selected_negative),
                "selection_statuses": [{"left": a, "right": b, "left_state": endpoint_state(a),
                                        "right_state": endpoint_state(b)} for a, b in selected_negative],
                "rule": "All retrieved pairs not coassigned to the same card-supported group; unresolved rivals are not negatives.",
                "changes_membership": False}, "human_validated": False, "accepted_as_scientific_findings": False,
            "globally_unique_dossiers_established": False, "all_potential_matches_guaranteed": False})
        for label, pairs in outcome["reference_selection"].items():
            self.reference_plan(session, pairs, label)
        for label, pairs in outcome["reference_selection"].items():
            self.reference(session, pairs, label)
        self.phase(session, "full_v6_outcome", outcome)

    def report(self, session):
        if getattr(self, "_loading_parent", False):
            return None
        completed = self.phase(session, "full_v6_outcome")
        outcome = completed or self.phase(session, "full_v6_processing_outcome")
        primary, secondary, _ = self.pilot_counts()
        gate = self.phase(session, "pilot_v6_gate")
        primary["incoming_accepted"] = primary["reference_supported_normal_incoming"] if gate and gate["passed"] else 0
        audit_completion = self.final_audit_status(session, outcome)
        covered, memberships = {}, []
        if outcome:
            for dossier, members in outcome["groups"].items():
                for identifier in members:
                    if identifier in covered:
                        raise AuditError("dossier_multiple_membership")
                    covered[identifier] = dossier
            memberships = [{**a, "dossier_id": covered.get(a["document_id"]),
                "state": outcome.get("group_states", {}).get(covered.get(a["document_id"]),
                    "model_supported_group" if a["document_id"] in covered else "unresolved"), "human_validated": False}
                for a in self.articles]
        report = {"plan": self.plan["_record_id"], "execution_amendment": self.amendment["_record_id"],
            "parent_report": PARENT_REPORT, "legacy_budget_at_amendment": self.amendment["legacy_budget"], **self.hold_lineage(),
            "at": utc(), "articles": len(self.articles), "distinct_inputs": len(self.documents),
            "responses_by_phase": dict(Counter(r["phase"] for r in self.results.values())), "stored_responses": len(self.results),
            **parent.accounting(list(self.results.values()), self.ledger.unresolved), "budget_usd": 50,
            "pilot_budget": {"main": self.pilot_budget("main"), "audit": self.pilot_budget("audit")},
            "pilot_gate": gate, "pilot_primary": primary, "pilot_secondary": secondary,
            "pipeline_finished": completed is not None, "pipeline_processing_complete": outcome is not None,
            "final_audit_completion": audit_completion, "final_audit_complete": audit_completion["complete"],
            "groups": len(outcome["groups"]) if outcome else None,
            "multi_article_groups": sum(len(group) > 1 for group in outcome["groups"].values()) if outcome else None,
            "groups_with_usable_card": len(outcome["cards"]["usable"]) if outcome else None,
            "four_processes_complete": bool(outcome and len(outcome["cards"]["usable"]) == len(outcome["groups"])
                                             and len(covered) == len(self.documents)),
            "provisional_card_incomplete_groups": len(outcome.get("group_states", {})) if outcome else None,
            "quality_rejected_or_unavailable_groups": len(outcome.get("unresolved_groups", {})) if outcome else None,
            "quality_rejected_or_unavailable_articles": len({i for group in outcome.get("unresolved_groups", {}).values()
                for i in group["document_ids"]}) if outcome else None,
            "nonjoined_audit_candidate_pool": outcome.get("nonjoined_audit_frame", {}).get("candidate_pool") if outcome else None,
            "nonjoined_audit_frame_counts": {key: outcome.get("nonjoined_audit_frame", {}).get(key) for key in
                ("base_retrieval_pairs", "uncertain_rival_pairs", "added_uncertain_rival_pairs", "deduplicated_union_pairs", "candidate_pool")} if outcome else None,
            "nonjoined_audit_selected_endpoint_status_counts": dict(Counter(status
                for row in outcome.get("nonjoined_audit_frame", {}).get("selection_statuses", [])
                for status in (row["left_state"], row["right_state"]))) if outcome else None,
            "unique_inputs_grouped": len(covered), "unresolved_inputs": len(self.documents) - len(covered),
            "rejected_expansion_groups": len(outcome.get("rejected_expansions", {})) if outcome else None,
            "unresolved_rival_relations": len(outcome.get("uncertainty_edges", [])) if outcome else None,
            "quarantined_articles": len(self.amendment["quarantined_document_ids"]),
            "memberships_artifact": self.ledger.artifacts.put(memberships) if outcome else None,
            "article_routes": dict(Counter(r["state"] for r in memberships)),
            "globally_unique_dossiers_established": False, "all_potential_matches_guaranteed": False,
            "limitations": "Adaptive retained-case functional validation with dependent groups; no independent holdout, human gold or population precision/recall.",
            "exact_chat_presentation_capture_supported": False}
        identifier = self.ledger.record(session, "cyber_dossier_report", digest([utc(), len(self.results)]), report)
        (self.ledger.root / "dossier-report.json").write_text(json.dumps({"id": identifier, **report}, indent=2), encoding="utf-8")
        return {"id": identifier, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("amend", "pilot", "run", "report"))
    parser.add_argument("--workspace", type=Path, default=parent.preparation.OWNER)
    parser.add_argument("--allow-paid-execution", action="store_true")
    args = parser.parse_args()
    study = Study(args.workspace, config=Config(offline=args.action in {"amend", "report"}))
    try:
        result = study.execute("status", {"action": args.action, "allow_paid_execution": args.allow_paid_execution},
            objective="Register or execute prospective v6 expanded-group validation within the existing USD50 dossier study",
            actor="codex:cybercrime-dossiers")
        print(json.dumps(result), flush=True)
    finally:
        study.close()


if __name__ == "__main__":
    main()
