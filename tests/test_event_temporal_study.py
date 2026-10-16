"""One source-free runtime diagnostic: coverage, auditing and exact resume."""
from contextlib import contextmanager
from dataclasses import replace
from typing import Any

import numpy as np
import pytest

from newsresearch import event_temporal_study as study
from newsresearch.common import AuditError, ResearchError, digest
from newsresearch.event_pair_selection import FEATURES
from test_event_pair_experiment import planned as _planned

planned = _planned


def test_temporal_diagnostic_preserves_cohorts_audit_failures_and_exact_cache(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    engine.config = replace(engine.config, offline=True)
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    ids = sorted(metadata)
    a, b, c, unknown, e, f = ids[:6]
    for source, date in zip(ids, ("2020-01-01", "2020-01-02", "2020-01-30", None,
                                 "2020-05-01", "2020-05-03", "2020-07-01", "2020-07-02"), strict=True):
        metadata[source]["published_at"] = date
    rule = {"features": list(FEATURES), "thresholds": [.5] * 5, "publication_gap_days": 7}
    groups = [{"group_id": "ab", "members": [a, b]}, *[{"group_id": source, "members": [source]} for source in (c, e, f)]]
    mapping = [{"source_version": source, "chunks": [{"row": n, "chunk": f"chunk-{n}", "passage": f"passage-{n}"}]} for n, source in enumerate(ids[:6])]

    def row(left: str, right: str) -> Any:
        left, right = sorted((left, right))
        dates = study.publication_coverage(ids, {source: value["published_at"] for source, value in metadata.items()})["valid_dates"]
        return {"pair_id": digest([left, right]), "left": left, "right": right, "distance": 0.,
            "fold": "development", "weight": 2., "inclusion_probability": .5, "origin": ["synthetic"],
            "status": "completed", "features": dict.fromkeys(FEATURES, 1.),
            "publication_gap_days": abs((dates[left] - dates[right]).days) if left in dates and right in dates else None}

    refs = [row(a, b), row(a, c), row(a, e), row(a, unknown)]
    labels = {value["pair_id"]: {"status": "completed", "label": label} for value, label in zip(
        refs, ("same_event", "same_event", "different_event", "uncertain"), strict=True)}

    def setup(session: str, context: Any, data: Any) -> Any:
        def save(value: Any) -> str:
            return study.base._save(engine, session, value, "Constructed temporal fixture only")
        plan["development_sample_artifact"] = save({"rows": refs})
        feature_manifest = engine.ledger.record(session, "event_pair_feature_manifest", "fixture", {
            "versions": plan["versions"], "method": {"implementation": study.base._hashes(study.base.CODE)}})
        feature_id = engine.ledger.record(session, "event_pair_feature_experiment", "fixture", {
            "manifest": feature_manifest, "versions": plan["versions"], "plan": plan["id"], "development_features": save(refs)})
        final = {"parent_feature_result": feature_id}
        final_id = engine.ledger.record(session, "event_pair_monotone_result", "fixture", final)
        application_manifest = engine.ledger.record(session, "event_rule_application_manifest", "fixture", {
            "versions": plan["versions"], "method": {"rule": rule, "plan": plan["id"], "parent": final_id,
            "implementation": study.base._hashes(study.application.CODE)}})
        parent = {"versions": plan["versions"], "manifest": application_manifest, "status": "completed_provisional_application",
            "plan": plan["id"], "parent_result": final_id, "rule": rule, "accepted_dossiers": 0, "pending_pairs": 0,
            "dataset_articles": 8, "vector_articles": 6, "date_eligible_articles": 5, "missing_date_articles": 1,
            "pooled_candidates": 2, "proposed_link_pairs": 2, "score_artifact": save([row(a, b), row(e, f)])}
        parent_id = engine.ledger.record(session, "event_rule_application_result", "fixture", parent)
        refinement_manifest = engine.ledger.record(session, "event_group_refinement_manifest", "fixture", {
            "versions": plan["versions"], "method": {"parent": parent_id, "implementation": study.base._hashes(study.refinement.CODE)}})
        current = {"versions": plan["versions"], "manifest": refinement_manifest, "status": "adopted_provisional_refinement",
            "adopted": True, "parent_result": parent_id, "plan": plan["id"], "rule": rule, "accepted_dossiers": 0,
            "pending_pairs": 0, "exports": {"groups": {"artifact": save(groups)}}}
        return engine.ledger.record(session, "event_group_refinement_result", "fixture", current), parent, final

    monkeypatch.setattr(engine, "_status", setup)
    current_id, parent, final = engine.execute("status", objective="Store source-free temporal fixture", actor="test:software")
    monkeypatch.setattr(study.application, "_inputs", lambda *args: (final, plan, {}, metadata, mapping,
        np.tile(np.array([[1., 0.]], dtype=np.float32), (6, 1))))
    monkeypatch.setattr(study.refinement, "_references", lambda *args: (labels, plan["versions"], "synthetic-references"))
    opened = []

    @contextmanager
    def vectors(*args: Any) -> Any:
        opened.append(True)
        yield [{"source_version": source, "id": f"chunk-{n}", "passage_id": f"passage-{n}"} for n, source in enumerate(ids[:6])], np.tile([[1., 0.]], (6, 1))

    monkeypatch.setattr(study, "vectors", vectors)
    data = {"parent_result": current_id, "diagnostic_key": "synthetic-temporal", "user_instruction": "Constructed software test only",
            "output_directory": str(engine.ledger.root / "temporal")}

    def run(**extra: Any) -> Any:
        return engine.execute("check_event_time_spans", {**data, **extra}, objective="Verify synthetic temporal diagnostic", actor="test:software")

    engine.ledger.fail_event = "event_temporal.intended"
    with pytest.raises(AuditError):
        run()
    assert opened == []
    engine.ledger.fail_event = None
    result = run()
    assert result["checked_vector_pairs"] == result["pooled_candidates"] == 15
    assert result["reused_feature_pairs"] == 2 and result["new_feature_pairs"] == 13
    assert result["missing_vector_articles"] == 2 and result["missing_date_articles"] == 1
    assert [cap["dated_passing_pairs"] for cap in result["caps"]] == [2, 2, 4, 4, 10]
    assert result["unknown_gap_cosine_passing_pairs"] == 5
    assert result["provider_coverage"] == {"missing": 8}
    assert result["reference_pairs"] == 4 and result["reference_unprocessed"] == 0
    assert result["reference_caps"][-1]["labels"]["same_event"]["passing_weight"] == 4.
    assert result["reference_caps"][-1]["labels"]["uncertain"]["unknown_dates"] == 1
    assert result["active_partition_changed"] is False and result["accepted_dossiers"] == result["new_model_calls"] == 0
    assert result["presentation"]["markdown"] == study.render(result)
    query = engine.ledger.artifacts.read(result["provider_artifact"])
    assert len(query["rows"]) == 8
    assert engine.ledger.artifacts.read(query["query_artifact"])["sql"] == study.PROVIDER_SQL
    monkeypatch.setattr(study.application, "_inputs", lambda *args: pytest.fail("Completed diagnostic recomputed"))
    assert run()["id"] == result["id"] and len(opened) == 1
    with pytest.raises(ResearchError, match="immutable"):
        run(user_instruction="Changed instruction requires a new diagnostic")
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    # SQLite returns objects/arrays as JSON strings: neither is a textual ID.
    values = [{"eventUri": "provider-id"}, {"eventUri": "  "}, {"eventUri": None},
              {"eventUri": {}}, {"eventUri": []}, {"eventUri": 4}, {}]
    dataset = engine.execute("ingest", {"articles": [{"source_key": f"provider-{n}", "body": f"Provider type fixture {n}.",
        "retention": "permitted", "synthetic": True, "raw_record": value} for n, value in enumerate(values)],
        "retrieval": {"source": "constructed-provider-fixture", "retrieved_at": study.utc(), "parameters": {}}},
        versions=plan["versions"], objective="Construct provider type regression fixtures", actor="test:software")
    provider_ids = engine.ledger.get(dataset["id"], "dataset")["source_versions"]
    monkeypatch.setattr(engine, "_status", lambda session, context, data: study._providers(engine, session, provider_ids,
        {**plan["versions"], "dataset": dataset["id"]}))
    providers, counts, _ = engine.execute("status", objective="Verify provider metadata type coverage", actor="test:software")
    assert counts == {"populated": 1, "empty_string": 1, "null": 1, "nonstring": 3, "missing": 1}
    assert list(providers.values()).count("provider-id") == 1 and list(providers.values()).count(None) == 6
    assert engine.ledger.verify()["status"] == "verified"
