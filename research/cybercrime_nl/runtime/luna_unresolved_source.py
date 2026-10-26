"""One-owner, retained-only import and diagnosis of the completed rollout.

This capability is called inside a new registered Research prepare operation.
Historical fatal outcomes and liabilities survive; quarantine is isolation, not
an explanation or repair of the discarded provider content.
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

import luna_snippet_rollout_v2 as rollout
import luna_snippet_rollout_source_v2 as previous
from newsresearch.common import digest, require_active
from newsresearch.embeddings import offline_tokenizer
from newsresearch.gateway import ProviderResponse
from newsresearch.storage import check_permissions

base, retained, bounded = previous.base, previous.retained, previous.bounded
Reader = bounded.Reader
require = base.require
METHOD = "luna-unresolved-retained-rollout-v1"
PREFLIGHT = "luna_unresolved_import_preflight"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/cybercrime-nl-luna-snippet-rollout-20261025-v2")
PLAN = "1f067f189235e0b5dc7be250e3156b86bbdfcbd83dd3fe40e2b34df2bdffdb4b"
REPORT = "c3a8be28d5180ca1d2da93fb172a7ad56f133e7646813a0986f06541d0ecbd3b"
FREEZE = "1e985bea6cdfc119b655262fa5df8f3c80fb5d4c1447ab78b0a8a1cbd958fbc3"
SUCCESSOR = "55f4cd27bd2d47a782fdacb9f4478718829ae4ff8e45954378cf406922ff7fc6"
PRIOR_COMMITMENT = 9_710_343_318
POLICY = {**bounded.POLICY, "owners": 1, "bulk_queue_bodies_read": False,
    "historical_parent_sources_reopened": False, "historical_fatal_cleared": False,
    "fatal_packet_all_articles_quarantined": True, "discarded_content_recoverable": False,
    "diagnostic_is_semantic_judgment": False, "unresolved_causes_are_overlapping_evidence_tags": True}


def binding():
    return {"plan_record": PLAN, "report_record": REPORT, "freeze_record": FREEZE, "successor_artifact": SUCCESSOR}


def implementation():
    return {**rollout.implementation(), Path(__file__).relative_to(base.ROOT).as_posix():
        hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


class View(previous.View):
    completed_prepare = rollout.Rollout.completed_prepare
    verify_selection = staticmethod(rollout.Rollout.verify_selection)


def preflight(reader, metadata, engine, session, progress):
    """Finite native fields only. Queue packet lists and evaluation draws stay closed."""
    reader._active()
    require(metadata["source_head"] == reader.head(), "unresolved_preflight_head")
    refs = defaultdict(list)
    def add(ref, kind, identity, field):
        retained.frozen.source_api._sha(ref)
        refs[ref].append({"kind": kind, "identity": identity, "field": field})
    found = set()
    for raw in reader.db.execute("SELECT * FROM records ORDER BY created_event"):
        row = dict(raw)
        value = json.loads(row["payload"])
        add(row["artifact"], row["kind"], row["id"], "artifact")
        if row["id"] == PLAN:
            require(row["kind"] == rollout.PLAN, "unresolved_plan_kind")
            found.add(PLAN)
            for field in ("import_artifact", "selection_artifact", "quote_artifact", "method_artifact"):
                add(value[field], row["kind"], row["id"], field)
        if row["id"] == REPORT:
            require(row["kind"] == rollout.RESULT and value["freeze_record"] == FREEZE
                and value["successor_artifact"] == SUCCESSOR, "unresolved_report_binding")
            found.add(REPORT)
            for field in ("successor_artifact", "change_manifest_artifact"):
                add(value[field], row["kind"], row["id"], field)
        if row["id"] == FREEZE:
            require(row["kind"] == rollout.CHECKPOINT and row["logical_key"] == "freeze-before-draw", "unresolved_freeze_kind")
            found.add(FREEZE)
        if row["kind"] == rollout.CHECKPOINT and row["logical_key"] == "proposals":
            for field in ("artifact", "links_artifact"):
                add(value[field], row["kind"], row["id"], field)
        if row["kind"] == rollout.RESPONSE:
            add(value["response"], row["kind"], row["id"], "response")
            if value["parsed"] is not None:
                add(value["parsed"], row["kind"], row["id"], "parsed")
    require(found == {PLAN, REPORT, FREEZE}, "unresolved_fixed_records")
    fields = {"session.started": ("identity",), "operation.intended": ("input",), "operation.completed": ("result",),
        "model.attempt.intended": ("packet", "request", "dispatch"), "luna_snippet.response.received": ("response",)}
    for event in reader.db.execute("SELECT kind,event_hash,payload FROM events ORDER BY seq"):
        if event["kind"] in fields:
            value = json.loads(event["payload"])
            for field in fields[event["kind"]]:
                add(value[field], event["kind"], event["event_hash"], field)
    entries = [{"reference": ref, "bytes": reader.artifact_size(ref), "anchors": anchors}
        for ref, anchors in sorted(refs.items())]
    total = sum(e["bytes"] for e in entries)
    manifest = {"method": METHOD, "binding": binding(), "owner": str(reader.owner), "head": metadata["source_head"],
        "entries": entries, "distinct_references": len(entries), "total_distinct_bytes": total,
        "maximum_selected_bytes": POLICY["maximum_selected_bytes"], "fits": total <= POLICY["maximum_selected_bytes"],
        "bulk_queue_bodies_selected": False, "scope": "native_metadata_and_executed_requests_only"}
    ref = engine.ledger.artifacts.put(manifest)
    record = engine.ledger.record(session, PREFLIGHT, ref, {"method": METHOD, "implementation": implementation(),
        "manifest_artifact": ref, "binding": binding(), "fits": manifest["fits"]})
    progress("unresolved_size_preflight", selected_bytes=total, references=len(entries), fits=manifest["fits"])
    require(manifest["fits"], "unresolved_preflight_byte_limit")
    reader.allowed = {e["reference"]: e["bytes"] for e in entries}
    return manifest, ref, record


def checkpoint(reader, key, plan, report):
    ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?",
        (rollout.CHECKPOINT, key))]
    require(len(ids) == 1, "unresolved_checkpoint_unique")
    row = reader.record(ids[0], rollout.CHECKPOINT)
    base.keyed(reader, row, key)
    require(row["plan"] == PLAN and plan["_created_event"] < row["_created_event"] < report["_created_event"], "unresolved_checkpoint_binding")
    return row


def authority(reader):
    plan, intent = base.one(reader, rollout.PLAN, PLAN), base.one(reader, rollout.INTENT)
    report = base.one(reader, rollout.RESULT, REPORT)
    reader.ensure_report_last(report)
    for row, key in ((plan, rollout.METHOD), (intent, rollout.METHOD), (report, PLAN)):
        base.keyed(reader, row, key)
    require(report["method"] == rollout.METHOD and report["plan"] == PLAN and report["rollout_finished"] is True
        and report["freeze_record"] == FREEZE and report["successor_artifact"] == SUCCESSOR, "unresolved_result_binding")
    view = View(reader)
    public, imported, selection = rollout.Rollout.load_plan(view)
    require(public["id"] == PLAN, "unresolved_plan_identity")
    expected = rollout.versions(base.plain(intent))
    require(set(plan["versions"]) == set(expected), "unresolved_version_set")
    for kind, content in expected.items():
        ids = [r[0] for r in reader.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?", (kind, rollout.METHOD))]
        require(ids == [plan["versions"][kind]], "unresolved_version_identity")
        row = reader.record(ids[0], kind)
        base.keyed(reader, row, rollout.METHOD)
        require(row["content"] == content and row["branch"] == "main" and row["reason"] is None
            and intent["_created_event"] < row["_created_event"] < plan["_created_event"], "unresolved_version_binding")
    proof = retained.completed(reader, report, plan["implementation"])
    require(reader.artifact(proof["input"]) == {"action": "run", "allow_paid_execution": True}, "unresolved_completed_run")
    provenance = imported["provenance"]
    require(provenance["method"] == previous.METHOD and provenance["implementation"] == previous.implementation()
        and provenance["plan_record"] == previous.PLAN and provenance["report_record"] == previous.REPORT
        and provenance["state_artifact"] == digest(imported["state"]) == previous.SUCCESSOR
        and provenance["source_head_unchanged"] is True, "unresolved_import_authority")
    prior_row = reader.record(provenance["size_preflight_record"], previous.PREFLIGHT)
    require(prior_row["method"] == previous.METHOD and prior_row["fits"] is True
        and prior_row["manifest_artifact"] == provenance["size_manifest_artifact"]
        and intent["_created_event"] < prior_row["_created_event"] < plan["_created_event"], "unresolved_import_checkpoint")
    prefix, _ = base.session_prefix(reader, plan["_created_event"], plan["implementation"], {"action": "prepare"})
    require(prior_row["_created_event"] in {r["seq"] for r in prefix}, "unresolved_import_session")
    freeze = checkpoint(reader, "freeze-before-draw", plan, report)
    require(freeze["_record_id"] == FREEZE and freeze["successor_artifact"] == SUCCESSOR
        and freeze["change_manifest_artifact"] == report["change_manifest_artifact"], "unresolved_freeze_binding")
    state, changes = reader.artifact(SUCCESSOR), reader.artifact(report["change_manifest_artifact"])
    require(digest(rollout.repair.commit(imported["state"], changes, reason=rollout.METHOD)) == SUCCESSOR
        and previous.statistics_equal(rollout.statistics(imported["state"]), report["before"])
        and previous.statistics_equal(rollout.statistics(state), report["after"])
        and report["changes"] == len(changes), "unresolved_successor_replay")
    return plan, report, imported, selection, state, freeze, proof


def packet_members(packet, source):
    if packet["role"] == "snippet_proposal":
        members = packet["article_ids"]
        bound = [i for u in packet["unit_bindings"].values() for i in u["members"]]
        require(sorted(bound) == members and len(bound) == len(set(bound)), "unresolved_proposal_articles")
    elif packet["role"] in {"group_membership", "group_quality"}:
        members = packet["members"]
        require(members == sorted(set(members)) and packet["membership_revision"] == digest(members), "unresolved_membership_identity")
        logical = digest([rollout.contract.METHOD, packet["role"], packet["membership_revision"],
            [(i, source["documents"][i]["input_sha256"]) for i in members]])
        require(packet["logical_ids"] == [logical], "unresolved_membership_logical_identity")
    elif packet["role"] == "final_reference":
        members = sorted(v["document_id"] for v in packet["source_bindings"].values())
    else:
        require(False, "unresolved_packet_role")
    require(bool(members) and len(members) == len(set(members)) and set(members) <= set(source["documents"]), "unresolved_packet_population")
    return members


def physical_census(reader, plan, report, source, selection, imported_history, progress):
    """Read each physical packet once; retain only compact evidence after replay."""
    queues, assessments, receipts, completions = {}, {}, {}, {}
    for row in reader.rows(rollout.QUEUE):
        base.keyed(reader, row, row["name"])
        require(row["plan"] == PLAN and row["implementation"] == plan["implementation"]
            and row["category"] in {"proposal", "qa", "validation"}
            and plan["_created_event"] < row["_created_event"] < report["_created_event"], "unresolved_queue_binding")
        queues[row["_record_id"]] = row
    for row in reader.rows(rollout.RESPONSE):
        require(row["attempt"] not in assessments, "unresolved_duplicate_assessment")
        base.keyed(reader, row, row["attempt"])
        assessments[row["attempt"]] = row
    for kind, target in (("luna_snippet.response.received", receipts), ("model.attempt.completed", completions)):
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
    selected = {p["task_key"]: p for p in selection["packets"]}
    facts, intents, health_rows, question_answers, links, fatal, clarities = [], {}, {}, [], [], [], []
    proposal_parsed = {}
    attempted, usable, quarantine, seen_attempts = set(), set(), set(), set()
    counters = {"new_settled_nanousd": 0, "new_held_nanousd": 0, "unknown_holds": 0}
    by_category = {"proposal": 0, "qa": 0, "validation": 0}
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
        require(value["method"] == rollout.METHOD and value["batch"] == PLAN and value["number"] == 1
            and value["category"] == queue["category"] and packet["task_key"] == key
            and value["packet"] == digest(packet) and value["request"] == packet["request_sha256"] == digest(packet["request"])
            and value["reserved_nanousd"] == packet["reservation_nanousd"] == rollout.contract.reservation(packet), "unresolved_intent_binding")
        require(reader.artifact(value["request"]) == packet["request"]
            and reader.artifact(value["dispatch"]) == rollout.wire.Invocation(packet["request"], attempt, kind=packet["kind"]).manifest(), "unresolved_wire_binding")
        require(len(packet["logical_ids"]) == len(set(packet["logical_ids"]))
            and not logical.intersection(packet["logical_ids"]), "unresolved_logical_retry")
        members = packet_members(packet, source)
        tasks.add(key)
        logical.update(packet["logical_ids"])
        seen_attempts.add(attempt)
        intents[key] = value
        receipt, assessment, completion = receipts.get(attempt), assessments.get(attempt), completions.get(attempt)
        parsed, derived, envelope = None, None, None
        if receipt:
            require(raw["seq"] < receipt["sequence"] < report["_created_event"], "unresolved_receipt_chronology")
            envelope = reader.artifact(receipt["response"])
            derived, parsed = rollout.outcome(packet, ProviderResponse(**envelope))
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
        if assessment:
            fact["artifact_refs"].update(response_record=assessment["_record_id"], parsed=assessment["parsed"])
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
        if packet["role"] == "snippet_proposal":
            require(key in selected and digest(selected[key]) == digest(packet), "unresolved_selected_proposal")
            attempted.add(key)
            exposed.update(members)
            history["proposal_packets"].append({**fact, "displayed_document_ids": members})
            for name in packet["question_map"]:
                identity = rollout.grouping.normalized_question_identity(packet, name)
                history["proposal_questions"].setdefault(identity, []).append({**fact, "question_name": name,
                    "source_unit": packet["question_map"][name], "menus": packet["menus"], "displayed_document_ids": members})
            if good:
                usable.add(key)
                proposal_parsed[key] = (attempt, parsed)
        elif packet["role"] in {"group_membership", "group_quality"}:
            exposed.update(members)
            stage = "member" if packet["role"] == "group_membership" else "card"
            revision = packet["membership_revision"]
            item = memberships.setdefault(revision, {"members": members, "member_attempted": False, "card_attempted": False,
                "member_supported": False, "card_supported": False, "blocked": False,
                "member_result_ref": None, "card_result_ref": None, "card": None, "provenance": []})
            require(item["members"] == members and not item[stage+"_attempted"], "unresolved_membership_retry")
            supported = bool(good and derived["members_supported" if stage == "member" else "group_supported"])
            if supported:
                builder = rollout.contract.member_packet if stage == "member" else rollout.contract.group_packet
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
        else:
            final_ids.update(packet["logical_ids"])
        if len(facts) % 100 == 0:
            progress("unresolved_replaying_attempts", physical_attempts=len(facts), unique_source_artifact_bytes_read=reader.unique_bytes)
    require(set(assessments) <= set(receipts) <= seen_attempts and set(completions) <= set(assessments), "unresolved_orphan_metadata")
    # Native run collects proposal answers in selection order, while concurrent
    # workers may have written their physical intents in a different order.
    for packet in selection["packets"]:
        key = packet["task_key"]
        if key in proposal_parsed:
            attempt, parsed = proposal_parsed[key]
            links.extend(parsed["links"])
            question_answers.extend({**a, "physical_attempt": attempt, "task_key": key} for a in parsed["answers"].values())
    health = rollout.prior.health_state(intents, health_rows)
    expected = {**counters, "attempted_requests": len(facts), "returned_requests": len(receipts),
        "usable_requests": sum(r["usable"] for r in assessments.values()),
        "new_committed_nanousd": counters["new_settled_nanousd"]+counters["new_held_nanousd"],
        "category_commitments_nanousd": by_category, "health": health}
    expected["combined_commitment_nanousd"] = rollout.PRIOR_COMMITMENT+expected["new_committed_nanousd"]
    require(all(digest(report[k]) == digest(v) for k, v in expected.items())
        and expected["combined_commitment_nanousd"] == PRIOR_COMMITMENT, "unresolved_cost_census")
    require(type(report["queued_requests"]) is int and type(report["unattempted_requests"]) is int
        and report["unattempted_requests"] >= 0 and report["queued_requests"] == len(facts)+report["unattempted_requests"], "unresolved_prepared_counts")
    history.update(logical_ids=sorted(logical), task_keys=sorted(tasks), prior_final_reference_logical_ids=sorted(final_ids),
        development_exposed_documents=sorted(exposed), quarantine_document_ids=sorted(quarantine),
        historical_fatal_cases=fatal, historical_response_health=health,
        current_rollout_liabilities=expected, global_history_complete=False,
        prepared_only_summary={"enumerated": False, "reported_queued_requests": report["queued_requests"],
            "reported_unattempted_requests": report["unattempted_requests"], "report_record": REPORT})
    return history, {"facts": facts, "attempted": attempted, "usable": usable, "links": links,
        "answers": question_answers, "fatal_cases": fatal, "clarity": clarities, "queues": queues, "counts": expected}


def diagnose(reader, plan, report, selection, state, history, census):
    row = checkpoint(reader, "proposals", plan, report)
    links, proposed = reader.artifact(row["links_artifact"]), reader.artifact(row["artifact"])
    require(links == census["links"] and proposed == rollout.grouping.proposals(links, selection["units"]), "unresolved_proposal_replay")
    stages = [checkpoint(reader, name+"/completed", plan, report) for name in ("primary", "fallback")]
    rejected = set(stages[0]["rejected"])
    fallback = [p for p in proposed["fallbacks"] if set(p["parent_revisions"]) & rejected]
    candidates = {p["membership_revision"]: p for p in [*proposed["primary"], *fallback]}
    evidence = {"checkpoint": row["_record_id"], "proposal_artifact": row["artifact"], "links_artifact": row["links_artifact"]}
    history["resolution_proposals"] = [{**p, "provenance": evidence} for p in candidates.values()]
    history["proposal_links"] = links
    history["proposal_units"] = selection["units"]
    coverage = rollout.grouping.coverage_status(selection, census["attempted"], census["usable"])
    require(coverage == report["coverage"], "unresolved_coverage_replay")
    by_doc = {i: u for u, unit in selection["units"].items() for i in unit["members"]}
    def index(rows, members):
        result = defaultdict(list)
        for item in rows:
            for i in members(item):
                result[i].append(item)
        return result
    candidates_by_doc = index(candidates.values(), lambda p: p["members"])
    facts_by_doc = index(census["facts"], lambda p: p["members"])
    clarity_by_doc = index(census["clarity"], lambda p: [p["document_id"]])
    answers_by_unit = index(census["answers"], lambda p: [p["unit_id"]])
    links_by_unit = index(links, lambda p: [p["source"], p["target"]])
    quarantine = set(history["quarantine_document_ids"])
    shown = set(coverage["actual_shown_article_ids"])
    cp = selection["coverage_plan"]
    prior_segments = {r["segment_id"] for r in cp["prior_blocked"]}
    rows, tags = [], Counter()
    for i in sorted(state["unresolved_ids"]):
        require(i in by_doc, "unresolved_input_unit")
        unit = by_doc[i]
        menu = cp["anchors"][unit]
        keys = [cp["segment_packets"][s] for s in menu["segments"] if s in cp["segment_packets"]]
        status = ("no_candidates" if not menu["targets"] else "capacity" if menu["unavailable"] else
            "prior_blocked" if prior_segments.intersection(menu["segments"]) else
            ("complete_joint" if menu["mode"] == "complete" else "all_shards") if keys and all(k in census["usable"] for k in keys) else
            "partial" if any(k in census["attempted"] for k in keys) else "unattempted")
        reasons = set()
        if i in quarantine:
            reasons.add("quarantined_fatal_packet")
        if status in {"unattempted", "partial", "capacity", "prior_blocked", "no_candidates"}:
            reasons.add("proposal_"+status)
        if not candidates_by_doc[i]:
            reasons.add("no_retained_direct_star_proposal")
        proposals = []
        for p in candidates_by_doc[i]:
            revision = p["membership_revision"]
            outcomes = [{"checkpoint": s["_record_id"], "unavailable": s["unavailable"].get(revision),
                "rejected": revision in s["rejected"], "supported": revision in s["supported"]} for s in stages]
            reasons.update("qa_"+str(o["unavailable"]) for o in outcomes if o["unavailable"])
            if any(o["rejected"] for o in outcomes):
                reasons.add("qa_semantically_unsupported")
            if any(o["supported"] for o in outcomes):
                reasons.add("supported_candidate_not_committed")
            proposals.append({"membership_revision": revision, "members": p["members"], "stage_outcomes": outcomes})
        if not clarity_by_doc[i]:
            reasons.add("no_current_usable_clarity_observation")
        tags.update(reasons)
        rows.append({"document_id": i, "starting_unit": unit, "proposal_menu_status": status,
            "context_or_anchor_shown": i in shown, "quarantined": i in quarantine,
            "proposal_answers": answers_by_unit[unit], "direct_links": links_by_unit[unit],
            "proposals": proposals, "physical_attempts": [f["physical_attempt"] for f in facts_by_doc[i]],
            "clarity_observations": clarity_by_doc[i], "evidence_tags": sorted(reasons)})
    require(len(rows) == report["after"]["unresolved_inputs"], "unresolved_diagnostic_population")
    admission = bool(census["fatal_cases"]) and all(f["is_bound_content_guard"] for f in census["fatal_cases"]) \
        and report["health"]["stop_reason"] == "response_content_rejected"
    return {"unresolved_rows": rows, "fatal_cases": census["fatal_cases"],
        "scope_admission_allowed": admission,
        "quarantined_document_ids": sorted(quarantine), "quarantined_unresolved_ids": sorted(quarantine & set(state["unresolved_ids"])),
        "counts": {"unresolved_inputs": len(rows), "quarantined_inputs": len(quarantine),
            "quarantined_unresolved_inputs": len(quarantine & set(state["unresolved_ids"])), "fatal_packets": len(census["fatal_cases"]),
            "evidence_tags": dict(tags), "tags_overlap": True}, "coverage": coverage,
        "physical_accounting": census["counts"], "proposal_evidence": evidence,
        "historical_fatal_cleared": False, "discarded_content_recoverable": False,
        "semantic_cause_inferred": False, "singleton_uniqueness_proved": False}


def collect(engine, session, *, binding=None, deadline_monotonic=None):
    require_active(engine, session)
    require(engine.config.offline, "unresolved_offline_only")
    desired = globals()["binding"]()
    require(binding is None or binding == desired, "unresolved_fixed_binding")
    started = time.monotonic()
    deadline = started+POLICY["maximum_seconds"] if deadline_monotonic is None else deadline_monotonic
    require(isinstance(deadline, (int, float)) and math.isfinite(deadline)
        and 0 < deadline-started <= POLICY["maximum_seconds"], "unresolved_deadline")
    code = implementation()
    owner = retained.frozen.discovery.canonical_path(str(OWNER))
    observer = retained.frozen.discovery.study.WindowsProcessObserver()
    def progress(stage, **values):
        callback = getattr(engine, "source_progress", None)
        if callback:
            callback({"stage": stage, "elapsed_seconds": round(time.monotonic()-started, 3), **values})
    with ExitStack() as stack:
        retained.frozen._stop(engine, session, [owner], deadline)
        progress("unresolved_opening_completed_rollout")
        observations = [retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner)]
        reader = Reader(engine, session, owner, deadline=deadline)
        stack.callback(reader.close)
        reader.read_progress = progress
        metadata = retained.frozen.discovery.metadata_census(reader)
        head, stop = reader.head(), retained.frozen._historical_stop(owner)
        manifest, manifest_ref, preflight_record = preflight(reader, metadata, engine, session, progress)
        plan, report, imported, selection, state, freeze, proof = authority(reader)
        history, census = physical_census(reader, plan, report, imported["source"], selection, imported["history"], progress)
        diagnostic = diagnose(reader, plan, report, selection, state, history, census)
        history["development_exposed_documents"] = sorted(set(history["development_exposed_documents"]) | set(freeze["exposed_documents"]))
        history["original_rollout_validation_seed"] = freeze["seed"]
        source = imported["source"]
        del selection, census, imported
        reader._active()
        require(set(reader.copied) <= set(reader.allowed) and all(v == reader.allowed[k] for k, v in reader.copied.items())
            and sum(reader.copied.values()) == reader.unique_bytes <= manifest["total_distinct_bytes"], "unresolved_copy_partition")
        require(reader.head(fresh=True) == head and retained.frozen._historical_stop(owner) == stop, "unresolved_source_changed")
        check_permissions(owner, root=True)
        check_permissions(owner/"objects")
        observations.append(retained.frozen.source_api._liveness(lambda p: observer.observe(engine, session, p), owner))
        require(implementation() == code, "unresolved_implementation_changed")
        progress("unresolved_import_complete", **diagnostic["counts"], unique_source_artifact_bytes_read=reader.unique_bytes)
        return {"source": source, "state": state, "history": history, "diagnostic": diagnostic,
            "prior_commitment_nanousd": PRIOR_COMMITMENT,
            "provenance": {"method": METHOD, "implementation": code, "policy": POLICY, "binding": desired,
                "owner": str(owner), "head": head, "plan_record": PLAN, "report_record": REPORT,
                "freeze_record": FREEZE, "state_artifact": SUCCESSOR, "completed_producer": proof,
                "metadata_census_artifact": engine.ledger.artifacts.put(metadata), "size_manifest_artifact": manifest_ref,
                "size_preflight_record": preflight_record, "copied_artifacts": dict(reader.copied),
                "unique_source_artifact_bytes_read": reader.unique_bytes, "source_head_unchanged": True,
                "historical_stop": stop, "liveness": observations, "elapsed_seconds": round(time.monotonic()-started, 3)}}
