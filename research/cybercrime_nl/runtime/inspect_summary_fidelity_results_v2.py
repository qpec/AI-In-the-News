"""Separate-owner, read-only projection of the fixed-frame diagnostic repair."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import inspect_summary_fidelity_results as previous
import run_summary_fidelity_diagnostic_v2 as diagnostic
from newsresearch.common import AuditError, Config, digest, utc
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-summary-fidelity-reason-view-20261023-v2"
ACTIVE_OWNER = diagnostic.runner.preparation.OWNER
OWNER = ACTIVE_OWNER.parent / METHOD
Source = diagnostic.runner.preparation.screening.original.base.pilot.Source
PLAN_KIND = "cyber_summary_fidelity_diagnostic_amendment_v2"
REPORT_KIND = "cyber_summary_fidelity_diagnostic_report_v2"
project = previous.project  # Reuse the exact reviewed allowlist, without reinterpretation.


def implementation():
    return {str(p.relative_to(diagnostic.runner.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), Path(previous.__file__))}


def _require(condition, name):
    if not condition:
        raise AuditError("summary_fidelity_reason_view_v2_" + name)


def _payload(row):
    return {k: v for k, v in row.items() if k not in {"_record_id", "_logical_key"}}


def _report_digest(row):
    # Source separately verifies the exact payload/artifact and record identity.
    _require(row["_logical_key"] == digest(_payload(row)), "report_digest_changed")


def _details(report, details, tasks):
    _report_digest(report)
    _require(len(details) == len(tasks) == report["selected"], "denominator_changed")
    _require([d["selection"] for d in details] == [t["selection"] for t in tasks], "selection_changed")
    counts = {}
    for item in details:
        outcome, parsed = item["outcome"], item["parsed"]
        _require(outcome in {*diagnostic.contract.LABELS, "unknown_hold", "invalid", "not_attempted"},
                 "unknown_outcome")
        if outcome in diagnostic.contract.LABELS:
            _require(parsed and parsed.get("status") == "valid" and parsed.get("label") == outcome
                     and item["response_record"] is not None and item["unresolved_attempt"] is None,
                     "outcome_parse_disagrees")
        else:
            _require(parsed is None, "unresolved_reclassified")
        if outcome == "unknown_hold":
            _require(item["unresolved_attempt"] is not None, "hold_identity_missing")
        else:
            _require(item["unresolved_attempt"] is None, "unexpected_hold_identity")
        if outcome == "not_attempted":
            _require(item["response_record"] is None, "unattempted_has_response")
        counts.setdefault(item["selection"]["stratum"], Counter())[outcome] += 1
    _require(report["stratum_labels"] == {k: dict(v) for k, v in counts.items()}, "reported_counts_changed")
    _require(report["stored_diagnostic_responses"] == sum(d["response_record"] is not None for d in details),
             "stored_count_changed")
    _require(report["attempted_diagnostic_tasks"] == sum(d["outcome"] != "not_attempted" for d in details),
             "attempted_count_changed")


def validate_lineage(parent, parent_report, parent_details, amendment, report, details):
    """Mechanical consistency only; never derive or replace a substantive label."""
    _require(parent["_record_id"] == diagnostic.PARENT_PLAN
             and parent_report["_record_id"] == diagnostic.PARENT_REPORT
             and parent_report["diagnostic_plan"] == parent["_record_id"], "parent_identity_changed")
    _require(parent["implementation"] == diagnostic.original.implementation()
             and amendment["implementation"] == diagnostic.implementation()
             and amendment["parent_implementation"] == parent["implementation"], "implementation_changed")
    _require(parent["_logical_key"] == diagnostic.original.METHOD
             and amendment["_logical_key"] == diagnostic.METHOD, "plan_key_changed")
    _require(amendment["parent_diagnostic_plan"] == parent["_record_id"]
             and amendment["parent_diagnostic_report"] == parent_report["_record_id"]
             and report["diagnostic_plan"] == amendment["_record_id"]
             and report["parent_diagnostic_plan"] == parent["_record_id"], "repair_lineage_changed")
    for key in ("execution_amendment", "original_deadline"):
        _require(parent[key] == parent_report[key] == amendment[key] == report[key], key + "_changed")
    _require(parent["parent_plan"] == parent_report["plan"] == amendment["parent_plan"] == report["plan"],
             "dossier_plan_changed")
    tasks = parent["tasks"]
    expected_total = diagnostic.EXPECTED_PARENT_ATTEMPTS + diagnostic.EXPECTED_UNTOUCHED
    _require(len(tasks) == expected_total and amendment["original_tasks"] == tasks, "original_frame_changed")
    originals = {t["selection"]["summary_version"]: t for t in tasks}
    _require(len(originals) == expected_total, "duplicate_original_version")
    _details(parent_report, parent_details, tasks)
    _details(report, details, tasks)
    old = {d["selection"]["summary_version"]: d for d in parent_details if d["outcome"] == "unknown_hold"}
    _require(len(old) == diagnostic.EXPECTED_PARENT_ATTEMPTS
             and all(d["outcome"] in {"unknown_hold", "not_attempted"} for d in parent_details),
             "parent_attempt_frame_changed")
    excluded = amendment["excluded_attempts"]
    _require(len(excluded) == len(old) and {r["summary_version"] for r in excluded} == set(old),
             "excluded_frame_changed")
    for row in excluded:
        _require(row["attempt"] == old[row["summary_version"]]["unresolved_attempt"]
                 and row["original_task_key"] == originals[row["summary_version"]]["task_key"]
                 and row["reason"] == "prior_attempt_never_retried", "excluded_identity_changed")
    _require(amendment["required_parent_hold_attempts"] == sorted(d["unresolved_attempt"] for d in old.values()),
             "parent_holds_changed")
    remaining = amendment["tasks"]
    remaining_versions = {t["selection"]["summary_version"] for t in remaining}
    _require(len(remaining) == len(remaining_versions) == diagnostic.EXPECTED_UNTOUCHED
             and remaining_versions == set(originals) - set(old), "repair_frame_changed")
    for task in remaining:
        original = originals[task["selection"]["summary_version"]]
        _require(task["selection"] == original["selection"] and task["original_task_key"] == original["task_key"]
                 and task["original_packet"] == original["packet"], "repair_selection_changed")
    current = {d["selection"]["summary_version"]: d for d in details}
    _require(all(current[version] == item for version, item in old.items()), "old_hold_rewritten")
    _require(report["repair_selected"] == len(remaining)
             and report["repair_stored_responses"] == sum(current[v]["response_record"] is not None for v in remaining_versions),
             "repair_count_changed")
    for key, expected in (("old_gates_modified", False), ("summaries_regenerated", 0),
                          ("human_validated", False), ("population_accuracy_estimate", False)):
        _require(report[key] == expected, "interpretation_changed")
    return {"fixed_original_denominator": expected_total, "preserved_parent_holds": len(old),
            "repair_selected": len(remaining)}


def read_projection(source, fresh_head):
    """Read only saved metadata/details; fresh_head must open a new read snapshot."""
    head = source.head()
    parent = source.one("cyber_summary_fidelity_diagnostic_plan")
    parents = [r for r in source.rows("cyber_summary_fidelity_diagnostic_report")
               if r["_record_id"] == diagnostic.PARENT_REPORT]
    _require(len(parents) == 1, "parent_report_missing")
    parent_report = parents[0]
    amendment = source.one(PLAN_KIND)
    reports = source.rows(REPORT_KIND)
    _require(bool(reports), "repair_report_missing")
    report = reports[-1]
    parent_details = json.loads(source.artifacts.read(parent_report["details_artifact"]))
    details = json.loads(source.artifacts.read(report["details_artifact"]))
    verified = validate_lineage(parent, parent_report, parent_details, amendment, report, details)
    result = {"observed_at": utc(), "source_owner": str(source.owner), "source_head": head,
        "parent_diagnostic_plan": parent["_record_id"], "parent_diagnostic_report": parent_report["_record_id"],
        "diagnostic_plan": amendment["_record_id"], "diagnostic_report": report["_record_id"],
        "report_observed_at": report["at"], "report_details_sha256": report["details_artifact"],
        "stratum_labels": report["stratum_labels"], "selected": report["selected"], **verified,
        "cases": project(details), "new_model_calls": 0, "worker_mutations": 0, "new_substantive_labels": 0,
        "source_head_stable": True,
        "limitation": "Saved model rationale only; no independent semantic adjudication or population extrapolation. All12 original cases remain, including3 prior schema-error holds.",
        "exact_chat_presentation_capture_supported": False}
    _require(fresh_head() == head, "source_changed")
    return result


class Study(Research):
    def __init__(self, root, *args, **kwargs):
        if Path(root).resolve() == Path(ACTIVE_OWNER).resolve():
            raise AuditError("summary_fidelity_reason_view_v2_owner_must_be_separate")
        super().__init__(root, *args, **kwargs)

    @audited_handler
    def _status(self, session, context, data):
        _require(self.config.offline, "offline_required")
        versions = {}
        for kind, content in {
            "protocol": {"method": METHOD, "implementation": implementation(),
                "diagnostic_implementation": diagnostic.implementation(),
                "procedure": "Read exact parent plan/report and latest diagnosticv2 report through verified read-only records/artifacts. Validate lineage, original12 selections,3 preserved holds, repair9 partition and report counts. Reopen read-only source to verify stable head after reads. Reuse original safe projection exactly: existing reason max2000characters plus truncation flag, original probabilities, claim paths/hashes and source offsets/hashes only; omit source quote fields and affected claim values. No new labels, source edits, models or retries."},
            "question": {"text": "What reasons did the saved fixed-frame independent Astra summary diagnostic give?"},
            "selection": {"rules": "All12 original cases, including3 blocked old schema holds and9 untouched repair cases; preserve every existing label or unresolved outcome."},
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
            result = {**read_projection(source, fresh_head), "versions": versions}
        finally:
            source.close()
        identifier = self.ledger.record(session, "cyber_summary_fidelity_reason_view_v2", digest(result), result)
        return {"id": identifier, **result}


if __name__ == "__main__":
    study = Study(OWNER, config=Config(offline=True))
    try:
        print(json.dumps(study.execute("status", {}, objective="Inspect saved fixed-frame summary diagnostic reasons without source passages",
                                       actor="codex:summary-fidelity-reason-view-v2")))
    finally:
        study.close()
