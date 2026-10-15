"""Bounded source-free clustering mechanics; corpus callers must use Research.execute.

These implementations propose uncertain vector groups, never accepted event dossiers.
The retained DBSCAN reference recomputes all original article vectors after each batch;
it is deliberately bounded and is not a scalable incremental production algorithm.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
import hashlib
import json
import time
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.cluster import DBSCAN

from .common import ResearchError

MAX_ARTICLES = 2000
MAX_DIMENSIONS = 8192
NUMERICAL_TOLERANCE = float(64 * np.finfo(np.float64).eps)
_Fit = Callable[[NDArray[np.float64], list[str], float], list[list[str]]]


def _checked(vectors: Any, ids: list[str], eps: float) -> NDArray[np.float64]:
    if (not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_ARTICLES
            or any(not isinstance(item, str) or not item.strip() for item in ids)):
        raise ResearchError("Clustering requires 1..2000 nonblank article IDs")
    if len(set(ids)) != len(ids):
        raise ResearchError("Article IDs must be globally unique, including across batches")
    if (isinstance(eps, bool) or not isinstance(eps, (float, int))
            or not np.isfinite(eps) or not 0 < eps <= 2):
        raise ResearchError("Cosine-distance eps must be finite and in (0,2]")
    try:
        if np.iscomplexobj(vectors):
            raise ValueError("Complex vectors are unsupported")
        values = np.array(vectors, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchError("Vectors must be a rectangular real numeric matrix") from exc
    if (values.ndim != 2 or values.shape[0] != len(ids)
            or not 1 <= values.shape[1] <= MAX_DIMENSIONS or not np.isfinite(values).all()):
        raise ResearchError("Expected finite article vectors with 1..8192 dimensions")
    # Scale first so finite large magnitudes cannot overflow the norm calculation.
    scales = np.max(np.abs(values), axis=1, keepdims=True)
    if np.any(scales == 0):
        raise ResearchError("Zero article vectors cannot be normalized")
    values /= scales
    values /= np.linalg.norm(values, axis=1, keepdims=True)
    values.setflags(write=False)
    return values


def _distance(values: NDArray[np.float64]) -> NDArray[np.float64]:
    distance = np.clip(1 - values @ values.T, 0, 2)
    distance = (distance + distance.T) / 2
    np.fill_diagonal(distance, 0)
    return distance


def _partition(ids: list[str], labels: Any) -> list[list[str]]:
    groups: dict[str, list[str]] = {}
    for item, label in zip(ids, labels, strict=True):
        key = f"singleton:{item}" if label == -1 else f"group:{int(label)}"
        groups.setdefault(key, []).append(item)
    return sorted((sorted(members) for members in groups.values()), key=tuple)


def _dbscan(distance: NDArray[np.float64], ids: list[str], eps: float) -> list[list[str]]:
    labels = DBSCAN(eps=eps, min_samples=2, metric="precomputed", n_jobs=1).fit_predict(distance)
    return _partition(ids, labels)


def _complete_link(distance: NDArray[np.float64], ids: list[str], eps: float) -> list[list[str]]:
    if len(ids) == 1:
        return [list(ids)]
    tree = linkage(squareform(distance, checks=False), method="complete", optimal_ordering=False)
    return _partition(ids, fcluster(tree, t=eps, criterion="distance"))


def _candidate_id(members: list[str]) -> str:
    raw = json.dumps(members, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return "candidate:" + hashlib.sha256(raw).hexdigest()


def _snapshot(
    partition: list[list[str]], ids: list[str], distance: NDArray[np.float64], eps: float,
) -> dict[str, Any]:
    positions = {item: index for index, item in enumerate(ids)}
    groups: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    for members in partition:
        indexes = [positions[item] for item in members]
        maximum = float(distance[np.ix_(indexes, indexes)].max())
        candidate_id = _candidate_id(members)
        groups.append({"candidate_id": candidate_id, "members": list(members),
                       "kind": "singleton" if len(members) == 1 else "candidate_group",
                       "assignment": "uncertain", "max_within_cosine_distance": maximum,
                       "within_eps": maximum <= eps + NUMERICAL_TOLERANCE})
        assignments.extend({"source_version": item, "candidate_id": candidate_id,
                            "assignment": "uncertain"} for item in members)
    counts = Counter(row["source_version"] for row in assignments)
    if set(counts) != set(ids) or any(count != 1 for count in counts.values()):
        raise ResearchError("Clustering partition violated complete unique membership")
    return {"partition": partition, "singletons": sorted(group[0] for group in partition if len(group) == 1),
            "groups": groups, "assignments": sorted(assignments, key=lambda row: row["source_version"]),
            "max_within_cosine_distance": max(row["max_within_cosine_distance"] for row in groups)}


def _lineage(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    merges: list[dict[str, Any]] = []
    old_membership = {item: group["candidate_id"] for group in previous for item in group["members"]}
    new_membership = {item: group["candidate_id"] for group in current for item in group["members"]}
    for old in previous:
        successor_ids = sorted({new_membership[item] for item in old["members"] if item in new_membership})
        relation = ("unchanged" if successor_ids == [old["candidate_id"]] else
                    "split" if len(successor_ids) > 1 else "reassigned")
        changes.append({"previous_candidate_id": old["candidate_id"],
                        "successor_candidate_ids": successor_ids, "relation": relation})
    for new in current:
        parents = sorted({old_membership[item] for item in new["members"] if item in old_membership})
        if len(parents) > 1:
            merges.append({"previous_candidate_ids": parents, "candidate_id": new["candidate_id"],
                           "members": new["members"]})
    return {"changes": changes, "merges": merges,
            "new_candidate_ids": sorted(new["candidate_id"] for new in current
                                        if not any(item in old_membership for item in new["members"]))}


def _run(
    vectors: Any, ids: list[str], batch_sizes: list[int], *, eps: float, fit: _Fit, implementation: str,
) -> dict[str, Any]:
    values = _checked(vectors, ids, eps)
    if (not isinstance(batch_sizes, (list, tuple)) or not batch_sizes
            or any(isinstance(size, bool) or not isinstance(size, int) or size < 1 for size in batch_sizes)
            or sum(batch_sizes) != len(ids)):
        raise ResearchError("Positive integer batch sizes must cover every input article exactly once")
    batches: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    successful: dict[str, Any] = {"partition": [], "singletons": [], "groups": [], "assignments": [],
                                  "max_within_cosine_distance": None}
    completed = 0
    dense_cells_evaluated = 0
    for number, size in enumerate(batch_sizes):
        end = completed + size
        started = time.perf_counter()
        try:
            order = sorted(range(end), key=lambda index: ids[index])
            retained_ids = [ids[index] for index in order]
            distance = _distance(values[order])
            dense_cells_evaluated += end * end
            partition = fit(distance, retained_ids, eps)
            snapshot = _snapshot(partition, retained_ids, distance, eps)
            if fit is _complete_link and any(not group["within_eps"] for group in snapshot["groups"]):
                raise ResearchError("Complete-link partition violated the pairwise cosine-distance bound")
            lineage = _lineage(successful["groups"], snapshot["groups"])
        except Exception as exc:
            error = {"batch": number, "error_type": type(exc).__name__, "input_ids": ids[completed:end]}
            errors.append(error)
            batches.append({**error, "status": "failed", "elapsed_seconds": time.perf_counter() - started})
            break
        completed = end
        successful = snapshot
        batches.append({"batch": number, "input_ids": ids[end-size:end], "status": "completed",
                        "retained_original_vector_count": end, **snapshot, "lineage": lineage,
                        "emitted_projection": [{"cluster_id": group["candidate_id"], "members": group["members"]}
                                               for group in snapshot["groups"]],
                        "elapsed_seconds": time.perf_counter() - started})
    retained = {item for group in successful["partition"] for item in group}
    return {"implementation": implementation,
            "parameters": {"eps": eps, "metric": "float64-cosine", "min_samples": 2 if fit is _dbscan else None,
                           "linkage": "complete" if fit is _complete_link else None,
                           "deterministic_input_order": "ascending-source-version-id",
                           "numerical_tolerance": NUMERICAL_TOLERANCE},
            "batch_sizes": list(batch_sizes), **successful, "batches": batches,
            "errors": errors, "complete": not errors,
            "coverage": {"input_occurrences": len(ids), "unique_input_ids": len(ids),
                         "completed_input_occurrences": completed, "pending_input_occurrences": len(ids)-completed,
                         "pool_member_occurrences": len(retained), "pool_unique_ids": len(retained),
                         "missing_pool_ids": sorted(set(ids)-retained), "duplicate_pool_ids": [],
                         "duplicate_input_ids": [], "emitted_unique_ids": len(retained),
                         "never_emitted_ids": sorted(set(ids)-retained)},
            "emitted_projection": [{"cluster_id": group["candidate_id"], "members": group["members"]}
                                   for group in successful["groups"]],
            "work_bound": {"max_articles": MAX_ARTICLES, "max_dimensions": MAX_DIMENSIONS,
                           "max_dense_distance_cells": len(ids)**2,
                           "max_dense_distance_bytes": len(ids)**2 * np.dtype(np.float64).itemsize,
                           "evaluated_dense_cells": dense_cells_evaluated,
                           "pairwise_reference_only": True},
            "accepted_dossiers": 0,
            "limitations": ["All memberships are uncertain vector candidates, not validated same-event findings.",
                            "Dense all-pairs recomputation is a bounded reference, not scalable incremental production.",
                            "The selected eps is an operating distance, not a calibrated event-identity cutoff.",
                            "DBSCAN can connect dissimilar endpoints through density chains; compactness is diagnostic."]}


def retained_dbscan(vectors: Any, ids: list[str], batch_sizes: list[int], *, eps: float = .10) -> dict[str, Any]:
    """Recompute deterministic DBSCAN from every original retained article vector after each batch."""
    return _run(vectors, ids, batch_sizes, eps=eps, fit=_dbscan,
                implementation="corrected-retained-article-float64-dbscan-v1")


def complete_link(vectors: Any, ids: list[str], *, eps: float = .10) -> dict[str, Any]:
    """Deterministic compact complete-link candidates, without density-chain expansion."""
    return _run(vectors, ids, [len(ids)], eps=eps, fit=_complete_link,
                implementation="bounded-complete-link-cosine-v1")
