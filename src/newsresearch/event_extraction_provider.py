"""Exact Codex transport for source-bound full-article event extraction.

The audited workflow owns approval, manifests and attempt accounting. Calls
must pass through Gateway.codex_dispatch, never this adapter independently.
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
from .event_extraction_contract import PARAMETERS, TASK_KIND, WORKER_RULES, validate_request
from .gateway import BOUNDARY
from .storage import check_permissions, prepare_root


def build_prompt(request: Json) -> str:
    validate_request(request)
    packet = {"boundary": BOUNDARY, "task": TASK_KIND, "instructions": request["instructions"],
              "source": {key: request["source"][key] for key in ("source_version", "title", "published_at")},
              "evidence": [{key: passage[key] for key in ("id", "source_id", "text")}
                           for passage in request["evidence"]], "schema": request["schema"]}
    return json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_text(schema: Json) -> str:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True)


def _reject_links(path: Path) -> None:
    if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents)):
        raise ResearchError("event_extraction_worker_link_forbidden")


@dataclass(frozen=True)
class PreparedExtractionInvocation(PreparedCodexInvocation):
    def manifest(self) -> Json:
        value = super().manifest()
        value.update(transport="codex-cli-event-extraction-v1", worker_rules=WORKER_RULES,
                     reasoning_effort="low")
        return value


class ExtractionProvider(CodexCLIProvider):
    def __init__(self, workspace: Path, config: Json | None = None, *, executable: str = "codex",
                 timeout_seconds: float = 180, max_input_bytes: int = 131072, max_output_bytes: int = 65536,
                 runner: Callable[..., Any] = subprocess.run) -> None:
        configured = config or {}
        if any(configured.get(key, expected) != expected for key, expected in PARAMETERS.items()):
            raise ResearchError("event_extraction_model_or_effort_changed")
        _reject_links(workspace.absolute())
        super().__init__(workspace, executable=configured.get("codex_executable", executable), model="gpt-6-luna",
                         timeout_seconds=configured.get("timeout_seconds", timeout_seconds),
                         max_input_bytes=configured.get("max_input_bytes", max_input_bytes),
                         max_output_bytes=configured.get("max_output_bytes", max_output_bytes), runner=runner)

    def _command(self, cwd: Path) -> tuple[str, ...]:
        command = super()._command(cwd)
        return (*command[:-1], "-c", 'model_reasoning_effort="low"', command[-1])

    def prepare(self, request: Json) -> PreparedExtractionInvocation:
        self._check_auth_environment()
        stdin = build_prompt(request)
        if len(stdin.encode("utf-8")) > self.max_input_bytes:
            raise ResearchError("codex_input_too_large_no_dispatch")
        Draft202012Validator.check_schema(request["schema"])
        _reject_links(self.workspace)
        prepare_root(self.workspace)
        cwd = Path(tempfile.mkdtemp(prefix="codex-extraction-", dir=self.workspace))
        prepare_root(cwd)
        (cwd / "AGENTS.md").write_text(WORKER_RULES, encoding="utf-8", newline="\n")
        (cwd / "response-schema.json").write_text(_schema_text(codex_wire_schema(request["schema"])),
                                                 encoding="utf-8", newline="\n")
        return PreparedExtractionInvocation(self._command(cwd), cwd, stdin, request["schema"], request, self.model)

    def _validate_prepared(self, prepared: PreparedCodexInvocation) -> None:
        _reject_links(self.workspace)
        _reject_links(prepared.cwd)
        cwd = prepared.cwd
        if (not isinstance(prepared, PreparedExtractionInvocation) or cwd.parent != self.workspace
                or cwd.resolve() != cwd or not cwd.name.startswith("codex-extraction-")):
            raise ResearchError("codex_worker_path_changed")
        if prepared.command != self._command(cwd) or prepared.configured_model != self.model:
            raise ResearchError("codex_command_changed")
        if prepared.stdin != build_prompt(prepared.request) or prepared.schema != prepared.request["schema"]:
            raise ResearchError("codex_prepared_input_changed")
        try:
            check_permissions(self.workspace, root=True)
            check_permissions(cwd, root=True)
            rules, schema = cwd / "AGENTS.md", cwd / "response-schema.json"
            for path in (rules, schema):
                _reject_links(path)
                check_permissions(path)
            if rules.read_bytes() != WORKER_RULES.encode("utf-8"):
                raise ResearchError("codex_worker_rules_changed")
            if schema.read_bytes() != _schema_text(codex_wire_schema(prepared.schema)).encode("utf-8"):
                raise ResearchError("codex_worker_schema_changed")
        except OSError as error:
            raise ResearchError("codex_worker_file_unavailable") from error
