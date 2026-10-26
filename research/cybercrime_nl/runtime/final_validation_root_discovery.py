"""Finite catalog hints -> audited metadata cutoffs, never history clearance.

Only a separately protected observer is writable. The fixed catalog determines
every candidate basename; there is no directory enumeration, recursive link
following, article/response read, origin inference, or purpose classification.
The exact retained V11 snapshot is checked through a read-only ledger view in
the observer's real active operation. This view is not a source Research engine.
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path

import final_validation_history_closure as closure
import final_validation_snapshot_v11 as snapshot_api
from newsresearch.common import AuditError, Config, digest, require_active
from newsresearch.runtime import Research, audited_handler

source_api = snapshot_api.compatibility.original
study = snapshot_api.original
METHOD = "final-validation-finite-root-cutoffs-v1"
INTENT = "final_validation_root_discovery_intent"
CUTOFF = "final_validation_root_discovery_cutoff"
RESULT = "final_validation_root_discovery"
POLICY = {"metadata_only": True, "source_mutations": 0, "new_model_calls": 0,
    "dispatch_authorized": False, "history_complete": False, "root_semantics_resolved": False,
    "source_intersections_verified": False, "physical_origins_verified": False,
    "filesystem_enumeration": False, "linked_paths_followed": False}
METADATA_KINDS = {study.INTENT, study.SEEDS, study.STUDY, study.FREEZE, study.ACCESS, study.SNAPSHOT,
    snapshot_api.FREEZE, snapshot_api.ACCESS, snapshot_api.PREFLIGHT, snapshot_api.SNAPSHOT,
    snapshot_api.compatibility.RESULT_KIND, "protocol", "selection", "policy"}


def require(value, reason):
    if not value:
        raise AuditError("root_discovery_" + reason)


def implementation():
    path = Path(__file__)
    return {**snapshot_api.implementation(),
        closure.CATALOG.relative_to(study.ROOT).as_posix(): hashlib.sha256(closure.CATALOG.read_bytes()).hexdigest(),
        Path(closure.__file__).relative_to(study.ROOT).as_posix(): hashlib.sha256(Path(closure.__file__).read_bytes()).hexdigest(),
        path.relative_to(study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def canonical_path(value):
    require(isinstance(value, str) and value, "explicit_path")
    path = Path(value)
    require(path.is_absolute() and str(path) == str(path.resolve()), "canonical_path")
    require(not any(p.is_symlink() or p.is_junction() or (p / ".git").exists()
        for p in [path, *path.parents]), "protected_unlinked_path")
    return path


def candidates(catalog, base, main):
    """Only literal one-component basenames from fixed catalog owner hints."""
    result = []
    for root in catalog["roots"]:
        selector = root["selector"]
        if root["id"] == "current-main":
            path, state = main, "frozen_main_cutoff"
        elif selector["kind"] == "owner_basename_hint":
            name = selector["basename"]
            require(isinstance(name, str) and name not in {"", ".", ".."}
                and "/" not in name and "\\" not in name and ":" not in name, "literal_catalog_basename")
            path, state = canonical_path(str(base / name)), "declared_hint_only"
            require(path.parent == base, "candidate_outside_base")
        else:
            path, state = None, "unresolved_link_or_manual_root"
        result.append({"root_id": root["id"], "selector_sha256": digest(selector),
            "source_owner": str(path) if path else None, "discovery_state": state})
    require(len({r["source_owner"] for r in result if r["source_owner"]})
        == sum(r["source_owner"] is not None for r in result), "duplicate_candidate_paths")
    return result


def metadata_census(source):
    """Verify chain/record projections without opening nested source artifacts.

    SQL payload bytes are hashed for integrity, not interpreted as task purpose.
    This is deliberately not Ledger.verify or full source/artifact preflight.
    """
    source._active()
    require(source.db.execute("PRAGMA query_only").fetchone()[0] == 1, "query_only")
    previous, event_rows, creates = "0" * 64, [], {}
    for row in source.db.execute("SELECT * FROM events ORDER BY seq"):
        value = dict(row)
        expected = value.pop("event_hash")
        value["payload"] = json.loads(value["payload"])
        require(type(value["seq"]) is int and value["seq"] == len(event_rows) + 1
            and value["previous_hash"] == previous and digest(value) == expected, "metadata_chain")
        if value["kind"] == "record.created":
            creates[value["seq"]] = value["payload"]
        event_rows.append({"seq": value["seq"], "kind": value["kind"], "event_hash": expected})
        previous = expected
    require(event_rows and source.head() == [len(event_rows), previous], "metadata_head")
    records = []
    for row in source.db.execute("SELECT * FROM records ORDER BY created_event"):
        require(hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"]
            and row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
                "payload": row["artifact"], "supersedes": row["supersedes"]})
            and digest(creates.get(row["created_event"])) == digest({"record": row["id"],
                "kind": row["kind"], "artifact": row["artifact"]}), "metadata_record_projection")
        records.append({"record_id": row["id"], "kind": row["kind"], "artifact": row["artifact"],
            "logical_key_sha256": digest(row["logical_key"]), "created_event": row["created_event"]})
    return {"source_owner": str(source.owner), "owner_sha256": digest(str(source.owner)),
        "source_head": [len(event_rows), previous], "events": event_rows, "records": records,
        "event_kind_counts": dict(sorted(Counter(r["kind"] for r in event_rows).items())),
        "record_kind_counts": dict(sorted(Counter(r["kind"] for r in records).items())),
        "source_row_count": source.db.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
        "metadata_chain_and_projection_verified": True, "full_source_ledger_preflight_verified": False,
        "nested_artifact_integrity_verified": False, "source_intersection": "unknown"}


class MetadataLedger:
    """Fixed metadata capability for the unchanged retained snapshot verifier."""
    def __init__(self, source, engine):
        self.source, self.engine, self.root = source, engine, source.owner
        self.artifacts = self
        self.allowed, self.read_refs, self.record_refs = set(), set(), {}

    @property
    def db(self):
        self.source._active()
        return self.source.db

    def get(self, identity, kind=None):
        row = self.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
        require(row is not None and row["kind"] in METADATA_KINDS
            and (kind is None or kind == row["kind"]), "snapshot_metadata_kind")
        value = self.source._row(row)
        value = {k: v for k, v in value.items() if k not in {"_record_id", "_record_kind", "_artifact", "_created_event"}}
        self.record_refs[identity] = {"kind": row["kind"], "artifact": row["artifact"], "created_event": row["created_event"]}
        self.engine.ledger.artifacts.put_bytes(self.source.artifact_bytes(row["artifact"]))
        fields = {study.STUDY: ("instruction_evidence_artifact", "specification_artifact"),
            study.SEEDS: ("schedule_seed_artifact", "article_order_seed_artifact"),
            snapshot_api.compatibility.RESULT_KIND: ("input_index_artifact",)}
        self.allowed.update(value[k] for k in fields.get(row["kind"], ()))
        if row["kind"] == snapshot_api.PREFLIGHT:
            self.allowed.update(r["evidence_sha256"] for r in value["liveness"])
        return value

    def read_bytes(self, reference):
        require(reference in self.allowed, "snapshot_nested_metadata_scope")
        raw = self.source.artifact_bytes(reference)
        require(self.engine.ledger.artifacts.put_bytes(raw) == reference, "retained_metadata_bytes")
        self.read_refs.add(reference)
        return raw

    def read(self, reference):
        return json.loads(self.read_bytes(reference))


class SnapshotMetadataView:
    """Borrow the real active operation only while its Source is live."""
    def __init__(self, engine, source, ledger):
        self._engine, self._source, self.ledger = engine, source, ledger
        self.config = engine.config

    @property
    def _active(self):
        self._source._active()
        return self._engine._active


def verify_snapshot_metadata(engine, session, source, selected):
    require_active(engine, session)
    ledger = MetadataLedger(source, engine)
    # The capability view shares the actual observer's active context. It does
    # not create a source session, register a source record, or expose mutations.
    view = SnapshotMetadataView(engine, source, ledger)
    snapshot, index = snapshot_api.load_snapshot(view, session, selected)
    return snapshot, index, {"validation_owner": str(source.owner), "validation_head": source.head(),
        "snapshot_binding": selected, "source_bindings": snapshot["source_bindings"],
        "input_index_digest": index.digest, "study_record": snapshot["parent_authority"]["binding"]["study_record"],
        "seed_record": snapshot["parent_authority"]["binding"]["seed_record"],
        "metadata_records": ledger.record_refs, "nested_metadata_artifacts": sorted(ledger.read_refs),
        "unchanged_snapshot_loader_verified": True, "source_owner_engine_created": False}


def registry_for(rows, states, main, reference):
    owners = []
    for row in rows:
        if row["source_owner"] == str(main):
            continue
        owners.append({"source_owner": row["source_owner"], "source_head": row["source_head"],
            "scope_input_sha256": None,
            # 'declaration' is a collection bucket, never a semantic exclusion.
            "record_kinds": {k: "declaration" for k in row["record_kind_counts"]},
            "event_kinds": sorted(row["event_kind_counts"]),
            "expected_records": [{"record_id": r["record_id"], "kind": r["kind"], "affected_input_sha256": None}
                for r in row["records"]], "artifact_rules": [], "required_artifacts": []})
    gaps = [{"reason_code": "study_history_scope_missing", "affected_input_sha256": None},
        {"reason_code": "manual_review_scope_missing", "affected_input_sha256": None}]
    if any(r["discovery_state"] != "observed_candidate_cutoff" and r["root_id"] != "current-main" for r in states):
        gaps.append({"reason_code": "owner_scope_missing", "affected_input_sha256": None})
    return {"owners": sorted(owners, key=lambda r: r["source_owner"]), "declared_gaps": gaps,
        "adapter_origins": [{"owner_sha256": digest(r["source_owner"]), "adapter": "unresolved",
            "origin_owner_sha256": None} for r in sorted(owners, key=lambda r: r["source_owner"])],
        "registry_source_reference": reference}


class RootDiscovery(Research):
    _rows = study.Study._rows
    _one = study.Study._one
    _version_once = study.Study._version_once

    def __init__(self, workspace, *, config=None):
        canonical_path(str(workspace))
        require(config is None or config.offline, "offline_required")
        self.observer = study.WindowsProcessObserver()
        super().__init__(workspace, config=config or Config(offline=True))

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "base_directory", "validation_owner", "snapshot_binding"}
            and data["action"] in {"discover", "status"}, "operation_shape")
        base, validation = canonical_path(data["base_directory"]), canonical_path(data["validation_owner"])
        require(base.is_dir() and validation != self.ledger.root.resolve()
            and self.ledger.root.resolve() not in validation.parents and validation not in self.ledger.root.resolve().parents,
            "separate_validation_owner")
        require(set(data["snapshot_binding"]) == {"snapshot_record", "snapshot_artifact"}, "snapshot_binding")
        for ref in data["snapshot_binding"].values():
            source_api._sha(ref)
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _observe(self, session, owner):
        require(type(self.observer) is study.WindowsProcessObserver, "concrete_process_observer")
        value = source_api._liveness(lambda path: self.observer.observe(self, session, path), owner)
        source_api._retained_liveness(self, value)
        return value

    def _cutoff(self, session, intent, path, head):
        value = {"discovery_intent": intent, "source_owner": str(path), "source_head": head,
            "exists": head is not None}
        key = digest([intent, str(path)])
        old = [r for r in self._rows(CUTOFF) if r["payload"]["source_owner"] == str(path)]
        require(len(old) <= 1 and (not old or old[0]["payload"] == value), "cutoff_changed_requires_new_discovery")
        return old[0]["id"] if old else self.ledger.record(session, CUTOFF, key, value)

    def _summary(self, identifier, value, *, reused):
        require(value["method"] == METHOD and value["implementation"] == implementation()
            and value["policy"] == POLICY, "retained_method")
        require(self.ledger.get(value["intent_record"], INTENT) == value["binding"]
            and self.ledger.get(value["protocol_record"], "protocol")["content"] == value["binding"], "retained_registration")
        states = self.ledger.artifacts.read(value["root_states_artifact"])
        rows = [self.ledger.artifacts.read(ref) for ref in value["owner_metadata_artifacts"]]
        snapshot = self.ledger.artifacts.read(value["snapshot_metadata_artifact"])
        registry = registry_for(rows, states, Path(snapshot["source_bindings"]["source_owner"]),
            "audited-root-discovery:" + value["intent_record"])
        require(self.ledger.artifacts.read(value["registry_artifact"]) == registry
            and value["root_count"] == len(states) and value["owner_count"] == len(rows), "retained_projection")
        for identity in value["cutoff_records"]:
            cutoff = self.ledger.get(identity, CUTOFF)
            require(cutoff["discovery_intent"] == value["intent_record"], "retained_cutoff")
        for ref in snapshot["nested_metadata_artifacts"]:
            self.ledger.artifacts.read_bytes(ref)
        for record in snapshot["metadata_records"].values():
            self.ledger.artifacts.read_bytes(record["artifact"])
        return {"discovery_record": identifier, "registry_artifact": value["registry_artifact"],
            "root_states_artifact": value["root_states_artifact"], "root_count": len(states), "owner_count": len(rows),
            "observed_candidate_count": sum(r["discovery_state"] == "observed_candidate_cutoff" for r in states),
            "unresolved_root_count": sum(r["discovery_state"] != "frozen_main_cutoff" for r in states),
            "reused_historical_evidence": reused, "current_quiescence_claimed": not reused, **POLICY}

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_required")
        catalog_bytes, catalog = closure._catalog()
        binding = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "base_directory": data["base_directory"], "validation_owner": data["validation_owner"],
            "snapshot_binding": data["snapshot_binding"], "catalog_artifact": hashlib.sha256(catalog_bytes).hexdigest()}
        old = self._one(RESULT, optional=True)
        if old:
            require(old["payload"]["binding"] == binding, "discovery_changed")
            return self._summary(old["id"], old["payload"], reused=True)
        intent = self._one(INTENT, optional=True)
        require(intent is None or intent["payload"] == binding, "discovery_changed")
        if data["action"] == "status":
            return {"discovered": False, "incomplete_discovery": intent is not None, **POLICY}
        self.ledger.artifacts.put_bytes(catalog_bytes)
        intent_id = intent["id"] if intent else self.ledger.record(session, INTENT, METHOD, binding)
        protocol = self._version_once(session, context, "protocol", METHOD, binding)
        validation, base = Path(data["validation_owner"]), Path(data["base_directory"])
        retained, cutoffs, observations, readers = [], [], [], []
        with ExitStack() as stack:
            observations.append(self._observe(session, validation))
            source = source_api.Source(self, session, validation)
            stack.callback(source.close)
            readers.append(source)
            cutoffs.append(self._cutoff(session, intent_id, validation, source.head()))
            validation_metadata = metadata_census(source)
            snapshot, _, authority = verify_snapshot_metadata(self, session, source, data["snapshot_binding"])
            main = canonical_path(snapshot["source_bindings"]["source_owner"])
            require(main != validation and main != self.ledger.root.resolve(), "main_owner_separation")
            states = candidates(catalog, base, main)
            for state in states:
                if state["source_owner"] is None:
                    continue
                path = Path(state["source_owner"])
                require(path != validation and path != self.ledger.root.resolve()
                    and self.ledger.root.resolve() not in path.parents and path not in self.ledger.root.resolve().parents,
                    "candidate_owner_separation")
                if not path.exists():
                    cutoffs.append(self._cutoff(session, intent_id, path, None))
                    state["discovery_state"] = "declared_candidate_not_present"
                    continue
                observations.append(self._observe(session, path))
                current = source_api.Source(self, session, path)
                stack.callback(current.close)
                readers.append(current)
                head = current.head()
                if path == main:
                    require(head == snapshot["source_bindings"]["source_head"], "main_final_cutoff_changed")
                cutoffs.append(self._cutoff(session, intent_id, path, head))
                metadata = metadata_census(current)
                retained.append(metadata)
                state["source_head"] = head
                state["owner_sha256"] = metadata["owner_sha256"]
                state["metadata_artifact"] = self.ledger.artifacts.put(metadata)
                if path != main:
                    state["discovery_state"] = "observed_candidate_cutoff"
            for current in readers:
                observations.append(self._observe(session, current.owner))
                require(current.head(fresh=True) == current.head(), "head_changed_during_discovery")
            for state in states:
                if state["discovery_state"] == "declared_candidate_not_present":
                    require(not Path(state["source_owner"]).exists(), "missing_candidate_changed")
            require(implementation() == binding["implementation"], "implementation_changed")
            registry = registry_for(retained, states, main, "audited-root-discovery:" + intent_id)
            value = {"method": METHOD, "implementation": binding["implementation"], "policy": POLICY,
                "binding": binding, "intent_record": intent_id, "protocol_record": protocol,
                "cutoff_records": cutoffs, "root_states_artifact": self.ledger.artifacts.put(states),
                "owner_metadata_artifacts": [self.ledger.artifacts.put(r) for r in retained],
                "validation_metadata_artifact": self.ledger.artifacts.put(validation_metadata),
                "snapshot_metadata_artifact": self.ledger.artifacts.put(authority),
                "registry_artifact": self.ledger.artifacts.put(registry), "liveness_artifact": self.ledger.artifacts.put(observations),
                "root_count": len(states), "owner_count": len(retained)}
            # Verify public projection before committing while every lock remains held.
            self._summary("pending", value, reused=False)
            identifier = self.ledger.record(session, RESULT, intent_id, value)
        return self._summary(identifier, value, reused=False)
