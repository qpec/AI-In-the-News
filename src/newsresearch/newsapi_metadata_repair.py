"""Versioned offline collection rebuild with lossless event metadata and replay."""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any
import uuid
import zipfile

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .legacy import EVENT_URI_STATES, event_uri_state
from .newsapi_event_diagnosis import raw_matches
from .newsapi_id_manifest_archive_repair import budget
from .newsapi_metadata import project_article_metadata

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "nl-cyber-event-metadata-repair-v2"
MARKER = "event-metadata-repair.json"


def article_items(receipt: Json) -> list[tuple[list[Any], Json]]:
    response = receipt.get("response")
    if receipt.get("http_status") != 200 or not isinstance(response, dict):
        return []
    section = response.get("articles")
    if isinstance(section, dict) and isinstance(section.get("results"), list):
        return [(["articles", "results", i], a) for i, a in enumerate(section["results"])
                if isinstance(a, dict) and isinstance(a.get("uri"), str)]
    return [([uri, "info"], value["info"]) for uri, value in response.items()
            if isinstance(value, dict) and isinstance(value.get("info"), dict)
            and value["info"].get("uri") == uri]


def observe(article: Json, receipt: Json, path: list[Any], sequence: int, kind: str) -> Json:
    return {"article_uri": article["uri"], "receipt": receipt["id"], "receipt_kind": kind,
        "path": path, "record_hash": digest(article), "created_event": sequence,
        "retrieved_at": receipt["completed_at"], "field_present": "eventUri" in article,
        "event_value": article.get("eventUri"), "state": event_uri_state(article)}


def choose(history: list[Json]) -> Json:
    available = [row for row in history if row["field_present"]]
    if not available:
        return history[0]
    newest = max(row["created_event"] for row in available)
    tied = [row for row in available if row["created_event"] == newest]
    if len({canonical([row["state"], row["event_value"]]) for row in tied}) != 1:
        raise ResearchError("Conflicting event metadata within one receipt; no arbitrary assignment")
    return min(tied, key=lambda row: canonical(row["path"]))


def repair_article(article: Json, base: Json, additional: list[Json]) -> Json:
    if article["uri"] != base["article_uri"] or digest(article) != base["record_hash"]:
        raise ResearchError("Base article differs from its source locator/hash")
    observations = {canonical([base["receipt"], base["path"]]): base}
    for row in additional:
        if row["article_uri"] != article["uri"]:
            raise ResearchError("Metadata belongs to another article")
        key = canonical([row["receipt"], row["path"]])
        if key in observations and observations[key] != row:
            raise ResearchError("One source locator has inconsistent observations")
        observations[key] = row
    history = sorted(observations.values(), key=lambda row: (row["created_event"], canonical(row["path"])))
    selected = choose(history)
    updated = dict(article)
    if selected["field_present"]:
        updated["eventUri"] = selected["event_value"]
    else:
        updated.pop("eventUri", None)
    return {"article": updated, "source_hash": digest(updated), "base_observation": base,
        "event_metadata": {"method": METHOD, "projection_version": 2, "selected_observation": selected,
            "state": event_uri_state(updated), "observations": history,
            "observed_event_ids": sorted({row["event_value"] for row in history if row["state"] == "populated"})},
        "retention": "metadata_only_quarantine" if article.get("quarantined") else "permitted_private",
        "representation": "Derived article version; only eventUri may differ from the base record"}


def summarize_collection(rows: list[Json]) -> Json:
    counts = Counter(event_uri_state(row["article"]) for row in rows)
    changes: Counter[str] = Counter()
    for row in rows:
        base, selected = row["base_observation"], row["event_metadata"]["selected_observation"]
        if (base["field_present"], base["event_value"]) != (selected["field_present"], selected["event_value"]):
            changes[base["state"] + "_to_" + selected["state"]] += 1
    return {"articles": len(rows), "event_states": {state: counts[state] for state in EVENT_URI_STATES},
        "populated_percent": 100 * counts["populated"] / len(rows) if rows else None,
        "changed_event_fields": dict(changes),
        "articles_with_any_saved_event_id": sum(bool(row["event_metadata"]["observed_event_ids"]) for row in rows),
        "distinct_selected_event_ids": len({row["article"]["eventUri"] for row in rows if event_uri_state(row["article"]) == "populated"}),
        "missing_body": sum(not isinstance(row["article"].get("body"), str) or not row["article"]["body"].strip() for row in rows),
        "quarantined_records": sum(row["article"].get("quarantined") is True for row in rows)}


def pack(files: dict[str, bytes]) -> bytes:
    if "file-sha256.json" in files:
        raise ResearchError("Checksum inventory is generated by the packer")
    files = {**files, "file-sha256.json": canonical({"files": {
        name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)} for name, raw in sorted(files.items())}}).encode()}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
    return output.getvalue()


def unpack(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise AuditError("Duplicate archive members")
        files = {name: archive.read(name) for name in names}
    checks = json.loads(files.pop("file-sha256.json"))["files"]
    if set(checks) != set(files) or any(len(content) != checks[name]["bytes"] or
            hashlib.sha256(content).hexdigest() != checks[name]["sha256"] for name, content in files.items()):
        raise AuditError("Archive checksum inventory mismatch")
    return files


def parent_sources(raw: bytes) -> tuple[dict[str, Json], dict[str, int]]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if MARKER in archive.namelist():
            raise AuditError("Repair requires the original retrieval proof, not recursive repair nesting")
        refs = {r["id"]: r["created_event"] for r in json.loads(archive.read("record-references.json"))}
        receipts = {r["id"]: r for name in archive.namelist() if name.startswith("receipts/")
            for r in [json.loads(archive.read(name))]}
        for receipt in receipts.values():
            if not article_items(receipt):
                continue
            raw_response = archive.read(f"responses/{receipt['id']}.json")
            hashed = hashlib.sha256(raw_response).hexdigest()
            if (hashed != receipt.get("raw_response") or hashed != receipt.get("raw_sha256")
                    or canonical(json.loads(raw_response)) != canonical(receipt["response"])):
                raise AuditError("Packaged metadata differs from its retained raw response")
    return receipts, refs


def validate_frame(parent: bytes, coverage: Json, manifest: Json) -> None:
    with zipfile.ZipFile(io.BytesIO(parent)) as archive:
        baseline = json.loads(archive.read("baseline-identity-manifest.json"))
        comparison = json.loads(archive.read("comparison.json"))
    originals = {row["uri"]: row for partition in baseline.values() for row in partition["identifiers"]}
    enumeration = comparison["minimal_recovery_summary"]["enumeration"]
    added = set(enumeration["observed_added_ids"])
    if (manifest["fresh_receipt_ids"] != enumeration["receipt_ids"] or set(manifest["added_ids"]) != added
            or set(originals) & added or {row["article_uri"] for row in coverage["rows"]} != set(originals) | added):
        raise AuditError("Repair frame differs from the parent retrieval proof")
    for row in coverage["rows"]:
        original = originals.get(row["article_uri"])
        if original is not None:
            if row["origin"] != "original_saved" or any(row[key] != original[key] for key in ("receipt", "index", "record_hash")):
                raise AuditError("Coverage locator differs from the baseline identity manifest")
        elif row["origin"] != "fresh_minimal_metadata" or row["receipt"] not in enumeration["receipt_ids"]:
            raise AuditError("Supplement locator differs from the verified metadata recovery")


def metadata_observations(receipts: dict[str, Json], refs: dict[str, int], ids: set[str]) -> dict[str, list[Json]]:
    result: dict[str, list[Json]] = defaultdict(list)
    for receipt in receipts.values():
        for path, article in article_items(receipt):
            if article["uri"] not in ids:
                continue
            project_article_metadata(article)  # Enforce metadata-only source contract.
            if not receipt.get("raw_response") or receipt.get("outcome") != "received":
                raise AuditError("Metadata recovery requires a retained successful raw response")
            result[article["uri"]].append(observe(article, receipt, path, refs[receipt["id"]], "newsapi_id_receipt"))
    return result


def verify_repaired_proof(raw: bytes) -> Json:
    from .newsapi_id_manifest_proof import verify_proof_bytes
    files = unpack(raw)
    manifest = json.loads(files[MARKER])
    source_coverage = json.loads(files["source-coverage.json"])
    source_diagnosis = json.loads(files["source-diagnosis.json"])
    if (manifest.get("method") != METHOD or manifest.get("projection_version") != 2
            or source_coverage["proof_artifact"] != manifest["coverage_proof_sha256"]
            or source_coverage["recovery_id"] != manifest["recovery_id"]
            or source_diagnosis["coverage_id"] != manifest["coverage_id"]):
        raise AuditError("Repair method or immutable source relationships differ")
    parent = files["retrieval-proof-before-event-repair.zip"]
    if hashlib.sha256(parent).hexdigest() != manifest["parent_proof_sha256"]:
        raise AuditError("Parent proof reference mismatch")
    receipts, refs = parent_sources(parent)
    parent_check = verify_proof_bytes(parent)
    coverage = json.loads(files["source-coverage-proof.json"])
    if hashlib.sha256(files["source-coverage-proof.json"]).hexdigest() != manifest["coverage_proof_sha256"]:
        raise AuditError("Coverage proof reference mismatch")
    validate_frame(parent, coverage, manifest)
    expected = {row["article_uri"]: row for row in coverage["rows"]}
    if len(expected) != len(coverage["rows"]):
        raise AuditError("Repeated base article IDs")
    additional = metadata_observations(receipts, refs, set(expected))
    collection = files["collection.zip"]
    if hashlib.sha256(collection).hexdigest() != manifest["collection_sha256"]:
        raise AuditError("Collection reference mismatch")
    contents = unpack(collection)
    collection_manifest = json.loads(contents["manifest.json"])
    rows = [json.loads(line) for name, content in sorted(contents.items()) if name.startswith("articles/")
            for line in content.decode("utf-8").split("\n") if line]
    if len(rows) != len(expected) or {row["article"]["uri"] for row in rows} != set(expected):
        raise AuditError("Repaired collection membership differs from the complete saved frame")
    for row in rows:
        article, base = row["article"], row["base_observation"]
        prior = expected[article["uri"]]
        if (base["record_hash"] != prior["record_hash"] or base["receipt"] != prior["receipt"]
                or base["path"] != ["articles", "results", prior["index"]]
                or base["created_event"] != refs[base["receipt"]]
                or base["receipt_kind"] != ("newsapi_collection_receipt" if prior["origin"] == "original_saved" else "newsapi_id_receipt")):
            raise AuditError("Base identity locator differs from the original coverage frame")
        original = dict(article)
        if base["field_present"]:
            original["eventUri"] = base["event_value"]
        else:
            original.pop("eventUri", None)
        if digest(original) != prior["record_hash"] or event_uri_state(original) != prior["state"]:
            raise AuditError("Original record cannot be reconstructed exactly")
        if article["date"][:4] != prior["year"]:
            raise AuditError("Repaired article year differs from its original coverage")
        if base["receipt"] in receipts:
            source = receipts[base["receipt"]]
            located = source["response"]["articles"]["results"][prior["index"]]
            source_base = observe(located, source, base["path"], refs[base["receipt"]], "newsapi_id_receipt")
            if canonical(source_base) != canonical(base):
                raise AuditError("Supplement base differs from its retained response")
        rebuilt = repair_article(original, base, additional.get(article["uri"], []))
        if canonical(row) != canonical(rebuilt):
            raise AuditError("Event metadata history/selection does not reproduce the source responses")
    summary = summarize_collection(rows)
    if canonical(summary) != canonical(manifest["summary"]) or canonical(summary) != canonical(collection_manifest["summary"]):
        raise AuditError("Repaired coverage summary does not reproduce the collection")
    years = []
    for year in sorted({row["article"]["date"][:4] for row in rows}):
        selected = [row for row in rows if row["article"]["date"].startswith(year)]
        years.append({"year": year, **summarize_collection(selected)})
        expected_bytes = ("\n".join(canonical(row) for row in selected) + "\n").encode()
        if contents.get(f"articles/articles-{year}.jsonl") != expected_bytes:
            raise AuditError("Article record stored under the wrong calendar year or order")
    if (canonical(years) != canonical(manifest["years"])
            or canonical(years) != canonical(collection_manifest["years"])
            or {name for name in contents if name.startswith("articles/")} != {f"articles/articles-{row['year']}.jsonl" for row in years}):
        raise AuditError("Per-year collection coverage does not reproduce its records")
    # Exact v2 projection replay, including explicit null versus missing key.
    fresh = []
    for ref in manifest["fresh_receipt_ids"]:
        for path, article in article_items(receipts[ref]):
            fresh.append({**project_article_metadata(article), "_metadata_source": observe(article, receipts[ref], path, refs[ref], "newsapi_id_receipt")})
    fresh.sort(key=lambda article: article["uri"])
    if canonical(fresh) != canonical(json.loads(contents["metadata/fresh-window-v2.json"])):
        raise AuditError("Corrected metadata projection lost or changed a provider field")
    recovered = [{**article, "article_body_status": "not_requested"} for article in fresh if article["uri"] in manifest["added_ids"]]
    if canonical(recovered) != canonical(json.loads(contents["metadata/recovered-articles-v2.json"])):
        raise AuditError("Recovered-article supplement differs from its raw source")
    return {"status": "verified", "articles_checked": len(rows), "years_checked": len(collection_manifest["years"]),
        "projection_records_checked": len(fresh), "source_history_replayed": True,
        "original_records_reconstructed": len(rows), "parent_retrieval_proof": parent_check,
        "summary": summary, "network_calls": 0, "scope": "Saved-response reconstruction and provenance; no external attestation or current provider census"}


def write_protected(engine: Research, session: str, name: str, raw: bytes) -> str:
    if name not in {"cybercrime-nl-collection-event-metadata-v2.zip", "cybercrime-nl-collection-latest.json",
                    "event-metadata-repair-audit.json", "id-manifest-minimal-recovered-articles-v2.json"}:
        raise ResearchError("Unregistered repaired artifact destination")
    target = engine.ledger.root / name
    if target.is_symlink() or target.is_junction():
        raise AuditError("Repaired artifacts cannot follow links")
    reference = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "export.write_intended", {"artifact": reference, "path": str(target), "method": METHOD})
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=engine.ledger.root, prefix="event-repair-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != reference:
            raise AuditError("Repaired export bytes differ from its saved artifact")
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    engine.ledger.append(session, "export.saved", {"artifact": reference, "path": str(target), "method": METHOD})
    return str(target)


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    from .newsapi_id_manifest_proof import export_proof, verify_proof_bytes
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile"})
    protocol = engine.ledger.get(context.versions["protocol"], "protocol")["content"]
    selection = engine.ledger.get(context.versions["selection"], "selection")["content"]["rules"]
    if protocol.get("method") != METHOD or selection.get("diagnosis_id") != data.get("diagnosis_id"):
        raise ResearchError("Register the exact offline metadata repair and source diagnosis")
    if data.get("reuse_result"):
        previous = engine.ledger.get(data["reuse_result"], "newsapi_metadata_repair")
        if previous["versions"] != context.versions or previous["diagnosis_id"] != data["diagnosis_id"]:
            raise ResearchError("Metadata repair reuse requires exact original versions and source diagnosis")
        return {"id": data["reuse_result"], **previous, "reused": True}
    diagnosis = engine.ledger.get(data["diagnosis_id"], "newsapi_event_diagnosis")
    coverage = engine.ledger.get(diagnosis["coverage_id"], "newsapi_event_coverage")
    coverage_raw = engine.ledger.artifacts.read_bytes(coverage["proof_artifact"])
    frame = json.loads(coverage_raw)
    recovery = engine.ledger.get(coverage["recovery_id"], "newsapi_id_manifest_minimal_recovery")
    parent = engine.ledger.artifacts.read_bytes(recovery["proof_artifact"])
    parent_check = verify_proof_bytes(parent)
    receipts, refs = parent_sources(parent)
    for receipt in receipts.values():
        if article_items(receipt) and not raw_matches(engine, receipt):
            raise ResearchError("Source metadata response has no verifiable raw bytes")
    additional = metadata_observations(receipts, refs, {row["article_uri"] for row in frame["rows"]})
    repaired: list[Json] = []
    current_ref, current_receipt = None, {}
    for row in sorted(frame["rows"], key=lambda item: (item["receipt"], item["index"])):
        ref = row["receipt"]
        kind = "newsapi_collection_receipt" if row["origin"] == "original_saved" else "newsapi_id_receipt"
        if ref != current_ref:
            current_receipt = {"id": ref, **engine.ledger.get(ref, kind)}
            raw_matches(engine, current_receipt)  # Missing original raw bytes stay explicit in previous audit.
            current_ref = ref
        article = current_receipt["response"]["articles"]["results"][row["index"]]
        base = observe(article, current_receipt, ["articles", "results", row["index"]], refs[ref], kind)
        if base["record_hash"] != row["record_hash"] or base["state"] != row["state"]:
            raise ResearchError("Original source changed since the saved event coverage check")
        repaired.append(repair_article(article, base, additional.get(article["uri"], [])))
    repaired.sort(key=lambda row: (row["article"]["date"], row["article"]["uri"]))
    summary = summarize_collection(repaired)
    years = []
    collection_files = {}
    for year in sorted({row["article"]["date"][:4] for row in repaired}):
        selected = [row for row in repaired if row["article"]["date"].startswith(year)]
        years.append({"year": year, **summarize_collection(selected)})
        collection_files[f"articles/articles-{year}.jsonl"] = ("\n".join(canonical(row) for row in selected) + "\n").encode()
    enumeration = recovery["minimal_recovery_summary"]["enumeration"]
    fresh = []
    for ref in enumeration["receipt_ids"]:
        for path, article in article_items(receipts[ref]):
            fresh.append({**project_article_metadata(article), "_metadata_source": observe(article, receipts[ref], path, refs[ref], "newsapi_id_receipt")})
    fresh.sort(key=lambda article: article["uri"])
    added = [{**article, "article_body_status": "not_requested"} for article in fresh if article["uri"] in enumeration["observed_added_ids"]]
    balance = budget(engine)
    manifest = {"method": METHOD, "versions": context.versions, "diagnosis_id": data["diagnosis_id"],
        "coverage_id": diagnosis["coverage_id"], "recovery_id": coverage["recovery_id"], "summary": summary, "years": years,
        "projection_version": 2, "latest_rule": "Latest saved receipt creation sequence with an explicit event field; null supersedes older assignment; absent fields do not erase known metadata; all observations retained",
        "updated_fields": ["eventUri"], "historical_sources_modified": False, "budget": balance,
        "network_calls": 0, "model_calls": 0, "newsapi_tokens": 0,
        "retention": "Protected private working collection including permitted article text; never Git/public export",
        "timestamp_replay_limit": "Original full-response receipt timestamps are retained from audited source records; the parent proof references those receipts but does not embed them. Later metadata receipt timestamps replay directly from the packaged receipts.",
        "frame": "All original saved IDs plus six recovered metadata records, retaining five saved-only historical IDs"}
    collection_files.update({"manifest.json": canonical(manifest).encode(),
        "metadata/fresh-window-v2.json": canonical(fresh).encode(),
        "metadata/recovered-articles-v2.json": canonical(added).encode()})
    collection = pack(collection_files)
    collection_ref = engine.ledger.artifacts.put_bytes(collection)
    engine.ledger.append(session, "newsapi.metadata_repair.collection.saved", {"artifact": collection_ref})
    proof_manifest = {**manifest, "parent_proof_sha256": recovery["proof_artifact"],
        "coverage_proof_sha256": coverage["proof_artifact"], "collection_sha256": collection_ref,
        "fresh_receipt_ids": enumeration["receipt_ids"], "added_ids": enumeration["observed_added_ids"]}
    proof_files = {MARKER: canonical(proof_manifest).encode(), "collection.zip": collection,
        "retrieval-proof-before-event-repair.zip": parent, "source-coverage-proof.json": coverage_raw,
        "source-diagnosis.json": canonical(diagnosis).encode(), "source-coverage.json": canonical(coverage).encode()}
    for kind, ref in context.versions.items():
        proof_files[f"versions/{kind}.json"] = canonical({"id": ref, **engine.ledger.get(ref, kind)}).encode()
    proof_files["repair-code-identity.json"] = canonical(engine.identity()).encode()
    proof = pack(proof_files)
    proof_ref = engine.ledger.artifacts.put_bytes(proof)
    engine.ledger.append(session, "newsapi.metadata_repair.proof.saved", {"artifact": proof_ref})
    verified = verify_repaired_proof(proof)
    if canonical(budget(engine)) != canonical(balance):
        raise ResearchError("Offline repair unexpectedly changed API accounting")
    collection_path = write_protected(engine, session, "cybercrime-nl-collection-event-metadata-v2.zip", collection)
    supplement_path = write_protected(engine, session, "id-manifest-minimal-recovered-articles-v2.json", canonical(added).encode())
    old_proof_path = export_proof(engine, session, recovery["proof_artifact"], "id-manifest-final-proof-before-event-metadata-repair.zip")
    proof_path = export_proof(engine, session, proof_ref, "id-manifest-final-proof.zip")
    result = {**manifest, "collection_artifact": collection_ref, "collection_path": collection_path,
        "proof_artifact": proof_ref, "proof_path": proof_path, "previous_proof_path": old_proof_path,
        "supplement_path": supplement_path, "proof_self_check": verified, "parent_self_check": parent_check,
        "restored_projection_ids": sum(event_uri_state(article) == "populated" for article in fresh),
        "fresh_projection_records": len(fresh), "failed": 0, "pending": 0, "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_metadata_repair", str(uuid.uuid4()), result)
    write_protected(engine, session, "event-metadata-repair-audit.json", canonical({"id": identifier, **result}).encode())
    write_protected(engine, session, "cybercrime-nl-collection-latest.json", canonical({"result_id": identifier,
        "method": METHOD, "collection_path": collection_path, "collection_artifact": collection_ref,
        "proof_path": proof_path, "proof_artifact": proof_ref, "summary": summary}).encode())
    return {"id": identifier, **result}
