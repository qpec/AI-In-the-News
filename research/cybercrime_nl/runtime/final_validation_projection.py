"""Pure metadata projections; no source-owner/file/model access or registration.

The audited Source adapter is still required to verify original record bytes,
final report/phase lineage, normalized packet fidelity, historical member lookup,
production/reuse roles and inventory completeness. These primitives check their
supplied bindings but cannot certify that an omitted record never existed.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from final_validation_design import pair_count, pair_from_rank, pair_rank
from final_validation_frame import InputIndex, build_input_index

VERSION = "final-validation-projection-primitives-v1"
PAIR_PHASES = {"seed", "assignment"}
ROLES = {"production", "development", "diagnostic", "reference"}
PRIOR_ROLES = {"development", "diagnostic", "reference", "substantive_review"}
PRIOR_SCOPE = "Recorded prior-study owners and substantive source reviews; not unrecorded reading or model pretraining."


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("projection_identity_required")


def _sha(value):
    if not isinstance(value, str) or re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("projection_sha256_required")


def _identities(values, *, allow_empty=False):
    if not isinstance(values, list) or (not values and not allow_empty):
        raise ValueError("projection_identity_list_required")
    for value in values:
        _text(value)
    if len(values) != len(set(values)):
        raise ValueError("projection_duplicate_identity")
    return set(values)


def project_final_membership(document_rows: list[dict], article_rows: list[dict], outcome: dict, *,
                             expected_documents: int, expected_articles: int,
                             frame_bindings: dict, artifact_bindings: dict) -> InputIndex:
    """Project retained preparation metadata and a bound final outcome to inputs.

    document_rows/articles are the original preparation artifacts; extra retained
    metadata is hashed but never copied to the returned source-free index. Only
    outcome.card_supported_group_ids establishes A. Every other input receives
    explicit None (a separate singleton downstream), including provisional groups.
    Final completion/report and source-text fidelity require upstream verification.
    """
    for value in (expected_documents, expected_articles):
        if type(value) is not int or value < 0:
            raise ValueError("projection_expected_frame_required")
    if not isinstance(document_rows, list) or not isinstance(article_rows, list) or not isinstance(outcome, dict):
        raise ValueError("projection_payloads_required")
    if len(document_rows) != expected_documents or len(article_rows) != expected_articles:
        raise ValueError("projection_frame_count_mismatch")
    if set(artifact_bindings) != {"documents_artifact", "articles_artifact", "outcome_artifact"}:
        raise ValueError("projection_artifact_bindings_required")
    for key, value in zip(("documents_artifact", "articles_artifact", "outcome_artifact"),
                          (document_rows, article_rows, outcome), strict=True):
        _sha(artifact_bindings[key])
        if digest(value) != artifact_bindings[key]:
            raise ValueError("projection_artifact_digest_mismatch")
    documents = {}
    for row in document_rows:
        for key in ("document_id", "canonical_custom_id", "input_sha256", "screening_request_hash", "document_artifact"):
            if key not in row:
                raise ValueError("projection_document_metadata_missing")
        identity = row["document_id"]
        _text(identity)
        _text(row["canonical_custom_id"])
        for key in ("input_sha256", "screening_request_hash", "document_artifact"):
            _sha(row[key])
        if identity in documents:
            raise ValueError("projection_duplicate_document")
        documents[identity] = row
    aliases = {identity: [] for identity in documents}
    by_article = {}
    for row in article_rows:
        identity, alias = row.get("document_id"), row.get("custom_id")
        _text(alias)
        if identity not in documents or alias in by_article:
            raise ValueError("projection_alias_outside_or_duplicate")
        document = documents[identity]
        if (row.get("canonical_custom_id") != document["canonical_custom_id"]
                or row.get("request_hash") != document["screening_request_hash"]
                or row.get("screening_route") != "keep"
                or type(row.get("exact_input_reuse")) is not bool
                or row["exact_input_reuse"] != (alias != row["canonical_custom_id"])):
            raise ValueError("projection_alias_binding_mismatch")
        aliases[identity].append(alias)
        by_article[alias] = row
    for identity, document in documents.items():
        canonical = by_article.get(document["canonical_custom_id"])
        if canonical is None or canonical["document_id"] != identity or canonical["exact_input_reuse"]:
            raise ValueError("projection_missing_canonical_article")
    groups = outcome.get("groups")
    if not isinstance(groups, dict) or "card_supported_group_ids" not in outcome:
        raise ValueError("projection_final_acceptance_missing")
    accepted = _identities(outcome["card_supported_group_ids"], allow_empty=True)
    if not accepted <= set(groups):
        raise ValueError("projection_accepted_group_missing")
    membership = dict.fromkeys(documents)
    seen = set()
    group_states = outcome.get("group_states", {})
    if not isinstance(group_states, dict):
        raise ValueError("projection_group_states_invalid")
    for dossier, members in groups.items():
        _text(dossier)
        identifiers = _identities(members)
        if not identifiers <= set(documents) or seen.intersection(identifiers):
            raise ValueError("projection_overlapping_or_outside_membership")
        seen.update(identifiers)
        if dossier in accepted:
            if dossier in group_states:
                raise ValueError("projection_acceptance_state_conflict")
            for identity in identifiers:
                membership[identity] = dossier
    manifest = [{"document_id": identity, "input_sha256": row["input_sha256"],
                 "article_row_ids": aliases[identity]} for identity, row in documents.items()]
    return build_input_index(manifest, membership, bindings=frame_bindings)


def candidate_packet_metadata(index: InputIndex, packet: dict) -> dict:
    """Validate a SOURCE-FREE normalized view, not an original packet replacement.

    Required fields: packet_sha256/request_sha256, phase, model, document_ids,
    question_names, question_map, candidate_memberships. The upstream adapter must
    compare these with the exact original request/packet. Question-map values keep
    original document IDs. Each candidate includes dossier_id, membership_revision,
    version_field (card_version/summary_version), representation_version, and exact
    source_document_ids, or explicit None when historical members are unavailable.
    Never substitute the final dossier's members for an older offered revision.
    """
    fields = {"packet_sha256", "request_sha256", "phase", "model", "document_ids",
              "question_names", "question_map", "candidate_memberships"}
    if not isinstance(packet, dict) or set(packet) != fields or packet["phase"] not in PAIR_PHASES:
        raise ValueError("projection_supported_packet_metadata_required")
    for key in ("packet_sha256", "request_sha256"):
        _sha(packet[key])
    if packet["model"] != "gpt-6-luna":
        raise ValueError("projection_unexpected_request_model")
    known = {document.document_id: i for i, document in enumerate(index.inputs)}
    ids = _identities(packet["document_ids"])
    names = _identities(packet["question_names"])
    mapping = packet["question_map"]
    if not ids <= set(known) or not isinstance(mapping, dict) or set(mapping) != names:
        raise ValueError("projection_question_or_document_binding")
    if not isinstance(packet["candidate_memberships"], list):
        raise ValueError("projection_candidate_memberships_required")
    candidates = {}
    for candidate in packet["candidate_memberships"]:
        if set(candidate) != {"dossier_id", "membership_revision", "version_field", "representation_version", "source_document_ids"}:
            raise ValueError("projection_candidate_fields")
        dossier = candidate["dossier_id"]
        _text(dossier)
        if dossier in candidates or candidate["version_field"] not in {"card_version", "summary_version"}:
            raise ValueError("projection_candidate_identity")
        for key in ("membership_revision", "representation_version"):
            _sha(candidate[key])
        members = candidate["source_document_ids"]
        if members is not None:
            member_ids = _identities(members)
            if not member_ids <= set(known) or digest(sorted(members)) != candidate["membership_revision"]:
                raise ValueError("projection_historical_membership_binding")
        candidates[dossier] = candidate
    pairs, unknown_endpoints, used_candidates, clarity = set(), set(), set(), set()

    def add_pair(left, right):
        if left not in known or right not in known or left == right:
            raise ValueError("projection_pair_endpoint_binding")
        a, b = sorted((known[left], known[right]))
        pairs.add(pair_rank(len(known), a, b))

    for metadata in mapping.values():
        if not isinstance(metadata, dict):
            raise ValueError("projection_question_metadata")
        kind = metadata.get("kind")
        if kind == "clarity":
            identifier = metadata.get("document_id")
            if identifier not in ids or identifier in clarity:
                raise ValueError("projection_clarity_binding")
            clarity.add(identifier)
        elif kind == "pair" and packet["phase"] == "seed":
            if metadata.get("left") not in ids or metadata.get("right") not in ids:
                raise ValueError("projection_seed_pair_outside_packet")
            add_pair(metadata["left"], metadata["right"])
        elif kind == "assignment" and packet["phase"] == "assignment":
            query, dossier = metadata.get("document_id"), metadata.get("dossier_id")
            if len(ids) != 1 or query not in ids or dossier not in candidates or dossier in used_candidates:
                raise ValueError("projection_assignment_binding")
            candidate = candidates[dossier]
            if (metadata.get("membership_revision") != candidate["membership_revision"]
                    or metadata.get(candidate["version_field"]) != candidate["representation_version"]):
                raise ValueError("projection_offered_revision_mismatch")
            used_candidates.add(dossier)
            if candidate["source_document_ids"] is None:
                unknown_endpoints.add(known[query])
            else:
                for member in candidate["source_document_ids"]:
                    add_pair(query, member)
        else:
            raise ValueError("projection_unexpected_question_kind")
    if clarity != ids or used_candidates != set(candidates) or (packet["phase"] == "seed" and candidates):
        raise ValueError("projection_incomplete_packet_metadata")
    return {"pair_ranks": sorted(pairs), "unknown_endpoint_indices": sorted(unknown_endpoints),
            "packet_metadata_sha256": digest(packet)}


def acknowledged_decision_envelope(packet: dict, envelope: dict | None) -> tuple[str, str]:
    """Acknowledged request exposure, never model attention or correct judgment.

    A successful expected-model serving envelope has every named question with a
    choice/refusal type. Invalid probabilities/labels or billing holds do not undo
    exposure. Partial/malformed envelopes may be actual exposure but stay unknown.
    """
    if envelope is None:
        return "unknown", "unreturned_or_unavailable_envelope"
    if not isinstance(envelope, dict):
        raise ValueError("projection_provider_envelope_type")
    raw, payload = envelope.get("raw_response"), envelope.get("payload")
    raw = raw if isinstance(raw, dict) else {}
    status = raw.get("http_status")
    started = raw.get("dispatch_started")
    answers = payload.get("answers") if isinstance(payload, dict) else None
    names = packet["question_names"]
    serving = (type(status) is int and 200 <= status < 300 and isinstance(payload, dict)
        and payload.get("error") is None
        and payload.get("model") == packet["model"]
        and envelope.get("model") in (None, packet["model"])
        and isinstance(answers, list) and len(answers) == len(names) and bool(answers)
        and all(isinstance(answer, dict) and isinstance(answer.get("name"), str)
                and answer.get("type") in {"choice", "refusal"} for answer in answers)
        and {answer["name"] for answer in answers} == set(names))
    if started is False:
        if payload is not None or status is not None:
            raise ValueError("projection_predispatch_response_contradiction")
        return "unexposed", "explicit_predispatch_failure"
    if serving:
        return "exposed", "acknowledged_expected_decisions_envelope"
    return "unknown", "transmission_or_serving_envelope_uncertain"


@dataclass(frozen=True)
class ExposureProjection:
    document_ids: tuple[str, ...]
    confirmed_pairs: frozenset[int]
    uncertain_pairs: frozenset[int]
    unknown_endpoints: frozenset[int]
    global_unknown: bool
    metadata: dict

    def state(self, rank: int) -> str:
        left, right = pair_from_rank(len(self.document_ids), rank)
        if rank in self.confirmed_pairs:
            return "exposed"
        if (self.global_unknown or rank in self.uncertain_pairs
                or left in self.unknown_endpoints or right in self.unknown_endpoints):
            return "unknown"
        return "unexposed"

    def states(self):
        for rank in range(pair_count(len(self.document_ids))):
            yield rank, self.state(rank)


def project_attempt_exposure(index: InputIndex, observations: list[dict], *,
                             inventory_certificate: dict, derived_revalidations: list[dict] | None = None) -> ExposureProjection:
    """Deduplicate physical attempts and project production candidate exposure.

    Observation fields: intent (original attempt/task/packet/request/phase metadata),
    packet_metadata (normalized view above, or None), response_record (original
    metadata or None), response_envelope (retained ProviderResponse or None), roles,
    role_binding, affected_document_ids (None=unlocalized, used for missing packet).
    Multiple identical views of one physical attempt can add roles, not exposures.

    Inventory certificate: complete, production_pair_attempt_ids, gaps, evidence_sha256.
    complete is an upstream AUDITED claim, not a fact proved here. Gaps contain
    reason_code and document_ids (None means global). Incomplete reconciliation
    always makes the residual universe unknown. Complete reconciliation can still
    contain bounded gaps. This function never releases holds or rewrites statuses.
    """
    certificate = inventory_certificate
    if (not isinstance(certificate, dict) or set(certificate) != {
            "complete", "production_pair_attempt_ids", "gaps", "evidence_sha256"}
            or type(certificate["complete"]) is not bool or not isinstance(certificate["gaps"], list)):
        raise ValueError("projection_inventory_certificate_required")
    _sha(certificate["evidence_sha256"])
    expected = _identities(certificate["production_pair_attempt_ids"], allow_empty=True)
    known = {document.document_id: i for i, document in enumerate(index.inputs)}
    confirmed, uncertain, endpoints = set(), set(), set()
    global_unknown = not certificate["complete"]

    def widen(ids):
        nonlocal global_unknown
        if ids is None:
            global_unknown = True
        else:
            identifiers = _identities(ids)
            if not identifiers <= set(known):
                raise ValueError("projection_unknown_scope_outside_frame")
            endpoints.update(known[identifier] for identifier in identifiers)

    for gap in certificate["gaps"]:
        if (not isinstance(gap, dict) or set(gap) != {"reason_code", "document_ids"}
                or not isinstance(gap["reason_code"], str) or re.fullmatch("[a-z][a-z0-9_]*", gap["reason_code"]) is None):
            raise ValueError("projection_inventory_gap")
        widen(gap["document_ids"])
    physical = {}
    for observed in observations:
        if not isinstance(observed, dict) or set(observed) != {
                "intent", "packet_metadata", "response_record", "response_envelope", "roles",
                "role_binding", "affected_document_ids"}:
            raise ValueError("projection_attempt_observation_fields")
        _sha(observed["role_binding"])
        roles = _identities(observed["roles"])
        if not roles <= ROLES:
            raise ValueError("projection_attempt_role")
        intent = observed["intent"]
        for key in ("attempt", "task_key", "packet", "request", "phase"):
            if key not in intent:
                raise ValueError("projection_intent_metadata_missing")
        for key in ("attempt", "task_key", "phase"):
            _text(intent[key])
        for key in ("packet", "request"):
            _sha(intent[key])
        core = {key: value for key, value in observed.items() if key not in {"roles", "role_binding"}}
        attempt = intent["attempt"]
        if attempt in physical:
            if physical[attempt]["core"] != core:
                raise ValueError("projection_conflicting_physical_attempt")
            physical[attempt]["roles"].update(roles)
            physical[attempt]["role_bindings"].add(observed["role_binding"])
        else:
            physical[attempt] = {"core": core, "roles": set(roles), "role_bindings": {observed["role_binding"]}}
    production_ids = {attempt for attempt, item in physical.items()
                      if "production" in item["roles"] and item["core"]["intent"]["phase"] in PAIR_PHASES}
    if production_ids != expected:
        raise ValueError("projection_production_attempt_inventory_mismatch")
    outcomes = []
    for attempt in sorted(production_ids):
        item = physical[attempt]
        observed, intent = item["core"], item["core"]["intent"]
        packet, record, envelope = observed["packet_metadata"], observed["response_record"], observed["response_envelope"]
        if record is not None:
            for key in ("attempt", "task_key", "packet", "request", "phase"):
                if record.get(key) != intent[key]:
                    raise ValueError("projection_response_intent_binding")
            _sha(record.get("response"))
            if envelope is not None and digest(envelope) != record["response"]:
                raise ValueError("projection_response_artifact_digest")
        elif envelope is not None:
            raise ValueError("projection_envelope_without_response_record")
        if packet is None:
            raw = envelope.get("raw_response") if isinstance(envelope, dict) else None
            if isinstance(raw, dict) and raw.get("dispatch_started") is False:
                if envelope.get("payload") is not None or raw.get("http_status") is not None:
                    raise ValueError("projection_predispatch_response_contradiction")
                state, reason = "unexposed", "explicit_predispatch_failure"
            else:
                widen(observed["affected_document_ids"])
                state, reason = "unknown", "packet_metadata_unavailable"
        else:
            if (packet.get("packet_sha256") != intent["packet"] or packet.get("request_sha256") != intent["request"]
                    or packet.get("phase") != intent["phase"]):
                raise ValueError("projection_packet_intent_binding")
            relations = candidate_packet_metadata(index, packet)
            state, reason = acknowledged_decision_envelope(packet, envelope)
            if state == "exposed":
                confirmed.update(relations["pair_ranks"])
            elif state == "unknown":
                uncertain.update(relations["pair_ranks"])
            if state != "unexposed":
                endpoints.update(relations["unknown_endpoint_indices"])
        outcomes.append({"attempt": attempt, "state": state, "reason": reason,
                         "roles": sorted(item["roles"]), "role_bindings": sorted(item["role_bindings"])})
    derived = derived_revalidations or []
    linked = set()
    for row in derived:
        attempt = row.get("source_attempt")
        if attempt not in physical or row.get("model_calls") != 0 or type(row.get("model_calls")) is not int:
            raise ValueError("projection_invalid_local_revalidation")
        original = physical[attempt]["core"]
        if (row.get("source_packet") != original["intent"]["packet"]
                or row.get("source_request") != original["intent"]["request"]
                or original["response_record"] is None
                or row.get("source_response") != original["response_record"]["response"]):
            raise ValueError("projection_revalidation_source_binding")
        linked.add(attempt)
    metadata = {"version": VERSION, "input_index_digest": index.digest,
        "inventory_certificate_sha256": digest(certificate), "physical_attempts": len(physical),
        "production_pair_attempts": len(production_ids), "observed_views": len(observations),
        "ignored_nonproduction_or_nonpair_attempts": len(physical) - len(production_ids),
        "locally_revalidated_physical_attempts": len(linked), "new_exposures_from_revalidation": 0,
        "attempt_exposure": outcomes, "requires_audited_source_inventory_and_normalization": True,
        "exposure_definition": "Acknowledged expected-model request envelope; not model attention, semantic validity or gold labels."}
    return ExposureProjection(tuple(known), frozenset(confirmed), frozenset(uncertain),
                              frozenset(endpoints), global_unknown, metadata)


@dataclass(frozen=True)
class PriorExposureProjection:
    document_ids: tuple[str, ...]
    confirmed_documents: frozenset[str]
    uncertain_documents: frozenset[str]
    global_unknown: bool
    metadata: dict

    def document_state(self, document_id: str) -> str:
        if document_id not in self.document_ids:
            raise ValueError("projection_prior_document_outside_frame")
        if document_id in self.confirmed_documents:
            return "exposed"
        if self.global_unknown or document_id in self.uncertain_documents:
            return "unknown"
        return "unexposed"

    def state(self, rank: int) -> str:
        left, right = pair_from_rank(len(self.document_ids), rank)
        endpoints = (self.document_ids[left], self.document_ids[right])
        if any(identity in self.confirmed_documents for identity in endpoints):
            return "exposed"
        if self.global_unknown or any(identity in self.uncertain_documents for identity in endpoints):
            return "unknown"
        return "unexposed"

    def states(self):
        for rank in range(pair_count(len(self.document_ids))):
            yield rank, self.state(rank)


def prior_event_identity(origin_source_id: str, event_id: str) -> str:
    """Owner/review-scoped physical identity; reused views retain the origin."""
    _text(origin_source_id)
    _text(event_id)
    return digest({"origin_source_id": origin_source_id, "event_id": event_id})


def project_prior_exposure(index: InputIndex, observations: list[dict], *, inventory_certificate: dict) -> PriorExposureProjection:
    """Project explicitly normalized prior study evidence, without certifying it.

    P is article-level: either endpoint's confirmed recorded prior exposure makes
    a pair exposed. Routine production and metadata-only roles do not qualify.
    All source/model/review evidence must be verified upstream BEFORE normalization;
    the hashes below bind that verification but do not perform it. An acknowledged
    provider response need not contain a valid judgment. Technical/local evidence
    alone is uncertain, never acknowledged. Prepared-only and proven predispatch
    records establish no exposure for that event, not globally absent exposure.

    Certificate fields: scope_statement=PRIOR_SCOPE, scope_complete, required_source_ids,
    study_inventory_sha256, cutoff_binding_sha256, input_index_digest, sources. The
    cutoff binding identifies the upstream verified pre-frame-freeze scope; actual
    record times/head coverage must be checked there. Each source supplies source_id, source_kind
    (owner/review), immutable_head_sha256, reconciliation (complete/incomplete),
    missing_document_ids ([] for complete; None for global missing), event_ids
    (prior_event_identity values),
    inventory_sha256. Required source scope is a separate audited cross-study claim;
    a main-owner candidate inventory alone cannot establish it. A complete source
    requires a head; an unavailable source can carry bounded or global missingness.

    Observations contain event_id, origin_source_id, source_id, record_sha256, roles, role_binding,
    task_binding={kind,document_ids,binding_sha256}, and
    evidence={state,kind,evidence_sha256}. The exact task binding is preserved only
    as reuse/contamination metadata: group exposure NEVER creates pair gold labels.
    """
    certificate = inventory_certificate
    if (not isinstance(certificate, dict) or set(certificate) != {
            "scope_statement", "scope_complete", "required_source_ids", "study_inventory_sha256",
            "cutoff_binding_sha256", "input_index_digest", "sources"}
            or certificate["scope_statement"] != PRIOR_SCOPE or type(certificate["scope_complete"]) is not bool
            or not isinstance(certificate["sources"], list)):
        raise ValueError("projection_prior_inventory_scope_required")
    _sha(certificate["study_inventory_sha256"])
    _sha(certificate["cutoff_binding_sha256"])
    if certificate["input_index_digest"] != index.digest:
        raise ValueError("projection_prior_input_index_binding")
    required_sources = _identities(certificate["required_source_ids"])
    known = {document.document_id for document in index.inputs}
    confirmed, uncertain = set(), set()
    global_unknown = not certificate["scope_complete"]

    def widen(document_ids):
        nonlocal global_unknown
        if document_ids is None:
            global_unknown = True
        else:
            identifiers = _identities(document_ids)
            if not identifiers <= known:
                raise ValueError("projection_prior_missing_region_outside_frame")
            uncertain.update(identifiers)

    sources, expected_events = {}, {}
    for source in certificate["sources"]:
        if not isinstance(source, dict) or set(source) != {
                "source_id", "source_kind", "immutable_head_sha256", "reconciliation",
                "missing_document_ids", "event_ids", "inventory_sha256"}:
            raise ValueError("projection_prior_source_fields")
        identity = source["source_id"]
        _text(identity)
        if identity in sources or source["source_kind"] not in {"owner", "review"}:
            raise ValueError("projection_prior_source_identity")
        _sha(source["inventory_sha256"])
        if source["immutable_head_sha256"] is not None:
            _sha(source["immutable_head_sha256"])
        if source["reconciliation"] == "complete":
            if source["immutable_head_sha256"] is None or source["missing_document_ids"] != []:
                raise ValueError("projection_prior_complete_source_binding")
        elif source["reconciliation"] == "incomplete":
            widen(source["missing_document_ids"])
        else:
            raise ValueError("projection_prior_reconciliation_state")
        expected_events[identity] = _identities(source["event_ids"], allow_empty=True)
        sources[identity] = source
    if set(sources) != required_sources:
        raise ValueError("projection_prior_required_source_inventory_mismatch")
    seen_events = {identity: set() for identity in sources}
    physical = {}
    evidence_kinds = {
        "acknowledged": {"model_serving_envelope", "substantive_review_record"},
        "uncertain": {"local_attempt_only", "unavailable_envelope", "unrecognized_envelope", "technical_failure", "incomplete_record"},
        "prepared_only": {"prepared_selection"},
        "predispatch_failure": {"explicit_predispatch_failure"},
    }
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {
                "event_id", "origin_source_id", "source_id", "record_sha256", "roles", "role_binding", "task_binding", "evidence"}:
            raise ValueError("projection_prior_observation_fields")
        event, origin, source = observation["event_id"], observation["origin_source_id"], observation["source_id"]
        physical_id = prior_event_identity(origin, event)
        if source not in sources or origin not in sources:
            raise ValueError("projection_prior_source_outside_inventory")
        for field in ("record_sha256", "role_binding"):
            _sha(observation[field])
        roles = _identities(observation["roles"])
        if not roles <= PRIOR_ROLES | {"production", "metadata_only"}:
            raise ValueError("projection_prior_role")
        task, evidence = observation["task_binding"], observation["evidence"]
        if not isinstance(task, dict) or set(task) != {"kind", "document_ids", "binding_sha256"}:
            raise ValueError("projection_prior_task_binding_fields")
        _sha(task["binding_sha256"])
        if task["kind"] not in {"article", "pair", "group", "multiarticle", "unavailable"}:
            raise ValueError("projection_prior_task_kind")
        if task["document_ids"] is None:
            if task["kind"] != "unavailable":
                raise ValueError("projection_prior_task_missing_members")
        else:
            ids = _identities(task["document_ids"])
            if (not ids <= known or task["kind"] == "unavailable"
                    or (task["kind"] == "article" and len(ids) != 1)
                    or (task["kind"] == "pair" and len(ids) != 2)):
                raise ValueError("projection_prior_task_member_binding")
        if (not isinstance(evidence, dict) or set(evidence) != {"state", "kind", "evidence_sha256"}
                or evidence.get("state") not in evidence_kinds
                or evidence.get("kind") not in evidence_kinds[evidence["state"]]):
            raise ValueError("projection_prior_evidence_state")
        _sha(evidence["evidence_sha256"])
        if evidence["state"] == "acknowledged":
            if task["document_ids"] is None:
                raise ValueError("projection_prior_acknowledged_members_unavailable")
            if evidence["kind"] == "substantive_review_record" and "substantive_review" not in roles:
                raise ValueError("projection_prior_review_role_missing")
        core = {"task_binding": task, "evidence": evidence, "origin_source_id": origin, "event_id": event}
        record_binding = {"source_id": source, "record_sha256": observation["record_sha256"],
                          "role_binding": observation["role_binding"], "roles": sorted(roles)}
        if physical_id in physical:
            if physical[physical_id]["core"] != core:
                raise ValueError("projection_prior_conflicting_physical_event")
            physical[physical_id]["roles"].update(roles)
            if record_binding not in physical[physical_id]["record_bindings"]:
                physical[physical_id]["record_bindings"].append(record_binding)
        else:
            physical[physical_id] = {"core": core, "roles": set(roles), "record_bindings": [record_binding]}
        seen_events[source].add(physical_id)
    if seen_events != expected_events:
        raise ValueError("projection_prior_event_inventory_mismatch")
    details = []
    for physical_id, item in sorted(physical.items()):
        task, evidence = item["core"]["task_binding"], item["core"]["evidence"]
        relevant = bool(item["roles"] & PRIOR_ROLES)
        if relevant and evidence["state"] == "acknowledged":
            confirmed.update(task["document_ids"])
        elif relevant and evidence["state"] == "uncertain":
            widen(task["document_ids"])
        details.append({"physical_event_id": physical_id, "event_id": item["core"]["event_id"],
            "origin_source_id": item["core"]["origin_source_id"], "roles": sorted(item["roles"]), "relevant_prior_role": relevant,
            "task_binding": task, "evidence": evidence, "record_bindings": item["record_bindings"]})
    metadata = {"version": VERSION, "input_index_digest": index.digest,
        "inventory_certificate_sha256": digest(certificate), "scope_statement": PRIOR_SCOPE,
        "cutoff_binding_sha256": certificate["cutoff_binding_sha256"],
        "absence_claim": "No recorded prior exposure in the reconciled study inventory.",
        "source_bindings": certificate["sources"], "physical_events": len(physical),
        "observed_views": len(observations), "task_bindings": details,
        "creates_pair_labels": False, "requires_audited_cross_study_inventory_and_evidence_normalization": True}
    return PriorExposureProjection(tuple(document.document_id for document in index.inputs),
        frozenset(confirmed), frozenset(uncertain), global_unknown, metadata)
