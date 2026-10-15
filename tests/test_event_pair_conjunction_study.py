"""Source-free amendment, shared-holdout and exact-resume integration tests."""
from __future__ import annotations

import copy
from typing import Any

import pytest

from newsresearch import event_pair_conjunction_study as study
from newsresearch.common import AuditError, ResearchError
from test_event_pair_feature_study import parent as feature_parent, planned, execute as feature_execute, append

planned = planned
feature_parent = feature_parent


@pytest.fixture
def amended(feature_parent: Any, monkeypatch: Any) -> Any:
    failed = feature_execute(feature_parent)
    monkeypatch.setattr(study, "load_plan", lambda *args: feature_parent[-1])
    monkeypatch.setattr(study, "vectors", study.base.vectors)
    return feature_parent, failed


def execute(amended: Any, **extra: Any) -> Any:
    parent, failed = amended
    return parent[0].execute("event_pair_conjunction_experiment", {
        "parent_feature_result": failed["id"], "experiment_key": "synthetic-conjunction-amendment",
        "reuse_cache": True, "continuation_instruction": "Synthetic bounded continuation", **extra},
        versions=parent[1]["versions"], objective="Verify source-free conjunction amendment", actor="test:software")


def test_finite_offline_amendment_keeps_refs_budget_and_exact_presentation(amended: Any) -> None:
    parent, failed = amended
    result = execute(amended)
    assert result["parent_feature_result"] == failed["id"]
    assert result["development_counts"]["uncertain"] == result["development_pairs"] == 6
    assert len(result["variant_summaries"]) == 40 and result["parameter_combinations"] > 40
    assert result["new_pair_attempts"] == 0 and result["pair_attempts"] == parent[2]["pair_attempts"]
    assert result["validation_pairs"] == 0 and result["candidate"] is None
    assert result["presentation"]["markdown"] == study.render(result)
    assert result["new_embedding_requests"] == result["accepted_dossiers"] == result["applied_tags"] == 0
    again = execute(amended)
    assert again["development_metrics"] == result["development_metrics"]
    assert again["new_pair_attempts"] == 0


def test_existing_frozen_older_candidate_prevents_amendment(amended: Any, monkeypatch: Any) -> None:
    parent, _ = amended
    append(parent, monkeypatch, "event_pair_feature_candidate", parent[1]["study_key"], {"synthetic": True})
    with pytest.raises(ResearchError, match="older candidate"):
        execute(amended)


def test_opened_shared_holdout_prevents_initial_amendment(amended: Any, monkeypatch: Any) -> None:
    parent, _ = amended
    append(parent, monkeypatch, "event_pair_holdout_opened", parent[1]["study_key"], {"synthetic": True})
    with pytest.raises(ResearchError, match="sealed shared holdout"):
        execute(amended)


def test_completed_candidate_is_not_a_failed_parent(amended: Any, monkeypatch: Any) -> None:
    parent, failed = amended
    changed = {**failed, "candidate": {"synthetic": True}}
    identifier = append(parent, monkeypatch, "event_pair_feature_experiment", "synthetic-not-failed", changed)
    with pytest.raises(ResearchError, match="completed failed"):
        execute(amended, parent_feature_result=identifier)


def test_key_change_cannot_reset_amendment(amended: Any) -> None:
    execute(amended)
    with pytest.raises(ResearchError, match="immutable"):
        execute(amended, experiment_key="fresh-key-not-allowed")


def test_audit_failure_prevents_parameter_search(amended: Any, monkeypatch: Any) -> None:
    calls = []
    monkeypatch.setattr(study.rules, "evaluate", lambda *args: calls.append(True))
    amended[0][0].ledger.fail_event = "model.cache_reused"
    with pytest.raises(AuditError):
        execute(amended)
    assert calls == []


def test_changed_sampling_weight_reuse_is_rejected(amended: Any, monkeypatch: Any) -> None:
    engine = amended[0][0]
    artifact = amended[1]["development_features"]
    original = engine.ledger.artifacts.read
    def read(identifier: str) -> Any:
        value = original(identifier)
        if identifier == artifact:
            value = copy.deepcopy(value)
            value[0]["inclusion_probability"] = .01
        return value
    monkeypatch.setattr(engine.ledger.artifacts, "read", read)
    with pytest.raises(AuditError, match="sampling probabilities"):
        execute(amended)


def test_required_grid_artifact_cannot_disappear(amended: Any) -> None:
    result = execute(amended)
    engine = amended[0][0]
    (engine.ledger.artifacts.root / result["development_metrics"]).unlink()
    with pytest.raises(AuditError):
        engine.execute("status", objective="Verify synthetic mandatory grid artifact", actor="test:software")


def test_frozen_conjunction_seals_before_original_judging_and_resumes_exactly(amended: Any, monkeypatch: Any) -> None:
    original = study.rules.evaluate
    def forced(*args: Any) -> Any:
        result = original(*args)
        metrics = next(iter(result["metrics_map"].values()))
        # Force the branch only; this is not an eligibility or research result.
        result["best_candidate"] = {"features": ["pooled_cosine", "first_passage_cosine"],
            "thresholds": [.5, .9], "publication_gap_days": None, "metrics": metrics}
        return result
    monkeypatch.setattr(study.rules, "evaluate", forced)
    policy = copy.deepcopy(study.selection.POLICY)
    policy["validation"]["minimum_selected_pairs"] = 1
    monkeypatch.setattr(study.selection, "POLICY", policy)
    parent = amended[0]
    before = len(parent[3])
    result = execute(amended, execute_validation=True)
    assert result["new_pair_attempts"] == result["validation_pairs"] == 6
    assert all(call.request["versions"] == parent[2]["versions"] for call in parent[3][before:])
    engine = parent[0]
    frozen_seq = engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (result["frozen_candidate"],)).fetchone()[0]
    opened_seq = engine.ledger.db.execute("SELECT created_event FROM records WHERE kind='event_pair_holdout_opened'").fetchone()[0]
    assert frozen_seq < opened_seq
    again = execute(amended, execute_validation=True)
    assert again["new_pair_attempts"] == 0 and again["frozen_candidate"] == result["frozen_candidate"]
    assert len(parent[3]) == before + 6
