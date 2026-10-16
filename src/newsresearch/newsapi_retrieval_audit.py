"""Offline receipt and bundle audit; no semantic article assessments or network."""
from __future__ import annotations

from collections import Counter
import hashlib
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING
import uuid
import zipfile

from .common import Context, Json, ResearchError, canonical, digest, require_active, utc
from .newsapi_collection import BACKFILL_PERIODS, PERIODS, collection_request

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-retrieval-method-audit-v1"


def percent(numerator: int, denominator: int | None) -> float | None:
    return 100 * numerator / denominator if denominator else None


def inspect_partition(receipts: list[Json], start: str, end: str) -> tuple[Json, Json]:
    """Independent receipt checks; keep occurrences and distinct identities separate."""
    selected = [r for r in receipts if (r["parameters"].get("dateStart"), r["parameters"].get("dateEnd")) == (start, end)]
    shaped = [r for r in selected if r["http_status"] == 200
              and isinstance(r.get("response", {}).get("articles", {}).get("results"), list)]
    totals = [r["response"]["articles"].get("totalResults") for r in shaped]
    positive = sorted({n for n in totals if isinstance(n, int) and n > 0})
    maximum = max(positive, default=0)
    expected_pages = (maximum + 99) // 100
    anomalies = [r for r in shaped if maximum > 0 and not r["response"]["articles"]["results"]
                 and r["response"]["articles"].get("totalResults") == 0
                 and r["parameters"]["articlesPage"] <= expected_pages]
    accepted = [r for r in shaped if r not in anomalies]
    pages: dict[int, list[Json]] = {}
    for r in accepted:
        pages.setdefault(r["parameters"]["articlesPage"], []).append(r)
    # More than one valid attempt is reported, not counted twice toward coverage.
    chosen = [pages[p][-1] for p in sorted(pages)]
    last = chosen[-1]["response"]["articles"] if chosen else {}
    denominator = last.get("totalResults")
    reported_pages = last.get("pages")
    page_indices = set(pages)
    invariant_counts: Counter[str] = Counter()
    mismatch = []
    uri_counts: Counter[str] = Counter()
    uri_pages: dict[str, set[int]] = {}
    source_versions = set()
    identifiers = []
    page_details = []
    dates = []
    missing_uri = invalid_scope = missing_body = quarantine = 0
    for r in selected:
        actual = r["parameters"]
        expected = collection_request((start, end), actual["articlesPage"])
        differences = {k: {"actual": actual.get(k), "expected": expected.get(k)}
                       for k in actual.keys() | expected.keys() if actual.get(k) != expected.get(k)}
        if differences:
            mismatch.append({"receipt": r["id"], "differences": differences})
        invariant_counts[digest({k: v for k, v in actual.items() if k not in {"dateStart", "dateEnd", "articlesPage"}})] += 1
    for r in chosen:
        page = r["parameters"]["articlesPage"]
        rows = r["response"]["articles"]["results"]
        uris, page_dates = [], []
        for index, article in enumerate(rows):
            valid = isinstance(article, dict) and start <= str(article.get("date", "")) <= end and article.get("lang") == "nld"
            invalid_scope += not valid
            if not isinstance(article, dict):
                continue
            uri = article.get("uri")
            if isinstance(uri, str) and uri.strip():
                uri_counts[uri] += 1
                uri_pages.setdefault(uri, set()).add(page)
                uris.append(uri)
            else:
                missing_uri += 1
            body = article.get("body")
            body_present = isinstance(body, str) and bool(body.strip())
            missing_body += not body_present
            quarantine += article.get("quarantined") is True
            stamp = str(article.get("date", ""))
            page_dates.append(stamp)
            dates.append(stamp)
            source_versions.add((article.get("uri") or article.get("source_hash") or article.get("url"), digest(article)))
            identifiers.append({"receipt": r["id"], "index": index, "uri": uri, "record_hash": digest(article)})
        expected_size = min(100, max(0, denominator - 100 * (page-1))) if isinstance(denominator, int) else None
        page_details.append({"receipt": r["id"], "page": page, "rows": len(rows), "expected_rows": expected_size,
            "uri_set_hash": digest(sorted(set(uris))), "first_date": page_dates[0] if page_dates else None,
            "last_date": page_dates[-1] if page_dates else None, "provider_total": r["response"]["articles"].get("totalResults"),
            "provider_pages": r["response"]["articles"].get("pages")})
    rows = sum(p["rows"] for p in page_details)
    duplicates = {uri: n for uri, n in uri_counts.items() if n > 1}
    overlaps = {uri: sorted(ps) for uri, ps in uri_pages.items() if len(ps) > 1}
    sequence = sorted(page_details, key=lambda p: p["page"])
    zeros = len(anomalies)
    invalid_attempts = [r for r in selected if r not in accepted]
    recovery = [{"receipt": r["id"], "page": r["parameters"]["articlesPage"], "http_status": r["http_status"],
        "billed_tokens": r.get("billed_tokens"), "response_missing": r.get("raw_sha256") is None,
        "inconsistent_zero_total": r in anomalies,
        "matching_successful_retry": any(canonical(r["parameters"]) == canonical(ok["parameters"]) for ok in accepted)} for r in invalid_attempts]
    result = {"year": start[:4], "date_start": start, "date_end": end, "attempts": len(selected),
        "valid_receipts": len(accepted), "valid_pages": len(page_indices), "expected_pages": reported_pages,
        "missing_pages": sorted(set(range(1, reported_pages+1)) - page_indices) if isinstance(reported_pages, int) else None,
        "provider_total_final": denominator, "provider_positive_totals": positive,
        "zero_total_anomalies": zeros, "provider_total_drift": len(positive) > 1,
        "rows": rows, "distinct_provider_ids": len(uri_counts), "missing_provider_ids": missing_uri,
        "retrieved_percent_of_provider_total": percent(rows, denominator),
        "distinct_percent_of_provider_total": percent(len(uri_counts), denominator),
        "missing_body": missing_body, "body_retained_percent_of_retrieved": percent(rows-missing_body, rows),
        "quarantined": quarantine, "invalid_scope": invalid_scope,
        "duplicate_uri_occurrences": sum(n-1 for n in duplicates.values()), "cross_page_overlap_ids": len(overlaps),
        "repeated_valid_page_requests": sum(len(rs)-1 for rs in pages.values()),
        "page_size_mismatches": [p for p in page_details if p["rows"] != p["expected_rows"]],
        "date_order_reversals": sum(a > b for a, b in zip(dates, dates[1:])),
        "equal_date_page_boundaries": sum(a["last_date"] == b["first_date"] for a, b in zip(sequence, sequence[1:]) if a["last_date"]),
        "normalized_parameter_fingerprints": dict(invariant_counts), "parameter_mismatches": mismatch,
        "recovery": recovery, "raw_response_bytes_unavailable": sum(r.get("raw_response") is None for r in chosen),
        "reported_cost": sum(r["billed_tokens"] for r in selected if r.get("billed_tokens") is not None),
        "unknown_individual_costs": sum(r.get("billed_tokens") is None for r in selected),
        "first_receipt_time": min((r["completed_at"] for r in selected), default=None),
        "last_receipt_time": max((r["completed_at"] for r in selected), default=None),
        "receipt_ids": [r["id"] for r in selected], "page_details": page_details}
    return result, {"identifiers": identifiers, "uri_counts": dict(uri_counts), "overlap_ids": overlaps,
                    "versions": sorted(source_versions, key=str)}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "retrieval_profile"})
    profile = engine.ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"]
    if profile.get("method") != METHOD or data.get("sources") != profile.get("sources"):
        raise ResearchError("Register exact immutable source materializations and audit method first")
    sources = [{"id": identifier, **engine.ledger.get(identifier, "newsapi_collection_materialization")} for identifier in data["sources"]]
    covered = sorted(tuple(p) for source in sources for p in source.get("periods", PERIODS))
    if covered != sorted(PERIODS + BACKFILL_PERIODS):
        raise ResearchError("Audit binds both complete original and extension interval frames")
    receipt_ids = list(dict.fromkeys(identifier for source in sources for identifier in source["receipt_ids"]))
    receipts = [{"id": identifier, **engine.ledger.get(identifier, "newsapi_collection_receipt")} for identifier in receipt_ids]
    periods, manifests = [], {}
    year_ids: dict[str, set[str]] = {}
    all_ids: Counter[str] = Counter()
    uri_partitions: dict[str, set[str]] = {}
    for start, end in covered:
        row, private = inspect_partition(receipts, start, end)
        periods.append(row)
        manifests[start] = private
        year_ids.setdefault(start[:4], set()).update(private["uri_counts"])
        all_ids.update(private["uri_counts"])
        for uri in private["uri_counts"]:
            uri_partitions.setdefault(uri, set()).add(start)
    bundle_checks = []
    for source in sources:
        source_periods = source.get("periods", PERIODS)
        for bundle, (start, end) in zip(source["bundles"], source_periods, strict=True):
            raw = engine.ledger.artifacts.read_bytes(bundle["artifact"])
            observed, repeated, uri_set, absent, bad_hash = set(), 0, set(), 0, 0
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                with archive.open("artikelen.jsonl") as stream:
                    for line in stream:
                        item = json.loads(line)
                        article = item["article"]
                        body = article.get("body")
                        absent += not isinstance(body, str) or not body.strip()
                        hashed = digest(article)
                        bad_hash += hashed != item["source_hash"]
                        key = (article.get("uri") or article.get("source_hash") or article.get("url"), hashed)
                        repeated += key in observed
                        observed.add(key)
                        if article.get("uri"):
                            uri_set.add(article["uri"])
            expected = {tuple(v) for v in manifests[start]["versions"]}
            relative = (Path("topics/cybercrime-nl") / ("extensions/2020-2023" if start < "2023-10-15" else "")
                        / "articles" / f"articles-{start[:4]}.zip")
            copied = Path(data["data_repository"]) / relative
            repo_matches = copied.is_file() and hashlib.sha256(copied.read_bytes()).hexdigest() == bundle["artifact"]
            bundle_checks.append({"date_start": start, "date_end": end, "bundle_sha256": bundle["artifact"],
                "protected_artifact_hash_valid": hashlib.sha256(raw).hexdigest() == bundle["artifact"],
                "repository_copy_matches": repo_matches, "records": len(observed), "distinct_provider_ids": len(uri_set),
                "missing_body": absent, "duplicate_record_versions": repeated, "row_hash_errors": bad_hash,
                "receipt_versions_missing_from_bundle": len(expected-observed), "extra_bundle_versions": len(observed-expected)})
    years = []
    for year, ids in sorted(year_ids.items()):
        selected = [p for p in periods if p["year"] == year]
        denominator = sum(p["provider_total_final"] for p in selected)
        rows = sum(p["rows"] for p in selected)
        absent = sum(p["missing_body"] for p in selected)
        years.append({"year": year, "date_start": min(p["date_start"] for p in selected), "date_end": max(p["date_end"] for p in selected),
            "provider_total": denominator, "rows": rows, "distinct_provider_ids": len(ids),
            "retrieval_percent": percent(len(ids), denominator), "missing_body": absent,
            "retained_body_percent": percent(rows-absent, denominator),
            "valid_pages": sum(p["valid_pages"] for p in selected), "expected_pages": sum(p["expected_pages"] for p in selected),
            "missing_page_count": sum(len(p["missing_pages"]) for p in selected),
            "cross_page_overlap_ids": sum(p["cross_page_overlap_ids"] for p in selected),
            "parameter_mismatches": sum(len(p["parameter_mismatches"]) for p in selected)})
    private_ref = engine.ledger.artifacts.put(manifests)
    engine.ledger.append(session, "newsapi.retrieval_audit.identifiers.saved", {"artifact": private_ref})
    result = {"versions": context.versions, "sources": data["sources"], "source_versions": {s["id"]: s["versions"] for s in sources},
        "years": years, "periods": periods, "bundle_checks": bundle_checks, "identity_manifest": private_ref,
        "rows": sum(y["rows"] for y in years), "distinct_provider_ids": len(all_ids),
        "cross_partition_duplicate_ids": sum(len(ps) > 1 for ps in uri_partitions.values()),
        "duplicate_id_occurrences": sum(n-1 for n in all_ids.values()),
        "normalized_parameter_fingerprints": sorted({k for p in periods for k in p["normalized_parameter_fingerprints"]}),
        "network_calls": 0, "model_calls": 0, "generated_at": utc(),
        "coverage_denominator": "Final provider-reported matches for the exact eight-term query, language, type and date partitions; not all Dutch news or relevant Netherlands incidents",
        "unperformed": ["independent URI-universe census", "repeat or reverse-order live retrieval", "provider snapshot/tie stability verification", "semantic relevance or event grouping", "publisher-body fidelity review", "human known-item recall evaluation"]}
    identifier = engine.ledger.record(session, "newsapi_retrieval_audit", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
