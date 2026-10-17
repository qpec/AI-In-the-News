"""Offline report of retained Batch results; no transport, projection or restart."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config
from newsresearch.event_batch_live_gateway import EventBatchLiveGateway
from newsresearch.runtime import Research, audited_handler
from luna_batch_budget_run import OWNER, STUDY, present
from luna_event_contract_v2 import contract_digest

KINDS = {"manifests": "luna_budget_dispatch_manifest", "jobs": "luna_budget_provider_job",
    "reconciled": "luna_budget_job_reconciled", "assessments": "luna_budget_assessment",
    "projections": "luna_budget_literal_projection", "finishes": "luna_budget_controller_finish"}


def aggregate(plan, rows, entries):
    """Join immutable identities before counting; missing projections stay missing."""
    manifests = {row["id"]: row for row in rows["manifests"]}
    tasks = {task["custom_id"]: (row["id"], row["corpus_id"])
             for row in manifests.values() for task in row["tasks"]}
    jobs = {row["manifest"]: row for row in rows["jobs"]}
    assessed = {row["id"]: row for row in rows["assessments"]}
    if (len(tasks) != sum(len(row["tasks"]) for row in manifests.values())
            or len(jobs) != len(rows["jobs"]) or not jobs.keys() <= manifests.keys()
            or len({row["custom_id"] for row in assessed.values()}) != len(rows["assessments"])):
        raise AuditError("progress_duplicate_or_foreign_identity")
    for manifest, job in jobs.items():
        if job["request_count"] != len(manifests[manifest]["tasks"]) or job["corpus_id"] != manifests[manifest]["corpus_id"]:
            raise AuditError("progress_job_coverage_mismatch")
    for row in assessed.values():
        if tasks.get(row["custom_id"]) != (row["manifest"], row["corpus_id"]) or row["manifest"] not in jobs:
            raise AuditError("progress_assessment_lineage_mismatch")
    projected, derived = set(), set()
    for row in rows["projections"]:
        original = assessed.get(row["original_assessment"])
        if original is None or any(row[key] != original[key] for key in ("custom_id", "corpus_id")) or row["original_status"] != original["status"]:
            raise AuditError("progress_projection_lineage_mismatch")
        projected.add(original["id"])
        if row["derived_valid"]:
            if original["status"] not in {"valid", "invalid"}:
                raise AuditError("progress_technical_projection_invalid")
            derived.add(original["id"])
    submitted_ids = {key for key, (manifest, _) in tasks.items() if manifest in jobs}
    entry_ids = {entry["request"]["request_id"] for entry in entries}
    if len(entry_ids) != len(entries) or not submitted_ids <= entry_ids:
        raise AuditError("progress_duplicate_budget_entry")
    for entry in entries:
        request = entry["request"]
        if request["request_id"] not in tasks or tasks[request["request_id"]][1] != request["corpus_id"]:
            raise AuditError("progress_budget_lineage_mismatch")
    result = {}
    for corpus, details in plan["corpora"].items():
        local = [row for row in assessed.values() if row["corpus_id"] == corpus]
        ids = {row["id"] for row in local}
        raw = {row["id"] for row in local if row["status"] == "valid"}
        invalid = {row["id"] for row in local if row["status"] == "invalid"}
        money = [entry for entry in entries if entry["request"]["corpus_id"] == corpus]
        submitted = sum(job["request_count"] for job in jobs.values() if job["corpus_id"] == corpus)
        known_usage = [row["usage"] for row in local if isinstance(row.get("usage"), dict)
                       and all(type(row["usage"].get(key)) is int for key in ("input_tokens", "output_tokens"))]
        counts = Counter(row["status"] for row in local)
        focus = Counter(row["output"]["focus"] for row in local if row["status"] == "valid")
        result[corpus] = {"eligible": details["summary"]["eligible_requests"], "submitted": submitted,
            "assessed": len(local), "unassessed": submitted - len(local),
            "eligible_not_submitted": details["summary"]["eligible_requests"] - submitted,
            "status_counts": {key: counts[key] for key in ("valid", "invalid", "error", "unknown")},
            "raw_valid_focus_counts": {key: focus[key] for key in ("single", "multiple", "none", "uncertain")},
            "projection_covered": len(ids & projected), "projection_uncovered": len(ids - projected),
            "derived_valid": len(ids & derived), "derived_only_recovered": len((ids & derived) - raw),
            "mechanically_usable": len(raw | (ids & derived)), "remaining_content_invalid": len(invalid - derived),
            "technical_or_unknown": sum(row.get("technical_failure", False) or row["status"] not in {"valid", "invalid"} for row in local),
            "usage_available_rows": len(known_usage), "usage_unavailable_rows": len(local) - len(known_usage),
            "usage": {key: sum(usage[key] for usage in known_usage) for key in ("input_tokens", "output_tokens")},
            "charged_nanousd": sum(entry["charged_nanousd"] for entry in money),
            "reserved_submitted_unresolved_nanousd": sum(entry["reserved_nanousd"] for entry in money if entry["request"]["request_id"] in submitted_ids),
            "reserved_staged_unsubmitted_nanousd": sum(entry["reserved_nanousd"] for entry in money if entry["request"]["request_id"] not in submitted_ids),
            "budget_status_counts": dict(Counter(entry["status"] for entry in money)),
            "examples": [{key: row[key] for key in ("id", "custom_id", "title", "url", "output")}
                for row in sorted(local, key=lambda row: row["custom_id"])
                if row["status"] == "valid" and row["output"]["focus"] == "single"][:3]}
    return result


class ProgressResearch(Research):
    def technical_metadata(self, session, row):
        sql = "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1"
        self.ledger.append(session, "budget.progress.provider_metadata.inspection.intended", {"sql": sql,
            "parameters": ["luna_budget_job_parsed", row["manifest"]], "custom_id": row["custom_id"],
            "output_text_permitted": "Only retained technical-error model output, bounded to 4096 characters; no source packet"})
        found = self.ledger.db.execute(sql, ("luna_budget_job_parsed", row["manifest"])).fetchone()
        matches = []
        if found:
            parsed = self.ledger.get(found["id"], "luna_budget_job_parsed")
            for receipt_id in parsed.get("download_receipts", {}).values():
                receipt = self.ledger.get(receipt_id, "event_batch_live_receipt")
                self.ledger.append(session, "budget.progress.provider_file.inspection.intended", {"receipt": receipt_id,
                    "artifact": receipt["body_ref"], "custom_id": row["custom_id"], "fields": ["error", "response.status_code", "response.body.error", "response.body.incomplete_details", "response.body.status", "response.body.model", "response.body.output structure and bounded text"]})
                for line in self.ledger.artifacts.read_bytes(receipt["body_ref"]).decode("utf-8").splitlines():
                    item = json.loads(line) if line.strip() else {}
                    if item.get("custom_id") == row["custom_id"]:
                        response = item.get("response") or {}
                        body = response.get("body") or {}
                        output = body.get("output")
                        encoded = json.dumps(output, ensure_ascii=False)
                        matches.append({"receipt": receipt_id, "row_error": item.get("error"), "http_status": response.get("status_code"),
                            **{key: body.get(key) for key in ("error", "incomplete_details", "status", "model")},
                            "retained_output": output if len(encoded) <= 4096 else None,
                            "output_display_omitted": len(encoded) > 4096})
        if len(matches) > 1:
            raise AuditError("progress_duplicate_provider_row")
        return matches[0] if matches else None

    @audited_handler
    def _status(self, session, context, data):
        if not self.config.offline or self.ledger.root.resolve() != OWNER.resolve():
            raise AuditError("progress_requires_original_offline_owner")
        plan_id = data["plan"]
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":retained-progress",
            "content": {"method": "luna-budget-retained-progress-v1", "plan": plan_id,
                "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "rules": "Read existing plan, task identities, results, projections, terminal controller metadata and budget only. Preserve original and derived counts, missing projection coverage and unresolved reservations. No source-body reads, inference, projection, transport, retry, restart or acceptance."},
            "amend_latest": True, "reason": "Bind the exact offline reporting implementation; retain prior failed report intent"})["id"]
        self.ledger.append(session, "budget.progress.inspection.intended", {"protocol": protocol, "plan": plan_id,
            "queries": [{"sql": "SELECT id FROM records WHERE kind=? ORDER BY created_event", "parameters": [kind]} for kind in KINDS.values()],
            "budget_query": {"sql": "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1", "parameters": ["event_batch_live_budget", STUDY]}})
        plan = self.ledger.get(plan_id, "luna_budget_execution_plan")
        if plan["authorization_id"] != STUDY or plan["contract_sha256"] != contract_digest():
            raise AuditError("progress_plan_contract_mismatch")
        profile = self._version(session, context, {"kind": "profile", "key": STUDY + ":retained-progress",
            "content": {"mode": "exploratory", "population_estimate": False,
                "protocol": protocol, "plan": plan_id, "versions": plan["versions"],
                "unit": "retained request, not dossier", "denominators": "Frozen eligible requests and submitted task identities; original and derived validity separate"},
            "amend_latest": True, "reason": "Bind this retained-result report without population inference"})["id"]
        rows = {name: [{**self.ledger.get(item["id"], kind), "id": item["id"]}
            for item in self.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event", (kind,))]
            for name, kind in KINDS.items()}
        rows = {name: [row for row in values if row.get("plan") == plan_id] for name, values in rows.items()}
        saved = EventBatchLiveGateway(self, self.gateway.provider).load_book(session, STUDY)
        if saved is None:
            raise AuditError("progress_existing_budget_required")
        book, state = saved
        entries = [book.entry(key) for key in sorted({event["value"]["request_id"] for event in book.to_dict()["events"] if event["action"] == "reserve"})]
        if any(entry["request"]["plan_id"] != plan_id for entry in entries):
            raise AuditError("progress_budget_plan_mismatch")
        corpora = aggregate(plan, rows, entries)
        if (sum(row["charged_nanousd"] for row in corpora.values()) != book.charged_nanousd
                or sum(row["reserved_submitted_unresolved_nanousd"] + row["reserved_staged_unsubmitted_nanousd"] for row in corpora.values()) != book.reserved_nanousd):
            raise AuditError("progress_budget_totals_do_not_reconcile")
        technical = []
        for row in rows["assessments"]:
            if row.get("technical_failure") or row["status"] not in {"valid", "invalid"}:
                self.ledger.append(session, "budget.progress.response.inspection.intended", {"assessment": row["id"], "artifact": row["response"], "fields": "source-free parser metadata only"})
                parsed = self.ledger.artifacts.read(row["response"])
                technical.append({**{key: row.get(key) for key in ("id", "custom_id", "corpus_id", "title", "url", "errors", "cost_status", "status", "usage", "request_id")},
                    "parsed_metadata": {key: parsed.get(key) for key in ("http_status", "provider_status", "observed_model", "usage_complete", "response_id", "provider_request_id", "missing", "errors")},
                    "retained_provider_metadata": self.technical_metadata(session, row),
                    "current_cost_status": book.entry(row["custom_id"])["status"]})
        value = {"plan": plan_id, "protocol": protocol, "profile": profile, "versions": plan["versions"], "corpora": corpora,
            "technical_rows": technical, "controller_finishes": rows["finishes"],
            "pending_jobs": len({row["manifest"] for row in rows["jobs"]} - {row["manifest"] for row in rows["reconciled"]}),
            "projection_protocols": dict(Counter(row["protocol"] for row in rows["projections"])),
            "budget_state": state, "charged_estimate_usd": book.charged_nanousd / 1e9,
            "reserved_usd": book.reserved_nanousd / 1e9, "budget_frozen": book.frozen,
            "new_models": 0, "new_projections": 0, "accepted_events": 0, "human_validated": False}
        lines = [f"Retained offline Batch progress: conservative charge **${book.charged_nanousd / 1e9:.6f}**, reserved **${book.reserved_nanousd / 1e9:.6f}**. Budget frozen: {book.frozen}. Pending jobs: {value['pending_jobs']}.", ""]
        for corpus, summary in corpora.items():
            lines.extend([f"**{corpus}:** {summary['submitted']:,}/{summary['eligible']:,} eligible submitted; {summary['assessed']} assessed; statuses {summary['status_counts']}; {summary['unassessed']} unassessed. Raw-valid focus: {summary['raw_valid_focus_counts']}.",
                f"Existing projections cover {summary['projection_covered']}/{summary['assessed']}; {summary['projection_uncovered']} unprojected. {summary['derived_only_recovered']} derived-only recoveries; {summary['mechanically_usable']} combined mechanically usable; {summary['remaining_content_invalid']} content-invalid unresolved; {summary['technical_or_unknown']} technical/unknown.",
                f"Known usage {summary['usage']} across {summary['usage_available_rows']} rows; unavailable for {summary['usage_unavailable_rows']}. Charge ${summary['charged_nanousd']/1e9:.6f}; reserved submitted/unresolved ${summary['reserved_submitted_unresolved_nanousd']/1e9:.6f}; staged/unsubmitted ${summary['reserved_staged_unsubmitted_nanousd']/1e9:.6f}.", ""])
            for example in summary["examples"]:
                event = example["output"]["event"]
                entities = "; ".join(f"{p['surface']} ({p['kind']}; {', '.join(r['role'] for r in p['roles'])})" for p in event["participants"])
                lines.append(f"- [{example['title']}](<{example['url']}>) — {event['summary']} Entities: {entities or 'none extracted'}.")
            lines.append("")
        for row in technical:
            lines.append(f"Technical record [{row['title']}](<{row['url']}>): {json.dumps(row, ensure_ascii=False)}")
        lines.extend([f"Retained controller finishes: {[(row['reason'], row['ended_at']) for row in rows['finishes']]}", "",
            "These are provisional mechanically checked article extractions, not confirmed events or grouping accuracy. Original statuses remain unchanged; unprocessed/missing/invalid is not negative eligibility. Costs are conservative estimates, not invoices. Zero new model calls, projections, embeddings, retries, source-body reads or restarts. Exact protected Markdown retained; record_presentation does not support this technical kind."])
        return present(self, session, "luna_budget_progress_report", value, "\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ProgressResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", {"plan": args.plan}, objective="Report retained Batch progress, unresolved failures, existing projections and cost without restarting", actor="codex:luna-batch-budget")
        print(result["markdown"])
        print(json.dumps({key: result[key] for key in ("id", "presentation", "charged_estimate_usd", "reserved_usd", "budget_frozen")}, ensure_ascii=False))
    finally:
        engine.close()
