"""One integrated synthetic audit/coverage/resume scenario; no corpus inference."""
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from newsresearch import event_rule_application_study as study
from newsresearch.common import AuditError, ResearchError
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_all_article_application_keeps_unknowns_provenance_and_resume(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    plan = {**plan, "index": "synthetic-index"}
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    vector_ids = ids[:-1]
    for source in vector_ids[:-1]:
        metadata[source]["published_at"] = "2026-10-01"
    mapped = [{"source_version": source, "chunks": [{"row": n, "chunk": f"c{n}", "passage": f"p{n}"}]} for n, source in enumerate(vector_ids)]
    passages = [{"source_version": source, "id": f"c{n}", "passage_id": f"p{n}"} for n, source in enumerate(vector_ids)]
    matrix = np.tile([[1., 0.]], (len(vector_ids), 1))
    metrics = {"precision_pessimistic_observed": .8, "precision_pessimistic_weighted": .954,
               "known_same_coverage_weighted": .551}
    parent = {"plan": plan["id"], "best_at_required_coverage": {"features": list(FEATURES), "thresholds": [.8] * 5,
               "publication_gap_days": 7, "metrics": metrics}}
    monkeypatch.setattr(study, "_inputs", lambda *args: (parent, plan, {}, metadata, mapped, matrix))

    @contextmanager
    def vectors(*args: Any) -> Any:
        yield passages, matrix

    monkeypatch.setattr(study, "vectors", vectors)
    original = study.base._compute
    calls = []

    def compute(*args: Any) -> Any:
        calls.append(True)
        rows = original(*args)
        # A constructed numeric failure must remain unknown, never a negative.
        rows[0]["status"] = "failed"
        rows[0]["features"]["max_passage_cosine"] = None
        return rows

    monkeypatch.setattr(study.base, "_compute", compute)
    data = {"parent_result": "synthetic-parent", "application_key": "synthetic-application",
            "user_instruction": "Synthetic software authorization to apply an unvalidated rule",
            "apply_unvalidated": True, "output_directory": str(engine.ledger.root / "output")}

    def run(**extra: Any) -> Any:
        return engine.execute("apply_event_rule", {**data, **extra}, objective="Verify offline application using synthetic fixtures", actor="test:software")

    engine.ledger.fail_event = "event_rule.application.intended"
    with pytest.raises(AuditError):
        run()
    assert calls == []
    engine.ledger.fail_event = None
    result = run()
    assert result["dataset_articles"] == 8 and result["vector_articles"] == 7
    assert result["missing_vector_articles"] == result["missing_date_articles"] == 1
    assert result["checked_date_pairs"] == result["pooled_candidates"] == 15
    assert result["failed_feature_pairs"] == 1 and result["pending_pairs"] == 0
    assert result["proposed_link_pairs"] == 14 and result["bridge_edges"] > 0
    assert result["accepted_dossiers"] == result["new_model_calls"] == result["new_embedding_requests"] == 0
    articles = engine.ledger.artifacts.read(result["exports"]["articles"]["artifact"])
    assert len(articles) == 8 and all(item["same_event_answer"] is None and not item["accepted"] for item in articles)
    assert {item["status"] for item in articles} >= {"missing_vectors", "missing_publication_date", "provisional"}
    assert sum(item["failed_pair_count"] for item in articles) == 2
    assert sum(item["processing_status"] == "partial_failed_pairs" for item in articles) == 2
    assert result["presentation"]["markdown"] == study.render(result)
    monkeypatch.setattr(study.base, "_compute", lambda *args: pytest.fail("Completed scores were recomputed"))
    assert run()["id"] == result["id"]
    with pytest.raises(ResearchError, match="immutable"):
        run(user_instruction="Changed instruction cannot reuse this key")
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"
