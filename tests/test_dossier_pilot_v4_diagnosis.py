"""Source-free projections of synthetic saved judgments, never semantic relabeling."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import inspect_dossier_pilot_v4 as view  # noqa: E402
from newsresearch.common import AuditError, Config  # noqa: E402
from newsresearch.runtime import Research, audited_handler  # noqa: E402


def answer(label, **extra):
    return {"status": "valid", "label": label, "reason": "Specific saved reason " + "r" * 2000,
            "claim_paths": ["/overview"],
            "affected_claims": [{"path": "/overview", "value_sha256": "claim-hash", "value": "PRIVATE CLAIM"}],
            "selected_passage_locations": [{"document_id": "a", "field": "body", "start": 5, "end": 20,
                "text_sha256": "text-hash", "quote": "PRIVATE PASSAGE"}],
            "citations": [{"quote": "PRIVATE CITATION"}], **extra}


def data():
    phases = {view.SUMMARY_PHASE: {"usable": {"d1": {"summary_version": "v1", "summary": "PRIVATE SUMMARY"}},
        "quality": {"d1": answer("supported", dossier_id="d1", summary_version="v1"),
                    "d2": answer("unsupported", dossier_id="d2", summary_version="v2")},
        "deferred": [{"dossier_id": "d2", "reason": "summary_quality_not_supported", "source_text": "PRIVATE"}]},
        view.SUMMARY_REFERENCE: {"items": [{"dossier_id": "d1", "summary_version": "v1",
                                          "reference": answer("unsupported", dossier_id="d1", summary_version="v1")}]},
        "pilot_v4_positive_challenge": {"groups": {"d1": ["a", "b"], "d2": ["c", "d"]}},
        view.PAIR_REFERENCES[0]: {"items": [{"left": "a", "right": "b", "reference": answer("uncertain"),
            "clarity": [answer("clear_single_event", document_id="a"), answer("multiple_events", document_id="b")],
            "reference_both_clear": False}]},
        view.PAIR_REFERENCES[1]: {"items": [{"left": "c", "right": "d", "reference": answer("same_event"),
            "clarity": [answer("clear_single_event", document_id="c"), answer("clear_single_event", document_id="d")],
            "reference_both_clear": True}]}}
    gate = {"passed": False, "summary_usable_fraction": .5, "reference_pairs": 2, "reference_same": 1,
            "reference_clear_false_merges": 0, "reference_all_articles_clear": False}
    phases["pilot_v4_gate"] = gate
    report = {"pilot_gate": gate, "pilot_summary_reference": {"selected": 1, "valid": 1,
        "supported": 0, "unsupported": 1, "identity_missing": 0, "uncertain": 0},
        "settled_nanousd": 5, "held_nanousd": 3, "committed_nanousd": 8,
        "unresolved_holds": 4, "legacy_unresolved_holds": 4, "new_unresolved_holds": 0}
    return report, phases


def test_projection_preserves_valid_uncertainty_and_clarity_failure_without_private_evidence():
    report, phases = data()
    original = deepcopy((report, phases))
    projected = view.project_outcome(report, phases)
    assert "PRIVATE" not in json.dumps(projected)
    assert projected["normal_luna_quality"]["label_counts"] == {"supported": 1, "unsupported": 1}
    assert projected["astra_summary_quality"]["label_counts"] == {"unsupported": 1}
    pair = projected["pair_references"]["exceptions"][0]
    assert pair["pair_label"] == "uncertain" and pair["pair_result_kind"] == "model_judgment"
    assert pair["clarity_result_kind"] == "model_judgment"
    assert projected["pair_references"]["technical_unavailable"] == 0
    assert projected["pair_references"]["clarity_model_failures"] == 1
    reason = projected["normal_luna_quality"]["cases"][1]
    assert reason["model_reason_truncated"] and len(reason["model_reason"]) == 2000
    assert reason["claim_paths"] == ["/overview"]
    assert reason["affected_claim_hashes"] == [{"path": "/overview", "value_sha256": "claim-hash"}]
    assert (report, phases) == original


def test_absent_pair_and_clarity_remain_technical_and_never_become_semantic_labels():
    item = {"left": "a", "right": "b", "reference": None, "available": False, "reason": "reference_packet_capacity"}
    result = view.pair_case("synthetic", item)
    assert result["pair_label"] is None
    assert result["pair_result_kind"] == result["clarity_result_kind"] == "technical_unavailable"
    assert result["technical_reason"] == "reference_packet_capacity"


@pytest.mark.parametrize("fault,expected", [("usable_qa", "usable_quality"), ("audit_count", "summary_reference_counts"),
    ("pair_count", "pair_reference_counts"), ("clarity_flag", "clarity_flag"), ("report_gate", "report_gate"),
    ("wrong_snapshot", "quality_snapshot_binding"), ("foreign_dossier", "quality_frame")])
def test_recorded_counts_and_bindings_cannot_be_rewritten(fault, expected):
    report, phases = data()
    if fault == "usable_qa":
        phases[view.SUMMARY_PHASE]["quality"]["d1"]["label"] = "unsupported"
    elif fault == "audit_count":
        report["pilot_summary_reference"]["unsupported"] = 0
    elif fault == "pair_count":
        phases[view.PAIR_REFERENCES[0]]["items"][0]["reference"]["label"] = "same_event"
    elif fault == "clarity_flag":
        phases[view.PAIR_REFERENCES[0]]["items"][0]["reference_both_clear"] = True
    elif fault == "wrong_snapshot":
        phases[view.SUMMARY_REFERENCE]["items"][0]["reference"]["summary_version"] = "other"
    elif fault == "foreign_dossier":
        phases[view.SUMMARY_PHASE]["quality"]["other"] = answer("supported")
    else:
        report["pilot_gate"] = {**report["pilot_gate"], "passed": True}
    with pytest.raises(AuditError, match=expected):
        view.project_outcome(report, phases)


class Fixture(Research):
    @audited_handler
    def _status(self, session, context, input):
        report, phases = data()
        plan = self.ledger.record(session, "cyber_dossier_plan", "fixture", {"implementation": {"original": "frozen"}})
        amendment = self.ledger.record(session, "cyber_dossier_execution_amendment_v4", "fixture", {
            "parent_plan": plan, "implementation": {"v4": "frozen"}})
        for name, value in phases.items():
            self.ledger.record(session, "cyber_dossier_phase", name, {"name": name, "plan": plan,
                "execution_amendment": amendment, "artifact": self.ledger.artifacts.put(value)})
        self.ledger.record(session, "cyber_dossier_report", "fixture", {
            **report, "plan": plan, "execution_amendment": amendment, "at": "synthetic"})
        return {"plan": plan}


def test_separate_registered_reader_leaves_synthetic_source_unchanged(tmp_path, monkeypatch):
    active = tmp_path / "source"
    fixture = Fixture(active, config=Config(offline=True))
    try:
        ids = fixture.execute("status", {}, objective="Synthetic pilot metadata fixture", actor="test:pilot-view")
    finally:
        fixture.close()
    monkeypatch.setattr(view, "ACTIVE_OWNER", active)
    monkeypatch.setattr(view.runner, "PARENT_PLAN", ids["plan"])
    monkeypatch.setattr(view.runner, "implementation", lambda: {"v4": "frozen"})
    monkeypatch.setattr(view.runner.original, "implementation", lambda: {"original": "frozen"})
    source = view.Source(active)
    before = source.head()
    source.close()
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        view.Study(active, config=Config(offline=True))
    study = view.Study(tmp_path / "inspector", config=Config(offline=True))
    try:
        result = study.execute("status", {}, objective="Project saved synthetic pilot reasons", actor="test:pilot-view")
        assert result["source_head"] == before and "PRIVATE" not in json.dumps(result)
        assert result["new_model_calls"] == result["worker_mutations"] == 0
        assert study.ledger.db.execute("SELECT COUNT(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0] == 0
    finally:
        study.close()
    source = view.Source(active)
    assert source.head() == before
    source.close()
