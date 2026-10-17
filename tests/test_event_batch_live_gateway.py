"""Synthetic live-gateway boundary checks; no network, sources or research owner."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, ResearchError, canonical, digest
from newsresearch.event_batch_budget import BudgetBook, InputTokenReceipt, PricePolicy
from newsresearch.event_batch_live_gateway import (
    ACTION_KIND, BUDGET_KIND, RECEIPT_KIND, STOP_KIND, EventBatchLiveGateway,
)
from newsresearch.event_batch_transport import BatchReceipt


class Artifacts:
    def __init__(self, ledger):
        self.ledger, self.objects = ledger, {}

    def put_bytes(self, raw):
        if self.ledger.fail_artifacts:
            raise AuditError("synthetic_storage_failure")
        reference = hashlib.sha256(raw).hexdigest()
        self.objects[reference] = raw
        self.ledger.trace.append(("artifact", reference))
        return reference

    def put(self, value):
        return self.put_bytes(canonical(value).encode())

    def read_bytes(self, reference):
        return self.objects[reference]

    def read(self, reference):
        return json.loads(self.read_bytes(reference))


class Ledger:
    def __init__(self):
        self.trace, self.payloads, self.unresolved = [], {}, {}
        self.fail_artifacts = False
        self.fail_record_kind = None
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE records(id TEXT,kind TEXT,logical_key TEXT,created_event INTEGER)")
        self.artifacts = Artifacts(self)

    def append(self, session, kind, payload):
        self.trace.append((kind, deepcopy(payload)))

    def record(self, session, kind, key, payload, supersedes=None):
        if kind == self.fail_record_kind:
            raise AuditError("synthetic_record_failure")
        identifier = digest([kind, key, payload, supersedes])
        self.payloads[identifier] = deepcopy(payload)
        self.db.execute("INSERT INTO records VALUES(?,?,?,?)", (identifier, kind, key, len(self.trace)))
        self.trace.append((kind, identifier))
        return identifier

    def get(self, identifier, kind=None):
        row = self.db.execute("SELECT kind FROM records WHERE id=?", (identifier,)).fetchone()
        if row is None or kind is not None and row["kind"] != kind:
            raise AuditError("synthetic_missing_record")
        return deepcopy(self.payloads[identifier])


class Transport:
    max_retries = 0
    synthetic = True

    def __init__(self, ledger, receipt=None, error=None):
        self.ledger, self.calls, self.error = ledger, [], error
        self.receipt = receipt or BatchReceipt(b'{"input_tokens":123}', 200, "provider-1")

    def perform(self, request, body, client_request_id):
        self.ledger.trace.append(("http", client_request_id))
        self.calls.append((deepcopy(request), body, client_request_id))
        if self.error:
            raise self.error
        return self.receipt


def pricing():
    return PricePolicy("gpt-6-luna", 100_000_000, 125_000_000, 500_000_000,
                       (1, 2), (11, 10), (2, 1), (3, 2), 272_000,
                       "https://example.invalid/synthetic-rates", "2026-10-17T00:00:00Z")


def setup():
    ledger = Ledger()
    engine = SimpleNamespace(ledger=ledger, _active={"session"}, config=SimpleNamespace(offline=False))
    gateway = EventBatchLiveGateway(engine, None)
    plan = ledger.record("session", "fictional_plan", "plan", {"authorization_id": "authorization"})
    policy = ledger.record("session", "policy", "policy", {"content": {
        "authorization_id": "authorization", "plan_ids": [plan], "allow_external_processing": True,
        "allow_paid_inference": True, "approved_by": "test:synthetic", "instruction": "Synthetic test only",
        "ceiling_nanousd": 150_000_000_000, "operational_limit_nanousd": 120_000_000_000,
        "price_fingerprint": pricing().fingerprint,
    }})
    transport = Transport(ledger)
    args = dict(plan_id=plan, policy_id=policy, authorization_id="authorization", action_key="count-1",
                request={"method": "POST", "path": "/v1/responses/input_tokens"},
                body=canonical({"model": "gpt-6-luna", "instructions": "Fictional only", "input": "Fictional text",
                                "text": {"format": {"type": "text"}}}).encode(), transport=transport)
    return gateway, engine, args


def book_for(gateway):
    book = BudgetBook(pricing(), "authorization", operational_limit_nanousd=120_000_000_000)
    identifier = gateway.save_book("session", book)
    return book, identifier


def paid(gateway, engine, args, *, actual_cap=512, reserved_cap=512, reserved_count=123,
         receipt_hash=None):
    book, state_id = book_for(gateway)
    count_result = gateway.execute_action("session", **args)
    raw = canonical(json.loads(args["body"]) | {"max_output_tokens": actual_cap}).encode()
    request_ref = engine.ledger.artifacts.put_bytes(raw)
    request_id = "paid-request-1"
    book.reserve(request_id=request_id, task_id="task-1", corpus_id="fictional", plan_id=args["plan_id"],
                 request_sha256=request_ref, max_output_tokens=reserved_cap, price_fingerprint=pricing().fingerprint,
                 input_count=InputTokenReceipt(reserved_count, "gpt-6-luna", request_ref,
                                               receipt_hash or count_result["body_sha256"],
                                               "provider_responses_input_tokens"))
    gateway.save_book("session", book, state_id)
    dispatch = engine.ledger.artifacts.put({"synthetic": True})
    intent = {"attempt": "attempt-1", "budget_authorization_id": "authorization",
              "budget_request_id": request_id, "task_key": "task-1", "request_sha256": request_ref,
              "request": request_ref, "dispatch": dispatch}
    engine.ledger.append("session", "model.attempt.intended", intent)
    engine.ledger.unresolved["attempt-1"] = intent
    jsonl = (canonical({"custom_id": request_id, "method": "POST", "url": "/v1/responses",
                        "body": json.loads(raw)}) + "\n").encode()
    args["transport"].receipt = BatchReceipt(canonical({"id": "file-fictional", "purpose": "batch",
                                                        "bytes": len(jsonl)}).encode(), 200)
    gateway.execute_action("session", **(args | {
        "action_key": "upload-1", "body": jsonl,
        "request": {"method": "POST", "path": "/v1/files", "purpose": "batch",
                    "filename": "fictional.jsonl", "content_sha256": hashlib.sha256(jsonl).hexdigest()},
    }))
    args["transport"].receipt = BatchReceipt(b'{"id":"batch_fictional"}', 200)
    args = args | {"action_key": "create-1", "request": {"method": "POST", "path": "/v1/batches"},
                   "body": canonical({"input_file_id": "file-fictional", "endpoint": "/v1/responses",
                                      "completion_window": "24h"}).encode(),
                   "reserved_request_ids": [request_id], "attempt_ids": ["attempt-1"]}
    return args, book


def test_exact_count_intent_and_wire_bytes_precede_http_and_raw_precedes_return():
    gateway, engine, args = setup()
    result = gateway.execute_action("session", **args)
    trace = [kind for kind, value in engine.ledger.trace]
    assert trace.index(ACTION_KIND) < trace.index("http") < trace.index(RECEIPT_KIND)
    action = engine.ledger.get(next(value for kind, value in engine.ledger.trace if kind == ACTION_KIND))
    exact = engine.ledger.artifacts.read(action["exact_request_ref"])
    assert engine.ledger.artifacts.read_bytes(exact["wire_body_ref"]) == args["body"]
    assert "Authorization" not in exact["headers_excluding_authentication"]
    assert exact["headers_excluding_authentication"]["X-Client-Request-Id"] == action["action_id"]
    assert engine.ledger.artifacts.read_bytes(result["body_ref"]) == b'{"input_tokens":123}'
    assert result["unknown"] is False and result["reused"] is False


def test_exact_replay_reuses_receipt_without_http_and_changed_identity_blocks():
    gateway, engine, args = setup()
    first = gateway.execute_action("session", **args)
    second = gateway.execute_action("session", **args)
    assert first["id"] == second["id"] and second["reused"] is True
    assert len(args["transport"].calls) == 1
    changed = json.loads(args["body"])
    changed["input"] = "Changed fictional text"
    with pytest.raises(AuditError, match="identity_changed"):
        gateway.execute_action("session", **(args | {"body": canonical(changed).encode()}))


def test_changed_key_cannot_retry_same_count_or_mutation():
    gateway, engine, args = setup()
    gateway.execute_action("session", **args)
    with pytest.raises(AuditError, match="changed_key_retry"):
        gateway.execute_action("session", **(args | {"action_key": "changed-key"}))
    assert len(args["transport"].calls) == 1


@pytest.mark.parametrize("receipt", [BatchReceipt(None, None, unknown=True),
    BatchReceipt(b'{}', 500, unknown=True), BatchReceipt(None, 200, unknown=False)])
def test_unknown_receipt_remains_unknown_and_exact_reissue_forbidden(receipt):
    gateway, engine, args = setup()
    args["transport"] = Transport(engine.ledger, receipt)
    result = gateway.execute_action("session", **args)
    assert result["unknown"] is True
    with pytest.raises(AuditError, match="unknown_action_no_retry"):
        gateway.execute_action("session", **args)
    assert len(args["transport"].calls) == 1


def test_transport_exception_retains_safe_type_and_unknown_intent():
    gateway, engine, args = setup()
    args["transport"] = Transport(engine.ledger, error=RuntimeError("secret exception details"))
    result = gateway.execute_action("session", **args)
    assert result["error_type"] == "RuntimeError" and result["unknown"]
    assert "secret exception" not in canonical(engine.ledger.payloads)


@pytest.mark.parametrize("receipt", [
    BatchReceipt(None, 200, retention_error="credential_guard"),
    BatchReceipt(b'{"api_key":"fictional-sensitive-value"}', 200),
    BatchReceipt(b'{"okay":1}', 200, headers={"Authorization": "not-retainable"}),
    BatchReceipt(b'{}', 200, body_sha256="f" * 64),
    BatchReceipt(b'{}', True),
])
def test_retention_failure_latches_authorization_stop_and_no_further_network(receipt):
    gateway, engine, args = setup()
    args["transport"] = Transport(engine.ledger, receipt)
    with pytest.raises(AuditError, match="response_retention_failed"):
        gateway.execute_action("session", **args)
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (STOP_KIND,)).fetchone()[0] == 1
    with pytest.raises(AuditError, match="authorization_stopped"):
        gateway.execute_action("session", **(args | {"action_key": "anything-new"}))
    assert len(args["transport"].calls) == 1


def test_malformed_json_retained_before_any_caller_parse():
    gateway, engine, args = setup()
    args["transport"] = Transport(engine.ledger, BatchReceipt(b'not JSON', 200))
    result = gateway.execute_action("session", **args)
    assert engine.ledger.artifacts.read_bytes(result["body_ref"]) == b'not JSON'


def test_non_success_http_is_retained_replayable_and_not_retried():
    gateway, engine, args = setup()
    args["transport"] = Transport(engine.ledger, BatchReceipt(b'{"error":"fictional"}', 400, error_type="http_error"))
    result = gateway.execute_action("session", **args)
    assert result["status"] == 400 and result["unknown"] is False
    assert gateway.execute_action("session", **args)["reused"]
    assert len(args["transport"].calls) == 1


@pytest.mark.parametrize("failure", ["inactive", "offline", "wrong-plan", "no-permission", "retry-transport", "storage"])
def test_preflight_scope_storage_or_retry_configuration_failure_prevents_http(failure):
    gateway, engine, args = setup()
    if failure == "inactive":
        engine._active.clear()
    elif failure == "offline":
        engine.config.offline = True
    elif failure == "wrong-plan":
        args["plan_id"] = engine.ledger.record("session", "fictional_plan", "other", {"authorization_id": "authorization"})
    elif failure == "no-permission":
        engine.ledger.payloads[args["policy_id"]]["content"]["allow_paid_inference"] = False
    elif failure == "retry-transport":
        args["transport"].max_retries = 1
    elif failure == "storage":
        engine.ledger.fail_record_kind = ACTION_KIND
    with pytest.raises(ResearchError):
        gateway.execute_action("session", **args)
    assert args["transport"].calls == []


def test_distinct_poll_observation_keys_allowed_and_exact_observation_replayed():
    gateway, engine, args = setup()
    args |= {"body": None, "request": {"method": "GET", "path": "/v1/batches/batch_fictional"}}
    gateway.execute_action("session", **args)
    gateway.execute_action("session", **(args | {"action_key": "later-observation"}))
    gateway.execute_action("session", **args)
    assert len(args["transport"].calls) == 2


def test_initial_budget_empty_then_strict_extension_and_exact_state_reuse():
    gateway, engine, args = setup()
    book, first = book_for(gateway)
    assert gateway.load_book("session", "authorization")[1] == first
    assert gateway.save_book("session", book, first) == first
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (BUDGET_KIND,)).fetchone()[0] == 1
    book.reserve(request_id="r", task_id="t", corpus_id="c", plan_id=args["plan_id"], request_sha256="a" * 64,
                 input_count=InputTokenReceipt(100, "gpt-6-luna", "a" * 64, "b" * 64, "provider_responses_input_tokens"),
                 max_output_tokens=100, price_fingerprint=pricing().fingerprint)
    second = gateway.save_book("session", book, first)
    assert second != first and gateway.load_book("session", "authorization")[0].to_dict() == book.to_dict()
    with pytest.raises(AuditError, match="stale_state"):
        gateway.save_book("session", book, first)
    reset = BudgetBook(pricing(), "authorization", operational_limit_nanousd=120_000_000_000)
    with pytest.raises(AuditError, match="history_changed"):
        gateway.save_book("session", reset, second)


def test_unknown_existing_budget_cannot_be_replaced_with_fresh_reservations():
    gateway, engine, args = setup()
    paid_args, book = paid(gateway, engine, args)
    _, state_id = gateway.load_book("session", "authorization")
    book.settle("paid-request-1", None)
    latest = gateway.save_book("session", book, state_id)
    assert gateway.load_book("session", "authorization")[0].reserved_nanousd > 0
    with pytest.raises(AuditError):
        gateway.save_book("session", BudgetBook(pricing(), "authorization"), latest)


def test_paid_create_requires_persisted_budget_and_exact_unresolved_attempt():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    result = gateway.execute_action("session", **args)
    assert result["phase"] == "create"
    trace = [kind for kind, value in engine.ledger.trace]
    assert trace.index(BUDGET_KIND) < trace.index("model.attempt.intended") < max(i for i, kind in enumerate(trace) if kind == "http")
    assert gateway.execute_action("session", **args)["reused"]
    assert len(args["transport"].calls) == 3


@pytest.mark.parametrize("failure", ["unresolved", "request-hash", "budget-id", "task", "request-bytes", "policy"])
def test_paid_create_rejects_unbound_or_changed_budget_and_intents(failure):
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    if failure == "unresolved":
        engine.ledger.unresolved.clear()
    elif failure == "request-hash":
        engine.ledger.unresolved["attempt-1"]["request_sha256"] = "f" * 64
    elif failure == "budget-id":
        engine.ledger.unresolved["attempt-1"]["budget_request_id"] = "unknown"
    elif failure == "task":
        engine.ledger.unresolved["attempt-1"]["task_key"] = "wrong-task"
    elif failure == "request-bytes":
        engine.ledger.unresolved["attempt-1"]["request"] = engine.ledger.artifacts.put({"changed": True})
    elif failure == "policy":
        engine.ledger.payloads[args["policy_id"]]["content"]["operational_limit_nanousd"] += 1
    with pytest.raises(ResearchError):
        gateway.execute_action("session", **args)
    assert len(args["transport"].calls) == 2


def test_create_cannot_reuse_same_paid_requests_under_different_file_or_action_key():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    gateway.execute_action("session", **args)
    body = json.loads(args["body"])
    body["input_file_id"] = "file-different"
    with pytest.raises(AuditError):
        gateway.execute_action("session", **(args | {"body": canonical(body).encode(), "action_key": "create-other"}))
    assert len(args["transport"].calls) == 3


@pytest.mark.parametrize("changes,reason", [
    ({"actual_cap": 4096, "reserved_cap": 256}, "cap_or_model_mismatch"),
    ({"reserved_count": 122}, "provider_count_provenance_missing"),
    ({"receipt_hash": "f" * 64}, "provider_count_provenance_missing"),
])
def test_actual_paid_cap_and_exact_provider_count_bound_at_create(changes, reason):
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args, **changes)
    with pytest.raises(AuditError, match=reason):
        gateway.execute_action("session", **args)
    assert len(args["transport"].calls) == 2


def change_upload(engine, change):
    row = engine.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1",
                                  (ACTION_KIND,)).fetchone()
    action = engine.ledger.get(row["id"])
    assert action["phase"] == "upload"
    exact = engine.ledger.artifacts.read(action["exact_request_ref"])
    rows = [json.loads(line) for line in engine.ledger.artifacts.read_bytes(exact["original_body_ref"]).splitlines()]
    change(rows)
    new_raw = ("\n".join(canonical(item) for item in rows) + "\n").encode()
    exact["original_body_ref"] = engine.ledger.artifacts.put_bytes(new_raw)
    exact["logical_request"]["content_sha256"] = hashlib.sha256(new_raw).hexdigest()
    engine.ledger.payloads[row["id"]]["exact_request_ref"] = engine.ledger.artifacts.put(exact)
    receipt_row = engine.ledger.db.execute("SELECT id FROM records WHERE kind=? AND logical_key=?",
                                          (RECEIPT_KIND, action["action_id"])).fetchone()
    receipt = engine.ledger.payloads[receipt_row["id"]]
    new_receipt = canonical({"id": "file-fictional", "purpose": "batch", "bytes": len(new_raw)}).encode()
    receipt["body_ref"] = engine.ledger.artifacts.put_bytes(new_receipt)
    receipt["body_sha256"] = hashlib.sha256(new_receipt).hexdigest()


def test_upload_cannot_contain_unreserved_extra_request():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    change_upload(engine, lambda rows: rows.append(rows[0] | {"custom_id": "unreserved"}))
    with pytest.raises(AuditError, match="request_set_mismatch"):
        gateway.execute_action("session", **args)
    assert len(args["transport"].calls) == 2


def test_upload_cannot_substitute_different_paid_text_under_same_custom_id():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    def change(rows):
        rows[0]["body"]["input"] = "Different fictional text"
    change_upload(engine, change)
    with pytest.raises(AuditError, match="cap_or_model_mismatch"):
        gateway.execute_action("session", **args)


def test_count_receipt_for_different_evidence_does_not_support_paid_input_bound():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    row = engine.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event LIMIT 1",
                                  (ACTION_KIND,)).fetchone()
    action = engine.ledger.get(row["id"])
    exact = engine.ledger.artifacts.read(action["exact_request_ref"])
    body = engine.ledger.artifacts.read(exact["original_body_ref"])
    body["input"] = "Different fictional article with coincidentally identical token count"
    exact["original_body_ref"] = engine.ledger.artifacts.put(body)
    engine.ledger.payloads[row["id"]]["exact_request_ref"] = engine.ledger.artifacts.put(exact)
    with pytest.raises(AuditError, match="provider_count_provenance_missing"):
        gateway.execute_action("session", **args)


def test_uploaded_provider_id_must_be_exact_retained_id():
    gateway, engine, args = setup()
    args, book = paid(gateway, engine, args)
    body = json.loads(args["body"])
    body["input_file_id"] = "file-unrelated"
    with pytest.raises(AuditError, match="exact_retained_upload"):
        gateway.execute_action("session", **(args | {"body": canonical(body).encode()}))
    assert len(args["transport"].calls) == 2
