"""Pure diagnostics and explicitly counterfactual structural pair replay.

Only an audited caller may obtain/retain the supplied research packets and model
responses. No store, files, tools, model or network is read here. Diagnostics
contain counts and timestamps only; replay records contain restricted evidence
and must remain in protected storage. Structural replay never changes an old
validation, reruns a prompt, infers event identity, or creates human gold.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from jsonschema import Draft202012Validator

from .common import Json, ResearchError, canonical
from .event_pair_reference import (
    MAX_REASON_CHARS,
    MIN_SUPPORT_ALNUM,
    build_request,
    validate_answer,
)
from .luna_lead_answers import EVENT_FIELDS, answer_schema, validate_request


CONTRACT = "event-evaluation-structural-diagnostics-v1"
_STATUS = {"valid", "invalid", "unknown", "error", "pending", "failed"}


def _rows(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _object(value: Any) -> Json:
    return value if isinstance(value, dict) else {}


def _bytes(value: Any) -> int | None:
    try:
        return len(canonical(value).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def _time(value: Any) -> tuple[str | None, datetime | None]:
    if not isinstance(value, str):
        return None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (value, parsed) if parsed.tzinfo is not None else (None, None)
    except ValueError:
        return None, None


def _claims(request: Json, payload: Json) -> list[Json]:
    evidence = {p["id"]: p for p in _rows(request.get("evidence"))
                if isinstance(p, dict) and isinstance(p.get("id"), str)}
    valid = []
    for claim in _rows(payload.get("claims")):
        item = _object(claim)
        passage = evidence.get(item.get("passage_id")) if isinstance(item.get("passage_id"), str) else None
        quote = item.get("quote")
        if (passage is not None and item.get("source_version") == passage.get("source_id")
                and isinstance(quote, str) and quote.strip()
                and isinstance(passage.get("text"), str) and quote in passage["text"]):
            valid.append(item)
    return valid


def technical_failure_details(old_request: Json, retained_response: Any, outcome: Json) -> Json:
    """Return no evidence, rationale, identifiers, actor names or exception text.

    Byte counts describe canonical JSON of the supplied objects, not hidden
    provider traffic. ISO timestamps are raw caller-supplied local observations.
    Unsupported fields mean missing exact source-bound claim mapping only.
    """
    request = _object(old_request)
    response = _object(retained_response)
    payload, raw = _object(response.get("payload")), _object(response.get("raw_response"))
    articles, passages = _rows(request.get("articles")), _rows(request.get("evidence"))
    sources = {a["source_version"] for a in articles
               if isinstance(a, dict) and isinstance(a.get("source_version"), str)}
    expected_ids = {p["id"] for p in passages if isinstance(p, dict) and isinstance(p.get("id"), str)}
    inspected = [p for p in _rows(payload.get("inspected_passage_ids")) if isinstance(p, str)]
    events = [e for e in _rows(payload.get("events")) if isinstance(e, dict)]
    event_sources = [e["source_version"] for e in events if isinstance(e.get("source_version"), str)]
    anchor = request.get("anchor_source")
    expected_candidates = (sources - {anchor if isinstance(anchor, str) else None}
                           if request.get("mode") == "anchor" else set())
    relations = [r for r in _rows(payload.get("relations")) if isinstance(r, dict)]
    relation_sources = [r["source_version"] for r in relations if isinstance(r.get("source_version"), str)]
    valid_claims = _claims(request, payload)
    supported: dict[str, set[str]] = {}
    for claim in valid_claims:
        supported.setdefault(claim["source_version"], set()).update(
            field for field in _rows(claim.get("supports")) if field in EVENT_FIELDS)
    unsupported: Counter[str] = Counter({field: 0 for field in EVENT_FIELDS})
    for event in events:
        for field in EVENT_FIELDS:
            value = event.get(field)
            material = bool(value) if field == "actors" else isinstance(value, str) and value != "unknown"
            source = event.get("source_version")
            mapped = supported.get(source, set()) if isinstance(source, str) else set()
            if material and field not in mapped:
                unsupported[field] += 1
    started, start = _time(raw.get("started_at"))
    ended, end = _time(raw.get("ended_at"))
    latency = (end - start).total_seconds() if start is not None and end is not None else None
    if latency is not None and latency < 0:
        latency = None
    status = _object(outcome).get("status")
    return {
        "contract": CONTRACT,
        "outcome_status": status if isinstance(status, str) and status in _STATUS else "unavailable",
        "articles": len(articles), "passages": len(passages),
        "missing_inspected_ids": len(expected_ids - set(inspected)),
        "extra_inspected_ids": len(set(inspected) - expected_ids),
        "duplicate_inspected_ids": len(inspected) - len(set(inspected)),
        "missing_events": len(sources - set(event_sources)),
        "extra_event_sources": len(set(event_sources) - sources),
        "duplicate_event_sources": len(event_sources) - len(set(event_sources)),
        "invalid_quote_count": len(_rows(payload.get("claims"))) - len(valid_claims),
        "unsupported_event_fields": dict(unsupported),
        "relation_coverage": {"expected": len(expected_candidates), "returned": len(relations),
                              "missing": len(expected_candidates - set(relation_sources)),
                              "extra": len(set(relation_sources) - expected_candidates),
                              "duplicates": len(relation_sources) - len(set(relation_sources))},
        "old_schema_valid": not list(Draft202012Validator(answer_schema()).iter_errors(response.get("payload"))),
        "input_bytes": _bytes(old_request), "output_bytes": _bytes(retained_response),
        "output_payload_bytes": _bytes(response.get("payload")),
        "byte_measure": "canonical JSON of caller-supplied request/retained response; not wire traffic",
        "started_at": started, "ended_at": ended, "latency_seconds": latency,
        "timestamp_basis": "raw supplied local observations; unavailable or invalid timestamps stay null",
    }


def _transport_reason(response: Json, outcome: Json) -> str | None:
    raw = _object(response.get("raw_response"))
    status = _object(outcome).get("status")
    if not isinstance(status, str) or status not in {"valid", "invalid"}:
        return "old_attempt_not_known_returned"
    if (raw.get("transport_status") != "returned" or "failure" not in raw or raw.get("failure") is not None
            or raw.get("unknown_outcome") is not False or type(raw.get("exit_code")) is not int
            or raw["exit_code"] != 0):
        return "transport_not_known_clean_return"
    events = raw.get("events")
    if not isinstance(events, list) or not events:
        return "transport_completion_unobserved"
    completed = False
    for event in events:
        if not isinstance(event, dict):
            return "transport_event_unrecognized"
        kind = event.get("type")
        if kind == "turn.completed":
            completed = True
        elif kind in {"thread.started", "turn.started"}:
            pass
        elif kind in {"item.started", "item.updated", "item.completed"}:
            item = _object(event.get("item"))
            if item.get("type") not in {"agent_message", "reasoning"}:
                return "transport_tool_or_unrecognized_activity"
        else:
            return "transport_tool_or_unrecognized_activity"
    return None if completed else "transport_completion_unobserved"


def replay_anchor_pairs(old_request: Json, retained_response: Any, outcome: Json,
                        *, versions: dict[str, str]) -> Json:
    """Reuse only recorded labels through a NEW version-bound structural test.

    ``newrequest`` is a counterfactual validation target, never an executed model
    prompt. The old executed request, complete context and outcome references
    remain linked. This operation cannot repair or relabel an old invalid row.
    Protected relation records may contain source IDs, evidence and old text;
    only ``summary`` is suitable as a source-free diagnostic overview.
    """
    request, response = _object(old_request), _object(retained_response)
    payload = _object(response.get("payload"))
    articles = [a for a in _rows(request.get("articles")) if isinstance(a, dict)]
    anchor = request.get("anchor_source")
    candidates = [a.get("source_version") for a in articles if a.get("source_version") != anchor]
    common_reason = _transport_reason(response, outcome)
    if common_reason is None:
        try:
            validate_request(request)
            if request.get("mode") != "anchor":
                common_reason = "old_request_not_anchor"
        except ResearchError:
            common_reason = "old_request_integrity_invalid"
    if common_reason is None and list(Draft202012Validator(answer_schema()).iter_errors(response.get("payload"))):
        common_reason = "old_answer_schema_invalid"
    valid_claims = _claims(request, payload)
    records = []
    for candidate in candidates:
        record: Json = {"anchor": anchor, "candidate": candidate, "label": None,
                        "eligibilityreason": common_reason, "newrequest": None, "newanswer": None,
                        "newvalidation": None,
                        "original_refs": {key: outcome.get(key) for key in
                                          ("request", "response", "assessment", "attempt")},
                        "provenance": "recorded old-context relation; new request is counterfactual, not executed"}
        if common_reason is not None:
            records.append(record)
            continue
        relations = [r for r in payload["relations"] if r["source_version"] == candidate]
        endpoints = {source: [event for event in payload["events"] if event["source_version"] == source]
                     for source in (anchor, candidate)}
        if len(relations) != 1:
            record["eligibilityreason"] = "relation_missing_or_duplicate"
        elif any(len(values) != 1 for values in endpoints.values()):
            record["eligibilityreason"] = "endpoint_event_missing_or_duplicate"
        elif any(values[0]["multiple_focal_events"] is not False for values in endpoints.values()):
            record["eligibilityreason"] = "endpoint_multiple_focal_events"
        else:
            leads = {article["source_version"]: article for article in articles}
            try:
                newrequest = build_request(left=leads[anchor], right=leads[candidate], versions=versions)
                mapping = {span["lead_span_id"]: span for span in newrequest["evidence"]}
                claims = [claim for claim in valid_claims
                          if claim["source_version"] in endpoints and claim["passage_id"] in mapping
                          and sum(char.isalnum() for char in claim["quote"]) >= MIN_SUPPORT_ALNUM]
                support = {mapping[claim["passage_id"]]["id"] for claim in claims}
                newanswer = {"label": relations[0]["label"],
                             "support_span_ids": [span["id"] for span in newrequest["evidence"]
                                                  if span["id"] in support],
                             "reason": payload["rationale"][:MAX_REASON_CHARS]}
                newvalidation = validate_answer(newrequest, newanswer)
                record.update(label=relations[0]["label"], eligibilityreason="eligible_structural_replay",
                              newrequest=newrequest, newanswer=newanswer, newvalidation=newvalidation)
                record["original_refs"].update({
                    "relation_index": payload["relations"].index(relations[0]),
                    "claim_indices": [payload["claims"].index(claim) for claim in claims],
                    "reason_transform": "original rationale prefix, at most 600 Unicode characters",
                })
            except (ResearchError, KeyError):
                record["eligibilityreason"] = "new_pair_structural_validation_failed"
        records.append(record)
    counts = Counter(record["eligibilityreason"] for record in records)
    labels = Counter(record["label"] for record in records if record["label"] is not None)
    return {"relations": records, "summary": {
        "contract": CONTRACT, "expected_pairs": len(records),
        "eligible_pairs": counts["eligible_structural_replay"],
        "ineligible_pairs": len(records) - counts["eligible_structural_replay"],
        "eligibility_counts": dict(counts), "eligible_label_counts": dict(labels),
        "new_model_calls": 0, "old_rows_modified": 0, "human_validated": False,
        "semantic_entailment_validated": False, "whole_group_purity_validated": False,
        "interpretation": "new structural replay of old-context labels; old invalidity remains unchanged",
    }}
