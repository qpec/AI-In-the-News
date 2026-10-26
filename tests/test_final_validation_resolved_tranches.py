"""Synthetic boundary tests; one real resolved-initial/later gateway integration.

Small Guard fixtures exercise only the new session/receipt/dispatch guards using
actual audited ledgers, with explicitly synthetic authority. The integrated
case retains genuine original Study, resolved authority, initial manifest,
series, fixed slots, old later producer/epochs and shared gateway. Only upstream
source derivation and native transport use the previously reviewed fixtures.
"""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_resolved_tranches as subject  # noqa: E402
import test_final_validation_resolved_run as resolved_fixture  # noqa: E402
import test_final_validation_run as original_fixture  # noqa: E402
from test_final_validation_admission import receipt  # noqa: E402
from test_final_validation_packets import case as packet_case  # noqa: E402
from test_final_validation_study import process  # noqa: E402


@pytest.fixture(autouse=True)
def synthetic_only(monkeypatch):
    monkeypatch.setattr(subject.original.study.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def call(engine, action, prepared, **values):
    return engine.execute("status", {"action": action, "prepared_record": prepared, **values},
        objective="Synthetic resolved-later authority", actor="test")


class Synthetic(subject.ResolvedLaterValidationRun):
    gap = False
    _documents = original_fixture.SyntheticAuthority._documents


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(original_fixture, "case", lambda counter, size: packet_case(counter, size=10))
    prior = original_fixture.SyntheticAuthority._frame_and_closure
    def compact(self, session, context, selected):
        result = prior(self, session, context, selected)
        frame, schedule, saved, projection = result[2:6]
        # Exact role blockers leave one real initial invocation/liability.
        # Later ranks remain fresh; no blanket input/global gap is introduced.
        for slot in schedule.manifest["initial_prefix"]["tasks"][1:]:
            rank, role = slot["pair_rank"], slot["kind"]
            positions = subject.kernel.pair_from_rank(len(frame.index.inputs), rank)
            inputs = sorted(frame.index.inputs[p].input_sha256 for p in positions)
            projection["pair_role_blockers"].append({"pair_key": digest({"input_sha256": inputs, "role": role}),
                "input_sha256": inputs, "role": role, "references": [{"synthetic_prior_attempt": digest([rank, role])}]})
        reference = self.ledger.artifacts.put(projection)
        saved.update(projection_artifact=reference, effective_projection_artifact=reference,
            root_resolution_evidence_artifact=reference, original_closure_sha256=digest({"synthetic_role_blockers": reference}))
        return result
    monkeypatch.setattr(original_fixture.SyntheticAuthority, "_frame_and_closure", compact)
    engine, values, _, _, calls = resolved_fixture.setup(tmp_path, monkeypatch, gap=False)
    # Prospectively allow four hours for this synthetic replay: the first run
    # exceeded its one-hour admission window before later dispatch. Set this
    # before initial preparation; never renew a retained window during the test.
    values["resource_policy"]["admit_before"] = (
        datetime.fromisoformat(values["resource_policy"]["admit_before"]) + timedelta(hours=3)
    ).isoformat()
    prepared = resolved_fixture.call(engine, values)
    initial_run = resolved_fixture.call(engine, {"action": "run-initial", "prepared_record": prepared["prepared_record"],
        "quota_receipt": receipt()})
    assert initial_run["new_local_attempts"] == len(calls) == 1
    assert initial_run["execution_stop_reason"] == "fixed_tranche_processed"
    owner, source = engine.ledger.root, engine.source_owner
    authority = engine._one(subject.resolved.AUTHORITY)["id"]
    engine.close()
    return Synthetic(owner, source_owner=source), prepared["prepared_record"], authority, calls, values["resource_policy"]


def test_real_resolved_initial_to_later_gateway_reopen_and_exact_operation_authority(tmp_path, monkeypatch):
    engine, prepared, initial_authority, calls, policy = setup(tmp_path, monkeypatch)
    try:
        seeds = engine._one(subject.original.study.SEEDS)
        initial_value = engine.ledger.get(prepared, subject.original.PREPARED)
        initial_manifest = engine.ledger.get(initial_value["manifest_record"], subject.initial.MANIFEST_KIND)
        # Old Later cannot silently acquire the resolved projection.
        owner, source = engine.ledger.root, engine.source_owner
        engine.close()
        old = subject.later.LaterValidationRun(owner, source_owner=source)
        try:
            with pytest.raises(AuditError):
                old.execute("status", {"action": "status", "prepared_record": prepared}, objective="Synthetic old route refusal", actor="test")
        finally:
            old.close()
        engine = Synthetic(owner, source_owner=source)
        registered = call(engine, "register", prepared, resolved_initial_authority=initial_authority)
        assert not registered["registration_is_quota_authority"] and registered["new_model_calls"] == 0
        authority = engine._one(subject.AUTHORITY)
        assert registered["authority_record"] == authority["id"]
        assert call(engine, "register", prepared, resolved_initial_authority=initial_authority)["reused"]
        first = call(engine, "prepare-next", prepared, primary_limit=1, quota_receipt=receipt(), resource_policy=policy)
        assert first["fresh_slots"] > 0
        producer = engine.ledger.get(first["producer_record"], subject.later.PRODUCER)
        assert producer["method"] == subject.later.METHOD
        assert authority["created_event"] < engine._sequence(producer["intent_record"]) < engine._sequence(first["manifest_record"])
        admitted = call(engine, "admit", prepared, producer_record=first["producer_record"], quota_receipt=receipt(), resource_policy=policy)
        epoch = engine.ledger.get(admitted["epoch_record"], subject.later.EPOCH)
        assert epoch["initial_prepared_record"] == prepared
        before = len(calls)
        result = call(engine, "run", prepared, producer_record=first["producer_record"], epoch_record=admitted["epoch_record"], quota_receipt=receipt())
        assert result["new_local_attempts"] == len(calls) - before > 0 and result["stop_reason"] == "fixed_tranche_processed"
        assert all(row["payload"]["status"] == "resolved" for row in engine._rows(subject.kernel.RESULT))
        state = engine.ledger.artifacts.read(result["census_artifact"])
        assert state["resolved_later_authority"] == authority["id"]
        assert len(state["resolved_later_dispatches"]) == result["new_local_attempts"]
        assert state["accounting"]["coordinator_invocations"] == len(calls)
        assert state["accounting"]["account_dollar_cost"] is None
        assert set(state["cleared_kernel_blockers"]) <= {"later_dispatch_producer_not_bound"}
        for proof in state["resolved_later_dispatches"]:
            operation = engine.ledger.get(proof["operation_record"], subject.OPERATION)
            assert operation["inputs"]["epoch_record"] == admitted["epoch_record"]
        retained = deepcopy(engine._rows(subject.kernel.INTENT))
        engine.close()
        engine = Synthetic(owner, source_owner=source)
        repeated = call(engine, "resume", prepared, producer_record=first["producer_record"], epoch_record=admitted["epoch_record"], quota_receipt=receipt())
        assert repeated["new_local_attempts"] == 0 and len(calls) == before + result["new_local_attempts"]
        assert engine._rows(subject.kernel.INTENT) == retained
        assert engine.ledger.get(initial_value["manifest_record"], subject.initial.MANIFEST_KIND) == initial_manifest
        assert engine._one(subject.original.study.SEEDS) == seeds and not source.exists()
        assert call(engine, "status", prepared)["accounting"]["coordinator_invocations"] == len(calls)
        with pytest.raises(AuditError, match="initial_authority_selection"):
            call(engine, "register", prepared, resolved_initial_authority=digest("wrong authority"))
    finally:
        engine.close()


class Guard(subject.ResolvedLaterValidationRun):
    """Only guard units use synthetic authority; real public path is above."""
    def _authority(self):
        return self._one("synthetic_bridge_authority")

    def _proof(self, loaded):
        return {"synthetic": True}

    @audited_handler
    def _status(self, session, context, data):
        action = data["action"]
        prepared = digest("synthetic prepared")
        if action == "authority":
            return {"record": self.ledger.record(session, "synthetic_bridge_authority", "exact",
                {"proof": {"synthetic": True}})}
        authority = self._authority()
        inputs = {"action": "run", "prepared_record": prepared, "producer_record": digest("producer"),
            "epoch_record": digest("epoch"), "quota_receipt": {"synthetic": True}}
        operation = {"method": subject.METHOD, "authority_record": authority["id"],
            "authority_payload_sha256": digest(authority["payload"]),
            "implementation_sha256": digest(subject.implementation()), "inputs": inputs}
        fault = getattr(self, "fault", None)
        if fault in {"authority_record", "authority_payload_sha256", "implementation_sha256"}:
            operation[fault] = digest("wrong")
        if fault == "prepared_record":
            operation["inputs"] = {**inputs, "prepared_record": digest("other")}
        if fault == "action":
            operation["inputs"] = {**inputs, "action": "register"}
        if fault == "framework_input":
            operation["inputs"] = {**inputs, "quota_receipt": {"other": True}}
        operation_id = self.ledger.record(session, subject.OPERATION, session, operation)
        seq = self._sequence(operation_id)
        if fault == "duplicate":
            self.ledger.record(session, subject.OPERATION, session + "duplicate", operation)
        if fault:
            with pytest.raises(AuditError, match="resolved_later_operation"):
                self._operation_for(seq, expected_prepared=prepared)
            return {"blocked": True}
        verified = self._operation_for(seq, expected_prepared=prepared)
        assert verified["id"] == operation_id
        return {"verified": operation_id}


@pytest.mark.parametrize("fault", [None, "authority_record", "authority_payload_sha256", "implementation_sha256",
    "prepared_record", "action", "framework_input", "duplicate"])
def test_exact_operation_receipt_and_framework_input_binding(tmp_path, fault):
    engine = Guard(tmp_path / "guard", source_owner=tmp_path / "absent")
    try:
        Research.execute(engine, "status", {"action": "authority"}, objective="Synthetic guard", actor="test")
        engine.fault = fault
        inputs = {"method": subject.METHOD, "action": "run", "prepared_record": digest("synthetic prepared"),
            "producer_record": digest("producer"), "epoch_record": digest("epoch"), "quota_receipt": {"synthetic": True}}
        result = Research.execute(engine, "status", inputs, objective="Synthetic guard", actor="test")
        assert result.get("blocked") if fault else result.get("verified")
    finally:
        engine.close()


@pytest.mark.parametrize("kind", [subject.later.INTENT, subject.later.PRODUCER, subject.later.EPOCH,
    subject.kernel.TRANCHE, subject.kernel.INTENT, subject.kernel.SLOT])
def test_existing_later_evidence_refuses_registration_before_loader(tmp_path, monkeypatch, kind):
    class Existing(Guard):
        @audited_handler
        def _status(self, session, context, data):
            self.ledger.record(session, kind, "unbound", {"synthetic": True})
            selected = {"prepared_record": digest("prepared"), "resolved_initial_authority": digest("authority")}
            monkeypatch.setattr(self, "_selection", lambda v: v)
            monkeypatch.setattr(self, "_intent", lambda v: {"selection": v})
            with pytest.raises(AuditError, match="prior_later_evidence_forbids_adoption"):
                self._register(session, context, selected)
            assert not self._rows(subject.INTENT) and not self._rows(subject.AUTHORITY)
            return {"blocked": True}
    engine = Existing(tmp_path / "guard", source_owner=tmp_path / "absent")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic adoption refusal", actor="test")["blocked"]
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["content", "branch", "duplicate", "before_intent"])
def test_invalid_protocol_fails_before_initial_replay_or_authority_write(tmp_path, monkeypatch, fault):
    class ProtocolGuard(Guard):
        @audited_handler
        def _status(self, session, context, data):
            selected = {"prepared_record": digest("prepared"), "resolved_initial_authority": digest("authority")}
            monkeypatch.setattr(self, "_selection", lambda v: v)
            monkeypatch.setattr(self, "_intent", lambda v: {"selection": v})
            early = None
            if fault == "before_intent":
                desired = {"selection": selected}
                predicted = digest({"kind": subject.INTENT, "key": subject.METHOD,
                    "payload": digest(desired), "supersedes": None})
                early = self.ledger.record(session, "protocol", subject.METHOD,
                    {"content": {"method": subject.METHOD, "intent_record": predicted, "binding": desired},
                        "reason": None, "branch": "main"})
            def version(s, c, kind, key, content):
                if early:
                    return early
                value = {"content": content, "reason": None, "branch": "main"}
                if fault == "content":
                    value["content"] = {"wrong": True}
                if fault == "branch":
                    value["branch"] = "alternate"
                first = self.ledger.record(s, "protocol", key, value)
                if fault == "duplicate":
                    self.ledger.record(s, "protocol", key, {**value, "reason": "duplicate"})
                return first
            monkeypatch.setattr(self, "_version_once", version)
            def forbidden(*a, **k):
                pytest.fail("Invalid protocol entered initial replay")
            monkeypatch.setattr(subject.original.FinalValidationRun, "_load_run", forbidden)
            with pytest.raises(AuditError, match="authority_protocol"):
                self._register(session, context, selected)
            assert not self._rows(subject.AUTHORITY) and not self._rows(subject.initial.SLOT_KIND)
            return {"blocked": True}
    engine = ProtocolGuard(tmp_path / "guard", source_owner=tmp_path / "absent")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic protocol ordering", actor="test")["blocked"]
    finally:
        engine.close()


def test_lean_initial_orphan_and_active_epoch_guards(tmp_path, monkeypatch):
    class Boundaries(Guard):
        @audited_handler
        def _status(self, session, context, data):
            # These deliberately malformed scoped histories must fail before
            # packet/Invocation reconstruction, without consulting response Y.
            loaded = ({"manifest_record": digest("initial")}, {"tasks": [], "scope_sha256": digest("scope")},
                {"cli_profile": {}}, None, None)
            self.ledger.append(session, "model.attempt.completed", {"attempt": "completion-only"})
            with pytest.raises(AuditError, match="foreign_initial_attempt_state"):
                self._initial_attempts(loaded)
            # A separate history iterator is unnecessary: the exact foreign
            # request guard is independently checked in a second audited owner.
            return {"completion_only_blocked": True}
    engine = Boundaries(tmp_path / "completion", source_owner=tmp_path / "source")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic generic orphan", actor="test")["completion_only_blocked"]
    finally:
        engine.close()
    class Foreign(Guard):
        @audited_handler
        def _status(self, session, context, data):
            self.ledger.append(session, "model.attempt.intended", {"attempt": "foreign", "manifest": digest("foreign")})
            loaded = ({"manifest_record": digest("initial")}, {"tasks": [], "scope_sha256": digest("scope")}, {"cli_profile": {}})
            with pytest.raises(AuditError, match="foreign_or_unbound_initial_attempt"):
                self._initial_attempts(loaded)
            return {"foreign_blocked": True}
    engine = Foreign(tmp_path / "foreign", source_owner=tmp_path / "source")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic foreign attempt", actor="test")["foreign_blocked"]
    finally:
        engine.close()
    class Epochs(Guard):
        @audited_handler
        def _status(self, session, context, data):
            self.ledger.record(session, "synthetic_bridge_authority", "exact", {"proof": {"synthetic": True}})
            prepared = self.ledger.record(session, subject.original.PREPARED, "synthetic", {})
            epoch = {"producer_record": digest("producer")}
            epoch_id = self.ledger.record(session, subject.later.EPOCH, "synthetic", epoch)
            operation_id = self.ledger.record(session, "synthetic_operation", "synthetic", {})
            inputs = {"action": "run", "prepared_record": prepared, "producer_record": epoch["producer_record"],
                "epoch_record": epoch_id, "quota_receipt": {"synthetic": True}}
            operation = {"payload": {"inputs": inputs}}
            monkeypatch.setattr(self, "_operation_for", lambda *a, **k: operation)
            monkeypatch.setattr(subject.later.LaterValidationRun, "_conditions",
                lambda *a, **k: pytest.fail("Invalid new authority boundary delegated to dispatcher"))
            self._bridge_operation, self._bridge_loaded = (session, operation_id), (session, ())
            with pytest.raises(AuditError, match="active_epoch_binding"):
                self._conditions(session, (), {"producer_record": digest("wrong")}, {}, None)
            with pytest.raises(AuditError, match="active_fresh_quota"):
                self._conditions(session, (), epoch, {"receipt_artifact": digest("different")}, None)
            self._bridge_loaded = ("another-session", ())
            with pytest.raises(AuditError, match="active_initial_proof"):
                self._conditions(session, (), epoch, {"receipt_artifact": digest(inputs["quota_receipt"])}, None)
            self._bridge_operation = None
            with pytest.raises(AuditError, match="active_operation_required"):
                self._conditions(session, (), epoch, {}, None)
            return {"epoch_and_receipt_blocked": True}
    engine = Epochs(tmp_path / "epoch", source_owner=tmp_path / "source")
    try:
        assert Research.execute(engine, "status", {}, objective="Synthetic dispatch boundaries", actor="test")["epoch_and_receipt_blocked"]
    finally:
        engine.close()


def test_implementation_binds_both_actual_producers_and_numerical_dispatch_dependencies():
    code = subject.implementation()
    for module in (subject, subject.resolved, subject.later, subject.kernel, subject.original):
        path = Path(module.__file__)
        assert code[path.relative_to(subject.initial.ROOT).as_posix()] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert any(name.endswith("gateway.py") for name in code)
    assert any(name.endswith("final_validation_frame.py") for name in code)


@pytest.mark.parametrize("payload", [{"action": "status"}, {"action": "prepare"},
    {"action": "register", "prepared_record": digest("p"), "resolved_initial_authority": digest("a"), "complete": True}])
def test_public_route_refuses_missing_or_caller_authority_fields_before_execute(payload):
    engine = object.__new__(subject.ResolvedLaterValidationRun)
    with pytest.raises(AuditError, match="entry_shape"):
        engine.execute("status", payload, objective="Synthetic malformed input", actor="test")


def test_cli_requires_protected_config_before_constructing_owner(tmp_path):
    with pytest.raises(AuditError, match="protected_input_required"):
        subject.main(["--owner", str(tmp_path / "not-created"), "--source-owner", str(tmp_path / "source"),
            "--input", "relative.json"])
    assert not (tmp_path / "not-created").exists()
