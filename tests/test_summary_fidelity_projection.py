"""Compact saved-reason projections retain bindings without source passages."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import inspect_summary_fidelity_results as view  # noqa: E402
import inspect_summary_fidelity_v3 as census  # noqa: E402


def test_projection_allowlists_claim_hashes_and_source_locations():
    row = {"selection": {"stratum": "weak", "summary_version": "summary-version",
            "summary_record": "summary-record", "grounding_probabilities": {"supported": .84}},
        "outcome": "unsupported", "response_record": "response-record", "validation_error": None,
        "parsed": {"reason": "The claimed actor is attributed to a different event.",
            "claim_paths": ["/overview"],
            "affected_claims": [{"path": "/overview", "value_sha256": "claim-hash",
                "value": {"text": "PRIVATE CLAIM VALUE"}, "future_text_field": "PRIVATE FUTURE FIELD"}],
            "selected_passage_locations": [{"document_id": "source-one", "field": "body",
                "start": 20, "end": 40, "text_sha256": "source-hash", "quote": "PRIVATE SOURCE PASSAGE"}],
            "citations": [{"quote": "PRIVATE CITATION"}]}}
    actual = view.project([row])[0]
    assert actual["model_reason"] == row["parsed"]["reason"]
    assert actual["claim_paths"] == ["/overview"]
    assert actual["affected_claim_hashes"] == [{"path": "/overview", "value_sha256": "claim-hash"}]
    assert actual["source_locations"] == [{"document_id": "source-one", "field": "body",
                                          "start": 20, "end": 40, "text_sha256": "source-hash"}]
    assert "PRIVATE" not in json.dumps(actual)


def test_projection_preserves_unresolved_cases_and_explicit_reason_truncation():
    common = {"selection": {"stratum": "control", "summary_version": "v", "summary_record": "r"},
              "response_record": None, "validation_error": "synthetic-invalid"}
    cases = view.project([{**common, "outcome": "unknown_hold", "parsed": None},
                          {**common, "outcome": "uncertain", "parsed": {"reason": "x" * 2001}}])
    assert cases[0]["outcome"] == "unknown_hold" and cases[0]["model_reason"] is None
    assert cases[0]["claim_paths"] == [] and cases[0]["source_locations"] == []
    assert len(cases[1]["model_reason"]) == 2000 and cases[1]["model_reason_truncated"]


def test_fixed_selection_keeps_all_six_weak_and_same_six_controls():
    rows = [{"dossier_id": f"dossier-{i}", "summary_version": f"version-{i}"} for i in range(17)]
    usable = {r["dossier_id"] for r in rows[6:]}
    selected = census.select(rows, usable)
    assert selected == census.select(list(reversed(rows)), usable)
    assert len(selected) == len({r["summary_version"] for r in selected}) == 12
    assert {r["dossier_id"] for r in selected if r["stratum"] == "weak"} == {r["dossier_id"] for r in rows[:6]}
    assert sum(r["stratum"] == "usable_control" for r in selected) == 6
