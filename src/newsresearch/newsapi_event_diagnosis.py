"""Distinguish provider nulls, retention gaps and derived metadata projection loss."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, digest, require_active, utc
from .legacy import event_uri_state
from .newsapi_event_coverage import summarize
from .newsapi_id_manifest import records
from .newsapi_id_manifest_archive_repair import budget

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-event-uri-fetch-diagnosis-v1"


def event_signature(article: Json) -> tuple[str, str | None]:
    state = event_uri_state(article)
    return state, article["eventUri"] if state == "populated" else None


def raw_matches(engine: Research, receipt: Json) -> bool:
    reference = receipt.get("raw_response")
    if reference is None:
        return False
    raw = engine.ledger.artifacts.read_bytes(reference)
    hashed = hashlib.sha256(raw).hexdigest()
    if hashed != reference or receipt.get("raw_sha256", hashed) != hashed:
        raise ResearchError("Retained raw response hash mismatch")
    if canonical(json.loads(raw)) != canonical(receipt["response"]):
        raise ResearchError("Parsed receipt differs from retained provider response")
    return True


def transition(old: Json, new: Json) -> str:
    if old["state"] == new["state"] == "populated":
        return "populated_same_id" if old["event_uri"] == new["event_uri"] else "populated_changed_id"
    return old["state"] + "_to_" + new["state"]


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile"})
    protocol = engine.ledger.get(context.versions["protocol"], "protocol")["content"]
    rules = engine.ledger.get(context.versions["selection"], "selection")["content"]["rules"]
    if protocol.get("method") != METHOD or data.get("coverage_id") != rules.get("coverage_id"):
        raise ResearchError("Register the exact saved coverage result before diagnosis")
    if data.get("reuse_result"):
        previous = engine.ledger.get(data["reuse_result"], "newsapi_event_diagnosis")
        if previous["versions"] != context.versions or previous["coverage_id"] != data["coverage_id"]:
            raise ResearchError("Saved diagnosis reuse requires its exact original versions and coverage")
        return {"id": data["reuse_result"], **previous, "reused": True}
    coverage = engine.ledger.get(data["coverage_id"], "newsapi_event_coverage")
    proof = engine.ledger.artifacts.read(coverage["proof_artifact"])
    rows = proof["rows"]
    if canonical(summarize(rows)) != canonical(coverage["combined"]):
        raise ResearchError("Coverage proof does not reproduce the bound summary")
    by_receipt: dict[str, list[Json]] = defaultdict(list)
    for row in rows:
        by_receipt[row["receipt"]].append(row)
    flags: dict[str, Counter[str]] = defaultdict(Counter)
    raw_counts: Counter[str] = Counter()
    raw_states: Counter[str] = Counter()
    mixed_pages = 0
    absent_nonquarantine = 0
    duplicate_strata: dict[str, Counter[str]] = defaultdict(Counter)
    receipt_proof = []
    for ref, selected in by_receipt.items():
        original = selected[0]["origin"] == "original_saved"
        kind = "newsapi_collection_receipt" if original else "newsapi_id_receipt"
        receipt = engine.ledger.get(ref, kind)
        verified = raw_matches(engine, receipt)
        flag = str(receipt["parameters"].get("includeArticleEventUri", "not_explicitly_set"))
        flags["original" if original else "supplement"][flag] += 1
        all_articles = receipt["response"]["articles"]["results"]
        all_states = Counter(event_uri_state(a) for a in all_articles)
        mixed_pages += original and all_states["populated"] > 0 and all_states["null"] > 0
        for row in selected:
            article = all_articles[row["index"]]
            if (article.get("uri") != row["article_uri"] or digest(article) != row["record_hash"]
                    or event_signature(article) != (row["state"], row["event_uri"])):
                raise ResearchError("Source locator/hash/event metadata differs from the saved coverage proof")
            raw_counts["verified_rows" if verified else "raw_bytes_unavailable_rows"] += 1
            if verified:
                raw_states[row["state"]] += 1
            absent_nonquarantine += row["state"] == "absent" and not row["quarantined"]
            if original:
                value = article.get("isDuplicate")
                stratum = "duplicate" if value is True else "nonduplicate" if value is False else "unavailable"
                duplicate_strata[stratum][row["state"]] += 1
        receipt_proof.append({"receipt": ref, "kind": kind, "rows": len(selected),
            "raw_response": receipt.get("raw_response"), "raw_verified": verified,
            "event_flag": flag, "all_page_event_states": dict(all_states)})
    original_rows = {r["article_uri"]: r for r in rows if r["origin"] == "original_saved"}
    transitions: Counter[str] = Counter()
    comparisons = []
    fresh_by_receipt: dict[str, list[Json]] = defaultdict(list)
    for row in proof["fresh_comparison_rows"]:
        fresh_by_receipt[row["receipt"]].append(row)
        old = original_rows.get(row["article_uri"])
        label = transition(old, row) if old else "new_metadata_record"
        transitions[label] += 1
        comparisons.append({"article_uri": row["article_uri"], "transition": label,
            "original_locator": old, "fresh_locator": row})
    fresh_raw_verified = 0
    for ref in fresh_by_receipt:
        receipt = engine.ledger.get(ref, "newsapi_id_receipt")
        if not raw_matches(engine, receipt):
            raise ResearchError("Fresh comparison requires retained exact raw responses")
        for row in fresh_by_receipt[ref]:
            article = receipt["response"]["articles"]["results"][row["index"]]
            if (article.get("uri") != row["article_uri"] or digest(article) != row["record_hash"]
                    or event_signature(article) != (row["state"], row["event_uri"])):
                raise ResearchError("Fresh comparison locator/hash/event metadata mismatch")
        fresh_raw_verified += 1
        flags["fresh_window"][str(receipt["parameters"].get("includeArticleEventUri", "not_explicitly_set"))] += 1
    recovery = engine.ledger.get(coverage["recovery_id"], "newsapi_id_manifest_minimal_recovery")
    projected = recovery["minimal_recovery_summary"]["enumeration"]["articles"]
    projection: Counter[str] = Counter()
    for row in proof["fresh_comparison_rows"]:
        projected_state = event_uri_state(projected[row["article_uri"]])
        projection[row["state"] + "_to_" + projected_state] += 1
    # Also inspect every already-retained detail/list response under this authorization.
    route_observations = []
    for receipt in records(engine, "newsapi_id_receipt"):
        response = receipt.get("response")
        if not isinstance(response, dict) or receipt.get("http_status") != 200:
            continue
        candidates = response.get("articles", {}).get("results", []) if isinstance(response.get("articles"), dict) else []
        if not candidates:
            candidates = [v["info"] for v in response.values() if isinstance(v, dict) and isinstance(v.get("info"), dict)]
        for article in candidates:
            if not isinstance(article, dict) or article.get("uri") not in original_rows:
                continue
            old = original_rows[article["uri"]]
            state, value = event_signature(article)
            route_observations.append({"receipt": receipt["id"], "article_uri": article["uri"],
                "endpoint": receipt["parameters"].get("endpointVariant"), "action": receipt["parameters"].get("action"),
                "archive_header": receipt.get("headers", {}).get("req-archive"),
                "event_flag": receipt["parameters"].get("includeArticleEventUri", "not_explicitly_set"),
                "state": state, "transition": transition(old, {"state": state, "event_uri": value})})
    balance = budget(engine)
    diagnosis = {"method": METHOD, "versions": context.versions, "coverage_id": data["coverage_id"],
        "receipt_checks": receipt_proof, "paired_comparisons": comparisons,
        "retained_route_observations": route_observations}
    artifact = engine.ledger.artifacts.put(diagnosis)
    engine.ledger.append(session, "newsapi.event_diagnosis.proof.saved", {"artifact": artifact})
    result = {"versions": context.versions, "method": METHOD, "coverage_id": data["coverage_id"],
        "proof_artifact": artifact, "saved": coverage["combined"], "six_recovered": coverage["supplement"],
        "receipt_count": len(receipt_proof), "raw_verified_receipts": sum(r["raw_verified"] is True for r in receipt_proof),
        "raw_rows": dict(raw_counts), "raw_verified_event_states": dict(raw_states),
        "original_mixed_null_populated_pages": mixed_pages, "absent_nonquarantined": absent_nonquarantine,
        "request_event_flags": {k: dict(v) for k, v in flags.items()},
        "duplicate_strata": {k: dict(v) for k, v in duplicate_strata.items()},
        "fresh_window": coverage["fresh_metadata_window"], "fresh_raw_verified_pages": fresh_raw_verified,
        "paired_transitions": dict(transitions), "derived_projection_transitions": dict(projection),
        "retained_route_transitions": dict(Counter(r["transition"] for r in route_observations)),
        "retained_route_observation_count": len(route_observations), "budget": balance,
        "remaining_conservative_tokens": balance["limit"] - balance["conservative_accounted_tokens"],
        "network_calls": 0, "model_calls": 0, "newsapi_tokens": 0, "failed": 0, "pending": 0,
        "generated_at": utc(), "interpretation_limit": "Null is provider-reported no assignment at recorded retrieval, not proof of internal clustering eligibility, permanent nonassignment or current state. Quarantine loses metadata; normalized auxiliary projection drops eventUri but earlier coverage used raw receipt records. No explicit-true live intervention was run."}
    identifier = engine.ledger.record(session, "newsapi_event_diagnosis", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
