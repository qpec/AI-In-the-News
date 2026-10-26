"""Deterministic bounded repair proposals and atomic membership transitions."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from fractions import Fraction
from itertools import combinations

import dossier_candidates as candidates
import luna_recall_contract as contract
from newsresearch.common import ResearchError, digest

METHOD = "luna-recall-disjoint-full-qa-repair-v1"
MAX_ROUNDS, MAX_TARGETS, BATCH_PAIRS = 3, 3, 600


def task(pair):
    a, b = sorted(pair)
    return {"pair_key": contract.pair_key(a, b), "left": a, "right": b, "slot_ids": []}


def initial_state(source):
    groups = deepcopy(source["groups"])
    covered = {i for members in groups.values() for i in members}
    cards = {}
    for g, members in groups.items():
        matches = [r for r in source.get("prior_history", {}).get("cards", {}).get(g, []) if r["membership_revision"] == digest(sorted(members))]
        cards[g] = {"retained_original_references": matches, "owner": source["provenance"].get("source_owner"),
            "head": source["provenance"].get("source_head"), "availability": "referenced" if matches else "unknown"}
    return {"groups": groups, "accepted_group_ids": sorted(source["accepted_group_ids"]),
        "group_states": deepcopy(source.get("group_states", {})),
        "unresolved_ids": sorted(set(source["documents"]) - covered), "cards": cards, "lineage": []}


def membership(state):
    result = {i: g for g, members in state["groups"].items() for i in members}
    if len(result) != sum(map(len, state["groups"].values())):
        raise ResearchError("recall_overlapping_memberships")
    return result


def pilot(source, seed):
    owner = membership(initial_state(source))
    accepted = set(source["accepted_group_ids"])
    pools = {"positive_nonjoin": [], "unknown_nonjoin": [], "internal": []}
    labels = source["audit"]["labels"]
    for key, pair in source["audit"]["source_pairs"].items():
        a, b = pair
        internal = owner.get(a) in accepted and owner.get(a) == owner.get(b)
        label = labels.get(key, "unknown")
        if internal:
            pools["internal"].append(task(pair))
        elif label == "same_event":
            pools["positive_nonjoin"].append(task(pair))
        elif label == "unknown":
            pools["unknown_nonjoin"].append(task(pair))
    selected = []
    counts = {}
    for name, limit in (("positive_nonjoin", 100), ("unknown_nonjoin", 50), ("internal", 50)):
        ordered = sorted(pools[name], key=lambda r: (0 if name == "internal" and labels.get(r["pair_key"]) == "negative" else 1,
            digest([seed, name, r["pair_key"]])))
        selected.extend(ordered[:limit])
        counts[name] = {"available": len(ordered), "selected": min(limit, len(ordered)), "target": limit}
    return {"pair_tasks": selected, "strata": counts, "development_only": True}


def compatible_prior(source):
    result = []
    for row in source.get("prior_history", {}).get("pair_observations", []):
        if not (row.get("compatible_focal_rubric") and row.get("usable") and row.get("status") == "valid"
                and isinstance(row.get("probabilities"), dict) and len(row.get("pair", [])) == 2
                and set(row["pair"]) <= set(source["documents"])
                and (row.get("reference_model") == "gpt-6-luna" or (row.get("role") == "native_seed" and row.get("reference_model") is None))):
            continue
        clear = len(row.get("clarity", [])) == 2 and all(c and c.get("status") == "valid"
            and c.get("label") == "clear_single_event" and (c.get("probabilities") or {}).get("clear_single_event", 0) >= .85
            for c in row["clarity"])
        p = row["probabilities"]
        label = "unknown"
        if clear:
            if row["label"] == "same_event" and p.get("same_event", 0) >= .85:
                label = "same_event"
            elif p.get("related_event", 0)+p.get("different_event", 0) >= .85:
                label = "negative"
        result.append({**row, "native_label": row["label"], "native_negative_rule": row.get("negative_rule"),
            "label": label, "operational_negative_rule": "registered_sum_nonmatch_085", "clarification": False})
    return result


def split_eligibility(source):
    owner = membership(initial_state(source))
    selected = set()
    audit_negative = [{"pair": source["audit"]["source_pairs"][k], "label": "negative"}
        for k,v in source["audit"]["labels"].items() if v == "negative" and k in source["audit"]["source_pairs"]]
    for row in [*compatible_prior(source), *audit_negative]:
        a, b = row["pair"]
        if row.get("label") in {"negative", "related_event", "different_event"} and owner.get(a) and owner.get(a) == owner.get(b):
            selected.add(owner[a])
    for row in source.get("prior_history", {}).get("membership_attempts", []):
        if row.get("label") == "incoherent_group":
            for g, members in source["groups"].items():
                if row["membership_revision"] == digest(sorted(members)):
                    selected.add(g)
    return {g: sorted(source["groups"][g]) for g in sorted(selected)}


def observations_by_pair(rows):
    result = defaultdict(list)
    for row in rows:
        result[row["pair_key"]].append(row)
    return dict(result)


def round_plan(source, state, observations, number):
    """At most three saved-RRF targets per anchor; no vector reconstruction."""
    units = {**deepcopy(state["groups"]), **{"unresolved:" + i: [i] for i in state["unresolved_ids"]}}
    owner = {i: g for g, members in units.items() for i in members}
    ranking = defaultdict(lambda: Fraction(0))
    for a, channels in source["candidate_manifest"]["neighbors"].items():
        for rows in channels.values():
            for row in rows:
                b = row["document_id"]
                if a != b:
                    ranking[tuple(sorted([a, b]))] += Fraction(1, 60 + row["rank"])
    pairs = {tuple(sorted([r["left"], r["right"]])) for r in source["candidate_manifest"]["pairs"]}
    for row in source.get("unresolved_edges", []):
        pairs.update(tuple(sorted([row["document_id"], b])) for b in row["source_document_ids"] if b != row["document_id"])
    misses = {tuple(sorted(source["audit"]["source_pairs"][k])) for k, label in source["audit"]["labels"].items()
        if label == "same_event" and k in source["audit"]["source_pairs"]}
    pairs |= misses
    best = {}
    for a, b in pairs:
        if a not in owner or b not in owner or owner[a] == owner[b]:
            continue
        priority = 0 if (a, b) in misses else 1 if min(len(units[owner[a]]), len(units[owner[b]])) == 1 else 2
        rank = (priority, -ranking[(a, b)], a, b)
        for anchor, target in ((owner[a], owner[b]), (owner[b], owner[a])):
            if (anchor, target) not in best or rank < best[anchor, target][0]:
                best[anchor, target] = (rank, [a, b])
    anchors = defaultdict(list)
    for (anchor, target), (rank, pair) in best.items():
        anchors[anchor].append((rank, target, pair))
    proposals = []
    for anchor in sorted(anchors):
        for n, (rank, target, pair) in enumerate(sorted(anchors[anchor]), 1):
            proposals.append({"anchor": anchor, "target": target, "pair": pair, "rank": n,
                "priority": rank[0], "rrf": str(-rank[1])})
    proposals.sort(key=lambda p: (p["priority"], p["rank"], -Fraction(p["rrf"]), p["anchor"], p["target"]))
    tasks, seen = [], set()
    known = observations_by_pair(observations)
    for row in proposals:
        t = task(row["pair"])
        if t["pair_key"] not in seen and contract.combine(known.get(t["pair_key"], [])) == "unknown":
            tasks.append(t)
        seen.add(t["pair_key"])
    return {"method": METHOD, "round": number, "state_digest": digest(state), "units": units,
        "proposals": proposals, "pair_tasks": tasks, "maximum_targets": MAX_TARGETS}


def union_proposals(plan, observations):
    known = observations_by_pair(observations)
    positive = defaultdict(list)
    for row in plan["proposals"]:
        rows = known.get(contract.pair_key(*row["pair"]), [])
        if contract.combine(rows) == "same_event":
            score = min(r["probabilities"]["same_event"] for r in rows if r["label"] == "same_event")
            if len(positive[row["anchor"]]) < MAX_TARGETS:
                positive[row["anchor"]].append({**row, "score": score})
    proposals = []
    for anchor, rows in positive.items():
        targets = sorted({r["target"] for r in rows})
        groups = [anchor, *targets]
        members = sorted({i for g in groups for i in plan["units"][g]})
        veto = any(contract.combine(known.get(contract.pair_key(a, b), [])) == "negative" for a, b in combinations(members, 2))
        proposals.append({"anchor": anchor, "targets": targets, "groups": groups, "members": members,
            "negative_veto": veto,
            "supports": [{"target": r["target"], "pair": r["pair"], "score": r["score"]} for r in rows],
            "membership_revision": digest(members), "minimum_support": min(r["score"] for r in rows),
            "new_pairs": len(members)*(len(members)-1)//2-sum(len(plan["units"][g])*(len(plan["units"][g])-1)//2 for g in groups)})
    proposals.sort(key=lambda p: (-p["minimum_support"], -p["new_pairs"], p["membership_revision"]))
    chosen, occupied = [], set()
    for p in proposals:
        if not occupied.intersection(p["members"]):
            chosen.append(p)
            occupied.update(p["members"])
    return chosen


def fallback(proposal, units, observations):
    if len(proposal["targets"]) <= 1:
        return []
    known = observations_by_pair(observations)
    result = []
    for target in proposal["targets"]:
        members = sorted(set(units[proposal["anchor"]]) | set(units[target]))
        if any(contract.combine(known.get(contract.pair_key(a, b), [])) == "negative" for a, b in combinations(members, 2)):
            continue
        result.append({**proposal, "targets": [target], "groups": [proposal["anchor"], target],
            "members": members, "membership_revision": digest(members), "fallback_from": proposal["membership_revision"],
            "negative_veto": False, "minimum_support": min(r["score"] for r in proposal["supports"] if r["target"] == target),
            "new_pairs": len(units[proposal["anchor"]])*len(units[target]),
            "supports": [r for r in proposal["supports"] if r["target"] == target]})
    return result


def split_components(members, observations):
    known = observations_by_pair(observations)
    rows, clarity = [], {}
    for a, b in combinations(members, 2):
        evidence = known.get(contract.pair_key(a, b), [])
        if contract.combine(evidence) == "same_event":
            good = [r for r in evidence if r["label"] == "same_event"]
            selected = min(good, key=lambda r: r["probabilities"]["same_event"])
            rows.append({"left": a, "right": b, "label": "same_event", "status": "valid", "probabilities": selected["probabilities"]})
            for i, c in zip(selected["pair"], selected["clarity"], strict=True):
                if i not in clarity or c["probability"] < clarity[i]["probability"]:
                    clarity[i] = c
    return candidates.complete_link_partition(members, rows, clarity=clarity, threshold=.85, clarity_threshold=.85)


def commit(state, replacements, *, reason):
    """Complete atomic transitions; unsupported split children remain provisional."""
    result = deepcopy(state)
    occupied = set()
    for change in replacements:
        old = set(change["original_members"])
        flat = [i for child in change["children"] for i in child["members"]]
        if len(flat) != len(set(flat)) or set(flat) != old or occupied & old:
            raise ResearchError("recall_atomic_partition")
        occupied |= old
        current = membership(result)
        original_groups = {current[i] for i in old if i in current}
        if any(not set(result["groups"][g]) <= old for g in original_groups):
            raise ResearchError("recall_atomic_partial_group")
        for g in original_groups:
            del result["groups"][g]
            result["cards"].pop(g, None)
            result["group_states"].pop(g, None)
            if g in result["accepted_group_ids"]:
                result["accepted_group_ids"].remove(g)
        result["unresolved_ids"] = sorted(set(result["unresolved_ids"]) - old)
        for child in change["children"]:
            g = "recall-" + digest(sorted(child["members"]))[:24]
            result["groups"][g] = sorted(child["members"])
            result["group_states"][g] = "accepted" if child["supported"] else "provisional"
            if child["supported"]:
                result["accepted_group_ids"].append(g)
                result["cards"][g] = child["card"]
        result["lineage"].append({"reason": reason, "before": {g: state["groups"][g] for g in original_groups},
            "original_members": sorted(old), "children": change["children"]})
    result["accepted_group_ids"] = sorted(set(result["accepted_group_ids"]))
    if set(membership(result)) | set(result["unresolved_ids"]) != set(membership(state)) | set(state["unresolved_ids"]):
        raise ResearchError("recall_coverage_changed")
    return result
