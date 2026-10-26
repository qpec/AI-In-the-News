"""Full-source v4 quality contracts: synthetic mechanics, not model accuracy."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract as base
import dossier_contract_v3 as v3
import dossier_contract_v4 as contract
import summary_fidelity_contract_v2 as fidelity
import test_summary_fidelity_contract as fixtures
from newsresearch.common import ResearchError, canonical, digest

ROUTES = [(contract.summary_quality_request, contract.parse_summary_quality, "gpt-6-luna", "summary_quality"),
          (contract.summary_quality_audit_request, contract.parse_summary_quality_audit, "gpt-6-astra", "summary_quality_audit")]


def test_targeted_generation_and_review_instructions_keep_original_rules_and_catalog():
    documents, snapshot = fixtures.inputs()
    documents[0]["body"] += "\r\n" + "  Café 𝄞 paragraph.\r\n" * 200
    packet = contract.summary_request(documents, "d", "r", count_tokens=lambda _: 0)
    prior = v3.summary_request(documents, "d", "r", count_tokens=lambda _: 0)
    assert packet["request"]["input"] == prior["request"]["input"]
    assert packet["source_passage_catalog"] == prior["source_passage_catalog"]
    assert v3.MAX_PASSAGE_CHARACTERS == packet["source_passage_catalog"]["max_passage_characters"] == 1200
    assert all(len(p["text"]) <= 1200 for p in packet["source_passage_catalog"]["passages"])
    text = " ".join(packet["request"]["instructions"].split())
    for phrase in ("Make each claim atomic", "every clause must be supported", "select multiple passages",
                   "Reporting, statement and publication dates must not become incident or action dates",
                   "Compatible broad and precise counts, or additional detail, are not contradictions",
                   "same referent, time and scope"):
        assert phrase in text
    assert base.PAIR_RULES in packet["request"]["instructions"] and base.CLARITY_RULES in packet["request"]["instructions"]
    qa = contract.summary_quality_request(documents, snapshot, count_tokens=lambda _: 0)
    assert qa["source_passage_catalog"] == packet["source_passage_catalog"]
    assert fidelity.INSTRUCTIONS in qa["request"]["instructions"]
    assert "every summary claim" in qa["request"]["instructions"]
    assert "that claim's original cited passage" in qa["request"]["instructions"]


@pytest.mark.parametrize("make_request,parse,model,phase", ROUTES)
def test_request_keeps_full_sources_exact_attributed_summary_and_blinds_prior_qa(make_request, parse, model, phase):
    documents, snapshot = fixtures.inputs()
    snapshot.update(summary_quality={"label": "PRIVATE_QA_LABEL", "reason": "PRIVATE_QA_REASON"},
                    summary_quality_audit={"label": "PRIVATE_ASTRA_LABEL"}, probability=.01)
    before = deepcopy((documents, snapshot))
    packet = make_request(documents, snapshot, count_tokens=len)
    original = fidelity.request(documents, snapshot, count_tokens=len, max_output_tokens=2000)
    assert packet["request"]["input"] == original["request"]["input"]
    assert packet["source_passage_catalog"] == original["source_passage_catalog"]
    assert packet["passage_source_bindings"] == original["passage_source_bindings"]
    assert packet["bindings"] == original["bindings"]
    assert packet["summary_snapshot"]["summary"] == snapshot["summary"]
    supplied = json.loads(packet["request"]["input"])
    assert [d["title"] for d in supplied["articles"]] == [d["title"] for d in documents]
    assert [d["body"] for d in supplied["articles"]] == [d["body"] for d in documents]
    assert "PRIVATE" not in canonical(packet)
    assert packet["phase"] == phase and packet["kind"] == "responses"
    assert packet["request"]["model"] == model and packet["request"]["max_output_tokens"] == 2000
    assert (documents, snapshot) == before
    assert packet["normalization"]["semantic_summary_repair"] is False
    assert packet["request_sha256"] == digest(packet["request"])


@pytest.mark.parametrize("make_request,parse,model,phase", ROUTES)
@pytest.mark.parametrize("label", fidelity.LABELS)
def test_labels_preserve_fidelity_validation_and_only_supported_is_usable(make_request, parse, model, phase, label):
    documents, snapshot = fixtures.inputs()
    packet = make_request(documents, snapshot, count_tokens=len)
    answer = fixtures.answer(label, None if label == "supported" else [{"passage_id": "S2.B1"}])
    response = fixtures.response(answer, model)
    before = deepcopy((packet, response, snapshot))
    parsed = parse(packet, response)
    original = fidelity.parse(fidelity.request(documents, snapshot, count_tokens=len), fixtures.response(answer))
    common_keys = ("status", "label", "reason", "claim_paths", "examined_source_ids", "citations", "dossier_id",
                   "membership_revision", "summary_version", "resolved_citations", "selected_passage_locations",
                   "affected_claims", "wire_result_sha256", "normalized_result_sha256")
    assert {k: parsed[k] for k in common_keys} == {k: original[k] for k in common_keys}
    assert parsed["usable"] == (label == "supported")
    assert parsed["reference_model"] == model and parsed["phase"] == phase
    assert parsed["probability"] is parsed["probabilities"] is None
    assert not parsed["human_validated"] and not parsed["validation"]["semantic_entailment_verified"]
    assert parsed["validation"]["source_examination_is_self_reported"]
    assert parsed["validation"]["summary_claims_and_attribution_unchanged"]
    assert (packet, response, snapshot) == before


@pytest.mark.parametrize("fault", ["duplicate_path", "empty_reason", "unknown_path", "whole_identity_unsupported",
    "unknown_passage", "misattributed_passage", "missing_examined", "duplicate_examined", "missing_supported_source",
    "invented_probability", "unsupported_missing_path", "identity_missing_no_path"])
def test_source_claim_schema_and_coverage_errors_never_become_usable(fault):
    documents, snapshot = fixtures.inputs()
    packet = contract.summary_quality_request(documents, snapshot, count_tokens=len)
    answer = fixtures.answer()
    if fault == "duplicate_path":
        answer["claim_paths"] = ["/overview", "/overview"]
    elif fault == "empty_reason":
        answer["reason"] = ""
    elif fault == "unknown_path":
        answer["claim_paths"] = ["/identity/nonexistent"]
    elif fault == "whole_identity_unsupported":
        answer.update(label="unsupported", claim_paths=["/identity"])
    elif fault == "unknown_passage":
        answer["citations"][0]["passage_id"] = "S99.B1"
    elif fault == "misattributed_passage":
        answer["citations"][0]["document_id"] = "S2"
    elif fault == "missing_examined":
        answer["examined_source_ids"].pop()
    elif fault == "duplicate_examined":
        answer["examined_source_ids"] = ["S1", "S1"]
    elif fault == "missing_supported_source":
        answer["citations"].pop()
    elif fault == "invented_probability":
        answer["probability"] = .99
    elif fault == "unsupported_missing_path":
        answer["label"] = "unsupported"
    else:
        answer["label"] = "identity_missing"
    with pytest.raises(ResearchError):
        contract.parse_summary_quality(packet, fixtures.response(answer, "gpt-6-luna"))


@pytest.mark.parametrize("fault", ["model", "phase", "summary", "binding", "catalog", "alias", "wire_hash", "instructions"])
def test_exact_quality_packet_and_snapshot_binding_is_required(fault):
    documents, snapshot = fixtures.inputs()
    packet = contract.summary_quality_request(documents, snapshot, count_tokens=len)
    if fault == "model":
        packet["request"]["model"] = "gpt-6-astra"
    elif fault == "phase":
        packet["phase"] = "summary_quality_audit"
    elif fault == "summary":
        packet["summary_snapshot"]["summary"]["overview"]["text"] += " repaired"
    elif fault == "binding":
        packet["bindings"]["summary_version"] = "wrong"
    elif fault == "catalog":
        packet["source_passage_catalog"]["passages"][0]["text"] += " changed"
    elif fault == "alias":
        packet["alias_to_original"]["S1"] = "wrong"
    elif fault == "wire_hash":
        packet["request_sha256"] = "wrong"
    else:
        packet["request"]["instructions"] += " Changed"
    with pytest.raises(ResearchError):
        contract.parse_summary_quality(packet, fixtures.response(fixtures.answer(), "gpt-6-luna"))


def test_schema_compatibility_and_phase_model_capacity_are_explicit():
    assert contract.QUALITY_SCHEMA == fidelity.SCHEMA
    fidelity.validate_wire_schema(contract.QUALITY_SCHEMA)
    assert "uniqueItems" not in canonical(contract.QUALITY_SCHEMA)
    assert fidelity.LOCAL_SCHEMA["properties"]["claim_paths"]["uniqueItems"]
    documents, snapshot = fixtures.inputs()
    packet = contract.summary_quality_request(documents, snapshot, count_tokens=len)
    audit = contract.summary_quality_audit_request(documents, snapshot, count_tokens=len)
    assert packet["request"]["input"] == audit["request"]["input"]
    assert packet["request"]["instructions"] == audit["request"]["instructions"]
    assert packet["request_sha256"] != audit["request_sha256"]
    with pytest.raises(ResearchError, match="capacity"):
        contract.summary_quality_request(documents, snapshot, count_tokens=len, max_tokens=packet["input_tokens_proxy"] - 1)
    for payload in (fixtures.response(fixtures.answer()),
                    {**fixtures.response(fixtures.answer(), "gpt-6-luna"), "status": "incomplete"}):
        with pytest.raises(ResearchError):
            contract.parse_summary_quality(packet, payload)
    with pytest.raises(ResearchError, match="binding_mismatch"):
        contract.parse_summary_quality_audit(packet, fixtures.response(fixtures.answer(), "gpt-6-luna"))
