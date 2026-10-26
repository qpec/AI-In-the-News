"""Audited local/account evidence and packet-resource assessment, never dispatch.

This new extension does not modify the initialized Study or its frozen helpers.
All persistence and the non-model --version probe require Research.execute and a
separate registered preflight protocol. Quota receipts are imported exact app
observations, not independently authenticated here; percentages never become
task/token capacity. The complete audited packet parent is still pending, so no
function creates an execution admission/manifest or authorizes account calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess

import final_validation_execution as execution
import final_validation_packets as packets
import final_validation_provider as provider
import final_validation_study as study
from newsresearch.common import AuditError, digest, require_active, require_no_credentials, utc

METHOD = "cybercrime-final-validation-admission-preflight-v1"
RUNTIME_INTENT = "cyber_final_validation_runtime_preflight_intent"
RUNTIME = "cyber_final_validation_runtime_evidence"
QUOTA = "cyber_final_validation_quota_receipt"
POLICY = "cyber_final_validation_resource_policy"
ASSESSMENT = "cyber_final_validation_packet_resource_assessment"
ROOT = Path(__file__).resolve().parents[3]


def require(value, code):
    if not value:
        raise AuditError("final_admission_" + code)


def implementation():
    return {**study.implementation(), Path(__file__).relative_to(ROOT).as_posix():
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def protocol_content(study_record):
    execution.sha(study_record)
    return {"method": METHOD, "implementation": implementation(), "study_record": study_record,
            "scope": "local-evidence-and-packet-resource-assessment-only", "model_dispatch_authorized": False}


def _registered(engine, session, context, study_record):
    require_active(engine, session)
    require(engine.ledger.get(context.versions["protocol"], "protocol")["content"] == protocol_content(study_record),
            "registered_preflight_protocol_required")
    saved = engine.ledger.get(study_record, study.STUDY)
    # Invoke the frozen verifier on this already-open ledger; no source owner is
    # constructed or read, and no seeds/versions are regenerated.
    view = object.__new__(study.Study)
    view.ledger, view.source_owner = engine.ledger, Path(saved["source_owner"])
    require(view._registration()["id"] == study_record, "original_study_binding")
    return saved


def _once(engine, session, kind, key, value):
    rows = list(engine.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, key)))
    require(len(rows) <= 1, "duplicate_evidence_record")
    if rows:
        require(engine.ledger.get(rows[0][0], kind) == value, "immutable_evidence_changed")
        return rows[0][0]
    return engine.ledger.record(session, kind, key, value)


def _native_bytes(path, expected):
    require(path.is_absolute() and path.suffix.lower() == ".exe"
            and not any(p.is_symlink() or p.is_junction() for p in [path, *path.parents]), "native_executable_required")
    raw = path.read_bytes()
    # An explicit native PE avoids treating an npm/PowerShell shim hash as the
    # executable bundle identity. This is format/hash evidence, not publisher trust.
    offset = int.from_bytes(raw[60:64], "little") if len(raw) >= 64 else -1
    require(raw[:2] == b"MZ" and offset >= 64 and raw[offset:offset + 4] == b"PE\0\0", "native_pe_required")
    require(hashlib.sha256(raw).hexdigest() == expected, "executable_hash_changed")
    return len(raw)


def observe_runtime(engine, session, context, *, study_record, executable, executable_sha256):
    """Actually hash the selected local native binary, run only --version, and
    verify the offline tokenizer. Synthetic tests patch subprocess.run only.
    No account login/status, credential file, source owner or model is inspected.
    """
    _registered(engine, session, context, study_record)
    execution.sha(executable_sha256)
    path = Path(executable)
    size = _native_bytes(path, executable_sha256)
    intended = {"method": METHOD, "study_record": study_record, "executable": str(path),
        "binary_sha256": executable_sha256, "command": [str(path), "--version"], "timeout_seconds": 10,
        "protocol": context.versions["protocol"], "implementation": implementation(), "model_calls": 0}
    key = digest(intended)
    prior = list(engine.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (RUNTIME, key)))
    if prior:
        require(len(prior) == 1, "duplicate_runtime_evidence")
        saved = engine.ledger.get(prior[0][0], RUNTIME)
        require(saved["intended"] == intended, "runtime_evidence_changed")
        return _runtime_result(engine, prior[0][0])
    require(not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=? AND logical_key=?", (RUNTIME_INTENT, key)).fetchone(),
            "incomplete_runtime_preflight_requires_diagnosis")
    intent_id = engine.ledger.record(session, RUNTIME_INTENT, key, intended)
    result = subprocess.run(intended["command"], capture_output=True, text=True, timeout=10, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    observation = {"command": intended["command"], "stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
    require(type(result.returncode) is int and isinstance(result.stdout, str) and isinstance(result.stderr, str)
            and len(result.stdout.encode()) + len(result.stderr.encode()) <= 4096, "version_output_capacity")
    require_no_credentials(observation)
    observation_ref = engine.ledger.artifacts.put(observation)
    version = provider.version_from_observation(path, observation)
    require(version is not None, "version_required")
    _native_bytes(path, executable_sha256)
    identity = {"encoding": "cl100k_base", "library": "tiktoken", "version": importlib.metadata.version("tiktoken")}
    counter = packets.load_token_counter(evidence_record=intent_id, expected_identity=identity)
    configuration = counter.validate()
    value = {"method": METHOD, "study_record": study_record, "intended": intended, "intent_record": intent_id,
        "observed_at": utc(), "version_observation_artifact": observation_ref,
        "cli_profile": {"cli_binding": {"executable": str(path), "binary_sha256": executable_sha256,
            "version_observation": observation, "cli_version": version}, "tokenizer_identity": identity},
        "tokenizer_configuration_sha256": configuration, "vocabulary_sha256": packets.VOCAB_HASH,
        "binary_bytes": size, "native_format": "PE", "publisher_identity_verified": False,
        "account_authentication_observed": False, "model_identity_observed": False,
        "configured_model": provider.contract.MODEL, "reasoning_effort": provider.contract.REASONING_EFFORT,
        "account_dollar_cost": None, "model_calls": 0, "source_access": False, "dispatch_authorized": False}
    identifier = engine.ledger.record(session, RUNTIME, key, value)
    return _runtime_result(engine, identifier)


def _runtime_result(engine, record):
    saved = engine.ledger.get(record, RUNTIME)
    require(saved["intended"]["implementation"] == implementation(), "runtime_implementation_changed")
    intended = engine.ledger.get(saved["intent_record"], RUNTIME_INTENT)
    require(intended == saved["intended"] and intended["study_record"] == saved["study_record"]
            and engine.ledger.get(intended["protocol"], "protocol")["content"] == protocol_content(saved["study_record"]),
            "runtime_intent_binding")
    observed = engine.ledger.artifacts.read(saved["version_observation_artifact"])
    expected_cli = {"executable": intended["executable"], "binary_sha256": intended["binary_sha256"],
        "version_observation": observed, "cli_version": provider.version_from_observation(Path(intended["executable"]), observed)}
    require(observed == saved["cli_profile"]["cli_binding"]["version_observation"]
            and saved["cli_profile"]["cli_binding"] == expected_cli,
            "retained_version_observation_changed")
    counter = packets.load_token_counter(evidence_record=record, expected_identity=saved["cli_profile"]["tokenizer_identity"])
    require(counter.validate() == saved["tokenizer_configuration_sha256"] and saved["vocabulary_sha256"] == packets.VOCAB_HASH,
            "retained_tokenizer_changed")
    return {"runtime_record": record, "cli_profile": saved["cli_profile"], "token_counter": counter}


def quota_percentages(raw, selected_limit_id=None):
    """Bounded app-result projection; no percentage-to-token/call conversion.
    Unsupported/ambiguous responses remain unavailable, not zero or sufficient.
    """
    if isinstance(raw, dict) and (raw.get("isError") is True or raw.get("error") is not None):
        return {"windows": [], "known_exhausted": False, "shape": "unrecognized"}
    payload = raw
    if isinstance(raw, dict) and isinstance(raw.get("structuredContent"), dict):
        payload = raw["structuredContent"]
    elif isinstance(raw, dict) and isinstance(raw.get("content"), list):
        blocks = raw["content"]
        if len(blocks) == 1 and isinstance(blocks[0], dict) and blocks[0].get("type") == "text":
            try:
                payload = json.loads(blocks[0]["text"])
            except (ValueError, KeyError, TypeError):
                return {"windows": [], "known_exhausted": False, "shape": "unrecognized"}
    if not isinstance(payload, dict) or payload.get("error") is not None or payload.get("isError") is True:
        return {"windows": [], "known_exhausted": False, "shape": "unrecognized"}
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and buckets:
        selected = selected_limit_id if selected_limit_id is not None else next(iter(buckets)) if len(buckets) == 1 else None
        bucket = buckets.get(selected)
    else:
        bucket = payload.get("rateLimits") if selected_limit_id is None else None
    if not isinstance(bucket, dict):
        return {"windows": [], "known_exhausted": False, "shape": "unavailable_or_ambiguous_bucket"}
    windows = []
    for name in ("primary", "secondary"):
        row = bucket.get(name)
        if row is None:
            continue
        used = row.get("usedPercent") if isinstance(row, dict) else None
        if type(used) not in (int, float) or not math.isfinite(used) or not 0 <= used <= 100:
            return {"windows": [], "known_exhausted": False, "shape": "malformed_window"}
        reset = row.get("resetsAt")
        if reset is not None and (type(reset) is not int or reset < 0):
            return {"windows": [], "known_exhausted": False, "shape": "malformed_window"}
        windows.append({"window": name, "used_percent": used, "remaining_percent": 100 - used, "resets_at": reset})
    return {"windows": windows, "known_exhausted": any(r["used_percent"] == 100 for r in windows),
            "shape": "percentage_only" if windows else "unavailable"}


def retain_quota_receipt(engine, session, context, *, study_record, receipt):
    """Import exact tool evidence as an asserted observation, not a fake probe.
    The orchestrator must actually obtain the named app output before import;
    this helper cannot authenticate its transcript origin or access that account.
    """
    _registered(engine, session, context, study_record)
    require(isinstance(receipt, dict) and set(receipt) == {"source", "source_reference", "captured_at", "selected_limit_id", "raw_result"}
            and receipt["source"] == "codex_app_get_usage_limits"
            and isinstance(receipt["source_reference"], str) and bool(receipt["source_reference"].strip())
            and (receipt["selected_limit_id"] is None or isinstance(receipt["selected_limit_id"], str)), "quota_receipt_fields")
    require(execution.timestamp(receipt["captured_at"]) <= datetime.now(timezone.utc), "future_quota_receipt")
    require_no_credentials(receipt)
    exact = engine.ledger.artifacts.put(receipt)
    value = {"method": METHOD, "study_record": study_record, "receipt_artifact": exact,
        "captured_at": receipt["captured_at"], "percentage_observation": quota_percentages(receipt["raw_result"], receipt["selected_limit_id"]),
        "unit_capacity_state": "unavailable", "remaining_invocations": None, "remaining_tokens": None,
        "origin_independently_authenticated": False, "account_dollar_cost": None, "new_account_probe_by_helper": False}
    return _once(engine, session, QUOTA, digest([study_record, exact]), value)


def retain_resource_policy(engine, session, context, *, study_record, policy):
    registered = _registered(engine, session, context, study_record)
    require(isinstance(policy, dict), "policy_fields")
    policy = {"unavailable_quota_policy": "block", **policy}
    require(isinstance(policy, dict) and set(policy) == {"maximum_invocations", "maximum_token_reservations", "output_token_allowance",
        "not_before", "admit_before", "quota_valid_for_seconds", "unavailable_quota_policy", "decision_note"}, "policy_fields")
    for field in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance", "quota_valid_for_seconds"):
        execution.integer(policy[field], 1)
    require(policy["maximum_invocations"] <= 60 and execution.timestamp(policy["not_before"]) < execution.timestamp(policy["admit_before"]), "policy_limits")
    require(policy["unavailable_quota_policy"] in {"block", "allow_bounded_registered"}
        and isinstance(policy["decision_note"], str) and policy["decision_note"].strip(), "explicit_quota_policy_required")
    require_no_credentials(policy)
    value = {"method": METHOD, "study_record": study_record, "policy": policy,
        "instruction_evidence_artifact": registered["instruction_evidence_artifact"], "protocol": context.versions["protocol"],
        "account_only": True, "paid_api_fallback": False, "quota_purchase_or_reset": False,
        "initial_primary_limit": 40, "initial_task_limit": 60, "dispatch_authorized": False}
    return _once(engine, session, POLICY, study_record, value)


def resources_from_evidence(engine, session, context, *, study_record, quota_record, policy_record):
    _registered(engine, session, context, study_record)
    quota, policy = engine.ledger.get(quota_record, QUOTA), engine.ledger.get(policy_record, POLICY)
    require(quota["study_record"] == policy["study_record"] == study_record, "resource_study_changed")
    receipt = engine.ledger.artifacts.read(quota["receipt_artifact"])
    require(quota["percentage_observation"] == quota_percentages(receipt["raw_result"], receipt["selected_limit_id"])
        and quota["captured_at"] == receipt["captured_at"], "quota_projection_changed")
    chosen = policy["policy"]
    resources = {key: chosen[key] for key in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance",
        "not_before", "admit_before", "unavailable_quota_policy")}
    resources.update(quota_policy_evidence_sha256=digest(policy), quota={"state": "unavailable", "remaining_invocations": None,
        "remaining_tokens": None, "observed_at": quota["captured_at"],
        "valid_until": (execution.timestamp(quota["captured_at"]) + timedelta(seconds=chosen["quota_valid_for_seconds"])).isoformat(),
        "evidence_sha256": digest(quota)})
    execution.validate_resources(resources)
    return resources


def assess_packet_resources(engine, session, context, *, study_record, prepared, runtime_record, quota_record, policy_record):
    """Retain/recount actual complete packets; never manufacture upstream proof.
    The eventual audited packet parent must independently establish source/frame/
    history/seed authority. This record is deliberately NOT ADMISSION_KIND.
    """
    registered = _registered(engine, session, context, study_record)
    require(type(prepared) is packets.PreparedInitial, "prepared_initial_required")
    runtime = _runtime_result(engine, runtime_record)
    saved_runtime = engine.ledger.get(runtime_record, RUNTIME)
    require(saved_runtime["study_record"] == study_record, "runtime_study_changed")
    cli = runtime["cli_profile"]["cli_binding"]
    _native_bytes(Path(cli["executable"]), cli["binary_sha256"])
    resources = resources_from_evidence(engine, session, context, study_record=study_record,
        quota_record=quota_record, policy_record=policy_record)
    value = prepared.payload
    require(value["cli_profile"] == runtime["cli_profile"] and value["resources"] == resources
        and value["bindings"]["tokenizer_evidence_record"] == runtime_record
        and value["execution_scope"]["user_instruction_sha256"] == registered["instruction_evidence_artifact"], "prepared_resource_evidence_changed")
    # This rebuilt manifest is a transient structural check with an explicitly
    # synthetic upstream key. It is not persisted as an execution manifest.
    check = prepared.build_execution_manifest(digest([METHOD, "assessment-only", prepared.digest]))
    for task in check["tasks"]:
        if task["packet"] is not None:
            provider.contract.validate_for_dispatch(task["packet"], count_tokens=runtime["token_counter"].count)
    for reference, raw in prepared.artifacts.items():
        require(engine.ledger.artifacts.put_bytes(raw) == reference, "retained_packet_bytes_changed")
    packet_ref = engine.ledger.artifacts.put(value)
    require(packet_ref == prepared.digest, "retained_preparation_changed")
    now, quota = datetime.now(timezone.utc), engine.ledger.get(quota_record, QUOTA)
    blockers = ["audited_packet_source_history_seed_authority_pending"]
    if not check["planned_new_invocations"]:
        blockers.append("zero_fresh_slots_preserved")
    if now < execution.timestamp(resources["not_before"]) or now >= execution.timestamp(resources["admit_before"]):
        blockers.append("outside_registered_admission_window")
    if now >= execution.timestamp(resources["quota"]["valid_until"]):
        blockers.append("quota_observation_stale")
    if quota["percentage_observation"]["known_exhausted"]:
        blockers.append("observed_account_limit_exhausted")
    if resources["unavailable_quota_policy"] == "block":
        blockers.append("quota_unit_capacity_unavailable_policy_blocks")
    result = {"method": METHOD, "study_record": study_record, "implementation": implementation(),
        "prepared_initial_artifact": packet_ref, "runtime_record": runtime_record, "quota_record": quota_record, "policy_record": policy_record,
        "slot_catalog_sha256": check["slot_catalog_sha256"], "fixed_primary_units": len(check["prefix"]["primary_ranks"]),
        "fixed_slots": len(check["tasks"]), "reserved_schedule_invocations": check["prefix"]["reserved_invocations"],
        "fresh_potential_invocations": check["planned_new_invocations"], "planned_token_reservations": check["planned_token_reservations"],
        "unavailable_slots": sum(t["disposition"] == "unavailable" for t in check["tasks"]),
        "reused_slots": sum(t["disposition"] == "reused" for t in check["tasks"]), "resources": resources,
        "blockers": blockers, "dispatch_authorized": False, "upstream_packet_authority_verified": False,
        "model_calls": 0, "account_dollar_cost": None, "generation_token_cap_enforced": False,
        "configured_identity_not_observed_serving_identity": True,
        "limitations": "Actual local binary/version/tokenizer evidence and exact full-packet resources only. Imported account receipt origin is asserted; percentage quota is not invocation/token capacity. No source/history completeness, execution admission, API fallback, new seed or model call."}
    identifier = engine.ledger.record(session, ASSESSMENT, digest(result), result)
    return {"assessment_record": identifier, **{k: result[k] for k in ("fixed_primary_units", "fixed_slots", "fresh_potential_invocations",
        "planned_token_reservations", "unavailable_slots", "reused_slots", "blockers", "dispatch_authorized", "model_calls")}}
