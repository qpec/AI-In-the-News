"""Guard against topic-only, ambiguous and missing-context automatic matches."""
from newsresearch.luna_scalable_rules_v2 import calibrate, rule_label


def detail(**updates):
    return {"single_variant": True, "publication_gap_days": 1, "shared_names": 1,
        "score": .30, "action": .25, "lexical": .20, "shared_words": 4, **updates}


def test_two_channels_do_not_treat_actor_only_overlap_as_identity():
    assert rule_label(detail(), .25) == "same_event"
    assert rule_label(detail(shared_names=2, action=0, lexical=.30, shared_words=6), .25) == "same_event"
    for change in ({"action": 0}, {"shared_names": 0}, {"lexical": .05},
                   {"single_variant": False}, {"publication_gap_days": None},
                   {"publication_gap_days": 56}):
        assert rule_label(detail(**change), .25) == "unresolved"
    assert rule_label(detail(shared_names=2, action=0, lexical=.18, shared_words=6), .20) == "unresolved"


def test_calibration_blocks_false_or_uncertain_calls_and_freezes_ties():
    rows = [{"features": detail(score=.30), "reference": "same_event"},
        {"features": detail(score=.24), "reference": "insufficient_evidence"},
        {"features": detail(score=.22), "reference": "different_event"}]
    result = calibrate(rows)
    assert result["selection_passed"]
    assert result["selected"]["threshold"] == .30
    assert result["selected"]["correct_same"] == 1
    assert result["selected"]["unverifiable_same"] == result["selected"]["false_same"] == 0
    failed = calibrate([{"features": detail(score=.95), "reference": "different_event"}])
    assert not failed["selection_passed"]
