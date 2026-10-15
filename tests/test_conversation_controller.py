"""Controller and local HTTP checks with synthetic, store-free research doubles."""

from __future__ import annotations

from datetime import datetime, timezone
from http.client import HTTPConnection
import json
from pathlib import Path
import threading
import time
from typing import Any
import uuid

import pytest

from newsresearch.common import ResearchError
from newsresearch.conversation_controller import ConversationController
from newsresearch.result_viewer import create_server


def request_data(**changes: Any) -> dict[str, Any]:
    return {"request_id": str(uuid.uuid4()), "question": "Explain the supplied evidence.",
            "scope": "current", "actor": "synthetic:reviewer", "confirm_model": True, **changes}


class FakeFactory:
    def __init__(self) -> None:
        self.constructed: list[Any] = []
        self.calls: list[Any] = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.closed = threading.Event()
        self.failure: Exception | None = None
        self.close_failure: Exception | None = None
        self.returned_result: dict[str, Any] | None = None

    def __call__(self, workspace: Path, *, config: Any):
        self.constructed.append((workspace, config))
        factory = self

        class Engine:
            def execute(self, operation: str, payload: Any, **kwargs: Any):
                factory.calls.append((operation, payload, kwargs))
                factory.started.set()
                if not factory.release.wait(5):
                    raise RuntimeError("Synthetic worker was not released")
                if factory.failure:
                    raise factory.failure
                if factory.returned_result is not None:
                    return factory.returned_result
                turn = {"id": "turn-1", "question": payload["question"], "status": "answered",
                    "answer": {"normalized_answer": {"status": "answered", "answer": "Synthetic response", "citations": []}},
                    "coverage": {"passages": 2}, "presentation": {"id": "presentation-1", "markdown": "Synthetic response"},
                    "attempt": "attempt-1", "session": "session-1", "versions": kwargs["versions"],
                    "request_ref": "private-packet", "raw_response": "private-model-wire", "path": "private-path"}
                return {"turn": turn, "state": {"turns": [turn], "conversation": "conversation-1", "definition": "definition-1"},
                    "retrieval": {"presentation": {"id": "retrieval-presentation", "markdown": "Synthetic retrieval"}}}

            def close(self):
                factory.closed.set()
                if factory.close_failure:
                    raise factory.close_failure

        return Engine()


@pytest.fixture
def controlled(tmp_path: Any):
    factory = FakeFactory()
    controller = ConversationController(tmp_path / "never-opened-store",
        {"id": "saved-result", "versions": {"dataset": "dataset-v1"}},
        model="synthetic-model", executable="synthetic-codex", research_factory=factory)
    yield controller, factory
    factory.release.set()
    if factory.constructed:
        factory.closed.wait(5)


def completed(controller: Any, identifier: str) -> dict[str, Any]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = controller.job(identifier)
        if job and job["status"] in {"completed", "failed"} and controller.snapshot()["pending"] is None:
            return job
        time.sleep(0.002)
    raise AssertionError("Synthetic asynchronous job did not complete")


def test_snapshot_and_unknown_job_never_open_a_store(controlled: Any) -> None:
    controller, factory = controlled
    state = controller.snapshot()
    assert state["enabled"] and state["history_loaded"] is False and state["turns"] == []
    assert controller.job("unknown") is None
    state["turns"].append({"modified": True})
    assert controller.snapshot()["turns"] == []
    assert factory.constructed == [] and factory.calls == []


def test_submit_is_async_idempotent_and_rejects_busy_or_conflicting_requests(controlled: Any) -> None:
    controller, factory = controlled
    data = request_data()
    first = controller.submit(data)
    assert factory.started.wait(2)
    assert controller.job(first["job_id"])["status"] == "running"
    assert controller.submit(dict(data)) == first
    with pytest.raises(ResearchError, match="different instructions"):
        controller.submit({**data, "question": "Different question"})
    with pytest.raises(ResearchError, match="already running"):
        controller.submit(request_data())
    assert len(factory.calls) == 1
    factory.release.set()
    job = completed(controller, first["job_id"])
    assert job["status"] == "completed" and job["result"]["answer"]["answer"] == "Synthetic response"
    assert controller.submit(dict(data)) == first and len(factory.calls) == 1
    assert not {"request_ref", "raw_response", "path"}.intersection(job["result"])
    job["result"]["answer"]["answer"] = "Caller mutation"
    assert controller.job(first["job_id"])["result"]["answer"]["answer"] == "Synthetic response"


def test_concrete_approval_and_dataset_binding_are_created_only_after_submission(controlled: Any) -> None:
    controller, factory = controlled
    data = request_data(scope="search", query="synthetic local keywords")
    job = controller.submit(data)
    assert factory.started.wait(2)
    operation, payload, context = factory.calls[0]
    assert operation == "conversation_chat" and context["actor"] == data["actor"]
    assert context["versions"] == {"dataset": "dataset-v1"}
    assert payload["result"] == "saved-result" and payload["question"] == data["question"]
    assert payload["codex_model"] == "synthetic-model" and payload["codex_executable"] == "synthetic-codex"
    assert payload["query"] == data["query"] and factory.constructed[0][1].offline is False
    approval = payload["run_approval"]
    assert approval["approved_by"] == data["actor"] and data["question"] in approval["instruction"]
    assert approval["max_attempts"] == 1 and approval["allow_codex_account"] is True
    assert approval["allow_external_processing"] is True
    assert datetime.fromisoformat(approval["expires_at"]) > datetime.now(timezone.utc)
    factory.release.set()
    assert completed(controller, job["job_id"])["result"]["retrieval"]["id"] == "retrieval-presentation"


@pytest.mark.parametrize("changes", [
    {"confirm_model": False}, {"scope": "all_sources"}, {"question": " "}, {"actor": ""},
    {"request_id": "not-a-uuid"}, {"workspace": "browser-supplied-path"},
    {"question": "é" * 4001}, {"actor": "é" * 81}, {"query": "é" * 1001},
])
def test_invalid_or_unapproved_input_never_constructs_research(controlled: Any, changes: Any) -> None:
    controller, factory = controlled
    with pytest.raises(ResearchError):
        controller.submit(request_data(**changes))
    assert factory.constructed == [] and controller.snapshot()["pending"] is None


def test_worker_failures_are_sanitized_and_allow_a_new_request(controlled: Any) -> None:
    controller, factory = controlled
    factory.failure = RuntimeError("sensitive private path and model payload")
    job = controller.submit(request_data())
    assert factory.started.wait(2)
    factory.release.set()
    failed = completed(controller, job["job_id"])
    assert failed["status"] == "failed" and failed["error_type"] == "RuntimeError"
    assert "sensitive" not in json.dumps(failed) and factory.closed.is_set()
    factory.failure = None
    second = controller.submit(request_data())
    assert completed(controller, second["job_id"])["status"] == "completed"


def test_close_failure_is_sanitized_and_never_leaves_the_controller_busy(controlled: Any) -> None:
    controller, factory = controlled
    factory.close_failure = RuntimeError("sensitive storage-close detail")
    factory.release.set()
    first = controller.submit(request_data())
    job = completed(controller, first["job_id"])
    assert job["status"] == "failed" and job["error_type"] == "RuntimeError"
    assert "sensitive" not in json.dumps(job) and controller.snapshot()["pending"] is None
    factory.close_failure = None
    second = controller.submit(request_data())
    assert completed(controller, second["job_id"])["status"] == "completed"


def test_thread_start_failure_is_sanitized_without_opening_research(controlled: Any, monkeypatch: Any) -> None:
    from newsresearch import conversation_controller

    controller, factory = controlled

    class BrokenThread:
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        def start(self):
            raise RuntimeError("sensitive thread-start detail")

    with monkeypatch.context() as patch:
        patch.setattr(conversation_controller.threading, "Thread", BrokenThread)
        first = controller.submit(request_data())
    job = controller.job(first["job_id"])
    assert job["status"] == "failed" and job["error_type"] == "RuntimeError"
    assert "sensitive" not in json.dumps(job) and controller.snapshot()["pending"] is None
    assert factory.constructed == [] and factory.calls == []
    factory.release.set()
    second = controller.submit(request_data())
    assert completed(controller, second["job_id"])["status"] == "completed"


def test_replaying_an_older_turn_preserves_later_history_and_its_current_definition(controlled: Any) -> None:
    controller, factory = controlled
    old = {"id": "old-turn", "question": "Old question", "scope": "search", "processing_status": "valid",
        "definition": "old-definition", "result": {"status": "answered", "answer": "Old answer", "citations": []}}
    newer = {"id": "new-turn", "question": "New question", "scope": "current", "processing_status": "unknown",
        "definition": "new-definition", "result": None}
    retrieval = {"id": "old-retrieval", "markdown": "Original captured search overview"}
    factory.returned_result = {"turn": old, "retrieval": None,
        "state": {"turns": [old, newer], "conversation": "conversation-1", "definition": "new-definition",
                  "definitions": [{"id": "old-definition", "presentation": retrieval}, {"id": "new-definition"}]}}
    factory.release.set()
    submitted = controller.submit(request_data(scope="search", question="Old question"))
    job = completed(controller, submitted["job_id"])
    state = controller.snapshot()
    assert [turn["id"] for turn in state["turns"]] == ["old-turn", "new-turn"]
    assert state["definition"] == "new-definition"
    assert state["turns"][0]["retrieval"] == retrieval
    assert state["turns"][1]["status"] == "unknown" and state["turns"][1]["answer"] == {}
    assert job["result"]["id"] == "old-turn" and job["result"]["retrieval"] == retrieval


class StubController:
    def __init__(self) -> None:
        self.posts: list[Any] = []

    def snapshot(self):
        return {"enabled": True, "turns": [], "history_loaded": False}

    def job(self, identifier: str):
        return {"job_id": "known", "status": "completed"} if identifier == "known" else None

    def submit(self, value: Any):
        if not isinstance(value, dict):
            raise ResearchError("Invalid synthetic request")
        self.posts.append(value)
        return {"job_id": "known"}


@pytest.fixture
def server_factory(tmp_path: Any):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("index.html", "app.js", "app.css"):
        (assets / name).write_text("Synthetic public asset", encoding="utf-8")
    servers = []

    def factory(controller: Any = None, **kwargs: Any):
        server = create_server(b'{"id":"synthetic","question":"Synthetic","rows":[]}', assets,
            0, conversation=controller, **kwargs)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return server

    yield factory
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join()


def http(server: Any, path: str = "/api/conversation", *, method: str = "GET",
         body: Any = None, headers: Any = None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.mark.parametrize("body", [b"[" * 1100 + b"0" + b"]" * 1100,
    json.dumps(request_data(question="\ud800")).encode("ascii")])
def test_malformed_unicode_and_nested_json_return_400_without_research(server_factory: Any, controlled: Any, body: bytes) -> None:
    controller, factory = controlled
    server = server_factory(controller)
    status, _, _ = http(server, method="POST", body=body,
        headers={"Origin": f"http://127.0.0.1:{server.server_port}", "Content-Type": "application/json"})
    assert status == 400 and not factory.constructed and not factory.calls


def post_headers(server: Any) -> dict[str, str]:
    return {"Origin": f"http://127.0.0.1:{server.server_port}", "Content-Type": "application/json"}


def test_disabled_conversation_routes_never_start_research(server_factory: Any) -> None:
    server = server_factory()
    status, _, body = http(server)
    assert status == 200 and json.loads(body) == {"enabled": False, "turns": []}
    assert http(server, method="POST", headers=post_headers(server), body="{}")[0] == 404
    assert http(server, "/api/conversation/jobs/unknown")[0] == 404


def test_get_and_head_routes_only_read_controller_snapshots(controlled: Any, server_factory: Any) -> None:
    controller, factory = controlled
    server = server_factory(controller)
    assert http(server)[0] == 200
    assert http(server, method="HEAD")[2] == b""
    assert http(server, "/api/conversation/jobs/missing")[0] == 404
    assert factory.constructed == []


def test_conversation_routes_require_authentication_in_paired_mode(server_factory: Any) -> None:
    controller = StubController()
    server = server_factory(controller, pairing_key="synthetic-conversation-pairing-" + "x" * 40)
    assert http(server)[0] == 401
    assert http(server, "/api/conversation/jobs/known")[0] == 401
    assert http(server, method="POST", headers=post_headers(server), body="{}")[0] == 401
    assert controller.posts == []


@pytest.mark.parametrize("extra", [{"Origin": "http://malicious.test"}, {"Host": "malicious.test"},
                                  {"Sec-Fetch-Site": "cross-site"}, {"Origin": ""}])
def test_post_conversation_enforces_origin_host_and_fetch_site(server_factory: Any, extra: Any) -> None:
    controller = StubController()
    server = server_factory(controller)
    assert http(server, method="POST", headers={**post_headers(server), **extra}, body="{}")[0] == 403
    assert controller.posts == []


@pytest.mark.parametrize("body,extra", [("not json", {}), ("[]", {}), ("null", {}),
    ("{}", {"Content-Type": "text/plain"}), ("x" * 16385, {}),
    ("{}", {"Content-Length": "-1"}), ("{}", {"Content-Length": "invalid"}),
    ("{}", {"Transfer-Encoding": "chunked"})],
    ids=["malformed", "array", "null", "mime", "oversized", "negative_length", "invalid_length", "chunked"])
def test_post_conversation_rejects_invalid_json_types_and_transport_limits(server_factory: Any, body: str, extra: Any) -> None:
    controller = StubController()
    server = server_factory(controller)
    status, _, response = http(server, method="POST", headers={**post_headers(server), **extra}, body=body)
    assert status == 400 and b"Invalid" in response
    assert controller.posts == []


def test_http_duplicate_requests_use_the_controller_idempotency_guard(controlled: Any, server_factory: Any) -> None:
    controller, factory = controlled
    server = server_factory(controller)
    data = request_data()
    body = json.dumps(data)
    first = http(server, method="POST", headers=post_headers(server), body=body)
    assert first[0] == 202 and factory.started.wait(2)
    second = http(server, method="POST", headers=post_headers(server), body=body)
    assert second[0] == 202 and json.loads(first[2]) == json.loads(second[2])
    assert len(factory.calls) == 1
    conflict = json.dumps({**data, "question": "Conflicting input"})
    assert http(server, method="POST", headers=post_headers(server), body=conflict)[0] == 400
    factory.release.set()
    job_id = json.loads(first[2])["job_id"]
    assert completed(controller, job_id)["status"] == "completed"
    assert http(server, f"/api/conversation/jobs/{job_id}")[0] == 200
