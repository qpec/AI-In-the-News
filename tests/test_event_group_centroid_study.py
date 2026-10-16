"""Constructed runtime centroid scenario; no corpus or model operations."""
from dataclasses import replace
from itertools import combinations
from typing import Any

import numpy as np
import pytest

from newsresearch import event_group_centroid_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_centroid_variants_freeze_before_labels_sql_coverage_and_resume(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    a, b, c, d, e = ids[:5]
    for n, source in enumerate(ids):
        metadata[source]["published_at"] = "2026-01-01" if n < 2 else "2026-01-20" if n == 2 else "2026-01-21"
        metadata[source]["url"] = f"https://fixture{n}.example/article"
    groups = [{"group_id": "A", "members": [a, b]}, {"group_id": "B", "members": [c]},
              {"group_id": "C", "members": [d, e]}]
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}
    scored = [{"pair_id": digest([left, right]), "left": left, "right": right,
               "status": "completed", "features": dict.fromkeys(FEATURES, .99)}
              for left, right in combinations(ids[:5], 2)]
    rows = [{"pair_id": digest(sorted(pair)), "left": min(pair), "right": max(pair),
             "weight": float(n + 1), "inclusion_probability": 1. / (n + 1)}
            for n, pair in enumerate(((a, b), (a, c), (ids[6], ids[7])))]
    judged = {row["pair_id"]: {"status": "completed", "label": label} for row, label in zip(
        rows, ("same_event", "different_event", "uncertain"), strict=True)}
    parent = {"versions": plan["versions"], "proposals": [{"candidate_id": "prior-AB",
        "old_group_ids": ["A", "B"], "review_status": "conflicting_model_references"}]}
    inputs = {"groups": groups, "scored": scored, "metadata": metadata,
        "pooled": np.tile(np.array([[1., 0.]], dtype=np.float32), (len(ids), 1)), "article_ids": ids,
        "allowed": set(ids), "current": {"rule": rule},
        "comparison": {"dataset_articles": 8, "missing_vector_articles": 1, "missing_date_articles": 1},
        "temporal": {"failed_feature_pairs": 0}}
    monkeypatch.setattr(study, "_parent", lambda *args: parent)
    monkeypatch.setattr(study, "_inputs", lambda *args: inputs)
    calls = []
    def references(*args: Any) -> Any:
        frozen = study.judged.original._records(engine, "event_group_centroid_frozen", "synthetic-centroids")
        assert len(frozen) == 1 and frozen[0][1]["frozen_before_reference_evaluation"]
        value = engine.ledger.artifacts.read(frozen[0][1]["artifact"])
        assert set(value["variants"]) == {"0.9", "0.95", "0.975"}
        calls.append(True)
        return {"rows": rows, "judged": judged, "failed_ids": [], "duplicate_pair_ids": []}
    monkeypatch.setattr(study, "_references", references)
    data = {"reference_result": "synthetic-completed-review", "study_key": "synthetic-centroids",
            "instruction": "Constructed collective-vector diagnostic only", "output_directory": str(engine.ledger.root / "centroids")}
    def run(**extra: Any) -> Any:
        return engine.execute("test_collective_group_vectors", {**data, **extra},
            objective="Verify constructed centroid audit, SQL and frozen resume", actor="test:software")
    engine.ledger.fail_event = "centroid_merge.frozen"
    with pytest.raises(AuditError):
        run()
    assert not calls
    engine.ledger.fail_event = None
    monkeypatch.setattr(study, "_compute", lambda *args: pytest.fail("Frozen variants recomputed"))
    result = run()
    assert len(calls) == 1 and result["default_cutoff"] == .975 and result["threshold_validated"] is False
    assert result["reference_pairs"] == 3 and result["mapping_diagnostics"]["multi_group_queries"] == 2
    assert result["mapping_diagnostics"]["valid_centroids"] == 3
    assert result["baseline_quality"]["labels"]["uncertain"]["unprocessed"] == 1
    assert len(result["table"]) == 3
    for variant in result["table"]:
        assert variant["reference_labels"]["same_event"]["together"] == 1
        assert variant["reference_labels"]["different_event"]["together"] == 1
        assert variant["reference_labels"]["different_event"]["weighted_together"] == 2.
        assert variant["reference_labels"]["uncertain"]["unprocessed"] == 1
        calculation = engine.ledger.artifacts.read(variant["calculation_artifact"])
        assert calculation["sql"] == study.SQL
        assert engine.ledger.artifacts.read(calculation["parameters"][0]["artifact"])
    frozen = engine.ledger.get(result["frozen_candidates"], "event_group_centroid_frozen")
    stored = engine.ledger.artifacts.read(frozen["artifact"])
    assert len(engine.ledger.artifacts.read_bytes(stored["centroid_artifact"])) == 3 * 2 * 4
    assert result["warm_retrieval"]["queries"] == 2
    assert result["timings"]["default_full_algorithm_seconds"] > 0
    assert result["new_model_calls"] == result["actual_group_merges"] == result["accepted_dossiers"] == 0
    assert result["new_embedding_requests"] == 0 and not result["current_memberships_changed"]
    assert result["presentation"]["markdown"] == study.render(result)
    assert run()["id"] == result["id"] and len(calls) == 1
    with pytest.raises(ResearchError, match="immutable"):
        run(instruction="A changed instruction needs a new method")
    assert engine.ledger.verify()["status"] == "verified"
