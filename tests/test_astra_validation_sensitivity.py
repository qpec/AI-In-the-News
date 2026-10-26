from copy import deepcopy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "workbench"))
from report_astra_validation_sensitivity import route_sensitivity  # noqa: E402


def test_sensitivity_preserves_original_and_review_missingness():
    cases = [
        {"stratum": "keep", "reference": {"route": "keep", "boundary_ambiguous": True}},
        {"stratum": "keep", "reference": {"route": "review", "boundary_ambiguous": True}},
        {"stratum": "exclude", "reference": {"route": "exclude", "boundary_ambiguous": True}},
        {"stratum": "exclude", "reference": None},
    ]
    before = deepcopy(cases)
    result = route_sensitivity(cases, {"keep": 100, "exclude": 1000})
    assert cases == before
    assert result["confusion_against_astra_clear_references"] == {
        "TP": 1, "FP": 0, "unresolved_keep": 1, "FN": 0, "TN": 1, "unresolved_exclude": 1}
