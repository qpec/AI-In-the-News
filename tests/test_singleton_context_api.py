"""Synthetic context/citation, scope, audit, failure and resume checks; no network."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from newsresearch.common import AuditError, Config, Context, ResearchError, digest
from newsresearch.embeddings import EmbeddingHTTPResponse
from newsresearch.runtime import audited_handler
from newsresearch import singleton_context_api as workflow
from newsresearch.singleton_context_contract import build_request, make_context, validate_answer, validate_request


def context(source, body):
    parents, start = [], 0
    for text in body.split("\n\n"):
        parents.append({"id": digest([source, start]), "source_id": source, "start": start,
                        "end": start + len(text), "text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()})
        start += len(text) + 2
    return make_context(source, "Fictional title", None, body, parents)


def test_full_and_capped_context_exact_slices_citations_and_tampering():
    text = "Fictional announcement in a synthetic city.\n\nA closing paragraph about a fictional event."
    short = context("a", text)
    assert short["coverage"]["all_stored_paragraph_text_supplied"]
    long = context("b", "opening " * 4000 + "closing " * 1000)
    assert [s["start"] for s in long["passages"]] == [0, 34000]
    assert long["coverage"]["retained_body_characters"] == 24000
    assert not long["coverage"]["all_stored_paragraph_text_supplied"]
    many = context("c", "\n\n".join(["Fictional paragraph of sufficient length."] * 150))
    assert many["coverage"]["retained_spans"] == 128
    request = build_request(short, long, {"protocol": "fictional"})
    answer = {"label": "same_event", "support_span_ids": ["A1", "B2"], "reason": "Fictional only."}
    assert validate_answer(request, answer)["status"] == "valid"
    assert workflow.wire_body(request)["model"] == "gpt-6-luna"
    with pytest.raises(ResearchError):
        validate_answer(request, {**answer, "support_span_ids": ["A1"]})
    with pytest.raises(ResearchError):
        validate_answer(request, {**answer, "support_span_ids": ["A1", "A1", "B2"]})
    changed = deepcopy(request)
    changed["evidence"][0]["text"] += "tampering"
    with pytest.raises(ResearchError):
        validate_request(changed)


class Fixture(workflow.SingletonContextResearch):
    @audited_handler
    def _status(self, session, ctx, data):
        versions = {}
        for kind, content in (("protocol", {"method": "fictional context fixture"}),
                              ("selection", {"rules": "103 invented sources"})):
            versions[kind] = self._version(session, ctx, {"kind": kind, "key": "fixture", "content": content})["id"]
        dataset = self._ingest(session, Context(ctx.objective, ctx.actor, versions), {
            "articles": [{"source_key": str(i), "title": f"Fictional {i}", "synthetic": True, "retention": "permitted",
                          "url": f"https://example.invalid/{i}", "body": f"Fictional {i} reports a synthetic event.\n\n" +
                          "An invented longer context paragraph.\n\n" * 4 + "Fictional closing evidence."} for i in range(103)],
            "retrieval": {"source": "synthetic-fixture", "retrieved_at": "2026-10-17T00:00:00+00:00", "parameters": {}}})
        versions["dataset"] = dataset["id"]
        sources = self.ledger.get(dataset["id"], "dataset")["source_versions"]
        rows, tasks, outcomes = [], [], {}
        for index, source in enumerate(sources[:100]):
            category = "uncertain" if index < 41 else "incomplete" if index < 44 else "supported_match" if index < 58 else "unmatched_among_top3"
            candidates = []
            for rank, candidate in enumerate(sources[100:]):
                left, right = sorted((source, candidate))
                pair = digest([left, right])
                candidates.append({"source": candidate, "pair": pair, "score": .8, "group": "fictional", "group_size": 1})
                tasks.append({"pair": pair, "left": left, "right": right})
                status = "invalid" if category == "incomplete" and rank == 0 else "valid"
                label = None if status == "invalid" else "uncertain" if category == "uncertain" else "same_event" if category == "supported_match" and rank == 0 else "different_event"
                value = {"status": status, "label": label, "attempt": f"fictional-old-{pair}"}
                assessment = self.ledger.record(session, "fictional_prior_reference", pair, value)
                outcomes[pair] = {**value, "assessment": assessment}
            rows.append({"source": source, "category": category, "candidates": candidates})
        plan = {"versions": versions, "tasks": tasks,
                "source_metadata": {s: {"title": "Fictional", "url": "https://example.invalid/fixture"} for s in sources}}
        plan_id = self.ledger.record(session, "luna_group_validation_plan", "fictional-parent-plan", plan)
        parent = {"plan": plan_id, "versions": versions, "rows": rows, "outcomes": outcomes,
                  "counts": dict(zip(workflow.CATEGORIES, (14, 41, 42, 3), strict=True))}
        return self.ledger.record(session, "luna_group_validation_result", "fictional-parent-result", parent)


class Transport:
    def __init__(self, failure=None):
        self.calls = 0
        self.failure = failure

    def send(self, body, request_id):
        self.calls += 1
        packet = json.loads(body)
        assert packet["model"] == "gpt-6-luna" and packet["store"] is False
        assert "uniqueItems" not in packet["text"]["format"]["schema"]["properties"]["support_span_ids"]
        if self.failure == "unknown":
            raise TimeoutError("fictional timeout")
        if self.failure == "retention":
            return EmbeddingHTTPResponse(json.dumps({"fictional": "Bearer" + " placeholder"}).encode(), 200, "fictional-request")
        answer = {"label": "different_event", "support_span_ids": ["A1", "B1"], "reason": "Fictional fixture only."}
        response = {"id": "fictional-response", "model": "wrong" if self.failure == "model" else "gpt-6-luna",
                    "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(answer)}]}],
                    "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}}
        return EmbeddingHTTPResponse(json.dumps(response).encode(), 200, "fictional-request")


@pytest.mark.parametrize("failure", [None, "model", "unknown", "retention", "audit"])
def test_frozen_scope_retained56_retry_links_and_no_duplicate_resume(tmp_path, monkeypatch, failure):
    engine = Fixture(tmp_path / "synthetic-context", config=Config(offline=False))
    engine.context_transport = Transport(failure)
    try:
        def run(operation, data):
            return engine.execute(operation, data, objective="Source-free expanded-context fixture", actor="test:synthetic")
        parent = run("status", {})
        monkeypatch.setattr(workflow, "PARENT", parent)
        plan = run("luna_group_validation", {"phase": "singleton_context_prepare"})
        assert len(plan["tasks"]) == 132 and len(plan["preserved_rows"]) == 56
        assert sum(t["retry_of"] is not None for t in plan["tasks"]) == 3
        with pytest.raises(AuditError, match="active audited"):
            list(engine.gateway.context_dispatch("not-active", plan["id"], "fictional", []))
        payload = {"phase": "singleton_context_execute", "plan": plan["id"], "user_instruction": workflow.USER_INSTRUCTION}
        if failure == "audit":
            original_record = engine.ledger.record

            def fail_assessment(session, kind, key, value, *args, **kwargs):
                if kind == "singleton_context_assessment":
                    raise AuditError("fictional durable assessment failure")
                return original_record(session, kind, key, value, *args, **kwargs)

            monkeypatch.setattr(engine.ledger, "record", fail_assessment)
            with pytest.raises(AuditError, match="durable assessment failure"):
                run("luna_group_validation", payload)
            assert engine.context_transport.calls == 1
            monkeypatch.setattr(engine.ledger, "record", original_record)
            replay = run("luna_group_validation", payload)
            assert replay["stopped"] and replay["new_pair_statuses"] == {"unknown": 1}
            assert engine.context_transport.calls == 1
            engine.ledger.verify()
            return
        result = run("luna_group_validation", payload)
        assert sum(result["counts"].values()) == 100 and not result["memberships_changed"]
        assert result["counts"]["supported_match"] == 14
        if failure in {"model", "unknown"}:
            assert result["stopped"] and engine.context_transport.calls == 1
            assert result["pending_pairs"] == 131 and result["counts"]["incomplete"] == 44
        else:
            assert engine.context_transport.calls == 132 and not result["stopped"]
            assert result["pending_pairs"] == 0 and result["explicit_retry_attempts"] == 3
            assert result["counts"] == dict(zip(workflow.CATEGORIES, (14, 0, 42 if failure else 86, 44 if failure else 0), strict=True))
        previous_calls = engine.context_transport.calls
        replay = run("luna_group_validation", payload)
        assert replay["counts"] == result["counts"] and engine.context_transport.calls == previous_calls
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == previous_calls
        presentation = result["presentation"]
        assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode()
        engine.ledger.verify()
    finally:
        engine.close()
