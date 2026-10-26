"""Synthetic blinded-summary contract checks, not semantic/model validation."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as base
import summary_fidelity_contract as contract
from newsresearch.common import ResearchError, canonical, digest


def inputs():
    documents = [{"document_id": identity, "title": "  Café 𝄞 " + identity,
                  "body": "Full synthetic original.\r\nQuotation, whitespace\tand trailing spaces.  "}
                 for identity in ("original-one", "original-two")]
    claim = {"text": "Exact retained claim: alleged, not established; 𝄞.\nSecond line.", "citations": [
        {"document_id": document["document_id"], "field": "title", "quote": document["title"]}
        for document in documents]}
    summary = {"dossier_id": "opaque-dossier", "membership_revision": "opaque-revision",
        "source_document_ids": [document["document_id"] for document in documents],
        "event_title": deepcopy(claim), "overview": deepcopy(claim),
        "identity": {"scope": deepcopy(claim), "action": deepcopy(claim),
                     **{field: [] for field in base.IDENTITY_FIELDS}, "unknowns": ["No exact time established."]}}
    summary["identity"]["distinguishing_facts"] = [{"text": "A separate exact claim referring only to source two.",
        "citations": [{"document_id": documents[1]["document_id"], "field": "body",
                       "quote": "Quotation, whitespace\tand trailing spaces.  "}]}]
    snapshot = {"status": "valid", "summary": summary, "summary_version": digest(summary),
                "dossier_id": summary["dossier_id"], "membership_revision": summary["membership_revision"],
                "validation": base.validate_summary(summary, documents),
                "previous_luna_label": "PRIVATE_PRIOR_LABEL", "previous_probability": .61,
                "selection_stratum": "PRIVATE_SELECTION_STRATUM"}
    return documents, snapshot


def response(value, model=contract.MODEL):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": canonical(value)}]}]}


def answer(label="supported", citations=None):
    return {"label": label, "reason": "Specific synthetic rationale; S1.B1 stays literal reason text.",
            "claim_paths": ["/overview"] if label == "unsupported" else ["/identity"] if label == "identity_missing" else [],
            "examined_source_ids": ["S1", "S2"],
            "citations": citations if citations is not None else [{"passage_id": "S1.B1"}, {"passage_id": "S2.T1"}]}


def test_full_sources_and_all_claims_remain_exact_and_previous_judgments_are_blinded():
    documents, snapshot = inputs()
    before_documents, before_snapshot = deepcopy(documents), deepcopy(snapshot)
    packet = contract.request(documents, snapshot, count_tokens=len)
    supplied = json.loads(packet["request"]["input"])
    assert set(supplied) == {"articles", "source_passage_catalog", "source_passage_catalog_sha256", "summary", "summary_binding",
                             "summary_claim_paths"}
    assert base.summary_matching_view(supplied["summary"]) == base.summary_matching_view(snapshot["summary"])
    assert supplied["summary"]["source_document_ids"] == ["S1", "S2"]
    saved_claims = [snapshot["summary"][key] for key in ("event_title", "overview")]
    saved_claims += [snapshot["summary"]["identity"][key] for key in ("scope", "action")]
    wire_claims = [supplied["summary"][key] for key in ("event_title", "overview")]
    wire_claims += [supplied["summary"]["identity"][key] for key in ("scope", "action")]
    for saved, wire in zip(saved_claims, wire_claims, strict=True):
        assert wire["text"] == saved["text"]
        assert wire["citations"] == [{**citation, "document_id": f"S{index}"}
                                     for index, citation in enumerate(saved["citations"], 1)]
    distinguishing = supplied["summary"]["identity"]["distinguishing_facts"][0]
    assert distinguishing == {**snapshot["summary"]["identity"]["distinguishing_facts"][0], "citations": [
        {"document_id": "S2", "field": "body", "quote": "Quotation, whitespace\tand trailing spaces.  "}]}
    assert packet["normalization"]["attributed_summary_sha256"] == digest(supplied["summary"])
    assert "/identity/distinguishing_facts/0" in supplied["summary_claim_paths"]
    assert [d["title"] for d in supplied["articles"]] == [d["title"] for d in documents]
    assert [d["body"] for d in supplied["articles"]] == [d["body"] for d in documents]
    assert [d["document_id"] for d in supplied["articles"]] == ["S1", "S2"]
    assert "PRIVATE_PRIOR_LABEL" not in canonical(packet)
    assert "PRIVATE_SELECTION_STRATUM" not in canonical(packet)
    assert "previous_probability" not in canonical(packet)
    assert supplied["summary_binding"] == packet["bindings"]
    assert packet["bindings"]["summary_version"] == snapshot["summary_version"]
    assert packet["request"]["model"] == "gpt-6-astra" and packet["request"]["max_output_tokens"] == 4000
    assert packet["kind"] == "responses"
    assert documents == before_documents and snapshot == before_snapshot


def test_instruction_checks_reported_claims_and_available_essential_identity_evidence_only():
    assert "what the sources report, not independent truth" in contract.INSTRUCTIONS
    assert "present in the sources is omitted and is needed to distinguish this occurrence" in contract.INSTRUCTIONS
    assert "Facts absent from the sources are not summary omissions" in contract.INSTRUCTIONS
    assert "Incidental details are\nnot mandatory" in contract.INSTRUCTIONS
    assert "attributed allegation into asserted fact" in contract.INSTRUCTIONS
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len, max_output_tokens=2000)
    assert packet["request"]["max_output_tokens"] == 2000


def test_supported_requires_all_sources_and_expands_exact_locations_without_rewriting_raw_response():
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = answer()
    payload = response(value)
    original_packet, original_payload = deepcopy(packet), deepcopy(payload)
    parsed = contract.parse(packet, payload)
    assert parsed["label"] == value["label"] and parsed["reason"] == value["reason"]
    assert parsed["examined_source_ids"] == [d["document_id"] for d in documents]
    assert parsed["citations"][0] == {"document_id": documents[0]["document_id"], "field": "body", "quote": documents[0]["body"]}
    assert parsed["selected_passage_locations"][0]["end"] == len(documents[0]["body"])
    assert parsed["normalization"]["catalog_sha256"] == digest(packet["source_passage_catalog"])
    assert parsed["summary_version"] == snapshot["summary_version"]
    assert parsed["validation"]["all_sources_cited"]
    assert parsed["validation"]["source_examination_is_self_reported"]
    assert not parsed["validation"]["semantic_entailment_verified"]
    assert not parsed["human_validated"] and parsed["probability"] is None
    assert packet == original_packet and payload == original_payload
    with pytest.raises(ResearchError, match="supported_source_coverage"):
        contract.parse(packet, response(answer(citations=[{"passage_id": "S1.B1"}])))


@pytest.mark.parametrize("label", ["unsupported", "identity_missing", "uncertain"])
def test_nonpositive_labels_allow_one_relevant_source_without_forcing_false_whole_group_support(label):
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = answer(label, [{"passage_id": "S2.B1"}])
    parsed = contract.parse(packet, response(value))
    assert parsed["label"] == label and len(parsed["citations"]) == 1
    assert parsed["citations"][0]["document_id"] == documents[1]["document_id"]
    assert not parsed["validation"]["all_sources_cited"]
    assert parsed["validation"]["all_sources_declared_examined"]
    if value["claim_paths"]:
        assert parsed["affected_claims"][0]["path"] == value["claim_paths"][0]
        assert parsed["affected_claims"][0]["value_sha256"] == digest(parsed["affected_claims"][0]["value"])


@pytest.mark.parametrize("label,paths", [("unsupported", []), ("identity_missing", []),
    ("unsupported", ["/identity"]), ("unsupported", ["/identity/nonexistent"]),
    ("unsupported", ["/identity/participants/999"]), ("unsupported", ["/overview", "/overview"]),
    ("unsupported", ["/dossier_id"])])
def test_affected_claim_paths_must_be_real_relevant_unique_anchors(label, paths):
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = answer(label)
    value["claim_paths"] = paths
    with pytest.raises(ResearchError):
        contract.parse(packet, response(value))


def test_affected_claim_preserves_original_quote_attribution_in_private_metadata():
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = answer("unsupported", [{"passage_id": "S2.B1"}])
    value["claim_paths"] = ["/identity/distinguishing_facts/0"]
    parsed = contract.parse(packet, response(value))
    assert parsed["affected_claims"][0]["value"] == snapshot["summary"]["identity"]["distinguishing_facts"][0]


@pytest.mark.parametrize("fault", ["unknown_passage", "case_change", "misattributed_source", "empty_citations",
                                 "omitted_examined", "duplicate_examined", "unknown_examined", "invented_label", "probability"])
def test_model_reference_or_coverage_errors_fail_without_quote_repair(fault):
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = answer("unsupported")
    if fault == "unknown_passage":
        value["citations"][0]["passage_id"] = "S99.B1"
    elif fault == "case_change":
        value["citations"][0]["passage_id"] = "s1.b1"
    elif fault == "misattributed_source":
        value["citations"][0]["document_id"] = "S2"
    elif fault == "empty_citations":
        value["citations"] = []
    elif fault == "omitted_examined":
        value["examined_source_ids"] = ["S1"]
    elif fault == "duplicate_examined":
        value["examined_source_ids"] = ["S1", "S1"]
    elif fault == "unknown_examined":
        value["examined_source_ids"] = ["S1", "S99"]
    elif fault == "invented_label":
        value["label"] = "probably_supported"
    else:
        value["probability"] = .99
    with pytest.raises(ResearchError):
        contract.parse(packet, response(value))


@pytest.mark.parametrize("fault", ["catalog", "alias", "claim", "normalization", "summary_binding", "wire", "request_hash"])
def test_packet_catalog_and_summary_claim_bindings_fail_closed(fault):
    documents, snapshot = inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    if fault == "catalog":
        packet["source_passage_catalog"]["passages"][0]["start"] = 1
    elif fault == "alias":
        packet["alias_to_original"]["S1"] = documents[1]["document_id"]
    elif fault == "claim":
        packet["summary_snapshot"]["summary"]["overview"]["text"] += " changed"
    elif fault == "normalization":
        packet["normalization"]["catalog_sha256"] = "changed"
    elif fault == "summary_binding":
        packet["bindings"]["membership_revision"] = "changed"
    elif fault == "wire":
        packet["request"]["input"] += " "
    else:
        packet["request_sha256"] = "changed"
    with pytest.raises(ResearchError):
        contract.parse(packet, response(answer()))


def test_original_snapshot_version_and_full_input_capacity_and_response_completion_are_required():
    documents, snapshot = inputs()
    changed = deepcopy(snapshot)
    changed["summary_version"] = "wrong"
    with pytest.raises(ResearchError, match="snapshot_binding"):
        contract.request(documents, changed, count_tokens=len)
    packet = contract.request(documents, snapshot, count_tokens=len)
    with pytest.raises(ResearchError, match="packet_capacity"):
        contract.request(documents, snapshot, count_tokens=len, max_tokens=packet["input_tokens_proxy"] - 1)
    for payload in (response(answer(), "gpt-6-luna"), {**response(answer()), "status": "incomplete"},
                    {"model": contract.MODEL, "status": "completed", "output": [{"type": "message", "content": [
                        {"type": "refusal", "refusal": "Cannot establish evidence."}]}]}):
        with pytest.raises(ResearchError):
            contract.parse(packet, payload)
