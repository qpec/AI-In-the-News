"""Pure fixed sampling and finite-population reporting for the Luna quality audit.

No source access, registration or dispatch authority. The caller binds this
design to verified full sources and retains it before any model judgment.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from fractions import Fraction
import platform

from newsresearch.common import digest
from final_validation_design import nested_srs_ranks, pair_count, pair_from_rank, positive_total_bounds

METHOD = "luna-quality-fixed-probability-design-v1"
LIMITS = {"precision": 600, "nonjoined": 3000, "singleton": 200}
CHANNELS = ("vector", "word", "character")
TAIL_ALPHA = .05 / 6
LABELS = {"same_event", "negative", "unknown"}


def _require(value, reason):
    if not value:
        raise ValueError("luna_quality_design_" + reason)


def pair_key(left, right):
    _require(isinstance(left, str) and isinstance(right, str) and left and right and left != right,
             "distinct_document_ids")
    return digest(sorted((left, right)))


def _source(source):
    _require(isinstance(source, dict) and {"documents", "groups", "accepted_group_ids",
        "candidate_manifest", "unresolved_edges", "provenance", "counts"} <= set(source), "source_fields")
    documents, groups = source["documents"], source["groups"]
    _require(isinstance(documents, dict) and isinstance(groups, dict), "source_mappings")
    hashes, aliases = {}, set()
    for identity, value in documents.items():
        _require(isinstance(identity, str) and bool(identity) and isinstance(value, dict)
            and isinstance(value.get("title"), str) and isinstance(value.get("body"), str)
            and bool(value["body"].strip()), "full_document")
        full_hash = digest({"title": value["title"], "body": value["body"]})
        _require(value.get("input_sha256", full_hash) == full_hash, "input_hash")
        hashes[identity] = full_hash
        rows = value.get("article_row_ids", [identity])
        _require(isinstance(rows, list) and rows and all(isinstance(x, str) and x for x in rows)
            and len(rows) == len(set(rows)) and not aliases.intersection(rows), "article_alias_partition")
        aliases.update(rows)
    _require(len(set(hashes.values())) == len(hashes), "unique_full_input_population")
    normalized, allocated = {}, set()
    for identity, members in groups.items():
        _require(isinstance(identity, str) and identity and isinstance(members, list) and members
            and all(isinstance(x, str) and x in documents for x in members)
            and len(set(members)) == len(members) and not allocated.intersection(members), "group_partition")
        normalized[identity] = sorted(members)
        allocated.update(members)
    accepted = source["accepted_group_ids"]
    _require(isinstance(accepted, list) and all(isinstance(x, str) and x in groups for x in accepted)
        and len(accepted) == len(set(accepted)), "accepted_groups")
    manifest = source["candidate_manifest"]
    _require(isinstance(manifest, dict) and isinstance(manifest.get("document_ids"), list)
        and len(manifest["document_ids"]) == len(documents)
        and set(manifest["document_ids"]) == set(documents)
        and isinstance(manifest.get("pairs"), list) and isinstance(manifest.get("neighbors"), dict)
        and set(manifest["neighbors"]) <= set(documents), "candidate_manifest")
    for query, channels in manifest["neighbors"].items():
        _require(isinstance(channels, dict) and set(channels) <= set(CHANNELS), "candidate_channels")
        for channel, rows in channels.items():
            _require(isinstance(rows, list), "candidate_rank_rows")
            _require(all(isinstance(row, dict) and row.get("document_id") in documents
                and type(row.get("rank")) is int and row["rank"] > 0 for row in rows), "candidate_rank")
            _require(len({row["document_id"] for row in rows}) == len(rows)
                and {row["rank"] for row in rows} == set(range(1, len(rows) + 1)), "candidate_rank_partition")
    membership = {member: group for group in accepted for member in normalized[group]}
    return documents, normalized, sorted(accepted), manifest, membership, hashes, len(aliases)


def _candidate_frame(source, documents, membership, hashes):
    def canonical(left, right):
        _require(left in documents and right in documents, "candidate_endpoint")
        if left == right or hashes[left] == hashes[right]:
            return None
        return tuple(sorted((left, right)))
    base, rivals = set(), set()
    for row in source["candidate_manifest"]["pairs"]:
        _require(isinstance(row, dict) and "left" in row and "right" in row, "candidate_pair")
        pair = canonical(row["left"], row["right"])
        if pair:
            base.add(pair)
    _require(isinstance(source["unresolved_edges"], list), "rival_edges")
    for edge in source["unresolved_edges"]:
        _require(isinstance(edge, dict) and edge.get("document_id") in documents
            and isinstance(edge.get("source_document_ids"), list), "frozen_rival_members")
        members = edge["source_document_ids"]
        _require(members and len(members) == len(set(members))
            and all(member in documents for member in members)
            and edge.get("frozen_membership_revision") == digest(sorted(members)), "frozen_rival_revision")
        if "original_answer" in edge:
            _require(isinstance(edge["original_answer"], dict)
                and edge["original_answer"].get("membership_revision") == digest(sorted(members)), "original_rival_revision")
        for member in members:
            pair = canonical(edge["document_id"], member)
            if pair:
                rivals.add(pair)
    union = base | rivals
    pool = sorted(pair for pair in union if pair[0] not in membership or pair[1] not in membership
        or membership[pair[0]] != membership[pair[1]])
    return pool, {"base_retrieval_pairs": len(base), "uncertain_rival_pairs": len(rivals),
        "added_uncertain_rival_pairs": len(rivals - base), "deduplicated_union_pairs": len(union),
        "excluded_accepted_coassignments": len(union) - len(pool), "nonjoined_pairs": len(pool)}


def _sample(population, component, seed):
    selected = nested_srs_ranks(population, [LIMITS[component]], seed=seed, stratum=METHOD + ":" + component)
    size = len(selected["rank_order"])
    return {"population_size": population, "sample_size": size, "requested_size": LIMITS[component],
        "inclusion_numerator": size, "inclusion_denominator": population,
        "weight_numerator": population, "weight_denominator": size,
        "rank_order": selected["rank_order"], "empty_population": population == 0, "slots": []}


def _ranked_candidates(anchor, manifest, hashes):
    channels = manifest["neighbors"].get(anchor, {})
    scores = {}
    for channel in CHANNELS:
        for row in channels.get(channel, []):
            other = row["document_id"]
            if other != anchor and hashes[other] != hashes[anchor]:
                scores[other] = scores.get(other, Fraction()) + Fraction(1, 60 + row["rank"])
    order = sorted(scores, key=lambda identity: (-scores[identity], identity))[:20]
    return [(identity, scores[identity]) for identity in order], [c for c in CHANNELS if c not in channels]


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def _recall_bounds(tp, fn):
    return [_ratio(tp[0], tp[0] + fn[1]), _ratio(tp[1], tp[1] + fn[0])]


def build_design(source, seed):
    """Freeze SRSWOR slots, exact frame counts, RRF shortlists and execution dedup."""
    _require(isinstance(seed, str) and bool(seed), "seed")
    documents, groups, accepted, manifest, membership, hashes, alias_rows = _source(source)
    candidates, candidate_counts = _candidate_frame(source, documents, membership, hashes)
    # Rank the complete within-group pair universe without allocating its pairs.
    frames, prefix, total = [], [], 0
    for group in accepted:
        count = pair_count(len(groups[group]))
        if count:
            frames.append(groups[group])
            total += count
            prefix.append(total)
    singletons = sorted(groups[g][0] for g in accepted if len(groups[g]) == 1)
    samples = {name: _sample(size, name, seed) for name, size in
        (("precision", total), ("nonjoined", len(candidates)), ("singleton", len(singletons)))}
    tasks = {}
    def add_pair(left, right, slot_id):
        left, right = sorted((left, right))
        key = pair_key(left, right)
        task = tasks.setdefault(key, {"pair_key": key, "left": left, "right": right, "slot_ids": []})
        task["slot_ids"].append(slot_id)
        return key
    for component in ("precision", "nonjoined"):
        for rank in samples[component]["rank_order"]:
            if component == "precision":
                position = bisect_right(prefix, rank)
                members = frames[position]
                a, b = pair_from_rank(len(members), rank - (prefix[position - 1] if position else 0))
                left, right = members[a], members[b]
            else:
                left, right = candidates[rank]
            slot = digest({"method": METHOD, "seed": seed, "component": component, "rank": rank})
            key = add_pair(left, right, slot)
            samples[component]["slots"].append({"slot_id": slot, "rank": rank,
                "pair_key": key, "left": left, "right": right})
    for rank in samples["singleton"]["rank_order"]:
        anchor = singletons[rank]
        slot = digest({"method": METHOD, "seed": seed, "component": "singleton", "rank": rank})
        ranked, missing = _ranked_candidates(anchor, manifest, hashes)
        rows = []
        for order, (other, score) in enumerate(ranked, 1):
            child = digest({"anchor_slot": slot, "pair_key": pair_key(anchor, other)})
            key = add_pair(anchor, other, child)
            rows.append({"slot_id": child, "document_id": other, "pair_key": key, "rank": order,
                "rrf_numerator": score.numerator, "rrf_denominator": score.denominator})
        samples["singleton"]["slots"].append({"slot_id": slot, "rank": rank, "document_id": anchor,
            "candidates": rows, "candidate_count": len(rows), "missing_channels": missing,
            "search_status": "zero_candidates" if not rows else "shortlist_under_20" if len(rows) < 20 else "top_20"})
    for task in tasks.values():
        task["slot_ids"].sort()
    pair_slots = sum(len(samples[c]["slots"]) for c in ("precision", "nonjoined")) + sum(
        s["candidate_count"] for s in samples["singleton"]["slots"])
    _require(pair_slots <= 7600 and len(tasks) <= pair_slots, "pair_slot_limit")
    def hist(ids):
        return dict(sorted(Counter(str(len(groups[g])) for g in ids).items(), key=lambda p: int(p[0])))
    provisional = sorted(set(groups) - set(accepted))
    coverage = {"documents": len(documents), "source_records": alias_rows, "alias_records": alias_rows - len(documents),
        "all_groups": len(groups), "accepted_groups": len(accepted), "provisional_groups": len(provisional),
        "accepted_inputs": len(membership), "provisional_inputs": sum(len(groups[g]) for g in provisional),
        "ungrouped_inputs": len(documents) - sum(len(v) for v in groups.values()),
        "accepted_singletons": len(singletons), "group_size_histograms": {
            "all": hist(groups), "accepted": hist(accepted), "provisional": hist(provisional)}}
    tp = positive_total_bounds(total, samples["precision"]["sample_size"], samples["precision"]["sample_size"], tail_alpha=TAIL_ALPHA)
    fn = positive_total_bounds(len(candidates), samples["nonjoined"]["sample_size"], 0, tail_alpha=TAIL_ALPHA)
    best = _recall_bounds(tp, fn)[0]
    source_binding = {"documents": [{"document_id": i, "input_sha256": hashes[i],
        "article_row_ids": documents[i].get("article_row_ids", [i])} for i in sorted(documents)],
        "groups": groups, "accepted_group_ids": accepted, "candidate_manifest_sha256": digest(manifest),
        "unresolved_edges_sha256": digest(source["unresolved_edges"]), "provenance": source["provenance"],
        "counts": source["counts"]}
    result = {"method": METHOD, "seed": seed, "seed_sha256": digest(seed), "source_binding_sha256": digest(source_binding),
        "provenance": source["provenance"], "source_counts": source["counts"], "coverage": coverage,
        "frames": {**candidate_counts, "coassigned_pairs": total, "accepted_singleton_anchors": len(singletons),
            "all_possible_pairs": pair_count(len(documents)),
            "excluded_never_retrieved_nonjoined_pairs": pair_count(len(documents)) - total - len(candidates)},
        "samples": samples, "pair_tasks": [tasks[k] for k in sorted(tasks)], "pair_slots_before_dedup": pair_slots,
        "unique_pair_tasks": len(tasks), "rng": {"algorithm": "python.random.Random.sample(range)", "python": platform.python_version()},
        "inference": {"family_alpha": .05, "count_intervals": 3, "tails": 2, "looks": 1, "tail_alpha": TAIL_ALPHA,
            "reference": "dependent Luna model judgments", "recall_scope": "accepted coassigned plus frozen nonjoined candidate pairs",
            "singleton_scope": "frozen RRF top20; empty lists unknown", "global_recall_claimed": False},
        "preflight": {"best_case_tp_count_bounds": list(tp), "best_case_fn_count_bounds": list(fn),
            "best_case_recall_lower_bound": best, "recall_90_certification_possible": best is not None and best >= .9,
            "sample_expansion_authorized": False}}
    return {**result, "design_sha256": digest(result)}


def _cell(population, labels):
    counts = Counter(labels)
    n, positives, unknown = len(labels), counts["same_event"], counts["unknown"]
    bounds = positive_total_bounds(population, n, positives, unresolved=unknown, tail_alpha=TAIL_ALPHA)
    estimated = [_ratio(population * positives, n), _ratio(population * (positives + unknown), n)] if population else [0.0, 0.0]
    return {"population_size": population, "selected": n, "positive": positives, "negative": counts["negative"],
        "unknown": unknown, "resolved": n - unknown, "positive_total_bounds": list(bounds),
        "ht_positive_total_range": estimated, "ht_positive_total": estimated[0] if unknown == 0 else None}


def _target(bounds, target):
    lower, upper = bounds
    return "supported" if lower is not None and lower >= target else "below_target" if upper is not None and upper < target else "inconclusive"


def compute_report(design, pair_labels):
    """One final design-based analysis; missing selected judgments stay unknown."""
    _require(isinstance(design, dict) and design.get("method") == METHOD
        and design.get("design_sha256") == digest({k: v for k, v in design.items() if k != "design_sha256"}), "design_binding")
    _require(isinstance(pair_labels, dict) and all(isinstance(v, str) and v in LABELS for v in pair_labels.values()), "pair_labels")
    task_keys = {task["pair_key"] for task in design["pair_tasks"]}
    _require(set(pair_labels) <= task_keys, "foreign_pair_labels")
    def label(key):
        return pair_labels.get(key, "unknown")
    cells = {}
    for component in ("precision", "nonjoined"):
        sample = design["samples"][component]
        cells[component] = _cell(sample["population_size"], [label(row["pair_key"]) for row in sample["slots"]])
    outcomes = []
    for slot in design["samples"]["singleton"]["slots"]:
        values = [label(row["pair_key"]) for row in slot["candidates"]]
        outcome = "same_event" if "same_event" in values else "negative" if values and all(v == "negative" for v in values) else "unknown"
        outcomes.append({"slot_id": slot["slot_id"], "document_id": slot["document_id"], "label": outcome,
            "outcome": "detected_missed_match" if outcome == "same_event" else "no_match_in_shortlist" if outcome == "negative" else "unknown",
            "candidate_count": len(values), "search_status": slot["search_status"], "missing_channels": slot["missing_channels"]})
    cells["singleton"] = _cell(design["samples"]["singleton"]["population_size"], [r["label"] for r in outcomes])
    p, c, s = (cells[k] for k in ("precision", "nonjoined", "singleton"))
    precision_bounds = [_ratio(x, p["population_size"]) for x in p["positive_total_bounds"]]
    recall_bounds = _recall_bounds(p["positive_total_bounds"], c["positive_total_bounds"])
    recall_range = _recall_bounds(p["ht_positive_total_range"], c["ht_positive_total_range"])
    point = _ratio(p["ht_positive_total"], p["ht_positive_total"] + c["ht_positive_total"]) if p["ht_positive_total"] is not None and c["ht_positive_total"] is not None else None
    totals = {"TP": p["ht_positive_total_range"], "FN": c["ht_positive_total_range"],
        "FP": [p["population_size"] - x for x in reversed(p["ht_positive_total_range"])],
        "TN": [c["population_size"] - x for x in reversed(c["ht_positive_total_range"])]}
    return {"method": METHOD, "design_sha256": design["design_sha256"], "reference": "dependent Luna model judgments",
        "cells": cells, "weighted_total_ranges": totals,
        "precision": {"estimate": _ratio(p["ht_positive_total"], p["population_size"]) if p["ht_positive_total"] is not None else None,
            "estimate_range": [_ratio(x, p["population_size"]) for x in p["ht_positive_total_range"]],
            "bounds": precision_bounds, "target": .95, "target_status": _target(precision_bounds, .95)},
        "candidate_recall": {"estimate": point, "estimate_range": recall_range, "bounds": recall_bounds,
            "target": .9, "target_status": _target(recall_bounds, .9), "unbiased_ratio_estimator": False,
            "zero_true_match_total_possible": p["positive_total_bounds"][0] + c["positive_total_bounds"][0] == 0},
        "singleton_missed_match_rate": {"estimate": _ratio(s["ht_positive_total"], s["population_size"]) if s["ht_positive_total"] is not None else None,
            "estimate_range": [_ratio(x, s["population_size"]) for x in s["ht_positive_total_range"]],
            "bounds": [_ratio(x, s["population_size"]) for x in s["positive_total_bounds"]],
            "zero_candidates": sum(r["candidate_count"] == 0 for r in outcomes),
            "short_nonempty_lists": sum(0 < r["candidate_count"] < 20 for r in outcomes),
            "full_20_lists": sum(r["candidate_count"] == 20 for r in outcomes), "outcomes": outcomes},
        "unique_pair_outcomes": dict(Counter(label(key) for key in sorted(task_keys))),
        "coverage": design["coverage"], "frames": design["frames"], "preflight": design["preflight"],
        "inference": design["inference"], "actual_attempt_counts_available": False,
        "human_truth_claimed": False, "global_recall_claimed": False, "group_coherence_claimed": False}
