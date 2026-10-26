"""Continuation boundaries and private/source-free registered observation."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import diagnose_dossier_failures_v8_v2 as diagnostic  # noqa: E402
from test_dossier_failures_v8_diagnostic import case  # noqa: E402

BASELINE_AT = "2026-10-23T17:34:27+00:00"
NEW_AT = "2026-10-23T17:50:00+00:00"
STOPPED_AT = "2026-10-23T17:54:17+00:00"


def patched_frame(monkeypatch):
    for key, value in {"BASELINE_TOTAL": 2, "EXPECTED_TOTAL": 6, "EXPECTED_ADDITIONAL": 4,
                       "EXPECTED_ADDITIONAL_HOLDS": 1, "AMENDMENT": "amendment"}.items():
        monkeypatch.setattr(diagnostic, key, value)
    rows = []
    for index, mode in enumerate(("timeout", "valid", "timeout", "incomplete", "valid", "valid")):
        item, _, _ = case(mode)
        item.update(at=BASELINE_AT if index < 2 else NEW_AT, execution_amendment="amendment")
        rows.append(item)
    return rows, {"stored_responses": 2, "new_unresolved_holds": 1, "at": BASELINE_AT}, {
        "stored_responses": 6, "new_unresolved_holds": 2, "at": STOPPED_AT}


@pytest.mark.parametrize("change,error", [
    ("count", "count_boundary_changed"), ("old_time", "response_interval_changed"),
    ("new_time", "response_interval_changed"), ("phase", "response_interval_changed"),
    ("amendment", "response_interval_changed"), ("old_hold", "hold_boundary_changed"),
    ("new_hold", "hold_boundary_changed"),
])
def test_fixed_interval_rejects_shifted_or_reclassified_history(monkeypatch, change, error):
    rows, baseline, report = patched_frame(monkeypatch)
    if change == "count":
        report["stored_responses"] += 1
    elif change == "old_time":
        rows[0]["at"] = NEW_AT
    elif change == "new_time":
        rows[-1]["at"] = BASELINE_AT
    elif change == "phase":
        rows[-1]["phase"] = "seed"
    elif change == "amendment":
        rows[-1]["execution_amendment"] = "other"
    elif change == "old_hold":
        rows[0]["hold"] = False
    elif change == "new_hold":
        rows[2]["hold"] = False
    with pytest.raises(AuditError, match=error):
        diagnostic.continuation_rows(rows, baseline, report)


def test_fixed_interval_separates_old_holds_and_keeps_source_rows_unchanged(monkeypatch):
    rows, baseline, report = patched_frame(monkeypatch)
    original = deepcopy(rows)
    before, after = diagnostic.continuation_rows(rows, baseline, report)
    assert len(before) == 2 and len(after) == 4
    assert sum(row["hold"] for row in before) == sum(row["hold"] for row in after) == 1
    assert rows == original


class Fixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment_v8", "fixture", {
            "implementation": diagnostic.runner.implementation(), "parent_plan": "plan"})
        baseline = None
        for index, mode in enumerate(("timeout", "valid", "timeout", "incomplete", "valid", "valid")):
            item, packet, envelope = case(mode)
            item.update(at=BASELINE_AT if index < 2 else NEW_AT, task_key=f"task-{index}")
            if index == 3:
                item["validation_error"] = "UNPROJECTED private provider prose with spaces"
            self.ledger.record(session, "cyber_dossier_response", f"case-{index}", {
                **{k: v for k, v in item.items() if not k.startswith("_")}, "execution_amendment": amendment,
                "plan": "plan", "packet": self.ledger.artifacts.put(packet), "response": self.ledger.artifacts.put(envelope)})
            if index == 1:
                baseline = self.ledger.record(session, "cyber_dossier_report", "baseline", {
                    "execution_amendment": amendment, "plan": "plan", "stored_responses": 2,
                    "new_unresolved_holds": 1, "at": BASELINE_AT})
        report = self.ledger.record(session, "cyber_dossier_report", "final", {
            "execution_amendment": amendment, "plan": "plan", "stored_responses": 6,
            "new_unresolved_holds": 2, "at": STOPPED_AT})
        return amendment, baseline, report


def test_registered_continuation_observer_is_private_and_read_only(tmp_path, monkeypatch):
    active, owner = tmp_path / "active", tmp_path / "observer"
    fixture = Fixture(active, config=Config(offline=True))
    try:
        amendment, baseline, report = fixture.execute("status", {}, objective="Synthetic response continuation", actor="test")
    finally:
        fixture.close()
    patched_frame(monkeypatch)
    for key, value in {"ACTIVE_OWNER": active, "AMENDMENT": amendment, "BASELINE_REPORT": baseline, "REPORT": report}.items():
        monkeypatch.setattr(diagnostic, key, value)
    source = diagnostic.Source(active)
    before = source.head()
    with pytest.raises(AuditError, match="source_changed"):
        diagnostic.inspect(source, lambda: [0, "wrong"])
    source.close()
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        diagnostic.Diagnostic(active, config=Config(offline=True))
    study = diagnostic.Diagnostic(owner, config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Synthetic continuation diagnosis", actor="test")
        assert result["provider_responses_before"] == 2 and result["provider_responses_after"] == 6
        assert result["continuation_responses"] == 4 and result["continuation_stored_parsed"] == 2
        assert result["new_continuation_holds"]["responses"] == 1
        assert result["continuation_failures"]["responses"] == 2
        assert result["last_card_quality_wave"]["responses"] == 4
        assert result["wave_failure_counts"] == [2] and result["wave_hold_counts"] == [1]
        assert result["v8_holds_before"] == 1 and result["v8_holds_after"] == 2
        assert result["new_model_calls"] == result["new_cost_nanousd"] == 0
        assert not result["outputs_modified"] and not result["holds_released"]
        assert "UNPROJECTED" not in canonical(result) and "task-" not in canonical(result)
        private = study.ledger.artifacts.read(result["protected_cases_artifact"])
        assert len(private) == 4 and "UNPROJECTED" not in canonical(private)
        assert study.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()
    source = diagnostic.Source(active)
    assert source.head() == before
    source.close()
