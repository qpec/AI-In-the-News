"""Prospective bounded initial-tranche execution library; no launch command.

The real adapter must first freeze/verify the final source frame, random sample,
QC/diagnostic policy, authority, CLI/version/tokenizer and quota observation.
These helpers do not inspect those upstream owners or authorize a model run.
All persistence/dispatch below requires an active Research.execute operation.
Only the first <=40-primary/<=60-reserved-task tranche is supported here.
Output allowances are local reservations, NOT enforceable CLI generation caps.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

import final_validation_contract as contract
import final_validation_history as history
import final_validation_provider as transport
from newsresearch.common import AuditError, ResearchError, digest, require_active, require_no_credentials, utc

METHOD = "cybercrime-final-validation-initial-execution-v1"
MANIFEST_KIND = "final_validation_execution_manifest"
INTENT_KIND = "final_validation_execution_intent"
RESULT_KIND = "final_validation_execution_result"
HALT_KIND = "final_validation_execution_halt"
REPORT_KIND = "final_validation_execution_report"
ADMISSION_KIND = "final_validation_slot_admission"
SLOT_KIND = "final_validation_execution_slot_resolution"
TASK_FIELDS = ("pair_rank", "role", "packet", "history", "capacity_unavailable")
ROLES = ("primary", "qc", "qc_adjudication", "uncertain_adjudication")
ITEM_CONTENT_ERRORS = {"final_pair_" + name for name in (
    "response_capacity", "response_schema", "examined_source_coverage", "article_coverage",
    "empty_explanation", "clear_identity_missing", "focus_relationship_consistency",
    "citation_identity", "citation_source", "relationship_source_coverage")}
ROOT = Path(__file__).resolve().parents[3]


def require(value, code):
    if not value:
        raise AuditError("final_execution_" + code)


def sha(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), "sha256_required")


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "integer_required")


def timestamp(value):
    require(isinstance(value, str), "timestamp_required")
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise AuditError("final_execution_timestamp_required") from error
    require(result.tzinfo is not None, "timezone_required")
    return result


def implementation():
    paths = [Path(__file__), Path(transport.__file__), Path(contract.__file__), Path(history.__file__),
        Path(transport.CodexCLIProvider.__module__.replace(".", "/") + ".py")]
    paths[-1] = ROOT / "src" / paths[-1]
    paths += [ROOT / "src/newsresearch/astra_incident_validation.py",
              ROOT / "research/cybercrime_nl/runtime/final_validation_policy.py"]
    paths += [ROOT / "src/newsresearch" / name for name in ("common.py", "runtime.py", "gateway.py", "storage.py")]
    paths += [ROOT / "research/cybercrime_nl/runtime" / name for name in
              ("dossier_contract.py", "dossier_contract_v2.py", "dossier_contract_v3.py",
               "dossier_contract_v4.py", "dossier_contract_v5.py", "summary_fidelity_contract.py",
               "summary_fidelity_contract_v2.py")]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def source_identity(packet):
    return sorted([{k: row[k] for k in ("document_id", "title_sha256", "body_sha256", "input_sha256")}
                   for row in packet["source_bindings"]], key=lambda row: row["document_id"])


def logical_task_id(scope, packet, role):
    """Order/request/tranche-independent identity; packet changes cannot retry it."""
    sha(scope)
    require(role in ROLES, "role")
    contract.validate_packet(packet)
    return digest([METHOD, "logical-pair-role", scope, source_identity(packet), role])


def slot_catalog(tasks):
    """Source-free exact admission projection; a catalog is not permission."""
    return [{"pair_rank": t["pair_rank"], "role": t["role"],
        "source_identity_sha256": t["source_identity_sha256"],
        "history_entry_sha256": t["history"]["entry_sha256"],
        "capacity_unavailable": t["capacity_unavailable"], "disposition": t["disposition"],
        "request_sha256": t["request_sha256"]} for t in tasks]


def validate_resources(resources):
    require(isinstance(resources, dict) and set(resources) == {"maximum_invocations", "maximum_token_reservations",
        "output_token_allowance", "not_before", "admit_before", "quota", "unavailable_quota_policy",
        "quota_policy_evidence_sha256"}, "resource_fields")
    for key in ("maximum_invocations", "maximum_token_reservations", "output_token_allowance"):
        integer(resources[key], 1)
    require(resources["maximum_invocations"] <= 60, "initial_invocation_limit")
    require(timestamp(resources["not_before"]) < timestamp(resources["admit_before"]), "admission_window")
    quota = resources["quota"]
    require(isinstance(quota, dict) and set(quota) == {"state", "remaining_invocations", "remaining_tokens",
        "observed_at", "valid_until", "evidence_sha256"}, "quota_fields")
    sha(quota["evidence_sha256"])
    require(timestamp(quota["observed_at"]) <= timestamp(quota["valid_until"]), "quota_window")
    require(quota["state"] in {"known", "unavailable"}, "quota_state")
    if quota["state"] == "known":
        integer(quota["remaining_invocations"])
        integer(quota["remaining_tokens"])
    else:
        require(quota["remaining_invocations"] is None and quota["remaining_tokens"] is None, "unknown_quota_not_zero")
    require(resources["unavailable_quota_policy"] in {"block", "allow_bounded_registered"}, "quota_policy")
    sha(resources["quota_policy_evidence_sha256"])


def build_manifest(*, scope, prefix, tasks, cli_profile, resources, upstream_binding):
    """Pure immutable manifest. Upstream source/sample verification remains required.

    `prefix` is the unchanged initial_prefix_manifest output. `tasks` associates
    each fixed slot with its immutable historical lookup and exact source binding.
    Fresh slots require packets; reused/unavailable slots cannot dispatch. Capacity
    failures need an explicit bound deferral, never omission or replacement.
    """
    require(isinstance(scope, dict) and set(scope) == {"frame_sha256", "definition_version", "user_instruction_sha256"}, "scope_fields")
    sha(scope["frame_sha256"])
    sha(scope["user_instruction_sha256"])
    require(scope["definition_version"] == contract.DEFINITION_VERSION, "definition")
    sha(upstream_binding)
    require(isinstance(prefix, dict) and prefix.get("initial_manifest_sha256") == digest({k: v for k, v in prefix.items()
        if k != "initial_manifest_sha256"}), "prefix_digest")
    require(prefix.get("no_substitution") is True and prefix.get("dispatch_authorized") is False
        and prefix.get("fixed_look_weights_apply_to_this_prefix") is False, "prefix_policy")
    ranks = prefix["primary_ranks"]
    require(isinstance(ranks, list) and 1 <= len(ranks) <= 40 and len(ranks) == len(set(ranks)), "primary_limit")
    expected = [(r["pair_rank"], r["kind"]) for r in prefix["tasks"]]
    require(len(expected) == len(set(expected)) and all(type(r) is int and r >= 0 and role in ROLES for r, role in expected), "task_slots")
    require({r for r, role in expected if role == "primary"} == set(ranks)
        and all(r in ranks for r, _ in expected), "primary_task_frame")
    qc = {r for r, role in expected if role == "qc"}
    require({r for r, role in expected if role == "qc_adjudication"} == qc
        and {r for r, role in expected if role == "uncertain_adjudication"} == set(prefix["diagnostic_units"])
        and not qc & set(prefix["diagnostic_units"]) and len(prefix["diagnostic_units"]) <= 4, "conditional_slot_frame")
    require(prefix["qc_units"] == len(qc) and prefix["reserved_invocations"] == len(ranks) + 2 * len(qc) + 4
        and len(expected) + prefix["unused_diagnostic_identity_slots"] == prefix["reserved_invocations"] <= 60, "reserved_slot_limit")
    require(prefix.get("diagnostic_condition") == "clean_transport_and_available_provenance_and_epistemically_uncertain_primary"
        and prefix.get("qc_adjudication_condition") == "two_clean_provenance_available_valid_references_with_substantive_disagreement_or_epistemic_uncertainty",
        "conditional_policy_changed")
    require(isinstance(tasks, list) and [(t.get("pair_rank"), t.get("role")) for t in tasks] == expected
        and all(set(t) == set(TASK_FIELDS) for t in tasks), "fixed_task_order")
    validate_resources(resources)
    require(prefix["reserved_invocations"] <= resources["maximum_invocations"], "resource_invocation_limit")
    require(isinstance(cli_profile, dict) and set(cli_profile) == {"cli_binding", "tokenizer_identity"}, "cli_profile_fields")
    require_no_credentials(cli_profile)
    scope_id, prepared, sources, reused_physical = digest(scope), [], {}, {}
    for task in tasks:
        entry, packet, capacity = task["history"], task["packet"], task["capacity_unavailable"]
        history.validate_entry(entry)
        require(entry["role"] == task["role"], "history_role_binding")
        identity = sorted(entry["source_identity"], key=lambda row: row["document_id"])
        if packet is not None:
            contract.validate_packet(packet)
            require(packet["definition_version"] == scope["definition_version"], "task_definition")
            require(source_identity(packet) == identity, "history_packet_sources_changed")
        if capacity is not None:
            require(isinstance(capacity, dict) and set(capacity) == {"reason_code", "evidence_sha256"}
                and capacity["reason_code"] == "full_pair_capacity", "capacity_deferral_fields")
            sha(capacity["evidence_sha256"])
            require(entry["state"] == "fresh_unattempted" and packet is None, "capacity_deferral_scope")
        disposition = "fresh" if entry["state"] == "fresh_unattempted" and capacity is None else \
            "reused" if entry["state"] == "reused_resolved" else "unavailable"
        require(disposition != "fresh" or packet is not None, "fresh_packet_required")
        for physical in entry["physical_attempts"]:
            physical_key = digest(physical)
            require(physical_key not in reused_physical, "independent_roles_share_physical_judgment")
            reused_physical[physical_key] = task["role"]
        previous = sources.setdefault(task["pair_rank"], identity)
        require(identity == previous, "role_sources_changed")
        row = {**deepcopy(task), "logical_task_id": digest([METHOD, "logical-pair-role", scope_id, identity, task["role"]]),
            "request_sha256": packet["request_sha256"] if packet is not None else None,
            "source_identity_sha256": digest(identity), "disposition": disposition,
            "reservation_tokens": packet["input_tokens_proxy"] + resources["output_token_allowance"] if disposition == "fresh" else 0}
        prepared.append(row)
    require(len({t["logical_task_id"] for t in prepared}) == len(prepared), "duplicate_logical_task")
    reservation = sum(t["reservation_tokens"] for t in prepared)
    require(reservation <= resources["maximum_token_reservations"], "token_plan_over_limit")
    result = {"method": METHOD, "scope": deepcopy(scope), "scope_sha256": scope_id,
        "tranche": "initial_operational_prefix", "prefix": deepcopy(prefix), "upstream_binding": upstream_binding,
        "tasks": prepared, "cli_profile": deepcopy(cli_profile), "resources": deepcopy(resources),
        "planned_token_reservations": reservation, "planned_new_invocations": sum(t["disposition"] == "fresh" for t in prepared),
        "slot_catalog_sha256": digest(slot_catalog(prepared)), "implementation": implementation(),
        "generation_token_cap_enforced": False, "timeout_guarantees_remote_cancellation": False,
        "coordinator_invocations_not_remote_requests": True, "account_dollar_cost": None,
        "no_paid_api_fallback": True, "statistical_look": False}
    return {**result, "manifest_sha256": digest(result)}


def validate_manifest(value):
    require(isinstance(value, dict), "manifest_required")
    rebuilt = build_manifest(scope=value["scope"], prefix=value["prefix"],
        tasks=[{k: t[k] for k in TASK_FIELDS} for t in value["tasks"]],
        cli_profile=value["cli_profile"], resources=value["resources"], upstream_binding=value["upstream_binding"])
    require(value == rebuilt, "manifest_or_implementation_changed")
    return value


def rows(engine, session, kind):
    require_active(engine, session)
    return [{**engine.ledger.get(row[0], kind), "_record_id": row[0]} for row in
            engine.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]


def retain_manifest(engine, session, manifest, *, versions):
    """Call only after actual upstream registration; idempotent, never a reset."""
    require_active(engine, session)
    validate_manifest(manifest)
    require(isinstance(versions, dict) and {"protocol", "policy", "selection", "prompt", "dossier_definition"} <= set(versions), "registered_versions")
    for kind, identifier in versions.items():
        engine.ledger.get(identifier, kind)
    protocol = engine.ledger.get(versions["protocol"], "protocol")["content"]
    require(protocol.get("method") == METHOD
        and protocol.get("execution_manifest_sha256") == manifest["manifest_sha256"]
        and protocol.get("scope_sha256") == manifest["scope_sha256"]
        and protocol.get("implementation_sha256") == digest(manifest["implementation"]),
        "registered_execution_protocol_required")
    policy = engine.ledger.get(versions["policy"], "policy")["content"]
    require(policy.get("execution_manifest_sha256") == manifest["manifest_sha256"]
        and policy.get("allow_codex_account_execution") is True
        and policy.get("user_instruction_sha256") == manifest["scope"]["user_instruction_sha256"],
        "registered_account_policy_required")
    selection = engine.ledger.get(versions["selection"], "selection")["content"]
    require(selection.get("upstream_admission") == manifest["upstream_binding"]
        and selection.get("slot_catalog_sha256") == manifest["slot_catalog_sha256"], "registered_slot_selection_required")
    admission = engine.ledger.get(manifest["upstream_binding"], ADMISSION_KIND)
    require(admission.get("method") == METHOD and admission.get("scope_sha256") == manifest["scope_sha256"]
        and admission.get("prefix_sha256") == manifest["prefix"]["initial_manifest_sha256"]
        and admission.get("slot_catalog_sha256") == manifest["slot_catalog_sha256"], "upstream_slot_admission_binding")
    for name in ("source_snapshot", "history_inventory", "verification_protocol"):
        sha(admission.get(name))
        engine.ledger.get(admission[name])
    for task in manifest["tasks"]:
        if task["capacity_unavailable"] is not None:
            engine.ledger.artifacts.read(task["capacity_unavailable"]["evidence_sha256"])
    existing = rows(engine, session, MANIFEST_KIND)
    if existing:
        require(len(existing) == 1 and existing[0]["manifest"] == manifest and existing[0]["versions"] == versions,
                "existing_scope_or_tranche_cannot_change")
        return existing[0]["_record_id"]
    return engine.ledger.record(session, MANIFEST_KIND, manifest["scope_sha256"],
        {"manifest": manifest, "versions": versions, "at": utc()})


def slot_resolution(manifest_id, task):
    require(task["disposition"] != "fresh", "fresh_slot_not_locally_resolved")
    return {"manifest": manifest_id, "logical_task_id": task["logical_task_id"],
        "pair_rank": task["pair_rank"], "role": task["role"], "task_sha256": digest(task),
        "status": "technical_unavailable" if task["capacity_unavailable"] is not None else task["history"]["reference_status"],
        "positive": task["history"]["positive"] if task["disposition"] == "reused" else None,
        "disposition": task["disposition"], "history": task["history"],
        "capacity_unavailable": task["capacity_unavailable"],
        "new_model_calls": 0, "new_token_usage": 0, "new_remote_usage_observed": False}


def conditional_state(task, results):
    """Fixed branches; technical failure never triggers an adjudication retry."""
    rank, role = task["pair_rank"], task["role"]
    if role in {"primary", "qc"}:
        return "eligible"
    needed = ["primary", "qc"] if role == "qc_adjudication" else ["primary"]
    evidence = [results.get((rank, name)) for name in needed]
    if any(row is None for row in evidence):
        return "dependency_pending_or_unreturned"
    if any(row["status"] not in {"resolved", "epistemic_unknown"} for row in evidence):
        return "condition_false_technical_or_provenance_unavailable"
    if role == "uncertain_adjudication":
        return "eligible" if evidence[0]["status"] == "epistemic_unknown" else "condition_false"
    return "eligible" if any(row["status"] == "epistemic_unknown" for row in evidence) \
        or evidence[0]["positive"] != evidence[1]["positive"] else "condition_false"


def usage_units(usage):
    """Conservative reported-counter sum; reasoning may overlap output tokens.

    This is an admission accounting unit, not a billing calculation. Missing or
    malformed input/output counters are unavailable, never zero. All raw usage is
    retained separately; optional reasoning counts are added conservatively.
    """
    if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ("input_tokens", "output_tokens")):
        return None
    reasoning = usage.get("reasoning_output_tokens", 0)
    if type(reasoning) is not int or reasoning < 0:
        return None
    return usage["input_tokens"] + usage["output_tokens"] + reasoning


class Execution:
    """Sequential initial-tranche coordinator used by a registered parent handler."""

    def __init__(self, research, session, manifest_id, provider, *, now=None):
        require_active(research, session)
        require(isinstance(provider, transport.PairProvider) and provider.research is research and provider.session == session,
                "registered_pair_provider_required")
        self.engine, self.session, self.provider, self.manifest_id = research, session, provider, manifest_id
        saved = research.ledger.get(manifest_id, MANIFEST_KIND)
        self.manifest = validate_manifest(saved["manifest"])
        require(retain_manifest(research, session, self.manifest, versions=saved["versions"]) == manifest_id,
                "manifest_registration_changed")
        require({"cli_binding": provider.cli_binding, "tokenizer_identity": provider.tokenizer_identity} == self.manifest["cli_profile"],
                "provider_profile_changed")
        self.now = now or (lambda: datetime.now(timezone.utc))
        existing_slots = {row["logical_task_id"]: row for row in rows(research, session, SLOT_KIND)}
        for task in self.manifest["tasks"]:
            if task["disposition"] == "fresh":
                continue
            expected = slot_resolution(manifest_id, task)
            retained = existing_slots.get(task["logical_task_id"])
            if retained is None:
                research.ledger.record(session, SLOT_KIND, task["logical_task_id"], expected)
            else:
                require({k: v for k, v in retained.items() if k != "_record_id"} == expected, "retained_slot_resolution_changed")
        self.refresh()

    def refresh(self):
        require_active(self.engine, self.session)
        self.intents = rows(self.engine, self.session, INTENT_KIND)
        self.results = rows(self.engine, self.session, RESULT_KIND)
        self.slot_results = rows(self.engine, self.session, SLOT_KIND)
        self.halts = rows(self.engine, self.session, HALT_KIND)
        tasks = {t["logical_task_id"]: t for t in self.manifest["tasks"]}
        generic = [json.loads(row[0]) for row in self.engine.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq")]
        generic = [row for row in generic if row.get("validation_scope") == self.manifest["scope_sha256"]]
        require(len({row["attempt"] for row in generic}) == len(generic)
            and len({row["task_key"] for row in generic}) == len(generic), "duplicate_generic_attempt")
        generic_by_id = {row["attempt"]: row for row in generic}
        completed = [json.loads(row[0]) for row in self.engine.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='model.attempt.completed' ORDER BY seq")]
        completed = [row for row in completed if row["attempt"] in generic_by_id]
        require(len({row["attempt"] for row in completed}) == len(completed), "duplicate_completion")
        self.uncompleted_attempt_ids = set(generic_by_id) - {row["attempt"] for row in completed}
        seen, attempts = {}, {}
        for row in self.intents:
            require(generic_by_id.get(row["attempt"]) == {k: v for k, v in row.items() if k != "_record_id"},
                    "generic_intent_projection_mismatch")
            require(row["manifest"] == self.manifest_id and row["logical_task_id"] in tasks, "intent_scope")
            task = tasks[row["logical_task_id"]]
            require(task["disposition"] == "fresh", "nondispatchable_slot_has_attempt")
            require(row["task_key"] == row["logical_task_id"] and row["task_sha256"] == digest(task)
                and row["reservation_tokens"] == task["reservation_tokens"] and row["number"] == 1,
                "intent_task_binding")
            require(row["pair_rank"] == task["pair_rank"] and row["role"] == task["role"]
                and row["validation_scope"] == self.manifest["scope_sha256"], "intent_role_binding")
            require(row["logical_task_id"] not in seen and row["attempt"] not in attempts, "duplicate_durable_attempt")
            require(self.engine.ledger.artifacts.read(row["packet"]) == task["packet"]
                and self.engine.ledger.artifacts.read(row["request"]) == task["packet"]["request"], "intent_packet_binding")
            seen[row["logical_task_id"]], attempts[row["attempt"]] = row, row
        self.by_task = {}
        for row in self.results:
            intent = attempts.get(row["attempt"])
            require(intent is not None and row["manifest"] == self.manifest_id and row["logical_task_id"] == intent["logical_task_id"]
                and row["logical_task_id"] not in self.by_task, "result_attempt_binding")
            require(row["pair_rank"] == intent["pair_rank"] and row["role"] == intent["role"]
                and row["reservation_tokens"] == intent["reservation_tokens"], "result_role_binding")
            self.by_task[row["logical_task_id"]] = row
        result_attempts = {row["attempt"]: row for row in self.results}
        for row in completed:
            retained = result_attempts.get(row["attempt"])
            require(retained is not None and row["assessment"] == retained["_record_id"]
                and row["response"] == retained["response"] and not retained["unknown_outcome"],
                "completion_result_binding")
        # Inspect durable events, not only the mutable unresolved cache: a failed
        # append acknowledgement may leave an intent persisted before either the
        # in-memory assignment or custom projection happened, even this process.
        self.orphan_intents = [row for row in generic if row["attempt"] not in attempts]
        for row in self.orphan_intents:
            require(row["manifest"] == self.manifest_id and row["task_key"] in tasks
                and tasks[row["task_key"]]["disposition"] == "fresh"
                and row["task_sha256"] == digest(tasks[row["task_key"]]) and row["number"] == 1
                and row["reservation_tokens"] == tasks[row["task_key"]]["reservation_tokens"], "orphan_intent_binding")
        require(len({r["task_key"] for r in self.orphan_intents}) == len(self.orphan_intents)
            and not set(seen) & {r["task_key"] for r in self.orphan_intents}, "duplicate_orphan_attempt")
        require(all(r["manifest"] == self.manifest_id for r in self.halts), "halt_scope")
        expected_slots = {t["logical_task_id"]: slot_resolution(self.manifest_id, t)
            for t in self.manifest["tasks"] if t["disposition"] != "fresh"}
        require(len(self.slot_results) == len(expected_slots) and
            {r["logical_task_id"]: {k: v for k, v in r.items() if k != "_record_id"} for r in self.slot_results} == expected_slots,
            "slot_resolution_frame_changed")
        self.attempted = set(seen) | {r["task_key"] for r in self.orphan_intents}

    def normalized_results(self):
        """Local reuse is evidence, never a fabricated provider attempt/response."""
        base = {(r["pair_rank"], r["role"]): r for r in [*self.results, *self.slot_results]
            if r["role"] in {"primary", "qc"}}
        return {**base, **{(r["pair_rank"], r["role"]): r for r in [*self.results, *self.slot_results]
            if r["role"] not in {"primary", "qc"} and conditional_state(r, base) == "eligible"}}

    def reference_observations(self):
        """Projection consumed by the fixed-look helper, without prefix inference."""
        result = []
        for row in self.normalized_results().values():
            incomplete = row.get("attempt") in self.uncompleted_attempt_ids
            result.append({"pair_rank": row["pair_rank"], "role": row["role"], "record_id": row["_record_id"],
                "status": "technical_unavailable" if incomplete else row["status"],
                "positive": None if incomplete else row["positive"]})
        return sorted(result, key=lambda r: (r["pair_rank"], r["role"]))

    def accounting(self):
        result = {r["attempt"]: r for r in self.results}
        intents = [*self.intents, *self.orphan_intents]
        return {"coordinator_invocations": len(intents),
            "reservation_tokens": sum(r["reservation_tokens"] for r in intents),
            "committed_token_units": sum(max(r["reservation_tokens"], (result.get(r["attempt"], {}).get("observed_token_units") or 0)) for r in intents),
            "observed_token_units": sum(r["observed_token_units"] for r in self.results if r["observed_token_units"] is not None),
            "usage_unavailable_attempts": sum(r["attempt"] not in result or result[r["attempt"]]["observed_token_units"] is None for r in intents),
            "unreturned_attempts": sum(r["attempt"] not in result for r in intents),
            "durably_uncompleted_intents": len(self.uncompleted_attempt_ids)}

    def blocker(self):
        self.refresh()
        if self.halts:
            return "retained_terminal_halt:" + self.halts[0]["reason"]
        # A process may exit after its result record but before its separate halt
        # record; the immutable result's terminal reason must survive that gap.
        terminal = next((row["terminal_reason"] for row in self.results if row["terminal_reason"]), None)
        if terminal:
            return "retained_terminal_result:" + terminal
        if self.accounting()["unreturned_attempts"]:
            return "unreturned_intent_unknown_outcome"
        if self.uncompleted_attempt_ids:
            return "durable_completion_missing"
        if (self.engine.ledger.root / "STOP").exists():
            return "user_stop"
        current, resources = self.now(), self.manifest["resources"]
        if current < timestamp(resources["not_before"]):
            return "admission_not_started"
        if current >= timestamp(resources["admit_before"]):
            return "admission_deadline"
        quota = resources["quota"]
        if current < timestamp(quota["observed_at"]) or current >= timestamp(quota["valid_until"]):
            return "quota_observation_stale"
        if quota["state"] == "unavailable":
            if resources["unavailable_quota_policy"] == "block":
                return "quota_unavailable_policy_blocks"
        elif (quota["remaining_invocations"] < self.manifest["planned_new_invocations"]
              or quota["remaining_tokens"] < self.manifest["planned_token_reservations"]):
            return "known_quota_insufficient_for_frozen_tranche"
        return None

    def halt(self, reason, result_id):
        self.engine.ledger.record(self.session, HALT_KIND, digest([self.manifest_id, result_id, reason]),
            {"manifest": self.manifest_id, "reason": reason, "result": result_id, "at": utc()})

    def run(self, *, allow_account_execution=False):
        require(allow_account_execution is True, "explicit_account_execution_required")
        stop = self.blocker()
        for task in self.manifest["tasks"]:
            if stop:
                break
            if task["disposition"] != "fresh" or task["logical_task_id"] in self.attempted:
                continue
            normalized = self.normalized_results()
            if conditional_state(task, normalized) != "eligible":
                continue
            stop = self.blocker()
            if stop:
                break
            count = self.accounting()
            resources = self.manifest["resources"]
            if (count["coordinator_invocations"] + 1 > resources["maximum_invocations"]
                    or count["committed_token_units"] + task["reservation_tokens"] > resources["maximum_token_reservations"]):
                stop = "registered_task_or_token_limit"
                break
            invocation = self.provider.prepare(task["packet"])
            # Preparation does not consume a slot. Recheck time/STOP before intent.
            stop = self.blocker()
            if stop:
                break
            attempt = str(uuid.uuid4())
            ledger = self.engine.ledger
            intended = {"attempt": attempt, "task_key": task["logical_task_id"], "logical_task_id": task["logical_task_id"],
                "validation_scope": self.manifest["scope_sha256"], "manifest": self.manifest_id, "batch": self.manifest_id,
                "task_sha256": digest(task), "number": 1, "pair_rank": task["pair_rank"], "role": task["role"],
                "reservation_tokens": task["reservation_tokens"], "packet": ledger.artifacts.put(task["packet"]),
                "request": ledger.artifacts.put(invocation.request), "dispatch": ledger.artifacts.put(invocation.manifest()),
                "started_at": utc()}
            ledger.append(self.session, "model.attempt.intended", intended)
            ledger.unresolved[attempt] = intended
            ledger.record(self.session, INTENT_KIND, task["logical_task_id"], intended)
            _, response = next(self.engine.gateway.codex_dispatch(self.session, self.provider, [(invocation, attempt)], 1))
            response_ref = ledger.artifacts.put(asdict(response))
            raw = response.raw_response or {}
            parsed, error, status, positive = None, None, "technical_unavailable", None
            fatal_parse = False
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
                    # Only known output-content validation failures are ordinary
                    # missing references. Identity/provenance/runtime safeguards
                    # and unexpected parser exceptions halt the initial tranche.
                    fatal_parse = isinstance(caught, AuditError) or code not in ITEM_CONTENT_ERRORS
            units = usage_units(response.usage)
            unknown = bool(raw.get("unknown_outcome"))
            if unknown:
                status, positive = "technical_unavailable", None
            overrun = units is not None and (units > task["reservation_tokens"]
                or response.usage["output_tokens"] > resources["output_token_allowance"])
            reason = ("token_allowance_exceeded" if overrun else "unknown_outcome" if unknown else
                "usage_unavailable" if units is None else "transport_unavailable" if response.payload is None else
                "reference_identity_or_adapter_failure" if fatal_parse else
                "reference_provenance_unavailable" if status == "provenance_unavailable" else None)
            result = {"manifest": self.manifest_id, "logical_task_id": task["logical_task_id"], "attempt": attempt,
                "pair_rank": task["pair_rank"], "role": task["role"], "status": status, "positive": positive,
                "response": response_ref, "parsed": ledger.artifacts.put(parsed) if parsed is not None else None,
                "validation_error": error, "unknown_outcome": unknown, "observed_token_units": units,
                "reservation_tokens": task["reservation_tokens"], "token_allowance_exceeded": overrun,
                "terminal_reason": reason, "at": utc()}
            result_id = ledger.record(self.session, RESULT_KIND, task["logical_task_id"], result)
            if not unknown:
                def project(event):
                    ledger.db.execute("INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?,?)", (attempt, task["logical_task_id"],
                        self.manifest_id, 1, intended["request"], response_ref, status, result_id, error, event))
                ledger.append(self.session, "model.attempt.completed", {"attempt": attempt, "response": response_ref,
                    "assessment": result_id, "status": status, "ended_at": utc()}, project)
                ledger.unresolved.pop(attempt)
            if reason:
                self.halt(reason, result_id)
            self.refresh()
            stop = self.blocker()
        return self.report(stop or "fixed_tranche_processed")

    def report(self, stop_reason):
        self.refresh()
        normalized = self.normalized_results()
        slot_by_task = {r["logical_task_id"]: r for r in self.slot_results}
        states = Counter()
        dispositions = Counter()
        for task in self.manifest["tasks"]:
            key = task["logical_task_id"]
            dispositions[task["disposition"]] += 1
            if key in self.by_task:
                states[self.by_task[key]["status"]] += 1
            elif key in self.attempted:
                states["unreturned_unknown"] += 1
            else:
                condition = conditional_state(task, normalized)
                states[slot_by_task[key]["status"] if condition == "eligible" and key in slot_by_task
                    else "not_attempted" if condition == "eligible" else condition] += 1
        result = {"manifest": self.manifest_id, "scope_sha256": self.manifest["scope_sha256"], "at": utc(),
            "stop_reason": stop_reason, "selected_primary_units": len(self.manifest["prefix"]["primary_ranks"]),
            "fixed_task_slots": len(self.manifest["tasks"]), "reserved_invocation_slots": self.manifest["prefix"]["reserved_invocations"],
            "states": dict(states), "slot_dispositions": dict(dispositions),
            "local_slot_resolution_records": len(self.slot_results),
            "reference_observations_artifact": self.engine.ledger.artifacts.put(self.reference_observations()),
            "new_invocations_planned": self.manifest["planned_new_invocations"],
            **self.accounting(), "generation_token_cap_enforced": False,
            "token_units_include_reported_reasoning_conservatively": True, "quota_state": self.manifest["resources"]["quota"]["state"],
            "account_quota_is_shared_and_may_change": True, "account_dollar_cost": None,
            "no_paid_api_fallback": True, "coordinator_invocations_not_remote_requests": True,
            "statistical_look": False, "reference_gold": False}
        identifier = self.engine.ledger.record(self.session, REPORT_KIND, digest(result), result)
        return {"id": identifier, **result}
