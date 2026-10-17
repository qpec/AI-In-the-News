"""Source-free compact event contract; production use requires audited gateway.

The validator establishes syntax, packet fidelity and literal grounding only.
It does not validate focus, boundaries, entity identity, roles, entailment, truth
or completeness. No corpus read, model dispatch or accepted finding occurs here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from structured_article_input import (
    PACKET_VERSION,
    InvalidSourceMap,
    LiteralNotGrounded,
    _validate_source_map,
    build_structured_input,
    resolve_surface,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "luna-event-v2"
PROMPT_PATH = ROOT / "prompts/luna_event_v2.txt"
SCHEMA_PATH = ROOT / "schemas/luna_event_v2.json"
PARTICIPANT_CAP = 12
FACT_CAP = 6
REASONS = {
    "single": {"main_occurrence"},
    "multiple": {"coequal_occurrences"},
    "none": {"no_particular_occurrence"},
    "uncertain": {"boundary_unclear", "focus_unclear", "insufficient_evidence", "insufficient_body"},
}
CODEBOOK = {
    "version": CONTRACT_VERSION,
    "purpose": "Provisional single-article event records for later same-event assessment; no automatic grouping.",
    "entity_kinds": ["person", "organization", "group", "place", "product", "artifact", "object"],
    "role_kinds": ["initiator", "operator", "developer", "affected", "authority", "claim_source",
                   "event_place", "subject"],
    "focus": ["single", "multiple", "none", "uncertain"],
    "caps": {"event_essential_participants": PARTICIPANT_CAP, "additional_facts": FACT_CAP,
             "empirically_validated": False},
    "grounding": "Literal surfaces and evidence-unit refs only; normalization and offsets are not model output.",
}


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def contract_digest() -> str:
    paths = [PROMPT_PATH, SCHEMA_PATH, Path(__file__), Path(__file__).with_name("structured_article_input.py")]
    return hashlib.sha256(b"\x00".join(path.read_bytes() for path in paths)).hexdigest()


def build_input(article: dict[str, Any]) -> dict[str, Any]:
    """Pure builder; caller supplies an already-permitted source under Research.execute."""
    return build_structured_input(article, instructions=load_prompt(), codebook=CODEBOOK)


def validate_packet(packet: Any) -> list[str]:
    """Require full retained text and exact equality between sent text and map.

    This cannot establish fidelity to an external source version: its protected
    hash and retention decision still require upstream audited validation.
    """
    if not isinstance(packet, dict):
        return ["packet:not_object"]
    try:
        model = packet["model_input"]
        mapping = packet["source_map"]
        _validate_source_map(mapping)
        if model["packet_version"] != PACKET_VERSION or mapping["schema_version"] != PACKET_VERSION:
            return ["packet:version_mismatch"]
        coverage = model["coverage"]
        if coverage["retained_body_complete"] is not True or coverage["truncated"] is not False:
            return ["packet:incomplete_retained_body"]
        evidence = model["evidence"]
        title = evidence["title"]
        paragraphs = evidence["paragraphs"]
        if not isinstance(paragraphs, list) or not paragraphs:
            return ["packet:paragraphs_missing"]
        if title["id"] != "t0" or [p["id"] for p in paragraphs] != [f"p{i + 1}" for i in range(len(paragraphs))]:
            return ["packet:reference_order_invalid"]
        items = [title, *paragraphs]
        if set(mapping["spans"]) != {item["id"] for item in items}:
            return ["packet:reference_map_mismatch"]
        for item in items:
            span = mapping["spans"][item["id"]]
            expected_field = "title" if item["id"] == "t0" else "body"
            if span["field"] != expected_field:
                return ["packet:reference_field_mismatch"]
            text = mapping["source_fields"][span["field"]]["text"]
            if item["text"] != text[span["start"]:span["end"]]:
                return ["packet:model_evidence_map_mismatch"]
        body = mapping["source_fields"]["body"]["text"]
        title_text = mapping["source_fields"]["title"]["text"]
        if (not body.strip() or "".join(p["text"] for p in paragraphs) != body
                or title["text"] != title_text):
            return ["packet:source_coverage_mismatch"]
        cursor = 0
        for paragraph in paragraphs:
            span = mapping["spans"][paragraph["id"]]
            if span["start"] != cursor:
                return ["packet:noncontiguous_source_map"]
            cursor = span["end"]
        title_span = mapping["spans"]["t0"]
        if title_span["start"] != 0 or title_span["end"] != len(title_text):
            return ["packet:title_source_map_mismatch"]
    except (InvalidSourceMap, KeyError, TypeError, AttributeError, ValueError):
        return ["packet:invalid_source_map_or_shape"]
    return []


def validate_output(
    output: Any,
    packet: Any,
    *,
    response_status: str | None = "completed",
    response_truncated: bool = False,
) -> list[str]:
    """Return safe codes; the gateway must supply observed provider completion.

    A caller default does not establish a real response's completion metadata.
    Never use this pure function as a replacement for response retention,
    provider identity, refusal and attempt-state checks in the audited gateway.
    """
    if response_status != "completed" or response_truncated is not False:
        return ["response:not_completed"]
    errors = validate_packet(packet)
    schema_errors = sorted(Draft202012Validator(load_schema()).iter_errors(output),
                           key=lambda error: str(list(error.absolute_path)))
    def schema_codes(error: Any) -> list[str]:
        codes = ["schema:" + ".".join(map(str, error.absolute_path)) + ":" + str(error.validator)]
        for child in error.context:
            codes.extend(schema_codes(child))
        return codes

    for error in schema_errors:
        errors.extend(schema_codes(error))
    if errors:
        return errors
    mapping = packet["source_map"]
    available = set(mapping["spans"])
    excluded: set[str] = set()
    reasons: set[str] = set()

    def check_refs(refs: list[str], path: str, *, exclusion: bool = False) -> None:
        if len(refs) != len(set(refs)):
            errors.append(path + ":duplicate_reference")
        if not set(refs) <= available:
            errors.append(path + ":unknown_reference")
        if not exclusion and set(refs) & excluded:
            errors.append(path + ":excluded_evidence")
        for ref in refs:
            if ref in available:
                span = mapping["spans"][ref]
                text = mapping["source_fields"][span["field"]]["text"][span["start"]:span["end"]]
                if not text.strip():
                    errors.append(path + ":blank_evidence")

    def check_literal(value: dict[str, Any], path: str) -> None:
        check_refs(value["refs"], path + ".refs")
        try:
            matches = resolve_surface(value["surface"], value["refs"], mapping)
            if {match["span_id"] for match in matches} != set(value["refs"]):
                errors.append(path + ":surface_absent_from_some_refs")
        except (LiteralNotGrounded, ValueError):
            errors.append(path + ":surface_not_grounded")

    for index, exclusion in enumerate(output["excluded"]):
        path = f"excluded.{index}"
        check_refs(exclusion["refs"], path + ".refs", exclusion=True)
        if exclusion["reason"] in reasons:
            errors.append(path + ":duplicate_reason")
        if set(exclusion["refs"]) & excluded:
            errors.append(path + ":duplicate_excluded_reference")
        reasons.add(exclusion["reason"])
        excluded.update(exclusion["refs"])
    check_refs(output["refs"], "refs")
    if output["reason"] not in REASONS[output["focus"]]:
        errors.append("focus:reason_mismatch")
    event = output["event"]
    if output["focus"] != "single":
        if event is not None:
            errors.append("focus:nonsingle_requires_null_event")
        return errors
    if event is None:
        return errors + ["focus:single_requires_event"]
    if not event["summary"].strip():
        errors.append("event.summary:blank")
    check_literal(event["action"], "event.action")
    if event["time"] is not None:
        check_literal(event["time"], "event.time")
    check_refs(event["status_refs"], "event.status_refs")
    participant_ids = [item["id"] for item in event["participants"]]
    if len(set(participant_ids)) != len(participant_ids):
        errors.append("event.participants:duplicate_id")
    if participant_ids != [f"e{i + 1}" for i in range(len(participant_ids))]:
        errors.append("event.participants:nonsequential_id")
    for index, participant in enumerate(event["participants"]):
        path = f"event.participants.{index}"
        check_literal(participant, path)
        roles: set[str] = set()
        for role_index, role in enumerate(participant["roles"]):
            check_refs(role["refs"], path + f".roles.{role_index}.refs")
            if role["role"] in roles:
                errors.append(path + ":duplicate_role")
            roles.add(role["role"])
    facts: set[tuple[str, str | None, str, str, str | None]] = set()
    for index, fact in enumerate(event["facts"]):
        path = f"event.facts.{index}"
        check_literal(fact["value"], path + ".value")
        check_refs(fact["support_refs"], path + ".support_refs")
        if fact["subject"] is not None and fact["subject"] not in participant_ids:
            errors.append(path + ":unknown_subject")
        if fact["attributed_to"] is not None and fact["attributed_to"] not in participant_ids:
            errors.append(path + ":unknown_attribution")
        elif fact["attributed_to"] is not None:
            attributed = next(item for item in event["participants"] if item["id"] == fact["attributed_to"])
            if "claim_source" not in {role["role"] for role in attributed["roles"]}:
                errors.append(path + ":attribution_missing_claim_source_role")
        signature = (fact["predicate"], fact["subject"], fact["value"]["surface"], fact["status"], fact["attributed_to"])
        if signature in facts:
            errors.append(path + ":duplicate_fact")
        facts.add(signature)
    if event["participants_overflow"] and len(event["participants"]) != PARTICIPANT_CAP:
        errors.append("event.participants:overflow_without_cap")
    if event["facts_overflow"] and len(event["facts"]) != FACT_CAP:
        errors.append("event.facts:overflow_without_cap")
    return errors


def resolve_output_literals(output: Any, packet: Any) -> dict[str, list[dict[str, Any]]]:
    """Resolve every occurrence after validation; repeated literals stay ambiguous."""
    if validate_output(output, packet):
        raise ValueError("invalid_event_output_or_packet")
    event = output["event"]
    if event is None:
        return {}
    values = {"event.action": event["action"]}
    if event["time"] is not None:
        values["event.time"] = event["time"]
    values.update({f"event.participants.{index}": item for index, item in enumerate(event["participants"])})
    values.update({f"event.facts.{index}.value": item["value"] for index, item in enumerate(event["facts"])})
    return {path: resolve_surface(value["surface"], value["refs"], packet["source_map"])
            for path, value in values.items()}


def fictional_example() -> tuple[dict[str, Any], dict[str, Any]]:
    """Clearly fictional source-free demonstration, never a research result."""
    article = {"title": "Fictional example: Lumen Council launches a school service",
        "body": "On 4 May 2026, Lumen Council launched StudyLink for local pupils.\n\n"
                "The council said the service covers 12 schools. It is operated by Lumen Council.\n\n"
                "Related stories: Fictional harbor festival opens next week.",
        "lang": "eng", "dateTimePub": "2026-05-05T09:00:00Z",
        "source": {"uri": "fictional.example", "title": "Fictional Gazette"}}
    output = {"schema_version": CONTRACT_VERSION, "focus": "single", "reason": "main_occurrence",
        "refs": ["p1", "p2"], "excluded": [{"reason": "related_story", "refs": ["p3"]}],
        "event": {"summary": "Lumen Council launched StudyLink for local pupils.",
            "action": {"surface": "launched", "refs": ["p1"]},
            "time": {"surface": "4 May 2026", "refs": ["p1"]}, "status": "reported", "status_refs": ["p1"],
            "participants": [
                {"id": "e1", "kind": "organization", "named": True, "surface": "Lumen Council", "refs": ["p1", "p2"],
                 "roles": [{"role": "initiator", "refs": ["p1"]}, {"role": "operator", "refs": ["p2"]},
                           {"role": "claim_source", "refs": ["p2"]}]},
                {"id": "e2", "kind": "product", "named": True, "surface": "StudyLink", "refs": ["p1"],
                 "roles": [{"role": "subject", "refs": ["p1"]}]},
                {"id": "e3", "kind": "group", "named": False, "surface": "local pupils", "refs": ["p1"],
                 "roles": [{"role": "affected", "refs": ["p1"]}]}],
            "facts": [{"predicate": "covered_school_count", "subject": "e2",
                       "value": {"surface": "12 schools", "refs": ["p2"]},
                       "status": "stated", "attributed_to": "e1", "support_refs": ["p2"]}],
            "participants_overflow": False, "facts_overflow": False}}
    return build_input(article), output
