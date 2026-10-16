"""Constructed end-to-end audited preparation, mock Codex dispatch and replay."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import sys

import numpy as np

from newsresearch import luna_validation_gateway as runner
from newsresearch import luna_validation_study as study
from newsresearch.common import Context
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research, audited_handler
from test_luna_lead_answers import answer


def test_audited_prepare_model_policy_capture_and_exact_resume(tmp_path, monkeypatch):
    state = {}

    class FixtureResearch(Research):
        @audited_handler
        def _status(self, session, context, data):
            def register(kind, content):
                return self._version(session, context, {"kind": kind, "key": "constructed-" + kind, "content": content})["id"]
            versions = {"protocol": register("protocol", {"method": "constructed-fixture-only"}),
                "selection": register("selection", {"rules": {"synthetic": True}})}
            body = "Aster announced a model on Monday in Delft.\n\nSecond fixture paragraph.\n\nThird fixture paragraph.\n\nNever supplied fourth paragraph."
            dataset = self._ingest(session, Context(context.objective, context.actor, versions),
                {"articles": [{"source_key": "constructed-" + str(n), "title": "Aster model announcement " + str(n),
                    "body": body, "retention": "permitted", "url": "https://example.test/" + str(n), "synthetic": True} for n in range(3)],
                 "retrieval": {"source": "constructed-fixture", "retrieved_at": "2026-01-01T00:00:00Z", "parameters": {}}})
            versions["dataset"] = dataset["id"]
            sources = self.ledger.get(dataset["id"], "dataset")["source_versions"]
            metadata = {s: {"source_version": s, "title": "Aster model announcement", "url": "https://example.test/a",
                "published_at": None, "body_sha256": hashlib.sha256(body.encode()).hexdigest()} for s in sources}

            def save(value, binary=False):
                ref = self.ledger.artifacts.put_bytes(value) if binary else self.ledger.artifacts.put(value)
                self.ledger.append(session, "preparation.artifact.saved", {"artifact": ref, "purpose": "Constructed input fixture"})
                return ref

            index = self.ledger.record(session, "vector_index", "constructed-index", {"versions": versions, "dimensions": 3})
            plan = {"index": index, "mapping_artifact": save([{"source_version": s} for s in sources]),
                "pooled_vectors_artifact": save(np.eye(3, dtype="<f4").tobytes(), True), "metadata_artifact": save(metadata)}
            group_artifact = save([{"group_id": "g", "members": sources[:2]}, {"group_id": "s", "members": sources[2:]}])
            group = self.ledger.record(session, "event_group_refinement_result", "constructed-groups",
                {"plan": "constructed-original-plan", "rule": {"publication_gap_days": 7}, "adopted": True,
                 "exports": {"groups": {"artifact": group_artifact}}})
            state.update(group=group, original=plan, sources=sources)
            return {"constructed": True}

    engine = FixtureResearch(tmp_path / "audit")
    try:
        engine.execute("status", objective="Create source-free integration fixture", actor="test")
        monkeypatch.setattr(study, "GROUP_RESULT", state["group"])
        monkeypatch.setattr(study, "load_plan", lambda *args: (state["original"], {"representatives": []}, {"rows": []}))
        prepared = engine.execute("luna_group_validation", {"phase": "prepare", "group_result": state["group"],
            "study_key": "constructed-luna-study", "seed": "constructed-seed", "codex_executable": sys.executable},
            objective="Prepare a constructed lead-only study through the real runtime", actor="test")
        assert prepared["workload"]["primary_requests"] == 4
        assert prepared["presentation"]["markdown"] == study.render_plan(prepared)
        for task in prepared["tasks"]:
            request = engine.ledger.artifacts.read(task["request_ref"])
            assert all(a["coverage"]["omitted_paragraphs"] == 1 for a in request["articles"])
            assert "Never supplied fourth" not in str(request)
        calls = []
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CODEX_API_KEY", raising=False)

        def complete(self, invocation):
            calls.append(invocation)
            assert invocation.configured_model == "gpt-6-luna"
            assert 'model_reasoning_effort="low"' in invocation.command
            assert "Never supplied fourth" not in invocation.stdin
            result = answer(invocation.request)
            if invocation.request["mode"] == "anchor":
                result.update(group_label="uncertain", partitions=[], relations=[
                    {"source_version": a["source_version"], "label": "same_event"}
                    for a in invocation.request["articles"] if a["source_version"] != invocation.request["anchor_source"]])
            return ProviderResponse(result, "synthetic-transport", None, raw_response={"fixture": True})

        monkeypatch.setattr(runner.LunaProvider, "complete_prepared", complete)
        approval = {"method": "luna-validation-run-approval-v1", "plan": prepared["id"],
            "study_key": prepared["study_key"], "approved_by": "test:constructed", "instruction": "Only mock HTTP-free software verification",
            "allow_codex_account_execution": True, "allow_external_processing": True,
            "max_requests": 400, "max_article_exposures": 6000, "max_retries": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
        engine.config = replace(engine.config, offline=False)
        data = {"phase": "execute", "plan": prepared["id"], "study_key": prepared["study_key"],
            "run_approval": approval, "reuse_cache": True, "workers": 4}
        result = engine.execute("luna_group_validation", data, objective="Exercise the real ledger/gateway with a synthetic provider", actor="test")
        assert result["status"] == "complete" and len(calls) == 4
        assert result["workflow_article_exposures"] == 11
        assert result["presentation"]["markdown"] == runner.render_result(result)
        again = engine.execute("luna_group_validation", data, objective="Verify exact audited result reuse", actor="test")
        assert len(calls) == 4 and again["workflow_article_exposures"] == 11
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
    finally:
        engine.close()
