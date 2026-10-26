"""Audited final frame and exact initial-slot authority; offline, no dispatch.

Only retained Study/preparation/reconciliation evidence is accepted. This closes
the packet helper's source/seed/history authority boundary, not missing history:
the current conservative certificate is copied unchanged. No hypothetical closure
record, caller labels, sources, completeness flags or replacement slots are read.
"""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_admission as admission
import final_validation_execution as execution
import final_validation_frame_pipeline as pipeline
import final_validation_packets as packets
import final_validation_preparation as preparation
import final_validation_reconciliation as reconciliation
import final_validation_source as source
import final_validation_source_lineage as lineage
import final_validation_study as study
from newsresearch.common import AuditError, Context, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-final-frame-and-packet-authority-v1"
INTENT = "cyber_final_validation_final_frame_intent"
SCOPE = "cyber_final_validation_final_scope_disposition"
FRAME = "cyber_final_validation_final_frame"
SLOT_INTENT = "cyber_final_validation_initial_slot_intent"
SLOTS = "cyber_final_validation_verified_initial_slots"
POLICY = {"offline_only": True, "model_dispatch_authorized": False, "new_model_calls": 0,
    "source_mutations": 0, "new_seed_draws": 0, "universal_history_completeness_claimed": False,
    "unknown_prior_exposure_remains_stratum": True, "unknown_reference_history_blocks_affected_slots": True,
    "no_redraw_or_substitution": True, "task_scope_closure_supported": False}


def require(value, reason):
    if not value:
        raise AuditError("final_packet_parent_" + reason)


def implementation():
    code = {}
    for module in (reconciliation, admission, pipeline):
        code.update(module.implementation())
    path = Path(__file__)
    code[path.relative_to(study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def frame_binding(*, preparation_binding, reconciliation_record):
    reconciliation.validate_binding(preparation_binding)
    execution.sha(reconciliation_record)
    return {"preparation_binding": deepcopy(preparation_binding), "reconciliation_record": reconciliation_record}


def slot_binding(*, final_frame_record, runtime_record, quota_record, resource_policy_record):
    value = {"final_frame_record": final_frame_record, "runtime_record": runtime_record,
        "quota_record": quota_record, "resource_policy_record": resource_policy_record}
    for reference in value.values():
        execution.sha(reference)
    return value


class PacketParent(reconciliation.Reconciliation):
    """No initialize, execution or generic registration operations are exposed.

    Finalizing current incomplete history is deliberately conservative: all
    affected slots stay unavailable. Actual use should finish planned history
    work first. Changed scope after finalization requires an explicit amendment,
    never a silent second draw or a new certificate supplied by a caller.
    """

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "binding"}, "offline_operation")
        if data["action"] in {"freeze_final_frame", "frame_status"}:
            require(set(data["binding"]) == {"preparation_binding", "reconciliation_record"}, "frame_binding_fields")
            frame_binding(**data["binding"])
        else:
            require(data["action"] in {"prepare_initial_slots", "slot_status"}, "offline_action")
            require(set(data["binding"]) == {"final_frame_record", "runtime_record", "quota_record",
                "resource_policy_record"}, "slot_binding_fields")
            slot_binding(**data["binding"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _chain(self, binding):
        selected = binding["preparation_binding"]
        snapshot, index, prepared = self._prepared(selected)
        require(self._one(reconciliation.RESULT_KIND)["id"] == binding["reconciliation_record"], "unique_reconciliation_result")
        value = self.ledger.get(binding["reconciliation_record"], reconciliation.RESULT_KIND)
        require(value["method"] == reconciliation.METHOD and value["binding"] == selected
            and value["implementation"] == reconciliation.implementation()
            and all(value.get(k) == v for k, v in reconciliation.POLICY.items()), "reconciliation_binding")
        intended = self.ledger.get(value["reconciliation_intent"], reconciliation.INTENT_KIND)
        require(intended["binding"] == selected and intended["implementation"] == value["implementation"]
            and intended["preparation_artifact"] == digest(prepared), "reconciliation_intent")
        protocol = self.ledger.get(value["versions"]["protocol"], "protocol")["content"]
        require(protocol["method"] == reconciliation.METHOD and protocol["implementation"] == value["implementation"]
            and protocol["reconciliation_intent"] == value["reconciliation_intent"]
            and protocol["binding_sha256"] == digest(selected), "reconciliation_protocol")
        for reference in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        registry = self.ledger.artifacts.read(value["registry_artifact"])
        require(digest(registry) == intended["registry_sha256"] == protocol["registry_sha256"], "registry_binding")
        reconciliation.validate_registry(registry, index, main_owner=self.source_owner, observer_owner=self.ledger.root.resolve())
        proof = self.ledger.get(value["inventory"]["inventory_record"], reconciliation.inventory.RESULT_KIND)
        require(digest(proof) == value["inventory"]["inventory_artifact"]
            and proof["binding"]["snapshot_binding"] == selected["snapshot_binding"]
            and proof["binding"]["owners"] == registry["owners"]
            and proof["binding"]["declared_gaps"] == registry["declared_gaps"]
            and proof["source_head_stable"] and proof["full_declared_source_ledger_preflight_verified"], "registry_census_proof")
        require(proof["main_final_cutoff_guard"]["source_head"] == snapshot["source_bindings"]["source_head"]
            and proof["main_final_cutoff_guard"]["head_stable"], "main_cutoff_proof")
        for key in ("schedule_seed_artifact", "article_order_seed_artifact"):
            require(value[key] == prepared[key], "original_seed_changed")
        return snapshot, index, prepared, value, registry, proof

    def _scope(self, binding, chain):
        snapshot, index, prepared, value, registry, proof = chain
        # Generic declared gaps are not proof that the omitted source was read
        # and unavailable. A pending/manual source cannot be frozen away by a
        # caller-selected status or a plausible-looking reason string.
        require(not registry["declared_gaps"], "declared_unprocessed_scope_blocks_finalization")
        expected = {digest(s["source_owner"]): s for s in registry["owners"]}
        require(len(proof["owners"]) == len(expected)
            and {item["census"]["owner_sha256"] for item in proof["owners"]} == set(expected), "scope_census_coverage")
        dispositions = [{"source": "main", "source_owner_sha256": digest(str(self.source_owner)),
            "head": snapshot["source_bindings"]["source_head"],
            "inventory_record": prepared["inventory"]["inventory_record"],
            "state": "inspected_with_unresolved_formats", "missingness": "global_unknown"}]
        for item in proof["owners"]:
            owner = item["census"]["owner_sha256"]
            require(owner in expected and item["census"]["source_head"] == expected[owner]["source_head"], "owner_census_binding")
            dispositions.append({"source": "declared_external", "source_owner_sha256": owner,
                "head": expected[owner]["source_head"], "census_sha256": digest(item["census"]),
                "state": "inspected_with_unresolved_formats", "missingness": "global_unknown"})
        return {"method": METHOD, "binding": binding, "input_index_digest": index.digest,
            "registry_artifact": value["registry_artifact"], "registry_inventory_record": value["inventory"]["inventory_record"],
            "retained_gap_artifact": value["artifacts"]["gaps"], "source_dispositions": dispositions,
            "known_declared_unprocessed_sources": 0, "declared_registry_inspected": True,
            "never_enumerated_history": "unverified_global_unknown", "prior_scope_complete": False,
            "no_retry_scope_complete": False, "scope_policy": POLICY,
            "limitations": "Finalizes evidence and explicit unknowns for this inspected declared registry only. Never-enumerated/manual history and unsupported task formats remain global uncertainty. No new task-scope closure is inferred."}

    def _documents(self, snapshot, index):
        rows = self.ledger.artifacts.read(snapshot["documents_artifact"])
        documents = []
        for row in rows:
            document = self.ledger.artifacts.read(row["document_artifact"])
            request = self.ledger.artifacts.read(row["screening_request_hash"])
            source._exact_document(row, document, request, source.INPUT_METHOD)
            documents.append(document)
        require([d["document_id"] for d in documents] == [d.document_id for d in index.inputs], "full_input_order")
        return documents

    @contextmanager
    def _commit_guard(self, session, snapshot, registry):
        """Hold all exact source cutoffs while committing a parent result."""
        require(type(self.observer) is study.WindowsProcessObserver, "concrete_observer")
        scopes = [(self.source_owner, snapshot["source_bindings"]["source_head"])]
        scopes += [(Path(s["source_owner"]), s["source_head"]) for s in registry["owners"]]
        with ExitStack() as stack:
            opened = []
            for owner, head in scopes:
                before = source._liveness(lambda path: self.observer.observe(self, session, path), owner)
                source._retained_liveness(self, before)
                api = lineage.source_api(snapshot) if owner == self.source_owner else source
                reader = api.Source(self, session, owner)
                stack.callback(reader.close)
                require(reader.head() == head, "final_commit_cutoff_changed")
                opened.append((reader, head))
            # Fresh copies and observed liveness checked with every exclusion
            # lock still held. The following durable commit occurs under locks.
            for reader, head in opened:
                observed = source._liveness(lambda path: self.observer.observe(self, session, path), reader.owner)
                source._retained_liveness(self, observed)
                require(reader.head(fresh=True) == head, "final_commit_source_changed")
            yield

    def _compose(self, session, context, binding, chain, protocol, retained):
        snapshot, index, prepared, reconciled, _, _ = chain
        selected = binding["preparation_binding"]
        selected_preparation = lineage.preparation_module(self, selected["preparation_record"], selected["snapshot_binding"])
        selected_inventory = selected_preparation.inventory
        token_id = prepared["tokenizer_record"]
        token = self.ledger.get(token_id, selected_preparation.TOKENIZER_KIND)
        require(token["method"] == selected_preparation.METHOD
            and token["preparation_intent"] == prepared["preparation_intent"], "original_tokenizer_evidence")
        counter = packets.load_token_counter(evidence_record=token_id, expected_identity=token["identity"])
        require(counter.validate() == token["configuration_sha256"], "original_tokenizer_binding")
        versions = {}
        for kind in ("protocol", "selection"):
            content = {"snapshot_binding_sha256": digest(selected["snapshot_binding"]), "parent_protocol": protocol}
            content.update({"method": selected_inventory.METHOD, "implementation": selected_inventory.implementation()}
                if kind == "protocol" else {"rules": "Reverify entire fixed main cutoff; unchanged input/roles/embedding producer."})
            versions[kind] = self._version_once(session, context, kind, METHOD + ":inventory", content)
        with selected_inventory.open_attempt_inventory(self, session, Context(context.objective, context.actor, versions),
                selected["snapshot_binding"], observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            require(reader.index == index, "replayed_index_changed")
            documents = self._documents(snapshot, index)
            resolution = preparation.roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in documents},
                count_tokens=counter.count, tokenizer_binding=digest(token))
            require(digest(resolution.catalog) == prepared["contributions"]["role_catalog"], "replayed_role_catalog_changed")
            for ref, raw in resolution.additions.items():
                require(self.ledger.artifacts.put_bytes(raw) == ref, "role_bytes_changed")
                retained.add(ref)
            plan = reader.source.one("cyber_dossier_plan", reader.certificate["plan"])
            profile_id = plan["versions"]["embedding_profile"]
            # Same explicitly registered plan-selected profile scope as original
            # preparation. No new Source allowlist or arbitrary query parameter.
            row = reader.source.db.execute("SELECT * FROM records WHERE kind='embedding_profile' AND id=?", (profile_id,)).fetchone()
            require(row is not None, "embedding_profile_missing")
            profile = reader.source._row(row)
            require(profile["content"] == preparation.embedding.vectors.PROFILE
                and profile["_created_event"] < plan["_created_event"], "embedding_profile_plan_binding")
            phases = [(row, event) for row, event in zip(reader.phase_records, reader.phase_events, strict=True)
                if row["logical_key"] == "embeddings"]
            require(len(phases) == 1, "unique_original_embedding_phase")
            phase, phase_event = phases[0]
            phase_value = reader.source.artifact(phase["artifact"])
            inputs = [{"document_id": d.document_id, "input_sha256": d.input_sha256} for d in index.inputs]
            replay = preparation.embedding.verify_embedding_provenance(index, documents, counter.encoder,
                events=reader.events, records=reader.records, artifacts=reader.artifacts,
                inventory=self.ledger.artifacts.read(reader.counts["census_artifact"]), phase_record=phase,
                phase_creation_event=phase_event, profile=profile["content"],
                bindings={"source_head": digest(reader.certificate["source_head"]), "plan": reader.certificate["plan"],
                    "phase_record": phase["id"], "phase_artifact": phase_value["artifact"], "profile_record": profile_id,
                    "profile_sha256": digest(profile["content"]), "input_manifest": dict(index.bindings)["input_manifest"],
                    "input_bindings_artifact": self.ledger.artifacts.put(inputs)},
                tokenizer={**token["identity"], "vocabulary_sha256": packets.VOCAB_HASH, "verification_record": token_id})
            require(replay.digest == prepared["contributions"]["embedding_replay"], "original_embedding_replay_changed")
            candidate = resolution.exposure_arguments(reader)
            prior_inputs = {"observations": self.ledger.artifacts.read(reconciled["artifacts"]["prior_observations"]),
                "inventory_certificate": self.ledger.artifacts.read(reconciled["artifacts"]["prior_inventory"])}
            seeds = self.ledger.artifacts.read(prepared["schedule_seed_artifact"])
            result = pipeline.assemble_frame(index, candidate_inputs=candidate, prior_inputs=prior_inputs, embeddings=replay,
                bindings={**selected["snapshot_binding"], "candidate_inventory_artifact": self.ledger.artifacts.put(candidate["inventory"]),
                    "prior_inventory_artifact": prior_inputs["inventory_certificate"]["study_inventory_sha256"],
                    "embedding_proof_artifact": replay.digest}, seeds=seeds["seeds"],
                seed_binding={"record": selected["seed_record"], "artifact": prepared["schedule_seed_artifact"]},
                **prepared["binding"]["limits"])
            for reference, raw in result.artifacts:
                require(self.ledger.artifacts.put_bytes(raw) == reference, "composed_artifact_changed")
                retained.add(reference)
        require(reader.result is not None, "fresh_main_inventory_missing")
        return result, reader.result

    def _frame(self, session, context, data):
        binding, code = data["binding"], implementation()
        chain = self._chain(binding)
        scope = self._scope(binding, chain)
        desired = {"method": METHOD, "binding": binding, "implementation": code, "policy": POLICY, "scope_sha256": digest(scope)}
        prior = self._one(INTENT, optional=True)
        require(prior is None or prior["payload"] == desired, "changed_final_frame_requires_amendment")
        old = self._one(FRAME, optional=True)
        if old:
            require(prior is not None and old["payload"]["intent"] == prior["id"]
                and old["payload"]["implementation"] == code, "retained_final_frame_binding")
            self._load_frame(old["id"])
            return self._frame_summary(old, reused=True)
        if data["action"] == "frame_status":
            return {"final_frame_frozen": False, "incomplete": prior is not None, "dispatch_authorized": False}
        intent = prior["id"] if prior else self.ledger.record(session, INTENT, METHOD, desired)
        versions = {}
        for kind, content in {"protocol": {"method": METHOD, "implementation": code, "binding_sha256": digest(binding),
                "intent": intent, "additional_source_metadata_scope": "exact-original-plan-versions.embedding_profile-record-only"},
                "selection": {"rules": "One complete all-pair frame; exact original seeds; unknown strata preserved.", "intent": intent},
                "policy": {**POLICY, "scope_sha256": digest(scope), "intent": intent}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD, content)
        scope_id = self.ledger.record(session, SCOPE, intent, {**scope, "versions": versions})
        retained = {self.ledger.artifacts.put(scope)}
        frame, fresh_inventory = self._compose(session, context, binding, chain, versions["protocol"], retained)
        require(implementation() == code, "implementation_changed")
        value = {"method": METHOD, "binding": binding, "implementation": code, "intent": intent, "versions": versions,
            "scope_disposition_record": scope_id, "fresh_main_inventory": fresh_inventory,
            "frame_manifest_artifact": frame.digest, "frame_digest": frame.frame.digest,
            "schedule_digest": frame.schedule.digest, "schedule_artifact": frame.manifest["artifact_references"]["schedule"],
            "schedule_seed_artifact": chain[2]["schedule_seed_artifact"], "article_order_seed_artifact": chain[2]["article_order_seed_artifact"],
            "retained_artifacts": sorted(retained), "final_frame_frozen": True,
            "source_seed_history_evidence_verified": True, "history_scope_complete": False,
            "final_evidence_scope": "exact_declared_registry_plus_explicit_global_unknowns", **POLICY,
            "dispatch_authorized": False, "empirical_validation_completed": False}
        with self._commit_guard(session, chain[0], chain[4]):
            require(implementation() == code, "implementation_changed_before_commit")
            identifier = self.ledger.record(session, FRAME, intent, value)
        return self._frame_summary(self._one(FRAME), reused=False) | {"final_frame_record": identifier}

    def _load_frame(self, identifier):
        row = self.ledger.get(identifier, FRAME)
        require(row["method"] == METHOD and row["implementation"] == implementation(), "final_frame_code_binding")
        require(self._one(FRAME)["id"] == identifier, "unique_final_frame")
        intended = self.ledger.get(row["intent"], INTENT)
        chain = self._chain(row["binding"])
        scope = self.ledger.get(row["scope_disposition_record"], SCOPE)
        expected_scope = self._scope(row["binding"], chain)
        require(intended == {"method": METHOD, "binding": row["binding"], "implementation": row["implementation"],
            "policy": POLICY, "scope_sha256": digest(expected_scope)}, "frame_intent_binding")
        require({k: v for k, v in scope.items() if k != "versions"} == expected_scope
            and scope["versions"] == row["versions"], "scope_disposition_changed")
        require(set(row["versions"]) == {"protocol", "selection", "policy"}, "frame_versions")
        require(self.ledger.get(row["versions"]["protocol"], "protocol")["content"] == {
            "method": METHOD, "implementation": row["implementation"], "binding_sha256": digest(row["binding"]),
            "intent": row["intent"], "additional_source_metadata_scope": "exact-original-plan-versions.embedding_profile-record-only"}, "frame_protocol")
        require(self.ledger.get(row["versions"]["selection"], "selection")["content"] == {
            "rules": "One complete all-pair frame; exact original seeds; unknown strata preserved.", "intent": row["intent"]}, "frame_selection")
        require(self.ledger.get(row["versions"]["policy"], "policy")["content"] == {
            **POLICY, "scope_sha256": digest(expected_scope), "intent": row["intent"]}, "frame_policy")
        require(all(row[key] == chain[2][key] for key in ("schedule_seed_artifact", "article_order_seed_artifact")),
            "final_frame_original_seed_binding")
        for ref in row["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(ref)
        manifest = self.ledger.artifacts.read(row["frame_manifest_artifact"])
        refs = manifest["artifact_references"]
        require(manifest["implementation"] == pipeline.implementation()
            and manifest["input_index_digest"] == chain[1].digest
            and row["schedule_artifact"] == refs["schedule"]
            and row["schedule_digest"] == manifest["schedule_digest"], "frame_manifest_bindings")
        original = self.ledger.artifacts.read(chain[2]["frame_manifest_artifact"])
        original_refs = original["artifact_references"]
        original_derivation = self.ledger.artifacts.read(original_refs["derivation"])
        expected_bindings = {**row["binding"]["preparation_binding"]["snapshot_binding"],
            "candidate_inventory_artifact": original_derivation["bindings"]["candidate_inventory_artifact"],
            "prior_inventory_artifact": chain[3]["artifacts"]["scope"],
            "embedding_proof_artifact": chain[2]["contributions"]["embedding_replay"]}
        expected_derivation = {"version": pipeline.VERSION, "implementation": pipeline.implementation(),
            "cutoff": pipeline.cutoff_binding(chain[1], expected_bindings), "bindings": expected_bindings,
            "candidate_metadata": original_refs["candidate_metadata"],
            "candidate_projection": original_refs["candidate_projection"],
            "prior_projection": chain[3]["artifacts"]["prior_projection"],
            "embedding_proof": chain[2]["contributions"]["embedding_replay"]}
        require(self.ledger.artifacts.read(refs["derivation"]) == expected_derivation
            and refs["derivation"] == digest(expected_derivation), "frame_derivation_source_bindings")
        require(refs["input_index"] == original_refs["input_index"]
            and refs["candidate_metadata"] == original_refs["candidate_metadata"]
            and refs["candidate_projection"] == original_refs["candidate_projection"]
            and refs["prior_projection"] == chain[3]["artifacts"]["prior_projection"]
            and refs["embedding_proof"] == chain[2]["contributions"]["embedding_replay"], "frame_projection_evidence")
        inventory_kind = lineage.inventory_result_kind(self, row["binding"]["preparation_binding"]["snapshot_binding"])
        fresh = self.ledger.get(row["fresh_main_inventory"]["inventory_record"], inventory_kind)
        require(digest(fresh) == row["fresh_main_inventory"]["inventory_artifact"]
            and fresh["snapshot_binding"] == row["binding"]["preparation_binding"]["snapshot_binding"]
            and fresh["source_head_stable"] and fresh["full_source_ledger_preflight_verified"], "final_frame_source_proof")
        states = self.ledger.artifacts.read_bytes(refs["state_codes"])
        bands = self.ledger.artifacts.read_bytes(refs["band_codes"])
        require(len(states) == len(bands) == manifest["total_pairs"]
            and all(v < 9 for v in states) and all(v < len(pipeline.vectors.BAND_NAMES) for v in bands), "stored_pair_codes")
        scoring = self.ledger.artifacts.read(refs["score_bands"])
        original_scoring = self.ledger.artifacts.read(original_refs["score_bands"])
        require(scoring == {**original_scoring, "derivation_binding": digest(expected_derivation),
                "state_codes_sha256": hashlib.sha256(states).hexdigest()}
            and scoring["band_codes_sha256"] == hashlib.sha256(bands).hexdigest()
            and scoring["vectors_digest"] == self.ledger.artifacts.read(refs["embedding_proof"])["prepared_vectors_digest"]
            and manifest["derivation_binding"] == digest({"derivation": refs["derivation"], "score_bands": refs["score_bands"]}),
            "frame_score_evidence")
        # P does not participate in the frozen A0/C0 score ranking. Preserve the
        # original compact bands and original C codes; recompute only P from the
        # audited reconciled observations. No all-pair JSON expansion/re-embedding.
        original_states = self.ledger.artifacts.read_bytes(original_refs["state_codes"])
        require(bands == self.ledger.artifacts.read_bytes(original_refs["band_codes"])
            and len(original_states) == len(states), "frame_original_score_bands")
        p = pipeline.projection.project_prior_exposure(chain[1],
            self.ledger.artifacts.read(chain[3]["artifacts"]["prior_observations"]),
            inventory_certificate=self.ledger.artifacts.read(chain[3]["artifacts"]["prior_inventory"]))
        require(digest(p.metadata) == refs["prior_projection"] and all(
            new // 3 == old // 3 and pipeline.frames.STATES[new % 3] == p.state(rank)
            for rank, (new, old) in enumerate(zip(states, original_states, strict=True))), "frame_exact_candidate_prior_codes")
        frame = pipeline.frames.build_probability_frame(chain[1], (
            {"pair_rank": n, "candidate_exposure": pipeline.frames.STATES[s // 3],
             "prior_exposure": pipeline.frames.STATES[s % 3], "cosine_band": pipeline.vectors.BAND_NAMES[b]}
            for n, (s, b) in enumerate(zip(states, bands, strict=True))), derivation_binding=manifest["derivation_binding"])
        require(frame.digest == row["frame_digest"] == manifest["frame_digest"], "stored_frame_changed")
        schedule = pipeline.schedules.SampleSchedule(self.ledger.artifacts.read_bytes(row["schedule_artifact"]), row["schedule_digest"])
        pipeline.schedules.verify_schedule(frame, schedule)
        seeds = self.ledger.artifacts.read(row["schedule_seed_artifact"])
        require(schedule.manifest["seed_content"] == seeds
            and schedule.manifest["seed_binding"] == {"record": row["binding"]["preparation_binding"]["seed_record"],
                "artifact": row["schedule_seed_artifact"]}, "stored_schedule_seed_changed")
        return row, chain, frame, schedule

    def _frame_summary(self, row, *, reused):
        value = row["payload"]
        return {"final_frame_record": row["id"], "frame_manifest_artifact": value["frame_manifest_artifact"],
            "frame_digest": value["frame_digest"], "schedule_digest": value["schedule_digest"],
            "scope_disposition_record": value["scope_disposition_record"], "final_frame_frozen": True,
            "history_scope_complete": False, "dispatch_authorized": False, "empirical_validation_completed": False,
            "reused_historical_frame": reused, "current_source_quiescence_verified": not reused}

    def _slots(self, session, context, data):
        selected, code = data["binding"], implementation()
        saved, chain, frame, schedule = self._load_frame(selected["final_frame_record"])
        expected = {"method": METHOD, "binding": selected, "implementation": code, "frame_digest": frame.digest,
            "schedule_digest": schedule.digest, "policy": POLICY}
        prior = self._one(SLOT_INTENT, optional=True)
        require(prior is None or prior["payload"] == expected, "changed_slots_require_amendment")
        old = self._one(SLOTS, optional=True)
        if old:
            require(prior is not None and old["payload"]["slot_intent"] == prior["id"]
                and old["payload"]["implementation"] == code, "retained_slot_binding")
            for ref in old["payload"]["retained_artifacts"]:
                self.ledger.artifacts.read_bytes(ref)
            return self._slot_summary(old, reused=True)
        if data["action"] == "slot_status":
            return {"prepared": False, "incomplete": prior is not None, "dispatch_authorized": False}
        intent = prior["id"] if prior else self.ledger.record(session, SLOT_INTENT, METHOD, expected)
        study_id = saved["binding"]["preparation_binding"]["study_record"]
        resource_protocol = self._version_once(session, context, "protocol", admission.METHOD, admission.protocol_content(study_id))
        resource_context = Context(context.objective, context.actor, {"protocol": resource_protocol})
        runtime = admission._runtime_result(self, selected["runtime_record"])
        require(self.ledger.get(selected["runtime_record"], admission.RUNTIME)["study_record"] == study_id, "runtime_study")
        resources = admission.resources_from_evidence(self, session, resource_context, study_record=study_id,
            quota_record=selected["quota_record"], policy_record=selected["resource_policy_record"])
        records_ref = chain[3]["artifacts"]["pair_history_records"]
        history_ref = chain[3]["artifacts"]["pair_history_inventory"]
        history_certificate = self.ledger.artifacts.read(history_ref)
        require(history_certificate["global_gap"] is True and history_certificate["complete"] is False,
            "current_conservative_history_cannot_be_replaced")
        registered = self.ledger.get(study_id, study.STUDY)
        prepared = packets.prepare_initial_packets(frame, schedule, self._documents(chain[0], chain[1]),
            historical_records=self.ledger.artifacts.read(records_ref), history_inventory=history_certificate,
            order_seed=self.ledger.artifacts.read(saved["article_order_seed_artifact"])["seed"],
            bindings={"source_snapshot_record": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
                "source_snapshot_artifact": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_artifact"],
                "frame_verification_record": selected["final_frame_record"], "history_verification_record": saved["binding"]["reconciliation_record"],
                "history_records_sha256": records_ref, "history_inventory_sha256": history_ref,
                "order_seed_record": saved["binding"]["preparation_binding"]["seed_record"],
                "order_seed_artifact": saved["article_order_seed_artifact"], "tokenizer_evidence_record": selected["runtime_record"]},
            token_counter=runtime["token_counter"], cli_profile=runtime["cli_profile"], resources=resources,
            user_instruction_sha256=registered["instruction_evidence_artifact"])
        assessment = admission.assess_packet_resources(self, session, resource_context, study_record=study_id, prepared=prepared,
            runtime_record=selected["runtime_record"], quota_record=selected["quota_record"], policy_record=selected["resource_policy_record"])
        scope = prepared.payload["execution_scope"]
        protocol = self._version_once(session, context, "protocol", METHOD + ":slots", {"method": METHOD,
            "implementation": code, "slot_intent": intent, "prepared_initial_sha256": prepared.digest,
            "upstream_authority": "actual-bound-study-final-frame-history-tokenizer-and-fixed-slot-verification"})
        # An authority record for the exact slots is distinct from permission to
        # run. The original resource assessment stays immutable and nonpermissive.
        authority = {"method": execution.METHOD, "scope_sha256": digest(scope),
            "prefix_sha256": prepared.payload["initial_prefix"]["initial_manifest_sha256"],
            "slot_catalog_sha256": prepared.payload["slot_catalog_sha256"],
            "source_snapshot": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
            "history_inventory": saved["binding"]["reconciliation_record"], "verification_protocol": protocol,
            "final_frame_record": selected["final_frame_record"], "slot_intent": intent,
            "prepared_initial_artifact": prepared.digest, "source_history_seed_and_authority_verified": True,
            "dispatch_authorized": False, "history_scope_complete": False}
        with self._commit_guard(session, chain[0], chain[4]):
            require(implementation() == code, "implementation_changed_before_slots")
            admission_id = self.ledger.record(session, execution.ADMISSION_KIND, intent, authority)
            manifest = prepared.build_execution_manifest(admission_id)
            manifest_ref = self.ledger.artifacts.put(manifest)
            # No MANIFEST_KIND/execution policy is created, no model pathway is
            # reachable here. The future execution operation must retain its own
            # exact policy and honor every remaining resource/history blocker.
            remaining = [v for v in assessment["blockers"] if v != "audited_packet_source_history_seed_authority_pending"]
            value = {"method": METHOD, "binding": selected, "implementation": code, "slot_intent": intent,
                "slot_admission_record": admission_id, "prepared_initial_artifact": prepared.digest,
                "candidate_execution_manifest_artifact": manifest_ref, "resource_assessment_record": assessment["assessment_record"],
                "upstream_packet_authority_verified": True, "resource_assessment_upstream_flag_unchanged": True,
                "remaining_blockers": remaining, "dispatch_authorized": False, "empirical_validation_completed": False,
                "resource_census": prepared.payload["resource_census"], "history_inventory_artifact": history_ref,
                "retained_artifacts": sorted({*prepared.artifacts, prepared.digest, manifest_ref}), **POLICY}
            identifier = self.ledger.record(session, SLOTS, intent, value)
        return self._slot_summary(self._one(SLOTS), reused=False) | {"slot_record": identifier}

    def _slot_summary(self, row, *, reused):
        value = row["payload"]
        return {"slot_record": row["id"], **{k: value[k] for k in ("slot_admission_record", "prepared_initial_artifact",
            "candidate_execution_manifest_artifact", "resource_assessment_record", "upstream_packet_authority_verified",
            "remaining_blockers", "resource_census", "dispatch_authorized", "empirical_validation_completed")},
            "reused_historical_slots": reused, "current_source_quiescence_verified": not reused}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry_required")
        return self._frame(session, context, data) if data["action"] in {"freeze_final_frame", "frame_status"} else self._slots(session, context, data)
