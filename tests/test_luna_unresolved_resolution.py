"""Pure finite plans, exact unchanged QA packets and terminal dispositions."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError, digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_unresolved_resolution as subject
from test_luna_snippet_grouping import fixture, links_for, token_count
from test_luna_recall_run import response


def imported(groups=None, loose=None, *, complete=True):
    source, state = fixture(groups, loose, complete=complete)
    return {"source": source, "state": state, "history": {"membership_attempts": {}, "pair_observations": [],
        "logical_ids": [], "quarantine_document_ids": [], "resolution_proposals": []}}


def singleton(plan, article):
    return next(p for p in plan["singleton_proposals"] if p["members"] == [article])


def passed_card(value, proposal):
    bundle = subject.packet_bundle(value, proposal, token_count)
    assert not bundle["unavailable"]
    if bundle["reused_card"]:
        return bundle["reused_card"]
    if bundle["member"]:
        assert subject.contract.parse_members(bundle["member"], response(bundle["member"]["request"]))["usable"]
    card = bundle["card"]
    assert subject.contract.focal.parse_card_quality(card, response(card["request"]))["usable"]
    return card["card"]


def test_deterministic_top_three_total_prioritizes_retained_direct_hints():
    value = imported({f"s{n}": [f"a{n}"] for n in range(6)}, ["z"])
    units = subject._units(value["source"], value["state"])
    old = subject.grouping.proposals(links_for(units, [("unresolved:z", "s5", .2)]), units)
    value["history"]["resolution_proposals"] = old["primary"]
    before = deepcopy(value)
    plan = subject.build_plan(value)
    assert plan == subject.build_plan(value) and value == before
    assert len(plan["union_proposals"]) == 3
    assert "a5" in plan["union_proposals"][0]["members"]  # A hint, never a QA result.
    assert len(plan["article_diagnostics"]["z"]["omitted_targets"]) == 3
    assert subject.select_changes(plan, value["state"], {})["changes"] == []
    assert subject.POLICY["new_proposal_calls"] == 0


def test_loose_targets_do_not_bypass_three_union_limit_or_create_components():
    value = imported({}, [f"u{n}" for n in range(8)])
    plan = subject.build_plan(value)
    counts = Counter(i for p in plan["union_proposals"] for i in p["anchor_ids"])
    assert max(counts.values()) <= 3
    assert all(len(p["members"]) == 2 for p in plan["union_proposals"])
    assert all(len(d["planned_targets"]) <= 3 for d in plan["article_diagnostics"].values())


def test_quarantine_blocks_anchor_and_whole_target_in_every_stage():
    value = imported()
    value["history"]["quarantine_document_ids"] = ["a", "g"]
    plan = subject.build_plan(value)
    assert all(not {"a", "g"} & set(p["members"]) for p in plan["union_proposals"]+plan["singleton_proposals"])
    assert plan["article_diagnostics"]["h"]["excluded_targets"]["m1"] == "quarantined_source"
    assert subject.dispositions(plan, value["state"])["articles"]["g"]["dossier_status"] == "unresolved_quarantined_prior_failure"
    unquarantined = imported()
    proposed = singleton(subject.build_plan(unquarantined), "g")
    assert subject.packet_bundle(value, proposed, token_count)["unavailable"] == "quarantined_source"


def test_exact_old_packets_and_joint_reservations_no_renamed_task():
    value = imported()
    plan = subject.build_plan(value)
    row = plan["union_proposals"][0]
    bundle = subject.packet_bundle(value, row, token_count)
    assert bundle["member"] == subject.contract.member_packet(value["source"], row["members"], token_count)
    assert bundle["card"] == subject.contract.group_packet(value["source"], row["members"], token_count)
    assert bundle["reservation_nanousd"] == sum(bundle[k]["reservation_nanousd"] for k in ("member", "card"))
    value["history"]["logical_ids"] = bundle["member"]["logical_ids"]
    assert subject.packet_bundle(value, row, token_count)["unavailable"] == "prior_logical_attempt"
    value["history"]["logical_ids"] = []
    value["history"]["task_keys"] = [bundle["member"]["task_key"]]
    assert subject.packet_bundle(value, row, token_count)["unavailable"] == "prior_logical_attempt"


def test_prior_success_reused_but_failed_or_orphaned_exact_stage_blocked():
    value = imported()
    row = singleton(subject.build_plan(value), "g")
    card = passed_card(value, row)
    h = {"members": ["g"], "member_attempted": True, "member_supported": True,
        "card_attempted": True, "card_supported": True, "blocked": False, "card": card}
    value["history"]["membership_attempts"][row["membership_revision"]] = h
    bundle = subject.packet_bundle(value, row, token_count)
    assert bundle["reused_card"] == card and bundle["member"] is bundle["card"] is None
    assert bundle["reservation_nanousd"] == 0
    h.update(card_attempted=False, card_supported=False, card=None)
    bundle = subject.packet_bundle(value, row, token_count)
    assert bundle["member"] is None and bundle["card"] is not None
    h.update(card_attempted=True)
    assert subject.packet_bundle(value, row, token_count)["unavailable"] == "prior_failed_or_unknown_membership"
    plan = subject.build_plan(value)
    assert not any(p["members"] == ["g"] for p in plan["singleton_proposals"])


def test_known_negative_veto_preserved_but_not_inferred_from_failed_union():
    value = imported({"group": ["a", "b"]}, ["g"])
    value["history"]["pair_observations"] = [{"pair": ["g", "a"], "label": "negative", "compatible_focal_rubric": True}]
    plan = subject.build_plan(value)
    assert not plan["union_proposals"]
    assert plan["article_diagnostics"]["g"]["checked_negative_targets"] == []
    row = singleton(plan, "g")
    change = subject.select_changes(plan, value["state"], {row["membership_revision"]: passed_card(value, row)}, singletons=True)
    final = subject.repair.commit(value["state"], change["changes"], reason=subject.METHOD)
    status = subject.dispositions(plan, final)["articles"]["g"]
    assert status["dossier_status"] == "accepted_singleton" and status["identity_link_status"] == "coverage_incomplete"
    assert status["global_uniqueness_established"] is False


@pytest.mark.parametrize("complete", [False, True])
def test_clear_singleton_accepted_without_claiming_no_neighbor_match(complete):
    value = imported({"group": ["a", "b"]}, ["g"], complete=complete)
    plan = subject.build_plan(value)
    p = singleton(plan, "g")
    bundle = subject.packet_bundle(value, p, token_count)
    assert not subject.contract.parse_members(bundle["member"], response(bundle["member"]["request"], probability=.849))["usable"]
    changes = subject.select_changes(plan, value["state"], {p["membership_revision"]: passed_card(value, p)}, singletons=True)
    final = subject.repair.commit(value["state"], changes["changes"], reason=subject.METHOD)
    result = subject.dispositions(plan, final)
    row = result["articles"]["g"]
    assert row["dossier_status"] == "accepted_singleton"
    assert row["identity_link_status"] == ("coverage_incomplete" if complete else "not_established")
    assert result["summary"]["counts"] == {"accepted_singleton": 1}
    assert not result["global_uniqueness_established"]


def test_complete_retained_negative_menu_is_only_candidate_limited():
    value = imported({"group": ["a", "b"]}, ["g"])
    value["history"]["pair_observations"] = [{"pair": ["g", i], "label": "negative", "compatible_focal_rubric": True} for i in ("a", "b")]
    plan = subject.build_plan(value)
    p = singleton(plan, "g")
    changes = subject.select_changes(plan, value["state"], {p["membership_revision"]: passed_card(value, p)}, singletons=True)
    final = subject.repair.commit(value["state"], changes["changes"], reason=subject.METHOD)
    row = subject.dispositions(plan, final)["articles"]["g"]
    assert row["identity_link_status"] == "checked_no_match_within_menu"
    assert not row["global_uniqueness_established"]


def test_disjoint_supported_joins_then_singletons_preserve_atomic_coverage():
    value = imported({"existing": ["a", "b"]}, ["g", "h"])
    plan = subject.build_plan(value)
    supported = {p["membership_revision"]: passed_card(value, p) for p in plan["union_proposals"]}
    joined = subject.select_changes(plan, value["state"], supported)
    assert len(joined["changes"]) == 1
    remaining = [p for p in plan["singleton_proposals"] if not set(p["members"]) & set(joined["occupied"])]
    supported.update({p["membership_revision"]: passed_card(value, p) for p in remaining})
    single = subject.select_changes(plan, value["state"], supported, singletons=True, occupied=joined["occupied"])
    final = subject.repair.commit(value["state"], joined["changes"]+single["changes"], reason=subject.METHOD)
    assert {i for m in final["groups"].values() for i in m} | set(final["unresolved_ids"]) == set(value["source"]["documents"])
    reports = subject.dispositions(plan, final)["articles"]
    assert set(reports) == {"g", "h"}
    assert any(r["assignment_kind"] == "existing_group" for r in reports.values())
    assert all(not r["global_uniqueness_established"] for r in reports.values())


def test_direct_loose_pair_is_new_group_only_after_exact_full_qa():
    value = imported({}, ["g", "h"])
    plan = subject.build_plan(value)
    p, = plan["union_proposals"]
    assert not subject.select_changes(plan, value["state"], {})["changes"]
    chosen = subject.select_changes(plan, value["state"], {p["membership_revision"]: passed_card(value, p)})
    final = subject.repair.commit(value["state"], chosen["changes"], reason=subject.METHOD)
    rows = subject.dispositions(plan, final)["articles"]
    assert all(r["assignment_kind"] == "new_loose_group" for r in rows.values())


@pytest.mark.parametrize("status,expected", [
    ("joint_member_card_budget_bound", "unresolved_unattempted"),
    ("health_stop_unattempted", "unresolved_unattempted"),
    ("historical_attempt_or_negative_block", "unresolved_prior_failed"),
    ("exact_membership_stage_already_attempted", "unresolved_prior_failed"),
    ("historical_logical_identity", "unresolved_prior_failed"),
    ("physical_outcome_unknown", "unresolved_prior_failed"),
    ("mechanically_unusable", "unresolved_prior_failed"),
    ("semantic_rejection", "unresolved_ambiguous"),
    ("full_source_capacity", "unresolved_capacity")])
def test_nonacceptance_causes_are_not_conflated(status, expected):
    value = imported({}, ["g"], complete=False)
    plan = subject.build_plan(value)
    outcome = {digest(["g"]): {"status": status}}
    row = subject.dispositions(plan, value["state"], membership_outcomes=outcome)["articles"]["g"]
    assert row["dossier_status"] == expected and row["singleton_outcome"]["status"] == status


def test_non_event_and_possible_identity_are_separate_from_singleton_card_support():
    value = imported({"group": ["a"]}, ["g"])
    plan = subject.build_plan(value)
    outcome = {digest(["g"]): {"status": "semantic_rejection", "clarity_label": "not_event_focused", "clarity_probability": .9}}
    assert subject.dispositions(plan, value["state"], membership_outcomes=outcome)["articles"]["g"]["dossier_status"] == "unresolved_non_event"
    p = singleton(plan, "g")
    chosen = subject.select_changes(plan, value["state"], {p["membership_revision"]: passed_card(value, p)}, singletons=True)
    final = subject.repair.commit(value["state"], chosen["changes"], reason=subject.METHOD)
    union, = plan["union_proposals"]
    outcome = {union["membership_revision"]: {"status": "card_unknown", "member_supported": True}}
    row = subject.dispositions(plan, final, membership_outcomes=outcome)["articles"]["g"]
    assert row["dossier_status"] == "accepted_singleton" and row["identity_link_status"] == "possible_match"


def test_stale_state_foreign_support_and_changed_unit_fail_closed():
    value = imported()
    plan = subject.build_plan(value)
    changed = deepcopy(value["state"])
    changed["lineage"].append({"changed": True})
    with pytest.raises(ResearchError, match="stale_state"):
        subject.select_changes(plan, changed, {})
    with pytest.raises(ResearchError, match="foreign_supported_membership"):
        subject.select_changes(plan, value["state"], {"foreign": {}})
    p = deepcopy(plan["union_proposals"][0])
    p["unit_bindings"][p["groups"][0]]["input_bindings"][0][1] = "f"*64
    with pytest.raises(ResearchError, match="stale_proposal"):
        subject.packet_bundle(value, p, token_count)
    changed_plan = deepcopy(plan)
    changed_plan["anchors"].pop()
    with pytest.raises(ResearchError, match="plan_binding"):
        subject.select_changes(changed_plan, value["state"], {})


def test_capacity_keeps_whole_sources_and_does_not_replace_selection():
    value = imported()
    plan = subject.build_plan(value)
    p = singleton(plan, "g")
    before = deepcopy(p)
    bundle = subject.packet_bundle(value, p, lambda _: 96_001)
    assert bundle["unavailable"] == "full_source_capacity"
    assert bundle["member"] is bundle["card"] is None and p == before


def test_stale_retained_proposal_is_hint_gap_not_current_support():
    value = imported({"group": ["a"]}, ["g"])
    units = subject._units(value["source"], value["state"])
    proposals = subject.grouping.proposals(links_for(units, [("group", "unresolved:g", .9)]), units)
    proposals["primary"][0]["unit_bindings"]["group"]["input_bindings"][0][1] = "f"*64
    value["history"]["resolution_proposals"] = proposals["primary"]
    plan = subject.build_plan(value)
    assert plan["stale_retained_proposals"] == 1
    assert plan["article_diagnostics"]["g"]["prior_positive_targets"] == []
