"""Pure temporal sensitivity summaries, called only by audited research adapters."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from statistics import median
from typing import Any

from .common import ResearchError
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES, _feature
from .event_temporal import BANDS, CAPS, pair_band

Json = dict[str, Any]


def _spans(groups: list[Json], dates: dict[str, date]) -> Json:
    rows = []
    for group in groups:
        members = group["members"]
        if len(members) < 2:
            continue
        observed = [dates[source] for source in members if source in dates]
        span = (max(observed) - min(observed)).days if len(observed) >= 2 else None
        rows.append({"group_id": group["group_id"], "articles": len(members),
                     "dated_articles": len(observed), "missing_dates": len(members) - len(observed),
                     "span_days": span, "complete_dates": len(observed) == len(members)})
    spans = sorted(row["span_days"] for row in rows if row["span_days"] is not None)
    return {"multi_article_groups": len(rows), "groups_with_two_or_more_dates": len(spans),
            "complete_date_groups": sum(row["complete_dates"] for row in rows),
            "min_days": min(spans) if spans else None, "median_days": median(spans) if spans else None,
            "p90_days": spans[math.ceil(.9 * len(spans)) - 1] if spans else None,
            "max_days": max(spans) if spans else None,
            "groups_beyond_7_days": sum(value > 7 for value in spans),
            "quantiles": "median averages middle values; p90 is nearest rank; observed dates only",
            "rows": sorted(rows, key=lambda row: row["group_id"])}


def summarize(scored: list[Json], rule: Json, dates: dict[str, date], metadata: dict[str, Json],
              groups: list[Json], provider_ids: dict[str, str | None]) -> Json:
    """Compare date caps on one fixed cosine rule without changing partitions.

    Unknown dates remain a separate band, including under the uncapped dated
    cohort. Provider event identifiers are exact-string metadata aids, not gold.
    Examples maximize minimum normalized feature margin, then pooled cosine,
    then ascending stable pair ID; this is numerical ranking, not article judging.
    """
    no_date_rule = {**rule, "publication_gap_days": None}
    owners: dict[str, str] = {}
    sizes: dict[str, int] = {}
    for group in groups:
        identity, members = group["group_id"], group["members"]
        if identity in sizes or not members or len(set(members)) != len(members):
            raise ResearchError("Temporal summary requires unique nonempty groups")
        sizes[identity] = len(members)
        for source in members:
            if source in owners:
                raise ResearchError("Temporal summary groups must partition sources")
            owners[source] = identity
    bands = {name: {"pooled_candidates": 0, "completed": 0, "failed": 0,
                    "cosine_passing": 0} for name in BANDS}
    passing: list[Json] = []
    long_rows: list[Json] = []
    examples: dict[str, tuple[tuple[float, float, str], Json]] = {}
    seen: set[str] = set()
    for row in scored:
        pair_id, left, right = row["pair_id"], row["left"], row["right"]
        if pair_id in seen or left == right or left not in metadata or right not in metadata:
            raise ResearchError("Temporal summary requires distinct valid source pairs")
        seen.add(pair_id)
        gap = abs((dates[left] - dates[right]).days) if left in dates and right in dates else None
        band = pair_band(gap)
        summary = bands[band]
        summary["pooled_candidates"] += 1
        complete = row.get("status") == "completed" and all(_feature(row, name) is not None for name in FEATURES)
        summary["completed" if complete else "failed"] += 1
        if not complete or not predicts(row, no_date_rule):
            continue
        summary["cosine_passing"] += 1
        a, b = owners.get(left), owners.get(right)
        cross = "unknown_assignment" if a is None or b is None else (
            "within_group" if a == b else "singleton_singleton" if sizes[a] == sizes[b] == 1 else
            "singleton_group" if min(sizes[a], sizes[b]) == 1 else "group_group")
        uri_a, uri_b = provider_ids.get(left), provider_ids.get(right)
        populated = all(isinstance(value, str) and bool(value.strip()) for value in (uri_a, uri_b))
        provider = "same" if populated and uri_a == uri_b else "different" if populated else "unavailable"
        margin = min((float(row["features"][name]) - cut) / max(1. - cut, 1e-15)
                     for name, cut in zip(FEATURES, rule["thresholds"], strict=True))
        value = {"pair_id": pair_id, "left": left, "right": right, "publication_gap_days": gap,
                 "band": band, "features": row["features"], "cross_group_type": cross,
                 "provider_equality": provider, "minimum_normalized_margin": margin,
                 "articles": [{"source": source, "title": metadata[source].get("title"),
                               "url": metadata[source].get("url"),
                               "published_at": metadata[source].get("published_at")} for source in (left, right)]}
        passing.append(value)
        if gap is not None and gap > 7:
            long_rows.append(value)
            key = (-margin, -row["features"]["pooled_cosine"], pair_id)
            if band not in examples or key < examples[band][0]:
                examples[band] = (key, value)
    cap_rows = []
    cross_types = ("singleton_singleton", "singleton_group", "group_group", "unknown_assignment")
    for cap in CAPS:
        eligible = [row for row in passing if row["publication_gap_days"] is not None
                    and (cap is None or row["publication_gap_days"] <= cap)]
        cap_rows.append({"cap_days": cap, "dated_passing_pairs": len(eligible),
                         "distinct_articles": len({source for row in eligible for source in (row["left"], row["right"])}),
                         "long_passing_cross_group": {kind: sum(row["publication_gap_days"] > 7
                             and row["cross_group_type"] == kind for row in eligible) for kind in cross_types}})
    providers: dict[str, list[str]] = defaultdict(list)
    for source in sorted(metadata):
        uri = provider_ids.get(source)
        if isinstance(uri, str) and uri.strip():
            providers[uri].append(source)
    provider_groups = [{"group_id": uri, "members": members} for uri, members in sorted(providers.items())]
    provider_spans = _spans(provider_groups, dates)
    provider_spans.update({"corpus_articles": len(metadata), "articles_with_provider_id": sum(map(len, providers.values())),
                           "distinct_populated_provider_ids": len(providers),
                           "interpretation": "Exact populated provider identifiers are not validated event identity."})
    return {"bands": [{"band": name, **bands[name]} for name in BANDS], "caps": cap_rows,
            "unknown_gap_cosine_passing_pairs": bands["unknown"]["cosine_passing"],
            "current_group_spans": _spans(groups, dates), "provider_group_spans": provider_spans,
            "long_passing_pairs": sorted(long_rows, key=lambda row: row["pair_id"]),
            "examples": [examples[name][1] for name in BANDS if name in examples],
            "new_partitions": False, "semantic_validation": False}
