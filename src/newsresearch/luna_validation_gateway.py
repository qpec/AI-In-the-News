"""Bounded Luna lead-screen execution through the shared audited Codex gateway.

Lead references are provisional model observations, never human gold. This is a
separate study: it neither spends nor reopens the historical cutoff study.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from .codex_provider import CodexCLIProvider
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .luna_group_validation import candidate_pool_recall, group_precision
from .luna_lead_answers import validate_answer, validate_request


class LunaProvider(CodexCLIProvider):
    """Pin model and effort in the exact command validated by the base transport."""

    def __init__(self, workspace: Path, config: Json) -> None:
        if config["codex_model"] != "gpt-6-luna" or config["reasoning_effort"] != "low":
            raise ResearchError("luna_model_or_effort_changed")
        super().__init__(workspace, executable=config["codex_executable"], model="gpt-6-luna",
                         timeout_seconds=config["timeout_seconds"],
                         max_input_bytes=config["max_input_bytes"],
                         max_output_bytes=config["max_output_bytes"])

    def _command(self, cwd: Path) -> tuple[str, ...]:
        command = super()._command(cwd)
        return (*command[:-1], "-c", 'model_reasoning_effort="low"', command[-1])


def _implementation() -> Json:
    names = ("luna_validation_gateway.py", "luna_validation_study.py", "luna_lead_answers.py",
             "luna_group_validation.py", "codex_provider.py", "gateway.py")
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in names}


def _approval(policy: Json, plan_id: str, study: str) -> None:
    required = {"method": "luna-validation-run-approval-v1", "plan": plan_id, "study_key": study,
                "allow_codex_account_execution": True, "allow_external_processing": True,
                "max_requests": 400, "max_article_exposures": 6000, "max_retries": 0}
    if any(policy.get(key) != value or type(policy.get(key)) is not type(value)
           for key, value in required.items()):
        raise ResearchError("luna_concrete_approval_required")
    if any(not isinstance(policy.get(key), str) or not policy[key].strip()
           for key in ("approved_by", "instruction")):
        raise ResearchError("luna_approval_actor_or_instruction_missing")
    try:
        expires = datetime.fromisoformat(policy["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None or expires <= datetime.now(timezone.utc):
            raise ValueError("expired or naive")
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        raise ResearchError("luna_approval_expired_or_invalid") from error


def _artifact(engine: Any, session: str, value: Json, purpose: str) -> str:
    ref = engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": ref, "purpose": purpose})
    return str(ref)


def _bind(engine: Any, session: str, binding: Json) -> None:
    rows = engine.ledger.db.execute(
        "SELECT payload FROM events WHERE kind='luna.validation.authorization.bound' "
        "AND json_extract(payload,'$.study_key')=?", (binding["study_key"],)).fetchall()
    if rows:
        if any(json.loads(row[0])["binding"] != binding for row in rows):
            raise ResearchError("luna_study_authorization_or_implementation_changed")
        return
    record = engine.ledger.record(session, "luna_validation_authorization", binding["study_key"], binding)
    engine.ledger.append(session, "luna.validation.authorization.bound",
                         {"study_key": binding["study_key"], "binding": binding, "record": record})


def _history(engine: Any, study: str) -> list[Json]:
    return [json.loads(row[0]) for row in engine.ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' "
        "AND json_extract(payload,'$.luna_validation_study')=?", (study,)).fetchall()]


def _complete(engine: Any, session: str, task: Json, intended: Json, response: Any) -> Json:
    raw = asdict(response)
    response_ref = engine.ledger.artifacts.put(raw)
    engine.ledger.append(session, "codex.response.received",
                         {"artifact": response_ref, "attempt": intended["attempt"]})
    request = engine.ledger.artifacts.read(task["request_ref"])
    validation, answer, error = {}, None, None
    unknown = bool((response.raw_response or {}).get("unknown_outcome"))
    try:
        if unknown:
            raise ResearchError("luna_transport_unknown_outcome")
        if response.payload is None:
            raise ResearchError((response.raw_response or {}).get("failure") or "luna_response_missing")
        validation = validate_answer(request, response.payload)
        answer = response.payload
    except AuditError:
        raise
    except ResearchError as failure:
        error = str(failure)
    status = "unknown" if unknown else ("valid" if answer is not None else "invalid")
    value = {"task": task["logical_id"], "request": task["request_ref"], "response": response_ref,
             "answer": answer, "validation": validation, "status": status, "error": error,
             "configured_model": "gpt-6-luna", "observed_model": response.model,
             "request_id": response.request_id, "usage": response.usage,
             "human_validated": False}
    assessment = engine.ledger.record(session, "luna_lead_assessment", intended["attempt"], value)

    def projection(event: int) -> None:
        engine.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
            intended["attempt"], intended["task_key"], intended["batch"], intended["number"],
            task["request_ref"], response_ref, status, assessment, None, event))

    event_kind = "model.attempt.unobserved" if unknown else "model.attempt.completed"
    engine.ledger.append(session, event_kind, {"attempt": intended["attempt"], "status": status,
        "response": response_ref, "assessment": assessment, "validation": validation,
        "ended_at": utc()}, projection)
    if not unknown:
        engine.ledger.unresolved.pop(intended["attempt"], None)
    return {**value, "assessment": assessment, "attempt": intended["attempt"]}


def _metrics(plan: Json, outcomes: dict[str, Json]) -> Json:
    labels, relations = {}, []
    frames = plan["anchor_frames"]
    if isinstance(frames, dict):
        frames = list(frames.values())
    by_anchor = {frame["anchor"]: frame for frame in frames}
    for task in plan["tasks"]:
        outcome = outcomes.get(task["logical_id"], {})
        answer = outcome.get("answer") if outcome.get("status") == "valid" else None
        fallback = "failed" if outcome.get("status") in {"invalid", "unknown", "failed"} else "pending"
        if task["status"] != "prepared":
            fallback = "failed"
        if task["mode"] == "group":
            label = answer["group_label"] if answer is not None else fallback
            labels[task["logical_id"]] = "mixed" if label == "mixed_events" else label
        else:
            anchor = task["logical_id"]
            references = {row["source_version"]: row["label"]
                          for row in answer["relations"]} if answer is not None else {}
            for row in by_anchor[anchor]["candidates"]:
                candidate = row["candidate"]
                relations.append({"anchor": anchor, "candidate": candidate,
                                  "label": references.get(candidate, fallback)})
    folds = {}
    for fold in ("audit", "held_out"):
        selected = [task["logical_id"] for task in plan["tasks"]
                    if task["mode"] == "group" and task["fold"] == fold]
        folds[fold] = group_precision(selected, {group: labels[group] for group in selected})
    return {"group_precision": group_precision(plan["groups"], labels),
            "fold_group_precision": folds,
            "candidate_pool_recall": candidate_pool_recall(list(by_anchor), relations, plan["membership"],
                bootstrap_seed=plan["sampling"]["group_frame"]["seed"]),
            "relations": relations}


def execute(engine: Any, session: str, context: Context, data: Json) -> Json:
    """Run or explicitly reuse one frozen, independently budgeted study; never retry."""
    require_active(engine, session)
    if engine.config.offline:
        raise ResearchError("luna_codex_execution_requires_explicit_online_mode")
    if data.get("reuse_cache") is not True or type(data.get("workers", 4)) is not int:
        raise ResearchError("luna_explicit_cache_reuse_and_integer_workers_required")
    workers = data.get("workers", 4)
    if not 1 <= workers <= 4:
        raise ResearchError("luna_workers_outside_1_4")
    plan = engine.ledger.get(data["plan"], "luna_group_validation_plan")
    study = data["study_key"]
    if (not isinstance(study, str) or not study.strip() or study != plan["study_key"]
            or plan["versions"] != context.versions):
        raise ResearchError("luna_plan_study_or_versions_mismatch")
    policy = engine.ledger.get(data["run_approval"], "policy")["content"]
    _approval(policy, data["plan"], study)
    config = plan["config"]
    executable = Path(config["codex_executable"])
    if (not executable.is_absolute() or not executable.is_file()
            or hashlib.sha256(executable.read_bytes()).hexdigest() != config["executable_sha256"]):
        raise ResearchError("luna_codex_executable_changed")
    if not plan["workload"]["within_budget"]:
        raise ResearchError("luna_prepared_workload_exceeds_budget")
    binding = {"study_key": study, "plan": data["plan"], "approval_policy": data["run_approval"],
               "approval": policy, "versions": context.versions, "config": config,
               "implementation": _implementation(), "automatic_retries": 0}
    _bind(engine, session, binding)
    manifest = _artifact(engine, session, {"binding": binding, "tasks": plan["tasks"],
        "sampling": plan["sampling"], "workload": plan["workload"]}, "Frozen Luna study execution manifest")
    batch = engine.ledger.record(session, "luna_validation_batch", digest(binding),
                                 {"manifest": manifest, "binding": binding})
    history = _history(engine, study)
    spent, exposures = len(history), sum(item["article_exposures"] for item in history)
    if spent > 400 or exposures > 6000:
        raise ResearchError("luna_historical_budget_exceeded")
    provider = LunaProvider(engine.ledger.root / "codex-workers", config)
    outcomes: dict[str, Json] = {}
    blocked = None
    tasks = sorted(plan["tasks"], key=lambda task: (task["fold"] == "held_out", task["logical_id"]))
    if len({task["logical_id"] for task in tasks}) != len(tasks):
        raise ResearchError("luna_duplicate_logical_task_id")
    pending_tasks, known_keys = [], set()
    for task in tasks:
        key = digest({"binding": binding, "task": task})
        known_keys.add(key)
        previous = [item for item in history if item["task_key"] == key]
        if task["status"] != "prepared":
            if previous:
                raise ResearchError("luna_unprepared_task_has_dispatch_history")
            outcomes[task["logical_id"]] = {"status": "failed", "error": task["status"], "answer": None}
        elif previous:
            if len(previous) != 1:
                raise ResearchError("luna_duplicate_attempt_history")
            row = engine.ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?",
                                           (previous[0]["attempt"],)).fetchone()
            if row is not None and row[1] is not None:
                value = engine.ledger.get(row[1], "luna_lead_assessment")
                outcomes[task["logical_id"]] = {**value, "assessment": row[1]}
                if row[0] == "valid":
                    validate_answer(engine.ledger.artifacts.read(task["request_ref"]), value["answer"])
                    engine.ledger.append(session, "model.cache.reused", {"task_key": key,
                        "attempt": previous[0]["attempt"], "versions": context.versions,
                        "assessment": row[1], "luna_validation_study": study})
                    continue
            else:
                outcomes[task["logical_id"]] = {"status": "unknown", "answer": None,
                                                "attempt": previous[0]["attempt"]}
            blocked = "Prior failed or unresolved attempt; no automatic retry"
        else:
            pending_tasks.append(task)
    if any(item["task_key"] not in known_keys for item in history):
        raise ResearchError("luna_dispatch_history_outside_frozen_plan")
    heldout_open = bool(engine.ledger.db.execute(
        "SELECT 1 FROM events WHERE kind='luna.validation.holdout.opened' "
        "AND json_extract(payload,'$.study_key')=? LIMIT 1", (study,)).fetchone())
    cursor = 0
    while cursor < len(pending_tasks) and not blocked:
        fold = pending_tasks[cursor]["fold"]
        block: list[Json] = []
        while cursor < len(pending_tasks) and len(block) < workers and pending_tasks[cursor]["fold"] == fold:
            block.append(pending_tasks[cursor])
            cursor += 1
        prepared: list[tuple[Any, str]] = []
        dispatched: list[tuple[Json, Json]] = []
        for task in block:
            _approval(policy, data["plan"], study)
            key = digest({"binding": binding, "task": task})
            if spent + 1 > 400 or exposures + len(task["source_versions"]) > 6000:
                blocked = "Workflow-wide request/article-exposure cap reached"
                break
            request = engine.ledger.artifacts.read(task["request_ref"])
            validate_request(request)
            if [article["source_version"] for article in request["articles"]] != task["source_versions"]:
                raise ResearchError("luna_task_sources_changed")
            if task["fold"] == "held_out" and not heldout_open:
                engine.ledger.append(session, "luna.validation.holdout.opened",
                    {"study_key": study, "plan": data["plan"], "frozen_manifest": manifest,
                     "purpose": "Separate lead-study frozen validation; historical holdout untouched"})
                heldout_open = True
            invocation = provider.prepare(request)
            dispatch = _artifact(engine, session, invocation.manifest(), "Exact Luna Codex invocation before dispatch")
            intended = {"attempt": str(uuid.uuid4()), "task_key": key, "number": 1,
                "batch": batch, "request": task["request_ref"], "dispatch": dispatch, "started_at": utc(),
                "luna_validation_study": study, "article_exposures": len(task["source_versions"]),
                "source_versions": task["source_versions"], "approval_policy": data["run_approval"]}
            engine.ledger.append(session, "model.attempt.intended", intended)
            engine.ledger.unresolved[intended["attempt"]] = intended
            history.append(intended)
            spent += 1
            exposures += intended["article_exposures"]
            prepared.append((invocation, intended["attempt"]))
            dispatched.append((task, intended))
        for index, response in engine.gateway.codex_dispatch(session, provider, prepared, workers):
            task, intended = dispatched[index]
            outcome = _complete(engine, session, task, intended, response)
            outcomes[task["logical_id"]] = outcome
            if outcome["status"] != "valid":
                blocked = "Technical/validation failure or unknown outcome; new dispatch stopped"
    metrics = _metrics(plan, outcomes)
    counts = {status: sum(outcome.get("status") == status for outcome in outcomes.values())
              for status in ("valid", "invalid", "unknown", "failed")}
    pending = len(tasks) - len(outcomes)
    result = {"versions": context.versions, "plan": data["plan"], "study_key": study,
        "group_result": plan["group_result"], "manifest": manifest, "batch": batch,
        "status": "complete" if not blocked and counts["valid"] == len(tasks) else "partial",
        "obstacle": blocked or ("Frozen source-unavailable or oversize tasks remain unjudged"
                                if counts["failed"] else None),
        "expected_tasks": len(tasks), "task_counts": {**counts, "pending": pending},
        "preparation_missing_counts": {status: sum(task["status"] == status for task in tasks)
                                       for status in ("source_unavailable", "oversize")},
        "workflow_model_attempts": spent, "workflow_article_exposures": exposures,
        "automatic_retries": 0, "outcomes": outcomes, **metrics, "examples": plan.get("examples", []),
        "configured_model": "gpt-6-luna", "reasoning_effort": "low", "human_validated": False,
        "holdout_scope": "Distinct frozen tasks; anchor candidates can overlap held-out group articles/events",
        "full_articles_read": False, "accepted_dossiers": 0, "membership_changes": 0,
        "historical_study_budget_changed": False, "model_metadata": "Observed identity and usage retained per attempt; unavailable stays null"}
    identifier = engine.ledger.record(session, "luna_group_validation_result", digest(result), result)
    presentation = engine._record_presentation(session, context,
        {"results": [{"kind": "luna_group_validation_result", "id": identifier}],
         "markdown": render_result(result), "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **result, "presentation": presentation}


def render_result(result: Json) -> str:
    """Concrete coverage and uncertainty, without treating model labels as gold."""
    precision, recall = result["group_precision"], result["candidate_pool_recall"]
    heldout = result["fold_group_precision"]["held_out"]
    def percent(value: Any) -> str:
        return "unavailable" if value is None else f"{100 * value:.1f}%"
    text = (f"Luna title/first-three-paragraph grouping check: {result['status']}.\n\n"
        f"Tasks: {result['expected_tasks']}; outcomes {result['task_counts']}. "
        f"Preparation exclusions {result['preparation_missing_counts']}. "
        f"Study attempts {result['workflow_model_attempts']}/400; article exposures "
        f"{result['workflow_article_exposures']}/6,000; automatic retries 0.\n\n"
        f"Entire-group precision against lead-only model references: "
        f"{percent(precision['complete_case_precision'])}; group labels {precision['counts']}; "
        f"unknown groups {precision['unknown_groups']}. Bounds including unknowns: "
        f"{percent(precision['identified_bounds']['lower'])}–{percent(precision['identified_bounds']['upper'])}. "
        f"Complete-case Wilson 95% diagnostic: {precision['complete_case_wilson_95']}.\n\n"
        f"Frozen held-out group subset: {heldout['expected_groups']} groups; "
        f"precision {percent(heldout['complete_case_precision'])}; labels {heldout['counts']}.\n\n"
        f"Recall within the frozen examined candidate pool: "
        f"{percent(recall['complete_case_candidate_pool_recall'])}; same-event pairs captured "
        f"{recall['same_event_inside']}, missed {recall['same_event_outside']}; "
        f"unknown inside/outside {recall['unknown_inside']}/{recall['unknown_outside']}. "
        f"Bounds including unknowns: {percent(recall['identified_bounds']['lower'])}–"
        f"{percent(recall['identified_bounds']['upper'])}. "
        f"Anchor-bootstrap 95% diagnostic: {recall['bootstrap']['complete_case_95']}. "
        "Full-corpus recall is not estimable from this pool. Intervals exclude model error.\n\n"
        "Provisional Luna references; no human validation or full-article reading. "
        "Held-out tasks may share articles/events with anchor candidate pools. "
        "No group memberships or accepted dossiers changed. "
        f"Remaining obstacle: {result['obstacle'] or 'none'}.")
    examples = []
    for example in result.get("examples", []):
        outcome = result["outcomes"].get(example["logical_id"], {})
        if outcome.get("answer") is None:
            continue
        articles = []
        for article in example["articles"]:
            title = str(article.get("title") or article["source_version"]).replace("\n", " ")
            title = title.replace("[", "\\[").replace("]", "\\]")
            articles.append(f"[{title}]({article['url']})" if article.get("url") else title)
        examples.append(f"- {outcome['answer']['group_label']}: " + "; ".join(articles))
        if len(examples) == 3:
            break
    if examples:
        text += "\n\nAvailable reviewed lead-screen examples:\n\n" + "\n".join(examples)
    else:
        text += "\n\nNo validated model-reference example is available in the frozen example subset."
    return text
