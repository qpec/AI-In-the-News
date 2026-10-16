"""Pure strong-anchor cross-window proposals; never mutate event memberships."""
from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations, product
from typing import Any
from urllib.parse import urlsplit

from .common import digest
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES, _feature
from .event_rule_application import complete_link_groups, publication_coverage

Json = dict[str, Any]
METHOD = "exact-provider-complete-cross-feature-group-links-v1"


def _domain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            return None
        return hostname[4:] if hostname.startswith("www.") else hostname
    except ValueError:
        return None


def propose(groups: list[Json], scored: list[Json], metadata: Json,
            provider_ids: dict[str, str | None], rule: Json) -> Json:
    """Require a full provider anchor and every strong cross-article comparison."""
    current = sorted((group for group in groups if len(group["members"]) >= 2), key=lambda row: row["group_id"])
    ids = [item for group in current for item in group["members"]]
    if (len(set(ids)) != len(ids) or len({group["group_id"] for group in current}) != len(current)
            or any(not isinstance(item, str) or not item for item in ids)):
        raise ValueError("current multi-article groups must partition unique article IDs")
    coverage = publication_coverage(ids, {item: metadata.get(item, {}).get("published_at") for item in ids})
    if coverage["missing_date_ids"]:
        raise ValueError("current group members require usable publication dates")
    dates = coverage["valid_dates"]
    no_date_rule = {**rule, "publication_gap_days": None}
    # Validate the frozen rule even when the candidate frame is empty.
    predicts({"features": dict.fromkeys(FEATURES, 1.)}, no_date_rule)
    lookup: dict[tuple[str, str], Json] = {}
    for row in scored:
        left, right = row.get("left"), row.get("right")
        if not isinstance(left, str) or not isinstance(right, str) or not left or not right or left == right:
            raise ValueError("scored pairs require distinct nonempty article IDs")
        pair = (left, right) if left < right else (right, left)
        if pair in lookup or row.get("pair_id") != digest(list(pair)):
            raise ValueError("duplicate or noncanonical scored pair identity")
        lookup[pair] = row

    status_counts: Counter[str] = Counter()
    anchored: dict[str, list[Json]] = defaultdict(list)
    group_anchors = []
    for group in current:
        members = sorted(group["members"])
        values = [provider_ids.get(item) for item in members]
        populated = [value for value in values if isinstance(value, str) and value.strip()]
        unique = sorted(set(populated))
        status = ("conflicting" if len(unique) > 1 else "missing" if not populated
                  else "partial" if len(populated) != len(members) else "fully_anchored")
        status_counts[status] += 1
        group_anchors.append({"group_id": group["group_id"], "members": members,
                              "member_count": len(members), "status": status,
                              "provider_status": status, "populated_members": len(populated),
                              "populated_ids_count": len(populated), "provider_values": unique,
                              "distinct_provider_uris": unique})
        if status == "fully_anchored":
            anchored[unique[0]].append(group)

    candidate_rows: list[Json] = []
    qualified: list[Json] = []
    reason_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    for provider_uri in sorted(anchored):
        for first, second in combinations(anchored[provider_uri], 2):
            left, right = sorted(first["members"]), sorted(second["members"])
            union = sorted(left + right)
            span = (max(dates[item] for item in union) - min(dates[item] for item in union)).days
            if span <= 7:
                continue
            domains = sorted({domain for item in union if (domain := _domain(metadata.get(item, {}).get("url")))})
            bodies = sorted({body for item in union
                             if isinstance(body := metadata.get(item, {}).get("body_sha256"), str) and body})
            reasons = []
            if len(domains) < 2:
                reasons.append("insufficient_distinct_domains")
            if len(bodies) < 2:
                reasons.append("insufficient_distinct_bodies")
            counts: Counter[str] = Counter()
            weakest: dict[str, float | None] = dict.fromkeys(FEATURES)
            for a, b in product(left, right):
                pair = (a, b) if a < b else (b, a)
                score_row = lookup.get(pair)
                if score_row is None:
                    counts["missing_row"] += 1
                    continue
                processing_status = score_row.get("status")
                if processing_status != "completed":
                    counts[processing_status if processing_status in {"failed", "pending", "unknown"}
                           else "invalid_status"] += 1
                    continue
                features = {feature: _feature(score_row, feature) for feature in FEATURES}
                if any(value is None for value in features.values()):
                    counts["missing_or_invalid_features"] += 1
                    continue
                counts["completed"] += 1
                for feature, value in features.items():
                    if value is not None:
                        previous = weakest[feature]
                        weakest[feature] = value if previous is None else min(previous, value)
                if predicts(score_row, no_date_rule):
                    counts["passing"] += 1
                else:
                    counts["below_feature_cutoff"] += 1
            expected = len(left) * len(right)
            reasons.extend(key for key in sorted(counts) if key not in {"completed", "passing"} and counts[key])
            reason_counts.update(reasons)
            pair_counts.update(counts)
            row = {"left_group_id": first["group_id"], "right_group_id": second["group_id"],
                   "left_members": left, "right_members": right, "article_members": union,
                   "provider_uri": provider_uri, "provider_populated_members": len(union),
                   "provider_total_members": len(union), "distinct_domains": domains,
                   "distinct_body_families": bodies, "publication_span_days": span,
                   "expected_cross_pair_count": expected, "completed_cross_pair_count": counts["completed"],
                   "passing_cross_pair_count": counts["passing"], "cross_pair_counts": dict(sorted(counts.items())),
                   "weakest_cross_features": weakest, "reasons": reasons,
                   "qualified": not reasons and counts["passing"] == expected,
                   "status": "unjudged", "accepted": False}
            candidate_rows.append(row)
            if row["qualified"]:
                node_pair = sorted((first["group_id"], second["group_id"]))
                qualified.append({"left": node_pair[0], "right": node_pair[1],
                                  "pair_id": digest(node_pair), "status": "completed",
                                  "features": {"pooled_cosine": weakest["pooled_cosine"]}})
    grouped = complete_link_groups([group["group_id"] for group in current], qualified)
    by_id = {group["group_id"]: group for group in current}
    proposals = []
    qualified_pairs = {tuple(sorted((row["left"], row["right"]))) for row in qualified}
    for group in grouped["groups"]:
        previous_ids = sorted(group["members"])
        if len(previous_ids) < 2:
            continue
        if any(tuple(pair) not in qualified_pairs for pair in combinations(previous_ids, 2)):
            raise ValueError("group-link proposal contains an unsupported transitive link")
        union = sorted(item for key in previous_ids for item in by_id[key]["members"])
        proposal_values = {provider_ids[item] for item in union}
        if len(proposal_values) != 1:
            raise ValueError("proposal lost the exact full-coverage provider anchor")
        proposals.append({"proposal_id": digest({"method": METHOD, "old_group_ids": previous_ids}),
                          "old_group_ids": previous_ids, "article_members": union,
                          "publication_span_days": (max(dates[item] for item in union)
                                                    - min(dates[item] for item in union)).days,
                          "provider_uri": next(iter(proposal_values)), "status": "unjudged", "accepted": False})
    return {"candidate_rows": candidate_rows, "proposals": proposals, "group_anchors": group_anchors,
            "diagnostics": {"multi_article_groups": len(current),
                            **{f"{key}_groups": status_counts[key]
                               for key in ("fully_anchored", "partial", "conflicting", "missing")},
                            "frame_pairs": len(candidate_rows), "qualified_pairs": len(qualified),
                            "proposals": len(proposals), "reason_counts": dict(sorted(reason_counts.items())),
                            "cross_pair_counts": dict(sorted(pair_counts.items())),
                            "diversity_failed_pairs": sum(any(reason.startswith("insufficient_")
                                                              for reason in row["reasons"]) for row in candidate_rows),
                            "qualified_bridges_retained": len(grouped["bridges"]),
                            "current_memberships_changed": 0, "accepted_dossiers": 0}}
