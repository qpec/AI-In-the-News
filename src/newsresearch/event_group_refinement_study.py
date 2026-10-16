"""Audited, label-blind refinement and descriptive development comparison."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import math
from pathlib import Path
import time
from typing import TYPE_CHECKING

from . import event_group_refinement as algorithm
from . import event_pair_feature_study as base
from . import event_pair_monotone as rules
from . import event_rule_application as baseline_algorithm
from . import event_rule_application_study as previous
from .common import AuditError, Context, Json, ResearchError, require_active, utc
from .event_pair_experiment import _records
from .event_pair_selection import FEATURES
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "offline-event-group-refinement-comparison-v1"
CODE = ("event_group_refinement_study.py", "event_group_refinement.py", *previous.CODE)


def _parent(engine: Research, identifier: str) -> Json:
    parent = engine.ledger.get(identifier, "event_rule_application_result")
    manifest = engine.ledger.get(parent["manifest"], "event_rule_application_manifest")
    if (parent["status"] not in {"completed_provisional_application", "completed_with_failed_pairs"}
            or parent["versions"] != manifest["versions"] or parent["rule"] != manifest["method"]["rule"]
            or parent["parent_result"] != manifest["method"]["parent"]
            or parent["plan"] != manifest["method"]["plan"]
            or manifest["method"]["implementation"] != base._hashes(previous.CODE)
            or parent["accepted_dossiers"] != 0 or parent["pending_pairs"] != 0):
        raise AuditError("Refinement requires the unchanged completed provisional application")
    return parent


def _references(engine: Research, session: str, parent: Json, plan: Json, rows: list[Json]) -> tuple[Json, Json, str]:
    final = engine.ledger.get(parent["parent_result"], "event_pair_monotone_result")
    original = engine.ledger.get(final["original_parent"], "event_pair_experiment")
    base.parent_binding(engine, original, parent["plan"], plan)
    judged = base.references(engine, session, original, plan, rows)
    return judged, original["versions"], final["original_parent"]


def _owners(groups: list[Json]) -> dict[str, str]:
    return {source: group["group_id"] for group in groups for source in group["members"]}


def compare(rows: list[Json], judged: Json, before: list[Json], after: list[Json], failed: set[str]) -> Json:
    """All original development references, including uncertainty and weights."""
    old, new = _owners(before), _owners(after)
    if set(judged) != {row["pair_id"] for row in rows}:
        raise AuditError("Refinement comparison must retain every original development reference")
    output = []
    regressions = []
    for row in rows:
        reference = judged[row["pair_id"]]
        if reference["status"] != "completed" or reference["label"] not in {"same_event", "different_event", "uncertain"}:
            raise ResearchError("Incomplete reference processing cannot support the comparison")
        available = row["left"] in old and row["right"] in old and row["pair_id"] not in failed
        was = old[row["left"]] == old[row["right"]] if available else None
        now = new[row["left"]] == new[row["right"]] if available else None
        regression = bool(reference["label"] == "same_event" and was is True and now is False
                          or reference["label"] == "different_event" and was is False and now is True)
        item = {**row, "reference": reference, "baseline_together": was, "candidate_together": now,
                "processing_status": "completed" if available else "unprocessed",
                "changed": was != now, "development_regression": regression}
        output.append(item)
        if regression:
            regressions.append(row["pair_id"])
    summary = {}
    for label in ("same_event", "different_event", "uncertain"):
        selected = [row for row in output if row["reference"]["label"] == label]
        label_summary: Json = {"total": len(selected), "weight": math.fsum(row["weight"] for row in selected)}
        for key in ("baseline", "candidate"):
            label_summary[key] = {"together": sum(row[key + "_together"] is True for row in selected),
                "separate": sum(row[key + "_together"] is False for row in selected),
                "unprocessed": sum(row[key + "_together"] is None for row in selected),
                "weighted_together": math.fsum(row["weight"] for row in selected if row[key + "_together"] is True)}
        summary[label] = label_summary
    return {"rows": output, "summary": summary, "regressions": regressions,
            "changed": [row for row in output if row["changed"]], "held_out": False, "human_gold": False}


def _lineage(before: list[Json], after: list[Json]) -> list[Json]:
    owners = _owners(before)
    old_members = {row["group_id"]: set(row["members"]) for row in before}
    output = []
    for row in after:
        members = set(row["members"])
        parents = sorted({owners[source] for source in members})
        relation = "unchanged" if len(parents) == 1 and members == old_members[parents[0]] else (
            "split" if len(parents) == 1 else "merge" if all(old_members[parent] <= members for parent in parents) else "rearrangement")
        output.append({"group_id": row["group_id"], "relationship": relation,
            "previous_groups": [{"group_id": parent, "shared_members": sorted(members & old_members[parent])} for parent in parents]})
    return output


def _counts(groups: list[Json], bridges: list[Json], edges: int, objective: float) -> Json:
    return {"multi_article_groups": sum(len(row["members"]) > 1 for row in groups),
        "grouped_articles": sum(len(row["members"]) for row in groups if len(row["members"]) > 1),
        "singletons": sum(len(row["members"]) == 1 for row in groups), "bridge_edges": len(bridges),
        "internal_edges": edges - len(bridges), "objective": objective}


def guarded_partition(ids: list[str], edges: list[Json], before: list[Json], after: list[Json], comparison: Json) -> tuple[list[Json], list[Json]]:
    """Veto a regressing connected component, preserving unrelated improvements."""
    neighbors: dict[str, set[str]] = {source: set() for source in ids}
    for edge in edges:
        neighbors[edge["left"]].add(edge["right"])
        neighbors[edge["right"]].add(edge["left"])
    component = {}
    for source in sorted(ids):
        if source in component:
            continue
        stack = [source]
        component[source] = source
        while stack:
            for neighbor in sorted(neighbors[stack.pop()]):
                if neighbor not in component:
                    component[neighbor] = source
                    stack.append(neighbor)
    blocked: dict[str, list[str]] = {}
    for row in comparison["rows"]:
        if row["development_regression"]:
            if component[row["left"]] != component[row["right"]]:
                raise AuditError("A co-membership regression crosses disconnected graph components")
            blocked.setdefault(component[row["left"]], []).append(row["pair_id"])
    selected = [group for group in after if component[group["members"][0]] not in blocked]
    selected += [group for group in before if component[group["members"][0]] in blocked]
    vetoes = [{"component_id": key, "regression_pair_ids": sorted(blocked[key]),
        "reason": "Development-reference co-membership regression; baseline retained for the entire connected component",
        "members": sorted(source for source in ids if component[source] == key)} for key in sorted(blocked)]
    return sorted(selected, key=lambda row: (-len(row["members"]), row["members"])), vetoes


def _support(groups: list[Json], edges: list[Json], rule: Json, bodies: dict[str, str]) -> float:
    owners = _owners(groups)
    copies = Counter(bodies.values())
    return math.fsum((algorithm.EPSILON + min((edge["features"][name] - cut) / (1 - cut)
        for name, cut in zip(FEATURES, rule["thresholds"], strict=True))) / (copies[bodies[edge["left"]]] * copies[bodies[edge["right"]]])
        for edge in edges if owners[edge["left"]] == owners[edge["right"]])


def _present(engine: Research, session: str, context: Context, identifier: str, result: Json) -> Json:
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, result["versions"]), {
        "results": [{"kind": "event_group_refinement_result", "id": identifier}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) != {"parent_result", "comparison_key", "user_instruction", "output_directory"}
            or not engine.config.offline
            or any(not isinstance(value, str) or not value.strip() for value in data.values())):
        raise ResearchError("Declare an offline comparison, parent, exact instruction and protected output")
    parent = _parent(engine, data["parent_result"])
    if context.versions and context.versions != parent["versions"]:
        raise ResearchError("Refinement context differs from the original application")
    method = {"method": METHOD, "implementation": base._hashes(CODE), "parent": data["parent_result"],
        "input_versions": parent["versions"], "score_artifact": parent["score_artifact"], "rule": parent["rule"],
        "user_instruction": data["user_instruction"], "observed_chat_timestamp": None,
        "objective": "Sum of within-group (1e-9 + weakest normalized five-feature margin)/(eligible exact-body family multiplicities)",
        "algorithm": "Start from original cliques; deterministic positive-gain single-article relocations and compatible merges, at most 20 passes; no new passing edges",
        "adoption": "Freeze one complete candidate. For any newly joined different_event or newly separated same_event development reference, retain the baseline in that entire passing-graph connected component; keep unrelated candidate components. Adopt only for positive selected objective gain and complete coverage/cliques. No algorithm/threshold retuning.",
        "reference_check": "Freeze complete label-blind candidate before reading all original probability-weighted development judgments; descriptive reuse only, not independent validation",
        "uncertainty": "Keep uncertain model references distinct; missing/failed processing stays unknown; all memberships provisional",
        "output_directory": str(Path(data["output_directory"]).absolute()), "new_model_calls": 0, "new_embeddings": 0}
    key = data["comparison_key"]
    old = _records(engine, "event_group_refinement_manifest", key)
    if old and (len(old) != 1 or old[0][1]["method"] != method):
        raise ResearchError("Comparison key already binds another immutable refinement")
    if old:
        manifest_id, manifest = old[0]
        versions = manifest["versions"]
    else:
        versions = dict(parent["versions"])
        for kind in ("protocol", "question", "selection", "profile", "dossier_definition"):
            versions[kind] = engine._version(session, Context(context.objective, context.actor, parent["versions"]), {
                "kind": kind, "key": key, "branch": "exploratory-group-refinement", "amend_latest": True,
                "reason": "Compare one label-blind refinement while retaining the original application and failed cutoff status",
                "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                    "text": "Can compatible article relocations improve saved event-group proposals without development-reference regressions?",
                    "rules": "Exact original pilot and score artifact; no source exclusions or new inference",
                    "unit": "Provisional reports of one real-world event; no accepted event dossiers"}})["id"]
        manifest = {"versions": versions, "method": method, "started_at": utc()}
        manifest_id = engine.ledger.record(session, "event_group_refinement_manifest", key, manifest)
    finished = _records(engine, "event_group_refinement_result", key)
    if finished:
        if len(finished) != 1 or finished[0][1]["manifest"] != manifest_id or finished[0][1]["versions"] != versions:
            raise AuditError("Stored refinement differs from immutable manifest")
        engine.ledger.append(session, "analysis.cache_reused", {"result": finished[0][0], "basis": "exact_version_completed_refinement"})
        return _present(engine, session, context, *finished[0])
    engine.ledger.append(session, "event_groups.refinement.intended", {"manifest": manifest_id, "versions": versions, "parent": data["parent_result"]})
    plan, _, development = load_plan(engine, session, parent["plan"])
    articles = engine.ledger.artifacts.read(parent["exports"]["articles"]["artifact"])
    before = engine.ledger.artifacts.read(parent["exports"]["groups"]["artifact"])
    scored = engine.ledger.artifacts.read(parent["score_artifact"])
    engine.ledger.append(session, "analysis.cache_reused", {"artifact": parent["score_artifact"],
        "source_result": data["parent_result"], "input_versions": parent["versions"],
        "rows": len(scored), "basis": "exact_version_complete_feature_reuse_no_rescoring"})
    article_map = {row["source_version"]: row for row in articles}
    expected = engine.ledger.get(plan["versions"]["dataset"], "dataset")["source_versions"]
    eligible = sorted(source for source, row in article_map.items() if row["group_id"] is not None)
    if (len(article_map) != len(articles) or set(article_map) != set(expected)
            or len(articles) != parent["dataset_articles"] or len(eligible) != parent["date_eligible_articles"]
            or parent["versions"]["dataset"] != plan["versions"]["dataset"]
            or len(scored) != parent["pooled_candidates"] or len({row["pair_id"] for row in scored}) != len(scored)):
        raise AuditError("Refinement input coverage differs from the original application")
    failed = {row["pair_id"] for row in scored if row["status"] != "completed" or any(row["features"].get(name) is None for name in FEATURES)}
    edges = [row for row in scored if row["pair_id"] not in failed and rules.predicts(row, parent["rule"])]
    replay = baseline_algorithm.complete_link_groups(eligible, edges)
    if ([(row["group_id"], row["members"]) for row in before] != [(row["group_id"], row["members"]) for row in replay["groups"]]
            or len(failed) != parent["failed_feature_pairs"] or len(edges) != parent["proposed_link_pairs"]):
        raise AuditError("Original partition or passing-edge replay differs")
    frozen = _records(engine, "event_group_refinement_candidate", key)
    if frozen:
        if len(frozen) != 1 or frozen[0][1]["manifest"] != manifest_id or frozen[0][1]["versions"] != versions:
            raise AuditError("Frozen refinement differs from manifest")
        candidate_id, saved = frozen[0]
        proposal = engine.ledger.artifacts.read(saved["candidate_artifact"])
        algorithm_seconds = saved["algorithm_seconds"]
        engine.ledger.append(session, "analysis.cache_reused", {"artifact": saved["candidate_artifact"], "basis": "frozen_label_blind_refinement_no_retuning"})
    else:
        started = time.perf_counter()
        proposal = algorithm.refine(eligible, edges, before, parent["rule"], {source: article_map[source]["body_sha256"] for source in eligible})
        algorithm_seconds = time.perf_counter() - started
        artifact = base._save(engine, session, proposal, "Required label-blind candidate, moves and diagnostics frozen before reference comparison")
        candidate_id = engine.ledger.record(session, "event_group_refinement_candidate", key, {
            "versions": versions, "manifest": manifest_id, "candidate_artifact": artifact, "algorithm_seconds": algorithm_seconds,
            "frozen_before_reference_check": True, "frozen_at": utc()})
    engine.ledger.append(session, "event_groups.refinement.frozen", {"candidate": candidate_id,
        "algorithm_seconds": algorithm_seconds, "passes": proposal["diagnostics"]["passes"],
        "converged": proposal["diagnostics"]["converged"], "objective_gain": proposal["diagnostics"]["objective_gain"]})
    after = proposal["groups"]
    if set(_owners(after)) != set(eligible):
        raise AuditError("Candidate changed article coverage")
    passed_pairs = {tuple(sorted((row["left"], row["right"]))) for row in edges}
    if any(tuple(sorted(pair)) not in passed_pairs for group in after for pair in combinations(group["members"], 2)):
        raise AuditError("Candidate contains an unqualified article pair")
    judged, reference_versions, original_reference = _references(engine, session, parent, plan, development["rows"])
    comparison = compare(development["rows"], judged, before, after, failed)
    selected, vetoes = guarded_partition(eligible, edges, before, after, comparison)
    vetoed_components = len(vetoes)
    bodies = {source: article_map[source]["body_sha256"] for source in eligible}
    if (set(_owners(selected)) != set(eligible) or sum(len(group["members"]) for group in selected) != len(eligible)
            or any(tuple(sorted(pair)) not in passed_pairs for group in selected for pair in combinations(group["members"], 2))):
        raise AuditError("Guarded selection changed coverage or complete-link validity")
    selected_support = _support(selected, edges, parent["rule"], bodies)
    baseline_support = proposal["diagnostics"]["baseline_objective"]
    if not math.isclose(_support(before, edges, parent["rule"], bodies), baseline_support, rel_tol=1e-12, abs_tol=1e-12):
        raise AuditError("Independent baseline objective check differs")
    if not math.isclose(_support(after, edges, parent["rule"], bodies), proposal["diagnostics"]["objective"], rel_tol=1e-12, abs_tol=1e-12):
        raise AuditError("Independent candidate objective check differs")
    if selected_support + algorithm.MIN_GAIN < baseline_support:
        raise AuditError("Component guard reduced the original graph objective")
    adopted = selected_support > baseline_support + algorithm.MIN_GAIN
    if not adopted:
        selected, selected_support = before, baseline_support
    selected_comparison = compare(development["rows"], judged, before, selected, failed)
    if selected_comparison["regressions"]:
        raise AuditError("Guarded partition retains a development-reference regression")
    for label, item in comparison["summary"].items():
        item["selected"] = selected_comparison["summary"][label]["candidate"]
    selected_rows = {row["pair_id"]: row for row in selected_comparison["rows"]}
    for row in comparison["rows"]:
        row["selected_together"] = selected_rows[row["pair_id"]]["candidate_together"]
        row["selected_development_regression"] = selected_rows[row["pair_id"]]["development_regression"]
    comparison["vetoed_components"] = vetoed_components
    comparison["component_vetoes"] = vetoes
    comparison["selected_regressions"] = selected_comparison["regressions"]
    reference_artifact = base._save(engine, session, comparison, "Required all-reference weighted comparison including uncertain, missing and regressions")
    owners = _owners(selected)
    original_owners = _owners(before)
    selected_bridges = [edge for edge in edges if owners[edge["left"]] != owners[edge["right"]]]
    bridge_degree = Counter(source for row in selected_bridges for source in (row["left"], row["right"]))
    sizes = {row["group_id"]: len(row["members"]) for row in selected}
    updated_articles = [{**row, "previous_group_id": row["group_id"], "group_id": owners.get(row["source_version"]),
        "status": ("provisional" if sizes[owners[row["source_version"]]] > 1 else "review_singleton") if row["source_version"] in owners else row["status"],
        "bridge_count": bridge_degree[row["source_version"]]} for row in articles]

    def enrich(groups: list[Json]) -> list[Json]:
        return [{**group, "status": "provisional" if len(group["members"]) > 1 else "review_singleton", "accepted": False,
            "articles": [{key: article_map[source].get(key) for key in ("source_version", "title", "url", "published_at")}
                         for source in group["members"]]} for group in groups]

    lineage = _lineage(before, selected)
    directory = Path(data["output_directory"])
    exports = {"articles": previous._export(engine, session, directory, "articles.json", updated_articles),
        "groups": previous._export(engine, session, directory, "groups.json", enrich(selected)),
        "candidate_groups": previous._export(engine, session, directory, "candidate-groups.json", enrich(after)),
        "bridges": previous._export(engine, session, directory, "bridges.json", selected_bridges),
        "lineage": previous._export(engine, session, directory, "group-lineage.json", lineage),
        "reference_comparison": previous._export(engine, session, directory, "development-comparison.json", comparison)}
    baseline_counts = _counts(before, replay["bridges"], len(edges), proposal["diagnostics"]["baseline_objective"])
    candidate_counts = _counts(after, proposal["bridges"], len(edges), proposal["diagnostics"]["objective"])
    selected_counts = _counts(selected, selected_bridges, len(edges), selected_support)
    example_partition = selected if adopted else after
    changed_group_ids = {row["group_id"] for row in _lineage(before, example_partition) if row["relationship"] != "unchanged"}
    examples = [{"group_id": group["group_id"], "article_count": len(group["members"]),
        "articles": [article_map[source] for source in group["members"][:2]]}
        for group in sorted(example_partition, key=lambda row: (-len(row["members"]), row["group_id"]))
        if group["group_id"] in changed_group_ids and len(group["members"]) > 1][:2]
    result = {"versions": versions, "manifest": manifest_id, "parent_result": data["parent_result"], "plan": parent["plan"],
        "frozen_candidate": candidate_id, "adopted": adopted,
        "status": "adopted_provisional_refinement" if adopted else "candidate_kept_for_review",
        "baseline": baseline_counts, "candidate": candidate_counts, "selected": selected_counts,
        "vetoed_components": vetoed_components, "selected_reference_regressions": selected_comparison["regressions"],
        "component_vetoes": vetoes,
        "selected_membership_changed": sum(owners[source] != original_owners[source] for source in eligible),
        "diagnostics": proposal["diagnostics"], "algorithm_seconds": algorithm_seconds,
        "reference_summary": comparison["summary"], "reference_regressions": comparison["regressions"],
        "changed_reference_pairs": comparison["changed"], "reference_artifact": reference_artifact,
        "changed_reference_examples": [{"label": row["reference"]["label"], "before": row["baseline_together"],
            "after": row["candidate_together"], "selected": row["selected_together"], "regression": row["development_regression"],
            "articles": [article_map[row["left"]], article_map[row["right"]]]} for row in comparison["changed"]],
        "reference_versions": reference_versions, "original_reference_result": original_reference,
        "reference_pairs": len(comparison["rows"]), "reference_unprocessed": sum(row["processing_status"] != "completed" for row in comparison["rows"]),
        "dataset_articles": parent["dataset_articles"], "vector_articles": parent["vector_articles"],
        "missing_vector_articles": parent["missing_vector_articles"], "missing_date_articles": parent["missing_date_articles"],
        "reused_scored_pairs": len(scored), "failed_feature_pairs": len(failed), "pending_pairs": 0,
        "rule": parent["rule"], "validation_status": parent["validation_status"], "development_metrics": parent["development_metrics"],
        "exports": exports, "examples": examples, "new_model_calls": 0, "new_embedding_requests": 0, "accepted_dossiers": 0,
        "heldout_labels_opened": 0, "human_validated": False, "started_at": manifest["started_at"], "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_group_refinement_result", key, result)
    return _present(engine, session, context, identifier, result)


def render(result: Json) -> str:
    lines = [f"Grouping refinement: **{'adopted provisionally' if result['adopted'] else 'baseline retained; candidate available for review'}** across {result['dataset_articles']:,} pilot articles.", "",
        "| Metric | Previous | Candidate | Applied |", "|---|---:|---:|---:|"]
    for name, title in (("multi_article_groups", "Multi-article groups"), ("grouped_articles", "Grouped articles"),
                        ("singletons", "Review singletons"), ("internal_edges", "Passing links kept within groups"),
                        ("bridge_edges", "Cross-group review bridges"), ("objective", "Duplicate-discounted graph support")):
        old, new, selected = result["baseline"][name], result["candidate"][name], result["selected"][name]
        lines.append(f"| {title} | {old:,.4f} | {new:,.4f} | {selected:,.4f} |" if name == "objective" else f"| {title} | {old:,} | {new:,} | {selected:,} |")
    lines += ["", f"Applied membership changed for {result['selected_membership_changed']:,} articles ({result['diagnostics']['moved_articles']:,} in the full candidate); "
        f"{result['diagnostics']['passes']} refinement passes, converged: {result['diagnostics']['converged']}. "
        f"Refinement computation took {result['algorithm_seconds']:.2f}s, excluding preflight, loading and audit/export work.", "",
        f"Reused all {result['reference_pairs']} existing development model references after freezing the candidate:", "",
        "| Model reference | Total | Previously together | Candidate together | Applied together | Unprocessed |", "|---|---:|---:|---:|---:|---:|"]
    for label, row in result["reference_summary"].items():
        lines.append(f"| {label} | {row['total']} | {row['baseline']['together']} | {row['candidate']['together']} | {row['selected']['together']} | {row['candidate']['unprocessed']} |")
    lines += ["", f"Candidate development regressions: {len(result['reference_regressions'])}; {result['vetoed_components']} connected components retained their baseline. "
        f"Applied regressions: {len(result['selected_reference_regressions'])}. Changed candidate reference pairs: {len(result['changed_reference_pairs'])}. "
        "All weights, uncertainty and changed pairs are retained in the audit. This is reused development evidence; event accuracy remains unvalidated.",
        f"Coverage: {result['vector_articles']:,} articles with vectors; {result['missing_vector_articles']:,} without; "
        f"{result['missing_date_articles']:,} vector-bearing articles lack usable dates. Reused {result['reused_scored_pairs']:,} scored pairs; "
        f"feature failures {result['failed_feature_pairs']}, pending {result['pending_pairs']}. No new embeddings/model calls; accepted dossiers **0**.", "",
        "All five cutoffs and the seven-day publication gate are unchanged. Every within-group pair must pass. "
        "The cutoff's earlier development failure remains; graph-support improvement does not establish correct real-world events.", "",
        f"Changed-group examples ({'applied' if result['adopted'] else 'candidate for review'}, source titles only):", ""]
    from .rag_answers import _link
    for item in result["examples"]:
        lines.append(f"- {item['article_count']} articles: " + "; ".join(_link(article.get('title') or article['source_version'], article.get('url')) for article in item['articles']))
    if not result["examples"]:
        lines.append("- No changed multi-article group.")
    if result["changed_reference_examples"]:
        lines += ["", "All changed development-reference pairs:", ""]
        for item in result["changed_reference_examples"]:
            links = "; ".join(_link(article.get('title') or article['source_version'], article.get('url')) for article in item['articles'])
            lines.append(f"- {item['label']}: together previous {item['before']}, candidate {item['after']}, applied {item['selected']}; candidate regression {item['regression']}. {links}")
    lines += ["", "[Updated groups](" + result["exports"]["groups"]["path"].replace('\\', '/') + ") · "
        "[All article dispositions](" + result["exports"]["articles"]["path"].replace('\\', '/') + ") · "
        "[Complete development comparison](" + result["exports"]["reference_comparison"]["path"].replace('\\', '/') + ")"]
    return "\n".join(lines)
