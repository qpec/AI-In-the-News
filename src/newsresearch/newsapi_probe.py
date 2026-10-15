"""Bounded NewsAPI.ai retrieval diagnostics; no model inference or accepted findings."""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
import urllib.error
import urllib.request
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc

if TYPE_CHECKING:
    from .runtime import Research

ENDPOINT = "https://eventregistry.org/api/v1/article/getArticles"
AUTHORIZATION = "nl-cyber-search-pilot-2026-10-15-200"
RESERVATION = 20
ALLOWED = {"action", "keyword", "keywordOper", "keywordLoc", "keywordSearchMode", "lang",
           "dateStart", "dateEnd", "sourceLocationUri", "locationUri", "conceptUri",
           "articlesPage", "articlesCount", "articlesSortBy", "articlesSortByAsc",
           "resultType", "dataType", "isDuplicateFilter", "includeArticleBody", "query"}
SAFE_HEADERS = {"date", "x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining",
                "req-action", "req-tokens", "req-archive", "req-chargable", "req-years",
                "req-article-search"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


def transport(parameters: Json) -> tuple[int, Json, bytes]:
    key = os.environ.get("EVENTREGISTRY_API_KEY")
    if not key:
        raise ResearchError("NewsAPI.ai credential unavailable")
    # The provider requires a JSON authentication field. It is added only here,
    # outside the exact persisted search parameters, and never logged.
    wire = canonical({**parameters, "apiKey": key}).encode("utf-8")
    request = urllib.request.Request(ENDPOINT, data=wire, method="POST",
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
            or policy.get("method") != "newsapi-probe-approval-v1"
            or policy.get("authorization_id") != AUTHORIZATION
            or policy.get("max_tokens") != 200):
        raise ResearchError("Concrete 200-token pilot authorization and online execution required")
    parameters = data.get("parameters", {})
    search = parameters
    if "query" in parameters:
        query = json.loads(parameters["query"]) if isinstance(parameters["query"], str) else parameters["query"]
        search = query.get("$query", {})
    if (parameters not in policy.get("requests", []) or set(parameters) - ALLOWED
            or parameters.get("articlesCount") != 100 or parameters.get("articlesPage") != 1
            or parameters.get("resultType") != "articles"
            or parameters.get("action") != "getArticles"
            or parameters.get("includeArticleBody") is not False
            or not "2023-10-15" <= search.get("dateStart", "") <= search.get("dateEnd", "") <= "2026-10-15"):
        raise ResearchError("Request differs from the registered bounded pilot")
    reservations = [json.loads(row[0]) for row in engine.ledger.db.execute(
        "SELECT payload FROM records WHERE kind='newsapi_reservation'")]
    same = [r for r in reservations if r["authorization_id"] == AUTHORIZATION]
    if any(r["parameters"] == parameters for r in same):
        raise ResearchError("Request already reserved; unknown outcomes cannot be retried")
    if sum(r["reserved_tokens"] for r in same) + RESERVATION > 200:
        raise ResearchError("200-token authorization exhausted")
    attempt = str(uuid.uuid4())
    engine.ledger.record(session, "newsapi_reservation", attempt, {
        "authorization_id": AUTHORIZATION, "parameters": parameters, "versions": context.versions,
        "reserved_tokens": RESERVATION, "started_at": utc(), "endpoint": ENDPOINT,
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
    articles = parsed.get("articles", {})
    success = status == 200 and isinstance(articles, dict) and isinstance(articles.get("results"), list)
    rows = articles.get("results", []) if success else []
    output = {"versions": context.versions, "parameters": parameters, "attempt": attempt,
              "authorization_id": AUTHORIZATION, "http_status": status, "headers": headers,
              "raw_response": raw_ref, "retrieved_at": started, "completed_at": utc(),
              "status": "completed" if success else "failed", "reserved_tokens": RESERVATION,
              "cumulative_reserved_tokens": sum(r["reserved_tokens"] for r in same) + RESERVATION,
              "provider_total": articles.get("totalResults") if success else None,
              "returned": len(rows), "scored": 0, "model_calls": 0,
              "articles": rows, "failure": None if success else "http_or_provider_error",
              "missing": "All pages after page 1 remain uncollected; no relevance assessment",
              "actual_billed_tokens": headers.get("req-tokens"), "actor": context.actor,
              "provider_notes": {k: v for k, v in parsed.items() if k != "articles"}}
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
                        "notes": {k: v for k, v in content.items() if k != "articles"},
                        "dates": sorted({str(a.get("date", "")) for a in result["articles"]}),
                        "articles": [{k: a.get(k) for k in ["uri", "title", "url", "date", "lang", "source"]}
                                     for a in result["articles"]]})
    reservations = engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='newsapi_reservation'").fetchone()[0]
    known_costs = [float(r["headers"]["req-tokens"]) for r in results if "req-tokens" in r["headers"]]
    compared = results[-3:]
    overlap = []
    for i, left in enumerate(compared):
        for right in compared[i + 1:]:
            a = {r["uri"] for r in left["articles"] if r["uri"]}
            b = {r["uri"] for r in right["articles"] if r["uri"]}
            overlap.append({"left": left["id"], "right": right["id"], "shared_page1_uris": len(a & b)})
    output = {"versions": context.versions, "results": results, "reserved_tokens": reservations * 20,
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
