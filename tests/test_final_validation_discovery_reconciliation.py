"""Real temporary audited discovery import and conservative census delegation."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_discovery_reconciliation as subject  # noqa: E402
import final_validation_task_census_parent as tasks  # noqa: E402
import test_final_validation_preparation_v11 as preparation_fixture  # noqa: E402
import test_final_validation_root_discovery as discovery_fixture  # noqa: E402


@pytest.fixture(autouse=True)
def no_process_access(monkeypatch):
    monkeypatch.setattr(subject.discovery.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: [preparation_fixture.process()]))


def setup(tmp_path):
    main, owner, selected = preparation_fixture.setup(tmp_path)
    prepared, _ = preparation_fixture.run(owner, main, selected)
    base = tmp_path / "catalog-base"
    base.mkdir()
    roots = subject.discovery.closure._catalog()[1]["roots"]
    hint = next(r for r in roots if r["selector"]["kind"] == "owner_basename_hint" and r["id"] != "current-main")
    external = base / hint["selector"]["basename"]
    source = discovery_fixture.Historical(external, config=Config(offline=True))
    try:
        private = source.execute("status", {}, objective="Synthetic historical manual evidence", actor="test")
    finally:
        source.close()
    discovery_owner = tmp_path / "discovery"
    writer = subject.discovery.RootDiscovery(discovery_owner)
    discovery_input = {"base_directory": str(base), "validation_owner": str(owner), "snapshot_binding": selected["snapshot_binding"]}
    try:
        found = discovery_fixture.call(writer, discovery_input)
    finally:
        writer.close()
    binding = subject.reconciliation.binding(preparation_record=prepared["preparation_record"],
        **{key: selected[key] for key in ("study_record", "seed_record", "snapshot_binding")})
    locator = {"discovery_owner": str(discovery_owner), "discovery_record": found["discovery_record"],
        "registry_artifact": found["registry_artifact"]}
    return main, owner, external, private, binding, locator, discovery_input


def call(engine, binding, locator, action="import"):
    return engine.execute("status", {"action": action, "binding": binding, "discovery": locator},
        objective="Synthetic immutable discovery registry transfer", actor="test")


def test_actual_import_reopen_and_delegated_reconciliation_task_census_preserve_all_gaps(tmp_path, monkeypatch):
    main, owner, external, private, binding, locator, _ = setup(tmp_path)
    source_paths = (main, external, Path(locator["discovery_owner"]))
    before = {str(p): preparation_fixture.source_bytes(p) for p in source_paths}
    engine = subject.DiscoveryReconciliation(owner, source_owner=main)
    try:
        assert not call(engine, binding, locator, "status")["imported"]
        assert not engine._rows(subject.INTENT)
        # A live source writer blocks at the OS lock; no bypass or source engine.
        writer = Research(Path(locator["discovery_owner"]), config=Config(offline=True))
        try:
            with pytest.raises(AuditError):
                call(engine, binding, locator)
        finally:
            writer.close()
        observe = subject.discovery.source_api.Source.artifact_bytes
        opened = []
        def bounded(source, ref):
            opened.append((str(source.owner), ref))
            assert source.owner == Path(locator["discovery_owner"])
            assert ref != private["source"]
            return observe(source, ref)
        record = engine.ledger.record
        def locked(session, kind, key, value, *args, **kwargs):
            if kind == subject.RESULT:
                with pytest.raises(AuditError):
                    Research(Path(locator["discovery_owner"]), config=Config(offline=True))
            return record(session, kind, key, value, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(subject.discovery.source_api.Source, "artifact_bytes", bounded)
            patch.setattr(engine.ledger, "record", locked)
            imported = call(engine, binding, locator)
        assert opened and imported["discovery_quiescence_verified_during_import"]
        assert not imported["current_discovery_quiescence_claimed"]
        assert imported["counts"]["root_count"] == 35
        assert imported["counts"]["owner_count"] == 2
        assert imported["counts"]["unresolved_root_count"] == 34
        assert imported["counts"]["external_registry_owners"] == imported["counts"]["unresolved_adapters"] == 1
        assert imported["counts"]["declared_global_gaps"] == 3
        assert imported["counts"]["logical_tasks_classified"] is None
        assert not imported["history_complete"] and not imported["dispatch_authorized"]
        assert not engine._rows(subject.reconciliation.INTENT_KIND)
        assert str(tmp_path) not in canonical(imported) and "PRIVATE" not in canonical(imported)
        retained = engine._one(subject.RESULT)["payload"]
        bundle_ref = retained["bundle_artifact"]
        bundle = engine.ledger.artifacts.read(bundle_ref)
        assert private["source"] not in bundle["artifacts"]
        # Original-row substitutions, not duplicate result fixtures. All fail
        # retained verification before a source open or reconciliation delegate.
        changes = []
        changed = deepcopy(bundle)
        changed["source_owner"] = str(tmp_path / "foreign")
        changes.append(changed)
        changed = deepcopy(bundle)
        changed["source_head"][1] = digest("foreign")
        changes.append(changed)
        changed = deepcopy(bundle)
        changed["artifacts"].append(engine.ledger.artifacts.put({"foreign": "metadata"}))
        changed["artifacts"].sort()
        changes.append(changed)
        changed = deepcopy(bundle)
        changed["session_events"] = [e for e in changed["session_events"] if e["kind"] != "operation.completed"]
        changes.append(changed)
        changed = deepcopy(bundle)
        changed["records"][locator["discovery_record"]]["logical_key"] = "foreign"
        changes.append(changed)
        read = engine.ledger.artifacts.read
        with monkeypatch.context() as patch:
            patch.setattr(subject.discovery.source_api.Source, "__init__", lambda *_: pytest.fail("Retained replay cannot open source"))
            for changed in changes:
                patch.setattr(engine.ledger.artifacts, "read", lambda ref, changed=changed: deepcopy(changed) if ref == bundle_ref else read(ref))
                with pytest.raises(AuditError):
                    call(engine, binding, locator, "status")
            patch.setattr(engine.ledger.artifacts, "read", read)
            again = call(engine, binding, locator, "status")
        assert again["import_record"] == imported["import_record"] and not again["discovery_quiescence_verified_during_import"]
        # Same immutable registry enters the original audited handler.
        result = call(engine, binding, locator, "reconcile")
        assert result["reconciliation"]["counts"]["owners"] == 1
        assert result["reconciliation_gap_counts"]["owner_adapter_unresolved"] == 1
        assert result["reconciliation_gap_counts"]["study_history_scope_missing"] == 1
        assert result["reconciliation_gap_counts"]["manual_review_scope_missing"] == 1
        saved = engine.ledger.get(result["reconciliation"]["reconciliation_record"], subject.reconciliation.RESULT_KIND)
        assert saved["registry_artifact"] == locator["registry_artifact"]
        certificate = engine.ledger.artifacts.read(saved["artifacts"]["pair_history_inventory"])
        assert certificate["global_gap"] and not certificate["complete"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        wrong = {**locator, "registry_artifact": digest("different")}
        with pytest.raises(AuditError, match="changed_import_requires_amendment"):
            call(engine, binding, wrong)
    finally:
        engine.close()
    census = tasks.TaskCensusParent(owner, source_owner=main)
    try:
        task_result = census.execute("status", {"action": "collect", "binding": {
            "preparation_binding": binding, "reconciliation_record": result["reconciliation"]["reconciliation_record"]}},
            objective="Synthetic complete task census after exact import", actor="test")
        assert task_result["new_model_calls"] == 0 and not task_result["dispatch_authorized"]
    finally:
        census.close()
    for path, values in before.items():
        assert preparation_fixture.source_bytes(Path(path)) == values
    engine = subject.DiscoveryReconciliation(owner, source_owner=main)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(subject.discovery.source_api.Source, "__init__", lambda *_: pytest.fail("No source reopening on historical status"))
            status = call(engine, binding, locator, "status")
        assert status["reconciliation"]["reused_historical_reconciliation"]
    finally:
        engine.close()


@pytest.mark.parametrize("field,value", [
    ("discovery_owner", "relative"), ("discovery_owner", ""),
    ("discovery_record", "bad"), ("registry_artifact", "bad"),
])
def test_locator_rejects_missing_exact_authority(field, value, tmp_path):
    locator = {"discovery_owner": str(tmp_path / "discovery"), "discovery_record": digest("record"), "registry_artifact": digest("registry")}
    locator[field] = value
    with pytest.raises((AuditError, ValueError)):
        subject.validate_locator(locator)


def test_locator_rejects_semantic_override(tmp_path):
    with pytest.raises(AuditError, match="locator_fields"):
        subject.validate_locator({"discovery_owner": str(tmp_path), "discovery_record": digest("r"),
            "registry_artifact": digest("a"), "complete": True})


def test_partial_import_pins_cutoff_and_never_adopts_new_discovery_head(tmp_path, monkeypatch):
    main, owner, _, _, binding, locator, discovery_input = setup(tmp_path)
    engine = subject.DiscoveryReconciliation(owner, source_owner=main)
    try:
        capture = engine._capture
        with monkeypatch.context() as patch:
            patch.setattr(engine, "_capture", lambda *_: (_ for _ in ()).throw(AuditError("synthetic_copy_failure")))
            with pytest.raises(AuditError, match="synthetic_copy_failure"):
                call(engine, binding, locator)
        assert engine._one(subject.CUTOFF) and not engine._rows(subject.RESULT)
        read = subject.discovery.source_api.Source.artifact_bytes
        with monkeypatch.context() as patch:
            patch.setattr(subject.discovery.source_api.Source, "artifact_bytes", lambda source, ref:
                b'{"foreign":true}' if ref == locator["registry_artifact"] else read(source, ref))
            with pytest.raises(AuditError, match="copied_artifact_identity"):
                call(engine, binding, locator)
        assert not engine._rows(subject.RESULT)
        writer = subject.discovery.RootDiscovery(Path(locator["discovery_owner"]))
        try:
            discovery_fixture.call(writer, discovery_input, "status")
        finally:
            writer.close()
        with monkeypatch.context() as patch:
            patch.setattr(engine, "_capture", lambda *_: pytest.fail("Changed cutoff must fail before metadata capture"))
            with pytest.raises(AuditError, match="incomplete_import_cutoff_changed"):
                call(engine, binding, locator)
        assert capture and not engine._rows(subject.reconciliation.INTENT_KIND)
    finally:
        engine.close()


class ProtocolFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        desired = data["desired"]
        if data["fault"] == "before_intent":
            self._version(session, context, {"kind": "protocol", "key": subject.METHOD, "content": desired})
        self.ledger.record(session, subject.INTENT, subject.METHOD, desired)
        if data["fault"] != "before_intent":
            for number in range(2 if data["fault"] == "duplicate" else 1):
                content = desired if number == 0 else {**desired, "extra": True}
                self._version(session, context, {"kind": "protocol", "key": subject.METHOD, "content": content,
                    **({"reason": "synthetic contradiction"} if data["fault"] == "reason" else {})})
        return {"written": True}


@pytest.mark.parametrize("fault", ["before_intent", "duplicate", "reason"])
def test_local_protocol_must_be_prospective_and_unique_before_any_snapshot_or_source_access(tmp_path, monkeypatch, fault):
    binding = {"preparation_record": digest("prep"), "study_record": digest("study"), "seed_record": digest("seed"),
        "snapshot_binding": {"snapshot_record": digest("snapshot"), "snapshot_artifact": digest("artifact")}}
    locator = {"discovery_owner": str(tmp_path / "remote"), "discovery_record": digest("d"), "registry_artifact": digest("r")}
    desired = {"method": subject.METHOD, "implementation": subject.implementation(), "policy": subject.POLICY,
        "preparation_binding": binding, "preparation_artifact": digest({}), "discovery": locator}
    fixture = ProtocolFixture(tmp_path / "observer", config=Config(offline=True))
    try:
        fixture.execute("status", {"desired": desired, "fault": fault}, objective="Synthetic contradictory prior protocol", actor="test")
    finally:
        fixture.close()
    engine = subject.DiscoveryReconciliation(tmp_path / "observer", source_owner=tmp_path / "main")
    try:
        monkeypatch.setattr(engine, "_prepared", lambda _: (None, None, {}))
        monkeypatch.setattr(subject, "local_snapshot_metadata", lambda *_: pytest.fail("Protocol must fail before snapshot replay"))
        monkeypatch.setattr(subject.discovery.source_api.Source, "__init__", lambda *_: pytest.fail("Protocol must fail before source access"))
        with pytest.raises(AuditError, match="prospective_import_protocol|version_replaced|version_binding_changed"):
            call(engine, binding, locator)
        assert not engine._rows(subject.CUTOFF) and not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_retained_artifact_scope_rejects_unlisted_pointer_before_read():
    class Forbidden:
        def read(self, reference):
            pytest.fail("Foreign artifact cannot be read")
        read_bytes = read
    scoped = subject._ScopedArtifacts(Forbidden(), [digest("allowed")])
    with pytest.raises(AuditError, match="retained_artifact_scope"):
        scoped.read(digest("foreign"))
