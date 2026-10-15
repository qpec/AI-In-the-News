"""Pure numerical helpers for a bounded, frame-conditional event-link study.

Research callers must register and retain inputs/results through Research.execute.
No source reading, model calls, acceptance, or population inference occurs here.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from typing import Any

import faiss
import numpy as np

from .common import ResearchError

BANDS = (0., .025, .05, .10, .20, .30, .50, 2.)
QUOTAS = (8, 10, 12, 10, 6, 4, 4)
GRID = (.01, .025, .05, .075, .10, .125, .15, .175, .20, .225, .25, .275, .30, .35, .40)
LIMITATIONS = [
    "Probabilities and metrics condition on the frozen nearest-neighbor plus random-background pair frame.",
    "No corpus-population recall or confidence interval is established; pairs may share articles.",
    "Passing a model-reference screen does not establish human-validated event identity.",
]


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _rng(seed: str, purpose: str) -> np.random.Generator:
    if not isinstance(seed, str) or not seed.strip():
        raise ResearchError("Pair sampling requires a nonempty seed")
    return np.random.Generator(np.random.PCG64(int(_hash([seed, purpose])[:32], 16)))


def _unrank_pair(rank: int, size: int) -> tuple[int, int]:
    """Invert the lexicographic upper triangle without constructing all pairs."""
    low, high = 0, size - 1
    while low + 1 < high:
        middle = (low + high) // 2
        before = middle * (2 * size - middle - 1) // 2
        if before <= rank:
            low = middle
        else:
            high = middle
    before = low * (2 * size - low - 1) // 2
    return low, low + 1 + rank - before


def build_frame(vectors: Any, article_ids: Sequence[str], body_sha256_by_id: Mapping[str, str],
                *, seed: str) -> dict[str, Any]:
    """Keep one lowest-ID representative per exact body SHA; split bodies 70/30."""
    _rng(seed, "validate")
    try:
        values = np.asarray(vectors)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchError("Pair vectors must be a rectangular numeric matrix") from exc
    ids = list(article_ids)
    if (values.ndim != 2 or not 1 <= len(values) <= 20000 or not 1 <= values.shape[1] <= 8192
            or len(ids) != len(values) or len(set(ids)) != len(ids)
            or any(not isinstance(item, str) or not item.strip() for item in ids)):
        raise ResearchError("Pair frame requires 1..20000 unique IDs and 1..8192 vector dimensions")
    try:
        values = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ResearchError("Pair vectors must be numeric") from exc
    if not np.isfinite(values).all():
        raise ResearchError("Pair vectors must be finite")
    norms = np.sqrt(np.einsum("ij,ij->i", values, values, dtype=np.float64))
    if not np.all(np.abs(norms - 1.) <= 1e-4):
        raise ResearchError("Pair vectors must have unit norm")
    bodies: dict[str, list[str]] = defaultdict(list)
    for item in ids:
        body = body_sha256_by_id.get(item)
        if (not isinstance(body, str) or len(body) != 64
                or any(character not in "0123456789abcdef" for character in body)):
            raise ResearchError("Every article requires an exact lowercase SHA256 body hash")
        bodies[body].append(item)
    position = {item: index for index, item in enumerate(ids)}
    representatives = []
    aliases = []
    for body, members in sorted(bodies.items()):
        members.sort()
        fold = "validation" if int(_hash([seed, "body-fold", body])[:16], 16) % 10 < 3 else "development"
        representative = members[0]
        representatives.append({"article_id": representative, "body_sha256": body, "fold": fold})
        aliases.append({"representative": representative, "body_sha256": body, "fold": fold,
                        "aliases": members[1:], "all_source_ids": members})
    origins: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    fold_counts = {}
    normalized = np.array(values, dtype=np.float32, order="C", copy=True)
    normalized /= norms.astype(np.float32)[:, None]
    for fold in ("development", "validation"):
        members = sorted(row["article_id"] for row in representatives if row["fold"] == fold)
        count = len(members)
        fold_counts[fold] = {"representatives": count, "all_possible_pairs": count * (count - 1) // 2}
        if count < 2:
            fold_counts[fold]["background_pairs"] = 0
            continue
        subset = normalized[[position[item] for item in members]]
        index = faiss.IndexFlatIP(values.shape[1])
        index.add(subset)
        _, neighbors = index.search(subset, min(count, 9))
        for left, candidates in enumerate(neighbors):
            retained = [int(right) for right in candidates if right >= 0 and right != left][:8]
            for right in retained:
                first, second = sorted((members[left], members[right]))
                origins[(fold, first, second)].add("nearest_neighbor")
        possible = count * (count - 1) // 2
        chosen = _rng(seed, "background:" + fold).choice(possible, size=min(512, possible), replace=False)
        fold_counts[fold]["background_pairs"] = len(chosen)
        for rank in chosen:
            left, right = _unrank_pair(int(rank), count)
            origins[(fold, members[left], members[right])].add("background")
    rows = []
    for (fold, left_id, right_id), origin in sorted(origins.items()):
        a, b = position[left_id], position[right_id]
        distance = float(np.clip(1. - np.dot(values[a].astype(np.float64), values[b].astype(np.float64))
                                 / (norms[a] * norms[b]), 0., 2.))
        rows.append({"pair_id": _hash([left_id, right_id]), "left": left_id, "right": right_id,
                     "distance": distance, "fold": fold, "origin": sorted(origin)})
    configuration = {"seed": seed, "neighbors": 8, "background_pairs_per_fold": 512,
                     "split": "body-sha-hash-70-development-30-validation-v1",
                     "discovery_dtype": "float32", "rerank_dtype": "float64",
                     "faiss_version": getattr(faiss, "__version__", None),
                     "numpy_version": np.__version__}
    return {"rows": rows, "frame_hash": _hash(rows), "configuration": configuration,
            "vector_sha256": hashlib.sha256(values.astype("<f4").tobytes()).hexdigest(),
            "vector_article_order": ids, "representatives": representatives, "aliases": aliases,
            "input_articles": len(ids), "unique_bodies": len(representatives),
            "excluded_duplicate_copies": len(ids) - len(representatives),
            "fold_counts": fold_counts, "limitations": LIMITATIONS}


def _sample_strata(frame: dict[str, Any], strata: list[list[dict[str, Any]]], counts: list[int],
                   names: list[str], *, seed: str, purpose: str) -> dict[str, Any]:
    selected, audit = [], []
    for rows, count, name in zip(strata, counts, names, strict=True):
        ordered = sorted(rows, key=lambda row: row["pair_id"])
        count = min(len(ordered), count)
        probability = count / len(ordered) if ordered else 0.
        audit.append({"stratum": name, "N": len(ordered), "n": count,
                      "inclusion_probability": probability})
        chosen = _rng(seed, purpose + ":" + name).choice(len(ordered), size=count, replace=False)
        for index in sorted(int(value) for value in chosen):
            selected.append({**ordered[index], "stratum": name, "inclusion_probability": probability,
                             "weight": 1. / probability})
    selected.sort(key=lambda row: row["pair_id"])
    return {"rows": selected, "strata": audit, "seed": seed, "frame_hash": frame["frame_hash"],
            "sampling": "stratified-SRS-without-replacement-PCG64-v1", "purpose": purpose,
            "selected_pairs": len(selected), "limitations": LIMITATIONS}


def sample_development(frame: dict[str, Any], *, seed: str) -> dict[str, Any]:
    strata: list[list[dict[str, Any]]] = [[] for _ in QUOTAS]
    for row in frame["rows"]:
        if row["fold"] == "development":
            band = min(int(np.searchsorted(BANDS, row["distance"], side="right")) - 1, len(QUOTAS) - 1)
            strata[band].append(row)
    counts = [min(len(rows), quota) for rows, quota in zip(strata, QUOTAS, strict=True)]
    remaining = min(54, sum(map(len, strata))) - sum(counts)
    while remaining:
        for index, rows in enumerate(strata):
            if remaining and counts[index] < len(rows):
                counts[index] += 1
                remaining -= 1
    result = _sample_strata(frame, strata, counts, [f"band_{index}" for index in range(len(QUOTAS))],
                            seed=seed, purpose="development")
    result["band_edges"] = list(BANDS)
    result["band_intervals"] = "lower-inclusive, upper-exclusive; final upper bound inclusive"
    result["initial_quotas"] = list(QUOTAS)
    result["redistribution"] = "pre-label deterministic round-robin in ascending band order"
    return result


def sample_validation(frame: dict[str, Any], candidate_cutoff: float, *, seed: str) -> dict[str, Any]:
    if not isinstance(candidate_cutoff, (int, float)) or not math.isfinite(candidate_cutoff) or not 0 < candidate_cutoff <= .40:
        raise ResearchError("Validation requires a frozen cutoff in (0,0.40]")
    rows = [row for row in frame["rows"] if row["fold"] == "validation"]
    strata = [[row for row in rows if row["distance"] <= candidate_cutoff],
              [row for row in rows if row["distance"] > candidate_cutoff]]
    result = _sample_strata(frame, strata, [30, 6], ["predicted_link", "predicted_nonlink"],
                            seed=seed, purpose="validation")
    result["candidate_cutoff"] = candidate_cutoff
    result["deficit_replacement"] = False
    return result


def _metrics(rows: Sequence[dict[str, Any]], judgements: Mapping[str, dict[str, Any]],
             cutoff: float, *, validation: bool) -> dict[str, Any]:
    if len({row["pair_id"] for row in rows}) != len(rows):
        raise ResearchError("Sample pair IDs must be unique")
    if set(judgements) - {row["pair_id"] for row in rows}:
        raise ResearchError("Judgements outside this frozen sample are forbidden")
    weighted = {name: 0. for name in ("TP", "FP", "FN", "TN", "uncertain_link", "uncertain_nonlink")}
    counts = {name: 0 for name in ("same_event", "different_event", "uncertain", "missing", "failed",
                                    "pending", "invalid", "predicted_link", "predicted_nonlink")}
    for row in rows:
        probability = row.get("inclusion_probability")
        if not isinstance(probability, (int, float)) or not math.isfinite(probability) or not 0 < probability <= 1:
            raise ResearchError("Sample inclusion probability must be finite and in (0,1]")
        link = row["distance"] <= cutoff
        counts["predicted_link" if link else "predicted_nonlink"] += 1
        judgement = judgements.get(row["pair_id"])
        if judgement is None:
            counts["missing"] += 1
            continue
        status, label = judgement.get("status"), judgement.get("label")
        if status in {"failed", "pending"}:
            counts[status] += 1
            continue
        if status != "completed" or label not in {"same_event", "different_event", "uncertain"}:
            counts["invalid"] += 1
            continue
        counts[label] += 1
        category = ("uncertain_link" if link else "uncertain_nonlink") if label == "uncertain" else (
            ("TP" if link else "FN") if label == "same_event" else ("FP" if link else "TN"))
        weighted[category] += 1. / probability
    precision_denominator = weighted["TP"] + weighted["FP"] + weighted["uncertain_link"]
    recall_denominator = weighted["TP"] + weighted["FN"] + weighted["uncertain_nonlink"]
    precision = weighted["TP"] / precision_denominator if precision_denominator else None
    recall = weighted["TP"] / recall_denominator if recall_denominator else None
    observed = counts["uncertain"] / len(rows) if rows else None
    total = sum(weighted.values())
    uncertain_weight = weighted["uncertain_link"] + weighted["uncertain_nonlink"]
    weighted_fraction = uncertain_weight / total if total else None
    failures = []
    if not rows or any(counts[name] for name in ("missing", "failed", "pending", "invalid")):
        failures.append("incomplete_processing")
    if counts["same_event"] < 5 or counts["different_event"] < 5:
        failures.append("insufficient_clear_labels")
    if observed is None or weighted_fraction is None or observed > .20 or weighted_fraction > .20:
        failures.append("excessive_or_unidentified_uncertainty")
    if precision is None or precision < .90:
        failures.append("precision_below_0.90_or_unidentified")
    if recall is None or recall < .80:
        failures.append("recall_below_0.80_or_unidentified")
    if validation and (counts["predicted_link"] < 10 or counts["predicted_nonlink"] < 5):
        failures.append("sparse_validation_strata")
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.
    return {"cutoff": cutoff, "counts": counts, "weighted": weighted, "pessimistic_precision": precision,
            "pessimistic_recall": recall, "pessimistic_f1": f1, "observed_uncertain_fraction": observed,
            "weighted_uncertain_fraction": weighted_fraction, "eligible": not failures, "failures": failures}


def evaluate_grid(sample_rows: Sequence[dict[str, Any]], judgements: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    if any(row["fold"] != "development" for row in sample_rows):
        raise ResearchError("Cutoff selection may inspect development labels only")
    cutoffs = sorted(set(GRID) | {float(row["distance"]) for row in sample_rows if 0 < row["distance"] <= .40})
    metrics = [_metrics(sample_rows, judgements, cutoff, validation=False) for cutoff in cutoffs]
    eligible = [row for row in metrics if row["eligible"]]
    winner = min(eligible, key=lambda row: (-row["pessimistic_f1"], row["cutoff"])) if eligible else None
    return {"grid": metrics, "candidate_cutoff": winner["cutoff"] if winner else None,
            "selection_rule": "fixed grid plus observed development distance boundaries",
            "status": "candidate_frozen" if winner else "inconclusive", "limitations": LIMITATIONS}


def evaluate_validation(sample_rows: Sequence[dict[str, Any]], judgements: Mapping[str, dict[str, Any]],
                        candidate_cutoff: float) -> dict[str, Any]:
    if (not isinstance(candidate_cutoff, (int, float)) or not math.isfinite(candidate_cutoff)
            or not 0 < candidate_cutoff <= .40 or any(row["fold"] != "validation" for row in sample_rows)):
        raise ResearchError("Validation requires a frozen cutoff and validation-only pairs")
    result = _metrics(sample_rows, judgements, candidate_cutoff, validation=True)
    result.update({"status": "passed_model_reference" if result["eligible"] else "inconclusive",
                   "human_validated": False, "limitations": LIMITATIONS})
    return result
