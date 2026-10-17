"""Account-bound archive verification and calendar-year collection; no inference."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import time
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .newsapi_probe import transport

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-calendar-collection-4000-total-v1"
WORDS = ["hack", "gehackt", "hackers", "ransomware", "datalek", "datalekken", "cyberaanval", "cyberaanvallen"]
PERIODS = [("2023-10-15", "2023-12-31"), ("2024-01-01", "2024-12-31"),
           ("2025-01-01", "2025-12-31"), ("2026-01-01", "2026-10-15")]
BACKFILL_PERIODS = [("2020-01-01", "2020-12-31"), ("2021-01-01", "2021-12-31"),
                    ("2022-01-01", "2022-12-31"), ("2023-01-01", "2023-10-14")]
CONTROL = {"endpointVariant": "sdk", "action": "getArticles", "resultType": "articles",
           "lang": "nld", "dateStart": "2024-01-01", "dateEnd": "2024-01-02",
           "articlesCount": 100, "articlesPage": 1, "includeArticleBody": False,
           "articlesSortBy": "date", "articlesSortByAsc": True}


def diagnostics() -> list[Json]:
    direct = {**CONTROL, "endpointVariant": "rest", "dateStart": "2024-01-01", "dateEnd": "2024-12-31"}
    complex_request = {k: v for k, v in direct.items() if k not in {"lang", "dateStart", "dateEnd"}}
    complex_request.update(endpointVariant="sdk", query=canonical({"$query": {"$and": [
        {"dateStart": "2024-01-01", "dateEnd": "2024-12-31"}, {"lang": "nld"}]}}))
    return [direct, complex_request]


def collection_request(period: tuple[str, str], page: int) -> Json:
    return {"endpointVariant": "rest", "action": "getArticles", "resultType": "articles",
        "keyword": WORDS, "keywordOper": "or", "keywordSearchMode": "phrase", "keywordLoc": "body,title",
        "lang": "nld", "dateStart": period[0], "dateEnd": period[1], "dataType": "news",
        "isDuplicateFilter": "keepAll", "includeArticleBody": True, "articlesArticleBodyLen": -1,
        "articlesPage": page, "articlesCount": 100, "articlesSortBy": "date", "articlesSortByAsc": True}


def number(value: object) -> float | None:
    try:
        result = Decimal(str(value))
        return float(result) if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def saved(engine: Research, kind: str, versions: dict[str, str] | None) -> list[Json]:
    values = [{"id": row["id"], **json.loads(row["payload"])} for row in engine.ledger.db.execute(
        "SELECT id,payload FROM records WHERE kind=? ORDER BY created_event", (kind,))]
    return [row for row in values if versions is None or row["versions"] == versions]


def dispatch(engine: Research, session: str, context: Context, parameters: Json, purpose: str,
             account_ceiling: int = 4000) -> Json:
    require_active(engine, session)
    # Billing projection references immutable receipts, avoiding repeated full-text reads.
    missing = engine.ledger.db.execute("SELECT id FROM records WHERE kind='newsapi_collection_receipt' AND id NOT IN (SELECT json_extract(payload,'$.receipt_id') FROM records WHERE kind='newsapi_collection_cost')").fetchall()
    for row in missing:
        full = engine.ledger.get(row["id"], "newsapi_collection_receipt")
        save_cost(engine, session, row["id"], full)
    receipts = saved(engine, "newsapi_collection_cost", None)
    intents = saved(engine, "newsapi_collection_intent", None)
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
        if used + sum(r["billed_tokens"] for r in unreflected) + 5 > account_ceiling:
            raise ResearchError(f"{account_ceiling} total account usage target reached; next request blocked")
        if any(r["billed_tokens"] is not None and r["billed_tokens"] > 5 for r in unreflected):
            raise ResearchError("Single-year charge exceeded five-token bound")
    attempt = str(uuid.uuid4())
    engine.ledger.record(session, "newsapi_collection_intent", attempt,
        {"attempt": attempt, "versions": context.versions, "parameters": parameters,
         "purpose": purpose, "started_at": utc(), "reserved_tokens": 5,
         "total_account_target": 4000, "account_ceiling": account_ceiling,
         "authentication_omitted": True, "automatic_retries": 0})
    status, headers, raw = transport(parameters)
    key = os.environ.get("EVENTREGISTRY_API_KEY", "")
    if key and (key.encode() in raw or key in canonical(headers)):
        raise ResearchError("Credential echo rejected; outcome remains reserved")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError):
        parsed = {"error_type": "non_json_response"}
    if not isinstance(parsed, dict):
        raise ResearchError("Unexpected provider response type")
    artifact = None
    quarantined = 0
    try:
        require_no_credentials(parsed)
    except ResearchError:
        # Preserve membership and hashes, never a matched value or raw secret-like text.
        section = parsed.get("articles", {})
        if not purpose.startswith("collect_") or not isinstance(section, dict) or not isinstance(section.get("results"), list):
            raise ResearchError("Unretainable response outside registered article quarantine") from None
        permitted = []
        for article in section["results"]:
            try:
                require_no_credentials(article)
                permitted.append(article)
            except ResearchError:
                locator = {}
                unavailable = []
                for field in ["uri", "date", "lang", "url"]:
                    try:
                        require_no_credentials(article.get(field))
                        locator[field] = article.get(field)
                    except ResearchError:
                        unavailable.append(field)
                permitted.append({**locator, "quarantined": True, "source_hash": digest(article),
                                  "unavailable_locator_fields": unavailable,
                                  "retention_reason": "credential_pattern_no_text_retained"})
                quarantined += 1
        parsed = {**parsed, "articles": {**section, "results": permitted}}
        require_no_credentials(parsed)
        engine.ledger.append(session, "newsapi.collection.response.quarantined", {
            "attempt": attempt, "raw_sha256": hashlib.sha256(raw).hexdigest(), "quarantined_articles": quarantined})
    else:
        artifact = engine.ledger.artifacts.put_bytes(raw)
        engine.ledger.append(session, "newsapi.collection.response.saved", {"artifact": artifact, "attempt": attempt})
    result = {"attempt": attempt, "versions": context.versions, "purpose": purpose,
              "parameters": parameters, "http_status": status, "headers": headers,
              "raw_response": artifact, "response": parsed, "completed_at": utc(),
              "raw_sha256": hashlib.sha256(raw).hexdigest(), "quarantined_articles": quarantined,
              "billed_tokens": number(headers.get("req-tokens"))}
    identifier = engine.ledger.record(session, "newsapi_collection_receipt", attempt, result)
    save_cost(engine, session, identifier, result)
    return {"id": identifier, **result}


def save_cost(engine: Research, session: str, identifier: str, receipt: Json) -> None:
    require_active(engine, session)
    engine.ledger.record(session, "newsapi_collection_cost", receipt["attempt"], {
        "receipt_id": identifier, "attempt": receipt["attempt"], "versions": receipt["versions"],
        "purpose": receipt["purpose"], "http_status": receipt["http_status"], "billed_tokens": receipt["billed_tokens"],
        "response": {k: receipt["response"].get(k) for k in ["usedTokens", "availableTokens"]}
            if receipt["purpose"].startswith("usage") else {}})


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if data.get("action") == "event_id_matching":
        from .newsapi_event_matching_run import run as event_id_matching
        return event_id_matching(engine, session, context, data)
    if data.get("action") == "event_metadata_repair":
        from .newsapi_metadata_repair import run as event_metadata_repair
        return event_metadata_repair(engine, session, context, data)
    if data.get("action") == "event_uri_diagnosis":
        from .newsapi_event_diagnosis import run as event_uri_diagnosis
        return event_uri_diagnosis(engine, session, context, data)
    if data.get("action") == "event_uri_coverage":
        from .newsapi_event_coverage import run as event_uri_coverage
        return event_uri_coverage(engine, session, context, data)
    if data.get("action") == "id_manifest_resolution_diagnostic":
        from .newsapi_id_manifest_final_audit import diagnose
        return diagnose(engine, session, context, data)
    if data.get("action") in {"id_manifest_resolution_prepare", "id_manifest_resolution"}:
        from .newsapi_id_manifest_resolution_run import prepare, run as resolve
        return (prepare if data["action"] == "id_manifest_resolution_prepare" else resolve)(engine, session, context, data)
    if data.get("action") in {"id_manifest_archive_repair_prepare", "id_manifest_archive_repair"}:
        from .newsapi_id_manifest_archive_repair import prepare, run as repair
        return (prepare if data["action"] == "id_manifest_archive_repair_prepare" else repair)(engine, session, context, data)
    if data.get("action") in {"id_manifest_minimal_prepare", "id_manifest_minimal_recovery"}:
        from .newsapi_id_manifest_minimal_recovery import prepare, run as minimal_recover
        return (prepare if data["action"] == "id_manifest_minimal_prepare" else minimal_recover)(engine, session, context, data)
    if data.get("action") == "id_manifest_final_source":
        from .newsapi_id_manifest_final_audit import source as id_manifest_final_source
        return id_manifest_final_source(engine, session, context, data)
    if data.get("action") == "id_manifest_final_audit":
        from .newsapi_id_manifest_final_audit import run as id_manifest_final_audit
        return id_manifest_final_audit(engine, session, context, data)
    if data.get("action") == "id_manifest_block_source":
        from .newsapi_id_manifest_block_proof import source as id_manifest_block_source
        return id_manifest_block_source(engine, session, context, data)
    if data.get("action") == "id_manifest_block_proof":
        from .newsapi_id_manifest_block_proof import run as id_manifest_block_proof
        return id_manifest_block_proof(engine, session, context, data)
    if data.get("action") == "id_manifest_quarter_proof":
        from .newsapi_id_manifest_quarter_proof import run as id_manifest_quarter_proof
        return id_manifest_quarter_proof(engine, session, context, data)
    if data.get("action") == "id_manifest_proof":
        from .newsapi_id_manifest_proof import run as id_manifest_proof
        return id_manifest_proof(engine, session, context, data)
    if data.get("action") == "id_manifest_details":
        from .newsapi_id_manifest_details import run as id_manifest_details
        return id_manifest_details(engine, session, context, data)
    if data.get("action") == "id_manifest_test":
        from .newsapi_id_manifest import run as id_manifest_test

        return id_manifest_test(engine, session, context, data)
    if data.get("action") == "retrieval_audit":
        from .newsapi_retrieval_audit import run as retrieval_audit

        return retrieval_audit(engine, session, context, data)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    backfill = data.get("action") in {"backfill", "backfill_consistency", "backfill_materialize", "backfill_missingness", "backfill_topic_export"}
    periods = BACKFILL_PERIODS if backfill else PERIODS
    if (policy.get("method") != METHOD
            or policy.get("total_account_target") != 4000 or policy.get("monthly_allowance") != 5000
            or policy.get("words") != WORDS or policy.get("periods") != [list(p) for p in periods]):
        raise ResearchError("Exact authorized 4000/5000 account-bound collection policy required")
    existing = saved(engine, "newsapi_collection_check", context.versions)
    if data.get("action") == "report":
        if not existing:
            raise ResearchError("No stored archive check is available")
        return existing[-1]
    if data.get("action") == "materialize":
        from .newsapi_materialize import materialize

        return materialize(engine, session, context)
    if data.get("action") == "backfill_materialize":
        from .newsapi_materialize import materialize

        return materialize(engine, session, context, BACKFILL_PERIODS, "backfill-")
    if data.get("action") in {"missingness", "backfill_missingness"}:
        from .newsapi_missingness import run as missingness

        return missingness(engine, session, context, data)
    if data.get("action") in {"topic_export", "backfill_topic_export"}:
        from .newsapi_topic_export import run as topic_export

        return topic_export(engine, session, context, data)
    if data.get("action") == "backfill_consistency":
        if policy.get("consistency_rule") != "empty-zero-total-within-prior-positive-pages-v1":
            raise ResearchError("Register provider consistency inspection rule first")
        result = {**collection_state(engine, BACKFILL_PERIODS), "versions": context.versions,
                  "network_calls": 0, "model_calls": 0, "generated_at": utc()}
        identifier = engine.ledger.record(session, "newsapi_collection_consistency", str(uuid.uuid4()), result)
        return {"id": identifier, **result}
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit online execution required")
    if backfill:
        if policy.get("user_authorized_backfill_2020") is not True:
            raise ResearchError("Explicit 2020 backfill authorization required")
        return collect(engine, session, context, data, policy, periods)
    if data.get("action") == "collect":
        return collect(engine, session, context, data, policy)
    if data.get("action") == "recover":
        return recover(engine, session, context, policy)
    if data.get("action") not in {"check", "diagnose"}:
        raise ResearchError("Archive access must be verified before enabling collection")
    requests = diagnostics() if data.get("action") == "diagnose" else [CONTROL]
    if data.get("action") == "diagnose" and policy.get("diagnostic_requests") != requests:
        raise ResearchError("Register exact alternative archive diagnostics before dispatch")
    if existing:
        raise ResearchError("Archive check already recorded; preserve it and do not silently repeat paid tests")
    baseline = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_archive_check")
    before = baseline["response"]
    if (baseline["http_status"] != 200 or number(before.get("usedTokens")) is None
            or number(before.get("availableTokens")) != 5000):
        raise ResearchError("Account balance unavailable or allowance differs from authorized 5000")
    observations = []
    for index, parameters in enumerate(requests):
        probe = dispatch(engine, session, context, parameters, "archive_access_control_" + str(index))
        after = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_archive_check_" + str(index))
        section = probe["response"].get("articles", {})
        articles = section.get("results", []) if isinstance(section, dict) else []
        dates = [a.get("date", "") for a in articles if isinstance(a, dict)]
        end = "2024-12-31" if data.get("action") == "diagnose" else "2024-01-02"
        proof = (probe["http_status"] == 200 and any("2024-01-01" <= d <= end for d in dates))
        observations.append({"request": parameters, "receipt": probe["id"], "usage_receipt": after["id"],
            "returned": len(articles), "http_status": probe["http_status"], "headers": probe["headers"],
            "billed_tokens": probe["billed_tokens"], "proof": proof})
        if proof or probe["http_status"] in {401, 403, 429, 503}:
            break
    a, b = number(before.get("usedTokens")), number(after["response"].get("usedTokens"))
    result = {"versions": context.versions, "archive_access": "verified_by_historical_articles" if proof else "not_verified",
              "baseline_used": a, "final_observed_used": b, "account_observed_delta": b-a if a is not None and b is not None else None,
              "allowance": before.get("availableTokens"), "target_used": 4000,
              "remaining_to_target": max(0, 4000-b) if b is not None else None,
              "receipt_ids": [baseline["id"], probe["id"], after["id"]],
              "diagnostics": observations, "control_date_end": end,
              "archive_headers": probe["headers"], "archive_http_status": probe["http_status"],
              "archive_provider_total": section.get("totalResults") if isinstance(section, dict) else None,
              "archive_control_returned": len(articles), "archive_control_dates": sorted(set(dates)),
              "archive_control_examples": [{k: a.get(k) for k in ["title", "url", "date"]} for a in articles[:3]],
              "archive_reported_cost": probe["billed_tokens"], "collected_keyword_articles": 0,
              "pending_years": [p[0][:4] for p in PERIODS], "model_calls": 0,
              "account_delta_attribution": "Observed balance difference; may include usage endpoint charges or concurrent account activity; not fabricated per-request billing"}
    identifier = engine.ledger.record(session, "newsapi_collection_check", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def collect(engine: Research, session: str, context: Context, data: Json, policy: Json,
            periods: list[tuple[str, str]] | None = None) -> Json:
    periods = PERIODS if periods is None else periods
    account_ceiling = (5000 if periods == BACKFILL_PERIODS and policy.get("complete_requested_history_within_allowance") is True else 4000)
    proof = engine.ledger.get(policy.get("archive_check", ""), "newsapi_collection_check")
    if (policy.get("collection_enabled") is not True
            or proof["archive_access"] != "verified_by_historical_articles"
            or policy.get("templates") != [collection_request(p, 1) for p in periods]):
        raise ResearchError("Verified archive check and exact full-text collection templates required")
    limit = data.get("pages", 20)
    if not isinstance(limit, int) or not 1 <= limit <= 40:
        raise ResearchError("Collect 1 through40 pages per checkpoint")
    baseline = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_collection_batch", account_ceiling)
    if (baseline["http_status"] != 200 or number(baseline["response"].get("usedTokens")) is None
            or number(baseline["response"].get("availableTokens")) != 5000):
        raise ResearchError("Live account usage unavailable")
    stop = "checkpoint"
    state = collection_state(engine, periods)
    permitted = policy.get("inconsistent_response_retry_receipts", [])
    if any(r["receipt_id"] not in permitted for r in state["unresolved_inconsistent_responses"]):
        raise ResearchError("Inconsistent provider response requires a versioned explicit retry decision")
    for _ in range(limit):
        candidates = [row for row in state["years"] if not row["exhausted"]]
        if not candidates:
            stop = "query_exhausted"
            break
        # Balance first-page coverage and continuing page counts across years.
        year = min(candidates, key=lambda row: (row["pages"], row["year"]))
        period = next(p for p in periods if p[0][:4] == year["year"])
        page = year["pages"] + 1
        try:
            receipt = dispatch(engine, session, context, collection_request(period, page),
                               f"collect_{year['year']}_page_{page}", account_ceiling)
        except ResearchError as error:
            if str(error).startswith(f"{account_ceiling} total account usage"):
                stop = "budget_target"
                break
            raise
        section = receipt["response"].get("articles", {})
        articles = section.get("results") if isinstance(section, dict) else None
        if receipt["http_status"] != 200 or not isinstance(articles, list):
            stop = "failed_page"
            break
        if not articles and section.get("totalResults") == 0 and (year.get("provider_total") or 0) > 0:
            stop = "inconsistent_provider_response"
            break
        if any(not isinstance(a, dict) or not period[0] <= str(a.get("date", "")) <= period[1]
               or a.get("lang") != "nld" for a in articles):
            stop = "scope_validation_failed"
            break
        if receipt["billed_tokens"] is None:
            stop = "unavailable_request_cost"
            break
        if receipt["billed_tokens"] > 5:
            stop = "charge_exceeded_bound"
            break
        year["pages"] = page
        year["provider_total"] = section.get("totalResults")
        year["exhausted"] = len(articles) < 100 or (isinstance(section.get("pages"), int) and section["pages"] <= page)
        print(json.dumps({"year": year["year"], "page": page, "returned": len(articles),
                          "cost": receipt["billed_tokens"], "provider_total": section.get("totalResults")}), flush=True)
        time.sleep(.6)
    after = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_collection_batch", account_ceiling)
    result = {**collection_state(engine, periods), "versions": context.versions, "stop_reason": stop,
              "periods": periods,
              "baseline_used": number(baseline["response"].get("usedTokens")),
              "final_observed_used": number(after["response"].get("usedTokens")),
              "target_used": 4000, "allowance": 5000, "model_calls": 0, "scored": 0,
              "account_ceiling": account_ceiling,
              "archive_check": policy["archive_check"], "completed_at": utc(),
              "usage_receipts": [baseline["id"], after["id"]]}
    if result["final_observed_used"] is not None:
        result["remaining_to_target"] = max(0, 4000-result["final_observed_used"])
    identifier = engine.ledger.record(session, "newsapi_collection_progress", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def collection_state(engine: Research, periods: list[tuple[str, str]] | None = None) -> Json:
    periods = PERIODS if periods is None else periods
    receipts = [r for r in saved(engine, "newsapi_collection_receipt", None) if r["purpose"].startswith("collect_")
                and (r["parameters"].get("dateStart"), r["parameters"].get("dateEnd")) in periods]
    years, unique, examples, anomalies = [], set(), [], []
    unresolved: list[Json] = []
    for period in periods:
        selected = [r for r in receipts if r["parameters"]["dateStart"] == period[0]]
        good, bad = consistent_pages(selected)
        anomalies.extend(bad)
        unresolved.extend(r for r in bad if not r["successful_retry"])
        articles = [a for r in good for a in r["response"]["articles"]["results"]]
        valid = [a for a in articles if isinstance(a, dict) and period[0] <= str(a.get("date", "")) <= period[1] and a.get("lang") == "nld"]
        for article in valid:
            identity = article.get("uri") or article.get("url") or article.get("source_hash")
            if identity:
                unique.add(identity)
        good.sort(key=lambda r: r["parameters"]["articlesPage"])
        last = good[-1]["response"]["articles"] if good else {}
        exhausted = bool(good) and (len(last["results"]) < 100 or
            (isinstance(last.get("pages"), int) and last["pages"] <= good[-1]["parameters"]["articlesPage"]))
        indices = {r["parameters"]["articlesPage"] for r in good}
        contiguous = 0
        while contiguous + 1 in indices:
            contiguous += 1
        years.append({"year": period[0][:4], "pages": contiguous, "failed_pages": len(selected)-len(good),
                      "returned": len(valid), "scope_invalid": len(articles)-len(valid),
                      "provider_total": last.get("totalResults"), "exhausted": exhausted,
                      "missing_body": sum(not isinstance(a.get("body"), str) or not a["body"].strip() for a in valid),
                      "quarantined": sum(a.get("quarantined") is True for a in valid),
                      "reported_cost": sum(r["billed_tokens"] for r in selected if r["billed_tokens"] is not None),
                      "unavailable_costs": sum(r["billed_tokens"] is None for r in selected)})
        examples.extend([{k: a.get(k) for k in ["uri", "title", "url", "date"]} for a in valid[:1]])
    return {"years": years, "unique_articles": len(unique), "returned_articles": sum(y["returned"] for y in years),
            "missing_body": sum(y["missing_body"] for y in years), "failed_pages": sum(y["failed_pages"] for y in years),
            "quarantined": sum(y["quarantined"] for y in years),
            "scope_invalid": sum(y["scope_invalid"] for y in years),
            "reported_collection_cost": sum(y["reported_cost"] for y in years),
            "unavailable_costs": sum(y["unavailable_costs"] for y in years), "examples": examples,
            "receipt_ids": [r["id"] for r in receipts],
            "inconsistent_responses": anomalies, "unresolved_inconsistent_responses": unresolved}


def consistent_pages(receipts: list[Json]) -> tuple[list[Json], list[Json]]:
    shaped = [r for r in receipts if r["http_status"] == 200
              and isinstance(r["response"].get("articles", {}).get("results"), list)]
    maximum = max((r["response"]["articles"].get("totalResults", 0) or 0 for r in shaped), default=0)
    bad = [r for r in shaped if maximum > 0 and not r["response"]["articles"]["results"]
           and r["response"]["articles"].get("totalResults") == 0
           and r["parameters"]["articlesPage"] <= (maximum + 99) // 100]
    good = [r for r in shaped if r not in bad]
    anomalies = [{"receipt_id": r["id"], "year": r["parameters"]["dateStart"][:4],
        "page": r["parameters"]["articlesPage"], "observed_positive_total": maximum,
        "response_top_level_keys": sorted(r["response"]),
        "provider_diagnostics": {k: r["response"][k] for k in ["error", "warning", "errorCode", "message"] if k in r["response"]},
        "reason": "Empty page reports zero total despite earlier positive matches within expected pages",
        "successful_retry": any(canonical(r["parameters"]) == canonical(ok["parameters"]) for ok in good)} for r in bad]
    return good, anomalies


def recover(engine: Research, session: str, context: Context, policy: Json) -> Json:
    reason = policy.get("recovery_reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ResearchError("Register an explicit recovery and retry rationale")
    completed = {r["attempt"] for r in saved(engine, "newsapi_collection_receipt", None)}
    unknown = [r for r in saved(engine, "newsapi_collection_intent", None) if r["attempt"] not in completed]
    if not unknown or any(not r["purpose"].startswith("collect_") for r in unknown):
        raise ResearchError("Recovery must identify interrupted collection attempts only")
    for intent in unknown:
        engine.ledger.record(session, "newsapi_collection_resolution", intent["attempt"], {
            "attempt": intent["attempt"], "original_intent": intent["id"], "versions": context.versions,
            "reason": reason, "outcome": "Response not retained after source-locator credential-pattern rejection",
            "billed_tokens": None, "missing_processing": True,
            "retry": "One explicit retry permitted after corrected retention and fresh account reconciliation; old attempt preserved"})
        tombstone = {"attempt": intent["attempt"], "versions": intent["versions"],
            "purpose": intent["purpose"], "parameters": intent["parameters"], "http_status": None,
            "headers": {}, "raw_response": None, "raw_sha256": None, "response": {"error_type": "unretained_response"},
            "billed_tokens": None, "completed_at": utc(), "resolved_unknown": True}
        identifier = engine.ledger.record(session, "newsapi_collection_receipt", intent["attempt"], tombstone)
        save_cost(engine, session, identifier, tombstone)
    after = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_explicit_recovery")
    result = {**collection_state(engine), "versions": context.versions, "stop_reason": "recovery_reconciled",
        "final_observed_used": number(after["response"].get("usedTokens")), "target_used": 4000,
        "allowance": 5000, "recovered_attempts": [r["attempt"] for r in unknown], "model_calls": 0,
        "recovery_reason": reason, "usage_receipts": [after["id"]]}
    identifier = engine.ledger.record(session, "newsapi_collection_progress", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
