"""Synthetic prospective-design checks; no production frame or judgments."""
import importlib.util
from fractions import Fraction
from itertools import product
from math import comb
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime/final_validation_design.py"
SPEC = importlib.util.spec_from_file_location("final_validation_design", PATH)
design = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(design)


def test_pair_rank_bijection_and_large_frame_without_pair_matrix():
    for size in range(2, 16):
        expected = [(i, j) for i in range(size) for j in range(i + 1, size)]
        assert [design.pair_from_rank(size, r) for r in range(design.pair_count(size))] == expected
        assert [design.pair_rank(size, *pair) for pair in expected] == list(range(len(expected)))
    assert design.pair_count(6691) == 22_381_395
    assert design.pair_from_rank(6691, 22_381_394) == (6689, 6690)


@pytest.mark.parametrize("args", [(2, 1), (1, 0), (3, -1), (True, 0)])
def test_pair_rank_rejects_outside_or_noninteger_frames(args):
    with pytest.raises(ValueError):
        design.pair_from_rank(*args)


def test_nested_sample_keeps_nonzero_probabilities_census_and_exact_replay():
    result = design.nested_srs_ranks(100, [10, 30, 200], seed="predeclared", stratum="outside")
    assert result == design.nested_srs_ranks(100, [10, 30, 200], seed="predeclared", stratum="outside")
    assert len(set(result["rank_order"])) == 100
    assert {x for x in result["rank_order"]} == set(range(100))
    assert [x["sample_size"] for x in result["looks"]] == [10, 30, 100]
    assert result["looks"][0]["weight_numerator"] / result["looks"][0]["weight_denominator"] == 10
    assert set(result["rank_order"][:10]) <= set(result["rank_order"][:30])
    assert result["rank_order"] != design.nested_srs_ranks(100, [10, 30, 200], seed="predeclared", stratum="joined")["rank_order"]
    empty = design.nested_srs_ranks(0, [0, 10, 30], seed="predeclared", stratum="empty")
    assert empty["empty_stratum"] and empty["rank_order"] == []


@pytest.mark.parametrize("sizes", [[0, 10], [10, 9], [], [True, 10]])
def test_no_zero_probability_or_posthoc_shrinking_look(sizes):
    with pytest.raises(ValueError):
        design.nested_srs_ranks(100, sizes, seed="fixed", stratum="tail")


def test_joint_alpha_allocation_has_familywise_budget():
    alpha = design.simultaneous_tail_alpha(cells=7, looks=3)
    assert alpha * 7 * 3 * 2 == pytest.approx(.05)
    with pytest.raises(ValueError):
        design.simultaneous_tail_alpha(cells=0)


def test_zero_positive_bound_matches_exact_small_hypergeometric_inversion():
    for population in range(1, 25):
        for sample in range(population + 1):
            for alpha in (.05, .005):
                expected = max(m for m in range(population + 1)
                    if (comb(population - m, sample) / comb(population, sample)
                        if population - m >= sample else 0) >= alpha)
                assert design.zero_positive_upper_count(population, sample, alpha=alpha) == expected


def test_rare_tail_zero_hits_still_leaves_many_possible_missed_pairs():
    population = design.pair_count(6691)
    bound = design.zero_positive_upper_count(population, 1000, alpha=.05)
    assert 60_000 < bound < 70_000
    assert design.zero_positive_upper_count(population, 2000, alpha=.05) < bound
    assert design.zero_positive_upper_count(population, 1000, alpha=.005) > bound
    assert design.zero_positive_upper_count(40, 0, alpha=.05) == 40
    assert design.zero_positive_upper_count(40, 40, alpha=.05) == 0


@pytest.mark.parametrize("population,sample,alpha", [(10, 11, .05), (True, 0, .05), (10, -1, .05), (10, 1, 0), (10, 1, float("nan"))])
def test_invalid_bound_inputs_fail_closed(population, sample, alpha):
    with pytest.raises(ValueError):
        design.zero_positive_upper_count(population, sample, alpha=alpha)


def exact_mass(population, successes, sample, observed):
    if not 0 <= observed <= min(successes, sample) or sample - observed > population - successes:
        return Fraction(0)
    return Fraction(comb(successes, observed) * comb(population - successes, sample - observed),
                    comb(population, sample))


def row(name, population, sample, positive, *, unresolved=0, coassigned=False):
    return {"stratum": name, "population": population, "sample_size": sample,
            "positives": positive, "unresolved": unresolved, "coassigned": coassigned}


def test_general_inversion_matches_exact_enumeration_and_design_coverage():
    alpha = Fraction(1, 20)
    for population in range(1, 13):
        for sample in range(population + 1):
            intervals = {}
            for observed in range(sample + 1):
                compatible = []
                for successes in range(population + 1):
                    cdf = sum(exact_mass(population, successes, sample, x) for x in range(observed + 1))
                    sf = sum(exact_mass(population, successes, sample, x) for x in range(observed, sample + 1))
                    if cdf >= alpha and sf >= alpha:
                        compatible.append(successes)
                actual = design.positive_total_bounds(population, sample, observed, tail_alpha=float(alpha))
                assert actual == (min(compatible), max(compatible))
                intervals[observed] = actual
            for successes in range(population + 1):
                missed_mass = sum(exact_mass(population, successes, sample, x)
                    for x, (lo, hi) in intervals.items() if not lo <= successes <= hi)
                assert missed_mass <= 2 * alpha


def test_unresolved_envelope_contains_every_possible_completion_and_census_bounds():
    for population in range(1, 10):
        for sample in range(population + 1):
            for positive in range(sample + 1):
                unresolved = sample - positive
                lo, hi = design.positive_total_bounds(population, sample, positive,
                    unresolved=unresolved, tail_alpha=.025)
                for completed in range(positive, positive + unresolved + 1):
                    a, b = design.positive_total_bounds(population, sample, completed, tail_alpha=.025)
                    assert lo <= a <= b <= hi
    assert design.positive_total_bounds(10, 10, 3, unresolved=2, tail_alpha=.025) == (3, 5)
    assert design.positive_total_bounds(10, 0, 0, tail_alpha=.025) == (0, 10)


def test_sparse_positive_large_population_interval_does_not_collapse():
    population = design.pair_count(6691)
    zero = design.positive_total_bounds(population, 1000, 0, tail_alpha=.005)
    one = design.positive_total_bounds(population, 1000, 1, tail_alpha=.005)
    assert zero[0] == 0 and zero[1] > 100_000
    assert 1 <= one[0] < one[1] and one[1] > zero[1]
    assert zero[1] == design.zero_positive_upper_count(population, 1000, alpha=.005)


def test_joint_census_metrics_and_exact_simultaneous_error_budget():
    result = design.joint_pair_metrics([
        row("joined_retrieved", 2, 2, 1, coassigned=True),
        row("joined_unretrieved", 1, 1, 1, coassigned=True),
        row("split_retrieved", 2, 2, 1), row("split_unretrieved", 1, 1, 0),
        row("empty", 0, 0, 0)], documents=4)
    assert result["true_positive_total_bounds"] == [2, 2]
    assert result["false_negative_total_bounds"] == [1, 1]
    assert result["false_positive_total_bounds"] == [1, 1]
    assert result["true_negative_total_bounds"] == [2, 2]
    assert result["confusion_total_estimates"] == {"true_positive": 2., "false_positive": 1.,
        "false_negative": 1., "true_negative": 2.}
    assert result["pair_precision"]["interval"] == [2 / 3, 2 / 3]
    assert result["pair_recall"]["interval"] == [2 / 3, 2 / 3]
    assert result["requested_widths_met"]
    alpha = Fraction(result["tail_alpha_numerator"], result["tail_alpha_denominator"])
    assert alpha * result["tail_tests_budgeted"] == Fraction(1, 20)
    assert result["nonempty_strata"] == 4


def test_joint_point_estimates_use_population_weights_not_pooled_sample_fraction():
    result = design.joint_pair_metrics([
        row("joined_large", 3, 1, 1, coassigned=True),
        row("joined_small", 2, 2, 0, coassigned=True),
        row("split", 1, 1, 1)], documents=4)
    assert result["pair_precision"]["estimate"] == pytest.approx(.6)
    assert result["pair_recall"]["estimate"] == pytest.approx(.75)
    assert result["confusion_total_estimates"] == {"true_positive": 3., "false_positive": 2.,
        "false_negative": 1., "true_negative": 0.}
    assert not result["requested_widths_met"]


def test_joint_unknowns_keep_worst_case_counts_and_suppress_point_estimates():
    result = design.joint_pair_metrics([
        row("joined", 3, 3, 1, unresolved=1, coassigned=True),
        row("split", 3, 3, 1, unresolved=2)], documents=4)
    assert result["true_positive_total_bounds"] == [1, 2]
    assert result["false_negative_total_bounds"] == [1, 3]
    assert result["false_positive_total_bounds"] == [1, 2]
    assert result["true_negative_total_bounds"] == [0, 2]
    assert all(value is None for value in result["confusion_total_estimates"].values())
    assert result["pair_precision"]["interval"] == [1 / 3, 2 / 3]
    assert result["pair_recall"]["interval"] == [1 / 4, 2 / 3]
    assert result["pair_precision"]["estimate"] is None
    assert result["pair_recall"]["estimate"] is None
    assert not result["requested_widths_met"]
    unobserved = design.joint_pair_metrics([
        row("joined", 3, 0, 0, coassigned=True), row("split", 3, 0, 0)], documents=4)
    assert unobserved["pair_precision"]["interval"] == [0., 1.]
    assert unobserved["pair_recall"]["interval"] == [0., 1.]
    assert unobserved["pair_recall"]["state"] == "denominator_may_be_zero"
    assert not unobserved["requested_widths_met"]
    partially_resolved = design.joint_pair_metrics([
        row("joined", 3, 3, 1, unresolved=1, coassigned=True),
        row("split", 3, 3, 1)], documents=4)
    assert partially_resolved["confusion_total_estimates"] == {"true_positive": None,
        "false_positive": None, "false_negative": 1., "true_negative": 2.}


def test_empty_and_zero_denominators_do_not_claim_target_achievement():
    for documents in (0, 1):
        result = design.joint_pair_metrics([], documents=documents)
        assert result["state"] == "empty_pair_frame"
        assert result["pair_precision"]["interval"] is None
        assert result["pair_recall"]["interval"] is None
        assert result["tail_tests_budgeted"] == 0
        assert not result["requested_widths_met"]
    no_true_pairs = design.joint_pair_metrics([row("joined", 3, 3, 0, coassigned=True)], documents=3)
    assert no_true_pairs["pair_precision"]["interval"] == [0., 0.]
    assert no_true_pairs["pair_recall"]["state"] == "undefined_no_reference_positive_pairs"
    assert not no_true_pairs["requested_widths_met"]
    no_joined_pairs = design.joint_pair_metrics([row("split", 3, 3, 1)], documents=3)
    assert no_joined_pairs["pair_precision"]["state"] == "undefined_no_predicted_pairs"
    assert no_joined_pairs["pair_recall"]["interval"] == [0., 0.]
    assert not no_joined_pairs["requested_widths_met"]
    possible_only_joined = design.joint_pair_metrics([
        row("joined", 3, 0, 0, coassigned=True)], documents=3)
    assert possible_only_joined["pair_recall"]["interval"] == [1., 1.]
    assert possible_only_joined["pair_recall"]["state"] == "denominator_may_be_zero"
    assert not possible_only_joined["requested_widths_met"]


def test_joint_projection_covers_exact_stratified_sampling_distribution():
    # Three predicted and three split pairs; enumerate all possible reference
    # totals and sample outcomes. Confidence is conditional on these fixed labels.
    family_alpha = Fraction(1, 20)
    for tp, fn in product(range(4), repeat=2):
        if tp + fn == 0:
            continue
        covered = Fraction(0)
        for x, y in product(range(3), repeat=2):
            probability = exact_mass(3, tp, 2, x) * exact_mass(3, fn, 2, y)
            if not probability:
                continue
            result = design.joint_pair_metrics([
                row("joined", 3, 2, x, coassigned=True), row("split", 3, 2, y)], documents=4)
            p_lo, p_hi = result["pair_precision"]["interval"]
            r_lo, r_hi = result["pair_recall"]["interval"]
            if p_lo <= tp / 3 <= p_hi and r_lo <= tp / (tp + fn) <= r_hi:
                covered += probability
        assert covered >= 1 - family_alpha / 3


@pytest.mark.parametrize("change", [
    {"sample_size": 4}, {"positives": 2, "unresolved": 2}, {"coassigned": 1},
    {"population": True}, {"stratum": ""}, {"unexpected": "metadata"}])
def test_joint_invalid_strata_fail_closed(change):
    invalid = {**row("joined", 3, 3, 1, coassigned=True), **change}
    with pytest.raises(ValueError):
        design.joint_pair_metrics([invalid], documents=3)


def test_joint_missing_frame_duplicate_identifiers_and_bad_alpha_fail_closed():
    with pytest.raises(ValueError, match="incomplete_pair_population"):
        design.joint_pair_metrics([row("subset", 2, 2, 0)], documents=3)
    with pytest.raises(ValueError, match="stratum_frame_identity"):
        design.joint_pair_metrics([row("duplicate", 1, 1, 0), row("duplicate", 2, 2, 0)], documents=3)
    for alpha in (0, 1, True, float("nan")):
        with pytest.raises(ValueError):
            design.joint_pair_metrics([], documents=0, family_alpha=alpha)


@pytest.mark.parametrize("args", [(10, 11, 0, 0, .01), (10, 2, 2, 1, .01),
    (True, 0, 0, 0, .01), (10, 2, 0, 0, float("nan")), (10, 2, 0, 0, .5)])
def test_general_invalid_bounds_fail_closed(args):
    population, sample, positives, unresolved, alpha = args
    with pytest.raises(ValueError):
        design.positive_total_bounds(population, sample, positives, unresolved=unresolved, tail_alpha=alpha)
