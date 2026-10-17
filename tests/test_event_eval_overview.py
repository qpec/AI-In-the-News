"""A single source-free audited integration: unknowns, bindings and exact capture."""
from __future__ import annotations

import hashlib
import json

import pytest

from newsresearch.common import Config, Context, ResearchError
from newsresearch.event_eval_math import build_pair_design, estimate_pair_metrics
from newsresearch.event_eval_overview import (CANDIDATE_PREPARATION_METHOD, FINE_PREPARATION_METHOD, FROZEN_CANDIDATE_TARGET,
    EventEvaluationOverviewResearch, TARGET_METHOD, _target_status)
from newsresearch.event_eval_workflow import METHOD, save
from newsresearch.event_pair_reference import build_request, make_lead, validate_answer
from newsresearch.runtime import audited_handler


class FixtureResearch(EventEvaluationOverviewResearch):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in (("protocol", {"method": "fictional-overview-fixture"}),
                              ("selection", {"rules": "Two invented sources only"})):
            versions[kind] = self._version(session, context, {"kind": kind, "key": "fixture", "content": content})["id"]
        if data.get("candidate"):
            criterion = {**FROZEN_CANDIDATE_TARGET}
            if data.get("invalid_target"):
                criterion["missingness"] = "Drop unresolved references"
            versions["protocol"] = self._version(session, context, {"kind": "protocol", "key": "candidate-preparation",
                "content": {"method": data.get("preparation_method", CANDIDATE_PREPARATION_METHOD), "candidate_result": "fictional-candidate",
                    "original_plan": "fictional-original-plan", "precision_target": criterion}})["id"]
        dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": [{"source_key": name, "title": f"Invented {name}", "synthetic": True,
                "retention": "permitted", "url": f"https://example.invalid/{name}",
                "body": f"Fictional {name} announced an invented model at a synthetic gathering."} for name in ("a", "b")],
            "retrieval": {"source": "synthetic-test", "retrieved_at": "2026-01-01T00:00:00+00:00", "parameters": {}}})
        versions["dataset"] = dataset["id"]
        sources = dataset["sources"]
        leads = []
        for source in sources:
            paragraphs = [dict(row) for row in self.ledger.db.execute(
                "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start", (source,))]
            leads.append(make_lead(source, "Fictional title", None, paragraphs))
        request = build_request(left=leads[0], right=leads[1], versions=versions)
        request_ref = save(self, session, request, "Fictional request; no model called")
        design = build_pair_design({"fictional": sources}, {}, sample_sizes={"within_group": 1}, seed="fictional")
        pair = design["selected_pairs"][0]
        task = {**pair, "left": sources[0], "right": sources[1], "phase": "evaluation", "request": request_ref}
        plan = {"method": METHOD, "versions": versions, "study_key": "fictional", "tasks": [task], "design": design}
        if data.get("candidate"):
            plan.update({"preparation_method": data.get("preparation_method", CANDIDATE_PREPARATION_METHOD),
                "candidate_result": "fictional-candidate", "original_plan": "fictional-original-plan"})
        plan_id = self.ledger.record(session, "luna_group_validation_plan", "fictional", plan)
        answer = {"label": "uncertain", "support_span_ids": ["A1", "B1"], "reason": "Fictional ambiguity only."}
        outcome = {"pair_id": pair["pair_id"], "phase": "evaluation", "request": request_ref,
            "status": "valid", "label": "uncertain", "answer": answer, "validation": validate_answer(request, answer)}
        assessment = self.ledger.record(session, "event_pair_eval_assessment", "fictional", outcome)
        metrics = estimate_pair_metrics(design, [{"pair_id": pair["pair_id"], "label": "uncertain"}], reference_kind="model")
        result = {"method": METHOD, "plan": plan_id, "versions": versions, "study_key": "fictional",
            "outcomes": {pair["pair_id"]: {**outcome, "assessment": assessment}}, "metrics": metrics,
            "status": "complete", "workflow_model_attempts": 1, "workflow_article_exposures": 2,
            "automatic_retries": 0, "obstacle": None}
        result_id = self.ledger.record(session, "luna_group_validation_result", "fictional", result)
        if data.get("candidate"):
            return {"result": result_id, "target_from_plan": True}
        target = self._version(session, context, {"kind": "protocol", "key": "fictional-target",
            "content": {"method": TARGET_METHOD, "frozen_plan": plan_id, "target": .9}})["id"]
        return {"result": result_id, "target_protocol": target}


def test_audited_unknown_stays_unresolved_exact_capture_and_target_binding(tmp_path):
    engine = FixtureResearch(tmp_path / "synthetic-store", config=Config(offline=True))
    try:
        def call(operation, payload):
            return engine.execute(operation, payload, objective="Source-free compact overview test", actor="test:synthetic")
        fixture = call("status", {})
        result = call("luna_group_validation", {"phase": "pair_target_overview", **fixture})
        assert result["target_status"]["status"] == "unresolved"
        assert result["within_counts"]["uncertain"] == 1 and result["pair_precision"]["point"] is None
        assert result["new_model_calls"] == result["new_evaluations"] == 0
        assert result["memberships_changed"] is False
        presentation = result["presentation"]
        encoded = presentation["markdown"].encode("utf-8")
        assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == encoded
        assert hashlib.sha256(encoded).hexdigest() == presentation["content_sha256"]
        assert presentation["results"][-1]["id"] == fixture["result"]
        assert "https://example.invalid/" in presentation["markdown"] and "A1 exact cited prefix" in presentation["markdown"]
        assert presentation["ui_delivery_verified"] is False
        inspected = [json.loads(row[0]) for row in engine.ledger.db.execute(
            "SELECT payload FROM events WHERE kind='event.eval.overview.evidence.inspected'")]
        assert len(inspected) == 1 and len(inspected[0]["passages"]) == 2
        wrong = call("version", {"kind": "protocol", "key": "wrong-target", "content": {
            "method": TARGET_METHOD, "target": .9, "frozen_plan": "different-plan"}})["id"]
        with pytest.raises(ResearchError, match="target_or_result_binding"):
            call("luna_group_validation", {"phase": "pair_target_overview", "result": fixture["result"], "target_protocol": wrong})
        counts = {"total": 32, "same_event": 29, "different_event": 3}
        target = _target_status(counts, {"point": 29 / 32, "confidence_interval": [.7, .99],
            "weighted_missingness_bounds": [29 / 32, 29 / 32]}, .9)
        assert target["status"] == "met_for_model_references" and target["confidence_lower_at_target"] is False
        engine.ledger.verify()
    finally:
        engine.close()


@pytest.mark.parametrize("preparation_method", [CANDIDATE_PREPARATION_METHOD, FINE_PREPARATION_METHOD])
def test_frozen_v2_target_from_plan_exact_criteria_and_presentation(tmp_path, preparation_method):
    engine = FixtureResearch(tmp_path / "synthetic-candidate-store", config=Config(offline=True))
    try:
        def call(operation, payload):
            return engine.execute(operation, payload, objective="Source-free frozen candidate target test", actor="test:synthetic")
        fixture = call("status", {"candidate": True, "preparation_method": preparation_method})
        result = call("luna_group_validation", {"phase": "pair_target_overview", **fixture})
        assert result["target_status"]["status"] == "unresolved"
        assert result["within_counts"]["uncertain"] == 1
        assert result["pair_precision"]["point"] is None
        assert result["target_protocol"] == result["versions"]["protocol"]
        markdown = result["presentation"]["markdown"]
        assert "| Canaries (excluded) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |" in markdown
        assert "| Within-group evaluation | 1 | 0 | 0 | 1 | 0 | 0 | 0 | 0 |" in markdown
        assert "not sampled in this candidate evaluation" in markdown
        assert "A1 exact cited prefix" in markdown and "https://example.invalid/" in markdown
        assert engine.ledger.artifacts.read_bytes(result["presentation"]["content_artifact"]) == markdown.encode("utf-8")
        bad = call("status", {"candidate": True, "invalid_target": True, "preparation_method": preparation_method})
        with pytest.raises(ResearchError, match="frozen_target_binding_invalid"):
            call("luna_group_validation", {"phase": "pair_target_overview", **bad})
        engine.ledger.verify()
    finally:
        engine.close()
