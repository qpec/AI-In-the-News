"""Pure, date-free numeric diagnostics; research callers use Research.execute.

No source reading, article judging, group acceptance or model calls occur here.
Publication gaps are reporting metadata, never inferred event dates.
"""
from __future__ import annotations

from collections.abc import Iterator, Sequence
import math
from typing import Any

import numpy as np

from .common import ResearchError, digest

BANDS = ("0-7", "8-14", "15-30", "31-90", ">90", "unknown")
CAPS = (7, 14, 30, 90, None)


def pair_band(gap: Any) -> str:
    """Classify a validated absolute UTC-calendar publication gap."""
    if gap is None:
        return "unknown"
    if isinstance(gap, bool) or not isinstance(gap, int) or gap < 0:
        raise ResearchError("Publication gap must be a nonnegative integer or null")
    for limit, name in zip((7, 14, 30, 90), BANDS, strict=False):
        if gap <= limit:
            return name
    return ">90"


def candidate_batches(values: Any, ids: Sequence[str], pooled_threshold: float,
                      block_size: int = 128
                      ) -> Iterator[tuple[list[dict[str, Any]], dict[str, int]]]:
    """Visit ALL unordered vector pairs without dates or nearest-neighbor caps.

    Original float32 vectors and float64 scalar reranking match the frozen pair
    study. Block products only prefilter with a 1e-10 margin; the exact canonical
    distance controls inclusion. Distinct source IDs retain duplicate vectors.
    Each yielded batch contains at most 200 rows; block counters are emitted
    exactly once, including blocks which emit no candidate rows.
    """
    sources = list(ids)
    if (not 1 <= len(sources) <= 20000 or len(set(sources)) != len(sources)
            or any(not isinstance(value, str) or not value.strip() for value in sources)):
        raise ResearchError("Temporal scan requires 1..20000 unique nonempty article IDs")
    try:
        raw = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchError("Temporal scan requires a rectangular numeric vector matrix") from exc
    if (raw.ndim != 2 or raw.shape[0] != len(sources) or not 1 <= raw.shape[1] <= 8192
            or not np.isfinite(raw).all()):
        raise ResearchError("Temporal scan requires finite rows and 1..8192 vector dimensions")
    norms = np.sqrt(np.einsum("ij,ij->i", raw, raw, dtype=np.float64))
    if not np.all(np.abs(norms - 1.) <= 1e-4):
        raise ResearchError("Temporal scan requires unit-norm pooled vectors")
    if isinstance(block_size, bool) or not isinstance(block_size, int) or not 1 <= block_size <= 128:
        raise ResearchError("Temporal candidate blocks require 1..128 query rows")
    if (isinstance(pooled_threshold, bool) or not isinstance(pooled_threshold, (float, int))
            or not math.isfinite(pooled_threshold) or not -1 <= pooled_threshold <= 1):
        raise ResearchError("Temporal scan requires a finite cosine threshold in [-1,1]")
    matrix = raw.astype(np.float64)
    size = len(sources)
    for block, start in enumerate(range(0, size, block_size)):
        stop = min(start + block_size, size)
        targets = np.arange(start + 1, size)
        queries = np.arange(start, stop)
        scores = (matrix[queries] @ matrix[targets].T) / (norms[queries, None] * norms[targets])
        eligible = targets[None, :] > queries[:, None]
        possible = np.argwhere(eligible & (scores >= pooled_threshold - 1e-10))
        stats = {"block_index": block, "query_rows": stop - start,
                 "checked_vector_pairs": int(eligible.sum()), "emitted_pairs": 0}
        rows: list[dict[str, Any]] = []
        first = True
        for a, b in possible:
            left_index, right_index = int(queries[a]), int(targets[b])
            distance = float(np.clip(1. - np.dot(matrix[left_index], matrix[right_index])
                                    / (norms[left_index] * norms[right_index]), 0., 2.))
            if 1. - distance < pooled_threshold:
                continue
            left, right = sorted((sources[left_index], sources[right_index]))
            rows.append({"pair_id": digest([left, right]), "left": left, "right": right,
                         "distance": distance, "fold": "temporal_diagnostic",
                         "origin": ["all_vector_pairs_no_date_gate"]})
            if len(rows) == 200:
                yield rows, {**stats, "emitted_pairs": len(rows)} if first else {
                    "block_index": block, "query_rows": 0, "checked_vector_pairs": 0,
                    "emitted_pairs": len(rows)}
                first, rows = False, []
        if rows or first:
            yield rows, {**stats, "emitted_pairs": len(rows)} if first else {
                "block_index": block, "query_rows": 0, "checked_vector_pairs": 0,
                "emitted_pairs": len(rows)}
