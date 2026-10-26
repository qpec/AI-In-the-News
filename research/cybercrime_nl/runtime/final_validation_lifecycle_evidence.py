"""Supplemental lifecycle bytes at a completed task-census cutoff.

This is evidence retention, never a purpose classifier or no-retry clearance.
The original census and all its unresolved rows stay unchanged. The enclosing
history reader must finish its source-head/liveness guards before a parent may
use a child result. Operation inputs/results can contain manual research and
must receive separate producer-specific dispositions.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import final_validation_full_history_census as full
import final_validation_task_census_parent as task
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-lifecycle-evidence-v1"
CHILD = "cyber_final_validation_lifecycle_evidence"
INTENT = "cyber_final_validation_lifecycle_intent"
RESULT = "cyber_final_validation_lifecycle_collection"
REFERENCE_FIELDS = {"session.started": "identity", "operation.intended": "input",
    "operation.completed": "result"}
POLICY = {"offline_only": True, "new_model_calls": 0, "dispatch_authorized": False,
    "source_mutations": 0, "classifies_task_purpose": False,
    "discharges_history_gaps": False, "original_task_census_unchanged": True}


def require(value, reason):
    if not value:
        raise AuditError("lifecycle_evidence_" + reason)


def implementation():
    path = Path(__file__)
    return {**task.implementation(), path.relative_to(task.parent.study.ROOT).as_posix():
        hashlib.sha256(path.read_bytes()).hexdigest()}


def _task(engine, identifier):
    saved = engine.ledger.get(identifier, task.RESULT)
    intended = engine.ledger.get(saved["intent_record"], task.INTENT)
    require(intended["implementation"] == task.implementation(), "task_implementation")
    task.TaskCensusParent._verified(engine, {"payload": saved}, intended, saved["intent_record"])
    return saved


def _reference_rows(events):
    rows, gaps = [], []
    for event in events:
        field = REFERENCE_FIELDS.get(event["kind"])
        if field is None:
            continue
        value = json.loads(event["payload"])
        reference = value.get(field)
        try:
            task.parent.source._sha(reference)
        except (AuditError, TypeError):
            gaps.append({"event_hash": event["event_hash"], "reason": "unsupported_reference_envelope"})
            continue
        rows.append({"event_hash": event["event_hash"], "session_id": event["session_id"],
            "kind": event["kind"], "field": field, "artifact": reference})
    return rows, gaps


def _binding(*, task_census_record, full_census_record, owner_sha256, source_head, scope_sha256):
    return {"method": METHOD, "implementation": implementation(),
        "task_census_record": task_census_record, "full_census_record": full_census_record,
        "owner_sha256": owner_sha256, "source_head": source_head,
        "declared_history_scope_sha256": scope_sha256,
        "reference_fields": REFERENCE_FIELDS, "recursive_artifact_traversal": False,
        "policy": POLICY}


def protocol_content(owner, *, task_census_record, full_census_record):
    base = full.protocol_content(owner)  # Concrete locked source and active session.
    return _binding(task_census_record=task_census_record, full_census_record=full_census_record,
        owner_sha256=base["owner_sha256"], source_head=base["source_head"],
        scope_sha256=base["declared_history_scope_sha256"])


def collect(owner, *, task_census_record, full_census_record, protocol_record):
    expected = protocol_content(owner, task_census_record=task_census_record,
        full_census_record=full_census_record)
    source = owner.source
    engine, session = source.engine, source.session
    require_active(engine, session)
    require(engine.config.offline, "offline_required")
    require(engine.ledger.get(protocol_record, "protocol")["content"] == expected, "registered_protocol")
    saved = _task(engine, task_census_record)
    history = engine.ledger.artifacts.read(saved["artifacts"]["history"])
    matches = [r for r in history["owners"] if r["owner_sha256"] == expected["owner_sha256"]]
    require(len(matches) == 1 and matches[0]["full_census"]["record"] == full_census_record
        and matches[0]["source_head"] == expected["source_head"]
        and matches[0]["scope_artifact"] == expected["declared_history_scope_sha256"], "task_owner_binding")
    census = engine.ledger.get(full_census_record, full.RESULT)
    events = engine.ledger.artifacts.read(census["events_artifact"])
    records = engine.ledger.artifacts.read(census["records_artifact"])
    require(digest(census) == matches[0]["full_census"]["artifact"]
        and source.head() == expected["source_head"]
        and events == [dict(r) for r in source.db.execute("SELECT * FROM events ORDER BY seq")]
        and records == [dict(r) for r in source.db.execute("SELECT * FROM records ORDER BY created_event")],
        "exact_retained_census")
    intent = engine.ledger.record(session, INTENT, digest(expected),
        {"binding": expected, "protocol_record": protocol_record})
    rows, gaps = _reference_rows(events)
    for row in rows:
        raw = source.artifact_bytes(row["artifact"])
        require(engine.ledger.artifacts.put_bytes(raw) == row["artifact"], "exact_artifact_retention")
    projection = {"owner_sha256": expected["owner_sha256"], "source_head": expected["source_head"],
        "events_artifact": census["events_artifact"], "records_artifact": census["records_artifact"],
        "references": rows, "unresolved_reference_envelopes": gaps,
        "operation_payload_purpose_requires_separate_proof": True,
        "runtime_identity_is_not_proof_of_task_semantics": True}
    require(source.head() == expected["source_head"] and implementation() == expected["implementation"],
        "source_or_code_changed")
    value = {"method": METHOD, **POLICY, "binding": expected, "intent_record": intent,
        "protocol_record": protocol_record, "projection_artifact": engine.ledger.artifacts.put(projection),
        "parent_final_inventory_proof_required": True}
    identifier = engine.ledger.record(session, CHILD, intent, value)
    return {"record": identifier, "artifact": digest(value), "owner_sha256": expected["owner_sha256"],
        "source_head": expected["source_head"], "reference_count": len(rows), "gap_count": len(gaps)}


def replay(engine, reference, *, task_census_record):
    """Reverify retained child evidence; caller still needs completed parent proof."""
    value = engine.ledger.get(reference["record"], CHILD)
    expected = value["binding"]
    require(digest(value) == reference["artifact"] and value["method"] == METHOD
        and expected["implementation"] == implementation()
        and expected["task_census_record"] == task_census_record
        and all(value.get(k) == v for k, v in POLICY.items()), "child_binding")
    require(engine.ledger.get(value["intent_record"], INTENT) == {
        "binding": expected, "protocol_record": value["protocol_record"]}
        and engine.ledger.get(value["protocol_record"], "protocol")["content"] == expected,
        "child_registration")
    census = engine.ledger.get(expected["full_census_record"], full.RESULT)
    events = engine.ledger.artifacts.read(census["events_artifact"])
    rows, gaps = _reference_rows(events)
    projection = engine.ledger.artifacts.read(value["projection_artifact"])
    require(projection == {"owner_sha256": expected["owner_sha256"], "source_head": expected["source_head"],
        "events_artifact": census["events_artifact"], "records_artifact": census["records_artifact"],
        "references": rows, "unresolved_reference_envelopes": gaps,
        "operation_payload_purpose_requires_separate_proof": True,
        "runtime_identity_is_not_proof_of_task_semantics": True}, "projection_replay")
    for row in rows:
        engine.ledger.artifacts.read_bytes(row["artifact"])
    return projection


class LifecycleParent(task.TaskCensusParent):
    """Optional supplemental offline stage after the exact TaskCensus result."""
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "task_census_record"}
            and data["action"] in {"collect", "status"}, "offline_operation")
        task.parent.source._sha(data["task_census_record"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _verify(self, value, selected):
        saved = _task(self, selected)
        history = self.ledger.artifacts.read(saved["artifacts"]["history"])
        require(value["method"] == METHOD and all(value.get(k) == v for k, v in POLICY.items())
            and value["binding"] == {"task_census_record": selected, "task_census_artifact": digest(saved),
            "implementation": implementation(), "policy": POLICY}, "result_binding")
        binding = value["binding"]
        require(self.ledger.get(value["intent_record"], INTENT) == binding
            and self.ledger.get(value["protocol_record"], "protocol")["content"] == {"method": METHOD, **binding},
            "parent_registration")
        proof = self.ledger.get(value["inventory_proof"]["inventory_record"],
            task.parent.reconciliation.inventory.RESULT_KIND)
        require(digest(proof) == value["inventory_proof"]["inventory_artifact"]
            and proof["binding"] == self.ledger.artifacts.read(history["read_binding"])
            and proof["source_head_stable"] and proof["full_declared_source_ledger_preflight_verified"],
            "completed_inventory_proof")
        children = value["children"]
        require(len(children) == len(history["owners"])
            and {c["owner_sha256"] for c in children} == {r["owner_sha256"] for r in history["owners"]},
            "full_owner_partition")
        by_owner = {r["owner_sha256"]: r for r in history["owners"]}
        for child in children:
            projection = replay(self, child, task_census_record=selected)
            original = by_owner[child["owner_sha256"]]
            raw = self.ledger.get(child["record"], CHILD)
            require(raw["binding"] == _binding(task_census_record=selected,
                    full_census_record=original["full_census"]["record"], owner_sha256=original["owner_sha256"],
                    source_head=original["source_head"], scope_sha256=original["scope_artifact"])
                and projection["owner_sha256"] == child["owner_sha256"]
                and projection["source_head"] == original["source_head"] == child["source_head"]
                and child["reference_count"] == len(projection["references"])
                and child["gap_count"] == len(projection["unresolved_reference_envelopes"]), "child_cutoff")
        return value

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data["method"] == METHOD, "offline_required")
        selected = data["task_census_record"]
        saved = _task(self, selected)
        old = self._one(RESULT, optional=True)
        if old:
            self._verify(old["payload"], selected)
            return {"lifecycle_record": old["id"], **POLICY, "reused_historical_evidence": True}
        if data["action"] == "status":
            return {"collected": False, **POLICY}
        require(type(self.observer) is task.parent.study.WindowsProcessObserver, "concrete_process_observer")
        chain = self._chain(saved["binding"])
        snapshot, _, _, _, registry, _ = chain
        binding = {"task_census_record": selected, "task_census_artifact": digest(saved),
            "implementation": implementation(), "policy": POLICY}
        intent = self.ledger.record(session, INTENT, METHOD, binding)
        protocol = self._version_once(session, context, "protocol", METHOD, {"method": METHOD, **binding})
        history = self.ledger.artifacts.read(saved["artifacts"]["history"])
        read_binding = self.ledger.artifacts.read(history["read_binding"])
        module = task.parent.reconciliation.inventory
        ctx = self._reader_versions(session, context, module=module, selected=read_binding,
            protocol=protocol, label="lifecycle-supplement")
        children = []
        by_owner = {r["owner_sha256"]: r for r in history["owners"]}
        with module.open_history_inventory(self, session, ctx, read_binding,
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            for owner in reader.owners:
                identity = owner.census["owner_sha256"]
                original = by_owner[identity]
                args = {"task_census_record": selected, "full_census_record": original["full_census"]["record"]}
                child_protocol = self._version_once(session, context, "protocol", METHOD + ":" + identity,
                    protocol_content(owner, **args))
                children.append(collect(owner, **args, protocol_record=child_protocol))
        require(reader.result is not None, "completed_inventory_required")
        value = {"method": METHOD, **POLICY, "binding": binding, "intent_record": intent,
            "protocol_record": protocol, "children": children, "inventory_proof": reader.result}
        with self._commit_guard(session, snapshot, registry):
            self._verify(value, selected)
            identifier = self.ledger.record(session, RESULT, intent, value)
        return {"lifecycle_record": identifier, **POLICY, "reused_historical_evidence": False}
