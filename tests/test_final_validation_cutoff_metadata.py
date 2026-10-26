"""Operational metadata selection and concrete read-only boundary, no models."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_cutoff_metadata as subject  # noqa: E402
import test_final_validation_source_v11 as fixtures  # noqa: E402
from test_final_validation_inventory import bytes_snapshot  # noqa: E402
from test_final_validation_study import process  # noqa: E402


class Metadata:
    def __init__(self):
        self.expected = {"source_owner": "/synthetic", "source_head": [80, digest("head")],
            **{key: digest(key) for key in ("plan", "input_manifest", "report")},
            "amendments": [{"kind": kind, "id": digest(kind)} for kind in subject.source_api.AMENDMENT_KINDS],
            "expected_documents": 4, "expected_articles": 5, "expected_aliases": 1}
        self.data = {kind: [{"_record_id": identity}] for kind, identity in (
            ("cyber_dossier_plan", self.expected["plan"]), ("cyber_dossier_input_manifest", self.expected["input_manifest"]),
            *[(r["kind"], r["id"]) for r in self.expected["amendments"]])}
        self.data["cyber_dossier_report"] = [{"_record_id": self.expected["report"], "_created_event": 70,
            "plan": self.expected["plan"], "execution_amendment": self.expected["amendments"][-1]["id"],
            "pipeline_processing_complete": True, "pipeline_finished": True,
            "final_audit_completion": {"processing_finished": True}}]
        self.data["cyber_dossier_phase"] = [{"_record_id": digest(name), "name": name,
            "_created_event": 60 + i, "plan": self.expected["plan"], "artifact": digest([name, "payload"]),
            "execution_amendment": self.expected["amendments"][-1]["id"]}
            for i, name in enumerate(("full_v6_processing_outcome", "full_v6_outcome"))]
        self.current = True

    def head(self):
        return self.expected["source_head"]

    def one(self, kind, identity):
        values = self.rows(kind)
        assert len(values) == 1 and values[0]["_record_id"] == identity
        return values[0]

    def rows(self, kind):
        return self.data.get(kind, [])

    def ensure_report_last(self, _report):
        if not self.current:
            raise AuditError("report_not_current")


def test_selection_uses_unique_record_ids_without_opening_phase_payloads():
    source = Metadata()
    value, rows = subject.select_metadata(source, source.expected)
    assert value["processing_outcome"] == digest("full_v6_processing_outcome")
    assert value["final_outcome"] == digest("full_v6_outcome")
    assert value["final_outcome"] != rows[-1]["artifact"]
    assert len(rows) == 14


@pytest.mark.parametrize("fault", ["head", "report", "tail", "unfinished", "audit_unfinished", "report_plan",
    "report_amendment", "phase_plan", "phase_amendment", "phase_artifact", "phase_after_report", "phase_order",
    "duplicate_phase", "missing_phase", "v10", "supplied_phase_id"])
def test_changed_or_ambiguous_cutoff_fails_closed(fault):
    source = Metadata()
    expected = deepcopy(source.expected)
    report, phases = source.data["cyber_dossier_report"][0], source.data["cyber_dossier_phase"]
    if fault == "head":
        expected["source_head"] = [81, digest("new")]
    elif fault == "report":
        expected["report"] = digest("new")
    elif fault == "tail":
        source.current = False
    elif fault == "unfinished":
        report["pipeline_finished"] = False
    elif fault == "audit_unfinished":
        report["final_audit_completion"]["processing_finished"] = False
    elif fault == "report_plan":
        report["plan"] = digest("other")
    elif fault == "report_amendment":
        report["execution_amendment"] = expected["amendments"][-2]["id"]
    elif fault == "phase_plan":
        phases[0]["plan"] = digest("other")
    elif fault == "phase_amendment":
        phases[0]["execution_amendment"] = digest("other")
    elif fault == "phase_artifact":
        phases[0]["artifact"] = "not-a-hash"
    elif fault == "phase_after_report":
        phases[0]["_created_event"] = 71
    elif fault == "phase_order":
        phases[0]["_created_event"] = 62
    elif fault == "duplicate_phase":
        phases.append(deepcopy(phases[0]))
    elif fault == "missing_phase":
        phases.pop()
    elif fault == "v10":
        source.data["cyber_dossier_execution_amendment_v10"] = [{}]
    elif fault == "supplied_phase_id":
        expected["final_outcome"] = digest("caller")
    with pytest.raises(AuditError):
        subject.select_metadata(source, expected)


def test_concrete_discovery_retains_metadata_preserves_source_and_never_dispatches(tmp_path, monkeypatch):
    source_owner, observer_owner = tmp_path / "source", tmp_path / "discovery"
    engine = fixtures.SourceFixture(source_owner, config=Config(offline=True))
    try:
        bindings = engine.execute("status", {}, objective="Synthetic source", actor="test")
        bindings["source_head"] = list(engine.ledger.db.execute(
            "SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        engine.close()
    before = bytes_snapshot(source_owner)
    expected = {k: v for k, v in bindings.items() if k not in {"processing_outcome", "final_outcome"}}
    monkeypatch.setattr(subject.original.WindowsProcessObserver, "_capture", staticmethod(lambda: [process()]))
    engine = subject.Discovery(observer_owner, source_owner=source_owner)
    try:
        result = engine.execute("status", {"expected": expected}, objective="Synthetic metadata", actor="test")
        assert result["source_bindings"] == bindings
        assert not result["source_frozen"] and not result["dispatch_authorized"]
        assert result["new_model_calls"] == result["source_mutations"] == 0
        assert len(result["liveness"]) == 2
        assert "PRIVATE BODY" not in json.dumps(result)
        assert not engine.ledger.db.execute("SELECT 1 FROM events WHERE kind LIKE 'model.%'").fetchone()
        for row in result["records"]:
            assert engine.ledger.artifacts.read_bytes(row["_artifact"])
        assert engine.ledger.verify()["status"] == "verified"
    finally:
        engine.close()
    assert bytes_snapshot(source_owner) == before
