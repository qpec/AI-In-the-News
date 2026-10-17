"""Audited offline replay of one retained Responses phase-envelope failure."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config
from newsresearch.event_batch_live_gateway import EventBatchLiveGateway, RECEIPT_KIND
from newsresearch.runtime import Research, audited_handler
from luna_batch_budget_run import OWNER, STUDY, present, save
from luna_batch_phase_projection import project_final_answer_phase
from luna_event_contract_v2 import contract_digest


class PhaseReplayResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        if not self.config.offline or self.ledger.root.resolve() != OWNER.resolve():
            raise AuditError("phase_replay_requires_original_offline_owner")
        plan_id, original_id = data["plan"], data["assessment"]
        root = Path(__file__).resolve().parents[1]
        implementation = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in (
            "scripts/replay_luna_budget_phase.py", "scripts/luna_batch_phase_projection.py",
            "scripts/luna_batch_results.py", "scripts/luna_event_contract_v2.py")}
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":phase-replay",
            "content": {"method": "retained-final-answer-phase-replay-v1", "plan": plan_id,
                "original_assessment": original_id, "implementation": implementation,
                "official_reference": "https://developers.openai.com/api/docs/guides/deployment-checklist",
                "documentation_provenance": "Official page fetched by assistant web tool; acquisition not gateway-retained",
                "rules": "Offline replay of the exact retained phase-envelope failure. Select a unique explicit final_answer after only completed assistant commentary; preserve all original bytes and unchanged final text. Revalidate the unchanged JSON/literal contract; reject ambiguity, tools, refusals or incomplete usage. No model call, retry, status overwrite or automatic restart."},
            "amend_latest": True, "reason": "Bind an explicit retrospective envelope compatibility replay"})["id"]
        self.ledger.append(session, "budget.phase_replay.inspection.intended", {
            "plan": plan_id, "assessment": original_id, "protocol": protocol})
        plan = self.ledger.get(plan_id, "luna_budget_execution_plan")
        original = self.ledger.get(original_id, "luna_budget_assessment")
        if (plan["authorization_id"] != STUDY or plan["contract_sha256"] != contract_digest()
                or original["plan"] != plan_id or original["status"] != "error"
                or original["errors"] != ["response:not_single_message"]):
            raise AuditError("phase_replay_original_scope_mismatch")
        saved = EventBatchLiveGateway(self, self.gateway.provider).load_book(session, STUDY)
        if saved is None:
            raise AuditError("phase_replay_missing_budget")
        book, state = saved
        cost = book.entry(original["custom_id"])
        if book.frozen or cost["status"] != "settled" or not cost["accepted"]:
            raise AuditError("phase_replay_requires_complete_settlement")
        sql = "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1"
        parameters = ["luna_budget_job_parsed", original["manifest"]]
        self.ledger.append(session, "budget.phase_replay.lookup.intended", {"sql": sql, "parameters": parameters})
        checkpoint = self.ledger.db.execute(sql, parameters).fetchone()
        if checkpoint is None:
            raise AuditError("phase_replay_parse_checkpoint_missing")
        parsed = self.ledger.get(checkpoint["id"], "luna_budget_job_parsed")
        if parsed["plan"] != plan_id or parsed["job_id"] != original["job_id"]:
            raise AuditError("phase_replay_provider_lineage_mismatch")
        matches = []
        for receipt_id in parsed["download_receipts"].values():
            receipt = self.ledger.get(receipt_id, RECEIPT_KIND)
            reference = receipt["body_ref"]
            self.ledger.append(session, "budget.phase_replay.file.inspection.intended", {
                "artifact": reference, "custom_id": original["custom_id"], "receipt": receipt_id})
            for number, line in enumerate(self.ledger.artifacts.read_bytes(reference).splitlines(), 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("custom_id") == original["custom_id"]:
                    matches.append((row, reference, number, hashlib.sha256(line).hexdigest()))
        if len(matches) != 1:
            raise AuditError("phase_replay_requires_one_retained_row")
        row, file_ref, line_number, line_sha = matches[0]
        self.ledger.append(session, "budget.phase_replay.packet.inspection.intended", {
            "packet_ref": original["packet_ref"], "request_body_ref": original["request"],
            "purpose": "Unchanged mechanical schema and exact literal validation only"})
        task = {"packet": self.ledger.artifacts.read(original["packet_ref"]),
                "body": self.ledger.artifacts.read(original["request"])}
        projected = project_final_answer_phase(row, task)
        projection_ref = save(self, session, projected, "Separate final-answer envelope replay with exact provenance")
        assessment = projected["assessment"]
        value = {"plan": plan_id, "protocol": protocol, "versions": plan["versions"],
            "original_assessment": original_id, "custom_id": original["custom_id"],
            "manifest": original["manifest"], "packet_ref": original["packet_ref"],
            "request_body_ref": original["request"], "original_response": original["response"],
            "provider_file_ref": file_ref, "raw_line_number": line_number,
            "raw_line_sha256": line_sha, "raw_line_hash_encoding": "UTF-8 line bytes without line terminator",
            "projection_ref": projection_ref,
            "phase_implementation_sha256": implementation["scripts/luna_batch_phase_projection.py"],
            "derived_status": assessment["status"],
            "derived_output": assessment.get("result"), "derived_errors": assessment.get("errors"),
            "budget_state": state, "cost_status": cost["status"], "new_models": 0,
            "original_status_unchanged": True, "human_validated": False, "accepted": False}
        output = assessment.get("result") or {}
        markdown = (f"Offline phase replay: one retained response; derived status **{assessment['status']}**, "
            f"focus **{output.get('focus', 'unavailable')}**; errors {assessment.get('errors', [])}. "
            f"Source: [{original['title']}](<{original['url']}>). "
            "The explicit final_answer was selected under a separate documented envelope rule. "
            "The original error, commentary, final message and cost remain retained. "
            "Zero new model calls, paid retries, membership changes or controller restarts. "
            "Mechanical validation is not semantic accuracy. Exact protected Markdown retained; "
            "record_presentation does not support this technical kind.")
        return present(self, session, "luna_budget_phase_replay", value, markdown)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--assessment", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = PhaseReplayResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", vars(args),
            objective="Replay one retained final-answer phase envelope without inference or rewriting history",
            actor="codex:luna-batch-budget")
        print(result["markdown"], flush=True)
        print(json.dumps({key: result[key] for key in ("id", "presentation", "derived_status", "projection_ref")}), flush=True)
    finally:
        engine.close()
