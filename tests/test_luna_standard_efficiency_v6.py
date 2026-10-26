"""No network: reservation boundaries, changing ceilings and cumulative pace."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from newsresearch.common import AuditError

spec = importlib.util.spec_from_file_location("efficiency_monitor", Path(__file__).resolve().parents[1] / "scripts/check_luna_standard_efficiency_v6.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


def test_window_excludes_old_and_future_and_counts_frozen_output():
    rows = [(40, 4096, 0), (41, 8000, 3904), (100, 8000, 3904), (101, 8000, 3904)]
    result = monitor.utilization(rows, 100, 0, 60, 20000, 20000)
    assert result["admissions"] == 2 and result["reserved_tokens"] == 16000
    assert result["utilization_percent"] == 80 and result["target_met"]
    assert result["exact_input_tokens"] == 7808 and result["maximum_output_tokens"] == 8192
    assert not result["warmup"]
    with pytest.raises(AuditError, match="reservation_count_mismatch"):
        monitor.utilization([(41, 8000, 4000)], 100, 0, 60, 20000, 20000)


def test_warmup_and_changed_ceiling_are_not_false_precise_success():
    result = monitor.utilization([(99, 8000, 3904)], 100, 70, 900, 10000, 20000)
    assert result["warmup"] and result["observed_seconds"] == 30
    assert result["utilization_bounds_percent"] == [80, 160]
    assert result["utilization_percent"] is None and result["target_met"] is None
    with pytest.raises(AuditError, match="efficiency_window_or_ceiling"):
        monitor.utilization([], 100, 100, 60, 10000, 10000)


def progress(minute, saved):
    return {"updated_at": f"2026-10-20T00:{minute:02d}:00+00:00", "new_returned": saved,
        "count_held": 1, "corpora": {"a": {"returned": saved, "pending": 10, "unsubmitted": 91}}}


def test_pace_uses_recent_cumulative_saves_and_excludes_held_identity():
    result = monitor.output_pace([progress(0, 100), progress(10, 150), progress(20, 200), progress(40, 400)])
    assert result["basis"] == "recent_recorded_progress" and result["new_saved"] == 200
    assert result["saved_per_minute"] == 10 and result["remaining_eligible_including_pending"] == 100
    assert result["remaining_runtime_hours"] == pytest.approx(1 / 6)
    paused = monitor.output_pace([progress(20, 400), progress(40, 400)])
    assert paused["saved_per_minute"] == 0 and paused["remaining_runtime_hours"] is None
    with pytest.raises(AuditError, match="nonmonotonic_progress"):
        monitor.output_pace([progress(20, 400), progress(40, 399)])


def test_startup_fallback_and_no_elapsed_time():
    first = progress(0, 100)
    assert monitor.output_pace([first])["saved_per_minute"] is None
    later = deepcopy(first)
    later.update(updated_at="2026-10-20T00:05:00+00:00", new_returned=150)
    later["corpora"]["a"]["returned"] = 150
    assert monitor.output_pace([first, later])["basis"] == "overall_current_execution_fallback"
