"""Offline fetch-completeness diagnostics; never article relevance judgements."""
from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_collection import PERIODS, consistent_pages

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-fetch-missingness-v1"


def inspect_receipts(receipts: list[Json], periods: list[tuple[str, str]] | None = None) -> Json:
    years = []
    fields: Counter[str] = Counter()
    quarantine_fields: Counter[str] = Counter()
    other_fields: Counter[str] = Counter()
    withheld_locators: Counter[str] = Counter()
    examples: list[Json] = []
    for start, end in PERIODS if periods is None else periods:
        selected = [r for r in receipts if r["parameters"]["dateStart"] == start]
        good, _ = consistent_pages(selected)
        indices = sorted({r["parameters"]["articlesPage"] for r in good})
        counts: Counter[str] = Counter()
        for receipt in good:
            for index, article in enumerate(receipt["response"]["articles"]["results"]):
                counts["returned"] += 1
                quarantine = article.get("quarantined") is True
                body_present = isinstance(article.get("body"), str) and bool(article["body"].strip())
                counts["body_present"] += body_present
                counts["quarantined"] += quarantine
                counts["missing_body_quarantined"] += not body_present and quarantine
                counts["missing_body_other"] += not body_present and not quarantine
                counts["nonblank_body_at_most_200_chars"] += body_present and len(article["body"].strip()) <= 200
                for field in ["uri", "title", "url", "date", "lang", "body"]:
                    if not isinstance(article.get(field), str) or not article[field].strip():
                        fields[field] += 1
                        (quarantine_fields if quarantine else other_fields)[field] += 1
                for field in ["uri", "title"]:
                    source = article.get("source")
                    if not isinstance(source, dict) or not source.get(field):
                        fields["source." + field] += 1
                        (quarantine_fields if quarantine else other_fields)["source." + field] += 1
                if quarantine:
                    withheld_locators.update(article.get("unavailable_locator_fields", []))
                    if len(examples) < 3:
                        examples.append({"year": start[:4], "uri": article.get("uri"), "date": article.get("date"),
                            "url": article.get("url"), "source_hash": article.get("source_hash"),
                            "unavailable_locator_fields": article.get("unavailable_locator_fields", []),
                            "receipt": receipt["id"], "item_index": index})
        last = max(good, key=lambda r: r["parameters"]["articlesPage"]) if good else None
        section = last["response"]["articles"] if last else {}
        expected_pages = section.get("pages")
        missing_pages = sorted(set(range(1, expected_pages + 1)) - set(indices)) if isinstance(expected_pages, int) else None
        failed = [r for r in selected if r not in good]
        retried = sum(any(canonical(r["parameters"]) == canonical(ok["parameters"]) for ok in good) for r in failed)
        years.append({"year": start[:4], "date_start": start, "date_end": end, **dict(counts),
            "successful_pages": len(good), "distinct_pages": len(indices), "provider_pages": expected_pages,
            "missing_page_indices": missing_pages, "provider_total": section.get("totalResults"),
            "count_gap": section.get("totalResults", 0) - counts["returned"],
            "failed_attempts": len(failed), "failed_attempts_with_successful_retry": retried,
            "raw_response_bytes_unavailable_pages": sum(r["raw_response"] is None for r in good),
            "unavailable_request_costs": sum(r["billed_tokens"] is None for r in selected)})
    total = sum(y.get("returned", 0) for y in years)
    absent = sum(y.get("missing_body_quarantined", 0) + y.get("missing_body_other", 0) for y in years)
    return {"years": years, "total_records": total, "missing_body": absent,
        "body_present": total-absent, "missing_body_percent": 100*absent/total if total else None,
        "missing_fields": dict(fields), "withheld_locator_fields": dict(withheld_locators), "quarantined_examples": examples,
        "missing_fields_quarantined": dict(quarantine_fields), "missing_fields_other": dict(other_fields),
        "raw_response_bytes_unavailable_pages": sum(y["raw_response_bytes_unavailable_pages"] for y in years),
        "successful_pages": sum(y["successful_pages"] for y in years),
        "nonblank_body_at_most_200_chars": sum(y.get("nonblank_body_at_most_200_chars", 0) for y in years)}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"retrieval_profile"})
    profile = engine.ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"]
    if profile.get("method") != METHOD:
        raise ResearchError("Register the offline fetch-missingness method first")
    original = engine.ledger.get(data["result"], "newsapi_collection_materialization")
    if ({k: v for k, v in original["versions"].items() if k != "retrieval_profile"}
            != {k: v for k, v in context.versions.items() if k != "retrieval_profile"}):
        raise ResearchError("Bind the exact original collection methods")
    receipts = [{"id": identifier, **engine.ledger.get(identifier, "newsapi_collection_receipt")}
                for identifier in original["receipt_ids"]]
    periods = [tuple(p) for p in original.get("periods", PERIODS)]
    result = {**inspect_receipts(receipts, periods), "versions": context.versions,
        "source_result": data["result"], "receipt_ids": original["receipt_ids"], "network_calls": 0,
        "model_calls": 0, "generated_at": utc(), "classification": "Retrieval and retention diagnostics only"}
    identifier = engine.ledger.record(session, "newsapi_collection_missingness", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
