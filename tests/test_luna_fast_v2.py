"""Synthetic terminal-recovery and bounded continuation checks; no model calls."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import Config, ResearchError
from newsresearch.luna_fast_provider_v2 import FastProviderV2, build_prompt, execution_notes
from newsresearch.luna_speed_provider import SpeedProvider, contract, validate_response
from newsresearch.runtime import audited_handler

import test_luna_speed_workflow as prior
from test_luna_speed_provider import ATTEMPT, TASK, stream

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_fast_iteration_v2 as fast
finally:
    sys.path.pop(0)

DETAIL = ("unexpected status 403 Forbidden: Unknown error, url: "
          "wss://chatgpt.com/backend-api/codex/responses, cf-ray: abc123-AMS")
RECONNECT = {"type": "error", "message": "Reconnecting... 2/5 (" + DETAIL + ")"}
FALLBACK = {"type": "item.completed", "item": {"id": "item_0", "type": "error",
            "message": "Falling back from WebSockets to HTTPS transport. " + DETAIL}}


@pytest.fixture(autouse=True)
def no_api_environment(monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


def recovered_stream(output, include_notice=True):
    events = [json.loads(line) for line in stream(output).splitlines()]
    events[2:2] = [deepcopy(RECONNECT)] + ([deepcopy(FALLBACK)] if include_notice else [])
    return events


def run_response(tmp_path, events, *, exit_code=0, suffix="", timeout=False, max_output_bytes=262144):
    packet, _ = contract.fictional_example()
    stdout = "\n".join(json.dumps(e) for e in events) + suffix
    calls = []
    def runner(*args, **kwargs):
        calls.append(kwargs)
        if timeout:
            raise subprocess.TimeoutExpired("synthetic", 3, output=stdout, stderr="")
        return SimpleNamespace(stdout=stdout, stderr="", returncode=exit_code)
    provider = FastProviderV2(tmp_path / "workers", runner=runner, max_output_bytes=max_output_bytes)
    invocation = provider.prepare(TASK, ATTEMPT, packet)
    response = provider.complete_prepared(invocation)
    assert len(calls) == 1  # Recovery replays bytes; it never invokes the runner again.
    return invocation, response, packet


@pytest.mark.parametrize("include_notice", [True, False])
def test_completed_reconnect_retains_exact_evidence_and_usage(tmp_path, include_notice):
    packet, output = contract.fictional_example()
    events = recovered_stream(output, include_notice)
    invocation, response, _ = run_response(tmp_path, events)
    assert response.payload == output and validate_response(response, packet) == []
    raw = response.raw_response
    assert raw["events"] == events and raw["recovered_transport"]
    assert not raw["unknown_outcome"] and raw["transport_status"] == "returned"
    assert raw["original_parser_failure"] == "codex_turn_failed_unknown_outcome"
    assert raw["transport_warning_count"] == (2 if include_notice else 1)
    assert raw["remote_attempt_uniqueness_proven"] is False
    assert response.usage == {"input_tokens": 42, "output_tokens": 18}
    wire = json.loads(invocation.stdin)
    assert wire["article"] == packet["model_input"] and wire["schema"] == contract.load_schema()
    assert wire["execution_notes"] == execution_notes()
    assert invocation.stdin == build_prompt(invocation.request)
    assert invocation.manifest()["stdin"] == invocation.stdin
    assert invocation.manifest()["transport"] == "codex-cli-luna-fast-v2"


@pytest.mark.parametrize("problem", ["tool", "arbitrary_error", "unrecognized_item_error", "turn_failed",
    "missing_completion", "duplicate_completion", "duplicate_answer", "trailing_event", "non_json_line",
    "nonzero_exit", "wrong_model", "wrong_tier", "timeout", "output_limit", "late_error"])
def test_recovery_never_hides_real_failures_or_activity(tmp_path, problem):
    _, output = contract.fictional_example()
    events = recovered_stream(output)
    options = {}
    if problem == "tool":
        events.insert(4, {"type": "item.completed", "item": {"type": "command_execution", "command": "fictional"}})
    elif problem == "arbitrary_error":
        events.insert(4, {"type": "error", "message": "Permission denied"})
    elif problem == "unrecognized_item_error":
        events[3]["item"]["message"] = "An unrelated failure"
    elif problem == "turn_failed":
        events.insert(-1, {"type": "turn.failed", "error": {"message": "fictional failure"}})
    elif problem == "missing_completion":
        events.pop()
    elif problem == "duplicate_completion":
        events.append(deepcopy(events[-1]))
    elif problem == "duplicate_answer":
        events.insert(-1, deepcopy(events[-2]))
    elif problem == "trailing_event":
        events.append({"type": "turn.started"})
    elif problem == "non_json_line":
        options["suffix"] = "\nnot a JSON event"
    elif problem == "nonzero_exit":
        options["exit_code"] = 1
    elif problem == "wrong_model":
        events[0]["model"] = "gpt-6-sol"
    elif problem == "wrong_tier":
        events[0]["service_tier"] = "standard"
    elif problem == "timeout":
        options["timeout"] = True
    elif problem == "output_limit":
        options["max_output_bytes"] = 10
    elif problem == "late_error":
        events.insert(-1, deepcopy(RECONNECT))
    _, response, packet = run_response(tmp_path, events, **options)
    assert response.payload is None and validate_response(response, packet)
    assert not response.raw_response["recovered_transport"]


def test_recovered_invalid_content_still_fails_unchanged_validator(tmp_path):
    _, response, packet = run_response(tmp_path, recovered_stream({}))
    assert response.payload == {} and response.raw_response["transport_status"] == "returned"
    assert validate_response(response, packet)


def test_guidance_or_input_changes_are_rejected_before_dispatch(tmp_path):
    packet, _ = contract.fictional_example()
    provider = FastProviderV2(tmp_path / "workers", runner=lambda *args, **kwargs: pytest.fail("must not dispatch"))
    call = provider.prepare(TASK, ATTEMPT, packet)
    with pytest.raises(ResearchError, match="guided_invocation_changed"):
        provider.complete_prepared(replace(call, stdin=call.stdin + " "))


class FixtureFast(fast.FastResearch, prior.FixtureResearch):
    def batch_exclusions(self, session, database):
        self.cross_lane_snapshot = {"body_hashes": [], "synthetic": True}
        return self.cross_lane_snapshot

    @audited_handler
    def _status(self, session, context, data):
        result = super()._status(session, context, data)
        sources = list(result["metadata"])
        parent = self.ledger.record(session, "luna_fast_plan", "fictional-parent", {
            "tasks": [{"source_version": source} for source in sources[:5]]})
        parent_result = {"plan": parent, "outcomes": [{"source_version": sources[0], "dispatch_offset": 0}]}
        result["parent_result"] = self.ledger.record(session, "luna_fast_result", "fictional-parent", parent_result)
        self.ledger.record(session, "luna_fast_assessment", "fictional-spent", parent_result["outcomes"][0])
        result["eligible"] = sources[1:5]
        return result


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    engine = FixtureFast(tmp_path / "protected", config=Config(offline=True))
    fixture = prior.call(engine, "status", {"fixture": "build"})
    for name, value in (("ORIGINAL_RESULT", fixture["original_result"]), ("STOPPED_PLAN", fixture["stopped_plan"]),
                        ("PARENT_RESULT", fixture["parent_result"])):
        monkeypatch.setattr(fast, name, value)
    monkeypatch.setattr(fast, "load_frame", lambda *args: {"metadata": fixture["metadata"], "frame": fixture["frame"]})
    monkeypatch.setattr(fast, "partition_binding", lambda path: {"corpus_id": "incident-reports",
        "file_sha256": {"corpora/incident-reports/manifest.json": "b" * 64}, "manifests": {
            "incident-reports": {"bundles": [{"path": "fictional.zip", "sha256": "a" * 64}]}, "cybercrime": {"bundles": []}}})
    plan = prior.call(engine, "luna_group_validation", {"phase": "prepare", "queue_limit": 6,
                      "data_root": "fictional", "batch_state": "synthetic"})
    try:
        yield engine, plan, fixture
    finally:
        engine.close()


def test_audited_continuation_only_uses_parent_unattempted_sources_and_never_restarts(prepared, monkeypatch):
    engine, plan, fixture = prepared
    _, output = contract.fictional_example()
    events = recovered_stream(output)
    calls = []
    def runner(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(stdout="\n".join(json.dumps(e) for e in events), stderr="", returncode=0)
    original = SpeedProvider.__init__
    monkeypatch.setattr(SpeedProvider, "__init__", lambda self, *args, **kwargs: original(self, *args, **kwargs, runner=runner))
    assert {t["source_version"] for t in plan["tasks"]} == set(fixture["eligible"])
    assert plan["continuation_parent_result"] == fixture["parent_result"]
    assert plan["limits"]["max_attempts"] == 1835
    parent_before = engine.ledger.get(fixture["parent_result"], "luna_fast_result")
    engine.config = replace(engine.config, offline=False)
    data = {"phase": "run", "plan": plan["id"], "batch_state": "synthetic", "authorization_text": "Continue this fictional fixture"}
    result = prior.call(engine, "luna_group_validation", data)
    assert result["counts"] == {"valid": 4} and result["recovered_transport_calls"] == 4
    assert result["transport_warning_count"] == 8 and len(calls) == 4
    assert not engine.ledger.unresolved
    assert engine.ledger.get(fixture["parent_result"], "luna_fast_result") == parent_before
    for outcome in result["outcomes"]:
        raw = engine.ledger.artifacts.read(outcome["response"])["raw_response"]
        assert raw["events"] == events and raw["recovered_transport"]
    report = prior.call(engine, "luna_group_validation", {"phase": "report", "result": result["id"]})
    assert report["markdown"] == result["markdown"]
    with pytest.raises(ResearchError, match="spent_no_restart"):
        prior.call(engine, "luna_group_validation", data)
    assert len(calls) == 4
    engine.ledger.verify()


def test_unrecovered_canary_stops_new_dispatch_and_keeps_hold(prepared, monkeypatch):
    engine, plan, _ = prepared
    calls = prior.mock_runner(monkeypatch, unknown=True)
    engine.config = replace(engine.config, offline=False)
    result = prior.call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
        "batch_state": "synthetic", "authorization_text": "Fictional failure only"})
    assert len(calls) == 1 and result["counts"] == {"unknown": 1}
    assert result["pending"] == 3 and len(engine.ledger.unresolved) == 1
