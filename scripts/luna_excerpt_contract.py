"""Source-free Luna excerpt contract and deterministic checks.

Production callers must enter Research.execute and the shared model gateway.
This module does not read corpus records, call a provider or accept findings.
Exact citation validation cannot establish entailment or semantic accuracy.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "luna-excerpt-v1"
PROMPT_PATH = ROOT / "prompts/luna_excerpt_v1.txt"
SCHEMA_PATH = ROOT / "schemas/luna_excerpt_v1.json"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def contract_digest() -> str:
    """Bind the exact prompt/schema and validation implementation bytes."""
    parts = [PROMPT_PATH.read_bytes(), SCHEMA_PATH.read_bytes(), Path(__file__).read_bytes()]
    return hashlib.sha256(b"\x00".join(parts)).hexdigest()


def _packet_spans(packet: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    spans: dict[str, dict[str, Any]] = {}
    if not isinstance(packet, dict):
        return spans, ["packet:not_object"]
    if type(packet.get("body_fully_covered")) is not bool:
        errors.append("packet:body_coverage_missing")
    title = packet.get("title", "")
    if not isinstance(title, str):
        errors.append("packet:title_not_string")
    elif title.strip():
        spans["title"] = {"span_id": "title", "text": title, "start": 0, "end": len(title), "field": "title"}
    body_spans = packet.get("spans")
    if not isinstance(body_spans, list) or not body_spans:
        return spans, errors + ["packet:body_spans_missing"]
    previous_end = -1
    for index, span in enumerate(body_spans):
        code = f"packet:span_{index}"
        if not isinstance(span, dict):
            errors.append(f"{code}:not_object")
            continue
        sid, text = span.get("span_id"), span.get("text")
        start, end = span.get("start"), span.get("end")
        if not isinstance(sid, str) or not sid or sid == "title" or sid in spans:
            errors.append(f"{code}:invalid_id")
            continue
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{code}:blank_text")
            continue
        if type(start) is not int or type(end) is not int or start < 0 or end - start != len(text):
            errors.append(f"{code}:invalid_offsets")
            continue
        if start < previous_end:
            errors.append(f"{code}:overlap_or_unsorted")
        previous_end = end
        spans[sid] = {**span, "field": "body"}
    return spans, errors


def resolve_evidence(evidence: dict[str, Any], packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve *all* exact occurrences; never silently choose a repeated quote.

    Offsets use Python Unicode code points and exclusive ends. Body positions
    are relative to the retained body; title positions are relative to title.
    The upstream runtime must verify input spans against the source version.
    """
    spans, errors = _packet_spans(packet)
    if errors:
        raise ValueError("invalid_excerpt_packet")
    span = spans.get(evidence.get("span_id", ""))
    quote = evidence.get("quote")
    if span is None or not isinstance(quote, str) or not quote.strip():
        return []
    return [
        {"span_id": span["span_id"], "field": span["field"],
         "quote_start": match.start(), "quote_end": match.start() + len(quote),
         "source_start": span["start"] + match.start(),
         "source_end": span["start"] + match.start() + len(quote)}
        for match in re.finditer(f"(?={re.escape(quote)})", span["text"])
    ]


def validate_output(output: Any, packet: Any) -> list[str]:
    """Return safe error codes, never source snippets or schema error payloads."""
    spans, errors = _packet_spans(packet)
    schema_errors = sorted(Draft202012Validator(load_schema()).iter_errors(output),
                           key=lambda err: str(list(err.absolute_path)))
    errors.extend("schema:" + ".".join(map(str, err.absolute_path)) + ":" + str(err.validator)
                  for err in schema_errors)
    if errors:
        return errors
    expected_basis = "full_body" if packet["body_fully_covered"] else "excerpts"
    if output["evidence_basis"] != expected_basis:
        errors.append("evidence_basis:mismatch")

    def check_evidence(evidence: dict[str, Any], path: str, surface: str | None = None) -> None:
        span = spans.get(evidence["span_id"])
        quote = evidence["quote"]
        if not quote.strip() or span is None or quote not in span["text"]:
            errors.append(f"{path}:quote_not_grounded")
        if surface is not None and (not surface.strip() or surface not in quote):
            errors.append(f"{path}:surface_not_in_own_quote")

    for index, evidence in enumerate(output["focus_evidence"]):
        check_evidence(evidence, f"focus_evidence.{index}")
    if not output["reason"].strip():
        errors.append("reason:blank")
    if output["focus"] == "multiple":
        distinct = {(item["span_id"], item["quote"]) for item in output["focus_evidence"]}
        if len(distinct) < 2:
            errors.append("focus:multiple_needs_two_quotes")
    event = output["event"]
    if output["focus"] == "single":
        if event is None:
            errors.append("focus:single_requires_event")
    elif event is not None or output["extra_facts"] or output["facts_truncated"]:
        errors.append("focus:non_single_has_event_or_facts")
    entity_ids = [entity["id"] for entity in output["entities"]]
    if len(set(entity_ids)) != len(entity_ids):
        errors.append("entities:duplicate_id")
    expected_ids = [f"e{i + 1}" for i in range(len(entity_ids))]
    if entity_ids != expected_ids:
        errors.append("entities:nonsequential_id")
    entities = {entity["id"]: entity for entity in output["entities"]}
    normalized_texts = [unicodedata.normalize("NFKC", span["text"]).casefold()
                        for span in spans.values()]
    for index, entity in enumerate(output["entities"]):
        check_evidence(entity["evidence"], f"entities.{index}", entity["surface"])
        normalized = entity["normalized_name"]
        if normalized is not None:
            # Presence is necessary but not sufficient proof of alias identity.
            normalized = unicodedata.normalize("NFKC", normalized).casefold()
            if not normalized.strip() or not any(normalized in text for text in normalized_texts):
                errors.append(f"entities.{index}:normalized_name_not_in_packet")
        if entity["subtype"] is not None and not entity["subtype"].strip():
            errors.append(f"entities.{index}:blank_subtype")
    if output["entities_truncated"] and len(entity_ids) != 24:
        errors.append("entities:overflow_without_cap")
    if output["facts_truncated"] and len(output["extra_facts"]) != 16:
        errors.append("facts:overflow_without_cap")
    if event is not None:
        check_evidence(event["trigger"]["evidence"], "event.trigger", event["trigger"]["surface"])
        if not event["summary"].strip():
            errors.append("event.summary:blank")
        if event["claim_status"] == "hypothetical":
            errors.append("event:hypothetical_not_occurrence")
        if event["time_expression"] is not None:
            time = event["time_expression"]
            check_evidence(time["evidence"], "event.time_expression", time["surface"])
        attribution = event["attribution_entity_id"]
        if attribution is not None:
            if attribution not in entities:
                errors.append("event:unknown_attribution")
            elif entities[attribution]["surface"] not in event["trigger"]["evidence"]["quote"]:
                errors.append("event:attribution_not_in_quote")
        participant_roles: list[tuple[str, str]] = []
        for index, participant in enumerate(event["participants"]):
            eid = participant["entity_id"]
            participant_roles.append((eid, participant["role"]))
            check_evidence(participant["evidence"], f"event.participants.{index}")
            if eid not in entities:
                errors.append("event.participants:unknown_entity")
            elif entities[eid]["relation"] != "focal":
                errors.append("event.participants:nonfocal_entity")
        if len(set(participant_roles)) != len(participant_roles):
            errors.append("event.participants:duplicate_entity_role")
    for index, fact in enumerate(output["extra_facts"]):
        path = f"extra_facts.{index}"
        check_evidence(fact["evidence"], path, fact["value_text"])
        if fact["subject_entity_id"] is not None and fact["subject_entity_id"] not in entities:
            errors.append(f"{path}:unknown_entity")
        elif fact["subject_entity_id"] is not None and entities[fact["subject_entity_id"]]["relation"] != "focal":
            errors.append(f"{path}:nonfocal_subject")
        attribution = fact["attribution_entity_id"]
        if attribution is not None:
            if attribution not in entities:
                errors.append(f"{path}:unknown_attribution")
            elif entities[attribution]["surface"] not in fact["evidence"]["quote"]:
                errors.append(f"{path}:attribution_not_in_quote")
        if fact["unit_text"] is not None:
            check_evidence(fact["evidence"], path + ".unit_text", fact["unit_text"])
        number = fact["value_number"]
        if number is not None:
            try:
                finite = math.isfinite(number)
            except OverflowError:
                finite = False
            if fact["value_type"] not in {"quantity", "money", "duration"} or not finite:
                errors.append(f"{path}:invalid_numeric_type")
        normalized_date = fact["normalized_date"]
        if normalized_date is not None:
            if fact["value_type"] != "date":
                errors.append(f"{path}:date_on_nondate")
            try:
                date.fromisoformat(normalized_date)
            except ValueError:
                errors.append(f"{path}:invalid_date")
            if not re.search(r"(?<!\d)" + re.escape(normalized_date[:4]) + r"(?!\d)",
                             fact["evidence"]["quote"]):
                errors.append(f"{path}:date_year_not_explicit")
    return errors


def fictional_example() -> tuple[dict[str, Any], dict[str, Any]]:
    """A deliberately fictional software fixture, never a research result."""
    text = "Fictional Acme Labs launched the Aster system in Delft on 2026-01-12. The rollout covers 12 schools."
    packet = {"title": "Fictional Aster launch", "body_fully_covered": True,
              "spans": [{"span_id": "body1", "start": 0, "end": len(text), "text": text}]}
    first = {"span_id": "body1", "quote": text.split(". ")[0] + "."}
    second = {"span_id": "body1", "quote": "The rollout covers 12 schools."}
    entities = [
        {"id": "e1", "type": "organization", "subtype": None, "surface": "Acme Labs",
         "normalized_name": None, "relation": "focal", "evidence": first},
        {"id": "e2", "type": "product_system", "subtype": None, "surface": "Aster",
         "normalized_name": None, "relation": "focal", "evidence": first},
        {"id": "e3", "type": "place", "subtype": None, "surface": "Delft",
         "normalized_name": None, "relation": "focal", "evidence": first},
    ]
    output = {
        "schema_version": CONTRACT_VERSION, "focus": "single", "evidence_basis": "full_body",
        "reason": "The supplied fictional article focuses on one system launch.", "focus_evidence": [first],
        "event": {"summary": "Acme Labs launched Aster in Delft.", "type": "release",
                  "trigger": {"surface": "launched", "evidence": first}, "claim_status": "reported",
                  "attribution_entity_id": None,
                  "participants": [{"entity_id": "e1", "role": "agent", "evidence": first},
                                   {"entity_id": "e2", "role": "product", "evidence": first},
                                   {"entity_id": "e3", "role": "location", "evidence": first}],
                  "time_expression": {"surface": "2026-01-12", "evidence": first}},
        "entities": entities,
        "extra_facts": [{"name": "school_count", "subject_entity_id": None, "value_type": "quantity",
                         "value_text": "12 schools", "value_number": 12, "unit_text": "schools",
                         "normalized_date": None, "claim_status": "reported", "attribution_entity_id": None,
                         "evidence": second}],
        "entities_truncated": False, "facts_truncated": False,
    }
    return packet, output
