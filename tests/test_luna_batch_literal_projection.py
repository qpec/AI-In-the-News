"""Synthetic deterministic reference-projection checks only."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_event_contract_v2 as contract
    from luna_batch_literal_projection import project_literal_refs
finally:
    sys.path.pop(0)


def test_extra_unmatched_refs_recovered_across_only_four_literal_field_types() -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p2", "p1"]
    output["event"]["time"]["refs"] = ["p1", "p2"]
    output["event"]["participants"][1]["refs"] = ["p2", "p1"]
    output["event"]["facts"][0]["value"]["refs"] = ["p1", "p2"]
    original, original_packet = deepcopy(output), deepcopy(packet)
    result = project_literal_refs(output, packet, response_status="completed")
    assert result["valid"] and result["changed"] and not result["derived_errors"]
    assert len(result["raw_errors"]) == 4 and len(result["transformations"]) == 4
    assert result["transformations"][0] == {"path": "event.action.refs", "old_refs": ["p2", "p1"],
                                            "new_refs": ["p1"], "removed_refs": ["p2"]}
    assert output == original and packet == original_packet
    restored = deepcopy(result["derived_output"])
    for change in result["transformations"]:
        target = restored
        parts = change["path"].split(".")
        for key in parts[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        target[parts[-1]] = change["old_refs"]
    assert restored == original  # Every other field is byte-value identical.


def test_zero_grounding_is_not_repaired_by_searching_elsewhere() -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p2"]  # Exact surface exists only in uncited p1.
    result = project_literal_refs(output, packet, response_status="completed")
    assert not result["valid"] and not result["changed"]
    assert "event.action:surface_not_grounded" in result["derived_errors"]
    assert result["derived_output"] == output


def test_missing_attribution_stays_invalid_after_unrelated_literal_projection() -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p2"]
    output["event"]["facts"][0]["attributed_to"] = "e2"
    result = project_literal_refs(output, packet, response_status="completed")
    assert result["changed"] and not result["valid"]
    assert "event.facts.0:attribution_missing_claim_source_role" in result["derived_errors"]
    assert result["derived_output"]["event"]["facts"][0] == output["event"]["facts"][0]


@pytest.mark.parametrize("refs,error", [(["p1", "p999"], "event.action.refs:unknown_reference"),
                                       (["p1", "p3"], "event.action.refs:excluded_evidence")])
def test_unknown_and_excluded_references_are_never_trimmed(refs: list[str], error: str) -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = refs
    result = project_literal_refs(output, packet, response_status="completed")
    assert not result["valid"] and not result["changed"]
    assert error in result["derived_errors"] and result["derived_output"] == output


@pytest.mark.parametrize("status,truncated", [(None, False), ("incomplete", False), ("completed", True)])
def test_incomplete_response_prohibits_projection(status: str | None, truncated: bool) -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p2"]
    result = project_literal_refs(output, packet, response_status=status, response_truncated=truncated)
    assert not result["transformation_permitted"] and not result["valid"] and not result["changed"]
    assert result["derived_output"] == output and result["derived_errors"] == ["response:not_completed"]


@pytest.mark.parametrize("kind", ["packet", "schema"])
def test_invalid_packet_or_schema_prohibits_all_projection(kind: str) -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p2"]
    if kind == "packet":
        packet["model_input"]["coverage"]["truncated"] = True
    else:
        output["extra"] = "unsupported"
    result = project_literal_refs(output, packet, response_status="completed")
    assert not result["transformation_permitted"] and not result["valid"]
    assert result["derived_output"] == output and not result["transformations"]


def test_case_whitespace_and_literal_text_never_normalized() -> None:
    packet, output = contract.fictional_example()
    output["event"]["participants"][0]["surface"] = "lumen council"
    result = project_literal_refs(output, packet, response_status="completed")
    assert not result["valid"] and not result["changed"]
    assert result["derived_output"]["event"]["participants"][0]["surface"] == "lumen council"


def test_valid_output_and_nonsingle_output_are_identity_projections() -> None:
    packet, output = contract.fictional_example()
    for single in (True, False):
        candidate = deepcopy(output)
        if not single:
            candidate.update(focus="none", reason="no_particular_occurrence", event=None)
        result = project_literal_refs(candidate, packet, response_status="completed")
        assert result["valid"] and not result["changed"] and result["derived_output"] == candidate
        assert result["derived_output"] is not candidate


def test_role_support_and_event_refs_not_modified_or_inferred() -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p2"]
    output["event"]["participants"][1]["roles"][0]["refs"] = ["p1", "p2"]
    output["event"]["facts"][0]["support_refs"] = ["p1", "p2"]
    output["event"]["status_refs"] = ["p1", "p2"]
    result = project_literal_refs(output, packet, response_status="completed")
    derived = result["derived_output"]
    assert result["valid"] and len(result["transformations"]) == 1
    assert derived["refs"] == output["refs"] and derived["excluded"] == output["excluded"]
    assert derived["event"]["status_refs"] == ["p1", "p2"]
    assert derived["event"]["participants"][1]["roles"] == output["event"]["participants"][1]["roles"]
    assert derived["event"]["facts"][0]["support_refs"] == ["p1", "p2"]


def test_matching_duplicate_ref_is_preserved_and_stays_invalid() -> None:
    packet, output = contract.fictional_example()
    output["event"]["action"]["refs"] = ["p1", "p1", "p2"]
    result = project_literal_refs(output, packet, response_status="completed")
    assert result["changed"] and not result["valid"]
    assert result["derived_output"]["event"]["action"]["refs"] == ["p1", "p1"]
    assert "event.action.refs:duplicate_reference" in result["derived_errors"]
