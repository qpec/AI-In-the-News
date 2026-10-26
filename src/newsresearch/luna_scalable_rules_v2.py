"""Second deterministic rule, developed on frozen development panels only."""
from __future__ import annotations

from typing import Any

METHOD = "luna-scalable-two-channel-rule-v2"
THRESHOLDS = (.18, .20, .225, .25, .275, .30, .35, .40, .45, .50, .60, .70, .80, .90)


def rule_label(values: dict[str, Any], threshold: float) -> str:
    """Require action+word agreement or stronger wording plus two names.

    Scores are heuristics, not probabilities; failure means unresolved. This
    does not resolve paraphrases, subevent boundaries or publication-date gaps.
    """
    gap = values["publication_gap_days"]
    if (not values["single_variant"] or gap is None or gap > 14
            or values["shared_names"] < 1 or values["score"] < threshold):
        return "unresolved"
    action_channel = values["action"] >= .10 and values["lexical"] >= .10 and values["shared_words"] >= 2
    wording_channel = values["shared_names"] >= 2 and values["lexical"] >= .25 and values["shared_words"] >= 5
    return "same_event" if action_channel or wording_channel else "unresolved"


def metrics(pairs: list[dict[str, Any]], threshold: float) -> dict[str, Any]:
    calls = [p for p in pairs if rule_label(p["features"], threshold) == "same_event"]
    correct = sum(p["reference"] == "same_event" for p in calls)
    false = sum(p["reference"] == "different_event" for p in calls)
    unclear = sum(p["reference"] == "insufficient_evidence" for p in calls)
    positives = sum(p["reference"] == "same_event" for p in pairs)
    return {"threshold": threshold, "called_same": len(calls), "correct_same": correct,
        "false_same": false, "unverifiable_same": unclear, "reference_same": positives,
        "same_precision_on_clear_references": correct / (correct + false) if correct + false else None,
        "same_recall_on_references": correct / positives if positives else None,
        "unresolved": len(pairs) - len(calls)}


def calibrate(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    grid = [metrics(pairs, threshold) for threshold in THRESHOLDS]
    admissible = [m for m in grid if not m["false_same"] and not m["unverifiable_same"]]
    selected = max(admissible, key=lambda m: (m["correct_same"], m["threshold"])) if admissible else metrics(pairs, .90)
    return {"grid": grid, "selected": selected, "selection_passed": bool(admissible and selected["correct_same"])}
