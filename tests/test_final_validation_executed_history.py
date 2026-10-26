"""Compact executed-scope proof tests; no actual owners, models or old runs."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, canonical, digest
from newsresearch.runtime import audited_handler
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_executed_history as subject  # noqa: E402
import test_final_validation_compatible_native_reference as previous  # noqa: E402

native_fixture = previous.previous
probe = native_fixture.previous.subject
compact = native_fixture.previous.previous.compact


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    initialize = native_fixture.NativeSource.__init__
    def oversized_planning(engine, *args, **kwargs):
        initialize(engine, *args, **kwargs)
        put = engine.ledger.artifacts.put
        def keep_executed_fields(value):
            if isinstance(value, dict) and set(value) == {"tasks", "selected"}:
                value = {**value, "selected": [{"synthetic_unused_candidate_metadata": "x" * previous.subject.MAX_ARTIFACT}]}
            elif (isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict)
                    and value[0].get("status") == "prepared" and "dispatch_ref" in value[0]):
                value = [{**value[0], "prior_model_reference": {"synthetic_unused_old_metadata": "x" * previous.subject.MAX_ARTIFACT}}]
            return put(value)
        engine.ledger.artifacts.put = keep_executed_fields
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(native_fixture.NativeSource, "__init__", oversized_planning)
        native = previous.template.__wrapped__(tmp_path_factory, previous.code_bytes.__wrapped__())
    prepared = next(json.loads(r["payload"]) for r in native["records"] if r["id"] == native["prepared_result"])
    queue = next(json.loads(r["payload"]) for r in native["records"] if r["id"] == prepared["frozen_queue"])
    bulk = {queue["artifact"], prepared["exports"]["packets"]["artifact"]}
    assert all(len(native["objects"][ref]) > previous.subject.MAX_ARTIFACT for ref in bulk)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(probe, "CANDIDATE", native["candidate"])
        patch.setattr(probe.scope, "PAIR_RESULT", native["native_result"])
        patch.setattr(probe.ProbeObserver, "_capture", staticmethod(lambda: [compact.process()]))
        engine = previous.subject.CompatibleNativeReference(native["owner"])
        try:
            result = previous.execute(engine, {"projection_record": native["projection"]["reference_projection_record"],
                "projection_artifact": native["projection"]["reference_projection_artifact"]})
            assert result["observed_physical_intents"] == result["processed_attempts"] == 1
            assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 0
            assert result["gap_counts"]["native_artifact_byte_limit"] == 1
            value = engine.ledger.get(result["compatible_reference_record"], previous.subject.RESULT)
            saved = engine.ledger.artifacts.read(value["native_evidence_artifact"])
            compiled = engine.ledger.artifacts.read(value["proof_artifact"])
            assert not bulk.intersection(row["artifact"] for row in saved["artifacts"])
        finally:
            engine.close()
    return {**native, "bulk_refs": bulk, "compatible": result, "compatible_value": value,
        "compatible_saved": saved, "compatible_compiled": compiled}


@pytest.fixture
def case(tmp_path, template, monkeypatch):
    owner = tmp_path / "observer"
    prepare_root(owner)
    shutil.copytree(template["owner"], owner, dirs_exist_ok=True)
    monkeypatch.setattr(probe, "CANDIDATE", template["candidate"])
    monkeypatch.setattr(probe.scope, "PAIR_RESULT", template["native_result"])
    monkeypatch.setattr(probe.ProbeObserver, "_capture", staticmethod(lambda: [compact.process()]))
    return owner, template, {"compatible_record": template["compatible"]["compatible_reference_record"],
        "compatible_artifact": template["compatible"]["compatible_reference_artifact"]}


def execute(engine, selected, action="prove"):
    return engine.execute("status", {"action": action, **selected},
        objective="Synthetic bounded executed-history proof", actor="test")


def test_executed_requests_reuse_retained_bytes_without_reading_bulk_selection(case, monkeypatch):
    owner, native, selected = case
    before = compact.file_hashes(native["candidate"])
    old_refs = {row["artifact"] for saved in (native["compatible_saved"], native["saved"]) for row in saved["artifacts"]}
    reads = []
    source_read = probe.SOURCE.Source.artifact_bytes
    def missing_only(source, reference):
        assert reference not in native["bulk_refs"], "executed proof read an unneeded oversized selection artifact"
        assert reference not in old_refs, "executed proof refetched retained bytes"
        reads.append(reference)
        return source_read(source, reference)
    monkeypatch.setattr(probe.SOURCE.Source, "artifact_bytes", missing_only)
    engine = subject.ExecutedHistoryProof(owner)
    record, committed_under_lock = engine.ledger.record, []
    def locked_record(session, kind, key, value, *args, **kwargs):
        if kind == subject.RESULT:
            writer = None
            try:
                with pytest.raises(AuditError, match="concurrent research processes"):
                    writer = native_fixture.Research(native["candidate"], config=native_fixture.Config(offline=True))
                committed_under_lock.append(True)
            finally:
                if writer:
                    writer.close()
        return record(session, kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", locked_record)
    try:
        result = execute(engine, selected)
        assert committed_under_lock == [True]
        assert result["observed_physical_intents"] == result["processed_attempts"] == 1
        assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 1
        assert result["uncompleted_intents"] == result["primary_pair_blockers"] == 1
        assert result["gap_counts"] == {} and result["previous_gap_counts"]["native_artifact_byte_limit"] == 1
        assert result["retained_bytes_reused"] > 0
        assert len(reads) == len(set(reads))
        assert not set(reads).intersection(native["bulk_refs"] | old_refs)
        assert result["new_model_calls"] == 0 and not result["dispatch_authorized"]
        assert result["all_original_gaps_preserved"] and result["fresh_eligibility"] == "unknown"
        assert not result["whole_history_complete"] and not result["old_labels_reused"] and not result["sample_registered"]
        assert not result["selection_replayed"] and not result["bulk_queue_or_packet_bodies_read"]
        value = engine.ledger.get(result["executed_history_record"], subject.RESULT)
        assert value["source_head"] == native["compatible_value"]["source_head"]
        assert value["input_index_digest"] == native["index"].digest
        assert value["preserved_authority"] == native["compatible_value"]["preserved_authority"]
        assert value["preserved_authority"]["declared_gap_counts"] == {"manual_review_scope_missing": 1}
        assert engine.ledger.get(selected["compatible_record"], previous.subject.RESULT) == native["compatible_value"]
        compiled = engine.ledger.artifacts.read(value["proof_artifact"])
        evidence = value["evidence_projection"]
        assert evidence == subject.public_evidence(compiled, engine.ledger.artifacts.read(value["partition_artifact"]))
        assert {evidence["executed_derivation"][k] for k in ("queue_artifact", "packet_artifact")} == native["bulk_refs"]
        assert evidence["original_global_gaps_preserved"] and evidence["specifically_missing_references"] == []
        attempt = compiled["attempts"][0]
        old = native["compatible_compiled"]["attempts"][0]
        assert attempt["intended_event_hash"] == old["intended_event_hash"]
        assert attempt["original_attempt"] == old["original_attempt"] == "synthetic-native-orphan"
        assert attempt["joined_events"] == [] and attempt["physical_id"] == digest([str(native["candidate"]), old["original_attempt"]])
        assert attempt["label"] is None and not attempt["current_reference_compatible"]
        assert any(len(row["article_row_ids"]) == 2 for endpoint in attempt["endpoints"] for row in endpoint["final_inputs"])
        assert all(row["document_id"] in {i.document_id for i in native["index"].inputs}
            for endpoint in attempt["endpoints"] for row in endpoint["final_inputs"])
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        progress = json.loads((owner / "executed-history-progress.json").read_text(encoding="utf-8"))
        assert progress["method"] == subject.METHOD and progress["stage"] == "complete"
        assert "PRIVATE BODY" not in json.dumps(result)
        identifier = result["executed_history_record"]
    finally:
        engine.close()
    assert compact.file_hashes(native["candidate"]) == before
    monkeypatch.setattr(probe.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("cached proof reopened source"))
    monkeypatch.setattr(probe.ProbeObserver, "_capture", staticmethod(lambda: pytest.fail("cached proof observed source")))
    engine = subject.ExecutedHistoryProof(owner)
    try:
        repeated = execute(engine, selected, "status")
        assert repeated["executed_history_record"] == identifier and repeated["reused_completed"]
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()


@pytest.fixture
def memory(template, monkeypatch):
    monkeypatch.setattr(probe.scope, "PAIR_RESULT", template["native_result"])
    reader = previous.MemoryCompatible(template)
    read = reader.read
    def no_bulk(reference, reason):
        assert reference not in template["bulk_refs"], "compiler read bulk queue or packet content"
        return read(reference, reason)
    monkeypatch.setattr(reader, "read", no_bulk)
    try:
        yield reader, template
    finally:
        reader.source.db.close()


@pytest.mark.parametrize("fault", ["wrong_task", "request_body", "dispatch_stdin", "task_request", "after_intent", "wrong_session"])
def test_executed_scope_keeps_exact_wire_and_task_creation_guards(memory, monkeypatch, fault):
    reader, native = memory
    read, record = reader.read, reader.record
    intended = next(r for r in native["events"] if r["kind"] == "model.attempt.intended")
    def altered_read(reference, reason):
        value = deepcopy(read(reference, reason))
        if reason == "actual_intended_request" and fault == "wrong_task":
            value["task_kind"] = "luna_article_lead_screen"
        elif reason == "actual_intended_request" and fault == "request_body":
            value["articles"][0]["body"] += "changed full input"
        elif reason == "actual_intended_dispatch" and fault == "dispatch_stdin":
            value["stdin"] += "changed wire"
        return value
    def altered_record(identifier, kind):
        value = deepcopy(record(identifier, kind))
        if kind == subject.TASKS_KIND and fault == "task_request":
            value["items"][0]["request_hash"] = digest("different request")
        elif kind == subject.TASKS_KIND and fault == "after_intent":
            # Keep the real immutable record check; isolate the new chronology guard.
            reader.records[identifier]["created_event"] = intended["seq"]
        return value
    monkeypatch.setattr(reader, "read", altered_read)
    monkeypatch.setattr(reader, "record", altered_record)
    if fault == "wrong_session":
        tasks = next(r for r in native["records"] if r["kind"] == subject.TASKS_KIND)
        reader.record(tasks["id"], subject.TASKS_KIND)
        prepare_session = next(r["session_id"] for r in native["events"]
            if r["kind"] == "record.created" and r["seq"] == next(x["created_event"] for x in native["records"] if x["id"] == native["prepared_result"]))
        # After exact row/creation verification, isolate the session-selection join.
        reader.source.db.execute("UPDATE events SET session_id=? WHERE seq=?", (prepare_session, tasks["created_event"]))
    if fault == "request_body":
        compiled = subject.compile_executed(reader, native["index"], native["native_result"])
        attempt = compiled["attempts"][0]
        assert attempt["intended_event_hash"] == intended["event_hash"]
        assert attempt["original_attempt"] == json.loads(intended["payload"])["attempt"]
        assert attempt["endpoints"] == [] and not attempt["origin_verified"] and attempt["physical_id"] is None
        assert not attempt.get("request_and_dispatch_verified") and not attempt.get("native_request_generation_verified")
        assert attempt["gaps"] == [{"reason": "unsupported_or_incomplete_native_shape", "error_type": "ResearchError"}]
        partition = subject.projection.project_evidence(compiled, {"records": reader.records}, native["index"], native["native_value"]["binding"])
        assert any(r["affected_input_sha256"] is None for r in partition["unknown_regions"])
        print("malformed_request_observation=" + json.dumps({
            "original_attempt": attempt["original_attempt"], "intended_event_hash": attempt["intended_event_hash"],
            "endpoints": attempt["endpoints"], "gaps": attempt["gaps"], "physical_id": attempt["physical_id"],
            "origin_verified": attempt["origin_verified"], "generation_verified": bool(attempt.get("native_request_generation_verified")),
            "dispatch_verified": bool(attempt.get("request_and_dispatch_verified")),
            "unlocalized_unknown": any(r["affected_input_sha256"] is None for r in partition["unknown_regions"])}))
    elif fault == "wrong_session":
        compiled = subject.compile_executed(reader, native["index"], native["native_result"])
        assert not compiled["native_graph_verified"]
        assert any(g["reason"] == "unsupported_native_operation" for g in compiled["gaps"])
        assert len(compiled["attempts"]) == 1 and not compiled["attempts"][0].get("request_and_dispatch_verified")
    else:
        with pytest.raises(AuditError, match="executed_task_binding_before_attempt" if fault == "after_intent" else None):
            subject.compile_executed(reader, native["index"], native["native_result"])


@pytest.mark.parametrize("missing", ["request", "dispatch"])
def test_missing_executed_evidence_preserves_orphan_and_global_unknown(memory, missing):
    reader, native = memory
    intended = next(json.loads(r["payload"]) for r in native["events"] if r["kind"] == "model.attempt.intended")
    reader.objects = dict(reader.objects)
    del reader.objects[intended[missing]]
    compiled = subject.compile_executed(reader, native["index"], native["native_result"])
    assert compiled["matched_intents"] == len(compiled["attempts"]) == 1
    attempt = compiled["attempts"][0]
    assert attempt["original_attempt"] == intended["attempt"] and attempt["physical_id"] is None and attempt["label"] is None
    assert attempt["gaps"] == [{"reason": "native_artifact_absent", "reference": intended[missing]}]
    partition = subject.projection.project_evidence(compiled, {"records": reader.records}, native["index"], native["native_value"]["binding"])
    evidence = subject.public_evidence(compiled, partition)
    assert evidence["specifically_missing_references"] == [intended[missing]]
    assert any(r["affected_input_sha256"] is None for r in evidence["unknown_region_partitions"])
    assert evidence["original_global_gaps_preserved"] and evidence["fresh_eligibility"] == "unknown"


def test_foreign_looking_intent_linked_by_task_is_retained_as_unknown(template, monkeypatch):
    # Pure reconstructed rows exercise the census union; they grant no Source proof.
    data = {**template, "events": deepcopy(template["events"]), "metadata": deepcopy(template["metadata"])}
    row = next(r for r in data["events"] if r["kind"] == "model.attempt.intended")
    payload = {**json.loads(row["payload"]), "event_pair_study": "unknown-linked-study", "plan": digest("unknown linked plan")}
    row["payload"] = canonical(payload)
    row["event_hash"] = digest({**{k: v for k, v in row.items() if k != "event_hash"}, "payload": payload})
    data["metadata"]["events"] = [{k: r[k] for k in ("seq", "kind", "event_hash")} for r in data["events"]]
    monkeypatch.setattr(probe.scope, "PAIR_RESULT", template["native_result"])
    reader = previous.MemoryCompatible(data)
    read = reader.read
    def no_bulk(reference, reason):
        assert reference not in template["bulk_refs"]
        return read(reference, reason)
    monkeypatch.setattr(reader, "read", no_bulk)
    try:
        compiled = subject.compile_executed(reader, template["index"], template["native_result"])
        assert compiled["matched_intents"] == len(compiled["attempts"]) == 1
        attempt = compiled["attempts"][0]
        assert attempt["intended_event_hash"] == row["event_hash"] and attempt["original_attempt"] == payload["attempt"]
        assert attempt["gaps"] == [{"reason": "unsupported_linked_native_study", "reference": payload["plan"]}]
        assert not attempt["origin_verified"] and attempt["physical_id"] is None and attempt["label"] is None
        partition = subject.projection.project_evidence(compiled, {"records": reader.records}, template["index"], template["native_value"]["binding"])
        assert any(r["affected_input_sha256"] is None for r in partition["unknown_regions"])
    finally:
        reader.source.db.close()


@pytest.mark.parametrize("omitted", ["processed", "unprocessed"])
def test_executed_partition_cannot_drop_old_intents(omitted):
    processed, unprocessed = digest("old processed event"), digest("old unprocessed event")
    old = {"attempts": [{"intended_event_hash": processed}], "unprocessed_attempt_event_hashes": [unprocessed], "original_study_key": "old"}
    new = {"attempts": [] if omitted == "processed" else [{"intended_event_hash": processed}],
        "unprocessed_attempt_event_hashes": [] if omitted == "unprocessed" else [unprocessed], "original_study_key": "old"}
    engine = SimpleNamespace(ledger=SimpleNamespace(artifacts=SimpleNamespace(read=lambda *_: pytest.fail("omission reached projection"))))
    with pytest.raises(AuditError, match="executed_old_attempts_preserved"):
        subject.ExecutedHistoryProof._verify_partition(engine, {}, new, {}, old, None, {})


@pytest.mark.parametrize("field", ["compatible_record", "compatible_artifact"])
def test_foreign_compatible_result_rejected_before_source(case, monkeypatch, field):
    owner, _, selected = case
    selected[field] = digest("foreign parent")
    monkeypatch.setattr(probe.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("foreign parent opened source"))
    engine = subject.ExecutedHistoryProof(owner)
    try:
        with pytest.raises(AuditError, match="executed_selected_compatible"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_parent_completed_output_binding_is_required(case, monkeypatch):
    owner, _, selected = case
    engine = subject.ExecutedHistoryProof(owner)
    raw = engine._raw(selected["compatible_record"])
    session = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (raw["created_event"],)).fetchone()[0]
    completed = engine.ledger.db.execute("SELECT payload FROM events WHERE session_id=? AND kind='operation.completed'", (session,)).fetchone()[0]
    reference = json.loads(completed)["result"]
    read = engine.ledger.artifacts.read
    def wrong_output(ref):
        value = read(ref)
        return {**value, "compatible_reference_artifact": digest("foreign artifact")} if ref == reference else value
    monkeypatch.setattr(engine.ledger.artifacts, "read", wrong_output)
    monkeypatch.setattr(probe.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("uncompleted parent opened source"))
    try:
        with pytest.raises(AuditError, match="producer_output"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_source_head_drift_prevents_executed_result(case, monkeypatch):
    owner, _, selected = case
    head = probe.SOURCE.Source.head
    def changed(source, *, fresh=False):
        value = head(source, fresh=fresh)
        return [value[0] + 1, digest("different source head")] if fresh else value
    monkeypatch.setattr(probe.SOURCE.Source, "head", changed)
    engine = subject.ExecutedHistoryProof(owner)
    try:
        with pytest.raises(AuditError, match="source_head_changed"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("where", ["observer", "candidate"])
def test_stop_prevents_source_open(case, monkeypatch, where):
    owner, native, selected = case
    stop = (owner if where == "observer" else native["candidate"]) / "STOP"
    stop.write_text("synthetic stop", encoding="utf-8")
    monkeypatch.setattr(probe.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("STOP permitted source opening"))
    engine = subject.ExecutedHistoryProof(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()
        stop.unlink()


class OriginalPrefix(native_fixture.Research):
    """Tiny genuine ledger prefix, no actual call and no cross-window completion."""

    @audited_handler
    def _status(self, session, context, data):
        implementation = subject.preparation.links.base._hashes(subject.ORIGINAL_CODE)
        config = {"codex_executable": "C:/synthetic/codex.exe", "codex_model": "synthetic-native-model",
            "timeout_seconds": 180, "max_input_bytes": 500_000, "max_output_bytes": 2_000_000}
        approval = {"synthetic_only": True, "no_model_calls": True}
        content = {"protocol": {"method": subject.original.METHOD, "implementation": implementation},
            "policy": approval, "model_profile": config}
        versions = {kind: self._version(session, context, {"kind": kind, "key": "original-prefix",
            "content": value})["id"] for kind, value in content.items()}
        study = "synthetic-independent-original"
        plan = self.ledger.record(session, "event_pair_plan", study,
            {"study_key": study, "study_binding": digest("synthetic original study")})
        self.ledger.record(session, "event_pair_run_authorization", study, {"binding": {
            "plan": plan, "study_binding": digest("synthetic original study"),
            "implementation": implementation, "config": config, "versions": versions, "approval": approval}})
        # A known result locator does not assert a completed cross-window graph.
        root = self.ledger.record(session, subject.RESULT_KIND, probe.scope.PAIR_KEY,
            {"original_study_key": study, "manifest": digest("absent cross-window manifest")})
        return {"plan": plan, "root": root, "study": study, "versions": versions, "config": config}

    @audited_handler
    def _event_pair_experiment(self, session, context, data):
        plan = self.ledger.get(data["plan"], "event_pair_plan")
        authorization = self.ledger.db.execute("SELECT id FROM records WHERE kind='event_pair_run_authorization'").fetchone()[0]
        binding = self.ledger.get(authorization, "event_pair_run_authorization")["binding"]
        request, dispatch = native_fixture.request_and_dispatch(self.ledger.root, binding["versions"])
        sources = [a["source_version"] for a in request["articles"]]
        pair = digest(sorted(sources))
        request_ref, dispatch_ref = self.ledger.artifacts.put(request), self.ledger.artifacts.put(dispatch)
        task = digest({"plan": data["plan"], "request": request, "config": binding["config"], "method": subject.original.METHOD})
        batch = self.ledger.record(session, "codex_batch_manifest", task, {"plan": data["plan"],
            "versions": binding["versions"], "task_kind": "event_pair_identity", "event_pair_study": plan["study_key"],
            "items": [{"pair_id": pair, "task_key": task, "request_ref": request_ref, "dispatch_ref": dispatch_ref}]})
        self.ledger.append(session, "model.attempt.intended", {"attempt": "independent-original-orphan",
            "plan": data["plan"], "request": request_ref, "dispatch": dispatch_ref,
            "number": 1, "event_pair_retry": False, "reserved_pair_attempts": 1, "reserved_article_exposures": 2,
            "source_versions": sources, "event_pair_study": plan["study_key"], "pair_id": pair, "task_key": task, "batch": batch})
        return {"synthetic_no_model_calls": True}


def test_original_plan_orphan_is_proved_without_crosswindow_graph(tmp_path, template):
    candidate = tmp_path / "original-prefix"
    engine = OriginalPrefix(candidate, config=native_fixture.Config(offline=True))
    try:
        initialized = engine.execute("status", {}, objective="Synthetic independent original plan", actor="test")
    finally:
        engine.close()
    engine = OriginalPrefix(candidate, config=native_fixture.Config(offline=False))
    try:
        engine.execute("event_pair_experiment", {"plan": initialized["plan"]},
            objective="Synthetic durable original intent without a model call", actor="test")
        records = [dict(r) for r in engine.ledger.db.execute("SELECT * FROM records ORDER BY created_event")]
        events = [dict(r) for r in engine.ledger.db.execute("SELECT * FROM events ORDER BY seq")]
        objects = {p.name: p.read_bytes() for p in (candidate / "objects").iterdir() if p.is_file()}
        head = [events[-1]["seq"], events[-1]["event_hash"]]
    finally:
        engine.close()
    data = {"candidate": candidate, "records": records, "events": events, "objects": objects,
        "metadata": {"source_head": head, "records": [{"record_id": r["id"], "kind": r["kind"],
            "artifact": r["artifact"], "logical_key_sha256": digest(r["logical_key"]), "created_event": r["created_event"]} for r in records],
            "events": [{k: r[k] for k in ("seq", "kind", "event_hash")} for r in events]}}
    reader = previous.MemoryCompatible(data)
    try:
        compiled = subject.compile_executed(reader, template["index"], initialized["root"])
        assert not compiled["native_graph_verified"] and not compiled["native_scope_complete"]
        assert compiled["matched_intents"] == len(compiled["attempts"]) == 1
        attempt = compiled["attempts"][0]
        assert attempt["original_attempt"] == "independent-original-orphan" and attempt["joined_events"] == []
        assert attempt["request_and_dispatch_verified"] and attempt["origin_verified"] and attempt["gaps"] == []
        assert attempt["physical_id"] == digest([str(candidate), "independent-original-orphan"])
        assert attempt["label"] is None and not attempt["current_reference_compatible"]
        assert compiled["gaps"] and compiled["executed_derivation"] is None
    finally:
        reader.source.db.close()
