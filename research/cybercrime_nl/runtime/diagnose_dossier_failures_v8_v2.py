"""Read-only continuation diagnosis; reuse the frozen technical projection."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import diagnose_dossier_failures_v8 as prior
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-v8-failure-technical-view-20261023-v2"
ACTIVE_OWNER, Source, runner = prior.ACTIVE_OWNER, prior.Source, prior.runner
OWNER = ACTIVE_OWNER.parent / METHOD
AMENDMENT = prior.AMENDMENT
BASELINE_REPORT = prior.REPORT
REPORT = "a8519102194effa9a837068f9207e58ba37a6db40475ed66a22b368b2dd43001"
BASELINE_DIAGNOSTIC = "feeef29d4c6173155bc14b3dddf484a278da426880b6fa18ad4e45c1fcc64222"
BASELINE_TOTAL, EXPECTED_TOTAL, EXPECTED_ADDITIONAL, EXPECTED_ADDITIONAL_HOLDS = 2407, 2607, 200, 4


def require(value, message):
    if not value:
        raise AuditError("dossier_v8_continuation_diagnosis_" + message)


def continuation_rows(all_rows, baseline, report):
    require(len(all_rows) == report["stored_responses"] == EXPECTED_TOTAL
        and baseline["stored_responses"] == BASELINE_TOTAL, "count_boundary_changed")
    before, after = all_rows[:BASELINE_TOTAL], all_rows[BASELINE_TOTAL:]
    require(len(after) == EXPECTED_ADDITIONAL and all(r["at"] <= baseline["at"] for r in before)
        and all(baseline["at"] < r["at"] <= report["at"] for r in after)
        and all(r.get("execution_amendment") == AMENDMENT and r["phase"] == "card_quality" for r in after), "response_interval_changed")
    old_holds = sum(r["hold"] for r in before if r.get("execution_amendment") == AMENDMENT)
    new_holds = sum(r["hold"] for r in after)
    require(old_holds == baseline["new_unresolved_holds"] and new_holds == EXPECTED_ADDITIONAL_HOLDS
        and old_holds + new_holds == report["new_unresolved_holds"], "hold_boundary_changed")
    return before, after


def inspect(source, fresh_head):
    head = source.head()
    amendment = source.one("cyber_dossier_execution_amendment_v8")
    reports = {r["_record_id"]: r for r in source.rows("cyber_dossier_report")}
    require(REPORT in reports and BASELINE_REPORT in reports, "bound_reports_missing")
    baseline, report = reports[BASELINE_REPORT], reports[REPORT]
    require(amendment["_record_id"] == AMENDMENT and amendment["implementation"] == runner.implementation()
        and all(r["execution_amendment"] == AMENDMENT and r["plan"] == amendment["parent_plan"]
                for r in (baseline, report)), "lineage_changed")
    before, after = continuation_rows(source.rows("cyber_dossier_response"), baseline, report)
    require(all(r["plan"] == amendment["parent_plan"] for r in after), "response_plan_changed")
    workers = runner.BASE.PARAMETERS["workers"]
    final_ids = {r["_record_id"] for r in after[-workers:]}
    selected = [r for r in after if r["hold"] or not r["parsed"] or r["_record_id"] in final_ids]
    cases = [prior.technical_view(r, source.artifacts.json(r["packet"]), source.artifacts.json(r["response"])) for r in selected]
    require(fresh_head() == head, "source_changed")
    return {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head, "source_head_stable": True,
        "source_report": REPORT, "source_report_at": report["at"], "baseline_report": BASELINE_REPORT,
        "baseline_diagnostic": BASELINE_DIAGNOSTIC, "execution_amendment": AMENDMENT,
        "provider_responses_before": len(before), "provider_responses_after": len(before) + len(after),
        "continuation_responses": len(after), "continuation_stored_parsed": sum(bool(r["parsed"]) and not r["hold"] for r in after),
        "continuation_failed_or_held": sum(r["hold"] or not r["parsed"] for r in after),
        "v8_holds_before": baseline["new_unresolved_holds"], "v8_holds_after": report["new_unresolved_holds"],
        "new_continuation_holds": prior.aggregate([c for c in cases if c["hold"]]),
        "continuation_failures": prior.aggregate([c for c in cases if c["hold"] or not c["stored_parsed"]]),
        "last_card_quality_wave": prior.aggregate([c for c in cases if c["record"] in final_ids]),
        "wave_failure_counts": [sum(r["hold"] or not r["parsed"] for r in after[start:start+workers])
                                for start in range(0, len(after), workers)],
        "wave_hold_counts": [sum(r["hold"] for r in after[start:start+workers]) for start in range(0, len(after), workers)],
        "stored_validation_error_counts": dict(Counter(prior.safe.safe_code(r["validation_error"]) or "none" for r in after)),
        "new_model_calls": 0, "new_cost_nanousd": 0, "outputs_modified": False, "holds_released": False,
        "limitation": "The fixed continuation interval is split into configured-size completion waves; no unrecorded error cause or semantic quality is inferred."}, cases


class Diagnostic(Research):
    def __init__(self, workspace, *args, **kwargs):
        require(Path(workspace).resolve() != Path(ACTIVE_OWNER).resolve(), "owner_must_be_separate")
        super().__init__(workspace, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and not data, "offline_empty_input_required")
        code = {**runner.implementation(), **{str(p.relative_to(runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(prior.__file__), Path(prior.safe.__file__))}}
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": code,
                "procedure": "Select only the fixed200 additional card-quality response rows between exact2407/2607 stopped-report boundaries. Verify timestamps, amendment and four added holds against old/current reports. Reuse frozen technical envelope/billing projection for every failed/held response plus final worker-count wave; preserve exact IDs privately and expose technical aggregates only. Include configured-wave fault/hold counts. Fresh read-only source head check. No calls, retries, original edits, parser changes, semantic judgments or hold release."},
            "question": {"text": "Which technical outcomes caused the second v8 continuation stop, separately from the first interval?"},
            "selection": {"rules": "Exact200 continuation responses after the first2407; all four new holds and final8 responses; no replacement."},
            "profile": {"mode": "exploratory", "population_estimate": False},
        }.items():
            versions[kind] = self._version(session, context, {"kind": kind, "key": METHOD, "content": content})["id"]
        source = Source(ACTIVE_OWNER)
        try:
            def fresh_head():
                fresh = Source(ACTIVE_OWNER)
                try:
                    return fresh.head()
                finally:
                    fresh.close()
            result, cases = inspect(source, fresh_head)
        finally:
            source.close()
        result.update(versions=versions, protected_cases_artifact=self.ledger.artifacts.put(cases))
        identity = self.ledger.record(session, "cyber_dossier_v8_failure_technical_view_v2", digest(result), result)
        return {"id": identity, **result}


if __name__ == "__main__":
    study = Diagnostic(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Diagnose fixed v8 continuation responses without restart or retries", actor="codex:v8-technical-view")))
    finally:
        study.close()
