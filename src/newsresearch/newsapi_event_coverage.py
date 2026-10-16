"""Offline provider-event metadata coverage of the exact saved cybercrime frame."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, digest, require_active, utc
from .legacy import event_uri_state, event_uri_summary
from .newsapi_id_manifest import load_baseline

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-saved-event-uri-coverage-v1"


def summarize(rows: list[Json]) -> Json:
    counts = Counter(row["state"] for row in rows)
    values = {row["event_uri"] for row in rows if row["state"] == "populated"}
    result = event_uri_summary(counts, values)
    result["populated_percent"] = 100 * counts["populated"] / len(rows) if rows else None
    result["quarantined_records"] = sum(row["quarantined"] for row in rows)
    return result


def observation(article: Json, receipt: str, index: int, origin: str) -> Json:
    state = event_uri_state(article)
    return {"article_uri": article["uri"], "year": article["date"][:4], "state": state,
        "event_uri": article["eventUri"] if state == "populated" else None,
        "quarantined": article.get("quarantined") is True, "record_hash": digest(article),
        "receipt": receipt, "index": index, "origin": origin}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile"})
    selection = engine.ledger.get(context.versions["selection"], "selection")["content"]["rules"]
    protocol = engine.ledger.get(context.versions["protocol"], "protocol")["content"]
    if protocol.get("method") != METHOD or data.get("recovery_id") != selection.get("recovery_id"):
        raise ResearchError("Register the exact recovery source and offline event coverage method")
    recovery = engine.ledger.get(data["recovery_id"], "newsapi_id_manifest_minimal_recovery")
    baseline, identities = load_baseline(engine, recovery["baseline_audit"])
    original: list[Json] = []
    receipts: dict[str, Json] = {}
    flags: Counter[str] = Counter()
    for partition in baseline["periods"]:
        for locator in identities[partition["date_start"]]["identifiers"]:
            ref = locator["receipt"]
            if ref not in receipts:
                receipts[ref] = engine.ledger.get(ref, "newsapi_collection_receipt")
                parameters = receipts[ref]["parameters"]
                flags[str(parameters.get("includeArticleEventUri", "not_explicitly_set"))] += 1
            article = receipts[ref]["response"]["articles"]["results"][locator["index"]]
            if article.get("uri") != locator["uri"] or digest(article) != locator["record_hash"]:
                raise ResearchError("Original article does not match its immutable identity locator")
            original.append(observation(article, ref, locator["index"], "original_saved"))
    if len({r["article_uri"] for r in original}) != len(original):
        raise ResearchError("Original saved frame has repeated IDs; explicit version policy required")
    if len(original) != baseline["distinct_provider_ids"]:
        raise ResearchError("Original saved frame count disagrees with the baseline")
    enumeration = recovery["minimal_recovery_summary"]["enumeration"]
    added = set(enumeration["observed_added_ids"])
    supplement: list[Json] = []
    fresh: list[Json] = []
    fresh_receipts = enumeration["receipt_ids"]
    for ref in fresh_receipts:
        receipt = engine.ledger.get(ref, "newsapi_id_receipt")
        for index, article in enumerate(receipt["response"]["articles"]["results"]):
            row = observation(article, ref, index, "fresh_minimal_metadata")
            fresh.append(row)
            if article["uri"] in added:
                supplement.append(row)
    if (len(fresh) != enumeration["unique_ids_seen"] or len({r["article_uri"] for r in fresh}) != len(fresh)
            or {r["article_uri"] for r in supplement} != added or len(supplement) != len(added)
            or added & {r["article_uri"] for r in original}):
        raise ResearchError("Fresh metadata source does not match its exact verified ID frame")
    combined = original + supplement
    by_year: dict[str, list[Json]] = defaultdict(list)
    for row in combined:
        by_year[row["year"]].append(row)
    proof = {"method": METHOD, "versions": context.versions, "baseline_audit": recovery["baseline_audit"],
        "original_identity_manifest": baseline["identity_manifest"], "recovery_id": data["recovery_id"],
        "rows": combined, "fresh_comparison_rows": fresh}
    artifact = engine.ledger.artifacts.put(proof)
    engine.ledger.append(session, "newsapi.event_coverage.proof.saved", {"artifact": artifact})
    engine.ledger.append(session, "newsapi.event_coverage.receipts.inspected", {
        "original_receipts": sorted(receipts), "fresh_receipts": fresh_receipts,
        "fields": ["uri", "date", "eventUri", "quarantined"], "source_text_used": False})
    result = {"versions": context.versions, "method": METHOD, "baseline_audit": recovery["baseline_audit"],
        "recovery_id": data["recovery_id"], "proof_artifact": artifact, "original": summarize(original),
        "supplement": summarize(supplement), "combined": summarize(combined),
        "years": [{"year": year, **summarize(rows)} for year, rows in sorted(by_year.items())],
        "fresh_metadata_window": summarize(fresh), "original_event_flag_receipt_counts": dict(flags),
        "supplement_states": [{"article_uri": r["article_uri"], "state": r["state"]} for r in supplement],
        "failed": 0, "pending": 0, "network_calls": 0, "model_calls": 0, "newsapi_tokens": 0,
        "generated_at": utc(), "limitations": [
            "Technical article metadata coverage, not dossier/event counts or event identity validation.",
            "Absent fields and quarantined metadata do not establish that the provider has no event ID.",
            "Original records and later metadata supplement have different retrieval times and field projections."]}
    identifier = engine.ledger.record(session, "newsapi_event_coverage", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
