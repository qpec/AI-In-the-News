"""Audited offline preparation of complete-source cross-window event review.

No model dispatch, semantic judgment, threshold calibration or merge occurs.
The immutable old budget and sealed body holdout survive this new queue.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from . import event_group_evidence as numeric
from . import event_group_link_study as links
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .codex_provider import CodexCLIProvider
from .event_pair_answers import CONTRACT, TASK_INSTRUCTION, validate_request
from .event_pair_experiment import _config, _records, _request, _spent
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "bounded-complete-source-cross-window-event-review-preparation-v1"
CODE = ("event_group_evidence_study.py", "event_group_evidence.py", "event_pair_answers.py",
        "event_pair_experiment.py", "codex_provider.py", *links.CODE)


def _configuration(engine: Research, current: Json) -> Json:
    reference = engine.ledger.get(current["original_reference_result"], "event_pair_experiment")
    old = reference["config"]
    config = _config(engine, {"codex_model": old["codex_model"], "codex_executable": old["codex_executable"]})
    if config["executable_sha256"] != old["executable_sha256"]:
        raise ResearchError("Original Codex executable changed; explicitly repin configuration before preparation")
    return {**config, "configuration_origin": {"mode": "unchanged_original_event_pair_configuration",
                                                "result": current["original_reference_result"]}}


def _parents(engine: Research, identifier: str) -> tuple[Json, Json, Json, Json, Json]:
    previous = engine.ledger.get(identifier, "event_group_link_result")
    manifest = engine.ledger.get(previous["manifest"], "event_group_link_manifest")
    if (previous["versions"] != manifest["versions"]
            or manifest["method"]["implementation"] != links.base._hashes(links.CODE)
            or previous["current_memberships_changed"] or previous["actual_group_merges"] != 0
            or previous["status"] != "completed_provisional_group_links"):
        raise AuditError("Evidence preparation requires the unchanged seven-day choice")
    comparison, temporal, current, original = links._parents(engine, previous["comparison_result"])
    if previous["selected_seven_day_result"] != temporal["parent_result"]:
        raise AuditError("Selected seven-day group lineage differs")
    return previous, comparison, temporal, current, original


def _budget(engine: Research, session: str, plan: Json) -> Json:
    query = "SELECT payload FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.event_pair_study')=?"
    artifact = links.base._save(engine, session, {"sql": query, "parameters": [plan["study_key"]]},
                               "Original workflow attempt-accounting query before queue allocation")
    spent = _spent(engine, plan["study_key"])
    if (len({row["attempt"] for row in spent}) != len(spent)
            or any(type(row.get("event_pair_retry")) is not bool or row.get("reserved_article_exposures") != 2
                   or row.get("reserved_pair_attempts") != 1 for row in spent)):
        raise AuditError("Original article-attempt reservation accounting differs")
    primary = sum(not row["event_pair_retry"] for row in spent)
    retries = len(spent) - primary
    if primary > 90 or retries > 10 or len(spent) > 100:
        raise AuditError("Original workflow budget already exceeded")
    unresolved = [key for key, value in engine.ledger.unresolved.items()
                  if value.get("event_pair_study") == plan["study_key"]]
    return {"query_artifact": artifact, "original_study_key": plan["study_key"],
        "spent_attempts": len(spent), "spent_article_exposures": 2 * len(spent),
        "spent_primary": primary, "spent_retries": retries,
        "remaining_primary": 90 - primary, "remaining_retries": 10 - retries,
        "remaining_attempts": 100 - len(spent), "remaining_article_exposures": 200 - 2 * len(spent),
        "unresolved_attempts": unresolved, "budget_reset": False,
        "future_dispatch": "Reconcile durable counts again; require fresh concrete authorization; original allocation remains binding"}


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_group_evidence_result", "id": identifier}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"previous_result", "study_key", "output_directory"} or not engine.config.offline
            or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare offline seven-day result reuse, immutable study key and protected output")
    previous, comparison, temporal, current, original = _parents(engine, data["previous_result"])
    if context.versions and context.versions != previous["versions"]:
        raise ResearchError("Review context differs from selected seven-day frame")
    config = _configuration(engine, current)
    method = {"method": METHOD, "implementation": links.base._hashes(CODE),
        "previous_result": data["previous_result"], "input_versions": previous["versions"],
        "working_groups": current["exports"]["groups"], "saved_features": temporal["feature_artifact"],
        "rule": current["rule"], "candidate_rule": numeric.METHOD,
        "scope": "All current dated groups including singletons; union publication span over seven days; provider ID not required",
        "review": "Every unordered article pair within the entire union, including old-group internal pairs; no representative-only approval or transitive chains",
        "selection": "At least one multi-article group first; smaller unions then stronger weakest margin; disjoint old groups; max10 proposals,6 articles per union,36 primary pair tasks",
        "holdout": "Only original development-body-fold sources may enter packets; sealed validation-body fold never inspected or relabeled",
        "budget": "Original90 primary/10 retry,100 attempts/200 article exposures cumulatively; reconcile previous spend; no new authorization inferred",
        "evidence_contract": CONTRACT, "instructions": TASK_INSTRUCTION, "config": config,
        "reference_check": "Freeze full frame and bounded queue before old54 model references; preserve known conflicts without relabeling",
        "acceptance": "No actual merges, human validation, calibrated probabilities or accepted dossiers",
        "output_directory": str(Path(data["output_directory"]).absolute()), "new_models": 0, "new_embeddings": 0}
    key = data["study_key"]
    prior = _records(engine, "event_group_evidence_manifest", key)
    if prior and (len(prior) != 1 or prior[0][1]["method"] != method):
        raise ResearchError("Study key already binds another immutable evidence-preparation method")
    if prior:
        manifest_id, manifest = prior[0]
        versions = manifest["versions"]
    else:
        versions = dict(previous["versions"])
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition", "prompt", "codebook", "model_profile"):
            content = {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                "text": "Which separate seven-day groups warrant full-source same-event review?",
                "unit": "One real-world event across sources or reporting times; every union member must be evidenced",
                "rules": "Missing, failed, pending and unjudged evidence never means different events",
                "labels": ["same_event", "different_event", "uncertain"]}
            if kind == "model_profile":
                content = dict(config)
            versions[kind] = engine._version(session, Context(context.objective, context.actor, previous["versions"]), {
                "kind": kind, "key": key, "amend_latest": True, "branch": "exploratory-cross-window-event-evidence",
                "reason": "Continue source-backed same-event review preparation after provider-only tier found no candidates",
                "content": content})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_group_evidence_manifest", key, manifest)
    finished = _records(engine, "event_group_evidence_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Prepared result differs from its immutable evidence manifest")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_evidence_preparation"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_group_evidence.intended", {"manifest": manifest_id, "new_models": 0})
    plan, frame, development = load_plan(engine, session, current["plan"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    groups = engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    scored = engine.ledger.artifacts.read(temporal["feature_artifact"])
    source_ids = engine.ledger.get(versions["dataset"], "dataset")["source_versions"]
    owners = links.windows.temporal.refinement._owners(groups)
    if (set(metadata) != set(source_ids) or len(scored) != temporal["pooled_candidates"]
            or len(owners) != comparison["dated_vector_articles"]
            or not set(owners) <= set(metadata)):
        raise AuditError("Evidence preparation source, feature or selected group coverage differs")
    engine.ledger.append(session, "analysis.cache_reused", {"score_artifact": temporal["feature_artifact"],
        "groups_artifact": current["exports"]["groups"]["artifact"], "basis": "exact_version_saved_feature_and_guarded_group_reuse"})
    frozen = _records(engine, "event_group_evidence_queue", key)
    if frozen:
        if len(frozen) != 1 or frozen[0][1]["manifest"] != manifest_id or frozen[0][1]["versions"] != versions:
            raise AuditError("Frozen review queue differs from method")
        frozen_id, saved = frozen[0]
        queue = engine.ledger.artifacts.read(saved["artifact"])
        budget = saved["budget"]
        engine.ledger.append(session, "analysis.cache_reused", {"artifact": saved["artifact"], "basis": "frozen_label_blind_evidence_queue"})
    else:
        budget = _budget(engine, session, plan)
        folds = {row["body_sha256"]: row["fold"] for row in frame["representatives"]}
        allowed = {source for source in owners if folds.get(metadata[source]["body_sha256"]) == "development"}
        queue = numeric.prepare(groups, scored, metadata, current["rule"],
            max_tasks=min(36, budget["remaining_primary"]) if not budget["unresolved_attempts"] else 0,
            review_source_ids=allowed)
        artifact = links.base._save(engine, session, queue, "Complete candidate frame and bounded all-union-pair queue frozen before reading reference labels")
        saved = {"manifest": manifest_id, "versions": versions, "artifact": artifact, "budget": budget,
            "frozen_before_reference_check": True, "allowed_development_sources": len(allowed)}
        frozen_id = engine.ledger.record(session, "event_group_evidence_queue", key, saved)
    engine.ledger.append(session, "event_group_evidence.frozen", {"frozen": frozen_id, "diagnostics": queue["diagnostics"]})
    references = links.windows._references(engine, session, temporal, original, plan, development)
    reference_by_pair = {row["pair_id"]: references["judged"][row["pair_id"]] for row in references["rows"]}
    packet_rows: list[Json] = []
    examples: list[Json] = []
    prior_packets = _records(engine, "event_group_evidence_packets", key)
    if prior_packets:
        if (len(prior_packets) != 1 or prior_packets[0][1]["manifest"] != manifest_id
                or prior_packets[0][1]["frozen_queue"] != frozen_id or prior_packets[0][1]["versions"] != versions):
            raise AuditError("Prepared packets differ from their frozen queue")
        packet_rows = engine.ledger.artifacts.read(prior_packets[0][1]["artifact"])
        engine.ledger.append(session, "analysis.cache_reused", {"artifact": prior_packets[0][1]["artifact"],
            "basis": "exact_version_source_and_transport_packets"})
    else:
        provider = CodexCLIProvider(engine.ledger.root / "codex-workers", executable=config["codex_executable"],
            model=config["codex_model"], timeout_seconds=config["timeout_seconds"],
            max_input_bytes=config["max_input_bytes"], max_output_bytes=config["max_output_bytes"])
        for task in queue["tasks"]:
            try:
                request = _request(engine, session, task, metadata, versions)
                validate_request(request)
                request_ref = links.base._save(engine, session, request, "Complete stored source bodies, exact instructions, schema, source hashes and passage IDs; preparation only")
                try:
                    invocation = provider.prepare(request)
                except ResearchError as error:
                    packet_rows.append({**task, "status": "transport_preparation_incomplete", "request_ref": request_ref,
                                        "reason_code": str(error), "label": None})
                    continue
                dispatch_ref = links.base._save(engine, session, invocation.manifest(), "Exact Codex CLI inputs and byte-limit check prepared without starting a process")
                packet_rows.append({**task, "status": "prepared", "request_ref": request_ref,
                    "dispatch_ref": dispatch_ref,
                    "task_key": digest({"manifest": manifest_id, "request": request, "contract": CONTRACT, "config": config}),
                    "prior_model_reference": reference_by_pair.get(task["pair_id"]),
                    "reference_reuse": "comparison only; no exact-new-version model result claimed"})
            except AuditError:
                raise
            except ResearchError as error:
                packet_rows.append({**task, "status": "source_input_incomplete", "request_ref": None,
                    "reason_code": str(error), "label": None})
        packet_artifact = links.base._save(engine, session, packet_rows, "Frozen complete source and transport packet outcomes before export")
        engine.ledger.record(session, "event_group_evidence_packets", key, {"manifest": manifest_id,
            "versions": versions, "frozen_queue": frozen_id, "artifact": packet_artifact})
    engine.ledger.append(session, "event_group_evidence.packets_frozen", {"manifest": manifest_id, "pair_packets": len(packet_rows)})
    packet_map = {row["pair_id"]: row for row in packet_rows}
    annotated = []
    for candidate in queue["selected"]:
        tasks = [packet_map[identifier] for identifier in candidate["pair_task_ids"]]
        labels = Counter(value["label"] for row in tasks if (value := reference_by_pair.get(row["pair_id"]))
                         and value["status"] == "completed")
        status = "packet_preparation_incomplete" if any(row["status"] != "prepared" for row in tasks) else "awaiting_fresh_codex_authorization"
        annotated.append({**candidate, "packet_status": status, "prior_reference_labels": dict(labels),
            "known_reference_conflict": labels["different_event"] > 0,
            "current_semantic_decision": None, "independent_validation": False})
        if len(examples) < 3:
            examples.append({**annotated[-1], "articles": candidate["articles"]})
    directory = Path(data["output_directory"])
    exports = {"frame": links.windows.temporal.application._export(engine, session, directory, "candidate-frame.json", queue),
        "proposals": links.windows.temporal.application._export(engine, session, directory, "review-proposals.json", annotated),
        "packets": links.windows.temporal.application._export(engine, session, directory, "source-packet-manifest.json", packet_rows)}
    result = {"versions": versions, "manifest": manifest_id, "previous_result": data["previous_result"],
        "selected_seven_day_result": previous["selected_seven_day_result"], "frozen_queue": frozen_id,
        "status": "prepared_evidence_queue" if all(row["status"] == "prepared" for row in packet_rows) else "partial_source_preparation",
        "diagnostics": queue["diagnostics"], "budget": budget, "selected_proposals": len(annotated),
        "pair_tasks": len(packet_rows), "prepared_pair_packets": sum(row["status"] == "prepared" for row in packet_rows),
        "failed_source_packets": sum(row["status"] == "source_input_incomplete" for row in packet_rows),
        "failed_transport_packets": sum(row["status"] == "transport_preparation_incomplete" for row in packet_rows),
        "unique_articles_prepared": len({source for row in packet_rows if row["status"] == "prepared" for source in (row["left"], row["right"])}),
        "planned_primary_article_exposures": 2 * len(packet_rows), "reserved_retry_article_exposures": 2 * budget["remaining_retries"],
        "known_reference_conflict_proposals": sum(row["known_reference_conflict"] for row in annotated),
        "reused_reference_pairs_in_queue": sum(row["pair_id"] in reference_by_pair for row in packet_rows),
        "reference_pairs_checked": len(references["rows"]), "unprocessed_references": len(references["failed_ids"]),
        "dataset_articles": comparison["dataset_articles"], "missing_vector_articles": comparison["missing_vector_articles"],
        "missing_date_articles": comparison["missing_date_articles"], "feature_failed_pairs": temporal["failed_feature_pairs"],
        "pending_model_judgments": len(packet_rows), "new_model_calls": 0, "new_embedding_requests": 0,
        "actual_group_merges": 0, "accepted_dossiers": 0, "current_memberships_changed": False,
        "sealed_holdout_opened": False, "original_reference_result": references["original_result"],
        "config": config, "statistics": previous["statistics"], "exports": exports, "examples": examples, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_group_evidence_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    from .rag_answers import _link
    d, b, stats = result["diagnostics"], result["budget"], result["statistics"]
    lines = ["**Seven-day groups retained; cross-window source review prepared.**", "",
        f"Offline scope: {result['dataset_articles']:,} pilot articles, {d['current_groups']:,} existing groups including singletons. "
        f"Working frame remains {stats['multi_article_groups']:,} multi-article groups / {stats['grouped_articles']:,} grouped articles / {stats['singletons']:,} singletons.", "",
        f"Saved similarities nominated {d['frame_pairs']:,} group pairs spanning over seven days; {d['qualified_pairs']:,} passed all five existing similarity gates on every cross-group article pair. "
        "Provider IDs are optional. These are review candidates, not proven same-event links.", "",
        f"**Prepared queue: {result['selected_proposals']} proposed group links, {result['prepared_pair_packets']}/{result['pair_tasks']} full-source article-pair packets, "
        f"{result['unique_articles_prepared']} distinct articles.** Every pair within each entire union is included, including old-group internal pairs. "
        "No representative-only approval or transitive chaining. Original validation-body fold excluded from inspection.", "",
        f"Codex configuration pinned from the original run: {result['config']['codex_model']}; executable SHA-256 verified. "
        f"Exact CLI inputs prepared with a {result['config']['max_input_bytes']:,}-byte input limit; no process started.", "",
        f"Candidate dispositions: {d['candidate_status_counts']}. Selected types: {d['selected_types']}; publication-span bands: {d['selected_span_bins']}. "
        "Selection favors small unions involving an existing multi-article group, then stronger weakest-pair similarity; it is not representative and does not estimate accuracy.", "",
        f"Original workflow spent {b['spent_attempts']}/100 attempts ({b['spent_article_exposures']}/200 article exposures): "
        f"{b['spent_primary']} first attempts + {b['spent_retries']} retries. Remaining allocation: {b['remaining_primary']} first attempts + {b['remaining_retries']} retries. "
        f"Prepared first-attempt exposures: {result['planned_primary_article_exposures']}; retry reserve: {result['reserved_retry_article_exposures']}. Budget not reset.", "",
        f"Existing reference overlap: {result['reused_reference_pairs_in_queue']} queued pairs; {result['known_reference_conflict_proposals']} proposals flagged by a saved different-event reference. "
        f"Revalidated {result['reference_pairs_checked']} saved model-reference pairs; {result['unprocessed_references']} unprocessed. "
        "These development references do not provide independent validation. No new event-identity judgments have run."]
    for n, example in enumerate(result["examples"], 1):
        lines += ["", f"{n}. **Unjudged candidate:** group sizes {example['group_sizes']}, "
            f"{len(example['article_members'])} articles across {example['publication_span_days']} publication days; {example['packet_status']}. "
            + "; ".join(_link(article.get("title") or article["source_id"], article.get("url"))
                          + " (" + str(article.get("published_at")) + ")" for article in example["articles"])]
    lines += ["", f"Missing vectors: {result['missing_vector_articles']}; unusable dates: {result['missing_date_articles']}; "
        f"saved-feature failures: {result['feature_failed_pairs']}; source/transport preparation failures: {result['failed_source_packets']}/{result['failed_transport_packets']}; "
        f"pending model judgments: {result['pending_model_judgments']}; unresolved previous attempts: {len(b['unresolved_attempts'])}. "
        "Missing evidence is not a different-event finding. New model/embedding calls: 0; merges: 0; accepted dossiers: 0.", "",
        "**Remaining step:** fresh concrete authorization for the bounded Codex judgments is required because the previous run approval expired. "
        "The prepared requests and original cumulative limits are fixed; all-same results would remain provisional pending the required review.", "",
        "[Prepared proposals](" + result["exports"]["proposals"]["path"].replace("\\", "/") + ") Â· "
        "[Full candidate dispositions](" + result["exports"]["frame"]["path"].replace("\\", "/") + ")"]
    return "\n".join(lines)
