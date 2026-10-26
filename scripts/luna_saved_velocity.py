"""Wall-clock review threshold for cumulative saved results, not token use."""
from datetime import datetime


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def review(progresses, now, policy):
    seconds, fraction, baseline = policy["window_seconds"], policy["fraction"], policy["baseline_saved_per_minute"]
    if seconds != 900 or fraction != 0.1 or baseline <= 0:
        raise ValueError("invalid_velocity_review_policy")
    observations = sorted(progresses, key=lambda p: epoch(p["updated_at"]))
    threshold = baseline * fraction
    result = {"requested_seconds": seconds, "baseline_saved_per_minute": baseline,
        "threshold_saved_per_minute": threshold, "fraction": fraction,
        "includes_pauses_and_preparation": True, "automatic_stop": False}
    candidates = [p for p in observations if epoch(p["updated_at"]) <= now - seconds]
    if not observations or not candidates:
        return {**result, "window_complete": False, "recheck_required": None, "saved_per_minute": None}
    first, last = candidates[-1], observations[-1]
    elapsed = now - epoch(first["updated_at"])
    delta = last["new_returned"] - first["new_returned"]
    if elapsed < seconds or delta < 0 or epoch(last["updated_at"]) > now:
        raise ValueError("nonmonotonic_velocity_observation")
    rate = delta * 60 / elapsed
    return {**result, "window_complete": True, "from": first["updated_at"], "to_epoch": now,
        "latest_recorded_count_at": last["updated_at"], "observed_seconds": elapsed,
        "new_saved": delta, "saved_per_minute": rate, "baseline_percent": rate / baseline * 100,
        "recheck_required": rate <= threshold,
        "basis": "Comparable cumulative saved-count observations; wall time includes startup and stopped gaps. No inferred output during gaps."}
