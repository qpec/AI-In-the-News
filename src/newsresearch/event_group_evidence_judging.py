"""Future authorized Codex judgments of a frozen complete-source review queue.

No approval is inferred from preparation. Reuses the original audited transport,
attempt allocations and source-bound contract; never merges or accepts groups.
"""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import json
from typing import TYPE_CHECKING

from . import event_group_evidence_study as preparation
from . import event_pair_experiment as original
from .common import AuditError, Context, Json, ResearchError, digest, require_active, utc
from .event_pair_answers import validate_request
from .event_pair_study import load_plan

if TYPE_CHECKING:
    from .runtime import Research

METHOD = "authorized-frozen-cross-window-full-pair-codex-review-v1"
CODE = ("event_group_evidence_judging.py", *preparation.CODE)


def _load(engine: Research, session: str, identifier: str) -> tuple[Json, Json, Json, list[Json], Json, Json]:
    prepared = engine.ledger.get(identifier, "event_group_evidence_result")
    manifest = engine.ledger.get(prepared["manifest"], "event_group_evidence_manifest")
    frozen = engine.ledger.get(prepared["frozen_queue"], "event_group_evidence_queue")
    if (prepared["status"] != "prepared_evidence_queue" or prepared["versions"] != manifest["versions"]
            or manifest["method"]["implementation"] != preparation.links.base._hashes(preparation.CODE)
            or frozen["manifest"] != prepared["manifest"] or frozen["versions"] != prepared["versions"]
            or not frozen["frozen_before_reference_check"]):
        raise AuditError("Judging requires the unchanged complete prepared result and frozen queue")
    queue = engine.ledger.artifacts.read(frozen["artifact"])
    packets = engine.ledger.artifacts.read(prepared["exports"]["packets"]["artifact"])
    if (len(queue["tasks"]) > 36 or len(packets) != len(queue["tasks"])
            or len({row["pair_id"] for row in packets}) != len(packets)
            or {row["pair_id"] for row in packets} != {row["pair_id"] for row in queue["tasks"]}
            or any(row["status"] != "prepared" for row in packets)):
        raise AuditError("Prepared pair packet coverage differs from the complete frozen queue")
    tasks = {row["pair_id"]: row for row in queue["tasks"]}
    for packet in packets:
        pair = [packet["left"], packet["right"]]
        task = tasks[packet["pair_id"]]
        if (pair != sorted(set(pair)) or len(pair) != 2 or digest(pair) != packet["pair_id"]
                or any(packet[key] != task[key] for key in ("left", "right"))):
            raise AuditError("Prepared packet endpoints differ from canonical frozen pair tasks")
    _, _, _, current, _ = preparation._parents(engine, prepared["previous_result"])
    plan, _, _ = load_plan(engine, session, current["plan"])
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    return prepared, frozen, queue, packets, plan, metadata


def approval_binding(identifier: str, prepared: Json, frozen: Json) -> str:
    return digest({"prepared_result": identifier, "prepared_manifest": prepared["manifest"],
                   "queue_artifact": frozen["artifact"], "packet_artifact": prepared["exports"]["packets"]["artifact"],
                   "versions": prepared["versions"], "config": prepared["config"]})


def _approval(data: Json, prepared: Json, frozen: Json, plan: Json, queue: Json) -> Json:
    value = data.get("run_approval")
    attestation = data.get("human_authorization")
    if attestation is not None:
        fields = {"authorization_key", "approved_by", "instruction", "expires_at", "authorized",
                  "external_processing_authorized", "codex_account_execution_authorized",
                  "approval_source", "observed_chat_timestamp"}
        if value is not None or not isinstance(attestation, dict) or set(attestation) != fields:
            raise ResearchError("Choose exact run approval or an explicit human authorization attestation")
        value = {**attestation, "method": "cross-window-event-review-run-approval-v1",
            "prepared_result": data["prepared_result"], "study_key": data["study_key"],
            "original_study_key": plan["study_key"],
            "prepared_binding": approval_binding(data["prepared_result"], prepared, frozen),
            "max_pair_attempts": 100, "max_article_exposures": 200, "max_primary_pairs": 90,
            "max_known_invalid_retries": 10, "queue_primary_tasks": len(queue["tasks"]),
            "remaining_primary_ceiling": 36, "remaining_retry_ceiling": 9}
    if not isinstance(value, dict):
        raise ResearchError("Fresh concrete cross-window Codex run approval is required")
    original._expiry(value)
    required = {"method": "cross-window-event-review-run-approval-v1", "prepared_result": data["prepared_result"],
        "study_key": data["study_key"], "original_study_key": plan["study_key"],
        "prepared_binding": approval_binding(data["prepared_result"], prepared, frozen),
        "approval_source": "human_reply_in_current_codex_chat"}
    limits = {"max_pair_attempts": 100, "max_article_exposures": 200, "max_primary_pairs": 90,
              "max_known_invalid_retries": 10, "queue_primary_tasks": len(queue["tasks"]),
              "remaining_primary_ceiling": 36, "remaining_retry_ceiling": 9}
    if (any(value.get(key) != expected for key, expected in required.items())
            or any(type(value.get(key)) is not int or value[key] != expected for key, expected in limits.items())
            or any(value.get(key) is not True for key in ("authorized", "external_processing_authorized",
                                                         "codex_account_execution_authorized"))
            or any(not isinstance(value.get(key), str) or not value[key].strip()
                   for key in ("authorization_key", "approved_by", "instruction"))
            or "observed_chat_timestamp" not in value or value["observed_chat_timestamp"] is not None):
        raise ResearchError("Approval must bind exact prepared requests, human instruction, external Codex account and cumulative original limits")
    return dict(value)


def classify(selected: list[Json], judgements: Json) -> list[Json]:
    results = []
    for proposal in selected:
        expected = {digest(list(pair)) for pair in combinations(sorted(proposal["article_members"]), 2)}
        if len(proposal["pair_task_ids"]) != len(expected) or set(proposal["pair_task_ids"]) != expected:
            raise AuditError("Proposal must include every union article pair, including old-group internal pairs")
        values = [judgements.get(key, {"status": "pending", "label": None}) for key in sorted(expected)]
        labels = Counter(value.get("label") for value in values if value.get("status") == "completed")
        complete = sum(value.get("status") == "completed" and value.get("label") in
                       {"same_event", "different_event", "uncertain"} for value in values)
        status = ("incomplete" if complete != len(expected) else "conflicting_model_references"
                  if labels["different_event"] else "uncertain" if labels["uncertain"] else
                  "provisional_pairwise_support_requires_cluster_review")
        results.append({**proposal, "review_status": status, "expected_pair_count": len(expected),
                        "completed_pair_count": complete, "model_reference_labels": dict(labels),
                        "has_different_event_reference": labels["different_event"] > 0,
                        "accepted": False, "actual_group_merges": 0, "human_validated": False})
    return results


def execute(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if (set(data) - {"prepared_result", "study_key", "run_approval", "human_authorization", "workers", "reuse_cache"}
            or any(not isinstance(data.get(key), str) or not data[key].strip() for key in ("prepared_result", "study_key"))
            or type(data.get("workers", 4)) is not int or not 1 <= data.get("workers", 4) <= 4
            or data.get("reuse_cache") is not True):
        raise ResearchError("Declare exact prepared result, immutable study key, workers1..4 and explicit exact-version cache reuse")
    prepared, frozen, queue, packets, plan, metadata = _load(engine, session, data["prepared_result"])
    classify(queue["selected"], {})  # Validate complete union-pair coverage before any model intent.
    required_pairs = {pair for proposal in queue["selected"] for pair in proposal["pair_task_ids"]}
    if required_pairs != {row["pair_id"] for row in queue["tasks"]}:
        raise AuditError("Frozen task IDs must equal the complete selected union-pair coverage")
    approval = _approval(data, prepared, frozen, plan, queue)
    if engine.config.offline:
        raise ResearchError("Authorized judgments require process-local online configuration")
    versions = prepared["versions"]
    if context.versions and context.versions != versions:
        raise ResearchError("Judging context must preserve the exact prepared request versions")
    config = original._config(engine, {key: prepared["config"][key] for key in ("codex_model", "codex_executable")})
    config["configuration_origin"] = prepared["config"]["configuration_origin"]
    if config != prepared["config"]:
        raise AuditError("Prepared Codex configuration or executable hash changed")
    budget = preparation._budget(engine, session, plan)
    snapshot = prepared["budget"]
    if (budget["original_study_key"] != snapshot["original_study_key"]
            or budget["spent_primary"] < snapshot["spent_primary"] or budget["spent_retries"] < snapshot["spent_retries"]
            or budget["remaining_primary"] > 36 or budget["remaining_retries"] > 9):
        raise AuditError("Original workflow allocation cannot be reset or enlarged")
    if budget["unresolved_attempts"]:
        raise ResearchError("Unresolved original workflow attempts block fresh judgments")
    binding = {"method": METHOD, "prepared_result": data["prepared_result"],
        "prepared_binding": approval_binding(data["prepared_result"], prepared, frozen), "approval": approval,
        "implementation": preparation.links.base._hashes(CODE), "request_versions": versions, "config": config,
        "original_study_key": plan["study_key"], "budget_reset": False,
        "transport": "unchanged original audited _phase and shared gateway; no Responses substitute",
        "acceptance": "all-pair references only; no automatic merges or accepted event dossiers"}
    prior = original._records(engine, "event_group_evidence_judging_manifest", data["study_key"])
    if prior:
        if len(prior) != 1 or prior[0][1]["binding"] != binding:
            raise ResearchError("Judgment approval, preparation, code, configuration and request versions are immutable")
        manifest_id, manifest = prior[0]
    else:
        for other in engine.ledger.db.execute("SELECT payload FROM records WHERE kind='event_group_evidence_judging_manifest'"):
            if json.loads(other[0])["binding"]["prepared_result"] == data["prepared_result"]:
                raise ResearchError("Prepared queue already has an immutable authorization lineage; cannot reset it")
        method_version = engine._version(session, context, {"kind": "protocol", "key": data["study_key"],
            "content": {"method": METHOD, **binding}, "branch": "authorized-cross-window-pairwise-review"})["id"]
        policy = engine._version(session, context, {"kind": "policy", "key": data["study_key"], "content": approval})["id"]
        manifest = {"versions": versions, "binding": binding, "method_version": method_version,
                    "approval_version": policy, "budget_before": budget}
        manifest_id = engine.ledger.record(session, "event_group_evidence_judging_manifest", data["study_key"], manifest)
    actual_bindings = []
    spent = original._spent(engine, plan["study_key"])
    new_primary = 0
    for packet in sorted(packets, key=lambda row: row["pair_id"]):
        saved = engine.ledger.artifacts.read(packet["request_ref"])
        validate_request(saved)
        regenerated = original._request(engine, session, packet, metadata, versions)
        if saved != regenerated or saved["versions"] != versions:
            raise AuditError("Queued complete source request, versions or exact instructions changed")
        actual_key = digest({"plan": manifest_id, "request": regenerated, "config": config, "method": original.METHOD})
        new_primary += not any(row["task_key"] == actual_key for row in spent)
        actual_bindings.append({"pair_id": packet["pair_id"], "planning_task_key": packet["task_key"],
            "actual_task_key": actual_key, "request_ref": packet["request_ref"], "request_hash": digest(saved),
            "source_versions": [packet["left"], packet["right"]], "request_versions": versions,
            "dispatch_manifest": "Original phase regenerates and records its own exact invocation; planning cwd identity is not claimed"})
    if new_primary > budget["remaining_primary"]:
        raise ResearchError("Frozen queue exceeds the remaining original primary allocation")
    engine.ledger.record(session, "event_group_evidence_task_bindings", data["study_key"],
        {"manifest": manifest_id, "versions": versions, "items": actual_bindings})
    engine.ledger.append(session, "event_group_evidence.judging_intended", {"manifest": manifest_id,
        "new_primary_tasks": new_primary, "budget": budget, "exact_requests_revalidated": len(actual_bindings)})
    judgements, stopped = original._phase(engine, session, queue["tasks"], manifest_id, plan,
                                         versions, approval, config, data)
    proposals = classify(queue["selected"], judgements)
    examples = []
    for proposal in proposals[:3]:
        pair_examples = []
        for pair_id in proposal["pair_task_ids"][:2]:
            value = judgements.get(pair_id, {})
            if value.get("status") == "completed":
                assessment = engine.ledger.get(value["assessment"], "event_pair_judgement")
                pair_examples.append({"pair_id": pair_id, "label": value["label"],
                    "rationale": assessment["result"]["rationale"],
                    "claims": assessment["result"]["claims"], "assessment": value["assessment"]})
        examples.append({"proposal": proposal, "pair_examples": pair_examples})
    after = preparation._budget(engine, session, plan)
    labels = Counter(value.get("label") for value in judgements.values() if value.get("status") == "completed")
    result = {"versions": versions, "manifest": manifest_id, "prepared_result": data["prepared_result"],
        "method_version": manifest["method_version"], "approval_version": manifest["approval_version"],
        "original_study_key": plan["study_key"], "judgements": judgements, "proposals": proposals,
        "pair_tasks": len(queue["tasks"]), "completed_pairs": sum(value.get("status") == "completed" for value in judgements.values()),
        "pair_label_counts": {key: labels[key] for key in ("same_event", "different_event", "uncertain")},
        "failed_pairs": sum(value.get("status") == "failed" for value in judgements.values()),
        "pending_pairs": sum(judgements.get(row["pair_id"], {}).get("status", "pending") == "pending" for row in queue["tasks"]),
        "unknown_pairs": sum(value.get("outcome") == "unknown" for value in judgements.values()),
        "proposal_status_counts": dict(Counter(row["review_status"] for row in proposals)),
        "budget_before": budget, "budget_after": after, "new_model_attempts": after["spent_attempts"] - budget["spent_attempts"],
        "prior_model_references": {"overlap_pairs": prepared["reused_reference_pairs_in_queue"],
            "known_conflict_proposals": prepared["known_reference_conflict_proposals"], "independent_validation": False},
        "status": "partial" if stopped or any(row["review_status"] == "incomplete" for row in proposals) else "completed_provisional_model_references",
        "actual_group_merges": 0, "accepted_dossiers": 0, "new_embedding_requests": 0,
        "human_validated": False, "sealed_holdout_opened": False, "provider_billing": None,
        "examples": examples, "dataset_articles": prepared.get("dataset_articles"),
        "missing_vector_articles": prepared.get("missing_vector_articles"),
        "missing_date_articles": prepared.get("missing_date_articles"),
        "provider_internal_request_count": None, "completed_at": utc()}
    identifier = engine.ledger.record(session, "event_group_evidence_judgment_result", data["study_key"], result)
    from .presentation import record
    presentation = record(engine, session, Context(context.objective, context.actor, versions), {
        "results": [{"kind": "event_group_evidence_judgment_result", "id": identifier}],
        "markdown": render(result), "destination": "codex_chat"})
    return {"id": identifier, **result, "presentation": presentation}


def render(result: Json) -> str:
    from .rag_answers import _excerpt, _link
    budget = result["budget_after"]
    overview = (f"Cross-window Codex reference review: **{result['status']}**.\n\n"
            f"Completed {result['completed_pairs']}/{result['pair_tasks']} article pairs: {result['pair_label_counts']}. "
            f"Failed {result['failed_pairs']}; pending {result['pending_pairs']}; unknown {result['unknown_pairs']}.\n\n"
            f"Proposal outcomes: {result['proposal_status_counts']}. Every entire union includes all article pairs; "
            "all-same results still require cluster review. These are model references, not human gold or accuracy estimates.\n\n"
            f"Original cumulative allocation: {budget['spent_attempts']}/100 attempts, {budget['spent_article_exposures']}/200 article exposures "
            f"({budget['spent_primary']} primary, {budget['spent_retries']} retries); "
            f"unresolved {len(budget['unresolved_attempts'])}. New attempts this execution: {result['new_model_attempts']}. "
            "Billing and internal provider request counts are unavailable. Current groups changed: 0; accepted dossiers: 0; new embeddings: 0.")
    lines = [overview, "", f"Pilot scope: {result['dataset_articles']} articles; missing vectors: {result['missing_vector_articles']}; "
        f"unusable dates: {result['missing_date_articles']}. The sealed holdout was not opened. "
        "The bounded development-only queue is not representative. Prior references remain separate from new judgments."]
    for example in result["examples"]:
        proposal = example["proposal"]
        articles = {article["source_id"]: article for article in proposal.get("articles", [])}
        lines += ["", "- Proposal: " + proposal["review_status"] + ". " + "; ".join(
            _link(article.get("title") or article["source_id"], article.get("url")) for article in articles.values())]
        for pair in example["pair_examples"]:
            lines += ["  Model reference: " + pair["label"] + "; " + _excerpt(pair["rationale"])]
            for claim in pair["claims"][:2]:
                article = articles.get(claim["source_version"], {})
                lines += ["  Evidence (" + claim["passage_id"] + "): “" + _excerpt(claim["quote"]) + "” — "
                    + _link(article.get("title") or claim["source_version"], article.get("url"))]
    return "\n".join(lines)
