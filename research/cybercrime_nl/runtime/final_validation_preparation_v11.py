"""Versioned V11 OFFLINE intermediate main-owner frame preparation, never admission.

This NEW operation composes the already registered Study and its frozen final
snapshot with an actual locked/preflighted main-owner census, role reconciliation
and original embedding replay. It cannot certify cross-owner/manual history.
The resulting frame/schedule are explicitly provisional: later reconciliation
must rebuild with the SAME retained seeds, not activate this incomplete frame.
No CLI, model transport, automatic source selection or mutable code amendment.
This separate parent accepts only the original-Study/seed-bound V11 snapshot and
InventoryV11. Older Preparation/Reconciliation/Task/Batch/Closure parents are not
changed or implicitly enabled. load_completed provides retained evidence to a
future explicitly versioned consumer; it is not permission to dispatch or a
finite-history closure. The original four seeds and Study digest stay unchanged.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import final_validation_embedding_provenance as embedding
import final_validation_frame_pipeline as pipeline
import final_validation_inventory_v11 as inventory
import final_validation_snapshot_v11 as snapshot_parent
import final_validation_pair_history as pair_history
import final_validation_prior as prior
import final_validation_projection as projection
import final_validation_roles as roles
import final_validation_study as original
from newsresearch.common import AuditError, Context, digest, require_active
from newsresearch.embeddings import VOCAB_HASH
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-intermediate-main-frame-preparation-v11-v1"
INTENT_KIND = "cyber_final_validation_frame_preparation_v11_intent"
RESULT_KIND = "cyber_final_validation_frame_preparation_v11"
TOKENIZER_KIND = "cyber_final_validation_preparation_tokenizer_v11"
POLICY = {"stage": "intermediate_main_owner_frame", "final_statistical_frame": False,
    "packet_preparation_eligible": False, "dispatch_authorized": False,
    "no_retry_history_complete": False, "prior_exposure_scope_complete": False,
    "future_reconciliation_requires_same_registered_seeds": True,
    "new_model_calls": 0, "source_mutations": 0}
DEFAULT_LIMITS = {"block_size": 128, "max_numeric_bytes": 768 * 1024 * 1024}


def require(value, reason):
    if not value:
        raise AuditError("final_preparation_" + reason)


def implementation():
    code = {}
    for module in (original, inventory, roles, prior, pair_history, pipeline):
        code.update(module.implementation())
    path = Path(__file__)
    code[path.relative_to(original.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def binding(*, study_record, seed_record, snapshot_binding, limits=None):
    """Only immutable identities/operational bounds; no caller C/P/vector truth."""
    value = {"study_record": study_record, "seed_record": seed_record,
        "snapshot_binding": snapshot_binding, "limits": limits or dict(DEFAULT_LIMITS)}
    validate_binding(value)
    return value


def validate_binding(value):
    require(isinstance(value, dict) and set(value) == {
        "study_record", "seed_record", "snapshot_binding", "limits"}, "binding_fields")
    original.source._sha(value["study_record"])
    original.source._sha(value["seed_record"])
    require(isinstance(value["snapshot_binding"], dict) and set(value["snapshot_binding"]) == {
        "snapshot_record", "snapshot_artifact"}, "snapshot_binding_fields")
    for item in value["snapshot_binding"].values():
        original.source._sha(item)
    limits = value["limits"]
    require(isinstance(limits, dict) and set(limits) == set(DEFAULT_LIMITS)
        and type(limits["block_size"]) is int and 1 <= limits["block_size"] <= 128
        and type(limits["max_numeric_bytes"]) is int
        and 1 <= limits["max_numeric_bytes"] <= DEFAULT_LIMITS["max_numeric_bytes"], "numeric_bounds")


def load_completed(engine, session, preparation_record):
    """Load concrete retained V11 evidence, never a current observation/admission.

    Returns (preparation, snapshot, input_index). Future versioned history parents
    must explicitly bind this METHOD/RESULT_KIND, not relabel it as the old V1
    preparation. This verifies retained producer bindings; it does not replay the
    entire frame or reopen source/history owners on historical reuse.
    """
    require_active(engine, session)
    require(engine.config.offline, "offline_completed_reader")
    original.source._sha(preparation_record)
    value = engine.ledger.get(preparation_record, RESULT_KIND)
    validate_binding(value["binding"])
    result_rows = list(engine.ledger.db.execute("SELECT id,logical_key FROM records WHERE kind=?", (RESULT_KIND,)))
    intent_rows = list(engine.ledger.db.execute("SELECT id,logical_key FROM records WHERE kind=?", (INTENT_KIND,)))
    require(len(result_rows) == len(intent_rows) == 1 and result_rows[0]["id"] == preparation_record
        and result_rows[0]["logical_key"] == intent_rows[0]["id"] == value["preparation_intent"]
        and intent_rows[0]["logical_key"] == METHOD, "completed_unique_producer_result")
    require(value.get("method") == METHOD and value.get("implementation") == implementation()
        and digest({key: value.get(key) for key in POLICY}) == digest(POLICY)
        and value.get("snapshot_method") == snapshot_parent.METHOD
        and value.get("inventory_method") == inventory.METHOD
        and value.get("labels_requested") == 0 and type(value.get("labels_requested")) is int
        and value.get("final_sample_selected") is False, "completed_method_policy")
    selected = value["binding"]
    snapshot, index = snapshot_parent.load_snapshot(engine, session, selected["snapshot_binding"])
    authority = snapshot["parent_authority"]["binding"]
    require(all(authority[key] == selected[key] for key in ("study_record", "seed_record")), "completed_original_study_binding")
    registration = engine.ledger.get(selected["study_record"], original.STUDY)
    intent = engine.ledger.get(value["preparation_intent"], INTENT_KIND)
    require(intent == {"method": METHOD, "binding": selected, "implementation": value["implementation"],
        "policy": POLICY, "original_study_artifact": digest(registration),
        "registered_specification_artifact": registration["specification_artifact"]}, "completed_intent_binding")
    require(set(value["versions"]) == {"protocol", "selection", "policy"}, "completed_versions")
    for kind, identity in value["versions"].items():
        content = engine.ledger.get(identity, kind)["content"]
        require(content.get("binding_sha256") == digest(selected), "completed_protocol_binding")
        if kind == "protocol":
            require(content.get("method") == METHOD and content.get("implementation") == value["implementation"]
                and content.get("preparation_intent") == value["preparation_intent"], "completed_registered_method")
        elif kind == "policy":
            require(digest({key: content.get(key) for key in POLICY}) == digest(POLICY)
                and content.get("preparation_intent") == value["preparation_intent"], "completed_registered_policy")
    token = engine.ledger.get(value["tokenizer_record"], TOKENIZER_KIND)
    require(token.get("method") == METHOD and token.get("preparation_intent") == value["preparation_intent"], "completed_tokenizer_binding")
    inventory_value = engine.ledger.get(value["inventory"]["inventory_record"], inventory.RESULT_KIND)
    require(digest(inventory_value) == value["inventory"]["inventory_artifact"]
        and inventory_value.get("method") == inventory.METHOD
        and inventory_value.get("implementation") == inventory.implementation()
        and inventory_value["snapshot_binding"] == selected["snapshot_binding"]
        and inventory_value["source_bindings"] == snapshot["source_bindings"]
        and inventory_value["input_index_digest"] == index.digest
        and inventory_value["original_study_record"] == selected["study_record"]
        and inventory_value["original_seed_record"] == selected["seed_record"]
        and inventory_value["full_source_ledger_preflight_verified"] is True
        and inventory_value["source_head_stable"] is True, "completed_inventory_binding")
    require(set(inventory_value["versions"]) == {"protocol", "selection"}, "completed_inventory_versions")
    for kind, identity in inventory_value["versions"].items():
        content = engine.ledger.get(identity, kind)["content"]
        require(content.get("snapshot_binding_sha256") == digest(selected["snapshot_binding"])
            and content.get("preparation_intent") == value["preparation_intent"]
            and content.get("preparation_protocol") == value["versions"]["protocol"], "completed_inventory_protocol")
        if kind == "protocol":
            require(content.get("method") == inventory.METHOD
                and content.get("implementation") == inventory.implementation(), "completed_inventory_method")
    seeds = engine.ledger.get(selected["seed_record"], original.SEEDS)
    require(all(value[key] == seeds[key] for key in ("schedule_seed_artifact", "article_order_seed_artifact")), "completed_seeds_changed")
    require(value["retained_artifacts"] == sorted(set(value["retained_artifacts"])), "completed_artifact_partition")
    for reference in value["retained_artifacts"]:
        engine.ledger.artifacts.read_bytes(reference)
    expected_refs = {value["frame_manifest_artifact"], value["schedule_artifact"], *value["contributions"].values()}
    require(expected_refs <= set(value["retained_artifacts"]), "completed_outputs_not_retained")
    manifest = engine.ledger.artifacts.read(value["frame_manifest_artifact"])
    schedule = engine.ledger.artifacts.read(value["schedule_artifact"])
    require(manifest["implementation"] == pipeline.implementation() and manifest["input_index_digest"] == index.digest
        and manifest["frame_digest"] == value["frame_digest"] and manifest["schedule_digest"] == value["schedule_digest"]
        and manifest["artifact_references"]["schedule"] == value["schedule_artifact"]
        and digest(schedule) == value["schedule_digest"]
        and schedule["seed_binding"] == {"record": selected["seed_record"], "artifact": seeds["schedule_seed_artifact"]}
        and schedule["seed_content"] == engine.ledger.artifacts.read(seeds["schedule_seed_artifact"]), "completed_frame_schedule_binding")
    replay = engine.ledger.artifacts.read(value["contributions"]["embedding_replay"])
    history = engine.ledger.artifacts.read(value["contributions"]["pair_history_inventory"])
    require(manifest["artifact_references"]["embedding_proof"] == value["contributions"]["embedding_replay"]
        and replay["input_index_digest"] == index.digest and history["complete"] is False
        and history["global_gap"] is True, "completed_provenance_scope")
    read = engine.ledger.artifacts.read
    refs = manifest["artifact_references"]
    derivation = read(refs["derivation"])
    require(derivation["version"] == pipeline.VERSION and derivation["implementation"] == pipeline.implementation()
        and all(derivation["bindings"][key] == selected["snapshot_binding"][key] for key in selected["snapshot_binding"])
        and derivation["cutoff"] == pipeline.cutoff_binding(index, derivation["bindings"])
        and derivation["embedding_proof"] == derivation["bindings"]["embedding_proof_artifact"] == value["contributions"]["embedding_replay"],
        "completed_derivation_cutoff")
    expected_inputs = [{"document_id": d.document_id, "input_sha256": d.input_sha256,
        "article_row_ids": list(d.article_row_ids), "accepted_dossier_id": d.accepted_dossier_id} for d in index.inputs]
    require(read(refs["input_index"]) == {"bindings": dict(index.bindings), "digest": index.digest, "inputs": expected_inputs},
        "completed_original_input_index")
    candidate = read(refs["candidate_metadata"])
    role_catalog = read(value["contributions"]["role_catalog"])
    role_metadata = read(value["contributions"]["role_metadata"])
    candidate_inventory = read(derivation["bindings"]["candidate_inventory_artifact"])
    require(derivation["candidate_metadata"] == refs["candidate_metadata"]
        and derivation["candidate_projection"] == refs["candidate_projection"]
        and candidate["inventory_sha256"] == digest(candidate_inventory)
        and candidate["role_artifact"] == role_metadata["role_artifact"] == candidate_inventory["role_artifact"]
        and role_metadata["catalog_artifact"] == value["contributions"]["role_catalog"]
        and role_catalog["census_artifact"] == inventory_value["census_artifact"]
        and all(candidate_inventory[key] == role_catalog[key] for key in ("source_id", "source_head", "plan", "input_index_digest"))
        and candidate["input_index_digest"] == index.digest, "completed_candidate_derivation")
    prior_certificate = read(value["contributions"]["prior_inventory"])
    observations = read(value["contributions"]["prior_observations"])
    prior_manifest = read(value["contributions"]["prior_manifest"])
    prior_result = projection.project_prior_exposure(index, observations, inventory_certificate=prior_certificate)
    prior_scope = read(derivation["bindings"]["prior_inventory_artifact"])
    require(derivation["prior_projection"] == refs["prior_projection"] == digest(prior_result.metadata)
        and prior_certificate["study_inventory_sha256"] == digest(prior_scope)
        and prior_certificate["cutoff_binding_sha256"] == digest(derivation["cutoff"])
        and prior_certificate["sources"] == [read(value["contributions"]["prior_source_contribution"])]
        and prior_manifest["input_index_digest"] == index.digest
        and prior_manifest["observations_sha256"] == digest(observations)
        and prior_manifest["role_catalog_sha256"] == value["contributions"]["role_catalog"]
        and prior_certificate["sources"][0]["inventory_sha256"] == value["contributions"]["prior_manifest"]
        and prior_scope == {"method": METHOD, "snapshot_binding": selected["snapshot_binding"],
            "main_contribution": value["contributions"]["prior_manifest"], "scope_complete": False,
            "unresolved_scope": ["cross_owner_manual_and_unsupported_history"]}, "completed_prior_derivation")
    pair_records = read(value["contributions"]["pair_history_records"])
    pair_manifest = read(value["contributions"]["pair_history_manifest"])
    source_certificate = read(inventory_value["pair_inventory_artifact"])
    require(history["binding_sha256"] == value["contributions"]["pair_history_manifest"]
        and pair_manifest["records_sha256"] == digest(pair_records)
        and pair_manifest["role_catalog_sha256"] == value["contributions"]["role_catalog"]
        and pair_manifest["prior_manifest_sha256"] == value["contributions"]["prior_manifest"]
        and pair_manifest["source_certificate_sha256"] == digest(source_certificate)
        and pair_manifest["census_artifact"] == inventory_value["census_artifact"]
        and pair_manifest["input_index_digest"] == index.digest
        and all(pair_manifest[key] == source_certificate[key] for key in ("source_id", "source_head")),
        "completed_pair_history_derivation")
    profile = read(value["contributions"]["embedding_profile_evidence"])
    phases = read(inventory_value["phase_records_artifact"])
    phase = [row for row in phases if row["id"] == replay["phase_record"]]
    require(len(phase) == 1 and phase[0]["logical_key"] == "embeddings"
        and json.loads(phase[0]["payload"])["artifact"] == replay["phase_artifact"]
        and replay["source_head"] == snapshot["source_bindings"]["source_head"]
        and replay["plan"] == profile["plan_record"] == snapshot["source_bindings"]["plan"]
        and replay["profile_record"] == profile["record"]["_record_id"]
        and profile["record"]["content"] == embedding.vectors.PROFILE
        and replay["inventory_sha256"] == inventory_value["census_artifact"], "completed_embedding_source_binding")
    counts = {"unique_inputs": len(index.inputs), "article_rows": snapshot["article_rows"],
        "alias_rows": snapshot["alias_rows"], "total_pairs": manifest["total_pairs"], "strata": len(manifest["strata"]),
        "pooled_inputs": replay["pooled_inputs"], "missing_vector_inputs": replay["missing_inputs"],
        "physical_attempts": inventory_value["physical_attempts"],
        "main_prior_observations": len(observations),
        "main_pair_history_records": len(pair_records)}
    require(digest(value["counts"]) == digest(counts), "completed_counts")
    rows = {}
    for kind, identity in ((INTENT_KIND, value["preparation_intent"]), (TOKENIZER_KIND, value["tokenizer_record"]),
            (inventory.RESULT_KIND, value["inventory"]["inventory_record"]), (RESULT_KIND, preparation_record)):
        row = engine.ledger.db.execute("SELECT id,created_event FROM records WHERE kind=? AND id=?", (kind, identity)).fetchone()
        require(row is not None, "completed_record_required")
        rows[kind] = row["created_event"]
    require(rows[INTENT_KIND] < rows[TOKENIZER_KIND] < rows[inventory.RESULT_KIND] < rows[RESULT_KIND], "completed_evidence_order")
    return value, snapshot, index


class Preparation(original.Study):
    """Explicit new entrypoint; initialization/freeze/model operations unavailable.

    The original Study registration must already exist in this protected owner.
    Repeating prepare reuses only an identical completed result. An interrupted
    operation may recompute the same fixed cutoff/configuration, using the same
    seeds. Changed bindings/code require a separately reviewed amendment.
    """

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        payload = payload or {}
        require(operation == "status" and not versions, "offline_operations_only")
        require(payload.get("action") in {"prepare", "status"}
            and set(payload) == {"action", "binding"}, "operation_shape")
        validate_binding(payload["binding"])
        return Research.execute(self, "status", {"method": METHOD, **payload},
            objective=objective, actor=actor)

    def _bound_study(self, selected, session):
        registered = self._registration()
        require(registered["id"] == selected["study_record"]
            and registered["payload"]["seed_record"] == selected["seed_record"], "study_or_seed_changed")
        snapshot, index = snapshot_parent.load_snapshot(self, session, selected["snapshot_binding"])
        authority = snapshot["parent_authority"]["binding"]
        require(authority["study_record"] == registered["id"]
            and authority["seed_record"] == selected["seed_record"]
            and authority["source_bindings"] == snapshot["source_bindings"], "v11_freeze_binding")
        return registered, snapshot, index

    def _summary(self, row, *, reused):
        value = row["payload"]
        # Verify retained outputs on repeat without reopening source owners.
        for reference in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        return {"preparation_record": row["id"], "preparation_artifact": digest(value),
            "method": METHOD, **POLICY, "study_record": value["binding"]["study_record"],
            "seed_record": value["binding"]["seed_record"],
            "snapshot_binding": value["binding"]["snapshot_binding"],
            "inventory_record": value["inventory"]["inventory_record"],
            "frame_manifest_artifact": value["frame_manifest_artifact"],
            "frame_digest": value["frame_digest"], "schedule_artifact": value["schedule_artifact"],
            "schedule_digest": value["schedule_digest"], "counts": value["counts"],
            "contributions": value["contributions"], "reused_historical_preparation": reused,
            "current_source_quiescence_verified": False,
            "source_quiescence_verified_during_census": not reused,
            "pending": ["cross_owner_and_manual_history_reconciliation", "final_statistical_frame",
                "exact_slot_and_resource_preparation", "separately_registered_account_admission"]}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry_required")
        selected = data["binding"]
        registered, snapshot, index = self._bound_study(selected, session)
        code = implementation()
        desired = {"method": METHOD, "binding": selected, "implementation": code,
            "policy": POLICY, "original_study_artifact": digest(registered["payload"]),
            "registered_specification_artifact": registered["payload"]["specification_artifact"]}
        old = self._one(INTENT_KIND, optional=True)
        if old:
            require(old["payload"] == desired, "changed_preparation_requires_amendment")
        result = self._one(RESULT_KIND, optional=True)
        if result:
            require(old is not None and result["payload"]["preparation_intent"] == old["id"]
                and result["payload"]["implementation"] == code
                and result["payload"]["binding"] == selected, "completed_preparation_binding")
            load_completed(self, session, result["id"])
            return self._summary(result, reused=True)
        if data["action"] == "status":
            return {"method": METHOD, **POLICY, "prepared": False,
                "incomplete_preparation": old is not None, "current_source_quiescence_verified": False}
        require(type(self.observer) is original.WindowsProcessObserver, "concrete_process_observer_required")
        intent_id = old["id"] if old else self.ledger.record(session, INTENT_KIND, METHOD, desired)
        versions = {}
        for kind, content in {"protocol": {"method": METHOD, "implementation": code,
                "preparation_intent": intent_id, "binding_sha256": digest(selected),
                "additional_source_metadata_scope": "exact-original-plan-versions.embedding_profile-record-only"},
                "selection": {"rules": "Entire frozen input frame; actual main-owner evidence; unresolved cross-study scope.",
                    "binding_sha256": digest(selected)},
                "policy": {"mode": "offline-intermediate-preparation-only", **POLICY,
                    "preparation_intent": intent_id, "binding_sha256": digest(selected)}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD, content)
        token_content = {"encoding": "cl100k_base", "library": "tiktoken",
            "version": importlib.metadata.version("tiktoken")}
        # Local cache/configuration checked before the source owner opens. No
        # network tokenizer download and no user-supplied fake count callback.
        token_evidence = {"method": METHOD, "preparation_intent": intent_id,
            "identity": token_content, "vocabulary_sha256": VOCAB_HASH,
            "configuration_sha256": original.packets._tokenizer_configuration_digest(
                original.packets._tokenizer_configuration())}
        token_id = self.ledger.record(session, TOKENIZER_KIND, intent_id, token_evidence)
        counter = original.packets.load_token_counter(evidence_record=token_id, expected_identity=token_content)
        require(counter.validate() == token_evidence["configuration_sha256"], "tokenizer_identity")
        source_versions = {}
        for kind in ("protocol", "selection"):
            content = {"snapshot_binding_sha256": digest(selected["snapshot_binding"]),
                "preparation_intent": intent_id, "preparation_protocol": versions["protocol"]}
            if kind == "protocol":
                content.update(method=inventory.METHOD, implementation=inventory.implementation())
            else:
                content["rules"] = "Complete immutable main-owner census under the registered final cutoff."
            source_versions[kind] = self._version_once(session, context, kind, METHOD + ":inventory", content)
        scoped = Context(context.objective, context.actor, source_versions)
        retained = set()

        def put(value):
            ref = self.ledger.artifacts.put(value)
            retained.add(ref)
            return ref

        with inventory.open_attempt_inventory(self, session, scoped, selected["snapshot_binding"],
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            require(reader.index == index, "inventory_index_changed")
            documents = []
            metadata = self.ledger.artifacts.read(snapshot["documents_artifact"])
            for row in metadata:
                document = self.ledger.artifacts.read(row["document_artifact"])
                request = self.ledger.artifacts.read(row["screening_request_hash"])
                original.source._exact_document(row, document, request, original.source.INPUT_METHOD)
                documents.append(document)
            require([d["document_id"] for d in documents] == [d.document_id for d in index.inputs], "complete_input_order")
            resolution = roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in documents},
                count_tokens=counter.count, tokenizer_binding=digest(token_evidence))
            for ref, raw in resolution.additions.items():
                require(self.ledger.artifacts.put_bytes(raw) == ref, "role_artifact_changed")
                retained.add(ref)
            main_prior = prior.normalize_main_owner_prior(reader, resolution)
            history = pair_history.normalize_main_owner_pair_history(reader, resolution)
            contributions = {"role_catalog": put(resolution.catalog), "role_metadata": put(resolution.metadata),
                "prior_observations": put(list(main_prior.observations)), "prior_manifest": put(main_prior.manifest),
                "prior_source_contribution": put(main_prior.source_contribution),
                "pair_history_records": put(list(history.records)), "pair_history_manifest": put(history.manifest),
                "pair_history_inventory": put(history.inventory_certificate)}
            require(history.inventory_certificate["complete"] is False
                and history.inventory_certificate["global_gap"] is True, "history_must_remain_incomplete")
            plan = reader.source.one("cyber_dossier_plan", reader.certificate["plan"])
            profile_id = plan.get("versions", {}).get("embedding_profile")
            original.source._sha(profile_id)
            # Explicit NEW protocol scope: frozen Source.rows deliberately has a
            # smaller allowlist. Read only the exact plan-selected version from
            # its same verified private clone; _row verifies artifact/creation.
            profile_row = reader.source.db.execute("SELECT * FROM records WHERE kind='embedding_profile' AND id=?",
                (profile_id,)).fetchone()
            require(profile_row is not None, "plan_profile_record_unavailable")
            profile = reader.source._row(profile_row)
            require(profile["content"] == embedding.vectors.PROFILE
                and profile["_created_event"] < plan["_created_event"], "profile_plan_binding")
            contributions["embedding_profile_evidence"] = put({"record": profile,
                "plan_record": plan["_record_id"], "plan_artifact": plan["_artifact"]})
            phase_matches = [(row, event) for row, event in zip(reader.phase_records, reader.phase_events, strict=True)
                if row["logical_key"] == "embeddings"]
            require(len(phase_matches) == 1, "unique_embedding_phase")
            phase_row, phase_event = phase_matches[0]
            phase_value = reader.source.artifact(phase_row["artifact"])
            input_bindings = [{"document_id": d.document_id, "input_sha256": d.input_sha256} for d in index.inputs]
            embedding_bindings = {"source_head": digest(reader.certificate["source_head"]),
                "plan": reader.certificate["plan"], "phase_record": phase_row["id"],
                "phase_artifact": phase_value["artifact"], "profile_record": profile_id,
                "profile_sha256": digest(profile["content"]), "input_manifest": dict(index.bindings)["input_manifest"],
                "input_bindings_artifact": put(input_bindings)}
            replay = embedding.verify_embedding_provenance(index, documents, counter.encoder,
                events=reader.events, records=reader.records, artifacts=reader.artifacts,
                inventory=self.ledger.artifacts.read(reader.counts["census_artifact"]),
                phase_record=phase_row, phase_creation_event=phase_event, profile=profile["content"],
                bindings=embedding_bindings, tokenizer={**token_content,
                    "vocabulary_sha256": VOCAB_HASH, "verification_record": token_id})
            contributions["embedding_replay"] = put(replay.metadata)
            candidate = resolution.exposure_arguments(reader)
            candidate_ref = put(candidate["inventory"])
            scope = {"method": METHOD, "snapshot_binding": selected["snapshot_binding"],
                "main_contribution": contributions["prior_manifest"], "scope_complete": False,
                "unresolved_scope": ["cross_owner_manual_and_unsupported_history"]}
            scope_ref = put(scope)
            frame_bindings = {**selected["snapshot_binding"], "candidate_inventory_artifact": candidate_ref,
                "prior_inventory_artifact": scope_ref, "embedding_proof_artifact": replay.digest}
            prior_certificate = {"scope_statement": projection.PRIOR_SCOPE, "scope_complete": False,
                "required_source_ids": [main_prior.source_contribution["source_id"]],
                "study_inventory_sha256": scope_ref,
                "cutoff_binding_sha256": digest(pipeline.cutoff_binding(index, frame_bindings)),
                "input_index_digest": index.digest, "sources": [main_prior.source_contribution]}
            contributions["prior_inventory"] = put(prior_certificate)
            seeds = self.ledger.get(selected["seed_record"], original.SEEDS)
            seed_payload = self.ledger.artifacts.read(seeds["schedule_seed_artifact"])
            prepared = pipeline.assemble_frame(index, candidate_inputs=candidate,
                prior_inputs={"observations": list(main_prior.observations), "inventory_certificate": prior_certificate},
                embeddings=replay, bindings=frame_bindings, seeds=seed_payload["seeds"],
                seed_binding={"record": selected["seed_record"], "artifact": seeds["schedule_seed_artifact"]},
                **selected["limits"])
            for ref, raw in prepared.artifacts:
                require(self.ledger.artifacts.put_bytes(raw) == ref, "frame_artifact_changed")
                retained.add(ref)
            counts = {"unique_inputs": len(index.inputs), "article_rows": snapshot["article_rows"],
                "alias_rows": snapshot["alias_rows"], "total_pairs": prepared.manifest["total_pairs"],
                "strata": len(prepared.frame.strata), "pooled_inputs": replay.metadata["pooled_inputs"],
                "missing_vector_inputs": replay.metadata["missing_inputs"],
                "physical_attempts": reader.counts["physical_attempts"],
                "main_prior_observations": len(main_prior.observations),
                "main_pair_history_records": len(history.records)}
        # Result is written only after source fresh-head/liveness checks complete.
        require(reader.result is not None and implementation() == code, "verification_or_implementation_changed")
        record = {"method": METHOD, **POLICY, "binding": selected, "implementation": code,
            "versions": versions, "preparation_intent": intent_id, "tokenizer_record": token_id,
            "inventory_method": inventory.METHOD, "snapshot_method": snapshot_parent.METHOD,
            "inventory": reader.result, "contributions": contributions, "counts": counts,
            "frame_manifest_artifact": prepared.digest, "frame_digest": prepared.frame.digest,
            "schedule_artifact": prepared.manifest["artifact_references"]["schedule"],
            "schedule_digest": prepared.schedule.digest, "retained_artifacts": sorted(retained),
            "schedule_seed_artifact": seeds["schedule_seed_artifact"],
            "article_order_seed_artifact": seeds["article_order_seed_artifact"],
            "labels_requested": 0, "final_sample_selected": False,
            "limitations": "Verified fixed-cutoff main-owner composition only. Cross-owner/manual and unsupported prior histories remain unresolved. Provisional P strata/schedule cannot authorize packet preparation or judging. A later reconciled frame must use the unchanged registered seeds; hashes are local audit bindings, not external attestation."}
        identifier = self.ledger.record(session, RESULT_KIND, intent_id, record)
        load_completed(self, session, identifier)
        return self._summary(self._one(RESULT_KIND), reused=False) | {"preparation_record": identifier}
