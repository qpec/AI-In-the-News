"""Narrow Codex transport for bounded two-lead event references.

The audited caller owns authorization, immutable requests and attempt intent.
This module prepares exact blinded inputs; it never dispatches independently or
claims OS isolation, semantic validation, a remote token cap or cancellation.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable

from jsonschema import Draft202012Validator

from .codex_provider import CodexCLIProvider, PreparedCodexInvocation, codex_wire_schema
from .common import Json, ResearchError
from .event_pair_reference import TASK_KIND, WORKER_RULES, validate_request
from .gateway import BOUNDARY
from .storage import check_permissions, prepare_root


def build_prompt(request: Json) -> str:
    """Expose exactly two leads once, without selection or prior-label metadata."""
    validate_request(request)
    packet = {
        "boundary": BOUNDARY,
        "task": TASK_KIND,
        "inclusion": request["inclusion"],
        "articles": [{key: article[key] for key in
                      ("role", "source_version", "title", "published_at", "coverage")}
                     for article in request["articles"]],
        "evidence": [{key: span[key] for key in ("id", "source_id", "text")}
                     for span in request["evidence"]],
        "schema": request["schema"],
    }
    return json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_text(schema: Json) -> str:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True)


def _reject_link_components(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink() or component.is_junction():
            raise ResearchError("event_eval_worker_link_forbidden")


@dataclass(frozen=True)
class PreparedPairInvocation(PreparedCodexInvocation):
    def manifest(self) -> Json:
        # The base manifest supplies exact command/stdin/schema metadata. Its
        # generic worker-rule choice must be replaced for this separate contract.
        value = super().manifest()
        value.update(transport="codex-cli-event-pair-reference-v1",
                     worker_rules=WORKER_RULES, reasoning_effort="low")
        return value


class PairProvider(CodexCLIProvider):
    """Reuse the observed CLI execution/parser with a separate minimal contract."""

    def __init__(
        self,
        workspace: Path,
        config: Json | None = None,
        *,
        executable: str = "codex",
        timeout_seconds: float = 90,
        max_input_bytes: int = 32768,
        max_output_bytes: int = 16384,
        runner: Callable[..., Any] = subprocess.run,
    ) -> None:
        configured = config or {}
        if (configured.get("codex_model", "gpt-6-luna") != "gpt-6-luna"
                or configured.get("reasoning_effort", "low") != "low"):
            raise ResearchError("event_eval_model_or_effort_changed")
        _reject_link_components(workspace.absolute())
        super().__init__(workspace, executable=configured.get("codex_executable", executable),
                         model="gpt-6-luna",
                         timeout_seconds=configured.get("timeout_seconds", timeout_seconds),
                         max_input_bytes=configured.get("max_input_bytes", max_input_bytes),
                         max_output_bytes=configured.get("max_output_bytes", max_output_bytes),
                         runner=runner)

    def _command(self, cwd: Path) -> tuple[str, ...]:
        command = super()._command(cwd)
        return (*command[:-1], "-c", 'model_reasoning_effort="low"', command[-1])

    def prepare(self, request: Json) -> PreparedPairInvocation:
        self._check_auth_environment()
        stdin = build_prompt(request)
        if len(stdin.encode("utf-8")) > self.max_input_bytes:
            raise ResearchError("codex_input_too_large_no_dispatch")
        Draft202012Validator.check_schema(request["schema"])
        _reject_link_components(self.workspace)
        prepare_root(self.workspace)
        cwd = Path(tempfile.mkdtemp(prefix="codex-judge-pair-", dir=self.workspace))
        prepare_root(cwd)
        (cwd / "AGENTS.md").write_text(WORKER_RULES, encoding="utf-8", newline="\n")
        (cwd / "response-schema.json").write_text(
            _schema_text(codex_wire_schema(request["schema"])), encoding="utf-8", newline="\n")
        return PreparedPairInvocation(self._command(cwd), cwd, stdin,
                                      request["schema"], request, self.model)

    def _validate_prepared(self, prepared: PreparedCodexInvocation) -> None:
        _reject_link_components(self.workspace)
        _reject_link_components(prepared.cwd)
        cwd = prepared.cwd
        if (not isinstance(prepared, PreparedPairInvocation)
                or cwd.parent != self.workspace or cwd.resolve() != cwd
                or not cwd.name.startswith("codex-judge-pair-")):
            raise ResearchError("codex_worker_path_changed")
        if prepared.command != self._command(cwd) or prepared.configured_model != self.model:
            raise ResearchError("codex_command_changed")
        if prepared.stdin != build_prompt(prepared.request) or prepared.schema != prepared.request["schema"]:
            raise ResearchError("codex_prepared_input_changed")
        try:
            check_permissions(self.workspace, root=True)
            check_permissions(cwd, root=True)
            rules_path, schema_path = cwd / "AGENTS.md", cwd / "response-schema.json"
            for path in (rules_path, schema_path):
                _reject_link_components(path)
                check_permissions(path)
            if rules_path.read_bytes() != WORKER_RULES.encode("utf-8"):
                raise ResearchError("codex_worker_rules_changed")
            if schema_path.read_bytes() != _schema_text(codex_wire_schema(prepared.schema)).encode("utf-8"):
                raise ResearchError("codex_worker_schema_changed")
        except OSError as error:
            raise ResearchError("codex_worker_file_unavailable") from error
