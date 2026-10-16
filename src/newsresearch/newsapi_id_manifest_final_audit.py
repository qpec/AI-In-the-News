"""Metadata-only scope diagnosis of retained ID differences; no keyword search."""
from __future__ import annotations

from datetime import date
import io
import json
import os
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_collection import number
from .newsapi_id_manifest import AUTH_ID, CAP, METHOD, accounting, dispatch, load_baseline, records
from .newsapi_id_manifest_details import extract_info, info_request
from .newsapi_id_manifest_proof import evidence_zip, export_proof, verify_proof_bytes

if TYPE_CHECKING:
    from .runtime import Research

FINAL_METHOD = "nl-cyber-id-manifest-final-audit-v1"
SCOPE = {"date_start": "2020-01-01", "date_end": "2026-10-15", "lang": "nld"}


def bound_source(engine: Research, context: Context) -> Json:
    values = records(engine, "newsapi_id_manifest_block_proof")
    if not values:
        raise ResearchError("A retained archive block proof is required")
    previous = values[-1]
    if any(context.versions[k] != previous["versions"].get(k) for k in ("selection", "question", "profile")):
        raise ResearchError("Final diagnosis must preserve selection/question/profile versions")
    return previous


def diagnostics(previous: Json) -> Json:
    rows = []
    for window in previous["windows"]:
        a, b = set(window["ascending"]["ids"]), set(window["reverse"]["ids"])
        rows.append({"date_start": window["date_start"], "date_end": window["date_end"],
            "ascending": dict(window["ascending"]), "reverse": dict(window["reverse"]),
            "ascending_only_ids": sorted(a-b), "reverse_only_ids": sorted(b-a), "pair_equal": a == b})
    return {"windows": rows, "years": previous["years"], "prior_quarter_windows": previous.get("prior_quarter_windows"),
        "observed_missing_candidates": previous["observed_missing_candidates"]}


def source(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    previous = bound_source(engine, context)
    ids = sorted({r["article_uri"] for r in previous["observed_missing_candidates"]})
    detail = diagnostics(previous)
    for window in detail["windows"]:
        for direction in ("ascending", "reverse"):
            window[direction]["receipts"] = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")}
                for ref in window[direction]["attempts"]]
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "method": FINAL_METHOD,
        "source_id": previous["id"], "source_versions": previous["versions"], "metadata_ids": ids, "candidate_ids": ids,
        "prior_reported_tokens": previous["budget"]["reported_tokens"], "diagnostics": detail, "new_api_calls": 0,
        "model_calls": 0, "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_final_source", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def decide(ids: list[str], metadata: dict[str, Json]) -> list[Json]:
    decisions = []
    for uri in ids:
        item = metadata.get(uri) or {"status": "unavailable", "reason": "metadata_not_obtained"}
        stamp, language = item.get("date"), item.get("lang")
        available = item.get("status") == "available"
        try:
            parsed = date.fromisoformat(stamp) if available and isinstance(stamp, str) else None
        except ValueError:
            parsed = None
        in_date = SCOPE["date_start"] <= parsed.isoformat() <= SCOPE["date_end"] if parsed else None
        in_language = language == SCOPE["lang"] if available and isinstance(language, str) and language.strip() else None
        excluded = in_date is False or in_language is False
        decision = "excluded" if excluded else "eligible" if in_date is True and in_language is True else "unknown"
        reason = "reported_date_outside_scope" if in_date is False else "reported_language_outside_scope" if in_language is False else "reported_metadata_within_scope" if decision == "eligible" else "metadata_missing_or_invalid"
        decisions.append({"article_uri": uri, "metadata": item, "metadata_date": stamp, "lang": language,
            "decision": decision, "scope_decision": decision, "reason": reason, "in_date_scope": in_date,
            "in_language_scope": in_language, "excluded": excluded})
    return decisions


def apply_scope(previous: Json, frames: dict[str, Json], decisions: list[Json]) -> tuple[Json, dict[str, Json], Json]:
    excluded = {r["article_uri"] for r in decisions if r["excluded"]}
    selected = {start: {**f} for start, f in frames.items()}
    windows = []
    for raw in previous["windows"]:
        a, b = set(raw["ascending"]["ids"])-excluded, set(raw["reverse"]["ids"])-excluded
        complete = raw["ascending"]["complete"] and raw["reverse"]["complete"]
        windows.append({**raw, "raw_complete": complete, "eligible_ascending_ids": sorted(a), "eligible_reverse_ids": sorted(b),
            "eligible_ascending_only_ids": sorted(a-b), "eligible_reverse_only_ids": sorted(b-a), "eligible_pair_equal": a == b if complete else None})
    sets = {d: set().union(*(set(w[f"eligible_{d}_ids"]) for w in windows)) for d in ("ascending", "reverse")}
    overlaps = {d: sum(len(w[f"eligible_{d}_ids"]) for w in windows)-len(sets[d]) for d in sets}
    raw_complete = all(w["raw_complete"] for w in windows)
    agreement = all(w["eligible_pair_equal"] for w in windows) and sets["ascending"] == sets["reverse"] if raw_complete else None
    settled = raw_complete and agreement is True and not any(overlaps.values()) and all(r["decision"] != "unknown" for r in decisions)
    years = []
    for old in previous["years"]:
        row = {**old, "raw_ascending_ids": old.get("ascending_ids"), "raw_reverse_ids": old["reverse_ids"]}
        if old["year"] == "2026":
            saved = set().union(*(f["saved"] for f in frames.values() if f["year"] == "2026"))
            row.update(ascending_ids=len(sets["ascending"]), reverse_ids=len(sets["reverse"]), reverse_ids_seen=len(sets["reverse"]),
                manifest_ids_seen=len(sets["reverse"]), complete=settled, ascending_reverse_equal=agreement,
                saved_equals_reverse=saved == sets["reverse"] if settled else None,
                manifest_only_ids=sorted(sets["reverse"]-saved), reverse_only_vs_saved_ids=sorted(sets["reverse"]-saved),
                saved_only_ids=sorted(saved-sets["reverse"]) if settled else None,
                saved_only_vs_reverse_ids=sorted(saved-sets["reverse"]) if settled else None,
                common_ids=len(saved & sets["reverse"]), scope_excluded_ids=sorted(excluded),
                eligible_coverage_percent=100*len(saved & sets["reverse"])/len(sets["reverse"]) if settled and sets["reverse"] else None,
                cross_block_duplicate_occurrences=overlaps, raw_both_orders_enumerated=raw_complete,
                verification_method="archive_blocks_with_reported_metadata_scope_exclusions")
            row.update(saved_coverage_of_reverse_percent=row["eligible_coverage_percent"], saved_coverage_of_manifest_percent=row["eligible_coverage_percent"])
            for start, frame in selected.items():
                if frame["year"] == "2026":
                    selected[start] = {**frame, **sets}
        else:
            if not old["complete"] or not old["ascending_reverse_equal"]:
                raise ResearchError("The six non-target years must already have matching retained evidence")
            row.update(eligible_coverage_percent=old.get("saved_coverage_of_reverse_percent"), scope_excluded_ids=[])
        years.append(row)
    result = {"years": years, "windows": windows, "complete": all(y["complete"] for y in years),
        "ascending_reverse_equal": agreement, "remaining_unsettled_years": [y["year"] for y in years if not y["complete"]]}
    document = {"scope": SCOPE, "scope_decisions": decisions, "excluded_ids": sorted(excluded),
        "raw_block_windows": previous["windows"], "filtered_blocks": windows}
    return result, selected, document


def verify_scope_package(archive: Any, comparison: Json) -> Json:
    document = json.loads(archive.read("final-scope-verification.json"))
    policy = json.loads(archive.read("versions/policy.json"))["content"]
    block = json.loads(archive.read("source-block-proof.json"))
    ids = policy["final_metadata_ids"]
    if (document["scope"] != SCOPE or policy.get("allow_metadata_scope_filter") is not True
            or ids != sorted({r["article_uri"] for r in block["observed_missing_candidates"]})):
        raise AuditError("Final scope proof lacks the exact registered candidate IDs and metadata scope policy")
    metadata: dict[str, Json] = {}
    for identifier in document["metadata_receipts"]:
        receipt = json.loads(archive.read(f"receipts/{identifier}.json"))
        parameters = receipt["parameters"]
        if canonical(parameters) != canonical(info_request(parameters["articleUri"])):
            raise AuditError("Final scope evidence is not an exact-ID metadata-only request")
        if receipt.get("outcome") == "received" and receipt.get("http_status") == 200:
            response = json.loads(archive.read(f"responses/{identifier}.json"))
            metadata.update(extract_info(response, sorted(set(parameters["articleUri"]) & set(ids))))
    expected = decide(ids, metadata)
    if canonical(expected) != canonical(document["scope_decisions"]) or sorted(r["article_uri"] for r in expected if r["excluded"]) != document["excluded_ids"]:
        raise AuditError("Final metadata exclusions do not reproduce exact-ID raw evidence")
    raw_windows = json.loads(archive.read("block-verification.json"))["windows"]
    if canonical(block["windows"]) != canonical(document["raw_block_windows"]) or canonical(raw_windows) != canonical(block["windows"]):
        raise AuditError("Final filtering changed the original retained block windows")
    frames = {"2026-01-01": {"year": "2026", **{d: set(archive.read(f"years/2026/{d}-ids.txt").decode().splitlines()) for d in ("saved", "ascending", "reverse")}}}
    replay, selected, replay_doc = apply_scope(block, frames, expected)
    for direction in ("ascending", "reverse"):
        observed = set(archive.read(f"years/2026/{direction}-ids.txt").decode().splitlines())
        if selected["2026-01-01"][direction] != observed:
            raise AuditError("Final year IDs do not equal raw block IDs minus explicit scope exclusions")
    expected_year = next(y for y in replay["years"] if y["year"] == "2026")
    actual_year = next(y for y in comparison["years"] if y["year"] == "2026")
    if (expected_year["complete"] != actual_year["complete"] or expected_year["ascending_reverse_equal"] != actual_year["ascending_reverse_equal"]
            or canonical(replay_doc["filtered_blocks"]) != canonical(document["filtered_blocks"])):
        raise AuditError("Final completeness claim does not reproduce filtered block agreement and metadata coverage")
    return {"metadata_scope_checks": len(expected), "scope_excluded_ids": len(document["excluded_ids"]),
        "unknown_metadata": sum(r["decision"] == "unknown" for r in expected)}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    previous = bound_source(engine, context)
    ids = sorted({r["article_uri"] for r in previous["observed_missing_candidates"]})
    if (policy.get("method") != METHOD or policy.get("final_method") != FINAL_METHOD or policy.get("authorization_id") != AUTH_ID
            or policy.get("max_tokens") != CAP or policy.get("final_source") != previous["id"] or policy.get("final_metadata_ids") != ids
            or len(ids) > 10 or policy.get("baseline_audit") != previous["baseline_audit"] or policy.get("allow_metadata_scope_filter") is not True):
        raise ResearchError("Register exact metadata-only final diagnosis, scope exclusions and the existing 583-token authorization")
    diagnostic = policy.get("final_source_diagnostic", policy.get("final_diagnostic"))
    if diagnostic and engine.ledger.get(diagnostic, "newsapi_id_manifest_final_source")["source_id"] != previous["id"]:
        raise ResearchError("Final diagnostic refers to another immutable block proof")
    baseline, _ = load_baseline(engine, previous["baseline_audit"])
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    original_zip = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    verify_proof_bytes(original_zip)
    with zipfile.ZipFile(io.BytesIO(original_zip)) as archive:
        frames = {p["date_start"]: {"year": p["year"], **{d: set(archive.read(f"partitions/{p['date_start']}/{d}-ids.txt").decode().splitlines())
            for d in ("saved", "ascending", "reverse")}} for p in baseline["periods"]}
        prior_quarters = json.loads(archive.read("quarter-verification.json"))
        prior_blocks = json.loads(archive.read("block-verification.json"))
    metadata: dict[str, Json] = {}
    used_receipts = []
    attempted = set()
    for receipt in records(engine, "newsapi_id_receipt"):
        parameters = receipt["parameters"]
        if parameters.get("endpointVariant") != "article_info":
            continue
        covered = set(parameters.get("articleUri", [])) & set(ids)
        if covered and all(receipt.get("versions", {}).get(k) == context.versions[k] for k in ("selection", "question", "profile")):
            attempted.update(covered)
            used_receipts.append(receipt["id"])
            if receipt.get("outcome") == "received" and receipt.get("http_status") == 200:
                metadata.update(extract_info(receipt.get("response") or {}, sorted(covered)))
    wanted = sorted(set(ids)-attempted)
    calls = 0
    if wanted:
        if engine.config.offline or data.get("execute") is not True or not os.environ.get("EVENTREGISTRY_API_KEY"):
            raise ResearchError("Explicit live metadata-only execution and a credential are required")
        engine.ledger.record(session, "newsapi_id_manifest_final_plan", str(uuid.uuid4()), {"versions": context.versions,
            "source": previous["id"], "metadata_ids": wanted, "parameters": info_request(wanted), "scope": SCOPE})
        try:
            before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_final_metadata")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
            before = {}
        if before.get("outcome") == "received" and before.get("http_status") == 200 and number(before.get("response", {}).get("usedTokens")) is not None:
            try:
                receipt = dispatch(engine, session, context, info_request(wanted), "final_scope_metadata")
                calls += 1
                used_receipts.append(receipt["id"])
                if receipt.get("outcome") == "received" and receipt.get("http_status") == 200:
                    metadata.update(extract_info(receipt.get("response") or {}, wanted))
            except ResearchError as error:
                if not str(error).startswith(("ID-manifest authorization budget", "Account allowance", "Unresolved or excessive")):
                    raise
        if calls:
            try:
                dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_final_metadata")
                calls += 1
            except ResearchError as error:
                if not str(error).startswith("ID-manifest authorization budget"):
                    raise
    decisions = decide(ids, metadata)
    result, frames, scope_doc = apply_scope(previous, frames, decisions)
    scope_doc.update(metadata_receipts=used_receipts, metadata_receipt=used_receipts[-1] if used_receipts else None)
    receipts = records(engine, "newsapi_id_receipt")
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received" and r.get("http_status") == 200
        and number(r.get("response", {}).get("usedTokens")) is not None]
    initial = number(usages[0]["response"]["usedTokens"]) if usages else None
    latest = number(usages[-1]["response"]["usedTokens"]) if usages else None
    costs = [r for r in receipts if r.get("purpose") == "final_scope_metadata"]
    metadata_cost = (sum(r["billed_tokens"] for r in costs)
        if costs and all(r.get("billed_tokens") is not None for r in costs) else None)
    result.update(versions=context.versions, authorization_id=AUTH_ID, method=FINAL_METHOD, final_source=previous["id"],
        baseline_audit=previous["baseline_audit"], confirmation_source=first["id"], scope_decisions=decisions,
        scope_excluded_ids=scope_doc["excluded_ids"], diagnostics=diagnostics(previous), metadata_ids=ids,
        differences=[{"year": "2026", "direction": "observed_missing_api_id", **r} for r in decisions],
        observed_missing_candidates=previous["observed_missing_candidates"], metadata_receipts=used_receipts,
        metadata_receipt=scope_doc["metadata_receipt"], prior_reported_tokens=previous["budget"]["reported_tokens"],
        metadata_billed_tokens=metadata_cost, additional_metadata_tokens=metadata_cost,
        unavailable_metadata=sum(r["metadata"].get("status") != "available" for r in decisions),
        unknown_scope_decisions=sum(r["decision"] == "unknown" for r in decisions),
        budget=accounting(records(engine, "newsapi_id_intent"), receipts), baseline_used=initial, latest_used=latest,
        observed_account_delta=latest-initial if initial is not None and latest is not None else None,
        new_api_calls=calls, model_calls=0, generated_at=utc(),
        limitation="Metadata-only diagnosis of observed provider-ID differences. Exclusions use only exact reported date/language. No semantic relevance judgement, external census, fixed provider snapshot, or proof of original omission. Unknown metadata remains unsettled; original raw evidence is preserved.")
    reference = evidence_zip(engine, session, context, baseline, first, result, frames, method=FINAL_METHOD,
        extra_json={"final-scope-verification.json": scope_doc, "source-block-proof.json": previous,
            "quarter-verification.json": prior_quarters, "block-verification.json": prior_blocks})
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)),
        evidence_zip=reference, proof_path=export_proof(engine, session, reference, filename="id-manifest-final-proof.zip"))
    identifier = engine.ledger.record(session, "newsapi_id_manifest_final_audit", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
