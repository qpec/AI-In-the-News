"""Audited representation/matching batches and original pilot/Standard sources.

An exact completed task census precedes this separately declared source read.
One physical reference batch remains one attempt with its original logical slots. This
is a family contribution, not discovery closure, a current reference judgment,
sampling, execution admission, or permission to retry. Original certificates and
seeds remain unchanged. Retained complete adapter inputs permit source-free
revalidation of completed results without reopening historical owners.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import final_validation_representation_history as adapter
import final_validation_matching_history as matching
import final_validation_task_census_parent as task
from newsresearch.common import AuditError, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-representation-batch-parent-v1"
INTENT = "cyber_final_validation_batch_history_intent"
RESULT = "cyber_final_validation_batch_history"
POLICY = {"offline_only": True, "new_model_calls": 0, "source_mutations": 0, "new_seed_draws": 0,
    "dispatch_authorized": False, "creates_pair_y": False, "sample_or_frame_reselected": False,
    "finite_owner_link_discovery_complete": False, "whole_history_complete": False,
    "inherited_no_retry_certificate_unchanged": True, "physical_batches_not_flattened_into_attempts": True}
VERSION_KINDS = {"protocol", "question", "selection", "dossier_definition", "codebook", "prompt", "profile", "policy"}
REP_RULES = {("record", "representation_plan", ("/panels",)),
    ("record", "representation_plan", ("/views",)), ("record", "representation_plan", ("/cards",)),
    ("record", "representation_plan", ("/manifest",)),
    ("record", "representation_plan", ("/manifest", "/*/request")),
    ("record", "representation_references", ("/response",)),
    ("event", "operation.intended", ("/input",)), ("event", "operation.completed", ("/result",))}
STANDARD_RULES = {("record", "luna_standard_assessment", ("/request",)),
    ("record", "luna_standard_assessment", ("/response",))}
MATCH_VERSION_KINDS = {"protocol", "question", "selection", "codebook", "prompt", "profile"}
MATCH_RULES = {("record", "luna_pilot_reference_result", ("/response",)),
    ("event", "luna.pilot.reference.inspected", ("/packet",)),
    ("event", "operation.intended", ("/input",)), ("event", "operation.completed", ("/result",))}
PILOT_RULES = {("record", "luna_matching_pilot_plan", ("/cards",)),
    ("record", "luna_matching_pilot_plan", ("/manifest",)),
    ("record", "luna_matching_pilot_plan", ("/selected_provenance",)),
    ("record", "luna_matching_pilot_plan", ("/manifest", "/*/request"))}


def require(value, reason):
    if not value:
        raise AuditError("batch_history_parent_" + reason)


def implementation():
    path = Path(__file__)
    return {**task.implementation(), **adapter.implementation(), **matching.implementation(),
        path.relative_to(task.parent.study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def binding(*, task_census_record, task_census_binding):
    task.parent.execution.sha(task_census_record)
    task.binding(**task_census_binding)
    return {"task_census_record": task_census_record, "task_census_binding": deepcopy(task_census_binding)}


def declared_entries(value):
    return [{**entry, "family": family} for key, family in (("representation_sources", adapter.FAMILY),
        ("matching_sources", matching.FAMILY)) for entry in value.get(key, [])]


def validate_declaration(value, index, *, main_owner, observer_owner, prior_registry):
    required_fields = {"owners", "representation_sources", "source_reference"}
    require(isinstance(value, dict) and required_fields <= set(value)
        and set(value) <= required_fields | {"matching_sources"}, "declaration_fields")
    require(isinstance(value["source_reference"], str) and value["source_reference"].strip(), "declaration_provenance")
    inventory = task.parent.reconciliation.inventory
    inventory._validate({"snapshot_binding": {}, "owners": value["owners"], "declared_gaps": [],
        "registry_declaration_artifact": digest(value)}, {d.input_sha256 for d in index.inputs})
    scopes = {}
    prior = {s["source_owner"]: s["source_head"] for s in prior_registry["owners"]}
    for scope in value["owners"]:
        owner = Path(scope["source_owner"])
        require(owner.is_absolute() and str(owner) == str(owner.resolve())
            and owner not in {main_owner, observer_owner} and owner not in observer_owner.parents
            and observer_owner not in owner.parents, "external_owner_separation")
        if str(owner) in prior:
            require(scope["source_head"] == prior[str(owner)], "prior_owner_cutoff_changed")
        scopes[digest(str(owner))] = scope
    for key in ("representation_sources", "matching_sources"):
        require(isinstance(value.get(key, []), list) and all(isinstance(e, dict) for e in value.get(key, [])), "source_entry_list")
    entries = declared_entries(value)
    require(entries, "batch_sources_required")
    by_owner, standards, pilots = {}, set(), set()
    previous_origins = {entry["owner_sha256"]: entry["origin_owner_sha256"] for entry in prior_registry["adapter_origins"]}
    for entry in entries:
        is_matching = entry["family"] == matching.FAMILY
        fields = {"owner_sha256", "origin_owner_sha256", "standard_owner_sha256", "family"}
        fields |= {"pilot_owner_sha256", "pilot_plan_records"} if is_matching else {"plan_records"}
        require(set(entry) == fields, "entry_fields")
        owner, origin, standard = (entry[k] for k in ("owner_sha256", "origin_owner_sha256", "standard_owner_sha256"))
        require(owner in scopes and owner not in by_owner and origin in scopes and standard in scopes
            and owner != standard and origin != standard, "entry_owner_links")
        require(previous_origins.get(owner) is None or previous_origins[owner] == origin, "prior_physical_origin_changed")
        plans = entry["pilot_plan_records"] if is_matching else entry["plan_records"]
        require(isinstance(plans, list) and plans and plans == sorted(set(plans)), "exact_plan_set_required")
        for ref in plans:
            task.parent.execution.sha(ref)
        scope = scopes[owner]
        if is_matching:
            pilot = entry["pilot_owner_sha256"]
            require(pilot in scopes and pilot not in {owner, origin, standard}, "pilot_owner_links")
            pilots.add(pilot)
            required = MATCH_VERSION_KINDS | {"luna_pilot_reference_handoff", "luna_pilot_reference_result"}
            require(all(scope["record_kinds"].get(k) in inventory.CATEGORIES - {"out_of_scope"} for k in required), "matching_record_scope")
            require({"operation.intended", "operation.completed", "luna.pilot.reference.inspected"} <= set(scope["event_kinds"]), "matching_event_scope")
            require(MATCH_RULES <= {(r["origin"], r["kind"], tuple(r["paths"])) for r in scope["artifact_rules"] if r["required"]}, "matching_artifact_scope")
            plan_scope, plan_kind = scopes[pilot], "luna_matching_pilot_plan"
            require(all(plan_scope["record_kinds"].get(k) in inventory.CATEGORIES - {"out_of_scope"}
                for k in VERSION_KINDS | {plan_kind}), "pilot_record_scope")
            require(PILOT_RULES <= {(r["origin"], r["kind"], tuple(r["paths"])) for r in plan_scope["artifact_rules"] if r["required"]}, "pilot_artifact_scope")
            require("session.ended" in scopes[standard]["event_kinds"], "standard_snapshot_event_scope")
        else:
            required = VERSION_KINDS | {"representation_plan", "representation_handoff", "representation_references"}
            require(all(scope["record_kinds"].get(k) in inventory.CATEGORIES - {"out_of_scope"} for k in required), "representation_record_scope")
            require({"operation.intended", "operation.completed", "representation.inspected"} <= set(scope["event_kinds"]), "representation_event_scope")
            require(REP_RULES <= {(r["origin"], r["kind"], tuple(r["paths"])) for r in scope["artifact_rules"] if r["required"]}, "representation_artifact_scope")
            plan_scope, plan_kind = scope, "representation_plan"
        require(set(plans) == {r["record_id"] for r in plan_scope["expected_records"] if r["kind"] == plan_kind}, "declared_plan_record_scope")
        by_owner[owner] = entry
        standards.add(standard)
    require(set(scopes) == set(by_owner) | standards | pilots and not set(by_owner) & (standards | pilots)
        and not standards & pilots, "complete_owner_role_partition")
    for entry in entries:
        origin = by_owner.get(entry["origin_owner_sha256"])
        require(origin is not None and origin["origin_owner_sha256"] == origin["owner_sha256"]
            and origin["standard_owner_sha256"] == entry["standard_owner_sha256"] and origin["family"] == entry["family"]
            and all(origin[k] == entry[k] for k in (("pilot_owner_sha256", "pilot_plan_records")
                if entry["family"] == matching.FAMILY else ("plan_records",))), "native_copy_declaration")
    for identity in standards:
        scope = scopes[identity]
        require(scope["record_kinds"].get("luna_standard_assessment") in inventory.CATEGORIES - {"out_of_scope"}, "standard_record_scope")
        require(STANDARD_RULES <= {(r["origin"], r["kind"], tuple(r["paths"])) for r in scope["artifact_rules"] if r["required"]}, "standard_artifact_scope")
    return by_owner


def normalize_source(entry, owners, index):
    owner = owners[entry["owner_sha256"]]
    if entry["family"] == adapter.FAMILY:
        require(sorted(r["id"] for r in owner.records if r["kind"] == "representation_plan") == entry["plan_records"], "exact_plan_set")
        return adapter.normalize_representation_history(owner, index,
            origin_owner=owners[entry["origin_owner_sha256"]], standard_owner=owners[entry["standard_owner_sha256"]])
    require(entry["family"] == matching.FAMILY, "unsupported_family")
    pilot = owners[entry["pilot_owner_sha256"]]
    require(sorted(r["id"] for r in pilot.records if r["kind"] == "luna_matching_pilot_plan") == entry["pilot_plan_records"], "exact_pilot_plan_set")
    for row in owner.events:
        if row["kind"] == "model.attempt.intended":
            payload = json.loads(row["payload"])
            if payload.get("task_key") == matching.FAMILY:
                require(payload.get("parent_plan") in entry["pilot_plan_records"], "attempt_pilot_plan_binding")
    return matching.normalize_matching_history(owner, index, origin_owner=owners[entry["origin_owner_sha256"]],
        pilot_owner=pilot, standard_owner=owners[entry["standard_owner_sha256"]])


def verify_physical_origins(owners, entries):
    """An identical durable intent cannot become two native physical events."""
    origins = {}
    for entry in entries:
        for row in owners[entry["owner_sha256"]].events:
            if row["kind"] == "model.attempt.intended":
                old = origins.setdefault(row["event_hash"], entry["origin_owner_sha256"])
                require(old == entry["origin_owner_sha256"], "copied_intent_conflicting_origins")


def result_counts(owners, sources, read):
    physical = {p["physical_id"] for s in sources
        for p in read(s["pair_attempt_bindings_artifact"]) if p["physical_id"] is not None}
    return {"declared_owners": len(owners), "representation_views": sum(s["family"] == adapter.FAMILY for s in sources),
        "matching_views": sum(s["family"] == matching.FAMILY for s in sources),
        "reference_batch_views": sum(read(s["manifest_artifact"])["reference_physical_batches"] for s in sources),
        "verified_distinct_reference_batches": len(physical),
        "logical_pair_views": sum(len(read(s["pair_attempt_bindings_artifact"])) for s in sources)}


class BatchHistoryParent(task.TaskCensusParent):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "binding", "declaration"}, "offline_operation")
        require(data["action"] in {"collect", "status", "lookup"}, "offline_action")
        require(set(data["binding"]) == {"task_census_record", "task_census_binding"}, "binding_fields")
        binding(**data["binding"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _upstream(self, selected):
        selected_task = selected["task_census_binding"]
        chain = self._chain(selected_task)
        snapshot, index, prepared, reconciled, registry, _ = chain
        row = self._one(task.RESULT)
        require(row["id"] == selected["task_census_record"], "completed_task_census_required")
        intent = self.ledger.get(row["payload"]["intent_record"], task.INTENT)
        desired = {"method": task.METHOD, "binding": selected_task, "implementation": task.implementation(), "policy": task.POLICY,
            "upstream": {"preparation_artifact": digest(prepared), "reconciliation_artifact": digest(reconciled),
                "registry_artifact": digest(registry), "schedule_seed_artifact": prepared["schedule_seed_artifact"],
                "article_order_seed_artifact": prepared["article_order_seed_artifact"],
                "prior_inventory": reconciled["artifacts"]["prior_inventory"],
                "no_retry_inventory": reconciled["artifacts"]["pair_history_inventory"]}}
        require(digest(intent) == digest(desired), "task_census_intent_changed")
        verified = task.TaskCensusParent._verified(self, row, desired, row["payload"]["intent_record"])
        return snapshot, index, prepared, registry, verified

    def _desired(self, selected, declaration, upstream):
        _, _, prepared, _, census = upstream
        return {"method": METHOD, "binding": selected, "implementation": implementation(), "policy": POLICY,
            "declaration_artifact": digest(declaration), "task_census_artifact": digest(census),
            "schedule_seed_artifact": prepared["schedule_seed_artifact"],
            "article_order_seed_artifact": prepared["article_order_seed_artifact"],
            "inherited_no_retry_inventory": census["artifacts"]["unchanged_no_retry_inventory"]}

    def _retained_owner(self, saved):
        read = self.ledger.artifacts.read
        refs = saved["classifier_input_artifacts"]
        raw = {ref: self.ledger.artifacts.read_bytes(ref) for ref in refs["permitted_artifacts"]}
        return task.parent.reconciliation.inventory.HistoryOwner(None, read(saved["scope_artifact"]),
            read(refs["events"]), read(refs["records"]), MappingProxyType(raw), read(refs["census"]), read(refs["gaps"]))

    def _verify_batch(self, value, desired, declaration, index):
        require(value["method"] == METHOD and value["binding"] == desired["binding"]
            and value["implementation"] == desired["implementation"]
            and all(value.get(k) == v for k, v in POLICY.items()), "result_binding")
        intent = self.ledger.get(value["intent_record"], INTENT)
        require(digest(intent) == digest(desired), "result_intent")
        for key in ("declaration_artifact", "task_census_artifact", "schedule_seed_artifact", "article_order_seed_artifact", "inherited_no_retry_inventory"):
            require(value[key] == desired[key], "upstream_binding")
        protocol = self.ledger.get(value["versions"]["protocol"], "protocol")["content"]
        require(protocol == {"method": METHOD, "implementation": desired["implementation"],
            "intent_record": value["intent_record"], "declaration_artifact": digest(declaration),
            "binding_sha256": digest(desired["binding"])}, "result_protocol")
        for ref in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(ref)
        proof = self.ledger.get(value["inventory"]["inventory_record"], task.parent.reconciliation.inventory.RESULT_KIND)
        require(digest(proof) == value["inventory"]["inventory_artifact"]
            and proof["binding"] == self.ledger.artifacts.read(value["read_binding_artifact"])
            and proof["binding"]["owners"] == declaration["owners"] and proof["binding"]["declared_gaps"] == []
            and proof["binding"]["snapshot_binding"] == desired["binding"]["task_census_binding"]["preparation_binding"]["snapshot_binding"]
            and proof["source_head_stable"] and proof["full_declared_source_ledger_preflight_verified"], "completed_inventory_proof")
        proof_owners = {p["census"]["owner_sha256"]: p for p in proof["owners"]}
        require(set(proof_owners) == set(value["full_census_by_owner"])
            == {digest(s["source_owner"]) for s in declaration["owners"]}, "owner_partition")
        owners = {}
        for identity, saved in value["full_census_by_owner"].items():
            p, refs = proof_owners[identity], saved["classifier_input_artifacts"]
            require(refs["events"] == p["events_artifact"] and refs["records"] == p["records_artifact"]
                and refs["gaps"] == p["gaps_artifact"] and refs["census"] == digest(p["census"])
                and refs["permitted_artifacts"] == p["permitted_source_artifacts"]
                and saved["scope_artifact"] == p["census"]["scope_sha256"], "adapter_input_proof")
            child = self.ledger.get(saved["full_census"]["record"], task.full.RESULT)
            require(digest(child) == saved["full_census"]["artifact"]
                and child["method"] == task.full.METHOD and child["implementation"] == task.full.implementation()
                and child["owner_sha256"] == identity
                and child["original_scoped_census_artifact"] == refs["census"]
                and child["declared_history_scope_sha256"] == saved["scope_artifact"]
                and child["source_head"] == p["census"]["source_head"], "full_census_proof")
            owners[identity] = self._retained_owner(saved)
        expected = {e["owner_sha256"]: e for e in declared_entries(declaration)}
        verify_physical_origins(owners, list(expected.values()))
        require(len(value["sources"]) == len(expected) and {s["owner_sha256"] for s in value["sources"]} == set(expected), "source_partition")
        for source in value["sources"]:
            entry = expected[source["owner_sha256"]]
            require(all(source[k] == entry[k] for k in entry), "source_declaration")
            normalized = normalize_source(entry, owners, index)
            for name in ("manifest", "observations", "source_contribution", "pair_attempt_bindings", "inventory_certificate"):
                expected_value = getattr(normalized, name)
                require(digest(expected_value) == source[name + "_artifact"], "normalized_artifact_changed")
            owner_refs = value["full_census_by_owner"][source["owner_sha256"]]
            require(all(source[k] == owner_refs[k] for k in ("scope_artifact", "classifier_input_artifacts", "full_census")), "source_input_binding")
        require(digest(value["counts"]) == digest(result_counts(owners, value["sources"], self.ledger.artifacts.read)), "result_counts")

    def load_completed(self, record_id):
        """Verify immutable completed authority; no current source observation."""
        row = self._one(RESULT)
        require(row["id"] == record_id, "unique_completed_result")
        value = row["payload"]
        upstream = self._upstream(value["binding"])
        declaration = self.ledger.artifacts.read(value["declaration_artifact"])
        validate_declaration(declaration, upstream[1], main_owner=self.source_owner,
            observer_owner=self.ledger.root.resolve(), prior_registry=upstream[3])
        self._verify_batch(value, self._desired(value["binding"], declaration, upstream), declaration, upstream[1])
        return value, upstream[1]

    def _summary(self, record_id, *, reused):
        value, _ = self.load_completed(record_id)
        return {"batch_history_record": record_id, "batch_history_artifact": digest(value), "method": METHOD,
            **POLICY, "counts": value["counts"], "inherited_no_retry_inventory": value["inherited_no_retry_inventory"],
            "reused_historical_result": reused, "current_source_quiescence_verified": not reused}

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data.get("method") == METHOD, "offline_entry")
        selected, declaration = data["binding"], data["declaration"]
        upstream = self._upstream(selected)
        snapshot, index, _, registry, _ = upstream
        entries = validate_declaration(declaration, index, main_owner=self.source_owner,
            observer_owner=self.ledger.root.resolve(), prior_registry=registry)
        desired = self._desired(selected, declaration, upstream)
        old, completed = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        if old:
            require(digest(old["payload"]) == digest(desired), "changed_scope_requires_amendment")
        if data["action"] == "lookup":
            require(completed is not None, "collect_before_lookup")
            import final_validation_batch_pair_lookup as lookup
            protocol = self._version_once(session, context, "protocol", lookup.METHOD,
                lookup.protocol_content(self, session, completed["id"]))
            return lookup.derive_pair_lookup(self, session, record_id=completed["id"], protocol_record=protocol)
        if completed:
            return self._summary(completed["id"], reused=True)
        if data["action"] == "status":
            return {"method": METHOD, **POLICY, "collected": False, "incomplete_operation": old is not None}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        versions = {}
        for kind, value in {"protocol": {"method": METHOD, "implementation": desired["implementation"],
                "intent_record": intent, "declaration_artifact": digest(declaration), "binding_sha256": digest(selected)},
                "selection": {"intent_record": intent, "rules": "Exact declared representation/matching plans, native/copy origins and original pilot/Standard cutoffs."},
                "policy": {"intent_record": intent, **POLICY}}.items():
            versions[kind] = self._version_once(session, context, kind, METHOD, value)
        retained = set()
        def put(value):
            ref = self.ledger.artifacts.put(value)
            retained.add(ref)
            return ref
        declaration_ref = put(declaration)
        read_binding = {"snapshot_binding": selected["task_census_binding"]["preparation_binding"]["snapshot_binding"],
            "owners": declaration["owners"], "declared_gaps": [], "registry_declaration_artifact": put({
                "snapshot_binding": selected["task_census_binding"]["preparation_binding"]["snapshot_binding"],
                "owners_sha256": digest(declaration["owners"]), "declared_gaps": [],
                "scope": "explicit_recorded_study_sources_only", "universal_history_completeness_claimed": False})}
        inventory = task.parent.reconciliation.inventory
        ctx = self._reader_versions(session, context, module=inventory, selected=read_binding,
            protocol=versions["protocol"], label="batch-history")
        owner_values, outputs = {}, []
        with inventory.open_history_inventory(self, session, ctx, read_binding,
                observe_liveness=lambda path: self.observer.observe(self, session, path)) as reader:
            by_owner = {o.census["owner_sha256"]: o for o in reader.owners}
            verify_physical_origins(by_owner, list(entries.values()))
            for identity, owner in by_owner.items():
                protocol = self._version_once(session, context, "protocol", METHOD + ":full:" + identity,
                    task.full.protocol_content(owner))
                full = task.full.collect_full_history_census(owner, protocol_record=protocol)
                child = self.ledger.get(full["record"], task.full.RESULT)
                for ref in (child["events_artifact"], child["records_artifact"], full["artifact"]):
                    self.ledger.artifacts.read_bytes(ref)
                    retained.add(ref)
                permitted = sorted(owner.artifacts.permitted)
                for ref in permitted:
                    require(self.ledger.artifacts.put_bytes(owner.artifacts[ref]) == ref, "copied_input_artifact_changed")
                    retained.add(ref)
                owner_values[identity] = {"scope_artifact": put(owner.scope), "full_census": full,
                    "classifier_input_artifacts": {"events": put(owner.events), "records": put(owner.records),
                        "census": put(owner.census), "gaps": put(owner.gaps), "permitted_artifacts": permitted}}
            for identity, entry in entries.items():
                result = normalize_source(entry, by_owner, index)
                outputs.append({**entry, **owner_values[identity], **{name + "_artifact": put(getattr(result, name))
                    for name in ("manifest", "observations", "source_contribution", "pair_attempt_bindings", "inventory_certificate")}})
        require(reader.result is not None, "completed_inventory_required")
        counts = result_counts(owner_values, outputs, self.ledger.artifacts.read)
        # Existing prior scopes stay fixed; new owners add locks, never replace
        # them. Repeated physical paths require the same immutable head.
        scopes = {s["source_owner"]: s for s in [*registry["owners"], *declaration["owners"]]}
        guard_registry = {**registry, "owners": list(scopes.values())}
        with self._commit_guard(session, snapshot, guard_registry):
            require(implementation() == desired["implementation"], "implementation_changed")
            value = {"method": METHOD, **POLICY, "binding": selected, "implementation": desired["implementation"],
                "intent_record": intent, "versions": versions, "declaration_artifact": declaration_ref,
                "task_census_artifact": desired["task_census_artifact"], "inventory": reader.result,
                "read_binding_artifact": put(read_binding), "full_census_by_owner": owner_values,
                "sources": outputs, "counts": counts,
                **{k: desired[k] for k in ("schedule_seed_artifact", "article_order_seed_artifact", "inherited_no_retry_inventory")},
                "retained_artifacts": sorted(retained),
                "limitations": "Exact declared family contribution. Native/copy declarations are checked against retained evidence, not externally attested. Standard lineage verifies retained source versions, not original websites. Unselected/manual metadata and other owner discovery remain unresolved. Multiple logical pairs share one physical batch; no current Y or independent-attempt fiction is created."}
            self._verify_batch(value, desired, declaration, index)
            record_id = self.ledger.record(session, RESULT, intent, value)
        return self._summary(record_id, reused=False)
