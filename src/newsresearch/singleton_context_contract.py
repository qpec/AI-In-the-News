"""Expanded retained-context pair contract; pure helpers, no research access."""
from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any

from jsonschema import Draft202012Validator

from .common import Json, ResearchError, digest, require_no_credentials
from .event_pair_reference import TASK_INSTRUCTION as LEAD_INSTRUCTION
from .luna_lead_answers import _parent

CONTRACT = "event-pair-expanded-context-v1"
MAX_CHARS = 24000
MAX_SPANS = 128
INSTRUCTION = LEAD_INSTRUCTION.replace(
    "exactly two article leads", "exactly two articles' retained context"
).replace(
    "Only the titles and first three nonempty body paragraphs, capped at 3000 body\ncharacters per article, were supplied.",
    "Each article supplies up to 24,000 retained body characters and 128 exact body spans.\n"
    "Short articles supply all stored paragraphs; longer articles supply the first\n"
    "18,000 and last 6,000 body characters. Excess spans retain the first 96 and\n"
    "last 32. Coverage metadata states omissions; omitted text was not supplied."
).replace("If the leads do not identify", "If the supplied context does not identify").replace(
    "provisional lead-only", "provisional expanded-context"
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_context(source: str, title: str | None, published_at: str | None,
                 body: str, paragraphs: list[Json]) -> Json:
    """Caller obtains body/paragraphs through audited inspection; verify slices."""
    intervals = [(0, len(body))] if len(body) <= MAX_CHARS else [(0, 18000), (len(body) - 6000, len(body))]
    spans = []
    cursor = 0
    for passage in paragraphs:
        parent = _parent(passage, source)
        if parent["start"] < cursor or body[parent["start"]:parent["end"]] != passage["text"]:
            raise ResearchError("context_source_paragraph_mismatch")
        cursor = parent["end"]
        if not passage["text"].strip():
            continue
        for lower, upper in intervals:
            start, end = max(parent["start"], lower), min(parent["end"], upper)
            if start < end:
                text = body[start:end]
                value = {"source_id": source, "start": start, "end": end,
                         "text": text, "text_hash": sha(text), "parent_ref": parent}
                spans.append({"span_version": digest({"contract": CONTRACT, **value}), **value})
    if len(spans) > MAX_SPANS:
        spans = spans[:96] + spans[-32:]
    chars = sum(len(span["text"]) for span in spans)
    available = sum(len(p["text"]) for p in paragraphs if p["text"].strip())
    return {"source_version": source, "title": title[:400] if title is not None else None,
            "published_at": published_at, "passages": spans,
            "coverage": {"body_characters": len(body), "available_paragraph_characters": available,
                         "retained_body_characters": chars, "omitted_paragraph_characters": available - chars,
                         "input_paragraphs": len(paragraphs), "retained_spans": len(spans),
                         "all_stored_paragraph_text_supplied": chars == available,
                         "body_sha256": sha(body), "selection": "all-or-head18000-tail6000-max128"}}


def schema(ids: list[str]) -> Json:
    return {"type": "object", "additionalProperties": False,
            "required": ["label", "support_span_ids", "reason"], "properties": {
                "label": {"type": "string", "enum": ["same_event", "different_event", "uncertain"]},
                "support_span_ids": {"type": "array", "maxItems": 6, "uniqueItems": True,
                                     "items": {"type": "string", "enum": ids}},
                "reason": {"type": "string", "minLength": 1, "maxLength": 600}}}


def build_request(left: Json, right: Json, versions: dict[str, str]) -> Json:
    articles: list[Json] = []
    evidence: list[Json] = []
    for role, context in zip(("A", "B"), (left, right), strict=True):
        articles.append({"role": role, **{k: deepcopy(context[k]) for k in
                                         ("source_version", "title", "published_at", "coverage")}})
        evidence.extend({"id": f"{role}{i}", **deepcopy(span)} for i, span in enumerate(context["passages"], 1))
    packet = {"gateway_contract": CONTRACT, "task_kind": "event_pair_reference", "versions": dict(versions),
              "articles": articles, "evidence": evidence, "schema": schema([s["id"] for s in evidence]),
              "inclusion": {"instruction": INSTRUCTION, "sha256": sha(INSTRUCTION),
                            "criterion_ids": ["same_focal_real_world_event_expanded_context_pair"]},
              "evidence_digest": digest(evidence)}
    validate_request(packet)
    return packet


def validate_request(request: Json) -> None:
    require_no_credentials(request)
    articles, evidence = request.get("articles", []), request.get("evidence", [])
    if (request.get("gateway_contract") != CONTRACT or request.get("task_kind") != "event_pair_reference"
            or len(articles) != 2 or articles[0]["source_version"] == articles[1]["source_version"]
            or request.get("evidence_digest") != digest(evidence)
            or request.get("inclusion") != {"instruction": INSTRUCTION, "sha256": sha(INSTRUCTION),
                                          "criterion_ids": ["same_focal_real_world_event_expanded_context_pair"]}
            or request.get("schema") != schema([s["id"] for s in evidence])):
        raise ResearchError("context_request_contract_invalid")
    consumed = 0
    for role, article in zip(("A", "B"), articles, strict=True):
        spans = [s for s in evidence if s["source_id"] == article["source_version"]]
        coverage = article["coverage"]
        if (article["role"] != role or not 1 <= len(spans) <= MAX_SPANS
                or sum(len(s["text"]) for s in spans) > MAX_CHARS
                or coverage["retained_spans"] != len(spans)
                or coverage["retained_body_characters"] != sum(len(s["text"]) for s in spans)):
            raise ResearchError("context_request_coverage_invalid")
        cursor = 0
        for i, span in enumerate(spans, 1):
            value = {k: v for k, v in span.items() if k not in {"id", "span_version"}}
            parent = span["parent_ref"]
            if (span["id"] != f"{role}{i}" or span["text_hash"] != sha(span["text"])
                    or span["span_version"] != digest({"contract": CONTRACT, **value})
                    or span["source_id"] != parent["source_id"]
                    or not (cursor <= span["start"] and parent["start"] <= span["start"] < span["end"] <= parent["end"])
                    or span["end"] - span["start"] != len(span["text"])):
                raise ResearchError("context_request_span_invalid")
            cursor = span["end"]
        consumed += len(spans)
    if consumed != len(evidence):
        raise ResearchError("context_request_unmapped_spans")


def validate_answer(request: Json, answer: Any) -> Json:
    validate_request(request)
    if list(Draft202012Validator(request["schema"]).iter_errors(answer)) or not answer["reason"].strip():
        raise ResearchError("context_answer_schema_invalid")
    require_no_credentials(answer)
    by_id = {span["id"]: span for span in request["evidence"]}
    cited = [by_id[i] for i in answer["support_span_ids"]]
    substantive = {s["source_id"] for s in cited if sum(c.isalnum() for c in s["text"]) >= 20}
    if answer["label"] != "uncertain" and substantive != {a["source_version"] for a in request["articles"]}:
        raise ResearchError("context_answer_both_sources_required")
    return {"status": "valid", "human_validated": False, "semantic_entailment_validated": False,
            "whole_group_purity_validated": False,
            "coverage_observation": "Supplied retained context; model attention unobserved",
            "evidence_references": [{"span_id": s["id"], "source_version": s["source_id"],
                "passage_hash": s["text_hash"], "parent_ref": s["parent_ref"], "source_start": s["start"],
                "source_end": s["end"], "quote": s["text"]} for s in cited],
            "review_status": "provisional_expanded_context_model_reference"}
