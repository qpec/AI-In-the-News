"""Fixed native metadata artifacts at an audited main-owner cutoff.

This is a bounded retention supplement, not a semantic classifier. It neither
opens an arbitrary owner nor follows recursive references. All source access is
inside the existing registered locked inventory and its final cutoff guards.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import final_validation_lifecycle_evidence as lifecycle
import run_dossiers_v8 as v8
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-native-artifact-supplement-v1"
INTENT = "final_validation_native_artifact_intent"
RESULT = "final_validation_native_artifact_collection"
POLICY = {"offline_only": True, "new_model_calls": 0, "source_mutations": 0,
    "dispatch_authorized": False, "classifies_task_purpose": False, "discharges_history_gaps": False,
    "recursive_artifact_traversal": False}
RESPONSE_FIELDS = {"plan", "task_key", "phase", "category", "packet", "request", "response", "attempt",
    "parsed", "cost_nanousd", "reserved_nanousd", "hold", "validation_error", "http_status", "at"}
RESPONSE_OPTIONAL = {"execution_amendment", "diagnostic_plan", "parent_diagnostic_plan"}


def require(value, reason):
    if not value:
        raise AuditError("native_artifacts_" + reason)


def implementation():
    path = Path(__file__)
    return {**lifecycle.implementation(), **v8.implementation(),
        path.relative_to(lifecycle.task.parent.study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def raw(row):
    return json.loads(row["payload"])


def references(records, events, dispositions, *, plan, amendment_ids):
    """Derive fixed pointers from exact retained native rows, never caller refs."""
    intents = {raw(e)["attempt"]: e for e in events if e["kind"] == "model.attempt.intended"}
    require(len(intents) == sum(e["kind"] == "model.attempt.intended" for e in events), "unique_intents")
    tasks = {r["original_attempt"]: r for r in dispositions}
    require(len(tasks) == len(dispositions) and set(tasks) == set(intents), "exact_task_partition")
    selected, gaps = [], []
    eligible = {}

    def add(row, field, value, *, nullable=False):
        if nullable and value is None:
            return
        if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
            gaps.append({"record_id": row["id"], "field": field, "reason": "invalid_fixed_artifact_reference"})
            return
        selected.append({"record_id": row["id"], "record_kind": row["kind"], "field": field, "artifact": value})

    for row in records:
        value = raw(row)
        if row["kind"] != "cyber_dossier_response":
            continue
        task = tasks.get(value.get("attempt"))
        intended = raw(intents[value["attempt"]]) if task else {}
        if not (task and task.get("response_record") == row["id"] and RESPONSE_FIELDS <= set(value)
                and not set(value) - RESPONSE_FIELDS - RESPONSE_OPTIONAL
                and value["plan"] == intended["batch"] == plan
                and value["task_key"] == intended["task_key"] == task["task_key"] == row["logical_key"]
                and all(digest(value.get(k)) == digest(intended.get(k)) for k in
                    ("packet", "request", "phase", "category", *RESPONSE_OPTIONAL))):
            gaps.append({"record_id": row["id"], "reason": "unsupported_or_unbound_native_response"})
            continue
        eligible[row["id"]] = value
        for field in ("response", "parsed"):
            add(row, field, value[field], nullable=field == "parsed")
        if row["id"] in v8.SOURCE_RESPONSES:
            for field in ("packet", "request"):
                add(row, field, value[field])

    for row in records:
        value = raw(row)
        if row["kind"] == "cyber_dossier_seed_revalidation":
            source = eligible.get(value.get("source_response_record"))
            if (source and value.get("source_response_record") in v8.SOURCE_RESPONSES
                    and value.get("method") == v8.METHOD
                    and value.get("parent_execution_amendment") == v8.PARENT_AMENDMENT
                    and value.get("parent_plan") == plan
                    and all(value.get("source_" + key) == source[key] for key in ("packet", "request", "response"))):
                add(row, "parsed", value.get("parsed"))
            else:
                gaps.append({"record_id": row["id"], "reason": "unsupported_seed_derivation"})
        elif row["kind"] == "cyber_dossier_evidence_card":
            fields = {"dossier_id", "membership_revision", "card_version", "document_ids", "artifact",
                "execution_amendment", "model_generation_calls"}
            if (set(value) == fields and value["execution_amendment"] in amendment_ids
                    and row["logical_key"] == digest([value["dossier_id"], value["membership_revision"]])
                    and type(value["model_generation_calls"]) is int and value["model_generation_calls"] == 0):
                add(row, "artifact", value["artifact"])
            else:
                gaps.append({"record_id": row["id"], "reason": "unsupported_card_projection"})
    return selected, gaps


def evidence(engine, task_record, lifecycle_record):
    """Replay both completed upstream producers; no source access here."""
    life = engine._one(lifecycle.RESULT)
    require(life["id"] == lifecycle_record, "unique_lifecycle")
    lifecycle.LifecycleParent._verify(engine, life["payload"], task_record)
    task = lifecycle._task(engine, task_record)
    chain = engine._chain(task["binding"])
    snapshot, _, _, _, registry, _ = chain
    main = engine.ledger.artifacts.read(task["artifacts"]["main"])
    children = [r for r in life["payload"]["children"] if r["owner_sha256"] == main["owner_sha256"]]
    require(len(children) == 1 and children[0]["source_head"] == snapshot["source_bindings"]["source_head"], "main_lifecycle_cutoff")
    projected = lifecycle.replay(engine, children[0], task_census_record=task_record)
    read = engine.ledger.artifacts.read
    records, events = read(projected["records_artifact"]), read(projected["events_artifact"])
    manifest = read(main["manifest"])
    refs, gaps = references(records, events, read(main["dispositions"]), plan=manifest["plan"],
        amendment_ids={r["id"] for r in snapshot["source_bindings"]["amendments"]})
    binding = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
        "task_census_record": task_record, "task_census_artifact": digest(task), "lifecycle_record": lifecycle_record,
        "lifecycle_artifact": digest(life["payload"]), "main_owner_sha256": main["owner_sha256"],
        "source_head": snapshot["source_bindings"]["source_head"], "records_artifact": projected["records_artifact"],
        "events_artifact": projected["events_artifact"], "references_sha256": digest(refs), "gaps_sha256": digest(gaps)}
    return binding, refs, gaps, snapshot, registry, task, records, events


def _verify_value(engine, value, inputs):
    expected, refs, gaps, snapshot, _, task, records, _ = inputs
    require(digest(value["binding"]) == digest(expected) and value["method"] == METHOD
        and digest({k: value.get(k) for k in POLICY}) == digest(POLICY), "result_binding")
    require(engine.ledger.get(value["intent_record"], INTENT) == expected
        and engine.ledger.get(value["protocol_record"], "protocol")["content"] == {"method": METHOD, "binding": expected},
        "registered_binding")
    read = engine.ledger.artifacts.read
    require(read(value["references_artifact"]) == refs and read(value["gaps_artifact"]) == gaps
        and type(value["reference_count"]) is int and type(value["gap_count"]) is int
        and value["reference_count"] == len(refs) and value["gap_count"] == len(gaps), "exact_reference_manifest")
    scope = lifecycle.task.main_metadata_scope(snapshot)
    declaration = {"snapshot_binding": task["binding"]["preparation_binding"]["snapshot_binding"],
        "owners_sha256": digest([scope]), "declared_gaps": [], "scope": "explicit_recorded_study_sources_only",
        "universal_history_completeness_claimed": False}
    expected_read = {"snapshot_binding": declaration["snapshot_binding"], "owners": [scope], "declared_gaps": [],
        "registry_declaration_artifact": digest(declaration)}
    require(read(value["reader_binding_artifact"]) == expected_read and read(digest(declaration)) == declaration,
        "derived_reader_scope")
    module = lifecycle.task.parent.reconciliation.inventory
    proof = engine.ledger.get(value["inventory_proof"]["inventory_record"], module.RESULT_KIND)
    require(digest(proof) == value["inventory_proof"]["inventory_artifact"] and proof["binding"] == expected_read
        and proof["method"] == module.METHOD and proof["implementation"] == module.implementation()
        and proof["input_index_digest"] == snapshot["input_index_digest"]
        and proof["source_head_stable"] and proof["full_declared_source_ledger_preflight_verified"]
        and proof["main_final_cutoff_guard"]["source_head"] == expected["source_head"]
        and proof["main_final_cutoff_guard"]["head_stable"], "completed_reader_proof")
    require(len(proof["owners"]) == 1 and proof["owners"][0]["census"]["owner_sha256"] == expected["main_owner_sha256"]
        and proof["owners"][0]["census"]["source_head"] == expected["source_head"]
        and read(proof["owners"][0]["records_artifact"]) == records, "exact_reader_owner")
    require(engine.ledger.get(proof["versions"]["protocol"], "protocol")["content"] == {
        "binding_sha256": digest(expected_read), "parent_protocol": value["protocol_record"],
        "method": module.METHOD, "implementation": module.implementation()}, "registered_reader_protocol")
    for ref in {r["artifact"] for r in refs}:
        engine.ledger.artifacts.read_bytes(ref)
    return value, refs


def verify_completed(engine, task_record, lifecycle_record, supplement_record):
    inputs = evidence(engine, task_record, lifecycle_record)
    saved = engine._one(RESULT)
    require(saved["id"] == supplement_record, "unique_supplement")
    return _verify_value(engine, saved["payload"], inputs)


class NativeArtifactParent(lifecycle.LifecycleParent):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "task_census_record", "lifecycle_record"}
            and data["action"] in {"collect", "status"}, "offline_operation")
        for key in ("task_census_record", "lifecycle_record"):
            lifecycle.task.parent.source._sha(data[key])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_required")
        selected = data["task_census_record"], data["lifecycle_record"]
        expected, refs, gaps, snapshot, registry, task, records, events = evidence(self, *selected)
        old = self._one(RESULT, optional=True)
        if old:
            verify_completed(self, *selected, old["id"])
            return {"supplement_record": old["id"], **POLICY, "reused_historical_evidence": True}
        if data["action"] == "status":
            return {"collected": False, **POLICY}
        require(type(self.observer) is lifecycle.task.parent.study.WindowsProcessObserver, "concrete_observer")
        intended = self._one(INTENT, optional=True)
        require(intended is None or intended["payload"] == expected, "changed_binding")
        intent = intended["id"] if intended else self.ledger.record(session, INTENT, METHOD, expected)
        protocol = self._version_once(session, context, "protocol", METHOD, {"method": METHOD, "binding": expected})
        scope = lifecycle.task.main_metadata_scope(snapshot)
        declaration = {"snapshot_binding": task["binding"]["preparation_binding"]["snapshot_binding"],
            "owners_sha256": digest([scope]), "declared_gaps": [], "scope": "explicit_recorded_study_sources_only",
            "universal_history_completeness_claimed": False}
        binding = {"snapshot_binding": declaration["snapshot_binding"], "owners": [scope], "declared_gaps": [],
            "registry_declaration_artifact": self.ledger.artifacts.put(declaration)}
        module = lifecycle.task.parent.reconciliation.inventory
        ctx = self._reader_versions(session, context, module=module, selected=binding, protocol=protocol, label="native-artifacts")
        with module.open_history_inventory(self, session, ctx, binding,
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            require(len(reader.owners) == 1, "one_main_reader")
            owner = reader.owners[0]
            source = owner.source
            require(owner.census["owner_sha256"] == expected["main_owner_sha256"]
                and source.head() == expected["source_head"]
                and records == [dict(r) for r in source.db.execute("SELECT * FROM records ORDER BY created_event")]
                and events == [dict(r) for r in source.db.execute("SELECT * FROM events ORDER BY seq")], "exact_main_census")
            for ref in sorted({r["artifact"] for r in refs}):
                # The separately registered fixed manifest is the authority for
                # these exact non-recursive reads; generic reader scope is unchanged.
                require(self.ledger.artifacts.put_bytes(source.artifact_bytes(ref)) == ref, "exact_artifact_bytes")
        require(reader.result is not None and implementation() == expected["implementation"], "completed_unchanged_inventory")
        value = {"method": METHOD, **POLICY, "binding": expected, "intent_record": intent, "protocol_record": protocol,
            "references_artifact": self.ledger.artifacts.put(refs), "gaps_artifact": self.ledger.artifacts.put(gaps),
            "reference_count": len(refs), "gap_count": len(gaps), "reader_binding_artifact": self.ledger.artifacts.put(binding),
            "inventory_proof": reader.result}
        with self._commit_guard(session, snapshot, registry):
            _verify_value(self, value, (expected, refs, gaps, snapshot, registry, task, records, events))
            identifier = self.ledger.record(session, RESULT, intent, value)
        return {"supplement_record": identifier, **POLICY, "reused_historical_evidence": False,
            "reference_count": len(refs), "gap_count": len(gaps)}
