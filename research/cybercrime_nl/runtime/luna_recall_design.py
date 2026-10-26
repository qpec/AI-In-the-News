"""Pure matched-frame design for the separately registered Luna recall upgrade.

No I/O or dispatch authority. Old and successor predictions share one frozen
pair universe and one new reference per selected pair. Exposed inputs remain
flagged; these model-reference results do not establish independent human truth.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
import platform

from newsresearch.common import digest
from final_validation_design import nested_srs_ranks, pair_count, positive_total_bounds
import luna_quality_design as prior

METHOD = "luna-recall-matched-probability-design-v1"
LIMITS = {"internal": 1000, "external": 6000, "singleton": 200}
RISK_FIELDS = {"repair_proposal", "development_positive_or_uncertain"}
LABELS = {"same_event", "negative", "unknown"}


def require(value, reason):
    if not value:
        raise ValueError("luna_recall_design_" + reason)


pair_key = prior.pair_key


def _prediction(documents, value):
    require(isinstance(value, dict) and {"groups", "accepted_group_ids"} <= set(value), "successor_fields")
    groups, accepted = value["groups"], value["accepted_group_ids"]
    require(isinstance(groups, dict) and isinstance(accepted, list) and all(isinstance(g, str) for g in accepted)
        and len(accepted) == len(set(accepted)) and set(accepted) <= set(groups), "successor_groups")
    seen, normalized = set(), {}
    for key, members in groups.items():
        require(isinstance(key, str) and key and isinstance(members, list) and members
            and all(isinstance(i, str) and i in documents for i in members)
            and len(members) == len(set(members)) and not seen.intersection(members), "successor_partition")
        normalized[key] = sorted(members)
        seen.update(members)
    membership = {i: group for group in accepted for i in groups[group]}
    if "unresolved_ids" in value:
        require(isinstance(value["unresolved_ids"], list) and len(value["unresolved_ids"]) == len(set(value["unresolved_ids"]))
            and set(value["unresolved_ids"]) == set(documents) - seen, "successor_unresolved_partition")
    if "provisional_group_ids" in value:
        require(isinstance(value["provisional_group_ids"], list)
            and len(value["provisional_group_ids"]) == len(set(value["provisional_group_ids"]))
            and set(value["provisional_group_ids"]) == set(groups) - set(accepted), "successor_provisional_partition")
    if "membership" in value:
        require(value["membership"] == {i: membership.get(i) for i in documents}, "successor_membership")
    return normalized, sorted(accepted), membership


def _coverage(documents, groups, accepted, alias_rows):
    provisional = sorted(set(groups) - set(accepted))
    def hist(ids):
        return dict(sorted(Counter(str(len(groups[g])) for g in ids).items(), key=lambda item: int(item[0])))
    return {"documents": len(documents), "source_records": alias_rows, "alias_records": alias_rows - len(documents),
        "groups": len(groups), "accepted_groups": len(accepted), "provisional_groups": len(provisional),
        "accepted_inputs": sum(len(groups[g]) for g in accepted),
        "provisional_inputs": sum(len(groups[g]) for g in provisional),
        "unresolved_inputs": len(documents) - sum(len(members) for members in groups.values()),
        "accepted_singletons": sum(len(groups[g]) == 1 for g in accepted),
        "group_size_histograms": {"all": hist(groups), "accepted": hist(accepted), "provisional": hist(provisional)}}


class _JoinedFrame:
    """Rank filtered within-group pairs with O(documents) rows, no pair matrix."""
    def __init__(self, groups, accepted, other_membership, *, equal, exposed, exposed_documents):
        self.other, self.equal, self.exposed, self.exposure = other_membership, equal, exposed, exposed_documents
        self.rows, self.prefix, total = [], [], 0
        for group in accepted:
            members = tuple(groups[group])
            counts = Counter((other_membership.get(i), i in exposed_documents) for i in members)
            remaining = Counter(i in exposed_documents for i in members)
            for position, left in enumerate(members[:-1]):
                other, known = other_membership.get(left), left in exposed_documents
                counts[(other, known)] -= 1
                remaining[known] -= 1
                if not exposed and known:
                    continue
                statuses = (False, True) if exposed and known else (exposed,)
                allowed = sum(remaining[status] for status in statuses)
                same = sum(counts[(other, status)] for status in statuses) if other is not None else 0
                count = same if equal else allowed - same
                if count:
                    total += count
                    self.rows.append((members, position))
                    self.prefix.append(total)
        self.population = total

    def pair_at(self, rank):
        require(type(rank) is int and 0 <= rank < self.population, "pair_rank")
        row = bisect_right(self.prefix, rank)
        offset = rank - (self.prefix[row - 1] if row else 0)
        members, position = self.rows[row]
        left = members[position]
        for right in members[position + 1:]:
            same = left in self.other and right in self.other and self.other[left] == self.other[right]
            exposed = left in self.exposure or right in self.exposure
            if same == self.equal and exposed == self.exposed:
                if offset == 0:
                    return left, right
                offset -= 1
        raise AssertionError("joined_pair_rank_inconsistent")


class _ExplicitFrame:
    def __init__(self, pairs):
        self.pairs = pairs
        self.population = len(pairs)

    def pair_at(self, rank):
        return self.pairs[rank]


def _cell_id(old, new, risk, exposed):
    return f"{int(old)}{int(new)}:{risk}:{'exposed' if exposed else 'unexposed'}"


def _frames(source, successor, exposed_documents, risk_pairs):
    documents, old_groups, old_accepted, manifest, old_membership, hashes, alias_rows = prior._source(source)
    new_groups, new_accepted, new_membership = _prediction(documents, successor)
    require(isinstance(exposed_documents, (list, tuple, set, frozenset))
        and all(isinstance(i, str) and i in documents for i in exposed_documents), "exposure_documents")
    exposed = set(exposed_documents)
    require(isinstance(risk_pairs, dict) and set(risk_pairs) == RISK_FIELDS, "risk_fields")
    risks, risk_binding = set(), {}
    for reason in sorted(RISK_FIELDS):
        require(isinstance(risk_pairs[reason], (list, tuple, set, frozenset)), "risk_pairs")
        pairs = set()
        for row in risk_pairs[reason]:
            require(isinstance(row, (list, tuple)) and len(row) == 2
                and all(isinstance(i, str) and i in documents for i in row) and row[0] != row[1], "risk_pair_identity")
            pairs.add(tuple(sorted(row)))
        risks.update(pairs)
        risk_binding[reason] = sorted(pairs)
    candidates, candidate_counts = prior._candidate_frame(source, documents, old_membership, hashes)
    for edge in source["unresolved_edges"]:
        risks.update(tuple(sorted((edge["document_id"], other))) for other in edge["source_document_ids"]
            if other != edge["document_id"])
    frames, cells = {}, []
    for old, new in ((True, True), (False, True), (True, False)):
        for exposure in (False, True):
            key = _cell_id(old, new, "na", exposure)
            frames[key] = _JoinedFrame(new_groups if new else old_groups, new_accepted if new else old_accepted,
                old_membership if new else new_membership, equal=old and new,
                exposed=exposure, exposed_documents=exposed)
            cells.append({"cell_id": key, "old_joined": old, "new_joined": new, "risk": "na", "exposed": exposure})
    remaining = {(risk, exposure): [] for risk in ("high", "remaining") for exposure in (False, True)}
    for left, right in candidates:
        if left in new_membership and right in new_membership and new_membership[left] == new_membership[right]:
            continue
        remaining[("high" if (left, right) in risks else "remaining", left in exposed or right in exposed)].append((left, right))
    for (risk, exposure), pairs in remaining.items():
        key = _cell_id(False, False, risk, exposure)
        frames[key] = _ExplicitFrame(pairs)
        cells.append({"cell_id": key, "old_joined": False, "new_joined": False, "risk": risk, "exposed": exposure})
    cells = sorted(({**cell, "population_size": frames[cell["cell_id"]].population} for cell in cells), key=lambda c: c["cell_id"])
    old_pairs = sum(pair_count(len(old_groups[g])) for g in old_accepted)
    new_pairs = sum(pair_count(len(new_groups[g])) for g in new_accepted)
    require(sum(c["population_size"] for c in cells if c["old_joined"]) == old_pairs
        and sum(c["population_size"] for c in cells if c["new_joined"]) == new_pairs, "coassignment_partition")
    universe = sum(c["population_size"] for c in cells)
    singletons = sorted(new_groups[g][0] for g in new_accepted if len(new_groups[g]) == 1)
    source_binding = {"documents": [{"document_id": i, "input_sha256": hashes[i],
        "article_row_ids": documents[i].get("article_row_ids", [i])} for i in sorted(documents)],
        "baseline": {"groups": old_groups, "accepted_group_ids": old_accepted},
        "successor": {"groups": new_groups, "accepted_group_ids": new_accepted},
        "candidate_manifest_sha256": digest(manifest), "unresolved_edges_sha256": digest(source["unresolved_edges"]),
        "exposed_documents": sorted(exposed), "risk_pairs": risk_binding, "provenance": source["provenance"], "counts": source["counts"]}
    summary = {"method": METHOD, "source_binding_sha256": digest(source_binding), "cells": cells,
        "universe_size": universe, "baseline_coassigned_pairs": old_pairs, "successor_coassigned_pairs": new_pairs,
        "successor_external_pairs": universe - new_pairs, "successor_singletons": len(singletons),
        "original_candidate_counts": candidate_counts, "all_possible_pairs": pair_count(len(documents)),
        "excluded_nonjoined_pairs": pair_count(len(documents)) - universe,
        "exposed_documents": len(exposed), "risk_pair_counts": {key: len(value) for key, value in risk_binding.items()},
        "coverage": {"baseline": _coverage(documents, old_groups, old_accepted, alias_rows),
            "successor": _coverage(documents, new_groups, new_accepted, alias_rows)}}
    return frames, summary, singletons, manifest, hashes


def frame_summary(source, successor, *, exposed_documents, risk_pairs):
    """Pre-draw populations only; no labels or realized sample costs are inputs."""
    return _frames(source, successor, exposed_documents, risk_pairs)[1]


def _allocate(cells, size):
    active = [cell for cell in cells if cell["population_size"]]
    population = sum(cell["population_size"] for cell in active)
    size = min(size, population)
    require(size >= len(active), "positive_cell_inclusion")
    result = {cell["cell_id"]: 0 for cell in cells}
    for cell in active:
        result[cell["cell_id"]] = 1
    left = size - len(active)
    while left:
        eligible = [cell for cell in active if result[cell["cell_id"]] < cell["population_size"]]
        total_weight = sum(cell["population_size"] for cell in eligible)
        capped = [cell for cell in eligible if left * cell["population_size"]
            >= (cell["population_size"] - result[cell["cell_id"]]) * total_weight]
        if capped:
            for cell in capped:
                key = cell["cell_id"]
                left -= cell["population_size"] - result[key]
                result[key] = cell["population_size"]
            continue
        fractions = []
        for cell in eligible:
            allocated, remainder = divmod(left * cell["population_size"], total_weight)
            result[cell["cell_id"]] += allocated
            fractions.append((-remainder, cell["cell_id"]))
        for _, key in sorted(fractions)[:size - sum(result.values())]:
            result[key] += 1
        left = 0
    require(sum(result.values()) == size and all(result[c["cell_id"]] <= c["population_size"] for c in cells), "allocation_partition")
    return result


def _sample(population, count, seed, key):
    ranks = nested_srs_ranks(population, [count], seed=seed, stratum=METHOD + ":" + key)["rank_order"]
    return {"sample_size": len(ranks), "population_size": population, "rank_order": ranks,
        "inclusion_numerator": len(ranks), "inclusion_denominator": population,
        "weight_numerator": population, "weight_denominator": len(ranks), "slots": []}


def _count(population, labels, alpha):
    counts = Counter(labels)
    n, positive, unknown = len(labels), counts["same_event"], counts["unknown"]
    bounds = positive_total_bounds(population, n, positive, unresolved=unknown, tail_alpha=alpha)
    estimates = [population * positive / n, population * (positive + unknown) / n] if n else [0., 0.]
    return {"population_size": population, "selected": n, "positive": positive, "negative": counts["negative"],
        "unknown": unknown, "resolved": n - unknown, "positive_total_bounds": list(bounds),
        "ht_positive_total_range": estimates, "ht_positive_total": estimates[0] if unknown == 0 else None}


def _sum(cells, field):
    return [sum(cell[field][i] for cell in cells) for i in (0, 1)]


def _metrics(cells, flag):
    joined = [cell for cell in cells if cell[flag]]
    other = [cell for cell in cells if not cell[flag]]
    np, nc = (sum(cell["population_size"] for cell in rows) for rows in (joined, other))
    tp, fn = (_sum(rows, "ht_positive_total_range") for rows in (joined, other))
    tpb, fnb = (_sum(rows, "positive_total_bounds") for rows in (joined, other))
    precision_bounds = [prior._ratio(value, np) for value in tpb]
    recall_bounds = prior._recall_bounds(tpb, fnb)
    point_tp = tp[0] if all(cell["unknown"] == 0 for cell in joined) else None
    point_fn = fn[0] if all(cell["unknown"] == 0 for cell in other) else None
    return {"coassigned_population": np, "nonjoined_population": nc,
        "weighted_total_ranges": {"TP": tp, "FN": fn, "FP": [np - value for value in reversed(tp)], "TN": [nc - value for value in reversed(fn)]},
        "count_bounds": {"TP": tpb, "FN": fnb},
        "precision": {"estimate": prior._ratio(point_tp, np) if point_tp is not None else None,
            "estimate_range": [prior._ratio(value, np) for value in tp], "bounds": precision_bounds,
            "target": .95, "target_status": prior._target(precision_bounds, .95)},
        "candidate_recall": {"estimate": prior._ratio(point_tp, point_tp + point_fn) if point_tp is not None and point_fn is not None else None,
            "estimate_range": prior._recall_bounds(tp, fn), "bounds": recall_bounds, "target": .9,
            "target_status": prior._target(recall_bounds, .9), "unbiased_ratio_estimator": False,
            "zero_true_match_total_possible": tpb[0] + fnb[0] == 0},
        "certification": {"precision_supported": prior._target(precision_bounds, .95) == "supported",
            "recall_supported": prior._target(recall_bounds, .9) == "supported",
            "both_supported": prior._target(precision_bounds, .95) == prior._target(recall_bounds, .9) == "supported",
            "required_tp_lower": .95 * np, "allowed_fn_upper_at_tp_lower": tpb[0] / 9,
            "observed_fn_upper": fnb[1]}}


def build_design(source, successor, seed, *, exposed_documents, risk_pairs):
    """Freeze nominal allocations, SRS slots, RRF lists and deduplicated tasks."""
    require(isinstance(seed, str) and seed, "seed")
    frames, summary, singletons, manifest, hashes = _frames(source, successor, exposed_documents, risk_pairs)
    cells = summary["cells"]
    allocations = {}
    for side, name in ((True, "internal"), (False, "external")):
        allocations.update(_allocate([cell for cell in cells if cell["new_joined"] == side], LIMITS[name]))
    tasks, sampled = {}, []
    def add(left, right, slot):
        left, right = sorted((left, right))
        key = pair_key(left, right)
        tasks.setdefault(key, {"pair_key": key, "left": left, "right": right, "slot_ids": []})["slot_ids"].append(slot)
        return key
    for cell in cells:
        key = cell["cell_id"]
        sample = {**cell, **_sample(cell["population_size"], allocations[key], seed, key)}
        for rank in sample["rank_order"]:
            left, right = frames[key].pair_at(rank)
            slot = digest({"method": METHOD, "seed": seed, "cell_id": key, "rank": rank})
            pair = add(left, right, slot)
            sample["slots"].append({"slot_id": slot, "rank": rank, "pair_key": pair, "left": left, "right": right})
        sampled.append(sample)
    singleton = _sample(len(singletons), min(LIMITS["singleton"], len(singletons)), seed, "singleton")
    for rank in singleton["rank_order"]:
        anchor = singletons[rank]
        slot = digest({"method": METHOD, "seed": seed, "singleton_rank": rank})
        ranked, missing = prior._ranked_candidates(anchor, manifest, hashes)
        candidates = []
        for order, (other, score) in enumerate(ranked, 1):
            child = digest({"anchor_slot": slot, "pair_key": pair_key(anchor, other)})
            key = add(anchor, other, child)
            candidates.append({"slot_id": child, "document_id": other, "pair_key": key, "rank": order,
                "rrf_numerator": score.numerator, "rrf_denominator": score.denominator})
        singleton["slots"].append({"slot_id": slot, "rank": rank, "document_id": anchor,
            "candidates": candidates, "candidate_count": len(candidates), "missing_channels": missing,
            "search_status": "zero_candidates" if not candidates else "shortlist_under_20" if len(candidates) < 20 else "top_20"})
    for task in tasks.values():
        task["slot_ids"].sort()
    slot_count = sum(cell["sample_size"] for cell in sampled) + sum(slot["candidate_count"] for slot in singleton["slots"])
    require(slot_count <= 11000 and len(tasks) <= slot_count, "pair_slot_limit")
    family = sum(cell["population_size"] > 0 for cell in cells) + int(bool(singletons))
    alpha = .05 / (2 * max(1, family))
    ideal = [{**cell, **_count(cell["population_size"],
        ["same_event" if cell["new_joined"] else "negative"] * cell["sample_size"], alpha)} for cell in sampled]
    best = _metrics(ideal, "new_joined")
    result = {"method": METHOD, "seed": seed, "seed_sha256": digest(seed), "source_binding_sha256": summary["source_binding_sha256"],
        "frame": summary, "frame_sha256": digest(summary), "limits": dict(LIMITS),
        "samples": {"pair_cells": sampled, "singleton": singleton},
        "pair_tasks": [tasks[key] for key in sorted(tasks)], "unique_pair_tasks": len(tasks), "pair_slots_before_dedup": slot_count,
        "inference": {"family_alpha": .05, "count_intervals": family, "tail_alpha": alpha if family else None,
            "looks": 1, "baseline_and_successor_share_reference": True,
            "exposed_pairs_are_not_independent_holdout": True, "reference": "dependent Luna final-rubric judgments",
            "negative_rule": "related_event_probability_plus_different_event_probability_at_least_0.85",
            "global_recall_claimed": False, "sample_resize_after_draw_allowed": False},
        "rng": {"algorithm": "python.random.Random.sample(range)", "python": platform.python_version()},
        "preflight": {"assumption": "all_selected_successor_internal_positive_external_negative_no_unknowns",
            "best_case_precision_lower": best["precision"]["bounds"][0],
            "best_case_recall_lower": best["candidate_recall"]["bounds"][0],
            "both_targets_certifiable_in_best_case": best["certification"]["both_supported"],
            "descriptive_audit_allowed_if_not_certifiable": True, "sample_expansion_authorized": False}}
    return {**result, "design_sha256": digest(result)}


def compute_report(design, pair_labels):
    """One matched final analysis; no labels alter membership, slots or weights."""
    require(isinstance(design, dict) and design.get("method") == METHOD
        and design.get("design_sha256") == digest({k: v for k, v in design.items() if k != "design_sha256"}), "design_binding")
    keys = {task["pair_key"] for task in design["pair_tasks"]}
    require(isinstance(pair_labels, dict) and set(pair_labels) <= keys
        and all(isinstance(label, str) and label in LABELS for label in pair_labels.values()), "pair_labels")
    alpha = design["inference"]["tail_alpha"] or .025
    cells = [{**{k: sample[k] for k in ("cell_id", "old_joined", "new_joined", "risk", "exposed")},
        **_count(sample["population_size"], [pair_labels.get(slot["pair_key"], "unknown") for slot in sample["slots"]], alpha)}
        for sample in design["samples"]["pair_cells"]]
    singleton_sample = design["samples"]["singleton"]
    outcomes = []
    for slot in singleton_sample["slots"]:
        labels = [pair_labels.get(row["pair_key"], "unknown") for row in slot["candidates"]]
        label = "same_event" if "same_event" in labels else "negative" if labels and all(value == "negative" for value in labels) else "unknown"
        outcomes.append({"slot_id": slot["slot_id"], "document_id": slot["document_id"], "label": label,
            "outcome": "detected_missed_match" if label == "same_event" else "no_match_in_shortlist" if label == "negative" else "unknown",
            "candidate_count": len(labels), "search_status": slot["search_status"], "missing_channels": slot["missing_channels"]})
    singleton = _count(singleton_sample["population_size"], [row["label"] for row in outcomes], alpha)
    baseline, successor = (_metrics(cells, flag) for flag in ("old_joined", "new_joined"))
    changes = {}
    for metric in ("precision", "candidate_recall"):
        old, new = baseline[metric], successor[metric]
        changes[metric] = {"estimate": new["estimate"] - old["estimate"] if new["estimate"] is not None and old["estimate"] is not None else None,
            "conservative_bounds": [new["bounds"][0] - old["bounds"][1], new["bounds"][1] - old["bounds"][0]]
                if all(value is not None for value in old["bounds"] + new["bounds"]) else None}
    ns = singleton["population_size"]
    return {"method": METHOD, "design_sha256": design["design_sha256"], "frame_sha256": design["frame_sha256"],
        "cells": cells, "baseline": baseline, "successor": successor, "matched_changes": changes,
        "exposure": {name: {"baseline": _metrics([cell for cell in cells if cell["exposed"] == exposed], "old_joined"),
            "successor": _metrics([cell for cell in cells if cell["exposed"] == exposed], "new_joined")}
            for name, exposed in (("exposed", True), ("unexposed", False))},
        "singleton_missed_match_rate": {**singleton,
            "estimate": prior._ratio(singleton["ht_positive_total"], ns) if singleton["ht_positive_total"] is not None else None,
            "estimate_range": [prior._ratio(value, ns) for value in singleton["ht_positive_total_range"]],
            "bounds": [prior._ratio(value, ns) for value in singleton["positive_total_bounds"]], "outcomes": outcomes,
            "zero_candidates": sum(row["candidate_count"] == 0 for row in outcomes),
            "short_nonempty_lists": sum(0 < row["candidate_count"] < 20 for row in outcomes),
            "full_20_lists": sum(row["candidate_count"] == 20 for row in outcomes)},
        "unique_pair_outcomes": dict(Counter(pair_labels.get(key, "unknown") for key in sorted(keys))),
        "coverage": design["frame"]["coverage"], "frame": design["frame"], "preflight": design["preflight"],
        "inference": design["inference"], "human_truth_claimed": False, "group_coherence_claimed": False,
        "global_recall_claimed": False, "actual_attempt_counts_available": False}
