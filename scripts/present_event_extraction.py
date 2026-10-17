"""Audit and display saved event-extraction results without new model inference.

This is an additive report operation. It never invokes the extraction executor,
changes an execution plan, retries a task, accepts findings, or reads vectors.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

from newsresearch.common import Config, Context, Json, ResearchError, digest, require_active
from newsresearch import event_extraction_contract as contract
from newsresearch.runtime import Research, audited_handler


METHOD = "saved-text-event-extraction-v1"
REPORT_METHOD = "saved-text-event-extraction-presentation-v1"
RESULT_KIND = "luna_group_validation_result"
# Capture before potentially long runtime preflight, not from an edited file later.
SCRIPT_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def escape(value: Any) -> str:
    text = str(value if value is not None else "unavailable")
    for char in "\\`*_{}[]<>|":
        text = text.replace(char, "\\" + char)
    return text.replace("\r", " ").replace("\n", " ")


def source_link(source: Json) -> str:
    title = escape(source.get("title") or source["source_version"])
    url = source.get("url")
    if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and not any(c in url for c in "<>\r\n"):
        return f"[{title}](<{url}>)"
    return title


def render_time(value: Json | None) -> str:
    if value is None:
        return "unavailable"
    interval = (f"{value['start']} to {value['end']}" if value["start"] else "unresolved dates")
    return f"{escape(value['text'])} ({interval}; {value['precision']}; {value['basis']})"


def evidence_lines(mention: Json, *, compact: bool) -> list[str]:
    """Group identical quotes without interpreting or dropping field provenance."""
    entries: list[Json] = list(mention["evidence"])
    if not compact:
        for name in ("participants", "locations", "attribution", "identifiers"):
            for item in mention[name]:
                entries.extend(item["evidence"])
        entries.extend(mention["factuality"]["evidence"])
        if mention["time"]:
            entries.extend(mention["time"]["evidence"])
    else:
        entries = entries[:1]
    grouped: dict[tuple[Any, ...], list[str]] = {}
    for item in entries:
        key = (item["quote"], item["passage_id"], item["source_start"], item["source_end"])
        grouped.setdefault(key, [])
        if item["field"] not in grouped[key]:
            grouped[key].append(item["field"])
    lines = []
    for (quote, passage, start, end), fields in grouped.items():
        suffix = "" if compact else f"; fields {', '.join(escape(field) for field in fields)}"
        lines.append(f"  Evidence: “{escape(quote)}” (passage `{passage}`, source characters {start}–{end}{suffix}).")
    return lines


def rejected_diagnostic(retained: Json, request: Json) -> Json:
    """Deterministic rejected-response inspection, never repair or acceptance."""
    raw = retained.get("raw_response")
    raw = raw if isinstance(raw, dict) else {}
    payload = retained.get("payload")
    origin = "retained_payload"
    if not isinstance(payload, dict):
        finals = []
        for event in raw.get("events", []) if isinstance(raw.get("events"), list) else []:
            if not isinstance(event, dict) or event.get("type") != "item.completed":
                continue
            item = event.get("item")
            if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                finals.append(item["text"])
        payload = None
        origin = "unavailable"
        if len(finals) == 1:
            try:
                candidate = json.loads(finals[0])
                if isinstance(candidate, dict):
                    payload, origin = candidate, "recovered_rejected_agent_message"
            except (TypeError, ValueError):
                pass
    def safe(value: Any) -> str | None:
        return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,150}", value) else None
    diagnostic: Json = {"disposition": "rejected_unvalidated_not_event_findings", "payload_origin": origin,
        "transport_failure": safe(raw.get("failure")), "transport_status": safe(raw.get("transport_status")),
        "observed_model": retained.get("model"), "usage": retained.get("usage"),
        "request_id": retained.get("request_id"), "exit_code": raw.get("exit_code"),
        "stdout_bytes": len(raw["stdout"].encode("utf-8")) if isinstance(raw.get("stdout"), str) else None,
        "stderr_bytes": len(raw["stderr"].encode("utf-8")) if isinstance(raw.get("stderr"), str) else None,
        "schema_errors": [], "quote_failures": [], "literal_failures": [], "replay_code": "payload_unavailable",
        "preview": [], "recovered_payload": payload, "accepted_or_provisional_mentions_added": 0}
    if payload is None:
        return diagnostic
    diagnostic["schema_errors"] = [{"path": list(error.absolute_path), "validator": error.validator}
                                   for error in Draft202012Validator(request["schema"]).iter_errors(payload)]
    try:
        contract.validate_output(payload, request)
        diagnostic["replay_code"] = "mechanically_valid_but_original_rejection_preserved"
    except ResearchError as error:
        diagnostic["replay_code"] = safe(str(error)) or "unclassified_contract_failure"
    passages = {entry["id"]: entry["text"] for entry in request["evidence"]}

    def check_quotes(value: Any, path: str) -> None:
        if isinstance(value, dict):
            if isinstance(value.get("passage_id"), str) and isinstance(value.get("quote"), str):
                text = passages.get(value["passage_id"])
                occurrences, offset = 0, -1
                if text is not None and value["quote"]:
                    while (offset := text.find(value["quote"], offset + 1)) >= 0:
                        occurrences += 1
                if occurrences != 1:
                    diagnostic["quote_failures"].append({"path": path,
                        "passage_exists": text is not None, "exact_occurrences": occurrences})
            for key, child in value.items():
                check_quotes(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                check_quotes(child, f"{path}[{index}]")

    check_quotes(payload, "output")

    def check_literal(value: Any, evidence: Any, path: str) -> None:
        if not isinstance(value, str) or not isinstance(evidence, list):
            return
        quotes = [{"passage_id": row.get("passage_id"), "quote": row["quote"]}
                  for row in evidence if isinstance(row, dict) and isinstance(row.get("quote"), str)]
        if not any(value in row["quote"] for row in quotes):
            diagnostic["literal_failures"].append({"path": path, "literal": value, "supporting_quotes": quotes})

    events = payload.get("events", []) if isinstance(payload.get("events"), list) else []
    for index, entry in enumerate(events):
        if not isinstance(entry, dict):
            continue
        prefix = f"output.events[{index}]"
        check_literal(entry.get("trigger"), entry.get("evidence"), prefix + ".trigger")
        for collection, field in (("participants", "name"), ("locations", "name"),
                                  ("attribution", "name"), ("identifiers", "value")):
            items = entry.get(collection)
            for position, item in enumerate(items if isinstance(items, list) else []):
                if isinstance(item, dict):
                    check_literal(item.get(field), item.get("evidence"), f"{prefix}.{collection}[{position}].{field}")
        if isinstance(entry.get("time"), dict):
            check_literal(entry["time"].get("text"), entry["time"].get("evidence"), prefix + ".time.text")
        if not isinstance(entry, dict) or not isinstance(entry.get("summary"), str):
            continue
        preview = {key: entry[key] for key in ("local_id", "event_type", "summary", "action", "trigger")
                   if isinstance(entry.get(key), str)}
        preview["participants"] = [{key: participant[key] for key in ("name", "type", "role")
                                    if isinstance(participant.get(key), str)}
                                   for participant in entry.get("participants", [])
                                   if isinstance(participant, dict) and isinstance(participant.get("name"), str)] \
            if isinstance(entry.get("participants"), list) else []
        diagnostic["preview"].append(preview)
    return diagnostic


def render(plan: Json, result: Json, *, compact: bool, diagnostics: Json | None = None) -> str:
    """Format stored fields only; counts are processing coverage, not dossiers."""
    lines = [f"Saved-text event extraction: **{result['status']}**.", "",
        f"{result['workflow_model_attempts']}/{plan['limits']['max_requests']} attempts; "
        f"{result['valid']} complete articles; {result['incomplete']} incomplete; "
        f"{result['invalid']} invalid; {result['unknown']} unknown; {result['unavailable']} unavailable; "
        f"{result['pending']} pending (including {result['unfilled_slots']} unfilled slots). "
        f"{result['event_count']} provisional event mentions "
        f"({result['complete_article_event_mentions']} from completed articles, "
        f"{result['incomplete_article_event_mentions']} from incomplete articles). "
        f"{result['automatic_retries']} retries; {result['embeddings_created']} new embeddings.",
        "These are unreviewed source-level model extractions, not accepted events or dossier counts. "
        "Repeated mentions across articles remain separate. Complete means mechanically valid declared coverage; "
        "semantic accuracy and event recall have not been validated. No memberships changed.",
        f"Execution obstacle: {escape(result.get('obstacle') or 'none')}. "
        "Invalid, unavailable, unknown and pending processing are not negative event findings.", ""]
    if compact and result["event_count"]:
        lines.extend(["All extracted summaries and participant entities follow; one exact supporting quote per mention. "
                      "The full protected presentation retains every field and supporting quote.", ""])
    elif compact:
        lines.extend(["No usable event mentions passed validation. Any rejected model previews below are diagnostic only; "
                      "they carry no accepted supporting evidence and remain outside the event-mention count.", ""])
    by_source = {example["source_version"]: example for example in plan["examples"]}
    for number, task in enumerate(plan["tasks"], 1):
        outcome = result["outcomes"].get(task["task_id"])
        state = outcome["status"] if outcome else "pending"
        lines.append(f"**{number}. {source_link(by_source[task['source_version']])} — {state}**")
        if not outcome or state not in {"valid", "incomplete"}:
            reason = outcome.get("error") if outcome else "not dispatched in this result"
            lines.append(f"No usable extracted event or entity output; reason: {escape(reason or state)}.")
            diagnostic = (diagnostics or {}).get(task["task_id"])
            if diagnostic:
                lines.append(f"Deterministic replay: `{diagnostic['replay_code']}`; transport failure: "
                             f"`{diagnostic['transport_failure'] or 'none recorded'}`. "
                             f"Observed model: {escape(diagnostic['observed_model'])}. "
                             f"Retained stdout/stderr bytes: {diagnostic['stdout_bytes']}/{diagnostic['stderr_bytes']}; "
                             f"acceptance limit: {plan['config']['max_output_bytes']} bytes.")
                lines.append(f"Schema failures: {escape(json.dumps(diagnostic['schema_errors']))}; "
                             f"exact-quote failures: {escape(json.dumps(diagnostic['quote_failures']))}. "
                             f"Observed usage: {escape(json.dumps(diagnostic['usage']))}.")
                for failure in diagnostic["literal_failures"]:
                    lines.append(f"Literal mismatch at `{failure['path']}`: returned “{escape(failure['literal'])}” "
                                 "does not occur exactly in any quote supplied for that field.")
                    for quote in failure["supporting_quotes"]:
                        lines.append(f"  Model-supplied supporting quote: “{escape(quote['quote'])}” "
                                     f"(passage `{escape(quote['passage_id'])}`).")
                if diagnostic["preview"]:
                    lines.extend(["", f"**Rejected, unvalidated model-output preview ({len(diagnostic['preview'])} raw proposals). "
                                  "These are not usable extractions and do not enter the event-mention count.**", ""])
                    for preview in diagnostic["preview"]:
                        entities = "; ".join(f"{escape(p['name'])} [{escape(p.get('type'))}; {escape(p.get('role'))}]"
                                             for p in preview["participants"]) or "none returned"
                        lines.append(f"- REJECTED proposal {escape(preview.get('local_id'))}: {escape(preview['summary'])}")
                        lines.append(f"  Rejected entities: {entities}.")
            lines.append("")
            continue
        validation = outcome["validation"]
        lines.append(f"Extraction status: {validation['extraction_status']}; "
                     f"declared coverage complete: {str(validation['coverage_complete']).lower()}; "
                     f"mentions: {validation['event_count']}.")
        if validation["limitation"]:
            lines.append(f"Model limitation: {escape(validation['limitation'])}")
        if not validation["events"]:
            lines.append("No event mentions returned. This is an unreviewed model outcome, not a verified absence of events.")
        lines.append("")
        for mention in validation["events"]:
            lines.append(f"- **{escape(mention['local_id'])}: {escape(mention['summary'])}** "
                         f"({escape(mention['event_type'])}; {mention['prominence']}; {mention['specificity']}).")
            entities = "; ".join(f"{escape(p['name'])} [{p['type']}; {escape(p['role'])}]"
                                 for p in mention["participants"]) or "none returned"
            places = "; ".join(escape(p["name"]) for p in mention["locations"]) or "unavailable"
            factuality = mention["factuality"]
            conditional = "unknown" if factuality["conditional"] is None else str(factuality["conditional"]).lower()
            lines.append(f"  Entities: {entities}. Time: {render_time(mention['time'])}. Place: {places}.")
            lines.append(f"  Source factuality: {factuality['polarity']}, {factuality['actuality']}, "
                         f"{factuality['certainty']}, conditional={conditional}.")
            if not compact:
                attributions = "; ".join(escape(p["name"]) for p in mention["attribution"]) or "none returned"
                identifiers = "; ".join(f"{escape(p['kind'])}: {escape(p['value'])}"
                                        for p in mention["identifiers"]) or "none returned"
                lines.append(f"  Action: {escape(mention['action'])}; exact trigger: “{escape(mention['trigger'])}”. "
                             f"Attribution: {attributions}. Identifiers: {identifiers}. "
                             f"Mention ID: `{mention['mention_id']}`.")
            lines.extend(evidence_lines(mention, compact=compact))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_chat(plan: Json, result: Json, diagnostics: Json) -> str:
    """Concise exact-field display; omit pending titles and repetitive diagnostics."""
    rejected_count = sum(len(value["preview"]) for value in diagnostics.values())
    lines = [f"**Event extraction pilot: {result['status']}.**", "",
        f"{result['workflow_model_attempts']}/{plan['limits']['max_requests']} article attempts; "
        f"{result['valid']} complete, {result['incomplete']} incomplete, {result['invalid']} invalid, "
        f"{result['unknown']} unknown, {result['unavailable']} unavailable; {result['pending']} pending. "
        f"{result['event_count']} usable provisional event mentions; {rejected_count} rejected raw proposals. "
        f"{result['automatic_retries']} retries; **{result['embeddings_created']} new embeddings**.",
        "Usable mentions are unreviewed model extractions, not accepted events or dossier counts. "
        "Rejected proposals below failed validation and must not be used for grouping. "
        "Missing and pending processing are not negative findings. No memberships changed.", ""]
    sources = {example["source_version"]: example for example in plan["examples"]}
    for task in plan["tasks"]:
        outcome = result["outcomes"].get(task["task_id"])
        if outcome is None:
            continue
        lines.extend([f"Source: {source_link(sources[task['source_version']])} — **{outcome['status']}**.", ""])
        if outcome["status"] in {"valid", "incomplete"}:
            validation = outcome["validation"]
            lines.append(f"Model status: {validation['extraction_status']}; "
                         f"declared complete coverage: {str(validation['coverage_complete']).lower()}.")
            if validation["limitation"]:
                lines.append(f"Model limitation: {escape(validation['limitation'])}")
            if validation["events"]:
                lines.extend(["", "| Unreviewed event summary | Participant entities |", "| --- | --- |"])
                for event in validation["events"]:
                    entities = "; ".join(f"{escape(item['name'])} [{escape(item['type'])}; {escape(item['role'])}]"
                                         for item in event["participants"]) or "none returned"
                    lines.append(f"| {escape(event['summary'])} | {entities} |")
            else:
                lines.append("No event mentions returned; this is not a verified absence of events.")
            lines.append("")
            continue
        diagnostic = diagnostics.get(task["task_id"])
        if not diagnostic:
            lines.extend([f"No usable event or entity output. Recorded reason: {escape(outcome.get('error') or outcome['status'])}.", ""])
            continue
        lines.append(f"Rejection replay: `{diagnostic['replay_code']}`. "
                     f"Transport failure: `{diagnostic['transport_failure'] or 'none recorded'}`. "
                     f"Literal mismatches: **{len(diagnostic['literal_failures'])}**; "
                     f"schema failures: {len(diagnostic['schema_errors'])}; "
                     f"exact-quote failures: {len(diagnostic['quote_failures'])}.")
        if diagnostic["literal_failures"]:
            first = diagnostic["literal_failures"][0]
            lines.append(f"First mismatch: `{first['path']}` returned “{escape(first['literal'])}”, "
                         "which does not occur exactly in its supplied evidence.")
            if first["supporting_quotes"]:
                quote = first["supporting_quotes"][0]
                lines.append(f"Supplied quote: “{escape(quote['quote'])}” (passage `{escape(quote['passage_id'])}`).")
            else:
                lines.append("No supporting quote was supplied for that field.")
        if diagnostic["preview"]:
            lines.extend(["", "**Rejected, unvalidated raw model output — verbatim summaries and participant fields:**", "",
                          "| Rejected raw event proposal | Rejected participant entities |", "| --- | --- |"])
            for preview in diagnostic["preview"]:
                entities = "; ".join(f"{escape(item['name'])} [{escape(item.get('type'))}; {escape(item.get('role'))}]"
                                     for item in preview["participants"]) or "none returned"
                lines.append(f"| {escape(preview['summary'])} | {entities} |")
        else:
            lines.append("No retained parseable event proposals are available.")
        lines.append("")
    lines.append(f"Execution obstacle: {escape(result.get('obstacle') or 'none')}. "
                 "This report only replays saved output; it does not retry, repair or accept it.")
    return "\n".join(lines)


def verify_result(engine: Any, session: str, plan_id: str, plan: Json, result: Json) -> Json:
    """Replay mechanical checks against exact saved requests, never a new model."""
    require_active(engine, session)
    diagnostics: Json = {}
    if (plan.get("method") != METHOD or result.get("method") != METHOD
            or result.get("plan") != plan_id or plan.get("versions") != result.get("versions")
            or plan.get("study_key") != result.get("study_key")
            or Path(plan["owner_workspace"]).resolve() != engine.ledger.root.resolve()):
        raise ResearchError("event_extraction_report_binding_changed")
    contract_hash = hashlib.sha256(Path(contract.__file__).read_bytes()).hexdigest()
    if plan["implementation"].get("event_extraction_contract.py") != contract_hash:
        raise ResearchError("event_extraction_report_requires_exact_contract")
    tasks = {task["task_id"]: task for task in plan["tasks"]}
    if (len(tasks) != len(plan["tasks"]) or not set(result["outcomes"]) <= set(tasks)
            or len({task["source_version"] for task in tasks.values()}) != len(tasks)
            or {e["source_version"] for e in plan["examples"]} != {t["source_version"] for t in tasks.values()}
            or len(plan["examples"]) != len(tasks)):
        raise ResearchError("event_extraction_report_task_frame_changed")
    for task_id, task in tasks.items():
        if task_id != digest({"study_binding": plan["study_binding"], "source_version": task["source_version"]}):
            raise ResearchError("event_extraction_report_task_identity_changed")
        outcome = result["outcomes"].get(task_id)
        if outcome is None:
            continue
        if (outcome.get("task_id") != task_id or outcome.get("source_version") != task["source_version"]
                or outcome.get("phase") != task["phase"]
                or outcome.get("status") not in {"valid", "incomplete", "invalid", "unknown", "unavailable"}):
            raise ResearchError("event_extraction_report_outcome_identity_changed")
        if outcome.get("assessment"):
            saved = engine.ledger.get(outcome["assessment"], "event_extraction_assessment")
            if saved != {key: value for key, value in outcome.items() if key != "assessment"}:
                raise ResearchError("event_extraction_report_assessment_changed")
            if saved.get("plan") != plan_id or saved.get("request") != task["request"]:
                raise ResearchError("event_extraction_report_assessment_binding_changed")
        elif outcome["status"] in {"valid", "incomplete", "invalid"}:
            raise ResearchError("event_extraction_report_assessment_missing")
        if outcome["status"] in {"valid", "incomplete"}:
            request = engine.ledger.artifacts.read(task["request"])
            if (request["versions"] != plan["versions"]
                    or request["source"]["source_version"] != task["source_version"]):
                raise ResearchError("event_extraction_report_request_binding_changed")
            retained = engine.ledger.artifacts.read(outcome["response"])
            validation = contract.validate_output(outcome["output"], request)
            processing = "complete" if validation["coverage_complete"] and validation["extraction_status"] != "insufficient_evidence" else "incomplete"
            if (retained["payload"] != outcome["output"] or validation != outcome["validation"]
                    or outcome["events"] != validation["events"] or outcome["event_count"] != validation["event_count"]
                    or outcome["processing"] != processing
                    or outcome["status"] != ("valid" if processing == "complete" else "incomplete")):
                raise ResearchError("event_extraction_report_validation_changed")
            engine.ledger.append(session, "event.extraction.presentation.inspected", {
                "plan": plan_id, "task_id": task_id, "assessment": outcome["assessment"],
                "request": task["request"], "response": outcome["response"],
                "passage_ids": [row["id"] for row in request["evidence"]],
                "event_mentions": validation["event_count"], "semantic_review": False,
                "human_reading_observed": False})
        elif outcome.get("events") or outcome.get("event_count"):
            raise ResearchError("event_extraction_report_unusable_output_has_events")
        elif outcome.get("response"):
            request = engine.ledger.artifacts.read(task["request"])
            contract.validate_request(request)
            if (request["versions"] != plan["versions"]
                    or request["source"]["source_version"] != task["source_version"]):
                raise ResearchError("event_extraction_report_request_binding_changed")
            retained = engine.ledger.artifacts.read(outcome["response"])
            diagnostics[task_id] = {**rejected_diagnostic(retained, request),
                "plan": plan_id, "task_id": task_id, "request": task["request"], "response": outcome["response"],
                "assessment": outcome.get("assessment"), "original_status": outcome["status"]}
            engine.ledger.append(session, "event.extraction.rejected_output.inspected", {
                "plan": plan_id, "task_id": task_id, "request": task["request"], "response": outcome["response"],
                "original_status": outcome["status"], "replay_code": diagnostics[task_id]["replay_code"],
                "passage_ids": [row["id"] for row in request["evidence"]],
                "human_reading_observed": False,
                "new_inference": False, "accepted_or_provisional_mentions_added": 0})
    counts = Counter(row["status"] for row in result["outcomes"].values())
    complete_mentions = sum(row["event_count"] for row in result["outcomes"].values() if row["status"] == "valid")
    incomplete_mentions = sum(row["event_count"] for row in result["outcomes"].values() if row["status"] == "incomplete")
    expected = {**{name: counts[name] for name in ("valid", "incomplete", "invalid", "unknown", "unavailable")},
        "outcome_counts": dict(counts), "event_count": complete_mentions + incomplete_mentions,
        "complete_article_event_mentions": complete_mentions, "incomplete_article_event_mentions": incomplete_mentions,
        "pending": len(tasks) - len(result["outcomes"]) + plan["selection"]["unfilled_slots"],
        "unfilled_slots": plan["selection"]["unfilled_slots"], "embeddings_created": 0,
        "automatic_retries": 0, "memberships_changed": False, "human_validated": False}
    if any(result.get(key) != value for key, value in expected.items()):
        raise ResearchError("event_extraction_report_coverage_changed")
    return diagnostics


class EventExtractionReportResearch(Research):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        correction_fields = {"supersedes_presentations", "correction_reason"}
        if (set(data) not in ({"phase", "result"}, {"phase", "result"} | correction_fields)
                or data["phase"] != "report" or not self.config.offline):
            raise ResearchError("event_extraction_report_offline_fields_required")
        prior_ids = data.get("supersedes_presentations", [])
        correction_reason = data.get("correction_reason")
        if correction_fields <= set(data) and (not isinstance(prior_ids, list) or not prior_ids
                or any(not isinstance(value, str) or not value for value in prior_ids)
                or len(prior_ids) != len(set(prior_ids))
                or not isinstance(correction_reason, str) or not correction_reason.strip()):
            raise ResearchError("event_extraction_report_correction_fields_invalid")
        profile = self._version(session, context, {"kind": "profile", "key": REPORT_METHOD,
            "content": {"mode": "exploratory", "method": REPORT_METHOD, "population_estimate": False,
                "script_sha256": SCRIPT_SHA256, "script_hash_observed": "module load, before runtime preflight",
                "procedure": "Read the named result and plan, check immutable bindings, replay exact request/output mechanics, format saved fields and all task statuses without inference, preserve full and compact presentations. For rejected outputs, inspect retained JSON or the single retained final agent_message JSON; report safe validator/transport codes, exact overlapping-quote and literal-to-own-evidence diagnostics, and literal summary/entity previews explicitly rejected and unvalidated, outside event counts. No repair or status changes.",
                "compact_rule": "All summaries and participant entities; one first event quote per mention. Full presentation retains all fields and field evidence.",
                "chat_rule": "Coverage plus every processed source link and every valid/incomplete or explicitly rejected raw summary and participant name/type/role, verbatim in tables. Omit pending source titles; show safe rejection codes, total literal mismatch count and only the first literal mismatch with its first supplied quote. No semantic inference or promotion of rejected output.",
                "counts": "Source-processing coverage and provisional mentions only, never unique events or dossiers",
                "new_models": 0, "new_embeddings": 0, "semantic_review": False},
            "amend_latest": True, "reason": "Register exact current report implementation and deterministic diagnostic rules before inspecting saved output"})["id"]
        result = self.ledger.get(data["result"], RESULT_KIND)
        plan_id = result["plan"]
        plan = self.ledger.get(plan_id, "luna_group_validation_plan")
        if plan.get("method") != METHOD or result.get("method") != METHOD:
            raise ResearchError("event_extraction_report_wrong_method")
        for kind, reference in result["versions"].items():
            self.ledger.get(reference, kind)
        bound = Context(context.objective, context.actor, result["versions"])
        for previous_id in prior_ids:
            previous = self.ledger.get(previous_id, "result_presentation")
            if (previous.get("versions") != result["versions"]
                    or {"kind": RESULT_KIND, "id": data["result"]} not in previous.get("results", [])):
                raise ResearchError("event_extraction_report_correction_result_changed")
        correction_note = None
        if prior_ids:
            correction_note = self._version(session, bound, {"kind": "note",
                "key": REPORT_METHOD + ":correction:" + digest({"result": data["result"], "prior": prior_ids}),
                "content": {"method": REPORT_METHOD, "result": data["result"], "plan": plan_id,
                    "versions": result["versions"], "supersedes_presentations": prior_ids,
                    "correction_reason": correction_reason, "display_profile": profile,
                    "prior_presentations_preserved": True, "model_results_changed": False,
                    "new_model_calls": 0, "new_embeddings": 0},
                "amend_latest": True, "reason": correction_reason})["id"]
        note = self._version(session, bound, {"kind": "note", "key": REPORT_METHOD + ":" + data["result"],
            "content": {"method": REPORT_METHOD, "display_profile": profile, "result": data["result"],
                "plan": plan_id, "versions": result["versions"], "new_inference": False,
                "correction_note": correction_note,
                "purpose": "Show exact saved event mentions and entities; structurally invalid outputs remain unusable, no semantic inference or accepted findings"},
            "amend_latest": True, "reason": "Bind the exact current report profile and append any declared presentation correction"})["id"]
        diagnostics = verify_result(self, session, plan_id, plan, result)
        diagnostic_ref = self.ledger.artifacts.put({"method": REPORT_METHOD, "result": data["result"],
            "profile": profile, "note": note, "diagnostics": diagnostics, "new_inference": False})
        self.ledger.append(session, "event.extraction.report_diagnostics.saved", {"artifact": diagnostic_ref,
            "result": data["result"], "accepted_or_provisional_mentions_added": 0})
        presentations = {}
        for label, compact in (("full", False), ("compact", True)):
            presentations[label] = self._record_presentation(session, bound, {
                "results": [{"kind": RESULT_KIND, "id": data["result"]},
                            {"kind": "luna_group_validation_plan", "id": plan_id}],
                "markdown": render(plan, result, compact=compact, diagnostics=diagnostics),
                "destination": "private_file" if label == "full" else "codex_chat",
                "status": "prepared_for_delivery"})
        presentations["chat"] = self._record_presentation(session, bound, {
            "results": [{"kind": RESULT_KIND, "id": data["result"]},
                        {"kind": "luna_group_validation_plan", "id": plan_id}],
            "markdown": render_chat(plan, result, diagnostics), "destination": "codex_chat",
            "status": "prepared_for_delivery"})
        self.ledger.append(session, "event.extraction.presentation.prepared", {
            "result": data["result"], "plan": plan_id, "profile": profile, "note": note,
            "correction_note": correction_note, "supersedes_presentations": prior_ids,
            "presentations": {label: value["id"] for label, value in presentations.items()},
            "model_calls": 0, "embeddings_created": 0, "ui_delivery_verified": False})
        return {"result": data["result"], "plan": plan_id, "profile": profile, "note": note,
                "correction_note": correction_note,
                "presentations": presentations, "diagnostic_artifact": diagnostic_ref,
                "model_calls": 0, "embeddings_created": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--actor", default="codex:event-extraction-presentation")
    parser.add_argument("--supersedes-presentations", help="Comma-separated retained presentation IDs for this same result")
    parser.add_argument("--correction-reason")
    args = parser.parse_args()
    if bool(args.supersedes_presentations) != bool(args.correction_reason):
        parser.error("Presentation correction requires both --supersedes-presentations and --correction-reason")
    payload: Json = {"phase": "report", "result": args.result}
    if args.supersedes_presentations:
        payload.update(supersedes_presentations=[item.strip() for item in args.supersedes_presentations.split(",")],
                       correction_reason=args.correction_reason)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    config = Config.load(Path(__file__).resolve().parents[1] / "research.toml")
    engine = EventExtractionReportResearch(args.workspace, config=replace(config, offline=True))
    try:
        report = engine.execute("luna_group_validation", payload,
            objective="Show all saved provisional event mentions and entities from the authorized extraction pilot, with coverage and exact evidence; no new inference",
            actor=args.actor)
        print(report["presentations"]["chat"]["markdown"])
        for label, presentation in report["presentations"].items():
            print(f"\n{label.capitalize()} presentation: {presentation['id']}\nProtected path: {presentation['content_path']}")
        print(f"\nDiagnostic artifact: {report['diagnostic_artifact']}\nCorrection note: {report['correction_note'] or 'none'}")
        return 0
    finally:
        engine.close()


if __name__ == "__main__":
    raise SystemExit(main())
