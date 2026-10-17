"""Audited offline event-ID candidate search in the frozen saved collection."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .legacy import event_uri_state
from .newsapi_event_matching import METHOD, POLICY, analyze
from .newsapi_id_manifest_archive_repair import budget
from .newsapi_metadata_repair import pack, summarize_collection, unpack

if TYPE_CHECKING:
    from .runtime import Research


def load_rows(raw: bytes, expected: Json) -> list[Json]:
    files = unpack(raw)
    manifest = json.loads(files["manifest.json"])
    rows = [json.loads(line) for name, content in sorted(files.items()) if name.startswith("articles/")
            for line in content.decode("utf-8").split("\n") if line]
    if (len({row["article"]["uri"] for row in rows}) != len(rows)
            or any(digest(row["article"]) != row["source_hash"] for row in rows)
            or canonical(summarize_collection(rows)) != canonical(expected)
            or canonical(manifest["summary"]) != canonical(expected)):
        raise AuditError("Matching source differs from the frozen repaired collection")
    return rows


def validate_output(rows: list[Json], analysis: Json) -> None:
    targets = {row["article"]["uri"] for row in rows if event_uri_state(row["article"]) != "populated"}
    candidates = analysis["candidates"]
    if len(candidates) != len(targets) or {row["article_uri"] for row in candidates} != targets:
        raise AuditError("Candidate output does not preserve every unassigned article")
    originals = {row["article"]["uri"]: row for row in rows}
    for row in candidates:
        source = originals[row["article_uri"]]
        if row["source_hash"] != source["source_hash"] or row["original_event_state"] != event_uri_state(source["article"]):
            raise AuditError("Candidate output changes its original metadata identity")
        for candidate in row["candidates"]:
            if not candidate["anchors"]:
                raise AuditError("Candidate lacks a saved provider-assigned anchor")
            for link in candidate["anchors"]:
                anchor = originals.get(link["article_uri"])
                if (anchor is None or link["article_uri"] == row["article_uri"]
                        or event_uri_state(anchor["article"]) != "populated"
                        or anchor["article"]["eventUri"] != candidate["event_uri"]
                        or anchor["source_hash"] != link["source_hash"]):
                    raise AuditError("Candidate anchor differs from actual saved provider metadata")
                gap = abs((date.fromisoformat(source["article"]["date"]) - date.fromisoformat(anchor["article"]["date"])).days)
                if gap > POLICY["maximum_publication_gap_days"] or link["publication_gap_days"] != gap:
                    raise AuditError("Candidate crosses the registered publication interval")
    if any(digest(row["article"]) != row["source_hash"] for row in rows):
        raise AuditError("Candidate search mutated an original article")


def save_export(engine: Research, session: str, filename: str, raw: bytes) -> str:
    if filename not in {"cybercrime-nl-event-matches-v1.zip", "event-matching-proof-v1.zip", "event-matching-audit.json"}:
        raise ResearchError("Unsupported protected event-match export")
    target = engine.ledger.root / filename
    if target.is_symlink() or target.is_junction():
        raise AuditError("Event matching export cannot follow a link")
    reference = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "export.write_intended", {"method": METHOD, "path": str(target), "artifact": reference})
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=engine.ledger.root, prefix="event-matches-", suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != reference:
            raise AuditError("Event-match export hash mismatch")
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
    engine.ledger.append(session, "export.saved", {"method": METHOD, "path": str(target), "artifact": reference})
    return str(target)


def run(engine: Research, session: str, context: Context, data: Json) -> Json:
    from .newsapi_id_manifest_proof import verify_proof_bytes
    require_active(engine, session)
    engine._require(context, {"protocol", "question", "selection", "profile"})
    protocol = engine.ledger.get(context.versions["protocol"], "protocol")["content"]
    rules = engine.ledger.get(context.versions["selection"], "selection")["content"]["rules"]
    if (protocol.get("method") != METHOD or canonical(protocol.get("matching_policy")) != canonical(POLICY)
            or rules.get("repair_id") != data.get("repair_id") or not engine.config.offline):
        raise ResearchError("Register the exact offline matching policy and repaired source")
    if data.get("reuse_result"):
        previous = engine.ledger.get(data["reuse_result"], "newsapi_event_matching")
        if previous["versions"] != context.versions or previous["repair_id"] != data["repair_id"]:
            raise ResearchError("Match-result reuse requires exact original versions and source")
        return {"id": data["reuse_result"], **previous, "reused": True}
    source = engine.ledger.get(data["repair_id"], "newsapi_metadata_repair")
    before_budget = budget(engine)
    source_proof = engine.ledger.artifacts.read_bytes(source["proof_artifact"])
    proof_check = verify_proof_bytes(source_proof)
    source_raw = engine.ledger.artifacts.read_bytes(source["collection_artifact"])
    if hashlib.sha256(source_raw).hexdigest() != source["collection_artifact"]:
        raise AuditError("Collection bytes differ from the selected repair")
    rows = load_rows(source_raw, source["summary"])
    inspection = {"method": METHOD, "repair_id": data["repair_id"], "collection_artifact": source["collection_artifact"],
        "source_proof": source["proof_artifact"], "versions": context.versions, "policy": POLICY,
        "article_ids": [row["article"]["uri"] for row in rows],
        "fields": ["uri", "date", "title", "body", "url", "eventUri", "originalArticle", "duplicateList", "storyUri"],
        "use": "Deterministic metadata and lexical candidate search; no semantic model judging or membership adoption"}
    inspection_ref = engine.ledger.artifacts.put_bytes(canonical(inspection).encode())
    engine.ledger.append(session, "newsapi.event_matching.inspection.intended", {"artifact": inspection_ref})
    print(json.dumps({"stage": "matching", "articles": len(rows), "newsapi_tokens": 0}), flush=True)
    analysis = analyze(rows)
    validate_output(rows, analysis)
    analysis_ref = engine.ledger.artifacts.put_bytes(canonical(analysis).encode())
    engine.ledger.append(session, "newsapi.event_matching.analysis.saved", {"artifact": analysis_ref, "inspection": inspection_ref})
    print(json.dumps({"stage": "replaying_saved_inputs", "analysis_artifact": analysis_ref}), flush=True)
    # A second deterministic run checks reproduction, not independent scientific validity.
    replay = analyze(load_rows(source_raw, source["summary"]))
    if canonical(replay) != canonical(analysis):
        raise AuditError("Offline candidate search does not reproduce exactly")
    if canonical(before_budget) != canonical(budget(engine)):
        raise AuditError("Offline event matching changed NewsAPI accounting")
    manifest = {"method": METHOD, "versions": context.versions, "repair_id": data["repair_id"],
        "source_collection": source["collection_artifact"], "source_proof": source["proof_artifact"],
        "inspection_artifact": inspection_ref, "analysis_artifact": analysis_ref, "policy": POLICY,
        "summary": analysis["summary"], "years": analysis["years"], "field_inventory": analysis["field_inventory"],
        "heldout_summary": analysis["heldout"]["summary"], "examples": analysis["examples"],
        "heldout_diagnostics": {key: value for key, value in analysis["heldout"].items()
            if key not in {"per_item", "heldout_uris", "anchor_uris"}}, "retrieval_fit": analysis["fit"],
        "newsapi_tokens": 0, "network_calls": 0, "model_calls": 0, "budget": before_budget,
        "automatic_assignments": 0, "review_status": "unreviewed",
        "original_provider_fields_modified": False, "failed": 0, "pending_computation": 0,
        "limitations": ["These are provisional links to existing saved provider event IDs; no new event ID is invented.",
            "Absence of a matching saved anchor is not absence of an event.",
            "Fixed lexical thresholds are unvalidated; cosine scores are not probabilities.",
            "Masked known-ID agreement is a provider-metadata diagnostic, not independent human accuracy or accuracy on null-ID articles.",
            "Seven-day eligibility can miss later reporting; original collection completeness is separate from event matching."]}
    files = {"manifest.json": canonical(manifest).encode(),
        "candidates.jsonl": ("\n".join(canonical(row) for row in analysis["candidates"]) + "\n").encode(),
        "heldout.json": canonical(analysis["heldout"]).encode()}
    bundle = pack(files)
    bundle_ref = engine.ledger.artifacts.put_bytes(bundle)
    engine.ledger.append(session, "newsapi.event_matching.bundle.saved", {"artifact": bundle_ref})
    proof_files = {"manifest.json": canonical({**manifest, "bundle_artifact": bundle_ref,
        "replay": "Two executions from the same frozen collection produced byte-identical canonical results",
        "source_requirement": "Replay requires the protected source_collection artifact; source text is referenced, not embedded"}).encode(),
        "analysis.json": canonical(analysis).encode(), "matches.zip": bundle,
        "source-repair-result.json": canonical(source).encode(), "code-identity.json": canonical(engine.identity()).encode()}
    for name in ("newsapi_event_matching.py", "newsapi_event_matching_run.py"):
        proof_files[f"code/{name}"] = Path(__file__).with_name(name).read_bytes()
    for kind, ref in context.versions.items():
        proof_files[f"versions/{kind}.json"] = canonical({"id": ref, **engine.ledger.get(ref, kind)}).encode()
    proof = pack(proof_files)
    proof_ref = engine.ledger.artifacts.put_bytes(proof)
    engine.ledger.append(session, "newsapi.event_matching.proof.saved", {"artifact": proof_ref})
    if unpack(proof)["analysis.json"] != canonical(replay).encode() or unpack(bundle) != files:
        raise AuditError("Saved event-matching proof failed readback")
    bundle_path = save_export(engine, session, "cybercrime-nl-event-matches-v1.zip", bundle)
    proof_path = save_export(engine, session, "event-matching-proof-v1.zip", proof)
    result = {**manifest, "bundle_artifact": bundle_ref, "bundle_path": bundle_path,
        "proof_artifact": proof_ref, "proof_path": proof_path, "source_proof_check": proof_check,
        "deterministic_replay": "verified", "generated_at": utc()}
    identifier = engine.ledger.record(session, "newsapi_event_matching", str(uuid.uuid4()), result)
    save_export(engine, session, "event-matching-audit.json", canonical({"id": identifier, **result}).encode())
    return {"id": identifier, **result}
