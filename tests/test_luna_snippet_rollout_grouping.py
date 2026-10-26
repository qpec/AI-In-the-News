"""Pure rollout coverage and no-repeat contracts; no owners or providers."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import ResearchError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_snippet_rollout_grouping as rollout
import luna_snippet_grouping as pilot
from test_luna_snippet_grouping import fixture, response, token_count, links_for


def test_full_menus_shared_packets_balanced_order_and_exact_source():
    source, state = fixture()
    before = deepcopy((source, state))
    selection = rollout.prepare(source, state, token_count)
    assert selection == rollout.prepare(source, state, token_count)
    assert (source, state) == before
    units, plan = selection["units"], selection["coverage_plan"]
    assert [units[u]["kind"] for u in plan["anchor_order"][:6]] == list(rollout.CATEGORIES) * 2
    assert selection["coverage"]["complete_menu_anchors"] == len(units)
    assert selection["coverage"]["shared_packets"] and len(selection["packets"]) < len(units)
    edge_counts = []
    for packet in selection["packets"]:
        assert packet["article_occurrences"] <= 100 and packet["input_tokens_proxy"] <= 32000
        assert packet["reservation_nanousd"] == pilot.recall.reservation(packet)
        assert len(packet["request"]["questions"]) == len(packet["anchor_unit_ids"])
        displayed = json.loads(packet["request"]["input"])
        assert pilot.focal.FOCUS_RULES in displayed["instructions"]
        for unit in displayed["units"]:
            assert [a["document_id"] for a in unit["articles"]] == units[unit["unit_id"]]["members"]
            for a in unit["articles"]:
                assert a["first_sentence"] in source["documents"][a["document_id"]]["body"]
                assert "Hidden middle" not in str(a)
        for anchor, targets in packet["menus"].items():
            assert targets == [r["unit_id"] for r in selection["menus"][anchor]]
            edge_counts.extend((anchor, t) for t in targets)
    assert len(edge_counts) == len(set(edge_counts)) == selection["coverage"]["menu_edges"]
    assert selection["actual_shown_article_ids"] is None
    all_keys = {p["task_key"] for p in selection["packets"]}
    assert rollout.coverage_status(selection, [], [])["unattempted"] == len(units)
    status = rollout.coverage_status(selection, all_keys, all_keys)
    assert status["complete_joint"] == len(units) and status["all_shards"] == 0


def test_context_only_units_are_never_anchor_coverage():
    source, state = fixture({"a": ["a"], "b": ["b"], "c": ["c"]}, [], complete=False)
    source["candidate_manifest"]["neighbors"] = {"a": {"vector": [{"document_id": "b", "rank": 1}, {"document_id": "c", "rank": 2}]}}
    selection = rollout.prepare(source, state, token_count)
    packet, = selection["packets"]
    assert packet["anchor_unit_ids"] == ["a"] and packet["context_only_unit_ids"] == ["b", "c"]
    assert len(packet["request"]["questions"]) == 1
    status = rollout.coverage_status(selection, [packet["task_key"]], [packet["task_key"]])
    assert status["complete_joint"] == 1 and status["no_candidates"] == 2
    assert status["actual_shown_unique_articles"] == 3


def test_atomic_article_shards_preserve_every_edge_and_segment_keep_scope():
    source, state = fixture({u: [f"{u}{n}" for n in range(40)] for u in "abc"}, [])
    selection = rollout.prepare(source, state, lambda _: 100)
    assert selection["coverage"]["sharded_menu_anchors"] == 3
    assert selection["coverage"]["planned_menu_edges"] == 6
    assert not selection["coverage_plan"]["unavailable"]
    assert all(p["article_occurrences"] == 80 for p in selection["packets"])
    links = []
    for p in selection["packets"]:
        choices = {a: "target:" + p["menus"][a][0] for a in p["anchor_unit_ids"]}
        parsed = rollout.parse(p, response(p, choices, probability=.2))
        assert parsed["keep_and_unknown_scope"] == "visible_menu_segment_only"
        links.extend(parsed["links"])
    assert len(links) == 6 and all(r["probability"] == .2 for r in links)
    keys = [p["task_key"] for p in selection["packets"]]
    assert rollout.coverage_status(selection, keys[:1], keys[:1])["partial"]
    assert rollout.coverage_status(selection, keys, keys)["all_shards"] == 3


def test_token_shards_and_unavailable_edges_never_vanish_from_validation_frame():
    source, state = fixture({u: [u] for u in "abc"}, [])
    def two_units(wire):
        return 32000 if len(json.loads(json.loads(wire)["input"])["units"]) <= 2 else 32001
    selection = rollout.prepare(source, state, two_units)
    assert selection["coverage"]["sharded_menu_anchors"] == 3
    assert selection["candidate_article_pairs"] == [["a", "b"], ["a", "c"], ["b", "c"]]
    failed = rollout.prepare(source, state, lambda _: 32001)
    assert not failed["packets"] and failed["coverage"]["unavailable_menu_edges"] == 6
    assert failed["candidate_article_pairs"] == selection["candidate_article_pairs"]
    assert rollout.coverage_status(failed, [], [])["capacity"] == 3
    huge_source, huge_state = fixture({"huge": [f"h{i}" for i in range(101)], "small": ["s"]}, [])
    huge = rollout.prepare(huge_source, huge_state, lambda _: 1)
    assert not huge["packets"] and len(huge["candidate_article_pairs"]) == 101
    assert len(huge["coverage_plan"]["unavailable"]) == 2


def test_prior_pilot_identity_blocks_only_exact_questions_and_survives_renames():
    source, state = fixture()
    old = pilot.prepare(source, state, token_count)["packets"][0]
    name = next(iter(old["question_map"]))
    old_unit = old["question_map"][name]["unit_id"]
    identity = rollout.normalized_question_identity(old, name)
    prior = {identity: [{"attempt": "historical", "status": "unknown"}]}
    selection = rollout.prepare(source, state, token_count, prior_questions=prior)
    assert selection["coverage"]["prior_blocked_segments"] == 1
    assert all(old_unit not in p["anchor_unit_ids"] for p in selection["packets"])
    assert any(old_unit in p["context_only_unit_ids"] for p in selection["packets"])
    assert selection["coverage"]["fresh_question_segments"] == len(selection["units"]) - 1
    renamed = deepcopy(state)
    renamed["groups"] = {"renamed-" + k: v for k, v in state["groups"].items()}
    again = rollout.prepare(source, renamed, token_count, prior_questions=prior)
    assert again["coverage"]["prior_blocked_segments"] == 1
    packet = selection["packets"][0]
    assert rollout.normalized_question_identity(packet, next(iter(packet["question_map"]))) != identity
    keys = [p["task_key"] for p in selection["packets"]]
    assert rollout.coverage_status(selection, keys, keys)["prior_blocked"] == 1
    assert selection["candidate_article_pairs"] == rollout.prepare(source, state, token_count)["candidate_article_pairs"]


def test_question_identity_ignores_target_order_names_context_but_not_sources_or_targets():
    source, state = fixture()
    packet = rollout.prepare(source, state, token_count)["packets"][0]
    name = next(iter(packet["question_map"]))
    anchor = packet["question_map"][name]["unit_id"]
    identity = rollout.normalized_question_identity(packet, name)
    changed = deepcopy(packet)
    changed["menus"][anchor].reverse()
    changed["question_map"]["renamed"] = changed["question_map"].pop(name)
    assert rollout.normalized_question_identity(changed, "renamed") == identity
    changed["menus"][anchor].pop()
    assert rollout.normalized_question_identity(changed, "renamed") != identity
    changed = deepcopy(packet)
    changed["unit_bindings"][anchor]["input_bindings"][0][1] = "f" * 64
    assert rollout.normalized_question_identity(changed, name) != identity
    changed["request"]["input"] = json.dumps({"instructions": "Different semantic rules"})
    with pytest.raises(ResearchError, match="unsupported_question_rubric"):
        rollout.normalized_question_identity(changed, name)


@pytest.mark.parametrize("fault", ["model", "distribution", "duplicate_anchor", "context_question", "segment", "request"])
def test_exact_parser_binding_faults(fault):
    source, state = fixture()
    packet = rollout.prepare(source, state, token_count)["packets"][0]
    raw = response(packet)
    names = list(packet["question_map"])
    if fault == "model":
        raw["model"] = "other"
    elif fault == "distribution":
        raw["answers"][0]["probabilities"][0]["probability"] = .999
    elif fault == "duplicate_anchor":
        packet["question_map"][names[1]] = deepcopy(packet["question_map"][names[0]])
    elif fault == "context_question":
        packet["anchor_unit_ids"].pop()
    elif fault == "segment":
        packet["question_map"][names[0]]["segment_id"] = "other"
    else:
        packet["request"]["input"] += "changed"
    with pytest.raises(ResearchError):
        rollout.parse(packet, raw)


def test_parse_keep_unknown_refusal_are_not_negative_or_global_rejection():
    source, state = fixture()
    packet = rollout.prepare(source, state, token_count)["packets"][0]
    a, b, c, *_ = packet["anchor_unit_ids"]
    choices = {a: "target:" + packet["menus"][a][0], b: "UNKNOWN", c: "REFUSAL"}
    parsed = rollout.parse(packet, response(packet, choices, probability=.2))
    assert len(parsed["links"]) == 1 and parsed["links"][0]["probability"] == .2
    assert parsed["unknown"] == sorted([b, c]) and parsed["keep"]
    assert not parsed["global_uniqueness_proved"]


def test_bounded_lookahead_scales_linearly_and_has_no_five_packet_limit():
    n = 140
    source, state = fixture({f"u{i:03}": [f"d{i:03}"] for i in range(n)}, [], complete=False)
    ids = sorted(source["documents"])
    source["candidate_manifest"]["neighbors"] = {d: {"vector": [
        {"document_id": ids[(i + step) % n], "rank": step} for step in (1, 2)]} for i, d in enumerate(ids)}
    calls = []
    result = rollout.prepare(source, state, lambda wire: calls.append(len(wire)) or 100)
    assert result["coverage"]["complete_menu_anchors"] == n
    assert len(calls) == result["coverage"]["tokenizer_calls"] <= 4 * n
    assert result["coverage_plan"]["lookahead"] == 32
    # Force two-unit question contexts: there are many packets, with no pilot cap.
    source["candidate_manifest"]["neighbors"] = {d: {"vector": [{"document_id": ids[(i+1) % n], "rank": 1}]} for i, d in enumerate(ids)}
    result = rollout.prepare(source, state, lambda wire: 100 if len(json.loads(json.loads(wire)["input"])["units"]) <= 2 else 32001)
    assert len(result["packets"]) > 5 and result["coverage"]["article_occurrences"] > 5


def test_unchanged_direct_star_and_post_qa_selection_delegates():
    assert rollout.proposals is pilot.proposals and rollout.select_supported is pilot.select_supported
    source, state = fixture({u: [u] for u in "abcd"}, [])
    units = rollout.prepare(source, state, token_count)["units"]
    proposed = rollout.proposals(links_for(units, [("a", "b", .1), ("b", "c", .2), ("c", "d", .3)]), units)
    assert all(len(p["members"]) <= 3 for p in proposed["primary"])
    assert not rollout.select_supported(proposed, {}, state)
    chosen = proposed["primary"][0]
    changes = rollout.select_supported(proposed, {chosen["membership_revision"]: {"card": "exact"}}, state)
    assert len(changes) == 1 and changes[0]["original_members"] == chosen["members"]
    implementation = rollout.implementation()
    assert "research/cybercrime_nl/runtime/luna_snippet_grouping.py" in implementation
    assert "research/cybercrime_nl/runtime/luna_snippet_rollout_grouping.py" in implementation
