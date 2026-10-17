"""Pure, bounded diagnostics for URI-list IDs with unavailable article metadata.

These helpers perform no transport, storage or research operation. Their caller
must register the exact templates and preserve receipts through Research.execute.
An unavailable URI is never silently excluded from the raw URI-list universe.
"""
from __future__ import annotations

from datetime import date
from math import ceil

from .common import Json, ResearchError
from .newsapi_collection import collection_request
from .newsapi_metadata import project_article_metadata

RESOLUTION_METHOD = "nl-cyber-id-manifest-resolution-v1"
MAX_PAGES = 30
PAGE_SIZE = 100
START = "2026-09-01"
END = "2026-10-15"


def _identifiers(ids: list[str], control: str | None = None) -> list[str]:
    values = [*ids, *([control] if control is not None else [])]
    if (len(ids) != 6 or len(values) != len(set(values)) or any(
            not isinstance(uri, str) or not uri or ":" in uri or any(c.isspace() for c in uri)
            for uri in values)):
        raise ResearchError("Resolution requires six distinct bare IDs and a separate control")
    return values


def enumeration(page: int) -> Json:
    """One of thirty unchanged-keyword, metadata-only ascending article pages."""
    if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= MAX_PAGES:
        raise ResearchError("Resolution enumeration is bounded to thirty pages")
    return {**collection_request((START, END), page), "includeArticleBody": False, "articleBodyLen": 0}


def minimal_enumeration(page: int, title: bool = True) -> Json:
    return {**enumeration(page), "includeArticleBasicInfo": True, "includeArticleTitle": title,
        "includeArticleUrl": False, "includeArticleImage": False, "includeSourceTitle": False}


def templates(ids: list[str], control: str) -> Json:
    values = _identifiers(ids, control)
    flags = {"includeArticleBody": False, "articleBodyLen": 0,
        "includeArticleTitle": True, "includeArticleUrl": True, "includeArticleBasicInfo": True,
        "includeSourceTitle": True}
    sdk = {"endpointVariant": "sdk", "action": "getArticle", "resultType": ["info"],
        "articleUri": values, **flags}
    exact = {"endpointVariant": "sdk", "action": "getArticles", "resultType": "articles",
        "articleUri": values, "dataType": ["news", "blog", "pr"], "articlesPage": 1,
        "articlesCount": PAGE_SIZE, **flags}
    pages = [enumeration(page) for page in range(1, MAX_PAGES + 1)]
    return {"control_sdk": sdk, "control_list": exact, "enumerations": pages, "all": [sdk, exact, *pages]}


def _metadata(article: Json) -> Json:
    # Historical v1 proof replay must reproduce its original exact field set.
    return project_article_metadata(article, version=1)


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _info(response: Json, expected: list[str], status: int | None) -> Json:
    rows: dict[str, Json] = {}
    global_error = response.get("error") if isinstance(response, dict) else None
    for uri in expected:
        item = response.get(uri) if isinstance(response, dict) else None
        info = item.get("info") if isinstance(item, dict) else None
        error = item.get("error") if isinstance(item, dict) else None
        row: Json = {"status": "unknown", "reason": "missing_or_mismatched_exact_id"}
        if status != 200:
            row = {"status": "unknown", "reason": "http_status", "http_status": status}
        elif global_error is not None:
            row = {"status": "provider_error", "reason": "top_level_error", "error": global_error}
        elif error is not None:
            invalid = isinstance(error, str) and error.strip().casefold() in {
                "invalid article uri", "invalid article uri.",
                f"invalid article uri ('{uri}') was provided.".casefold(),
            }
            row = {"status": "invalid_uri" if invalid else "provider_error", "error": error}
        elif isinstance(info, dict) and info.get("uri") == uri:
            row = {"status": "available", **_metadata(info)}
        rows[uri] = row
    unexpected = sorted(key for key, item in response.items() if key not in expected
        and isinstance(item, dict) and ("info" in item or "error" in item)) if isinstance(response, dict) else []
    return {"rows": rows, "unexpected_ids": unexpected, "provider_error": global_error,
        "http_status": status}


def _list(response: Json, expected: list[str], status: int | None) -> Json:
    section = response.get("articles") if isinstance(response, dict) else None
    section = section if isinstance(section, dict) else {}
    errors = []
    articles: dict[str, Json] = {}
    total = section.get("totalResults") if isinstance(section, dict) else None
    results = section.get("results") if isinstance(section, dict) else None
    if status != 200 or response.get("error") is not None:
        errors.append("http_or_provider_error")
    if not isinstance(results, list) or not _integer(total):
        errors.append("missing_results_or_total")
    else:
        for article in results:
            if not isinstance(article, dict) or not isinstance(article.get("uri"), str) or not article["uri"]:
                errors.append("invalid_article_identity")
                continue
            uri = article["uri"]
            if uri in articles:
                errors.append("duplicate_article_identity")
            articles[uri] = _metadata(article)
        if len(results) != total or len(results) > PAGE_SIZE:
            errors.append("incomplete_count")
        if section.get("page", 1) != 1 or section.get("pages", 1) not in (0, 1):
            errors.append("unexpected_pagination")
    unexpected = sorted(set(articles) - set(expected))
    if unexpected:
        errors.append("unexpected_article_ids")
    complete = not errors
    return {"complete": complete, "ids": sorted(articles), "articles": articles,
        "total": total, "unexpected_ids": unexpected, "diagnostics": sorted(set(errors)),
        "provider_error": response.get("error"), "http_status": status,
        "rows": {uri: ({"status": "available", **articles[uri]} if uri in articles else {
            "status": "not_returned" if complete else "unknown"}) for uri in expected}}


def parse_controls(sdk_response: Json, list_response: Json, ids: list[str], control: str,
                   original_response: Json | None = None, *, sdk_http_status: int | None = 200,
                   list_http_status: int | None = 200, original_http_status: int | None = 200) -> Json:
    values = _identifiers(ids, control)
    sdk = _info(sdk_response, values, sdk_http_status)
    original = _info(original_response or {}, ids, original_http_status)
    exact = _list(list_response, values, list_http_status)
    sdk_control = sdk["rows"][control]["status"] == "available" and not sdk["unexpected_ids"]
    list_control = exact["complete"] and exact["rows"][control]["status"] == "available"
    candidates = [uri for uri in ids if sdk_control and list_control
        and original["rows"][uri]["status"] == sdk["rows"][uri]["status"] == "invalid_uri"
        and uri not in exact["ids"]]
    return {"suspect_ids": list(ids), "control_id": control, "sdk": sdk, "original": original,
        "exact_list": exact, "sdk_control_success": sdk_control, "list_control_success": list_control,
        "both_controls_work": bool(sdk_control and list_control),
        "provider_unresolvable_candidates": sorted(candidates), "model_calls": 0}


def validate_enumeration(receipts: list[Json], saved_ids: list[str],
                         expected_ids: list[str] | None = None, *, allow_minimal: bool = False) -> Json:
    """Replay exact receipts; partial absence remains unknown, never a negative."""
    diagnostics: list[str] = []
    pages: dict[int, Json] = {}
    totals: list[int] = []
    articles: dict[str, Json] = {}
    duplicate_ids: set[str] = set()
    receipt_ids = []
    if len(saved_ids) != len(set(saved_ids)):
        raise ResearchError("Saved comparison IDs must be unique")
    if len(receipts) > MAX_PAGES:
        diagnostics.append("page_cap_exceeded")
    for receipt in receipts:
        receipt_ids.append(receipt.get("id"))
        parameters = receipt.get("parameters", {})
        page = parameters.get("articlesPage")
        if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= MAX_PAGES:
            diagnostics.append("page_outside_cap")
            continue
        allowed = [enumeration(page)]
        if allow_minimal:
            allowed.extend([minimal_enumeration(page), minimal_enumeration(page, False)])
        if parameters not in allowed:
            diagnostics.append("request_template_mismatch")
            continue
        if page in pages:
            diagnostics.append("duplicate_page")
        pages[page] = receipt
        response = receipt.get("response") or {}
        section = response.get("articles") if isinstance(response, dict) else None
        if (receipt.get("outcome") != "received" or receipt.get("http_status") != 200
                or receipt.get("headers", {}).get("req-archive") != "1"
                or response.get("error") is not None or not isinstance(section, dict)
                or not isinstance(section.get("results"), list) or not _integer(section.get("totalResults"))):
            diagnostics.append("invalid_page_response")
            continue
        total = section["totalResults"]
        totals.append(total)
        expected_pages = max(1, ceil(total / PAGE_SIZE))
        expected_count = min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE))
        if expected_pages > MAX_PAGES:
            diagnostics.append("provider_total_exceeds_cap")
        if (section.get("page", page) != page or section.get("pages", expected_pages) not in
                ({0, 1} if total == 0 else {expected_pages}) or len(section["results"]) != expected_count):
            diagnostics.append("page_count_or_pagination_mismatch")
        for article in section["results"]:
            if not isinstance(article, dict) or not isinstance(article.get("uri"), str) or not article["uri"]:
                diagnostics.append("invalid_article_identity")
                continue
            uri = article["uri"]
            if uri in articles:
                duplicate_ids.add(uri)
            articles[uri] = _metadata(article)
            publication = article.get("date")
            try:
                valid_date = isinstance(publication, str) and date.fromisoformat(publication).isoformat() == publication
            except ValueError:
                valid_date = False
            if not valid_date or not isinstance(publication, str) or not START <= publication <= END or article.get("lang") != "nld":
                diagnostics.append("article_scope_unknown_or_mismatched")
    if not receipts:
        diagnostics.append("no_receipts")
    total = totals[0] if totals else None
    if len(set(totals)) > 1:
        diagnostics.append("provider_total_drift")
    expected_pages = max(1, ceil(total / PAGE_SIZE)) if total is not None else None
    if expected_pages is None or set(pages) != set(range(1, expected_pages + 1)):
        diagnostics.append("noncontiguous_or_incomplete_pages")
    if duplicate_ids:
        diagnostics.append("duplicate_article_ids")
    if total is None or len(articles) != total:
        diagnostics.append("unique_count_mismatch")
    complete = not diagnostics
    ids = set(articles)
    saved = set(saved_ids)
    return {"complete": complete, "date_start": START, "date_end": END, "lang": "nld",
        "provider_total": total, "provider_totals": totals, "pages_seen": sorted(pages),
        "expected_pages": expected_pages, "ids": sorted(ids), "articles": articles,
        "unique_ids_seen": len(ids), "common_ids": len(ids & saved), "saved_ids": len(saved),
        "observed_added_ids": sorted(ids - saved), "missing_from_saved_ids": sorted(ids - saved) if complete else None,
        "saved_only_ids": sorted(saved - ids) if complete else None,
        "coverage_percent": (100.0 * len(ids & saved) / len(ids) if ids else 100.0) if complete else None,
        "unexpected_ids": sorted(ids - set(expected_ids)) if expected_ids is not None else [],
        "duplicate_ids": sorted(duplicate_ids), "diagnostics": sorted(set(diagnostics)),
        "receipt_ids": receipt_ids, "scored": 0, "model_calls": 0,
        "population": "metadata-retrievable provider article set; raw URI-list universe remains separate"}


def resolve(controls: Json, enumeration_result: Json, ids: list[str]) -> Json:
    _identifiers(ids)
    candidates = set(controls.get("provider_unresolvable_candidates", []))
    observed = set(enumeration_result.get("ids", []))
    complete = enumeration_result.get("complete") is True
    rows = [{"article_uri": uri, "classification": ("metadata_retrievable" if uri in observed else
        "provider_unresolvable" if complete and uri in candidates else "unresolved"),
        "raw_uri_scope": "unknown", "exclude_from_raw_uri_universe": False,
        "enumeration_presence": uri in observed if complete or uri in observed else None} for uri in ids]
    return {"method": RESOLUTION_METHOD, "rows": rows,
        "provider_unresolvable_ids": sorted(row["article_uri"] for row in rows if row["classification"] == "provider_unresolvable"),
        "unresolved_ids": sorted(row["article_uri"] for row in rows if row["classification"] == "unresolved"),
        "retrievable_set_complete": complete, "raw_uri_disagreement_resolved": False,
        "cause": "not established; invalid-URI responses do not prove deletion", "model_calls": 0}
