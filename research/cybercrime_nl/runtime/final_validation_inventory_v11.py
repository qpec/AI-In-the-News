"""Explicit V11-snapshot consumer; no original Study/Inventory globals changed.

Registered offline callers must use the new snapshot parent and this entrypoint.
The yielded scoped census has the original AttemptInventory interface. Thus pure
role/exposure helpers can consume it, but original preparation/history parents
do not automatically accept the new snapshot or this distinct result kind.
This is complete one-owner storage preflight/census, not complete role/history
reconciliation, a statistical frame, sampling, or model admission.
"""
from contextlib import contextmanager
import hashlib
from pathlib import Path

import final_validation_inventory as original
import final_validation_snapshot_v11 as parent
from newsresearch.common import digest, require_active, utc

METHOD = "cybercrime-final-validation-attempt-inventory-v11-v1"
RESULT_KIND = "cyber_final_validation_attempt_inventory_v11"


def implementation():
    root = Path(__file__).resolve().parents[3]
    value = parent.implementation()
    value[Path(__file__).relative_to(root).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return value


@contextmanager
def open_attempt_inventory(engine, session, context, binding, *, observe_liveness):
    """Only a concrete original-Study/seed-bound V11 snapshot is accepted."""
    require_active(engine, session)
    parent._require(engine.config.offline, "inventory_offline_required")
    engine._require(context, {"protocol", "selection"})
    code = implementation()
    for kind in ("protocol", "selection"):
        version = engine.ledger.get(context.versions[kind], kind)["content"]
        parent._require(version.get("snapshot_binding_sha256") == digest(binding), "inventory_registered_snapshot_binding")
        if kind == "protocol":
            parent._require(version.get("method") == METHOD and version.get("implementation") == code, "inventory_registered_method")
    snapshot, index = parent.load_snapshot(engine, session, binding)
    bindings = snapshot["source_bindings"]
    source_api = parent.compatibility
    owner = Path(bindings["source_owner"]).resolve(strict=True)
    before = source_api._liveness(observe_liveness, owner)
    source_api._retained_liveness(engine, before)
    source = source_api.Source(engine, session, owner)
    try:
        parent._selected_source(source, snapshot)
        preflight = original._full_preflight(source, bindings["source_head"])
        reader = original._census(source, engine, session, snapshot, index)
        fingerprint = reader._fingerprint()
        yield reader
        parent._require(reader._fingerprint() == fingerprint, "inventory_census_changed_by_consumer")
        after = source_api._liveness(observe_liveness, owner)
        source_api._retained_liveness(engine, after)
        parent._require(source.head(fresh=True) == bindings["source_head"], "source_changed_during_inventory")
        parent._require(implementation() == code, "inventory_implementation_changed")
        record = {"method": METHOD, "implementation": code, "versions": context.versions,
            "snapshot_binding": binding, "source_bindings": bindings, "input_index_digest": index.digest,
            "original_study_record": snapshot["parent_authority"]["binding"]["study_record"],
            "original_seed_record": snapshot["parent_authority"]["binding"]["seed_record"],
            "preflight": preflight, **reader.counts, "events_artifact": engine.ledger.artifacts.put(reader.events),
            "records_artifact": engine.ledger.artifacts.put(reader.records),
            "phase_records_artifact": engine.ledger.artifacts.put(reader.phase_records),
            "phase_events_artifact": engine.ledger.artifacts.put(reader.phase_events),
            "pilot_selections_artifact": engine.ledger.artifacts.put(reader.pilot_selections),
            "prior_diagnostics_artifact": engine.ledger.artifacts.put(reader.prior_diagnostics),
            "amendment_packet_plans_artifact": engine.ledger.artifacts.put(reader.amendment_packet_plans),
            "pair_inventory_artifact": engine.ledger.artifacts.put(reader.certificate),
            "permitted_source_artifacts": sorted(reader.artifacts.permitted), "liveness": [before, after],
            "observed_at": utc(), "source_head_stable": True, "full_source_ledger_preflight_verified": True,
            "main_owner_attempt_census_complete": True, "production_roles_reconciled": False,
            "candidate_exposure_resolved": False, "prior_inventory_complete": False,
            "new_model_calls": 0, "source_mutations": 0,
            "limitations": "Complete one-owner ledger census at the original-Study/seed-bound V11 cutoff. Role/reuse, cross-owner P, reference compatibility and versioned downstream preparation remain pending; no frame or admission authority."}
        identity = engine.ledger.record(session, RESULT_KIND, digest(binding), record)
        reader.result = {"inventory_record": identity, "inventory_artifact": digest(record), "source_head": bindings["source_head"],
            **{key: record[key] for key in ("physical_attempts", "response_records", "orphan_intents", "derived_records",
                "pair_attempts", "excluded_nonpair_attempts", "unknown_task_semantics", "input_index_digest",
                "full_source_ledger_preflight_verified", "main_owner_attempt_census_complete", "production_roles_reconciled",
                "candidate_exposure_resolved", "prior_inventory_complete", "new_model_calls", "source_mutations")}}
    finally:
        source.close()
