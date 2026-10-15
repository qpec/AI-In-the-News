"""Synthetic child-adapter checks; never real corpus inspection or inference."""
from __future__ import annotations

from contextlib import contextmanager
import copy
from typing import Any

import numpy as np
import pytest

from newsresearch import event_pair_feature_study as child
from newsresearch.common import AuditError, ResearchError, digest
from test_event_pair_experiment import planned as _planned, run, fake_provider

planned = _planned


@pytest.fixture
def parent(planned: Any, monkeypatch: Any) -> Any:
    engine, plan = planned
    seen = fake_provider(monkeypatch)
    result = run(planned)
    plan.update(selected_articles=8, processed_articles=8, missing_articles=0)
    passages = []
    mapping = []
    for n, row in enumerate(engine.ledger.db.execute("SELECT id,source_id FROM passages ORDER BY source_id,id")):
        passages.append({"id": f"chunk-{n}", "source_version": row["source_id"], "passage_id": row["id"]})
        mapping.append({"source_version": row["source_id"], "chunks": [{"row": n, "chunk": f"chunk-{n}", "passage": row["id"]}]})
    def setup(session: str, context: Any, data: Any) -> Any:
        artifact = engine.ledger.artifacts.put(mapping)
        engine.ledger.append(session, "preparation.artifact.saved", {"artifact": artifact, "purpose": "Synthetic vector mapping"})
        plan["mapping_artifact"] = artifact
        plan["index"] = engine.ledger.record(session, "vector_index", "synthetic-child-index", {"versions": plan["versions"]})
        return {"synthetic": True}
    old = engine._status
    monkeypatch.setattr(engine, "_status", setup)
    engine.execute("status", objective="Prepare synthetic child feature mapping", actor="test:software")
    monkeypatch.setattr(engine, "_status", old)
    loaded = child.original.load_plan(engine, "unused", result["plan"])
    monkeypatch.setattr(child, "load_plan", lambda *args: loaded)
    @contextmanager
    def vectors(*args: Any) -> Any:
        # Each article has one normalized saved fixture vector.
        yield passages, np.tile(np.array([[1., 0., 0.]], dtype=np.float32), (len(passages), 1))
    monkeypatch.setattr(child, "vectors", vectors)
    return engine, plan, result, seen, loaded


def execute(parent: Any, **extra: Any) -> Any:
    engine, plan, result, _, _ = parent
    return engine.execute("event_pair_feature_experiment", {"parent_result": result["id"],
        "experiment_key": "synthetic-feature-child", "reuse_cache": True,
        "continuation_instruction": "Synthetic continuation fixture within the existing budget", **extra},
        versions=plan["versions"], objective="Verify child reference reuse and sealed validation", actor="test:software")


def append(parent: Any, monkeypatch: Any, kind: str, key: str, value: Any) -> str:
    engine = parent[0]
    old = engine._status
    monkeypatch.setattr(engine, "_status", lambda session, context, data: {
        "id": engine.ledger.record(session, kind, key, value)})
    try:
        return str(engine.execute("status", objective="Construct immutable synthetic test branch", actor="test:software")["id"])
    finally:
        monkeypatch.setattr(engine, "_status", old)


def test_offline_child_reuses_every_reference_and_spends_no_new_attempt(parent: Any) -> None:
    engine, _, original, seen, _ = parent
    count = len(seen)
    result = execute(parent)
    assert len(seen) == count == original["pair_attempts"]
    assert result["new_pair_attempts"] == 0 and result["pair_attempts"] == count
    assert result["development_counts"]["uncertain"] == count
    assert all(result["development_counts"][key] == 0 for key in
               ("same_event", "different_event", "failed", "invalid", "pending", "unknown"))
    assert len(result["variant_summaries"]) == 20
    assert result["candidate"] is None and result["validation_pairs"] == 0
    assert result["original_judge_versions"] == original["versions"]
    assert result["versions"] != original["versions"]
    assert result["new_embedding_requests"] == result["accepted_dossiers"] == result["applied_tags"] == 0
    assert result["presentation"]["markdown"] == child.render(result)
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["missing", "extra", "failed", "label"])
def test_reference_dropping_extra_labels_and_incomplete_judgments_block(parent: Any, monkeypatch: Any, change: str) -> None:
    value = copy.deepcopy(parent[2])
    judged = value["development_judgements"]
    first = next(iter(judged))
    if change == "missing":
        judged.pop(first)
    elif change == "extra":
        judged["not-in-development"] = copy.deepcopy(judged[first])
    elif change == "failed":
        judged[first]["status"] = "failed"
    else:
        judged[first]["label"] = "same_event"
    identifier = append(parent, monkeypatch, "event_pair_experiment", "synthetic-corrupt-parent", value)
    with pytest.raises((ResearchError, AuditError)):
        execute(parent, parent_result=identifier)
    assert len(parent[3]) == parent[2]["pair_attempts"]


def test_original_implementation_hash_change_blocks_before_features(parent: Any, monkeypatch: Any) -> None:
    old = child._hashes
    monkeypatch.setattr(child, "_hashes", lambda names: {**old(names), "event_pair_experiment.py": "changed"})
    called = []
    monkeypatch.setattr(child, "_compute", lambda *args: called.append(True))
    with pytest.raises(ResearchError, match="implementation changed"):
        execute(parent)
    assert called == []


def test_shared_holdout_registry_prevents_child_reopening(parent: Any, monkeypatch: Any) -> None:
    append(parent, monkeypatch, "event_pair_holdout_opened", parent[1]["study_key"], {
        "frozen_candidate": "another-candidate", "child_manifest": "another-child"})
    with pytest.raises(ResearchError, match="Shared holdout already opened"):
        execute(parent)
    assert len(parent[3]) == parent[2]["pair_attempts"]


def test_child_selection_method_is_immutable_under_changed_experiment_key(parent: Any) -> None:
    execute(parent)
    with pytest.raises(ResearchError, match="One immutable child"):
        execute(parent, experiment_key="fresh-key-cannot-reset-study")


def test_validation_sampling_is_fold_bound_weighted_and_label_blind() -> None:
    candidate = {"feature": "max_passage_cosine", "threshold": .9, "publication_gap_days": 7}
    rows = [{"pair_id": f"pair-{n:03}", "left": f"left-{n}", "right": f"right-{n}", "fold": "validation",
        "features": {"max_passage_cosine": .95 if n < 40 else .7}, "publication_gap_days": 2} for n in range(60)]
    first = child.validation_sample(rows, digest(rows), candidate, "fixed-seed")
    second = child.validation_sample(rows, digest(rows), candidate, "fixed-seed")
    assert first == second and len(first["rows"]) == 36
    assert [value["n"] for value in first["strata"]] == [30, 6]
    assert [value["inclusion_probability"] for value in first["strata"]] == [.75, .3]
    for row in first["rows"]:
        assert row["weight"] == pytest.approx(1 / row["inclusion_probability"])
    rows[0]["fold"] = "development"
    with pytest.raises(ResearchError, match="validation fold"):
        child.validation_sample(rows, "frame", candidate, "fixed-seed")


def test_missing_publication_date_routes_to_review_not_different_event() -> None:
    row = {"features": {"first_passage_cosine": .99}, "publication_gap_days": None}
    gated = {"feature": "first_passage_cosine", "threshold": .9, "publication_gap_days": 7}
    assert child.predicts(row, gated) is False
    assert child.predicts(row, {**gated, "publication_gap_days": None}) is True


def test_required_audit_failure_stops_before_feature_processing(parent: Any, monkeypatch: Any) -> None:
    called = []
    monkeypatch.setattr(child, "_compute", lambda *args: called.append(True))
    parent[0].ledger.fail_event = "model.cache_reused"
    with pytest.raises(AuditError, match="Injected audit failure"):
        execute(parent)
    assert called == []


def test_removing_required_feature_artifact_fails_complete_preflight(parent: Any) -> None:
    result = execute(parent)
    engine = parent[0]
    (engine.ledger.artifacts.root / result["development_features"]).unlink()
    with pytest.raises(AuditError):
        engine.execute("status", objective="Detect deleted synthetic feature artifact", actor="test:software")


def test_numeric_failure_is_retained_as_null_not_negative(parent: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(child.features, "pair_features", lambda *args: (_ for _ in ()).throw(ResearchError("fixture numeric failure")))
    result = execute(parent)
    rows = parent[0].ledger.artifacts.read(result["development_features"])
    assert all(row["status"] == "failed" and row["failure_reason"] == "fixture numeric failure" for row in rows)
    assert result["candidate"] is None and result["development_counts"]["uncertain"] == len(rows)
    assert result["new_pair_attempts"] == 0 and result["status"] == "partial"


def force_candidate(monkeypatch: Any) -> None:
    original = child.selection.evaluate
    def evaluate(*args: Any, **kwargs: Any) -> Any:
        metrics = original(*args, **kwargs)
        # Deliberately force a candidate to exercise transport/sealing branches;
        # this synthetic fixture does not assert statistical qualification.
        first = metrics["full_grid"][0]["metrics"]
        metrics["best_candidate"] = {"feature": "max_passage_cosine", "threshold": .9,
                                     "publication_gap_days": None, "metrics": first}
        return metrics
    monkeypatch.setattr(child.selection, "evaluate", evaluate)


def test_small_holdout_is_not_judged_when_support_is_impossible(parent: Any, monkeypatch: Any) -> None:
    force_candidate(monkeypatch)
    result = execute(parent, execute_validation=True)
    assert result["validation_pairs"] == result["new_pair_attempts"] == 0
    assert result["holdout_obstacle"].startswith("insufficient_available")
    assert parent[0].ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_holdout_opened'").fetchone()[0] == 0


def test_child_freezes_then_uses_original_judge_versions_and_exact_resume(parent: Any, monkeypatch: Any) -> None:
    force_candidate(monkeypatch)
    policy = copy.deepcopy(child.selection.POLICY)
    policy["validation"]["minimum_selected_pairs"] = 1  # software branch fixture only
    monkeypatch.setattr(child.selection, "POLICY", policy)
    original_count = len(parent[3])
    result = execute(parent, execute_validation=True)
    engine = parent[0]
    assert result["validation_pairs"] == result["new_pair_attempts"] == 6
    assert len(parent[3]) == original_count + 6
    for invocation in parent[3][original_count:]:
        assert invocation.request["versions"] == parent[2]["versions"]
        assert "features" not in str(invocation.request)
    candidate_seq = engine.ledger.db.execute("SELECT created_event FROM records WHERE id=?", (result["frozen_candidate"],)).fetchone()[0]
    opened_seq = engine.ledger.db.execute("SELECT created_event FROM records WHERE kind='event_pair_holdout_opened'").fetchone()[0]
    assert candidate_seq < opened_seq
    for row in engine.ledger.db.execute("SELECT seq,payload FROM events WHERE kind='model.attempt.intended' AND seq>?", (opened_seq,)):
        assert row["seq"] > opened_seq
    again = execute(parent, execute_validation=True)
    assert again["new_pair_attempts"] == 0 and again["frozen_candidate"] == result["frozen_candidate"]
    assert len(parent[3]) == original_count + 6
    with pytest.raises(ResearchError, match="Shared holdout opened by child"):
        run((engine, parent[1]))
