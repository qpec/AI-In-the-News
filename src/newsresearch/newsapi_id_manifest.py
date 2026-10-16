"""Bounded live ID enumeration and exact comparison to an immutable saved frame."""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc
from .newsapi_collection import collection_request, number, saved
from .newsapi_probe import transport

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-id-manifest-583-v1"
AUTH_ID = "nl-cyber-id-manifest-20261016-583"
CAP = 583
PAGE_SIZE = 1000
SEARCH_RESERVATION = 50
USAGE_RESERVATION = 5
RESERVATIONS = {1000: SEARCH_RESERVATION, 5000: 250}


def request(start: str, end: str, page: int, page_size: int = PAGE_SIZE) -> Json:
    if page_size not in RESERVATIONS:
        raise ResearchError("Use an explicitly supported ID-list page size")
    query = {k: v for k, v in collection_request((start, end), 1).items()
             if not k.startswith("articles") and k != "includeArticleBody"}
    return {**query, "resultType": "uriWgtList", "uriWgtListCount": page_size,
        "uriWgtListPage": page, "uriWgtListSortBy": "date", "uriWgtListSortByAsc": True}


def parse_manifest(response: Json) -> tuple[list[str], int]:
    section = response.get("uriWgtList")
    if not isinstance(section, dict) or not isinstance(section.get("results"), list):
        raise ResearchError("Expected documented uriWgtList.results array")
    total = section.get("totalResults")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ResearchError("Manifest totalResults is unavailable")
    identifiers = []
    for entry in section["results"]:
        if not isinstance(entry, str) or not entry or any(c.isspace() for c in entry):
            raise ResearchError("Unexpected URI-weight entry format")
        uri = entry.split(":", 1)[0]
        if not uri:
            raise ResearchError("Empty normalized article ID")
        identifiers.append(uri)
    return identifiers, total


def accounting(intents: list[Json], receipts: list[Json]) -> Json:
    by_attempt = {r["attempt"]: r for r in receipts}
    known = upper = 0.0
    unknown, unresolved, excess = [], [], []
    for intent in intents:
        receipt = by_attempt.get(intent["attempt"])
        cost = number(receipt.get("billed_tokens")) if receipt else None
        known += cost or 0
        upper += cost if cost is not None else intent["reserved_tokens"]
        if cost is None:
            unknown.append(intent["attempt"])
        if receipt is None or receipt.get("outcome") == "unknown":
            unresolved.append(intent["attempt"])
        if cost is not None and cost > intent["reserved_tokens"]:
            excess.append(intent["attempt"])
    return {"reported_tokens": known, "conservative_accounted_tokens": upper,
        "unknown_individual_costs": unknown, "unresolved_outcomes": unresolved,
        "reservation_exceeded_attempts": excess, "limit": CAP}


def records(engine: Research, kind: str) -> list[Json]:
    return [r for r in saved(engine, kind, None) if r.get("authorization_id") == AUTH_ID]


def dispatch(engine: Research, session: str, context: Context, parameters: Json, purpose: str,
             reserve_override: int | None = None) -> Json:
    require_active(engine, session)
    usage = parameters == {"endpointVariant": "usage"}
    resolution = purpose.startswith("resolution_") and not usage
    if resolution:
        policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
        if (policy.get("resolution_method") != "nl-cyber-id-manifest-resolution-v1"
                or policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP
                or parameters not in policy.get("resolution_templates", [])
                or parameters.get("includeArticleBody") is not False or parameters.get("articleBodyLen") != 0):
            raise ResearchError("Resolution dispatch requires an exact registered metadata-only template")
    metadata = parameters.get("endpointVariant") == "article_info" or resolution
    reserve = USAGE_RESERVATION if usage else SEARCH_RESERVATION if metadata else RESERVATIONS[parameters["uriWgtListCount"]]
    if reserve_override is not None:
        policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
        if (usage or metadata or reserve_override != 50 or policy.get("block_reservation") != 50
                or policy.get("block_method") != "nl-cyber-id-manifest-archive-block-v1"
                or parameters not in policy.get("block_templates", [])):
            raise ResearchError("Empirical block reservation requires its exact registered request and policy")
        reserve = reserve_override
    intents, receipts = records(engine, "newsapi_id_intent"), records(engine, "newsapi_id_receipt")
    balance = accounting(intents, receipts)
    if balance["conservative_accounted_tokens"] + reserve > CAP:
        raise ResearchError("ID-manifest authorization budget reached")
    if not usage:
        if balance["unresolved_outcomes"] or balance["reservation_exceeded_attempts"]:
            raise ResearchError("Unresolved or excessive charge blocks further searches")
        usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received"
                  and r.get("http_status") == 200 and number(r.get("response", {}).get("usedTokens")) is not None]
        if not usages:
            raise ResearchError("Fresh account balance is required")
        latest = usages[-1]
        if number(latest["response"].get("availableTokens")) != 5000:
            raise ResearchError("Account allowance differs from authorized 5000")
        unreflected = receipts[receipts.index(latest)+1:]
        pending = sum(r["billed_tokens"] if r.get("billed_tokens") is not None else r["reserved_tokens"] for r in unreflected)
        used = number(latest["response"].get("usedTokens"))
        if used is None or used + pending + reserve > 5000:
            raise ResearchError("Account allowance cannot cover next conservative reservation")
        same = [r for r in receipts if canonical(r["parameters"]) == canonical(parameters)]
        if len(same) >= 2 or any(r.get("manifest_status") == "valid" for r in same):
            raise ResearchError("No duplicate valid-page dispatch or unbounded retry")
    attempt = str(uuid.uuid4())
    intent = {"attempt": attempt, "authorization_id": AUTH_ID, "versions": context.versions,
        "purpose": purpose, "parameters": parameters, "reserved_tokens": reserve, "started_at": utc()}
    engine.ledger.record(session, "newsapi_id_intent", attempt, intent)
    # No retry in transport. Unknown outcomes retain the reservation and stop paid continuation.
    try:
        status, headers, raw = transport(parameters)
    except ResearchError as error:
        result = {**intent, "outcome": "unknown", "http_status": None, "billed_tokens": None,
            "response": None, "raw_response": None, "error_type": type(error).__name__, "completed_at": utc()}
    else:
        parsed = None
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("Non-object response")
            key = os.environ.get("EVENTREGISTRY_API_KEY", "")
            if key and (key.encode() in raw or key in canonical(parsed) or key in canonical(headers)):
                raise ResearchError("Credential echo rejected")
            require_no_credentials(parsed)
            require_no_credentials(headers)
            def has_body(value: object) -> bool:
                if isinstance(value, dict):
                    return any((k == "body" and bool(v)) or has_body(v) for k, v in value.items())
                return isinstance(value, list) and any(has_body(item) for item in value)
            if resolution and has_body(parsed):
                raise ResearchError("Unexpected article body rejected from resolution metadata retention")
            if metadata and any(isinstance(item, dict) and isinstance(item.get("info"), dict)
                    and item["info"].get("body") for item in parsed.values()):
                raise ResearchError("Unexpected article body rejected from metadata-only retention")
        except (ValueError, UnicodeError, ResearchError) as error:
            result = {**intent, "outcome": "unknown", "http_status": status, "billed_tokens": number(headers.get("req-tokens")),
                "response": None, "raw_response": None, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                "error_type": type(error).__name__, "completed_at": utc()}
        else:
            raw_ref = engine.ledger.artifacts.put_bytes(raw)
            engine.ledger.append(session, "newsapi.id_manifest.raw.saved", {"attempt": attempt, "artifact": raw_ref})
            result = {**intent, "outcome": "received", "http_status": status, "headers": headers,
                "billed_tokens": number(headers.get("req-tokens")), "response": parsed,
                "raw_response": raw_ref, "raw_sha256": hashlib.sha256(raw).hexdigest(), "completed_at": utc()}
            if not usage and not metadata:
                result["manifest_status"] = "invalid"
                try:
                    ids, total = parse_manifest(parsed)
                    page = parameters["uriWgtListPage"]
                    count = parameters["uriWgtListCount"]
                    expected = min(count, max(0, total - count * (page-1)))
                    if (status == 200 and headers.get("req-archive") == "1" and total > 0
                            and len(ids) == expected and len(ids) == len(set(ids))):
                        result.update(manifest_status="valid", normalized_ids=ids, provider_total=total)
                    else:
                        result["validation_reason"] = "archive_unconfirmed_empty_duplicate_or_unexpected_page_size"
                except ResearchError:
                    result["validation_reason"] = "unsupported_manifest_shape"
    identifier = engine.ledger.record(session, "newsapi_id_receipt", attempt, result)
    return {"id": identifier, **result}


def compare_partition(base_ids: set[str], receipts: list[Json], page_size: int = PAGE_SIZE) -> Json:
    valid = [r for r in receipts if r.get("manifest_status") == "valid"
             and r["parameters"].get("uriWgtListCount", PAGE_SIZE) == page_size]
    page_rows = {r["parameters"]["uriWgtListPage"]: r for r in valid}
    ids = {uri for r in valid for uri in r["normalized_ids"]}
    totals = sorted({r["provider_total"] for r in valid})
    total = totals[-1] if totals else None
    expected_pages = (total+page_size-1)//page_size if total is not None else None
    missing_pages = sorted(set(range(1, expected_pages+1))-set(page_rows)) if expected_pages is not None else None
    occurrences = sum(len(r["normalized_ids"]) for r in valid)
    complete = bool(valid) and len(totals) == 1 and not missing_pages and len(ids) == total and len(ids) == occurrences
    return {"saved_ids": len(base_ids), "manifest_ids_seen": len(ids), "provider_total": total,
        "pages": len(page_rows), "expected_pages": expected_pages, "pending_pages": missing_pages,
        "complete": complete, "positive_total_drift": len(totals) > 1, "duplicate_id_occurrences": occurrences-len(ids),
        "common_ids": len(ids & base_ids), "manifest_only_ids": sorted(ids-base_ids),
        "saved_only_ids": sorted(base_ids-ids) if complete else None,
        "saved_ids_not_yet_seen": len(base_ids-ids),
        "saved_coverage_of_manifest_percent": 100*len(ids & base_ids)/len(ids) if complete and ids else None,
        "manifest_receipts": [r["id"] for r in valid]}


def load_baseline(engine: Research, identifier: str) -> tuple[Json, Json]:
    audit = engine.ledger.get(identifier, "newsapi_retrieval_audit")
    first = audit["periods"][0]["page_details"][0]["receipt"]
    audit["query_parameters"] = engine.ledger.get(first, "newsapi_collection_receipt")["parameters"]
    return audit, engine.ledger.artifacts.read(audit["identity_manifest"])


def snapshot(engine: Research, baseline: Json, identities: Json, context: Context, page_size: int = PAGE_SIZE) -> Json:
    receipts = records(engine, "newsapi_id_receipt")
    periods = []
    manifest_sets: dict[str, set[str]] = {}
    saved_sets: dict[str, set[str]] = {}
    for p in baseline["periods"]:
        start, end = p["date_start"], p["date_end"]
        base_ids = set(identities[start]["uri_counts"])
        selected = [r for r in receipts if (r["parameters"].get("dateStart"), r["parameters"].get("dateEnd")) == (start, end)]
        phase_receipts = [r for r in selected if r["parameters"].get("uriWgtListCount") == page_size]
        row = {"year": p["year"], "date_start": start, "date_end": end, **compare_partition(base_ids, phase_receipts, page_size),
            "attempts": len(selected), "invalid_attempts": sum(r.get("manifest_status") != "valid" for r in selected),
            "reported_tokens": sum(r["billed_tokens"] for r in selected if r.get("billed_tokens") is not None)}
        periods.append(row)
        year = p["year"]
        manifest_sets.setdefault(year, set()).update(uri for r in phase_receipts if r.get("manifest_status") == "valid" for uri in r["normalized_ids"])
        saved_sets.setdefault(year, set()).update(base_ids)
    years = []
    for year, saved_ids in sorted(saved_sets.items()):
        current = manifest_sets[year]
        rows = [p for p in periods if p["year"] == year]
        complete = all(p["complete"] for p in rows)
        years.append({"year": year, "saved_ids": len(saved_ids), "manifest_ids_seen": len(current),
            "complete": complete, "common_ids": len(saved_ids & current),
            "manifest_only_ids": sorted(current-saved_ids), "saved_only_ids": sorted(saved_ids-current) if complete else None,
            "saved_coverage_of_manifest_percent": 100*len(saved_ids & current)/len(current) if complete and current else None,
            "reported_tokens": sum(p["reported_tokens"] for p in rows)})
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("http_status") == 200 and r.get("outcome") == "received"]
    baseline_used = number(usages[0]["response"].get("usedTokens")) if usages else None
    final_used = number(usages[-1]["response"].get("usedTokens")) if usages else None
    return {"versions": context.versions, "authorization_id": AUTH_ID, "baseline_audit": baseline["id"], "page_size": page_size,
        "prior_phase_receipts": [r["id"] for r in receipts if r["purpose"] == "manifest" and r["parameters"].get("uriWgtListCount") != page_size],
        "periods": periods, "years": years,
        "budget": accounting(records(engine, "newsapi_id_intent"), receipts),
        "baseline_used": baseline_used, "latest_used": final_used,
        "observed_account_delta": final_used-baseline_used if baseline_used is not None and final_used is not None else None,
        "receipt_ids": [r["id"] for r in receipts], "model_calls": 0, "generated_at": utc(),
        "limitation": "Present-day provider ID-list comparison, not proof of original omission or all relevant Dutch news; partial enumeration never establishes absent IDs"}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    page_size = policy.get("page_size", PAGE_SIZE)
    if (policy.get("method") != METHOD or policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP
            or page_size not in RESERVATIONS
            or policy.get("templates") != [request(p[0], p[1], 1, page_size) for p in policy.get("periods", [])]):
        raise ResearchError("Exact 583-token ID-manifest test authorization required")
    baseline, identities = load_baseline(engine, policy["baseline_audit"])
    baseline = {"id": policy["baseline_audit"], **baseline}
    if sorted(policy["periods"]) != sorted([[p["date_start"], p["date_end"]] for p in baseline["periods"]]):
        raise ResearchError("Use the exact saved publication intervals")
    predicates = ["keyword", "keywordOper", "keywordLoc", "keywordSearchMode", "lang", "dataType", "isDuplicateFilter"]
    if any(request(policy["periods"][0][0], policy["periods"][0][1], 1).get(k) != baseline["query_parameters"].get(k) for k in predicates):
        raise ResearchError("Manifest search predicates differ from saved collection")
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit live ID-manifest execution required")
    if not os.environ.get("EVENTREGISTRY_API_KEY"):
        raise ResearchError("NewsAPI credential unavailable before dispatch")
    if page_size == 5000 and not any(r.get("manifest_status") == "valid" and r["parameters"].get("uriWgtListCount") == 1000
            and r.get("billed_tokens") is not None and r["billed_tokens"] <= SEARCH_RESERVATION
            for r in records(engine, "newsapi_id_receipt")):
        raise ResearchError("Successful, cost-confirmed 1000-ID calibration required before larger pages")
    unknown_collection = engine.ledger.db.execute("SELECT COUNT(*) FROM records i WHERE i.kind='newsapi_collection_intent' AND NOT EXISTS (SELECT 1 FROM records r WHERE r.kind='newsapi_collection_receipt' AND json_extract(r.payload,'$.attempt')=json_extract(i.payload,'$.attempt'))").fetchone()[0]
    if unknown_collection:
        raise ResearchError("An unresolved earlier collection dispatch blocks the test")
    limit = data.get("requests", 8)
    if not isinstance(limit, int) or not 1 <= limit <= 12:
        raise ResearchError("Use 1 through12 searches per checkpoint")
    state = snapshot(engine, baseline, identities, context, page_size)
    if all(p["complete"] for p in state["periods"]):
        raise ResearchError("Manifest test is complete; do not spend more tokens")
    before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_manifest_checkpoint")
    if before.get("outcome") != "received" or before.get("http_status") != 200 or number(before["response"].get("usedTokens")) is None:
        raise ResearchError("Account usage unavailable; no manifest dispatch")
    stop = "checkpoint"
    for _ in range(limit):
        state = snapshot(engine, baseline, identities, context, page_size)
        if state["budget"]["unresolved_outcomes"]:
            stop = "unknown_outcome"
            break
        if any(p["positive_total_drift"] or p["duplicate_id_occurrences"] for p in state["periods"]):
            stop = "inconsistent_manifest"
            break
        pending = [p for p in state["periods"] if not p["complete"]]
        if not pending:
            stop = "manifest_complete"
            break
        period = min(pending, key=lambda p: (p["pages"], p["date_start"]))
        page = min(period["pending_pages"]) if period["pending_pages"] else period["pages"]+1
        params = request(period["date_start"], period["date_end"], page, page_size)
        try:
            receipt = dispatch(engine, session, context, params, "manifest")
        except ResearchError as error:
            if str(error).startswith(("ID-manifest authorization budget", "Account allowance")):
                stop = "budget_limit"
                break
            if str(error).startswith("No duplicate valid-page dispatch"):
                stop = "invalid_manifest_response"
                break
            raise
        print(json.dumps({"start": period["date_start"], "page": page, "ids": len(receipt.get("normalized_ids", [])),
            "status": receipt.get("manifest_status", receipt["outcome"]), "billed_tokens": receipt.get("billed_tokens"),
            "provider_total": receipt.get("provider_total"), "archive": receipt.get("headers", {}).get("req-archive")}), flush=True)
        if receipt.get("outcome") == "unknown":
            stop = "unknown_outcome"
            break
        if receipt.get("manifest_status") != "valid":
            # A single explicit received-response retry is preregistered; no hidden retries.
            same = [r for r in records(engine, "newsapi_id_receipt") if canonical(r["parameters"]) == canonical(params)]
            if len(same) >= 2:
                stop = "invalid_manifest_response"
                break
        time.sleep(0.6)
    try:
        dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_manifest_checkpoint")
    except ResearchError as error:
        if not str(error).startswith("ID-manifest authorization budget"):
            raise
    result = snapshot(engine, baseline, identities, context, page_size)
    if all(p["complete"] for p in result["periods"]):
        stop = "manifest_complete"
    result["stop_reason"] = stop
    identifier = engine.ledger.record(session, "newsapi_id_manifest_test", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
