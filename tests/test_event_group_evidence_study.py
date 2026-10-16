"""Source-free integration: frozen queue, full packets, cumulative budget, resume."""
from dataclasses import replace
from itertools import combinations
import sys
from typing import Any

import pytest

from newsresearch import event_group_evidence_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_full_packets_holdout_budget_audit_failure_and_resume(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    for n, source in enumerate(ids):
        metadata[source]["published_at"] = "2026-01-01" if n < 2 else "2026-01-20"
        metadata[source]["url"] = f"https://site{n}.example/story"
    groups = [{"group_id": "A", "members": ids[:2]}, {"group_id": "B", "members": [ids[2]]},
              {"group_id": "C", "members": [ids[3]]}]
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}
    scored = [{"pair_id": digest([left, right]), "left": left, "right": right, "status": "completed",
               "features": dict.fromkeys(FEATURES, .99)} for left, right in combinations(ids[:4], 2)]

    def setup(session: str, context: Any, data: Any) -> Any:
        def save(value: Any) -> str:
            return study.links.base._save(engine, session, value, "Constructed evidence fixture")
        plan["metadata_artifact"] = save(metadata)
        current = {"plan": plan["id"], "exports": {"groups": {"artifact": save(groups)}}, "rule": rule}
        temporal = {"feature_artifact": save(scored), "pooled_candidates": len(scored), "failed_feature_pairs": 0}
        for n in range(55):
            engine.ledger.append(session, "model.attempt.intended", {"attempt": f"synthetic-{n}",
                "event_pair_study": plan["study_key"], "event_pair_retry": n == 54,
                "reserved_pair_attempts": 1, "reserved_article_exposures": 2})
            engine.ledger.append(session, "model.attempt.completed", {"attempt": f"synthetic-{n}", "status": "invalid"})
        return current, temporal

    monkeypatch.setattr(engine, "_status", setup)
    current, temporal = engine.execute("status", objective="Construct evidence preparation fixture", actor="test:software")
    previous = {"versions": plan["versions"], "selected_seven_day_result": "synthetic-seven", "statistics": {
        "multi_article_groups": 1, "grouped_articles": 2, "singletons": 2}}
    comparison = {"dated_vector_articles": 4, "dataset_articles": 8, "missing_vector_articles": 1, "missing_date_articles": 3}
    frame = {"representatives": [{"body_sha256": metadata[source]["body_sha256"],
                                 "fold": "validation" if source == ids[3] else "development"} for source in ids]}
    monkeypatch.setattr(study, "_parents", lambda *args: (previous, comparison, temporal, current, {}))
    monkeypatch.setattr(study, "_configuration", lambda *args: study._config(engine,
        {"codex_model": "synthetic-model", "codex_executable": sys.executable}))
    monkeypatch.setattr(study, "load_plan", lambda *args: (plan, frame, {"rows": []}))
    original_request = study._request
    # Numeric publication dates above are constructed; stored source metadata remains null.
    monkeypatch.setattr(study, "_request", lambda e, s, task, m, v: original_request(e, s, task,
        {source: {**summary, "published_at": None} for source, summary in m.items()}, v))
    calls = []

    def references(*args: Any) -> Any:
        assert study._records(engine, "event_group_evidence_queue", "synthetic-evidence")[0][1]["frozen_before_reference_check"]
        calls.append(True)
        return {"rows": [], "judged": {}, "failed_ids": [], "original_result": "synthetic-model-references"}

    monkeypatch.setattr(study.links.windows, "_references", references)
    data = {"previous_result": "synthetic-links", "study_key": "synthetic-evidence",
            "output_directory": str(engine.ledger.root / "evidence")}

    def run(**extra: Any) -> Any:
        return engine.execute("prepare_cross_window_event_review", {**data, **extra},
            objective="Verify offline source packets and original workflow accounting", actor="test:software")

    engine.ledger.fail_event = "event_group_evidence.frozen"
    with pytest.raises(AuditError):
        run()
    assert not calls
    engine.ledger.fail_event = None
    monkeypatch.setattr(study.numeric, "prepare", lambda *a, **kw: pytest.fail("Frozen queue recomputed"))
    engine.ledger.fail_event = "event_group_evidence.packets_frozen"
    with pytest.raises(AuditError):
        run()
    engine.ledger.fail_event = None
    monkeypatch.setattr(study, "_request", lambda *a, **kw: pytest.fail("Frozen packets reread"))
    result = run()
    assert result["selected_proposals"] == 1 and result["prepared_pair_packets"] == 3
    assert result["unique_articles_prepared"] == 3 and result["pending_model_judgments"] == 3
    assert result["budget"]["remaining_primary"] == 36 and result["budget"]["remaining_retries"] == 9
    assert result["budget"]["spent_article_exposures"] == 110 and not result["budget"]["budget_reset"]
    packets = engine.ledger.artifacts.read(result["exports"]["packets"]["artifact"])
    for packet in packets:
        request = engine.ledger.artifacts.read(packet["request_ref"])
        study.validate_request(request)
        assert ids[3] not in {article["source_version"] for article in request["articles"]}
    assert result["diagnostics"]["candidate_status_counts"]["heldout_or_unmapped_excluded"] == 1
    assert result["presentation"]["markdown"] == study.render(result)
    assert result["new_model_calls"] == result["actual_group_merges"] == result["accepted_dossiers"] == 0
    assert not result["sealed_holdout_opened"] and result["failed_source_packets"] == 0
    assert run()["id"] == result["id"] and len(calls) == 2
    with pytest.raises(ResearchError, match="immutable"):
        run(output_directory=str(engine.ledger.root / "changed"))
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"
