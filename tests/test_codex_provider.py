from __future__ import annotations

import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from newsresearch.codex_provider import CodexCLIProvider, build_prompt, judge_schema, validate_judgement
from newsresearch.common import ResearchError


@pytest.fixture
def request_packet(monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    instruction = "Include a concrete observed service outage related to AI."
    return {
        "inclusion": {
            "instruction": instruction,
            "sha256": hashlib.sha256(instruction.encode()).hexdigest(),
            "criterion_ids": ["observed", "ai"],
        },
        "evidence": [{"id": "p1", "text": "The AI service outage lasted one hour."}],
        "schema": judge_schema(), "score": 0.123, "cutoff": 0.3, "prior_label": "no",
    }


def result():
    return {
        "label": "yes", "rationale": "An observed AI outage is stated.",
        "criterion_ids": ["observed", "ai"],
        "claims": [{"passage_id": "p1", "quote": "AI service outage"}],
        "inspected_passage_ids": ["p1"],
    }


def stream(extra=None, final=None):
    events = [{"type": "thread.started", "thread_id": "visible-thread"}, {"type": "turn.started"}]
    if extra:
        events.append(extra)
    events.extend([
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(final or result())}},
        {"type": "turn.completed", "usage": {"input_tokens": 42, "output_tokens": 18}},
    ])
    return "\n".join(json.dumps(event) for event in events)


def test_prepare_blinds_scores_and_preserves_complete_evidence(tmp_path, request_packet):
    provider = CodexCLIProvider(tmp_path)
    invocation = provider.prepare(request_packet)
    packet = json.loads(invocation.stdin)
    assert "score" not in packet and "cutoff" not in packet and "prior_label" not in packet
    assert packet["evidence"] == request_packet["evidence"]
    assert packet["inclusion"] == request_packet["inclusion"]
    assert "--ignore-user-config" in invocation.command and "--ephemeral" in invocation.command
    assert invocation.command[-1] == "-"
    assert (invocation.cwd / "AGENTS.md").is_file()
    assert invocation.manifest()["stdin"] == invocation.stdin


def test_inclusion_mismatch_and_oversize_never_dispatch(tmp_path, request_packet):
    calls = []
    provider = CodexCLIProvider(tmp_path, max_input_bytes=1, runner=lambda *a, **kw: calls.append(kw))
    with pytest.raises(ResearchError, match="input_too_large"):
        provider.complete(request_packet)
    request_packet["inclusion"]["sha256"] = "wrong"
    with pytest.raises(ResearchError, match="hash_mismatch"):
        build_prompt(request_packet)
    assert calls == []


def test_existing_key_presence_refused_without_reading_value(tmp_path, request_packet, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fixture")
    with pytest.raises(ResearchError, match="api_key_environment_forbidden"):
        CodexCLIProvider(tmp_path).prepare(request_packet)


def test_success_captures_exact_command_payload_and_observable_usage(tmp_path, request_packet):
    calls = []
    output = stream()
    def runner(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=output, stderr="", returncode=0)
    provider = CodexCLIProvider(tmp_path, runner=runner)
    prepared = provider.prepare(request_packet)
    response = provider.complete_prepared(prepared)
    assert response.payload == result()
    assert response.model is None and response.request_id is None
    assert response.usage == {"input_tokens": 42, "output_tokens": 18}
    assert response.raw_response["stdout"] == output
    assert response.raw_response["command"] == list(prepared.command)
    assert calls[0][1]["input"] == prepared.stdin and calls[0][1]["shell"] is False
    assert validate_judgement(request_packet, response.payload)["human_validated"] is False


@pytest.mark.parametrize("kind", ["command_execution", "mcp_tool_call", "web_search", "file_change", "agent_delegation"])
def test_observed_tool_activity_is_never_accepted(tmp_path, request_packet, kind):
    output = stream({"type": "item.started", "item": {"type": kind}})
    provider = CodexCLIProvider(tmp_path, runner=lambda *a, **kw: SimpleNamespace(stdout=output, stderr="", returncode=0))
    response = provider.complete(request_packet)
    assert response.payload is None
    assert response.raw_response["failure"] == "codex_tool_or_unrecognized_activity"
    assert response.raw_response["stdout"] == output


def test_timeout_keeps_partial_response_and_unknown_outcome(tmp_path, request_packet):
    output = json.dumps({"type": "thread.started", "thread_id": "partial"})
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=output.encode(), stderr=b"partial stderr")
    response = CodexCLIProvider(tmp_path, runner=runner).complete(request_packet)
    assert response.payload is None
    assert response.raw_response["unknown_outcome"] is True
    assert response.raw_response["stdout"] == output
    assert response.raw_response["stderr"] == "partial stderr"


def test_invalid_json_and_nonzero_exit_keep_permitted_return(tmp_path, request_packet):
    output = "not json"
    response = CodexCLIProvider(tmp_path, runner=lambda *a, **kw: SimpleNamespace(stdout=output, stderr="safe failure", returncode=1)).complete(request_packet)
    assert response.payload is None and response.raw_response["stdout"] == output
    assert response.raw_response["exit_code"] == 1


def test_evidence_validation_rejects_incomplete_fabricated_and_unknown_criteria(request_packet):
    sample = result()
    sample["inspected_passage_ids"] = []
    with pytest.raises(ResearchError, match="incomplete_coverage"):
        validate_judgement(request_packet, sample)
    sample = result()
    sample["claims"][0]["quote"] = "not present"
    with pytest.raises(ResearchError, match="quote_invalid"):
        validate_judgement(request_packet, sample)
    sample = result()
    sample["criterion_ids"] = ["unknown"]
    with pytest.raises(ResearchError, match="unknown_criterion"):
        validate_judgement(request_packet, sample)


def test_absence_can_have_no_quote_but_yes_requires_evidence(request_packet):
    sample = result()
    sample["claims"] = []
    sample["label"] = "no"
    assert validate_judgement(request_packet, sample)["status"] == "valid"
    sample["label"] = "uncertain"
    assert validate_judgement(request_packet, sample)["status"] == "valid"
    sample["label"] = "yes"
    with pytest.raises(ResearchError, match="yes_requires_evidence"):
        validate_judgement(request_packet, sample)


@pytest.mark.parametrize("filename", ["AGENTS.md", "response-schema.json"])
def test_changed_worker_inputs_never_dispatch(tmp_path, request_packet, filename):
    calls = []
    provider = CodexCLIProvider(tmp_path, runner=lambda *a, **kw: calls.append(kw))
    prepared = provider.prepare(request_packet)
    (prepared.cwd / filename).write_text("changed", encoding="utf-8")
    with pytest.raises(ResearchError, match="changed"):
        provider.complete_prepared(prepared)
    assert calls == []


def test_turn_failure_and_missing_completion_stay_unknown(tmp_path, request_packet):
    output = json.dumps({"type": "turn.failed", "error": {"message": "safe failure"}})
    response = CodexCLIProvider(tmp_path, runner=lambda *a, **kw: SimpleNamespace(stdout=output, stderr="", returncode=0)).complete(request_packet)
    assert response.payload is None and response.raw_response["unknown_outcome"] is True


def test_worker_must_be_outside_git(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(ResearchError, match="inside_git"):
        CodexCLIProvider(tmp_path / "workers")
