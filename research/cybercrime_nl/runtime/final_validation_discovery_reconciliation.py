"""Audited metadata import, followed only on request by immutable reconciliation.

The imported registry is the exact conservative RootDiscovery projection. Names
do not establish origins, task purpose, or complete history. Import can be
reviewed before the separate reconcile action fixes that registry permanently.
Historical status replays retained evidence; it never claims fresh quiescence.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import final_validation_root_discovery as discovery
import final_validation_reconciliation as reconciliation
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-discovery-registry-import-v1"
INTENT = "final_validation_discovery_import_intent"
CUTOFF = "final_validation_discovery_import_cutoff"
RESULT = "final_validation_discovery_registry_import"
POLICY = {"source_mutations": 0, "new_model_calls": 0, "new_seed_draws": 0,
    "dispatch_authorized": False, "history_complete": False,
    "root_semantics_resolved": False, "physical_origins_verified": False,
    "registry_modified": False, "article_or_response_bodies_imported": False,
    "discovery_metadata_preflight_only": True}


def require(value, reason):
    if not value:
        raise AuditError("discovery_registry_import_" + reason)


def implementation():
    path = Path(__file__)
    return {**discovery.implementation(), **reconciliation.implementation(),
        path.relative_to(discovery.study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_locator(value):
    require(isinstance(value, dict) and set(value) == {
        "discovery_owner", "discovery_record", "registry_artifact"}, "locator_fields")
    discovery.canonical_path(value["discovery_owner"])
    for field in ("discovery_record", "registry_artifact"):
        discovery.source_api._sha(value[field])


class _LocalMetadata:
    """Trace precisely the unchanged snapshot loader's local metadata reads."""
    def __init__(self, engine, session):
        self.engine, self.session = engine, session
        self.root, self.artifacts = engine.ledger.root, self
        self.records, self.nested = {}, set()

    @property
    def db(self):
        require_active(self.engine, self.session)
        return self.engine.ledger.db

    def get(self, identity, kind=None):
        row = self.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
        require(row is not None and row["kind"] in discovery.METADATA_KINDS, "local_metadata_scope")
        value = self.engine.ledger.get(identity, kind)
        self.records[identity] = {"kind": row["kind"], "artifact": row["artifact"], "created_event": row["created_event"]}
        return value

    def read_bytes(self, reference):
        require_active(self.engine, self.session)
        self.nested.add(reference)
        return self.engine.ledger.artifacts.read_bytes(reference)

    def read(self, reference):
        return json.loads(self.read_bytes(reference))


def local_snapshot_metadata(engine, session, selected):
    ledger = _LocalMetadata(engine, session)
    # Uses the actual current operation and owner; no source session is invented.
    view = SimpleNamespace(ledger=ledger, config=engine.config, _active=engine._active)
    snapshot, index = discovery.snapshot_api.load_snapshot(view, session, selected)
    return snapshot, index, ledger


class _BundleLedger:
    def __init__(self, artifacts, bundle):
        self.artifacts, self.bundle = artifacts, bundle

    def get(self, identity, kind=None):
        row = self.bundle["records"].get(identity)
        require(row is not None and (kind is None or row["kind"] == kind), "retained_record_scope")
        return json.loads(row["payload"])


class _ScopedArtifacts:
    def __init__(self, artifacts, references):
        self.artifacts, self.references = artifacts, frozenset(references)

    def read_bytes(self, reference):
        require(reference in self.references, "retained_artifact_scope")
        return self.artifacts.read_bytes(reference)

    def read(self, reference):
        require(reference in self.references, "retained_artifact_scope")
        return self.artifacts.read(reference)


def _row_identity(row):
    require(set(row) == {"id", "kind", "logical_key", "payload", "artifact", "created_event", "supersedes"}, "record_fields")
    require(row["supersedes"] is None and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"]
        and row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
            "payload": row["artifact"], "supersedes": None}), "record_identity")


def verify_bundle(engine, session, bundle, selected, locator):
    """Reverify retained metadata against the real local Study/snapshot loader."""
    require_active(engine, session)
    require(set(bundle) == {"source_owner", "source_head", "metadata", "records", "session_events", "artifacts"}, "bundle_fields")
    require(bundle["source_owner"] == locator["discovery_owner"], "discovery_owner_changed")
    artifacts = _ScopedArtifacts(engine.ledger.artifacts, bundle["artifacts"])
    for reference in bundle["artifacts"]:
        artifacts.read_bytes(reference)
    metadata = bundle["metadata"]
    require(metadata["source_owner"] == bundle["source_owner"]
        and metadata["source_head"] == bundle["source_head"]
        and metadata["owner_sha256"] == digest(bundle["source_owner"])
        and metadata["metadata_chain_and_projection_verified"] is True
        and metadata["full_source_ledger_preflight_verified"] is False, "discovery_metadata_binding")
    rows = bundle["records"]
    for identity, row in rows.items():
        _row_identity(row)
        require(row["id"] == identity and artifacts.read_bytes(row["artifact"]) == row["payload"].encode(), "retained_projection")
        item = {"record_id": identity, "kind": row["kind"], "artifact": row["artifact"],
            "logical_key_sha256": digest(row["logical_key"]), "created_event": row["created_event"]}
        require(metadata["records"].count(item) == 1, "record_not_in_cutoff")
    result_row = rows[locator["discovery_record"]]
    require(result_row["kind"] == discovery.RESULT, "discovery_result_kind")
    value = json.loads(result_row["payload"])
    require(value["registry_artifact"] == locator["registry_artifact"], "registry_substitution")
    expected_ids = {locator["discovery_record"], value["intent_record"], value["protocol_record"], *value["cutoff_records"]}
    require(set(rows) == expected_ids and len(value["cutoff_records"]) == len(set(value["cutoff_records"])), "exact_source_records")
    for kind, identity in ((discovery.RESULT, locator["discovery_record"]), (discovery.INTENT, value["intent_record"])):
        require([r["record_id"] for r in metadata["records"] if r["kind"] == kind] == [identity], "unique_completed_discovery")
    intent, protocol = rows[value["intent_record"]], rows[value["protocol_record"]]
    version = json.loads(protocol["payload"])
    require(intent["logical_key"] == discovery.METHOD and protocol["kind"] == "protocol"
        and protocol["logical_key"] == discovery.METHOD and version["branch"] == "main" and version["reason"] is None
        and result_row["logical_key"] == intent["id"]
        and intent["created_event"] < protocol["created_event"] < result_row["created_event"], "discovery_registration_order")
    require([r["record_id"] for r in metadata["records"] if r["kind"] == "protocol"
        and r["logical_key_sha256"] == digest(discovery.METHOD)] == [protocol["id"]], "unique_discovery_protocol")
    shadow = SimpleNamespace(ledger=_BundleLedger(artifacts, bundle))
    summary = discovery.RootDiscovery._summary(shadow, result_row["id"], value, reused=False)
    binding = value["binding"]
    require(binding["validation_owner"] == str(engine.ledger.root.resolve())
        and binding["snapshot_binding"] == selected["snapshot_binding"], "validation_snapshot_changed")
    catalog_bytes, _ = discovery.closure._catalog()
    require(artifacts.read_bytes(binding["catalog_artifact"]) == catalog_bytes, "catalog_changed")
    snapshot, index, local = local_snapshot_metadata(engine, session, selected["snapshot_binding"])
    proof = artifacts.read(value["snapshot_metadata_artifact"])
    require(proof["validation_owner"] == str(engine.ledger.root.resolve())
        and proof["snapshot_binding"] == selected["snapshot_binding"]
        and proof["source_bindings"] == snapshot["source_bindings"]
        and proof["input_index_digest"] == index.digest
        and proof["study_record"] == selected["study_record"] and proof["seed_record"] == selected["seed_record"]
        and proof["metadata_records"] == local.records
        and proof["nested_metadata_artifacts"] == sorted(local.nested)
        and proof["unchanged_snapshot_loader_verified"] is True
        and proof["source_owner_engine_created"] is False, "local_snapshot_authority")
    validation_metadata = artifacts.read(value["validation_metadata_artifact"])
    require(validation_metadata["source_owner"] == proof["validation_owner"]
        and validation_metadata["source_head"] == proof["validation_head"], "validation_cutoff")
    head = proof["validation_head"]
    prefix = engine.ledger.db.execute("SELECT event_hash FROM events WHERE seq=?", (head[0],)).fetchone()
    require(prefix is not None and prefix[0] == head[1], "validation_prefix_changed")
    owners = [artifacts.read(ref) for ref in value["owner_metadata_artifacts"]]
    require(len({row["source_owner"] for row in owners}) == len(owners), "duplicate_owner_metadata")
    states = artifacts.read(value["root_states_artifact"])
    expected_states = discovery.candidates(discovery.closure._catalog()[1], Path(binding["base_directory"]), Path(snapshot["source_bindings"]["source_owner"]))
    by_path = {row["source_owner"]: row for row in owners}
    cutoffs = {json.loads(rows[identity]["payload"])["source_owner"]: json.loads(rows[identity]["payload"])
        for identity in value["cutoff_records"]}
    require(len(cutoffs) == len(value["cutoff_records"])
        and set(cutoffs) == {proof["validation_owner"], *(r["source_owner"] for r in expected_states if r["source_owner"])}, "cutoff_partition")
    for state in expected_states:
        path = state["source_owner"]
        if path is None:
            continue
        cutoff = cutoffs[path]
        require(cutoff["exists"] is (cutoff["source_head"] is not None), "cutoff_existence")
        if cutoff["exists"]:
            require(path in by_path and by_path[path]["source_head"] == cutoff["source_head"], "owner_cutoff_changed")
            state.update(source_head=cutoff["source_head"], owner_sha256=digest(path), metadata_artifact=digest(by_path[path]))
            if state["root_id"] != "current-main":
                state["discovery_state"] = "observed_candidate_cutoff"
        else:
            require(path not in by_path and state["root_id"] != "current-main", "missing_main_or_present_owner")
            state["discovery_state"] = "declared_candidate_not_present"
    require(states == expected_states and set(by_path) == {r["source_owner"] for r in states if "source_head" in r}
        and cutoffs[proof["validation_owner"]]["source_head"] == head
        and by_path[snapshot["source_bindings"]["source_owner"]]["source_head"] == snapshot["source_bindings"]["source_head"], "root_cutoff_projection")
    # Completion is evidence of the producer's real audited operation, not just
    # the presence of a result-shaped row in the observer's database.
    events = bundle["session_events"]
    require(events and len({e["session_id"] for e in events}) == 1, "discovery_session")
    kinds = {kind: [e for e in events if e["kind"] == kind] for kind in (
        "session.started", "operation.intended", "operation.completed", "session.ended")}
    require(all(len(v) == 1 for v in kinds.values()) and not any(e["kind"] == "operation.failed" for e in events), "discovery_operation_incomplete")
    start, request, complete, end = (kinds[k][0] for k in kinds)
    require(start["seq"] < request["seq"] < result_row["created_event"] < complete["seq"] < end["seq"], "completed_operation_order")
    for event in events:
        copy = dict(event)
        expected = copy.pop("event_hash")
        require(digest(copy) == expected and {"seq": event["seq"], "kind": event["kind"], "event_hash": expected}
            in metadata["events"], "operation_event_binding")
    require(request["payload"]["operation"] == complete["payload"]["operation"] == "status"
        and artifacts.read(request["payload"]["input"]) == {"method": discovery.METHOD, "action": "discover",
            **{key: binding[key] for key in ("base_directory", "validation_owner", "snapshot_binding")}}
        and digest(artifacts.read(complete["payload"]["result"])) == digest(summary)
        and end["payload"] == {"status": "completed"}, "completed_operation_projection")
    observations = artifacts.read(value["liveness_artifact"])
    observed = Counter()
    for observation in observations:
        discovery.source_api._retained_liveness(engine, observation)
        require(observation["inspection_complete"] is True
            and observation["active_writers"] == observation["matching_processes"] == []
            and observation["source_owner"] in {proof["validation_owner"], *by_path}, "discovery_liveness")
        observed[observation["source_owner"]] += 1
    require(observed == Counter({owner: 2 for owner in {proof["validation_owner"], *by_path}}), "discovery_liveness_coverage")
    expected_refs = {r["artifact"] for r in rows.values()} | set(local.nested) | {r["artifact"] for r in local.records.values()}
    expected_refs.update(value[key] for key in ("root_states_artifact", "validation_metadata_artifact",
        "snapshot_metadata_artifact", "registry_artifact", "liveness_artifact"))
    expected_refs.update(value["owner_metadata_artifacts"])
    expected_refs.update((binding["catalog_artifact"], request["payload"]["input"], complete["payload"]["result"], start["payload"]["identity"]))
    expected_refs.update(o["evidence_sha256"] for o in observations)
    require(bundle["artifacts"] == sorted(expected_refs), "exact_artifact_allowlist")
    runtime = artifacts.read(start["payload"]["identity"])
    require(runtime["code_digest"] == digest(runtime["code_files"])
        and all(runtime["code_files"].get(path) == sha for path, sha in discovery.implementation().items()
            if path.startswith("src/") and path.endswith(".py")), "discovery_runtime_identity")
    registry = artifacts.read(value["registry_artifact"])
    reconciliation.validate_registry(registry, index, main_owner=engine.source_owner, observer_owner=engine.ledger.root.resolve())
    return registry, summary, owners


class DiscoveryReconciliation(reconciliation.Reconciliation):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "binding", "discovery"}
            and data["action"] in {"import", "reconcile", "status"}, "entry_shape")
        reconciliation.validate_binding(data["binding"])
        validate_locator(data["discovery"])
        path, here = Path(data["discovery"]["discovery_owner"]), self.ledger.root.resolve()
        require(path != here and path != self.source_owner and path not in here.parents and here not in path.parents,
            "separate_discovery_owner")
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _observe_import(self, session, owner):
        require(type(self.observer) is discovery.study.WindowsProcessObserver, "concrete_observer")
        value = discovery.source_api._liveness(lambda path: self.observer.observe(self, session, path), owner)
        discovery.source_api._retained_liveness(self, value)
        return value

    def _import_protocol(self, identity, desired):
        intent = self._one(INTENT)
        raw_intent = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (intent["id"],)).fetchone()
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        require(len(rows) == 1 and rows[0]["id"] == identity and rows[0]["supersedes"] is None
            and raw_intent["logical_key"] == METHOD and raw_intent["supersedes"] is None
            and intent["payload"] == desired and intent["created_event"] < rows[0]["created_event"], "prospective_import_protocol")
        value = self.ledger.get(identity, "protocol")
        require(value["content"] == desired and value["branch"] == "main" and value["reason"] is None, "import_protocol_content")
        return rows[0]

    def _capture(self, source, locator, local):
        metadata = discovery.metadata_census(source)
        records, refs = {}, set()
        def row(identity, kind):
            saved = source.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
            require(saved is not None and saved["kind"] == kind, "source_record_kind")
            source._row(saved)
            records[identity] = dict(saved)
            refs.add(saved["artifact"])
            return json.loads(saved["payload"])
        value = row(locator["discovery_record"], discovery.RESULT)
        require(value["method"] == discovery.METHOD and value["implementation"] == discovery.implementation()
            and value["policy"] == discovery.POLICY and value["registry_artifact"] == locator["registry_artifact"], "source_producer_binding")
        row(value["intent_record"], discovery.INTENT)
        row(value["protocol_record"], "protocol")
        for identity in value["cutoff_records"]:
            row(identity, discovery.CUTOFF)
        refs.update(value[key] for key in ("root_states_artifact", "validation_metadata_artifact",
            "snapshot_metadata_artifact", "registry_artifact", "liveness_artifact"))
        refs.update(value["owner_metadata_artifacts"])
        refs.add(value["binding"]["catalog_artifact"])
        observations = source.artifact(value["liveness_artifact"])
        refs.update(o["evidence_sha256"] for o in observations)
        # The local original loader, not a source-supplied arbitrary pointer
        # list, defines exactly which nested snapshot metadata may be copied.
        refs.update(local.nested)
        refs.update(r["artifact"] for r in local.records.values())
        created = source.db.execute("SELECT session_id FROM events WHERE seq=?", (records[locator["discovery_record"]]["created_event"],)).fetchone()
        events = []
        for saved in source.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY seq", (created[0],)):
            item = dict(saved)
            item["payload"] = json.loads(item["payload"])
            events.append(item)
            if item["kind"] == "session.started":
                refs.add(item["payload"]["identity"])
            if item["kind"] == "operation.intended":
                refs.add(item["payload"]["input"])
            if item["kind"] == "operation.completed":
                refs.add(item["payload"]["result"])
        for reference in sorted(refs):
            require(self.ledger.artifacts.put_bytes(source.artifact_bytes(reference)) == reference, "copied_artifact_identity")
        return {"source_owner": str(source.owner), "source_head": source.head(), "metadata": metadata,
            "records": records, "session_events": events, "artifacts": sorted(refs)}

    def _verified_import(self, session, row, desired):
        value = row["payload"]
        require(value["method"] == METHOD and value["binding"] == desired and value["policy"] == POLICY, "retained_import_binding")
        intent, protocol = self._one(INTENT), self.ledger.get(value["protocol_record"], "protocol")
        require(intent["id"] == value["intent_record"] and intent["payload"] == desired
            and protocol["content"] == desired and protocol["reason"] is None and protocol["branch"] == "main", "retained_import_registration")
        protocol_row = self._import_protocol(value["protocol_record"], desired)
        raw_result = self.ledger.db.execute("SELECT logical_key,supersedes FROM records WHERE id=?", (row["id"],)).fetchone()
        require(raw_result["logical_key"] == intent["id"] and raw_result["supersedes"] is None, "import_result_identity")
        bundle = self.ledger.artifacts.read(value["bundle_artifact"])
        cutoff = self._one(CUTOFF)
        require(protocol_row["created_event"] < cutoff["created_event"] < row["created_event"], "import_registration_order")
        require(cutoff["payload"] == {"intent_record": intent["id"], "discovery_owner": desired["discovery"]["discovery_owner"],
            "source_head": bundle["source_head"]}, "import_cutoff_binding")
        for observation in value["liveness"]:
            discovery.source_api._retained_liveness(self, observation)
            require(observation["source_owner"] == bundle["source_owner"] and observation["inspection_complete"] is True
                and observation["active_writers"] == observation["matching_processes"] == [], "import_retained_liveness")
        require(len(value["liveness"]) == 2, "import_liveness_pair")
        return verify_bundle(self, session, bundle, desired["preparation_binding"], desired["discovery"])

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data["method"] == METHOD, "offline_entry")
        selected, locator = data["binding"], data["discovery"]
        _, _, prepared = self._prepared(selected)
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "preparation_binding": selected, "preparation_artifact": digest(prepared), "discovery": locator}
        intent, completed = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(intent is None or intent["payload"] == desired, "changed_import_requires_amendment")
        require(completed is not None or not self._rows(reconciliation.INTENT_KIND), "cannot_adopt_existing_reconciliation")
        reused = completed is not None
        if not completed and data["action"] == "status":
            return {"imported": False, "incomplete_import": intent is not None, **POLICY}
        if not completed:
            identity = intent["id"] if intent else self.ledger.record(session, INTENT, METHOD, desired)
            protocol = self._version_once(session, context, "protocol", METHOD, desired)
            self._import_protocol(protocol, desired)
            _, _, local = local_snapshot_metadata(self, session, selected["snapshot_binding"])
            owner = Path(locator["discovery_owner"])
            before = self._observe_import(session, owner)
            source = discovery.source_api.Source(self, session, owner)
            try:
                cutoff_value = {"intent_record": identity, "discovery_owner": str(owner), "source_head": source.head()}
                cutoff = self._one(CUTOFF, optional=True)
                require(cutoff is None or cutoff["payload"] == cutoff_value, "incomplete_import_cutoff_changed")
                if cutoff is None:
                    self.ledger.record(session, CUTOFF, identity, cutoff_value)
                bundle = self._capture(source, locator, local)
                verify_bundle(self, session, bundle, selected, locator)
                after = self._observe_import(session, owner)
                require(source.head(fresh=True) == bundle["source_head"] and implementation() == desired["implementation"], "source_or_code_changed")
                value = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": identity,
                    "protocol_record": protocol, "bundle_artifact": self.ledger.artifacts.put(bundle), "liveness": [before, after]}
                self.ledger.record(session, RESULT, identity, value)
                completed = self._one(RESULT)
                self._verified_import(session, completed, desired)
            finally:
                source.close()
        registry, summary, owners = self._verified_import(session, completed, desired)
        result = {"method": METHOD, "import_record": completed["id"], "import_artifact": digest(completed["payload"]),
            "registry_artifact": locator["registry_artifact"], "discovery_record": locator["discovery_record"],
            "reused_retained_import": reused, "discovery_quiescence_verified_during_import": not reused,
            "current_discovery_quiescence_claimed": False, **POLICY,
            "counts": {**{key: summary[key] for key in ("root_count", "owner_count", "observed_candidate_count", "unresolved_root_count")},
                "external_registry_owners": len(registry["owners"]),
                "declared_global_gaps": sum(g["affected_input_sha256"] is None for g in registry["declared_gaps"]),
                "declared_gap_reasons": dict(sorted(Counter(g["reason_code"] for g in registry["declared_gaps"]).items())),
                "unresolved_adapters": sum(e["adapter"] == "unresolved" for e in registry["adapter_origins"]),
                "generic_intended_events": sum(r["event_kind_counts"].get("model.attempt.intended", 0) for r in owners),
                "generic_completed_events": sum(r["event_kind_counts"].get("model.attempt.completed", 0) for r in owners),
                "metadata_records": sum(len(r["records"]) for r in owners),
                "logical_tasks_classified": None},
            "registry_binding_is_immutable_on_reconcile": True,
            "declared_global_gaps_require_separate_evidence_based_resolution": True}
        if data["action"] in {"reconcile", "status"} and (data["action"] == "reconcile" or self._rows(reconciliation.INTENT_KIND)):
            outcome = reconciliation.Reconciliation._status(self, session, context,
                {"method": reconciliation.METHOD, "action": data["action"], "binding": selected, "registry": registry})
            result["reconciliation"] = outcome
            if "reconciliation_record" in outcome:
                saved = self.ledger.get(outcome["reconciliation_record"], reconciliation.RESULT_KIND)
                gaps = self.ledger.artifacts.read(saved["artifacts"]["gaps"])
                result["reconciliation_gap_counts"] = dict(sorted(Counter(g["reason_code"] for g in gaps).items()))
        return result

