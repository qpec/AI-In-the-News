"""Audited live route counts from committed decisions and immutable article mapping."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_screening_v2 as screening
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import audited_handler

METHOD = "luna-decisions-cybercrime-nl-counts-20261023-v1"
PLAN = "14fad3705b1e8fde7ecbeb8436d8c66c7eb69fe187da05ba6a5d521cae78317f"
OWNER = screening.original.base.pilot.BASE / METHOD


def aggregate(rows, mapping):
    decisions = {row["custom_id"]: row for row in rows}
    if len(decisions) != len(rows):
        raise AuditError("cyber_counts_duplicate_decision")
    identities, canonicals = set(), set()
    counts, unique, unavailable = Counter(), Counter(), Counter()
    aliases = 0

    def label(row):
        decision = row.get("decision") or {}
        if decision.get("status") == "valid":
            route = decision.get("route")
            if route not in {"keep", "exclude", "review"}:
                raise AuditError("cyber_counts_invalid_route")
            return route
        return "refusal" if decision.get("status") == "refusal" else "invalid_or_unknown"

    for row in rows:
        unique[label(row)] += 1
    for entry in mapping:
        key = entry["custom_id"]
        if key in identities:
            raise AuditError("cyber_counts_duplicate_article")
        identities.add(key)
        if entry["request_hash"] is None:
            if entry["status"] not in {"sealed_validation", "retention_unavailable"}:
                raise AuditError("cyber_counts_unexpected_unavailable")
            unavailable[entry["status"]] += 1
            continue
        canonical = entry["canonical_custom_id"]
        canonicals.add(canonical)
        aliases += int(entry["exact_input_reuse"])
        row = decisions.get(canonical)
        if row and row["request"] != entry["request_hash"]:
            raise AuditError("cyber_counts_request_mismatch")
        counts[label(row) if row else "no_stored_response"] += 1
    if not set(decisions) <= canonicals:
        raise AuditError("cyber_counts_decision_outside_mapping")
    return {"unique_responses": len(rows), "unique_routes": dict(unique),
            "article_routes_including_aliases": dict(counts), "unavailable": dict(unavailable),
            "selected_articles": len(identities), "eligible_articles": sum(counts.values()),
            "planned_unique_requests": len(canonicals), "aliases": aliases,
            "responses_with_billing_or_outcome_hold": sum(bool(r["unknown_or_billing_hold"]) for r in rows)}


class Study(screening.original.base.pilot.Study):
    def __init__(self, workspace, *args, **kwargs):
        if Path(workspace).resolve() == screening.OWNER.resolve():
            raise AuditError("cyber_counts_owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "procedure": "Use a read-only consistent Source snapshot. Verify current decision records and the frozen initial report's full article-to-canonical mapping. Ignore all historical export labels and join only current committed decisions. Retain unavailable, sealed, refusal, invalid/unknown and absent responses separately. Save aggregate output and provenance in separate protected owner. No source text, new model request or worker mutation.",
                "limitations": "Provisional model routes, not accuracy or accepted dossiers. Selected artifact verification is not a full active-owner replay; missing responses include in-flight or untouched inputs."},
            "question": {"text": "How many cybercrime articles currently have provisional keep, exclude and review labels?"},
            "selection": {"rules": "Fixed full cybercrime v2 plan and all committed decisions at one read-only snapshot; expand exact-input aliases using frozen source-free mapping."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content,
                "amend_latest": True, "reason": "Register live saved-label aggregation before observation"})["id"]
        source = screening.original.base.pilot.Source(screening.OWNER)
        try:
            observed = utc()
            head = source.head()
            plan = source.one("cyber_screen_plan")
            if plan["_record_id"] != PLAN or plan["implementation"] != screening.original.implementation():
                raise AuditError("cyber_counts_plan_changed")
            report = source.rows("cyber_screen_report")[0]
            if report["plan"] != PLAN or report["selected_articles"] != 61089:
                raise AuditError("cyber_counts_mapping_plan_changed")
            mapping_ref = report["article_results_artifact"]
            mapping = [json.loads(line) for line in source.artifacts.read(mapping_ref).splitlines() if line]
            rows = source.rows("cyber_screen_decision")
            if any(r["plan"] != PLAN or r["corpus"] != "cybercrime" for r in rows):
                raise AuditError("cyber_counts_wrong_plan_or_corpus")
            result = aggregate(rows, mapping)
            if (result["selected_articles"], result["eligible_articles"], result["planned_unique_requests"], result["aliases"],
                    result["unavailable"]) != (61089, 60777, 57002, 3775, {"sealed_validation": 61, "retention_unavailable": 251}):
                raise AuditError("cyber_counts_frame_mismatch")
            result.update(observed_at=observed, source_owner=str(source.owner), snapshot_head=head, plan=PLAN,
                          mapping_report=report["_record_id"], mapping_artifact=mapping_ref,
                          decision_records_artifact=self.ledger.artifacts.put([r["_record_id"] for r in rows]),
                          versions=versions, human_validated=False, new_model_calls=0, worker_mutations=0,
                          exact_chat_presentation_capture_supported=False)
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_live_label_counts", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Count existing cybercrime screening routes without interrupting the worker",
                                       actor="codex:cybercrime-live-label-counts")))
    finally:
        study.close()
