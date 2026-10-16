"""Audited actual partitions across publication caps, with no new inference."""
from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import time
from typing import TYPE_CHECKING

from . import event_pair_feature_study as base
from . import event_temporal_study as temporal
from . import event_window_groups as numeric
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_experiment import _records
from .event_pair_selection import FEATURES
from .event_pair_study import load_plan
from .event_rule_application import publication_coverage

if TYPE_CHECKING:
    from .runtime import Research

CAPS = (7, 30, 90, None)
METHOD = "offline-actual-event-partition-window-comparison-v1"
CODE = ("event_window_study.py", "event_window_groups.py", *temporal.CODE)
COUNT_SQL = """WITH g AS (SELECT json_array_length(json_extract(value,'$.members')) AS n
FROM json_each(?)) SELECT count(*) AS groups, coalesce(sum(n>1),0) AS multi_article_groups,
coalesce(sum(CASE WHEN n>1 THEN n ELSE 0 END),0) AS grouped_articles,
coalesce(sum(n=1),0) AS singletons FROM g"""


def cap_key(cap: int | None) -> str:
    return str(cap) if cap is not None else "unlimited"


def _parent(engine: Research, identifier: str) -> tuple[Json, Json, Json]:
    parent = engine.ledger.get(identifier, "event_temporal_result")
    manifest = engine.ledger.get(parent["manifest"], "event_temporal_manifest")
    if (parent["status"] not in {"completed_temporal_diagnostic", "completed_with_failed_pairs"}
            or parent["versions"] != manifest["versions"] or parent["pending_pairs"] != 0
            or parent["parent_result"] != manifest["method"]["parent"]
            or parent["rule"] != manifest["method"]["rule"] or parent["plan"] != manifest["method"]["plan"]
            or manifest["method"]["implementation"] != base._hashes(temporal.CODE)):
        raise AuditError("Partition comparison requires the unchanged completed date-free score diagnostic")
    current, original = temporal._parent(engine, parent["parent_result"])
    if current["plan"] != parent["plan"] or current["rule"] != parent["rule"]:
        raise AuditError("Temporal scores and current grouping bind different inputs")
    return parent, current, original


def _references(engine: Research, session: str, parent: Json, original: Json, plan: Json, development: Json) -> Json:
    saved = engine.ledger.artifacts.read(parent["exports"]["references"]["artifact"])
    judged, versions, identifier = temporal.refinement._references(engine, session, original, plan, development["rows"])
    rows = {row["pair_id"]: row for row in saved["rows"]}
    if (len(rows) != len(saved["rows"]) or set(rows) != {row["pair_id"] for row in development["rows"]}
            or versions != saved["reference_versions"] or identifier != saved["original_reference_result"]):
        raise AuditError("Stored comparison does not preserve every original reference")
    for row in development["rows"]:
        prior = rows[row["pair_id"]]
        if any(prior.get(key) != row.get(key) for key in ("left", "right", "distance", "fold", "weight", "inclusion_probability")) or prior["reference"] != judged[row["pair_id"]]:
            raise AuditError("Reference sources, labels or probability weights changed")
    engine.ledger.append(session, "analysis.cache_reused", {"artifact": parent["exports"]["references"]["artifact"],
        "versions": parent["versions"], "basis": "all_original_revalidated_development_references_after_all_partitions_frozen"})
    return {"rows": development["rows"], "judged": judged, "versions": versions, "original_result": identifier,
        "failed_ids": [row["pair_id"] for row in saved["rows"] if row["processing_status"] != "completed"]}


def quality(references: Json, groups: list[Json], failed: set[str]) -> Json:
    owners = temporal.refinement._owners(groups)
    flags: dict[str, dict[str, list[str]]] = {row["group_id"]: {label: [] for label in ("same_event", "different_event", "uncertain")}
             for row in groups if len(row["members"]) > 1}
    rows = []
    for row in references["rows"]:
        reference = references["judged"][row["pair_id"]]
        if reference["status"] != "completed" or reference["label"] not in {"same_event", "different_event", "uncertain"}:
            raise AuditError("Incomplete or invalid references cannot support group quality checks")
        available = row["left"] in owners and row["right"] in owners and row["pair_id"] not in failed
        together = owners[row["left"]] == owners[row["right"]] if available else None
        rows.append({**row, "reference": reference, "together": together,
            "left_group": owners.get(row["left"]), "right_group": owners.get(row["right"]),
            "processing_status": "completed" if available else "unprocessed"})
        if together:
            flags[owners[row["left"]]][reference["label"]].append(row["pair_id"])
    labels = {}
    for label in ("same_event", "different_event", "uncertain"):
        selected = [row for row in rows if row["reference"]["label"] == label]
        labels[label] = {"total": len(selected), "weight": math.fsum(row["weight"] for row in selected),
            **{name: sum(row["together"] is value for row in selected) for name, value in
               (("together", True), ("separate", False), ("unprocessed", None))},
            **{"weighted_" + name: math.fsum(row["weight"] for row in selected if row["together"] is value)
               for name, value in (("together", True), ("separate", False), ("unprocessed", None))}}
    covered = sum(any(value.values()) for value in flags.values())
    return {"rows": rows, "labels": labels, "group_flags": flags,
        "multi_groups_with_internal_reference": covered, "multi_groups_without_internal_reference": len(flags) - covered,
        "groups_with_different_event_reference": sum(bool(value["different_event"]) for value in flags.values()),
        "groups_with_uncertain_reference": sum(bool(value["uncertain"]) for value in flags.values()),
        "unprocessed_references": sum(row["together"] is None for row in rows), "human_gold": False, "held_out": False}


def _sql_counts(engine: Research, session: str, artifact: str, expected: Json, versions: Json) -> str:
    calculation = {"sql": COUNT_SQL, "parameters": [{"artifact": artifact, "encoding": "exact_UTF8_JSON"}],
                   "versions": versions, "unit": "provisional groups, never accepted events"}
    ref = base._save(engine, session, calculation, "Required group-count SQL and exact artifact parameter before execution")
    engine.ledger.append(session, "event_windows.sql.intended", {"calculation_artifact": ref})
    observed = dict(engine.ledger.db.execute(COUNT_SQL, (engine.ledger.artifacts.read_bytes(artifact).decode("utf-8"),)).fetchone())
    if any(observed[key] != expected[key] for key in observed):
        raise AuditError("Independent SQL group counts differ from the frozen numerical partition")
    engine.ledger.append(session, "event_windows.sql.completed", {"calculation_artifact": ref, "counts": observed})
    return ref


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_window_result", "id": identifier}], "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"parent_result", "comparison_key", "user_instruction", "output_directory"}
            or not engine.config.offline or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare an offline group comparison with exact parent, instruction and protected output")
    parent, current, original = _parent(engine, data["parent_result"])
    if context.versions and context.versions != parent["versions"]:
        raise ResearchError("Group comparison context differs from the saved scores")
    method = {"method": METHOD, "implementation": base._hashes(CODE), "parent": data["parent_result"],
        "input_versions": parent["versions"], "score_artifact": parent["feature_artifact"], "rule": parent["rule"],
        "caps": list(CAPS), "user_instruction": data["user_instruction"], "observed_chat_timestamp": None,
        "population": "Same vector-bearing usable-publication-date cohort at every cap; missing vectors/dates remain unprocessed",
        "algorithm": "Original deterministic complete-link from singleton articles, then identical duplicate-discounted fixed refinement at every cap; full five-feature rule unchanged",
        "evaluation": "Freeze all four label-blind partitions before reloading every original probability-weighted development reference; compare actual co-memberships, uncertainty separate",
        "guard": "No reference-based rollback, retuning or adoption; show current guarded seven-day partition separately",
        "lineage": "Exact member-set intersections versus controlled seven-day, adjacent windows and current active groups; partitions need not be nested",
        "count_sql": COUNT_SQL, "size_calculation": "mean/median and nearest-rank p90 of multi-article group sizes; spans are UTC-calendar publication ranges",
        "acceptance": "No accepted dossiers, corpus accuracy, held-out validation or new active group version",
        "output_directory": str(Path(data["output_directory"]).absolute()), "new_model_calls": 0, "new_embeddings": 0}
    key = data["comparison_key"]
    previous = _records(engine, "event_window_manifest", key)
    if previous and (len(previous) != 1 or previous[0][1]["method"] != method):
        raise ResearchError("Comparison key already binds another immutable method")
    if previous:
        manifest_id, manifest = previous[0]
        versions = manifest["versions"]
    else:
        versions = dict(parent["versions"])
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, parent["versions"]), {
                "kind": kind, "key": key, "amend_latest": True, "branch": "exploratory-actual-window-partitions",
                "reason": "Compare actual groups under fixed algorithms instead of substituting passing-pair counts",
                "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                    "text": "How do actual group counts, sizes, memberships and development-reference co-memberships change across publication windows?",
                    "rules": "All original pilot members retained; same dated-vector denominator; no new inference or source collection",
                    "unit": "Provisional groups reporting one real-world event; singletons do not establish distinct events"}})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_window_manifest", key, manifest)
    finished = _records(engine, "event_window_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Completed group comparison differs from its manifest")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_group_comparison"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_windows.intended", {"manifest": manifest_id, "versions": versions})
    plan, _, development = load_plan(engine, session, parent["plan"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    mapped = engine.ledger.artifacts.read(plan["mapping_artifact"])
    ids = [row["source_version"] for row in mapped]
    selected = engine.ledger.get(plan["versions"]["dataset"], "dataset")["source_versions"]
    coverage = publication_coverage(ids, {source: row.get("published_at") for source, row in metadata.items()})
    eligible = sorted(coverage["valid_dates"])
    vector_ids, eligible_ids = set(ids), set(eligible)
    scored = engine.ledger.artifacts.read(parent["feature_artifact"])
    if (set(metadata) != set(selected) or len(metadata) != parent["dataset_articles"]
            or len(set(ids)) != len(ids) or len(ids) != parent["vector_articles"] or not set(ids) <= set(metadata)
            or len(eligible) != parent["dated_vector_articles"] or len(coverage["missing_date_ids"]) != parent["missing_date_articles"]
            or len(scored) != parent["pooled_candidates"] or len({row["pair_id"] for row in scored}) != len(scored)):
        raise AuditError("Group comparison input coverage differs from the saved full-pilot scan")
    failed = {row["pair_id"] for row in scored if row["status"] != "completed" or any(row["features"].get(name) is None for name in FEATURES)}
    for row in scored:
        if (row["left"] not in vector_ids or row["right"] not in vector_ids or row["left"] >= row["right"]
                or row["pair_id"] != digest([row["left"], row["right"]])
                or row["pair_id"] not in failed and row["features"]["pooled_cosine"] != 1. - row["distance"]):
            raise AuditError("Saved score table changed canonical pair identity or pooled distance")
        if row["pair_id"] not in failed and any(isinstance(row["features"][name], bool)
                or not isinstance(row["features"][name], (int, float)) or not math.isfinite(row["features"][name])
                or not -1 <= row["features"][name] <= 1 for name in FEATURES):
            raise AuditError("Completed saved feature row contains an invalid cosine")
    if len(failed) != parent["failed_feature_pairs"]:
        raise AuditError("Feature-failure coverage changed")
    engine.ledger.append(session, "analysis.cache_reused", {"artifact": parent["feature_artifact"], "versions": parent["versions"],
        "rows": len(scored), "source_result": data["parent_result"], "basis": "complete_saved_date_free_five_feature_scores_no_rescoring"})
    active = engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"])
    if set(temporal.refinement._owners(active)) != set(eligible):
        raise AuditError("Current groups do not partition the common comparison cohort")
    stored = _records(engine, "event_window_partition", manifest_id)
    cached = {row["cap_key"]: (identifier, row) for identifier, row in stored}
    if len(cached) != len(stored) or not set(cached) <= {cap_key(cap) for cap in CAPS}:
        raise AuditError("Duplicate or unexpected frozen group windows")
    partitions, partition_records = {}, []
    for cap in CAPS:
        window = cap_key(cap)
        if window in cached:
            identifier, frozen = cached[window]
            if frozen["versions"] != versions or frozen["manifest"] != manifest_id or frozen["cap_days"] != cap:
                raise AuditError("Resumed partition changed version bindings")
            proposal = engine.ledger.artifacts.read(frozen["partition_artifact"])
            engine.ledger.append(session, "analysis.cache_reused", {"artifact": frozen["partition_artifact"], "basis": "exact_version_frozen_window_partition"})
        else:
            engine.ledger.append(session, "event_windows.partition.intended", {"manifest": manifest_id, "cap_days": cap, "versions": versions})
            started = time.perf_counter()
            proposal = numeric.build(eligible, scored, metadata, parent["rule"], cap)
            seconds = time.perf_counter() - started
            proposal["bridge_pair_ids"] = [row["pair_id"] for row in proposal.pop("bridges")]
            group_ref = base._save(engine, session, proposal["groups"], "Required exact provisional group frame for SQL and lineage")
            calculation = _sql_counts(engine, session, group_ref, proposal["statistics"], versions)
            artifact = base._save(engine, session, proposal, "Required label-blind partition, stable memberships, moves and complete diagnostics")
            frozen = {"manifest": manifest_id, "versions": versions, "cap_key": window, "cap_days": cap,
                "partition_artifact": artifact, "groups_artifact": group_ref, "calculation_artifact": calculation,
                "algorithm_seconds": seconds, "frozen_before_reference_check": True}
            identifier = engine.ledger.record(session, "event_window_partition", manifest_id, frozen)
        expected = next(row for row in parent["caps"] if row["cap_days"] == cap)
        if len(proposal["passing_pair_ids"]) != expected["dated_passing_pairs"]:
            raise AuditError("Actual grouping changed the previously recorded passing-pair set size")
        if cap == 7:
            old_candidate = engine.ledger.artifacts.read(current["exports"]["candidate_groups"]["artifact"])
            if ({tuple(sorted(row["members"])) for row in old_candidate} != {tuple(sorted(row["members"])) for row in proposal["groups"]}
                    or proposal["initial_counts"]["multi_article_groups"] != original["multi_article_groups"]):
                raise AuditError("Controlled seven-day partition did not reproduce the original label-blind algorithm")
        partitions[window] = proposal
        partition_records.append(identifier)
        engine.ledger.append(session, "event_windows.partition.frozen", {"partition": identifier, "cap_key": window,
            "algorithm_seconds": frozen["algorithm_seconds"], "counts": proposal["statistics"]})
    engine.ledger.append(session, "event_windows.all_partitions.frozen", {"manifest": manifest_id, "partitions": partition_records,
        "reference_based_rollback": False, "adopted": False})
    references = _references(engine, session, parent, original, plan, development)
    failed.update(references["failed_ids"])
    evaluations = {window: quality(references, proposal["groups"], failed) for window, proposal in partitions.items()}
    active_quality = quality(references, active, failed)
    directory = Path(data["output_directory"])
    exports, table, lineages = {}, [], {}
    previous_groups = active
    for cap in CAPS:
        window = cap_key(cap)
        proposal, assessment = partitions[window], evaluations[window]
        changes = numeric.lineage(partitions["7"]["groups"], proposal["groups"])
        lineages[window] = {"versus_seven_days": changes, "versus_previous_window": numeric.lineage(previous_groups, proposal["groups"]),
            "versus_current_active": numeric.lineage(active, proposal["groups"])}
        previous_groups = proposal["groups"]
        groups = [{**row, "status": "provisional" if len(row["members"]) > 1 else "review_singleton", "accepted": False,
            "reference_flags": assessment["group_flags"].get(row["group_id"]),
            "articles": [metadata[source] for source in row["members"]]} for row in proposal["groups"]]
        exports[window] = temporal.application._export(engine, session, directory, f"groups-{window}.json", groups)
        table.append({"cap_key": window, "cap_days": cap, "statistics": proposal["statistics"], "initial_counts": proposal["initial_counts"],
            "counts": proposal["counts"], "diagnostics": proposal["diagnostics"],
            "quality": {key: value for key, value in assessment.items() if key not in {"rows", "group_flags"}},
            "changes_from_seven_days": {key: value for key, value in changes.items() if key not in {"relations", "membership_changed_article_ids"}}})
    article_rows = []
    owners = {window: temporal.refinement._owners(proposal["groups"]) for window, proposal in partitions.items()}
    for source in sorted(metadata):
        article_rows.append({**metadata[source], "status": "missing_vectors" if source not in vector_ids else "missing_publication_date" if source not in eligible_ids else "provisional",
            "groups": {window: by_source.get(source) for window, by_source in owners.items()}, "accepted": False})
    exports["articles"] = temporal.application._export(engine, session, directory, "article-memberships.json", article_rows)
    exports["lineage"] = temporal.application._export(engine, session, directory, "all-group-lineage.json", lineages)
    exports["quality"] = temporal.application._export(engine, session, directory, "all-reference-comemberships.json", evaluations)
    exports["table"] = temporal.application._export(engine, session, directory, "comparison-table.json", table)
    group_examples = []
    for window in ("30", "unlimited"):
        candidates = [group for group in partitions[window]["groups"] if len(group["members"]) > 1
            and len({owners["7"][source] for source in group["members"]}) > 1]
        if candidates:
            group = min(candidates, key=lambda row: (-len(row["members"]), row["group_id"]))
            parts = Counter(owners["7"][source] for source in group["members"])
            dates = [coverage["valid_dates"][source] for source in group["members"]]
            group_examples.append({"window": window, "group_id": group["group_id"], "size": len(group["members"]),
                "prior_group_count": len(parts), "shared_article_counts": sorted(parts.values(), reverse=True),
                "publication_span_days": (max(dates) - min(dates)).days,
                "articles": [metadata[source] for source in group["members"][:3]], "unjudged": True})
    example_rows = []
    for label in ("same_event", "different_event", "uncertain"):
        candidates = [row for row in evaluations["7"]["rows"] if row["reference"]["label"] == label]
        for row in sorted(candidates, key=lambda row: row["pair_id"]):
            together = {window: next(value["together"] for value in assessment["rows"] if value["pair_id"] == row["pair_id"])
                        for window, assessment in evaluations.items()}
            if len(set(together.values())) > 1:
                example_rows.append({"label": label, "together": together, "articles": [metadata[row["left"]], metadata[row["right"]]]})
                break
    result = {"versions": versions, "manifest": manifest_id, "parent_result": data["parent_result"], "plan": parent["plan"],
        "status": "completed_with_missing_processing" if failed or any(value["unprocessed_references"] for value in evaluations.values()) else "completed_group_comparison",
        "dataset_articles": len(metadata), "vector_articles": len(ids), "dated_vector_articles": len(eligible),
        "missing_vector_articles": len(metadata) - len(ids), "missing_date_articles": len(coverage["missing_date_ids"]),
        "reused_scored_pairs": len(scored), "failed_feature_pairs": parent["failed_feature_pairs"], "pending_pairs": 0,
        "partition_records": partition_records, "table": table, "active_statistics": numeric.stats(active, metadata),
        "active_quality": {key: value for key, value in active_quality.items() if key not in {"rows", "group_flags"}},
        "reference_pairs": len(references["rows"]), "reference_versions": references["versions"], "original_reference_result": references["original_result"],
        "examples": example_rows, "group_examples": group_examples, "exports": exports, "active_partition_changed": False,
        "new_model_calls": 0, "new_embedding_requests": 0, "new_feature_calculations": 0, "network_calls": 0,
        "accepted_dossiers": 0, "heldout_labels_opened": 0, "started_at": manifest["started_at"], "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_window_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    from .rag_answers import _link
    lines = ["**These are actual rebuilt groups, using the same grouping algorithm at every window.**", "",
        f"Reused {result['reused_scored_pairs']:,} saved score rows. All four partitions cover the same {result['dated_vector_articles']:,} articles "
        f"from the {result['dataset_articles']:,}-article pilot. No new embeddings, similarity calculations or model calls.", "",
        "A group below contains at least two articles. Average and maximum sizes refer to these groups; singletons are listed separately.", "",
        "| Window | Groups | Articles grouped | Singletons | Average size | Largest group | Longest publication span |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for row in result["table"]:
        value = row["statistics"]
        size = value["multi_article_size"]
        average = f"{size['mean']:.2f}" if size["mean"] is not None else "unavailable"
        lines.append(f"| {row['cap_key']} | {value['multi_article_groups']:,} | {value['grouped_articles']:,} | {value['singletons']:,} | "
            f"{average} | {size['maximum']} | {value['publication_spans']['maximum_days']} days |")
    lines += ["", f"The current active seven-day version still has {result['active_statistics']['multi_article_groups']:,} groups. "
        "It previously rolled back a component using development judgments. This controlled comparison omits that rollback for every window, "
        "so the seven-day row is a separate baseline; the difference from the active version is not caused by a wider window.", "",
        f"**Quality check: actual group memberships against all {result['reference_pairs']} existing development model references.** "
        "These are model judgments, not human gold or corpus accuracy. Uncertain references remain separate.", "",
        "| Window | Same-event references together | Different-event references together | Uncertain references together | Groups with a different-event conflict |",
        "|---|---:|---:|---:|---:|"]
    for row in result["table"]:
        quality_value = row["quality"]
        labels = quality_value["labels"]
        lines.append(f"| {row['cap_key']} | " + " | ".join(f"{labels[label]['together']}/{labels[label]['total']}"
            for label in ("same_event", "different_event", "uncertain")) + f" | {quality_value['groups_with_different_event_reference']} |")
    lines += ["", "A different-event conflict means an existing model reference says two co-grouped reports describe different events. "
        "Groups without an internal reference have unmeasured semantic quality; they are not assumed correct. "
        "Groups containing any internal reference by window: " + "; ".join(
            f"{row['cap_key']}: {row['quality']['multi_groups_with_internal_reference']}/{row['statistics']['multi_article_groups']}"
            for row in result["table"]) + ".", "",
        "| Window | Articles with changed group companions versus 7 days | New groups combining earlier groups | Earlier groups split |",
        "|---|---:|---:|---:|"]
    for row in result["table"][1:]:
        changes = row["changes_from_seven_days"]
        lines.append(f"| {row['cap_key']} | {changes['membership_changed_articles']:,} | {changes['merged_new_groups']:,} | {changes['split_old_groups']:,} |")
    lines += ["", "Partitions can rearrange as well as merge; wider windows do not guarantee nested groups. "
        "The private comparison retains every group overlap, member change, lost/new internal pair, size distribution, original sampling weight and reference decision.", "",
        "Examples whose actual co-membership changes (existing labels reused):"]
    for example in result["examples"]:
        decisions = ", ".join(f"{window}: {'together' if decision is True else 'separate' if decision is False else 'unprocessed'}"
                              for window, decision in example["together"].items())
        lines.append(f"- Model reference **{example['label']}**; {decisions}: "
            + " ↔ ".join(_link(item.get("title") or item["source_version"], item.get("url")) for item in example["articles"]))
    if not result["examples"]:
        lines.append("- No original model-reference pair changed co-membership.")
    lines += ["", "Concrete group changes (structural examples, **unjudged**):"]
    for example in result["group_examples"]:
        lines.append(f"- {example['window']} days: {example['size']} articles now share a group, drawn from {example['prior_group_count']} seven-day groups "
            f"(shared article counts {example['shared_article_counts']}); publication span {example['publication_span_days']} days. Example sources: "
            + "; ".join(_link(item.get("title") or item["source_version"], item.get("url")) for item in example["articles"]))
    if not result["group_examples"]:
        lines.append("- No wider-window multi-article group combines members from different seven-day groups.")
    lines += ["", f"Coverage limits: {result['missing_vector_articles']} articles lack vectors; {result['missing_date_articles']} vector-bearing articles lack usable dates "
        "and remain outside all four partitions, including unlimited, to keep the comparison fair. "
        f"Feature failures: {result['failed_feature_pairs']}; pending pairs: {result['pending_pairs']}; "
        "unprocessed reference comparisons by window: " + ", ".join(f"{row['cap_key']}={row['quality']['unprocessed_references']}" for row in result["table"]) + ". "
        "Missing processing is never a negative finding. All groups are provisional; accepted event dossiers: 0. "
        "No held-out labels were opened and no new window has been adopted.", "",
        "[Full group-by-group lineage](" + result["exports"]["lineage"]["path"].replace("\\", "/") + ") · "
        "[Comparison table and size distributions](" + result["exports"]["table"]["path"].replace("\\", "/") + ") · "
        "[Article memberships at all windows](" + result["exports"]["articles"]["path"].replace("\\", "/") + ")"]
    return "\n".join(lines)
