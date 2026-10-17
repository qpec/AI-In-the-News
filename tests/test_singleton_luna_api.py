"""Source-free API fixtures: no key, network, corpus or research labels."""
from __future__ import annotations

import json
import threading

import pytest

from newsresearch.common import AuditError, Config, Context, digest
from newsresearch.embeddings import EmbeddingHTTPResponse
from newsresearch.event_pair_reference import build_request, make_lead
from newsresearch.runtime import audited_handler
from newsresearch.singleton_luna_api import (METHOD, MODEL, STUDY, USER_INSTRUCTION, SingletonResearch,
    classify, implementation, parse_response, sample_singletons, wire_body)


def test_sampling_and_missingness_do_not_manufacture_matches() -> None:
    groups = {f"s{i}": [f"source{i}"] for i in range(150)}
    groups["pair"] = ["paired-a", "paired-b"]
    draw = sample_singletons(groups, "fixed-seed")
    assert len(draw) == len(set(draw)) == 100 and not set(draw) & {"paired-a", "paired-b"}
    assert draw == sample_singletons(groups, "fixed-seed")
    assert draw != sample_singletons(groups, "another-seed")
    assert classify(["same_event", "different_event", "uncertain"]) == "supported_match"
    assert classify(["different_event", "uncertain", "different_event"]) == "uncertain"
    assert classify(["different_event"] * 3) == "unmatched_among_top3"
    assert classify(["same_event", None, "different_event"]) == "incomplete"
    with pytest.raises(Exception):
        parse_response({"model": MODEL, "status": "incomplete", "output": []})


class FixtureResearch(SingletonResearch):
    @audited_handler
    def _status(self, session, context, data):
        versions = {}
        for kind, content in (("protocol", {"method": "fictional-singleton-api-fixture"}),
                              ("selection", {"rules": "103 invented sources, no corpus access"})):
            versions[kind] = self._version(session, context, {"kind": kind, "key": "fixture", "content": content})["id"]
        dataset = self._ingest(session, Context(context.objective, context.actor, versions), {
            "articles": [{"source_key": str(i), "title": f"Fictional source {i}", "synthetic": True, "retention": "permitted",
                          "url": f"https://example.invalid/{i}",
                          "body": f"Fictional source {i} reports an invented launch event at a synthetic location."} for i in range(103)],
            "retrieval": {"source": "synthetic-fixture", "retrieved_at": "2026-10-17T00:00:00+00:00", "parameters": {}}})
        versions["dataset"] = dataset["id"]
        sources = self.ledger.get(dataset["id"], "dataset")["source_versions"]
        leads, metadata = {}, {}
        for source in sources:
            paragraphs = [dict(row) for row in self.ledger.db.execute(
                "SELECT id,source_id,start,end,text,text_hash FROM passages WHERE source_id=? ORDER BY start", (source,))]
            leads[source] = make_lead(source, "Fictional only", None, paragraphs)
            metadata[source] = {"title": "Fictional only", "url": "https://example.invalid/fixture"}
        rows, tasks = [], []
        for source in sources[:100]:
            candidates = []
            for candidate in sources[100:]:
                left, right = sorted((source, candidate))
                request = build_request(left=leads[left], right=leads[right], versions=versions)
                pair = digest([left, right])
                candidates.append({"source": candidate, "pair": pair, "score": .8, "group": "fictional", "group_size": 1})
                tasks.append({"pair": pair, "left": left, "right": right,
                              "request": self.ledger.artifacts.put(request), "body": self.ledger.artifacts.put(wire_body(request)), "status": "prepared"})
            rows.append({"source": source, "inclusion_probability": 100 / 15537, "candidates": candidates})
        plan = {"method": METHOD, "study_key": STUDY, "implementation": implementation(), "versions": versions,
                "rows": rows, "tasks": tasks, "source_metadata": metadata}
        return self.ledger.record(session, "luna_group_validation_plan", STUDY, plan)


class FakeTransport:
    def __init__(self, *, invalid=False):
        self.calls = 0
        self.invalid = invalid
        self.lock = threading.Lock()

    def send(self, body, client_request_id):
        with self.lock:
            self.calls += 1
            call_number = self.calls
        sent = json.loads(body)
        assert sent["model"] == MODEL and sent["store"] is False
        assert "uniqueItems" not in sent["text"]["format"]["schema"]["properties"]["support_span_ids"]
        label = "same_event" if call_number == 1 else "uncertain" if call_number == 2 else "different_event"
        payload = {"label": label, "support_span_ids": ["A1", "B1"], "reason": "Synthetic fixture only."}
        response = {"id": "fictional-response", "model": "wrong" if self.invalid else MODEL, "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(payload)}]}],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}
        return EmbeddingHTTPResponse(json.dumps(response).encode(), 200, "fictional-request")


@pytest.mark.parametrize("invalid", [False, True])
def test_audited_api_exact_intent_results_resume_and_stop(tmp_path, invalid) -> None:
    engine = FixtureResearch(tmp_path / "fictional-store", config=Config(offline=False))
    transport = FakeTransport(invalid=invalid)
    engine.singleton_transport = transport
    try:
        def call(operation, data):
            return engine.execute(operation, data, objective="Source-free singleton API test", actor="test:synthetic")
        plan = call("status", {})
        with pytest.raises(AuditError, match="active audited"):
            list(engine.gateway.singleton_api_dispatch("not-active", plan, "not-real", []))
        payload = {"phase": "singleton_api_execute", "plan": plan, "authorize_user_request": USER_INSTRUCTION}
        result = call("luna_group_validation", payload)
        assert sum(result["counts"].values()) == 100 and not result["memberships_changed"]
        assert result["automatic_retries"] == 0
        if invalid:
            assert transport.calls == 1 and result["stopped"]
            assert result["counts"]["incomplete"] == 100 and result["pair_statuses"] == {"invalid": 1}
        else:
            assert transport.calls == 300 and result["pending_pairs"] == 0 and not result["stopped"]
            assert result["counts"] == {"supported_match": 1, "uncertain": 0, "unmatched_among_top3": 99, "incomplete": 0}
            assert result["usage"] == {"input_tokens": 30000, "output_tokens": 6000, "total_tokens": 36000}
        calls_before = transport.calls
        replay = call("luna_group_validation", payload)
        assert transport.calls == calls_before and replay["counts"] == result["counts"]
        presentation = result["presentation"]
        assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode("utf-8")
        intents = engine.ledger.db.execute("SELECT count(*) FROM events WHERE kind='model.attempt.intended'").fetchone()[0]
        assert intents == transport.calls
        engine.ledger.verify()
    finally:
        engine.close()


def test_untouched_continuation_keeps_one_retention_exclusion_and_shared_budget(tmp_path, monkeypatch) -> None:
    from newsresearch import singleton_api_continuation as continuation

    class PartialTransport(FakeTransport):
        def send(self, body, client_request_id):
            response = super().send(body, client_request_id)
            if self.calls == 60:
                # A fictional placeholder exercises the guard. No real key and
                # no flagged response bytes are retained in the fixture store.
                return EmbeddingHTTPResponse(json.dumps({"fictional": "Bearer" + " placeholder"}).encode(), 200, "fictional-request")
            return response

    location = tmp_path / "fictional-continuation-store"
    original = FixtureResearch(location, config=Config(offline=False))
    original.singleton_transport = PartialTransport()
    try:
        plan = original.execute("status", {}, objective="Synthetic setup", actor="test:synthetic")
        parent = original.execute("luna_group_validation", {"phase": "singleton_api_execute", "plan": plan,
            "authorize_user_request": USER_INSTRUCTION}, objective="Synthetic parent", actor="test:synthetic")
        assert parent["model_attempts"] == 60 and parent["pair_statuses"] == {"valid": 59, "invalid": 1}
    finally:
        original.close()
    monkeypatch.setattr(continuation, "PARENT_RESULT", parent["id"])
    engine = continuation.SingletonContinuationResearch(location, config=Config(offline=False))
    engine.singleton_transport = FakeTransport()
    try:
        payload = {"phase": "singleton_api_continue_untouched"}
        result = engine.execute("luna_group_validation", payload, objective="Synthetic continuation", actor="test:synthetic")
        assert result["model_attempts"] == 300 and engine.singleton_transport.calls == 240
        assert result["pair_statuses"] == {"valid": 299, "invalid": 1}
        assert result["counts"]["incomplete"] == 1 and result["pending_pairs"] == 0
        assert result["original_stop_preserved"] and result["automatic_retries"] == 0
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='singleton_api_stop'").fetchone()[0] == 1
        replay = engine.execute("luna_group_validation", payload, objective="Synthetic exact resume", actor="test:synthetic")
        assert replay["counts"] == result["counts"] and engine.singleton_transport.calls == 240
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 300
        engine.ledger.verify()
    finally:
        engine.close()
