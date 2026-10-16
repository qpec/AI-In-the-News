"""Archive-only one-page block comparison for the unsettled 2026 provider frame."""
from __future__ import annotations

import os
import csv
import io
from typing import TYPE_CHECKING
import uuid

from .common import Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_collection import number
from .newsapi_id_manifest import AUTH_ID, CAP, METHOD, accounting, dispatch, load_baseline, records, request
from .newsapi_id_manifest_proof import compare_frames, evidence_zip, export_proof, verify_proof_bytes
from .newsapi_id_manifest_quarter_proof import _metadata, compare_quarters

if TYPE_CHECKING:
    from .runtime import Research

BLOCK_METHOD = "nl-cyber-id-manifest-archive-block-v1"
WINDOWS = [("2026-01-01", "2026-04-30"), ("2026-05-01", "2026-08-31"), ("2026-09-01", "2026-10-15")]


def templates() -> list[Json]:
    return [{**request(start, end, 1, 5000), "uriWgtListSortByAsc": ascending}
        for start, end in WINDOWS for ascending in (True, False)]


def _bound_source(engine: Research, context: Context) -> Json:
    previous = records(engine, "newsapi_id_manifest_quarter_proof")
    if not previous:
        raise ResearchError("A retained quarter proof must precede archive block refinement")
    latest = previous[-1]
    if any(context.versions[k] != latest["versions"].get(k) for k in ("selection", "question", "profile")):
        raise ResearchError("Archive blocks must retain the original selection/question/profile versions")
    return latest


def source(engine: Research, session: str, context: Context, data: Json) -> Json:
    """Persist available prior-window diagnostics before registering paid refinement."""
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    previous = _bound_source(engine, context)
    diagnostics = []
    for window in previous["windows"]:
        row = {"date_start": window["date_start"], "date_end": window["date_end"], "directions": {}}
        for direction in ("ascending", "reverse"):
            item = window[direction]
            receipts = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in item["attempts"]]
            row["directions"][direction] = {"accepted_ids": len(item["ids"]), "provider_total": item["provider_total"],
                "complete": item["complete"], "attempts": [{"receipt": r["id"], "http_status": r.get("http_status"),
                    "archive": r.get("headers", {}).get("req-archive"), "billed_tokens": r.get("billed_tokens"),
                    "completed_at": r.get("completed_at"), "raw_response": r.get("raw_response")} for r in receipts]}
        diagnostics.append(row)
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "method": BLOCK_METHOD,
        "source_id": previous["id"], "source_versions": previous["versions"], "diagnostics": diagnostics,
        "prior_reported_tokens": previous["budget"]["reported_tokens"], "new_api_calls": 0,
        "no_paid_calls": 0, "model_calls": 0, "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_block_source", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def _reconstruct(engine: Research, previous: Json) -> tuple[Json, Json, Json, Json, Json, dict[str, Json]]:
    baseline, identities = load_baseline(engine, previous["baseline_audit"])
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    annual = {"id": previous["quarter_source"], **engine.ledger.get(previous["quarter_source"], "newsapi_id_manifest_proof")}
    asc_refs = list(dict.fromkeys(ref for p in first["periods"] for ref in p["manifest_receipts"]))
    asc = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in asc_refs]
    reverse = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in annual["reverse_receipt_ids"]]
    old, frames = compare_frames(baseline, identities, asc, reverse)
    settled = [y for y in previous["years"] if y["year"] == "2020"]
    windows = [w for w in previous["windows"] if w["year"] == "2020"]
    if (len(settled) != 1 or not settled[0]["complete"] or not settled[0]["ascending_reverse_equal"]
            or len(windows) != 4 or not all(w["complete"] and w["ascending_reverse_equal"] for w in windows)):
        raise ResearchError("The four settled 2020 quarter pairs are required for explicit reuse")
    sets = {direction: set().union(*(set(w[direction]["ids"]) for w in windows)) for direction in ("ascending", "reverse")}
    if any(len(sets[d]) != sum(len(w[d]["ids"]) for w in windows) for d in sets) or sets["ascending"] != sets["reverse"]:
        raise ResearchError("Settled 2020 quarters overlap or differ between orders")
    old["years"] = [{**y} if y["year"] != "2020" else {**settled[0]} for y in old["years"]]
    frames["2020-01-01"] = {**frames["2020-01-01"], **sets}
    return baseline, identities, first, annual, old, frames


def _compare(baseline: Json, identities: Json, previous: Json, old: Json,
             frames: dict[str, Json], receipts: list[Json]) -> tuple[Json, dict[str, Json]]:
    result, selected = compare_quarters(baseline, identities, old, frames, receipts, windows=WINDOWS)
    for row in result["years"]:
        if row["year"] == "2020":
            row["verification_method"] = "reused_matching_2020_quarters"
        elif row["year"] == "2026":
            row["verification_method"] = "archive_only_one_page_blocks_both_orders"
            row["cross_block_duplicate_occurrences"] = row["cross_quarter_duplicate_occurrences"]
            row["expected_pages"] = 6
    saved_2026 = set().union(*(f["saved"] for f in frames.values() if f["year"] == "2026"))
    populations: dict[str, set[str]] = {}
    for direction in ("ascending", "reverse"):
        populations[f"annual_{direction}"] = set().union(*(f[direction] for f in frames.values() if f["year"] == "2026"))
        populations[f"quarter_{direction}"] = set().union(*(set(w[direction]["ids"]) for w in previous["windows"] if w["year"] == "2026"))
        populations[f"block_{direction}"] = set().union(*(f[direction] for f in selected.values() if f["year"] == "2026"))
    candidates = set().union(*populations.values())-saved_2026
    result["observed_missing_candidates"] = [{"year": "2026", "article_uri": uri,
        "observed_in": [name for name, ids in populations.items() if uri in ids],
        "confirmed_in_settled_blocks": uri in populations["block_reverse"] if result["complete"] else None}
        for uri in sorted(candidates)]
    result["observed_missing_candidate_count"] = len(candidates)
    return result, selected


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("method") != METHOD or policy.get("block_method") != BLOCK_METHOD or policy.get("authorization_id") != AUTH_ID
            or policy.get("max_tokens") != CAP or policy.get("block_templates") != templates() or policy.get("block_reservation") != 50):
        raise ResearchError("Register the six exact archive-block requests and fifty-token reservations under the existing authorization")
    previous = _bound_source(engine, context)
    if policy.get("block_source") != previous["id"] or policy.get("baseline_audit") != previous["baseline_audit"]:
        raise ResearchError("Bind the latest quarter proof and unchanged original baseline")
    if policy.get("block_source_diagnostic"):
        diagnostic = engine.ledger.get(policy["block_source_diagnostic"], "newsapi_id_manifest_block_source")
        if diagnostic["source_id"] != previous["id"]:
            raise ResearchError("Block source diagnostic refers to another quarter proof")
    baseline, identities, first, annual, old, old_frames = _reconstruct(engine, previous)
    def state() -> tuple[Json, dict[str, Json]]:
        return _compare(baseline, identities, previous, old, old_frames, records(engine, "newsapi_id_receipt"))
    for prior in reversed(records(engine, "newsapi_id_manifest_block_proof")):
        if prior.get("complete") and prior.get("versions") == context.versions and prior.get("block_source") == previous["id"]:
            verified = verify_proof_bytes(engine.ledger.artifacts.read_bytes(prior["proof_artifact"]))
            path = export_proof(engine, session, prior["proof_artifact"], filename="id-manifest-block-proof.zip")
            engine.ledger.append(session, "newsapi.id_manifest.block_proof.reused", {"result": prior["id"], "versions": context.versions})
            return {**prior, "new_api_calls": 0, "reused": True, "proof_path": path, "proof_self_check": verified}
    result, frames = state()
    limit = data.get("requests", 6)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 6:
        raise ResearchError("Use one through six archive block requests per checkpoint")
    execute = not engine.config.offline and data.get("execute") is True and bool(os.environ.get("EVENTREGISTRY_API_KEY"))
    calls, stop = 0, "checkpoint"
    if not result["complete"]:
        if not execute:
            raise ResearchError("Explicit live archive-block execution and a credential are required")
        try:
            before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_archive_blocks")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
            before, stop = {}, "budget_or_unresolved_dispatch"
        if (before.get("outcome") == "received" and before.get("http_status") == 200
                and number(before.get("response", {}).get("usedTokens")) is not None):
            for _ in range(limit):
                result, frames = state()
                pending = []
                invalid = False
                for window in result["windows"]:
                    for direction in ("ascending", "reverse"):
                        item = window[direction]
                        if item["attempts"] and not item["complete"]:
                            invalid = True
                        elif not item["complete"]:
                            pending.append({**request(window["date_start"], window["date_end"], 1, 5000), "uriWgtListSortByAsc": direction == "ascending"})
                if not pending:
                    stop = "invalid_block_response" if invalid else stop
                    break
                try:
                    receipt = dispatch(engine, session, context, pending[0], "archive_block_confirmation", reserve_override=50)
                    calls += 1
                except ResearchError as error:
                    if not str(error).startswith(("ID-manifest authorization budget", "Account allowance", "Unresolved or excessive", "No duplicate valid-page")):
                        raise
                    stop = "budget_or_unresolved_dispatch"
                    break
                if receipt.get("outcome") == "unknown":
                    stop = "unknown_outcome"
                    break
        elif stop != "budget_or_unresolved_dispatch":
            stop = "account_usage_unavailable"
    result, frames = state()
    result.update(versions=context.versions, authorization_id=AUTH_ID, method=BLOCK_METHOD,
        block_source=previous["id"], block_source_diagnostic=policy.get("block_source_diagnostic"),
        quarter_source=previous["quarter_source"], confirmation_source=first["id"], baseline_audit=previous["baseline_audit"],
        prior_reported_tokens=previous["budget"]["reported_tokens"], prior_quarter_windows=previous["windows"],
        generated_at=utc(), model_calls=0, body_fetch_requested=False, reused=False,
        limitation="Same-provider exact ID verification for the fixed keywords/dates: five matching annual years and settled2020quarters reused;2026checked in three archive-only one-page blocks, both orders. Does not prove an external census, a fixed snapshot, original omission or article relevance. Prior observed missing candidates remain explicit when new verification is unsettled.")
    known_metadata = {r["article_uri"]: r for r in previous.get("differences", [])
        if (r.get("metadata") or {}).get("status") == "available"}
    metadata_policy = policy
    if known_metadata:
        prior_metadata = engine.ledger.get(policy["metadata_result"], "newsapi_id_manifest_details") if policy.get("metadata_result") else {}
        cached = {r["article_uri"]: r for r in prior_metadata.get("differences", [])}
        cached.update(known_metadata)
        projection = {"versions": context.versions, "authorization_id": AUTH_ID, "baseline_audit": previous["baseline_audit"],
            "differences": list(cached.values()), "cache_reuse": "Exact article URI metadata from explicitly bound prior results; no provider dispatch",
            "source_quarter_result": previous["id"], "source_metadata_result": policy.get("metadata_result"),
            "new_api_calls": 0, "model_calls": 0}
        cache_id = engine.ledger.record(session, "newsapi_id_manifest_details", str(uuid.uuid4()), projection)
        metadata_policy = {**policy, "metadata_result": cache_id}
    calls += _metadata(engine, session, context, result, identities, metadata_policy, execute)
    for row in result["differences"]:
        if row["article_uri"] in known_metadata:
            row.update(metadata=known_metadata[row["article_uri"]]["metadata"], metadata_source_result=previous["id"])
    if not result["complete"]:
        current = {r["article_uri"] for r in result["differences"]}
        for candidate in result["observed_missing_candidates"]:
            if candidate["article_uri"] not in current:
                cached = known_metadata.get(candidate["article_uri"], {})
                result["differences"].append({**candidate, "direction": "prior_observed_missing_candidate",
                    "metadata": cached.get("metadata"), "metadata_source_result": previous["id"] if cached else None})
    result["unavailable_metadata"] = sum((r.get("metadata") or {}).get("status") != "available" for r in result["differences"])
    result["metadata_pending_ids"] = sorted({r["article_uri"] for r in result["differences"] if r.get("metadata") is None})
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=["year", "direction", "article_uri", "metadata_status", "title", "url", "date"], lineterminator="\n")
    writer.writeheader()
    for row in result["differences"]:
        item = row.get("metadata") or {}
        writer.writerow({"year": row["year"], "direction": row["direction"], "article_uri": row["article_uri"],
            "metadata_status": item.get("status", "pending"), **{k: item.get(k) for k in ("title", "url", "date")}})
    result["differences_csv"] = buffer.getvalue()
    if execute and calls:
        try:
            dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_archive_blocks")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
    receipts = records(engine, "newsapi_id_receipt")
    relevant = [r for r in receipts if any(canonical(r["parameters"]) == canonical(t) for t in templates())]
    metadata_receipts = [r for r in receipts if r.get("purpose") == "quarter_difference_metadata"
        and r["id"] not in previous.get("receipt_ids", [])]
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received"
        and r.get("http_status") == 200 and number(r.get("response", {}).get("usedTokens")) is not None]
    initial = number(usages[0]["response"]["usedTokens"]) if usages else None
    latest = number(usages[-1]["response"]["usedTokens"]) if usages else None
    result.update(budget=accounting(records(engine, "newsapi_id_intent"), receipts), baseline_used=initial, latest_used=latest,
        observed_account_delta=latest-initial if initial is not None and latest is not None else None,
        receipt_ids=[r["id"] for r in receipts], new_api_calls=calls,
        block_reported_tokens=sum(r["billed_tokens"] for r in relevant if r.get("billed_tokens") is not None),
        additional_metadata_tokens=sum(r["billed_tokens"] for r in metadata_receipts if r.get("billed_tokens") is not None),
        stop_reason="archive_block_confirmation_complete" if result["complete"] else "block_order_disagreement" if result["ascending_reverse_equal"] is False
            else "block_cross_window_overlap" if any(any(y.get("cross_block_duplicate_occurrences", {}).values()) for y in result["years"]) else stop)
    reference = evidence_zip(engine, session, context, baseline, first, result, frames,
        extra_json={"block-verification.json": {"method": BLOCK_METHOD, "source_proof_id": previous["id"], "windows": result["windows"]},
            "quarter-verification.json": {"method": "historical_quarter_evidence", "source_proof_id": previous["id"], "windows": previous["windows"]},
            "source-quarter-proof.json": previous, "source-reverse-proof.json": annual}, method=BLOCK_METHOD)
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)),
        evidence_zip=reference, proof_path=export_proof(engine, session, reference, filename="id-manifest-block-proof.zip"))
    identifier = engine.ledger.record(session, "newsapi_id_manifest_block_proof", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
