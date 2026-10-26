"""Synthetic registered slot-to-account receipt checks; never a CLI/account run."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_account_admission as subject  # noqa: E402
import test_final_validation_packet_parent as fixtures  # noqa: E402
import test_final_validation_execution as execution_fixture  # noqa: E402
from test_final_validation_source import source_bytes  # noqa: E402
from test_final_validation_study import process  # noqa: E402


@pytest.fixture(autouse=True)
def synthetic_observer(monkeypatch):
    monkeypatch.setattr(subject.parent.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))


def ready(tmp_path, **resource_options):
    main, observer, binding, historical, documents = fixtures.setup(tmp_path)
    frame = fixtures.execute(main, observer, "freeze_final_frame", binding)
    evidence = fixtures.resource_evidence(tmp_path, observer, binding["preparation_binding"]["study_record"], **resource_options)
    selected = subject.parent.slot_binding(final_frame_record=frame["final_frame_record"], **evidence)
    slots = fixtures.execute(main, observer, "prepare_initial_slots", selected)
    return main, observer, binding, historical, documents, evidence, slots


def assess(engine, slot, action="assess"):
    return engine.execute("status", {"action": action, "slot_record": slot},
        objective="Synthetic exact account candidate assessment", actor="synthetic")


def forbid(*args, **kwargs):
    raise AssertionError("No source-owner observation, CLI invocation or dispatch is permitted here")


def forbid_cli(monkeypatch):
    original = subject.parent.admission.subprocess.run
    def only_identity(command, **kwargs):
        assert command[0] == "git", "No CLI/account probe is permitted"
        return original(command, **kwargs)
    monkeypatch.setattr(subject.parent.admission.subprocess, "run", only_identity)


def test_actual_registered_slot_replay_receipt_and_reopen_without_source_or_dispatch(tmp_path, monkeypatch):
    main, observer, binding, historical, documents, evidence, slots = ready(tmp_path)
    before = {str(p): source_bytes(Path(p)) for p in (main, historical["source_owner"])}
    monkeypatch.setattr(subject.parent.study.WindowsProcessObserver, "_capture", staticmethod(forbid))
    forbid_cli(monkeypatch)
    monkeypatch.setattr(subject.parent.execution, "Execution", forbid)
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        saved_slots = engine.ledger.get(slots["slot_record"], subject.parent.SLOTS)
        saved_assessment = engine.ledger.get(slots["resource_assessment_record"], subject.parent.admission.ASSESSMENT)
        original_seeds = engine._one(subject.parent.study.SEEDS)
        first = assess(engine, slots["slot_record"])
        receipt = engine.ledger.get(first["receipt_record"], subject.RESULT)
        assert receipt["upstream_packet_authority_verified_by_exact_replay"]
        assert not receipt["dispatch_authorized"] and not receipt["execution_manifest_registered_here"]
        assert subject.AUTHORITY_PLACEHOLDER == receipt["obsolete_placeholder_discharged"]
        assert subject.AUTHORITY_PLACEHOLDER not in receipt["blockers"]
        assert receipt["historical_specific_blockers_preserved"] == ["zero_fresh_slots_preserved"]
        assert set(receipt["blockers"]) == {"zero_fresh_slots_preserved", "retained_reference_history_scope_incomplete",
            "account_execution_operation_not_registered"}
        assert receipt["account_dollar_cost"] is None
        assert receipt["current_resource_conditions"]["remaining_tokens"] is None
        assert receipt["current_resource_conditions"]["remaining_invocations"] is None
        assert not receipt["current_resource_conditions"]["generation_token_cap_enforced"]
        assert receipt["configured_route"] == {"model": "gpt-6-astra", "reasoning_effort": "medium",
            "fast": False, "route": "codex_cli_account_only", "observed_serving_model": None,
            "account_authentication_observed": False}
        manifest = engine.ledger.artifacts.read(receipt["verified_candidate_manifest_artifact"])
        assert manifest["manifest_sha256"] == receipt["execution_manifest_sha256"]
        assert 0 < len(manifest["prefix"]["primary_ranks"]) <= 40
        assert len(manifest["tasks"]) <= manifest["prefix"]["reserved_invocations"] <= 60
        assert all(t["disposition"] == "unavailable" for t in manifest["tasks"])
        assert manifest["planned_new_invocations"] == manifest["planned_token_reservations"] == 0
        assert receipt["human_instruction_evidence_artifact"] == manifest["scope"]["user_instruction_sha256"]
        assert receipt["resource_census"] == slots["resource_census"]
        assert not any(engine._rows(k) for k in receipt["existing_execution_records"])
        assert not receipt["existing_execution_state"]["requires_coordinator_reconciliation"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert engine.ledger.get(slots["slot_record"], subject.parent.SLOTS) == saved_slots
        assert engine.ledger.get(slots["resource_assessment_record"], subject.parent.admission.ASSESSMENT) == saved_assessment
        assert engine._one(subject.parent.study.SEEDS) == original_seeds
        intent = engine._one(subject.INTENT)
        protocol = engine.ledger.get(receipt["protocol_record"], "protocol")
        assert protocol["content"] == {"method": subject.METHOD, "intent_record": intent["id"], "binding": intent["payload"]}
        assert len(engine._rows(subject.RESULT)) == 1
        status = assess(engine, slots["slot_record"], "status")
        assert status["exact_binding_registered"] and not status["current_resource_conditions_recomputed"]
        assert len(engine._rows(subject.RESULT)) == 1
        assert all(document["body"] not in canonical(first) for document in documents)
    finally:
        engine.close()
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        again = assess(engine, slots["slot_record"])
        assert again["receipt_record"] != first["receipt_record"]
        assert again["execution_manifest_sha256"] == first["execution_manifest_sha256"]
        assert again["verified_candidate_manifest_artifact"] == first["verified_candidate_manifest_artifact"]
        assert len(engine._rows(subject.INTENT)) == 1 and len(engine._rows(subject.RESULT)) == 2
        assert engine._one(subject.parent.study.SEEDS) == original_seeds
    finally:
        engine.close()
    assert all(source_bytes(Path(path)) == raw for path, raw in before.items())


@pytest.mark.parametrize("mode,expected", [
    ("unknown_block", "quota_unit_capacity_unavailable_policy_blocks"),
    ("unknown_allowed", None),
    ("exhausted_allowed", "observed_account_limit_exhausted"),
    ("known_insufficient_calls", "known_quota_insufficient_for_frozen_tranche"),
    ("known_insufficient_tokens", "known_quota_insufficient_for_frozen_tranche"),
    ("expired_quota", "quota_observation_stale"),
    ("future_quota", "quota_observation_stale"),
    ("expired_window", "outside_registered_admission_window"),
    ("future_window", "outside_registered_admission_window"),
])
def test_fresh_candidate_resource_rules_do_not_convert_percentages_or_invent_authority(mode, expected):
    limits, now = execution_fixture.resources(), execution_fixture.NOW
    observation = {"percentage_observation": {"windows": [{"window": "primary", "used_percent": 20,
        "remaining_percent": 80, "resets_at": None}], "known_exhausted": False, "shape": "percentage_only"}}
    if mode.startswith("unknown") or mode == "exhausted_allowed":
        limits["quota"].update(state="unavailable", remaining_invocations=None, remaining_tokens=None)
        if mode != "unknown_block":
            limits["unavailable_quota_policy"] = "allow_bounded_registered"
    if mode == "exhausted_allowed":
        observation["percentage_observation"].update(known_exhausted=True, windows=[])
    elif mode == "known_insufficient_calls":
        limits["quota"]["remaining_invocations"] = 0
    elif mode == "known_insufficient_tokens":
        limits["quota"]["remaining_tokens"] = 0
    elif mode == "expired_quota":
        limits["quota"]["valid_until"] = now.isoformat()
    elif mode == "future_quota":
        limits["quota"]["observed_at"] = (now + timedelta(minutes=1)).isoformat()
    elif mode == "expired_window":
        limits["admit_before"] = now.isoformat()
    elif mode == "future_window":
        limits["not_before"] = (now + timedelta(minutes=1)).isoformat()
    manifest = execution_fixture.manifest(limits=limits)
    value = subject.resource_conditions(manifest, observation, now=now)
    assert value["blockers"] == ([expected] if expected else [])
    assert value["account_dollar_cost"] is None and value["percentage_is_not_token_or_invocation_capacity"]
    assert not value["generation_token_cap_enforced"] and not value["timeout_guarantees_remote_cancellation"]
    if mode.startswith("unknown") or mode == "exhausted_allowed":
        assert value["remaining_invocations"] is value["remaining_tokens"] is None


@pytest.mark.parametrize("payload", [
    {"action": "run", "slot_record": digest("slot")},
    {"action": "assess", "slot_record": digest("slot"), "allow_account_execution": True},
    {"action": "assess", "slot_record": digest("slot"), "complete": True},
    {"action": "assess", "slot_record": digest("slot"), "manifest": {}},
    {"action": "assess", "slot_record": digest("slot"), "quota_record": digest("replacement")},
])
def test_caller_permission_completeness_manifest_or_receipt_cannot_replace_registered_evidence(tmp_path, payload):
    engine = subject.AccountAdmissionParent(tmp_path / "observer", source_owner=tmp_path / "never-opened-source")
    try:
        with pytest.raises(AuditError, match="offline_operation"):
            engine.execute("status", payload, objective="Synthetic rejected override", actor="synthetic")
        assert not engine._rows(subject.INTENT)
    finally:
        engine.close()
    assert not (tmp_path / "never-opened-source").exists()


@pytest.mark.parametrize("fault,reason", [
    ("exhausted", "observed_account_limit_exhausted"),
    ("unknown", "quota_unit_capacity_unavailable_policy_blocks"),
    ("stale", "quota_observation_stale"),
])
def test_actual_bound_resource_failure_is_not_removed_with_obsolete_placeholder(tmp_path, fault, reason):
    main, observer, _, _, _, _, slots = ready(tmp_path, used=100 if fault == "exhausted" else 20,
        allow=fault != "unknown", stale=fault == "stale")
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        result = assess(engine, slots["slot_record"])
        receipt = engine.ledger.get(result["receipt_record"], subject.RESULT)
        assert reason in receipt["historical_specific_blockers_preserved"]
        assert reason in receipt["current_resource_conditions"]["blockers"]
        assert reason in receipt["blockers"] and not receipt["dispatch_authorized"]
        assert subject.AUTHORITY_PLACEHOLDER not in receipt["blockers"]
        assert not engine._rows(subject.parent.execution.MANIFEST_KIND)
    finally:
        engine.close()


def test_direct_receipt_rejects_changed_protected_slot_resource_and_authority_proofs(tmp_path, monkeypatch):
    main, observer, _, _, _, evidence, slots = ready(tmp_path)
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        saved = engine.ledger.get(slots["slot_record"], subject.parent.SLOTS)
        cases = [
            (saved["slot_intent"], subject.parent.SLOT_INTENT, lambda v: v.update(schedule_digest=digest("other schedule"))),
            (saved["slot_admission_record"], subject.parent.execution.ADMISSION_KIND,
                lambda v: v.update(source_snapshot=digest("other source"))),
            (saved["slot_admission_record"], subject.parent.execution.ADMISSION_KIND,
                lambda v: v.update(slot_catalog_sha256=digest("other pair ranks"))),
            (evidence["runtime_record"], subject.parent.admission.RUNTIME,
                lambda v: v.update(configured_model="gpt-6-luna")),
            (evidence["quota_record"], subject.parent.admission.QUOTA,
                lambda v: v.update(remaining_tokens=100000)),
            (evidence["resource_policy_record"], subject.parent.admission.POLICY,
                lambda v: v.update(instruction_evidence_artifact=digest("other instruction"))),
            (evidence["resource_policy_record"], subject.parent.admission.POLICY,
                lambda v: v["policy"].update(maximum_invocations=61)),
            (saved["resource_assessment_record"], subject.parent.admission.ASSESSMENT,
                lambda v: v.update(fixed_slots=v["fixed_slots"] + 1)),
            (saved["resource_assessment_record"], subject.parent.admission.ASSESSMENT,
                lambda v: v.update(blockers=[])),
        ]
        original_get = engine.ledger.get
        for identifier, kind, change in cases:
            def changed(record, record_kind=None):
                value = original_get(record, record_kind)
                if record == identifier and record_kind == kind:
                    value = deepcopy(value)
                    change(value)
                return value
            with monkeypatch.context() as scoped:
                scoped.setattr(engine.ledger, "get", changed)
                with pytest.raises(AuditError):
                    assess(engine, slots["slot_record"])
            assert not engine._rows(subject.RESULT)
        # Exact artifact replay also binds task order, original source bindings,
        # reference inventory and every retained candidate field.
        original_read = engine.ledger.artifacts.read
        references = [saved["prepared_initial_artifact"], saved["candidate_execution_manifest_artifact"],
            saved["history_inventory_artifact"]]
        for reference in references:
            def changed_artifact(identifier):
                value = original_read(identifier)
                if identifier == reference:
                    value = deepcopy(value)
                    if identifier == saved["history_inventory_artifact"]:
                        value.update(global_gap=False, complete=True)
                    else:
                        value["tasks"][0]["pair_rank"] += 1
                return value
            with monkeypatch.context() as scoped:
                scoped.setattr(engine.ledger.artifacts, "read", changed_artifact)
                with pytest.raises(AuditError):
                    assess(engine, slots["slot_record"])
            assert not engine._rows(subject.RESULT)
        assert assess(engine, slots["slot_record"])["new_model_calls"] == 0
    finally:
        engine.close()


def test_registered_intent_precedes_replay_partial_resume_and_code_binding(tmp_path, monkeypatch):
    main, observer, _, _, _, _, slots = ready(tmp_path)
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    original = subject.AccountAdmissionParent._replay_slots
    def interrupted(self, session, context, chain):
        intended = self._one(subject.INTENT)
        assert intended and not self._rows(subject.RESULT)
        assert any(row["payload"]["content"].get("intent_record") == intended["id"] for row in self._rows("protocol"))
        raise AuditError("synthetic-interruption-before-proof-replay")
    try:
        seeds = engine._one(subject.parent.study.SEEDS)
        with monkeypatch.context() as scoped:
            scoped.setattr(subject.AccountAdmissionParent, "_replay_slots", interrupted)
            with pytest.raises(AuditError, match="synthetic-interruption"):
                assess(engine, slots["slot_record"])
        assert len(engine._rows(subject.INTENT)) == 1 and not engine._rows(subject.RESULT)
        assert subject.AccountAdmissionParent._replay_slots is original
    finally:
        engine.close()
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        current = subject.implementation()
        with monkeypatch.context() as scoped:
            scoped.setattr(subject, "implementation", lambda: {**current, "synthetic-changed-code": digest("changed")})
            with pytest.raises(AuditError, match="changed_binding_requires_amendment"):
                assess(engine, slots["slot_record"])
        assert not engine._rows(subject.RESULT)
        result = assess(engine, slots["slot_record"])
        assert not result["dispatch_authorized"] and len(engine._rows(subject.INTENT)) == 1
        assert engine._one(subject.parent.study.SEEDS) == seeds
    finally:
        engine.close()


def test_stop_existing_execution_and_binary_drift_never_create_new_admission(tmp_path, monkeypatch):
    main, observer, _, _, _, _, slots = ready(tmp_path)
    class ExistingState(subject.AccountAdmissionParent):
        @audited_handler
        def _status(self, session, context, data):
            manifest = self.ledger.artifacts.read(slots["candidate_execution_manifest_artifact"])
            self.ledger.append(session, "model.attempt.intended", {"attempt": "synthetic-generic-orphan",
                "validation_scope": manifest["scope_sha256"], "task_key": manifest["tasks"][0]["logical_task_id"],
                "request": self.ledger.artifacts.put({"synthetic": True}),
                "dispatch": self.ledger.artifacts.put({"synthetic_dispatch": True})})
            return {"synthetic_fixture_only": True}
    engine = ExistingState(observer, source_owner=main)
    try:
        assess(engine, slots["slot_record"])
    finally:
        engine.close()
    (observer / "STOP").write_text("Synthetic existing stop", encoding="utf-8")
    engine = subject.AccountAdmissionParent(observer, source_owner=main)
    try:
        forbid_cli(monkeypatch)
        value = assess(engine, slots["slot_record"])
        assert {"user_stop", "existing_execution_state_requires_coordinator_reconciliation"} <= set(value["blockers"])
        assert not engine._rows(subject.parent.execution.MANIFEST_KIND)
        assert not engine._rows(subject.parent.execution.INTENT_KIND)
        state = engine.ledger.get(value["receipt_record"], subject.RESULT)["existing_execution_state"]
        assert state["generic_intended_events"] == state["generic_intents_without_custom_projection"] == 1
        assert state["candidate_scope_intended_events"] == state["candidate_logical_identity_unverified"] == 1
        assert state["cached_unresolved_attempts"] == state["intent_events_without_later_completion_event"] == 1
        before = len(engine._rows(subject.RESULT))
        (tmp_path / "synthetic-native.exe").write_bytes(b"changed local binary")
        with pytest.raises(AuditError, match="native|binary"):
            assess(engine, slots["slot_record"])
        assert len(engine._rows(subject.RESULT)) == before
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["generic_before_cache", "result_before_completion", "ambiguous_scope", "completed_event_only"])
def test_durable_generic_crash_boundaries_cannot_look_clean(tmp_path, fault):
    manifest = execution_fixture.manifest()
    class Census(Research):
        def _rows(self, kind):
            return [{"id": r[0], "payload": self.ledger.get(r[0], kind)}
                for r in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (kind,))]
        @audited_handler
        def _status(self, session, context, data):
            task = manifest["tasks"][0]
            intended = {"attempt": "synthetic-durable-attempt", "validation_scope": manifest["scope_sha256"],
                "logical_task_id": task["logical_task_id"], "task_key": task["logical_task_id"],
                "task_sha256": digest(task), "pair_rank": task["pair_rank"], "role": task["role"],
                "number": 1, "reservation_tokens": task["reservation_tokens"],
                "request": self.ledger.artifacts.put({"synthetic_request": True}),
                "dispatch": self.ledger.artifacts.put({"synthetic_dispatch": True})}
            if fault == "ambiguous_scope":
                intended.pop("validation_scope")
            self.ledger.append(session, "model.attempt.intended", intended)
            # Deliberately do not populate mutable ledger.unresolved here.
            if fault == "result_before_completion":
                self.ledger.record(session, subject.parent.execution.INTENT_KIND, "synthetic", intended)
                self.ledger.record(session, subject.parent.execution.RESULT_KIND, "synthetic",
                    {"attempt": intended["attempt"], "synthetic": True})
            elif fault == "completed_event_only":
                self.ledger.append(session, "model.attempt.completed", {"attempt": intended["attempt"],
                    "response": self.ledger.artifacts.put({"synthetic_response": True})})
            return subject.retained_execution_state(self, session, manifest)
    engine = Census(tmp_path / "synthetic-census")
    try:
        state = engine.execute("status", {}, objective="Synthetic crash-boundary census", actor="synthetic")
        assert state["requires_coordinator_reconciliation"] and not state["settlement_or_usage_inferred"]
        assert state["generic_intended_events"] == 1
        assert state["cached_unresolved_attempts"] == 0
        if fault == "completed_event_only":
            assert state["generic_completed_events"] == 1
            assert state["intent_events_without_later_completion_event"] == 0
        else:
            assert state["intent_events_without_later_completion_event"] == 1
            assert state["durable_uncompleted_attempts_absent_from_cache"] == 1
        if fault == "ambiguous_scope":
            assert state["other_or_missing_scope_intended_events"] == 1
        else:
            assert state["candidate_logical_identity_matches"] == 1
        assert state["generic_intents_without_custom_projection"] == (0 if fault == "result_before_completion" else 1)
    finally:
        engine.close()
