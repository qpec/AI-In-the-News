"""Pure, version-bound proposal selection for one title-search work unit.

The audited caller supplies compatible completed pair evidence and supported
cards. This module neither grants semantic support nor dispatches research.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
from pathlib import Path

from newsresearch.common import ResearchError, digest

ROOT = Path(__file__).resolve().parents[3]
METHOD = "luna-title-summary-repair-v1"
FALLBACK_REASONS = frozenset({"preflight_capacity", "negative_conflict", "usable_semantic_rejection"})


def require(value, reason):
    if not value:
        raise ResearchError("title_summary_repair_" + reason)


def implementation():
    import newsresearch.common as common
    files = [Path(__file__), Path(common.__file__)]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _seal(value):
    return {**value, "digest": digest(value)}


def _check_plan(plan):
    require(isinstance(plan, dict) and plan.get("method") == METHOD
        and plan.get("digest") == digest({k: v for k, v in plan.items() if k != "digest"}), "plan_binding")


def build_units(source, state):
    """Use already-verified input hashes; never re-read or summarize source bodies."""
    documents, groups = source["documents"], state["groups"]
    require(isinstance(documents, dict) and bool(documents)
        and all(isinstance(i, str) and i for i in documents), "documents")
    hashes = {i: d["input_sha256"] for i, d in documents.items()}
    require(all(_hash(h) for h in hashes.values()) and len(set(hashes.values())) == len(hashes), "input_identity")
    require(isinstance(groups, dict), "groups")
    accepted = state["accepted_group_ids"]
    require(isinstance(accepted, list) and len(set(accepted)) == len(accepted) and set(accepted) <= set(groups), "accepted_groups")
    accepted = set(accepted)
    units, occupied = {}, set()
    for group, members in sorted(groups.items()):
        require(isinstance(group, str) and group and not group.startswith("unresolved:"), "group_id")
        require(isinstance(members, list) and bool(members) and len(set(members)) == len(members)
            and set(members) <= set(documents) and not occupied.intersection(members), "group_partition")
        occupied.update(members)
        units[group] = {"unit_id": group, "members": sorted(members), "source_group_id": group,
            "kind": "singleton" if len(members) == 1 else "multi", "accepted": group in accepted}
    loose = state["unresolved_ids"]
    require(isinstance(loose, list) and len(set(loose)) == len(loose)
        and not occupied.intersection(loose) and occupied | set(loose) == set(documents), "population_partition")
    for i in sorted(loose):
        unit_id = "unresolved:" + i
        units[unit_id] = {"unit_id": unit_id, "members": [i], "source_group_id": None,
            "kind": "loose", "accepted": False}
    for unit in units.values():
        unit["membership_revision"] = digest(unit["members"])
        unit["input_bindings"] = [[i, hashes[i]] for i in unit["members"]]
        unit["source_version"] = digest(unit["input_bindings"])
    return units


def _pairs(values, documents):
    pairs = set()
    for pair in values:
        require(isinstance(pair, (list, tuple)) and len(pair) == 2
            and all(isinstance(i, str) and i in documents for i in pair) and pair[0] != pair[1], "pair_scope")
        pairs.add(tuple(sorted(pair)))
    return pairs


def _deferred(values, documents):
    rows = {}
    for row in values:
        members = row["members"]
        require(isinstance(members, list) and len(members) >= 2 and members == sorted(set(members))
            and set(members) <= set(documents) and row["membership_revision"] == digest(members), "deferred_membership")
        keys = row.get("direct_pair_keys", [])
        require(isinstance(keys, list) and keys == sorted(set(keys)) and all(_hash(k) for k in keys), "deferred_pair_keys")
        value = {"membership_revision": row["membership_revision"], "members": list(members), "direct_pair_keys": keys}
        if value["membership_revision"] in rows:
            require(rows[value["membership_revision"]]["members"] == members, "deferred_identity")
            value["direct_pair_keys"] = sorted(set(keys) | set(rows[value["membership_revision"]]["direct_pair_keys"]))
        rows[value["membership_revision"]] = value
    return [rows[k] for k in sorted(rows)]


def priority(row):
    return (-row["unresolved_absorbed"], -row["singleton_absorbed"], -row["new_pairs"], row["membership_revision"])


def build_proposals(source, state, positive_pairs, negative_pairs, *, work_unit,
        deferred_pair_keys=(), deferred_memberships=(), attempted_memberships=()):
    """Freeze direct stars and edge alternatives against the current exact state.

    Pair lists have already passed the caller's provenance/compatibility checks.
    attempted_memberships is a conservative caller-supplied no-fresh-QA set;
    stage-specific attempts and exact positive reuse remain caller obligations.
    """
    require(type(work_unit) is int and work_unit >= 0, "work_unit")
    units = build_units(source, state)
    documents = source["documents"]
    positive, negative = _pairs(positive_pairs, documents), _pairs(negative_pairs, documents)
    attempted, deferred_keys = set(attempted_memberships), set(deferred_pair_keys)
    require(all(_hash(k) for k in attempted | deferred_keys), "history_identity")
    previous = _deferred(deferred_memberships, documents)
    deferred_keys.update(k for row in previous for k in row["direct_pair_keys"])
    unit_of = {i: u for u, row in units.items() for i in row["members"]}
    edges, skipped = defaultdict(set), []
    for pair in sorted(positive):
        key, ends = digest(list(pair)), tuple(sorted({unit_of[i] for i in pair}))
        reason = ("deferred_overlap_pair" if key in deferred_keys else "negative_conflict" if pair in negative
            else "already_coassigned" if len(ends) == 1 else None)
        if reason:
            skipped.append({"pair": list(pair), "pair_key": key, "reason": reason})
        else:
            edges[ends].add(pair)
    neighbors, negative_neighbors = defaultdict(set), defaultdict(set)
    for a, b in edges:
        neighbors[a].add(b)
        neighbors[b].add(a)
    for a, b in negative:
        negative_neighbors[a].add(b)
        negative_neighbors[b].add(a)

    def make_row(groups, direct):
        bindings = {u: deepcopy(units[u]) for u in sorted(groups)}
        members = sorted(i for row in bindings.values() for i in row["members"])
        member_set, revision = set(members), digest(members)
        conflicts = sorted({tuple(sorted((i, j))) for i in members for j in negative_neighbors[i] & member_set})
        rebases = sorted(r["membership_revision"] for r in previous if set(r["members"]) <= member_set)
        reason = "deferred_membership_rebase" if rebases else "negative_conflict" if conflicts else (
            "exact_membership_already_attempted" if revision in attempted else None)
        value = {"work_unit": work_unit, "groups": sorted(bindings), "members": members,
            "membership_revision": revision, "unit_bindings": bindings,
            "direct_pairs": [list(p) for p in sorted(direct)], "parent_revisions": [],
            "unresolved_absorbed": sum(len(b["members"]) for b in bindings.values() if b["kind"] == "loose"),
            "singleton_absorbed": sum(b["kind"] == "singleton" and b["accepted"] for b in bindings.values()),
            "new_pairs": len(members)*(len(members)-1)//2
                - sum(len(b["members"])*(len(b["members"])-1)//2 for b in bindings.values()),
            "blocked_reason": reason, "already_attempted": revision in attempted,
            "negative_pairs": [list(p) for p in conflicts], "deferred_from": rebases}
        return value

    primary = {}
    for center in sorted(neighbors):
        direct = set().union(*(edges[tuple(sorted((center, n)))] for n in neighbors[center]))
        row = make_row({center, *neighbors[center]}, direct)
        revision = row["membership_revision"]
        if revision in primary:
            primary[revision]["direct_pairs"] = [list(p) for p in sorted(
                {tuple(p) for p in primary[revision]["direct_pairs"]} | direct)]
            primary[revision]["centers"].append(center)
        else:
            primary[revision] = {**row, "centers": [center]}
    # A leaf's two-unit view must not independently bypass its larger star's
    # fallback gate. Isolated edges remain primary proposals.
    larger = [set(row["groups"]) for row in primary.values() if len(row["groups"]) > 2]
    primary = {revision: row for revision, row in primary.items()
        if len(row["groups"]) > 2 or not any(set(row["groups"]) < groups for groups in larger)}
    fallbacks = {}
    for revision, parent in sorted(primary.items()):
        if len(parent["groups"]) <= 2:
            continue
        unit_edges = {tuple(sorted((unit_of[a], unit_of[b]))) for a, b in parent["direct_pairs"]}
        for edge in sorted(unit_edges):
            row = make_row(edge, edges[edge])
            key = row["membership_revision"]
            target = primary.get(key)
            if target is None:
                target = fallbacks.setdefault(key, row)
            target["parent_revisions"].append(revision)
    for row in [*primary.values(), *fallbacks.values()]:
        row["parent_revisions"] = sorted(set(row["parent_revisions"]))
    primary_rows, fallback_rows = sorted(primary.values(), key=priority), sorted(fallbacks.values(), key=priority)
    return _seal({"method": METHOD, "work_unit": work_unit, "state_sha256": digest(state), "units": units,
        "primary": primary_rows, "fallbacks": fallback_rows,
        "blocked": [{"membership_revision": r["membership_revision"], "reason": r["blocked_reason"]}
            for r in [*primary_rows, *fallback_rows] if r["blocked_reason"]], "skipped_pairs": skipped,
        "deferred_pair_keys": sorted(deferred_keys), "deferred_memberships": previous,
        "transitive_closure_used": False, "full_source_qa_required": True})


def eligible_fallbacks(plan, parent_outcomes, *, attempted_memberships=()):
    """Only an explicit admissible parent disposition activates untouched edges."""
    _check_plan(plan)
    primary = {r["membership_revision"]: r for r in plan["primary"]}
    require(set(parent_outcomes) <= set(primary), "foreign_parent_outcome")
    require(all(isinstance(reason, str) for reason in parent_outcomes.values()), "parent_outcome")
    attempted = set(attempted_memberships)
    require(all(_hash(k) for k in attempted), "history_identity")
    allowed = {r for r, why in parent_outcomes.items() if why in FALLBACK_REASONS
        and not primary[r]["already_attempted"] and not primary[r]["deferred_from"]
        and (why != "negative_conflict" or primary[r]["negative_pairs"])}
    return [deepcopy(row) for row in plan["fallbacks"] if row["blocked_reason"] is None
        and row["membership_revision"] not in attempted and set(row["parent_revisions"]) & allowed]


def select_supported(plan, state, supported_cards, *, eligible_fallback_revisions=()):
    """Select only caller-verified complete cards; never infer semantic support."""
    _check_plan(plan)
    require(digest(state) == plan["state_sha256"], "stale_work_unit_state")
    all_rows = {r["membership_revision"]: r for r in [*plan["primary"], *plan["fallbacks"]]}
    fallback_ids = {r["membership_revision"] for r in plan["fallbacks"]}
    eligible = set(eligible_fallback_revisions)
    require(eligible <= fallback_ids and set(supported_cards) <= set(all_rows), "foreign_supported_membership")
    require(not (set(supported_cards) & fallback_ids) - eligible, "inactive_fallback_support")
    for revision, card in supported_cards.items():
        require(isinstance(card, dict) and bool(card), "supported_card")
        require(all_rows[revision]["blocked_reason"] in {None, "exact_membership_already_attempted"}, "blocked_supported_membership")
    occupied, selected, changes = set(), [], []
    for row in sorted((all_rows[r] for r in supported_cards), key=priority):
        if occupied.intersection(row["members"]):
            continue
        occupied.update(row["members"])
        selected.append(row)
        changes.append({"original_members": list(row["members"]), "children": [{"members": list(row["members"]),
            "supported": True, "card": deepcopy(supported_cards[row["membership_revision"]])}],
            "proposal_revision": row["membership_revision"]})
    # Deferral applies even to untouched alternatives: a later reciprocal query
    # must not quietly rebase them onto this work unit's committed groups.
    deferred, deferred_keys = list(plan["deferred_memberships"]), set(plan["deferred_pair_keys"])
    covered, overlap = [], []
    selected_sets = [set(r["members"]) for r in selected]
    selected_ids = {r["membership_revision"] for r in selected}
    for row in all_rows.values():
        if row["membership_revision"] in selected_ids or not occupied.intersection(row["members"]):
            continue
        if any(set(row["members"]) <= members for members in selected_sets):
            covered.append(row["membership_revision"])
            continue
        keys = sorted({digest(p) for p in row["direct_pairs"] if not any(set(p) <= members for members in selected_sets)})
        deferred_keys.update(keys)
        overlap.append(row["membership_revision"])
        deferred.append({"membership_revision": row["membership_revision"], "members": row["members"], "direct_pair_keys": keys})
    documents = {i for u in plan["units"].values() for i in u["members"]}
    return {"changes": changes, "selected_memberships": sorted(selected_ids),
        "overlap_deferred_memberships": sorted(overlap), "already_covered_memberships": sorted(covered),
        "deferred_pair_keys": sorted(deferred_keys), "deferred_memberships": _deferred(deferred, documents)}
