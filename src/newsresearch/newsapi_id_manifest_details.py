"""Metadata-only identification of differences in a completed ID comparison."""
from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, digest, require_active, utc
from .newsapi_id_manifest import AUTH_ID, CAP, METHOD, accounting, dispatch, load_baseline, records

if TYPE_CHECKING:
    from .runtime import Research

DETAILS_METHOD = "nl-cyber-id-manifest-metadata-v1"


def info_request(ids: list[str]) -> Json:
    if not ids or len(ids) > 10 or len(ids) != len(set(ids)):
        raise ResearchError("Metadata-only lookup requires one through ten distinct exact IDs")
    return {"endpointVariant": "article_info", "action": "getArticle", "resultType": "info", "articleUri": ids,
        "includeArticleBody": False, "articleBodyLen": 0, "infoArticleBodyLen": 0,
        "includeArticleTitle": True, "includeArticleUrl": True, "includeArticleBasicInfo": True, "includeSourceTitle": True}


def metadata(article: Json) -> Json:
    return {"title": article.get("title"), "url": article.get("url"), "date": article.get("date"),
        "lang": article.get("lang"), "source": article.get("source")}


def extract_info(response: Json, ids: list[str]) -> dict[str, Json]:
    output = {}
    for uri in ids:
        item = response.get(uri)
        info = item.get("info") if isinstance(item, dict) else None
        if isinstance(info, dict) and info.get("uri") == uri:
            output[uri] = {"status": "available", **metadata(info)}
        else:
            output[uri] = {"status": "unavailable", "reason": "missing_or_mismatched_exact_id"}
    return output


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("method") != METHOD or policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP
            or policy.get("details_method") != DETAILS_METHOD or policy.get("metadata_max_ids") != 10):
        raise ResearchError("Register the exact metadata-only difference method under the existing budget")
    if data.get("reuse_result"):
        previous = engine.ledger.get(data["reuse_result"], "newsapi_id_manifest_details")
        if previous["versions"] != context.versions or previous["authorization_id"] != AUTH_ID:
            raise ResearchError("Metadata reuse requires exact original versions and authorization")
        return {"id": data["reuse_result"], **previous, "reused": True}
    comparisons = records(engine, "newsapi_id_manifest_test")
    if not comparisons or not all(y["complete"] for y in comparisons[-1]["years"]):
        raise ResearchError("A complete manifest comparison must precede difference identification")
    comparison = comparisons[-1]
    if comparison["baseline_audit"] != policy["baseline_audit"]:
        raise ResearchError("Metadata phase must retain the immutable original collection baseline")
    for kind in ["question", "selection", "profile"]:
        if context.versions[kind] != comparison["versions"][kind]:
            raise ResearchError("Metadata phase may not change the corpus selection or research question")
    _, identities = load_baseline(engine, comparison["baseline_audit"])
    differences = []
    for year in comparison["years"]:
        for direction in ["manifest_only_ids", "saved_only_ids"]:
            for uri in year[direction]:
                row = {"year": year["year"], "direction": direction, "article_uri": uri, "metadata": None}
                if direction == "saved_only_ids":
                    locations = [item for frame in identities.values() for item in frame["identifiers"] if item["uri"] == uri]
                    if len(locations) != 1:
                        raise ResearchError("Saved-only ID has an ambiguous original record locator")
                    locator = locations[0]
                    original_receipt = engine.ledger.get(locator["receipt"], "newsapi_collection_receipt")
                    original = original_receipt["response"]["articles"]["results"][locator["index"]]
                    if original.get("uri") != uri or digest(original) != locator["record_hash"]:
                        raise ResearchError("Saved-only metadata does not match the audited original source hash")
                    row["metadata"] = {"status": "available", **metadata(original)}
                    row["original_locator"] = locator
                differences.append(row)
    ids = sorted(row["article_uri"] for row in differences if row["direction"] == "manifest_only_ids")
    if len(ids) > 10:
        raise ResearchError("More than ten new IDs: preserve comparison and register a separately bounded metadata plan")
    parameters = info_request(ids) if ids else None
    prior = [r for r in records(engine, "newsapi_id_receipt") if r.get("purpose") == "difference_metadata"
             and canonical(r["parameters"]) == canonical(parameters)]
    if prior:
        raise ResearchError("Metadata request already dispatched; no automatic repeat or unknown-outcome retry")
    plan = {"versions": context.versions, "authorization_id": AUTH_ID, "comparison": comparison["id"],
        "differences": differences, "parameters": parameters, "model_calls": 0, "created_at": utc()}
    plan_id = engine.ledger.record(session, "newsapi_id_manifest_details_plan", str(uuid.uuid4()), plan)
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit live metadata lookup required; no paid dispatch occurred")
    receipt = None
    if parameters:
        before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_difference_metadata")
        if before.get("outcome") != "received" or before.get("http_status") != 200:
            raise ResearchError("Account usage unavailable before metadata lookup")
        receipt = dispatch(engine, session, context, parameters, "difference_metadata")
        returned = extract_info(receipt.get("response") or {}, ids) if receipt.get("http_status") == 200 else {}
        for row in differences:
            if row["direction"] == "manifest_only_ids":
                row["metadata"] = returned.get(row["article_uri"], {"status": "unavailable", "reason": "metadata_request_failed"})
        dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_difference_metadata")
    receipts = records(engine, "newsapi_id_receipt")
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received" and r.get("http_status") == 200]
    first = usages[0]["response"].get("usedTokens") if usages else None
    last = usages[-1]["response"].get("usedTokens") if usages else None
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "plan": plan_id, "comparison": comparison["id"],
        "baseline_audit": comparison["baseline_audit"], "years": comparison["years"], "differences": differences,
        "metadata_receipt": receipt["id"] if receipt else None, "metadata_billed_tokens": receipt.get("billed_tokens") if receipt else 0,
        "budget": accounting(records(engine, "newsapi_id_intent"), receipts), "baseline_used": first, "latest_used": last,
        "observed_account_delta": last-first if isinstance(first, (int, float)) and isinstance(last, (int, float)) else None,
        "manifest_pages": sum(p["pages"] for p in comparison["periods"]), "calibration_pages": len(comparison["prior_phase_receipts"]),
        "total_current_ids": sum(y["manifest_ids_seen"] for y in comparison["years"]),
        "total_saved_ids": sum(y["saved_ids"] for y in comparison["years"]),
        "total_common_ids": sum(y["common_ids"] for y in comparison["years"]),
        "incomplete_years": [y["year"] for y in comparison["years"] if not y["complete"]],
        "unavailable_metadata": sum(row["metadata"] is None or row["metadata"].get("status") != "available" for row in differences),
        "body_fetch_requested": False, "model_calls": 0, "completed_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_details", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
