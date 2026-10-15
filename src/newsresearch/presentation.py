"""Preserve exact result presentations without claiming observable UI delivery."""
from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import TYPE_CHECKING

from .common import Context, Json, ResearchError, require_active, utc

if TYPE_CHECKING:
    from .runtime import Research


RESULT_KINDS = {
    "newsapi_probe",
    "newsapi_overview",
    "search", "candidate_run", "article_candidates", "article_query_run",
    "article_query_overview", "article_query_chart", "article_query_inspection",
    "article_query_manifest", "tag_retrieval",
    "adaptive_cutoff_result", "adaptive_cutoff_plan",
    "rag_query_result",
    "conversation_turn", "conversation_retrieval",
    "embedding_checkpoint_result", "aws_clustering_evaluation",
    "event_clustering_evaluation",
    "event_pair_plan", "event_pair_experiment", "event_pair_feature_experiment",
    "event_pair_conjunction_experiment",
}


def record(engine: Research, session: str, context: Context, data: Json) -> Json:
    require_active(engine, session)
    if set(data) - {"results", "markdown", "destination", "status", "delivery_report"}:
        raise ResearchError("Unsupported presentation fields")
    content = data.get("markdown")
    references = data.get("results")
    destination = data.get("destination")
    status = data.get("status", "prepared_for_delivery")
    report = data.get("delivery_report")
    if not isinstance(content, str) or not content.strip():
        raise ResearchError("A presentation requires exact nonblank Markdown")
    if destination not in {"codex_chat", "cli", "private_file", "local_app"}:
        raise ResearchError("Declare the presentation destination")
    if status not in {"prepared_for_delivery", "delivery_reported"}:
        raise ResearchError("Presentation status does not establish verified UI delivery")
    if status == "prepared_for_delivery" and report is not None:
        raise ResearchError("Prepared content cannot claim a delivery report")
    if status == "delivery_reported":
        if not isinstance(report, dict) or set(report) != {"occurred_at", "unavailable_reason"}:
            raise ResearchError("A reported delivery requires its time or an explicit unavailable reason")
        observed = report["occurred_at"]
        if observed is None:
            if not isinstance(report["unavailable_reason"], str) or not report["unavailable_reason"].strip():
                raise ResearchError("Unknown delivery time requires an unavailable reason")
        else:
            try:
                timestamp = datetime.fromisoformat(observed)
            except (TypeError, ValueError) as error:
                raise ResearchError("Reported delivery time must be timezone-aware ISO 8601") from error
            if timestamp.utcoffset() is None or timestamp > datetime.now(timezone.utc):
                raise ResearchError("Reported delivery time must be timezone-aware and not in the future")
            if report["unavailable_reason"] is not None:
                raise ResearchError("A known delivery time cannot have an unavailable reason")
    if not isinstance(references, list) or not references:
        raise ResearchError("Link the presentation to stored search results")
    seen = set()
    for reference in references:
        if (not isinstance(reference, dict) or set(reference) != {"kind", "id"}
                or not isinstance(reference["kind"], str) or reference["kind"] not in RESULT_KINDS
                or not isinstance(reference["id"], str)):
            raise ResearchError("Presentation result references require a supported kind and ID")
        key = (reference["kind"], reference["id"])
        if key in seen:
            raise ResearchError("Duplicate presentation result reference")
        seen.add(key)
        result = engine.ledger.get(reference["id"], reference["kind"])
        if result.get("versions") != context.versions:
            raise ResearchError("Presentation requires the exact original result version bindings")
    method = engine._version(session, context, {"kind": "profile", "key": "search-result-presentation-v1",
        "content": {"mode": "exploratory", "method": "search-result-presentation-v1",
            "population_estimate": False,
            "purpose": "Preserve caller-supplied exact result presentation linked to original immutable results",
            "delivery": "Prepared or caller-reported only; UI visibility and human reading are unobserved",
            "validation": "Identity, versions and exact text fidelity; no semantic validation or fresh inference"},
        "amend_latest": True, "reason": "Register exact search-result presentation capture before recording it"})["id"]
    artifact = engine.ledger.artifacts.put_bytes(content.encode("utf-8"))
    engine.ledger.append(session, "presentation.artifact.saved", {"artifact": artifact})
    result = {"results": references, "versions": context.versions, "method_version": method,
        "markdown": content, "content_artifact": artifact, "content_sha256": artifact,
        "format": "text/markdown; charset=utf-8", "destination": destination, "status": status,
        "delivery_report": report, "delivery_basis": "caller_attestation" if report else None,
        "recorded_at": utc(), "actor": context.actor, "session": session,
        "ui_delivery_verified": False, "human_reading_observed": False,
        "content_validation": "Caller-supplied transcription; semantic consistency not automatically validated",
        "network_calls": 0, "model_calls": 0}
    identifier = engine.ledger.record(session, "result_presentation", str(uuid.uuid4()), result)
    return {"id": identifier, **result, "content_path": str(engine.ledger.artifacts.root / artifact)}
