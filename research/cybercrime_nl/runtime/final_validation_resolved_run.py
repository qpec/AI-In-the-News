"""Prospective initial Run authority for the completed main-metadata resolution.

This is a distinct, separately registered parent. The original Run is an
explicit unchanged subproducer, not silently upgraded evidence. An existing
Run intent, manifest, local slot or model attempt cannot acquire this authority
retrospectively. Completed Root/MainMetadata/Lifecycle/NativeArtifact producers
must already exist; this module opens no source owners and resolves no new gaps.

The original Study, four seeds, fixed slots, Execution, provider, gateway and
initial resource window remain unchanged. Missing P and missing task history
remain separate. Later dispatch is NOT enabled: a separately reviewed consumer
must select this actual authority kind and call verified_frame_and_closure.
The original Run/later parent cannot consume the derived projection by a flag.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_main_metadata as metadata
import final_validation_run as original
from newsresearch.common import AuditError, digest, require_active, require_no_credentials
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-metadata-resolved-initial-run-v1"
INTENT = "cyber_final_validation_resolved_run_intent"
AUTHORITY = "cyber_final_validation_resolved_run_authority"
POLICY = {"original_run_is_unchanged_subproducer": True,
    "completed_metadata_replay_required": True, "retroactive_adoption": False,
    "remaining_history_gaps_preserved": True, "initial_window_renewable": False,
    "later_dispatch_enabled": False, "paid_api_fallback": False,
    "new_seed_draws": 0, "source_owner_reads": 0}
BINDING_FIELDS = {"final_frame_record", "closure_record", "lifecycle_record",
    "supplement_record", "metadata_resolution_record"}


def require(value, reason):
    if not value:
        raise AuditError("resolved_run_" + reason)


def implementation():
    code = {**original.implementation(), **metadata.implementation()}
    path = Path(__file__)
    code[path.relative_to(original.study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def binding(**values):
    require(set(values) == BINDING_FIELDS, "binding_fields")
    for value in values.values():
        original.execution.sha(value)
    return deepcopy(values)


def base_binding(selected):
    return original.binding(**{key: selected[key] for key in ("final_frame_record", "closure_record")})


def _replay_resolution(engine, session, context, selected):
    """Real completed producer replay, with no caller-supplied proof semantics."""
    require_active(engine, session)
    selected = binding(**selected)
    completed = engine._one(metadata.RESULT)
    require(completed["id"] == selected["metadata_resolution_record"], "unique_metadata_result")
    saved = completed["payload"]
    for key in ("closure_record", "lifecycle_record", "supplement_record"):
        require(saved["binding"][key] == selected[key], "metadata_selected_binding")
    # The original frame loader can create a Root resolution. This parent only
    # consumes already completed producers, so verify their exact identities
    # before entering that loader, even when the selected metadata is malformed.
    for kind, key in ((metadata.roots.RESULT, "root_resolution_record"),
        (original.lifecycle.RESULT, "lifecycle_record"), (metadata.supplement.RESULT, "supplement_record")):
        require(engine._one(kind)["id"] == saved["binding"][key], "completed_metadata_prerequisite")
    # This explicitly invokes the unchanged producer, not a caller override or
    # the inherited BatchHistory loader mistaken for a Closure replay.
    verified = original.FinalValidationRun._frame_and_closure(engine, session, context, base_binding(selected))
    frame_value, chain, frame, schedule, root_bound, root_projection, registered = verified
    resolved = metadata.resolve_completed_metadata(engine, session, context,
        selected["closure_record"], selected["lifecycle_record"], selected["supplement_record"], create=False)
    require(resolved.get("resolved") and resolved["metadata_resolution_record"] == completed["id"], "completed_metadata_required")
    root_id = root_bound["history_verification_record"]
    require(resolved["root_resolution_record"] == saved["binding"]["root_resolution_record"] == root_id,
        "same_root_resolution")
    require(saved["binding"]["inherited_projection_artifact"] == root_bound["effective_projection_artifact"]
        and root_bound["lifecycle_evidence_record"] == selected["lifecycle_record"], "same_root_and_lifecycle")
    require(saved["binding"]["input_index_digest"] == frame.index.digest
        and saved["binding"]["main_owner_sha256"] == digest(str(engine.source_owner))
        and original.same(saved["binding"]["source_head"], chain[0]["source_bindings"]["source_head"]), "same_source_frame")
    projection = engine.ledger.artifacts.read(resolved["projection_artifact"])
    require(digest(projection) == resolved["projection_artifact"]
        and projection["input_index_digest"] == frame.index.digest, "metadata_projection")
    # MainMetadata may discharge only its mechanically proved metadata gaps.
    # Checking these invariants here also prevents a cross-frame projection from
    # being accepted merely because its result record has an expected kind.
    for field in ("pair_role_blockers", "physical_tasks", "prepared_only", "root_dispositions"):
        require(original.same(projection[field], root_projection[field]), "task_or_root_partition_changed")
    require(original.same(projection["scoped_certificate"]["source_heads"],
        root_projection["scoped_certificate"]["source_heads"]), "projection_cutoffs_changed")
    require(all(region in root_projection["unresolved_regions"] for region in projection["unresolved_regions"]),
        "projection_regions_changed")
    bound = {**root_bound, "root_resolution_record": root_id,
        "root_projection_artifact": root_bound["effective_projection_artifact"],
        "effective_projection_artifact": resolved["projection_artifact"],
        "history_verification_record": resolved["metadata_resolution_record"],
        "metadata_resolution_record": resolved["metadata_resolution_record"],
        "metadata_evidence_artifact": resolved["metadata_evidence_artifact"],
        "native_supplement_record": selected["supplement_record"]}
    return frame_value, chain, frame, schedule, bound, projection, registered


def _proof_binding(engine, selected, verified):
    frame_value, chain, frame, schedule, saved, projection, registered = verified
    seeds = engine.ledger.get(registered["payload"]["seed_record"], original.study.SEEDS)
    result = engine.ledger.get(selected["metadata_resolution_record"], metadata.RESULT)
    return {"binding": selected, "study_record": registered["id"],
        "seed_record": registered["payload"]["seed_record"], "seed_payload_sha256": digest(seeds),
        "source_snapshot": frame_value["binding"]["preparation_binding"]["snapshot_binding"],
        "source_head": chain[0]["source_bindings"]["source_head"],
        "frame_digest": frame.digest, "schedule_digest": schedule.digest,
        "input_index_digest": frame.index.digest,
        "schedule_seed_artifact": frame_value["schedule_seed_artifact"],
        "article_order_seed_artifact": frame_value["article_order_seed_artifact"],
        "metadata_payload_sha256": digest(result), "metadata_protocol_record": result["protocol_record"],
        "metadata_binding_sha256": digest(result["binding"]),
        "root_resolution_record": saved["root_resolution_record"],
        "root_projection_artifact": saved["root_projection_artifact"],
        "root_evidence_artifact": saved["root_resolution_evidence_artifact"],
        "effective_projection_artifact": saved["effective_projection_artifact"],
        "metadata_evidence_artifact": saved["metadata_evidence_artifact"],
        "original_closure_sha256": saved["original_closure_sha256"],
        "legacy_records_artifact": chain[3]["artifacts"]["pair_history_records"],
        "legacy_inventory_artifact": chain[3]["artifacts"]["pair_history_inventory"],
        "remaining_regions_sha256": digest(projection["unresolved_regions"])}


def _base_kinds():
    return (original.INTENT, original.AUTHORITY, original.PREPARED, original.OBSERVATION, original.REPORT,
        original.execution.ADMISSION_KIND, original.execution.MANIFEST_KIND,
        original.execution.SLOT_KIND, original.execution.INTENT_KIND, original.execution.RESULT_KIND,
        original.execution.HALT_KIND, original.execution.REPORT_KIND,
        original.series.SERIES, original.series.TRANCHE, original.series.ADMISSION,
        original.series.INTENT, original.series.RESULT, original.series.SLOT, original.series.HALT, original.series.LOOK)


def _base_evidence(engine):
    return any(engine._rows(kind) for kind in _base_kinds()) or bool(engine.ledger.db.execute(
        "SELECT 1 FROM events WHERE kind LIKE 'model.attempt.%' LIMIT 1").fetchone())


def _row(engine, kind, *, optional=False):
    row = engine._one(kind, optional=optional)
    if row is not None:
        key = engine.ledger.db.execute("SELECT logical_key FROM records WHERE id=?", (row["id"],)).fetchone()[0]
        expected = METHOD if kind == INTENT else row["payload"]["intent_record"]
        require(key == expected, "authority_logical_key")
    return row


def _registered_protocol(engine, identifier, intent, desired, *, authority=None):
    rows = list(engine.ledger.db.execute(
        "SELECT id,created_event FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
    require(len(rows) == 1 and rows[0]["id"] == identifier, "authority_protocol")
    value = engine.ledger.get(identifier, "protocol")
    require(original.same(value["content"], {"method": METHOD, "intent_record": intent["id"], "binding": desired})
        and value["reason"] is None and value["branch"] == "main", "authority_protocol")
    sequence = rows[0]["created_event"]
    require(type(intent["created_event"]) is int and type(sequence) is int
        and intent["created_event"] < sequence, "authority_chronology")
    if authority is not None:
        require(type(authority["created_event"]) is int and sequence < authority["created_event"], "authority_chronology")


def verified_frame_and_closure(engine, session, context, selected):
    """Read exact NEW authority; future consumers must select its actual kind.

    This verifies retained authority and returns the original Run tuple shape.
    It does not authorize a later producer or renew any resource window.
    """
    require_active(engine, session)
    require(isinstance(engine, original.FinalValidationRun), "concrete_run_parent")
    row, intent = _row(engine, AUTHORITY), _row(engine, INTENT)
    value = row["payload"]
    require(value["method"] == METHOD and original.same(value["policy"], POLICY)
        and original.same(value["implementation"], implementation()), "authority_implementation")
    require(value["intent_record"] == intent["id"]
        and value["intent_sha256"] == digest(intent["payload"]), "authority_intent")
    desired = intent["payload"]
    require(desired["method"] == METHOD and original.same(desired["policy"], POLICY)
        and original.same(desired["implementation"], implementation()), "intent_implementation")
    require(original.same(base_binding(desired["inputs"]["binding"]), selected), "base_binding_changed")
    _registered_protocol(engine, value["protocol_record"], intent, desired, authority=row)
    for kind in _base_kinds():
        for existing in engine._rows(kind):
            require(row["created_event"] < existing["created_event"], "retrospective_authority")
    first = engine.ledger.db.execute("SELECT MIN(seq) FROM events WHERE kind LIKE 'model.attempt.%'").fetchone()[0]
    require(first is None or row["created_event"] < first, "retrospective_authority")
    verified = _replay_resolution(engine, session, context, desired["inputs"]["binding"])
    require(original.same(value["proof"], _proof_binding(engine, desired["inputs"]["binding"], verified)), "authority_proof_changed")
    base_intent = engine._one(original.INTENT, optional=True)
    if base_intent:
        expected_inputs = {**desired["inputs"], "binding": selected}
        require(original.same(base_intent["payload"]["inputs"], expected_inputs), "base_inputs_changed")
    return verified


class ResolvedValidationRun(original.FinalValidationRun):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        fields = {"prepare": {"action", "binding", "runtime", "quota_receipt", "resource_policy", "series_limits"},
            "run-initial": {"action", "prepared_record", "quota_receipt"},
            "resume": {"action", "prepared_record", "quota_receipt"}, "status": {"action"}}
        require(operation == "status" and not versions and data.get("action") in fields
            and set(data) == fields[data["action"]], "entry_shape")
        if data["action"] == "prepare":
            binding(**data["binding"])
            require(isinstance(data["runtime"], dict) and set(data["runtime"]) == {"executable", "sha256"}, "runtime_fields")
            original.execution.sha(data["runtime"]["sha256"])
            original.series.limits(data["series_limits"])
        elif data["action"] != "status":
            original.execution.sha(data["prepared_record"])
        require_no_credentials(data)
        return Research.execute(self, operation, {"method": METHOD, **data}, objective=objective, actor=actor)

    def _prepare_authority(self, session, context, data):
        require_active(self, session)
        desired = {"method": METHOD, "policy": POLICY, "implementation": implementation(),
            "inputs": {key: deepcopy(data[key]) for key in ("binding", "runtime", "quota_receipt", "resource_policy", "series_limits")}}
        existing, done = _row(self, INTENT, optional=True), _row(self, AUTHORITY, optional=True)
        require(existing is None or original.same(existing["payload"], desired), "changed_preparation_requires_amendment")
        require(done is None or existing is not None, "authority_without_intent")
        if done:
            verified_frame_and_closure(self, session, context, base_binding(data["binding"]))
            return done["id"]
        require(not _base_evidence(self), "existing_base_evidence_forbids_adoption")
        identity = existing["id"] if existing else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD,
            {"method": METHOD, "intent_record": identity, "binding": desired})
        _registered_protocol(self, protocol, _row(self, INTENT), desired)
        # Intent/protocol precede completed evidence replay and all base writes.
        verified = _replay_resolution(self, session, context, data["binding"])
        proof = _proof_binding(self, data["binding"], verified)
        value = {"method": METHOD, "policy": POLICY, "implementation": desired["implementation"],
            "intent_record": identity, "intent_sha256": digest(desired), "protocol_record": protocol, "proof": proof,
            "source_owner_reads": 0, "new_model_calls": 0, "later_dispatch_authorized": False}
        require(original.same(implementation(), desired["implementation"]), "implementation_changed")
        return self.ledger.record(session, AUTHORITY, identity, value)

    def _frame_and_closure(self, session, context, selected):
        return verified_frame_and_closure(self, session, context, selected)

    def _prepare_run(self, session, context, data):
        self._prepare_authority(session, context, data)
        return original.FinalValidationRun._prepare_run(self, session, context,
            {**data, "method": original.METHOD, "binding": base_binding(data["binding"])})

    def _load_run(self, session, context, identifier):
        _row(self, AUTHORITY)  # before any base replay/materialization
        return original.FinalValidationRun._load_run(self, session, context, identifier)

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        if data["action"] == "prepare":
            result = self._prepare_run(session, context, data)
        else:
            authority = _row(self, AUTHORITY, optional=True)
            if authority is None:
                require(not _base_evidence(self), "base_without_resolved_authority")
                require(data["action"] == "status", "prepared_authority_required")
                intent = _row(self, INTENT, optional=True)
                if intent:
                    require(intent["payload"]["method"] == METHOD
                        and original.same(intent["payload"]["implementation"], implementation())
                        and original.same(intent["payload"]["policy"], POLICY), "intent_implementation")
                return {"method": METHOD, "prepared": False, "dispatch_ready": False,
                    "authority_incomplete": intent is not None, "new_model_calls": 0}
            # A completed base result always enters _load_run, whose virtual
            # frame loader performs the full authority replay before any writes
            # or provider construction. Replay explicitly for incomplete status.
            if self._one(original.PREPARED, optional=True) is None:
                desired = _row(self, INTENT)["payload"]
                verified_frame_and_closure(self, session, context, base_binding(desired["inputs"]["binding"]))
            result = original.FinalValidationRun._status(self, session, context, {**data, "method": original.METHOD})
        row = _row(self, AUTHORITY)
        require(original.same(row["payload"]["implementation"], implementation()), "implementation_changed")
        return {**result, "subproducer_method": original.METHOD, "method": METHOD,
            "resolved_authority_record": row["id"], "metadata_resolution_record": row["payload"]["proof"]["binding"]["metadata_resolution_record"],
            "later_dispatch_authorized": False}
