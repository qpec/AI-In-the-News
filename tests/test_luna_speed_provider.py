"""Synthetic speed-transport checks; no article stores, subprocesses or models."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from newsresearch.common import ResearchError
from newsresearch.luna_speed_provider import (
    MODEL, WORKER_RULES, SpeedProvider, build_prompt, contract, validate_response,
)

TASK = hashlib.sha256(b"fictional-task").hexdigest()
ATTEMPT = "9377fca6-e039-4b6d-a22f-46178f15b310"


@pytest.fixture
def sample(monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    return contract.fictional_example()


def stream(output, *, model=None, extra=None, completed=True):
    events = [{"type": "thread.started", "thread_id": "fictional-thread"}, {"type": "turn.started"}]
    if model is not None:
        events[0]["model"] = model
    if extra is not None:
        events.append(extra)
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(output)}})
    if completed:
        events.append({"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 18}})
    return "\n".join(json.dumps(event) for event in events)


def runner_for(output, **options):
    return lambda *args, **kwargs: SimpleNamespace(stdout=stream(output, **options), stderr="", returncode=0)


def test_exact_prompt_packet_and_full_manifest(tmp_path, sample):
    packet, output = sample
    calls = []
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=stream(output), stderr="", returncode=0)
    provider = SpeedProvider(tmp_path / "workers", runner=runner)
    invocation = provider.prepare(TASK, ATTEMPT, packet, timeout_seconds=17.5)
    sent = json.loads(invocation.stdin)
    assert sent["article"] == packet["model_input"]
    assert set(sent) == {"boundary", "article", "schema"}
    assert sent["article"]["instructions"] == contract.load_prompt()
    assert "source_map" not in sent and "task_key" not in sent
    assert invocation.stdin == build_prompt(invocation.request)
    assert "".join(p["text"] for p in sent["article"]["evidence"]["paragraphs"]) == packet["source_map"]["source_fields"]["body"]["text"]
    manifest = invocation.manifest()
    assert manifest["packet"] == packet
    assert manifest["contract_digest"] == contract.contract_digest()
    assert manifest["timeout_seconds"] == 17.5
    assert manifest["max_input_bytes"] == 1_000_000
    assert manifest["max_output_bytes"] == 262144
    assert manifest["provider_output_token_cap"] is None
    assert manifest["worker_rules"] == WORKER_RULES
    assert manifest["stdin_sha256"] == hashlib.sha256(invocation.stdin.encode()).hexdigest()
    assert manifest["schema_file_utf8"] == (invocation.cwd / "response-schema.json").read_text(encoding="utf-8")
    assert (invocation.cwd / "AGENTS.md").read_text(encoding="utf-8") == WORKER_RULES
    assert invocation.command[-3:] == ("-c", 'model_reasoning_effort="low"', "-")
    assert invocation.command[invocation.command.index("--model") + 1] == MODEL
    response = provider.complete_prepared(invocation)
    assert response.payload == output
    assert validate_response(response, packet) == []
    assert response.usage == {"input_tokens": 42, "output_tokens": 18}
    assert response.model is None and response.request_id is None
    assert response.raw_response["observed_model_unavailable_reason"]
    assert calls[0][1]["timeout"] == 17.5
    assert calls[0][1]["input"] == invocation.stdin
    assert calls[0][1]["shell"] is False
    assert provider.timeout_seconds == 180


def test_input_snapshot_is_immutable_to_caller_mutation(tmp_path, sample):
    packet, _ = sample
    provider = SpeedProvider(tmp_path / "workers")
    invocation = provider.prepare(TASK, ATTEMPT, packet)
    packet["model_input"]["context"]["language"] = "changed"
    assert invocation.request["packet"]["model_input"]["context"]["language"] != "changed"


def test_parallel_call_timeouts_do_not_mutate_shared_provider(tmp_path, sample):
    packet, output = sample
    seen = []
    def runner(*args, **kwargs):
        seen.append(kwargs["timeout"])
        return SimpleNamespace(stdout=stream(output), stderr="", returncode=0)
    provider = SpeedProvider(tmp_path / "workers", runner=runner)
    first = provider.prepare(TASK, ATTEMPT, packet, timeout_seconds=2)
    second = provider.prepare(TASK, "a" * 64, packet, timeout_seconds=9)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(provider.complete_prepared, [first, second]))
    assert sorted(seen) == [2, 9]
    assert all(validate_response(response, packet) == [] for response in results)
    assert provider.timeout_seconds == 180


@pytest.mark.parametrize("model", [MODEL, MODEL + "-2026-10-17"])
def test_observed_luna_alias_or_dated_snapshot_validates(tmp_path, sample, model):
    packet, output = sample
    provider = SpeedProvider(tmp_path / "workers", runner=runner_for(output, model=model))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert response.model == model
    assert response.raw_response["observed_model_unavailable_reason"] is None
    assert validate_response(response, packet) == []


@pytest.mark.parametrize("model", ["gpt-6-sol", "gpt-6-luna-wrong", "gpt-6-luna-20261017"])
def test_observed_wrong_model_retains_output_but_rejects_result(tmp_path, sample, model):
    packet, output = sample
    provider = SpeedProvider(tmp_path / "workers", runner=runner_for(output, model=model))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert response.payload is None
    assert response.raw_response["stdout"] == stream(output, model=model)
    assert validate_response(response, packet) == ["response:observed_model_mismatch"]


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "web_search", "agent_delegation"])
def test_tools_never_validate(tmp_path, sample, kind):
    packet, output = sample
    extra = {"type": "item.started", "item": {"type": kind}}
    provider = SpeedProvider(tmp_path / "workers", runner=runner_for(output, extra=extra))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert response.payload is None
    assert response.raw_response["failure"] == "codex_tool_or_unrecognized_activity"
    assert validate_response(response, packet)


def test_timeout_retains_partial_response_as_unknown(tmp_path, sample):
    packet, _ = sample
    partial = '{"type":"thread.started"}'
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], output=partial.encode(), stderr=b"partial")
    provider = SpeedProvider(tmp_path / "workers", runner=runner)
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet, timeout_seconds=0.5))
    assert response.raw_response["stdout"] == partial
    assert response.raw_response["timeout_seconds"] == 0.5
    assert response.raw_response["unknown_outcome"] is True
    assert validate_response(response, packet) == ["response:unknown_outcome"]


def test_completion_and_literal_grounding_are_independent_requirements(tmp_path, sample):
    packet, output = sample
    provider = SpeedProvider(tmp_path / "incomplete", runner=runner_for(output, completed=False))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert validate_response(response, packet) == ["response:unknown_outcome"]
    output["event"]["action"]["surface"] = "invented unsupported action"
    provider = SpeedProvider(tmp_path / "ungrounded", runner=runner_for(output))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert "event.action:surface_not_grounded" in validate_response(response, packet)


@pytest.mark.parametrize("filename", ["AGENTS.md", "response-schema.json"])
def test_worker_tampering_prevents_dispatch(tmp_path, sample, filename):
    packet, _ = sample
    calls = []
    provider = SpeedProvider(tmp_path / "workers", runner=lambda *a, **kw: calls.append(kw))
    invocation = provider.prepare(TASK, ATTEMPT, packet)
    (invocation.cwd / filename).write_text("changed", encoding="utf-8")
    with pytest.raises(ResearchError, match="changed"):
        provider.complete_prepared(invocation)
    assert calls == []


@pytest.mark.parametrize("change", ["stdin", "command", "timeout_seconds", "max_output_bytes"])
def test_changed_invocation_prevents_dispatch(tmp_path, sample, change):
    packet, _ = sample
    calls = []
    provider = SpeedProvider(tmp_path / "workers", runner=lambda *a, **kw: calls.append(kw))
    invocation = provider.prepare(TASK, ATTEMPT, packet, timeout_seconds=4)
    changed = {"stdin": invocation.stdin + " ", "command": (*invocation.command, "changed"),
               "timeout_seconds": 5, "max_output_bytes": 1}[change]
    with pytest.raises(ResearchError, match="changed"):
        provider.complete_prepared(replace(invocation, **{change: changed}))
    assert calls == []


@pytest.mark.parametrize("change", ["instructions", "codebook", "body"])
def test_changed_contract_or_incomplete_evidence_rejected(tmp_path, sample, change):
    packet, _ = sample
    packet = deepcopy(packet)
    if change == "body":
        packet["model_input"]["evidence"]["paragraphs"][0]["text"] = "cropped"
    else:
        packet["model_input"][change] = "changed"
    with pytest.raises(ResearchError):
        SpeedProvider(tmp_path / "workers").prepare(TASK, ATTEMPT, packet)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), 181])
def test_invalid_timeout_rejected(tmp_path, timeout):
    with pytest.raises(ResearchError, match="invalid_timeout"):
        SpeedProvider(tmp_path / "workers", timeout_seconds=timeout)


@pytest.mark.parametrize("variable", ["OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"])
def test_api_or_endpoint_environment_rejected(tmp_path, sample, monkeypatch, variable):
    packet, _ = sample
    monkeypatch.setenv(variable, "fictional-presence-only")
    with pytest.raises(ResearchError, match="environment_forbidden|override_forbidden"):
        SpeedProvider(tmp_path / "workers").prepare(TASK, ATTEMPT, packet)


def test_byte_limits_do_not_truncate_or_claim_token_caps(tmp_path, sample):
    packet, output = sample
    with pytest.raises(ResearchError, match="too_large_no_dispatch"):
        SpeedProvider(tmp_path / "small", max_input_bytes=1).prepare(TASK, ATTEMPT, packet)
    provider = SpeedProvider(tmp_path / "output", max_output_bytes=1, runner=runner_for(output))
    response = provider.complete_prepared(provider.prepare(TASK, ATTEMPT, packet))
    assert response.raw_response["stdout"] == stream(output)
    assert response.raw_response["failure"] == "codex_output_acceptance_limit_exceeded"
    assert validate_response(response, packet)


def test_direct_complete_is_not_supported(tmp_path, sample):
    with pytest.raises(ResearchError, match="prepared_audited_gateway"):
        SpeedProvider(tmp_path / "workers").complete(sample[0])
