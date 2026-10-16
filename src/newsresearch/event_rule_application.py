"""Label-blind numeric helpers; research callers must enter Research.execute."""
from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterator, Mapping, Sequence
import math
from typing import Any

import numpy as np

from .common import ResearchError, digest
from .event_pair_features import _publication_date

METHOD = "all-article-date-pooled-prefilter-complete-link-v1"


def _ids(ids: Sequence[str]) -> list[str]:
    result = list(ids)
    if (len(result) > 20000 or len(set(result)) != len(result)
            or any(not isinstance(value, str) or not value.strip() for value in result)):
        raise ResearchError("Application requires at most 20000 unique nonempty article IDs")
    return result


def publication_coverage(ids: Sequence[str], published: Mapping[str, Any]) -> dict[str, Any]:
    dates, statuses = {}, {}
    missing = []
    for source in _ids(ids):
        value, status = _publication_date(published.get(source))
        statuses[source] = status
        if value is None:
            missing.append(source)
        else:
            dates[source] = value
    return {"valid_dates": dates, "missing_date_ids": sorted(missing), "date_status": statuses}


def candidate_batches(values: Any, ids: Sequence[str], published: Mapping[str, Any],
                      rule: Mapping[str, Any], block_size: int = 128
                      ) -> Iterator[tuple[list[dict[str, Any]], dict[str, int]]]:
    """Visit every date-eligible unordered pair, yielding at most 200 candidates.

    Block products only prefilter; final scores use the original float64 scalar
    cosine/distance formula. The 1e-10 margin never changes the applied cutoff.
    Publication dates are metadata, not event dates. Duplicate vectors retain
    separate article identities and publication dates.
    """
    sources = _ids(ids)
    original = np.asarray(values)
    matrix = np.asarray(original, dtype=np.float64)
    if (matrix.ndim != 2 or matrix.shape[0] != len(sources)
            or not 1 <= matrix.shape[1] <= 8192 or not np.isfinite(matrix).all()):
        raise ResearchError("Pooled vectors require finite numeric rows and 1..8192 dimensions")
    norms = np.sqrt(np.einsum("ij,ij->i", original, original, dtype=np.float64))
    if not np.all(np.abs(norms - 1.) <= 1e-4):
        raise ResearchError("Pooled article vectors must have unit norm")
    if isinstance(block_size, bool) or not isinstance(block_size, int) or not 1 <= block_size <= 128:
        raise ResearchError("Candidate blocks must contain 1..128 query rows")
    try:
        cut = float(rule["thresholds"][0])
        gate = rule["publication_gap_days"]
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise ResearchError("Application requires the original pooled cutoff and publication gate") from exc
    if (not math.isfinite(cut) or not -1 <= cut <= 1 or isinstance(gate, bool)
            or not isinstance(gate, int) or gate < 0):
        raise ResearchError("A finite cosine cutoff and nonnegative integer date gate are required")
    coverage = publication_coverage(sources, published)
    dates = coverage["valid_dates"]
    order = sorted((index for index, source in enumerate(sources) if source in dates),
                   key=lambda index: (dates[sources[index]], sources[index]))
    days = [dates[sources[index]].toordinal() for index in order]
    for block, start in enumerate(range(0, len(order), block_size)):
        stop = min(start + block_size, len(order))
        end = bisect_right(days, days[stop - 1] + gate)
        queries = np.asarray(order[start:stop], dtype=np.int64)
        targets = np.asarray(order[start + 1:end], dtype=np.int64)
        scores = (matrix[queries] @ matrix[targets].T) / (norms[queries, None] * norms[targets])
        eligible = ((np.arange(start + 1, end)[None, :] > np.arange(start, stop)[:, None])
                    & (np.asarray(days[start + 1:end])[None, :]
                       - np.asarray(days[start:stop])[:, None] <= gate))
        possible = np.argwhere(eligible & (scores >= cut - 1e-10))
        stats = {"block_index": block, "query_rows": stop - start,
                 "checked_date_pairs": int(eligible.sum()), "emitted_pairs": 0}
        rows: list[dict[str, Any]] = []
        first = True
        for a, b in possible:
            left_index, right_index = int(queries[a]), int(targets[b])
            cosine = float(np.dot(matrix[left_index], matrix[right_index])
                           / (norms[left_index] * norms[right_index]))
            distance = float(np.clip(1. - cosine, 0., 2.))
            if 1. - distance < cut:
                continue
            left, right = sorted((sources[left_index], sources[right_index]))
            rows.append({"pair_id": digest([left, right]), "left": left, "right": right,
                         "distance": distance, "fold": "application", "origin": ["all_eligible_pairs"]})
            if len(rows) == 200:
                yield rows, {**stats, "emitted_pairs": len(rows)} if first else {
                    "block_index": block, "query_rows": 0, "checked_date_pairs": 0, "emitted_pairs": len(rows)}
                first, rows = False, []
        if rows or first:
            yield rows, {**stats, "emitted_pairs": len(rows)} if first else {
                "block_index": block, "query_rows": 0, "checked_date_pairs": 0, "emitted_pairs": len(rows)}


def complete_link_groups(ids: Sequence[str], edges: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic clique partition, retaining every unmerged passing bridge.

    Every supplied edge must already pass the entire registered rule. Absence
    of an edge blocks a merge; it never asserts different real-world events.
    """
    sources = _ids(ids)
    known = set(sources)
    passing: dict[tuple[str, str], dict[str, Any]] = {}
    scores = {}
    seen = set()
    for edge in edges:
        left, right = edge.get("left"), edge.get("right")
        if left not in known or right not in known or left == right:
            raise ResearchError("Passing edges require distinct known article IDs")
        pair = tuple(sorted((left, right)))
        pair_id = edge.get("pair_id")
        value = edge.get("features", {}).get("pooled_cosine", edge.get("pooled_cosine"))
        if (pair in passing or not isinstance(pair_id, str) or not pair_id or pair_id in seen
                or isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -1 <= value <= 1
                or edge.get("status", "completed") != "completed"):
            raise ResearchError("Passing edges must have unique identities and finite completed pooled scores")
        passing[pair], scores[pair] = dict(edge), float(value)
        seen.add(pair_id)
    owner = {source: source for source in sources}
    members = {source: {source} for source in sources}
    for pair in sorted(passing, key=lambda key: (-scores[key], passing[key]["pair_id"])):
        a, b = owner[pair[0]], owner[pair[1]]
        if a == b:
            continue
        if all(tuple(sorted((left, right))) in passing for left in members[a] for right in members[b]):
            keep, drop = sorted((a, b))
            for source in members[drop]:
                owner[source] = keep
            members[keep].update(members.pop(drop))
    groups = [{"group_id": digest({"method": METHOD, "members": sorted(group)}), "members": sorted(group)}
              for group in sorted(members.values(), key=lambda value: (-len(value), sorted(value)))]
    bridges = [passing[pair] for pair in sorted(passing) if owner[pair[0]] != owner[pair[1]]]
    return {"groups": groups, "bridges": bridges, "counts": {"groups": len(groups),
        "multi_article_groups": sum(len(group["members"]) > 1 for group in groups),
        "singletons": sum(len(group["members"]) == 1 for group in groups),
        "passing_edges": len(passing), "bridge_edges": len(bridges)}}
