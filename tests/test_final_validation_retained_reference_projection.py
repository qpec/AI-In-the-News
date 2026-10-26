"""Compact retained-only projection checks; no real owner or model access."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, digest
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_retained_reference_projection as subject  # noqa: E402
import test_final_validation_native_reference as previous  # noqa: E402


@pytest.fixture(scope="module")
def completed_parent(tmp_path_factory):
    """One compact real completed native proof, reused by local-only cases."""
    native = previous.template.__wrapped__(tmp_path_factory)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(previous.previous.subject, "CANDIDATE", native["candidate"])
        patch.setattr(previous.previous.subject.scope, "PAIR_RESULT", native["native_result"])
        patch.setattr(previous.previous.subject.ProbeObserver, "_capture",
            staticmethod(lambda: [previous.previous.previous.compact.process()]))
        engine = previous.subject.NativeReferenceProof(native["owner"])
        try:
            result = previous.execute(engine, {
                "probe_record": native["probe"]["exact_locator_probe_record"],
                "probe_artifact": native["probe"]["exact_locator_probe_artifact"],
            })
            value = engine.ledger.get(result["native_reference_record"], previous.subject.RESULT)
            compiled = engine.ledger.artifacts.read(value["proof_artifact"])
            saved = engine.ledger.artifacts.read(value["native_evidence_artifact"])
            assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 1
        finally:
            engine.close()
    return {**native, "native_proof": result, "native_value": value, "compiled": compiled, "saved": saved}


@pytest.fixture
def case(tmp_path, completed_parent, monkeypatch):
    owner = tmp_path / "observer"
    prepare_root(owner)
    shutil.copytree(completed_parent["owner"], owner, dirs_exist_ok=True)
    monkeypatch.setattr(previous.previous.subject, "CANDIDATE", completed_parent["candidate"])
    monkeypatch.setattr(previous.previous.subject.scope, "PAIR_RESULT", completed_parent["native_result"])
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "__init__",
        lambda *_a, **_k: pytest.fail("retained projection opened a source"))
    monkeypatch.setattr(previous.previous.subject.ProbeObserver, "_capture",
        staticmethod(lambda: pytest.fail("retained projection observed a source process")))
    selected = {"native_reference_record": completed_parent["native_proof"]["native_reference_record"],
        "native_reference_artifact": completed_parent["native_proof"]["native_reference_artifact"]}
    return owner, completed_parent, selected


def execute(engine, selected, action="project"):
    return engine.execute("status", {"action": action, **selected},
        objective="Synthetic retained native evidence projection", actor="test")


def test_completed_native_projection_is_local_bound_and_cached(case, monkeypatch):
    owner, parent, selected = case
    before = previous.previous.previous.compact.file_hashes(parent["candidate"])
    engine = subject.RetainedReferenceProjection(owner)
    reads = []
    native_read = engine.ledger.artifacts.read
    def counted(reference):
        reads.append(reference)
        return native_read(reference)
    monkeypatch.setattr(engine.ledger.artifacts, "read", counted)
    try:
        result = execute(engine, selected)
        assert result["observed_physical_intents"] == result["verified_physical_ids"] == result["primary_pair_blockers"] == 1
        assert result["unknown_regions"] == result["implementation_mismatch_count"] == 0
        assert result["source_owner_reads"] == result["new_model_calls"] == 0
        assert result["fresh_eligibility"] == "unknown" and result["original_global_gaps_preserved"]
        assert not result["dispatch_authorized"] and not result["history_complete"] and not result["sample_registered"]
        assert not result["old_labels_reused"] and not result["historical_code_equivalence_inferred"]
        value = engine.ledger.get(result["reference_projection_record"], subject.RESULT)
        assert value["native_reference_record"] == selected["native_reference_record"]
        assert value["source_head"] == parent["native_value"]["source_head"]
        assert value["input_index_digest"] == parent["index"].digest
        assert value["preserved_authority"] == parent["native_value"]["preserved_authority"]
        assert value["preserved_authority"]["declared_gap_counts"] == {"manual_review_scope_missing": 1}
        projection = engine.ledger.artifacts.read(value["projection_artifact"])
        assert projection["pair_role_blockers"][0]["references"][0]["physical_id"] == parent["compiled"]["attempts"][0]["physical_id"]
        assert projection["attempt_partitions"][0]["original_gaps"] == []
        original_intent = next(json.loads(r["payload"]) for r in parent["events"] if r["kind"] == "model.attempt.intended")
        assert original_intent["request"] not in reads and original_intent["dispatch"] not in reads
        assert "PRIVATE BODY" not in json.dumps(result)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        identifier = result["reference_projection_record"]
    finally:
        engine.close()
    engine = subject.RetainedReferenceProjection(owner)
    try:
        repeated = execute(engine, selected, "status")
        assert repeated["reference_projection_record"] == identifier and repeated["reused_completed"]
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()
    assert previous.previous.previous.compact.file_hashes(parent["candidate"]) == before


@pytest.mark.parametrize("field", ["native_reference_record", "native_reference_artifact"])
def test_foreign_completed_native_parent_rejected(case, field):
    owner, _, selected = case
    selected[field] = digest("foreign parent")
    engine = subject.RetainedReferenceProjection(owner)
    try:
        with pytest.raises(AuditError, match="selected_native_result"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["summary", "producer_output"])
def test_parent_derived_summary_and_completed_output_cannot_be_substituted(case, monkeypatch, fault):
    owner, parent, selected = case
    engine = subject.RetainedReferenceProjection(owner)
    reference = parent["native_value"]["proof_artifact"]
    if fault == "producer_output":
        raw = engine._raw(selected["native_reference_record"])
        session = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (raw["created_event"],)).fetchone()[0]
        output = engine.ledger.db.execute("SELECT payload FROM events WHERE session_id=? AND kind='operation.completed'", (session,)).fetchone()[0]
        reference = json.loads(output)["result"]
    native_read = engine.ledger.artifacts.read
    def altered(ref):
        value = native_read(ref)
        if ref == reference:
            value = deepcopy(value)
            if fault == "summary":
                value["matched_intents"] += 1
            else:
                value["native_reference_artifact"] = digest("foreign result")
        return value
    monkeypatch.setattr(engine.ledger.artifacts, "read", altered)
    try:
        with pytest.raises(AuditError, match="native_summary|producer_output"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def pure_evidence():
    rows = tuple(SimpleNamespace(input_sha256=digest(["input", i]), document_id=f"doc-{i}",
        article_row_ids=(f"article-{i}", f"alias-{i}")) for i in range(2))
    index = SimpleNamespace(inputs=rows, digest=digest("synthetic complete index"))
    endpoints = [{"input_sha256": r.input_sha256, "full_input_identity_verified": True,
        "native_full_source_provenance_verified": False, "outside_final_frame_proved": False,
        "final_inputs": [{"document_id": r.document_id, "article_row_ids": list(r.article_row_ids)}]} for r in rows]
    record = digest("synthetic manifest")
    names = set(subject.native.judging.CODE)
    code = {name: digest(["synthetic code", name]) for name in names}
    binding = {"implementation": {"src/newsresearch/" + name: sha for name, sha in code.items()}}
    saved = {"records": {record: {"kind": subject.native.MANIFEST_KIND,
        "payload": json.dumps({"binding": {"implementation": code}})}}}
    attempt = {"original_attempt": "synthetic physical attempt", "intended_event_hash": digest("intent event"),
        "physical_id": None, "origin_verified": False, "plan": record, "task_key": digest("task"),
        "endpoints": endpoints, "role": "possible_primary", "gaps": [], "label": None}
    compiled = {"attempts": [attempt], "gaps": [], "unprocessed_attempt_event_hashes": [], "matched_intents": 1}
    return compiled, saved, index, binding, record


def test_historical_code_differences_are_diagnostics_not_purpose_or_origin():
    compiled, saved, index, binding, record = pure_evidence()
    payload = json.loads(saved["records"][record]["payload"])
    code = payload["binding"]["implementation"]
    changed, missing = sorted(code)[:2]
    code[changed] = digest("old recorded bytes")
    del code[missing]
    code["extra_native_module.py"] = digest("extra bytes")
    saved["records"][record]["payload"] = json.dumps(payload)
    compiled["gaps"] = [{"reason": "unsupported_historical_producer_code", "reference": record, "scope": "native_graph"}]
    result = subject.project_evidence(compiled, saved, index, binding)
    by_path = {r["path"]: r for r in result["implementation_mismatches"]}
    assert by_path["src/newsresearch/" + changed]["change"] == "changed"
    assert by_path["src/newsresearch/" + changed]["recorded_sha256"] == digest("old recorded bytes")
    assert by_path["src/newsresearch/" + missing]["change"] == "missing_recorded_path"
    assert by_path["src/newsresearch/extra_native_module.py"]["change"] == "extra_recorded_path"
    assert all(row["record"] == record and row["producer_kind"] == subject.native.MANIFEST_KIND for row in by_path.values())
    assert result["pair_role_blockers"] == [] and result["physical_attempts"] == {}
    assert result["unknown_regions"][0]["affected_input_sha256"] is None
    assert result["unknown_regions"][0]["role"] is None
    assert result["attempt_partitions"][0]["input_sha256"] == sorted(r.input_sha256 for r in index.inputs)
    assert result["original_native_scope_gaps"] == compiled["gaps"]
    assert result["fresh_eligibility"] == "unknown" and not result["historical_code_equivalence_inferred"]


def test_unknown_endpoint_and_unprocessed_intent_remain_global_regions():
    compiled, saved, index, binding, _ = pure_evidence()
    for endpoint in compiled["attempts"][0]["endpoints"]:
        endpoint.update(input_sha256=digest(["outside unproved", endpoint["input_sha256"]]), final_inputs=[],
            outside_final_frame_proved=False)
    compiled["unprocessed_attempt_event_hashes"] = [digest("over-cap unprocessed event")]
    compiled["matched_intents"] = 2
    result = subject.project_evidence(compiled, saved, index, binding)
    assert len(result["unknown_regions"]) == 2
    assert all(r["affected_input_sha256"] is None and r["role"] is None for r in result["unknown_regions"])
    assert result["pair_role_blockers"] == [] and not result["history_complete"]
    assert result["unprocessed_attempt_event_hashes"] == compiled["unprocessed_attempt_event_hashes"]


@pytest.mark.parametrize("shape", ["outside", "same_input_aliases", "exact_pair"])
def test_generation_without_verified_dispatch_cannot_exclude_unknown_regions(shape):
    compiled, saved, index, binding, _ = pure_evidence()
    attempt = compiled["attempts"][0]
    attempt.update(native_request_generation_verified=True, request_and_dispatch_verified=False, role="primary")
    for endpoint in attempt["endpoints"]:
        endpoint["native_full_source_provenance_verified"] = True
    if shape == "outside":
        attempt["endpoints"][0].update(input_sha256=digest("exact source outside frame"),
            final_inputs=[], outside_final_frame_proved=True)
    elif shape == "same_input_aliases":
        attempt["endpoints"][1] = deepcopy(attempt["endpoints"][0])
    result = subject.project_evidence(compiled, saved, index, binding)
    assert len(result["unknown_regions"]) >= 1
    assert any(r["affected_input_sha256"] is None and r["role"] is None for r in result["unknown_regions"])
    assert result["attempt_partitions"][0]["disposition"] not in {
        "one_verified_source_outside_current_frame", "same_final_input_aliases_only"}
    assert len(result["pair_role_blockers"]) == (1 if shape == "exact_pair" else 0)
    assert result["physical_attempts"] == {} and result["fresh_eligibility"] == "unknown"


@pytest.mark.parametrize("fault", ["duplicate_intent", "omitted_intent", "alias_mapping", "duplicate_physical"])
def test_projection_rejects_foreign_or_ambiguous_partitions(fault):
    compiled, saved, index, binding, _ = pure_evidence()
    if fault == "duplicate_intent":
        compiled["attempts"].append(deepcopy(compiled["attempts"][0]))
        compiled["matched_intents"] = 2
    elif fault == "omitted_intent":
        compiled["matched_intents"] = 2
    elif fault == "alias_mapping":
        compiled["attempts"][0]["endpoints"][0]["final_inputs"][0]["article_row_ids"] = ["foreign alias"]
    else:
        attempt = compiled["attempts"][0]
        attempt.update(physical_id=digest("same physical attempt"), origin_verified=True)
        other = deepcopy(attempt)
        other["intended_event_hash"] = digest("different retained intent")
        compiled["attempts"].append(other)
        compiled["matched_intents"] = 2
    with pytest.raises(AuditError, match="attempt_partition|intent_partition|endpoint_index_binding|physical_identity"):
        subject.project_evidence(compiled, saved, index, binding)


def test_unrecognized_code_locations_and_paths_stay_unresolved():
    compiled, saved, index, binding, record = pure_evidence()
    payload = json.loads(saved["records"][record]["payload"])
    payload["binding"]["implementation"]["../private-source.txt"] = digest("opaque path")
    payload["binding"]["implementation"]["bad_hash.py"] = "not a content hash"
    saved["records"][record]["payload"] = json.dumps(payload)
    absent = digest("unavailable historical code record")
    compiled["gaps"] = [{"reason": "unsupported_historical_producer_code", "reference": r} for r in (record, absent)]
    result = subject.project_evidence(compiled, saved, index, binding)
    assert {r["reason"] for r in result["unresolved_code_locations"]} == {
        "unsupported_code_path", "invalid_recorded_code_hash", "unsupported_retained_code_location"}
    assert "../private-source.txt" not in json.dumps(result)
    assert not result["pair_role_blockers"] and result["unknown_regions"]
