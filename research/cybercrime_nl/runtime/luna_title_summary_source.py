"""Finite import of a completed audit derivation, without replaying packet bodies.

The native audit already verified its physical wire and generated the immutable
pair coverage/observation artifacts. This observer verifies that completed
producer and those exact outputs, preserving every attempt and liability. It
does not claim a second wire replay or reopen any ancestor owner.
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

import luna_unresolved_audit as run
import luna_unresolved_audit_source as previous
from newsresearch.common import digest, require_active
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

base, retained, Reader = previous.base, previous.retained, previous.Reader
require = base.require
METHOD = "luna-title-summary-completed-audit-import-v1"
PREFLIGHT = "luna_title_summary_import_preflight"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-audit-20261025-v1")
PLAN = "e946f2cb78b483a4241d15fd3f1bd8a7cbde26b3ea01c6d393ceeb8c3bd88cf1"
REPORT = "39aad986a71a683b4badf9719d3eaeae6e96918eb5a71e0f2c4be75100f12ef9"
SUCCESSOR = "3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63"
REPAIR_COMMITMENT, VALIDATION_COMMITMENT = 9_998_784_420, 6_129_023_256
POLICY = {**previous.POLICY, "source_scope": "one_completed_unresolved_audit_owner",
    "maximum_index_bytes": 8*1024**2, "maximum_coverage_rows": 1_000_000,
    "maximum_attempts": 10_000, "completed_native_derivation_reused": True,
    "physical_packet_bodies_replayed": False, "response_bodies_replayed": False,
    "pair_attempt_blocking_ignores_new_role_names": True, "membership_changes": False,
    "validation_costs_are_repair_costs": False}


def binding():
    return {"plan_record": PLAN, "report_record": REPORT, "successor_artifact": SUCCESSOR}


def implementation():
    return {**run.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def preflight(reader, metadata, engine, session, progress):
    """Only the bounded coverage index may precede the full size preflight."""
    require(metadata["source_head"] == reader.head(), "title_preflight_head")
    rows = list(reader.db.execute("SELECT * FROM records ORDER BY created_event"))
    selected = {r["id"]: r for r in rows}
    require(PLAN in selected and REPORT in selected and selected[PLAN]["kind"] == run.PLAN
        and selected[REPORT]["kind"] == run.RESULT, "title_fixed_records")
    plan, report = (json.loads(selected[i]["payload"]) for i in (PLAN, REPORT))
    index_ref = report["pair_coverage_artifact"]
    index_size = reader.artifact_size(index_ref)
    require(index_size <= POLICY["maximum_index_bytes"], "title_index_limit")
    reader.allowed = {index_ref: index_size}
    index = reader.artifact(index_ref)
    require(isinstance(index, dict) and isinstance(index.get("rectangles"), list)
        and type(index.get("unique_pairs")) is int
        and 0 <= index["unique_pairs"] <= POLICY["maximum_coverage_rows"], "title_index_shape")
    refs = defaultdict(list)
    def add(ref, kind, identity, field):
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"kind": kind, "identity": identity, "field": field})
    for row in rows:
        add(row["artifact"], row["kind"], row["id"], "artifact")
    for field in ("import_artifact", "selection_artifact", "quote_artifact", "method_artifact", "diagnostic_artifact"):
        add(plan[field], run.PLAN, PLAN, field)
    for field in ("pair_coverage_artifact", "observations_artifact", "statistical_summary_artifact"):
        add(report[field], run.RESULT, REPORT, field)
    for entry in index["rectangles"]:
        require(set(entry) == {"descriptor_digest", "artifact", "pairs"}
            and type(entry["pairs"]) is int and entry["pairs"] >= 0, "title_index_entry")
        add(entry["artifact"], "native_coverage", entry["descriptor_digest"], "artifact")
    require(sum(e["pairs"] for e in index["rectangles"]) == index["unique_pairs"], "title_index_count")
    assessed = {json.loads(r["payload"])["attempt"] for r in rows if r["kind"] == run.RESPONSE}
    fields = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",)}
    for row in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        value = json.loads(row["payload"])
        for field in fields.get(row["kind"], ()):
            add(value[field], row["kind"], row["event_hash"], field)
        # A receipt without an assessment still carries a cost high-water mark.
        if row["kind"] == run.RECEIVED and value["attempt"] not in assessed:
            add(value["response"], row["kind"], row["event_hash"], "unassessed_response")
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "anchors": anchors}
        for ref, anchors in sorted(refs.items())]
    total = sum(e["bytes"] for e in entries)
    manifest = {"method": METHOD, "binding": binding(), "owner": str(reader.owner), "head": metadata["source_head"],
        "entries": entries, "total_distinct_bytes": total, "distinct_references": len(entries),
        "maximum_selected_bytes": POLICY["maximum_selected_bytes"], "fits": total <= POLICY["maximum_selected_bytes"],
        "packet_request_dispatch_bodies_selected": False, "completed_coverage_index": index_ref}
    ref = engine.ledger.artifacts.put(manifest)
    record = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "implementation": implementation(),
        "binding": binding(), "manifest_artifact": ref, "fits": manifest["fits"]})
    progress("title_import_size_preflight", selected_bytes=total, references=len(entries), fits=manifest["fits"])
    require(manifest["fits"], "title_selected_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
    return index, manifest, ref, record


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
        and all(digest(plan.get(k)) == digest(v) for k, v in base.plain(intent).items()), "title_plan_authority")
    require(seed["method"] == run.METHOD and seed["intent"] == intent["_record_id"] and seed["draw_performed"] is False
        and intent["_created_event"] < seed["_created_event"] < plan["_created_event"]
        and report["plan"] == PLAN and report["prepared"] is True and report["audit_finished"] is True
        and report["membership_changes"] == 0 and report["source_state_sha256"] == SUCCESSOR,
        "title_native_scope")
    require(reader.artifact_bytes(plan["method_artifact"]) == run.SPEC.read_bytes(), "title_method_bytes")
    expected = run.versions(base.plain(intent))
    require(set(plan["versions"]) == set(expected), "title_version_set")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, run.METHOD))]
        require(ids == [plan["versions"][kind]], "title_version_identity")
        row = reader.record(ids[0], kind)
        base.keyed(reader, row, run.METHOD)
        require(row["content"] == content and row["branch"] == "main" and row["reason"] is None
            and intent["_created_event"] < row["_created_event"] < seed["_created_event"], "title_version_binding")
    prefix, prep = base.session_prefix(reader, plan["_created_event"], code, {"action": "prepare"})
    done = [r for r in prefix if r["kind"] == "operation.completed"]
    ended = [r for r in prefix if r["kind"] == "session.ended"]
    require(len(done) == len(ended) == 1 and not any(r["kind"] == "operation.failed" for r in prefix)
        and seed["_created_event"] in {r["seq"] for r in prefix}
        and plan["_created_event"] < done[0]["seq"] < ended[0]["seq"]
        and json.loads(ended[0]["payload"]) == {"status": "completed"}, "title_prepare_completed")
    output = json.loads(done[0]["payload"])
    prepared = reader.artifact(output["result"])
    require(output["operation"] == "status" and prepared["method"] == run.METHOD and prepared["plan"] == PLAN
        and prepared["prepared"] is True and prepared["attempted_requests"] == 0, "title_prepare_output")
    completed = retained.completed(reader, report, code)
    require(reader.artifact(completed["input"]) in ({"action": "run", "allow_paid_execution": True}, {"action": "report"}),
        "title_report_operation")
    imported = reader.artifact(plan["import_artifact"])
    provenance = imported["provenance"]
    require(plan["source_binding"] == previous.binding() and provenance["binding"] == previous.binding()
        and provenance["method"] == previous.METHOD and provenance["implementation"] == previous.implementation()
        and Path(provenance["owner"]) == previous.OWNER and provenance["plan_record"] == previous.PLAN
        and provenance["report_record"] == previous.REPORT and provenance["state_artifact"] == SUCCESSOR
        and provenance["source_head_unchanged"] is True and digest(imported["state"]) == SUCCESSOR
        and imported["prior_commitment_nanousd"] == REPAIR_COMMITMENT == run.PRIOR_COMMITMENT, "title_parent_import")
    checkpoint = reader.record(provenance["size_preflight_record"], previous.PREFLIGHT)
    base.keyed(reader, checkpoint, provenance["size_manifest_artifact"])
    require(checkpoint["method"] == previous.METHOD and checkpoint["implementation"] == previous.implementation()
        and checkpoint["binding"] == previous.binding() and checkpoint["fits"] is True
        and checkpoint["manifest_artifact"] == provenance["size_manifest_artifact"]
        and checkpoint["_created_event"] in {r["seq"] for r in prefix}
        and seed["_created_event"] < checkpoint["_created_event"] < plan["_created_event"], "title_parent_checkpoint")
    require(reader.artifact(plan["diagnostic_artifact"]) == imported["diagnostic"], "title_diagnostic_binding")
    selection = reader.artifact(plan["selection_artifact"])
    run.design._verify(selection, "import_selection")
    selected = selection["selection"]
    run.design._verify(selected, "import_draw")
    documents = imported["source"]["documents"]
    require(selected["seed"] == seed["seed"] and selected["state_sha256"] == SUCCESSOR
        and selected["all_document_ids"] == sorted(documents)
        and selected["population_ids"] == sorted(imported["state"]["unresolved_ids"])
        and selected["source_bindings"] == {i: d["input_sha256"] for i, d in documents.items()}
        and len(set(selected["source_bindings"].values())) == len(documents)
        and selected["quarantine_document_ids"] == imported["history"]["quarantine_document_ids"], "title_selection_sources")
    require(selected["sample_ids"] == [selected["population_ids"][i] for i in selected["draw"]["rank_order"]]
        and len(selected["sample_ids"]) == selected["sample_size"] == len(set(selected["sample_ids"]))
        and set(selected["sample_ids"]) <= set(selected["population_ids"]), "title_sample_binding")
    quarantine = set(imported["history"]["quarantine_document_ids"])
    require(quarantine <= set(documents) and report["quarantined_inputs"] == len(quarantine)
        and report["historical_fatal_preserved"] == imported["diagnostic"]["fatal_cases"]
        == imported["history"]["historical_fatal_cases"]
        and quarantine == {i for case in imported["diagnostic"]["fatal_cases"] for i in case["members"]}, "title_quarantine")
    return plan, report, imported, selection, {"prepare": {**prep, "output": output["result"]}, "report": completed}


def physical_metadata(reader, plan, report):
    """Reuse native assessed outcomes; no repeated request/response parsing."""
    launch = base.one(reader, run.LAUNCH)
    base.keyed(reader, launch, PLAN)
    require(launch["method"] == run.METHOD and launch["plan"] == PLAN and launch["implementation"] == plan["implementation"]
        and launch["validation_cap_nanousd"] == run.VALIDATION_CAP
        and plan["_created_event"] < launch["_created_event"] < report["_created_event"], "title_launch_binding")
    prefix, launch_proof = base.session_prefix(reader, launch["_created_event"], plan["implementation"],
        {"action": "run", "allow_paid_execution": True})
    sequences = {r["seq"] for r in prefix}
    queues, assessments = {}, {}
    for row in reader.rows(run.QUEUE):
        base.keyed(reader, row, digest([PLAN, row["parent_descriptor_digest"], row["wave"]]))
        require(row["method"] == run.METHOD and row["plan"] == PLAN
            and launch["_created_event"] < row["_created_event"] < report["_created_event"]
            and row["_created_event"] in sequences, "title_queue_scope")
        queues[row["_record_id"]] = row
    for row in reader.rows(run.RESPONSE):
        base.keyed(reader, row, row["attempt"])
        require(row["attempt"] not in assessments and row["plan"] == PLAN
            and row["_created_event"] in sequences, "title_assessment_unique")
        assessments[row["attempt"]] = row
    events = {}
    for kind in ("model.attempt.intended", run.RECEIVED, "model.attempt.completed"):
        values = {}
        for row in reader.db.execute("SELECT * FROM events WHERE kind=? ORDER BY seq", (kind,)):
            value = json.loads(row["payload"])
            require(value["attempt"] not in values and row["seq"] in sequences
                and launch["_created_event"] < row["seq"] < report["_created_event"], "title_physical_event_scope")
            values[value["attempt"]] = {**value, "_seq": row["seq"], "_event_hash": row["event_hash"]}
        events[kind] = values
    intents, receipts, completions = (events[k] for k in ("model.attempt.intended", run.RECEIVED, "model.attempt.completed"))
    require(len(intents) <= POLICY["maximum_attempts"] and set(completions) <= set(assessments) <= set(receipts) <= set(intents),
        "title_physical_partition")
    facts, tasks, health_rows = {}, set(), {}
    counters = Counter(new_settled_nanousd=0, new_held_nanousd=0, unknown_holds=0, usable_requests=0)
    for attempt, row in intents.items():
        queue = queues.get(row["queue"])
        require(row["method"] == run.METHOD and row["batch"] == PLAN and row["category"] == "validation" and row["number"] == 1
            and row["task_key"] not in tasks and queue is not None and row["packet"] in queue["packet_artifacts"]
            and queue["_created_event"] < row["_seq"] and type(row["reserved_nanousd"]) is int and row["reserved_nanousd"] > 0,
            "title_intent_binding")
        tasks.add(row["task_key"])
        for field in ("packet", "request", "dispatch", "task_key"):
            retained.frozen.source_api._sha(row[field])
        receipt, assessment, completion = receipts.get(attempt), assessments.get(attempt), completions.get(attempt)
        cost, health = None, None
        if receipt:
            require(receipt["_seq"] > row["_seq"], "title_receipt_order")
        if assessment:
            require(assessment["task_key"] == row["task_key"] and assessment["response"] == receipt["response"]
                and receipt["_seq"] < assessment["_created_event"], "title_receipt_assessment")
            cost = assessment["cost_nanousd"]
            require(cost is None or type(cost) is int and cost >= 0, "title_cost_shape")
            require(type(assessment["hold"]) is bool and type(assessment["usable"]) is bool
                and (not assessment["usable"] or not assessment["hold"] and cost is not None and assessment["parsed"] is not None)
                and (assessment["hold"] or cost is not None and cost <= row["reserved_nanousd"]), "title_assessment_state")
            health = base.plain(assessment)
        elif receipt:
            # Only this exceptional envelope is read, to preserve known cost/fatal high-water.
            envelope = ProviderResponse(**reader.artifact(receipt["response"]))
            health, _ = run.outcome({"reservation_nanousd": row["reserved_nanousd"]}, envelope)
            cost = health["cost_nanousd"]
        if completion:
            require(not assessment["hold"] and completion["assessment"] == assessment["_record_id"]
                and completion["response"] == assessment["response"] and completion["_seq"] > assessment["_created_event"],
                "title_completion_binding")
            liability = cost
            counters["new_settled_nanousd"] += cost
            counters["usable_requests"] += bool(assessment["usable"])
        else:
            liability = max(row["reserved_nanousd"], cost or 0)
            counters["new_held_nanousd"] += liability
            counters["unknown_holds"] += 1
        if health:
            health_rows[attempt] = {**health, "usable": bool(completion and assessment and assessment["usable"])}
        facts[attempt] = {"owner": str(reader.owner), "head": reader.head(), "physical_attempt": attempt,
            "task_key": row["task_key"], "category": "validation", "role": "final_reference", "queue": row["queue"],
            "completed": bool(completion), "hold": not bool(completion), "usable": bool(completion and assessment["usable"]),
            "cost_nanousd": cost, "liability_nanousd": liability, "reserved_nanousd": row["reserved_nanousd"],
            "fatal": health.get("fatal") if health else None, "logical_ids": [], "pair_keys": [], "members": [],
            "intended_event": {"seq": row["_seq"], "event_hash": row["_event_hash"]},
            "artifact_refs": {**{k: row[k] for k in ("packet", "request", "dispatch")},
                "response": receipt["response"] if receipt else None,
                "response_record": assessment["_record_id"] if assessment else None,
                "parsed": assessment["parsed"] if assessment else None},
            "evidence_authority": "completed_native_audit_derivation", "wire_replayed_now": False}
    health = run.prior.health_state({r["task_key"]: r for r in intents.values()},
        {intents[a]["task_key"]: health_rows[a] for a in receipts if a in health_rows})
    counts = {**counters, "attempted_requests": len(intents), "returned_requests": len(receipts),
        "new_committed_nanousd": counters["new_settled_nanousd"]+counters["new_held_nanousd"], "health": health}
    require(all(digest(report[k]) == digest(v) for k, v in counts.items())
        and counts["new_committed_nanousd"] == VALIDATION_COMMITMENT
        and report["prior_repair_commitment_nanousd"] == REPAIR_COMMITMENT, "title_accounting_equality")
    return facts, queues, counts, launch_proof


def pair_history(reader, report, imported, selection, index, facts, queues, progress):
    descriptors = selection["descriptors"]
    require(index["selection_digest"] == selection["digest"] and index["unique_pairs"] == selection["expected_unique_pairs"]
        and [e["descriptor_digest"] for e in index["rectangles"]] == [d["digest"] for d in descriptors], "title_coverage_binding")
    selected = selection["selection"]
    universe = set(selected["all_document_ids"])
    observations = reader.artifact(report["observations_artifact"])
    require(isinstance(observations, dict), "title_observation_shape")
    history = deepcopy(imported["history"])
    old_physical = {r["physical_attempt"] for r in history.get("physical_attempts", [])}
    require(not old_physical.intersection(facts), "title_physical_retry")
    logical = set(history.get("logical_ids", [])) | set(history.get("prior_final_reference_logical_ids", []))
    tasks = set(history.get("task_keys", []))
    require(not tasks.intersection(r["task_key"] for r in facts.values()), "title_task_retry")
    attempted, observed, all_pairs = {}, set(), set()
    by_anchor = {i: {"positive": [], "negative": 0, "unknown": 0} for i in selected["sample_ids"]}
    exposed = set(history.get("development_exposed_documents", []))
    quarantine = set(history["quarantine_document_ids"])
    for n, (entry, descriptor) in enumerate(zip(index["rectangles"], descriptors, strict=True), 1):
        reader._active()
        run.design._verify(descriptor, "import_rectangle")
        rows = reader.artifact(entry["artifact"])
        expected = [sorted(p) for p in run.design.descriptor_pairs(descriptor)]
        require(len(rows) == entry["pairs"] == descriptor["pair_count"] and [r["pair"] for r in rows] == expected,
            "title_coverage_rectangle")
        for row in rows:
            pair, key, attempt = row["pair"], row["pair_key"], row["physical_attempt"]
            require(key == run.contract.pair_key(*pair) and key not in all_pairs
                and set(pair) <= universe, "title_pair_identity")
            all_pairs.add(key)
            observation = observations.get(key)
            if attempt is None:
                require(observation is None and not row["reason"].startswith("observed_")
                    and row["reason"] != "physical_outcome_unknown_or_unusable", "title_unattempted_observation")
                continue
            require(attempt in facts and key not in attempted and not quarantine.intersection(pair)
                and queues[facts[attempt]["queue"]]["parent_descriptor_digest"] == descriptor["digest"], "title_attempted_pair")
            identity = run.design._logical(selected["source_bindings"], pair)
            require(identity not in logical, "title_logical_retry")
            logical.add(identity)
            fact = facts[attempt]
            fact["logical_ids"].append(identity)
            fact["pair_keys"].append(key)
            fact["members"].extend(pair)
            attempted[key] = {"pair": pair, "pair_key": key, "logical_id": identity, "physical_attempt": attempt,
                "source_bindings": {i: selected["source_bindings"][i] for i in pair}, "role": "final_reference",
                "usable": fact["usable"], "hold": fact["hold"], "coverage_artifact": entry["artifact"],
                "evidence_authority": "completed_native_audit_derivation"}
            exposed.update(pair)
            if observation is None:
                require(not fact["usable"] and row["reason"] == "physical_outcome_unknown_or_unusable", "title_missing_observation")
                continue
            require(fact["usable"] and observation["pair_key"] == key and observation["pair"] == pair
                and observation["physical_attempt"] == attempt and observation["assessment"] == fact["artifact_refs"]["response_record"]
                and observation["response"] == fact["artifact_refs"]["response"] and observation["logical_id"] == identity
                and observation["role"] == "final_reference" and observation["full_source"] is True
                and observation["compatible_focal_rubric"] is True and observation["rubric_sha256"] == digest(run.design.SHARED_RULES)
                and observation["label"] in {"same_event", "negative", "unknown"}
                and row["reason"] == "observed_"+observation["label"], "title_observation_binding")
            observed.add(key)
            for anchor in set(pair) & set(by_anchor):
                if observation["label"] == "same_event":
                    by_anchor[anchor]["positive"].append(next(i for i in pair if i != anchor))
                else:
                    by_anchor[anchor][observation["label"]] += 1
        if n % 50 == 0 or n == len(descriptors):
            progress("title_import_pair_coverage", processed_rectangles=n, total_rectangles=len(descriptors),
                covered_pairs=len(all_pairs), attempted_pairs=len(attempted), observations=len(observed))
    require(len(all_pairs) == index["unique_pairs"] and observed == set(observations)
        and len(attempted) == report["attempted_unique_pairs"] and len(observed) == report["usable_pair_observations"]
        and all(f["pair_keys"] for f in facts.values()), "title_pair_partition")
    statistics = reader.artifact(report["statistical_summary_artifact"])
    require(statistics["selection_digest"] == selected["digest"] and statistics["summary"] == report["statistical_summary"]
        and statistics["articles"] == report["sample_outcomes"] and set(statistics["articles"]) == set(by_anchor), "title_statistics_binding")
    positives = {}
    for anchor, counts in by_anchor.items():
        saved = statistics["articles"][anchor]
        require(saved["positive_partners"] == sorted(counts["positive"]) and saved["negative_count"] == counts["negative"]
            and saved["observed_unknown_count"] == counts["unknown"], "title_witness_binding")
        if counts["positive"]:
            positives[anchor] = sorted(counts["positive"])
    for fact in facts.values():
        fact["members"] = sorted(set(fact["members"]))
    history.setdefault("physical_attempts", []).extend(facts.values())
    history.setdefault("pair_observations", []).extend(observations.values())
    # This role-independent blocker prevents a new development namespace from
    # repeating a previous final-reference pair, including failed/held outcomes.
    pair_attempts = history.setdefault("pair_attempts", {})
    require(isinstance(pair_attempts, dict), "title_prior_pair_mapping")
    for row in history["pair_observations"]:
        pair = row.get("pair", [])
        if len(pair) == 2 and set(pair) <= universe and pair[0] != pair[1]:
            key = run.contract.pair_key(*pair)
            pair_attempts.setdefault(key, {"pair": sorted(pair), "pair_key": key,
                "evidence_authority": "retained_prior_pair_observation", "role": row.get("role"),
                "physical_attempt": row.get("physical_attempt")})
    pair_attempts.update(attempted)
    history.update(logical_ids=sorted(logical),
        prior_final_reference_logical_ids=sorted(set(history.get("prior_final_reference_logical_ids", [])) |
            {row["logical_id"] for row in attempted.values()}),
        task_keys=sorted(tasks | {r["task_key"] for r in facts.values()}),
        development_exposed_documents=sorted(exposed), current_audit_attempts=list(facts.values()),
        current_audit_report=REPORT, global_history_complete=False)
    return history, positives, [r for r in observations.values() if r["label"] == "same_event"]


def collect(engine, session, *, binding=None, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "title_offline_only")
    desired = globals()["binding"]()
    require(binding is None or binding == desired, "title_fixed_binding")
    started = time.monotonic()
    deadline = started+POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline)
        and 0 < deadline-started <= POLICY["maximum_seconds"], "title_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-started, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("title_import_opening_completed_audit")
        liveness = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        index, manifest, manifest_ref, preflight_record = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, proof = authority(reader)
        facts, queues, counts, launch = physical_metadata(reader, plan, report)
        history, positives, positive_rows = pair_history(reader, report, imported, selection, index, facts, queues, progress)
        accounting = {"repair_commitment_nanousd": REPAIR_COMMITMENT, "validation_commitment_nanousd": VALIDATION_COMMITMENT,
            "repair": {"settled_nanousd": run.PRIOR_SETTLED, "held_nanousd": run.PRIOR_HELD,
                "committed_nanousd": REPAIR_COMMITMENT},
            "validation": {"settled_nanousd": counts["new_settled_nanousd"], "held_nanousd": counts["new_held_nanousd"],
                "committed_nanousd": VALIDATION_COMMITMENT, "unknown_holds": counts["unknown_holds"]},
            "combined_committed_nanousd": REPAIR_COMMITMENT+VALIDATION_COMMITMENT, "categories_mixed": False}
        require(accounting["repair"]["settled_nanousd"]+accounting["repair"]["held_nanousd"] == REPAIR_COMMITMENT,
            "title_prior_liabilities")
        fatal = [f for f in facts.values() if f["fatal"]]
        diagnostic = {"scope_admission_allowed": not fatal and counts["health"]["stop_reason"] is None,
            "fatal_cases": imported["diagnostic"]["fatal_cases"], "new_audit_fatal_cases": fatal,
            "historical_fatal_cleared": False, "quarantined_document_ids": history["quarantine_document_ids"],
            "physical_accounting": counts, "completed_native_derivation_reused": True, "wire_replayed_now": False,
            "counts": {"full_inputs": len(imported["source"]["documents"]), "unresolved_inputs": len(imported["state"]["unresolved_ids"]),
                "current_audit_attempts": len(facts), "attempted_pairs": report["attempted_unique_pairs"],
                "usable_pair_observations": report["usable_pair_observations"], "positive_sampled_anchors": len(positives),
                "positive_pairs": len(positive_rows), "quarantined_inputs": len(history["quarantine_document_ids"])}}
        reader._active()
        require(set(reader.copied) <= set(reader.allowed) and all(v == reader.allowed[k] for k, v in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "title_copy_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "title_source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        liveness.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "title_implementation_changed")
        progress("title_import_complete", **diagnostic["counts"], unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": imported["source"], "state": imported["state"], "history": history,
            "accounting": accounting, "diagnostic": diagnostic, "audit_positives": positives,
            "audit_positive_observations": positive_rows, "prior_commitment_nanousd": REPAIR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "binding": desired,
                "owner": str(owner), "head": head, "plan_record": PLAN, "report_record": REPORT, "state_artifact": SUCCESSOR,
                "parent_import_artifact": plan["import_artifact"], "completed_producer": proof, "launch": launch,
                "observations_artifact": report["observations_artifact"], "pair_coverage_artifact": report["pair_coverage_artifact"],
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata), "size_manifest_artifact": manifest_ref,
                "size_preflight_record": preflight_record, "copied_artifacts": dict(reader.copied),
                "unique_source_artifact_bytes_read": reader.unique_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": liveness, "elapsed_seconds": round(time.monotonic()-started, 3)}}
