"""Synthetic source strings, tokenizer and immutable rows; no owner/model access."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_embedding_provenance as subject  # noqa: E402
from final_validation_frame import build_input_index  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402
from newsresearch.gateway import ProviderResponse  # noqa: E402
from test_final_validation_exposure import Census  # noqa: E402


class SyntheticEncoder:
    # Test double only: this is explicitly NOT actual cl100k tokenization.
    name = "cl100k_base"

    def encode(self, text, *, disallowed_special):
        assert disallowed_special == ()
        return list(text.encode("utf-8"))


def source(lengths=(7000, 13000, 2000)):
    return [{"document_id": f"d{i}", "title": f"Synthetic title {i} Ω",
             "body": ("a" * n) + "\r\n\r\n完整 unchanged tail. "} for i, n in enumerate(lengths)]


def fixture(*, statuses=None, lengths=(7000, 13000, 2000), mutate_packet=None, mutate_response=None, encoder=None):
    statuses = statuses or {}
    census, documents = Census(), source(lengths)
    encoder = encoder or SyntheticEncoder()
    packets = subject.producer.embedding_packets(documents, encoder)
    seen, parsed = set(), {}
    for packet in packets:
        key = digest([census.plan, "embeddings", packet["request"]])
        if key in seen:
            continue
        position = len(seen)
        seen.add(key)
        status = statuses.get(position, "usable")
        if status == "unattempted":
            continue
        retained = deepcopy(packet)
        if mutate_packet:
            mutate_packet(retained)
        attempt = f"embedding-{position}"
        intent = {"attempt": attempt, "task_key": key, "number": 1, "batch": census.plan,
            "request": census.put(retained["request"]), "packet": census.put(retained),
            "dispatch": census.put(subject.Invocation(retained["request"], attempt, "embeddings").manifest()),
            "phase": "embeddings", "category": "main", "reserved_nanousd": subject.producer.reserve(retained),
            "started_at": "2026-10-24T00:00:00Z"}
        census.event("model.attempt.intended", intent)
        if status == "unreturned":
            continue
        data = []
        for i in range(len(packet["chunks"])):
            values = [0.0] * 1536
            values[i % 3] = 0.5 + i / 100
            values[(i + 1) % 3] = 0.7
            data.append({"index": i, "embedding": values, "object": "embedding"})
        payload = {"object": "list", "model": "text-embedding-3-large", "data": list(reversed(data)),
                   "usage": {"prompt_tokens": packet["input_tokens_proxy"], "total_tokens": packet["input_tokens_proxy"]}}
        if status == "invalid":
            payload["data"].pop()
        if status == "model_missing":
            payload["model"] = None
        envelope = {"payload": payload, "provider": "openai-embeddings", "model": payload["model"],
            "request_id": attempt, "usage": payload["usage"],
            "raw_response": {"http_status": 200, "dispatch_started": True, "unknown_outcome": False,
                "kind": "embeddings", "response_text": canonical(payload)}}
        if status == "opaque":
            envelope.update(payload=None, model=None, usage=None)
            envelope["raw_response"] = {"dispatch_started": True, "unknown_outcome": True,
                "kind": "embeddings", "error_type": "ResearchError"}
        result = None
        if envelope["payload"] is not None:
            try:
                result = subject.producer.parse_embeddings(packet, envelope["payload"])
            except subject.ResearchError:
                pass
        cost = subject.producer.billed(packet, ProviderResponse(**envelope))
        hold = bool(envelope["raw_response"].get("unknown_outcome")) or cost is None or cost > intent["reserved_nanousd"]
        row = {"plan": census.plan, **{k: intent[k] for k in ("attempt", "task_key", "phase", "category", "packet", "request")},
            "response": census.put(envelope), "parsed": census.put(result) if result is not None else None,
            "cost_nanousd": cost, "reserved_nanousd": intent["reserved_nanousd"] if hold else 0,
            "hold": hold, "validation_error": "invalid" if result is None else None,
            "http_status": envelope["raw_response"].get("http_status"), "at": "2026-10-24T00:00:00Z"}
        if mutate_response:
            mutate_response(row, envelope, census)
        census.record("cyber_dossier_response", key, row)
        if result is not None and not hold:
            parsed[key] = result
    phase = subject.pool_exact(documents, packets, parsed, census.plan)
    phase_row = census.record("cyber_dossier_phase", "embeddings", {
        "name": "embeddings", "plan": census.plan, "artifact": census.put(phase), "at": "2026-10-24T00:00:01Z"})
    phase_event = census.events[-1]
    head = [phase_event["seq"], phase_event["event_hash"]]
    idx = build_input_index([{"document_id": d["document_id"], "input_sha256": digest({k: d[k] for k in ("title", "body")}),
        "article_row_ids": [f"article-{d['document_id']}"]} for d in documents], {d["document_id"]: None for d in documents},
        bindings={"source_head": digest(head), "final_report": digest("final"), "input_manifest": digest("input-manifest")})
    inputs = [{"document_id": row.document_id, "input_sha256": row.input_sha256} for row in idx.inputs]
    rows, events = census.records[:-1], census.events[:-1]
    bindings = {"source_head": digest(head), "plan": census.plan, "phase_record": phase_row["id"],
        "phase_artifact": digest(phase), "profile_record": digest("embedding-profile-record"),
        "profile_sha256": digest(subject.vectors.PROFILE), "input_manifest": dict(idx.bindings)["input_manifest"],
        "input_bindings_artifact": digest(inputs)}
    args = {"events": events, "records": rows, "artifacts": census.artifacts,
        "inventory": {"source_head": head, "plan": census.plan, "input_index_digest": idx.digest,
            "intent_event_hashes": [e["event_hash"] for e in events if e["kind"] == "model.attempt.intended"],
            "record_ids": [r["id"] for r in rows], "phase_record_ids": [phase_row["id"]],
            "phase_event_hashes": [phase_event["event_hash"]]},
        "phase_record": phase_row, "phase_creation_event": phase_event, "profile": deepcopy(subject.vectors.PROFILE),
        "bindings": bindings, "tokenizer": {"encoding": "cl100k_base", "library": "tiktoken",
            "version": "synthetic-test-double", "vocabulary_sha256": subject.VOCAB_HASH,
            "verification_record": digest("synthetic-tokenizer-certificate-not-production-proof")}}
    return idx, documents, encoder, args, packets, parsed, phase


def verify(item):
    idx, documents, encoder, args, *_ = item
    return subject.verify_embedding_provenance(idx, documents, encoder, **args)


def test_exact_full_unicode_source_requests_float32_chunks_and_pool_match_frozen_producer():
    item = fixture()
    value = verify(item)
    idx, documents, encoder, args, packets, replies, saved = item

    class Replay:
        def __init__(self):
            self.documents = {d["document_id"]: d for d in documents}
            self.encoder = encoder

        def phase(self, _session, name, value=None):
            assert name == "embeddings"
            return value

        def calls(self, _session, observed):
            assert observed == packets
            return [replies.get(digest([args["inventory"]["plan"], "embeddings", p["request"]])) for p in observed]

    assert subject.producer.Study.vectors(Replay(), None) == saved
    assert value.vectors.index_digest == idx.digest and value.metadata["pooled_inputs"] == 3
    assert value.metadata["planned_chunks"] > 3 and value.metadata["full_input_tokens"] > 22_000
    assert value.metadata["retained_pool_and_missing_partition_reproduced"] is True
    assert value.metadata["new_model_calls"] == value.metadata["retained_status_or_cost_changes"] == 0
    assert value.metadata["profile_plan_and_tokenizer_implementation_independently_verified"] is False
    assert all("request_sha256" not in p for p in packets)


@pytest.mark.parametrize("status", ["unattempted", "unreturned", "opaque", "invalid", "model_missing"])
def test_missing_or_failed_tasks_stay_missing_without_repair_or_retry(status):
    item = fixture(statuses={0: status})
    value = verify(item)
    assert value.metadata["pooled_inputs"] == 0 and value.metadata["missing_inputs"] == 3
    label = "held" if status in {"opaque", "model_missing"} else status
    assert value.metadata["task_statuses"][label] == 1
    assert value.metadata["embedding_retries"] == 0


def test_missing_middle_chunks_do_not_pool_a_partial_article_but_other_inputs_survive():
    item = fixture(lengths=(210000, 1000), statuses={1: "invalid"})
    value = verify(item)
    assert value.metadata["planned_packet_occurrences"] == 3
    assert value.metadata["pooled_inputs"] == 1 and value.metadata["missing_inputs"] == 1
    assert value.vectors.present == bytes([0, 1])


def test_exact_wire_duplicate_packet_occurrences_reuse_one_original_attempt():
    value = verify(fixture(lengths=(410000,)))
    assert value.metadata["exact_wire_reused_occurrences"] > 0
    assert value.metadata["planned_packet_occurrences"] > value.metadata["unique_request_tasks"]
    assert len(value.metadata["verified_task_provenance"]) == value.metadata["unique_request_tasks"]
    assert value.metadata["pooled_inputs"] == 1 and value.metadata["new_model_calls"] == 0


def test_real_offline_cl100k_public_vocabulary_reconstructs_synthetic_full_input():
    # Hash-verified public tokenizer cache only; no corpus or model access.
    encoder = subject.producer.offline_tokenizer()
    item = fixture(lengths=(60000,), encoder=encoder)
    value = verify(item)
    tokens = encoder.encode(canonical({k: item[1][0][k] for k in ("title", "body")}), disallowed_special=())
    assert value.metadata["planned_chunks"] == 2
    assert value.metadata["full_input_tokens"] == len(tokens)
    assert item[4][0]["request"]["input"][0] == tokens[:6000]
    assert value.metadata["verified_task_provenance"][0]["observed_model"] == "text-embedding-3-large"


def test_existing_scoped_inventory_artifact_mapping_works_only_while_context_open():
    from final_validation_inventory import ScopedArtifacts
    from newsresearch.common import AuditError

    item = fixture()
    raw = item[3]["artifacts"]

    class SyntheticSource:
        active = True

        def _active(self):
            if not self.active:
                raise AuditError("synthetic_scoped_source_closed")

        def artifact_bytes(self, reference):
            self._active()
            return raw[reference]

    source = SyntheticSource()
    item[3]["artifacts"] = ScopedArtifacts(source, raw, {})
    assert verify(item).metadata["pooled_inputs"] == 3
    source.active = False
    with pytest.raises(AuditError, match="synthetic_scoped_source_closed"):
        verify(item)


def test_empty_tokenizer_output_cannot_certify_full_canonical_source_coverage():
    item = fixture()

    class EmptyEncoder(SyntheticEncoder):
        def encode(self, text, *, disallowed_special):
            return []

    idx, documents, _, args, *_ = item
    with pytest.raises(ValueError, match="tokenizer_omitted_full_input"):
        subject.verify_embedding_provenance(idx, documents, EmptyEncoder(), **args)


def test_phase_creation_must_match_the_same_scoped_inventory_census():
    item = fixture()
    item[3]["inventory"]["phase_event_hashes"] = [digest("different-phase-event")]
    with pytest.raises(ValueError, match="phase_census_binding"):
        verify(item)


@pytest.mark.parametrize("fault", ["title", "tail", "order", "missing_source", "profile", "tokenizer", "vocabulary",
    "cutoff", "census_intent", "census_response", "phase_identity", "phase_event", "phase_artifact", "raw_artifact"])
def test_source_profile_census_and_immutable_binding_faults_fail_closed(fault):
    item = fixture()
    idx, documents, encoder, args, *_ = item
    if fault == "title":
        documents[0]["title"] += "changed"
    elif fault == "tail":
        documents[0]["body"] = documents[0]["body"][:-1]
    elif fault == "order":
        documents.reverse()
    elif fault == "missing_source":
        documents.pop()
    elif fault == "profile":
        args["profile"]["pooling"] = "unweighted"
    elif fault == "tokenizer":
        encoder.name = "other"
    elif fault == "vocabulary":
        args["tokenizer"]["vocabulary_sha256"] = digest("wrong")
    elif fault == "cutoff":
        args["inventory"]["source_head"][0] -= 1
    elif fault == "census_intent":
        args["inventory"]["intent_event_hashes"] = []
    elif fault == "census_response":
        args["inventory"]["record_ids"] = []
    elif fault == "phase_identity":
        args["phase_record"]["id"] = digest("wrong")
    elif fault == "phase_event":
        args["phase_creation_event"]["event_hash"] = digest("wrong")
    elif fault == "phase_artifact":
        args["bindings"]["phase_artifact"] = digest("wrong")
    else:
        ref = args["records"][0]["artifact"]
        args["artifacts"][ref] += b" "
    with pytest.raises(ValueError):
        subject.verify_embedding_provenance(idx, documents, encoder, **args)


@pytest.mark.parametrize("fault", ["token", "offset", "input_hash", "full_tokens", "chunk_order", "model", "dimensions"])
def test_rehashed_packet_cannot_change_original_full_input_or_chunk_coverage(fault):
    def mutate(packet):
        if fault == "token":
            packet["request"]["input"][0][-1] += 1
        elif fault == "offset":
            packet["chunks"][0]["token_start"] += 1
        elif fault == "input_hash":
            packet["chunks"][0]["exact_input_sha256"] = digest("wrong")
        elif fault == "full_tokens":
            packet["chunks"][0]["full_tokens"] -= 1
        elif fault == "chunk_order":
            packet["chunks"].reverse()
        else:
            packet["request"][fault] = "other" if fault == "model" else 2
    with pytest.raises(ValueError, match="exact_original_request_and_chunks"):
        verify(fixture(mutate_packet=mutate))


@pytest.mark.parametrize("fault", ["cost", "hold", "reserved", "parsed", "observed_model", "raw_text", "usage"])
def test_rehashed_response_cannot_change_vectors_model_usage_or_original_liabilities(fault):
    def mutate(row, envelope, census):
        if fault == "cost":
            row["cost_nanousd"] += 1
        elif fault == "hold":
            row["hold"] = True
        elif fault == "reserved":
            row["reserved_nanousd"] = 1
        elif fault == "parsed":
            parsed = deepcopy(subject.retained._json(census.artifacts[row["parsed"]]))
            parsed["vectors"][0][0] += 0.1
            row["parsed"] = census.put(parsed)
        else:
            envelope[{"observed_model": "model", "raw_text": "raw_response", "usage": "usage"}[fault]] = (
                "other" if fault == "observed_model" else {**envelope["raw_response"], "response_text": "{}"}
                if fault == "raw_text" else {"prompt_tokens": 0})
            row["response"] = census.put(envelope)
    with pytest.raises(ValueError):
        verify(fixture(mutate_response=mutate))
