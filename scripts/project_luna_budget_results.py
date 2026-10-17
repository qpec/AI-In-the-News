"""Append an audited deterministic literal-reference projection; never retry."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
from luna_batch_budget_run import OWNER, STUDY, present, save
from luna_batch_literal_projection import project_literal_refs
from luna_event_contract_v2 import contract_digest


class ProjectionResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        plan_id = data["plan"]
        plan = self.ledger.get(plan_id, "luna_budget_execution_plan")
        if not self.config.offline or plan["authorization_id"] != STUDY or plan["contract_sha256"] != contract_digest():
            raise AuditError("literal_projection_scope_changed")
        implementation = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).with_name("luna_batch_literal_projection.py"))}
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":literal-projection",
            "content": {"method": "literal-reference-subset-projection-v1", "plan": plan_id,
                "implementation": implementation, "contract_sha256": plan["contract_sha256"],
                "retrospective": True, "rules": "Preserve original assessments and statuses. For observed complete content-valid/invalid responses only, derive a copy by removing original literal refs that lack the exact unchanged surface, only if at least one original ref remains. No new text, refs, roles or facts. Unknown/excluded refs unchanged. Revalidate unchanged contract. This is mechanical normalization, not semantic accuracy or acceptance."}})["id"]
        self.ledger.append(session, "budget.literal_projection.inspection.intended", {"plan": plan_id, "protocol": protocol,
            "sql": "SELECT id FROM records WHERE kind='luna_budget_assessment'"})
        outcomes = []
        for item in self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_budget_assessment'"):
            original = self.ledger.get(item["id"], "luna_budget_assessment")
            if original["plan"] != plan_id:
                continue
            key = item["id"] + ":" + protocol
            existing = self.ledger.db.execute("SELECT id FROM records WHERE kind='luna_budget_literal_projection' AND logical_key=?", (key,)).fetchone()
            if existing:
                outcomes.append(self.ledger.get(existing["id"], "luna_budget_literal_projection"))
                continue
            parsed = self.ledger.artifacts.read(original["response"])
            packet = self.ledger.artifacts.read(original["packet_ref"])
            output = parsed.get("result") if parsed.get("result") is not None else parsed.get("rejected_output")
            projected = project_literal_refs(output, packet, response_status=parsed.get("provider_status"), response_truncated=False)
            reference = save(self, session, projected, "Deterministic projection with original errors and exact citation transformations")
            value = {"plan": plan_id, "protocol": protocol, "original_assessment": item["id"],
                "custom_id": original["custom_id"], "corpus_id": original["corpus_id"],
                "original_status": original["status"], "derived_valid": projected["valid"],
                "changed": projected["changed"], "projection": reference,
                "remaining_errors": projected["derived_errors"], "title": original["title"], "url": original["url"],
                "accepted": False, "human_validated": False}
            self.ledger.record(session, "luna_budget_literal_projection", key, value)
            outcomes.append(value)
        raw = Counter(row["original_status"] for row in outcomes)
        recovered = [row for row in outcomes if row["original_status"] != "valid" and row["derived_valid"]]
        valid = sum(row["derived_valid"] for row in outcomes)
        value = {"plan": plan_id, "protocol": protocol, "rows": len(outcomes), "original_status_counts": dict(raw),
            "derived_valid": valid, "derived_invalid": len(outcomes) - valid, "mechanically_recovered": len(recovered),
            "new_models": 0, "paid_retries": 0, "original_status_changes": 0,
            "recovered": recovered, "remaining": [row for row in outcomes if not row["derived_valid"]]}
        lines = [f"Offline literal-reference projection: **{valid}/{len(outcomes)} derived records pass the unchanged mechanical validator**; "
                 f"{len(recovered)} recovered without new inference. Original statuses remain {dict(raw)}. "
                 f"{len(outcomes) - valid} derived records remain invalid.", "",
                 "Only surplus references lacking an unchanged literal were removed when another original reference contained it. "
                 "No extracted values, roles or facts were changed; all original responses and citations remain retained.", ""]
        for row in recovered:
            lines.append(f"- [{row['title']}](<{row['url']}>) — {row['corpus_id']}; separately derived citation subset passes.")
        lines.extend(["", "Zero new model calls, paid retries, source collection or membership changes. This retrospective software projection "
            "does not establish semantic correctness or human accuracy. Exact protected presentation retained; record_presentation does not support this technical kind."])
        return present(self, session, "luna_budget_projection_result", value, "\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    engine = ProjectionResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", {"plan": args.plan}, objective="Derive exact literal-reference subsets without paid retries, preserving original Batch failures", actor="codex:luna-batch-budget")
        print(result["markdown"])
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}))
    finally:
        engine.close()
