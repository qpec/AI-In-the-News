"""Prospective account-only pair transport; no CLI entry point or study execution.

The coordinator must register the method/CLI/tokenizer, enforce task and quota
limits/no retry, and persist packet + request + invocation intent inside
Research.execute before using the shared gateway. This adapter checks that active
boundary and exact intent too; it does not authorize research or select samples.
Only the existing CLI subprocess transport is reused. No API fallback is present.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import subprocess
import threading
import uuid

import final_validation_contract as contract
from newsresearch.astra_incident_validation import terminal_response
from newsresearch.codex_provider import CodexCLIProvider, PreparedCodexInvocation, build_prompt
from newsresearch.common import AuditError, ResearchError, digest, require_active, require_no_credentials

METHOD = "cybercrime-final-codex-pair-provider-v1"
TRANSPORT = "codex-cli-full-pair-reference-v1"
TIMEOUT_SECONDS = 600
MAX_OUTPUT_BYTES = 4_000_000
VERSION_PATTERN = re.compile(r"codex-cli ([0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?)\s*\Z")


def require(value, code):
    if not value:
        raise ResearchError("final_pair_provider_" + code)


def version_from_observation(executable, observation):
    """Consume a prior registered, non-model --version observation; never run it."""
    if observation is None:
        return None
    require(isinstance(observation, dict) and set(observation) == {"command", "stdout", "stderr", "exit_code"},
            "cli_version_observation_fields")
    require_no_credentials(observation)
    require(observation["command"] == [str(executable), "--version"] and type(observation["exit_code"]) is int and observation["exit_code"] == 0
            and isinstance(observation["stdout"], str) and observation["stderr"] == "", "cli_version_observation")
    match = VERSION_PATTERN.fullmatch(observation["stdout"])
    require(match is not None, "cli_version_unrecognized")
    return match.group(1)


@dataclass(frozen=True)
class PreparedPairInvocation(PreparedCodexInvocation):
    packet: dict
    cli_binding: dict
    tokenizer_identity: dict
    invocation_id: str

    def manifest(self):
        return {**super().manifest(), "transport": TRANSPORT, "adapter_method": METHOD,
            "invocation_id": self.invocation_id, "pair_packet_sha256": self.packet["packet_sha256"],
            "request_sha256": self.packet["request_sha256"], "input_tokens_proxy": self.packet["input_tokens_proxy"],
            "max_input_tokens": self.packet["max_input_tokens"], "tokenizer_identity": self.tokenizer_identity,
            "cli_binding": self.cli_binding, "reasoning_effort": contract.REASONING_EFFORT, "fast_mode": False,
            "timeout_seconds": TIMEOUT_SECONDS, "max_output_bytes": MAX_OUTPUT_BYTES,
            "account_dollar_cost": None, "remote_attempt_uniqueness_proven": False}


def terminal_metadata(response):
    """Keep the exact stream; narrowly reuse the known pre-final fallback parser.

    Its permitted warning recovery is allowed only if every original nonempty
    stdout line is retained as an event. A dropped malformed line cannot vanish
    during warning recovery. No filtering conceals tools or changes model JSON.
    """
    original = deepcopy(response.raw_response or {})
    events = original.get("events", [])
    try:
        complete_stream = [json.loads(line) for line in (original.get("stdout") or "").splitlines() if line.strip()]
    except (ValueError, TypeError):
        complete_stream = None
    normalized = terminal_response(response) if complete_stream == events else response
    raw = dict(normalized.raw_response or {})
    warnings = raw.get("permitted_transport_warnings", [])
    remaining_warnings = list(warnings)
    substantive = []
    for event in events:
        if event in remaining_warnings:
            remaining_warnings.remove(event)
        else:
            substantive.append(event)
    terminal_complete = bool(substantive and substantive[0].get("type") == "thread.started"
        and substantive[-1].get("type") == "turn.completed"
        and sum(e.get("type") == "thread.started" for e in substantive) == 1
        and sum(e.get("type") == "turn.started" for e in substantive) == 1
        and sum(e.get("type") == "turn.completed" for e in substantive) == 1)
    forbidden = any(e.get("type") not in {"thread.started", "turn.started", "turn.completed", "item.started", "item.updated", "item.completed"}
        or e.get("type", "").startswith("item.") and (not isinstance(e.get("item"), dict)
            or e["item"].get("type") not in {"agent_message", "reasoning"}) for e in substantive)
    # Base failures, nonzero exit, timeout and prohibited output are never repaired.
    if raw.get("transport_status") == "returned" and (complete_stream != events or not terminal_complete or forbidden):
        raw.update(failure="final_pair_terminal_shape_or_activity", transport_status="invalid_or_unknown")
        normalized = replace(normalized, payload=None)
    raw.update(terminal_complete=terminal_complete, tool_activity_detected=forbidden,
        base_transport_failure=original.get("failure"), coordinator_retries=0)
    return replace(normalized, raw_response=raw)


class PairProvider(CodexCLIProvider):
    """Prepare inside an audited operation; dispatch only through its gateway.

    `cli_version_observation` and `tokenizer_identity` must be registered evidence,
    not guessed settings. The supplied callable is checked against each exact
    stdin count before preparation and dispatch. No model/account probe is made.
    The coordinator remains responsible for durable cross-process no-retry and
    selected primary/QC/adjudication identities; roles never enter the prompt.
    A registered native executable is preferred. A shim's file hash alone does
    not attest its target bundle; the coordinator must pin that dependency too.
    """

    def __init__(self, workspace, *, research, session, executable, executable_sha256,
                 cli_version_observation, tokenizer_identity, count_tokens, runner=subprocess.run):
        executable = Path(executable)
        require(executable.is_absolute(), "absolute_executable_required")
        require(isinstance(executable_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", executable_sha256), "binary_digest")
        require(isinstance(tokenizer_identity, dict) and set(tokenizer_identity) == {"encoding", "library", "version"}
                and all(isinstance(v, str) and v.strip() for v in tokenizer_identity.values()), "tokenizer_identity")
        require(callable(count_tokens), "tokenizer_callable")
        require_no_credentials(tokenizer_identity)
        self.research, self.session, self.count_tokens = research, session, count_tokens
        self.cli_binding = {"executable": str(executable), "binary_sha256": executable_sha256,
            "version_observation": deepcopy(cli_version_observation),
            "cli_version": version_from_observation(executable, cli_version_observation)}
        self.tokenizer_identity = deepcopy(tokenizer_identity)
        self._profile_sha256 = digest([self.cli_binding, self.tokenizer_identity])
        self._dispatch_lock, self._consumed = threading.Lock(), set()
        super().__init__(Path(workspace), executable=str(executable), model=contract.MODEL,
            timeout_seconds=TIMEOUT_SECONDS, max_input_bytes=contract.MAX_INPUT_BYTES,
            max_output_bytes=MAX_OUTPUT_BYTES, runner=runner)

    def _check_binding(self):
        require_active(self.research, self.session)
        require(digest([self.cli_binding, self.tokenizer_identity]) == self._profile_sha256, "registered_profile_changed")
        require(self.model == contract.MODEL and self.executable == self.cli_binding["executable"]
            and self.timeout_seconds == TIMEOUT_SECONDS and self.max_input_bytes == contract.MAX_INPUT_BYTES
            and self.max_output_bytes == MAX_OUTPUT_BYTES, "transport_settings_changed")
        try:
            actual = hashlib.sha256(Path(self.executable).read_bytes()).hexdigest()
        except OSError as error:
            raise ResearchError("final_pair_provider_binary_unavailable") from error
        require(actual == self.cli_binding["binary_sha256"], "binary_changed")

    def _command(self, cwd):
        command = super()._command(cwd)
        return (*command[:-1], "-c", 'model_reasoning_effort="medium"', "-c", "features.fast_mode=false",
                "-c", 'forced_login_method="chatgpt"', command[-1])

    def prepare(self, packet):
        self._check_binding()
        contract.validate_for_dispatch(packet, count_tokens=self.count_tokens)
        packet = deepcopy(packet)
        original = super().prepare(packet["request"])
        return PreparedPairInvocation(original.command, original.cwd, contract.cli_prompt(packet["request"]),
            original.schema, original.request, original.configured_model, packet,
            deepcopy(self.cli_binding), deepcopy(self.tokenizer_identity), str(uuid.uuid4()))

    def _validate_prepared(self, prepared):
        self._check_binding()
        require(isinstance(prepared, PreparedPairInvocation), "prepared_type")
        contract.validate_for_dispatch(prepared.packet, count_tokens=self.count_tokens)
        require(prepared.cli_binding == self.cli_binding and prepared.tokenizer_identity == self.tokenizer_identity,
                "prepared_profile_changed")
        require(prepared.request == prepared.packet["request"] and prepared.stdin == prepared.packet["stdin"]
                and prepared.stdin == contract.cli_prompt(prepared.request), "prepared_pair_changed")
        super()._validate_prepared(replace(prepared, stdin=build_prompt(prepared.request)))

    def complete(self, request):
        raise AuditError("final_pair_requires_registered_prepare_intent_and_shared_gateway")

    def _require_intent(self, prepared):
        require_active(self.research, self.session)
        manifest = prepared.manifest()
        matches = [row for row in list(self.research.ledger.unresolved.values()) if row.get("dispatch") == digest(manifest)]
        if len(matches) != 1:
            raise AuditError("final_pair_exact_unresolved_intent_required")
        row = matches[0]
        artifacts = self.research.ledger.artifacts
        if (row.get("number") != 1 or not row.get("attempt") or not row.get("task_key")
                or artifacts.read(row["dispatch"]) != manifest
                or artifacts.read(row["request"]) != prepared.request
                or not row.get("packet") or artifacts.read(row["packet"]) != prepared.packet):
            raise AuditError("final_pair_durable_intent_changed")
        return row["attempt"]

    def complete_prepared(self, prepared):
        self._validate_prepared(prepared)
        attempt = self._require_intent(prepared)
        with self._dispatch_lock:
            if attempt in self._consumed:
                raise AuditError("final_pair_attempt_already_dispatched")
            self._consumed.add(attempt)
        response = terminal_metadata(super().complete_prepared(prepared))
        raw = dict(response.raw_response or {})
        raw.update(adapter_method=METHOD, cli_version=self.cli_binding["cli_version"],
            configured_model=contract.MODEL, reasoning_effort=contract.REASONING_EFFORT, fast_mode=False,
            account_dollar_cost=None, attempt=attempt, pair_packet_sha256=prepared.packet["packet_sha256"])
        return replace(response, raw_response=raw)

    def reference_provenance(self, prepared, response):
        """Project adapter-observed metadata after the coordinator retains raw output."""
        raw = response.raw_response or {}
        manifest = prepared.manifest()
        require(raw.get("adapter_method") == METHOD and all(raw.get(key) == manifest[key] for key in
            ("command", "cwd", "stdin_sha256", "request_sha256", "pair_packet_sha256", "cli_binding", "tokenizer_identity",
             "configured_model", "reasoning_effort", "fast_mode")) and raw.get("cli_version") == prepared.cli_binding["cli_version"],
            "response_invocation_binding")
        require(raw.get("observed_model") == response.model and raw.get("usage") == response.usage,
                "response_observation_changed")
        return {"configured_model": raw["configured_model"], "reasoning_effort": raw["reasoning_effort"],
            "fast_mode": raw["fast_mode"], "observed_model": response.model, "cli_version": raw["cli_version"],
            "request_sha256": prepared.packet["request_sha256"], "stdin_sha256": prepared.packet["stdin_sha256"],
            "terminal_complete": raw["terminal_complete"], "tool_activity_detected": raw["tool_activity_detected"],
            "transport_status": raw["transport_status"]}

    def parse_response(self, prepared, response):
        require(response.payload is not None, "response_unavailable")
        return contract.parse(prepared.packet, response.payload,
                              provenance=self.reference_provenance(prepared, response))
