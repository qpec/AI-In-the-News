"""Audited exact count reuse and bounded parallel count HTTP, one ledger writer.

This helper performs no extraction inference and cannot upload/create a Batch.
The caller must enter Research.execute with a registered method and retain its
unchanged plan/paid policy. Every count sends evidence and has an exact durable
intent. Worker threads call only the injected one-shot HTTP transport; all
ledger/artifact access and cache linking remain on the caller's thread.
"""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from newsresearch.common import AuditError, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from newsresearch.event_batch_live_gateway import (
    ACTION_IDENTITY_KIND, ACTION_KIND, METHOD as GATEWAY_METHOD, RECEIPT_KIND,
    EventBatchLiveGateway, _rows,
)
from newsresearch.event_batch_transport import BatchReceipt, count_request_body, prepare_request

METHOD = "luna-batch-exact-count-cache-parallel-v1"
LINK_KIND = "luna_batch_count_consumer"
SUMMARY_KIND = "luna_batch_count_many"
COUNT_REQUEST = {"method": "POST", "path": "/v1/responses/input_tokens"}


class CountManyError(ResearchError):
    """All launched work has drained; available receipts remain individually retained."""

    def __init__(self, reason: str, receipts: dict[str, Json], summary_record_id: str | None) -> None:
        super().__init__(reason)
        self.receipts = receipts
        self.summary_record_id = summary_record_id


@dataclass
class _Group:
    body: bytes
    logical_hash: str
    consumers: list[Json]
    action: Json | None = None


def _validate_receipt(engine: Any, receipt: Json) -> int:
    if (receipt.get("unknown") is not False or type(receipt.get("status")) is not int or receipt.get("status") != 200
            or not receipt.get("body_ref") or receipt.get("error_type") is not None):
        raise ResearchError("count_cache_receipt_not_successful_no_retry")
    raw = engine.ledger.artifacts.read_bytes(receipt["body_ref"])
    if hashlib.sha256(raw).hexdigest() != receipt.get("body_sha256"):
        raise AuditError("count_cache_receipt_hash_mismatch")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ResearchError("count_cache_malformed_provider_receipt_no_retry") from None
    if not isinstance(value, dict) or type(value.get("input_tokens")) is not int or value["input_tokens"] < 1:
        raise ResearchError("count_cache_provider_input_tokens_invalid_no_retry")
    if value.get("model") not in {None, "gpt-6-luna"}:
        raise ResearchError("count_cache_provider_model_mismatch_no_retry")
    require_no_credentials(value)
    return value["input_tokens"]


def _old_action(engine: Any, group: _Group, *, plan_id: str, policy_id: str,
                authorization_id: str, legacy: dict[str, list[Json]]) -> Json | None:
    identity = _rows(engine, ACTION_IDENTITY_KIND, digest([authorization_id, group.logical_hash]))
    if len(identity) > 1:
        raise AuditError("count_cache_ambiguous_identity")
    actions = _rows(engine, ACTION_KIND, identity[0]["action_id"]) if identity else legacy.get(group.logical_hash, [])
    if identity and not actions:
        raise AuditError("count_cache_intent_incomplete_no_retry")
    if not actions:
        return None
    if len(actions) != 1:
        raise AuditError("count_cache_ambiguous_action")
    action = actions[0]
    if (action.get("method") != GATEWAY_METHOD or action.get("phase") != "count"
            or action.get("plan_id") != plan_id or action.get("policy_id") != policy_id
            or action.get("authorization_id") != authorization_id or action.get("logical_hash") != group.logical_hash
            or action.get("reserved_request_ids") != [] or action.get("attempt_ids") != []):
        raise AuditError("count_cache_scope_or_action_mismatch")
    exact = engine.ledger.artifacts.read(action["exact_request_ref"])
    prepared = prepare_request(COUNT_REQUEST, group.body, action["action_id"])
    if (exact.get("logical_request") != COUNT_REQUEST or exact.get("method") != prepared.method
            or exact.get("url") != prepared.url or exact.get("headers_excluding_authentication") != prepared.headers
            or engine.ledger.artifacts.read_bytes(exact["original_body_ref"]) != group.body
            or engine.ledger.artifacts.read_bytes(exact["wire_body_ref"]) != prepared.body):
        raise AuditError("count_cache_exact_request_mismatch")
    receipts = _rows(engine, RECEIPT_KIND, action["action_id"])
    if len(receipts) != 1:
        raise AuditError("count_cache_missing_or_ambiguous_receipt_no_retry")
    receipt = receipts[0]
    if (receipt.get("authorization_id") != authorization_id or receipt.get("plan_id") != plan_id
            or receipt.get("phase") != "count" or receipt.get("action_id") != action["action_id"]):
        raise AuditError("count_cache_receipt_provenance_mismatch")
    _validate_receipt(engine, receipt)
    return action


def _prepare(gateway: EventBatchLiveGateway, session: str, group: _Group, *, plan_id: str,
             policy_id: str, authorization_id: str) -> Json:
    engine = gateway.engine
    action_key = "count-exact-v1:" + hashlib.sha256(group.body).hexdigest()
    action_id = digest({"authorization_id": authorization_id, "action_key": action_key})
    if _rows(engine, ACTION_KIND, action_id) or _rows(engine, ACTION_IDENTITY_KIND, digest([authorization_id, group.logical_hash])):
        raise AuditError("count_cache_new_action_already_reserved")
    prepared = prepare_request(COUNT_REQUEST, group.body, action_id)
    body_ref = gateway._save(session, group.body)
    exact_ref = gateway._save(session, {"method": prepared.method, "url": prepared.url,
        "headers_excluding_authentication": prepared.headers, "wire_body_ref": body_ref,
        "original_body_ref": body_ref, "logical_request": COUNT_REQUEST})
    gateway.engine.ledger.record(session, ACTION_IDENTITY_KIND, digest([authorization_id, group.logical_hash]), {
        "method": GATEWAY_METHOD, "authorization_id": authorization_id, "action_id": action_id,
        "logical_hash": group.logical_hash, "exact_request_ref": exact_ref, "reserved_at": utc()})
    action = {"method": GATEWAY_METHOD, "authorization_id": authorization_id, "plan_id": plan_id,
        "policy_id": policy_id, "action_key": action_key, "action_id": action_id, "phase": "count",
        "logical_hash": group.logical_hash, "reserved_request_ids": [], "attempt_ids": [],
        "exact_request_ref": exact_ref, "budget_state_id": None, "started_at": utc()}
    engine.ledger.record(session, ACTION_KIND, action_id, action)
    return action


def _retain(gateway: EventBatchLiveGateway, session: str, action: Json, receipt: Any) -> Json:
    """Writer-only counterpart of the unchanged gateway's one-shot retention."""
    authorization_id, action_id = action["authorization_id"], action["action_id"]
    if not isinstance(receipt, BatchReceipt):
        gateway._stop(session, authorization_id, action_id, "invalid_transport_receipt")
        raise AuditError("count_many_invalid_transport_receipt")
    try:
        if (receipt.retention_error or receipt.body is not None and not isinstance(receipt.body, bytes)
                or type(receipt.unknown) is not bool
                or receipt.status is not None and (type(receipt.status) is not int or not 100 <= receipt.status <= 599)):
            raise ResearchError("count_many_transport_receipt_invalid")
        require_no_credentials({"headers": receipt.headers, "request_id": receipt.request_id,
                                "error_type": receipt.error_type, "body_sha256": receipt.body_sha256})
        raw_ref = gateway._save(session, receipt.body) if receipt.body is not None else None
        raw_hash = hashlib.sha256(receipt.body).hexdigest() if receipt.body is not None else None
        if receipt.body_sha256 is not None and receipt.body_sha256 != raw_hash:
            raise ResearchError("count_many_receipt_hash_mismatch")
    except ResearchError:
        gateway._stop(session, authorization_id, action_id, "response_retention_failed")
        raise AuditError("count_many_response_retention_failed") from None
    value = {"method": GATEWAY_METHOD, "authorization_id": authorization_id, "plan_id": action["plan_id"],
        "action_id": action_id, "phase": "count", "body_ref": raw_ref, "body_sha256": raw_hash,
        "status": receipt.status, "provider_request_id": receipt.request_id, "headers": receipt.headers,
        "error_type": receipt.error_type, "unknown": bool(receipt.unknown or receipt.body is None), "received_at": utc()}
    identifier = gateway.engine.ledger.record(session, RECEIPT_KIND, action_id, value)
    return {"id": identifier, **value, "reused": False}


def _link(gateway: EventBatchLiveGateway, session: str, group: _Group, action: Json,
          receipt: Json, *, reused: bool) -> dict[str, Json]:
    count = _validate_receipt(gateway.engine, receipt)
    exact = gateway.engine.ledger.artifacts.read(action["exact_request_ref"])
    result = {}
    for index, consumer in enumerate(group.consumers):
        is_reuse = reused or index > 0
        value = {"method": METHOD, "authorization_id": action["authorization_id"],
            "plan_id": action["plan_id"], "policy_id": action["policy_id"], "custom_id": consumer["custom_id"],
            "corpus_id": consumer["corpus_id"], "reuse_kind": "exact_input_token_count_only", "model_output_reused": False,
            "request_body_ref": consumer["body_ref"], "count_body_ref": exact["original_body_ref"],
            "origin_action_id": action["action_id"], "origin_action_key": action["action_key"],
            "origin_receipt_id": receipt["id"], "provider_count_body_sha256": receipt["body_sha256"],
            "input_tokens": count, "reused": is_reuse, "linked_at": utc()}
        key = digest([action["authorization_id"], action["plan_id"], action["policy_id"], consumer["corpus_id"], consumer["custom_id"]])
        identifier = gateway.engine.ledger.record(session, LINK_KIND, key, value)
        result[consumer["custom_id"]] = {**receipt, "input_tokens": count, "count_body_ref": exact["original_body_ref"],
                                         "reuse_record_id": identifier, "reused": is_reuse,
                                         "corpus_id": consumer["corpus_id"], "model_output_reused": False}
    return result


def count_many(engine: Any, session: str, *, plan_id: str, policy_id: str, authorization_id: str,
               tasks: list[Json], max_workers: int = 16, transport: Any = None) -> dict[str, Json]:
    """Return ``custom_id -> retained receipt``; unknown/failed identities never retry.

    Tasks need custom_id, frozen corpus_id and body_ref pointing to the exact Responses body.
    A CountManyError carries partial receipts and the retained summary identity.
    No more than max_workers requests are in flight; after the first observed
    failure, no new workers start and every launched result is drained/retained.
    """
    require_active(engine, session)
    gateway = engine.gateway
    if not isinstance(gateway, EventBatchLiveGateway):
        raise AuditError("count_many_shared_gateway_required")
    gateway._scope(session, plan_id, policy_id, authorization_id)
    if type(max_workers) is not int or not 1 <= max_workers <= 16:
        raise ResearchError("count_many_workers_invalid")
    if transport is None or getattr(transport, "max_retries", None) != 0:
        raise ResearchError("count_many_one_shot_transport_required")
    if not isinstance(tasks, list) or any(not isinstance(task, dict) for task in tasks):
        raise ResearchError("count_many_tasks_invalid")
    groups: dict[str, _Group] = {}
    customs: set[str] = set()
    for task in tasks:
        custom_id, body_ref, corpus_id = task.get("custom_id"), task.get("body_ref"), task.get("corpus_id")
        if (not isinstance(custom_id, str) or not custom_id or custom_id in customs or not isinstance(body_ref, str)
                or not isinstance(corpus_id, str) or not corpus_id.strip()):
            raise ResearchError("count_many_task_identity_invalid")
        customs.add(custom_id)
        raw = engine.ledger.artifacts.read_bytes(body_ref)
        if hashlib.sha256(raw).hexdigest() != body_ref:
            raise AuditError("count_many_request_body_hash_mismatch")
        try:
            paid_body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ResearchError("count_many_request_body_invalid") from None
        if not isinstance(paid_body, dict):
            raise ResearchError("count_many_request_body_invalid")
        body = canonical(count_request_body(paid_body)).encode()
        logical_hash = digest({"request": COUNT_REQUEST, "body_sha256": hashlib.sha256(body).hexdigest()})
        group = groups.setdefault(logical_hash, _Group(body, logical_hash, []))
        if group.body != body:
            raise AuditError("count_many_digest_collision")
        group.consumers.append({"custom_id": custom_id, "body_ref": body_ref, "corpus_id": corpus_id})
    # One bounded SQL lookup also protects older actions predating the indexed
    # identity record. Never scan all earlier actions once per new article.
    legacy: dict[str, list[Json]] = {}
    for offset in range(0, len(groups), 500):
        hashes = list(groups)[offset:offset + 500]
        placeholders = ",".join("?" for _ in hashes)
        sql = ("SELECT id FROM records WHERE kind=? AND json_extract(payload,'$.authorization_id')=? "
               f"AND json_extract(payload,'$.logical_hash') IN ({placeholders}) ORDER BY created_event")
        parameters = [ACTION_KIND, authorization_id, *hashes]
        engine.ledger.append(session, "batch.count_cache.action_inspection.intended", {
            "method": METHOD, "plan_id": plan_id, "policy_id": policy_id, "authorization_id": authorization_id,
            "scope": "prior_count_action_metadata_only", "sql": sql, "parameters": parameters,
            "article_passages_inspected": False})
        for row in engine.ledger.db.execute(sql, parameters):
            action = {"id": row["id"], **engine.ledger.get(row["id"], ACTION_KIND)}
            legacy.setdefault(action["logical_hash"], []).append(action)
    receipts: dict[str, Json] = {}
    pending_groups = []
    # Reconcile all existing identities before creating any new dispatch.
    for group in groups.values():
        group.action = _old_action(engine, group, plan_id=plan_id, policy_id=policy_id,
                                   authorization_id=authorization_id, legacy=legacy)
    for group in groups.values():
        if group.action is None:
            pending_groups.append(group)
            continue
        receipt = gateway.execute_action(session, plan_id=plan_id, policy_id=policy_id,
            authorization_id=authorization_id, action_key=group.action["action_key"],
            request=COUNT_REQUEST, body=group.body, transport=transport)
        receipts.update(_link(gateway, session, group, group.action, receipt, reused=True))

    def send(group: _Group) -> Any:
        assert group.action is not None
        try:
            return transport.perform(dict(COUNT_REQUEST), group.body, group.action["action_id"])
        except Exception as error:
            return BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)

    failure: str | None = None
    launched = finished = 0
    in_flight: dict[Future[Any], _Group] = {}
    iterator = iter(pending_groups)
    exhausted = False
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while in_flight or not exhausted and failure is None:
            while failure is None and not exhausted and len(in_flight) < max_workers:
                next_group = next(iterator, None)
                if next_group is None:
                    exhausted = True
                    break
                group = next_group
                try:
                    group.action = _prepare(gateway, session, group, plan_id=plan_id,
                                            policy_id=policy_id, authorization_id=authorization_id)
                    in_flight[pool.submit(send, group)] = group
                    launched += 1
                except Exception as error:
                    failure = str(error) if isinstance(error, ResearchError) else type(error).__name__
                    break
            if not in_flight:
                break
            done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                group = in_flight.pop(future)
                finished += 1
                try:
                    assert group.action is not None
                    receipt = _retain(gateway, session, group.action, future.result())
                    receipts.update(_link(gateway, session, group, group.action, receipt, reused=False))
                except Exception as error:
                    if failure is None:
                        failure = str(error) if isinstance(error, ResearchError) else type(error).__name__
    summary = {"method": METHOD, "authorization_id": authorization_id, "plan_id": plan_id,
        "policy_id": policy_id, "task_count": len(tasks), "unique_count_bodies": len(groups),
        "transport_launched": launched, "transport_finished": finished, "workers_max": max_workers,
        "linked_receipts": len(receipts), "unlinked_tasks": len(tasks) - len(receipts),
        "failure": failure, "automatic_retries": 0, "new_inference_calls": 0, "ended_at": utc()}
    summary_id = None
    try:
        summary_id = engine.ledger.record(session, SUMMARY_KIND, digest([authorization_id, plan_id, sorted(customs)]), summary)
    except Exception as error:
        if failure is None:
            failure = str(error) if isinstance(error, ResearchError) else type(error).__name__
    if failure:
        raise CountManyError(failure, receipts, summary_id)
    return receipts
