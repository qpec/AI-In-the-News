"""Test archive routing for the same opaque IDs; never guess alternate URIs."""
from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_id_manifest import AUTH_ID, CAP, accounting, dispatch, load_baseline, records
from .newsapi_id_manifest_details import metadata
from .newsapi_id_manifest_final_audit import decide
from .newsapi_id_manifest_proof import evidence_zip, export_proof, verify_proof_bytes
from .newsapi_id_manifest_resolution import templates

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-archive-uri-repair-v1"
REJECTION_RULE = "observed-http200-known-cost-no-retained-data-v1"


def _policy(engine: Research, context: Context) -> Json:
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("archive_repair_method") != METHOD or policy.get("authorization_id") != AUTH_ID
            or policy.get("max_tokens") != CAP or policy.get("response_rejection_rule") != REJECTION_RULE):
        raise ResearchError("Register the archive diagnostic and received-response reconciliation under the original cap")
    return policy


def budget(engine: Research) -> Json:
    return accounting(records(engine, "newsapi_id_intent"), records(engine, "newsapi_id_receipt"), records(engine, "newsapi_id_receipt_resolution"))


def prepare(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    _policy(engine, context)
    previous = records(engine, "newsapi_id_manifest_resolution")[-1]
    if any(context.versions[k] != previous["versions"][k] for k in ("question", "selection", "profile")):
        raise ResearchError("Archive diagnostic must preserve the unchanged original selection")
    raw = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    verify_proof_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        old_document = json.loads(archive.read("resolution-verification.json"))
        old_plan = old_document["preparation"]
    numeric = next((uri for uri in previous["resolution_summary"]["enumeration"]["ids"] if uri.isdigit()), None)
    if numeric is None:
        raise ResearchError("A retained numeric-URI metadata control is required")
    parameters = {**templates(old_plan["metadata_ids"], old_plan["control_uri"])["control_list"],
        "articleUri": [*old_plan["metadata_ids"], old_plan["control_uri"], numeric], "dateStart": "2026-01-01"}
    reconciled: list[str] = []
    existing = records(engine, "newsapi_id_receipt_resolution")
    for receipt in records(engine, "newsapi_id_receipt"):
        if receipt.get("outcome") != "unknown":
            continue
        if (receipt.get("http_status") != 200 or receipt.get("error_type") != "ResearchError"
                or receipt.get("billed_tokens") is None or receipt.get("raw_response") is not None
                or not isinstance(receipt.get("raw_sha256"), str) or len(receipt["raw_sha256"]) != 64):
            raise ResearchError("An unknown transport outcome cannot be reconciled by the observed-response rule")
        prior = [r for r in existing if r.get("receipt") == receipt["id"]]
        if prior:
            reconciled.extend(r["id"] for r in prior)
            continue
        item = {"versions": context.versions, "authorization_id": AUTH_ID, "method": METHOD, "rule": REJECTION_RULE,
            "receipt": receipt["id"], "attempt": receipt["attempt"], "raw_sha256": receipt["raw_sha256"],
            "billed_tokens": receipt["billed_tokens"], "resolution": "http_response_received_retention_rejected",
            "reason": "HTTP200 and the exact provider charge establish response receipt. Parsing or retention validation failed. The original content and specific rejection cause are unavailable. No usable page, released charge or retry is inferred.",
            "retry_same_request": False, "generated_at": utc()}
        reconciled.append(engine.ledger.record(session, "newsapi_id_receipt_resolution", str(uuid.uuid4()), item))
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "method": METHOD,
        "source": previous["id"], "metadata_ids": old_plan["metadata_ids"],
        "controls": [old_plan["control_uri"], numeric], "parameters": parameters,
        "prior_lookup_receipts": old_document["lookups"],
        "receipt_reconciliations": reconciled, "budget": budget(engine), "new_api_calls": 0, "model_calls": 0}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_archive_repair_preparation", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def summarize(receipt: Json, prepared: Json, saved: set[str], old_controls: Json) -> Json:
    response = receipt.get("response") or {}
    section = response.get("articles", {})
    items = section.get("results") if isinstance(section, dict) else None
    total = section.get("totalResults") if isinstance(section, dict) else None
    wanted = [*prepared["metadata_ids"], *prepared["controls"]]
    observed = [r.get("uri") for r in items if isinstance(r, dict)] if isinstance(items, list) else []
    complete = (receipt.get("outcome") == "received" and receipt.get("http_status") == 200
        and isinstance(total, int) and not isinstance(total, bool) and total == len(observed)
        and len(observed) == len(set(observed)) and set(observed) <= set(wanted))
    by_uri = {r["uri"]: {"status": "available", **metadata(r)} for r in (items if isinstance(items, list) else [])
        if isinstance(r, dict) and r.get("uri") in wanted} if complete else {}
    decisions = decide(prepared["metadata_ids"], by_uri)
    rows = [{**row, "in_original_saved_collection": row["article_uri"] in saved,
        "metadata_recovered": row["metadata"].get("status") == "available"} for row in decisions]
    eligible = sorted(row["article_uri"] for row in rows if row["decision"] == "eligible")
    excluded = sorted(row["article_uri"] for row in rows if row["decision"] == "excluded")
    unknown = sorted(row["article_uri"] for row in rows if row["decision"] == "unknown")
    population = saved | set(eligible)
    return {"rows": rows, "archive_header": receipt.get("headers", {}).get("req-archive"),
        "original_lookup_headers": old_controls, "complete_exact_id_response": bool(complete),
        "controls_available": {uri: uri in by_uri for uri in prepared["controls"]},
        "eligible_ids": eligible, "excluded_ids": excluded, "unknown_ids": unknown,
        "eligible_missing_from_original_saved_ids": sorted(set(eligible)-saved),
        "all_six_metadata_recovered": all(row["metadata_recovered"] for row in rows),
        "observed_eligible_2026_union_count": len(population), "original_saved_2026_count": len(saved),
        "original_coverage_of_observed_eligible_union_percent": 100*len(saved)/len(population) if not unknown else None,
        "metadata_coverage_of_observed_eligible_union_percent": 100.0 if not unknown else None,
        "raw_sort_disagreement_preserved": True, "provider_population_completeness_proven": False,
        "limitation": "Only the previously observed six IDs and controls were looked up. No generated aliases, article bodies, new relevance inference or claim of a fixed provider population. A rejected metadata page remains unavailable; the optional full-window metadata enumeration remains partial."}


def verify_package(archive: Any, comparison: Json) -> Json:
    doc = json.loads(archive.read("archive-uri-repair.json"))
    policy = json.loads(archive.read("versions/policy.json"))["content"]
    prepared = doc["preparation"]
    if (policy.get("archive_repair_method") != METHOD or policy.get("archive_repair_preparation") != prepared["id"]
            or policy.get("resolution_extension_templates") != [prepared["parameters"]]):
        raise AuditError("Archive repair proof lacks its exact registered template")
    receipt = json.loads(archive.read(f"receipts/{doc['receipt']}.json"))
    if receipt["parameters"] != prepared["parameters"]:
        raise AuditError("Archive repair changed its exact-ID template")
    if receipt.get("raw_response"):
        receipt["response"] = json.loads(archive.read(f"responses/{doc['receipt']}.json"))
    saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
    old_headers = {name: json.loads(archive.read(f"receipts/{identifier}.json")).get("headers", {})
        for name, identifier in prepared["prior_lookup_receipts"].items()}
    expected = summarize(receipt, prepared, saved, old_headers)
    if canonical(expected) != canonical(comparison["archive_repair_summary"]):
        raise AuditError("Archive repair summary does not reproduce exact raw metadata")
    receipts = [json.loads(archive.read(name)) for name in archive.namelist() if name.startswith("receipts/")]
    intents = [json.loads(archive.read(name)) for name in archive.namelist() if name.startswith("intents/")]
    resolutions = doc["response_reconciliations"]
    by_id = {r["id"]: r for r in receipts}
    for item in resolutions:
        rejected = by_id[item["receipt"]]
        if (item["rule"] != REJECTION_RULE or rejected.get("http_status") != 200
                or rejected.get("error_type") != "ResearchError" or rejected.get("raw_response") is not None
                or rejected.get("billed_tokens") != item["billed_tokens"] or rejected.get("raw_sha256") != item["raw_sha256"]
                or rejected["attempt"] != item["attempt"]):
            raise AuditError("Response-rejection reconciliation lacks observable receipt evidence")
    replay_budget = accounting(intents, receipts, resolutions)
    for key, value in replay_budget.items():
        actual = comparison["budget"][key]
        if (sorted(value) != sorted(actual)) if isinstance(value, list) else value != actual:
            raise AuditError("Archive-repair cumulative budget does not reproduce all retained intents and receipts")
    return {"status": "verified", "metadata_recovered": sum(row["metadata_recovered"] for row in expected["rows"]),
        "archive_header": expected["archive_header"], "unknown_scope": len(expected["unknown_ids"])}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    policy = _policy(engine, context)
    prepared = {"id": policy["archive_repair_preparation"], **engine.ledger.get(policy["archive_repair_preparation"], "newsapi_id_manifest_archive_repair_preparation")}
    if policy.get("resolution_extension_templates") != [prepared["parameters"]]:
        raise ResearchError("Bind the one exact archive-date diagnostic before dispatch")
    previous = {"id": prepared["source"], **engine.ledger.get(prepared["source"], "newsapi_id_manifest_resolution")}
    if any(context.versions[k] != previous["versions"][k] for k in ("selection", "question", "profile")):
        raise ResearchError("Archive repair cannot change selection versions")
    prior = [r for r in records(engine, "newsapi_id_receipt") if r["purpose"] == "resolution_archive_uri_repair"]
    if prior:
        if len(prior) != 1 or prior[0]["versions"] != context.versions:
            raise ResearchError("Archive repair reuse requires the exact prior versions")
        receipt = prior[0]
    else:
        if engine.config.offline or data.get("execute") is not True:
            raise ResearchError("Explicit live archive diagnostic required")
        before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_archive_uri_repair")
        if before.get("outcome") != "received" or before.get("http_status") != 200:
            raise ResearchError("Fresh account status is unavailable")
        receipt = dispatch(engine, session, context, prepared["parameters"], "resolution_archive_uri_repair")
        dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_archive_uri_repair")
    raw = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    verify_proof_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        extra = {name: json.loads(archive.read(name)) for name in ("quarter-verification.json", "block-verification.json", "final-scope-verification.json", "source-block-proof.json", "resolution-verification.json", "prior-final-audit.json")}
        baseline, _ = load_baseline(engine, previous["baseline_audit"])
        frames = {p["date_start"]: {"year": p["year"], **{d: set(archive.read(f"partitions/{p['date_start']}/{d}-ids.txt").decode().splitlines()) for d in ("saved", "ascending", "reverse")}} for p in baseline["periods"]}
        saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
    headers = {name: engine.ledger.get(identifier, "newsapi_id_receipt").get("headers", {}) for name, identifier in prepared["prior_lookup_receipts"].items()}
    summary = summarize(receipt, prepared, saved, headers)
    receipts = records(engine, "newsapi_id_receipt")
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received" and r.get("http_status") == 200 and isinstance((r.get("response") or {}).get("usedTokens"), (int, float))]
    latest = usages[-1]["response"]["usedTokens"]
    result = {**{k: v for k, v in previous.items() if k not in {"id", "proof_artifact", "proof_self_check", "proof_path"}},
        "versions": context.versions, "method": METHOD, "archive_repair_source": previous["id"],
        "supplemental_record_refs": [prepared["id"], previous["id"], *prepared["receipt_reconciliations"]],
        "archive_repair_summary": summary, "archive_repair_receipt": receipt["id"], "budget": budget(engine),
        "latest_used": latest, "observed_account_delta": latest-previous["baseline_used"], "generated_at": utc()}
    extra["archive-uri-repair.json"] = {"preparation": prepared, "receipt": receipt["id"],
        "response_reconciliations": records(engine, "newsapi_id_receipt_resolution")}
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    reference = evidence_zip(engine, session, context, baseline, first, result, frames, extra_json=extra, method=METHOD)
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)))
    result["proof_path"] = export_proof(engine, session, reference, filename="id-manifest-final-proof.zip")
    identifier = engine.ledger.record(session, "newsapi_id_manifest_archive_repair", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
