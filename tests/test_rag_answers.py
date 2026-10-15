from __future__ import annotations

import copy
import hashlib

import pytest

from newsresearch.common import ResearchError
from newsresearch.rag_answers import ANSWER_FIELDS, TASK_KIND, build_request, render_answers, validate_answer


@pytest.fixture
def request_packet():
    body = "Aster's director approved the AI deployment.\n\nThe malfunction harmed three customers."
    first, last = body.split("\n\n")
    return build_request(
        question="Which organizational decisions preceded or followed an AI incident with negative impact?",
        source_version="source", body=body,
        evidence=[
            {"id": "p1", "source_id": "source", "start": 0, "end": len(first), "text": first},
            {"id": "p2", "source_id": "source", "start": len(first) + 2, "end": len(body), "text": last},
        ],
        versions={"question": "question-version"},
    )


def result():
    return {
        "status": "supported",
        "answer": "Aster's director approved an AI deployment before a malfunction harmed three customers.",
        "organization": "Aster", "actors": ["Aster's director"],
        "decisions": ["Approved the AI deployment"], "incident": "AI deployment malfunction",
        "negative_impact": "Three customers harmed", "timing": "before",
        "claims": [
            {"passage_id": "p1", "quote": "Aster's director approved the AI deployment.",
             "supports": ["answer", "organization", "actors", "decisions", "timing"]},
            {"passage_id": "p2", "quote": "The malfunction harmed three customers.",
             "supports": ["answer", "incident", "negative_impact"]},
        ],
        "inspected_passage_ids": ["p1", "p2"],
    }


def test_request_preserves_exact_question_and_all_article_passages(request_packet):
    instruction = request_packet["inclusion"]["instruction"]
    assert request_packet["inclusion"]["sha256"] == hashlib.sha256(instruction.encode()).hexdigest()
    assert request_packet["task_kind"] == TASK_KIND
    assert len(request_packet["evidence"]) == 2
    assert not {"score", "rank", "cutoff"} & set(request_packet)
    assert validate_answer(request_packet, result())["human_validated"] is False


@pytest.mark.parametrize("change", ["missing", "duplicate", "wrong_source", "wrong_text", "wrong_offsets"])
def test_full_stored_article_must_be_covered_exactly(request_packet, change):
    evidence = copy.deepcopy(request_packet["evidence"])
    if change == "missing":
        evidence.pop()
    elif change == "duplicate":
        evidence.append(dict(evidence[0]))
    elif change == "wrong_source":
        evidence[0]["source_id"] = "other"
    elif change == "wrong_text":
        evidence[0]["text"] = "Different text"
    else:
        evidence[0]["start"] = True
    with pytest.raises(ResearchError):
        build_request(question="q", source_version="source",
                      body="Aster's director approved the AI deployment.\n\nThe malfunction harmed three customers.",
                      evidence=evidence, versions={})


def test_no_article_clipping_even_with_later_supplied_passages():
    with pytest.raises(ResearchError, match="incomplete_source_coverage"):
        build_request(question="q", source_version="s", body="first omitted last",
                      evidence=[{"id": "p1", "start": 0, "end": 5, "text": "first"},
                                {"id": "p2", "start": 14, "end": 18, "text": "last"}], versions={})


@pytest.mark.parametrize("field", ANSWER_FIELDS)
def test_supported_answer_requires_each_field_explicitly_cited(request_packet, field):
    sample = result()
    for claim in sample["claims"]:
        claim["supports"] = [item for item in claim["supports"] if item != field]
    with pytest.raises(ResearchError, match="uncited_factual_field"):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("field,value", [("organization", ""), ("actors", []), ("decisions", []),
                                          ("incident", ""), ("negative_impact", ""), ("timing", "unknown")])
def test_supported_cannot_omit_or_invent_required_facts(request_packet, field, value):
    sample = result()
    sample[field] = value
    with pytest.raises(ResearchError, match="supported_fields_required"):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("status", ["insufficient", "uncertain"])
def test_nonanswers_retain_unknown_without_forced_quotes(request_packet, status):
    sample = result()
    sample.update(status=status, answer="The requested decision and impact are not sufficiently established.",
                  organization="", actors=[], decisions=[], incident="", negative_impact="", timing="unknown",
                  claims=[])
    assert validate_answer(request_packet, sample)["status"] == "valid"


def test_uncertain_partial_facts_still_need_citations(request_packet):
    sample = result()
    sample["status"] = "uncertain"
    sample["claims"] = []
    with pytest.raises(ResearchError, match="uncited_factual_field"):
        validate_answer(request_packet, sample)


@pytest.mark.parametrize("change,reason", [("quote", "quote_invalid"), ("passage", "quote_invalid"),
                                           ("coverage", "incomplete_coverage"), ("repeated", "schema_invalid"),
                                           ("support", "schema_invalid"), ("extra", "schema_invalid")])
def test_fabricated_quotes_incomplete_coverage_and_schema_drift_rejected(request_packet, change, reason):
    sample = result()
    if change == "quote":
        sample["claims"][0]["quote"] = "not present"
    elif change == "passage":
        sample["claims"][0]["passage_id"] = "other"
    elif change == "coverage":
        sample["inspected_passage_ids"] = ["p1"]
    elif change == "repeated":
        sample["inspected_passage_ids"] = ["p1", "p2", "p1"]
    elif change == "support":
        sample["claims"][0]["supports"] = ["invented"]
    else:
        sample["hidden_reasoning"] = "not allowed"
    with pytest.raises(ResearchError, match=reason):
        validate_answer(request_packet, sample)


def test_claim_validation_does_not_claim_semantic_entailment(request_packet):
    validated = validate_answer(request_packet, result())
    assert "entailment not validated" in validated["citation_validation"]
    assert "attention unobserved" in validated["coverage_observation"]


def test_renderer_displays_every_row_and_missingness_without_assigning_tags():
    text = render_answers({
        "question": "Question", "query": "Exact retrieval query", "expected_articles": 20000,
        "scored_articles": 19576, "missing_scores": 424, "selected_articles": 100,
        "attempted_articles": 2, "counts": {"supported": 1}, "failed_articles": 1, "pending_articles": 98,
        "rows": [
            {"rank": 1, "score": 0.54321, "title": "A | source", "url": "https://example.test/a(1)",
             "answer": result()},
            {"rank": 2, "score": None, "title": "Other", "url": "javascript:alert(1)",
             "status": "failed", "error": "technical failure"},
        ],
    })
    assert "0.5432" in text and "A \\| source" in text
    assert "https://example.test/a%281%29" in text and "javascript:" not in text
    assert "Exact retrieval query" in text and "null/untagged **20000**" in text
    assert "cutoff: **none**" in text and "failed: 1; pending: 98" in text
    assert "technical failure" in text and "Aster's director approved" in text
    assert "Missing or failed processing is not a negative answer" in text


def test_worked_example_uses_first_supported_not_first_candidate():
    absent = result()
    absent.update(status="insufficient", answer="No requested example", organization="", actors=[],
                  decisions=[], incident="", negative_impact="", timing="unknown", claims=[])
    text = render_answers({"question": "q", "rows": [
        {"rank": 1, "title": "First but insufficient", "answer": absent},
        {"rank": 2, "title": "First supported", "score": 0.5,
         "url": "https://example.test/second", "answer": result()},
        {"rank": 3, "title": "Second supported", "answer": result()},
    ]})
    worked = text.split("**Specific example from the highest-ranked supported answer:**", 1)[1]
    assert "[First supported](https://example.test/second)" in worked
    assert "First but insufficient" not in worked and "Second supported" not in worked
    assert "Organization: Aster" in worked and "Timing: before" in worked
    assert "(passage p1)" in worked


def test_renderer_displays_no_supported_example_and_limits_quote_excerpt():
    unsupported = render_answers({"rows": []})
    assert "No supported example is available" in unsupported
    sample = result()
    sample["claims"][0]["quote"] = " ".join(f"word{i}" for i in range(40))
    text = render_answers({"rows": [{"rank": 1, "answer": sample}]})
    assert "word24" in text and "word25" not in text


def test_malformed_publisher_url_does_not_prevent_report():
    text = render_answers({"rows": [{"rank": 1, "title": "Malformed URL source",
        "url": "https://[broken", "answer": result()}]})
    assert "Malformed URL source" in text
    assert "https://[broken" not in text
    assert "Organization: Aster" in text
