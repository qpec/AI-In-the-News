"""Capacity-only continuation: retained attempts, explicit coverage and resume."""
from itertools import combinations
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import run_dossiers_v7 as runner  # noqa: E402
import test_cybercrime_dossier_runtime_v6 as prior  # noqa: E402


def docs(*identifiers):
    return {i: {"document_id": i, "title": "Synthetic " + i, "body": "Complete first paragraph.\n\nComplete second paragraph."} for i in identifiers}


def call(study, action, **extra):
    return study.execute("status", {"action": action, **extra}, objective="Synthetic capacity-only continuation", actor="test")


def test_both_settled_and_held_seed_sets_reused_before_new_builder(monkeypatch):
    documents = docs("a", "b", "c", "d")
    packets = [runner.BASE.contract.seed_request([documents[i] for i in ids], count_tokens=lambda _: 100)
               for ids in (("a", "b"), ("c", "d"))]
    study = object.__new__(runner.Study)
    study.results = {"settled": {"phase": "seed", "attempt": "old-settled", "packet": "ab"}}
    study.ledger = SimpleNamespace(unresolved={"old-held": {"phase": "seed", "packet": "cd"}},
        artifacts=SimpleNamespace(read={"ab": packets[0], "cd": packets[1]}.__getitem__))
    monkeypatch.setattr(runner.BASE.contract, "seed_request", lambda *args, **kwargs: pytest.fail("old sets must bypass builder"))
    entries = runner.classify_seed_packets([{"document_ids": p["document_ids"]} for p in packets],
        study.seed_attempts(), documents, lambda _: 33_000)
    assert [r["packet"] for r in entries] == packets
    assert all(r["state"] == "reused_prior_attempt" for r in entries)
    assert runner.seed_census(entries)["reused_prior_attempt_packets"] == 2


def test_untouched_capacity_deferral_preserves_all_unasked_pairs_and_no_attempt():
    documents = docs("a", "b", "c")
    proposal = {"document_ids": ["a", "b", "c"], "original_proposal": "unchanged"}
    entries = runner.classify_seed_packets([proposal], {}, documents, lambda _: 33_000)
    row = entries[0]
    assert row["proposal_sha256"] == digest(proposal) and row["document_ids"] == proposal["document_ids"]
    assert row["intended_pairs"] == [["a", "b"], ["a", "c"], ["b", "c"]]
    assert row["packet"] is None and row["state"] == "deferred_capacity_unjudged"
    assert row["provider_attempted"] is row["provider_unknown"] is row["billing_hold"] is False
    assert row["input_tokens_proxy"] == 33_000 and row["token_limit"] == 32_000
    census = runner.seed_census(entries)
    assert census["deferred_unasked_within_packet_pairs"] == census["distinct_deferred_unasked_within_packet_pairs"] == 3
    assert census["fitting_or_reused_distinct_articles"] == census["deferred_billing_holds"] == census["model_calls"] == 0


def test_noncapacity_integrity_failure_propagates_and_duplicate_frame_rejected(monkeypatch):
    documents = docs("a", "b")
    proposal = {"document_ids": ["a", "b"]}
    def broken(*args, **kwargs):
        raise ResearchError("synthetic_binding_failure")
    monkeypatch.setattr(runner.BASE.contract, "seed_request", broken)
    with pytest.raises(ResearchError, match="synthetic_binding_failure"):
        runner.classify_seed_packets([proposal], {}, documents, lambda _: 100)
    with pytest.raises(AuditError, match="proposal_identity"):
        runner.classify_seed_packets([{"document_ids": ["a", "a"]}], {}, documents, lambda _: 100)


def test_census_distinguishes_overlapping_documents_and_distinct_pairs():
    entries = [{"state": state, "document_ids": members, "intended_pairs": list(combinations(members, 2)),
                "intended_pair_count": len(list(combinations(members, 2)))} for state, members in
        (("untouched_request_fits", ["a", "b", "c"]), ("deferred_capacity_unjudged", ["b", "c", "d"]))]
    census = runner.seed_census(entries)
    assert census["fitting_and_deferred_article_overlap"] == 2
    assert census["proposed_distinct_articles"] == 4
    assert census["intended_within_packet_pairs"] == 6 and census["distinct_intended_within_packet_pairs"] == 5
    assert census["deferred_unasked_within_packet_pairs"] == census["distinct_deferred_unasked_within_packet_pairs"] == 3


def test_seed_phase_separates_unjudged_deferrals_from_unknown_provider_reply_and_resumes():
    study = object.__new__(runner.Study)
    proposals = [{"document_ids": ["a", "b"]}, {"document_ids": ["c", "d"]}]
    entries = [{"proposal_sha256": digest(proposals[0]), "state": "untouched_request_fits", "packet_artifact": "ab",
                "document_ids": ["a", "b"], "intended_pairs": [["a", "b"]], "intended_pair_count": 1},
               {"proposal_sha256": digest(proposals[1]), "state": "deferred_capacity_unjudged", "packet_artifact": None,
                "document_ids": ["c", "d"], "intended_pairs": [["c", "d"]], "intended_pair_count": 1}]
    study.amendment = {"seed_proposals_sha256": digest(proposals), "seed_packet_plan_artifact": "entries",
                       "quarantined_document_ids": [], "quarantined_group_ids": []}
    store = {"entries": entries, "ab": {"document_ids": ["a", "b"]}}
    study.ledger = SimpleNamespace(artifacts=SimpleNamespace(read=store.__getitem__))
    phases, calls = {}, []
    study.phase = lambda session, name, value=None: phases.setdefault(name, value) if value is not None else phases.get(name)
    study.calls = lambda session, requests: calls.append(requests) or [None]
    result = study.seed_results(None, proposals, "full_v6")
    assert result["failed_packets"] == result["packets"] == 1
    assert result["capacity_deferred_document_ids"] == ["c", "d"] and result["covered"] == ["a", "b"]
    assert result["clarity"] == {} and result["pair_answers"] == []
    assert not result["capacity_deferral_is_provider_unknown"]
    assert study.seed_results(None, proposals, "full_v6") == result and len(calls) == 1


def test_pilot_budget_keeps_original_v6_baseline_after_technical_amendment():
    study = object.__new__(runner.Study)
    study.v6_amendment = {"legacy_response_keys": ["old"], "legacy_unresolved_attempts": ["old-held"]}
    study.amendment = {"legacy_response_keys": ["old", "pilot"], "legacy_unresolved_attempts": ["old-held"]}
    study.pilot_task_keys = {"old", "pilot"}
    study.results = {"pilot": {"attempt": "p", "task_key": "pilot", "category": "main", "cost_nanousd": 10,
                               "reserved_nanousd": 20, "hold": False}}
    study.ledger = SimpleNamespace(unresolved={})
    assert study.pilot_budget("main")["committed_nanousd"] == 10


def test_registered_extension_deferrals_reach_actual_assignment_and_resume(tmp_path, monkeypatch):
    owner, _, deadline, _ = prior.setup(tmp_path, monkeypatch)
    previous = runner.parent.Study(owner, config=Config(offline=False))
    try:
        passed = call(previous, "pilot", allow_paid_execution=True)
        assert passed["pilot_gate"]["passed"]
        stopped = call(previous, "report")
        parent_id = previous.one("cyber_dossier_execution_amendment_v6")["_record_id"]
        proposals = previous.phase(None, "seed_proposals")["packets"]
        attempted = previous.seed_attempts()
        candidate = next(p for p in proposals if tuple(sorted(p["document_ids"])) not in attempted)
        deferred_ids = set(candidate["document_ids"])
        v6_budget = {c: previous.pilot_budget(c) for c in ("main", "audit")}
    finally:
        previous.close()
    for key, value in {"PARENT_AMENDMENT": parent_id, "PARENT_REPORT": stopped["id"], "PASSED_REPORT": passed["id"]}.items():
        monkeypatch.setattr(runner, key, value)
    monkeypatch.setattr(runner, "implementation", lambda: {**runner.parent.implementation(), "v7": "synthetic"})
    original_builder = runner.BASE.contract.seed_request
    def bounded(documents, **kwargs):
        if {d["document_id"] for d in documents} == deferred_ids:
            return original_builder(documents, **{**kwargs, "count_tokens": lambda _: 33_000})
        return original_builder(documents, **kwargs)
    monkeypatch.setattr(runner.BASE.contract, "seed_request", bounded)
    study = runner.Study(owner, config=Config(offline=True))
    try:
        count_before = len(study.rows("cyber_dossier_response"))
        prepared = call(study, "amend")
        assert prepared["paid_calls"] == 0 and len(study.rows("cyber_dossier_response")) == count_before
        assert prepared["seed_capacity_census"]["deferred_unjudged_packets"] == 1
        assert prepared["legacy_budget"]["committed_nanousd"] == stopped["committed_nanousd"]
    finally:
        study.close()
    # Parser validation legitimately reconstructs a retained wire at 96k; new
    # admission construction at 32k must instead use the frozen packet artifact.
    def parser_only(documents, **kwargs):
        assert kwargs.get("max_tokens") == 96_000 and "pairs" in kwargs
        return original_builder(documents, **kwargs)
    monkeypatch.setattr(runner.BASE.contract, "seed_request", parser_only)
    seen = {}
    original_assignments = runner.Study.assignments
    def capture(self, session, index, document_ids, groups, cards, label, recovery=False):
        seen[label] = set(document_ids)
        return original_assignments(self, session, index, document_ids, groups, cards, label, recovery=recovery)
    monkeypatch.setattr(runner.Study, "assignments", capture)
    study = runner.Study(owner, config=Config(offline=False))
    try:
        report = call(study, "run", allow_paid_execution=True)
        assert report["pipeline_processing_complete"] and report["technical_extension_version"] == 7
        assert deferred_ids <= seen["full_v6_seed"]
        # The fake transport supports singletons and any proposed expansion, so
        # these unjudged inputs are also present in actual recovery matching.
        assert deferred_ids <= seen["full_v6_recovery"]
        seeds = study.phase(None, "full_v6_seeds")
        assert not deferred_ids.intersection(seeds["covered"]) and not deferred_ids.intersection(seeds["clarity"])
        assert len(seeds["capacity_deferred_packets"]) == 1
        assert seeds["unasked_within_deferred_pairs"] == len(list(combinations(deferred_ids, 2)))
        assert tuple(sorted(deferred_ids)) not in study.seed_attempts()
        assert report["held_nanousd"] == stopped["held_nanousd"] and report["unresolved_holds"] == 4
        assert study.one("cyber_dossier_first_launch")["deadline"] == deadline
        assert {c: study.pilot_budget(c) for c in ("main", "audit")} == v6_budget
        count_after = len(study.results)
        resumed = call(study, "run", allow_paid_execution=True)
        assert len(study.results) == count_after and resumed["committed_nanousd"] == report["committed_nanousd"]
        assert resumed["seed_capacity"] == report["seed_capacity"]
        assert report["seed_capacity"]["execution_summary"]["deferred_are_provider_unknowns"] is False
    finally:
        study.close()
