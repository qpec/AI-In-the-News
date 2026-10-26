"""Separate post-hoc ambiguity sensitivity; never edits the frozen reference study."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from newsresearch import astra_incident_validation as method
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler
from validate_incident_decisions_astra import BASE, METHOD, Source, state

DIAGNOSTIC = "astra-incident-route-sensitivity-20261022-v1"


def route_sensitivity(cases, frame_sizes):
    tentative = deepcopy(cases)
    for row in tentative:
        if row.get("reference"):
            row["reference"]["boundary_ambiguous"] = False
    return method.metrics(tentative, frame_sizes)


class Study(Research):
    @audited_handler
    def _status(self, session, context, data):
        phase = data["phase"]
        if phase not in {"pilot", "all"}:
            raise AuditError("sensitivity_unknown_phase")
        versions = {}
        for kind, content in {
            "protocol": {"method": DIAGNOSTIC, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "procedure": "Post-hoc descriptive sensitivity prompted by the pilot's broad ambiguity flags. Read the frozen pilot/final report and references only after their primary report exists. Tabulate saved routes with and without removing boundary-flagged binary judgments; retain actual review/missing routes. Use the original stratified metrics unchanged. Do not change saved flags, labels, prompts, samples or primary results. Read completed transport metadata to report configured/observed model, returned token usage and unknown batches. No source text or new model judgments.",
                "limitations": "Secondary exploratory analysis, not preregistered primary validation or human gold. Flags may represent label ambiguity without route ambiguity. Counting a tentative binary route does not resolve its semantic uncertainty."},
            "question": {"text": "How sensitive is the reported confusion matrix to counting boundary-flagged but binary Astra routes?"},
            "selection": {"rules": "Exactly the cases and completed requests corresponding to the saved pilot or final report", "phase": phase},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": DIAGNOSTIC + "-" + phase, "content": content,
                "amend_latest": True, "reason": "Register a separate post-hoc sensitivity without changing primary judgments"})["id"]
        source = Source(BASE / METHOD)
        try:
            rows = list(source.db.execute("SELECT * FROM records WHERE kind=? AND json_extract(payload,'$.phase')=? ORDER BY created_event",
                                          ("astra_validation_report", phase)))
            if not rows:
                raise AuditError("sensitivity_primary_report_missing")
            source.artifacts.check(rows[-1]["artifact"])
            report = state.row_value(rows[-1], "astra_validation_report")
            cases = source.artifacts.json(report["cases"])
            primary = method.metrics(cases, report["metrics"]["population_strata"])
            if primary != report["metrics"]:
                raise AuditError("sensitivity_primary_replay_mismatch")
            secondary = route_sensitivity(cases, primary["population_strata"])
            models, usage, outcomes = Counter(), Counter(), Counter()
            for raw in source.db.execute("SELECT * FROM records WHERE kind=? ORDER BY created_event", ("astra_validation_response",)):
                source.artifacts.check(raw["artifact"])
                row = state.row_value(raw, "astra_validation_response")
                if phase == "pilot" and row["phase"] != "pilot":
                    continue
                models[row.get("model_observed") or "unobserved"] += 1
                outcomes["valid" if row["references"] else "invalid_or_unknown"] += 1
                if row["configured_model"] != method.MODEL:
                    raise AuditError("sensitivity_wrong_configured_model")
                for key, value in (row.get("usage") or {}).items():
                    if type(value) is int:
                        usage[key] += value
            result = {"phase": phase, "versions": versions, "source_report": report["_record_id"],
                "strict_primary": primary, "secondary_stated_routes": secondary,
                "configured_model": method.MODEL, "observed_models_by_request": dict(models),
                "returned_token_usage": dict(usage), "request_outcomes": dict(outcomes),
                "codex_account_dollar_cost": None, "new_api_calls": 0,
                "reference_changes": 0, "human_validated": False, "at": utc()}
        finally:
            source.close()
        identifier = self.ledger.record(session, "astra_route_sensitivity_report", digest(result), result)
        result = {"id": identifier, **result}
        (self.ledger.root / (phase + "-sensitivity-report.json")).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["pilot", "all"], default="all")
    args = parser.parse_args()
    study = Study(BASE / DIAGNOSTIC, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {"phase": args.phase}, objective="Describe route-level sensitivity of frozen Astra references", actor="codex:astra-sensitivity")))
    finally:
        study.close()


if __name__ == "__main__":
    main()
