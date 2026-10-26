"""Inspect frozen validation disagreements through the existing audited runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from newsresearch.common import AuditError, Config
from newsresearch.runtime import audited_handler
from validate_luna_incident_screening import Study, core, implementation


class Inspection(Study):
    @audited_handler
    def _status(self, session, context, data):
        plan = self.one("screen_validation_plan")
        frozen = self.one("screen_validation_references_frozen")
        report = self.one("screen_validation_report")
        if (plan["implementation"] != implementation() or self.ledger.unresolved
                or report["frozen_references"] != frozen["_record_id"]
                or report["sample_size"] != plan["count"]):
            raise AuditError("completed_unchanged_validation_required")
        protocol = self._version(session, context, {
            "kind": "protocol", "key": "luna-screen-validation-disagreement-inspection-v1",
            "content": {
                "method": "Post-unblinding descriptive inspection of existing frozen disagreements; no relabeling, new sampling, tuning or model call.",
                "validation_plan": plan["_record_id"], "report": report["_record_id"],
                "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "limitations": "Current-Codex references; not human gold or population accuracy.",
            },
        })["id"]
        items = {r["ordinal"]: r for r in self.ledger.artifacts.read(plan["items"])}
        rows = self.ledger.artifacts.read(report["details"])
        if len(rows) != plan["count"]:
            raise AuditError("comparison_coverage_mismatch")
        disagreements = []
        for row in rows:
            reference = row["reference"]
            if all(reference[k] == row["luna"]["answers"][k]["label"] for k in core.LABELS):
                continue
            disagreements.append({
                "ordinal": row["ordinal"], "title": items[row["ordinal"]]["title"],
                "reference": {k: reference[k] for k in core.LABELS},
                "reference_route": core.route(reference["event_scope"], reference["ai_incident"]),
                "luna": row["luna"],
                "scope_rationale": reference["scope_rationale"],
                "incident_rationale": reference["incident_rationale"],
            })
        result = {"protocol": protocol, "report": report["_record_id"],
                  "disagreements": disagreements, "new_model_calls": 0,
                  "changed_references": 0, "human_validated": False}
        identifier = self.ledger.record(session, "screen_validation_disagreement_inspection", protocol, result)
        return {"id": identifier, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    engine = Inspection(args.workspace, config=Config(offline=True))
    try:
        result = engine.execute("status", {"action": "inspect_frozen_comparison"},
                                objective="Explain existing frozen screening-validation disagreements",
                                actor="codex:luna-screening-validation")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
