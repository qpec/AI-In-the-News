"""Pure bounded review preparation, never event acceptance or group merging.

Real research callers must register this method and enter Research.execute.
Saved similarities nominate candidates; no source bodies are read here. Every
selected union requires every article pair, including pairs within old groups.
"""
from __future__ import annotations

import math
from collections import Counter
from itertools import combinations, product
from typing import Any
from urllib.parse import urlsplit

from .common import digest
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES
from .event_rule_application import publication_coverage

Json = dict[str, Any]
METHOD = "all-pair-union-cross-window-review-preparation-v1"


def _features(row: Json) -> dict[str, float] | None:
    values = row.get("features")
    if not isinstance(values, dict):
        return None
    result = {}
    for name in FEATURES:
        value = values.get(name)
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -1 <= value <= 1):
            return None
        result[name] = float(value)
    return result


def _domain(value: Any) -> str | None:
    try:
        parsed = urlsplit(value) if isinstance(value, str) else None
        if parsed is None or parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        return parsed.hostname.removeprefix("www.")
    except ValueError:
        return None


def prepare(groups: list[Json], scored: list[Json], metadata: Json, rule: Json, *,
            max_candidates: int = 10, max_tasks: int = 36, max_union: int = 6,
            review_source_ids: set[str] | None = None) -> Json:
    """Nominate disjoint group-pair review packets under an atomic task budget."""
    for bound, limit in ((max_candidates, 10), (max_tasks, 36), (max_union, 6)):
        if isinstance(bound, bool) or not isinstance(bound, int) or not 0 <= bound <= limit:
            raise ValueError("review bounds exceed the frozen 10-candidate/36-task/6-article policy")
    no_date_rule = {**rule, "publication_gap_days": None}
    predicts({"features": dict.fromkeys(FEATURES, 1.)}, no_date_rule)
    cuts = no_date_rule["thresholds"]
    if any(cut >= 1 for cut in cuts):
        raise ValueError("normalized margins require thresholds below one")
    by_group: dict[str, Json] = {}
    owners: dict[str, str] = {}
    for group in groups:
        group_id, members = group.get("group_id"), group.get("members")
        if (not isinstance(group_id, str) or not group_id or group_id in by_group
                or not isinstance(members, list) or not members or len(set(members)) != len(members)):
            raise ValueError("groups need unique identities and nonempty unique article members")
        for item in members:
            if not isinstance(item, str) or not item or item in owners:
                raise ValueError("groups must partition unique nonempty article IDs")
            owners[item] = group_id
        by_group[group_id] = {"group_id": group_id, "members": sorted(members)}
    coverage = publication_coverage(sorted(owners), {
        item: metadata.get(item, {}).get("published_at") for item in owners})
    if coverage["missing_date_ids"]:
        raise ValueError("candidate group members require usable publication dates")
    dates = coverage["valid_dates"]
    lookup: dict[tuple[str, str], Json] = {}
    frame: dict[tuple[str, str], list[str]] = {}
    outside = 0
    for row in scored:
        a, b = row.get("left"), row.get("right")
        if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
            raise ValueError("scored pair endpoints must be distinct nonempty article IDs")
        pair = (min(a, b), max(a, b))
        if pair in lookup or row.get("pair_id") != digest(list(pair)):
            raise ValueError("duplicate, conflicting or noncanonical scored pair identity")
        lookup[pair] = row
        if a not in owners or b not in owners:
            outside += 1
            continue
        if (owners[a] != owners[b] and row.get("status") == "completed"
                and _features(row) is not None and predicts(row, no_date_rule)):
            group_pair = (min(owners[a], owners[b]), max(owners[a], owners[b]))
            frame.setdefault(group_pair, []).append(row["pair_id"])

    candidates: list[Json] = []
    for group_pair in sorted(frame):
        first, second = (by_group[key]["members"] for key in group_pair)
        union = sorted(first + second)
        span = (max(dates[item] for item in union) - min(dates[item] for item in union)).days
        candidate_id = digest({"method": METHOD, "group_ids": list(group_pair), "members": union})
        type_name = ("both_multi" if len(first) > 1 and len(second) > 1
                     else "both_singletons" if len(first) == len(second) == 1 else "mixed")
        row = {"candidate_id": candidate_id, "old_group_ids": list(group_pair), "article_members": union,
               "group_sizes": [len(first), len(second)], "candidate_type": type_name,
               "publication_span_days": span, "inducing_pair_ids": sorted(frame[group_pair]),
               "in_frame": span > 7, "qualified": False, "semantic_review_status": "unjudged",
               "accepted": False, "all_union_pairs_required": True, "representative_only": False,
               "required_union_pair_count": len(union) * (len(union) - 1) // 2}
        if span <= 7:
            candidates.append({**row, "status": "same_window_excluded", "reasons": ["publication_span_not_over_7"]})
            continue
        counts: Counter[str] = Counter()
        weakest: dict[str, float | None] = dict.fromkeys(FEATURES)
        for a, b in product(first, second):
            score = lookup.get(tuple(sorted((a, b))))
            if score is None:
                counts["missing_row"] += 1
                continue
            processing = score.get("status")
            if processing != "completed":
                counts[processing if processing in {"failed", "pending", "unknown"} else "invalid_status"] += 1
                continue
            values = _features(score)
            if values is None:
                counts["invalid_or_missing_features"] += 1
                continue
            counts["completed_finite"] += 1
            for name, value in values.items():
                previous = weakest[name]
                weakest[name] = value if previous is None else min(previous, value)
            counts["passing" if predicts(score, no_date_rule) else "below_cutoff"] += 1
        reasons = [key for key in sorted(counts) if key not in {"completed_finite", "passing"} and counts[key]]
        qualified = counts["passing"] == len(first) * len(second)
        domains = sorted({domain for item in union if (domain := _domain(metadata.get(item, {}).get("url")))})
        bodies = sorted({value for item in union
                         if isinstance(value := metadata.get(item, {}).get("body_sha256"), str) and value})
        margin = min((value - cut) / (1 - cut) for value, cut in zip(weakest.values(), cuts, strict=True)
                     if value is not None) if counts["completed_finite"] else None
        status = "cross_evidence_requires_review"
        if qualified:
            if review_source_ids is not None and not set(union) <= review_source_ids:
                status = "heldout_or_unmapped_excluded"
                reasons.append("preserve_original_sealed_body_fold")
            elif len(domains) < 2 or len(bodies) < 2:
                status = "diversity_excluded"
                reasons.extend(name for name, count in (("distinct_domains", len(domains)),
                                                       ("distinct_body_families", len(bodies))) if count < 2)
            elif len(union) > max_union:
                status = "union_size_excluded"
                reasons.append("union_exceeds_review_size_bound")
            else:
                status = "eligible_for_review"
        candidates.append({**row, "qualified": qualified, "status": status, "reasons": reasons,
                           "expected_cross_pair_count": len(first) * len(second),
                           "completed_cross_pair_count": counts["completed_finite"],
                           "cross_pair_counts": dict(sorted(counts.items())), "weakest_cross_features": weakest,
                           "weakest_normalized_margin": margin,
                           "margin_scope": "available completed finite cross pairs; complete only when qualified",
                           "distinct_domains": domains, "distinct_body_families": bodies})

    eligible = sorted((row for row in candidates if row["status"] == "eligible_for_review"),
                      key=lambda row: (row["candidate_type"] == "both_singletons", len(row["article_members"]),
                                       -row["weakest_normalized_margin"], row["old_group_ids"]))
    selected: list[Json] = []
    task_map: dict[tuple[str, str], Json] = {}
    used_groups: set[str] = set()
    for row in eligible:
        pairs = list(combinations(row["article_members"], 2))
        additional = sum(pair not in task_map for pair in pairs)
        if any(key in used_groups for key in row["old_group_ids"]):
            row["status"] = "old_group_already_selected"
        elif len(selected) >= max_candidates:
            row["status"] = "candidate_budget_excluded"
        elif len(task_map) + additional > max_tasks:
            row["status"] = "atomic_task_budget_excluded"
        else:
            row["status"] = "selected_for_review"
            used_groups.update(row["old_group_ids"])
            for pair in pairs:
                task = task_map.setdefault(pair, {"pair_id": digest(list(pair)), "left": pair[0], "right": pair[1],
                                                  "candidate_ids": [], "status": "pending_review"})
                task["candidate_ids"].append(row["candidate_id"])
            selected.append({"candidate_id": row["candidate_id"], "old_group_ids": row["old_group_ids"],
                             "article_members": row["article_members"], "candidate_type": row["candidate_type"],
                             "group_sizes": row["group_sizes"],
                             "publication_span_days": row["publication_span_days"],
                             "pair_task_ids": [digest(list(pair)) for pair in pairs],
                             "all_union_pairs_required": True, "representative_only": False,
                             "articles": [{"source_id": item, **{key: metadata.get(item, {}).get(key)
                                           for key in ("title", "url", "published_at", "body_sha256")}}
                                          for item in row["article_members"]],
                             "semantic_review_status": "unjudged", "accepted": False})
    statuses = Counter(row["status"] for row in candidates)
    spans = Counter("8-30" if row["publication_span_days"] <= 30 else "31-90"
                    if row["publication_span_days"] <= 90 else ">90" for row in selected)
    return {"candidates": candidates, "selected": selected, "tasks": [task_map[pair] for pair in sorted(task_map)],
            "diagnostics": {"method": METHOD, "current_groups": len(groups),
                            "current_singletons": sum(len(group["members"]) == 1 for group in groups),
                            "induced_group_pairs": len(frame), "frame_pairs": sum(row["in_frame"] for row in candidates),
                            "same_window_excluded": statuses["same_window_excluded"],
                            "qualified_pairs": sum(row["qualified"] for row in candidates),
                            "candidate_status_counts": dict(sorted(statuses.items())), "selected_candidates": len(selected),
                            "unique_pair_tasks": len(task_map), "outside_group_scored_rows": outside,
                            "selected_span_bins": {key: spans[key] for key in ("8-30", "31-90", ">90")},
                            "selected_types": dict(sorted(Counter(row["candidate_type"] for row in selected).items())),
                            "selection_order": "at least one multi-article group first; smaller union; stronger weakest margin; stable group IDs",
                            "selection_bias": "bounded size/type/score-prioritized exploratory queue, not a representative sample",
                            "old_group_reuse_limit": 1, "maximum_candidates": max_candidates,
                            "maximum_pair_tasks": max_tasks, "maximum_union_articles": max_union,
                            "current_memberships_changed": 0, "accepted_dossiers": 0,
                            "missing_edge_interpretation": "unavailable evidence, never a different-event finding"}}
