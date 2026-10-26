"""Synthetic v6 routing and rollback bindings, without models or source reads."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import dossier_contract_v5 as previous
import dossier_contract_v6 as contract
from newsresearch.common import ResearchError, digest


def fixtures():
    groups = {"A": ["a1", "a2"], "B": ["b1"]}
    bindings = {d: {"card_version": "version-" + d, "membership_revision": digest(members),
                   "representation_type": "evidence_card"} for d, members in groups.items()}
    return groups, bindings


def answer(query, dossier=None, *, bindings=None, same=.96, clear=.99):
    if dossier:
        distribution = {"same_event": same, "related_event": 0., "different_event": 1 - same, "uncertain": 0.}
        label = max(distribution, key=distribution.get)
        return {"kind": "assignment", "document_id": query, "dossier_id": dossier, **bindings[dossier], "status": "valid",
                "label": label, "probabilities": distribution, "probability": distribution[label], "confidence": distribution[label]}
    labels = previous.CLARITY_LABELS
    alternative = next(label for label in labels if label != "clear_single_event")
    distribution = {label: (clear if label == "clear_single_event" else 1 - clear if label == alternative else 0.) for label in labels}
    label = max(distribution, key=distribution.get)
    return {"kind": "clarity", "document_id": query, "status": "valid", "label": label,
            "probability": distribution[label], "probabilities": distribution, "confidence": distribution[label]}


def phase(queries=("q1", "q2"), rival=.5, clear=.99):
    groups, bindings = fixtures()
    decisions = {q: [answer(q, clear=clear), answer(q, "A", bindings=bindings), answer(q, "B", bindings=bindings, same=rival)] for q in queries}
    return groups, bindings, {"decisions": decisions, "proposals": {},
        "unresolved": {q: "competing_or_uncertain_candidates" for q in queries},
        "packet_coverage": {q: {"chosen_dossiers": ["A", "B"], "coverage_complete": True, "packets": 1, "candidate_counts": [2]} for q in queries}}


def test_existing_full_source_quality_contract_is_reused_without_prompt_changes():
    assert contract.card_quality_request is previous.card_quality_request
    assert contract.card_quality_audit_request is previous.card_quality_audit_request
    assert contract.parse_card_quality is previous.parse_card_quality
    assert contract.parse_card_quality_audit is previous.parse_card_quality_audit


def test_single_positive_uncertain_rivals_are_preserved_not_promoted_negative():
    _, bindings, assigned = phase()
    before = deepcopy((bindings, assigned))
    result = contract.eligible_assignments(assigned, bindings)
    assert set(result["proposals"]) == {"q1", "q2"} and not result["exclusions"]
    assert len(result["uncertainty_edges"]) == 2
    assert all(edge["relation"] == "unresolved" and not edge["treated_as_negative"] for edge in result["uncertainty_edges"])
    assert result["uncertainty_edges"][0]["original_answer"] == assigned["decisions"]["q1"][-1]
    assert result["proposals"]["q1"]["unresolved_rival_ids"] == ["B"]
    assert result["memberships_accepted"] == 0
    assert not result["proposals"]["q1"]["membership_accepted"]
    assert (bindings, assigned) == before


@pytest.mark.parametrize("rival,clear,reason", [
    (.9, .99, "multiple_positive_candidates"), (.5, .84, "focal_event_not_clear"),
])
def test_multiple_positives_or_low_clarity_do_not_become_eligible(rival, clear, reason):
    _, bindings, assigned = phase(rival=rival, clear=clear)
    result = contract.eligible_assignments(assigned, bindings)
    assert not result["proposals"] and set(result["exclusions"].values()) == {reason}


@pytest.mark.parametrize("fault", ["missing_answer", "refusal", "missing_clarity", "packet_counts", "coverage", "nan"])
def test_partial_or_invalid_answer_is_incomplete_not_a_negative(fault):
    _, bindings, assigned = phase(queries=("q1",))
    if fault == "missing_answer":
        assigned["decisions"]["q1"].pop()
    elif fault == "refusal":
        assigned["decisions"]["q1"][-1].update(status="refusal", label=None, probabilities=None)
    elif fault == "missing_clarity":
        assigned["decisions"]["q1"].pop(0)
    elif fault == "packet_counts":
        assigned["packet_coverage"]["q1"]["candidate_counts"] = [1]
    elif fault == "coverage":
        assigned["packet_coverage"]["q1"]["coverage_complete"] = False
    else:
        assigned["decisions"]["q1"][-1]["probabilities"]["same_event"] = float("nan")
    # Nonfinite evidence cannot be hashed canonically; keep the test to the
    # meaningful missing/refusal cases rather than treating corruption as data.
    if fault == "nan":
        with pytest.raises((ResearchError, ValueError)):
            contract.eligible_assignments(assigned, bindings)
    else:
        result = contract.eligible_assignments(assigned, bindings)
        assert not result["proposals"] and result["exclusions"]["q1"] == "incomplete_candidate_or_clarity_evaluation"


@pytest.mark.parametrize("fault", ["version", "revision", "query", "candidate", "duplicate"])
def test_eligibility_fails_closed_on_static_binding_changes(fault):
    _, bindings, assigned = phase(queries=("q1",))
    target = assigned["decisions"]["q1"][1]
    if fault in {"version", "revision"}:
        target["card_version" if fault == "version" else "membership_revision"] = "wrong"
    elif fault == "query":
        target["document_id"] = "other"
    elif fault == "candidate":
        target["dossier_id"] = "unknown"
    else:
        assigned["decisions"]["q1"].append(deepcopy(target))
    with pytest.raises(ResearchError):
        contract.eligible_assignments(assigned, bindings)


def test_whole_static_group_expansion_collects_all_incoming_before_quality_and_rolls_back():
    groups, bindings, assigned = phase()
    eligibility = contract.eligible_assignments(assigned, bindings)
    proposed = {"A": [*groups["A"], "q1", "q2"], "B": groups["B"]}
    snapshot = deepcopy((groups, proposed, eligibility))
    result = contract.expansion_plan(groups, proposed, eligibility["proposals"], eligibility)
    assert result["stable_groups"] == {"B": groups["B"]}
    changed = result["expansions"]["A"]
    assert changed["incoming_document_ids"] == changed["new_article_ids"] == ["q1", "q2"]
    assert changed["original_groups"] == {"A": groups["A"]}
    assert changed["membership_revision"] == digest(sorted(proposed["A"]))
    assert len(changed["unresolved_rival_edges"]) == 2
    assert not changed["membership_accepted"] and result["memberships_accepted"] == 0
    assert result["all_proposed_groups_require_independent_audit_before_filtering"]
    assert (groups, proposed, eligibility) == snapshot


def test_reciprocal_component_retains_every_original_group_for_atomic_rollback():
    groups, bindings = fixtures()
    assigned = {"decisions": {}, "proposals": {}, "unresolved": {}, "packet_coverage": {}}
    for query, target in (("a1", "B"), ("a2", "B"), ("b1", "A")):
        assigned["decisions"][query] = [answer(query), answer(query, target, bindings=bindings)]
        assigned["unresolved"][query] = "old-result"
        assigned["packet_coverage"][query] = {"chosen_dossiers": [target], "coverage_complete": True, "packets": 1, "candidate_counts": [1]}
    eligibility = contract.eligible_assignments(assigned, bindings)
    proposed = {"A": ["a1", "a2", "b1"]}
    result = contract.expansion_plan(groups, proposed, {"A": {"target": "A", "rule": "reciprocal"}}, eligibility)
    changed = result["expansions"]["A"]
    assert changed["original_groups"] == groups and changed["original_group_ids"] == ["A", "B"]
    assert changed["new_article_ids"] == [] and changed["moved_source_member_ids"] == ["b1"]


@pytest.mark.parametrize("fault", ["lost", "duplicate", "split", "unproposed", "revision"])
def test_expansion_plan_rejects_lost_split_duplicate_or_unbound_members(fault):
    groups, bindings, assigned = phase()
    eligibility = contract.eligible_assignments(assigned, bindings)
    proposed = {"A": [*groups["A"], "q1", "q2"], "B": groups["B"]}
    if fault == "lost":
        proposed["B"] = ["q2"]
        proposed["A"].remove("q2")
    elif fault == "duplicate":
        proposed["B"].append("q1")
    elif fault == "split":
        proposed["A"].remove("a2")
        proposed["B"].append("a2")
    elif fault == "unproposed":
        proposed["A"].append("unapproved")
    else:
        eligibility["proposals"]["q1"]["membership_revision"] = "wrong"
    with pytest.raises(ResearchError):
        contract.expansion_plan(groups, proposed, eligibility["proposals"], eligibility)
