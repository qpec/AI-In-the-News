"""Offline count-identity/capacity diagnosis; never dispatch, retry or reset."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import sys

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.event_batch_live_gateway import ACTION_IDENTITY_KIND, ACTION_KIND, RECEIPT_KIND, EventBatchLiveGateway
from newsresearch.event_batch_transport import count_request_body
from newsresearch.runtime import Research, audited_handler
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
from luna_event_contract_v2 import contract_digest
from report_luna_budget_progress import KINDS as PROGRESS_KINDS, aggregate

COUNT_REQUEST = {"method": "POST", "path": "/v1/responses/input_tokens"}
KINDS = {**PROGRESS_KINDS, "actions": ACTION_KIND, "identities": ACTION_IDENTITY_KIND,
    "receipts": RECEIPT_KIND, "runs": "luna_budget_controller_run",
    "continuations": "luna_budget_phase_continuation"}


def diagnose_counts(plan_id, tasks, rows, read_bytes):
    """Compare exact retained bytes, not token proxies or article similarity."""
    actions = {row["action_id"]: row for row in rows["actions"]}
    receipts = {}
    identities = {}
    for row in rows["receipts"]:
        receipts.setdefault(row["action_id"], []).append(row)
    for row in rows["identities"]:
        identities.setdefault(row["logical_hash"], []).append(row)
    results = []
    for task in tasks:
        raw = read_bytes(task["request_body_ref"])
        if hashlib.sha256(raw).hexdigest() != task["request_body_ref"]:
            raise AuditError("capacity_task_body_hash_mismatch")
        body = json.loads(raw)
        count_raw = canonical(count_request_body(body)).encode()
        count_hash = hashlib.sha256(count_raw).hexdigest()
        logical_hash = digest({"request": COUNT_REQUEST, "body_sha256": count_hash})
        wanted = digest({"authorization_id": STUDY, "action_key": "count:" + task["custom_id"]})
        candidates = []
        for identity in identities.get(logical_hash, []):
            action = actions.get(identity["action_id"])
            exact = json.loads(read_bytes(identity["exact_request_ref"]))
            prior_raw = read_bytes(exact["original_body_ref"])
            same_bytes = prior_raw == count_raw and exact.get("logical_request") == COUNT_REQUEST
            retained = receipts.get(identity["action_id"], [])
            receipt = retained[-1] if retained else None
            valid = bool(action and action.get("phase") == "count" and action.get("plan_id") == plan_id
                and action.get("logical_hash") == logical_hash and action.get("exact_request_ref") == identity["exact_request_ref"]
                and receipt and receipt.get("unknown") is False and receipt.get("phase") == "count"
                and receipt.get("plan_id") == plan_id and type(receipt.get("status")) is int
                and 200 <= receipt["status"] < 300 and receipt.get("body_ref") and same_bytes)
            tokens = None
            if valid:
                answer_raw = read_bytes(receipt["body_ref"])
                if hashlib.sha256(answer_raw).hexdigest() != receipt["body_sha256"]:
                    raise AuditError("capacity_count_receipt_hash_mismatch")
                answer = json.loads(answer_raw)
                tokens = answer.get("input_tokens") if isinstance(answer, dict) else None
                valid = type(tokens) is int and tokens > 0
            candidates.append({"identity_record": identity["id"], "action_record": action.get("id") if action else None,
                "action_id": identity["action_id"], "action_key": action.get("action_key") if action else None,
                "same_action_id": identity["action_id"] == wanted, "exact_count_bytes_equal": same_bytes,
                "successful_exact_count": valid, "input_tokens": tokens if valid else None,
                "receipt_record": receipt.get("id") if receipt else None,
                "receipt_body_sha256": receipt.get("body_sha256") if receipt else None,
                "provider_request_id": receipt.get("provider_request_id") if receipt else None,
                "unknown_or_missing_receipt": not receipt or receipt.get("unknown") is not False,
                "http_status": receipt.get("status") if receipt else None,
                "prior_exact_request_ref": identity["exact_request_ref"],
                "prior_original_body_ref": exact["original_body_ref"]})
        same_action = wanted in actions
        changed_key = bool(candidates) and not same_action
        results.append({"custom_id": task["custom_id"], "corpus_id": task["corpus_id"],
            "manifest": task["manifest"], "request_body_ref": task["request_body_ref"],
            "requested_model": body["model"], "observed_count_model": None,
            "count_body_sha256": count_hash, "logical_hash": logical_hash,
            "wanted_action_id": wanted, "existing_same_key_action": same_action,
            "gateway_dispatch_intent_absent": not same_action,
            "changed_key_collision": changed_key,
            "successful_exact_count_available": any(row["successful_exact_count"] for row in candidates),
            "candidates": candidates})
    return results


class CapacityResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        if not self.config.offline or self.ledger.root.resolve() != OWNER.resolve():
            raise AuditError("capacity_diagnostic_requires_fixed_offline_owner")
        plan_id = data["plan"]
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":capacity-diagnostic",
            "content": {"method": "retained-count-identity-diagnostic-v1", "plan": plan_id,
                "implementation": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in
                    ("scripts/diagnose_luna_batch_capacity.py", "scripts/report_luna_budget_progress.py", "src/newsresearch/event_batch_transport.py")},
                "rules": "Offline metadata and exact-byte comparison only. Inspect retained unsubmitted request/count payloads without displaying source text. Preserve every identity, reservation and failed intent. Successful count matches are diagnostic candidates, not cache-reuse authorization. No provider, model, retry, reset or continuation."}})["id"]
        self.ledger.append(session, "budget.capacity.plan.inspection.intended", {"plan": plan_id, "protocol": protocol})
        plan = self.ledger.get(plan_id, "luna_budget_execution_plan")
        if plan["authorization_id"] != STUDY or plan["contract_sha256"] != contract_digest():
            raise AuditError("capacity_plan_contract_mismatch")
        profile = self._version(session, context, {"kind": "profile", "key": STUDY + ":capacity-diagnostic",
            "content": {"mode": "exploratory", "population_estimate": False, "plan": plan_id,
                "protocol": protocol, "versions": plan["versions"], "unit": "retained request and count action"}})["id"]
        rows = {}
        for name, kind in KINDS.items():
            sql = "SELECT id FROM records WHERE kind=? ORDER BY created_event"
            self.ledger.append(session, "budget.capacity.records.inspection.intended", {"sql": sql, "parameters": [kind]})
            loaded = [{**self.ledger.get(row["id"], kind), "id": row["id"]} for row in self.ledger.db.execute(sql, (kind,))]
            rows[name] = [row for row in loaded if row.get("authorization_id") == STUDY] if name in {"actions", "identities", "receipts"} else [row for row in loaded if row.get("plan") == plan_id]
        self.ledger.append(session, "budget.capacity.budget.inspection.intended", {"authorization_id": STUDY})
        saved = EventBatchLiveGateway(self, self.gateway.provider).load_book(session, STUDY)
        if saved is None:
            raise AuditError("capacity_existing_budget_required")
        book, state = saved
        entries = [book.entry(key) for key in sorted({event["value"]["request_id"] for event in book.to_dict()["events"] if event["action"] == "reserve"})]
        if any(entry["request"]["plan_id"] != plan_id for entry in entries):
            raise AuditError("capacity_budget_plan_mismatch")
        progress = aggregate(plan, rows, entries)
        for summary in progress.values():
            summary.pop("examples", None)
        submitted_manifests = {row["manifest"] for row in rows["jobs"]}
        staged = [{**task, "manifest": manifest["id"]} for manifest in rows["manifests"]
                  if manifest["id"] not in submitted_manifests for task in manifest["tasks"]]
        def read(reference):
            self.ledger.append(session, "budget.capacity.artifact.inspection.intended", {"artifact": reference,
                "purpose": "Exact request/count byte comparison or count receipt; no source display"})
            return self.ledger.artifacts.read_bytes(reference)
        counts = diagnose_counts(plan_id, staged, rows, read)
        task_attempts = {task["custom_id"]: attempt for manifest in rows["manifests"]
            for task, attempt in zip(manifest["tasks"], manifest.get("attempt_ids", []))}
        for item in counts:
            attempt = task_attempts.get(item["custom_id"])
            sql = "SELECT id,status FROM attempts WHERE id=?"
            self.ledger.append(session, "budget.capacity.attempt.inspection.intended", {"sql": sql, "parameters": [attempt]})
            projected = self.ledger.db.execute(sql, (attempt,)).fetchone() if attempt else None
            item.update(frozen_attempt_id=attempt, unresolved_paid_intent=attempt in self.ledger.unresolved if attempt else None,
                        projected_attempt_status=projected["status"] if projected else None)
        reserved = {entry["request"]["request_id"] for entry in entries if entry["status"] == "reserved"}
        entry_ids = {entry["request"]["request_id"] for entry in entries}
        budget_by_corpus = {corpus: {"staged_unsubmitted": sum(task["corpus_id"] == corpus for task in staged),
            "reserved_staged": sum(task["corpus_id"] == corpus and task["custom_id"] in reserved for task in staged),
            "never_reserved_staged": sum(task["corpus_id"] == corpus and task["custom_id"] not in entry_ids for task in staged)} for corpus in plan["corpora"]}
        failures = []
        sql = "SELECT seq,session_id,time,payload FROM events WHERE kind=? ORDER BY seq DESC LIMIT 20"
        self.ledger.append(session, "budget.capacity.failures.inspection.intended", {"sql": sql, "parameters": ["operation.failed"]})
        for failure in self.ledger.db.execute(sql, ("operation.failed",)):
            intended_sql = "SELECT payload FROM events WHERE session_id=? AND kind=? ORDER BY seq LIMIT 1"
            self.ledger.append(session, "budget.capacity.failure_input.inspection.intended", {"sql": intended_sql, "parameters": [failure["session_id"], "operation.intended"]})
            intended = self.ledger.db.execute(intended_sql, (failure["session_id"], "operation.intended")).fetchone()
            payload = self.ledger.artifacts.read(json.loads(intended["payload"])["input"]) if intended else {}
            if payload.get("plan") == plan_id:
                failures.append({"event_seq": failure["seq"], "session": failure["session_id"], "time": failure["time"],
                    **json.loads(failure["payload"]), "continuation_ref": payload.get("continuation_ref")})
        continuations = []
        for row in rows["continuations"]:
            matches = {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest() == expected for name, expected in row["implementation"].items()}
            continuations.append({"id": row["id"], "original_run": row["original_run"], "original_stop": row["original_stop"],
                "deadline_epoch": row["deadline_epoch"], "implementation_matches": matches, "all_code_matches": all(matches.values())})
        value = {"plan": plan_id, "protocol": protocol, "profile": profile, "versions": plan["versions"],
            "progress": progress, "staging": budget_by_corpus, "count_diagnostics": counts,
            "count_summary": dict(Counter("changed_key_collision" if row["changed_key_collision"] else "same_key_existing" if row["existing_same_key_action"] else "no_prior_identity" for row in counts)),
            "successful_count_candidates": sum(row["successful_exact_count_available"] for row in counts),
            "budget_state": state, "charged_estimate_usd": book.charged_nanousd / 1e9, "reserved_usd": book.reserved_nanousd / 1e9,
            "committed_usd": book.committed_nanousd / 1e9, "available_operating_usd": book.available_nanousd / 1e9, "budget_frozen": book.frozen,
            "budget_status_counts": dict(Counter(entry["status"] for entry in entries)),
            "unknown_or_frozen_budget_entries": sum(entry["status"] in {"unknown", "frozen", "overrun"} for entry in entries),
            "staged_manifests": [{"id": row["id"], "jsonl_ref": row.get("jsonl_ref"), "corpus_id": row["corpus_id"],
                "task_count": len(row["tasks"]), "attempt_ids": row.get("attempt_ids", [])} for row in rows["manifests"] if row["id"] not in submitted_manifests],
            "pending_jobs": len(submitted_manifests - {row["manifest"] for row in rows["reconciled"]}),
            "controller_runs": [{key: row.get(key) for key in ("id", "deadline_epoch", "started_at", "original_run", "continuation_ref")} for row in rows["runs"]],
            "continuations": continuations, "recent_plan_failures": failures,
            "failure_message_retained": False, "account_capacity_verified": False,
            "new_provider_calls": 0, "new_models": 0, "new_embeddings": 0, "retries": 0}
        lines = [f"Offline capacity diagnosis: charge ${value['charged_estimate_usd']:.6f}, reserved ${value['reserved_usd']:.6f}, committed ${value['committed_usd']:.6f}; {value['pending_jobs']} pending jobs. Frozen: {book.frozen}.",
            f"Staged count identities: {value['count_summary']}; {value['successful_count_candidates']} have exact successful retained count candidates. No reuse or submission performed.", ""]
        for corpus, item in progress.items():
            lines.append(f"{corpus}: {item['submitted']} submitted/{item['assessed']} assessed; raw {item['raw_status_counts']}, current parser {item['status_counts']}; phase recoveries {item['phase_recovered']}, literal-only recoveries {item['derived_only_recovered']}, combined mechanically usable {item['mechanically_usable']}; literal coverage {item['projection_covered']}/{item['assessed']}. Staging {budget_by_corpus[corpus]}.")
        collisions = [row for row in counts if row["changed_key_collision"]]
        lines.extend(["", f"Collision examples (up to five, no article text): {json.dumps(collisions[:5])}",
            f"Retained runtime failures: {json.dumps(failures)}. Runtime stores exception type, not the exception message.",
            f"Controller deadlines and code-bound continuations: {json.dumps(value['controller_runs'])}; {json.dumps(continuations)}.",
            "Account queue capacity is not established by this offline diagnostic. Missing/invalid/deferred processing is not negative eligibility. Costs are estimates, not invoices. Zero provider/model calls, embeddings, retries, reservation releases or restarts. Exact protected report retained; record_presentation does not support this technical kind."])
        return present(self, session, "luna_batch_capacity_diagnostic", value, "\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = CapacityResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args), objective="Diagnose retained count-action collisions and shared-budget capacity without retry or dispatch", actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "count_summary", "charged_estimate_usd", "reserved_usd")}), flush=True)
    finally:
        engine.close()
