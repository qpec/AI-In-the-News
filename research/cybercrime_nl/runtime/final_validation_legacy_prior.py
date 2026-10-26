"""One bounded legacy Codex screening family -> prior exposure, never pair Y.

Consumes verified HistoryOwner readers inside their audited scoped lifetime. No
owner is opened, provider invoked or method registered here. Exact title/body
hash intersection is independent of corpus labels. The caller explicitly supplies
the original owner reader; copied views must match that origin's retained physical
evidence. An unavailable origin stays unknown, not a new invented physical event.

Only incident-decisions-astra-stratified-validation-20261022-v1 is supported.
Other formats/history remain incomplete. A clean complete terminal model reply
can establish P despite unavailable observed model or invalid judgment JSON; it
does not establish trusted current-reference provenance, attention or correctness.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import final_validation_exposure as exposure
import final_validation_history_inventory as inventory
import final_validation_projection as projection
from newsresearch import astra_incident_validation as legacy
from newsresearch import codex_provider as cli
from newsresearch.common import canonical, digest

VERSION = "final-validation-legacy-astra-prior-v1"
FAMILY = "incident-decisions-astra-stratified-validation-20261022-v1"
PLAN = "astra_validation_plan"
INTENDED = "astra_validation_intended"
RESPONSE = "astra_validation_response"
ACKNOWLEDGEMENT = "exact-full-source-cli-dispatch-clean-terminal-reply-p-only-v1"


def require(value, code):
    if not value:
        raise ValueError("legacy_prior_" + code)


def implementation():
    root = Path(__file__).resolve().parents[3]
    paths = (Path(__file__), Path(legacy.__file__), Path(cli.__file__),
             root / "workbench/validate_incident_decisions_astra.py")
    return {**inventory.implementation(), **{str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}


def _owner(owner):
    """Validate supplied reader census/records, not its independently verified scope."""
    store = exposure._Artifacts(owner.artifacts)
    head = owner.scope["source_head"]
    require(owner.census["source_head"] == head and owner.census["scope_sha256"] == digest(owner.scope), "owner_scope")
    require([r["event_hash"] for r in owner.events] == owner.census["selected_event_hashes"]
            and [r["id"] for r in owner.records] == owner.census["selected_record_ids"], "selected_census")
    events = {r["seq"]: (r, exposure._event(r, head[0])) for r in owner.events}
    require(len(events) == len(owner.events), "event_duplicate")
    rows = {}
    for row in owner.records:
        payload = store.get(row["artifact"])
        require(canonical(payload) == row["payload"] and row["id"] == digest({"kind": row["kind"],
            "key": row["logical_key"], "payload": row["artifact"], "supersedes": row["supersedes"]}), "record_digest")
        event = events.get(row["created_event"])
        require(event is not None and event[0]["kind"] == "record.created" and event[1] == {
            "record": row["id"], "kind": row["kind"], "artifact": row["artifact"]}, "record_creation")
        require(row["id"] not in rows, "record_duplicate")
        rows[row["id"]] = (row, payload)
    intents = {value["attempt"]: (row, value) for row, value in events.values() if row["kind"] == "model.attempt.intended"}
    require(len(intents) == sum(r["kind"] == "model.attempt.intended" for r in owner.events)
            and [r["event_hash"] for r, _ in intents.values()] == owner.census["intent_event_hashes"], "intent_census")
    return store, events, rows, intents


def _dispatch(request, manifest, plan):
    """Rebuild the exact no-I/O legacy CLI invocation; never call prepare()."""
    require(isinstance(manifest, dict), "dispatch_shape")
    cwd = Path(manifest["cwd"])
    provider = object.__new__(legacy.AstraProvider)
    provider.executable, provider.model = plan["codex_executable"], legacy.MODEL
    expected = cli.PreparedCodexInvocation(provider._command(cwd), cwd, legacy.batch_prompt(request),
        request["schema"], request, legacy.MODEL).manifest()
    require(expected == manifest, "exact_dispatch_binding")
    exposure._sha(plan["codex_binary_sha256"])
    return {"dispatch_sha256": digest(manifest), "stdin_sha256": manifest["stdin_sha256"],
            "configured_model": legacy.MODEL, "binary_sha256": plan["codex_binary_sha256"]}


def _terminal(envelope, dispatch):
    """Source exposure only: neither screening schema nor citations are judged."""
    if envelope is None:
        return "uncertain", "unavailable_envelope", ["response_unavailable"]
    require(isinstance(envelope, dict), "response_envelope_shape")
    raw = envelope.get("raw_response")
    if not isinstance(raw, dict):
        return "uncertain", "unrecognized_envelope", ["raw_terminal_unavailable"]
    if raw.get("failure") == "codex_process_start_failed" and not raw.get("stdout") and not raw.get("events"):
        require(envelope.get("payload") is None and raw.get("exit_code") is None, "predispatch_response_conflict")
        return "predispatch_failure", "explicit_predispatch_failure", []
    if any(key in raw and raw[key] != value for key, value in dispatch.items()):
        raise ValueError("legacy_prior_response_dispatch_conflict")
    if any(key not in raw for key in dispatch):
        return "uncertain", "incomplete_record", ["response_dispatch_provenance_missing"]
    if (raw.get("timed_out") not in (None, False) or envelope.get("provider") != "codex-cli"
            or type(raw.get("exit_code")) is not int
            or raw["exit_code"] != 0 or not isinstance(raw.get("stdout"), str)):
        return "uncertain", "technical_failure", ["unclean_cli_transport"]
    try:
        events = [json.loads(line) for line in raw["stdout"].splitlines() if line.strip()]
    except (ValueError, TypeError):
        return "uncertain", "unrecognized_envelope", ["non_json_cli_stream"]
    if events != raw.get("events") or not events or not all(isinstance(e, dict) for e in events):
        return "uncertain", "unrecognized_envelope", ["terminal_event_binding_unavailable"]
    # Validate the exact old transport-warning allowance; preserve all originals.
    filtered, warnings, final_seen = [], [], False
    for event in events:
        item = event.get("item", {})
        item = item if isinstance(item, dict) else {}
        permitted = ((event.get("type") == "error" and legacy._RECONNECT.fullmatch(str(event.get("message", ""))))
            or (event.get("type") == "item.completed" and item.get("type") == "error"
                and legacy._FALLBACK.fullmatch(str(item.get("message", "")))))
        (warnings if permitted and not final_seen else filtered).append(event)
        final_seen |= event.get("type") == "item.completed" and item.get("type") == "agent_message"
    if warnings and (warnings != raw.get("permitted_transport_warnings") or raw.get("coordinator_retries") != 0):
        return "uncertain", "unrecognized_envelope", ["warning_normalization_unbound"]
    kinds = [e.get("type") for e in filtered]
    if (len(kinds) < 4 or kinds[:2] != ["thread.started", "turn.started"] or kinds[-1] != "turn.completed"
            or any(kinds.count(kind) != 1 for kind in ("thread.started", "turn.started", "turn.completed"))):
        return "uncertain", "technical_failure", ["terminal_completion_unavailable"]
    finals, observed = [], set()
    for event in filtered:
        if event.get("model") is not None and not isinstance(event["model"], str):
            return "uncertain", "unrecognized_envelope", ["observed_model_shape"]
        if isinstance(event.get("model"), str):
            observed.add(event["model"])
        kind = event.get("type")
        if kind in {"thread.started", "turn.started", "turn.completed"}:
            continue
        item = event.get("item")
        if (kind not in {"item.started", "item.updated", "item.completed"} or not isinstance(item, dict)
                or item.get("type") not in {"agent_message", "reasoning"}):
            return "uncertain", "technical_failure", ["tool_or_unclean_terminal_activity"]
        if kind == "item.completed" and item["type"] == "agent_message":
            finals.append(item.get("text"))
    for value in (envelope.get("model"), raw.get("observed_model")):
        if value is not None:
            if not isinstance(value, str):
                return "uncertain", "unrecognized_envelope", ["observed_model_shape"]
            observed.add(value)
    extra = raw.get("observed_models", [])
    if not isinstance(extra, list) or not all(isinstance(v, str) for v in extra):
        return "uncertain", "unrecognized_envelope", ["observed_model_shape"]
    observed.update(extra)
    if any(not legacy._MODEL.fullmatch(value) for value in observed):
        return "uncertain", "unrecognized_envelope", ["observed_model_conflict"]
    if len(finals) != 1 or not isinstance(finals[0], str) or not finals[0].strip():
        return "uncertain", "unrecognized_envelope", ["terminal_reply_missing_or_multiple"]
    try:
        parsed = json.loads(finals[0])
        final_invalid = False
    except ValueError:
        parsed, final_invalid = None, True
    if envelope.get("payload") != parsed:
        require(envelope.get("payload") is None, "response_terminal_payload_conflict")
        return "uncertain", "technical_failure", ["payload_withheld_without_clean_binding"]
    allowed = {None, "codex_final_json_invalid"} if final_invalid else {None}
    if raw.get("failure") not in allowed or raw.get("unknown_outcome") is not False:
        return "uncertain", "technical_failure", ["unclean_cli_outcome"]
    gaps = ["observed_model_unavailable"] if not observed else []
    if final_invalid:
        gaps.append("judgment_json_invalid_exposure_only")
    return "acknowledged", "model_serving_envelope", gaps


@dataclass(frozen=True)
class LegacyPrior:
    observations: tuple
    source_contribution: dict
    manifest: dict

    def project(self, index, *, inventory_certificate):
        require([s for s in inventory_certificate.get("sources", []) if s.get("source_id") == self.source_contribution["source_id"]]
                == [self.source_contribution], "source_contribution_changed")
        return projection.project_prior_exposure(index, list(self.observations), inventory_certificate=inventory_certificate)


def normalize_legacy_astra_prior(owner, index, *, origin_owner):
    """Normalize one verified historical owner; origin must be explicitly supplied.

    Pass the same reader for a declared native original. For an exact copied view,
    also supply its verified original reader; intent event, immutable plan/record
    and request/dispatch/response bytes must agree. Other transfer formats are
    unsupported: origin_owner=None leaves a global gap and no fabricated event.
    Native-origin declarations and comprehensive study scope remain upstream.
    """
    store, events, rows, intents = _owner(owner)
    origin = _owner(origin_owner) if origin_owner is not None and origin_owner is not owner else None
    source_id = owner.census["owner_sha256"]
    origin_id = origin_owner.census["owner_sha256"] if origin_owner is not None else None
    known = {item.input_sha256: item.document_id for item in index.inputs}
    require(len(known) == len(index.inputs), "unique_exact_inputs_required")
    plans = {identity: (row, value) for identity, (row, value) in rows.items()
             if row["kind"] == PLAN and value.get("method") == FAMILY}
    actual_responses, retained_intents = {}, {}
    for row, value in rows.values():
        if row["kind"] not in {INTENDED, RESPONSE}:
            continue
        attempt = value.get("attempt")
        require(isinstance(attempt, str) and attempt, "record_attempt_identity")
        target = actual_responses if row["kind"] == RESPONSE else retained_intents
        require(attempt not in target, "duplicate_attempt_record")
        target[attempt] = (row, value)
    require(set(actual_responses) <= set(intents) and set(retained_intents) <= set(intents), "record_without_physical_intent")
    observations, bindings, gaps, outside = [], [], [], []
    unsupported = []
    for attempt, (intent_row, intended) in intents.items():
        selected = plans.get(intended.get("batch"))
        if selected is None:
            unsupported.append(attempt)
            gaps.append({"reason_code": "unsupported_plan_or_attempt_family", "attempt": attempt, "document_ids": None})
            continue
        plan_row, plan = selected
        batch_index = intended.get("batch_index")
        if (type(batch_index) is not int or not isinstance(plan.get("batches"), list)
                or not 0 <= batch_index < len(plan["batches"])):
            gaps.append({"reason_code": "batch_source_mapping_unavailable", "attempt": attempt, "document_ids": None})
            continue
        batch = plan["batches"][batch_index]
        items = store.get(batch["items"], optional=True)
        request = store.get(intended["request"], optional=True)
        dispatch = store.get(intended["dispatch"], optional=True)
        if items is None or request is None or dispatch is None:
            gaps.append({"reason_code": "source_or_dispatch_artifact_unavailable", "attempt": attempt, "document_ids": None})
            continue
        if (not isinstance(items, list) or not items or any(not isinstance(i, dict) or set(i) != {"article_id", "title", "body"}
                or not all(isinstance(i[k], str) for k in i) for i in items)
                or not isinstance(plan.get("questions"), list)):
            gaps.append({"reason_code": "unsupported_full_source_format", "attempt": attempt, "document_ids": None})
            continue
        require(len({i["article_id"] for i in items}) == len(items) == batch["count"] == intended.get("count"), "batch_input_coverage")
        require(request == legacy.request_for(items, plan["questions"]), "full_request_binding")
        require(intended.get("task_key") == digest([plan_row["id"], batch_index])
                and intended.get("number") == 1 and intended.get("phase") == batch["phase"]
                and plan_row["created_event"] < intent_row["seq"], "planned_task_identity")
        dispatch_metadata = _dispatch(request, dispatch, plan)
        bound_sources = [{"legacy_article_id": i["article_id"], "title_sha256": hashlib.sha256(i["title"].encode()).hexdigest(),
            "body_sha256": hashlib.sha256(i["body"].encode()).hexdigest(),
            "input_sha256": digest({"title": i["title"], "body": i["body"]})} for i in items]
        matched = sorted({known[s["input_sha256"]] for s in bound_sources if s["input_sha256"] in known})
        response = actual_responses.get(attempt)
        own_intent = retained_intents.get(attempt)
        if own_intent:
            require(own_intent[1] == intended and own_intent[0]["logical_key"] == intended["task_key"], "retained_intent_binding")
        envelope = None
        if response:
            require(all(response[1].get(k) == v for k, v in intended.items())
                    and response[0]["logical_key"] == intended["task_key"] and response[0]["created_event"] > intent_row["seq"],
                    "response_attempt_binding")
            envelope = store.get(response[1]["response"], optional=True)
        received = [r for r, v in events.values() if r["kind"] == "astra_validation.response.received"
                    and v.get("attempt") == attempt and response and v.get("response") == response[1]["response"]]
        state, evidence_kind, evidence_gaps = _terminal(envelope, dispatch)
        if not own_intent or response and len(received) != 1:
            state, evidence_kind = "uncertain", "incomplete_record"
            evidence_gaps.append("original_attempt_response_link_incomplete")
        origin_ok = origin_owner is owner
        if origin is not None:
            origin_store, _, origin_rows, origin_intents = origin
            original = origin_intents.get(attempt)
            origin_ok = original is not None and original == (intent_row, intended)
            origin_ok &= plan_row["id"] in origin_rows and origin_rows[plan_row["id"]] == (plan_row, plan)
            if response:
                origin_ok &= response[0]["id"] in origin_rows and origin_rows[response[0]["id"]] == response
                if origin_ok:
                    origin_ok &= origin_store.get(response[1]["response"]) == envelope
            if origin_ok:
                origin_ok &= origin_store.get(intended["request"]) == request and origin_store.get(intended["dispatch"]) == dispatch
        if not origin_ok:
            gaps.append({"reason_code": "physical_origin_unresolved", "attempt": attempt, "document_ids": matched or None})
        source_binding = {"plan_record": plan_row["id"], "batch_index": batch_index, "batch_items": batch["items"],
            "request_sha256": intended["request"], "source_versions": bound_sources, "matched_document_ids": matched}
        evidence_binding = {"intent_event": intent_row["event_hash"], "response_record": response[0]["id"] if response else None,
            "response_artifact": response[1]["response"] if response else None,
            "dispatch": dispatch_metadata, "rule": ACKNOWLEDGEMENT, "state": state, "gaps": evidence_gaps}
        bindings.append({"original_attempt": attempt, "original_owner_source_id": origin_id if origin_ok else None,
            "source_binding": source_binding, "evidence_binding": evidence_binding,
            "original_task_role": "blinded_article_screening_reference", "origin_verified": bool(origin_ok),
            "current_pair_reference_compatible": False})
        if not matched:
            outside.append(attempt)  # Exact retained versions only, not corpus names.
            continue
        if origin_ok:
            observations.append({"event_id": attempt, "origin_source_id": origin_id, "source_id": source_id,
                "record_sha256": response[0]["artifact"] if response else intent_row["event_hash"],
                "roles": ["reference"], "role_binding": digest({"family": FAMILY, "plan": plan_row["id"]}),
                "task_binding": {"kind": "article" if len(items) == 1 else "multiarticle",
                    "document_ids": matched, "binding_sha256": digest(source_binding)},
                "evidence": {"state": state, "kind": evidence_kind, "evidence_sha256": digest(evidence_binding)}})
    prepared = []
    attempted = {(value.get("batch"), value.get("batch_index")) for _, value in intents.values()}
    for identity, (_, plan) in plans.items():
        for n, batch in enumerate(plan.get("batches", [])):
            if (identity, n) not in attempted:
                prepared.append({"plan_record": identity, "batch_index": n, "items_artifact": batch.get("items")})
    manifest = {"version": VERSION, "family": FAMILY, "source_id": source_id, "source_head": owner.scope["source_head"],
        "origin_source_id": origin_id, "input_index_digest": index.digest, "history_census_sha256": digest(owner.census),
        "acknowledgement_rule": ACKNOWLEDGEMENT, "missing_observed_model_blocks_current_Y_not_clean_P": True,
        "normalized_attempts": bindings, "observations_sha256": digest(observations), "physical_intents": len(intents),
        "supported_exact_request_attempts": len(bindings), "intersecting_observations": len(observations),
        "exact_version_nonintersection_attempts": outside, "unsupported_attempts": unsupported,
        "prepared_only_batches": prepared, "unresolved_evidence": gaps, "inherited_inventory_gaps": deepcopy(owner.gaps),
        "evidence_states": dict(Counter(o["evidence"]["state"] for o in observations)),
        "owner_history_complete": False, "whole_study_history_complete": False, "creates_pair_labels": False,
        "model_calls": 0, "source_mutations": 0,
        "limitations": "One explicit historical screening-reference family only. Native-origin declarations, copied/transfer formats not exactly matched, other records/owners and manual history still require audited reconciliation. Missing observed model can acknowledge source exposure only under the bound clean terminal rule, never current model-reference provenance or Y. Corpus names and labels are not source matches."}
    contribution = {"source_id": source_id, "source_kind": "owner", "immutable_head_sha256": digest(owner.scope["source_head"]),
        "reconciliation": "incomplete", "missing_document_ids": None,
        "event_ids": [projection.prior_event_identity(o["origin_source_id"], o["event_id"]) for o in observations],
        "inventory_sha256": digest(manifest)}
    return LegacyPrior(tuple(observations), contribution, manifest)
