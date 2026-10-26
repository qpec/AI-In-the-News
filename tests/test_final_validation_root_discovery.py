"""Finite metadata discovery in temporary synthetic owners only."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_root_discovery as subject  # noqa: E402
import final_validation_reconciliation as reconciliation  # noqa: E402
import test_final_validation_snapshot_v11 as fixture  # noqa: E402


class Historical(Research):
    @audited_handler
    def _status(self, session, context, data):
        source = self.ledger.artifacts.put({"body": "PRIVATE FULL SOURCE NOT READ BY DISCOVERY"})
        row = self.ledger.record(session, "unsupported_manual_pair_review", "manual", {"source": source})
        self.ledger.append(session, "custom.manual.review", {"record": row})
        return {"record": row, "source": source}


@pytest.fixture(autouse=True)
def process_probe(monkeypatch):
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [fixture.process()]))


def actual_fixture(tmp_path):
    main, binding, registration = fixture.initialized(tmp_path)
    writer = subject.snapshot_api.SnapshotParent(tmp_path / "validation", source_owner=main)
    try:
        saved = fixture.execute(writer, binding)
    finally:
        writer.close()
    base = tmp_path / "finite-base"
    base.mkdir()
    catalog = subject.closure._catalog()[1]
    hint = next(r for r in catalog["roots"] if r["selector"]["kind"] == "owner_basename_hint" and r["id"] != "current-main")
    external = base / hint["selector"]["basename"]
    writer = Historical(external, config=Config(offline=True))
    try:
        historical = writer.execute("status", {}, objective="Synthetic manual owner", actor="test")
    finally:
        writer.close()
    return main, base, external, historical, registration, {
        "base_directory": str(base), "validation_owner": str(tmp_path / "validation"),
        "snapshot_binding": fixture.selected(saved)}


def call(engine, binding, action="discover"):
    return engine.execute("status", {"action": action, **binding}, objective="Synthetic finite root metadata discovery", actor="test")


def test_actual_separate_observer_snapshot_cutoffs_registry_locks_no_nested_reads_and_reopen(tmp_path, monkeypatch):
    main, base, external, historical, registration, binding = actual_fixture(tmp_path)
    untouched = base / "unlisted-private-owner"
    untouched.mkdir()
    (untouched / "private.txt").write_text("not enumerated", encoding="utf-8")
    before = {str(p): fixture.bytes_snapshot(p) for p in (main, external, Path(binding["validation_owner"]))}
    observed_artifacts = []
    original_artifact = subject.source_api.Source.artifact_bytes
    def limited(source, reference):
        assert source.owner not in {main, external}, "Discovery must not open main/historical source artifacts"
        observed_artifacts.append(reference)
        return original_artifact(source, reference)
    monkeypatch.setattr(subject.source_api.Source, "artifact_bytes", limited)
    monkeypatch.setattr(subject.study.secrets, "token_hex", lambda *_: pytest.fail("No seed generation"))
    engine = subject.RootDiscovery(tmp_path / "discovery")
    try:
        summary = engine._summary
        def locked(identifier, value, *, reused):
            if identifier == "pending":
                for path in (main, external, Path(binding["validation_owner"])):
                    with pytest.raises(AuditError):
                        Research(path, config=Config(offline=True))
            return summary(identifier, value, reused=reused)
        monkeypatch.setattr(engine, "_summary", locked)
        result = call(engine, binding)
        assert result["owner_count"] == 2 and result["observed_candidate_count"] == 1
        assert result["root_count"] == 35 and result["unresolved_root_count"] == 34
        assert not result["history_complete"] and not result["root_semantics_resolved"]
        assert not result["source_intersections_verified"] and not result["physical_origins_verified"]
        assert not result["dispatch_authorized"] and result["new_model_calls"] == 0
        assert "PRIVATE" not in canonical(result) and str(tmp_path) not in canonical(result)
        states = engine.ledger.artifacts.read(result["root_states_artifact"])
        assert not any(r["source_owner"] == str(untouched) for r in states)
        assert all(r["discovery_state"] == "unresolved_link_or_manual_root" for r in states
            if r["root_id"] in {"event-pair-cross-window", "linked-manual-registry", "sealed-standard-source"})
        registry = engine.ledger.artifacts.read(result["registry_artifact"])
        assert len(registry["owners"]) == 1
        selected = registry["owners"][0]
        assert selected["source_owner"] == str(external) and selected["scope_input_sha256"] is None
        assert selected["record_kinds"] == {"unsupported_manual_pair_review": "declaration"}
        assert "custom.manual.review" in selected["event_kinds"]
        assert selected["expected_records"][0]["record_id"] == historical["record"]
        assert registry["adapter_origins"] == [{"owner_sha256": digest(str(external)), "adapter": "unresolved", "origin_owner_sha256": None}]
        # The generated shape is directly admissible as a conservative registry.
        reconciliation.validate_registry(registry, SimpleNamespace(inputs=[]), main_owner=main, observer_owner=engine.ledger.root.resolve())
        assert historical["source"] not in observed_artifacts
        saved = engine.ledger.get(result["discovery_record"], subject.RESULT)
        metadata = engine.ledger.artifacts.read(saved["snapshot_metadata_artifact"])
        assert metadata["study_record"] == registration["study_record"] and metadata["seed_record"] == registration["seed_record"]
        assert metadata["unchanged_snapshot_loader_verified"] and not metadata["source_owner_engine_created"]
        for field in ("owner_count", "root_count"):
            wrong = deepcopy(saved)
            wrong[field] += 1
            with pytest.raises(AuditError, match="retained_projection"):
                summary(result["discovery_record"], wrong, reused=True)
        get = engine.ledger.get
        with monkeypatch.context() as patch:
            patch.setattr(engine.ledger, "get", lambda ref, kind=None: {"content": {}} if ref == saved["protocol_record"] else get(ref, kind))
            with pytest.raises(AuditError, match="retained_registration"):
                call(engine, binding, "status")
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
    finally:
        engine.close()
    for path, contents in before.items():
        assert fixture.bytes_snapshot(Path(path)) == contents
    monkeypatch.setattr(subject.source_api.Source, "__init__", lambda *_: pytest.fail("Historical status must not reopen owners"))
    engine = subject.RootDiscovery(tmp_path / "discovery")
    try:
        again = call(engine, binding, "status")
        assert again["discovery_record"] == result["discovery_record"] and again["reused_historical_evidence"]
        assert not again["current_quiescence_claimed"]
        wrong = {**binding, "snapshot_binding": {**binding["snapshot_binding"], "snapshot_artifact": digest("foreign")}}
        with pytest.raises(AuditError, match="discovery_changed"):
            call(engine, wrong)
    finally:
        engine.close()


def test_live_validation_writer_blocks_before_any_root_cutoff_or_source_read(tmp_path):
    main, _, _, _, _, binding = actual_fixture(tmp_path)
    writer = Research(Path(binding["validation_owner"]), config=Config(offline=True))
    engine = subject.RootDiscovery(tmp_path / "discovery")
    try:
        with pytest.raises(AuditError, match="writer_present"):
            call(engine, binding)
        assert not engine._rows(subject.CUTOFF) and not engine._rows(subject.RESULT)
        assert engine._one(subject.INTENT)
    finally:
        engine.close()
        writer.close()
    assert main.exists()


def test_main_cutoff_drift_is_not_downgraded_to_unresolved_owner(tmp_path):
    main, _, _, _, _, binding = actual_fixture(tmp_path)
    writer = Research(main, config=Config(offline=True))
    try:
        writer.execute("status", {}, objective="Synthetic post-freeze drift", actor="test")
    finally:
        writer.close()
    engine = subject.RootDiscovery(tmp_path / "discovery")
    try:
        with pytest.raises(AuditError, match="main_final_cutoff_changed"):
            call(engine, binding)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["snapshot", "artifact"])
def test_foreign_snapshot_identity_fails_before_root_discovery(tmp_path, fault):
    _, _, _, _, _, binding = actual_fixture(tmp_path)
    binding["snapshot_binding"]["snapshot_record" if fault == "snapshot" else "snapshot_artifact"] = digest("wrong")
    engine = subject.RootDiscovery(tmp_path / "discovery")
    try:
        with pytest.raises(AuditError):
            call(engine, binding)
        assert len(engine._rows(subject.CUTOFF)) == 1 and not engine._rows(subject.RESULT)
    finally:
        engine.close()


def tiny_census():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE events(seq INTEGER, kind TEXT, payload TEXT, previous_hash TEXT, event_hash TEXT)")
    db.execute("CREATE TABLE records(id TEXT,kind TEXT,logical_key TEXT,payload TEXT,artifact TEXT,supersedes TEXT,created_event INTEGER)")
    db.execute("CREATE TABLE sources(id TEXT)")
    payload = canonical({"full_text": "PRIVATE CONTENT IS NOT PROJECTED"})
    artifact = hashlib.sha256(payload.encode()).hexdigest()
    identity = digest({"kind": "manual", "key": "logical", "payload": artifact, "supersedes": None})
    event = {"seq": 1, "kind": "record.created", "payload": {"record": identity, "kind": "manual", "artifact": artifact}, "previous_hash": "0" * 64}
    db.execute("INSERT INTO events VALUES(?,?,?,?,?)", (1, event["kind"], canonical(event["payload"]), event["previous_hash"], digest(event)))
    db.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)", (identity, "manual", "logical", payload, artifact, None, 1))
    db.execute("PRAGMA query_only=ON")
    return SimpleNamespace(db=db, owner=Path("C:/synthetic-owner").resolve(), _active=lambda: None,
        head=lambda: list(db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()))


@pytest.mark.parametrize("fault", [None, "event", "projection", "identity", "creation", "writable"])
def test_exact_metadata_chain_projection_and_no_content_projection(fault):
    source = tiny_census()
    try:
        if fault:
            source.db.execute("PRAGMA query_only=OFF")
            mutations = {"event": "UPDATE events SET event_hash='changed'", "projection": "UPDATE records SET payload='{}'",
                "identity": "UPDATE records SET id='wrong'", "creation": "UPDATE records SET created_event=2"}
            if fault in mutations:
                source.db.execute(mutations[fault])
                source.db.execute("PRAGMA query_only=ON")
            with pytest.raises(AuditError):
                subject.metadata_census(source)
        else:
            result = subject.metadata_census(source)
            assert result["metadata_chain_and_projection_verified"]
            assert not result["full_source_ledger_preflight_verified"] and not result["nested_artifact_integrity_verified"]
            assert "PRIVATE" not in canonical(result) and "logical" not in canonical(result["records"][0]["logical_key_sha256"])
    finally:
        source.db.close()


@pytest.mark.parametrize("name", ["../outside", "..", "a/b", "a\\b", "C:outside", ""])
def test_catalog_basename_cannot_expand_discovery_scope(tmp_path, name):
    catalog = {"roots": [{"id": "x", "selector": {"kind": "owner_basename_hint", "basename": name}}]}
    with pytest.raises(AuditError, match="literal_catalog_basename"):
        subject.candidates(catalog, tmp_path, tmp_path / "main")


def test_nested_snapshot_metadata_capability_rejects_arbitrary_artifact_or_record():
    source = tiny_census()
    view = subject.MetadataLedger(source, SimpleNamespace())
    try:
        with pytest.raises(AuditError, match="snapshot_nested_metadata_scope"):
            view.read_bytes(digest("private source"))
        row = source.db.execute("SELECT id FROM records").fetchone()[0]
        with pytest.raises(AuditError, match="snapshot_metadata_kind"):
            view.get(row)
    finally:
        source.db.close()


def test_snapshot_view_uses_actual_context_and_expires_with_source():
    engine = SimpleNamespace(config=Config(offline=True), _active={"actual-observer-session"})
    source = tiny_census()
    try:
        view = subject.SnapshotMetadataView(engine, source, subject.MetadataLedger(source, engine))
        assert view._active is engine._active
        def closed():
            raise AuditError("reader_closed")
        source._active = closed
        with pytest.raises(AuditError, match="reader_closed"):
            _ = view._active
        with pytest.raises(AuditError, match="reader_closed"):
            _ = view.ledger.db
    finally:
        source.db.close()


def test_cutoff_retry_cannot_silently_rebind_observed_head(tmp_path):
    class Bound(subject.RootDiscovery):
        @audited_handler
        def _status(self, session, context, data):
            self._cutoff(session, digest("intent"), tmp_path / "historical", [1, digest("first")])
            with pytest.raises(AuditError, match="cutoff_changed_requires_new_discovery"):
                self._cutoff(session, digest("intent"), tmp_path / "historical", [2, digest("second")])
            return {"checked": True}
    engine = Bound(tmp_path / "observer")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic cutoff binding", actor="test")["checked"]
    finally:
        engine.close()


def test_only_hints_become_candidates_linked_and_manual_roots_stay_unresolved(tmp_path):
    catalog = subject.closure._catalog()[1]
    result = subject.candidates(catalog, tmp_path, tmp_path / "main")
    assert len(result) == len(catalog["roots"]) == 35
    assert all(r["source_owner"] is None for r in result if r["root_id"] in {
        "event-pair-cross-window", "linked-manual-registry", "sealed-standard-source", "main-summary-diagnostics"})


def test_missing_root_and_manual_gaps_cannot_produce_empty_complete_registry(tmp_path):
    registry = subject.registry_for([], [{"root_id": "manual", "discovery_state": "unresolved_link_or_manual_root"}], tmp_path / "main", "test-proof")
    assert registry["owners"] == [] and registry["adapter_origins"] == []
    assert {r["reason_code"] for r in registry["declared_gaps"]} == {
        "study_history_scope_missing", "manual_review_scope_missing", "owner_scope_missing"}
