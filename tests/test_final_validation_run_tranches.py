"""Synthetic account transport, genuine Study/Run/series/ledger/gateway boundaries.

The initial outcomes are explicit synthetic fixtures; later requests use the real
PairProvider/shared gateway with a mocked native subprocess. No account/source
owner is opened. The separately tested Run supplies original authority.
"""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, ResearchError, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_run_tranches as subject  # noqa: E402
import test_final_validation_run as original_tests  # noqa: E402
from test_final_validation_admission import policy as initial_policy, receipt  # noqa: E402
from test_final_validation_execution_v2 import Kernel  # noqa: E402
from test_final_validation_packets import case as packet_case  # noqa: E402
from test_final_validation_study import process  # noqa: E402
from test_final_validation_provider import setup as provider_fixture, packet  # noqa: E402, F401


@pytest.fixture(autouse=True)
def no_real_process_or_credentials(monkeypatch):
    monkeypatch.setattr(subject.original.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


class SyntheticLater(subject.LaterValidationRun, original_tests.SyntheticAuthority):
    @audited_handler
    def _status(self, session, context, data):
        if data.get("synthetic_orphan_attempt"):
            loaded = self._load_run(session, context, data["prepared_record"])
            self.frame = loaded[3][2]
            self.options = {"user_instruction_sha256": loaded[1]["scope"]["user_instruction_sha256"]}
            manifest = self.ledger.get(data["manifest"], subject.kernel.TRANCHE)
            task = next(t for t in manifest["tasks"] if t["disposition"] == "fresh")
            Kernel.attempt(self, session, data["manifest"], task, mode="generic_before_custom")
            return {"synthetic_generic_intent_retained": True}
        if data.get("synthetic_settle_initial"):
            loaded = self._load_run(session, context, data["prepared_record"])
            self.frame = loaded[3][2]
            self.options = {"user_instruction_sha256": loaded[1]["scope"]["user_instruction_sha256"]}
            normalized = {}
            for task in loaded[1]["tasks"]:
                if task["disposition"] == "fresh" and subject.initial.conditional_state(task, normalized) == "eligible":
                    Kernel.attempt(self, session, loaded[0]["manifest_record"], task)
                    normalized[(task["pair_rank"], task["role"])] = {"status": "resolved", "positive": 0}
            return self._census(session, loaded)
        return super()._status(session, context, data)


def call(engine, action, prepared, **kwargs):
    return engine.execute("status", {"action": action, "prepared_record": prepared, **kwargs},
        objective="Synthetic later-tranche execution", actor="synthetic")


def policy(*, allow=False):
    # The fully verified replay is deliberately expensive. This is an explicit
    # synthetic epoch policy, not a clock patch or production quota renewal.
    result = initial_policy(allow=allow)
    result["quota_valid_for_seconds"] = 7200
    return result


def opened(tmp_path, monkeypatch, *, gap=False, ceilings=None, compact=True, mixed=False):
    monkeypatch.setattr(original_tests, "case", lambda counter, size: packet_case(counter, size=12))
    if compact and not gap:
        original_authority = original_tests.SyntheticAuthority._frame_and_closure
        def compact_authority(self, session, context, selected):
            result = original_authority(self, session, context, selected)
            frame, schedule, saved, projection = result[2:6]
            prefix = schedule.manifest["initial_prefix"]
            # Exact synthetic prior role attempts, never endpoint/global gaps:
            # one initial primary stays fresh with real nonzero liability.
            blocked = [(t["pair_rank"], t["kind"]) for t in prefix["tasks"]][1:]
            if mixed:
                rank = schedule.manifest["cumulative_primary_orders"][0][len(prefix["primary_ranks"])]
                blocked += [(rank, role) for role in subject.initial.history.ROLES]
            for rank, role in blocked:
                positions = subject.kernel.pair_from_rank(len(frame.index.inputs), rank)
                inputs = sorted(frame.index.inputs[p].input_sha256 for p in positions)
                projection["pair_role_blockers"].append({"pair_key": digest({"input_sha256": inputs, "role": role}),
                    "input_sha256": inputs, "role": role,
                    "references": [{"synthetic_prior_attempt": digest([rank, role])}]})
            reference = self.ledger.artifacts.put(projection)
            saved.update(projection_artifact=reference, effective_projection_artifact=reference,
                root_resolution_evidence_artifact=reference,
                original_closure_sha256=digest({"synthetic_exact_role_blockers": reference}))
            return result
        monkeypatch.setattr(original_tests.SyntheticAuthority, "_frame_and_closure", compact_authority)
    engine, values, _, versions, calls = original_tests.setup(tmp_path, monkeypatch, gap=gap)
    if ceilings:
        values["series_limits"].update(ceilings)
    try:
        ready = original_tests.call(engine, values)
        owner, source = engine.ledger.root, engine.source_owner
    finally:
        engine.close()
    later = SyntheticLater(owner, source_owner=source)
    later.gap = gap
    state = Research.execute(later, "status", {"synthetic_settle_initial": True, "prepared_record": ready["prepared_record"]},
        objective="Synthetic settled initial results, not model judgments", actor="test")
    assert not state["blockers"] and subject.kernel._settled_states(state["states"])
    if compact and not gap:
        assert state["accounting"]["coordinator_invocations"] == 1
        assert state["accounting"]["committed_token_units"] > 0
        assert len(later._rows(subject.initial.SLOT_KIND)) > 0
    assert not calls
    return later, ready["prepared_record"], calls, versions


def prepare(engine, prepared, *, count=3, chosen=None):
    return call(engine, "prepare-next", prepared, primary_limit=count, quota_receipt=receipt(), resource_policy=chosen or policy(allow=True))


def admit(engine, prepared, producer, *, chosen=None, observed=None):
    return call(engine, "admit", prepared, producer_record=producer, quota_receipt=observed or receipt(), resource_policy=chosen or policy(allow=True))


def test_actual_later_gateway_fixed_roles_stop_epoch_reopen_and_cumulative_no_retry(tmp_path, monkeypatch):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch, compact=False)
    try:
        seeds = engine._one(subject.original.study.SEEDS)
        first = prepare(engine, prepared, count=2)
        manifest = engine.ledger.get(first["manifest_record"], subject.kernel.TRANCHE)
        assert manifest["plan"]["diagnostic_identities_added"] == []
        assert not any(t["role"] == "uncertain_adjudication" for t in manifest["tasks"])
        assert len({t["logical_task_id"] for t in manifest["tasks"]}) == len(manifest["tasks"])
        with pytest.raises(AuditError, match="previous_tranche_not_closed"):
            prepare(engine, prepared)
        epoch = admit(engine, prepared, first["producer_record"])
        calls.stop_after_first = True
        stopped = call(engine, "run", prepared, producer_record=first["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
        assert stopped["new_local_attempts"] == 1 and stopped["stop_reason"] == "user_stop"
        assert engine._rows(subject.kernel.RESULT)[0]["payload"]["status"] == "resolved"
        retained = engine._rows(subject.kernel.INTENT)[0]
        original_manifest = engine.ledger.get(first["manifest_record"], subject.kernel.TRANCHE)
        (engine.ledger.root / "STOP").unlink()
        calls.stop_after_first = False
        second_epoch = admit(engine, prepared, first["producer_record"])
        epoch_value = engine.ledger.get(second_epoch["epoch_record"], subject.EPOCH)
        assert retained["payload"]["logical_task_id"] not in epoch_value["untouched_logical_task_ids"]
        prior = engine.ledger.artifacts.read(epoch_value["prior_census_artifact"])
        assert prior["accounting"]["coordinator_invocations"] == stopped["accounting"]["coordinator_invocations"]
        epoch = second_epoch
        owner, source = engine.ledger.root, engine.source_owner
        engine.close()
        engine = SyntheticLater(owner, source_owner=source)
        resumed = call(engine, "resume", prepared, producer_record=first["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
        assert resumed["stop_reason"] == "fixed_tranche_processed" and not resumed["blockers"]
        assert engine._rows(subject.kernel.INTENT)[0] == retained
        previous = len(calls)
        assert call(engine, "resume", prepared, producer_record=first["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())["new_local_attempts"] == 0
        assert len(calls) == previous
        assert engine.ledger.get(first["manifest_record"], subject.kernel.TRANCHE) == original_manifest
        assert engine._one(subject.original.study.SEEDS) == seeds
        projected = engine.ledger.artifacts.read(resumed["census_artifact"])
        raw = engine.ledger.artifacts.read(projected["kernel_census_sha256"])
        assert projected["cleared_kernel_blockers"] == ["later_dispatch_producer_not_bound"]
        assert set(raw["blockers"]) - set(projected["blockers"]) == {"later_dispatch_producer_not_bound"}
        assert projected["accounting"]["coordinator_invocations"] > len(calls)
        assert len(projected["verified_later_dispatches"]) == len(calls)
        assert projected["accounting"]["account_dollar_cost"] is None
        assert not engine.source_owner.exists()
        assert not any(d["body"] in canonical(resumed) for d in engine.documents)
    finally:
        engine.close()


def test_all_unavailable_local_materialization_and_partial_recovery_never_construct_provider(tmp_path, monkeypatch):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch, gap=True)
    original_record = engine.ledger.record
    seen = []
    def interrupted(session, kind, key, content, *args, **kwargs):
        if kind == subject.kernel.SLOT:
            seen.append(key)
            if len(seen) == 2:
                raise AuditError("synthetic_local_interruption")
        return original_record(session, kind, key, content, *args, **kwargs)
    try:
        monkeypatch.setattr(engine.ledger, "record", interrupted)
        with pytest.raises(AuditError, match="synthetic_local_interruption"):
            prepare(engine, prepared)
        producer = engine._rows(subject.PRODUCER)[0]
        first_slot = engine._rows(subject.kernel.SLOT)[0]
        monkeypatch.setattr(engine.ledger, "record", original_record)
        state = call(engine, "status", prepared)
        assert "local_resolution_missing" not in state["states"]
        assert engine._rows(subject.kernel.SLOT)[0] == first_slot
        assert len(engine._rows(subject.PRODUCER)) == 1
        epoch = admit(engine, prepared, producer["id"])
        outcome = call(engine, "run", prepared, producer_record=producer["id"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
        assert outcome["new_local_attempts"] == 0 and not calls and outcome["stop_reason"] == "fixed_tranche_processed"
        remainder = prepare(engine, prepared, count=40)
        assert remainder["fresh_slots"] == 0
        first_manifest = engine.ledger.get(producer["payload"]["manifest_record"], subject.kernel.TRANCHE)
        next_manifest = engine.ledger.get(remainder["manifest_record"], subject.kernel.TRANCHE)
        assert next_manifest["previous_manifest"] == producer["payload"]["manifest_record"]
        assert next_manifest["plan"]["start"] == first_manifest["plan"]["stop"]
        assert not {t["logical_task_id"] for t in first_manifest["tasks"]} & {t["logical_task_id"] for t in next_manifest["tasks"]}
        complete = call(engine, "fixed-look", prepared, look=1)
        repeated = call(engine, "fixed-look", prepared, look=1)
        assert complete["look_record"] == repeated["look_record"] and repeated["reused"]
        report = engine.ledger.get(complete["look_record"], subject.kernel.LOOK)
        assert report["look"] == 1 and report["result"]["metrics"]["requested_widths_met"] is False
        with pytest.raises(AuditError, match="all_declared_looks_exhausted"):
            prepare(engine, prepared)
    finally:
        engine.close()


def test_mixed_later_local_and_fresh_slots_preserve_order_and_only_dispatch_untouched(tmp_path, monkeypatch):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch, mixed=True)
    try:
        ready = prepare(engine, prepared)
        manifest = engine.ledger.get(ready["manifest_record"], subject.kernel.TRANCHE)
        local = [t for t in manifest["tasks"] if t["disposition"] != "fresh"]
        fresh = [t for t in manifest["tasks"] if t["disposition"] == "fresh"]
        assert local and fresh
        retained = engine._rows(subject.kernel.SLOT)
        assert {r["payload"]["logical_task_id"] for r in retained} == {t["logical_task_id"] for t in local}
        with pytest.raises(AuditError, match="complete_fixed_look_required"):
            call(engine, "fixed-look", prepared, look=1)
        epoch = admit(engine, prepared, ready["producer_record"])
        result = call(engine, "run", prepared, producer_record=ready["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
        assert result["stop_reason"] == "fixed_tranche_processed" and 0 < result["new_local_attempts"] == len(calls)
        assert engine._rows(subject.kernel.SLOT) == retained
        attempted = {r["payload"]["logical_task_id"] for r in engine._rows(subject.kernel.INTENT)}
        assert attempted <= {t["logical_task_id"] for t in fresh} and attempted.isdisjoint(t["logical_task_id"] for t in local)
        assert engine.ledger.get(ready["manifest_record"], subject.kernel.TRANCHE) == manifest
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["generic_before_custom", "result_before_completion", "unknown"])
def test_later_crash_or_unknown_preserves_liability_and_blocks_new_epoch_and_resume(tmp_path, monkeypatch, fault):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch)
    original_record, original_append = engine.ledger.record, engine.ledger.append
    try:
        ready = prepare(engine, prepared, count=1)
        epoch = admit(engine, prepared, ready["producer_record"])
        if fault == "unknown":
            calls.timeout = True
        elif fault == "generic_before_custom":
            def record(session, kind, *args, **kwargs):
                if kind == subject.kernel.INTENT:
                    raise AuditError("synthetic_custom_gap")
                return original_record(session, kind, *args, **kwargs)
            monkeypatch.setattr(engine.ledger, "record", record)
        else:
            def append(session, kind, *args, **kwargs):
                if kind == "model.attempt.completed":
                    raise AuditError("synthetic_completion_gap")
                return original_append(session, kind, *args, **kwargs)
            monkeypatch.setattr(engine.ledger, "append", append)
        arguments = {"producer_record": ready["producer_record"], "epoch_record": epoch["epoch_record"], "quota_receipt": receipt()}
        if fault == "unknown":
            outcome = call(engine, "run", prepared, **arguments)
            assert "retained_unknown_outcome" in outcome["blockers"]
        else:
            with pytest.raises(AuditError, match="synthetic_"):
                call(engine, "run", prepared, **arguments)
        monkeypatch.setattr(engine.ledger, "record", original_record)
        monkeypatch.setattr(engine.ledger, "append", original_append)
        count = len(calls)
        state = call(engine, "status", prepared)
        assert "durable_completion_missing" in state["blockers"]
        assert state["accounting"]["committed_token_units"] >= state["accounting"]["reservation_tokens"] > 0
        resumed = call(engine, "resume", prepared, **arguments)
        assert resumed["new_local_attempts"] == 0 and len(calls) == count
        with pytest.raises(AuditError, match="existing_attempts_block_admission"):
            admit(engine, prepared, ready["producer_record"])
    finally:
        engine.close()


def test_quota_exhaustion_unknown_time_stop_and_epoch_caps_are_independent(tmp_path, monkeypatch):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch)
    try:
        ready = prepare(engine, prepared, count=1)
        expanded = policy(allow=True)
        expanded["maximum_token_reservations"] += 1
        with pytest.raises(AuditError, match="epoch_cannot_expand_tranche"):
            admit(engine, prepared, ready["producer_record"], chosen=expanded)
        for chosen, observed, reason in [(policy(), receipt(), "quota_unit_capacity_unavailable_policy_blocks"),
                (policy(allow=True), receipt(used=100), "observed_account_limit_exhausted")]:
            epoch = admit(engine, prepared, ready["producer_record"], chosen=chosen, observed=observed)
            result = call(engine, "run", prepared, producer_record=ready["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
            assert reason in result["blockers"] and not calls
        expired = policy(allow=True)
        now = datetime.now(timezone.utc)
        expired.update(not_before=(now - timedelta(hours=2)).isoformat(), admit_before=(now - timedelta(hours=1)).isoformat())
        epoch = admit(engine, prepared, ready["producer_record"], chosen=expired)
        result = call(engine, "resume", prepared, producer_record=ready["producer_record"], epoch_record=epoch["epoch_record"], quota_receipt=receipt())
        assert "outside_registered_admission_window" in result["blockers"] and not calls
        # A separately registered LATER epoch can admit only untouched tasks;
        # it never replaces either the initial manifest or an earlier epoch.
        fresh = admit(engine, prepared, ready["producer_record"])
        result = call(engine, "run", prepared, producer_record=ready["producer_record"], epoch_record=fresh["epoch_record"], quota_receipt=receipt())
        assert result["stop_reason"] == "fixed_tranche_processed" and result["new_local_attempts"] > 0
        assert len(engine._rows(subject.EPOCH)) == 4
    finally:
        engine.close()


@pytest.mark.parametrize("attempted", [False, True])
def test_registered_manifest_before_producer_is_recovered_locally_without_new_task_or_request(tmp_path, monkeypatch, attempted):
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch, gap=not attempted)
    original_record = engine.ledger.record
    def interrupted(session, kind, *args, **kwargs):
        if kind == subject.PRODUCER:
            raise AuditError("synthetic_producer_gap")
        return original_record(session, kind, *args, **kwargs)
    try:
        monkeypatch.setattr(engine.ledger, "record", interrupted)
        with pytest.raises(AuditError, match="synthetic_producer_gap"):
            prepare(engine, prepared)
        manifest = engine._rows(subject.kernel.TRANCHE)[0]
        intended = engine._rows(subject.INTENT)[0]
        assert not engine._rows(subject.PRODUCER) and not calls
        monkeypatch.setattr(engine.ledger, "record", original_record)
        if attempted:
            Research.execute(engine, "status", {"synthetic_orphan_attempt": True, "prepared_record": prepared,
                "manifest": manifest["id"]}, objective="Synthetic durable orphan attempt", actor="test")
            with pytest.raises(AuditError, match="orphan_manifest_already_attempted"):
                call(engine, "status", prepared)
            assert not engine._rows(subject.PRODUCER) and not calls
            assert engine._rows(subject.kernel.TRANCHE) == [manifest] and engine._rows(subject.INTENT) == [intended]
            return
        state = call(engine, "status", prepared)
        assert not state["blockers"] and "local_resolution_missing" not in state["states"]
        producer = engine._rows(subject.PRODUCER)[0]
        assert producer["payload"]["manifest_record"] == manifest["id"]
        assert producer["payload"]["intent_record"] == intended["id"]
        assert engine._rows(subject.kernel.TRANCHE) == [manifest] and engine._rows(subject.INTENT) == [intended]
        call(engine, "status", prepared)
        assert engine._rows(subject.PRODUCER) == [producer] and not calls
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["per_tranche_tokens", "cumulative_invocations"])
def test_insufficient_registered_resources_cannot_retain_invalid_manifest(tmp_path, monkeypatch, fault):
    ceilings = {"maximum_cumulative_invocations": 60} if fault == "cumulative_invocations" else None
    engine, prepared, calls, _ = opened(tmp_path, monkeypatch, ceilings=ceilings, compact=fault != "cumulative_invocations")
    try:
        chosen = policy(allow=True)
        if fault == "per_tranche_tokens":
            chosen["maximum_token_reservations"] = 1
        error = ResearchError if fault == "per_tranche_tokens" else AuditError
        with pytest.raises(error, match="resource_token_limit|cumulative_reservation_limit"):
            prepare(engine, prepared, count=40, chosen=chosen)
        assert not engine._rows(subject.kernel.TRANCHE) and not engine._rows(subject.PRODUCER) and not calls
        assert len(engine._rows(subject.INTENT)) == 1  # exact failed scope, no silent replacement
        with pytest.raises(AuditError, match="incomplete_preparation_changed"):
            prepare(engine, prepared, count=1)
    finally:
        engine.close()


@pytest.mark.parametrize("name,value", [("maximum_invocations", True), ("maximum_invocations", 61),
    ("unavailable_quota_policy", "assume_zero"), ("maximum_token_reservations", 1.5),
    ("decision_note", ""), ("quota_valid_for_seconds", 0)])
def test_resource_policy_rejects_unbounded_or_ambiguous_units(name, value):
    chosen = policy(allow=True)
    chosen[name] = value
    with pytest.raises(AuditError):
        subject.resource_policy(chosen)


def test_new_module_is_bound_without_changing_original_dependency_maps():
    path = Path(subject.__file__).relative_to(subject.initial.ROOT).as_posix()
    assert path in subject.implementation()
    assert path not in subject.kernel.implementation() and path not in subject.original.implementation()
    assert subject.POLICY["initial_window_renewed"] is False
    assert subject.POLICY["diagnostic_identities_added"] == []


@pytest.mark.parametrize("fault", [None, "command", "stdin", "input_tokens_proxy", "invocation_id", "cwd", "extra"])
def test_dispatch_replay_proves_exact_retained_blinded_invocation(provider_fixture, fault):  # noqa: F811
    provider = provider_fixture.provider
    provider.workspace = provider.workspace.parent / "final-validation-account-workers"
    invocation = provider.prepare(packet())
    retained = deepcopy(invocation.manifest())
    if fault == "command":
        retained["command"].append("--dangerously-bypass-approvals-and-sandbox")
    elif fault == "stdin":
        retained["stdin"] += " changed"
    elif fault == "input_tokens_proxy":
        retained[fault] += 1
    elif fault == "invocation_id":
        retained[fault] = "caller-selected"
    elif fault == "cwd":
        retained[fault] = str(provider.workspace.parent / "other" / "codex-judge-123")
    elif fault == "extra":
        retained["extra"] = True
    profile = {"cli_binding": provider.cli_binding, "tokenizer_identity": provider.tokenizer_identity}
    if fault:
        with pytest.raises(AuditError, match="dispatch_"):
            subject.dispatch_binding(invocation.packet, retained, profile, provider.workspace.parent)
    else:
        replay = subject.dispatch_binding(invocation.packet, retained, profile, provider.workspace.parent)
        assert replay.manifest() == retained
    assert not provider_fixture.calls
