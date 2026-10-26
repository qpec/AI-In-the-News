"""Pure matched finite-population frames; no owner, retrieval or model calls."""
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import random
import sys

import pytest

from newsresearch.common import digest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import luna_recall_design as subject
from test_luna_quality_design import ranks, source_fixture


EMPTY_RISK = {"repair_proposal": [], "development_positive_or_uncertain": []}


def example():
    source = source_fixture(6, groups={"a": ["d000", "d001"], "b": ["d002", "d003"],
        "single": ["d004"], "provisional": ["d005"]},
        neighbors={"d003": {"vector": ranks("d004", "d000")}, "d004": {"word": ranks("d003")}})
    successor = {"groups": {"merged": ["d000", "d001", "d002"], "split": ["d003"], "single": ["d004"]},
        "accepted_group_ids": ["merged", "split", "single"], "unresolved_ids": ["d005"], "provisional_group_ids": []}
    risk = {"repair_proposal": [["d003", "d004"]], "development_positive_or_uncertain": []}
    return source, successor, {"exposed_documents": ["d000"], "risk_pairs": risk}


def coassigned(groups, accepted):
    return {tuple(sorted(pair)) for group in accepted for pair in combinations(groups[group], 2)}


def test_exact_matched_census_and_one_reference_shared_with_both_anchors():
    source, successor, options = example()
    design = subject.build_design(source, successor, "matched", **options)
    positive = {subject.pair_key(a, b) for a, b in [("d000", "d001"), ("d000", "d002"),
        ("d001", "d002"), ("d003", "d004")]}
    labels = {row["pair_key"]: "same_event" if row["pair_key"] in positive else "negative" for row in design["pair_tasks"]}
    report = subject.compute_report(design, labels)
    assert design["frame"]["universe_size"] == 15
    assert design["frame"]["baseline_coassigned_pairs"] == 2
    assert design["frame"]["successor_coassigned_pairs"] == 3
    assert report["baseline"]["weighted_total_ranges"] == {"TP": [1., 1.], "FP": [1., 1.], "FN": [3., 3.], "TN": [10., 10.]}
    assert report["successor"]["weighted_total_ranges"] == {"TP": [3., 3.], "FP": [0., 0.], "FN": [1., 1.], "TN": [11., 11.]}
    assert report["baseline"]["precision"]["bounds"] == [.5, .5]
    assert report["successor"]["precision"]["bounds"] == [1., 1.]
    assert report["baseline"]["candidate_recall"]["bounds"] == [.25, .25]
    assert report["successor"]["candidate_recall"]["bounds"] == [.75, .75]
    assert report["matched_changes"]["candidate_recall"] == {"estimate": .5, "conservative_bounds": [.5, .5]}
    key = subject.pair_key("d003", "d004")
    shared = [task for task in design["pair_tasks"] if task["pair_key"] == key]
    assert len(shared) == 1 and len(shared[0]["slot_ids"]) == 3  # main + both singleton anchors
    assert report["singleton_missed_match_rate"]["positive"] == 2
    assert report["coverage"]["baseline"]["group_size_histograms"] == {
        "all": {"1": 2, "2": 2}, "accepted": {"1": 1, "2": 2}, "provisional": {"1": 1}}
    assert report["coverage"]["successor"]["group_size_histograms"] == {
        "all": {"1": 2, "3": 1}, "accepted": {"1": 2, "3": 1}, "provisional": {}}
    assert report["coverage"]["successor"]["accepted_inputs"] + report["coverage"]["successor"]["provisional_inputs"] + report["coverage"]["successor"]["unresolved_inputs"] == 6
    assert report["human_truth_claimed"] is report["global_recall_claimed"] is report["group_coherence_claimed"] is False


def test_common_frame_keeps_split_pairs_and_adds_nonretrieved_new_coassignments():
    source, successor, options = example()
    source["candidate_manifest"]["pairs"] = [{"left": "d004", "right": "d005"}]
    design = subject.build_design(source, successor, "common", **options)
    pairs = {(task["left"], task["right"]) for task in design["pair_tasks"]
        if any(slot["pair_key"] == task["pair_key"] for cell in design["samples"]["pair_cells"] for slot in cell["slots"])}
    assert pairs == {("d000", "d001"), ("d002", "d003"), ("d000", "d002"), ("d001", "d002"), ("d004", "d005")}
    assert design["frame"]["universe_size"] == 5
    assert design["frame"]["excluded_nonjoined_pairs"] == 10
    assert sum(cell["population_size"] for cell in design["samples"]["pair_cells"] if cell["old_joined"]) == 2
    assert sum(cell["population_size"] for cell in design["samples"]["pair_cells"] if cell["new_joined"]) == 3


def test_ranked_implicit_cells_match_bruteforce_complete_pair_partition():
    rng = random.Random(171)
    for size in range(2, 19):
        ids = [f"d{i:03}" for i in range(size)]
        def partition():
            shuffled = rng.sample(ids, len(ids))
            groups = {f"g{i}": shuffled[i:i + 3] for i in range(0, size, 3)}
            return groups, [g for n, g in enumerate(groups) if n % 3 != 2]
        old, old_accepted = partition()
        new, new_accepted = partition()
        candidate = [pair for n, pair in enumerate(combinations(ids, 2)) if n % 3 == 0]
        source = source_fixture(size, groups=old, accepted=old_accepted, pairs=candidate)
        exposed = set(ids[::3])
        risks = set(candidate[::2])
        frames, summary, *_ = subject._frames(source, {"groups": new, "accepted_group_ids": new_accepted},
            exposed, {"repair_proposal": list(risks), "development_positive_or_uncertain": []})
        op, np = coassigned(old, old_accepted), coassigned(new, new_accepted)
        expected = set(candidate) | op | np
        observed = set()
        for cell in summary["cells"]:
            frame = frames[cell["cell_id"]]
            rows = [frame.pair_at(n) for n in range(frame.population)]
            assert len(rows) == len(set(rows)) and not observed.intersection(rows)
            observed.update(rows)
            for pair in rows:
                assert (pair in op) == cell["old_joined"]
                assert (pair in np) == cell["new_joined"]
                assert bool(exposed.intersection(pair)) == cell["exposed"]
                if not cell["old_joined"] and not cell["new_joined"]:
                    assert cell["risk"] == ("high" if pair in risks else "remaining")
        assert observed == expected and summary["universe_size"] == len(expected)


def test_frozen_rivals_and_development_risk_apply_only_to_neither_joined_cell():
    source, successor, options = example()
    members = ["d000", "d005"]
    source["unresolved_edges"] = [{"document_id": "d003", "source_document_ids": members,
        "frozen_membership_revision": digest(members)}]
    options["risk_pairs"]["development_positive_or_uncertain"] = [["d001", "d005"], ["d000", "d001"]]
    design = subject.build_design(source, successor, "risk", **options)
    high = {(slot["left"], slot["right"]) for cell in design["samples"]["pair_cells"] if cell["risk"] == "high" for slot in cell["slots"]}
    assert high == {("d000", "d003"), ("d003", "d005"), ("d001", "d005"), ("d003", "d004")}
    assert any(cell["exposed"] and cell["risk"] == "high" and cell["population_size"] == 1 for cell in design["samples"]["pair_cells"])


def test_one_per_cell_largest_remainders_and_census():
    cells = [{"cell_id": key, "population_size": 10} for key in "abc"] + [{"cell_id": "empty", "population_size": 0}]
    assert subject._allocate(cells, 8) == {"a": 3, "b": 3, "c": 2, "empty": 0}
    assert subject._allocate(cells, 100) == {"a": 10, "b": 10, "c": 10, "empty": 0}
    assert subject._allocate([{"cell_id": "a", "population_size": 1}, {"cell_id": "b", "population_size": 10}], 4) == {"a": 1, "b": 3}
    asymmetric = [{"cell_id": key, "population_size": n} for key, n in zip("abc", (2, 10, 20), strict=True)]
    assert subject._allocate(asymmetric, 10) == {"a": 2, "b": 3, "c": 5}  # N_h, not remaining N_h-1 capacity
    capped = [{"cell_id": key, "population_size": n} for key, n in zip("abc", (1, 2, 100), strict=True)]
    assert subject._allocate(capped, 100) == {"a": 1, "b": 2, "c": 97}
    with pytest.raises(ValueError, match="positive_cell_inclusion"):
        subject._allocate(cells, 2)


@pytest.fixture(scope="module")
def large_design():
    ids = [f"d{i:03}" for i in range(270)]
    groups = {"old": ids[:40], **{"s" + i: [i] for i in ids[40:]}}
    successor = {"groups": {"merged": ids[:50], **{"s" + i: [i] for i in ids[50:]}}}
    successor["accepted_group_ids"] = list(successor["groups"])
    source = source_fixture(270, groups=groups, neighbors={i: {"vector": ranks(*ids[:25])} for i in ids[50:]})
    options = {"exposed_documents": ids[::7], "risk_pairs": {"repair_proposal": [[ids[60], ids[61]]],
        "development_positive_or_uncertain": [[ids[70], ids[71]]]}}
    return source, successor, options, subject.build_design(source, successor, "fixed-seed", **options)


def test_nominal_allocations_srs_replay_weights_and_dedup(large_design):
    source, successor, options, design = large_design
    assert design == subject.build_design(source, successor, "fixed-seed", **options)
    alternate = subject.build_design(source, successor, "other-seed", **options)
    assert design["frame"] == subject.frame_summary(source, successor, **options)
    cells = design["samples"]["pair_cells"]
    assert sum(cell["sample_size"] for cell in cells if cell["new_joined"]) == 1000
    assert sum(cell["sample_size"] for cell in cells if not cell["new_joined"]) == 6000
    assert design["samples"]["singleton"]["sample_size"] == 200
    for cell in cells:
        assert cell["sample_size"] == len(cell["slots"]) == len(set(cell["rank_order"]))
        assert cell["inclusion_numerator"] == cell["weight_denominator"] == cell["sample_size"]
        assert cell["inclusion_denominator"] == cell["weight_numerator"] == cell["population_size"]
        if cell["population_size"]:
            assert cell["sample_size"] > 0
    assert any(a["rank_order"] != b["rank_order"] for a, b in zip(cells, alternate["samples"]["pair_cells"], strict=True))
    assert design["pair_slots_before_dedup"] == 11000
    assert design["unique_pair_tasks"] < 11000
    slots = [slot for task in design["pair_tasks"] for slot in task["slot_ids"]]
    assert len(slots) == len(set(slots)) == 11000
    family = sum(cell["population_size"] > 0 for cell in cells) + 1
    assert design["inference"]["count_intervals"] == family
    assert design["inference"]["tail_alpha"] * 2 * family == pytest.approx(.05)


def test_supplemental_labels_never_enter_main_matched_totals(large_design):
    *_, design = large_design
    primary = {slot["pair_key"] for cell in design["samples"]["pair_cells"] for slot in cell["slots"]}
    extra = next(task["pair_key"] for task in design["pair_tasks"] if task["pair_key"] not in primary)
    labels = {task["pair_key"]: "negative" for task in design["pair_tasks"]}
    before = subject.compute_report(design, labels)
    labels[extra] = "same_event"
    after = subject.compute_report(design, labels)
    assert before["baseline"] == after["baseline"] and before["successor"] == after["successor"]
    assert before["matched_changes"] == after["matched_changes"]
    assert before["singleton_missed_match_rate"]["positive"] == 0 < after["singleton_missed_match_rate"]["positive"]


def test_shared_cell_unknowns_widen_both_predictions_without_dropping_slots():
    source, successor, options = example()
    design = subject.build_design(source, successor, "unknown", **options)
    labels = {task["pair_key"]: "negative" for task in design["pair_tasks"]}
    key = subject.pair_key("d000", "d001")  # both coassigned
    labels[key] = "unknown"
    report = subject.compute_report(design, labels)
    assert report["baseline"]["count_bounds"]["TP"] == report["successor"]["count_bounds"]["TP"] == [0, 1]
    assert report["baseline"]["precision"]["bounds"] == [0., .5]
    assert report["successor"]["precision"]["bounds"] == [0., 1/3]
    assert report["baseline"]["precision"]["estimate"] is report["successor"]["precision"]["estimate"] is None
    assert sum(cell["selected"] for cell in report["cells"]) == 15


def test_all_unknowns_and_empty_populations_are_explicit(large_design):
    *_, design = large_design
    report = subject.compute_report(design, {})
    for name in ("baseline", "successor"):
        assert report[name]["precision"]["bounds"] == [0., 1.]
        assert report[name]["candidate_recall"]["bounds"] == [0., 1.]
        assert report[name]["precision"]["estimate"] is report[name]["candidate_recall"]["estimate"] is None
    assert report["unique_pair_outcomes"] == {"unknown": design["unique_pair_tasks"]}
    source = source_fixture(0, groups={})
    empty = subject.build_design(source, {"groups": {}, "accepted_group_ids": []}, "empty", exposed_documents=[], risk_pairs=EMPTY_RISK)
    report = subject.compute_report(empty, {})
    assert empty["inference"]["count_intervals"] == 0 and empty["inference"]["tail_alpha"] is None
    assert report["baseline"]["precision"]["bounds"] == report["successor"]["candidate_recall"]["bounds"] == [None, None]
    assert report["singleton_missed_match_rate"]["bounds"] == [None, None]


def test_zero_candidate_singleton_unknown_short_nonempty_negative_is_not_isolation():
    source = source_fixture(3, groups={"a": ["d000"], "b": ["d001"]},
        neighbors={"d000": {"word": ranks("d002")}})
    successor = {"groups": source["groups"], "accepted_group_ids": source["accepted_group_ids"]}
    design = subject.build_design(source, successor, "singleton", exposed_documents=[], risk_pairs=EMPTY_RISK)
    report = subject.compute_report(design, {task["pair_key"]: "negative" for task in design["pair_tasks"]})
    singleton = report["singleton_missed_match_rate"]
    assert singleton["zero_candidates"] == singleton["short_nonempty_lists"] == 1
    assert singleton["unknown"] == 1 and singleton["bounds"] == [0., .5]
    assert {row["outcome"] for row in singleton["outcomes"]} == {"unknown", "no_match_in_shortlist"}


def test_best_case_feasibility_does_not_cancel_or_resize_descriptive_design():
    source = source_fixture(120, groups={"only": ["d000", "d001"]})
    successor = {"groups": source["groups"], "accepted_group_ids": source["accepted_group_ids"]}
    design = subject.build_design(source, successor, "feasibility", exposed_documents=[], risk_pairs=EMPTY_RISK)
    assert sum(cell["sample_size"] for cell in design["samples"]["pair_cells"] if not cell["new_joined"]) == 6000
    assert design["preflight"]["best_case_recall_lower"] < .9
    assert design["preflight"]["both_targets_certifiable_in_best_case"] is False
    assert design["preflight"]["descriptive_audit_allowed_if_not_certifiable"] is True
    assert design["preflight"]["sample_expansion_authorized"] is False


def test_large_new_group_has_no_materialized_pair_matrix():
    source = source_fixture(6691, groups={}, pairs=[])
    ids = sorted(source["documents"])
    successor = {"groups": {"all": ids}, "accepted_group_ids": ["all"]}
    frames, summary, *_ = subject._frames(source, successor, [], EMPTY_RISK)
    assert summary["universe_size"] == summary["successor_coassigned_pairs"] == 22_381_395
    frame = frames["01:na:unexposed"]
    assert len(frame.rows) == len(frame.prefix) == 6690
    assert frame.pair_at(0) == (ids[0], ids[1])
    assert frame.pair_at(frame.population - 1) == (ids[-2], ids[-1])


@pytest.mark.parametrize("fault,reason", [("overlap", "successor_partition"), ("missing", "successor_groups"),
    ("unresolved", "successor_unresolved_partition"), ("provisional", "successor_provisional_partition"),
    ("membership", "successor_membership"), ("exposure", "exposure_documents"), ("risk", "risk_pair_identity")])
def test_foreign_or_inconsistent_partition_inputs_rejected(fault, reason):
    source, successor, options = example()
    if fault == "overlap":
        successor["groups"]["split"].append("d000")
    elif fault == "missing":
        successor["accepted_group_ids"].append("missing")
    elif fault == "unresolved":
        successor["unresolved_ids"] = []
    elif fault == "provisional":
        successor["provisional_group_ids"] = ["merged"]
    elif fault == "membership":
        successor["membership"] = {}
    elif fault == "exposure":
        options["exposed_documents"] = ["foreign"]
    else:
        options["risk_pairs"]["repair_proposal"] = [["d000", "foreign"]]
    with pytest.raises(ValueError, match=reason):
        subject.build_design(source, successor, "bad", **options)


def test_bound_design_and_strict_normalized_reference_labels():
    source, successor, options = example()
    design = subject.build_design(source, successor, "guard", **options)
    tampered = deepcopy(design)
    tampered["samples"]["pair_cells"][0]["sample_size"] += 1
    with pytest.raises(ValueError, match="design_binding"):
        subject.compute_report(tampered, {})
    with pytest.raises(ValueError, match="pair_labels"):
        subject.compute_report(design, {"foreign": "same_event"})
    with pytest.raises(ValueError, match="pair_labels"):
        subject.compute_report(design, {design["pair_tasks"][0]["pair_key"]: "related_event"})
