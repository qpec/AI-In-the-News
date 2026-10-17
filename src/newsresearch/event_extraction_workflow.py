"""Frozen saved-text event mentions; no embeddings, adopted groups or implicit calls.

The existing bounded-pilot operation/result envelopes are reused deliberately;
the separate method, task kind and study key identify extraction, not validation.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .common import AuditError, Context, Json, ResearchError, digest, require_active
from .runtime import Research, audited_handler

METHOD = "saved-text-event-extraction-v1"
APPROVAL_METHOD = "event-extraction-run-approval-v1"
DEFAULT_STUDY = "saved-text-event-extraction-pilot-20261017-v1"
ORIGINAL_RESULT = "da480ad8c3fa87ca41ddfe11530695f22246581419412193a2580d60dc4bc19a"
SEED = "saved-text-event-mentions-development-v1"
LITERATURE_PROTOCOL = "84fa3a5c39d63ae30b0e181876cab28927fccf55f1648c22ccb0b136fb4b6db8"
LITERATURE_NOTE = "4c3d048d39e62f3a858bc3f354ee627ab4127d6f9a4451f5e295d3cdae92be56"
SOURCES = [
    "https://aclanthology.org/2020.acl-main.718/",
    "https://aclanthology.org/2021.naacl-main.69/",
    "https://aclanthology.org/P19-1409/",
    "https://aclanthology.org/L14-1646/",
    "https://aclanthology.org/2023.findings-acl.44/",
]


def implementation() -> Json:
    names = ("event_extraction_workflow.py", "event_extraction_contract.py",
             "event_extraction_provider.py", "event_extraction_execution.py", "event_extraction_inputs.py",
             "codex_provider.py", "gateway.py", "runtime.py", "common.py",
             "storage.py", "presentation.py")
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in names} | {"uv.lock": hashlib.sha256(
                Path(__file__).resolve().parents[2].joinpath("uv.lock").read_bytes()).hexdigest()}


def save(engine: Any, session: str, value: Any, purpose: str) -> str:
    reference = str(engine.ledger.artifacts.put(value))
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": purpose})
    return reference


def present(engine: Any, session: str, context: Context, kind: str, value: Json,
            text: str, key: str | None = None) -> Json:
    identifier = engine.ledger.record(session, kind, key or digest(value), value)
    return _presentation(engine, session, context, kind, identifier, value, text)


def _presentation(engine: Any, session: str, context: Context, kind: str,
                  identifier: str, value: Json, text: str) -> Json:
    presentation = engine._record_presentation(session, context, {
        "results": [{"kind": kind, "id": identifier}], "markdown": text,
        "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **value, "presentation": presentation}


def _rank(seed: str, scope: str, item: str) -> tuple[str, str]:
    return digest({"seed": seed, "scope": scope, "item": item}), item


def select_pilot(membership: dict[str, str], metadata: Json, frame: Json,
                 unavailable: set[str], seed: str = SEED) -> Json:
    """Select four original group pairs and four singletons, without labels/text."""
    representatives = frame["representatives"]
    folds = {row["body_sha256"]: row["fold"] for row in representatives}
    if len(folds) != len(representatives) or any(v not in {"development", "validation"} for v in folds.values()):
        raise AuditError("event_extraction_body_fold_frame_invalid")
    if not set(membership) <= set(metadata):
        raise AuditError("event_extraction_membership_metadata_missing")
    groups: dict[str, list[str]] = defaultdict(list)
    exclusions: dict[str, str] = {}
    for source, group in membership.items():
        groups[group].append(source)
        body = metadata[source].get("body_sha256")
        if body not in folds:
            exclusions[source] = "body_fold_unavailable"
        elif folds[body] != "development":
            exclusions[source] = "sealed_held_out_body"
        elif source in unavailable:
            exclusions[source] = "unresolved_prior_attempt"
    eligible = set(membership) - set(exclusions)
    pair_groups = {group: [s for s in members if s in eligible]
                   for group, members in groups.items() if len(members) >= 2}
    pair_groups = {group: members for group, members in pair_groups.items() if len(members) >= 2}
    singletons = [members[0] for members in groups.values() if len(members) == 1 and members[0] in eligible]
    selected: list[Json] = []
    for group in sorted(pair_groups, key=lambda g: _rank(seed, "group", g))[:4]:
        members = sorted(pair_groups[group], key=lambda s: _rank(seed, group, s))[:2]
        selected.extend({"source_version": source, "selection_stratum": "current_group_pair", "group": group}
                        for source in members)
    for source in sorted(singletons, key=lambda s: _rank(seed, "singleton", s))[:4]:
        selected.append({"source_version": source, "selection_stratum": "current_singleton", "group": membership[source]})
    return {"method": "fixed-sha-rank-development-group-pairs-and-singletons-v1", "seed": seed,
            "original_frame_count": len(membership), "eligible_development_sources": len(eligible),
            "eligible_pair_groups": len(pair_groups), "eligible_singletons": len(singletons),
            "expected_slots": 12, "selected_count": len(selected), "unfilled_slots": 12 - len(selected),
            "selected": selected, "exclusions": exclusions, "exclusion_counts": dict(Counter(exclusions.values())),
            "population_estimate": False, "labels_used": False, "replacement": False}


def _owner(engine: Any, old_plan: Json) -> None:
    row = engine.ledger.db.execute(
        "SELECT id FROM records WHERE kind='study_execution_ownership' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
        (old_plan["study_key"],)).fetchone()
    if row is None:
        raise ResearchError("event_extraction_original_owner_record_required")
    owner = engine.ledger.get(row[0], "study_execution_ownership")
    if (owner.get("status") != "imported_owner" or
            Path(owner.get("owner_workspace", "")).resolve() != engine.ledger.root.resolve()):
        raise ResearchError("event_extraction_use_original_owning_workspace")


def _source_request(engine: Any, session: str, source_id: str, metadata: Json,
                    versions: dict[str, str]) -> tuple[Json | None, Json]:
    from .event_extraction_contract import build_request

    source_sql = "SELECT payload FROM sources WHERE id=?"
    passage_sql = "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start,id"
    engine.ledger.append(session, "event.extraction.inspection.intended", {
        "source_version": source_id, "source_sql": source_sql, "passage_sql": passage_sql,
        "parameters": [source_id], "purpose": "Prepare the complete retained body, no lead truncation"})
    row = engine.ledger.db.execute(source_sql, (source_id,)).fetchone()
    if row is None:
        raise AuditError("event_extraction_frozen_source_missing")
    source = json.loads(row[0])
    example = {"source_version": source_id, "title": source.get("title"), "url": source.get("url")}
    if source.get("retention") != "permitted" or not (source.get("body") or "").strip():
        engine.ledger.append(session, "event.extraction.source.unavailable", {"source_version": source_id})
        return None, example
    if hashlib.sha256(source["body"].encode("utf-8")).hexdigest() != metadata["body_sha256"]:
        raise AuditError("event_extraction_original_body_changed")
    passages = [dict(row) for row in engine.ledger.db.execute(passage_sql, (source_id,))]
    request = build_request({**source, "source_version": source_id}, passages, versions=versions)
    engine.ledger.append(session, "event.extraction.source.inspected", {
        "source_version": source_id, "body_sha256": metadata["body_sha256"],
        "passage_ids": [p["id"] for p in passages], "full_body_supplied": True,
        "body_characters": len(source["body"]), "actual_human_reading_observed": False})
    return request, example


def _escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]").replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def _link(example: Json) -> str:
    title = _escape(example.get("title") or example["source_version"])
    url = example.get("url")
    if isinstance(url, str) and urlsplit(url).scheme in {"http", "https"} and not any(c in url for c in "<>\r\n"):
        return f"[{title}](<{url}>)"
    return title


def render_plan(plan: Json) -> str:
    counts = Counter(task["status"] for task in plan["tasks"])
    sampling = plan["selection"]
    lines = ["Saved-text event-extraction pilot prepared; no extraction model has run.", "",
        f"Selected {len(plan['tasks'])}/12 article slots from {sampling['eligible_development_sources']:,} eligible development sources "
        f"in the {sampling['original_frame_count']:,}-article frozen grouping frame. "
        f"Selection: {sum(t['selection_stratum'] == 'current_group_pair' for t in plan['tasks'])} articles in current-group pairs and "
        f"{sum(t['selection_stratum'] == 'current_singleton' for t in plan['tasks'])} current singletons. "
        f"Prepared {counts['prepared']}; missing text {counts['source_unavailable']}; oversized {counts['oversize']}; "
        f"unfilled slots {sampling['unfilled_slots']}. No replacement or truncation.",
        f"Frame exclusions: {sampling['exclusion_counts']}. Sealed validation bodies stay excluded. "
        "Selection uses stored group IDs and deterministic ranks, without reference labels; groups are not assumed correct.", "",
        f"Frozen full-text packets: {plan['passage_count']} passages / {plan['body_characters']:,} source characters. "
        "New embeddings 0; extraction calls 0; extraction results 0; selected article processing remains pending.",
        f"Proposed maximum: {plan['limits']['max_requests']} Codex-account requests / {plan['limits']['max_article_exposures']} article exposures / zero retries, "
        "configured gpt-6-luna / low. First two are sequential contract canaries; all requests are sequential. "
        "First invalid, incomplete or unknown response latches a stop. No model authorization has been registered.", "",
        "Fields: action/trigger, participants with roles, affected objects and distinguishing identifiers, event time, place, "
        "polarity/actuality/certainty, attribution and exact evidence. One article can yield multiple mentions. "
        "The pilot is exploratory; extraction accuracy, event totals and grouping quality remain unmeasured. Current memberships are unchanged.", "",
        "Prepared examples (selection slots, not extracted events):"]
    for example in plan["examples"][:4]:
        lines.append(f"- {example['selection_stratum']}: {_link(example)}")
    lines.extend(["", "A protected blank review template is prepared for all selected slots; zero human reviews exist."])
    return "\n".join(lines)


def render_result(plan: Json, value: Json) -> str:
    lines = [f"Saved-text event extraction: {value['status']}.", "",
        f"Attempts {value.get('workflow_model_attempts', 0)}/{plan['limits']['max_requests']}; "
        f"outcomes {value.get('outcome_counts', {})}; pending {value.get('pending', 0)} "
        f"(including {value.get('unfilled_slots', 0)} unfilled selection slots); "
        f"provisional event mentions {value.get('event_count', 0)} "
        f"({value.get('complete_article_event_mentions', 0)} from completed articles; "
        f"{value.get('incomplete_article_event_mentions', 0)} from incomplete articles); retries 0; new embeddings 0.",
        f"Obstacle: {value.get('obstacle') or 'none'}. Model outputs are unreviewed; evidence matching does not establish semantic accuracy. "
        "Missing, invalid, incomplete and unknown processing are not negative event findings. No memberships changed."]
    by_source = {example["source_version"]: example for example in plan["examples"]}
    shown = 0
    for outcome in value.get("outcomes", {}).values():
        if outcome.get("status") not in {"valid", "incomplete"}:
            continue
        validation = outcome.get("validation", {})
        source = outcome.get("source_version")
        for mention in validation.get("events", [])[:2]:
            lines.extend(["", f"- {_link(by_source[source])} ({outcome['status']} article processing): {_escape(mention.get('summary'))}"])
            for evidence in mention.get("evidence", [])[:1]:
                lines.append(f"  Evidence: “{_escape(evidence.get('quote'))}” (passage {_escape(evidence.get('passage_id'))}).")
            shown += 1
        if shown >= 4:
            break
    return "\n".join(lines)


def prepare(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_extraction_contract import TASK_INSTRUCTION, answer_schema
    from .event_extraction_provider import build_prompt
    from .event_extraction_inputs import load_frame

    require_active(engine, session)
    if set(data) - {"phase", "original_result", "study_key", "seed"} or not engine.config.offline:
        raise ResearchError("event_extraction_preparation_offline_fields_required")
    original_id = data.get("original_result", ORIGINAL_RESULT)
    key, seed = data.get("study_key", DEFAULT_STUDY), data.get("seed", SEED)
    if not all(isinstance(x, str) and x.strip() for x in (original_id, key, seed)):
        raise ResearchError("event_extraction_preparation_identity_required")
    code = implementation()
    binding = digest({"method": METHOD, "original_result": original_id, "study_key": key, "seed": seed, "implementation": code})
    existing = engine.ledger.db.execute(
        "SELECT id,payload FROM records WHERE kind='luna_group_validation_plan' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (key,)).fetchone()
    if existing:
        plan = engine.ledger.get(existing[0], "luna_group_validation_plan")
        if plan.get("method") != METHOD or plan.get("study_binding") != binding:
            raise ResearchError("event_extraction_existing_plan_binding_changed")
        _bound_plan(engine, session, context, existing[0])
        engine.ledger.append(session, "analysis.cache_reused", {"plan": existing[0], "reason": "Exact frozen extraction preparation"})
        return _presentation(engine, session, Context(context.objective, context.actor, plan["versions"]),
                             "luna_group_validation_plan", existing[0], plan, render_plan(plan))
    partial = engine.ledger.db.execute(
        "SELECT id FROM records WHERE kind='event_extraction_preparation_manifest' AND logical_key=?", (key,)).fetchall()
    if len(partial) > 1:
        raise AuditError("event_extraction_ambiguous_preparation_lineage")
    previous = engine.ledger.get(partial[0][0], "event_extraction_preparation_manifest") if partial else None
    if previous is not None and previous["study_binding"] != binding:
        raise ResearchError("event_extraction_partial_preparation_binding_changed")
    method = {"method": METHOD, "implementation": code, "original_result": original_id,
        "selection": {"seed": seed, "group_pairs": 4, "singletons": 4, "development_body_fold_only": True,
            "exclude_unresolved_attempts": True, "replacement": False, "semantic_selection": False},
        "evidence": "Every retained source paragraph; no truncation; field-level exact quotes and derived offsets",
        "scope": "Provisional mentions before grouping, no dossier adoption", "new_embeddings": 0,
        "literature": {"sources": SOURCES, "external_protocol": LITERATURE_PROTOCOL, "external_note": LITERATURE_NOTE,
            "lookup_workspace": "event-extraction-method-20261017-v1", "hosted_observability_limited": True},
        "fold_metadata": "Use retained local ancestry if present; otherwise the exact saved original-group content identity in the child precision capsule anchors one parent pair-plan record and its named metadata/frame artifacts. Read-only bounded import, full named-byte hashes and ACL checks; no parent journal revalidation, vectors, labels or source-body reads.",
        "unknowns": "Null/empty fields and incomplete processing retained; no_event requires complete coverage",
        "stop": "First invalid, incomplete or unknown response durably stops; zero retries", "model_authorized": False}
    protocol = (previous["versions"]["protocol"] if previous else
                engine._version(session, context, {"kind": "protocol", "key": key, "content": method})["id"])
    old = engine.ledger.get(original_id, "luna_group_validation_result")
    original = engine.ledger.get(old["plan"], "luna_group_validation_plan")
    _owner(engine, original)
    if original["study_key"] == key:
        raise ResearchError("event_extraction_separate_study_required")
    dataset_id = original["versions"]["dataset"]
    dataset = engine.ledger.get(dataset_id, "dataset")
    if not set(original["membership"]) <= set(dataset["source_versions"]):
        raise AuditError("event_extraction_membership_outside_dataset")
    unavailable = {s for intent in engine.ledger.unresolved.values() for s in intent.get("source_versions", [])}
    old_tasks = {task["logical_id"]: task for task in original["tasks"]}
    for logical_id, outcome in old["outcomes"].items():
        if outcome["status"] == "unknown":
            unavailable.update(old_tasks[logical_id]["source_versions"])
    executable = Path(original["config"]["codex_executable"])
    if not executable.is_absolute() or not executable.is_file():
        raise ResearchError("event_extraction_codex_executable_unavailable")
    config = {"codex_executable": str(executable), "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "codex_model": "gpt-6-luna", "reasoning_effort": "low", "timeout_seconds": 180,
        "max_input_bytes": 131072, "max_output_bytes": 65536}
    versions = dict(previous["versions"]) if previous else {"dataset": dataset_id, "protocol": protocol}
    contents = {"question": {"text": "What specific event mentions and evidence-backed arguments occur in each complete saved article?"},
        "selection": {"rules": method["selection"], "original_group_result": original["group_result"]},
        "dossier_definition": {"unit": "One real-world event across reporting; this operation extracts mentions only"},
        "codebook": {"labels": ["events_found", "no_event", "insufficient_evidence"], "event_schema": answer_schema()},
        "prompt": {"instructions": TASK_INSTRUCTION, "details_schema": answer_schema()},
        "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
        "model_profile": config}
    if previous:
        if previous["config"] != config or previous["original_plan"] != old["plan"]:
            raise ResearchError("event_extraction_partial_preparation_inputs_changed")
        for kind, reference in versions.items():
            engine.ledger.get(reference, kind)
    else:
        for kind, content in contents.items():
            versions[kind] = engine._version(session, Context(context.objective, context.actor, versions), {
                "kind": kind, "key": key, "content": content})["id"]
    bound = Context(context.objective, context.actor, versions)
    inputs = load_frame(engine, session, original)
    current, metadata, frame = inputs["current"], inputs["metadata"], inputs["frame"]
    if current.get("rule", {}).get("publication_gap_days") != 7:
        raise ResearchError("event_extraction_original_seven_day_frame_required")
    selection = select_pilot(original["membership"], metadata, frame, unavailable, seed)
    if previous:
        frozen = engine.ledger.artifacts.read(previous["selection"])
        if selection != frozen:
            raise ResearchError("event_extraction_partial_preparation_selection_changed")
        selection = frozen
    if previous:
        selection_ref, manifest = previous["selection"], partial[0][0]
        engine.ledger.append(session, "analysis.cache_reused", {"manifest": manifest,
            "reason": "Resume exact partial preparation without redraw or changed versions"})
    else:
        selection_ref = save(engine, session, selection, "Complete frozen selection/exclusions before source inspection; no labels or vectors read")
        manifest = engine.ledger.record(session, "event_extraction_preparation_manifest", key, {
            "method": METHOD, "versions": versions, "study_binding": binding, "selection": selection_ref,
            "original_result": original_id, "original_plan": old["plan"], "pair_plan": inputs["pair_plan_id"],
            "metadata_artifact": inputs["metadata_artifact"], "body_fold_artifact": inputs["frame_artifact"],
            "input_provenance": inputs["provenance"], "config": config})
    tasks, examples, reviews = [], [], []
    passage_count = body_characters = 0
    for n, selected in enumerate(selection["selected"]):
        source_id = selected["source_version"]
        request, example = _source_request(engine, session, source_id, metadata[source_id], versions)
        task = {**selected, "task_id": digest({"study_binding": binding, "source_version": source_id}),
            "phase": "canary" if n < 2 else "pilot", "status": "source_unavailable", "request": None}
        if request:
            task["request"] = save(engine, session, request, "Exact full-source extraction packet; no approval or dispatch")
            task["wire_bytes"] = len(build_prompt(request).encode("utf-8"))
            task["status"] = "prepared" if task["wire_bytes"] <= config["max_input_bytes"] else "oversize"
            passage_count += len(request["evidence"])
            body_characters += len(request["body"])
        tasks.append(task)
        examples.append({**example, "selection_stratum": selected["selection_stratum"]})
        reviews.append({"source_version": source_id, "request": task["request"], "article": example,
            "evidence": request["evidence"] if request else [], "reviewer": None, "reviewed_at": None,
            "event_completeness": None, "unsupported_fields": [], "wrong_roles": [], "date_errors": [],
            "factuality_errors": [], "merged_or_split_events": [], "proposed_corrections": [], "notes": None})
    review = save(engine, session, {"method": METHOD + ":blank-review", "versions": versions,
        "manifest": manifest, "instructions": "Copy before editing. Identify reviewer; inspect full text and field evidence. No model answers or memberships supplied; this is development review, not independent held-out gold.",
        "reviews": reviews}, "Blank source-linked human-review material; zero reviews, not an acceptance operation")
    value = {"method": METHOD, "versions": versions, "study_key": key, "study_binding": binding,
        "original_result": original_id, "original_plan": old["plan"], "group_result": original["group_result"],
        "manifest": manifest, "implementation": code, "config": config, "tasks": tasks,
        "selection": {k: v for k, v in selection.items() if k not in {"selected", "exclusions"}},
        "selection_artifact": selection_ref, "examples": examples, "review_template_artifact": review,
        "review_template_path": str(engine.ledger.artifacts.root / review),
        "limits": {"max_requests": 12, "max_article_exposures": 12, "max_retries": 0},
        "canary_count": 2, "passage_count": passage_count, "body_characters": body_characters,
        "new_embeddings": 0, "new_model_calls": 0, "model_authorized": False, "memberships_changed": False,
        "human_validated": False, "owner_workspace": str(engine.ledger.root.resolve())}
    return present(engine, session, bound, "luna_group_validation_plan", value, render_plan(value), key)


def _bound_plan(engine: Any, session: str, context: Context, identifier: str) -> tuple[Json, Context]:
    from .event_extraction_contract import validate_request

    require_active(engine, session)
    plan = engine.ledger.get(identifier, "luna_group_validation_plan")
    if plan.get("method") != METHOD or plan.get("implementation") != implementation():
        raise ResearchError("event_extraction_execution_binding_changed")
    if Path(plan["owner_workspace"]).resolve() != engine.ledger.root.resolve():
        raise ResearchError("event_extraction_plan_owner_changed")
    if context.versions and context.versions != plan["versions"]:
        raise ResearchError("event_extraction_context_changed")
    original = engine.ledger.get(plan["original_plan"], "luna_group_validation_plan")
    _owner(engine, original)
    if (plan["limits"] != {"max_requests": 12, "max_article_exposures": 12, "max_retries": 0}
            or not 0 <= len(plan["tasks"]) <= 12 or plan["canary_count"] != 2
            or len({t["task_id"] for t in plan["tasks"]}) != len(plan["tasks"])
            or len({t["source_version"] for t in plan["tasks"]}) != len(plan["tasks"])):
        raise ResearchError("event_extraction_plan_limits_invalid")
    for kind, reference in plan["versions"].items():
        engine.ledger.get(reference, kind)
    for n, task in enumerate(plan["tasks"]):
        if (task["task_id"] != digest({"study_binding": plan["study_binding"], "source_version": task["source_version"]})
                or task["phase"] != ("canary" if n < 2 else "pilot")):
            raise ResearchError("event_extraction_task_identity_changed")
        if task["status"] not in {"prepared", "oversize", "source_unavailable"}:
            raise ResearchError("event_extraction_preparation_status_invalid")
        if task["request"]:
            request = engine.ledger.artifacts.read(task["request"])
            validate_request(request)
            if request["versions"] != plan["versions"] or request["source"]["source_version"] != task["source_version"]:
                raise ResearchError("event_extraction_request_binding_changed")
        elif task["status"] != "source_unavailable":
            raise ResearchError("event_extraction_request_missing")
    return plan, Context(context.objective, context.actor, plan["versions"])


class EventExtractionResearch(Research):
    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data.get("phase") == "prepare":
            return prepare(self, session, context, data)
        if data.get("phase") == "execute":
            from .event_extraction_execution import execute

            return execute(self, session, context, data)
        if data.get("phase") == "approve":
            from .event_extraction_execution import execute, validate_approval

            if set(data) != {"phase", "plan", "approval", "reuse_cache"} or data["reuse_cache"] is not True:
                raise ResearchError("event_extraction_approval_fields_invalid")
            plan, bound = _bound_plan(self, session, context, data["plan"])
            validate_approval(data["approval"], data["plan"], plan)
            policy = self._version(session, bound, {"kind": "policy", "key": plan["study_key"] + "-approval",
                "content": data["approval"]})["id"]
            return execute(self, session, bound, {"phase": "execute", "plan": data["plan"],
                "approval_policy": policy, "reuse_cache": True})
        raise ResearchError("event_extraction_phase_invalid")
