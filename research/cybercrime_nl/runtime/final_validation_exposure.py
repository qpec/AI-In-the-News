"""Pure retained-artifact reconstruction of candidate exposure; no I/O or models.

This verifies a SUPPLIED one-owner census, not its completeness against a ledger.
The future registered Source caller must check the full chain/fresh cutoff, select
every relevant intended/response/revalidation row, and establish production/reuse
roles from immutable phase evidence. Generic phase='assignment' is NOT a role.
Unclassified roles, absent packets and missing historical memberships stay unknown.
No semantic parser is called and no original status, reservation or label changes.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re

import dossier_contract as legacy
import dossier_contract_v5 as cards
import final_validation_projection as projection
from newsresearch.common import ResearchError, canonical, digest

VERSION = "final-validation-retained-exposure-v1"
RECORD_KINDS = {"cyber_dossier_response", "cyber_dossier_seed_revalidation"}
NONPAIR_PHASES = {"embeddings", "audit", "summary", "summary_faithfulness", "summary_quality",
                  "summary_quality_audit", "card_quality", "card_quality_audit", "assignment_full_member_control"}


def _require(condition, code):
    if not condition:
        raise ValueError("exposure_" + code)


def _sha(value):
    _require(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None, "sha256_required")


def _ids(values):
    _require(isinstance(values, list) and all(isinstance(v, str) and v for v in values)
             and len(values) == len(set(values)), "identity_list_required")
    return set(values)


def _json(raw):
    try:
        value = json.loads(raw)
        _require(canonical(value).encode() == raw, "noncanonical_json")
        return value
    except (TypeError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("exposure_canonical_json_required") from error


class _Artifacts:
    def __init__(self, values):
        _require(isinstance(values, Mapping), "artifact_map_required")
        self.values, self.checked = values, set()

    def get(self, identity, *, optional=False):
        _sha(identity)
        raw = self.values.get(identity)
        if raw is None and optional:
            return None
        _require(type(raw) is bytes, "artifact_unavailable")
        _require(hashlib.sha256(raw).hexdigest() == identity, "artifact_digest_mismatch")
        value = _json(raw)
        self.checked.add(identity)
        return value


def _event(row, cutoff):
    fields = {"seq", "event_id", "session_id", "kind", "time", "payload", "previous_hash", "event_hash"}
    _require(isinstance(row, dict) and set(row) == fields and type(row["seq"]) is int
             and 0 < row["seq"] <= cutoff, "event_fields_or_cutoff")
    _sha(row["event_hash"])
    _sha(row["previous_hash"])
    _require(isinstance(row["payload"], str), "event_payload_required")
    payload = _json(row["payload"].encode())
    value = {key: row[key] for key in fields - {"event_hash", "payload"}}
    value["payload"] = payload
    _require(digest(value) == row["event_hash"], "event_digest_mismatch")
    return payload


def _record(row, events, store):
    fields = {"id", "kind", "logical_key", "payload", "artifact", "supersedes", "created_event"}
    _require(isinstance(row, dict) and set(row) == fields and row["kind"] in RECORD_KINDS,
             "record_fields")
    value = store.get(row["artifact"])
    _require(isinstance(row["payload"], str) and canonical(value) == row["payload"], "record_payload_mismatch")
    _require(row["id"] == digest({"kind": row["kind"], "key": row["logical_key"],
        "payload": row["artifact"], "supersedes": row["supersedes"]}), "record_identity_mismatch")
    _require(row["supersedes"] is None, "superseded_attempt_record_unsupported")
    event = events.get(row["created_event"])
    _require(event is not None and event[0]["kind"] == "record.created" and event[1] == {
        "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "record_creation_binding")
    _require(isinstance(value, dict), "record_payload_object_required")
    return value


def _documents(index, values):
    _require(isinstance(values, list) and bool(values), "documents_required")
    known = {item.document_id: item.input_sha256 for item in index.inputs}
    result, seen = [], set()
    for value in values:
        _require(isinstance(value, dict), "document_required")
        identity, title, body = (value.get(k) for k in ("document_id", "title", "body"))
        _require(identity in known and identity not in seen and isinstance(title, str)
                 and isinstance(body, str), "document_identity_or_type")
        _require(digest({"title": title, "body": body}) == known[identity], "full_input_digest_mismatch")
        result.append({"document_id": identity, "title": title, "body": body})
        seen.add(identity)
    return result


def _compare(packet, expected, keys):
    _require(all(packet.get(k) == expected.get(k) for k in keys), "packet_content_binding")


def _summary_members(view, summary_catalog, store):
    """Resolve exact historical summary; absent locator is explicitly unknown.

    Catalog values are {artifact, path}, where path traverses a retained JSON
    container to the full original summary (not its citation-free wire view).
    Locator provenance/completeness must be established by the Source caller.
    """
    locator = summary_catalog.get(view["summary_version"])
    if locator is None:
        return None
    _require(isinstance(locator, dict) and set(locator) == {"artifact", "path"}
             and isinstance(locator["path"], list), "summary_locator_fields")
    value = store.get(locator["artifact"], optional=True)
    if value is None:
        return None
    try:
        for step in locator["path"]:
            _require(isinstance(step, str) or type(step) is int, "summary_locator_step")
            value = value[step]
        _require(digest(value) == view["summary_version"] and value["dossier_id"] == view["dossier_id"]
                 and value["membership_revision"] == view["membership_revision"]
                 and legacy.summary_matching_view(value) == view["summary"], "historical_summary_binding")
        return value["source_document_ids"]
    except (KeyError, IndexError, TypeError, ResearchError) as error:
        raise ValueError("exposure_historical_summary_binding") from error


def _legacy_assignment(packet, docs, summary_catalog, store):
    supplied = _json(packet["request"]["input"].encode())
    _require(set(supplied) == {"article", "candidate_summaries"} and supplied["article"] == docs[0]
             and len(docs) == 1, "assignment_wire_article_binding")
    views = supplied["candidate_summaries"]
    _require(isinstance(views, list) and 1 <= len(views) <= 20, "summary_candidate_count")
    mapping = {"clarity_0": {"kind": "clarity", "document_id": docs[0]["document_id"]}}
    questions = [legacy._question("clarity_0", f"ARTICLE {docs[0]['document_id']}.\n" + legacy.CLARITY_RULES,
                                 legacy.CLARITY_LABELS, legacy.CLARITY_DESCRIPTIONS)]
    bindings, candidates = {}, []
    for n, view in enumerate(views):
        _require(isinstance(view, dict) and set(view) == {
            "dossier_id", "summary_version", "membership_revision", "summary"}, "summary_view_fields")
        identity = view["dossier_id"]
        _require(isinstance(identity, str) and identity and identity not in bindings, "summary_identity")
        for field in ("summary_version", "membership_revision"):
            _sha(view[field])
        binding = {key: view[key] for key in ("summary_version", "membership_revision")}
        bindings[identity] = binding
        name = f"dossier_{n}"
        questions.append(legacy._question(name, f"ARTICLE {docs[0]['document_id']} versus DOSSIER {identity}.\n"
            + legacy.PAIR_RULES, legacy.PAIR_LABELS, legacy.PAIR_DESCRIPTIONS))
        mapping[name] = {"kind": "assignment", "document_id": docs[0]["document_id"],
                         "dossier_id": identity, **binding}
        candidates.append({"dossier_id": identity, "membership_revision": view["membership_revision"],
            "version_field": "summary_version", "representation_version": view["summary_version"],
            "source_document_ids": _summary_members(view, summary_catalog, store)})
    request = {"model": legacy.MODEL, "input": canonical(supplied), "questions": questions,
               "prompt_cache_options": {"mode": "explicit"}}
    expected = legacy._finish("assignment", request, docs, mapping, bindings, lambda _: 0, 96_000)
    return expected, candidates


def packet_metadata(index, packet, request, *, packet_sha256, request_sha256, artifacts, summary_catalog=None):
    """Check full literal inputs, exact wire, questions and historical revisions.

    Supports original v1 seeds/summary assignments and v5 full-source/card packets
    inherited by v6-v10. Does not invoke Decisions parsing or reinterpret labels.
    Unsupported methods fail closed. Missing whole artifacts are handled by the
    outer reconstructor; missing old summary membership is explicitly localized.
    """
    store = artifacts if isinstance(artifacts, _Artifacts) else _Artifacts(artifacts)
    try:
        _require(isinstance(packet, dict) and isinstance(request, dict), "packet_objects")
        _require(digest(packet) == packet_sha256 and digest(request) == request_sha256
                 and packet["request"] == request and packet["request_sha256"] == request_sha256,
                 "packet_request_binding")
        _require(packet.get("kind", "decisions") == "decisions" and packet["phase"] in {"seed", "assignment"}
                 and packet["method"] in {legacy.METHOD, cards.METHOD}, "unsupported_pair_packet")
        docs = _documents(index, packet["documents"])
        candidates = []
        if packet["phase"] == "seed":
            pairs = [(packet["question_map"][q["name"]]["left"], packet["question_map"][q["name"]]["right"])
                     for q in request["questions"] if packet["question_map"][q["name"]]["kind"] == "pair"]
            builder = cards.seed_request if packet["method"] == cards.METHOD else legacy.seed_request
            expected = builder(docs, pairs=pairs, count_tokens=lambda _: 0, max_tokens=96_000)
        elif packet["method"] == cards.METHOD:
            for snapshot in packet["candidate_cards"]:
                _documents(index, snapshot["original_documents"])
                candidates.append({"dossier_id": snapshot["dossier_id"],
                    "membership_revision": snapshot["membership_revision"], "version_field": "card_version",
                    "representation_version": snapshot["card_version"],
                    "source_document_ids": snapshot["card"]["source_document_ids"]})
            expected = cards.assignment_request(docs[0], packet["candidate_cards"], count_tokens=lambda _: 0, max_tokens=96_000)
            _require(packet.get("diagnostic_control_only") is False, "diagnostic_not_production_pair")
        else:
            expected, candidates = _legacy_assignment(packet, docs, summary_catalog or {}, store)
        _compare(packet, expected, ("method", "phase", "request", "request_sha256", "documents", "document_ids",
                                  "question_map", "bindings", "wire_bytes"))
        if packet["method"] == cards.METHOD:
            _compare(packet, expected, ("kind", "focus_rules_sha256", "normalization"))
        value = {"packet_sha256": packet_sha256, "request_sha256": request_sha256, "phase": packet["phase"],
            "model": request["model"], "document_ids": packet["document_ids"],
            "question_names": [q["name"] for q in request["questions"]], "question_map": packet["question_map"],
            "candidate_memberships": candidates}
        projection.candidate_packet_metadata(index, value)
        return deepcopy(value)
    except (KeyError, TypeError, IndexError, ResearchError) as error:
        raise ValueError("exposure_packet_content_binding") from error


@dataclass(frozen=True)
class ReconstructedExposure:
    projection: projection.ExposureProjection
    observations: tuple[dict, ...]
    metadata: dict


def reconstruct_exposure(index, *, events, records, artifacts, inventory, summary_catalog=None):
    """Verify supplied rows/bytes then feed the existing source-free C primitive.

    inventory: source_id, source_head=[seq,hash], plan, amendments, input_index_digest,
    intended_event_hashes, response_record_ids, derived_record_ids, complete, gaps,
    role_artifact, evidence_sha256. The role artifact binds the same source/head/
    plan/index and has attempts=[{attempt,roles,evidence_ids,affected_document_ids}].
    roles=None means unclassified, NOT nonproduction. Evidence IDs are upstream
    verified phase/selection/reuse records, not a guess from phase or timestamp.
    An empty role list is forbidden. One physical attempt may have multiple roles.

    events include each intended event and each record.created event. Only these
    selected hashes are checked here, not omitted events/chain continuity. Missing
    expected rows fail closed; caller must instead register a bounded/global gap.
    artifacts may be a read-only/lazy Mapping: no full corpus byte materialization
    or parsed-artifact cache is required here. Any reads supplied by a mapping
    remain the audited caller's responsibility; this module opens nothing.
    All returned data exclude article text, provider prose, labels and probabilities.
    """
    fields = {"source_id", "source_head", "plan", "amendments", "input_index_digest", "intended_event_hashes",
              "response_record_ids", "derived_record_ids", "complete", "gaps", "role_artifact", "evidence_sha256"}
    _require(isinstance(inventory, dict) and set(inventory) == fields, "inventory_fields")
    _require(isinstance(inventory["source_id"], str) and bool(inventory["source_id"]), "source_id")
    head = inventory["source_head"]
    _require(isinstance(head, list) and len(head) == 2 and type(head[0]) is int and head[0] > 0, "source_head")
    for value in (head[1], inventory["plan"], inventory["role_artifact"], inventory["evidence_sha256"]):
        _sha(value)
    _require(inventory["input_index_digest"] == index.digest and type(inventory["complete"]) is bool,
             "inventory_index_or_completeness")
    _require(dict(index.bindings)["source_head"] == digest(head), "index_source_cutoff_binding")
    allowed = _ids(inventory["amendments"])
    for value in allowed:
        _sha(value)
    store = _Artifacts(artifacts)
    selected, intended = {}, {}
    for row in events:
        value = _event(row, head[0])
        _require(row["seq"] not in selected, "duplicate_event")
        _require(row["kind"] in {"model.attempt.intended", "record.created"}, "unexpected_event_kind")
        selected[row["seq"]] = (row, value)
        if row["kind"] == "model.attempt.intended":
            _require(isinstance(value, dict) and value.get("attempt") not in intended, "duplicate_physical_intent")
            intended[value["attempt"]] = (row, value)
    _require({row["event_hash"] for row, _ in intended.values()} == _ids(inventory["intended_event_hashes"]),
             "intended_census_mismatch")
    responses, derived, response_ids, derived_ids, used_creation = {}, [], set(), set(), set()
    for row in records:
        value = _record(row, selected, store)
        _require(row["created_event"] not in used_creation, "duplicate_record_creation")
        used_creation.add(row["created_event"])
        if row["kind"] == "cyber_dossier_response":
            _require(value.get("attempt") not in responses and row["logical_key"] == value.get("task_key"),
                     "duplicate_response_or_task_binding")
            responses[value["attempt"]] = (row, value)
            response_ids.add(row["id"])
        else:
            derived.append((row, value))
            derived_ids.add(row["id"])
    _require(response_ids == _ids(inventory["response_record_ids"])
             and derived_ids == _ids(inventory["derived_record_ids"]), "record_census_mismatch")
    _require(set(responses) <= set(intended), "response_without_intent")
    _require(used_creation == {seq for seq, (row, _) in selected.items() if row["kind"] == "record.created"},
             "unconsumed_creation_event")
    role = store.get(inventory["role_artifact"])
    binding_fields = ("source_id", "source_head", "plan", "input_index_digest")
    _require(isinstance(role, dict) and set(role) == {*binding_fields, "attempts"}
             and all(role[k] == inventory[k] for k in binding_fields), "role_scope_binding")
    roles = {}
    known = {item.document_id for item in index.inputs}
    for item in role["attempts"]:
        _require(isinstance(item, dict) and set(item) == {"attempt", "roles", "evidence_ids", "affected_document_ids"}
                 and item["attempt"] in intended and item["attempt"] not in roles, "role_attempt_binding")
        evidence = _ids(item["evidence_ids"])
        _require(bool(evidence), "role_evidence_required")
        for value in evidence:
            _sha(value)
        if item["roles"] is not None:
            _require(bool(_ids(item["roles"])) and set(item["roles"]) <= projection.ROLES, "role_values")
        if item["affected_document_ids"] is not None:
            _require(bool(_ids(item["affected_document_ids"])) and set(item["affected_document_ids"]) <= known,
                     "affected_documents")
        roles[item["attempt"]] = item
    _require(set(roles) == set(intended), "role_census_mismatch")
    gaps, observations, original_responses = deepcopy(inventory["gaps"]), [], {}
    derived_views, missing_artifacts, unclassified, ignored = [], 0, 0, 0
    scope_ids = {attempt: digest([inventory["source_id"], attempt]) for attempt in intended}
    for attempt, (_, intent) in intended.items():
        _require(isinstance(attempt, str) and bool(attempt) and intent.get("batch") == inventory["plan"]
                 and intent.get("execution_amendment") in {None, *allowed}
                 and type(intent.get("number")) is int and intent["number"] == 1, "intent_plan_or_amendment")
        for key in ("task_key", "packet", "request", "dispatch"):
            _sha(intent.get(key))
        _require(isinstance(intent.get("phase"), str), "intent_phase")
        response_row = responses.get(attempt)
        envelope, response = None, None
        if response_row is not None:
            raw_row, response = response_row
            _require(response.get("plan") == inventory["plan"]
                     and response.get("execution_amendment") == intent.get("execution_amendment")
                     and all(response.get(k) == intent.get(k) for k in ("attempt", "task_key", "phase", "packet", "request", "category")),
                     "response_intent_binding")
            envelope = store.get(response["response"], optional=True)
            original_responses[attempt] = (raw_row, response)
            if envelope is None:
                missing_artifacts += 1
            elif isinstance(envelope, dict):
                raw = envelope.get("raw_response")
                raw_status = raw.get("http_status") if isinstance(raw, dict) else None
                _require(response.get("http_status") == raw_status, "response_status_binding")
            else:
                raise ValueError("exposure_envelope_object_required")
        request, packet, dispatch = (store.get(intent[k], optional=True) for k in ("request", "packet", "dispatch"))
        _require(intent["phase"] in projection.PAIR_PHASES | NONPAIR_PHASES, "unrecognized_intent_phase")
        if packet is not None:
            _require(isinstance(packet, dict) and packet.get("phase") == intent["phase"]
                     and (packet.get("request_sha256") == intent["request"] or (
                         packet.get("phase") == "embeddings" and packet.get("kind") == "embeddings"
                         and "request_sha256" not in packet and isinstance(packet.get("request"), dict)
                         and digest(packet["request"]) == intent["request"])), "packet_intent_binding")
            if request is not None:
                _require(packet.get("request") == request, "packet_request_binding")
        if intent["phase"] not in projection.PAIR_PHASES:
            # The caller must have established phase semantics against the frozen
            # producer code. Missing packet/dispatch cannot certify that exclusion.
            if request is None or packet is None or dispatch is None:
                gaps.append({"reason_code": "nonpair_attempt_metadata_missing",
                             "document_ids": roles[attempt]["affected_document_ids"]})
            else:
                kind = packet.get("kind")
                _require(kind in {"decisions", "responses", "embeddings"}
                         and intent["task_key"] == digest([inventory["plan"], kind, request])
                         and dispatch.get("wire_sha256") == intent["request"]
                         and dispatch.get("client_id") == attempt and dispatch.get("kind") == kind,
                         "nonpair_dispatch_binding")
            ignored += 1
            continue
        metadata = None
        if request is not None:
            _require(isinstance(request, dict) and intent["task_key"] == digest([inventory["plan"], "decisions", request]),
                     "task_request_binding")
        if dispatch is not None:
            expected = {"transport": "openai-dossier-http-v1", "kind": "decisions", "url": "https://api.openai.com/v1/decisions",
                "method": "POST", "wire_sha256": intent["request"], "client_id": attempt, "automatic_retries": 0,
                "timeout_seconds": 120, "max_response_bytes": 16_777_216}
            _require(dispatch == expected, "dispatch_request_binding")
        if packet is not None and request is not None and dispatch is not None:
            metadata = packet_metadata(index, packet, request, packet_sha256=intent["packet"], request_sha256=intent["request"],
                                       artifacts=store, summary_catalog=summary_catalog)
        else:
            missing_artifacts += 1
        item = roles[attempt]
        if item["roles"] is None:
            unclassified += 1
            # Even known packet relations cannot prove its role; conservative
            # endpoint/global region deliberately overcovers possible exposure.
            is_none = (isinstance(envelope, dict) and isinstance(envelope.get("raw_response"), dict)
                       and envelope["raw_response"].get("dispatch_started") is False)
            if is_none:
                _require(envelope.get("payload") is None and envelope["raw_response"].get("http_status") is None,
                         "predispatch_response_contradiction")
            else:
                gaps.append({"reason_code": "unclassified_attempt_role", "document_ids":
                             metadata["document_ids"] if metadata is not None else item["affected_document_ids"]})
            continue
        # Separate owner-scoped projection identity; original rows remain bound
        # by their hashes and are never edited or written back.
        normalized_intent = {**intent, "attempt": scope_ids[attempt]}
        normalized_response = None if response is None else {**response, "attempt": scope_ids[attempt]}
        observations.append({"intent": normalized_intent, "packet_metadata": metadata,
            "response_record": normalized_response, "response_envelope": envelope, "roles": item["roles"],
            "role_binding": digest([inventory["role_artifact"], item]), "affected_document_ids": item["affected_document_ids"]})
    for row, value in derived:
        attempt = value.get("source_attempt")
        _require(attempt in original_responses and attempt in scope_ids, "derived_original_missing")
        raw_row, original = original_responses[attempt]
        _require(row["logical_key"] == raw_row["id"] and value.get("source_response_record") == raw_row["id"]
                 and value.get("source_response_record_sha256") == digest({**original, "_record_id": raw_row["id"]})
                 and value.get("parent_plan") == inventory["plan"] and value.get("parent_execution_amendment") in allowed
                 and value.get("task_key") == original["task_key"] and value.get("status") == "valid"
                 and value.get("normalization_version") == "seed-question-map-in-retained-request-list-order-v1"
                 and value.get("canonical_packet_sha256") == original["packet"]
                 and value.get("request_sha256") == original["request"]
                 and value.get("source_validation_error") == original.get("validation_error")
                 and value.get("original_rows_unchanged") is True
                 and type(value.get("model_calls")) is int and value["model_calls"] == 0
                 and type(value.get("cost_nanousd")) is int and value["cost_nanousd"] == 0
                 and all(value.get("source_" + k) == original[k] for k in ("packet", "request", "response")),
                 "derived_original_binding")
        store.get(value["parsed"])
        if roles[attempt]["roles"] is not None and intended[attempt][1]["phase"] in projection.PAIR_PHASES:
            derived_views.append({**value, "source_attempt": scope_ids[attempt]})
    certificate = {"complete": inventory["complete"], "production_pair_attempt_ids": [
        item["intent"]["attempt"] for item in observations if "production" in item["roles"]],
        "gaps": gaps, "evidence_sha256": digest(inventory)}
    projected = projection.project_attempt_exposure(index, observations, inventory_certificate=certificate,
                                                  derived_revalidations=derived_views)
    # Observation envelopes are necessary internally, but not an output: raw
    # provider prose/labels/probabilities are never projected to console/results.
    safe_observations = tuple({"physical_attempt": item["intent"]["attempt"],
        "task_key": item["intent"]["task_key"], "packet_metadata": item["packet_metadata"],
        "roles": item["roles"], "role_binding": item["role_binding"],
        "response_artifact": None if item["response_record"] is None else item["response_record"]["response"]}
        for item in observations)
    metadata = {"version": VERSION, "source_id": inventory["source_id"], "source_head": head,
        "input_index_digest": index.digest, "inventory_sha256": digest(inventory),
        "role_artifact": inventory["role_artifact"], "checked_artifacts": sorted(store.checked),
        "physical_intents": len(intended), "response_records": len(responses),
        "orphan_intents": len(set(intended) - set(responses)), "derived_records": len(derived),
        "unclassified_pair_attempts": unclassified, "ignored_nonpair_attempts": ignored,
        "missing_artifact_cases": missing_artifacts, "new_exposures_from_revalidation": 0,
        "source_inventory_completeness_verified": False, "source_role_evidence_verified": False,
        "requires_audited_source_snapshot_and_inventory": True, "prior_exposure_reconstruction_included": False,
        "semantic_labels_reclassified": False}
    return ReconstructedExposure(projected, safe_observations, metadata)
