"""Synthetic immutable rows/artifacts only; no processing-owner or model access."""
from copy import deepcopy
from pathlib import Path
import sys
from types import MappingProxyType

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"
sys.path.insert(0, str(RUNTIME))
import final_validation_exposure as module  # noqa: E402
from dossier_transport import Invocation  # noqa: E402
from final_validation_design import pair_rank  # noqa: E402
from final_validation_frame import build_input_index  # noqa: E402
from newsresearch.common import canonical, digest  # noqa: E402


def docs(count=8):
    return [{"document_id": f"d{i}", "title": f"Synthetic title {i} Ω",
             "body": f"Synthetic full body {i}.\r\n\r\nSecond paragraph {i}.\nUnchanged whitespace. "}
            for i in range(count)]


def seed(*, old=False, count=3, pairs=None):
    maker = module.legacy if old else module.cards
    return maker.seed_request(docs(count), pairs=pairs, count_tokens=len, max_tokens=96_000)


def card_assignment():
    members = docs()[1:3]
    card = module.cards.build_evidence_card(members, "historical", digest(["d1", "d2"]),
                                          count_tokens=len, max_tokens=96_000)
    return module.cards.assignment_request(docs()[0], [card], count_tokens=len, max_tokens=96_000)


def summary_assignment():
    claim = {"text": "Synthetic claim", "citations": [{"document_id": "d1", "field": "title", "quote": docs()[1]["title"]}]}
    summary = {"dossier_id": "old", "membership_revision": digest(["d1", "d2"]),
               "source_document_ids": ["d1", "d2"], "event_title": deepcopy(claim), "overview": deepcopy(claim),
               "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                            **{name: [] for name in module.legacy.IDENTITY_FIELDS}, "unknowns": []}}
    snapshot = {"status": "valid", "summary": summary, "summary_version": digest(summary),
                "dossier_id": summary["dossier_id"], "membership_revision": summary["membership_revision"],
                "validation": {"citations_exact": True}}
    return module.legacy.assignment_request(docs()[0], [snapshot], count_tokens=len, max_tokens=96_000), summary


class Census:
    def __init__(self):
        self.artifacts, self.events, self.records, self.roles = {}, [], [], []
        self.plan, self.amendment = digest("plan"), digest("amendment")
        self.last_response = None

    def put(self, value):
        identity = digest(value)
        self.artifacts[identity] = canonical(value).encode()
        return identity

    def event(self, kind, value):
        row = {"seq": len(self.events) + 1, "event_id": f"event-{len(self.events)}", "session_id": "synthetic",
               "kind": kind, "time": "2026-10-24T00:00:00Z", "payload": value,
               "previous_hash": self.events[-1]["event_hash"] if self.events else "0" * 64}
        row["event_hash"] = digest(row)
        row["payload"] = canonical(value)
        self.events.append(row)
        return row

    def record(self, kind, key, value):
        artifact = self.put(value)
        identity = digest({"kind": kind, "key": key, "payload": artifact, "supersedes": None})
        event = self.event("record.created", {"record": identity, "kind": kind, "artifact": artifact})
        row = {"id": identity, "kind": kind, "logical_key": key, "payload": canonical(value),
               "artifact": artifact, "supersedes": None, "created_event": event["seq"]}
        self.records.append(row)
        return row

    def attempt(self, packet=None, *, state="ack", roles=("production",), affected=None, mutate_intent=None,
                mutate_response=None, mutate_envelope=None):
        packet = seed() if packet is None else deepcopy(packet)
        kind = packet.get("kind", "decisions")
        identity = f"attempt-{len(self.roles)}"
        request = packet["request"]
        value = {"attempt": identity, "task_key": digest([self.plan, kind, request]), "number": 1,
                 "batch": self.plan, "execution_amendment": self.amendment, "request": self.put(request),
                 "packet": self.put(packet), "dispatch": self.put(Invocation(request, identity, kind).manifest()),
                 "phase": packet["phase"], "category": "main", "reserved_nanousd": 1000,
                 "started_at": "2026-10-24T00:00:00Z"}
        if mutate_intent:
            mutate_intent(value)
        self.event("model.attempt.intended", value)
        self.roles.append({"attempt": identity, "roles": None if roles is None else list(roles),
                           "evidence_ids": [digest(["verified_role", identity])], "affected_document_ids": affected})
        if state == "orphan":
            return value
        envelope = {"provider": "openai-decisions", "model": "gpt-6-luna", "request_id": identity,
                    "payload": {"model": "gpt-6-luna", "answers": [
                        {"name": q["name"], "type": "choice", "choice": "invalid_label", "probabilities": "bad"}
                        for q in request.get("questions", [])]},
                    "raw_response": {"http_status": 200, "dispatch_started": True}}
        if state in {"predispatch", "opaque"}:
            envelope.update(model=None, payload=None)
            envelope["raw_response"] = {"dispatch_started": state != "predispatch"}
        elif state == "partial":
            envelope["payload"]["answers"].pop()
        elif state == "error":
            envelope["payload"]["error"] = {"message": "not valid serving"}
        elif state == "wrong_model":
            envelope["payload"]["model"] = "other"
        elif state == "non2xx":
            envelope["raw_response"]["http_status"] = 503
        elif state == "refusal":
            for answer in envelope["payload"]["answers"]:
                answer["type"] = "refusal"
        if mutate_envelope:
            mutate_envelope(envelope)
        response = {"plan": self.plan, **{k: value[k] for k in (
            "attempt", "task_key", "phase", "category", "packet", "request", "execution_amendment")},
            "response": self.put(envelope), "parsed": None, "cost_nanousd": None if state == "opaque" else 500,
            "reserved_nanousd": 1000, "hold": state == "opaque", "validation_error": "dossier_probability_invalid",
            "http_status": envelope["raw_response"].get("http_status"), "at": "2026-10-24T00:00:00Z"}
        if mutate_response:
            mutate_response(response)
        self.last_response = self.record("cyber_dossier_response", value["task_key"], response)
        return value

    def revalidation(self):
        row = self.last_response
        value = module._json(self.artifacts[row["artifact"]])
        result = {"source_response_record": row["id"], "source_response_record_sha256": digest({**value, "_record_id": row["id"]}),
            "parent_plan": self.plan, "parent_execution_amendment": self.amendment, "task_key": value["task_key"],
            "source_attempt": value["attempt"], **{"source_" + k: value[k] for k in ("packet", "request", "response")},
            "status": "valid", "original_rows_unchanged": True, "model_calls": 0, "cost_nanousd": 0,
            "normalization_version": "seed-question-map-in-retained-request-list-order-v1",
            "canonical_packet_sha256": value["packet"], "request_sha256": value["request"],
            "source_validation_error": value["validation_error"], "parsed": self.put({"status": "valid"})}
        return self.record("cyber_dossier_seed_revalidation", row["id"], result)

    def arguments(self, *, complete=True, gaps=None):
        head = [self.events[-1]["seq"], self.events[-1]["event_hash"]]
        index = build_input_index([{"document_id": d["document_id"], "input_sha256": digest({"title": d["title"], "body": d["body"]}),
                                    "article_row_ids": ["a" + d["document_id"]]} for d in docs()],
                                  {d["document_id"]: None for d in docs()}, bindings={"source_head": digest(head),
                                    "final_report": digest("final"), "input_manifest": digest("inputs")})
        role = {"source_id": "synthetic-owner", "source_head": head, "plan": self.plan,
                "input_index_digest": index.digest, "attempts": self.roles}
        inventory = {k: role[k] for k in ("source_id", "source_head", "plan", "input_index_digest")}
        inventory.update(amendments=[self.amendment], complete=complete, gaps=gaps or [],
            intended_event_hashes=[r["event_hash"] for r in self.events if r["kind"] == "model.attempt.intended"],
            response_record_ids=[r["id"] for r in self.records if r["kind"] == "cyber_dossier_response"],
            derived_record_ids=[r["id"] for r in self.records if r["kind"] == "cyber_dossier_seed_revalidation"],
            role_artifact=self.put(role), evidence_sha256=digest("upstream-source-census-evidence"))
        return index, {"events": self.events, "records": self.records, "artifacts": self.artifacts, "inventory": inventory}

    def run(self, **kwargs):
        index, arguments = self.arguments(**{k: kwargs.pop(k) for k in list(kwargs) if k in {"complete", "gaps"}})
        return module.reconstruct_exposure(index, **arguments, **kwargs)


def state(result, left, right):
    return result.projection.state(pair_rank(8, left, right))


@pytest.mark.parametrize("old", [False, True])
def test_full_canonical_seed_roundtrip_uses_wire_question_order_not_lexical_mapping(old):
    source = Census()
    source.attempt(seed(old=old, count=8))
    before = deepcopy(source.artifacts)
    result = source.run()
    assert len(result.projection.confirmed_pairs) == 28
    assert result.metadata["physical_intents"] == 1
    assert result.metadata["source_inventory_completeness_verified"] is False
    assert all(source.artifacts[k] == v for k, v in before.items())
    output = canonical({"metadata": result.metadata, "observations": result.observations})
    assert "Synthetic full body" not in output and "invalid_label" not in output and "probabilities" not in output


def test_exact_offered_historical_members_not_final_membership_and_mixed_reuse_roles():
    source = Census()
    source.attempt(card_assignment(), roles=("development", "production"))
    result = source.run()
    assert state(result, 0, 1) == state(result, 0, 2) == "exposed"
    assert state(result, 1, 2) == state(result, 0, 3) == "unexposed"
    assert result.projection.metadata["physical_attempts"] == 1
    assert result.projection.metadata["attempt_exposure"][0]["roles"] == ["development", "production"]


@pytest.mark.parametrize("response_state", ["orphan", "opaque", "partial", "error", "wrong_model", "non2xx"])
def test_uncertain_serving_is_not_false_negative_exposure(response_state):
    source = Census()
    source.attempt(state=response_state)
    result = source.run()
    assert state(result, 0, 1) == "unknown"
    assert state(result, 3, 4) == "unexposed"
    assert result.metadata["orphan_intents"] == (response_state == "orphan")


def test_refusal_or_invalid_probabilities_preserves_acknowledged_exposure():
    source = Census()
    source.attempt(state="refusal")
    assert state(source.run(), 0, 1) == "exposed"


def test_explicit_predispatch_is_none_but_serving_contradiction_is_integrity_error():
    source = Census()
    source.attempt(state="predispatch")
    assert state(source.run(), 0, 1) == "unexposed"
    broken = Census()
    broken.attempt(mutate_envelope=lambda e: e["raw_response"].update(dispatch_started=False))
    with pytest.raises(ValueError, match="predispatch_response_contradiction"):
        broken.run()


def test_unknown_role_is_never_inferred_production_or_absence_and_prepared_only_is_not_exposure():
    source = Census()
    source.attempt(seed(pairs=[("d0", "d1")]), roles=None, affected=["d7"])
    source.put(seed(count=4))  # Prepared packet alone is not an intended call.
    result = source.run()
    assert result.metadata["unclassified_pair_attempts"] == 1
    assert state(result, 0, 4) == "unknown"  # Uses verified packet endpoints, not mistaken supplied d7.
    assert state(result, 5, 6) == "unexposed"
    assert result.metadata["physical_intents"] == 1


def test_missing_artifacts_localize_only_with_bound_evidence_otherwise_global():
    source = Census()
    intent = source.attempt(card_assignment(), affected=["d0"])
    del source.artifacts[intent["packet"]]
    result = source.run()
    assert state(result, 0, 7) == "unknown" and state(result, 5, 6) == "unexposed"
    source.roles[0]["affected_document_ids"] = None
    assert state(source.run(), 5, 6) == "unknown"


def test_missing_response_and_unreconciled_inventory_keep_unknown_with_ack_dominance():
    source = Census()
    source.attempt(seed(pairs=[("d0", "d1")]))
    other = source.attempt(seed(pairs=[("d0", "d2")]))
    response = module._json(source.artifacts[source.last_response["artifact"]])
    del source.artifacts[response["response"]]
    result = source.run(complete=False)
    assert state(result, 0, 1) == "exposed"
    assert state(result, 0, 2) == state(result, 6, 7) == "unknown"
    assert other["attempt"] != "attempt-0"


def test_explicit_bounded_gap_keeps_complete_inventory_residual_unexposed():
    source = Census()
    source.attempt(seed(pairs=[("d0", "d1")]))
    result = source.run(gaps=[{"reason_code": "missing_history", "document_ids": ["d4"]}])
    assert state(result, 4, 7) == "unknown" and state(result, 6, 7) == "unexposed"


@pytest.mark.parametrize("available", [True, False])
def test_legacy_summary_members_require_exact_historical_snapshot_not_current_group(available):
    packet, summary = summary_assignment()
    source = Census()
    source.attempt(packet)
    catalog = {digest(summary): {"artifact": source.put({"saved": summary}), "path": ["saved"]}} if available else {}
    result = source.run(summary_catalog=catalog)
    assert state(result, 0, 1) == ("exposed" if available else "unknown")
    assert state(result, 0, 7) == ("unexposed" if available else "unknown")


def test_wrong_historical_summary_or_changed_literal_full_input_fails_closed():
    packet, summary = summary_assignment()
    source = Census()
    source.attempt(packet)
    summary["source_document_ids"] = ["d1"]
    catalog = {packet["bindings"]["old"]["summary_version"]: {"artifact": source.put(summary), "path": []}}
    with pytest.raises(ValueError, match="historical_summary_binding"):
        source.run(summary_catalog=catalog)
    changed = docs(3)
    changed[0]["body"] = changed[0]["body"].replace("\r\n", "\n")
    source = Census()
    source.attempt(module.cards.seed_request(changed, count_tokens=len, max_tokens=96_000))
    with pytest.raises(ValueError, match="full_input_digest_mismatch"):
        source.run()


def test_local_derived_revalidation_is_bound_to_original_without_extra_exposure_or_reclassification():
    source = Census()
    source.attempt(seed(count=8))
    original = deepcopy(source.last_response)
    source.revalidation()
    result = source.run()
    assert len(result.projection.confirmed_pairs) == 28
    assert result.projection.metadata["locally_revalidated_physical_attempts"] == 1
    assert result.metadata["new_exposures_from_revalidation"] == 0
    assert source.records[0] == original


@pytest.mark.parametrize("fault", ["packet_text", "question_identity", "dispatch", "response_request", "response_status",
                                   "plan", "amendment", "task_key"])
def test_binding_tampering_fails_even_when_new_artifact_hashes_are_self_consistent(fault):
    source = Census()
    packet = card_assignment()
    intent_change = response_change = None
    if fault == "packet_text":
        packet["documents"][0]["body"] += " changed"
    elif fault == "question_identity":
        packet["question_map"]["dossier_0"]["dossier_id"] = "wrong"
    elif fault == "dispatch":
        def intent_change(i):
            i.update(dispatch=source.put({"wire_sha256": i["request"]}))
    elif fault == "response_request":
        def response_change(r):
            r.update(request=digest("other"))
    elif fault == "response_status":
        def response_change(r):
            r.update(http_status=503)
    elif fault == "plan":
        def intent_change(i):
            i.update(batch=digest("other"))
    elif fault == "amendment":
        def intent_change(i):
            i.update(execution_amendment=digest("other"))
    elif fault == "task_key":
        def intent_change(i):
            i.update(task_key=digest("other"))
    source.attempt(packet, mutate_intent=intent_change, mutate_response=response_change)
    with pytest.raises(ValueError):
        source.run()


@pytest.mark.parametrize("fault", ["event_digest", "record_payload", "artifact_bytes", "response_missing_intent",
                                   "census_missing", "role_missing", "head_mismatch", "duplicate_intent"])
def test_immutable_row_and_census_binding_failures(fault):
    source = Census()
    intent = source.attempt()
    index, args = source.arguments()
    if fault == "event_digest":
        args["events"][0]["time"] = "changed"
    elif fault == "record_payload":
        args["records"][0]["payload"] = "{}"
    elif fault == "artifact_bytes":
        args["artifacts"][intent["packet"]] += b" "
    elif fault == "response_missing_intent":
        args["events"] = args["events"][1:]
        args["inventory"]["intended_event_hashes"] = []
    elif fault == "census_missing":
        args["inventory"]["response_record_ids"] = []
    elif fault == "role_missing":
        roles = module._json(args["artifacts"][args["inventory"]["role_artifact"]])
        roles["attempts"] = []
        args["inventory"]["role_artifact"] = source.put(roles)
    elif fault == "head_mismatch":
        args["inventory"]["source_head"][1] = digest("different-cutoff")
    elif fault == "duplicate_intent":
        args["events"].append(deepcopy(args["events"][0]))
    with pytest.raises(ValueError):
        module.reconstruct_exposure(index, **args)


def test_nonproduction_and_nonpair_reviews_supply_no_candidate_pairs():
    source = Census()
    source.attempt(roles=("development", "reference"))
    card_packet = card_assignment()
    snapshot = card_packet["candidate_cards"][0]
    quality = module.cards.card_quality_request(docs()[1:3], snapshot, count_tokens=len, max_tokens=96_000)
    source.attempt(quality)
    result = source.run()
    assert not result.projection.confirmed_pairs and not result.projection.uncertain_pairs
    assert result.metadata["ignored_nonpair_attempts"] == 1
    assert state(result, 0, 1) == "unexposed"


def test_physical_identity_is_owner_scoped_and_does_not_expose_original_attempt_ids():
    source = Census()
    intent = source.attempt()
    result = source.run()
    assert result.observations[0]["physical_attempt"] == digest(["synthetic-owner", intent["attempt"]])
    assert intent["attempt"] not in canonical(result.observations)


def test_readonly_artifact_mapping_is_supported_without_mutation_or_eager_iteration():
    source = Census()
    source.attempt()
    index, args = source.arguments()
    before = deepcopy(source.artifacts)
    args["artifacts"] = MappingProxyType(source.artifacts)
    result = module.reconstruct_exposure(index, **args)
    assert state(result, 0, 1) == "exposed" and source.artifacts == before


def frozen_embedding_packet():
    from run_dossiers_v5 import embedding_packets
    class Encoder:
        def encode(self, text, **kwargs):
            return list(text.encode())
    packet = embedding_packets(docs(3), Encoder())[0]
    assert packet["phase"] == packet["kind"] == "embeddings" and "request_sha256" not in packet
    return packet


def test_exact_frozen_embedding_packet_omits_redundant_hash_without_candidate_exposure():
    source = Census()
    packet = frozen_embedding_packet()
    intent = source.attempt(packet, roles=None)
    source.attempt(seed(pairs=[("d0", "d1")]))
    index, arguments = source.arguments()
    before = deepcopy(source.artifacts)
    result = module.reconstruct_exposure(index, **arguments)
    assert result.metadata["ignored_nonpair_attempts"] == 1
    assert result.metadata["physical_intents"] == 2
    assert state(result, 0, 1) == "exposed" and state(result, 0, 2) == "unexposed"
    assert source.artifacts == before
    assert digest(packet["request"]) == intent["request"]


@pytest.mark.parametrize("fault", ["wrong_hash", "null_hash", "wrong_kind", "changed_request"])
def test_embedding_hash_exception_does_not_accept_declared_or_wire_mismatch(fault):
    source = Census()
    packet = frozen_embedding_packet()
    if fault == "wrong_hash":
        packet["request_sha256"] = digest("wrong request")
    elif fault == "null_hash":
        packet["request_sha256"] = None
    elif fault == "wrong_kind":
        packet["kind"] = "responses"
    source.attempt(packet, roles=None)
    if fault == "changed_request":
        index, args = source.arguments()
        event = args["events"][0]
        intent = module._json(event["payload"].encode())
        changed = deepcopy(packet)
        changed["request"]["input"][0].append(0)
        intent["packet"] = source.put(changed)
        event["payload"] = intent
        event["event_hash"] = digest({k: v for k, v in event.items() if k != "event_hash"})
        event["payload"] = canonical(intent)
        # Stop before response comparison so this tests exact packet/request bytes.
        args["records"] = []
        args["events"] = [event]
        args["inventory"]["intended_event_hashes"] = [event["event_hash"]]
        args["inventory"]["response_record_ids"] = []
        with pytest.raises(ValueError, match="packet_intent_binding"):
            module.reconstruct_exposure(index, **args)
    else:
        with pytest.raises(ValueError, match="packet_intent_binding"):
            source.run()


@pytest.mark.parametrize("maker", [seed, card_assignment])
def test_pair_packets_still_require_their_declared_request_hash(maker):
    source = Census()
    packet = maker()
    del packet["request_sha256"]
    source.attempt(packet)
    with pytest.raises(ValueError, match="packet_intent_binding"):
        source.run()
