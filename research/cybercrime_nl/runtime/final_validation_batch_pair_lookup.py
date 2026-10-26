"""Exact pair blockers from completed, audited historical batch adapters.

One physical batch may contain many logical slots. This child preserves that
identity and imports no labels. It never clears the inherited whole-history gap
or changes the original single-pair history/packet helpers. Pure compilation is
software only; the public child requires actual completed parent-ledger proofs.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_history as history
import final_validation_matching_history as matching
import final_validation_representation_history as representation
from newsresearch.common import AuditError, digest, require_active

METHOD = "final-validation-batch-pair-lookup-v1"
RESULT = "cyber_final_validation_batch_pair_lookup"
POLICY = {"creates_pair_y": False, "dispatch_authorized": False,
    "whole_history_complete": False, "inherited_no_retry_certificate_unchanged": True,
    "source_mutations": 0, "new_model_calls": 0, "new_seed_draws": 0,
    "original_packet_history_api_changed": False, "current_source_quiescence_verified": False}


def require(value, reason):
    if not value:
        raise AuditError("batch_pair_lookup_" + reason)


def implementation():
    path = Path(__file__).resolve()
    return {**representation.implementation(), **matching.implementation(),
        path.relative_to(path.parents[3]).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def pair_key(inputs, role):
    require(role in history.ROLES and isinstance(inputs, list) and len(inputs) == 2
        and len(set(inputs)) == 2, "pair_identity")
    for value in inputs:
        history.sha(value)
    return digest({"input_sha256": sorted(inputs), "role": role})


def _compile(sources, index):
    """Pure compiler for exact parent-retained adapter artifacts, not admission."""
    known = {item.input_sha256 for item in index.inputs}
    require(len(known) == len(index.inputs), "input_index_aliases")
    blockers, regions, excluded, slots, batches, unverified = {}, {}, {}, {}, set(), set()
    endpoint_versions, physical_contracts, view_count = {}, {}, 0

    def region(source_id, reason, inputs, evidence):
        require(inputs is None or isinstance(inputs, list), "region_scope")
        if inputs is not None:
            require(set(inputs) <= known, "region_outside_frame")
        value = {"source_id": source_id, "reason_code": reason,
            "affected_input_sha256": sorted(set(inputs)) if inputs else None,
            "evidence_sha256": digest(evidence), "role": "primary"}
        regions[digest(value)] = value

    for source in sources:
        manifest, bindings = source["manifest"], source["bindings"]
        source_id = manifest["source_id"]
        history.sha(source_id)
        adapters = {(representation.VERSION, representation.FAMILY): representation,
            (matching.VERSION, matching.FAMILY): matching}
        adapter = adapters.get((manifest.get("version"), manifest.get("family")))
        require(adapter is not None, "unsupported_adapter_family")
        is_matching = adapter is matching
        require(manifest["implementation"] == adapter.implementation()
            and manifest["role_policy"] == adapter.ROLE_POLICY
            and manifest["input_index_digest"] == index.digest
            and manifest["pair_attempt_bindings_sha256"] == digest(bindings)
            and manifest["logical_pair_bindings"] == len(bindings), "adapter_binding")
        declared = {}
        for batch in manifest["reference_batches"]:
            key = (batch["original_attempt"], None if is_matching else batch["plan_record"])
            require(key not in declared, "duplicate_declared_batch")
            declared[key] = batch
        observed = {key: set() for key in declared}
        gap_slots, seen_bindings = set(), set()
        for row in bindings:
            view_count += 1
            slot = row["logical_slot"]
            key = (row["original_attempt"], None if is_matching else slot["plan_record"])
            require(key in declared and row["logical_slot_id"] == digest(slot)
                and row["role_policy"] == adapter.ROLE_POLICY
                and row["current_reference_compatible"] is False and row["creates_pair_y"] is False,
                "logical_slot_binding")
            if is_matching:
                require(set(slot) == {"request_artifact", "number", "pair_id"}
                    and type(slot["number"]) is int and 1 <= slot["number"] <= 24
                    and slot["request_artifact"] == row["request_artifact"]
                    and row.get("evidence_scope") == "card_fields", "matching_logical_slot")
                history.sha(slot["pair_id"])
                history.sha(row["parent_plan"])
                history.sha(row["parent_pair_request"])
            local = (key, row["logical_slot_id"])
            require(local not in seen_bindings, "duplicate_slot_in_view")
            seen_bindings.add(local)
            observed[key].add(row["logical_slot_id"])
            batch = declared[key]
            expected_origin = batch["physical_id"] is not None if is_matching else batch["origin_verified"]
            require(type(row["origin_verified"]) is bool and row["origin_verified"] == expected_origin
                and row["physical_id"] == batch["physical_id"], "batch_origin_binding")
            if row["origin_verified"]:
                history.sha(row["original_owner_source_id"])
                require(row["physical_id"] == digest([row["original_owner_source_id"], row["original_attempt"]]),
                    "original_physical_identity")
                physical = row["physical_id"]
                batches.add(physical)
                physical_scope = {"physical_id": physical, "unverified_source_view": None}
                dedup = ("original", physical, row["logical_slot_id"])
            else:
                require(row["physical_id"] is None and row["original_owner_source_id"] is None,
                    "unverified_origin_cannot_be_physical")
                view = digest([source_id, row["original_attempt"]])
                unverified.add(view)
                physical_scope = {"physical_id": None, "unverified_source_view": view}
                dedup = ("unverified", view, row["logical_slot_id"])
            # A physical attempt is not a new attempt merely because a second
            # family or view describes it. Incompatible producer/wire bindings
            # are corruption, not another independent reference.
            physical_key = (dedup[0], dedup[1])
            physical_contract = digest({"family": adapter.FAMILY, "version": adapter.VERSION,
                "request_artifact": row["request_artifact"], "dispatch_artifact": row["dispatch_artifact"]})
            require(physical_contracts.setdefault(physical_key, physical_contract) == physical_contract,
                "conflicting_physical_batch_contract")
            identities = row["source_identities"]
            require(isinstance(identities, list) and len(identities) == 2, "two_logical_endpoints")
            for identity in identities:
                if identity is None:
                    continue
                flag = "full_retained_source_identity_proven" if is_matching else "full_retained_source_proven"
                require(identity.get(flag) is True, "full_source_provenance")
                for field in ("input_sha256", "title_sha256", "body_sha256"):
                    history.sha(identity[field])
                signature = (identity["title_sha256"], identity["body_sha256"])
                previous = endpoint_versions.setdefault(identity["input_sha256"], signature)
                require(signature == previous, "conflicting_full_input_identity")
            matched = sorted({x["input_sha256"] for x in identities if x and x["input_sha256"] in known})
            require(row["matched_input_sha256"] == matched, "current_endpoint_mapping")
            comparable = {k: row[k] for k in ("logical_slot", "original_attempt", "original_owner_source_id",
                "physical_id", "source_identities", "request_artifact", "dispatch_artifact", "role_policy")}
            if is_matching:
                comparable.update({k: row[k] for k in ("parent_plan", "parent_pair_request", "evidence_scope")})
            signature = digest(comparable)
            require(slots.setdefault(dedup, signature) == signature, "conflicting_copied_slot")
            reference = {**physical_scope, "logical_slot_id": row["logical_slot_id"],
                "request_artifact": row["request_artifact"], "dispatch_artifact": row["dispatch_artifact"],
                "family": adapter.FAMILY}
            # Unknown origins cannot create independent judgments; their exact
            # retained pairs still prevent an accidental replacement.
            if all(x is not None for x in identities):
                if len(matched) == 2:
                    pkey = pair_key(matched, "primary")
                    entry = blockers.setdefault(pkey, {"pair_key": pkey, "input_sha256": matched,
                        "role": "primary", "logical_references": {}})
                    entry["logical_references"][digest(reference)] = reference
                else:
                    disposition = "exact_alias_not_distinct_pair" if identities[0]["input_sha256"] == identities[1]["input_sha256"] else "complete_sources_outside_current_pair_frame"
                    excluded[digest(dedup)] = {**reference, "reason_code": disposition}
            elif any(x is not None and x["input_sha256"] not in known for x in identities):
                # One proven outside endpoint excludes a current-frame pair even
                # when its partner is unavailable; no identity is inferred.
                excluded[digest(dedup)] = {**reference,
                    "reason_code": "one_proven_source_outside_current_frame"}
            else:
                region(source_id, "logical_pair_endpoint_unavailable", matched or None, reference)
            gap_slots.add((row["original_attempt"], slot["number"]) if is_matching
                else (row["original_attempt"], slot["panel"], slot["a"], slot["b"]))
        for key, batch in declared.items():
            expected_size = 24 if is_matching else 60
            require(len(batch["logical_pair_slots"]) == len(set(batch["logical_pair_slots"])) == expected_size
                and observed[key] == set(batch["logical_pair_slots"]), "complete_batch_slot_partition")
            if is_matching:
                require({row["logical_slot"]["number"] for row in bindings if row["original_attempt"] == key[0]}
                    == set(range(1, 25)), "matching_number_partition")
        for gap in manifest["unresolved_evidence"]:
            reason = gap.get("reason_code")
            if reason == "pair_endpoint_unavailable":
                marker = (gap["attempt"], gap["number"]) if is_matching else (gap["attempt"], gap["panel"], *gap["sides"])
                require(marker in gap_slots, "unbound_endpoint_gap")
                continue  # Replaced by the more precise slot-derived region.
            if reason == "physical_origin_unverified" and any(k[0] == gap.get("attempt") for k in declared):
                continue  # The unverified physical view remains in each blocker.
            region(source_id, reason or "unclassified_adapter_gap", gap.get("input_sha256"), gap)
        for gap in manifest["inherited_inventory_gaps"]:
            region(source_id, "inherited_owner_inventory_gap", gap.get("affected_input_sha256"), gap)
    output = []
    for key in sorted(blockers):
        row = blockers[key]
        row["logical_references"] = [value for _, value in sorted(row["logical_references"].items())]
        output.append(row)
    return {"method": METHOD, **POLICY, "input_index_digest": index.digest,
        "pair_blockers": output, "unresolved_regions": [value for _, value in sorted(regions.items())],
        "excluded_slots": [value for _, value in sorted(excluded.items())],
        "counts": {"verified_physical_reference_batches": len(batches),
            "unverified_reference_batch_views": len(unverified), "unique_logical_slots": len(slots),
            "retained_slot_views": view_count, "unique_current_pair_blockers": len(output),
            "unresolved_regions": len(regions), "excluded_logical_slots": len(excluded)},
        "meaning": "Same-role no-replacement evidence only; no independent judgment count, reusable Y or whole-history closure."}


def _load(parent, session, record_id):
    from final_validation_batch_history_parent import BatchHistoryParent
    require(type(parent) is BatchHistoryParent, "concrete_parent_required")
    require_active(parent, session)
    require(parent.config.offline, "offline_required")
    history.sha(record_id)
    value, index = parent.load_completed(record_id)
    require(value["dispatch_authorized"] is False and value["whole_history_complete"] is False,
        "bounded_parent_policy")
    return value, index


def _protocol(value, index, record_id):
    return {"method": METHOD, "implementation": implementation(), "parent_record": record_id,
        "parent_artifact": digest(value), "input_index_digest": index.digest,
        "inherited_no_retry_inventory": value["inherited_no_retry_inventory"], "policy": POLICY}


def protocol_content(parent, session, record_id):
    value, index = _load(parent, session, record_id)
    return _protocol(value, index, record_id)


def derive_pair_lookup(parent, session, *, record_id, protocol_record):
    """Retain a child under an active separately registered offline operation."""
    value, index = _load(parent, session, record_id)
    expected = _protocol(value, index, record_id)
    actual = parent.ledger.get(protocol_record, "protocol")
    require(digest(actual["content"]) == digest(expected), "registered_protocol_binding")
    sources = [{"manifest": parent.ledger.artifacts.read(row["manifest_artifact"]),
        "bindings": parent.ledger.artifacts.read(row["pair_attempt_bindings_artifact"])} for row in value["sources"]]
    compiled = _compile(sources, index)
    payload = {**compiled, "protocol_record": protocol_record, "binding": expected,
        "source_artifacts": deepcopy(value["sources"]),
        "inherited_no_retry_inventory": value["inherited_no_retry_inventory"]}
    existing = parent._one(RESULT, optional=True)
    if existing:
        require(digest(existing["payload"]) == digest(payload), "changed_lookup_requires_amendment")
        identifier = existing["id"]
    else:
        require(implementation() == expected["implementation"], "implementation_changed")
        identifier = parent.ledger.record(session, RESULT, record_id, payload)
    return {"pair_lookup_record": identifier, "pair_lookup_artifact": digest(payload),
        **POLICY, "counts": compiled["counts"], "reused_historical_lookup": existing is not None}
