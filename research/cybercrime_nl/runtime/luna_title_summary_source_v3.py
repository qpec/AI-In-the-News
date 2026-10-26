"""Bounded exact import of the completed V2 title-summary owner.

Only fixed metadata references and actually attempted packet artifacts are read.
Bulk queued packet bodies and ancestor owners are not opened. Large wire evidence
is hash-verified in place; successful parsed outputs and the inherited source are
embedded in one new protected derived import. No provider or research writer is reopened.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

import luna_title_summary_run_v2 as run
import luna_title_summary_source_v2 as previous
from newsresearch.common import digest, require_active
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

base, retained = previous.base, previous.retained
require = base.require
METHOD = "luna-title-summary-completed-continuation-import-v3"
PREFLIGHT = "luna_title_summary_import_preflight_v3"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-title-summary-20261025-v2")
PLAN = "aebeac7281f78913aeb3465618e22ebdbc01951c5bde6651950349bf05b619c5"
REPORT = "cc0494bb9569298c2ffcda33ba298d3e898ab461f96374b9dcf52fd3a39e2a6e"
SUCCESSOR = "b72c3b9ac759087101ffe7af799f712e0cbd7c04d36b0908c927ba4c87a9e1a3"
REPAIR_COMMITMENT, VALIDATION_COMMITMENT = 19_239_038_002, 6_129_023_256
POLICY = {**previous.POLICY, "source_scope": "one_completed_title_summary_continuation_owner",
    "maximum_attempts": 10_000, "maximum_selected_bytes": 16*1024**3,
    "maximum_copied_bytes": 3*1024**3, "maximum_seconds": 1800,
    "bulk_queued_packet_bodies_replayed": False, "physical_packet_bodies_replayed": True,
    "response_bodies_replayed": True, "large_wire_artifacts_copied": False, "selected_artifacts_copied": False,
    "required_prior_commits": None, "original_frozen_selection_reused": True}


def binding():
    return {"plan_record": PLAN, "report_record": REPORT, "successor_artifact": SUCCESSOR}


def implementation():
    return {**run.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class Reader(previous.Reader):
    """Verify transient wire bytes without duplicating thousands of full sources."""
    def __init__(self, *args, **kwargs):
        self.transient = set()
        self.verified_transient = {}
        super().__init__(*args, **kwargs)

    def artifact_bytes(self, reference):
        if reference not in self.transient:
            return super().artifact_bytes(reference)
        self._active()
        retained.frozen.source_api._sha(reference)
        require(self.allowed is not None and reference in self.allowed, "v3_reference_allowlist")
        path = self.owner/"objects"/reference
        check_permissions(path)
        require(self.artifact_size(reference) == self.allowed[reference], "v3_transient_size")
        raw = path.read_bytes()
        require(len(raw) == self.allowed[reference] and hashlib.sha256(raw).hexdigest() == reference,
            "v3_transient_hash")
        self.verified_transient[reference] = len(raw)
        require(sum(self.verified_transient.values())+self.unique_bytes <= POLICY["maximum_selected_bytes"],
            "v3_read_limit")
        self._active()
        return raw


def preflight(reader, metadata, engine, session, progress):
    require(metadata["source_head"] == reader.head(), "v3_preflight_head")
    rows = list(reader.db.execute("SELECT * FROM records ORDER BY created_event"))
    selected = {r["id"]: r for r in rows}
    require(PLAN in selected and REPORT in selected and selected[PLAN]["kind"] == run.PLAN
        and selected[REPORT]["kind"] == run.RESULT, "v3_fixed_records")
    refs, transient = defaultdict(list), set()
    def add(ref, kind, identity, field, *, wire=False):
        if ref is None:
            return
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"kind": kind, "identity": identity, "field": field})
        if wire:
            transient.add(ref)
    fields = {run.PLAN: ("import_artifact", "selection_artifact", "quote_artifact", "method_artifact", "diagnostic_artifact"),
        run.RESULT: ("successor_artifact", "change_manifest_artifact", "coverage_artifact", "pair_observations_artifact", "deferred_artifact"),
        run.RESPONSE: ("parsed",), run.CHECKPOINT: ("coverage_artifact", "summaries_artifact", "search_results_artifact", "candidate_pairs_artifact"),
        run.COMMIT: ("changes_artifact",)}
    for row in rows:
        add(row["artifact"], row["kind"], row["id"], "artifact")
        value = json.loads(row["payload"])
        for field in fields.get(row["kind"], ()):
            add(value.get(field), row["kind"], row["id"], field)
    event_fields = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",),
        "model.attempt.intended": ("packet", "request", "dispatch"), run.RECEIVED: ("response",)}
    attempts = 0
    for row in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        attempts += row["kind"] == "model.attempt.intended"
        value = json.loads(row["payload"])
        for field in event_fields.get(row["kind"], ()):
            add(value[field], row["kind"], row["event_hash"], field,
                wire=row["kind"] in {"model.attempt.intended", run.RECEIVED})
    require(attempts <= POLICY["maximum_attempts"], "v3_attempt_bound")
    transient = set(refs)
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "anchors": anchors,
        "copy": ref not in transient} for ref, anchors in sorted(refs.items())]
    total, copied = sum(e["bytes"] for e in entries), sum(e["bytes"] for e in entries if e["copy"])
    manifest = {"method": METHOD, "binding": binding(), "owner": str(reader.owner), "head": reader.head(),
        "entries": entries, "total_distinct_bytes": total, "copied_bytes_upper": copied,
        "distinct_references": len(entries), "maximum_selected_bytes": POLICY["maximum_selected_bytes"],
        "maximum_copied_bytes": POLICY["maximum_copied_bytes"],
        "fits": total <= POLICY["maximum_selected_bytes"] and copied <= POLICY["maximum_copied_bytes"],
        "physical_attempts": attempts, "ancestor_artifact_references_followed": False,
        "bulk_queue_artifact_references_followed": False}
    ref = engine.ledger.artifacts.put(manifest)
    identity = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "implementation": implementation(),
        "binding": binding(), "manifest_artifact": ref, "fits": manifest["fits"]})
    progress("title_v3_size_preflight", selected_bytes=total, copied_bytes_upper=copied,
        references=len(entries), fits=manifest["fits"])
    require(manifest["fits"], "v3_selected_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
    reader.transient = transient
    return manifest, ref, identity


def authority(reader):
    plan, intent, seed, report = (base.one(reader, kind, identity) for kind, identity in
        ((run.PLAN, PLAN), (run.INTENT, None), (run.SEED, None), (run.RESULT, REPORT)))
    reader.ensure_report_last(report)
    for row, key in ((plan, run.METHOD), (intent, run.METHOD), (seed, intent["_record_id"]), (report, PLAN)):
        base.keyed(reader, row, key)
    code = run.implementation()
    require(plan["implementation"] == code and plan["method"] == report["method"] == run.METHOD
        and plan["policy"] == report["policy"] == run.POLICY and plan["approval"] == run.APPROVAL
        and plan["intent"] == intent["_record_id"] and plan["seed_record"] == seed["_record_id"]
        and all(digest(plan.get(k)) == digest(v) for k, v in base.plain(intent).items()), "continuation_plan_authority")
    require(seed["method"] == run.METHOD and seed["intent"] == intent["_record_id"] and seed["draw_performed"] is False
        and intent["_created_event"] < seed["_created_event"] < plan["_created_event"]
        and report["plan"] == PLAN and report["prepared"] is True and report["title_summary_finished"] is True
        and report["successor_artifact"] == SUCCESSOR
        and report["terminal_reason"] == "single_pass_finished", "continuation_native_scope")
    require(reader.artifact_bytes(plan["method_artifact"]) == run.SPEC.read_bytes(), "continuation_method_bytes")
    expected = run.versions(base.plain(intent))
    require(set(plan["versions"]) == set(expected), "continuation_version_set")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, run.METHOD))]
        require(ids == [plan["versions"][kind]], "continuation_version_identity")
        row = reader.record(ids[0], kind)
        base.keyed(reader, row, run.METHOD)
        require(row["content"] == content and row["branch"] == "main" and row["reason"] is None
            and intent["_created_event"] < row["_created_event"] < seed["_created_event"], "continuation_version_binding")
    events, prep = base.session_prefix(reader, plan["_created_event"], code, {"action": "prepare"})
    done, ended = ([r for r in events if r["kind"] == k] for k in ("operation.completed", "session.ended"))
    require(len(done) == len(ended) == 1 and not any(r["kind"] == "operation.failed" for r in events)
        and seed["_created_event"] in {r["seq"] for r in events}
        and plan["_created_event"] < done[0]["seq"] < ended[0]["seq"]
        and json.loads(ended[0]["payload"]) == {"status": "completed"}, "continuation_prepare_completed")
    output = json.loads(done[0]["payload"])
    prepared = reader.artifact(output["result"])
    require(output["operation"] == "status" and prepared["method"] == run.METHOD and prepared["plan"] == PLAN
        and prepared["prepared"] is True and prepared["attempted_requests"] == 0, "continuation_prepare_output")
    completed = retained.completed(reader, report, code)
    require(reader.artifact(completed["input"]) == {"action": "run", "allow_paid_execution": True}, "continuation_report_operation")
    imported = reader.artifact(plan["import_artifact"])
    provenance = imported["provenance"]
    require(plan["source_binding"] == provenance["binding"] == previous.binding()
        and provenance["method"] == previous.METHOD and provenance["implementation"] == previous.implementation()
        and Path(provenance["owner"]) == previous.OWNER and provenance["plan_record"] == previous.PLAN
        and provenance["report_record"] == previous.REPORT and provenance["state_artifact"] == previous.SUCCESSOR
        and provenance["source_head_unchanged"] is True and digest(imported["state"]) == previous.SUCCESSOR
        and imported["accounting"]["repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        and imported["accounting"]["validation_commitment_nanousd"] == VALIDATION_COMMITMENT,
        "continuation_parent_import")
    checkpoint = reader.record(provenance["size_preflight_record"], previous.PREFLIGHT)
    base.keyed(reader, checkpoint, provenance["size_manifest_artifact"])
    require(checkpoint["method"] == previous.METHOD and checkpoint["implementation"] == previous.implementation()
        and checkpoint["binding"] == previous.binding() and checkpoint["fits"] is True
        and checkpoint["manifest_artifact"] == provenance["size_manifest_artifact"]
        and intent["_created_event"] < checkpoint["_created_event"] < seed["_created_event"]
        and checkpoint["_created_event"] in {r["seq"] for r in events}, "continuation_parent_checkpoint")
    require(reader.artifact(plan["diagnostic_artifact"]) == imported["diagnostic"]
        and imported["diagnostic"]["scope_admission_allowed"] is True, "continuation_parent_admission")
    selection = reader.artifact(plan["selection_artifact"])
    run.design._verify(selection, "continuation_selection")
    run.design._verify(selection["selection"], "continuation_draw")
    require(selection["selection"]["seed"] == seed["seed"] and selection["selection"]["state_sha256"] == previous.SUCCESSOR
        and reader.artifact(plan["quote_artifact"]) == selection["quote"]

        and selection == imported["continuation"]["selection"]
        and report["pilot"] == imported["continuation"]["pilot"]
        and report["pilot"]["passed"] is False and report["original_pilot_preserved"] is True
        and report["retrieval_quality_gate_passed"] is False, "continuation_preserved_design")

    return plan, report, imported, selection, {"prepare": {**prep, "output": output["result"]}, "report": completed}


def physical(reader, plan, report, imported, progress):
    """Replay selected attempted packets, receipts and deterministic assessments."""
    launch = base.one(reader, run.LAUNCH)
    base.keyed(reader, launch, PLAN)
    require(launch["plan"] == PLAN and launch["implementation"] == plan["implementation"]
        and launch["allow_paid_execution"] is True and launch["restart_allowed"] is False
        and plan["_created_event"] < launch["_created_event"] < report["_created_event"], "v3_launch")
    events, proof = base.session_prefix(reader, launch["_created_event"], plan["implementation"],
        {"action": "run", "allow_paid_execution": True})
    sequences = {r["seq"] for r in events}
    queues = {}
    for row in reader.rows(run.QUEUE):
        base.keyed(reader, row, row["name"])
        require(row["plan"] == PLAN and row["implementation"] == plan["implementation"]
            and row["_created_event"] in sequences, "v3_queue_scope")
        queues[row["_record_id"]] = row
    assessments = {}
    for row in reader.rows(run.RESPONSE):
        base.keyed(reader, row, row["attempt"])
        require(row["plan"] == PLAN and row["attempt"] not in assessments
            and row["_created_event"] in sequences, "v3_assessment_scope")
        assessments[row["attempt"]] = row
    event_rows = {}
    for kind in ("model.attempt.intended", run.RECEIVED, "model.attempt.completed"):
        values = {}
        for event in reader.db.execute("SELECT * FROM events WHERE kind=? ORDER BY seq", (kind,)):
            value = json.loads(event["payload"])
            require(value["attempt"] not in values and event["seq"] in sequences
                and launch["_created_event"] < event["seq"] < report["_created_event"], "v3_attempt_scope")
            values[value["attempt"]] = {**value, "_seq": event["seq"], "_event_hash": event["event_hash"]}
        event_rows[kind] = values
    intended, received, completed = (event_rows[k] for k in
        ("model.attempt.intended", run.RECEIVED, "model.attempt.completed"))
    require(len(intended) <= POLICY["maximum_attempts"] and set(completed) <= set(assessments)
        <= set(received) <= set(intended), "v3_attempt_partition")
    facts, intents, responses, parsed_rows, summaries, search = [], {}, {}, {}, {}, {}
    categories = {"pilot": 0, "discovery": 0, "verification": 0}
    counters = Counter(new_settled_nanousd=0, new_held_nanousd=0, unknown_holds=0, usable_requests=0)
    logical = set(imported["history"].get("logical_ids", []))
    tasks = set(imported["history"].get("task_keys", []))
    for n, (attempt, row) in enumerate(intended.items(), 1):
        queue = queues.get(row["queue"])
        require(queue is not None and queue["_created_event"] < row["_seq"] and row["method"] == run.METHOD
            and row["batch"] == PLAN and row["category"] == queue["category"] in categories
            and row["number"] == 1 and row["task_key"] not in tasks, "v3_intent_binding")
        packet = reader.artifact(row["packet"])
        require(digest(packet) == row["packet"] and packet["task_key"] == row["task_key"]
            and row["request"] == packet["request_sha256"] == digest(packet["request"])
            and row["reserved_nanousd"] == packet["reservation_nanousd"] == run.contract.reservation(packet)
            and packet["role"] in run.continuation.ROLES and not logical.intersection(packet["logical_ids"]),
            "v3_packet_identity")
        require(reader.artifact(row["request"]) == packet["request"]
            and reader.artifact(row["dispatch"]) == run.wire.Invocation(packet["request"], attempt,
                kind=packet["kind"]).manifest(), "v3_wire_identity")
        logical.update(packet["logical_ids"])
        tasks.add(row["task_key"])
        receipt, assessment, completion = received.get(attempt), assessments.get(attempt), completed.get(attempt)
        derived, parsed, cost = None, None, None
        if receipt:
            require(receipt["_seq"] > row["_seq"], "v3_receipt_order")
            envelope = ProviderResponse(**reader.artifact(receipt["response"]))
            derived, parsed = run.outcome(packet, envelope)
            cost = derived["cost_nanousd"]
        if assessment:
            require(assessment["task_key"] == row["task_key"] and assessment["response"] == receipt["response"]
                and receipt["_seq"] < assessment["_created_event"]
                and assessment["parsed"] == (digest(parsed) if parsed is not None else None)
                and all(digest(assessment.get(k)) == digest(v) for k, v in derived.items()), "v3_assessment_replay")
            if parsed is not None:
                require(reader.artifact(assessment["parsed"]) == parsed, "v3_parsed_bytes")
        if completion:
            require(assessment and not assessment["hold"] and completion["assessment"] == assessment["_record_id"]
                and completion["response"] == assessment["response"]
                and completion["_seq"] > assessment["_created_event"] and type(cost) is int and cost >= 0,
                "v3_completion")
            liability = cost
            counters["new_settled_nanousd"] += cost
        else:
            liability = max(row["reserved_nanousd"], cost or 0)
            counters["new_held_nanousd"] += liability
            counters["unknown_holds"] += 1
        categories[row["category"]] += liability
        usable = bool(completion and assessment and assessment["usable"])
        counters["usable_requests"] += usable
        intents[row["task_key"]] = base.plain(row)
        if derived:
            responses[row["task_key"]] = {**(base.plain(assessment) if assessment else derived),
                "task_key": row["task_key"], "attempt": attempt, "usable": usable}
        members = sorted(set(packet.get("members", []) + packet.get("document_ids", []))
            | {v["document_id"] for v in packet.get("source_bindings", {}).values()})
        fact = {"owner": str(reader.owner), "head": reader.head(), "physical_attempt": attempt,
            "task_key": row["task_key"], "role": packet["role"], "category": row["category"],
            "logical_ids": packet["logical_ids"], "members": members, "completed": bool(completion),
            "usable": usable, "hold": not bool(completion), "reserved_nanousd": row["reserved_nanousd"],
            "cost_nanousd": cost, "liability_nanousd": liability, "fatal": (derived or {}).get("fatal"),
            "original_fatal": (derived or {}).get("original_fatal"),
            "is_bound_content_guard": bool((derived or {}).get("local_guard_unavailable")),
            "clarification": bool(packet.get("clarification")), "pair_keys": packet.get("pair_keys", []),
            "artifact_refs": {k: row[k] for k in ("packet", "request", "dispatch")}
                | ({"response_record": assessment["_record_id"], "response": assessment["response"],
                    "parsed": assessment["parsed"]} if assessment else {})}
        if packet["role"] == "article_summary":
            fact["document_id"] = packet["bindings"]["document_id"]
            if usable:
                summaries[fact["document_id"]] = parsed
        elif packet["role"] == "title_search":
            fact["descriptor_digest"] = packet["descriptor"]["digest"]
            fact["descriptor"] = packet["descriptor"]
            if usable:
                search[fact["descriptor_digest"]] = parsed
        elif packet["role"] == "development":
            fact["pairs"] = run.packet_pairs(packet)
        else:
            fact["membership_revision"] = packet["membership_revision"]
            require(fact["membership_revision"] == digest(packet["members"]), "v3_membership_revision")
            if packet["role"] == "group_quality":
                fact["card"] = packet["card"]
        if usable:
            parsed_rows[row["task_key"]] = parsed
        facts.append(fact)
        if n % 100 == 0 or n == len(intended):
            progress("title_v3_replaying_attempts", physical_attempts=n, total=len(intended))
    carried = imported["continuation"]
    order = [f["task_key"] for f in carried["physical_facts"]]
    old_intents = {k: carried["carried_intents"][k] for k in order}
    old_responses = {k: carried["carried_responses"][k] for k in order if k in carried["carried_responses"]}
    health = run.continuation.health_state(intents, responses, carried_intents=old_intents, carried_responses=old_responses)
    expected = {**counters, "attempted_requests": len(intents), "returned_requests": len(received),
        "category_commitments_nanousd": categories, "health": health}
    require(all(digest(report[k]) == digest(v) for k, v in expected.items())
        and counters["new_settled_nanousd"]+counters["new_held_nanousd"] == report["new_committed_nanousd"]
        and run.PRIOR_COMMITMENT+report["new_committed_nanousd"] == REPAIR_COMMITMENT
        == report["combined_repair_commitment_nanousd"]
        and report["validation_commitment_nanousd"] == VALIDATION_COMMITMENT, "v3_accounting")
    return {"facts": facts, "intents": intents, "responses": responses, "parsed": parsed_rows,
        "summaries": summaries, "search": search, "categories": categories, "counters": dict(counters),
        "health": health, "launch_proof": proof}


def projections(reader, plan, report, imported, selection, census):
    """Bind reusable parsed results to native checkpoints and replay committed changes."""
    old = imported["continuation"]
    summaries = {**old["summaries"], **census["summaries"]}
    results = {**old["search_results"], **census["search"]}
    old_summary_ids, old_blocks = set(old["attempted_summary_ids"]), set(old["attempted_descriptor_digests"])
    summary_ids, block_ids = set(old_summary_ids), set(old_blocks)
    descriptors = {d["digest"]: d for d in selection["descriptors"]}
    for fact in census["facts"]:
        if fact["role"] == "article_summary":
            identity = fact["document_id"]
            require(identity not in summary_ids and identity in selection["summary_quotes"], "v3_summary_retry")
            summary_ids.add(identity)
        if fact["role"] == "title_search":
            key = fact["descriptor_digest"]
            require(key not in block_ids and descriptors.get(key) == fact["descriptor"], "v3_block_retry")
            block_ids.add(key)
    checkpoints = reader.rows(run.CHECKPOINT)
    pilot_rows = [r for r in checkpoints if "pilot" in r]
    require(len(pilot_rows) == 1 and pilot_rows[0]["pilot"] == old["pilot"] == report["pilot"]
        and not report["pilot"]["passed"], "v3_original_pilot")
    coverage, candidates, units = {}, {tuple(p) for p in old["candidates"]}, set()
    for checkpoint in checkpoints:
        require(checkpoint["plan"] == PLAN and plan["_created_event"] < checkpoint["_created_event"]
            < report["_created_event"], "v3_checkpoint_scope")
        if "work_unit" not in checkpoint:
            continue
        unit = checkpoint["work_unit"]
        base.keyed(reader, checkpoint, f"unit-{unit}/discovery")
        require(unit not in units and 0 <= unit < len(selection["work_units"]), "v3_discovery_unit")
        units.add(unit)
        ids = selection["work_units"][unit]
        blocks = [d for d in selection["descriptors"] if d["work_unit"] == unit]
        expected_summaries = {i: summaries[i] for i in ids if i in summaries}
        expected_search = [results[d["digest"]] for d in blocks if d["digest"] in results]
        require(reader.artifact(checkpoint["summaries_artifact"]) == expected_summaries
            and reader.artifact(checkpoint["search_results_artifact"]) == expected_search, "v3_successful_checkpoint")
        current, pairs = {}, set()
        for identity in ids:
            intended = [d for d in blocks if identity in d["query_ids"]]
            outputs = [next(r for r in results[d["digest"]]["results"] if r["query_id"] == identity)
                for d in intended if d["digest"] in results]
            pairs.update(tuple(sorted((identity, other))) for row in outputs for other in row["candidate_ids"])
            reason = None
            if identity not in summaries:
                reason = ("historical_summary_unknown_no_retry" if identity in old_summary_ids
                    else selection["summary_unavailable"].get(identity)
                    or ("summary_unknown" if identity in summary_ids else "summary_unattempted"))
            current[identity] = {"work_unit": unit, "summary_usable": identity in summaries,
                "planned_blocks": len(intended), "returned_blocks": len(outputs),
                "eligible_title_blocks_complete": bool(intended)
                    and not any(identity in r["query_ids"] for r in selection["capacity_unavailable"])
                    and len(outputs) == len(intended) and all(r["complete"] for r in outputs),
                "unavailable_other_titles": len(selection["catalogue"]["unavailable"])
                    - int(identity in selection["catalogue"]["unavailable"]),
                "intended_other_titles": len(imported["source"]["documents"])-1,
                "candidate_count": len({j for r in outputs for j in r["candidate_ids"]}),
                "reason": reason, "uniqueness_established": False}
        require(reader.artifact(checkpoint["coverage_artifact"]) == current
            and reader.artifact(checkpoint["candidate_pairs_artifact"]) == [list(p) for p in sorted(pairs)],
            "v3_coverage_projection")
        coverage.update(current)
        candidates.update(pairs)
    require(units == set(range(len(selection["work_units"])))
        and reader.artifact(report["coverage_artifact"]) == coverage
        and report["queries_processed"] == report["queries_selected"] == len(coverage) == len(selection["query_order"])
        and report["summaries_usable"] == len(summaries) and report["title_blocks_usable"] == len(results)
        and report["eligible_title_coverage_complete"] == sum(r["eligible_title_blocks_complete"] for r in coverage.values())
        and report["unique_candidate_pairs"] == report["candidate_pairs_entering_verifier"] == len(candidates),
        "v3_final_discovery")
    state, changes, previous_unit = deepcopy(imported["state"]), [], -1
    commits = reader.rows(run.COMMIT)
    for row in commits:
        base.keyed(reader, row, f"unit-{row['work_unit']}")
        require(row["plan"] == PLAN and row["versions"] == plan["versions"]
            and row["before_sha256"] == digest(state) and row["work_unit"] == previous_unit+1
            and plan["_created_event"] < row["_created_event"] < report["_created_event"], "v3_commit_chain")
        current = reader.artifact(row["changes_artifact"])
        state = run.repair.commit(state, current, reason=f"{run.METHOD}/unit-{row['work_unit']}")
        require(digest(state) == row["successor_artifact"] and run.statistics(state) == row["after"], "v3_commit_replay")
        changes.extend(current)
        previous_unit = row["work_unit"]
    require(state == reader.artifact(SUCCESSOR) and digest(state) == SUCCESSOR
        and reader.artifact(report["change_manifest_artifact"]) == changes
        and report["changes"] == len(changes) and report["committed_work_units"] == len(commits) == len(units)+1
        and report["before"] == run.statistics(imported["state"]) and report["after"] == run.statistics(state),
        "v3_successor")
    observations = run.repair.observations_by_pair(imported["history"].get("pair_observations", []))
    for fact in census["facts"]:
        if fact["role"] == "development" and fact["usable"]:
            for row in census["parsed"][fact["task_key"]]["observations"]:
                observations.setdefault(row["pair_key"], []).append(row)
    require(reader.artifact(report["pair_observations_artifact"]) == observations, "v3_pair_projection")
    deferred = reader.artifact(report["deferred_artifact"])
    require(set(deferred) == {"pair_keys", "memberships"}
        and report["overlap_deferred_memberships"] == len(deferred["memberships"]), "v3_deferrals")
    categories = {k: old["category_commitments_nanousd"][k]+census["categories"][k] for k in census["categories"]}
    facts = [*old["physical_facts"], *census["facts"]]
    require(len({f["physical_attempt"] for f in facts}) == len(facts), "v3_physical_repeat")
    continuation = {"plan_record": PLAN, "report_record": REPORT, "selection": selection,
        "original_selection_state_sha256": selection["selection"]["state_sha256"],
        "summaries": summaries, "search_results": results, "coverage": coverage,
        "candidates": [list(p) for p in sorted(candidates)], "pilot": deepcopy(old["pilot"]),
        "attempted_summary_ids": sorted(summary_ids), "attempted_descriptor_digests": sorted(block_ids),
        "category_commitments_nanousd": categories, "physical_facts": facts,
        "current_physical_facts": census["facts"],
        "carried_intents": {**old["carried_intents"], **census["intents"]},
        "carried_responses": {**old["carried_responses"], **census["responses"]},
        "deferred_pair_keys": deferred["pair_keys"], "deferred_memberships": deferred["memberships"],
        "original_pilot_passed": False}
    return state, observations, continuation


def history_projection(imported, census, observations, continuation):
    history = deepcopy(imported["history"])
    facts = census["facts"]
    require(not {f["physical_attempt"] for f in facts}
        & {f["physical_attempt"] for f in history.get("physical_attempts", [])}, "v3_history_overlap")
    history.setdefault("physical_attempts", []).extend(facts)
    history["pair_observations"] = [row for rows in observations.values() for row in rows]
    logical, tasks = set(history.get("logical_ids", [])), set(history.get("task_keys", []))
    pairs, memberships = history.setdefault("pair_attempts", {}), history.setdefault("membership_attempts", {})
    pending = {}
    for fact in facts:
        require(not logical.intersection(fact["logical_ids"]) and fact["task_key"] not in tasks, "v3_history_retry")
        logical.update(fact["logical_ids"])
        tasks.add(fact["task_key"])
        response = census["responses"].get(fact["task_key"], {})
        if fact["role"] == "development":
            for key, pair in fact["pairs"].items():
                prior = pairs.setdefault(key, {"pair_key": key, "pair": pair, "attempts": []})
                prior.setdefault("attempts", []).append({"physical_attempt": fact["physical_attempt"],
                    "task_key": fact["task_key"], "clarification": fact["clarification"],
                    "usable": fact["usable"], "hold": fact["hold"]})
            if fact["usable"] and not fact["clarification"]:
                for row in census["parsed"][fact["task_key"]]["observations"]:
                    if row["label"] == "unknown" and row.get("semantic_unknown"):
                        pending[row["pair_key"]] = {"pair": row["pair"], "primary_task_key": fact["task_key"],
                            "primary_attempt": fact["physical_attempt"],
                            "primary_logical_id": run.contract.identity(imported["source"], row["pair"], "development", False),
                            "primary_observation_sha256": digest(row)}
        elif fact["role"] in {"group_membership", "group_quality"}:
            revision = fact["membership_revision"]
            item = memberships.setdefault(revision, {"members": fact["members"]})
            stage = "member" if fact["role"] == "group_membership" else "card"
            require(not item.get(stage+"_attempted"), "v3_membership_stage_repeat")
            item[stage+"_attempted"] = True
            item[stage+"_supported"] = bool(fact["usable"] and response.get(
                "members_supported" if stage == "member" else "group_supported"))
            item.setdefault("stage_attempts", {})[stage] = fact["physical_attempt"]
            if stage == "card" and item["card_supported"]:
                item["card"] = fact["card"]
            if not item[stage+"_supported"]:
                item["blocked"] = True
    blocked_clarifications = {key for f in continuation["physical_facts"] if f.get("clarification") for key in f.get("pair_keys", [])}
    continuation["pending_clarifications"] = {key: value for key, value in pending.items()
        if key not in blocked_clarifications and all(run.contract.identity(imported["source"], value["pair"], role, True)
            not in logical for role in ("development", "final_reference"))}
    history.update(logical_ids=sorted(logical), task_keys=sorted(tasks), current_title_attempts=facts,
        title_summary_attempts=continuation["attempted_summary_ids"], title_block_attempts=continuation["attempted_descriptor_digests"])
    history["development_exposed_documents"] = sorted(set(history.get("development_exposed_documents", []))
        | {i for f in facts for i in f["members"]})
    history.setdefault("historical_fatal_cases", []).extend(f for f in facts if f["fatal"] or f.get("original_fatal"))
    return history


def collect(engine, session, *, binding=None, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "v3_offline_only")
    desired = globals()["binding"]()
    require(binding is None or binding == desired, "v3_fixed_binding")
    started = time.monotonic()
    deadline = started+POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline)
        and 0 < deadline-started <= POLICY["maximum_seconds"], "v3_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-started, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("title_v3_opening_completed_owner")
        liveness = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest, manifest_ref, preflight_record = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, proof = authority(reader)
        census = physical(reader, plan, report, imported, progress)
        state, observations, continuation = projections(reader, plan, report, imported, selection, census)
        history = history_projection(imported, census, observations, continuation)
        accounting = deepcopy(imported["accounting"])
        repair = accounting["repair"]
        repair["settled_nanousd"] += census["counters"]["new_settled_nanousd"]
        repair["held_nanousd"] += census["counters"]["new_held_nanousd"]
        repair["committed_nanousd"] = REPAIR_COMMITMENT
        require(repair["settled_nanousd"]+repair["held_nanousd"] == REPAIR_COMMITMENT, "v3_liability_sum")
        accounting.update(repair_commitment_nanousd=REPAIR_COMMITMENT,
            combined_committed_nanousd=REPAIR_COMMITMENT+VALIDATION_COMMITMENT, categories_mixed=False)
        diagnostic = {"scope_admission_allowed": census["health"]["stop_reason"] is None,
            "fatal_cases": history["historical_fatal_cases"], "historical_fatal_cleared": False,
            "original_pilot_passed": False, "discarded_content_recovered": False,
            "quarantined_document_ids": history["quarantine_document_ids"],
            "counts": {"retained_summaries": len(continuation["summaries"]),
                "retained_search_blocks": len(continuation["search_results"]),
                "retained_candidate_pairs": len(continuation["candidates"]),
                "current_title_attempts": len(census["facts"]), "unknown_holds": census["counters"]["unknown_holds"],
                "inherited_title_attempts": len(continuation["physical_facts"])-len(census["facts"]),
                "original_pilot_recovered": continuation["pilot"]["recovered"],
                "pending_semantic_clarifications": len(continuation["pending_clarifications"])}}
        reader._active()
        require(not reader.copied and reader.unique_bytes == 0
            and all(reader.allowed[k] == v for k, v in reader.verified_transient.items()), "v3_read_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "v3_source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        liveness.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "v3_implementation_changed")
        verified_bytes = sum(reader.verified_transient.values())
        progress("title_v3_import_complete", **diagnostic["counts"], unique_source_artifact_bytes_read=verified_bytes)
        return {**imported, "state": state, "history": history, "accounting": accounting, "diagnostic": diagnostic,
            "prior_commitment_nanousd": REPAIR_COMMITMENT, "continuation": continuation,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "binding": desired,
                "owner": str(owner), "head": head, "plan_record": PLAN, "report_record": REPORT, "state_artifact": SUCCESSOR,
                "parent_import_artifact": plan["import_artifact"], "completed_producer": proof,
                "launch": census["launch_proof"], "metadata_census_artifact": engine.ledger.artifacts.put(metadata),
                "size_manifest_artifact": manifest_ref, "size_preflight_record": preflight_record,
                "copied_artifacts": {}, "verified_artifacts_retained_at_source": dict(reader.verified_transient),
                "unique_source_artifact_bytes_read": verified_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": liveness, "elapsed_seconds": round(time.monotonic()-started, 3)}}

