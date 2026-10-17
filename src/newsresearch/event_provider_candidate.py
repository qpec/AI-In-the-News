"""Audited exact-provider metadata splits; identifiers are protected, not gold."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .common import AuditError, Context, Json, ResearchError, digest, require_no_credentials, utc
from .event_precision_candidate import GROUP_RESULT, _save, split_candidate
from .runtime import Research, audited_handler

METHOD = "provider-anchored-event-split-v1"
PARENT_CANDIDATE = "c5627181294c9d267561b1d75e9adb8f17c041343ec3d73573a055d215b5e8d2"
SQL = """SELECT id,json_type(payload,'$.raw_record.eventUri') AS uri_type,
json_extract(payload,'$.raw_record.eventUri') AS event_uri FROM sources
WHERE id IN (SELECT value FROM json_each(?)) ORDER BY id"""


def _counts(groups: list[Json]) -> Json:
    sizes = [len(group["members"]) for group in groups]
    return {"groups": len(sizes), "multi_article_groups": sum(size > 1 for size in sizes),
            "grouped_articles": sum(size for size in sizes if size > 1), "singletons": sizes.count(1),
            "within_pairs": sum(size * (size - 1) // 2 for size in sizes),
            "group_size_counts": {str(size): count for size, count in sorted(Counter(sizes).items())}}


def provider_split(groups: Json, metadata: list[Json]) -> Json:
    """Split a caller-validated baseline by exact strings; unknowns stay separate."""
    ids = sorted(source for members in groups.values() for source in members)
    if len(ids) != len(set(ids)):
        raise AuditError("provider_candidate_duplicate_source")
    rows = {row["id"]: row for row in metadata}
    if len(rows) != len(metadata) or set(rows) - set(ids):
        raise AuditError("provider_candidate_metadata_scope_changed")
    providers: Json = {}
    statuses: Counter[str] = Counter()
    for source in ids:
        row = rows.get(source)
        kind, value = (row.get("uri_type"), row.get("event_uri")) if row else (None, None)
        status = "source_missing" if row is None else "missing" if kind is None else "null" if kind == "null" else (
            "populated" if kind == "text" and isinstance(value, str) and value.strip() else
            "empty_string" if kind == "text" and isinstance(value, str) else "nonstring")
        providers[source] = {"provider_event_uri": value if status == "populated" else None, "coverage_status": status}
        statuses[status] += 1
    require_no_credentials(providers)
    output, lineage = [], []
    for parent, members in sorted(groups.items()):
        buckets: dict[tuple[str, str], list[str]] = {}
        for source in sorted(members):
            value = providers[source]["provider_event_uri"]
            bucket = ("provider", value) if value is not None else ("unknown", source)
            buckets.setdefault(bucket, []).append(source)
        for (kind, _), sources in sorted(buckets.items()):
            identity = parent if sources == sorted(members) else digest({"method": METHOD, "parent": parent, "members": sources})
            output.append({"group_id": identity, "members": sources, "provider_status": "available" if kind == "provider" else "unknown"})
            lineage.append({"group_id": identity, "parent_group": parent,
                            "relationship": "unchanged" if sources == sorted(members) else "split"})
    baseline = _counts([{"members": members} for members in groups.values()])
    candidate = _counts(output)
    pair_fraction = candidate["within_pairs"] / baseline["within_pairs"] if baseline["within_pairs"] else None
    article_fraction = candidate["grouped_articles"] / baseline["grouped_articles"] if baseline["grouped_articles"] else None
    return {"groups": output, "lineage": lineage, "provider_map": providers,
            "metadata_counts": {status: statuses[status] for status in ("populated", "missing", "null", "empty_string", "nonstring", "source_missing")},
            "baseline": baseline, "candidate": candidate, "all_source_count": len(ids),
            "retained_pairs_fraction": pair_fraction, "grouped_article_retention_fraction": article_fraction,
            "coverage_guard_passed": bool(pair_fraction is not None and pair_fraction >= .60 and article_fraction is not None and article_fraction >= .70)}


def render(result: Json) -> str:
    before, after = result["baseline"], result["candidate"]
    pairs = f"{result['retained_pairs_fraction']:.1%}" if result["retained_pairs_fraction"] is not None else "unavailable"
    articles = f"{result['grouped_article_retention_fraction']:.1%}" if result["grouped_article_retention_fraction"] is not None else "unavailable"
    lines = ["Provider-anchored seven-day split candidate prepared — **unjudged; original memberships unchanged**.", "",
             "| Metric | Original guarded groups | Provider candidate |", "|---|---:|---:|"]
    for key, title in (("multi_article_groups", "Multi-article groups"), ("grouped_articles", "Grouped articles"),
                       ("singletons", "Review singletons"), ("within_pairs", "Within-group pairs")):
        lines.append(f"| {title} | {before[key]:,} | {after[key]:,} |")
    lines.extend(["", f"Metadata coverage over {result['all_source_count']:,} articles: {result['metadata_counts']}. "
                  f"Unknown-provider articles: {result['unknown_provider_articles']:,}. Missing features {result['missing_feature_pairs']}; pending preparation 0.",
                  f"Pair retention {pairs}; grouped-article retention {articles}. Candidate sizes: {after['group_size_counts']}. "
                  f"Coverage guard (60% pairs and 70% grouped articles): **{'passes' if result['coverage_guard_passed'] else 'does not meet guard'}**.",
                  "Only exact, nonblank provider-event strings join articles inside an original guarded group. Strings are not normalized. "
                  "Unavailable metadata remains uncertain singletons, never different-event judgments. Original five feature gates and the seven-day rule are inherited; no extra margin.",
                  "Provider agreement is a metadata aid, not human gold or proof of event identity. **Precision remains unavailable.** "
                  "No labels selected this candidate; no model queue or approval was prepared, and no memberships were adopted.",
                  "Provider identifiers, full mapping, candidate groups and split lineage remain protected. No parent reads, model calls, embeddings or network requests; paid inference cost USD 0.",
                  "", "Algorithmic split examples (source links only):"])
    for example in result["examples"]:
        links = "; ".join(f"[{article.get('title') or article['source_version']}]({article['url']})" if article.get("url") else article["source_version"]
                          for article in example["articles"])
        lines.append(f"- {example['original_size']} articles → subgroup sizes {example['candidate_sizes']}. {links}")
    if not result["examples"]:
        lines.append("- No original group split.")
    return "\n".join(lines)


class ProviderCandidateResearch(Research):
    @audited_handler
    def _refine_event_groups(self, session: str, context: Context, data: Json) -> Json:
        if (set(data) != {"phase", "comparison_key", "user_instruction"} or data.get("phase") != "prepare_provider_candidate"
                or not self.config.offline or any(not isinstance(value, str) or not value.strip() for value in data.values())):
            raise ResearchError("provider_candidate_exact_offline_inputs_required")
        parent = self.ledger.get(PARENT_CANDIDATE, "event_group_refinement_result")
        if parent.get("method") != "fixed-margin-event-split-v1" or parent.get("baseline_group_result") != GROUP_RESULT or parent.get("unchanged_original_memberships") is not True:
            raise AuditError("provider_candidate_parent_binding_changed")
        if context.versions and context.versions != parent["versions"]:
            raise ResearchError("provider_candidate_context_differs")
        method = {"method": METHOD, "parent_candidate": PARENT_CANDIDATE, "capsule": parent["capsule"],
                  "input_versions": parent["versions"], "original_evaluation_plan": parent["original_evaluation_plan"],
                  "baseline_group_result": GROUP_RESULT, "sql": SQL,
                  "selection": "All frozen capsule members; exact provider-event URI strings; missing/null/empty/nonstring/source-missing stay uncertain singletons",
                  "candidate": "Split within original groups only; original five gates and seven days unchanged; no additional margin",
                  "coverage_guard": {"minimum_pair_retention": .60, "minimum_grouped_article_retention": .70},
                  "new_models": 0, "evaluation_labels_accessed": 0, "reference_labels_used_for_selection": 0,
                  "user_instruction": data["user_instruction"], "observed_chat_timestamp": None,
                  "implementation": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                     for name in (Path(__file__).name, "event_precision_candidate.py", "event_rule_application.py", "event_pair_monotone.py", "event_pair_selection.py")}}
        key = data["comparison_key"]
        prior = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_provider_candidate_manifest' AND logical_key=?", (key,)).fetchall()
        if prior:
            if len(prior) != 1 or json.loads(prior[0][1])["method"] != method:
                raise ResearchError("provider_candidate_immutable_method_changed")
            manifest_id, manifest = prior[0][0], json.loads(prior[0][1])
            versions = manifest["versions"]
        else:
            versions = dict(parent["versions"])
            for kind in ("protocol", "question", "selection", "dossier_definition", "profile"):
                versions[kind] = self._version(session, Context(context.objective, context.actor, versions), {"kind": kind, "key": key,
                    "content": {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                                "text": "Prepare an exact provider-event metadata split candidate", "rules": method["selection"],
                                "unit": "Provisional reports of one real-world event; provider equality is not gold"}})["id"]
            manifest = {"method": method, "versions": versions, "registered_at": utc()}
            manifest_id = self.ledger.record(session, "event_provider_candidate_manifest", key, manifest)
        bound = Context(context.objective, context.actor, versions)
        prior = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_group_refinement_result' AND logical_key=?", (key,)).fetchall()
        if prior:
            if len(prior) != 1 or json.loads(prior[0][1]).get("manifest") != manifest_id:
                raise AuditError("provider_candidate_completed_binding_changed")
            identifier, result = prior[0][0], json.loads(prior[0][1])
            self.ledger.append(session, "analysis.cache_reused", {"result": identifier, "basis": "exact_version_completed_provider_split"})
        else:
            self.ledger.append(session, "provider_candidate.capsule_read.intended", {"manifest": manifest_id, "capsule": parent["capsule"]})
            capsule = self.ledger.artifacts.read(parent["capsule"])
            if capsule.get("method") != "fixed-margin-event-split-v1" or capsule.get("original_rule") != parent["original_rule"]:
                raise AuditError("provider_candidate_capsule_binding_changed")
            checked = split_candidate(capsule["groups"], capsule["feature_rows"], capsule["original_rule"])
            ids = sorted(source for members in capsule["groups"].values() for source in members)
            query = {"sql": SQL, "parameters": [json.dumps(ids)], "versions": versions,
                     "source_count": len(ids), "purpose": "Stored provider event identifiers only; no article body or labels"}
            query_ref = _save(self, session, query, "Exact provider metadata SQL and parameters before execution")
            self.ledger.append(session, "provider_candidate.metadata_read.intended", {"manifest": manifest_id, "query": query_ref})
            metadata = [dict(zip(("id", "uri_type", "event_uri"), row, strict=True)) for row in self.ledger.db.execute(SQL, query["parameters"])]
            proposal = provider_split(capsule["groups"], metadata)
            if proposal["baseline"] != parent["baseline"] or proposal["all_source_count"] != parent["all_source_count"] or checked["source_count"] != len(ids):
                raise AuditError("provider_candidate_original_scope_changed")
            metadata_ref = _save(self, session, {"query": query_ref, "raw_rows": metadata, "source_to_provider": proposal["provider_map"]},
                                 "Protected exact provider identifiers and coverage states; never public output")
            proposal_ref = _save(self, session, {key: value for key, value in proposal.items() if key != "provider_map"},
                                 "Complete provider candidate partition, lineage and uncertainty; original groups unchanged")
            membership_ref = _save(self, session, {source: group["group_id"] for group in proposal["groups"] for source in group["members"]},
                                   "Frozen provider candidate membership; no adoption")
            examples = []
            lineage = {row["group_id"]: row["parent_group"] for row in proposal["lineage"]}
            for original, members in sorted(capsule["groups"].items(), key=lambda item: (-len(item[1]), item[0])):
                sizes = [len(group["members"]) for group in proposal["groups"] if lineage[group["group_id"]] == original]
                if len(sizes) > 1:
                    examples.append({"original_size": len(members), "candidate_sizes": sizes,
                                     "articles": [{field: capsule["articles"][source].get(field) for field in ("source_version", "title", "url")} for source in members[:2]]})
                if len(examples) == 2:
                    break
            result = {"method": METHOD, "versions": versions, "manifest": manifest_id, "parent_candidate": PARENT_CANDIDATE,
                      "capsule": parent["capsule"], "candidate_artifact": proposal_ref, "provider_metadata_artifact": metadata_ref,
                      "candidate_membership": membership_ref, "original_evaluation_plan": parent["original_evaluation_plan"],
                      "baseline_group_result": GROUP_RESULT, "all_source_count": len(ids), "source_count": len(ids),
                      "unchanged_original_memberships": True, "original_memberships_changed": False, "adopted": False,
                      "baseline": proposal["baseline"], "candidate": proposal["candidate"], "metadata_counts": proposal["metadata_counts"],
                      "unknown_provider_articles": len(ids) - proposal["metadata_counts"]["populated"],
                      "retained_pairs_fraction": proposal["retained_pairs_fraction"],
                      "grouped_article_retention_fraction": proposal["grouped_article_retention_fraction"],
                      "grouped_article_fraction": proposal["candidate"]["grouped_articles"] / len(ids),
                      "coverage_guard_passed": proposal["coverage_guard_passed"], "original_rule": capsule["original_rule"],
                      "rule": capsule["original_rule"], "delta": None, "gatekind": "provider", "precision": None,
                      "status": "provider_candidate_unjudged" if proposal["coverage_guard_passed"] else "provider_candidate_below_coverage_guard",
                      "missing_feature_pairs": checked["missing_feature_pairs"], "baseline_replay_passed": True,
                      "new_model_calls": 0, "new_embedding_requests": 0, "new_network_calls": 0, "external_parent_reads": 0,
                      "evaluation_labels_accessed": 0, "reference_labels_used_for_selection": 0, "paid_inference_cost_usd": "0",
                      "model_queue_prepared": False, "human_validated": False, "accepted_dossiers": 0,
                      "import_provenance": parent["import_provenance"], "examples": examples, "completed_at": utc()}
            identifier = self.ledger.record(session, "event_group_refinement_result", key, result)
        presentation = self._record_presentation(session, bound, {"results": [{"kind": "event_group_refinement_result", "id": identifier}],
                                                                "markdown": render(result), "destination": "codex_chat"})
        return {"id": identifier, **result, "presentation": presentation}
