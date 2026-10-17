"""One offline, label-blind coverage grid over the already retained capsule."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import hashlib
import json
from pathlib import Path

from .common import AuditError, Context, Json, ResearchError, digest, utc
from .event_pair_monotone import predicts
from .event_precision_candidate import APPLICATION_RESULT, GROUP_RESULT, _save, split_candidate
from .event_rule_application import complete_link_groups
from .runtime import Research, audited_handler

METHOD = "coverage-guarded-event-split-v2"
PARENT_CANDIDATE = "c5627181294c9d267561b1d75e9adb8f17c041343ec3d73573a055d215b5e8d2"
DELTAS = (0., .025, .05, .075, .1, .15, .2, .25)
MIN_PAIR_RETENTION = .60
MIN_GROUPED_RETENTION = .70


def coverage_grid(groups: Json, rows: list[Json], rule: Json) -> Json:
    """Validate delta zero once, then compare only the registered finite grid."""
    checked = split_candidate(groups, rows, rule)
    baseline = {**checked["baseline"], "group_size_counts": {
        str(size): count for size, count in checked["baseline"]["group_size_counts"].items()}}
    features = {(row["left"], row["right"]): row for row in checked["feature_rows"]}
    variants: list[Json] = []
    for delta in DELTAS:
        candidate_rule = {**rule, "thresholds": [cut + delta * (1 - cut) for cut in rule["thresholds"]]}
        proposed = []
        for parent, members in sorted(groups.items()):
            members = sorted(members)
            passing = [features[(left, right)] for left, right in combinations(members, 2)
                       if predicts(features[(left, right)], candidate_rule)]
            for group in complete_link_groups(members, passing)["groups"]:
                identity = parent if group["members"] == members else digest({
                    "method": METHOD, "delta": delta, "parent": parent, "members": group["members"]})
                proposed.append({"group_id": identity, "members": group["members"], "parent_group": parent})
        sizes = [len(group["members"]) for group in proposed]
        counts = {"groups": len(sizes), "multi_article_groups": sum(size > 1 for size in sizes),
                  "grouped_articles": sum(size for size in sizes if size > 1), "singletons": sizes.count(1),
                  "within_pairs": sum(size * (size - 1) // 2 for size in sizes),
                  "group_size_counts": {str(size): count for size, count in sorted(Counter(sizes).items())}}
        pair_retention = counts["within_pairs"] / baseline["within_pairs"] if baseline["within_pairs"] else None
        article_retention = counts["grouped_articles"] / baseline["grouped_articles"] if baseline["grouped_articles"] else None
        eligible = bool(delta > 0 and pair_retention is not None and pair_retention >= MIN_PAIR_RETENTION
                        and article_retention is not None and article_retention >= MIN_GROUPED_RETENTION)
        variants.append({"delta": delta, "rule": candidate_rule, "groups": proposed, "counts": counts,
                         "retained_pairs_fraction": pair_retention, "grouped_article_retention_fraction": article_retention,
                         "eligible": eligible})
    selected = max((variant for variant in variants if variant["eligible"]), key=lambda variant: variant["delta"], default=None)
    if variants[0]["counts"] != baseline:
        raise AuditError("coverage_candidate_delta_zero_counts_changed")
    return {"baseline": baseline, "variants": variants, "selected": selected,
            "all_source_count": checked["source_count"], "retained_feature_rows": len(checked["feature_rows"]),
            "missing_feature_pairs": checked["missing_feature_pairs"], "baseline_replay_passed": True}


def render(result: Json) -> str:
    lines = ["Coverage-guarded seven-day split grid prepared — **unjudged; original memberships unchanged**.", "",
             "| Normalized margin delta | Within pairs | Pair retention | Grouped articles | Article retention | Eligible |",
             "|---:|---:|---:|---:|---:|---|"]
    for row in result["variant_summary"]:
        pairs = f"{row['retained_pairs_fraction']:.1%}" if row["retained_pairs_fraction"] is not None else "unavailable"
        articles = f"{row['grouped_article_retention_fraction']:.1%}" if row["grouped_article_retention_fraction"] is not None else "unavailable"
        lines.append(f"| {row['delta']} | {row['counts']['within_pairs']:,} | {pairs} | {row['counts']['grouped_articles']:,} | {articles} | {'yes' if row['eligible'] else 'no'} |")
    if result["delta"] is None:
        lines.extend(["", "**No positive margin met both coverage requirements. No candidate was selected.**"])
    else:
        counts = result["candidate"]
        lines.extend(["", f"Selected the largest eligible delta: **{result['delta']}**; at least 60% of original within pairs and 70% of originally grouped articles retained.",
                      f"Candidate: {counts['multi_article_groups']:,} multi-article groups, {counts['singletons']:,} review singletons; sizes {counts['group_size_counts']}."])
    lines.extend(["", f"Scope: {result['all_source_count']:,} frozen articles; {result['retained_feature_rows']:,} original internal feature rows; missing feature pairs {result['missing_feature_pairs']}; pending preparation 0. Baseline replay passed.",
                  "Each subgroup requires every pair to pass all five stricter cutoffs and the original seven-day gate. Only splits inside current groups are proposed.",
                  "**Precision remains unavailable.** The fixed grid and coverage rule use no evaluation or historical-reference labels. Fresh evaluation remains necessary; no membership adoption occurred.",
                  "All variants and any selected membership are frozen in protected artifacts. New parent reads/model calls/embeddings/network requests: **0/0/0/0**; paid inference cost USD 0.",
                  "", "Selected split examples (algorithmic proposals, no new event judgments):"])
    for example in result["examples"]:
        links = "; ".join(f"[{article.get('title') or article['source_version']}]({article['url']})" if article.get("url")
                          else article["source_version"] for article in example["articles"])
        lines.append(f"- {example['original_size']} articles → subgroup sizes {example['candidate_sizes']}. {links}")
    if not result["examples"]:
        lines.append("- No selected changed group.")
    return "\n".join(lines)


class CoverageCandidateResearch(Research):
    @audited_handler
    def _refine_event_groups(self, session: str, context: Context, data: Json) -> Json:
        if (set(data) != {"phase", "parent_candidate", "comparison_key", "user_instruction"}
                or data.get("phase") != "prepare_coverage_grid" or data.get("parent_candidate") != PARENT_CANDIDATE
                or not self.config.offline or any(not isinstance(value, str) or not value.strip() for value in data.values())):
            raise ResearchError("coverage_candidate_exact_offline_inputs_required")
        parent = self.ledger.get(PARENT_CANDIDATE, "event_group_refinement_result")
        if (parent.get("method") != "fixed-margin-event-split-v1" or parent.get("delta") != .25
                or parent.get("baseline_group_result") != GROUP_RESULT or parent.get("unchanged_original_memberships") is not True
                or parent.get("adopted") is not False or parent.get("accepted_dossiers") != 0):
            raise AuditError("coverage_candidate_parent_binding_changed")
        if context.versions and context.versions != parent["versions"]:
            raise ResearchError("coverage_candidate_context_differs_from_parent")
        method = {"method": METHOD, "parent_candidate": PARENT_CANDIDATE, "capsule": parent["capsule"],
                  "original_evaluation_plan": parent["original_evaluation_plan"], "baseline_group_result": GROUP_RESULT,
                  "input_versions": parent["versions"], "deltas": list(DELTAS), "minimum_pair_retention": MIN_PAIR_RETENTION,
                  "minimum_originally_grouped_article_retention": MIN_GROUPED_RETENTION,
                  "selection": "Largest positive delta satisfying both coverage floors; otherwise no candidate",
                  "source_scope": "Exact retained capsule; baseline replay; complete-link splits only; seven-day gate unchanged",
                  "reference_labels_used_for_selection": 0, "evaluation_labels_accessed": 0,
                  "external_parent_reads": 0, "new_model_calls": 0, "user_instruction": data["user_instruction"],
                  "observed_chat_timestamp": None,
                  "implementation": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in (
                      Path(__file__).name, "event_precision_candidate.py", "event_rule_application.py", "event_pair_monotone.py", "event_pair_selection.py")}}
        key = data["comparison_key"]
        previous = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_coverage_candidate_manifest' AND logical_key=?", (key,)).fetchall()
        if previous:
            if len(previous) != 1 or json.loads(previous[0][1])["method"] != method:
                raise ResearchError("coverage_candidate_key_binds_another_immutable_method")
            manifest_id, manifest = previous[0][0], json.loads(previous[0][1])
            versions = manifest["versions"]
        else:
            versions = dict(parent["versions"])
            for kind in ("protocol", "question", "selection", "dossier_definition", "profile"):
                versions[kind] = self._version(session, Context(context.objective, context.actor, versions), {
                    "kind": kind, "key": key, "content": {**method, "binding_role": kind, "mode": "exploratory",
                        "population_estimate": False, "text": "Prepare a fixed margin grid with predeclared coverage floors",
                        "rules": method["source_scope"], "unit": "Provisional reports of one real-world event"}})["id"]
            manifest = {"method": method, "versions": versions, "registered_at": utc()}
            manifest_id = self.ledger.record(session, "event_coverage_candidate_manifest", key, manifest)
        bound = Context(context.objective, context.actor, versions)
        previous_results = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_group_refinement_result' AND logical_key=?", (key,)).fetchall()
        if previous_results:
            if len(previous_results) != 1 or json.loads(previous_results[0][1]).get("manifest") != manifest_id:
                raise AuditError("coverage_candidate_completed_binding_changed")
            identifier, result = previous_results[0][0], json.loads(previous_results[0][1])
            self.ledger.append(session, "analysis.cache_reused", {"result": identifier, "basis": "exact_version_completed_coverage_grid"})
        else:
            self.ledger.append(session, "coverage_candidate.capsule_read.intended", {"manifest": manifest_id, "capsule": parent["capsule"]})
            capsule = self.ledger.artifacts.read(parent["capsule"])
            if (capsule.get("method") != "fixed-margin-event-split-v1" or capsule.get("original_rule") != parent["original_rule"]
                    or capsule.get("parameters") != [GROUP_RESULT, APPLICATION_RESULT]):
                raise AuditError("coverage_candidate_retained_capsule_binding_changed")
            output = coverage_grid(capsule["groups"], capsule["feature_rows"], capsule["original_rule"])
            if output["all_source_count"] != parent["all_source_count"] or output["baseline"] != parent["baseline"]:
                raise AuditError("coverage_candidate_original_scope_changed")
            variants_artifact = _save(self, session, {"method": METHOD, "manifest": manifest_id, "variants": output["variants"]},
                                      "All predeclared coverage variants frozen without label access")
            selected = output["selected"]
            membership_artifact = None
            if selected is not None:
                membership_artifact = _save(self, session, {source: group["group_id"] for group in selected["groups"] for source in group["members"]},
                                            "Selected fixed coverage-guarded candidate membership; no adoption")
            examples = []
            if selected is not None:
                for original, members in sorted(capsule["groups"].items(), key=lambda item: (-len(item[1]), item[0])):
                    sizes = [len(group["members"]) for group in selected["groups"] if group["parent_group"] == original]
                    if len(sizes) > 1:
                        examples.append({"original_group": original, "original_size": len(members), "candidate_sizes": sizes,
                                         "articles": [{field: capsule["articles"][source].get(field) for field in ("source_version", "title", "url")}
                                                      for source in members[:2]]})
                    if len(examples) == 2:
                        break
            result = {"method": METHOD, "versions": versions, "manifest": manifest_id, "parent_candidate": PARENT_CANDIDATE,
                      "capsule": parent["capsule"], "candidate_membership": membership_artifact,
                      "original_evaluation_plan": parent["original_evaluation_plan"], "baseline_group_result": GROUP_RESULT,
                      "unchanged_original_memberships": True, "original_memberships_changed": False, "adopted": False,
                      "all_source_count": output["all_source_count"], "source_count": output["all_source_count"],
                      "baseline": output["baseline"], "candidate": selected["counts"] if selected else None,
                      "delta": selected["delta"] if selected else None, "rule": selected["rule"] if selected else None,
                      "original_rule": capsule["original_rule"], "variants_artifact": variants_artifact,
                      "variant_summary": [{field: row[field] for field in ("delta", "counts", "retained_pairs_fraction", "grouped_article_retention_fraction", "eligible")} for row in output["variants"]],
                      "retained_pairs_fraction": selected["retained_pairs_fraction"] if selected else None,
                      "grouped_article_retention_fraction": selected["grouped_article_retention_fraction"] if selected else None,
                      "grouped_article_fraction": selected["counts"]["grouped_articles"] / output["all_source_count"] if selected else None,
                      "retained_feature_rows": output["retained_feature_rows"], "missing_feature_pairs": output["missing_feature_pairs"],
                      "precision": None, "human_validated": False, "evaluation_labels_accessed": 0,
                      "reference_labels_used_for_selection": 0, "external_parent_reads": 0, "new_model_calls": 0,
                      "new_embedding_requests": 0, "new_network_calls": 0, "paid_inference_cost_usd": "0", "accepted_dossiers": 0,
                      "status": "coverage_guarded_candidate_unjudged" if selected else "no_coverage_guarded_candidate",
                      "import_provenance": parent["import_provenance"], "examples": examples, "completed_at": utc()}
            identifier = self.ledger.record(session, "event_group_refinement_result", key, result)
        presentation = self._record_presentation(session, bound, {"results": [{"kind": "event_group_refinement_result", "id": identifier}],
                                                                "markdown": render(result), "destination": "codex_chat"})
        return {"id": identifier, **result, "presentation": presentation}
