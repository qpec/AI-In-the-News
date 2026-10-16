"""Source-free planning/statistics for an audited, separate Luna lead study.

These helpers do not inspect evidence, retrieve sources, dispatch models or grant
authorization. A research adapter must freeze their inputs/outputs in protected
storage through Research.execute before judging. SHA-256 rank sampling is a
deterministic pseudorandom approximation to SRS without replacement: n/N is its
nominal inclusion probability under exchangeable hash ranks, not independently
certified randomization. Register the seed before examining labels.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

GROUP_LABELS = frozenset({"same_event", "mixed", "uncertain", "failed", "pending"})
PAIR_LABELS = frozenset({"same_event", "different_event", "uncertain", "failed", "pending"})
SAMPLING_METHOD = "sha256-rank-without-replacement-v1"


def _ids(values: Sequence[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("Identifiers must be a sequence, not a string")
    result = list(values)
    if any(not isinstance(value, str) or not value.strip() for value in result):
        raise ValueError("Identifiers must be nonblank strings")
    if len(set(result)) != len(result):
        raise ValueError("Duplicate identifiers are not allowed")
    return sorted(result)


def _rank(seed: str, domain: str, identifier: str) -> str:
    if not isinstance(seed, str) or not seed.strip():
        raise ValueError("A preregistered nonblank seed is required")
    payload = json.dumps([seed, domain, identifier], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sample(frame: Sequence[str], requested: int, seed: str, domain: str) -> dict[str, Any]:
    if type(requested) is not int or requested < 0:
        raise ValueError("Requested sample size must be a nonnegative integer")
    ids = _ids(frame)
    _rank(seed, domain, "seed-validation")
    selected = sorted(ids, key=lambda item: (_rank(seed, domain, item), item))[:requested]
    size, drawn = len(ids), len(selected)
    half_width = None
    if drawn:
        correction = math.sqrt((size - drawn) / (size - 1)) if size > 1 else 0.0
        half_width = 1.959963984540054 * math.sqrt(0.25 / drawn) * correction
    return {"N": size, "n": drawn, "requested_n": requested,
            "pi": drawn / size if size else None, "frame_ids": ids, "selected_ids": selected,
            "sampling_method": SAMPLING_METHOD, "seed": seed, "domain": domain,
            "planning_worst_case_95_half_width": half_width,
            "planning_interval_warning": "Normal/FPC planning diagnostic, not an exact design interval"}


def sample_validation_frames(
    groups: Mapping[str, Sequence[str]], *, seed: str,
    group_sample_size: int = 300, anchor_sample_size: int = 100,
) -> dict[str, Any]:
    """Select complete multi-article groups and article anchors including singletons.

    Oversized groups are never replaced or truncated. Realized exposure counts
    must be checked separately before dispatch. A smaller frame is a census.
    """
    group_ids = _ids(list(groups))
    membership: dict[str, str] = {}
    members: dict[str, list[str]] = {}
    for group in group_ids:
        current = _ids(groups[group])
        if not current:
            raise ValueError("Frozen groups cannot be empty")
        for article in current:
            if article in membership:
                raise ValueError("An article cannot occur in multiple frozen groups")
            membership[article] = group
        members[group] = current
    selected_groups = _sample([group for group in group_ids if len(members[group]) >= 2],
                              group_sample_size, seed, "complete-group")
    anchors = _sample(list(membership), anchor_sample_size, seed, "article-anchor")
    return {"group_frame": selected_groups, "anchor_frame": anchors,
            "selected_group_members": {group: members[group] for group in selected_groups["selected_ids"]},
            "frozen_membership": membership,
            "sample_replacement": False, "new_study_budget_required": True,
            "sampling_warning": "Fixed-seed SHA ranks approximate SRS; pi assumes exchangeable ranks"}


def build_anchor_candidates(
    anchor: str, membership: Mapping[str, str], *, pooled_vector_ids: Sequence[str],
    keyword_ids: Sequence[str], provider_ids: Sequence[str], seed: str, outside_controls: int = 2,
) -> dict[str, Any]:
    """Union supplied retrieval channels, all co-members and outside-pool controls.

    Retrieval itself belongs in the audited adapter. The adapter must bind each
    channel's search parameters/results, including its broader temporal scope.
    Random controls do not establish exhaustive candidate coverage or recall.
    """
    if anchor not in membership:
        raise ValueError("Anchor must belong to the frozen article frame")
    article_ids = _ids(list(membership))
    channels: dict[str, set[str]] = {}
    supplied = {"pooled_vector": pooled_vector_ids, "keyword": keyword_ids, "provider_id": provider_ids,
                "frozen_group": [item for item in article_ids if membership[item] == membership[anchor]]}
    for channel, values in supplied.items():
        for item in _ids(values):
            if item not in membership:
                raise ValueError("Candidate must belong to the frozen article frame")
            if item != anchor:
                channels.setdefault(item, set()).add(channel)
    outside = [item for item in article_ids if item != anchor and item not in channels]
    controls = _sample(outside, outside_controls, seed, "outside-control:" + anchor)
    for item in controls["selected_ids"]:
        channels[item] = {"outside_control"}
    return {"anchor": anchor,
            "candidates": [{"candidate": item, "channels": sorted(channels[item])} for item in sorted(channels)],
            "outside_controls": controls, "exhaustive_retrieval": False,
            "recall_scope": "Frozen examined candidate pool only; not full-corpus recall"}


def realized_workload(
    selected_group_members: Mapping[str, Sequence[str]], candidate_frames: Sequence[Mapping[str, Any]],
    *, max_primary_requests: int = 400, max_article_exposures: int = 6000,
) -> dict[str, Any]:
    """Count repeated article exposures across tasks, without authorizing execution."""
    group_ids = _ids(list(selected_group_members))
    group_exposures = sum(len(_ids(selected_group_members[group])) for group in group_ids)
    anchor_ids = _ids([frame["anchor"] for frame in candidate_frames])
    anchor_exposures = sum(1 + len(_ids([row["candidate"] for row in frame["candidates"]]))
                           for frame in candidate_frames)
    for limit in (max_primary_requests, max_article_exposures):
        if type(limit) is not int or limit <= 0:
            raise ValueError("Exposure and request limits must be positive integers")
    requests = len(group_ids) + len(anchor_ids)
    exposures = group_exposures + anchor_exposures
    return {"primary_requests": requests, "group_requests": len(group_ids), "anchor_requests": len(anchor_ids),
            "group_article_exposures": group_exposures, "anchor_article_exposures": anchor_exposures,
            "article_exposures": exposures, "max_primary_requests": max_primary_requests,
            "max_article_exposures": max_article_exposures, "automatic_retries": 0,
            "within_budget": requests <= max_primary_requests and exposures <= max_article_exposures,
            "authorization_granted": False}


def _wilson(successes: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = 1.959963984540054
    estimate = successes / count
    divisor = 1 + z * z / count
    center = (estimate + z * z / (2 * count)) / divisor
    radius = z * math.sqrt(estimate * (1 - estimate) / count + z * z / (4 * count * count)) / divisor
    return [max(0.0, center - radius), min(1.0, center + radius)]


def group_precision(selected_group_ids: Sequence[str], judgments: Mapping[str, str]) -> dict[str, Any]:
    """Strict entire-group model-reference precision; missing results stay pending."""
    groups = _ids(selected_group_ids)
    if set(judgments) - set(groups):
        raise ValueError("Judgment outside the selected group frame")
    labels = [judgments.get(group, "pending") for group in groups]
    if any(label not in GROUP_LABELS for label in labels):
        raise ValueError("Unsupported group judgment label")
    counts = {label: labels.count(label) for label in sorted(GROUP_LABELS)}
    positive, negative = counts["same_event"], counts["mixed"]
    complete = positive + negative
    unknown = len(groups) - complete
    return {"estimand": "Strict entire-group macro precision against lead-only model references",
            "expected_groups": len(groups), "counts": counts, "complete_groups": complete,
            "unknown_groups": unknown,
            "identified_bounds": {"lower": positive / len(groups) if groups else None,
                                  "upper": (positive + unknown) / len(groups) if groups else None},
            "complete_case_precision": positive / complete if complete else None,
            "complete_case_wilson_95": _wilson(positive, complete),
            "interval_warning": "Complete-case binomial Wilson diagnostic; no FPC or model-error adjustment",
            "human_validated": False, "pair_precision": None,
            "pair_precision_status": "Unsupported without actual article-pair reference relations"}


def _quantile(values: Sequence[float], probability: float) -> float:
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def candidate_pool_recall(
    anchor_ids: Sequence[str], relations: Sequence[Mapping[str, str]], membership: Mapping[str, str],
    *, bootstrap_seed: str, bootstrap_replicates: int = 2000,
) -> dict[str, Any]:
    """Capture of known same-event pairs within the frozen examined candidate pool.

    The ratio pools anchor-candidate pairs, so it is not an equal-event or
    equal-anchor mean. Resampling whole anchors preserves within-anchor
    dependence; the percentile interval ignores model error and finite-population
    correction. Candidate rows (including pending ones) must cover the entire
    preregistered pool. These helpers cannot verify that external pool artifact.
    """
    anchors = _ids(anchor_ids)
    if type(bootstrap_replicates) is not int or not 1000 <= bootstrap_replicates <= 100000:
        raise ValueError("Use 1000 to 100000 anchor bootstrap replicates")
    if any(anchor not in membership for anchor in anchors):
        raise ValueError("Anchor missing from frozen membership")
    _rank(bootstrap_seed, "anchor-bootstrap", "seed-validation")
    totals = {anchor: Counter({"same_inside": 0, "same_outside": 0,
                               "unknown_inside": 0, "unknown_outside": 0}) for anchor in anchors}
    labels = Counter({label: 0 for label in PAIR_LABELS})
    seen: set[tuple[str, str]] = set()
    for row in relations:
        anchor, candidate, label = row["anchor"], row["candidate"], row["label"]
        if anchor not in totals or candidate not in membership or candidate == anchor:
            raise ValueError("Relation outside the frozen non-self candidate frame")
        if (anchor, candidate) in seen:
            raise ValueError("Duplicate anchor-candidate relation")
        if label not in PAIR_LABELS:
            raise ValueError("Unsupported pair judgment label")
        seen.add((anchor, candidate))
        labels[label] += 1
        side = "inside" if membership[anchor] == membership[candidate] else "outside"
        if label == "same_event":
            totals[anchor]["same_" + side] += 1
        elif label != "different_event":
            totals[anchor]["unknown_" + side] += 1
    group_members: dict[str, set[str]] = {}
    for article, group in membership.items():
        group_members.setdefault(group, set()).add(article)
    for anchor in anchors:
        required = group_members[membership[anchor]] - {anchor}
        if any((anchor, candidate) not in seen for candidate in required):
            raise ValueError("Candidate pool must retain all frozen co-members, including pending judgments")
    overall: Counter[str] = Counter()
    for item in totals.values():
        overall.update(item)
    inside, outside = overall["same_inside"], overall["same_outside"]
    uncertain_inside, uncertain_outside = overall["unknown_inside"], overall["unknown_outside"]
    known = inside + outside
    lower: float | None
    upper: float | None
    if known:
        lower = inside / (known + uncertain_outside)
        upper = (inside + uncertain_inside) / (known + uncertain_inside)
    elif uncertain_inside or uncertain_outside:
        lower = 0.0 if uncertain_outside else 1.0
        upper = 1.0 if uncertain_inside else 0.0
    else:
        lower = upper = None
    rng = random.Random(int(_rank(bootstrap_seed, "anchor-bootstrap", "random"), 16))
    bootstrap: list[float] = []
    if len(anchors) >= 2:
        values = list(totals.values())
        for _ in range(bootstrap_replicates):
            sampled = [values[rng.randrange(len(values))] for _ in values]
            hit = sum(item["same_inside"] for item in sampled)
            missed = sum(item["same_outside"] for item in sampled)
            if hit + missed:
                bootstrap.append(hit / (hit + missed))
    bootstrap.sort()
    interval = ([_quantile(bootstrap, 0.025), _quantile(bootstrap, 0.975)]
                if len(bootstrap) >= math.ceil(bootstrap_replicates * 0.95) else None)
    return {"estimand": "Anchor-candidate pair-ratio recall within the examined candidate pool",
            "expected_anchors": len(anchors), "candidate_pairs": len(seen), "counts": dict(sorted(labels.items())),
            "same_event_inside": inside, "same_event_outside": outside,
            "unknown_inside": uncertain_inside, "unknown_outside": uncertain_outside,
            "complete_case_candidate_pool_recall": inside / known if known else None,
            "identified_bounds": {"lower": lower, "upper": upper,
                                  "conditional_on_nonzero_same_event_denominator": True},
            "zero_denominator_possible": known == 0,
            "anchor_totals": {anchor: dict(totals[anchor]) for anchor in anchors},
            "bootstrap": {"method": "percentile-resample-whole-anchors-v1", "seed": bootstrap_seed,
                          "requested_replicates": bootstrap_replicates,
                          "defined_replicates": len(bootstrap), "complete_case_95": interval},
            "interval_warning": "Diagnostic anchor bootstrap; ignores model error/FPC and may degenerate at boundaries",
            "human_validated": False, "full_corpus_recall": None,
            "full_corpus_recall_status": "Not estimable from this retrieved candidate pool"}
