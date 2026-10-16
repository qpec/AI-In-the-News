"""Fresh, bounded archive enumeration with fewer requested metadata fields."""
from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_id_manifest import AUTH_ID, CAP, dispatch, load_baseline, records
from .newsapi_id_manifest_archive_repair import REJECTION_RULE, budget
from .newsapi_id_manifest_proof import evidence_zip, export_proof, verify_proof_bytes
from .newsapi_id_manifest_resolution import minimal_enumeration, validate_enumeration
from .newsapi_id_manifest_resolution_run import _reconcile

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-minimal-metadata-recovery-v1"


def _policy(engine: Research, context: Context) -> Json:
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if policy.get("minimal_metadata_method") != METHOD or policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP:
        raise ResearchError("Register minimal metadata recovery under the original shared cap")
    return policy


def prepare(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    _policy(engine, context)
    source = records(engine, "newsapi_id_manifest_archive_repair")[-1]
    if any(context.versions[k] != source["versions"][k] for k in ("question", "selection", "profile")):
        raise ResearchError("Minimal metadata must preserve the original selection")
    result = {"versions": context.versions, "authorization_id": AUTH_ID, "method": METHOD,
        "source": source["id"], "metadata_ids": source["metadata_ids"], "budget": budget(engine),
        "templates": [minimal_enumeration(page, title) for page in range(1, 31) for title in (True, False)],
        "new_api_calls": 0, "model_calls": 0}
    identifier = engine.ledger.record(session, "newsapi_id_manifest_minimal_preparation", str(uuid.uuid4()), result)
    return {"id": identifier, **result}


def verify_package(archive: Any, comparison: Json) -> Json:
    doc = json.loads(archive.read("minimal-metadata-recovery.json"))
    policy = json.loads(archive.read("versions/policy.json"))["content"]
    preparation = doc["preparation"]
    expected_templates = [minimal_enumeration(page, title) for page in range(1, 31) for title in (True, False)]
    if (policy.get("minimal_metadata_method") != METHOD or policy.get("minimal_metadata_reservation") != 25
            or policy.get("minimal_metadata_templates") != expected_templates or policy.get("minimal_metadata_preparation") != preparation["id"]):
        raise AuditError("Minimal metadata proof lacks the exact registered bounded templates")
    pages = []
    for index, identifier in enumerate(doc["pages"], 1):
        row = json.loads(archive.read(f"receipts/{identifier}.json"))
        if row["parameters"] not in [minimal_enumeration(index), minimal_enumeration(index, False)]:
            raise AuditError("Minimal metadata page differs from its registered template")
        if row.get("raw_response"):
            row["response"] = json.loads(archive.read(f"responses/{identifier}.json"))
        pages.append(row)
    saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
    block = json.loads(archive.read("source-block-proof.json"))
    earlier = set().union(*(set(w["ascending"]["ids"]) for w in block["windows"][:2]))
    enumeration = validate_enumeration(pages, sorted(saved-earlier), allow_minimal=True)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as source:
        source.writestr("years/2026/saved-ids.txt", "\n".join(sorted(saved)))
        source.writestr("source-block-proof.json", canonical(block))
    controls = comparison["resolution_summary"]["controls"]
    expected = _reconcile({"_proof_bytes": inner.getvalue()}, preparation, controls, enumeration)
    if canonical(expected) != canonical(comparison["minimal_recovery_summary"]):
        raise AuditError("Minimal metadata result does not reproduce the exact raw pages")
    return {"status": "verified", "pages_checked": len(pages), "complete": enumeration["complete"],
        "records": enumeration["unique_ids_seen"], "retrievable_2026_complete": expected["retrievable_2026_complete"]}


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    policy = _policy(engine, context)
    prepared = {"id": policy["minimal_metadata_preparation"], **engine.ledger.get(policy["minimal_metadata_preparation"], "newsapi_id_manifest_minimal_preparation")}
    expected = [minimal_enumeration(page, title) for page in range(1, 31) for title in (True, False)]
    if policy.get("minimal_metadata_templates") != expected or policy.get("minimal_metadata_reservation") != 25:
        raise ResearchError("Bind all exact minimal templates and the empirical25-token reservation")
    previous = {"id": prepared["source"], **engine.ledger.get(prepared["source"], "newsapi_id_manifest_archive_repair")}
    if any(context.versions[k] != previous["versions"][k] for k in ("question", "selection", "profile")):
        raise ResearchError("Minimal recovery must preserve selection versions")
    if engine.config.offline or data.get("execute") is not True:
        raise ResearchError("Explicit live minimal metadata recovery required")
    pages: list[Json] = []
    rejected: list[str] = []
    calls = 0
    started = False
    stopped = None
    def perform(page: int, title: bool) -> Json:
        nonlocal calls, started
        parameters = minimal_enumeration(page, title)
        purpose = f"resolution_minimal_page_{page}_title_{title}"
        prior = [r for r in records(engine, "newsapi_id_receipt") if r["purpose"] == purpose]
        if prior:
            if len(prior) != 1 or prior[0]["versions"] != context.versions or prior[0]["parameters"] != parameters:
                raise ResearchError("Minimal metadata reuse requires one exact-version receipt")
            return prior[0]
        if not started:
            usage = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_minimal_metadata")
            started = True
            calls += 1
            if usage.get("outcome") != "received" or usage.get("http_status") != 200:
                raise ResearchError("Fresh account status unavailable")
        result = dispatch(engine, session, context, parameters, purpose)
        calls += 1
        return result
    total_seen = None
    seen: set[str] = set()
    try:
        for page in range(1, 31):
            row = perform(page, True)
            if (row.get("outcome") == "unknown" and row.get("http_status") == 200 and row.get("error_type") == "ResearchError"
                    and row.get("billed_tokens") is not None and row.get("raw_response") is None and row.get("raw_sha256")):
                if policy.get("minimal_title_fallback") is not True:
                    raise ResearchError("Metadata retention rejected; no fallback authorized")
                rejected.append(row["id"])
                if not any(r.get("receipt") == row["id"] for r in records(engine, "newsapi_id_receipt_resolution")):
                    engine.ledger.record(session, "newsapi_id_receipt_resolution", str(uuid.uuid4()), {
                        "versions": context.versions, "authorization_id": AUTH_ID, "method": METHOD, "rule": REJECTION_RULE,
                        "receipt": row["id"], "attempt": row["attempt"], "raw_sha256": row["raw_sha256"], "billed_tokens": row["billed_tokens"],
                        "resolution": "http_response_received_retention_rejected", "reason": "HTTP200 and known cost prove response receipt but content failed retention. Preserve the failed content as unavailable and its cost; use only the separately registered title-omitting request.",
                        "retry_same_request": False, "generated_at": utc()})
                row = perform(page, False)
            pages.append(row)
            section = (row.get("response") or {}).get("articles", {})
            total, items = section.get("totalResults"), section.get("results")
            print(json.dumps({"minimal_page": page, "returned": len(items) if isinstance(items, list) else None,
                "total": total, "billed_tokens": row.get("billed_tokens"), "title_requested": row["parameters"]["includeArticleTitle"]}), flush=True)
            if (row.get("outcome") != "received" or row.get("http_status") != 200 or row.get("headers", {}).get("req-archive") != "1"
                    or not isinstance(total, int) or isinstance(total, bool) or not 0 <= total <= 3000 or not isinstance(items, list)
                    or len(items) != min(100, max(0, total-100*(page-1))) or total_seen not in (None, total)):
                raise ResearchError("Minimal metadata page invalid, incomplete or total drifted")
            total_seen = total
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("uri"), str) or item["uri"] in seen:
                    raise ResearchError("Minimal metadata page has a missing or repeated identity")
                seen.add(item["uri"])
            if page*100 >= total:
                break
    except ResearchError as error:
        if isinstance(error, AuditError):
            raise
        stopped = str(error)
    if started:
        try:
            dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_minimal_metadata")
            calls += 1
        except ResearchError as error:
            if isinstance(error, AuditError):
                raise
            stopped = stopped or str(error)
    raw = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
    verify_proof_bytes(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = ("quarter-verification.json", "block-verification.json", "final-scope-verification.json", "source-block-proof.json", "resolution-verification.json", "prior-final-audit.json", "archive-uri-repair.json")
        extra = {name: json.loads(archive.read(name)) for name in names}
        baseline, _ = load_baseline(engine, previous["baseline_audit"])
        frames = {p["date_start"]: {"year": p["year"], **{d: set(archive.read(f"partitions/{p['date_start']}/{d}-ids.txt").decode().splitlines()) for d in ("saved", "ascending", "reverse")}} for p in baseline["periods"]}
        saved = set(archive.read("years/2026/saved-ids.txt").decode().splitlines())
        earlier = set().union(*(set(w["ascending"]["ids"]) for w in extra["source-block-proof.json"]["windows"][:2]))
    enumeration = validate_enumeration(pages, sorted(saved-earlier), allow_minimal=True)
    summary = _reconcile({**previous, "_proof_bytes": raw}, prepared, previous["resolution_summary"]["controls"], enumeration)
    receipts = records(engine, "newsapi_id_receipt")
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received" and r.get("http_status") == 200 and isinstance((r.get("response") or {}).get("usedTokens"), (int, float))]
    latest = usages[-1]["response"]["usedTokens"]
    resolutions = records(engine, "newsapi_id_receipt_resolution")
    result = {**{k: v for k, v in previous.items() if k not in {"id", "proof_artifact", "proof_self_check", "proof_path"}},
        "versions": context.versions, "method": METHOD, "minimal_source": previous["id"], "minimal_recovery_summary": summary,
        "budget": budget(engine), "latest_used": latest, "observed_account_delta": latest-previous["baseline_used"],
        "minimal_new_api_calls": calls, "minimal_stopped": stopped, "generated_at": utc(),
        "supplemental_record_refs": [prepared["id"], previous["id"], *[r["id"] for r in resolutions]]}
    extra["minimal-metadata-recovery.json"] = {"preparation": prepared, "pages": [r["id"] for r in pages],
        "rejected_primary_receipts": rejected, "response_reconciliations": resolutions}
    first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
    reference = evidence_zip(engine, session, context, baseline, first, result, frames, extra_json=extra, method=METHOD)
    result.update(proof_artifact=reference, proof_self_check=verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference)))
    result["proof_path"] = export_proof(engine, session, reference, filename="id-manifest-final-proof.zip")
    identifier = engine.ledger.record(session, "newsapi_id_manifest_minimal_recovery", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
