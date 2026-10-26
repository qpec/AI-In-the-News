"""Audited declared-history reconciliation; no models, samples or admission.

Consumes the retained intermediate main-owner preparation and an explicitly
registered external-owner/origin registry. Actual locked inventories and exact
family adapters provide observations; caller hashes cannot supply C/P/Y truth.
Unsupported/main/manual scope remains incomplete. The merged P and no-retry
artifacts are separate inputs to a future reviewed final preparation operation.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_history as history
import final_validation_history_inventory as inventory
import final_validation_legacy_pair_history as pair_adapter
import final_validation_legacy_prior as screening_adapter
import final_validation_preparation as preparation
import final_validation_projection as projection
import final_validation_study as study
import final_validation_source_lineage as lineage
from newsresearch.common import AuditError, Context, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-declared-history-reconciliation-v1"
INTENT_KIND = "cyber_final_validation_history_reconciliation_intent"
RESULT_KIND = "cyber_final_validation_history_reconciliation"
ADAPTERS = {"legacy_astra_screening", "provider_event_pair_labels", "unresolved"}
POLICY = {"stage": "verified_declared_history_contributions", "final_statistical_frame": False,
    "packet_preparation_eligible": False, "dispatch_authorized": False,
    "prior_exposure_scope_complete": False, "no_retry_history_complete": False,
    "new_model_calls": 0, "source_mutations": 0, "new_seed_draws": 0,
    "sample_or_frame_reselected": False, "universal_history_completeness_claimed": False}


def require(value, reason):
    if not value:
        raise AuditError("final_reconciliation_" + reason)


def implementation():
    code = {}
    for module in (preparation, inventory, screening_adapter, pair_adapter, lineage):
        code.update(module.implementation())
    path = Path(__file__)
    code[path.relative_to(study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def binding(*, preparation_record, study_record, seed_record, snapshot_binding):
    selected = {"preparation_record": preparation_record, "study_record": study_record,
        "seed_record": seed_record, "snapshot_binding": snapshot_binding}
    validate_binding(selected)
    return selected


def validate_binding(selected):
    require(isinstance(selected, dict) and set(selected) == {
        "preparation_record", "study_record", "seed_record", "snapshot_binding"}, "binding_fields")
    for key in ("preparation_record", "study_record", "seed_record"):
        history.sha(selected[key])
    require(isinstance(selected["snapshot_binding"], dict) and set(selected["snapshot_binding"]) == {
        "snapshot_record", "snapshot_artifact"}, "snapshot_fields")
    for value in selected["snapshot_binding"].values():
        history.sha(value)


def _has_rule(scope, origin, kind, path):
    return any(rule["origin"] == origin and rule["kind"] == kind and rule["paths"] == [path]
        for rule in scope["artifact_rules"])


def validate_registry(registry, index, *, main_owner, observer_owner):
    require(isinstance(registry, dict) and set(registry) == {
        "owners", "declared_gaps", "adapter_origins", "registry_source_reference"}, "registry_fields")
    require(isinstance(registry["registry_source_reference"], str)
        and bool(registry["registry_source_reference"].strip()), "registry_evidence_required")
    # Reuse the exact reader's scope validation; the actual registry artifact is
    # created after the immutable parent intent and before source access.
    inventory._validate({"snapshot_binding": {}, "owners": registry["owners"],
        "declared_gaps": registry["declared_gaps"], "registry_declaration_artifact": digest(registry)},
        {d.input_sha256 for d in index.inputs})
    owners = {}
    for scope in registry["owners"]:
        path = Path(scope["source_owner"])
        require(path.is_absolute() and str(path) == str(path.resolve()), "explicit_canonical_owner_required")
        require(path != main_owner and path != observer_owner
            and observer_owner not in path.parents and path not in observer_owner.parents,
            "external_owner_separation")
        owners[digest(str(path))] = scope
    entries = registry["adapter_origins"]
    require(isinstance(entries, list) and len(entries) == len(owners), "owner_adapter_coverage")
    by_owner = {}
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {
            "owner_sha256", "adapter", "origin_owner_sha256"}, "adapter_fields")
        owner = entry["owner_sha256"]
        require(owner in owners and owner not in by_owner and entry["adapter"] in ADAPTERS, "declared_adapter")
        origin = entry["origin_owner_sha256"]
        require(origin is None or origin in owners, "origin_must_be_in_same_locked_inventory")
        require(entry["adapter"] != "unresolved" or origin is None, "unresolved_origin_claim")
        scope = owners[owner]
        if entry["adapter"] == "legacy_astra_screening":
            required = {screening_adapter.PLAN, screening_adapter.INTENDED, screening_adapter.RESPONSE}
            require(all(scope["record_kinds"].get(k) in inventory.CATEGORIES - {"out_of_scope"} for k in required),
                "screening_record_scope")
            require("astra_validation.response.received" in scope["event_kinds"]
                and _has_rule(scope, "record", screening_adapter.PLAN, "/batches/*/items")
                and _has_rule(scope, "record", screening_adapter.RESPONSE, "/response"), "screening_artifact_scope")
        elif entry["adapter"] == "provider_event_pair_labels":
            required = {"provider_label_plan", "provider_label_handoff", "provider_label_judgment",
                "protocol", "selection", "question", "dossier_definition", "codebook", "prompt", "profile"}
            require(all(scope["record_kinds"].get(k) in inventory.CATEGORIES - {"out_of_scope"} for k in required),
                "pair_record_scope")
            require({"codex.response.received", "provider_label.request.chunk_inspected", "provider_label.handoff.prepared"}
                <= set(scope["event_kinds"]), "pair_event_scope")
            for origin_kind, kind, pointer in (("record", "provider_label_plan", "/pairs/*/articles/*/original"),
                    ("record", "provider_label_judgment", "/response"),
                    ("event", "provider_label.request.chunk_inspected", "/packets"),
                    ("event", "codex.response.received", "/artifact")):
                require(_has_rule(scope, origin_kind, kind, pointer), "pair_artifact_scope")
        by_owner[owner] = entry
    # Origins must be explicitly native, same-family entries; no cycles or view
    # chains can manufacture another independent physical review.
    for entry in entries:
        origin = entry["origin_owner_sha256"]
        if origin is not None:
            require(by_owner[origin]["origin_owner_sha256"] == origin
                and by_owner[origin]["adapter"] == entry["adapter"], "native_origin_family_required")
    return by_owner


class Reconciliation(study.Study):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        payload = payload or {}
        require(operation == "status" and not versions, "offline_operations_only")
        require(payload.get("action") in {"reconcile", "status"}
            and set(payload) == {"action", "binding", "registry"}, "operation_shape")
        validate_binding(payload["binding"])
        return Research.execute(self, "status", {"method": METHOD, **payload}, objective=objective, actor=actor)

    def _prepared(self, selected):
        registered = self._registration()
        require(registered["id"] == selected["study_record"]
            and registered["payload"]["seed_record"] == selected["seed_record"], "study_or_seed_changed")
        selected_preparation = lineage.preparation_module(self, selected["preparation_record"], selected["snapshot_binding"])
        if selected_preparation is lineage.v11_preparation:
            prepared, snapshot, index = selected_preparation.load_completed(
                self, lineage.active_session(self), selected["preparation_record"])
            require(all(prepared["binding"][key] == selected[key]
                for key in ("study_record", "seed_record", "snapshot_binding")), "preparation_binding")
            return snapshot, index, prepared
        snapshot, index = inventory.inventory._snapshot(self, selected["snapshot_binding"])
        freeze = self._one(study.FREEZE)
        require(freeze["payload"]["study_record"] == registered["id"]
            and freeze["payload"]["seed_record"] == selected["seed_record"]
            and freeze["payload"]["source_bindings"] == snapshot["source_bindings"], "original_freeze_binding")
        prepared = self.ledger.get(selected["preparation_record"], preparation.RESULT_KIND)
        require(prepared["method"] == preparation.METHOD and prepared["implementation"] == preparation.implementation()
            and all(prepared.get(k) == v for k, v in preparation.POLICY.items())
            and all(prepared["binding"][k] == selected[k] for k in ("study_record", "seed_record", "snapshot_binding")),
            "preparation_binding")
        intent = self.ledger.get(prepared["preparation_intent"], preparation.INTENT_KIND)
        require(intent["binding"] == prepared["binding"] and intent["implementation"] == prepared["implementation"]
            and intent["original_study_artifact"] == digest(registered["payload"]), "preparation_intent_binding")
        protocol = self.ledger.get(prepared["versions"]["protocol"], "protocol")["content"]
        require(protocol["method"] == preparation.METHOD and protocol["implementation"] == preparation.implementation()
            and protocol["preparation_intent"] == prepared["preparation_intent"]
            and protocol["binding_sha256"] == digest(prepared["binding"]), "preparation_protocol_binding")
        for reference in prepared["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        proof = self.ledger.get(prepared["inventory"]["inventory_record"], "cyber_final_validation_attempt_inventory")
        require(digest(proof) == prepared["inventory"]["inventory_artifact"]
            and proof["snapshot_binding"] == selected["snapshot_binding"]
            and proof["full_source_ledger_preflight_verified"] and proof["source_head_stable"], "main_inventory_proof")
        seeds = self.ledger.get(selected["seed_record"], study.SEEDS)
        require(all(prepared[k] == seeds[k] for k in ("schedule_seed_artifact", "article_order_seed_artifact")), "seed_artifacts_changed")
        return snapshot, index, prepared

    def _summary(self, row, *, reused):
        value = row["payload"]
        for reference in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        return {"reconciliation_record": row["id"], "reconciliation_artifact": digest(value),
            "method": METHOD, **POLICY, "binding": value["binding"], "artifacts": value["artifacts"],
            "counts": value["counts"], "inventory_record": value["inventory"]["inventory_record"],
            "reused_historical_reconciliation": reused, "current_source_quiescence_verified": not reused,
            "pending": ["unsupported_and_manual_scope_reconciliation", "final_frame_with_unchanged_seeds",
                "complete_slot_history_admission", "registered_account_execution"]}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry_required")
        selected, registry = data["binding"], data["registry"]
        snapshot, index, prepared = self._prepared(selected)
        adapters = validate_registry(registry, index, main_owner=self.source_owner, observer_owner=self.ledger.root.resolve())
        code = implementation()
        desired = {"method": METHOD, "binding": selected, "registry_sha256": digest(registry),
            "preparation_artifact": digest(prepared), "implementation": code, "policy": POLICY}
        old = self._one(INTENT_KIND, optional=True)
        if old:
            require(old["payload"] == desired, "changed_reconciliation_requires_amendment")
        completed = self._one(RESULT_KIND, optional=True)
        if completed:
            require(old is not None and completed["payload"]["reconciliation_intent"] == old["id"]
                and completed["payload"]["implementation"] == code
                and completed["payload"]["binding"] == selected, "result_binding")
            return self._summary(completed, reused=True)
        if data["action"] == "status":
            return {"method": METHOD, **POLICY, "reconciled": False,
                "incomplete_reconciliation": old is not None, "current_source_quiescence_verified": False}
        require(type(self.observer) is study.WindowsProcessObserver, "concrete_process_observer_required")
        intent_id = old["id"] if old else self.ledger.record(session, INTENT_KIND, METHOD, desired)
        retained = set()

        def put(value):
            reference = self.ledger.artifacts.put(value)
            retained.add(reference)
            return reference

        registry_ref = put(registry)
        declared = {"snapshot_binding": selected["snapshot_binding"], "owners_sha256": digest(registry["owners"]),
            "declared_gaps": registry["declared_gaps"], "scope": "explicit_recorded_study_sources_only",
            "universal_history_completeness_claimed": False}
        history_binding = {"snapshot_binding": selected["snapshot_binding"], "owners": registry["owners"],
            "declared_gaps": registry["declared_gaps"], "registry_declaration_artifact": put(declared)}
        versions = {}
        for kind, content in {"protocol": {"method": METHOD, "implementation": code, "binding_sha256": digest(selected),
                "registry_sha256": registry_ref, "reconciliation_intent": intent_id},
                "selection": {"rules": "Exactly declared external owners and native/copy mappings; unresolved scope retained.",
                    "binding_sha256": digest(selected), "registry_sha256": registry_ref},
                "policy": {"mode": "offline-contributions-only", **POLICY, "reconciliation_intent": intent_id}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD, content)
        read_versions = {}
        for kind in ("protocol", "selection"):
            content = {"binding_sha256": digest(history_binding), "parent_protocol": versions["protocol"]}
            if kind == "protocol":
                content.update(method=inventory.METHOD, implementation=inventory.implementation())
            else:
                content["rules"] = "Complete declared immutable ledgers; no semantic inference from kind or owner name."
            read_versions[kind] = self._version_once(session, context, kind, METHOD + ":inventory", content)
        main = prepared["contributions"]
        observations = deepcopy(self.ledger.artifacts.read(main["prior_observations"]))
        contributions = [self.ledger.artifacts.read(main["prior_source_contribution"])]
        pair_records = deepcopy(self.ledger.artifacts.read(main["pair_history_records"]))
        main_history = self.ledger.artifacts.read(main["pair_history_inventory"])
        history.validate_inventory(main_history)
        manifests, gaps = [], [{"reason_code": "main_owner_inherited_history_incomplete", "affected_input_sha256": None}]
        with inventory.open_history_inventory(self, session, Context(context.objective, context.actor, read_versions),
                history_binding, observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            by_owner = {item.census["owner_sha256"]: item for item in reader.owners}
            # Identical durable physical intent evidence cannot be declared as
            # two native originals merely by assigning two filesystem paths.
            event_origins = {}
            for owner_id, owner in by_owner.items():
                origin = adapters[owner_id]["origin_owner_sha256"]
                if origin is not None:
                    for event in owner.events:
                        if event["kind"] == "model.attempt.intended":
                            previous = event_origins.setdefault(event["event_hash"], origin)
                            require(previous == origin, "same_physical_evidence_conflicting_origins")
            for owner_id, entry in adapters.items():
                owner = by_owner[owner_id]
                origin = by_owner.get(entry["origin_owner_sha256"])
                if entry["adapter"] == "legacy_astra_screening":
                    normalized = screening_adapter.normalize_legacy_astra_prior(owner, index, origin_owner=origin)
                    rows = []  # Screening never supplies pair truth or blocks another estimand by label alone.
                elif entry["adapter"] == "provider_event_pair_labels":
                    normalized = pair_adapter.normalize_provider_label_history(owner, index, origin_owner=origin)
                    rows = list(normalized.records)
                    history.validate_inventory(normalized.inventory_certificate)
                else:
                    gap = {"reason_code": "owner_adapter_unresolved", "owner_sha256": owner_id,
                        "affected_input_sha256": owner.scope["scope_input_sha256"]}
                    gaps.append(gap)
                    manifest = {"adapter": "unresolved", "owner_sha256": owner_id,
                        "census_sha256": digest(owner.census), "scope_sha256": digest(owner.scope),
                        "physical_attempts": owner.census["physical_attempts"], "gaps": [gap]}
                    manifests.append(put(manifest))
                    contributions.append({"source_id": owner_id, "source_kind": "owner",
                        "immutable_head_sha256": digest(owner.scope["source_head"]), "reconciliation": "incomplete",
                        "missing_document_ids": None, "event_ids": [], "inventory_sha256": digest(manifest)})
                    continue
                observations.extend(normalized.observations)
                contributions.append(normalized.source_contribution)
                pair_records.extend(rows)
                manifests.append(put({"adapter": entry["adapter"], "declared_origin": entry["origin_owner_sha256"],
                    "manifest": normalized.manifest, "source_contribution": normalized.source_contribution,
                    "observations_artifact": put(list(normalized.observations)), "pair_records_artifact": put(rows)}))
                # Each currently supported adapter explicitly leaves other
                # history unresolved. Never infer exhaustive semantics from a
                # complete raw SQL census or a native-origin declaration.
                gaps.append({"reason_code": "adapter_history_scope_incomplete", "owner_sha256": owner_id,
                    "affected_input_sha256": None})
            gaps.extend(reader.declared_gaps)
            gaps.extend(gap for owner in reader.owners for gap in owner.gaps)
            scope = {"method": METHOD, "binding": selected, "registry_artifact": registry_ref,
                "main_prior_manifest": main["prior_manifest"], "external_manifest_artifacts": manifests,
                "gaps": gaps, "scope_complete": False}
            scope_ref = put(scope)
            # Same cutoff definition as frame_pipeline.cutoff_binding, without
            # constructing/replacing a statistical frame or provisional sample.
            cutoff = {"input_index_digest": index.digest, "source_bindings": dict(index.bindings),
                **selected["snapshot_binding"]}
            p_certificate = {"scope_statement": projection.PRIOR_SCOPE, "scope_complete": False,
                "required_source_ids": [c["source_id"] for c in contributions],
                "study_inventory_sha256": scope_ref, "cutoff_binding_sha256": digest(cutoff),
                "input_index_digest": index.digest, "sources": contributions}
            p = projection.project_prior_exposure(index, observations, inventory_certificate=p_certificate)
            normalized_pairs = history.normalize_records(pair_records)
            no_retry = {"binding_sha256": scope_ref, "complete": False,
                "unknown_input_sha256": sorted({v for g in gaps for v in (g["affected_input_sha256"] or [])}),
                "global_gap": main_history["global_gap"] or any(g["affected_input_sha256"] is None for g in gaps)}
            history.validate_inventory(no_retry)
            artifacts = {"registry": registry_ref, "scope": scope_ref, "prior_observations": put(observations),
                "prior_inventory": put(p_certificate), "prior_projection": put(p.metadata),
                "pair_history_records": put(pair_records), "pair_history_inventory": put(no_retry),
                "pair_history_physical_catalog": put(normalized_pairs), "gaps": put(gaps),
                "external_contributions": put(manifests)}
            counts = {"owners": len(reader.owners), "prior_observation_views": len(observations),
                "unique_prior_physical_events": p.metadata["physical_events"],
                "confirmed_prior_inputs": len(p.confirmed_documents),
                "localized_uncertain_prior_inputs": len(p.uncertain_documents),
                "uncertain_prior_inputs": sum(p.document_state(d.document_id) == "unknown" for d in index.inputs),
                "prior_global_unknown": p.global_unknown, "pair_reference_views": len(pair_records),
                "unique_pair_reference_attempts": len(normalized_pairs), "gap_count": len(gaps)}
        require(reader.result is not None and implementation() == code, "verification_or_implementation_changed")
        seeds = self.ledger.get(selected["seed_record"], study.SEEDS)
        value = {"method": METHOD, **POLICY, "binding": selected, "implementation": code,
            "versions": versions, "reconciliation_intent": intent_id, "registry_artifact": registry_ref,
            "inventory": reader.result, "artifacts": artifacts, "counts": counts,
            "schedule_seed_artifact": seeds["schedule_seed_artifact"],
            "article_order_seed_artifact": seeds["article_order_seed_artifact"],
            "retained_artifacts": sorted(retained),
            "limitations": "Declared native-origin and scope registry is operator evidence, not external attestation or exhaustive human-history proof. Every selected ledger is clone-preflighted at its exact cutoff. Supported full-source families preserve physical origins; copied views cannot become independent judgments. P exposure and no-retry availability remain separate, with inherited/manual/unsupported gaps. No final frame, sample, packet, semantic label or dispatch permission is created."}
        identifier = self.ledger.record(session, RESULT_KIND, intent_id, value)
        return self._summary(self._one(RESULT_KIND), reused=False) | {"reconciliation_record": identifier}
