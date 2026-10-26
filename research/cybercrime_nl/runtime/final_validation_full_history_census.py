"""Audited full metadata census inside an existing locked history inventory.

The original scoped reader intentionally omits unselected non-model events.
This separately registered extension preserves every event and record, including
manual-task envelopes and records declared out of scope. It does not classify
their purpose, traverse referenced artifacts, close discovery or authorize calls.
Exact rows are protected evidence; only counts/record identities may be printed.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

import final_validation_exposure as exposure
import final_validation_history_inventory as history_inventory
import final_validation_source as source_adapter
from newsresearch.common import AuditError, digest, require_active

METHOD = "final-validation-full-history-metadata-census-v1"
RESULT = "cyber_final_validation_full_history_metadata_census"
INTENT = "cyber_final_validation_full_history_metadata_intent"


def require(value, code):
    if not value:
        raise AuditError("full_history_census_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    path = Path(__file__)
    return {**history_inventory.implementation(),
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()}


def protocol_content(owner):
    """Exact registration content; registering it requires the audited parent."""
    require(type(owner) is history_inventory.HistoryOwner, "concrete_history_owner")
    source = owner.source
    # The enclosing inventory verifies the exact snapshot family before opening
    # either concrete reader. Do not accept arbitrary Source subclasses.
    require(type(source) in {source_adapter.Source,
        history_inventory.lineage.v11_snapshot.compatibility.Source}, "concrete_locked_source")
    source._active()
    return {"method": METHOD, "implementation": implementation(),
        "owner_sha256": digest(str(source.owner)), "source_head": list(owner.scope["source_head"]),
        "declared_history_scope_sha256": digest(owner.scope),
        "read_scope": "all_event_and_record_sql_rows_no_referenced_artifact_traversal",
        "purpose": "Reveal omitted event/record evidence for later task classification; no semantic exclusion."}


def collect_full_history_census(owner, *, protocol_record):
    """Retain all raw metadata under an active registered Research operation.

    The parent must use open_history_inventory through final-cutoff/liveness
    verification and retain its completed proof. This extension neither opens a
    source nor substitutes for that full preflight and final commit guard.
    The supplied protocol is read from the observer's actual immutable ledger.
    """
    expected = protocol_content(owner)
    source = owner.source
    engine, session = source.engine, source.session
    require_active(engine, session)
    require(engine.config.offline, "offline_required")
    protocol = engine.ledger.get(protocol_record, "protocol")
    require(digest(protocol["content"]) == digest(expected), "registered_protocol_binding")
    head = expected["source_head"]
    require(source.head() == head and owner.census["source_head"] == head
        and owner.census["scope_sha256"] == expected["declared_history_scope_sha256"]
        and owner.census["owner_sha256"] == expected["owner_sha256"], "source_scope_binding")
    intent = engine.ledger.record(session, INTENT, digest(expected),
        {"method": METHOD, "protocol_record": protocol_record, "binding": expected})

    # Query the already locked, read-only private clone. No additional source
    # connection, writer, artifact traversal or heuristic event filtering.
    events = [dict(row) for row in source.db.execute("SELECT * FROM events ORDER BY seq")]
    records = [dict(row) for row in source.db.execute("SELECT * FROM records ORDER BY created_event")]
    previous, event_by_seq = "0" * 64, {}
    for position, row in enumerate(events, 1):
        payload = exposure._event(row, head[0])
        require(row["seq"] == position and row["previous_hash"] == previous, "full_event_chain")
        previous = row["event_hash"]
        event_by_seq[position] = (row, payload)
    require(len(events) == head[0] and previous == head[1], "complete_event_head")
    record_by_id = {}
    for row in records:
        require(set(row) == {"id", "kind", "logical_key", "payload", "artifact", "supersedes", "created_event"},
            "record_fields")
        require(isinstance(row["payload"], str)
            and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"], "record_payload_bytes")
        # Check valid JSON, but preserve exact projection bytes rather than
        # reserializing historical numeric-key mappings.
        json.loads(row["payload"])
        require(row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
            "payload": row["artifact"], "supersedes": row["supersedes"]})
            and row["id"] not in record_by_id, "record_identity")
        creation = event_by_seq.get(row["created_event"])
        require(creation is not None and creation[0]["kind"] == "record.created"
            and digest(creation[1]) == digest({"record": row["id"], "kind": row["kind"],
                "artifact": row["artifact"]}), "record_creation_binding")
        record_by_id[row["id"]] = row
    creations = [payload["record"] for row, payload in event_by_seq.values() if row["kind"] == "record.created"]
    require(len(creations) == len(records) and set(creations) == set(record_by_id), "complete_record_projection")
    event_by_hash = {row["event_hash"]: row for row in events}
    require(len(event_by_hash) == len(events), "duplicate_event_identity")
    selected_events = [row["event_hash"] for row in owner.events]
    selected_records = [row["id"] for row in owner.records]
    selected_event_set, selected_record_set = set(selected_events), set(selected_records)
    require(selected_events == owner.census["selected_event_hashes"]
        and selected_records == owner.census["selected_record_ids"], "selected_census_binding")
    require(len(selected_event_set) == len(selected_events)
        and len(selected_record_set) == len(selected_records), "duplicate_selected_identity")
    for row in owner.events:
        require(row["event_hash"] in event_by_hash
            and digest(row) == digest(event_by_hash[row["event_hash"]]), "selected_event_changed")
    for row in owner.records:
        require(row["id"] in record_by_id and digest(row) == digest(record_by_id[row["id"]]), "selected_record_changed")
    require(dict(Counter(row["kind"] for row in records)) == owner.census["record_kind_counts"], "full_record_census")
    intended = [r["event_hash"] for r in events if r["kind"] == "model.attempt.intended"]
    completed = [r["event_hash"] for r in events if r["kind"] == "model.attempt.completed"]
    require(intended == owner.census["intent_event_hashes"]
        and completed == owner.census["completion_event_hashes"], "generic_attempt_census")
    unselected_events = [row["event_hash"] for row in events if row["event_hash"] not in selected_event_set]
    unselected_records = [row["id"] for row in records if row["id"] not in selected_record_set]
    require(set(unselected_records) == set(owner.census["out_of_scope_record_ids"]), "excluded_record_census")
    events_ref, records_ref = (engine.ledger.artifacts.put(value) for value in (events, records))
    value = {"method": METHOD, "implementation": expected["implementation"], "protocol_record": protocol_record,
        "intent_record": intent, "owner_sha256": expected["owner_sha256"], "source_head": head,
        "declared_history_scope_sha256": expected["declared_history_scope_sha256"],
        "original_scoped_census_artifact": engine.ledger.artifacts.put(owner.census),
        "events_artifact": events_ref, "records_artifact": records_ref,
        "event_count": len(events), "record_count": len(records),
        "event_kind_counts": dict(Counter(row["kind"] for row in events)),
        "record_kind_counts": dict(Counter(row["kind"] for row in records)),
        "selected_event_hashes": selected_events, "unselected_event_hashes": unselected_events,
        "selected_record_ids": selected_records, "unselected_record_ids": unselected_records,
        "all_metadata_rows_retained": True, "generic_intent_count": len(intended),
        "referenced_artifacts_traversed": False, "manual_task_semantics_classified": False,
        "unselected_metadata_requires_disposition": bool(unselected_events or unselected_records),
        "whole_history_discovery_complete": False, "no_retry_certificate_created": False,
        "prior_exposure_reclassified": False, "parent_final_inventory_proof_required": True,
        "fresh_source_liveness_verified_here": False, "new_model_calls": 0, "dispatch_authorized": False}
    require(source.head() == head and implementation() == expected["implementation"], "source_or_implementation_changed")
    record = engine.ledger.record(session, RESULT, intent, value)
    return {"record": record, "artifact": digest(value), "event_count": len(events), "record_count": len(records),
        "unselected_event_count": len(unselected_events), "unselected_record_count": len(unselected_records),
        "whole_history_discovery_complete": False, "dispatch_authorized": False}
