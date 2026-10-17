"""Synthetic audited extraction preparation/execution; no corpus or model calls."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.event_extraction_contract import validate_output
from newsresearch.event_extraction_provider import ExtractionProvider
from newsresearch.event_extraction_workflow import EventExtractionResearch, render_plan
from newsresearch import event_extraction_workflow as workflow
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import audited_handler
from test_event_extraction import event


OBJECTIVE = "Verify synthetic saved-text extraction invariants, without external execution"
FIRST = "Aster announced Model V2 in Delft on 2026-01-02."


def run(engine, data):
    return engine.execute("luna_group_validation", data, objective=OBJECTIVE, actor="test:synthetic")


def fixture(tmp_path, monkeypatch, *, unavailable=False, short_frame=False, prepare=True):
    """Register sources and a minimal historical owner/frame under real preflight."""
    state = {}
    executable = tmp_path / "synthetic-codex-never-executed.txt"
    executable.write_text("Synthetic executable identity only; never executed.", encoding="utf-8")

    class FixtureResearch(EventExtractionResearch):
        @audited_handler
        def _status(self, session, context, data):
            def version(kind, content):
                return self._version(session, context, {
                    "kind": kind, "key": "extraction-fixture-" + kind, "content": content})["id"]

            versions = {"protocol": version("protocol", {"method": "synthetic-integration-fixture"}),
                        "selection": version("selection", {"rules": {"synthetic": True}})}
            bodies = [FIRST + f"\n\nSynthetic detail {n}.\n\nThird paragraph {n}."
                      f"\n\nFinal paragraph {n}, preserved beyond lead-only evidence." for n in range(14)]
            if unavailable:
                bodies[8] = ""
                bodies[9] += "\n\n" + "Long synthetic retained text. " * 6000
            articles = [{"source_key": f"fixture-{n}", "title": f"Synthetic article {n}",
                         "body": body, "retention": "permitted", "synthetic": True,
                         "url": f"https://example.test/extraction/{n}",
                         "published_at": "2026-01-03T12:00:00Z"}
                        for n, body in enumerate(bodies)]
            dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
                "articles": articles,
                "retrieval": {"source": "synthetic-integration-fixture", "parameters": {},
                              "retrieved_at": "2026-01-04T00:00:00Z"}})
            versions["dataset"] = dataset["id"]
            sources = dataset["sources"]
            metadata = {source: {"body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
                        for source, body in zip(sources, bodies, strict=True)}
            frame = {"representatives": [{"body_sha256": metadata[source]["body_sha256"],
                                           "fold": "validation" if n == 12 else "development"}
                                          for n, source in enumerate(sources)]}

            def artifact(value):
                reference = self.ledger.artifacts.put(value)
                self.ledger.append(session, "preparation.artifact.saved", {
                    "artifact": reference, "purpose": "Synthetic owner/frame fixture only"})
                return reference

            pair_plan = self.ledger.record(session, "event_pair_plan", "synthetic-original-frame", {
                "metadata_artifact": artifact(metadata), "frame_artifact": artifact(frame), "versions": versions})
            group_result = self.ledger.record(session, "event_group_refinement_result", "synthetic-groups", {
                "plan": pair_plan, "rule": {"publication_gap_days": 7}, "versions": versions})
            membership = {source: f"group-{n // 2}" if n < 8 else f"singleton-{n}"
                          for n, source in enumerate(sources)}
            if short_frame:
                membership = {source: group for source, group in membership.items()
                              if source in {sources[n] for n in (0, 1, 2, 3, 8, 9, 12, 13)}}
            old_plan = self.ledger.record(session, "luna_group_validation_plan", "synthetic-prior-plan", {
                "study_key": "synthetic-prior-study", "versions": versions, "group_result": group_result,
                "membership": membership, "config": {"codex_executable": str(executable)},
                "tasks": [{"logical_id": "prior-unresolved", "source_versions": [sources[13]]}]})
            original = self.ledger.record(session, "luna_group_validation_result", "synthetic-prior-result", {
                "plan": old_plan, "outcomes": {"prior-unresolved": {"status": "unknown"}}})
            self.ledger.record(session, "study_execution_ownership", "synthetic-prior-study", {
                "status": "imported_owner", "owner_workspace": str(self.ledger.root.resolve())})
            state.update(sources=sources, bodies=bodies, original=original, membership=membership)
            return {"synthetic": True}

    engine = FixtureResearch(tmp_path / "protected-audit")
    engine.execute("status", objective=OBJECTIVE, actor="test:synthetic")

    def forbid_embeddings(*args, **kwargs):
        pytest.fail("Saved-text extraction must not prepare or execute embeddings")

    for name in ("embed", "plan_embeddings", "plan_query_embedding"):
        monkeypatch.setattr(engine.gateway, name, forbid_embeddings)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    data = {"phase": "prepare", "original_result": state["original"],
            "study_key": "synthetic-saved-text-pilot", "seed": "synthetic-extraction-seed"}
    plan = run(engine, data) if prepare else None
    return engine, state, plan, data


def approval(plan):
    return {"method": "event-extraction-run-approval-v1", "plan": plan["id"],
            "study_key": plan["study_key"], "approved_by": "test:synthetic",
            "instruction": "Synthetic software verification only; never start a real subprocess or model",
            "allow_codex_account_execution": True, "allow_external_processing": True,
            "max_requests": 12, "max_article_exposures": 12, "max_retries": 0,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}


def answer(request):
    item = event()
    passage = request["evidence"][0]["id"]

    def source_claims(value):
        if isinstance(value, dict):
            if "passage_id" in value:
                value["passage_id"] = passage
            for child in value.values():
                source_claims(child)
        elif isinstance(value, list):
            for child in value:
                source_claims(child)

    source_claims(item)
    result = {"source_version": request["source"]["source_version"], "status": "events_found",
              "inspected_passage_ids": [p["id"] for p in request["evidence"]],
              "coverage_complete": True, "limitation": None, "events": [item]}
    validate_output(result, request)
    return result


def install_transport(engine, monkeypatch, plan, failure=None):
    """Keep the actual shared gateway, exact invocation manifest and provider prep."""
    calls, dispatched = [], []
    actual_dispatch = engine.gateway.codex_dispatch
    task_by_source = {task["source_version"]: task for task in plan["tasks"]}

    def dispatch(session, provider, invocations, workers):
        assert workers == 1 and len(invocations) == 1
        invocation, attempt = invocations[0]
        task = task_by_source[invocation.request["source"]["source_version"]]
        assert attempt in engine.ledger.unresolved
        assert engine.ledger.artifacts.read(task["request"]) == invocation.request
        if task["phase"] == "pilot":
            assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts WHERE status='valid'").fetchone()[0] >= 2
        dispatched.append(task["phase"])
        yield from actual_dispatch(session, provider, invocations, workers)

    def complete(provider, invocation):
        provider._validate_prepared(invocation)
        calls.append(invocation.request["source"]["source_version"])
        assert "preserved beyond lead-only evidence" in invocation.stdin
        output = answer(invocation.request)
        raw = {"synthetic": True, "unknown_outcome": False}
        if failure == "invalid":
            output["source_version"] = "wrong-source"
        elif failure == "unknown":
            output, raw = None, {"synthetic": True, "unknown_outcome": True}
        elif failure == "incomplete":
            output.update(status="insufficient_evidence", coverage_complete=False,
                          limitation="Synthetic incomplete processing")
        return ProviderResponse(output, "synthetic-extraction", "synthetic-model", raw_response=raw)

    monkeypatch.setattr(engine.gateway, "codex_dispatch", dispatch)
    monkeypatch.setattr(ExtractionProvider, "complete_prepared", complete)
    engine.config = replace(engine.config, offline=False)
    return calls, dispatched


def approve_and_run(engine, plan, policy=None):
    return run(engine, {"phase": "approve", "plan": plan["id"], "approval": policy or approval(plan),
                        "reuse_cache": True})


def test_offline_full_text_preparation_and_exact_reuse_excludes_heldout_and_unknown(tmp_path, monkeypatch):
    engine, state, plan, data = fixture(tmp_path, monkeypatch)
    try:
        assert len(plan["tasks"]) == 12 and all(t["status"] == "prepared" for t in plan["tasks"])
        assert plan["selection"]["exclusion_counts"] == {"sealed_held_out_body": 1, "unresolved_prior_attempt": 1}
        assert {t["source_version"] for t in plan["tasks"]} == set(state["sources"][:12])
        assert plan["passage_count"] == 48
        assert plan["body_characters"] == sum(len(body) for body in state["bodies"][:12])
        for task in plan["tasks"]:
            request = engine.ledger.artifacts.read(task["request"])
            n = state["sources"].index(task["source_version"])
            assert request["body"] == state["bodies"][n]
            assert len(request["evidence"]) == 4
        assert plan["new_embeddings"] == plan["new_model_calls"] == 0
        assert plan["model_authorized"] is False and plan["memberships_changed"] is False
        assert plan["presentation"]["markdown"] == render_plan(plan)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='policy'").fetchone()[0] == 0
        again = run(engine, data)
        assert again["id"] == plan["id"] and again["tasks"] == plan["tasks"]
        review = engine.ledger.artifacts.read(plan["review_template_artifact"])
        assert len(review["reviews"]) == 12 and all(row["reviewer"] is None for row in review["reviews"])
    finally:
        engine.close()


def test_missing_and_oversize_sources_are_retained_without_truncation_or_replacement(tmp_path, monkeypatch):
    engine, state, plan, _ = fixture(tmp_path, monkeypatch, unavailable=True)
    try:
        tasks = {task["source_version"]: task for task in plan["tasks"]}
        assert len(tasks) == 12
        assert tasks[state["sources"][8]]["status"] == "source_unavailable"
        oversized = tasks[state["sources"][9]]
        assert oversized["status"] == "oversize"
        request = engine.ledger.artifacts.read(oversized["request"])
        assert request["body"] == state["bodies"][9]
        assert oversized["wire_bytes"] > plan["config"]["max_input_bytes"]
        assert "missing text 1; oversized 1" in plan["presentation"]["markdown"]
    finally:
        engine.close()


def test_interrupted_preparation_keeps_frozen_manifest_versions_and_rejects_redraw(tmp_path, monkeypatch):
    engine, _, _, data = fixture(tmp_path, monkeypatch, prepare=False)
    try:
        original = workflow._source_request
        inspections = []

        def interrupt_once(*args):
            inspections.append(args[2])
            if len(inspections) == 1:
                raise ResearchError("synthetic_preparation_interrupted")
            return original(*args)

        monkeypatch.setattr(workflow, "_source_request", interrupt_once)
        with pytest.raises(ResearchError, match="synthetic_preparation_interrupted"):
            run(engine, data)
        manifests = engine.ledger.db.execute(
            "SELECT id FROM records WHERE kind='event_extraction_preparation_manifest'").fetchall()
        assert len(manifests) == 1
        frozen = engine.ledger.get(manifests[0][0], "event_extraction_preparation_manifest")
        with pytest.raises(ResearchError, match="partial_preparation_binding_changed"):
            run(engine, {**data, "seed": "forbidden-redraw"})
        assert len(inspections) == 1
        plan = run(engine, data)
        assert plan["manifest"] == manifests[0][0]
        assert plan["versions"] == frozen["versions"] and plan["config"] == frozen["config"]
        assert plan["selection_artifact"] == frozen["selection"]
        assert len(plan["tasks"]) == 12 and len(inspections) == 13
        assert engine.ledger.db.execute(
            "SELECT COUNT(*) FROM records WHERE kind='event_extraction_preparation_manifest'").fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    finally:
        engine.close()


def test_gateway_completion_canary_barrier_and_exact_resume(tmp_path, monkeypatch):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        calls, phases = install_transport(engine, monkeypatch, plan)
        policy = approval(plan)
        result = approve_and_run(engine, plan, policy)
        assert result["status"] == "complete" and result["valid"] == 12
        assert result["workflow_model_attempts"] == result["workflow_article_exposures"] == 12
        assert result["pending"] == result["unknown"] == result["invalid"] == result["incomplete"] == 0
        assert result["provisional_event_mentions"] == 12
        assert phases == ["canary"] * 2 + ["pilot"] * 10
        assert len(calls) == len(set(calls)) == 12
        assert result["embeddings_created"] == result["automatic_retries"] == 0
        assert result["memberships_changed"] is False and result["human_validated"] is False
        assert engine.ledger.verify()["unresolved_model_attempts"] == []
        before = deepcopy(result["outcomes"])
        again = approve_and_run(engine, plan, policy)
        assert again["new_attempts"] == 0 and again["cached"] == 12
        assert again["outcomes"] == before and len(calls) == 12
        with pytest.raises(ResearchError, match="approval_cannot_reset_budget"):
            approve_and_run(engine, plan, {**policy, "approved_by": "test:changed-actor"})
        assert len(calls) == 12
    finally:
        engine.close()


def test_short_frozen_frame_reuses_exact_slots_and_never_reports_full_pilot_completion(tmp_path, monkeypatch):
    engine, _, plan, preparation = fixture(tmp_path, monkeypatch, short_frame=True)
    try:
        assert len(plan["tasks"]) == 6 and plan["selection"]["unfilled_slots"] == 6
        again = run(engine, preparation)
        assert again["id"] == plan["id"] and again["tasks"] == plan["tasks"]
        calls, phases = install_transport(engine, monkeypatch, plan)
        policy = approval(plan)
        result = approve_and_run(engine, plan, policy)
        assert result["status"] != "complete"
        assert result["valid"] == result["workflow_model_attempts"] == 6
        assert result["selected_slots"] == result["unfilled_slots"] == result["pending"] == 6
        assert result["expected_slots"] == 12 and result["selected_pending"] == 0
        assert phases == ["canary"] * 2 + ["pilot"] * 4
        assert len(calls) == 6
        resumed = approve_and_run(engine, plan, policy)
        assert len(calls) == 6 and resumed["new_attempts"] == 0 and resumed["status"] != "complete"
    finally:
        engine.close()


@pytest.mark.parametrize("field,value", [("plan", "different-plan"), ("max_requests", 13),
                                         ("max_retries", 1), ("allow_external_processing", False)])
def test_wrong_concrete_approval_never_dispatches(tmp_path, monkeypatch, field, value):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        calls, _ = install_transport(engine, monkeypatch, plan)
        with pytest.raises(ResearchError, match="new_plan_bound_approval_required"):
            approve_and_run(engine, plan, {**approval(plan), field: value})
        assert not calls
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 0
    finally:
        engine.close()


@pytest.mark.parametrize("failure", ["invalid", "unknown", "incomplete", "retention"])
def test_first_failed_or_incomplete_canary_latches_stop_and_resume_spend(tmp_path, monkeypatch, failure):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        calls, phases = install_transport(engine, monkeypatch, plan, failure)
        if failure == "retention":
            original_put = engine.ledger.artifacts.put

            def reject_response(value):
                if isinstance(value, dict) and value.get("provider") == "synthetic-extraction":
                    raise ResearchError("synthetic_response_retention_rejected")
                return original_put(value)

            monkeypatch.setattr(engine.ledger.artifacts, "put", reject_response)
        policy = approval(plan)
        result = approve_and_run(engine, plan, policy)
        assert result["status"] == "partial" and result["pending"] == 11
        assert result["workflow_model_attempts"] == result["workflow_article_exposures"] == 1
        assert phases == ["canary"] and len(calls) == 1
        assert result["valid"] == 0 and result["obstacle"]
        outcome = next(iter(result["outcomes"].values()))
        assert outcome["negative_finding"] is False
        if failure == "retention":
            assert outcome["status"] == "unavailable" and outcome["response"] is None
            assert outcome["error"] == "response_retention_excluded"
        elif failure == "incomplete":
            assert outcome["processing"] == "incomplete"
            assert result["incomplete"] == 1
        else:
            assert outcome["status"] == failure
        again = approve_and_run(engine, plan, policy)
        assert len(calls) == 1 and again["new_attempts"] == 0
        assert again["workflow_model_attempts"] == 1 and again["pending"] == 11
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='event_extraction_stop'").fetchone()[0] >= 1
        assert bool(engine.ledger.verify()["unresolved_model_attempts"]) is (failure == "unknown")
    finally:
        engine.close()


def test_response_audit_failure_stops_before_acceptance_and_restored_resume_never_redispatches(tmp_path, monkeypatch):
    engine, _, plan, _ = fixture(tmp_path, monkeypatch)
    try:
        calls, _ = install_transport(engine, monkeypatch, plan)
        original_put = engine.ledger.artifacts.put

        def fail_response(value):
            if isinstance(value, dict) and value.get("provider") == "synthetic-extraction":
                raise AuditError("synthetic_response_storage_unavailable")
            return original_put(value)

        monkeypatch.setattr(engine.ledger.artifacts, "put", fail_response)
        policy = approval(plan)
        with pytest.raises(AuditError, match="synthetic_response_storage_unavailable"):
            approve_and_run(engine, plan, policy)
        assert len(calls) == 1 and len(engine.ledger.unresolved) == 1
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='event_extraction_assessment'").fetchone()[0] == 0
        monkeypatch.setattr(engine.ledger.artifacts, "put", original_put)
        resumed = approve_and_run(engine, plan, policy)
        assert len(calls) == 1 and resumed["new_attempts"] == 0
        assert resumed["unknown"] == 1 and resumed["pending"] == 11 and resumed["obstacle"]
    finally:
        engine.close()
