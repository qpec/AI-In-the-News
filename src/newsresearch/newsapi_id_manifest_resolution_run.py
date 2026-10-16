"""Bounded provider-ID reconciliation with unchanged-keyword metadata enumeration."""
from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_id_manifest import AUTH_ID, CAP, accounting, dispatch, load_baseline, records
from .newsapi_id_manifest_details import metadata
from .newsapi_id_manifest_final_audit import RESOLUTION_METHOD
from .newsapi_id_manifest_proof import evidence_zip, export_proof, verify_proof_bytes
from . import newsapi_id_manifest_resolution as helpers

if TYPE_CHECKING:
    from .runtime import Research


def _policy(engine: Research, context: Context) -> Json:
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("resolution_method") != RESOLUTION_METHOD or policy.get("authorization_id") != AUTH_ID
            or policy.get("max_tokens") != CAP):
        raise ResearchError("Resolution must retain the original authorization, selection and cumulative cap")
    return policy


def prepare(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    policy = _policy(engine, context)
    if policy.get("resolution_prepare_rule") != "maximum-saved-2026-uri-control-v1":
        raise ResearchError("Register the deterministic saved control selection before inspection")
    previous = records(engine, "newsapi_id_manifest_final_audit")[-1]
    if any(context.versions[k] != previous["versions"][k] for k in ("selection", "question", "profile")):
        raise ResearchError("Resolution must preserve the original selection")
    _, identities = load_baseline(engine, previous["baseline_audit"])
    identifiers = [r for r in identities["2026-01-01"]["identifiers"] if r["uri"] not in previous["metadata_ids"]]
    chosen = max(identifiers, key=lambda r: (len(r["uri"]), r["uri"]))
    receipt = engine.ledger.get(chosen["receipt"], "newsapi_collection_receipt")
    article = receipt["response"]["articles"]["results"][chosen["index"]]
    from .common import digest
    if article["uri"] != chosen["uri"] or digest(article) != chosen["record_hash"]:
        raise AuditError("Saved control does not reproduce the original source version")
    planned = helpers.templates(previous["metadata_ids"], chosen["uri"])
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "method": RESOLUTION_METHOD,
        "source_audit": previous["id"], "source_versions": previous["versions"], "metadata_ids": previous["metadata_ids"],
        "control_uri": chosen["uri"], "control_metadata": metadata(article), "control_locator": chosen,
        "templates": planned, "budget": accounting(records(engine, "newsapi_id_intent"), records(engine, "newsapi_id_receipt")),
        "new_api_calls": 0, "model_calls": 0, "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_resolution_preparation", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def _reconcile(previous: Json, preparation: Json, controls: Json, enumeration: Json) -> Json:
    resolved = helpers.resolve(controls, enumeration, preparation["metadata_ids"])
    with zipfile.ZipFile(io.BytesIO(previous["_proof_bytes"])) as archive:
        saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
        block = json.loads(archive.read("source-block-proof.json"))
    earlier = set().union(*(set(w["ascending"]["ids"]) for w in block["windows"][:2]))
    actual = set(enumeration["ids"])
    complete = bool(enumeration["complete"]) and not (earlier & actual)
    current = earlier | actual
    return {"controls": controls, "enumeration": enumeration, "candidate_resolution": resolved,
        "retrievable_2026_complete": complete,
        "retrievable_2026_ids": sorted(current), "retrievable_2026_count": len(current),
        "retrievable_2026_missing_saved_ids": sorted(current-saved) if complete else None,
        "retrievable_2026_saved_only_ids": sorted(saved-current) if complete else None,
        "retrievable_2026_saved_coverage_percent": 100*len(current & saved)/len(current) if complete and current else None,
        "raw_manifest_disagreement_preserved": True,
        "limitation": "A complete metadata enumeration describes retrievable matching records at request times. Invalid provider IDs remain unresolvable index observations, not proven deletions, date/language exclusions, or negative article findings. Earlier agreeing blocks are reused; there is no fixed provider snapshot or external news census."}


def compute(engine: Research, previous: Json, preparation: Json, lookup_receipts: dict[str, Json], pages: list[Json]) -> Json:
    original = engine.ledger.get(previous["metadata_receipts"][-1], "newsapi_id_receipt")
    sdk, listing = lookup_receipts.get("sdk", {}), lookup_receipts.get("list", {})
    controls = helpers.parse_controls(sdk.get("response") or {}, listing.get("response") or {},
        preparation["metadata_ids"], preparation["control_uri"], original.get("response") or {},
        sdk_http_status=sdk.get("http_status"), list_http_status=listing.get("http_status"), original_http_status=original.get("http_status"))
    raw = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
        block = json.loads(archive.read("source-block-proof.json"))
    earlier = set().union(*(set(w["ascending"]["ids"]) for w in block["windows"][:2]))
    enumeration = helpers.validate_enumeration(pages, sorted(saved-earlier))
    return _reconcile({**previous, "_proof_bytes": raw}, preparation, controls, enumeration)


def verify_resolution_package(archive: Any, comparison: Json) -> Json:
    document = json.loads(archive.read("resolution-verification.json"))
    policy = json.loads(archive.read("versions/policy.json"))["content"]
    preparation = document["preparation"]
    planned = helpers.templates(preparation["metadata_ids"], preparation["control_uri"])
    if (policy.get("resolution_method") != RESOLUTION_METHOD or policy.get("resolution_templates") != planned["all"]
            or policy.get("resolution_preparation") != preparation["id"]):
        raise AuditError("Resolution proof does not match its exact registered templates")
    previous = json.loads(archive.read("prior-final-audit.json"))
    if (policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP
            or policy.get("resolution_source") != previous["id"] or preparation["source_audit"] != previous["id"]
            or comparison["prior_final_audit"] != previous["id"] or preparation["metadata_ids"] != previous["metadata_ids"]):
        raise AuditError("Resolution proof changed its source, suspect IDs or cumulative authorization")
    original = json.loads(archive.read(f"receipts/{previous['metadata_receipts'][-1]}.json"))
    if original.get("raw_response"):
        original["response"] = json.loads(archive.read(f"responses/{previous['metadata_receipts'][-1]}.json"))
    def receipt(identifier: str, expected: Json) -> Json:
        row = json.loads(archive.read(f"receipts/{identifier}.json"))
        if row["parameters"] != expected:
            raise AuditError("Resolution receipt differs from the registered exact template")
        if row.get("raw_response"):
            row["response"] = json.loads(archive.read(f"responses/{identifier}.json"))
        return row
    sdk = receipt(document["lookups"]["sdk"], planned["control_sdk"]) if document["lookups"].get("sdk") else {}
    listing = receipt(document["lookups"]["list"], planned["control_list"]) if document["lookups"].get("list") else {}
    pages = [receipt(ref, helpers.enumeration(page)) for page, ref in enumerate(document["pages"], 1)]
    controls = helpers.parse_controls(sdk.get("response") or {}, listing.get("response") or {},
        preparation["metadata_ids"], preparation["control_uri"], original.get("response") or {},
        sdk_http_status=sdk.get("http_status"), list_http_status=listing.get("http_status"), original_http_status=original.get("http_status"))
    saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
    if preparation["control_uri"] not in saved or preparation["control_uri"] in preparation["metadata_ids"]:
        raise AuditError("Resolution positive control is not a separate original saved ID")
    block = json.loads(archive.read("source-block-proof.json"))
    earlier = set().union(*(set(w["ascending"]["ids"]) for w in block["windows"][:2]))
    enumeration = helpers.validate_enumeration(pages, sorted(saved-earlier))
    # Reconstruct only the prior proof fields used by deterministic reconciliation.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as inner:
        inner.writestr("years/2026/saved-ids.txt", "\n".join(sorted(saved)))
        inner.writestr("source-block-proof.json", canonical(block))
    expected = _reconcile({"_proof_bytes": buffer.getvalue()}, preparation, controls, enumeration)
    if canonical(expected) != canonical(comparison["resolution_summary"]):
        raise AuditError("Resolution summary does not reproduce raw lookup and enumeration evidence")
    return {"status": "verified", "lookup_routes_checked": len(document["lookups"]),
        "metadata_pages_checked": len(pages), "metadata_enumeration_complete": enumeration["complete"],
        "retrievable_2026_complete": expected["retrievable_2026_complete"]}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    policy = _policy(engine, context)
    preparation = {"id": policy["resolution_preparation"], **engine.ledger.get(policy["resolution_preparation"], "newsapi_id_manifest_resolution_preparation")}
    previous = {"id": preparation["source_audit"], **engine.ledger.get(preparation["source_audit"], "newsapi_id_manifest_final_audit")}
    planned = helpers.templates(preparation["metadata_ids"], preparation["control_uri"])
    if (policy.get("resolution_source") != previous["id"] or policy.get("resolution_templates") != planned["all"]
            or any(context.versions[k] != previous["versions"][k] for k in ("selection", "question", "profile"))):
        raise ResearchError("Register exact templates and immutable source before resolving provider IDs")
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit authorized live resolution is required")
    calls = 0
    started = False
    stopped = None
    def perform(parameters: Json, purpose: str) -> Json:
        nonlocal calls, started
        prior = [r for r in records(engine, "newsapi_id_receipt") if r["purpose"] == purpose and r["parameters"] == parameters]
        if prior:
            if len(prior) != 1 or prior[0]["versions"] != context.versions:
                raise ResearchError("Resolution reuse requires exact registered versions and one immutable receipt")
            return prior[0]
        if not started:
            usage = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_resolution")
            calls += 1
            started = True
            if usage.get("outcome") != "received" or usage.get("http_status") != 200:
                raise ResearchError("Fresh account usage is unavailable")
        row = dispatch(engine, session, context, parameters, purpose)
        calls += 1
        return row
    lookups: dict[str, Json] = {}
    pages = []
    first_total = None
    seen_ids: set[str] = set()
    try:
        for name, key in (("sdk", "control_sdk"), ("list", "control_list")):
            lookups[name] = perform(planned[key], "resolution_" + name + "_control")
            if lookups[name].get("outcome") != "received":
                raise ResearchError("Resolution lookup has an unknown outcome")
        for page in range(1, 31):
            row = perform(helpers.enumeration(page), f"resolution_keyword_page_{page}")
            pages.append(row)
            section = (row.get("response") or {}).get("articles", {})
            total, items = section.get("totalResults"), section.get("results")
            print(json.dumps({"resolution_page": page, "http_status": row.get("http_status"), "returned": len(items) if isinstance(items, list) else None,
                "provider_total": total, "billed_tokens": row.get("billed_tokens")}), flush=True)
            if (row.get("outcome") != "received" or row.get("http_status") != 200 or row.get("headers", {}).get("req-archive") != "1"
                    or not isinstance(total, int) or isinstance(total, bool) or not 0 <= total <= 3000 or not isinstance(items, list)
                    or len(items) != min(100, max(0, total-100*(page-1)))):
                raise ResearchError("Resolution metadata page is incomplete or exceeds its registered frame")
            if first_total is not None and first_total != total:
                raise ResearchError("Resolution metadata total drifted between pages")
            first_total = total
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("uri"), str) or item["uri"] in seen_ids:
                    raise ResearchError("Resolution metadata page has a missing or repeated identity")
                seen_ids.add(item["uri"])
            if page*100 >= total:
                break
    except ResearchError as error:
        if isinstance(error, AuditError):
            raise
        stopped = str(error)
    if started:
        try:
            dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_resolution")
            calls += 1
        except ResearchError as error:
            if isinstance(error, AuditError):
                raise
            stopped = stopped or str(error)
    summary = compute(engine, previous, preparation, lookups, pages)
    raw = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    verify_proof_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        extra = {name: json.loads(archive.read(name)) for name in ("quarter-verification.json", "block-verification.json", "final-scope-verification.json", "source-block-proof.json")}
        baseline, _ = load_baseline(engine, previous["baseline_audit"])
        frames = {p["date_start"]: {"year": p["year"], **{d: set(archive.read(f"partitions/{p['date_start']}/{d}-ids.txt").decode().splitlines()) for d in ("saved", "ascending", "reverse")}} for p in baseline["periods"]}
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    receipts = records(engine, "newsapi_id_receipt")
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received" and r.get("http_status") == 200]
    latest = usages[-1]["response"].get("usedTokens") if usages else None
    result = {**{k: v for k, v in previous.items() if k not in {"id", "proof_artifact", "proof_self_check", "proof_path", "evidence_zip"}},
        "versions": context.versions, "method": RESOLUTION_METHOD, "prior_final_audit": previous["id"],
        "resolution_summary": summary, "stopped": stopped, "new_api_calls": calls, "generated_at": utc(),
        "resolution_prior_tokens": previous["budget"]["reported_tokens"],
        "budget": accounting(records(engine, "newsapi_id_intent"), receipts), "latest_used": latest,
        "observed_account_delta": latest-previous["baseline_used"] if latest is not None else None}
    document = {"preparation": preparation, "lookups": {k: v["id"] for k, v in lookups.items()}, "pages": [r["id"] for r in pages]}
    extra.update({"prior-final-audit.json": previous, "resolution-verification.json": document})
    reference = evidence_zip(engine, session, context, baseline, first, result, frames, extra_json=extra, method=RESOLUTION_METHOD)
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)))
    result["prior_proof_path"] = export_proof(engine, session, previous["proof_artifact"], filename="id-manifest-final-proof-before-resolution.zip")
    result["proof_path"] = export_proof(engine, session, reference, filename="id-manifest-final-proof.zip")
    identifier = engine.ledger.record(session, "newsapi_id_manifest_resolution", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
