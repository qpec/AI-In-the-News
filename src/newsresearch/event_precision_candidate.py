"""Audited, content-anchored import and one label-blind split proposal.

The child verifies its complete own store. Two independently retained checkpoint
record IDs anchor the narrowly imported parent payloads and named artifacts; the
parent's complete journal, sources and unrelated objects are not reverified.
No labels, model calls, active memberships or existing approvals are changed.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import sqlite3
import time
from typing import Any

from .common import AuditError, Context, Json, ResearchError, canonical, digest, utc
from .event_pair_monotone import predicts
from .event_pair_selection import FEATURES
from .event_rule_application import complete_link_groups
from .runtime import Research, audited_handler
from .storage import check_permissions

METHOD = "fixed-margin-event-split-v1"
DELTA = .25
GROUP_RESULT = "1e803a0c84fe80ef441005687209364dd3302a3b0ab1f3e8169ea76f0e55600d"
APPLICATION_RESULT = "3fb0d5c5f4b05c9dec7f2270c36ef5a2fa4daeefbabbc5c3809a74ef35a1594e"
SQL = "SELECT id,kind,logical_key,artifact,payload,supersedes,created_event FROM records WHERE id IN (?,?) ORDER BY id"


def verified_record(row: Mapping[str, Any], expected_id: str, expected_kind: str) -> Json:
    """Verify a complete record against a caller-supplied retained content ID."""
    if row.get("id") != expected_id or row.get("kind") != expected_kind or not isinstance(row.get("payload"), str):
        raise AuditError("precision_candidate_record_anchor_mismatch")
    payload = json.loads(row["payload"])
    if (canonical(payload) != row["payload"]
            or hashlib.sha256(row["payload"].encode("utf-8")).hexdigest() != row.get("artifact")
            or digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"],
                       "supersedes": row["supersedes"]}) != expected_id):
        raise AuditError("precision_candidate_record_content_changed")
    return dict(payload)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def split_candidate(groups: Mapping[str, Sequence[str]], scored: Sequence[Json], rule: Json) -> Json:
    """Pure fixed-margin splitting, retaining all input members and uncertainty."""
    cuts = rule.get("thresholds")
    if (rule.get("features") != list(FEATURES) or rule.get("publication_gap_days") != 7
            or not isinstance(cuts, list) or len(cuts) != 5
            or any(not _finite(cut) or not -1 <= cut < 1 for cut in cuts)):
        raise AuditError("precision_candidate_original_seven_day_rule_required")
    original = {key: sorted(values) for key, values in groups.items()}
    owners: dict[str, str] = {}
    for key, members in original.items():
        if not isinstance(key, str) or not key or not members or len(set(members)) != len(members):
            raise AuditError("precision_candidate_invalid_group_frame")
        for source in members:
            if not isinstance(source, str) or not source or source in owners:
                raise AuditError("precision_candidate_invalid_membership")
            owners[source] = key
    internal: dict[tuple[str, str], Json] = {}
    for row in scored:
        left, right = row.get("left"), row.get("right")
        if left not in owners or right not in owners or owners[left] != owners[right]:
            continue
        pair = tuple(sorted((left, right)))
        if left == right or pair in internal or row.get("pair_id") != digest(list(pair)):
            raise AuditError("precision_candidate_duplicate_or_changed_pair")
        internal[pair] = dict(row)
    expected = sum(len(members) * (len(members) - 1) // 2 for members in original.values())
    if len(internal) != expected:
        raise AuditError("precision_candidate_missing_original_within_pair")
    missing = sum(row.get("status") != "completed"
                  or any(not _finite(row.get("features", {}).get(name)) for name in FEATURES)
                  or not _finite(row.get("publication_gap_days")) for row in internal.values())
    if missing or any(not predicts(row, rule) for row in internal.values()):
        raise AuditError("precision_candidate_original_clique_replay_failed")
    candidate_rule = {**rule, "thresholds": [cut + DELTA * (1 - cut) for cut in cuts]}
    output: list[Json] = []
    lineage: list[Json] = []
    removed: list[list[str]] = []
    for old_id, members in sorted(original.items()):
        rows = [internal[(left, right)] for left, right in combinations(members, 2)]
        replay = complete_link_groups(members, rows)
        if len(replay["groups"]) != 1 or replay["groups"][0]["members"] != members:
            raise AuditError("precision_candidate_delta_zero_did_not_replay")
        passed = [row for row in rows if row.get("status") == "completed" and predicts(row, candidate_rule)]
        proposed = complete_link_groups(members, passed)["groups"]
        candidate_owners = {source: group["group_id"] for group in proposed for source in group["members"]}
        for group in proposed:
            same = group["members"] == members
            group_id = old_id if same else digest({"method": METHOD, "parent": old_id, "members": group["members"]})
            output.append({"group_id": group_id, "members": group["members"]})
            lineage.append({"group_id": group_id, "parent_group": old_id,
                            "relationship": "unchanged" if same else "split"})
        removed.extend([left, right] for left, right in combinations(members, 2)
                       if candidate_owners[left] != candidate_owners[right])
    if sorted(source for group in output for source in group["members"]) != sorted(owners):
        raise AuditError("precision_candidate_changed_article_coverage")

    def counts(partition: Sequence[Mapping[str, Any]]) -> Json:
        sizes = [len(group["members"]) for group in partition]
        return {"groups": len(sizes), "multi_article_groups": sum(size > 1 for size in sizes),
                "grouped_articles": sum(size for size in sizes if size > 1), "singletons": sizes.count(1),
                "within_pairs": sum(size * (size - 1) // 2 for size in sizes),
                "group_size_counts": dict(sorted(Counter(sizes).items()))}
    before = counts([{"members": members} for members in original.values()])
    after = counts(output)
    return {"groups": output, "lineage": lineage, "rule": candidate_rule,
            "original_rule": rule, "baseline": before, "candidate": after,
            "source_count": len(owners), "retained_pairs_fraction": after["within_pairs"] / expected if expected else None,
            "grouped_article_fraction": after["grouped_articles"] / len(owners) if owners else None,
            "removed_within_pairs": removed, "feature_rows": list(internal.values()),
            "missing_feature_pairs": missing, "baseline_replay_passed": True,
            "original_memberships_changed": False, "precision": None,
            "precision_status": "Unjudged fixed candidate; fresh frozen evaluation and concrete approval required"}


def _save(engine: Research, session: str, value: Any, purpose: str) -> str:
    reference = engine.ledger.artifacts.put(value)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": purpose})
    return reference


def _checked_path(path: Path, *, root: bool = False) -> None:
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink() or ancestor.is_junction() or (ancestor / ".git").exists():
            raise AuditError("precision_candidate_external_path_must_be_protected")
    check_permissions(path, root=root)


def _read_artifact(parent: Path, reference: str) -> tuple[Any, int]:
    if (not isinstance(reference, str) or len(reference) != 64
            or any(char not in "0123456789abcdef" for char in reference)):
        raise AuditError("precision_candidate_invalid_artifact_reference")
    path = parent / "objects" / reference
    _checked_path(path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference:
        raise AuditError("precision_candidate_external_artifact_changed")
    return json.loads(raw), len(raw)


def _import(engine: Research, session: str, parent: Path, groups: Json, dataset: str) -> Json:
    _checked_path(parent, root=True)
    _checked_path(parent / "objects")
    _checked_path(parent / "research.sqlite3")
    sidecars = []
    for suffix in ("-wal", "-shm"):
        sidecar = parent / ("research.sqlite3" + suffix)
        if sidecar.exists() or sidecar.is_symlink() or sidecar.is_junction():
            _checked_path(sidecar)
            sidecars.append(sidecar.name)
    parameters = [GROUP_RESULT, APPLICATION_RESULT]
    engine.ledger.append(session, "precision_candidate.external_read.intended", {
        "workspace": str(parent), "sql": SQL, "parameters": parameters,
        "present_sqlite_sidecars_acl_and_links_checked": sidecars,
        "mode": "SQLite mode=ro snapshot; two exact retained record IDs; no parent preflight or journal verification"})
    connection = sqlite3.connect((parent / "research.sqlite3").as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        rows = {row["id"]: dict(row) for row in connection.execute(SQL, parameters)}
    finally:
        connection.close()
    if set(rows) != set(parameters):
        raise AuditError("precision_candidate_missing_retained_anchor")
    current = verified_record(rows[GROUP_RESULT], GROUP_RESULT, "event_group_refinement_result")
    application = verified_record(rows[APPLICATION_RESULT], APPLICATION_RESULT, "event_rule_application_result")
    if (current.get("parent_result") != APPLICATION_RESULT or current.get("rule") != application.get("rule")
            or current.get("status") != "adopted_provisional_refinement" or current.get("adopted") is not True
            or any(value.get("versions", {}).get("dataset") != dataset for value in (current, application))
            or any(value.get("accepted_dossiers") != 0 or value.get("pending_pairs") != 0 for value in (current, application))):
        raise AuditError("precision_candidate_retained_lineage_changed")
    imported, byte_count = {}, 0
    refs = {"groups": current["exports"]["groups"]["artifact"],
            "articles": current["exports"]["articles"]["artifact"], "scores": application["score_artifact"]}
    for name, reference in refs.items():
        engine.ledger.append(session, "precision_candidate.external_artifact.intended", {
            "parent_workspace": str(parent), "artifact": reference, "role": name,
            "anchor": APPLICATION_RESULT if name == "scores" else GROUP_RESULT})
        imported[name], size = _read_artifact(parent, reference)
        byte_count += size
    anchored_groups = {row["group_id"]: sorted(row["members"]) for row in imported["groups"]}
    if len(anchored_groups) != len(imported["groups"]) or anchored_groups != groups:
        raise AuditError("precision_candidate_plan_differs_from_guarded_membership")
    scored = imported["scores"]
    if (not isinstance(scored, list) or len(scored) != application["pooled_candidates"]
            or len({row["pair_id"] for row in scored}) != len(scored)):
        raise AuditError("precision_candidate_original_score_coverage_changed")
    proposal = split_candidate(groups, scored, current["rule"])
    ids = {source for members in groups.values() for source in members}
    articles = {row["source_version"]: row for row in imported["articles"] if row["source_version"] in ids}
    if set(articles) != ids:
        raise AuditError("precision_candidate_source_metadata_incomplete")
    capsule = {"method": METHOD, "retained_anchor_records": rows, "parent_workspace": str(parent),
               "external_sql": SQL, "parameters": parameters, "named_artifacts": refs,
               "full_named_artifact_bytes_verified": byte_count, "parent_archive_reverified": False,
               "parent_head_inclusion_proof": False, "scope": "Exact checkpoint content IDs and their named artifacts only",
               "groups": groups, "articles": articles, "feature_rows": proposal["feature_rows"],
               "original_rule": current["rule"], "imported_at": utc()}
    reference = _save(engine, session, capsule, "Narrow checkpoint-anchored inputs; only current internal feature rows retained")
    engine.ledger.append(session, "precision_candidate.external_read.completed", {
        "capsule": reference, "external_bytes_verified": byte_count, "retained_feature_rows": len(proposal["feature_rows"]),
        "parent_archive_reverified": False, "evaluation_labels_accessed": 0, "reference_labels_used_for_selection": 0})
    return {"capsule": reference, "proposal": proposal, "articles": articles, "external_bytes_verified": byte_count}


def render(result: Json) -> str:
    before, after = result["baseline"], result["candidate"]
    lines = ["Fixed seven-day split candidate prepared — **unjudged; original memberships unchanged**.", "",
             "| Metric | Original guarded groups | Candidate |", "|---|---:|---:|"]
    for name, title in (("multi_article_groups", "Multi-article groups"), ("grouped_articles", "Articles in multi-article groups"),
                        ("singletons", "Review singletons"), ("within_pairs", "Within-group article pairs")):
        lines.append(f"| {title} | {before[name]:,} | {after[name]:,} |")
    lines.extend(["", f"Scope: {result['source_count']:,} frozen articles; {result['retained_feature_rows']:,} exact internal feature rows. "
                  f"Missing features {result['missing_feature_pairs']}; pending preparation 0. Baseline delta-zero replay passed.",
                  f"Fixed normalized margin delta **{DELTA}**: each cutoff becomes t + 0.25 × (1 − t). "
                  "All five features and the seven-day gate must pass for every pair in each proposed subgroup. "
                  "Only splits inside existing groups are proposed; no similarity is treated as probability.",
                  f"Retained pair fraction: {result['retained_pairs_fraction']}; candidate grouped-article fraction: {result['grouped_article_fraction']}. "
                  f"Candidate size counts: {after['group_size_counts']}.",
                  "**Precision remains unavailable.** No evaluation labels, historical model references or human labels selected this candidate. "
                  "A fresh frozen evaluation and concrete approval are required. Whole-group purity and recall remain unvalidated.",
                  f"New models/embeddings/network requests: **0/0/0**; paid inference cost **USD0**. "
                  f"Verified {result['external_bytes_verified']:,} bytes from three exact parent artifacts. "
                  "The complete child preflight ran; the full parent archive/journal and parent-head inclusion were not reverified.",
                  "The complete candidate partition, split lineage, necessary feature rows and full-support frame inputs are frozen in protected artifacts.",
                  "", "Changed-group examples (algorithmic splits, no new event judgments):"])
    for example in result["examples"]:
        links = "; ".join(f"[{row.get('title') or row['source_version']}]({row['url']})" if row.get("url")
                          else row["source_version"] for row in example["articles"])
        lines.append(f"- {example['old_size']} articles → subgroup sizes {example['new_sizes']}. {links}")
    if not result["examples"]:
        lines.append("- No original group split under the fixed candidate rule.")
    return "\n".join(lines)


class PrecisionCandidateResearch(Research):
    """Add one audited offline phase without changing existing bound handlers."""

    @audited_handler
    def _refine_event_groups(self, session: str, context: Context, data: Json) -> Json:
        if (set(data) != {"phase", "plan", "comparison_key", "user_instruction"}
                or data.get("phase") != "prepare_precision_candidate" or not self.config.offline
                or any(not isinstance(data.get(key), str) or not data[key].strip() for key in data)):
            raise ResearchError("precision_candidate_offline_exact_inputs_required")
        plan = self.ledger.get(data["plan"], "luna_group_validation_plan")
        if plan.get("method") != "fast-event-pair-evaluation-v1" or plan.get("group_result") != GROUP_RESULT:
            raise ResearchError("precision_candidate_exact_original_evaluation_plan_required")
        if context.versions and context.versions != plan["versions"]:
            raise ResearchError("precision_candidate_context_differs_from_plan")
        old_plan = self.ledger.get(plan["original_plan"], "luna_group_validation_plan")
        row = self.ledger.db.execute("SELECT id FROM records WHERE kind='study_execution_ownership' AND logical_key=? ORDER BY created_event DESC LIMIT 1",
                                     (old_plan["study_key"],)).fetchone()
        if row is None:
            raise ResearchError("precision_candidate_original_child_owner_required")
        owner = self.ledger.get(row[0], "study_execution_ownership")
        if owner.get("status") != "imported_owner" or Path(owner["owner_workspace"]).resolve() != self.ledger.root.resolve():
            raise ResearchError("precision_candidate_use_original_owning_child")
        parent = Path(owner["parent_provenance"]["workspace"]).absolute()
        groups = {key: sorted(members) for key, members in plan["design"]["groups"].items()}
        if sum(map(len, groups.values())) != plan["source_count"]:
            raise AuditError("precision_candidate_plan_source_count_changed")
        method = {"method": METHOD, "plan": data["plan"], "input_versions": plan["versions"],
                  "source_frame_hash": digest(groups), "group_result": GROUP_RESULT, "application_result": APPLICATION_RESULT,
                  "parent_workspace": str(parent), "external_sql": SQL, "parameters": [GROUP_RESULT, APPLICATION_RESULT],
                  "content_identity": "Payload SHA256 and full original record identity match retained checkpoint ID; each named artifact fully hashed",
                  "parent_archive_reverified": False, "parent_head_inclusion_proof": False,
                  "margin_delta": DELTA, "rule": "t + 0.25*(1-t) on all five original features; seven-day gate unchanged",
                  "candidate": "Complete-link split inside each original group only; freeze one candidate, no adoption or label use",
                  "evaluation_labels_accessed": 0, "reference_labels_used_for_selection": 0,
                  "checkpoint_payload_note": "Full anchored checkpoint payloads include historical summaries; they are retained for content verification, not used for selection",
                  "new_models": 0, "new_embeddings": 0, "new_network_calls": 0,
                  "user_instruction": data["user_instruction"], "observed_chat_timestamp": None,
                  "implementation": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                     for name in (Path(__file__).name, "event_rule_application.py", "event_pair_monotone.py", "event_pair_selection.py")}}
        key = data["comparison_key"]
        existing = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_precision_candidate_manifest' AND logical_key=?", (key,)).fetchall()
        if existing:
            if len(existing) != 1 or json.loads(existing[0][1])["method"] != method:
                raise ResearchError("precision_candidate_key_binds_another_immutable_method")
            manifest_id, manifest = existing[0][0], json.loads(existing[0][1])
            versions = manifest["versions"]
        else:
            versions = dict(plan["versions"])
            for kind in ("protocol", "question", "selection", "dossier_definition", "profile"):
                content = {**method, "binding_role": kind, "mode": "exploratory", "population_estimate": False,
                           "text": "Prepare one fixed stricter event-group candidate for future fresh evaluation",
                           "rules": "Current frozen guarded seven-day membership; no new sources, labels or inference",
                           "unit": "Provisional same-real-world-event group; no accepted dossiers"}
                versions[kind] = self._version(session, Context(context.objective, context.actor, versions), {
                    "kind": kind, "key": key, "content": content})["id"]
            manifest = {"method": method, "versions": versions, "registered_at": utc()}
            manifest_id = self.ledger.record(session, "event_precision_candidate_manifest", key, manifest)
        bound = Context(context.objective, context.actor, versions)
        saved = self.ledger.db.execute("SELECT id,payload FROM records WHERE kind='event_group_refinement_result' AND logical_key=?", (key,)).fetchall()
        if saved:
            if len(saved) != 1 or json.loads(saved[0][1]).get("manifest") != manifest_id:
                raise AuditError("precision_candidate_completed_binding_changed")
            identifier, result = saved[0][0], json.loads(saved[0][1])
            self.ledger.append(session, "analysis.cache_reused", {"result": identifier, "basis": "exact_version_completed_fixed_split_candidate"})
        else:
            started = time.perf_counter()
            self.ledger.append(session, "precision_candidate.preparation.intended", {"manifest": manifest_id, "versions": versions})
            imported = _import(self, session, parent, groups, plan["versions"]["dataset"])
            proposal = imported["proposal"]
            candidate_artifact = _save(self, session, {key: value for key, value in proposal.items() if key != "feature_rows"},
                                       "Complete fixed candidate and split lineage; no evaluation labels read")
            membership = {source: group["group_id"] for group in proposal["groups"] for source in group["members"]}
            membership_artifact = _save(self, session, membership, "Frozen candidate source-to-group membership; original groups unchanged")
            channels = dict(plan["design"]["candidate_channels"])
            channels["removed_original_within"] = proposal["removed_within_pairs"]
            frame = {"groups": {row["group_id"]: row["members"] for row in proposal["groups"]},
                     "candidate_channels": channels, "article_ids": sorted(imported["articles"]),
                     "baseline_plan": data["plan"], "candidate_artifact": candidate_artifact,
                     "sampling_status": "Frame inputs only; no sample drawn; future full-support sampling/approval required",
                     "old_evaluation_labels_reused": False}
            frame_artifact = _save(self, session, frame, "Frozen candidate frame; original removed-within pairs retained as a retrieval channel")
            examples = []
            for old_id, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
                sizes = [len(group["members"]) for group in proposal["groups"] if group["members"][0] in members]
                if len(sizes) > 1:
                    examples.append({"old_group_id": old_id, "old_size": len(members), "new_sizes": sizes,
                                     "articles": [{field: imported["articles"][source].get(field) for field in ("source_version", "title", "url")}
                                                  for source in members[:2]]})
                if len(examples) == 2:
                    break
            result = {"method": METHOD, "versions": versions, "manifest": manifest_id, "plan": data["plan"],
                      "status": "fixed_split_candidate_unjudged", "capsule": imported["capsule"],
                      "candidate_membership": membership_artifact, "original_evaluation_plan": data["plan"],
                      "baseline_group_result": GROUP_RESULT, "all_source_count": proposal["source_count"],
                      "unchanged_original_memberships": True, "delta": DELTA, "rule": proposal["rule"],
                      "original_rule": proposal["original_rule"],
                      "import_provenance": {"capsule": imported["capsule"], "group_result": GROUP_RESULT,
                                            "application_result": APPLICATION_RESULT, "parent_workspace": str(parent),
                                            "parent_archive_reverified": False, "parent_head_inclusion_proof": False},
                      "candidate_artifact": candidate_artifact, "frame_artifact": frame_artifact,
                      "baseline": proposal["baseline"], "candidate": proposal["candidate"], "source_count": proposal["source_count"],
                      "retained_pairs_fraction": proposal["retained_pairs_fraction"], "grouped_article_fraction": proposal["grouped_article_fraction"],
                      "retained_feature_rows": len(proposal["feature_rows"]), "missing_feature_pairs": proposal["missing_feature_pairs"],
                      "external_bytes_verified": imported["external_bytes_verified"], "preparation_seconds": time.perf_counter() - started,
                      "examples": examples, "original_memberships_changed": False, "adopted": False, "accepted_dossiers": 0,
                      "evaluation_labels_accessed": 0, "reference_labels_used_for_selection": 0,
                      "new_model_calls": 0, "new_embedding_requests": 0, "new_network_calls": 0,
                      "paid_inference_cost_usd": "0", "precision": None, "human_validated": False,
                      "parent_archive_reverified": False, "parent_head_inclusion_proof": False, "completed_at": utc()}
            identifier = self.ledger.record(session, "event_group_refinement_result", key, result)
        presentation = self._record_presentation(session, bound, {"results": [{"kind": "event_group_refinement_result", "id": identifier}],
                                                                "markdown": render(result), "destination": "codex_chat"})
        return {"id": identifier, **result, "presentation": presentation}
