"""Label-blind passage-vector features for bounded event-pair experiments.

No source text, judgements or model calls are accepted here. Research callers
must record the original row mapping and enter through Research.execute.
Publication gaps are descriptive; they are not event dates or decision gates.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections import OrderedDict
from datetime import date, datetime, timezone
import math
from typing import Any

import numpy as np

from .common import ResearchError

METHOD = "label-blind-saved-passage-pair-features-v1"
MAX_PAIRS = 200
MAX_PASSAGES = 2048
MAX_PAIRWISE_COMPARISONS = 4_000_000
FEATURES = ("pooled_cosine", "max_passage_cosine", "top3_mutual_best_mean_cosine",
            "symmetric_mean_best_cosine", "first_passage_cosine")
PAIR_FIELDS = {"pair_id", "left", "right", "distance", "fold", "origin", "stratum",
               "inclusion_probability", "weight"}


def _publication_date(value: Any) -> tuple[date | None, str]:
    if value is None or value == "":
        return None, "missing"
    if not isinstance(value, str):
        return None, "invalid"
    try:
        if len(value) == 10:
            return date.fromisoformat(value), "date_only"
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            return None, "timezone_unavailable"
        return stamp.astimezone(timezone.utc).date(), "aware_datetime_UTC_date"
    except (ValueError, OverflowError):
        return None, "invalid"


def _article(values: Any, source: str, chunk_rows: Mapping[str, Sequence[int]]) -> tuple[list[int], np.ndarray]:
    raw = chunk_rows.get(source, [])
    if not isinstance(raw, (list, tuple, np.ndarray)):
        raise ResearchError("Article passage rows must be a sequence of original integer row indices")
    if len(raw) > MAX_PASSAGES:
        raise ResearchError("Article exceeds 2048 passages; features do not truncate evidence")
    if any(not isinstance(row, (int, np.integer)) or isinstance(row, (bool, np.bool_)) for row in raw):
        raise ResearchError("Passage rows must be original integer row indices")
    rows = sorted(int(row) for row in raw)
    if len(set(rows)) != len(rows) or any(row < 0 or row >= values.shape[0] for row in rows):
        raise ResearchError("Passage row indices must be unique and in matrix bounds")
    if not rows:
        return rows, np.empty((0, values.shape[1]), dtype=np.float64)
    matrix = np.asarray(values[rows], dtype=np.float64)
    if not np.isfinite(matrix).all():
        raise ResearchError("Selected passage vectors must be finite")
    norms = np.sqrt(np.einsum("ij,ij->i", matrix, matrix))
    if not np.all(np.abs(norms - 1.) <= 1e-4):
        raise ResearchError("Selected passage vectors must have unit norm")
    matrix /= norms[:, None]
    return rows, matrix


def _pooled_cosine(left: np.ndarray, right: np.ndarray) -> float | None:
    a, b = left.sum(axis=0), right.sum(axis=0)
    norm_a, norm_b = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return None
    return float(np.clip(np.dot(a, b) / (norm_a * norm_b), -1., 1.))


def pair_features(passage_matrix: Any, article_chunk_rows: Mapping[str, Sequence[int]],
                  pair_rows: Sequence[dict[str, Any]], published_at_by_id: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Compute one bounded pair matrix at a time; no corpus-sized dense matrix.

    Original row indices define passage order and tie-breaking. Mutual-best
    means each passage chooses the other as its highest-cosine counterpart;
    ties choose the lowest original row. The top-three feature averages the
    available mutual pairs, explicitly recording when fewer than three exist.
    """
    if len(pair_rows) > MAX_PAIRS:
        raise ResearchError("Passage-feature batches are bounded to 200 pairs")
    try:
        values = np.asarray(passage_matrix)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchError("Saved passage matrix must be rectangular numeric data") from exc
    if values.ndim != 2 or not 1 <= values.shape[1] <= 8192 or values.dtype.kind not in "fiu":
        raise ResearchError("Saved passage matrix needs 1..8192 numeric dimensions")
    seen: set[str] = set()
    cache: OrderedDict[str, tuple[list[int], np.ndarray]] = OrderedDict()
    cache_bytes = 0

    def article(source: str) -> tuple[list[int], np.ndarray]:
        nonlocal cache_bytes
        if source in cache:
            cache.move_to_end(source)
            return cache[source]
        result = _article(values, source, article_chunk_rows)
        size = result[1].nbytes
        while cache and cache_bytes + size > 128 * 1024 * 1024:
            _, removed = cache.popitem(last=False)
            cache_bytes -= removed[1].nbytes
        if size <= 128 * 1024 * 1024:
            cache[source] = result
            cache_bytes += size
        return result

    output = []
    for pair in pair_rows:
        if set(pair) - PAIR_FIELDS:
            raise ResearchError("Passage features accept frozen numeric pair rows, never judge labels or explanations")
        pair_id, left, right = pair.get("pair_id"), pair.get("left"), pair.get("right")
        if (any(not isinstance(value, str) or not value.strip() for value in (pair_id, left, right))
                or pair_id in seen or left == right):
            raise ResearchError("Feature pairs require unique nonempty IDs and distinct article IDs")
        assert isinstance(pair_id, str) and isinstance(left, str) and isinstance(right, str)
        seen.add(pair_id)
        left_rows, a = article(left)
        right_rows, b = article(right)
        comparison_count = len(left_rows) * len(right_rows)
        if comparison_count > MAX_PAIRWISE_COMPARISONS:
            raise ResearchError("Pair exceeds four million passage comparisons; features do not truncate")
        left_date, left_date_status = _publication_date(published_at_by_id.get(left))
        right_date, right_date_status = _publication_date(published_at_by_id.get(right))
        gap = abs((left_date - right_date).days) if left_date and right_date else None
        row: dict[str, Any] = {"pair_id": pair_id, "left": left, "right": right, "method": METHOD,
            "publication_gap_days": gap, "publication_gap_basis": "Absolute UTC calendar-date difference; date-only values retained",
            "publication_status": {"left": left_date_status, "right": right_date_status},
            "publication_limit": "Descriptive publication metadata only; publication dates are not event dates",
            "diagnostics": {"left_passage_count": len(left_rows), "right_passage_count": len(right_rows),
                "pairwise_comparisons": comparison_count},
            "features": {feature: None for feature in FEATURES},
            "status": "missing_vectors" if not left_rows or not right_rows else "completed"}
        if row["status"] != "completed":
            row["missing_articles"] = [source for source, rows in ((left, left_rows), (right, right_rows)) if not rows]
            output.append(row)
            continue
        similarities = np.clip(a @ b.T, -1., 1.)
        left_best = np.argmax(similarities, axis=1)
        right_best = np.argmax(similarities, axis=0)
        mutual = [(index, int(other)) for index, other in enumerate(left_best) if right_best[int(other)] == index]
        mutual.sort(key=lambda indices: (-float(similarities[indices]), left_rows[indices[0]], right_rows[indices[1]]))
        top = mutual[:3]
        best = np.unravel_index(int(np.argmax(similarities)), similarities.shape)
        features = {"pooled_cosine": _pooled_cosine(a, b),
            "max_passage_cosine": float(similarities[best]),
            "top3_mutual_best_mean_cosine": float(np.mean([similarities[index] for index in top])),
            "symmetric_mean_best_cosine": float((np.max(similarities, axis=1).mean() + np.max(similarities, axis=0).mean()) / 2),
            "first_passage_cosine": float(similarities[0, 0])}
        if any(value is not None and not math.isfinite(value) for value in features.values()):
            raise ResearchError("Passage features must be finite when available")
        row["features"] = features
        row["diagnostics"].update({"best_pair_rows": [left_rows[best[0]], right_rows[best[1]]],
            "top_mutual_rows": [[left_rows[i], right_rows[j]] for i, j in top],
            "mutual_best_pairs": len(mutual), "top_mutual_pairs_used": len(top),
            "first_pair_rows": [left_rows[0], right_rows[0]],
            "pooled_feature_unavailable": features["pooled_cosine"] is None})
        output.append(row)
    return output
