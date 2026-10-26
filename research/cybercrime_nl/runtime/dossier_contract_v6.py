"""Prospective v6 eligibility and atomic expansion bindings; no source I/O.

Full-source card QA remains the frozen v5 contract. These helpers neither call
models nor accept memberships. The coordinator applies its existing commit
guards provisionally, then validates every expanded group before any acceptance.
"""
from copy import deepcopy

import dossier_contract_v5 as v5
from newsresearch.common import ResearchError, digest

METHOD = "cyber-dossier-single-positive-expansion-v6"


def __getattr__(name):
    return getattr(v5, name)


def require(condition, message):
    if not condition:
        raise ResearchError("dossier_v6_" + message)


def eligible_assignments(assignment_phase, current_bindings, *, threshold=.85, clarity_threshold=.85):
    """Exactly one strong positive; valid uncertain rivals remain unresolved.

    Complete means all selected candidates and every packet clarity answer have
    valid retained outputs. A refusal or missing response is not a negative.
    Labels/probabilities are preserved; this is a new routing policy, not relabeling.
    """
    v5.v3._threshold(threshold)
    v5.v3._threshold(clarity_threshold)
    decisions, coverage = assignment_phase["decisions"], assignment_phase["packet_coverage"]
    frame = set(assignment_phase.get("proposals", {})) | set(assignment_phase.get("unresolved", {})) | set(decisions) | set(coverage)
    proposals, edges, exclusions, evidence = {}, [], {}, {}
    for identifier in sorted(frame):
        answers = decisions.get(identifier, [])
        covered = coverage.get(identifier, {})
        chosen = covered.get("chosen_dossiers", [])
        require(len(chosen) == len(set(chosen)), "duplicate_candidate")
        require(all(candidate in current_bindings for candidate in chosen), "unknown_static_candidate")
        require(all(a.get("document_id") == identifier and a.get("kind") in {"clarity", "assignment"} for a in answers),
                "answer_query_binding_changed")
        pairs = [a for a in answers if a["kind"] == "assignment"]
        clarities = [a for a in answers if a["kind"] == "clarity"]
        candidate_ids = [a["dossier_id"] for a in pairs]
        require(len(candidate_ids) == len(set(candidate_ids)) and set(candidate_ids) <= set(chosen), "answer_candidate_binding_changed")
        for answer in pairs:
            binding = current_bindings[answer["dossier_id"]]
            require(all(answer.get(key) == binding.get(key) for key in ("card_version", "membership_revision", "representation_type"))
                    and binding.get("representation_type") == "evidence_card"
                    and all(isinstance(binding.get(key), str) and binding[key] for key in ("card_version", "membership_revision")),
                    "static_card_binding_changed")
        distributions = [v5.v3._distribution(a, v5.PAIR_LABELS) for a in pairs]
        clear_distributions = [v5.v3._distribution(a, v5.CLARITY_LABELS) for a in clarities]
        packet_count = covered.get("packets", 0)
        counts = covered.get("candidate_counts", [])
        complete = (bool(chosen) and covered.get("coverage_complete") is True
                    and type(packet_count) is int and packet_count > 0 and len(clarities) == packet_count
                    and len(counts) == packet_count and all(type(n) is int and n > 0 for n in counts)
                    and sum(counts) == len(chosen) and set(candidate_ids) == set(chosen)
                    and all(d is not None for d in [*distributions, *clear_distributions]))
        clear = bool(clarities) and all(d is not None and a["label"] == "clear_single_event"
            and d["clear_single_event"] >= clarity_threshold for a, d in zip(clarities, clear_distributions, strict=True))
        routes = {a["dossier_id"]: v5.assignment_route(a, threshold=threshold) for a in pairs}
        positives = [d for d, route in routes.items() if route == "positive"]
        for answer in pairs:
            if routes[answer["dossier_id"]] == "unresolved":
                edges.append({"document_id": identifier, "dossier_id": answer["dossier_id"],
                    "relation": "unresolved", "treated_as_negative": False,
                    "original_answer": deepcopy(answer)})
        evidence[identifier] = {"complete": complete, "clear": clear, "candidate_routes": routes,
            "positive_dossiers": positives, "original_answers": deepcopy(answers),
            "coverage": deepcopy(covered), "old_unresolved_reason": assignment_phase.get("unresolved", {}).get(identifier)}
        if not complete:
            exclusions[identifier] = "incomplete_candidate_or_clarity_evaluation"
        elif not clear:
            exclusions[identifier] = "focal_event_not_clear"
        elif len(positives) != 1:
            exclusions[identifier] = "multiple_positive_candidates" if positives else "no_positive_candidate"
        else:
            target = positives[0]
            proposals[identifier] = {"dossier_id": target, **deepcopy(current_bindings[target]),
                "eligibility_method": METHOD, "positive_threshold": threshold, "clarity_threshold": clarity_threshold,
                "unresolved_rival_ids": [d for d, route in routes.items() if route == "unresolved"],
                "membership_accepted": False, "requires_expanded_full_source_quality": True}
    return {"method": METHOD, "proposals": proposals, "uncertainty_edges": edges, "exclusions": exclusions,
            "query_evidence": evidence, "static_bindings_sha256": digest(current_bindings),
            "source_phase_sha256": digest(assignment_phase), "memberships_accepted": 0,
            "probabilities_calibrated": False}


def _groups(value):
    require(isinstance(value, dict), "group_mapping_invalid")
    result, owner = {}, {}
    for dossier, members in value.items():
        require(isinstance(dossier, str) and dossier and isinstance(members, list) and members
                and all(isinstance(i, str) and i for i in members) and len(members) == len(set(members)), "group_members_invalid")
        require(not set(members) & set(owner), "multiple_membership")
        result[dossier] = sorted(members)
        owner.update({i: dossier for i in members})
    return result, owner


def expansion_plan(original_groups, proposed_final_groups, applied, eligibility):
    """Bind a provisional result from existing commit guards and exact rollback.

    This does not calculate joins or replace the coordinator's no-chain guards.
    Whole original groups must remain intact. All new/source-group members need
    eligible proposals into an original group in the same final component.
    """
    before, before_owner = _groups(original_groups)
    after, after_owner = _groups(proposed_final_groups)
    require(set(before_owner) <= set(after_owner), "original_member_lost")
    require(set(after) <= set(before), "new_target_without_static_group")
    require(eligibility.get("method") == METHOD and eligibility.get("memberships_accepted") == 0, "eligibility_binding_invalid")
    proposals = eligibility["proposals"]
    require(isinstance(applied, dict) and set(applied) <= (set(proposals) | set(before)), "applied_frame_invalid")
    stable, expansions, claimed_originals = {}, {}, set()
    for target, members in sorted(after.items()):
        require(set(before[target]) <= set(members), "static_target_members_removed")
        originals = sorted({before_owner[i] for i in members if i in before_owner})
        require(all(set(before[d]) <= set(members) for d in originals), "source_group_split")
        require(not set(originals) & claimed_originals, "rollback_component_overlap")
        claimed_originals.update(originals)
        if members == before[target]:
            stable[target] = members
            continue
        incoming = sorted(set(members) - set(before[target]))
        require(bool(incoming), "nonexpanding_membership_change")
        for identifier in incoming:
            proposal = proposals.get(identifier)
            require(proposal and proposal.get("dossier_id") in originals
                    and proposal.get("membership_accepted") is False
                    and proposal.get("requires_expanded_full_source_quality") is True, "incoming_without_eligible_proposal")
            require(proposal["membership_revision"] == digest(before[proposal["dossier_id"]]), "proposal_static_revision_changed")
            if identifier in before_owner:
                require(proposal["dossier_id"] != before_owner[identifier], "source_member_self_match")
        new_ids = [i for i in incoming if i not in before_owner]
        row = {"dossier_id": target, "original_target_document_ids": before[target],
            "proposed_document_ids": members, "incoming_document_ids": incoming,
            "new_article_ids": new_ids, "moved_source_member_ids": [i for i in incoming if i in before_owner],
            "original_group_ids": originals, "original_groups": {d: before[d] for d in originals},
            "before_revision": digest(before[target]), "membership_revision": digest(members),
            "incoming_proposals": {i: deepcopy(proposals[i]) for i in incoming},
            "unresolved_rival_edges": [deepcopy(edge) for edge in eligibility["uncertainty_edges"] if edge["document_id"] in incoming],
            "membership_accepted": False, "requires_expanded_full_source_quality": True,
            "on_rejection": "Restore every original group and prior supported card; external incoming articles remain unresolved."}
        expansions[target] = {**row, "expansion_id": digest([METHOD, row])}
    require(claimed_originals == set(before), "original_group_missing_from_components")
    return {"method": METHOD, "stable_groups": stable, "expansions": expansions,
            "proposed_groups": after, "original_groups_sha256": digest(before),
            "eligibility_sha256": digest(eligibility), "applied_sha256": digest(applied),
            "memberships_accepted": 0, "all_proposed_groups_require_independent_audit_before_filtering": True}
