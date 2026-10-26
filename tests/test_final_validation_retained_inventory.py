"""Small real audit/readonly-source boundary; no full preparation pipeline.

Snapshot is genuine. Preparation/Reconciliation are explicitly synthetic native
metadata producers: their actual Research operations/version/record envelopes
exercise the transfer contract without embeddings, frame work or model calls.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_retained_inventory as subject  # noqa: E402
import test_final_validation_snapshot_v11 as snapshot_fixture  # noqa: E402
from test_final_validation_study import process  # noqa: E402


def stored_rows(owner):
    db = sqlite3.connect((owner / "research.sqlite3").as_uri() + "?mode=ro&immutable=1", uri=True)
    db.row_factory = sqlite3.Row
    try:
        return ([dict(r) for r in db.execute("SELECT * FROM events ORDER BY seq")],
            [dict(r) for r in db.execute("SELECT * FROM records ORDER BY created_event")])
    finally:
        db.close()


def file_hashes(owner):
    return {str(p.relative_to(owner)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in owner.rglob("*") if p.is_file()}


class External(Research):
    @audited_handler
    def _status(self, session, context, data):
        body = self.ledger.artifacts.put({"text": "PRIVATE BODY: synthetic historical article"})
        self.ledger.record(session, "unknown_manual_review", "unclassified", {"body_artifact": body})
        self.ledger.append(session, "model.attempt.intended", {"attempt": "synthetic-orphan",
            "request": body, "dispatch": self.ledger.artifacts.put({"synthetic": True})})
        return {"body": body}


class NativeMetadata(snapshot_fixture.subject.SnapshotParent):
    """Exact recorded producer schemas; explicitly not semantic preparation."""
    source_events = None
    source_records = None
    external = None
    registry = None

    def versions(self, session, context, method, contents):
        return {kind: self._version(session, context, {"kind": kind, "key": method, "content": value})["id"]
            for kind, value in contents.items()}

    @audited_handler
    def _status(self, session, context, data):
        prep, rec = subject.preparation, subject.reconciliation
        selected = data["binding"]
        if data["method"] == subject.delegated.METHOD:
            module = subject.delegated
            if data["action"] == "import":
                desired = {"method": module.METHOD, "implementation": module.implementation(), "policy": module.POLICY,
                    "preparation_binding": selected, "preparation_artifact": digest(self.ledger.get(selected["preparation_record"], prep.RESULT_KIND)),
                    "discovery": data["discovery"]}
                intent = self.ledger.record(session, module.INTENT, module.METHOD, desired)
                protocol = self._version(session, context, {"kind": "protocol", "key": module.METHOD, "content": desired})["id"]
                self.ledger.record(session, module.CUTOFF, intent, {"intent_record": intent,
                    "discovery_owner": data["discovery"]["discovery_owner"], "source_head": [1, digest("synthetic-discovery-head")]})
                value = {"method": module.METHOD, "binding": desired, "policy": module.POLICY,
                    "intent_record": intent, "protocol_record": protocol,
                    "bundle_artifact": self.ledger.artifacts.put({"synthetic_native_import_metadata_only": True}), "liveness": []}
                identity = self.ledger.record(session, module.RESULT, intent, value)
                return {"import_record": identity, "import_artifact": digest(value)}
            imported = self._one(module.RESULT)
            nested = self._status(session, context, {"method": rec.METHOD, "action": "reconcile", "binding": selected, "registry": self.registry})
            return {"import_record": imported["id"], "import_artifact": digest(imported["payload"]), "reconciliation": nested}
        snapshot, index = snapshot_fixture.subject.load_snapshot(self, session, selected["snapshot_binding"])
        seeds = self.ledger.get(selected["seed_record"], subject.discovery.study.SEEDS)
        seed_refs = {k: seeds[k] for k in ("schedule_seed_artifact", "article_order_seed_artifact")}
        put = self.ledger.artifacts.put
        if data["method"] == prep.METHOD:
            code = prep.implementation()
            registered = self.ledger.get(selected["study_record"], subject.discovery.study.STUDY)
            desired = {"method": prep.METHOD, "binding": selected, "implementation": code,
                "policy": prep.POLICY, "original_study_artifact": digest(registered),
                "registered_specification_artifact": registered["specification_artifact"]}
            intended = self.ledger.record(session, prep.INTENT_KIND, prep.METHOD, desired)
            versions = self.versions(session, context, prep.METHOD, {
                "protocol": {"method": prep.METHOD, "implementation": code, "preparation_intent": intended,
                    "binding_sha256": digest(selected), "additional_source_metadata_scope": "exact-original-plan-versions.embedding_profile-record-only"},
                "selection": {"rules": "Entire frozen input frame; actual main-owner evidence; unresolved cross-study scope.", "binding_sha256": digest(selected)},
                "policy": {"mode": "offline-intermediate-preparation-only", **prep.POLICY,
                    "preparation_intent": intended, "binding_sha256": digest(selected)}})
            contents = {k: {"snapshot_binding_sha256": digest(selected["snapshot_binding"]),
                "preparation_intent": intended, "preparation_protocol": versions["protocol"]} for k in ("protocol", "selection")}
            contents["protocol"].update(method=prep.inventory.METHOD, implementation=prep.inventory.implementation())
            contents["selection"]["rules"] = "Complete immutable main-owner census under the registered final cutoff."
            inventory_versions = self.versions(session, context, prep.METHOD + ":inventory", contents)
            records = [r for r in self.source_records if r["kind"] in {"cyber_dossier_response", "cyber_dossier_seed_revalidation"}]
            phases = [r for r in self.source_records if r["kind"] == "cyber_dossier_phase"]
            created = {r["created_event"] for r in records}
            phase_created = {r["created_event"] for r in phases}
            events = [e for e in self.source_events if e["kind"] == "model.attempt.intended" or e["seq"] in created]
            phase_events = [e for e in self.source_events if e["seq"] in phase_created]
            refs = {k: put([]) for k in subject.MAIN_REFS}
            refs.update(events_artifact=put(events), records_artifact=put(records),
                phase_events_artifact=put(phase_events), phase_records_artifact=put(phases),
                pair_inventory_artifact=put({"gaps": [{"reason_code": "unresolved_main_history"}]}),
                census_artifact=put({"synthetic_metadata_only": True}))
            main = {"method": prep.inventory.METHOD, "implementation": prep.inventory.implementation(),
                "versions": inventory_versions, "snapshot_binding": selected["snapshot_binding"],
                "source_bindings": snapshot["source_bindings"], "input_index_digest": index.digest,
                "source_head_stable": True, "full_source_ledger_preflight_verified": True,
                "original_study_record": selected["study_record"], "original_seed_record": selected["seed_record"],
                "permitted_source_artifacts": [self.external["body"]], **refs}
            inventory_id = self.ledger.record(session, prep.inventory.RESULT_KIND, digest(selected["snapshot_binding"]), main)
            value = {"method": prep.METHOD, **prep.POLICY, "binding": selected, "implementation": code,
                "preparation_intent": intended, "versions": versions, **seed_refs,
                "inventory": {"inventory_record": inventory_id, "inventory_artifact": digest(main)},
                "contributions": {k: put({"synthetic_metadata_only": k}) for k in subject.ROLE_REFS}}
            identity = self.ledger.record(session, prep.RESULT_KIND, intended, value)
            return {"preparation_record": identity, "preparation_artifact": digest(value)}
        assert data["method"] == rec.METHOD
        registry = data["registry"]
        code = rec.implementation()
        prepared = self.ledger.get(selected["preparation_record"], prep.RESULT_KIND)
        desired = {"method": rec.METHOD, "binding": selected, "registry_sha256": put(registry),
            "preparation_artifact": digest(prepared), "implementation": code, "policy": rec.POLICY}
        intended = self.ledger.record(session, rec.INTENT_KIND, rec.METHOD, desired)
        versions = self.versions(session, context, rec.METHOD, {
            "protocol": {"method": rec.METHOD, "implementation": code, "binding_sha256": digest(selected),
                "registry_sha256": digest(registry), "reconciliation_intent": intended},
            "selection": {"rules": "Exactly declared external owners and native/copy mappings; unresolved scope retained.",
                "binding_sha256": digest(selected), "registry_sha256": digest(registry)},
            "policy": {"mode": "offline-contributions-only", **rec.POLICY, "reconciliation_intent": intended}})
        declaration = {"snapshot_binding": selected["snapshot_binding"], "owners_sha256": digest(registry["owners"]),
            "declared_gaps": registry["declared_gaps"], "scope": "explicit_recorded_study_sources_only", "universal_history_completeness_claimed": False}
        binding = {"snapshot_binding": selected["snapshot_binding"], "owners": registry["owners"],
            "declared_gaps": registry["declared_gaps"], "registry_declaration_artifact": put(declaration)}
        contents = {k: {"binding_sha256": digest(binding), "parent_protocol": versions["protocol"]} for k in ("protocol", "selection")}
        contents["protocol"].update(method=rec.inventory.METHOD, implementation=rec.inventory.implementation())
        contents["selection"]["rules"] = "Complete declared immutable ledgers; no semantic inference from kind or owner name."
        inventory_versions = self.versions(session, context, rec.METHOD + ":inventory", contents)
        scope = registry["owners"][0]
        ext = self.external
        census = {"owner_sha256": digest(scope["source_owner"]), "source_head": scope["source_head"],
            "scope_sha256": digest(scope), "selected_record_ids": [r["id"] for r in ext["records"]],
            "selected_event_hashes": [e["event_hash"] for e in ext["events"]]}
        history = {"method": rec.inventory.METHOD, "implementation": rec.inventory.implementation(),
            "versions": inventory_versions, "binding": binding, "input_index_digest": index.digest,
            "source_head_stable": True, "full_declared_source_ledger_preflight_verified": True,
            "main_final_cutoff_guard": {"source_head": snapshot["source_bindings"]["source_head"], "head_stable": True},
            "owners": [{"census": census, "events_artifact": put(ext["events"]), "records_artifact": put(ext["records"]),
                "gaps_artifact": put([{ "reason_code": "unknown_manual_semantics"}]), "permitted_source_artifacts": [ext["body"]]}]}
        inventory_id = self.ledger.record(session, rec.inventory.RESULT_KIND, digest(binding), history)
        value = {"method": rec.METHOD, **rec.POLICY, "binding": selected, "implementation": code,
            "reconciliation_intent": intended, "versions": versions, "registry_artifact": digest(registry), **seed_refs,
            "artifacts": {"gaps": put([{"reason_code": "unresolved_owner_adapter"}, {"reason_code": "unresolved_owner_adapter"}])},
            "inventory": {"inventory_record": inventory_id, "inventory_artifact": digest(history)}}
        identity = self.ledger.record(session, rec.RESULT_KIND, intended, value)
        return {"reconciliation_record": identity, "reconciliation_artifact": digest(value)}


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    base = tmp_path_factory.mktemp("retained-inventory-native")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subject.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
        source, frozen_binding, registered = snapshot_fixture.initialized(base)
        observer = base / "validation"
        engine = snapshot_fixture.subject.SnapshotParent(observer, source_owner=source)
        try:
            frozen = snapshot_fixture.execute(engine, frozen_binding)
        finally:
            engine.close()
        ext = External(base / "external", config=Config(offline=True))
        try:
            body = ext.execute("status", {}, objective="Synthetic external metadata", actor="test")["body"]
        finally:
            ext.close()
        external_events, external_records = stored_rows(base / "external")
        external = {"body": body, "events": external_events, "records": external_records}
        selected = subject.preparation.binding(study_record=registered["study_record"], seed_record=registered["seed_record"],
            snapshot_binding=snapshot_fixture.selected(frozen))
        engine = NativeMetadata(observer, source_owner=source)
        engine.source_events, engine.source_records = stored_rows(source)
        engine.external = external
        try:
            prepared = Research.execute(engine, "status", {"method": subject.preparation.METHOD, "action": "prepare", "binding": selected},
                objective="Synthetic native preparation metadata", actor="test")
            engine.close()
            delegated_owner = base / "delegated-validation"
            prepare_root(delegated_owner)
            shutil.copytree(observer, delegated_owner, dirs_exist_ok=True)
            engine = NativeMetadata(observer, source_owner=source)
            engine.external = external
            reconciliation_binding = {k: selected[k] for k in ("study_record", "seed_record", "snapshot_binding")}
            reconciliation_binding["preparation_record"] = prepared["preparation_record"]
            scope = {"source_owner": str(base / "external"), "source_head": [external_events[-1]["seq"], external_events[-1]["event_hash"]]}
            registry = {"owners": [scope], "declared_gaps": [{"reason_code": "manual_review_scope_missing", "affected_input_sha256": None}],
                "adapter_origins": [{"owner_sha256": digest(scope["source_owner"]), "adapter": "unresolved", "origin_owner_sha256": None}]}
            reconciled = Research.execute(engine, "status", {"method": subject.reconciliation.METHOD, "action": "reconcile",
                "binding": reconciliation_binding, "registry": registry}, objective="Synthetic native reconciliation metadata", actor="test")
        finally:
            engine.close()
        delegated_engine = NativeMetadata(delegated_owner, source_owner=source)
        delegated_engine.external, delegated_engine.registry = external, registry
        locator = {"discovery_owner": str(base / "recorded-discovery-only"),
            "discovery_record": digest("synthetic-discovery-record"), "registry_artifact": digest(registry)}
        try:
            incoming = {"method": subject.delegated.METHOD, "action": "import", "binding": reconciliation_binding, "discovery": locator}
            Research.execute(delegated_engine, "status", incoming, objective="Synthetic native completed import", actor="test")
            incoming["action"] = "reconcile"
            delegated_result = Research.execute(delegated_engine, "status", incoming,
                objective="Synthetic native delegated reconciliation", actor="test")["reconciliation"]
        finally:
            delegated_engine.close()
    return {"owner": observer, "source": source, "external": base / "external", "body": body,
        "delegated_owner": delegated_owner, "delegated_result": delegated_result,
        "binding": {"validation_owner": str(observer), "study_record": selected["study_record"], "seed_record": selected["seed_record"],
            "snapshot": {"record": frozen["snapshot_record"], "artifact": frozen["snapshot_artifact"]},
            "preparation": {"record": prepared["preparation_record"], "artifact": prepared["preparation_artifact"]},
            "reconciliation": {"record": reconciled["reconciliation_record"], "artifact": reconciled["reconciliation_artifact"]}}}


@pytest.fixture
def case(tmp_path, template, monkeypatch):
    monkeypatch.setattr(subject.discovery.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    validation = tmp_path / "retained-validation"
    prepare_root(validation)
    shutil.copytree(template["owner"], validation, dirs_exist_ok=True)
    selected = deepcopy(template["binding"])
    selected["validation_owner"] = str(validation)
    return tmp_path / "small-observer", validation, selected, template


def collect(engine, selected, action="collect"):
    return engine.execute("status", {"action": action, "binding": selected}, objective="Synthetic retained metadata transfer", actor="test")


def test_native_completed_metadata_one_pass_readonly_and_reopen(case, monkeypatch):
    observer, validation, selected, original = case
    before = file_hashes(validation)
    untouched = {p: file_hashes(p) for p in (original["source"], original["external"])}
    reads = []
    readers, saved_readers = [], []
    cached = {}
    native_reader, native_saved = subject.Reader.__init__, subject.SavedReader.__init__
    def capture_reader(reader, *args, **kwargs):
        native_reader(reader, *args, **kwargs)
        readers.append(reader)
    def capture_saved(reader, *args, **kwargs):
        native_saved(reader, *args, **kwargs)
        saved_readers.append(reader)
    monkeypatch.setattr(subject.Reader, "__init__", capture_reader)
    monkeypatch.setattr(subject.SavedReader, "__init__", capture_saved)
    native_copy = subject.Reader.copy
    def capture_copy(reader, reference):
        value = native_copy(reader, reference)
        cached[id(reader)] = (reference, value)
        return value
    monkeypatch.setattr(subject.Reader, "copy", capture_copy)
    native_read = subject.discovery.source_api.Source.artifact_bytes
    def guarded(source, reference):
        assert reference != original["body"], "provider/source body must not be traversed"
        reads.append(reference)
        return native_read(source, reference)
    monkeypatch.setattr(subject.discovery.source_api.Source, "artifact_bytes", guarded)
    engine = subject.RetainedInventory(observer)
    progress = []
    native_progress, native_census = engine._progress, subject.discovery.metadata_census
    def record_progress(value):
        progress.append(value)
        native_progress(value)
    def guarded_census(*args, **kwargs):
        assert progress[0]["stage"] == "verifying_registered_metadata"
        return native_census(*args, **kwargs)
    monkeypatch.setattr(engine, "_progress", record_progress)
    monkeypatch.setattr(subject.discovery, "metadata_census", guarded_census)
    try:
        result = collect(engine, selected)
        assert result["owners_completed"] == result["owners_total"] == 2
        assert result["new_model_calls"] == result["historical_owners_opened"] == 0
        assert not result["dispatch_authorized"] and not result["history_complete"] and not result["gaps_removed"]
        assert result["declared_gap_counts"] == {"manual_review_scope_missing": 1}
        assert result["reconciliation_gap_counts"] == {"unresolved_owner_adapter": 2}
        assert result["unresolved_adapter_count"] == 1
        main = next(r for r in result["owners"] if r["main_owner"])
        phases = main["additional_main_metadata_partitions"]
        assert phases["phase_records"] == phases["phase_creation_events"] > 0
        assert phases["phase_record_kinds"] == {"cyber_dossier_phase": phases["phase_records"]}
        assert any(r["intended_events"] == 1 for r in result["owners"] if not r["main_owner"])
        assert any(r["record_kinds"].get("unknown_manual_review") == 1 for r in result["owners"])
        assert all(r["logical_tasks_classified"] is None for r in result["owners"])
        assert not (observer / "objects" / original["body"]).exists()
        assert "PRIVATE BODY" not in json.dumps(result)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        retained = result["retained_inventory_record"]
        assert len(reads) == len(set(reads)) > 0
        final_progress = json.loads((observer / "retained-inventory-progress.json").read_text(encoding="utf-8"))
        assert final_progress["final_result"] and final_progress["owners_completed"] == final_progress["owners_total"] == 2
        assert final_progress["elapsed_seconds"] >= 0 and final_progress["processed_metadata_rows"] > 0
        assert final_progress["unique_source_artifact_bytes_read"] > 0
        assert not readers[-1].values
        reference, value = cached[id(readers[-1])]
        readers[-1].values[reference] = value  # Exercise a cache hit after the actual source has closed.
        with pytest.raises(AuditError):
            readers[-1].copy(reference)
    finally:
        engine.close()
    assert file_hashes(validation) == before and all(file_hashes(p) == hashes for p, hashes in untouched.items())
    engine = subject.RetainedInventory(observer)
    try:
        monkeypatch.setattr(subject.MetadataSource, "__init__", lambda *_: pytest.fail("completed reuse reopened source"))
        repeat = collect(engine, selected, "status")
        assert repeat["retained_inventory_record"] == retained and repeat["reused_completed_inventory"]
        assert not repeat["current_source_quiescence_claimed"]
        assert not saved_readers[-1].values
        reference, value = cached[id(saved_readers[-1])]
        saved_readers[-1].values[reference] = value
        with pytest.raises(AuditError):
            saved_readers[-1].copy(reference)
    finally:
        engine.close()


def test_separate_native_import_then_delegated_reconciliation(case, tmp_path):
    observer, _, selected, original = case
    validation = tmp_path / "delegated-copy"
    prepare_root(validation)
    shutil.copytree(original["delegated_owner"], validation, dirs_exist_ok=True)
    selected["validation_owner"] = str(validation)
    selected["reconciliation"] = {"record": original["delegated_result"]["reconciliation_record"],
        "artifact": original["delegated_result"]["reconciliation_artifact"]}
    before = file_hashes(validation)
    engine = subject.RetainedInventory(observer)
    try:
        result = collect(engine, selected)
        assert result["owners_completed"] == 2 and not result["dispatch_authorized"]
        assert result["reconciliation_gap_counts"] == {"unresolved_owner_adapter": 2}
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
    finally:
        engine.close()
    assert file_hashes(validation) == before


@pytest.mark.parametrize("field", ["study_record", "seed_record", "snapshot", "preparation", "reconciliation"])
def test_foreign_selected_identity_fails_without_completed_result(case, field):
    observer, _, selected, _ = case
    if isinstance(selected[field], dict):
        selected[field]["artifact"] = digest("foreign selected artifact")
    else:
        selected[field] = digest("foreign selected authority")
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError):
            collect(engine, selected)
        assert not engine._rows(subject.RESULT)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
    finally:
        engine.close()


def test_corrupt_selected_metadata_rejected(case):
    observer, validation, selected, _ = case
    (validation / "objects" / selected["preparation"]["artifact"]).write_bytes(b"corrupt selected metadata")
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError):
            collect(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_partial_bundle_recovery_reuses_exact_unit_and_head(case, monkeypatch):
    observer, validation, selected, _ = case
    before = file_hashes(validation)
    engine = subject.RetainedInventory(observer)
    native = engine._progress
    def interrupt(value):
        native(value)
        if value.get("owners_completed") == 1:
            raise AuditError("synthetic checkpoint interruption")
    monkeypatch.setattr(engine, "_progress", interrupt)
    try:
        with pytest.raises(AuditError, match="synthetic checkpoint"):
            collect(engine, selected)
        assert len(engine._rows(subject.BUNDLE)) == 1 and not engine._rows(subject.RESULT)
        first = engine._rows(subject.BUNDLE)[0]["id"]
    finally:
        engine.close()
    engine = subject.RetainedInventory(observer)
    try:
        result = collect(engine, selected)
        assert result["owners_completed"] == 2
        assert len(engine._rows(subject.BUNDLE)) == 2 and first in {r["id"] for r in engine._rows(subject.BUNDLE)}
    finally:
        engine.close()
    assert file_hashes(validation) == before


def test_partial_recovery_rejects_changed_validation_head(case, monkeypatch):
    observer, validation, selected, _ = case
    engine = subject.RetainedInventory(observer)
    monkeypatch.setattr(engine, "_progress", lambda value: (_ for _ in ()).throw(AuditError("synthetic checkpoint"))
        if value.get("owners_completed") == 1 else None)
    try:
        with pytest.raises(AuditError, match="synthetic checkpoint"):
            collect(engine, selected)
    finally:
        engine.close()
    writer = Research(validation, config=Config(offline=True))
    try:
        writer.execute("status", {}, objective="Synthetic later owner operation", actor="test")
    finally:
        writer.close()
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError, match="resume_cutoff_changed"):
            collect(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("kind", [subject.CUTOFF, subject.BUNDLE])
def test_partial_same_payload_wrong_key_cannot_be_adopted(case, monkeypatch, kind):
    observer, _, selected, _ = case
    engine = subject.RetainedInventory(observer)
    native = engine.ledger.record
    def wrong_key(session, record_kind, key, value, *args, **kwargs):
        if record_kind == kind:
            native(session, record_kind, "synthetic-wrong-key", value, *args, **kwargs)
            raise AuditError("synthetic wrong-key interruption")
        return native(session, record_kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", wrong_key)
    try:
        with pytest.raises(AuditError, match="synthetic wrong-key"):
            collect(engine, selected)
    finally:
        engine.close()
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError):
            collect(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_source_writer_lock_blocks_collection(case):
    observer, validation, selected, _ = case
    writer = Research(validation, config=Config(offline=True))
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError):
            collect(engine, selected)
        assert not engine._rows(subject.BUNDLE) and not engine._rows(subject.RESULT)
    finally:
        engine.close()
        writer.close()


@pytest.mark.parametrize("action", ["run", "resume", "dispatch"])
def test_no_model_operation_allowance(case, action):
    observer, _, selected, _ = case
    engine = subject.RetainedInventory(observer)
    try:
        with pytest.raises(AuditError, match="operation_shape"):
            collect(engine, selected, action)
        assert not engine._rows(subject.INTENT)
    finally:
        engine.close()
