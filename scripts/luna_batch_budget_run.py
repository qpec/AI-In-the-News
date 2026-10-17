"""Audited full-text Luna Batch execution with one authorization-wide USD ceiling.

All source reads and network actions enter Research.execute. Preparations and
eligibility exports are immutable; no old model queue is resumed or repaired.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config, Context, Json, ResearchError, digest, utc
from newsresearch.event_extraction_inputs import load_frame
from newsresearch.event_extraction_workflow import ORIGINAL_RESULT, _owner
from newsresearch.runtime import Research, audited_handler

import luna_multibatch as core
from luna_speed_test import STOPPED_PLAN
from scope_reduction_replay import assign_corpus, partition_binding

ROOT = Path(__file__).resolve().parents[1]
BASE = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News")
OWNER = BASE / "luna-fulltext-batch-budget-20261017-v1"
STUDY = "luna-fulltext-batch-budget-20261017-v1"
METHOD = "luna-fulltext-batch-budget-v1"
USER_INSTRUCTION = "Lets do the batch, but i want to prevent it costing as much as 300 dollar. Implement measure to reduce cost to 150 max"
PREPARATIONS = {
    "incident-reports": "f39bc9380ce572aa5ec66156c7badc66ec852783e1bc301446efff8c6a429cbc",
    "cybercrime": "c91132f38369d77d2374879d52f5409e9176bf67138d03cae53f168210f7385b",
}


def save(engine: Research, session: str, value: object, purpose: str) -> str:
    raw = value if isinstance(value, bytes) else core.canonical_json(value).encode("utf-8")
    reference = engine.ledger.artifacts.put_bytes(raw)
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": purpose})
    return reference


def present(engine: Research, session: str, kind: str, value: Json, markdown: str) -> Json:
    identifier = engine.ledger.record(session, kind, STUDY, value)
    reference = engine.ledger.artifacts.put_bytes(markdown.encode("utf-8"))
    engine.ledger.append(session, "presentation.artifact.saved", {"artifact": reference, "result": identifier,
        "result_kind": kind, "status": "prepared_for_delivery", "destination": "codex_chat",
        "record_presentation_supported": False})
    return {"id": identifier, **value, "markdown": markdown, "presentation": reference,
            "presentation_path": str(engine.ledger.artifacts.root / reference)}


def register(engine: Research, session: str, context: Context, suffix: str, rules: str) -> str:
    return engine._version(session, context, {"kind": "protocol", "key": STUDY + suffix,
        "content": {"method": METHOD + suffix, "rules": rules,
                    "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        "amend_latest": True, "reason": "Append exact implementation-bound operation protocol"})["id"]


class BudgetResearch(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        phase = data["phase"]
        if phase == "export-eligibility":
            return self.export_eligibility(session, context, data)
        if phase == "export-preparation":
            return self.export_preparation(session, context, data)
        raise ResearchError("batch_budget_phase_not_implemented")

    def export_preparation(self, session: str, context: Context, data: Json) -> Json:
        corpus = data["corpus"]
        if not self.config.offline or corpus not in PREPARATIONS:
            raise AuditError("batch_preparation_export_requires_offline_corpus")
        expected = BASE / f"luna-fulltext-multibatch-{corpus}-20261017-v1"
        if self.ledger.root.resolve() != expected.resolve():
            raise AuditError("batch_preparation_wrong_owner")
        protocol = register(self, session, context, ":preparation-export", "Read only the named immutable preparation and its descriptor artifacts. Export hashes/locators, no source-body rescan or model calls.")
        identifier = PREPARATIONS[corpus]
        self.ledger.append(session, "budget.preparation.export.intended", {"result": identifier, "corpus_id": corpus, "protocol": protocol})
        result = self.ledger.get(identifier, "note")["content"]
        manifest = self.ledger.artifacts.read(result["manifest_artifact"])
        if result["corpus_id"] != corpus or manifest["corpus_id"] != corpus:
            raise AuditError("batch_preparation_export_partition_mismatch")
        chunks = []
        for descriptor in manifest["descriptor_chunks"]:
            raw = self.ledger.artifacts.read_bytes(descriptor["artifact"])
            chunks.append({"descriptor": descriptor, "content": json.loads(raw)})
        value = {"source_owner": str(self.ledger.root), "source_result": identifier,
                 "protocol": protocol, "result": result, "manifest": manifest, "chunks": chunks}
        reference = save(self, session, value, "Immutable full-text preparation export for shared-budget authorization")
        summary = {"corpus_id": corpus, "source_result": identifier, "export": reference,
                   "export_path": str(self.ledger.artifacts.root / reference), "rows": result["totals"]["rows"],
                   "requests": result["totals"]["requests"], "new_models": 0, "archive_rescans": 0}
        return present(self, session, "luna_batch_preparation_export", summary,
            f"Offline preparation export: **{corpus}**. Replayed {summary['rows']:,} saved row descriptors and {summary['requests']:,} proposed full-text requests. Zero source rescans, model calls or uploads. Production selection is still pending. Exact report is protected; record_presentation does not support this technical kind.")

    def export_eligibility(self, session: str, context: Context, data: Json) -> Json:
        if not self.config.offline or self.ledger.root.resolve() != (BASE / "luna-seven-day-validation-20261016-v1").resolve():
            raise AuditError("batch_eligibility_requires_original_offline_owner")
        protocol = register(self, session, context, ":eligibility-export", "Freeze held-out body hashes, stopped extraction sources, all previously dispatched speed sources and unresolved source identities before new Batch selection. Hash source bodies/provider records only; no semantic inference, vectors or prior-label reuse.")
        old = self.ledger.get(ORIGINAL_RESULT, "luna_group_validation_result")
        original = self.ledger.get(old["plan"], "luna_group_validation_plan")
        _owner(self, original)
        inputs = load_frame(self, session, original)
        folds = {row["body_sha256"]: row["fold"] for row in inputs["frame"]["representatives"]}
        reasons: dict[str, set[str]] = {}
        for source in original["membership"]:
            if folds[inputs["metadata"][source]["body_sha256"]] != "development":
                reasons.setdefault(source, set()).add("sealed_body_validation")
        stopped = self.ledger.get(STOPPED_PLAN, "luna_group_validation_plan")
        for task in stopped["tasks"]:
            reasons.setdefault(task["source_version"], set()).add("stopped_extraction")
        query = "SELECT json_extract(payload,'$.source_version') AS source FROM records WHERE kind='luna_speed_assessment' AND json_extract(payload,'$.dispatch_offset') IS NOT NULL"
        self.ledger.append(session, "budget.prior_attempts.inspection.intended", {"sql": query, "protocol": protocol})
        for row in self.ledger.db.execute(query):
            reasons.setdefault(row["source"], set()).add("prior_speed_attempt")
        tasks = {task["logical_id"]: task for task in original["tasks"]}
        unresolved = {s for row in self.ledger.unresolved.values() for s in row.get("source_versions", [])}
        for key, outcome in old["outcomes"].items():
            if outcome["status"] == "unknown":
                unresolved.update(tasks[key]["source_versions"])
        # Custom speed attempts retain source identity in their assessment even
        # when the generic unresolved projection has no source_versions field.
        query = "SELECT json_extract(payload,'$.source_version') AS source FROM records WHERE kind='luna_speed_assessment' AND json_extract(payload,'$.status')='unknown'"
        self.ledger.append(session, "budget.unknown_attempts.inspection.intended", {"sql": query})
        unresolved.update(row["source"] for row in self.ledger.db.execute(query))
        for source in unresolved:
            reasons.setdefault(source, set()).add("unresolved_prior_attempt")
        self.ledger.append(session, "budget.exclusion_source_hashes.inspection.intended", {
            "source_versions": sorted(reasons), "sql": "SELECT payload FROM sources WHERE id=?",
            "purpose": "Exact corpus/body/article identity reconciliation; text not returned"})
        partition = partition_binding(Path(data["data_root"]))
        rows = []
        for source, why in sorted(reasons.items()):
            row = self.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()
            if row is None:
                raise AuditError("batch_exclusion_source_unavailable")
            payload = json.loads(row[0])
            body, article = payload.get("body"), payload.get("raw_record")
            if not isinstance(body, str) or not isinstance(article, dict):
                raise AuditError("batch_exclusion_source_identity_missing")
            rows.append({"source_version": source, "corpus_id": assign_corpus(payload["archive_provenance"], partition),
                         "reasons": sorted(why), "source_sha256": digest(article),
                         "retained_body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
                         "archive_provenance": payload["archive_provenance"]})
        categories = ("sealed_body_validation", "stopped_extraction", "prior_speed_attempt", "unresolved_prior_attempt")
        counts = {kind: sum(kind in row["reasons"] for row in rows) for kind in categories}
        value = {"method": METHOD + ":eligibility-export", "source_owner": str(self.ledger.root),
                 "original_result": ORIGINAL_RESULT, "protocol": protocol, "partition": partition,
                 "categories": list(categories), "category_counts": counts, "rows": rows,
                 "sealed_body_hashes": sorted(body for body, fold in folds.items() if fold != "development"),
                 "sealed_body_hash_count": sum(fold != "development" for fold in folds.values()),
                 "completed": True, "created_at": utc(), "labels_read": False}
        reference = save(self, session, value, "Complete exclusion identities before paid Batch selection")
        summary = {"export": reference, "export_path": str(self.ledger.artifacts.root / reference),
                   "category_counts": counts, "distinct_sources": len(rows), "model_calls": 0,
                   "sealed_body_hash_count": value["sealed_body_hash_count"],
                   "source_text_returned": False, "protocol": protocol}
        return present(self, session, "luna_batch_eligibility_export", summary,
            f"Offline Batch eligibility reconciliation: {len(rows):,} distinct protected source identities; overlapping reasons {counts}. Zero model calls, embeddings, membership changes or source text returned. These are preservation exclusions, not negative event labels. New Batch selection remains pending. Exact report is protected; record_presentation does not support this technical kind.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("export-eligibility", "export-preparation"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--corpus", choices=tuple(PREPARATIONS))
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = BudgetResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"phase": args.phase, "data_root": str(args.data_root) if args.data_root else None, "corpus": args.corpus},
            objective="Reconcile existing full-text preparations and protected eligibility for one Batch run capped at USD150",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({k: v for k, v in result.items() if k != "markdown"}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
