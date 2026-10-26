"""Synthetic alias normalization tests; no source/model calls and no v1 edits."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as v1
import dossier_contract_v2 as c
from newsresearch.common import ResearchError, canonical, digest


def documents():
    return [{"document_id": digest(identity), "title": "Café 𝄞 " + identity,
             "body": "  Full retained article.\r\nRepeated quote. Repeated quote.\t"} for identity in ("one", "two")]


def response(value, model):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": canonical(value)}]}]}


def summary(packet):
    wire = packet["wire_documents"]
    claim = {"text": "S1 is a literal part of this fixture claim; do not rewrite text.",
             "citations": [{"document_id": doc["document_id"], "field": "title", "quote": doc["title"]}
                           for doc in wire]}
    return {**packet["bindings"], "source_document_ids": [doc["document_id"] for doc in wire],
            "event_title": deepcopy(claim), "overview": deepcopy(claim),
            "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                         **{field: [] for field in c.IDENTITY_FIELDS}, "unknowns": ["Exact time unknown."]}}


def audit(packet):
    docs = {doc["document_id"]: doc for doc in packet["wire_documents"]}
    values = []
    for name, metadata in packet["wire_question_map"].items():
        required = ([metadata["document_id"]] if metadata["kind"] == "clarity"
                    else [metadata["left"], metadata["right"]])
        values.append({"name": name, "label": "clear_single_event" if metadata["kind"] == "clarity" else "same_event",
                       "reason": "Synthetic reference evidence.", "citations": [
                           {"document_id": identity, "field": "body", "quote": "Repeated quote."}
                           for identity in required if identity in docs]})
    return {"answers": values}


def test_summary_aliases_validate_then_expand_without_modifying_text_or_raw_wire():
    docs = documents()
    packet = c.summary_request(docs, "dossier", "revision", count_tokens=len)
    assert packet["request"]["max_output_tokens"] == 8320
    assert packet["request"]["instructions"] == v1.SUMMARY_RULES
    wire = json.loads(packet["request"]["input"])["articles"]
    assert [doc["document_id"] for doc in wire] == ["S1", "S2"]
    assert [{k: doc[k] for k in ("title", "body")} for doc in wire] == [
        {k: doc[k] for k in ("title", "body")} for doc in docs]
    assert packet["document_ids"] == [doc["document_id"] for doc in docs]
    payload = response(summary(packet), c.MODEL)
    before_packet, before_payload = deepcopy(packet), deepcopy(payload)
    parsed = c.parse_summary(packet, payload)
    assert parsed["summary"]["source_document_ids"] == packet["document_ids"]
    assert parsed["summary_version"] == digest(parsed["summary"])
    assert parsed["wire_summary_sha256"] != parsed["summary_version"]
    assert parsed["summary"]["overview"]["text"] == summary(packet)["overview"]["text"]
    assert {entry["document_id"] for entry in parsed["validation"]["resolved_citations"]} == set(packet["document_ids"])
    assert parsed["normalization"]["version"] == c.NORMALIZATION_VERSION
    assert packet == before_packet and payload == before_payload
    # Existing downstream contracts consume the original-ID snapshot directly.
    faithful = c.summary_faithfulness_request(docs, parsed, count_tokens=len)
    assert json.loads(faithful["request"]["input"])["summary"] == parsed["summary"]
    assignment = c.assignment_request({"document_id": "new", "title": "", "body": "Full incoming article"},
                                      [parsed], count_tokens=len)
    assert assignment["bindings"]["dossier"]["summary_version"] == parsed["summary_version"]


@pytest.mark.parametrize("fault", ["mapping", "wire_body", "question_map", "unknown_alias", "original_id"])
def test_alias_binding_or_invalid_model_source_ids_fail_closed(fault):
    packet = c.summary_request(documents(), "dossier", "revision", count_tokens=len)
    value = summary(packet)
    if fault == "mapping":
        packet["alias_to_original"]["S1"] = packet["alias_to_original"]["S2"]
    elif fault == "wire_body":
        packet["wire_documents"][0]["body"] += "changed"
    elif fault == "question_map":
        packet["question_map"] = {"unexpected": {}}
    elif fault == "unknown_alias":
        value["overview"]["citations"][0]["document_id"] = "S99"
    else:
        value["source_document_ids"][0] = packet["document_ids"][0]
    with pytest.raises(ResearchError):
        c.parse_summary(packet, response(value, c.MODEL))


def test_alias_names_can_also_be_original_ids_without_recursive_replacement():
    docs = documents()
    docs[0]["document_id"], docs[1]["document_id"] = "S2", "S1"
    packet = c.summary_request(docs, "dossier", "revision", count_tokens=len)
    parsed = c.parse_summary(packet, response(summary(packet), c.MODEL))
    assert parsed["summary"]["source_document_ids"] == ["S2", "S1"]
    assert [c["document_id"] for c in parsed["summary"]["overview"]["citations"]] == ["S2", "S1"]
    with pytest.raises(ResearchError, match="duplicate_original"):
        c.summary_request([docs[0], docs[0]], "dossier", "revision", count_tokens=len)


def test_audit_maps_pair_identity_and_recomputes_original_citation_locations():
    docs = documents()
    packet = c.audit_request(docs, count_tokens=len)
    assert packet["request"]["max_output_tokens"] == 4000
    value = audit(packet)
    payload = response(value, "gpt-6-astra")
    original = deepcopy(payload)
    parsed = c.parse_audit(packet, payload)
    pair = parsed["answers"]["pair_0"]
    assert {pair["left"], pair["right"]} == {doc["document_id"] for doc in docs}
    assert pair["pair_id"] == v1.pair_id(docs[0]["document_id"], docs[1]["document_id"])
    assert pair["pair_id"] != packet["wire_question_map"]["pair_0"]["pair_id"]
    assert {entry["document_id"] for entry in pair["citations"]} == set(packet["document_ids"])
    assert all(len(entry["exact_occurrences"]) == 2 for entry in pair["resolved_citations"])
    assert payload == original
    value["answers"][-1]["citations"].pop()
    with pytest.raises(ResearchError, match="incomplete_citations"):
        c.parse_audit(packet, response(value, "gpt-6-astra"))
    bad_packet = deepcopy(packet)
    bad_packet["question_map"]["pair_0"]["left"] = "wrong"
    with pytest.raises(ResearchError, match="question_binding"):
        c.parse_audit(bad_packet, payload)


def test_unmodified_contracts_delegate_and_output_bounds_stay_explicit():
    assert c.seed_request is v1.seed_request
    assert c.assignment_request is v1.assignment_request
    docs = [{"document_id": f"article-{i}", "title": "Title", "body": "Full text"} for i in range(64)]
    assert c.summary_request(docs, "dossier", "revision", count_tokens=lambda _: 1)["request"]["max_output_tokens"] == 16000
    assert c.summary_request(docs[:2], "dossier", "revision", count_tokens=len,
                             max_output_tokens=9000)["request"]["max_output_tokens"] == 9000
    packet = c.summary_request(documents(), "dossier", "revision", count_tokens=len)
    truncated = response(summary(packet), c.MODEL)
    truncated["status"] = "incomplete"
    with pytest.raises(ResearchError, match="incomplete"):
        c.parse_summary(packet, truncated)
