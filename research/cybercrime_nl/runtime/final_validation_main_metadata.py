"""Exact retained main-owner metadata projections; no source/model operations.

This separate registered result changes only proved metadata gap hashes. It does
not change a physical task's role, reference blocker, P state, or liability.
Unknown operations and unsupported nested report/phase schemas remain gaps.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import final_validation_history_roots as roots
import final_validation_lifecycle_evidence as lifecycle
import final_validation_native_artifacts as supplement
import run_dossiers_v8 as v8
from newsresearch.common import AuditError, digest, require_active
from newsresearch.runtime import Research, audited_handler

METHOD = "final-validation-retained-main-metadata-v1"
INTENT = "final_validation_main_metadata_intent"
RESULT = "final_validation_main_metadata_resolution"
POLICY = {**roots.POLICY, "only_main_metadata_gaps_discharged": True,
    "task_roles_unchanged": True, "pair_blockers_unchanged": True,
    "missing_artifacts_remain_unresolved": True}
RESPONSE_FIELDS = {"plan", "task_key", "phase", "category", "packet", "request", "response", "attempt",
    "parsed", "cost_nanousd", "reserved_nanousd", "hold", "validation_error", "http_status", "at"}
RESPONSE_OPTIONAL = {"execution_amendment", "diagnostic_plan", "parent_diagnostic_plan"}


def require(value, reason):
    if not value:
        raise AuditError("main_metadata_" + reason)


def implementation():
    path = Path(__file__)
    return {**roots.implementation(), **lifecycle.implementation(), **supplement.implementation(), **v8.implementation(),
        path.relative_to(roots.closure.ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()}


def raw(row):
    return json.loads(row["payload"])


def same(a, b):
    return digest(a) == digest(b)


def timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _derive(owner_id, owner, main_rows, main_manifest, base, read, *,
            documents=None, count_tokens=None, embedding_phase=None, amendments=None):
    """Pure projection after concrete parent replay. Never accepts a complete flag."""
    events = {e["event_hash"]: e for e in owner["events"]}
    records = {r["id"]: r for r in owner["records"]}
    require(len(events) == len(owner["events"]) and len(records) == len(owner["records"]), "duplicate_metadata")
    original = base["owner_partitions"][owner_id]
    require(same(original["source_head"], owner["scope"]["source_head"])
        and original["full_census_artifact"] == owner["full_census_artifact"], "same_main_cutoff")
    represented = {r["original_attempt"]: r for r in main_rows}
    require(len(represented) == len(main_rows), "unique_task_partition")
    intents = {raw(e)["attempt"]: e for e in events.values() if e["kind"] == "model.attempt.intended"}
    require(len(intents) == sum(e["kind"] == "model.attempt.intended" for e in events.values())
        and set(intents) == set(represented), "complete_existing_task_partition")
    proved_records, proved_events, missing = {}, {}, set()

    def artifact(ref):
        if not isinstance(ref, str) or not re.fullmatch("[0-9a-f]{64}", ref):
            return None
        try:
            return read(ref)
        except KeyError:
            missing.add(ref)
            return None
        except AuditError as error:
            if str(error) != "Required artifact is missing":
                raise
            missing.add(ref)
            return None

    def prove_record(row, rule, evidence):
        proved_records[row["id"]] = {"rule": rule, "evidence": evidence}

    responses = {}
    for row in records.values():
        value = raw(row)
        if row["kind"] != "cyber_dossier_response":
            continue
        attempt = value.get("attempt")
        if attempt not in represented or represented[attempt].get("response_record") != row["id"]:
            continue
        intent_row, task = intents[attempt], represented[attempt]
        intent = raw(intent_row)
        if not RESPONSE_FIELDS <= set(value) or set(value) - RESPONSE_FIELDS - RESPONSE_OPTIONAL:
            continue
        if not (row["logical_key"] == value["task_key"] == task["task_key"]
                and value["plan"] == main_manifest["plan"] == intent["batch"]
                and row["created_event"] > intent_row["seq"]
                and row["supersedes"] is None and timestamp(value["at"])
                and type(value["hold"]) is bool
                and all(same(value.get(k), intent.get(k)) for k in
                    ("packet", "request", "phase", "category", *RESPONSE_OPTIONAL))):
            continue
        if not (value["cost_nanousd"] is None or type(value["cost_nanousd"]) is int and value["cost_nanousd"] >= 0):
            continue
        if not (type(value["reserved_nanousd"]) is int and value["reserved_nanousd"] >= 0
                and (value["http_status"] is None or type(value["http_status"]) is int)
                and (value["validation_error"] is None or isinstance(value["validation_error"], str))):
            continue
        # The existing exact task proof remains the authority for the question.
        # This classifies a response projection, never its semantic correctness.
        if artifact(value["response"]) is None or (value["parsed"] is not None and artifact(value["parsed"]) is None):
            continue
        responses[attempt] = row
        prove_record(row, "exact_native_response_of_represented_task", {"intent_event": intent_row["event_hash"],
            "task_key": task["task_key"], "response": value["response"], "parsed": value["parsed"],
            "underlying_disposition": task["disposition"], "semantic_correctness_inferred": False})

    completion_counts = Counter(raw(e).get("attempt") for e in events.values() if e["kind"] == "model.attempt.completed")
    for event in events.values():
        value = raw(event)
        if event["kind"] != "model.attempt.completed" or set(value) != {"attempt", "status", "assessment", "response", "ended_at"}:
            continue
        row = responses.get(value["attempt"])
        if row is None or completion_counts[value["attempt"]] != 1:
            continue
        response = raw(row)
        if (value["assessment"] == row["id"] and value["response"] == response["response"]
                and response["hold"] is False and event["seq"] > row["created_event"]
                and value["status"] == ("valid" if response["parsed"] is not None else "invalid")
                and timestamp(value["ended_at"])):
            proved_events[event["event_hash"]] = {"rule": "exact_native_completion_projection", "response_record": row["id"]}

    for row in records.values():
        value = raw(row)
        if row["kind"] == "cyber_dossier_seed_revalidation":
            required = {"method", "versions", "parent_plan", "parent_execution_amendment", "source_response_record",
                "source_response_record_sha256", "task_key", "source_attempt", "source_packet", "source_request",
                "source_response", "source_validation_error", "normalization_version", "canonical_packet_sha256",
                "request_sha256", "parsed", "status", "model_calls", "cost_nanousd", "original_rows_unchanged", "at"}
            source_row = records.get(value.get("source_response_record"))
            if set(value) != required or source_row is None or source_row["id"] not in proved_records:
                continue
            source = {**raw(source_row), "_record_id": source_row["id"]}
            v8_rows = [r for r in (amendments or {}).values() if r.get("method") == v8.METHOD]
            if not (value["method"] == v8.METHOD and source_row["id"] in v8.SOURCE_RESPONSES
                    and len(v8_rows) == 1 and row["id"] in v8_rows[0]["derived_revalidation_records"]
                    and same(value["versions"], v8_rows[0]["versions"])
                    and value["parent_plan"] == main_manifest["plan"]
                    and value["parent_execution_amendment"] == v8.PARENT_AMENDMENT
                    and value["source_response_record_sha256"] == digest(source)
                    and value["source_validation_error"] == v8.ERROR and value["normalization_version"] == v8.NORMALIZATION
                    and value["source_attempt"] == source["attempt"] and value["task_key"] == source["task_key"]
                    and all(value["source_" + k] == source[k] for k in ("packet", "request", "response"))
                    and row["logical_key"] == source_row["id"] and row["created_event"] > source_row["created_event"]
                    and same([value["model_calls"], value["cost_nanousd"], value["original_rows_unchanged"]], [0, 0, True])
                    and value["status"] == "valid" and timestamp(value["at"])):
                continue
            inputs = [artifact(source[k]) for k in ("packet", "response", "request")]
            parsed = artifact(value["parsed"])
            if any(v is None for v in inputs) or parsed is None:
                continue
            normalized, expected = v8.revalidate_retained(source, *inputs)
            if same(parsed, expected) and value["canonical_packet_sha256"] == digest(normalized) and value["request_sha256"] == source["request"]:
                prove_record(row, "exact_v8_local_seed_revalidation", {"source_response_record": source_row["id"], "new_attempts": 0})
        elif row["kind"] == "cyber_dossier_evidence_card" and documents is not None and callable(count_tokens):
            if set(value) != {"dossier_id", "membership_revision", "card_version", "document_ids", "artifact", "execution_amendment", "model_generation_calls"}:
                continue
            ids = value["document_ids"]
            if not (isinstance(ids, list) and ids == sorted(set(ids)) and all(i in documents for i in ids)
                    and value["execution_amendment"] in (amendments or {})
                    and value["model_generation_calls"] == 0 and type(value["model_generation_calls"]) is int
                    and row["logical_key"] == digest([value["dossier_id"], value["membership_revision"]])):
                continue
            card = artifact(value["artifact"])
            if card is None:
                continue
            expected = roots.closure.batch.task.main.prior.v5.build_evidence_card(
                [documents[i] for i in ids], value["dossier_id"], value["membership_revision"], count_tokens=count_tokens, max_tokens=32000)
            if same(card, expected) and value["card_version"] == card["card_version"]:
                prove_record(row, "exact_extractive_card_builder", {"card_artifact": value["artifact"], "new_model_calls": 0})
        elif row["kind"] == "cyber_dossier_phase" and embedding_phase is not None:
            if same(row, embedding_phase):
                prove_record(row, "original_embedding_replay_phase", {"phase_record": row["id"], "artifact": value["artifact"]})

    # Framework envelopes do not decide the purpose of their operation body.
    # An unknown input/result remains its own gap, even when its session shell is exact.
    sessions = {}
    for event in events.values():
        sessions.setdefault(event["session_id"], []).append(event)
    expected_core = v8.implementation()
    core = {k.replace("\\", "/"): v for k, v in expected_core.items() if k.replace("\\", "/") in {
        "src/newsresearch/runtime.py", "src/newsresearch/storage.py", "src/newsresearch/common.py"}}
    for rows in sessions.values():
        starts = [e for e in rows if e["kind"] == "session.started"]
        intentions = [e for e in rows if e["kind"] == "operation.intended"]
        if len(starts) != 1 or len(intentions) != 1:
            continue
        start, intended = starts[0], intentions[0]
        header, operation = raw(start), raw(intended)
        if not (set(header) == {"context", "identity", "configuration", "preflight", "actor_assurance"}
                and set(operation) == {"operation", "input"} and start["seq"] < intended["seq"]
                and isinstance(operation["operation"], str)):
            continue
        identity, request = artifact(header["identity"]), artifact(operation["input"])
        if identity is None or request is None or not isinstance(identity, dict):
            continue
        code = identity.get("code_files")
        if not (isinstance(code, dict) and identity.get("code_digest") == digest(code)
                and core and all(code.get(k) == v for k, v in core.items())):
            continue
        context = header["context"]
        if not (isinstance(context, dict) and set(context) == {"objective", "actor", "versions"}
                and all(isinstance(context[k], str) for k in ("objective", "actor"))
                and isinstance(context["versions"], dict) and isinstance(header["configuration"], dict)
                and isinstance(header["preflight"], dict) and header["preflight"].get("status") == "verified"
                and header["actor_assurance"] == "self-asserted local operator"):
            continue
        proved_events[start["event_hash"]] = {"rule": "exact_core_session_shell_only", "identity": header["identity"],
            "operation_input_still_separately_classified": True}
        completed = [e for e in rows if e["kind"] == "operation.completed"]
        failed = [e for e in rows if e["kind"] == "operation.failed"]
        ended = [e for e in rows if e["kind"] == "session.ended"]
        if len(completed) == 1 and not failed:
            event, result_value = completed[0], raw(completed[0])
            if set(result_value) == {"operation", "result"} and result_value["operation"] == operation["operation"] and event["seq"] > intended["seq"]:
                result = artifact(result_value["result"])
                # The generic version handler is an exact deterministic record
                # projection. Other operation bodies require separate producers.
                if operation["operation"] == "version" and isinstance(request, dict) and isinstance(result, dict):
                    rid = result.get("id")
                    row = records.get(rid)
                    allowed = {"kind", "key", "content", "supersedes", "reason", "branch"}
                    if (row is not None and {"kind", "key", "content"} <= set(request) <= allowed
                            and isinstance(request["content"], dict) and set(result) == {"id", "kind"}
                            and result["kind"] == row["kind"] == request["kind"] and row["logical_key"] == request["key"]
                            and row["supersedes"] == request.get("supersedes") and intended["seq"] < row["created_event"] < event["seq"]
                            and same(raw(row), {"content": request["content"], "registered_by": context["actor"],
                                "reason": request.get("reason"), "branch": request.get("branch", "main")})):
                        # Registration may itself contain substantive source/review
                        # text. Only its output envelope duplicates that input;
                        # the intended input remains unresolved here.
                        proved_events[event["event_hash"]] = {"rule": "exact_version_output_duplicates_input", "record_id": rid,
                            "operation_input_still_unresolved": True}
                        prove_record(row, "exact_version_record_duplicates_input", {"operation_input": operation["input"],
                            "input_event": intended["event_hash"], "input_remains_unresolved": True})
                if result is not None and len(ended) == 1 and ended[0]["seq"] > event["seq"] and same(raw(ended[0]), {"status": "completed"}):
                    proved_events[ended[0]["event_hash"]] = {"rule": "exact_session_end_shell_only", "completion_event": event["event_hash"]}
        elif len(failed) == 1 and not completed and not ended:
            event, failure = failed[0], raw(failed[0])
            if (set(failure) == {"operation", "error_type"} and failure["operation"] == operation["operation"]
                    and isinstance(failure["error_type"], str) and re.fullmatch("[A-Za-z_][A-Za-z0-9_]*", failure["error_type"])
                    and event["seq"] > intended["seq"]):
                proved_events[event["event_hash"]] = {"rule": "exact_failure_shell_only", "operation_input_still_unresolved": True}

    removed, kept = [], []
    record_hashes, event_hashes = {digest(k) for k in proved_records}, {digest(k) for k in proved_events}
    for region in base["unresolved_regions"]:
        valid = region["owner_sha256"] == owner_id and ((region["reason_code"] == "unclassified_full_record"
            and region["evidence_sha256"] in record_hashes) or (region["reason_code"] == "unclassified_full_event"
            and region["evidence_sha256"] in event_hashes))
        (removed if valid else kept).append(region)
    result = deepcopy(base)
    result["unresolved_regions"] = kept
    for row in result["owner_partitions"][owner_id]["records"]:
        if row["record_id"] in proved_records:
            row["disposition"] = proved_records[row["record_id"]]["rule"]
    for row in result["owner_partitions"][owner_id]["events"]:
        if row["event_hash"] in proved_events:
            row["disposition"] = proved_events[row["event_hash"]]["rule"]
    result["scoped_certificate"].update(complete=not kept, global_gap=any(r["affected_input_sha256"] is None for r in kept),
        unknown_input_sha256=sorted({i for r in kept for i in (r["affected_input_sha256"] or [])}))
    result["counts"].update(unresolved_regions=len(kept), global_regions=sum(r["affected_input_sha256"] is None for r in kept))
    pending = {(r["reason_code"], r["evidence_sha256"]) for r in kept if r["owner_sha256"] == owner_id}
    proof = {"main_owner_sha256": owner_id, "source_head": owner["scope"]["source_head"],
        "proved_records": proved_records, "proved_events": proved_events, "missing_artifacts": sorted(missing),
        "discharged_metadata_gaps": removed, "inherited_projection_sha256": digest(base),
        "derived_projection_sha256": digest(result), "pair_blockers_unchanged": same(result["pair_role_blockers"], base["pair_role_blockers"]),
        "remaining_metadata_counts": {
            "records_by_kind": dict(sorted(Counter(r["kind"] for r in records.values()
                if ("unclassified_full_record", digest(r["id"])) in pending).items())),
            "events_by_kind": dict(sorted(Counter(e["kind"] for e in events.values()
                if ("unclassified_full_event", digest(e["event_hash"])) in pending).items()))}}
    return result, proof


def resolve_completed_metadata(engine, session, context, closure_record, lifecycle_record, supplement_record, *, create=True):
    require_active(engine, session)
    require(isinstance(engine, roots.closure.HistoryClosureParent) and engine.config.offline, "concrete_offline_parent")
    resolved = roots.resolve_completed_roots(engine, session, context, closure_record, create=create)
    require(resolved.get("resolved"), "completed_root_resolution_required")
    closed = engine.ledger.get(closure_record, roots.closure.RESULT)
    selected = closed["binding"]["binding"]
    value, index, owners, main, _, _, _, census, _, _ = roots.closure.HistoryClosureParent._evidence(engine, selected)
    require(len(main) == 1, "one_main_owner")
    oid = next(iter(main))
    life = engine._one(lifecycle.RESULT)
    require(life["id"] == lifecycle_record, "unique_completed_lifecycle")
    task_id = value["binding"]["task_census_record"]
    lifecycle.LifecycleParent._verify(engine, life["payload"], task_id)
    retained, fixed_refs = supplement.verify_completed(engine, task_id, lifecycle_record, supplement_record)
    children = [c for c in life["payload"]["children"] if c["owner_sha256"] == oid]
    require(len(children) == 1 and same(children[0]["source_head"], owners[oid]["scope"]["source_head"]), "same_lifecycle_main_head")
    lifecycle_projection = lifecycle.replay(engine, children[0], task_census_record=task_id)
    allowed = {r["artifact"] for r in fixed_refs + lifecycle_projection["references"]}
    read = engine.ledger.artifacts.read
    base = read(resolved["projection_artifact"])
    main_artifacts = read(census["artifacts"]["main"])
    manifest = read(main_artifacts["manifest"])
    # The existing parent replays original snapshot/preparation authority; no
    # fresh source observation or source owner is opened by _chain/_documents.
    chain = engine._chain(census["binding"])
    snapshot, original_index, prepared = chain[:3]
    require(original_index == index, "snapshot_index")
    documents = {d["document_id"]: d for d in engine._documents(snapshot, index)}
    token = engine.ledger.get(main_artifacts["tokenizer_record"])
    counter = roots.closure.batch.task.parent.packets.load_token_counter(
        evidence_record=main_artifacts["tokenizer_record"], expected_identity=token["identity"])
    require(counter.validate() == token["configuration_sha256"], "tokenizer_binding")
    replay = read(prepared["contributions"]["embedding_replay"])
    phase_rows = read(main_artifacts["classifier_input_artifacts"]["phase_records"])
    phase = next((r for r in phase_rows if r["id"] == replay["phase_record"]), None)
    require(phase is not None and raw(phase)["artifact"] == replay["phase_artifact"], "embedding_phase_binding")
    source_records = {r["id"]: r for r in owners[oid]["records"]}
    amendments = {r["id"]: raw(source_records[r["id"]]) for r in snapshot["source_bindings"]["amendments"]}
    desired = {"method": METHOD, "policy": POLICY, "implementation": implementation(),
        "closure_record": closure_record, "root_resolution_record": resolved["resolution_record"],
        "inherited_projection_artifact": resolved["projection_artifact"], "lifecycle_record": lifecycle_record,
        "supplement_record": supplement_record, "supplement_artifact": digest(retained),
        "lifecycle_artifact": digest(life["payload"]), "task_census_record": task_id, "task_census_artifact": digest(census),
        "main_owner_sha256": oid, "source_head": owners[oid]["scope"]["source_head"],
        "main_classifier_manifest": digest(manifest), "input_index_digest": index.digest,
        "tokenizer_record": main_artifacts["tokenizer_record"], "embedding_replay": prepared["contributions"]["embedding_replay"]}
    old, done = engine._one(INTENT, optional=True), engine._one(RESULT, optional=True)
    require(old is None or same(old["payload"], desired), "changed_binding_requires_amendment")
    require(done is None or old is not None, "result_without_intent")
    if done is None and not create:
        return {"method": METHOD, **POLICY, "resolved": False}
    intent = old["id"] if old else engine.ledger.record(session, INTENT, METHOD, desired)
    registration = {"method": METHOD, "intent_record": intent, "binding": desired}
    protocol = done["payload"]["protocol_record"] if done else engine._version_once(session, context, "protocol", METHOD, registration)
    require(same(engine.ledger.get(protocol, "protocol")["content"], registration), "registered_protocol")
    def permitted_read(ref):
        if ref not in allowed:
            raise KeyError(ref)
        return read(ref)
    derived, proof = _derive(oid, owners[oid], main[oid], manifest, base, permitted_read,
        documents=documents, count_tokens=counter.count, embedding_phase=phase, amendments=amendments)
    result = {"method": METHOD, **POLICY, "intent_record": intent, "protocol_record": protocol, "binding": desired,
        "projection_artifact": digest(derived), "metadata_evidence_artifact": digest(proof)}
    if done:
        require(same(done["payload"], result), "completed_projection_changed")
        read(result["projection_artifact"])
        read(result["metadata_evidence_artifact"])
        identity = done["id"]
    else:
        engine.ledger.artifacts.put(derived)
        engine.ledger.artifacts.put(proof)
        require(implementation() == desired["implementation"], "implementation_changed")
        identity = engine.ledger.record(session, RESULT, intent, result)
    return {"method": METHOD, **POLICY, "resolved": True, "metadata_resolution_record": identity,
        "projection_artifact": result["projection_artifact"], "metadata_evidence_artifact": result["metadata_evidence_artifact"],
        "root_resolution_record": resolved["resolution_record"], "closure_record": closure_record,
        "scoped_complete": derived["scoped_certificate"]["complete"], "global_gap": derived["scoped_certificate"]["global_gap"],
        "counts": derived["counts"], "discharged_metadata_gaps": len(proof["discharged_metadata_gaps"])}


class MainMetadataParent(roots.RootResolutionParent):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        data = payload or {}
        require(operation == "status" and not versions and set(data) == {"action", "closure_record", "lifecycle_record", "supplement_record"}
            and data["action"] in {"resolve", "status"}, "offline_operation")
        for key in ("closure_record", "lifecycle_record", "supplement_record"):
            roots.closure.lookup.history.sha(data[key])
        return Research.execute(self, "status", {"method": METHOD, **data}, objective=objective, actor=actor)

    @audited_handler
    def _status(self, session, context, data):
        require(data["method"] == METHOD, "method")
        return resolve_completed_metadata(self, session, context, data["closure_record"], data["lifecycle_record"],
            data["supplement_record"], create=data["action"] == "resolve")
