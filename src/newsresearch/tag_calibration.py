"""Fit a query-specific cutoff on calibration labels; assess it on separate held-out labels."""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .common import Context, Json, ResearchError, digest, require_active
from .tagging import article_scores, bounded, definition, same_versions

if TYPE_CHECKING:
    from .runtime import Research


def metrics(items: list[Json], threshold: float, beta: float) -> Json:
    tp = sum(i["relevant"] and i["score"] >= threshold for i in items)
    fp = sum(not i["relevant"] and i["score"] >= threshold for i in items)
    fn = sum(i["relevant"] and i["score"] < threshold for i in items)
    tn = len(items) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    weight = beta * beta
    fbeta = (1 + weight) * precision * recall / (weight * precision + recall) if precision + recall else 0.0
    return {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": precision, "recall": recall, "f_beta": fbeta, "beta": beta, "denominator": len(items)}


def calibrate(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"evaluation"})
    run = engine.ledger.get(data["run"], "tag_run")
    same_versions(run, context)
    evaluation = engine.ledger.get(context.versions["evaluation"], "evaluation")["content"]
    if evaluation.get("method") != "query-tag-calibration-v1":
        raise ResearchError("Register a query-tag calibration evaluation")
    def created(ref: str) -> int:
        return int(engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (ref,)).fetchone()[0])
    if created(context.versions["evaluation"]) >= created(run["plan"]):
        raise ResearchError("Gold split and threshold rule must be registered before the model plan")
    beta = {"balanced": 1.0, "recall": 2.0, "precision": 0.5}.get(evaluation.get("priority"))
    if beta is None:
        raise ResearchError("Choose balanced, recall or precision before scoring")
    minimum = bounded(evaluation.get("minimum_per_class_per_split"), "minimum_per_class_per_split", 10000)
    required = [evaluation.get("minimum_test_precision"), evaluation.get("minimum_test_recall")]
    if any(type(v) not in {int, float} or not math.isfinite(v) or not 0 < v <= 1 for v in required):
        raise ResearchError("Register positive held-out precision and recall requirements")
    scored = {i["source_version"]: i for i in article_scores(engine, run)}
    groups: dict[str, str] = {}
    seen: set[str] = set()
    splits: dict[str, list[Json]] = {"calibration": [], "test": []}
    for item in evaluation.get("items", []):
        source, split = item.get("source_version"), item.get("split")
        group = item.get("group")
        if (source not in scored or source in seen or split not in splits or not isinstance(group, str)
                or not group.strip() or type(item.get("relevant")) is not bool
                or not item.get("reviewer") or not item.get("reason") or item.get("reviewer_type") != "human"):
            raise ResearchError("Gold labels need distinct in-frame sources, human reviewers, rationale, group and split")
        seen.add(source)
        if group in groups and groups[group] != split:
            raise ResearchError("Related reporting group leaks across calibration and held-out splits")
        groups[group] = split
        if scored[source]["score"] is None:
            raise ResearchError("All calibration and test articles must be fully processed; missing is not negative")
        splits[split].append({**item, "score": scored[source]["score"]})
    for items in splits.values():
        if any(sum(item["relevant"] == label for item in items) < minimum for label in (True, False)):
            raise ResearchError("Each evaluation split needs the registered minimum of both classes")
    # Only calibration scores choose candidates and the winner. Test labels cannot tune the cutoff.
    thresholds = sorted({1.0, *(i["score"] for i in splits["calibration"] if i["score"] > 0)})
    curve = [metrics(splits["calibration"], value, beta) for value in thresholds]
    best = max(curve, key=lambda m: (m["f_beta"], m["recall"], m["precision"], m["threshold"]))
    held_out = metrics(splits["test"], best["threshold"], beta)
    passed = held_out["precision"] >= required[0] and held_out["recall"] >= required[1]
    result = {"run": data["run"], "plan": run["plan"], "versions": context.versions,
              "threshold": best["threshold"], "comparison": "score >= threshold",
              "calibration": best, "test": held_out, "curve": curve, "splits": splits,
              "passed": passed, "expected_evaluation_articles": len(seen), "processed_evaluation_articles": len(seen),
              "rule": "Maximize registered F-beta; ties prefer recall, precision, then higher threshold",
              "scope": "Technical article relevance evaluation, not dossier counts or population inference",
              "limitations": "Reviewer identity, group independence and sample representativeness are self-asserted; no confidence intervals"}
    identifier = engine.ledger.record(session, "tag_calibration", digest(result), result)
    return {"id": identifier, **{k: v for k, v in result.items() if k not in {"curve", "splits"}}}


def apply(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    run = engine.ledger.get(data["run"], "tag_run")
    calibration = engine.ledger.get(data["calibration"], "tag_calibration")
    same_versions(run, context)
    same_versions(calibration, context)
    if calibration["plan"] != run["plan"] or not calibration["passed"]:
        raise ResearchError("Threshold must pass held-out requirements for this exact plan")
    articles = article_scores(engine, run)
    label = definition(engine, context)["tag"]
    for item in articles:
        item["tag"] = label
        item["value"] = item["score"] >= calibration["threshold"] if item["score"] is not None else None
        item["status"] = "provisional" if item["value"] is not None else "unprocessed"
    result = {"run": data["run"], "calibration": data["calibration"], "versions": context.versions,
              "threshold": calibration["threshold"], "comparison": "score >= threshold", "articles": articles,
              "expected_articles": len(articles), "processed_articles": sum(i["value"] is not None for i in articles),
              "missing_articles": sum(i["value"] is None for i in articles),
              "scope": "Provisional binary article tags; missing stays null; not accepted dossier findings"}
    identifier = engine.ledger.record(session, "tag_labels", digest(result), result)
    return {"id": identifier, **{k: v for k, v in result.items() if k != "articles"}}
