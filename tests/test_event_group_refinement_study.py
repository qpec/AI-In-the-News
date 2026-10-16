"""One integrated synthetic comparison, audit-failure and resume scenario."""
from dataclasses import replace
from typing import Any

import pytest

from newsresearch import event_group_refinement_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_refinement_freezes_before_references_preserves_unknowns_and_resumes(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    a, b, c, d = ids[:4]
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}

    def edge(left: str, right: str, value: float, weak: float | None = None) -> Any:
        features = dict.fromkeys(FEATURES, value)
        if weak is not None:
            features["first_passage_cosine"] = weak
        return {"left": left, "right": right, "pair_id": digest(sorted((left, right))), "status": "completed",
                "features": features, "publication_gap_days": 0}

    edges = [edge(a, b, .99, .51), edge(b, c, .9), edge(b, d, .9), edge(c, d, .9)]
    baseline = study.baseline_algorithm.complete_link_groups(ids[:5], edges)
    owners = study._owners(baseline["groups"])
    articles = [{**metadata[source], "group_id": owners.get(source), "same_event_answer": None, "accepted": False,
        "status": "provisional" if source in ids[:4] else "review_singleton" if source == ids[4] else "missing_publication_date" if source == ids[7] else "missing_vectors",
        "processing_status": "complete" if source in owners else "unprocessed", "bridge_count": 0} for source in ids]

    def setup(session: str, context: Any, data: Any) -> Any:
        def save(value: Any) -> str:
            return study.base._save(engine, session, value, "Constructed software fixture")
        manifest = engine.ledger.record(session, "event_rule_application_manifest", "fixture", {
            "versions": plan["versions"], "method": {"rule": rule, "plan": plan["id"], "parent": "synthetic-original", "implementation": study.base._hashes(study.previous.CODE)}})
        payload = {"versions": plan["versions"], "manifest": manifest, "status": "completed_provisional_application",
            "plan": plan["id"], "parent_result": "synthetic-original", "rule": rule, "validation_status": "failed_development_unvalidated",
            "development_metrics": {}, "dataset_articles": 8, "vector_articles": 6, "date_eligible_articles": 5,
            "missing_vector_articles": 2, "missing_date_articles": 1, "failed_feature_pairs": 0, "pending_pairs": 0,
            "accepted_dossiers": 0, "pooled_candidates": 4, "proposed_link_pairs": 4, "score_artifact": save(edges),
            "exports": {"articles": {"artifact": save(articles)}, "groups": {"artifact": save(baseline["groups"])}}}
        return engine.ledger.record(session, "event_rule_application_result", "fixture", payload)

    monkeypatch.setattr(engine, "_status", setup)
    parent_id = engine.execute("status", objective="Prepare constructed refinement fixture", actor="test:software")
    rows = [{**row, "fold": "development", "inclusion_probability": 1. / (n + 1), "weight": float(n + 1)}
            for n, row in enumerate((edges[1], edges[0], edges[3]))]
    labels = {row["pair_id"]: {"status": "completed", "label": label}
              for row, label in zip(rows, ("same_event", "different_event", "uncertain"), strict=True)}
    monkeypatch.setattr(study, "load_plan", lambda *args: (plan, {}, {"rows": rows}))
    calls = []

    def references(*args: Any) -> Any:
        frozen = study._records(engine, "event_group_refinement_candidate", "synthetic-refinement")
        assert len(frozen) == 1 and frozen[0][1]["frozen_before_reference_check"]
        calls.append(True)
        return labels, plan["versions"], "synthetic-model-reference"

    monkeypatch.setattr(study, "_references", references)
    data = {"parent_result": parent_id, "comparison_key": "synthetic-refinement", "user_instruction": "Constructed test only",
            "output_directory": str(engine.ledger.root / "output")}

    def run(**extra: Any) -> Any:
        return engine.execute("refine_event_groups", {**data, **extra}, objective="Verify constructed group refinement", actor="test:software")

    engine.ledger.fail_event = "event_groups.refinement.intended"
    with pytest.raises(AuditError):
        run()
    assert not calls
    engine.ledger.fail_event = None
    result = run()
    assert result["adopted"] and result["diagnostics"]["objective_gain"] > 0
    assert result["baseline"]["grouped_articles"] == 4 and result["candidate"]["grouped_articles"] == 3
    assert result["reference_summary"]["same_event"]["candidate"]["together"] == 1
    assert result["reference_summary"]["different_event"]["candidate"]["together"] == 0
    assert result["reference_summary"]["uncertain"]["candidate"]["weighted_together"] == 3.
    assert result["accepted_dossiers"] == result["new_model_calls"] == result["new_embedding_requests"] == 0
    updated = engine.ledger.artifacts.read(result["exports"]["articles"]["artifact"])
    assert len(updated) == 8 and sum(row["status"] == "missing_vectors" for row in updated) == 2
    assert sum(row["status"] == "missing_publication_date" for row in updated) == 1
    assert all(not row["accepted"] and row["same_event_answer"] is None for row in updated)
    assert result["presentation"]["markdown"] == study.render(result)
    monkeypatch.setattr(study.algorithm, "refine", lambda *args: pytest.fail("Completed refinement was recomputed"))
    assert run()["id"] == result["id"] and len(calls) == 1
    with pytest.raises(ResearchError, match="immutable"):
        run(user_instruction="A changed instruction needs a new version")
    reversed_labels = {key: {**value, "label": "different_event" if value["label"] == "same_event" else "same_event" if value["label"] == "different_event" else "uncertain"} for key, value in labels.items()}
    candidate = engine.ledger.artifacts.read(result["exports"]["candidate_groups"]["artifact"])
    regressed = study.compare(rows, reversed_labels, baseline["groups"], candidate, set())
    assert len(regressed["regressions"]) == 2
    # Veto the regressing component, while preserving an unrelated improvement.
    extended_before = baseline["groups"] + [{"group_id": "x", "members": ["x"]}, {"group_id": "y", "members": ["y"]}]
    extended_after = candidate + [{"group_id": "xy", "members": ["x", "y"]}]
    guarded, blocked = study.guarded_partition(ids[:5] + ["x", "y"], edges + [edge("x", "y", .9)], extended_before, extended_after, regressed)
    assert len(blocked) == 1 and blocked[0]["regression_pair_ids"] and study._owners(guarded)["x"] == study._owners(guarded)["y"]
    assert study.compare(rows, reversed_labels, baseline["groups"], guarded, set())["regressions"] == []
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"
