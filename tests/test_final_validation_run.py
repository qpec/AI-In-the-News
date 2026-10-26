"""Concrete audited account orchestration with synthetic sources/native runner only.

SyntheticAuthority deliberately replaces ONLY source/frame/closure derivation;
the original Study, seeds, resource observation, fixed-slot producer, manifest,
series, PairProvider, gateway, intent ledger and execution remain real. A separate
composed V11 test below exercises the actual retained upstream authority.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import subprocess
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_run as subject  # noqa: E402
import final_validation_fixed_slots as fixed  # noqa: E402
from test_final_validation_admission import native_bytes, policy, receipt  # noqa: E402
from test_final_validation_packets import case  # noqa: E402
from test_final_validation_history_closure import minimal  # noqa: E402
from test_final_validation_provider import events, stream  # noqa: E402
from test_final_validation_study import payload as initialization, process  # noqa: E402


class SyntheticAuthority(subject.FinalValidationRun):
    gap = False

    def _frame_and_closure(self, session, context, selected):
        registered = self._registration()
        seeds = self.ledger.get(registered["payload"]["seed_record"], subject.study.SEEDS)
        counter = fixed.original.load_token_counter(evidence_record=digest("synthetic-frame-counter"),
            expected_identity={"encoding": "cl100k_base", "library": "tiktoken", "version": importlib.metadata.version("tiktoken")})
        frame, _, documents, legacy = case(counter, 4)
        schedule = fixed.schedules.assemble_schedule(frame,
            seeds=self.ledger.artifacts.read(seeds["schedule_seed_artifact"])["seeds"],
            seed_binding={"record": registered["payload"]["seed_record"], "artifact": seeds["schedule_seed_artifact"]})
        args = list(minimal())
        args[0] = frame.index
        owner = digest(str(self.source_owner))
        old_owner = next(iter(args[1]))
        args[1] = {owner: args[1][old_owner]}
        args[1][owner]["scope"]["source_owner"] = str(self.source_owner)
        args[2][0]["owner_sha256"] = [owner]
        args[3] = {owner: args[3][old_owner]}
        args[3][owner][0]["owner_sha256"] = owner
        projection = subject.closure._compile(*args)
        if self.gap:
            projection["unresolved_regions"].append({"reason_code": "synthetic_unlocalized_history", "owner_sha256": owner,
                "evidence_sha256": digest("synthetic gap"), "affected_input_sha256": None, "role": None})
            projection["scoped_certificate"].update(complete=False, global_gap=True)
        projection_ref = self.ledger.artifacts.put(projection)
        inventory = deepcopy(legacy["history_inventory"])
        inventory.update(complete=False, global_gap=True)
        registry = {"owners": [], "declared_gaps": []}
        reconciled = {"registry_artifact": self.ledger.artifacts.put(registry), "artifacts": {
            "pair_history_records": self.ledger.artifacts.put([]), "pair_history_inventory": self.ledger.artifacts.put(inventory)}}
        snapshot = {"method": subject.lineage.v11_snapshot.METHOD, "source_bindings": {
            "source_head": projection["scoped_certificate"]["source_heads"][owner]}}
        snapshot_artifact = self.ledger.artifacts.put(snapshot)
        snapshot_ref = self._one("synthetic_verified_snapshot", optional=True)
        snapshot_id = snapshot_ref["id"] if snapshot_ref else self.ledger.record(session, "synthetic_verified_snapshot", "exact", snapshot)
        selected_snapshot = {"snapshot_record": snapshot_id, "snapshot_artifact": snapshot_artifact}
        frame_value = {"binding": {"preparation_binding": {"snapshot_binding": selected_snapshot,
            "study_record": registered["id"], "seed_record": registered["payload"]["seed_record"]}},
            **{k: seeds[k] for k in ("schedule_seed_artifact", "article_order_seed_artifact")}}
        saved = {"binding": {"catalog_artifact": digest("synthetic complete catalog")},
            "projection_artifact": projection_ref, "protocol_record": self._version_once(session, context, "protocol",
                "synthetic-history", {"method": "synthetic-history", "rules": "Synthetic fixture authority only, never an actual history assertion."})}
        saved.update(original_closure_sha256=digest(saved), effective_projection_artifact=projection_ref,
            history_verification_record=selected["closure_record"], root_resolution_evidence_artifact=projection_ref,
            lifecycle_evidence_record=None)
        for name, identifier in selected.items():
            if not self.ledger.db.execute("SELECT 1 FROM records WHERE id=?", (identifier,)).fetchone():
                # The exact hash references are actual synthetic records created
                # in setup; a changed requested identity is never accepted.
                raise AuditError("synthetic_unknown_selected_" + name)
        self.documents = documents
        chain = (snapshot, frame.index, {"binding": {"seed_record": registered["payload"]["seed_record"]}},
            reconciled, registry, {})
        return frame_value, chain, frame, schedule, saved, projection, registered

    def _documents(self, snapshot, index):
        return deepcopy(self.documents)


@pytest.fixture(autouse=True)
def no_real_process_or_credentials(monkeypatch):
    monkeypatch.setattr(subject.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


def call(engine, data):
    return engine.execute("status", data, objective="Synthetic fixed validation run", actor="test")


def setup(tmp_path, monkeypatch, *, gap=False, allow=True):
    source, owner = tmp_path / "never-opened-source", tmp_path / "validation"
    initial = subject.study.Study(owner, source_owner=source)
    try:
        registered = initial.execute("status", initialization(), objective="Synthetic initialized Study", actor="test")
    finally:
        initial.close()
    binary = tmp_path / "synthetic-native.exe"
    binary.write_bytes(native_bytes())
    class Calls(list):
        timeout = False
        stop_after_first = False
    version_calls, model_calls = [], Calls()
    original_subprocess = subject.admission.subprocess.run
    def version(command, **kwargs):
        if len(command) == 2 and command[1] == "--version":
            version_calls.append(command)
            return SimpleNamespace(stdout="codex-cli 0.120.0\n", stderr="", returncode=0)
        return original_subprocess(command, **kwargs)
    monkeypatch.setattr(subject.admission.subprocess, "run", version)
    native_init = subject.provider.PairProvider.__init__
    def initialize_provider(instance, *args, **kwargs):
        # Capture SQL-backed registration in the audited caller thread. The
        # gateway worker must never use its caller's SQLite connection.
        registered_series = kwargs["research"]._rows(subject.series.SERIES)
        def native_runner(command, **options):
            model_calls.append((command, options))
            assert len(registered_series) == 1
            assert instance.research.ledger.unresolved  # exact durable intent is checked by PairProvider itself
            assert 'forced_login_method="chatgpt"' in command
            if model_calls.timeout:
                raise subprocess.TimeoutExpired(command, 1)
            if model_calls.stop_after_first:
                (instance.research.ledger.root / "STOP").write_text("Synthetic stop after one request", encoding="utf-8")
            return SimpleNamespace(stdout=stream(events()), stderr="", returncode=0)
        return native_init(instance, *args, **kwargs, runner=native_runner)
    monkeypatch.setattr(subject.provider.PairProvider, "__init__", initialize_provider)
    engine = SyntheticAuthority(owner, source_owner=source)
    engine.gap = gap
    # Create concrete hash references inside a genuine audited operation.
    from newsresearch.runtime import Research, audited_handler
    class Marker(subject.study.Study):
        @audited_handler
        def _status(self, session, context, data):
            return {key: self.ledger.record(session, "synthetic_verified_upstream", key, {"kind": key})
                for key in ("final_frame_record", "closure_record")}
    engine.close()
    markers = Marker(owner, source_owner=source)
    try:
        selected = Research.execute(markers, "status", {}, objective="Synthetic authority marker", actor="test")
    finally:
        markers.close()
    engine = SyntheticAuthority(owner, source_owner=source)
    engine.gap = gap
    values = {"action": "prepare", "binding": selected,
        "runtime": {"executable": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
        "quota_receipt": receipt(), "resource_policy": policy(allow=allow),
        "series_limits": {"maximum_cumulative_invocations": 10000, "maximum_cumulative_token_reservations": 100000000,
            "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60}}
    return engine, values, registered, version_calls, model_calls


def test_actual_initial_manifest_series_gateway_run_status_and_no_retry_resume(tmp_path, monkeypatch):
    engine, values, registration, versions, calls = setup(tmp_path, monkeypatch)
    try:
        seeds = engine._one(subject.study.SEEDS)
        ready = call(engine, values)
        assert ready["resource_census"]["fresh_potential_invocations"] > 0
        assert len(versions) == 1 and not calls
        assert len(engine._rows(subject.series.SERIES)) == len(engine._rows(subject.execution.MANIFEST_KIND)) == 1
        again = call(engine, values)
        assert again["prepared_record"] == ready["prepared_record"] and len(versions) == 1
        result = call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert result["new_local_attempts"] == len(calls) > 0 and not result["blockers"]
        assert result["execution_stop_reason"] == "fixed_tranche_processed"
        assert all(row["payload"]["status"] == "resolved" and not row["payload"]["unknown_outcome"]
            for row in engine._rows(subject.execution.RESULT_KIND))
        assert result["execution_report_record"] and result["account_dollar_cost"] is None
        assert not result["initial_window_renewed"] and not result["statistical_look"]
        assert engine._one(subject.study.SEEDS) == seeds
        state = call(engine, {"action": "status"})
        assert state["existing_execution_state"]["generic_intended_events"] == len(calls)
        previous = len(calls)
        resumed = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert resumed["new_local_attempts"] == 0 and len(calls) == previous
        with pytest.raises(AuditError, match="existing_attempts_require_resume"):
            call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert not any(d["body"] in canonical(result) for d in engine.documents)
        assert not engine.source_owner.exists()
        assert engine.ledger.verify()["status"] == "verified"
    finally:
        engine.close()


@pytest.mark.parametrize("mode,expected", [("gap", "zero_fresh_slots_preserved"),
    ("quota", "observed_account_limit_exhausted"), ("stale", "fresh_quota_observation_required"),
    ("unknown", "quota_unit_capacity_unavailable_policy_blocks"), ("stop", "user_stop")])
def test_history_and_fresh_resource_blockers_never_dispatch_or_replace_slots(tmp_path, monkeypatch, mode, expected):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=mode == "gap", allow=mode != "unknown")
    try:
        ready = call(engine, values)
        value = engine.ledger.get(ready["prepared_record"], subject.PREPARED)
        saved = engine.ledger.get(value["manifest_record"], subject.execution.MANIFEST_KIND)
        if mode == "stop":
            (engine.ledger.root / "STOP").write_text("Synthetic user stop", encoding="utf-8")
        observed = receipt(used=100 if mode == "quota" else 20, stale=mode == "stale")
        result = call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": observed})
        assert expected in result["blockers"] and not calls and result["new_local_attempts"] == 0
        assert not engine._rows(subject.execution.INTENT_KIND)
        assert engine.ledger.get(value["manifest_record"], subject.execution.MANIFEST_KIND) == saved
        assert len(saved["manifest"]["tasks"]) == ready["resource_census"]["selected_slots"]
        if mode == "gap":
            assert len(engine._rows(subject.execution.SLOT_KIND)) == len(saved["manifest"]["tasks"])
            states = call(engine, {"action": "status"})["series_state_counts"]
            assert "local_resolution_missing" not in states and "not_attempted" not in states
    finally:
        engine.close()


def test_fresh_quota_receipt_cannot_renew_original_expired_window(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        now = datetime.now(timezone.utc)
        values["resource_policy"].update(not_before=(now - timedelta(hours=2)).isoformat(),
            admit_before=(now - timedelta(hours=1)).isoformat())
        ready = call(engine, values)
        result = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert "outside_registered_admission_window" in result["blockers"] and not calls
    finally:
        engine.close()


def test_partial_nonfresh_local_record_creation_replays_without_provider_or_new_manifest(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=True)
    original = engine.ledger.record
    local = []
    def interrupted(session, kind, key, content, *args, **kwargs):
        if kind == subject.execution.SLOT_KIND:
            local.append(key)
            if len(local) == 2:
                raise AuditError("synthetic interruption before second local result")
        return original(session, kind, key, content, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", interrupted)
    try:
        with pytest.raises(AuditError, match="synthetic interruption"):
            call(engine, values)
        first = engine._rows(subject.execution.SLOT_KIND)
        assert len(first) == 1 and not engine._rows(subject.PREPARED)
        monkeypatch.setattr(engine.ledger, "record", original)
        ready = call(engine, values)
        assert not calls and len(engine._rows(subject.execution.MANIFEST_KIND)) == 1
        assert engine._rows(subject.execution.SLOT_KIND)[0] == first[0]
        status = call(engine, {"action": "status"})
        assert "local_resolution_missing" not in status["series_state_counts"]
        assert ready["prepared_record"] == status["prepared_record"]
    finally:
        engine.close()


def test_foreign_local_resolution_is_not_hidden_by_zero_fresh_gate(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch, gap=True)
    original = engine.ledger.record
    inserted = []
    def foreign(session, kind, key, content, *args, **kwargs):
        result = original(session, kind, key, content, *args, **kwargs)
        if kind == subject.execution.SLOT_KIND and not inserted:
            wrong = deepcopy(content)
            wrong["logical_task_id"] = digest("foreign immutable slot")
            inserted.append(original(session, kind, wrong["logical_task_id"], wrong))
        return result
    monkeypatch.setattr(engine.ledger, "record", foreign)
    try:
        with pytest.raises(AuditError, match="foreign_or_fresh_local_resolution"):
            call(engine, values)
        assert not engine._rows(subject.PREPARED)
        assert not calls
    finally:
        engine.close()


def test_unknown_gateway_outcome_is_retained_and_never_retried(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        ready = call(engine, values)
        calls.timeout = True
        first = call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert first["new_local_attempts"] == len(calls) == 1
        assert engine.ledger.unresolved
        held = deepcopy(engine.ledger.unresolved)
        second = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert second["new_local_attempts"] == 0 and len(calls) == 1
        assert engine.ledger.unresolved == held
    finally:
        engine.close()


def test_generic_intent_before_custom_projection_crash_resumes_without_dispatch(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    original = engine.ledger.record
    def interrupted(session, kind, key, content, *args, **kwargs):
        if kind == subject.execution.INTENT_KIND:
            raise AuditError("synthetic crash before custom attempt projection")
        return original(session, kind, key, content, *args, **kwargs)
    try:
        ready = call(engine, values)
        monkeypatch.setattr(engine.ledger, "record", interrupted)
        with pytest.raises(AuditError, match="synthetic crash"):
            call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert not calls and not engine._rows(subject.execution.INTENT_KIND)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 1
        held = deepcopy(engine.ledger.unresolved)
        monkeypatch.setattr(engine.ledger, "record", original)
        resumed = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert resumed["new_local_attempts"] == 0 and not calls
        assert resumed["retained_execution_state"]["generic_intents_without_custom_projection"] == 1
        assert engine.ledger.unresolved == held
        assert not engine._rows(subject.execution.INTENT_KIND)
    finally:
        engine.close()


def test_user_stop_between_requests_preserves_untouched_tasks_for_same_window_resume(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        ready = call(engine, values)
        calls.stop_after_first = True
        first = call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert first["new_local_attempts"] == len(calls) == 1
        first_intents = deepcopy(engine._rows(subject.execution.INTENT_KIND))
        calls.stop_after_first = False
        (engine.ledger.root / "STOP").unlink()
        second = call(engine, {"action": "resume", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert second["new_local_attempts"] > 0
        assert engine._rows(subject.execution.INTENT_KIND)[0] == first_intents[0]
        assert len({row["payload"]["logical_task_id"] for row in engine._rows(subject.execution.INTENT_KIND)}) == len(calls)
    finally:
        engine.close()


@pytest.mark.parametrize("field", ["binding", "resource_policy", "series_limits", "quota_receipt"])
def test_preparation_cannot_reset_or_rebind_after_registration(tmp_path, monkeypatch, field):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        call(engine, values)
        altered = deepcopy(values)
        if field == "binding":
            altered[field]["closure_record"] = digest("different closure")
        elif field == "resource_policy":
            altered[field]["maximum_invocations"] -= 1
        elif field == "series_limits":
            altered[field]["maximum_cumulative_invocations"] += 1
        else:
            altered[field] = receipt()
        with pytest.raises(AuditError, match="changed_preparation_requires_amendment"):
            call(engine, altered)
        assert not calls
    finally:
        engine.close()


def test_run_rehashes_exact_native_binary_before_provider_construction(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        ready = call(engine, values)
        Path(values["runtime"]["executable"]).write_bytes(native_bytes() + b"changed")
        with pytest.raises(AuditError, match="executable_hash_changed"):
            call(engine, {"action": "run-initial", "prepared_record": ready["prepared_record"], "quota_receipt": receipt()})
        assert not calls
    finally:
        engine.close()


def test_unknown_public_operation_or_injected_provider_is_rejected_before_research(tmp_path, monkeypatch):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    try:
        with pytest.raises(AuditError, match="entry_shape"):
            call(engine, {"action": "run-initial", "prepared_record": digest("anything"), "quota_receipt": receipt(), "provider": "caller"})
        assert not calls and not engine._rows(subject.INTENT)
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["resource_census", "fixed_slot_artifact", "manifest_sha256", "series_record"])
def test_retained_preparation_substitution_is_rejected_on_real_loader(tmp_path, monkeypatch, fault):
    engine, values, _, _, calls = setup(tmp_path, monkeypatch)
    original = engine.ledger.record
    def changed(session, kind, key, content, *args, **kwargs):
        if kind == subject.PREPARED:
            content = deepcopy(content)
            content[fault] = {} if fault == "resource_census" else digest(["wrong", fault])
        return original(session, kind, key, content, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", changed)
    try:
        call(engine, values)
        with pytest.raises(AuditError):
            call(engine, {"action": "status"})
        assert not calls
    finally:
        engine.close()


def test_status_cli_is_source_free_and_never_invents_quota_observation(monkeypatch, capsys):
    seen = []
    def stage(parent, owner, source_owner, payload, **kwargs):
        seen.append((parent, owner, source_owner, payload))
        return {"prepared": False, "dispatch_ready": False, "new_model_calls": 0}
    monkeypatch.setattr(subject, "_stage", stage)
    assert subject.main(["status", "--owner", "synthetic-observer", "--source-owner", "synthetic-source"]) == 0
    assert seen == [(subject.FinalValidationRun, "synthetic-observer", "synthetic-source", {"action": "status"})]
    assert json.loads(capsys.readouterr().out) == {"prepared": False, "dispatch_ready": False, "new_model_calls": 0}


def test_configuration_cannot_supply_completeness_or_inline_source_flags():
    value = {"version": "final-validation-offline-stages-v1", "study_record": digest("study"), "seed_record": digest("seeds"),
        **{key: {} for key in ("source_bindings", "registry", "batch_declaration", "preparation_limits", "runtime", "quota_receipt", "resource_policy")},
        "series_limits": {"maximum_cumulative_invocations": 10000, "maximum_cumulative_token_reservations": 100000000,
            "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60}}
    subject.validate_configuration(value)
    with pytest.raises(AuditError, match="configuration_fields"):
        subject.validate_configuration({**value, "history_complete": True})


def test_concrete_v11_chain_offline_cli_retains_unknown_closure_and_never_dispatches(tmp_path, monkeypatch):
    import test_final_validation_downstream_v11 as composed
    import test_final_validation_reconciliation as reconciliation_fixture
    import test_final_validation_task_census_parent as task_fixture
    from test_final_validation_source import source_bytes
    monkeypatch.setattr(reconciliation_fixture, "setup", composed.v11_setup)
    main, owner, selected, registry, _ = task_fixture.prepared(tmp_path, copies=True, pair=True)
    census, _ = task_fixture.run(main, owner, selected)
    selected_batch, declaration = composed.representation_scope(tmp_path, main, owner, selected, census)
    # These are declared synthetic owners only; original source bytes must stay unchanged.
    source_paths = [main, *[Path(row["source_owner"]) for row in registry["owners"]],
        *[Path(row["source_owner"]) for row in declaration["owners"]]]
    before = {str(path): source_bytes(path) for path in source_paths}
    engine = subject.FinalValidationRun(owner, source_owner=main)
    try:
        snapshot_binding = selected["preparation_binding"]["snapshot_binding"]
        snapshot = engine.ledger.get(snapshot_binding["snapshot_record"], subject.lineage.v11_snapshot.SNAPSHOT)
        preparation = engine.ledger.get(selected["preparation_binding"]["preparation_record"], subject.lineage.v11_preparation.RESULT_KIND)
        original_seeds = engine._one(subject.study.SEEDS)
        binary = tmp_path / "synthetic-native-cli.exe"
        binary.write_bytes(native_bytes())
        config = {"version": "final-validation-offline-stages-v1",
            **{key: selected["preparation_binding"][key] for key in ("study_record", "seed_record")},
            "source_bindings": snapshot["binding"]["source_bindings"], "registry": registry, "batch_declaration": declaration,
            "preparation_limits": preparation["binding"]["limits"],
            "runtime": {"executable": str(binary), "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()},
            "quota_receipt": receipt(), "resource_policy": policy(allow=True),
            "series_limits": {"maximum_cumulative_invocations": 10000, "maximum_cumulative_token_reservations": 100000000,
                "maximum_tranche_primary": 40, "maximum_tranche_invocations": 60}}
    finally:
        engine.close()
    version_calls = []
    original_subprocess = subject.admission.subprocess.run
    def native_version(command, **kwargs):
        if len(command) == 2 and command[1] == "--version":
            version_calls.append(command)
            return SimpleNamespace(stdout="codex-cli 0.120.0\n", stderr="", returncode=0)
        return original_subprocess(command, **kwargs)
    monkeypatch.setattr(subject.admission.subprocess, "run", native_version)
    monkeypatch.setattr(subject.FinalValidationRun, "_native_provider", lambda *args: pytest.fail("Unknown closure cannot dispatch"))
    configuration = tmp_path / "protected-offline-config.json"
    configuration.write_text(canonical(config), encoding="utf-8")
    result = subject.offline_prepare(owner, main, configuration, objective="Synthetic end-to-end retained stages", actor="test")
    assert result["resource_census"]["fresh_potential_invocations"] == 0
    assert "zero_fresh_slots_preserved" in result["initial_conditions"]["blockers"]
    engine = subject.FinalValidationRun(owner, source_owner=main)
    try:
        attempted = call(engine, {"action": "run-initial", "prepared_record": result["prepared_record"], "quota_receipt": receipt()})
        assert attempted["new_local_attempts"] == 0 and "zero_fresh_slots_preserved" in attempted["blockers"]
        assert engine._one(subject.study.SEEDS) == original_seeds
        assert len(engine._rows(subject.series.SERIES)) == 1 and not engine._rows(subject.execution.INTENT_KIND)
        assert engine._one(subject.roots.RESULT)["payload"]["binding"]["closure_record"]
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended'").fetchone()
    finally:
        engine.close()
    assert len(version_calls) == 1
    assert all(source_bytes(path) == before[str(path)] for path in source_paths)
