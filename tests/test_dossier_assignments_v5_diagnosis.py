"""Synthetic-only validation of read-only v5 assignment outcome projection."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import inspect_dossier_assignments_v5 as reader
from newsresearch.common import AuditError, canonical


def answer(query, dossier=None, *, same=.96, clear=.99):
    if dossier:
        distribution = {"same_event": same, "related_event": 0., "different_event": 1 - same, "uncertain": 0.}
        label = max(distribution, key=distribution.get)
        return {"kind": "assignment", "document_id": query, "dossier_id": dossier, "card_version": "version-" + dossier,
                "membership_revision": "member-" + dossier, "representation_type": "evidence_card", "status": "valid",
                "label": label, "probabilities": distribution, "probability": distribution[label], "confidence": distribution[label]}
    labels = reader.runner.contract.CLARITY_LABELS
    alternative = next(label for label in labels if label != "clear_single_event")
    distribution = {label: (clear if label == "clear_single_event" else 1 - clear if label == alternative else 0.) for label in labels}
    label = max(distribution, key=distribution.get)
    return {"kind": "clarity", "document_id": query, "status": "valid", "label": label,
            "probability": distribution[label], "probabilities": distribution, "confidence": distribution[label]}


def fixture():
    # Both queries have two plausible positive dossiers. Card and full-member
    # answers agree; the withheld target was actually retrieved.
    chosen = ["target", "rival"]
    decisions = {q: [answer(q), answer(q, "target"), answer(q, "rival", same=.91)] for q in ("withheld", "natural")}
    assignment = {"decisions": decisions, "proposals": {},
        "unresolved": {q: "competing_or_uncertain_candidates" for q in decisions},
        "packet_coverage": {q: {"chosen_dossiers": chosen, "coverage_complete": True, "packets": 1} for q in decisions}}
    gate = {"passed": False, "assignment_articles": 2, "natural_query_articles": 1,
            "positive_challenge_articles": 1, "proposed_assignments": 0}
    detail = {"document_id": "withheld", "chosen_dossiers": chosen, "task_keys": ["control-task"],
        "card_coverage_complete": True, "control_complete": True, "card_complete": True,
        "control_routes": {d: "positive" for d in chosen}, "card_routes": {d: "positive" for d in chosen},
        "control_match": None, "control_clear": True, "card_clear": True}
    control = {"details_artifact": reader.CONTROL_DETAILS, "diagnostic_only": True, "changes_membership": False,
               "selected_queries": 1, "complete_control_queries": 1, "control_clear_unique_matches": 0}
    phases = {"pilot_v5_gate": gate, "pilot_v5_positive_challenge": {"groups": {"target": ["source"]},
                  "held_out": {"withheld": {"dossier_id": "target"}}},
        "pilot_v5_assignment_selection": {"withheld": ["withheld"], "natural": ["natural"]},
        reader.ASSIGNMENTS: assignment, reader.CONTROL: control,
        reader.CONTROL + "_plan": {"queries": [{k: detail[k] for k in ("document_id", "chosen_dossiers", "task_keys", "card_coverage_complete")}], "unavailable": {}},
        "pilot_v5_outcome": {"applied": {}}}
    report = {"pilot_gate": gate, "pilot_full_bundle_control": control,
              "settled_nanousd": 3, "held_nanousd": 2, "committed_nanousd": 5, "unresolved_holds": 1}
    replies = {"control-task": {"task_key": "control-task", "response_record": "record", "hold": False,
                "validation_error": None, "http_status": 200,
                "parsed": {"status": "valid", "answers": {str(i): a for i, a in enumerate(decisions["withheld"])}}}}
    return report, phases, [detail], replies


def test_complete_projection_separates_competing_positive_target_and_preserves_inputs():
    values = fixture()
    before = deepcopy(values)
    result = reader.project_outcome(*values)
    assert result["card_assignment"]["all"]["candidate_pattern_counts"] == {"multiple_positives": 2}
    assert result["card_assignment"]["withheld"]["expected_target_present"] == 1
    assert result["card_assignment"]["withheld"]["expected_target_route_counts"] == {"positive": 1}
    assert result["full_member_control"]["complete_queries"] == 1
    assert result["paired_comparisons"][0]["all_candidate_routes_equal"]
    assert result["card_assignment"]["cases"][0]["other_candidate_routes"] == {"rival": "positive"}
    assert result["card_assignment"]["all"]["retained_reason_count"] == 0
    assert result["new_model_calls"] == result["new_substantive_labels"] == result["worker_mutations"] == 0
    assert values == before


@pytest.mark.parametrize("same,pattern,blocker", [
    (.5, "one_positive_with_unresolved_rivals", "unresolved_candidate_probability"),
    (.9, "multiple_positives", "multiple_positive_candidates"),
    (.1, "one_positive_all_rivals_nonmatch", None),
])
def test_one_positive_uncertain_rival_is_distinct_from_multiple_positives(same, pattern, blocker):
    case = reader.query_view("q", ["target", "rival"], [answer("q"), answer("q", "target"), answer("q", "rival", same=same)],
                             coverage_complete=True, expected_target="target")
    assert case["candidate_pattern"] == pattern
    assert (blocker in case["acceptance_blockers"]) if blocker else not case["acceptance_blockers"]


def test_no_positive_clarity_and_technical_are_separate_nonexclusive_blockers():
    case = reader.query_view("q", ["target", "rival"], [answer("q", clear=.7), answer("q", "target", same=.4)],
                             coverage_complete=True, expected_target="target", technical_unavailable=True)
    assert set(case["acceptance_blockers"]) == {"technical_or_candidate_coverage_incomplete", "query_clarity_threshold_or_label",
                                               "unresolved_candidate_probability", "no_candidate_reaches_positive_threshold"}
    assert case["candidate_pattern"] == "no_positive_with_unresolved_candidates"
    missing = reader.query_view("q", ["rival"], [answer("q"), answer("q", "rival", same=.1)],
                                coverage_complete=True, expected_target="target")
    assert missing["expected_target_in_candidates"] is False and missing["expected_target_answer"] is None


def test_missing_or_partial_candidate_answers_do_not_imply_all_candidates_nonmatch():
    absent = reader.query_view("q", ["target", "rival"], [], coverage_complete=True, technical_unavailable=True)
    assert absent["candidate_pattern"] == "no_candidate_answers"
    partial = reader.query_view("q", ["target", "rival"], [answer("q"), answer("q", "rival", same=.1)],
                                coverage_complete=True, expected_target="target", technical_unavailable=True)
    assert partial["candidate_pattern"] == "all_available_candidates_nonmatch"
    assert not partial["candidate_coverage_complete"]
    assert "technical_or_candidate_coverage_incomplete" in partial["acceptance_blockers"]
    partial_positive = reader.query_view("q", ["target", "rival"], [answer("q"), answer("q", "target")],
                                         coverage_complete=True, technical_unavailable=True)
    assert partial_positive["candidate_pattern"] == "one_positive_all_available_rivals_nonmatch"


def test_safe_answer_projection_omits_sources_and_quotes_caps_existing_reason():
    value = answer("q", "target")
    value.update(reason="r" * 2100, title="PRIVATE_TITLE", body="PRIVATE_BODY", quote="PRIVATE_QUOTE",
                 citations=[{"quote": "PRIVATE_CITATION"}], selected_passage_locations=[{"text": "PRIVATE_LOCATION"}])
    result = reader.answer_view(value)
    assert "PRIVATE" not in canonical(result)
    assert result["model_reason"] == "r" * 2000 and result["model_reason_truncated"]


@pytest.mark.parametrize("fault", ["report", "query", "candidate", "control_candidates", "control_label", "control_counts", "frame"])
def test_projection_rejects_binding_or_count_changes(fault):
    report, phases, details, replies = fixture()
    if fault == "report":
        report["pilot_gate"] = {**report["pilot_gate"], "passed": True}
    elif fault == "query":
        phases[reader.ASSIGNMENTS]["decisions"]["natural"][0]["document_id"] = "wrong"
    elif fault == "candidate":
        phases[reader.ASSIGNMENTS]["decisions"]["natural"][1]["dossier_id"] = "wrong"
    elif fault == "control_candidates":
        details[0]["chosen_dossiers"] = ["wrong"]
    elif fault == "control_label":
        details[0]["control_routes"] = {"target": "nonmatch", "rival": "positive"}
    elif fault == "control_counts":
        phases[reader.CONTROL]["complete_control_queries"] = 0
    else:
        phases["pilot_v5_assignment_selection"]["natural"] = ["withheld"]
    with pytest.raises(AuditError):
        reader.project_outcome(report, phases, details, replies)


def test_invalid_distribution_does_not_become_a_substantive_label():
    value = answer("q", "target")
    value["probabilities"]["same_event"] = float("nan")
    with pytest.raises(AuditError, match="valid_probability_invalid"):
        reader.answer_view(value)


class FakeSource:
    def __init__(self, monkeypatch):
        report, phases, details, replies = fixture()
        self.owner = Path("synthetic-source")
        self.allowed_reads = set()
        self.reads = []
        self.saved = {}
        self.artifacts = self
        monkeypatch.setattr(reader.runner, "implementation", lambda: {"synthetic": "v5"})
        monkeypatch.setattr(reader.runner.original, "implementation", lambda: {"synthetic": "v1"})
        self.records = {"cyber_dossier_plan": [{"_record_id": reader.runner.PARENT_PLAN, "implementation": {"synthetic": "v1"}}],
            "cyber_dossier_execution_amendment_v5": [{"_record_id": reader.AMENDMENT, "implementation": {"synthetic": "v5"}, "parent_plan": reader.runner.PARENT_PLAN}],
            "cyber_dossier_report": [{**report, "_record_id": reader.REPORT, "at": "synthetic-time", "plan": reader.runner.PARENT_PLAN, "execution_amendment": reader.AMENDMENT}],
            "cyber_dossier_phase": [], "cyber_dossier_response": []}
        for name, value in phases.items():
            ref = "metadata-" + name
            self.saved[ref] = canonical(value)
            self.records["cyber_dossier_phase"].append({"name": name, "artifact": ref, "_record_id": "record-" + name,
                "plan": reader.runner.PARENT_PLAN, "execution_amendment": reader.AMENDMENT})
        self.saved[reader.CONTROL_DETAILS] = canonical(details)
        self.saved["control-parsed"] = canonical(replies["control-task"]["parsed"])
        self.records["cyber_dossier_response"] = [{"task_key": "control-task", "_record_id": "response-id", "plan": reader.runner.PARENT_PLAN,
            "execution_amendment": reader.AMENDMENT, "phase": "assignment_full_member_control", "parsed": "control-parsed",
            "packet": "FORBIDDEN_SOURCE_PACKET", "request": "FORBIDDEN_REQUEST", "response": "FORBIDDEN_RAW_RESPONSE",
            "hold": False, "http_status": 200, "validation_error": None}]
        self.allowed_reads = set(self.saved)

    def head(self):
        return "fixed-head"

    def one(self, kind):
        return self.records[kind][0]

    def rows(self, kind):
        return self.records[kind]

    def read(self, key):
        assert key in self.allowed_reads, "Raw sources or unselected artifacts must not be read"
        self.reads.append(key)
        return self.saved[key]


def test_read_projection_restricted_artifacts_fixed_lineage_and_fresh_head(monkeypatch):
    source = FakeSource(monkeypatch)
    result = reader.read_projection(source, lambda: "fixed-head")
    assert result["source_report"] == reader.REPORT and result["source_head_stable"]
    assert set(source.reads) == source.allowed_reads
    assert "FORBIDDEN" not in json.dumps(result)
    with pytest.raises(AuditError, match="source_changed"):
        reader.read_projection(source, lambda: "changed-head")
    source.records["cyber_dossier_execution_amendment_v5"][0]["implementation"] = {"changed": True}
    with pytest.raises(AuditError, match="frozen_lineage_changed"):
        reader.read_projection(source, lambda: "fixed-head")


def test_active_owner_cannot_be_opened_for_writing():
    with pytest.raises(AuditError, match="owner_must_be_separate"):
        reader.Study(reader.ACTIVE_OWNER)
