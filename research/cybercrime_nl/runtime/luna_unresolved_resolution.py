"""Pure finite unresolved-article plan; no model, source or QA authority."""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
from itertools import combinations
from pathlib import Path

import luna_recall_contract as contract
import luna_recall_repair as repair
import luna_snippet_rollout_grouping as grouping
from newsresearch.common import ResearchError, digest

METHOD = "luna-unresolved-focal-resolution-v1"
MAX_TARGETS = 3
POLICY = {"maximum_target_units_per_article": MAX_TARGETS, "new_proposal_calls": 0,
    "full_member_and_card_qa_required": True, "singleton_requires_negative_neighbors": False,
    "global_uniqueness_established": False, "threshold": .85, "technical_retries": 0}


def implementation():
    root = Path(__file__).resolve().parents[3]
    return {**grouping.implementation(), **{p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (Path(__file__), Path(repair.__file__))}}


def require(condition, reason):
    if not condition:
        raise ResearchError("unresolved_resolution_" + reason)


def _units(source, state):
    documents, units, occupied = source["documents"], {}, set()
    require(set(state["accepted_group_ids"]) <= set(state["groups"]), "accepted_groups")
    for group, members in sorted(state["groups"].items()):
        require(isinstance(group, str) and not group.startswith("unresolved:") and members
            and len(set(members)) == len(members) and set(members) <= set(documents)
            and not occupied.intersection(members), "group_partition")
        occupied.update(members)
        units[group] = {"unit_id": group, "kind": "multi" if len(members) > 1 else "singleton",
            "members": sorted(members), "source_group_id": group}
    loose = state["unresolved_ids"]
    require(len(loose) == len(set(loose)) and not occupied.intersection(loose)
        and occupied | set(loose) == set(documents), "source_partition")
    for article in sorted(loose):
        units["unresolved:"+article] = {"unit_id": "unresolved:"+article, "kind": "loose",
            "members": [article], "source_group_id": None}
    for unit in units.values():
        unit["membership_revision"] = digest(unit["members"])
        unit["input_bindings"] = [[i, documents[i]["input_sha256"]] for i in unit["members"]]
        unit["source_version"] = digest(unit["input_bindings"])
    return units


def _proposal(units, names, anchors, priority):
    names = sorted(names)
    members = sorted(i for u in names for i in units[u]["members"])
    require(len(members) == len(set(members)), "proposal_overlap")
    return {"members": members, "membership_revision": digest(members), "groups": names,
        "unit_bindings": {u: deepcopy(units[u]) for u in names}, "anchor_ids": sorted(anchors),
        "priority": list(priority), "new_pairs": len(members)*(len(members)-1)//2
            - sum(len(units[u]["members"])*(len(units[u]["members"])-1)//2 for u in names)}


def _prior_block(history, members):
    row = history.get("membership_attempts", {}).get(digest(members), {})
    if row:
        require(row["members"] == members, "prior_membership_identity")
    if row.get("blocked") or any(row.get(stage+"_attempted") and not row.get(stage+"_supported")
            for stage in ("member", "card")):
        return "prior_failed_or_unknown_membership"
    return None


def build_plan(imported):
    source, state, history = (imported[k] for k in ("source", "state", "history"))
    units = _units(source, state)
    anchors = sorted(state["unresolved_ids"])
    anchor_set = set(anchors)
    quarantine = set(history.get("quarantine_document_ids", []))
    require(quarantine <= set(source["documents"]), "quarantine_identity")
    menus, _, missing = grouping.pilot._menus(source, units)
    owner = {i: u for u, row in units.items() for i in row["members"]}
    negative, positive = set(), set()
    for row in history.get("pair_observations", []):
        if not row.get("compatible_focal_rubric") or row.get("label") not in {"same_event", "negative"}:
            continue
        pair = tuple(sorted(row["pair"]))
        require(len(pair) == 2 and pair[0] != pair[1] and set(pair) <= set(owner), "pair_identity")
        (negative if row["label"] == "negative" else positive).add(pair)
    preferred, stale = defaultdict(set), 0
    for a, b in positive:
        if owner[a] != owner[b]:
            preferred[owner[a]].add(owner[b])
            preferred[owner[b]].add(owner[a])
    for proposal in history.get("resolution_proposals", []):
        bindings = proposal["unit_bindings"]
        if any(u not in units or digest(binding) != digest(units[u]) for u, binding in bindings.items()):
            stale += 1
            continue
        require(proposal["members"] == sorted(i for b in bindings.values() for i in b["members"])
            and proposal["membership_revision"] == digest(proposal["members"]), "retained_proposal_identity")
        for a, b in proposal.get("direct_links", []):
            require(a != b and a in bindings and b in bindings, "retained_direct_link")
            preferred[a].add(b)
            preferred[b].add(a)
    unions, singletons, diagnostics = {}, [], {}
    accepted = set(state["accepted_group_ids"])
    for article in anchors:
        anchor = "unresolved:"+article
        ranked = [r["unit_id"] for r in menus[anchor]]
        ranks = {u: n for n, u in enumerate(ranked)}
        targets = sorted(set(ranked) | preferred[anchor],
            key=lambda u: (u not in preferred[anchor], ranks.get(u, len(ranks)), u))
        selected, excluded, checked_negative = [], {}, []
        for target in targets:
            members = sorted([article, *units[target]["members"]])
            cross = [tuple(sorted((article, i))) for i in units[target]["members"]]
            if all(pair in negative for pair in cross):
                checked_negative.append(target)
            reason = ("quarantined_source" if quarantine.intersection(members) else
                "provisional_target" if units[target]["source_group_id"] is not None and target not in accepted else
                "compatible_negative_veto" if any(pair in negative for pair in combinations(members, 2)) else
                _prior_block(history, members))
            if reason:
                excluded[target] = reason
                continue
            if len(selected) == MAX_TARGETS:
                continue
            priority = (target not in preferred[anchor], len(selected), article, target)
            row = _proposal(units, [anchor, target], set(units[anchor]["members"]) | (set(units[target]["members"]) & anchor_set), priority)
            existing = unions.get(row["membership_revision"])
            if existing is None or row["priority"] < existing["priority"]:
                unions[row["membership_revision"]] = row
            selected.append(target)
        singleton = _proposal(units, [anchor], [article], (False, 0, article, anchor))
        singleton_reason = "quarantined_source" if article in quarantine else _prior_block(history, [article])
        if not singleton_reason:
            singletons.append(singleton)
        diagnostics[article] = {"quarantined": article in quarantine,
            "planned_targets": selected, "retained_menu_targets": targets,
            "omitted_targets": [u for u in targets if u not in selected and u not in excluded],
            "excluded_targets": excluded, "prior_positive_targets": sorted(preferred[anchor]),
            "checked_negative_targets": checked_negative, "singleton_unavailable": singleton_reason,
            "missing_rank_channels": [r["channel"] for r in missing if r["document_id"] == article]}
    bounded, incident = [], defaultdict(int)
    for row in sorted(unions.values(), key=lambda r: (r["priority"], r["membership_revision"])):
        if any(incident[i] >= MAX_TARGETS for i in row["anchor_ids"]):
            continue
        bounded.append(row)
        for i in row["anchor_ids"]:
            incident[i] += 1
    # A loose target is itself a covered anchor. Account for reciprocal joins
    # too, so no article silently receives more than its three frozen unions.
    actual_targets = defaultdict(set)
    for row in bounded:
        for i in row["anchor_ids"]:
            actual_targets[i].update(u for u in row["groups"] if u != "unresolved:"+i)
    for i, d in diagnostics.items():
        previous = set(d["planned_targets"])
        d["planned_targets"] = sorted(actual_targets[i])
        d["omitted_targets"] = sorted((set(d["omitted_targets"]) | previous) - actual_targets[i])
        d["retained_menu_targets"] = sorted(set(d["retained_menu_targets"]) | actual_targets[i])
    value = {"method": METHOD, "policy": POLICY, "state_sha256": digest(state),
        "source_bindings_sha256": digest(sorted((i, d["input_sha256"]) for i, d in source["documents"].items())),
        "anchors": anchors, "union_proposals": bounded,
        "singleton_proposals": singletons, "article_diagnostics": diagnostics,
        "quarantined_document_ids": sorted(quarantine), "stale_retained_proposals": stale,
        "prior_membership_history_sha256": digest(history.get("membership_attempts", {}))}
    return {**value, "digest": digest(value)}


def _verify_plan(plan):
    require(plan["method"] == METHOD and plan["policy"] == POLICY
        and digest({k: v for k, v in plan.items() if k != "digest"}) == plan["digest"], "plan_binding")


def packet_bundle(imported, proposal, count):
    """Ephemeral exact old-contract packets; coordinator owns completed evidence."""
    source, state, history = (imported[k] for k in ("source", "state", "history"))
    require(set(proposal["groups"]) == set(proposal["unit_bindings"]), "proposal_units")
    # The complete partition is verified once in build_plan. Check only this
    # small selected scope here; never rebuild corpus units for every packet.
    for u, b in proposal["unit_bindings"].items():
        group = b["source_group_id"]
        require(b["unit_id"] == u and b["membership_revision"] == digest(b["members"])
            and (b["members"] == sorted(state["groups"].get(group, [])) if group is not None else
                len(b["members"]) == 1 and b["members"][0] in state["unresolved_ids"])
            and b["input_bindings"] == [[i, source["documents"][i]["input_sha256"]] for i in b["members"]]
            and b["source_version"] == digest(b["input_bindings"]), "stale_proposal")
    members = sorted(i for b in proposal["unit_bindings"].values() for i in b["members"])
    require(members == proposal["members"] and digest(members) == proposal["membership_revision"], "proposal_identity")
    result = {"member": None, "card": None, "reused_card": None, "unavailable": None, "reservation_nanousd": 0}
    reason = "quarantined_source" if set(members) & set(history.get("quarantine_document_ids", [])) else _prior_block(history, members)
    negatives = {tuple(sorted(r["pair"])) for r in history.get("pair_observations", [])
        if r.get("compatible_focal_rubric") and r.get("label") == "negative"}
    if any(pair in negatives for pair in combinations(members, 2)):
        reason = "compatible_negative_veto"
    if reason:
        return {**result, "unavailable": reason}
    prior = history.get("membership_attempts", {}).get(digest(members), {})
    if prior.get("member_supported") and prior.get("card_supported"):
        require(isinstance(prior.get("card"), dict), "prior_supported_card")
        return {**result, "reused_card": prior["card"]}
    try:
        member = None if prior.get("member_supported") else contract.member_packet(source, members, count)
        card = contract.group_packet(source, members, count)
    except ResearchError as exc:
        if str(exc) not in {"dossier_packet_capacity", "dossier_card_quality_token_limit"}:
            raise
        return {**result, "unavailable": "full_source_capacity"}
    if any(set(p["logical_ids"]) & set(history.get("logical_ids", []))
            or p["task_key"] in history.get("task_keys", []) for p in (member, card) if p):
        return {**result, "unavailable": "prior_logical_attempt"}
    return {**result, "member": member, "card": card,
        "reservation_nanousd": card["reservation_nanousd"] + (member["reservation_nanousd"] if member else 0)}


def select_changes(plan, state, supported, *, singletons=False, occupied=()):
    """Structural selection; supported cards must come from concrete parent QA."""
    _verify_plan(plan)
    require(digest(state) == plan["state_sha256"], "stale_state")
    all_rows = {p["membership_revision"]: p for p in [*plan["union_proposals"], *plan["singleton_proposals"]]}
    require(set(supported) <= set(all_rows), "foreign_supported_membership")
    used, changes = set(occupied), []
    require(used <= set(i for r in all_rows.values() for i in r["members"]), "foreign_occupied")
    for row in plan["singleton_proposals"] if singletons else plan["union_proposals"]:
        revision = row["membership_revision"]
        if revision not in supported or used.intersection(row["members"]):
            continue
        require(not set(row["members"]) & set(plan["quarantined_document_ids"]), "quarantined_selection")
        # Reuse the established exact-unit/whole-membership verifier, one row at
        # a time so registered priority, rather than group size, resolves overlap.
        selected = grouping.select_supported([row], {revision: supported[revision]}, state)
        require(len(selected) == 1, "supported_selection")
        changes.extend(selected)
        used.update(row["members"])
    return {"changes": changes, "occupied": sorted(used)}


def dispositions(plan, successor, *, membership_outcomes=None):
    _verify_plan(plan)
    outcomes = membership_outcomes or {}
    accepted = set(successor["accepted_group_ids"])
    anchor_set = set(plan["anchors"])
    membership = {i: g for g, members in successor["groups"].items() for i in members}
    require(set(plan["anchors"]) <= set(membership) | set(successor["unresolved_ids"]), "coverage_lost")
    related_by_article = defaultdict(list)
    for proposal in plan["union_proposals"]:
        for article in proposal["anchor_ids"]:
            related_by_article[article].append(proposal)
    rows = {}
    for article in plan["anchors"]:
        d = plan["article_diagnostics"][article]
        group = membership.get(article)
        singleton = outcomes.get(digest([article]), {})
        related = related_by_article[article]
        possible = bool(d["prior_positive_targets"]) or any(outcomes.get(p["membership_revision"], {}).get("member_supported") for p in related)
        if d["quarantined"]:
            require(article in successor["unresolved_ids"], "quarantine_promoted")
            status = "unresolved_quarantined_prior_failure"
        elif group in accepted:
            status = "accepted_singleton" if len(successor["groups"][group]) == 1 else "supported_group_assignment"
        elif d["singleton_unavailable"]:
            status = "unresolved_prior_failed"
        elif singleton.get("clarity_label") == "not_event_focused" and singleton.get("clarity_probability", 0) >= .85:
            status = "unresolved_non_event"
        elif singleton.get("status") in {"full_source_capacity", "capacity"}:
            status = "unresolved_capacity"
        elif singleton.get("status") in {"prior_failed", "prior_logical_attempt", "held", "fatal",
                "historical_attempt_or_negative_block", "exact_membership_stage_already_attempted",
                "historical_logical_identity", "physical_outcome_unknown", "mechanically_unusable",
                "prior_failed_or_unknown_membership"}:
            status = "unresolved_prior_failed"
        elif singleton.get("status") in {"budget", "budget_bound", "unattempted", "joint_member_card_budget_bound",
                "health_stop_unattempted"} or not singleton:
            status = "unresolved_unattempted"
        else:
            status = "unresolved_ambiguous"
        menu = d["retained_menu_targets"]
        relation = ("supported_group_match" if status == "supported_group_assignment" else
            "possible_match" if possible else
            "checked_no_match_within_menu" if menu and set(menu) <= set(d["checked_negative_targets"]) else
            "coverage_incomplete" if menu else "not_established")
        rows[article] = {"document_id": article, "dossier_status": status, "group_id": group,
            "assignment_kind": ("existing_group" if set(successor["groups"][group]) - anchor_set else "new_loose_group")
                if status == "supported_group_assignment" else None,
            "identity_link_status": relation, "global_uniqueness_established": False,
            "planned_target_count": len(d["planned_targets"]), "retained_menu_target_count": len(menu),
            "checked_negative_target_count": len(d["checked_negative_targets"]),
            "omitted_target_count": len(d["omitted_targets"]), "excluded_targets": d["excluded_targets"],
            "singleton_outcome": singleton}
    summary = {"counts": dict(Counter(r["dossier_status"] for r in rows.values())),
        "identity_link_counts": dict(Counter(r["identity_link_status"] for r in rows.values())),
        "original_unresolved_articles": len(plan["anchors"]), "global_uniqueness_established": False}
    return {"articles": rows, "summary": summary, **summary}
