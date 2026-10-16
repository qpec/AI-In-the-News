"""Source-free contract tests; these do not simulate semantic model quality."""

from __future__ import annotations

import copy
import hashlib

import pytest

from newsresearch.common import ResearchError
from newsresearch.luna_lead_answers import (
    EVENT_FIELDS,
    build_request,
    make_lead,
    validate_answer,
    validate_request,
)


def paragraph(source: str, text: str, start: int = 0) -> dict:
    return {"id": f"{source}-{start}", "source_id": source, "start": start, "end": start + len(text),
            "text": text, "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def lead(source: str) -> dict:
    return make_lead(source, "Metadata title, never passage evidence", None,
                     [paragraph(source, "Aster announced a model on Monday in Delft.")])


def answer(request: dict) -> dict:
    return {
        "group_label": "same_event", "rationale": "The supplied leads describe one announcement.",
        "events": [{"source_version": item["source_version"], "description": "Aster model announcement",
                    "action": "announced a model", "actors": ["Aster"], "event_date": "Monday",
                    "location": "Delft", "multiple_focal_events": False} for item in request["articles"]],
        "claims": [{"source_version": p["source_id"], "passage_id": p["id"], "quote": p["text"],
                    "supports": list(EVENT_FIELDS)} for p in request["evidence"]],
        "inspected_passage_ids": [p["id"] for p in request["evidence"]],
        "partitions": [[item["source_version"] for item in request["articles"]]], "relations": [],
    }


def test_exact_unicode_prefix_budget_and_parent_provenance() -> None:
    paragraphs = [paragraph("s1", "é" * 1000), paragraph("s1", "界" * 2200, 1002),
                  paragraph("s1", "Third paragraph omitted", 3204), paragraph("s1", "Fourth", 3230)]
    packet = make_lead("s1", "t" * 401, None, paragraphs)
    assert len(packet["title"]) == 400
    assert [len(p["text"]) for p in packet["passages"]] == [1000, 2000]
    assert packet["passages"][1]["start"] == 1002
    assert packet["passages"][1]["end"] == 3002
    assert packet["passages"][1]["parent_ref"] == {
        key: value for key, value in paragraphs[1].items() if key != "text"}
    assert "body" not in packet
    assert packet["coverage"] == {
        "input_nonempty_paragraphs": 4, "retained_paragraphs": 2, "omitted_paragraphs": 2,
        "retained_body_characters": 3000, "truncated": True, "title_truncated": True,
        "fullarticle_not_read": True}
    request = build_request(leads=[packet], versions={}, mode="article")
    validate_request(request)
    changed = copy.deepcopy(request)
    changed["articles"][0]["passages"][1]["text"] += "hidden body"
    with pytest.raises(ResearchError, match="slice_integrity"):
        validate_request(changed)
    for field, value in (("text_hash", "wrong"), ("source_id", "s2"), ("start", False)):
        invalid = copy.deepcopy(paragraphs)
        invalid[0][field] = value
        with pytest.raises(ResearchError, match="parent_source_or_hash"):
            make_lead("s1", None, None, invalid)


def test_group_all_member_citations_and_coverage_are_required() -> None:
    request = build_request(leads=[lead("s1"), lead("s2")], versions={"protocol": "method-v1"})
    result = answer(request)
    validated = validate_answer(request, result)
    assert validated["fullarticle_not_read"] is True
    assert validated["human_validated"] is False
    assert validated["evidence_references"][0]["source_start"] == 0
    for change, reason in (("title_quote", "quote_invalid"), ("missing_quote", "uncited_factual_field"),
                           ("missing_member", "incomplete_source_coverage"),
                           ("missing_passage", "incomplete_passage_coverage"),
                           ("missing_partition_member", "partition_coverage_invalid"),
                           ("multiple_focal_events", "decisive_event_anchors_required")):
        invalid = copy.deepcopy(result)
        if change == "title_quote":
            invalid["claims"][0]["quote"] = request["articles"][0]["title"]
        elif change == "missing_quote":
            invalid["claims"].pop()
        elif change == "missing_member":
            invalid["events"].pop()
        elif change == "missing_passage":
            invalid["inspected_passage_ids"].pop()
        elif change == "missing_partition_member":
            invalid["partitions"][0].pop()
        else:
            invalid["events"][0]["multiple_focal_events"] = True
        with pytest.raises(ResearchError, match=reason):
            validate_answer(request, invalid)


def test_anchor_requires_every_endpoint_and_never_claims_group_validation() -> None:
    request = build_request(leads=[lead("s1"), lead("s2"), lead("s3")], versions={},
                            mode="anchor", anchor_source="s1")
    result = answer(request)
    result.update(group_label="uncertain", partitions=[], relations=[
        {"source_version": "s2", "label": "same_event"},
        {"source_version": "s3", "label": "different_event"}])
    assert validate_answer(request, result)["status"] == "valid"
    invalid = copy.deepcopy(result)
    invalid["relations"].pop()
    with pytest.raises(ResearchError, match="anchor_coverage_invalid"):
        validate_answer(request, invalid)
    invalid = copy.deepcopy(result)
    invalid["group_label"] = "mixed_events"
    with pytest.raises(ResearchError, match="anchor_coverage_invalid"):
        validate_answer(request, invalid)
    single = build_request(leads=[make_lead("empty", None, None, [])], versions={}, mode="article")
    unknown = {"group_label": "uncertain", "rationale": "No retained lead text.", "claims": [],
               "inspected_passage_ids": [], "partitions": [], "relations": [], "events": [{
                   "source_version": "empty", **{k: [] if k == "actors" else "unknown" for k in EVENT_FIELDS},
                   "multiple_focal_events": True}]}
    assert validate_answer(single, unknown)["status"] == "valid"
    unknown["group_label"] = "same_event"
    with pytest.raises(ResearchError, match="single_article_group_claim_invalid"):
        validate_answer(single, unknown)
