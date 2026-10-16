"""Single-page quarter checks for years with inconsistent annual manifests."""
from __future__ import annotations

import csv
import io
import os
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, digest, require_active, utc
from .newsapi_collection import number
from .newsapi_id_manifest import AUTH_ID, CAP, METHOD, accounting, dispatch, load_baseline, parse_manifest, records, request
from .newsapi_id_manifest_details import extract_info, info_request, metadata
from .newsapi_id_manifest_proof import RECENT_WINDOW_METHOD, archive_or_recent, compare_frames, evidence_zip, export_proof, verify_proof_bytes

if TYPE_CHECKING:
    from .runtime import Research

QUARTER_METHOD = "nl-cyber-id-manifest-quarter-proof-v1"
WINDOWS = [(f"{year}-{start}", f"{year}-{end}") for year in ("2020", "2026") for start, end in
    [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"), ("10-01", "12-31" if year == "2020" else "10-15")]]


def templates() -> list[Json]:
    return [{**request(start, end, 1, 5000), "uriWgtListSortByAsc": ascending}
        for start, end in WINDOWS for ascending in (True, False)]


def inspect_windows(receipts: list[Json], allow_recent: bool = False) -> list[Json]:
    rows = []
    for start, end in WINDOWS:
        row: Json = {"date_start": start, "date_end": end, "year": start[:4]}
        for ascending, direction in ((True, "ascending"), (False, "reverse")):
            expected = {**request(start, end, 1, 5000), "uriWgtListSortByAsc": ascending}
            candidates = [r for r in receipts if canonical(r["parameters"]) == canonical(expected)]
            valid = []
            for r in candidates:
                try:
                    ids, total = parse_manifest(r.get("response") or {})
                except ResearchError:
                    continue
                if (r.get("outcome") == "received" and r.get("http_status") == 200
                        and archive_or_recent(r, allow_recent)
                        and 0 <= total <= 5000 and len(ids) == total and len(ids) == len(set(ids))):
                    valid.append((r, ids, total))
            # Do not choose one successful repeated response and silently discard drift.
            complete = len(valid) == 1 and len(candidates) == 1
            row[direction] = {"complete": complete, "ids": sorted(valid[0][1]) if complete else [],
                "provider_total": valid[0][2] if complete else None,
                "receipt": valid[0][0]["id"] if complete else None, "attempts": [r["id"] for r in candidates],
                "validation_method": RECENT_WINDOW_METHOD if complete and valid[0][0].get("headers", {}).get("req-archive") == "0" else "archive_required",
                "status": "complete" if complete else "pending" if not candidates else "invalid_or_repeated_response"}
        row["enumerated"] = row["ascending"]["complete"] and row["reverse"]["complete"]
        row["ascending_reverse_equal"] = row["ascending"]["ids"] == row["reverse"]["ids"] if row["enumerated"] else None
        row["complete"] = row["enumerated"] and row["ascending_reverse_equal"]
        rows.append(row)
    return rows


def compare_quarters(baseline: Json, identities: Json, old: Json, old_frames: dict[str, Json],
                     receipts: list[Json], allow_recent: bool = False) -> tuple[Json, dict[str, Json]]:
    windows = inspect_windows(receipts, allow_recent)
    frames = {start: {**frame} for start, frame in old_frames.items()}
    years = []
    for previous in old["years"]:
        year = previous["year"]
        selected = [w for w in windows if w["year"] == year]
        if not selected:
            if not previous["complete"] or not previous["ascending_reverse_equal"]:
                raise ResearchError("Only the five previously matching years may reuse their annual ID sets")
            years.append({**previous, "verification_method": "reused_matching_annual_orders", "quarter_source": False})
            continue
        grouped = [f for f in old_frames.values() if f["year"] == year]
        saved_ids = set().union(*(f["saved"] for f in grouped))
        asc = set().union(*(set(w["ascending"]["ids"]) for w in selected))
        reverse = set().union(*(set(w["reverse"]["ids"]) for w in selected))
        overlaps = {direction: sum(len(w[direction]["ids"]) for w in selected)-len(asc if direction == "ascending" else reverse)
            for direction in ("ascending", "reverse")}
        enumerated = all(w["enumerated"] for w in selected)
        equal = all(w["ascending_reverse_equal"] for w in selected) and asc == reverse if enumerated else None
        complete = enumerated and not any(overlaps.values()) and equal is True
        old_asc = set().union(*(f["ascending"] for f in grouped))
        old_reverse = set().union(*(f["reverse"] for f in grouped))
        row = {"year": year, "saved_ids": len(saved_ids), "ascending_ids": len(asc), "reverse_ids": len(reverse),
            "manifest_ids_seen": len(reverse), "complete": complete, "all_quarters_enumerated": enumerated,
            "ascending_reverse_equal": equal, "saved_equals_reverse": saved_ids == reverse if complete else None,
            "ascending_provider_total": sum(w["ascending"]["provider_total"] for w in selected) if complete else None,
            "reverse_provider_total": sum(w["reverse"]["provider_total"] for w in selected) if complete else None,
            "manifest_only_ids": sorted(reverse-saved_ids), "saved_only_ids": sorted(saved_ids-reverse) if complete else None,
            "common_ids": len(saved_ids & reverse),
            "saved_coverage_of_manifest_percent": 100*len(saved_ids & reverse)/len(reverse) if complete and equal and reverse else None,
            "ascending_only_ids": sorted(asc-reverse) if complete else None, "reverse_only_ids": sorted(reverse-asc),
            "cross_quarter_duplicate_occurrences": overlaps, "verification_method": "single_page_quarters_both_orders",
            "quarter_source": True, "old_annual_ascending_ids": len(old_asc), "old_annual_reverse_ids": len(old_reverse),
            "old_ascending_only_vs_quarters": sorted(old_asc-asc) if complete else None,
            "quarters_only_vs_old_ascending": sorted(asc-old_asc),
            "old_reverse_only_vs_quarters": sorted(old_reverse-reverse) if complete else None,
            "quarters_only_vs_old_reverse": sorted(reverse-old_reverse),
            "pages": sum(w[d]["complete"] for w in selected for d in ("ascending", "reverse")), "expected_pages": 8}
        row.update(reverse_ids_seen=row["reverse_ids"], reverse_only_vs_saved_ids=row["manifest_only_ids"],
            saved_only_vs_reverse_ids=row["saved_only_ids"], saved_coverage_of_reverse_percent=row["saved_coverage_of_manifest_percent"])
        years.append(row)
        starts = [p["date_start"] for p in baseline["periods"] if p["year"] == year]
        if len(starts) != 1:
            raise ResearchError("Quarter refinement requires exactly one original interval for each targeted year")
        frames[starts[0]] = {"year": year, "saved": saved_ids, "ascending": asc, "reverse": reverse}
    complete = all(y["complete"] for y in years)
    return {"years": years, "windows": windows, "complete": complete,
        "all_windows_enumerated": all(w["enumerated"] for w in windows),
        "ascending_reverse_equal": False if any(y["ascending_reverse_equal"] is False for y in years) else True if complete else None,
        "saved_equals_reverse": all(y["saved_equals_reverse"] for y in years) if complete else None}, frames


def _metadata(engine: Research, session: str, context: Context, result: Json, identities: Json,
              policy: Json, execute: bool) -> int:
    previous_id = policy.get("metadata_result")
    previous = engine.ledger.get(previous_id, "newsapi_id_manifest_details") if previous_id else {}
    if previous and (previous.get("baseline_audit") != result["baseline_audit"] or previous.get("authorization_id") != AUTH_ID):
        raise ResearchError("Metadata reuse must bind the same audited baseline and authorization")
    cached = {r["article_uri"]: r for r in previous.get("differences", []) if (r.get("metadata") or {}).get("status") == "available"}
    differences = []
    for year in result["years"]:
        for direction in ("manifest_only_ids", "saved_only_ids"):
            for uri in year[direction] or []:
                row = {"year": year["year"], "direction": direction, "article_uri": uri, "metadata": None}
                if uri in cached:
                    row.update(metadata=cached[uri]["metadata"], metadata_source_result=previous_id)
                    if cached[uri].get("original_locator"):
                        row["original_locator"] = cached[uri]["original_locator"]
                elif direction == "saved_only_ids":
                    locations = [item for frame in identities.values() for item in frame["identifiers"] if item["uri"] == uri]
                    if len(locations) != 1:
                        raise ResearchError("Saved-only quarter difference has an ambiguous original locator")
                    locator = locations[0]
                    original = engine.ledger.get(locator["receipt"], "newsapi_collection_receipt")["response"]["articles"]["results"][locator["index"]]
                    if original.get("uri") != uri or digest(original) != locator["record_hash"]:
                        raise ResearchError("Saved-only locator does not match its audited original record hash")
                    row.update(metadata={"status": "available", **metadata(original)}, original_locator=locator)
                differences.append(row)
    result.update(differences=differences, metadata_result=previous_id, metadata_receipts=[])
    wanted = sorted({r["article_uri"] for r in differences if r["direction"] == "manifest_only_ids" and r["metadata"] is None})
    result["metadata_status"] = "complete" if not wanted else "pending"
    result["metadata_capped_ids"] = wanted[10:]
    calls = 0
    if wanted and result["complete"] and result["ascending_reverse_equal"] and policy.get("allow_metadata") is True:
        if policy.get("metadata_max_ids", 10) != 10:
            raise ResearchError("Quarter metadata authorization is capped at ten exact IDs")
        lookup_ids = wanted[:10]
        if lookup_ids:
            parameters = info_request(lookup_ids)
            prior = [r for r in records(engine, "newsapi_id_receipt") if canonical(r["parameters"]) == canonical(parameters)]
            receipt = next((r for r in prior if r.get("versions") == context.versions), None)
            if not prior and execute:
                try:
                    receipt = dispatch(engine, session, context, parameters, "quarter_difference_metadata")
                    calls += 1
                except ResearchError as error:
                    if not str(error).startswith(("ID-manifest authorization budget", "Account allowance", "Unresolved or excessive")):
                        raise
                    result["metadata_status"] = "budget_or_unresolved_charge"
            if receipt:
                result["metadata_receipts"] = [receipt["id"]]
                returned = extract_info(receipt.get("response") or {}, lookup_ids) if receipt.get("http_status") == 200 else {}
                for row in differences:
                    if row["article_uri"] in lookup_ids:
                        row["metadata"] = returned.get(row["article_uri"], {"status": "unavailable", "reason": "metadata_request_failed"})
                result["metadata_status"] = "complete" if all((r.get("metadata") or {}).get("status") == "available" for r in differences) else "partially_unavailable_or_capped"
            elif prior:
                result["metadata_status"] = "prior_dispatch_not_repeated"
    result["unavailable_metadata"] = sum(r["metadata"] is None or r["metadata"].get("status") != "available" for r in differences)
    result["metadata_pending_ids"] = sorted({r["article_uri"] for r in differences if r["metadata"] is None})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "metadata_status", "title", "url", "date"], lineterminator="\n")
    writer.writeheader()
    for row in differences:
        item = row["metadata"] or {}
        writer.writerow({"year": row["year"], "direction": row["direction"], "article_uri": row["article_uri"],
            "metadata_status": item.get("status", "pending"), **{k: item.get(k) for k in ("title", "url", "date")}})
    result["differences_csv"] = buffer.getvalue()
    return calls


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("method") != METHOD or policy.get("quarter_method") != QUARTER_METHOD or policy.get("authorization_id") != AUTH_ID
            or policy.get("max_tokens") != CAP or policy.get("quarter_templates") != templates()):
        raise ResearchError("Register exact targeted-quarter templates under the original 583-token authorization")
    proofs = records(engine, "newsapi_id_manifest_proof")
    if not proofs or policy.get("quarter_source") != proofs[-1]["id"] or not proofs[-1].get("complete"):
        raise ResearchError("Bind the latest complete original annual reverse proof")
    previous = proofs[-1]
    if (policy.get("baseline_audit") != previous["baseline_audit"] or any(context.versions[k] != previous["versions"][k]
            for k in ("selection", "question", "profile"))):
        raise ResearchError("Quarter refinement must retain the baseline and original selection/question/profile versions")
    baseline, identities = load_baseline(engine, previous["baseline_audit"])
    targeted = sorted((p["year"], p["date_start"], p["date_end"]) for p in baseline["periods"] if p["year"] in ("2020", "2026"))
    if targeted != [("2020", "2020-01-01", "2020-12-31"), ("2026", "2026-01-01", "2026-10-15")]:
        raise ResearchError("Fixed quarter windows must exactly partition the original 2020 and2026 scopes")
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    asc_refs = list(dict.fromkeys(ref for p in first["periods"] for ref in p["manifest_receipts"]))
    asc = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in asc_refs]
    reverse = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in previous["reverse_receipt_ids"]]
    old, old_frames = compare_frames(baseline, identities, asc, reverse)
    if not old["complete"]:
        raise ResearchError("Original annual proof cannot be independently reconstructed")
    for prior in reversed(records(engine, "newsapi_id_manifest_quarter_proof")):
        if prior.get("complete") and prior.get("versions") == context.versions and prior.get("quarter_source") == previous["id"]:
            verified = verify_proof_bytes(engine.ledger.artifacts.read_bytes(prior["proof_artifact"]))
            path = export_proof(engine, session, prior["proof_artifact"], filename="id-manifest-quarter-proof.zip")
            engine.ledger.append(session, "newsapi.id_manifest.quarter_proof.reused", {"result": prior["id"], "versions": context.versions,
                "reason": "Exact-version completed quarter proof reused without provider calls"})
            return {**prior, "new_api_calls": 0, "reused": True, "proof_path": path, "proof_self_check": verified}
    def state() -> tuple[Json, dict[str, Json]]:
        return compare_quarters(baseline, identities, old, old_frames, records(engine, "newsapi_id_receipt"),
            allow_recent=policy.get("recent_window_validation") == RECENT_WINDOW_METHOD)
    result, frames = state()
    limit = data.get("requests", 16)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 16:
        raise ResearchError("Use one through sixteen quarter requests per checkpoint")
    execute = not engine.config.offline and data.get("execute") is True and bool(os.environ.get("EVENTREGISTRY_API_KEY"))
    calls, stop = 0, "checkpoint"
    if not result["complete"]:
        if not execute:
            raise ResearchError("Explicit live quarter confirmation and a credential are required")
        try:
            before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_quarter_confirmation")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
            before, stop = {}, "budget_or_unresolved_dispatch"
        if before.get("outcome") != "received" or before.get("http_status") != 200 or number(before.get("response", {}).get("usedTokens")) is None:
            if stop != "budget_or_unresolved_dispatch":
                stop = "account_usage_unavailable"
        else:
            for _ in range(limit):
                result, frames = state()
                missing = []
                invalid = False
                for window in result["windows"]:
                    for direction in ("ascending", "reverse"):
                        info = window[direction]
                        if info["attempts"] and not info["complete"]:
                            invalid = True
                            continue
                        if not info["complete"]:
                            missing.append({**request(window["date_start"], window["date_end"], 1, 5000), "uriWgtListSortByAsc": direction == "ascending"})
                if not missing:
                    if invalid:
                        stop = "invalid_quarter_response"
                    break
                try:
                    receipt = dispatch(engine, session, context, missing[0], "quarter_confirmation")
                    calls += 1
                except ResearchError as error:
                    if not str(error).startswith(("ID-manifest authorization budget", "Account allowance", "Unresolved or excessive", "No duplicate valid-page")):
                        raise
                    stop = "budget_or_unresolved_dispatch"
                    break
                if receipt.get("outcome") == "unknown":
                    stop = "unknown_outcome"
                    break
    result, frames = state()
    result.update(versions=context.versions, authorization_id=AUTH_ID, method=QUARTER_METHOD,
        quarter_source=previous["id"], confirmation_source=first["id"], baseline_audit=previous["baseline_audit"],
        prior_reported_tokens=previous["budget"]["reported_tokens"],
        prior_annual_comparison=old, receipt_ids=[r["id"] for r in records(engine, "newsapi_id_receipt")],
        generated_at=utc(), model_calls=0, body_fetch_requested=False, reused=False,
        limitation="Exact observed same-provider ID sets, with five matching annual frames reused and two years checked by single-page quarters in both orders. Does not establish an external news census, a fixed index snapshot, historical omission, or article relevance. Disagreement stays explicit.")
    calls += _metadata(engine, session, context, result, identities, policy, execute)
    if execute and calls:
        try:
            dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_quarter_confirmation")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
    receipts = records(engine, "newsapi_id_receipt")
    quarter_receipts = [r for r in receipts if any(canonical(r["parameters"]) == canonical(t) for t in templates())]
    metadata_receipts = [r for r in receipts if r.get("purpose") == "quarter_difference_metadata"]
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received"
        and r.get("http_status") == 200 and number(r.get("response", {}).get("usedTokens")) is not None]
    initial = number(usages[0]["response"]["usedTokens"]) if usages else None
    latest = number(usages[-1]["response"]["usedTokens"]) if usages else None
    result.update(budget=accounting(records(engine, "newsapi_id_intent"), receipts), baseline_used=initial, latest_used=latest,
        observed_account_delta=latest-initial if initial is not None and latest is not None else None,
        receipt_ids=[r["id"] for r in receipts], new_api_calls=calls,
        quarter_reported_tokens=sum(r["billed_tokens"] for r in quarter_receipts if r.get("billed_tokens") is not None),
        additional_metadata_tokens=sum(r["billed_tokens"] for r in metadata_receipts if r.get("billed_tokens") is not None),
        metadata_billed_tokens=sum(r["billed_tokens"] for r in metadata_receipts if r.get("billed_tokens") is not None),
        stop_reason="quarter_confirmation_complete" if result["complete"] else "quarter_order_disagreement" if result["ascending_reverse_equal"] is False
            else "quarter_cross_window_overlap" if any(any(y.get("cross_quarter_duplicate_occurrences", {}).values()) for y in result["years"]) else stop)
    extra = {"quarter-verification.json": {"method": QUARTER_METHOD, "source_proof_id": previous["id"], "windows": result["windows"]},
        "source-reverse-proof.json": previous}
    older_quarter = records(engine, "newsapi_id_manifest_quarter_proof")
    if policy.get("recent_window_validation") == RECENT_WINDOW_METHOD and older_quarter:
        extra["prior-quarter-proof.json"] = older_quarter[-1]
        export_proof(engine, session, older_quarter[-1]["proof_artifact"], filename="id-manifest-quarter-proof-initial.zip")
    reference = evidence_zip(engine, session, context, baseline, first, result, frames, extra_json=extra, method=QUARTER_METHOD)
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)),
        evidence_zip=reference, proof_path=export_proof(engine, session, reference, filename="id-manifest-quarter-proof.zip"))
    identifier = engine.ledger.record(session, "newsapi_id_manifest_quarter_proof", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
