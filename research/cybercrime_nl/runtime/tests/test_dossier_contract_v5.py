"""Deterministic extractive provenance and QA mechanics, no model/corpus use."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dossier_contract_v5 as contract
import summary_fidelity_contract_v2 as compatible
from newsresearch.common import ResearchError, canonical, digest


def documents():
    return [{"document_id": identity, "title": "  Exact Café 𝄞 title " + identity,
             "body": "  First paragraph.\r\nA lone line break.\r\n \t\r\n" + "β" * 2450 + "\n\nThird paragraph omitted.  "}
            for identity in ("original-one", "original-two")]


def card(docs=None, full=False):
    docs = docs or documents()
    build = contract.full_member_bundle if full else contract.build_evidence_card
    return build(docs, "dossier", digest(sorted(d["document_id"] for d in docs)), count_tokens=lambda _: 0)


def response(answer, model="gpt-6-luna"):
    return {"model": model, "status": "completed", "output": [{"type": "message", "content": [
        {"type": "output_text", "text": canonical(answer)}]}]}


def quality(label="supported"):
    return {"label": label, "reason": "Synthetic judgment without repaired prose.",
            "examined_source_ids": ["S1", "S2"],
            "affected_source_ids": [] if label == "supported" else ["S1"],
            "selected_span_ids": [] if label == "identity_missing" else ["S1.CB1"],
            "citations": [{"passage_id": "S1.B1"}, {"passage_id": "S2.T1"}]}


def decisions(packet, chosen="same_event"):
    answers = []
    for question in packet["request"]["questions"]:
        labels = [choice["value"] for choice in question["choices"]]
        label = "clear_single_event" if question["name"].startswith("clarity") else chosen
        answers.append({"type": "choice", "name": question["name"], "choice": label, "confidence": .99,
                        "probabilities": [{"value": v, "probability": 1.0 if v == label else 0.0} for v in labels]})
    return {"model": "gpt-6-luna", "answers": answers}


@pytest.mark.parametrize("text,expected", [
    ("one\r\ntwo", [(0, 8)]), ("one\ntwo", [(0, 7)]), ("one\rtwo", [(0, 7)]),
    ("one\r\n\r\ntwo", [(0, 7), (7, 10)]), ("one\n \t\ntwo", [(0, 7), (7, 10)]),
    (" \n\nfirst\n\nsecond  \n\n ", [(0, 10), (10, 21)]),
])
def test_paragraphs_preserve_atomic_crlf_lone_breaks_and_whitespace(text, expected):
    bounds = contract.body_paragraphs(text)
    assert bounds == expected
    assert "".join(text[start:end] for start, end in bounds) == text
    assert all(text[start:end].strip() for start, end in bounds)


@pytest.mark.parametrize("body", ["", " \r\n\t "])
def test_empty_body_explicitly_rejected_before_card_or_census(body):
    doc = {"document_id": "d", "title": "title", "body": body}
    with pytest.raises(ResearchError, match="document_incomplete"):
        contract.card_source_census(doc, count_tokens=len)
    with pytest.raises(ResearchError, match="document_incomplete"):
        card([doc])


def test_card_keeps_two_complete_paragraphs_all_sources_exact_title_and_provenance():
    docs = documents()
    before = deepcopy(docs)
    snapshot = card(docs)
    value = snapshot["card"]
    assert snapshot["representation_type"] == "evidence_card" and snapshot["card_version"] == digest(value)
    assert value["source_document_ids"] == [d["document_id"] for d in docs]
    for source, doc in zip(value["sources"], docs, strict=True):
        assert source["title"]["text"] == doc["title"]
        spans = source["body_paragraphs"]
        assert len(spans) == 2 and source["retained_body_characters"] > 2400
        assert "".join(s["text"] for s in spans) == doc["body"][:spans[-1]["end"]]
        assert "Third paragraph" not in "".join(s["text"] for s in spans)
        assert source["excerpted"] and not source["complete"]
        assert source["retained_characters"] == len(doc["title"]) + spans[-1]["end"]
        for span in [source["title"], *spans]:
            assert span["text"] == doc[span["field"]][span["start"]:span["end"]]
            assert span["text_sha256"] == contract._sha(span["text"])
            assert span["field_sha256"] == contract._sha(doc[span["field"]])
    assert contract.validate_card(snapshot)["card"] == value
    assert not snapshot["validation"]["semantic_sufficiency_verified"]
    assert docs == before


@pytest.mark.parametrize("body,selected,complete", [
    ("a" * 3000 + "\n\nsecond\n\nthird", 2, False),
    ("first\n\nsecond\n\n" + "c" * 2400 + "\n\nfourth", 3, False),
    ("one\nline\nonly" * 500, 1, True),
    ("first\n\nsecond", 2, True),
])
def test_minimum_two_and_target_never_cut_long_or_unseparated_paragraph(body, selected, complete):
    doc = {"document_id": "source", "title": "full title", "body": body}
    source = card([doc])["card"]["sources"][0]
    assert len(source["body_paragraphs"]) == selected
    assert source["complete"] is complete and source["excerpted"] is not complete
    if complete:
        assert "".join(s["text"] for s in source["body_paragraphs"]) == body


def test_numeric_census_uses_same_selection_and_exposes_no_source_or_ids():
    doc = documents()[0]
    numeric = contract.card_source_census(doc, count_tokens=len)
    source = card([doc])["card"]["sources"][0]
    assert all(type(value) is int for value in numeric.values())
    assert numeric["body_paragraphs"] == 3 and numeric["without_blankline_boundaries"] == 0
    assert numeric["retained_body_characters"] == source["retained_body_characters"]
    assert numeric["full_body_tokens"] == len(doc["body"]) and numeric["full_title_tokens"] == len(doc["title"])
    assert numeric["excerpted"] == 1 and numeric["full_body_retained"] == 0


@pytest.mark.parametrize("fault", ["text", "offset", "source_removed", "order", "version", "membership", "source_body"])
def test_card_tampering_missing_member_or_binding_fails(fault):
    snapshot = card()
    if fault == "text":
        snapshot["card"]["sources"][0]["body_paragraphs"][0]["text"] += " changed"
    elif fault == "offset":
        snapshot["card"]["sources"][0]["body_paragraphs"][0]["start"] = 1
    elif fault == "source_removed":
        snapshot["card"]["sources"].pop()
    elif fault == "order":
        snapshot["card"]["sources"].reverse()
    elif fault == "version":
        snapshot["card_version"] = "wrong"
    elif fault == "membership":
        snapshot["membership_revision"] = "wrong"
    else:
        snapshot["original_documents"][0]["body"] += " changed"
    with pytest.raises(ResearchError):
        contract.validate_card(snapshot)


def test_card_capacity_does_not_trim_members_and_old_summary_adapter_is_rejected():
    docs = documents()
    with pytest.raises(ResearchError, match="capacity"):
        contract.build_evidence_card(docs, "d", digest(sorted(d["document_id"] for d in docs)), count_tokens=len, max_tokens=1)
    oversized = [{"document_id": str(i), "title": "", "body": "body"} for i in range(65)]
    with pytest.raises(ResearchError, match="capacity"):
        card(oversized)
    with pytest.raises(ResearchError):
        contract.assignment_request(docs[0], [{"status": "valid", "summary": {}}], count_tokens=lambda _: 0)
    with pytest.raises(AttributeError):
        getattr(contract, "summary_request")


def test_assignment_preserves_source_boundaries_full_incoming_article_and_versions():
    snapshot = card()
    incoming = {"document_id": "incoming", "title": "full query", "body": "Entire query.\n\nNothing trimmed.  "}
    packet = contract.assignment_request(incoming, [snapshot], count_tokens=lambda _: 0)
    supplied = json.loads(packet["request"]["input"])
    assert supplied["article"] == incoming
    assert supplied["candidate_cards"][0] == contract.card_matching_view(snapshot)
    assert "candidate_summaries" not in supplied
    assert packet["bindings"]["dossier"]["card_version"] == snapshot["card_version"]
    assert all(contract.FOCUS_RULES in q["instructions"] for q in packet["request"]["questions"])
    parsed = contract.parse_decisions(packet, decisions(packet))
    assert parsed["answers"]["dossier_0"]["card_version"] == snapshot["card_version"]
    assert contract.assignment_outcome(packet, parsed, packet["bindings"])["route"] == "match"
    with pytest.raises(ResearchError, match="stale"):
        contract.assignment_outcome(packet, parsed, {})


def test_full_bundle_control_is_distinct_complete_and_cannot_create_memberships():
    abbreviated, full = card(), card(full=True)
    assert full["card_version"] != abbreviated["card_version"]
    assert full["card"]["diagnostic_control_only"] and full["card"]["complete"]
    for source, doc in zip(full["card"]["sources"], documents(), strict=True):
        assert "".join(s["text"] for s in source["body_paragraphs"]) == doc["body"]
    incoming = {"document_id": "incoming", "title": "q", "body": "query"}
    with pytest.raises(ResearchError, match="type_invalid"):
        contract.assignment_request(incoming, [full], count_tokens=lambda _: 0)
    packet = contract.full_member_assignment_request(incoming, [full], count_tokens=lambda _: 0)
    assert packet["phase"] == "assignment_full_member_control"
    parsed = contract.parse_decisions(packet, decisions(packet))
    with pytest.raises(ResearchError, match="cannot_create_membership"):
        contract.assignment_outcome(packet, parsed, packet["bindings"])


@pytest.mark.parametrize("full", [False, True])
def test_compact_wire_omits_only_audit_metadata_and_keeps_every_exact_span(full):
    snapshot = card(full=full)
    before = deepcopy(snapshot)
    view = contract.card_matching_view(snapshot, allow_full=full)
    assert view["projection_sha256"] == digest({k: v for k, v in view.items() if k != "projection_sha256"})
    assert view["card_version"] == snapshot["card_version"]
    assert view["card"]["source_document_ids"] == snapshot["card"]["source_document_ids"]
    for compact, original in zip(view["card"]["sources"], snapshot["card"]["sources"], strict=True):
        for key in ("document_id", "retained_body_characters", "total_body_characters", "complete", "excerpted"):
            assert compact[key] == original[key]
        for actual, span in zip([compact["title"], *compact["body_paragraphs"]],
                               [original["title"], *original["body_paragraphs"]], strict=True):
            assert actual == {key: span[key] for key in ("span_id", "document_id", "field", "start", "end", "text")}
        assert "source_binding" not in compact
    assert all(key not in view["card"] for key in ("paragraph_rule", "selection_rule", "member_bindings_sha256"))
    assert "text_sha256" not in canonical(view) and "field_sha256" not in canonical(view)
    assert len(canonical(view)) < len(canonical(snapshot["card"]))
    assert snapshot == before


def test_seed_keeps_full_original_articles_and_same_label_families_with_focus_rules():
    docs = documents()
    packet = contract.seed_request(docs, count_tokens=lambda _: 0)
    assert json.loads(packet["request"]["input"])["articles"] == docs
    assert all(contract.FOCUS_RULES in q["instructions"] for q in packet["request"]["questions"])
    assert "single common technical cause" in contract.FOCUS_RULES
    assert set(contract.parse_decisions(packet, decisions(packet))["answers"]) == set(packet["question_map"])


def reference_value(packet):
    answers = []
    for name, meta in packet["wire_question_map"].items():
        ids = [meta["document_id"]] if meta["kind"] == "clarity" else [meta["left"], meta["right"]]
        answers.append({"name": name, "label": "clear_single_event" if meta["kind"] == "clarity" else "uncertain",
                        "reason": "Synthetic source-grounded reference.",
                        "citations": [{"passage_id": identity + ".B1"} for identity in ids]})
    return {"answers": answers}


def test_v5_reference_same_focus_definition_blinded_full_sources_and_uncertainty_preserved():
    docs = documents()
    packet = contract.audit_request(docs, count_tokens=lambda _: 0)
    supplied = json.loads(packet["request"]["input"])
    assert set(supplied) == {"articles", "source_passage_catalog", "source_passage_catalog_sha256", "questions"}
    assert [d["title"] for d in supplied["articles"]] == [d["title"] for d in docs]
    assert [d["body"] for d in supplied["articles"]] == [d["body"] for d in docs]
    assert contract.FOCUS_RULES in packet["request"]["instructions"]
    assert all(contract.FOCUS_RULES in q["instructions"] for q in supplied["questions"])
    value = reference_value(packet)
    payload = response(value, "gpt-6-astra")
    before = deepcopy((packet, payload))
    parsed = contract.parse_audit(packet, payload)
    pair = next(a for a in parsed["answers"].values() if a["kind"] == "pair")
    assert pair["label"] == "uncertain" and pair["probability"] is None
    assert {c["document_id"] for c in pair["citations"]} == {d["document_id"] for d in docs}
    assert len(pair["selected_passage_locations"]) == 2
    assert parsed["wire_audit_sha256"] == digest(value)
    assert parsed["normalization"]["focus_rules_sha256"] == digest(contract.FOCUS_RULES)
    assert (packet, payload) == before


@pytest.mark.parametrize("fault", ["instruction", "question", "normalization", "catalog", "mapping", "model", "phase"])
def test_v5_reference_binds_actual_request_and_all_normalization_fields(fault):
    packet = contract.audit_request(documents(), count_tokens=lambda _: 0)
    payload = response(reference_value(packet), "gpt-6-astra")
    if fault == "instruction":
        packet["request"]["instructions"] = "Changed rule"
    elif fault == "question":
        supplied = json.loads(packet["request"]["input"])
        supplied["questions"][0]["instructions"] = "Changed rule"
        packet["request"]["input"] = canonical(supplied)
    elif fault == "normalization":
        packet["normalization"]["focus_rules_sha256"] = "changed"
    elif fault == "catalog":
        packet["source_passage_catalog"]["passages"][0]["text"] += " changed"
    elif fault == "mapping":
        packet["alias_to_original"]["S1"] = "wrong-source"
    elif fault == "model":
        payload["model"] = "gpt-6-luna"
    else:
        packet["phase"] = "summary"
    packet["request_sha256"] = digest(packet["request"])
    with pytest.raises(ResearchError):
        contract.parse_audit(packet, payload)


def test_v5_reference_requires_pair_citations_from_both_actual_sources_and_capacity():
    packet = contract.audit_request(documents(), count_tokens=lambda _: 0)
    value = reference_value(packet)
    value["answers"][-1]["citations"] = [{"passage_id": "S1.B1"}]
    with pytest.raises(ResearchError, match="incomplete_citations"):
        contract.parse_audit(packet, response(value, "gpt-6-astra"))
    with pytest.raises(ResearchError, match="capacity"):
        contract.audit_request(documents(), count_tokens=lambda _: 100, max_tokens=99)


@pytest.mark.parametrize("audit", [False, True])
@pytest.mark.parametrize("label", contract.QUALITY_LABELS)
def test_card_qa_blinded_fullsource_and_exact_provenance_with_supported_only(audit, label):
    docs, snapshot = documents(), card()
    snapshot.update(previous_label="PRIVATE_OLD_LABEL", previous_probability=.99, selection_stratum="PRIVATE_STRATUM")
    make = contract.card_quality_audit_request if audit else contract.card_quality_request
    parse = contract.parse_card_quality_audit if audit else contract.parse_card_quality
    packet = make(docs, snapshot, count_tokens=lambda _: 0)
    wire = json.loads(packet["request"]["input"])
    assert [d["body"] for d in wire["articles"]] == [d["body"] for d in docs]
    assert [d["title"] for d in wire["articles"]] == [d["title"] for d in docs]
    assert "PRIVATE" not in canonical(packet)
    assert "not paraphrase fidelity" in packet["request"]["instructions"]
    assert packet["card_snapshot"]["card"] == snapshot["card"]
    payload = response(quality(label), "gpt-6-astra" if audit else "gpt-6-luna")
    before = deepcopy((packet, payload))
    result = parse(packet, payload)
    assert result["label"] == label and result["usable"] is (label == "supported")
    assert result["card_version"] == snapshot["card_version"]
    assert result["examined_source_ids"] == [d["document_id"] for d in docs]
    assert result["probability"] is result["probabilities"] is None
    assert not result["validation"]["semantic_sufficiency_verified"]
    assert (packet, payload) == before


@pytest.mark.parametrize("fault", ["unknown_span", "unknown_source", "duplicate_source", "duplicate_span", "span_source",
    "missing_examined", "missing_citations", "missing_supported_source", "missing_affected", "unknown_passage", "prose_field"])
def test_quality_references_schema_and_source_coverage_fail_closed(fault):
    packet = contract.card_quality_request(documents(), card(), count_tokens=lambda _: 0)
    value = quality()
    if fault == "unknown_span":
        value["selected_span_ids"] = ["S1.CB99"]
    elif fault == "unknown_source":
        value["affected_source_ids"] = ["S99"]
    elif fault == "duplicate_source":
        value["examined_source_ids"] = ["S1", "S1"]
    elif fault == "duplicate_span":
        value["selected_span_ids"] *= 2
    elif fault == "span_source":
        value.update(label="unclear_focus", affected_source_ids=["S2"])
    elif fault == "missing_examined":
        value["examined_source_ids"].pop()
    elif fault == "missing_citations":
        value["citations"] = []
    elif fault == "missing_supported_source":
        value["citations"].pop()
    elif fault == "missing_affected":
        value["label"] = "identity_missing"
    elif fault == "unknown_passage":
        value["citations"][0]["passage_id"] = "S9.B1"
    else:
        value["repaired_card"] = "Invented new prose"
    with pytest.raises(ResearchError):
        contract.parse_card_quality(packet, response(value))


def test_schema_compatibility_and_full_packet_binding_and_capacity():
    compatible.validate_wire_schema(contract.QUALITY_SCHEMA)
    assert "uniqueItems" not in canonical(contract.QUALITY_SCHEMA)
    docs, snapshot = documents(), card()
    packet = contract.card_quality_request(docs, snapshot, count_tokens=lambda _: 100)
    with pytest.raises(ResearchError, match="capacity"):
        contract.card_quality_request(docs, snapshot, count_tokens=lambda _: 101, max_tokens=100)
    for fault in ("card", "binding", "source", "model", "catalog"):
        changed = deepcopy(packet)
        if fault == "card":
            changed["card_snapshot"]["card"]["sources"][0]["title"]["text"] += " changed"
        elif fault == "binding":
            changed["bindings"]["card_version"] = "wrong"
        elif fault == "source":
            changed["original_documents"][0]["body"] += " changed"
        elif fault == "model":
            changed["request"]["model"] = "gpt-6-astra"
        else:
            changed["source_passage_catalog"]["passages"][0]["text"] += " changed"
        with pytest.raises(ResearchError):
            contract.parse_card_quality(changed, response(quality()))
