"""Audited local article retrieval using retained vectors, without model calls."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from .common import AuditError, Context, Json, ResearchError, digest
from .event_extraction_inputs import RETAINED_CANDIDATE, load_frame
from .event_extraction_workflow import METHOD as EXTRACTION_METHOD, _link, _owner, present, save
from .runtime import Research, audited_handler

METHOD = "saved-article-rag-retrieval-v1"
STUDY = "saved-article-rag-retrieval-20261017-v1"
PLAN = "c532c7ce77af1ad916f17aaa15055132d16fb52ae635488d0c4f300bb1a68bce"


def implementation() -> Json:
    names = ("event_rag_retrieval.py", "event_extraction_inputs.py", "event_extraction_workflow.py",
             "singleton_luna_api.py", "event_precision_candidate.py", "event_eval_workflow.py",
             "runtime.py", "storage.py", "common.py", "presentation.py")
    return {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in names} | {"uv.lock": hashlib.sha256(
                Path(__file__).resolve().parents[2].joinpath("uv.lock").read_bytes()).hexdigest()}


def rank_saved_vectors(ids: list[str], vectors: Any, anchors: list[str],
                       eligible: list[str], top_k: int = 3) -> Json:
    """Exact cosine; restrict targets before ranking and retain missing coverage."""
    if (type(top_k) is not int or not 1 <= top_k <= 20
            or any(len(values) != len(set(values)) for values in (ids, anchors, eligible))
            or any(not isinstance(s, str) or not s for s in ids + anchors + eligible)
            or not set(anchors) <= set(eligible)):
        raise ResearchError("rag_retrieval_invalid_frame")
    values = np.asarray(vectors)
    if (values.dtype.kind not in "fi" or values.ndim != 2 or values.shape[0] != len(ids)
            or values.shape[1] == 0 or not np.isfinite(values).all()):
        raise ResearchError("rag_retrieval_invalid_vectors")
    matrix = values.astype(np.float32, copy=True)
    norms = np.linalg.norm(matrix, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise ResearchError("rag_retrieval_zero_or_invalid_vector")
    matrix /= norms[:, None]
    positions = {source: n for n, source in enumerate(ids)}
    columns = sorted(set(eligible) & set(ids))
    query_ids = [source for source in anchors if source in positions]
    scores = matrix[[positions[s] for s in query_ids]] @ matrix[[positions[s] for s in columns]].T
    rows = []
    score_positions = {source: n for n, source in enumerate(query_ids)}
    for source in anchors:
        candidates = []
        if source in score_positions:
            values_row = scores[score_positions[source]]
            order = sorted((n for n, candidate in enumerate(columns) if candidate != source),
                           key=lambda n: (-float(values_row[n]), columns[n]))[:top_k]
            candidates = [{"source_version": columns[n], "score": float(values_row[n]), "rank": rank}
                          for rank, n in enumerate(order, 1)]
        rows.append({"source_version": source, "candidates": candidates,
                     "status": "vector_unavailable" if source not in positions else
                     "complete" if len(candidates) == top_k else "short_candidates"})
    count = sum(len(row["candidates"]) for row in rows)
    return {"rows": rows, "missing_vector_sources": sorted(set(eligible) - set(ids)),
            "eligible_vector_sources": columns, "scored_pairs": len(query_ids) * max(0, len(columns) - 1),
            "candidate_slots": count, "pending_slots": len(anchors) * top_k - count,
            "score_row_ids": query_ids, "score_column_ids": columns, "scores": scores}


def _vectors(engine: Any, session: str, capsule: Json, dataset: str) -> tuple[Json, list[str], Any]:
    """Retain one immutable local copy so later queries need no parent reads."""
    ledger = engine.ledger
    key = digest({"method": METHOD, "dataset": dataset, "capsule": digest(capsule)})
    rows = ledger.db.execute("SELECT id FROM records WHERE kind='event_rag_vector_snapshot' AND logical_key=?", (key,)).fetchall()
    if len(rows) > 1:
        raise AuditError("rag_retrieval_duplicate_vector_snapshot")
    if rows:
        snapshot = ledger.get(rows[0][0], "event_rag_vector_snapshot")
        mapping = ledger.artifacts.read(snapshot["mapping"])
        raw = (ledger.artifacts.root / snapshot["vectors"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != snapshot["vectors"]:
            raise AuditError("rag_retrieval_vector_snapshot_changed")
        ledger.append(session, "analysis.cache_reused", {"vector_snapshot": rows[0][0], "external_parent_reads": 0})
    else:
        from .singleton_luna_api import _external_inputs

        provenance, mapping, raw = _external_inputs(engine, session, capsule)
        if provenance["versions"]["dataset"] != dataset:
            raise AuditError("rag_retrieval_vector_dataset_changed")
        mapping_ref = save(engine, session, mapping, "Exact original saved vector-to-source mapping")
        vector_ref = ledger.artifacts.put_bytes(raw)
        ledger.append(session, "retrieval.artifact.saved", {"artifact": vector_ref, "purpose": "Original retained float32 pooled vectors; no new embeddings"})
        snapshot = {"mapping": mapping_ref, "vectors": vector_ref, "provenance": provenance,
                    "dataset": dataset, "new_embeddings": 0, "parent_archive_reverified": False}
        ledger.record(session, "event_rag_vector_snapshot", key, snapshot)
    ids = [row["source_version"] for row in mapping]
    if not ids or len(raw) % (4 * len(ids)):
        raise AuditError("rag_retrieval_vector_mapping_shape_invalid")
    return snapshot, ids, np.frombuffer(raw, dtype="<f4").reshape(len(ids), -1)


def _saved_text(engine: Any, session: str, sources: list[str], metadata: Json) -> Json:
    ledger = engine.ledger
    source_sql = "SELECT payload FROM sources WHERE id=?"
    passage_sql = "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start,id"
    ledger.append(session, "retrieval.source.inspection.intended", {"source_versions": sources,
        "source_sql": source_sql, "passage_sql": passage_sql,
        "scope": "Complete retained text and stable paragraph references for selected retrieval endpoints"})
    packets = []
    missing = []
    for source_id in sources:
        source_row = ledger.db.execute(source_sql, (source_id,)).fetchone()
        if source_row is None:
            raise AuditError("rag_retrieval_frozen_source_missing")
        source = json.loads(source_row[0])
        body = source.get("body")
        if source.get("retention") != "permitted" or not isinstance(body, str) or not body.strip():
            missing.append(source_id)
            continue
        if hashlib.sha256(body.encode("utf-8")).hexdigest() != metadata[source_id]["body_sha256"]:
            raise AuditError("rag_retrieval_source_hash_changed")
        paragraphs = [dict(row) for row in ledger.db.execute(passage_sql, (source_id,))]
        packets.append({"source_version": source_id, "body": body, "body_sha256": metadata[source_id]["body_sha256"],
                        "paragraphs": paragraphs, "metadata": {k: metadata[source_id].get(k) for k in ("title", "url", "published_at")}})
    artifact = save(engine, session, {"sources": packets, "missing_sources": missing},
                    "Retrieved saved full text for later extraction; source evidence only, no model interpretations")
    ledger.append(session, "retrieval.source.inspected", {"artifact": artifact,
        "source_versions": [row["source_version"] for row in packets],
        "passage_ids": [p["id"] for row in packets for p in row["paragraphs"]], "missing_sources": missing})
    return {"artifact": artifact, "path": str(ledger.artifacts.root / artifact),
            "requested": len(sources), "available": len(packets), "missing": missing,
            "passages": sum(len(row["paragraphs"]) for row in packets)}


def render(value: Json) -> str:
    text = (f"Saved-vector retrieval: **{len(value['rows'])} article queries**, top {value['top_k']} each, "
            f"against **{len(value['eligible_vector_sources']):,} development articles**. "
            f"{value['scored_pairs']:,} nonself cosine scores; **{value['candidate_slots']} ranked candidates** "
            f"({value['distinct_candidates']} distinct target articles).\n\n"
            f"Excluded from the original {value['original_frame_count']:,}-article frame: "
            f"{value['exclusion_counts']}. Missing vectors: {len(value['missing_vector_sources'])}; "
            f"pending candidate slots: {value['pending_slots']}; failed queries: 0. "
            f"Saved full text: {value['text']['available']}/{value['text']['requested']} distinct query/candidate articles, "
            f"{value['text']['passages']} passages; missing text: {len(value['text']['missing'])}.\n\n"
            f"Local normalization, scoring and ranking: {value['ranking_seconds']:.3f} seconds; "
            "excludes storage preflight, vector loading and durable audit. "
            "**Zero new embeddings, LLM calls or network calls.** No date filter or score cutoff; "
            "cosine is similarity, not event identity probability. No relevance yes/no tags or memberships were assigned. "
            "Extraction and event grouping remain unprocessed.\n\n")
    for n, row in enumerate(value["rows"], 1):
        text += f"**Query {n}: {_link(value['metadata'][row['source_version']])}**\n\n"
        for candidate in row["candidates"]:
            text += f"{candidate['rank']}. {_link(value['metadata'][candidate['source_version']])} — cosine **{candidate['score']:.4f}**.\n"
        if not row["candidates"]:
            text += f"No candidates returned; status: {row['status']}.\n"
        text += "\n"
    return text.rstrip()


class EventRagResearch(Research):
    @audited_handler
    def _vector_search(self, session: str, context: Context, data: Json) -> Json:
        if (context.versions or set(data) != {"plan", "study_key", "top_k"}
                or not isinstance(data["study_key"], str) or not data["study_key"].strip()
                or type(data["top_k"]) is not int or not 1 <= data["top_k"] <= 20):
            raise ResearchError("rag_retrieval_input_invalid")
        ledger = self.ledger
        binding = {**data, "implementation": implementation()}
        previous = ledger.db.execute("SELECT id FROM records WHERE kind='candidate_run' AND logical_key=?", (data["study_key"],)).fetchall()
        if previous:
            if len(previous) != 1:
                raise AuditError("rag_retrieval_duplicate_run")
            value = ledger.get(previous[0][0], "candidate_run")
            if value.get("method") != METHOD or value.get("binding") != binding:
                raise ResearchError("rag_retrieval_frozen_binding_changed")
            ledger.append(session, "analysis.cache_reused", {"result": previous[0][0], "new_computation": False})
            presentation = self._record_presentation(session, Context(context.objective, context.actor, value["versions"]), {
                "results": [{"kind": "candidate_run", "id": previous[0][0]}], "markdown": render(value), "destination": "codex_chat"})
            return {"id": previous[0][0], **value, "presentation": presentation}
        protocol = self._version(session, context, {"kind": "protocol", "key": data["study_key"], "content": {
            "method": METHOD, "binding": binding, "retrieval": "Exact normalized saved pooled article cosine; filter frozen development frame before scoring, exclude self, source-ID ties; no date/score cutoff",
            "inputs": "Frozen extraction plan seeds/exclusions and content-anchored original vectors; retain local vector snapshot. Bounded parent artifact verification, not parent archive-wide preflight",
            "text": "Retrieve complete saved text and stable passages for distinct returned endpoints, no truncation or model interpretation",
            "models": "No model, embedding, collection, adoption or relevance labeling", "user_instruction": "i want to use the rag for quick and cheap retrieval. go"}})["id"]
        plan = ledger.get(data["plan"], "luna_group_validation_plan")
        if plan.get("method") != EXTRACTION_METHOD or Path(plan["owner_workspace"]).resolve() != ledger.root.resolve():
            raise ResearchError("rag_retrieval_extraction_plan_owner_invalid")
        original = ledger.get(plan["original_plan"], "luna_group_validation_plan")
        _owner(self, original)
        versions = {k: v for k, v in plan["versions"].items() if k not in {"model_profile", "prompt", "codebook"}}
        versions["protocol"] = protocol
        contents = {"question": {"text": "Which saved development articles are nearest to the 12 frozen extraction-pilot articles?"},
                    "selection": {"rules": "Use exact frozen seed IDs and exclusions; no redraw, validation-body targets, label-based selection or replacement", "input_plan": data["plan"]},
                    "retrieval_profile": {"method": METHOD, "top_k": data["top_k"], "threshold": None},
                    "profile": {"mode": "exploratory", "population_estimate": False, "human_validated": False}}
        for kind, content in contents.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": data["study_key"], "content": content})["id"]
        bound = Context(context.objective, context.actor, versions)
        selection = ledger.artifacts.read(plan["selection_artifact"])
        anchors = [task["source_version"] for task in plan["tasks"]]
        if not 1 <= len(anchors) <= 12 or anchors != [row["source_version"] for row in selection["selected"]]:
            raise AuditError("rag_retrieval_frozen_seeds_changed")
        eligible = sorted(set(original["membership"]) - set(selection["exclusions"]))
        if len(eligible) != selection["eligible_development_sources"] or not set(anchors) <= set(eligible):
            raise AuditError("rag_retrieval_frozen_frame_changed")
        inputs = load_frame(self, session, original)
        folds = {row["body_sha256"]: row["fold"] for row in inputs["frame"]["representatives"]}
        if any(folds[inputs["metadata"][s]["body_sha256"]] != "development" for s in eligible):
            raise AuditError("rag_retrieval_sealed_body_target")
        manifest = ledger.record(session, "event_rag_retrieval_manifest", digest(binding), {
            "binding": binding, "versions": versions, "anchors": anchors, "eligible": eligible,
            "selection_artifact": plan["selection_artifact"], "exclusions": selection["exclusions"]})
        candidate = ledger.get(RETAINED_CANDIDATE, "event_group_refinement_result")
        capsule = ledger.artifacts.read(candidate["capsule"])
        snapshot, ids, matrix = _vectors(self, session, capsule, versions["dataset"])
        started = time.perf_counter()
        ranked = rank_saved_vectors(ids, matrix, anchors, eligible, data["top_k"])
        ranking_seconds = time.perf_counter() - started
        scores = ranked.pop("scores")
        score_ref = ledger.artifacts.put_bytes(scores.astype("<f4").tobytes())
        ledger.append(session, "retrieval.artifact.saved", {"artifact": score_ref, "shape": list(scores.shape),
            "dtype": "<f4", "purpose": "Complete query-by-development cosine matrix including excluded self entries"})
        targets = {c["source_version"] for row in ranked["rows"] for c in row["candidates"]}
        endpoints = sorted(set(anchors) | targets)
        text = _saved_text(self, session, endpoints, inputs["metadata"])
        metadata = {s: {"source_version": s, **{k: inputs["metadata"][s].get(k) for k in ("title", "url", "published_at")}} for s in endpoints}
        value = {**ranked, "method": METHOD, "binding": binding, "versions": versions, "manifest": manifest,
            "study_key": data["study_key"], "top_k": data["top_k"], "input_plan": data["plan"],
            "vector_snapshot": snapshot, "scores_artifact": score_ref, "score_shape": list(scores.shape),
            "original_frame_count": len(original["membership"]), "exclusion_counts": selection["exclusion_counts"],
            "metadata": metadata, "text": text, "distinct_candidates": len(targets), "ranking_seconds": ranking_seconds,
            "new_embeddings": 0, "new_model_calls": 0, "network_calls": 0, "memberships_changed": False,
            "status": "complete" if not ranked["pending_slots"] and not ranked["missing_vector_sources"] and not text["missing"] else "partial"}
        return present(self, session, bound, "candidate_run", value, render(value), data["study_key"])
