"""Synthetic account coordinator checks; no real CLI, corpus, account or model."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, digest
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_contract as contract  # noqa: E402
import final_validation_execution as execution  # noqa: E402
import final_validation_history as history  # noqa: E402
import final_validation_policy as policy  # noqa: E402
import final_validation_provider as provider  # noqa: E402
from final_validation_design import pair_from_rank  # noqa: E402
from test_final_validation_policy import orders, probability, sampled  # noqa: E402
from test_final_validation_provider import TOKENIZER, events, judgment, stream  # noqa: E402
from test_final_validation_history import inventory, reference  # noqa: E402

NOW = datetime(2026, 10, 24, 1, tzinfo=timezone.utc)
PROFILE = {"cli_binding": {"synthetic": True}, "tokenizer_identity": TOKENIZER}


def resources():
    return {"maximum_invocations": 60, "maximum_token_reservations": 1_000_000,
        "output_token_allowance": 2000, "not_before": "2026-10-24T00:00:00+00:00",
        "admit_before": "2026-10-24T04:00:00+00:00", "unavailable_quota_policy": "block",
        "quota_policy_evidence_sha256": digest("synthetic quota rule"),
        "quota": {"state": "known", "remaining_invocations": 60, "remaining_tokens": 1_000_000,
            "observed_at": "2026-10-24T00:00:00+00:00", "valid_until": "2026-10-24T04:00:00+00:00",
            "evidence_sha256": digest("synthetic quota observation")}}


def manifest(profile=PROFILE, *, count=3, size=3, limits=None, transform=None):
    frame = probability(size)
    sample = sampled(frame, count=count)
    qc = policy.qc_manifest(frame, sample, qc_seed="execution-fixed-before-outcomes")
    primary, diagnostic, _ = orders(sample, qc)
    prefix = policy.initial_prefix_manifest(frame, sample, qc, primary_order=primary,
        diagnostic_order=diagnostic, diagnostic_order_binding=digest("synthetic diagnostic order"))
    docs = [{"document_id": f"d{i}", "title": f"Complete synthetic title {i}",
        "body": f"Synthetic occurrence at site Z, source {i}.\n\nAll source paragraphs remain supplied."} for i in range(size)]
    tasks = []
    for slot in prefix["tasks"]:
        left, right = pair_from_rank(size, slot["pair_rank"])
        documents = [docs[left], docs[right]]
        order = [d["document_id"] for d in documents]
        if slot["kind"] == "qc":
            order.reverse()
        packet = contract.request(documents, order=order, count_tokens=lambda value: len(value) // 4)
        tasks.append({"pair_rank": slot["pair_rank"], "role": slot["kind"], "packet": packet,
            "history": history.resolve_history(execution.source_identity(packet), slot["kind"], [], inventory()),
            "capacity_unavailable": None})
    if transform:
        transform(tasks)
    return execution.build_manifest(scope={"frame_sha256": frame.digest,
        "definition_version": contract.DEFINITION_VERSION, "user_instruction_sha256": digest("synthetic instruction")},
        prefix=prefix, tasks=tasks, cli_profile=profile, resources=limits or resources(),
        upstream_binding=digest("synthetic verified frame and sample registration"))


def rebuild(value, **changes):
    args = {key: value[key] for key in ("scope", "prefix", "cli_profile", "resources", "upstream_binding")}
    args["tasks"] = [{key: task[key] for key in execution.TASK_FIELDS} for task in value["tasks"]]
    return execution.build_manifest(**(args | changes))


def test_initial_frozen_prefix_has_complete_fixed_roles_and_conservative_limits():
    value = manifest(count=50, size=12)
    assert 1 <= len(value["prefix"]["primary_ranks"]) <= 40
    assert len(value["tasks"]) <= value["prefix"]["reserved_invocations"] <= 60
    assert value["planned_token_reservations"] == sum(t["reservation_tokens"] for t in value["tasks"])
    assert not value["generation_token_cap_enforced"] and not value["timeout_guarantees_remote_cancellation"]
    assert value["coordinator_invocations_not_remote_requests"] and value["account_dollar_cost"] is None
    assert execution.validate_manifest(value) == value
    assert {"src/newsresearch/gateway.py", "src/newsresearch/storage.py"} <= value["implementation"].keys()


def test_logical_identity_ignores_order_and_request_but_binds_frame_sources_role():
    value = manifest()
    packet = value["tasks"][0]["packet"]
    reversed_packet = contract.request(packet["documents"], order=list(reversed(packet["document_order"])),
        count_tokens=lambda text: len(text) // 4)
    original = execution.logical_task_id(value["scope_sha256"], packet, "primary")
    assert packet["request_sha256"] != reversed_packet["request_sha256"]
    assert original == execution.logical_task_id(value["scope_sha256"], reversed_packet, "primary")
    assert original != execution.logical_task_id(value["scope_sha256"], packet, "qc")
    assert original != execution.logical_task_id(digest("other frame scope"), packet, "primary")


@pytest.mark.parametrize("fault", ["extra_task", "changed_role_sources", "conditional_rule", "sixty_one",
    "token_plan", "unknown_as_zero", "duplicate_primary_pair", "implementation_changed"])
def test_manifest_rejects_unfrozen_scope_or_resource_changes(fault):
    value = manifest()
    tasks = [{k: t[k] for k in execution.TASK_FIELDS} for t in value["tasks"]]
    prefix, limits = deepcopy(value["prefix"]), deepcopy(value["resources"])
    if fault == "extra_task":
        tasks.append(deepcopy(tasks[0]))
    elif fault == "changed_role_sources":
        dependent = next(t for t in tasks if t["role"] != "primary")
        replacement = next(t for t in tasks if t["pair_rank"] != dependent["pair_rank"])
        dependent["packet"] = replacement["packet"]
    elif fault == "conditional_rule":
        prefix["diagnostic_condition"] = "any failed primary"
        prefix["initial_manifest_sha256"] = digest({k: v for k, v in prefix.items() if k != "initial_manifest_sha256"})
    elif fault == "sixty_one":
        limits["maximum_invocations"] = 61
    elif fault == "token_plan":
        limits["maximum_token_reservations"] = 1
    elif fault == "unknown_as_zero":
        limits["quota"].update(state="unavailable", remaining_invocations=0, remaining_tokens=0)
    elif fault == "duplicate_primary_pair":
        tasks[1]["packet"] = tasks[0]["packet"]
    else:
        value["implementation"]["src/newsresearch/gateway.py"] = "0" * 64
        with pytest.raises(AuditError, match="implementation_changed"):
            execution.validate_manifest(value)
        return
    with pytest.raises(AuditError):
        rebuild(value, tasks=tasks, prefix=prefix, resources=limits)


@pytest.mark.parametrize("role,statuses,expected", [
    ("uncertain_adjudication", [("resolved", 1)], "condition_false"),
    ("uncertain_adjudication", [("epistemic_unknown", None)], "eligible"),
    ("uncertain_adjudication", [("invalid", None)], "condition_false_technical_or_provenance_unavailable"),
    ("qc_adjudication", [("resolved", 0), ("resolved", 1)], "eligible"),
    ("qc_adjudication", [("resolved", 1), ("resolved", 1)], "condition_false"),
    ("qc_adjudication", [("epistemic_unknown", None), ("resolved", 1)], "eligible"),
    ("qc_adjudication", [("provenance_unavailable", None), ("resolved", 1)], "condition_false_technical_or_provenance_unavailable"),
    ("qc_adjudication", [("resolved", 1)], "dependency_pending_or_unreturned"),
])
def test_fixed_conditional_roles_never_repair_technical_failures(role, statuses, expected):
    evidence = {(7, name): {"status": status, "positive": positive}
        for name, (status, positive) in zip(("primary", "qc"), statuses)}
    assert execution.conditional_state({"pair_rank": 7, "role": role}, evidence) == expected


class SyntheticStudy(Research):
    fixture = None

    @audited_handler
    def _status(self, session, context, data):
        fixture = self.fixture
        fixture.study = self
        instance = provider.PairProvider(self.ledger.root / "synthetic-workers", research=self, session=session,
            runner=fixture.runner, **fixture.config)
        saved = execution.rows(self, session, execution.MANIFEST_KIND)
        if saved:
            identifier = saved[0]["_record_id"]
            value = saved[0]["manifest"]
            if fixture.replacement:
                execution.retain_manifest(self, session, fixture.replacement, versions=saved[0]["versions"])
        else:
            value = manifest({"cli_binding": instance.cli_binding, "tokenizer_identity": instance.tokenizer_identity},
                             limits=fixture.limits, transform=fixture.task_transform)
            references = {name: self.ledger.record(session, "synthetic_upstream_verification", name,
                {"synthetic": True, "method": "Fixture only, not real source verification."})
                for name in ("source_snapshot", "history_inventory", "verification_protocol")}
            admission = {"method": execution.METHOD, "scope_sha256": value["scope_sha256"],
                "prefix_sha256": value["prefix"]["initial_manifest_sha256"],
                "slot_catalog_sha256": value["slot_catalog_sha256"], **references}
            if fixture.admission_fault:
                admission[fixture.admission_fault] = digest("changed synthetic admission")
            upstream = self.ledger.record(session, execution.ADMISSION_KIND, "synthetic-upstream", admission)
            for task in value["tasks"]:
                if task["capacity_unavailable"]:
                    assert self.ledger.artifacts.put(fixture.capacity_evidence) == task["capacity_unavailable"]["evidence_sha256"]
            value = rebuild(value, upstream_binding=upstream)
            content = {
                "protocol": {"method": execution.METHOD,
                    "execution_manifest_sha256": value["manifest_sha256"],
                    "scope_sha256": value["scope_sha256"], "implementation_sha256": digest(value["implementation"]),
                    "description": "Synthetic frozen initial pair validation; no real CLI or model."},
                "policy": {"execution_manifest_sha256": value["manifest_sha256"],
                    "allow_codex_account_execution": fixture.policy_allowed,
                    "user_instruction_sha256": value["scope"]["user_instruction_sha256"]},
                "selection": {"rules": "Synthetic pre-label frame, sample and fixed branch manifest.",
                    "upstream_admission": upstream, "slot_catalog_sha256": value["slot_catalog_sha256"]},
                "prompt": {"instructions": contract.TASK},
                "dossier_definition": {"unit": contract.DEFINITION_VERSION}}
            if fixture.protocol_fault:
                content["protocol"][fixture.protocol_fault] = "unrelated synthetic registration"
            versions = {kind: self._version(session, context, {"kind": kind, "key": "synthetic-final-" + kind,
                "content": payload})["id"] for kind, payload in content.items()}
            identifier = execution.retain_manifest(self, session, value, versions=versions)
        worker = execution.Execution(self, session, identifier, instance, now=lambda: fixture.now)
        fixture.worker = worker
        if data.get("prepare"):
            return {"manifest": identifier, "plan": value, "accounting": worker.accounting()}
        return worker.run(allow_account_execution=data.get("allow", True))


@pytest.fixture
def rig(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    binary = tmp_path / "synthetic-codex.exe"
    binary.write_bytes(b"Synthetic identity only; this fixture is never executed.")
    fixture = SimpleNamespace(root=tmp_path / "owner", calls=[], outcomes=[], limits=resources(), now=NOW,
        replacement=None, policy_allowed=True, protocol_fault=None, task_transform=None,
        admission_fault=None, capacity_evidence={"synthetic": "capacity proof"})
    fixture.config = {"executable": binary, "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "cli_version_observation": {"command": [str(binary), "--version"], "stdout": "codex-cli 0.120.0\n",
                                    "stderr": "", "exit_code": 0},
        "tokenizer_identity": TOKENIZER, "count_tokens": lambda text: len(text) // 4}

    def runner(*args, **kwargs):
        # Real protected ledger and shared gateway must have persisted the exact
        # packet/request/stdin/schema/argv intent before the mocked subprocess.
        pending = list(fixture.study.ledger.unresolved.values())
        assert len(pending) == 1
        intended = pending[0]
        retained = fixture.study.ledger.artifacts.read(intended["dispatch"])
        assert retained["stdin"] == kwargs["input"]
        assert retained["command"] == list(args[0])
        request = fixture.study.ledger.artifacts.read(intended["request"])
        assert kwargs["input"] == contract.cli_prompt(request)
        fixture.calls.append({"intended": deepcopy(intended), "stdin": kwargs["input"], "command": args[0]})
        outcome = fixture.outcomes.pop(0) if fixture.outcomes else "valid"
        if isinstance(outcome, Exception):
            raise outcome
        value = events()
        if outcome == "unknown_model":
            value[0].pop("model")
        elif outcome == "no_usage":
            value[-1].pop("usage")
        elif outcome == "overrun":
            value[-1]["usage"]["output_tokens"] = 20_000
        elif outcome == "invalid":
            response = judgment()
            response["relationship"]["citations"] = []
            value[-2]["item"]["text"] = json.dumps(response)
        elif outcome == "epistemic":
            response = judgment()
            response["relationship"]["label"] = "uncertain"
            value[-2]["item"]["text"] = json.dumps(response)
        return SimpleNamespace(stdout=stream(value), stderr="", returncode=0)

    fixture.runner = runner
    return fixture


def operate(rig, data=None, *, hook=None):
    study = SyntheticStudy(rig.root, config=Config(offline=True))
    study.fixture = rig
    try:
        if hook:
            hook(study)
        return study.execute("status", data or {}, objective="Synthetic initial-tranche coordinator verification",
                             actor="test:synthetic")
    finally:
        study.close()


def test_registered_real_gateway_full_tranche_and_reopen_never_redispatch(rig):
    first = operate(rig)
    assert first["stop_reason"] == "fixed_tranche_processed" and first["selected_primary_units"] == 3
    assert first["coordinator_invocations"] == first["states"]["resolved"] == len(rig.calls)
    assert first["durably_uncompleted_intents"] == first["unreturned_attempts"] == 0
    count = len(rig.calls)
    second = operate(rig)
    assert second["coordinator_invocations"] == count == len(rig.calls)
    assert second["reservation_tokens"] == first["reservation_tokens"] > second["observed_token_units"]
    assert second["statistical_look"] is False and second["account_dollar_cost"] is None


def test_same_owner_rejects_changed_packet_order_or_new_scope_instead_of_reset(rig):
    prepared = operate(rig, {"prepare": True})
    old = prepared["plan"]
    tasks = [{k: t[k] for k in execution.TASK_FIELDS} for t in old["tasks"]]
    packet = tasks[0]["packet"]
    tasks[0]["packet"] = contract.request(packet["documents"], order=list(reversed(packet["document_order"])),
        count_tokens=lambda text: len(text) // 4)
    rig.replacement = rebuild(old, tasks=tasks)
    assert rig.replacement["tasks"][0]["logical_task_id"] == old["tasks"][0]["logical_task_id"]
    with pytest.raises(AuditError, match="registered_execution_protocol_required|registered_account_policy_required|cannot_change"):
        operate(rig)
    assert not rig.calls


@pytest.mark.parametrize("fault,reason", [
    ("known_low", "known_quota_insufficient"), ("unknown", "quota_unavailable"),
    ("quota_stale", "quota_observation_stale"), ("deadline", "admission_deadline"),
    ("before", "admission_not_started"), ("stop", "user_stop")])
def test_resource_or_stop_gate_precedes_every_intent(rig, fault, reason):
    if fault == "known_low":
        rig.limits["quota"]["remaining_invocations"] = 0
    elif fault == "unknown":
        rig.limits["quota"].update(state="unavailable", remaining_invocations=None, remaining_tokens=None)
    elif fault == "quota_stale":
        rig.limits["quota"]["valid_until"] = "2026-10-24T00:30:00+00:00"
    elif fault == "deadline":
        rig.limits["admit_before"] = "2026-10-24T00:30:00+00:00"
    elif fault == "before":
        rig.now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    else:
        operate(rig, {"prepare": True})
        (rig.root / "STOP").write_text("Synthetic stop")
    report = operate(rig)
    assert reason in report["stop_reason"] and report["coordinator_invocations"] == 0 and not rig.calls


def test_unknown_quota_requires_explicit_registered_bounded_policy_and_stays_null(rig):
    rig.limits["quota"].update(state="unavailable", remaining_invocations=None, remaining_tokens=None)
    rig.limits["unavailable_quota_policy"] = "allow_bounded_registered"
    report = operate(rig)
    assert report["quota_state"] == "unavailable" and report["stop_reason"] == "fixed_tranche_processed"
    assert len(rig.calls) <= 60 and report["account_quota_is_shared_and_may_change"]


@pytest.mark.parametrize("fault,reason", [("overrun", "token_allowance_exceeded"),
    ("no_usage", "usage_unavailable"), ("unknown_model", "reference_provenance_unavailable"),
    ("timeout", "unknown_outcome")])
def test_unknown_usage_provenance_or_overrun_stops_and_preserves_reservation_across_reopen(rig, fault, reason):
    rig.outcomes = [subprocess.TimeoutExpired("synthetic", 600) if fault == "timeout" else fault]
    first = operate(rig)
    assert reason in first["stop_reason"] and len(rig.calls) == 1
    assert first["reservation_tokens"] > 0 and first["committed_token_units"] >= first["reservation_tokens"]
    if fault == "overrun":
        assert first["committed_token_units"] > first["reservation_tokens"]
    if fault in {"timeout", "no_usage"}:
        assert first["usage_unavailable_attempts"] == 1
    if fault == "timeout":
        assert first["states"]["technical_unavailable"] == 1 and first["durably_uncompleted_intents"] == 1
    second = operate(rig)
    assert reason in second["stop_reason"] and len(rig.calls) == 1
    assert second["committed_token_units"] == first["committed_token_units"]


@pytest.mark.parametrize("gap", ["generic_before_cache", "custom_before_gateway", "result_before_completion", "result_before_halt"])
def test_durable_crash_gaps_never_retry_or_proceed_after_reopen(rig, gap):
    def hook(study):
        append, record = study.ledger.append, study.ledger.record

        def guarded_append(session, kind, payload, project=None):
            if gap == "result_before_completion" and kind == "model.attempt.completed":
                raise RuntimeError("synthetic interruption before completion")
            result = append(session, kind, payload, project)
            if gap == "generic_before_cache" and kind == "model.attempt.intended":
                assert not study.ledger.unresolved
                raise RuntimeError("synthetic lost append acknowledgement")
            return result

        def guarded_record(session, kind, key, payload, supersedes=None):
            if gap == "result_before_halt" and kind == execution.HALT_KIND:
                raise RuntimeError("synthetic interruption before halt")
            result = record(session, kind, key, payload, supersedes)
            if gap == "custom_before_gateway" and kind == execution.INTENT_KIND:
                raise RuntimeError("synthetic interruption before dispatch")
            return result

        study.ledger.append, study.ledger.record = guarded_append, guarded_record

    if gap == "result_before_halt":
        rig.outcomes = ["overrun"]
    with pytest.raises(RuntimeError, match="synthetic"):
        operate(rig, hook=hook)
    calls = len(rig.calls)
    report = operate(rig)
    assert calls == len(rig.calls) and report["coordinator_invocations"] == 1
    assert report["reservation_tokens"] > 0
    if gap in {"generic_before_cache", "custom_before_gateway"}:
        assert report["stop_reason"] == "unreturned_intent_unknown_outcome" and report["unreturned_attempts"] == 1
    elif gap == "result_before_completion":
        assert report["stop_reason"] == "durable_completion_missing"
        assert report["states"]["resolved"] == 1 and report["durably_uncompleted_intents"] == 1
    else:
        assert report["stop_reason"] == "retained_terminal_result:token_allowance_exceeded"


def test_same_process_durable_generic_append_without_cache_is_authoritative(rig):
    def hook(study):
        append = study.ledger.append
        def guarded(session, kind, payload, project=None):
            result = append(session, kind, payload, project)
            if kind == "model.attempt.intended":
                assert study.ledger.unresolved == {}
                assert rig.worker.blocker() == "unreturned_intent_unknown_outcome"
                raise RuntimeError("synthetic same-process gap")
            return result
        study.ledger.append = guarded
    with pytest.raises(RuntimeError, match="same-process"):
        operate(rig, hook=hook)
    assert not rig.calls


def test_explicit_runtime_permission_and_registered_policy_required(rig):
    with pytest.raises(AuditError, match="explicit_account_execution"):
        operate(rig, {"allow": False})
    assert not rig.calls


def test_unapproved_policy_cannot_create_execution_manifest(rig):
    rig.policy_allowed = False
    with pytest.raises(AuditError, match="registered_account_policy"):
        operate(rig)
    assert not rig.calls


@pytest.mark.parametrize("field", ["method", "execution_manifest_sha256", "scope_sha256", "implementation_sha256"])
def test_unrelated_protocol_registration_cannot_authorize_manifest_or_dispatch(rig, field):
    rig.protocol_fault = field
    with pytest.raises(AuditError, match="registered_execution_protocol_required"):
        operate(rig)
    assert not rig.calls


def test_invalid_reference_is_not_negative_or_replacement_and_no_adjudication_repair(rig):
    rig.outcomes = ["invalid"]
    report = operate(rig)
    assert report["states"]["invalid"] == 1 and report["states"].get("condition_false_technical_or_provenance_unavailable", 0) >= 1
    invalid_intent = rig.calls[0]["intended"]
    assert sum(call["intended"]["task_key"] == invalid_intent["task_key"] for call in rig.calls) == 1
    assert report["stop_reason"] == "fixed_tranche_processed"


def test_usage_units_missing_malformed_and_reasoning_overlap_are_explicit():
    assert execution.usage_units(None) is None
    assert execution.usage_units({"input_tokens": 0, "output_tokens": None}) is None
    assert execution.usage_units({"input_tokens": True, "output_tokens": 1}) is None
    assert execution.usage_units({"input_tokens": 10, "output_tokens": 20, "reasoning_output_tokens": 15}) == 45


@pytest.mark.parametrize("fault", ["wrong_model", "wrong_request", "unexpected_parser_exception"])
def test_identity_or_adapter_fault_is_terminal_even_with_known_usage_and_payload(rig, monkeypatch, fault):
    original = provider.PairProvider.parse_response
    def damaged(instance, invocation, response):
        if fault == "unexpected_parser_exception":
            raise KeyError("synthetic field")
        raw = deepcopy(response.raw_response)
        if fault == "wrong_model":
            raw["observed_model"] = "gpt-6-luna"
            response = replace(response, model="gpt-6-luna", raw_response=raw)
        else:
            raw["request_sha256"] = "0" * 64
            response = replace(response, raw_response=raw)
        return original(instance, invocation, response)
    monkeypatch.setattr(provider.PairProvider, "parse_response", damaged)
    report = operate(rig)
    assert "reference_identity_or_adapter_failure" in report["stop_reason"]
    assert report["states"]["invalid"] == 1 and len(rig.calls) == 1
    assert report["usage_unavailable_attempts"] == 0
    second = operate(rig)
    assert "reference_identity_or_adapter_failure" in second["stop_reason"] and len(rig.calls) == 1


def reuse_slots(tasks, *, change=None):
    for task in tasks:
        p = task["packet"]
        row = reference(p, role=task["role"], identity=f"{task['pair_rank']}:{task['role']}")
        if change:
            change(task, row)
        task["history"] = history.resolve_history(execution.source_identity(p), task["role"], [row], inventory())
        task["packet"] = None


def test_all_compatible_slots_reused_with_zero_new_invocations_usage_and_no_duplicate_on_reopen(rig):
    rig.task_transform = reuse_slots
    rig.limits["quota"].update(remaining_invocations=0, remaining_tokens=0)
    first = operate(rig)
    assert first["stop_reason"] == "fixed_tranche_processed"
    assert first["selected_primary_units"] == 3 and first["slot_dispositions"]["reused"] == first["fixed_task_slots"]
    assert first["coordinator_invocations"] == first["observed_token_units"] == first["reservation_tokens"] == 0
    assert first["local_slot_resolution_records"] == first["fixed_task_slots"] and not rig.calls
    second = operate(rig)
    assert second["local_slot_resolution_records"] == first["local_slot_resolution_records"]
    assert second["coordinator_invocations"] == 0 and not rig.calls
    study = Research(rig.root, config=Config(offline=True))
    try:
        observations = study.ledger.artifacts.read(second["reference_observations_artifact"])
        assert sum(row["role"] == "primary" and row["positive"] == 1 for row in observations) == 3
        assert len({row["record_id"] for row in observations}) == len(observations)
        assert not study.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended'").fetchone()
    finally:
        study.close()


def test_prior_technical_unavailability_stays_selected_without_replacement_or_diagnostic(rig):
    def transform(tasks):
        def prior_intent(task, row):
            if task["role"] == "primary":
                row.update(attempt_state="intent", payload=None, provenance=None)
        reuse_slots(tasks, change=prior_intent)
    rig.task_transform = transform
    report = operate(rig)
    assert report["states"]["technical_unavailable"] == 3
    assert report["states"]["condition_false_technical_or_provenance_unavailable"] >= 1
    assert report["selected_primary_units"] == 3 and report["coordinator_invocations"] == 0 and not rig.calls


def test_historical_clean_epistemic_unknown_enables_only_fixed_new_diagnostic_slot(rig):
    def transform(tasks):
        diagnostic = next(t for t in tasks if t["role"] == "uncertain_adjudication")
        rank = diagnostic["pair_rank"]
        for task in tasks:
            if task["pair_rank"] == rank and task["role"] == "primary":
                row = reference(task["packet"], label="uncertain", identity="one-clean-uncertain")
                task["history"] = history.resolve_history(execution.source_identity(task["packet"]), "primary", [row], inventory())
                task["packet"] = None
    rig.task_transform = transform
    report = operate(rig)
    primary_ranks = {row["intended"]["pair_rank"] for row in rig.calls if row["intended"]["role"] == "primary"}
    diagnostics = [row for row in rig.calls if row["intended"]["role"] == "uncertain_adjudication"]
    assert len(primary_ranks) == 2 and len(diagnostics) == 1
    assert diagnostics[0]["intended"]["pair_rank"] not in primary_ranks
    assert report["states"]["epistemic_unknown"] == 1 and report["selected_primary_units"] == 3
    count = len(rig.calls)
    operate(rig)
    assert len(rig.calls) == count


def test_capacity_blocked_primary_has_no_packet_attempt_or_replacement_but_keeps_denominator(rig):
    def transform(tasks):
        for task in tasks:
            if task["role"] == "primary":
                task["capacity_unavailable"] = {"reason_code": "full_pair_capacity", "evidence_sha256": digest(rig.capacity_evidence)}
                task["packet"] = None
    rig.task_transform = transform
    report = operate(rig)
    assert report["selected_primary_units"] == 3 and report["states"]["technical_unavailable"] == 3
    assert not any(call["intended"]["role"] in {"primary", "uncertain_adjudication", "qc_adjudication"} for call in rig.calls)
    assert report["slot_dispositions"]["unavailable"] == 3


@pytest.mark.parametrize("label", ["same_event", "uncertain"])
def test_same_physical_judgment_cannot_fill_primary_and_independent_qc(label):
    def transform(tasks):
        selected = next(t for t in tasks if t["role"] == "qc")
        pair = [t for t in tasks if t["pair_rank"] == selected["pair_rank"] and t["role"] in {"primary", "qc"}]
        assert len(pair) == 2
        for task in pair:
            # Each individual lookup validates, but cross-slot independence must
            # reject the same physical request relabeled by separate callers.
            row = reference(task["packet"], role=task["role"], identity="same-physical", label=label)
            task["history"] = history.resolve_history(execution.source_identity(task["packet"]), task["role"], [row], inventory())
            task["packet"] = None
    with pytest.raises(AuditError, match="independent_roles_share_physical_judgment"):
        manifest(count=50, size=12, transform=transform)


@pytest.mark.parametrize("field", ["method", "scope_sha256", "prefix_sha256", "slot_catalog_sha256"])
def test_bare_catalog_cannot_bypass_exact_registered_parent_admission(rig, field):
    rig.admission_fault = field
    with pytest.raises(AuditError, match="upstream_slot_admission_binding"):
        operate(rig)
    assert not rig.calls


def test_fresh_slot_without_packet_or_capacity_evidence_is_not_silently_dropped():
    def transform(tasks):
        tasks[0]["packet"] = None
    with pytest.raises(AuditError, match="fresh_packet_required"):
        manifest(transform=transform)


def test_physical_full_pair_reference_cannot_be_reassigned_to_another_pair():
    def transform(tasks):
        for task in [t for t in tasks if t["role"] == "primary"][:2]:
            row = reference(task["packet"], identity="same-attempt-other-inputs")
            task["history"] = history.resolve_history(execution.source_identity(task["packet"]), task["role"], [row], inventory())
            task["packet"] = None
    with pytest.raises(AuditError, match="independent_roles_share_physical_judgment"):
        manifest(transform=transform)


def test_partial_local_slot_materialization_resumes_without_fabricating_attempts(rig):
    rig.task_transform = reuse_slots
    def hook(study):
        record = study.ledger.record
        def guarded(session, kind, key, payload, supersedes=None):
            result = record(session, kind, key, payload, supersedes)
            if kind == execution.SLOT_KIND:
                raise RuntimeError("synthetic interruption after one local slot")
            return result
        study.ledger.record = guarded
    with pytest.raises(RuntimeError, match="after one local slot"):
        operate(rig, hook=hook)
    assert not rig.calls
    report = operate(rig)
    assert report["local_slot_resolution_records"] == report["fixed_task_slots"]
    assert report["coordinator_invocations"] == 0 and not rig.calls
