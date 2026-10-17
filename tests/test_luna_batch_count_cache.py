"""Synthetic ledger/HTTP checks only, with SQLite and all writes on one thread."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from newsresearch.common import AuditError, ResearchError, canonical, digest
from newsresearch.event_batch_live_gateway import ACTION_IDENTITY_KIND, ACTION_KIND, RECEIPT_KIND, STOP_KIND, EventBatchLiveGateway
from newsresearch.event_batch_transport import BatchReceipt, count_request_body

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    from luna_batch_count_cache import COUNT_REQUEST, LINK_KIND, SUMMARY_KIND, CountManyError, count_many
finally:
    sys.path.pop(0)


class Artifacts:
    def __init__(self, ledger: Any) -> None:
        self.ledger = ledger
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, raw: bytes) -> str:
        self.ledger.check_thread()
        reference = hashlib.sha256(raw).hexdigest()
        self.objects[reference] = raw
        return reference

    def put(self, value: Any) -> str:
        return self.put_bytes(canonical(value).encode())

    def read_bytes(self, reference: str) -> bytes:
        self.ledger.check_thread()
        return self.objects[reference]

    def read(self, reference: str) -> Any:
        return json.loads(self.read_bytes(reference))


class Ledger:
    def __init__(self) -> None:
        self.owner = threading.get_ident()
        self.trace: list[Any] = []
        self.payloads: dict[str, Any] = {}
        self.intended_ids: set[str] = set()
        self.fail_kind: str | None = None
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE records(id TEXT,kind TEXT,logical_key TEXT,created_event INTEGER,payload TEXT)")
        self.artifacts = Artifacts(self)

    def check_thread(self) -> None:
        assert threading.get_ident() == self.owner, "ledger accessed from HTTP worker"

    def append(self, session: str, kind: str, payload: Any) -> None:
        self.check_thread()
        self.trace.append((kind, deepcopy(payload)))

    def record(self, session: str, kind: str, key: str, payload: Any, **kwargs: Any) -> str:
        self.check_thread()
        if self.fail_kind == kind:
            raise AuditError("synthetic_record_failure")
        identifier = digest([kind, key, payload, len(self.trace)])
        self.payloads[identifier] = deepcopy(payload)
        self.db.execute("INSERT INTO records VALUES(?,?,?,?,?)", (identifier, kind, key, len(self.trace), canonical(payload)))
        self.trace.append((kind, identifier))
        if kind == ACTION_KIND:
            self.intended_ids.add(payload["action_id"])
        return identifier

    def get(self, identifier: str, kind: str | None = None) -> Any:
        self.check_thread()
        row = self.db.execute("SELECT kind FROM records WHERE id=?", (identifier,)).fetchone()
        if row is None or kind is not None and row["kind"] != kind:
            raise AuditError("synthetic_missing_record")
        return deepcopy(self.payloads[identifier])


class Transport:
    max_retries = 0

    def __init__(self, ledger: Ledger, *, barrier: int = 0, mode: str = "success") -> None:
        self.ledger, self.mode = ledger, mode
        self.calls: list[Any] = []
        self.lock = threading.Lock()
        self.barrier = threading.Barrier(barrier) if barrier else None
        self.active = self.peak = 0

    def perform(self, request: Any, body: bytes, client_request_id: str) -> BatchReceipt:
        assert client_request_id in self.ledger.intended_ids  # Read-only synthetic proof of prior intent.
        with self.lock:
            self.calls.append((request, body, client_request_id, threading.get_ident()))
            number = len(self.calls)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.barrier and number <= self.barrier.parties:
                self.barrier.wait(timeout=5)
            if self.mode.startswith("first") and number != 1:
                time.sleep(0.03)  # Make the failed receipt observable before the two successful receipts.
            if self.mode == "timeout":
                raise TimeoutError("private provider text must not be retained")
            if self.mode == "429" or self.mode == "first429" and number == 1:
                return BatchReceipt(b'{"error":{"code":"rate_limit"}}', 429, "synthetic", error_type="http_error")
            if self.mode == "first_secret" and number == 1:
                return BatchReceipt(b'{"password":"forbidden"}', 200, "synthetic")
            if self.mode == "malformed":
                return BatchReceipt(b'{"input_tokens":false}', 200, "synthetic")
            return BatchReceipt(b'{"input_tokens":123}', 200, "provider_" + client_request_id)
        finally:
            with self.lock:
                self.active -= 1


def setup() -> tuple[Any, dict[str, Any]]:
    ledger = Ledger()
    engine = SimpleNamespace(ledger=ledger, _active={"session"}, config=SimpleNamespace(offline=False))
    engine.gateway = EventBatchLiveGateway(engine, None)
    plan_id = ledger.record("session", "fictional_plan", "plan", {"authorization_id": "authorization"})
    policy_id = ledger.record("session", "policy", "policy", {"content": {"authorization_id": "authorization",
        "plan_ids": [plan_id], "allow_external_processing": True, "allow_paid_inference": True,
        "approved_by": "test:synthetic", "instruction": "Synthetic fixture only"}})
    return engine, {"plan_id": plan_id, "policy_id": policy_id, "authorization_id": "authorization"}


def task(engine: Any, index: int, *, same_text: bool = False, cap: int = 512) -> dict[str, str]:
    body = {"model": "gpt-6-luna", "instructions": "Fictional instruction",
            "input": "Fictional text" if same_text else f"Fictional text {index}",
            "text": {"format": {"type": "text"}}, "max_output_tokens": cap, "reasoning": {"effort": "low"}}
    return {"custom_id": "task_" + str(index), "corpus_id": "fictional", "body_ref": engine.ledger.artifacts.put(body)}


def existing(engine: Any, scope: Any, item: Any, transport: Any) -> dict[str, Any]:
    raw = canonical(count_request_body(engine.ledger.artifacts.read(item["body_ref"]))).encode()
    return engine.gateway.execute_action("session", **scope, action_key="historical-per-custom-action",
        request=COUNT_REQUEST, body=raw, transport=transport)


def count_kind(engine: Any, kind: str) -> int:
    return engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (kind,)).fetchone()[0]


def test_parallel_http_all_writes_main_thread_and_intents_precede_each_call() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger, barrier=4)
    tasks = [task(engine, index) for index in range(9)]
    result = count_many(engine, "session", **scope, tasks=tasks, transport=transport, max_workers=4)
    assert len(result) == 9 and len(transport.calls) == 9 and transport.peak == 4
    assert all(call[3] != engine.ledger.owner for call in transport.calls)
    assert count_kind(engine, ACTION_KIND) == 9 and count_kind(engine, RECEIPT_KIND) == 9
    assert count_kind(engine, LINK_KIND) == 9 and all(row["input_tokens"] == 123 for row in result.values())
    assert count_kind(engine, SUMMARY_KIND) == 1


def test_identical_count_inputs_group_once_even_when_output_caps_differ() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    first, second = task(engine, 1, same_text=True), task(engine, 2, same_text=True, cap=1024)
    result = count_many(engine, "session", **scope, tasks=[first, second], transport=transport)
    assert len(transport.calls) == 1 and len(result) == 2
    assert result["task_1"]["id"] == result["task_2"]["id"]
    assert not result["task_1"]["reused"] and result["task_2"]["reused"]
    assert result["task_1"]["reuse_record_id"] != result["task_2"]["reuse_record_id"]


@pytest.mark.parametrize("legacy", [False, True])
def test_existing_success_reuses_original_key_and_explicit_consumer_link(legacy: bool) -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    first = task(engine, 1, same_text=True)
    prior = existing(engine, scope, first, transport)
    if legacy:
        engine.ledger.db.execute("DELETE FROM records WHERE kind=?", (ACTION_IDENTITY_KIND,))
    result = count_many(engine, "session", **scope, tasks=[task(engine, 2, same_text=True)], transport=transport)
    assert len(transport.calls) == 1 and count_kind(engine, ACTION_KIND) == 1
    assert result["task_2"]["id"] == prior["id"] and result["task_2"]["reused"]
    linked = engine.ledger.get(result["task_2"]["reuse_record_id"])
    assert linked["origin_action_key"] == "historical-per-custom-action" and linked["custom_id"] == "task_2"


@pytest.mark.parametrize("mode", ["timeout", "429", "malformed"])
def test_failed_or_unknown_prior_receipt_blocks_before_any_new_count(mode: str) -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger, mode=mode)
    first = task(engine, 1)
    existing(engine, scope, first, transport)
    with pytest.raises(ResearchError, match="count_cache_"):
        count_many(engine, "session", **scope, tasks=[task(engine, 2), first], transport=transport)
    assert len(transport.calls) == 1


def test_cross_policy_reuse_is_rejected_without_dispatch() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    first = task(engine, 1)
    existing(engine, scope, first, transport)
    replacement = engine.ledger.get(scope["policy_id"])
    replacement["content"]["instruction"] = "Different synthetic policy"
    policy_id = engine.ledger.record("session", "policy", "replacement", replacement)
    with pytest.raises(AuditError, match="scope_or_action"):
        count_many(engine, "session", **{**scope, "policy_id": policy_id}, tasks=[first], transport=transport)
    assert len(transport.calls) == 1


def test_equal_returned_counts_for_different_inputs_do_not_create_false_cache_hit() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    result = count_many(engine, "session", **scope, tasks=[task(engine, 1), task(engine, 2)], transport=transport)
    assert len(transport.calls) == 2 and result["task_1"]["id"] != result["task_2"]["id"]


def test_first_error_stops_new_launches_but_drains_all_inflight_receipts() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger, barrier=3, mode="first429")
    with pytest.raises(CountManyError) as failure:
        count_many(engine, "session", **scope, tasks=[task(engine, index) for index in range(10)],
                   transport=transport, max_workers=3)
    assert len(transport.calls) == 3 and count_kind(engine, RECEIPT_KIND) == 3
    assert len(failure.value.receipts) == 2
    summary = engine.ledger.get(failure.value.summary_record_id)
    assert summary["transport_launched"] == summary["transport_finished"] == 3
    assert summary["unlinked_tasks"] == 8 and summary["failure"]


def test_retention_failure_stops_and_other_inflight_receipts_still_accounted() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger, barrier=3, mode="first_secret")
    with pytest.raises(CountManyError) as failure:
        count_many(engine, "session", **scope, tasks=[task(engine, index) for index in range(10)],
                   transport=transport, max_workers=3)
    assert len(transport.calls) == 3 and count_kind(engine, STOP_KIND) == 1
    assert count_kind(engine, RECEIPT_KIND) == 2 and len(failure.value.receipts) == 2
    assert engine.ledger.get(failure.value.summary_record_id)["transport_finished"] == 3


def test_intent_write_failure_causes_no_dispatch_and_no_identity_reset() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    item = task(engine, 1)
    engine.ledger.fail_kind = ACTION_KIND
    with pytest.raises(CountManyError):
        count_many(engine, "session", **scope, tasks=[item], transport=transport)
    assert not transport.calls and count_kind(engine, ACTION_IDENTITY_KIND) == 1
    engine.ledger.fail_kind = None
    with pytest.raises(AuditError, match="intent_incomplete_no_retry"):
        count_many(engine, "session", **scope, tasks=[item], transport=transport)
    assert not transport.calls


@pytest.mark.parametrize("workers", [0, 17, True])
def test_worker_bound_is_enforced(workers: Any) -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    with pytest.raises(ResearchError, match="workers_invalid"):
        count_many(engine, "session", **scope, tasks=[task(engine, 1)], transport=transport, max_workers=workers)
    assert not transport.calls


def test_retry_transport_or_duplicate_custom_ids_fail_before_dispatch() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    item = task(engine, 1)
    with pytest.raises(ResearchError, match="identity_invalid"):
        count_many(engine, "session", **scope, tasks=[item, item], transport=transport)
    transport.max_retries = 1
    with pytest.raises(ResearchError, match="one_shot"):
        count_many(engine, "session", **scope, tasks=[item], transport=transport)
    assert not transport.calls


def test_complete_resume_does_not_issue_any_new_http() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    tasks = [task(engine, 1), task(engine, 2)]
    first = count_many(engine, "session", **scope, tasks=tasks, transport=transport)
    resumed = count_many(engine, "session", **scope, tasks=tasks, transport=transport)
    assert len(transport.calls) == 2 and all(item["reused"] for item in resumed.values())
    assert {key: row["id"] for key, row in first.items()} == {key: row["id"] for key, row in resumed.items()}


def test_identical_numerical_count_reuse_preserves_each_separate_corpus_binding() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    first, second = task(engine, 1, same_text=True), task(engine, 2, same_text=True)
    first["corpus_id"], second["corpus_id"] = "incident-reports", "cybercrime"
    result = count_many(engine, "session", **scope, tasks=[first, second], transport=transport)
    assert len(transport.calls) == 1 and result["task_1"]["id"] == result["task_2"]["id"]
    for item in (first, second):
        linked = engine.ledger.get(result[item["custom_id"]]["reuse_record_id"])
        assert linked["corpus_id"] == item["corpus_id"] and linked["request_body_ref"] == item["body_ref"]
        assert linked["reuse_kind"] == "exact_input_token_count_only" and linked["model_output_reused"] is False


def test_missing_corpus_binding_is_rejected_before_count_dispatch() -> None:
    engine, scope = setup()
    transport = Transport(engine.ledger)
    item = task(engine, 1)
    item.pop("corpus_id")
    with pytest.raises(ResearchError, match="identity_invalid"):
        count_many(engine, "session", **scope, tasks=[item], transport=transport)
    assert not transport.calls
