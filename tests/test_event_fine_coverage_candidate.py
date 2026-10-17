"""Two source-free fine-grid selection checks; no research labels or data."""
from newsresearch.event_coverage_candidate import coverage_grid
from newsresearch.event_fine_coverage_candidate import DELTAS, METHOD
from test_event_coverage_candidate import RULE, edge


def test_fine_grid_chooses_largest_margin_passing_both_retention_floors() -> None:
    groups = {"triple": ["a", "b", "c"], "pair": ["d", "e"]}
    rows = [edge("a", "b", .61), edge("a", "c", .61), edge("b", "c", .61), edge("d", "e", .5315)]
    result = coverage_grid(groups, rows, RULE, deltas=DELTAS, method=METHOD)
    assert tuple(row["delta"] for row in result["variants"]) == DELTAS
    assert result["selected"]["delta"] == .06
    assert result["selected"]["retained_pairs_fraction"] == 1
    assert not next(row for row in result["variants"] if row["delta"] == .065)["eligible"]


def test_fine_grid_can_retain_coarse_margin_without_claiming_a_stronger_choice() -> None:
    groups = {"triple": ["a", "b", "c"], "pair": ["d", "e"]}
    rows = [edge("a", "b", .61), edge("a", "c", .61), edge("b", "c", .61), edge("d", "e", .526)]
    result = coverage_grid(groups, rows, RULE, deltas=DELTAS, method=METHOD)
    assert result["selected"]["delta"] == .05
    assert all(not row["eligible"] for row in result["variants"] if row["delta"] > .05)
    assert result["baseline_replay_passed"]
