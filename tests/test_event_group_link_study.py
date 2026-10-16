"""One synthetic decision/proposal scenario with raw conflicts and audit resume."""
from dataclasses import replace
from itertools import combinations
from typing import Any

import pytest

from newsresearch import event_group_link_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_seven_day_choice_frozen_links_quarantine_and_no_actual_merges(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    a, b, c, d, e, f = ids[:6]
    for n, source in enumerate(ids):
        metadata[source]["published_at"] = f"2026-01-{(1, 2, 15, 16, 29, 30)[n]:02d}" if n < 6 else None
        metadata[source]["url"] = f"https://site{n % 2}.example/story"
    groups = [{"group_id": "A", "members": [a, b]}, {"group_id": "B", "members": [c, d]}, {"group_id": "C", "members": [e, f]}]
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}

    def pair(left: str, right: str) -> Any:
        left, right = sorted((left, right))
        return {"pair_id": digest([left, right]), "left": left, "right": right, "distance": .01,
            "status": "completed", "features": dict.fromkeys(FEATURES, .99), "fold": "development"}

    rows = [{**pair(left, right), "weight": float(n + 1), "inclusion_probability": 1. / (n + 1)}
            for n, (left, right) in enumerate(((a, b), (a, c), (a, e), (b, f)))]
    judged = {row["pair_id"]: {"status": "completed", "label": label} for row, label in zip(rows,
        ("same_event", "same_event", "different_event", "uncertain"), strict=True)}

    def setup(session: str, context: Any, data: Any) -> Any:
        def save(value: Any) -> str:
            return study.base._save(engine, session, value, "Constructed group-link fixture")
        plan["metadata_artifact"] = save(metadata)
        current = {"rule": rule, "plan": plan["id"], "versions": plan["versions"], "exports": {"groups": {"artifact": save(groups)}}}
        temporal = {"parent_result": "synthetic-selected-guarded-seven", "versions": plan["versions"],
            "feature_artifact": save([pair(left, right) for left, right in combinations(ids[:6], 2)]),
            "provider_artifact": save({"rows": [{"source_version": source, "event_uri": "event-1", "uri_type": "text", "coverage_status": "populated"} for source in ids]}),
            "provider_coverage": {"populated": 8}, "pooled_candidates": 15, "failed_feature_pairs": 0}
        temporal_id = engine.ledger.record(session, "event_temporal_result", "fixture", temporal)
        manifest = engine.ledger.record(session, "event_window_manifest", "fixture", {"versions": plan["versions"],
            "method": {"parent": temporal_id, "implementation": study.base._hashes(study.windows.CODE)}})
        comparison = {"manifest": manifest, "versions": plan["versions"], "parent_result": temporal_id, "plan": plan["id"],
            "status": "completed_group_comparison", "accepted_dossiers": 0, "pending_pairs": 0,
            "dataset_articles": 8, "dated_vector_articles": 6, "missing_vector_articles": 1, "missing_date_articles": 1}
        return engine.ledger.record(session, "event_window_result", "fixture", comparison), temporal, current

    monkeypatch.setattr(engine, "_status", setup)
    comparison_id, temporal, current = engine.execute("status", objective="Store synthetic link fixture", actor="test:software")
    monkeypatch.setattr(study.windows, "_parent", lambda *args: (temporal, current, {}))
    monkeypatch.setattr(study, "load_plan", lambda *args: (plan, {}, {"rows": rows}))
    calls = []

    def references(*args: Any) -> Any:
        frozen = study._records(engine, "event_group_link_proposals", "synthetic-links")
        assert len(frozen) == 1 and frozen[0][1]["frozen_before_reference_check"]
        calls.append(True)
        return {"rows": rows, "judged": judged, "versions": plan["versions"], "original_result": "synthetic-references", "failed_ids": []}

    monkeypatch.setattr(study.windows, "_references", references)
    data = {"comparison_result": comparison_id, "study_key": "synthetic-links", "instruction": "Keep seven days; propose strong group links",
        "superseded_instruction": "Thirty days was suggested then withdrawn", "output_directory": str(engine.ledger.root / "links")}

    def run(**extra: Any) -> Any:
        return engine.execute("propose_cross_window_group_links", {**data, **extra}, objective="Verify synthetic strong group links", actor="test:software")

    engine.ledger.fail_event = "event_group_links.frozen"
    with pytest.raises(AuditError):
        run()
    assert calls == []
    engine.ledger.fail_event = None
    monkeypatch.setattr(study.numeric, "propose", lambda *args: pytest.fail("Frozen proposals recomputed"))
    result = run()
    assert result["statistics"]["multi_article_groups"] == 3
    assert result["diagnostics"]["qualified_pairs"] == 3 and result["qualified_proposals"] == 1
    assert result["affected_reference_pairs"] == 3 and result["affected_labels"] == {"same_event": 1, "different_event": 1, "uncertain": 1}
    assert result["quarantined_proposals"] == 1 and result["awaiting_event_fact_review"] == 0
    assert result["baseline_labels"]["different_event"]["together"] == 0 and result["raw_labels"]["different_event"]["together"] == 1
    assert result["raw_labels"]["same_event"]["weighted_together"] == 3.
    assert not result["current_memberships_changed"] and result["actual_group_merges"] == result["new_model_calls"] == result["accepted_dossiers"] == 0
    policy = engine.ledger.get(result["policy"], "policy")["content"]
    assert policy["publication_gap_days"] == 7 and not policy["thirty_day_selection_was_applied"] and not policy["threshold_validated"]
    assert policy["instruction"] == data["instruction"] and policy["withdrawn_instruction"] == data["superseded_instruction"]
    assert engine.ledger.artifacts.read(current["exports"]["groups"]["artifact"]) == groups
    assert result["presentation"]["markdown"] == study.render(result)
    assert run()["id"] == result["id"] and len(calls) == 1
    with pytest.raises(ResearchError, match="immutable"):
        run(instruction="Changed method instruction")
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"
