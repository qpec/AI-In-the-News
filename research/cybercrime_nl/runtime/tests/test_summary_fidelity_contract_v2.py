"""Responses strict-subset repair without changed questions or weaker validation."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import summary_fidelity_contract as previous
import summary_fidelity_contract_v2 as contract
import test_summary_fidelity_contract as fixtures
from newsresearch.common import ResearchError, digest


def test_only_uniqueitems_changes_provider_wire_and_original_semantic_input_is_identical():
    documents, snapshot = fixtures.inputs()
    packet = contract.request(documents, snapshot, count_tokens=len, max_output_tokens=2000)
    original = previous.request(documents, snapshot, count_tokens=len, max_output_tokens=2000)
    expected = deepcopy(original["request"])
    expected["text"]["format"]["schema"]["properties"]["claim_paths"].pop("uniqueItems")
    assert packet["request"] == expected
    assert contract.INSTRUCTIONS == previous.INSTRUCTIONS
    assert contract.LOCAL_SCHEMA == previous.SCHEMA
    assert contract.SCHEMA["properties"]["reason"]["minLength"] == 1
    assert previous.SCHEMA["properties"]["claim_paths"]["uniqueItems"] is True
    assert packet["request_sha256"] == digest(expected) != original["request_sha256"]
    assert packet["normalization"]["provider_omitted_keywords_checked_locally"] == ["uniqueItems"]
    contract.validate_wire_schema(contract.SCHEMA)
    with pytest.raises(ResearchError, match="wire_schema_incompatible"):
        contract.validate_wire_schema(previous.SCHEMA)


@pytest.mark.parametrize("fault", ["uniqueItems", "composition", "patternProperties", "optional_field", "open_object"])
def test_provider_schema_guard_rejects_unsupported_or_nonstrict_shapes(fault):
    schema = deepcopy(contract.SCHEMA)
    if fault == "uniqueItems":
        schema["properties"]["claim_paths"]["uniqueItems"] = True
    elif fault == "composition":
        schema["allOf"] = []
    elif fault == "patternProperties":
        schema["patternProperties"] = {}
    elif fault == "optional_field":
        schema["required"].remove("reason")
    else:
        schema["additionalProperties"] = True
    with pytest.raises(ResearchError, match="wire_schema_incompatible"):
        contract.validate_wire_schema(schema)


@pytest.mark.parametrize("label", contract.LABELS)
def test_original_fidelity_source_and_claim_results_are_preserved(label):
    documents, snapshot = fixtures.inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    original_packet = previous.request(documents, snapshot, count_tokens=len)
    payload = fixtures.response(fixtures.answer(label))
    saved_packet, saved_payload = deepcopy(packet), deepcopy(payload)
    parsed = contract.parse(packet, payload)
    original = previous.parse(original_packet, payload)
    assert {key: value for key, value in parsed.items() if key not in {"normalization", "validation"}} == {
        key: value for key, value in original.items() if key not in {"normalization", "validation"}}
    assert parsed["validation"]["duplicate_claim_paths_checked_locally"]
    assert parsed["validation"]["full_original_local_schema_validated"]
    assert parsed["normalization"]["fidelity_contract"] == contract.METHOD
    assert packet == saved_packet and payload == saved_payload


def test_duplicate_claim_paths_rejected_explicitly_without_deduplication_or_schema_keyword():
    documents, snapshot = fixtures.inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = fixtures.answer("unsupported")
    value["claim_paths"] = ["/overview", "/overview"]
    payload = fixtures.response(value)
    saved = deepcopy(payload)
    with pytest.raises(ResearchError, match="duplicate_claim_path"):
        contract.parse(packet, payload)
    assert payload == saved


@pytest.mark.parametrize("fault", ["empty_reason", "unknown_path", "unknown_passage", "examined_source_missing", "supported_source_missing"])
def test_nonempty_source_claim_and_supported_coverage_checks_remain_strict(fault):
    documents, snapshot = fixtures.inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    value = fixtures.answer()
    if fault == "empty_reason":
        value["reason"] = ""
    elif fault == "unknown_path":
        value["claim_paths"] = ["/identity/imaginary"]
    elif fault == "unknown_passage":
        value["citations"][0]["passage_id"] = "S99.B1"
    elif fault == "examined_source_missing":
        value["examined_source_ids"].pop()
    else:
        value["citations"].pop()
    with pytest.raises(ResearchError):
        contract.parse(packet, fixtures.response(value))


def test_changed_wire_or_local_binding_is_rejected_and_capacity_still_measures_complete_request():
    documents, snapshot = fixtures.inputs()
    packet = contract.request(documents, snapshot, count_tokens=len)
    with pytest.raises(ResearchError, match="packet_capacity"):
        contract.request(documents, snapshot, count_tokens=len, max_tokens=packet["input_tokens_proxy"] - 1)
    for key in ("request_sha256", "bindings"):
        altered = deepcopy(packet)
        if key == "bindings":
            altered[key]["summary_version"] = "changed"
        else:
            altered[key] = "changed"
        with pytest.raises(ResearchError, match="binding_mismatch"):
            contract.parse(altered, fixtures.response(fixtures.answer()))
