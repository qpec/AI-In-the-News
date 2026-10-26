"""Bounded main-owner pair-reference history; no source I/O or model calls.

The audited caller supplies a live verified AttemptInventory and its exact role
resolution. Named immutable two-article reference plans establish primary-task
blockers under the prospective policy below. Generic audit phases, two-member
group QA and prior exposure alone do not establish a pair-reference task.

This adapter supports historical Responses audit packets only. Their original
criteria/transport are not the current CLI pair contract: no label is converted
or reused. It does not manufacture CLI provenance. Protected records retain the
original full packets/payloads; only manifest is suitable for source-free output.
The returned inventory remains globally incomplete until other historical roles,
owners and manual reviews are reconciled by a separately audited integration.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from pathlib import Path

import final_validation_contract as current
import final_validation_exposure as exposure
import final_validation_history as history
import final_validation_prior as prior
import final_validation_roles as roles
import newsresearch.codex_provider as codex_provider
from dossier_transport import Invocation
from newsresearch.common import ResearchError, digest

VERSION = "final-validation-main-owner-pair-history-v1"
ROLE_POLICY = {
    "version": "named-legacy-pair-reference-as-primary-blocker-v1",
    "eligible_plan_names": sorted(roles.REFERENCES),
    "historical_role": "reference",
    "final_validation_role": "primary",
    "other_roles_inferred": False,
    "meaning": "A designated earlier pair-reference attempt blocks replacement of the primary task; it does not become a new independent or compatible reference.",
}
PHYSICAL_ID_POLICY = {
    "version": "verified-source-id-and-original-attempt-v1",
    "owner_sha256": "digest(certificate.source_id)",
    "attempt_id": "digest([certificate.source_id, original_attempt])",
    "source_id": "Exact verified inventory source_id; retain it and the original attempt for cross-adapter reconciliation.",
    "requirement": "Other adapters must reproduce these identities for duplicate views of this owner/attempt, not hash a different owner alias or substitute a response ID.",
}


def require(value, code):
    if not value:
        raise ValueError("pair_history_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), Path(history.__file__), Path(current.__file__), Path(codex_provider.__file__))
    return {**prior.implementation(), **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _legacy_contract(index, packet, artifacts):
    """Exact frozen builder identity, not inferred equivalence to current rules."""
    require(packet.get("phase") == "audit" and packet.get("kind") == "responses", "pair_transport_required")
    ids, kind, _ = prior.task_sources(index, packet, artifacts)
    require(kind == "pair" and len(ids) == 2, "two_source_pair_required")
    docs = exposure._documents(index, packet.get("original_documents", packet.get("documents")))
    for builder in (prior.v1, prior.v2, prior.v3, prior.v5):
        try:
            expected = builder.audit_request(docs, count_tokens=lambda _: 0, max_tokens=96_000,
                                            max_output_tokens=packet["request"]["max_output_tokens"])
            prior._same_packet(packet, expected)
        except (ValueError, ResearchError):
            continue
        mapping = packet["question_map"]
        pairs = [value for value in mapping.values() if value.get("kind") == "pair"]
        clarity = [value for value in mapping.values() if value.get("kind") == "clarity"]
        require(len(pairs) == 1 and {pairs[0]["left"], pairs[0]["right"]} == set(ids)
                and len(clarity) == 2 and {a["document_id"] for a in clarity} == set(ids), "pair_criterion_sources")
        definition = {"builder": builder.__name__, "method": packet.get("method"),
            "instructions_sha256": digest(packet["request"]["instructions"]),
            "question_map_sha256": digest(mapping),
            "output_schema_sha256": digest(packet["request"]["text"]["format"]["schema"]),
            "focus_rules_sha256": packet.get("focus_rules_sha256")}
        identity = history.sources([{"document_id": doc["document_id"],
            "title_sha256": hashlib.sha256(doc["title"].encode()).hexdigest(),
            "body_sha256": hashlib.sha256(doc["body"].encode()).hexdigest(),
            "input_sha256": digest({"title": doc["title"], "body": doc["body"]})} for doc in docs], pair=True)
        return identity, definition
    raise ValueError("pair_history_unsupported_audit_contract")


@dataclass(frozen=True)
class MainOwnerPairHistory:
    records: tuple
    inventory_certificate: dict
    manifest: dict

    def resolve(self, source_identity, *, role="primary"):
        """Conservative local resolution; never certifies whole-study coverage."""
        return history.resolve_history(source_identity, role, list(self.records), self.inventory_certificate)


def normalize_main_owner_pair_history(reader, resolved_roles):
    """Bind actual attempts to exact named plans; prepared requests do not block.

    Requires the Source caller's complete immutable census and active scoped byte
    mapping. This pure function verifies supplied identities, not that an arbitrary
    caller actually opened a Source. It adds no role to production candidate C.
    CLI-compatible historical rows require a future trusted CLI-specific adapter;
    copying API payload fields into CLI provenance is explicitly unsupported.
    Physical IDs follow PHYSICAL_ID_POLICY; downstream cross-owner integration
    must reconcile the original inventory source_id/attempt before combining.
    """
    certificate = reader.certificate
    normalized_prior = prior.normalize_main_owner_prior(reader, resolved_roles)
    store = exposure._Artifacts(reader.artifacts)
    census = store.get(certificate["evidence_sha256"])
    events = {row["seq"]: (row, exposure._event(row, certificate["source_head"][0])) for row in reader.events}
    intended = {value["attempt"]: (row, value) for row, value in events.values() if row["kind"] == "model.attempt.intended"}
    require([row["event_hash"] for row, _ in intended.values()] == census["intent_event_hashes"], "intent_census")
    by_task = {value["task_key"]: attempt for attempt, (_, value) in intended.items()}
    require(len(by_task) == len(intended), "duplicate_physical_task")
    responses = {}
    for row in reader.records:
        value = exposure._record(row, events, store)
        if row["kind"] == "cyber_dossier_response":
            require(value["attempt"] not in responses, "duplicate_response")
            responses[value["attempt"]] = (row, value)
    require([row["id"] for row in reader.records] == census["record_ids"], "record_census")
    prior_by_attempt = {row["event_id"]: row for row in normalized_prior.observations}
    planned_roles = resolved_roles.catalog["planned_task_bindings"]
    proven, prepared, gaps = {}, [], []
    plan_records = []
    for row, event in zip(reader.phase_records, reader.phase_events, strict=True):
        value = roles._record(row, store, certificate, kind="cyber_dossier_phase")
        if value["name"] not in ROLE_POLICY["eligible_plan_names"]:
            continue
        require(event["kind"] == "record.created" and event["seq"] == row["created_event"]
                and exposure._event(event, certificate["source_head"][0]) == {
                    "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "plan_creation_binding")
        selected = store.get(value["artifact"])
        items = selected.get("items")
        require(isinstance(items, list) and selected.get("selected_pairs") == [[i["left"], i["right"]] for i in items], "plan_selection")
        plan_records.append(row["id"])
        for item in items:
            ids = [item["left"], item["right"]]
            require(len(set(ids)) == 2 and set(ids) <= {i.document_id for i in reader.index.inputs}, "selected_pair_identity")
            if "packet" not in item or "task_key" not in item:
                gaps.append({"reason_code": "reference_binding_fields_absent", "document_ids": ids, "plan_record": row["id"]})
                continue
            if item["packet"] is None:
                require(item["task_key"] is None and item.get("reason") == "reference_packet_capacity", "capacity_plan")
                prepared.append({"plan_record": row["id"], "document_ids": ids, "task_key": None,
                                 "reason_code": "prepared_capacity_no_attempt"})
                continue
            packet = store.get(item["packet"], optional=True)
            if packet is None:
                gaps.append({"reason_code": "selected_packet_unavailable", "document_ids": ids, "plan_record": row["id"]})
                continue
            identity, definition = _legacy_contract(reader.index, packet, reader.artifacts)
            require({s["document_id"] for s in identity} == set(ids), "plan_packet_sources")
            task = digest([certificate["plan"], "responses", packet["request"]])
            require(item["task_key"] == task, "plan_task_binding")
            attempt = by_task.get(task)
            matching_role = [entry for entry in planned_roles if entry["stage"] == value["name"]
                and entry["task_key"] == task and entry["role"] == "reference" and entry["physical_attempt"] == attempt]
            proof = sorted({row["id"], row["artifact"], value["artifact"], item["packet"]})
            require(matching_role and all(set(entry["evidence_ids"]) == set(proof) for entry in matching_role), "exact_role_plan_binding")
            if attempt is None:
                prepared.append({"plan_record": row["id"], "document_ids": ids, "task_key": task,
                                 "reason_code": "prepared_request_no_attempt"})
                continue
            intent = intended[attempt][1]
            require(intent["phase"] == "audit" and intent["packet"] == item["packet"]
                    and intent["request"] == digest(packet["request"]), "actual_selected_packet")
            require(store.get(intent["request"]) == packet["request"]
                    and store.get(intent["dispatch"]) == Invocation(packet["request"], attempt, "responses").manifest(), "exact_dispatch_binding")
            observed_prior = prior_by_attempt.get(attempt)
            require(observed_prior is not None and "reference" in observed_prior["roles"]
                    and observed_prior["task_binding"]["kind"] == "pair"
                    and set(observed_prior["task_binding"]["document_ids"]) == set(ids), "prior_pair_role_binding")
            if attempt not in proven:
                proven[attempt] = {"identity": identity, "definition": definition, "packet": packet, "proof": set(), "plans": set()}
            require(proven[attempt]["identity"] == identity and proven[attempt]["definition"] == definition, "reused_pair_binding_changed")
            proven[attempt]["proof"].update(proof)
            proven[attempt]["plans"].add(value["name"])

    records, bindings = [], []
    for attempt in sorted(proven):
        selected = proven[attempt]
        row, intent = intended[attempt]
        response = responses.get(attempt)
        envelope = store.get(response[1]["response"]) if response else None
        require(response is None or isinstance(envelope, dict), "response_envelope_type")
        acknowledged, evidence_kind = prior.serving_evidence(selected["packet"], envelope)
        state = "intent" if response is None else ("predispatch_failure" if acknowledged == "predispatch_failure" else "returned")
        # Original API provenance is retained as API provenance. No CLI version,
        # terminal completion, criterion answers or binary Y are manufactured.
        provenance = None if state != "returned" else {
            "kind": "historical_responses_audit", "transport": "openai-dossier-http-v1",
            "configured_model": selected["packet"]["request"]["model"],
            "reasoning_effort": selected["packet"]["request"].get("reasoning", {}).get("effort"),
            "observed_model": envelope.get("model"),
            "payload_model": envelope.get("payload", {}).get("model") if isinstance(envelope.get("payload"), dict) else None,
            "cli_version": None, "request_sha256": intent["request"], "dispatch_sha256": intent["dispatch"],
            "packet_sha256": intent["packet"], "response_sha256": response[1]["response"],
            "original_parsed_artifact": response[1].get("parsed"),
            "acknowledgement_state": acknowledged, "acknowledgement_rule": prior.VERSION,
            "current_cli_contract_compatible": False,
        }
        result = {"record_id": response[0]["id"] if response else row["event_hash"],
            "owner_sha256": digest(certificate["source_id"]), "attempt_id": digest([certificate["source_id"], attempt]),
            "logical_task_id": intent["task_key"], "role": "primary", "scope_kind": "pair_reference",
            "source_identity": selected["identity"], "attempt_state": state,
            "definition_version": "legacy-responses-audit:" + digest(selected["definition"]),
            "packet": deepcopy(selected["packet"]),
            "payload": deepcopy(envelope.get("payload")) if state == "returned" else None, "provenance": provenance}
        records.append(result)
        bindings.append({"record_id": result["record_id"], "attempt_id": result["attempt_id"], "original_attempt": attempt,
            "original_task_key": intent["task_key"], "intent_event": row["event_hash"],
            "original_response_record": response[0]["id"] if response else None,
            "original_response_artifact": response[1]["response"] if response else None,
            "packet_sha256": intent["packet"], "request_sha256": intent["request"], "dispatch_sha256": intent["dispatch"],
            "source_identity_sha256": digest(selected["identity"]), "historical_role": "reference",
            "historical_contract": selected["definition"], "mapping_policy_sha256": digest(ROLE_POLICY),
            "plan_names": sorted(selected["plans"]), "role_evidence_ids": sorted(selected["proof"]),
            "acknowledgement_state": acknowledged, "evidence_kind": evidence_kind,
            "compatible": False, "incompatibility_reason": "legacy_api_contract_is_not_current_cli_pair_contract"})
    history.normalize_records(records)  # Mechanical consistency; never rejudge.
    unintegrated = sorted(set(intended) - set(proven))
    manifest = {"version": VERSION, "role_mapping_policy": deepcopy(ROLE_POLICY),
        "physical_identity_policy": deepcopy(PHYSICAL_ID_POLICY), "source_id": certificate["source_id"],
        "source_head": certificate["source_head"], "input_index_digest": reader.index.digest,
        "source_certificate_sha256": digest(certificate), "census_artifact": certificate["evidence_sha256"],
        "role_catalog_sha256": digest(resolved_roles.catalog), "prior_manifest_sha256": digest(normalized_prior.manifest),
        "records_sha256": digest(records), "physical_attempts": len(intended), "pair_reference_attempts": len(records),
        "attempt_state_counts": dict(Counter(r["attempt_state"] for r in records)),
        "acknowledgement_counts": dict(Counter(b["acknowledgement_state"] for b in bindings)),
        "exact_reference_plan_records": sorted(plan_records), "attempt_bindings": bindings,
        "prepared_only": prepared, "unresolved_evidence": gaps,
        "unintegrated_physical_attempts": unintegrated,
        "unintegrated_phase_counts": dict(Counter(intended[a][1]["phase"] for a in unintegrated)),
        "known_positive_roles_are_not_complete_history": True, "whole_study_history_complete": False,
        "main_owner_pair_role_history_complete": False, "all_normalized_references_incompatible": True,
        "reused_labels": 0, "new_model_calls": 0, "source_mutations": 0, "changes_candidate_exposure": False,
        "limitations": "Exact named two-source API reference plans only. Unplanned/batched ancestor audits, other role histories, separate owners and substantive manual/CLI reviews remain unresolved. Group/card/screening judgments supply no pair truth. Original costs, holds, responses and labels are unchanged; no compatible CLI provenance is invented."}
    inventory_certificate = {"binding_sha256": digest(manifest), "complete": False,
                             "unknown_input_sha256": [], "global_gap": True}
    history.validate_inventory(inventory_certificate)
    return MainOwnerPairHistory(tuple(records), inventory_certificate, manifest)
