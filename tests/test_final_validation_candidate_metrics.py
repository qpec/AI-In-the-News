from itertools import product
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
from final_validation_candidate_metrics import candidate_ratio_bounds, joint_pair_and_candidate_metrics
from final_validation_design import joint_pair_metrics


def cell(identity, population, positive, candidate, assigned=False, n=None, unresolved=0):
    return {"stratum": identity, "population": population, "sample_size": population if n is None else n,
            "positives": positive, "unresolved": unresolved, "coassigned": assigned,
            "candidate_exposure": candidate}


def test_census_candidate_recall_does_not_assume_coassignment_implies_exposure():
    rows = [cell("a", 4, 3, "exposed"), cell("b", 3, 1, "unexposed", True),
            cell("c", 3, 0, "unknown")]
    result = joint_pair_and_candidate_metrics(rows, documents=5)
    base = joint_pair_metrics([{k: v for k, v in row.items() if k != "candidate_exposure"} for row in rows], documents=5)
    assert {k: v for k, v in result.items() if k != "candidate_recall"} == base
    assert result["pair_recall"]["estimate"] == .25
    candidate = result["candidate_recall"]
    assert candidate["interval"] == [.75, .75]
    assert candidate["estimate"] == .75
    assert candidate["exposure_groups"]["unknown"]["pair_population"] == 3
    assert candidate["is_primary_stopping_target"] is False


def test_census_unknown_exposure_remains_identification_interval():
    result = joint_pair_and_candidate_metrics([
        cell("e", 3, 2, "exposed"), cell("n", 3, 1, "unexposed"),
        cell("u", 4, 3, "unknown", True)], documents=5)
    candidate = result["candidate_recall"]
    assert candidate["interval"] == [2 / 6, 5 / 6]
    assert candidate["estimate"] is None
    assert candidate["exposure_groups"]["unknown"]["positive_total_bounds"] == [3, 3]
    assert result["tail_tests_budgeted"] == 18


def test_all_unknown_reference_and_exposure_do_not_become_absent():
    result = joint_pair_and_candidate_metrics([cell("u", 10, 0, "unknown", n=5, unresolved=5)], documents=5)
    candidate = result["candidate_recall"]
    assert candidate["interval"] == [0, 1]
    assert candidate["state"] == "denominator_may_be_zero"
    assert candidate["estimate"] is None
    assert result["requested_widths_met"] is False


def test_zero_positive_census_has_undefined_recall_and_no_estimate():
    result = joint_pair_and_candidate_metrics([cell("e", 6, 0, "exposed", True)], documents=4)
    assert result["candidate_recall"]["state"] == "undefined_no_reference_positive_pairs"
    assert result["candidate_recall"]["interval"] is None
    assert result["candidate_recall"]["estimate"] is None


def test_exhaustive_small_count_regions_match_all_missing_exposure_assignments():
    bounds = [(lo, hi) for lo in range(3) for hi in range(lo, 3)]
    for exposed, unexposed, unknown in product(bounds, repeat=3):
        actual = []
        for e, n, u in product(range(exposed[0], exposed[1] + 1),
                               range(unexposed[0], unexposed[1] + 1),
                               range(unknown[0], unknown[1] + 1)):
            if e + n + u:
                actual.extend((e + retrieved_u) / (e + n + u) for retrieved_u in range(u + 1))
        result = candidate_ratio_bounds(exposed, unexposed, unknown)
        if not actual:
            assert result["interval"] is None
        else:
            assert result["interval"] == [min(actual), max(actual)]
            assert (result["state"] == "denominator_may_be_zero") == (sum(x[0] for x in (exposed, unexposed, unknown)) == 0)


@pytest.mark.parametrize("state", [None, "", "not_retrieved", False])
def test_exposure_state_must_be_explicit(state):
    with pytest.raises(ValueError, match="explicit_candidate_exposure_required"):
        joint_pair_and_candidate_metrics([cell("x", 3, 1, state)], documents=3)


@pytest.mark.parametrize("bounds", [(2, 1), (-1, 1), (False, 1), [0, 1]])
def test_invalid_count_regions_fail_closed(bounds):
    with pytest.raises(ValueError, match="candidate_positive_count_bounds_required"):
        candidate_ratio_bounds(bounds, (0, 0), (0, 0))
