"""Synthetic saved-vector retrieval through real preflight; no corpus/model calls."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from newsresearch.common import AuditError, ResearchError
from newsresearch import event_rag_retrieval as retrieval
from newsresearch.event_extraction_workflow import save
from newsresearch.runtime import audited_handler
from test_event_extraction_workflow import fixture


OBJECTIVE = "Verify synthetic saved-vector retrieval and audit invariants without external execution"


def run(engine, plan, **changes):
    return engine.execute("vector_search", {
        "plan": plan["id"], "study_key": "synthetic-event-rag", "top_k": 3, **changes,
    }, objective=OBJECTIVE, actor="test:synthetic")


def rag_fixture(tmp_path, monkeypatch, *, missing_target=False):
    engine, state, plan, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(type(engine), "_vector_search", retrieval.EventRagResearch._vector_search)

    @audited_handler
    def setup(self, session, context, data):
        capsule = save(self, session, {"synthetic": True}, "Synthetic vector input fixture only")
        candidate = self.ledger.record(session, "event_group_refinement_result", "synthetic-rag-input", {
            "capsule": capsule, "versions": plan["versions"],
        })
        selected_plan = plan
        if missing_target:
            # A separate, append-only synthetic frame has one eligible non-anchor.
            # It makes target-vector missingness observable despite 36 filled slots.
            original = self.ledger.get(plan["original_plan"], "luna_group_validation_plan")
            original.update(study_key="synthetic-rag-extra-target", tasks=[])
            original_id = self.ledger.record(session, "luna_group_validation_plan",
                                             "synthetic-rag-extra-target", original)
            self.ledger.record(session, "study_execution_ownership", original["study_key"], {
                "status": "imported_owner", "owner_workspace": str(self.ledger.root.resolve()),
            })
            selection = self.ledger.artifacts.read(plan["selection_artifact"])
            selection["exclusions"].pop(state["sources"][13])
            selection["exclusion_counts"].pop("unresolved_prior_attempt")
            selection["eligible_development_sources"] += 1
            selected_plan = {key: value for key, value in plan.items() if key not in {"id", "presentation"}}
            selected_plan.update(original_plan=original_id, selection=selection,
                                 selection_artifact=save(self, session, selection,
                                                         "Synthetic independent extra-target frame"))
            identifier = self.ledger.record(session, "luna_group_validation_plan",
                                            "synthetic-rag-extra-target-extraction", selected_plan)
            selected_plan = {"id": identifier, **selected_plan}
        return {"candidate": candidate, "plan": selected_plan}

    monkeypatch.setattr(type(engine), "_status", setup)
    setup_result = engine.execute("status", objective=OBJECTIVE, actor="test:synthetic")
    monkeypatch.setattr(retrieval, "RETAINED_CANDIDATE", setup_result["candidate"])
    plan = setup_result["plan"]
    calls = []

    def synthetic_vectors(current, session, capsule, dataset):
        assert current is engine and capsule == {"synthetic": True}
        assert dataset == plan["versions"]["dataset"]
        assert engine.ledger.db.execute(
            "SELECT COUNT(*) FROM records WHERE kind='event_rag_retrieval_manifest'"
        ).fetchone()[0] == 1
        calls.append(dataset)
        ids = state["sources"][:12]
        matrix = np.asarray([[1.0, n / 20, (n % 3) / 10] for n in range(12)], dtype=np.float32)
        return {"synthetic": True, "dataset": dataset}, ids, matrix

    def forbidden_model(*args, **kwargs):
        pytest.fail("Saved-vector retrieval must not dispatch models or prepare embeddings")

    monkeypatch.setattr(retrieval, "_vectors", synthetic_vectors)
    for name in ("codex_dispatch", "embed", "plan_embeddings", "plan_query_embedding"):
        monkeypatch.setattr(engine.gateway, name, forbidden_model)
    return engine, state, plan, calls


def test_audited_saved_vector_retrieval_retains_manifest_text_scores_and_presentation(tmp_path, monkeypatch):
    engine, state, plan, calls = rag_fixture(tmp_path, monkeypatch)
    try:
        result = run(engine, plan)
        assert result["status"] == "complete"
        assert len(result["rows"]) == 12 and result["candidate_slots"] == 36
        assert result["scored_pairs"] == 12 * 11 and result["pending_slots"] == 0
        assert result["missing_vector_sources"] == []
        assert result["eligible_vector_sources"] == sorted(state["sources"][:12])
        assert result["new_embeddings"] == result["new_model_calls"] == result["network_calls"] == 0
        assert result["memberships_changed"] is False and len(calls) == 1
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='policy'").fetchone()[0] == 0
        manifest = engine.ledger.get(result["manifest"], "event_rag_retrieval_manifest")
        assert manifest["anchors"] == [task["source_version"] for task in plan["tasks"]]
        assert manifest["versions"] == result["versions"]
        assert not set(state["sources"][12:]) & set(manifest["eligible"])
        packets = engine.ledger.artifacts.read(result["text"]["artifact"])
        assert len(packets["sources"]) == 12 and packets["missing_sources"] == []
        for packet in packets["sources"]:
            n = state["sources"].index(packet["source_version"])
            assert packet["body"] == state["bodies"][n]
            assert len(packet["paragraphs"]) == 4
        raw = (engine.ledger.artifacts.root / result["scores_artifact"]).read_bytes()
        assert np.frombuffer(raw, dtype="<f4").shape == (144,)
        assert result["presentation"]["markdown"] == retrieval.render(result)
        assert "No date filter or score cutoff" in result["presentation"]["markdown"]
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
    finally:
        engine.close()


def test_exact_reuse_keeps_result_without_ranking_or_loading_vectors_again(tmp_path, monkeypatch):
    engine, _, plan, calls = rag_fixture(tmp_path, monkeypatch)
    try:
        first = run(engine, plan)

        def forbidden_rank(*args, **kwargs):
            pytest.fail("Exact cache reuse must not rerank or inspect saved source text")

        monkeypatch.setattr(retrieval, "rank_saved_vectors", forbidden_rank)
        monkeypatch.setattr(retrieval, "_saved_text", forbidden_rank)
        again = run(engine, plan)
        assert again["id"] == first["id"] and again["rows"] == first["rows"]
        assert again["text"] == first["text"] and len(calls) == 1
        assert again["presentation"]["markdown"] == first["presentation"]["markdown"]
        with pytest.raises(ResearchError, match="rag_retrieval_frozen_binding_changed"):
            run(engine, plan, top_k=4)
        assert engine.ledger.db.execute(
            "SELECT COUNT(*) FROM records WHERE kind='event_rag_retrieval_manifest'"
        ).fetchone()[0] == 1
    finally:
        engine.close()


def test_missing_nonanchor_vector_remains_partial_with_all_candidate_slots_filled(tmp_path, monkeypatch):
    engine, state, plan, _ = rag_fixture(tmp_path, monkeypatch, missing_target=True)
    try:
        result = run(engine, plan)
        assert result["candidate_slots"] == 36 and result["pending_slots"] == 0
        assert all(row["status"] == "complete" for row in result["rows"])
        assert result["status"] == "partial"
        assert result["missing_vector_sources"] == [state["sources"][13]]
        assert "Missing vectors: 1" in result["presentation"]["markdown"]
        assert result["new_model_calls"] == result["new_embeddings"] == 0
    finally:
        engine.close()


def test_changed_source_hash_stops_before_result_or_presentation_acceptance(tmp_path, monkeypatch):
    engine, state, plan, _ = rag_fixture(tmp_path, monkeypatch)
    try:
        actual_load = retrieval.load_frame

        def changed_metadata(*args):
            inputs = deepcopy(actual_load(*args))
            source = state["sources"][0]
            old_hash = inputs["metadata"][source]["body_sha256"]
            inputs["metadata"][source]["body_sha256"] = "0" * 64
            for row in inputs["frame"]["representatives"]:
                if row["body_sha256"] == old_hash:
                    row["body_sha256"] = "0" * 64
            return inputs

        monkeypatch.setattr(retrieval, "load_frame", changed_metadata)
        with pytest.raises(AuditError, match="rag_retrieval_source_hash_changed"):
            run(engine, plan)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='candidate_run'").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.db.execute(
            "SELECT COUNT(*) FROM records WHERE kind='event_rag_retrieval_manifest'"
        ).fetchone()[0] == 1
    finally:
        engine.close()
