"""Constructed metadata only: sampling coverage, uncertainty and clustered ratios."""
import pytest

from newsresearch.luna_group_validation import (
    build_anchor_candidates,
    candidate_pool_recall,
    group_precision,
    realized_workload,
    sample_validation_frames,
)


def test_fixed_frames_preserve_large_groups_and_count_actual_exposures() -> None:
    groups = {"small": ["b", "a"], "large": ["c", "d", "e", "f"], "singleton": ["g"]}
    sample = sample_validation_frames(groups, seed="registered-fixture", group_sample_size=300,
                                      anchor_sample_size=100)
    reordered = sample_validation_frames(dict(reversed(list(groups.items()))), seed="registered-fixture")
    assert sample == reordered
    assert sample["group_frame"]["N"] == sample["group_frame"]["n"] == 2
    assert sample["group_frame"]["pi"] == 1
    assert sample["group_frame"]["planning_worst_case_95_half_width"] == 0
    assert sample["anchor_frame"]["n"] == 7
    assert "g" in sample["anchor_frame"]["selected_ids"]
    assert sample["selected_group_members"]["large"] == ["c", "d", "e", "f"]
    frame = build_anchor_candidates("a", sample["frozen_membership"], pooled_vector_ids=["c"],
                                    keyword_ids=["d", "c"], provider_ids=[], seed="registered-fixture",
                                    outside_controls=2)
    channels = {row["candidate"]: row["channels"] for row in frame["candidates"]}
    assert channels["b"] == ["frozen_group"]
    assert channels["c"] == ["keyword", "pooled_vector"]
    assert frame["outside_controls"]["N"] == 3 and frame["outside_controls"]["pi"] == 2 / 3
    workload = realized_workload(sample["selected_group_members"], [frame], max_article_exposures=10)
    assert workload["primary_requests"] == 3 and workload["article_exposures"] == 12
    assert not workload["within_budget"] and not workload["authorization_granted"]
    assert workload["automatic_retries"] == 0
    with pytest.raises(ValueError, match="multiple frozen groups"):
        sample_validation_frames({"one": ["a"], "two": ["a"]}, seed="fixture")


def test_model_reference_bounds_and_anchor_bootstrap_do_not_claim_global_recall() -> None:
    precision = group_precision(["a", "b", "c", "d", "e"],
                                {"a": "same_event", "b": "mixed", "c": "uncertain", "d": "failed"})
    assert precision["complete_case_precision"] == 0.5
    assert precision["identified_bounds"] == {"lower": 0.2, "upper": 0.8}
    assert precision["counts"]["pending"] == 1 and precision["pair_precision"] is None
    assert precision["complete_case_wilson_95"] == pytest.approx([0.0945312057, 0.9054687943])
    membership = {"a": "one", "b": "one", "c": "two", "d": "two", "e": "three"}
    rows = [{"anchor": "a", "candidate": "b", "label": "same_event"},
            {"anchor": "a", "candidate": "c", "label": "same_event"},
            {"anchor": "a", "candidate": "e", "label": "uncertain"},
            {"anchor": "c", "candidate": "d", "label": "same_event"},
            {"anchor": "c", "candidate": "b", "label": "pending"}]
    recall = candidate_pool_recall(["a", "c"], rows, membership, bootstrap_seed="registered-fixture")
    repeated = candidate_pool_recall(["c", "a"], list(reversed(rows)), membership,
                                     bootstrap_seed="registered-fixture")
    assert recall == repeated
    assert recall["complete_case_candidate_pool_recall"] == 2 / 3
    assert recall["identified_bounds"]["lower"] == 2 / 5
    assert recall["identified_bounds"]["upper"] == 2 / 3
    assert recall["bootstrap"]["defined_replicates"] == 2000
    assert recall["bootstrap"]["complete_case_95"] == [0.5, 1.0]
    assert recall["full_corpus_recall"] is None and not recall["human_validated"]
    with pytest.raises(ValueError, match="retain all frozen co-members"):
        candidate_pool_recall(["a", "c"], rows[:-2] + rows[-1:], membership, bootstrap_seed="fixture")
    missing = candidate_pool_recall(["e"], [], membership, bootstrap_seed="fixture")
    assert missing["complete_case_candidate_pool_recall"] is None
    assert missing["bootstrap"]["complete_case_95"] is None
