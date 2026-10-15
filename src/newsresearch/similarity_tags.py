"""Exhaustive local cosine scoring and one immutable SQLite audit row per article/run."""
from __future__ import annotations

import base64
from collections import defaultdict
import hashlib
import json
import math
from typing import TYPE_CHECKING, Any
import uuid

import numpy as np

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, utc
from .embeddings import ENDPOINT, cost, offline_tokenizer, validate_response
from .retrieval import implementation, normalize_vector, opened, save
from .tagging import same_versions
from .tag_calibration import metrics

if TYPE_CHECKING:
    from .runtime import Research

METHOD: Json = {
    "method": "exhaustive-cosine-query-tags-v1",
    "query_input": "Query: {query}\nQuestion: {question}",
    "scoring": "Float32 dot product of L2-normalized query and every saved full-precision passage vector; clip to [-1,1]",
    "aggregation": "Maximum cosine across every article chunk; ties use lexicographically smallest chunk ID",
    "selection": "Every source in the bound dataset; no ANN, top-k or similarity filter",
    "answer": "Is this article semantically relevant? score >= calibrated threshold; not an answer to the substantive question",
    "missingness": "No vectors or incomplete coverage means unprocessed with null score/answer",
    "threshold_selection": "Default to recall priority (F2); record any explicit override and held-out precision/recall",
    "timestamps": "UTC local observations for planning, request start/response receipt, scoring, tag application and SQL recording; no provider execution clock is inferred",
    "scope": "Provisional article relevance, not probabilities, incident identity or accepted dossier findings",
}

# This projection runs against the existing immutable SQL records table. No working-store migration.
ROW_SQL = """SELECT r.id AS result_id,
 json_extract(r.payload,'$.run') AS run_id,
 json_extract(r.payload,'$.article_id') AS article_id,
 json_extract(r.payload,'$.source_version') AS source_version,
 json_extract(r.payload,'$.query') AS query,
 json_extract(r.payload,'$.question') AS question,
 json_extract(r.payload,'$.tag') AS tag,
 json_extract(r.payload,'$.score') AS score,
 json_extract(r.payload,'$.answer') AS answer,
 json_extract(r.payload,'$.status') AS status,
 json_extract(r.payload,'$.threshold') AS threshold,
 json_extract(r.payload,'$.calibration') AS calibration_id,
 json_extract(r.payload,'$.evidence') AS evidence_json,
 json_extract(r.payload,'$.chunks_scored') AS chunks_scored,
 json_extract(r.payload,'$.query_embedding_result') AS query_embedding_result,
 json_extract(r.payload,'$.embedding_model') AS embedding_model,
 json_extract(r.payload,'$.dimensions') AS dimensions,
 json_extract(r.payload,'$.query_request_id') AS query_request_id,
 json_extract(r.payload,'$.query_attempt') AS query_attempt_id,
 json_extract(r.payload,'$.query_planned_at') AS query_planned_at,
 json_extract(r.payload,'$.query_request_started_at') AS query_request_started_at,
 json_extract(r.payload,'$.query_response_received_at') AS query_response_received_at,
 json_extract(r.payload,'$.score_run_started_at') AS score_run_started_at,
 json_extract(r.payload,'$.score_run_completed_at') AS score_run_completed_at,
 json_extract(r.payload,'$.tag_application_started_at') AS tag_application_started_at,
 json_extract(r.payload,'$.tag_applied_at') AS tag_applied_at,
 json_extract(r.payload,'$.query_usage') AS query_usage_json,
 json_extract(r.payload,'$.query_usage_scope') AS query_usage_scope,
 json_extract(r.payload,'$.model_calls') AS article_model_calls,
 json_extract(r.payload,'$.index') AS index_id,
 json_extract(r.payload,'$.method') AS method,
 json_extract(r.payload,'$.versions') AS versions_json,
 json_extract(r.payload,'$.implementation_digest') AS implementation_digest,
 json_extract(r.payload,'$.actor') AS actor,
 json_extract(r.payload,'$.session') AS session_id,
 json_extract(r.payload,'$.started_at') AS started_at,
 json_extract(r.payload,'$.completed_at') AS completed_at,
 json_extract(r.payload,'$.error_type') AS error_type,
 json_extract(r.payload,'$.parent_result') AS parent_result,
 r.created_event AS audit_event, e.event_hash AS audit_hash, e.time AS recorded_at,
 s.payload AS session_audit_json
 FROM records r JOIN events e ON e.seq=r.created_event
 JOIN events s ON s.session_id=e.session_id AND s.kind='session.started'
 WHERE r.kind='article_query_result' AND json_extract(r.payload,'$.run')=?
 ORDER BY article_id,source_version"""


def setup(engine: Research, session: str, context: Context, data: Json) -> Json:
    """Register the default method and plan ONE query embedding through the shared gateway."""
    require_active(engine, session)
    index = engine.ledger.get(data["index"], "vector_index")
    if context.versions.get("dataset") != index["versions"]["dataset"]:
        raise ResearchError("Similarity query and index must share the exact dataset")
    for key in ("query", "question", "tag"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ResearchError("A query, specific question and tag are required")
    versions = {"dataset": index["versions"]["dataset"], "embedding_profile": index["versions"]["embedding_profile"]}
    specifications = {
        "protocol": {"method": METHOD["method"], "contract": METHOD},
        "question": {"query": data["query"], "text": data["question"]},
        "selection": {"rules": METHOD["selection"], "dataset": versions["dataset"]},
        "profile": {"mode": "exploratory", "population_estimate": False},
        "codebook": {"labels": ["yes", "no"], "tag": data["tag"], "definition": METHOD["answer"]},
        "retrieval_profile": METHOD,
    }
    if "evaluation" in data:
        evaluation = dict(data["evaluation"])
        evaluation.setdefault("priority", "recall")
        specifications["evaluation"] = evaluation
    for kind, value in specifications.items():
        versions[kind] = engine._version(session, context, {"kind": kind,
            "key": "similarity-" + data["tag"] + "-" + kind, "content": value,
            "amend_latest": True, "reason": "Use saved embeddings and local exhaustive scoring as the default tagging method"})["id"]
    return engine.gateway.plan_query_embedding(session, Context(context.objective, context.actor, versions), {"index": data["index"]})


def plan_query(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"dataset", "question", "protocol", "selection", "profile", "codebook", "retrieval_profile", "embedding_profile"})
    ledger = engine.ledger
    index = ledger.get(data["index"], "vector_index")
    if any(context.versions[k] != index["versions"][k] for k in ("dataset", "embedding_profile")):
        raise ResearchError("Query model and dataset must match the saved article embeddings")
    if ledger.get(context.versions["retrieval_profile"], "retrieval_profile")["content"] != METHOD:
        raise ResearchError("Register the exact exhaustive cosine method")
    question = ledger.get(context.versions["question"], "question")["content"]
    query_text = f"Query: {question['query']}\nQuestion: {question['text']}"
    profile = ledger.get(index["plan"], "embedding_plan")["profile"]
    tokens = len(offline_tokenizer().encode_ordinary(query_text))
    if not 1 <= tokens <= profile["max_tokens_per_input"]:
        raise ResearchError("Query embedding input exceeds the registered model limit")
    body = {"model": profile["model"], "dimensions": profile["dimensions"], "encoding_format": "base64", "input": [query_text]}
    wire = ledger.artifacts.put_bytes(canonical(body).encode())
    chunk = {"id": digest({"text": query_text, "question": context.versions["question"]}),
             "method": "query-and-question-v1", "text_hash": hashlib.sha256(query_text.encode()).hexdigest()}
    code = implementation(engine)
    request = {"gateway_contract": "embedding-v1", "task_kind": "query_embedding", "endpoint": ENDPOINT,
               "instructions": [], "provider": "openai", "model": profile["model"],
               "versions": context.versions, "implementation_digest": code, "profile": profile,
               "body": body, "wire_body_ref": wire, "chunks": [chunk], "input_tokens": tokens,
               "index": data["index"], "index_versions": index["versions"]}
    reference = ledger.artifacts.put(request)
    ledger.append(session, "embedding.request.prepared", {"request": reference, "wire_body": wire})
    context_ref = save(engine, session, {"versions": context.versions})
    result = {"purpose": "query_embedding", "items": [{"task_key": digest(request), "request_ref": reference,
               "chunks": 1, "input_tokens": tokens}], "profile": profile, "versions": context.versions,
              "index": data["index"], "index_versions": index["versions"], "query_text": query_text,
              "implementation_digest": code, "expected_chunks": 1, "input_tokens": tokens,
              "expected_articles": index["source_records"], "context_artifact": context_ref,
              "estimated_cost_usd": str(cost(tokens, profile["usd_per_million_input_tokens"])),
              "price_basis": "Saved embedding profile and its recorded price-check date; verify before paid execution",
              "network_calls": 0, "model_calls": 0}
    identifier = ledger.record(session, "embedding_plan", digest(result), result)
    return {"id": identifier, **{k: v for k, v in result.items() if k != "items"}}


def query_vector(engine: Research, context: Context, plan_id: str, run_id: str) -> tuple[Json, Json, Any]:
    ledger = engine.ledger
    plan = ledger.get(plan_id, "embedding_plan")
    run = ledger.get(run_id, "embedding_run")
    same_versions(plan, context)
    same_versions(run, context)
    if (plan.get("purpose") != "query_embedding" or run["plan"] != plan_id or run["missing_task_keys"]
            or run["completed_chunks"] != 1 or len(run["items"]) != 1):
        raise ResearchError("A complete audited query embedding is required")
    item = run["items"][0]
    planned = plan["items"][0]
    if any(item[k] != v for k, v in planned.items()) or item["status"] not in {"valid", "cached"}:
        raise ResearchError("Query run does not reconcile to its plan")
    result = ledger.get(item["result"], "embedding_result")
    request = ledger.artifacts.read(planned["request_ref"])
    if (digest(request) != planned["task_key"] or result["task_key"] != planned["task_key"]
            or result["plan"] != plan_id or result["versions"] != context.versions
            or result["request_ref"] != planned["request_ref"] or request["index"] != plan["index"]):
        raise AuditError("Query embedding provenance mismatch")
    if not ledger.db.execute("SELECT 1 FROM attempts WHERE id=? AND result_id=? AND status='valid'",
                             (result["attempt"], item["result"])).fetchone():
        raise AuditError("Query embedding lacks a durable successful attempt")
    if any(v["task_key"] == planned["task_key"] for v in ledger.unresolved.values()):
        raise ResearchError("Query embedding attempt has an unresolved outcome")
    parsed = ledger.artifacts.read(result["raw_response_ref"])
    validate_response(request, parsed)
    values = np.frombuffer(base64.b64decode(parsed["data"][0]["embedding"], validate=True), dtype="<f4")
    return plan, {"id": item["result"], **result}, normalize_vector(values)


def score(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"plan", "embedding_run", "reuse_cache"}:
        raise ResearchError("Similarity scoring does not accept corpus filters or per-article inference")
    ledger = engine.ledger
    plan, query_result, vector = query_vector(engine, context, data["plan"], data["embedding_run"])
    question = ledger.get(context.versions["question"], "question")["content"]
    tag = ledger.get(context.versions["codebook"], "codebook")["content"]["tag"]
    code = implementation(engine)
    identity = {"plan": data["plan"], "embedding_run": data["embedding_run"], "versions": context.versions,
                "implementation_digest": code, "index": plan["index"], "method": METHOD["method"]}
    index = ledger.get(plan["index"], "vector_index")
    frame = ledger.get(context.versions["dataset"], "dataset")["source_versions"]
    manifest = {**identity, "source_ids": frame, "expected_articles": len(frame), "phase": "scores"}
    run_id = ledger.record(session, "article_query_manifest", digest(manifest), manifest)
    existing = ledger.db.execute("SELECT 1 FROM records WHERE kind='article_query_result' AND json_extract(payload,'$.run')=? LIMIT 1", (run_id,)).fetchone()
    if existing and data.get("reuse_cache") is not True:
        raise ResearchError("Existing article results require explicit reuse_cache")
    started = utc()
    query_response = ledger.artifacts.read(query_result["response_ref"])
    query_planned_at = ledger.db.execute(
        "SELECT e.time FROM records r JOIN events e ON e.seq=r.created_event WHERE r.id=?",
        (data["plan"],),
    ).fetchone()[0]
    best: dict[str, tuple[float, Json]] = {}
    counts: dict[str, int] = defaultdict(int)
    # Use original index bindings for reading its immutable vectors, retaining both contexts in the audit.
    original_context = Context(context.objective, context.actor, index["versions"])
    with opened(engine, original_context, plan["index"]) as (_, _, _, rows, matrix):
        if matrix.shape[1] != len(vector):
            raise ResearchError("Query and article embedding dimensions differ")
        allowed = set(frame)
        for start in range(0, len(rows), 4096):
            scores = np.clip(np.asarray(matrix[start:start + 4096]) @ vector, -1.0, 1.0)
            if not np.isfinite(scores).all():
                raise AuditError("Nonfinite similarity scores")
            for row, value in zip(rows[start:start + 4096], scores, strict=True):
                source, value = row["source_version"], float(value)
                if source not in allowed:
                    raise AuditError("Index includes an out-of-dataset source")
                counts[source] += 1
                previous = best.get(source)
                if previous is None or value > previous[0] or (value == previous[0] and row["id"] < previous[1]["id"]):
                    best[source] = (value, row)
    score_run_completed_at = utc()
    ids = []
    for source in frame:
        key = digest({"run": run_id, "source": source})
        cached = ledger.db.execute("SELECT id FROM records WHERE kind='article_query_result' AND logical_key=?", (key,)).fetchone()
        if cached:
            ledger.append(session, "similarity.result.reused", {"result": cached[0], "run": run_id})
            ids.append(cached[0])
            continue
        raw = json.loads(ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()[0])
        evidence = None
        value = None
        if source in best:
            value, chunk = best[source]
            passage = engine._evidence(chunk["passage_id"])
            begin, end = chunk["source_start"] - passage["start"], chunk["source_end"] - passage["start"]
            quote = passage["text"][begin:end]
            if (passage["source_id"] != source or not 0 <= begin < end <= len(passage["text"])
                    or hashlib.sha256(quote.encode()).hexdigest() != chunk["text_hash"]):
                raise AuditError("Winning passage reference does not match source evidence")
            evidence = {"chunk": chunk, "quote": quote, "role": "Maximum similarity evidence, not entailment proof"}
        record = {**identity, "run": run_id, "phase": "scores", "article_id": raw["source_key"],
                  "source_version": source, "query": question["query"], "question": question["text"], "tag": tag,
                  "query_text": plan["query_text"], "score": value, "answer": None,
                  "answer_semantics": "Binary semantic relevance to this query; substantive question unanswered",
                  "status": "scored_awaiting_threshold" if value is not None else "unprocessed_no_vector",
                  "threshold": None, "calibration": None, "evidence": evidence, "chunks_scored": counts[source],
                  "query_embedding_result": query_result["id"], "query_attempt": query_result["attempt"],
                  "query_response_ref": query_result["response_ref"], "embedding_model": plan["profile"]["model"],
                  "dimensions": plan["profile"]["dimensions"], "index_versions": index["versions"],
                  "query_request_ref": query_result["request_ref"], "source_retention": raw["retention"],
                  "query_request_id": query_response.get("request_id"), "query_usage": query_response.get("usage"),
                  "query_usage_scope": "Shared query embedding request; do not sum usage across article rows",
                  "query_http_status": query_response.get("http_status"),
                  "query_planned_at": query_planned_at,
                  "query_request_started_at": query_response.get("started_at"),
                  "query_response_received_at": query_response.get("ended_at"),
                  "score_run_started_at": started, "score_run_completed_at": score_run_completed_at,
                  "tag_application_started_at": None, "tag_applied_at": None,
                  "actor": context.actor, "session": session, "started_at": started, "completed_at": utc(),
                  "error_type": None, "parent_result": None, "network_calls": 0, "model_calls": 0,
                  "review_status": "provisional", "scope": METHOD["scope"]}
        ids.append(ledger.record(session, "article_query_result", key, record))
    result = {**manifest, "run": run_id, "result_ids": ids, "scored_articles": len(best),
              "missing_articles": len(frame) - len(best), "chunks_scored": sum(counts.values()),
              "network_calls": 0, "model_calls": 0}
    completion = ledger.record(session, "article_query_run", digest(result), result)
    return {"id": completion, **{k: v for k, v in result.items() if k not in {"result_ids", "source_ids"}}}


def calibrate(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    engine._require(context, {"evaluation"})
    ledger = engine.ledger
    run = ledger.get(data["scores"], "article_query_run")
    same_versions(run, context)
    if run["phase"] != "scores":
        raise ResearchError("Calibrate from the original score run")
    evaluation = ledger.get(context.versions["evaluation"], "evaluation")["content"]
    if evaluation.get("method") != "query-tag-calibration-v1":
        raise ResearchError("Register separate human calibration and held-out test labels")
    events = [ledger.db.execute("SELECT created_event FROM records WHERE id=?", (ref,)).fetchone()[0]
              for ref in (context.versions["evaluation"], run["plan"])]
    if events[0] >= events[1]:
        raise ResearchError("Evaluation must be registered before the query embedding plan")
    beta = {"balanced": 1.0, "recall": 2.0, "precision": 0.5}.get(evaluation.get("priority"))
    minimum = evaluation.get("minimum_per_class_per_split")
    required = [evaluation.get("minimum_test_precision"), evaluation.get("minimum_test_recall")]
    if (beta is None or type(minimum) is not int or minimum < 1
            or any(type(v) not in {int, float} or not math.isfinite(v) or not 0 < v <= 1 for v in required)):
        raise ResearchError("Register priority, class minimums and held-out precision/recall requirements")
    scored = {row["source_version"]: row for row in
              (ledger.get(ref, "article_query_result") for ref in run["result_ids"])}
    groups: dict[str, str] = {}
    seen: set[str] = set()
    splits: dict[str, list[Json]] = {"calibration": [], "test": []}
    for item in evaluation.get("items", []):
        source, split, group = item.get("source_version"), item.get("split"), item.get("group")
        if (source not in scored or source in seen or split not in splits or not isinstance(group, str)
                or not group.strip() or type(item.get("relevant")) is not bool
                or item.get("reviewer_type") != "human" or not item.get("reviewer") or not item.get("reason")):
            raise ResearchError("Invalid independently reviewed evaluation item")
        if group in groups and groups[group] != split:
            raise ResearchError("Related reporting group leaks across evaluation splits")
        groups[group] = split
        seen.add(source)
        if scored[source]["score"] is None:
            raise ResearchError("Evaluation source is unprocessed; missing is not negative")
        splits[split].append({**item, "score": scored[source]["score"]})
    for items in splits.values():
        if any(sum(i["relevant"] == label for i in items) < minimum for label in (True, False)):
            raise ResearchError("Each split requires the registered minimum of both classes")
    # Cosine scores may be negative: unlike LLM scores, zero is not a meaningful boundary.
    thresholds = sorted({-1.0, 1.0, *(i["score"] for i in splits["calibration"])})
    curve = [metrics(splits["calibration"], value, beta) for value in thresholds]
    selected = max(curve, key=lambda m: (m["f_beta"], m["recall"], m["precision"], m["threshold"]))
    held_out = metrics(splits["test"], selected["threshold"], beta)
    result = {"scores": data["scores"], "score_run": run["run"], "plan": run["plan"], "versions": context.versions,
              "threshold": selected["threshold"], "comparison": "score >= threshold",
              "calibration": selected, "test": held_out, "curve": curve, "splits": splits,
              "passed": held_out["precision"] >= required[0] and held_out["recall"] >= required[1],
              "method": "calibration F-beta; independent held-out check; negative cosine cutoffs allowed",
              "scope": "Article relevance diagnostic; independent labels/grouping and representativeness self-asserted"}
    identifier = ledger.record(session, "similarity_calibration", digest(result), result)
    return {"id": identifier, **{k: v for k, v in result.items() if k not in {"curve", "splits"}}}


def apply(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    ledger = engine.ledger
    scored = ledger.get(data["scores"], "article_query_run")
    calibration = ledger.get(data["calibration"], "similarity_calibration")
    same_versions(scored, context)
    same_versions(calibration, context)
    if scored["phase"] != "scores" or calibration["score_run"] != scored["run"] or not calibration["passed"]:
        raise ResearchError("Apply only a passing calibration bound to this exact score run")
    code = implementation(engine)
    manifest = {"scores": data["scores"], "calibration": data["calibration"], "versions": context.versions,
                "expected_articles": scored["expected_articles"], "source_ids": scored["source_ids"],
                "implementation_digest": code, "phase": "tags"}
    run_id = ledger.record(session, "article_query_manifest", digest(manifest), manifest)
    ids = []
    started = utc()
    for parent in scored["result_ids"]:
        original = ledger.get(parent, "article_query_result")
        key = digest({"run": run_id, "source": original["source_version"]})
        cached = ledger.db.execute("SELECT id FROM records WHERE kind='article_query_result' AND logical_key=?", (key,)).fetchone()
        if cached:
            if data.get("reuse_cache") is not True:
                raise ResearchError("Existing tag results require explicit reuse_cache")
            ledger.append(session, "similarity.result.reused", {"result": cached[0], "run": run_id})
            ids.append(cached[0])
            continue
        value = original["score"]
        result = {**original, "run": run_id, "phase": "tags", "parent_result": parent,
                  "answer": ("yes" if value >= calibration["threshold"] else "no") if value is not None else None,
                  "threshold": calibration["threshold"], "calibration": data["calibration"],
                  "comparison": "score >= threshold", "status": "classified" if value is not None else original["status"],
                  "actor": context.actor, "session": session, "started_at": started, "completed_at": utc(),
                  "tag_application_started_at": started, "tag_applied_at": utc(),
                  "implementation_digest": code, "review_status": "provisional"}
        ids.append(ledger.record(session, "article_query_result", key, result))
    result = {**manifest, "run": run_id, "result_ids": ids, "classified_articles": scored["scored_articles"],
              "missing_articles": scored["missing_articles"], "network_calls": 0, "model_calls": 0}
    identifier = ledger.record(session, "article_query_run", digest(result), result)
    return {"id": identifier, **{k: v for k, v in result.items() if k not in {"result_ids", "source_ids"}}}


def read_rows(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    run = engine.ledger.get(data["run"], "article_query_manifest")
    same_versions(run, context)
    limit = data.get("limit", 100)
    offset = data.get("offset", 0)
    if type(limit) is not int or not 1 <= limit <= 20000 or type(offset) is not int or offset < 0:
        raise ResearchError("Invalid article audit pagination")
    sql = ROW_SQL + " LIMIT ? OFFSET ?"
    parameters = [data["run"], limit, offset]
    rows = [dict(row) for row in engine.ledger.db.execute(sql, parameters)]
    completed = engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='article_query_result' AND json_extract(payload,'$.run')=?", (data["run"],)).fetchone()[0]
    result = {"run": data["run"], "versions": context.versions, "sql": sql, "parameters": parameters,
              "rows": rows, "expected_articles": run["expected_articles"], "offset": offset,
              "logged_articles": completed, "pending_articles": run["expected_articles"] - completed,
              "scope": "Audited SQL inspection; incomplete runs retain their expected denominator"}
    engine.ledger.record(session, "article_query_inspection", str(uuid.uuid4()), result)
    return result
