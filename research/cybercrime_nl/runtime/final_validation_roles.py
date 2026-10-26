"""Pure bounded role resolution over a verified final attempt inventory.

No owner access, registration, model calls or new exposure. The caller supplies
the active final_validation_inventory reader, full input documents from the
verified final snapshot, and its bound frozen token counter. The upstream reader
must establish complete ledger/head integrity; a self-consistent supplied subset
does not establish completeness. Generic phase/version names never imply roles.

Supported evidence: exact V7 full seed plan, full_v6 initial/recovery card
assignment phases, pilot_v5 initial card assignments, explicit pair-reference
plans. Other ancestor/development/group-reference roles remain unknown. This is
not the complete cross-owner P inventory or a source-integrity certificate.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from itertools import combinations
from pathlib import Path

import final_validation_exposure as exposure
import run_dossiers_v5 as frozen
from newsresearch.common import ResearchError, canonical, digest

VERSION = "final-validation-exact-phase-roles-v1"
ASSIGNMENTS = {
    "full_v6_seed_assignments": ("production", ("full_v6_seed_cards",)),
    "full_v6_recovery_assignments": ("production", ("full_v6_seed_checked_commit", "full_v6_singleton_cards")),
    "pilot_v5_seed_assignments": ("development", ("pilot_v5_seed_cards",)),
}
REFERENCES = {
    "full_v6_retained_memberships_reference_plan", "full_v6_nonjoined_candidates_reference_plan",
    "full_v5_retained_memberships_reference_plan", "full_v5_nonjoined_candidates_reference_plan",
    "pilot_v5_positive_reference_plan", "pilot_v5_assignments_reference_plan",
}


def _require(value, code):
    if not value:
        raise ValueError("roles_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = [Path(__file__), Path(exposure.__file__)]
    paths.extend(Path(__file__).with_name(name) for name in (
        "final_validation_projection.py", "final_validation_frame.py", "final_validation_design.py"))
    return {**frozen.implementation(), **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


class _Overlay(Mapping):
    def __init__(self, base, additions):
        self.base, self.additions = base, dict(additions)

    def __getitem__(self, key):
        return self.additions[key] if key in self.additions else self.base[key]

    def __iter__(self):
        return iter(set(self.base) | set(self.additions))

    def __len__(self):
        return len(set(self.base) | set(self.additions))


@dataclass(frozen=True)
class RoleResolution:
    role_artifact: dict
    catalog: dict
    metadata: dict
    additions: dict
    source_certificate_sha256: str

    def exposure_arguments(self, reader):
        """Overlay only pair roles; underlying scoped bytes cannot escape Source."""
        _require(digest(reader.certificate) == self.source_certificate_sha256, "reader_certificate_changed")
        values = reader.exposure_arguments()
        values["artifacts"] = _Overlay(values["artifacts"], self.additions)
        values["inventory"]["role_artifact"] = digest(self.role_artifact)
        values["inventory"]["gaps"] += deepcopy(self.catalog["production_role_gaps"])
        return values


def _record(row, store, certificate, *, kind=None):
    _require(isinstance(row, dict) and (kind is None or row.get("kind") == kind), "record_kind")
    value = store.get(row["artifact"])
    _require(canonical(value) == row["payload"] and row.get("supersedes") is None
             and row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
                 "payload": row["artifact"], "supersedes": None})
             and type(row["created_event"]) is int and 0 < row["created_event"] <= certificate["source_head"][0],
             "immutable_record_binding")
    if kind == "cyber_dossier_phase":
        _require(value.get("plan") == certificate["plan"] and value.get("name") == row["logical_key"]
                 and value.get("execution_amendment") in {None, *certificate["amendments"]}, "phase_scope")
    return value


def resolve_inventory_roles(reader, documents, *, count_tokens, tokenizer_binding):
    """Return source-free role metadata and a lazy overlay for reconstruct_exposure.

    documents is a caller-verified Mapping of complete indexed title/body inputs.
    tokenizer_binding identifies the caller's exact counter implementation/cache;
    this pure helper records, but does not independently certify, that binding.
    Exact reconstructed packets must match actual requests before a role attaches.
    Missing phase/card/packet evidence leaves roles unknown; contradictory retained
    identities/coverage fail closed. No labels, probabilities or billing change.
    """
    exposure._sha(tokenizer_binding)
    _require(callable(count_tokens) and isinstance(documents, Mapping), "inputs_required")
    certificate = deepcopy(reader.certificate)
    store = exposure._Artifacts(reader.artifacts)
    census = store.get(certificate["evidence_sha256"])
    _require(census.get("source_head") == certificate["source_head"] and census.get("plan") == certificate["plan"]
             and census.get("input_index_digest") == reader.index.digest == certificate["input_index_digest"], "census_binding")
    known = {item.document_id for item in reader.index.inputs}
    _require(set(documents) <= known, "foreign_document")
    # Missing inputs may leave some reconstruction unresolved; supplied ones must
    # be literal originals. This does not require a second full-text copy.
    for identity, document in documents.items():
        _require(document.get("document_id") == identity, "document_key")
        exposure._documents(reader.index, [document])

    intents, tasks, roles, evidence_ids = {}, {}, {}, {}
    intended_hashes = []
    for row in reader.events:
        if row["kind"] != "model.attempt.intended":
            continue
        intent = exposure._event(row, certificate["source_head"][0])
        attempt = intent["attempt"]
        _require(attempt not in intents and intent.get("batch") == certificate["plan"], "intent_scope_or_duplicate")
        _require(intent["task_key"] not in tasks, "duplicate_physical_task")
        packet, request = store.get(intent["packet"]), store.get(intent["request"])
        _require(packet.get("request") == request and digest(request) == intent["request"]
                 and intent["task_key"] == digest([certificate["plan"], packet.get("kind", "decisions"), request])
                 and intent.get("phase") == packet.get("phase"), "intent_packet_task")
        intents[attempt], tasks[intent["task_key"]] = intent, attempt
        roles[attempt], evidence_ids[attempt] = set(), set()
        intended_hashes.append(row["event_hash"])
    _require(intended_hashes == census.get("intent_event_hashes"), "complete_supplied_intent_census")
    _require(set(census.get("pair_attempt_ids", [])) == {
        a for a, intent in intents.items() if intent["phase"] in {"seed", "assignment"}}, "pair_census")

    phases = {}
    _require([r["id"] for r in reader.phase_records] == census.get("phase_record_ids"), "phase_census")
    _require([r["event_hash"] for r in reader.phase_events] == census.get("phase_event_hashes")
             and len(reader.phase_events) == len(reader.phase_records), "phase_event_census")
    for row, event in zip(reader.phase_records, reader.phase_events, strict=True):
        value = _record(row, store, certificate, kind="cyber_dossier_phase")
        created = exposure._event(event, certificate["source_head"][0])
        _require(row["created_event"] == event["seq"] and event["kind"] == "record.created" and created == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "phase_creation_binding")
        _require(value["name"] not in phases, "duplicate_phase")
        phases[value["name"]] = (row, value)
    _require(reader.amendment_packet_plans == census.get("amendment_packet_plans"), "seed_plan_census")
    diagnostics, planned, production_gaps = [], [], []

    def pair_metadata(packet):
        return exposure.packet_metadata(reader.index, packet, packet["request"], packet_sha256=digest(packet),
            request_sha256=digest(packet["request"]), artifacts=reader.artifacts)

    def gap(stage, code, identifiers=None):
        diagnostics.append({"stage": stage, "reason_code": code,
                            "document_ids": sorted(identifiers) if identifiers is not None else None})
        if stage in {"full_v6_seeds", "full_v6_seed_assignments", "full_v6_recovery_assignments"} and code != "prepared_capacity_deferred_no_attempt":
            production_gaps.append({"reason_code": "unresolved_production_role_evidence",
                                    "document_ids": sorted(identifiers) if identifiers is not None else None})

    def phase(name, *, record_gap=True):
        item = phases.get(name)
        if item is None:
            if record_gap:
                gap(name, "phase_evidence_absent")
            return None
        row, value = item
        result = store.get(value["artifact"], optional=True)
        if result is None:
            if record_gap:
                gap(name, "phase_artifact_unavailable")
            return None
        _require(isinstance(result, dict), "phase_payload")
        return result, [row["id"], row["artifact"], value["artifact"]]

    def match(packet, role, proof, stage):
        kind = packet.get("kind", "decisions")
        task = digest([certificate["plan"], kind, packet["request"]])
        attempt = tasks.get(task)
        entry = {"stage": stage, "task_key": task, "request_sha256": digest(packet["request"]),
                 "role": role, "physical_attempt": attempt, "evidence_ids": sorted(set(proof))}
        planned.append(entry)
        if attempt is None:
            return task  # Prepared-only: never creates a physical attempt.
        original = store.get(intents[attempt]["packet"])
        _require(original.get("phase") == packet.get("phase") and original.get("kind", "decisions") == kind
                 and original["request"] == packet["request"], "matched_task_wire")
        if packet["phase"] in {"seed", "assignment"}:
            left = pair_metadata(original)
            right = pair_metadata(packet)
            # Packet hashes differ only for non-wire bookkeeping such as token
            # proxies. Full literal sources, historical members and questions must match.
            _require({k: v for k, v in left.items() if k != "packet_sha256"}
                     == {k: v for k, v in right.items() if k != "packet_sha256"}, "matched_task_source_binding")
        else:
            _require(digest(original) == digest(packet), "reference_exact_packet")
        roles[attempt].add(role)
        evidence_ids[attempt].update(proof)
        return task

    # V7's explicitly registered full production frame, not a generic seed phase.
    seed_refs = set()
    for binding in reader.amendment_packet_plans:
        if binding["record_kind"] != "cyber_dossier_execution_amendment_v7":
            continue
        amendment = store.get(binding["record_artifact"])
        _require(binding["record_id"] in certificate["amendments"]
                 and amendment.get("parent_plan") == certificate["plan"]
                 and amendment.get("seed_packet_plan_artifact") == binding["artifact"], "v7_seed_plan_binding")
        entries = store.get(binding["artifact"])
        _require(isinstance(entries, list) and [e["packet_artifact"] for e in entries if e["packet_artifact"] is not None]
                 == binding["packet_artifacts"], "v7_seed_plan_packets")
        for entry in entries:
            ids = entry["document_ids"]
            _require(exposure._ids(ids) <= known and len(ids) >= 1
                     and entry["intended_pairs"] == [list(p) for p in combinations(ids, 2)]
                     and entry["intended_pair_count"] == len(entry["intended_pairs"]), "seed_plan_members")
            ref = entry["packet_artifact"]
            if ref is None:
                _require(entry["state"] == "deferred_capacity_unjudged", "seed_deferred_state")
                gap("full_v6_seeds", "prepared_capacity_deferred_no_attempt", ids)
                continue
            _require(entry["state"] in {"untouched_request_fits", "reused_prior_attempt"}, "seed_state")
            packet = store.get(ref, optional=True)
            if packet is None:
                gap("full_v6_seeds", "seed_packet_unavailable", ids)
                continue
            _require(packet.get("phase") == "seed" and set(packet["document_ids"]) == set(ids), "seed_packet_members")
            pair_metadata(packet)
            match(packet, "production", [binding["record_id"], binding["record_artifact"], binding["artifact"], ref], "full_v6_seeds")
        seed_refs.add(binding["artifact"])
    if not seed_refs:
        gap("full_v6_seeds", "registered_v7_seed_plan_absent")

    # Rebuild all offered packets, not just positive proposal task keys.
    for name, (role, card_names) in ASSIGNMENTS.items():
        selected = phase(name)
        if selected is None:
            continue
        assignment, proof = selected
        coverage = assignment.get("packet_coverage")
        _require(isinstance(coverage, dict), "assignment_coverage_required")
        pool, available = {}, True
        for card_name in card_names:
            selected_cards = phase(card_name, record_gap=False)
            if selected_cards is None:
                available = False
                continue
            value, card_proof = selected_cards
            source_cards = value.get("cards" if card_name.endswith("_checked_commit") else "usable")
            _require(isinstance(source_cards, dict) and not set(pool).intersection(source_cards), "historical_card_pool")
            pool.update(source_cards)
            proof += card_proof
        for identifier, value in coverage.items():
            _require(identifier in known and isinstance(value, dict), "assignment_query")
            chosen = value.get("chosen_dossiers")
            exposure._ids(chosen)
            _require(0 < len(chosen) <= (15 if "recovery" in name else 5), "chosen_candidate_count")
            if value.get("coverage_complete") is False:
                _require(value.get("packets") == 0 and value.get("reason") == "full_article_single_candidate_exceeds_capacity",
                         "capacity_coverage_state")
                gap(name, "prepared_capacity_deferred_no_attempt", [identifier])
                continue
            _require(value.get("coverage_complete") is True, "coverage_boolean")
            if not available or identifier not in documents or any(d not in pool for d in chosen):
                gap(name, "historical_card_or_query_unavailable", [identifier])
                continue
            snapshots = [pool[d] for d in chosen]
            _require(all(s.get("dossier_id") == d for d, s in zip(chosen, snapshots, strict=True)), "card_pool_identity")
            try:
                packets = frozen.pack_assignment(documents[identifier], snapshots, count_tokens)
            except ResearchError as error:
                if str(error) != "dossier_packet_capacity":
                    raise
                gap(name, "reconstruction_capacity_disagrees_with_saved_coverage", [identifier])
                continue
            _require(value.get("packets") == len(packets) and value.get("candidate_counts") == [len(p["bindings"]) for p in packets],
                     "reconstructed_packet_coverage")
            keys = [match(p, role, proof, name) for p in packets]
            proposal = assignment.get("proposals", {}).get(identifier)
            if proposal is not None:
                _require(proposal.get("task_keys") == keys, "positive_task_keys_disagree")

    # Selected exact pair-reference packets, including original methods reused by
    # later final audits. A reference phase does not add production candidate C.
    for name in sorted(REFERENCES & phases.keys()):
        selected = phase(name)
        if selected is None:
            continue
        value, proof = selected
        items = value.get("items")
        _require(isinstance(items, list) and value.get("selected_pairs") == [[i["left"], i["right"]] for i in items],
                 "reference_selection")
        for item in items:
            ids = [item["left"], item["right"]]
            _require(exposure._ids(ids) <= known and len(ids) == 2, "reference_pair")
            if "packet" not in item or "task_key" not in item:
                gap(name, "reference_binding_fields_absent", ids)
                continue
            if item.get("packet") is None:
                _require(item.get("task_key") is None and item.get("reason") == "reference_packet_capacity", "reference_capacity")
                gap(name, "prepared_reference_capacity_no_attempt", ids)
                continue
            packet = store.get(item["packet"], optional=True)
            if packet is None:
                gap(name, "reference_packet_unavailable", ids)
                continue
            _require(packet.get("phase") == "audit" and packet.get("kind") == "responses"
                     and set(packet.get("document_ids", [])) == set(ids), "reference_packet_scope")
            _require(item["task_key"] == digest([certificate["plan"], "responses", packet["request"]]), "reference_task_key")
            match(packet, "reference", [*proof, item["packet"]], name)

    entries = [{"attempt": attempt, "roles": sorted(roles[attempt]) or None,
                "evidence_ids": sorted(evidence_ids[attempt]) or [certificate["evidence_sha256"]],
                "affected_document_ids": None} for attempt in sorted(intents)]
    catalog = {"version": VERSION, **{k: certificate[k] for k in ("source_id", "source_head", "plan", "input_index_digest")},
        "census_artifact": certificate["evidence_sha256"], "tokenizer_binding": tokenizer_binding,
        "attempts": entries, "planned_task_bindings": planned, "unresolved_evidence": diagnostics,
        "production_role_gaps": production_gaps,
        "role_claims_are_positive_evidence_not_exhaustive_history": True,
        "incomplete_prior_role_history_attempts": sorted(intents),
        "all_prior_roles_reconciled": False, "cross_owner_prior_exposure_complete": False,
        "semantic_labels_reclassified": False, "physical_attempts_added": 0}
    pair_ids = set(census["pair_attempt_ids"])
    role_artifact = {k: certificate[k] for k in ("source_id", "source_head", "plan", "input_index_digest")}
    role_artifact["attempts"] = [entry for entry in entries if entry["attempt"] in pair_ids]
    additions = {digest(value): canonical(value).encode() for value in (catalog, role_artifact)}
    metadata = {"version": VERSION, "catalog_artifact": digest(catalog), "role_artifact": digest(role_artifact),
        "physical_attempts": len(intents), "pair_attempts": len(pair_ids),
        "resolved_pair_attempts": sum(bool(roles[a]) for a in pair_ids),
        "unclassified_pair_attempts": sum(not roles[a] for a in pair_ids),
        "role_counts": dict(Counter(r for values in roles.values() for r in values)),
        "prepared_task_bindings_without_attempt": sum(p["physical_attempt"] is None for p in planned),
        "unresolved_evidence_counts": dict(Counter(d["reason_code"] for d in diagnostics)),
        "source_integrity_verified_by_this_pure_helper": False, "all_prior_roles_reconciled": False,
        "cross_owner_prior_exposure_complete": False, "physical_attempts_added": 0}
    return RoleResolution(role_artifact, catalog, metadata, additions, digest(certificate))
