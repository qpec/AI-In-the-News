"""Source-free checks of exhaustive boxes, closure metrics and unchanged policy."""

import itertools
import math
from copy import deepcopy

import pytest

from newsresearch import event_pair_selection as selection
from newsresearch.event_pair_conjunction import _masked_metrics
from newsresearch.event_pair_monotone import evaluate, predicts, validate


def fixtures(same=9, different=8, uncertain=2, fold="development"):
    rows, judgments = [], {}
    for index, label in enumerate(["same_event"] * same + ["different_event"] * different
                                   + ["uncertain"] * uncertain):
        pair_id = f"{fold}-{index:03}"
        rows.append({"pair_id": pair_id, "left": f"{fold}-l{index}",
                     "right": f"{fold}-r{index}", "fold": fold,
                     "features": {name: .95 if label == "same_event" else .2 for name in selection.FEATURES},
                     "inclusion_probability": .5, "publication_gap_days": .5})
        judgments[pair_id] = {"status": "completed", "label": label}
    return rows, judgments


def candidate(gate=None):
    return {"features": list(selection.FEATURES), "thresholds": [.9] * 5,
            "publication_gap_days": gate}


def test_complete_enumeration_and_exact_dedup_preserve_all_generators():
    rows, judgments = fixtures(10)
    original = deepcopy(rows)
    rows[9]["features"] = {name: .99 for name in selection.FEATURES}
    result = evaluate(rows, judgments)
    expected = 4 * sum(math.comb(10, size) for size in range(8, 11))
    assert result["search_complete"]
    assert result["evaluated_generating_subsets"] == expected == 224
    assert len(result["full_grid"]["rows"]) == expected
    assert len(result["metrics_map"]) == 1
    assert result["best_candidate"]["metrics"]["selected_label_counts"]["same_event"] == 10
    assert result["all_label_counts"]["uncertain"] == 2
    assert original[9]["features"] != rows[9]["features"]
    assert result == evaluate(list(reversed(rows)), judgments)


def test_generating_subsets_thresholds_and_closure_are_reconstructible():
    rows, judgments = fixtures()
    result = evaluate(rows, judgments)
    by_id = {row["pair_id"]: row for row in rows}
    for gate_index, subset_mask, vector_index, mask_id in result["full_grid"]["rows"]:
        seeds = [by_id[pair_id] for index, pair_id in enumerate(result["positive_subset_row_order"])
                 if int(subset_mask, 16) & (1 << index)]
        assert len(seeds) >= 8
        cuts = [min(row["features"][feature] for row in seeds) for feature in selection.FEATURES]
        assert cuts == result["threshold_vectors"][vector_index]
        parameters = {"features": list(selection.FEATURES), "thresholds": cuts,
                      "publication_gap_days": result["publication_gates_days"][gate_index]}
        mask = sum(1 << index for index, pair_id in enumerate(result["row_order_pair_ids"])
                   if predicts(by_id[pair_id], parameters))
        assert hex(mask) == mask_id
        assert mask_id in result["metrics_map"]


def test_no_eligible_rule_certifies_fixed_family_without_dropping_uncertain():
    rows, judgments = fixtures()
    for row in rows[-2:]:
        row["features"] = {name: .95 for name in selection.FEATURES}
    result = evaluate(rows, judgments)
    assert result["status"] == "no_eligible_rule"
    assert result["search_complete"]
    assert result["best_candidate"] is None
    diagnostic = result["best_at_required_coverage"]
    assert diagnostic["metrics"]["precision_pessimistic_observed"] == 9 / 11
    assert diagnostic["metrics"]["selected_label_counts"]["uncertain"] == 2
    assert diagnostic["metrics"]["selected_label_counts"]["different_event"] == 0


def test_original_weights_remain_in_pessimistic_precision():
    rows, judgments = fixtures(uncertain=1)
    rows[-1]["features"] = {name: .95 for name in selection.FEATURES}
    rows[-1]["inclusion_probability"] = .001
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    metric = result["best_at_required_coverage"]["metrics"]
    assert metric["precision_pessimistic_observed"] == .9
    assert metric["precision_pessimistic_weighted"] == 18 / 1018


def test_existence_representative_dominates_every_small_brute_force_box():
    rows, judgments = fixtures()
    result = evaluate(rows, judgments)
    prepared, errors = selection._prepare(rows, judgments, "development", selection.FEATURES)
    represented_masks = {int(value, 16) for value in result["metrics_map"]}
    for cuts in itertools.product((.2, .6, .95), repeat=5):
        parameters = {**candidate(), "thresholds": list(cuts)}
        mask = sum(1 << index for index, row in enumerate(prepared) if predicts(row, parameters))
        metrics = _masked_metrics(prepared, mask, "development", errors)
        if metrics["eligible"]:
            positives = [index for index, row in enumerate(prepared)
                         if mask & (1 << index) and row["reference_label"] == "same_event"]
            tightened = [min(prepared[index]["features"][feature] for index in positives)
                         for feature in selection.FEATURES]
            tight_mask = sum(1 << index for index, row in enumerate(prepared)
                             if predicts(row, {**candidate(), "thresholds": tightened}))
            assert tight_mask in represented_masks
            assert tight_mask & mask == tight_mask
            tight_metrics = result["metrics_map"][hex(tight_mask)]
            assert tight_metrics["eligible"]
            assert tight_metrics["known_same_coverage_weighted"] == metrics["known_same_coverage_weighted"]
            assert tight_metrics["precision_pessimistic_weighted"] >= metrics["precision_pessimistic_weighted"]


def test_unknown_dates_exclude_only_gated_positive_subsets():
    rows, judgments = fixtures(8)
    rows[0]["publication_gap_days"] = None
    result = evaluate(rows, judgments)
    assert result["gate_summaries"][0]["evaluated_subsets"] == 1
    assert all(item["evaluated_subsets"] == 0 for item in result["gate_summaries"][1:])
    assert predicts(rows[0], candidate())
    assert not predicts(rows[0], candidate(30))


def test_incomplete_processing_is_not_a_geometric_impossibility_claim():
    rows, judgments = fixtures()
    rows[0]["features"]["pooled_cosine"] = float("nan")
    result = evaluate(rows, judgments)
    assert result["status"] == "incomplete_features"
    assert not result["search_complete"]
    rows, judgments = fixtures()
    judgments[rows[0]["pair_id"]] = {"status": "unknown"}
    result = evaluate(rows, judgments)
    assert result["status"] == "incomplete_references"
    assert result["all_label_counts"]["unknown"] == 1
    assert not result["search_complete"]


def test_insufficient_positive_support_is_explicit():
    rows, judgments = fixtures(7)
    result = evaluate(rows, judgments)
    assert result["status"] == "insufficient_positive_support"
    assert result["search_complete"]
    assert result["evaluated_generating_subsets"] == 0


def test_holdout_features_and_labels_cannot_change_development_result():
    rows, judgments = fixtures()
    heldout, other_judgments = fixtures(fold="validation")
    heldout[0]["features"]["pooled_cosine"] = .12345
    assert evaluate(rows + heldout, {**judgments, **other_judgments}) == evaluate(rows, judgments)


def test_frozen_validation_keeps_original_criteria_and_unknowns():
    rows, judgments = fixtures(30, 6, 0, "validation")
    result = validate(rows, judgments, candidate())
    assert result["status"] == "provisional_model_reference_pass"
    assert not result["metrics"]["human_validated"]
    assert not result["metrics"]["recall_pass_claim"]
    judgments[rows[0]["pair_id"]] = {"status": "failed"}
    result = validate(rows, judgments, candidate())
    assert result["status"] == "inconclusive"
    assert result["metrics"]["selected_label_counts"]["failed"] == 1


def test_positive_count_and_development_bound_are_not_silently_truncated():
    rows, judgments = fixtures(15)
    with pytest.raises(ValueError):
        evaluate(rows, judgments)
    rows, judgments = fixtures(9, 100)
    with pytest.raises(ValueError):
        evaluate(rows, judgments)


def test_predicate_rejects_unregistered_features_and_ignores_labels():
    rows, _ = fixtures()
    rows[0]["label"] = "different_event"
    assert predicts(rows[0], candidate())
    with pytest.raises(ValueError):
        predicts(rows[0], {**candidate(), "features": ["judge_event_date"] * 5})
