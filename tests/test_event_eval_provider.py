"""Synthetic transport checks; no CLI process, source store or model calls."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from newsresearch.common import ResearchError
from newsresearch.event_eval_provider import PairProvider, build_prompt
from newsresearch.event_pair_reference import WORKER_RULES, build_request, make_lead, validate_answer


@pytest.fixture
def packet(monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    def lead(source, text):
        span = {"id": f"{source}-paragraph", "source_id": source, "start": 0,
                "end": len(text), "text": text, "text_hash": hashlib.sha256(text.encode()).hexdigest()}
        return make_lead(source, f"Title {source}", None, [span])
    return build_request(left=lead("source-a", "Aster announced the Delft model on Monday."),
                         right=lead("source-b", "Aster introduced its Delft model on Monday."),
                         versions={"protocol": "synthetic-method"})


def answer():
    return {"label": "same_event", "support_span_ids": ["A1", "B1"],
            "reason": "The supplied leads describe the same model announcement."}


def stream(extra=None):
    events = [{"type": "thread.started"}, {"type": "turn.started"}]
    if extra is not None:
        events.append(extra)
    events.extend([{"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer())}},
                   {"type": "turn.completed", "usage": {"input_tokens": 20, "output_tokens": 10}}])
    return "\n".join(json.dumps(event) for event in events)


def test_exact_blinded_prompt_manifest_and_pinned_transport(tmp_path, packet):
    packet.update(score=0.92, rank=1, stratum="within", membership="same", old_label="different_event")
    calls = []
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=stream(), stderr="", returncode=0)
    provider = PairProvider(tmp_path / "workers", runner=runner)
    invocation = provider.prepare(packet)
    prompt = json.loads(invocation.stdin)
    assert set(prompt) == {"boundary", "task", "inclusion", "articles", "evidence", "schema"}
    assert len(prompt["articles"]) == 2
    assert [span["id"] for span in prompt["evidence"]] == ["A1", "B1"]
    for span in packet["evidence"]:
        assert invocation.stdin.count(span["text"]) == 1
    assert "parent_ref" not in invocation.stdin and "lead_span_id" not in invocation.stdin
    assert invocation.stdin == build_prompt(packet)
    manifest = invocation.manifest()
    assert manifest["worker_rules"] == WORKER_RULES
    assert manifest["stdin_sha256"] == hashlib.sha256(invocation.stdin.encode()).hexdigest()
    assert manifest["schema_file_utf8"] == (invocation.cwd / "response-schema.json").read_text(encoding="utf-8")
    assert (invocation.cwd / "AGENTS.md").read_text(encoding="utf-8") == WORKER_RULES
    assert invocation.command[-3:] == ("-c", 'model_reasoning_effort="low"', "-")
    assert invocation.command[invocation.command.index("--model") + 1] == "gpt-6-luna"
    response = provider.complete_prepared(invocation)
    assert validate_answer(packet, response.payload)["status"] == "valid"
    assert response.usage == {"input_tokens": 20, "output_tokens": 10}
    assert response.model is None and response.request_id is None
    assert calls[0][1]["input"] == invocation.stdin and calls[0][1]["shell"] is False
    assert calls[0][1]["timeout"] == 90
    assert response.raw_response["worker_rules"] == WORKER_RULES


@pytest.mark.parametrize("filename", ["AGENTS.md", "response-schema.json"])
def test_tampered_worker_inputs_never_dispatch(tmp_path, packet, filename):
    calls = []
    provider = PairProvider(tmp_path / "workers", runner=lambda *a, **kw: calls.append(kw))
    invocation = provider.prepare(packet)
    (invocation.cwd / filename).write_text("changed", encoding="utf-8")
    with pytest.raises(ResearchError, match="changed"):
        provider.complete_prepared(invocation)
    assert not calls


def test_changed_command_and_input_never_dispatch(tmp_path, packet):
    calls = []
    provider = PairProvider(tmp_path / "workers", runner=lambda *a, **kw: calls.append(kw))
    invocation = provider.prepare(packet)
    with pytest.raises(ResearchError, match="command_changed"):
        provider.complete_prepared(replace(invocation, command=(*invocation.command, "changed")))
    with pytest.raises(ResearchError, match="input_changed"):
        provider.complete_prepared(replace(invocation, stdin=invocation.stdin + " "))
    assert not calls


def test_limits_key_and_model_rejection_do_not_dispatch(tmp_path, packet, monkeypatch):
    calls = []
    with pytest.raises(ResearchError, match="too_large_no_dispatch"):
        PairProvider(tmp_path / "small", max_input_bytes=1, runner=lambda *a, **kw: calls.append(kw)).complete(packet)
    with pytest.raises(ResearchError, match="model_or_effort_changed"):
        PairProvider(tmp_path / "wrong-model", {"codex_model": "different"})
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-presence-only")
    with pytest.raises(ResearchError, match="api_key_environment_forbidden"):
        PairProvider(tmp_path / "key").prepare(packet)
    assert not calls


def test_timeout_and_observed_tools_remain_unusable(tmp_path, packet):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 90, output=b"", stderr=b"")
    response = PairProvider(tmp_path / "timeout", runner=timeout).complete(packet)
    assert response.payload is None and response.raw_response["unknown_outcome"] is True
    output = stream({"type": "item.started", "item": {"type": "command_execution"}})
    response = PairProvider(tmp_path / "tools", runner=lambda *a, **kw:
                            SimpleNamespace(stdout=output, stderr="", returncode=0)).complete(packet)
    assert response.payload is None
    assert response.raw_response["failure"] == "codex_tool_or_unrecognized_activity"
