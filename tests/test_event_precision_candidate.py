"""Source-free checks for scoped anchors and the single fixed split policy."""
from copy import deepcopy

import pytest

from newsresearch.common import AuditError, canonical, digest
from newsresearch.event_pair_selection import FEATURES
from newsresearch.event_precision_candidate import split_candidate, verified_record


def edge(left: str, right: str, value: float) -> dict:
    return {"left": left, "right": right, "pair_id": digest(sorted((left, right))), "status": "completed",
            "publication_gap_days": 7, "features": dict.fromkeys(FEATURES, value)}


RULE = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}


def test_retained_anchor_rejects_tampered_payload_or_identity() -> None:
    payload = {"fixture": "No real research data"}
    artifact = digest(payload)
    row = {"kind": "fixture", "logical_key": "fixture", "artifact": artifact,
           "payload": canonical(payload), "supersedes": None}
    identifier = digest({"kind": row["kind"], "key": row["logical_key"], "payload": artifact, "supersedes": None})
    row["id"] = identifier
    assert verified_record(row, identifier, "fixture") == payload
    with pytest.raises(AuditError, match="content_changed"):
        verified_record({**row, "payload": canonical({"fixture": "changed"})}, identifier, "fixture")
    with pytest.raises(AuditError, match="content_changed"):
        verified_record({**row, "logical_key": "changed"}, identifier, "fixture")


def test_missing_original_pair_blocks_preparation() -> None:
    with pytest.raises(AuditError, match="missing_original_within_pair"):
        split_candidate({"old": ["a", "b", "c"]}, [edge("a", "b", .9), edge("b", "c", .9)], RULE)


def test_fixed_margin_splits_only_and_preserves_original_input() -> None:
    groups = {"old": ["a", "b", "c"], "singleton": ["d"]}
    scored = [edge("a", "b", .9), edge("a", "c", .6), edge("b", "c", .6), edge("c", "d", .99)]
    before = deepcopy((groups, scored, RULE))
    result = split_candidate(groups, scored, RULE)
    assert (groups, scored, RULE) == before
    assert sorted(sorted(row["members"]) for row in result["groups"]) == [["a", "b"], ["c"], ["d"]]
    assert result["rule"]["thresholds"] == [.625] * 5
    assert result["rule"]["publication_gap_days"] == 7
    assert result["baseline"]["within_pairs"] == 3 and result["candidate"]["within_pairs"] == 1
    assert result["candidate"]["singletons"] == 2 and result["source_count"] == 4
    assert result["baseline_replay_passed"] and not result["original_memberships_changed"]
    assert result["precision"] is None and len(result["removed_within_pairs"]) == 2
