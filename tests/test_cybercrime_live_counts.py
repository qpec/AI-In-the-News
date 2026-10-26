"""Synthetic route aggregation only; no production data or provider calls."""
from pathlib import Path
import sys

import pytest
from newsresearch.common import AuditError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
from count_labels import aggregate  # noqa: E402


def test_current_decisions_override_stale_export_labels_and_expand_aliases():
    rows = [{"custom_id": "a", "request": "hash-a", "decision": {"status": "valid", "route": "keep"}, "unknown_or_billing_hold": False},
            {"custom_id": "b", "request": "hash-b", "decision": None, "unknown_or_billing_hold": True}]
    mapping = [{"custom_id": key, "canonical_custom_id": canonical, "request_hash": "hash-" + canonical,
                "exact_input_reuse": key != canonical, "status": "not_attempted", "decision": {"route": "exclude"}}
               for key, canonical in [("a", "a"), ("copy", "a"), ("b", "b"), ("c", "c")]]
    mapping.append({"custom_id": "sealed", "request_hash": None, "status": "sealed_validation"})
    result = aggregate(rows, mapping)
    assert result["unique_routes"] == {"keep": 1, "invalid_or_unknown": 1}
    assert result["article_routes_including_aliases"] == {"keep": 2, "invalid_or_unknown": 1, "no_stored_response": 1}
    assert result["aliases"] == 1 and result["selected_articles"] == 5
    assert result["responses_with_billing_or_outcome_hold"] == 1
    with pytest.raises(AuditError, match="duplicate_article"):
        aggregate(rows, mapping + [mapping[0]])
    mapping[0]["request_hash"] = "wrong"
    with pytest.raises(AuditError, match="request_mismatch"):
        aggregate(rows, mapping)
