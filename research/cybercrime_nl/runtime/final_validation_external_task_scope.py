"""Evidence-based task census for three bounded historical producer families.

Pure HistoryOwner consumer: no owner reads, registrations, model calls or labels.
The audited caller supplies exact stopped cutoffs and explicitly declared native
origins. Every durable intent is classified independently of response, P or Y.
Unrecognized records are possible manual pair tasks, never silently administrative.
This closes only the supplied inspected scope, not discovery of all study history.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path

import final_validation_conversation_prior as conversation
import final_validation_legacy_pair_history as pairs
import final_validation_legacy_prior as prior
from newsresearch import luna_incident_screening as screening
from newsresearch.common import digest

VERSION = "final-validation-external-physical-task-scope-v1"
POLICY = "exact-native-contract-purpose-independent-of-review-outcome-v1"
ROOT = Path(__file__).resolve().parents[3]


def require(value, reason):
    if not value:
        raise ValueError("external_task_scope_" + reason)


def implementation():
    return {**conversation.implementation(), str(Path(__file__).relative_to(ROOT)):
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def _same(a, b):
    return digest(a) == digest(b)


def _astra_plan(row, plan, rows, store):
    """Exact registered per-article contract, not a generic named CLI batch."""
    versions = plan.get("versions")
    if not isinstance(versions, dict):
        return None
    require(set(versions) == {"protocol", "question", "selection", "profile", "prompt", "policy", "codebook"}, "astra_versions")
    selected = [rows.get(identity) for identity in versions.values()]
    if any(value is None for value in selected):
        return None
    for kind, identity in versions.items():
        r, _ = rows[identity]
        require(r["kind"] == kind and r["logical_key"] == prior.FAMILY and r["created_event"] < row["created_event"], "astra_version_binding")
    contents = {r["kind"]: value["content"] for r, value in selected}
    declared = plan.get("implementation")
    require(isinstance(declared, dict), "astra_implementation")
    declared = {key.replace("\\", "/"): value for key, value in declared.items()}
    paths = (ROOT / "workbench/validate_incident_decisions_astra.py", Path(prior.legacy.__file__), Path(prior.cli.__file__))
    require(all(declared.get(str(path.relative_to(ROOT)).replace("\\", "/")) == hashlib.sha256(path.read_bytes()).hexdigest()
                for path in paths), "astra_producer")
    require(contents["protocol"].get("method") == prior.FAMILY
        and _same(contents["protocol"].get("implementation"), plan["implementation"])
        and _same(plan.get("questions"), screening.QUESTIONS)
        and contents["prompt"] == {"instructions": prior.legacy.RULES, "model": prior.legacy.MODEL,
            "reasoning_effort": "medium", "batch_size_max": 5,
            "questions": "Exact questions verified identical across all selected frozen requests before dispatch; bound in plan."}
        and _same(contents["codebook"], {"labels": sorted({v for choices in prior.legacy.LABELS.values() for v in choices}),
            "questions": plan["questions"], "boundary_ambiguous_policy": "Retain as unresolved in primary confusion matrix"}), "astra_contract")
    batches = plan.get("batches")
    require(isinstance(batches, list) and batches, "astra_batches")
    prepared = []
    for batch in batches:
        require(set(batch) == {"phase", "items", "count"} and batch["phase"] in {"pilot", "extension"}
            and type(batch["count"]) is int and 1 <= batch["count"] <= 5, "astra_batch")
        items = store.get(batch["items"], optional=True)
        if items is None:
            prepared.append(None)
            continue
        require(isinstance(items, list) and len(items) == batch["count"] and all(isinstance(i, dict)
            and set(i) == {"article_id", "title", "body"} and all(isinstance(v, str) for v in i.values())
            and i["article_id"] for i in items) and len({i["article_id"] for i in items}) == len(items), "astra_sources")
        prepared.append({"items": items, "request": prior.legacy.request_for(items, plan["questions"])})
    return {"kind": "astra", "prefix": "astra_validation", "versions": selected, "batches": prepared}


def _plans(rows, store):
    result = {}
    for identity, (row, plan) in rows.items():
        if row["kind"] == pairs.PLAN and row["logical_key"] == pairs.FAMILY:
            if not pairs._plan(row, plan, rows):
                continue
            protocol = rows[plan["versions"]["protocol"]][1]["content"]
            require(protocol.get("implementation_sha256") == hashlib.sha256(Path(pairs.legacy.__file__).read_bytes()).hexdigest(), "pair_producer")
            value = {"kind": "pair", "prefix": "provider_label", "versions": [rows[v] for v in plan["versions"].values()]}
        elif row["logical_key"] in conversation.FAMILIES and row["kind"] == conversation.FAMILIES[row["logical_key"]][1] + "_plan":
            value = conversation._plan(row, plan, rows, store)
            if value is None:
                continue
            value = {**value, "kind": "conversation", "versions": value["version_rows"]}
        elif row["kind"] == prior.PLAN and row["logical_key"] == prior.FAMILY and plan.get("method") == prior.FAMILY:
            value = _astra_plan(row, plan, rows, store)
            if value is None:
                continue
        else:
            continue
        result[identity] = {**value, "row": row, "plan": plan, "family": row["logical_key"]}
    return result


def _source(item, alias):
    return {"legacy_source_id": alias, "input_sha256": digest({"title": item["title"], "body": item["body"]}),
            "title_sha256": hashlib.sha256(item["title"].encode()).hexdigest(),
            "body_sha256": hashlib.sha256(item["body"].encode()).hexdigest()}


def _task(selected, intent_row, intent, owner, store):
    """Return native task evidence without consulting results or serving state."""
    plan, row, kind = selected["plan"], selected["row"], selected["kind"]
    require(row["created_event"] < intent_row["seq"] and type(intent.get("number")) is int and intent["number"] == 1, "intent_chronology")
    request, dispatch = (store.get(intent[k], optional=True) for k in ("request", "dispatch"))
    if request is None or dispatch is None:
        return None
    refs = {intent["request"], intent["dispatch"]}
    if kind == "pair":
        number = intent.get("pair")
        require(type(number) is int and 1 <= number <= len(plan["pairs"]), "pair_number")
        pair = plan["pairs"][number - 1]
        expected = {"pair": number, "boundary": pairs.legacy.BOUNDARY, "instructions": pairs.legacy.RULES,
            "versions": plan["versions"], "response_fields": pairs.RESPONSE_FIELDS,
            **{role: {k: article[k] for k in ("source_sha256", "title", "published", "body")}
               for role, article in zip(("a", "b"), pair["articles"], strict=True)}}
        require(intent.get("task_key") == digest([row["id"], number]) and intent.get("authorization_key") == pairs.FAMILY
            and type(intent.get("reserved_pair_attempts")) is int and intent["reserved_pair_attempts"] == 1
            and type(intent.get("reserved_article_exposures")) is int and intent["reserved_article_exposures"] == 2, "pair_intent")
        sources = [pairs._source(a, old, pair["event_uri"], owner.artifacts)
                   for a, old in zip(pair["articles"], pair["article_ids"], strict=True)]
        refs.update(s["original_artifact"] for s in sources if s)
        expected_dispatch = pairs.legacy.Invocation(request).manifest()
        slot = number
    elif kind == "conversation":
        require(intent.get("task_key") == intent.get("batch") == row["id"], "conversation_intent")
        expected = selected["request"]
        sources = [_source(item, item["ordinal"]) for item in selected["items"]]
        refs.add(plan["items"])
        expected_dispatch = pairs.legacy.Invocation(request).manifest()
        slot = 0
    else:
        slot = intent.get("batch_index")
        require(type(slot) is int and 0 <= slot < len(selected["batches"])
            and intent.get("task_key") == digest([row["id"], slot]) and intent.get("batch") == row["id"], "astra_intent")
        batch, prepared = plan["batches"][slot], selected["batches"][slot]
        if prepared is None:
            return None
        require(type(intent.get("count")) is int and intent["count"] == batch["count"] and intent.get("phase") == batch["phase"], "astra_batch_intent")
        expected = prepared["request"]
        sources = [_source(item, item["article_id"]) for item in prepared["items"]]
        refs.add(batch["items"])
        prior._dispatch(request, dispatch, plan)
        expected_dispatch = dispatch
    require(_same(request, expected) and _same(dispatch, expected_dispatch), "native_request_dispatch")
    return {"sources": sources, "artifact_refs": refs, "slot": slot}


def _record_dispositions(rows, plans, intents, tasks, store):
    """Partition all selected records, leaving unsupported derived formats open."""
    covered = {}
    for identity, selected in plans.items():
        covered[identity] = {"disposition": "registered_plan", "plan": identity}
        for row, _ in selected["versions"]:
            covered[row["id"]] = {"disposition": "registered_definition", "plan": identity}
        if selected["kind"] == "conversation":
            covered[selected["selection"][0]["id"]] = {"disposition": "bound_source_selection", "plan": identity}
    # These are task views/subresults, not independent new judgments. Exact
    # native shapes and source ordinals are checked even when a reply is absent.
    for identity, (row, value) in rows.items():
        if identity in covered:
            continue
        attempt = value.get("attempt") if isinstance(value, dict) else None
        task = tasks.get(attempt)
        if task and task["disposition"] != "possible_pair_unknown":
            selected = plans[task["plan_record"]]
            intent = intents[attempt][1]
            prefix, kind = selected["prefix"], selected["kind"]
            handoff_kind = prior.INTENDED if kind == "astra" else prefix + "_handoff"
            if row["kind"] == handoff_kind:
                key = selected["family"] if kind == "conversation" else intent["task_key"]
                require(row["logical_key"] == key and _same(value, intent), "handoff_record")
                covered[identity] = {"disposition": "physical_intent_view", "attempt": attempt}
            elif kind == "astra" and row["kind"] == prior.RESPONSE:
                if not set(value) <= set(intent) | {"response", "references", "validation_error", "unknown_outcome", "failure", "usage", "model_observed", "configured_model", "finished_at"}:
                    continue
                require(row["logical_key"] == intent["task_key"] and all(k in value and _same(value[k], v) for k, v in intent.items()), "astra_result_intent")
                covered[identity] = {"disposition": "physical_result_view", "attempt": attempt}
            elif kind == "pair" and row["kind"] == pairs.JUDGMENT:
                require(set(value) == {"plan", "attempt", "request", "response", "reply", "validation", "human_validated", "recorded_at"}
                    and row["logical_key"] == intent["task_key"] and value["plan"] == task["plan_record"]
                    and value["request"] == intent["request"], "pair_result_intent")
                covered[identity] = {"disposition": "physical_result_view", "attempt": attempt}
            if identity in covered:
                require(row["created_event"] > intents[attempt][0]["seq"], "task_view_chronology")
                continue
        selected = plans.get(value.get("plan")) if isinstance(value, dict) else None
        if selected and selected["kind"] == "conversation" and row["kind"] == selected["prefix"] + "_reference":
            ordinal = value.get("ordinal")
            require(set(value) == conversation.REVIEW_FIELDS | {"plan", "submission", "reviewer", "human_validated"}
                and type(ordinal) is int and 1 <= ordinal <= len(selected["items"]) and row["logical_key"] == str(ordinal)
                and row["created_event"] > selected["row"]["created_event"], "article_reference_contract")
            # Missing submission does not change this exact per-article task's
            # semantics; provenance/P remains the separate normalizer's job.
            covered[identity] = {"disposition": "nonpair_article_subresult", "plan": selected["row"]["id"], "ordinal": ordinal}
            continue
        for plan_id, selected in plans.items():
            if row["kind"] == selected["prefix"] + "_preparation" and row["logical_key"] == selected["family"]:
                if set(value) != {"versions", "at" if selected["kind"] == "astra" else "started_at"}:
                    continue
                versions = value.get("versions", {})
                expected = selected["plan"]["versions"]
                # Astra preparation precedes the codebook registered after input
                # collection; all other families already bind their whole set.
                if selected["kind"] == "astra":
                    expected = {k: v for k, v in expected.items() if k != "codebook"}
                require(_same(versions, expected) and row["created_event"] < selected["row"]["created_event"], "preparation_versions")
                covered[identity] = {"disposition": "bound_preparation", "plan": plan_id}
                break
    return covered


def _event_dispositions(events, rows, plans, intents, tasks, store):
    """Unknown custom/manual events cannot disappear behind the record census."""
    covered = {}
    administrative = {"session.started": {"context", "identity", "configuration", "preflight", "actor_assurance"},
        "session.ended": {"status"}}
    exact_read_events = set()
    for identity, selected in plans.items():
        handoffs = [intents[attempt][0]["seq"] for attempt, task in tasks.items()
                    if task.get("plan_record") == identity and task["disposition"] == "nonpair_screening"]
        if selected["kind"] == "conversation" and handoffs:
            # Generic operation wrappers can themselves carry an otherwise
            # unrecorded manual review. Only these exact original read() returns
            # are discharged; unrelated status/prepare/submit/report wrappers
            # need a future producer-specific proof, not their generic shape.
            _, _, _, used, _ = conversation._reads(selected["row"], selected, events, store, after=min(handoffs))
            exact_read_events.update(row["event_hash"] for row, _ in used)
    for row, value in events.values():
        kind, reason = row["kind"], None
        if row["event_hash"] in exact_read_events:
            reason = "exact_native_single_article_read_operation"
        elif kind in administrative and set(value) == administrative[kind]:
            reason = "audited_runtime_operation_metadata"
        elif kind == "record.created" and value.get("record") in rows:
            reason = "record_projection_creation"
        elif kind == "record.reused" and value.get("record") in rows:
            reason = "existing_record_view"
        elif kind in {"model.attempt.intended", "model.attempt.completed"} and value.get("attempt") in intents:
            reason = "physical_attempt_ledger"
        elif value.get("attempt") in tasks:
            task = tasks[value["attempt"]]
            selected = plans.get(task.get("plan_record"))
            if selected:
                expected = "codex.response.received" if selected["kind"] == "pair" else "astra_validation.response.received" if selected["kind"] == "astra" else selected["prefix"] + ".handoff_receipt"
                if kind == expected:
                    require(row["seq"] > intents[value["attempt"]][0]["seq"], "result_event_chronology")
                    reason = "bound_task_receipt"
        if reason is None and value.get("plan") in plans:
            selected = plans[value["plan"]]
            prefix = selected["prefix"]
            if kind == "provider_label.handoff.prepared" and selected["kind"] == "pair":
                numbers = value.get("pairs")
                require(isinstance(numbers, list) and all(type(n) is int and 1 <= n <= len(selected["plan"]["pairs"]) for n in numbers), "prepared_pair_numbers")
                reason = "bound_handoff_preparation_view"
            elif selected["kind"] == "conversation" and kind == prefix + ".inspected":
                numbers = value.get("ordinals")
                require(isinstance(numbers, list) and all(type(n) is int and 1 <= n <= len(selected["items"]) for n in numbers), "inspection_ordinals")
                reason = "bound_single_article_source_inspection"
            elif selected["kind"] == "conversation" and kind in {prefix + ".unblinding", prefix + ".probabilities_revealed"} and value.get("frozen") in rows:
                frozen_row, frozen = rows[value["frozen"]]
                if frozen_row["kind"] == prefix + "_references_frozen" and frozen.get("plan") == value["plan"]:
                    reason = "bound_existing_references_revealed"
        if reason is None and kind == "provider_label.request.chunk_inspected":
            packets = store.get(value["packets"], optional=True)
            known_requests = {t.get("request_artifact"): t for t in tasks.values() if t["disposition"] == "pair_reference"}
            if isinstance(packets, list) and packets and all(isinstance(p, dict) and p.get("request") in known_requests for p in packets):
                for packet in packets:
                    task = known_requests[packet["request"]]
                    intent = intents[task["view_attempt"]][1]
                    require(type(packet.get("pair")) is int and packet["pair"] == intent["pair"], "window_task_pair")
                reason = "bound_existing_pair_source_windows"
        if reason is not None:
            covered[row["event_hash"]] = reason
    return covered


def normalize_external_task_scope(owner, index, *, origin_owner):
    """Classify a verified reader's exact inspected task scope, not all history.

    Pass the same reader only for an audited native-origin declaration. Copies
    require a verified original reader. No caller flags can assert task semantics.
    Missing P/results never make a proven nonpair task a possible pair task.
    """
    store, events, rows, intents = prior._owner(owner)
    plans = _plans(rows, store)
    known = {i.input_sha256: i.document_id for i in index.inputs}
    require(len(known) == len(index.inputs), "unique_input_frame")
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner is not None else None
    tasks, gaps, provenance_gaps, attempted, requirements = {}, [], [], set(), []
    unlocalized_plan_attempts = set()
    for attempt, (intent_row, intent) in intents.items():
        selected = plans.get(intent.get("plan")) or plans.get(intent.get("batch"))
        task = {"view_attempt": attempt, "view_source_id": source_id, "intent_event": intent_row["event_hash"],
            "disposition": "possible_pair_unknown", "origin_verified": False,
            "physical_identity": None, "source_identities": [], "matched_document_ids": []}
        if selected:
            slot = intent.get("pair") if selected["kind"] == "pair" else intent.get("batch_index") if selected["kind"] == "astra" else 0
            if type(slot) is int:
                attempted.add((selected["row"]["id"], slot))
            else:
                unlocalized_plan_attempts.add(selected["row"]["id"])
        detail = _task(selected, intent_row, intent, owner, store) if selected else None
        if detail is None:
            gaps.append({"reason_code": "unsupported_or_incomplete_physical_task", "attempt": attempt, "input_sha256": None})
            tasks[attempt] = task
            continue
        plan_id = selected["row"]["id"]
        attempted.add((plan_id, detail["slot"]))
        sources = detail["sources"]
        matched = sorted({known[s["input_sha256"]] for s in sources if s and s["input_sha256"] in known})
        selected_rows = [(selected["row"], selected["plan"]), *selected["versions"]]
        if selected["kind"] == "conversation":
            selected_rows.append(selected["selection"])
        origin_ok = origin_owner is owner or pairs._origin_matches(origin_owner, owner, selected_rows,
            [(intent_row, intent)], detail["artifact_refs"])
        is_pair = selected["kind"] == "pair"
        task.update(disposition="pair_reference" if is_pair else "nonpair_screening", family=selected["family"],
            plan_record=plan_id, registered_versions=selected["plan"]["versions"],
            request_artifact=intent["request"], dispatch_artifact=intent["dispatch"],
            source_identities=sources, matched_document_ids=matched, origin_verified=bool(origin_ok),
            physical_identity={"source_id": origin_id, "attempt": attempt} if origin_ok else None,
            canonical_physical_id=digest([origin_id, attempt]) if origin_ok else None,
            historical_role="conversational_pair_reference" if is_pair else "per_article_screening_reference",
            primary_blocker_required=is_pair, creates_pair_y=False, outcome_required_for_disposition=False)
        if not origin_ok:
            gap = {"reason_code": "physical_origin_unverified", "attempt": attempt,
                   "input_sha256": sorted(s["input_sha256"] for s in sources if s and s["input_sha256"] in known) or None}
            provenance_gaps.append(gap)
            requirements.append({"view_source_id": source_id, "proposed_origin_source_id": origin_id,
                "attempt": attempt, "intent_event": intent_row["event_hash"], "plan_record": plan_id,
                "request_artifact": intent["request"], "dispatch_artifact": intent["dispatch"]})
            if is_pair:
                gaps.append(gap)
        if is_pair and any(s is None for s in sources):
            # One exactly known endpoint bounds this two-source pair; an absent
            # final-frame intersection of that endpoint proves exact nonintersection.
            bound = sorted(s["input_sha256"] for s in sources if s and s["input_sha256"] in known)
            if bound or not any(s for s in sources):
                gaps.append({"reason_code": "pair_source_identity_unavailable", "attempt": attempt, "input_sha256": bound or None})
        tasks[attempt] = task
    covered = _record_dispositions(rows, plans, intents, tasks, store)
    event_covered = _event_dispositions(events, rows, plans, intents, tasks, store)
    event_unknown = sorted({r["event_hash"] for r, _ in events.values()} - set(event_covered))
    for identity in event_unknown:
        gaps.append({"reason_code": "unclassified_event_possible_manual_pair", "event_hash": identity, "input_sha256": None})
    unresolved_records = sorted(set(rows) - set(covered))
    for identity in unresolved_records:
        gaps.append({"reason_code": "unclassified_record_possible_manual_pair", "record_id": identity, "input_sha256": None})
    for identity in owner.census.get("out_of_scope_record_ids", []):
        gaps.append({"reason_code": "omitted_record_scope_unverified", "record_id": identity, "input_sha256": None})
    for kind in owner.census.get("unclassified_model_event_kinds", []):
        gaps.append({"reason_code": "unsupported_model_event", "kind_sha256": digest(kind), "input_sha256": None})
    outcome_only_gaps = []
    outcome_refs = {value.get("response") for row, value in events.values()
        if row["kind"] == "model.attempt.completed" and tasks.get(value.get("attempt"), {}).get("disposition") in {"pair_reference", "nonpair_screening"}}
    for identity, disposition in covered.items():
        if disposition["disposition"] == "physical_result_view":
            outcome_refs.add(rows[identity][1].get("response"))
        elif disposition["disposition"] == "nonpair_article_subresult":
            outcome_refs.add(rows[identity][1].get("submission"))
    outcome_refs.discard(None)
    task_refs = {task[key] for task in tasks.values() for key in ("request_artifact", "dispatch_artifact") if key in task}
    for gap in owner.gaps:
        reason = gap.get("reason_code")
        evidence = {"reason_code": "inherited_inventory_gap", "evidence_sha256": digest(gap),
                    "input_sha256": deepcopy(gap.get("affected_input_sha256"))}
        is_outcome = reason == "declared_artifact_missing" and gap.get("artifact") in outcome_refs - task_refs
        if reason == "attempt_artifact_reference_missing" and gap.get("field") == "response":
            is_outcome = any(row["event_hash"] == gap.get("event_hash") and row["kind"] == "model.attempt.completed"
                and tasks.get(value.get("attempt"), {}).get("disposition") in {"pair_reference", "nonpair_screening"}
                for row, value in events.values())
        if is_outcome:
            outcome_only_gaps.append({**evidence, "discharge_rule": "known_task_response_not_required_for_semantics"})
        else:
            gaps.append(evidence)
    # Every completion must belong to the physical intent census, even if no
    # semantic response was retained. It cannot manufacture a fresh attempt.
    completions = [value for row, value in events.values() if row["kind"] == "model.attempt.completed"]
    require(all(value.get("attempt") in intents for value in completions), "orphan_completion")
    require(len({v["attempt"] for v in completions}) == len(completions), "duplicate_completion")
    prepared = []
    links = []
    for identity, selected in plans.items():
        count = len(selected["plan"]["pairs"]) if selected["kind"] == "pair" else len(selected["batches"]) if selected["kind"] == "astra" else 1
        first = 1 if selected["kind"] == "pair" else 0
        prepared.extend({"plan_record": identity, "family": selected["family"], "slot": slot, "physical_attempt_created": False}
                        for slot in range(first, first + count) if identity not in unlocalized_plan_attempts and (identity, slot) not in attempted)
        for key in ("prior_validation", "prior_review_owners", "source_owner"):
            if selected["plan"].get(key):
                links.append({"plan_record": identity, "field": key, "link_value_sha256": digest(selected["plan"][key]),
                              "discovery_resolved_here": False})
    intent_ids, partition = sorted(intents), sorted(tasks)
    require(intent_ids == partition and set(covered).isdisjoint(unresolved_records)
        and set(covered) | set(unresolved_records) == set(rows), "partition_set_equality")
    result = {"version": VERSION, "policy": POLICY, "implementation": implementation(),
        "source_id": source_id, "source_head": deepcopy(owner.scope["source_head"]), "scope_sha256": digest(owner.scope),
        "input_index_digest": index.digest, "history_census_sha256": digest(owner.census),
        "dispositions": list(tasks.values()), "record_dispositions": covered, "unclassified_record_ids": unresolved_records,
        "event_dispositions": event_covered, "unclassified_event_hashes": event_unknown,
        "prepared_only": prepared, "possible_pair_gaps": gaps, "physical_origin_gaps": provenance_gaps,
        "outcome_only_inventory_gaps": outcome_only_gaps,
        "linked_origin_requirements": requirements, "other_owner_links": links,
        "census": {"expected_intent_ids": intent_ids, "classified_intent_ids": partition,
            "intent_set_sha256": digest(intent_ids), "expected_record_ids": sorted(rows),
            "classified_record_ids": sorted(covered), "unclassified_record_ids": unresolved_records,
            "record_set_sha256": digest(sorted(rows)), "physical_intent_count": len(intents),
            "expected_event_hashes": sorted(r["event_hash"] for r, _ in events.values()),
            "classified_event_hashes": sorted(event_covered), "unclassified_event_hashes": event_unknown,
            "event_partition_exact": set(event_covered).isdisjoint(event_unknown) and
                set(event_covered) | set(event_unknown) == {r["event_hash"] for r, _ in events.values()},
            "completion_count": len(completions), "disposition_counts": dict(Counter(t["disposition"] for t in tasks.values())),
            "intent_partition_exact": True, "record_partition_exact": True},
        "inspected_task_semantics_complete": not gaps, "verified_physical_origin_census_complete": not gaps and not provenance_gaps,
        "upstream_inventory_scope_complete": owner.census.get("scope_complete") is True,
        "full_manual_event_inventory_verified": False,
        "historical_discovery_complete": False, "creates_pair_y": False, "establishes_P": False,
        "limitations": "Exact supported native tasks at the supplied audited cutoff only. Outcome and P availability do not determine task role. Unrecognized records/omissions remain possible pair tasks. Source/archive provenance and discovery of other owners/manual histories remain upstream. No historical labels are reused as current Y."}
    result["manifest_sha256"] = digest(result)
    return result


def merge_verified_dispositions(manifests):
    """Deduplicate proven copies; never turn unresolved origins into new tasks."""
    by_id, unresolved = {}, []
    for manifest in manifests:
        require(manifest.get("version") == VERSION and manifest.get("manifest_sha256") == digest({k: v for k, v in manifest.items() if k != "manifest_sha256"}), "manifest_digest")
        for task in manifest["dispositions"]:
            if not task["origin_verified"]:
                unresolved.append({"source_id": manifest["source_id"], "view_attempt": task["view_attempt"]})
                continue
            identity = task["canonical_physical_id"]
            core = {k: task[k] for k in ("physical_identity", "disposition", "family", "plan_record", "request_artifact", "dispatch_artifact", "source_identities")}
            if identity in by_id:
                require(_same(by_id[identity]["core"], core), "copied_physical_task_conflict")
            else:
                by_id[identity] = {"core": core, "views": []}
            by_id[identity]["views"].append({"source_id": manifest["source_id"], "intent_event": task["intent_event"]})
    return {"physical_tasks": by_id, "unresolved_origin_views": unresolved,
            "whole_history_complete": False, "input_manifests": [m["manifest_sha256"] for m in manifests]}
