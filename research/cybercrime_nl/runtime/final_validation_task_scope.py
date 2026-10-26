"""Pure main-owner physical task census; no owner/model I/O or registration.

Use inside an audited parent with an active, fully verified AttemptInventory.
This closes supported *generic-intent* task semantics, not universal historical
discovery, manual reviews, P exposure, or permission to dispatch. Every intent,
including an orphan, survives. Exact original contracts can prove a different
estimand without a response or P label. A phase string cannot prove that.

The returned certificate is a main-owner contribution only. A later reviewed
parent must combine it with every declared external/manual scope; passing it
alone as a whole-study history certificate would be incorrect. Existing frozen
parents are deliberately not changed to consume it.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import dossier_contract_v4 as v4
import final_validation_exposure as exposure
import final_validation_pair_history as pair_history
import final_validation_prior as prior
import final_validation_roles as roles
from dossier_transport import Invocation
from final_validation_frame import build_input_index
from newsresearch.common import ResearchError, canonical, digest

VERSION = "final-validation-main-owner-task-scope-v1"
SCOPE = "all-durable-generic-model-intents-in-one-verified-main-owner-cutoff"
DISPOSITIONS = {
    "pair_reference_blocker", "possible_pair_reference_bounded",
    "possible_pair_reference_global", "proven_not_pair_reference", "proven_source_disjoint",
}
SEMANTICS = {
    "seed": "full-article candidate identity decisions; purpose requires retained production/development plan",
    "assignment": "one article versus historical dossier representations, not an independent full-article pair reference",
    "assignment_full_member_control": "fixed article-to-group diagnostic control, not an independent pair reference",
    "summary": "source-based summary generation",
    "summary_faithfulness": "summary fidelity and distinguishing-evidence review",
    "summary_quality": "summary fidelity and distinguishing-evidence review",
    "summary_quality_audit": "summary fidelity reference, not pair-reference identity",
    "summary_fidelity_audit": "summary fidelity diagnostic, not pair-reference identity",
    "card_quality": "group/card sufficiency and focus review",
    "card_quality_audit": "group/card sufficiency reference, not pair-reference identity",
    "embeddings": "retrieval vectors, no judgment questions",
    "audit": "full-source identity reference; exact named plan required to assign historical primary role",
}


def _require(value, reason):
    if not value:
        raise ValueError("task_scope_" + reason)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), Path(v4.__file__))
    return {**pair_history.implementation(), **prior.original.implementation(),
            **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _bytes(value):
    return canonical(value).encode()


@dataclass(frozen=True)
class MainTaskScope:
    dispositions_json: bytes
    history_records_json: bytes
    prepared_only_json: bytes
    manifest_json: bytes
    inventory_certificate_json: bytes

    @property
    def dispositions(self):
        return json.loads(self.dispositions_json)

    @property
    def history_records(self):
        """Protected original pair packets/results; never a public projection."""
        return json.loads(self.history_records_json)

    @property
    def prepared_only(self):
        return json.loads(self.prepared_only_json)

    @property
    def manifest(self):
        return json.loads(self.manifest_json)

    @property
    def inventory_certificate(self):
        return json.loads(self.inventory_certificate_json)


def _identity(document):
    return {"document_id": document["document_id"],
            **{k + "_sha256": hashlib.sha256(document[k].encode()).hexdigest() for k in ("title", "body")},
            "input_sha256": digest({k: document[k] for k in ("title", "body")})}


def _literal_sources(packet, index):
    """Only candidate literal sources; not proven until exact wire rebuild passes."""
    values = packet.get("original_documents", packet.get("documents"))
    if not isinstance(values, list) or not values:
        return None
    extra = [d for s in packet.get("candidate_cards", []) for d in s.get("original_documents", [])]
    seen = {}
    indexed = {d.document_id: d.input_sha256 for d in index.inputs}
    for value in [*values, *extra]:
        doc = prior.v1.document_evidence(value)
        identifier = doc["document_id"]
        _require(identifier not in seen or seen[identifier] == doc, "conflicting_literal_source")
        if identifier in indexed:
            _require(digest({k: doc[k] for k in ("title", "body")}) == indexed[identifier], "indexed_input_changed")
        seen[identifier] = doc
    return list(seen.values())


def _local_index(documents, index):
    return build_input_index([
        {"document_id": d["document_id"], "input_sha256": _identity(d)["input_sha256"],
         "article_row_ids": ["literal:" + d["document_id"]]} for d in documents],
        {d["document_id"]: None for d in documents}, bindings=dict(index.bindings))


def _same(actual, expected):
    expected = {**expected, **({"kind": actual["kind"]} if "kind" in actual else {})}
    # Runtime kind is checked independently. Only the local token proxy may
    # differ; every builder-produced wire/source/normalization field must agree.
    expected = {k: v for k, v in expected.items() if k != "input_tokens_proxy"}
    return set(expected) <= set(actual) and canonical({k: actual[k] for k in expected}) == canonical(expected)


def _proof(packet, index, artifacts, embedding_packets):
    """Return exact contract + complete source identity, or an explicit gap.

    A failed builder match never falls back to phase-based classification.
    Malformed immutable source identity propagates. Unsupported semantic wire is
    retained as a global gap, rather than inferred from its local document list.
    """
    phase = packet.get("phase")
    if phase == "embeddings":
        expected = embedding_packets.get(digest(packet))
        if expected is None:
            return None, "embedding_original_packet_unproven"
        ids = sorted({c["document_id"] for c in expected["chunks"]})
        return {"builder": "run_dossiers.embedding_packets", "estimand": SEMANTICS[phase],
                "source_identities": [], "document_ids": ids, "source_complete": True,
                "sources_from_complete_frozen_input_order": True}, None
    if phase not in SEMANTICS:
        return None, "unrecognized_task_contract"
    documents = _literal_sources(packet, index)
    if documents is None:
        return None, "literal_sources_unavailable"
    primary = packet.get("original_documents", packet.get("documents"))
    docs = [prior.v1.document_evidence(d) for d in primary]
    kind = "decisions" if phase in {"seed", "assignment", "assignment_full_member_control", "summary_faithfulness"} else "responses"
    if packet.get("kind", "decisions") != kind:
        return None, "task_transport_contract_unproven"
    def count(_):
        return 0
    candidates = []
    metadata = None
    try:
        if phase in {"seed", "assignment"}:
            metadata = exposure.packet_metadata(_local_index(documents, index), packet, packet["request"],
                packet_sha256=digest(packet), request_sha256=digest(packet["request"]), artifacts=artifacts)
            if phase == "seed":
                pairs = [(packet["question_map"][q["name"]]["left"], packet["question_map"][q["name"]]["right"])
                         for q in packet["request"]["questions"] if packet["question_map"][q["name"]]["kind"] == "pair"]
                maker = prior.v5 if packet["method"] == prior.v5.METHOD else prior.v1
                exact = maker.seed_request(docs, pairs=pairs, count_tokens=count, max_tokens=96_000)
            elif packet["method"] == prior.v5.METHOD:
                exact = prior.v5.assignment_request(docs[0], packet["candidate_cards"], count_tokens=count, max_tokens=96_000)
            else:
                exact, _ = exposure._legacy_assignment(packet, docs, {}, exposure._Artifacts(artifacts))
            if not _same(packet, exact):
                return None, "exact_task_contract_unproven"
            complete = all(m["source_document_ids"] is not None for m in metadata["candidate_memberships"])
            return {"builder": "final_validation_exposure.packet_metadata", "estimand": SEMANTICS[phase],
                    "source_identities": [_identity(d) for d in documents],
                    "document_ids": [d["document_id"] for d in documents], "source_complete": complete,
                    "request_metadata_sha256": digest(metadata)}, None
        if phase == "assignment_full_member_control":
            candidates.append(("dossier_contract_v5.full_member_assignment_request",
                prior.v5.full_member_assignment_request(docs[0], packet["candidate_cards"], count_tokens=count, max_tokens=96_000)))
        elif phase == "summary":
            for maker in (prior.v1, prior.v2, prior.v3, v4):
                try:
                    candidates.append((maker.__name__ + ".summary_request", maker.summary_request(docs,
                        packet["bindings"]["dossier_id"], packet["bindings"]["membership_revision"],
                        count_tokens=count, max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])))
                except ResearchError:
                    continue
        elif phase == "summary_faithfulness":
            supplied = json.loads(packet["request"]["input"])
            summary = supplied["summary"]
            snapshot = {"summary": summary, "summary_version": digest(summary)}
            candidates.append(("dossier_contract.summary_faithfulness_request",
                prior.v1.summary_faithfulness_request(docs, snapshot, count_tokens=count, max_tokens=96_000)))
        elif phase in {"summary_quality", "summary_quality_audit"}:
            maker = getattr(v4, phase + "_request")
            candidates.append(("dossier_contract_v4." + phase + "_request", maker(docs, packet["summary_snapshot"],
                count_tokens=count, max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])))
        elif phase in {"card_quality", "card_quality_audit"}:
            maker = getattr(prior.v5, phase + "_request")
            candidates.append(("dossier_contract_v5." + phase + "_request", maker(docs, packet["card_snapshot"],
                count_tokens=count, max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])))
        elif phase == "summary_fidelity_audit":
            for maker in (prior.fidelity_v1, prior.fidelity_v2):
                candidates.append((maker.__name__ + ".request", maker.request(docs, packet["summary_snapshot"],
                    count_tokens=count, max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])))
        elif phase == "audit":
            for maker in (prior.v1, prior.v2, prior.v3, prior.v5):
                try:
                    candidates.append((maker.__name__ + ".audit_request", maker.audit_request(docs, count_tokens=count,
                        max_tokens=96_000, max_output_tokens=packet["request"]["max_output_tokens"])))
                except ResearchError:
                    continue
    except (KeyError, TypeError, ValueError, ResearchError):
        return None, "exact_task_contract_unproven"
    matches = [name for name, expected in candidates if _same(packet, expected)]
    if not matches:
        return None, "exact_task_contract_unproven"
    return {"builder": matches[0], "estimand": SEMANTICS[phase],
            "source_identities": [_identity(d) for d in documents],
            "document_ids": [d["document_id"] for d in documents], "source_complete": True}, None


def classify_main_owner_tasks(reader, documents, *, count_tokens, tokenizer_binding, encoder=None):
    """Classify every actual generic intent using unchanged frozen producers.

    documents is the exact complete indexed input order (list or keyed Mapping).
    count_tokens/encoder and tokenizer_binding must be verified by the audited
    parent; this helper binds their use, not their implementation authenticity.
    Encoder absence leaves any embeddings unsupported instead of inventing input
    provenance. RoleResolution is recomputed here; caller roles are not accepted.
    Results contain no new labels, requests, attempts, usage or cost accounting.
    """
    exposure._sha(tokenizer_binding)
    _require(callable(count_tokens), "token_counter_required")
    if isinstance(documents, Mapping):
        _require(set(documents) == {d.document_id for d in reader.index.inputs}, "complete_documents")
        documents = [documents[d.document_id] for d in reader.index.inputs]
    docs = exposure._documents(reader.index, documents)
    _require([d["document_id"] for d in docs] == [d.document_id for d in reader.index.inputs], "complete_input_order")
    certificate = reader.certificate
    store = exposure._Artifacts(reader.artifacts)
    census = store.get(certificate["evidence_sha256"])
    _require(census.get("source_head") == certificate["source_head"]
             and census.get("plan") == certificate["plan"]
             and census.get("input_index_digest") == certificate["input_index_digest"] == reader.index.digest,
             "census_binding")
    events, intents, tasks = {}, {}, set()
    for row in reader.events:
        value = exposure._event(row, certificate["source_head"][0])
        _require(row["seq"] not in events, "duplicate_event")
        events[row["seq"]] = row, value
        if row["kind"] == "model.attempt.intended":
            _require(value.get("attempt") not in intents and value.get("task_key") not in tasks
                     and value.get("batch") == certificate["plan"], "physical_intent_scope")
            intents[value["attempt"]] = row, value
            tasks.add(value["task_key"])
    _require([row["event_hash"] for row, _ in intents.values()] == census.get("intent_event_hashes"), "complete_intent_census")
    _require([row["id"] for row in reader.records] == census.get("record_ids"), "complete_response_census")
    responses, derived = {}, []
    for row in reader.records:
        value = exposure._record(row, events, store)
        if row["kind"] == "cyber_dossier_response":
            attempt = value["attempt"]
            _require(attempt in intents and attempt not in responses, "unique_response_intent")
            intent = intents[attempt][1]
            _require(all(value.get(k) == intent.get(k) for k in ("task_key", "phase", "packet", "request")), "response_identity")
            responses[attempt] = row
        elif row["kind"] == "cyber_dossier_seed_revalidation":
            derived.append(row["id"])
        else:
            _require(False, "unexpected_response_record_kind")
    # Exact registered phase plans, not generic phase labels, establish purpose.
    resolution = roles.resolve_inventory_roles(reader, {d["document_id"]: d for d in docs},
        count_tokens=count_tokens, tokenizer_binding=tokenizer_binding)
    references = pair_history.normalize_main_owner_pair_history(reader, resolution)
    ref_bindings = {b["original_attempt"]: b for b in references.manifest["attempt_bindings"]}
    role_by_attempt = {r["attempt"]: r for r in resolution.catalog["attempts"]}
    embeddings = {}
    if encoder is not None and any(v["phase"] == "embeddings" for _, v in intents.values()):
        _require(callable(getattr(encoder, "encode", None)), "encoder_required")
        embeddings = {digest(p): p for p in prior.original.embedding_packets(docs, encoder)}
    indexed_hashes = {d.input_sha256 for d in reader.index.inputs}
    dispositions, unknown, global_gap = [], set(), False
    for attempt, (event, intent) in intents.items():
        packet, request, dispatch = (store.get(intent[k]) for k in ("packet", "request", "dispatch"))
        kind = packet.get("kind", "decisions")
        _require(packet.get("phase") == intent.get("phase") and canonical(packet.get("request")) == canonical(request)
                 and digest(request) == intent["request"]
                 and intent["task_key"] == digest([certificate["plan"], kind, request])
                 and canonical(dispatch) == canonical(Invocation(request, attempt, kind).manifest()), "immutable_request_dispatch_binding")
        _require(packet.get("request_sha256") == intent["request"] or (kind == "embeddings"
                 and packet.get("phase") == "embeddings" and "request_sha256" not in packet), "request_hash_binding")
        proof, reason = _proof(packet, reader.index, reader.artifacts, embeddings)
        in_frame, disposition = [], "possible_pair_reference_global"
        if attempt in ref_bindings:
            _require(proof is not None and proof["source_complete"], "reference_source_proof")
            disposition, reason = "pair_reference_blocker", "exact_named_reference_plan"
        elif proof is not None:
            in_frame = sorted({s["input_sha256"] for s in proof["source_identities"]} & indexed_hashes)
            if packet["phase"] not in {"seed", "audit"}:
                disposition, reason = "proven_not_pair_reference", "exact_different_estimand_contract"
            elif packet["phase"] == "seed" and set(role_by_attempt[attempt]["roles"] or []) & {"production", "development"}:
                disposition, reason = "proven_not_pair_reference", "exact_candidate_purpose_plan"
            elif proof["source_complete"] and len(in_frame) < 2:
                disposition, reason = "proven_source_disjoint", "no_complete_compared_pair_in_current_frame"
            elif proof["source_complete"]:
                disposition, reason = "possible_pair_reference_bounded", "independent_reference_role_unproven"
            else:
                reason = "complete_compared_source_scope_unavailable"
        if disposition == "possible_pair_reference_global":
            global_gap = True
        if disposition == "possible_pair_reference_bounded":
            unknown.update(in_frame)
        _require(disposition in DISPOSITIONS, "disposition")
        dispositions.append({"original_attempt": attempt, "owner_sha256": digest(certificate["source_id"]),
            "attempt_id": digest([certificate["source_id"], attempt]), "task_key": intent["task_key"],
            "intent_event": event["event_hash"], "response_record": responses.get(attempt, {}).get("id"),
            "return_state": "retained_response" if attempt in responses else "no_retained_response",
            "packet": intent["packet"], "request": intent["request"], "dispatch": intent["dispatch"],
            "phase": intent["phase"] if intent["phase"] in SEMANTICS else "unrecognized",
            "disposition": disposition, "reason_code": reason,
            "source_proof": proof, "bounded_unknown_input_sha256": in_frame if disposition == "possible_pair_reference_bounded" else [],
            "role_evidence_ids": sorted(role_by_attempt[attempt]["evidence_ids"]),
            "reference_binding": ref_bindings.get(attempt)})
    prepared = [{"disposition": "prepared_only", "evidence": p}
                for p in resolution.catalog["planned_task_bindings"] if p["physical_attempt"] is None]
    prepared += [{"disposition": "prepared_only", "evidence": p} for p in references.manifest["prepared_only"]]
    for gap in resolution.catalog["unresolved_evidence"]:
        if gap["reason_code"] in {"prepared_capacity_deferred_no_attempt", "prepared_reference_capacity_no_attempt"}:
            prepared.append({"disposition": "prepared_only", "evidence": gap})
    prepared = list({digest(p): p for p in prepared}.values())
    counts = Counter(d["disposition"] for d in dispositions)
    manifest = {"version": VERSION, "scope": SCOPE, "source_id": certificate["source_id"],
        "source_head": certificate["source_head"], "plan": certificate["plan"], "input_index_digest": reader.index.digest,
        "census_artifact": certificate["evidence_sha256"], "tokenizer_binding": tokenizer_binding,
        "role_catalog_sha256": digest(resolution.catalog), "pair_history_manifest_sha256": digest(references.manifest),
        "physical_identity_policy": pair_history.PHYSICAL_ID_POLICY, "semantics_sha256": digest(SEMANTICS),
        "dispositions_sha256": digest(dispositions), "history_records_sha256": digest(list(references.records)),
        "prepared_only_sha256": digest(prepared), "physical_intents": len(intents),
        "disposition_counts": dict(counts), "responses": len(responses), "orphan_intents": len(intents) - len(responses),
        "derived_records": len(derived), "derived_record_ids": derived, "prepared_only_evidence": len(prepared),
        "main_generic_intent_scope_complete": not global_gap and not unknown,
        "bounded_unknown_inputs": len(unknown), "global_possible_pair_gap": global_gap,
        "source_census_integrity_verified_by_this_pure_helper": False,
        "tokenizer_authenticity_verified_by_this_pure_helper": False,
        "nongateway_or_manual_task_discovery_complete": False, "whole_study_history_complete": False,
        "prior_exposure_reclassified": False, "creates_pair_labels": False, "new_attempts": 0,
        "dispatch_authorized": False, "implementation_sha256": digest(implementation())}
    inventory = {"binding_sha256": digest(manifest), "complete": not global_gap and not unknown,
                 "unknown_input_sha256": sorted(unknown), "global_gap": global_gap}
    pair_history.history.validate_inventory(inventory)
    return MainTaskScope(_bytes(dispositions), _bytes(list(references.records)), _bytes(prepared), _bytes(manifest), _bytes(inventory))
