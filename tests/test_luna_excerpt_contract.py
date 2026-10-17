"""Synthetic contract checks only: no corpus, model, accuracy or acceptance."""
from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SPEC = importlib.util.spec_from_file_location(
    "luna_excerpt_contract", Path(__file__).resolve().parents[1] / "scripts/luna_excerpt_contract.py")
assert SPEC is not None and SPEC.loader is not None
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)


def test_fictional_contract_is_valid_and_source_free():
    packet, output = contract.fictional_example()
    Draft202012Validator.check_schema(contract.load_schema())
    assert contract.validate_output(output, packet) == []
    assert "fictional" in packet["title"].lower()
    assert len(contract.contract_digest()) == 64


def test_every_schema_object_is_strict_and_requires_all_keys():
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["properties"]) == set(node["required"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(contract.load_schema())


@pytest.mark.parametrize("changes,expected", [
    ({"evidence_basis": "excerpts"}, "evidence_basis:mismatch"),
    ({"event": None}, "focus:single_requires_event"),
    ({"focus": "no_event"}, "focus:non_single_has_event_or_facts"),
    ({"reason": " "}, "reason:blank"),
    ({"entities_truncated": True}, "entities:overflow_without_cap"),
    ({"facts_truncated": True}, "facts:overflow_without_cap"),
])
def test_crossfield_rules(changes, expected):
    packet, output = contract.fictional_example()
    output.update(changes)
    assert expected in contract.validate_output(output, packet)


@pytest.mark.parametrize("focus", ["multiple", "no_event", "uncertain"])
def test_nonsingle_retains_entities_but_has_no_focal_event(focus):
    packet, output = contract.fictional_example()
    output.update(focus=focus, event=None, extra_facts=[])
    if focus == "multiple":
        output["focus_evidence"].append(output["entities"][0]["evidence"])
        assert "focus:multiple_needs_two_quotes" in contract.validate_output(output, packet)
        output["focus_evidence"][-1] = {"span_id": "body1", "quote": "The rollout covers 12 schools."}
    assert contract.validate_output(output, packet) == []


def test_exact_surface_grounding_is_separate_from_normalized_name():
    packet, output = contract.fictional_example()
    output["entities"][0]["normalized_name"] = "acme labs"
    assert contract.validate_output(output, packet) == []
    output["entities"][0]["surface"] = "acme labs"
    assert "entities.0:surface_not_in_own_quote" in contract.validate_output(output, packet)


def test_surface_must_be_in_own_quote_not_elsewhere_in_packet():
    packet, output = contract.fictional_example()
    output["entities"][0]["evidence"] = output["extra_facts"][0]["evidence"]
    assert "entities.0:surface_not_in_own_quote" in contract.validate_output(output, packet)


def test_unseen_normalization_is_rejected_without_mislabeling_paraphrase():
    packet, output = contract.fictional_example()
    output["event"]["summary"] = "A fictional technology launch took place."
    assert contract.validate_output(output, packet) == []
    output["entities"][0]["normalized_name"] = "Acme Incorporated"
    assert "entities.0:normalized_name_not_in_packet" in contract.validate_output(output, packet)


def test_quotes_cannot_splice_or_change_unicode():
    packet, output = contract.fictional_example()
    output["focus_evidence"][0] = {"span_id": "body1", "quote": "Fictional Acme Labs...12 schools."}
    assert "focus_evidence.0:quote_not_grounded" in contract.validate_output(output, packet)
    output["focus_evidence"][0]["quote"] = "Fictional Ácme Labs"
    assert "focus_evidence.0:quote_not_grounded" in contract.validate_output(output, packet)


@pytest.mark.parametrize("field,value,expected", [
    ("surface", "invented", "event.trigger:surface_not_in_own_quote"),
    ("evidence", {"span_id": "absent", "quote": "launched"}, "event.trigger:quote_not_grounded"),
])
def test_trigger_checks(field, value, expected):
    packet, output = contract.fictional_example()
    output["event"]["trigger"][field] = value
    assert expected in contract.validate_output(output, packet)


def test_title_is_distinct_from_body_evidence():
    packet, output = contract.fictional_example()
    output["focus_evidence"] = [{"span_id": "title", "quote": packet["title"]}]
    assert contract.validate_output(output, packet) == []
    resolved = contract.resolve_evidence(output["focus_evidence"][0], packet)
    assert resolved == [{"span_id": "title", "field": "title", "quote_start": 0,
                         "quote_end": len(packet["title"]), "source_start": 0,
                         "source_end": len(packet["title"])}]


def test_repeated_quote_returns_every_unicode_source_position():
    packet = {"title": "", "body_fully_covered": False,
              "spans": [{"span_id": "tail", "start": 500, "end": 508, "text": "é A é A "}]}
    resolved = contract.resolve_evidence({"span_id": "tail", "quote": "é A"}, packet)
    assert [item["source_start"] for item in resolved] == [500, 504]
    assert [item["source_end"] for item in resolved] == [503, 507]


@pytest.mark.parametrize("mutation,expected", [
    (lambda p: p.pop("body_fully_covered"), "packet:body_coverage_missing"),
    (lambda p: p.update(spans=[]), "packet:body_spans_missing"),
    (lambda p: p["spans"][0].update(end=1), "packet:span_0:invalid_offsets"),
    (lambda p: p["spans"][0].update(start=True), "packet:span_0:invalid_offsets"),
    (lambda p: p["spans"][0].update(span_id="title"), "packet:span_0:invalid_id"),
    (lambda p: p["spans"].append(deepcopy(p["spans"][0])), "packet:span_1:invalid_id"),
])
def test_packet_safety(mutation, expected):
    packet, output = contract.fictional_example()
    mutation(packet)
    assert expected in contract.validate_output(output, packet)


def test_overlapping_body_spans_are_rejected():
    packet, output = contract.fictional_example()
    packet["spans"].append({"span_id": "body2", "start": 0, "end": 1, "text": "F"})
    assert "packet:span_1:overlap_or_unsorted" in contract.validate_output(output, packet)


def test_refs_must_resolve_and_focal_participants_cannot_be_background():
    packet, output = contract.fictional_example()
    output["event"]["participants"][0]["entity_id"] = "e99"
    output["extra_facts"][0]["subject_entity_id"] = "e99"
    errors = contract.validate_output(output, packet)
    assert "event.participants:unknown_entity" in errors
    assert "extra_facts.0:unknown_entity" in errors
    output["event"]["participants"][0]["entity_id"] = "e1"
    output["entities"][0]["relation"] = "background"
    assert "event.participants:nonfocal_entity" in contract.validate_output(output, packet)


def test_duplicate_entity_ids_and_participants_are_rejected():
    packet, output = contract.fictional_example()
    output["entities"][1]["id"] = "e1"
    errors = contract.validate_output(output, packet)
    assert "entities:duplicate_id" in errors
    assert "entities:nonsequential_id" in errors
    packet, output = contract.fictional_example()
    output["event"]["participants"].append(output["event"]["participants"][0])
    assert "event.participants:duplicate_entity_role" in contract.validate_output(output, packet)


def test_entity_can_have_multiple_evidenced_roles():
    packet, output = contract.fictional_example()
    participant = deepcopy(output["event"]["participants"][0])
    participant["role"] = "affected"
    output["event"]["participants"].append(participant)
    assert contract.validate_output(output, packet) == []


def test_participant_role_evidence_must_be_grounded():
    packet, output = contract.fictional_example()
    output["event"]["participants"][0]["evidence"] = {"span_id": "body1", "quote": "Invented quote"}
    assert "event.participants.0:quote_not_grounded" in contract.validate_output(output, packet)


@pytest.mark.parametrize("target", ["event", "fact"])
def test_attribution_must_reference_a_visible_named_entity(target):
    packet, output = contract.fictional_example()
    item = output["event"] if target == "event" else output["extra_facts"][0]
    prefix = "event" if target == "event" else "extra_facts.0"
    item["attribution_entity_id"] = "e99"
    assert f"{prefix}:unknown_attribution" in contract.validate_output(output, packet)
    item["attribution_entity_id"] = "e1"
    if target == "event":
        assert contract.validate_output(output, packet) == []
    else:
        assert f"{prefix}:attribution_not_in_quote" in contract.validate_output(output, packet)


@pytest.mark.parametrize("field,value,expected", [
    ("value_number", float("nan"), "extra_facts.0:invalid_numeric_type"),
    ("value_number", float("inf"), "extra_facts.0:invalid_numeric_type"),
    ("value_number", 10 ** 1000, "extra_facts.0:invalid_numeric_type"),
    ("value_type", "text", "extra_facts.0:invalid_numeric_type"),
    ("unit_text", "people", "extra_facts.0.unit_text:surface_not_in_own_quote"),
    ("normalized_date", "2026-02-30", "extra_facts.0:invalid_date"),
])
def test_fact_types_and_grounding(field, value, expected):
    packet, output = contract.fictional_example()
    output["extra_facts"][0][field] = value
    assert expected in contract.validate_output(output, packet)


def test_relative_date_cannot_silently_acquire_a_year():
    packet, output = contract.fictional_example()
    text = "The rollout is planned for tomorrow."
    packet["spans"].append({"span_id": "tail", "start": 200, "end": 200 + len(text), "text": text})
    output["extra_facts"][0].update(value_type="date", value_text="tomorrow", value_number=None,
                                     unit_text=None, normalized_date="2026-01-13",
                                     evidence={"span_id": "tail", "quote": text})
    assert "extra_facts.0:date_year_not_explicit" in contract.validate_output(output, packet)


def test_hypothetical_focal_occurrence_is_invalid():
    packet, output = contract.fictional_example()
    output["event"]["claim_status"] = "hypothetical"
    assert "event:hypothetical_not_occurrence" in contract.validate_output(output, packet)


def test_facts_cannot_silently_attach_to_background_entities():
    packet, output = contract.fictional_example()
    output["entities"][0]["relation"] = "background"
    output["extra_facts"][0]["subject_entity_id"] = "e1"
    assert "extra_facts.0:nonfocal_subject" in contract.validate_output(output, packet)


def test_missing_or_failed_result_is_not_a_negative_label():
    packet, _ = contract.fictional_example()
    assert contract.validate_output(None, packet) == ["schema::type"]
    assert contract.validate_output({"focus": "failed"}, packet)


def test_unrequested_metadata_and_arbitrary_json_keys_are_rejected():
    packet, output = contract.fictional_example()
    output["publisher"] = "Invented Publisher"
    assert "schema::additionalProperties" in contract.validate_output(output, packet)


def test_cap_enforces_bounded_schema_output():
    packet, output = contract.fictional_example()
    output["entities"] = output["entities"] * 9
    assert "schema:entities:maxItems" in contract.validate_output(output, packet)
