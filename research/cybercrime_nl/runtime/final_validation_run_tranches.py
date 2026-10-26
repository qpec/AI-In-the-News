"""Concrete later account tranches over the original immutable validation series.

No initial window is renewed. Each later resource epoch is registered before
its untouched tasks, under the original cumulative ceilings. The old kernel
remains unchanged: only its missing-later-producer marker can be discharged,
after exact retained producer/epoch/Invocation verification. All other unknowns,
orphans, terminal outcomes and reservations remain cumulative and blocking.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

import final_validation_run as original
import final_validation_execution as initial
import final_validation_execution_v2 as kernel
import final_validation_fixed_slots as fixed
from newsresearch.common import AuditError, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-later-account-run-parent-v1"
INTENT = "cyber_final_validation_later_preparation_intent"
PRODUCER = "cyber_final_validation_later_packet_producer"
EPOCH = "cyber_final_validation_later_resource_epoch"
REPORT = "cyber_final_validation_later_run_report"
POLICY = {"account_only": True, "paid_api_fallback": False, "initial_window_renewed": False,
    "new_seed_draws": 0, "diagnostic_identities_added": [], "unknown_outcomes_retried": False,
    "unavailable_slots_replaced": False, "quota_purchase_or_reset": False,
    "generation_token_cap_enforced": False, "account_dollar_cost": None,
    "coordinator_invocations_not_remote_requests": True}


def require(value, reason):
    if not value:
        raise AuditError("later_run_" + reason)


def same(left, right):
    return canonical(left) == canonical(right)


def implementation():
    path = Path(__file__)
    return {**original.implementation(), **kernel.implementation(), **fixed.implementation(),
        path.relative_to(initial.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def resource_policy(value):
    """Same bounded units as initial admission; percentages never become tokens."""
    require(isinstance(value, dict), "resource_policy")
    value = {"unavailable_quota_policy": "block", **deepcopy(value)}
    require(set(value) == {"maximum_invocations", "maximum_token_reservations", "output_token_allowance",
        "not_before", "admit_before", "quota_valid_for_seconds", "unavailable_quota_policy", "decision_note"}, "resource_policy")
    for name in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance", "quota_valid_for_seconds"):
        initial.integer(value[name], 1)
    require(value["maximum_invocations"] <= 60 and initial.timestamp(value["not_before"]) < initial.timestamp(value["admit_before"])
        and value["unavailable_quota_policy"] in {"block", "allow_bounded_registered"}
        and isinstance(value["decision_note"], str) and value["decision_note"].strip(), "resource_policy")
    require_no_credentials(value)
    return value


def resources_for(policy, quota, policy_artifact):
    value = {k: policy[k] for k in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance",
        "not_before", "admit_before", "unavailable_quota_policy")}
    value.update(quota_policy_evidence_sha256=policy_artifact,
        quota={"state": "unavailable", "remaining_invocations": None, "remaining_tokens": None,
            "observed_at": quota["captured_at"], "valid_until": (initial.timestamp(quota["captured_at"])
                + timedelta(seconds=policy["quota_valid_for_seconds"])).isoformat(), "evidence_sha256": digest(quota)})
    initial.validate_resources(value)
    return value


def dispatch_binding(packet, saved, profile, owner):
    """Rebuild retained application-controlled wire without opening a CLI worker."""
    transport = original.provider
    require(isinstance(saved, dict) and isinstance(saved.get("cwd"), str), "dispatch_shape")
    cwd = Path(saved["cwd"])
    require(cwd.is_absolute() and cwd.parent == owner / "final-validation-account-workers"
        and cwd.name.startswith("codex-judge-"), "dispatch_worker_scope")
    invocation_id = saved.get("invocation_id")
    try:
        require(str(uuid.UUID(invocation_id)) == invocation_id, "dispatch_invocation_id")
    except (TypeError, ValueError, AttributeError) as error:
        raise AuditError("later_run_dispatch_invocation_id") from error
    # _command is deterministic and reads only these immutable configured fields.
    shape = object.__new__(transport.PairProvider)
    shape.executable, shape.model = profile["cli_binding"]["executable"], initial.contract.MODEL
    command = shape._command(cwd)
    invocation = transport.PreparedPairInvocation(command, cwd, packet["stdin"], packet["request"]["schema"],
        packet["request"], initial.contract.MODEL, packet, profile["cli_binding"], profile["tokenizer_identity"], invocation_id)
    require(same(invocation.manifest(), saved), "dispatch_exact_wire")
    return invocation


class LaterValidationRun(original.FinalValidationRun):
    """New audited entry point; the initial Run and all original helpers stay fixed."""

    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        fields = {
            "prepare-next": {"action", "prepared_record", "primary_limit", "quota_receipt", "resource_policy"},
            "admit": {"action", "prepared_record", "producer_record", "quota_receipt", "resource_policy"},
            "run": {"action", "prepared_record", "producer_record", "epoch_record", "quota_receipt"},
            "resume": {"action", "prepared_record", "producer_record", "epoch_record", "quota_receipt"},
            "status": {"action", "prepared_record"},
            "fixed-look": {"action", "prepared_record", "look"},
        }
        require(operation == "status" and not versions and data.get("action") in fields
            and set(data) == fields[data["action"]], "entry_shape")
        for name in ("prepared_record", "producer_record", "epoch_record"):
            if name in data:
                initial.sha(data[name])
        require_no_credentials(data)
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    def _sequence(self, record):
        row = self.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (record,)).fetchone()
        require(row is not None and type(row[0]) is int, "record_sequence")
        return row[0]

    def _versions(self, session, context, content):
        return {kind: self._version_once(session, context, kind, METHOD + ":" + kind + ":" + digest(content), content)
            for kind in ("protocol", "policy")}

    def _registered(self, record, value):
        require(value["method"] == METHOD and same(value["implementation"], implementation())
            and same(value["policy"], POLICY), "producer_code")
        expected = {k: v for k, v in value.items() if k != "versions"}
        kernel._registered(self, value["versions"], expected)
        require(all(self._sequence(v) < self._sequence(record) for v in value["versions"].values()), "registration_chronology")

    def _prior_state(self, session, reference, sequence, loaded, manifest_ids):
        """Validate a retained census against the exact earlier durable event set."""
        state = self.ledger.artifacts.read(reference)
        raw = self.ledger.artifacts.read(state["kernel_census_sha256"])
        require(state["series_record"] == loaded[0]["series_record"] and state["scope_sha256"] == loaded[1]["scope_sha256"]
            and state["manifest_records"] == manifest_ids and not state["blockers"]
            and state["later_producer_method"] == METHOD and same(state["later_producer_implementation"], implementation())
            and state["unsupported_later_intent_sha256"] == [], "prior_census_scope")
        require(all(same(state[k], v) for k, v in raw.items() if k != "blockers")
            and state["cleared_kernel_blockers"] in ([], ["later_dispatch_producer_not_bound"])
            and sorted(set(raw["blockers"]) - set(state["cleared_kernel_blockers"])) == [], "prior_census_only_producer_gap")
        events = [{"seq": r[0], "kind": r[1], "payload": json.loads(r[2]), "event_hash": r[3]}
            for r in self.ledger.db.execute("SELECT seq,kind,payload,event_hash FROM events WHERE seq<? AND kind IN "
                "('model.attempt.intended','model.attempt.completed','model.attempt.resolved') ORDER BY seq", (sequence,))]
        intended = [e["payload"] for e in events if e["kind"] == "model.attempt.intended"]
        require(digest(events) == raw["generic_events_sha256"]
            and sorted(r["logical_task_id"] for r in intended) == state["attempted_logical_ids"], "prior_census_event_binding")
        responses = {r["attempt"]: r for kind in (initial.RESULT_KIND, kernel.RESULT)
            for r in initial.rows(self, session, kind) if self._sequence(r["_record_id"]) < sequence}
        accounting = raw["accounting"]
        require(accounting["coordinator_invocations"] == len(intended)
            and accounting["reservation_tokens"] == sum(r["reservation_tokens"] for r in intended)
            and accounting["committed_token_units"] == sum(max(r["reservation_tokens"],
                responses.get(r["attempt"], {}).get("observed_token_units") or 0) for r in intended), "prior_census_liabilities")
        return state

    def _quota_value(self, record, registered):
        value = self.ledger.get(record, original.admission.QUOTA)
        receipt = self.ledger.artifacts.read(value["receipt_artifact"])
        expected = {"method": original.admission.METHOD, "study_record": registered["id"],
            "receipt_artifact": digest(receipt), "captured_at": receipt["captured_at"],
            "percentage_observation": original.admission.quota_percentages(receipt["raw_result"], receipt["selected_limit_id"]),
            "unit_capacity_state": "unavailable", "remaining_invocations": None, "remaining_tokens": None,
            "origin_independently_authenticated": False, "account_dollar_cost": None, "new_account_probe_by_helper": False}
        require(receipt["source"] == "codex_app_get_usage_limits" and receipt["source_reference"]
            and same(value, expected), "quota_record")
        return value

    def _produce_later(self, loaded, plan, resources):
        value, _, runtime, verified, _ = loaded
        frame_value, chain, frame, schedule, saved, projection, registered = verified
        snapshot, index, _, reconciled, *_ = chain
        # Reuse the exact original bindings/history envelope; only selection and
        # resource window differ. No role, article ordering or seed is selected here.
        original_fixed = self.ledger.artifacts.read(value["fixed_slot_artifact"])
        bindings = original_fixed["bindings"]
        return fixed.prepare_fixed_slots(frame, schedule, self._documents(snapshot, index),
            selection={"kind": "later", "plan": plan, "ceilings": self.ledger.get(value["series_record"], kernel.SERIES)["limits"],
                "primary_limit": len(plan["primary_ranks"])},
            legacy_records=self.ledger.artifacts.read(reconciled["artifacts"]["pair_history_records"]),
            legacy_inventory=self.ledger.artifacts.read(reconciled["artifacts"]["pair_history_inventory"]),
            closure_evidence=fixed.BoundClosureEvidence(canonical(projection).encode(), saved["effective_projection_artifact"]),
            order_seed=self.ledger.artifacts.read(frame_value["article_order_seed_artifact"])["seed"], bindings=bindings,
            token_counter=runtime["token_counter"], cli_profile=runtime["cli_profile"], resources=resources,
            user_instruction_sha256=registered["payload"]["instruction_evidence_artifact"])

    def _load_producers(self, session, loaded):
        initial_value, first, _, verified, _ = loaded
        series_id, frame, schedule = initial_value["series_record"], verified[2], verified[3]
        series = kernel.load_series(self, session, series_id, frame, schedule)
        manifests, _ = kernel._manifests(self, session, series, frame, schedule, series_id)
        producers = initial.rows(self, session, PRODUCER)
        require(len({r["manifest_record"] for r in producers}) == len(producers)
            and {r["manifest_record"] for r in producers} == {r for r, _ in manifests[1:]}, "unbound_later_manifest")
        by_manifest = {}
        for row in producers:
            identifier = row["_record_id"]
            value = {k: v for k, v in row.items() if k != "_record_id"}
            self._registered(identifier, value)
            intended = self.ledger.get(value["intent_record"], INTENT)
            self._registered(value["intent_record"], intended)
            require(value["initial_prepared_record"] == intended["initial_prepared_record"] == self._one(original.PREPARED)["id"]
                and value["series_record"] == intended["series_record"] == series_id
                and same(value["plan"], intended["plan"]), "producer_initial_binding")
            preceding = [ref for ref, _ in manifests[:next(n for n, (ref, _) in enumerate(manifests) if ref == value["manifest_record"])]]
            prior_state = self._prior_state(session, value["plan"]["prior_census_sha256"], self._sequence(value["intent_record"]), loaded, preceding)
            require(kernel._settled_states(prior_state["states"]), "producer_previous_not_closed")
            quota = self._quota_value(intended["quota_record"], verified[-1])
            policy = resource_policy(intended["resource_policy"])
            require(intended["history_protocol"] == initial_value["history_protocol"]
                and all(policy[k] <= first["resources"][k] for k in (
                    "maximum_invocations", "maximum_token_reservations", "output_token_allowance")), "producer_resource_scope")
            resources = resources_for(policy, quota, self.ledger.artifacts.put({k: v for k, v in intended.items() if k != "versions"}))
            fixed_slots = self._produce_later(loaded, value["plan"], resources)
            require(fixed_slots.digest == value["fixed_slot_artifact"]
                and same(self.ledger.artifacts.read(fixed_slots.digest), fixed_slots.payload), "producer_packet_replay")
            for reference, raw in fixed_slots.artifacts.items():
                require(self.ledger.artifacts.read_bytes(reference) == raw, "producer_artifact")
            manifest = dict(manifests)[value["manifest_record"]]
            require(same({k: v for k, v in manifest.items() if k not in {"versions", "manifest_sha256"}},
                self._content(loaded, series, value["plan"], fixed_slots, resources))
                and same({k: v for k, v in value.items() if k != "versions"}, self._producer_value(loaded,
                    value["initial_prepared_record"], value["intent_record"], value["manifest_record"], manifest, fixed_slots)),
                "producer_exact_replay")
            require(same(manifest["tasks"], kernel._normalize_tasks(fixed_slots.tasks, kernel._role_slots(schedule, value["plan"]["primary_ranks"]), frame,
                first["scope"], resources["output_token_allowance"])) and same(manifest["resources"], resources)
                and value["manifest_sha256"] == manifest["manifest_sha256"]
                and value["history_envelope_sha256"] == fixed_slots.payload["history_envelope_sha256"]
                and value["history_envelope_sha256"] == self.ledger.artifacts.read(initial_value["fixed_slot_artifact"])["history_envelope_sha256"],
                "producer_manifest_binding")
            require(self._sequence(value["intent_record"]) < self._sequence(value["manifest_record"]) < self._sequence(identifier), "producer_chronology")
            kernel.resume_tranche(self, session, series_record=series_id, frame=frame, schedule=schedule,
                manifest_record=value["manifest_record"])
            by_manifest[value["manifest_record"]] = (identifier, value)
        return series, manifests, by_manifest

    def _content(self, loaded, series, plan, prepared, resources):
        frame, schedule = loaded[3][2:4]
        tasks = kernel._normalize_tasks(prepared.tasks, kernel._role_slots(schedule, plan["primary_ranks"]), frame,
            loaded[1]["scope"], resources["output_token_allowance"])
        planned = sum(t["reservation_tokens"] for t in tasks)
        fresh = sum(t["disposition"] == "fresh" for t in tasks)
        require(len(tasks) <= resources["maximum_invocations"] <= series["limits"]["maximum_tranche_invocations"]
            and fresh <= resources["maximum_invocations"] and planned <= resources["maximum_token_reservations"],
            "tranche_resource_limits")
        return {"method": kernel.METHOD, "series": digest(series), "scope": loaded[1]["scope"],
            "scope_sha256": loaded[1]["scope_sha256"], "previous_manifest": plan["previous_manifest"], "plan": plan,
            "tasks": tasks, "resources": resources, "planned_token_reservations": planned, "planned_new_invocations": fresh,
            "cli_profile": loaded[1]["cli_profile"], "implementation": kernel.implementation(), "schedule_sha256": schedule.digest,
            **kernel.POLICY, "later_full_source_slot_authority_verified": False}

    def _producer_value(self, loaded, prepared_record, intent_id, manifest_id, manifest, prepared):
        return {"method": METHOD, "implementation": implementation(), "initial_prepared_record": prepared_record,
            "intent_record": intent_id, "series_record": loaded[0]["series_record"], "manifest_record": manifest_id,
            "manifest_sha256": manifest["manifest_sha256"], "fixed_slot_artifact": prepared.digest, "plan": manifest["plan"],
            "history_envelope_sha256": prepared.payload["history_envelope_sha256"], "policy": POLICY}

    def _recover_local_producer(self, session, context, loaded, prepared_record):
        """Finish only an exact local write gap; no provider/attempt/epoch exists."""
        series_id, frame, schedule = loaded[0]["series_record"], loaded[3][2], loaded[3][3]
        series = kernel.load_series(self, session, series_id, frame, schedule)
        manifests, _ = kernel._manifests(self, session, series, frame, schedule, series_id)
        known = initial.rows(self, session, PRODUCER)
        require(len({r["manifest_record"] for r in known}) == len(known)
            and {r["manifest_record"] for r in known} <= {ref for ref, _ in manifests[1:]}, "unbound_later_manifest")
        missing = [(ref, manifest) for ref, manifest in manifests[1:] if ref not in {r["manifest_record"] for r in known}]
        if not missing:
            return
        require(len(missing) == 1 and missing[0][0] == manifests[-1][0], "unbound_later_manifest")
        identifier, manifest = missing[0]
        attempts = [json.loads(r[0]) for r in self.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'")]
        logical = {t["logical_task_id"] for t in manifest["tasks"]}
        custom = [r for kind in (kernel.INTENT, kernel.RESULT, kernel.HALT) for r in initial.rows(self, session, kind)]
        require(not any(r.get("manifest") == identifier or r.get("logical_task_id") in logical for r in attempts + custom),
            "orphan_manifest_already_attempted")
        intents = [r for r in initial.rows(self, session, INTENT) if same(r["plan"], manifest["plan"])]
        require(len(intents) == 1, "orphan_manifest_intent")
        intent_id = intents[0]["_record_id"]
        intended = {k: v for k, v in intents[0].items() if k != "_record_id"}
        self._registered(intent_id, intended)
        require(intended["initial_prepared_record"] == prepared_record and intended["series_record"] == series_id
            and self._sequence(intent_id) < self._sequence(identifier), "orphan_manifest_authority")
        prior = self._prior_state(session, manifest["plan"]["prior_census_sha256"], self._sequence(intent_id), loaded,
            [ref for ref, _ in manifests[:-1]])
        require(kernel._settled_states(prior["states"]), "orphan_manifest_prior_incomplete")
        quota = self._quota_value(intended["quota_record"], loaded[3][-1])
        policy = resource_policy(intended["resource_policy"])
        require(intended["history_protocol"] == loaded[0]["history_protocol"]
            and all(policy[k] <= loaded[1]["resources"][k] for k in (
                "maximum_invocations", "maximum_token_reservations", "output_token_allowance")), "orphan_resource_scope")
        resources = resources_for(policy, quota,
            self.ledger.artifacts.put({k: v for k, v in intended.items() if k != "versions"}))
        prepared = self._produce_later(loaded, manifest["plan"], resources)
        require(prepared.payload["history_envelope_sha256"] == self.ledger.artifacts.read(
            loaded[0]["fixed_slot_artifact"])["history_envelope_sha256"], "orphan_history_scope")
        require(same(self.ledger.artifacts.read(prepared.digest), prepared.payload), "orphan_packet_artifact")
        for ref, raw in prepared.artifacts.items():
            require(self.ledger.artifacts.read_bytes(ref) == raw, "orphan_packet_bytes")
        expected = self._content(loaded, series, manifest["plan"], prepared, resources)
        require(same({k: v for k, v in manifest.items() if k not in {"versions", "manifest_sha256"}}, expected),
            "orphan_manifest_changed")
        value = self._producer_value(loaded, prepared_record, intent_id, identifier, manifest, prepared)
        self.ledger.record(session, PRODUCER, identifier, {**value, "versions": self._versions(session, context, value)})

    def _load_epoch(self, session, record, loaded, producers):
        value = self.ledger.get(record, EPOCH)
        self._registered(record, value)
        producer_id, producer = producers.get(value["manifest_record"], (None, None))
        require(producer_id == value["producer_record"] and value["series_record"] == loaded[0]["series_record"]
            and value["initial_prepared_record"] == self._one(original.PREPARED)["id"], "epoch_producer_binding")
        quota = self._quota_value(value["quota_record"], loaded[3][-1])
        policy = resource_policy(value["resource_policy"])
        policy_artifact = self.ledger.artifacts.read(value["resource_policy_artifact"])
        require(same(policy_artifact, {"method": METHOD, "producer_record": producer_id,
            "series_record": value["series_record"], "policy": policy,
            "instruction_evidence_artifact": loaded[3][-1]["payload"]["instruction_evidence_artifact"], **POLICY}), "epoch_policy")
        require(same(value["resources"], resources_for(policy, quota, value["resource_policy_artifact"])), "epoch_resources")
        manifest = self.ledger.get(value["manifest_record"], kernel.TRANCHE)
        require(all(same(value["resources"][key], manifest["resources"][key]) for key in (
            "maximum_invocations", "maximum_token_reservations", "output_token_allowance")), "epoch_cannot_expand_tranche")
        require(self._sequence(producer_id) < self._sequence(record), "epoch_chronology")
        expected_manifests = [loaded[0]["manifest_record"], *producers]
        expected_manifests = expected_manifests[:expected_manifests.index(value["manifest_record"]) + 1]
        prior = self._prior_state(session, value["prior_census_artifact"], self._sequence(record), loaded, expected_manifests)
        require(value["untouched_logical_task_ids"] == [t["logical_task_id"] for t in manifest["tasks"]
            if t["disposition"] == "fresh" and t["logical_task_id"] not in prior["attempted_logical_ids"]], "epoch_untouched_binding")
        return value

    def _census(self, session, loaded, *, producers=None):
        series, manifests, producers = self._load_producers(session, loaded) if producers is None else producers
        value, _, runtime, verified, _ = loaded
        raw = kernel.census(self, session, series_record=value["series_record"], frame=verified[2], schedule=verified[3])
        proofs, unsupported, epochs = [], [], {}
        tasks = {t["logical_task_id"]: (identifier, t) for identifier, manifest in manifests for t in manifest["tasks"]}
        for sequence, payload in self.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
            row = json.loads(payload)
            if row.get("manifest") == value["manifest_record"]:
                continue
            try:
                identifier, task = tasks[row["logical_task_id"]]
                producer_id, _ = producers[identifier]
                require(row["producer_record"] == producer_id and row["producer_method"] == METHOD
                    and row["producer_implementation_sha256"] == digest(implementation()), "intent_producer")
                if row["epoch_record"] not in epochs:
                    epochs[row["epoch_record"]] = self._load_epoch(session, row["epoch_record"], loaded, producers)
                epoch = epochs[row["epoch_record"]]
                require(epoch["producer_record"] == producer_id and self._sequence(row["epoch_record"]) < sequence,
                    "intent_epoch_chronology")
                require(row["logical_task_id"] in epoch["untouched_logical_task_ids"], "intent_not_admitted")
                started = initial.timestamp(row["started_at"])
                limits = epoch["resources"]
                require(initial.timestamp(limits["not_before"]) <= started < initial.timestamp(limits["admit_before"])
                    and initial.timestamp(limits["quota"]["observed_at"]) <= started < initial.timestamp(limits["quota"]["valid_until"]),
                    "intent_outside_epoch")
                require(limits["unavailable_quota_policy"] == "allow_bounded_registered"
                    and not self._quota_value(epoch["quota_record"], verified[-1])["percentage_observation"]["known_exhausted"],
                    "intent_quota_policy")
                observed = self._quota_value(row["fresh_quota_record"], verified[-1])
                require(self._sequence(row["fresh_quota_record"]) < sequence and not observed["percentage_observation"]["known_exhausted"]
                    and 0 <= (started - initial.timestamp(observed["captured_at"])).total_seconds()
                        < epoch["resource_policy"]["quota_valid_for_seconds"], "intent_fresh_quota")
                dispatch_binding(task["packet"], self.ledger.artifacts.read(row["dispatch"]), runtime["cli_profile"], self.ledger.root)
                proofs.append({"attempt": row["attempt"], "producer": producer_id, "epoch": row["epoch_record"],
                    "intent_sha256": digest(row), "dispatch": row["dispatch"]})
            except (KeyError, TypeError, ValueError, AuditError):
                unsupported.append(digest(row))
        cleared = ["later_dispatch_producer_not_bound"] if proofs and not unsupported and "later_dispatch_producer_not_bound" in raw["blockers"] else []
        blockers = [reason for reason in raw["blockers"] if reason not in cleared]
        if unsupported:
            blockers.append("unsupported_later_dispatch_authority")
        return {**raw, "blockers": sorted(set(blockers)), "later_producer_method": METHOD,
            "later_producer_implementation": implementation(), "kernel_census_sha256": self.ledger.artifacts.put(raw),
            "verified_later_dispatches": proofs, "unsupported_later_intent_sha256": unsupported,
            "cleared_kernel_blockers": cleared, "account_dollar_cost": None}

    def _plan(self, session, loaded, state, series, manifests, primary_limit):
        require(not state["blockers"] and kernel._settled_states(state["states"]), "previous_tranche_not_closed")
        frame, schedule = loaded[3][2:4]
        seen = [t["pair_rank"] for _, m in manifests for t in m["tasks"] if t["role"] == "primary"]
        require(seen == schedule.manifest["cumulative_primary_orders"][-1][:len(seen)], "primary_prefix_changed")
        plan = kernel.bounded_segment(schedule, start=len(seen), ceilings=series["limits"], primary_limit=primary_limit)
        for previous in range(1, plan["look"]):
            kernel._verified_look(self, session, loaded[0]["series_record"], frame, schedule, previous, state)
        return {**plan, "previous_manifest": manifests[-1][0], "prior_census_sha256": self.ledger.artifacts.put(state)}

    def _prepare_next(self, session, context, data, loaded):
        series, manifests, producers = self._load_producers(session, loaded)
        state = self._census(session, loaded, producers=(series, manifests, producers))
        plan = self._plan(session, loaded, state, series, manifests, data["primary_limit"])
        policy = resource_policy(data["resource_policy"])
        first = loaded[1]["resources"]
        require(all(policy[k] <= first[k] for k in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance")),
            "initial_per_tranche_ceiling_preserved")
        quota_id, quota = self._quota(session, context, loaded[3][-1], data["quota_receipt"])
        intended = {"method": METHOD, "implementation": implementation(), "initial_prepared_record": data["prepared_record"],
            "series_record": loaded[0]["series_record"], "plan": plan, "resource_policy": policy, "quota_record": quota_id,
            "history_protocol": loaded[0]["history_protocol"], "policy": POLICY}
        existing = [r for r in initial.rows(self, session, INTENT) if r["plan"]["start"] == plan["start"]]
        if existing:
            require(len(existing) == 1 and same({k: v for k, v in existing[0].items() if k not in {"_record_id", "versions"}}, intended),
                "incomplete_preparation_changed")
            intent_id = existing[0]["_record_id"]
        else:
            intent_id = self.ledger.record(session, INTENT, digest([loaded[0]["series_record"], plan["start"]]),
                {**intended, "versions": self._versions(session, context, intended)})
        resources = resources_for(policy, quota, self.ledger.artifacts.put(intended))
        prepared = self._produce_later(loaded, plan, resources)
        for reference, raw in prepared.artifacts.items():
            require(self.ledger.artifacts.put_bytes(raw) == reference, "packet_retention")
        require(self.ledger.artifacts.put(prepared.payload) == prepared.digest, "producer_retention")
        content = self._content(loaded, series, plan, prepared, resources)
        tasks = content["tasks"]
        known_tasks = {t["logical_task_id"] for _, m in manifests for t in m["tasks"]}
        physical = {digest(p) for _, m in manifests for t in m["tasks"] for p in t["history"]["physical_attempts"]}
        for task in tasks:
            require(task["logical_task_id"] not in known_tasks, "duplicate_logical_task_across_tranches")
            for attempt in task["history"]["physical_attempts"]:
                require(digest(attempt) not in physical, "independent_slots_share_physical_history")
                physical.add(digest(attempt))
        planned, fresh = content["planned_token_reservations"], content["planned_new_invocations"]
        require(state["accounting"]["coordinator_invocations"] + fresh <= series["limits"]["maximum_cumulative_invocations"]
            and state["accounting"]["committed_token_units"] + planned <= series["limits"]["maximum_cumulative_token_reservations"],
            "cumulative_reservation_limit")
        registration = kernel._tranche_protocol(loaded[0]["series_record"], content)
        manifest = {**content, "versions": self._versions(session, context, registration), "manifest_sha256": digest(content)}
        manifest_id = self.ledger.record(session, kernel.TRANCHE, digest([loaded[0]["series_record"], plan["start"]]), manifest)
        value = self._producer_value(loaded, data["prepared_record"], intent_id, manifest_id, manifest, prepared)
        identifier = self.ledger.record(session, PRODUCER, manifest_id, {**value, "versions": self._versions(session, context, value)})
        self._load_producers(session, loaded)
        return {"producer_record": identifier, "manifest_record": manifest_id, "primary_count": len(plan["primary_ranks"]),
            "slot_count": len(tasks), "fresh_slots": fresh, "new_model_calls": 0, "statistical_look": False}

    def _admit(self, session, context, data, loaded):
        series, manifests, producers = self._load_producers(session, loaded)
        manifest_id, manifest = manifests[-1]
        require(manifest_id in producers and producers[manifest_id][0] == data["producer_record"], "current_producer_required")
        state = self._census(session, loaded, producers=(series, manifests, producers))
        require(not state["blockers"], "existing_attempts_block_admission")
        policy = resource_policy(data["resource_policy"])
        require(all(same(policy[k], manifest["resources"][k]) for k in (
            "maximum_invocations", "maximum_token_reservations", "output_token_allowance")), "epoch_cannot_expand_tranche")
        quota_id, quota = self._quota(session, context, loaded[3][-1], data["quota_receipt"])
        policy_ref = self.ledger.artifacts.put({"method": METHOD, "producer_record": data["producer_record"],
            "series_record": loaded[0]["series_record"], "policy": policy,
            "instruction_evidence_artifact": loaded[3][-1]["payload"]["instruction_evidence_artifact"], **POLICY})
        untouched = [t for t in manifest["tasks"] if t["disposition"] == "fresh" and t["logical_task_id"] not in state["attempted_logical_ids"]]
        require(state["accounting"]["coordinator_invocations"] + len(untouched) <= series["limits"]["maximum_cumulative_invocations"]
            and state["accounting"]["committed_token_units"] + sum(t["reservation_tokens"] for t in untouched)
                <= series["limits"]["maximum_cumulative_token_reservations"], "cumulative_reservation_limit")
        value = {"method": METHOD, "implementation": implementation(), "initial_prepared_record": data["prepared_record"],
            "producer_record": data["producer_record"], "manifest_record": manifest_id, "series_record": loaded[0]["series_record"],
            "resource_policy": policy, "resource_policy_artifact": policy_ref, "quota_record": quota_id,
            "resources": resources_for(policy, quota, policy_ref), "prior_census_artifact": self.ledger.artifacts.put(state),
            "untouched_logical_task_ids": [t["logical_task_id"] for t in untouched], "policy": POLICY}
        retained = [r for r in initial.rows(self, session, EPOCH) if same({k: v for k, v in r.items() if k not in {"versions", "_record_id"}}, value)]
        if retained:
            require(len(retained) == 1, "duplicate_epoch")
            return {"epoch_record": retained[0]["_record_id"], "reused": True}
        record = self.ledger.record(session, EPOCH, digest(value), {**value, "versions": self._versions(session, context, value)})
        self._load_epoch(session, record, loaded, producers)
        return {"epoch_record": record, "reused": False, "new_model_calls": 0}

    def _conditions(self, session, loaded, epoch, fresh_quota, producers):
        require(same(epoch["implementation"], implementation()), "implementation_changed")
        state = self._census(session, loaded, producers=producers)
        reasons = list(state["blockers"])
        now, resources = datetime.now(timezone.utc), epoch["resources"]
        if (self.ledger.root / "STOP").exists():
            reasons.append("user_stop")
        if not initial.timestamp(resources["not_before"]) <= now < initial.timestamp(resources["admit_before"]):
            reasons.append("outside_registered_admission_window")
        if not initial.timestamp(resources["quota"]["observed_at"]) <= now < initial.timestamp(resources["quota"]["valid_until"]):
            reasons.append("quota_observation_stale")
        if not 0 <= (now - initial.timestamp(fresh_quota["captured_at"])).total_seconds() < epoch["resource_policy"]["quota_valid_for_seconds"]:
            reasons.append("fresh_quota_observation_required")
        original_quota = self._quota_value(epoch["quota_record"], loaded[3][-1])
        if original_quota["percentage_observation"]["known_exhausted"] or fresh_quota["percentage_observation"]["known_exhausted"]:
            reasons.append("observed_account_limit_exhausted")
        if resources["unavailable_quota_policy"] == "block":
            reasons.append("quota_unit_capacity_unavailable_policy_blocks")
        return state, sorted(set(reasons))

    def _fixed_look(self, session, loaded, look):
        require(type(look) is int and look in (1, 2, 3), "declared_look")
        series, manifests, producers = self._load_producers(session, loaded)
        state = self._census(session, loaded, producers=(series, manifests, producers))
        frame, schedule = loaded[3][2:4]
        seen = [t["pair_rank"] for _, m in manifests for t in m["tasks"] if t["role"] == "primary"]
        require(not state["blockers"] and kernel._settled_states(state["states"])
            and seen == schedule.manifest["cumulative_primary_orders"][look - 1], "complete_fixed_look_required")
        result = kernel.results.summarize_look(frame, schedule.manifest["primary_sample"], schedule.manifest["qc"],
            state["observations"], look=look, reference_projection_binding=digest(state))
        value = {"method": kernel.METHOD, "series_record": loaded[0]["series_record"], "look": look, "result": result,
            "census_sha256": self.ledger.artifacts.put(state), "implementation": kernel.implementation(), **kernel.POLICY}
        prior = [r for r in initial.rows(self, session, kernel.LOOK) if r["look"] == look]
        if prior:
            require(len(prior) == 1 and same({k: v for k, v in prior[0].items() if k != "_record_id"}, value), "fixed_look_changed")
            return {"look_record": prior[0]["_record_id"], "reused": True}
        return {"look_record": self.ledger.record(session, kernel.LOOK, digest([loaded[0]["series_record"], look]), value), "reused": False}

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        loaded = self._load_run(session, context, data["prepared_record"])
        self._recover_local_producer(session, context, loaded, data["prepared_record"])
        if data["action"] == "prepare-next":
            return self._prepare_next(session, context, data, loaded)
        if data["action"] == "admit":
            return self._admit(session, context, data, loaded)
        if data["action"] == "fixed-look":
            return self._fixed_look(session, loaded, data["look"])
        producers = self._load_producers(session, loaded)
        if data["action"] == "status":
            state = self._census(session, loaded, producers=producers)
            return {"census_artifact": self.ledger.artifacts.put(state), "blockers": state["blockers"],
                "states": dict(Counter(state["states"].values())), "accounting": state["accounting"], "new_model_calls": 0}
        epoch = self._load_epoch(session, data["epoch_record"], loaded, producers[2])
        require(epoch["producer_record"] == data["producer_record"] and epoch["manifest_record"] == producers[1][-1][0],
            "current_epoch_producer_required")
        quota_id, quota = self._quota(session, context, loaded[3][-1], data["quota_receipt"])
        state, reasons = self._conditions(session, loaded, epoch, quota, producers)
        manifest = producers[1][-1][1]
        local_attempts = [r for r in initial.rows(self, session, kernel.INTENT) if r["manifest"] == epoch["manifest_record"]]
        require(data["action"] == "resume" or not local_attempts, "existing_attempts_require_resume")
        provider = self._native_provider(session, loaded[2]) if not reasons and any(t["disposition"] == "fresh"
            and t["logical_task_id"] not in state["attempted_logical_ids"] for t in manifest["tasks"]) else None
        before = state["accounting"]["coordinator_invocations"]
        if provider is not None:
            state, reasons = LaterExecution(self, session, loaded, producers, epoch, data["epoch_record"], quota_id, quota, provider).run()
        report = {"method": METHOD, "prepared_record": data["prepared_record"], "producer_record": data["producer_record"],
            "epoch_record": data["epoch_record"], "census_artifact": self.ledger.artifacts.put(state), "blockers": reasons,
            "stop_reason": reasons[0] if reasons else "fixed_tranche_processed", "accounting": state["accounting"],
            "new_local_attempts": state["accounting"]["coordinator_invocations"] - before, "at": utc(), "statistical_look": False, **POLICY}
        identifier = self.ledger.record(session, REPORT, digest(report), report)
        return {"report_record": identifier, **report}


class LaterExecution:
    """Same exact PairProvider/gateway/parse loop; all admission uses series history."""

    def __init__(self, engine, session, loaded, producers, epoch, epoch_id, quota_id, quota, provider):
        require_active(engine, session)
        require(isinstance(provider, original.provider.PairProvider) and provider.research is engine and provider.session == session,
            "registered_pair_provider_required")
        self.engine, self.session, self.loaded, self.producers = engine, session, loaded, producers
        self.epoch, self.epoch_id, self.quota, self.provider = epoch, epoch_id, quota, provider
        self.quota_id = quota_id
        self.manifest_id, self.manifest = producers[1][-1]
        require(same({"cli_binding": provider.cli_binding, "tokenizer_identity": provider.tokenizer_identity}, self.manifest["cli_profile"]),
            "provider_profile_changed")

    def check(self):
        return self.engine._conditions(self.session, self.loaded, self.epoch, self.quota, self.producers)

    def run(self):
        state, reasons = self.check()
        for task in self.manifest["tasks"]:
            if reasons:
                break
            if task["disposition"] != "fresh" or task["logical_task_id"] in state["attempted_logical_ids"]:
                continue
            normalized = {(r["pair_rank"], r["role"]): r for r in state["observations"]}
            if initial.conditional_state(task, normalized) != "eligible":
                continue
            require(task["logical_task_id"] in self.epoch["untouched_logical_task_ids"], "task_outside_epoch")
            state, reasons = self.check()
            if reasons:
                break
            # Count ALL epochs for this manifest, and ALL manifests for the series.
            ledger = self.engine.ledger
            intents = [json.loads(r[0]) for r in ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'")]
            local = [r for r in intents if r.get("manifest") == self.manifest_id]
            returned = {r["attempt"]: r for r in initial.rows(self.engine, self.session, kernel.RESULT)}
            committed = sum(max(r["reservation_tokens"], returned.get(r["attempt"], {}).get("observed_token_units") or 0) for r in local)
            resources, ceilings = self.epoch["resources"], self.producers[0]["limits"]
            if len(local) + 1 > resources["maximum_invocations"] or committed + task["reservation_tokens"] > resources["maximum_token_reservations"] \
                    or state["accounting"]["coordinator_invocations"] + 1 > ceilings["maximum_cumulative_invocations"] \
                    or state["accounting"]["committed_token_units"] + task["reservation_tokens"] > ceilings["maximum_cumulative_token_reservations"]:
                reasons = ["registered_task_or_token_limit"]
                break
            invocation = self.provider.prepare(task["packet"])
            state, reasons = self.check()
            if reasons:
                break
            attempt = str(uuid.uuid4())
            intended = {"attempt": attempt, "task_key": task["logical_task_id"], "logical_task_id": task["logical_task_id"],
                "validation_scope": self.manifest["scope_sha256"], "manifest": self.manifest_id, "batch": self.manifest_id,
                "task_sha256": digest(task), "number": 1, "pair_rank": task["pair_rank"], "role": task["role"],
                "reservation_tokens": task["reservation_tokens"], "packet": ledger.artifacts.put(task["packet"]),
                "request": ledger.artifacts.put(invocation.request), "dispatch": ledger.artifacts.put(invocation.manifest()),
                "started_at": utc(), "producer_record": self.epoch["producer_record"], "epoch_record": self.epoch_id,
                "producer_method": METHOD, "producer_implementation_sha256": digest(implementation()), "fresh_quota_record": self.quota_id}
            ledger.append(self.session, "model.attempt.intended", intended)
            ledger.unresolved[attempt] = intended
            ledger.record(self.session, kernel.INTENT, task["logical_task_id"], intended)
            _, response = next(self.engine.gateway.codex_dispatch(self.session, self.provider, [(invocation, attempt)], 1))
            response_ref = ledger.artifacts.put(asdict(response))
            raw = response.raw_response or {}
            parsed, error, status, positive, fatal_parse = None, None, "technical_unavailable", None, False
            if response.payload is not None:
                try:
                    parsed = self.provider.parse_response(invocation, response)
                    status = "provenance_unavailable" if parsed["provenance_gaps"] else \
                        "resolved" if parsed["reference_positive"] is not None else "epistemic_unknown"
                    positive = parsed["reference_positive"]
                except (ResearchError, KeyError, TypeError, ValueError) as caught:
                    code = str(caught)
                    error = code if isinstance(caught, ResearchError) and re.fullmatch(r"final_pair_[a-z0-9_]+", code) else type(caught).__name__
                    status = "invalid"
                    fatal_parse = isinstance(caught, AuditError) or code not in initial.ITEM_CONTENT_ERRORS
            units = initial.usage_units(response.usage)
            unknown = bool(raw.get("unknown_outcome"))
            if unknown:
                status, positive = "technical_unavailable", None
            overrun = units is not None and (units > task["reservation_tokens"] or response.usage["output_tokens"] > resources["output_token_allowance"])
            reason = ("token_allowance_exceeded" if overrun else "unknown_outcome" if unknown else "usage_unavailable" if units is None else
                "transport_unavailable" if response.payload is None else "reference_identity_or_adapter_failure" if fatal_parse else
                "reference_provenance_unavailable" if status == "provenance_unavailable" else None)
            result = {"manifest": self.manifest_id, "logical_task_id": task["logical_task_id"], "attempt": attempt,
                "pair_rank": task["pair_rank"], "role": task["role"], "status": status, "positive": positive,
                "response": response_ref, "parsed": ledger.artifacts.put(parsed) if parsed is not None else None,
                "validation_error": error, "unknown_outcome": unknown, "observed_token_units": units,
                "reservation_tokens": task["reservation_tokens"], "token_allowance_exceeded": overrun, "terminal_reason": reason, "at": utc()}
            result_id = ledger.record(self.session, kernel.RESULT, task["logical_task_id"], result)
            if not unknown:
                def project(event):
                    ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (attempt, task["logical_task_id"],
                        self.manifest_id, 1, intended["request"], response_ref, status, result_id, error, event))
                ledger.append(self.session, "model.attempt.completed", {"attempt": attempt, "response": response_ref,
                    "assessment": result_id, "status": status, "ended_at": utc()}, project)
                ledger.unresolved.pop(attempt)
            if reason:
                ledger.record(self.session, kernel.HALT, digest([self.manifest_id, result_id, reason]),
                    {"manifest": self.manifest_id, "reason": reason, "result": result_id, "at": utc()})
            state, reasons = self.check()
        return state, reasons
