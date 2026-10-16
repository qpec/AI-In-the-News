"""Account-bound archive verification and calendar-year collection; no inference."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, require_no_credentials, utc
from .newsapi_probe import transport

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-calendar-collection-4000-total-v1"
WORDS = ["hack", "gehackt", "hackers", "ransomware", "datalek", "datalekken", "cyberaanval", "cyberaanvallen"]
PERIODS = [("2023-10-15", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-10-15")]
CONTROL = {"endpointVariant": "sdk", "action": "getArticles", "resultType": "articles",
           "lang": "nld", "dateStart": "2024-01-01", "dateEnd": "2024-01-02",
           "articlesCount": 100, "articlesPage": 1, "includeArticleBody": False,
           "articlesSortBy": "date", "articlesSortByAsc": True}


def number(value: object) -> float | None:
    try:
        result = Decimal(str(value))
        return float(result) if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def saved(engine: Research, kind: str, versions: dict[str, str]) -> list[Json]:
    values = [{"id": row["id"], **json.loads(row["payload"])} for row in engine.ledger.db.execute(
        "SELECT id,payload FROM records WHERE kind=? ORDER BY created_event", (kind,))]
    return [row for row in values if row["versions"] == versions]


def dispatch(engine: Research, session: str, context: Context, parameters: Json, purpose: str) -> Json:
    receipts = saved(engine, "newsapi_collection_receipt", context.versions)
    intents = saved(engine, "newsapi_collection_intent", context.versions)
    if len(receipts) != len(intents):
        raise ResearchError("Unknown account dispatch outcome; automatic re-dispatch blocked")
    usage = [r for r in receipts if r["purpose"].startswith("usage") and r["http_status"] == 200]
    if parameters != {"endpointVariant": "usage"}:
        if not usage or number(usage[-1]["response"].get("usedTokens")) is None:
            raise ResearchError("A fresh valid account balance is required")
        used = float(usage[-1]["response"]["usedTokens"])
        unreflected = [r for r in receipts[receipts.index(usage[-1])+1:] if not r["purpose"].startswith("usage")]
        if any(r["billed_tokens"] is None for r in unreflected):
            raise ResearchError("Unavailable billing requires account reconciliation before another search")
        if used + sum(r["billed_tokens"] for r in unreflected) + 5 > 4000:
            raise ResearchError("4000 total account usage target reached; next request blocked")
        if any(r["billed_tokens"] is not None and r["billed_tokens"] > 5 for r in unreflected):
            raise ResearchError("Single-year charge exceeded five-token bound")
    attempt = str(uuid.uuid4())
    engine.ledger.record(session, "newsapi_collection_intent", attempt,
        {"attempt": attempt, "versions": context.versions, "parameters": parameters,
         "purpose": purpose, "started_at": utc(), "reserved_tokens": 5,
         "total_account_target": 4000, "authentication_omitted": True, "automatic_retries": 0})
    status, headers, raw = transport(parameters)
    key = os.environ.get("EVENTREGISTRY_API_KEY", "")
    if key and (key.encode() in raw or key in canonical(headers)):
        raise ResearchError("Credential echo rejected; outcome remains reserved")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError):
        parsed = {"error_type": "non_json_response"}
    require_no_credentials(parsed)
    if not isinstance(parsed, dict):
        raise ResearchError("Unexpected provider response type")
    artifact = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "newsapi.collection.response.saved", {"artifact": artifact, "attempt": attempt})
    result = {"attempt": attempt, "versions": context.versions, "purpose": purpose,
              "parameters": parameters, "http_status": status, "headers": headers,
              "raw_response": artifact, "response": parsed, "completed_at": utc(),
              "billed_tokens": number(headers.get("req-tokens"))}
    identifier = engine.ledger.record(session, "newsapi_collection_receipt", attempt, result)
    return {"id": identifier, **result}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("method") != METHOD
            or policy.get("total_account_target") != 4000 or policy.get("monthly_allowance") != 5000
            or policy.get("words") != WORDS or policy.get("periods") != [list(p) for p in PERIODS]):
        raise ResearchError("Exact authorized 4000/5000 account-bound collection policy required")
    existing = saved(engine, "newsapi_collection_check", context.versions)
    if data.get("action") == "report":
        if not existing:
            raise ResearchError("No stored archive check is available")
        return existing[-1]
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit online execution required")
    if data.get("action") != "check":
        raise ResearchError("Archive access must be verified before enabling collection")
    if existing:
        raise ResearchError("Archive check already recorded; preserve it and do not silently repeat paid tests")
    baseline = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_archive_check")
    before = baseline["response"]
    if (baseline["http_status"] != 200 or number(before.get("usedTokens")) is None
            or number(before.get("availableTokens")) != 5000):
        raise ResearchError("Account balance unavailable or allowance differs from authorized 5000")
    probe = dispatch(engine, session, context, CONTROL, "archive_access_control")
    after = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_archive_check")
    section = probe["response"].get("articles", {})
    articles = section.get("results", []) if isinstance(section, dict) else []
    dates = [a.get("date", "") for a in articles if isinstance(a, dict)]
    proof = (probe["http_status"] == 200 and any("2024-01-01" <= d <= "2024-01-02" for d in dates))
    a, b = number(before.get("usedTokens")), number(after["response"].get("usedTokens"))
    result = {"versions": context.versions, "archive_access": "verified_by_historical_articles" if proof else "not_verified",
              "baseline_used": a, "final_observed_used": b, "account_observed_delta": b-a if a is not None and b is not None else None,
              "allowance": before.get("availableTokens"), "target_used": 4000,
              "remaining_to_target": max(0, 4000-b) if b is not None else None,
              "receipt_ids": [baseline["id"], probe["id"], after["id"]],
              "archive_headers": probe["headers"], "archive_http_status": probe["http_status"],
              "archive_provider_total": section.get("totalResults") if isinstance(section, dict) else None,
              "archive_control_returned": len(articles), "archive_control_dates": sorted(set(dates)),
              "archive_control_examples": [{k: a.get(k) for k in ["title", "url", "date"]} for a in articles[:3]],
              "archive_reported_cost": probe["billed_tokens"], "collected_keyword_articles": 0,
              "pending_years": [p[0][:4] for p in PERIODS], "model_calls": 0,
              "account_delta_attribution": "Observed balance difference; may include usage endpoint charges or concurrent account activity; not fabricated per-request billing"}
    identifier = engine.ledger.record(session, "newsapi_collection_check", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
