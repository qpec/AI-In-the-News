"""Explicit, append-only continuation after a proven response-phase mismatch.

This acknowledges one settled historical parser error. It never changes that
assessment, the stopped controller, the original deadline or shared accounting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from typing import Any

from newsresearch.common import AuditError, Config, Context, Json, require_active
from newsresearch.event_batch_live_gateway import ACTION_KIND, RECEIPT_KIND, STOP_KIND
from newsresearch.runtime import audited_handler

from execute_luna_budget_batch import ExecutionResearch, PLAN_KIND
from luna_batch_budget_run import OWNER, ROOT, STUDY, present
import luna_event_contract_v2 as contract
from luna_batch_phase_projection import project_final_answer_phase

CONTINUATION_KIND = "luna_budget_phase_continuation"
PROOF_KIND = "luna_budget_phase_replay"
RUN_KIND = "luna_budget_controller_run"
FINISH_KIND = "luna_budget_controller_finish"
ASSESSMENT_KIND = "luna_budget_assessment"
INSTRUCTION = "if everything checks out run it full"


def code_hashes() -> dict[str, str]:
    names = ("luna_budget_continuation.py", "luna_batch_phase_projection.py", "luna_batch_results.py",
             "run_luna_budget_workflow.py", "poll_luna_budget_batch.py", "prepare_luna_budget_wave.py",
             "execute_luna_budget_wave.py")
    return {name: hashlib.sha256((ROOT / "scripts" / name).read_bytes()).hexdigest() for name in names}


def validate_proof_fields(plan_id: str, proof: Json, assessment_id: str, assessment: Json,
                          entry: Json, phase_hash: str) -> None:
    """Pure binding check; the caller additionally replays the retained raw line."""
    if (proof.get("plan") != plan_id or proof.get("original_assessment") != assessment_id
            or assessment.get("plan") != plan_id or assessment.get("status") != "error"
            or assessment.get("errors") != ["response:not_single_message"]
            or assessment.get("technical_failure") is not True
            or proof.get("derived_status") != "valid" or proof.get("cost_status") != "settled"
            or proof.get("new_models") != 0 or proof.get("original_status_unchanged") is not True
            or proof.get("phase_implementation_sha256") != phase_hash):
        raise AuditError("continuation_exact_phase_proof_required")
    for proof_key, assessment_key in (("custom_id", "custom_id"), ("manifest", "manifest"),
            ("packet_ref", "packet_ref"), ("request_body_ref", "request"), ("original_response", "response")):
        if not proof.get(proof_key) or proof[proof_key] != assessment.get(assessment_key):
            raise AuditError("continuation_proof_assessment_binding_changed")
    request, settlement = entry.get("request", {}), entry.get("settlement") or {}
    if (entry.get("status") != "settled" or entry.get("accepted") is not True
            or request.get("plan_id") != plan_id or request.get("request_id") != proof["custom_id"]
            or request.get("request_sha256") != proof["request_body_ref"]
            or settlement.get("complete") is not True
            or settlement.get("model") != assessment.get("model")
            or settlement.get("input_tokens") != request.get("input_count", {}).get("input_tokens")
            or type(settlement.get("output_tokens")) is not int
            or not 0 <= settlement["output_tokens"] <= request.get("max_output_tokens", -1)):
        raise AuditError("continuation_exact_settled_cost_required")


def checked_proof(engine: ExecutionResearch, session: str, plan_id: str, proof_id: str) -> Json:
    require_active(engine, session)
    engine.ledger.append(session, "budget.continuation.proof_inspection.intended", {"plan": plan_id, "proof": proof_id})
    proof = engine.ledger.get(proof_id, PROOF_KIND)
    assessment_id = proof["original_assessment"]
    assessment = engine.ledger.get(assessment_id, ASSESSMENT_KIND)
    saved = engine.gateway.load_book(session, STUDY)
    if saved is None:
        raise AuditError("continuation_existing_budget_required")
    book, state = saved
    phase_hash = code_hashes()["luna_batch_phase_projection.py"]
    validate_proof_fields(plan_id, proof, assessment_id, assessment, book.entry(proof["custom_id"]), phase_hash)
    engine.ledger.get(proof["protocol"], "protocol")
    original = engine.ledger.artifacts.read(proof["original_response"])
    if (original.get("usage_complete") is not True or original.get("errors") != ["response:not_single_message"]
            or original.get("observed_model") != book.price_policy.model):
        raise AuditError("continuation_original_response_not_complete")
    raw_file = engine.ledger.artifacts.read_bytes(proof["provider_file_ref"])
    lines = [line for line in raw_file.splitlines() if hashlib.sha256(line).hexdigest() == proof["raw_line_sha256"]]
    if len(lines) != 1:
        raise AuditError("continuation_exact_raw_line_not_unique")
    row = json.loads(lines[0])
    if row.get("custom_id") != proof["custom_id"]:
        raise AuditError("continuation_raw_custom_id_changed")
    task = {"packet": engine.ledger.artifacts.read(proof["packet_ref"]),
            "body": engine.ledger.artifacts.read(proof["request_body_ref"])}
    projection = project_final_answer_phase(row, task)
    retained = engine.ledger.artifacts.read(proof["projection_ref"])
    if (projection != retained or projection.get("valid") is not True
            or projection.get("assessment", {}).get("status") != "valid"
            or projection["assessment"].get("result") != proof.get("derived_output")):
        raise AuditError("continuation_derived_final_validation_failed")
    if book.frozen or any(book.entry(event["value"]["request_id"])["status"] in {"unknown", "frozen", "overrun"}
                           for event in book.to_dict()["events"] if event["action"] == "reserve"):
        raise AuditError("continuation_unknown_or_frozen_cost")
    if engine.ledger.db.execute("SELECT 1 FROM records WHERE kind=? AND logical_key=?", (STOP_KIND, STUDY)).fetchone():
        raise AuditError("continuation_gateway_stop_preserved")
    return {"proof": proof_id, "assessment": assessment_id, "custom_id": proof["custom_id"],
            "budget_state": state, "phase_implementation_sha256": phase_hash}


def load_continuation(engine: Any, session: str, plan_id: str, reference: str | None,
                      *, for_admission: bool = False) -> Json | None:
    if reference is None:
        return None
    require_active(engine, session)
    value = engine.ledger.get(reference, CONTINUATION_KIND)
    if (value.get("plan") != plan_id or value.get("authorization_id") != STUDY
            or value.get("implementation") != code_hashes()):
        raise AuditError("continuation_binding_or_code_changed")
    verified = checked_proof(engine, session, plan_id, value["proof"])
    if any(value.get(key) != verified[key] for key in ("assessment", "custom_id", "phase_implementation_sha256")):
        raise AuditError("continuation_acknowledgment_changed")
    original = engine.ledger.get(value["original_run"], RUN_KIND)
    stopped = engine.ledger.get(value["original_stop"], FINISH_KIND)
    if (original.get("plan") != plan_id or stopped.get("run") != value["original_run"]
            or stopped.get("reason") != "technical_stop" or value["deadline_epoch"] != original["deadline_epoch"]
            or value["max_per_corpus"] != original["max_per_corpus"]
            or value["max_runtime_seconds"] != original["max_runtime_seconds"]):
        raise AuditError("continuation_original_stop_or_deadline_changed")
    if for_admission and time.time() >= value["deadline_epoch"]:
        raise AuditError("continuation_original_deadline_expired")
    return {**value, "id": reference}


def acknowledged_assessment(row: Json, continuation: Json | None) -> bool:
    return bool(continuation and row.get("id") == continuation["assessment"]
                and row.get("plan") == continuation["plan"] and row.get("technical_failure") is True
                and row.get("custom_id") == continuation["custom_id"]
                and row.get("status") == "error" and row.get("errors") == ["response:not_single_message"])


class ContinuationResearch(ExecutionResearch):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if self.ledger.root.resolve() != OWNER.resolve() or not self.config.offline:
            raise AuditError("continuation_registration_fixed_offline_owner")
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, PLAN_KIND)
        if plan.get("authorization_id") != STUDY or plan.get("contract_sha256") != contract.contract_digest():
            raise AuditError("continuation_original_plan_changed")
        original = self.latest(RUN_KIND, plan_id)
        stopped = self.latest(FINISH_KIND, original[0]) if original else None
        if not original or not stopped or stopped[1].get("reason") != "technical_stop":
            raise AuditError("continuation_original_technical_stop_required")
        implementation = code_hashes()
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":phase-continuation",
            "content": {"method": "exact-settled-phase-error-continuation-v1", "plan": plan_id,
                "implementation": implementation, "versions": plan["versions"], "proof": data["proof"],
                "original_run": original[0], "original_stop": stopped[0],
                "rules": "Preserve stopped execution, raw assessments and shared budget. Acknowledge only exact settled commentary/final_answer parser error after independently replayed valid final output. Original deadline, frozen inputs and output cap remain. Never retry any submitted request. New technical/unknown failure stops; content invalid remains invalid. Mechanical validation is not semantic acceptance."}})["id"]
        verified = checked_proof(self, session, plan_id, data["proof"])
        self.ledger.append(session, "budget.continuation.assessments.inspection.intended",
            {"sql": "SELECT id FROM records WHERE kind=?", "parameters": [ASSESSMENT_KIND]})
        bad = []
        for item in self.ledger.db.execute("SELECT id FROM records WHERE kind=?", (ASSESSMENT_KIND,)):
            row = self.ledger.get(item["id"], ASSESSMENT_KIND)
            if row.get("plan") == plan_id and (row.get("technical_failure") or row.get("status") not in {"valid", "invalid"}):
                bad.append(item["id"])
        if bad != [verified["assessment"]]:
            raise AuditError("continuation_requires_sole_exact_historical_error")
        # These guards remain unconditional; the acknowledgment is not a way to
        # recover an unknown HTTP action or an unrelated execution obstacle.
        inspected: dict[str, list[Json]] = {}
        for kind in (ACTION_KIND, RECEIPT_KIND, "luna_budget_execution_obstacle", "luna_budget_bulk_obstacle"):
            self.ledger.append(session, "budget.continuation.action_inspection.intended",
                {"sql": "SELECT id FROM records WHERE kind=?", "parameters": [kind]})
            inspected[kind] = [self.ledger.get(row["id"], kind) for row in self.ledger.db.execute(
                "SELECT id FROM records WHERE kind=?", (kind,))]
        obstacles = [row for kind in ("luna_budget_execution_obstacle", "luna_budget_bulk_obstacle")
                     for row in inspected[kind] if row.get("plan") == plan_id]
        receipt_map: dict[str, list[Json]] = {}
        for receipt in inspected[RECEIPT_KIND]:
            if receipt.get("authorization_id") == STUDY:
                receipt_map.setdefault(receipt["action_id"], []).append(receipt)
        failed_action = False
        for action in inspected[ACTION_KIND]:
            if action.get("authorization_id") != STUDY:
                continue
            matches = receipt_map.get(action["action_id"], [])
            if (len(matches) != 1 or matches[0].get("unknown") is not False or not matches[0].get("body_ref")
                    or type(matches[0].get("status")) is not int or not 200 <= matches[0]["status"] < 300):
                failed_action = True
        if failed_action or obstacles:
            raise AuditError("continuation_shared_action_or_obstacle_unresolved")
        if verified["custom_id"] in {task["custom_id"] for task in plan["canary_tasks"]}:
            raise AuditError("continuation_cannot_acknowledge_canary_failure")
        if time.time() >= original[1]["deadline_epoch"]:
            raise AuditError("continuation_original_deadline_expired")
        value = {"plan": plan_id, "authorization_id": STUDY, "protocol": protocol,
            "instruction": INSTRUCTION, "approved_by": "user:current-chat", "implementation": implementation,
            **verified, "original_run": original[0], "original_stop": stopped[0],
            "deadline_epoch": original[1]["deadline_epoch"], "max_per_corpus": original[1]["max_per_corpus"],
            "max_runtime_seconds": original[1]["max_runtime_seconds"], "paid_retries": 0,
            "original_stop_unchanged": True, "original_status_unchanged": True}
        key = plan_id + ":" + data["proof"]
        existing = self.latest(CONTINUATION_KIND, key)
        if existing:
            if any(existing[1].get(k) != value[k] for k in value if k != "budget_state"):
                raise AuditError("continuation_registration_changed")
            identifier = existing[0]
        else:
            identifier = self.ledger.record(session, CONTINUATION_KIND, key, value)
        return present(self, session, "luna_budget_continuation_registration", {"continuation_ref": identifier, **value},
            "Registered explicit continuation for one fully settled historical commentary/final_answer parser error, "
            "independently replayed as mechanically valid. Original error and controller stop remain unchanged. "
            "Same plan, shared $120 operating/$150 ceiling, reservations and original deadline; zero retries or new model calls in registration. "
            "Only never-submitted requests may proceed. Invalid content remains invalid; no semantic accuracy or accepted dossiers is established. "
            "Exact report retained in protected storage; record_presentation does not support this technical kind.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--proof", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ContinuationResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args), objective="Register exact proven phase-error continuation under original authorization",
                                actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({"result": result["id"], "continuation_ref": result["continuation_ref"]}), flush=True)
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
