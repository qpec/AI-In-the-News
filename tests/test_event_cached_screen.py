"""Pure fictional references only; no source, store or model access."""
from newsresearch.event_cached_screen import render, subset


def test_subsets_keep_per_study_conflicts_and_unresolved_without_pooled_accuracy():
    membership = {"a": "g", "b": "g", "c": "other"}
    tasks = [{"pair_id": pair, "left": left, "right": right, "phase": "evaluation", "stratum": "within_group"}
        for pair, left, right in (("ab", "a", "b"), ("ac", "a", "c"))]
    def study(identifier, label):
        return {"id": identifier, "study_key": identifier, "tasks": tasks,
            "outcomes": {"ab": {"status": "valid", "label": label, "assessment": identifier + "-ab"}}}
    result = subset(membership, [study("first", "same_event"), study("second", "different_event"), study("third", "uncertain")])
    assert [row["surviving"]["total"] for row in result["studies"]] == [1, 1, 1]
    assert [row["removed"]["pending"] for row in result["studies"]] == [1, 1, 1]
    assert result["overlap_pairs"] == 2 and result["conflicting_decisive_pairs"] == 1
    assert result["disagreeing_reference_pairs"] == 1
    assert [ref["label"] for ref in result["overlap_references"]["ab"]] == ["same_event", "different_event", "uncertain"]
    markdown = render({**result, "examples": []})
    assert "candidate precision remains unmeasured" in markdown
    assert "| first | removed | 1 | 0 | 0 | 0 | 1 |" in markdown
    assert "pooled into an accuracy estimate" in markdown
