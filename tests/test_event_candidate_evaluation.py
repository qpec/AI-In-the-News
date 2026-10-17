"""Source-free fixed-draw and audited preparation checks; no model execution."""
from __future__ import annotations

import pytest

from newsresearch.common import Config, Context, ResearchError
from newsresearch.event_candidate_evaluation import CANDIDATE_METHOD, CandidateEvaluationResearch, _coverage, frozen_draw
from newsresearch.event_eval_math import estimate_pair_metrics
from newsresearch.event_eval_workflow import METHOD, save
from newsresearch.runtime import audited_handler


def test_chance_overlap_is_retained_without_rejection_replacement_or_seed_change():
    membership = {f"invented-{i:03}": f"group-{i // 2:03}" for i in range(160)}
    first = frozen_draw(membership, [])
    overlapping = first["design"]["selected_pairs"][0]
    second = frozen_draw(membership, [overlapping])
    assert first["design"] == second["design"]
    assert second["overlap"]["evaluation_pair_ids"] == [overlapping["pair_id"]]
    assert second["overlap"]["excluded_pairs"] == second["overlap"]["replacements"] == 0
    assert second["overlap"]["reseeded"] is False
    assert second["overlap"]["strict_unseen_pair_holdout"] is False
    assert [(row["stratum"], row["n"]) for row in second["design"]["strata"]] == [
        ("within_group", 56), ("between:random_tail", 8)]
    assert {row["pair_id"] for row in second["canaries"]}.isdisjoint(
        {row["pair_id"] for row in second["design"]["selected_pairs"]})
    metrics = estimate_pair_metrics(second["design"], [], reference_kind="model")
    assert metrics["expected_pairs"] == 64 and metrics["counts"]["pending"] == 64
    with pytest.raises(ResearchError, match="coverage_guards_failed"):
        _coverage({"delta": .25, "baseline": {"within_pairs": 100, "grouped_articles": 100},
            "candidate": {"within_pairs": 20, "grouped_articles": 32}, "retained_pairs_fraction": .2})


class FixtureResearch(CandidateEvaluationResearch):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in (("protocol", {"method": "fictional-candidate-plan-fixture"}),
                              ("selection", {"rules": "160 invented sources only"})):
            versions[kind] = self._version(session, context, {"kind": kind, "key": "fixture", "content": content})["id"]
        dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": [{"source_key": str(i), "title": f"Invented source {i}", "synthetic": True,
                "retention": "permitted", "url": f"https://example.invalid/{i}",
                "body": f"Fictional group {i // 2} announced an invented model at a synthetic gathering. Source {i}."} for i in range(160)],
            "retrieval": {"source": "synthetic-test", "retrieved_at": "2026-01-01T00:00:00+00:00", "parameters": {}}})
        versions["dataset"] = dataset["id"]
        sources = dataset["sources"]
        membership = {source: f"fictional-group-{i // 2:03}" for i, source in enumerate(sources)}
        draw = frozen_draw(membership, [])
        old = {"method": METHOD, "versions": versions, "study_key": "fictional-original",
            "group_result": "fictional-baseline", "design": draw["design"],
            "tasks": [draw["design"]["selected_pairs"][0]], "quarantined_source_versions": [],
            "config": {"codex_model": "gpt-6-luna", "reasoning_effort": "low", "timeout_seconds": 90,
                "max_input_bytes": 32768, "max_output_bytes": 16384, "codex_executable": "fictional-never-run",
                "executable_sha256": "fictional-not-executed"}}
        old_id = self.ledger.record(session, "luna_group_validation_plan", "fictional-original", old)
        membership_ref = save(self, session, membership, "Invented candidate memberships")
        candidate = {"method": CANDIDATE_METHOD, "delta": .05, "original_evaluation_plan": old_id,
            "baseline_group_result": "fictional-baseline", "unchanged_original_memberships": True,
            "candidate_membership": membership_ref,
            "original_rule": {"features": [f"fictional-feature-{i}" for i in range(5)], "thresholds": [.8] * 5},
            "rule": {"features": [f"fictional-feature-{i}" for i in range(5)], "thresholds": [.81] * 5},
            "baseline": {"groups": 80, "grouped_articles": 160, "within_pairs": 80},
            "candidate": {"groups": 80, "grouped_articles": 160, "within_pairs": 80},
            "retained_pairs_fraction": 1, "grouped_article_fraction": 1}
        candidate_id = self.ledger.record(session, "event_group_refinement_result", "fictional-candidate", candidate)
        return {"candidate_result": candidate_id, "original_plan": old_id}


def test_audited_preparation_freezes_68_packets_and_reuses_exact_plan_without_models(tmp_path):
    engine = FixtureResearch(tmp_path / "synthetic-store", config=Config(offline=True))
    try:
        def call(operation, payload):
            return engine.execute(operation, payload, objective="Source-free candidate preparation test", actor="test:synthetic")
        fixture = call("status", {})
        data = {"phase": "prepare_candidate_pairs", **fixture}
        result = call("luna_group_validation", data)
        assert len(result["tasks"]) == 68 and all(task["status"] == "prepared" for task in result["tasks"])
        assert result["limits"] == {"max_requests": 68, "max_article_exposures": 136, "max_retries": 0}
        assert len(result["overlap"]["evaluation_pair_ids"]) == 1
        assert result["model_authorized"] is False and result["new_model_calls"] == 0
        assert result["candidate_rule"]["thresholds"] == [.81] * 5
        assert result["baseline_counts"]["within_pairs"] == result["candidate_counts"]["within_pairs"] == 80
        assert "| fictional-feature-0 | 0.8 | 0.81 |" in result["presentation"]["markdown"]
        assert result["coverage_guards"]["pair_retention"] == result["coverage_guards"]["grouped_article_retention"] == 1
        for task in result["tasks"]:
            request = engine.ledger.artifacts.read(task["request"])
            assert request["versions"] == result["versions"]
            assert [article["source_version"] for article in request["articles"]] == [task["left"], task["right"]]
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='policy'").fetchone()[0] == 0
        assert call("luna_group_validation", data)["id"] == result["id"]
        presentation = result["presentation"]
        assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode("utf-8")
        engine.ledger.verify()
    finally:
        engine.close()
