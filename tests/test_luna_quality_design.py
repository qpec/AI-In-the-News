"""Synthetic fixed-probability audit frames and uncertainty, without owner I/O."""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
from pathlib import Path
import sys

import pytest

from newsresearch.common import digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_quality_design as design


def source_fixture(size=7, *, groups=None, accepted=None, pairs=None, neighbors=None):
    ids = [f"d{i:03}" for i in range(size)]
    documents = {}
    for identity in ids:
        text = {"title": "Synthetic " + identity, "body": "Full synthetic source text " + identity}
        documents[identity] = {**text, "input_sha256": digest(text), "article_row_ids": ["row-" + identity]}
    if groups is None:
        groups = {"multi": ids[:3], "singleton": ids[3:4], "provisional": ids[4:6]}
    if accepted is None:
        accepted = [g for g in groups if g != "provisional"]
    if pairs is None:
        pairs = list(combinations(ids, 2))
    return {"documents": documents, "groups": groups, "accepted_group_ids": accepted,
        "candidate_manifest": {"document_ids": ids, "pairs": [{"left": a, "right": b} for a, b in pairs],
            "neighbors": neighbors or {}}, "unresolved_edges": [],
        "provenance": {"snapshot_record": "synthetic-snapshot"}, "counts": {"fixture": True}}


def ranks(*ids):
    return [{"document_id": identity, "rank": n} for n, identity in enumerate(ids, 1)]


@pytest.fixture(scope="module")
def large_design():
    ids = [f"d{i:03}" for i in range(250)]
    groups = {"multi": ids[:40], **{"single-" + i: [i] for i in ids[40:]}}
    neighbors = {i: {"vector": ranks(*[j for j in ids if j != i][:25])} for i in ids[40:]}
    source = source_fixture(250, groups=groups, neighbors=neighbors)
    return source, design.build_design(source, "frozen-large-seed")


def test_all_coassigned_pairs_and_exact_histogram_alias_denominators():
    source = source_fixture()
    source["documents"]["d000"]["article_row_ids"].append("row-alias")
    frozen = design.build_design(source, "fixed")
    pairs = {(s["left"], s["right"]) for s in frozen["samples"]["precision"]["slots"]}
    assert pairs == set(combinations(["d000", "d001", "d002"], 2))
    assert ("d001", "d002") in pairs  # not an anchor-star frame
    assert frozen["frames"]["coassigned_pairs"] == 3
    assert frozen["frames"]["nonjoined_pairs"] == 18
    assert frozen["coverage"] == {"documents": 7, "source_records": 8, "alias_records": 1,
        "all_groups": 3, "accepted_groups": 2, "provisional_groups": 1, "accepted_inputs": 4,
        "provisional_inputs": 2, "ungrouped_inputs": 1, "accepted_singletons": 1,
        "group_size_histograms": {"all": {"1": 1, "2": 1, "3": 1},
            "accepted": {"1": 1, "3": 1}, "provisional": {"2": 1}}}
    assert frozen["inference"]["tail_alpha"] * 6 == pytest.approx(.05)
    assert frozen["inference"]["looks"] == 1


def test_frozen_rival_members_not_current_group_membership():
    source = source_fixture(pairs=[("d000", "d001"), ("d003", "d004"), ("d004", "d003")])
    members = ["d000", "d004"]  # includes a historical member now in a different group
    source["unresolved_edges"] = [{"document_id": "d006", "group_id": "multi",
        "source_document_ids": members, "frozen_membership_revision": digest(sorted(members)),
        "original_answer": {"membership_revision": digest(sorted(members))}}]
    frozen = design.build_design(source, "rivals")
    pairs = {(s["left"], s["right"]) for s in frozen["samples"]["nonjoined"]["slots"]}
    assert pairs == {("d003", "d004"), ("d000", "d006"), ("d004", "d006")}
    assert ("d001", "d006") not in pairs
    assert frozen["frames"]["base_retrieval_pairs"] == 2
    assert frozen["frames"]["added_uncertain_rival_pairs"] == 2
    assert frozen["frames"]["excluded_accepted_coassignments"] == 1
    source["unresolved_edges"][0]["frozen_membership_revision"] = digest(["d000", "d001", "d002"])
    with pytest.raises(ValueError, match="frozen_rival_revision"):
        design.build_design(source, "rivals")


def test_sample_caps_exact_replay_seed_and_inclusion_weights(large_design):
    source, frozen = large_design
    assert frozen == design.build_design(source, "frozen-large-seed")
    alternate = design.build_design(source, "another-fixed-seed")
    for component, count in {"precision": 600, "nonjoined": 3000, "singleton": 200}.items():
        sample = frozen["samples"][component]
        assert sample["sample_size"] == count == len(sample["slots"])
        assert len(set(sample["rank_order"])) == count
        assert sample["inclusion_numerator"] == sample["weight_denominator"] == count
        assert sample["inclusion_denominator"] == sample["weight_numerator"] == sample["population_size"]
        assert sample["rank_order"] != alternate["samples"][component]["rank_order"]
    assert frozen["frames"]["coassigned_pairs"] == 780
    assert frozen["frames"]["nonjoined_pairs"] == 30345
    assert frozen["pair_slots_before_dedup"] == 7600
    assert frozen["unique_pair_tasks"] < 7600
    all_slots = [slot for task in frozen["pair_tasks"] for slot in task["slot_ids"]]
    assert len(all_slots) == len(set(all_slots)) == 7600
    assert all(task["left"] < task["right"] and task["pair_key"] == digest([task["left"], task["right"]])
        for task in frozen["pair_tasks"])


def test_rrf_uses_saved_ranks_exact_ties_and_deduplicates_execution():
    neighbors = {"d003": {"vector": ranks("d000", "d001", "d002", "d003"),
        "character": ranks("d001", "d000"), "word": ranks("d002", "d004")}}
    source = source_fixture(neighbors=neighbors)
    frozen = design.build_design(source, "rrf")
    anchor = frozen["samples"]["singleton"]["slots"][0]
    assert [r["document_id"] for r in anchor["candidates"]] == ["d000", "d001", "d002", "d004"]
    assert Fraction(anchor["candidates"][0]["rrf_numerator"], anchor["candidates"][0]["rrf_denominator"]) == Fraction(1, 61) + Fraction(1, 62)
    assert anchor["candidate_count"] == 4 and anchor["search_status"] == "shortlist_under_20"
    assert anchor["missing_channels"] == []
    task = next(t for t in frozen["pair_tasks"] if t["pair_key"] == design.pair_key("d000", "d003"))
    assert len(task["slot_ids"]) == 2
    assert frozen["unique_pair_tasks"] == 21
    assert frozen["pair_slots_before_dedup"] == 25


def test_exact_census_report_confusion_totals_and_unknown_worst_case():
    frozen = design.build_design(source_fixture(), "census")
    p = frozen["samples"]["precision"]["slots"]
    c = frozen["samples"]["nonjoined"]["slots"]
    labels = {t["pair_key"]: "negative" for t in frozen["pair_tasks"]}
    for row in p[:2] + c[:3]:
        labels[row["pair_key"]] = "same_event"
    report = design.compute_report(frozen, labels)
    assert report["weighted_total_ranges"] == {"TP": [2., 2.], "FP": [1., 1.], "FN": [3., 3.], "TN": [15., 15.]}
    assert report["precision"]["estimate"] == pytest.approx(2/3)
    assert report["precision"]["bounds"] == [2/3, 2/3]
    assert report["candidate_recall"]["estimate"] == .4
    assert report["candidate_recall"]["bounds"] == [.4, .4]
    assert report["precision"]["target_status"] == report["candidate_recall"]["target_status"] == "below_target"
    assert report["human_truth_claimed"] is report["group_coherence_claimed"] is report["global_recall_claimed"] is False
    labels[p[0]["pair_key"]] = "unknown"
    del labels[c[-1]["pair_key"]]
    report = design.compute_report(frozen, labels)
    assert report["cells"]["precision"]["positive_total_bounds"] == [1, 2]
    assert report["cells"]["nonjoined"]["positive_total_bounds"] == [3, 4]
    assert report["cells"]["nonjoined"]["selected"] == 18  # no complete-case deletion
    assert report["precision"]["estimate"] is report["candidate_recall"]["estimate"] is None
    assert report["candidate_recall"]["bounds"] == [.2, .4]


def test_weighted_point_estimates_use_population_and_primary_samples(large_design):
    _, frozen = large_design
    p = frozen["samples"]["precision"]["slots"]
    c = frozen["samples"]["nonjoined"]["slots"]
    labels = {t["pair_key"]: "negative" for t in frozen["pair_tasks"]}
    for row in p[:300] + c[:30]:
        labels[row["pair_key"]] = "same_event"
    report = design.compute_report(frozen, labels)
    assert report["cells"]["precision"]["ht_positive_total"] == 390
    assert report["cells"]["nonjoined"]["ht_positive_total"] == pytest.approx(303.45)
    assert report["precision"]["estimate"] == .5
    assert report["candidate_recall"]["estimate"] == pytest.approx(390 / (390 + 303.45))
    primary_keys = {row["pair_key"] for row in p + c}
    extra_key = next(row["pair_key"] for anchor in frozen["samples"]["singleton"]["slots"]
        for row in anchor["candidates"] if row["pair_key"] not in primary_keys)
    labels[extra_key] = "same_event"
    changed = design.compute_report(frozen, labels)
    for key in ("precision", "candidate_recall", "weighted_total_ranges"):
        assert changed[key] == report[key]
    assert changed["cells"]["precision"] == report["cells"]["precision"]
    assert changed["cells"]["nonjoined"] == report["cells"]["nonjoined"]


def test_singleton_zero_short_unknown_and_positive_dominates():
    groups = {"a": ["d000"], "b": ["d001"], "c": ["d002"]}
    source = source_fixture(5, groups=groups, neighbors={"d000": {"vector": ranks("d003", "d004")},
        "d001": {"word": ranks("d004")}})
    frozen = design.build_design(source, "singletons")
    labels = {design.pair_key("d000", "d003"): "same_event", design.pair_key("d001", "d004"): "negative"}
    report = design.compute_report(frozen, labels)
    outcomes = {r["document_id"]: r["outcome"] for r in report["singleton_missed_match_rate"]["outcomes"]}
    assert outcomes == {"d000": "detected_missed_match", "d001": "no_match_in_shortlist", "d002": "unknown"}
    singleton = report["singleton_missed_match_rate"]
    assert singleton["zero_candidates"] == 1 and singleton["short_nonempty_lists"] == 2
    assert singleton["full_20_lists"] == 0 and singleton["estimate"] is None
    assert singleton["bounds"] == [1/3, 2/3]
    assert report["cells"]["singleton"]["selected"] == 3


@pytest.mark.parametrize("size,groups", [(0, {}), (1, {"one": ["d000"]})])
def test_empty_frames_are_undefined_and_empty_singleton_shortlist_unknown(size, groups):
    frozen = design.build_design(source_fixture(size, groups=groups), "empty")
    report = design.compute_report(frozen, {})
    assert frozen["frames"]["coassigned_pairs"] == frozen["frames"]["nonjoined_pairs"] == 0
    assert report["precision"]["estimate"] is report["candidate_recall"]["estimate"] is None
    assert report["precision"]["bounds"] == report["candidate_recall"]["bounds"] == [None, None]
    assert report["cells"]["singleton"]["unknown"] == size
    assert report["singleton_missed_match_rate"]["bounds"] == ([0., 1.] if size else [None, None])
    assert frozen["preflight"]["recall_90_certification_possible"] is False


def test_all_unknowns_retain_every_selected_slot_and_bounds(large_design):
    _, frozen = large_design
    report = design.compute_report(frozen, {})
    for component in ("precision", "nonjoined", "singleton"):
        cell = report["cells"][component]
        assert cell["selected"] == cell["unknown"]
        assert cell["positive_total_bounds"] == [0, cell["population_size"]]
        assert cell["ht_positive_total"] is None
    assert report["precision"]["bounds"] == report["candidate_recall"]["bounds"] == [0., 1.]
    assert report["unique_pair_outcomes"] == {"unknown": frozen["unique_pair_tasks"]}


def test_best_case_warning_keeps_fixed_design_and_does_not_expand():
    ids = [f"d{i:03}" for i in range(110)]
    source = source_fixture(110, groups={"one_pair": ids[:2]}, accepted=["one_pair"])
    frozen = design.build_design(source, "rare-recall")
    assert frozen["frames"]["coassigned_pairs"] == 1
    assert frozen["samples"]["nonjoined"]["sample_size"] == 3000
    assert frozen["preflight"]["best_case_fn_count_bounds"][1] > 0
    assert frozen["preflight"]["best_case_recall_lower_bound"] < .9
    assert frozen["preflight"]["recall_90_certification_possible"] is False
    assert frozen["preflight"]["sample_expansion_authorized"] is False


@pytest.mark.parametrize("fault,reason", [
    ("input", "input_hash"), ("duplicate_input", "unique_full_input_population"),
    ("alias", "article_alias_partition"), ("group_overlap", "group_partition"),
    ("candidate", "candidate_endpoint"), ("rank_bool", "candidate_rank"),
    ("rank_duplicate", "candidate_rank_partition"), ("accepted", "accepted_groups"),
])
def test_frame_and_rank_corruption_rejected(fault, reason):
    source = source_fixture(neighbors={"d003": {"vector": ranks("d000", "d001")}})
    if fault == "input":
        source["documents"]["d000"]["body"] += " changed"
    elif fault == "duplicate_input":
        source["documents"]["d001"] = {**source["documents"]["d000"], "article_row_ids": ["unique-row"]}
    elif fault == "alias":
        source["documents"]["d001"]["article_row_ids"] = ["row-d000"]
    elif fault == "group_overlap":
        source["groups"]["singleton"].append("d000")
    elif fault == "candidate":
        source["candidate_manifest"]["pairs"][0]["left"] = "foreign"
    elif fault == "rank_bool":
        source["candidate_manifest"]["neighbors"]["d003"]["vector"][0]["rank"] = True
    elif fault == "rank_duplicate":
        source["candidate_manifest"]["neighbors"]["d003"]["vector"][1]["rank"] = 1
    else:
        source["accepted_group_ids"].append("missing-group")
    with pytest.raises(ValueError, match=reason):
        design.build_design(source, "invalid")


def test_design_and_foreign_label_guards():
    frozen = design.build_design(source_fixture(), "guard")
    changed = deepcopy(frozen)
    changed["samples"]["precision"]["population_size"] += 1
    with pytest.raises(ValueError, match="design_binding"):
        design.compute_report(changed, {})
    with pytest.raises(ValueError, match="foreign_pair_labels"):
        design.compute_report(frozen, {"unselected": "same_event"})
    with pytest.raises(ValueError, match="pair_labels"):
        design.compute_report(frozen, {frozen["pair_tasks"][0]["pair_key"]: "different_event"})
    with pytest.raises(ValueError, match="seed"):
        design.build_design(source_fixture(), "")
