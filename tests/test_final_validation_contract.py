"""Synthetic full-pair contract checks: no actual articles, owner or model I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, canonical, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_contract as contract  # noqa: E402


DOCS = [
    {"document_id": "private-retained-group-A/record-1.json", "title": "Synthetic report één",
     "body": "Synthetic café incident at site Z.\r\n\r\nThe report attributes the claim. " + "Complete retained evidence. " * 70},
    {"document_id": "private-unresolved-route-B/record-2.json", "title": "Synthetic report two",
     "body": "A synthetic second report describes site Z.\n\nLater details remain part of this full body.\nLone newline preserved."},
]


def packet(order=None, **kwargs):
    return contract.request(deepcopy(DOCS), order=order or [d["document_id"] for d in DOCS], count_tokens=lambda _: 3000, **kwargs)


def payload(label="same_event"):
    return {"examined_source_ids": ["S1", "S2"], "articles": [
        {"source_id": alias, "focus": "clear_single_event", "epistemic_uncertain": False,
         "identity_statement": "One synthetic reported occurrence.", "reason": "The source organizes its reporting around that occurrence.",
         "citations": [{"passage_id": alias + ".B1"}]} for alias in ("S1", "S2")],
        "relationship": {"assessment": "assessed", "label": label,
            "reason": "Synthetic comparison of the two supplied reports.",
            "citations": [{"passage_id": "S1.B1"}, {"passage_id": "S2.B1"}]}}


def provenance(p, **kwargs):
    return {"configured_model": contract.MODEL, "reasoning_effort": contract.REASONING_EFFORT,
        "fast_mode": False, "observed_model": contract.MODEL, "cli_version": "synthetic-cli-version",
        "request_sha256": p["request_sha256"], "stdin_sha256": p["stdin_sha256"],
        "terminal_complete": True, "tool_activity_detected": False, "transport_status": "returned", **kwargs}


def parse(value, p=None, **meta):
    p = p or packet()
    return contract.parse(p, value, provenance=provenance(p, **meta))


def test_wire_is_blinded_and_full_literal_articles_survive_frozen_order():
    p = packet(order=[DOCS[1]["document_id"], DOCS[0]["document_id"]])
    wire = json.loads(p["request"]["evidence"][0]["text"])
    assert wire["articles"] == [{**DOCS[1], "document_id": "S1"}, {**DOCS[0], "document_id": "S2"}]
    assert all(d["document_id"] not in p["stdin"] for d in DOCS)
    assert "text_sha256" not in p["request"]["evidence"][0]["text"]
    assert set(p["request"]) == {"inclusion", "evidence", "schema"}
    assert json.loads(p["stdin"])["task"] == contract.TASK
    assert json.loads(p["stdin"])["task"] != "Classify each independent article"
    for alias, original in zip(("S1", "S2"), (DOCS[1], DOCS[0]), strict=True):
        for field in ("title", "body"):
            rows = [r for r in p["source_passage_catalog"]["passages"] if r["document_id"] == alias and r["field"] == field]
            assert "".join(r["text"] for r in rows) == original[field]
            assert all(r["text"] == original[field][r["start"]:r["end"]] for r in rows)
    assert contract.FOCUS_RULES in p["request"]["inclusion"]["instruction"]
    assert contract.base.PAIR_RULES in p["request"]["inclusion"]["instruction"]


@pytest.mark.parametrize("fault", ["one_source", "duplicate", "missing_body", "blank_body", "bad_hash", "stratum", "model_label"])
def test_incomplete_or_unblinded_inputs_rejected(fault):
    docs = deepcopy(DOCS)
    if fault == "one_source":
        docs.pop()
    elif fault == "duplicate":
        docs[1]["document_id"] = docs[0]["document_id"]
    elif fault == "missing_body":
        del docs[1]["body"]
    elif fault == "blank_body":
        docs[1]["body"] = " \n"
    elif fault == "bad_hash":
        docs[1]["body_sha256"] = "0" * 64
    else:
        docs[1][fault] = "must never reach model"
    with pytest.raises(ResearchError):
        contract.request(docs, order=[d["document_id"] for d in docs], count_tokens=lambda _: 1)


@pytest.mark.parametrize("fault", ["wrong_order", "tokens", "bytes", "token_type", "limit"])
def test_capacity_or_order_failure_never_truncates_or_substitutes(fault, monkeypatch):
    docs = deepcopy(DOCS)
    original = deepcopy(docs)
    order = [d["document_id"] for d in docs]
    count, limit = 3000, 32000
    if fault == "wrong_order":
        order = [order[0], order[0]]
    elif fault == "tokens":
        count = 32001
    elif fault == "bytes":
        monkeypatch.setattr(contract, "MAX_INPUT_BYTES", 100)
    elif fault == "token_type":
        count = True
    else:
        limit = 96001
    with pytest.raises(ResearchError):
        contract.request(docs, order=order, count_tokens=lambda _: count, max_input_tokens=limit)
    assert docs == original


def test_exact_expansion_roundtrip_and_raw_payload_are_unchanged():
    p = json.loads(canonical(packet()))
    value = payload()
    before = canonical(value)
    result = parse(value, p)
    assert canonical(value) == before and result["raw_payload_sha256"] == digest(value)
    assert result["reference_available"] and result["reference_positive"] == 1
    for row, document in zip(result["articles"], DOCS, strict=True):
        assert row["document_id"] == document["document_id"]
        citation = row["citations"][0]
        assert citation["text"] == document[citation["field"]][citation["start"]:citation["end"]]
    assert result["source_examination_self_reported"] and not result["human_validated"]
    assert result["model_reference_not_ground_truth"] and not result["external_truth_verified"]
    assert "usage" not in result and "provider_dollar_cost" not in result


def test_dispatch_recomputes_frozen_token_proxy_and_does_not_claim_provider_usage():
    p = packet()
    assert contract.validate_for_dispatch(p, count_tokens=lambda _: 3000) == p
    with pytest.raises(ResearchError, match="dispatch_token_proxy_changed"):
        contract.validate_for_dispatch(p, count_tokens=lambda _: 3001)
    assert "Applicability: apply the identity-comparison rules only after both sources" in p["stdin"]


@pytest.mark.parametrize("fault", ["unknown_passage", "wrong_source", "duplicate_citation", "one_relation_source", "duplicate_article",
                                  "missing_examined", "invented_quote", "confidence", "model", "provenance", "blank_reason", "missing_identity"])
def test_invalid_evidence_coverage_or_model_fields_fail_closed(fault):
    value = payload()
    if fault == "unknown_passage":
        value["articles"][0]["citations"][0]["passage_id"] = "S1.B9999"
    elif fault == "wrong_source":
        value["articles"][0]["citations"][0]["passage_id"] = "S2.B1"
    elif fault == "duplicate_citation":
        value["articles"][0]["citations"] *= 2
    elif fault == "one_relation_source":
        value["relationship"]["citations"].pop()
    elif fault == "duplicate_article":
        value["articles"][1] = deepcopy(value["articles"][0])
    elif fault == "missing_examined":
        value["examined_source_ids"].pop()
    elif fault == "invented_quote":
        value["articles"][0]["citations"][0]["quote"] = "Invented unsupported source text"
    elif fault == "blank_reason":
        value["relationship"]["reason"] = "  "
    elif fault == "missing_identity":
        value["articles"][0]["identity_statement"] = None
    else:
        value[fault] = "model-authored forbidden value"
    with pytest.raises(ResearchError):
        parse(value)


@pytest.mark.parametrize("label,positive", [("same_event", 1), ("related_event", 0), ("different_event", 0), ("uncertain", None)])
def test_relationship_mapping_keeps_uncertainty_distinct(label, positive):
    result = parse(payload(label))
    assert result["mechanical_reference_positive"] == result["reference_positive"] == positive
    assert result["reference_available"] is (positive is not None)


@pytest.mark.parametrize("focus,uncertain,positive", [
    ("multiple_focal_events", False, 0), ("not_event_focused", False, 0),
    ("insufficient_information", False, None), ("clear_single_event", True, None),
    ("multiple_focal_events", True, None), ("not_event_focused", True, None),
])
def test_focus_failure_vs_epistemic_unknown_and_not_assessed(focus, uncertain, positive):
    value = payload()
    value["articles"][0].update(focus=focus, epistemic_uncertain=uncertain)
    value["relationship"].update(assessment="not_assessed", label=None)
    result = parse(value)
    assert result["reference_positive"] == positive
    assert result["relationship"]["assessment"] == "not_assessed" and result["relationship"]["label"] is None


def test_known_criterion_failure_determines_conjunction_even_if_other_source_unknown():
    value = payload()
    value["articles"][0]["focus"] = "multiple_focal_events"
    value["articles"][1].update(focus="insufficient_information", epistemic_uncertain=True, identity_statement=None)
    value["relationship"].update(assessment="not_assessed", label=None)
    assert parse(value)["reference_positive"] == 0


@pytest.mark.parametrize("fault", ["ineligible_assessed", "eligible_not_assessed", "not_assessed_label"])
def test_focus_relationship_inconsistency_not_repaired(fault):
    value = payload()
    if fault != "eligible_not_assessed":
        value["articles"][0]["focus"] = "multiple_focal_events"
    if fault != "ineligible_assessed":
        value["relationship"]["assessment"] = "not_assessed"
        if fault == "eligible_not_assessed":
            value["relationship"]["label"] = None
    with pytest.raises(ResearchError, match="focus_relationship_consistency"):
        parse(value)


@pytest.mark.parametrize("field", ["observed_model", "cli_version"])
def test_unavailable_provenance_retains_mechanical_judgment_but_not_usable_reference(field):
    result = parse(payload(), **{field: None})
    assert result["status"] == "mechanically_valid" and result["mechanical_reference_positive"] == 1
    assert result["reference_positive"] is None and not result["reference_available"]
    assert result["provenance_gaps"] == [field] and result["reference_state"] == "provenance_unavailable"


@pytest.mark.parametrize("change", [
    {"observed_model": "gpt-6-luna"}, {"configured_model": "gpt-6-luna"}, {"reasoning_effort": "low"},
    {"fast_mode": True}, {"request_sha256": "0" * 64}, {"stdin_sha256": "0" * 64},
    {"terminal_complete": False}, {"tool_activity_detected": True}, {"transport_status": "unknown"},
    {"prior_label": "same_event"},
])
def test_transport_or_identity_mismatch_fails_closed(change):
    with pytest.raises(ResearchError):
        parse(payload(), **change)


@pytest.mark.parametrize("fault", ["packet_digest", "source", "request", "catalog", "extra_field"])
def test_packet_tamper_rejected_even_if_outer_digest_recomputed(fault):
    p = packet()
    if fault == "source":
        p["documents"][0]["body"] += "different"
    elif fault == "request":
        p["request"]["inclusion"]["instruction"] += "changed"
    elif fault == "catalog":
        p["source_passage_catalog"]["passages"][0]["text"] = "changed"
    elif fault == "extra_field":
        p["stratum"] = "hidden"
    else:
        p["packet_sha256"] = "0" * 64
    if fault != "packet_digest":
        p["packet_sha256"] = digest({k: v for k, v in p.items() if k != "packet_sha256"})
    with pytest.raises(ResearchError):
        parse(payload(), p)
