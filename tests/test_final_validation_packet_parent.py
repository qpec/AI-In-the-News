"""Actual synthetic registered parent composition; never real owners or models."""
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_packet_parent as subject  # noqa: E402
import test_final_validation_reconciliation as fixtures  # noqa: E402
from test_final_validation_admission import native_bytes, policy, receipt  # noqa: E402
from test_final_validation_source import source_bytes  # noqa: E402
from test_final_validation_study import process  # noqa: E402


@pytest.fixture(autouse=True)
def synthetic_observer(monkeypatch):
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


class Evidence(Research):
    @audited_handler
    def _status(self, session, context, data):
        module = subject.admission
        version = self._version(session, context, {"kind": "protocol", "key": module.METHOD,
            "content": module.protocol_content(data["study_record"])})["id"]
        context = Context(context.objective, context.actor, {"protocol": version})
        def version_only(command, **kwargs):
            assert command == [data["executable"], "--version"]
            return SimpleNamespace(stdout="codex-cli 0.120.0\n", stderr="", returncode=0)
        with patch.object(module.subprocess, "run", version_only):
            runtime = module.observe_runtime(self, session, context, study_record=data["study_record"],
                executable=data["executable"], executable_sha256=data["executable_sha256"])
        quota = module.retain_quota_receipt(self, session, context, study_record=data["study_record"], receipt=data["receipt"])
        chosen = module.retain_resource_policy(self, session, context, study_record=data["study_record"], policy=data["policy"])
        return {"runtime_record": runtime["runtime_record"], "quota_record": quota, "resource_policy_record": chosen}


def setup(tmp_path, *, declared_gap=False):
    main, observer, binding, documents = fixtures.setup(tmp_path)
    old = fixtures.screening(tmp_path, "historical", documents[:2])
    registry = fixtures.registry([old], gaps=[{"reason_code": "manual_review_scope_missing", "affected_input_sha256": None}]
        if declared_gap else None)
    reconciled, _ = fixtures.run(main, observer, binding, registry)
    return main, observer, subject.frame_binding(preparation_binding=binding,
        reconciliation_record=reconciled["reconciliation_record"]), old, documents


def execute(main, observer, action, binding):
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        return engine.execute("status", {"action": action, "binding": binding},
            objective="Synthetic final frame/slot verification", actor="synthetic")
    finally:
        engine.close()


def resource_evidence(tmp_path, observer, study_record, **kwargs):
    executable = tmp_path / "synthetic-native.exe"
    executable.write_bytes(native_bytes())
    engine = Evidence(observer, config=Config(offline=True))
    try:
        return engine.execute("status", {"study_record": study_record, "executable": str(executable),
            "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
            "receipt": receipt(used=kwargs.get("used", 20), stale=kwargs.get("stale", False)),
            "policy": policy(allow=kwargs.get("allow", True))}, objective="Synthetic resource evidence", actor="synthetic")
    finally:
        engine.close()


def test_real_final_frame_fixed_unavailable_slots_actual_admission_and_reopen(tmp_path, monkeypatch):
    main, observer, binding, old, documents = setup(tmp_path)
    before = {str(p): source_bytes(Path(p)) for p in (main, old["source_owner"])}
    result = execute(main, observer, "freeze_final_frame", binding)
    assert result["final_frame_frozen"] and not result["history_scope_complete"]
    evidence = resource_evidence(tmp_path, observer, binding["preparation_binding"]["study_record"])
    selected = subject.slot_binding(final_frame_record=result["final_frame_record"], **evidence)
    slots = execute(main, observer, "prepare_initial_slots", selected)
    assert slots["upstream_packet_authority_verified"] and not slots["dispatch_authorized"]
    assert not slots["empirical_validation_completed"] and slots["resource_census"]["selected_primary_pairs"] > 0
    assert slots["resource_census"]["unavailable_slots"] == slots["resource_census"]["selected_slots"]
    assert slots["resource_census"]["fresh_potential_invocations"] == slots["resource_census"]["planned_token_reservations"] == 0
    assert slots["remaining_blockers"] == ["zero_fresh_slots_preserved"]
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        frame_row, chain, frame, schedule = engine._load_frame(result["final_frame_record"])
        assert len(frame.index.inputs) == len(documents) == 4
        assert sum(s.population for s in frame.strata) == 6
        assert {s.prior_exposure for s in frame.strata} == {"exposed", "unknown"}
        scope = engine.ledger.get(result["scope_disposition_record"], subject.SCOPE)
        assert len(scope["source_dispositions"]) == 2 and scope["known_declared_unprocessed_sources"] == 0
        assert scope["never_enumerated_history"] == "unverified_global_unknown"
        initial = engine.ledger.artifacts.read(slots["prepared_initial_artifact"])
        assert initial["initial_prefix"] == schedule.manifest["initial_prefix"]
        assert all(t["packet"] is None and t["history"]["state"] == "prior_attempt_unavailable" for t in initial["tasks"])
        assert initial["bindings"]["history_inventory_sha256"] == chain[3]["artifacts"]["pair_history_inventory"]
        assert engine.ledger.artifacts.read(initial["bindings"]["history_inventory_sha256"])["global_gap"]
        assert initial["order_seed_binding"]["artifact"] == chain[2]["article_order_seed_artifact"]
        assert frame_row["schedule_seed_artifact"] == chain[2]["schedule_seed_artifact"]
        authority = engine.ledger.get(slots["slot_admission_record"], subject.execution.ADMISSION_KIND)
        assert authority["source_history_seed_and_authority_verified"] and not authority["dispatch_authorized"]
        manifest = engine.ledger.artifacts.read(slots["candidate_execution_manifest_artifact"])
        subject.execution.validate_manifest(manifest)
        assert manifest["upstream_binding"] == slots["slot_admission_record"]
        assert manifest["slot_catalog_sha256"] == authority["slot_catalog_sha256"]
        assessment = engine.ledger.get(slots["resource_assessment_record"], subject.admission.ASSESSMENT)
        assert "audited_packet_source_history_seed_authority_pending" in assessment["blockers"]
        assert not assessment["upstream_packet_authority_verified"]  # Original report never rewritten.
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.execution.MANIFEST_KIND,)).fetchone()
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert len(engine._rows(subject.study.SEEDS)) == len(engine._rows(subject.FRAME)) == len(engine._rows(subject.SLOTS)) == 1
    finally:
        engine.close()
    assert all(source_bytes(Path(path)) == raw for path, raw in before.items())
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("exact historical reuse must not reopen source"))))
    repeated = execute(main, observer, "freeze_final_frame", binding)
    again = execute(main, observer, "prepare_initial_slots", selected)
    assert repeated["final_frame_record"] == result["final_frame_record"] and repeated["reused_historical_frame"]
    assert again["slot_record"] == slots["slot_record"] and again["reused_historical_slots"]
    assert not repeated["current_source_quiescence_verified"] and not again["current_source_quiescence_verified"]
    assert all(d["body"] not in canonical(slots) for d in documents)


def test_known_declared_unprocessed_manual_scope_cannot_be_finalized(tmp_path, monkeypatch):
    main, observer, binding, _, _ = setup(tmp_path, declared_gap=True)
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("pending scope fails before source reads"))))
    with pytest.raises(AuditError, match="unprocessed_scope"):
        execute(main, observer, "freeze_final_frame", binding)
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        assert not engine._rows(subject.INTENT) and not engine._rows(subject.FRAME)
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["reconciliation_record", "seed_record", "snapshot_artifact"])
def test_wrong_upstream_record_cannot_supply_packet_truth(tmp_path, monkeypatch, field):
    main, observer, binding, _, _ = setup(tmp_path)
    if field == "reconciliation_record":
        binding[field] = digest("unrelated")
    elif field == "seed_record":
        binding["preparation_binding"][field] = digest("unrelated")
    else:
        binding["preparation_binding"]["snapshot_binding"][field] = digest("unrelated")
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("upstream failure before reads"))))
    with pytest.raises((AuditError, ValueError)):
        execute(main, observer, "freeze_final_frame", binding)


def test_same_bound_interruption_resumes_without_seed_reroll_or_new_scope(tmp_path, monkeypatch):
    main, observer, binding, _, _ = setup(tmp_path)
    real = subject.PacketParent._compose
    monkeypatch.setattr(subject.PacketParent, "_compose", lambda *a: (_ for _ in ()).throw(AuditError("synthetic-interruption")))
    with pytest.raises(AuditError, match="synthetic-interruption"):
        execute(main, observer, "freeze_final_frame", binding)
    monkeypatch.setattr(subject.PacketParent, "_compose", real)
    result = execute(main, observer, "freeze_final_frame", binding)
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        assert len(engine._rows(subject.INTENT)) == len(engine._rows(subject.FRAME)) == len(engine._rows(subject.study.SEEDS)) == 1
        assert result["final_frame_frozen"]
    finally:
        engine.close()


def test_external_source_changed_after_composition_blocks_frame_commit(tmp_path, monkeypatch):
    main, observer, binding, old, _ = setup(tmp_path)
    real = subject.PacketParent._compose
    def changed(self, *args):
        result = real(self, *args)
        writer = Research(Path(old["source_owner"]), config=Config(offline=True))
        try:
            writer.execute("status", {}, objective="Synthetic later source activity", actor="synthetic")
        finally:
            writer.close()
        return result
    monkeypatch.setattr(subject.PacketParent, "_compose", changed)
    with pytest.raises(AuditError, match="final_commit_cutoff_changed"):
        execute(main, observer, "freeze_final_frame", binding)
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        assert not engine._rows(subject.FRAME)
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["exhausted", "stale", "quota_policy_blocks"])
def test_resource_blockers_survive_verified_upstream_authority(tmp_path, fault):
    main, observer, binding, _, _ = setup(tmp_path)
    frame = execute(main, observer, "freeze_final_frame", binding)
    evidence = resource_evidence(tmp_path, observer, binding["preparation_binding"]["study_record"],
        used=100 if fault == "exhausted" else 20, stale=fault == "stale", allow=fault != "quota_policy_blocks")
    selected = subject.slot_binding(final_frame_record=frame["final_frame_record"], **evidence)
    result = execute(main, observer, "prepare_initial_slots", selected)
    assert {"exhausted": "observed_account_limit_exhausted", "stale": "quota_observation_stale",
        "quota_policy_blocks": "quota_unit_capacity_unavailable_policy_blocks"}[fault] in result["remaining_blockers"]
    assert not result["dispatch_authorized"]


@pytest.mark.parametrize("field", ["task_scope_closure_record", "history_inventory", "source_documents", "complete"])
def test_caller_closure_or_source_assertions_are_not_an_interface(tmp_path, field):
    engine = subject.PacketParent(tmp_path / "empty-observer", source_owner=tmp_path / "never-open-source")
    try:
        binding = subject.slot_binding(**{k: digest(k) for k in (
            "final_frame_record", "runtime_record", "quota_record", "resource_policy_record")})
        binding[field] = digest("asserted")
        with pytest.raises(AuditError, match="slot_binding_fields"):
            engine.execute("status", {"action": "prepare_initial_slots", "binding": binding}, objective="Synthetic rejection", actor="test")
        assert not (tmp_path / "never-open-source").exists()
    finally:
        engine.close()


def test_changed_final_scope_or_resources_cannot_silently_redraw(tmp_path):
    main, observer, binding, _, _ = setup(tmp_path)
    frame = execute(main, observer, "freeze_final_frame", binding)
    evidence = resource_evidence(tmp_path, observer, binding["preparation_binding"]["study_record"])
    selected = subject.slot_binding(final_frame_record=frame["final_frame_record"], **evidence)
    execute(main, observer, "prepare_initial_slots", selected)
    changed = deepcopy(selected)
    changed["quota_record"] = digest("later quota")
    with pytest.raises(AuditError, match="changed_slots_require_amendment"):
        execute(main, observer, "prepare_initial_slots", changed)


@pytest.mark.parametrize("fault", ["schedule_seed", "order_seed", "protocol", "intent", "scope_versions", "schedule_reference",
    "derivation_source", "input_index", "score_hash"])
def test_direct_slot_path_rejects_self_consistent_wrong_frame_authority(tmp_path, monkeypatch, fault):
    main, observer, binding, _, _ = setup(tmp_path)
    frozen = execute(main, observer, "freeze_final_frame", binding)
    engine = subject.PacketParent(observer, source_owner=main)
    try:
        identifier = frozen["final_frame_record"]
        original_get = engine.ledger.get
        row = original_get(identifier, subject.FRAME)
        expected = ""
        targets = {}
        if fault in {"schedule_seed", "order_seed"}:
            key = "schedule_seed_artifact" if fault == "schedule_seed" else "article_order_seed_artifact"
            row[key] = digest("alternate deterministic but uncommitted seed")
            expected = "original_seed_binding"
        elif fault == "schedule_reference":
            row["schedule_artifact"] = digest("other self-consistent schedule")
            expected = "frame_manifest_bindings"
        elif fault in {"derivation_source", "input_index", "score_hash"}:
            manifest = engine.ledger.artifacts.read(row["frame_manifest_artifact"])
            refs = manifest["artifact_references"]
            if fault == "derivation_source":
                derivation = engine.ledger.artifacts.read(refs["derivation"])
                derivation["bindings"]["candidate_inventory_artifact"] = digest("other candidate truth")
                refs["derivation"] = engine.ledger.artifacts.put(derivation)
                expected = "frame_derivation_source_bindings"
            elif fault == "input_index":
                refs["input_index"] = engine.ledger.artifacts.put({"different": "self-consistent index"})
                expected = "frame_projection_evidence"
            else:
                scoring = engine.ledger.artifacts.read(refs["score_bands"])
                scoring["state_codes_sha256"] = digest("other state codes")
                refs["score_bands"] = engine.ledger.artifacts.put(scoring)
                expected = "frame_score_evidence"
            row["frame_manifest_artifact"] = engine.ledger.artifacts.put(manifest)
        elif fault == "protocol":
            value = original_get(row["versions"]["protocol"], "protocol")
            value["content"]["binding_sha256"] = digest("other frame authority")
            targets[row["versions"]["protocol"]] = value
            expected = "frame_protocol"
        elif fault == "intent":
            value = original_get(row["intent"], subject.INTENT)
            value["scope_sha256"] = digest("other finalized scope")
            targets[row["intent"]] = value
            expected = "frame_intent_binding"
        else:
            value = original_get(row["scope_disposition_record"], subject.SCOPE)
            value["versions"]["policy"] = digest("unrelated scope policy")
            targets[row["scope_disposition_record"]] = value
            expected = "scope_disposition_changed"
        targets[identifier] = row
        # Fault-inject only returned immutable metadata. No source/store edits;
        # this exercises the parent proof layer beyond artifact hash verification.
        monkeypatch.setattr(engine.ledger, "get", lambda ref, *args: deepcopy(targets[ref])
            if ref in targets else original_get(ref, *args))
        selected = subject.slot_binding(final_frame_record=identifier, runtime_record=digest("unused runtime"),
            quota_record=digest("unused quota"), resource_policy_record=digest("unused policy"))
        with pytest.raises(AuditError, match=expected):
            engine.execute("status", {"action": "prepare_initial_slots", "binding": selected},
                objective="Synthetic proof rejection before runtime or source access", actor="test")
        assert not engine._rows(subject.SLOTS) and not engine._rows(subject.execution.ADMISSION_KIND)
    finally:
        engine.close()
