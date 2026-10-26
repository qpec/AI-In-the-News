"""Registered temporary synthetic owners; mocked --version, no account/source/model."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from newsresearch.common import AuditError, Config, Context, canonical, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_admission as subject  # noqa: E402
import test_final_validation_packets as fixtures  # noqa: E402
from test_final_validation_study import payload as study_payload  # noqa: E402


def native_bytes():
    value = bytearray(128)
    value[:2], value[60:64], value[64:68] = b"MZ", (64).to_bytes(4, "little"), b"PE\0\0"
    return bytes(value)


def policy(*, allow=False):
    now = datetime.now(timezone.utc)
    value = {"maximum_invocations": 60, "maximum_token_reservations": 1_000_000, "output_token_allowance": 2000,
        "not_before": (now - timedelta(hours=1)).isoformat(), "admit_before": (now + timedelta(hours=1)).isoformat(),
        "quota_valid_for_seconds": 600, "decision_note": "Synthetic prospective account-only resource decision."}
    if allow:
        value["unavailable_quota_policy"] = "allow_bounded_registered"
    return value


def receipt(*, used=20, stale=False):
    return {"source": "codex_app_get_usage_limits", "source_reference": "synthetic-tool-output:fixed-test",
        "captured_at": (datetime.now(timezone.utc) - timedelta(hours=1) if stale else datetime.now(timezone.utc)).isoformat(),
        "selected_limit_id": "codex", "raw_result": {"rateLimitsByLimitId": {"codex": {
            "primary": {"usedPercent": used, "resetsAt": 1_900_000_000}, "secondary": None}}}}


class Probe(Research):
    calls = None
    settings = None

    @audited_handler
    def _status(self, session, context, data):
        content = subject.protocol_content(data["study_record"])
        if self.settings.get("unregistered"):
            content["scope"] = "wrong"
        protocol = self._version(session, context, {"kind": "protocol", "key": subject.METHOD, "content": content})["id"]
        active = Context(context.objective, context.actor, {"protocol": protocol})
        def runner(command, **kwargs):
            self.calls.append((command, kwargs))
            assert command == [data["executable"], "--version"]
            if self.settings.get("changed_binary"):
                Path(data["executable"]).write_bytes(native_bytes() + b"changed")
            if self.settings.get("timeout"):
                raise subject.subprocess.TimeoutExpired(command, 10)
            return SimpleNamespace(stdout=self.settings.get("version", "codex-cli 0.120.0\n"),
                                   stderr="", returncode=self.settings.get("exit_code", 0))
        with patch.object(subject.subprocess, "run", runner):
            runtime = subject.observe_runtime(self, session, active, study_record=data["study_record"],
                executable=data["executable"], executable_sha256=data["executable_sha256"])
        self.runtime = runtime
        quota = subject.retain_quota_receipt(self, session, active, study_record=data["study_record"], receipt=data["receipt"])
        chosen = subject.retain_resource_policy(self, session, active, study_record=data["study_record"], policy=data["policy"])
        resources = subject.resources_from_evidence(self, session, active, study_record=data["study_record"],
            quota_record=quota, policy_record=chosen)
        frame, schedule, documents, values = fixtures.case(runtime["token_counter"], size=4)
        values.update(cli_profile=runtime["cli_profile"], resources=resources,
            user_instruction_sha256=self.ledger.get(data["study_record"], subject.study.STUDY)["instruction_evidence_artifact"])
        if self.settings.get("history_gap"):
            values["history_inventory"].update(complete=False, global_gap=True)
            fixtures.rebind(values)
        if self.settings.get("resource_mismatch"):
            values["resources"] = deepcopy(resources)
            values["resources"]["maximum_token_reservations"] += 1
        if self.settings.get("counter_tamper"):
            original_count = runtime["token_counter"].count
            object.__setattr__(runtime["token_counter"], "count", lambda text: original_count(text) + 1)
        prepared = subject.packets.prepare_initial_packets(frame, schedule, documents, **values)
        if self.settings.get("binary_before_assessment"):
            Path(data["executable"]).write_bytes(native_bytes() + b"changed")
        result = subject.assess_packet_resources(self, session, active, study_record=data["study_record"], prepared=prepared,
            runtime_record=runtime["runtime_record"], quota_record=quota, policy_record=chosen)
        return result | {"runtime_record": runtime["runtime_record"], "quota_record": quota, "policy_record": chosen}


def initialize(tmp_path, **settings):
    root = tmp_path / "validation"
    original = subject.study.Study(root, source_owner=tmp_path / "never-opened-source")
    try:
        registration = original.execute("status", study_payload(), objective="Synthetic existing study", actor="synthetic")
    finally:
        original.close()
    executable = tmp_path / "mock-native-codex.exe"
    executable.write_bytes(native_bytes())
    data = {"study_record": registration["study_record"], "executable": str(executable),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "receipt": receipt(), "policy": policy(allow=settings.pop("allow", False))}
    engine = Probe(root, config=Config(offline=True))
    engine.calls, engine.settings = [], settings
    return engine, data, registration


def execute(engine, data):
    return engine.execute("status", data, objective="Synthetic non-dispatching admission preflight", actor="synthetic")


def test_real_registered_evidence_recounts_packets_retains_fixed_slots_and_cannot_dispatch(tmp_path):
    engine, data, registration = initialize(tmp_path)
    try:
        result = execute(engine, data)
        saved = engine.ledger.get(result["assessment_record"], subject.ASSESSMENT)
        runtime = engine.ledger.get(result["runtime_record"], subject.RUNTIME)
        prepared = engine.ledger.artifacts.read(saved["prepared_initial_artifact"])
        assert len(engine.calls) == 1 and engine.calls[0][0][-1] == "--version"
        assert runtime["cli_profile"]["cli_binding"]["cli_version"] == "0.120.0"
        assert not runtime["model_identity_observed"] and not runtime["account_authentication_observed"]
        assert result["fresh_potential_invocations"] == result["fixed_slots"]
        assert saved["planned_token_reservations"] == sum(
            engine.runtime["token_counter"].count(t["packet"]["stdin"]) + 2000 for t in prepared["tasks"])
        assert "quota_unit_capacity_unavailable_policy_blocks" in result["blockers"]
        assert "audited_packet_source_history_seed_authority_pending" in result["blockers"]
        assert saved["resources"]["quota"]["remaining_invocations"] is None
        assert saved["resources"]["quota"]["remaining_tokens"] is None
        assert not result["dispatch_authorized"] and saved["account_dollar_cost"] is None
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.execution.ADMISSION_KIND,)).fetchone()
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.execution.MANIFEST_KIND,)).fetchone()
        assert engine.ledger.get(registration["study_record"], subject.study.STUDY)["new_model_calls"] == 0
        assert "Complete synthetic source" not in canonical(result)
        assert not (tmp_path / "never-opened-source").exists()
        # Reusing the exact retained local observation neither reruns --version
        # nor redraws the original four seeds.
        again = execute(engine, data)
        assert again["runtime_record"] == result["runtime_record"] and len(engine.calls) == 1
    finally:
        engine.close()


def test_explicit_bounded_unknown_quota_does_not_invent_history_or_units(tmp_path):
    engine, data, _ = initialize(tmp_path, allow=True, history_gap=True)
    try:
        result = execute(engine, data)
        saved = engine.ledger.get(result["assessment_record"], subject.ASSESSMENT)
        assert result["fresh_potential_invocations"] == result["planned_token_reservations"] == 0
        assert result["unavailable_slots"] == result["fixed_slots"]
        assert "zero_fresh_slots_preserved" in result["blockers"]
        assert "quota_unit_capacity_unavailable_policy_blocks" not in result["blockers"]
        assert not result["dispatch_authorized"] and not saved["upstream_packet_authority_verified"]
        assert saved["resources"]["quota"]["state"] == "unavailable"
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["exhausted", "stale", "outside_window"])
def test_fresh_receipt_and_time_are_separate_blockers_even_with_allow_policy(tmp_path, fault):
    engine, data, _ = initialize(tmp_path, allow=True)
    if fault == "exhausted":
        data["receipt"] = receipt(used=100)
    elif fault == "stale":
        data["receipt"] = receipt(stale=True)
    else:
        data["policy"]["admit_before"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    expected = {"exhausted": "observed_account_limit_exhausted", "stale": "quota_observation_stale",
                "outside_window": "outside_registered_admission_window"}[fault]
    try:
        assert expected in execute(engine, data)["blockers"]
    finally:
        engine.close()


@pytest.mark.parametrize("fault", ["unregistered", "changed_binary", "resource_mismatch", "binary_before_assessment", "bad_version", "boolean_exit", "script_shim", "wrong_hash", "counter_tamper"])
def test_actual_runtime_and_packet_evidence_cannot_be_replaced_by_asserted_hashes(tmp_path, fault):
    settings = {fault: True}
    if fault == "bad_version":
        settings = {"version": "not a Codex CLI version"}
    if fault == "boolean_exit":
        settings = {"exit_code": False}
    engine, data, _ = initialize(tmp_path, **settings)
    if fault == "script_shim":
        Path(data["executable"]).write_bytes(b"#!/script shim")
        data["executable_sha256"] = hashlib.sha256(b"#!/script shim").hexdigest()
    elif fault == "wrong_hash":
        data["executable_sha256"] = digest("not actual bytes")
    try:
        with pytest.raises((AuditError, subject.provider.ResearchError)):
            execute(engine, data)
        assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=?", (subject.ASSESSMENT,)).fetchone()
    finally:
        engine.close()


def test_incomplete_local_probe_is_durable_and_not_automatically_repeated(tmp_path):
    engine, data, _ = initialize(tmp_path, timeout=True)
    try:
        with pytest.raises(subject.subprocess.TimeoutExpired):
            execute(engine, data)
        engine.settings.clear()
        with pytest.raises(AuditError, match="incomplete_runtime_preflight"):
            execute(engine, data)
        assert len(engine.calls) == 1
    finally:
        engine.close()


def test_requires_active_audited_operation_before_any_subprocess_or_file_read():
    with pytest.raises(AuditError, match="active audited operation"):
        subject.observe_runtime(SimpleNamespace(_active=set()), "absent", None, study_record=digest("study"),
            executable="never-read.exe", executable_sha256=digest("binary"))


@pytest.mark.parametrize("raw,selected,shape,exhausted", [
    ({"rateLimits": {"primary": {"usedPercent": 20, "resetsAt": 100}}}, None, "percentage_only", False),
    ({"rateLimits": {"secondary": {"usedPercent": 100}}}, None, "percentage_only", True),
    ({"rateLimitsByLimitId": {"a": {}, "b": {}}}, None, "unavailable_or_ambiguous_bucket", False),
    ({"rateLimitsByLimitId": {"a": {"primary": {"usedPercent": 1}}, "b": {}}}, "a", "percentage_only", False),
    ({"rateLimits": {"primary": {"usedPercent": True}}}, None, "malformed_window", False),
    ({"rateLimits": {"primary": {"usedPercent": -1}}}, None, "malformed_window", False),
    ({"rateLimits": {"primary": {"usedPercent": 1, "resetsAt": False}}}, None, "malformed_window", False),
    ({"error": "unavailable", "rateLimits": {"primary": {"usedPercent": 1}}}, None, "unrecognized", False),
    ({"isError": True, "structuredContent": {"rateLimits": {"primary": {"usedPercent": 1}}}}, None, "unrecognized", False),
    ({"content": [{"type": "text", "text": "not JSON"}]}, None, "unrecognized", False),
])
def test_account_percentage_shapes_never_claim_count_or_token_capacity(raw, selected, shape, exhausted):
    result = subject.quota_percentages(raw, selected)
    assert result["shape"] == shape and result["known_exhausted"] is exhausted
    assert "remaining_tokens" not in result and "remaining_invocations" not in result


def test_dependency_bindings_include_registered_study_provider_packets_and_original_runtime():
    paths = subject.implementation()
    assert {"research/cybercrime_nl/runtime/final_validation_study.py",
        "research/cybercrime_nl/runtime/final_validation_execution.py",
        "research/cybercrime_nl/runtime/final_validation_provider.py",
        "research/cybercrime_nl/runtime/final_validation_admission.py"} <= paths.keys()
