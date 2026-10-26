"""One-owner, bounded import of the completed incomplete title pilot.

The original native census is replayed only for this small title/summary owner.
Ancestor histories are reused from its completed import. No original writer,
failed request retry, pilot replacement or discarded-response recovery exists.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import time

import luna_title_summary_run as run
import luna_title_summary_source as previous
import luna_title_summary_continuation as continuation_api
from newsresearch.common import digest, require_active
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

base, retained, Reader = previous.base, previous.retained, previous.Reader
require = base.require
METHOD = "luna-title-summary-completed-pilot-import-v2"
PREFLIGHT = "luna_title_summary_import_preflight_v2"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-title-summary-20261025-v1")
PLAN = "7b0ab1e5462783e953f612203732f9157d56c3f081fceb809a8d7a5754829b83"
REPORT = "9a725445f722032da1c3de57c929a4e17e7b74ff22afa94c761adda0e3c32e63"
SUCCESSOR = previous.SUCCESSOR
REPAIR_COMMITMENT, VALIDATION_COMMITMENT = 10_090_251_184, 6_129_023_256
POLICY = {**previous.POLICY, "source_scope": "one_completed_title_summary_owner",
    "maximum_attempts": 1000, "physical_packet_bodies_replayed": True,
    "response_bodies_replayed": True, "ancestor_packet_bodies_replayed": False,
    "required_prior_commits": 0, "original_pilot_promoted": False,
    "local_guard_scope": "exact_discarded_http200_response_credentials_only",
    "source_articles_newly_quarantined": False}


def binding():
    return {"plan_record": PLAN, "report_record": REPORT, "successor_artifact": SUCCESSOR}


def implementation():
    return {**continuation_api.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def preflight(reader, metadata, engine, session, progress):
    require(metadata["source_head"] == reader.head(), "continuation_preflight_head")
    rows = list(reader.db.execute("SELECT * FROM records ORDER BY created_event"))
    by_id = {r["id"]: r for r in rows}
    require(PLAN in by_id and REPORT in by_id and by_id[PLAN]["kind"] == run.PLAN
        and by_id[REPORT]["kind"] == run.RESULT, "continuation_fixed_records")
    refs = defaultdict(list)
    def add(ref, kind, identity, field):
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"kind": kind, "identity": identity, "field": field})
    fields = {run.PLAN: ("import_artifact", "selection_artifact", "quote_artifact", "method_artifact", "diagnostic_artifact"),
        run.RESULT: ("successor_artifact", "change_manifest_artifact", "coverage_artifact", "pair_observations_artifact", "deferred_artifact"),
        run.QUEUE: ("packets_artifact",), run.RESPONSE: ("response", "parsed"),
        run.CHECKPOINT: ("coverage_artifact", "summaries_artifact", "search_results_artifact", "candidate_pairs_artifact")}
    for row in rows:
        add(row["artifact"], row["kind"], row["id"], "artifact")
        value = json.loads(row["payload"])
        for field in fields.get(row["kind"], ()):
            if value.get(field) is not None:
                add(value[field], row["kind"], row["id"], field)
    events = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",),
        "model.attempt.intended": ("packet", "request", "dispatch"), run.RECEIVED: ("response",)}
    attempts = 0
    for row in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        attempts += row["kind"] == "model.attempt.intended"
        value = json.loads(row["payload"])
        for field in events.get(row["kind"], ()):
            add(value[field], row["kind"], row["event_hash"], field)
    require(attempts <= POLICY["maximum_attempts"], "continuation_attempt_bound")
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "anchors": anchors}
        for ref, anchors in sorted(refs.items())]
    total = sum(e["bytes"] for e in entries)
    manifest = {"method": METHOD, "binding": binding(), "owner": str(reader.owner), "head": reader.head(),
        "entries": entries, "total_distinct_bytes": total, "distinct_references": len(entries),
        "maximum_selected_bytes": POLICY["maximum_selected_bytes"], "fits": total <= POLICY["maximum_selected_bytes"],
        "physical_attempts": attempts, "ancestor_artifact_references_followed": False}
    ref = engine.ledger.artifacts.put(manifest)
    identity = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "implementation": implementation(),
        "binding": binding(), "manifest_artifact": ref, "fits": manifest["fits"]})
    progress("title_continuation_size_preflight", selected_bytes=total, references=len(entries), fits=manifest["fits"])
    require(manifest["fits"], "continuation_selected_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
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
        and not reader.rows(run.COMMIT) and report["changes"] == report["committed_work_units"] == 0
        and report["successor_artifact"] == SUCCESSOR, "continuation_native_scope")
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
        and provenance["report_record"] == previous.REPORT and provenance["state_artifact"] == SUCCESSOR
        and provenance["source_head_unchanged"] is True and digest(imported["state"]) == SUCCESSOR
        and imported["accounting"]["repair_commitment_nanousd"] == run.PRIOR_COMMITMENT
        and imported["accounting"]["validation_commitment_nanousd"] == VALIDATION_COMMITMENT,
        "continuation_parent_import")
    checkpoint = reader.record(provenance["size_preflight_record"], previous.PREFLIGHT)
    base.keyed(reader, checkpoint, provenance["size_manifest_artifact"])
    require(checkpoint["method"] == previous.METHOD and checkpoint["implementation"] == previous.implementation()
        and checkpoint["binding"] == previous.binding() and checkpoint["fits"] is True
        and checkpoint["manifest_artifact"] == provenance["size_manifest_artifact"]
        and seed["_created_event"] < checkpoint["_created_event"] < plan["_created_event"]
        and checkpoint["_created_event"] in {r["seq"] for r in events}, "continuation_parent_checkpoint")
    require(reader.artifact(plan["diagnostic_artifact"]) == imported["diagnostic"]
        and imported["diagnostic"]["scope_admission_allowed"] is True, "continuation_parent_admission")
    selection = reader.artifact(plan["selection_artifact"])
    run.design._verify(selection, "continuation_selection")
    run.design._verify(selection["selection"], "continuation_draw")
    require(selection["selection"]["seed"] == seed["seed"] and selection["selection"]["state_sha256"] == SUCCESSOR
        and reader.artifact(plan["quote_artifact"]) == selection["quote"]
        and reader.artifact(SUCCESSOR) == imported["state"]
        and reader.artifact(report["change_manifest_artifact"]) == []
        and reader.artifact(report["deferred_artifact"]) == {"pair_keys": [], "memberships": []}
        and reader.artifact(report["pair_observations_artifact"]) == run.repair.observations_by_pair(imported["history"].get("pair_observations", [])),
        "continuation_unchanged_outputs")
    return plan, report, imported, selection, {"prepare": {**prep, "output": output["result"]}, "report": completed}


def physical(reader, plan, report):
    """Use the unchanged native census on this finite current owner only."""
    launch = base.one(reader, run.LAUNCH)
    base.keyed(reader, launch, PLAN)
    require(launch["plan"] == PLAN and launch["implementation"] == plan["implementation"]
        and launch["allow_paid_execution"] is True and launch["restart_allowed"] is False
        and plan["_created_event"] < launch["_created_event"] < report["_created_event"], "continuation_launch")
    events, proof = base.session_prefix(reader, launch["_created_event"], plan["implementation"],
        {"action": "run", "allow_paid_execution": True})
    sequences = {r["seq"] for r in events}
    for kind in (run.QUEUE, run.RESPONSE, run.CHECKPOINT):
        for row in reader.rows(kind):
            key = row["name"] if kind == run.QUEUE else row["attempt"] if kind == run.RESPONSE else (
                "pilot" if "pilot" in row else f"unit-{row['work_unit']}/discovery")
            base.keyed(reader, row, key)
            require(row["plan"] == PLAN and row["_created_event"] in sequences
                and launch["_created_event"] < row["_created_event"] < report["_created_event"], "continuation_record_scope")
    for event in reader.db.execute("SELECT * FROM events WHERE kind LIKE 'model.attempt.%' OR kind=?", (run.RECEIVED,)):
        require(event["kind"] in {"model.attempt.intended", "model.attempt.completed", run.RECEIVED}
            and event["seq"] in sequences and launch["_created_event"] < event["seq"] < report["_created_event"], "continuation_event_scope")
    state = run.TitleSummary.census(retained.AuditView(reader), {"id": PLAN, **base.plain(plan)})
    expected = {"attempted_requests": len(state["intents"]), "returned_requests": state["returned_requests"],
        "queued_requests": len(state["packets"]), "usable_requests": sum(r["usable"] for r in state["responses"].values()),
        "new_settled_nanousd": state["settled_nanousd"], "new_held_nanousd": state["held_nanousd"],
        "unknown_holds": state["unknown_holds"], "category_commitments_nanousd": state["by_category"], "health": state["health"]}
    require(all(digest(report[k]) == digest(v) for k, v in expected.items())
        and state["settled_nanousd"]+state["held_nanousd"] == report["new_committed_nanousd"]
        and run.PRIOR_COMMITMENT+report["new_committed_nanousd"] == report["combined_repair_commitment_nanousd"] == REPAIR_COMMITMENT
        and report["validation_commitment_nanousd"] == VALIDATION_COMMITMENT, "continuation_accounting")
    envelopes = {json.loads(e["payload"])["attempt"]: reader.artifact(json.loads(e["payload"])["response"])
        for e in events if e["kind"] == run.RECEIVED}
    facts, prospective = [], {}
    for task, intended in state["intents"].items():
        packet, assessment = state["packets"][task], state["responses"].get(task)
        require(packet["role"] in {"article_summary", "title_search"} and intended["category"] == "pilot", "continuation_discovery_only")
        done = intended["attempt"] in state["completed"]
        envelope = envelopes.get(intended["attempt"])
        local = bool(envelope and continuation_api.qualifies_local_guard(ProviderResponse(**envelope)))
        if envelope:
            derived, _ = continuation_api.outcome(packet, ProviderResponse(**envelope))
            prospective[task] = {**(assessment or {}), **derived, "attempt": intended["attempt"], "task_key": task,
                "usable": bool(done and derived["usable"]), "original_assessment": assessment}
        facts.append({"owner": str(reader.owner), "head": reader.head(), "physical_attempt": intended["attempt"],
            "task_key": task, "role": packet["role"], "category": intended["category"],
            "logical_ids": packet["logical_ids"], "members": packet["document_ids"], "completed": done,
            "usable": bool(done and assessment and assessment["usable"]), "hold": not done,
            "reserved_nanousd": intended["reserved_nanousd"], "cost_nanousd": assessment["cost_nanousd"] if assessment else None,
            "liability_nanousd": assessment["cost_nanousd"] if done else max(intended["reserved_nanousd"], (assessment or {}).get("cost_nanousd") or 0),
            "fatal": (assessment or {}).get("fatal"), "is_bound_content_guard": local,
            "artifact_refs": {k: intended[k] for k in ("packet", "request", "dispatch")}
                | ({"response_record": assessment["id"], "response": assessment["response"], "parsed": assessment["parsed"]} if assessment else {})})
    return state, facts, {task: envelopes[i["attempt"]] for task, i in state["intents"].items() if i["attempt"] in envelopes}, prospective, proof


def discovery(reader, report, imported, selection, census):
    checkpoints = reader.rows(run.CHECKPOINT)
    discoveries = [r for r in checkpoints if "work_unit" in r]
    pilots = [r for r in checkpoints if "pilot" in r]
    require(len(discoveries) == len(pilots) == 1 and discoveries[0]["work_unit"] == 0, "continuation_checkpoint_set")
    checkpoint = discoveries[0]
    summaries, results = {}, {}
    attempted_summaries, attempted_blocks = [], []
    descriptors = {d["digest"]: d for d in selection["descriptors"] if d["work_unit"] == 0}
    for task, packet in census["packets"].items():
        require(packet["role"] in {"article_summary", "title_search"}, "continuation_packet_scope")
        intended, assessment = census["intents"].get(task), census["responses"].get(task)
        parsed = reader.artifact(assessment["parsed"]) if assessment and assessment["usable"] and assessment["attempt"] in census["completed"] else None
        if packet["role"] == "article_summary":
            identity = packet["bindings"]["document_id"]
            require(identity in selection["work_units"][0]
                and {k: packet[k] for k in selection["summary_quotes"][identity]} == selection["summary_quotes"][identity], "continuation_summary_binding")
            if intended:
                attempted_summaries.append(identity)
            if parsed:
                summaries[identity] = parsed
        else:
            key = packet["descriptor"]["digest"]
            require(key in descriptors and packet["descriptor"] == descriptors[key], "continuation_block_binding")
            if intended:
                attempted_blocks.append(key)
            if parsed:
                results[key] = parsed
    require(len(attempted_summaries) == len(set(attempted_summaries)) and len(attempted_blocks) == len(set(attempted_blocks)), "continuation_logical_repeat")
    require(reader.artifact(checkpoint["summaries_artifact"]) == summaries
        and reader.artifact(checkpoint["search_results_artifact"]) == [results[d["digest"]] for d in descriptors.values() if d["digest"] in results],
        "continuation_successful_checkpoint")
    coverage, candidates = {}, set()
    for i in selection["work_units"][0]:
        blocks = [d for d in descriptors.values() if i in d["query_ids"]]
        outputs = [next(r for r in results[d["digest"]]["results"] if r["document_id"] == i) for d in blocks if d["digest"] in results]
        candidates.update(tuple(sorted([i, c["document_id"]])) for r in outputs for c in r["candidates"])
        reason = selection["summary_unavailable"].get(i)
        if reason is None and i not in summaries:
            reason = "summary_unknown" if i in attempted_summaries else "summary_unattempted"
        coverage[i] = {"work_unit": 0, "summary_usable": i in summaries, "planned_blocks": len(blocks), "returned_blocks": len(outputs),
            "eligible_title_blocks_complete": bool(blocks) and not any(i in r["query_ids"] for r in selection["capacity_unavailable"])
                and len(outputs) == len(blocks) and all(r["complete"] for r in outputs),
            "unavailable_other_titles": len(selection["catalogue"]["unavailable"])-int(i in selection["catalogue"]["unavailable"]),
            "intended_other_titles": len(imported["source"]["documents"])-1,
            "candidate_count": len({c["document_id"] for r in outputs for c in r["candidates"]}), "reason": reason, "uniqueness_established": False}
    candidates = [list(p) for p in sorted(candidates)]
    require(reader.artifact(checkpoint["coverage_artifact"]) == coverage == reader.artifact(report["coverage_artifact"])
        and reader.artifact(checkpoint["candidate_pairs_artifact"]) == candidates, "continuation_discovery_projection")
    pilot = run.design.summarize_pilot(selection, list(results.values()), coverage)
    pilot["passed"] = pilot["threshold_met"] and pilot["all_selected_title_coverage_complete"]
    require(pilot == report["pilot"] == pilots[0]["pilot"] and not pilot["passed"]
        and report["summaries_usable"] == len(summaries) and report["title_blocks_usable"] == len(results)
        and report["queries_processed"] == len(coverage), "continuation_failed_pilot_preserved")
    return {"plan_record": PLAN, "report_record": REPORT, "selection": selection, "summaries": summaries,
        "search_results": results, "coverage": coverage, "candidates": candidates, "pilot": pilot,
        "attempted_summary_ids": sorted(attempted_summaries), "attempted_descriptor_digests": sorted(attempted_blocks),
        "category_commitments_nanousd": dict(census["by_category"]),
        "carried_intents": census["intents"], "carried_responses": census["responses"],
        "original_pilot_passed": False, "candidate_count_is_checkpoint_not_unreached_verification_counter": True}


def collect(engine, session, *, binding=None, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "continuation_offline_only")
    desired = globals()["binding"]()
    require(binding is None or binding == desired, "continuation_fixed_binding")
    started = time.monotonic()
    deadline = started+POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline)
        and 0 < deadline-started <= POLICY["maximum_seconds"], "continuation_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-started, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("title_continuation_opening_completed_owner")
        liveness = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest, manifest_ref, preflight_record = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, proof = authority(reader)
        census, facts, envelopes, prospective, launch = physical(reader, plan, report)
        continuation = discovery(reader, report, imported, selection, census)
        continuation.update(physical_facts=facts, response_envelopes=envelopes,
            original_assessments=census["responses"], carried_responses=prospective)
        history = deepcopy(imported["history"])
        require(not {r["physical_attempt"] for r in facts} & {r["physical_attempt"] for r in history.get("physical_attempts", [])}, "continuation_prior_physical_repeat")
        logical, tasks = set(history.get("logical_ids", [])), set(history.get("task_keys", []))
        for fact in facts:
            require(not logical.intersection(fact["logical_ids"]) and fact["task_key"] not in tasks, "continuation_prior_logical_repeat")
            logical.update(fact["logical_ids"])
            tasks.add(fact["task_key"])
        history.setdefault("physical_attempts", []).extend(facts)
        history.update(logical_ids=sorted(logical), task_keys=sorted(tasks), current_title_attempts=facts,
            title_summary_attempts=continuation["attempted_summary_ids"], title_block_attempts=continuation["attempted_descriptor_digests"])
        history["development_exposed_documents"] = sorted(set(history.get("development_exposed_documents", [])) | {i for f in facts for i in f["members"]})
        fatal = [f for f in facts if f["fatal"]]
        history.setdefault("historical_fatal_cases", []).extend(fatal)
        accounting = deepcopy(imported["accounting"])
        repair = accounting["repair"]
        repair["settled_nanousd"] += census["settled_nanousd"]
        repair["held_nanousd"] += census["held_nanousd"]
        repair["committed_nanousd"] = REPAIR_COMMITMENT
        require(repair["settled_nanousd"]+repair["held_nanousd"] == REPAIR_COMMITMENT, "continuation_liability_sum")
        accounting.update(repair_commitment_nanousd=REPAIR_COMMITMENT,
            combined_committed_nanousd=REPAIR_COMMITMENT+VALIDATION_COMMITMENT, categories_mixed=False)
        diagnostic = {"scope_admission_allowed": bool(fatal) and all(f["is_bound_content_guard"] for f in fatal)
            and census["health"]["stop_reason"] == "response_content_rejected",
            "fatal_cases": [*imported["diagnostic"].get("fatal_cases", []), *fatal], "new_title_fatal_cases": fatal,
            "historical_fatal_cleared": False, "original_pilot_passed": False, "discarded_content_recovered": False,
            "packet_local_unknowns": len(fatal), "quarantined_document_ids": history["quarantine_document_ids"],
            "counts": {"retained_summaries": len(continuation["summaries"]), "retained_search_blocks": len(continuation["search_results"]),
                "retained_candidate_pairs": len(continuation["candidates"]), "current_title_attempts": len(facts),
                "unknown_holds": census["unknown_holds"], "original_pilot_recovered": continuation["pilot"]["recovered"]}}
        reader._active()
        require(set(reader.copied) <= set(reader.allowed) and all(v == reader.allowed[k] for k, v in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "continuation_copy_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "continuation_source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        liveness.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "continuation_implementation_changed")
        progress("title_continuation_import_complete", **diagnostic["counts"], unique_source_artifact_bytes_read=reader.unique_bytes)
        return {**imported, "history": history, "accounting": accounting, "diagnostic": diagnostic,
            "prior_commitment_nanousd": REPAIR_COMMITMENT, "continuation": continuation,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "binding": desired,
                "owner": str(owner), "head": head, "plan_record": PLAN, "report_record": REPORT, "state_artifact": SUCCESSOR,
                "parent_import_artifact": plan["import_artifact"], "completed_producer": proof, "launch": launch,
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata), "size_manifest_artifact": manifest_ref,
                "size_preflight_record": preflight_record, "copied_artifacts": dict(reader.copied),
                "unique_source_artifact_bytes_read": reader.unique_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": liveness, "elapsed_seconds": round(time.monotonic()-started, 3)}}
