"""Audited, blinded human-reference files; identity is self-asserted, not verified."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .common import Context, Json, ResearchError, digest, require_active, require_no_credentials
from .event_pair_reference import TASK_INSTRUCTION, validate_answer, validate_request
from .storage import check_permissions

METHOD = "fast-event-pair-evaluation-human-review-v1"


def _bind(engine: Any, session: str, context: Context, plan_id: str) -> tuple[Json, Context, list[Json]]:
    from .event_eval_workflow import METHOD as evaluation_method

    require_active(engine, session)
    protocol = engine._version(session, context, {"kind": "protocol", "key": METHOD,
        "content": {"method": METHOD, "plan": plan_id, "instructions": TASK_INSTRUCTION,
            "identity": "Identified self-asserted human; not independently authenticated",
            "corrections": "Append; changed annotations must supersede the latest pair reference",
            "missingness": "Unfilled rows never delete earlier references; otherwise remain pending",
            "model_calls": 0, "independent_human_gold_validated": False},
        "amend_latest": True, "reason": "Register blinded human-reference method before reading plan or evidence"})["id"]
    plan = engine.ledger.get(plan_id, "luna_group_validation_plan")
    if plan.get("method") != evaluation_method or (context.versions and context.versions != plan["versions"]):
        raise ResearchError("event_eval_human_review_plan_or_versions_invalid")
    tasks = [task for task in plan["tasks"] if task["phase"] == "evaluation"]
    if (len(tasks) > 64 or len({task["pair_id"] for task in tasks}) != len(tasks)
            or {task["pair_id"] for task in tasks} != {row["pair_id"] for row in plan["design"]["selected_pairs"]}):
        raise ResearchError("event_eval_human_review_frame_invalid")
    return plan, Context(context.objective, context.actor, {**plan["versions"], "protocol": protocol}), tasks


def _row(engine: Any, session: str, plan: Json, task: Json) -> Json:
    request = None
    if task.get("request"):
        request = engine.ledger.artifacts.read(task["request"])
        validate_request(request)
        if (request["versions"] != plan["versions"]
                or [a["source_version"] for a in request["articles"]] != [task["left"], task["right"]]):
            raise ResearchError("event_eval_human_review_request_binding_invalid")
        engine.ledger.append(session, "event.eval.human.evidence.inspected", {
            "request": task["request"], "pair_id": task["pair_id"],
            "passages": [span["parent_ref"] for span in request["evidence"]],
            "purpose": "Blinded human-reference preparation or import; actual human reading unobserved"})
    return {"pair_id": task["pair_id"], "request_hash": task.get("request"),
            "articles": request["articles"] if request else [], "evidence": request["evidence"] if request else [],
            "label": None, "support_span_ids": [], "reason": ""}


def review_template(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_eval_workflow import present, save

    plan, bound, tasks = _bind(engine, session, context, data["plan"])
    template = {"method": METHOD, "plan": data["plan"], "instructions": TASK_INSTRUCTION,
                "reviews": [_row(engine, session, plan, task) for task in tasks]}
    artifact = save(engine, session, template, "Exact blinded human-reference template; copy before editing")
    value = {"method": METHOD + ":template", "versions": bound.versions, "plan": data["plan"],
             "template_artifact": artifact, "template_path": str(engine.ledger.artifacts.root / artifact),
             "expected_pairs": len(tasks), "unavailable_requests": sum(not task.get("request") for task in tasks),
             "model_calls": 0, "human_reviews_created": 0, "independent_human_gold_validated": False}
    return present(engine, session, bound, "luna_group_validation_diagnostic", value,
        f"Blinded human-reference template: {len(tasks)} evaluation pairs; {value['unavailable_requests']} unavailable requests; "
        f"zero model calls and zero human references. Protected template: {value['template_path']}. "
        "Copy the template to a new JSON file inside this protected workspace before editing. "
        "Canaries, model answers, groups, sampling strata and ranks are omitted. Human identity and independent gold remain unverified.")


def import_reviews(engine: Any, session: str, context: Context, data: Json) -> Json:
    from .event_eval_math import estimate_pair_metrics
    from .event_eval_workflow import present

    plan, bound, tasks = _bind(engine, session, context, data["plan"])
    reviewer = data.get("reviewer")
    if (not context.actor.startswith("human:") or not context.actor[6:].strip()
            or not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 160):
        raise ResearchError("event_eval_identified_human_reviewer_required")
    path = Path(data["reviews_file"]).expanduser().absolute()
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction() or (component / ".git").exists():
            raise ResearchError("event_eval_review_file_links_or_git_forbidden")
    try:
        path.resolve(strict=True).relative_to(engine.ledger.root.resolve())
    except (ValueError, OSError) as error:
        raise ResearchError("event_eval_review_file_must_be_inside_own_workspace") from error
    check_permissions(path)
    raw = path.read_bytes()
    if len(raw) > 8 * 1024 * 1024:
        raise ResearchError("event_eval_review_file_too_large")
    text = raw.decode("utf-8")
    require_no_credentials(text)
    if re.search(r'"(?:api[_-]?key|authorization|password|access[_-]?token|secret|credential)"\s*:', text, re.I):
        raise ResearchError("event_eval_review_credential_like_field_forbidden")
    artifact = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": artifact,
        "purpose": "Exact permitted human-reference file bytes before parsing", "bytes": len(raw)})
    document = json.loads(text)
    require_no_credentials(document)
    if (not isinstance(document, dict) or document.get("method") != METHOD or document.get("plan") != data["plan"]
            or set(document) - {"method", "plan", "instructions", "reviews"}
            or document.get("instructions", TASK_INSTRUCTION) != TASK_INSTRUCTION
            or not isinstance(document.get("reviews"), list) or len(document["reviews"]) > 64):
        raise ResearchError("event_eval_review_document_invalid")
    expected, seen, staged = {task["pair_id"]: task for task in tasks}, set(), []
    for row in document["reviews"]:
        if (not isinstance(row, dict) or not isinstance(row.get("pair_id"), str)
                or row["pair_id"] not in expected or row["pair_id"] in seen):
            raise ResearchError("event_eval_review_pair_or_fields_invalid")
        seen.add(row["pair_id"])
        task = expected[row["pair_id"]]
        original = _row(engine, session, plan, task)
        if set(row) != set(original) | ({"supersedes"} if "supersedes" in row else set()):
            raise ResearchError("event_eval_review_pair_or_fields_invalid")
        if any(row[key] != original[key] for key in ("pair_id", "request_hash", "articles", "evidence")):
            raise ResearchError("event_eval_review_evidence_or_request_changed")
        if row["label"] is None:
            continue
        if not task.get("request"):
            raise ResearchError("event_eval_review_unavailable_source_cannot_be_judged")
        answer = {key: row[key] for key in ("label", "support_span_ids", "reason")}
        validation = validate_answer(engine.ledger.artifacts.read(task["request"]), answer)
        key = digest({"plan": data["plan"], "pair_id": task["pair_id"]})
        latest = engine.ledger.db.execute("SELECT id FROM records WHERE kind='event_pair_eval_review' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (key,)).fetchone()
        previous = engine.ledger.get(latest[0], "event_pair_eval_review") if latest else None
        unchanged = previous is not None and all(previous[field] == value for field, value in (
            ("answer", answer), ("reviewer", reviewer), ("reviewed_by", context.actor)))
        if (previous and not unchanged and row.get("supersedes") != latest[0]) or (row.get("supersedes") and (not latest or row["supersedes"] != latest[0])):
            raise ResearchError("event_eval_review_correction_requires_latest_supersedes")
        staged.append((task, answer, validation, key, latest[0] if latest else None, unchanged))
    for task, answer, validation, key, latest_id, unchanged in staged:
        if unchanged:
            engine.ledger.append(session, "event.eval.human.review.reused", {"review": latest_id, "import_artifact": artifact})
            continue
        engine.ledger.record(session, "event_pair_eval_review", key, {"plan": data["plan"],
            "pair_id": task["pair_id"], "request": task["request"], "answer": answer, "validation": validation,
            "versions": bound.versions, "reviewer": reviewer, "reviewed_by": context.actor,
            "identity_assurance": "self_asserted", "import_artifact": artifact,
            "independent_human_gold_validated": False}, supersedes=latest_id)
    current = {}
    for record in engine.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_pair_eval_review' ORDER BY created_event"):
        review = json.loads(record["payload"])
        if review["plan"] == data["plan"]:
            current[review["pair_id"]] = {"review": record["id"], **review}
    metrics = estimate_pair_metrics(plan["design"], [{"pair_id": key, "label": value["answer"]["label"]}
        for key, value in current.items()], reference_kind="human")
    value = {"method": METHOD, "versions": bound.versions, "plan": data["plan"], "reviewer": reviewer,
        "identity_assurance": "self_asserted", "independent_human_gold_validated": False,
        "import_artifact": artifact, "imported_filled_rows": len(staged), "reviewed_pairs": len(current),
        "pending_pairs": len(tasks) - len(current), "reviews": current, "metrics": metrics, "model_calls": 0}
    return present(engine, session, bound, "luna_group_validation_result", value,
        f"Human-reference import: {len(current)}/{len(tasks)} evaluation pairs have recorded references; "
        f"{value['pending_pairs']} remain pending. Reviewer: {reviewer}; identity is self-asserted. "
        f"Zero model calls. Reference labels: {metrics['counts']}; pair precision {metrics['pair_precision']}; "
        f"pair recall {metrics['pair_recall']}. Independent human gold and reviewer authentication are unverified. "
        "Intervals condition on correct fixed reference labels. Original model records and memberships are unchanged.")
