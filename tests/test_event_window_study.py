"""One synthetic runtime comparison with audit failures and frozen-partition resume."""
from dataclasses import replace
from itertools import combinations
from typing import Any

import pytest

from newsresearch import event_window_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_actual_windows_freeze_before_references_preserve_missingness_and_resume(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    a, b, c, unknown, e, f = ids[:6]
    for source, published in zip(ids, ("2020-01-01", "2020-01-02", "2020-01-30", None,
                                       "2020-05-01", "2020-05-03", "2020-07-01", "2020-07-02"), strict=True):
        metadata[source]["published_at"] = published
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}

    def pair(left: str, right: str) -> Any:
        left, right = sorted((left, right))
        return {"pair_id": digest([left, right]), "left": left, "right": right, "distance": 0.,
            "status": "completed", "features": dict.fromkeys(FEATURES, 1.), "fold": "development"}

    scored = [pair(left, right) for left, right in combinations(ids[:6], 2)]
    failed_id = pair(b, unknown)["pair_id"]
    for row in scored:
        if row["pair_id"] == failed_id:
            row.update({"status": "failed", "features": dict.fromkeys(FEATURES, None)})
    active = [{"group_id": "ab", "members": [a, b]}, {"group_id": "ef", "members": [e, f]}, {"group_id": "c", "members": [c]}]
    rows = [{**pair(left, right), "weight": float(n + 1), "inclusion_probability": 1. / (n + 1)}
            for n, (left, right) in enumerate(((a, b), (a, c), (a, e), (a, unknown)))]
    judged = {row["pair_id"]: {"status": "completed", "label": label} for row, label in zip(rows,
        ("same_event", "same_event", "different_event", "uncertain"), strict=True)}

    def setup(session: str, context: Any, data: Any) -> Any:
        def save(value: Any) -> str:
            return study.base._save(engine, session, value, "Constructed window-comparison fixture")
        plan["metadata_artifact"] = save(metadata)
        plan["mapping_artifact"] = save([{"source_version": source} for source in ids[:6]])
        group_ref = save(active)
        current = {"plan": plan["id"], "rule": rule, "exports": {"groups": {"artifact": group_ref}, "candidate_groups": {"artifact": group_ref}}}
        original = {"multi_article_groups": 2}
        manifest = engine.ledger.record(session, "event_temporal_manifest", "fixture", {"versions": plan["versions"],
            "method": {"parent": "synthetic-current", "rule": rule, "plan": plan["id"], "implementation": study.base._hashes(study.temporal.CODE)}})
        parent = {"versions": plan["versions"], "manifest": manifest, "status": "completed_with_failed_pairs",
            "pending_pairs": 0, "parent_result": "synthetic-current", "rule": rule, "plan": plan["id"],
            "feature_artifact": save(scored), "dataset_articles": 8, "vector_articles": 6, "dated_vector_articles": 5,
            "missing_date_articles": 1, "pooled_candidates": 15, "failed_feature_pairs": 1,
            "caps": [{"cap_days": cap, "dated_passing_pairs": count} for cap, count in zip(study.CAPS, (2, 4, 4, 10), strict=True)]}
        return engine.ledger.record(session, "event_temporal_result", "fixture", parent), current, original

    monkeypatch.setattr(engine, "_status", setup)
    parent_id, current, original = engine.execute("status", objective="Store constructed group-window fixture", actor="test:software")
    monkeypatch.setattr(study.temporal, "_parent", lambda *args: (current, original))
    monkeypatch.setattr(study, "load_plan", lambda *args: (plan, {}, {"rows": rows}))
    calls = []

    def references(*args: Any) -> Any:
        frozen = study._records(engine, "event_window_partition", study._records(engine, "event_window_manifest", "synthetic-windows")[0][0])
        assert len(frozen) == 4 and all(row["frozen_before_reference_check"] for _, row in frozen)
        calls.append(True)
        return {"rows": rows, "judged": judged, "versions": plan["versions"], "original_result": "synthetic-judgments", "failed_ids": []}

    monkeypatch.setattr(study, "_references", references)
    data = {"parent_result": parent_id, "comparison_key": "synthetic-windows", "user_instruction": "Constructed comparison only",
            "output_directory": str(engine.ledger.root / "windows")}

    def run(**extra: Any) -> Any:
        return engine.execute("compare_event_group_windows", {**data, **extra}, objective="Verify actual synthetic group comparisons", actor="test:software")

    engine.ledger.fail_event = "event_windows.partition.intended"
    with pytest.raises(AuditError):
        run()
    assert calls == []
    engine.ledger.fail_event = "event_windows.all_partitions.frozen"
    with pytest.raises(AuditError):
        run()
    assert calls == []
    engine.ledger.fail_event = None
    monkeypatch.setattr(study.numeric, "build", lambda *args: pytest.fail("Frozen partition recomputed"))
    result = run()
    assert len(calls) == 1
    assert [row["statistics"]["multi_article_groups"] for row in result["table"]] == [2, 2, 2, 1]
    assert [row["statistics"]["multi_article_size"]["maximum"] for row in result["table"]] == [2, 3, 3, 5]
    assert [row["quality"]["labels"]["same_event"]["together"] for row in result["table"]] == [1, 2, 2, 2]
    assert [row["quality"]["labels"]["different_event"]["together"] for row in result["table"]] == [0, 0, 0, 1]
    assert all(row["quality"]["labels"]["uncertain"]["unprocessed"] == 1 for row in result["table"])
    assert result["table"][-1]["quality"]["labels"]["same_event"]["weighted_together"] == 3.
    assert result["failed_feature_pairs"] == result["missing_date_articles"] == 1
    assert result["missing_vector_articles"] == 2 and not result["active_partition_changed"]
    assert result["new_model_calls"] == result["new_embedding_requests"] == result["new_feature_calculations"] == result["accepted_dossiers"] == 0
    articles = engine.ledger.artifacts.read(result["exports"]["articles"]["artifact"])
    assert len(articles) == 8 and all(value is None for row in articles if row["source_version"] == unknown for value in row["groups"].values())
    assert result["table"][-1]["changes_from_seven_days"]["merged_new_groups"] == 1
    assert result["presentation"]["markdown"] == study.render(result)
    partition = engine.ledger.get(result["partition_records"][0], "event_window_partition")
    calculation = engine.ledger.artifacts.read(partition["calculation_artifact"])
    assert calculation["sql"] == study.COUNT_SQL and calculation["parameters"][0]["artifact"] == partition["groups_artifact"]
    assert run()["id"] == result["id"] and len(calls) == 1
    with pytest.raises(ResearchError, match="immutable"):
        run(user_instruction="A changed comparison requires another method version")
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.verify()["status"] == "verified"
