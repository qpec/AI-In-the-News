"""Offline discovery of two final phase identities at an explicit stopped cutoff.

Only operational record metadata is read. This is neither a source snapshot nor
history closure: SnapshotParent must independently verify the completed output.
The expected head/report/lineage is registered before the locked source read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import final_validation_source_v11 as source_api
import final_validation_study as original
from newsresearch.common import AuditError, digest
from newsresearch.runtime import Research, audited_handler

METHOD = "cybercrime-final-validation-cutoff-metadata-v1"
RESULT = "cyber_final_validation_cutoff_metadata"
ROOT = Path(__file__).resolve().parents[3]


def require(value, code):
    if not value:
        raise AuditError("final_validation_cutoff_metadata_" + code)


def implementation():
    code = source_api.implementation()
    code[Path(__file__).relative_to(ROOT).as_posix()] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return code


def validate_expected(value):
    require(isinstance(value, dict) and not {"processing_outcome", "final_outcome"} & set(value), "expected_fields")
    source_api._bindings({**value, "processing_outcome": "0" * 64, "final_outcome": "0" * 64})


def select_metadata(source, expected):
    """Pure selection over an already locked/verified metadata reader."""
    validate_expected(expected)
    require(source.head() == expected["source_head"], "head_changed")
    plan = source.one("cyber_dossier_plan", expected["plan"])
    manifest = source.one("cyber_dossier_input_manifest", expected["input_manifest"])
    amendments = [source.one(item["kind"], item["id"]) for item in expected["amendments"]]
    require(not source.rows("cyber_dossier_execution_amendment_v10"), "competing_branch")
    reports = source.rows("cyber_dossier_report")
    require(reports and reports[-1]["_record_id"] == expected["report"], "latest_report_changed")
    report = reports[-1]
    source.ensure_report_last(report)
    require(report.get("plan") == expected["plan"]
        and report.get("execution_amendment") == expected["amendments"][-1]["id"]
        and report.get("pipeline_processing_complete") is True and report.get("pipeline_finished") is True
        and report.get("final_audit_completion", {}).get("processing_finished") is True, "final_report_incomplete")
    phases = source.rows("cyber_dossier_phase")
    selected, bindings = [plan, manifest, *amendments, report], dict(expected)
    for key, name in (("processing_outcome", "full_v6_processing_outcome"), ("final_outcome", "full_v6_outcome")):
        matches = [row for row in phases if row.get("name") == name]
        require(len(matches) == 1, "unique_phase_required")
        row = matches[0]
        require(row.get("plan") == expected["plan"]
            and row.get("execution_amendment") in {item["id"] for item in expected["amendments"]}, "phase_scope")
        source_api.original._sha(row.get("artifact"))
        require(row["_created_event"] < report["_created_event"], "phase_after_report")
        selected.append(row)
        bindings[key] = row["_record_id"]
    require(selected[-2]["_created_event"] < selected[-1]["_created_event"], "phase_order")
    source_api._bindings(bindings)
    return bindings, selected


class Discovery(original.Study):
    def execute(self, operation, payload=None, *, objective, actor, versions=None):
        require(operation == "status" and not versions and isinstance(payload, dict)
            and set(payload) == {"expected"}, "entry_fields")
        validate_expected(payload["expected"])
        return Research.execute(self, operation, {"method": METHOD, **payload}, objective=objective, actor=actor)

    @audited_handler
    def _status(self, session, context, data):
        require(self.config.offline and data["method"] == METHOD
            and type(self.observer) is original.WindowsProcessObserver, "concrete_offline_reader_required")
        expected = data["expected"]
        require(Path(expected["source_owner"]).resolve() == self.source_owner, "owner_changed")
        code = implementation()
        versions = {kind: self._version_once(session, context, kind, METHOD, {
            "method": METHOD, "expected": expected,
            **({"implementation": code} if kind == "protocol" else {
                "rules": "Exact stopped head; operational metadata only, no underlying phase payloads, inputs or inference."})})
            for kind in ("protocol", "selection")}
        before = source_api._liveness(lambda owner: self.observer.observe(self, session, owner), self.source_owner)
        source_api._retained_liveness(self, before)
        source = source_api.Source(self, session, self.source_owner)
        try:
            bindings, selected = select_metadata(source, expected)
            for row in selected:
                require(self.ledger.artifacts.put_bytes(source.artifact_bytes(row["_artifact"])) == row["_artifact"], "copy_changed")
            after = source_api._liveness(lambda owner: self.observer.observe(self, session, owner), self.source_owner)
            source_api._retained_liveness(self, after)
            require(source.head(fresh=True) == expected["source_head"], "head_changed_during_read")
            require(implementation() == code, "implementation_changed")
            value = {"method": METHOD, "implementation": code, "versions": versions, "source_bindings": bindings,
                "records": [{key: row[key] for key in ("_record_id", "_record_kind", "_artifact", "_created_event")}
                    for row in selected], "liveness": [before, after], "source_mutations": 0, "new_model_calls": 0,
                "source_frozen": False, "dispatch_authorized": False,
                "limitations": "Metadata identities only; full SnapshotParent verification, history closure and validation remain required."}
            identity = self.ledger.record(session, RESULT, digest(expected), value)
            return {"record": identity, **value}
        finally:
            source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--expected-file", type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads(args.expected_file.read_text(encoding="utf-8"))
    validate_expected(expected)
    engine = Discovery(args.workspace, source_owner=Path(expected["source_owner"]))
    try:
        print(json.dumps(engine.execute("status", {"expected": expected},
            objective="Discover final phase identities at the explicitly observed completed V11 cutoff without source mutation",
            actor="codex:cybercrime-final-validation")), flush=True)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
