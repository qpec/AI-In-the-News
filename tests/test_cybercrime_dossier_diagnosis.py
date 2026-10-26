from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import diagnose_dossier_pilot_v2 as diagnosis  # noqa: E402


def test_existing_labels_distinguish_no_match_uncertain_competitor_and_low_clarity():
    def answer(kind, label, p):
        probabilities = {"same_event": 0., "related_event": 0., "different_event": 0., "uncertain": 0., "clear_single_event": 0.}
        probabilities[label] = p
        return {"kind": kind, "status": "valid", "label": label, "probabilities": probabilities}
    result = diagnosis.assignment_counts({"decisions": {
        "a": [answer("clarity", "clear_single_event", .99), answer("assignment", "same_event", .9), answer("assignment", "uncertain", .9)],
        "b": [answer("clarity", "clear_single_event", .7), answer("assignment", "different_event", .95)],
        "c": [answer("clarity", "clear_single_event", .99), answer("assignment", "same_event", .6)]},
        "proposals": {}, "unresolved": {"a": "competing_or_uncertain_candidates", "b": "focal_event_not_clear", "c": "competing_or_uncertain_candidates"},
        "shortlists": {}})
    assert result["articles"] == 3 and result["proposed"] == 0
    assert result["article_states"] == {"has_clear_positive": 1, "has_same_event_top_label": 2,
        "has_uncertain_competitor": 2, "exactly_one_positive_and_no_uncertain": 0, "all_clarity_pass": 2}
    assert result["candidate_labels"] == {"different_event": 1, "same_event": 2, "uncertain": 1}
    assert result["candidate_labels_meeting_085"] == {"different_event": 1, "same_event": 1, "uncertain": 1}


def test_competing_positive_fragments_keep_unasked_cross_pairs_unknown():
    def answer(dossier, label, same, different, related, uncertain):
        return {"kind": "assignment", "dossier_id": dossier, "status": "valid", "label": label,
            "probabilities": {"same_event": same, "different_event": different, "related_event": related, "uncertain": uncertain}}
    first = answer("g1", "same_event", .95, .02, .01, .02)
    second = answer("g2", "same_event", .9, .03, .02, .05)
    distant = answer("g3", "different_event", 0., .7, .3, 0.)
    value = {"decisions": {"article": [first, second, distant]}, "unresolved": {"article": "competing_or_uncertain_candidates"}}
    seeds = {"groups": {"g1": ["a", "b"], "g2": ["c", "d"]}, "pair_answers": []}
    result = diagnosis.assignment_competition(value, seeds)
    assert result["competing_reason_patterns"] == {"multiple_clear_positives": 1}
    assert result["cases"][0]["cross_pairs_between_clear_positive_candidate_groups"] == {"cross_pairs": 4, "unasked": 4}
    assert result["low_confidence_competitors_by_top_label"]["different_event"]["same_event_probability"]["max"] == 0.
