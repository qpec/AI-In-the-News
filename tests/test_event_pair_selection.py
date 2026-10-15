"""Synthetic checks only: these fixtures are not research event labels."""

from copy import deepcopy

import pytest

from newsresearch.event_pair_selection import FEATURES, evaluate, validate


def fixtures(same=9, different=8, uncertain=4, fold="development"):
    rows, judgments = [], {}
    for index, label in enumerate(["same_event"] * same + ["different_event"] * different
                                   + ["uncertain"] * uncertain):
        pair_id = f"{fold}-{index:03}"
        rows.append({"pair_id": pair_id, "left": f"{fold}-l{index}",
                     "right": f"{fold}-r{index}", "fold": fold,
                     "features": {name: .95 if label == "same_event" else .2 for name in FEATURES},
                     "originaldistance": .05 if label == "same_event" else .8,
                     "inclusion_probability": .5, "publication_gap_days": .5})
        judgments[pair_id] = {"status": "completed", "label": label}
    return rows, judgments


def test_support_and_deterministic_simplest_ungated_choice():
    rows, judgments = fixtures()
    untouched = deepcopy(rows)
    result = evaluate(rows, judgments)
    candidate = result["best_candidate"]
    assert candidate["feature"] == "pooled_cosine"
    assert candidate["publication_gap_days"] is None
    assert candidate["threshold"] == .95
    assert candidate["metrics"]["selected_label_counts"]["same_event"] == 9
    assert candidate["metrics"]["review_label_counts"]["uncertain"] == 4
    assert result["all_label_counts"]["uncertain"] == 4
    assert len(result["candidates"]) == 20
    assert rows == untouched
    assert evaluate(list(reversed(rows)), judgments) == result


def test_one_perfect_pair_is_not_enough():
    rows, judgments = fixtures(same=1)
    assert evaluate(rows, judgments)["best_candidate"] is None


def test_uncertain_is_penalized_without_becoming_negative():
    rows, judgments = fixtures(9, 8, 1)
    for name in FEATURES:
        rows[-1]["features"][name] = .95
    candidate = evaluate(rows, judgments)["best_candidate"]
    assert candidate["metrics"]["precision_pessimistic_observed"] == .9
    assert candidate["metrics"]["selected_label_counts"]["uncertain"] == 1
    assert candidate["metrics"]["selected_label_counts"]["different_event"] == 0


def test_inverse_weights_can_block_apparently_good_observed_precision():
    rows, judgments = fixtures(9, 8, 1)
    rows[-1]["inclusion_probability"] = .001
    rows[-1]["features"] = {name: .95 for name in FEATURES}
    assert evaluate(rows, judgments)["best_candidate"] is None


def test_weighted_known_same_coverage_is_required():
    rows, judgments = fixtures()
    rows[0]["inclusion_probability"] = .001
    rows[0]["features"] = {name: .1 for name in FEATURES}
    assert evaluate(rows, judgments)["best_candidate"] is None


@pytest.mark.parametrize("status", ["failed", "pending", "unknown"])
def test_incomplete_status_blocks_acceptance_and_is_not_a_negative(status):
    rows, judgments = fixtures()
    judgments[rows[-1]["pair_id"]] = {"status": status, "label": "different_event"}
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    assert not result["processing_complete"]
    assert result["all_label_counts"][status] == 1
    assert result["all_label_counts"]["different_event"] == 8


def test_missing_or_invalid_features_fail_closed():
    rows, judgments = fixtures()
    rows[-1]["features"]["max_passage_cosine"] = float("nan")
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    assert len(result["feature_errors"]) == 1


def test_development_boundaries_do_not_use_validation_features_or_labels():
    rows, judgments = fixtures()
    heldout, heldout_judgments = fixtures(fold="validation")
    heldout[0]["features"] = {name: .912345 for name in FEATURES}
    base = evaluate(rows, judgments)
    assert evaluate(rows + heldout, {**judgments, **heldout_judgments}) == base
    assert all(item["threshold"] != .912345 for item in base["full_grid"])


def test_publication_gate_is_selective_and_unknown_dates_require_review():
    rows, judgments = fixtures()
    rows[-1]["features"] = {name: .95 for name in FEATURES}
    rows[-1]["publication_gap_days"] = None
    result = evaluate(rows, judgments)
    gated = next(item for item in result["candidates"]
                 if item["feature"] == "pooled_cosine" and item["publication_gap_days"] == 30)
    metrics = gated["best_candidate"]["metrics"]
    assert rows[-1]["pair_id"] in metrics["review_pair_ids"]
    assert metrics["review_label_counts"]["uncertain"] == 4
    assert metrics["unknown_publication_gap_pairs"] == 1


def test_repeated_hub_does_not_establish_disjoint_support():
    rows, judgments = fixtures()
    for row in rows[:9]:
        row["left"] = "shared-hub"
    result = evaluate(rows, judgments)
    assert result["best_candidate"] is None
    assert max(item["metrics"]["disjoint_positive_pair_lower_bound"]
               for item in result["full_grid"]) == 1


def test_validation_is_one_fixed_screen_without_recall_pass_claim():
    rows, judgments = fixtures(30, 6, 0, "validation")
    result = validate(rows, judgments, {"feature": "pooled_cosine", "threshold": .9,
                                        "publication_gap_days": None})
    assert result["status"] == "provisional_model_reference_pass"
    assert result["metrics"]["auto_link_pairs"] == 30
    assert not result["metrics"]["recall_pass_claim"]
    assert not result["metrics"]["human_validated"]
    assert result["metrics"]["accepted_dossiers"] == 0


def test_validation_tiny_or_incomplete_sample_is_inconclusive():
    rows, judgments = fixtures(19, 6, 0, "validation")
    parameters = {"feature": "pooled_cosine", "threshold": .9, "publication_gap_days": None}
    assert validate(rows, judgments, parameters)["status"] == "inconclusive"
    rows, judgments = fixtures(30, 6, 0, "validation")
    del judgments[rows[0]["pair_id"]]
    result = validate(rows, judgments, parameters)
    assert result["status"] == "inconclusive"
    assert result["metrics"]["selected_label_counts"]["pending"] == 1


@pytest.mark.parametrize("modification", ["duplicate", "zero_probability", "negative_gap"])
def test_invalid_sampling_identity_and_metadata_raise(modification):
    rows, judgments = fixtures()
    if modification == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif modification == "zero_probability":
        rows[0]["inclusion_probability"] = 0
    else:
        rows[0]["publication_gap_days"] = -1
    with pytest.raises(ValueError):
        evaluate(rows, judgments)


def test_validation_requires_a_frozen_registered_candidate():
    rows, judgments = fixtures()
    with pytest.raises(ValueError):
        evaluate(rows, judgments, phase="validation")
    with pytest.raises(ValueError):
        validate(rows, judgments, {"feature": "judge_event_date", "threshold": .9})


def test_returned_policy_cannot_mutate_later_selection_criteria():
    rows, judgments = fixtures(same=1)
    result = evaluate(rows, judgments)
    result["policy"]["development"]["minimum_selected_same"] = 0
    assert evaluate(rows, judgments)["policy"]["development"]["minimum_selected_same"] == 8


def test_malformed_reference_status_is_invalid_not_negative():
    rows, judgments = fixtures()
    judgments[rows[-1]["pair_id"]] = {"status": ["completed"]}
    result = evaluate(rows, judgments)
    assert result["all_label_counts"]["invalid"] == 1
    assert not result["processing_complete"]
