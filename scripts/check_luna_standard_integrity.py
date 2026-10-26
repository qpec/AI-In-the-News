"""Incremental integrity replay of new Luna results in a separate Research owner."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.luna_speed_provider import validate_response, validate_request
from newsresearch.luna_standard_provider import build_prompt
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state
import luna_event_contract_v2 as contract
from luna_batch_literal_projection import project_literal_refs
from luna_standard_corpus import implementation

METHOD = "luna-standard-incremental-integrity-v1"


def inspect_assessment(value, artifacts):
    request = artifacts.json(value["request"])
    dispatch = artifacts.json(value["dispatch"])
    raw = artifacts.json(value["response"])
    response = ProviderResponse(**raw)
    packet = request["packet"]
    validate_request(request)
    if (request["attempt"] != value["attempt"] or request["task_key"] != value["task_key"]
            or contract.validate_packet(packet)
            or value["descriptor"]["corpus_id"] != value["corpus_id"]
            or value["descriptor"]["custom_id"] != value["custom_id"]
            or packet["source_map"]["source_fields"]["body"]["sha256"] != value["descriptor"]["retained_body_sha256"]
            or json.loads(dispatch["stdin"]) != json.loads(build_prompt(request))
            or dispatch["stdin_sha256"] != hashlib.sha256(dispatch["stdin"].encode()).hexdigest()
            or dispatch.get("configured_service_tier") != "standard" or dispatch.get("fast_mode") is not False
            or "features.fast_mode=false" not in dispatch["command"]
            or "--ignore-user-config" not in dispatch["command"]
            or any(arg.startswith("service_tier=") for arg in dispatch["command"])):
        raise AuditError("integrity_request_packet_or_standard_tier_binding_mismatch")
    errors = validate_response(response, packet)
    unknown = bool((response.raw_response or {}).get("unknown_outcome"))
    status = "not_dispatched" if value["dispatch_offset"] is None else "unknown" if unknown else "invalid" if errors else "valid"
    projection = project_literal_refs(response.payload, packet,
        response_status="completed" if not any(e.startswith("response:") for e in errors) else None)
    derived = "valid" if projection["valid"] else status if status in {"unknown", "not_dispatched"} else "invalid"
    if (value["status"] != status or value["errors"] != errors or value["projection"] != projection
            or value["derived_status"] != derived or value["usage"] != response.usage
            or value["observed_model"] != response.model
            or value.get("accepted") is not False or value.get("human_validated") is not False):
        raise AuditError("integrity_saved_result_replay_mismatch")
    return status, derived


class IntegrityResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        owner = Path(data["source_owner"]).resolve(strict=True)
        check_permissions(owner, root=True)
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Read one consistent SQLite snapshot of a running writer. Check new journal links, new record identities, referenced artifact hashes, exact requests, complete-packet bindings and saved mechanical results. Recompute separate reference projections. No model calls or source inference.",
            "limits": "Incremental local integrity since prior verified head; no adversarial rollback protection, full historical replay or semantic accuracy claim. In-flight intents may lack assessments at snapshot time."}})["id"]
        self.ledger.append(session, "standard.integrity.inspection.intended", {"source_owner": str(owner), "plan": data["plan"], "protocol": protocol})
        prior_row = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_integrity_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (str(owner),)).fetchone()
        previous = self.ledger.get(prior_row[0], "luna_integrity_checkpoint") if prior_row else None
        start = previous["head_seq"] if previous else 0
        previous_hash = previous["head_hash"] if previous else "0" * 64
        artifacts = state.SelectedArtifacts(owner)
        conn = state.read_only_database(owner)
        new_counts, new_derived, new_checked = Counter(), Counter(), 0
        try:
            plan_row = conn.execute("SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone()
            plan = state.row_value(plan_row, "luna_standard_plan")
            artifacts.check(plan_row["artifact"])
            expected_implementation = implementation()
            if plan.get("capacity_amendment"):
                from luna_standard_capacity import STUDY, implementation as capacity_implementation
                if plan["capacity_amendment"] != STUDY:
                    raise AuditError("integrity_unrecognized_capacity_amendment")
                expected_implementation = capacity_implementation()
            if plan.get("recovery_amendment"):
                from luna_standard_recovery import STUDY as RECOVERY, POLICY, implementation as recovery_implementation
                if plan["recovery_amendment"] != RECOVERY or plan.get("recovery_policy") != POLICY:
                    raise AuditError("integrity_unrecognized_recovery_amendment")
                expected_implementation = recovery_implementation()
            if plan.get("pacing_amendment"):
                from luna_standard_paced import STUDY as PACING, POLICY as PACING_POLICY, implementation as pacing_implementation
                if (plan["pacing_amendment"] != PACING or plan.get("pacing_policy") != PACING_POLICY
                        or plan.get("pacing_parent") not in plan.get("capacity_lineage", [])):
                    raise AuditError("integrity_unrecognized_pacing_amendment")
                expected_implementation = pacing_implementation()
            if plan.get("downscale_amendment"):
                from luna_standard_downscaled import STUDY as DOWNSCALE, POLICY as DOWNSCALE_POLICY, implementation as downscale_implementation
                if (plan["downscale_amendment"] != DOWNSCALE or plan.get("downscale_policy") != DOWNSCALE_POLICY
                        or plan.get("downscale_parent") not in plan.get("capacity_lineage", [])
                        or plan.get("operational_ceiling") != 1 or plan["config"]["allowed_workers"] != [1]
                        or plan["config"]["workers"] != 1):
                    raise AuditError("integrity_unrecognized_downscale_amendment")
                expected_implementation = downscale_implementation()
            allowed_plans = {data["plan"], *plan.get("capacity_lineage", [])}
            if plan["implementation"] != expected_implementation or plan["contract_digest"] != contract.contract_digest():
                raise AuditError("integrity_live_implementation_changed")
            head = conn.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            if head is None or head[0] < start:
                raise AuditError("integrity_source_rollback")
            if start and conn.execute("SELECT event_hash FROM events WHERE seq=?", (start,)).fetchone()[0] != previous_hash:
                raise AuditError("integrity_previous_head_changed")
            count = start
            required = {"session.started": ("identity",), "operation.intended": ("input",),
                "operation.completed": ("result",), "record.created": ("artifact",),
                "preparation.artifact.saved": ("artifact",), "model.attempt.intended": ("request", "dispatch"),
                "model.attempt.completed": ("response",), "model.attempt.unobserved": ("response",)}
            completions = []
            for row in conn.execute("SELECT * FROM events WHERE seq>? ORDER BY seq", (start,)):
                item = dict(row)
                current_hash = item.pop("event_hash")
                item["payload"] = json.loads(item["payload"])
                count += 1
                if item["seq"] != count or item["previous_hash"] != previous_hash or digest(item) != current_hash:
                    raise AuditError("integrity_new_journal_chain_mismatch")
                for field in required.get(item["kind"], ()):
                    if item["payload"].get(field):
                        artifacts.check(item["payload"][field])
                if item["kind"] in {"model.attempt.completed", "model.attempt.unobserved"}:
                    completions.append(item["payload"])
                previous_hash = current_hash
            if count != head[0] or previous_hash != head[1]:
                raise AuditError("integrity_snapshot_head_mismatch")
            for row in conn.execute("SELECT * FROM records WHERE created_event>? ORDER BY created_event", (start,)):
                value = state.row_value(row)
                artifacts.check(row["artifact"])
                if row["kind"] == "luna_standard_assessment":
                    if value["plan"] not in allowed_plans:
                        raise AuditError("integrity_assessment_plan_mismatch")
                    status, derived = inspect_assessment(value, artifacts)
                    projected = conn.execute("SELECT * FROM attempts WHERE id=?", (value["attempt"],)).fetchone()
                    if projected and (projected["status"] != status or projected["result_id"] != row["id"]
                            or projected["request_ref"] != value["request"] or projected["response_ref"] != value["response"]):
                        raise AuditError("integrity_attempt_projection_mismatch")
                    # A record and its completion are separate durable writes;
                    # the writer may be between them in this valid snapshot.
                    new_counts[(value["corpus_id"], status)] += 1
                    new_derived[(value["corpus_id"], derived)] += 1
                    new_checked += 1
            # A completion can follow an assessment checked in an earlier
            # snapshot. Verify its SQL projection when that completion arrives.
            for completed in completions:
                row = conn.execute("SELECT * FROM records WHERE id=?", (completed["assessment"],)).fetchone()
                value = state.row_value(row, "luna_standard_assessment")
                artifacts.check(row["artifact"])
                attempt = conn.execute("SELECT * FROM attempts WHERE id=?", (completed["attempt"],)).fetchone()
                if (attempt is None or attempt["result_id"] != completed["assessment"]
                        or attempt["response_ref"] != completed["response"] or attempt["status"] != completed["status"]
                        or value["attempt"] != completed["attempt"] or value["response"] != completed["response"]
                        or value["status"] != completed["status"] or attempt["request_ref"] != value["request"]):
                    raise AuditError("integrity_completion_projection_mismatch")
            lineage_json = json.dumps(sorted(allowed_plans))
            duplicates = conn.execute("SELECT json_extract(payload,'$.custom_id') FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.plan') IN (SELECT value FROM json_each(?)) GROUP BY 1 HAVING COUNT(*)>1", (lineage_json,)).fetchall()
            if duplicates:
                raise AuditError("integrity_duplicate_article_intents")
            intents = conn.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.plan') IN (SELECT value FROM json_each(?))", (lineage_json,)).fetchone()[0]
            totals = [{"corpus": r[0], "status": r[1], "count": r[2]} for r in conn.execute("SELECT json_extract(payload,'$.corpus_id'),json_extract(payload,'$.status'),COUNT(*) FROM records WHERE kind='luna_standard_assessment' GROUP BY 1,2")]
            if intents > plan["max_attempts"]:
                raise AuditError("integrity_queue_cap_exceeded")
            value = {"source_owner": str(owner), "plan": data["plan"], "head_seq": head[0], "head_hash": head[1],
                "previous_head_seq": start, "new_events_verified": head[0] - start, "new_results_verified": new_checked,
                "new_raw_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(new_counts.items())],
                "new_derived_counts": [{"corpus": k[0], "status": k[1], "count": v} for k, v in sorted(new_derived.items())],
                "artifacts_hashed": len(artifacts.checked), "total_raw_counts": totals,
                "reserved": intents, "unattempted": plan["max_attempts"] - intents,
                "integrity_passed": True, "semantic_accuracy_confirmed": False, "checked_at": utc(), "protocol": protocol}
        finally:
            conn.close()
        identifier = self.ledger.record(session, "luna_integrity_checkpoint", str(owner), value)
        report = self.ledger.root / "latest-integrity.json"
        report.write_text(json.dumps({"id": identifier, **value}, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"id": identifier, **value, "report_path": str(report)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-owner", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    engine = IntegrityResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"source_owner": str(args.source_owner), "plan": args.plan},
            objective="Verify new standard-speed Luna outputs without stopping the writer", actor="codex:luna-hourly-integrity")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as error:
        # This is a stop signal, never a repair or permission to resend an article.
        (args.source_owner / "STOP").write_text("Integrity check failed: " + type(error).__name__ + "\n", encoding="utf-8")
        raise
    finally:
        engine.close()


if __name__ == "__main__":
    main()
