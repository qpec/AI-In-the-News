"""Durable one-writer bridge for explicitly authorized OpenAI Batch actions.

The study coordinator owns materialization, exact scientific versions, result
validation and scheduling. This shared Gateway extension owns HTTP provenance,
one-shot action identity and the authorization-wide monetary projection. Raw
receipts are retained before callers can parse them. No request is retried here.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .common import AuditError, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .event_batch_budget import BudgetBook
from .event_batch_transport import BatchReceipt, count_request_body, prepare_request
from .gateway import Gateway

METHOD = "event-batch-live-actions-v1"
BUDGET_KIND = "event_batch_live_budget"
ACTION_KIND = "event_batch_live_action"
ACTION_IDENTITY_KIND = "event_batch_live_action_identity"
RECEIPT_KIND = "event_batch_live_receipt"
STOP_KIND = "event_batch_live_stop"


def _rows(engine: Any, kind: str, key: str | None = None) -> list[Json]:
    sql, parameters = "SELECT id FROM records WHERE kind=?", [kind]
    if key is not None:
        sql += " AND logical_key=?"
        parameters.append(key)
    sql += " ORDER BY created_event"
    return [{"id": row["id"], **engine.ledger.get(row["id"], kind)}
            for row in engine.ledger.db.execute(sql, parameters)]


def _retention_check(raw: bytes) -> None:
    text = raw.decode("utf-8", errors="replace")
    require_no_credentials(text)
    try:
        parsed = json.loads(text)
    except ValueError:
        for line in text.splitlines():
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            require_no_credentials(parsed)
    else:
        require_no_credentials(parsed)


class EventBatchLiveGateway(Gateway):
    def _save(self, session: str, value: bytes | Json) -> str:
        if isinstance(value, bytes):
            _retention_check(value)
            reference = self.engine.ledger.artifacts.put_bytes(value)
        else:
            require_no_credentials(value)
            reference = self.engine.ledger.artifacts.put(value)
        self.engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference})
        return reference

    def load_book(self, session: str, authorization_id: str) -> tuple[BudgetBook, str] | None:
        require_active(self.engine, session)
        row = self.engine.ledger.db.execute(
            "SELECT id FROM records WHERE kind=? AND logical_key=? ORDER BY created_event DESC LIMIT 1",
            (BUDGET_KIND, authorization_id)).fetchone()
        if row is None:
            return None
        record = self.engine.ledger.get(row["id"], BUDGET_KIND)
        book = BudgetBook.from_dict(self.engine.ledger.artifacts.read(record["state_ref"]))
        if book.authorization_id != authorization_id or record.get("method") != METHOD:
            raise AuditError("batch_budget_authorization_mismatch")
        return book, row["id"]

    def save_book(self, session: str, book: BudgetBook, previous_state_id: str | None = None) -> str:
        """Persist a strict extension of the latest state; no independent reset."""
        require_active(self.engine, session)
        state = book.to_dict()
        # Validate even caller-created or mutated in-memory instances.
        verified = BudgetBook.from_dict(state)
        previous = self.load_book(session, book.authorization_id)
        if previous is None:
            if previous_state_id is not None or state["events"]:
                raise AuditError("batch_budget_initial_state_must_be_empty")
        else:
            old, identifier = previous
            prior_state = old.to_dict()
            if previous_state_id != identifier:
                raise AuditError("batch_budget_stale_state_or_reset")
            if (prior_state["config"] != state["config"]
                    or state["events"][:len(prior_state["events"])] != prior_state["events"]):
                raise AuditError("batch_budget_history_changed")
            if state == prior_state:
                self.engine.ledger.append(session, "batch.budget.reused", {"record": identifier})
                return identifier
        state_ref = self._save(session, state)
        return self.engine.ledger.record(session, BUDGET_KIND, book.authorization_id, {
            "method": METHOD, "authorization_id": book.authorization_id, "state_ref": state_ref,
            "previous_state_id": previous_state_id, "price_fingerprint": verified.price_policy.fingerprint,
            "committed_nanousd": verified.committed_nanousd, "charged_nanousd": verified.charged_nanousd,
            "reserved_nanousd": verified.reserved_nanousd, "frozen": verified.frozen, "saved_at": utc(),
        }, supersedes=previous_state_id)

    def _scope(self, session: str, plan_id: str, policy_id: str, authorization_id: str) -> Json:
        require_active(self.engine, session)
        if self.engine.config.offline:
            raise ResearchError("batch_live_requires_explicit_online_configuration")
        plan = self.engine.ledger.get(plan_id)
        policy = self.engine.ledger.get(policy_id, "policy")["content"]
        if (plan.get("authorization_id") != authorization_id
                or policy.get("authorization_id") != authorization_id
                or plan_id not in policy.get("plan_ids", [])
                or policy.get("allow_external_processing") is not True
                or policy.get("allow_paid_inference") is not True
                or not policy.get("approved_by") or not policy.get("instruction")):
            raise ResearchError("batch_live_exact_plan_authorization_required")
        if _rows(self.engine, STOP_KIND, authorization_id):
            raise AuditError("batch_live_authorization_stopped")
        return plan

    def _stop(self, session: str, authorization_id: str, action_id: str, reason: str) -> None:
        self.engine.ledger.record(session, STOP_KIND, authorization_id, {
            "method": METHOD, "authorization_id": authorization_id, "action_id": action_id,
            "reason": reason, "stopped_at": utc(),
        })

    def _paid_intents(self, session: str, authorization_id: str, plan_id: str, policy_id: str,
                      request_ids: list[str], attempt_ids: list[str], create_body: bytes) -> str:
        if (not request_ids or len(set(request_ids)) != len(request_ids)
                or len(attempt_ids) != len(request_ids) or len(set(attempt_ids)) != len(attempt_ids)):
            raise AuditError("batch_live_create_requires_unique_reserved_attempts")
        saved = self.load_book(session, authorization_id)
        if saved is None:
            raise AuditError("batch_live_budget_missing")
        book, state_id = saved
        policy = self.engine.ledger.get(policy_id, "policy")["content"]
        if (policy.get("ceiling_nanousd") != book.ceiling_nanousd
                or policy.get("operational_limit_nanousd") != book.operational_limit_nanousd
                or policy.get("price_fingerprint") != book.price_policy.fingerprint):
            raise AuditError("batch_live_budget_policy_mismatch")
        if book.frozen or book.committed_nanousd > book.operational_limit_nanousd:
            raise AuditError("batch_live_budget_frozen_or_exceeded")
        actions = [row for row in _rows(self.engine, ACTION_KIND)
                   if row.get("authorization_id") == authorization_id]
        action_map = {row["action_id"]: row for row in actions}
        receipts = [row for row in _rows(self.engine, RECEIPT_KIND)
                    if row.get("authorization_id") == authorization_id
                    and row.get("unknown") is False and type(row.get("status")) is int
                    and 200 <= row["status"] < 300 and row.get("body_ref")]
        create = json.loads(create_body)
        uploads = []
        counts: dict[str, list[tuple[Json, Json]]] = {}
        for receipt in receipts:
            action = action_map.get(receipt["action_id"])
            if not action or action.get("plan_id") != plan_id or action.get("policy_id") != policy_id:
                continue
            if action.get("phase") not in {"upload", "count"}:
                continue
            try:
                parsed = json.loads(self.engine.ledger.artifacts.read_bytes(receipt["body_ref"]))
            except (ValueError, UnicodeError):
                continue
            if not isinstance(parsed, dict):
                continue
            if action["phase"] == "upload" and parsed.get("id") == create["input_file_id"]:
                uploads.append((action, parsed))
            elif action["phase"] == "count":
                counts.setdefault(receipt["body_sha256"], []).append((action, receipt))
        if len(uploads) != 1:
            raise AuditError("batch_live_create_requires_exact_retained_upload")
        upload_action, upload_receipt = uploads[0]
        upload_exact = self.engine.ledger.artifacts.read(upload_action["exact_request_ref"])
        raw_jsonl = self.engine.ledger.artifacts.read_bytes(upload_exact["original_body_ref"])
        if (upload_receipt.get("purpose") != "batch" or type(upload_receipt.get("bytes")) is not int
                or upload_receipt["bytes"] != len(raw_jsonl)
                or hashlib.sha256(raw_jsonl).hexdigest() != upload_exact["logical_request"].get("content_sha256")):
            raise AuditError("batch_live_upload_receipt_mismatch")
        file_rows = [json.loads(line) for line in raw_jsonl.splitlines()]
        uploaded = {row["custom_id"]: row for row in file_rows}
        if len(uploaded) != len(file_rows) or set(uploaded) != set(request_ids):
            raise AuditError("batch_live_uploaded_budget_request_set_mismatch")
        for request_id, attempt_id in zip(request_ids, attempt_ids, strict=True):
            reservation = book.entry(request_id)
            request = reservation["request"]
            intended = self.engine.ledger.unresolved.get(attempt_id)
            if (reservation["status"] != "reserved" or request["plan_id"] != plan_id
                    or not intended or intended.get("budget_authorization_id") != authorization_id
                    or intended.get("budget_request_id") != request_id
                    or intended.get("task_key") != request["task_id"]
                    or intended.get("request_sha256") != request["request_sha256"]):
                raise AuditError("batch_live_reserved_intent_mismatch")
            exact = self.engine.ledger.artifacts.read_bytes(intended["request"])
            if hashlib.sha256(exact).hexdigest() != request["request_sha256"]:
                raise AuditError("batch_live_reserved_request_bytes_mismatch")
            paid = json.loads(exact)
            row = uploaded[request_id]
            if (set(row) != {"custom_id", "method", "url", "body"}
                    or row["method"] != "POST" or row["url"] != "/v1/responses"
                    or canonical(row["body"]).encode() != exact
                    or paid.get("model") != book.price_policy.model
                    or type(paid.get("max_output_tokens")) is not int
                    or paid["max_output_tokens"] != request["max_output_tokens"]):
                raise AuditError("batch_live_uploaded_request_cap_or_model_mismatch")
            expected_count = count_request_body(paid)
            verified_count = False
            for count_action, count_receipt in counts.get(request["input_count"]["receipt_sha256"], []):
                count_exact = self.engine.ledger.artifacts.read(count_action["exact_request_ref"])
                count_body = self.engine.ledger.artifacts.read(count_exact["original_body_ref"])
                count_answer = self.engine.ledger.artifacts.read(count_receipt["body_ref"])
                if (count_body == expected_count and type(count_answer.get("input_tokens")) is int
                        and count_answer["input_tokens"] == request["input_count"]["input_tokens"]
                        and (request["input_count"].get("provider_request_id") is None
                             or request["input_count"]["provider_request_id"] == count_receipt["provider_request_id"])):
                    verified_count = True
                    break
            if not verified_count:
                raise AuditError("batch_live_exact_provider_count_provenance_missing")
            # Dispatch artifact is independently required by model preflight.
            self.engine.ledger.artifacts.read_bytes(intended["dispatch"])
        for prior in actions:
            if (prior.get("authorization_id") == authorization_id and prior.get("phase") == "create"
                    and set(request_ids) & set(prior.get("reserved_request_ids", []))):
                raise AuditError("batch_live_reserved_request_already_dispatched")
        return state_id

    def execute_action(self, session: str, *, plan_id: str, policy_id: str, authorization_id: str,
                       action_key: str, request: Json, body: bytes | None, transport: Any,
                       reserved_request_ids: list[str] | tuple[str, ...] = (),
                       attempt_ids: list[str] | tuple[str, ...] = ()) -> Json:
        """Return retained receipt metadata; caller parses ``body_ref`` afterward.

        Exact repeats return ``reused=True`` and never issue HTTP. Unknown prior
        actions block. Distinct polling observation keys are allowed; changing a
        mutation/count key cannot reissue the same exact logical request.
        """
        self._scope(session, plan_id, policy_id, authorization_id)
        if not isinstance(action_key, str) or not action_key:
            raise ResearchError("batch_live_action_key_required")
        if getattr(transport, "max_retries", None) != 0:
            raise ResearchError("batch_live_transport_retries_forbidden")
        action_id = digest({"authorization_id": authorization_id, "action_key": action_key})
        prepared = prepare_request(request, body, action_id)
        path = request["path"]
        phase = ("count" if path == "/v1/responses/input_tokens" else
                 "upload" if path == "/v1/files" else
                 "create" if path == "/v1/batches" and request["method"] == "POST" else
                 "list" if path == "/v1/batches" else
                 "download" if path.endswith("/content") else "poll")
        logical_hash = digest({"request": request, "body_sha256": hashlib.sha256(body).hexdigest() if body is not None else None})
        binding = {"method": METHOD, "authorization_id": authorization_id, "plan_id": plan_id,
                   "policy_id": policy_id, "action_key": action_key, "action_id": action_id,
                   "phase": phase, "logical_hash": logical_hash,
                   "reserved_request_ids": list(reserved_request_ids), "attempt_ids": list(attempt_ids)}
        old = _rows(self.engine, ACTION_KIND, action_id)
        if old:
            if any(old[0].get(key) != value for key, value in binding.items()):
                raise AuditError("batch_live_action_identity_changed")
            receipts = _rows(self.engine, RECEIPT_KIND, action_id)
            if not receipts or receipts[-1].get("unknown") is not False:
                raise AuditError("batch_live_unknown_action_no_retry")
            self.engine.ledger.append(session, "batch.action.receipt.reused", {
                "action_id": action_id, "receipt": receipts[-1]["id"], "explicit_cache_reuse": True})
            return {**receipts[-1], "reused": True}
        if request["method"] == "POST":
            # Indexed immutable reservation avoids scanning all earlier count
            # calls for every article. If the later intent write fails, this
            # reservation still blocks implicit reissue under a changed key.
            identity_key = digest([authorization_id, logical_hash])
            if _rows(self.engine, ACTION_IDENTITY_KIND, identity_key):
                raise AuditError("batch_live_changed_key_retry_forbidden")
        state_id = None
        if phase == "create":
            state_id = self._paid_intents(session, authorization_id, plan_id, policy_id,
                                          list(reserved_request_ids), list(attempt_ids), body or b"")
        elif reserved_request_ids or attempt_ids:
            raise ResearchError("batch_live_attempts_only_for_create")
        wire_body_ref = self._save(session, prepared.body) if prepared.body is not None else None
        original_body_ref = self._save(session, body) if body is not None else None
        exact_ref = self._save(session, {"method": prepared.method, "url": prepared.url,
            "headers_excluding_authentication": prepared.headers, "wire_body_ref": wire_body_ref,
            "original_body_ref": original_body_ref, "logical_request": request})
        if request["method"] == "POST":
            self.engine.ledger.record(session, ACTION_IDENTITY_KIND, identity_key, {
                "method": METHOD, "authorization_id": authorization_id, "action_id": action_id,
                "logical_hash": logical_hash, "exact_request_ref": exact_ref, "reserved_at": utc()})
        self.engine.ledger.record(session, ACTION_KIND, action_id, {
            **binding, "exact_request_ref": exact_ref, "budget_state_id": state_id, "started_at": utc()})
        try:
            receipt = transport.perform(request, body, action_id)
        except Exception as error:
            # A durable intent exists. Even a seemingly local exception remains
            # unknown unless an explicit recovery confirms no provider dispatch.
            receipt = BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)
        if not isinstance(receipt, BatchReceipt):
            self._stop(session, authorization_id, action_id, "invalid_transport_receipt")
            raise AuditError("batch_live_invalid_transport_receipt")
        try:
            if receipt.retention_error:
                raise ResearchError("batch_live_transport_retention_failed")
            if (receipt.body is not None and not isinstance(receipt.body, bytes)
                    or type(receipt.unknown) is not bool
                    or receipt.status is not None and (type(receipt.status) is not int or not 100 <= receipt.status <= 599)):
                raise ResearchError("batch_live_transport_receipt_invalid")
            require_no_credentials({"headers": receipt.headers, "request_id": receipt.request_id,
                                    "error_type": receipt.error_type, "body_sha256": receipt.body_sha256})
            raw_ref = self._save(session, receipt.body) if receipt.body is not None else None
            raw_hash = hashlib.sha256(receipt.body).hexdigest() if receipt.body is not None else None
            if receipt.body_sha256 is not None and receipt.body_sha256 != raw_hash:
                raise ResearchError("batch_live_receipt_hash_mismatch")
        except ResearchError:
            self._stop(session, authorization_id, action_id, "response_retention_failed")
            raise AuditError("batch_live_response_retention_failed") from None
        value = {"method": METHOD, "authorization_id": authorization_id, "plan_id": plan_id,
                 "action_id": action_id, "phase": phase, "body_ref": raw_ref, "body_sha256": raw_hash,
                 "status": receipt.status, "provider_request_id": receipt.request_id, "headers": receipt.headers,
                 "error_type": receipt.error_type, "unknown": bool(receipt.unknown or receipt.body is None),
                 "received_at": utc()}
        require_no_credentials(value)
        identifier = self.engine.ledger.record(session, RECEIPT_KIND, action_id, value)
        return {"id": identifier, **value, "reused": False}
