"""Frozen singleton SRS and bounded OpenAI pair references, through the gateway.

This is a separate user-authorized API study, never an old Codex study resume.
Source/model artifacts stay protected; model references never adopt membership.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import secrets
import sqlite3
import time
from typing import Any
import uuid

import numpy as np

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .event_eval_provider import build_prompt
from .event_eval_workflow import present, save
from .event_pair_reference import TASK_INSTRUCTION, build_request, validate_answer, validate_request
from .event_precision_candidate import GROUP_RESULT, _checked_path, verified_record
from .event_provider_candidate import PARENT_CANDIDATE
from .gateway import BOUNDARY, Gateway
from .luna_validation_study import _lead
from .runtime import Research, audited_handler
from .tag_gateway import OpenAITagTransport

METHOD = "singleton-luna-openai-top3-v1"
STUDY = "singleton-luna-openai-100-20261017-v1"
MODEL = "gpt-6-luna"
ENDPOINT = "https://api.openai.com/v1/responses"
OUTPUT_CAP = 1536
USER_INSTRUCTION = "Do a random sample of 100 singletons with Luna but openai api key using this method and show me how many should be grouped, how many are uncertain and how many stay unmatched."


def implementation() -> Json:
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in
            ("singleton_luna_api.py", "event_pair_reference.py", "luna_lead_answers.py", "tag_gateway.py", "gateway.py")}


def sample_singletons(groups: Json, seed: str, size: int = 100) -> list[str]:
    frame = sorted(members[0] for members in groups.values() if len(members) == 1)
    if len(frame) != len(set(frame)) or len(frame) < size:
        raise ResearchError("singleton_sample_frame_invalid")
    return random.Random(seed).sample(frame, size)


def classify(labels: list[str | None]) -> str:
    if len(labels) != 3 or any(label not in {"same_event", "different_event", "uncertain"} for label in labels):
        return "incomplete"
    if "same_event" in labels:
        return "supported_match"
    return "uncertain" if "uncertain" in labels else "unmatched_among_top3"


def wire_body(request: Json) -> Json:
    validate_request(request)
    schema = deepcopy(request["schema"])
    # Keep the local stricter contract; this JSON-schema keyword is not needed
    # on the wire. Duplicate citations still fail local validation.
    schema["properties"]["support_span_ids"].pop("uniqueItems", None)
    return {"model": MODEL, "store": False, "reasoning": {"effort": "low"},
            "max_output_tokens": OUTPUT_CAP,
            "input": [{"role": "developer", "content": BOUNDARY},
                      {"role": "user", "content": build_prompt(request)}],
            "text": {"format": {"type": "json_schema", "name": "event_pair_reference", "strict": True, "schema": schema}}}


def parse_response(parsed: Json) -> Json:
    model = parsed.get("model", "")
    if (parsed.get("status") != "completed" or parsed.get("error") or parsed.get("incomplete_details")
            or not isinstance(model, str) or not (model == MODEL or model.startswith(MODEL + "-"))):
        raise ResearchError("singleton_api_incomplete_or_wrong_model")
    parts = [part for item in parsed.get("output", []) if item.get("type") == "message" for part in item.get("content", [])]
    if len(parts) != 1 or parts[0].get("type") != "output_text":
        raise ResearchError("singleton_api_refused_or_missing_output")
    return json.loads(parts[0]["text"])


def _external_inputs(engine: Any, session: str, capsule: Json) -> tuple[Json, list[Json], bytes]:
    """Read only content-anchored vector artifacts, not the parent's research state."""
    parent = Path(capsule["parent_workspace"])
    current = verified_record(capsule["retained_anchor_records"][GROUP_RESULT], GROUP_RESULT, "event_group_refinement_result")
    identifier = current["plan"]
    sql = "SELECT id,kind,logical_key,artifact,payload,supersedes,created_event FROM records WHERE id=?"
    for path in (parent, parent / "objects", parent / "research.sqlite3"):
        _checked_path(path, root=path == parent)
    for suffix in ("-wal", "-shm"):
        side = parent / ("research.sqlite3" + suffix)
        if side.exists():
            _checked_path(side)
    engine.ledger.append(session, "singleton.external.vector_plan.intended", {
        "sql": sql, "parameters": [identifier], "parent": str(parent),
        "basis": "Exact record ID retained in already verified guarded-group lineage; read-only snapshot, not parent-wide preflight"})
    connection = sqlite3.connect((parent / "research.sqlite3").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        row = connection.execute(sql, (identifier,)).fetchone()
        if row is None:
            raise AuditError("singleton_original_vector_plan_missing")
        spec = dict(row)
        plan = verified_record(spec, identifier, "event_pair_plan")
    finally:
        connection.close()
    if plan["versions"]["dataset"] != current["versions"]["dataset"]:
        raise AuditError("singleton_original_vector_dataset_changed")
    retained: Json = {"plan_record": spec, "parent": str(parent), "parent_archive_reverified": False,
                      "parent_head_inclusion_proof": False, "artifacts": {}}
    raw_values: Json = {}
    for key in ("mapping_artifact", "pooled_vectors_artifact"):
        ref = plan[key]
        if len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref):
            raise AuditError("singleton_vector_artifact_invalid")
        engine.ledger.append(session, "singleton.external.vector_artifact.intended", {"plan": identifier, "role": key, "artifact": ref})
        path = parent / "objects" / ref
        _checked_path(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref:
            raise AuditError("singleton_original_vector_artifact_changed")
        raw_values[key] = json.loads(raw) if key == "mapping_artifact" else raw
        retained["artifacts"][key] = {"sha256": ref, "bytes": len(raw), "complete_contents_verified": True}
    provenance = save(engine, session, retained, "Exact vector-plan record and full-content verification; parent remains preserved")
    return {"plan": identifier, "provenance": provenance, "versions": plan["versions"]}, raw_values["mapping_artifact"], raw_values["pooled_vectors_artifact"]


def prepare(engine: Any, session: str, context: Context) -> Json:
    ledger = engine.ledger
    existing = ledger.db.execute("SELECT id FROM records WHERE kind='luna_group_validation_plan' AND logical_key=?", (STUDY,)).fetchone()
    if existing:
        plan = ledger.get(existing[0], "luna_group_validation_plan")
        if plan.get("method") != METHOD or plan["implementation"] != implementation():
            raise ResearchError("singleton_frozen_plan_implementation_changed")
        text = render_preparation(plan)
        presentation = engine._record_presentation(session, Context(context.objective, context.actor, plan["versions"]), {
            "results": [{"kind": "luna_group_validation_plan", "id": existing[0]}], "markdown": text, "destination": "codex_chat"})
        return {"id": existing[0], **plan, "presentation": presentation}
    method = {"method": METHOD, "study_key": STUDY, "implementation": implementation(),
              "sampling": "SRS without replacement of 100 original guarded-seven-day singleton source IDs; OS seed saved before draw",
              "retrieval": "Exact normalized original pooled article-vector cosine over all 19,549 eligible articles, including other singletons; top 3, self excluded; stable source-ID ties; no temporal filter, no score cutoff",
              "judging": TASK_INSTRUCTION, "lead": "Title <=400 chars plus first 3 nonempty body paragraphs <=3000 chars",
              "aggregation": "All 3 valid: any same -> supported pair-match; else any uncertain -> uncertain; else unmatched among top3. Missing/failure -> incomplete",
              "limits": {"anchors": 100, "requests": 300, "article_exposures": 600, "retries": 0, "workers": 4},
              "canary": "First four actual sample pair requests sequential as structural canaries; included in sample, no extra research calls",
              "transport": "Explicit user-selected OpenAI API using stored key; overrides Luna skill Codex transport for this study only",
              "authorization": USER_INSTRUCTION, "membership_changes": False,
              "quality": "Lead-only model screening, not human gold, full-group consistency, true uniqueness, or corpus recall"}
    protocol = engine._version(session, context, {"kind": "protocol", "key": STUDY, "content": method})["id"]
    parent = ledger.get(PARENT_CANDIDATE, "event_group_refinement_result")
    capsule = ledger.artifacts.read(parent["capsule"])
    groups = capsule["groups"]
    membership = {source: group for group, members in groups.items() for source in members}
    if len(membership) != 19549 or sum(len(v) == 1 for v in groups.values()) != 15537:
        raise AuditError("singleton_original_frame_changed")
    versions = {**parent["versions"], "protocol": protocol}
    contents = {"question": {"text": "Among a random 100 original pilot singletons, how many have a supported same-event match, remain uncertain, or unmatched among three nearest vector candidates?"},
                "selection": {"rules": method["sampling"]},
                "dossier_definition": {"unit": "One real-world event; supported pair links are proposals, not group adoption"},
                "prompt": {"instructions": TASK_INSTRUCTION},
                "codebook": {"labels": ["same_event", "different_event", "uncertain"]},
                "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False},
                "retrieval_profile": {"method": method["retrieval"]},
                "model_profile": {"model": MODEL, "provider": "openai", "transport": ENDPOINT, "reasoning": "low", "max_output_tokens": OUTPUT_CAP,
                                  "price_per_million_input": "0.10", "price_per_million_output": "0.50", "price_checked_on": "2026-10-17"}}
    for kind, content in contents.items():
        versions[kind] = engine._version(session, Context(context.objective, context.actor, versions), {"kind": kind, "key": STUDY, "content": content})["id"]
    previous_seed = ledger.db.execute("SELECT id FROM records WHERE kind='singleton_sample_seed' AND logical_key=?", (STUDY,)).fetchone()
    if previous_seed:
        frozen_seed = ledger.get(previous_seed[0], "singleton_sample_seed")
        if frozen_seed["protocol"] != protocol or frozen_seed["frame_sha256"] != digest(groups):
            raise ResearchError("singleton_sample_seed_binding_changed")
        seed = frozen_seed["seed"]
    else:
        seed = secrets.token_hex(32)
        ledger.record(session, "singleton_sample_seed", STUDY, {"seed": seed, "protocol": protocol, "frame_sha256": digest(groups), "saved_before_draw": True})
    sampled = sample_singletons(groups, seed)
    inputs, mapping, raw = _external_inputs(engine, session, capsule)
    ids = [row["source_version"] for row in mapping]
    if len(set(ids)) != len(ids) or not set(membership) <= set(ids) or len(raw) % (4 * len(ids)):
        raise AuditError("singleton_original_vector_mapping_invalid")
    matrix = np.frombuffer(raw, dtype="<f4").reshape(len(ids), -1)
    positions = {source: pos for pos, source in enumerate(ids)}
    eligible = sorted(membership)
    matrix = matrix[[positions[source] for source in eligible]].copy()
    if not np.isfinite(matrix).all():
        raise AuditError("singleton_nonfinite_vector")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms <= 0):
        raise AuditError("singleton_zero_vector")
    matrix /= norms[:, None]
    positions = {source: pos for pos, source in enumerate(eligible)}
    scores = matrix[[positions[source] for source in sampled]] @ matrix.T
    score_ref = ledger.artifacts.put_bytes(scores.astype("<f4").tobytes())
    ledger.append(session, "retrieval.artifact.saved", {"artifact": score_ref, "dtype": "<f4", "shape": list(scores.shape), "row_ids": sampled, "column_ids_sha256": digest(eligible)})
    rows, tasks, leads = [], {}, {}
    metadata = capsule["articles"]
    for index, source in enumerate(sampled):
        ranked = sorted((candidate for candidate in eligible if candidate != source), key=lambda candidate: (-float(scores[index, positions[candidate]]), candidate))[:3]
        candidates = []
        for candidate in ranked:
            pair = digest(sorted((source, candidate)))
            candidates.append({"source": candidate, "pair": pair, "score": float(scores[index, positions[candidate]]), "group": membership[candidate],
                               "group_size": len(groups[membership[candidate]])})
            if pair not in tasks:
                left, right = sorted((source, candidate))
                for endpoint in (left, right):
                    if endpoint not in leads:
                        leads[endpoint] = _lead(engine, session, endpoint, metadata[endpoint])
                task: Json = {"pair": pair, "left": left, "right": right, "request": None, "body": None, "status": "unavailable"}
                left_lead, right_lead = leads[left], leads[right]
                if left_lead is not None and right_lead is not None:
                    request = build_request(left=left_lead, right=right_lead, versions=versions)
                    body = wire_body(request)
                    if len(canonical(body).encode("utf-8")) > 32768:
                        raise ResearchError("singleton_api_packet_exceeds_bound")
                    task.update(request=save(engine, session, request, "Exact two-lead singleton pair request"),
                                body=save(engine, session, body, "Exact OpenAI JSON body, excludes authentication"), status="prepared")
                tasks[pair] = task
        rows.append({"source": source, "inclusion_probability": 100 / 15537, "candidates": candidates})
    retrieval_ref = save(engine, session, {"anchors": sampled, "eligible_ids": eligible, "scores": score_ref, "shape": list(scores.shape),
                                         "ranked_top3": rows, "score_kind": "Normalized pooled-vector cosine, not identity probability"}, "Complete scored retrieval and exact selected candidates")
    plan = {"method": METHOD, "study_key": STUDY, "implementation": implementation(), "versions": versions, "seed": seed,
            "baseline_group_result": GROUP_RESULT, "capsule": parent["capsule"], "frame_size": 15537, "eligible_articles": len(eligible),
            "rows": rows, "tasks": list(tasks.values()), "vector_inputs": inputs, "retrieval": retrieval_ref,
            "source_metadata": {source: {k: metadata[source].get(k) for k in ("title", "url", "published_at")} for source in leads},
            "limits": method["limits"], "prepared_requests": sum(task["status"] == "prepared" for task in tasks.values()),
            "new_model_calls": 0, "memberships_changed": False, "human_validated": False}
    identifier = ledger.record(session, "luna_group_validation_plan", STUDY, plan)
    presentation = engine._record_presentation(session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "luna_group_validation_plan", "id": identifier}],
        "markdown": render_preparation(plan), "destination": "codex_chat"})
    return {"id": identifier, **plan, "presentation": presentation}


def _link(metadata: Json, source: str) -> str:
    row = metadata[source]
    title = str(row.get("title") or source).replace("[", "(").replace("]", ")").replace("\n", " ")
    return f"[{title}]({row['url']})" if row.get("url") else title


def render_preparation(plan: Json) -> str:
    text = (f"Random singleton sample frozen: **100 of {plan['frame_size']:,}**, without replacement. "
            f"Each was scored against {plan['eligible_articles']-1:,} other pilot articles using saved vectors; top three retained, no temporal filter or similarity cutoff. "
            f"**{len(plan['tasks'])} distinct pairs**, {plan['prepared_requests']} prepared; "
            f"{len(plan['tasks'])-plan['prepared_requests']} unavailable. Zero new embeddings or model calls. Original groups unchanged.\n\n"
            "The 100-source sample and full scored retrieval are protected. Cosine is a candidate score, not identity probability. "
            "Long-gap links will be reported separately. This is model-screening preparation, not results about how many should join.\n\n"
            "Example frozen retrieval (first sampled singleton):\n\n")
    row = plan["rows"][0]
    text += _link(plan["source_metadata"], row["source"]) + "\n\n"
    for rank, candidate in enumerate(row["candidates"], 1):
        text += f"{rank}. {_link(plan['source_metadata'], candidate['source'])} — cosine {candidate['score']:.4f}; current group size {candidate['group_size']}.\n"
    return text


class SingletonGateway(Gateway):
    """Narrow extension of the shared gateway; writer owns all durable state."""

    def singleton_api_dispatch(self, session: str, plan_id: str, policy_id: str, invocations: list[Json]) -> Any:
        require_active(self.engine, session)
        policy = self.engine.ledger.get(policy_id, "policy")["content"]
        if self.engine.config.offline or policy.get("plan") != plan_id or policy.get("method") != METHOD + ":approval":
            raise ResearchError("singleton_gateway_requires_bound_online_approval")
        if not policy.get("allow_paid_inference") or not policy.get("allow_external_processing"):
            raise ResearchError("singleton_gateway_processing_not_authorized")
        if datetime.fromisoformat(policy["expires_at"]) <= datetime.now(timezone.utc):
            raise ResearchError("singleton_gateway_approval_expired")
        for call in invocations:
            intended = self.engine.ledger.unresolved.get(call["attempt"])
            if (not intended or intended["batch"] != plan_id or intended["approval_policy"] != policy_id
                    or self.engine.ledger.artifacts.read(intended["dispatch"]) != call["manifest"]
                    or call["manifest"]["endpoint"] != ENDPOINT
                    or self.engine.ledger.artifacts.read(intended["request"]) != call["request"]
                    or call["manifest"]["body"] != wire_body(call["request"])):
                raise AuditError("singleton_gateway_durable_intent_mismatch")
        transport = getattr(self.engine, "singleton_transport", None) or OpenAITagTransport()

        def send(call: Json) -> Json:
            try:
                result = transport.send(canonical(call["manifest"]["body"]).encode("utf-8"), call["attempt"])
                return {"raw_bytes": result.body, "http_status": result.status, "request_id": result.request_id, "ended_at": utc()}
            except Exception as failure:
                return {"unknown": True, "error_type": type(failure).__name__, "ended_at": utc()}

        with ThreadPoolExecutor(max_workers=min(4, len(invocations))) as pool:
            futures = {pool.submit(send, call): call for call in invocations}
            for future in as_completed(futures):
                yield futures[future], future.result()


def _outcome(engine: Any, session: str, plan_id: str, task: Json, call: Json, response: Json) -> Json:
    ledger = engine.ledger
    request = call["request"]
    unknown = response.get("unknown", False)
    status, answer, validation, error, parsed, response_ref = "unknown" if unknown else "invalid", None, {}, response.get("error_type"), {}, None
    if not unknown:
        raw = response.pop("raw_bytes")
        try:
            require_no_credentials(raw.decode("utf-8", errors="replace"))
            raw_ref = ledger.artifacts.put_bytes(raw)
            ledger.append(session, "singleton.api.raw_response.saved", {"artifact": raw_ref, "attempt": call["attempt"]})
            response_ref = save(engine, session, {**response, "raw_response": raw_ref}, "Observable OpenAI HTTP result before parsing or acceptance")
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                parsed = {}
                raise ResearchError("singleton_api_response_not_object")
            require_no_credentials(parsed)
            if response["http_status"] != 200:
                raise ResearchError("singleton_api_http_error")
            answer = parse_response(parsed)
            validation = validate_answer(request, answer)
            status = "valid"
        except AuditError:
            raise
        except Exception as failure:
            error = str(failure) if isinstance(failure, ResearchError) and str(failure).startswith(("singleton_", "event_pair_")) else type(failure).__name__
            answer = None
    value = {"pair": task["pair"], "attempt": call["attempt"], "request": task["request"], "response": response_ref,
             "status": status, "label": answer["label"] if answer is not None else None, "answer": answer, "validation": validation,
             "observed_model": parsed.get("model"), "response_id": parsed.get("id"), "request_id": response.get("request_id"),
             "usage": parsed.get("usage"), "http_status": response.get("http_status"), "error": error,
             "started_at": call["manifest"]["started_at"], "ended_at": response["ended_at"], "human_validated": False}
    assessment = ledger.record(session, "singleton_api_assessment", call["attempt"], value)

    def project(event: int) -> None:
        ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (call["attempt"], call["task_key"], plan_id, 1,
                          task["request"], response_ref, status, assessment, error, event))

    ledger.append(session, "model.attempt.unobserved" if unknown else "model.attempt.completed", {
        "attempt": call["attempt"], "status": status, "response": response_ref, "assessment": assessment, "ended_at": response["ended_at"]}, project)
    if not unknown:
        ledger.unresolved.pop(call["attempt"], None)
    return {**value, "assessment": assessment}


def execute(engine: Any, session: str, context: Context, data: Json) -> Json:
    ledger = engine.ledger
    plan_id = data["plan"]
    plan = ledger.get(plan_id, "luna_group_validation_plan")
    if plan.get("method") != METHOD or plan["implementation"] != implementation() or len(plan["rows"]) != 100 or len(plan["tasks"]) > 300:
        raise ResearchError("singleton_execution_frozen_plan_changed")
    expected = {task["pair"]: task for task in plan["tasks"]}
    if (len(expected) != len(plan["tasks"]) or len({row["source"] for row in plan["rows"]}) != 100
            or any(len(row["candidates"]) != 3 or len({c["source"] for c in row["candidates"]}) != 3
                   or any(c["source"] == row["source"] or c["pair"] != digest(sorted((row["source"], c["source"])))
                          or c["pair"] not in expected for c in row["candidates"]) for row in plan["rows"])
            or any(task["pair"] != digest(sorted((task["left"], task["right"]))) for task in plan["tasks"])):
        raise AuditError("singleton_frozen_sample_or_pair_mapping_changed")
    bound = Context(context.objective, context.actor, plan["versions"])
    previous = ledger.db.execute("SELECT id,payload FROM records WHERE kind='singleton_api_authorization' AND logical_key=?", (STUDY,)).fetchone()
    if previous:
        policy_id = json.loads(previous["payload"])["policy"]
    else:
        if data.get("authorize_user_request") != USER_INSTRUCTION:
            raise ResearchError("singleton_explicit_user_api_authorization_required")
        policy = {"method": METHOD + ":approval", "plan": plan_id, "approved_by": "user:current-chat",
                  "authorization_text": USER_INSTRUCTION, "observed_chat_timestamp": None,
                  "allow_paid_inference": True, "allow_external_processing": True, "max_requests": len(plan["tasks"]),
                  "max_article_exposures": 2 * len(plan["tasks"]), "max_retries": 0, "max_planning_reservation_usd": 2,
                  "expires_at": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()}
        policy_id = engine._version(session, bound, {"kind": "policy", "key": STUDY, "content": policy})["id"]
        ledger.record(session, "singleton_api_authorization", STUDY, {"plan": plan_id, "policy": policy_id})
    history = [json.loads(row[0]) for row in ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.singleton_study')=?", (STUDY,))]
    if len(history) > len(expected) or len({item["pair"] for item in history}) != len(history):
        raise AuditError("singleton_duplicate_or_overspent_history")
    outcomes: Json = {}
    stopped = False
    for intended in history:
        task = expected.get(intended["pair"])
        if not task or intended["request"] != task["request"] or intended["approval_policy"] != policy_id or intended["number"] != 1 or intended["batch"] != plan_id:
            raise AuditError("singleton_attempt_lineage_changed")
        prior = ledger.db.execute("SELECT status,result_id FROM attempts WHERE id=?", (intended["attempt"],)).fetchone()
        if not prior or not prior["result_id"]:
            outcomes[task["pair"]] = {"status": "unknown", "label": None, "attempt": intended["attempt"]}
            stopped = True
        else:
            outcome = ledger.get(prior["result_id"], "singleton_api_assessment")
            if outcome["status"] != prior["status"] or outcome["request"] != task["request"] or outcome["pair"] != task["pair"]:
                raise AuditError("singleton_assessment_binding_changed")
            if outcome["status"] == "valid":
                validate_answer(ledger.artifacts.read(task["request"]), outcome["answer"])
            else:
                stopped = True
            outcomes[task["pair"]] = {**outcome, "assessment": prior["result_id"]}
            ledger.append(session, "model.cache_reused", {"assessment": prior["result_id"], "request": task["request"], "basis": "Exact immutable singleton plan, no new dispatch"})
    if ledger.db.execute("SELECT 1 FROM records WHERE kind='singleton_api_stop' AND logical_key=?", (STUDY,)).fetchone():
        stopped = True
    ledger.record(session, "singleton_api_batch", str(uuid.uuid4()), {"plan": plan_id, "policy": policy_id, "tasks": plan["tasks"], "previous_attempts": len(history)})
    spent = len(history)
    reservation = sum(float(item["reserved_cost_usd"]) for item in history)
    start = time.perf_counter()
    remaining = [task for task in plan["tasks"] if task["pair"] not in outcomes]
    cursor = 0
    while cursor < len(remaining) and not stopped:
        width = 1 if spent < 4 else 4
        block = remaining[cursor:cursor + width]
        cursor += len(block)
        calls = []
        # Snapshot unresolved *earlier* attempts. Other calls being reserved in
        # this bounded block are in flight, not unknown historical outcomes.
        blocked_sources = {source for item in ledger.unresolved.values() for source in item.get("source_versions", [])}
        for task in block:
            if task["status"] != "prepared":
                outcomes[task["pair"]] = {"status": "unavailable", "label": None}
                continue
            request = ledger.artifacts.read(task["request"])
            validate_request(request)
            body = ledger.artifacts.read(task["body"])
            if body != wire_body(request) or request["versions"] != plan["versions"]:
                raise AuditError("singleton_frozen_wire_body_changed")
            blocked = bool(blocked_sources & {task["left"], task["right"]})
            if blocked:
                outcomes[task["pair"]] = {"status": "unavailable", "label": None, "reason": "unresolved_prior_source_attempt"}
                continue
            reserve = ((len(canonical(body).encode("utf-8")) + 4096) * .10 + OUTPUT_CAP * .50) / 1000000
            if reservation + reserve > 2 or spent >= 300:
                stopped = True
                break
            attempt = str(uuid.uuid4())
            manifest = {"transport": "openai-responses-event-pair-v1", "endpoint": ENDPOINT, "body": body,
                        "client_request_id": attempt, "started_at": utc(), "retries": 0}
            dispatch = save(engine, session, manifest, "Exact API dispatch excluding secret authentication headers")
            task_key = digest({"plan": plan_id, "policy": policy_id, "pair": task["pair"]})
            intent = {"attempt": attempt, "task_key": task_key, "number": 1, "batch": plan_id, "request": task["request"], "dispatch": dispatch,
                      "started_at": manifest["started_at"], "singleton_study": STUDY, "pair": task["pair"], "approval_policy": policy_id,
                      "source_versions": [task["left"], task["right"]], "article_exposures": 2, "reserved_cost_usd": reserve}
            ledger.append(session, "model.attempt.intended", intent)
            ledger.unresolved[attempt] = intent
            calls.append({"attempt": attempt, "task_key": task_key, "manifest": manifest, "request": request, "pair": task["pair"]})
            reservation += reserve
            spent += 1
        if not calls:
            continue
        for call, response in engine.gateway.singleton_api_dispatch(session, plan_id, policy_id, calls):
            outcome = _outcome(engine, session, plan_id, expected[call["pair"]], call, response)
            outcomes[call["pair"]] = outcome
            if outcome["status"] != "valid":
                stopped = True
                ledger.record(session, "singleton_api_stop", STUDY, {"plan": plan_id, "attempt": call["attempt"], "reason": "First invalid/unknown response; no retry or further dispatch"})
        print(f"Luna API progress: {len(outcomes)}/{len(plan['tasks'])} pairs retained; stop={stopped}", flush=True)
    classified = [{**row, "category": classify([outcomes.get(c["pair"], {}).get("label") for c in row["candidates"]])} for row in plan["rows"]]
    counts = {name: sum(row["category"] == name for row in classified) for name in ("supported_match", "uncertain", "unmatched_among_top3", "incomplete")}
    usages = [row["usage"] for row in outcomes.values() if isinstance(row.get("usage"), dict)]
    tokens = {key: sum(row.get(key, 0) for row in usages) for key in ("input_tokens", "output_tokens", "total_tokens")}
    # Uncached Standard rates: a transparent usage-based estimate, not an invoice.
    usage_cost = (tokens["input_tokens"] * .10 + tokens["output_tokens"] * .50) / 1000000
    result = {"method": METHOD, "versions": plan["versions"], "plan": plan_id, "study_key": STUDY, "rows": classified, "outcomes": outcomes,
              "counts": counts, "pair_statuses": dict(Counter(row["status"] for row in outcomes.values())),
              "pair_labels": dict(Counter(row["label"] for row in outcomes.values() if row["status"] == "valid")),
              "model_attempts": spent, "article_exposures": 2 * spent, "pending_pairs": len(plan["tasks"]) - len(outcomes),
              "usage": tokens, "responses_with_usage": len(usages), "standard_uncached_usage_cost_usd": usage_cost,
              "planning_reservation_usd": reservation, "automatic_retries": 0, "memberships_changed": False,
              "stopped": stopped, "human_validated": False, "elapsed_seconds": time.perf_counter() - start}
    return present(engine, session, bound, "luna_group_validation_result", result, render_results(result, plan))


def render_results(result: Json, plan: Json) -> str:
    counts = result["counts"]
    text = ("Luna API screening of **100 randomly sampled pilot singletons**:\n\n"
            "| Outcome | Articles |\n|---|---:|\n"
            f"| Supported same-event match: grouping proposal | {counts['supported_match']} |\n"
            f"| Uncertain, no supported match | {counts['uncertain']} |\n"
            f"| Unmatched among the three candidates | {counts['unmatched_among_top3']} |\n"
            f"| Incomplete / technical or source missingness | {counts['incomplete']} |\n\n"
            f"Scope: SRS without replacement from 15,537 original singletons, 19,548 other eligible pilot articles searched per anchor. "
            f"{result['model_attempts']} API attempts / {result['article_exposures']} article exposures / zero retries. "
            f"Pair statuses: {result['pair_statuses']}; pending {result['pending_pairs']}; labels {result['pair_labels']}.\n\n"
            f"Observed usage on {result['responses_with_usage']} responses: {result['usage']}. "
            f"Cost at uncached Standard rates: USD {result['standard_uncached_usage_cost_usd']:.6f}, not a verified invoice; "
            f"planning reservations USD {result['planning_reservation_usd']:.6f}.\n\n"
            "These are lead-only Luna references, not human validation or 90% precision. A positive pair proposes grouping; existing multiarticle groups still need whole-group consistency review. "
            "Longer-than-seven-day links require the separate review tier. Unmatched means no match among the top three, not proven unique or corpus recall. "
            "All original groups remain unchanged. No new embeddings.\n\nExamples from the saved judgments:\n")
    for category in ("supported_match", "uncertain", "unmatched_among_top3"):
        example = next((row for row in result["rows"] if row["category"] == category), None)
        if example is None:
            text += f"\n- {category}: none.\n"
            continue
        desired = "same_event" if category == "supported_match" else "uncertain" if category == "uncertain" else "different_event"
        candidate = next(c for c in example["candidates"] if result["outcomes"][c["pair"]]["label"] == desired)
        outcome = result["outcomes"][candidate["pair"]]
        text += f"\n- **{category}**: {_link(plan['source_metadata'], example['source'])} ↔ {_link(plan['source_metadata'], candidate['source'])}; cosine {candidate['score']:.4f}. "
        text += f"Luna reason: {outcome['answer']['reason']} Evidence span IDs: {outcome['answer']['support_span_ids']}.\n"
    return text


class SingletonResearch(Research):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gateway = SingletonGateway(self, self.gateway.provider)

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if data.get("phase") == "singleton_api_prepare":
            return prepare(self, session, context)
        if data.get("phase") == "singleton_api_execute":
            return execute(self, session, context, data)
        raise ResearchError("singleton_api_phase_invalid")
