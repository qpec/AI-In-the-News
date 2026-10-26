"""Bounded main-owner prior-exposure normalization; no I/O/models/registration.

Consumes a verified active inventory and exact role resolution. Positive prior
roles are extended from immutable pilot selections/completed phases/task plans.
This does NOT reconcile all historical formats, cross-owner or manual reviews.
Its owner contribution is always incomplete; it cannot establish P=0. Outputs
preserve group/task bindings as exposure metadata, never reference pair labels.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path

import dossier_contract as v1
import dossier_contract_v2 as v2
import dossier_contract_v3 as v3
import dossier_contract_v5 as v5
import final_validation_exposure as exposure
import final_validation_inventory as inventory_module
import final_validation_projection as projection
import final_validation_roles as roles_module
import run_dossiers as original
import summary_fidelity_contract as fidelity_v1
import summary_fidelity_contract_v2 as fidelity_v2
from newsresearch.common import ResearchError, canonical, digest

VERSION = "final-validation-main-owner-prior-v1"
PILOT_LABELS = {"cyber_dossier_execution_amendment": "pilot_v2", **{
    f"cyber_dossier_execution_amendment_v{n}": f"pilot_v{n}" for n in (3, 4, 5)}}


def _require(value, code):
    if not value:
        raise ValueError("prior_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), Path(v2.__file__), Path(v3.__file__), Path(fidelity_v1.__file__), Path(fidelity_v2.__file__))
    return {**inventory_module.implementation(), **roles_module.implementation(),
            **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _same_packet(actual, expected):
    expected = {**expected, "kind": actual.get("kind", "decisions")}
    _require(all(actual.get(k) == value for k, value in expected.items() if k != "input_tokens_proxy"), "packet_source_wire_binding")


def task_sources(index, packet, artifacts):
    """Verify complete original inputs and exact supported wire projections."""
    phase = packet.get("phase")
    _require(packet.get("kind", "decisions") == ("responses" if phase in {
        "card_quality", "card_quality_audit", "audit", "summary_fidelity_audit"} else "decisions"), "task_transport_kind")
    docs = exposure._documents(index, packet.get("original_documents", packet.get("documents")))
    if phase in {"seed", "assignment"}:
        metadata = exposure.packet_metadata(index, packet, packet["request"], packet_sha256=digest(packet),
            request_sha256=digest(packet["request"]), artifacts=artifacts)
        ids = list(metadata["document_ids"])
        for member in metadata["candidate_memberships"]:
            _require(member["source_document_ids"] is not None, "historical_summary_members_unavailable")
            ids.extend(member["source_document_ids"])
        return sorted(set(ids)), "pair" if phase == "seed" and len(ids) == 2 else "multiarticle", metadata
    if phase == "assignment_full_member_control":
        for snapshot in packet["candidate_cards"]:
            exposure._documents(index, snapshot["original_documents"])
        expected = v5.full_member_assignment_request(docs[0], packet["candidate_cards"], count_tokens=lambda _: 0, max_tokens=96_000)
        _same_packet(packet, expected)
        ids = [d["document_id"] for d in docs] + [d["document_id"] for s in packet["candidate_cards"] for d in s["original_documents"]]
        return sorted(set(ids)), "multiarticle", {"model": packet["request"]["model"],
            "question_names": [q["name"] for q in packet["request"]["questions"]]}
    if phase in {"card_quality", "card_quality_audit"}:
        maker = v5.card_quality_request if phase == "card_quality" else v5.card_quality_audit_request
        expected = maker(docs, packet["card_snapshot"], count_tokens=lambda _: 0, max_tokens=96_000,
                         max_output_tokens=packet["request"]["max_output_tokens"])
        _same_packet(packet, expected)
        return [d["document_id"] for d in docs], "group", None
    if phase == "summary_fidelity_audit":
        maker = {fidelity_v1.METHOD: fidelity_v1, fidelity_v2.METHOD: fidelity_v2}.get(packet.get("method"))
        _require(maker is not None, "fidelity_contract_unknown")
        expected = maker.request(docs, packet["summary_snapshot"], count_tokens=lambda _: 0, max_tokens=96_000,
                                 max_output_tokens=packet["request"]["max_output_tokens"])
        _same_packet(packet, expected)
        return [d["document_id"] for d in docs], "group", None
    if phase == "audit":
        accepted = False
        for maker in (v1, v2, v3, v5):
            try:
                expected = maker.audit_request(docs, count_tokens=lambda _: 0, max_tokens=96_000,
                    max_output_tokens=packet["request"]["max_output_tokens"])
                _same_packet(packet, expected)
                accepted = True
                break
            except (ValueError, ResearchError):
                continue
        _require(accepted, "audit_wire_source_binding")
        return [d["document_id"] for d in docs], "pair" if len(docs) == 2 else "multiarticle", None
    raise ValueError("prior_unsupported_task_source_format")


def serving_evidence(packet, envelope, decision_metadata=None):
    """Acknowledgement, not successful judgment; no billing/label reinterpretation."""
    if envelope is None:
        return "uncertain", "unavailable_envelope"
    _require(isinstance(envelope, dict), "envelope_type")
    raw, payload = envelope.get("raw_response"), envelope.get("payload")
    raw = raw if isinstance(raw, dict) else {}
    if raw.get("dispatch_started") is False:
        _require(payload is None and raw.get("http_status") is None, "predispatch_serving_contradiction")
        return "predispatch_failure", "explicit_predispatch_failure"
    if packet.get("kind", "decisions") == "decisions":
        state, _ = projection.acknowledged_decision_envelope(decision_metadata, envelope)
        return ("acknowledged", "model_serving_envelope") if state == "exposed" else ("uncertain", "unrecognized_envelope")
    status = raw.get("http_status")
    if not (type(status) is int and 200 <= status < 300 and isinstance(payload, dict)
            and payload.get("error") is None and payload.get("model") == packet["request"]["model"]
            and envelope.get("model") == packet["request"]["model"]
            and payload.get("status") in {"completed", "incomplete"} and isinstance(payload.get("output"), list)):
        return "uncertain", "unrecognized_envelope"
    output = payload["output"]
    recognized = bool(output) and all(isinstance(item, dict) and (
        item.get("type") == "reasoning" and isinstance(item.get("summary"), list)
        or item.get("type") == "message" and isinstance(item.get("content"), list) and bool(item["content"])
        and all(isinstance(c, dict) and (c.get("type") == "output_text" and isinstance(c.get("text"), str)
            or c.get("type") == "refusal" and isinstance(c.get("refusal"), str)) for c in item["content"])) for item in output)
    usage = payload.get("usage")
    empty_incomplete = (not output and payload["status"] == "incomplete" and isinstance(payload.get("incomplete_details"), dict)
        and isinstance(payload["incomplete_details"].get("reason"), str) and isinstance(usage, dict)
        and type(usage.get("input_tokens")) is int and usage["input_tokens"] > 0
        and type(usage.get("output_tokens")) is int and usage["output_tokens"] >= 0)
    return ("acknowledged", "model_serving_envelope") if recognized or empty_incomplete else ("uncertain", "unrecognized_envelope")


@dataclass(frozen=True)
class MainOwnerPrior:
    observations: tuple
    source_contribution: dict
    manifest: dict

    def project(self, index, *, inventory_certificate):
        """Caller must supply an explicit cross-study scope; incomplete stays so."""
        selected = [s for s in inventory_certificate.get("sources", []) if s.get("source_id") == self.source_contribution["source_id"]]
        _require(selected == [self.source_contribution], "owner_contribution_changed")
        return projection.project_prior_exposure(index, list(self.observations), inventory_certificate=inventory_certificate)


def normalize_main_owner_prior(reader, resolved_roles):
    certificate = reader.certificate
    _require(resolved_roles.source_certificate_sha256 == digest(certificate)
             and resolved_roles.additions.get(digest(resolved_roles.catalog)) == canonical(resolved_roles.catalog).encode(), "role_resolution_binding")
    store = exposure._Artifacts(reader.artifacts)
    census = store.get(certificate["evidence_sha256"])
    _require(census.get("pilot_selections", []) == getattr(reader, "pilot_selections", []), "pilot_selection_census")
    _require(census.get("prior_diagnostics", []) == getattr(reader, "prior_diagnostics", []), "prior_diagnostic_census")
    events = {row["seq"]: (row, exposure._event(row, certificate["source_head"][0])) for row in reader.events}
    intended = {value["attempt"]: (row, value) for row, value in events.values() if row["kind"] == "model.attempt.intended"}
    _require([row["event_hash"] for row, _ in intended.values()] == census["intent_event_hashes"], "complete_intent_census")
    by_task = {value["task_key"]: attempt for attempt, (_, value) in intended.items()}
    _require(len(by_task) == len(intended), "duplicate_physical_task")
    roles = {entry["attempt"]: set(entry["roles"] or []) for entry in resolved_roles.catalog["attempts"]}
    proofs = {entry["attempt"]: set(entry["evidence_ids"]) for entry in resolved_roles.catalog["attempts"]}
    _require(set(roles) == set(intended), "role_attempt_census")
    responses = {}
    for row in reader.records:
        value = exposure._record(row, events, store)
        if row["kind"] != "cyber_dossier_response":
            continue  # Local revalidation creates no presentation.
        attempt = value["attempt"]
        _require(attempt in intended and attempt not in responses, "response_physical_identity")
        intent = intended[attempt][1]
        _require(all(value[k] == intent[k] for k in ("task_key", "packet", "request", "phase")), "response_intent_binding")
        responses[attempt] = (row, value)
    _require([r["id"] for r in reader.records] == census["record_ids"], "response_census")
    phases = {}
    _require([r["id"] for r in reader.phase_records] == census["phase_record_ids"]
             and [r["event_hash"] for r in reader.phase_events] == census["phase_event_hashes"], "phase_census")
    for row, event in zip(reader.phase_records, reader.phase_events, strict=True):
        value = roles_module._record(row, store, certificate, kind="cyber_dossier_phase")
        created = exposure._event(event, certificate["source_head"][0])
        _require(event["seq"] == row["created_event"] and created == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "phase_event_binding")
        phases[value["name"]] = (row, value, store.get(value["artifact"]))
    gaps, selections = [], []

    def packet(attempt):
        _, intent = intended[attempt]
        value = store.get(intent["packet"])
        _require(value.get("request") == store.get(intent["request"])
                 and digest(value["request"]) == intent["request"]
                 and intent["task_key"] == digest([certificate["plan"], value.get("kind", "decisions"), value["request"]]), "task_wire_binding")
        return value

    def attach(task, role, proof, *, before=None, expected_packet=None, expected_ids=None, binding=None):
        attempt = by_task.get(task)
        if attempt is None:
            selections.append({"task_key": task, "role": role, "state": "prepared_only", "evidence_ids": proof})
            return False
        if before is not None and intended[attempt][0]["seq"] >= before:
            gaps.append({"reason_code": "attempt_postdates_completed_role_phase", "attempt": attempt})
            return False
        value = packet(attempt)
        if expected_packet is not None:
            _require(intended[attempt][1]["packet"] == expected_packet, "selected_packet_identity")
        if expected_ids is not None:
            _require(set(value["document_ids"]) == set(expected_ids), "selected_source_identity")
        if binding is not None:
            _require(all(value.get("bindings", {}).get(k) == v for k, v in binding.items()), "selected_group_version")
        roles[attempt].add(role)
        proofs[attempt].update(proof)
        return True

    # Completed seed use binds selection to a unique earlier actual article set;
    # merely selecting a proposal or later dispatching it does not count.
    seed_sets = {}
    for attempt, (_, intent) in intended.items():
        if intent["phase"] == "seed":
            key = tuple(sorted(packet(attempt)["document_ids"]))
            seed_sets.setdefault(key, []).append(attempt)

    def seed_selection(label, selected, proof):
        completed = phases.get(label + "_seeds")
        if completed is None:
            gaps.append({"reason_code": "pilot_seed_completion_unavailable", "phase": label})
            return
        row, _, result = completed
        _require(result.get("packets") == len(selected), "pilot_seed_packet_count")
        for item in selected:
            ids = item["document_ids"]
            _require(set(ids) <= set(result.get("covered", [])), "pilot_seed_coverage")
            candidates = [a for a in seed_sets.get(tuple(sorted(ids)), []) if intended[a][0]["seq"] < row["created_event"]]
            if len(candidates) != 1:
                gaps.append({"reason_code": "pilot_seed_unique_attempt_unavailable", "document_ids": ids})
                continue
            a = candidates[0]
            attach(intended[a][1]["task_key"], "development", [*proof, row["id"]], before=row["created_event"], expected_ids=ids)

    if "pilot_seeds" in phases and "seed_proposals" in phases:
        row, _, proposals = phases["seed_proposals"]
        selected = sorted(proposals["packets"], key=lambda p: digest(["pilot-seeds-20261023", p["document_ids"]]))[:original.PARAMETERS["pilot_packets"]]
        seed_selection("pilot", selected, [row["id"]])
    for binding in getattr(reader, "pilot_selections", []):
        amendment = store.get(binding["record_artifact"])
        created = exposure._event(binding["creation_event"], certificate["source_head"][0])
        _require(binding["record_id"] == digest({"kind": binding["record_kind"], "key": binding["record_key"],
            "payload": binding["record_artifact"], "supersedes": None}) and binding["creation_event"]["kind"] == "record.created"
            and created == {"record": binding["record_id"], "kind": binding["record_kind"], "artifact": binding["record_artifact"]},
            "pilot_selection_creation_binding")
        _require(binding["record_id"] in certificate["amendments"] and amendment.get("parent_plan") == certificate["plan"]
                 and amendment.get("pilot_selection_artifact") == binding["artifact"], "pilot_amendment_binding")
        selected = store.get(binding["artifact"])
        proof = [binding["record_id"], binding["record_artifact"], binding["artifact"]]
        if binding["record_kind"] in PILOT_LABELS:
            seed_selection(PILOT_LABELS[binding["record_kind"]], selected["packets"], proof)
        if binding["record_kind"] == "cyber_dossier_execution_amendment_v6":
            for part, completed_name in (("primary", "pilot_v6_primary_quality_gate"), ("secondary", "pilot_v6_secondary_finished")):
                if completed_name not in phases:
                    gaps.append({"reason_code": "v6_review_completion_unavailable", "phase": part})
                    continue
                for item in selected[part]:
                    for transport, role in (("luna", "development"), ("astra", "reference")):
                        if part == "secondary" and transport == "luna":
                            continue
                        key, ref = item.get(transport + "_task_key"), item.get(transport + "_packet")
                        if key is not None:
                            _require(ref is not None, "v6_selected_packet_missing")
                            attached = attach(key, role, [*proof, ref, phases[completed_name][0]["id"]],
                                before=phases[completed_name][0]["created_event"], expected_packet=ref,
                                expected_ids=item["document_ids"], binding={k: item[k] for k in ("dossier_id", "membership_revision", "card_version")})
                            if part == "secondary" and attached:
                                roles[by_task[key]].add("diagnostic")

    # Exact pilot v5 group QA/challenge, card-reference and full-member controls.
    challenge, card_phase = phases.get("pilot_v5_positive_challenge"), phases.get("pilot_v5_seed_cards")
    if challenge and card_phase:
        groups = challenge[2]["groups"]
        for attempt, (_, intent) in intended.items():
            if intent["phase"] != "card_quality":
                continue
            value = packet(attempt)
            group = value.get("bindings", {}).get("dossier_id")
            if group in groups and group in card_phase[2].get("quality", {}) and value["bindings"].get("membership_revision") == digest(sorted(groups[group])):
                attach(intent["task_key"], "development", [challenge[0]["id"], card_phase[0]["id"]],
                       before=card_phase[0]["created_event"], expected_ids=groups[group])
    ref_plan = phases.get("pilot_v5_card_quality_reference_plan")
    if ref_plan:
        for item in ref_plan[2]["items"]:
            if item.get("task_key") is not None:
                attach(item["task_key"], "reference", [ref_plan[0]["id"]],
                       binding={k: item[k] for k in ("dossier_id", "card_version")})
    control = phases.get("pilot_v5_full_bundle_control_plan")
    if control:
        _require(control[2].get("diagnostic_only") is True, "control_role_binding")
        for item in control[2]["queries"]:
            for key in item["task_keys"]:
                if key in by_task:
                    value = packet(by_task[key])
                    _require(value["phase"] == "assignment_full_member_control" and value["document_ids"] == [item["document_id"]]
                             and set(value["bindings"]) <= set(item["chosen_dossiers"]), "control_query_membership")
                attach(key, "diagnostic", [control[0]["id"]])

    diagnostic_plans = {}
    for evidence in getattr(reader, "prior_diagnostics", []):
        row, event = evidence["row"], evidence["creation_event"]
        value = roles_module._record(row, store, certificate)
        created = exposure._event(event, certificate["source_head"][0])
        _require(event["seq"] == row["created_event"] and event["kind"] == "record.created" and created == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}
            and value.get("parent_plan") == certificate["plan"], "diagnostic_plan_identity")
        _require(row["kind"] in {"cyber_summary_fidelity_diagnostic_plan", "cyber_summary_fidelity_diagnostic_amendment_v2"},
                 "diagnostic_kind")
        if row["kind"] == "cyber_summary_fidelity_diagnostic_amendment_v2":
            parent = diagnostic_plans.get(value["parent_diagnostic_plan"])
            _require(parent is not None and value["original_tasks"] == parent["tasks"], "diagnostic_parent_frame")
            originals = {t["selection"]["summary_version"]: t for t in parent["tasks"]}
            changed = {t["selection"]["summary_version"]: t for t in value["tasks"]}
            excluded = {t["summary_version"]: t for t in value["excluded_attempts"]}
            _require(len(originals) == len(parent["tasks"]) and len(changed) == len(value["tasks"])
                     and len(excluded) == len(value["excluded_attempts"]) and not set(changed) & set(excluded)
                     and set(changed) | set(excluded) == set(originals), "diagnostic_fixed_frame_partition")
            for version, task in changed.items():
                _require(task["original_packet"] == originals[version]["packet"]
                         and task["original_task_key"] == originals[version]["task_key"]
                         and task["selection"] == originals[version]["selection"], "diagnostic_repair_source_binding")
            for version, excluded_item in excluded.items():
                _require(excluded_item["original_task_key"] == originals[version]["task_key"]
                         and by_task.get(excluded_item["original_task_key"]) == excluded_item["attempt"], "diagnostic_excluded_attempt")
        for task in value["tasks"]:
            selected_packet = store.get(task["packet"])
            _require(selected_packet["phase"] == "summary_fidelity_audit" and selected_packet["kind"] == "responses"
                     and task["task_key"] == digest([certificate["plan"], "responses", selected_packet["request"]])
                     and selected_packet["bindings"]["summary_version"] == task["selection"]["summary_version"], "diagnostic_task_binding")
            attempt = by_task.get(task["task_key"])
            if attempt is not None:
                _require(intended[attempt][1].get("diagnostic_plan") == row["id"]
                         and intended[attempt][0]["seq"] > event["seq"], "diagnostic_intent_plan_binding")
                if attempt in responses:
                    _require(responses[attempt][1].get("diagnostic_plan") == row["id"], "diagnostic_response_plan_binding")
            attach(task["task_key"], "diagnostic", [row["id"], row["artifact"], task["packet"]], expected_packet=task["packet"])
            if attempt is not None:
                roles[attempt].add("reference")
        diagnostic_plans[row["id"]] = value

    observations, unsupported, provenance = [], [], []
    source_id = certificate["source_id"]
    for attempt in sorted(intended):
        if not roles[attempt] & projection.PRIOR_ROLES:
            unsupported.append(attempt)
            continue
        row, intent = intended[attempt]
        value = packet(attempt)
        response = responses.get(attempt)
        envelope = store.get(response[1]["response"], optional=True) if response else None
        try:
            ids, kind, decisions = task_sources(reader.index, value, reader.artifacts)
        except ValueError as error:
            if str(error) not in {"prior_unsupported_task_source_format", "prior_historical_summary_members_unavailable"}:
                raise
            ids, kind, decisions = None, "unavailable", None
            state, evidence_kind = "uncertain", "incomplete_record"
        else:
            state, evidence_kind = serving_evidence(value, envelope, decisions)
        source_binding = {"packet": intent["packet"], "request": intent["request"], "document_ids": ids,
                          "task_key": intent["task_key"], "phase": intent["phase"]}
        evidence_binding = {"intent_event": row["event_hash"], "response_record": response[0]["id"] if response else None,
            "response_artifact": response[1]["response"] if response else None, "state": state, "rule": VERSION}
        provenance.append({"attempt": attempt, "role_evidence_ids": sorted(proofs[attempt]),
                           "source_binding": source_binding, "serving_evidence_binding": evidence_binding})
        observations.append({"event_id": attempt, "origin_source_id": source_id, "source_id": source_id,
            "record_sha256": response[0]["artifact"] if response else row["event_hash"], "roles": sorted(roles[attempt]),
            "role_binding": digest(sorted(proofs[attempt])),
            "task_binding": {"kind": kind, "document_ids": ids, "binding_sha256": digest(source_binding)},
            "evidence": {"state": state, "kind": evidence_kind, "evidence_sha256": digest(evidence_binding)}})
    manifest = {"version": VERSION, "source_id": source_id, "source_head": certificate["source_head"],
        "input_index_digest": reader.index.digest, "census_artifact": certificate["evidence_sha256"],
        "role_catalog_sha256": digest(resolved_roles.catalog), "observations_sha256": digest(observations),
        "normalized_evidence_bindings": provenance,
        "physical_intents": len(intended), "normalized_prior_events": len(observations),
        "unsupported_or_unproven_prior_role_attempts": unsupported, "missing_role_evidence": gaps,
        "unintegrated_or_unproven_prior_role_phase_counts": dict(Counter(intended[a][1]["phase"] for a in unsupported)),
        "summary_fidelity_diagnostic_plan_ids": sorted(diagnostic_plans),
        "explicit_unintegrated_substantive_history": ["ancestor generated-summary and legacy assignment role histories",
            "other recorded study owners and manual/Codex substantive reviews"],
        "prepared_only_selections": selections, "evidence_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "role_claims_are_positive_evidence_not_exhaustive_history": True,
        "main_owner_prior_inventory_complete": False, "cross_owner_or_manual_history_reconciled": False,
        "new_model_calls": 0, "new_physical_exposures": 0, "creates_pair_labels": False,
        "limitations": "Unsupported ancestor summary/assignment/review formats and missing role evidence remain unresolved. Separate recorded owners and substantive manual/Codex review inventories are still required. Semantic-invalid output may establish acknowledged exposure; these are not reusable reference judgments."}
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(certificate["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(source_id, o["event_id"]) for o in observations], "inventory_sha256": digest(manifest)}
    return MainOwnerPrior(tuple(observations), contribution, manifest)
