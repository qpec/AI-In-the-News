"""Audited reverse-order confirmation and a self-contained protected evidence bundle."""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
import io
import json
import os
from pathlib import Path
import tempfile
import time
from typing import TYPE_CHECKING
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, require_active, utc
from .newsapi_collection import number
from .newsapi_id_manifest import (
    AUTH_ID, CAP, METHOD, accounting, compare_partition, dispatch, load_baseline, parse_manifest, records, request,
)

if TYPE_CHECKING:
    from .runtime import Research

CONFIRM_METHOD = "nl-cyber-id-manifest-reverse-proof-v1"
PAGE_SIZE = 5000
RECENT_WINDOW_METHOD = "nl-cyber-quarter-recent-window-v1"
LIMITATION = (
    "Agreement of independent ascending and descending pagination establishes the observed provider ID set "
    "for these exact keywords and dates. It is not an external census of Dutch news, a fixed provider snapshot, "
    "proof of historical omission, semantic relevance, or publisher-body completeness. Local hashes are not "
    "independent attestation. No article text is requested by this confirmation."
)


def archive_or_recent(receipt: Json, allow_recent: bool = False) -> bool:
    archive = receipt.get("headers", {}).get("req-archive")
    if archive == "1":
        return True
    if not allow_recent or archive != "0":
        return False
    try:
        observed = date.fromisoformat(receipt["completed_at"][:10])
        start = date.fromisoformat(receipt["parameters"]["dateStart"])
        end = date.fromisoformat(receipt["parameters"]["dateEnd"])
    except (KeyError, TypeError, ValueError):
        return False
    return observed - timedelta(days=30) <= start <= end <= observed


def reverse_request(start: str, end: str, page: int) -> Json:
    return {**request(start, end, page, PAGE_SIZE), "uriWgtListSortByAsc": False}


def phase_receipts(receipts: list[Json], start: str, end: str, ascending: bool) -> list[Json]:
    """Require the complete exact predicate template, not just a sort flag/date pair."""
    result = []
    for receipt in receipts:
        parameters = receipt["parameters"]
        page = parameters.get("uriWgtListPage")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            continue
        expected = request(start, end, page, PAGE_SIZE) if ascending else reverse_request(start, end, page)
        if canonical(parameters) == canonical(expected):
            result.append(receipt)
    return result


def compare_frames(baseline: Json, identities: Json, first_receipts: list[Json],
                   reverse_receipts: list[Json]) -> tuple[Json, dict[str, Json]]:
    periods = []
    frames: dict[str, Json] = {}
    for period in baseline["periods"]:
        start, end = period["date_start"], period["date_end"]
        saved_ids = set(identities[start]["uri_counts"])
        asc = phase_receipts(first_receipts, start, end, True)
        desc = phase_receipts(reverse_receipts, start, end, False)
        first = compare_partition(saved_ids, asc, PAGE_SIZE)
        if not first["complete"]:
            raise ResearchError("Frozen ascending source does not independently enumerate every expected page")
        reverse = compare_partition(saved_ids, desc, PAGE_SIZE)
        first_ids = {uri for r in asc if r.get("manifest_status") == "valid" for uri in r["normalized_ids"]}
        reverse_ids = {uri for r in desc if r.get("manifest_status") == "valid" for uri in r["normalized_ids"]}
        ascending_order = [uri for r in sorted(asc, key=lambda r: r["parameters"]["uriWgtListPage"])
            if r.get("manifest_status") == "valid" for uri in r["normalized_ids"]]
        reverse_order = [uri for r in sorted(desc, key=lambda r: r["parameters"]["uriWgtListPage"])
            if r.get("manifest_status") == "valid" for uri in r["normalized_ids"]]
        complete = reverse["complete"]
        periods.append({"year": period["year"], "date_start": start, "date_end": end,
            **reverse, "ascending_ids": len(first_ids), "ascending_provider_total": first["provider_total"],
            "ascending_receipts": first["manifest_receipts"],
            "returned_order_differs": ascending_order != reverse_order if complete else None,
            "ascending_order_sha256": hashlib.sha256(canonical(ascending_order).encode()).hexdigest(),
            "reverse_order_sha256": hashlib.sha256(canonical(reverse_order).encode()).hexdigest(),
            "ascending_reverse_equal": first_ids == reverse_ids if complete else None,
            "ascending_only_ids": sorted(first_ids-reverse_ids) if complete else None,
            "reverse_only_ids": sorted(reverse_ids-first_ids),
            "saved_equals_reverse": saved_ids == reverse_ids if complete else None,
            "reverse_attempts": len(desc), "invalid_reverse_attempts": sum(r.get("manifest_status") != "valid" for r in desc)})
        frames[start] = {"year": period["year"], "saved": saved_ids, "ascending": first_ids, "reverse": reverse_ids}
    years = []
    for year in sorted({p["year"] for p in periods}):
        selected = [p for p in periods if p["year"] == year]
        grouped = [f for f in frames.values() if f["year"] == year]
        saved_ids = set().union(*(f["saved"] for f in grouped))
        first_ids = set().union(*(f["ascending"] for f in grouped))
        reverse_ids = set().union(*(f["reverse"] for f in grouped))
        complete = all(p["complete"] for p in selected)
        years.append({"year": year, "saved_ids": len(saved_ids), "ascending_ids": len(first_ids),
            "ascending_provider_total": sum(p["ascending_provider_total"] for p in selected),
            "reverse_ids": len(reverse_ids), "manifest_ids_seen": len(reverse_ids),
            "reverse_provider_total": sum(p["provider_total"] for p in selected) if all(p["provider_total"] is not None for p in selected) else None,
            "complete": complete, "ascending_reverse_equal": first_ids == reverse_ids if complete else None,
            "ascending_only_ids": sorted(first_ids-reverse_ids) if complete else None,
            "reverse_only_ids": sorted(reverse_ids-first_ids), "common_ids": len(saved_ids & reverse_ids),
            "manifest_only_ids": sorted(reverse_ids-saved_ids),
            "saved_only_ids": sorted(saved_ids-reverse_ids) if complete else None,
            "saved_equals_reverse": saved_ids == reverse_ids if complete else None,
            "saved_coverage_of_manifest_percent": 100*len(saved_ids & reverse_ids)/len(reverse_ids) if complete and reverse_ids else None,
            "expected_pages": sum(p["expected_pages"] for p in selected) if all(p["expected_pages"] is not None for p in selected) else None,
            "pages": sum(p["pages"] for p in selected)})
        years[-1].update(reverse_ids_seen=years[-1]["reverse_ids"],
            reverse_only_vs_saved_ids=years[-1]["manifest_only_ids"],
            saved_only_vs_reverse_ids=years[-1]["saved_only_ids"],
            saved_coverage_of_reverse_percent=years[-1]["saved_coverage_of_manifest_percent"])
    complete = all(p["complete"] for p in periods)
    equal = all(p["ascending_reverse_equal"] for p in periods) if complete else None
    return {"periods": periods, "years": years, "complete": complete,
        "ascending_reverse_equal": equal,
        "returned_order_differs_all_partitions": all(p["returned_order_differs"] for p in periods) if complete else None,
        "saved_equals_reverse": all(y["saved_equals_reverse"] for y in years) if complete else None}, frames


def _first_pass(engine: Research, policy: Json, context: Context) -> tuple[Json, list[Json]]:
    complete = [r for r in records(engine, "newsapi_id_manifest_test")
        if r.get("periods") and all(p.get("complete") for p in r["periods"])]
    if not complete or policy.get("confirmation_source") != complete[-1]["id"]:
        raise ResearchError("Bind the latest complete immutable ascending manifest result")
    first = complete[-1]
    if (first.get("page_size") != PAGE_SIZE or policy.get("baseline_audit") != first.get("baseline_audit")
            or any(context.versions[k] != first["versions"].get(k) for k in ("selection", "question", "profile"))):
        raise ResearchError("Confirmation must preserve the original baseline and selection/question/profile versions")
    identifiers = list(dict.fromkeys(ref for p in first["periods"] for ref in p["manifest_receipts"]))
    receipts = [{"id": ref, **engine.ledger.get(ref, "newsapi_id_receipt")} for ref in identifiers]
    if any(r.get("authorization_id") != AUTH_ID or r["parameters"].get("uriWgtListSortByAsc") is not True
           or r.get("headers", {}).get("req-archive") != "1" for r in receipts):
        raise ResearchError("Ascending source receipts must be archive-confirmed and separate from reverse pages")
    return first, receipts


def _state(engine: Research, baseline: Json, identities: Json, first: Json,
           first_receipts: list[Json], context: Context, metadata_result: str | None) -> tuple[Json, dict[str, Json]]:
    receipts = records(engine, "newsapi_id_receipt")
    result, frames = compare_frames(baseline, identities, first_receipts, receipts)
    usages = [r for r in receipts if r["purpose"].startswith("usage") and r.get("outcome") == "received"
        and r.get("http_status") == 200 and number(r.get("response", {}).get("usedTokens")) is not None]
    initial = number(usages[0]["response"]["usedTokens"]) if usages else None
    latest = number(usages[-1]["response"]["usedTokens"]) if usages else None
    reverse = [r for p in baseline["periods"] for r in phase_receipts(receipts, p["date_start"], p["date_end"], False)]
    result.update(versions=context.versions, authorization_id=AUTH_ID, method=CONFIRM_METHOD,
        baseline_audit=first["baseline_audit"], confirmation_source=first["id"], metadata_result=metadata_result,
        page_size=PAGE_SIZE, budget=accounting(records(engine, "newsapi_id_intent"), receipts),
        reverse_reported_tokens=sum(r["billed_tokens"] for r in reverse if r.get("billed_tokens") is not None),
        baseline_used=initial, latest_used=latest,
        observed_account_delta=latest-initial if initial is not None and latest is not None else None,
        receipt_ids=[r["id"] for r in receipts], reverse_receipt_ids=[r["id"] for r in reverse],
        model_calls=0, generated_at=utc(), limitation=LIMITATION)
    return result, frames


def evidence_zip(engine: Research, session: str, context: Context, baseline: Json,
                 first: Json, result: Json, frames: dict[str, Json], *,
                 extra_json: dict[str, Json] | None = None, method: str = CONFIRM_METHOD) -> str:
    """Freeze exact allowed evidence; original article text is referenced, never copied."""
    files: dict[str, bytes] = {}
    def json_file(name: str, value: object) -> None:
        files[name] = canonical(value).encode("utf-8")

    for name, value in (extra_json or {}).items():
        if "/" in name or "\\" in name or not name.endswith(".json") or name in {"comparison.json", "file-sha256.json"}:
            raise ResearchError("Extra proof document must have a distinct safe JSON basename")
        json_file(name, value)

    json_file("comparison.json", result)
    json_file("baseline-audit.json", baseline)
    json_file("ascending-result.json", first)
    files["baseline-identity-manifest.json"] = engine.ledger.artifacts.read_bytes(baseline["identity_manifest"])
    for year in sorted({f["year"] for f in frames.values()}):
        grouped = [f for f in frames.values() if f["year"] == year]
        for direction in ("saved", "ascending", "reverse"):
            ids = set().union(*(f[direction] for f in grouped))
            files[f"years/{year}/{direction}-ids.txt"] = ("\n".join(sorted(ids))+"\n").encode("utf-8")
    for start, frame in frames.items():
        for direction in ("saved", "ascending", "reverse"):
            files[f"partitions/{start}/{direction}-ids.txt"] = ("\n".join(sorted(frame[direction]))+"\n").encode("utf-8")
    references: list[Json] = []
    historical_versions = {(kind, ref) for kind, ref in context.versions.items()}
    historical_versions.update(first.get("versions", {}).items())
    historical_versions.update(baseline.get("versions", {}).items())
    sessions = {session}
    def record_reference(identifier: str) -> Json:
        row = engine.ledger.db.execute("SELECT r.id,r.kind,r.artifact,r.created_event,e.session_id FROM records r JOIN events e ON e.seq=r.created_event WHERE r.id=?", (identifier,)).fetchone()
        if row is None:
            raise ResearchError("Evidence source record is unavailable")
        item = dict(row)
        sessions.add(item["session_id"])
        references.append(item)
        return item

    for identifier in [first["id"], first["baseline_audit"], *context.versions.values()]:
        record_reference(identifier)
    if result.get("metadata_result"):
        identifier = result["metadata_result"]
        ref = record_reference(identifier)
        files["differing-id-metadata-result.json"] = engine.ledger.artifacts.read_bytes(ref["artifact"])
        historical_versions.update(json.loads(files["differing-id-metadata-result.json"]).get("versions", {}).items())
    original_receipt_ids = list(dict.fromkeys(ref for p in baseline["periods"] for ref in p.get("receipt_ids", [d["receipt"] for d in p["page_details"]])))
    query = "SELECT id,artifact,json_extract(payload,'$.parameters') AS parameters_json,json_extract(payload,'$.raw_response') AS raw_response_artifact,json_extract(payload,'$.raw_sha256') AS original_response_sha256 FROM records WHERE kind='newsapi_collection_receipt' AND id=?"
    originals = []
    for identifier in original_receipt_ids:
        item = engine.ledger.db.execute(query, (identifier,)).fetchone()
        if item is None:
            raise ResearchError("Original collection receipt reference is unavailable")
        originals.append(dict(item))
        record_reference(identifier)
    json_file("original-collection-references.json", {"sql": query, "records": originals,
        "retention": "References/hashes and exact retrieval parameters only; publisher texts and original full-article payloads are not duplicated"})
    missing_raw = []
    for receipt in records(engine, "newsapi_id_receipt"):
        historical_versions.update(receipt.get("versions", {}).items())
        record_reference(receipt["id"])
        json_file(f"receipts/{receipt['id']}.json", receipt)
        if receipt.get("raw_response"):
            files[f"responses/{receipt['id']}.json"] = engine.ledger.artifacts.read_bytes(receipt["raw_response"])
        else:
            missing_raw.append(receipt["id"])
    for intent in records(engine, "newsapi_id_intent"):
        historical_versions.update(intent.get("versions", {}).items())
        record_reference(intent["id"])
        json_file(f"intents/{intent['id']}.json", intent)
    for kind, identifier in context.versions.items():
        json_file(f"versions/{kind}.json", {"id": identifier, **engine.ledger.get(identifier, kind)})
    for kind, identifier in sorted(historical_versions):
        record_reference(identifier)
        json_file(f"versions/history/{kind}/{identifier}.json", {"id": identifier, **engine.ledger.get(identifier, kind)})
    json_file("record-references.json", references)
    provenance = []
    for identifier in sorted(sessions):
        row = engine.ledger.db.execute("SELECT * FROM events WHERE session_id=? AND kind='session.started' ORDER BY seq LIMIT 1", (identifier,)).fetchone()
        if row is None:
            raise ResearchError("Source session/code identity is unavailable")
        event = dict(row)
        payload = json.loads(event["payload"])
        reference = payload["identity"]
        files[f"code-identities/{reference}.json"] = engine.ledger.artifacts.read_bytes(reference)
        provenance.append({"session_started_event": event, "identity_artifact": reference})
    json_file("session-provenance.json", provenance)
    json_file("evidence-manifest.json", {"method": method, "authorization_id": AUTH_ID,
        "versions": context.versions, "baseline_audit": first["baseline_audit"], "ascending_result": first["id"],
        "metadata_result": result.get("metadata_result"), "comparison": "comparison.json",
        "missing_raw_response_receipts": missing_raw, "limitation": LIMITATION,
        "outer_zip_sha256": "Stored as the protected artifact reference and in the immutable proof result; excluded here to avoid a self-referential hash"})
    json_file("file-sha256.json", {"files": {name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        for name, raw in sorted(files.items())}, "self_exclusion": "This checksum file excludes itself"})
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    reference = engine.ledger.artifacts.put_bytes(buffer.getvalue())
    engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": reference, "method": method,
        "files": len(files), "baseline_audit": first["baseline_audit"], "ascending_result": first["id"]})
    return reference


def verify_proof_bytes(raw: bytes) -> Json:
    """Recompute checksums and ID comparisons from the packaged evidence itself."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            checksums = json.loads(archive.read("file-sha256.json"))["files"]
            if set(checksums) != set(archive.namelist()) - {"file-sha256.json"}:
                raise AuditError("Proof package file inventory differs from checksums")
            for name, expected in checksums.items():
                content = archive.read(name)
                if len(content) != expected["bytes"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
                    raise AuditError("Proof package file checksum mismatch")
            raw_count = 0
            for name in checksums:
                if not name.startswith("receipts/"):
                    continue
                receipt = json.loads(archive.read(name))
                if receipt.get("raw_response"):
                    response = archive.read(f"responses/{receipt['id']}.json")
                    if hashlib.sha256(response).hexdigest() != receipt["raw_sha256"]:
                        raise AuditError("Packaged raw response differs from its original receipt hash")
                    raw_count += 1
                    if receipt.get("manifest_status") == "valid":
                        ids, total = parse_manifest(json.loads(response))
                        if ids != receipt["normalized_ids"] or total != receipt["provider_total"]:
                            raise AuditError("Raw manifest differs from retained normalized IDs")
            comparison = json.loads(archive.read("comparison.json"))
            quarter_count = 0
            if "quarter-verification.json" in checksums:
                from .newsapi_id_manifest_quarter_proof import WINDOWS
                windows = json.loads(archive.read("quarter-verification.json"))["windows"]
                validation_policy = json.loads(archive.read("versions/policy.json"))["content"]
                allow_recent = validation_policy.get("recent_window_validation") == RECENT_WINDOW_METHOD
                if [(w["date_start"], w["date_end"]) for w in windows] != WINDOWS:
                    raise AuditError("Quarter proof does not contain the registered disjoint date ranges")
                for window in windows:
                    for direction in ("ascending", "reverse"):
                        item = window[direction]
                        if not item["complete"]:
                            continue
                        source = json.loads(archive.read(f"receipts/{item['receipt']}.json"))
                        expected = {**request(window["date_start"], window["date_end"], 1, 5000),
                            "uriWgtListSortByAsc": direction == "ascending"}
                        actual_ids, total = parse_manifest(json.loads(archive.read(f"responses/{item['receipt']}.json")))
                        if (canonical(source["parameters"]) != canonical(expected) or source.get("http_status") != 200
                                or not archive_or_recent(source, allow_recent) or not 0 <= total <= 5000
                                or len(actual_ids) != total or len(set(actual_ids)) != total
                                or sorted(actual_ids) != item["ids"] or total != item["provider_total"]):
                            raise AuditError("Quarter ID list does not reproduce its raw response and registered request")
                    enumerated = window["ascending"]["complete"] and window["reverse"]["complete"]
                    equal = window["ascending"]["ids"] == window["reverse"]["ids"] if enumerated else None
                    if (window["enumerated"] != enumerated or window["ascending_reverse_equal"] != equal
                            or bool(window["complete"]) != bool(enumerated and equal)):
                        raise AuditError("Quarter-pair comparison is not reproduced by its packaged ID lists")
                quarter_count = len(windows)
            for row in comparison["years"]:
                def year_ids(direction: str) -> set[str]:
                    return set(archive.read(f"years/{row['year']}/{direction}-ids.txt").decode().splitlines())
                saved_ids, ascending_ids, reverse_ids = year_ids("saved"), year_ids("ascending"), year_ids("reverse")
                if (len(saved_ids) != row["saved_ids"] or len(reverse_ids) != row["reverse_ids"]
                        or sorted(reverse_ids-saved_ids) != row["manifest_only_ids"]
                        or (row["saved_only_ids"] is not None and sorted(saved_ids-reverse_ids) != row["saved_only_ids"])
                        or (row["ascending_reverse_equal"] is not None and (row["complete"] or row["ascending_reverse_equal"])
                            and (ascending_ids == reverse_ids) != row["ascending_reverse_equal"])):
                    raise AuditError("Packaged year IDs do not reproduce the reported set comparison")
    except (KeyError, ValueError, zipfile.BadZipFile, ResearchError) as error:
        raise AuditError("Proof package could not be independently replayed") from error
    return {"status": "verified", "files_checked": len(checksums), "raw_responses_checked": raw_count,
        "years_checked": len(comparison["years"]), "complete_year_comparisons": sum(bool(r["complete"]) for r in comparison["years"]),
        "quarter_pairs_checked": quarter_count,
        "outer_sha256": hashlib.sha256(raw).hexdigest(),
        "scope": "Byte integrity, raw-to-normalized IDs and available set-comparison replay; null absence remains unsettled, no independent provider attestation"}


def export_proof(engine: Research, session: str, reference: str, filename: str = "id-manifest-proof.zip") -> str:
    """Write the same anchored bytes to one fixed, protected, user-readable path."""
    raw = engine.ledger.artifacts.read_bytes(reference)
    if filename not in {"id-manifest-proof.zip", "id-manifest-quarter-proof.zip", "id-manifest-quarter-proof-initial.zip"}:
        raise ResearchError("Use a fixed registered proof filename in protected storage")
    target = engine.ledger.root / filename
    if target.is_symlink() or target.is_junction():
        raise AuditError("Protected proof export cannot follow a link")
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == reference:
        engine.ledger.append(session, "newsapi.id_manifest.proof.export.verified", {"artifact": reference, "path": str(target)})
        return str(target)
    engine.ledger.append(session, "export.write_intended", {"artifact": reference, "path": str(target), "method": CONFIRM_METHOD})
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=engine.ledger.root, prefix="id-proof-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != reference:
            raise AuditError("Protected proof export does not match its anchored artifact")
    except OSError as error:
        raise AuditError("Required protected proof export failed") from error
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    engine.ledger.append(session, "newsapi.id_manifest.proof.export.saved", {"artifact": reference, "path": str(target), "bytes": len(raw)})
    return str(target)


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile", "policy"})
    policy = engine.ledger.get(context.versions["policy"], "policy")["content"]
    if (policy.get("method") != METHOD or policy.get("confirmation_method") != CONFIRM_METHOD
            or policy.get("authorization_id") != AUTH_ID or policy.get("max_tokens") != CAP):
        raise ResearchError("Explicit reverse-manifest confirmation under the original 583-token authorization required")
    first, first_receipts = _first_pass(engine, policy, context)
    baseline, identities = load_baseline(engine, first["baseline_audit"])
    periods = [[p["date_start"], p["date_end"]] for p in baseline["periods"]]
    if (policy.get("periods") != periods or policy.get("confirmation_templates") != [reverse_request(p[0], p[1], 1) for p in periods]):
        raise ResearchError("Register exactly the saved date partitions and unchanged reverse query templates")
    for prior in reversed(records(engine, "newsapi_id_manifest_proof")):
        if prior.get("versions") == context.versions and prior.get("complete") and prior.get("confirmation_source") == first["id"]:
            path = export_proof(engine, session, prior["proof_artifact"])
            engine.ledger.append(session, "newsapi.id_manifest.proof.reused", {"result": prior["id"], "versions": context.versions,
                "reason": "Explicit exact-version reuse; no new provider request", "artifact": prior["proof_artifact"]})
            return {**prior, "proof_path": path, "reused": True, "new_api_calls": 0}
    limit = data.get("requests", 16)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 16:
        raise ResearchError("Use 1 through16 reverse searches per checkpoint")
    state, _ = _state(engine, baseline, identities, first, first_receipts, context, policy.get("metadata_result"))
    stop, calls = "checkpoint", 0
    if not state["complete"]:
        if engine.config.offline or data.get("execute") is not True or not os.environ.get("EVENTREGISTRY_API_KEY"):
            raise ResearchError("Explicit live reverse-manifest execution and a credential are required")
        unknown = engine.ledger.db.execute("SELECT COUNT(*) FROM records i WHERE i.kind='newsapi_collection_intent' AND NOT EXISTS (SELECT 1 FROM records r WHERE r.kind='newsapi_collection_receipt' AND json_extract(r.payload,'$.attempt')=json_extract(i.payload,'$.attempt'))").fetchone()[0]
        if unknown:
            raise ResearchError("An unresolved original collection dispatch blocks new provider calls")
        try:
            before = dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_before_reverse_confirmation")
            calls += 1
        except ResearchError as error:
            if not str(error).startswith("ID-manifest authorization budget"):
                raise
            before, stop = {}, "budget_limit"
        usage_ok = before.get("outcome") == "received" and before.get("http_status") == 200 and number(before.get("response", {}).get("usedTokens")) is not None
        if not usage_ok and stop != "budget_limit":
            stop = "account_usage_unavailable"
        for _ in range(limit if usage_ok else 0):
            state, _ = _state(engine, baseline, identities, first, first_receipts, context, policy.get("metadata_result"))
            if state["budget"]["unresolved_outcomes"] or state["budget"]["reservation_exceeded_attempts"]:
                stop = "unknown_or_excessive_charge"
                break
            if any(p["positive_total_drift"] or p["duplicate_id_occurrences"] for p in state["periods"]):
                stop = "inconsistent_reverse_manifest"
                break
            pending = [p for p in state["periods"] if not p["complete"]]
            if not pending:
                stop = "reverse_manifest_complete"
                break
            period = min(pending, key=lambda p: (p["pages"], p["date_start"]))
            page = min(period["pending_pages"]) if period["pending_pages"] else period["pages"]+1
            try:
                receipt = dispatch(engine, session, context, reverse_request(period["date_start"], period["date_end"], page), "manifest_confirmation")
                calls += 1
            except ResearchError as error:
                if str(error).startswith(("ID-manifest authorization budget", "Account allowance")):
                    stop = "budget_limit"
                    break
                if str(error).startswith("No duplicate valid-page dispatch"):
                    stop = "invalid_reverse_response"
                    break
                raise
            print(json.dumps({"reverse_start": period["date_start"], "page": page,
                "ids": len(receipt.get("normalized_ids", [])), "status": receipt.get("manifest_status", receipt["outcome"]),
                "billed_tokens": receipt.get("billed_tokens")}), flush=True)
            if receipt.get("outcome") == "unknown" or receipt.get("manifest_status") != "valid":
                stop = "unknown_outcome" if receipt.get("outcome") == "unknown" else "invalid_reverse_response"
                break
            time.sleep(0.6)
        if usage_ok:
            try:
                dispatch(engine, session, context, {"endpointVariant": "usage"}, "usage_after_reverse_confirmation")
                calls += 1
            except ResearchError as error:
                if not str(error).startswith("ID-manifest authorization budget"):
                    raise
    result, frames = _state(engine, baseline, identities, first, first_receipts, context, policy.get("metadata_result"))
    result.update(stop_reason="reverse_manifest_complete" if result["complete"] else stop, new_api_calls=calls, reused=False)
    if result["complete"]:
        reference = evidence_zip(engine, session, context, baseline, first, result, frames)
        verified = verify_proof_bytes(engine.ledger.artifacts.read_bytes(reference))
        path = export_proof(engine, session, reference)
        result.update(proof_artifact=reference, evidence_zip=reference, proof_path=path, proof_self_check=verified)
    else:
        result.update(proof_artifact=None, evidence_zip=None, proof_path=None)
    identifier = engine.ledger.record(session, "newsapi_id_manifest_proof", str(uuid.uuid4()), result)
    return {"id": identifier, **result}
