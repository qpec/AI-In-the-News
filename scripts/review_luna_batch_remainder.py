"""Offline, audited review of the untouched Codex queue for an API Batch handoff.

No transport, inference permission, controller stop or source-body reads. The
saved selection is a proposal at a consistent journal head, not a dispatch queue.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics

from newsresearch.common import AuditError, Config, utc
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

import lean_luna_state as state

METHOD = "luna-batch-remainder-review-20261019-v1"


def select_remaining(queues, intents, prior_batch_ids):
    """Exclude every prior intent, including unknown and not-dispatched results."""
    all_ids = [d["custom_id"] for rows in queues.values() for d in rows]
    if len(all_ids) != len(set(all_ids)) or len(intents) != len(set(intents)):
        raise AuditError("remainder_duplicate_identity_or_intent")
    spent = set(intents)
    if not spent <= set(all_ids):
        raise AuditError("remainder_intent_outside_frozen_queue")
    if set(all_ids) & prior_batch_ids:
        raise AuditError("remainder_original_batch_exclusion_changed")
    for corpus, rows in queues.items():
        if any(d["corpus_id"] != corpus for d in rows):
            raise AuditError("remainder_corpus_binding_changed")
    return {k: [d for d in rows if d["custom_id"] not in spent] for k, rows in queues.items()}


def shards(rows, max_requests=1000, max_bytes=64_000_000):
    files, count, size = [], 0, 0
    for descriptor in rows:
        line_bytes = descriptor["line_bytes"]
        if type(line_bytes) is not int or not 0 < line_bytes <= max_bytes:
            raise AuditError("remainder_line_size_invalid")
        if count and (count >= max_requests or size + line_bytes > max_bytes):
            files.append({"requests": count, "bytes": size})
            count, size = 0, 0
        count += 1
        size += line_bytes
    if count:
        files.append({"requests": count, "bytes": size})
    return files


class ReviewResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": METHOD, "content": {
            "method": METHOD,
            "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "procedure": "Read consistent snapshots of the fixed-downscale owner and checkpoint-bound lean Batch operational state. Retain exact SQL, selected record and queue hashes, journal head and remaining request identities. Exclude every lineage intent regardless of result. Keep both corpora and old Batch liabilities. Calculate hypothetical file sizes, proxy-token scenarios and historical weighted cost extrapolation. No source text, HTTP or model calls, state changes or new execution authorization.",
            "limitations": "Snapshot proposal changes as the current worker progresses. Provider token counts and actual project queue capacity remain prerequisites for live admission. Historical costs and turnaround are not future guarantees; token proxies do not authorize spending. No semantic validation."}})["id"]
        codex_owner, lean_state = Path(data["codex_owner"]).resolve(), Path(data["lean_state"]).resolve()
        for path in (codex_owner, lean_state.parent):
            check_permissions(path, root=True)
        check_permissions(lean_state)
        self.ledger.append(session, "batch.remainder.review.intended", {
            "protocol": protocol, "codex_owner": str(codex_owner), "lean_state": str(lean_state), "plan": data["plan"]})
        queries = []

        def query(connection, source, sql, params=()):
            queries.append({"source": source, "sql": sql, "parameters": list(params)})
            return connection.execute(sql, params)

        source = state.read_only_database(codex_owner)
        lean = sqlite3.connect(lean_state.as_uri() + "?mode=ro", uri=True)
        lean.row_factory = sqlite3.Row
        lean.execute("PRAGMA query_only=ON")
        lean.execute("BEGIN")
        runtime = state.read_only_database(lean_state.parent / "runtime")
        source_artifacts, lean_artifacts = state.SelectedArtifacts(codex_owner), state.SelectedArtifacts(lean_state.parent / "runtime")
        try:
            plan_row = query(source, "codex", "SELECT * FROM records WHERE id=?", (data["plan"],)).fetchone()
            plan = state.row_value(plan_row, "luna_standard_plan")
            source_artifacts.check(plan_row["artifact"])
            head = query(source, "codex", "SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            lineage = {data["plan"], *plan.get("capacity_lineage", [])}
            rows = query(source, "codex", "SELECT payload FROM events WHERE kind='model.attempt.intended' ORDER BY seq")
            intents = [v["custom_id"] for r in rows if (v := json.loads(r[0])).get("plan") in lineage]
            queues = {k: source_artifacts.json(ref) for k, ref in plan["queues"].items()}
            if sum(len(rows) for rows in queues.values()) != plan["max_attempts"]:
                raise AuditError("remainder_frozen_cap_changed")
            meta = {r["key"]: json.loads(r["value"]) for r in query(lean, "lean", "SELECT * FROM meta")}
            checkpoint_row = query(runtime, "lean_runtime", "SELECT * FROM records WHERE kind='lean_luna_checkpoint' AND logical_key=? ORDER BY created_event DESC LIMIT 1", (meta["snapshot_id"],)).fetchone()
            checkpoint = state.row_value(checkpoint_row, "lean_luna_checkpoint")
            lean_artifacts.check(checkpoint_row["artifact"])
            if hashlib.sha256(lean.serialize()).hexdigest() != checkpoint["state_sha256"]:
                raise AuditError("remainder_lean_checkpoint_changed")
            if meta["blockers"] or meta["budget"]["frozen"]:
                raise AuditError("remainder_import_blocked")
            requests = {r["custom_id"]: dict(r) for r in query(lean, "lean", "SELECT custom_id,corpus_id,submitted,status FROM requests")}
            entries = {r["custom_id"]: dict(r) for r in query(lean, "lean", "SELECT custom_id,status,charged_nanousd,reserved_nanousd FROM budget_entries")}
            remaining = select_remaining(queues, intents, set(requests) | set(entries))
            price = meta["budget"]["config"]["price_policy"]
            totals = {key: sum(e[key] for e in entries.values()) for key in ("charged_nanousd", "reserved_nanousd")}
            totals["committed_nanousd"] = sum(totals.values())
            if totals != checkpoint["totals"]:
                raise AuditError("remainder_lean_balance_changed")
            submitted = Counter(r["corpus_id"] for r in requests.values() if r["submitted"])
            charges = Counter()
            for custom, entry in entries.items():
                if custom in requests and requests[custom]["submitted"]:
                    charges[requests[custom]["corpus_id"]] += entry["charged_nanousd"]
            jobs = [json.loads(r[0]) for r in query(lean, "lean", "SELECT payload FROM jobs")]
            manifests = {r[0]: json.loads(r[1]) for r in query(lean, "lean", "SELECT id,payload FROM manifests")}
            duration1000 = sorted(j["provider_completed_turnaround_seconds"] for j in jobs
                if j.get("provider_completed_turnaround_seconds") is not None
                and len(manifests[j["manifest_id"]]["request_ids"]) == 1000)
            details = {}
            for corpus, rows in remaining.items():
                proxies = [d["input_tokens_proxy"] for d in rows]
                files = shards(rows)
                details[corpus] = {
                    "frozen": len(queues[corpus]), "spent_intents": len(queues[corpus]) - len(rows), "untouched": len(rows),
                    "remaining_ids_ref": self.ledger.artifacts.put([d["custom_id"] for d in rows]),
                    "planned_files": len(files), "jsonl_bytes": sum(x["bytes"] for x in files),
                    "largest_file_bytes": max((x["bytes"] for x in files), default=0),
                    "input_token_proxy_sum": sum(proxies),
                    "input_token_proxy_mean": statistics.mean(proxies) if proxies else 0,
                    "historical_batch_submitted": submitted[corpus],
                    "historical_batch_charge_usd": charges[corpus] / 1e9,
                    "historical_weighted_cost_estimate_usd": round(len(rows) * charges[corpus] / submitted[corpus] / 1e9, 2) if submitted[corpus] else None,
                    "proxy_cost_scenarios_usd": {str(output): round(sum(state.cost(price, inp, output) for inp in proxies) / 1e9, 2) for output in (400, 800, 1600, 4096)},
                }
            result = {
                "method": METHOD, "protocol": protocol, "checked_at": utc(), "plan": data["plan"],
                "codex_owner": str(codex_owner), "head_seq": head[0], "head_hash": head[1],
                "queue_refs": plan["queues"], "lineage": sorted(lineage), "corpora": details,
                "untouched": sum(len(v) for v in remaining.values()), "spent_intents": len(intents),
                "legacy_batch_baseline": checkpoint["baseline"], "legacy_lean_checkpoint": checkpoint_row["id"],
                "legacy_state_sha256": checkpoint["state_sha256"], "authorization_id": meta["authorization_id"],
                "legacy_deadline": datetime.fromtimestamp(meta["deadline_epoch"], timezone.utc).isoformat(),
                "legacy_deadline_expired": datetime.now(timezone.utc).timestamp() >= meta["deadline_epoch"],
                "batch_budget_usd": {k.removesuffix("_nanousd"): v / 1e9 for k, v in totals.items()},
                "hard_cap_usd": state.HARD_CAP / 1e9, "operating_cap_usd": state.OPERATING_CAP / 1e9,
                "available_operating_usd": (state.OPERATING_CAP - totals["committed_nanousd"]) / 1e9,
                "unknown_cost_holds": sum(e["status"] == "unknown" for e in entries.values()),
                "pending_legacy_jobs": sum(not j["reconciled"] for j in jobs),
                "historical_1000_request_job_timing": {"n": len(duration1000), "median_seconds": statistics.median(duration1000) if duration1000 else None,
                    "p90_nearest_rank_seconds": duration1000[max(0, (9 * len(duration1000) + 9) // 10 - 1)] if duration1000 else None},
                "proposal": {"model": "gpt-6-luna", "reasoning_effort": "none", "max_output_tokens": 4096,
                    "max_requests_per_file": 1000, "max_jsonl_bytes": 64_000_000,
                    "candidate_queue_tokens": 20_000_000, "project_queue_limit_verified": False,
                    "scheduling": "Rolling concurrent jobs, refill after result reconciliation; separate corpus files; exact provider input counts and full output reservations precede admission.",
                    "requires": ["Explicitly renewed Batch submission window with the same existing USD150 total ceiling and USD120 operating admission limit, preserving old liabilities and deadline as history.", "Versioned audited adapter binding the final drained Codex head and untouched subset; no old controller restart.", "Stop and drain Codex only when the handoff is ready; recompute spent identities and update the monitor to prevent overlapping execution.", "Verify current project queue capacity before widening beyond established admission limits."],
                    "dispatch_authorized": False, "all_prior_intents_and_unknowns_excluded": True},
                "queries_ref": self.ledger.artifacts.put(queries), "model_calls": 0, "http_calls": 0,
                "source_bodies_read": False, "existing_state_mutated": False, "semantic_accuracy_confirmed": False}
        finally:
            source.close()
            lean.close()
            runtime.close()
        identifier = self.ledger.record(session, "luna_batch_remainder_review", METHOD, result)
        result = {"id": identifier, **result}
        (self.ledger.root / "latest-review.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--codex-owner", type=Path, required=True)
    parser.add_argument("--lean-state", type=Path, required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    engine = ReviewResearch(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"codex_owner": str(args.codex_owner), "lean_state": str(args.lean_state), "plan": args.plan},
            objective="Review the fastest Batch route for the remaining untouched articles, preserving all prior attempts and costs", actor="codex:batch-remainder-review")
        print(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
