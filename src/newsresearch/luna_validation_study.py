"""Offline, audited preparation of a separate bounded Luna lead-validation study.

No model dispatch, membership adoption, hidden retrieval or paid permission is
performed here. Reading a supplied lead does not validate its full article.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

import numpy as np

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active
from .event_pair_study import load_plan
from . import luna_group_validation as sampling
from .luna_lead_answers import TASK_INSTRUCTION, build_request, make_lead

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "luna-frozen-seven-day-lead-validation-v1"
GROUP_RESULT = "1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d"
STOPWORDS = frozenset("about after again against among before being between could first from have into more most other over same should their there these they this those through under using very were what when where which while with would article nieuws nieuwe omdat tijdens worden wordt heeft hebben deze door voor over naar niet maar zijn meer tegen tussen vanuit zonder".split())


def _save(engine: Research, session: str, value: Any, purpose: str) -> str:
    ref = str(engine.ledger.artifacts.put(value))
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": ref, "purpose": purpose})
    return ref


def _rank(seed: str, value: str) -> str:
    return digest({"seed": seed, "fold": "held-out-group", "group": value})


def _tokens(value: str | None) -> set[str]:
    return {word for word in re.findall(r"[^\W\d_]+", (value or "").casefold())
            if len(word) >= 5 and word not in STOPWORDS}


def _method(instruction: str) -> Json:
    files = [Path(__file__), Path(sampling.__file__), Path(__file__).with_name("luna_lead_answers.py"),
             Path(__file__).with_name("luna_validation_gateway.py"), Path(__file__).with_name("codex_provider.py")]
    return {"method": METHOD, "instruction": instruction,
            "implementation_hashes": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
            "frame": "Exact current guarded seven-day groups and singletons; no new grouping or embeddings",
            "sampling": {"complete_multi_article_groups": 300, "article_anchors": 100,
                         "held_out_groups": 100, "replacement": False,
                         "method": sampling.SAMPLING_METHOD},
            "lead": "Title plus first three nonempty stored paragraphs, at most 3000 body characters; not full source",
            "retrieval": {"pooled_vector_top_k": 12, "temporal_limit": None, "title_token_top_k": 6,
                          "minimum_title_token_letters": 5, "title_stopwords": sorted(STOPWORDS),
                          "outside_controls_per_anchor": 2, "retain_all_co_members": True,
                          "provider_event_id": "Exact existing raw_record.eventUri only; no inferred identifiers"},
            "budget": {"primary_requests": 400, "article_exposures": 6000, "automatic_retries": 0},
            "limitations": ["Retrospective lead-only model references, not human gold or full-article validation",
                            "Previously developed groups; no untouched confirmatory claim",
                            "Candidate-pool recall does not estimate unrestricted corpus recall",
                            "The separate held-out group fold is frozen before labels; no label-based tuning",
                            "Group folds are not article-disjoint or event-disjoint; no confirmatory held-out validation claim",
                            "SHA ranks approximate SRS under exchangeable ranks; not independently certified randomness"],
            "paid_authorization": False, "membership_adoption": False}


def _lead(engine: Research, session: str, source_id: str, metadata: Json) -> Json | None:
    source_sql = "SELECT payload FROM sources WHERE id=?"
    paragraph_sql = "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start,id"
    engine.ledger.append(session, "luna.lead.inspection.intended", {
        "source_version": source_id, "source_sql": source_sql, "paragraph_sql": paragraph_sql,
        "parameters": [source_id], "purpose": "Verify exact first stored paragraphs and source offsets"})
    row = engine.ledger.db.execute(source_sql, (source_id,)).fetchone()
    if row is None:
        raise AuditError("Frozen source missing from the required source ledger")
    source = json.loads(row["payload"])
    body = source.get("body") or ""
    if source.get("retention") != "permitted" or not body.strip():
        engine.ledger.append(session, "luna.lead.unavailable", {"source_version": source_id,
                                                               "reason": "No permitted retained body"})
        return None
    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if metadata.get("body_sha256") is not None and body_hash != metadata["body_sha256"]:
        raise AuditError("Frozen source body hash differs from original vector-study metadata")
    paragraphs = [dict(item) for item in engine.ledger.db.execute(paragraph_sql, (source_id,))]
    for passage in paragraphs:
        if (body[passage["start"]:passage["end"]] != passage["text"]
                or hashlib.sha256(passage["text"].encode("utf-8")).hexdigest() != passage["text_hash"]):
            raise AuditError("Stored lead paragraph differs from exact source body or hash")
    lead = make_lead(source_id, source.get("title"), source.get("published_at"), paragraphs)
    engine.ledger.append(session, "luna.lead.inspected", {
        "source_version": source_id, "body_sha256": body_hash,
        "passage_ids": [passage["parent_ref"]["id"] for passage in lead["passages"]],
        "coverage": lead["coverage"], "fullarticle_not_read": True})
    return lead if lead["passages"] else None


def render_plan(plan: Json) -> str:
    frame, anchors, work = plan["sampling"]["group_frame"], plan["sampling"]["anchor_frame"], plan["workload"]
    prepared = sum(task["status"] == "prepared" for task in plan["tasks"])
    unavailable = sum(task["status"] == "source_unavailable" for task in plan["tasks"])
    oversize = sum(task["status"] == "oversize" for task in plan["tasks"])
    lines = ["Luna lead-validation preparation — no model judgments performed.",
             f"Frozen guarded seven-day frame: {frame['N']:,} multi-article groups; {anchors['N']:,} article anchors including singletons.",
             f"Selected {frame['n']:,} complete groups (nominal inclusion probability {frame['pi']}) and {anchors['n']:,} anchors (probability {anchors['pi']}).",
             f"Requests: {prepared:,} prepared; {unavailable:,} source-unavailable; {oversize:,} oversize; {work['primary_requests']:,} planned / 400 maximum.",
             f"Article exposures: {work['article_exposures']:,} / 6,000; automatic retries 0; models run 0; judgments pending {prepared:,}.",
             f"{len(plan['held_out_groups']):,} sampled groups are frozen as held out. Group folds are not article-disjoint or event-disjoint; this is retrospective model-reference assessment, not confirmatory held-out validation. Previously exposed development articles in selected packets: {plan['source_frame']['prior_development_article_overlap']:,}.",
             "Titles and up to three lead paragraphs are screened. Precision is pending; candidate-pool recall is pending and cannot establish full-corpus recall. No groups changed."]
    overview = plan["retrieval_overview"]
    lines.append(f"Internal retrieval query: each selected anchor's saved pooled vector and title words of at least five letters. Scope {anchors['N']:,} frozen articles, no temporal limit; {overview['vector_scored_pairs']:,} pairs scored, {overview['returned_candidate_pairs']:,} union candidates retained. Rank limits: vector 12, independent title overlap 6, all co-members, two outside-pool controls. No relevance cutoff or yes/no tags; cosine is similarity, not probability.")
    for item in overview["examples"]:
        title = item.get("title") or item["source_version"]
        label = f"[{title}]({item['url']})" if item.get("url") else str(title)
        lines.append(f"Anchor {overview['example_anchor']} candidate rank {item['rank']}: {label}; cosine {item['score']:.6f}.")
    for example in plan["examples"]:
        articles = "; ".join(f"[{item.get('title') or item['source_version']}]({item['url']})"
                             if item.get("url") else str(item.get("title") or item["source_version"])
                             for item in example["articles"])
        lines.append(f"Prepared example {example['logical_id']}: {articles}")
    return "\n\n".join(lines)


def prepare(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"group_result", "study_key", "codex_executable", "instruction", "seed"}:
        raise ResearchError("Offline Luna preparation accepts no execution or expanded-budget fields")
    group_id = data.get("group_result", GROUP_RESULT)
    key, seed = data.get("study_key", METHOD), data.get("seed", METHOD)
    instruction = data.get("instruction", TASK_INSTRUCTION)
    executable = Path(data.get("codex_executable", ""))
    if (group_id != GROUP_RESULT or instruction != TASK_INSTRUCTION
            or any(not isinstance(value, str) or not value.strip() or len(value) > 160 for value in (key, seed))
            or not executable.is_absolute() or not executable.is_file()):
        raise ResearchError("Bind the current guarded group result, exact lead instruction, fixed seed and real absolute Codex executable")
    method = _method(instruction)
    config: Json = {"codex_model": "gpt-6-luna", "reasoning_effort": "low", "codex_executable": str(executable),
              "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
              "timeout_seconds": 180, "max_input_bytes": 262144, "max_output_bytes": 262144}
    binding = digest({"group_result": group_id, "seed": seed, "method": method, "config": config})
    ledger = engine.ledger
    existing = ledger.db.execute("SELECT id,payload FROM records WHERE kind='luna_group_validation_plan' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (key,)).fetchone()
    if existing:
        value = json.loads(existing["payload"])
        if value["study_binding"] != binding:
            raise ResearchError("Stable Luna study key already binds another immutable method, frame, seed or executable")
        ledger.append(session, "analysis.cache_reused", {"kind": "luna_group_validation_plan", "id": existing["id"],
                                                         "versions": value["versions"], "reason": "Exact frozen preparation reuse"})
        presentation = engine._record_presentation(session, Context(context.objective, context.actor, value["versions"]), {
            "results": [{"kind": "luna_group_validation_plan", "id": existing["id"]}],
            "markdown": render_plan(value), "destination": "codex_chat", "status": "prepared_for_delivery"})
        return {"id": existing["id"], **value, "presentation": presentation, "reused": True}
    versions = dict(context.versions)
    contents = {"protocol": method, "question": {"text": "How precisely do frozen guarded seven-day groups represent one event, and which examined same-event neighbors were missed?"},
                "selection": {"rules": {"group_result": group_id, "seed": seed, "complete_groups": 300,
                                         "anchors": 100, "singleton_coverage": True, "no_replacement": True}},
                "dossier_definition": {"unit": "One real-world event reported by different sources or publication times; no incident or harm requirement"},
                "codebook": {"labels": ["same_event", "mixed_events", "different_event", "uncertain"], "definitions": instruction},
                "prompt": {"instructions": instruction},
                "profile": {"mode": "systematic", "population_estimate": False, "human_validated": False,
                            "retrospective_model_reference": True, "no_label_tuning": True}, "model_profile": config}
    for kind, content in contents.items():
        versions[kind] = engine._version(session, Context(context.objective, context.actor, versions), {
            "kind": kind, "key": key, "content": content, "amend_latest": True,
            "reason": "Register bounded offline lead-validation study before source inspection"})["id"]
    current = ledger.get(group_id, "event_group_refinement_result")
    if (not isinstance(current.get("rule"), dict) or current["rule"].get("publication_gap_days") != 7
            or ("adopted" in current and current["adopted"] is not True)):
        raise ResearchError("Luna validation must retain the exact guarded adopted seven-day grouping rule")
    old_plan, old_frame, development = load_plan(engine, session, current["plan"])
    index = ledger.get(old_plan["index"], "vector_index")
    if context.versions.get("dataset", index["versions"]["dataset"]) != index["versions"]["dataset"]:
        raise ResearchError("Luna study context must retain the original pilot dataset")
    versions = {**index["versions"], **versions, "dataset": index["versions"]["dataset"]}
    ledger.append(session, "luna.study.preparation.intended", {"study_binding": binding, "versions": versions,
                                                             "method": method, "group_result": group_id})
    rows = ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    groups = {row["group_id"]: list(row["members"]) for row in rows}
    if len(groups) != len(rows):
        raise AuditError("Frozen groups contain duplicate group identifiers")
    sampled = sampling.sample_validation_frames(groups, seed=seed)
    membership = sampled["frozen_membership"]
    mapping = ledger.artifacts.read(old_plan["mapping_artifact"])
    ids = [row["source_version"] for row in mapping]
    raw = ledger.artifacts.read_bytes(old_plan["pooled_vectors_artifact"])
    if len(raw) != len(ids) * index["dimensions"] * 4 or not set(membership) <= set(ids):
        raise AuditError("Frozen group membership differs from complete original pooled vector mapping")
    matrix = np.frombuffer(raw, dtype="<f4").reshape(len(ids), index["dimensions"]).astype(np.float64)
    positions = {source: position for position, source in enumerate(ids)}
    metadata = ledger.artifacts.read(old_plan["metadata_artifact"])
    if not set(membership) <= set(metadata):
        raise AuditError("Frozen membership lacks complete original source metadata")
    dataset = ledger.get(versions["dataset"], "dataset")
    dataset_sources = set(dataset["source_versions"])
    if not set(membership) <= dataset_sources or not set(ids) <= dataset_sources:
        raise AuditError("Frozen vector or membership source lies outside the original dataset")
    tokens = {source: _tokens(metadata[source].get("title")) for source in membership}
    anchor_frames = []
    retrieval = []
    for anchor in sampled["anchor_frame"]["selected_ids"]:
        scores = matrix @ matrix[positions[anchor]]
        ranked = sorted((source for source in membership if source != anchor), key=lambda source: (-float(scores[positions[source]]), source))
        vector_ids = ranked[:12]
        keyword_ranked = sorted((source for source in membership if source != anchor and tokens[source] & tokens[anchor]),
                                key=lambda source: (-len(tokens[source] & tokens[anchor]), source))
        keyword = keyword_ranked[:6]
        frame = sampling.build_anchor_candidates(anchor, membership, pooled_vector_ids=vector_ids,
            keyword_ids=keyword, provider_ids=[], seed=seed, outside_controls=2)
        anchor_frames.append(frame)
        retrieval.append({"anchor": anchor, "parameters": method["retrieval"],
                          "vector_ranked": [{"source_version": source, "score": float(scores[positions[source]])} for source in ranked],
                          "title_ranked": [{"source_version": source, "overlap": len(tokens[source] & tokens[anchor])} for source in keyword_ranked],
                          "provider_id_status": "Not separately available in frozen source metadata; no inferred provider matches",
                          "selected": frame})
    workload = sampling.realized_workload(sampled["selected_group_members"], anchor_frames)
    if not workload["within_budget"]:
        raise ResearchError("Realized Luna study exceeds 400 requests or 6000 exposures; no truncation, replacement or models allowed")
    retrieval_ref = _save(engine, session, retrieval, "Frozen all-ranked vector retrieval and independent title candidates; no new query embedding")
    ledger.append(session, "luna.anchor.retrieval.completed", {"artifact": retrieval_ref, "anchors": len(anchor_frames),
        "scope": "Entire original frozen membership without temporal limit", "method": method["retrieval"], "model_calls": 0})
    held_out = set(sorted(sampled["group_frame"]["selected_ids"], key=lambda value: (_rank(seed, value), value))[:100])
    development_sources = {source for row in development["rows"] for source in (row["left"], row["right"])}
    selected = set(source for members in sampled["selected_group_members"].values() for source in members)
    selected.update(source for frame in anchor_frames for source in [frame["anchor"], *(row["candidate"] for row in frame["candidates"])])
    leads = {source: _lead(engine, session, source, metadata[source]) for source in sorted(selected)}
    tasks: list[Json] = []
    examples: list[Json] = []
    specs: list[tuple[str, str, list[str], Json | None]] = [
        ("group", group, members, None) for group, members in sampled["selected_group_members"].items()]
    specs.extend(("anchor", frame["anchor"], [frame["anchor"], *(row["candidate"] for row in frame["candidates"])], frame) for frame in anchor_frames)
    for mode, logical_id, sources, anchor_frame in specs:
        fold_group = logical_id if mode == "group" else membership[logical_id]
        task: Json = {"mode": mode, "logical_id": logical_id, "source_versions": sources,
                      "request_ref": None, "status": "source_unavailable", "fold": "held_out" if fold_group in held_out else "audit"}
        if anchor_frame is not None:
            task["anchor_candidates"] = anchor_frame
        if all(leads[source] is not None for source in sources):
            supplied = [lead for source in sources if (lead := leads[source]) is not None]
            request = build_request(leads=supplied, versions=versions,
                                    mode=mode, anchor_source=logical_id if mode == "anchor" else None)
            task["request_ref"] = _save(engine, session, request, "Exact bounded Luna lead request; no dispatch authorization")
            task["status"] = "prepared" if len(canonical(request).encode("utf-8")) <= config["max_input_bytes"] else "oversize"
        tasks.append(task)
        if mode == "group" and task["fold"] != "held_out" and len(examples) < 3:
            examples.append({"logical_id": logical_id, "articles": [metadata[source] for source in sources]})
    retrieval_examples = [{**metadata[row["source_version"]], "rank": rank, "score": row["score"]}
                          for rank, row in enumerate(retrieval[0]["vector_ranked"][:3], 1)] if retrieval else []
    plan = {"versions": versions, "method": method, "group_result": group_id, "study_key": key,
            "study_binding": binding, "seed": seed, "sampling": sampled,
            "groups": sampled["group_frame"]["selected_ids"], "membership": membership,
            "anchor_frames": anchor_frames, "workload": workload, "tasks": tasks, "config": config,
            "held_out_groups": sorted(held_out), "retrieval_artifact": retrieval_ref, "examples": examples,
            "retrieval_overview": {"vector_scored_pairs": len(anchor_frames) * (len(membership) - 1),
                "returned_candidate_pairs": sum(len(frame["candidates"]) for frame in anchor_frames),
                "example_anchor": retrieval[0]["anchor"] if retrieval else None, "examples": retrieval_examples},
            "source_frame": {"dataset": versions["dataset"], "membership_articles": len(membership),
                "dataset_articles": len(dataset_sources), "missing_vector_articles": len(dataset_sources - set(ids)),
                "missing_vector_source_versions": sorted(dataset_sources - set(ids)),
                "vector_articles": len(ids), "vector_articles_outside_membership": len(set(ids) - set(membership)),
                "vector_sources_excluded_by_frozen_membership": sorted(set(ids) - set(membership)),
                "prior_development_article_overlap": len(selected & development_sources),
                "old_sealed_holdout_labels_opened": False, "previous_frame_reused": True,
                "date_and_vector_exclusions": current.get("exclusions", current.get("coverage")),
                "frame_hash": digest(old_frame.get("representatives", []))},
            "model_calls": 0, "status": "prepared_pending_fresh_execution"}
    identifier = ledger.record(session, "luna_group_validation_plan", key, plan)
    presentation = engine._record_presentation(session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "luna_group_validation_plan", "id": identifier}],
        "markdown": render_plan(plan), "destination": "codex_chat", "status": "prepared_for_delivery"})
    return {"id": identifier, **plan, "presentation": presentation}
