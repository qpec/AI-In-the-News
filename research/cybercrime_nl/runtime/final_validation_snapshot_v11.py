"""Original-Study/seed-bound V11 snapshot parent; prospective, offline only.

This distinct authority does not impersonate the original Source snapshot or
change the original Study implementation/specification/seeds. Initialize using
the original Study, then explicitly register this new freeze method. The proof
and full cloned Ledger preflight refer to one exact immutable source cutoff.
Only final_validation_inventory_v11 consumes this snapshot. Original Preparation
and later frame/history/admission parents need separate versioned integration;
neither this snapshot nor its reuse permits sampling or model dispatch.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import final_validation_inventory as inventory
import final_validation_source_v11 as compatibility
import final_validation_study as original
from final_validation_frame import build_input_index
from newsresearch.common import AuditError, Context, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-final-validation-v11-snapshot-parent-v1"
FREEZE = "cyber_final_validation_v11_freeze_binding"
ACCESS = "cyber_final_validation_v11_source_access"
PREFLIGHT = "cyber_final_validation_v11_source_preflight"
SNAPSHOT = "cyber_final_validation_source_snapshot_v11"
ROOT = Path(__file__).resolve().parents[3]


def _require(value, code):
    if not value:
        raise AuditError("final_validation_snapshot_v11_" + code)


def implementation():
    result = {**compatibility.implementation(), **inventory.implementation()}
    result[Path(__file__).relative_to(ROOT).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return {key.replace("\\", "/"): value for key, value in result.items()}


class _Registration:
    """Read-only reuse of the exact original registration verifier, not init."""
    _rows = original.Study._rows
    _one = original.Study._one
    _verify_seeds = original.Study._verify_seeds
    _registration = original.Study._registration

    def __init__(self, engine, owner):
        self.ledger, self.source_owner = engine.ledger, Path(owner).resolve()


def binding(study_record, seed_record, source_bindings):
    for value in (study_record, seed_record):
        compatibility.original._sha(value)
    compatibility._bindings(source_bindings)
    return {"study_record": study_record, "seed_record": seed_record, "source_bindings": source_bindings}


def _authority(engine, value):
    _require(isinstance(value, dict) and set(value) == {"study_record", "seed_record", "source_bindings"}, "binding_fields")
    binding(**value)
    view = _Registration(engine, value["source_bindings"]["source_owner"])
    row = view._registration()
    _require(row["id"] == value["study_record"] and row["payload"]["seed_record"] == value["seed_record"], "original_registration_binding")
    _require(all(row["payload"]["configuration"][key] == value["source_bindings"][key]
        for key in ("expected_documents", "expected_articles", "expected_aliases")), "original_frame_changed")
    _require(not any(view._rows(kind) for kind in (original.FREEZE, original.ACCESS, original.SNAPSHOT)), "original_freeze_coexists")
    return view, row


def _versions(engine, versions, value, code):
    _require(set(versions) == {"protocol", "selection"}, "registered_versions_required")
    for kind, identity in versions.items():
        content = engine.ledger.get(identity, kind)["content"]
        _require(content.get("parent_binding_sha256") == digest(value)
            and content.get("study_record") == value["study_record"]
            and content.get("seed_record") == value["seed_record"], "registered_parent_binding")
        if kind == "protocol":
            _require(content.get("method") == METHOD and content.get("implementation") == code, "registered_parent_method")


def _proof(engine, row, value):
    proof = row["payload"]
    _require(proof.get("method") == compatibility.METHOD and proof.get("implementation") == compatibility.implementation()
        and proof.get("source_bindings") == value["source_bindings"], "compatibility_proof_binding")
    for kind, identity in proof["versions"].items():
        content = engine.ledger.get(identity, kind)["content"]
        _require(content.get("source_bindings_sha256") == digest(value["source_bindings"])
            and content.get("study_record") == value["study_record"]
            and content.get("seed_record") == value["seed_record"], "proof_original_seed_binding")
        if kind == "protocol":
            _require(content.get("method") == compatibility.METHOD
                and content.get("implementation") == proof["implementation"], "proof_registered_method")
    _require(set(proof["versions"]) == {"protocol", "selection"}, "proof_versions")
    _require(all(proof.get(key) is True for key in ("pipeline_processing_complete", "pipeline_finished", "export_verified",
        "source_head_stable", "source_writer_lock_held_during_snapshot"))
        and proof["reported_final_audit_completion"].get("processing_finished") is True, "final_processing_incomplete")
    _require(proof.get("original_study_implementation_sha256") == digest(original.implementation()), "original_code_changed")
    return proof


def _selected_source(source, proof):
    source_bindings = proof["source_bindings"]
    _require(source.head() == source_bindings["source_head"], "source_cutoff_changed")
    for item in proof["source_records"]:
        row = source.db.execute("SELECT * FROM records WHERE id=?", (item["_record_id"],)).fetchone()
        _require(row is not None and row["kind"] == item["_record_kind"] and row["artifact"] == item["_artifact"]
            and row["created_event"] == item["_created_event"], "selected_source_record_changed")
    reports = source.rows("cyber_dossier_report")
    _require(reports and reports[-1]["_record_id"] == source_bindings["report"], "latest_report_changed")
    source.ensure_report_last(reports[-1])


def load_snapshot(engine, session, selected):
    """Verify retained parent authority; no claim of current source liveness."""
    require_active(engine, session)
    _require(engine.config.offline and isinstance(selected, dict)
        and set(selected) == {"snapshot_record", "snapshot_artifact"}, "snapshot_binding_fields")
    for reference in selected.values():
        compatibility.original._sha(reference)
    saved = engine.ledger.get(selected["snapshot_record"], SNAPSHOT)
    _require(digest(saved) == selected["snapshot_artifact"] and set(saved) == {
        "method", "implementation", "versions", "binding", "freeze_record", "access_record", "proof_record", "proof_artifact",
        "preflight_record", "preflight_artifact", "original_study_implementation_sha256", "new_model_calls", "source_mutations",
        "sample_drawn", "dispatch_authorized"}, "snapshot_identity")
    code = implementation()
    _require(saved["method"] == METHOD and saved["implementation"] == code
        and saved["original_study_implementation_sha256"] == digest(original.implementation())
        and saved["sample_drawn"] is False and saved["dispatch_authorized"] is False
        and type(saved["new_model_calls"]) is int and saved["new_model_calls"] == 0
        and type(saved["source_mutations"]) is int and saved["source_mutations"] == 0, "snapshot_policy_or_implementation")
    view, registration = _authority(engine, saved["binding"])
    freeze, access, proof_row, preflight_row = (view._one(kind) for kind in (FREEZE, ACCESS, compatibility.RESULT_KIND, PREFLIGHT))
    _require(view._one(SNAPSHOT)["id"] == selected["snapshot_record"]
        and freeze["id"] == saved["freeze_record"] and access["id"] == saved["access_record"]
        and proof_row["id"] == saved["proof_record"] and preflight_row["id"] == saved["preflight_record"], "snapshot_record_links")
    _require(freeze["payload"] == {"method": METHOD, "implementation": code, "binding": saved["binding"], "versions": saved["versions"]}
        and access["payload"] == {"freeze_record": freeze["id"], "binding_sha256": digest(saved["binding"]), "versions": saved["versions"]}, "freeze_authority_changed")
    _versions(engine, saved["versions"], saved["binding"], code)
    _require(registration["created_event"] < freeze["created_event"] < access["created_event"]
        < proof_row["created_event"] < preflight_row["created_event"] < view._one(SNAPSHOT)["created_event"], "authority_order")
    proof = _proof(engine, proof_row, saved["binding"])
    _require(digest(proof) == saved["proof_artifact"], "proof_artifact_changed")
    preflight = preflight_row["payload"]
    _require(digest(preflight) == saved["preflight_artifact"] and preflight["method"] == METHOD
        and preflight["implementation"] == code and preflight["proof_record"] == proof_row["id"]
        and preflight["proof_artifact"] == saved["proof_artifact"] and preflight["freeze_record"] == freeze["id"]
        and preflight["source_head_stable"] is True, "preflight_binding")
    checked = preflight["preflight"]
    _require(checked["status"] == "verified" and [checked["events"], checked["head_hash"]] == proof["source_bindings"]["source_head"]
        and checked["database_verification"] == "isolated_in_memory_backup"
        and checked["fts_integrity_write_location"] == "private_memory_clone"
        and type(checked["source_database_writes"]) is int and checked["source_database_writes"] == 0, "full_preflight_required")
    _require(len(preflight["liveness"]) == 2, "retained_liveness_required")
    for observation in preflight["liveness"]:
        compatibility._retained_liveness(engine, observation)
        _require(observation.get("inspection_complete") is True and observation.get("active_writers") == []
            and Path(observation["source_owner"]).resolve() == view.source_owner, "retained_liveness_binding")
    entries = engine.ledger.artifacts.read(proof["input_index_artifact"])
    index = build_input_index([{key: row[key] for key in ("document_id", "input_sha256", "article_row_ids")} for row in entries],
        {row["document_id"]: row["accepted_dossier_id"] for row in entries}, bindings=proof["input_index_bindings"])
    _require(index.digest == proof["input_index_digest"] and len(index.inputs) == proof["unique_documents"]
        and dict(index.bindings) == {"source_head": digest(proof["source_bindings"]["source_head"]),
            "final_report": proof["source_bindings"]["report"], "input_manifest": proof["source_bindings"]["input_manifest"]}, "input_index_binding")
    return {**proof, "method": METHOD, "implementation": code, "parent_authority": saved,
        "original_study_registration_verified": True, "full_source_ledger_preflight_verified": True,
        "v11_snapshot_created": True, "original_snapshot_created": False}, index


class SnapshotParent(original.Study):
    """No initialization, randomness, sampling, or model route in this extension."""
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        _require(operation == "status" and not versions and isinstance(payload, dict)
            and payload.get("action") in {"freeze", "status"}
            and set(payload) == {"action", "binding"}, "entry_shape")
        return Research.execute(self, "status", {"method": METHOD, **payload}, objective=objective, actor=actor)

    @audited_handler
    def _status(self, session, context, data):
        _require(self.config.offline and data["method"] == METHOD, "offline_entry_required")
        value = data["binding"]
        _, registration = _authority(self, value)
        _require(Path(value["source_bindings"]["source_owner"]).resolve() == self.source_owner, "source_owner_changed")
        old = self._one(SNAPSHOT, optional=True)
        if old:
            _require(old["payload"]["binding"] == value, "cutoff_changed_requires_amendment")
            return self._summary_v11(session, old, reused=True)
        if data["action"] == "status":
            freeze = self._one(FREEZE, optional=True)
            _require(freeze is None or freeze["payload"]["binding"] == value, "cutoff_changed_requires_amendment")
            return {"method": METHOD, "study_record": registration["id"], "seed_record": value["seed_record"],
                "source_frozen": False, "incomplete_freeze": freeze is not None, "dispatch_authorized": False}
        _require(type(self.observer) is original.WindowsProcessObserver, "concrete_process_observer_required")
        code = implementation()
        versions = {kind: self._version_once(session, context, kind, METHOD, {
            "parent_binding_sha256": digest(value), "study_record": value["study_record"], "seed_record": value["seed_record"],
            **({"method": METHOD, "implementation": code} if kind == "protocol" else {"rules": "Exact V11 final cutoff; unchanged original Study and seeds."})})
            for kind in ("protocol", "selection")}
        desired = {"method": METHOD, "implementation": code, "binding": value, "versions": versions}
        freeze = self._one(FREEZE, optional=True)
        if freeze:
            _require(freeze["payload"] == desired, "cutoff_changed_requires_amendment")
        else:
            _require(not self._rows(ACCESS) and not self._rows(compatibility.RESULT_KIND) and not self._rows(PREFLIGHT), "unbound_prior_access")
            self.ledger.record(session, FREEZE, METHOD, desired)
            freeze = self._one(FREEZE)
        if not self._rows(ACCESS):
            self.ledger.record(session, ACCESS, METHOD, {"freeze_record": freeze["id"], "binding_sha256": digest(value), "versions": versions})
        proof_row = self._one(compatibility.RESULT_KIND, optional=True)
        if proof_row is None:
            proof_versions = {kind: self._version_once(session, context, kind, METHOD + ":proof", {
                "source_bindings_sha256": digest(value["source_bindings"]), "study_record": value["study_record"], "seed_record": value["seed_record"],
                **({"method": compatibility.METHOD, "implementation": compatibility.implementation()} if kind == "protocol"
                   else {"rules": "Exact completed V11 processing, export and finished audit phases; unavailable reference coverage stays explicit."})})
                for kind in ("protocol", "selection")}
            compatibility.verify_final_compatibility(self, session, Context(context.objective, context.actor, proof_versions),
                value["source_bindings"], observe_liveness=lambda owner: self.observer.observe(self, session, owner))
            proof_row = self._one(compatibility.RESULT_KIND)
        proof = _proof(self, proof_row, value)
        # Always recheck a fresh locked cutoff, even when recovering a prior proof.
        before = compatibility._liveness(lambda owner: self.observer.observe(self, session, owner), self.source_owner)
        compatibility._retained_liveness(self, before)
        source = compatibility.Source(self, session, self.source_owner)
        try:
            _selected_source(source, proof)
            preflight = inventory._full_preflight(source, value["source_bindings"]["source_head"])
            after = compatibility._liveness(lambda owner: self.observer.observe(self, session, owner), self.source_owner)
            compatibility._retained_liveness(self, after)
            _require(source.head(fresh=True) == value["source_bindings"]["source_head"], "source_changed_during_preflight")
            _require(implementation() == code, "implementation_changed")
            # A crash after preflight but before snapshot requires explicit
            # recovery. Hold the same source writer lock through both durable
            # records and their verification, exactly as in the original freeze.
            _require(not self._rows(PREFLIGHT), "incomplete_snapshot_requires_explicit_recovery")
            preflight_value = {"method": METHOD, "implementation": code, "proof_record": proof_row["id"], "proof_artifact": digest(proof),
                "freeze_record": freeze["id"], "preflight": preflight, "liveness": [before, after], "source_head_stable": True, "observed_at": utc()}
            preflight_id = self.ledger.record(session, PREFLIGHT, METHOD, preflight_value)
            saved = {"method": METHOD, "implementation": code, "versions": versions, "binding": value,
                "freeze_record": freeze["id"], "access_record": self._one(ACCESS)["id"], "proof_record": proof_row["id"], "proof_artifact": digest(proof),
                "preflight_record": preflight_id, "preflight_artifact": digest(preflight_value),
                "original_study_implementation_sha256": digest(original.implementation()), "new_model_calls": 0, "source_mutations": 0,
                "sample_drawn": False, "dispatch_authorized": False}
            self.ledger.record(session, SNAPSHOT, METHOD, saved)
            return self._summary_v11(session, self._one(SNAPSHOT), reused=False)
        finally:
            source.close()

    def _summary_v11(self, session, row, *, reused):
        selected = {"snapshot_record": row["id"], "snapshot_artifact": digest(row["payload"])}
        proof, _ = load_snapshot(self, session, selected)
        audit = proof["reported_final_audit_completion"]
        return {"method": METHOD, **selected, "study_record": row["payload"]["binding"]["study_record"],
            "seed_record": row["payload"]["binding"]["seed_record"], "source_frozen": True,
            **{key: proof[key] for key in ("input_index_digest", "unique_documents", "article_rows", "alias_rows", "accepted_inputs",
                "singleton_prediction_inputs", "pipeline_processing_complete", "pipeline_finished", "export_verified")},
            "full_source_ledger_preflight_verified": True, "final_audit_complete": audit["complete"],
            "final_audit_available": audit["available"], "final_audit_unavailable": audit["unavailable"],
            "final_audit_not_attempted": audit["not_attempted"], "reused_frozen_cutoff": reused,
            "current_source_quiescence_verified": not reused, "original_snapshot_created": False,
            "sample_drawn": False, "dispatch_authorized": False, "new_model_calls": 0, "source_mutations": 0,
            "pending": ["versioned_preparation_parent", "complete_reference_history_and_roles", "frame_and_schedule",
                "packet_resource_admission", "registered_account_execution", "statistical_estimation"]}
