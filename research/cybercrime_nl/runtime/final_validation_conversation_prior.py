"""Bounded P-only normalization of three recorded conversational article reviews.

No source/owner I/O, registrations or model calls. The audited caller supplies
verified HistoryOwner readers and explicit original/copy identities. Each method
asks two questions about each individual article; a batch is never a pair task.
Positive P requires an exact full-source request, an actual physical handoff,
same-session retained read input/inspection/complete returned packet, and a later
submitted substantive article review. Recorded return is not proof of UI delivery,
attention or reading every byte. Missing evidence stays unknown.

Incremental submissions combine under the original batch attempt. Retrospective
copied comparisons and overlap reports remain links to their original reviews;
they do not create new physical judgments. No screening answer is current pair Y
or a pair-reference retry blocker. Whole-study completeness remains upstream.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import final_validation_legacy_pair_history as pairs
import final_validation_legacy_prior as prior
import final_validation_projection as projection
from newsresearch.common import digest

WORKBENCH = Path(__file__).resolve().parents[3] / "workbench"
if str(WORKBENCH) not in sys.path:
    sys.path.insert(0, str(WORKBENCH))
import validate_luna_incident_screening as random100  # noqa: E402
import review_luna_screening_keeps as keeps  # noqa: E402
import validate_luna_incident_screening_30 as random30  # noqa: E402

VERSION = "final-validation-conversational-article-prior-v1"
FAMILIES = {
    random100.METHOD: (random100, "screen_validation", 100),
    keeps.METHOD: (keeps, "screen_keep_review", 45),
    random30.METHOD: (random30, "screen_validation", 30),
}
REVIEW_FIELDS = {"ordinal", "event_scope", "ai_incident", "scope_rationale", "incident_rationale", "scope_quote", "incident_quote"}
ACKNOWLEDGEMENT = "exact-recorded-full-article-return-before-submitted-substantive-review-v1"
NONPAIR_POLICY = "exact-registered-per-article-screening-contract-not-pair-reference-v1"
READ_NOTE = "Full text returned per article; no truncation. Receipt is not proof of attention."


def require(value, reason):
    if not value:
        raise ValueError("conversation_prior_" + reason)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), *(Path(builder.__file__) for builder, _, _ in FAMILIES.values()), Path(random100.core.__file__))
    return {**pairs.implementation(), **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _single(rows, kind, *, plan=None):
    result = [(r, v) for r, v in rows.values() if r["kind"] == kind and (plan is None or v.get("plan") == plan)]
    require(len(result) <= 1, "multiple_" + kind)
    return result[0] if result else None


def _plan(row, plan, rows, store):
    """Identify exact semantics from versions and source-bearing request content."""
    family = row["logical_key"]
    builder, prefix, ceiling = FAMILIES[family]
    versions = plan.get("versions")
    require(isinstance(versions, dict) and set(versions) == {
        "protocol", "selection", "question", "dossier_definition", "codebook", "prompt", "profile", "policy"}, "version_frame")
    selected = []
    for kind, identity in versions.items():
        version = rows.get(identity)
        if version is None:
            return None
        r, value = version
        require(r["kind"] == kind and r["logical_key"] == family and r["created_event"] < row["created_event"], "version_binding")
        selected.append(version)
    contents = {r["kind"]: v["content"] for r, v in selected}
    require(contents["protocol"].get("method") == family and contents["protocol"].get("implementation") == plan.get("implementation")
        and contents["prompt"] == {"instructions": builder.RULES, "questions": builder.core.QUESTIONS}
        and contents["codebook"].get("questions") == builder.core.QUESTIONS
        and plan.get("rules") == builder.RULES and plan.get("questions") == builder.core.QUESTIONS, "registered_contract")
    # Bind the specific historical producer and per-article question definition,
    # rather than infer task semantics from a name, article count or output label.
    expected = {str(Path(p).relative_to(WORKBENCH.parent)).replace("\\", "/"): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                for p in (builder.__file__, builder.core.__file__)}
    declared = {k.replace("\\", "/"): v for k, v in plan["implementation"].items()}
    require(all(declared.get(k) == v for k, v in expected.items()), "producer_binding")
    items = store.get(plan["items"], optional=True)
    selection = rows.get(plan["selection"])
    if items is None or selection is None:
        return None
    selected_row, selection_value = selection
    require(selected_row["kind"] == prefix + "_selection" and selected_row["logical_key"] == family
        and selected_row["created_event"] < row["created_event"] and selection_value.get("versions") == versions, "selection_binding")
    count = plan.get("count")
    require(type(count) is int and 1 <= count <= ceiling and isinstance(items, list) and len(items) == count, "source_count")
    require(all(isinstance(i, dict) and set(i) == {"ordinal", "title", "body"}
        and type(i["ordinal"]) is int and isinstance(i["title"], str) and isinstance(i["body"], str) for i in items)
        and [i["ordinal"] for i in items] == list(range(1, count + 1)), "full_source_items")
    mapping = selection_value.get("mapping")
    require(isinstance(mapping, list) and len(mapping) == count
        and all(type(i.get("ordinal")) is int for i in mapping)
        and [i.get("ordinal") for i in mapping] == list(range(1, count + 1)), "selection_source_frame")
    for mapped in mapping:
        require(set(mapped) == {"ordinal", "custom_id", "corpus", "decision_record", "request", "source"}, "selection_source_fields")
        for key in ("decision_record", "request", "source"):
            prior.exposure._sha(mapped[key])
        require(isinstance(mapped["custom_id"], str) and mapped["custom_id"], "selection_article_identity")
    require(len({m["custom_id"] for m in mapping}) == count, "duplicate_selection_identity")
    require({m[k] for m in mapping for k in ("request", "source")} <= set(plan.get("source_artifacts_verified", [])), "declared_parent_source_binding")
    request = {"instructions": builder.RULES, "questions": builder.core.QUESTIONS, "articles": items}
    return {"builder": builder, "prefix": prefix, "items": items, "request": request,
            "version_rows": selected, "selection": selection}


def _reads(plan_row, prepared, events, store, *, after):
    """Reconstruct exact original read() paging, then verify retained result bytes."""
    prefix, items, builder = prepared["prefix"], prepared["items"], prepared["builder"]
    proven, bindings, gaps, used_events, refs = {}, [], [], [], set()
    for row, value in events.values():
        if row["kind"] != prefix + ".inspected" or value.get("plan") != plan_row["id"]:
            continue
        require(row["seq"] > after, "inspection_before_handoff")
        same = [entry for entry in events.values() if entry[0]["session_id"] == row["session_id"]]
        inputs = [entry for entry in same if entry[0]["kind"] == "operation.intended"]
        outputs = [entry for entry in same if entry[0]["kind"] == "operation.completed"]
        if len(inputs) != 1 or len(outputs) != 1:
            gaps.append({"reason_code": "inspection_operation_unavailable", "inspection_event": row["event_hash"]})
            continue
        input_row, input_event = inputs[0]
        output_row, output_event = outputs[0]
        require(input_event.get("operation") == output_event.get("operation") == "status"
            and input_row["seq"] < row["seq"] < output_row["seq"], "inspection_operation_order")
        operation = store.get(input_event["input"], optional=True)
        result = store.get(output_event["result"], optional=True)
        if operation is None or result is None:
            gaps.append({"reason_code": "inspection_return_artifact_unavailable", "inspection_event": row["event_hash"]})
            continue
        start, end = operation.get("start"), operation.get("end")
        require(operation.get("action") == "read" and type(start) is int and type(end) is int
                and 1 <= start <= end <= len(items), "inspection_read_range")
        chosen, chars = [], 0
        for item in items:
            if start <= item["ordinal"] <= end:
                length = len(item["title"]) + len(item["body"])
                if chosen and chars + length > 24000:
                    break
                chosen.append(item)
                chars += length
        expected_event = {"plan": plan_row["id"], "ordinals": [i["ordinal"] for i in chosen],
                          "characters": chars, "coverage_note": READ_NOTE}
        expected_result = {"instructions": builder.RULES, "questions": builder.core.QUESTIONS, "articles": chosen,
            "next_ordinal": chosen[-1]["ordinal"] + 1, "full_text_characters": chars}
        require(digest(value) == digest(expected_event) and digest(result) == digest(expected_result), "inspection_exact_source_return")
        evidence = {"inspection_event": row["event_hash"], "read_intended_event": input_row["event_hash"],
            "read_completed_event": output_row["event_hash"], "input_artifact": input_event["input"],
            "result_artifact": output_event["result"], "ordinals": value["ordinals"], "characters": chars,
            "returned_complete_title_body": True, "ui_delivery_or_full_read_proven": False}
        bindings.append(evidence)
        for item in chosen:
            proven.setdefault(item["ordinal"], []).append(output_row["seq"])
        used_events.extend([inputs[0], (row, value), outputs[0]])
        refs.update((input_event["input"], output_event["result"]))
    return proven, bindings, gaps, used_events, refs


def _reviews(plan_row, prepared, rows, store, read_times, *, after):
    submitted, bindings, gaps, selected, refs = set(), [], [], [], set()
    candidates = [(r, v) for r, v in rows.values() if r["kind"] == prepared["prefix"] + "_reference" and v.get("plan") == plan_row["id"]]
    require(len({v.get("ordinal") for _, v in candidates}) == len(candidates), "duplicate_reference_ordinal")
    for row, value in candidates:
        ordinal = value.get("ordinal")
        require(type(ordinal) is int and 1 <= ordinal <= len(prepared["items"])
            and row["logical_key"] == str(ordinal) and row["created_event"] > after, "reference_source_binding")
        require(set(value) == REVIEW_FIELDS | {"plan", "submission", "reviewer", "human_validated"}, "reference_fields")
        submission = store.get(value["submission"], optional=True)
        if submission is None:
            gaps.append({"reason_code": "submitted_review_artifact_unavailable", "ordinal": ordinal, "record": row["id"]})
            continue
        require(isinstance(submission, dict) and set(submission) == {"submitted_text", "references"}
            and isinstance(submission["submitted_text"], str), "submission_fields")
        try:
            parsed = json.loads(submission["submitted_text"])
        except ValueError as error:
            raise ValueError("conversation_prior_submission_json_binding") from error
        require(parsed == submission["references"] and isinstance(parsed, list) and parsed
            and all(isinstance(r, dict) and set(r) == REVIEW_FIELDS and type(r["ordinal"]) is int
                and 1 <= r["ordinal"] <= len(prepared["items"]) for r in parsed)
            and len({r["ordinal"] for r in parsed}) == len(parsed), "submission_exact_references")
        reply = {k: value[k] for k in REVIEW_FIELDS}
        require([r for r in parsed if r["ordinal"] == ordinal] == [reply], "submitted_reference_binding")
        # Exposure does not depend on accepting its screening labels or quotes as
        # correct. Preserve original content and never derive a new reference Y.
        substantive = (value["reviewer"] == "codex:current-conversation" and value["human_validated"] is False
            and all(isinstance(reply.get(k), str) and reply[k].strip() for k in ("scope_rationale", "incident_rationale")))
        inspected_before = any(seq < row["created_event"] for seq in read_times.get(ordinal, []))
        if substantive and inspected_before:
            submitted.add(ordinal)
        bindings.append({"ordinal": ordinal, "record": row["id"], "record_artifact": row["artifact"],
            "submission_artifact": value["submission"], "substantive_reply": bool(substantive),
            "exact_return_before_reply": inspected_before, "acknowledged": bool(substantive and inspected_before)})
        selected.append((row, value))
        refs.add(value["submission"])
    return submitted, bindings, gaps, selected, refs


def _head_available(reader, head, events):
    if reader.scope["source_head"] == head:
        return True
    return (isinstance(head, list) and len(head) == 2 and type(head[0]) is int
            and 0 < head[0] <= reader.scope["source_head"][0] and head[0] in events
            and events[head[0]][0]["event_hash"] == head[1])


def _retrospective_links(plan_row, plan, prepared, rows, store, related):
    """Verify retained reused views, not new reference attempts or exposures."""
    links, gaps = [], []
    previous = plan.get("prior_validation")
    if previous is not None:
        link = {"kind": "copied_prior_validation_comparison", "owner": previous.get("owner"),
                "copied_artifact": previous.get("comparison"), "creates_new_review": False, "verified": False}
        other = related.get(previous.get("owner"))
        if other is not None:
            other_store, other_events, other_rows, other_intents = prior._owner(other)
            ids = [previous.get(k) for k in ("plan", "report", "frozen_references")]
            copied = store.get(previous["comparison"], optional=True)
            if _head_available(other, previous.get("head"), other_events) and copied is not None and all(i in other_rows for i in ids):
                old_plan, report, frozen = [other_rows[i] for i in ids]
                require(old_plan[0]["kind"] == "screen_validation_plan" and old_plan[0]["logical_key"] == random100.METHOD
                    and report[0]["kind"] == "screen_validation_report" and frozen[0]["kind"] == "screen_validation_references_frozen"
                    and report[1].get("plan") == ids[0] and report[1].get("frozen_references") == ids[2]
                    and frozen[1].get("plan") == ids[0]
                    and old_plan[0]["created_event"] < frozen[0]["created_event"] < report[0]["created_event"] <= previous["head"][0],
                    "copied_prior_plan_binding")
                old_prepared = _plan(*old_plan, other_rows, other_store)
                original = other_store.get(report[1]["details"], optional=True)
                if original is not None:
                    require(digest(copied) == digest(original), "copied_prior_comparison_changed")
                    require(isinstance(copied, list) and len(copied) == old_plan[1]["count"]
                        and len(frozen[1]["references"]) == old_plan[1]["count"], "copied_prior_reference_count")
                    reference_rows = [other_rows.get(i) for i in frozen[1]["references"]]
                    if all(r is not None for r in reference_rows):
                        by_ordinal = {v["ordinal"]: (r, v) for r, v in reference_rows}
                        require(len(by_ordinal) == len(copied), "copied_prior_unique_references")
                        for item in copied:
                            r, v = by_ordinal[item["ordinal"]]
                            require(r["kind"] == "screen_validation_reference" and v["plan"] == ids[0]
                                and item["reference"] == {**v, "_record_id": r["id"]}
                                and r["created_event"] <= previous["head"][0], "copied_prior_reference_binding")
                        attempts = [attempt for attempt, (_, intent) in other_intents.items() if intent.get("batch") == ids[0] and intent.get("task_key") == ids[0]]
                        if len(attempts) == 1 and old_prepared is not None:
                            original_intent_row, original_intent = other_intents[attempts[0]]
                            original_request = other_store.get(original_intent["request"], optional=True)
                            original_dispatch = other_store.get(original_intent["dispatch"], optional=True)
                            if original_request is not None and original_dispatch is not None:
                                require(digest(original_request) == digest(old_prepared["request"])
                                    and digest(original_dispatch) == digest(pairs.legacy.Invocation(original_request).manifest())
                                    and type(original_intent.get("number")) is int and original_intent["number"] == 1
                                    and old_plan[0]["created_event"] < original_intent_row["seq"] < frozen[0]["created_event"],
                                    "copied_prior_physical_request_binding")
                                link.update(verified=True, original_owner_source_id=other.census["owner_sha256"],
                                    original_attempt=attempts[0], original_plan=ids[0], original_report=ids[1],
                                    original_reference_records=sorted(r["id"] for r, _ in reference_rows),
                                    original_artifact=report[1]["details"], submission_exposure_verified=False)
        if not link["verified"]:
            gaps.append({"reason_code": "copied_prior_review_origin_unresolved", "owner": previous.get("owner")})
        links.append(link)
    # The 30-case method merely reports old selection overlap. This is metadata,
    # not a second submission of those prior references or another model call.
    expected_owners = plan.get("prior_review_owners", [])
    require(isinstance(expected_owners, list) and all(isinstance(v, str) for v in expected_owners)
        and len(expected_owners) == len(set(expected_owners)), "prior_owner_declarations")
    reports = [(r, v) for r, v in rows.values() if r["kind"] == prepared["prefix"] + "_report" and v.get("plan") == plan_row["id"]]
    require(len(reports) <= 1, "multiple_retrospective_reports")
    overlap = reports[0][1].get("prior_review_overlap", []) if reports else []
    require(isinstance(overlap, list) and len({v["owner"] for v in overlap}) == len(overlap)
        and {v["owner"] for v in overlap} <= set(expected_owners), "prior_overlap_frame")
    current_mapping = prepared["selection"][1]["mapping"]
    for name in expected_owners:
        values = [v for v in overlap if v["owner"] == name]
        link = {"kind": "selection_overlap_only", "owner": name, "creates_new_review": False, "verified": False}
        other = related.get(name)
        if other is not None and values:
            value = values[0]
            _, other_events, other_rows, _ = prior._owner(other)
            selected = other_rows.get(value["selection"])
            if selected and _head_available(other, value["head"], other_events):
                r, old = selected
                require(r["kind"] in {"screen_validation_selection", "screen_keep_review_selection"}
                    and r["created_event"] <= value["head"][0], "prior_overlap_selection_binding")
                old_ids = {item["custom_id"] for item in old["mapping"]}
                require(value["ordinals"] == [item["ordinal"] for item in current_mapping if item["custom_id"] in old_ids], "prior_overlap_changed")
                link.update(verified=True, original_owner_source_id=other.census["owner_sha256"], selection=value["selection"],
                            reported_overlap_ordinals=value["ordinals"], proves_exact_source_match=False)
        if not link["verified"]:
            gaps.append({"reason_code": "prior_selection_owner_unresolved", "owner": name})
        links.append(link)
    return links, gaps


def normalize_conversational_screening_prior(owner, index, *, origin_owner, related_owners=()):
    """Return LegacyPrior, with empty pair-label/blocker semantics explicitly bound.

    Scope must include operation.intended/completed input/result artifacts, named
    inspection events, all version/selection/plan/handoff/reference rows, each
    plan's items and each reference's submission. Related owners verify copied
    comparisons/overlap; their own exposures are normalized separately. Missing
    scope cannot become P0 or a complete non-pair census. No text is in manifest.
    """
    store, events, rows, intents = prior._owner(owner)
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner is not None else None
    known = {item.input_sha256: item.document_id for item in index.inputs}
    require(len(known) == len(index.inputs), "unique_final_inputs")
    related = {r.scope["source_owner"]: r for r in related_owners}
    require(len(related) == len(related_owners), "duplicate_related_owner")
    plans = {identity: (r, v) for identity, (r, v) in rows.items()
        if r["logical_key"] in FAMILIES and r["kind"] == FAMILIES[r["logical_key"]][1] + "_plan"}
    prepared = {identity: _plan(r, v, rows, store) for identity, (r, v) in plans.items()}
    observations, bindings, gaps, dispositions, links = [], [], [], [], []
    attempted, unsupported, outside = set(), [], []
    for attempt, (intent_row, intent) in intents.items():
        plan_id = intent.get("batch")
        if plan_id not in plans or prepared[plan_id] is None:
            unsupported.append(attempt)
            gaps.append({"reason_code": "unsupported_or_incomplete_registered_family", "attempt": attempt, "document_ids": None})
            continue
        attempted.add(plan_id)
        plan_row, plan = plans[plan_id]
        value = prepared[plan_id]
        request, dispatch = store.get(intent["request"], optional=True), store.get(intent["dispatch"], optional=True)
        if request is None or dispatch is None:
            gaps.append({"reason_code": "physical_request_or_dispatch_unavailable", "attempt": attempt, "document_ids": None})
            continue
        require(digest(request) == digest(value["request"])
            and digest(dispatch) == digest(pairs.legacy.Invocation(request).manifest()), "exact_source_request_dispatch")
        require(intent.get("task_key") == plan_id and type(intent.get("number")) is int and intent["number"] == 1
            and plan_row["created_event"] < intent_row["seq"], "physical_plan_binding")
        handoff = _single(rows, value["prefix"] + "_handoff")
        if handoff:
            require(handoff[1] == intent and handoff[0]["logical_key"] == plan_row["logical_key"]
                and handoff[0]["created_event"] > intent_row["seq"], "handoff_binding")
        read_times, read_bindings, read_gaps, read_events, read_refs = _reads(plan_row, value, events, store, after=intent_row["seq"])
        proven, review_bindings, review_gaps, review_rows, submission_refs = _reviews(plan_row, value, rows, store, read_times, after=intent_row["seq"])
        if not handoff:
            proven.clear()
        gaps.extend({**g, "attempt": attempt} for g in [*read_gaps, *review_gaps])
        sources = [{"ordinal": i["ordinal"], "title_sha256": hashlib.sha256(i["title"].encode()).hexdigest(),
            "body_sha256": hashlib.sha256(i["body"].encode()).hexdigest(), "input_sha256": digest({"title": i["title"], "body": i["body"]})} for i in value["items"]]
        matched = sorted({known[s["input_sha256"]] for s in sources if s["input_sha256"] in known})
        acknowledged = sorted({known[s["input_sha256"]] for s in sources if s["ordinal"] in proven and s["input_sha256"] in known})
        selected_rows = [(plan_row, plan), value["selection"], *value["version_rows"], *review_rows, *([handoff] if handoff else [])]
        selected_events = [(intent_row, intent), *read_events]
        artifact_refs = {intent["request"], intent["dispatch"], plan["items"], *read_refs, *submission_refs}
        origin_ok = origin_owner is owner or pairs._origin_matches(origin_owner, owner, selected_rows, selected_events, artifact_refs)
        if not origin_ok:
            gaps.append({"reason_code": "physical_review_origin_unresolved", "attempt": attempt, "document_ids": matched or None})
        source_binding = {"plan_record": plan_id, "selection_record": plan["selection"], "items_artifact": plan["items"],
            "request_artifact": intent["request"], "source_versions": sources, "matched_document_ids": matched,
            "acknowledged_document_ids": acknowledged, "parent_selection_binding": digest(value["selection"][1])}
        evidence = {"rule": ACKNOWLEDGEMENT, "intent_event": intent_row["event_hash"], "dispatch_artifact": intent["dispatch"],
            "handoff_record": handoff[0]["id"] if handoff else None, "read_bindings": read_bindings, "review_bindings": review_bindings,
            "reviewed_ordinals": sorted(proven), "unreviewed_ordinals": sorted(set(range(1, len(sources) + 1)) - proven),
            "state": "acknowledged" if acknowledged else "uncertain", "observed_model": None,
            "ui_delivery_attention_or_full_read_proven": False}
        bindings.append({"original_attempt": attempt, "original_owner_source_id": origin_id if origin_ok else None,
            "origin_verified": bool(origin_ok), "family": plan_row["logical_key"], "source_binding": source_binding, "evidence_binding": evidence,
            "independent_judgment_claim": False, "current_pair_reference_compatible": False})
        dispositions.append({"policy": NONPAIR_POLICY, "original_attempt": attempt, "source_id": source_id,
            "original_owner_source_id": origin_id if origin_ok else None, "origin_verified": bool(origin_ok),
            "plan_record": plan_id, "family": plan_row["logical_key"], "intent_event": intent_row["event_hash"],
            "request_artifact": intent["request"], "dispatch_artifact": intent["dispatch"],
            "registered_versions": plan["versions"], "task_scope": "per_article_screening_reference",
            "pair_reference_role": False, "creates_pair_retry_blocker": False})
        if origin_ok and matched:
            ids = acknowledged or matched
            observations.append({"event_id": attempt, "origin_source_id": origin_id, "source_id": source_id,
                "record_sha256": digest([r["id"] for r, _ in review_rows]) if review_rows else intent_row["event_hash"],
                "roles": ["reference", "substantive_review"], "role_binding": digest({"family": plan_row["logical_key"], "plan": plan_id, "policy": NONPAIR_POLICY}),
                "task_binding": {"kind": "multiarticle", "document_ids": ids, "binding_sha256": digest(source_binding)},
                "evidence": {"state": evidence["state"], "kind": "substantive_review_record" if acknowledged else "incomplete_record",
                             "evidence_sha256": digest(evidence)}})
        if not matched:
            outside.append(attempt)
    for plan_id, (row, plan) in plans.items():
        if prepared[plan_id] is not None:
            reused, unresolved = _retrospective_links(row, plan, prepared[plan_id], rows, store, related)
            links.extend(reused)
            gaps.extend(unresolved)
    manifest = {"version": VERSION, "source_id": source_id, "source_head": owner.scope["source_head"],
        "origin_source_id": origin_id, "input_index_digest": index.digest, "history_census_sha256": digest(owner.census),
        "supported_families": sorted(FAMILIES), "acknowledgement_rule": ACKNOWLEDGEMENT,
        "physical_id_policy": pairs.PHYSICAL_ID_POLICY, "physical_intents": len(intents), "normalized_attempts": bindings,
        "supported_exact_request_attempts": len(bindings), "non_pair_task_dispositions": dispositions,
        "prepared_only_plans": sorted(set(plans) - attempted), "unsupported_attempts": unsupported,
        "exact_version_nonintersection_attempts": outside, "retrospective_origin_links": links,
        "unresolved_evidence": gaps, "inherited_inventory_gaps": deepcopy(owner.gaps),
        "observations_sha256": digest(observations), "evidence_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "owner_history_complete": False, "whole_study_history_complete": False,
        "creates_pair_labels": False, "creates_pair_retry_blockers": False, "model_calls": 0, "source_mutations": 0,
        "limitations": "Three exact per-article conversational review contracts only. Retained read packets prove recorded complete title/body returns, not UI visibility, attention or full reading. Incremental subsets stay one batch event, copied comparisons add no new review, and no independence/model-provenance claim follows. Parent archive provenance, other review/manual histories and missing origins remain separately unreconciled; exact submitted input hashes alone establish frame intersection."}
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(owner.scope["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(o["origin_source_id"], o["event_id"]) for o in observations],
        "inventory_sha256": digest(manifest)}
    return prior.LegacyPrior(tuple(observations), contribution, manifest)
