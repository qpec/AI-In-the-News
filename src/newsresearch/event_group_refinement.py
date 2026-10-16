"""Pure deterministic refinement of provisional complete-link groups.

The caller must register and execute real data work through Research.execute.
Graph-objective gains do not establish better real-world event identity.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any

from .common import digest
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES

METHOD = "duplicate-discounted-bottleneck-clique-refinement-v1"
MAX_PASSES = 20
EPSILON = 1e-9
MIN_GAIN = 1e-12


def refine(
    ids: Sequence[str], edges: Sequence[Mapping[str, Any]],
    baseline_groups: Sequence[Mapping[str, Any]], rule: Mapping[str, Any],
    body_ids: Mapping[str, str],
) -> dict[str, Any]:
    """Improve a declared graph objective without adding or relaxing an edge."""
    if (any(not isinstance(item, str) or not item for item in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError("article IDs must be unique nonempty strings")
    sources = sorted(ids)
    if any(not isinstance(body_ids.get(item), str) or not body_ids[item] for item in sources):
        raise ValueError("every article needs a nonempty body identity")
    if tuple(rule.get("features", ())) != FEATURES:
        raise ValueError("the exact five-feature rule is required")
    cuts = rule.get("thresholds")
    if (not isinstance(cuts, (tuple, list)) or len(cuts) != len(FEATURES)
            or any(isinstance(cut, bool) or not isinstance(cut, (int, float))
                   or not math.isfinite(cut) or not -1 <= cut < 1 for cut in cuts)):
        raise ValueError("five finite thresholds below one are required")
    copies = Counter(body_ids[item] for item in sources)
    weights: dict[tuple[str, str], float] = {}
    original: dict[tuple[str, str], dict[str, Any]] = {}
    adjacent: dict[str, set[str]] = {item: set() for item in sources}
    pair_ids: set[str] = set()
    for edge in edges:
        left, right = edge.get("left"), edge.get("right")
        if left not in adjacent or right not in adjacent or left == right:
            raise ValueError("edges must join two eligible articles")
        pair = tuple(sorted((left, right)))
        pair_id = edge.get("pair_id")
        if (pair in weights or not isinstance(pair_id, str) or not pair_id
                or pair_id in pair_ids):
            raise ValueError("duplicate or missing edge identities")
        if edge.get("status") != "completed" or not predicts(edge, rule):
            raise ValueError("all supplied edges must completely pass the unchanged rule")
        features = edge["features"]
        strength = min((float(features[name]) - cut) / (1 - cut)
                       for name, cut in zip(FEATURES, cuts, strict=True))
        weights[pair] = (EPSILON + strength) / (copies[body_ids[left]] * copies[body_ids[right]])
        original[pair] = dict(edge)
        adjacent[left].add(right)
        adjacent[right].add(left)
        pair_ids.add(pair_id)

    ordered = sorted(baseline_groups, key=lambda group: tuple(sorted(group["members"])))
    groups: dict[int, set[str]] = {}
    owners: dict[str, int] = {}
    old_ids: dict[tuple[str, ...], str] = {}
    group_ids: set[str] = set()
    for token, group in enumerate(ordered):
        baseline_members = list(group["members"])
        group_id = group.get("group_id")
        if (not baseline_members or len(set(baseline_members)) != len(baseline_members)
                or not isinstance(group_id, str) or not group_id or group_id in group_ids):
            raise ValueError("baseline groups need unique identities and nonempty unique members")
        if any(item not in adjacent or item in owners for item in baseline_members):
            raise ValueError("baseline must partition eligible articles exactly once")
        if any(tuple(sorted(pair)) not in weights for pair in combinations(baseline_members, 2)):
            raise ValueError("every baseline group must be a complete passing clique")
        groups[token] = set(baseline_members)
        owners.update(dict.fromkeys(baseline_members, token))
        old_ids[tuple(sorted(baseline_members))] = group_id
        group_ids.add(group_id)
    if set(owners) != set(sources):
        raise ValueError("baseline must cover every eligible article")
    baseline_owners = dict(owners)

    def signature(token: int) -> tuple[str, ...]:
        return tuple(sorted(groups[token]))

    def edge_weight(left: str, right: str) -> float:
        return weights[(left, right) if left < right else (right, left)]

    def total(assignment: Mapping[str, int]) -> tuple[float, int]:
        included = [weights[pair] for pair in sorted(weights) if assignment[pair[0]] == assignment[pair[1]]]
        return math.fsum(included), len(included)

    baseline_objective, baseline_internal = total(owners)
    moves: list[dict[str, Any]] = []
    converged = False
    passes = 0
    for passes in range(1, MAX_PASSES + 1):
        changed = False
        for item in sources:
            source = owners[item]
            old = signature(source)
            lost = math.fsum(edge_weight(item, other) for other in old if other != item)
            # Moving to a fresh singleton has gain -lost <= 0, so cannot win.
            candidates: list[tuple[float, tuple[str, ...], int]] = []
            target_tokens = {owners[other] for other in adjacent[item]} - {source}
            for target in sorted(target_tokens, key=signature):
                members = signature(target)
                if all(other in adjacent[item] for other in members):
                    gain = math.fsum(edge_weight(item, other) for other in members) - lost
                    if gain > MIN_GAIN:
                        candidates.append((-gain, members, target))
            if not candidates:
                continue
            negative_gain, target_before, target = min(candidates)
            groups[source].remove(item)
            if not groups[source]:
                del groups[source]
            groups[target].add(item)
            owners[item] = target
            moves.append({"kind": "relocate", "article": item, "source_before": list(old),
                          "target_before": list(target_before), "objective_delta": -negative_gain})
            changed = True

        group_pairs = {tuple(sorted((owners[left], owners[right]))) for left, right in weights
                       if owners[left] != owners[right]}
        merges: list[tuple[float, tuple[str, ...], tuple[str, ...], int, int]] = []
        for first, second in group_pairs:
            a, b = signature(first), signature(second)
            if all(right in adjacent[left] for left in a for right in b):
                gain = math.fsum(edge_weight(left, right) for left in a for right in b)
                if gain > MIN_GAIN:
                    merges.append((-gain, a, b, first, second))
        for negative_gain, a, b, first, second in sorted(merges):
            if first not in groups or second not in groups or signature(first) != a or signature(second) != b:
                continue
            groups[first].update(groups.pop(second))
            owners.update(dict.fromkeys(b, first))
            moves.append({"kind": "merge", "source_before": list(a), "target_before": list(b),
                          "objective_delta": -negative_gain})
            changed = True
        if not changed:
            converged = True
            break

    objective, internal = total(owners)
    if objective + MIN_GAIN < baseline_objective:
        raise ValueError("refinement decreased the baseline objective")
    output = []
    for token in sorted(groups, key=signature):
        members = signature(token)
        group_id = old_ids.get(members) or digest({"method": METHOD, "members": list(members)})
        output.append({"group_id": group_id, "members": list(members)})
    bridges = [original[pair] for pair in sorted(original) if owners[pair[0]] != owners[pair[1]]]
    changed_articles = [item for item in sources
                        if groups[owners[item]] != set(ordered[baseline_owners[item]]["members"])]
    return {"groups": output, "bridges": bridges,
            "counts": {"groups": len(output),
                       "multi_article_groups": sum(len(group["members"]) > 1 for group in output),
                       "singletons": sum(len(group["members"]) == 1 for group in output),
                       "passing_edges": len(weights), "bridge_edges": len(bridges)},
            "diagnostics": {"method": METHOD, "baseline_objective": baseline_objective,
                            "objective": objective, "objective_gain": objective - baseline_objective,
                            "baseline_internal_edges": baseline_internal, "internal_edges": internal,
                            "moved_articles": len(changed_articles), "changed_article_ids": changed_articles,
                            "passes": passes, "converged": converged,
                            "optimization_limit_reached": not converged, "maximum_passes": MAX_PASSES,
                            "duplicate_body_families": sum(count > 1 for count in copies.values()),
                            "accepted_dossiers": 0}, "moves": moves}
