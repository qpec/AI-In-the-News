"""Temporary synthetic owners only; no production source or model/provider calls."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest, utc
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_history_inventory as adapter  # noqa: E402
import test_final_validation_source as fixtures  # noqa: E402


class HistoricalSource(Research):
    @audited_handler
    def _status(self, session, context, data):
        ids = []
        for number in range(data.get("attempts", 2)):
            request = self.ledger.artifacts.put({"input": "PRIVATE SYNTHETIC FULL ARTICLE", "ordinal": number})
            packet = self.ledger.artifacts.put({"request": request})
            dispatch = self.ledger.artifacts.put({"synthetic": True, "request": request})
            attempt = f"historical-{number}"
            self.ledger.append(session, "model.attempt.intended", {"attempt": attempt, "request": request,
                "dispatch": dispatch, "packet": packet, "batch": "synthetic-history", "reserved_nanousd": 1000})
            if number == 1 and not data.get("held_return"):
                continue
            raw = self.ledger.artifacts.put({"text": "PRIVATE SYNTHETIC MODEL RESPONSE", "valid": False})
            result = self.ledger.record(session, "historical_result", attempt, {"attempt": attempt,
                "response": raw, "parsed": None, "status": "unknown_held" if number == 1 else "invalid"})
            if number == 1:
                ids.append(result)
                continue
            self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "response": raw,
                "assessment": result, "status": "invalid"})
            derived = self.ledger.record(session, "historical_derived", result, {"source_result": result,
                "parsed": self.ledger.artifacts.put({"synthetic": "derived-not-new-provider-call"})})
            ids.extend((result, derived))
        detail = self.ledger.artifacts.put({"items": [{"evidence": self.ledger.artifacts.put_bytes(b"synthetic binary proof")}]})
        declared = self.ledger.record(session, "historical_declaration", "manual-review", {"details": detail,
            "explicit_manual_review": True, "missing_nested": digest("never-retained")})
        ids.append(declared)
        if data.get("unknown"):
            self.ledger.record(session, "unrecognized_review", "unknown", {"unknown": True})
            self.ledger.append(session, "model.future_observation", {"synthetic": True})
        self.ledger.artifacts.put_bytes(b"unreferenced synthetic content")
        return {"ids": ids}


def rule(origin, kind, *paths, required=True):
    return {"origin": origin, "kind": kind, "paths": list(paths), "required": required}


def historical(tmp_path, name, **data):
    owner = tmp_path / name
    writer = HistoricalSource(owner, config=Config(offline=True))
    try:
        result = writer.execute("status", data, objective="Synthetic historical store", actor="test")
        head = list(writer.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    return {"source_owner": str(owner), "source_head": head, "scope_input_sha256": None,
        "record_kinds": {"historical_result": "result", "historical_derived": "derived",
                         "historical_declaration": "declaration"},
        "event_kinds": [], "expected_records": [{"record_id": result["ids"][-1], "kind": "historical_declaration",
            "affected_input_sha256": None}], "required_artifacts": [],
        "artifact_rules": [rule("record", "historical_result", "/response"),
            rule("record", "historical_result", "/parsed", required=False),
            rule("record", "historical_derived", "/parsed"),
            rule("record", "historical_declaration", "/details", "/items/*/evidence")]}


class Observer(Research):
    callback = None
    escaped = None
    observe_fault = None

    @audited_handler
    def _status(self, session, context, data):
        binding = deepcopy(data["binding"])
        declaration = {"snapshot_binding": binding["snapshot_binding"], "owners_sha256": digest(binding["owners"]),
            "declared_gaps": binding["declared_gaps"], "scope": "explicit_recorded_study_sources_only",
            "universal_history_completeness_claimed": False}
        if data.get("fault") == "registry":
            declaration["owners_sha256"] = digest("wrong")
        binding["registry_declaration_artifact"] = self.ledger.artifacts.put(declaration)
        versions = {}
        for kind in ("protocol", "selection"):
            content = {"binding_sha256": digest(binding)}
            if kind == "protocol":
                content.update(method=adapter.METHOD, implementation=adapter.implementation())
            else:
                content["rules"] = "Explicit synthetic stores and scoped artifact traversal only."
            if data.get("fault") == kind:
                content["binding_sha256"] = digest("wrong")
            if data.get("fault") == "implementation" and kind == "protocol":
                content["implementation"] = {}
            versions[kind] = self._version(session, context, {"kind": kind, "key": "synthetic-history", "content": content})["id"]
        current = Context(context.objective, context.actor, versions)
        def observe(owner):
            proof = {"source_owner": str(owner), "observed_at": utc(), "inspection_complete": True,
                     "active_writers": [], "matching_processes": []}
            if self.observe_fault:
                proof.update(self.observe_fault)
            proof["evidence_sha256"] = self.ledger.artifacts.put(proof)
            return proof
        with adapter.open_history_inventory(self, session, current, binding, observe_liveness=observe) as reader:
            self.escaped = reader
            for item in reader.owners:
                assert item.source.db.execute("PRAGMA query_only").fetchone()[0] == 1
                with pytest.raises(sqlite3.OperationalError):
                    item.source.db.execute("CREATE TABLE forbidden_write(value TEXT)")
            if self.callback:
                self.callback(reader)
        return reader.result


def prepared(tmp_path, *, unknown=False):
    _, source_binding = fixtures.source_fixture(tmp_path)
    result, snapshot = fixtures.execute_observer(tmp_path, source_binding)
    binding = {"snapshot_binding": {"snapshot_record": result["snapshot_record"], "snapshot_artifact": result["snapshot_artifact"]},
        "owners": [historical(tmp_path, "history1", unknown=unknown), historical(tmp_path, "history2", attempts=0)],
        "declared_gaps": [], "registry_declaration_artifact": digest("placeholder")}
    return binding, snapshot


def run(tmp_path, binding, *, callback=None, fault=None, observe_fault=None):
    observer = Observer(tmp_path / "observer", config=Config(offline=True))
    observer.callback, observer.observe_fault = callback, observe_fault
    try:
        result = observer.execute("status", {"binding": binding, "fault": fault}, objective="Synthetic history inventory", actor="test")
        record = observer.ledger.get(result["inventory_record"], adapter.RESULT_KIND)
        return result, record, observer.escaped
    finally:
        observer.close()


def all_bytes(owner):
    return {str(path.relative_to(owner)): path.read_bytes() for path in Path(owner).rglob("*") if path.is_file()}


def test_two_reportless_owners_full_clone_preflight_exact_raw_census_and_scoped_lazy_access(tmp_path, monkeypatch):
    binding, _ = prepared(tmp_path)
    before = [all_bytes(row["source_owner"]) for row in binding["owners"]]
    verify = adapter.inventory.Ledger.verify
    clones = []
    def checked(facade):
        if isinstance(facade, adapter.inventory.SimpleNamespace):
            assert facade.db.execute("PRAGMA database_list").fetchone()[2] == ""
            clones.append(True)
        return verify(facade)
    monkeypatch.setattr(adapter.inventory.Ledger, "verify", checked)
    def inspect(reader):
        first, empty = reader.owners
        assert empty.census["physical_attempts"] == 0
        assert first.census["record_categories"] == {"result": 1, "derived": 1, "declaration": 1, "out_of_scope": 0}
        assert first.census["uncompleted_intents"] == 1
        assert {r["kind"] for r in first.events} >= adapter.ATTEMPT_EVENTS
        blobs = [first.artifacts[ref] for ref in first.artifacts]
        assert b"synthetic binary proof" in blobs
        assert any(b"PRIVATE SYNTHETIC FULL ARTICLE" in raw for raw in blobs)
        with pytest.raises(KeyError):
            first.artifacts[digest("outside-scope")]
    result, record, escaped = run(tmp_path, binding, callback=inspect)
    assert clones == [True, True]
    assert result["physical_attempts"] == 2 and result["completion_events"] == result["uncompleted_intents"] == 1
    assert result["coverage"]["declared_scope_complete"] and not result["coverage"]["prior_inventory_complete"]
    assert result["new_model_calls"] == result["source_mutations"] == 0
    assert "PRIVATE" not in canonical(result) and "history1" not in canonical(result)
    assert all(item["preflight"]["fts_integrity_write_location"] == "private_memory_clone" for item in record["owners"])
    assert before == [all_bytes(row["source_owner"]) for row in binding["owners"]]
    with pytest.raises(AuditError):
        escaped.owners[0].artifacts[next(iter(escaped.owners[0].artifacts.permitted))]


def test_unknown_records_model_events_and_missing_declared_scope_remain_global_unknown(tmp_path):
    binding, _ = prepared(tmp_path, unknown=True)
    binding["declared_gaps"] = [{"reason_code": "manual_review_scope_missing", "affected_input_sha256": None}]
    result, record, reader = run(tmp_path, binding)
    assert result["coverage"]["global_gap"] and not result["coverage"]["declared_scope_complete"]
    assert result["declared_gap_count"] == 3
    assert "unrecognized_review" in {r["kind"] for r in reader.owners[0].records}
    assert "model.future_observation" in {r["kind"] for r in reader.owners[0].events}
    assert record["owners"][0]["preflight"]["status"] == "verified"


def test_missing_nested_artifact_record_and_pointer_localize_to_exact_frozen_input(tmp_path):
    binding, snapshot = prepared(tmp_path)
    observer = Research(tmp_path / "observer", config=Config(offline=True))
    try:
        target = [observer.ledger.artifacts.read(snapshot["input_index_artifact"])[0]["input_sha256"]]
    finally:
        observer.close()
    scope = binding["owners"][0]
    scope["scope_input_sha256"] = target
    scope["artifact_rules"].extend([rule("record", "historical_declaration", "/missing_nested"),
                                    rule("record", "historical_declaration", "/not_a_field")])
    scope["expected_records"].append({"record_id": digest("absent-record"), "kind": "historical_declaration", "affected_input_sha256": target})
    result, _, _ = run(tmp_path, binding)
    assert result["declared_gap_count"] == 3
    assert result["coverage"]["unknown_input_sha256"] == target
    assert not result["coverage"]["global_gap"] and not result["coverage"]["declared_scope_complete"]


@pytest.mark.parametrize("fault", ["protocol", "selection", "implementation", "registry"])
def test_registered_scope_and_implementation_are_required(tmp_path, fault):
    binding, _ = prepared(tmp_path)
    with pytest.raises(AuditError, match="registered_|registry_declaration"):
        run(tmp_path, binding, fault=fault)


def test_verified_final_freeze_prerequisite_cannot_be_substituted(tmp_path):
    binding, _ = prepared(tmp_path)
    binding["snapshot_binding"]["snapshot_artifact"] = digest("wrong")
    with pytest.raises(AuditError, match="snapshot_identity"):
        run(tmp_path, binding)


@pytest.mark.parametrize("fault", ["unreferenced_artifact", "missing_request", "chain", "trigger"])
def test_full_ledger_integrity_failure_never_downgraded_to_missing_scope(tmp_path, fault):
    binding, _ = prepared(tmp_path)
    owner = Path(binding["owners"][0]["source_owner"])
    if fault == "unreferenced_artifact":
        import hashlib
        (owner / "objects" / hashlib.sha256(b"unreferenced synthetic content").hexdigest()).write_bytes(b"changed")
    else:
        db = sqlite3.connect(owner / "research.sqlite3", isolation_level=None)
        try:
            if fault == "missing_request":
                intent = json.loads(db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' LIMIT 1").fetchone()[0])
                (owner / "objects" / intent["request"]).unlink()
            elif fault == "trigger":
                db.execute("DROP TRIGGER immutable_records_delete")
            else:
                db.execute("DROP TRIGGER immutable_events_update")
                db.execute("UPDATE events SET time='corrupt' WHERE seq=1")
                db.execute("CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END")
        finally:
            db.close()
    with pytest.raises((AuditError, OSError)):
        run(tmp_path, binding)


def test_historical_writer_exclusion_and_actual_liveness_requirements(tmp_path):
    binding, _ = prepared(tmp_path)
    writer = Research(Path(binding["owners"][0]["source_owner"]), config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="writer_present"):
            run(tmp_path, binding)
    finally:
        writer.close()
    with pytest.raises(AuditError, match="source_not_quiescent"):
        run(tmp_path, binding, observe_fault={"matching_processes": [{"pid": 123}]})


@pytest.mark.parametrize("fault", ["head", "fresh_head", "consumer", "outside_scope"])
def test_cutoff_and_consumer_scope_cannot_drift(tmp_path, monkeypatch, fault):
    binding, _ = prepared(tmp_path)
    callback = None
    if fault == "head":
        binding["owners"][0]["source_head"][1] = digest("wrong")
    elif fault == "fresh_head":
        old = adapter.source_adapter.Source.head
        monkeypatch.setattr(adapter.source_adapter.Source, "head", lambda self, fresh=False:
            [1, digest("changed")] if fresh else old(self))
    elif fault == "consumer":
        def callback(reader):
            reader.owners[0].events.clear()
    else:
        binding["owners"][0]["scope_input_sha256"] = [digest("not-in-final-frame")]
    with pytest.raises(AuditError, match="cutoff_changed|changed_during|changed_by_consumer|not_in_final_frame"):
        run(tmp_path, binding, callback=callback)


def test_declared_out_of_scope_rows_and_missing_owner_gaps_are_retained_in_proof(tmp_path):
    binding, _ = prepared(tmp_path, unknown=True)
    binding["owners"][0]["record_kinds"]["unrecognized_review"] = "out_of_scope"
    binding["owners"][0]["event_kinds"] = ["model.future_observation"]
    binding["declared_gaps"] = [{"reason_code": "owner_scope_missing", "affected_input_sha256": None}]
    result, record, reader = run(tmp_path, binding)
    assert result["declared_gap_count"] == 1
    assert reader.owners[0].census["record_categories"]["out_of_scope"] == 1
    assert len(record["owners"][0]["census"]["out_of_scope_record_ids"]) == 1
    assert not result["coverage"]["prior_inventory_complete"]


def test_retained_held_response_without_completion_is_not_misnamed_unreturned(tmp_path):
    binding, _ = prepared(tmp_path)
    binding["owners"] = [historical(tmp_path, "held-history", held_return=True)]
    result, _, reader = run(tmp_path, binding)
    assert result["physical_attempts"] == 2 and result["uncompleted_intents"] == 1
    assert reader.owners[0].census["record_categories"]["result"] == 2
    assert "unreturned_intents" not in canonical(result)
    assert any(json.loads(row["payload"]).get("status") == "unknown_held" for row in reader.owners[0].records)


@pytest.mark.parametrize("mode", ["active", "changed"])
def test_main_final_owner_guard_required_even_when_not_in_historical_scope(tmp_path, mode):
    binding, snapshot = prepared(tmp_path)
    writer = Research(Path(snapshot["source_bindings"]["source_owner"]), config=Config(offline=True))
    try:
        if mode == "changed":
            writer.execute("status", {}, objective="Synthetic later operation", actor="test")
            writer.close()
        with pytest.raises(AuditError, match="writer_present|main_final_cutoff_changed"):
            run(tmp_path, binding)
    finally:
        writer.close()


def test_main_owner_included_uses_one_existing_guard_without_double_lock(tmp_path):
    binding, snapshot = prepared(tmp_path)
    binding["owners"].append({"source_owner": snapshot["source_bindings"]["source_owner"],
        "source_head": snapshot["source_bindings"]["source_head"], "scope_input_sha256": None,
        "record_kinds": {}, "event_kinds": [], "expected_records": [], "artifact_rules": [], "required_artifacts": []})
    result, record, _ = run(tmp_path, binding)
    assert result["owners"] == 3 and result["coverage"]["global_gap"]
    assert record["main_final_cutoff_guard"]["head_stable"]
    assert record["owners"][-1]["preflight"]["status"] == "verified"


def test_retained_committed_wal_is_read_from_private_copy_without_source_sidecar_changes(tmp_path):
    binding, _ = prepared(tmp_path)
    owner = Path(binding["owners"][1]["source_owner"])
    reader = sqlite3.connect(owner / "research.sqlite3", isolation_level=None)
    reader.execute("PRAGMA query_only=ON")
    reader.execute("BEGIN")
    prior_count = reader.execute("SELECT count(*) FROM events").fetchone()[0]
    writer = Research(owner, config=Config(offline=True))
    try:
        writer.execute("status", {}, objective="Synthetic WAL-only later event", actor="test")
        binding["owners"][1]["source_head"] = list(writer.ledger.db.execute(
            "SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        writer.close()
    try:
        assert (owner / "research.sqlite3-wal").stat().st_size > 0
        assert binding["owners"][1]["source_head"][0] > prior_count
        before = all_bytes(owner)
        result, record, _ = run(tmp_path, binding)
        assert result["full_declared_source_ledger_preflight_verified"]
        assert record["owners"][1]["preflight"]["events"] == binding["owners"][1]["source_head"][0]
        assert all_bytes(owner) == before
        assert not list((tmp_path / "observer").glob("validation-readonly-*"))
    finally:
        reader.close()


def test_required_null_artifact_is_a_missing_evidence_gap_not_a_semantic_result(tmp_path):
    binding, _ = prepared(tmp_path)
    binding["owners"][0]["artifact_rules"].append(rule("record", "historical_result", "/parsed"))
    result, _, _ = run(tmp_path, binding)
    assert result["declared_gap_count"] == 1 and result["coverage"]["global_gap"]
