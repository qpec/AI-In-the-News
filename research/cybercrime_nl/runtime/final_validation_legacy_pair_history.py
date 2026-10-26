"""One historical conversational pair family, never a current reference label.

Consumes already verified, scoped HistoryOwner readers; opens no owner and makes
no calls. Complete retained request bodies identify the old compared inputs, but
only recorded windows plus a submitted substantive reply establish P exposure.
This does not prove attention or a full reading. Handoff preparation alone never
establishes P. Every identified physical pair attempt remains a primary no-retry
blocker, including an orphan or mechanically invalid reply. Its old definition,
unobserved model and conversational transport are incompatible with current Y.

Native-origin declarations, complete ledger/scope verification and cross-study
reconciliation belong to the audited caller. Copies must match their supplied
original reader. This bounded contribution never certifies complete history.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys

import final_validation_history as history
import final_validation_legacy_prior as prior
import final_validation_projection as projection
from newsresearch.common import digest

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import check_provider_event_labels as legacy  # noqa: E402

VERSION = "final-validation-provider-label-history-v1"
FAMILY = "provider-event-label-current-conversation-v1"
PLAN, HANDOFF, JUDGMENT = "provider_label_plan", "provider_label_handoff", "provider_label_judgment"
ROLE_POLICY = {
    "version": "named-conversational-pair-reference-as-primary-blocker-v1",
    "family": FAMILY, "historical_role": "conversational_pair_reference",
    "final_validation_role": "primary", "infers_qc_or_adjudication": False,
    "current_reference_compatible": False,
}
PHYSICAL_ID_POLICY = {
    "version": "verified-source-id-and-original-attempt-v1",
    "owner_sha256": "digest(verified_original_source_id)",
    "attempt_id": "digest([verified_original_source_id, original_attempt])",
    "prior_event_id": "original_attempt, scoped by verified_original_source_id",
}
ACKNOWLEDGEMENT = "submitted-substantive-reply-and-exact-recorded-source-windows-v1"
RESPONSE_FIELDS = ["pair", "label", "rationale", "event_a", "event_b", "quote_a", "quote_b"]


def require(value, code):
    if not value:
        raise ValueError("legacy_pair_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), Path(history.__file__), Path(legacy.__file__),
             SCRIPTS / "audit_article_scope_metadata.py")
    return {**prior.implementation(), **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _plan(row, value, rows):
    require(row["logical_key"] == FAMILY and value["method"] == legacy.METHOD == FAMILY, "plan_family")
    versions = value.get("versions")
    require(isinstance(versions, dict) and set(versions) == {
        "protocol", "selection", "question", "dossier_definition", "codebook", "prompt", "profile"}, "plan_versions")
    content = {}
    for kind, identity in versions.items():
        entry = rows.get(identity)
        if entry is None:
            return False
        version_row, payload = entry
        require(version_row["kind"] == kind and version_row["logical_key"] == FAMILY
                and version_row["created_event"] < row["created_event"], "version_record_binding")
        content[kind] = payload["content"]
    require(content["protocol"].get("method") == FAMILY
            and content["prompt"] == {"instructions": legacy.BOUNDARY + "\n" + legacy.RULES}
            and content["codebook"] == {"labels": list(legacy.LABELS), "definitions": legacy.RULES}, "version_contract")
    pairs = value.get("pairs")
    require(isinstance(pairs, list) and pairs and [p.get("pair") for p in pairs] == list(range(1, len(pairs) + 1)), "plan_pair_frame")
    for pair in pairs:
        require(isinstance(pair.get("articles"), list) and len(pair["articles"]) == 2
                and isinstance(pair.get("article_ids"), list) and len(pair["article_ids"]) == 2
                and len(set(pair["article_ids"])) == 2, "pair_sources")
    return True


def _source(article, old_id, event_uri, artifacts):
    """Hash exact retained JSONL bytes; placeholders never stand in for sources."""
    reference = article.get("original")
    if reference is None or article.get("quarantined"):
        return None
    prior.exposure._sha(reference)
    raw = artifacts.get(reference)
    if raw is None:
        return None
    require(type(raw) is bytes and hashlib.sha256(raw).hexdigest() == reference, "original_source_digest")
    try:
        source = json.loads(raw)["article"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("legacy_pair_original_source_format") from error
    locator = article.get("locator", {})
    require(isinstance(source, dict) and digest(source) == article.get("source_sha256")
            and locator.get("row_sha256") == reference and locator.get("event") == event_uri
            and source.get("uri") == old_id and source.get("eventUri") == event_uri, "original_source_identity")
    expected = {"title": source.get("title"), "body": source.get("body") or "", "url": source.get("url"),
                "published": source.get("dateTimePub") or source.get("dateTime") or source.get("date")}
    require(all(article.get(k) == v for k, v in expected.items()), "retained_source_projection")
    if not isinstance(source.get("title"), str) or not isinstance(source.get("body"), str):
        return None  # An old missing/null field is not a known complete empty input.
    title, body = source["title"], source["body"]
    return {"legacy_article_id": old_id, "original_artifact": reference, "source_sha256": digest(source),
            "title_sha256": hashlib.sha256(title.encode()).hexdigest(), "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            "input_sha256": digest({"title": title, "body": body})}


def _reply(attempt, intended, intent_row, events, rows, store):
    received = [(r, v) for r, v in events.values() if r["kind"] == "codex.response.received" and v.get("attempt") == attempt]
    completed = [(r, v) for r, v in events.values() if r["kind"] == "model.attempt.completed" and v.get("attempt") == attempt]
    require(len(received) <= 1 and len(completed) <= 1, "multiple_physical_results")
    judgments = [(r, v) for r, v in rows.values() if r["kind"] == JUDGMENT and v.get("attempt") == attempt]
    require(len(judgments) <= 1, "multiple_judgment_records")
    refs = [v.get("artifact") for _, v in received] + [v.get("response") for _, v in completed]
    refs += [v.get("response") for _, v in judgments]
    require(len(set(refs)) <= 1 and all(r["seq"] > intent_row["seq"] for r, _ in received + completed), "result_attempt_binding")
    ref = refs[0] if refs else None
    envelope = store.get(ref, optional=True) if ref is not None else None
    if judgments:
        row, judgment = judgments[0]
        require(row["logical_key"] == intended["task_key"] and row["created_event"] > intent_row["seq"]
                and judgment.get("plan") == intended["plan"] and judgment.get("request") == intended["request"], "judgment_task_binding")
        if envelope is not None:
            require(judgment.get("reply") == envelope.get("payload"), "judgment_response_binding")
    if completed:
        result = completed[0][1]
        require(result.get("assessment") == (judgments[0][0]["id"] if judgments else None), "completion_assessment_binding")
        if received:
            require(received[0][0]["seq"] < completed[0][0]["seq"], "result_event_order")
    substantive = False
    if envelope is not None:
        require(isinstance(envelope, dict), "response_envelope")
        reply = envelope.get("payload")
        if envelope.get("provider") == "codex-current-conversation":
            require(envelope.get("raw_response") == reply, "submitted_reply_binding")
        # Deliberately not validate_reply: invalid quotations/labels do not undo
        # substantive source exposure. No old judgment is promoted to current Y.
        substantive = bool(received and envelope.get("provider") == "codex-current-conversation"
            and envelope.get("model") is None and envelope.get("request_id") is None and envelope.get("usage") is None
            and isinstance(reply, dict) and type(reply.get("pair")) is int and reply["pair"] == intended["pair"]
            and all(isinstance(reply.get(k), str) and reply[k].strip() for k in ("rationale", "event_a", "event_b")))
    return {"artifact": ref, "envelope": envelope, "substantive": substantive,
            "received": received, "completed": completed, "judgments": judgments}


def _windows(intended, intent_row, request, events, store, *, before):
    """Only pre-reply exact windows, never inferred attention or full reading."""
    spans, bindings = {"a": [], "b": []}, []
    for row, value in events.values():
        if row["kind"] != "provider_label.request.chunk_inspected":
            continue
        packets = store.get(value["packets"], optional=True)
        if packets is None:
            continue
        require(isinstance(packets, list), "inspection_packets")
        for packet in packets:
            if not isinstance(packet, dict) or packet.get("request") != intended["request"]:
                continue
            require(packet.get("pair") == intended["pair"] and row["seq"] > intent_row["seq"], "inspection_task_binding")
            start, end = packet.get("start"), packet.get("end")
            if type(start) is not int or type(end) is not int or not 0 <= start <= end:
                continue  # Unsupported historical slicing is not positive proof.
            detail = {"event": row["event_hash"], "packets_artifact": value["packets"], "start": start, "end": end, "sources": {}}
            for role in ("a", "b"):
                source, window = request[role], packet.get(role)
                expected = {"title": source["title"], "published": source["published"],
                    "total_chars": len(source["body"]), "text": source["body"][start:end]}
                require(window == expected, "inspection_source_binding")
                lower, upper = min(start, len(source["body"])), min(end, len(source["body"]))
                detail["sources"][role] = {"start": lower, "end": upper,
                    "text_sha256": hashlib.sha256(window["text"].encode()).hexdigest()}
                if before is not None and row["seq"] < before and upper > lower and window["text"].strip():
                    spans[role].append((lower, upper))
            detail["before_submitted_reply"] = before is not None and row["seq"] < before
            bindings.append(detail)
    coverage = {}
    for role, values in spans.items():
        merged = []
        for lower, upper in sorted(values):
            if merged and lower <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], upper)
            else:
                merged.append([lower, upper])
        count = sum(b - a for a, b in merged)
        coverage[role] = {"body_intervals": merged, "observed_body_characters": count,
            "total_body_characters": len(request[role]["body"]),
            "recorded_window_coverage": "full" if count and count == len(request[role]["body"]) else "partial" if count else "none",
            "attention_or_full_read_proven": False}
    return coverage, bindings


def _origin_matches(origin, owner, selected_rows, selected_events, artifacts):
    if origin is None:
        return False
    _, events, rows, _ = prior._owner(origin)
    if any(r["id"] not in rows for r, _ in selected_rows) or any(r["seq"] not in events for r, _ in selected_events):
        return False
    require(all(rows[r["id"]] == (r, v) for r, v in selected_rows), "copied_origin_record_conflict")
    require(all(events[r["seq"]] == (r, v) for r, v in selected_events), "copied_origin_event_conflict")
    for ref in artifacts:
        left, right = owner.artifacts.get(ref), origin.artifacts.get(ref)
        if left is None or right is None:
            return False
        require(left == right and hashlib.sha256(left).hexdigest() == ref, "copied_origin_artifact_conflict")
    return True


@dataclass(frozen=True)
class LegacyPairHistory:
    observations: tuple
    source_contribution: dict
    records: tuple
    inventory_certificate: dict
    manifest: dict


def normalize_provider_label_history(owner, index, *, origin_owner):
    """Normalize this family only; all returned source-bearing objects are private.

    ``manifest`` is source-free. ``records`` retain original request/reply and
    incompatible provenance. Supply the same verified reader for native origin;
    copied views require its original reader. This does not authorize dispatch.
    A P observation may contain only the window-proven subset of the old pair;
    uncovered endpoints remain explicitly unknown in the incomplete contribution.
    """
    store, events, rows, intents = prior._owner(owner)
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner is not None else None
    known = {item.input_sha256: item.document_id for item in index.inputs}
    require(len(known) == len(index.inputs), "unique_exact_inputs_required")
    plans = {identity: (row, value) for identity, (row, value) in rows.items()
             if row["kind"] == PLAN and value.get("method") == FAMILY}
    supported = {identity: _plan(row, value, rows) for identity, (row, value) in plans.items()}
    observations, records, bindings, gaps, outside = [], [], [], [], []
    unsupported, attempted = [], set()
    for attempt, (intent_row, intended) in intents.items():
        selected = plans.get(intended.get("plan"))
        if selected is None or not supported[intended["plan"]]:
            unsupported.append(attempt)
            gaps.append({"reason_code": "unsupported_or_incomplete_plan", "attempt": attempt, "document_ids": None})
            continue
        plan_row, plan = selected
        number = intended.get("pair")
        require(type(number) is int and 1 <= number <= len(plan["pairs"]), "selected_pair_number")
        attempted.add((plan_row["id"], number))
        pair = plan["pairs"][number - 1]
        expected = {"pair": number, "boundary": legacy.BOUNDARY, "instructions": legacy.RULES,
            "versions": plan["versions"], "response_fields": RESPONSE_FIELDS}
        expected.update({role: {key: article[key] for key in ("source_sha256", "title", "published", "body")}
            for role, article in zip(("a", "b"), pair["articles"], strict=True)})
        request, dispatch = store.get(intended["request"], optional=True), store.get(intended["dispatch"], optional=True)
        if request is None or dispatch is None:
            gaps.append({"reason_code": "request_or_dispatch_unavailable", "attempt": attempt, "document_ids": None})
            continue
        require(request == expected and dispatch == legacy.Invocation(request).manifest(), "exact_request_dispatch")
        require(intended.get("task_key") == digest([plan_row["id"], number]) and type(intended.get("number")) is int
            and intended["number"] == 1 and intended.get("authorization_key") == FAMILY
            and intended.get("reserved_pair_attempts") == 1 and intended.get("reserved_article_exposures") == 2
            and plan_row["created_event"] < intent_row["seq"], "physical_task_binding")
        handoffs = [(r, v) for r, v in rows.values() if r["kind"] == HANDOFF and v.get("attempt") == attempt]
        require(len(handoffs) <= 1 and all(v == intended and r["logical_key"] == intended["task_key"]
                and r["created_event"] > intent_row["seq"] for r, v in handoffs), "handoff_binding")
        sources = [_source(a, uri, pair["event_uri"], owner.artifacts)
                   for a, uri in zip(pair["articles"], pair["article_ids"], strict=True)]
        matched = sorted({known[s["input_sha256"]] for s in sources if s and s["input_sha256"] in known})
        if any(s is None for s in sources):
            gaps.append({"reason_code": "full_source_identity_unavailable", "attempt": attempt, "document_ids": matched or None})
        result = _reply(attempt, intended, intent_row, events, rows, store)
        before = result["received"][0][0]["seq"] if result["received"] else None
        coverage, window_bindings = _windows(intended, intent_row, request, events, store, before=before)
        selected_rows = [selected, *handoffs, *result["judgments"], *(rows[v] for v in plan["versions"].values())]
        window_events = [entry for entry in events.values() if entry[0]["event_hash"] in {w["event"] for w in window_bindings}]
        selected_events = [(intent_row, intended), *result["received"], *result["completed"], *window_events]
        refs = {intended["request"], intended["dispatch"], *(s["original_artifact"] for s in sources if s),
                *(w["packets_artifact"] for w in window_bindings)}
        if result["artifact"]:
            refs.add(result["artifact"])
        origin_ok = origin_owner is owner or _origin_matches(origin_owner, owner, selected_rows, selected_events, refs)
        if not origin_ok:
            gaps.append({"reason_code": "physical_origin_unresolved", "attempt": attempt, "document_ids": matched or None})
        proven = sorted({known[s["input_sha256"]] for role, s in zip(("a", "b"), sources, strict=True)
            if s and s["input_sha256"] in known and coverage[role]["observed_body_characters"] > 0})
        acknowledged = bool(result["substantive"] and handoffs and proven)
        observed_ids = proven if acknowledged else matched
        source_binding = {"plan_record": plan_row["id"], "pair": number, "request_sha256": intended["request"],
            "source_versions": sources, "matched_document_ids": matched, "acknowledged_document_ids": proven if acknowledged else []}
        evidence_binding = {"rule": ACKNOWLEDGEMENT, "intent_event": intent_row["event_hash"],
            "dispatch_sha256": intended["dispatch"], "handoff_records": [r["id"] for r, _ in handoffs],
            "received_events": [r["event_hash"] for r, _ in result["received"]],
            "completion_events": [r["event_hash"] for r, _ in result["completed"]], "response_artifact": result["artifact"],
            "window_bindings": window_bindings, "coverage": coverage, "substantive_reply": result["substantive"],
            "observed_model": None, "state": "acknowledged" if acknowledged else "uncertain"}
        bindings.append({"original_attempt": attempt, "original_owner_source_id": origin_id if origin_ok else None,
            "origin_verified": bool(origin_ok), "source_binding": source_binding, "evidence_binding": evidence_binding,
            "role_policy": ROLE_POLICY["version"], "current_reference_compatible": False})
        if matched and origin_ok:
            observations.append({"event_id": attempt, "origin_source_id": origin_id, "source_id": source_id,
                "record_sha256": result["artifact"] or intent_row["event_hash"],
                "roles": ["reference", "substantive_review"], "role_binding": digest({"policy": ROLE_POLICY, "plan": plan_row["id"]}),
                "task_binding": {"kind": "article" if len(observed_ids) == 1 else "pair", "document_ids": observed_ids,
                    "binding_sha256": digest(source_binding)},
                "evidence": {"state": "acknowledged" if acknowledged else "uncertain",
                    "kind": "substantive_review_record" if acknowledged else "incomplete_record", "evidence_sha256": digest(evidence_binding)}})
        if not matched and all(s is not None for s in sources):
            outside.append(attempt)
        if origin_ok and len(matched) == 2 and all(s is not None for s in sources):
            identity = history.sources([{k: s[k] for k in ("title_sha256", "body_sha256", "input_sha256")}
                | {"document_id": known[s["input_sha256"]]} for s in sources], pair=True)
            returned = result["envelope"] is not None
            records.append({"record_id": result["judgments"][0][0]["id"] if result["judgments"] else
                    result["received"][0][0]["event_hash"] if result["received"] else intent_row["event_hash"],
                "owner_sha256": digest(origin_id), "attempt_id": digest([origin_id, attempt]),
                "logical_task_id": intended["task_key"], "role": "primary", "scope_kind": "pair_reference",
                "source_identity": identity, "attempt_state": "returned" if returned else "intent",
                "definition_version": FAMILY, "packet": {"method": FAMILY, "request": deepcopy(request)},
                "payload": deepcopy(result["envelope"].get("payload")) if returned else None,
                "provenance": {"provider": "codex-current-conversation", "observed_model": None,
                    "request_sha256": intended["request"], "dispatch_sha256": intended["dispatch"],
                    "response_sha256": result["artifact"], "role_policy": ROLE_POLICY,
                    "current_reference_compatible": False, "full_read_proven": False} if returned else None})
    prepared = [{"plan_record": identity, "pair": pair["pair"]} for identity, (_, plan) in plans.items()
                for pair in plan.get("pairs", []) if (identity, pair["pair"]) not in attempted]
    history.normalize_records(records)
    manifest = {"version": VERSION, "family": FAMILY, "source_id": source_id, "origin_source_id": origin_id,
        "source_head": owner.scope["source_head"], "input_index_digest": index.digest, "history_census_sha256": digest(owner.census),
        "role_policy": ROLE_POLICY, "physical_id_policy": PHYSICAL_ID_POLICY, "acknowledgement_rule": ACKNOWLEDGEMENT,
        "physical_intents": len(intents), "supported_exact_request_attempts": len(bindings), "normalized_attempts": bindings,
        "prepared_only_pairs": prepared, "unsupported_attempts": unsupported, "exact_version_nonintersection_attempts": outside,
        "unresolved_evidence": gaps, "inherited_inventory_gaps": deepcopy(owner.gaps),
        "observations_sha256": digest(observations), "records_sha256": digest(records), "pair_primary_blockers": len(records),
        "evidence_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "owner_history_complete": False, "whole_study_history_complete": False, "creates_pair_labels": False,
        "model_calls": 0, "source_mutations": 0,
        "limitations": "One named conversational pair-reference family. Retained full bodies identify exact versions, but only bound pre-reply windows plus a submitted substantive reply establish prior exposure. Window coverage does not prove attention/full reading. Missing/withheld identities, unsupported history and copied origins remain gaps. No current model provenance, Y, group/card/screening pair truth, or fresh-dispatch authority is created."}
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(owner.scope["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(o["origin_source_id"], o["event_id"]) for o in observations],
        "inventory_sha256": digest(manifest)}
    certificate = {"binding_sha256": digest(manifest), "complete": False, "unknown_input_sha256": [], "global_gap": True}
    return LegacyPairHistory(tuple(observations), contribution, tuple(records), certificate, manifest)
