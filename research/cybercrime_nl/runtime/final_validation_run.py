"""Concrete initial account-validation authority and orchestration.

This separately registered extension never changes the initialized Study, its
seeds, source snapshot or fixed schedule. Preparation replays completed source,
frame and task-history producers; a history gap can leave every slot unavailable.
Only run-initial/resume can invoke the audited account-only PairProvider. The
initial manifest's time/resource window is immutable: a later quota receipt is
additional stopping evidence, not permission to renew that window.

All actual source inspection, native version observation and account dispatch
remain inside Research.execute. The CLI's offline stage driver supplies exact
protected declarations to existing audited parents; it does not discover roots
or manufacture source heads. Source text is never part of the console summary.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path

import final_validation_account_admission as account
import final_validation_admission as admission
import final_validation_execution as execution
import final_validation_execution_v2 as series
import final_validation_history_closure as closure
import final_validation_history_roots as roots
import final_validation_lifecycle_evidence as lifecycle
import final_validation_packet_parent as packets
import final_validation_provider as provider
import final_validation_source_lineage as lineage
import final_validation_study as study
from newsresearch.common import AuditError, Context, canonical, digest, require_active, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-initial-account-run-parent-v1"
INTENT = "cyber_final_validation_run_intent"
AUTHORITY = "cyber_final_validation_run_history_authority"
PREPARED = "cyber_final_validation_run_prepared"
OBSERVATION = "cyber_final_validation_run_account_observation"
REPORT = "cyber_final_validation_run_report"
STAGE_PLAN = "cyber_final_validation_offline_stage_plan"
POLICY = {"account_only": True, "paid_api_fallback": False, "new_seed_draws": 0,
    "fixed_initial_primary_limit": 40, "fixed_initial_task_limit": 60,
    "unavailable_slots_replaced": False, "old_attempts_retried": False,
    "quota_receipts_renew_initial_window": False, "unknown_prior_exposure_is_not_attempt_history": True,
    "later_tranche_dispatch_implemented": False, "universal_history_completeness_claimed": False}


def require(value, reason):
    if not value:
        raise AuditError("final_run_" + reason)


def same(left, right):
    return digest(left) == digest(right)


def implementation():
    # Imported lazily only to permit separate new-file ownership during development.
    import final_validation_fixed_slots as fixed
    code = {}
    for module in (closure, roots, lifecycle, account, series, fixed):
        code.update(module.implementation())
    path = Path(__file__)
    code[path.relative_to(study.ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return code


def binding(*, final_frame_record, closure_record):
    for value in (final_frame_record, closure_record):
        execution.sha(value)
    return {"final_frame_record": final_frame_record, "closure_record": closure_record}


class FinalValidationRun(closure.HistoryClosureParent):
    """The original offline Research provider stays unused; Codex uses its gateway.

    The base's offline flag selects the generic mock provider and is not a Codex
    permission. The explicit registered account operation below is the only
    reachable dispatch path. No caller can inject a provider or subprocess runner.
    """

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions, "registered_entry_only")
        fields = {
            "prepare": {"action", "binding", "runtime", "quota_receipt", "resource_policy", "series_limits"},
            "run-initial": {"action", "prepared_record", "quota_receipt"},
            "resume": {"action", "prepared_record", "quota_receipt"},
            "status": {"action"},
            "retain-config": {"action", "config_path"},
        }
        require(data.get("action") in fields and set(data) == fields[data["action"]], "entry_shape")
        if data["action"] == "prepare":
            require(set(data["binding"]) == {"final_frame_record", "closure_record"}, "binding_fields")
            binding(**data["binding"])
            require(isinstance(data["runtime"], dict) and set(data["runtime"]) == {"executable", "sha256"}, "runtime_fields")
            execution.sha(data["runtime"]["sha256"])
            series.limits(data["series_limits"])
        elif data["action"] not in {"status", "retain-config"}:
            execution.sha(data["prepared_record"])
        require_no_credentials(data)
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _frame_and_closure(self, session, context, selected):
        """Replay actual completed producers; never accept caller proof fields."""
        require_active(self, session)
        frame_value, chain, frame, schedule = self._load_frame(selected["final_frame_record"])
        snapshot = chain[0]
        require(snapshot["method"] == lineage.v11_snapshot.METHOD, "v11_snapshot_required")
        registered = self._registration()
        require(registered["id"] == frame_value["binding"]["preparation_binding"]["study_record"], "original_study")
        saved = self.ledger.get(selected["closure_record"], closure.RESULT)
        require(self._one(closure.RESULT)["id"] == selected["closure_record"], "unique_completed_closure")
        inputs = saved["binding"]["binding"]
        # This is the closure producer's OWN audited completed replay, not its
        # inherited BatchHistory.load_completed method.
        result = closure.HistoryClosureParent._status(self, session, context,
            {"method": closure.METHOD, "action": "status", **inputs})
        require(result.get("closure_record") == selected["closure_record"], "completed_closure_replay")
        batch = self.ledger.get(inputs["batch_history_record"], closure.batch.RESULT)
        require(same(batch["binding"]["task_census_binding"], frame_value["binding"]), "closure_frame_ancestry")
        resolved = roots.resolve_completed_roots(self, session, context, selected["closure_record"])
        projection = self.ledger.artifacts.read(resolved["projection_artifact"])
        require(digest(projection) == resolved["projection_artifact"]
            and projection["input_index_digest"] == frame.index.digest, "closure_index_projection")
        for field in ("schedule_seed_artifact", "article_order_seed_artifact"):
            require(saved["binding"][field] == frame_value[field], "closure_original_seed")
        main_owner = digest(str(self.source_owner))
        require(projection["scoped_certificate"]["source_heads"].get(main_owner) == snapshot["source_bindings"]["source_head"],
            "closure_main_cutoff")
        require(saved["binding"]["inherited_no_retry_inventory"] == chain[3]["artifacts"]["pair_history_inventory"],
            "closure_inherited_certificate")
        # Keep the original closure payload and its exact digest separate from
        # this in-memory bundle of explicitly versioned derived proof references.
        bound = {**saved, "original_closure_sha256": digest(saved),
            "effective_projection_artifact": resolved["projection_artifact"],
            "history_verification_record": resolved["resolution_record"],
            "root_resolution_evidence_artifact": resolved["resolution_evidence_artifact"]}
        supplement = self._one(lifecycle.RESULT, optional=True)
        if supplement:
            lifecycle.LifecycleParent._verify(self, supplement["payload"], batch["binding"]["task_census_record"])
        bound["lifecycle_evidence_record"] = supplement["id"] if supplement else None
        return frame_value, chain, frame, schedule, bound, projection, registered

    def _preflight_context(self, session, context, study_record):
        protocol = self._version_once(session, context, "protocol", admission.METHOD,
            admission.protocol_content(study_record))
        return Context(context.objective, context.actor, {"protocol": protocol})

    def _quota(self, session, context, registered, receipt):
        selected = self._preflight_context(session, context, registered["id"])
        reference = admission.retain_quota_receipt(self, session, selected,
            study_record=registered["id"], receipt=receipt)
        return reference, self.ledger.get(reference, admission.QUOTA)

    def _initial_versions(self, session, context, manifest):
        values = {
            "protocol": {"method": execution.METHOD, "execution_manifest_sha256": manifest["manifest_sha256"],
                "scope_sha256": manifest["scope_sha256"], "implementation_sha256": digest(manifest["implementation"])},
            "policy": {"method": execution.METHOD, "execution_manifest_sha256": manifest["manifest_sha256"],
                "allow_codex_account_execution": True, "user_instruction_sha256": manifest["scope"]["user_instruction_sha256"],
                "account_only": True, "paid_api_fallback": False, "immutable_initial_window": True},
            "selection": {"rules": "Unchanged original initial prefix, QC and diagnostic identities; unavailable slots retained.",
                "upstream_admission": manifest["upstream_binding"], "slot_catalog_sha256": manifest["slot_catalog_sha256"]},
            "prompt": {"instructions": provider.contract.INSTRUCTIONS},
            "dossier_definition": {"unit": provider.contract.DEFINITION_VERSION},
        }
        return {kind: self._version_once(session, context, kind, METHOD + ":initial:" + kind, value)
            for kind, value in values.items()}

    def _register_series(self, session, context, manifest_record, manifest, frame, schedule, ceilings):
        content = series.registration_content(manifest_record, manifest, schedule, ceilings)
        versions = {kind: self._version_once(session, context, kind, METHOD + ":series:" + kind, content)
            for kind in ("protocol", "policy")}
        return series.register_series(self, session, initial_manifest_record=manifest_record,
            frame=frame, schedule=schedule, ceilings=ceilings, versions=versions)

    def _retain_local_resolutions(self, session, manifest_record, manifest):
        """Retain fixed nonfresh outcomes without constructing any provider."""
        existing = execution.rows(self, session, execution.SLOT_KIND)
        require(len({row["logical_task_id"] for row in existing}) == len(existing), "duplicate_local_resolution")
        by_id = {row["logical_task_id"]: row for row in existing}
        expected_ids = {task["logical_task_id"] for task in manifest["tasks"] if task["disposition"] != "fresh"}
        require(set(by_id) <= expected_ids, "foreign_or_fresh_local_resolution")
        for task in manifest["tasks"]:
            if task["disposition"] == "fresh":
                continue
            expected = execution.slot_resolution(manifest_record, task)
            saved = by_id.get(task["logical_task_id"])
            if saved is None:
                self.ledger.record(session, execution.SLOT_KIND, task["logical_task_id"], expected)
            else:
                require(same({k: v for k, v in saved.items() if k != "_record_id"}, expected), "local_resolution_changed")
        retained = execution.rows(self, session, execution.SLOT_KIND)
        require(len(retained) == len(expected_ids) and {row["logical_task_id"] for row in retained} == expected_ids,
            "foreign_or_fresh_local_resolution")

    def _native_provider(self, session, runtime):
        cli = runtime["cli_profile"]["cli_binding"]
        admission._native_bytes(Path(cli["executable"]), cli["binary_sha256"])
        # Tests patch the provider's native subprocess boundary, never a public
        # runtime argument or caller-supplied Provider implementation.
        return provider.PairProvider(self.ledger.root / "final-validation-account-workers", research=self, session=session,
            executable=cli["executable"], executable_sha256=cli["binary_sha256"],
            cli_version_observation=cli["version_observation"],
            tokenizer_identity=runtime["cli_profile"]["tokenizer_identity"], count_tokens=runtime["token_counter"].count)

    def _scope_authority(self, session, context, selected, intent, verified):
        frame_value, chain, frame, schedule, saved, projection, registered = verified
        snapshot, _, prepared, reconciled, registry, _ = chain
        # Scoped closure can supersede the old main-only discovery placeholder
        # only for this exact reconciled registry/cutoff, never a supplied subset.
        expected_heads = {digest(str(self.source_owner)): snapshot["source_bindings"]["source_head"],
            **{digest(row["source_owner"]): row["source_head"] for row in registry["owners"]}}
        actual_heads = projection["scoped_certificate"]["source_heads"]
        require(all(actual_heads.get(key) == head for key, head in expected_heads.items()), "closure_registry_coverage")
        value = {"method": METHOD, "intent_record": intent, "binding": selected,
            "source_snapshot": frame_value["binding"]["preparation_binding"]["snapshot_binding"],
            "study_record": registered["id"], "seed_record": prepared["binding"]["seed_record"],
            "closure_record": selected["closure_record"], "closure_artifact": saved["original_closure_sha256"],
            "closure_projection": saved["projection_artifact"], "closure_protocol": saved["protocol_record"],
            "effective_projection_artifact": saved["effective_projection_artifact"],
            "history_verification_record": saved["history_verification_record"],
            "root_resolution_evidence_artifact": saved["root_resolution_evidence_artifact"],
            "lifecycle_evidence_record": saved["lifecycle_evidence_record"],
            "lifecycle_bytes_discharge_no_gaps": True,
            "catalog_artifact": saved["binding"]["catalog_artifact"],
            "root_dispositions_sha256": digest(projection["root_dispositions"]),
            "full_owner_partitions_sha256": digest(projection["owner_partitions"]),
            "covered_source_heads": actual_heads, "expected_legacy_source_heads": expected_heads,
            "registry_artifact": reconciled["registry_artifact"],
            "declared_registry_gaps_sha256": digest(registry["declared_gaps"]),
            "legacy_records": reconciled["artifacts"]["pair_history_records"],
            "legacy_inventory": reconciled["artifacts"]["pair_history_inventory"],
            "input_index_digest": frame.index.digest, "frame_digest": frame.digest, "schedule_digest": schedule.digest,
            "schedule_seed_artifact": frame_value["schedule_seed_artifact"],
            "article_order_seed_artifact": frame_value["article_order_seed_artifact"],
            "same_legacy_scope_verified": True, "inherited_inventory_unchanged": True,
            "current_source_quiescence_claimed": False, "universal_history_complete": False}
        protocol = self._version_once(session, context, "protocol", METHOD + ":history", value)
        prior = self._one(AUTHORITY, optional=True)
        if prior:
            require(same(prior["payload"], {**value, "protocol_record": protocol}), "history_authority_changed")
            return prior["id"], protocol
        return self.ledger.record(session, AUTHORITY, intent, {**value, "protocol_record": protocol}), protocol

    def _produce(self, verified, selected, runtime, resources, protocol):
        import final_validation_fixed_slots as fixed
        frame_value, chain, frame, schedule, saved, projection, registered = verified
        snapshot, index, prepared, reconciled, *_ = chain
        selected_snapshot = frame_value["binding"]["preparation_binding"]["snapshot_binding"]
        bindings = {"final_frame_record": selected["final_frame_record"], "closure_record": selected["closure_record"],
            "closure_projection_sha256": saved["effective_projection_artifact"],
            "source_snapshot_record": selected_snapshot["snapshot_record"],
            "source_snapshot_artifact": selected_snapshot["snapshot_artifact"],
            "history_verification_record": saved["history_verification_record"],
            "legacy_records_sha256": reconciled["artifacts"]["pair_history_records"],
            "legacy_inventory_sha256": reconciled["artifacts"]["pair_history_inventory"],
            "order_seed_record": prepared["binding"]["seed_record"],
            "order_seed_artifact": frame_value["article_order_seed_artifact"],
            "tokenizer_evidence_record": runtime["runtime_record"], "parent_verification_protocol": protocol}
        return fixed.prepare_fixed_slots(frame, schedule, self._documents(snapshot, index), selection={"kind": "initial"},
            legacy_records=self.ledger.artifacts.read(bindings["legacy_records_sha256"]),
            legacy_inventory=self.ledger.artifacts.read(bindings["legacy_inventory_sha256"]),
            closure_evidence=fixed.BoundClosureEvidence(canonical(projection).encode(), saved["effective_projection_artifact"]),
            order_seed=self.ledger.artifacts.read(bindings["order_seed_artifact"])["seed"], bindings=bindings,
            token_counter=runtime["token_counter"], cli_profile=runtime["cli_profile"], resources=resources,
            user_instruction_sha256=registered["payload"]["instruction_evidence_artifact"])

    @staticmethod
    def _admission_payload(manifest, *, snapshot_record, closure_record, protocol, intent, authority, fixed_digest):
        return {"method": execution.METHOD, "scope_sha256": manifest["scope_sha256"],
            "prefix_sha256": manifest["prefix"]["initial_manifest_sha256"],
            "slot_catalog_sha256": manifest["slot_catalog_sha256"],
            "source_snapshot": snapshot_record, "history_inventory": closure_record, "verification_protocol": protocol,
            "run_intent": intent, "history_authority": authority, "fixed_slot_artifact": fixed_digest,
            "no_substitution": True, "unavailable_slots_preserved": True}

    def _prepare_run(self, session, context, data):
        registered = self._registration()
        code = implementation()
        desired = {"method": METHOD, "policy": POLICY, "implementation": code,
            "inputs": {key: deepcopy(data[key]) for key in ("binding", "runtime", "quota_receipt", "resource_policy", "series_limits")},
            "study_record": registered["id"], "instruction_evidence_artifact": registered["payload"]["instruction_evidence_artifact"]}
        old = self._one(INTENT, optional=True)
        require(old is None or same(old["payload"], desired), "changed_preparation_requires_amendment")
        intent = old["id"] if old else self.ledger.record(session, INTENT, METHOD, desired)
        self._version_once(session, context, "protocol", METHOD, desired)
        if self._one(PREPARED, optional=True):
            value, *_ = self._load_run(session, context, self._one(PREPARED)["id"])
            return self._summary(value, reused=True)
        require(not self.ledger.db.execute("SELECT 1 FROM events WHERE kind='model.attempt.intended' LIMIT 1").fetchone(),
            "prospective_preparation_required")
        verified = self._frame_and_closure(session, context, data["binding"])
        authority, history_protocol = self._scope_authority(session, context, data["binding"], intent, verified)
        evidence_context = self._preflight_context(session, context, registered["id"])
        runtime = admission.observe_runtime(self, session, evidence_context, study_record=registered["id"],
            executable=data["runtime"]["executable"], executable_sha256=data["runtime"]["sha256"])
        quota_record, quota = self._quota(session, context, registered, data["quota_receipt"])
        policy_record = admission.retain_resource_policy(self, session, evidence_context,
            study_record=registered["id"], policy=data["resource_policy"])
        resources = admission.resources_from_evidence(self, session, evidence_context, study_record=registered["id"],
            quota_record=quota_record, policy_record=policy_record)
        prepared = self._produce(verified, data["binding"], runtime, resources, history_protocol)
        for ref, raw in prepared.artifacts.items():
            require(self.ledger.artifacts.put_bytes(raw) == ref, "prepared_artifact_changed")
        require(self.ledger.artifacts.put(prepared.payload) == prepared.digest, "prepared_payload_changed")
        # Build once with a temporary digest for structural/census verification;
        # only the manifest bound to the real admission record is retained.
        temporary = prepared.build_execution_manifest(digest([METHOD, "structural-check", intent]))
        for task in temporary["tasks"]:
            if task["packet"] is not None:
                provider.contract.validate_for_dispatch(task["packet"], count_tokens=runtime["token_counter"].count)
        authority_value = self._admission_payload(temporary,
            snapshot_record=verified[0]["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
            closure_record=data["binding"]["closure_record"], protocol=history_protocol, intent=intent,
            authority=authority, fixed_digest=prepared.digest)
        existing = list(self.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (execution.ADMISSION_KIND, intent)))
        require(len(existing) <= 1, "unique_slot_admission")
        if existing:
            admission_record = existing[0][0]
            require(same(self.ledger.get(admission_record, execution.ADMISSION_KIND), authority_value), "slot_admission_changed")
        else:
            admission_record = self.ledger.record(session, execution.ADMISSION_KIND, intent, authority_value)
        manifest = prepared.build_execution_manifest(admission_record)
        versions = self._initial_versions(session, context, manifest)
        manifest_record = execution.retain_manifest(self, session, manifest, versions=versions)
        self._retain_local_resolutions(session, manifest_record, manifest)
        series_record = self._register_series(session, context, manifest_record, manifest, verified[2], verified[3], data["series_limits"])
        conditions = account.resource_conditions(manifest, quota, now=datetime.now(timezone.utc))
        if (self.ledger.root / "STOP").exists():
            conditions["blockers"].append("user_stop")
        value = {"method": METHOD, "implementation": code, "policy": POLICY, "intent_record": intent,
            "binding": data["binding"], "history_authority_record": authority, "history_protocol": history_protocol,
            "runtime_record": runtime["runtime_record"], "quota_record": quota_record, "resource_policy_record": policy_record,
            "fixed_slot_artifact": prepared.digest, "slot_admission_record": admission_record,
            "manifest_record": manifest_record, "manifest_sha256": manifest["manifest_sha256"], "series_record": series_record,
            "frame_digest": verified[2].digest, "schedule_digest": verified[3].digest,
            "resource_census": prepared.payload["resource_census"], "initial_conditions": conditions,
            "prepared_at": utc(), "new_model_calls": 0, "statistical_look": False}
        require(implementation() == code, "implementation_changed")
        identifier = self.ledger.record(session, PREPARED, intent, value)
        return self._summary(value, reused=False) | {"prepared_record": identifier}

    def _load_run(self, session, context, identifier):
        """Replay retained authority, not a caller manifest or a receipt hash."""
        require_active(self, session)
        row, intent = self._one(PREPARED), self._one(INTENT)
        require(row["id"] == identifier, "unique_prepared_result")
        value, desired = row["payload"], intent["payload"]
        require(value["intent_record"] == intent["id"] and value["method"] == desired["method"] == METHOD
            and same(value["implementation"], implementation()) and same(desired["implementation"], implementation())
            and same(value["policy"], POLICY) and same(desired["policy"], POLICY), "prepared_implementation")
        require(self.ledger.db.execute("SELECT logical_key FROM records WHERE id=?", (identifier,)).fetchone()[0] == intent["id"],
            "prepared_logical_key")
        require(type(intent["created_event"]) is int and type(row["created_event"]) is int
            and intent["created_event"] < row["created_event"], "prepared_chronology")
        require(same(value["binding"], desired["inputs"]["binding"]), "prepared_binding")
        verified = self._frame_and_closure(session, context, value["binding"])
        registered = verified[-1]
        require(desired["study_record"] == registered["id"]
            and desired["instruction_evidence_artifact"] == registered["payload"]["instruction_evidence_artifact"], "prepared_study")
        authority, history_protocol = self._scope_authority(session, context, value["binding"], intent["id"], verified)
        require((authority, history_protocol) == (value["history_authority_record"], value["history_protocol"]), "prepared_history")
        runtime = admission._runtime_result(self, value["runtime_record"])
        chosen_runtime = desired["inputs"]["runtime"]
        cli = runtime["cli_profile"]["cli_binding"]
        require(cli["executable"] == chosen_runtime["executable"] and cli["binary_sha256"] == chosen_runtime["sha256"],
            "prepared_runtime")
        evidence_context = self._preflight_context(session, context, registered["id"])
        quota = self.ledger.get(value["quota_record"], admission.QUOTA)
        require(same(self.ledger.artifacts.read(quota["receipt_artifact"]), desired["inputs"]["quota_receipt"]), "initial_quota_changed")
        policy = self.ledger.get(value["resource_policy_record"], admission.POLICY)
        require(same(policy["policy"], {"unavailable_quota_policy": "block", **desired["inputs"]["resource_policy"]}), "initial_policy_changed")
        require(policy["protocol"] == evidence_context.versions["protocol"]
            and policy["instruction_evidence_artifact"] == registered["payload"]["instruction_evidence_artifact"], "resource_policy_authority")
        resources = admission.resources_from_evidence(self, session, evidence_context, study_record=registered["id"],
            quota_record=value["quota_record"], policy_record=value["resource_policy_record"])
        fixed = self._produce(verified, value["binding"], runtime, resources, history_protocol)
        require(fixed.digest == value["fixed_slot_artifact"]
            and same(self.ledger.artifacts.read(fixed.digest), fixed.payload)
            and same(value["resource_census"], fixed.payload["resource_census"]), "fixed_slots_changed")
        for reference, raw in fixed.artifacts.items():
            require(self.ledger.artifacts.read_bytes(reference) == raw, "fixed_artifact_changed")
        manifest = fixed.build_execution_manifest(value["slot_admission_record"])
        expected_admission = self._admission_payload(manifest,
            snapshot_record=verified[0]["binding"]["preparation_binding"]["snapshot_binding"]["snapshot_record"],
            closure_record=value["binding"]["closure_record"], protocol=history_protocol, intent=intent["id"],
            authority=authority, fixed_digest=fixed.digest)
        require(same(self.ledger.get(value["slot_admission_record"], execution.ADMISSION_KIND), expected_admission),
            "slot_admission_changed")
        retained = self.ledger.get(value["manifest_record"], execution.MANIFEST_KIND)
        require(same(retained["manifest"], manifest) and value["manifest_sha256"] == manifest["manifest_sha256"], "manifest_changed")
        require(same(retained["versions"], self._initial_versions(session, context, manifest)), "initial_versions_changed")
        require(execution.retain_manifest(self, session, manifest, versions=retained["versions"]) == value["manifest_record"],
            "manifest_authority_changed")
        self._retain_local_resolutions(session, value["manifest_record"], manifest)
        series_value = series.load_series(self, session, value["series_record"], verified[2], verified[3])
        require(series_value["initial_manifest_record"] == value["manifest_record"]
            and same(series_value["limits"], desired["inputs"]["series_limits"]), "prospective_series_changed")
        def record_sequence(reference):
            return self.ledger.db.execute("SELECT created_event FROM records WHERE id=?",
                (reference,)).fetchone()[0]
        require(record_sequence(value["manifest_record"]) < record_sequence(value["series_record"])
            < record_sequence(identifier), "prospective_registration_order")
        first_attempt = self.ledger.db.execute("SELECT MIN(seq) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        require(first_attempt is None or record_sequence(identifier) < first_attempt, "retrospective_run_authority")
        require(value["frame_digest"] == verified[2].digest and value["schedule_digest"] == verified[3].digest, "prepared_frame")
        return value, manifest, runtime, verified, policy

    def _summary(self, value, *, reused):
        return {"method": METHOD, "prepared_record": self._one(PREPARED)["id"],
            "manifest_record": value["manifest_record"], "series_record": value["series_record"],
            "resource_census": value["resource_census"], "initial_conditions": value["initial_conditions"],
            "reused": reused, "account_dollar_cost": None, "paid_api_fallback": False,
            "initial_window_renewable": False, "statistical_look": False, "later_tranche_dispatch_implemented": False}

    def _run_status(self, session, context):
        ready = self._one(PREPARED, optional=True)
        if ready is None:
            return {"method": METHOD, "prepared": False, "dispatch_ready": False, "new_model_calls": 0}
        value, manifest, _, verified, _ = self._load_run(session, context, ready["id"])
        current = series.census(self, session, series_record=value["series_record"], frame=verified[2], schedule=verified[3])
        return self._summary(value, reused=True) | {"prepared": True, "dispatch_ready": False,
            "existing_execution_state": account.retained_execution_state(self, session, manifest),
            "series_state_counts": dict(Counter(current["states"].values())), "series_blockers": current["blockers"],
            "current_quota_observation_required_before_run": True, "new_model_calls": 0}

    def _run_initial(self, session, context, data):
        value, manifest, runtime, verified, policy = self._load_run(session, context, data["prepared_record"])
        before = account.retained_execution_state(self, session, manifest)
        require(data["action"] == "resume" or not before["generic_intended_events"], "existing_attempts_require_resume")
        require(not before["other_or_missing_scope_intended_events"], "unrelated_or_unbound_attempt")
        quota_record, quota = self._quota(session, context, verified[-1], data["quota_receipt"])
        now = datetime.now(timezone.utc)
        conditions = account.resource_conditions(manifest, quota, now=now)
        age = (now - execution.timestamp(quota["captured_at"])).total_seconds()
        if not 0 <= age < policy["policy"]["quota_valid_for_seconds"]:
            conditions["blockers"].append("fresh_quota_observation_required")
        if (self.ledger.root / "STOP").exists():
            conditions["blockers"].append("user_stop")
        # A new receipt is additional stopping evidence. The original manifest's
        # quota validity/admission window and resource ceilings remain unchanged.
        observation = {"method": METHOD, "prepared_record": data["prepared_record"], "action": data["action"],
            "manifest_record": value["manifest_record"], "series_record": value["series_record"],
            "quota_record": quota_record, "original_resource_sha256": digest(manifest["resources"]),
            "conditions": conditions, "existing_execution_state": before, "observed_at": utc()}
        observation_record = self.ledger.record(session, OBSERVATION, digest(observation), observation)
        result = None
        if not conditions["blockers"]:
            selected = self._native_provider(session, runtime)
            coordinator = execution.Execution(self, session, value["manifest_record"], selected)
            result = coordinator.run(allow_account_execution=True)
        after = account.retained_execution_state(self, session, manifest)
        report = {"method": METHOD, "prepared_record": data["prepared_record"], "observation_record": observation_record,
            "manifest_record": value["manifest_record"], "series_record": value["series_record"],
            "blockers": conditions["blockers"], "execution_report_record": result["id"] if result else None,
            "execution_stop_reason": result.get("stop_reason") if result else None,
            "new_local_attempts": after["generic_intended_events"] - before["generic_intended_events"],
            "retained_execution_state": after, "account_dollar_cost": None, "statistical_look": False,
            "initial_window_renewed": False, "observed_at": utc()}
        require(implementation() == value["implementation"], "implementation_changed")
        identifier = self.ledger.record(session, REPORT, digest(report), report)
        return {"report_record": identifier, **report}

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        if data["action"] == "retain-config":
            return self._retain_config(session, context, data["config_path"])
        if data["action"] == "prepare":
            return self._prepare_run(session, context, data)
        if data["action"] == "status":
            return self._run_status(session, context)
        return self._run_initial(session, context, data)

    def _retain_config(self, session, context, filename):
        """Exact protected metadata only; never an inline source or truth flag."""
        require_active(self, session)
        path = Path(filename)
        require(path.is_absolute() and not path.is_symlink() and path.is_file()
            and not path.resolve().is_relative_to(study.ROOT.resolve()), "protected_configuration_required")
        require(all(not parent.is_symlink() for parent in path.parents), "configuration_link")
        raw = path.read_bytes()
        require(0 < len(raw) <= 4 * 1024 * 1024, "configuration_size")
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError) as error:
            raise AuditError("final_run_configuration_json") from error
        validate_configuration(value)
        registered = self._registration()
        require(value["study_record"] == registered["id"]
            and value["seed_record"] == registered["payload"]["seed_record"], "configuration_study")
        content = {"method": METHOD, "implementation": implementation(), "policy": POLICY,
            "study_record": registered["id"], "seed_record": value["seed_record"],
            "configuration_artifact": digest(value), "raw_configuration_artifact": hashlib.sha256(raw).hexdigest(),
            "declarations_are_not_verification": True, "new_model_calls": 0}
        existing = self._one(STAGE_PLAN, optional=True)
        require(existing is None or same(existing["payload"], content), "configuration_changed_requires_amendment")
        self._version_once(session, context, "protocol", METHOD + ":offline-stages", content)
        require(self.ledger.artifacts.put_bytes(raw) == content["raw_configuration_artifact"], "configuration_bytes")
        self.ledger.artifacts.put(value)
        identifier = existing["id"] if existing else self.ledger.record(session, STAGE_PLAN, METHOD, content)
        return {"stage_plan_record": identifier, "configuration_artifact": content["configuration_artifact"], "new_model_calls": 0}


def validate_configuration(value):
    fields = {"version", "study_record", "seed_record", "source_bindings", "registry", "batch_declaration",
        "preparation_limits", "runtime", "quota_receipt", "resource_policy", "series_limits"}
    require(isinstance(value, dict) and fields <= set(value) <= fields | {"collect_lifecycle_evidence"}
        and type(value.get("collect_lifecycle_evidence", False)) is bool
        and value["version"] == "final-validation-offline-stages-v1",
        "configuration_fields")
    execution.sha(value["study_record"])
    execution.sha(value["seed_record"])
    require(all(isinstance(value[key], dict) for key in fields - {"version", "study_record", "seed_record"}),
        "configuration_objects")
    series.limits(value["series_limits"])
    require_no_credentials(value)


def _stage(parent, owner, source_owner, payload, *, objective, actor):
    """One actual audited parent per stage; close its lock before the next."""
    engine = parent(owner, source_owner=source_owner)
    try:
        return engine.execute("status", payload, objective=objective, actor=actor)
    finally:
        engine.close()


def offline_prepare(owner, source_owner, config_path, *, objective, actor):
    """Runnable exact-declaration path from the already initialized Study.

    Each producer verifies its own concrete evidence and retains its intent
    before work. A later failure leaves completed stages replayable, never
    replaces their cutoffs or seeds. No account model is dispatched here.
    """
    retained = _stage(FinalValidationRun, owner, source_owner,
        {"action": "retain-config", "config_path": str(config_path)}, objective=objective, actor=actor)
    engine = FinalValidationRun(owner, source_owner=source_owner)
    try:
        value = engine.ledger.artifacts.read(retained["configuration_artifact"])
    finally:
        engine.close()
    snapshot_module, preparation_module = lineage.v11_snapshot, lineage.v11_preparation
    reconciliation, task, batch = packets.reconciliation, closure.batch.task, closure.batch
    frozen = _stage(snapshot_module.SnapshotParent, owner, source_owner,
        {"action": "freeze", "binding": snapshot_module.binding(value["study_record"], value["seed_record"], value["source_bindings"])},
        objective=objective, actor=actor)
    snapshot_binding = {key: frozen[key] for key in ("snapshot_record", "snapshot_artifact")}
    prep_binding = preparation_module.binding(study_record=value["study_record"], seed_record=value["seed_record"],
        snapshot_binding=snapshot_binding, limits=value["preparation_limits"])
    prepared = _stage(preparation_module.Preparation, owner, source_owner,
        {"action": "prepare", "binding": prep_binding}, objective=objective, actor=actor)
    selected = reconciliation.binding(preparation_record=prepared["preparation_record"], study_record=value["study_record"],
        seed_record=value["seed_record"], snapshot_binding=snapshot_binding)
    reconciled = _stage(reconciliation.Reconciliation, owner, source_owner,
        {"action": "reconcile", "binding": selected, "registry": value["registry"]}, objective=objective, actor=actor)
    frame_binding = packets.frame_binding(preparation_binding=selected, reconciliation_record=reconciled["reconciliation_record"])
    census = _stage(task.TaskCensusParent, owner, source_owner,
        {"action": "collect", "binding": frame_binding}, objective=objective, actor=actor)
    supplemental = None
    if value.get("collect_lifecycle_evidence", False):
        supplemental = _stage(lifecycle.LifecycleParent, owner, source_owner,
            {"action": "collect", "task_census_record": census["task_census_record"]}, objective=objective, actor=actor)
    selected_batch = batch.binding(task_census_record=census["task_census_record"], task_census_binding=frame_binding)
    batch_payload = {"binding": selected_batch, "declaration": value["batch_declaration"]}
    batches = _stage(batch.BatchHistoryParent, owner, source_owner,
        {"action": "collect", **batch_payload}, objective=objective, actor=actor)
    lookup = _stage(batch.BatchHistoryParent, owner, source_owner,
        {"action": "lookup", **batch_payload}, objective=objective, actor=actor)
    closed = _stage(closure.HistoryClosureParent, owner, source_owner,
        {"action": "compile", "batch_history_record": batches["batch_history_record"], "pair_lookup_record": lookup["pair_lookup_record"]},
        objective=objective, actor=actor)
    final_frame = _stage(packets.PacketParent, owner, source_owner,
        {"action": "freeze_final_frame", "binding": frame_binding}, objective=objective, actor=actor)
    result = _stage(FinalValidationRun, owner, source_owner, {"action": "prepare",
        "binding": binding(final_frame_record=final_frame["final_frame_record"], closure_record=closed["closure_record"]),
        **{key: value[key] for key in ("runtime", "quota_receipt", "resource_policy", "series_limits")}},
        objective=objective, actor=actor)
    return {"stage_plan_record": retained["stage_plan_record"],
        "lifecycle_evidence_record": supplemental["lifecycle_record"] if supplemental else None, **result}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audited fixed initial Codex account validation; no API fallback.")
    parser.add_argument("action", choices=("prepare", "run-initial", "resume", "status"))
    parser.add_argument("--owner", required=True)
    parser.add_argument("--source-owner", required=True)
    parser.add_argument("--config", help="Protected exact offline-stage JSON; prepare only")
    parser.add_argument("--prepared-record")
    parser.add_argument("--quota-receipt", help="Protected exact fresh app-result JSON; run/resume only")
    args = parser.parse_args(argv)
    objective = "Execute the registered final dossier validation method with fixed sources, slots and history."
    actor = "codex-final-validation-run"
    if args.action == "prepare":
        require(args.config is not None and args.prepared_record is args.quota_receipt is None, "prepare_cli_fields")
        result = offline_prepare(args.owner, args.source_owner, args.config, objective=objective, actor=actor)
    else:
        require(args.config is None, "configuration_only_for_prepare")
        payload = {"action": args.action}
        if args.action != "status":
            require(args.prepared_record is not None and args.quota_receipt is not None, "run_cli_fields")
            # This is account metadata, never source text or a model result.
            receipt_path = Path(args.quota_receipt)
            require(receipt_path.is_absolute() and receipt_path.is_file() and not receipt_path.is_symlink()
                and not receipt_path.resolve().is_relative_to(study.ROOT.resolve()), "protected_quota_receipt_required")
            raw = receipt_path.read_bytes()
            require(0 < len(raw) <= 1024 * 1024, "quota_receipt_size")
            payload.update(prepared_record=args.prepared_record, quota_receipt=json.loads(raw))
        else:
            require(args.prepared_record is args.quota_receipt is None, "status_cli_fields")
        result = _stage(FinalValidationRun, args.owner, args.source_owner, payload, objective=objective, actor=actor)
    print(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
