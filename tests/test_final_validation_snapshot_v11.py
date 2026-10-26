"""Real synthetic Research/Source boundaries; no actual source or model calls."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config, Context, digest
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_snapshot_v11 as subject  # noqa: E402
import final_validation_inventory_v11 as inventory  # noqa: E402
import final_validation_study as original  # noqa: E402
import test_final_validation_source_v11 as source_fixtures  # noqa: E402
from test_final_validation_inventory import AttemptSource, bytes_snapshot  # noqa: E402
from test_final_validation_study import payload, process  # noqa: E402


class CompleteSource(source_fixtures.SourceFixture):
    """Use the real V11 selected-proof fixture, with concrete nested artifacts."""
    _synthetic_attempts = AttemptSource._synthetic_attempts

    @audited_handler
    def _status(self, session, context, data):
        record = self.ledger.record
        def retain(active, kind, key, value, *args, **kwargs):
            if kind.startswith("cyber_dossier_execution_amendment") and "seed_packet_plan_artifact" in value:
                value["seed_packet_plan_artifact"] = self.ledger.artifacts.put([])
            if kind == "cyber_dossier_report" and key == "final" and not data.get("fault"):
                self._synthetic_attempts(session, value, data)
            return record(active, kind, key, value, *args, **kwargs)
        self.ledger.record = retain
        try:
            return super()._status(session, context, data)
        finally:
            self.ledger.record = record


class Consumer(subject.SnapshotParent):
    escaped = None
    callback = None

    def execute_inventory(self, selected, *, fault=None):
        return Research.execute(self, "status", {"inventory": selected, "fault": fault}, objective="Synthetic V11 inventory", actor="test")

    @audited_handler
    def _status(self, session, context, data):
        if "inventory" not in data:
            return super()._status(session, context, data)
        selected = data["inventory"]
        versions = {}
        for kind in ("protocol", "selection"):
            content = {"snapshot_binding_sha256": digest(selected)}
            if kind == "protocol":
                content.update(method=inventory.METHOD, implementation=inventory.implementation())
            else:
                content["rules"] = "Synthetic fixed-cutoff census; all unknown roles retained."
            if data.get("fault") == kind:
                content["snapshot_binding_sha256"] = digest("wrong")
            versions[kind] = self._version(session, context, {"kind": kind, "key": "synthetic-inventory", "content": content})["id"]
        with inventory.open_attempt_inventory(self, session, Context(context.objective, context.actor, versions), selected,
                observe_liveness=lambda owner: self.observer.observe(self, session, owner)) as reader:
            self.escaped = reader
            assert reader.source.db.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError):
                reader.source.db.execute("CREATE TABLE forbidden_test(x TEXT)")
            assert reader.artifacts[reader.certificate["evidence_sha256"]]
            if self.callback:
                self.callback(reader)
        return reader.result


@pytest.fixture(autouse=True)
def no_process_probe(monkeypatch):
    monkeypatch.setattr(original.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def source(tmp_path, **kwargs):
    engine = CompleteSource(tmp_path / "source", config=Config(offline=True))
    try:
        bindings = engine.execute("status", kwargs, objective="Synthetic final source", actor="test")
        bindings["source_head"] = list(engine.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        engine.close()
    return Path(bindings["source_owner"]), bindings


def initialized(tmp_path, **kwargs):
    owner, bindings = source(tmp_path, **kwargs)
    engine = original.Study(tmp_path / "validation", source_owner=owner)
    try:
        result = engine.execute("status", payload(), objective="Synthetic original Study", actor="test")
    finally:
        engine.close()
    return owner, subject.binding(result["study_record"], result["seed_record"], bindings), result


def execute(engine, value, action="freeze"):
    return engine.execute("status", {"action": action, "binding": value}, objective="Synthetic V11 snapshot", actor="test")


def selected(result):
    return {key: result[key] for key in ("snapshot_record", "snapshot_artifact")}


def test_original_registration_seeds_distinct_snapshot_full_clone_and_inventory(tmp_path, monkeypatch):
    owner, value, registration = initialized(tmp_path, audit_unavailable=True)
    before = bytes_snapshot(owner)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        seeds = engine.ledger.get(registration["seed_record"], original.SEEDS)
        baseline = original.implementation()
        assert digest(baseline) == "bfade8355b2d1cc9729f26108cff6dd21dd4b11f7ed55737a3e7304f4ae66f45"
        monkeypatch.setattr(original.secrets, "token_hex", lambda *_: pytest.fail("seeds rerolled"))
        first = execute(engine, value)
        assert first["source_frozen"] and first["full_source_ledger_preflight_verified"]
        assert first["pipeline_finished"] and first["export_verified"]
        assert not first["final_audit_complete"] and first["final_audit_unavailable"] == 1
        assert (first["unique_documents"], first["article_rows"], first["alias_rows"]) == (4, 5, 1)
        assert first["accepted_inputs"] == first["singleton_prediction_inputs"] == 2
        assert first["current_source_quiescence_verified"] and not first["dispatch_authorized"]
        assert not first["original_snapshot_created"] and not engine._rows(original.SNAPSHOT)
        assert not any(engine._rows(k) for k in (original.FREEZE, original.ACCESS))
        proof = engine._one(subject.compatibility.RESULT_KIND)
        assert engine._one(original.SEEDS)["created_event"] < engine._one(subject.FREEZE)["created_event"] < engine._one(subject.ACCESS)["created_event"] < proof["created_event"]
        actual = engine.execute_inventory(selected(first))
        assert actual["physical_attempts"] == 3 and actual["response_records"] == 2
        assert actual["orphan_intents"] == actual["derived_records"] == actual["excluded_nonpair_attempts"] == 1
        assert actual["pair_attempts"] == 2 and actual["main_owner_attempt_census_complete"]
        assert not actual["production_roles_reconciled"] and not actual["prior_inventory_complete"]
        assert not actual["candidate_exposure_resolved"]
        assert engine.escaped.result == actual
        with pytest.raises(AuditError):
            len(engine.escaped.artifacts)
        assert engine.ledger.get(registration["seed_record"], original.SEEDS) == seeds
        assert original.implementation() == baseline
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert "PRIVATE BODY" not in json.dumps([first, actual])
        assert engine.ledger.verify()["status"] == "verified"
    finally:
        engine.close()
    assert bytes_snapshot(owner) == before
    reopened = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        monkeypatch.setattr(original.WindowsProcessObserver, "_capture", staticmethod(lambda: pytest.fail("historical reuse is not fresh observation")))
        again = execute(reopened, value)
        assert selected(again) == selected(first) and again["reused_frozen_cutoff"]
        assert not again["current_source_quiescence_verified"]
        assert execute(reopened, value, "status") == again
    finally:
        reopened.close()


@pytest.mark.parametrize("field", ["study_record", "seed_record", "source_head", "expected_documents", "amendments"])
def test_original_authority_or_source_binding_change_fails_closed(tmp_path, field):
    owner, value, _ = initialized(tmp_path)
    changed = deepcopy(value)
    if field in {"study_record", "seed_record"}:
        changed[field] = digest("wrong")
    elif field == "source_head":
        changed["source_bindings"][field][1] = digest("wrong")
    elif field == "expected_documents":
        changed["source_bindings"][field] += 1
    else:
        changed["source_bindings"][field][-1]["kind"] = "cyber_dossier_execution_amendment_v10"
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        with pytest.raises((AuditError, ValueError)):
            execute(engine, changed)
        assert not engine._rows(subject.SNAPSHOT)
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["processing_incomplete", "pipeline_unfinished", "audit_unfinished", "literal_text", "alias_request", "export", "competing_v10"])
def test_no_weaker_final_freeze_or_input_predicate(tmp_path, fault):
    owner, value, _ = initialized(tmp_path, fault=fault)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        with pytest.raises((AuditError, ValueError)):
            execute(engine, value)
        assert not engine._rows(subject.SNAPSHOT)
    finally:
        engine.close()


@pytest.mark.parametrize("kind", [original.FREEZE, original.ACCESS, original.SNAPSHOT])
def test_original_freeze_path_cannot_coexist(tmp_path, kind):
    owner, value, _ = initialized(tmp_path)
    class Conflict(Consumer):
        @audited_handler
        def _status(self, session, context, data):
            self.ledger.record(session, kind, "synthetic-conflict", {})
            return super()._status(session, context, data)
    engine = Conflict(tmp_path / "validation", source_owner=owner)
    try:
        with pytest.raises(AuditError, match="original_freeze_coexists"):
            execute(engine, value)
    finally:
        engine.close()


def test_unreferenced_corruption_rejected_by_full_preflight_not_selected_proof(tmp_path):
    owner, value, _ = initialized(tmp_path)
    # Existing fixture deliberately retains this unrelated binary: complete
    # preflight must verify it even though the selected source proof does not.
    import hashlib
    reference = hashlib.sha256(b"synthetic-unreferenced-binary").hexdigest()
    object_path = next(path for path in (owner / "objects").rglob("*") if path.is_file() and path.name == reference)
    object_path.write_bytes(b"corrupt")
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, value)
        assert engine._rows(subject.compatibility.RESULT_KIND) and not engine._rows(subject.SNAPSHOT)
    finally:
        engine.close()


def test_interrupted_proof_can_resume_same_binding_without_seed_or_proof_replacement(tmp_path, monkeypatch):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    preflight = subject.inventory._full_preflight
    try:
        monkeypatch.setattr(subject.inventory, "_full_preflight", lambda *_: (_ for _ in ()).throw(AuditError("synthetic_interruption")))
        with pytest.raises(AuditError, match="synthetic_interruption"):
            execute(engine, value)
        proof = engine._one(subject.compatibility.RESULT_KIND)["id"]
        assert not engine._rows(subject.SNAPSHOT)
        monkeypatch.setattr(subject.inventory, "_full_preflight", preflight)
        complete = execute(engine, value)
        assert complete["source_frozen"] and engine._one(subject.compatibility.RESULT_KIND)["id"] == proof
        assert len(engine._rows(original.SEEDS)) == 1
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["protocol", "selection", "proof_only", "digest"])
def test_inventory_requires_new_parent_authority_and_registration(tmp_path, fault):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        result = execute(engine, value)
        chosen = selected(result)
        if fault == "proof_only":
            row = engine._one(subject.compatibility.RESULT_KIND)
            chosen = {"snapshot_record": row["id"], "snapshot_artifact": digest(row["payload"])}
        elif fault == "digest":
            chosen["snapshot_artifact"] = digest("wrong")
        with pytest.raises(AuditError):
            engine.execute_inventory(chosen, fault=fault)
        assert not engine._rows(inventory.RESULT_KIND)
    finally:
        engine.close()


def test_inventory_mutation_does_not_record_complete_census(tmp_path):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        result = execute(engine, value)
        engine.callback = lambda reader: reader.counts.update(physical_attempts=0)
        with pytest.raises(AuditError, match="census_changed_by_consumer"):
            engine.execute_inventory(selected(result))
        assert not engine._rows(inventory.RESULT_KIND)
    finally:
        engine.close()


def test_parent_requires_concrete_observer_and_has_no_initialize_route(tmp_path):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        engine.observer = object()
        with pytest.raises(AuditError, match="concrete_process_observer_required"):
            execute(engine, value)
        with pytest.raises(AuditError, match="entry_shape"):
            engine.execute("status", payload(), objective="synthetic", actor="test")
    finally:
        engine.close()


@pytest.mark.parametrize("action", ["amend", "report"])
def test_admin_python_writer_blocks_snapshot_even_without_run_subcommand(tmp_path, monkeypatch, action):
    owner, value, _ = initialized(tmp_path)
    rows = [process(), process(777777, command=f'"C:/Python/python.exe" run_dossiers_v11.py {action} --workspace "{owner}"')]
    monkeypatch.setattr(original.WindowsProcessObserver, "_capture", staticmethod(lambda: rows))
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        with pytest.raises(AuditError, match="source_not_quiescent"):
            execute(engine, value)
        assert not engine._rows(subject.SNAPSHOT)
    finally:
        engine.close()


def test_changed_completed_cutoff_rejected_without_new_source_read(tmp_path, monkeypatch):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    try:
        first = execute(engine, value)
        changed = deepcopy(value)
        changed["source_bindings"]["source_head"][1] = digest("new-head")
        monkeypatch.setattr(original.WindowsProcessObserver, "_capture", staticmethod(lambda: pytest.fail("must reject before inspection")))
        with pytest.raises(AuditError, match="cutoff_changed_requires_amendment"):
            execute(engine, changed)
        assert engine._one(subject.SNAPSHOT)["id"] == first["snapshot_record"]
    finally:
        engine.close()


def test_same_source_lock_held_through_durable_snapshot_and_summary_verification(tmp_path, monkeypatch):
    owner, value, _ = initialized(tmp_path)
    engine = Consumer(tmp_path / "validation", source_owner=owner)
    saved_record = engine.ledger.record
    saved_summary = engine._summary_v11
    checked = []
    def assert_locked(stage):
        with pytest.raises(AuditError, match="already open"):
            Research(owner, config=Config(offline=True))
        checked.append(stage)
    def record(session, kind, key, payload, *args, **kwargs):
        if kind in {subject.PREFLIGHT, subject.SNAPSHOT}:
            assert_locked(kind)
        return saved_record(session, kind, key, payload, *args, **kwargs)
    def summary(session, row, *, reused):
        assert not reused
        assert_locked("summary")
        return saved_summary(session, row, reused=reused)
    monkeypatch.setattr(engine.ledger, "record", record)
    monkeypatch.setattr(engine, "_summary_v11", summary)
    try:
        assert execute(engine, value)["source_frozen"]
        assert checked == [subject.PREFLIGHT, subject.SNAPSHOT, "summary"]
    finally:
        engine.close()
    # Lock ownership does end after the complete audited snapshot operation.
    reopened = Research(owner, config=Config(offline=True))
    reopened.close()
