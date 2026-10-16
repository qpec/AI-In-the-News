"""Bounded NewsAPI.ai retrieval diagnostics; no model inference or accepted findings."""
from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any
import urllib.error
import urllib.request
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc

if TYPE_CHECKING:
    from .runtime import Research

ENDPOINT = "https://eventregistry.org/api/v1/article/getArticles"
ENDPOINTS = {"rest": ENDPOINT, "sdk": "https://eventregistry.org/api/v1/article",
             "article_info": "https://eventregistry.org/api/v1/article/getArticle",
             "usage": "https://eventregistry.org/api/v1/usage",
             "service_status": "https://eventregistry.org/api/v1/getServiceStatus"}
AUTHORIZATION = "nl-cyber-search-pilot-2026-10-15-200"
RESERVATION = 20
ALLOWED = {"action", "keyword", "keywordOper", "keywordLoc", "keywordSearchMode", "lang",
           "dateStart", "dateEnd", "sourceLocationUri", "locationUri", "conceptUri",
           "articlesPage", "articlesCount", "articlesSortBy", "articlesSortByAsc",
           "resultType", "dataType", "isDuplicateFilter", "includeArticleBody", "query", "endpointVariant",
           "uriWgtListCount", "uriWgtListPage", "uriWgtListSortBy", "uriWgtListSortByAsc"}
SAFE_HEADERS = {"date", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining",
                "req-action", "req-tokens", "req-archive", "req-chargable", "req-years",
                "req-article-search", "warning"}


def budget(engine: Research) -> Json:
    reservations = [json.loads(r[0]) for r in engine.ledger.db.execute(
        "SELECT payload FROM records WHERE kind='newsapi_reservation'")]
    results = {json.loads(r["payload"])["attempt"]: (r["id"], json.loads(r["payload"]))
               for r in engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='newsapi_probe'")}
    entries = []
    for reservation in reservations:
        if reservation["authorization_id"] != AUTHORIZATION:
            continue
        # Existing records use the attempt UUID as their logical key.
        row = engine.ledger.db.execute("SELECT logical_key FROM records WHERE kind='newsapi_reservation' AND payload=?",
                                      (canonical(reservation),)).fetchone()
        result_id, result = results.get(row[0], (None, {}))
        cost = None
        try:
            candidate = Decimal(result.get("headers", {}).get("req-tokens", "NaN"))
            if candidate.is_finite() and candidate >= 0:
                cost = float(candidate)
        except (InvalidOperation, TypeError):
            pass
        entries.append({"attempt": row[0], "result": result_id, "reported_cost": cost,
                        "upper_bound": cost if cost is not None else reservation["reserved_tokens"],
                        "price_bound_exceeded": cost is not None and cost > reservation["reserved_tokens"]})
    return {"entries": entries, "upper_bound_tokens": float(sum(Decimal(str(e["upper_bound"])) for e in entries)),
            "price_bound_exceeded": any(e["price_bound_exceeded"] for e in entries),
            "original_reserved_tokens": sum(r["reserved_tokens"] for r in reservations),
            "method": "confirmed-costs-plus-unresolved-reservations-v1"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def transport(parameters: Json) -> tuple[int, Json, bytes]:
    key = os.environ.get("EVENTREGISTRY_API_KEY")
    if not key:
        raise ResearchError("NewsAPI.ai credential unavailable")
    # The provider requires a JSON authentication field. It is added only here,
    # outside the exact persisted search parameters, and never logged.
    endpoint = ENDPOINTS[parameters.get("endpointVariant", "rest")]
    wire = canonical({**{k: v for k, v in parameters.items() if k != "endpointVariant"}, "apiKey": key}).encode("utf-8")
    request = urllib.request.Request(endpoint, data=wire, method="POST",
                                     headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=75) as response:
            headers = {k.lower(): v for k, v in response.headers.items()
                       if k.lower() in SAFE_HEADERS}
            return response.status, headers, response.read()
    except urllib.error.HTTPError as error:
        # The caller rejects credential echoes before retaining any response.
        headers = {k.lower(): v for k, v in error.headers.items()
                   if k.lower() in SAFE_HEADERS}
        return error.code, headers, error.read()
    except Exception as error:
        raise ResearchError("NewsAPI.ai transport failed: " + type(error).__name__) from None


def probe(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (engine.config.offline or data.get("execute") is not True
            or policy.get("method") not in {"newsapi-probe-approval-v1", "newsapi-probe-approval-v2"}
            or policy.get("authorization_id") != AUTHORIZATION
            or policy.get("max_tokens") != 200):
        raise ResearchError("Concrete 200-token pilot authorization and online execution required")
    parameters = data.get("parameters", {})
    search = parameters
    if "query" in parameters:
        query = json.loads(parameters["query"]) if isinstance(parameters["query"], str) else parameters["query"]
        search = query.get("$query", {})
    account = parameters in ({"endpointVariant": "usage"}, {"endpointVariant": "service_status"})
    identifiers = parameters.get("resultType") == "uriWgtList"
    if (parameters not in policy.get("requests", []) or set(parameters) - ALLOWED
            or parameters.get("endpointVariant", "rest") not in ENDPOINTS):
        raise ResearchError("Request differs from the registered bounded pilot")
    if not account and (
            (not identifiers and (parameters.get("articlesCount") != 100 or parameters.get("articlesPage") != 1))
            or (identifiers and (parameters.get("uriWgtListCount") != 10000 or parameters.get("uriWgtListPage") != 1))
            or parameters.get("resultType") not in {"articles", "uriWgtList"}
            or parameters.get("action") != "getArticles"
            or parameters.get("includeArticleBody") is not False
            or not "2023-10-15" <= search.get("dateStart", "") <= search.get("dateEnd", "") <= "2026-10-15"):
        raise ResearchError("Request differs from the registered bounded pilot")
    reservations = [json.loads(row[0]) for row in engine.ledger.db.execute(
        "SELECT payload FROM records WHERE kind='newsapi_reservation'")]
    same = [r for r in reservations if r["authorization_id"] == AUTHORIZATION]
    if any(r["parameters"] == parameters for r in same):
        raise ResearchError("Request already reserved; unknown outcomes cannot be retried")
    snapshot = budget(engine)
    if snapshot["price_bound_exceeded"]:
        raise ResearchError("Observed provider charge exceeded its documented reservation; stop dispatch")
    accounted = sum(r["reserved_tokens"] for r in same)
    if policy.get("method") == "newsapi-probe-approval-v2":
        if policy.get("budget_accounting") != snapshot["method"]:
            raise ResearchError("A registered evidence-bound budget reconciliation is required")
        accounted = snapshot["upper_bound_tokens"]
    if accounted + RESERVATION > 200:
        raise ResearchError("200-token authorization exhausted")
    attempt = str(uuid.uuid4())
    engine.ledger.record(session, "newsapi_reservation", attempt, {
        "authorization_id": AUTHORIZATION, "parameters": parameters, "versions": context.versions,
        "reserved_tokens": RESERVATION, "started_at": utc(),
        "endpoint": ENDPOINTS[parameters.get("endpointVariant", "rest")],
        "wire_parameters": {k: v for k, v in parameters.items() if k != "endpointVariant"},
        "budget_before": snapshot, "accounted_upper_bound_after_dispatch": accounted + RESERVATION,
        "authentication_omitted": True, "automatic_retries": 0})
    started = utc()
    status, headers, raw = transport(parameters)
    # A key echoed by a provider must never enter persistent storage.
    key = os.environ.get("EVENTREGISTRY_API_KEY", "")
    if key and (key.encode() in raw or key in canonical(headers)):
        raise ResearchError("Provider response echoed credential; response not retained")
    try:
        parsed = json.loads(raw) if raw else {}
    except (ValueError, UnicodeError):
        parsed = {"error_format": "non-JSON", "error_text": raw.decode("utf-8", errors="replace")[:2000]}
    require_no_credentials(parsed)
    raw_ref = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "newsapi.response.saved", {"attempt": attempt, "artifact": raw_ref})
    articles = parsed.get("uriWgtList" if identifiers else "articles", {})
    success = status == 200 and (account or (isinstance(articles, dict) and isinstance(articles.get("results"), list)))
    rows = articles.get("results", []) if success and not account else []
    if identifiers:
        rows = [{"uri": item.split(":")[0], "provider_uri_weight": item} for item in rows]
    output = {"versions": context.versions, "parameters": parameters, "attempt": attempt,
              "authorization_id": AUTHORIZATION, "http_status": status, "headers": headers,
              "raw_response": raw_ref, "retrieved_at": started, "completed_at": utc(),
              "status": "completed" if success else "failed", "reserved_tokens": RESERVATION,
              "cumulative_reserved_tokens": sum(r["reserved_tokens"] for r in same) + RESERVATION,
              "accounted_upper_bound_after_dispatch": accounted + RESERVATION,
              "provider_total": articles.get("totalResults") if success else None,
              "returned": len(rows), "scored": 0, "model_calls": 0,
              "articles": rows, "failure": None if success else "http_or_provider_error",
              "missing": "All pages after page 1 remain uncollected; no relevance assessment",
              "actual_billed_tokens": headers.get("req-tokens"), "actor": context.actor,
              "provider_notes": {k: v for k, v in parsed.items() if k not in {"articles", "uriWgtList"}}}
    identifier = engine.ledger.record(session, "newsapi_probe", attempt, output)
    return {"id": identifier, **output}


def overview(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    results = []
    for row in engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='newsapi_probe' ORDER BY created_event"):
        result = json.loads(row["payload"])
        raw = (engine.ledger.artifacts.root / result["raw_response"]).read_bytes()
        try:
            content = json.loads(raw) if raw else {}
        except ValueError:
            content = {}
        results.append({"id": row["id"], "parameters": result["parameters"],
                        "versions": result["versions"], "status": result["status"],
                        "returned": result["returned"], "total": result["provider_total"],
                        "headers": result["headers"],
                        "notes": {k: v for k, v in content.items() if k not in {"articles", "uriWgtList"}},
                        "dates": sorted({str(a.get("date", "")) for a in result["articles"]}),
                        "articles": [{k: a.get(k) for k in ["uri", "title", "url", "date", "lang", "source"]}
                                     for a in result["articles"]]})
    reservations = engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='newsapi_reservation'").fetchone()[0]
    known_costs = [float(r["headers"]["req-tokens"]) for r in results if "req-tokens" in r["headers"]]
    comparison_ids = ["d412c4a5455e246d43546cd329c6d59038a1212e78bf21238d4da920eb546721",
                      "5ec89503b8e71f0d17cdece2b89cdeeb88da43b09bd4023233b84cf87db5325b",
                      "bf22ff1ca676c02e87ce77fb54eb5ed065328716b4dfefe82150437cb2ef0340"]
    by_id = {r["id"]: r for r in results}
    compared = [by_id[identifier] for identifier in comparison_ids if identifier in by_id]
    frames = [r for r in results if r["parameters"].get("resultType") == "uriWgtList"]
    frame_comparison = []
    supplemental_union = None
    if frames:
        first = {a["uri"] for a in frames[0]["articles"]}
        for frame in frames:
            current = {a["uri"] for a in frame["articles"]}
            frame_comparison.append({"id": frame["id"], "total": frame["total"],
                "returned_ids": len(current), "provider_frame_complete": len(current) == frame["total"],
                "shared_with_first": len(first & current), "added_to_first": sorted(current - first),
                "missing_from_first": sorted(first - current), "parameters": frame["parameters"]})
        extended = next((f for f in frames if "computerinbraak" in f["parameters"].get("keyword", [])), None)
        proximity = next((f for f in frames if "NEAR/15" in f["parameters"].get("keyword", [])), None)
        if extended and proximity:
            a = {r["uri"] for r in extended["articles"]}
            b = {r["uri"] for r in proximity["articles"]}
            supplemental_union = {"extended_result": extended["id"], "proximity_result": proximity["id"],
                "extended_count": len(a), "proximity_count": len(b), "shared_count": len(a & b),
                "additional_proximity_count": len(b - a), "additional_proximity_ids": sorted(b - a),
                "union_count": len(a | b), "union_ids": sorted(a | b),
                "interpretation": "Observed provider identifier union, not reviewed incident relevance or historical completeness"}
            default_frame = next((f for f in frames if "query" in f["parameters"] and
                "keywordSearchMode" not in json.loads(f["parameters"]["query"])["$query"]), None)
            if default_frame:
                c = {r["uri"] for r in default_frame["articles"]}
                supplemental_union.update({"default_discovery_result": default_frame["id"],
                    "default_discovery_count": len(c), "three_branch_union_count": len(a | b | c),
                    "three_branch_union_ids": sorted(a | b | c),
                    "explicit_additions_beyond_default": len((a | b) - c),
                    "default_additions_beyond_explicit": len(c - (a | b))})
            metadata = {article["uri"]: article for result in results for article in result["articles"]
                        if article.get("title") and article.get("url") and article.get("uri") in (a | b)}
            supplemental_union["available_examples"] = [metadata[k] for k in sorted(metadata)[:3]]
    overlap = []
    for i, left in enumerate(compared):
        for right in compared[i + 1:]:
            a = {r["uri"] for r in left["articles"] if r["uri"]}
            b = {r["uri"] for r in right["articles"] if r["uri"]}
            overlap.append({"left": left["id"], "right": right["id"], "shared_page1_uris": len(a & b)})
    output = {"versions": context.versions, "results": results, "reserved_tokens": reservations * 20,
              "budget_reconciliation": budget(engine),
              "identifier_frame_comparison": frame_comparison,
              "supplemental_union": supplemental_union,
              "dispatches": reservations, "completed_results": len(results),
              "missing_results": reservations - len(results), "model_calls": 0,
              "explicitly_reported_tokens": sum(known_costs),
              "dispatches_with_unavailable_billing": reservations - len(known_costs),
              "overlap": overlap,
              "unique_collected_uris": len({a["uri"] for r in results for a in r["articles"] if a["uri"]}),
              "expanded_match_increase_percent": ((compared[1]["total"] / compared[0]["total"] - 1) * 100)
                  if len(compared) == 3 and all(r["total"] for r in compared) else None,
              "calculation": "Match increase=(expanded_total/base_total-1)*100. Overlap uses exact provider URI equality, page 1 only; not recall, precision, or incident counts."}
    identifier = engine.ledger.record(session, "newsapi_overview", str(uuid.uuid4()), output)
    return {"id": identifier, **output}
