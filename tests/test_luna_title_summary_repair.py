"""Small pure proposal/atomic-selection checks; no owners or model calls."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_repair as atomic
import luna_title_summary_repair as repair


def fixture(groups=None, loose=None, accepted=None):
    groups = deepcopy(groups if groups is not None else {"A": ["a", "a2"], "B": ["b"], "P": ["p"]})
    loose = list(loose if loose is not None else ["c", "d", "e", "f"])
    accepted = list(accepted if accepted is not None else [g for g in groups if g != "P"])
    documents = {i: {"title": i, "body": "Full source " + i,
        "input_sha256": digest({"title": i, "body": "Full source " + i}), "article_row_ids": [i]}
        for i in sorted([*loose, *(i for members in groups.values() for i in members)])}
    state = {"groups": groups, "accepted_group_ids": accepted,
        "group_states": {g: "accepted" if g in accepted else "provisional" for g in groups},
        "cards": {g: {"synthetic_card": g} for g in accepted}, "unresolved_ids": loose, "lineage": []}
    return {"documents": documents}, state


def plan(source, state, positives, negatives=(), **kwargs):
    return repair.build_proposals(source, state, positives, negatives, work_unit=0, **kwargs)


def cards(rows):
    return {r["membership_revision"]: {"synthetic_complete_card": r["members"]} for r in rows}


def test_current_atomic_units_include_provisional_and_exact_source_bindings():
    source, state = fixture()
    frozen = deepcopy((source, state))
    units = repair.build_units(source, state)
    assert units["A"]["members"] == ["a", "a2"] and units["A"]["kind"] == "multi"
    assert units["B"]["kind"] == "singleton" and units["B"]["accepted"] is True
    assert units["P"]["kind"] == "singleton" and units["P"]["accepted"] is False
    assert units["unresolved:c"]["source_group_id"] is None
    for unit in units.values():
        assert unit["membership_revision"] == digest(unit["members"])
        assert unit["source_version"] == digest(unit["input_bindings"])
        assert unit["input_bindings"] == [[i, source["documents"][i]["input_sha256"]] for i in unit["members"]]
    assert (source, state) == frozen


def test_direct_stars_deduplicate_reciprocal_edges_and_gate_nested_leaf_proposals():
    source, state = fixture()
    p = plan(source, state, [["c", "a"], ["a", "c"], ["b", "c"]])
    assert len(p["primary"]) == 1 and len(p["fallbacks"]) == 2
    parent = p["primary"][0]
    assert parent["members"] == ["a", "a2", "b", "c"]
    assert parent["direct_pairs"] == [["a", "c"], ["b", "c"]]
    assert parent["unresolved_absorbed"] == parent["singleton_absorbed"] == 1
    assert parent["new_pairs"] == 5
    assert all(r["parent_revisions"] == [parent["membership_revision"]] for r in p["fallbacks"])
    assert repair.eligible_fallbacks(p, {}) == []
    assert not p["transitive_closure_used"] and p["full_source_qa_required"]
    assert p == plan(source, state, [["c", "b"], ["a", "c"]])


def test_chain_never_becomes_component_and_no_pair_label_grants_group_support():
    source, state = fixture()
    p = plan(source, state, [["c", "d"], ["d", "e"], ["e", "f"]])
    assert {tuple(r["members"]) for r in p["primary"]} == {("c", "d", "e"), ("d", "e", "f")}
    assert all(r["members"] != ["c", "d", "e", "f"] for r in [*p["primary"], *p["fallbacks"]])
    assert repair.select_supported(p, state, {})["changes"] == []


@pytest.mark.parametrize("reason", sorted(repair.FALLBACK_REASONS))
def test_only_declared_parent_disposition_releases_untouched_negative_free_edges(reason):
    source, state = fixture()
    p = plan(source, state, [["c", "a"], ["c", "b"]], [["a2", "b"]] if reason == "negative_conflict" else [])
    parent = p["primary"][0]["membership_revision"]
    children = repair.eligible_fallbacks(p, {parent: reason})
    assert len(children) == 2
    first = children[0]["membership_revision"]
    assert [r["membership_revision"] for r in repair.eligible_fallbacks(p, {parent: reason}, attempted_memberships=[first])] == [children[1]["membership_revision"]]


@pytest.mark.parametrize("reason", ["physical_hold", "physical_failure", "orphan", "missing_response",
    "budget_bound", "health_stop", "unattempted", "supported", "semantic_unknown_without_usable_assessment"])
def test_physical_missing_budget_or_unproved_reason_never_activates_fallback(reason):
    source, state = fixture()
    p = plan(source, state, [["c", "a"], ["c", "b"]])
    assert repair.eligible_fallbacks(p, {p["primary"][0]["membership_revision"]: reason}) == []


@pytest.mark.parametrize("barrier", ["attempted_parent", "deferred_parent", "invented_negative"])
def test_parent_barrier_cannot_be_relabelled_as_fallback_permission(barrier):
    source, state = fixture()
    revision = digest(["a", "a2", "b", "c"])
    kwargs = {"attempted_memberships": [revision]} if barrier == "attempted_parent" else (
        {"deferred_memberships": [{"membership_revision": revision, "members": ["a", "a2", "b", "c"],
            "direct_pair_keys": []}]} if barrier == "deferred_parent" else {})
    p = plan(source, state, [["c", "a"], ["c", "b"]], **kwargs)
    why = "negative_conflict" if barrier == "invented_negative" else "preflight_capacity"
    assert repair.eligible_fallbacks(p, {revision: why}) == []


def test_negative_nonedge_vetoes_whole_star_but_not_untouched_conflict_free_fallback():
    source, state = fixture()
    p = plan(source, state, [["c", "a"], ["c", "b"]], [["a2", "b"]])
    parent = p["primary"][0]
    assert parent["blocked_reason"] == "negative_conflict" and parent["negative_pairs"] == [["a2", "b"]]
    children = repair.eligible_fallbacks(p, {parent["membership_revision"]: "negative_conflict"})
    assert len(children) == 2 and all(not r["negative_pairs"] for r in children)
    with pytest.raises(ResearchError, match="blocked_supported"):
        repair.select_supported(p, state, cards([parent]))
    q = plan(source, state, [["c", "a"], ["c", "b"]], [["a", "a2"]])
    allowed = repair.eligible_fallbacks(q, {q["primary"][0]["membership_revision"]: "negative_conflict"})
    assert [r["members"] for r in allowed] == [["b", "c"]]


def test_conflicting_positive_pair_is_not_an_edge_and_coassigned_pair_needs_no_proposal():
    source, state = fixture()
    p = plan(source, state, [["c", "b"], ["a", "a2"]], [["b", "c"]])
    assert p["primary"] == p["fallbacks"] == []
    assert {r["reason"] for r in p["skipped_pairs"]} == {"negative_conflict", "already_coassigned"}


def test_priority_serves_loose_then_accepted_singletons_before_large_pair_gain():
    source, state = fixture({"A": ["a1", "a2", "a3", "a4"], "B": ["b1", "b2", "b3", "b4"],
        "S": ["s"], "P": ["p"]}, ["c", "d"], ["A", "B", "S"])
    p = plan(source, state, [["a1", "b1"], ["s", "p"], ["c", "d"]])
    assert [r["unresolved_absorbed"] for r in p["primary"]] == [2, 0, 0]
    assert [r["singleton_absorbed"] for r in p["primary"]] == [0, 1, 0]
    assert [r["new_pairs"] for r in p["primary"]] == [1, 1, 16]
    result = repair.select_supported(p, state, cards(reversed(p["primary"])))
    assert [r["proposal_revision"] for r in result["changes"]] == [r["membership_revision"] for r in p["primary"]]
    after = atomic.commit(state, result["changes"], reason="synthetic-title-test")
    assert not after["unresolved_ids"] and len(after["accepted_group_ids"]) == 3
    assert sorted(i for members in after["groups"].values() for i in members) == sorted(source["documents"])
    assert len(state["unresolved_ids"]) == 2 and len(state["groups"]) == 4


def test_attempted_membership_blocks_fresh_work_but_exact_verified_card_can_be_reused():
    source, state = fixture()
    revision = digest(["b", "c"])
    p = plan(source, state, [["b", "c"]], attempted_memberships=[revision])
    assert p["primary"][0]["blocked_reason"] == "exact_membership_already_attempted"
    assert repair.select_supported(p, state, {})["changes"] == []
    assert len(repair.select_supported(p, state, {revision: {"verified_retained_card": True}})["changes"]) == 1
    q = plan(source, state, [["c", "a"], ["c", "b"]], attempted_memberships=[revision])
    allowed = repair.eligible_fallbacks(q, {q["primary"][0]["membership_revision"]: "usable_semantic_rejection"})
    assert [r["members"] for r in allowed] == [["a", "a2", "c"]]


def test_supported_overlaps_are_selected_after_qa_and_deferred_across_updated_memberships():
    source, state = fixture({"A": ["a", "a2"], "B": ["b", "b2"], "C": ["c", "c2"]}, [], ["A", "B", "C"])
    p = plan(source, state, [["a", "b"], ["a", "c"]])
    parent = p["primary"][0]["membership_revision"]
    children = repair.eligible_fallbacks(p, {parent: "usable_semantic_rejection"})
    selection = repair.select_supported(p, state, cards(children),
        eligible_fallback_revisions=[r["membership_revision"] for r in children])
    assert len(selection["changes"]) == 1 and selection["overlap_deferred_memberships"]
    after = atomic.commit(state, selection["changes"], reason="synthetic-title-test")
    chosen = set(selection["changes"][0]["original_members"])
    remaining = "c2" if "b" in chosen else "b2"
    # A different article pair must not disguise rebasing the old deferred union.
    next_plan = repair.build_proposals(source, after, [["a2", remaining]], [], work_unit=1,
        deferred_pair_keys=selection["deferred_pair_keys"], deferred_memberships=selection["deferred_memberships"])
    assert len(next_plan["primary"]) == 1
    assert next_plan["primary"][0]["blocked_reason"] == "deferred_membership_rebase"
    with pytest.raises(ResearchError, match="blocked_supported"):
        repair.select_supported(next_plan, after, cards(next_plan["primary"]))
    original_remaining = "c" if remaining == "c2" else "b"
    reciprocal = repair.build_proposals(source, after, [[original_remaining, "a"]], [], work_unit=1,
        deferred_pair_keys=selection["deferred_pair_keys"], deferred_memberships=selection["deferred_memberships"])
    assert not reciprocal["primary"] and reciprocal["skipped_pairs"][0]["reason"] == "deferred_overlap_pair"


def test_untouched_overlapping_alternative_is_deferred_but_covered_edges_are_not():
    source, state = fixture()
    p = plan(source, state, [["c", "d"], ["d", "e"], ["e", "f"]])
    only = p["primary"][0]
    selected = repair.select_supported(p, state, cards([only]))
    other = next(r for r in p["primary"] if r != only)
    assert other["membership_revision"] in selected["overlap_deferred_memberships"]
    assert selected["already_covered_memberships"]
    assert set(selected["deferred_pair_keys"]).isdisjoint(digest(p) for p in only["direct_pairs"])


@pytest.mark.parametrize("fault", ["stale_membership", "stale_card", "plan_tamper", "foreign_support", "inactive_fallback"])
def test_stale_or_unbound_selection_fails_without_mutating_state(fault):
    source, state = fixture()
    p = plan(source, state, [["c", "a"], ["c", "b"]])
    frozen, selected_state = deepcopy(state), deepcopy(state)
    supported = cards(p["primary"])
    if fault == "stale_membership":
        selected_state["groups"]["A"].append("c")
    elif fault == "stale_card":
        selected_state["cards"]["A"] = {"new_version": True}
    elif fault == "plan_tamper":
        p["primary"][0]["new_pairs"] += 1
    elif fault == "foreign_support":
        supported = {digest(["x"]): {"card": True}}
    else:
        supported = cards(p["fallbacks"][:1])
    with pytest.raises(ResearchError):
        repair.select_supported(p, selected_state, supported)
    assert state == frozen


@pytest.mark.parametrize("fault", ["duplicate_input", "overlap", "missing_input", "foreign_pair", "self_pair", "foreign_parent"])
def test_population_and_evidence_boundaries(fault):
    source, state = fixture()
    if fault == "duplicate_input":
        source["documents"]["c"]["input_sha256"] = source["documents"]["b"]["input_sha256"]
    elif fault == "overlap":
        state["groups"]["B"].append("a")
    elif fault == "missing_input":
        state["unresolved_ids"].remove("c")
    pairs = [["c", "missing"]] if fault == "foreign_pair" else [["c", "c"]] if fault == "self_pair" else [["c", "a"], ["c", "b"]]
    with pytest.raises(ResearchError):
        p = plan(source, state, pairs)
        if fault == "foreign_parent":
            repair.eligible_fallbacks(p, {digest(["foreign"]): "usable_semantic_rejection"})


def test_implementation_has_own_bytes_and_digest_primitive_dependency():
    code = repair.implementation()
    assert any(p.endswith("luna_title_summary_repair.py") for p in code)
    assert any(p.endswith("newsresearch/common.py") for p in code)
    assert all(len(h) == 64 for h in code.values())
