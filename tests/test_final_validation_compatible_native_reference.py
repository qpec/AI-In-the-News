"""One compact historical-code continuation fixture; no real owners/models."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, digest
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_compatible_native_reference as subject  # noqa: E402
import final_validation_retained_reference_projection as projection  # noqa: E402
import test_final_validation_native_reference as previous  # noqa: E402


OLD_COMMIT = "df2848eba7c2ac34269d5a14c808e67f511f8801"
CODE_PATH = "src/newsresearch/codex_provider.py"


@pytest.fixture(scope="module")
def code_bytes():
    root = Path(__file__).resolve().parents[1]
    old = subprocess.run(["git", "-C", str(root), "show", f"{OLD_COMMIT}:{CODE_PATH}"],
        capture_output=True, check=True).stdout
    return old, (root / CODE_PATH).read_bytes()


@pytest.fixture(scope="module")
def template(tmp_path_factory, code_bytes):
    old_sha = hashlib.sha256(code_bytes[0]).hexdigest()
    hash_codes = previous.judging.preparation.links.base._hashes
    original_identity = previous.NativeSource.identity
    def historical_hashes(names):
        result = hash_codes(names)
        if "codex_provider.py" in result:
            result["codex_provider.py"] = old_sha
        return result
    def historical_identity(engine):
        # Explicit synthetic historical metadata. The actual event-pair wire
        # builders are also checked against the exact old/current AST gate.
        result = original_identity(engine)
        result["code_files"][CODE_PATH] = old_sha
        result["code_digest"] = digest(result["code_files"])
        return result
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(previous.judging.preparation.links.base, "_hashes", historical_hashes)
        patch.setattr(previous.NativeSource, "identity", historical_identity)
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
            native_value = engine.ledger.get(result["native_reference_record"], previous.subject.RESULT)
            saved = engine.ledger.artifacts.read(native_value["native_evidence_artifact"])
            assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 0
            assert result["gap_counts"]["unsupported_historical_producer_code"] == 1
        finally:
            engine.close()
        engine = projection.RetainedReferenceProjection(native["owner"])
        try:
            projected = engine.execute("status", {"action": "project",
                "native_reference_record": result["native_reference_record"],
                "native_reference_artifact": result["native_reference_artifact"]},
                objective="Synthetic historical transport mismatch projection", actor="test")
            assert projected["unknown_regions"] == 1 and projected["primary_pair_blockers"] == 0
        finally:
            engine.close()
    return {**native, "native_proof": result, "native_value": native_value, "saved": saved, "projection": projected}


@pytest.fixture
def case(tmp_path, template, monkeypatch):
    owner = tmp_path / "observer"
    prepare_root(owner)
    shutil.copytree(template["owner"], owner, dirs_exist_ok=True)
    monkeypatch.setattr(previous.previous.subject, "CANDIDATE", template["candidate"])
    monkeypatch.setattr(previous.previous.subject.scope, "PAIR_RESULT", template["native_result"])
    monkeypatch.setattr(previous.previous.subject.ProbeObserver, "_capture",
        staticmethod(lambda: [previous.previous.previous.compact.process()]))
    selected = {"projection_record": template["projection"]["reference_projection_record"],
        "projection_artifact": template["projection"]["reference_projection_artifact"]}
    return owner, template, selected


def execute(engine, selected, action="prove"):
    return engine.execute("status", {"action": action, **selected},
        objective="Synthetic exact-compatible native reference continuation", actor="test")


def test_exact_historical_bytes_have_only_the_two_disjoint_ast_additions(code_bytes):
    old, current = code_bytes
    proof = subject.prove_code_compatibility(old, current)
    assert proof["historical_sha256"] == hashlib.sha256(old).hexdigest() == subject.OLD_HASH
    assert proof["current_sha256"] == hashlib.sha256(current).hexdigest() == subject.CURRENT_HASH
    assert proof["removed_branch_counts"] == {"build_prompt": 1, "_worker_rules": 1}
    assert proof["task_kind"] == "event_pair_identity"
    assert not proof["historical_code_executed"] and not proof["general_code_equivalence_claimed"]


@pytest.mark.parametrize("fault", ["historical_bytes", "current_bytes", "other_ast_change"])
def test_compatibility_requires_both_fixed_hashes_and_the_complete_remaining_ast(code_bytes, monkeypatch, fault):
    old, current = code_bytes
    if fault == "historical_bytes":
        old += b"\n# different historical blob\n"
    elif fault == "current_bytes":
        current += b"\n# different current blob\n"
    else:
        changed = current.replace(b'"event_pair_identity"', b'"unrelated_pair_identity"')
        assert changed != current
        current = changed
        # Isolate the independent AST guard in a pure test. Production callers
        # cannot supply or change this implementation-bound expected hash.
        monkeypatch.setattr(subject, "CURRENT_HASH", hashlib.sha256(current).hexdigest())
    with pytest.raises(AuditError, match="compatibility_code_hashes|compatibility_ast"):
        subject.prove_code_compatibility(old, current)


def test_exact_current_and_historical_transport_profiles_are_the_only_exception():
    expected = {"codex_provider.py": subject.CURRENT_HASH, "event_pair_answers.py": digest("unchanged contract")}
    subject.compatible_code(expected, expected, digest("record"))
    subject.compatible_code({**expected, "codex_provider.py": subject.OLD_HASH}, expected, digest("record"))


@pytest.mark.parametrize("fault", ["provider_hash", "other_file", "extra_file", "missing_file"])
def test_other_code_differences_remain_unsupported(fault):
    expected = {"codex_provider.py": subject.CURRENT_HASH, "event_pair_answers.py": digest("unchanged contract")}
    recorded = {**expected, "codex_provider.py": subject.OLD_HASH}
    if fault == "provider_hash":
        recorded["codex_provider.py"] = digest("different provider")
    elif fault == "other_file":
        recorded["event_pair_answers.py"] = digest("different contract")
    elif fault == "extra_file":
        recorded["extra.py"] = digest("extra code")
    else:
        del recorded["event_pair_answers.py"]
    with pytest.raises(subject.Unavailable) as error:
        subject.compatible_code(recorded, expected, digest("record"))
    assert error.value.reason == "unsupported_historical_producer_code"


def test_actual_historical_continuation_reuses_retained_bytes_and_preserves_all_identities(case, monkeypatch):
    owner, native, selected = case
    before = previous.previous.previous.compact.file_hashes(native["candidate"])
    old_refs = {row["artifact"] for row in native["saved"]["artifacts"]}
    reads = []
    source_read = previous.previous.subject.SOURCE.Source.artifact_bytes
    def missing_only(source, reference):
        assert reference not in old_refs, "continuation refetched a retained artifact"
        reads.append(reference)
        return source_read(source, reference)
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "artifact_bytes", missing_only)
    engine = subject.CompatibleNativeReference(owner)
    native_record = engine.ledger.record
    committed_under_lock = []
    def locked_record(session, kind, key, value, *args, **kwargs):
        if kind == subject.RESULT:
            writer = None
            try:
                with pytest.raises(AuditError, match="concurrent research processes"):
                    writer = previous.Research(native["candidate"], config=previous.Config(offline=True))
                committed_under_lock.append(True)
            finally:
                if writer is not None:
                    writer.close()
        return native_record(session, kind, key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", locked_record)
    try:
        result = execute(engine, selected)
        assert committed_under_lock == [True]
        assert result["observed_physical_intents"] == result["processed_attempts"] == 1
        assert result["verified_actual_request_dispatches"] == result["native_origin_attempts"] == 1
        assert result["uncompleted_intents"] == 1 and result["primary_pair_blockers"] == 1
        assert result["retained_bytes_reused"] > 0 and result["missing_bytes_transferred"] > 0
        assert len(reads) == len(set(reads)) > 0
        assert result["previous_gap_counts"]["unsupported_historical_producer_code"] == 1
        assert result["fresh_eligibility"] == "unknown" and result["all_original_gaps_preserved"]
        assert result["new_model_calls"] == 0 and not result["dispatch_authorized"]
        assert not result["old_labels_reused"] and not result["historical_code_executed"] and not result["sample_registered"]
        value = engine.ledger.get(result["compatible_reference_record"], subject.RESULT)
        assert value["previous_native_proof_artifact"] == native["native_value"]["proof_artifact"]
        assert value["preserved_authority"] == native["native_value"]["preserved_authority"]
        assert value["source_head"] == native["native_value"]["source_head"]
        assert value["input_index_digest"] == native["index"].digest
        compiled = engine.ledger.artifacts.read(value["proof_artifact"])
        original_intent = next(r for r in native["events"] if r["kind"] == "model.attempt.intended")
        attempt = compiled["attempts"][0]
        assert attempt["intended_event_hash"] == original_intent["event_hash"]
        assert attempt["original_attempt"] == "synthetic-native-orphan" and attempt["joined_events"] == []
        assert attempt["physical_id"] == digest([str(native["candidate"]), "synthetic-native-orphan"])
        assert attempt["label"] is None and not attempt["current_reference_compatible"]
        assert any(len(row["article_row_ids"]) == 2 for e in attempt["endpoints"] for row in e["final_inputs"])
        assert engine.ledger.get(native["native_proof"]["native_reference_record"], previous.subject.RESULT) == native["native_value"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        progress = json.loads((owner / "compatible-native-reference-progress.json").read_text(encoding="utf-8"))
        assert progress["method"] == subject.METHOD and progress["stage"] == "complete"
        assert "PRIVATE BODY" not in json.dumps(result)
        identifier = result["compatible_reference_record"]
    finally:
        engine.close()
    assert previous.previous.previous.compact.file_hashes(native["candidate"]) == before
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("cached continuation opened source"))
    monkeypatch.setattr(previous.previous.subject.ProbeObserver, "_capture", staticmethod(lambda: pytest.fail("cached continuation observed source")))
    native_run = subprocess.run
    def no_new_historical_blob(command, *args, **kwargs):
        assert not (command[:2] == ["git", "show"]), "cached continuation fetched historical code again"
        return native_run(command, *args, **kwargs)
    monkeypatch.setattr(subject.subprocess, "run", no_new_historical_blob)
    engine = subject.CompatibleNativeReference(owner)
    try:
        repeated = execute(engine, selected, "status")
        assert repeated["compatible_reference_record"] == identifier and repeated["reused_completed"]
        assert len(engine._rows(subject.RESULT)) == 1
    finally:
        engine.close()


class MemoryCompatible(previous.MemoryReader):
    session = subject.CompatibleReader.session


@pytest.mark.parametrize("omitted", ["processed", "unprocessed"])
def test_partition_cannot_drop_an_original_physical_intent(omitted):
    processed, unprocessed = digest("original processed event"), digest("original unprocessed event")
    old = {"attempts": [{"intended_event_hash": processed}],
        "unprocessed_attempt_event_hashes": [unprocessed], "original_study_key": "synthetic original"}
    compiled = {"attempts": [] if omitted == "processed" else [{"intended_event_hash": processed}],
        "unprocessed_attempt_event_hashes": [] if omitted == "unprocessed" else [unprocessed],
        "original_study_key": "synthetic original"}
    engine = SimpleNamespace(ledger=SimpleNamespace(artifacts=SimpleNamespace(
        read=lambda *_: pytest.fail("dropped intent reached partition replay"))))
    with pytest.raises(AuditError, match="compatible_old_attempts_preserved"):
        subject.CompatibleNativeReference._verify_partition(engine, {}, compiled, {}, old, None, {})


@pytest.mark.parametrize("fault", ["wrong_task", "missing_dispatch"])
def test_request_scope_and_missing_evidence_never_grant_general_clearance(template, monkeypatch, fault):
    monkeypatch.setattr(previous.previous.subject.scope, "PAIR_RESULT", template["native_result"])
    reader = MemoryCompatible(template)
    original_read = reader.read
    def altered(reference, reason):
        if fault == "missing_dispatch" and reason == "actual_intended_dispatch":
            raise subject.Unavailable("native_artifact_absent", reference)
        value = original_read(reference, reason)
        if fault == "wrong_task" and reason == "actual_intended_request":
            value = {**value, "task_kind": "luna_article_lead_screen"}
        return value
    monkeypatch.setattr(reader, "read", altered)
    try:
        if fault == "wrong_task":
            with pytest.raises(AuditError, match="compatibility_task_kind"):
                subject.compile_reference(reader, template["index"], template["native_result"])
        else:
            compiled = subject.compile_reference(reader, template["index"], template["native_result"])
            attempt = compiled["attempts"][0]
            assert attempt["physical_id"] is None and attempt["label"] is None and not attempt["origin_verified"]
            assert attempt["gaps"][0]["reason"] == "native_artifact_absent"
            partition = projection.project_evidence(compiled, {"records": reader.records}, template["index"], template["native_value"]["binding"])
            assert any(r["affected_input_sha256"] is None for r in partition["unknown_regions"])
            assert not partition["history_complete"] and partition["fresh_eligibility"] == "unknown"
    finally:
        reader.source.db.close()


@pytest.mark.parametrize("field", ["projection_record", "projection_artifact"])
def test_foreign_completed_projection_is_rejected_before_source(case, monkeypatch, field):
    owner, _, selected = case
    selected[field] = digest("foreign projection")
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("foreign projection opened source"))
    engine = subject.CompatibleNativeReference(owner)
    try:
        with pytest.raises(AuditError, match="compatible_selected_projection"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_completed_projection_output_binding_is_required(case, monkeypatch):
    owner, _, selected = case
    engine = subject.CompatibleNativeReference(owner)
    raw = engine._raw(selected["projection_record"])
    session = engine.ledger.db.execute("SELECT session_id FROM events WHERE seq=?", (raw["created_event"],)).fetchone()[0]
    output = engine.ledger.db.execute("SELECT payload FROM events WHERE session_id=? AND kind='operation.completed'", (session,)).fetchone()[0]
    reference = json.loads(output)["result"]
    read = engine.ledger.artifacts.read
    def foreign_output(ref):
        value = read(ref)
        return {**value, "reference_projection_artifact": digest("foreign completed artifact")} if ref == reference else value
    monkeypatch.setattr(engine.ledger.artifacts, "read", foreign_output)
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("incomplete parent opened source"))
    try:
        with pytest.raises(AuditError, match="producer_output"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


def test_changed_source_head_cannot_commit_continuation(case, monkeypatch):
    owner, _, selected = case
    original_head = previous.previous.subject.SOURCE.Source.head
    def changed(source, *, fresh=False):
        head = original_head(source, fresh=fresh)
        return [head[0] + 1, digest("changed synthetic head")] if fresh else head
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "head", changed)
    engine = subject.CompatibleNativeReference(owner)
    try:
        with pytest.raises(AuditError, match="source_head_changed"):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()


@pytest.mark.parametrize("where", ["observer", "candidate"])
def test_stop_blocks_continuation_before_source(case, monkeypatch, where):
    owner, native, selected = case
    stop = (owner if where == "observer" else native["candidate"]) / "STOP"
    stop.write_text("synthetic stop", encoding="utf-8")
    monkeypatch.setattr(previous.previous.subject.SOURCE.Source, "__init__", lambda *_a, **_k: pytest.fail("STOP allowed source opening"))
    engine = subject.CompatibleNativeReference(owner)
    try:
        with pytest.raises(AuditError):
            execute(engine, selected)
        assert not engine._rows(subject.RESULT)
    finally:
        engine.close()
        stop.unlink()
