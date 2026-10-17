"""Offline mechanical replay of retained canary validation errors; no judging."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from newsresearch.common import Config
from newsresearch.runtime import Research, audited_handler
from luna_batch_budget_run import OWNER, STUDY, present

PLAN = "5ca47b44989d35bd364dc8a23b04a2509382085641e646ac3a9f5ca01032335f"


class DiagnosticResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = self._version(session, context, {"kind": "protocol", "key": STUDY + ":canary-errors",
            "content": {"method": "retained-canary-error-codes-v1", "plan": PLAN,
                "implementation": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "rules": "Count retained mechanical errors and show affected source titles/links; no new semantic judgement, source-body inspection, retry, model or status change."}})["id"]
        self.ledger.append(session, "budget.canary_errors.inspection.intended", {"plan": PLAN, "protocol": protocol,
            "sql": "SELECT id FROM records WHERE kind='luna_budget_assessment'"})
        rows = [self.ledger.get(row["id"], "luna_budget_assessment") for row in self.ledger.db.execute(
            "SELECT id FROM records WHERE kind='luna_budget_assessment'")]
        rows = [row for row in rows if row["plan"] == PLAN]
        errors = Counter(error for row in rows for error in row["errors"])
        cases = [{key: row.get(key) for key in ("custom_id", "corpus_id", "status", "errors", "title", "url")}
                 for row in rows if row["status"] != "valid"]
        value = {"plan": PLAN, "protocol": protocol, "inspected": len(rows), "invalid": len(cases),
                 "error_counts": dict(errors), "cases": cases, "new_model_calls": 0, "status_changes": 0}
        lines = [f"Offline canary error replay: {len(rows)} retained assessments, {len(cases)} invalid outputs. "
                 "Zero new models, source-body reads, retries or status changes.", ""]
        for row in cases:
            lines.append(f"- [{row['title']}](<{row['url']}>) — {row['corpus_id']}: " + ", ".join(row["errors"]))
        lines.extend(["", "These are validator diagnostics, not a semantic assessment or evidence that invalid articles lack events. "
            "Exact protected presentation retained; record_presentation does not support this technical kind."])
        return present(self, session, "luna_budget_canary_error_diagnostic", value, "\n".join(lines))


if __name__ == "__main__":
    engine = DiagnosticResearch(OWNER, config=Config(offline=True))
    try:
        result = engine.execute("status", {}, objective="Diagnose six retained full-text Batch canary validation failures before spending further", actor="codex:luna-batch-budget")
        print(result["markdown"])
        print(json.dumps({key: value for key, value in result.items() if key != "markdown"}))
    finally:
        engine.close()
