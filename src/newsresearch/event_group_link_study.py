"""Keep the selected seven-day frame and audit conservative cross-window links."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from . import event_group_links as numeric
from . import event_pair_feature_study as base
from . import event_window_study as windows
from .common import AuditError, Context, Json, ResearchError, require_active, utc
from .event_pair_experiment import _records
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "seven-day-working-choice-and-strong-cross-window-proposals-v1"
CODE = ("event_group_link_study.py", "event_group_links.py", *windows.CODE)


def _parents(engine: Research, identifier: str) -> tuple[Json, Json, Json, Json]:
    comparison = engine.ledger.get(identifier, "event_window_result")
    manifest = engine.ledger.get(comparison["manifest"], "event_window_manifest")
    if (comparison["status"] not in {"completed_group_comparison", "completed_with_missing_processing"}
            or comparison["versions"] != manifest["versions"] or comparison["parent_result"] != manifest["method"]["parent"]
            or manifest["method"]["implementation"] != base._hashes(windows.CODE)
            or comparison["accepted_dossiers"] != 0 or comparison["pending_pairs"] != 0):
        raise AuditError("Group linking requires the unchanged completed group-window comparison")
    temporal, current, original = windows._parent(engine, comparison["parent_result"])
    if current["rule"]["publication_gap_days"] != 7 or comparison["plan"] != current["plan"]:
        raise AuditError("Working groups must be the original guarded seven-day frame")
    return comparison, temporal, current, original


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_group_link_result", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"comparison_result", "study_key", "instruction", "superseded_instruction", "output_directory"}
            or not engine.config.offline or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare offline comparison reuse, exact changed decision and protected output")
    comparison, temporal, current, original = _parents(engine, data["comparison_result"])
    if context.versions and context.versions != comparison["versions"]:
        raise ResearchError("Link context differs from the compared pilot")
    method = {"method": METHOD, "implementation": base._hashes(CODE), "comparison": data["comparison_result"],
        "input_versions": comparison["versions"], "working_frame": temporal["parent_result"], "rule": current["rule"],
        "instruction": data["instruction"], "withdrawn_30_day_instruction": data["superseded_instruction"],
        "observed_chat_timestamp": None, "provider_namespace": "Event Registry raw_record.eventUri in the original pilot",
        "frame": "Current multi-article groups only; both fully populated by one identical exact provider event URI; union publication span >7 days",
        "qualification": "At least two distinct URL hostnames and body hashes across union; every cross-article pair has complete saved five-feature evidence passing unchanged cosines, with time gate ignored",
        "not_independence": "Distinct domains/body hashes do not establish independent reporting",
        "group_proposals": "Complete-link across old groups; AB and BC cannot establish AC; no active merge",
        "reference_check": "Freeze every raw proposal before reusing all original probability-weighted model references; report raw effects and known-conflict quarantine separately",
        "acceptance": "No calibrated probability or extremely-likely claim; event facts and cited evidence must be reviewed before actual merging",
        "output_directory": str(Path(data["output_directory"]).absolute()), "new_models": 0, "new_embeddings": 0}
    key = data["study_key"]
    previous = _records(engine, "event_group_link_manifest", key)
    if previous and (len(previous) != 1 or previous[0][1]["method"] != method):
        raise ResearchError("Study key already binds another immutable group-link method or decision")
    if previous:
        manifest_id, manifest = previous[0]
        versions = manifest["versions"]
    else:
        versions = dict(comparison["versions"])
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, comparison["versions"]), {
                "kind": kind, "key": key, "amend_latest": True, "branch": "exploratory-conservative-group-links",
                "reason": "User retains seven days and requests a separate very-strong-evidence group-link mechanism",
                "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                    "text": "Can separate seven-day report groups be proposed for cross-window event-identity review?",
                    "rules": "Reuse exact pilot, scores, provider snapshot and working groups; missing processing is not negative",
                    "unit": "Provisional report groups with proposed links to the same real-world event; no accepted event dossier"}})["id"]
        versions["policy"] = engine._version(session, Context(context.objective, context.actor, versions), {
            "kind": "policy", "key": "event-grouping-working-window:" + versions["dataset"], "amend_latest": True,
            "reason": "Human withdraws thirty days and explicitly keeps seven days",
            "content": {"method": "human-event-grouping-window-choice-v1", "publication_gap_days": 7,
                "selected_group_result": temporal["parent_result"], "selected_groups": current["exports"]["groups"],
                "instruction": data["instruction"], "withdrawn_instruction": data["superseded_instruction"],
                "thirty_day_selection_was_applied": False, "decision_origin": "human_user_instruction_in_current_codex_chat",
                "human_identity": None, "recorded_by": context.actor, "observed_chat_timestamp": None,
                "status": "working_provisional_choice", "threshold_validated": False, "accepted_findings": 0,
                "cross_window_links": "Separate unjudged proposals; evidence review before merging"}})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_group_link_manifest", key, manifest)
    finished = _records(engine, "event_group_link_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Completed links differ from their immutable method")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_group_links"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_group_links.intended", {"manifest": manifest_id, "policy": versions["policy"]})
    plan, _, development = load_plan(engine, session, current["plan"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    groups = engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    scored = engine.ledger.artifacts.read(temporal["feature_artifact"])
    snapshot = engine.ledger.artifacts.read(temporal["provider_artifact"])
    provider_rows = snapshot["rows"]
    source_ids = engine.ledger.get(versions["dataset"], "dataset")["source_versions"]
    provider_ids = {row["source_version"]: row["event_uri"] if row["coverage_status"] == "populated" else None for row in provider_rows}
    if (set(metadata) != set(source_ids) or set(provider_ids) != set(metadata) or len(provider_rows) != len(metadata)
            or dict(Counter(row["coverage_status"] for row in provider_rows)) != temporal["provider_coverage"]
            or any(row["coverage_status"] == "populated" and (row["uri_type"] != "text" or not isinstance(row["event_uri"], str) or not row["event_uri"].strip()) for row in provider_rows)
            or len(scored) != temporal["pooled_candidates"]
            or len(windows.temporal.refinement._owners(groups)) != comparison["dated_vector_articles"]):
        raise AuditError("Group-link score, provider or working-frame coverage changed")
    members = [source for row in groups for source in row["members"]]
    if len(set(members)) != len(members) or not set(members) <= set(metadata):
        raise AuditError("Working groups contain repeated or out-of-pilot articles")
    engine.ledger.append(session, "analysis.cache_reused", {"score_artifact": temporal["feature_artifact"],
        "provider_artifact": temporal["provider_artifact"], "group_artifact": current["exports"]["groups"]["artifact"],
        "versions": temporal["versions"], "working_versions": current["versions"], "basis": "exact_version_saved_scores_provider_metadata_and_guarded_working_frame"})
    frozen = _records(engine, "event_group_link_proposals", key)
    if frozen:
        if len(frozen) != 1 or frozen[0][1]["manifest"] != manifest_id or frozen[0][1]["versions"] != versions:
            raise AuditError("Frozen group links have another method")
        frozen_id, saved = frozen[0]
        proposal = engine.ledger.artifacts.read(saved["artifact"])
        engine.ledger.append(session, "analysis.cache_reused", {"artifact": saved["artifact"], "basis": "frozen_label_blind_group_links"})
    else:
        proposal = numeric.propose(groups, scored, metadata, provider_ids, current["rule"])
        artifact = base._save(engine, session, proposal, "Required complete label-blind group-link frame and proposals before references")
        saved = {"manifest": manifest_id, "versions": versions, "artifact": artifact, "frozen_before_reference_check": True}
        frozen_id = engine.ledger.record(session, "event_group_link_proposals", key, saved)
    engine.ledger.append(session, "event_group_links.frozen", {"frozen": frozen_id, "diagnostics": proposal["diagnostics"]})
    references = windows._references(engine, session, temporal, original, plan, development)
    failed = {row["pair_id"] for row in scored if row["status"] != "completed"} | set(references["failed_ids"])
    active_quality = windows.quality(references, groups, failed)
    consumed = {group for row in proposal["proposals"] for group in row["old_group_ids"]}
    expanded = [row for row in groups if row["group_id"] not in consumed] + [
        {"group_id": row["proposal_id"], "members": row["article_members"]} for row in proposal["proposals"]]
    if set(windows.temporal.refinement._owners(expanded)) != set(windows.temporal.refinement._owners(groups)):
        raise AuditError("Proposal simulation changed the working article population")
    raw_quality = windows.quality(references, expanded, failed)
    before = {row["pair_id"]: row for row in active_quality["rows"]}
    changed = [row for row in raw_quality["rows"] if row["together"] != before[row["pair_id"]]["together"]]
    annotated = []
    for row in proposal["proposals"]:
        flags = raw_quality["group_flags"][row["proposal_id"]]
        annotated.append({**row, "reference_flags": flags,
            "review_status": "quarantined_known_reference_conflict" if flags["different_event"] else "awaiting_event_fact_review"})
    statistics = windows.numeric.stats(groups, metadata)
    calculation = windows._sql_counts(engine, session, current["exports"]["groups"]["artifact"], statistics, versions)
    assessment = {"baseline": active_quality, "raw_proposal_simulation": raw_quality, "changed_reference_pairs": changed,
        "reference_versions": references["versions"], "original_reference_result": references["original_result"],
        "independent_validation": False, "note": "Current guarded groups already used development judgments; quarantine is not a passing independent evaluation"}
    directory = Path(data["output_directory"])
    exports = {"proposals": windows.temporal.application._export(engine, session, directory, "group-link-proposals.json", annotated),
        "frame": windows.temporal.application._export(engine, session, directory, "all-group-link-candidates.json", proposal),
        "references": windows.temporal.application._export(engine, session, directory, "reference-effects.json", assessment)}
    result = {"versions": versions, "manifest": manifest_id, "comparison_result": data["comparison_result"],
        "selected_seven_day_result": temporal["parent_result"], "frozen_proposals": frozen_id, "status": "completed_provisional_group_links",
        "policy": versions["policy"], "statistics": statistics, "calculation_artifact": calculation,
        "diagnostics": proposal["diagnostics"], "qualified_proposals": len(annotated),
        "quarantined_proposals": sum(row["review_status"] == "quarantined_known_reference_conflict" for row in annotated),
        "awaiting_event_fact_review": sum(row["review_status"] == "awaiting_event_fact_review" for row in annotated),
        "reference_pairs": len(references["rows"]), "affected_reference_pairs": len(changed),
        "affected_labels": dict(Counter(row["reference"]["label"] for row in changed)),
        "baseline_labels": active_quality["labels"], "raw_labels": raw_quality["labels"],
        "unprocessed_references": raw_quality["unprocessed_references"], "exports": exports,
        "examples": [{**row, "articles": [metadata[source] for source in row["article_members"][:3]]} for row in annotated[:2]],
        "dataset_articles": comparison["dataset_articles"], "missing_vector_articles": comparison["missing_vector_articles"],
        "missing_date_articles": comparison["missing_date_articles"], "failed_feature_pairs": temporal["failed_feature_pairs"], "pending_pairs": 0,
        "new_model_calls": 0, "new_embedding_requests": 0, "actual_group_merges": 0, "accepted_dossiers": 0,
        "completed_at": utc(), "current_memberships_changed": False}
    identifier = engine.ledger.record(session, "event_group_link_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    stats, diagnostic = result["statistics"], result["diagnostics"]
    lines = ["**Recorded decision: keep seven days. The proposed 30-day choice was withdrawn before it was applied.**", "",
        f"Working frame: {stats['multi_article_groups']:,} provisional multi-article groups, {stats['grouped_articles']:,} grouped articles "
        f"and {stats['singletons']:,} review singletons. Existing memberships remain unchanged.", "",
        "Current reference co-memberships (same-event / different-event / uncertain): " + " / ".join(
            f"{result['baseline_labels'][label]['together']}/{result['baseline_labels'][label]['total']}"
            for label in ("same_event", "different_event", "uncertain")) + ". "
        "The current rollback already used these development judgments, so this is not an independent accuracy check.", "",
        "The new cross-window stage requires the same provider event ID on every member, at least two distinct publisher domains and body hashes, "
        "and passing evidence on every cross-group article pair for all five existing similarity signals. It has no publication-gap cap. "
        "Groups must be mutually compatible; links cannot chain transitively.", "",
        f"**Offline result:** {diagnostic['fully_anchored_groups']:,}/{diagnostic['multi_article_groups']:,} groups have full, consistent provider IDs. "
        f"Partial/conflicting/missing ID groups: {diagnostic['partial_groups']}/{diagnostic['conflicting_groups']}/{diagnostic['missing_groups']}. "
        f"Checked {diagnostic['frame_pairs']} metadata-anchored group pairs spanning more than seven days; {diagnostic['qualified_pairs']} passed the complete cross-pair gate, "
        f"forming {result['qualified_proposals']} group-merge proposals. Known-reference quarantine: {result['quarantined_proposals']}; "
        f"awaiting event-fact review: {result['awaiting_event_fact_review']}.", "",
        f"**Quality measure:** {result['affected_reference_pairs']}/{result['reference_pairs']} saved model-reference pairs change co-membership in the raw proposal simulation "
        f"(labels: {result['affected_labels'] or 'none'}). Unprocessed reference comparisons: {result['unprocessed_references']}. "
        "This does not validate a very-high-probability claim. Provider IDs and cosine scores are supporting signals; distinct domains do not prove independent reporting. "
        "Actual merging requires review of shared actors, action, location and event date with cited evidence."]
    from .rag_answers import _link
    for example in result["examples"]:
        lines += ["", f"- Unjudged proposal: {len(example['old_group_ids'])} groups / {len(example['article_members'])} articles; "
            f"publication span {example['publication_span_days']} days; {example['review_status']}: "
            + "; ".join(_link(item.get("title") or item["source_version"], item.get("url")) for item in example["articles"])]
    lines += ["", f"Scope: {result['dataset_articles']:,} pilot articles; {result['missing_vector_articles']} missing vectors; "
        f"{result['missing_date_articles']} unusable dates; feature failures/pending: {result['failed_feature_pairs']}/{result['pending_pairs']}. "
        "The new stage covers multi-article groups only; missing evidence never means different events. "
        "New models/embeddings: 0; actual merges: 0; accepted event dossiers: 0.", "",
        "[All proposals](" + result["exports"]["proposals"]["path"].replace("\\", "/") + ") · "
        "[Candidate checks and exclusions](" + result["exports"]["frame"]["path"].replace("\\", "/") + ")"]
    return "\n".join(lines)
