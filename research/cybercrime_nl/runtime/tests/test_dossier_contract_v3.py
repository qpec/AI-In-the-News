"""Synthetic lossless passage evidence checks; no corpus or provider access."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as v1
import dossier_contract_v2 as v2
import dossier_contract_v3 as c
from newsresearch.common import ResearchError, canonical, digest


def documents():
    return [{"document_id": digest(identity), "title": "Café 𝄞 " + identity,
             "body": "  Full retained article.\r\nRepeated quote. Repeated quote.\t"} for identity in ("one", "two")]


def response(value, model=c.MODEL):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": canonical(value)}]}]}


def summary(packet):
    claim = {"text": "S1.B1 is literal claim text; never rewrite it.",
             "citations": [{"passage_id": f"{doc['document_id']}.T1"} for doc in packet["wire_documents"]]}
    return {**packet["bindings"], "source_document_ids": [doc["document_id"] for doc in packet["wire_documents"]],
            "event_title": deepcopy(claim), "overview": deepcopy(claim),
            "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                         **{field: [] for field in c.IDENTITY_FIELDS}, "unknowns": ["Exact time unknown."]}}


def audit(packet):
    answers = []
    for name, metadata in packet["wire_question_map"].items():
        ids = ([metadata["document_id"]] if metadata["kind"] == "clarity"
               else [metadata["left"], metadata["right"]])
        answers.append({"name": name, "label": "clear_single_event" if metadata["kind"] == "clarity" else "same_event",
                        "reason": "S1.B1 is unchanged reason text.",
                        "citations": [{"passage_id": f"{identity}.B1"} for identity in ids]})
    return {"answers": answers}


def test_lossless_bounded_catalog_covers_empty_title_unicode_crlf_and_all_whitespace():
    body = "𝄞é\u0301 " * 310 + "\r\n" + "x" * 1199 + "\r\n" + "\t " * 1400 + "尾😀\r\n  "
    docs = [{"document_id": "long", "title": "", "body": body}]
    catalog = c.source_passage_catalog(docs)
    assert catalog == c.source_passage_catalog(docs)
    assert catalog["fields"][0]["length"] == 0 and catalog["fields"][0]["passage_ids"] == []
    parts = catalog["passages"]
    assert "".join(p["text"] for p in parts) == body
    cursor = 0
    for number, part in enumerate(parts, 1):
        assert part["passage_id"] == f"S1.B{number}"
        assert part["start"] == cursor and part["end"] - cursor <= c.MAX_PASSAGE_CHARACTERS
        assert body[part["start"]:part["end"]] == part["text"]
        assert part["text_sha256"] == hashlib.sha256(part["text"].encode("utf-8")).hexdigest()
        assert body[part["end"] - 1:part["end"] + 1] != "\r\n"
        cursor = part["end"]
    assert cursor == len(body)


def test_exact_full_fields_rules_aliases_and_compact_wire_citations():
    docs = documents()
    packet = c.summary_request(docs, "dossier", "revision", count_tokens=len)
    supplied = json.loads(packet["request"]["input"])
    assert supplied["articles"] == packet["wire_documents"]
    for original, wire in zip(docs, supplied["articles"], strict=True):
        assert (original["title"], original["body"]) == (wire["title"], wire["body"])
    assert supplied["source_passage_catalog"] == packet["source_passage_catalog"]
    assert supplied["source_passage_catalog_sha256"] == digest(packet["source_passage_catalog"])
    assert v1.PAIR_RULES in packet["request"]["instructions"]
    assert v1.CLARITY_RULES in packet["request"]["instructions"]
    assert 150 <= len(c.SUMMARY_RULES.split()) <= 250
    assert packet["input_tokens_proxy"] == len(canonical(packet["request"]))
    schema = packet["request"]["text"]["format"]["schema"]
    assert schema["properties"]["overview"]["properties"]["citations"]["items"]["required"] == ["passage_id"]
    assert packet["request"]["max_output_tokens"] == 8320


def test_stable_original_passage_identity_survives_request_local_alias_reordering():
    docs = documents()
    first = c.summary_request(docs, "d", "r", count_tokens=lambda _: 0)
    second = c.summary_request(list(reversed(docs)), "d", "r", count_tokens=lambda _: 0)
    assert first["passage_source_bindings"]["S1.B1"] == second["passage_source_bindings"]["S2.B1"]
    assert first["normalization"]["catalog_sha256"] != second["normalization"]["catalog_sha256"]


def test_summary_expansion_preserves_claims_raw_inputs_and_original_schema_downstream():
    docs = documents()
    packet = c.summary_request(docs, "dossier", "revision", count_tokens=len)
    value = summary(packet)
    payload = response(value)
    before_packet, before_payload = deepcopy(packet), deepcopy(payload)
    parsed = c.parse_summary(packet, payload)
    assert parsed["summary"]["overview"]["text"] == value["overview"]["text"]
    assert parsed["summary"]["source_document_ids"] == packet["document_ids"]
    assert parsed["summary"]["overview"]["citations"] == [
        {"document_id": doc["document_id"], "field": "title", "quote": doc["title"]} for doc in docs]
    assert parsed["summary_version"] == digest(parsed["summary"])
    assert parsed["wire_summary_sha256"] == digest(value)
    assert parsed["validation"]["passage_bindings_exact"]
    assert not parsed["validation"]["semantic_entailment_verified"]
    assert not parsed["validation"]["human_validated"]
    assert parsed["validation"]["selected_passage_locations"][0]["start"] == 0
    assert parsed["normalization"]["catalog_sha256"] == digest(packet["source_passage_catalog"])
    assert packet == before_packet and payload == before_payload
    faithful = c.summary_faithfulness_request(docs, parsed, count_tokens=len)
    assert json.loads(faithful["request"]["input"])["summary"] == parsed["summary"]
    incoming = {"document_id": "new", "title": "", "body": "Full incoming evidence"}
    assigned = c.assignment_request(incoming, [parsed], count_tokens=len)
    assert assigned["bindings"]["dossier"]["summary_version"] == parsed["summary_version"]


@pytest.mark.parametrize("fault", ["catalog_text", "catalog_offset", "catalog_omission", "alias_mapping",
                                 "source_binding", "normalization", "wire_body", "questions", "request_hash"])
def test_packet_tampering_or_coverage_loss_fails_closed(fault):
    packet = c.summary_request(documents(), "d", "r", count_tokens=len)
    payload = response(summary(packet))
    if fault == "catalog_text":
        packet["source_passage_catalog"]["passages"][0]["text"] += " altered"
    elif fault == "catalog_offset":
        packet["source_passage_catalog"]["passages"][0]["start"] = 1
    elif fault == "catalog_omission":
        packet["source_passage_catalog"]["passages"].pop()
    elif fault == "alias_mapping":
        packet["alias_to_original"]["S1"] = packet["alias_to_original"]["S2"]
    elif fault == "source_binding":
        packet["passage_source_bindings"]["S1.B1"]["source_passage_sha256"] = "wrong"
    elif fault == "normalization":
        packet["normalization"]["catalog_sha256"] = "wrong"
    elif fault == "wire_body":
        packet["wire_documents"][0]["body"] += " altered"
    elif fault == "questions":
        packet["question_map"] = {"unexpected": {}}
    else:
        packet["request_sha256"] = "wrong"
    with pytest.raises(ResearchError, match="binding_mismatch"):
        c.parse_summary(packet, payload)


@pytest.mark.parametrize("fault", ["unknown_id", "case_change", "added_quote", "missing_source", "wrong_binding"])
def test_invalid_model_citations_do_not_get_repaired(fault):
    packet = c.summary_request(documents(), "d", "r", count_tokens=len)
    value = summary(packet)
    if fault == "unknown_id":
        value["overview"]["citations"][0]["passage_id"] = "S99.B1"
    elif fault == "case_change":
        value["overview"]["citations"][0]["passage_id"] = "s1.t1"
    elif fault == "added_quote":
        value["overview"]["citations"][0]["quote"] = "unrequested paraphrase"
    elif fault == "missing_source":
        for claim in (value["overview"], value["event_title"], value["identity"]["scope"], value["identity"]["action"]):
            claim["citations"] = claim["citations"][:1]
    else:
        value["membership_revision"] = "changed"
    with pytest.raises(ResearchError):
        c.parse_summary(packet, response(value))


def test_complete_catalog_can_have_whitespace_passages_but_they_are_not_valid_citations():
    docs = documents()
    docs[0]["title"] = " \r\n\t"
    packet = c.summary_request(docs, "d", "r", count_tokens=len)
    assert packet["source_passage_catalog"]["passages"][0]["text"] == docs[0]["title"]
    with pytest.raises(ResearchError, match="unknown_or_empty"):
        c.parse_summary(packet, response(summary(packet)))


def test_audit_preserves_questions_labels_reasons_and_requires_each_answer_source():
    docs = documents()
    packet = c.audit_request(docs, count_tokens=len)
    prior = v2.audit_request(docs, count_tokens=len)
    assert packet["question_map"] == prior["question_map"]
    assert json.loads(packet["request"]["input"])["questions"] == json.loads(prior["request"]["input"])["questions"]
    value = audit(packet)
    payload = response(value, "gpt-6-astra")
    before = deepcopy(payload)
    parsed = c.parse_audit(packet, payload)
    assert payload == before
    for name, answer in parsed["answers"].items():
        assert answer["reason"] == "S1.B1 is unchanged reason text."
        assert answer["probability"] is None
        assert answer["selected_passage_locations"]
        assert answer["label"] == next(a["label"] for a in value["answers"] if a["name"] == name)
    assert {p["document_id"] for p in parsed["answers"]["pair_0"]["citations"]} == set(packet["document_ids"])
    bad = deepcopy(value)
    bad["answers"][-1]["citations"].pop()
    with pytest.raises(ResearchError, match="incomplete_citations"):
        c.parse_audit(packet, response(bad, "gpt-6-astra"))
    bad = deepcopy(value)
    bad["answers"][0]["citations"] = [{"passage_id": "S2.B1"}]
    with pytest.raises(ResearchError, match="citation_invalid"):
        c.parse_audit(packet, response(bad, "gpt-6-astra"))
    bad = deepcopy(value)
    bad["answers"][0]["label"] = "same_event"
    with pytest.raises(ResearchError, match="wrong_label_family"):
        c.parse_audit(packet, response(bad, "gpt-6-astra"))


def test_capacity_uses_complete_duplicate_evidence_and_never_truncates_or_repairs_incomplete_response():
    docs = documents()
    packet = c.summary_request(docs, "d", "r", count_tokens=len)
    assert packet["input_tokens_proxy"] > v2.summary_request(docs, "d", "r", count_tokens=len)["input_tokens_proxy"]
    with pytest.raises(ResearchError, match="packet_capacity"):
        c.summary_request(docs, "d", "r", count_tokens=len, max_tokens=packet["input_tokens_proxy"] - 1)
    payload = response(summary(packet))
    payload["status"] = "incomplete"
    with pytest.raises(ResearchError, match="response_incomplete"):
        c.parse_summary(packet, payload)
    assert c.seed_request is v1.seed_request
    assert c.summary_faithfulness_request is v1.summary_faithfulness_request
    assert c.parse_decisions is v1.parse_decisions


def decision(probabilities, *, label=None, kind="assignment", **metadata):
    return {"status": "valid", "label": label or max(probabilities, key=probabilities.get),
            "probabilities": probabilities, "kind": kind, **metadata}


@pytest.mark.parametrize("same,related,different,uncertain,expected", [
    (.90, .04, .04, .02, "positive"),
    (.00, .45, .50, .05, "nonmatch"),
    (.09, .40, .45, .06, "nonmatch"),
    (.42, .20, .33, .05, "unresolved"),
    (.57, .10, .30, .03, "unresolved"),
    (.74, .10, .10, .06, "unresolved"),
    (.76, .10, .10, .04, "unresolved"),
    (.00, .40, .40, .20, "unresolved"),
])
def test_assignment_combines_only_distinct_event_mass(same, related, different, uncertain, expected):
    answer = decision(dict(zip(c.PAIR_LABELS, (same, related, different, uncertain), strict=True)))
    before = deepcopy(answer)
    assert c.assignment_route(answer) == expected
    assert answer == before


def test_assignment_invalid_distributions_and_uncertain_clarity_fail_closed():
    for probabilities in ({}, {"same_event": 1}, dict(zip(c.PAIR_LABELS, (True, 0, 0, 0), strict=True)),
                          dict(zip(c.PAIR_LABELS, (float("nan"), 0, 0, 0), strict=True))):
        assert c.assignment_route({"status": "valid", "label": "same_event", "probabilities": probabilities}) == "unresolved"
    assert c.assignment_route({"status": "refusal"}) == "unresolved"
    with pytest.raises(ResearchError, match="threshold"):
        c.assignment_route({}, threshold=True)
    overlap = decision(dict(zip(c.PAIR_LABELS, (.5, .25, .25, 0), strict=True)))
    assert c.assignment_route(overlap, threshold=.5) == "unresolved"


def test_assignment_keeps_exact_wire_up_to_fifteen_and_preserves_conflicts_staleness_and_coverage():
    docs = documents()
    snapshots = []
    for index in range(16):
        packet = c.summary_request(docs, f"d{index}", "r", count_tokens=lambda _: 0)
        snapshots.append(c.parse_summary(packet, response(summary(packet))))
    incoming = {"document_id": "incoming", "title": "  Café\r\n", "body": "Full 𝄞 body\t"}
    packet = c.assignment_request(incoming, snapshots[:2], count_tokens=len)
    assert packet == v1.assignment_request(incoming, snapshots[:2], count_tokens=len)
    assert json.loads(packet["request"]["input"])["article"] == incoming
    assert len(c.assignment_request(incoming, snapshots[:15], count_tokens=lambda _: 0)["bindings"]) == 15
    with pytest.raises(ResearchError, match="candidate_count"):
        c.assignment_request(incoming, snapshots, count_tokens=lambda _: 0)
    clarity = decision(dict(zip(c.CLARITY_LABELS, (.9, .05, .03, .02), strict=True)), kind="clarity")
    positive = decision(dict(zip(c.PAIR_LABELS, (.9, .04, .04, .02), strict=True)), dossier_id="d0")
    negative = decision(dict(zip(c.PAIR_LABELS, (.0, .45, .5, .05), strict=True)), dossier_id="d1")
    parsed = {"answers": {"clarity_0": clarity, "dossier_0": positive, "dossier_1": negative}}
    outcome = c.assignment_outcome(packet, parsed, packet["bindings"])
    assert outcome["route"] == "match" and outcome["dossier_id"] == "d0"
    parsed["answers"]["dossier_1"] = {**positive, "dossier_id": "d1"}
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "conflict"
    parsed["answers"]["dossier_1"] = decision(
        dict(zip(c.PAIR_LABELS, (.74, .1, .1, .06), strict=True)), dossier_id="d1")
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "unresolved"
    with pytest.raises(ResearchError, match="stale"):
        c.assignment_outcome(packet, parsed, {})
    parsed["answers"].pop("dossier_1")
    with pytest.raises(ResearchError, match="answer_coverage"):
        c.assignment_outcome(packet, parsed, packet["bindings"])
    parsed["answers"]["clarity_0"] = decision(
        dict(zip(c.CLARITY_LABELS, (.8, .1, .05, .05), strict=True)), kind="clarity")
    assert c.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "unresolved_clarity"
