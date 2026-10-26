"""Full-source fixed-slot construction for initial and later operational tranches.

Pure retained-evidence transformation: no owner, registration, CLI or dispatch.
The concrete audited parent must replay frame/closure/seed provenance and prove
that the closure covers the SAME legacy history universe. A digest or this
structural wrapper does not prove that authority. The legacy certificate remains
unchanged; the separately bound derived inventory expresses only the verified
scope, including every unresolved region and conservative batch endpoints.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

import final_validation_contract as contract
import final_validation_execution as execution
import final_validation_execution_v2 as kernel
import final_validation_history as history
import final_validation_packets as original
import final_validation_schedule as schedules
from final_validation_design import pair_from_rank
from newsresearch.common import ResearchError, canonical, digest

METHOD = "final-validation-fixed-full-source-slots-v1"
BINDINGS = {"final_frame_record", "closure_record", "closure_projection_sha256", "source_snapshot_record",
    "source_snapshot_artifact", "history_verification_record", "legacy_records_sha256", "legacy_inventory_sha256",
    "order_seed_record", "order_seed_artifact", "tokenizer_evidence_record", "parent_verification_protocol"}
PROJECTION_FIELDS = {"input_index_digest", "pair_role_blockers", "unresolved_regions", "owner_partitions",
    "physical_tasks", "prepared_only", "resolved_task_purpose_gaps", "root_dispositions", "scoped_certificate", "counts"}


def require(value, reason):
    if not value:
        raise ResearchError("fixed_slots_" + reason)


def _bytes(value):
    return canonical(value).encode()


def _hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def implementation():
    path = Path(__file__).resolve()
    return {**original.implementation(), **kernel.implementation(),
        path.relative_to(path.parents[3]).as_posix(): _hash_bytes(path.read_bytes())}


@dataclass(frozen=True)
class BoundClosureEvidence:
    """Immutable structural input, NOT an attestation or completeness permission.

    Only the audited parent can establish that these exact bytes came from the
    concrete completed closure and its required full source/registry proofs.
    """
    projection_json: bytes
    digest: str

    @property
    def projection(self):
        return json.loads(self.projection_json)


def bind_closure_projection(projection):
    """Freeze supplied bytes; parent provenance remains explicitly unverified."""
    return BoundClosureEvidence(_bytes(projection), digest(projection))


def _projection(evidence, index, bindings):
    require(type(evidence) is BoundClosureEvidence, "bound_closure_required")
    value = evidence.projection
    require(type(evidence.projection_json) is bytes and evidence.projection_json == _bytes(value)
        and evidence.digest == digest(value) == bindings["closure_projection_sha256"], "closure_bytes_binding")
    require(isinstance(value, dict) and set(value) == PROJECTION_FIELDS, "closure_fields")
    require(value["input_index_digest"] == index.digest, "closure_index")
    known = {r.input_sha256 for r in index.inputs}
    cert = value["scoped_certificate"]
    require(isinstance(cert, dict) and set(cert) == {"complete", "global_gap", "unknown_input_sha256",
        "covered_universe", "source_heads", "historical_replay_only", "universal_completeness"}, "closure_certificate_fields")
    require(cert["covered_universe"] == "fixed_catalog_roots_and_retained_owner_heads_only"
        and cert["historical_replay_only"] is True and cert["universal_completeness"] is False, "closure_scope")
    require(isinstance(value["owner_partitions"], dict) and isinstance(value["physical_tasks"], dict), "closure_partitions")
    require(canonical(cert["source_heads"]) == canonical({k: p["source_head"] for k, p in value["owner_partitions"].items()}),
        "closure_head_partition")
    regions = value["unresolved_regions"]
    require(isinstance(regions, list), "closure_regions")
    for row in regions:
        require(isinstance(row, dict) and set(row) == {"reason_code", "owner_sha256", "evidence_sha256",
            "affected_input_sha256", "role"}, "closure_region_fields")
        require(isinstance(row["reason_code"], str) and bool(row["reason_code"]), "closure_region_reason")
        history.sha(row["evidence_sha256"])
        if row["owner_sha256"] is not None:
            history.sha(row["owner_sha256"])
        affected = row["affected_input_sha256"]
        require(affected is None or (isinstance(affected, list) and bool(affected)
            and affected == sorted(set(affected)) and set(affected) <= known), "closure_region_bounds")
        require(row["role"] is None or row["role"] in history.ROLES, "closure_region_role")
    unknown = sorted({h for r in regions for h in (r["affected_input_sha256"] or [])})
    expected = {"complete": not regions, "global_gap": any(r["affected_input_sha256"] is None for r in regions),
        "unknown_input_sha256": unknown}
    require(all(canonical(cert[k]) == canonical(v) for k, v in expected.items()), "closure_gap_consistency")
    require(isinstance(value["pair_role_blockers"], list), "closure_blockers")
    seen = set()
    for row in value["pair_role_blockers"]:
        require(isinstance(row, dict) and set(row) == {"pair_key", "input_sha256", "role", "references"}, "closure_blocker_fields")
        inputs = row["input_sha256"]
        require(isinstance(inputs, list) and len(inputs) == 2 and inputs == sorted(set(inputs))
            and set(inputs) <= known and row["role"] in history.ROLES, "closure_blocker_sources")
        require(row["pair_key"] == digest({"input_sha256": inputs, "role": row["role"]})
            and row["pair_key"] not in seen, "closure_blocker_identity")
        seen.add(row["pair_key"])
        require(isinstance(row["references"], list) and bool(row["references"])
            and all(isinstance(r, dict) and r for r in row["references"]), "closure_blocker_evidence")
    # An unresolved declared root must never disappear by changing only flags.
    unresolved = [r for r in value["root_dispositions"] if r["status"] != "resolved_exact_retained_owner"]
    require(not unresolved or any(r["reason_code"] == "unresolved_catalog_root"
        and r["affected_input_sha256"] is None for r in regions), "unresolved_root_missing_gap")
    return value


def _history_envelope(projection, legacy_records, legacy_inventory, bindings, frame):
    history.validate_inventory(legacy_inventory)
    history.normalize_records(legacy_records)
    require(digest(legacy_records) == bindings["legacy_records_sha256"]
        and digest(legacy_inventory) == bindings["legacy_inventory_sha256"], "legacy_history_binding")
    # No physical batch is split into invented one-pair historical judgments.
    # Conservatively exclude all pairs touching its known endpoints in all roles.
    batch_rows = [r for r in projection["pair_role_blockers"]
        if any("logical_slot_id" in ref for ref in r["references"])]
    batch_endpoints = sorted({h for r in batch_rows for h in r["input_sha256"]})
    cert = projection["scoped_certificate"]
    envelope = {"method": METHOD, "input_index_digest": frame.index.digest, "frame_digest": frame.digest,
        "binding": {k: bindings[k] for k in sorted(BINDINGS - {"tokenizer_evidence_record"})},
        "legacy_inventory": legacy_inventory, "legacy_records_sha256": digest(legacy_records),
        "closure_projection_sha256": digest(projection), "covered_universe": cert["covered_universe"],
        "source_heads": cert["source_heads"], "historical_replay_only": True,
        "batch_endpoint_exclusion_sha256": batch_endpoints,
        "legacy_placeholder_supersession_requires_concrete_parent_replay": True,
        "universal_history_complete": False, "creates_reference_labels": False}
    inventory = {"binding_sha256": digest(envelope), "complete": not projection["unresolved_regions"] and not batch_endpoints,
        "global_gap": cert["global_gap"],
        "unknown_input_sha256": sorted(set(cert["unknown_input_sha256"]) | set(batch_endpoints))}
    history.validate_inventory(inventory)
    return envelope, inventory


def _entry(identity, role, records, inventory, projection):
    entry = history.resolve_history(identity, role, records, inventory)
    key = digest({"input_sha256": sorted(r["input_sha256"] for r in identity), "role": role})
    matched = [r for r in projection["pair_role_blockers"] if r["pair_key"] == key]
    if matched:
        # Retain ordinary physical identities if present; closure/batch links live
        # in the external map. They cannot supply Y or trigger a replacement.
        entry.update(state="prior_attempt_unavailable", positive=None, reference_status="technical_unavailable",
            diagnostic_eligible=False, reason_codes=sorted((set(entry["reason_codes"]) - {"no_recorded_pair_role_attempt"})
                | {"scoped_pair_role_attempt_blocker"}))
        entry["entry_sha256"] = digest({k: v for k, v in entry.items() if k != "entry_sha256"})
    return history.validate_entry(entry)


def _slots(schedule, selection):
    require(isinstance(selection, dict), "selection")
    if selection == {"kind": "initial"}:
        prefix = schedule.manifest["initial_prefix"]
        return prefix["tasks"], prefix["primary_ranks"], prefix["reserved_invocations"], prefix
    require(set(selection) == {"kind", "plan", "ceilings", "primary_limit"}
        and selection["kind"] == "later", "selection_fields")
    plan = selection["plan"]
    require(isinstance(plan, dict) and set(plan) == {"look", "start", "stop", "primary_ranks", "slots",
        "diagnostic_identities_added", "statistical_look", "previous_manifest", "prior_census_sha256"}, "later_plan_fields")
    for key in ("previous_manifest", "prior_census_sha256"):
        history.sha(plan[key])
    require(type(plan["start"]) is int and plan["start"] >= len(schedule.manifest["initial_prefix"]["primary_ranks"]),
        "later_cannot_replace_initial")
    expected = kernel.bounded_segment(schedule, start=plan["start"], ceilings=selection["ceilings"],
        primary_limit=selection["primary_limit"])
    require(canonical({k: plan[k] for k in expected}) == canonical(expected), "later_contiguous_schedule")
    return [{"pair_rank": r, "kind": role} for r, role in expected["slots"]], expected["primary_ranks"], len(expected["slots"]), None


@dataclass(frozen=True)
class PreparedFixedSlots:
    payload_json: bytes
    artifacts: object = field(repr=False)
    digest: str

    @property
    def payload(self):
        return json.loads(self.payload_json)

    @property
    def tasks(self):
        return self.payload["tasks"]

    @property
    def catalog(self):
        return self.payload["slot_catalog"]

    @property
    def resources(self):
        return self.payload["resources"]

    def build_execution_manifest(self, admission_record):
        history.sha(admission_record)
        value = self.payload
        require(self.payload_json == _bytes(value) and self.digest == digest(value), "preparation_digest")
        require(value["implementation"] == implementation(), "implementation_changed")
        require(set(self.artifacts) == set(value["artifact_sha256"])
            and all(_hash_bytes(raw) == ref for ref, raw in self.artifacts.items()), "artifact_binding")
        require(value["selection"] == {"kind": "initial"}, "later_uses_registered_series")
        result = execution.build_manifest(scope=value["execution_scope"], prefix=value["initial_prefix"],
            tasks=value["tasks"], cli_profile=value["cli_profile"], resources=value["resources"], upstream_binding=admission_record)
        require(result["slot_catalog_sha256"] == value["slot_catalog_sha256"]
            and result["planned_token_reservations"] == value["resource_census"]["planned_token_reservations"], "execution_projection")
        return result


def prepare_fixed_slots(frame, schedule, documents, *, selection, legacy_records, legacy_inventory,
                        closure_evidence, order_seed, bindings, token_counter, cli_profile, resources,
                        user_instruction_sha256, max_input_tokens=contract.MAX_INPUT_TOKENS):
    """Build exact original TASK_FIELDS. Later plan authority is parent/kernel-only.

    Every immutable record in bindings must be replayed by the audited parent;
    this function checks bytes and algorithms, never record existence or truth.
    Closure replaces only legacy purpose/discovery placeholders proved covered
    by that parent's SAME-universe replay. It does not erase inherited history.
    """
    docs = original._documents(frame, documents)
    schedules.verify_schedule(frame, schedule)
    require(isinstance(bindings, dict) and set(bindings) == BINDINGS, "binding_fields")
    for value in bindings.values():
        history.sha(value)
    history.sha(user_instruction_sha256)
    projection = _projection(closure_evidence, frame.index, bindings)
    envelope, inventory = _history_envelope(projection, legacy_records, legacy_inventory, bindings, frame)
    require(type(token_counter) is original.TokenCounter, "bound_token_counter_required")
    tokenizer_configuration = token_counter.validate()
    require(token_counter.evidence_record == bindings["tokenizer_evidence_record"], "tokenizer_evidence_binding")
    require(isinstance(cli_profile, dict) and set(cli_profile) == {"cli_binding", "tokenizer_identity"}
        and cli_profile["tokenizer_identity"] == token_counter.identity, "provider_tokenizer_binding")
    require(digest(original.order_seed_payload(order_seed)) == bindings["order_seed_artifact"], "order_seed_binding")
    execution.validate_resources(resources)
    require(type(max_input_tokens) is int and 1 <= max_input_tokens <= contract.MAX_INPUT_TOKENS, "input_capacity_policy")
    selected_slots, primary_ranks, reserved, prefix = _slots(schedule, selection)
    require(reserved <= resources["maximum_invocations"], "resource_invocation_limit")
    tasks, catalog, details, artifacts, used_physical = [], [], [], {}, set()
    reservation, fresh = 0, 0

    def retain(raw):
        reference = _hash_bytes(raw)
        previous = artifacts.setdefault(reference, raw)
        require(previous == raw, "artifact_collision")
        return reference

    for slot in selected_slots:
        rank, role = slot["pair_rank"], slot["kind"]
        left, right = pair_from_rank(len(frame.index.inputs), rank)
        selected = [docs[left], docs[right]]
        identity = original._identity(selected)
        entry = _entry(identity, role, legacy_records, inventory, projection)
        for attempt in entry["physical_attempts"]:
            key = (attempt["owner_sha256"], attempt["attempt_id"])
            require(key not in used_physical, "independent_slots_share_physical_judgment")
            used_physical.add(key)
        order = original._article_order(frame.digest, rank, role, selected, order_seed)
        packet, capacity, observed = None, None, []
        if entry["state"] == "fresh_unattempted":
            def measure(text):
                tokens = token_counter.count(text)
                observed.append((text, tokens))
                return tokens
            try:
                packet = contract.request(selected, order=order, count_tokens=measure, max_input_tokens=max_input_tokens)
            except ResearchError as error:
                if str(error) != "final_pair_packet_capacity":
                    raise
                require(len(observed) == 1, "capacity_measurement_missing")
                stdin, tokens = observed[0]
                proof = {"method": METHOD, "reason_code": "full_pair_capacity", "pair_rank": rank, "role": role,
                    "source_identity": identity, "document_order": order, "definition_version": contract.DEFINITION_VERSION,
                    "stdin_artifact": retain(stdin.encode()), "input_tokens_proxy": tokens,
                    "input_bytes": len(stdin.encode()), "max_input_tokens": max_input_tokens,
                    "max_input_bytes": contract.MAX_INPUT_BYTES, "tokenizer_identity": token_counter.identity,
                    "tokenizer_evidence_record": token_counter.evidence_record, "new_model_calls": 0,
                    "provider_attempted": False, "no_truncation": True}
                require(tokens > max_input_tokens or proof["input_bytes"] > contract.MAX_INPUT_BYTES,
                        "capacity_failure_without_excess")
                capacity = {"reason_code": "full_pair_capacity", "evidence_sha256": retain(_bytes(proof))}
            if packet is not None:
                contract.validate_for_dispatch(packet, count_tokens=token_counter.count)
                require(execution.source_identity(packet) == identity, "packet_source_substitution")
                retain(_bytes(packet))
                fresh += 1
                reservation += packet["input_tokens_proxy"] + resources["output_token_allowance"]
        disposition = "fresh" if packet is not None else "reused" if entry["state"] == "reused_resolved" else "unavailable"
        task = {"pair_rank": rank, "role": role, "packet": packet, "history": entry, "capacity_unavailable": capacity}
        tasks.append(task)
        catalog.append({"pair_rank": rank, "role": role, "source_identity_sha256": digest(identity),
            "history_entry_sha256": entry["entry_sha256"], "capacity_unavailable": capacity,
            "disposition": disposition, "request_sha256": packet["request_sha256"] if packet else None})
        details.append({"pair_rank": rank, "role": role, "indexed_positions": [left, right],
            "source_identity": identity, "frozen_article_order": order, "disposition": disposition,
            "packet_artifact": digest(packet) if packet else None,
            "packet_bytes": len(_bytes(packet)) if packet else None,
            "request_bytes": len(_bytes(packet["request"])) if packet else None,
            "stdin_bytes": packet["input_bytes"] if packet else (len(observed[0][0].encode()) if observed else None),
            "input_tokens_proxy": packet["input_tokens_proxy"] if packet else (observed[0][1] if observed else None),
            "output_token_allowance": resources["output_token_allowance"] if packet else 0,
            "reservation_tokens": packet["input_tokens_proxy"] + resources["output_token_allowance"] if packet else 0,
            "capacity_evidence": capacity["evidence_sha256"] if capacity else None})
    require(reservation <= resources["maximum_token_reservations"], "resource_token_limit")
    counts = Counter(item["disposition"] for item in catalog)
    physical_maps = retain(_bytes({"physical_tasks": projection["physical_tasks"],
        "pair_role_blockers": projection["pair_role_blockers"]}))
    value = {"method": METHOD, "implementation": implementation(), "bindings": bindings, "history_envelope": envelope, "history_envelope_sha256": digest(envelope),
        "derived_history_inventory": inventory, "inherited_history_inventory_unchanged": True,
        "input_index_digest": frame.index.digest, "frame_digest": frame.digest, "schedule_digest": schedule.digest,
        "initial_prefix": prefix, "selection": selection, "tasks": tasks, "slot_catalog": catalog, "slot_catalog_sha256": digest(catalog),
        "slot_resource_details": details, "cli_profile": cli_profile, "resources": resources,
        "execution_scope": {"frame_sha256": frame.digest, "definition_version": contract.DEFINITION_VERSION,
            "user_instruction_sha256": user_instruction_sha256},
        "order_policy": original.ORDER_POLICY, "order_seed_binding": {"record": bindings["order_seed_record"],
            "artifact": bindings["order_seed_artifact"]},
        "tokenizer_binding": {"identity": token_counter.identity, "evidence_record": token_counter.evidence_record,
            "vocabulary_sha256": original.VOCAB_HASH, "configuration_sha256": tokenizer_configuration,
            "counter": "len(cl100k_base.encode(exact_stdin,disallowed_special=()))"},
        "resource_census": {"selected_primary_pairs": len(primary_ranks), "selected_slots": len(tasks),
            "reserved_schedule_invocations": reserved, "fresh_potential_invocations": fresh,
            "reused_slots": counts["reused"], "unavailable_slots": counts["unavailable"],
            "capacity_deferred_slots": sum(t["capacity_unavailable"] is not None for t in tasks),
            "planned_token_reservations": reservation, "generation_token_cap_enforced": False,
            "coordinator_invocations_not_remote_requests": True, "account_dollar_cost": None},
        "artifact_sha256": sorted(artifacts), "no_substitution": True, "new_model_calls": 0, "dispatch_authorized": False,
        "source_history_seed_and_authority_provenance_verified": False,
        "physical_reference_maps_artifact": physical_maps,
        "limitations": "Parent verifies exact source/frame/history/seed/tokenizer evidence records, pre-label timing and authority, retains protected artifacts, registers admission, then uses Research.execute/shared gateway. Counts are exact local stdin proxies/reservations, not actual CLI usage or enforced remote generation caps. Reused/unavailable slots create no new invocation. Operational tranches are not statistical looks. The parent must verify the scoped closure covers the exact inherited history universe before superseding its placeholder certificate; structural hashes are not authority."}
    return PreparedFixedSlots(_bytes(value), MappingProxyType(artifacts), digest(value))
