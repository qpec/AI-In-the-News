"""Synthetic software checks, not corpus event-accuracy evidence."""

from copy import deepcopy

import pytest

from newsresearch import event_pair_selection as selection
from newsresearch.event_pair_conjunction import evaluate, predicts, validate


def fixtures(same=9, fold="development"):
    rows, judgments = [], {}
    cases = [("same_event", .95, .95)] * same
    cases += [("different_event", .95, .2)] * 8
    cases += [("different_event", .2, .95)] * 8
    cases += [("uncertain", .2, .2)] * 2
    for index, (label, first, second) in enumerate(cases):
        pair_id = f"{fold}-{index:03}"
        features = {name: .2 for name in selection.FEATURES}
        features.update(pooled_cosine=first, first_passage_cosine=second)
        rows.append({"pair_id": pair_id, "left": f"{fold}-l{index}",
                     "right": f"{fold}-r{index}", "fold": fold,
                     "features": features, "inclusion_probability": .5,
                     "publication_gap_days": .5})
        judgments[pair_id] = {"status": "completed", "label": label}
    return rows, judgments


def candidate(gate=None):
    return {"features": ["pooled_cosine", "first_passage_cosine"],
            "thresholds": [.9, .9], "publication_gap_days": gate}


def test_two_features_exclude_complementary_single_feature_false_matches():
    rows, judgments = fixtures()
    original = deepcopy(rows)
    assert selection.evaluate(rows, judgments)["best_candidate"] is None
    result = evaluate(rows, judgments)
    best = result["best_candidate"]
    assert best["features"] == candidate()["features"]
    assert best["thresholds"] == [.95, .95]
    assert best["publication_gap_days"] is None
    assert best["metrics"]["selected_label_counts"]["same_event"] == 9
    assert best["metrics"]["selected_label_counts"]["different_event"] == 0
    assert best["metrics"]["review_label_counts"]["uncertain"] == 2
    assert len(result["candidates"]) == 40
    assert rows == original


def test_all_parameter_combinations_and_mask_references_are_preserved():
    rows, judgments = fixtures()
    result = evaluate(rows, judgments)
    grid = result["full_grid"]["rows"]
    assert len(grid) == result["evaluated_parameter_combinations"]
    assert len(grid) == sum(item["evaluated_count"] for item in result["candidates"])
    assert result["distinct_prediction_masks"] == len(result["metrics_map"])
    assert len(result["metrics_map"]) < len(grid)
    assert all(item[3] in result["metrics_map"] for item in grid)
    for variant_id, left_index, right_index, mask_id in grid[::137]:
        variant = result["candidates"][variant_id]
        parameters = {"features": variant["features"],
                      "thresholds": [result["thresholds_by_feature"][variant["features"][0]][left_index],
                                     result["thresholds_by_feature"][variant["features"][1]][right_index]],
                      "publication_gap_days": variant["publication_gap_days"]}
        expected = sum(1 << index for index, row in enumerate(rows) if predicts(row, parameters))
        assert hex(expected) == mask_id


def test_selected_uncertain_retains_label_and_enters_precision_denominator():
    rows, judgments = fixtures()
    rows[-1]["features"].update(pooled_cosine=.95, first_passage_cosine=.95)
    best = evaluate(rows, judgments)["best_candidate"]
    assert best["metrics"]["precision_pessimistic_observed"] == .9
    assert best["metrics"]["selected_label_counts"]["uncertain"] == 1
    assert best["metrics"]["selected_label_counts"]["different_event"] == 0


def test_original_sampling_weights_prevent_apparent_precision_pass():
    rows, judgments = fixtures()
    rows[-1]["features"].update(pooled_cosine=.95, first_passage_cosine=.95)
    rows[-1]["inclusion_probability"] = .001
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    diagnostic = result["candidates"][0]["diagnostic_best_candidate"]
    assert diagnostic["metrics"]["precision_pessimistic_observed"] == .9
    assert diagnostic["metrics"]["precision_pessimistic_weighted"] < .1


def test_missing_publication_dates_require_review_under_gate():
    rows, _ = fixtures()
    row = rows[0]
    row["publication_gap_days"] = None
    assert predicts(row, candidate())
    assert not predicts(row, candidate(30))
    row["publication_gap_days"] = 31
    assert not predicts(row, candidate(30))
    assert predicts(row, candidate())


def test_label_blind_predicate_does_not_use_judgment_or_event_facts():
    rows, _ = fixtures()
    row = rows[0]
    row.update(label="different_event", extracted_event_date="different", status="failed")
    assert predicts(row, candidate())


def test_frozen_validation_reuses_unchanged_policy():
    rows, judgments = fixtures(30, "validation")
    result = validate(rows, judgments, candidate())
    assert result["status"] == "provisional_model_reference_pass"
    assert result["metrics"]["auto_link_pairs"] == 30
    assert not result["metrics"]["recall_pass_claim"]
    assert result["metrics"]["accepted_dossiers"] == 0
    assert result["policy"]["eligibility_policy"]["validation"] == selection.POLICY["validation"]


def test_incomplete_validation_never_becomes_negative():
    rows, judgments = fixtures(30, "validation")
    judgments[rows[0]["pair_id"]] = {"status": "unknown"}
    result = validate(rows, judgments, candidate())
    assert result["status"] == "inconclusive"
    assert result["metrics"]["selected_label_counts"]["unknown"] == 1
    assert result["metrics"]["selected_label_counts"]["different_event"] == 0


def test_heldout_values_and_labels_do_not_change_development_selection():
    rows, judgments = fixtures()
    heldout, other_judgments = fixtures(fold="validation")
    heldout[0]["features"]["pooled_cosine"] = .912345
    assert evaluate(rows + heldout, {**judgments, **other_judgments}) == evaluate(rows, judgments)
    with pytest.raises(ValueError):
        evaluate(rows, judgments, phase="validation")


def test_weighted_coverage_is_not_relaxed_to_force_candidate():
    rows, judgments = fixtures()
    rows[0]["features"].update(pooled_cosine=.1, first_passage_cosine=.1)
    rows[0]["inclusion_probability"] = .001
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    assert any("known_same_coverage_weighted_below_0.50" in item["eligibility_reasons"]
               for item in result["metrics_map"].values())


def test_missing_features_and_small_positive_support_block_candidates():
    rows, judgments = fixtures(7)
    assert evaluate(rows, judgments)["best_candidate"] is None
    rows, judgments = fixtures()
    rows[0]["features"]["max_passage_cosine"] = float("nan")
    result = evaluate(rows, judgments)
    assert not result["processing_complete"]
    assert result["best_candidate"] is None


def test_development_bound_and_registered_feature_pairs_are_enforced():
    rows, judgments = fixtures(101)
    with pytest.raises(ValueError):
        evaluate(rows, judgments)
    for features in (["pooled_cosine", "pooled_cosine"], ["judge_event_date", "pooled_cosine"]):
        parameters = {**candidate(), "features": features}
        with pytest.raises(ValueError):
            predicts(rows[0], parameters)
