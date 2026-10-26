"""Mocked CLI-only provider checks; no real executable, account, source or model."""
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest, utc
from newsresearch.runtime import Research, audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research/cybercrime_nl/runtime"))
import final_validation_contract as contract  # noqa: E402
import final_validation_provider as provider  # noqa: E402


DOCS = [{"document_id": "private-prediction-a", "title": "Synthetic first full title",
         "body": "Synthetic occurrence at site Z.\r\n\r\nAll literal body evidence remains present."},
        {"document_id": "private-stratum-b", "title": "Synthetic second full title",
         "body": "Synthetic reporting describes site Z.\n\nThis complete source has no hidden labels."}]
TOKENIZER = {"encoding": "synthetic-length", "library": "synthetic", "version": "1"}


def packet():
    return contract.request(DOCS, order=[d["document_id"] for d in DOCS], count_tokens=lambda value: len(value) // 4)


def judgment():
    return {"examined_source_ids": ["S1", "S2"], "articles": [
        {"source_id": s, "focus": "clear_single_event", "epistemic_uncertain": False,
         "identity_statement": "One synthetic occurrence at site Z.", "reason": "The supplied report names that occurrence.",
         "citations": [{"passage_id": s + ".B1"}]} for s in ("S1", "S2")],
        "relationship": {"assessment": "assessed", "label": "same_event", "reason": "Both synthetic sources describe site Z.",
                         "citations": [{"passage_id": "S1.B1"}, {"passage_id": "S2.B1"}]}}


def events(model=contract.MODEL, extra=()):
    return [{"type": "thread.started", "thread_id": "synthetic", **({"model": model} if model else {})},
        {"type": "turn.started"}, *extra,
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(judgment())}},
        {"type": "turn.completed", "usage": {"input_tokens": 700, "output_tokens": 100}}]


def stream(value):
    return "\n".join(json.dumps(event) for event in value)


class MemoryArtifacts:
    def __init__(self):
        self.values = {}

    def put(self, value):
        key = digest(value)
        self.values[key] = deepcopy(value)
        return key

    def read(self, key):
        return deepcopy(self.values[key])


def intended(engine, invocation):
    artifacts = engine.ledger.artifacts
    row = {"attempt": invocation.invocation_id, "task_key": digest(["synthetic-primary", invocation.packet["packet_sha256"]]),
        "number": 1, "packet": artifacts.put(invocation.packet), "request": artifacts.put(invocation.request),
        "dispatch": artifacts.put(invocation.manifest()), "started_at": utc()}
    engine.ledger.unresolved[row["attempt"]] = row
    return row


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    executable = tmp_path / "synthetic-codex.exe"
    executable.write_bytes(b"This is a non-executable synthetic CLI identity fixture.")
    config = {"executable": executable, "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "cli_version_observation": {"command": [str(executable), "--version"], "stdout": "codex-cli 0.120.0\n",
                                    "stderr": "", "exit_code": 0},
        "tokenizer_identity": TOKENIZER, "count_tokens": lambda value: len(value) // 4}
    calls = []
    state = {"stdout": stream(events()), "stderr": "", "returncode": 0}

    def mocked(*args, **kwargs):
        calls.append((args, kwargs))
        if "error" in state:
            raise state["error"]
        return SimpleNamespace(**state)

    engine = SimpleNamespace(_active={"synthetic-session"}, ledger=SimpleNamespace(artifacts=MemoryArtifacts(), unresolved={}))
    instance = provider.PairProvider(tmp_path / "workers", research=engine, session="synthetic-session", runner=mocked, **config)
    return SimpleNamespace(provider=instance, engine=engine, config=config, calls=calls, state=state, mocked=mocked)


def execute(fixture):
    invocation = fixture.provider.prepare(packet())
    intended(fixture.engine, invocation)
    return invocation, fixture.provider.complete_prepared(invocation)


def test_exact_pair_prompt_account_configuration_and_full_schema(setup):
    p = packet()
    invocation = setup.provider.prepare(p)
    value = json.loads(invocation.stdin)
    assert invocation.stdin == contract.cli_prompt(p["request"]) == p["stdin"]
    assert value["task"] == contract.TASK and value["schema"] == contract.schema()
    assert all(d["document_id"] not in invocation.stdin for d in DOCS)
    evidence = json.loads(value["evidence"][0]["text"])
    assert [d["body"] for d in evidence["articles"]] == [d["body"] for d in DOCS]
    assert invocation.command[-7:] == ("-c", 'model_reasoning_effort="medium"', "-c", "features.fast_mode=false",
                                       "-c", 'forced_login_method="chatgpt"', "-")
    assert invocation.command[invocation.command.index("--model") + 1] == contract.MODEL
    assert "--ignore-user-config" in invocation.command and "--ephemeral" in invocation.command
    assert invocation.command[invocation.command.index("--sandbox") + 1] == "read-only"
    manifest = invocation.manifest()
    assert manifest["transport"] == provider.TRANSPORT and manifest["schema"] == p["request"]["schema"]
    assert json.loads((invocation.cwd / "response-schema.json").read_text()) == manifest["wire_schema"]
    assert "uniqueItems" not in manifest["schema_file_utf8"] and "uniqueItems" in json.dumps(manifest["schema"])
    assert manifest["cli_binding"]["cli_version"] == "0.120.0" and manifest["account_dollar_cost"] is None
    assert setup.calls == []


def test_success_preserves_raw_observed_metadata_and_strict_pair_parse(setup):
    invocation, response = execute(setup)
    assert len(setup.calls) == 1
    args, kwargs = setup.calls[0]
    assert args[0] == list(invocation.command) and kwargs["input"] == invocation.stdin
    assert kwargs["shell"] is False and kwargs["timeout"] == 600 and kwargs["cwd"] == str(invocation.cwd)
    assert response.raw_response["stdout"] == setup.state["stdout"]
    assert response.raw_response["events"] == events() and response.usage == {"input_tokens": 700, "output_tokens": 100}
    assert response.request_id is None and response.model == contract.MODEL
    parsed = setup.provider.parse_response(invocation, response)
    assert parsed["reference_positive"] == 1 and parsed["reference_available"]
    assert parsed["provenance"]["cli_version"] == "0.120.0"
    bad = deepcopy(response.payload)
    bad["relationship"]["citations"] = [{"passage_id": "S1.B1"}]
    with pytest.raises(ResearchError, match="source_coverage"):
        setup.provider.parse_response(invocation, replace(response, payload=bad))


@pytest.mark.parametrize("missing", ["model", "version", "both"])
def test_absent_provenance_stays_null_and_not_a_reference(setup, missing):
    if missing in {"model", "both"}:
        setup.state["stdout"] = stream(events(model=None))
    if missing in {"version", "both"}:
        config = {**setup.config, "cli_version_observation": None}
        setup.provider = provider.PairProvider(setup.provider.workspace, research=setup.engine,
            session="synthetic-session", runner=setup.mocked, **config)
    invocation, response = execute(setup)
    parsed = setup.provider.parse_response(invocation, response)
    assert parsed["mechanical_reference_positive"] == 1 and parsed["reference_positive"] is None
    assert not parsed["reference_available"] and parsed["provenance_gaps"]
    if missing in {"model", "both"}:
        assert response.model is None and response.raw_response["observed_model"] is None


@pytest.mark.parametrize("fault", ["no_session", "no_intent", "wrong_packet", "wrong_request", "duplicate_intent", "number"])
def test_audit_boundary_denies_before_any_process(setup, fault):
    invocation = setup.provider.prepare(packet())
    row = intended(setup.engine, invocation)
    if fault == "no_session":
        setup.engine._active.clear()
    elif fault == "no_intent":
        setup.engine.ledger.unresolved.clear()
    elif fault == "wrong_packet":
        row["packet"] = setup.engine.ledger.artifacts.put({"wrong": True})
    elif fault == "wrong_request":
        row["request"] = setup.engine.ledger.artifacts.put({"wrong": True})
    elif fault == "duplicate_intent":
        setup.engine.ledger.unresolved["another"] = dict(row)
    else:
        row["number"] = 2
    with pytest.raises((AuditError, ResearchError)):
        setup.provider.complete_prepared(invocation)
    assert setup.calls == []


def test_no_standalone_convenience_or_same_instance_redispatch(setup):
    with pytest.raises(AuditError, match="shared_gateway"):
        setup.provider.complete(packet())
    invocation, _ = execute(setup)
    with pytest.raises(AuditError, match="already_dispatched"):
        setup.provider.complete_prepared(invocation)
    assert len(setup.calls) == 1


@pytest.mark.parametrize("fault", ["stdin", "argv", "schema_file", "worker_rules", "binary", "tokens", "packet", "model", "timeout"])
def test_frozen_input_and_transport_changes_deny_dispatch(setup, fault):
    invocation = setup.provider.prepare(packet())
    intended(setup.engine, invocation)
    if fault == "stdin":
        invocation = replace(invocation, stdin=invocation.stdin + " ")
    elif fault == "argv":
        invocation = replace(invocation, command=(*invocation.command[:-1], "--search", "-"))
    elif fault == "schema_file":
        (invocation.cwd / "response-schema.json").write_text("{}")
    elif fault == "worker_rules":
        (invocation.cwd / "AGENTS.md").write_text("changed")
    elif fault == "binary":
        Path(setup.provider.executable).write_bytes(b"different")
    elif fault == "tokens":
        setup.provider.count_tokens = lambda _: 1
    elif fault == "packet":
        invocation.packet["documents"][0]["body"] += "changed"
    elif fault == "model":
        setup.provider.model = "gpt-6-luna"
    else:
        setup.provider.timeout_seconds = 601
    with pytest.raises((AuditError, ResearchError)):
        setup.provider.complete_prepared(invocation)
    assert setup.calls == []


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"])
def test_api_credentials_and_endpoint_overrides_never_fallback(setup, monkeypatch, name):
    monkeypatch.setenv(name, "synthetic-placeholder")
    with pytest.raises(ResearchError, match="forbidden"):
        setup.provider.prepare(packet())
    assert setup.calls == []


DETAIL = "unexpected status 403 Forbidden: Unknown error, url: wss://chatgpt.com/backend-api/codex/responses, cf-ray: abc123-AMS"
WARNING = {"type": "error", "message": "Reconnecting... 1/5 (" + DETAIL + ")"}
FALLBACK = {"type": "item.completed", "item": {"type": "error", "message": "Falling back from WebSockets to HTTPS transport. " + DETAIL}}


def test_only_known_prefinal_warning_recovery_preserves_every_original_event(setup):
    saved = events(extra=[WARNING, FALLBACK])
    setup.state["stdout"] = stream(saved)
    invocation, response = execute(setup)
    assert response.payload == judgment() and response.raw_response["events"] == saved
    assert response.raw_response["stdout"] == setup.state["stdout"]
    assert response.raw_response["permitted_transport_warnings"] == [WARNING, FALLBACK]
    assert response.raw_response["original_parser_failure"] and response.raw_response["coordinator_retries"] == 0
    assert response.raw_response["remote_attempt_uniqueness_proven"] is False
    assert setup.provider.parse_response(invocation, response)["reference_positive"] == 1
    assert len(setup.calls) == 1


@pytest.mark.parametrize("fault", ["tool", "warning_and_tool", "unknown_warning", "warning_after_final", "warning_with_bad_line",
                                  "wrong_model", "conflicting_model", "double_completed", "missing_completed", "nonzero", "bad_json"])
def test_forbidden_activity_or_unclean_terminal_never_yields_reference(setup, fault):
    value = events()
    if fault == "tool":
        value.insert(2, {"type": "item.started", "item": {"type": "command_execution", "command": "synthetic"}})
    elif fault == "warning_and_tool":
        value[2:2] = [WARNING, {"type": "item.started", "item": {"type": "web_search"}}]
    elif fault == "unknown_warning":
        value.insert(2, {"type": "error", "message": "Unknown error"})
    elif fault == "warning_after_final":
        value.insert(-1, WARNING)
    elif fault == "warning_with_bad_line":
        value.insert(2, WARNING)
    elif fault == "wrong_model":
        value[0]["model"] = "gpt-6-luna"
    elif fault == "conflicting_model":
        value[-1]["model"] = "gpt-6-luna"
    elif fault == "double_completed":
        value.append(value[-1])
    elif fault == "missing_completed":
        value.pop()
    elif fault == "nonzero":
        setup.state["returncode"] = 1
    elif fault == "bad_json":
        value[-2]["item"]["text"] = "not JSON"
    setup.state["stdout"] = stream(value) + ("\nmalformed line" if fault == "warning_with_bad_line" else "")
    invocation, response = execute(setup)
    assert response.payload is None
    assert response.raw_response["stdout"] == setup.state["stdout"]
    assert response.raw_response["transport_status"] == "invalid_or_unknown"
    with pytest.raises(ResearchError, match="response_unavailable"):
        setup.provider.parse_response(invocation, response)
    assert len(setup.calls) == 1


@pytest.mark.parametrize("fault", ["timeout", "start", "secret", "no_usage"])
def test_unknown_outcome_retention_and_unavailable_usage_never_invented(setup, fault):
    if fault == "timeout":
        setup.state["error"] = subprocess.TimeoutExpired("synthetic", 600, output=b'{"type":"thread.started"}')
    elif fault == "start":
        setup.state["error"] = OSError("synthetic unavailable executable")
    elif fault == "secret":
        setup.state["stdout"] = "sk-" + "a" * 48
    else:
        value = events()
        del value[-1]["usage"]
        setup.state["stdout"] = stream(value)
    invocation, response = execute(setup)
    assert response.usage is None
    if fault == "no_usage":
        assert setup.provider.parse_response(invocation, response)["reference_positive"] == 1
    else:
        assert response.payload is None
        assert response.raw_response["unknown_outcome"] is (fault != "start")
    if fault == "secret":
        assert response.raw_response["stdout"] is None and response.raw_response["stderr"] is None
        assert "prohibited_output_sha256" in response.raw_response


@pytest.mark.parametrize("fault", ["bad_command", "nonzero", "unknown_version", "extra_field"])
def test_cli_version_requires_exact_prior_observation_without_probe(setup, fault):
    observation = deepcopy(setup.config["cli_version_observation"])
    if fault == "bad_command":
        observation["command"] = [str(setup.config["executable"]), "exec"]
    elif fault == "nonzero":
        observation["exit_code"] = 1
    elif fault == "unknown_version":
        observation["stdout"] = "unknown"
    else:
        observation["model_guess"] = contract.MODEL
    with pytest.raises(ResearchError):
        provider.version_from_observation(setup.config["executable"], observation)
    assert setup.calls == []


class SyntheticStudy(Research):
    fixture = None

    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": "synthetic-pair-provider",
            "content": {"method": "Synthetic shared-gateway transport verification; no actual CLI or model."}})
        instance = provider.PairProvider(self.ledger.root / "workers", research=self, session=session,
                                        runner=self.fixture.mocked, **self.fixture.config)
        invocation = instance.prepare(packet())
        row = intended(self, invocation)
        self.ledger.append(session, "model.attempt.intended", row)
        index, response = next(self.gateway.codex_dispatch(session, instance, [(invocation, row["attempt"])], 1))
        assert index == 0
        raw_artifact = self.ledger.artifacts.put(asdict(response))
        parsed = instance.parse_response(invocation, response)
        result_id = self.ledger.record(session, "synthetic_final_pair_response", row["task_key"],
            {"response": raw_artifact, "packet": row["packet"], "dispatch": row["dispatch"], "parsed": parsed})
        self.ledger.append(session, "model.attempt.completed", {"attempt": row["attempt"], "response": raw_artifact,
            "assessment": result_id, "status": "valid", "completed_at": utc()})
        del self.ledger.unresolved[row["attempt"]]
        return {"result": result_id, "positive": parsed["reference_positive"], "remaining": len(self.ledger.unresolved)}


def test_real_synthetic_research_gateway_retains_intent_before_mock_dispatch(tmp_path, setup):
    study = SyntheticStudy(tmp_path / "synthetic-owner", config=Config(offline=True))
    study.fixture = setup
    try:
        result = study.execute("status", {}, objective="Synthetic pair transport boundary", actor="test:synthetic")
        assert result["positive"] == 1 and result["remaining"] == 0
        assert len(setup.calls) == 1
        saved = study.ledger.get(result["result"], "synthetic_final_pair_response")
        response = study.ledger.artifacts.read(saved["response"])
        assert response["raw_response"]["adapter_method"] == provider.METHOD
        kinds = [row[0] for row in study.ledger.db.execute("SELECT kind FROM events ORDER BY seq")]
        assert kinds.index("model.attempt.intended") < kinds.index("model.attempt.completed")
        study.ledger.verify()
    finally:
        study.close()
    reopened = Research(tmp_path / "synthetic-owner", config=Config(offline=True))
    try:
        reopened.execute("status", {}, objective="Verify persisted synthetic provider history", actor="test:synthetic")
        assert not reopened.ledger.unresolved
        assert reopened.ledger.get(result["result"], "synthetic_final_pair_response")["parsed"]["reference_positive"] == 1
        assert len(setup.calls) == 1
    finally:
        reopened.close()
