"""Registered compact projection of saved Astra reasons, without source passages."""
import hashlib
import json
from pathlib import Path

import run_summary_fidelity_diagnostic as diagnostic
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-summary-fidelity-reason-view-20261023-v1"
OWNER = diagnostic.runner.preparation.OWNER.parent / METHOD


def project(details):
    rows = []
    for number, item in enumerate(details, 1):
        parsed = item["parsed"] or {}
        selected = item["selection"]
        reason = parsed.get("reason")
        rows.append({"case": number, "stratum": selected["stratum"], "outcome": item["outcome"],
            "summary_version": selected["summary_version"], "summary_record": selected["summary_record"],
            "response_record": item["response_record"], "prior_luna_probabilities": selected.get("grounding_probabilities"),
            "model_reason": reason[:2000] if reason else None, "model_reason_truncated": bool(reason and len(reason) > 2000),
            "claim_paths": parsed.get("claim_paths", []), "affected_claim_hashes": [
                {k: claim[k] for k in ("path", "value_sha256")} for claim in parsed.get("affected_claims", [])],
            "source_locations": [{k: location[k] for k in ("document_id", "field", "start", "end", "text_sha256")}
                                 for location in parsed.get("selected_passage_locations", [])],
            "validation_error": item["validation_error"]})
    return rows


class Study(Research):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "procedure": "Read immutable diagnostic plan and latest report in a separate protected read-only observer. Project existing model reason text up to2000characters with explicit truncation flag, original strata/probabilities, claim paths/hashes and source offset/hash metadata. Never return source passages, citation quote text or affected claim values. No new labels/models/worker writes; reasons are model findings, not adjudicated facts."},
            "question": {"text": "What concrete reasons did the saved independent Astra summary diagnostic give?"},
            "selection": {"rules": "Every selected case in latest completed or partial diagnostic report; preserve unknown/invalid/unattempted outcomes."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = diagnostic.runner.preparation.screening.original.base.pilot.Source(diagnostic.runner.preparation.OWNER)
        try:
            plan = source.one("cyber_summary_fidelity_diagnostic_plan")
            report = source.rows("cyber_summary_fidelity_diagnostic_report")[-1]
            if plan["implementation"] != diagnostic.implementation() or report["diagnostic_plan"] != plan["_record_id"]:
                raise AuditError("summary_fidelity_reason_view_binding_changed")
            details = json.loads(source.artifacts.read(report["details_artifact"]))
            result = {"observed_at": utc(), "versions": versions, "source_owner": str(source.owner), "source_head": source.head(),
                "diagnostic_plan": plan["_record_id"], "diagnostic_report": report["_record_id"],
                "stratum_labels": report["stratum_labels"], "selected": report["selected"],
                "cases": project(details), "new_model_calls": 0, "worker_mutations": 0,
                "limitation": "Saved model rationale only; no independent semantic adjudication or population extrapolation.",
                "exact_chat_presentation_capture_supported": False}
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_summary_fidelity_reason_view", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Inspect saved summary diagnostic reasons without source passages",
                                       actor="codex:summary-fidelity-reason-view")))
    finally:
        study.close()
