"""Exact old card-pair review history; no current pair labels or owner I/O.

Consumes verified HistoryOwner readers. The 24-pair conversational batch remains
one physical attempt. Complete retained title/body identity establishes which
input a card represents, not that its source article was read. Recorded card
inspection plus substantive submission can establish card-scope prior exposure.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import final_validation_legacy_pair_history as pairs
import final_validation_legacy_prior as prior
import final_validation_projection as projection
import final_validation_representation_history as source_proof
from newsresearch.common import canonical, digest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "workbench"))
import luna_matching_pilot as pilot  # noqa: E402
import review_luna_matching_pilot as native  # noqa: E402

VERSION = "final-validation-matching-card-reference-history-v1"
FAMILY = native.METHOD
ROLE_POLICY = {"version": "named-matching-card-reference-batch-primary-blockers-v1",
    "family": FAMILY, "historical_role": "conversational_card_pair_reference_batch",
    "final_validation_role": "primary", "infers_qc_or_adjudication": False,
    "current_reference_compatible": False, "experimental_decisions_are_references": False}
QUOTAS = (("rank_1_3", 8), ("rank_4_20", 8), ("rank_21_50", 4), ("random_ready", 4))


def require(value, code):
    if not value:
        raise ValueError("matching_history_" + code)


def same(left, right):
    return digest(left) == digest(right)


def implementation():
    contract = source_proof.speed.contract
    paths = (Path(__file__), Path(native.__file__), *pilot.legacy.contract_files(),
        contract.PROMPT_PATH, contract.SCHEMA_PATH,
        Path(contract.__file__).with_name("structured_article_input.py"))
    return {**source_proof.implementation(), **pilot.implementation(), **{
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _versions(rows, identities, family, before, kinds):
    require(isinstance(identities, dict) and set(identities) == set(kinds), "registered_version_kinds")
    if any(i not in rows for i in identities.values()):
        return None
    selected = [rows[i] for i in identities.values()]
    require(all(r["kind"] == kind and r["logical_key"] == family and r["created_event"] < before
        for kind, identity in identities.items() for r, _ in [rows[identity]]), "registered_version_identity")
    return selected, {r["kind"]: value["content"] for r, value in selected}


def _pilot(owner, plan_id):
    if owner is None:
        return None
    store, events, rows, intents = prior._owner(owner)
    if plan_id not in rows:
        return None
    row, plan = rows[plan_id]
    require(row["kind"] == "luna_matching_pilot_plan" and row["logical_key"] == pilot.METHOD
        and plan.get("method") == pilot.METHOD, "parent_plan_identity")
    versions = _versions(rows, plan.get("versions"), pilot.METHOD, row["created_event"],
        ("protocol", "question", "selection", "dossier_definition", "codebook", "prompt", "profile", "policy"))
    if versions is None:
        return None
    selected, content = versions
    require(same(plan.get("implementation"), pilot.implementation())
        and content["protocol"].get("method") == pilot.METHOD
        and same(content["protocol"].get("implementation"), plan["implementation"])
        and content["prompt"] == {"instructions": pilot.matching.RULES}
        and content["codebook"] == {"labels": list(pilot.matching.LABELS)}
        and content["selection"].get("seed") == pilot.SEED, "parent_native_contract")
    values = {k: store.get(plan[k], optional=True) for k in ("cards", "manifest", "selected_provenance")}
    if any(v is None for v in values.values()):
        return None
    cards = {c["article_id"]: c for c in values["cards"]}
    require(len(cards) == len(values["cards"]) and len(values["manifest"]) <= pilot.PAIR_CAP, "parent_card_task_frame")
    tasks = {}
    for task in values["manifest"]:
        require(task["left"] in cards and task["right"] in cards and task["pair_id"] not in tasks, "parent_task_endpoints")
        left, right = cards[task["left"]], cards[task["right"]]
        wire = store.get(task["request"], optional=True)
        if wire is None:
            return None
        expected = pilot.matching.make_request(left, right)
        require(same(wire, expected) and task["pair_id"] == pilot.matching.pair_key(left, right)
            and task["corpus"] == left["corpus"] == right["corpus"]
            and type(task["wire_bytes"]) is int and task["wire_bytes"] == len(canonical(expected).encode())
            and task["rules_label"] == pilot.matching.classify_rules(left, right), "parent_task_wire")
        tasks[task["pair_id"]] = task
    return {"owner": owner, "store": store, "events": events, "rows": rows, "intents": intents,
        "row": row, "plan": plan, "versions": selected, "cards": cards, "tasks": tasks, **values,
        "card_map": cards, "standard_path": source_proof._path(str(Path(content["selection"]["base"]) / pilot.STANDARD))}


def _sources(parent, standard_owner):
    """Reconstruct newly sampled cards through their original Standard requests.

    Inherited earlier cards lack selected_provenance and deliberately remain
    unknown here; a body digest alone cannot locate an exact title/body input.
    """
    result, gaps = {}, []
    if standard_owner is None:
        return {i: None for i in parent["card_map"]}, [{"reason_code": "standard_owner_missing"}]
    require(source_proof._path(standard_owner.scope["source_owner"]) == parent["standard_path"], "declared_standard_owner")
    store, events, rows, _ = prior._owner(standard_owner)
    snapshot = parent["plan"].get("standard_snapshot")
    require(isinstance(snapshot, dict) and set(snapshot) == {"seq", "event_hash"}
        and type(snapshot["seq"]) is int, "standard_snapshot_shape")
    if snapshot["seq"] not in events:
        return {i: None for i in parent["card_map"]}, [{"reason_code": "standard_snapshot_event_unavailable"}]
    require(events[snapshot["seq"]][0]["event_hash"] == snapshot["event_hash"], "standard_snapshot_binding")
    provenance = parent["selected_provenance"]
    require(isinstance(provenance, list) and len({p["assessment"] for p in provenance}) == len(provenance), "unique_source_provenance")
    by_assessment = {p["assessment"]: p for p in provenance}
    for identifier, card in parent["card_map"].items():
        selected = [by_assessment.get(r["extraction_id"]) for r in card["records"]]
        if not selected or any(p is None for p in selected):
            result[identifier] = None
            gaps.append({"reason_code": "inherited_or_missing_card_provenance", "article_id": identifier})
            continue
        variants, identities, evidence, incomplete = [], [], [], False
        for p in selected:
            require(source_proof._path(p["source_owner"]) == parent["standard_path"]
                and isinstance(p["identity"], list) and len(p["identity"]) == 3
                and p["identity"][0] == card["corpus"] and p["identity"][2] == card["body_sha256"]
                and identifier == digest([pilot.METHOD, tuple(p["identity"])]), "card_origin_identity")
            assessment = rows.get(p["assessment"])
            request, response = store.get(p["request"], optional=True), store.get(p["response"], optional=True)
            if assessment is None or request is None or response is None:
                incomplete = True
                continue
            ar, av = assessment
            require(ar["kind"] == "luna_standard_assessment" and ar["created_event"] <= snapshot["seq"]
                and av.get("request") == p["request"] and av.get("response") == p["response"]
                and av.get("corpus_id") == p["identity"][0] and av.get("custom_id") == p["identity"][1]
                and av.get("descriptor", {}).get("retained_body_sha256") == p["identity"][2]
                and request.get("attempt") == av.get("attempt") and request.get("task_key") == av.get("task_key"), "standard_assessment_binding")
            source_proof.speed.validate_request(request)
            fields = request["packet"]["source_map"]["source_fields"]
            title, body = fields["title"]["text"], fields["body"]["text"]
            require(hashlib.sha256(body.encode()).hexdigest() == card["body_sha256"], "original_body_identity")
            identities.append({"input_sha256": digest({"title": title, "body": body}),
                "title_sha256": hashlib.sha256(title.encode()).hexdigest(), "body_sha256": card["body_sha256"]})
            variants.append({"assessment": ar["id"], "raw_status": av["status"], "derived_status": av["derived_status"],
                "raw_output": response.get("payload"), "output": av.get("projection", {}).get("derived_output")})
            evidence.append({"assessment_record": ar["id"], "request_artifact": p["request"], "response_artifact": p["response"],
                "source_map_sha256": digest(request["packet"]["source_map"])})
        if incomplete:
            result[identifier] = None
            gaps.append({"reason_code": "original_source_artifact_unavailable", "article_id": identifier})
            continue
        require(identities and all(same(i, identities[0]) for i in identities), "full_source_variant_conflict")
        rebuilt = pilot.legacy.make_card(article_id=identifier, corpus=card["corpus"], published_at=None,
            body_sha256=card["body_sha256"], variants=variants)
        require(same(rebuilt, card), "exact_original_card_projection")
        result[identifier] = {**identities[0], "legacy_article_id": identifier, "full_retained_source_identity_proven": True,
            "standard_source_id": standard_owner.census["owner_sha256"], "standard_snapshot": snapshot, "original_evidence": evidence}
    return result, gaps


def _reference(intent, er, request, dispatch, rows, parent):
    versions = _versions(rows, request.get("versions"), FAMILY, er["seq"],
        ("protocol", "question", "selection", "prompt", "profile", "codebook"))
    if versions is None:
        return None
    selected, content = versions
    require(content["protocol"].get("method") == FAMILY
        and content["protocol"].get("implementation_sha256") == hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()
        and content["prompt"] == {"instructions": native.RULES}
        and content["codebook"] == {"labels": sorted(native.LABELS)}
        and content["selection"].get("seed") == FAMILY, "reference_native_contract")
    tasks = []
    for stratum, quota in QUOTAS:
        pool = sorted((t for t in parent["manifest"] if t["stratum"] == stratum), key=lambda t: digest([FAMILY, t["pair_id"]]))
        tasks.extend(pool[:quota])
    pairs_out, mapping = [], []
    for number, task in enumerate(tasks, 1):
        wire = parent["store"].get(task["request"])
        pairs_out.append({"number": number, "cards": json.loads(wire["input"])})
        mapping.append({"number": number, **{k: task[k] for k in ("pair_id", "stratum", "request", "rules_label")}})
    expected = {"instructions": native.RULES, "versions": request["versions"], "pairs": pairs_out,
        "response_fields": ["number", "label", "rationale", "evidence_a", "evidence_b"]}
    require(same(request, expected) and same(intent.get("mapping"), mapping)
        and same(dispatch, native.Invocation(request).manifest())
        and type(intent.get("paid_api_calls")) is int and intent["paid_api_calls"] == 0, "exact_reference_request")
    return {"versions": selected, "tasks": tasks, "pairs": pairs_out}


def _review(intent, er, request, events, rows, store):
    empty = {"row": None, "response": None, "events": [], "read_bindings": [], "acknowledged_numbers": set()}
    handoffs = [(r, v) for r, v in rows.values() if r["kind"] == "luna_pilot_reference_handoff" and r["logical_key"] == FAMILY]
    require(len(handoffs) <= 1, "multiple_handoffs")
    if not handoffs:
        return empty
    hr, handoff = handoffs[0]
    if handoff.get("attempt") != intent["attempt"]:
        return empty
    require(same(handoff, intent) and hr["created_event"] > er["seq"], "physical_handoff_binding")
    found = [(r, v) for r, v in rows.values() if r["kind"] == "luna_pilot_reference_result" and v.get("request") == intent["request"]]
    require(len(found) <= 1, "multiple_reference_results")
    if not found:
        return empty
    rr, value = found[0]
    require(rr["logical_key"] == FAMILY and rr["created_event"] > hr["created_event"]
        and set(value) == {"request", "response", "replies", "human_validated", "source_articles_inspected"}
        and value["human_validated"] is False and value["source_articles_inspected"] is False, "reference_result_binding")
    completions = [(r, v) for r, v in events.values() if r["kind"] == "model.attempt.completed"
        and (v.get("attempt") == intent["attempt"] or v.get("assessment") == rr["id"])]
    require(len(completions) <= 1 and all(v.get("attempt") == intent["attempt"] and v.get("assessment") == rr["id"]
        and v.get("response") == value["response"] and v.get("status") == "valid" and r["seq"] > rr["created_event"]
        for r, v in completions), "reference_completion_binding")
    response = store.get(value["response"], optional=True)
    if response is None:
        return empty
    require(response.get("provider") == "codex-current-conversation" and response.get("model") is None
        and response.get("request_id") is None and response.get("usage") is None
        and isinstance(response.get("raw_response"), str), "reference_response_envelope")
    raw = json.loads(response["raw_response"])
    require(same(raw, value["replies"]) and same(raw, response.get("payload")) and isinstance(raw, list), "exact_submitted_reply")
    by_number = {p["number"]: p for p in request["pairs"]}
    substantive, seen = set(), set()
    for reply in raw:
        require(isinstance(reply, dict) and set(reply) == {"number", "label", "rationale", "evidence_a", "evidence_b"}
            and type(reply["number"]) is int and reply["number"] in by_number and reply["number"] not in seen, "reply_slot")
        seen.add(reply["number"])
        if isinstance(reply["rationale"], str) and reply["rationale"].strip():
            substantive.add(reply["number"])
    inspected, bindings, used = set(), [], list(completions)
    for row, value in events.values():
        if row["kind"] != "luna.pilot.reference.inspected" or value.get("request") != intent["request"]:
            continue
        session = [(r, v) for r, v in events.values() if r["session_id"] == row["session_id"]]
        starts = [(r, v) for r, v in session if r["kind"] == "operation.intended"]
        ends = [(r, v) for r, v in session if r["kind"] == "operation.completed"]
        if len(starts) != 1 or len(ends) != 1:
            continue
        br, bv = starts[0]
        ar, av = ends[0]
        inp, out = store.get(bv["input"], optional=True), store.get(av["result"], optional=True)
        selected = store.get(value["packet"], optional=True)
        if inp is None or out is None or selected is None:
            continue
        require(bv.get("operation") == av.get("operation") == "status" and inp.get("action") == "read"
            and type(inp.get("start")) is int and type(inp.get("end")) is int
            and hr["created_event"] < br["seq"] < row["seq"] < ar["seq"], "read_operation_binding")
        expected = [p for p in request["pairs"] if inp["start"] <= p["number"] <= inp["end"]]
        require(same(selected, expected) and same(value.get("numbers"), [p["number"] for p in expected])
            and same(out, {"instructions": native.RULES, "pairs": expected}), "exact_card_return")
        before = ar["seq"] < rr["created_event"]
        if before:
            inspected.update(p["number"] for p in expected)
        bindings.append({"input_artifact": bv["input"], "returned_artifact": av["result"], "packet_artifact": value["packet"],
            "inspection_event": row["event_hash"], "numbers": [p["number"] for p in expected], "before_reply": before})
        used.extend([starts[0], (row, value), ends[0]])
    return {"row": found[0], "response": response,
        "response_ref": found[0][1]["response"], "events": used, "read_bindings": bindings,
        "acknowledged_numbers": inspected & substantive}


@dataclass(frozen=True)
class MatchingHistory:
    observations: tuple
    source_contribution: dict
    pair_attempt_bindings: tuple
    inventory_certificate: dict
    manifest: dict


def normalize_matching_history(owner, index, *, origin_owner, pilot_owner, standard_owner):
    """Pure bounded contribution; native/copy and full inventory proofs upstream."""
    store, events, rows, intents = prior._owner(owner)
    known = {i.input_sha256: i.document_id for i in index.inputs}
    require(len(known) == len(index.inputs), "unique_input_frame")
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner else None
    batches, slots, observations, gaps, source_gaps = [], [], [], [], []
    endpoints, global_gap, parents = set(), False, {}
    for attempt, (er, intent) in intents.items():
        if intent.get("task_key") != FAMILY:
            gaps.append({"reason_code": "unsupported_physical_intent", "attempt": attempt, "input_sha256": None})
            global_gap = True
            continue
        require(type(intent.get("number")) is int and intent["number"] == 1, "attempt_number")
        if pilot_owner is not None:
            require(source_proof._path(intent["parent_owner"]) == source_proof._path(pilot_owner.scope["source_owner"]), "declared_pilot_owner")
        if intent["parent_plan"] not in parents:
            parent = _pilot(pilot_owner, intent["parent_plan"])
            sources, missing = _sources(parent, standard_owner) if parent else ({}, [])
            parents[intent["parent_plan"]] = (parent, sources)
            source_gaps.extend(missing)
        parent, sources = parents[intent["parent_plan"]]
        request, dispatch = store.get(intent["request"], optional=True), store.get(intent["dispatch"], optional=True)
        if parent is None or request is None or dispatch is None:
            gaps.append({"reason_code": "reference_parent_or_request_missing", "attempt": attempt, "input_sha256": None})
            global_gap = True
            continue
        prepared = _reference(intent, er, request, dispatch, rows, parent)
        if prepared is None:
            gaps.append({"reason_code": "registered_reference_contract_missing", "attempt": attempt, "input_sha256": None})
            global_gap = True
            continue
        handoffs = [(r, v) for r, v in rows.values() if r["kind"] == "luna_pilot_reference_handoff" and v.get("attempt") == attempt]
        require(len(handoffs) <= 1 and all(r["logical_key"] == FAMILY and same(v, intent) for r, v in handoffs), "handoff_wire")
        origin_ok = origin_owner is owner or pairs._origin_matches(origin_owner, owner, [*prepared["versions"], *handoffs],
            [(er, intent)], {intent["request"], intent["dispatch"]})
        review = _review(intent, er, request, events, rows, store)
        reply_origin = origin_ok
        if review["row"] and origin_owner is not owner:
            refs = {review["response_ref"], *(ref for b in review["read_bindings"] for ref in
                (b["input_artifact"], b["returned_artifact"], b["packet_artifact"]))}
            reply_origin = pairs._origin_matches(origin_owner, owner, [review["row"]], review["events"], refs)
        matched, acknowledged, batch_slots = set(), set(), []
        for number, task in enumerate(prepared["tasks"], 1):
            identities = [sources[task[side]] for side in ("left", "right")]
            hashes = sorted({i["input_sha256"] for i in identities if i and i["input_sha256"] in known})
            matched.update(known[h] for h in hashes)
            if any(i is None for i in identities):
                if hashes or not any(identities):
                    gaps.append({"reason_code": "pair_endpoint_unavailable", "attempt": attempt, "number": number, "input_sha256": hashes or None})
                    endpoints.update(hashes)
                    global_gap |= not hashes
            elif len(hashes) == 2:
                endpoints.update(hashes)
            logical = {"request_artifact": intent["request"], "number": number, "pair_id": task["pair_id"]}
            item = {"original_attempt": attempt, "original_owner_source_id": origin_id if origin_ok else None,
                "physical_id": digest([origin_id, attempt]) if origin_ok else None, "origin_verified": bool(origin_ok),
                "logical_slot": logical, "logical_slot_id": digest(logical), "source_identities": identities,
                "matched_input_sha256": hashes, "request_artifact": intent["request"], "dispatch_artifact": intent["dispatch"],
                "parent_plan": intent["parent_plan"], "parent_pair_request": task["request"], "role_policy": ROLE_POLICY,
                "evidence_scope": "card_fields", "current_reference_compatible": False, "creates_pair_y": False}
            slots.append(item)
            batch_slots.append(item["logical_slot_id"])
            if reply_origin and number in review["acknowledged_numbers"]:
                acknowledged.update(known[h] for h in hashes)
        if not origin_ok:
            affected = sorted(h for h, d in known.items() if d in matched)
            gaps.append({"reason_code": "physical_origin_unverified", "attempt": attempt, "input_sha256": affected or None})
            endpoints.update(affected)
            global_gap |= not affected
        evidence = {"intent_event": er["event_hash"], "handoff_records": [r["id"] for r, _ in handoffs],
            "reference_record": review["row"][0]["id"] if review["row"] else None,
            "response_artifact": review.get("response_ref"), "reads": review["read_bindings"],
            "acknowledged_document_ids": sorted(acknowledged), "evidence_scope": "card_fields",
            "full_article_read_proven": False, "attention_or_ui_delivery_proven": False}
        batches.append({"original_attempt": attempt, "physical_id": digest([origin_id, attempt]) if origin_ok else None,
            "logical_pair_slots": batch_slots, "matched_document_ids": sorted(matched), "evidence": evidence})
        if origin_ok and matched:
            observations.append({"event_id": attempt, "origin_source_id": origin_id, "source_id": source_id,
                "record_sha256": review.get("response_ref") or er["event_hash"], "roles": ["reference", "substantive_review"],
                "role_binding": digest({"policy": ROLE_POLICY, "parent": intent["parent_plan"]}),
                "task_binding": {"kind": "multiarticle", "document_ids": sorted(acknowledged or matched), "binding_sha256": digest(batch_slots)},
                "evidence": {"state": "acknowledged" if acknowledged else "uncertain",
                    "kind": "substantive_review_record" if acknowledged else "incomplete_record", "evidence_sha256": digest(evidence)}})
    manifest = {"version": VERSION, "family": FAMILY, "implementation": implementation(), "role_policy": ROLE_POLICY,
        "source_id": source_id, "source_head": owner.scope["source_head"], "scope_sha256": digest(owner.scope),
        "history_census_sha256": digest(owner.census), "input_index_digest": index.digest,
        "reference_batches": batches, "physical_intents": len(intents), "reference_physical_batches": len(batches),
        "logical_pair_bindings": len(slots), "pair_attempt_bindings_sha256": digest(slots),
        "observations_sha256": digest(observations), "P_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "source_evidence_gaps": source_gaps, "unresolved_evidence": gaps, "inherited_inventory_gaps": deepcopy(owner.gaps),
        "whole_study_history_complete": False, "records_for_single_pair_history_schema": [],
        "requires_logical_subtask_resolver": True, "endpoint_certificate_overblocks_unrelated_pairs": True,
        "creates_pair_y": False, "model_calls": 0, "source_mutations": 0,
        "limitations": "One declared 24-pair card-review family. Full retained input identity is provenance only; acknowledged P concerns saved card fields, not article reading or correctness. Parent Decisions are experimental judgments, not references, and are not normalized as reference attempts here. Inherited cards without selected Standard provenance stay unknown. No complete discovery or current labels; endpoint gaps intentionally overblock until multi-pair physical integration."}
    certificate = {"binding_sha256": digest(manifest), "complete": not endpoints and not (global_gap or owner.gaps),
        "unknown_input_sha256": sorted(endpoints), "global_gap": bool(global_gap or owner.gaps)}
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(owner.scope["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(o["origin_source_id"], o["event_id"]) for o in observations], "inventory_sha256": digest(manifest)}
    return MatchingHistory(tuple(observations), contribution, tuple(slots), certificate, manifest)
