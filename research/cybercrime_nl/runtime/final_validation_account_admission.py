"""Verified initial account-execution candidate receipts; never a dispatcher.

This separately registered offline parent replays the concrete PacketParent
slot producer, including its original global history gap. It does not accept a
caller manifest, source/history assertions, replacement quota receipt or runtime
permission. It verifies retained local runtime evidence, rehashes the local
native binary, and recomputes fixed packets and resources without invoking it.

The user instruction is already bound by Study. Missing execution registration
is an implementation prerequisite, not a claim that human permission is absent.
Actual account dispatch remains a later reviewed operation using Research's
shared gateway and durable Execution intents. No API fallback is available.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import final_validation_packet_parent as parent
from newsresearch.common import AuditError, Context, canonical, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-initial-account-candidate-receipt-v1"
INTENT = "cyber_final_validation_account_candidate_intent"
RESULT = "cyber_final_validation_account_candidate_receipt"
POLICY = {"offline_only": True, "dispatch_authorized": False, "new_model_calls": 0,
    "source_owner_reads": 0, "source_mutations": 0, "new_seed_draws": 0,
    "new_cli_invocations": 0, "new_account_probes": 0,
    "retained_protected_artifacts_reverified": True, "account_dollar_cost": None,
    "paid_api_fallback": False, "quota_reset_or_purchase": False,
    "sample_or_frame_reselected": False, "execution_manifest_registered_here": False}
AUTHORITY_PLACEHOLDER = "audited_packet_source_history_seed_authority_pending"
KNOWN_ASSESSMENT_BLOCKERS = {AUTHORITY_PLACEHOLDER, "zero_fresh_slots_preserved",
    "outside_registered_admission_window", "quota_observation_stale",
    "observed_account_limit_exhausted", "quota_unit_capacity_unavailable_policy_blocks"}


def require(value, reason):
    if not value:
        raise AuditError("account_admission_" + reason)


def same(left, right):
    return canonical(left) == canonical(right)


def implementation():
    path = Path(__file__)
    return {**parent.implementation(), **parent.execution.implementation(),
        path.relative_to(parent.study.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def resource_conditions(manifest, quota, *, now):
    """Current resource facts only; never authority to dispatch or buy credits."""
    parent.execution.validate_manifest(manifest)
    require(isinstance(now, datetime) and now.tzinfo is not None, "aware_clock_required")
    resources, blockers = manifest["resources"], []
    timestamp = parent.execution.timestamp
    if now < timestamp(resources["not_before"]) or now >= timestamp(resources["admit_before"]):
        blockers.append("outside_registered_admission_window")
    if now < timestamp(resources["quota"]["observed_at"]) or now >= timestamp(resources["quota"]["valid_until"]):
        blockers.append("quota_observation_stale")
    if quota["percentage_observation"]["known_exhausted"]:
        blockers.append("observed_account_limit_exhausted")
    if resources["quota"]["state"] == "unavailable":
        if resources["unavailable_quota_policy"] == "block":
            blockers.append("quota_unit_capacity_unavailable_policy_blocks")
    elif resources["quota"]["remaining_invocations"] < manifest["planned_new_invocations"] or resources["quota"]["remaining_tokens"] < manifest["planned_token_reservations"]:
        blockers.append("known_quota_insufficient_for_frozen_tranche")
    if not manifest["planned_new_invocations"]:
        blockers.append("zero_fresh_slots_preserved")
    return {"observed_at": now.isoformat(), "blockers": blockers,
        "unit_capacity_state": resources["quota"]["state"],
        "remaining_invocations": resources["quota"]["remaining_invocations"],
        "remaining_tokens": resources["quota"]["remaining_tokens"],
        "percentage_observation": quota["percentage_observation"],
        "unknown_quota_policy": resources["unavailable_quota_policy"],
        "quota_policy_evidence_sha256": resources["quota_policy_evidence_sha256"],
        "percentage_is_not_token_or_invocation_capacity": True,
        "account_dollar_cost": None, "generation_token_cap_enforced": False,
        "timeout_guarantees_remote_cancellation": False,
        "coordinator_invocations_not_remote_requests": True}


def retained_execution_state(engine, session, manifest):
    """Durable attempt evidence, including pre-projection crash gaps.

    Counts are evidence presence, not accepted settlement/accounting. Any such
    state needs the real Execution reconciliation before a future dispatch.
    A later completion event does not itself prove a valid or paid response.
    """
    require_active(engine, session)
    execution = parent.execution
    kinds = (execution.MANIFEST_KIND, execution.INTENT_KIND, execution.RESULT_KIND,
        execution.HALT_KIND, execution.SLOT_KIND)
    custom = {kind: engine._rows(kind) for kind in kinds}
    events = [{"seq": row[0], "kind": row[1], "event_hash": row[2], "payload": json.loads(row[3])}
        for row in engine.ledger.db.execute("SELECT seq,kind,event_hash,payload FROM events WHERE kind IN "
            "('model.attempt.intended','model.attempt.completed','model.attempt.resolved') ORDER BY seq")]
    intended = [e for e in events if e["kind"] == "model.attempt.intended"]
    completed = [e for e in events if e["kind"] == "model.attempt.completed"]
    resolved = [e for e in events if e["kind"] == "model.attempt.resolved"]
    completion_seq = {}
    for event in completed:
        completion_seq.setdefault(event["payload"].get("attempt"), []).append(event["seq"])
    custom_attempts = {r["payload"].get("attempt") for r in custom[execution.INTENT_KIND]}
    intended_attempts = {e["payload"].get("attempt") for e in intended}
    tasks = {t["logical_task_id"]: t for t in manifest["tasks"]}
    scoped, matched = 0, 0
    for event in intended:
        value = event["payload"]
        if value.get("validation_scope") != manifest["scope_sha256"]:
            continue
        scoped += 1
        task = tasks.get(value.get("logical_task_id"))
        if task is not None and task["disposition"] == "fresh" and same({k: value.get(k) for k in (
                "task_key", "task_sha256", "pair_rank", "role", "number", "reservation_tokens")},
                {"task_key": task["logical_task_id"], "task_sha256": digest(task), "pair_rank": task["pair_rank"],
                    "role": task["role"], "number": 1, "reservation_tokens": task["reservation_tokens"]}):
            matched += 1
    uncompleted = [e for e in intended if not any(seq > e["seq"]
        for seq in completion_seq.get(e["payload"].get("attempt"), []))]
    durable_ids = {e["payload"].get("attempt") for e in uncompleted}
    cached_ids = set(engine.ledger.unresolved)
    counts = {kind: len(values) for kind, values in custom.items()}
    return {"custom_records": counts, "generic_intended_events": len(intended),
        "generic_completed_events": len(completed), "generic_resolved_events": len(resolved),
        "candidate_scope_intended_events": scoped, "other_or_missing_scope_intended_events": len(intended) - scoped,
        "candidate_logical_identity_matches": matched, "candidate_logical_identity_unverified": scoped - matched,
        "generic_intents_without_custom_projection": sum(e["payload"].get("attempt") not in custom_attempts for e in intended),
        "custom_intents_without_generic_event": sum(r["payload"].get("attempt") not in intended_attempts
            for r in custom[execution.INTENT_KIND]),
        "intent_events_without_later_completion_event": len(uncompleted),
        "cached_unresolved_attempts": len(cached_ids), "cache_only_unresolved_attempts": len(cached_ids - intended_attempts),
        "durable_uncompleted_attempts_absent_from_cache": len(durable_ids - cached_ids),
        "generic_event_census_sha256": digest(events), "unresolved_cache_sha256": digest(engine.ledger.unresolved),
        "event_census_last_sequence": events[-1]["seq"] if events else None,
        "requires_coordinator_reconciliation": bool(events or cached_ids or any(counts.values())),
        "settlement_or_usage_inferred": False, "uncompleted_does_not_mean_unreturned": True}


class AccountAdmissionParent(parent.PacketParent):
    """Assess/status only. No provider instance or execution-policy creation."""
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "slot_record"}
            and data["action"] in {"assess", "status"}, "offline_operation")
        parent.execution.sha(data["slot_record"])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _slot_chain(self, identifier):
        row = self._one(parent.SLOTS)
        require(row["id"] == identifier, "unique_completed_slots_required")
        value = row["payload"]
        require(value["method"] == parent.METHOD and same(value["implementation"], parent.implementation())
            and all(same(value.get(k), v) for k, v in parent.POLICY.items()), "slot_method_binding")
        selected = value["binding"]
        require(set(selected) == {"final_frame_record", "runtime_record", "quota_record", "resource_policy_record"}, "slot_binding_fields")
        parent.slot_binding(**selected)
        frame_row, chain, frame, schedule = self._load_frame(selected["final_frame_record"])
        intended = self._one(parent.SLOT_INTENT)
        require(intended["id"] == value["slot_intent"] and same(intended["payload"], {
            "method": parent.METHOD, "binding": selected, "implementation": parent.implementation(),
            "frame_digest": frame.digest, "schedule_digest": schedule.digest, "policy": parent.POLICY}), "slot_intent_binding")
        for reference in value["retained_artifacts"]:
            self.ledger.artifacts.read_bytes(reference)
        return value, frame_row, chain, frame, schedule

    def _resource_evidence(self, session, context, slot, study_id):
        module = parent.admission
        selected = slot["binding"]
        protocol = self._version_once(session, context, "protocol", module.METHOD, module.protocol_content(study_id))
        ctx = Context(context.objective, context.actor, {"protocol": protocol})
        registered = module._registered(self, session, ctx, study_id)
        runtime = module._runtime_result(self, selected["runtime_record"])
        runtime_row = self.ledger.get(selected["runtime_record"], module.RUNTIME)
        require(runtime_row["study_record"] == study_id and runtime_row["configured_model"] == parent.admission.provider.contract.MODEL
            and runtime_row["reasoning_effort"] == parent.admission.provider.contract.REASONING_EFFORT
            and runtime_row["account_dollar_cost"] is None and runtime_row["model_calls"] == 0
            and runtime_row["account_authentication_observed"] is False and runtime_row["model_identity_observed"] is False,
            "runtime_route_binding")
        cli = runtime["cli_profile"]["cli_binding"]
        module._native_bytes(Path(cli["executable"]), cli["binary_sha256"])
        resources = module.resources_from_evidence(self, session, ctx, study_record=study_id,
            quota_record=selected["quota_record"], policy_record=selected["resource_policy_record"])
        quota = self.ledger.get(selected["quota_record"], module.QUOTA)
        receipt = self.ledger.artifacts.read(quota["receipt_artifact"])
        require(set(receipt) == {"source", "source_reference", "captured_at", "selected_limit_id", "raw_result"}
            and receipt["source"] == "codex_app_get_usage_limits" and isinstance(receipt["source_reference"], str)
            and receipt["source_reference"].strip(), "quota_receipt_provenance")
        expected_quota = {"method": module.METHOD, "study_record": study_id,
            "receipt_artifact": quota["receipt_artifact"], "captured_at": receipt["captured_at"],
            "percentage_observation": module.quota_percentages(receipt["raw_result"], receipt["selected_limit_id"]),
            "unit_capacity_state": "unavailable", "remaining_invocations": None, "remaining_tokens": None,
            "origin_independently_authenticated": False, "account_dollar_cost": None, "new_account_probe_by_helper": False}
        require(same(quota, expected_quota), "quota_evidence_binding")
        policy = self.ledger.get(selected["resource_policy_record"], module.POLICY)
        require(set(policy) == {"method", "study_record", "policy", "instruction_evidence_artifact", "protocol",
            "account_only", "paid_api_fallback", "quota_purchase_or_reset", "initial_primary_limit", "initial_task_limit", "dispatch_authorized"}
            and policy["method"] == module.METHOD and policy["study_record"] == study_id
            and policy["instruction_evidence_artifact"] == registered["instruction_evidence_artifact"]
            and policy["account_only"] is True and policy["paid_api_fallback"] is False
            and policy["quota_purchase_or_reset"] is False and policy["dispatch_authorized"] is False
            and type(policy["initial_primary_limit"]) is int and policy["initial_primary_limit"] == 40
            and type(policy["initial_task_limit"]) is int and policy["initial_task_limit"] == 60
            and same(self.ledger.get(policy["protocol"], "protocol")["content"], module.protocol_content(study_id)), "resource_policy_binding")
        require(set(policy["policy"]) == {"maximum_invocations", "maximum_token_reservations", "output_token_allowance",
            "not_before", "admit_before", "quota_valid_for_seconds", "unavailable_quota_policy", "decision_note"}
            and isinstance(policy["policy"]["decision_note"], str) and policy["policy"]["decision_note"].strip(), "resource_policy_fields")
        parent.execution.integer(policy["policy"]["quota_valid_for_seconds"], 1)
        return registered, runtime, resources, quota

    def _replay_slots(self, session, context, chain_tuple):
        slot, saved, chain, frame, schedule = chain_tuple
        selected, read = slot["binding"], self.ledger.artifacts.read
        study_id = saved["binding"]["preparation_binding"]["study_record"]
        registered, runtime, resources, quota = self._resource_evidence(session, context, slot, study_id)
        records_ref, history_ref = (chain[3]["artifacts"][k] for k in ("pair_history_records", "pair_history_inventory"))
        certificate = read(history_ref)
        require(certificate["global_gap"] is True and certificate["complete"] is False,
            "original_history_gap_cannot_be_replaced")
        prepared = parent.packets.prepare_initial_packets(frame, schedule, self._documents(chain[0], chain[1]),
            historical_records=read(records_ref), history_inventory=certificate,
            order_seed=read(saved["article_order_seed_artifact"])["seed"],
            bindings={"source_snapshot_record": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
                "source_snapshot_artifact": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_artifact"],
                "frame_verification_record": selected["final_frame_record"], "history_verification_record": saved["binding"]["reconciliation_record"],
                "history_records_sha256": records_ref, "history_inventory_sha256": history_ref,
                "order_seed_record": saved["binding"]["preparation_binding"]["seed_record"],
                "order_seed_artifact": saved["article_order_seed_artifact"], "tokenizer_evidence_record": selected["runtime_record"]},
            token_counter=runtime["token_counter"], cli_profile=runtime["cli_profile"], resources=resources,
            user_instruction_sha256=registered["instruction_evidence_artifact"])
        require(prepared.digest == slot["prepared_initial_artifact"] and same(read(prepared.digest), prepared.payload)
            and all(self.ledger.artifacts.read_bytes(ref) == raw for ref, raw in prepared.artifacts.items()), "prepared_slot_replay")
        authority = self.ledger.get(slot["slot_admission_record"], parent.execution.ADMISSION_KIND)
        protocol = authority["verification_protocol"]
        require(same(self.ledger.get(protocol, "protocol")["content"], {"method": parent.METHOD,
            "implementation": parent.implementation(), "slot_intent": slot["slot_intent"],
            "prepared_initial_sha256": prepared.digest,
            "upstream_authority": "actual-bound-study-final-frame-history-tokenizer-and-fixed-slot-verification"}), "slot_protocol_binding")
        require(same(authority, {"method": parent.execution.METHOD, "scope_sha256": digest(prepared.payload["execution_scope"]),
            "prefix_sha256": prepared.payload["initial_prefix"]["initial_manifest_sha256"],
            "slot_catalog_sha256": prepared.payload["slot_catalog_sha256"],
            "source_snapshot": saved["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
            "history_inventory": saved["binding"]["reconciliation_record"], "verification_protocol": protocol,
            "final_frame_record": selected["final_frame_record"], "slot_intent": slot["slot_intent"],
            "prepared_initial_artifact": prepared.digest, "source_history_seed_and_authority_verified": True,
            "dispatch_authorized": False, "history_scope_complete": False}), "slot_authority_binding")
        manifest = prepared.build_execution_manifest(slot["slot_admission_record"])
        require(digest(manifest) == slot["candidate_execution_manifest_artifact"]
            and same(read(slot["candidate_execution_manifest_artifact"]), manifest), "candidate_manifest_replay")
        parent.execution.validate_manifest(manifest)
        assessment = self.ledger.get(slot["resource_assessment_record"], parent.admission.ASSESSMENT)
        expected = {"method": parent.admission.METHOD, "study_record": study_id, "implementation": parent.admission.implementation(),
            "prepared_initial_artifact": prepared.digest, "runtime_record": selected["runtime_record"],
            "quota_record": selected["quota_record"], "policy_record": selected["resource_policy_record"],
            "slot_catalog_sha256": manifest["slot_catalog_sha256"], "fixed_primary_units": len(manifest["prefix"]["primary_ranks"]),
            "fixed_slots": len(manifest["tasks"]), "reserved_schedule_invocations": manifest["prefix"]["reserved_invocations"],
            "fresh_potential_invocations": manifest["planned_new_invocations"],
            "planned_token_reservations": manifest["planned_token_reservations"],
            "unavailable_slots": sum(t["disposition"] == "unavailable" for t in manifest["tasks"]),
            "reused_slots": sum(t["disposition"] == "reused" for t in manifest["tasks"]), "resources": resources,
            "dispatch_authorized": False, "upstream_packet_authority_verified": False, "model_calls": 0,
            "account_dollar_cost": None, "generation_token_cap_enforced": False,
            "configured_identity_not_observed_serving_identity": True}
        require(all(same(assessment.get(k), value) for k, value in expected.items())
            and isinstance(assessment["blockers"], list) and len(assessment["blockers"]) == len(set(assessment["blockers"]))
            and set(assessment["blockers"]) <= KNOWN_ASSESSMENT_BLOCKERS and AUTHORITY_PLACEHOLDER in assessment["blockers"],
            "resource_assessment_binding")
        remaining = [v for v in assessment["blockers"] if v != AUTHORITY_PLACEHOLDER]
        require(same(slot["remaining_blockers"], remaining) and same(slot["resource_census"], prepared.payload["resource_census"])
            and slot["history_inventory_artifact"] == history_ref and slot["upstream_packet_authority_verified"] is True
            and slot["dispatch_authorized"] is False and slot["empirical_validation_completed"] is False, "retained_slot_summary_binding")
        return manifest, quota, remaining, prepared, registered

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data["method"] == METHOD, "offline_required")
        chain = self._slot_chain(data["slot_record"])
        slot = chain[0]
        desired = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "slot_record": data["slot_record"], "slot_artifact": digest(slot),
            "frame_record": slot["binding"]["final_frame_record"], "resource_records": slot["binding"],
            "candidate_manifest_artifact": slot["candidate_execution_manifest_artifact"]}
        old = self._one(INTENT, optional=True)
        require(old is None or same(old["payload"], desired), "changed_binding_requires_amendment")
        if data["action"] == "status":
            return {"method": METHOD, **POLICY, "assessments": len(self._rows(RESULT)),
                "exact_binding_registered": old is not None, "current_resource_conditions_recomputed": False}
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        protocol_content = {"method": METHOD, "intent_record": intent, "binding": desired}
        protocol = self._version_once(session, context, "protocol", METHOD, protocol_content)
        manifest, quota, historical_blockers, prepared, registered = self._replay_slots(session, context, chain)
        current = resource_conditions(manifest, quota, now=datetime.now(timezone.utc))
        blockers = list(dict.fromkeys([*historical_blockers, *current["blockers"],
            "retained_reference_history_scope_incomplete", "account_execution_operation_not_registered"]))
        existing_state = retained_execution_state(self, session, manifest)
        existing_execution = existing_state["custom_records"]
        if existing_state["requires_coordinator_reconciliation"]:
            blockers.append("existing_execution_state_requires_coordinator_reconciliation")
        if (self.ledger.root / "STOP").exists():
            blockers.append("user_stop")
        receipt = {"method": METHOD, **POLICY, "intent_record": intent, "protocol_record": protocol,
            "binding": desired, "observed_at": current["observed_at"],
            "verified_candidate_manifest_artifact": slot["candidate_execution_manifest_artifact"],
            "execution_manifest_sha256": manifest["manifest_sha256"], "execution_scope_sha256": manifest["scope_sha256"],
            "upstream_slot_admission_record": slot["slot_admission_record"],
            "slot_catalog_sha256": manifest["slot_catalog_sha256"], "resource_census": prepared.payload["resource_census"],
            "upstream_packet_authority_verified_by_exact_replay": True,
            "obsolete_placeholder_discharged": AUTHORITY_PLACEHOLDER,
            "historical_specific_blockers_preserved": historical_blockers,
            "current_resource_conditions": current, "blockers": blockers,
            "existing_execution_records": existing_execution,
            "existing_execution_state": existing_state,
            "human_instruction_evidence_artifact": registered["instruction_evidence_artifact"],
            "configured_route": {"model": parent.admission.provider.contract.MODEL,
                "reasoning_effort": parent.admission.provider.contract.REASONING_EFFORT,
                "fast": False, "route": "codex_cli_account_only", "observed_serving_model": None,
                "account_authentication_observed": False},
            "coordinator_binding": {"method": parent.execution.METHOD, "initial_primary_limit": 40,
                "initial_task_limit": 60, "manifest_sha256": manifest["manifest_sha256"],
                "slot_identity": "unchanged_frame_full_input_pair_and_role", "no_retry": True},
            "remaining_implementation_prerequisites": [
                "versioned_v11_snapshot_preparation_reconciliation_and_packet_consumer_chain",
                "evidence_based_task_history_closure_integrated_without_redraw",
                "separate_registered_account_execution_operation_with_fresh_resource_checks_and_gateway_intents"],
            "limitations": "Current original PacketParent history remains globally incomplete and fixed slots unavailable. The user's instruction is bound; missing execution activation is not a new permission request. Local binary/tokenizer evidence and imported quota receipt do not prove account login or serving-model identity. No percentages are converted to tokens or money, and no output reservation is claimed as an enforced remote token cap."}
        require(implementation() == desired["implementation"], "implementation_changed")
        record = self.ledger.record(session, RESULT, digest([intent, current["observed_at"]]), receipt)
        return {"receipt_record": record, "receipt_artifact": digest(receipt), "method": METHOD, **POLICY,
            "verified_candidate_manifest_artifact": receipt["verified_candidate_manifest_artifact"],
            "execution_manifest_sha256": receipt["execution_manifest_sha256"],
            "resource_census": receipt["resource_census"], "blockers": blockers,
            "account_dollar_cost": None, "current_resource_conditions_recomputed": True,
            "current_source_quiescence_verified": False}
