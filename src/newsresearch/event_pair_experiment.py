"""Bounded, audited Codex model-reference experiment; never dossier acceptance."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING
import uuid

from . import event_pair_sampling as sampling
from .codex_provider import CodexCLIProvider
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_answers import TASK_KIND, build_request, validate_answer
from .event_pair_study import BUDGET, CRITERION, LIMITATIONS, load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "bounded-codex-event-pair-experiment-v1"


def _expiry(approval: Json) -> None:
    try:
        value = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ResearchError("Event-pair approval needs a timezone-aware expiry") from None
    if value.tzinfo is None or value <= datetime.now(timezone.utc):
        raise ResearchError("Event-pair approval expired or lacks a timezone")


def _approval(data: Json, plan_id: str, plan: Json) -> Json:
    value = data.get("run_approval")
    if not isinstance(value, dict):
        raise ResearchError("A fresh concrete event-pair run approval is required")
    _expiry(value)
    strings = ("authorization_key", "approved_by", "instruction")
    if (any(not isinstance(value.get(k), str) or not value[k].strip() for k in strings)
            or value.get("method") != "event-pair-run-approval-v1"
            or value.get("plan") != plan_id or value.get("study_key") != plan["study_key"]
            or value.get("criterion_hash") != plan["criterion_hash"]
            or value.get("approval_source") != "human_reply_in_current_codex_chat"
            or "observed_chat_timestamp" not in value or value["observed_chat_timestamp"] is not None
            or any(value.get(k) is not True for k in ("authorized", "external_processing_authorized",
                                                     "codex_account_execution_authorized"))
            or any(type(value.get(k)) is not int or value[k] != n for k, n in {
                "max_pair_attempts": 100, "max_article_exposures": 200,
                "max_primary_pairs": 90, "max_known_invalid_retries": 10}.items())):
        raise ResearchError("Approval must explicitly bind this new study, external Codex processing and 100/200 limits")
    return dict(value)


def _config(engine: Research, data: Json) -> Json:
    explicit = "codex_model" in data or "codex_executable" in data
    if explicit == ("model_reference_result" in data):
        raise ResearchError("Choose exact Codex model/executable or one prior RAG result for configuration only")
    if explicit:
        values = {k: data.get(k) for k in ("codex_model", "codex_executable")}
        origin = {"mode": "explicit_model_and_executable"}
    else:
        old = engine.ledger.get(data["model_reference_result"], "rag_query_result")
        binding = engine.ledger.get(old["plan"], "rag_query_plan")["binding"]
        values = {k: binding.get(k) for k in ("codex_model", "codex_executable")}
        origin = {"mode": "prior_RAG_configuration_only", "result": data["model_reference_result"]}
    if any(not isinstance(v, str) or not v.strip() for v in values.values()):
        raise ResearchError("Pin a nonempty Codex model and absolute executable")
    executable = Path(str(values["codex_executable"]))
    if not executable.is_absolute() or not executable.is_file():
        raise ResearchError("Codex executable must be an existing absolute file")
    with executable.open("rb") as stream:
        binary_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    return {**values, "executable_sha256": binary_hash, "timeout_seconds": 180,
            "max_input_bytes": 500_000, "max_output_bytes": 2_000_000,
            "authentication": "existing Codex account; no API fallback", "provider_billing": None,
            "configuration_origin": origin}


def _records(engine: Research, kind: str, key: str) -> list[tuple[str, Json]]:
    return [(row["id"], engine.ledger.get(row["id"], kind)) for row in engine.ledger.db.execute(
        "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event", (kind, key))]


def _spent(engine: Research, study: str) -> list[Json]:
    return [json.loads(row[0]) for row in engine.ledger.db.execute(
        "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.event_pair_study')=?",
        (study,))]


def _request(engine: Research, session: str, row: Json, metadata: Json, versions: dict[str, str]) -> Json:
    articles = []
    for identifier in (row["left"], row["right"]):
        stored = engine.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (identifier,)).fetchone()
        if stored is None or identifier not in metadata:
            raise AuditError("Frozen event-pair source is missing")
        source, summary = json.loads(stored[0]), metadata[identifier]
        body = source.get("body")
        if (source.get("retention") != "permitted" or not isinstance(body, str) or not body.strip()
                or hashlib.sha256(body.encode()).hexdigest() != summary["body_sha256"]
                or source.get("title") != summary.get("title")
                or source.get("published_at") != summary.get("published_at")):
            raise AuditError("Frozen event-pair source body or metadata differs")
        evidence = [engine._evidence(p[0]) for p in engine.ledger.db.execute(
            "SELECT id FROM passages WHERE source_id=? ORDER BY start,id", (identifier,))]
        articles.append({"source_version": identifier, "body": body, "evidence": evidence,
                         "title": summary.get("title"), "published_at": summary.get("published_at")})
        engine.ledger.append(session, "codex.evidence.prepared", {"source_version": identifier,
            "source_text_sha256": summary["body_sha256"], "passage_ids": [p["id"] for p in evidence],
            "coverage": "Complete permitted stored article; publisher completeness unobserved", "task_kind": TASK_KIND})
    return build_request(left=articles[0], right=articles[1], versions=versions)


def _phase(engine: Research, session: str, rows: list[Json], plan_id: str, plan: Json,
           versions: dict[str, str], approval: Json, config: Json, data: Json) -> tuple[dict[str, Json], bool]:
    ledger, study = engine.ledger, plan["study_key"]
    metadata = ledger.artifacts.read(plan["metadata_artifact"])
    provider = CodexCLIProvider(ledger.root / "codex-workers", executable=config["codex_executable"],
        model=config["codex_model"], timeout_seconds=180, max_input_bytes=500_000, max_output_bytes=2_000_000)
    judgements: dict[str, Json] = {}
    tasks: list[Json] = []
    prior = _spent(engine, study)
    for row in rows:
        try:
            request = _request(engine, session, row, metadata, versions)
        except AuditError:
            raise
        except ResearchError as error:
            judgements[row["pair_id"]] = {"status": "failed", "label": None,
                "outcome": "source_input_incomplete_no_dispatch", "reason_code": str(error)}
            continue
        task_key = digest({"plan": plan_id, "request": request, "config": config, "method": METHOD})
        attempts = [value for value in prior if value["task_key"] == task_key]
        if any(v.get("event_pair_study") == study and v.get("pair_id") == row["pair_id"]
               for v in ledger.unresolved.values()):
            judgements[row["pair_id"]] = {"status": "failed", "label": None, "outcome": "unknown"}
            continue
        cached = ledger.db.execute("SELECT result_id,id FROM attempts WHERE task_key=? AND status='valid' ORDER BY number LIMIT 1",
                                   (task_key,)).fetchone()
        if cached:
            if data.get("reuse_cache") is not True:
                raise ResearchError("Exact-version event-pair resume requires reuse_cache=true")
            saved = ledger.get(cached["result_id"], "event_pair_judgement")
            validate_answer(request, saved["result"])
            ledger.append(session, "model.cache_reused", {"task_key": task_key, "attempt": cached["id"],
                "assessment": cached["result_id"], "plan": plan_id, "basis": "explicit_exact_version_bound_resume"})
            judgements[row["pair_id"]] = {"status": "completed", "label": saved["result"]["label"],
                "assessment": cached["result_id"], "cached": True}
            continue
        retry = bool(attempts)
        if retry:
            last = ledger.db.execute("SELECT status,response_ref FROM attempts WHERE task_key=? ORDER BY number DESC LIMIT 1",
                                     (task_key,)).fetchone()
            response = ledger.artifacts.read(last["response_ref"]) if last and last["response_ref"] else {}
            if len(attempts) != 1 or not last or last["status"] != "invalid" or response.get("payload") is None:
                judgements[row["pair_id"]] = {"status": "failed", "label": None, "outcome": "not_retryable"}
                continue
            judgements[row["pair_id"]] = {"status": "failed", "label": None, "outcome": "invalid"}
        request_ref = ledger.artifacts.put(request)
        try:
            invocation = provider.prepare(request)
        except ResearchError as error:
            if str(error) != "codex_input_too_large_no_dispatch":
                raise
            judgements[row["pair_id"]] = {"status": "failed", "label": None, "outcome": "oversize_no_dispatch"}
            continue
        tasks.append({"row": row, "request": request, "request_ref": request_ref, "task_key": task_key,
                      "invocation": invocation, "dispatch_ref": ledger.artifacts.put(invocation.manifest()), "retry": retry})
    batch = ledger.record(session, "codex_batch_manifest", digest({"plan": plan_id, "tasks": [t["task_key"] for t in tasks]}),
        {"versions": versions, "plan": plan_id, "task_kind": TASK_KIND, "event_pair_study": study,
         "items": [{"pair_id": t["row"]["pair_id"], **{k: t[k] for k in ("task_key", "request_ref", "dispatch_ref")}}
                   for t in tasks]})
    stop = any(v.get("event_pair_study") == study for v in ledger.unresolved.values())
    pending = tasks
    for round_number in range(2):
        retry_tasks: list[Json] = []
        for offset in range(0, len(pending), data.get("workers", 4)):
            prepared: list[tuple[Json, str, int]] = []
            for task in pending[offset:offset + data.get("workers", 4)]:
                identifier = task["row"]["pair_id"]
                spent = _spent(engine, study)
                retry = task["retry"] or round_number > 0
                primary = sum(not value["event_pair_retry"] for value in spent)
                retries = len(spent) - primary
                if stop or len(spent) >= 100 or (retries >= 10 if retry else primary >= 90):
                    if judgements.get(identifier, {}).get("outcome") == "invalid":
                        judgements[identifier].update(retry_pending=True, retry_block_reason="stopped_or_budget")
                    else:
                        judgements[identifier] = {"status": "pending", "label": None, "outcome": "stopped_or_budget"}
                    continue
                try:
                    _expiry(approval)
                except ResearchError:
                    stop = True
                    if judgements.get(identifier, {}).get("outcome") == "invalid":
                        judgements[identifier].update(retry_pending=True, retry_block_reason="approval_expired")
                    else:
                        judgements[identifier] = {"status": "pending", "label": None, "outcome": "approval_expired"}
                    continue
                attempt = str(uuid.uuid4())
                number = 1 + sum(value["task_key"] == task["task_key"] for value in spent)
                intent = {"attempt": attempt, "task_key": task["task_key"], "number": number, "batch": batch,
                    "plan": plan_id, "request": task["request_ref"], "dispatch": task["dispatch_ref"],
                    "event_pair_study": study, "pair_id": identifier, "event_pair_retry": retry,
                    "authorization_key": approval["authorization_key"], "reserved_pair_attempts": 1,
                    "reserved_article_exposures": 2, "source_versions": [task["row"]["left"], task["row"]["right"]],
                    "started_at": utc()}
                ledger.append(session, "model.attempt.intended", intent)
                ledger.unresolved[attempt] = intent
                prepared.append((task, attempt, number))
            for n, response in engine.gateway.codex_dispatch(session, provider,
                    [(task["invocation"], attempt) for task, attempt, _ in prepared], data.get("workers", 4)):
                task, attempt, number = prepared[n]
                response_ref = ledger.artifacts.put(asdict(response))
                ledger.append(session, "codex.response.received", {"artifact": response_ref, "attempt": attempt})
                unknown = bool((response.raw_response or {}).get("unknown_outcome"))
                status, validation, assessment = "unknown" if unknown else "invalid", {}, None
                if response.payload is not None and not unknown:
                    try:
                        validation = validate_answer(task["request"], response.payload)
                        assessment = ledger.record(session, "event_pair_judgement", attempt, {"versions": versions,
                            "plan": plan_id, "event_pair_study": study, "pair_id": task["row"]["pair_id"],
                            "task_key": task["task_key"], "attempt": attempt, "request_ref": task["request_ref"],
                            "response_ref": response_ref, "result": response.payload, "validation": validation,
                            "human_validated": False, "observed_model": response.model, "usage": response.usage,
                            "recorded_at": utc()})
                        status = "valid"
                    except AuditError:
                        raise
                    except ResearchError as error:
                        validation = {"status": "invalid", "reason_code": str(error)}
                def project(event: int) -> None:
                    ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (attempt, task["task_key"],
                        batch, number, task["request_ref"], response_ref, status, assessment, None, event))
                ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed",
                    {"attempt": attempt, "status": status, "response": response_ref, "assessment": assessment,
                     "validation": validation, "ended_at": utc()}, project)
                if not unknown:
                    ledger.unresolved.pop(attempt, None)
                else:
                    stop = True
                judgements[task["row"]["pair_id"]] = {"status": "completed" if status == "valid" else "failed",
                    "label": response.payload["label"] if status == "valid" else None,
                    "assessment": assessment, "outcome": status}
                if status == "invalid" and response.payload is not None and number == 1 and round_number == 0:
                    retry_tasks.append(task)
        pending = retry_tasks
    return judgements, stop


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"plan", "run_approval", "codex_model", "codex_executable", "model_reference_result", "workers", "reuse_cache"}:
        raise ResearchError("Unsupported event-pair experiment input")
    if not isinstance(data.get("plan"), str) or not data["plan"].strip():
        raise ResearchError("An immutable event-pair plan is required")
    if type(data.get("workers", 4)) is not int or not 1 <= data.get("workers", 4) <= 4:
        raise ResearchError("Event-pair workers must be 1..4")
    if "reuse_cache" in data and type(data["reuse_cache"]) is not bool:
        raise ResearchError("reuse_cache must be an explicit boolean")
    if engine.config.offline:
        raise ResearchError("Event-pair execution requires process-local online configuration")
    started = utc()
    plan_id = data["plan"]
    plan, frame, development = load_plan(engine, session, plan_id)
    if any(plan["versions"].get(k) != v for k, v in context.versions.items()):
        raise ResearchError("Event-pair context must match the exact plan versions")
    approval, config = _approval(data, plan_id, plan), _config(engine, data)
    implementation = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                      for name in ("event_pair_experiment.py", "codex_provider.py", "event_pair_answers.py")}
    previous = _records(engine, "event_pair_run_authorization", plan["study_key"])
    if previous and any(any(saved["binding"][key] != value for key, value in {
            "plan": plan_id, "study_binding": plan["study_binding"], "approval": approval,
            "config": config, "implementation": implementation}.items()) for _, saved in previous):
        raise ResearchError("Event-pair approval, code, configuration and versions are immutable; cannot reset or reseal")
    method = {"method": METHOD, "budget": BUDGET, "criterion": CRITERION, "implementation": implementation,
              "retry": "Once only for an observed returned payload failing local schema/citation validation; unknown never retried",
              "holdout": "Freeze once before opening; exact-version resume only; no retuning or resealing",
              "provider_billing": None, "hard_provider_token_cost_cap": None}
    protocol = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
        "kind": "protocol", "key": plan["study_key"] + "-execution", "content": method,
        "amend_latest": True, "reason": "Register bounded event-pair model-reference execution before dispatch"})["id"]
    approval_id = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
        "kind": "policy", "key": plan["study_key"] + "-execution", "content": approval,
        "amend_latest": True, "reason": "Register fresh concrete human event-pair run permission"})["id"]
    model_profile = engine._version(session, Context(context.objective, context.actor, plan["versions"]), {
        "kind": "model_profile", "key": plan["study_key"] + "-execution", "content": config,
        "amend_latest": True, "reason": "Bind the exact Codex transport configuration before pair judging"})["id"]
    versions = {**plan["versions"], "protocol": protocol, "policy": approval_id, "model_profile": model_profile}
    binding = {"plan": plan_id, "study_binding": plan["study_binding"], "approval": approval, "config": config,
               "versions": versions, "implementation": implementation}
    if previous and any(record[1]["binding"] != binding for record in previous):
        raise ResearchError("Event-pair approval, code, configuration and versions are immutable; cannot reset or reseal")
    reused_key = engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='event_pair_run_authorization' "
        "AND json_extract(payload,'$.binding.approval.authorization_key')=? AND logical_key<>?",
        (approval["authorization_key"], plan["study_key"])).fetchone()
    if reused_key:
        raise ResearchError("Event-pair authorization key is already bound to another study")
    engine.ledger.record(session, "event_pair_run_authorization", plan["study_key"], {"binding": binding, "versions": versions})
    frozen = _records(engine, "event_pair_candidate", plan["study_key"])
    if len(frozen) > 1:
        raise AuditError("More than one frozen event-pair candidate exists")
    development_judgements, stopped = _phase(engine, session, development["rows"], plan_id, plan, versions, approval, config, data)
    metrics = sampling.evaluate_grid(development["rows"], development_judgements)
    candidate = metrics["candidate_cutoff"]
    validation_sample: Json | None = None
    validation_judgements: dict[str, Json] = {}
    validation: Json | None = None
    if frozen:
        frozen_id, saved = frozen[0]
        if saved["binding"] != digest(binding) or saved["development_metrics"] != metrics:
            raise ResearchError("Frozen candidate cannot be retuned or reopened under changed development results")
        candidate = saved["candidate_cutoff"]
    elif candidate is not None and not stopped:
        saved = {"binding": digest(binding), "versions": versions, "plan": plan_id,
                 "candidate_cutoff": candidate, "development_metrics": metrics, "frozen_at": utc()}
        frozen_id = engine.ledger.record(session, "event_pair_candidate", plan["study_key"], saved)
    else:
        frozen_id = None
    if frozen_id:
        opened = _records(engine, "event_pair_holdout_opened", plan["study_key"])
        if len(opened) > 1:
            raise AuditError("More than one held-out opening exists")
        if opened:
            _, opened_record = opened[0]
            if opened_record["frozen_candidate"] != frozen_id or opened_record["binding"] != digest(binding):
                raise ResearchError("Held-out opening differs from frozen candidate and immutable run")
            validation_sample = engine.ledger.artifacts.read(opened_record["sample_artifact"])
        elif not stopped:
            validation_sample = sampling.sample_validation(frame, candidate, seed=plan["seed"])
            sample_ref = engine.ledger.artifacts.put(validation_sample)
            engine.ledger.append(session, "preparation.artifact.saved", {"artifact": sample_ref,
                "purpose": "Frozen candidate-dependent held-out sample before first held-out model dispatch"})
            engine.ledger.record(session, "event_pair_holdout_opened", plan["study_key"], {
                "binding": digest(binding), "versions": versions, "plan": plan_id, "frozen_candidate": frozen_id,
                "sample_artifact": sample_ref, "opened_at": utc()})
        if validation_sample is not None:
            validation_judgements, stopped = _phase(engine, session, validation_sample["rows"], plan_id, plan,
                versions, approval, config, data)
            validation = sampling.evaluate_validation(validation_sample["rows"], validation_judgements, candidate)
    spent = _spent(engine, plan["study_key"])
    all_judgements = {**development_judgements, **validation_judgements}
    counts = Counter(value.get("label") for value in all_judgements.values() if value["status"] == "completed")
    statuses = Counter(value["status"] for value in all_judgements.values())
    examples: list[Json] = []
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    for pair_id, value in all_judgements.items():
        if value["status"] == "completed" and len(examples) < 3:
            assessment = engine.ledger.get(value["assessment"], "event_pair_judgement")
            examples.append({"pair_id": pair_id, **value, "rationale": assessment["result"]["rationale"],
                "articles": [{**metadata[event["source_version"]], "event": event,
                    "claims": [claim for claim in assessment["result"]["claims"]
                               if claim["source_version"] == event["source_version"]]}
                    for event in assessment["result"]["events"]]})
    result = {"versions": versions, "input_plan_versions": plan["versions"], "plan": plan_id,
        "study_key": plan["study_key"], "run_approval": approval_id, "config": config,
        "candidate_cutoff": candidate, "frozen_candidate": frozen_id, "development_metrics": metrics,
        "development_judgements": development_judgements, "validation": validation,
        "validation_judgements": validation_judgements,
        "development_pairs": len(development["rows"]), "validation_pairs": len(validation_sample["rows"]) if validation_sample else 0,
        "pair_attempts": len(spent), "article_exposures": len(spent) * 2,
        "primary_attempts": sum(not value["event_pair_retry"] for value in spent),
        "retry_attempts": sum(value["event_pair_retry"] for value in spent),
        "counts": {label: counts[label] for label in ("same_event", "different_event", "uncertain")},
        "failed_pairs": statuses["failed"], "pending_pairs": statuses["pending"],
        "unknown_pairs": sum(value.get("outcome") == "unknown" for value in all_judgements.values()),
        "dataset_articles": plan.get("dataset_articles"), "vector_articles": plan.get("processed_articles"),
        "missing_vector_articles": plan.get("missing_articles"), "unique_bodies": plan.get("unique_bodies"),
        "unresolved_attempts": [key for key, value in engine.ledger.unresolved.items() if value.get("event_pair_study") == plan["study_key"]],
        "status": "partial" if statuses["failed"] or statuses["pending"] or stopped else
                  validation["status"] if validation else "inconclusive_development",
        "new_embedding_requests": 0, "accepted_dossiers": 0, "applied_tags": 0, "human_validated": False,
        "provider_billing": None, "provider_internal_request_count": None, "hard_provider_token_cost_cap": None,
        "started_at": started, "completed_at": utc(), "limitations": LIMITATIONS,
        "examples": examples}
    identifier = engine.ledger.record(session, "event_pair_experiment", plan["study_key"], result)
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "event_pair_experiment", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    from .rag_answers import _cell, _excerpt, _link

    lines = [f"Event-pair experiment: **{result['status']}**.", "",
        f"Development pairs: {result['development_pairs']}; held-out pairs opened: {result['validation_pairs']}. "
        f"Pair attempts: {result['pair_attempts']}/100; article exposures: {result['article_exposures']}/200; "
        f"known-invalid retries: {result['retry_attempts']}/10.",
        f"Input dataset articles: {result['dataset_articles']}; with saved vectors: {result['vector_articles']}; "
        f"missing vectors: {result['missing_vector_articles']}; unique stored bodies: {result['unique_bodies']}.",
        f"Model reference labels: same event {result['counts']['same_event']}; different event {result['counts']['different_event']}; "
        f"uncertain {result['counts']['uncertain']}. Known failed pairs: {result['failed_pairs'] - result['unknown_pairs']}; "
        f"unknown pairs: {result['unknown_pairs']}; pending: {result['pending_pairs']}; "
        f"unresolved attempts: {len(result['unresolved_attempts'])}.", "",
        f"Frozen candidate cosine-distance cutoff: {result['candidate_cutoff'] if result['candidate_cutoff'] is not None else 'unavailable'}."]
    grid = result["development_metrics"]["grid"]
    if grid:
        lines += ["", "Development screen (fixed grid and any frozen selected boundary; smaller distance is stricter):", "",
            "| Distance cutoff | Pessimistic weighted precision | Pessimistic weighted recall | Eligible |",
            "|---:|---:|---:|---|"]
        for item in grid:
            if item["cutoff"] not in sampling.GRID and item["cutoff"] != result["candidate_cutoff"]:
                continue
            precision, recall = item["pessimistic_precision"], item["pessimistic_recall"]
            p = "unavailable" if precision is None else f"{precision:.4f}"
            r = "unavailable" if recall is None else f"{recall:.4f}"
            lines.append(f"| {item['cutoff']:.8g} | {p} | {r} | {'yes' if item['eligible'] else 'no'} |")
    if result["validation"]:
        item = result["validation"]
        lines.append(f"Held-out screen: {item['status']}; pessimistic weighted precision {item['pessimistic_precision']}; "
                     f"recall {item['pessimistic_recall']}; failures: {', '.join(item['failures']) or 'none'}.")
    else:
        lines.append("No held-out labels opened; development did not yield a usable candidate or processing stopped.")
    lines += ["", "These are provisional Codex model references, not human gold or a validated correct event cutoff. "
        "No dossiers accepted, no tags applied and no new embeddings requested. Provider billing and internal request counts are unavailable."]
    lines += ["", "Scope limits: " + " ".join(result["limitations"])]
    quoted_sources = set()
    for example in result["examples"]:
        lines.append(f"- Pair `{example['pair_id']}`: {example['label']}; {_cell(example['rationale'])}")
        for article in example["articles"]:
            source = article["source_version"]
            lines.append(f"  {_link(article.get('title') or source, article.get('url'))}.")
            if article["claims"] and source not in quoted_sources:
                claim = article["claims"][0]
                lines.append(f"  Evidence: {_excerpt(claim['quote'])} (passage `{claim['passage_id']}`).")
                quoted_sources.add(source)
    return "\n".join(lines)
