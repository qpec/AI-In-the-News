"""Synthetic software checks only; no corpus, model or extraction-accuracy claims."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    import luna_event_contract_v2 as contract
finally:
    sys.path.pop(0)


def test_fictional_example_validates_and_all_literals_resolve():
    packet, output = contract.fictional_example()
    Draft202012Validator.check_schema(contract.load_schema())
    assert contract.validate_output(output, packet) == []
    assert "fictional" in packet["model_input"]["evidence"]["title"]["text"].lower()
    resolved = contract.resolve_output_literals(output, packet)
    assert len(resolved["event.participants.0"]) == 2
    assert {row["span_id"] for row in resolved["event.participants.0"]} == {"p1", "p2"}
    assert len(contract.contract_digest()) == 64
    assert packet["model_input"]["instructions"] == contract.load_prompt()
    assert packet["model_input"]["codebook"] == contract.CODEBOOK


def test_all_schema_objects_strict_and_all_properties_required():
    def visit(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(contract.load_schema())


@pytest.mark.parametrize("focus,reason", [
    ("multiple", "coequal_occurrences"), ("none", "no_particular_occurrence"),
    ("uncertain", "focus_unclear"), ("uncertain", "boundary_unclear"),
    ("uncertain", "insufficient_evidence"),
    ("uncertain", "insufficient_body"),
])
def test_nonsingle_outputs_are_minimal_and_multiple_can_have_one_reference(focus, reason):
    packet, output = contract.fictional_example()
    output.update(focus=focus, reason=reason, refs=["p1"], event=None)
    assert contract.validate_output(output, packet) == []
    assert contract.resolve_output_literals(output, packet) == {}
    assert set(output) == {"schema_version", "focus", "reason", "refs", "excluded", "event"}
    assert len(json.dumps(output, ensure_ascii=False, separators=(",", ":"))) < 300


@pytest.mark.parametrize("mutation,expected", [
    (lambda o: o.update(event=None), "focus:single_requires_event"),
    (lambda o: o.update(focus="multiple", reason="coequal_occurrences"), "focus:nonsingle_requires_null_event"),
    (lambda o: o.update(reason="boundary_unclear"), "focus:reason_mismatch"),
    (lambda o: o["event"].update(summary=" "), "event.summary:blank"),
    (lambda o: o["event"].update(participants_overflow=True), "event.participants:overflow_without_cap"),
    (lambda o: o["event"].update(facts_overflow=True), "event.facts:overflow_without_cap"),
    (lambda o: o["event"]["participants"][1].update(id="e1"), "event.participants:duplicate_id"),
    (lambda o: o["event"]["participants"][0].update(id="e7"), "event.participants:nonsequential_id"),
    (lambda o: o["event"]["facts"][0].update(subject="e12"), "event.facts.0:unknown_subject"),
    (lambda o: o["event"]["facts"][0].update(attributed_to="e12"), "event.facts.0:unknown_attribution"),
    (lambda o: o["event"]["facts"][0].update(attributed_to="e2"), "event.facts.0:attribution_missing_claim_source_role"),
    (lambda o: o["event"]["facts"].append(deepcopy(o["event"]["facts"][0])), "event.facts.1:duplicate_fact"),
    (lambda o: o["event"]["participants"][1]["roles"].append(deepcopy(o["event"]["participants"][1]["roles"][0])),
     "event.participants.1:duplicate_role"),
])
def test_crossfield_invariants(mutation, expected):
    packet, output = contract.fictional_example()
    mutation(output)
    assert expected in contract.validate_output(output, packet)


@pytest.mark.parametrize("surface", ["lumen council", "Lumen Council Incorporated", "Lumen...Council", "Lúmen Council"])
def test_entity_surface_must_be_exact_and_cannot_be_normalized(surface):
    packet, output = contract.fictional_example()
    output["event"]["participants"][0]["surface"] = surface
    assert "event.participants.0:surface_not_grounded" in contract.validate_output(output, packet)


@pytest.mark.parametrize("key", ["canonical_name", "quote", "start", "end", "normalized_name", "confidence"])
def test_unrequested_redundant_or_inferred_entity_fields_rejected(key):
    packet, output = contract.fictional_example()
    output["event"]["participants"][0][key] = "unsupported"
    assert "schema:event.participants.0:additionalProperties" in contract.validate_output(output, packet)


def test_each_literal_ref_must_contain_literal_but_roles_may_use_other_refs():
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p2"]
    assert "event.action:surface_absent_from_some_refs" in contract.validate_output(output, packet)
    output["event"]["action"]["refs"] = ["p1"]
    # Semantic role entailment is deliberately not established by this check.
    output["event"]["participants"][1]["roles"] = [{"role": "subject", "refs": ["p2"]}]
    assert contract.validate_output(output, packet) == []


def test_repeated_overlapping_occurrences_preserved_in_resolver():
    packet, output = contract.fictional_example()
    packet = contract.build_input({"title": "Fictional overlap", "body": "aaaa launched.\n\naaaa launched."})
    output["excluded"] = []
    output["event"].update(time=None, participants=[], facts=[])
    output["event"]["action"] = {"surface": "aa", "refs": ["p1", "p2"]}
    output["event"]["status_refs"] = ["p1"]
    assert contract.validate_output(output, packet) == []
    assert len(contract.resolve_output_literals(output, packet)["event.action"]) == 6


@pytest.mark.parametrize("mutation,expected", [
    (lambda o: o.update(refs=["p1", "p1"]), "refs:duplicate_reference"),
    (lambda o: o.update(refs=["p999"]), "refs:unknown_reference"),
    (lambda o: o.update(refs=["p3"]), "refs:excluded_evidence"),
    (lambda o: o["event"].update(status_refs=["p3"]), "event.status_refs:excluded_evidence"),
    (lambda o: o["event"]["participants"][0]["roles"][0].update(refs=["p3"]),
     "event.participants.0.roles.0.refs:excluded_evidence"),
    (lambda o: o["event"]["facts"][0].update(support_refs=["p999"]), "event.facts.0.support_refs:unknown_reference"),
    (lambda o: o["event"]["facts"][0].update(support_refs=["p3"]), "event.facts.0.support_refs:excluded_evidence"),
    (lambda o: o["event"]["facts"][0].update(support_refs=["p2", "p2"]), "event.facts.0.support_refs:duplicate_reference"),
    (lambda o: o["excluded"].append({"reason": "related_story", "refs": ["p2"]}), "excluded.1:duplicate_reason"),
    (lambda o: o["excluded"].append({"reason": "boilerplate", "refs": ["p3"]}), "excluded.1:duplicate_excluded_reference"),
])
def test_boundary_and_reference_invariants(mutation, expected):
    packet, output = contract.fictional_example()
    mutation(output)
    assert expected in contract.validate_output(output, packet)


@pytest.mark.parametrize("mutation,expected", [
    (lambda p: p["model_input"]["coverage"].update(truncated=True), "packet:incomplete_retained_body"),
    (lambda p: p["model_input"]["coverage"].update(retained_body_complete=False), "packet:incomplete_retained_body"),
    (lambda p: p["model_input"]["evidence"]["title"].update(text="Changed title"), "packet:model_evidence_map_mismatch"),
    (lambda p: p["model_input"]["evidence"]["paragraphs"][0].update(text="Changed body"), "packet:model_evidence_map_mismatch"),
    (lambda p: p["model_input"]["evidence"]["paragraphs"].reverse(), "packet:reference_order_invalid"),
    (lambda p: p["source_map"]["source_fields"]["body"].update(text="Changed map"), "packet:invalid_source_map_or_shape"),
    (lambda p: p["model_input"]["evidence"].update(paragraphs=[]), "packet:paragraphs_missing"),
    (lambda p: p["model_input"]["evidence"]["paragraphs"].pop(), "packet:reference_map_mismatch"),
])
def test_input_fidelity_and_coverage_are_not_assumed(mutation, expected):
    packet, output = contract.fictional_example()
    mutation(packet)
    assert expected in contract.validate_output(output, packet)


@pytest.mark.parametrize("status,truncated", [("incomplete", False), (None, False), ("failed", False), ("completed", True)])
def test_incomplete_provider_response_cannot_become_negative(status, truncated):
    packet, output = contract.fictional_example()
    output.update(focus="none", reason="no_particular_occurrence", event=None)
    assert contract.validate_output(output, packet, response_status=status, response_truncated=truncated) == [
        "response:not_completed"]


def test_output_caps_are_explicit_and_synthetic_overflow_is_not_silent_truncation():
    packet, output = contract.fictional_example()
    output["event"]["participants"] = [
        {**deepcopy(output["event"]["participants"][0]), "id": f"e{i}"} for i in range(1, 13)]
    output["event"].update(participants_overflow=True, facts=[])
    assert contract.validate_output(output, packet) == []
    output["event"]["participants"].append(deepcopy(output["event"]["participants"][0]))
    assert "schema:event.participants:maxItems" in contract.validate_output(output, packet)


def test_no_required_malware_type_and_unnamed_participant_supported():
    packet, output = contract.fictional_example()
    assert contract.CODEBOOK["entity_kinds"] == ["person", "organization", "group", "place", "product", "artifact", "object"]
    unnamed = output["event"]["participants"][2]
    assert unnamed["named"] is False
    assert contract.validate_output(output, packet) == []
    unnamed["kind"] = "malware"
    assert "schema:event.participants.2.kind:enum" in contract.validate_output(output, packet)


def test_fact_denial_is_separate_from_reported_event_and_preserves_attribution():
    packet, output = contract.fictional_example()
    body = packet["source_map"]["source_fields"]["body"]["text"]
    packet = contract.build_input({"title": "Fictional example", "body": body +
        "\n\nLumen Council denied that customer data was leaked."})
    denied = {"predicate": "customer_data_leak", "subject": "e1",
              "value": {"surface": "customer data was leaked", "refs": ["p4"]},
              "status": "denied", "attributed_to": "e1", "support_refs": ["p4"]}
    output["event"]["participants"][0]["roles"][2]["refs"].append("p4")
    output["event"]["facts"].append(denied)
    assert output["event"]["status"] == "reported"
    assert contract.validate_output(output, packet) == []
    assert contract.resolve_output_literals(output, packet)["event.facts.1.value"][0]["span_id"] == "p4"
    output["event"]["facts"].append({**deepcopy(denied), "status": "alleged"})
    # Structural checks preserve distinct claim statuses but do not establish
    # whether this new allegation is actually entailed by the cited paragraph.
    assert contract.validate_output(output, packet) == []


def test_cross_paragraph_fact_support_is_separate_from_literal_refs():
    packet, output = contract.fictional_example()
    body = packet["source_map"]["source_fields"]["body"]["text"]
    packet = contract.build_input({"title": "Fictional example", "body": body +
        "\n\nAn allegation said customer data was leaked.\n\nLumen Council denied that allegation."})
    output["event"]["participants"][0]["roles"][2]["refs"].append("p5")
    output["event"]["facts"].append({"predicate": "customer_data_leak", "subject": "e1",
        "value": {"surface": "customer data was leaked", "refs": ["p4"]},
        "status": "denied", "attributed_to": "e1", "support_refs": ["p4", "p5"]})
    assert contract.validate_output(output, packet) == []
    output["event"]["facts"][1]["value"]["refs"].append("p5")
    assert "event.facts.1.value:surface_absent_from_some_refs" in contract.validate_output(output, packet)


def test_all_eight_distinct_role_shapes_are_allowed_without_silent_three_role_cap():
    packet, output = contract.fictional_example()
    participant = output["event"]["participants"][0]
    participant["roles"] = [{"role": role, "refs": ["p1"]} for role in contract.CODEBOOK["role_kinds"]]
    # This synthetic test checks the output shape, not whether one entity can
    # semantically hold all these roles in a real occurrence.
    assert len(participant["roles"]) == 8
    assert contract.validate_output(output, packet) == []


def test_prompt_addresses_boundary_granularity_and_lexical_validation_limitations():
    prompt = contract.load_prompt()
    for required in ("related_story", "earnings", "underlying incidents", "role", "malware", "not model confidence",
                     "provisional caps", "not an independently established fact", "truncated/invalid JSON"):
        assert required.lower() in prompt.lower()


def test_saved_synthetic_example_validates():
    example = json.loads((ROOT / "examples/luna_event_output_v2.synthetic.json").read_text(encoding="utf-8"))
    assert example["synthetic"] is True
    assert contract.validate_output(example["output"], contract.build_input(example["article"])) == []
