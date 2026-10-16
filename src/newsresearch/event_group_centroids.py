"""Pure fast group-vector proposals, not semantic judgments or accepted merges.

Real data callers must register this method and use Research.execute. Exact-body
families vote once in a centroid; every article remains in coverage and radius.
"""
from __future__ import annotations

import math
import time
from collections import Counter
from itertools import product
from typing import Any

import faiss
import numpy as np

from .common import digest
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES
from .event_rule_application import publication_coverage

Json = dict[str, Any]
METHOD = "exact-body-deduplicated-group-centroid-saved-five-gate-proposals-v1"
THRESHOLDS = (.90, .95, .975)


def build_centroids(groups: list[Json], article_ids: list[str], pooled: Any, metadata: Json) -> Json:
    started = time.perf_counter()
    if (len(article_ids) > 20000 or len(set(article_ids)) != len(article_ids)
            or any(not isinstance(item, str) or not item for item in article_ids)):
        raise ValueError("at most20000 unique nonempty vector article IDs are required")
    matrix = np.asarray(pooled)
    if (matrix.ndim != 2 or matrix.shape[0] != len(article_ids) or not 1 <= matrix.shape[1] <= 8192
            or matrix.dtype.kind not in "fi"):
        raise ValueError("vector mapping requires numeric rows and 1..8192 dimensions")
    positions = {item: n for n, item in enumerate(article_ids)}
    owners: set[str] = set()
    group_ids: set[str] = set()
    rows: list[Json] = []
    vectors: list[Any] = []
    valid_ids = []
    for group in sorted(groups, key=lambda row: row["group_id"]):
        key, members = group.get("group_id"), group.get("members")
        if (not isinstance(key, str) or not key or key in group_ids or not isinstance(members, list)
                or not members or len(set(members)) != len(members)
                or any(not isinstance(item, str) or not item or item in owners for item in members)):
            raise ValueError("groups must partition unique article IDs with unique nonempty group identities")
        group_ids.add(key)
        owners.update(members)
        members = sorted(members)
        dates = publication_coverage(members, {item: metadata.get(item, {}).get("published_at") for item in members})
        available_dates = list(dates["valid_dates"].values())
        item = {"group_id": key, "members": members, "member_count": len(members),
                "publication_min": min(available_dates).isoformat() if available_dates else None,
                "publication_max": max(available_dates).isoformat() if available_dates else None,
                "missing_date_members": dates["missing_date_ids"], "missing_vector_members": [],
                "invalid_vector_members": [], "missing_body_members": [], "centroid_row": None,
                "angular_radius_radians": None, "min_member_cosine": None}
        units: dict[str, Any] = {}
        bodies: dict[str, str] = {}
        for source in members:
            body = metadata.get(source, {}).get("body_sha256")
            if not isinstance(body, str) or not body:
                item["missing_body_members"].append(source)
            else:
                bodies.setdefault(body, source)
            if source not in positions:
                item["missing_vector_members"].append(source)
                continue
            value = np.asarray(matrix[positions[source]], dtype=np.float64)
            norm = float(np.linalg.norm(value))
            if not np.isfinite(value).all() or not math.isfinite(norm) or abs(norm - 1.) > 1e-4:
                item["invalid_vector_members"].append(source)
                continue
            units[source] = value / norm
        item["distinct_body_representatives"] = sorted(bodies.values())
        item["distinct_body_families"] = len(bodies)
        item["status"] = "unprocessed" if any(item[name] for name in (
            "missing_vector_members", "invalid_vector_members", "missing_body_members")) else "completed"
        if item["status"] == "completed":
            center = np.mean([units[source] for source in sorted(bodies.values())], axis=0)
            norm = float(np.linalg.norm(center))
            if norm <= 1e-12:
                item["status"], item["reason"] = "unprocessed", "zero_or_degenerate_centroid"
            else:
                center = np.asarray(center / norm, dtype=np.float32)
                actual_center = center.astype(np.float64)
                actual_center /= np.linalg.norm(actual_center)
                minimum = min(float(np.clip(np.dot(actual_center, units[source]), -1., 1.)) for source in members)
                item.update(centroid_row=len(vectors), min_member_cosine=minimum,
                            angular_radius_radians=math.acos(minimum))
                vectors.append(center)
                valid_ids.append(key)
        rows.append(item)
    return {"group_ids": valid_ids, "centroids": np.asarray(vectors, dtype=np.float32).reshape(-1, matrix.shape[1]),
            "rows": rows, "timings": {"representation_seconds": time.perf_counter() - started}}


def map_candidates(representation: Json, top_k: int = 8) -> Json:
    if type(top_k) is not int or not 1 <= top_k <= 8:
        raise ValueError("the frozen topK must be within1..8")
    ids, values = representation["group_ids"], representation["centroids"]
    rows = {row["group_id"]: row for row in representation["rows"]}
    centers = np.asarray(values, dtype=np.float64)
    if len(ids):
        centers /= np.linalg.norm(centers, axis=1)[:, None]
    queries = [n for n, key in enumerate(ids) if rows[key]["member_count"] > 1]
    started = time.perf_counter()
    index = faiss.IndexFlatIP(values.shape[1])
    index.add(values)
    build_seconds = time.perf_counter() - started
    nominated: dict[tuple[str, str], Json] = {}
    fetch = min(len(ids), 32)
    old_threads = faiss.omp_get_max_threads()
    started = time.perf_counter()
    boundary_ties = 0
    try:
        faiss.omp_set_num_threads(4)
        for offset in range(0, len(queries), 512):
            batch = queries[offset:offset + 512]
            scores, neighbors = index.search(values[batch], fetch)
            for local, query in enumerate(batch):
                raw_scores, raw_neighbors = scores[local], neighbors[local]
                if fetch < len(ids) and len(raw_scores) and abs(float(raw_scores[-1]) - float(raw_scores[min(top_k, len(raw_scores) - 1)])) <= 2e-6:
                    boundary_ties += 1
                ranked = sorted(((-float(np.clip(np.dot(centers[query], centers[int(n)]), -1., 1.)), ids[int(n)], int(n))
                                 for n in raw_neighbors if int(n) >= 0 and int(n) != query))[:top_k]
                for rank, (negative, target_id, target) in enumerate(ranked, 1):
                    pair = tuple(sorted((ids[query], target_id)))
                    if pair not in nominated:
                        a, b = (rows[key] for key in pair)
                        missing_date = bool(a["missing_date_members"] or b["missing_date_members"])
                        span = None
                        if not missing_date:
                            from datetime import date
                            span = (date.fromisoformat(max(a["publication_max"], b["publication_max"]))
                                    - date.fromisoformat(min(a["publication_min"], b["publication_min"]))).days
                        cosine = -negative
                        angle = math.acos(float(np.clip(cosine, -1., 1.)))
                        lower = math.cos(min(math.pi, angle + a["angular_radius_radians"] + b["angular_radius_radians"]))
                        nominated[pair] = {"candidate_id": digest({"method": METHOD, "old_group_ids": list(pair)}),
                            "old_group_ids": list(pair), "article_members": sorted(a["members"] + b["members"]),
                            "left_members": a["members"], "right_members": b["members"],
                            "centroid_cosine": cosine, "pooled_angular_lower_bound": lower,
                            "publication_span_days": span, "nominated_by": [], "rank_by_query": {},
                            "status": "missing_publication_date" if missing_date else "same_window_excluded"
                            if span is not None and span <= 7 else "cross_window_nominated"}
                    nominated[pair]["nominated_by"].append(ids[query])
                    nominated[pair]["rank_by_query"][ids[query]] = rank
    finally:
        faiss.omp_set_num_threads(old_threads)
    return {"candidates": [nominated[pair] for pair in sorted(nominated)], "index": index,
            "diagnostics": {"valid_centroids": len(ids), "multi_group_queries": len(queries), "top_k": top_k,
                            "candidate_pairs": len(nominated), "retrieved_neighbors_per_query": fetch,
                            "tie_truncation_queries": boundary_ties,
                            "same_window_excluded": sum(row["status"] == "same_window_excluded" for row in nominated.values()),
                            "nearest_neighbor_truncation": True, "all_group_pairs_searched": False,
                            "retrieval": "exact float32 IndexFlatIP; at most32 retrieved neighbors; float64 reranking of bounded pool only",
                            "tie_policy": "stable sorted group-ID insertion; boundary ambiguity counted, never a different-event finding"},
            "timings": {"index_build_seconds": build_seconds, "batch_search_seconds": time.perf_counter() - started}}


def gate_candidates(rule: Json, scored: list[Json], frame: Json, minimum_threshold: float = .90) -> Json:
    """Check saved cross-article features once for any later cutoff variant."""
    started = time.perf_counter()
    if isinstance(minimum_threshold, bool) or minimum_threshold not in THRESHOLDS:
        raise ValueError("centroid cutoff must be one of the frozen0.90/0.95/0.975 options")
    no_date = {**rule, "publication_gap_days": None}
    predicts({"features": dict.fromkeys(FEATURES, 1.)}, no_date)
    lookup = {}
    for row in scored:
        a, b = row.get("left"), row.get("right")
        if not isinstance(a, str) or not isinstance(b, str) or not a or not b or a == b:
            raise ValueError("scored article pairs need distinct nonempty IDs")
        pair = tuple(sorted((a, b)))
        if pair in lookup or row.get("pair_id") != digest(list(pair)):
            raise ValueError("scored pairs must have unique canonical identities")
        lookup[pair] = row
    candidates = []
    for source in frame["candidates"]:
        row = {**source, "cross_pair_counts": {}, "accepted": False}
        row["pooled_certificate_passes"] = source["pooled_angular_lower_bound"] >= rule["thresholds"][0]
        if row["status"] == "cross_window_nominated":
            if row["centroid_cosine"] < minimum_threshold:
                row["status"] = "below_gate_floor_review"
            else:
                counts: Counter[str] = Counter()
                for a, b in product(row["left_members"], row["right_members"]):
                    score = lookup.get(tuple(sorted((a, b))))
                    if score is None:
                        counts["missing_row"] += 1
                    elif score.get("status") != "completed":
                        status = score.get("status")
                        counts[status if status in {"failed", "pending", "unknown"} else "invalid_status"] += 1
                    else:
                        features = score.get("features")
                        valid = isinstance(features, dict) and all(not isinstance(value := features.get(name), bool) and isinstance(value, (int, float))
                                    and math.isfinite(value) and -1 <= value <= 1 for name in FEATURES)
                        counts["invalid_features" if not valid else "passing" if predicts(score, no_date) else "below_original_cutoff"] += 1
                row["cross_pair_counts"] = dict(sorted(counts.items()))
                row["expected_cross_pairs"] = len(row["left_members"]) * len(row["right_members"])
                row["status"] = "qualified_unjudged" if counts["passing"] == row["expected_cross_pairs"] else "cross_evidence_requires_review"
        candidates.append(row)
    return {"candidates": candidates, "rule_hash": digest(no_date), "frame_hash": digest(frame["candidates"]),
            "minimum_threshold": minimum_threshold,
            "timings": {"original_cache_gate_seconds": time.perf_counter() - started}}


def select(rule: Json, scored: list[Json], frame: Json, threshold: float = .975, *, gated: Json | None = None) -> Json:
    started = time.perf_counter()
    if isinstance(threshold, bool) or threshold not in THRESHOLDS:
        raise ValueError("centroid cutoff must be one of the frozen0.90/0.95/0.975 options")
    frozen = gate_candidates(rule, scored, frame, threshold) if gated is None else gated
    if (frozen["rule_hash"] != digest({**rule, "publication_gap_days": None})
            or frozen["frame_hash"] != digest(frame["candidates"]) or frozen["minimum_threshold"] > threshold):
        raise ValueError("cached original gates must bind the same rule/frame and cover this centroid cutoff")
    candidates = [{**row, "centroid_cutoff": threshold} for row in frozen["candidates"]]
    for row in candidates:
        if row["status"] in {"qualified_unjudged", "below_gate_floor_review"} and row["centroid_cosine"] < threshold:
            row["status"] = "below_centroid_cutoff_review"
    used: set[str] = set()
    proposals = []
    for row in sorted(candidates, key=lambda value: (-value["centroid_cosine"], value["old_group_ids"])):
        if row["status"] != "qualified_unjudged":
            continue
        if any(key in used for key in row["old_group_ids"]):
            row["status"] = "old_group_already_proposed"
            continue
        used.update(row["old_group_ids"])
        row["status"] = "proposed_unjudged"
        proposals.append({**row, "proposal_id": digest({"method": METHOD, "threshold": threshold,
                                                       "old_group_ids": row["old_group_ids"]}),
                          "semantic_review_status": "unjudged", "accepted": False})
    return {"candidates": candidates, "proposals": proposals,
            "timings": {"selection_seconds": time.perf_counter() - started},
            "diagnostics": {"centroid_cutoff": threshold, "default_cutoff": .975,
                            "candidate_status_counts": dict(sorted(Counter(row["status"] for row in candidates).items())),
                            "proposed_group_pairs": len(proposals), "group_reuse": 0, "transitive_chaining": False,
                            "certificate_role": "pooled-cosine lower bound only; failure falls back to saved exact gates, never a different-event finding",
                            "new_passage_features": 0, "new_models": 0, "actual_group_merges": 0, "accepted_dossiers": 0}}
