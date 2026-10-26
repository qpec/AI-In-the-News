"""Exact metadata projection tests; temporary synthetic ledgers only."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.runtime import Research

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_main_metadata as subject  # noqa: E402
import test_final_validation_exposure as exposure  # noqa: E402
import test_final_validation_history_closure as upstream  # noqa: E402
from test_dossier_seed_v7_diagnostic import packet_and_reply  # noqa: E402


def prepare(source, disposition="possible_pair_reference_bounded"):
    oid = digest("synthetic-main")
    head = [len(source.events), source.events[-1]["event_hash"] if source.events else digest("empty")]
    owner = {"scope": {"source_owner": "synthetic-main", "source_head": head},
        "events": deepcopy(source.events), "records": deepcopy(source.records), "full_census_artifact": digest("full-census")}
    rows = []
    for event in source.events:
        value = subject.raw(event)
        if event["kind"] == "model.attempt.intended":
            response = next((r["id"] for r in source.records if r["kind"] == "cyber_dossier_response"
                and subject.raw(r)["attempt"] == value["attempt"]), None)
            rows.append({"original_attempt": value["attempt"], "task_key": value["task_key"],
                "response_record": response, "disposition": disposition})
    def gap(reason, identity):
        return {"reason_code": reason, "owner_sha256": oid, "evidence_sha256": digest(identity),
            "affected_input_sha256": None, "role": None}
    gaps = [gap("unclassified_full_record", r["id"]) for r in owner["records"]]
    gaps += [gap("unclassified_full_event", e["event_hash"]) for e in owner["events"]]
    gaps += [gap("unresolved_catalog_root", "root"), gap("unsupported_task_purpose", "intent")]
    base = {"input_index_digest": digest("index"), "pair_role_blockers": [{"pair_key": digest("old-pair"), "role": "primary"}],
        "unresolved_regions": gaps, "owner_partitions": {oid: {"source_head": head,
            "full_census_artifact": owner["full_census_artifact"],
            "records": [{"record_id": r["id"], "disposition": "unclassified"} for r in owner["records"]],
            "events": [{"event_hash": e["event_hash"], "disposition": "unclassified"} for e in owner["events"]]}},
        "physical_tasks": [{"original_attempt": r["original_attempt"], "disposition": disposition} for r in rows],
        "prepared_only": [], "resolved_task_purpose_gaps": [], "root_dispositions": [],
        "scoped_certificate": {"complete": False, "global_gap": True, "unknown_input_sha256": [], "universal_completeness": False},
        "counts": {"unresolved_regions": len(gaps), "global_regions": len(gaps)}}
    return [oid, owner, rows, {"plan": source.plan}, base, lambda ref: json.loads(source.artifacts[ref])]


def run(source, **kwargs):
    return subject._derive(*prepare(source), **kwargs)


def completed(source, *, status="invalid"):
    row = source.last_response
    value = subject.raw(row)
    return source.event("model.attempt.completed", {"attempt": value["attempt"], "status": status,
        "assessment": row["id"], "response": value["response"], "ended_at": "2026-10-24T00:01:00Z"})


@pytest.mark.parametrize("state", ["ack", "opaque", "predispatch"])
def test_response_projection_does_not_change_task_purpose_or_liability(state):
    source = exposure.Census()
    source.attempt(state=state)
    args = prepare(source)
    before = deepcopy(args[:5])
    derived, proof = subject._derive(*args)
    assert source.last_response["id"] in proof["proved_records"]
    assert proof["proved_records"][source.last_response["id"]]["evidence"]["semantic_correctness_inferred"] is False
    assert derived["pair_role_blockers"] == args[4]["pair_role_blockers"]
    assert derived["physical_tasks"] == args[4]["physical_tasks"]
    assert derived["scoped_certificate"]["global_gap"]
    assert [g for g in derived["unresolved_regions"] if g["reason_code"] == "unsupported_task_purpose"]
    assert before == args[:5]


@pytest.mark.parametrize("fault", ["extra", "packet", "task", "plan", "hold_type", "cost_type", "timestamp", "optional", "missing_response", "missing_parsed"])
def test_malformed_or_unavailable_response_projection_is_not_exempted(fault):
    source = exposure.Census()
    source.attempt()
    row = source.last_response
    value = subject.raw(row)
    if fault == "extra":
        value["manual_review"] = "private additional judgment"
    elif fault in {"packet", "plan"}:
        value[fault] = digest("wrong")
    elif fault == "task":
        value["task_key"] = digest("wrong")
    elif fault == "hold_type":
        value["hold"] = 0
    elif fault == "cost_type":
        value["cost_nanousd"] = True
    elif fault == "timestamp":
        value["at"] = "2026-10-24"
    elif fault == "optional":
        value["diagnostic_plan"] = digest("unbound")
    elif fault == "missing_response":
        del source.artifacts[value["response"]]
    else:
        value["parsed"] = digest("not-retained")
    row["payload"] = canonical(value)
    _, proof = run(source)
    assert row["id"] not in proof["proved_records"]
    assert proof["remaining_metadata_counts"]["records_by_kind"] == {"cyber_dossier_response": 1}


def test_artifact_integrity_failure_is_not_downgraded_to_missing():
    source = exposure.Census()
    source.attempt()
    args = prepare(source)
    def corrupt(ref):
        raise AuditError("Artifact integrity failure")
    args[-1] = corrupt
    with pytest.raises(AuditError, match="Artifact integrity failure"):
        subject._derive(*args)


@pytest.mark.parametrize("fault", [None, "hold", "status", "assessment", "response", "duplicate", "extra"])
def test_completion_is_only_exact_single_native_response_projection(fault):
    source = exposure.Census()
    source.attempt(state="opaque" if fault == "hold" else "ack")
    event = completed(source)
    value = subject.raw(event)
    if fault in {"assessment", "response"}:
        value[fault] = digest("wrong")
    elif fault == "status":
        value["status"] = "valid"
    elif fault == "extra":
        value["manual"] = "new observation"
    elif fault == "duplicate":
        source.event("model.attempt.completed", value)
    event["payload"] = canonical(value)
    _, proof = run(source)
    assert (event["event_hash"] in proof["proved_events"]) is (fault is None)


def version_session(source, *, operation="version", failed=False):
    code = {k.replace("\\", "/"): v for k, v in subject.v8.implementation().items() if k.replace("\\", "/") in {
        "src/newsresearch/runtime.py", "src/newsresearch/storage.py", "src/newsresearch/common.py"}}
    identity = source.put({"code_files": code, "code_digest": digest(code)})
    header = source.event("session.started", {"context": {"objective": "Synthetic metadata", "actor": "test", "versions": {}},
        "identity": identity, "configuration": {"offline": True}, "preflight": {"status": "verified"},
        "actor_assurance": "self-asserted local operator"})
    request = {"kind": "note", "key": "a", "content": {"private": "arbitrary manual review remains unknown"}}
    intended = source.event("operation.intended", {"operation": operation, "input": source.put(request)})
    if failed:
        return header, intended, source.event("operation.failed", {"operation": operation, "error_type": "AuditError"}), None
    row = source.record("note", "a", {"content": request["content"], "registered_by": "test", "reason": None, "branch": "main"})
    response = source.event("operation.completed", {"operation": operation, "result": source.put({"id": row["id"], "kind": "note"})})
    end = source.event("session.ended", {"status": "completed"})
    return header, intended, response, end


def test_exact_version_output_can_duplicate_input_without_clearing_manual_input():
    source = exposure.Census()
    header, intended, response, end = version_session(source)
    derived, proof = run(source)
    assert set(proof["proved_events"]) == {e["event_hash"] for e in (header, response, end)}
    assert source.records[0]["id"] in proof["proved_records"]
    assert any(g["evidence_sha256"] == digest(intended["event_hash"]) for g in derived["unresolved_regions"])
    assert derived["scoped_certificate"]["global_gap"]


@pytest.mark.parametrize("fault", ["generic_status", "missing_identity", "wrong_core", "missing_input", "missing_result", "changed_record", "wrong_order", "extra_operation"])
def test_lifecycle_proof_never_uses_operation_name_or_missing_payload_as_exemption(fault):
    source = exposure.Census()
    header, intended, response, end = version_session(source, operation="status" if fault == "generic_status" else "version")
    if fault == "missing_identity":
        del source.artifacts[subject.raw(header)["identity"]]
    elif fault == "wrong_core":
        value = subject.raw(header)
        code = {"src/newsresearch/runtime.py": digest("wrong")}
        value["identity"] = source.put({"code_files": code, "code_digest": digest(code)})
        header["payload"] = canonical(value)
    elif fault == "missing_input":
        del source.artifacts[subject.raw(intended)["input"]]
    elif fault == "missing_result":
        del source.artifacts[subject.raw(response)["result"]]
    elif fault == "changed_record":
        value = subject.raw(source.records[0])
        value["content"]["private"] = "different review"
        source.records[0]["payload"] = canonical(value)
    elif fault == "wrong_order":
        response["seq"] = intended["seq"] - 1
    else:
        if fault == "extra_operation":
            source.event("operation.intended", subject.raw(intended))
    derived, proof = run(source)
    assert intended["event_hash"] not in proof["proved_events"]
    assert response["event_hash"] not in proof["proved_events"]
    assert not proof["proved_records"]
    assert derived["scoped_certificate"]["global_gap"]


def test_failed_operation_shell_does_not_erase_input_or_manufacture_session_end():
    source = exposure.Census()
    header, intended, failed, _ = version_session(source, operation="status", failed=True)
    derived, proof = run(source)
    assert set(proof["proved_events"]) == {header["event_hash"], failed["event_hash"]}
    assert any(g["evidence_sha256"] == digest(intended["event_hash"]) for g in derived["unresolved_regions"])


@pytest.mark.parametrize("fault", [None, "extra", "unbound_amendment", "changed_card", "bool_calls"])
def test_exact_card_rebuild_requires_full_literal_sources_and_bound_amendment(fault):
    source = exposure.Census()
    documents = exposure.docs(2)
    card = subject.roots.closure.batch.task.main.prior.v5.build_evidence_card(documents, "g", digest(["d0", "d1"]), count_tokens=len, max_tokens=32000)
    value = {"dossier_id": "g", "membership_revision": card["membership_revision"], "card_version": card["card_version"],
        "document_ids": ["d0", "d1"], "artifact": source.put(card), "execution_amendment": source.amendment, "model_generation_calls": 0}
    if fault == "extra":
        value["manual"] = "separate review"
    elif fault == "unbound_amendment":
        value["execution_amendment"] = digest("other")
    elif fault == "changed_card":
        card["manual_review"] = "unrequested extra"
        value["artifact"] = source.put(card)
    elif fault == "bool_calls":
        value["model_generation_calls"] = False
    row = source.record("cyber_dossier_evidence_card", digest(["g", card["membership_revision"]]), value)
    _, proof = run(source, documents={d["document_id"]: d for d in documents}, count_tokens=len, amendments={source.amendment: {}})
    assert (row["id"] in proof["proved_records"]) is (fault is None)


def test_exact_embedding_phase_replay_does_not_clear_other_phase_report_or_plan():
    source = exposure.Census()
    phase = source.record("cyber_dossier_phase", "embeddings", {"name": "embeddings", "artifact": digest("verified"), "plan": source.plan})
    for kind in ("cyber_dossier_phase", "cyber_dossier_report", "cyber_dossier_plan", "manual_pair_review"):
        source.record(kind, "unsupported", {"artifact": digest("arbitrary")})
    _, proof = run(source, embedding_phase=phase)
    assert list(proof["proved_records"]) == [phase["id"]]
    assert proof["remaining_metadata_counts"]["records_by_kind"] == {
        "cyber_dossier_phase": 1, "cyber_dossier_plan": 1, "cyber_dossier_report": 1, "manual_pair_review": 1}


@pytest.mark.parametrize("fault", [None, "wrong_derived_list", "new_output"])
def test_v8_revalidation_replays_actual_immutable_question_order_fix(monkeypatch, fault):
    source = exposure.Census()
    packet, payload = packet_and_reply(8)
    source.amendment = subject.v8.PARENT_AMENDMENT
    source.attempt(packet, mutate_envelope=lambda e: e.update(payload=payload),
        mutate_response=lambda r: r.update(validation_error=subject.v8.ERROR, reserved_nanousd=0))
    original_row = source.last_response
    original = {**subject.raw(original_row), "_record_id": original_row["id"]}
    normalized, parsed = subject.v8.revalidate_retained(original, packet,
        json.loads(source.artifacts[original["response"]]), packet["request"])
    protocol = digest("protocol")
    value = {"method": subject.v8.METHOD, "versions": {"protocol": protocol}, "parent_plan": source.plan,
        "parent_execution_amendment": subject.v8.PARENT_AMENDMENT, "source_response_record": original_row["id"],
        "source_response_record_sha256": digest(original), "task_key": original["task_key"], "source_attempt": original["attempt"],
        **{"source_" + k: original[k] for k in ("packet", "request", "response")},
        "source_validation_error": subject.v8.ERROR, "normalization_version": subject.v8.NORMALIZATION,
        "canonical_packet_sha256": digest(normalized), "request_sha256": packet["request_sha256"],
        "parsed": source.put(parsed), "status": "valid", "model_calls": 0, "cost_nanousd": 0,
        "original_rows_unchanged": True, "at": "2026-10-24T00:03:00Z"}
    if fault == "new_output":
        parsed["manual_extra"] = "unsupported new judgment"
        value["parsed"] = source.put(parsed)
    derived = source.record("cyber_dossier_seed_revalidation", original_row["id"], value)
    amendment = {"method": subject.v8.METHOD, "versions": {"protocol": protocol},
        "derived_revalidation_records": [] if fault == "wrong_derived_list" else [derived["id"]]}
    monkeypatch.setattr(subject.v8, "SOURCE_RESPONSES", (original_row["id"],))
    before = deepcopy(source.artifacts)
    _, proof = run(source, amendments={digest("v8"): amendment})
    assert (derived["id"] in proof["proved_records"]) is (fault is None)
    assert source.artifacts == before


def test_wrong_owner_gap_same_hash_and_other_reason_are_never_removed():
    source = exposure.Census()
    source.attempt()
    args = prepare(source)
    matching = next(g for g in args[4]["unresolved_regions"] if g["reason_code"] == "unclassified_full_record")
    extras = [{**matching, "owner_sha256": digest("other-owner")}, {**matching, "reason_code": "manual_review_scope_missing"}]
    args[4]["unresolved_regions"] += extras
    derived, proof = subject._derive(*args)
    assert matching in proof["discharged_metadata_gaps"]
    assert all(g in derived["unresolved_regions"] for g in extras)


def test_changed_head_and_incomplete_task_partition_fail_closed():
    source = exposure.Census()
    source.attempt()
    args = prepare(source)
    args[1]["scope"]["source_head"] = [1, digest("other")]
    with pytest.raises(AuditError, match="same_main_cutoff"):
        subject._derive(*args)
    args = prepare(source)
    args[2] = []
    with pytest.raises(AuditError, match="complete_existing_task_partition"):
        subject._derive(*args)


def test_actual_completed_chain_resolve_reopen_only_retained_artifacts(tmp_path, monkeypatch):
    f = upstream.fixture
    monkeypatch.setattr(subject.roots.closure.batch.task.parent.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: [f.prior.fixture.process()]))
    main, observer, selected, declaration = f.prepared(tmp_path, copies=True)
    batch, batch_value = f.run(main, observer, selected, declaration)
    lookup, _ = f.run(main, observer, selected, declaration, "lookup")
    engine = subject.roots.closure.HistoryClosureParent(observer, source_owner=main)
    try:
        closed = upstream.call(engine, {"action": "compile", "batch_history_record": batch["batch_history_record"],
            "pair_lookup_record": lookup["pair_lookup_record"]})
    finally:
        engine.close()
    engine = subject.lifecycle.LifecycleParent(observer, source_owner=main)
    try:
        life = engine.execute("status", {"action": "collect", "task_census_record": batch_value["binding"]["task_census_record"]},
            objective="Synthetic exact lifecycle supplement", actor="test")
    finally:
        engine.close()
    before = f.prior.fixture.source_bytes(main)
    engine = subject.supplement.NativeArtifactParent(observer, source_owner=main)
    try:
        actual_verify = subject.supplement._verify_value
        def adversarial_checks(current, value, inputs):
            assert value["reference_count"] > 0
            with pytest.raises(AuditError):
                Research(main, config=Config(offline=True))
            for field in ("reference_count", "gap_count"):
                wrong = deepcopy(value)
                wrong[field] += 1
                with pytest.raises(AuditError, match="exact_reference_manifest"):
                    actual_verify(current, wrong, inputs)
            wrong = deepcopy(value)
            wrong["binding"]["source_head"][1] = digest("foreign")
            with pytest.raises(AuditError, match="result_binding"):
                actual_verify(current, wrong, inputs)
            wrong = deepcopy(value)
            refs = current.ledger.artifacts.read(value["references_artifact"])
            altered = deepcopy(refs)
            altered[0]["artifact"] = current.ledger.artifacts.put({"foreign": "not part of fixed native scope"})
            wrong["references_artifact"] = current.ledger.artifacts.put(altered)
            with pytest.raises(AuditError, match="exact_reference_manifest"):
                actual_verify(current, wrong, inputs)
            read_bytes = current.ledger.artifacts.read_bytes
            def changed(ref):
                if ref == refs[0]["artifact"]:
                    raise AuditError("Artifact integrity failure")
                return read_bytes(ref)
            with monkeypatch.context() as patch:
                patch.setattr(current.ledger.artifacts, "read_bytes", changed)
                with pytest.raises(AuditError, match="Artifact integrity failure"):
                    actual_verify(current, value, inputs)
            return actual_verify(current, value, inputs)
        with monkeypatch.context() as patch:
            patch.setattr(subject.supplement, "_verify_value", adversarial_checks)
            supplement_result = engine.execute("status", {"action": "collect", "task_census_record": batch_value["binding"]["task_census_record"],
                "lifecycle_record": life["lifecycle_record"]}, objective="Synthetic fixed native artifacts", actor="test")
    finally:
        engine.close()
    assert f.prior.fixture.source_bytes(main) == before
    monkeypatch.setattr(subject.roots.closure.batch.task.parent.reconciliation.inventory, "open_history_inventory",
        lambda *a, **k: pytest.fail("Metadata replay must not reopen a source"))
    data = {"action": "resolve", "closure_record": closed["closure_record"], "lifecycle_record": life["lifecycle_record"],
        "supplement_record": supplement_result["supplement_record"]}
    engine = subject.MainMetadataParent(observer, source_owner=main)
    try:
        result = upstream.call(engine, data)
        assert result["resolved"] and result["discharged_metadata_gaps"] > 0
        assert result["global_gap"] and not result["dispatch_authorized"]
        assert result["source_owner_reads"] == 0 and not result["task_semantics_reclassified"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert str(tmp_path) not in canonical(result)
        saved = engine.ledger.get(result["metadata_resolution_record"], subject.RESULT)
        proof = engine.ledger.artifacts.read(result["metadata_evidence_artifact"])
        assert proof["pair_blockers_unchanged"] and proof["remaining_metadata_counts"]["records_by_kind"]
        get = engine.ledger.get
        with monkeypatch.context() as patch:
            patch.setattr(engine.ledger, "get", lambda ref, kind=None: {"content": {}} if ref == saved["protocol_record"] else get(ref, kind))
            with pytest.raises(AuditError, match="registered_protocol"):
                upstream.call(engine, {**data, "action": "status"})
        with pytest.raises(AuditError, match="offline_operation"):
            upstream.call(engine, {**data, "complete": True})
    finally:
        engine.close()
    engine = subject.MainMetadataParent(observer, source_owner=main)
    try:
        again = upstream.call(engine, {**data, "action": "status"})
        assert again["metadata_resolution_record"] == result["metadata_resolution_record"]
        assert f.prior.fixture.source_bytes(main) == before
    finally:
        engine.close()
