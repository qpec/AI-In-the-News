from datetime import datetime
from pathlib import Path
import sys

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import luna_saved_velocity as velocity

POLICY = {"window_seconds": 900, "fraction": 0.1, "baseline_saved_per_minute": 140}


def observed(minute, count):
    return {"updated_at": f"2026-10-20T00:{minute:02d}:00+00:00", "new_returned": count}


def moment(minute):
    return datetime.fromisoformat(f"2026-10-20T00:{minute:02d}:00+00:00").timestamp()


def test_full_window_threshold_and_pause_time_never_reset_baseline():
    result = velocity.review([observed(0, 1000), observed(15, 1210)], moment(15), POLICY)
    assert result["saved_per_minute"] == 14 and result["recheck_required"]
    assert not result["automatic_stop"] and result["window_complete"]
    assert not velocity.review([observed(0, 1000), observed(15, 1211)], moment(15), POLICY)["recheck_required"]
    # Current execution may have restarted at minute 10; cumulative history stays.
    resumed = velocity.review([observed(0, 1000), observed(5, 1000), observed(10, 1000), observed(15, 1210)], moment(15), POLICY)
    assert resumed["saved_per_minute"] == 14
    stopped = velocity.review([observed(0, 1000), observed(15, 1210)], moment(30), POLICY)
    assert stopped["saved_per_minute"] == 0 and stopped["recheck_required"]
    assert stopped["baseline_saved_per_minute"] == 140


def test_warmup_and_nonmonotonic_counts_cannot_claim_healthy_velocity():
    result = velocity.review([observed(0, 1000), observed(5, 1100)], moment(5), POLICY)
    assert not result["window_complete"] and result["recheck_required"] is None
    with pytest.raises(ValueError, match="nonmonotonic"):
        velocity.review([observed(0, 1000), observed(15, 999)], moment(15), POLICY)
