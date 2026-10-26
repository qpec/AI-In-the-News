"""One-owner import of the stopped unresolved-resolution successor.

Only completed native metadata and executed request evidence are read. The old
and new fatal outcomes remain liabilities; isolation does not clear either stop.
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

import luna_unresolved_run as run
import luna_unresolved_source as previous
from newsresearch.common import digest, require_active
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

base, retained, Reader = previous.base, previous.retained, previous.Reader
require = base.require
METHOD = "luna-unresolved-audit-retained-source-v1"
PREFLIGHT = "luna_unresolved_audit_import_preflight"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-unresolved-20261025-v1")
PLAN = "0f04c3d9a4ded2185da945daa0c59e1ab47f419fa4d8c035ab8b1065cbe41711"
REPORT = "7e50ea6319d11e8d7dc17768dfa9870f1da0c1f41f08f55cda069af8f169281f"
SUCCESSOR = "3bbb16460eae5af3b3d64488500d9226343f4c653f1eb2a28b532717befb2b63"
PRIOR_COMMITMENT = 9_998_784_420
POLICY = {**previous.POLICY, "source_scope": "completed_unresolved_resolution_owner_only",
    "no_new_pair_labels_from_membership_qa": True, "all_source_inputs_preserved": True,
    "random_sample_filters_quarantine": False, "old_and_new_quarantine_union": True}


def binding():
    return {"plan_record": PLAN, "report_record": REPORT, "successor_artifact": SUCCESSOR}


def implementation():
    return {**run.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class View(previous.View):
    completed_prepare = run.Resolution.completed_prepare
    set_scope = run.Resolution.set_scope


def preflight(reader, metadata, engine, session, progress):
    reader._active()
    require(metadata["source_head"] == reader.head(), "audit_import_preflight_head")
    refs, found = defaultdict(list), set()
    def add(ref, kind, identity, field):
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"kind": kind, "identity": identity, "field": field})
    for row in reader.db.execute("SELECT * FROM records ORDER BY created_event"):
        value = json.loads(row["payload"])
        add(row["artifact"], row["kind"], row["id"], "artifact")
        if row["id"] == PLAN:
            require(row["kind"] == run.PLAN, "audit_import_plan_kind")
            found.add(PLAN)
            for field in ("import_artifact", "selection_artifact", "quote_artifact", "method_artifact", "diagnostic_artifact"):
                add(value[field], row["kind"], row["id"], field)
        if row["id"] == REPORT:
            require(row["kind"] == run.RESULT and value["successor_artifact"] == SUCCESSOR, "audit_import_report_binding")
            found.add(REPORT)
            for field in ("successor_artifact", "change_manifest_artifact", "dispositions_artifact"):
                add(value[field], row["kind"], row["id"], field)
        if row["kind"] == run.RESPONSE:
            add(value["response"], row["kind"], row["id"], "response")
            if value["parsed"] is not None:
                add(value["parsed"], row["kind"], row["id"], "parsed")
    require(found == {PLAN, REPORT}, "audit_import_fixed_records")
    fields = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",),
        "model.attempt.intended": ("packet", "request", "dispatch"), "luna_unresolved.response.received": ("response",)}
    for row in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        if row["kind"] in fields:
            value = json.loads(row["payload"])
            for field in fields[row["kind"]]:
                add(value[field], row["kind"], row["event_hash"], field)
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "anchors": anchors}
        for ref, anchors in sorted(refs.items())]
    total = sum(e["bytes"] for e in entries)
    manifest = {"method": METHOD, "binding": binding(), "owner": str(reader.owner), "head": metadata["source_head"],
        "entries": entries, "distinct_references": len(entries), "total_distinct_bytes": total,
        "maximum_selected_bytes": POLICY["maximum_selected_bytes"], "fits": total <= POLICY["maximum_selected_bytes"],
        "bulk_queue_bodies_selected": False, "ancestors_opened": False}
    ref = engine.ledger.artifacts.put(manifest)
    record = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "implementation": implementation(),
        "manifest_artifact": ref, "binding": binding(), "fits": manifest["fits"]})
    progress("audit_import_size_preflight", selected_bytes=total, references=len(entries), fits=manifest["fits"])
    require(manifest["fits"], "audit_import_preflight_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
    return manifest, ref, record


def authority(reader):
    plan, intent = base.one(reader, run.PLAN, PLAN), base.one(reader, run.INTENT)
    report = base.one(reader, run.RESULT, REPORT)
    reader.ensure_report_last(report)
    for row, key in ((plan, run.METHOD), (intent, run.METHOD), (report, PLAN)):
        base.keyed(reader, row, key)
    require(report["method"] == run.METHOD and report["plan"] == PLAN and report["resolution_finished"] is True
        and report["successor_artifact"] == SUCCESSOR and report["new_reference_judgments"] == 0,
        "audit_import_result_binding")
    public, imported, selection = run.Resolution.load_plan(View(reader))
    require(public["id"] == PLAN and imported["prior_commitment_nanousd"] == run.PRIOR_COMMITMENT,
        "audit_import_plan_identity")
    expected = run.versions(base.plain(intent))
    require(set(plan["versions"]) == set(expected), "audit_import_version_set")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, run.METHOD))]
        require(ids == [plan["versions"][kind]], "audit_import_version_identity")
        row = reader.record(ids[0], kind)
        base.keyed(reader, row, run.METHOD)
        require(row["content"] == content and row["branch"] == "main" and row["reason"] is None
            and intent["_created_event"] < row["_created_event"] < plan["_created_event"], "audit_import_version_binding")
    proof = retained.completed(reader, report, plan["implementation"])
    require(reader.artifact(proof["input"]) == {"action": "run", "allow_paid_execution": True}, "audit_import_completed_run")
    provenance = imported["provenance"]
    require(provenance["method"] == previous.METHOD and provenance["implementation"] == previous.implementation()
        and provenance["binding"] == previous.binding() and provenance["plan_record"] == previous.PLAN
        and provenance["report_record"] == previous.REPORT and provenance["freeze_record"] == previous.FREEZE
        and provenance["state_artifact"] == digest(imported["state"]) == previous.SUCCESSOR
        and provenance["source_head_unchanged"] is True, "audit_import_parent_authority")
    checkpoint = reader.record(provenance["size_preflight_record"], previous.PREFLIGHT)
    require(checkpoint["method"] == previous.METHOD and checkpoint["implementation"] == previous.implementation()
        and checkpoint["binding"] == previous.binding() and checkpoint["fits"] is True
        and checkpoint["manifest_artifact"] == provenance["size_manifest_artifact"]
        and intent["_created_event"] < checkpoint["_created_event"] < plan["_created_event"], "audit_import_parent_checkpoint")
    base.keyed(reader, checkpoint, checkpoint["manifest_artifact"])
    prefix, _ = base.session_prefix(reader, plan["_created_event"], plan["implementation"], {"action": "prepare"})
    require(checkpoint["_created_event"] in {r["seq"] for r in prefix}, "audit_import_parent_session")
    diagnostic, history = imported["diagnostic"], imported["history"]
    old_quarantine = set(history["quarantine_document_ids"])
    require(diagnostic["scope_admission_allowed"] is True and bool(diagnostic["fatal_cases"])
        and diagnostic["fatal_cases"] == history["historical_fatal_cases"] == report["historical_failure_preserved"]
        and old_quarantine == set(diagnostic["quarantined_document_ids"])
        and old_quarantine == {i for case in diagnostic["fatal_cases"] for i in case["members"]}
        and all(case["is_bound_content_guard"] for case in diagnostic["fatal_cases"])
        and report["quarantined_inputs"] == len(old_quarantine), "audit_import_prior_quarantine")
    state, changes = reader.artifact(SUCCESSOR), reader.artifact(report["change_manifest_artifact"])
    require(digest(run.repair.commit(imported["state"], changes, reason=run.METHOD)) == SUCCESSOR
        and previous.previous.statistics_equal(run.predecessor.statistics(imported["state"]), report["before"])
        and previous.previous.statistics_equal(run.predecessor.statistics(state), report["after"])
        and report["changes"] == len(changes), "audit_import_successor_replay")
    dispositions = reader.artifact(report["dispositions_artifact"])
    require(dispositions["summary"] == report["disposition_summary"]
        and set(dispositions["articles"]) == set(selection["anchors"])
        and set(state["unresolved_ids"]) <= set(dispositions["articles"]), "audit_import_disposition_scope")
    run.resolution._units(imported["source"], state)
    return plan, report, imported, selection, state, dispositions, proof


def physical_census(reader, plan, report, source, imported_history, progress):
    """Read each physical packet once; retain only compact evidence after replay."""
    queues, assessments, receipts, completions = {}, {}, {}, {}
    for row in reader.rows(run.QUEUE):
        base.keyed(reader, row, row["name"])
        require(row["plan"] == PLAN and row["implementation"] == plan["implementation"]
            and row["category"] in {"join", "singleton"}
            and plan["_created_event"] < row["_created_event"] < report["_created_event"], "unresolved_queue_binding")
        queues[row["_record_id"]] = row
    for row in reader.rows(run.RESPONSE):
        require(row["attempt"] not in assessments, "unresolved_duplicate_assessment")
        base.keyed(reader, row, row["attempt"])
        assessments[row["attempt"]] = row
    for kind, target in (("luna_unresolved.response.received", receipts), ("model.attempt.completed", completions)):
        for raw in reader.db.execute("SELECT * FROM events WHERE kind=? ORDER BY seq", (kind,)):
            value = json.loads(raw["payload"])
            require(value["attempt"] not in target, "unresolved_duplicate_event")
            target[value["attempt"]] = {**value, "sequence": raw["seq"], "event_hash": raw["event_hash"]}
    history = deepcopy(imported_history)
    history.setdefault("physical_attempts", [])
    history.setdefault("proposal_questions", {})
    history.setdefault("proposal_packets", [])
    memberships = history.setdefault("membership_attempts", {})
    logical, tasks = set(history.get("logical_ids", [])), set(history.get("task_keys", []))
    old_attempts = {r["physical_attempt"] for r in history["physical_attempts"]}
    exposed = set(history.get("development_exposed_documents", []))
    final_ids = set(history.get("prior_final_reference_logical_ids", []))
    facts, intents, health_rows, fatal, clarities = [], {}, {}, [], []
    old_quarantine = set(history["quarantine_document_ids"])
    quarantine, seen_attempts = set(old_quarantine), set()
    counters = {"new_settled_nanousd": 0, "new_held_nanousd": 0, "unknown_holds": 0}
    by_category = {"join": 0, "singleton": 0}
    encoder = offline_tokenizer()
    def count(text):
        return len(encoder.encode(text, disallowed_special=()))
    verified_sessions = set()
    for raw in reader.db.execute("SELECT * FROM events WHERE kind='model.attempt.intended' ORDER BY seq"):
        value = json.loads(raw["payload"])
        key, attempt = value["task_key"], value["attempt"]
        require(key not in tasks and attempt not in seen_attempts | old_attempts and value["queue"] in queues, "unresolved_attempt_retry")
        queue = queues[value["queue"]]
        require(queue["_created_event"] < raw["seq"] < report["_created_event"], "unresolved_intent_chronology")
        if raw["session_id"] not in verified_sessions:
            session_rows, _ = base.session_prefix(reader, raw["seq"], plan["implementation"], {"action": "run", "allow_paid_execution": True})
            require(all(e["seq"] < report["_created_event"] for e in session_rows if e["kind"] == "model.attempt.intended"), "unresolved_later_attempt")
            verified_sessions.add(raw["session_id"])
        packet = reader.artifact(value["packet"])
        require(value["method"] == run.METHOD and value["batch"] == PLAN and value["number"] == 1
            and value["category"] == queue["category"] and packet["task_key"] == key
            and value["packet"] == digest(packet) and value["request"] == packet["request_sha256"] == digest(packet["request"])
            and value["reserved_nanousd"] == packet["reservation_nanousd"] == run.contract.reservation(packet), "unresolved_intent_binding")
        require(reader.artifact(value["request"]) == packet["request"]
            and reader.artifact(value["dispatch"]) == run.wire.Invocation(packet["request"], attempt, kind=packet["kind"]).manifest(), "unresolved_wire_binding")
        require(len(packet["logical_ids"]) == len(set(packet["logical_ids"]))
            and not logical.intersection(packet["logical_ids"]), "unresolved_logical_retry")
        require(packet["role"] in {"group_membership", "group_quality"}, "audit_import_qa_role")
        members = previous.packet_members(packet, source)
        require(not old_quarantine.intersection(members), "audit_import_prior_quarantine_exposure")
        tasks.add(key)
        logical.update(packet["logical_ids"])
        seen_attempts.add(attempt)
        intents[key] = value
        receipt, assessment, completion = receipts.get(attempt), assessments.get(attempt), completions.get(attempt)
        parsed, derived, envelope = None, None, None
        if receipt:
            require(raw["seq"] < receipt["sequence"] < report["_created_event"], "unresolved_receipt_chronology")
            envelope = reader.artifact(receipt["response"])
            derived, parsed = run.outcome(packet, ProviderResponse(**envelope))
        if assessment:
            require(receipt and assessment["plan"] == PLAN and assessment["task_key"] == key
                and receipt["sequence"] < assessment["_created_event"] < report["_created_event"]
                and assessment["response"] == receipt["response"]
                and assessment["parsed"] == (digest(parsed) if parsed is not None else None)
                and all(digest(assessment.get(k)) == digest(v) for k, v in derived.items()), "unresolved_assessment_replay")
            if assessment["parsed"] is not None:
                require(reader.artifact(assessment["parsed"]) == parsed, "unresolved_parsed_binding")
        if completion:
            require(assessment and not derived["hold"] and completion["assessment"] == assessment["_record_id"]
                and completion["response"] == assessment["response"]
                and assessment["_created_event"] < completion["sequence"] < report["_created_event"], "unresolved_completion_binding")
        cost = derived["cost_nanousd"] if derived else None
        if completion:
            require(type(cost) is int and cost >= 0, "unresolved_settled_cost")
            liability = cost
            counters["new_settled_nanousd"] += cost
        else:
            liability = max(value["reserved_nanousd"], cost or 0)
            counters["new_held_nanousd"] += liability
            counters["unknown_holds"] += 1
        by_category[value["category"]] += liability
        if derived:
            health_rows[key] = {**derived, "usable": bool(assessment and derived["usable"])}
        good = bool(completion and assessment and derived["usable"])
        fact = {"owner": str(reader.owner), "head": reader.head(), "physical_attempt": attempt,
            "task_key": key, "logical_ids": packet["logical_ids"], "role": packet["role"], "members": members,
            "membership_revision": packet.get("membership_revision"), "completed": bool(completion), "hold": not bool(completion),
            "usable": good, "liability_nanousd": liability, "reserved_nanousd": value["reserved_nanousd"],
            "cost_nanousd": cost, "fatal": derived["fatal"] if derived else None,
            "artifact_refs": {k: value[k] for k in ("packet", "request", "dispatch")},
            "intended_event": {"seq": raw["seq"], "event_hash": raw["event_hash"]}, "queue": value["queue"]}
        if receipt:
            fact["artifact_refs"]["response"] = receipt["response"]
            fact["receipt_event"] = {k: receipt[k] for k in ("sequence", "event_hash")}
        if assessment:
            fact["artifact_refs"].update(response_record=assessment["_record_id"], parsed=assessment["parsed"])
        if completion:
            fact["completion_event"] = {k: completion[k] for k in ("sequence", "event_hash")}
        facts.append(fact)
        history["physical_attempts"].append(fact)
        if derived and derived["fatal"]:
            quarantine.update(members)
            raw_response = envelope.get("raw_response") or {}
            fatal.append({**fact, "failure_stage": derived["failure_stage"], "failure_code": derived["failure_code"],
                "http_status": derived["http_status"], "dispatch_started": derived["dispatch_started"],
                "unknown_outcome": raw_response.get("unknown_outcome"), "provider": envelope.get("provider"),
                "model": envelope.get("model"), "payload_present": envelope.get("payload") is not None,
                "observability_version": raw_response.get("observability_version"),
                "is_bound_content_guard": derived["fatal"] == "response_content_rejected"
                    and derived["failure_code"] == "response_content_rejected"
                    and derived["failure_stage"] == "response_credentials"
                    and raw_response.get("unknown_outcome") is True and derived["dispatch_started"] is True
                    and envelope.get("payload") is None and envelope.get("model") is None,
                "rejected_content_retained": False, "triggering_content_inferred": False,
                "quarantined_document_ids": members})
        exposed.update(members)
        stage = "member" if packet["role"] == "group_membership" else "card"
        revision = packet["membership_revision"]
        item = memberships.setdefault(revision, {"members": members, "member_attempted": False, "card_attempted": False,
            "member_supported": False, "card_supported": False, "blocked": False,
            "member_result_ref": None, "card_result_ref": None, "card": None, "provenance": []})
        require(item["members"] == members and not item[stage+"_attempted"], "unresolved_membership_retry")
        supported = bool(good and derived["members_supported" if stage == "member" else "group_supported"])
        if supported:
            builder = run.contract.member_packet if stage == "member" else run.contract.group_packet
            require(digest(builder(source, members, count)) == digest(packet), "unresolved_positive_full_source")
        item.update({stage+"_attempted": True, stage+"_supported": supported,
            stage+"_result_ref": assessment["_record_id"] if assessment else None})
        item["blocked"] |= not supported
        if stage == "card" and supported:
            item["card"] = packet["card"]
        item["provenance"].append({**fact, "stage": stage, "supported": supported})
        if stage == "member" and good:
            for answer in parsed["answers"].values():
                if answer["kind"] == "clarity":
                    alias = answer["document_id"]
                    index = int(alias[1:])-1 if alias.startswith("A") and alias[1:].isdigit() else -1
                    require(0 <= index < len(members), "unresolved_clarity_alias")
                    clarities.append({**answer, "document_id": members[index], "alias": alias,
                        "membership_revision": revision, "physical_attempt": attempt,
                        "response_record": assessment["_record_id"], "context_members": members})
        if len(facts) % 100 == 0:
            progress("unresolved_replaying_attempts", physical_attempts=len(facts), unique_source_artifact_bytes_read=reader.unique_bytes)
    require(set(assessments) <= set(receipts) <= seen_attempts and set(completions) <= set(assessments), "unresolved_orphan_metadata")
    # Match native response insertion order before adding receipt-only outcomes.
    assessed_keys = {r["task_key"] for r in assessments.values()}
    health_rows = {r["task_key"]: health_rows[r["task_key"]] for r in assessments.values()} | {
        k: v for k, v in health_rows.items() if k not in assessed_keys}
    health = run.prior.health_state(intents, health_rows)
    expected = {**counters, "attempted_requests": len(facts), "returned_requests": len(receipts),
        "usable_requests": sum(r["usable"] for r in assessments.values()),
        "new_committed_nanousd": counters["new_settled_nanousd"]+counters["new_held_nanousd"],
        "category_commitments_nanousd": by_category, "health": health}
    expected["combined_commitment_nanousd"] = run.PRIOR_COMMITMENT+expected["new_committed_nanousd"]
    require(all(digest(report[k]) == digest(v) for k, v in expected.items())
        and expected["combined_commitment_nanousd"] == PRIOR_COMMITMENT, "unresolved_cost_census")
    require(run.PRIOR_SETTLED + run.PRIOR_HELD == run.PRIOR_COMMITMENT, "audit_import_prior_liabilities")
    expected.update(combined_settled_nanousd=run.PRIOR_SETTLED+counters["new_settled_nanousd"],
        combined_held_nanousd=run.PRIOR_HELD+counters["new_held_nanousd"])
    require(expected["combined_settled_nanousd"]+expected["combined_held_nanousd"] == PRIOR_COMMITMENT,
        "audit_import_combined_liabilities")
    require(type(report["queued_requests"]) is int and type(report["unattempted_requests"]) is int
        and report["unattempted_requests"] >= 0 and report["queued_requests"] == len(facts)+report["unattempted_requests"], "unresolved_prepared_counts")
    history.update(logical_ids=sorted(logical), task_keys=sorted(tasks), prior_final_reference_logical_ids=sorted(final_ids),
        development_exposed_documents=sorted(exposed), quarantine_document_ids=sorted(quarantine),
        historical_fatal_cases=[*imported_history["historical_fatal_cases"], *fatal],
        current_resolution_response_health=health, current_resolution_liabilities=expected,
        current_resolution_clarity_observations=clarities,
        global_history_complete=False, current_resolution_prepared_only_summary={"enumerated": False, "reported_queued_requests": report["queued_requests"],
            "reported_unattempted_requests": report["unattempted_requests"], "report_record": REPORT})
    return history, {"facts": facts, "fatal_cases": fatal, "clarity": clarities,
        "queues": queues, "counts": expected}


def diagnostic(report, imported, state, dispositions, history, census):
    old = imported["diagnostic"]["fatal_cases"]
    new = census["fatal_cases"]
    quarantine = set(history["quarantine_document_ids"])
    population = sorted(state["unresolved_ids"])
    by_doc, clarity = defaultdict(list), defaultdict(list)
    for fact in census["facts"]:
        for i in fact["members"]:
            by_doc[i].append(fact["physical_attempt"])
    for observation in census["clarity"]:
        clarity[observation["document_id"]].append(observation)
    require(quarantine <= set(imported["source"]["documents"])
        and len(population) == report["after"]["unresolved_inputs"], "audit_import_diagnostic_population")
    allowed = bool(new) and all(case["is_bound_content_guard"] for case in new) \
        and report["health"]["stop_reason"] == "response_content_rejected"
    return {"scope_admission_allowed": allowed, "fatal_cases": [*old, *new],
        "prior_fatal_cases": old, "new_fatal_cases": new, "historical_fatal_cleared": False,
        "discarded_content_recoverable": False, "quarantined_document_ids": sorted(quarantine),
        "new_quarantined_document_ids": sorted({i for case in new for i in case["members"]}),
        "quarantined_unresolved_ids": sorted(quarantine & set(population)),
        "unresolved_population": population,
        "unresolved_rows": [{"document_id": i, "quarantined": i in quarantine,
            "native_disposition": dispositions["articles"][i], "current_physical_attempts": by_doc[i],
            "current_clarity_observations": clarity[i]} for i in population],
        "native_dispositions_artifact": report["dispositions_artifact"],
        "native_disposition_summary": dispositions["summary"], "physical_accounting": census["counts"],
        "counts": {"full_inputs": len(imported["source"]["documents"]), "unresolved_inputs": len(population),
            "current_physical_attempts": len(census["facts"]), "old_fatal_packets": len(old), "new_fatal_packets": len(new),
            "quarantined_inputs": len(quarantine), "quarantined_unresolved_inputs": len(quarantine & set(population))},
        "sampling_filters_applied": False, "membership_qa_interpreted_as_pair_labels": False,
        "singleton_uniqueness_proved": False, "semantic_cause_inferred": False}


def collect(engine, session, *, binding=None, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "audit_import_offline_only")
    desired = globals()["binding"]()
    require(binding is None or binding == desired, "audit_import_fixed_binding")
    started = time.monotonic()
    deadline = started+POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline)
        and 0 < deadline-started <= POLICY["maximum_seconds"], "audit_import_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-started, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("audit_import_opening_completed_resolution")
        observations = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest, manifest_ref, preflight_record = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, state, dispositions, proof = authority(reader)
        history, census = physical_census(reader, plan, report, imported["source"], imported["history"], progress)
        result = diagnostic(report, imported, state, dispositions, history, census)
        source = imported["source"]
        del imported, selection, census, dispositions
        reader._active()
        require(set(reader.copied) <= set(reader.allowed) and all(v == reader.allowed[k] for k, v in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "audit_import_copy_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "audit_import_source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "audit_import_implementation_changed")
        progress("audit_import_complete", **result["counts"], unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history, "diagnostic": result,
            "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "binding": desired,
                "owner": str(owner), "head": head, "plan_record": PLAN, "report_record": REPORT,
                "state_artifact": SUCCESSOR, "completed_producer": proof,
                "parent_import_artifact": plan["import_artifact"], "dispositions_artifact": report["dispositions_artifact"],
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata), "size_manifest_artifact": manifest_ref,
                "size_preflight_record": preflight_record, "copied_artifacts": dict(reader.copied),
                "unique_source_artifact_bytes_read": reader.unique_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": observations, "elapsed_seconds": round(time.monotonic()-started, 3)}}

