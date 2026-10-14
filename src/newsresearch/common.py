from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tomllib
from typing import Any

Json = dict[str, Any]


class ResearchError(RuntimeError):
    """An enforced research invariant was not satisfied."""


class AuditError(ResearchError):
    """Required durable provenance cannot be established."""


def require_active(engine: Any, session: str) -> None:
    if session not in engine._active:
        raise AuditError("Research handler requires an active audited operation")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


SECRET_KEY = re.compile(r"^(?:api[_-]?key|authorization|password|access[_-]?token|secret|credential)$", re.I)
SECRET_VALUE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|Bearer\s+\S+)"
)


def require_no_credentials(value: Any) -> None:
    """Reject credentials, rather than silently changing application payloads."""
    if isinstance(value, dict):
        for key, item in value.items():
            if SECRET_KEY.match(str(key)):
                raise ResearchError("Credential-like field is forbidden in persistent research payloads")
            require_no_credentials(str(key))
            require_no_credentials(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            require_no_credentials(item)
    elif isinstance(value, str) and SECRET_VALUE.search(value):
        raise ResearchError("Credential-like content is forbidden in persistent research payloads")


@dataclass(frozen=True)
class Config:
    schema_version: int = 1
    offline: bool = True
    max_articles: int = 20000
    max_attempts_per_run: int = 3

    @classmethod
    def load(cls, path: Path | None) -> Config:
        content = tomllib.loads(path.read_text(encoding="utf-8")) if path and path.exists() else {}
        require_no_credentials(content)
        instance = cls(**content)
        if (
            instance.schema_version != 1
            or instance.max_articles < 1
            or not 1 <= instance.max_attempts_per_run <= 5
        ):
            raise ResearchError("Unsupported configuration")
        return instance

    def payload(self) -> Json:
        return asdict(self)


@dataclass(frozen=True)
class Context:
    objective: str
    actor: str
    versions: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.objective.strip() or not self.actor.strip():
            raise ResearchError("Every operation needs an objective and identifiable actor")
        require_no_credentials(asdict(self))


def default_workspace() -> Path:
    if os.environ.get("NEWSRESEARCH_WORKSPACE"):
        return Path(os.environ["NEWSRESEARCH_WORKSPACE"])
    parent = Path(os.environ["LOCALAPPDATA"]) if os.name == "nt" else Path.home() / ".local/share"
    return parent / "AI-In-the-News/research"
