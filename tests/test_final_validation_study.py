"""Real synthetic Research owners; process enumeration mocked, no model calls."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_study as subject  # noqa: E402
from test_final_validation_source import source_fixture, source_bytes  # noqa: E402


def process(pid=None, *, parent=0, command='"C:/Python/python.exe" validation_driver.py', created="2026-10-24T01:00:00+00:00"):
    return {"pid": os.getpid() if pid is None else pid, "parent_pid": parent, "name": "python.exe",
        "created_at": created, "command_line": command}


@pytest.fixture(autouse=True)
def no_real_process_probes(monkeypatch):
    monkeypatch.setattr(subject.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def evidence():
    return {"instruction": "SYNTHETIC user instruction: validate full-source pair precision and recall with Codex.",
        "source_reference": "synthetic-transcript:event-1", "source_timestamp": "2026-10-23T20:09:21+00:00"}


def payload():
    return {"action": "initialize", "instruction_evidence": evidence(),
        "configuration": subject.configuration(expected_documents=4, expected_articles=5, expected_aliases=1)}


def run(study, data):
    return study.execute("status", data, objective="Synthetic offline validation registration", actor="test:synthetic")


def test_audited_initialize_precedes_source_freeze_and_reopen_reuses_seeds_and_exact_cutoff(tmp_path, monkeypatch):
    owner, bindings = source_fixture(tmp_path, audit_unavailable=True)
    before = source_bytes(owner)
    workspace = tmp_path / "validation"
    values = payload()
    calls = []
    original = subject.source.Source.__init__
    def entered(reader, engine, session, selected):
        assert engine._one(subject.SEEDS)["created_event"] < engine._one(subject.ACCESS)["created_event"]
        assert engine._one(subject.STUDY)["created_event"] < engine._one(subject.ACCESS)["created_event"]
        calls.append(str(selected))
        original(reader, engine, session, selected)
    monkeypatch.setattr(subject.source.Source, "__init__", entered)
    with_study = subject.Study(workspace, source_owner=owner)
    try:
        initial = run(with_study, values)
        assert calls == [] and not initial["source_frozen"]
        seed_record = with_study.ledger.get(initial["seed_record"], subject.SEEDS)
        sampling = with_study.ledger.artifacts.read(initial["schedule_seed_artifact"])
        ordering = with_study.ledger.artifacts.read(initial["article_order_seed_artifact"])
        assert len(set([*sampling["seeds"].values(), ordering["seed"]])) == 4
        assert seed_record["generator"] == subject.SEED_GENERATOR
        assert not initial["dispatch_authorized"] and not initial["sample_drawn"]
        assert "SYNTHETIC user instruction" not in json.dumps(initial)
        monkeypatch.setattr(subject.secrets, "token_hex", lambda _n: pytest.fail("randomness rerolled"))
        assert run(with_study, values) == initial
        frozen = run(with_study, {"action": "freeze", "source_bindings": bindings})
        assert len(calls) == 1 and frozen["pipeline_finished"] and frozen["export_verified"]
        assert not frozen["final_audit_complete"] and frozen["final_audit_unavailable"] == 1
        assert frozen["unique_documents"] == 4 and frozen["article_rows"] == 5 and frozen["alias_rows"] == 1
        assert frozen["current_source_quiescence_verified"] and not frozen["reused_frozen_cutoff"]
        assert not frozen["population_accuracy_measured"] and not frozen["dispatch_authorized"]
        assert not with_study.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert with_study.ledger.verify()["status"] == "verified"
    finally:
        with_study.close()
    reopened = subject.Study(workspace, source_owner=owner)
    try:
        again = run(reopened, values)
        assert again["seed_record"] == initial["seed_record"] and again["study_record"] == initial["study_record"]
        reused = run(reopened, {"action": "freeze", "source_bindings": bindings})
        assert reused["snapshot_record"] == frozen["snapshot_record"] and reused["reused_frozen_cutoff"]
        assert not reused["current_source_quiescence_verified"] and len(calls) == 1
        assert run(reopened, {"action": "status"})["source_frozen"]
    finally:
        reopened.close()
    assert source_bytes(owner) == before


@pytest.mark.parametrize("fault", ["same", "nested", "parent", "relative", "online"])
def test_source_or_unsafe_owner_refused_before_ledger_construction(tmp_path, fault):
    owner = tmp_path / "source-not-created"
    destination, source, config = tmp_path / "validation-not-created", owner, Config(offline=True)
    if fault == "same":
        destination = owner
    elif fault == "nested":
        destination = owner / "validation"
    elif fault == "parent":
        destination = tmp_path
    elif fault == "relative":
        source = Path("relative-source")
    else:
        config = Config(offline=False)
    with pytest.raises(AuditError):
        subject.Study(destination, source_owner=source, config=config)
    assert not owner.exists() and not (destination / "research.sqlite3").exists()


@pytest.mark.parametrize("fault", ["instruction", "frame", "policy", "code", "source_owner"])
def test_changed_initialization_requires_explicit_amendment_without_new_seeds(tmp_path, monkeypatch, fault):
    owner, values = tmp_path / "source", payload()
    study = subject.Study(tmp_path / "validation", source_owner=owner)
    try:
        initial = run(study, values)
        changed = deepcopy(values)
        if fault == "instruction":
            changed["instruction_evidence"]["instruction"] += " Changed authority."
        elif fault == "frame":
            changed["configuration"] = subject.configuration(expected_documents=5, expected_articles=6, expected_aliases=1)
        elif fault == "policy":
            changed["configuration"]["model_dispatch_authorized"] = True
        elif fault == "code":
            old = subject.implementation()
            monkeypatch.setattr(subject, "implementation", lambda: old | {"changed": digest("new code")})
        else:
            study.source_owner = tmp_path / "another-source"
        monkeypatch.setattr(subject.secrets, "token_hex", lambda _n: pytest.fail("randomness rerolled"))
        with pytest.raises(AuditError):
            run(study, changed)
        assert study._one(subject.SEEDS)["id"] == initial["seed_record"]
        assert len(study._rows(subject.STUDY)) == 1 and not owner.exists()
    finally:
        study.close()


@pytest.mark.parametrize("stage", ["seed_record", "study_record"])
def test_interrupted_initialization_never_regenerates_or_silently_resumes(tmp_path, monkeypatch, stage):
    workspace, owner, values = tmp_path / "validation", tmp_path / "source", payload()
    study = subject.Study(workspace, source_owner=owner)
    kind = subject.SEEDS if stage == "seed_record" else subject.STUDY
    original = study.ledger.record
    def fail(session, record_kind, *args, **kwargs):
        if record_kind == kind:
            raise AuditError("synthetic durable boundary failure")
        return original(session, record_kind, *args, **kwargs)
    monkeypatch.setattr(study.ledger, "record", fail)
    try:
        with pytest.raises(AuditError, match="synthetic durable"):
            run(study, values)
        assert study._rows(subject.INTENT) and not study._rows(subject.STUDY)
    finally:
        study.close()
    reopened = subject.Study(workspace, source_owner=owner)
    try:
        monkeypatch.setattr(subject.secrets, "token_hex", lambda _n: pytest.fail("randomness rerolled"))
        with pytest.raises(AuditError, match="incomplete_initialization_requires_explicit_recovery"):
            run(reopened, values)
        with pytest.raises(AuditError):
            run(reopened, {"action": "freeze", "source_bindings": {}})
        assert run(reopened, {"action": "status"})["incomplete_initialization"]
    finally:
        reopened.close()
    assert not owner.exists()


def test_preexisting_research_and_inherited_operations_cannot_initialize_or_dispatch(tmp_path):
    workspace = tmp_path / "validation"
    old = Research(workspace, config=Config(offline=True))
    try:
        old.execute("version", {"kind": "note", "key": "prior-source-inspection", "content": {"seen": "synthetic"}},
            objective="Synthetic previous work", actor="test")
    finally:
        old.close()
    study = subject.Study(workspace, source_owner=tmp_path / "source")
    try:
        with pytest.raises(AuditError, match="owner_has_prior_research"):
            run(study, payload())
        for operation in ("batch", "version", "ingest"):
            with pytest.raises(AuditError, match="offline_entry_operations_only"):
                study.execute(operation, {}, objective="Synthetic forbidden operation", actor="test")
        with pytest.raises(AuditError, match="operation_shape"):
            run(study, {"action": "run"})
        assert not study._rows(subject.SEEDS)
    finally:
        study.close()


def test_mutable_reporting_spec_does_not_replace_retained_method_or_invalidate_status(tmp_path, monkeypatch):
    spec = tmp_path / "synthetic-spec.md"
    spec.write_text("Synthetic prospective method version A", encoding="utf-8")
    monkeypatch.setattr(subject, "SPEC", spec)
    values = payload()
    study = subject.Study(tmp_path / "validation", source_owner=tmp_path / "source")
    try:
        initial = run(study, values)
        spec.write_text("Updated mutable reporting prose", encoding="utf-8")
        assert run(study, {"action": "status"}) == initial
        assert run(study, values) == initial
        assert study.ledger.artifacts.read_bytes(initial["specification_artifact"]) == b"Synthetic prospective method version A"
        with pytest.raises(AuditError, match="initialization_changed_requires_amendment"):
            run(study, payload())
    finally:
        study.close()


def test_specification_snapshot_reads_once_even_if_reporting_file_changes_during_registration(tmp_path, monkeypatch):
    spec = tmp_path / "synthetic-spec.md"
    spec.write_bytes(b"Exact prospectively bound method")
    monkeypatch.setattr(subject, "SPEC", spec)
    values = payload()
    study = subject.Study(tmp_path / "validation", source_owner=tmp_path / "source")
    original = study.ledger.artifacts.put
    def put(value):
        if value == values["instruction_evidence"]:
            spec.write_bytes(b"A later reporting edit")
        return original(value)
    monkeypatch.setattr(study.ledger.artifacts, "put", put)
    try:
        result = run(study, values)
        assert study.ledger.artifacts.read_bytes(result["specification_artifact"]) == b"Exact prospectively bound method"
        assert run(study, {"action": "status"}) == result
    finally:
        study.close()


@pytest.mark.parametrize("fault", ["active_writer", "missing_command", "missing_self", "observer_failure", "writer_ancestor"])
def test_os_process_or_inspection_failures_block_source_read_and_exact_retry_keeps_seed(tmp_path, monkeypatch, fault):
    owner, bindings = source_fixture(tmp_path)
    before = source_bytes(owner)
    study = subject.Study(tmp_path / "validation", source_owner=owner)
    writer = process(900001, command=f'python run_dossiers_v9.py report --workspace "{owner}"')
    rows = [process(), writer]
    if fault == "missing_command":
        rows[1]["command_line"] = None
    elif fault == "missing_self":
        rows = []
    elif fault == "writer_ancestor":
        rows[0]["parent_pid"] = writer["pid"]
    def capture():
        if fault == "observer_failure":
            raise AuditError("synthetic observer unavailable")
        return rows
    monkeypatch.setattr(subject.WindowsProcessObserver, "_capture", staticmethod(capture))
    try:
        initial = run(study, payload())
        with pytest.raises(AuditError):
            run(study, {"action": "freeze", "source_bindings": bindings})
        assert not study._rows(subject.SNAPSHOT)
        assert source_bytes(owner) == before
        monkeypatch.setattr(subject.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
        result = run(study, {"action": "freeze", "source_bindings": bindings})
        assert result["pipeline_finished"] and study._one(subject.SEEDS)["id"] == initial["seed_record"]
        assert len(study._rows(subject.ACCESS)) == 1 and len(study._rows(subject.FREEZE)) == 1
    finally:
        study.close()


def test_verified_venv_observer_wrapper_is_exempt_but_changed_args_are_not(tmp_path, monkeypatch):
    owner, bindings = source_fixture(tmp_path)
    study = subject.Study(tmp_path / "validation", source_owner=owner)
    tail = f'validation_driver.py --source-owner "{owner}"'
    rows = [process(parent=900002, command='"C:/Python/python.exe" ' + tail, created="2026-10-24T01:00:01+00:00"),
        process(900002, command='"C:/repo/.venv/Scripts/python.exe" ' + tail)]
    monkeypatch.setattr(subject.WindowsProcessObserver, "_capture", staticmethod(lambda: rows))
    try:
        run(study, payload())
        result = run(study, {"action": "freeze", "source_bindings": bindings})
        assert result["pipeline_finished"]
        observation = study._rows("cyber_final_validation_process_observation")[-1]["payload"]
        proof = study.ledger.artifacts.read(observation["inventory_artifact"])
        assert set(proof["verified_observer_process_ids"]) == {os.getpid(), 900002}
        assert not proof["raw_command_lines_retained"] and all("command_line" not in row for row in proof["processes"])
    finally:
        study.close()
    other = subject.Study(tmp_path / "other-validation", source_owner=owner)
    rows[1]["command_line"] += " --different-task"
    try:
        run(other, payload())
        with pytest.raises(AuditError, match="source_not_quiescent"):
            run(other, {"action": "freeze", "source_bindings": bindings})
    finally:
        other.close()


@pytest.mark.parametrize("fault", ["processing_incomplete", "pipeline_unfinished", "export"])
def test_incomplete_or_changed_final_outputs_never_commit_a_snapshot(tmp_path, fault):
    owner, bindings = source_fixture(tmp_path, fault=fault)
    study = subject.Study(tmp_path / "validation", source_owner=owner)
    try:
        run(study, payload())
        with pytest.raises(AuditError):
            run(study, {"action": "freeze", "source_bindings": bindings})
        assert not study._rows(subject.SNAPSHOT)
        assert not run(study, {"action": "status"})["source_frozen"]
    finally:
        study.close()


def test_changed_cutoff_is_not_silently_refrozen_after_failure_or_success(tmp_path, monkeypatch):
    owner, bindings = source_fixture(tmp_path)
    study = subject.Study(tmp_path / "validation", source_owner=owner)
    try:
        run(study, payload())
        monkeypatch.setattr(subject.WindowsProcessObserver, "_capture", staticmethod(lambda: []))
        with pytest.raises(AuditError):
            run(study, {"action": "freeze", "source_bindings": bindings})
        changed = deepcopy(bindings)
        changed["report"] = digest("another-final-report")
        with pytest.raises(AuditError, match="source_cutoff_changed_requires_amendment"):
            run(study, {"action": "freeze", "source_bindings": changed})
        assert len(study._rows(subject.FREEZE)) == 1
    finally:
        study.close()
