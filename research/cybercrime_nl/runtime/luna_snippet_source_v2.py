"""Bounded physical-attempt import; bulk unattempted queue bodies stay unopened.

The completed native producer proves the queue/attempt relationship. This method
independently replays every physical intention and liability, but does not claim
to enumerate the packet lists underlying retained queued/unattempted counts.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path
import time

import luna_snippet_source as base
from newsresearch.common import digest, require_active
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

recall = base.recall
retained = base.retained
Reader = base.Reader
REPORT, PLAN, FREEZE, SUCCESSOR, OWNER = base.REPORT, base.PLAN, base.FREEZE, base.SUCCESSOR, base.OWNER
PRIOR_COMMITMENT = base.PRIOR_COMMITMENT
METHOD = "cybercrime-luna-snippet-retained-recall-v2"
POLICY = {**base.POLICY, "packet_scope": "all_durable_physical_intents_only",
    "bulk_queue_packet_artifacts_read": False, "prepared_only_packet_inventory_verified": False,
    "queued_counts_authority": "exact_completed_native_report"}
require = base.require


def implementation():
    return {**base.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def executed_census(reader, plan, report):
    """Exact durable attempt partition, without fetching any queue packet list."""
    queues = {}
    for row in reader.rows(recall.QUEUE):
        identity = row["_record_id"]
        base.keyed(reader, row, row["name"])
        require(row["plan"] == plan["_record_id"] and digest(row["implementation"]) == digest(plan["implementation"])
            and plan["_created_event"] < row["_created_event"] < report["_created_event"], "queue_binding")
        base.session_prefix(reader, row["_created_event"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
        require(identity not in queues, "duplicate_queue")
        queues[identity] = row
    state = {"intents": {}, "responses": {}, "packets": {}, "queues": {}, "observations": [],
        "settled_nanousd": 0, "held_nanousd": 0, "by_category": defaultdict(int),
        "logical_attempted": set(), "returned_requests": 0, "unknown_holds": 0, "completed": set()}
    byattempt, events, perqueue = {}, {}, defaultdict(list)
    for event in reader.db.execute("SELECT seq,event_hash,payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
        value = json.loads(event["payload"])
        key, attempt = value.get("task_key"), value.get("attempt")
        require(isinstance(key, str) and isinstance(attempt, str) and key not in state["intents"]
            and attempt not in byattempt and value.get("queue") in queues, "attempt_scope_or_retry")
        queue = queues[value["queue"]]
        require(queue["_created_event"] < event["seq"] < report["_created_event"], "attempt_chronology")
        base.session_prefix(reader, event["seq"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
        packet = reader.artifact(value["packet"])
        require(value["method"] == recall.METHOD and value["batch"] == plan["_record_id"]
            and type(value["number"]) is int and value["number"] == 1
            and packet["task_key"] == key and value["packet"] == digest(packet)
            and value["request"] == packet["request_sha256"] == digest(packet["request"])
            and packet["reservation_nanousd"] == recall.contract.reservation(packet)
            and type(value["reserved_nanousd"]) is int and value["reserved_nanousd"] == packet["reservation_nanousd"]
            and value["category"] == queue["category"], "intent_binding")
        require(digest(reader.artifact(value["request"])) == digest(packet["request"])
            and digest(reader.artifact(value["dispatch"])) == digest(recall.transport.Invocation(
                packet["request"], attempt, kind=packet["kind"]).manifest()), "dispatch_binding")
        require(len(set(packet["logical_ids"])) == len(packet["logical_ids"])
            and not state["logical_attempted"].intersection(packet["logical_ids"]), "logical_retry")
        state["logical_attempted"].update(packet["logical_ids"])
        state["intents"][key], state["packets"][key] = value, packet
        state["queues"][key] = {"id": queue["_record_id"], **base.plain(queue)}
        byattempt[attempt] = key
        events[attempt] = {"sequence": event["seq"], "event_hash": event["event_hash"]}
        perqueue[queue["_record_id"]].append(attempt)
    receipts = {}
    for event in reader.db.execute("SELECT seq,event_hash,payload FROM events WHERE kind='luna_recall.response.received' ORDER BY seq"):
        receipt = json.loads(event["payload"])
        attempt = receipt["attempt"]
        require(attempt in byattempt and attempt not in receipts
            and events[attempt]["sequence"] < event["seq"] < report["_created_event"], "receipt_identity")
        response = ProviderResponse(**reader.artifact(receipt["response"]))
        derived, parsed = recall.outcome(state["packets"][byattempt[attempt]], response)
        receipts[attempt] = {"response": receipt["response"], "derived": derived, "parsed": parsed,
            "sequence": event["seq"], "event_hash": event["event_hash"]}
    response_events = {}
    for row in reader.rows(recall.RESPONSE):
        key, attempt = row["task_key"], row["attempt"]
        require(key in state["intents"] and key not in state["responses"] and attempt in receipts
            and byattempt[attempt] == key and row["plan"] == plan["_record_id"], "response_identity")
        base.keyed(reader, row, attempt)
        receipt = receipts[attempt]
        require(receipt["sequence"] < row["_created_event"] < report["_created_event"]
            and row["response"] == receipt["response"]
            and row["parsed"] == (digest(receipt["parsed"]) if receipt["parsed"] else None)
            and all(digest(row.get(k)) == digest(v) for k, v in receipt["derived"].items()), "response_replay")
        if row["parsed"]:
            reader.artifact_bytes(row["parsed"])
        state["responses"][key] = {"id": row["_record_id"], **base.plain(row)}
        response_events[attempt] = row["_created_event"]
    completions = {}
    for event in reader.db.execute("SELECT seq,event_hash,payload FROM events WHERE kind='model.attempt.completed' ORDER BY seq"):
        value = json.loads(event["payload"])
        attempt = value["attempt"]
        require(attempt in byattempt and attempt not in state["completed"], "completion_scope")
        row = state["responses"].get(byattempt[attempt])
        require(row and not row["hold"] and value["assessment"] == row["id"] and value["response"] == row["response"]
            and response_events[attempt] < event["seq"] < report["_created_event"], "completion_binding")
        state["completed"].add(attempt)
        completions[attempt] = {"sequence": event["seq"], "event_hash": event["event_hash"]}
    health_rows = dict(state["responses"])
    for key, intended in state["intents"].items():
        receipt = receipts.get(intended["attempt"])
        cost = receipt["derived"]["cost_nanousd"] if receipt else None
        if intended["attempt"] in state["completed"]:
            require(type(cost) is int and cost >= 0, "settled_cost")
            state["settled_nanousd"] += cost
            liability = cost
            if state["responses"][key]["usable"]:
                state["observations"].extend(state["responses"][key]["observations"])
        else:
            liability = max(intended["reserved_nanousd"], cost or 0)
            state["held_nanousd"] += liability
            state["unknown_holds"] += 1
        state["by_category"][intended["category"]] += liability
        if receipt and key not in health_rows:
            health_rows[key] = {**receipt["derived"], "usable": False}
    state["returned_requests"] = len(receipts)
    state["health"] = recall.prior.health_state(state["intents"], health_rows)
    expected = {"attempted_requests": len(state["intents"]), "returned_requests": len(receipts),
        **{k: state[k] for k in ("settled_nanousd", "held_nanousd", "unknown_holds")},
        "category_commitments_nanousd": dict(state["by_category"]), "response_health": state["health"],
        "prior_audit_commitment_nanousd": recall.PRIOR_COMMITMENT,
        "committed_including_prior_nanousd": recall.PRIOR_COMMITMENT+state["settled_nanousd"]+state["held_nanousd"]}
    require(all(digest(report[k]) == digest(v) for k, v in expected.items())
        and report["committed_including_prior_nanousd"] == PRIOR_COMMITMENT, "report_cost_census")
    require(type(report["queued_requests"]) is int and type(report["unattempted_requests"]) is int
        and report["unattempted_requests"] >= 0
        and report["queued_requests"] == len(state["intents"])+report["unattempted_requests"], "reported_queue_counts")
    metadata = [{"record": row["_record_id"], "artifact": row["_artifact"],
        "packets_artifact": row["packets_artifact"], "packet_list_read": False, "name": row["name"],
        "category": row["category"], "planned_reservation_nanousd": row["planned_reservation_nanousd"],
        "unavailable": row["unavailable"], "physical_attempts": perqueue[row["_record_id"]]}
        for row in queues.values()]
    evidence = {"intended_events": events, "receipt_events": {a: {k: r[k] for k in ("sequence", "event_hash", "response")} for a, r in receipts.items()},
        "completion_events": completions, "orphan_attempts": sorted(set(byattempt)-state["completed"]),
        "complete_physical_intent_partition": True, "queue_packet_membership_basis": "exact_native_producer_code_and_durable_intent",
        "bulk_queue_membership_independently_replayed": False}
    return state, metadata, evidence


def collect(engine, session, *, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "offline_only")
    start = time.monotonic()
    deadline = start + POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (float, int)) and math.isfinite(deadline)
        and 0 < deadline-start <= POLICY["maximum_seconds"], "bounded_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    observations = []
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-start, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("snippet_v2_opening_retained_recall")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        plan, report, source, state, proof = base.authority(reader)
        progress("snippet_v2_replaying_physical_attempts", metadata_events=len(metadata["events"]))
        census, queues, evidence = executed_census(reader, plan, report)
        history = base.membership_history(reader, source, census, head)
        history.update(queue_metadata=queues, physical_census=evidence,
            prepared_only_summary={"enumerated": False, "individual_memberships": "unknown",
                "reported_queued_requests": report["queued_requests"],
                "reported_unattempted_requests": report["unattempted_requests"],
                "authority": "completed_native_report", "report_record": REPORT})
        require(history["prepared_only"] == [], "physical_only_partition")
        reader._active()
        check_permissions(owner, root=True)
        check_permissions(owner / "objects")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "source_changed")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "implementation_changed")
        progress("snippet_v2_source_complete", physical_attempts=len(census["intents"]),
            unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history,
            "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY,
                "owner": str(owner), "head": head, "plan_record": PLAN, "plan_artifact": plan["_artifact"],
                "report_record": REPORT, "report_artifact": report["_artifact"], "state_artifact": SUCCESSOR,
                "source_artifact": plan["source_artifact"], **proof,
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata),
                "copied_artifacts": dict(reader.copied), "unique_source_artifact_bytes_read": reader.unique_bytes,
                "liveness": observations, "historical_stop": stop, "source_head_unchanged": True,
                "elapsed_seconds": round(time.monotonic()-start, 3)}}
