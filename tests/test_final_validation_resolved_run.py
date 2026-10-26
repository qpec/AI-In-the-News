"""Separate metadata authority with synthetic sources/native transport only.

Small authority cases replace the already-tested upstream resolver boundary;
the final composed case uses the actual V11/Closure/Lifecycle/Native/Metadata
producers. No runtime helper, source owner or account is used outside fixtures.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_resolved_run as subject  # noqa: E402
import test_final_validation_run as original_fixture  # noqa: E402
from test_final_validation_admission import native_bytes, policy, receipt  # noqa: E402

original = subject.original


@pytest.fixture(autouse=True)
def no_real_account_or_process(monkeypatch):
    monkeypatch.setattr(original.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [original_fixture.process()]))
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


def call(engine, data):
    return engine.execute("status", data, objective="Synthetic resolved validation authority", actor="test")


class SyntheticResolved(subject.ResolvedValidationRun):
    gap = True
    _documents = original_fixture.SyntheticAuthority._documents


class Markers(original.study.Study):
    @audited_handler
    def _status(self, session, context, data):
        refs = {key: self.ledger.record(session, "synthetic_resolved_evidence", key, {"kind": key})
            for key in ("lifecycle_record", "supplement_record", "root_record")}
        bound = {**data["binding"], **refs}
        protocol = self._version_once(session, context, "protocol", "synthetic-metadata", {"method": "synthetic-only"})
        refs["metadata_resolution_record"] = self.ledger.record(session, subject.metadata.RESULT, "synthetic-only",
            {"binding": bound, "protocol_record": protocol})
        return refs


def setup(tmp_path, monkeypatch, *, gap=True):
    engine, values, registered, versions, calls = original_fixture.setup(tmp_path, monkeypatch, gap=gap)
    owner, source = engine.ledger.root, engine.source_owner
    engine.close()
    marker = Markers(owner, source_owner=source)
    try:
        refs = Research.execute(marker, "status", {"binding": values["binding"]}, objective="Synthetic upstream evidence", actor="test")
    finally:
        marker.close()
    values["binding"].update({key: refs[key] for key in subject.BINDING_FIELDS - set(values["binding"])})
    engine = SyntheticResolved(owner, source_owner=source)
    engine.gap = gap
    # Explicit synthetic observation lifetime accommodates the full audited
    # replay; expiry is tested separately, never disabled in production.
    values["resource_policy"]["quota_valid_for_seconds"] = 7200
    def replay(current, session, context, selected):
        assert current._one(subject.INTENT, optional=True) is not None  # prospective outer intent
        verified = original_fixture.SyntheticAuthority._frame_and_closure(current, session, context, subject.base_binding(selected))
        result = current.ledger.get(selected["metadata_resolution_record"], subject.metadata.RESULT)
        assert result["binding"]["lifecycle_record"] == selected["lifecycle_record"]
        saved = {**verified[4], "root_resolution_record": refs["root_record"],
            "root_projection_artifact": verified[4]["effective_projection_artifact"],
            "history_verification_record": selected["metadata_resolution_record"],
            "metadata_resolution_record": selected["metadata_resolution_record"],
            "metadata_evidence_artifact": digest("synthetic metadata proof"),
            "native_supplement_record": selected["supplement_record"], "lifecycle_evidence_record": selected["lifecycle_record"]}
        return (*verified[:4], saved, *verified[5:])
    monkeypatch.setattr(subject, "_replay_resolution", replay)
    return engine, values, registered, versions, calls


def test_prospective_authority_unchanged_slots_local_resolution_replay_and_no_source_or_dispatch(tmp_path, monkeypatch):
    engine, values, _, versions, calls = setup(tmp_path, monkeypatch)
    try:
        seeds = engine._one(original.study.SEEDS)
        ready = call(engine, values)
        authority, intent = engine._one(subject.AUTHORITY), engine._one(subject.INTENT)
        base_intent = engine._one(original.INTENT)
        protocol_sequence = engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?",
            (authority["payload"]["protocol_record"],)).fetchone()[0]
        assert intent["created_event"] < protocol_sequence < authority["created_event"] < base_intent["created_event"]
        assert ready["method"] == subject.METHOD and ready["subproducer_method"] == original.METHOD
        assert not ready["later_dispatch_authorized"] and ready["resource_census"]["fresh_potential_invocations"] == 0
        assert len(engine._rows(original.execution.SLOT_KIND)) == ready["resource_census"]["selected_slots"]
        saved = engine.ledger.get(ready["prepared_record"], original.PREPARED)
        fixed = engine.ledger.artifacts.read(saved["fixed_slot_artifact"])
        assert fixed["history_envelope"]["binding"]["history_verification_record"] == values["binding"]["metadata_resolution_record"]
        assert fixed["history_envelope"]["legacy_inventory"]["global_gap"]
        assert fixed["derived_history_inventory"]["global_gap"]
        again = call(engine, values)
        assert again["prepared_record"] == ready["prepared_record"] and len(versions) == 1
        state = call(engine, {"action": "status"})
        assert "local_resolution_missing" not in state["series_state_counts"]
        result = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert result["new_local_attempts"] == 0 and "zero_fresh_slots_preserved" in result["blockers"]
        assert not calls and not engine.source_owner.exists() and engine._one(original.study.SEEDS) == seeds
    finally:
        engine.close()


def test_actual_initial_gateway_remains_bound_to_outer_authority_and_no_retry(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=False)
    try:
        ready = call(engine, values)
        result = call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert result["new_local_attempts"] == len(calls) > 0
        assert result["execution_stop_reason"] == "fixed_tranche_processed"
        assert all(r["payload"]["status"] == "resolved" for r in engine._rows(original.execution.RESULT_KIND))
        repeated = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert repeated["new_local_attempts"] == 0
        seq = engine._one(subject.AUTHORITY)["created_event"]
        first = engine.ledger.db.execute("SELECT MIN(seq) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        assert seq < engine._one(original.series.SERIES)["created_event"] < first
    finally:
        engine.close()


@pytest.mark.parametrize("existing_kind", [original.INTENT, original.PREPARED, original.execution.SLOT_KIND,
    original.execution.MANIFEST_KIND, original.series.SERIES, original.execution.INTENT_KIND,
    original.execution.RESULT_KIND, original.series.HALT, "generic_intent"])
def test_existing_base_evidence_cannot_be_adopted_even_without_prepared_record(tmp_path, monkeypatch, existing_kind):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    # Retain the adverse evidence through an actual audited status operation.
    class Existing(SyntheticResolved):
        @audited_handler
        def _status(self, session, context, data):
            if existing_kind == "generic_intent":
                self.ledger.append(session, "model.attempt.intended", {"attempt": "synthetic orphan"})
            else:
                self.ledger.record(session, existing_kind, "synthetic-before-authority", {"synthetic": True})
            with pytest.raises(AuditError, match="existing_base_evidence_forbids_adoption"):
                self._prepare_authority(session, context, values)
            assert not self._rows(subject.AUTHORITY) and not self._rows(subject.INTENT)
            return {"blocked": True}
    engine.close()
    current = Existing(tmp_path / "validation", source_owner=tmp_path / "never-opened-source")
    try:
        assert Research.execute(current, "status", {}, objective="Synthetic prior evidence", actor="test")["blocked"]
        assert not calls
    finally:
        current.close()


@pytest.mark.parametrize("key", ["closure_record", "metadata_resolution_record", "lifecycle_record", "supplement_record", "final_frame_record"])
def test_all_upstream_ids_are_immutable_before_any_base_write(tmp_path, monkeypatch, key):
    engine, values, _, _, _ = setup(tmp_path, monkeypatch)
    original_write = engine.ledger.record
    def stop(session, kind, logical_key, value, *args, **kwargs):
        if kind == original.INTENT:
            raise AuditError("synthetic stop before base intent")
        return original_write(session, kind, logical_key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", stop)
    try:
        with pytest.raises(AuditError, match="synthetic stop before base"):
            call(engine, values)
        assert engine._one(subject.AUTHORITY) and not engine._rows(original.INTENT)
        changed = deepcopy(values)
        changed["binding"][key] = digest("changed " + key)
        with pytest.raises(AuditError, match="changed_preparation_requires_amendment"):
            call(engine, changed)
        assert not engine._rows(original.INTENT)
    finally:
        engine.close()


def test_interrupted_outer_authority_and_base_intent_resume_without_replacing_any_identity(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    original_write = engine.ledger.record
    stopped = []
    def stop(session, kind, logical_key, value, *args, **kwargs):
        if kind == subject.AUTHORITY and not stopped:
            stopped.append(True)
            raise AuditError("synthetic interruption before outer authority")
        return original_write(session, kind, logical_key, value, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", stop)
    try:
        with pytest.raises(AuditError, match="synthetic interruption"):
            call(engine, values)
        intent = engine._one(subject.INTENT)
        assert not engine._rows(original.INTENT)
        monkeypatch.setattr(engine.ledger, "record", original_write)
        ready = call(engine, values)
        assert engine._one(subject.INTENT) == intent
        assert len(engine._rows(subject.AUTHORITY)) == len(engine._rows(original.PREPARED)) == 1
        assert ready["resource_census"]["fresh_potential_invocations"] == 0 and not calls
    finally:
        engine.close()


def test_generic_intent_before_custom_projection_is_never_retried_under_new_parent(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=False)
    record = engine.ledger.record
    def interrupted(session, kind, key, content, *args, **kwargs):
        if kind == original.execution.INTENT_KIND:
            raise AuditError("synthetic crash before custom projection")
        return record(session, kind, key, content, *args, **kwargs)
    try:
        ready = call(engine, values)
        authority = engine._one(subject.AUTHORITY)
        monkeypatch.setattr(engine.ledger, "record", interrupted)
        with pytest.raises(AuditError, match="synthetic crash"):
            call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert not calls and not engine._rows(original.execution.INTENT_KIND)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 1
        held = deepcopy(engine.ledger.unresolved)
        monkeypatch.setattr(engine.ledger, "record", record)
        result = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert result["new_local_attempts"] == 0 and not calls
        assert result["retained_execution_state"]["generic_intents_without_custom_projection"] == 1
        assert engine.ledger.unresolved == held and engine._one(subject.AUTHORITY) == authority
    finally:
        engine.close()


def test_fresh_quota_does_not_renew_resolved_initial_window(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=False)
    now = datetime.now(timezone.utc)
    values["resource_policy"].update(not_before=(now - timedelta(hours=2)).isoformat(),
        admit_before=(now - timedelta(hours=1)).isoformat())
    try:
        ready = call(engine, values)
        result = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert "outside_registered_admission_window" in result["blockers"] and not calls
        assert result["initial_window_renewed"] is False
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["proof", "implementation", "protocol", "base_inputs"])
def test_status_and_resume_replay_retained_outer_authority_not_only_base_manifest(tmp_path, monkeypatch, fault):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        ready = call(engine, values)
        authority = engine._one(subject.AUTHORITY)
        get = engine.ledger.get
        def changed(identity, kind=None):
            value = get(identity, kind)
            if identity == authority["id"] and fault in {"proof", "implementation"}:
                value = deepcopy(value)
                if fault == "proof":
                    value["proof"]["source_head"] = [0, digest("foreign")]
                else:
                    value["implementation"] = {}
            elif identity == authority["payload"]["protocol_record"] and fault == "protocol":
                value = {**value, "content": {"other": True}}
            elif kind == original.INTENT and fault == "base_inputs":
                value = deepcopy(value)
                value["inputs"]["binding"]["closure_record"] = digest("other")
            return value
        monkeypatch.setattr(engine.ledger, "get", changed)
        for data in ({"action": "status"}, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()}):
            with pytest.raises(AuditError, match="authority_proof_changed|authority_implementation|authority_protocol|base_inputs_changed|final_run_prepared_binding"):
                call(engine, data)
        assert not calls
    finally:
        engine.close()


def test_public_shape_and_original_method_cannot_silently_select_resolved_authority(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        assert call(engine, {"action": "status"})["prepared"] is False
        for extra in ("complete", "allow_dispatch", "projection"):
            with pytest.raises(AuditError, match="entry_shape"):
                call(engine, {**values, extra: True})
        with pytest.raises(AuditError, match="binding_fields"):
            call(engine, {**values, "binding": subject.base_binding(values["binding"])})
        with pytest.raises(AuditError, match="resolved_run_method"):
            Research.execute(engine, "status", {"method": original.METHOD, "action": "status"}, objective="Synthetic wrong method", actor="test")
        assert not calls and not engine._rows(subject.AUTHORITY)
    finally:
        engine.close()


def test_implementation_binds_real_metadata_native_and_original_subproducer_without_frozen_edits():
    code = subject.implementation()
    for module in (original, subject.metadata, subject.metadata.supplement, subject.metadata.roots):
        path = Path(module.__file__)
        assert code[path.relative_to(original.study.ROOT).as_posix()] == hashlib.sha256(path.read_bytes()).hexdigest()
    import run_dossiers_v11 as production
    assert digest(original.study.implementation()) == "bfade8355b2d1cc9729f26108cff6dd21dd4b11f7ed55737a3e7304f4ae66f45"
    assert digest(production.implementation()) == "3f922a376ac5edfe77b346fd6ab40e5c4427cd2d4b28adce45a77d0a15c86ee9"


@pytest.mark.parametrize("key,fault", [(key, fault) for key in
    ("root_resolution_record", "lifecycle_record", "supplement_record")
    for fault in ("missing", "mismatched", "duplicate")] + [(None, None)])
def test_completed_prerequisites_precede_any_original_replay(tmp_path, monkeypatch, key, fault):
    reached = []
    def original_replay(*args):
        reached.append(True)
        raise AuditError("synthetic original replay reached")
    monkeypatch.setattr(original.FinalValidationRun, "_frame_and_closure", original_replay)
    monkeypatch.setattr(original.FinalValidationRun, "_native_provider", lambda *a: pytest.fail("No provider is permitted"))
    class Probe(subject.ResolvedValidationRun):
        @audited_handler
        def _status(self, session, context, data):
            refs = {}
            for kind, field in ((subject.metadata.roots.RESULT, "root_resolution_record"),
                (original.lifecycle.RESULT, "lifecycle_record"), (subject.metadata.supplement.RESULT, "supplement_record")):
                if field == key and fault == "missing":
                    refs[field] = digest([field, "missing"])
                    continue
                refs[field] = self.ledger.record(session, kind, "synthetic", {"synthetic": field})
                if field == key and fault == "mismatched":
                    refs[field] = digest([field, "foreign"])
                if field == key and fault == "duplicate":
                    self.ledger.record(session, kind, "synthetic-other", {"synthetic": field, "other": True})
            selected = {name: digest(name) for name in subject.BINDING_FIELDS}
            selected.update({name: refs[name] for name in ("lifecycle_record", "supplement_record")})
            selected["metadata_resolution_record"] = self.ledger.record(session, subject.metadata.RESULT, "synthetic",
                {"binding": {**selected, "root_resolution_record": refs["root_resolution_record"]}})
            expected = "synthetic original replay reached" if key is None else "single_immutable|completed_metadata_prerequisite"
            with pytest.raises(AuditError, match=expected):
                subject._replay_resolution(self, session, context, selected)
            assert not self._rows(original.INTENT) and not self._rows(subject.AUTHORITY)
            return {"original_replay_reached": bool(reached)}
    engine = Probe(tmp_path / "observer", source_owner=tmp_path / "never-opened")
    try:
        result = Research.execute(engine, "status", {}, objective="Synthetic completed prerequisite boundary", actor="test")
        assert result["original_replay_reached"] is (key is None)
        assert not engine.source_owner.exists()
    finally:
        engine.close()


def guard_desired():
    return {"method": subject.METHOD, "policy": subject.POLICY, "implementation": subject.implementation(),
        "inputs": {"binding": {key: digest(key) for key in subject.BINDING_FIELDS},
            "runtime": {}, "quota_receipt": {}, "resource_policy": {}, "series_limits": {}}}


def guard_ids(desired, actor):
    intent = digest({"kind": subject.INTENT, "key": subject.METHOD, "payload": digest(desired), "supersedes": None})
    protocol = {"content": {"method": subject.METHOD, "intent_record": intent, "binding": desired},
        "registered_by": actor, "reason": None, "branch": "main"}
    identity = digest({"kind": "protocol", "key": subject.METHOD, "payload": digest(protocol), "supersedes": None})
    return intent, identity, protocol


@pytest.mark.parametrize("order", ["protocol_before_intent", "protocol_after_authority", "valid"])
def test_registered_protocol_is_strictly_between_intent_and_authority(tmp_path, monkeypatch, order):
    # Isolate chronology from expensive upstream evidence. Actual map binding
    # and full producer replay are separately covered by the composed tests.
    monkeypatch.setattr(subject, "implementation", lambda: {"synthetic_guard": digest("guard")})
    def reached(*args):
        raise AuditError("synthetic proof replay reached")
    monkeypatch.setattr(subject, "_replay_resolution", reached)
    class Probe(subject.ResolvedValidationRun):
        @audited_handler
        def _status(self, session, context, data):
            desired = guard_desired()
            intent, protocol, body = guard_ids(desired, context.actor)
            if order == "protocol_before_intent":
                assert self.ledger.record(session, "protocol", subject.METHOD, body) == protocol
                with pytest.raises(AuditError, match="authority_chronology"):
                    self._prepare_authority(session, context, desired["inputs"])
                assert not self._rows(subject.AUTHORITY) and not self._rows(original.INTENT)
                return {"blocked_before_replay": True}
            assert self.ledger.record(session, subject.INTENT, subject.METHOD, desired) == intent
            if order == "valid":
                assert self.ledger.record(session, "protocol", subject.METHOD, body) == protocol
            self.ledger.record(session, subject.AUTHORITY, intent,
                {"method": subject.METHOD, "policy": subject.POLICY, "implementation": subject.implementation(),
                    "intent_record": intent, "intent_sha256": digest(desired), "protocol_record": protocol, "proof": {}})
            if order == "protocol_after_authority":
                assert self.ledger.record(session, "protocol", subject.METHOD, body) == protocol
            expected = "synthetic proof replay reached" if order == "valid" else "authority_chronology"
            with pytest.raises(AuditError, match=expected):
                subject.verified_frame_and_closure(self, session, context, subject.base_binding(desired["inputs"]["binding"]))
            assert not self._rows(original.INTENT)
            return {"blocked_before_replay": order != "valid"}
    engine = Probe(tmp_path / "observer", source_owner=tmp_path / "never-opened")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic protocol chronology", actor="test")["blocked_before_replay"] is (order != "valid")
    finally:
        engine.close()


@pytest.mark.parametrize("kind", ["model.attempt.completed", "model.attempt.unobserved", "model.attempt.resolved"])
@pytest.mark.parametrize("path", ["adoption", "replay"])
def test_generic_nonintent_attempt_history_cannot_acquire_new_authority(tmp_path, monkeypatch, kind, path):
    monkeypatch.setattr(subject, "implementation", lambda: {"synthetic_guard": digest("guard")})
    monkeypatch.setattr(subject, "_replay_resolution", lambda *a: pytest.fail("No proof replay is permitted"))
    class Probe(subject.ResolvedValidationRun):
        @audited_handler
        def _status(self, session, context, data):
            self.ledger.append(session, kind, {"attempt": digest("synthetic-incomplete-history")})
            desired = guard_desired()
            if path == "adoption":
                with pytest.raises(AuditError, match="existing_base_evidence_forbids_adoption"):
                    self._prepare_authority(session, context, desired["inputs"])
                assert not self._rows(subject.INTENT) and not self._rows(subject.AUTHORITY)
            else:
                intent, protocol, body = guard_ids(desired, context.actor)
                assert self.ledger.record(session, subject.INTENT, subject.METHOD, desired) == intent
                assert self.ledger.record(session, "protocol", subject.METHOD, body) == protocol
                self.ledger.record(session, subject.AUTHORITY, intent,
                    {"method": subject.METHOD, "policy": subject.POLICY, "implementation": subject.implementation(),
                        "intent_record": intent, "intent_sha256": digest(desired), "protocol_record": protocol, "proof": {}})
                with pytest.raises(AuditError, match="retrospective_authority"):
                    subject.verified_frame_and_closure(self, session, context, subject.base_binding(desired["inputs"]["binding"]))
            assert not self._rows(original.INTENT)
            return {"blocked": True}
    engine = Probe(tmp_path / "observer", source_owner=tmp_path / "never-opened")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic incomplete generic history", actor="test")["blocked"]
    finally:
        engine.close()


def test_actual_v11_metadata_resolution_to_fixed_initial_run_preserves_remaining_gaps(tmp_path, monkeypatch):
    import test_final_validation_downstream_v11 as composed
    import test_final_validation_reconciliation as reconciliation_fixture
    import test_final_validation_task_census_parent as task_fixture
    import test_final_validation_batch_history_parent as batch_fixture
    import test_final_validation_packet_parent as packet_fixture
    from test_final_validation_source import source_bytes
    monkeypatch.setattr(reconciliation_fixture, "setup", composed.v11_setup)
    main, owner, selected, _, _ = task_fixture.prepared(tmp_path, copies=True, pair=True)
    census, _ = task_fixture.run(main, owner, selected)
    batch_selected, declaration = composed.representation_scope(tmp_path, main, owner, selected, census)
    batch, _ = batch_fixture.run(main, owner, batch_selected, declaration)
    lookup, _ = batch_fixture.run(main, owner, batch_selected, declaration, "lookup")
    frame = packet_fixture.execute(main, owner, "freeze_final_frame", selected)
    def stage(cls, data):
        parent = cls(owner, source_owner=main)
        try:
            return parent.execute("status", data, objective="Synthetic completed metadata chain", actor="test")
        finally:
            parent.close()
    closed = stage(original.closure.HistoryClosureParent, {"action": "compile", "batch_history_record": batch["batch_history_record"],
        "pair_lookup_record": lookup["pair_lookup_record"]})
    life = stage(original.lifecycle.LifecycleParent, {"action": "collect", "task_census_record": census["task_census_record"]})
    native = stage(subject.metadata.supplement.NativeArtifactParent, {"action": "collect", "task_census_record": census["task_census_record"],
        "lifecycle_record": life["lifecycle_record"]})
    resolved = stage(subject.metadata.MainMetadataParent, {"action": "resolve", "closure_record": closed["closure_record"],
        "lifecycle_record": life["lifecycle_record"], "supplement_record": native["supplement_record"]})
    assert resolved["discharged_metadata_gaps"] > 0 and resolved["global_gap"]
    before = source_bytes(main)
    monkeypatch.setattr(subject.metadata.roots.closure.batch.task.parent.reconciliation.inventory,
        "open_history_inventory", lambda *a, **k: pytest.fail("Completed resolution replay must not reopen source"))
    binary = tmp_path / "synthetic-native.exe"
    binary.write_bytes(native_bytes())
    original_subprocess = original.admission.subprocess.run
    def version(command, **kwargs):
        if len(command) == 2 and command[1] == "--version":
            return SimpleNamespace(stdout="codex-cli 0.120.0\n", stderr="", returncode=0)
        return original_subprocess(command, **kwargs)
    monkeypatch.setattr(original.admission.subprocess, "run", version)
    monkeypatch.setattr(original.FinalValidationRun, "_native_provider", lambda *a: pytest.fail("Remaining history gaps forbid dispatch"))
    engine = subject.ResolvedValidationRun(owner, source_owner=main)
    try:
        seeds = engine._one(original.study.SEEDS)
        inputs = {"action": "prepare", "binding": subject.binding(final_frame_record=frame["final_frame_record"],
            closure_record=closed["closure_record"], lifecycle_record=life["lifecycle_record"], supplement_record=native["supplement_record"],
            metadata_resolution_record=resolved["metadata_resolution_record"]),
            "runtime": {"executable": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
            "quota_receipt": receipt(), "resource_policy": {**policy(allow=True), "quota_valid_for_seconds": 7200},
            "series_limits": {"maximum_cumulative_invocations": 10000, "maximum_cumulative_token_reservations": 100000000,
                "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60}}
        ready = call(engine, inputs)
        assert ready["resource_census"]["fresh_potential_invocations"] == 0
        proof = engine._one(subject.AUTHORITY)["payload"]["proof"]
        assert proof["effective_projection_artifact"] == resolved["projection_artifact"]
        assert proof["root_resolution_record"] == resolved["root_resolution_record"]
        outcome = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert outcome["new_local_attempts"] == 0 and "zero_fresh_slots_preserved" in outcome["blockers"]
        assert engine._one(original.study.SEEDS) == seeds
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended'").fetchone()
        assert source_bytes(main) == before
    finally:
        engine.close()
    engine = subject.ResolvedValidationRun(owner, source_owner=main)
    try:
        assert call(engine, {"action": "status"})["prepared_record"] == ready["prepared_record"]
    finally:
        engine.close()
    # The original parent cannot silently reinterpret this new projection.
    engine = original.FinalValidationRun(owner, source_owner=main)
    try:
        with pytest.raises(AuditError, match="version_binding_changed|history_authority_changed"):
            original_fixture.call(engine, {"action": "status"})
    finally:
        engine.close()
