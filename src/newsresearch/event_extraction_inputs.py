"""Content-anchored body-fold inputs for the existing bounded child workspace.

The caller preregisters this bounded extension before invoking load_frame.
No source text, labels or vector artifact is read here. Parent journal history
is retained but is not reverified by this deliberately narrow input extension.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any

from .common import AuditError, Json, digest, require_active, require_no_credentials, utc
from .storage import check_permissions

METHOD = "event-extraction-anchored-body-fold-input-v1"
RETAINED_CANDIDATE = "c5627181294c9d267561b1d75e9adb8f17c041343ec3d73573a055d215b5e8d2"
SQL = "SELECT id,kind,logical_key,artifact,payload,supersedes,created_event FROM records WHERE id=?"


def verified_record(row: Json, identifier: str, kind: str) -> Json:
    """Hash original SQL payload bytes; numeric JSON keys are not reserialized."""
    if (row.get("id") != identifier or row.get("kind") != kind
            or not isinstance(row.get("payload"), str)):
        raise AuditError("event_extraction_input_record_anchor_mismatch")
    reference = hashlib.sha256(row["payload"].encode("utf-8")).hexdigest()
    if (reference != row.get("artifact") or digest({"kind": kind, "key": row.get("logical_key"),
            "payload": reference, "supersedes": row.get("supersedes")}) != identifier):
        raise AuditError("event_extraction_input_record_content_changed")
    try:
        value = json.loads(row["payload"])
    except (ValueError, TypeError) as error:
        raise AuditError("event_extraction_input_record_json_invalid") from error
    if not isinstance(value, dict):
        raise AuditError("event_extraction_input_record_json_invalid")
    return value


def _checked_path(path: Path, *, root: bool = False) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction() or (part / ".git").exists():
            raise AuditError("event_extraction_input_external_path_unprotected")
    check_permissions(path, root=root)


def _read_artifact(parent: Path, reference: str) -> tuple[Any, bytes]:
    if not isinstance(reference, str) or not re.fullmatch(r"[0-9a-f]{64}", reference):
        raise AuditError("event_extraction_input_artifact_reference_invalid")
    path = parent / "objects" / reference
    _checked_path(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise AuditError("event_extraction_input_artifact_unavailable") from error
    if hashlib.sha256(raw).hexdigest() != reference:
        raise AuditError("event_extraction_input_artifact_changed")
    try:
        return json.loads(raw), raw
    except (ValueError, UnicodeError) as error:
        raise AuditError("event_extraction_input_artifact_json_invalid") from error


def _check_frame(current: Json, pair: Json, metadata: Any, frame: Any, original: Json) -> None:
    dataset = original["versions"]["dataset"]
    if (current.get("versions", {}).get("dataset") != dataset
            or pair.get("versions", {}).get("dataset") != dataset
            or current.get("rule", {}).get("publication_gap_days") != 7):
        raise AuditError("event_extraction_input_dataset_or_group_binding_changed")
    if (not isinstance(metadata, dict) or not set(original["membership"]) <= set(metadata)
            or not isinstance(frame, dict) or not isinstance(frame.get("representatives"), list)):
        raise AuditError("event_extraction_input_metadata_or_body_fold_missing")
    seen = set()
    for row in frame["representatives"]:
        if (not isinstance(row, dict) or not isinstance(row.get("body_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["body_sha256"])
                or row["body_sha256"] in seen or row.get("fold") not in {"development", "validation"}):
            raise AuditError("event_extraction_input_body_fold_invalid")
        seen.add(row["body_sha256"])
    if any(not isinstance(metadata[source], dict) or metadata[source].get("body_sha256") not in seen
           for source in original["membership"]):
        raise AuditError("event_extraction_input_body_fold_incomplete")


def load_frame(engine: Any, session: str, original_plan: Json) -> Json:
    """Read existing child inputs, or import exactly one anchored parent plan."""
    require_active(engine, session)
    ledger = engine.ledger
    group_id = original_plan["group_result"]
    local = ledger.db.execute("SELECT id FROM records WHERE id=? AND kind='event_group_refinement_result'",
                              (group_id,)).fetchone()
    if local is not None:
        current = ledger.get(group_id, "event_group_refinement_result")
        pair_id = current["plan"]
        if ledger.db.execute("SELECT id FROM records WHERE id=? AND kind='event_pair_plan'", (pair_id,)).fetchone():
            pair = ledger.get(pair_id, "event_pair_plan")
            metadata, frame = (ledger.artifacts.read(pair[key]) for key in ("metadata_artifact", "frame_artifact"))
            _check_frame(current, pair, metadata, frame, original_plan)
            provenance = {"method": METHOD, "mode": "existing_local_records", "group_result": group_id,
                          "pair_plan": pair_id, "external_parent_reads": 0, "label_artifacts_read": 0,
                          "vector_artifacts_read": 0}
            ledger.append(session, "event.extraction.input.local.inspected", provenance)
            return {"current": current, "pair_plan_id": pair_id, "metadata": metadata, "frame": frame,
                    "metadata_artifact": pair["metadata_artifact"], "frame_artifact": pair["frame_artifact"],
                    "provenance": provenance}

    candidate = ledger.get(RETAINED_CANDIDATE, "event_group_refinement_result")
    dataset = original_plan["versions"]["dataset"]
    if (candidate.get("method") != "fixed-margin-event-split-v1"
            or candidate.get("baseline_group_result") != group_id
            or candidate.get("versions", {}).get("dataset") != dataset):
        raise AuditError("event_extraction_input_candidate_anchor_changed")
    capsule = ledger.artifacts.read(candidate["capsule"])
    groups: dict[str, list[str]] = defaultdict(list)
    for source, group in original_plan["membership"].items():
        groups[group].append(source)
    groups = {group: sorted(members) for group, members in groups.items()}
    if (not isinstance(capsule.get("groups"), dict)
            or {group: sorted(members) for group, members in capsule["groups"].items()} != groups):
        raise AuditError("event_extraction_input_capsule_membership_changed")
    anchored_row = capsule.get("retained_anchor_records", {}).get(group_id)
    if not isinstance(anchored_row, dict):
        raise AuditError("event_extraction_input_retained_group_missing")
    current = verified_record(anchored_row, group_id, "event_group_refinement_result")
    if current.get("versions", {}).get("dataset") != dataset:
        raise AuditError("event_extraction_input_retained_dataset_changed")
    pair_id = current["plan"]
    owner_row = ledger.db.execute(
        "SELECT id FROM records WHERE kind='study_execution_ownership' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
        (original_plan["study_key"],)).fetchone()
    if owner_row is None:
        raise AuditError("event_extraction_input_original_owner_required")
    owner = ledger.get(owner_row[0], "study_execution_ownership")
    parent_value = owner.get("parent_provenance", {}).get("workspace")
    if (owner.get("status") != "imported_owner" or not isinstance(parent_value, str)
            or Path(owner.get("owner_workspace", "")).resolve() != ledger.root.resolve()
            or not isinstance(capsule.get("parent_workspace"), str)
            or not Path(parent_value).is_absolute() or not Path(capsule["parent_workspace"]).is_absolute()
            or Path(parent_value).absolute() != Path(capsule["parent_workspace"]).absolute()):
        raise AuditError("event_extraction_input_parent_ownership_changed")
    parent = Path(parent_value).absolute()
    binding = {"method": METHOD, "group_result": group_id, "pair_plan": pair_id, "dataset": dataset,
               "membership_hash": digest(original_plan["membership"]), "candidate": RETAINED_CANDIDATE,
               "capsule": candidate["capsule"], "owner_record": owner_row[0], "parent_workspace": str(parent),
               "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    key = digest({"group_result": group_id, "pair_plan": pair_id})
    prior = ledger.db.execute("SELECT id FROM records WHERE kind='event_extraction_input_import' AND logical_key=?",
                              (key,)).fetchall()
    if prior:
        if len(prior) != 1:
            raise AuditError("event_extraction_input_duplicate_import")
        saved = ledger.get(prior[0][0], "event_extraction_input_import")
        if saved["binding"] != binding:
            raise AuditError("event_extraction_input_cached_binding_changed")
        pair = verified_record(ledger.artifacts.read(saved["pair_record_artifact"]), pair_id, "event_pair_plan")
        metadata = ledger.artifacts.read(saved["metadata_artifact"])
        frame = ledger.artifacts.read(saved["frame_artifact"])
        _check_frame(current, pair, metadata, frame, original_plan)
        if any(saved[name] != pair[name] for name in ("metadata_artifact", "frame_artifact")):
            raise AuditError("event_extraction_input_cached_artifact_binding_changed")
        ledger.append(session, "event.extraction.input.cache.reused", {
            "input_import": prior[0][0], "binding": binding, "external_parent_reads": 0})
        return {"current": current, "pair_plan_id": pair_id, "metadata": metadata, "frame": frame,
                "metadata_artifact": saved["metadata_artifact"], "frame_artifact": saved["frame_artifact"],
                "provenance": {**saved["provenance"], "input_import": prior[0][0], "reused": True,
                               "external_parent_reads_this_operation": 0}}

    _checked_path(parent, root=True)
    _checked_path(parent / "objects")
    _checked_path(parent / "research.sqlite3")
    sidecars = []
    for suffix in ("-wal", "-shm"):
        sidecar = parent / ("research.sqlite3" + suffix)
        if sidecar.exists() or sidecar.is_symlink() or sidecar.is_junction():
            _checked_path(sidecar)
            sidecars.append(sidecar.name)
    ledger.append(session, "event.extraction.external_record.read.intended", {
        "binding": binding, "sql": SQL, "parameters": [pair_id], "present_sidecars_checked": sidecars,
        "mode": "SQLite mode=ro; exact anchored record only; parent journal not reverified"})
    connection = sqlite3.connect((parent / "research.sqlite3").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        row = connection.execute(SQL, (pair_id,)).fetchone()
        if row is None:
            raise AuditError("event_extraction_input_anchored_pair_plan_missing")
        pair_row = dict(row)
    finally:
        connection.close()
    pair = verified_record(pair_row, pair_id, "event_pair_plan")
    imported: dict[str, Any] = {}
    byte_count = 0
    for name in ("metadata_artifact", "frame_artifact"):
        reference = pair[name]
        ledger.append(session, "event.extraction.external_artifact.read.intended", {
            "binding": binding, "artifact": reference, "role": name, "anchor": pair_id})
        value, raw = _read_artifact(parent, reference)
        require_no_credentials(value)
        retained = ledger.artifacts.put_bytes(raw)
        if retained != reference:
            raise AuditError("event_extraction_input_copy_identity_changed")
        ledger.append(session, "preparation.artifact.saved", {
            "artifact": retained, "purpose": "Exact anchored body-fold or article-metadata bytes; no vectors or labels"})
        imported[name] = value
        byte_count += len(raw)
    _check_frame(current, pair, imported["metadata_artifact"], imported["frame_artifact"], original_plan)
    record_ref = ledger.artifacts.put(pair_row)
    ledger.append(session, "preparation.artifact.saved", {
        "artifact": record_ref, "purpose": "Exact original pair-plan SQL row including unchanged payload bytes"})
    provenance = {"method": METHOD, "mode": "bounded_content_anchored_parent_extension", "sql": SQL,
        "parameters": [pair_id], "parent_workspace": str(parent), "group_result": group_id, "pair_plan": pair_id,
        "parent_journal_reverified": False, "parent_head_inclusion_proof": False,
        "full_named_artifact_bytes_verified": byte_count, "parent_record_reads": 1,
        "parent_artifact_reads": 2, "label_artifacts_read": 0, "vector_artifacts_read": 0,
        "observed_at": utc(), "external_parent_reads_this_operation": 3}
    saved = {"binding": binding, "pair_record_artifact": record_ref,
             "metadata_artifact": pair["metadata_artifact"], "frame_artifact": pair["frame_artifact"],
             "provenance": provenance}
    identifier = ledger.record(session, "event_extraction_input_import", key, saved)
    return {"current": current, "pair_plan_id": pair_id, "metadata": imported["metadata_artifact"],
            "frame": imported["frame_artifact"], "metadata_artifact": pair["metadata_artifact"],
            "frame_artifact": pair["frame_artifact"], "provenance": {**provenance, "input_import": identifier, "reused": False}}
