"""Audited OFFLINE intermediate main-owner frame preparation, never admission.

This NEW operation composes the already registered Study and its frozen final
snapshot with an actual locked/preflighted main-owner census, role reconciliation
and original embedding replay. It cannot certify cross-owner/manual history.
The resulting frame/schedule are explicitly provisional: later reconciliation
must rebuild with the SAME retained seeds, not activate this incomplete frame.
No CLI, model transport, automatic source selection or mutable code amendment.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path

import final_validation_embedding_provenance as embedding
import final_validation_frame_pipeline as pipeline
import final_validation_inventory as inventory
import final_validation_pair_history as pair_history
import final_validation_prior as prior
import final_validation_projection as projection
import final_validation_roles as roles
import final_validation_study as original
from newsresearch.common import AuditError, Context, digest
from newsresearch.embeddings import VOCAB_HASH
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-intermediate-main-frame-preparation-v1"
INTENT_KIND = "cyber_final_validation_frame_preparation_intent"
RESULT_KIND = "cyber_final_validation_frame_preparation"
TOKENIZER_KIND = "cyber_final_validation_preparation_tokenizer"
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

    def _bound_study(self, selected):
        registered = self._registration()
        require(registered["id"] == selected["study_record"]
            and registered["payload"]["seed_record"] == selected["seed_record"], "study_or_seed_changed")
        snapshot, index = inventory._snapshot(self, selected["snapshot_binding"])
        freeze = self._one(original.FREEZE)
        require(freeze["payload"]["study_record"] == registered["id"]
            and freeze["payload"]["seed_record"] == selected["seed_record"]
            and freeze["payload"]["source_bindings"] == snapshot["source_bindings"]
            and self._one(original.SEEDS)["created_event"] < freeze["created_event"], "original_freeze_binding")
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
            "current_source_quiescence_verified": not reused,
            "pending": ["cross_owner_and_manual_history_reconciliation", "final_statistical_frame",
                "exact_slot_and_resource_preparation", "separately_registered_account_admission"]}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry_required")
        selected = data["binding"]
        registered, snapshot, index = self._bound_study(selected)
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
            "inventory": reader.result, "contributions": contributions, "counts": counts,
            "frame_manifest_artifact": prepared.digest, "frame_digest": prepared.frame.digest,
            "schedule_artifact": prepared.manifest["artifact_references"]["schedule"],
            "schedule_digest": prepared.schedule.digest, "retained_artifacts": sorted(retained),
            "schedule_seed_artifact": seeds["schedule_seed_artifact"],
            "article_order_seed_artifact": seeds["article_order_seed_artifact"],
            "labels_requested": 0, "final_sample_selected": False,
            "limitations": "Verified fixed-cutoff main-owner composition only. Cross-owner/manual and unsupported prior histories remain unresolved. Provisional P strata/schedule cannot authorize packet preparation or judging. A later reconciled frame must use the unchanged registered seeds; hashes are local audit bindings, not external attestation."}
        identifier = self.ledger.record(session, RESULT_KIND, intent_id, record)
        return self._summary(self._one(RESULT_KIND), reused=False) | {"preparation_record": identifier}
