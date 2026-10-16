"""Pure event-group comparisons; callers audit real data through Research.execute."""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from itertools import combinations
from statistics import mean, median
from typing import Any

from .event_group_refinement import refine
from .event_pair_monotone import predicts
from .event_rule_application import complete_link_groups, publication_coverage

Json = dict[str, Any]


def _dates(ids: Sequence[str], metadata: Json) -> Json:
    coverage = publication_coverage(ids, {item: metadata.get(item, {}).get("published_at") for item in ids})
    if coverage["missing_date_ids"]:
        raise ValueError("group comparisons require usable UTC-calendar publication dates for every eligible article")
    return coverage["valid_dates"]


def _p90(values: list[int]) -> int | None:
    return sorted(values)[math.ceil(.9 * len(values)) - 1] if values else None


def stats(groups: Sequence[Json], metadata: Json) -> Json:
    """Exact descriptive graph statistics; sizes do not establish event accuracy."""
    ids = [item for group in groups for item in group["members"]]
    dates = _dates(ids, metadata)
    sizes = [len(group["members"]) for group in groups if len(group["members"]) > 1]
    spans = [(max(dates[item] for item in group["members"])
              - min(dates[item] for item in group["members"])).days
             for group in groups if len(group["members"]) > 1]
    histogram = dict.fromkeys(("2", "3-5", "6-10", "11-20", "21+"), 0)
    for size in sizes:
        key = "2" if size == 2 else "3-5" if size <= 5 else "6-10" if size <= 10 else "11-20" if size <= 20 else "21+"
        histogram[key] += 1
    return {"groups": len(groups), "multi_article_groups": len(sizes),
            "grouped_articles": sum(sizes), "singletons": len(groups) - len(sizes),
            "size_histogram": histogram,
            "multi_article_size": {"mean": mean(sizes) if sizes else None,
                                   "median": median(sizes) if sizes else None,
                                   "p90": _p90(sizes), "maximum": max(sizes) if sizes else None},
            "all_internal_pair_count": sum(size * (size - 1) // 2 for size in sizes),
            "publication_spans": {"median_days": median(spans) if spans else None,
                                  "p90_days": _p90(spans), "maximum_days": max(spans) if spans else None,
                                  "beyond_7_days": sum(span > 7 for span in spans),
                                  "beyond_30_days": sum(span > 30 for span in spans),
                                  "beyond_90_days": sum(span > 90 for span in spans)},
            "p90_method": "nearest rank ceil(0.9*n); multi-article groups only"}


def build(ids: list[str], scored: list[Json], metadata: Json, rule: Json, cap: int | None) -> Json:
    """Partition the same eligible articles with a frozen feature rule/date cap."""
    if isinstance(cap, bool) or (cap is not None and (not isinstance(cap, int) or cap < 0)):
        raise ValueError("date cap must be None or a nonnegative integer")
    dates = _dates(ids, metadata)
    known = set(ids)
    no_date_rule = {**rule, "publication_gap_days": None}
    passing: list[Json] = []
    excluded: Counter[str] = Counter()
    for row in scored:
        left, right = row.get("left"), row.get("right")
        if left not in known or right not in known:
            excluded["outside_eligible_articles"] += 1
            continue
        if row.get("status") != "completed":
            excluded["incomplete_processing"] += 1
            continue
        if not predicts(row, no_date_rule):
            excluded["failed_or_missing_feature_condition"] += 1
            continue
        gap = abs((dates[left] - dates[right]).days)
        if cap is not None and gap > cap:
            excluded["outside_publication_cap"] += 1
            continue
        passing.append({**row, "publication_gap_days": gap})
    initial = complete_link_groups(sorted(ids), passing)
    body_ids = {item: metadata.get(item, {}).get("body_sha256") for item in ids}
    refined = refine(ids, passing, initial["groups"], no_date_rule, body_ids)
    memberships = [item for group in refined["groups"] for item in group["members"]]
    if sorted(memberships) != sorted(ids):
        raise ValueError("refined groups changed article coverage")
    pairs = {tuple(sorted((row["left"], row["right"]))) for row in passing}
    for group in refined["groups"]:
        members = group["members"]
        if any(tuple(pair) not in pairs for pair in combinations(sorted(members), 2)):
            raise ValueError("refined group contains an unscored or nonpassing pair")
        if cap is not None and (max(dates[item] for item in members) - min(dates[item] for item in members)).days > cap:
            raise ValueError("refined group exceeds the publication cap")
    return {"groups": refined["groups"], "bridges": refined["bridges"], "moves": refined["moves"],
            "diagnostics": {**refined["diagnostics"], "publication_cap_days": cap,
                            "input_scored_rows": len(scored), "excluded_rows": dict(sorted(excluded.items())),
                            "coverage_and_cliques_verified": True},
            "initial_counts": initial["counts"], "counts": refined["counts"],
            "statistics": stats(refined["groups"], metadata),
            "passing_pair_ids": sorted(row["pair_id"] for row in passing)}


def lineage(before: Sequence[Json], after: Sequence[Json]) -> Json:
    """Exact partition intersections and pair changes, without enumerating all pairs."""
    def partition(groups: Sequence[Json]) -> tuple[dict[str, str], dict[str, frozenset[str]]]:
        owner: dict[str, str] = {}
        members: dict[str, frozenset[str]] = {}
        for group in groups:
            key = group["group_id"]
            items = group["members"]
            if key in members or not items or len(set(items)) != len(items) or any(item in owner for item in items):
                raise ValueError("lineage requires partitions with unique nonempty groups")
            members[key] = frozenset(items)
            owner.update(dict.fromkeys(items, key))
        return owner, members

    old_owner, old_members = partition(before)
    new_owner, new_members = partition(after)
    if set(old_owner) != set(new_owner):
        raise ValueError("lineage partitions must cover the same articles")
    shared: dict[tuple[str, str], list[str]] = defaultdict(list)
    for item in sorted(old_owner):
        shared[old_owner[item], new_owner[item]].append(item)
    children = Counter(old for old, _ in shared)
    parents = Counter(new for _, new in shared)
    relations = []
    for (old, new), items in sorted(shared.items()):
        kind = ("unchanged" if old_members[old] == new_members[new] else
                "rearrangement" if children[old] > 1 and parents[new] > 1 else
                "split" if children[old] > 1 else "merge")
        relations.append({"before_group_id": old, "after_group_id": new,
                          "relation": kind, "shared_members": items})
    retained = sum(len(items) * (len(items) - 1) // 2 for items in shared.values())
    old_pairs = sum(len(items) * (len(items) - 1) // 2 for items in old_members.values())
    new_pairs = sum(len(items) * (len(items) - 1) // 2 for items in new_members.values())
    changed = [item for item in sorted(old_owner)
               if old_members[old_owner[item]] != new_members[new_owner[item]]]
    return {"relations": relations, "unchanged_groups": sum(row["relation"] == "unchanged" for row in relations),
            "split_old_groups": sum(count > 1 for count in children.values()),
            "merged_new_groups": sum(count > 1 for count in parents.values()),
            "membership_changed_articles": len(changed), "membership_changed_article_ids": changed,
            "retained_copairs": retained, "gained_copairs": new_pairs - retained,
            "lost_copairs": old_pairs - retained}
