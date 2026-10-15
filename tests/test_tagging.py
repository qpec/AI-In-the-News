from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import pytest

from newsresearch import tag_gateway, tagging
from newsresearch.common import AuditError, Context, ResearchError, canonical, utc
from newsresearch.demo import baseline, source
from newsresearch.embeddings import EmbeddingHTTPResponse
from newsresearch.runtime import Research


def register(engine: Research, kind: str, content: dict[str, Any]) -> str:
    return engine.execute("version", {"kind": kind, "key": "tag-test-" + kind, "content": content},
                          objective="Register a synthetic software-test method", actor="test")["id"]


def setup(engine: Research, *, segment: int = 1000, evaluation_change: Any = None) -> tuple[Any, ...]:
    versions = baseline(engine, "test")
    versions["question"] = register(engine, "question", {"query": "fictional outage", "text": "Relevant to the fictional outage?"})
    versions["codebook"] = register(engine, "codebook", {"method": tagging.METHOD, "tag": "fixture_outage",
                                    "labels": ["yes", "no"], "definition": "Synthetic fixture relevance"})
    versions["retrieval_profile"] = register(engine, "retrieval_profile", {
        "method": tagging.METHOD, "aggregation": "max_segment_score", "segment_characters": segment,
        "overlap_characters": 3, "related_sources": 1})
    versions["model_profile"] = register(engine, "model_profile", {
        "method": "openai-responses-tags-v1", "provider": "openai", "model": "fixture-2026-01-01",
        "context_window_tokens": 100000, "max_output_tokens": 1000,
        "usd_per_million_input_tokens": "1", "usd_per_million_output_tokens": "2",
        "pricing_source": "synthetic fixture; not a real price", "price_checked_on": "2026-01-01"})

    def run(op: str, data: dict[str, Any] | None = None) -> Any:
        return engine.execute(op, data or {}, objective="Test corpus-wide tagging invariants", actor="test", versions=versions)

    dataset = run("ingest", {"articles": [source("a", "High support in first report."),
        source("b", "Low support in second report."), source("c", "High support in held-out report."),
        source("d", "Low support in held-out report."), source("empty", ""),
        source("long", "Low initial discussion.\n\n" + "Background. " * 10 + "High final evidence."),
        source("unrelated", "Outside nearest search results.")],
        "retrieval": {"source": "synthetic fixture", "retrieved_at": utc(), "parameters": {}}})
    versions["dataset"] = dataset["id"]
    gold = {"method": "query-tag-calibration-v1", "priority": "balanced", "minimum_per_class_per_split": 1,
            "minimum_test_precision": 0.8, "minimum_test_recall": 0.8, "items": [
                {"source_version": source_id, "split": "calibration" if n < 2 else "test",
                 "group": str(n), "relevant": n % 2 == 0, "reviewer": "test:synthetic",
                 "reviewer_type": "human", "reason": "Developer-visible synthetic label"}
                for n, source_id in enumerate(dataset["sources"][:4])]}
    if evaluation_change:
        evaluation_change(gold)
    versions["evaluation"] = register(engine, "evaluation", gold)
    retrieved = run("tag_retrieve")
    plan = run("plan_tags", {"retrieval": retrieved["id"]})
    return versions, run, dataset, retrieved, plan


@pytest.fixture
def tagged(engine: Research) -> tuple[Any, ...]:
    return (engine, *setup(engine))


def approval(engine: Research, planned: dict[str, Any], **changes: Any) -> str:
    return register(engine, "policy", {"method": "tag-run-approval-v1", "plan": planned["id"],
        "approved_by": "test:synthetic", "allow_paid_inference": True, "allow_external_processing": True,
        "max_estimated_cost_usd": "100", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), **changes})


def transport(engine: Research, monkeypatch: Any, mutate: Any = None) -> list[Any]:
    sent: list[Any] = []
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key-no-real-access")

    def send(self: Any, body: bytes, client_request_id: str) -> EmbeddingHTTPResponse:
        assert engine.ledger.db.execute(
            "SELECT 1 FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.attempt')=?",
            (client_request_id,)).fetchone()
        request = json.loads(body)
        assert canonical(request).encode() == body
        target = json.loads(request["input"])["target"]
        assert "evaluation" not in json.loads(request["input"])
        assert "reviewer" not in request["input"]
        excerpts = target["excerpts"]
        positive = next((e for e in excerpts if "High" in e["text"]), None)
        excerpt = positive or excerpts[0]
        result = {"score": 0.9 if positive else 0.2, "explanation": "Synthetic scripted output",
                  "inspected_excerpt_ids": [e["id"] for e in excerpts], "citations": [{
                      "excerpt_id": excerpt["id"], "quote": excerpt["text"], "start": 0, "end": len(excerpt["text"])}]}
        parsed = {"id": "synthetic-response", "model": request["model"], "status": "completed",
                  "usage": {"input_tokens": 100, "output_tokens": 20}, "output": [{"type": "message",
                      "content": [{"type": "output_text", "text": json.dumps(result)}]}]}
        sent.append(target)
        if mutate:
            mutate(parsed, result, target)
        return EmbeddingHTTPResponse(json.dumps(parsed).encode(), 200, "synthetic-request")

    monkeypatch.setattr(tag_gateway.OpenAITagTransport, "send", send)
    return sent


def execute_all(fixture: Any, monkeypatch: Any, **payload: Any) -> tuple[Any, Any]:
    engine, versions, run, dataset, retrieved, plan = fixture
    sent = transport(engine, monkeypatch)
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    result = run("tag", {"plan": plan["id"], "approval_policy": policy, "max_requests": plan["requests"], **payload})
    return result, sent


def test_every_article_including_nonmatches_and_missing_text_is_planned(tagged: Any) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    record = run("tag_inspect", {"id": retrieved["id"]})["record"]
    assert record["source_ids"] == dataset["sources"]
    assert len(record["sources"]) == plan["expected_sources"] == 7
    assert plan["unprocessed_sources"] == [dataset["sources"][4]]
    assert plan["requests"] == 6
    assert plan["network_calls"] == plan["model_calls"] == 0
    with pytest.raises(ResearchError, match="filters"):
        run("tag_retrieve", {"source_ids": [dataset["sources"][0]]})


def test_segmentation_covers_every_character_and_no_partial_article_score(engine: Research, monkeypatch: Any) -> None:
    fixture = (engine, *setup(engine, segment=30))
    _, versions, run, dataset, retrieved, plan = fixture
    record = engine.ledger.get(retrieved["id"], "tag_retrieval")
    coverage: dict[str, set[int]] = {}
    for item in record["packets"]:
        packet = engine.ledger.artifacts.read(item["packet_ref"])
        for excerpt in packet["excerpts"]:
            coverage.setdefault(excerpt["passage_id"], set()).update(range(excerpt["start"], excerpt["end"]))
    for row in engine.ledger.db.execute("SELECT id,text FROM passages"):
        assert coverage[row["id"]] == set(range(len(row["text"])))
    partial, sent = execute_all(fixture, monkeypatch, max_requests=1)
    assert len(sent) == 1
    scores = run("tag_review_queue", {"run": partial["id"]})["articles"]
    assert all(a["score"] is None for a in scores if a["completed_segments"] < a["expected_segments"])
    assert next(a for a in scores if a["source_version"] == dataset["sources"][4])["score"] is None


def test_gateway_resume_calibration_binary_tags_and_audit(tagged: Any, monkeypatch: Any) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    completed, sent = execute_all(tagged, monkeypatch)
    with pytest.raises(ResearchError, match="reuse_cache"):
        run("tag", {"plan": plan["id"], "approval_policy": completed["approval_policy"]})
    resumed = run("tag", {"plan": plan["id"], "approval_policy": completed["approval_policy"], "reuse_cache": True})
    assert resumed["requests_sent"] == 0 and len(sent) == 6
    assert not resumed["missing_task_keys"]
    calibration = run("tag_calibrate", {"run": resumed["id"]})
    assert calibration["threshold"] == 0.9 and calibration["passed"]
    assert calibration["test"]["precision"] == calibration["test"]["recall"] == 1
    applied = run("tag_apply", {"run": resumed["id"], "calibration": calibration["id"]})
    assert applied["expected_articles"] == 7 and applied["processed_articles"] == 6 and applied["missing_articles"] == 1
    labels = run("tag_inspect", {"id": applied["id"]})["record"]["articles"]
    assert [a["value"] for a in labels] == [True, False, True, False, None, True, False]
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert not engine.ledger.verify()["unresolved_model_attempts"]


@pytest.mark.parametrize("fault", ["offline", "no_policy", "wrong_plan", "expired", "budget", "changed_code"])
def test_execution_guards_send_nothing(tagged: Any, monkeypatch: Any, fault: str) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    sent = transport(engine, monkeypatch)
    if fault != "offline":
        engine.config = replace(engine.config, offline=False)
    changes = {"plan": "other"} if fault == "wrong_plan" else {}
    if fault == "expired":
        changes["expires_at"] = "2000-01-01T00:00:00+00:00"
    if fault == "budget":
        changes["max_estimated_cost_usd"] = "0.001"
    policy = approval(engine, plan, **changes)
    payload = {"plan": plan["id"], "approval_policy": policy}
    if fault == "no_policy":
        payload.pop("approval_policy")
    if fault == "changed_code":
        monkeypatch.setattr(tag_gateway, "implementation", lambda _: "different")
    if fault == "budget":
        result = run("tag", payload)
        assert len(result["missing_task_keys"]) == plan["requests"]
    else:
        with pytest.raises(ResearchError):
            run("tag", payload)
    assert not sent


@pytest.mark.parametrize("fault", ["citation", "offset", "missing_inspection", "nonfinite", "refusal", "incomplete", "model"])
def test_invalid_outputs_are_preserved_and_stop_the_batch(tagged: Any, monkeypatch: Any, fault: str) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged

    def mutate(parsed: Any, result: Any, target: Any) -> None:
        if fault == "citation":
            result["citations"][0]["excerpt_id"] = "related-context-not-target"
        if fault == "offset":
            result["citations"][0]["end"] -= 1
        if fault == "missing_inspection":
            result["inspected_excerpt_ids"] = []
        if fault == "nonfinite":
            result["score"] = float("nan")
        parsed["output"][0]["content"][0]["text"] = json.dumps(result)
        if fault == "refusal":
            parsed["output"][0]["content"] = [{"type": "refusal", "refusal": "synthetic"}]
        if fault == "incomplete":
            parsed["status"] = "incomplete"
        if fault == "model":
            parsed["model"] = "unexpected"

    sent = transport(engine, monkeypatch, mutate)
    engine.config = replace(engine.config, offline=False)
    result = run("tag", {"plan": plan["id"], "approval_policy": approval(engine, plan), "max_requests": plan["requests"]})
    assert len(sent) == 1 and result["items"][0]["status"] == "invalid"
    assert all(item["result"] is None for item in result["items"])
    assert engine.ledger.db.execute("SELECT response_ref FROM attempts").fetchone()[0]
    assert not engine.ledger.verify()["unresolved_model_attempts"]


def test_unknown_outcome_blocks_retry_and_reserves_cost(tagged: Any, monkeypatch: Any) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    transport(engine, monkeypatch)

    def timeout(*args: Any) -> Any:
        raise TimeoutError("Synthetic timeout")

    monkeypatch.setattr(tag_gateway.OpenAITagTransport, "send", timeout)
    engine.config = replace(engine.config, offline=False)
    payload = {"plan": plan["id"], "approval_policy": approval(engine, plan)}
    with pytest.raises(ResearchError, match="unknown"):
        run("tag", payload)
    assert len(engine.ledger.verify()["unresolved_model_attempts"]) == 1
    with pytest.raises(ResearchError, match="Unknown"):
        run("tag", payload)


@pytest.mark.parametrize("stage", ["intent", "response"])
def test_audit_failure_stops_before_more_calls(tagged: Any, monkeypatch: Any, stage: str) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    sent = transport(engine, monkeypatch)
    engine.config = replace(engine.config, offline=False)
    policy = approval(engine, plan)
    original = engine.ledger.append

    def fail(session: str, kind: str, payload: Any, projection: Any = None) -> Any:
        if (stage == "intent" and kind == "model.attempt.intended") or (stage == "response" and kind == "tagging.artifact.saved"):
            raise AuditError("Synthetic audit failure")
        return original(session, kind, payload, projection)

    monkeypatch.setattr(engine.ledger, "append", fail)
    with pytest.raises(AuditError):
        run("tag", {"plan": plan["id"], "approval_policy": policy, "max_requests": plan["requests"]})
    assert len(sent) == (1 if stage == "response" else 0)


def test_calibration_does_not_tune_on_heldout_labels(engine: Research, monkeypatch: Any) -> None:
    def change(gold: Any) -> None:
        for item in gold["items"][2:]:
            item["relevant"] = not item["relevant"]

    fixture = (engine, *setup(engine, evaluation_change=change))
    completed, _ = execute_all(fixture, monkeypatch)
    run = fixture[2]
    calibration = run("tag_calibrate", {"run": completed["id"]})
    assert calibration["threshold"] == 0.9 and not calibration["passed"]
    with pytest.raises(ResearchError, match="held-out"):
        run("tag_apply", {"run": completed["id"], "calibration": calibration["id"]})


def test_evaluation_group_leakage_is_rejected(engine: Research, monkeypatch: Any) -> None:
    fixture = (engine, *setup(engine, evaluation_change=lambda g: g["items"][2].update(group="0")))
    completed, _ = execute_all(fixture, monkeypatch)
    with pytest.raises(ResearchError, match="leaks"):
        fixture[2]("tag_calibrate", {"run": completed["id"]})


def test_missing_calibration_processing_is_not_negative(tagged: Any, monkeypatch: Any) -> None:
    completed, _ = execute_all(tagged, monkeypatch, max_requests=1)
    with pytest.raises(ResearchError, match="fully processed"):
        tagged[2]("tag_calibrate", {"run": completed["id"]})


def test_human_review_corrections_append_and_do_not_accept_incidents(tagged: Any, monkeypatch: Any) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    completed, _ = execute_all(tagged, monkeypatch)
    payload = {"run": completed["id"], "source_version": dataset["sources"][0],
               "reviewer_type": "human", "relevant": True, "reason": "Synthetic review"}
    reviewed = run("tag_review", payload)
    with pytest.raises(ResearchError, match="supersede"):
        run("tag_review", {**payload, "relevant": False})
    correction = run("tag_review", {**payload, "relevant": False, "supersedes": reviewed["id"]})
    assert correction["supersedes"] == reviewed["id"]
    assert engine.ledger.get(reviewed["id"], "tag_review")["relevant"] is True
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0


def test_handlers_require_runtime(engine: Research) -> None:
    with pytest.raises(AuditError):
        tagging.retrieve(engine, "not-a-session", Context("test", "test"), {})
    with pytest.raises(AuditError):
        tag_gateway.execute(engine, "not-a-session", Context("test", "test"), {})


def test_single_operation_setup_saves_bound_context_without_network(tagged: Any, monkeypatch: Any) -> None:
    engine, versions, run, dataset, retrieved, plan = tagged
    sent = transport(engine, monkeypatch)
    result = engine.execute("tag_setup", {"study": {
        "query": "second query", "question": "A distinct question?", "tag": "second_tag",
        "definition": "A distinct registered definition",
        "model_profile": engine.ledger.get(versions["model_profile"], "model_profile")["content"],
        "evaluation": engine.ledger.get(versions["evaluation"], "evaluation")["content"],
    }}, versions={"dataset": dataset["id"]}, objective="Test offline setup wrapper", actor="test")
    assert result["expected_sources"] == 7 and not sent
    assert engine.ledger.artifacts.read(result["context_artifact"]) == {"versions": result["versions"]}
    assert result["versions"]["question"] != versions["question"]
    prepared = engine.ledger.get(result["id"], "tag_plan")
    body = engine.ledger.artifacts.read(prepared["items"][0]["request_ref"])["body"]
    assert json.loads(body["input"])["task"]["query"] == "second query"
    assert not engine.ledger.verify()["unresolved_model_attempts"]
