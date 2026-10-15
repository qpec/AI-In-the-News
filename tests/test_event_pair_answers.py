from __future__ import annotations

import copy
import hashlib
import json

import pytest

from newsresearch.codex_provider import CodexCLIProvider, build_prompt
from newsresearch.common import ResearchError
from newsresearch.event_pair_answers import (
    EVENT_FIELDS, TASK_INSTRUCTION, TASK_KIND, WORKER_RULES, build_request, validate_answer,
)


def article(source, body):
    first, last = body.split("\n\n")
    return {"source_version": source, "body": body, "evidence": [
        {"id": source + "-p1", "source_id": source, "start": 0, "end": len(first), "text": first},
        {"id": source + "-p2", "source_id": source, "start": len(first) + 2, "end": len(body), "text": last},
    ]}


def articles():
    return (article("s1", "Aster announced a model on Monday in Delft.\n\nIt will be available next month."),
            article("s2", "On Monday in Delft, Aster announced a model.\n\nThe launch has no reported harm."))


@pytest.fixture
def request_packet():
    left, right = articles()
    return build_request(left=left, right=right, versions={"protocol": "protocol-version"})


def result(label="same_event"):
    return {
        "label": label, "rationale": "Both focal reports describe the same announcement.",
        "events": [{"source_version": source, "description": "Aster announced a model",
                    "action": "announced a model", "actors": ["Aster"], "event_date": "Monday",
                    "location": "Delft", "multiple_events": False} for source in ("s1", "s2")],
        "claims": [
            {"source_version": "s1", "passage_id": "s1-p1", "quote": "Aster announced a model on Monday in Delft.",
             "supports": list(EVENT_FIELDS)},
            {"source_version": "s2", "passage_id": "s2-p1", "quote": "On Monday in Delft, Aster announced a model.",
             "supports": list(EVENT_FIELDS)},
        ],
        "inspected_passage_ids": ["s1-p1", "s1-p2", "s2-p1", "s2-p2"],
    }


def test_complete_pair_request_and_normalized_source_bound_quotes(request_packet):
    assert request_packet["task_kind"] == TASK_KIND
    assert [a["role"] for a in request_packet["articles"]] == ["left", "right"]
    assert len(request_packet["evidence"]) == 4
    for item in request_packet["evidence"]:
        assert item["text_hash"] == hashlib.sha256(item["text"].encode()).hexdigest()
    validation = validate_answer(request_packet, result())
    assert validation["human_validated"] is False
    assert "entailment not validated" in validation["citation_validation"]
    assert "attention unobserved" in validation["coverage_observation"]
    assert validation["evidence_references"][1]["source_version"] == "s2"
    assert validation["evidence_references"][1]["source_start"] == 0
    assert validation["evidence_references"][1]["source_end"] == len(articles()[1]["evidence"][0]["text"])


@pytest.mark.parametrize("change", ["missing", "duplicate", "source", "text", "offset", "hash", "extra", "same_source"])
def test_incomplete_or_corrupt_input_never_becomes_pair_request(change):
    left, right = articles()
    if change == "missing":
        left["evidence"].pop()
    elif change == "duplicate":
        left["evidence"].append(dict(left["evidence"][0]))
    elif change == "source":
        left["evidence"][0]["source_id"] = "s2"
    elif change == "text":
        left["evidence"][0]["text"] = "not supplied"
    elif change == "offset":
        left["evidence"][0]["start"] = False
    elif change == "hash":
        left["evidence"][0]["text_hash"] = "wrong"
    elif change == "extra":
        left["evidence"][0]["distance"] = 0.2
    else:
        right = copy.deepcopy(left)
    with pytest.raises(ResearchError):
        build_request(left=left, right=right, versions={})


@pytest.mark.parametrize("field", EVENT_FIELDS)
def test_every_nonunknown_event_field_requires_same_source_claim(request_packet, field):
    sample = result()
    sample["claims"][1]["supports"].remove(field)
    with pytest.raises(ResearchError, match="uncited_factual_field"):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("label", ["same_event", "different_event"])
def test_decisive_labels_require_quotes_from_both_articles(request_packet, label):
    sample = result(label)
    sample["claims"] = sample["claims"][:1]
    with pytest.raises(ResearchError, match="uncited_factual_field"):
        validate_answer(request_packet, sample)


def test_uncertain_unknown_events_need_no_fabricated_facts(request_packet):
    sample = result("uncertain")
    sample["claims"] = []
    for event in sample["events"]:
        event.update({field: [] if field == "actors" else "unknown" for field in EVENT_FIELDS})
        event["multiple_events"] = True
    assert validate_answer(request_packet, sample)["status"] == "valid"


def test_multiple_focal_events_prevents_decisive_label(request_packet):
    sample = result()
    sample["events"][0]["multiple_events"] = True
    with pytest.raises(ResearchError, match="decisive_event_anchors_required"):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("change,reason", [
    ("cross_source", "quote_invalid"), ("fabricated", "quote_invalid"),
    ("coverage", "incomplete_coverage"), ("repeat", "schema_invalid"),
    ("event_source", "event_sources_invalid"), ("extra_field", "schema_invalid"),
    ("unknown_field", "schema_invalid"), ("blank_quote", "quote_invalid"),
])
def test_invalid_response_rejected(request_packet, change, reason):
    sample = result()
    if change == "cross_source":
        sample["claims"][0]["source_version"] = "s2"
    elif change == "fabricated":
        sample["claims"][0]["quote"] = "never supplied"
    elif change == "coverage":
        sample["inspected_passage_ids"].pop()
    elif change == "repeat":
        sample["inspected_passage_ids"].append("s1-p1")
    elif change == "event_source":
        sample["events"][1]["source_version"] = "s1"
    elif change == "extra_field":
        sample["score"] = 0.3
    elif change == "unknown_field":
        sample["claims"][0]["supports"] = ["publication_date"]
    else:
        sample["claims"][0]["quote"] = " "
    with pytest.raises(ResearchError, match=reason):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("field", ["body", "body_sha256"])
def test_request_article_mutations_invalidate_transport_and_validation(request_packet, field):
    request_packet["articles"][0][field] = "changed"
    with pytest.raises(ResearchError):
        build_prompt(request_packet)
    with pytest.raises(ResearchError):
        validate_answer(request_packet, result())


def test_provider_blinds_sampling_and_preserves_source_mapping(tmp_path, monkeypatch, request_packet):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    request_packet.update(distance=0.2, score=0.8, rank=1, sampling_arm="heldout", previous_label="same_event")
    invocation = CodexCLIProvider(tmp_path).prepare(request_packet)
    packet = json.loads(invocation.stdin)
    assert packet["task"] == TASK_INSTRUCTION
    assert packet["articles"] == [{"role": "left", "source_version": "s1", "title": None, "published_at": None},
                                  {"role": "right", "source_version": "s2", "title": None, "published_at": None}]
    assert {p["source_id"] for p in packet["evidence"]} == {"s1", "s2"}
    assert all(set(p) == {"id", "source_id", "text"} for p in packet["evidence"])
    assert not {"distance", "score", "rank", "sampling_arm", "previous_label", "versions"} & set(packet)
    assert (invocation.cwd / "AGENTS.md").read_text(encoding="utf-8") == WORKER_RULES
    assert invocation.manifest()["worker_rules"] == WORKER_RULES


def test_input_metadata_cannot_leak_scores_or_external_identifiers():
    left, right = articles()
    left["url"] = "https://example.test/unpermitted-extra"
    with pytest.raises(ResearchError, match="article_fields_invalid"):
        build_request(left=left, right=right, versions={})


def test_optional_metadata_is_exact_and_available_for_relative_time_not_citation():
    left, right = articles()
    left.update(title="Model announcement", published_at="2026-10-13T09:00:00+02:00")
    right.update(title=None, published_at="2026-10-15T17:01:00Z")
    request = build_request(left=left, right=right, versions={})
    packet = json.loads(build_prompt(request))
    assert packet["articles"][0]["title"] == left["title"]
    assert packet["articles"][0]["published_at"] == left["published_at"]
    assert packet["articles"][1]["title"] is None
    assert packet["articles"][1]["published_at"] == right["published_at"]
    assert "Publication gaps alone do not prove" in packet["task"]
    assert "must never\nautomatically become the event date" in packet["task"]
    assert "editorial or general analysis" in packet["task"]
    sample = result()
    sample["claims"][0]["quote"] = left["title"]
    with pytest.raises(ResearchError, match="quote_invalid"):
        validate_answer(request, sample)


@pytest.mark.parametrize("field,value", [("title", []), ("published_at", 20261015), ("published_at", False)])
def test_metadata_rejects_non_string_non_null_values(field, value):
    left, right = articles()
    left[field] = value
    with pytest.raises(ResearchError, match="article_metadata_invalid"):
        build_request(left=left, right=right, versions={})


def test_registered_article_metadata_shape_is_revalidated(request_packet):
    request_packet["articles"][0].pop("title")
    with pytest.raises(ResearchError, match="request_integrity_mismatch"):
        build_prompt(request_packet)


def test_nonblank_gap_and_cross_article_duplicate_passage_rejected():
    left, right = articles()
    left["evidence"][0]["end"] -= 1
    left["evidence"][0]["text"] = left["body"][:left["evidence"][0]["end"]]
    with pytest.raises(ResearchError, match="incomplete_source_coverage"):
        build_request(left=left, right=right, versions={})
    left, right = articles()
    right["evidence"][0]["id"] = left["evidence"][0]["id"]
    with pytest.raises(ResearchError, match="duplicate_passage"):
        build_request(left=left, right=right, versions={})
