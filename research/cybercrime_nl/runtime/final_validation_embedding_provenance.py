"""Pure retained embedding reconstruction; no owner, filesystem or model calls.

Use inside the later registered offline parent while its immutable inventory is
open. This validates supplied exact bytes/rows and recomputes the frozen producer;
it does not establish ledger-census completeness, source-owner authenticity or
the injected tokenizer implementation merely from a caller's certificate.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json

import numpy as np

import final_validation_exposure as retained
import final_validation_vectors as vectors
import run_dossiers as producer
from dossier_transport import Invocation
from final_validation_frame import InputIndex
from newsresearch.common import ResearchError, canonical, digest
from newsresearch.embeddings import VOCAB_HASH
from newsresearch.gateway import ProviderResponse

VERSION = "final-validation-embedding-provenance-v1"
TOKENIZER_FIELDS = {"encoding", "library", "version", "vocabulary_sha256", "verification_record"}
RESULT_FIELDS = {"payload", "provider", "model", "request_id", "usage", "raw_response"}


def _require(value, reason):
    if not value:
        raise ValueError("embedding_provenance_" + reason)


def _phase(row, event, store, *, head, plan):
    fields = {"id", "kind", "logical_key", "payload", "artifact", "supersedes", "created_event"}
    _require(isinstance(row, dict) and set(row) == fields and row["kind"] == "cyber_dossier_phase"
             and row["logical_key"] == "embeddings" and row["supersedes"] is None, "phase_record")
    value = store.get(row["artifact"])
    _require(row["payload"] == canonical(value)
             and row["id"] == digest({"kind": row["kind"], "key": "embeddings", "payload": row["artifact"], "supersedes": None}),
             "phase_identity")
    payload = retained._event(event, head[0])
    _require(event["seq"] == row["created_event"] and event["kind"] == "record.created"
             and payload == {"record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "phase_creation")
    _require(value.get("name") == "embeddings" and value.get("plan") == plan, "phase_plan")
    return value, store.get(value["artifact"])


def pool_exact(documents, packets, parsed_by_task, plan):
    """Exact frozen vectors() ordering/float operations, without dispatch or repair."""
    pieces = {}
    for packet in packets:
        reply = parsed_by_task.get(digest([plan, "embeddings", packet["request"]]))
        if reply is None:
            continue
        for locator, vector in zip(packet["chunks"], reply["vectors"], strict=True):
            pieces.setdefault(locator["document_id"], []).append((locator, vector))
    ids, pooled, missing = [], [], []
    for identifier in sorted(d["document_id"] for d in documents):
        values = sorted(pieces.get(identifier, []), key=lambda x: x[0]["token_start"])
        cursor, sums = 0, np.zeros(1536, dtype=np.float64)
        for locator, vector in values:
            if locator["token_start"] != cursor:
                break
            length = locator["token_end"] - cursor
            sums += np.asarray(vector) * length
            cursor = locator["token_end"]
        if not values or cursor != values[-1][0]["full_tokens"] or np.linalg.norm(sums) == 0:
            missing.append(identifier)
            continue
        ids.append(identifier)
        pooled.append((sums / np.linalg.norm(sums)).tolist())
    return {"document_ids": ids, "vectors": pooled, "missing": missing, "purpose": vectors.PURPOSE}


@dataclass(frozen=True)
class VerifiedEmbeddings:
    vectors: vectors.ExistingVectors
    input_bindings_json: bytes
    metadata_json: bytes
    digest: str

    @property
    def input_bindings(self):
        return json.loads(self.input_bindings_json)

    @property
    def metadata(self):
        return json.loads(self.metadata_json)


def verify_embedding_provenance(index: InputIndex, documents: list[dict], encoder, *,
        events: list[dict], records: list[dict], artifacts, inventory: dict,
        phase_record: dict, phase_creation_event: dict, profile: dict,
        bindings: dict, tokenizer: dict) -> VerifiedEmbeddings:
    """Verify an inventory subset, full chunks and the already-retained phase.

    events/records are the complete AttemptInventory.events/records; artifacts may
    be its live ScopedArtifacts Mapping. inventory is the bound census_artifact
    (NOT the pair-only exposure certificate). phase_creation_event comes from the
    same locked cutoff; the parent must fetch/verify that one exact event. Profile
    version↔plan and tokenizer vocabulary evidence are still audited upstream.
    documents follow the frozen input-manifest order, as producer.documents did.

    Every original packet occurrence is rebuilt, including exact-wire dedup reuse;
    held, unreturned, invalid and unattempted tasks contribute no chunk vectors.
    Successful parsed values are checked against raw payloads, not regenerated.
    Original accounting/status is verified, never written back or released.
    """
    _require(isinstance(index, InputIndex) and isinstance(documents, list), "input_index_or_documents")
    _require(profile == vectors.PROFILE, "embedding_profile")
    _require(isinstance(tokenizer, dict) and set(tokenizer) == TOKENIZER_FIELDS
             and tokenizer["encoding"] == "cl100k_base" and getattr(encoder, "name", None) == "cl100k_base"
             and tokenizer["library"] == "tiktoken" and isinstance(tokenizer["version"], str)
             and bool(tokenizer["version"]) and tokenizer["vocabulary_sha256"] == VOCAB_HASH, "tokenizer_binding")
    retained._sha(tokenizer["verification_record"])
    docs = retained._documents(index, documents)
    _require([d["document_id"] for d in docs] == [d.document_id for d in index.inputs], "full_frozen_input_order")
    inputs = [{"document_id": d.document_id, "input_sha256": d.input_sha256} for d in index.inputs]
    _require(isinstance(inventory, dict) and inventory.get("input_index_digest") == index.digest,
             "inventory_index")
    head, plan = inventory["source_head"], inventory["plan"]
    _require(isinstance(head, list) and len(head) == 2 and type(head[0]) is int
             and dict(index.bindings)["source_head"] == digest(head), "source_cutoff")
    retained._sha(plan)
    store = retained._Artifacts(artifacts)
    phase_value, phase = _phase(phase_record, phase_creation_event, store, head=head, plan=plan)
    phase_ids, phase_hashes = inventory.get("phase_record_ids", []), inventory.get("phase_event_hashes", [])
    _require(len(phase_ids) == len(phase_hashes) and len(set(phase_ids)) == len(phase_ids)
             and phase_record["id"] in phase_ids
             and phase_hashes[phase_ids.index(phase_record["id"])] == phase_creation_event["event_hash"]
             and bindings.get("plan") == plan and bindings.get("phase_record") == phase_record["id"]
             and bindings.get("phase_artifact") == phase_value["artifact"], "phase_census_binding")
    prepared_vectors = vectors.prepare_existing_vectors(index, phase, profile, input_bindings=inputs, bindings=bindings)

    selected, intended = {}, {}
    for row in events:
        value = retained._event(row, head[0])
        _require(row["seq"] not in selected and row["kind"] in {"model.attempt.intended", "record.created"}, "event_census")
        selected[row["seq"]] = (row, value)
        if row["kind"] == "model.attempt.intended":
            _require(value.get("attempt") not in intended, "duplicate_attempt")
            intended[value["attempt"]] = (row, value)
    _require({r["event_hash"] for r, _ in intended.values()} == set(inventory["intent_event_hashes"]), "intent_census")
    _require(len(records) == len({r["id"] for r in records})
             and {r["id"] for r in records} == set(inventory["record_ids"]), "response_census")
    responses = {}
    for row in records:
        value = retained._record(row, selected, store)
        if row["kind"] != "cyber_dossier_response":
            continue
        attempt = value.get("attempt")
        _require(attempt in intended and attempt not in responses, "response_attempt")
        responses[attempt] = (row, value)

    # Use unchanged frozen pure builders/parser; no Study/transport is constructed.
    packets = producer.embedding_packets(docs, encoder)
    _require({chunk["document_id"] for packet in packets for chunk in packet["chunks"]}
             == {d.document_id for d in index.inputs}, "tokenizer_omitted_full_input")
    expected = {}
    for packet in packets:
        key = digest([plan, "embeddings", packet["request"]])
        expected.setdefault(key, packet)  # Original calls() sends first occurrence only.
    actual, usable, statuses, provenance = {}, {}, Counter(), []
    for event, intent in intended.values():
        if intent.get("phase") != "embeddings":
            continue
        key, attempt = intent.get("task_key"), intent.get("attempt")
        _require(intent.get("batch") == plan and type(intent.get("number")) is int
                 and intent["number"] == 1 and intent.get("category") == "main"
                 and key in expected and key not in actual and event["seq"] < phase_record["created_event"], "embedding_intent_scope")
        actual[key] = attempt
        packet, request, dispatch = (store.get(intent[k]) for k in ("packet", "request", "dispatch"))
        _require(packet == expected[key] and request == packet["request"]
                 and intent["request"] == digest(request)
                 and dispatch == Invocation(request, attempt, "embeddings").manifest(), "exact_original_request_and_chunks")
        _require(intent.get("reserved_nanousd") == producer.reserve(packet), "original_reservation")
        result = responses.get(attempt)
        row_id, status, observed_model = None, "unreturned", None
        if result is not None:
            row, response = result
            row_id = row["id"]
            _require(row["created_event"] < phase_record["created_event"] and response.get("plan") == plan
                     and row["logical_key"] == key
                     and all(response.get(k) == intent.get(k) for k in
                             ("attempt", "task_key", "phase", "category", "packet", "request", "execution_amendment")), "response_binding")
            envelope = store.get(response["response"])
            _require(isinstance(envelope, dict) and set(envelope) == RESULT_FIELDS
                     and envelope["provider"] == "openai-embeddings" and isinstance(envelope["raw_response"], dict), "envelope_fields")
            raw, payload = envelope["raw_response"], envelope["payload"]
            observed_model = envelope["model"]
            _require(response.get("http_status") == raw.get("http_status")
                     and raw.get("kind") == "embeddings", "response_http_binding")
            if payload is not None:
                _require(raw.get("http_status") == 200 and isinstance(payload, dict)
                         and payload.get("model") == envelope["model"] and payload.get("usage") == envelope["usage"]
                         and isinstance(raw.get("response_text"), str)
                         and json.loads(raw["response_text"]) == payload, "retained_payload_transport_binding")
            cost = producer.billed(packet, ProviderResponse(**envelope))
            hold = bool(raw.get("unknown_outcome")) or cost is None or cost > intent["reserved_nanousd"]
            _require(type(response.get("hold")) is bool and response["hold"] == hold
                     and response.get("cost_nanousd") == cost
                     and response.get("reserved_nanousd") == (intent["reserved_nanousd"] if hold else 0), "retained_accounting_changed")
            reparsed = None
            if payload is not None:
                try:
                    reparsed = producer.parse_embeddings(packet, payload)
                except (KeyError, TypeError, ValueError, ResearchError):
                    pass  # Keep original invalidity; never repair/replace a vector.
            saved = store.get(response["parsed"]) if response.get("parsed") else None
            _require(saved == reparsed, "retained_parsed_vector_changed")
            status = "held" if hold else "invalid" if saved is None else "usable"
            if status == "usable":
                usable[key] = saved
        statuses[status] += 1
        provenance.append({"task_key": key, "attempt": attempt, "intent_event": event["event_hash"],
            "packet": intent["packet"], "request": intent["request"], "response_record": row_id,
            "observed_model": observed_model, "status": status})
    statuses["unattempted"] = len(set(expected) - set(actual))
    recomputed = pool_exact(docs, packets, usable, plan)
    _require(recomputed == phase, "saved_pool_or_missing_partition_changed")
    metadata = {"version": VERSION, "source_head": head, "plan": plan, "input_index_digest": index.digest,
        "inventory_sha256": digest(inventory), "phase_record": phase_record["id"], "phase_artifact": phase_value["artifact"],
        "profile_record": bindings["profile_record"], "tokenizer": tokenizer,
        "prepared_vectors_digest": prepared_vectors.digest, "input_bindings_artifact": digest(inputs),
        "documents": len(docs), "article_rows": sum(len(i.article_row_ids) for i in index.inputs),
        "planned_packet_occurrences": len(packets), "unique_request_tasks": len(expected),
        "exact_wire_reused_occurrences": len(packets) - len(expected),
        "planned_chunks": sum(len(p["chunks"]) for p in packets),
        "full_input_tokens": sum(p["input_tokens_proxy"] for p in packets),
        "task_statuses": dict(statuses), "pooled_inputs": len(phase["document_ids"]), "missing_inputs": len(phase["missing"]),
        "verified_task_provenance": provenance, "checked_artifacts": sorted(store.checked),
        "exact_original_requests_and_full_chunk_coverage_verified": True,
        "retained_pool_and_missing_partition_reproduced": True, "new_model_calls": 0,
        "embedding_retries": 0, "retained_status_or_cost_changes": 0,
        "full_source_ledger_census_independently_verified": False,
        "profile_plan_and_tokenizer_implementation_independently_verified": False,
        "limitations": "Supplied immutable bytes/census checked; parent must bind complete locked inventory, source/profile versions and hash-verified cl100k implementation. Exact old float operations are replayed locally; no model semantics or external provenance is inferred."}
    return VerifiedEmbeddings(prepared_vectors, canonical(inputs).encode(), canonical(metadata).encode(), digest(metadata))
