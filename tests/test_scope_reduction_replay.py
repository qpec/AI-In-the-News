"""Synthetic software checks only; not empirical event-recall validation."""
import importlib.util
from pathlib import Path

import pytest

from newsresearch.common import ResearchError

SPEC = importlib.util.spec_from_file_location("scope_reduction_replay", Path(__file__).parents[1] / "scripts/scope_reduction_replay.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def fixture():
    rows = [{"source": "a", "candidates": [{"source": s, "pair": s} for s in "bcd"]}]
    metadata = {s: {"corpus_id": "incident-reports", "publisher": "one" if s in "ab" else "two",
        "event_uri": "e" if s in "ab" else None, "published_at": "2026-01-01T00:00:00Z" if s in "ab" else "2026-02-01T00:00:00Z"} for s in "abcd"}
    outcomes = {"b": {"status": "valid", "label": "different_event"},
        "c": {"status": "valid", "label": "same_event"}, "d": {"status": "invalid", "label": "same_event"}}
    return rows, outcomes, metadata


def test_replay_missing_labels_never_positive_and_no_refill():
    rows, outcomes, metadata = fixture()
    result = module.summarize(rows, outcomes, metadata, set())
    by_name = {row["scenario"]: row for row in result["scenarios"]}
    assert result["raw_positive_anchor_denominator"] == 1
    assert by_name["top1"]["raw_positive_anchors_lost"] == 1
    assert by_name["top1_different_publisher"].get("candidate_checks", 0) == 0
    assert by_name["top2_different_publisher"]["candidate_checks"] == 1
    assert by_name["top3_baseline"]["selected_missing"] == 1
    assert by_name["top3_baseline"]["raw_positive_anchors_retained"] == 1


def test_missing_event_retained_in_null_safe_scenario():
    rows, outcomes, metadata = fixture()
    result = module.summarize(rows, outcomes, metadata, set())
    by_name = {row["scenario"]: row for row in result["scenarios"]}
    assert by_name["top3_both_event_ids_required"]["raw_positive_anchors_lost"] == 1
    assert by_name["top3_equal_event_ids_missing_retained"]["raw_positive_anchors_retained"] == 1
    assert by_name["top3_seven_days_missing_retained"]["raw_positive_anchors_lost"] == 1


def test_missing_publisher_and_date_unknown_not_negative():
    assert module.publisher_relation({"publisher": None}, {"publisher": "x"}) == "unknown"
    assert module.keep_pair("different_publisher", {"publisher": None}, {"publisher": "x"})
    assert module.keep_pair("seven_days", {"published_at": None}, {"published_at": "2026-01-01T00:00:00Z"})
    assert module.date_gap("2026-01-01", "2026-01-04") is None


def test_flags_remain_separate_from_labels():
    rows, outcomes, metadata = fixture()
    result = module.summarize(rows, outcomes, metadata, {"c"})
    assert result["raw_cross_publisher_positive_anchor_denominator"] == 1
    assert result["unflagged_cross_publisher_positive_anchor_denominator"] == 0
    assert outcomes["c"]["label"] == "same_event"


def test_cross_corpus_rejected_before_comparison():
    rows, outcomes, metadata = fixture()
    metadata["c"]["corpus_id"] = "cybercrime"
    with pytest.raises(ResearchError, match="cross_corpus"):
        module.summarize(rows, outcomes, metadata, set())


def test_provenance_requires_path_and_hash():
    partition = {"manifests": {"incident-reports": {"bundles": [{"path": "one.zip", "sha256": "abc"}]},
        "cybercrime": {"bundles": [{"path": "two.zip", "sha256": "def"}]}}}
    assert module.assign_corpus({"bundle": "one.zip", "bundle_sha256": "abc"}, partition) == "incident-reports"
    with pytest.raises(ResearchError, match="unresolved"):
        module.assign_corpus({"bundle": "one.zip", "bundle_sha256": "def"}, partition)


def test_offline_owner_required(tmp_path):
    from newsresearch.common import Config
    with pytest.raises(ResearchError, match="original_existing_owner"):
        module.ReplayResearch(tmp_path)
    owner = tmp_path / module.OWNER
    owner.mkdir()
    with pytest.raises(ResearchError, match="offline"):
        module.ReplayResearch(owner, config=Config(offline=False))
