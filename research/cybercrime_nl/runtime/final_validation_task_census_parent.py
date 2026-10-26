"""Audited task-census composition at an already frozen validation cutoff.

This operation derives scoped task evidence; it does not close finite owner/link
discovery. All metadata, including unselected/manual envelopes, is retained for
a later reviewed discovery combiner. The original P and no-retry certificates
are unchanged. No caller semantics, completeness flag, sample or model action
is accepted. Only new observer records and private read-only source copies are
created. Completed repeats are historical reuse, not current liveness claims.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_external_task_scope as external
import final_validation_full_history_census as full
import final_validation_packet_parent as parent
import final_validation_task_scope as main
from newsresearch.common import AuditError, Context, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-parent-physical-census-v1"
INTENT = "cyber_final_validation_task_census_intent"
RESULT = "cyber_final_validation_task_census"
POLICY = {"offline_only": True, "dispatch_authorized": False, "new_model_calls": 0,
    "source_mutations": 0, "new_seed_draws": 0, "sample_or_frame_reselected": False,
    "finite_owner_link_discovery_complete": False, "manual_task_discovery_complete": False,
    "whole_history_complete": False, "prior_exposure_reclassified": False,
    "inherited_no_retry_certificate_unchanged": True}


def require(value, reason):
    if not value:
        raise AuditError("task_census_parent_" + reason)


def implementation():
    code = {}
    for module in (parent, main, external, full):
        code.update(module.implementation())
    path = Path(__file__)
    code[path.relative_to(parent.study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def binding(*, preparation_binding, reconciliation_record):
    return parent.frame_binding(preparation_binding=preparation_binding, reconciliation_record=reconciliation_record)


def main_metadata_scope(snapshot):
    """Fixed extension scope, derived from the verified main snapshot only.

    Empty classifications are intentional. The full-metadata collector reads
    all rows; it cannot declare an unknown row administrative or non-reference.
    No extra referenced source artifacts are admitted by this scope.
    """
    return {"source_owner": snapshot["source_bindings"]["source_owner"],
        "source_head": deepcopy(snapshot["source_bindings"]["source_head"]), "scope_input_sha256": None,
        "record_kinds": {}, "event_kinds": [], "expected_records": [],
        "required_artifacts": [], "artifact_rules": []}


class TaskCensusParent(parent.PacketParent):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "binding"}, "offline_operation")
        require(data["action"] in {"collect", "status"}, "offline_action")
        require(set(data["binding"]) == {"preparation_binding", "reconciliation_record"}, "binding_fields")
        binding(**data["binding"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _reader_versions(self, session, context, *, module, selected, protocol, label, snapshot=False):
        versions = {}
        for kind in ("protocol", "selection"):
            value = {"snapshot_binding_sha256" if snapshot else "binding_sha256": digest(selected),
                "parent_protocol": protocol}
            value.update({"method": module.METHOD, "implementation": module.implementation()} if kind == "protocol"
                else {"rules": "Exact immutable census; no inferred purpose or universal discovery."})
            versions[kind] = self._version_once(session, context, kind, METHOD + ":" + label, value)
        return Context(context.objective, context.actor, versions)

    def _main(self, session, context, chain, selected, protocol, put):
        snapshot, index, prepared, _, _, _ = chain
        selected_preparation = parent.lineage.preparation_module(self, selected["preparation_record"], selected["snapshot_binding"])
        token_id = prepared["tokenizer_record"]
        token = self.ledger.get(token_id, selected_preparation.TOKENIZER_KIND)
        require(token["method"] == selected_preparation.METHOD
            and token["preparation_intent"] == prepared["preparation_intent"]
            and token["vocabulary_sha256"] == parent.packets.VOCAB_HASH, "original_tokenizer_evidence")
        counter = parent.packets.load_token_counter(evidence_record=token_id, expected_identity=token["identity"])
        require(counter.validate() == token["configuration_sha256"], "original_tokenizer_configuration")
        module = selected_preparation.inventory
        ctx = self._reader_versions(session, context, module=module, selected=selected["snapshot_binding"],
            protocol=protocol, label="main", snapshot=True)
        with module.open_attempt_inventory(self, session, ctx, selected["snapshot_binding"],
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            require(reader.index == index, "main_input_index")
            scope = main.classify_main_owner_tasks(reader, self._documents(snapshot, index),
                count_tokens=counter.count, tokenizer_binding=digest(token), encoder=counter.encoder)
            require(scope.manifest["role_catalog_sha256"] == prepared["contributions"]["role_catalog"]
                and scope.manifest["pair_history_manifest_sha256"] == prepared["contributions"]["pair_history_manifest"],
                "original_main_role_evidence_changed")
            census = self.ledger.artifacts.read(reader.counts["census_artifact"])
            require([row["intent_event"] for row in scope.dispositions] == census["intent_event_hashes"], "main_partition")
            evidence = {"events": put(reader.events), "records": put(reader.records),
                "phase_records": put(reader.phase_records), "phase_events": put(reader.phase_events),
                "certificate": put(reader.certificate), "census": put(census),
                "amendment_packet_plans": put(reader.amendment_packet_plans),
                "pilot_selections": put(reader.pilot_selections), "prior_diagnostics": put(reader.prior_diagnostics)}
            output = {"owner_sha256": digest(str(self.source_owner)), "source_id": reader.certificate["source_id"],
                "source_head": reader.certificate["source_head"], "input_index_digest": index.digest,
                "tokenizer_record": token_id, "classifier_input_artifacts": evidence,
                "dispositions": put(scope.dispositions), "history_records": put(scope.history_records),
                "prepared_only": put(scope.prepared_only), "manifest": put(scope.manifest),
                "scoped_inventory_certificate": put(scope.inventory_certificate)}
        require(reader.result is not None, "main_completed_proof_required")
        output["enclosing_inventory"] = reader.result
        return output

    def _history(self, session, context, chain, selected, protocol, main_result, put):
        snapshot, index, _, _, registry, _ = chain
        module = parent.reconciliation.inventory
        main_scope = main_metadata_scope(snapshot)
        scopes = [main_scope, *registry["owners"]]
        declaration = {"snapshot_binding": selected["snapshot_binding"], "owners_sha256": digest(scopes),
            "declared_gaps": registry["declared_gaps"], "scope": "explicit_recorded_study_sources_only",
            "universal_history_completeness_claimed": False}
        read_binding = {"snapshot_binding": selected["snapshot_binding"], "owners": scopes,
            "declared_gaps": registry["declared_gaps"], "registry_declaration_artifact": put(declaration)}
        ctx = self._reader_versions(session, context, module=module, selected=read_binding,
            protocol=protocol, label="history")
        owners, normalized, gap_rows = [], [], []
        main_id = digest(str(self.source_owner))
        entries = {entry["owner_sha256"]: entry for entry in registry["adapter_origins"]}
        with module.open_history_inventory(self, session, ctx, read_binding,
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            by_owner = {owner.census["owner_sha256"]: owner for owner in reader.owners}
            require(set(by_owner) == {main_id, *entries}, "history_owner_partition")
            for owner_id, owner in by_owner.items():
                full_protocol = self._version_once(session, context, "protocol", METHOD + ":full:" + owner_id,
                    full.protocol_content(owner))
                collected = full.collect_full_history_census(owner, protocol_record=full_protocol)
                raw = self.ledger.get(collected["record"], full.RESULT)
                raw_events = self.ledger.artifacts.read(raw["events_artifact"])
                raw_records = self.ledger.artifacts.read(raw["records_artifact"])
                put(raw)
                put(raw_events)
                put(raw_records)
                put(owner.census)
                event_ids = [row["event_hash"] for row in raw_events]
                record_ids = [row["id"] for row in raw_records]
                generic = [row["event_hash"] for row in raw_events if row["kind"] == "model.attempt.intended"]
                if owner_id == main_id:
                    tasks = self.ledger.artifacts.read(main_result["dispositions"])
                    require(generic == [row["intent_event"] for row in tasks], "full_main_intent_partition")
                    manifest_ref = main_result["manifest"]
                    classifier_inputs = main_result["classifier_input_artifacts"]
                    classified_events, classified_records = generic, []
                    origin = {"adapter": "exact_main_producer_contracts", "origin_owner_sha256": main_id}
                else:
                    entry = entries[owner_id]
                    classified = external.normalize_external_task_scope(owner, index,
                        origin_owner=by_owner.get(entry["origin_owner_sha256"]))
                    require(classified["census"]["intent_partition_exact"]
                        and classified["census"]["record_partition_exact"]
                        and classified["census"]["event_partition_exact"], "external_classifier_partition")
                    require(generic == [row["intent_event"] for row in classified["dispositions"]], "full_external_intent_partition")
                    manifest_ref = put(classified)
                    normalized.append(classified)
                    classifier_inputs = {"events": put(owner.events), "records": put(owner.records),
                        "census": put(owner.census), "scope": put(owner.scope),
                        "origin_scope": put(by_owner[entry["origin_owner_sha256"]].scope)
                            if entry["origin_owner_sha256"] is not None else None}
                    classified_events = list(classified["event_dispositions"])
                    classified_records = list(classified["record_dispositions"])
                    origin = entry
                    gap_rows.extend({"owner_sha256": owner_id, "kind": name, "gap": gap}
                        for name in ("possible_pair_gaps", "physical_origin_gaps", "outcome_only_inventory_gaps")
                        for gap in classified[name])
                require(set(classified_events) <= set(event_ids) and set(classified_records) <= set(record_ids), "classified_identity_outside_census")
                classified_event_set, classified_record_set = set(classified_events), set(classified_records)
                partition = {"owner_sha256": owner_id, "all_event_hashes": event_ids, "all_record_ids": record_ids,
                    "generic_intent_event_hashes": generic,
                    "classified_event_hashes": classified_events, "classified_record_ids": classified_records,
                    "unclassified_event_hashes": [v for v in event_ids if v not in classified_event_set],
                    "unclassified_record_ids": [v for v in record_ids if v not in classified_record_set],
                    "classification_scope": "generic_physical_intents_only" if owner_id == main_id else "declared_scoped_external_classifier",
                    "full_metadata_does_not_prove_task_semantics": True}
                gap_rows.append({"owner_sha256": owner_id, "kind": "full_metadata_requires_remaining_disposition",
                    "partition_artifact": put(partition), "affected_input_sha256": None})
                owners.append({"owner_sha256": owner_id, "source_head": owner.scope["source_head"],
                    "scope_artifact": put(owner.scope), "declared_origin": origin,
                    "full_census": collected, "classifier_manifest": manifest_ref,
                    "classifier_input_artifacts": classifier_inputs, "metadata_partition": digest(partition)})
            merged = external.merge_verified_dispositions(normalized)
            merged_ref = put(merged)
        require(reader.result is not None, "history_completed_proof_required")
        return {"main_metadata_scope": put(main_scope), "read_binding": put(read_binding),
            "owners": owners, "merged_external_physical_tasks": merged_ref,
            "unclassified_and_possible_reference_gaps": put(gap_rows), "enclosing_inventory": reader.result}

    def _verified(self, row, desired, intent_id):
        value = row["payload"]
        require(value["intent_record"] == intent_id and value["binding"] == desired["binding"]
            and value["implementation"] == desired["implementation"]
            and value["upstream"] == desired["upstream"]
            and all(value.get(k) == v for k, v in POLICY.items()), "result_binding")
        require(value["artifacts"]["unchanged_prior_inventory"] == desired["upstream"]["prior_inventory"]
            and value["artifacts"]["unchanged_no_retry_inventory"] == desired["upstream"]["no_retry_inventory"]
            and value["artifacts"]["declared_registry"] == desired["upstream"]["registry_artifact"], "inherited_artifact_changed")
        protocol = self.ledger.get(value["versions"]["protocol"], "protocol")["content"]
        require(protocol == {"method": METHOD, "implementation": desired["implementation"],
            "intent_record": intent_id, "binding_sha256": digest(desired["binding"]),
            "upstream_sha256": digest(desired["upstream"])}, "result_protocol")
        for reference in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        main_result = self.ledger.artifacts.read(value["artifacts"]["main"])
        history_result = self.ledger.artifacts.read(value["artifacts"]["history"])
        snapshot_binding = desired["binding"]["preparation_binding"]["snapshot_binding"]
        inventory_kind = parent.lineage.inventory_result_kind(self, snapshot_binding)
        for result, kind, guard in ((main_result, inventory_kind, "full_source_ledger_preflight_verified"),
                (history_result, parent.reconciliation.inventory.RESULT_KIND, "full_declared_source_ledger_preflight_verified")):
            proof_ref = result["enclosing_inventory"]
            proof = self.ledger.get(proof_ref["inventory_record"], kind)
            require(digest(proof) == proof_ref["inventory_artifact"] and proof["source_head_stable"] and proof[guard], "completed_inventory_binding")
        main_proof = self.ledger.get(main_result["enclosing_inventory"]["inventory_record"], inventory_kind)
        snapshot, _ = parent.lineage.load_snapshot(self, snapshot_binding)
        require(main_proof["snapshot_binding"] == snapshot_binding
            and main_proof["source_bindings"] == snapshot["source_bindings"]
            and main_proof["source_bindings"]["source_head"] == main_result["source_head"]
            and main_proof["input_index_digest"] == main_result["input_index_digest"]
            and main_result["owner_sha256"] == digest(snapshot["source_bindings"]["source_owner"]), "main_proof_cutoff_binding")
        for name, key in {"events": "events_artifact", "records": "records_artifact", "phase_records": "phase_records_artifact",
                "phase_events": "phase_events_artifact", "census": "census_artifact", "certificate": "pair_inventory_artifact",
                "pilot_selections": "pilot_selections_artifact", "prior_diagnostics": "prior_diagnostics_artifact",
                "amendment_packet_plans": "amendment_packet_plans_artifact"}.items():
            require(main_result["classifier_input_artifacts"][name] == main_proof[key], "main_classifier_input_binding")
        proof = self.ledger.get(history_result["enclosing_inventory"]["inventory_record"], parent.reconciliation.inventory.RESULT_KIND)
        read_binding = self.ledger.artifacts.read(history_result["read_binding"])
        registry = self.ledger.artifacts.read(desired["upstream"]["registry_artifact"])
        require(proof["binding"] == read_binding
            and read_binding["snapshot_binding"] == snapshot_binding
            and read_binding["owners"] == [main_metadata_scope(snapshot), *registry["owners"]]
            and read_binding["declared_gaps"] == registry["declared_gaps"]
            and history_result["main_metadata_scope"] == digest(main_metadata_scope(snapshot)), "history_proof_scope")
        proof_owners = {item["census"]["owner_sha256"]: item for item in proof["owners"]}
        require(set(proof_owners) == {item["owner_sha256"] for item in history_result["owners"]}, "completed_owner_set")
        for owner in history_result["owners"]:
            child = self.ledger.get(owner["full_census"]["record"], full.RESULT)
            require(digest(child) == owner["full_census"]["artifact"]
                and child["original_scoped_census_artifact"] == digest(proof_owners[owner["owner_sha256"]]["census"])
                and child["source_head"] == owner["source_head"]
                and child["declared_history_scope_sha256"] == owner["scope_artifact"], "full_child_enclosing_proof")
            if owner["owner_sha256"] != main_result["owner_sha256"]:
                input_refs, owner_proof = owner["classifier_input_artifacts"], proof_owners[owner["owner_sha256"]]
                require(input_refs["events"] == owner_proof["events_artifact"]
                    and input_refs["records"] == owner_proof["records_artifact"]
                    and input_refs["census"] == digest(owner_proof["census"])
                    and input_refs["scope"] == owner["scope_artifact"], "external_classifier_input_binding")
        return value

    def _summary(self, row, desired, intent_id, *, reused):
        value = self._verified(row, desired, intent_id)
        return {"task_census_record": row["id"], "task_census_artifact": digest(value), "method": METHOD, **POLICY,
            "counts": value["counts"], "artifacts": value["artifacts"],
            "reused_historical_census": reused, "current_source_quiescence_verified": not reused}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry")
        selected = data["binding"]
        chain = self._chain(selected)
        snapshot, _, prepared, reconciled, registry, _ = chain
        code = implementation()
        desired = {"method": METHOD, "binding": selected, "implementation": code, "policy": POLICY,
            "upstream": {"preparation_artifact": digest(prepared), "reconciliation_artifact": digest(reconciled),
                "registry_artifact": digest(registry), "schedule_seed_artifact": prepared["schedule_seed_artifact"],
                "article_order_seed_artifact": prepared["article_order_seed_artifact"],
                "prior_inventory": reconciled["artifacts"]["prior_inventory"],
                "no_retry_inventory": reconciled["artifacts"]["pair_history_inventory"]}}
        old, completed = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        if old:
            require(digest(old["payload"]) == digest(desired), "changed_binding_requires_amendment")
        if completed:
            require(old is not None, "result_without_intent")
            return self._summary(completed, desired, old["id"], reused=True)
        if data["action"] == "status":
            return {"method": METHOD, **POLICY, "collected": False, "incomplete_operation": old is not None}
        require(type(self.observer) is parent.study.WindowsProcessObserver, "concrete_process_observer")
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        versions = {}
        for kind, value in {"protocol": {"method": METHOD, "implementation": code, "intent_record": intent,
                "binding_sha256": digest(selected), "upstream_sha256": digest(desired["upstream"])},
                "selection": {"intent_record": intent, "rules": "Original exact registry plus derived full-main metadata; no new owner discovery."},
                "policy": {"intent_record": intent, **POLICY}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD, value)
        retained = set()
        def put(value):
            reference = self.ledger.artifacts.put(value)
            retained.add(reference)
            return reference
        main_result = self._main(session, context, chain, selected["preparation_binding"], versions["protocol"], put)
        history_result = self._history(session, context, chain, selected["preparation_binding"], versions["protocol"], main_result, put)
        artifacts = {"main": put(main_result), "history": put(history_result),
            "unchanged_prior_inventory": put(self.ledger.artifacts.read(desired["upstream"]["prior_inventory"])),
            "unchanged_no_retry_inventory": put(self.ledger.artifacts.read(desired["upstream"]["no_retry_inventory"])),
            "declared_registry": put(registry), "declared_discovery_gaps": put(registry["declared_gaps"])}
        counts = {"owners": len(history_result["owners"]),
            "main_physical_intents": len(self.ledger.artifacts.read(main_result["dispositions"])),
            "full_event_rows": sum(o["full_census"]["event_count"] for o in history_result["owners"]),
            "full_record_rows": sum(o["full_census"]["record_count"] for o in history_result["owners"]),
            "unclassified_metadata_events": sum(len(self.ledger.artifacts.read(o["metadata_partition"])["unclassified_event_hashes"])
                for o in history_result["owners"]),
            "unclassified_metadata_records": sum(len(self.ledger.artifacts.read(o["metadata_partition"])["unclassified_record_ids"])
                for o in history_result["owners"])}
        # The result is created only after both readers' closing fingerprints,
        # liveness and fresh-copy head guards, then with every source locked.
        with self._commit_guard(session, snapshot, registry):
            require(implementation() == code, "implementation_changed")
            value = {"method": METHOD, **POLICY, "binding": selected, "implementation": code,
                "intent_record": intent, "versions": versions, "artifacts": artifacts,
                "counts": counts, "upstream": desired["upstream"], "retained_artifacts": sorted(retained),
                "limitations": "Scoped classifiers do not discharge unclassified raw metadata or finite owner/link/manual discovery. Exact physical origin schemes are retained, not rehashed across views. Main and external contributions are separate from unchanged P and no-retry certificates; no packet authority or usable reference is created."}
            self._verified({"payload": value}, desired, intent)
            identifier = self.ledger.record(session, RESULT, intent, value)
        return self._summary(self._one(RESULT), desired, intent, reused=False) | {"task_census_record": identifier}
