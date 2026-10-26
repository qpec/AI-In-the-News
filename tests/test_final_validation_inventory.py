"""Synthetic Research workspaces; full read-only verification, no real articles/API."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest, utc
from newsresearch.runtime import Research, audited_handler

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_inventory as adapter  # noqa: E402
import final_validation_exposure as exposure  # noqa: E402
import dossier_contract_v5 as contract  # noqa: E402
from dossier_transport import Invocation  # noqa: E402
import test_final_validation_source as fixtures  # noqa: E402


class AttemptSource(fixtures.SourceFixture):
    @audited_handler
    def _status(self, session, context, data):
        original = self.ledger.record
        def record(active, kind, key, value, **kwargs):
            if data.get("pilot_selection") and kind == "cyber_dossier_execution_amendment_v6":
                manifest_id = self.ledger.db.execute("SELECT id FROM records WHERE kind='cyber_dossier_input_manifest'").fetchone()[0]
                manifest = self.ledger.get(manifest_id, "cyber_dossier_input_manifest")
                docs = [self.ledger.artifacts.read(row["document_artifact"])
                        for row in self.ledger.artifacts.read(manifest["documents_artifact"])][:2]
                snapshot = contract.build_evidence_card(docs, "planned", digest(sorted(d["document_id"] for d in docs)), count_tokens=len)
                packet = contract.card_quality_audit_request(docs, snapshot, count_tokens=len, max_tokens=96_000)
                selection = {"primary": [{"card_artifact": self.ledger.artifacts.put(snapshot), "luna_packet": None,
                    "astra_packet": self.ledger.artifacts.put(packet)}], "secondary": []}
                value = {**value, "pilot_selection_artifact": self.ledger.artifacts.put(selection)}
            if data.get("seed_plan") and kind == "cyber_dossier_execution_amendment_v7":
                manifest_row = self.ledger.db.execute("SELECT id FROM records WHERE kind='cyber_dossier_input_manifest'").fetchone()
                manifest = self.ledger.get(manifest_row[0], "cyber_dossier_input_manifest")
                documents = [self.ledger.artifacts.read(row["document_artifact"])
                             for row in self.ledger.artifacts.read(manifest["documents_artifact"])]
                packet = contract.seed_request(documents, count_tokens=len, max_tokens=96_000)
                entry = {"document_ids": packet["document_ids"], "state": "untouched_request_fits",
                         "packet_artifact": self.ledger.artifacts.put(packet)}
                value = {**value, "seed_packet_plan_artifact": self.ledger.artifacts.put([entry])}
            if kind == "cyber_dossier_report" and key == "final":
                self._synthetic_attempts(session, value, data)
            return original(active, kind, key, value, **kwargs)
        self.ledger.record = record
        try:
            result = super()._status(session, context, data)
        finally:
            self.ledger.record = original
        return result

    def _synthetic_attempts(self, session, report, data):
        plan = self.ledger.get(report["plan"], "cyber_dossier_plan")
        manifest = self.ledger.get(plan["input_manifest"], "cyber_dossier_input_manifest")
        metadata = self.ledger.artifacts.read(manifest["documents_artifact"])
        docs = [self.ledger.artifacts.read(row["document_artifact"]) for row in metadata]
        for number in range(3):
            packet = contract.seed_request(docs[number:number + 2], count_tokens=len, max_tokens=96_000)
            if number == 2:
                # Nonpair diagnostic lives in the same owner but must not enter C.
                request = {"model": "gpt-6-astra", "input": "SYNTHETIC_DIAGNOSTIC"}
                packet = {"kind": "responses", "phase": data.get("nonpair_phase", "summary_fidelity_audit"),
                          "request": request, "request_sha256": digest(request)}
                if data.get("nonpair_phase") == "embeddings":
                    import run_dossiers_v5
                    class SyntheticEncoder:
                        def encode(self, text, **kwargs):
                            return list(text.encode())
                    packet = run_dossiers_v5.embedding_packets(docs[2:], SyntheticEncoder())[0]
                    assert "request_sha256" not in packet
                if data.get("nonpair_phase") == "summary_faithfulness":
                    members = docs[2:]
                    claim = {"text": "Synthetic claim", "citations": [
                        {"document_id": doc["document_id"], "field": "title", "quote": doc["title"]} for doc in members]}
                    summary = {"dossier_id": "historical-summary", "membership_revision": digest(sorted(d["document_id"] for d in members)),
                        "source_document_ids": [d["document_id"] for d in members], "event_title": claim, "overview": claim,
                        "identity": {"scope": claim, "action": claim,
                            **{name: [] for name in contract.base.IDENTITY_FIELDS}, "unknowns": []}}
                    packet = contract.base.summary_faithfulness_request(members,
                        {"summary": summary, "summary_version": digest(summary)}, count_tokens=len, max_tokens=96_000)
                    packet["kind"] = "decisions"
            kind, request = packet["kind"], packet["request"]
            attempt = f"synthetic-attempt-{number}"
            intent = {"attempt": attempt, "task_key": digest([report["plan"], kind, request]), "number": 1,
                "batch": report["plan"], "execution_amendment": report["execution_amendment"],
                "packet": self.ledger.artifacts.put(packet), "request": self.ledger.artifacts.put(request),
                "dispatch": self.ledger.artifacts.put(Invocation(request, attempt, kind).manifest()),
                "phase": packet["phase"], "category": "main" if kind == "decisions" else "audit",
                "reserved_nanousd": 1000, "started_at": utc()}
            self.ledger.append(session, "model.attempt.intended", intent)
            if number == 1:
                continue  # Orphan intent remains durable and unknown.
            raw = {"provider": "synthetic", "model": request["model"], "payload": {"model": request["model"],
                "answers": [{"name": q["name"], "type": "choice"} for q in request.get("questions", [])]},
                "raw_response": {"http_status": 200, "dispatch_started": True}}
            response_ref = self.ledger.artifacts.put(raw)
            response = {"plan": report["plan"], **{k: intent[k] for k in (
                "attempt", "task_key", "phase", "category", "execution_amendment", "packet", "request")},
                "response": response_ref, "parsed": None, "cost_nanousd": 400, "reserved_nanousd": 0,
                "hold": False, "validation_error": "synthetic_invalid", "http_status": 200, "at": utc()}
            rid = self.ledger.record(session, "cyber_dossier_response", intent["task_key"], response)
            self.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "task_key": intent["task_key"],
                "response": response_ref, "assessment": rid, "status": "invalid"})
            if number == 0:
                derived = {"source_response_record": rid, "source_response_record_sha256": digest({**response, "_record_id": rid}),
                    "parent_plan": report["plan"], "parent_execution_amendment": report["execution_amendment"],
                    "task_key": intent["task_key"], "source_attempt": attempt,
                    **{"source_" + k: response[k] for k in ("packet", "request", "response")},
                    "source_validation_error": "synthetic_invalid", "status": "valid", "model_calls": 0,
                    "cost_nanousd": 0, "original_rows_unchanged": True,
                    "normalization_version": "seed-question-map-in-retained-request-list-order-v1",
                    "canonical_packet_sha256": intent["packet"], "request_sha256": intent["request"],
                    "parsed": self.ledger.artifacts.put({"status": "valid"})}
                self.ledger.record(session, "cyber_dossier_seed_revalidation", rid, derived)
        # An unreferenced binary object must still be checked by full preflight.
        self.ledger.artifacts.put_bytes(b"synthetic-unreferenced-binary")
        if data.get("prior_diagnostic"):
            self.ledger.record(session, "cyber_summary_fidelity_diagnostic_plan", "synthetic-prior-diagnostic", {
                "parent_plan": report["plan"], "tasks": [{"packet": intent["packet"], "task_key": intent["task_key"],
                    "selection": {"summary_version": digest("synthetic-summary")}}]})


class InventoryObserver(Research):
    callback = None
    escaped_reader = None

    @audited_handler
    def _status(self, session, context, data):
        binding = data["binding"]
        versions = {}
        for kind in ("protocol", "selection"):
            content = {"snapshot_binding_sha256": digest(binding)}
            if kind == "protocol":
                content.update(method=adapter.METHOD, implementation=adapter.implementation())
            else:
                content["rules"] = "Synthetic complete fixed-cutoff attempt census; no model calls."
            if data.get("registration_fault") == kind:
                content["snapshot_binding_sha256"] = digest("wrong")
            versions[kind] = self._version(session, context, {"kind": kind, "key": "synthetic-inventory", "content": content})["id"]
        registered = Context(context.objective, context.actor, versions)
        def observe(owner):
            proof = {"source_owner": str(owner), "observed_at": utc(), "inspection_complete": True,
                     "active_writers": [], "matching_processes": []}
            proof["evidence_sha256"] = self.ledger.artifacts.put(proof)
            return proof
        with adapter.open_attempt_inventory(self, session, registered, binding, observe_liveness=observe) as reader:
            self.escaped_reader = reader
            assert reader.source.db.execute("PRAGMA query_only").fetchone()[0] == 1
            with pytest.raises(sqlite3.OperationalError):
                reader.source.db.execute("CREATE TABLE forbidden_test(value TEXT)")
            arguments = reader.exposure_arguments()
            reconstructed = exposure.reconstruct_exposure(reader.index, **arguments)
            assert not reconstructed.projection.confirmed_pairs  # Default role unknown, never guessed.
            assert reconstructed.metadata["unclassified_pair_attempts"] == 2
            if self.callback:
                self.callback(reader)
        return reader.result


def prepared(tmp_path, **data):
    source = AttemptSource(tmp_path / "source", config=Config(offline=True))
    try:
        bindings = source.execute("status", data, objective="Synthetic source", actor="test")
        bindings["source_head"] = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    result, _ = fixtures.execute_observer(tmp_path, bindings)
    return bindings, {"snapshot_record": result["snapshot_record"], "snapshot_artifact": result["snapshot_artifact"]}


def run(tmp_path, binding, *, callback=None, fault=None):
    observer = InventoryObserver(tmp_path / "observer", config=Config(offline=True))
    observer.callback = callback
    try:
        result = observer.execute("status", {"binding": binding, "registration_fault": fault},
                                  objective="Synthetic inventory", actor="test")
        record = observer.ledger.get(result["inventory_record"], "cyber_final_validation_attempt_inventory")
        return result, record, observer.escaped_reader
    finally:
        observer.close()


def bytes_snapshot(owner):
    return {str(path.relative_to(owner)): path.read_bytes() for path in owner.rglob("*") if path.is_file()}


def test_full_clone_preflight_census_and_lazy_exposure_inputs_preserve_source_exactly(tmp_path, monkeypatch):
    bindings, binding = prepared(tmp_path)
    owner = Path(bindings["source_owner"])
    before = bytes_snapshot(owner)
    actual = adapter.Ledger.verify
    clones = []
    def verify(facade):
        if isinstance(facade, adapter.SimpleNamespace):
            assert facade.db.execute("PRAGMA database_list").fetchone()[2] == ""
            assert facade.db.execute("PRAGMA query_only").fetchone()[0] == 0
            assert isinstance(facade.artifacts, adapter._ReadOnlyArtifacts)
            clones.append(True)
        return actual(facade)
    monkeypatch.setattr(adapter.Ledger, "verify", verify)
    result, record, reader = run(tmp_path, binding)
    assert clones == [True]
    assert result["physical_attempts"] == 3 and result["response_records"] == 2
    assert result["orphan_intents"] == result["derived_records"] == result["excluded_nonpair_attempts"] == 1
    assert result["pair_attempts"] == 2 and result["unknown_task_semantics"] == 0
    assert result["main_owner_attempt_census_complete"] and result["full_source_ledger_preflight_verified"]
    assert not result["production_roles_reconciled"] and not result["candidate_exposure_resolved"]
    assert record["preflight"]["unresolved_model_attempts"] == ["synthetic-attempt-1"]
    assert record["preflight"]["fts_integrity_write_location"] == "private_memory_clone"
    assert "PRIVATE" not in canonical(result) and "Synthetic claim" not in canonical(result)
    assert result["new_model_calls"] == result["source_mutations"] == 0
    assert bytes_snapshot(owner) == before
    with pytest.raises(AuditError):
        reader.exposure_arguments()
    with pytest.raises(AuditError):
        reader.artifacts[next(iter(reader.artifacts.permitted))]


@pytest.mark.parametrize("fault", ["unreferenced_object", "chain", "trigger", "missing_orphan_packet", "fts_content"])
def test_full_preflight_detects_failures_outside_selected_final_snapshot(tmp_path, fault):
    bindings, binding = prepared(tmp_path)
    owner = Path(bindings["source_owner"])
    db = sqlite3.connect(owner / "research.sqlite3", isolation_level=None)
    try:
        if fault == "unreferenced_object":
            path = owner / "objects" / __import__("hashlib").sha256(b"synthetic-unreferenced-binary").hexdigest()
            path.write_bytes(b"tampered")
        elif fault == "chain":
            db.execute("DROP TRIGGER immutable_events_update")
            db.execute("UPDATE events SET time='tampered' WHERE seq=1")
            db.execute("CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only'); END")
        elif fault == "trigger":
            db.execute("DROP TRIGGER immutable_records_delete")
        elif fault == "missing_orphan_packet":
            events = [json.loads(row[0]) for row in db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'")]
            orphan = next(value for value in events if value["attempt"] == "synthetic-attempt-1")
            (owner / "objects" / orphan["packet"]).unlink()
        else:
            db.execute("INSERT INTO passage_fts(id,text) VALUES('extra','synthetic forged FTS')")
    finally:
        db.close()
    with pytest.raises((AuditError, OSError)):
        run(tmp_path, binding)


def test_unfamiliar_task_semantics_are_censused_and_leave_global_unknown_gap(tmp_path):
    _, binding = prepared(tmp_path, nonpair_phase="future_unknown_semantics")
    result, record, _ = run(tmp_path, binding)
    assert result["unknown_task_semantics"] == 1 and result["excluded_nonpair_attempts"] == 0
    observer = Research(tmp_path / "observer", config=Config(offline=True))
    try:
        certificate = observer.ledger.artifacts.read(record["pair_inventory_artifact"])
        assert certificate["complete"] is True
        assert certificate["gaps"] == [{"reason_code": "unrecognized_task_semantics", "document_ids": None}]
    finally:
        observer.close()


def test_historical_faithfulness_decisions_are_excluded_nonpair_without_changed_transport(tmp_path):
    _, binding = prepared(tmp_path, nonpair_phase="summary_faithfulness")
    result, record, _ = run(tmp_path, binding)
    assert result["excluded_nonpair_attempts"] == 1 and result["unknown_task_semantics"] == 0
    assert record["phase_counts"]["summary_faithfulness"] == 1


def test_frozen_embedding_packet_without_redundant_request_hash_is_exactly_bound(tmp_path):
    _, binding = prepared(tmp_path, nonpair_phase="embeddings")
    result, record, _ = run(tmp_path, binding)
    assert result["excluded_nonpair_attempts"] == 1 and result["unknown_task_semantics"] == 0
    assert record["phase_counts"]["embeddings"] == 1


def test_all_phase_metadata_and_bound_seed_plan_are_available_without_counting_prepared_calls(tmp_path):
    _, binding = prepared(tmp_path, seed_plan=True)
    def inspect(reader):
        assert len(reader.phase_records) == 6
        assert len(reader.phase_events) == 6
        for row, event in zip(reader.phase_records, reader.phase_events, strict=True):
            assert row["created_event"] == event["seq"]
            assert json.loads(event["payload"])["record"] == row["id"]
        assert len(reader.amendment_packet_plans) == 1
        plan = reader.amendment_packet_plans[0]
        entries = json.loads(reader.artifacts[plan["artifact"]])
        assert entries[0]["state"] == "untouched_request_fits"
        prepared_packet = json.loads(reader.artifacts[entries[0]["packet_artifact"]])
        assert len(prepared_packet["document_ids"]) == 4
        assert not any(json.loads(row["payload"]).get("packet") == entries[0]["packet_artifact"]
                       for row in reader.events if row["kind"] == "model.attempt.intended")
        for row in reader.phase_records:
            phase = json.loads(row["payload"])
            assert isinstance(json.loads(reader.artifacts[phase["artifact"]]), dict)
    result, record, _ = run(tmp_path, binding, callback=inspect)
    assert result["physical_attempts"] == 3 and result["pair_attempts"] == 2
    assert record["phase_records"] == 6 and record["amendment_packet_plans"] == 1


def test_ancestor_pilot_selection_and_nested_exact_packets_are_scoped_not_attempts(tmp_path):
    _, binding = prepared(tmp_path, pilot_selection=True)
    def inspect(reader):
        assert len(reader.pilot_selections) == 1
        selected = reader.pilot_selections[0]
        event = selected["creation_event"]
        assert json.loads(event["payload"])["record"] == selected["record_id"]
        values = json.loads(reader.artifacts[selected["artifact"]])
        assert len(values["primary"]) == 1 and len(selected["nested_artifacts"]) == 2
        for reference in selected["nested_artifacts"]:
            assert isinstance(json.loads(reader.artifacts[reference]), dict)
    result, _, _ = run(tmp_path, binding, callback=inspect)
    assert result["physical_attempts"] == 3


def test_same_owner_substantive_diagnostic_plans_are_exposed_by_exact_record_and_packet(tmp_path):
    _, binding = prepared(tmp_path, prior_diagnostic=True)
    def inspect(reader):
        assert len(reader.prior_diagnostics) == 1
        item = reader.prior_diagnostics[0]
        assert item["row"]["kind"] == "cyber_summary_fidelity_diagnostic_plan"
        assert json.loads(item["creation_event"]["payload"])["record"] == item["row"]["id"]
        assert json.loads(reader.artifacts[item["packet_artifacts"][0]])["phase"] == "summary_fidelity_audit"
    result, _, _ = run(tmp_path, binding, callback=inspect)
    assert result["physical_attempts"] == 3


@pytest.mark.parametrize("fault", ["protocol", "selection"])
def test_exact_registered_snapshot_binding_is_required(tmp_path, fault):
    _, binding = prepared(tmp_path)
    with pytest.raises(AuditError, match="registered_snapshot_binding"):
        run(tmp_path, binding, fault=fault)


def test_current_writer_and_changed_final_cutoff_block_inventory(tmp_path):
    bindings, binding = prepared(tmp_path)
    writer = Research(Path(bindings["source_owner"]), config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="writer_present"):
            run(tmp_path, binding)
        writer.execute("status", {}, objective="Synthetic later source operation", actor="test")
    finally:
        writer.close()
    with pytest.raises(AuditError, match="source_cutoff_changed"):
        run(tmp_path, binding)


def test_consumer_mutation_fails_and_no_inventory_result_is_committed(tmp_path):
    _, binding = prepared(tmp_path)
    def corrupt(reader):
        reader.certificate["complete"] = False
    with pytest.raises(AuditError, match="census_changed_by_consumer"):
        run(tmp_path, binding, callback=corrupt)
    observer = Research(tmp_path / "observer", config=Config(offline=True))
    try:
        assert observer.ledger.db.execute("SELECT count(*) FROM records WHERE kind='cyber_final_validation_attempt_inventory'").fetchone()[0] == 0
    finally:
        observer.close()


def test_artifact_scope_refuses_unrelated_owner_object_and_fresh_connection_catches_external_append(tmp_path):
    bindings, binding = prepared(tmp_path)
    def callback(reader):
        with pytest.raises(KeyError):
            reader.artifacts[__import__("hashlib").sha256(b"synthetic-unreferenced-binary").hexdigest()]
        # Simulate an actor bypassing OS writer cooperation; append changes the
        # fresh connection's head while the original reader snapshot stays fixed.
        db = sqlite3.connect(Path(bindings["source_owner"]) / "research.sqlite3", isolation_level=None)
        try:
            seq, last = bindings["source_head"]
            item = {"seq": seq + 1, "event_id": "outside", "session_id": "outside", "kind": "outside.append",
                    "time": utc(), "payload": {}, "previous_hash": last}
            db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?,?)", (
                item["seq"], item["event_id"], item["session_id"], item["kind"], item["time"], "{}", last, digest(item)))
        finally:
            db.close()
    with pytest.raises(AuditError, match="source_changed_during_inventory"):
        run(tmp_path, binding, callback=callback)


def test_reader_requires_active_research_boundary(tmp_path):
    _, binding = prepared(tmp_path)
    observer = InventoryObserver(tmp_path / "observer", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="active audited"):
            with adapter.open_attempt_inventory(observer, "inactive", Context("test", "test", {}), binding,
                                                observe_liveness=lambda _: None):
                pass
    finally:
        observer.close()
