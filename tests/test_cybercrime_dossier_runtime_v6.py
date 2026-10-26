"""Synthetic v6 lineage, atomic checks, fixed references and bounded admission."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v6 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v5 as prior  # noqa: E402


def setup(tmp_path, monkeypatch):
    owner, _, deadline = prior.setup(tmp_path, monkeypatch)
    parent = runner.parent.Study(owner, config=Config(offline=False))
    try:
        report = prior.prior.prior.previous_test.call(parent, "pilot", allow_paid_execution=True)
        parent_id = parent.one("cyber_dossier_execution_amendment_v5")["_record_id"]
    finally:
        parent.close()
    monkeypatch.setattr(runner, "PARENT_AMENDMENT", parent_id)
    monkeypatch.setattr(runner, "PARENT_REPORT", report["id"])
    monkeypatch.setattr(runner, "MIN_INCOMING", 1)  # One-packet transport fixture, not production gate.
    monkeypatch.setattr(runner, "implementation", lambda: {**runner.parent.implementation(), "v6": "synthetic"})
    monkeypatch.setattr(runner.Study, "read_diagnostic", lambda self: {"owner": "synthetic", "record_id": runner.DIAGNOSTIC})
    study = runner.Study(owner, config=Config(offline=True))
    try:
        prepared = prior.prior.prior.previous_test.call(study, "amend")
        assert prepared["paid_calls"] == 0 and prepared["legacy_budget"]["committed_nanousd"] == report["committed_nanousd"]
    finally:
        study.close()
    return owner, report, deadline, prepared


def test_registered_v6_reuses_ancestors_fixed_pilot_then_full_atomic_workflow(tmp_path, monkeypatch):
    owner, old, deadline, prepared = setup(tmp_path, monkeypatch)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        before = len(study.rows("cyber_dossier_response"))
        report = prior.prior.prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert report["pilot_gate"]["passed"]
        assert report["pilot_primary"]["incoming_accepted"] > 0
        assert report["pilot_primary"]["normal_valid"] == report["pilot_primary"]["selected"]
        assert report["pilot_primary"]["reference_valid"] == report["pilot_primary"]["selected"]
        assert report["unresolved_holds"] == 4 and report["held_nanousd"] == old["held_nanousd"]
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        assert study.phase(None, "pilot_v5_gate") == study.pilot_selection["retained_v5_gate"]
        new = study.rows("cyber_dossier_response")[before:]
        assert new and {r["phase"] for r in new} <= {"card_quality", "card_quality_audit"}
        assert all(r["execution_amendment"] == study.amendment["_record_id"] for r in new)
        primary = study.pilot_selection["primary"]
        secondary = study.pilot_selection["secondary"]
        primary_keys = {i["astra_task_key"] for i in primary}
        overlapping = [i for i in secondary if i["astra_task_key"] in primary_keys]
        assert len(overlapping) == prepared["secondary_shared_primary_tasks"]
        keys = [r["task_key"] for r in new]
        assert len(keys) == len(set(keys))
        count = len(study.results)
        repeated = prior.prior.prior.previous_test.call(study, "pilot", allow_paid_execution=True)
        assert repeated["committed_nanousd"] == report["committed_nanousd"] and len(study.results) == count
        # Full continuation uses the same checked-commit path and reuses every
        # identical pilot QA request; no second task or source binding is minted.
        full = prior.prior.prior.previous_test.call(study, "run", allow_paid_execution=True)
        assert full["pipeline_processing_complete"]
        assert full["held_nanousd"] == old["held_nanousd"]
        assert len(study.results) == len({r["task_key"] for r in study.rows("cyber_dossier_response")})
        outcome = study.phase(None, "full_v6_processing_outcome")
        for phase in ("initial_checked_commit", "recovery_checked_commit"):
            assert outcome[phase]["atomic_rollback"]
        assert full["globally_unique_dossiers_established"] is False
        assert "nonjoined_audit_candidate_pool" in full
        assert full["pilot_budget"]["main"]["committed_nanousd"] <= runner.PILOT_MAIN_CAP
        assert full["pilot_budget"]["audit"]["committed_nanousd"] <= runner.PILOT_AUDIT_CAP
    finally:
        study.close()


def synthetic_plan():
    return {"expansions": {"a": {"document_ids": ["a1", "b1", "q"],
            "original_groups": {"a": ["a1"], "b": ["b1"]}},
            "c": {"document_ids": ["c1", "r"], "original_groups": {"c": ["c1"]}}}}


def test_atomic_rejection_keeps_entire_source_and_target_groups():
    before = {"a": ["a1"], "b": ["b1"], "c": ["c1"]}
    assert runner.atomic_commit(before, synthetic_plan(), set()) == before
    assert runner.atomic_commit(before, synthetic_plan(), {"c"}) == {"a": ["a1"], "b": ["b1"], "c": ["c1", "r"]}
    assert runner.atomic_commit(before, synthetic_plan(), {"a"}) == {"a": ["a1", "b1", "q"], "c": ["c1"]}
    with pytest.raises(AuditError, match="unknown_accepted"):
        runner.atomic_commit(before, synthetic_plan(), {"unknown"})


def memory_pilot(monkeypatch, *, incoming=6, adverse=False, secondary_error=None, new_hold=False):
    study = object.__new__(runner.Study)
    phases = {}
    group = {"a": ["a1"]}
    expansion = {"document_ids": ["a1", *[f"q{i}" for i in range(incoming)]],
                 "original_groups": group, "incoming_document_ids": [f"q{i}" for i in range(incoming)]}
    primary = {"dossier_id": "a", "expansion": expansion, "luna_packet": "normal", "astra_packet": "reference",
               "luna_task_key": "n", "astra_task_key": "a", "unavailable": None}
    secondary = {"dossier_id": "secondary", "astra_packet": "secondary", "astra_task_key": "s", "unavailable": None}
    study.pilot_selection = {"primary": [primary], "secondary": [secondary], "before_groups": group,
        "expansion_plan": {"expansions": {"a": expansion}, "eligibility": {"uncertainty_edges": []}, "uncertainty_edges": []},
        "retained_v5_gate": {"passed": False, "card_usable_fraction": .9375, "card_reference_passed": True,
            "reference_pairs": 12, "reference_same": 12, "reference_clear_false_merges": 0, "reference_all_articles_clear": True}}
    study.phase = lambda session, name, value=None: phases.setdefault(name, value) if value is not None else phases.get(name)
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=lambda value: value))
    calls = []

    def dispatch(session, packets):
        calls.extend(packets)
        if packets == ["secondary"] and secondary_error:
            raise runner.PipelineStop(secondary_error)
        return [None] * len(packets)

    def result(item, role):
        if item["dossier_id"] == "secondary" and secondary_error:
            return ("unknown" if new_hold else "invalid"), None
        return "valid", {"label": "unsupported" if adverse and role == "astra" else "supported"}

    study.calls, study.item_result = dispatch, result
    study.hold_lineage = lambda: {"new_unresolved_holds": int(new_hold), "legacy_unresolved_holds": 4}
    return study, phases, calls


@pytest.mark.parametrize("incoming,adverse,passes", [(6, False, True), (5, False, False), (6, True, False)])
def test_unscaled_gate_counts_incoming_articles_and_preserves_normal_disagreements(monkeypatch, incoming, adverse, passes):
    study, phases, calls = memory_pilot(monkeypatch, incoming=incoming, adverse=adverse)
    study.pilot(None)
    assert calls == ["normal", "reference", "secondary"]
    assert phases["pilot_v6_gate"]["passed"] is passes
    outcome = phases["pilot_v6_outcome"]
    assert len(outcome["hypothetical_normal_groups"]["a"]) == incoming + 1
    assert outcome["normal_incoming_proposals"] == incoming
    if adverse:
        assert outcome["independent_validated_groups"] == {"a": ["a1"]}
        assert phases["pilot_v6_gate"]["incoming_accepted"] == 0


@pytest.mark.parametrize("failure,new_hold,passes", [
    ("v6_pilot_subcap_audit", False, True),
    ("v6_pilot_new_unknown_or_invalid", False, True),
    ("v6_pilot_new_unknown_or_invalid", True, False),
])
def test_optional_secondary_failure_does_not_replace_primary_quality(monkeypatch, failure, new_hold, passes):
    study, phases, _ = memory_pilot(monkeypatch, secondary_error=failure, new_hold=new_hold)
    study.pilot(None)
    assert phases["pilot_v6_primary_quality_gate"]["passed"] is True
    assert phases["pilot_v6_gate"]["passed"] is passes
    assert phases["pilot_v6_secondary_stop"]["reason"] == failure


def test_pilot_subcap_counts_unknown_intent_and_never_dispatches_an_overcap_request(monkeypatch):
    study = object.__new__(runner.Study)
    packet = {"kind": "responses", "request": {"model": "gpt-6-astra"}}
    study.task_key = lambda p: "new"
    study.pilot_task_keys = {"new"}
    study.results = {}
    study.ledger = SimpleNamespace(unresolved={})
    study.pilot_budget = lambda category: {"committed_nanousd": runner.PILOT_AUDIT_CAP - 1}
    monkeypatch.setattr(runner.parent, "reserve", lambda p: 2)
    monkeypatch.setattr(runner.parent.Study, "calls", lambda *args: pytest.fail("must not dispatch"))
    with pytest.raises(runner.PipelineStop, match="subcap_audit"):
        study.calls(None, [packet])


def test_retained_review_cannot_silently_bind_another_membership():
    study = object.__new__(runner.Study)
    item = {"dossier_id": "a", "membership_revision": "revision", "card_version": "card",
            "luna_task_key": "key", "unavailable": None}
    result = {"status": "valid", "label": "supported", "dossier_id": "other", "membership_revision": "revision",
              "card_version": "card", "representation_type": "evidence_card", "phase": "card_quality", "reference_model": "gpt-6-luna"}
    study.results = {"key": {"parsed": "result", "hold": False}}
    study.ledger = SimpleNamespace(unresolved={}, artifacts=SimpleNamespace(read=lambda _: result))
    with pytest.raises(AuditError, match="membership_binding_changed"):
        study.item_result(item, "luna")


def test_checked_commit_rejected_whole_expansion_keeps_supported_cards(monkeypatch):
    study = object.__new__(runner.Study)
    before = {"a": ["a1"], "b": ["b1"]}
    plan = {"expansions": {"a": {"document_ids": ["a1", "b1"], "original_groups": before}},
            "eligibility": {"uncertainty_edges": [{"relation": "unresolved"}]},
            "uncertainty_edges": [{"relation": "unresolved"}]}
    phases = {}
    study.phase = lambda session, name, value=None: phases.setdefault(name, value) if value is not None else phases.get(name)
    study.freeze_expansions = lambda *args, **kwargs: deepcopy(plan)
    study.make_cards = lambda *args: {"usable": {}, "quality": {"a": {"status": "valid", "label": "incoherent_group"}}}
    cards = {"a": {"card_version": "a"}, "b": {"card_version": "b"}}
    result = study.checked_commit(None, before, cards, {"v6_eligibility": {}}, "synthetic", recovery=True)
    assert result["groups"] == before and result["cards"] == cards
    assert result["rejected_expansions"]["a"]["reason"] == "incoherent_group"
    assert result["uncertainty_edges"] == [{"relation": "unresolved"}]


def test_diagnostic_reader_selects_exact_id_from_multiple_retained_reports(monkeypatch):
    study = object.__new__(runner.Study)
    study.plan = {"_record_id": "plan"}
    head = digest("head")

    class Source:
        def __init__(self, owner):
            pass

        def rows(self, kind):
            correct = {"_record_id": runner.DIAGNOSTIC, "source_report": runner.PARENT_REPORT,
                       "execution_amendment": runner.PARENT_AMENDMENT, "plan": "plan"}
            return [{**correct, "_record_id": "another-observation"}, correct]

        def head(self):
            return head

        def close(self):
            pass

    monkeypatch.setattr(runner.parent, "Source", Source)
    assert study.read_diagnostic()["record_id"] == runner.DIAGNOSTIC


def test_unresolved_rivals_outside_retrieval_frame_remain_eligible_for_final_audit():
    edges = runner.bind_rival_edges([{"document_id": "q", "dossier_id": "rival",
        "original_answer": {"membership_revision": digest(["r1", "r2"])}, "relation": "unresolved"}],
        {"rival": ["r1", "r2"]})
    pairs, counts = runner.nonjoined_frame([{"left": "q", "right": "r1"}, {"left": "a", "right": "b"}],
        {"q": "g", "r1": "g"}, edges)
    assert pairs == {("a", "b"), ("q", "r2")}
    assert counts == {"base_retrieval_pairs": 2, "uncertain_rival_pairs": 2,
                      "added_uncertain_rival_pairs": 1, "deduplicated_union_pairs": 3, "candidate_pool": 2}
    assert edges[0]["treated_as_negative"] is False


def test_pilot_budget_preserves_global_legacy_holds_and_counts_new_high_water_once():
    study = object.__new__(runner.Study)
    study.amendment = {"legacy_response_keys": ["old"], "legacy_unresolved_attempts": ["old-attempt", "old-unreturned"]}
    study.pilot_task_keys = {"old", "old-pending", "settled", "held", "new-pending"}
    study.results = {
        "old": {"attempt": "old-attempt", "task_key": "old", "category": "audit", "hold": True,
                "cost_nanousd": None, "reserved_nanousd": 100},
        "settled": {"attempt": "settled-attempt", "task_key": "settled", "category": "audit", "hold": False,
                    "cost_nanousd": 5, "reserved_nanousd": 0},
        "held": {"attempt": "held-attempt", "task_key": "held", "category": "audit", "hold": True,
                 "cost_nanousd": 9, "reserved_nanousd": 4}}
    pending = {
        "old-attempt": {"task_key": "old", "category": "audit", "reserved_nanousd": 100},
        "old-unreturned": {"task_key": "old-pending", "category": "audit", "reserved_nanousd": 200},
        "held-attempt": {"task_key": "held", "category": "audit", "reserved_nanousd": 11, "cost_nanousd": 7},
        "new-attempt": {"task_key": "new-pending", "category": "audit", "reserved_nanousd": 13}}
    study.ledger = SimpleNamespace(unresolved=pending)
    assert study.pilot_budget("audit") == {"settled_nanousd": 5, "held_nanousd": 24,
        "committed_nanousd": 29, "unresolved_holds": 2}
    assert runner.parent.accounting(list(study.results.values()), pending)["committed_nanousd"] == 329
