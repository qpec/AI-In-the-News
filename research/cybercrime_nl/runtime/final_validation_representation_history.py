"""Bounded historical representation-reference batches, never current pair Y.

Pure consumer of verified HistoryOwner readers. One conversational reference
batch contains sixty logical pairs; its original physical identity is never
expanded into sixty invented attempts. The existing single-pair history schema
cannot ingest this batch, so exact logical maps accompany a conservative endpoint
gap certificate until a separate logical-subtask resolver is reviewed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import sys

import final_validation_legacy_pair_history as pairs
import final_validation_legacy_prior as prior
import final_validation_projection as projection
from newsresearch import luna_speed_provider as speed
from newsresearch.common import digest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "workbench"))
import run_luna_representation_comparison as native  # noqa: E402

VERSION = "final-validation-representation-reference-history-v1"
FAMILY = native.METHOD
ROLE_POLICY = {"version": "named-representation-reference-batch-primary-blockers-v1",
    "family": FAMILY, "historical_role": "conversational_full_source_pair_reference_batch",
    "final_validation_role": "primary", "current_reference_compatible": False,
    "experimental_arms_are_reference_attempts": False}


def require(value, code):
    if not value:
        raise ValueError("representation_history_" + code)


def same(a, b):
    return digest(a) == digest(b)


def implementation():
    paths = (Path(__file__), Path(native.__file__), Path(native.core.__file__), Path(native.contract.__file__), Path(speed.__file__))
    return {**pairs.implementation(), **native.implementation(), **{
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _path(value):
    require(isinstance(value, str) and value, "owner_path")
    return os.path.normcase(os.path.abspath(value))


def _plan(row, plan, rows, store):
    versions = plan.get("versions")
    require(row["logical_key"] == FAMILY and isinstance(versions, dict) and set(versions) == {
        "protocol", "question", "selection", "dossier_definition", "codebook", "prompt", "profile", "policy"}, "plan_versions")
    if any(identity not in rows for identity in versions.values()):
        return None
    selected = [rows[identity] for identity in versions.values()]
    require(all(r["kind"] == kind and r["logical_key"] == FAMILY and r["created_event"] < row["created_event"]
                for kind, identity in versions.items() for r, _ in [rows[identity]]), "version_binding")
    content = {r["kind"]: value["content"] for r, value in selected}
    require(same(plan.get("implementation"), native.implementation()) and content["protocol"].get("method") == FAMILY
        and same(content["protocol"].get("implementation"), plan["implementation"])
        and content["prompt"] == {"instructions": native.core.RULES, "reference_instructions": native.core.REFERENCE_RULES}
        and content["codebook"] == {"labels": list(native.transport.LABELS), "definitions": native.core.REFERENCE_RULES}, "registered_native_contract")
    values = {k: store.get(plan[k], optional=True) for k in ("panels", "views", "cards", "manifest")}
    if any(value is None for value in values.values()):
        return None
    panels, views, cards, manifest = (values[k] for k in ("panels", "views", "cards", "manifest"))
    mapping = plan.get("mapping")
    require(isinstance(panels, list) and len(panels) == 10 and isinstance(mapping, list) and len(mapping) == 10
        and all(type(p.get("panel")) is int for p in panels + mapping)
        and [p["panel"] for p in panels] == [p["panel"] for p in mapping] == list(range(1, 11)), "panel_frame")
    require(isinstance(cards, list) and len(cards) == 40 and isinstance(views, dict) and len(views) == 40, "card_frame")
    card_map = {card["article_id"]: card for card in cards}
    require(len(card_map) == 40 and set(card_map) == set(views), "unique_card_frame")
    mapped = []
    for panel, entry in zip(panels, mapping, strict=True):
        require(set(panel) == {"panel", "cards"} and set(entry["cards"]) == set("ABCD")
            and entry["split"] in {"development", "test"}, "panel_mapping")
        mapped.extend(entry["cards"].values())
        require(all(identifier in views for identifier in entry["cards"].values()), "mapped_card_missing")
        expected = [{"side": side, **views[entry["cards"][side]]["article"]} for side in "ABCD"]
        require(same(panel["cards"], expected) and all(card_map[i]["corpus"] == entry["corpus"] for i in entry["cards"].values()), "panel_view_identity")
    require(len(set(mapped)) == 40 and set(mapped) == set(card_map), "complete_disjoint_panel_mapping")
    require(isinstance(manifest, list) and len(manifest) == 180, "arm_frame")
    task_map = {}
    for task in manifest:
        require(set(task) == {"pair_id", "panel", "split", "a", "b", "arm", "request", "wire_bytes"}
            and type(task["panel"]) is int and 1 <= task["panel"] <= 10
            and (task["a"], task["b"]) in set(combinations("ABCD", 2)) and task["arm"] in native.core.ARMS, "arm_task")
        entry = mapping[task["panel"] - 1]
        a, b = (entry["cards"][task[k]] for k in ("a", "b"))
        expected = native.core.request(views[a][task["arm"]], views[b][task["arm"]])
        request = store.get(task["request"], optional=True)
        if request is None:
            return None
        require(same(request, expected) and task["pair_id"] == digest([FAMILY, entry["corpus"], a, b])
            and task["split"] == entry["split"] and type(task["wire_bytes"]) is int
            and task["wire_bytes"] == len(native.canonical(expected).encode()), "arm_wire_binding")
        key = digest([task["pair_id"], task["arm"]])
        require(key not in task_map, "duplicate_arm")
        task_map[key] = task
    require({(t["panel"], t["a"], t["b"], t["arm"]) for t in manifest} == {
        (p, a, b, arm) for p in range(1, 11) for a, b in combinations("ABCD", 2) for arm in native.core.ARMS}, "arm_cartesian_coverage")
    base = content["selection"].get("base")
    require(content["selection"].get("parent") == native.PARENT and isinstance(base, str), "declared_parent")
    return {**values, "row": row, "plan": plan, "versions": selected, "card_map": card_map,
            "task_map": task_map, "standard_path": _path(str(Path(base) / native.STANDARD))}


def _sources(prepared, standard_owner):
    """Verify exact retained full inputs, not a card's body hash or corpus label."""
    result, gaps = {}, []
    if standard_owner is None:
        return {i: None for i in prepared["card_map"]}, [{"reason_code": "standard_owner_unavailable", "article_ids": sorted(prepared["card_map"])}]
    require(_path(standard_owner.scope["source_owner"]) == prepared["standard_path"], "declared_standard_owner")
    store, _, rows, _ = prior._owner(standard_owner)
    for identifier, card in prepared["card_map"].items():
        provenance = card.get("provenance")
        require(isinstance(provenance, list) and len({p["assessment"] for p in provenance}) == len(provenance), "card_provenance")
        by_assessment = {p["assessment"]: p for p in provenance}
        records = [r for r in card["records"] if r["mechanically_usable"]]
        require(card["readiness"] == "ready" and records, "card_readiness")
        packets, source_versions, evidence, missing = {}, [], [], False
        for record in records:
            p = by_assessment.get(record["extraction_id"])
            require(p is not None and _path(p["owner"]) == prepared["standard_path"], "card_original_owner")
            assessment = rows.get(p["assessment"])
            request = store.get(p["request"], optional=True)
            if assessment is None or request is None:
                missing = True
                continue
            ar, av = assessment
            require(ar["kind"] == "luna_standard_assessment" and av.get("request") == p["request"]
                and av.get("response") == p["response"] and av.get("custom_id") == p.get("custom_id")
                and av.get("corpus_id") == card["corpus"] and request.get("attempt") == av.get("attempt")
                and request.get("task_key") == av.get("task_key"), "original_assessment_request")
            speed.validate_request(request)
            packet = request["packet"]
            fields = packet["source_map"]["source_fields"]
            title, body = fields["title"]["text"], fields["body"]["text"]
            require(isinstance(title, str) and isinstance(body, str) and card["body_sha256"] == hashlib.sha256(body.encode()).hexdigest()
                and av["descriptor"]["retained_body_sha256"] == card["body_sha256"], "original_body_binding")
            if record["view"] == "raw":
                response = store.get(p["response"], optional=True)
                if response is None:
                    missing = True
                    continue
                output = response.get("payload")
                require(av.get("status") == "valid", "raw_assessment_status")
            else:
                require(record["view"] == "literal_reference_projection" and av.get("derived_status") == "valid", "derived_assessment_status")
                output = av.get("projection", {}).get("derived_output")
            require(same(record["output"], output) and digest(output) == record["output_sha256"], "saved_output_binding")
            packets[record["extraction_id"]] = packet
            source_versions.append({"title_sha256": hashlib.sha256(title.encode()).hexdigest(),
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "input_sha256": digest({"title": title, "body": body})})
            evidence.append({"assessment_record": ar["id"], "assessment_created_event": ar["created_event"],
                "request_artifact": p["request"], "response_artifact": p["response"], "source_map_sha256": digest(packet["source_map"])})
        if missing:
            result[identifier] = None
            gaps.append({"reason_code": "original_source_or_variant_evidence_unavailable", "article_ids": [identifier]})
            continue
        require(source_versions and all(same(v, source_versions[0]) for v in source_versions), "full_source_variant_conflict")
        reconstructed = native.core.views(card, packets)
        require(same(reconstructed, prepared["views"][identifier]), "saved_representation_views")
        result[identifier] = {**source_versions[0], "legacy_article_id": identifier,
            "standard_source_id": standard_owner.census["owner_sha256"], "standard_head": standard_owner.scope["source_head"],
            "original_evidence": evidence, "full_retained_source_proven": True}
    return result, gaps


def _reply(prepared, intent, intent_row, events, rows, store):
    empty = {"record": None, "response": None, "substantive_slots": set(), "events": [], "read_bindings": [], "inspected_panels": set()}
    matches = [(r, v) for r, v in rows.values() if r["kind"] == "representation_references" and v.get("plan") == prepared["row"]["id"]]
    require(len(matches) <= 1, "multiple_reference_submissions")
    if not matches:
        return empty
    row, value = matches[0]
    require(row["logical_key"] == FAMILY
        and set(value) == {"plan", "replies", "response", "human_validated"}, "reference_submission_binding")
    # Native submit selects the unique saved handoff. A prior orphan intent with
    # identical plan/request must not inherit the later attempt's review.
    handoffs = [(r, v) for r, v in rows.values()
        if r["kind"] == "representation_handoff" and r["logical_key"] == FAMILY]
    require(len(handoffs) <= 1, "multiple_reference_handoffs")
    completed = [(r, v) for r, v in events.values() if r["kind"] == "model.attempt.completed"
        and (v.get("assessment") == row["id"] or v.get("attempt") == intent["attempt"])]
    if not handoffs:
        return empty
    handoff_row, handoff = handoffs[0]
    require(handoff.get("batch") == prepared["row"]["id"] and handoff.get("task_key") == prepared["row"]["id"]
        and handoff_row["created_event"] < row["created_event"], "submission_handoff_binding")
    require(len(completed) <= 1 and all(v.get("attempt") == handoff.get("attempt")
        and v.get("assessment") == row["id"] and v.get("response") == value["response"]
        and v.get("status") == "valid" and r["seq"] > row["created_event"] for r, v in completed),
        "reference_completion_binding")
    if handoff.get("attempt") != intent["attempt"]:
        return empty
    require(same(handoff, intent) and intent_row["seq"] < handoff_row["created_event"], "reference_handoff_owner")
    response = store.get(value["response"], optional=True)
    slots, seen = set(), set()
    if response is not None:
        require(response.get("provider") == "codex-current-conversation" and response.get("model") is None
            and response.get("request_id") is None and response.get("usage") is None
            and isinstance(response.get("raw_response"), str), "reference_response_envelope")
        raw = json.loads(response["raw_response"])
        require(same(raw, value["replies"]) and same(response.get("payload"), raw), "exact_submitted_reply")
        require(isinstance(raw, list), "reference_reply_list")
        for reply in raw:
            require(isinstance(reply, dict) and set(reply) == {"panel", "a", "b", "label", "rationale", "evidence_a", "evidence_b"}
                and type(reply["panel"]) is int and 1 <= reply["panel"] <= 10
                and (reply["a"], reply["b"]) in set(combinations("ABCD", 2)), "reply_slot_identity")
            key = (reply["panel"], reply["a"], reply["b"])
            require(key not in seen, "duplicate_reply_slot")
            seen.add(key)
            if isinstance(reply["rationale"], str) and reply["rationale"].strip():
                slots.add(key)
    inspected, bindings, used = set(), [], list(completed)
    for er, ev in events.values():
        if er["kind"] != "representation.inspected" or ev.get("request") != intent["request"]:
            continue
        same_session = [(r, v) for r, v in events.values() if r["session_id"] == er["session_id"]]
        before = [(r, v) for r, v in same_session if r["kind"] == "operation.intended"]
        after = [(r, v) for r, v in same_session if r["kind"] == "operation.completed"]
        if len(before) != 1 or len(after) != 1:
            continue
        br, bv = before[0]
        ar, av = after[0]
        request, result = store.get(bv["input"], optional=True), store.get(av["result"], optional=True)
        if request is None or result is None:
            continue
        require(bv.get("operation") == av.get("operation") == "status" and request.get("action") == "read"
            and type(request.get("start")) is int and type(request.get("end")) is int
            and handoff_row["created_event"] < br["seq"] < er["seq"] < ar["seq"], "read_chronology")
        panels = [p for p in prepared["panels"] if request["start"] <= p["panel"] <= request["end"]]
        require(same(ev, {"request": intent["request"], "panels": [p["panel"] for p in panels]})
            and same(result, {"instructions": native.core.REFERENCE_RULES, "panels": panels}), "exact_panel_return")
        prior_to_reply = ar["seq"] < row["created_event"]
        if prior_to_reply:
            inspected.update(p["panel"] for p in panels)
        bindings.append({"read_input": bv["input"], "read_result": av["result"], "inspection_event": er["event_hash"],
            "panels": [p["panel"] for p in panels], "before_submission": prior_to_reply, "attention_or_ui_delivery_proven": False})
        used.extend([before[0], (er, ev), after[0]])
    return {"record": matches[0], "response": value["response"] if response is not None else None,
        "substantive_slots": slots, "events": used, "read_bindings": bindings, "inspected_panels": inspected}


@dataclass(frozen=True)
class RepresentationHistory:
    observations: tuple
    source_contribution: dict
    pair_attempt_bindings: tuple
    inventory_certificate: dict
    manifest: dict


def normalize_representation_history(owner, index, *, origin_owner, standard_owner):
    """Consume fixed-cutoff readers; native/copy origin declarations stay upstream."""
    store, events, rows, intents = prior._owner(owner)
    plans = {r["id"]: _plan(r, value, rows, store) for r, value in rows.values() if r["kind"] == "representation_plan"}
    known = {i.input_sha256: i.document_id for i in index.inputs}
    require(len(known) == len(index.inputs), "unique_input_frame")
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner is not None else None
    sources, source_gaps = {}, []
    for identity, prepared in plans.items():
        if prepared:
            sources[identity], missing = _sources(prepared, standard_owner)
            source_gaps.extend({"plan_record": identity, **g} for g in missing)
    batches, arms, pair_bindings, observations, gaps, prepared_only = [], [], [], [], [], []
    occupied, scope_inputs, global_gap = set(), set(), False
    for attempt, (er, intent) in intents.items():
        prepared = plans.get(intent.get("batch"))
        if not prepared:
            gaps.append({"reason_code": "unsupported_physical_intent", "attempt": attempt, "input_sha256": None})
            global_gap = True
            continue
        plan, pr = prepared["plan"], prepared["row"]
        request, dispatch = (store.get(intent[k], optional=True) for k in ("request", "dispatch"))
        require(type(intent.get("number")) is int and intent["number"] == 1 and pr["created_event"] < er["seq"], "physical_intent_binding")
        if intent.get("task_key") == pr["id"]:
            occupied.add(pr["id"])
            if request is None or dispatch is None:
                gaps.append({"reason_code": "reference_request_unavailable", "attempt": attempt, "input_sha256": None})
                global_gap = True
                continue
            expected = {"instructions": native.core.REFERENCE_RULES, "panels": prepared["panels"]}
            require(same(request, expected) and same(dispatch, native.Invocation(request).manifest()), "reference_wire")
            handoffs = [(r, v) for r, v in rows.values() if r["kind"] == "representation_handoff" and v.get("attempt") == attempt]
            require(len(handoffs) <= 1 and all(r["logical_key"] == FAMILY and same(v, intent) for r, v in handoffs), "reference_handoff")
            selected_rows = [(pr, plan), *prepared["versions"], *handoffs]
            refs = {intent["request"], intent["dispatch"], *(plan[k] for k in ("panels", "views", "cards", "manifest"))}
            origin_ok = origin_owner is owner or pairs._origin_matches(origin_owner, owner, selected_rows, [(er, intent)], refs)
            reply = _reply(prepared, intent, er, events, rows, store)
            reply_origin = origin_ok
            if reply["record"] and origin_owner is not owner:
                reply_refs = ({reply["response"]} if reply["response"] else set()) | {ref for b in reply["read_bindings"] for ref in (b["read_input"], b["read_result"])}
                reply_origin = pairs._origin_matches(origin_owner, owner, [reply["record"]], reply["events"], reply_refs)
            acknowledged, matched = set(), set()
            batch_slots = []
            for mapping in plan["mapping"]:
                for a, b in combinations("ABCD", 2):
                    identities = [sources[pr["id"]][mapping["cards"][side]] for side in (a, b)]
                    hashes = sorted({v["input_sha256"] for v in identities if v and v["input_sha256"] in known})
                    matched.update(known[h] for h in hashes)
                    # A single missing endpoint is bounded by its known partner;
                    # two missing endpoints leave the pair location unbounded.
                    if any(v is None for v in identities):
                        if len(hashes) or not any(identities):
                            gaps.append({"reason_code": "pair_endpoint_unavailable", "attempt": attempt,
                                "panel": mapping["panel"], "sides": [a, b], "input_sha256": hashes or None})
                            scope_inputs.update(hashes)
                            global_gap |= not hashes
                    elif len(hashes) == 2:
                        scope_inputs.update(hashes)
                    slot = {"plan_record": pr["id"], "panel": mapping["panel"], "a": a, "b": b}
                    binding = {"original_attempt": attempt, "original_owner_source_id": origin_id if origin_ok else None,
                        "physical_id": digest([origin_id, attempt]) if origin_ok else None,
                        "origin_verified": bool(origin_ok), "logical_slot": slot, "logical_slot_id": digest(slot),
                        "source_identities": identities, "matched_input_sha256": hashes,
                        "request_artifact": intent["request"], "dispatch_artifact": intent["dispatch"],
                        "role_policy": ROLE_POLICY, "current_reference_compatible": False, "creates_pair_y": False}
                    pair_bindings.append(binding)
                    batch_slots.append(binding["logical_slot_id"])
                    if reply_origin and mapping["panel"] in reply["inspected_panels"] and (mapping["panel"], a, b) in reply["substantive_slots"]:
                        acknowledged.update(known[h] for h in hashes)
            if not origin_ok:
                affected = sorted({h for p in pair_bindings if p["original_attempt"] == attempt for h in p["matched_input_sha256"]})
                gaps.append({"reason_code": "physical_origin_unverified", "attempt": attempt, "input_sha256": affected or None})
                scope_inputs.update(affected)
                global_gap |= not affected
            evidence = {"intent_event": er["event_hash"], "handoff_records": [r["id"] for r, _ in handoffs],
                "reference_record": reply["record"][0]["id"] if reply["record"] else None,
                "response_artifact": reply["response"], "read_bindings": reply["read_bindings"],
                "acknowledged_document_ids": sorted(acknowledged), "attention_or_full_read_proven": False}
            batches.append({"original_attempt": attempt, "plan_record": pr["id"], "origin_verified": bool(origin_ok),
                "physical_id": digest([origin_id, attempt]) if origin_ok else None,
                "logical_pair_slots": batch_slots, "matched_document_ids": sorted(matched), "evidence": evidence})
            if origin_ok and matched:
                ids = sorted(acknowledged or matched)
                observations.append({"event_id": attempt, "origin_source_id": origin_id, "source_id": source_id,
                    "record_sha256": reply["response"] or er["event_hash"], "roles": ["reference", "substantive_review"],
                    "role_binding": digest({"policy": ROLE_POLICY, "plan": pr["id"]}),
                    "task_binding": {"kind": "multiarticle", "document_ids": ids, "binding_sha256": digest(batch_slots)},
                    "evidence": {"state": "acknowledged" if acknowledged else "uncertain",
                        "kind": "substantive_review_record" if acknowledged else "incomplete_record", "evidence_sha256": digest(evidence)}})
        else:
            task = prepared["task_map"].get(intent.get("task_key"))
            if task is None or request is None or dispatch is None:
                gaps.append({"reason_code": "unresolved_experimental_or_other_intent", "attempt": attempt, "input_sha256": None})
                global_gap = True
                continue
            require(intent["request"] == task["request"] and same(dispatch, native.transport.Invocation(request, attempt).manifest())
                and intent.get("reserved_nanousd") == plan["reservation_nanousd"], "experimental_arm_wire")
            origin_ok = origin_owner is owner or pairs._origin_matches(origin_owner, owner,
                [(pr, plan), *prepared["versions"]], [(er, intent)],
                {intent["request"], intent["dispatch"], plan["manifest"]})
            arms.append({"original_attempt": attempt, "plan_record": pr["id"], "task_key": intent["task_key"],
                "origin_verified": bool(origin_ok), "original_owner_source_id": origin_id if origin_ok else None,
                "physical_id": digest([origin_id, attempt]) if origin_ok else None,
                "panel": task["panel"], "sides": [task["a"], task["b"]], "arm": task["arm"],
                "request_artifact": intent["request"], "dispatch_artifact": intent["dispatch"],
                "purpose": "experimental_decision_comparison", "pair_reference_attempt": False,
                "P_acknowledgement_normalized": False})
    for identity, prepared in plans.items():
        if prepared and identity not in occupied:
            prepared_only.append({"plan_record": identity, "logical_pairs": 60, "physical_attempt_created": False})
    manifest = {"version": VERSION, "family": FAMILY, "implementation": implementation(), "role_policy": ROLE_POLICY,
        "source_id": source_id, "source_head": owner.scope["source_head"], "scope_sha256": digest(owner.scope),
        "history_census_sha256": digest(owner.census), "input_index_digest": index.digest,
        "reference_batches": batches, "experimental_arms": arms, "prepared_only": prepared_only,
        "source_evidence_gaps": source_gaps, "unresolved_evidence": gaps, "inherited_inventory_gaps": deepcopy(owner.gaps),
        "physical_intents": len(intents), "reference_physical_batches": len(batches), "logical_pair_bindings": len(pair_bindings),
        "pair_attempt_bindings_sha256": digest(pair_bindings), "observations_sha256": digest(observations),
        "P_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "whole_study_history_complete": False, "records_for_single_pair_history_schema": [],
        "requires_logical_subtask_resolver": True, "endpoint_certificate_overblocks_unrelated_pairs": True,
        "creates_pair_y": False, "model_calls": 0, "source_mutations": 0,
        "limitations": "One declared family only. Original full retained title/body and saved representations are verified mechanically; archive/webpage fidelity remains upstream. One batch is one physical attempt with multiple logical pairs. Existing certificate conservatively blocks pairs incident to matched endpoints until logical-subtask integration; it is not a complete historical discovery certificate. Experimental-arm prior exposure remains unnormalized. Exact retained reads and replies establish only recorded source exposure, not attention or current reference correctness."}
    # Other scopes remain explicitly pending, but do not turn this bounded
    # contribution into a fictitious all-global outcome by its family name.
    certificate = {"binding_sha256": digest(manifest), "complete": False,
        "unknown_input_sha256": sorted(scope_inputs), "global_gap": bool(global_gap or owner.gaps)}
    if not certificate["unknown_input_sha256"] and not certificate["global_gap"]:
        certificate["complete"] = True  # This contribution only; never the study.
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(owner.scope["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(o["origin_source_id"], o["event_id"]) for o in observations],
        "inventory_sha256": digest(manifest)}
    return RepresentationHistory(tuple(observations), contribution, tuple(pair_bindings), certificate, manifest)
