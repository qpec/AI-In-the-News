"""Bounded asynchronous UI adapter; all store access enters Research.execute."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import threading
from typing import Any, Callable
import uuid

from .common import Config, Json, ResearchError, digest, require_no_credentials


class ConversationController:
    """One research writer, no model/research work on GET, no browser-supplied paths."""

    def __init__(self, workspace: Path, result: Json, *, model: str = "gpt-6.1-sol",
                 executable: str = "codex", research_factory: Callable[..., Any] | None = None) -> None:
        from .runtime import Research
        self.workspace = workspace
        self.original = result["id"]
        self.dataset = result["versions"]["dataset"]
        self.model = model
        self.executable = executable
        self.factory = research_factory or Research
        self._lock = threading.Lock()
        self._jobs: dict[str, Json] = {}
        self._requests: dict[str, str] = {}
        self._active: str | None = None
        self._state: Json = {"turns": [], "history_loaded": False}

    def snapshot(self) -> Json:
        with self._lock:
            return {"enabled": True, "initial_result_id": self.original, "actor": None,
                "max_attempts": 1, "search_supported": True, "search_method": "local_fts",
                "search_article_limit": 20, "codex_model": self.model,
                **json.loads(json.dumps(self._state)),
                "pending": dict(self._jobs[self._active]) if self._active else None}

    def job(self, identifier: str) -> Json | None:
        with self._lock:
            job = self._jobs.get(identifier)
            return json.loads(json.dumps(job)) if job else None

    def submit(self, data: Json) -> Json:
        if not isinstance(data, dict) or set(data) - {"request_id", "question", "scope", "actor", "confirm_model", "query"}:
            raise ResearchError("Unsupported conversation request")
        require_no_credentials(data)
        if data.get("confirm_model") is not True:
            raise ResearchError("Explicit authorization for this one Codex answer is required")
        if data.get("scope") not in {"current", "search"}:
            raise ResearchError("Choose current evidence or explicit local keyword search")
        for name, maximum in (("question", 8000), ("actor", 160)):
            if not isinstance(data.get(name), str) or not data[name].strip() or len(data[name].encode("utf-8")) > maximum:
                raise ResearchError("Provide a bounded question and an identifiable operator")
        if "query" in data and (not isinstance(data["query"], str) or len(data["query"].encode("utf-8")) > 2000):
            raise ResearchError("Search keywords must fit within 2000 UTF-8 bytes")
        try:
            request_id = str(uuid.UUID(data["request_id"]))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ResearchError("Provide a stable UUID request ID") from error
        fingerprint = digest(data)
        with self._lock:
            if request_id in self._jobs:
                if self._requests[request_id] != fingerprint:
                    raise ResearchError("A request ID cannot be reused for different instructions")
                return {"job_id": request_id}
            if self._active:
                raise ResearchError("A conversation request is already running; wait for its result")
            if len(self._jobs) >= 200:
                raise ResearchError("Reader request limit reached; restart to continue from the durable audit")
            approval = {"approved_by": data["actor"], "instruction":
                "Answer this exact question using the selected evidence with at most one Codex account attempt. "
                + ("First run explicit local keyword retrieval. " if data["scope"] == "search" else "Reuse current retrieval. ")
                + data["question"], "allow_external_processing": True, "allow_codex_account": True,
                "max_attempts": 1, "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()}
            payload = {"result": self.original, "key": "reader-" + self.original, "request_id": request_id,
                "question": data["question"], "scope": data["scope"], "query": data.get("query", ""),
                "run_approval": approval, "codex_model": self.model, "codex_executable": self.executable}
            self._jobs[request_id] = {"job_id": request_id, "status": "queued"}
            self._requests[request_id] = fingerprint
            self._active = request_id
            try:
                threading.Thread(target=self._run, args=(request_id, data["actor"], payload),
                    name="audited-conversation", daemon=True).start()
            except Exception as error:
                self._jobs[request_id] = {"job_id": request_id, "status": "failed",
                    "error": "The research worker could not start; no model was dispatched.",
                    "error_type": type(error).__name__}
                self._active = None
            return {"job_id": request_id}

    def _run(self, identifier: str, actor: str, payload: Json) -> None:
        engine = None
        try:
            with self._lock:
                self._jobs[identifier]["status"] = "running"
            # Online is process-local and only reached after the concrete UI
            # authorization. This transport has no API-key/Responses fallback.
            engine = self.factory(self.workspace, config=Config(offline=False))
            result = engine.execute("conversation_chat", payload, objective="Answer an exploratory reader follow-up",
                actor=actor, versions={"dataset": self.dataset})
            turns = [normalize_turn(turn) for turn in result["state"]["turns"]]
            current = normalize_turn(result["turn"], scope=payload["scope"])
            definitions = {item["id"]: item for item in result["state"].get("definitions", [])}
            for turn in turns:
                selected = definitions.get(turn["audit"].get("definition"), {})
                if turn["scope"] == "search" and selected.get("presentation"):
                    turn["retrieval"] = selected["presentation"]
            if result.get("retrieval"):
                current["retrieval"] = result["retrieval"]["presentation"]
            elif current["scope"] == "search":
                current["retrieval"] = definitions.get(current["audit"].get("definition"), {}).get("presentation")
            with self._lock:
                self._state = {"turns": turns, "history_loaded": True,
                    "conversation": result["state"]["conversation"], "definition": result["state"]["definition"]}
                # Return the captured presentations alongside the corresponding
                # answer; delivery remains prepared, never verified as read.
                self._state["turns"] = [current if turn["id"] == current["id"] else turn for turn in turns]
                self._jobs[identifier] = {"job_id": identifier, "status": "completed", "result": current}
        except Exception as error:
            with self._lock:
                self._jobs[identifier] = {"job_id": identifier, "status": "failed",
                    "error": "Research stopped. No answer is accepted; inspect the protected audit before retrying.",
                    "error_type": type(error).__name__}
        finally:
            try:
                if engine is not None:
                    engine.close()
            except Exception as error:
                with self._lock:
                    self._jobs[identifier] = {"job_id": identifier, "status": "failed",
                        "error": "Research storage did not close cleanly; inspect its audit before continuing.",
                        "error_type": type(error).__name__}
            finally:
                with self._lock:
                    self._active = None


def normalize_turn(turn: Json, *, scope: str | None = None) -> Json:
    """Expose only answer/provenance fields, never model wire packets or paths."""
    answer = turn.get("answer") or turn.get("result") or {}
    if isinstance(answer, dict) and "normalized_answer" in answer:
        answer = answer["normalized_answer"]
    return {"id": turn["id"], "question": turn.get("question", ""),
        "scope": scope or turn.get("scope", "current"),
        "evidence_mode": turn.get("evidence_mode", "reused selected passages"),
        "status": turn.get("processing_status", turn.get("status")), "answer": answer,
        "coverage": {"selected_articles": turn.get("selected_articles"),
            "evidence_source_count": turn.get("evidence_source_count"),
            "included_passages": turn.get("included_passages"),
            "excluded_passages": len(turn.get("excluded_passages", [])),
            "history_omitted_turns": turn.get("history_omitted_turns"),
            "embedding_requests": turn.get("new_embedding_requests", 0),
            "human_validated": False},
        "presentation": turn.get("presentation"),
        "retrieval": turn.get("retrieval"),
        "audit": {key: turn.get(key) for key in ("id", "conversation", "definition", "session", "attempt", "versions")}}
