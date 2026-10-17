"""Deterministic, side-effect-free saved-metadata event candidate generation.

Call this helper only from a registered audited operation for real research.
Its proposals never modify provider fields or accept event memberships.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import re
import unicodedata
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from .common import Json, ResearchError, digest

METHOD = "nl-cyber-saved-event-matching-v1"
POLICY: Json = {
    "method": METHOD,
    "anchors": "Latest nonblank string eventUri; exclude multiple distinct historical populated IDs",
    "query_fields": ["uri", "date", "title", "body", "url", "originalArticle", "duplicateList", "storyUri"],
    "maximum_publication_gap_days": 7,
    "direct_signals": ["provider_duplicate_reference_both_directions", "exact_story_uri", "exact_url", "exact_normalized_body"],
    "body_normalization": "Unicode NFC then collapse whitespace; preserve case and punctuation",
    "minimum_exact_body_characters": 300,
    "minimum_exact_body_words": 60,
    "url_normalization": "None: exact nonblank original string",
    "title_alone": False,
    "conflicting_direct_event_ids": "Abstain, retain all alternatives; do not resolve lexically",
    "transitive_propagation": False,
    "lexical_input": "title + newline + first 4000 Unicode characters of permitted body",
    "vectorizer": {"analyzer": "word", "ngram_range": [1, 2], "lowercase": True,
        "min_df": 2, "max_features": 60000, "sublinear_tf": True, "norm": "l2"},
    "lexical_fit": "Eligible anchor text only; refit without held-out rows for diagnostic",
    "lexical_event_aggregation": "Maximum cosine; tie by anchor URI; return top three distinct event IDs",
    "strong_lexical_rule": {"minimum_cosine": 0.85, "minimum_other_event_margin": 0.10,
        "minimum_title_token_jaccard": 0.50, "minimum_title_tokens_each": 3},
    "title_tokens": "NFC/casefold Unicode word tokens, unique; punctuation excluded",
    "holdout": {"hash_prefix": "nl-cyber-event-matching-v1|", "sha256_integer_modulus": 5,
        "held_out_remainder": 0, "purpose": "Provider-label agreement, not real-world accuracy"},
    "adoption": "All matches are provisional and unreviewed; no eventUri or membership changes",
    "network_calls": 0, "model_calls": 0, "newsapi_tokens": 0,
}
PROPOSED = frozenset({"proposed_same_text", "proposed_provider_duplicate_link", "proposed_same_story", "proposed_same_url",
    "proposed_lexical"})
STATUS_ORDER = ["proposed_same_text", "proposed_provider_duplicate_link", "proposed_same_story", "proposed_same_url",
    "proposed_lexical", "conflict", "review_only", "unmatchable"]


def event_state(article: Json) -> str:
    if "eventUri" not in article:
        return "absent"
    value = article["eventUri"]
    if value is None:
        return "null"
    if not isinstance(value, str):
        return "invalid_type"
    return "populated" if value.strip() else "empty"


def _normalized(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def _field_type(article: Json, key: str) -> str:
    if key not in article:
        return "absent"
    value = article[key]
    if value is None:
        return "null"
    if isinstance(value, str):
        return "nonblank_string" if value.strip() else "blank_string"
    return "object" if isinstance(value, dict) else "array" if isinstance(value, list) else "other"


def _reference(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("uri")
    return value if isinstance(value, str) and value.strip() else None


def _source_observation(row: Json) -> Json:
    value = row.get("event_metadata", {}).get("selected_observation")
    if not isinstance(value, dict):
        value = row.get("base_observation", {})
    return {key: value[key] for key in ("receipt", "receipt_kind", "path", "record_hash",
        "retrieved_at", "created_event") if key in value}


@dataclass(frozen=True)
class _Query:
    """Explicit feature whitelist: there are no labels or histories in queries."""
    uri: str
    source_hash: str
    published: date | None
    year: str
    title: str
    title_tokens: frozenset[str]
    text: str
    has_body: bool
    url: str | None
    body_hash: str | None
    story_uri: str | None


@dataclass(frozen=True)
class _Anchor:
    query: _Query
    event_uri: str
    source_observation: Json


def _prepare(rows: list[Json]) -> tuple[dict[str, _Query], dict[str, str], dict[str, str],
        dict[str, _Anchor], dict[str, list[Json]], Json]:
    queries: dict[str, _Query] = {}
    labels: dict[str, str] = {}
    states: dict[str, str] = {}
    anchors: dict[str, _Anchor] = {}
    reference_rows: list[Json] = []
    fields: dict[str, Counter[str]] = {key: Counter() for key in (
        "eventUri", "originalArticle", "duplicateList", "storyUri", "url", "body", "date")}
    refs: Counter[str] = Counter()
    excluded_history = 0
    for row in rows:
        article = row.get("article")
        if not isinstance(article, dict):
            raise ResearchError("Event matching requires repaired article wrappers")
        uri = article.get("uri")
        if not isinstance(uri, str) or not uri.strip() or uri in queries:
            raise ResearchError("Event matching requires unique nonblank article URIs")
        source_hash = row.get("source_hash")
        if not isinstance(source_hash, str) or source_hash != digest(article):
            raise ResearchError("Event matching article hash disagrees with the repaired source")
        for key, counts in fields.items():
            counts[_field_type(article, key)] += 1
        value = article.get("date")
        try:
            published = date.fromisoformat(value) if isinstance(value, str) else None
        except ValueError:
            published = None
        title_value, body_value = article.get("title"), article.get("body")
        title = title_value if isinstance(title_value, str) else ""
        body = body_value if isinstance(body_value, str) else ""
        # Quarantined records may never supply text, even in an invalid wrapper.
        if article.get("quarantined") and body.strip():
            raise ResearchError("Quarantined article unexpectedly contains body text")
        normalized_body = _normalized(body)
        body_hash = hashlib.sha256(normalized_body.encode()).hexdigest() if (
            len(normalized_body) >= 300 and len(normalized_body.split()) >= 60) else None
        url = article.get("url")
        story = article.get("storyUri")
        query = _Query(uri, source_hash, published, str(published.year) if published else "unknown",
            title, frozenset(re.findall(r"\w+", unicodedata.normalize("NFC", title).casefold())),
            title + "\n" + body[:4000], bool(body.strip()),
            url if isinstance(url, str) and url.strip() else None, body_hash,
            story if isinstance(story, str) and story.strip() else None)
        queries[uri] = query
        state = event_state(article)
        states[uri] = state
        if state == "populated":
            label = article["eventUri"]
            labels[uri] = label
            history = row.get("event_metadata", {}).get("observed_event_ids", [])
            if not isinstance(history, list) or any(not isinstance(item, str) or not item.strip() for item in history):
                raise ResearchError("Event matching requires well-formed saved event-ID history")
            if len(set(history) | {label}) > 1:
                excluded_history += 1
            else:
                anchors[uri] = _Anchor(query, label, _source_observation(row))
        for field in ("originalArticle", "duplicateList"):
            if field not in article or article[field] is None:
                continue
            entries = article[field] if field == "duplicateList" else [article[field]]
            if not isinstance(entries, list):
                refs[f"{field}_malformed_containers"] += 1
                continue
            for position, entry in enumerate(entries):
                target = _reference(entry)
                if target is None:
                    refs[f"{field}_malformed_references"] += 1
                    continue
                refs[f"{field}_parsed_references"] += 1
                reference_rows.append({"from_article_uri": uri, "to_article_uri": target,
                    "field": field, "position": position, "source_hash": source_hash})
    edges: dict[str, list[Json]] = defaultdict(list)
    for item in reference_rows:
        source, target = item["from_article_uri"], item["to_article_uri"]
        if source == target:
            refs["self_references"] += 1
        elif target not in queries:
            refs["out_of_frame_references"] += 1
        else:
            refs["in_frame_references"] += 1
            edges[source].append(item)
            edges[target].append(item)
    inventory = {"fields": {key: dict(sorted(value.items())) for key, value in fields.items()},
        "references": dict(sorted(refs.items())), "conflicting_history_anchor_exclusions": excluded_history,
        "date_unavailable": sum(item.published is None for item in queries.values()),
        "body_unavailable": sum(not item.has_body for item in queries.values()),
        "exact_body_eligible": sum(item.body_hash is not None for item in queries.values())}
    sorted_edges = {uri: sorted(items, key=lambda item: (
        item["from_article_uri"], item["to_article_uri"], item["field"], item["position"]))
        for uri, items in edges.items()}
    return queries, labels, states, anchors, sorted_edges, inventory


class _Index:
    def __init__(self, anchors: dict[str, _Anchor], edges: dict[str, list[Json]]) -> None:
        self.anchors = anchors
        self.edges = edges
        self.ordered = [anchors[key] for key in sorted(anchors)]
        self.by_body: dict[str, list[_Anchor]] = defaultdict(list)
        self.by_url: dict[str, list[_Anchor]] = defaultdict(list)
        self.by_story: dict[str, list[_Anchor]] = defaultdict(list)
        self.by_day: dict[int, list[int]] = defaultdict(list)
        for index, anchor in enumerate(self.ordered):
            item = anchor.query
            if item.body_hash:
                self.by_body[item.body_hash].append(anchor)
            if item.url:
                self.by_url[item.url].append(anchor)
            if item.story_uri:
                self.by_story[item.story_uri].append(anchor)
            if item.published:
                self.by_day[item.published.toordinal()].append(index)
        self.vectorizer: Any = None
        self.matrix: Any = None
        text_anchors = [item for item in self.ordered if item.query.has_body]
        self.lexical_anchor_positions = [index for index, item in enumerate(self.ordered) if item.query.has_body]
        self.lexical_position = {original: position for position, original in enumerate(self.lexical_anchor_positions)}
        self.fit_status = "no_body_anchors"
        self.fit_fingerprint: str | None = None
        if len(text_anchors) < 2:
            self.fit_status = "fewer_than_two_body_anchors"
            return
        vectorizer = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), lowercase=True, min_df=2,
            max_features=60000, sublinear_tf=True, norm="l2", dtype=np.float64)
        try:
            matrix = vectorizer.fit_transform([item.query.text for item in text_anchors])
        except ValueError as exc:
            if "empty vocabulary" not in str(exc) and "no terms remain" not in str(exc).lower():
                raise
            self.fit_status = "empty_vocabulary_after_min_df"
            return
        self.vectorizer, self.matrix = vectorizer, matrix
        self.fit_status = "fitted"
        self.fit_fingerprint = digest({"vocabulary": {word: int(value) for word, value in vectorizer.vocabulary_.items()},
            "idf": vectorizer.idf_.tolist(),
            "anchor_uris": [item.query.uri for item in text_anchors]})

    def nearby(self, target: _Query) -> list[int]:
        if target.published is None:
            return []
        day = target.published.toordinal()
        return sorted(index for day_value in range(day - 7, day + 8) for index in self.by_day.get(day_value, []))

    @staticmethod
    def anchor_evidence(anchor: _Anchor, target: _Query, evidence: list[Json]) -> Json:
        assert target.published is not None and anchor.query.published is not None
        return {"article_uri": anchor.query.uri, "url": anchor.query.url, "source_hash": anchor.query.source_hash,
            "source_observation": anchor.source_observation,
            "publication_gap_days": abs((target.published - anchor.query.published).days),
            "evidence": evidence}

    def direct(self, target: _Query) -> list[Json]:
        evidence: dict[str, list[Json]] = defaultdict(list)
        if target.body_hash:
            for anchor in self.by_body.get(target.body_hash, []):
                evidence[anchor.query.uri].append({"type": "same_text", "normalized_body_sha256": target.body_hash})
        if target.url:
            for anchor in self.by_url.get(target.url, []):
                evidence[anchor.query.uri].append({"type": "same_url", "url": target.url})
        if target.story_uri:
            for anchor in self.by_story.get(target.story_uri, []):
                evidence[anchor.query.uri].append({"type": "same_story", "story_uri": target.story_uri})
        for edge in self.edges.get(target.uri, []):
            other = edge["to_article_uri"] if edge["from_article_uri"] == target.uri else edge["from_article_uri"]
            if other in self.anchors:
                evidence[other].append({"type": "provider_duplicate_link", **edge})
        events: dict[str, list[Json]] = defaultdict(list)
        for uri in sorted(evidence):
            anchor = self.anchors[uri]
            if uri == target.uri or target.published is None or anchor.query.published is None:
                continue
            if abs((target.published - anchor.query.published).days) > 7:
                continue
            events[anchor.event_uri].append(self.anchor_evidence(anchor, target, evidence[uri]))
        return [{"event_uri": event, "score": None,
            "evidence_types": sorted({entry["type"] for anchor in anchors for entry in anchor["evidence"]}),
            "anchor_uri": anchors[0]["article_uri"], "url": anchors[0]["url"], "anchors": anchors}
            for event, anchors in sorted(events.items())]

    def lexical(self, targets: list[_Query]) -> dict[str, list[Json]]:
        if self.vectorizer is None:
            return {}
        by_day: dict[int, list[_Query]] = defaultdict(list)
        for target in targets:
            if target.has_body and target.published:
                by_day[target.published.toordinal()].append(target)
        results: dict[str, list[Json]] = {}
        for day in sorted(by_day):
            day_targets = sorted(by_day[day], key=lambda item: item.uri)
            original_positions = [position for position in self.nearby(day_targets[0])
                if position in self.lexical_position]
            if not original_positions:
                continue
            positions = [self.lexical_position[position] for position in original_positions]
            for start in range(0, len(day_targets), 256):
                block = day_targets[start:start + 256]
                scores = (self.vectorizer.transform([item.text for item in block]) @ self.matrix[positions].T).tocsr()
                for offset, target in enumerate(block):
                    values = scores.getrow(offset)
                    best: dict[str, Json] = {}
                    for local_position, score in zip(values.indices.tolist(), values.data.tolist(), strict=True):
                        if score <= 0:
                            continue
                        anchor = self.ordered[original_positions[local_position]]
                        if anchor.query.uri == target.uri:
                            continue
                        intersection = len(target.title_tokens & anchor.query.title_tokens)
                        union = len(target.title_tokens | anchor.query.title_tokens)
                        jaccard = intersection / union if min(len(target.title_tokens), len(anchor.query.title_tokens)) >= 3 else 0.0
                        candidate = {"event_uri": anchor.event_uri, "score": min(1.0, float(score)),
                            "title_jaccard": jaccard, "evidence_types": ["lexical_tfidf"],
                            "anchor_uri": anchor.query.uri, "url": anchor.query.url,
                            "anchors": [self.anchor_evidence(anchor, target, [{"type": "lexical_tfidf"}])]}
                        prior = best.get(anchor.event_uri)
                        if prior is None or (-candidate["score"], candidate["anchor_uri"]) < (-prior["score"], prior["anchor_uri"]):
                            best[anchor.event_uri] = candidate
                    results[target.uri] = sorted(best.values(), key=lambda item: (-item["score"], item["event_uri"]))[:3]
        return results


def _predict(targets: list[_Query], anchors: dict[str, _Anchor], edges: dict[str, list[Json]]) -> tuple[list[Json], Json]:
    """Labels are unavailable here; query features are a strict whitelist."""
    index = _Index(anchors, edges)
    results: dict[str, Json] = {}
    lexical_targets = []
    for target in sorted(targets, key=lambda item: item.uri):
        direct = index.direct(target)
        nearby = index.nearby(target)
        output: Json = {"article_uri": target.uri, "source_hash": target.source_hash, "year": target.year,
            "url": target.url, "status": "unmatchable", "proposed_event_uri": None, "candidates": direct,
            "reason": None, "nearby_anchor_articles": len(nearby), "has_body": target.has_body,
            "lexical_retrieval_attempted": False, "lexical_scored": False,
            "exact_overlap": any(set(item["evidence_types"]) & {"same_text", "same_url"} for item in direct),
            "review_status": "unreviewed", "provider_assignment_changed": False}
        if len(direct) > 1:
            output.update(status="conflict", reason="Multiple directly supported provider IDs; abstained")
        elif direct:
            evidence = direct[0]["evidence_types"]
            status = next("proposed_" + name for name in (
                "same_text", "provider_duplicate_link", "same_story", "same_url") if name in evidence)
            output.update(status=status, proposed_event_uri=direct[0]["event_uri"], reason="Provisional direct-evidence match")
        elif target.published is None:
            output["reason"] = "Publication date unavailable; seven-day rule cannot be checked"
        elif not nearby:
            output["reason"] = "No eligible assigned anchor within seven publication days"
        elif not target.has_body:
            output["reason"] = "No direct match and no permitted body for lexical retrieval"
        else:
            output["lexical_retrieval_attempted"] = True
            output["lexical_scored"] = index.fit_status == "fitted" and any(
                position in index.lexical_position for position in nearby)
            lexical_targets.append(target)
        results[target.uri] = output
    lexical = index.lexical(lexical_targets)
    for target in lexical_targets:
        output = results[target.uri]
        candidates = lexical.get(target.uri, [])
        output["candidates"] = candidates
        if not candidates:
            output["reason"] = "No positive lexical similarity" if index.fit_status == "fitted" else index.fit_status
            continue
        top = candidates[0]
        margin = top["score"] - (candidates[1]["score"] if len(candidates) > 1 else 0.0)
        output["other_event_margin"] = margin
        strong = top["score"] >= 0.85 and margin >= 0.10 and top["title_jaccard"] >= 0.50
        output.update(status="proposed_lexical" if strong else "review_only",
            proposed_event_uri=top["event_uri"] if strong else None,
            reason="Unvalidated strong lexical rule" if strong else "Candidates below the provisional strong rule")
    fit = {"status": index.fit_status, "fingerprint": index.fit_fingerprint,
        "anchor_articles": len(anchors), "body_anchor_articles": len(index.lexical_anchor_positions),
        "vocabulary_size": len(index.vectorizer.vocabulary_) if index.vectorizer is not None else 0,
        "feature_fit_uses_targets": False}
    return [results[uri] for uri in sorted(results)], fit


def _counts(items: list[Json]) -> Json:
    counts = Counter(item["status"] for item in items)
    return {"target_articles": len(items), "candidate_articles": sum(bool(item["candidates"]) for item in items),
        "proposed_articles": sum(counts[status] for status in PROPOSED), "conflicts": counts["conflict"],
        "status_counts": {status: counts[status] for status in STATUS_ORDER},
        "lexical_queries_attempted": sum(item["lexical_retrieval_attempted"] for item in items),
        "lexical_scored_articles": sum(item["lexical_scored"] for item in items),
        "missing_text": sum(not item["has_body"] for item in items),
        "no_eligible_anchor_within_seven_days": sum(not item["nearby_anchor_articles"] for item in items)}


def _diagnostic(predictions: list[Json], expected: dict[str, str], anchors: dict[str, _Anchor],
        queries: dict[str, _Query]) -> Json:
    by_event: dict[str, list[date]] = defaultdict(list)
    for anchor in anchors.values():
        if anchor.query.published:
            by_event[anchor.event_uri].append(anchor.query.published)
    items = []
    for prediction in predictions:
        uri = prediction["article_uri"]
        label = expected[uri]
        published = queries[uri].published
        reachable = published is not None and any(abs((published - other).days) <= 7 for other in by_event[label])
        candidates = prediction["candidates"]
        # Direct conflicts have no ranking; alphabetical alternatives are not top-1.
        top = candidates[0]["event_uri"] if candidates and prediction["status"] != "conflict" else None
        proposed = prediction["proposed_event_uri"]
        stratum = "exact_text_or_url_overlap" if prediction["exact_overlap"] else (
            "direct_provider_reference_only" if prediction["status"] in {
                "proposed_provider_duplicate_link", "proposed_same_story"} else
            "lexical_only" if candidates and prediction["status"] != "conflict" else "no_ranked_candidate")
        items.append({**prediction, "expected_provider_event_uri": label, "same_id_anchor_reachable": reachable,
            "top1_provider_agreement": top == label if top is not None else None,
            "proposed_provider_agreement": proposed == label if proposed is not None else None,
            "expected_id_in_candidates": any(item["event_uri"] == label for item in candidates),
            "expected_id_in_top3": any(item["event_uri"] == label for item in candidates[:3])
                if prediction["status"] != "conflict" else None, "stratum": stratum})
    def summary(group: list[Json]) -> Json:
        top = [item for item in group if item["top1_provider_agreement"] is not None]
        proposed = [item for item in group if item["proposed_provider_agreement"] is not None]
        good = sum(bool(item["top1_provider_agreement"]) for item in top)
        pg = sum(bool(item["proposed_provider_agreement"]) for item in proposed)
        return {**_counts(group), "heldout_articles": len(group),
            "same_id_anchor_reachable": sum(item["same_id_anchor_reachable"] for item in group),
            "same_id_anchor_unreachable": sum(not item["same_id_anchor_reachable"] for item in group),
            "top1_available": len(top), "top1_agree": good, "top1_disagree": len(top) - good,
            "top1_unavailable": len(group) - len(top), "top1_provider_agreement_fraction": good / len(top) if top else None,
            "proposed_agree": pg, "proposed_disagree": len(proposed) - pg,
            "proposal_abstentions": len(group) - len(proposed),
            "proposed_provider_agreement_fraction": pg / len(proposed) if proposed else None,
            "expected_id_in_top3": sum(bool(item["expected_id_in_top3"]) for item in group),
            "expected_id_in_candidates": sum(item["expected_id_in_candidates"] for item in group),
            "real_world_event_accuracy": None}
    return {"per_item": items, "summary": summary(items),
        "strata": {name: summary([item for item in items if item["stratum"] == name]) for name in (
            "exact_text_or_url_overlap", "direct_provider_reference_only", "lexical_only", "no_ranked_candidate")},
        "strong_lexical": summary([item for item in items if item["status"] == "proposed_lexical"]),
        "reachable": summary([item for item in items if item["same_id_anchor_reachable"]]),
        "unreachable": summary([item for item in items if not item["same_id_anchor_reachable"]]),
        "years": {year: summary([item for item in items if item["year"] == year])
            for year in sorted({item["year"] for item in items})},
        "interpretation": "Provider-ID agreement on assigned articles; overlap is retained and disclosed. "
            "Reachable means a remaining eligible same-ID anchor within seven publication days. "
            "Not independent human accuracy, not validation for null-ID articles, and not event-dossier acceptance."}


def analyze(rows: list[Json]) -> Json:
    """Return deterministic provisional matches and a label-masked diagnostic."""
    queries, labels, states, anchors, edges, inventory = _prepare(rows)
    targets = [query for uri, query in queries.items() if uri not in labels]
    predictions, fit = _predict(targets, anchors, edges)
    for item in predictions:
        item["original_event_state"] = states[item["article_uri"]]
    heldout_ids = {uri for uri in labels if int(hashlib.sha256(
        (POLICY["holdout"]["hash_prefix"] + uri).encode()).hexdigest(), 16) % 5 == 0}
    remaining = {uri: anchor for uri, anchor in anchors.items() if uri not in heldout_ids}
    heldout_predictions, heldout_fit = _predict([queries[uri] for uri in sorted(heldout_ids)], remaining, edges)
    diagnostic = _diagnostic(heldout_predictions, {uri: labels[uri] for uri in heldout_ids}, remaining, queries)
    diagnostic["fit"] = heldout_fit
    diagnostic["heldout_uris"] = sorted(heldout_ids)
    diagnostic["anchor_uris"] = sorted(remaining)
    diagnostic["labels_available_to_predictor"] = False
    summary = {"total_articles": len(rows), "latest_assigned_articles": len(labels),
        "eligible_anchor_articles": len(anchors), **_counts(predictions),
        "conflicting_history_anchor_exclusions": inventory["conflicting_history_anchor_exclusions"],
        "accepted_assignments": 0, "provider_fields_changed": 0,
        "network_calls": 0, "model_calls": 0, "newsapi_tokens": 0}
    years = {}
    for year in sorted({item.year for item in queries.values()}):
        members = [uri for uri, query in queries.items() if query.year == year]
        years[year] = {"total_articles": len(members), "latest_assigned_articles": sum(uri in labels for uri in members),
            "eligible_anchor_articles": sum(uri in anchors for uri in members),
            **_counts([item for item in predictions if item["year"] == year])}
    examples = []
    for status in STATUS_ORDER:
        for item in [value for value in predictions if value["status"] == status][:3]:
            examples.append({key: item[key] for key in ("article_uri", "year", "url", "status", "proposed_event_uri", "reason")}
                | {"candidates": [{key: candidate[key] for key in ("event_uri", "anchor_uri", "url", "score", "evidence_types")}
                    for candidate in item["candidates"][:3]]})
    return {"method": METHOD, "policy": POLICY, "summary": summary, "years": years,
        "field_inventory": inventory, "candidates": predictions, "heldout": diagnostic,
        "fit": fit, "examples": examples}
