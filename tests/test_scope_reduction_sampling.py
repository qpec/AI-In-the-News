"""Synthetic finite-frame planning tests; no corpus inference or models."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from scipy.stats import hypergeom

SPEC = importlib.util.spec_from_file_location(
    "scope_reduction_sampling", Path(__file__).resolve().parents[1] / "scripts/scope_reduction_sampling.py",
)
assert SPEC is not None and SPEC.loader is not None
sampling = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sampling)


@pytest.mark.parametrize("population,target", [(1, "0.01"), (10, "0.05"), (100, "0.01"), (500, "0.05")])
def test_minimum_zero_miss_n_is_minimal(population, target):
    plan = sampling.minimum_zero_miss_sample(population, target)
    n = plan["minimum_n_if_zero_misses_and_zero_unresolved"]
    allowed = plan["allowed_population_misses"]
    assert sampling.omission_upper_bound(population, n, 0, 0)["upper_missed_report_count"] <= allowed
    assert n == 0 or sampling.omission_upper_bound(population, n - 1, 0, 0)["upper_missed_report_count"] > allowed


def test_one_sided_small_population_coverage_is_conservative():
    # Enumerate the exact distribution, not a Monte Carlo demonstration.
    for population in range(1, 16):
        for n in range(population + 1):
            upper = [sampling.omission_upper_bound(population, n, x, 0)["upper_missed_report_count"]
                     for x in range(n + 1)]
            for positives in range(population + 1):
                noncoverage = sum(
                    float(hypergeom.pmf(x, population, positives, n))
                    for x in range(n + 1)
                    if upper[x] < positives
                )
                assert noncoverage <= sampling.STRATUM_ALPHA + 1e-12


def test_unresolved_labels_increase_bound_and_all_unresolved_gives_population():
    known = sampling.omission_upper_bound(100, 60, 0, 0)
    uncertain = sampling.omission_upper_bound(100, 60, 0, 10)
    all_unknown = sampling.omission_upper_bound(100, 60, 0, 60)
    assert known["upper_missed_report_count"] < uncertain["upper_missed_report_count"]
    assert all_unknown["upper_missed_report_count"] == 100
    assert uncertain["possible_sample_misses"] == 10
    assert uncertain["event_recall"] is None


def test_empty_frame_and_census_do_not_invent_fraction_or_negative_labels():
    assert sampling.omission_upper_bound(0, 0, 0, 0)["upper_missed_report_fraction"] is None
    assert sampling.omission_upper_bound(8, 8, 2, 3)["upper_missed_report_count"] == 5
    assert sampling.omission_upper_bound(8, 0, 0, 0)["upper_missed_report_count"] == 8


def test_draw_is_order_invariant_disjoint_and_probability_logged():
    values = [f"incident-reports:unit-{n:03}" for n in range(80)]
    first = sampling.plan_strata({"incident:missing": values, "cyber:empty": []}, seed="frozen-seed")
    second = sampling.plan_strata({"cyber:empty": [], "incident:missing": list(reversed(values))}, seed="frozen-seed")
    assert first == second
    row = first["strata"][1]
    assert row["n"] == len(set(row["selected_ids"])) == 60
    assert row["pi"] == 60 / 80
    assert row["pairwise_pi"] == 60 * 59 / (80 * 79)
    assert row["current_pending"] == 60
    assert row["all_labels_unresolved_case"]["upper_missed_report_count"] == 80
    assert first["final_looks"] == 1
    assert first["per_stratum_one_sided_alpha"] == 0.05 / 12
    assert first["authorization_granted"] is False


def test_small_stratum_is_census_with_exact_joint_probability():
    plan = sampling.plan_strata({"cyber:small": ["cyber:a", "cyber:b"]}, seed="fixed")
    row = plan["strata"][0]
    assert row["selected_ids"] == ["cyber:a", "cyber:b"]
    assert row["pi"] == row["pairwise_pi"] == 1


@pytest.mark.parametrize("frames", [
    {"x": ["a", "a"]}, {"x": ["a"], "y": ["a"]}, {"x": "abc"}, {"x": [""]},
])
def test_invalid_sampling_frames_rejected(frames):
    with pytest.raises(ValueError):
        sampling.plan_strata(frames, seed="fixed")


def test_family_size_and_invalid_counts_rejected():
    with pytest.raises(ValueError):
        sampling.plan_counts({str(i): 1 for i in range(13)}, seed="fixed")
    with pytest.raises(ValueError):
        sampling.plan_counts({"x": True}, seed="fixed")
    with pytest.raises(ValueError):
        sampling.omission_upper_bound(10, 5, 2, 4)
    with pytest.raises(ValueError):
        sampling.plan_counts({"x": 5}, seed="")
    with pytest.raises(ValueError):
        sampling.minimum_zero_miss_sample(10, "1")
