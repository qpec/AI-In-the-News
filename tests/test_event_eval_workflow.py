"""Real runtime/ledger integration using invented sources and a fake CLI runner.

These checks never open a research workspace, execute Codex, or infer real events.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from threading import Lock
from types import SimpleNamespace

import pytest

from newsresearch.common import Config, Context, ResearchError
from newsresearch.event_eval_math import build_pair_design, pair_id
from newsresearch.event_eval_provider import PairProvider
from newsresearch import event_eval_provider
from newsresearch import event_eval_workflow as workflow
from newsresearch.luna_lead_answers import build_request as old_request, make_lead
from newsresearch.runtime import audited_handler


SIZES = {"within_group": 3, "between:retrieved": 2, "between:random_tail": 1}
SEED = "synthetic-fixed-pair-sample"


class FixtureResearch(workflow.EventEvaluationResearch):
    @audited_handler
    def _status(self, session, context, data):
        """Construct fictional immutable historical inputs inside an audited call."""
        if data.get("fixture") == "reserve-unknown":
            dispatch = workflow.save(self, session, {"synthetic_prior_invocation": True},
                                     "Fictional unresolved reservation; no process was invoked")
            intended = {"attempt": "fictional-unobserved-prior-attempt", "task_key": "different-prior-task-key",
                        "number": 1, "request": data["request"], "dispatch": dispatch,
                        "source_versions": [data["source"]], "article_exposures": 1,
                        "synthetic_fixture_only": True}
            self.ledger.append(session, "model.attempt.intended", intended)
            self.ledger.unresolved[intended["attempt"]] = intended
            return {"attempt": intended["attempt"]}
        if data.get("fixture") != "old-study":
            return super()._status(session, context, data)
        versions = {}
        for kind, content in (("protocol", {"method": "invented-source-fixture"}),
                              ("selection", {"rules": "Twenty fictional sources only"})):
            versions[kind] = self._version(session, context, {
                "kind": kind, "key": "fixture-original", "content": content})["id"]
        dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": [{"source_key": f"invented-{i}", "synthetic": True, "retention": "permitted",
                          "title": f"Invented source {i}", "url": f"https://example.invalid/source/{i}",
                          "body": f"Fictional Aster group {i // 2} announced a model in Delft on Monday. Source number {i}."}
                         for i in range(20)],
            "retrieval": {"source": "synthetic-test", "retrieved_at": "2026-01-01T00:00:00+00:00",
                          "parameters": {"fixture": True}}})
        versions["dataset"] = dataset["id"]
        sources = dataset["sources"]
        groups = {f"fictional-group-{i}": sources[2 * i:2 * i + 2] for i in range(10)}
        membership = {source: group for group, members in groups.items() for source in members}
        candidates = [sources[i] for i in (1, 2, 4, 6)]
        frames = [{"anchor": sources[0], "candidates": [{"candidate": source} for source in candidates]}]
        channels = {"retrieved": [[sources[0], source] for source in candidates]}
        design = build_pair_design(groups, channels, sample_sizes=SIZES, seed=SEED)
        tasks, outcomes = [], {}
        if data.get("unknown_source"):
            source = design["selected_pairs"][0]["left"]
            body = json.loads(self.ledger.db.execute("SELECT payload FROM sources WHERE id=?", (source,)).fetchone()[0])["body"]
            paragraphs = [dict(row) for row in self.ledger.db.execute(
                "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start", (source,))]
            lead = make_lead(source, "Fictional unknown prior source", None, paragraphs)
            assert lead["passages"][0]["text"] == body
            request = workflow.save(self, session, old_request(leads=[lead], versions=versions, mode="article"),
                                    "Fictional retained old request")
            tasks.append({"logical_id": "old-unknown", "mode": "group", "request_ref": request,
                          "source_versions": [source]})
            outcomes["old-unknown"] = {"status": "unknown", "error": "synthetic_unknown"}
        executable = self.ledger.root / "synthetic-codex-never-executed"
        executable.write_bytes(b"This fixture is never executed.")
        config = {"codex_model": "gpt-6-luna", "reasoning_effort": "low", "codex_executable": str(executable),
                  "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                  "timeout_seconds": 180, "max_input_bytes": 262144, "max_output_bytes": 262144}
        old_plan = {"versions": versions, "study_key": "fictional-exhausted-original", "membership": membership,
                    "anchor_frames": frames, "tasks": tasks, "config": config, "group_result": "fictional-frozen-groups"}
        plan_id = self.ledger.record(session, "luna_group_validation_plan", old_plan["study_key"], old_plan)
        old = {"versions": versions, "plan": plan_id, "study_key": old_plan["study_key"], "outcomes": outcomes,
               "task_counts": {"unknown": len(outcomes)}, "workflow_model_attempts": len(outcomes),
               "workflow_article_exposures": len(outcomes)}
        result_id = self.ledger.record(session, "luna_group_validation_result", "fictional-original-result", old)
        return {"old_result": result_id, "old_plan": plan_id, "old_value": old,
                "membership": membership, "sources": sources}


def call(engine, operation, payload=None, versions=None):
    return engine.execute(operation, payload or {}, objective="Synthetic replacement-evaluator integration check",
                          actor="test:fictional-fixture", versions=versions)


def test_composed_new_approval_obeys_canary_stop_and_exact_resume(setup_study, monkeypatch):
    engine, old, plan, policy, _ = setup_study()
    calls, _ = fake_transport(monkeypatch, engine, plan, old["membership"], invalid_call=1)
    payload = {"phase": "approve_pairs", "plan": plan["id"], "study_key": plan["study_key"],
               "approval": policy, "reuse_cache": True}
    first = call(engine, "luna_group_validation", payload)
    assert first["status"] == "partial" and first["workflow_model_attempts"] == 1 and len(calls) == 1
    again = call(engine, "luna_group_validation", payload)
    assert again["workflow_model_attempts"] == 1 and len(calls) == 1
    engine.ledger.verify()


@pytest.fixture
def setup_study(tmp_path):
    engines = []
    def create(*, unknown_source=False):
        engine = FixtureResearch(tmp_path / f"store-{len(engines)}", config=Config(offline=False))
        engines.append(engine)
        old = call(engine, "status", {"fixture": "old-study", "unknown_source": unknown_source})
        prepared = call(engine, "luna_group_validation", {
            "phase": "prepare_pairs", "original_result": old["old_result"],
            "study_key": "fictional-replacement", "seed": SEED, "sample_sizes": SIZES})
        policy = {"method": workflow.APPROVAL_METHOD, "plan": prepared["id"], "study_key": prepared["study_key"],
                  **prepared["limits"], "allow_codex_account_execution": True, "allow_external_processing": True,
                  "approved_by": "test:fictional-operator", "instruction": "Synthetic fake-provider test only",
                  "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}
        approval = call(engine, "version", {"kind": "policy", "key": "fictional-approval", "content": policy})["id"]
        execution = {"phase": "execute_pairs", "plan": prepared["id"], "study_key": prepared["study_key"],
                     "approval_policy": approval, "reuse_cache": True}
        return engine, old, prepared, policy, execution
    yield create
    for engine in engines:
        engine.close()


def fake_transport(monkeypatch, engine, plan, membership, *, invalid_call=None):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    calls, batches = [], []
    lock = Lock()
    canaries = {task["pair_id"] for task in plan["tasks"] if task["phase"] == "canary"}
    def runner(*args, **kwargs):
        prompt = json.loads(kwargs["input"])
        left, right = [article["source_version"] for article in prompt["articles"]]
        identifier = pair_id(left, right)
        with lock:
            calls.append({"pair_id": identifier, "phase": "canary" if identifier in canaries else "evaluation"})
            index = len(calls)
        result = {"label": "same_event" if membership[left] == membership[right] else "different_event",
                  "support_span_ids": ["A1", "B1"], "reason": "Invented fixture response; no actual event inference."}
        if index == invalid_call:
            result["support_span_ids"] = ["A1"]
        events = [{"type": "thread.started"}, {"type": "turn.started"},
                  {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(result)}},
                  {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}]
        return SimpleNamespace(stdout="\n".join(json.dumps(event) for event in events), stderr="", returncode=0)
    def provider(workspace, config):
        return PairProvider(workspace, config, runner=runner)
    monkeypatch.setattr(event_eval_provider, "PairProvider", provider)
    original_dispatch = engine.gateway.codex_dispatch
    def dispatch(session, provider, invocations, workers):
        completed = engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0]
        batches.append({"workers": workers, "size": len(invocations), "completed_before": completed})
        if workers == 4:
            assert completed >= workflow.CANARIES
        yield from original_dispatch(session, provider, invocations, workers)
    monkeypatch.setattr(engine.gateway, "codex_dispatch", dispatch)
    return calls, batches


def assert_exact_presentation(engine, result):
    presentation = result["presentation"]
    assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode("utf-8")
    assert presentation["results"] == [{"kind": "luna_group_validation_result", "id": result["id"]}]
    assert presentation["versions"] == result["versions"]
    assert presentation["status"] == "prepared_for_delivery" and presentation["ui_delivery_verified"] is False


def test_real_runtime_canary_barrier_complete_support_and_exact_resume(setup_study, monkeypatch):
    engine, old, plan, policy, execution = setup_study()
    calls, batches = fake_transport(monkeypatch, engine, plan, old["membership"])
    result = call(engine, "luna_group_validation", execution)
    assert result["status"] == "complete" and result["workflow_model_attempts"] == 10
    assert [row["phase"] for row in calls[:4]] == ["canary"] * 4
    assert [row["phase"] for row in calls[4:]] == ["evaluation"] * 6
    assert [(row["workers"], row["size"]) for row in batches] == [(1, 1)] * 4 + [(4, 4), (4, 2)]
    assert [row["completed_before"] for row in batches[:5]] == [0, 1, 2, 3, 4]
    strata = {row["stratum"]: row for row in plan["design"]["strata"]}
    assert sum(row["N"] for row in strata.values()) == 190
    assert all(row["pi"] > 0 for row in strata.values())
    assert strata["between:random_tail"]["N"] == 177
    assert result["metrics"]["expected_pairs"] == 6
    assert result["metrics"]["counts"]["same_event"] == 3
    assert result["metrics"]["pair_precision"]["point"] == 1
    assert result["metrics"]["pair_recall"]["point"] == 1
    assert result["metrics"]["pair_recall"]["confidence_interval"]["lower"] < 1
    assert result["metrics"]["whole_group_purity"] is None
    assert_exact_presentation(engine, result)
    resumed = call(engine, "luna_group_validation", execution)
    assert len(calls) == 10 and resumed["workflow_model_attempts"] == 10
    assert resumed["workflow_article_exposures"] == 20 and resumed["automatic_retries"] == 0
    assert engine.ledger.get(old["old_result"], "luna_group_validation_result") == old["old_value"]
    engine.ledger.verify()


@pytest.mark.parametrize("invalid_call,expected_attempts", [(1, 1), (5, 8)])
def test_first_invalid_latches_resume_and_retains_entire_inflight_block(
        setup_study, monkeypatch, invalid_call, expected_attempts):
    engine, old, plan, policy, execution = setup_study()
    calls, batches = fake_transport(monkeypatch, engine, plan, old["membership"], invalid_call=invalid_call)
    result = call(engine, "luna_group_validation", execution)
    assert len(calls) == result["workflow_model_attempts"] == expected_attempts
    assert result["outcome_counts"]["invalid"] == 1
    assert sum(result["outcome_counts"].values()) == expected_attempts
    assert result["pending"] == 10 - expected_attempts
    assert result["status"] == "partial" and result["metrics"]["pair_recall"]["point"] is None
    if invalid_call == 1:
        assert all(row["workers"] == 1 for row in batches)
    else:
        assert batches[-1]["workers"] == 4 and result["outcome_counts"]["valid"] == 7
    resumed = call(engine, "luna_group_validation", execution)
    assert len(calls) == expected_attempts
    assert resumed["workflow_model_attempts"] == expected_attempts
    assert "latched" in resumed["obstacle"]
    replacement = call(engine, "version", {"kind": "policy", "key": "replacement-approval",
                       "content": {**policy, "approved_by": "test:changed-actor"}})["id"]
    with pytest.raises(ResearchError, match="approval_cannot_reset_budget"):
        call(engine, "luna_group_validation", {**execution, "approval_policy": replacement})
    assert len(calls) == expected_attempts
    assert_exact_presentation(engine, result)
    engine.ledger.verify()


def test_prior_unknown_sources_stay_null_and_old_approval_cannot_authorize_new_study(setup_study, monkeypatch):
    engine, old, plan, policy, execution = setup_study(unknown_source=True)
    assert plan["quarantined_source_versions"]
    quarantined = set(plan["quarantined_source_versions"])
    excluded = [task for task in plan["tasks"] if task["status"] == "quarantined_unknown_source"]
    assert excluded and all(task["phase"] == "evaluation" and task["request"] is None for task in excluded)
    old_approval = call(engine, "version", {"kind": "policy", "key": "old-approval",
        "content": {**policy, "method": "luna-validation-run-approval-v1", "plan": old["old_plan"],
                    "study_key": "fictional-exhausted-original", "max_requests": 400, "max_article_exposures": 6000}})["id"]
    with pytest.raises(ResearchError, match="new_plan_bound_approval_required"):
        call(engine, "luna_group_validation", {**execution, "approval_policy": old_approval})
    calls, batches = fake_transport(monkeypatch, engine, plan, old["membership"])
    result = call(engine, "luna_group_validation", execution)
    allowed = {task["pair_id"] for task in plan["tasks"] if task["status"] == "prepared"}
    assert {row["pair_id"] for row in calls} == allowed
    assert all(not ({task["left"], task["right"]} & quarantined)
               for task in plan["tasks"] if task["pair_id"] in allowed)
    assert result["outcome_counts"]["unavailable"] == len(excluded)
    assert result["metrics"]["complete_references"] is False
    assert result["metrics"]["pair_recall"]["point"] is None
    assert result["metrics"]["counts"]["unknown"] == len(excluded)
    assert result["workflow_article_exposures"] == 2 * len(allowed)
    assert engine.ledger.get(old["old_result"], "luna_group_validation_result") == old["old_value"]
    assert_exact_presentation(engine, result)
    engine.ledger.verify()


def test_unresolved_source_from_another_task_key_blocks_canary_and_evaluation(setup_study, monkeypatch):
    engine, old, plan, policy, execution = setup_study()
    first = next(task for task in plan["tasks"] if task["phase"] == "canary")
    prior = call(engine, "status", {"fixture": "reserve-unknown", "source": first["left"],
                                    "request": first["request"]})
    calls, batches = fake_transport(monkeypatch, engine, plan, old["membership"])
    result = call(engine, "luna_group_validation", execution)
    assert calls == []
    assert result["status"] == "partial" and result["workflow_model_attempts"] == 0
    assert result["outcomes"][first["pair_id"]]["label"] == "unknown"
    assert result["metrics"]["pair_recall"]["point"] is None
    assert prior["attempt"] in engine.ledger.unresolved
    resumed = call(engine, "luna_group_validation", execution)
    assert calls == [] and resumed["workflow_model_attempts"] == 0
    assert_exact_presentation(engine, result)
    engine.ledger.verify()
