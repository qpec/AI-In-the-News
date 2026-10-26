"""One-pass transfer of completed validation metadata into a small observer.

Only the validation owner opens read-only. Historical owners, source articles,
frame arrays and provider bodies are not opened. This is an evidence inventory,
not replacement task semantics, source preflight, history closure or admission.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

import final_validation_root_discovery as discovery
import final_validation_preparation_v11 as preparation
import final_validation_reconciliation as reconciliation
import final_validation_discovery_reconciliation as delegated
from newsresearch.common import AuditError, Config, canonical, digest, require_active, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "final-validation-retained-metadata-inventory-v1"
INTENT = "final_validation_retained_inventory_intent"
CUTOFF = "final_validation_retained_inventory_cutoff"
BUNDLE = "final_validation_retained_owner_bundle"
RESULT = "final_validation_retained_inventory"
POLICY = {"source_mutations": 0, "new_model_calls": 0, "new_seed_draws": 0,
    "dispatch_authorized": False, "history_complete": False, "semantic_dispositions_created": False,
    "gaps_removed": False, "frame_or_sample_recomputed": False,
    "historical_owners_opened": 0, "full_source_ledger_preflight_performed": False,
    "current_source_quiescence_claimed": False, "interrupted_census_adopted": False}
MAIN_REFS = ("events_artifact", "records_artifact", "phase_records_artifact", "phase_events_artifact",
    "pilot_selections_artifact", "prior_diagnostics_artifact", "amendment_packet_plans_artifact",
    "pair_inventory_artifact", "census_artifact")
ROLE_REFS = ("role_catalog", "role_metadata", "prior_manifest", "pair_history_manifest", "pair_history_inventory")


def require(value, code):
    if not value:
        raise AuditError("retained_inventory_" + code)


def implementation():
    path = Path(__file__)
    return {**discovery.implementation(), **preparation.implementation(), **reconciliation.implementation(), **delegated.implementation(),
        path.relative_to(discovery.study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def validate_binding(value):
    require(isinstance(value, dict) and set(value) == {
        "validation_owner", "study_record", "seed_record", "snapshot", "preparation", "reconciliation"}, "binding_fields")
    discovery.canonical_path(value["validation_owner"])
    for name in ("study_record", "seed_record"):
        discovery.source_api._sha(value[name])
    for name in ("snapshot", "preparation", "reconciliation"):
        require(isinstance(value[name], dict) and set(value[name]) == {"record", "artifact"}, "selected_record_fields")
        for reference in value[name].values():
            discovery.source_api._sha(reference)


class MetadataSource(discovery.source_api.Source):
    """Only operation-local immutable byte reuse; live checks are never cached."""
    def __init__(self, *args, **kwargs):
        self.read_hashes = set()
        self.unique_read_bytes = 0
        super().__init__(*args, **kwargs)

    def artifact_bytes(self, reference):
        self._active()
        discovery.source_api._sha(reference)
        if reference not in self.read_hashes:
            raw = super().artifact_bytes(reference)
            require(self.engine.ledger.artifacts.put_bytes(raw) == reference, "captured_bytes")
            self.unique_read_bytes += len(raw)
            self.read_hashes.add(reference)
            return raw
        check_permissions(self.owner / "objects" / reference)
        return self.engine.ledger.artifacts.read_bytes(reference)

    def close(self):
        try:
            super().close()
        finally:
            self.read_hashes.clear()


class Reader:
    """Fixed record/field traversal; no caller artifact or SQL query interface."""
    def __init__(self, source, engine, metadata, code):
        self.source, self.engine, self.metadata = source, engine, metadata
        self.code = code
        self.rows, self.values = {}, {}
        self.events = {r["seq"]: r for r in source.db.execute("SELECT * FROM events ORDER BY seq")}
        self.roster = {r["record_id"]: r for r in metadata["records"]}
        self.copied = set()
        self.proof_events = {}

    def _active(self):
        self.source._active()

    def retain(self, reference):
        self.source._active()
        if reference not in self.copied:
            raw = self.source.artifact_bytes(reference)
            self.copied.add(reference)
            return raw
        return self.engine.ledger.artifacts.read_bytes(reference)

    def copy(self, reference):
        self._active()
        if reference not in self.values:
            self.values[reference] = json.loads(self.retain(reference))
        return self.values[reference]

    def record(self, identity, kind, *, unique=False):
        self.source._active()
        if unique:
            require([r["record_id"] for r in self.metadata["records"] if r["kind"] == kind] == [identity], "unique_producer_record")
        if identity not in self.rows:
            row = self.source.db.execute("SELECT * FROM records WHERE id=?", (identity,)).fetchone()
            require(row is not None and identity in self.roster, "record_in_cutoff")
            self.source._row(row)
            self.rows[identity] = dict(row)
            self.proof_events[row["created_event"]] = dict(self.events[row["created_event"]])
        row = self.rows[identity]
        require(row["kind"] == kind, "record_kind")
        return self.copy(row["artifact"])

    def selected(self, item, kind):
        value = self.record(item["record"], kind, unique=True)
        require(self.rows[item["record"]]["artifact"] == item["artifact"], "selected_artifact")
        return value

    def version(self, identity, kind, key, content, after, before):
        version = self.record(identity, kind)
        matches = [r for r in self.metadata["records"] if r["kind"] == kind and r["logical_key_sha256"] == digest(key)]
        require(len(matches) == 1 and matches[0]["record_id"] == identity, "unique_version_key")
        require(set(version) == {"content", "reason", "branch", "registered_by"} and digest(version["content"]) == digest(content)
            and version["reason"] is None and version["branch"] == "main", "native_version_content")
        row = self.rows[identity]
        require(row["logical_key"] == key and row["supersedes"] is None
            and after < row["created_event"] < before, "producer_version_order")

    def versions(self, value, method, code, binding, intent, label, result_id):
        require(set(value["versions"]) == {"protocol", "selection", "policy"}, "producer_version_set")
        common = {"method": method, "implementation": code, label: intent, "binding_sha256": digest(binding)}
        if method == preparation.METHOD:
            expected = {"protocol": {**common, "additional_source_metadata_scope": "exact-original-plan-versions.embedding_profile-record-only"},
                "selection": {"rules": "Entire frozen input frame; actual main-owner evidence; unresolved cross-study scope.", "binding_sha256": digest(binding)},
                "policy": {"mode": "offline-intermediate-preparation-only", **preparation.POLICY, label: intent, "binding_sha256": digest(binding)}}
        else:
            expected = {"protocol": {**common, "registry_sha256": value["registry_artifact"]},
                "selection": {"rules": "Exactly declared external owners and native/copy mappings; unresolved scope retained.",
                    "binding_sha256": digest(binding), "registry_sha256": value["registry_artifact"]},
                "policy": {"mode": "offline-contributions-only", **reconciliation.POLICY, label: intent}}
        for kind, identity in value["versions"].items():
            self.version(identity, kind, method, expected[kind], self.rows[intent]["created_event"], self.rows[result_id]["created_event"])
        return self.record(value["versions"]["protocol"], "protocol")["content"]

    def completed(self, identity, method, result_key, artifact, binding, registry=None, expected_input=None):
        """Require the original producer operation to have returned this result."""
        created = self.rows[identity]["created_event"]
        session = self.events[created]["session_id"]
        rows = [r for r in self.events.values() if r["session_id"] == session]
        for row in rows:
            self.proof_events[row["seq"]] = dict(row)
        starts = [r for r in rows if r["kind"] == "session.started"]
        intended = [r for r in rows if r["kind"] == "operation.intended"]
        completed = [r for r in rows if r["kind"] == "operation.completed"]
        ended = [r for r in rows if r["kind"] == "session.ended"]
        require(len(starts) == len(intended) == len(completed) == len(ended) == 1 and not any(r["kind"] == "operation.failed" for r in rows), "producer_not_completed")
        require(starts[0]["seq"] < intended[0]["seq"] < created < completed[0]["seq"] < ended[0]["seq"]
            and json.loads(ended[0]["payload"]) == {"status": "completed"}, "producer_completion_order")
        require(json.loads(intended[0]["payload"])["operation"] == json.loads(completed[0]["payload"])["operation"] == "status", "producer_operation")
        runtime = self.copy(json.loads(starts[0]["payload"])["identity"])
        require(all(runtime["code_files"].get(path) == sha for path, sha in self.code.items()
            if path.startswith("src/") and path.endswith(".py")), "producer_runtime_identity")
        incoming = self.copy(json.loads(intended[0]["payload"])["input"])
        outgoing = self.copy(json.loads(completed[0]["payload"])["result"])
        if method == reconciliation.METHOD and incoming.get("method") == delegated.METHOD:
            self.delegate(incoming, outgoing, binding, registry, intended[0]["seq"])
            outgoing = outgoing.get("reconciliation", {})
        else:
            expected = {"method": method, "action": "prepare" if method == preparation.METHOD else "reconcile", "binding": binding}
            if method == reconciliation.METHOD:
                expected["registry"] = registry
            require(digest(incoming) == digest(expected_input or expected), "producer_input_binding")
        require(outgoing.get(result_key + "_record") == identity
            and outgoing.get(result_key + "_artifact") == artifact, "producer_return_identity")

    def delegate(self, incoming, outgoing, binding, registry, operation_start):
        require(set(incoming) == {"method", "action", "binding", "discovery"} and incoming["action"] == "reconcile"
            and incoming["binding"] == binding, "delegate_input")
        value = self.record(outgoing["import_record"], delegated.RESULT, unique=True)
        require(digest(value) == outgoing["import_artifact"] and value["method"] == delegated.METHOD
            and value["policy"] == delegated.POLICY, "delegate_result")
        desired = value["binding"]
        require(desired == {"method": delegated.METHOD, "implementation": delegated.implementation(), "policy": delegated.POLICY,
            "preparation_binding": binding, "preparation_artifact": self.rows[binding["preparation_record"]]["artifact"],
            "discovery": incoming["discovery"]} and desired["discovery"]["registry_artifact"] == digest(registry), "delegate_binding")
        intent = self.record(value["intent_record"], delegated.INTENT, unique=True)
        cutoff_ids = [r["record_id"] for r in self.metadata["records"] if r["kind"] == delegated.CUTOFF]
        require(len(cutoff_ids) == 1, "delegate_cutoff_unique")
        cutoff = self.record(cutoff_ids[0], delegated.CUTOFF)
        require(intent == desired and self.rows[value["intent_record"]]["logical_key"] == delegated.METHOD
            and self.rows[outgoing["import_record"]]["logical_key"] == value["intent_record"]
            and cutoff["intent_record"] == value["intent_record"] and cutoff["discovery_owner"] == incoming["discovery"]["discovery_owner"], "delegate_registration")
        self.version(value["protocol_record"], "protocol", delegated.METHOD, desired,
            self.rows[value["intent_record"]]["created_event"], self.rows[cutoff_ids[0]]["created_event"])
        require(self.rows[cutoff_ids[0]]["created_event"] < self.rows[outgoing["import_record"]]["created_event"] < operation_start, "delegate_import_precedes_reconcile")
        self.completed(outgoing["import_record"], delegated.METHOD, "import", outgoing["import_artifact"], binding,
            expected_input={"method": delegated.METHOD, "action": "import", "binding": binding, "discovery": incoming["discovery"]})


class SavedReader(Reader):
    """Replay only the captured successful producer metadata, without Source."""
    def __init__(self, engine, session, metadata, proof, code):
        self.engine, self.session, self.metadata = engine, session, metadata
        self.code = code
        self.rows, self.values = proof["records"], {}
        self.events = {r["seq"]: r for r in proof["events"]}
        self.proof_events, self.copied = {}, set(proof["artifacts"])
        self.roster = {r["record_id"]: r for r in metadata["records"]}
        roster_events = {r["seq"]: r for r in metadata["events"]}
        for seq, row in self.events.items():
            value = {**row, "payload": json.loads(row["payload"])}
            identity = value.pop("event_hash")
            require(digest(value) == identity and roster_events.get(seq) == {"seq": seq, "kind": row["kind"], "event_hash": identity}, "saved_event_identity")
        for identity, row in self.rows.items():
            delegated._row_identity(row)
            require(row["id"] == identity and self.roster.get(identity) == {"record_id": identity,
                "kind": row["kind"], "artifact": row["artifact"], "logical_key_sha256": digest(row["logical_key"]),
                "created_event": row["created_event"]}, "saved_record_roster")
            event = self.events.get(row["created_event"])
            require(event is not None and event["kind"] == "record.created" and json.loads(event["payload"]) == {
                "record": identity, "kind": row["kind"], "artifact": row["artifact"]}, "saved_record_creation")

    def _active(self):
        require_active(self.engine, self.session)

    def retain(self, reference):
        require_active(self.engine, self.session)
        require(reference in self.copied, "saved_artifact_scope")
        return self.engine.ledger.artifacts.read_bytes(reference)

    def record(self, identity, kind, *, unique=False):
        require_active(self.engine, self.session)
        require(identity in self.rows and self.rows[identity]["kind"] == kind, "saved_record_scope")
        if unique:
            require([r["record_id"] for r in self.metadata["records"] if r["kind"] == kind] == [identity], "unique_saved_record")
        return self.copy(self.rows[identity]["artifact"])


def _descriptors(prepared, main, history, registry, source_bindings):
    scopes = {digest(s["source_owner"]): s for s in registry["owners"]}
    require(len(scopes) == len(history["owners"]) and set(scopes) == {o["census"]["owner_sha256"] for o in history["owners"]}, "owner_partition")
    main_id = digest(source_bindings["source_owner"])
    require(main_id not in scopes, "main_external_overlap")
    descriptors = [{"owner_sha256": main_id, "source_head": main["source_bindings"]["source_head"],
        "refs": {k: main[k] for k in MAIN_REFS} | {k: prepared["contributions"][k] for k in ROLE_REFS},
        "permitted": main["permitted_source_artifacts"], "census": None, "main": True}]
    for item in history["owners"]:
        census = item["census"]
        require(census["source_head"] == scopes[census["owner_sha256"]]["source_head"]
            and census["scope_sha256"] == digest(scopes[census["owner_sha256"]]), "owner_scope_binding")
        descriptors.append({"owner_sha256": census["owner_sha256"], "source_head": census["source_head"],
            "refs": {k: item[k] for k in ("events_artifact", "records_artifact", "gaps_artifact")},
            "permitted": item["permitted_source_artifacts"], "census": census, "main": False})
    return descriptors


def _bundle_summary(descriptor, values):
    events, records = values["events_artifact"], values["records_artifact"]
    complete = not descriptor["main"] and len(events) == descriptor["source_head"][0]
    summary = _rows_summary(events, records, complete=complete, head=descriptor["source_head"])
    census = descriptor["census"]
    if census is not None:
        require([r["id"] for r in records] == census["selected_record_ids"]
            and [r["event_hash"] for r in events] == census["selected_event_hashes"], "external_metadata_partition")
    gaps = values.get("gaps_artifact", values.get("pair_inventory_artifact", {}).get("gaps", []))
    require(isinstance(gaps, list), "gap_rows")
    # This is deliberately not a claim that the original owner lacks a byte.
    missing = sorted(set(descriptor["permitted"]) - set(descriptor["refs"].values()))
    summary.update(owner_sha256=descriptor["owner_sha256"], main_owner=descriptor["main"],
        source_head=descriptor["source_head"], gap_counts=dict(sorted(Counter(g["reason_code"] for g in gaps).items())),
        permitted_source_artifact_references=len(set(descriptor["permitted"])),
        references_not_materialized_by_owner_bundle=len(missing),
        unmaterialized_reference_list_sha256=digest(missing))
    if descriptor["main"]:
        phase = _rows_summary(values["phase_events_artifact"], values["phase_records_artifact"], complete=False, head=descriptor["source_head"])
        summary["additional_main_metadata_partitions"] = {"phase_records": phase["records"],
            "phase_creation_events": phase["events"], "phase_record_kinds": phase["record_kinds"],
            **{key: len(values[field]) for key, field in (("pilot_selections", "pilot_selections_artifact"),
                ("prior_diagnostics", "prior_diagnostics_artifact"), ("amendment_packet_plans", "amendment_packet_plans_artifact"))}}
    return summary, missing


def _producer_evidence(reader, selected, snapshot, index, codes):
    expected = {"study_record": selected["study_record"], "seed_record": selected["seed_record"],
        "snapshot_binding": {"snapshot_record": selected["snapshot"]["record"], "snapshot_artifact": selected["snapshot"]["artifact"]}}
    prepared = reader.selected(selected["preparation"], preparation.RESULT_KIND)
    preparation.validate_binding(prepared["binding"])
    require(all(prepared["binding"][k] == v for k, v in expected.items())
        and prepared["method"] == preparation.METHOD and prepared["implementation"] == codes["preparation"]
        and all(prepared.get(k) == v for k, v in preparation.POLICY.items()), "preparation_binding")
    intent = reader.record(prepared["preparation_intent"], preparation.INTENT_KIND, unique=True)
    registration = reader.record(selected["study_record"], discovery.study.STUDY, unique=True)
    require(intent == {"method": preparation.METHOD, "binding": prepared["binding"], "implementation": codes["preparation"],
        "policy": preparation.POLICY, "original_study_artifact": digest(registration),
        "registered_specification_artifact": registration["specification_artifact"]}, "preparation_intent")
    reader.versions(prepared, preparation.METHOD, codes["preparation"], prepared["binding"], prepared["preparation_intent"], "preparation_intent", selected["preparation"]["record"])
    main = reader.record(prepared["inventory"]["inventory_record"], preparation.inventory.RESULT_KIND)
    require(digest(main) == prepared["inventory"]["inventory_artifact"] and main["method"] == preparation.inventory.METHOD
        and main["implementation"] == codes["main_inventory"] and main["snapshot_binding"] == expected["snapshot_binding"]
        and main["source_bindings"] == snapshot["source_bindings"] and main["input_index_digest"] == index.digest
        and main["source_head_stable"] is True and main["full_source_ledger_preflight_verified"] is True
        and main["original_study_record"] == selected["study_record"] and main["original_seed_record"] == selected["seed_record"], "main_inventory_binding")
    require(reader.rows[prepared["inventory"]["inventory_record"]]["logical_key"] == digest(expected["snapshot_binding"]), "main_inventory_key")
    require(set(main["versions"]) == {"protocol", "selection"}, "main_inventory_version_set")
    for kind, identity in main["versions"].items():
        content = {"snapshot_binding_sha256": digest(expected["snapshot_binding"]), "preparation_intent": prepared["preparation_intent"],
            "preparation_protocol": prepared["versions"]["protocol"]}
        if kind == "protocol":
            content.update(method=preparation.inventory.METHOD, implementation=codes["main_inventory"])
        else:
            content["rules"] = "Complete immutable main-owner census under the registered final cutoff."
        reader.version(identity, kind, preparation.METHOD + ":inventory", content,
            reader.rows[prepared["versions"]["protocol"]]["created_event"], reader.rows[prepared["inventory"]["inventory_record"]]["created_event"])
    reconciled = reader.selected(selected["reconciliation"], reconciliation.RESULT_KIND)
    binding = {"preparation_record": selected["preparation"]["record"], **expected}
    require(reconciled["binding"] == binding and reconciled["method"] == reconciliation.METHOD
        and reconciled["implementation"] == codes["reconciliation"]
        and all(reconciled.get(k) == v for k, v in reconciliation.POLICY.items()), "reconciliation_binding")
    intended = reader.record(reconciled["reconciliation_intent"], reconciliation.INTENT_KIND, unique=True)
    require(intended == {"method": reconciliation.METHOD, "binding": binding,
        "registry_sha256": reconciled["registry_artifact"], "preparation_artifact": selected["preparation"]["artifact"],
        "implementation": codes["reconciliation"], "policy": reconciliation.POLICY}, "reconciliation_intent")
    protocol = reader.versions(reconciled, reconciliation.METHOD, codes["reconciliation"], binding,
        reconciled["reconciliation_intent"], "reconciliation_intent", selected["reconciliation"]["record"])
    registry = reader.copy(reconciled["registry_artifact"])
    require(protocol["registry_sha256"] == digest(registry), "registry_protocol")
    history = reader.record(reconciled["inventory"]["inventory_record"], reconciliation.inventory.RESULT_KIND)
    require(digest(history) == reconciled["inventory"]["inventory_artifact"] and history["method"] == reconciliation.inventory.METHOD
        and history["implementation"] == codes["history_inventory"] and history["input_index_digest"] == index.digest
        and history["binding"]["snapshot_binding"] == expected["snapshot_binding"]
        and history["binding"]["owners"] == registry["owners"] and history["binding"]["declared_gaps"] == registry["declared_gaps"]
        and history["source_head_stable"] is True and history["full_declared_source_ledger_preflight_verified"] is True
        and history["main_final_cutoff_guard"]["source_head"] == snapshot["source_bindings"]["source_head"]
        and history["main_final_cutoff_guard"]["head_stable"] is True, "history_inventory_binding")
    require(reader.rows[reconciled["inventory"]["inventory_record"]]["logical_key"] == digest(history["binding"]), "history_inventory_key")
    require(set(history["versions"]) == {"protocol", "selection"}, "history_inventory_version_set")
    for kind, identity in history["versions"].items():
        content = {"binding_sha256": digest(history["binding"]), "parent_protocol": reconciled["versions"]["protocol"]}
        if kind == "protocol":
            content.update(method=reconciliation.inventory.METHOD, implementation=codes["history_inventory"])
        else:
            content["rules"] = "Complete declared immutable ledgers; no semantic inference from kind or owner name."
        reader.version(identity, kind, reconciliation.METHOD + ":inventory", content,
            reader.rows[reconciled["versions"]["protocol"]]["created_event"], reader.rows[reconciled["inventory"]["inventory_record"]]["created_event"])
    seeds = reader.record(selected["seed_record"], discovery.study.SEEDS, unique=True)
    for field in ("schedule_seed_artifact", "article_order_seed_artifact"):
        require(prepared[field] == reconciled[field] == seeds[field], "original_seed_binding")
    for item, method, key, inventory_id in (("preparation", preparation.METHOD, "preparation", prepared["inventory"]["inventory_record"]),
            ("reconciliation", reconciliation.METHOD, "reconciliation", reconciled["inventory"]["inventory_record"])):
        row = reader.rows[selected[item]["record"]]
        require(reader.rows[inventory_id]["created_event"] < row["created_event"], "enclosing_inventory_order")
        producer = prepared if item == "preparation" else reconciled
        require(row["logical_key"] == producer[key + "_intent"] and row["supersedes"] is None
            and reader.rows[producer[key + "_intent"]]["logical_key"] == method, "producer_logical_identity")
        reader.completed(row["id"], method, key, selected[item]["artifact"], producer["binding"], registry)
    require(reader.rows[selected["preparation"]["record"]]["created_event"]
        < reader.rows[reconciled["reconciliation_intent"]]["created_event"], "upstream_producer_order")
    return prepared, main, reconciled, history, registry


def _rows_summary(events, records, *, complete, head):
    require(isinstance(events, list) and isinstance(records, list), "metadata_lists")
    seqs, hashes, record_ids = set(), set(), set()
    previous = "0" * 64
    for position, row in enumerate(events, 1):
        value = dict(row)
        identity = value.pop("event_hash")
        value["payload"] = json.loads(value["payload"])
        require(type(value["seq"]) is int and value["seq"] <= head[0]
            and value["seq"] not in seqs and identity not in hashes and digest(value) == identity, "event_identity")
        if complete:
            require(value["seq"] == position and value["previous_hash"] == previous, "complete_event_chain")
        previous = identity
        seqs.add(value["seq"])
        hashes.add(identity)
    byseq = {r["seq"]: r for r in events}
    for row in records:
        require(row["id"] not in record_ids and hashlib.sha256(row["payload"].encode()).hexdigest() == row["artifact"]
            and row["id"] == digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]}), "raw_record_identity")
        event = byseq.get(row["created_event"])
        require(event is not None and event["kind"] == "record.created" and json.loads(event["payload"]) == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "raw_record_creation")
        record_ids.add(row["id"])
    if complete:
        require(len(events) == head[0] and previous == head[1], "complete_event_head")
    return {"events": len(events), "records": len(records), "event_kinds": dict(sorted(Counter(r["kind"] for r in events).items())),
        "record_kinds": dict(sorted(Counter(r["kind"] for r in records).items())),
        "intended_events": sum(r["kind"] == "model.attempt.intended" for r in events),
        "completed_events": sum(r["kind"] == "model.attempt.completed" for r in events),
        "complete_event_payload_roster": complete, "logical_tasks_classified": None}


class RetainedInventory(Research):
    _rows = discovery.study.Study._rows
    _one = discovery.study.Study._one
    _version_once = discovery.study.Study._version_once

    def __init__(self, workspace, *, config=None):
        discovery.canonical_path(str(workspace))
        require(config is None or config.offline, "offline_required")
        self.observer = discovery.study.WindowsProcessObserver()
        super().__init__(workspace, config=config or Config(offline=True))

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "binding"}
            and data["action"] in {"collect", "status"}, "operation_shape")
        validate_binding(data["binding"])
        owner, observer = Path(data["binding"]["validation_owner"]), self.ledger.root.resolve()
        require(owner != observer and owner not in observer.parents and observer not in owner.parents, "separate_owner")
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _observe(self, session, owner):
        require(type(self.observer) is discovery.study.WindowsProcessObserver, "concrete_observer")
        value = discovery.source_api._liveness(lambda path: self.observer.observe(self, session, path), owner)
        discovery.source_api._retained_liveness(self, value)
        return value

    def _progress(self, value):
        target = self.ledger.root / "retained-inventory-progress.json"
        require(not target.is_symlink() and not target.is_junction(), "progress_link")
        temporary = self.ledger.root / ("retained-inventory-" + uuid.uuid4().hex + ".writing")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(canonical({"method": METHOD, "observed_at": utc(), **value}))
                stream.flush()
                os.fsync(stream.fileno())
            check_permissions(temporary)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _protocol(self, intent, identity, desired):
        rows = list(self.ledger.db.execute("SELECT * FROM records WHERE kind='protocol' AND logical_key=?", (METHOD,)))
        raw_intent = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (intent,)).fetchone()
        require(len(rows) == 1 and rows[0]["id"] == identity and rows[0]["supersedes"] is None
            and raw_intent["logical_key"] == METHOD and raw_intent["supersedes"] is None
            and raw_intent["created_event"] < rows[0]["created_event"], "prospective_protocol")
        value = self.ledger.get(identity, "protocol")
        require(value["content"] == desired and value["reason"] is None and value["branch"] == "main", "protocol_content")
        return rows[0]["created_event"]

    def _stop(self, selected):
        require(not (self.ledger.root / "STOP").exists()
            and not (Path(selected["validation_owner"]) / "STOP").exists(), "stop_requested")

    def _summary(self, session, row, desired, codes, *, reused):
        value = row["payload"]
        selected = desired["binding"]
        require(value["method"] == METHOD and value["binding"] == desired and value["policy"] == POLICY
            and self._one(INTENT)["id"] == value["intent_record"]
            and self.ledger.get(value["intent_record"], INTENT) == desired, "retained_result_binding")
        protocol_seq = self._protocol(value["intent_record"], value["protocol_record"], desired)
        cutoff = self._one(CUTOFF)
        raw_result = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (row["id"],)).fetchone()
        raw_cutoff = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (cutoff["id"],)).fetchone()
        require(raw_result["logical_key"] == value["intent_record"] and raw_result["supersedes"] is None
            and raw_cutoff["logical_key"] == value["intent_record"] and raw_cutoff["supersedes"] is None
            and cutoff["id"] == value["cutoff_record"] and cutoff["payload"] == {
                "intent_record": value["intent_record"], "source_head": value["validation_head"], "source_owner": selected["validation_owner"]}
            and protocol_seq < cutoff["created_event"] < row["created_event"], "retained_cutoff_order")
        metadata = self.ledger.artifacts.read(value["metadata_artifact"])
        authority = self.ledger.artifacts.read(value["snapshot_authority"])
        proof = self.ledger.artifacts.read(value["producer_evidence"])
        require(metadata["source_head"] == value["validation_head"] and metadata["source_owner"] == selected["validation_owner"]
            and authority["validation_head"] == value["validation_head"] and authority["validation_owner"] == selected["validation_owner"]
            and authority["snapshot_binding"] == {"snapshot_record": selected["snapshot"]["record"], "snapshot_artifact": selected["snapshot"]["artifact"]}
            and authority["study_record"] == selected["study_record"] and authority["seed_record"] == selected["seed_record"]
            and authority["unchanged_snapshot_loader_verified"] is True, "retained_authority")
        reader = SavedReader(self, session, metadata, proof, desired["implementation"])
        for identity, item in authority["metadata_records"].items():
            reader.record(identity, item["kind"])
            require({k: reader.rows[identity][k] for k in ("kind", "artifact", "created_event")} == item, "snapshot_metadata_roster")
        for reference in authority["nested_metadata_artifacts"]:
            reader.retain(reference)
        saved = reader.record(selected["snapshot"]["record"], discovery.snapshot_api.SNAPSHOT)
        original_proof = reader.record(saved["proof_record"], discovery.snapshot_api.compatibility.RESULT_KIND)
        require(digest(saved) == selected["snapshot"]["artifact"] and digest(original_proof) == saved["proof_artifact"]
            and original_proof["source_bindings"] == authority["source_bindings"]
            and original_proof["input_index_digest"] == authority["input_index_digest"], "retained_snapshot_cross_binding")
        prepared, main, reconciled, history, registry = _producer_evidence(reader, selected,
            {"source_bindings": authority["source_bindings"]}, SimpleNamespace(digest=authority["input_index_digest"]), codes)
        reconciliation_gaps = reader.copy(reconciled["artifacts"]["gaps"])
        reconciliation_gap_counts = dict(sorted(Counter(g["reason_code"] for g in reconciliation_gaps).items()))
        require(value["reconciliation_gaps_artifact"] == reconciled["artifacts"]["gaps"]
            and value["reconciliation_gap_counts"] == reconciliation_gap_counts, "retained_reconciliation_gaps")
        descriptors = _descriptors(prepared, main, history, registry, authority["source_bindings"])
        all_bundles = self._rows(BUNDLE)
        require(len(all_bundles) == len(descriptors) and [r["id"] for r in all_bundles] == value["bundle_records"], "retained_bundle_set")
        counts = []
        for descriptor, saved_bundle in zip(descriptors, all_bundles):
            bundle = saved_bundle["payload"]
            raw = self.ledger.db.execute("SELECT logical_key,supersedes FROM records WHERE id=?", (saved_bundle["id"],)).fetchone()
            require(raw["logical_key"] == digest([value["intent_record"], descriptor["owner_sha256"]]) and raw["supersedes"] is None
                and cutoff["created_event"] < saved_bundle["created_event"] < row["created_event"], "retained_bundle_order")
            expected = {**descriptor["refs"], "permitted_source_refs": digest(sorted(set(descriptor["permitted"]))) }
            if descriptor["census"] is not None:
                expected["census"] = digest(descriptor["census"])
            values = {k: self.ledger.artifacts.read(ref) for k, ref in expected.items()}
            summary, missing = _bundle_summary(descriptor, values)
            expected["unmaterialized_refs"] = digest(missing)
            require(self.ledger.artifacts.read(expected["unmaterialized_refs"]) == missing
                and bundle == {"method": METHOD, "intent_record": value["intent_record"], "cutoff_record": cutoff["id"],
                    "owner_sha256": descriptor["owner_sha256"], "source_head": descriptor["source_head"],
                    "artifacts": expected, "summary": summary}, "retained_bundle_projection")
            counts.append(summary)
            reader.values.clear()
        gaps = dict(sorted(Counter(g["reason_code"] for g in registry["declared_gaps"]).items()))
        interrupted = {kind: sum(r["kind"] == kind for r in metadata["records"]) for kind in
            ("cyber_final_validation_task_census_intent", "cyber_final_validation_task_census")}
        require(counts == value["owners"] and gaps == value["declared_gap_counts"]
            and interrupted == value["interrupted_task_census"], "retained_summary_binding")
        require(len(value["liveness"]) == 2, "retained_liveness_pair")
        for observation in value["liveness"]:
            discovery.source_api._retained_liveness(self, observation)
            require(observation["source_owner"] == selected["validation_owner"] and observation["inspection_complete"] is True
                and observation["active_writers"] == observation["matching_processes"] == [], "retained_liveness")
        return {"retained_inventory_record": row["id"], "retained_inventory_artifact": digest(value), **POLICY,
            "owners": counts, "owners_completed": len(counts), "owners_total": len(counts),
            "declared_gap_counts": gaps, "validation_head": value["validation_head"],
            "reconciliation_gap_counts": reconciliation_gap_counts,
            "unresolved_adapter_count": sum(r["adapter"] == "unresolved" for r in registry["adapter_origins"]),
            "interrupted_task_census": interrupted, "reused_completed_inventory": reused,
            "elapsed_seconds_during_collection": value["timings"]["elapsed_seconds"],
            "unique_source_artifact_bytes_read": value["timings"]["unique_source_artifact_bytes_read"]}

    @audited_handler
    def _status(self, session, context, data):
        require_active(self, session)
        require(self.config.offline and data["method"] == METHOD, "offline_method")
        selected = data["binding"]
        started = time.perf_counter()
        processed_rows = 0
        def progress(stage, **fields):
            self._progress({"stage": stage, "elapsed_seconds": round(time.perf_counter() - started, 3),
                "processed_metadata_rows": processed_rows, **fields})
        self._stop(selected)
        progress("verifying_registered_metadata", owners_completed=0, owners_total=None, final_result=False)
        code = implementation()
        codes = {"preparation": preparation.implementation(), "reconciliation": reconciliation.implementation(),
            "main_inventory": preparation.inventory.implementation(), "history_inventory": reconciliation.inventory.implementation()}
        desired = {"method": METHOD, "binding": selected, "implementation": code, "policy": POLICY}
        old, done = self._one(INTENT, optional=True), self._one(RESULT, optional=True)
        require(old is None or old["payload"] == desired, "changed_binding_requires_new_observer")
        if done:
            require(old is not None, "result_without_intent")
            result = self._summary(session, done, desired, codes, reused=True)
            progress("complete_retained_replay", owners_completed=result["owners_completed"], owners_total=result["owners_total"],
                result_record=done["id"], final_result=True)
            return result
        if data["action"] == "status":
            return {"collected": False, "completed_bundles": len(self._rows(BUNDLE)), **POLICY}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol = self._version_once(session, context, "protocol", METHOD, desired)
        self._protocol(intent, protocol, desired)
        before = self._observe(session, Path(selected["validation_owner"]))
        source = MetadataSource(self, session, Path(selected["validation_owner"]))
        try:
            cutoff = {"intent_record": intent, "source_head": source.head(), "source_owner": selected["validation_owner"]}
            prior_cutoff = self._one(CUTOFF, optional=True)
            require(prior_cutoff is None or prior_cutoff["payload"] == cutoff, "resume_cutoff_changed")
            cutoff_id = prior_cutoff["id"] if prior_cutoff else self.ledger.record(session, CUTOFF, intent, cutoff)
            raw_cutoff = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (cutoff_id,)).fetchone()
            require(raw_cutoff["logical_key"] == intent and raw_cutoff["supersedes"] is None
                and self._protocol(intent, protocol, desired) < raw_cutoff["created_event"], "cutoff_identity_order")
            progress("validation_metadata_census", source_head=cutoff["source_head"], owners_completed=0, owners_total=None, final_result=False)
            metadata = discovery.metadata_census(source)
            processed_rows = len(metadata["events"]) + len(metadata["records"])
            self._stop(selected)
            progress("completed_producer_metadata", source_head=cutoff["source_head"], owners_completed=0, owners_total=None, final_result=False)
            snapshot, index, authority = discovery.verify_snapshot_metadata(self, session, source,
                {"snapshot_record": selected["snapshot"]["record"], "snapshot_artifact": selected["snapshot"]["artifact"]})
            require(authority["study_record"] == selected["study_record"] and authority["seed_record"] == selected["seed_record"], "study_seed_binding")
            reader = Reader(source, self, metadata, code)
            for identity, item in authority["metadata_records"].items():
                reader.record(identity, item["kind"])
            for reference in authority["nested_metadata_artifacts"]:
                reader.retain(reference)
            prepared, main, reconciled, history, registry = _producer_evidence(reader, selected, snapshot, index, codes)
            reconciliation_gaps = reader.copy(reconciled["artifacts"]["gaps"])
            reconciliation_gap_counts = dict(sorted(Counter(g["reason_code"] for g in reconciliation_gaps).items()))
            descriptors = _descriptors(prepared, main, history, registry, snapshot["source_bindings"])
            existing = self._rows(BUNDLE)
            expected_owners = [d["owner_sha256"] for d in descriptors]
            require([r["payload"]["owner_sha256"] for r in existing] == expected_owners[:len(existing)], "partial_bundle_partition")
            # Retain only the small producer proof here. Owner metadata is processed
            # one bundle at a time; neither decoded arrays nor raw bytes accumulate.
            producer_evidence = self.ledger.artifacts.put({"records": reader.rows,
                "events": list(reader.proof_events.values()), "artifacts": sorted(reader.copied)})
            reader.values.clear()
            bundles, owners = [], []
            for position, descriptor in enumerate(descriptors):
                self._stop(selected)
                progress("reading_owner_metadata", owners_completed=len(bundles), owners_total=len(descriptors),
                    current_owner_sha256=descriptor["owner_sha256"], unique_source_artifacts_read=len(source.read_hashes),
                    unique_source_artifact_bytes_read=source.unique_read_bytes, final_result=False)
                values = {k: reader.copy(v) for k, v in descriptor["refs"].items()}
                summary, missing = _bundle_summary(descriptor, values)
                processed_rows += summary["events"] + summary["records"]
                refs = dict(descriptor["refs"])
                refs["permitted_source_refs"] = self.ledger.artifacts.put(sorted(set(descriptor["permitted"])))
                refs["unmaterialized_refs"] = self.ledger.artifacts.put(missing)
                if descriptor["census"] is not None:
                    refs["census"] = self.ledger.artifacts.put(descriptor["census"])
                bundle = {"method": METHOD, "intent_record": intent, "cutoff_record": cutoff_id,
                    "owner_sha256": descriptor["owner_sha256"], "source_head": descriptor["source_head"],
                    "artifacts": refs, "summary": summary}
                key = digest([intent, descriptor["owner_sha256"]])
                previous = existing[position] if position < len(existing) else None
                require(previous is None or previous["payload"] == bundle, "changed_completed_bundle")
                if previous:
                    raw = self.ledger.db.execute("SELECT * FROM records WHERE id=?", (previous["id"],)).fetchone()
                    require(raw["logical_key"] == key and raw["supersedes"] is None
                        and raw_cutoff["created_event"] < raw["created_event"], "partial_bundle_identity")
                self._stop(selected)
                identity = previous["id"] if previous else self.ledger.record(session, BUNDLE, key, bundle)
                bundles.append(identity)
                owners.append(summary)
                values.clear()
                reader.values.clear()
                progress("completed_owner_bundle", owners_completed=len(bundles), owners_total=len(descriptors),
                    owners_remaining=len(descriptors)-len(bundles), last_completed_bundle=identity,
                    last_owner_sha256=descriptor["owner_sha256"], source_head=cutoff["source_head"],
                    unique_source_artifacts_read=len(source.read_hashes), unique_source_artifact_bytes_read=source.unique_read_bytes,
                    unmaterialized_references_in_completed_bundles=sum(r["references_not_materialized_by_owner_bundle"] for r in owners), final_result=False)
            interrupted = {kind: sum(r["kind"] == kind for r in metadata["records"]) for kind in
                ("cyber_final_validation_task_census_intent", "cyber_final_validation_task_census")}
            self._stop(selected)
            after = self._observe(session, source.owner)
            require(source.head(fresh=True) == cutoff["source_head"] and implementation() == code, "source_or_code_changed")
            value = {"method": METHOD, "binding": desired, "policy": POLICY, "intent_record": intent,
                "protocol_record": protocol, "cutoff_record": cutoff_id, "validation_head": cutoff["source_head"],
                "metadata_artifact": self.ledger.artifacts.put(metadata), "snapshot_authority": self.ledger.artifacts.put(authority),
                "producer_evidence": producer_evidence, "bundle_records": bundles,
                "reconciliation_gaps_artifact": reconciled["artifacts"]["gaps"], "reconciliation_gap_counts": reconciliation_gap_counts,
                "owners": owners, "declared_gap_counts": dict(sorted(Counter(g["reason_code"] for g in registry["declared_gaps"]).items())),
                "interrupted_task_census": interrupted, "liveness": [before, after],
                "timings": {"elapsed_seconds": round(time.perf_counter()-started, 3), "unique_source_artifact_bytes_read": source.unique_read_bytes,
                    "unique_source_artifacts_read": len(source.read_hashes), "processed_metadata_rows": processed_rows}}
            identity = self.ledger.record(session, RESULT, intent, value)
            progress("complete", owners_completed=len(owners), owners_total=len(owners), owners_remaining=0,
                result_record=identity, source_head=cutoff["source_head"], unique_source_artifact_bytes_read=source.unique_read_bytes, final_result=True)
            return {"retained_inventory_record": identity, "retained_inventory_artifact": digest(value), **POLICY,
                "owners": owners, "owners_completed": len(owners), "owners_total": len(owners),
                "declared_gap_counts": value["declared_gap_counts"], "validation_head": cutoff["source_head"],
                "reconciliation_gap_counts": reconciliation_gap_counts,
                "unresolved_adapter_count": sum(r["adapter"] == "unresolved" for r in registry["adapter_origins"]),
                "interrupted_task_census": interrupted, "reused_completed_inventory": False,
                "elapsed_seconds_during_collection": value["timings"]["elapsed_seconds"],
                "unique_source_artifact_bytes_read": source.unique_read_bytes}
        finally:
            source.close()
