"""Source-free final-family amendment and immutable-freeze integration tests."""
from __future__ import annotations

from typing import Any

import pytest

from newsresearch import event_pair_monotone_study as study
from newsresearch.common import AuditError, ResearchError
from test_event_pair_conjunction_study import amended as _amended, feature_parent as _feature_parent, planned as _planned
from test_event_pair_conjunction_study import execute as conjunction_execute
from test_event_pair_feature_study import append

planned = _planned
feature_parent = _feature_parent
amended = _amended


@pytest.fixture
def final_parent(amended: Any, monkeypatch: Any) -> Any:
    failed = conjunction_execute(amended)
    monkeypatch.setattr(study, "load_plan", lambda *args: amended[0][-1])
    return amended, failed


def execute(final_parent: Any, **extra: Any) -> Any:
    amended, failed = final_parent
    parent = amended[0]
    return parent[0].execute("event_pair_monotone_screen", {
        "parent_conjunction_result": failed["id"], "experiment_key": "synthetic-final-family",
        "continuation_instruction": "Synthetic final bounded continuation", "reuse_cache": True, **extra},
        versions=parent[1]["versions"], objective="Verify final family screen using source-free fixtures", actor="test:software")


def test_final_offline_screen_keeps_uncertain_and_reports_insufficient_support(final_parent: Any) -> None:
    result = execute(final_parent)
    assert result["development_pairs"] == result["development_counts"]["uncertain"] == 6
    assert result["search_status"] == "insufficient_positive_support"
    assert result["candidate"] is None and result["validation_pairs"] == 0
    assert result["new_pair_attempts"] == result["new_embedding_requests"] == result["accepted_dossiers"] == result["applied_tags"] == 0
    assert result["pair_attempts"] == final_parent[0][0][2]["pair_attempts"]
    assert result["presentation"]["markdown"] == study.render(result)
    assert "Processing or positive support is insufficient" in result["presentation"]["markdown"]


@pytest.mark.parametrize("kind", ["event_pair_candidate", "event_pair_feature_candidate", "event_pair_conjunction_candidate"])
def test_any_prior_candidate_blocks_final_search(final_parent: Any, monkeypatch: Any, kind: str) -> None:
    parent = final_parent[0][0]
    append(parent, monkeypatch, kind, parent[1]["study_key"], {"synthetic": True})
    with pytest.raises(ResearchError, match="earlier candidate"):
        execute(final_parent)


def test_opened_holdout_blocks_further_final_development(final_parent: Any, monkeypatch: Any) -> None:
    parent = final_parent[0][0]
    append(parent, monkeypatch, "event_pair_holdout_opened", parent[1]["study_key"], {"synthetic": True})
    with pytest.raises(ResearchError, match="already opened"):
        execute(final_parent)


def test_final_method_cannot_reset_under_new_key(final_parent: Any) -> None:
    first = execute(final_parent)
    assert execute(final_parent)["development_metrics"] == first["development_metrics"]
    with pytest.raises(ResearchError, match="immutable"):
        execute(final_parent, experiment_key="new-key-cannot-reset")


def test_no_silent_model_launch_flag(final_parent: Any) -> None:
    with pytest.raises(ResearchError, match="offline only"):
        execute(final_parent, execute_validation=True)


def test_audit_failure_prevents_final_parameter_search(final_parent: Any, monkeypatch: Any) -> None:
    called = []
    monkeypatch.setattr(study.rules, "evaluate", lambda *args: called.append(True))
    final_parent[0][0][0].ledger.fail_event = "model.cache_reused"
    with pytest.raises(AuditError):
        execute(final_parent)
    assert called == []


def test_frozen_final_candidate_resume_never_reselects(final_parent: Any, monkeypatch: Any) -> None:
    original = study.rules.evaluate
    def forced(rows: Any, judgments: Any) -> Any:
        result = original(rows, judgments)
        prepared, errors = study.rules.selection._prepare(rows, judgments, "development", study.rules.selection.FEATURES)
        metrics = study.rules._masked_metrics(prepared, (1 << len(prepared)) - 1, "development", errors, True)
        # Exercise freeze mechanics only, not scientific qualification.
        result["best_candidate"] = {"features": list(study.rules.selection.FEATURES), "thresholds": [.1] * 5,
            "publication_gap_days": None, "metrics": metrics}
        return result
    monkeypatch.setattr(study.rules, "evaluate", forced)
    first = execute(final_parent)
    monkeypatch.setattr(study.rules, "evaluate", lambda *args: pytest.fail("Frozen candidate was retuned"))
    second = execute(final_parent)
    assert first["frozen_candidate"] == second["frozen_candidate"]
    assert second["status"] == "candidate_unvalidated" and second["new_pair_attempts"] == 0


def test_required_full_grid_is_checked_on_next_preflight(final_parent: Any) -> None:
    result = execute(final_parent)
    engine = final_parent[0][0][0]
    (engine.ledger.artifacts.root / result["development_metrics"]).unlink()
    with pytest.raises(AuditError):
        engine.execute("status", objective="Detect deleted synthetic final grid", actor="test:software")


def test_close_failed_development_rule_can_only_be_an_explicit_unvalidated_probe() -> None:
    rows = []
    judgments = {}
    # Eight strong same references, six weaker same references, one dominant
    # uncertain reference and six medium nonmatches: best supported precision
    # is8/9. This is a constructed numerical fixture, not a corpus claim.
    for n in range(21):
        value = .8 if n < 8 else .4 if n < 14 else .9 if n == 14 else .5
        identifier = f"pair-{n:02}"
        rows.append({"pair_id": identifier, "left": f"left-{n}", "right": f"right-{n}", "fold": "development",
            "inclusion_probability": 1., "publication_gap_days": 0,
            "features": {name: value for name in study.rules.selection.FEATURES}})
        judgments[identifier] = {"status": "completed", "label": "same_event" if n < 14 else "uncertain" if n == 14 else "different_event"}
    metrics = study.rules.evaluate(rows, judgments)
    assert metrics["best_candidate"] is None and metrics["status"] == "no_eligible_rule"
    candidate, basis = study.select_hypothesis(metrics)
    assert basis == "exploratory_below_development_target" and candidate is not None
    assert candidate["metrics"]["precision_pessimistic_observed"] == pytest.approx(8 / 9)
    assert candidate["metrics"]["eligible"] is False
