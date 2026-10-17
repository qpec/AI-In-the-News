"""Audited asynchronous Batch lifecycle, currently restricted to injected fixtures.

This is executable software scaffolding, not a live OpenAI adapter. There is no
HTTP implementation, credential reader, production materializer or automatic
retry here. Real plans fail closed even if a caller injects a transport. The
descriptor-only corpus plans are deliberately incompatible with this module.

One runtime writer owns every artifact, intent, receipt and attempt projection.
At most four *HTTP operations* run together; this is not a remote-job limit.
Queue reservations persist until a retained terminal provider observation.

Every phase currently rereads the complete plan, packets and JSONL. This has
not been demonstrated efficient at corpus scale. A production coordinator needs
one verified frozen plan per active Research.execute session, per-action hash
checks, staggered polling, creation-rate control and explicit receipt recovery.
It also needs audited materialization and sealed/unresolved-frame eligibility
review. This module implements none of those missing production integrations.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Protocol
import uuid

from .common import AuditError, Context, Json, ResearchError, canonical, digest, require_active, require_no_credentials, utc
from .gateway import Gateway
from .runtime import Research, audited_handler

METHOD = "event-multibatch-lifecycle-fixture-v1"
MODEL = "gpt-6-luna"
ENDPOINT = "/v1/responses"
TERMINAL = frozenset({"completed", "failed", "expired", "cancelled"})
PRODUCTION_ENABLED = False


@dataclass(frozen=True)
class Receipt:
    body: bytes
    status: int
    request_id: str | None = None


class FixtureTransport(Protocol):
    """A fixture must not perform network I/O; no production implementation ships."""

    synthetic: bool

    def perform(self, request: Json, body: bytes | None, client_request_id: str) -> Receipt: ...


class Contract(Protocol):
    """The production contract must eventually be pinned, not caller selectable."""

    def contract_digest(self) -> str: ...
    def validate_packet(self, packet: Json) -> list[str]: ...
    def request_matches_packet(self, request: Json, packet: Json) -> bool: ...
    def validate_response(self, result: Json, packet: Json) -> list[str]: ...


def _records(engine: Any, kind: str, key: str | None = None) -> list[Json]:
    sql, parameters = "SELECT id,payload FROM records WHERE kind=?", [kind]
    if key is not None:
        sql += " AND logical_key=?"
        parameters.append(key)
    sql += " ORDER BY created_event"
    return [{"id": row["id"], **json.loads(row["payload"])}
            for row in engine.ledger.db.execute(sql, parameters)]


def _save(engine: Any, session: str, value: bytes | Json) -> str:
    if isinstance(value, bytes):
        require_no_credentials(value.decode("utf-8", errors="replace"))
        reference = engine.ledger.artifacts.put_bytes(value)
    else:
        reference = engine.ledger.artifacts.put(value)
    # Use the existing preflight allowlist; nested refs alone are insufficient.
    engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference})
    return reference


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ResearchError("batch_invalid_" + name)
    return value


def _money(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ResearchError("batch_invalid_cost") from None
    if not amount.is_finite() or amount < 0:
        raise ResearchError("batch_invalid_cost")
    return amount


def _time(value: Any) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        raise ResearchError("batch_invalid_timestamp") from None
    if result.tzinfo is None:
        raise ResearchError("batch_invalid_timestamp")
    return result


def parse_model_row(row: Json, request: Json, packet: Json, contract: Contract) -> tuple[Json, Json]:
    """Validate one retained Responses receipt against its exact full-text packet."""
    response = row.get("response")
    if row.get("error") or not isinstance(response, dict) or response.get("status_code") != 200:
        raise ResearchError("batch_request_error")
    body = response.get("body")
    if (not isinstance(body, dict) or body.get("model") != request["body"]["model"]
            or body.get("status") != "completed" or body.get("error") or body.get("incomplete_details")):
        raise ResearchError("batch_response_incomplete_or_wrong_model")
    content = [part for item in body.get("output", []) if item.get("type") == "message"
               for part in item.get("content", [])]
    if len(content) != 1 or content[0].get("type") != "output_text":
        raise ResearchError("batch_response_not_single_structured_output")
    result = json.loads(content[0]["text"])
    errors = contract.validate_response(result, packet)
    if errors:
        raise ResearchError("batch_literal_or_schema_validation_failed")
    return result, {"status": "valid", "packet_complete": True,
                    "semantic_entailment_validated": False, "human_validated": False}


class EventMultibatchGateway(Gateway):
    """Shared gateway extension; only the main thread writes durable state."""

    def _plan(self, session: str, context: Context, data: Json) -> tuple[Json, Json, Contract]:
        require_active(self.engine, session)
        plan = self.engine.ledger.get(data["plan"], "event_multibatch_execution_plan")
        transport = getattr(self.engine, "event_batch_transport", None)
        contract = getattr(self.engine, "event_batch_contract", None)
        if (plan.get("synthetic") is not True or transport is None or getattr(transport, "synthetic", False) is not True):
            raise ResearchError("batch_production_lifecycle_not_enabled")
        if self.engine.config.offline:
            raise ResearchError("batch_transport_requires_explicit_online_configuration")
        if (plan.get("method") != METHOD or plan.get("upload_ready") is not True
                or plan.get("source_material_retained") is not True or contract is None
                or plan.get("contract_sha256") != contract.contract_digest()
                or plan.get("versions") != context.versions or plan.get("model") != MODEL):
            raise ResearchError("batch_requires_exact_materialized_plan")
        policy_id = data.get("approval_policy")
        policy = self.engine.ledger.get(policy_id or "", "policy")["content"]
        if (policy.get("method") != METHOD + ":approval" or policy.get("plan") != data["plan"]
                or policy.get("corpus_id") != plan.get("corpus_id")
                or policy.get("manifest_sha256") != plan.get("manifest_sha256")
                or policy.get("request_count") != plan.get("request_count")
                or policy.get("allow_external_processing") is not True
                or policy.get("allow_paid_inference") is not True
                or not policy.get("approved_by") or not policy.get("instruction")):
            raise ResearchError("batch_requires_exact_plan_approval")
        _integer(policy.get("queue_token_allowance"), "known_queue_allowance", 1)
        _integer(policy.get("external_reserved_tokens"), "external_reserved_tokens")
        if not policy.get("queue_allowance_scope") or not policy.get("queue_scope_id"):
            raise ResearchError("batch_queue_allowance_scope_missing")
        _time(policy.get("queue_allowance_observed_at"))
        expiry = _time(policy.get("expires_at"))
        if data["phase"] in {"upload", "create"} and expiry <= datetime.now(timezone.utc):
            raise ResearchError("batch_approval_expired")
        budget = _money(policy.get("max_estimated_cost_usd"))
        shards = plan.get("shards", [])
        if not shards or len({s["shard_id"] for s in shards}) != len(shards):
            raise ResearchError("batch_invalid_shard_manifest")
        if sum(len(s["requests"]) for s in shards) != plan["request_count"]:
            raise ResearchError("batch_request_count_mismatch")
        if sum((_money(s["reserved_cost_usd"]) for s in shards), Decimal(0)) > budget:
            raise ResearchError("batch_plan_exceeds_approved_cost")
        customs: set[str] = set()
        tasks: set[str] = set()
        for shard in shards:
            if shard.get("corpus_id") != plan["corpus_id"] or shard.get("manifest_sha256") != plan["manifest_sha256"]:
                raise ResearchError("batch_partition_mismatch")
            _integer(shard.get("reserved_input_tokens"), "reserved_input_tokens", 1)
            raw = self.engine.ledger.artifacts.read_bytes(shard["jsonl_ref"])
            if len(raw) >= 200_000_000 or not 1 <= len(shard["requests"]) <= 50_000:
                raise ResearchError("batch_provider_file_limit")
            lines = []
            for item in shard["requests"]:
                request = self.engine.ledger.artifacts.read(item["request_ref"])
                packet = self.engine.ledger.artifacts.read(item["packet_ref"])
                if (item["custom_id"] in customs or item["task_key"] in tasks
                        or request.get("custom_id") != item["custom_id"] or request.get("method") != "POST"
                        or request.get("url") != ENDPOINT or request.get("body", {}).get("model") != MODEL
                        or digest({"request": request, "packet": packet, "corpus_id": plan["corpus_id"],
                                   "manifest_sha256": plan["manifest_sha256"],
                                   "contract_sha256": plan["contract_sha256"]}) != item["task_key"]
                        or contract.validate_packet(packet) or not contract.request_matches_packet(request, packet)):
                    raise ResearchError("batch_materialized_request_mismatch")
                customs.add(item["custom_id"])
                tasks.add(item["task_key"])
                lines.append((canonical(request) + "\n").encode("utf-8"))
            if b"".join(lines) != raw:
                raise ResearchError("batch_jsonl_manifest_mismatch")
        previous = _records(self.engine, "event_multibatch_authorization", data["plan"])
        if previous and previous[0]["approval_policy"] != policy_id:
            raise ResearchError("batch_approval_lineage_changed")
        if not previous:
            self.engine.ledger.record(session, "event_multibatch_authorization", data["plan"],
                                      {"plan": data["plan"], "approval_policy": policy_id})
        return plan, policy, contract

    def _history(self, plan: str, shard: str, phase: str) -> list[Json]:
        key = digest([plan, shard, phase])
        return _records(self.engine, "event_multibatch_action", key)

    def _receipt(self, action: Json) -> Json | None:
        receipts = _records(self.engine, "event_multibatch_receipt", action["action_id"])
        valid = [row for row in receipts if row["state"] == "received"]
        return valid[-1] if valid else None

    def _provider(self, plan: str, shard: str, phase: str) -> Json | None:
        actions = self._history(plan, shard, phase)
        if not actions:
            return None
        receipt = self._receipt(actions[-1])
        return receipt.get("parsed") if receipt else None

    def _job(self, plan: str, shard: str) -> Json | None:
        return self._provider(plan, shard, "poll") or self._provider(plan, shard, "create")

    def _intent(self, session: str, data: Json, shard: Json, phase: str, request: Json,
                body_ref: str | None = None) -> Json:
        action_id = str(uuid.uuid4())
        exact = {"phase": phase, "request": request, "body_ref": body_ref, "client_request_id": action_id}
        request_ref = _save(self.engine, session, exact)
        value = {"action_id": action_id, "plan": data["plan"], "shard_id": shard["shard_id"],
                 "phase": phase, "approval_policy": data["approval_policy"],
                 "request_ref": request_ref, "started_at": utc()}
        if phase == "create":
            policy = self.engine.ledger.get(data["approval_policy"], "policy")["content"]
            value.update(queue_scope_id=policy["queue_scope_id"], model=MODEL,
                         reserved_input_tokens=shard["reserved_input_tokens"],
                         reserved_cost_usd=shard["reserved_cost_usd"])
        self.engine.ledger.record(session, "event_multibatch_action", digest([data["plan"], shard["shard_id"], phase]), value)
        return value

    def _validate_receipt(self, action: Json, parsed: Json) -> None:
        """A success HTTP status alone cannot authorize IDs or release capacity."""
        exact = self.engine.ledger.artifacts.read(action["request_ref"])
        if not isinstance(parsed.get("id"), str) or not parsed["id"]:
            raise ResearchError("batch_receipt_id_missing")
        if action["phase"] == "upload":
            body = self.engine.ledger.artifacts.read_bytes(exact["body_ref"])
            if parsed.get("purpose") != "batch" or parsed.get("bytes") != len(body):
                raise ResearchError("batch_upload_receipt_mismatch")
            return
        if action["phase"] == "create":
            expected = self.engine.ledger.artifacts.read(exact["body_ref"])
        else:
            create = self._history(action["plan"], action["shard_id"], "create")
            if not create:
                raise ResearchError("batch_poll_without_create_intent")
            dispatch = self.engine.ledger.artifacts.read(create[0]["request_ref"])
            expected = self.engine.ledger.artifacts.read(dispatch["body_ref"])
            if parsed["id"] != exact["request"]["job_id"]:
                raise ResearchError("batch_poll_job_id_mismatch")
        if (parsed.get("input_file_id") != expected["input_file_id"]
                or parsed.get("endpoint") != expected["endpoint"]
                or parsed.get("metadata") != expected["metadata"]
                or parsed.get("status") not in TERMINAL | {"validating", "in_progress", "finalizing", "cancelling"}):
            raise ResearchError("batch_job_receipt_identity_mismatch")

    def _send(self, session: str, actions: list[Json]) -> list[Json]:
        """Materialize all intents on writer, then send independent I/O only."""
        if not actions:
            return []
        transport: FixtureTransport = getattr(self.engine, "event_batch_transport")
        calls = []
        for action in actions:
            exact = self.engine.ledger.artifacts.read(action["request_ref"])
            body = self.engine.ledger.artifacts.read_bytes(exact["body_ref"]) if exact["body_ref"] else None
            calls.append((action, exact, body))

        def send(call: tuple[Json, Json, bytes | None]) -> tuple[Receipt | None, str | None]:
            try:
                return transport.perform(call[1]["request"], call[2], call[0]["action_id"]), None
            except Exception as error:
                return None, type(error).__name__

        receipts = []
        with ThreadPoolExecutor(max_workers=min(4, len(calls))) as pool:
            futures = {pool.submit(send, call): call[0] for call in calls}
            for future in as_completed(futures):
                action = futures[future]
                receipt, error = future.result()
                value: Json = {"action_id": action["action_id"], "phase": action["phase"],
                               "state": "unknown", "ended_at": utc(), "error_type": error,
                               "raw_ref": None, "parsed": None}
                if receipt is not None:
                    # A retention failure leaves action and model intents unresolved.
                    raw_ref = _save(self.engine, session, receipt.body)
                    value.update(raw_ref=raw_ref, http_status=receipt.status, request_id=receipt.request_id)
                    if action["phase"].startswith("download_"):
                        value["state"] = "received" if receipt.status == 200 else "http_error"
                    else:
                        try:
                            parsed = json.loads(receipt.body)
                            if not isinstance(parsed, dict):
                                raise ValueError("not_object")
                            require_no_credentials(parsed)
                            if 200 <= receipt.status < 300:
                                self._validate_receipt(action, parsed)
                            value.update(state="received" if 200 <= receipt.status < 300 else "http_error", parsed=parsed)
                        except AuditError:
                            raise
                        except (ValueError, TypeError, ResearchError) as failure:
                            value["error_type"] = str(failure) if isinstance(failure, ResearchError) else "malformed_receipt"
                identifier = self.engine.ledger.record(session, "event_multibatch_receipt", action["action_id"], value)
                receipts.append({"id": identifier, **value})
        return receipts

    def event_multibatch(self, session: str, context: Context, data: Json) -> Json:
        plan, policy, contract = self._plan(session, context, data)
        phase = data["phase"]
        if phase not in {"upload", "create", "poll", "collect"}:
            raise ResearchError("batch_phase_invalid")
        selected = data.get("shard_ids", [s["shard_id"] for s in plan["shards"]])
        if len(selected) != len(set(selected)) or not set(selected) <= {s["shard_id"] for s in plan["shards"]}:
            raise ResearchError("batch_shard_selection_invalid")
        shards = [s for s in plan["shards"] if s["shard_id"] in selected]
        if phase == "collect":
            return self._collect(session, context, data, plan, shards, contract)
        reservations = policy["external_reserved_tokens"]
        # One queue scope spans corpus plans. Unknown creates remain reserved.
        for prior_action in _records(self.engine, "event_multibatch_action"):
            if (prior_action["phase"] == "create" and prior_action.get("model") == MODEL
                    and prior_action.get("queue_scope_id") == policy["queue_scope_id"]):
                job = self._job(prior_action["plan"], prior_action["shard_id"])
                if not job or job.get("status") not in TERMINAL:
                    reservations += prior_action["reserved_input_tokens"]
        actions, blocked, reused = [], [], []
        for shard in shards:
            sid = shard["shard_id"]
            history = self._history(data["plan"], sid, phase)
            if phase in {"upload", "create"} and history:
                prior = self._provider(data["plan"], sid, phase)
                if prior and isinstance(prior.get("id"), str) and prior["id"]:
                    reused.append(sid)
                else:
                    blocked.append({"shard_id": sid, "reason": "prior_mutation_no_usable_receipt_no_retry"})
                continue
            if phase == "upload":
                action = self._intent(session, data, shard, phase,
                    {"method": "POST", "path": "/v1/files", "purpose": "batch",
                     "filename": sid + ".jsonl", "content_sha256": shard["jsonl_ref"]}, shard["jsonl_ref"])
            elif phase == "create":
                uploaded = self._provider(data["plan"], sid, "upload")
                if not uploaded or not isinstance(uploaded.get("id"), str) or not uploaded["id"]:
                    blocked.append({"shard_id": sid, "reason": "upload_receipt_missing"})
                    continue
                if reservations + shard["reserved_input_tokens"] > policy["queue_token_allowance"]:
                    blocked.append({"shard_id": sid, "reason": "queue_capacity_reserved"})
                    continue
                for item in shard["requests"]:
                    prior = self.engine.ledger.db.execute(
                        "SELECT 1 FROM events WHERE kind='model.attempt.intended' AND json_extract(payload,'$.task_key')=?",
                        (item["task_key"],)).fetchone()
                    if prior:
                        raise ResearchError("batch_task_already_reserved_no_duplicate")
                body = {"input_file_id": uploaded["id"], "endpoint": ENDPOINT, "completion_window": "24h",
                        "metadata": {"plan": data["plan"], "shard_id": sid, "contract_sha256": plan["contract_sha256"]}}
                body_ref = _save(self.engine, session, body)
                action = self._intent(session, data, shard, phase, {"method": "POST", "path": "/v1/batches"}, body_ref)
                for item in shard["requests"]:
                    attempt = str(uuid.uuid4())
                    intent = {"attempt": attempt, "task_key": item["task_key"], "number": 1,
                              "batch": data["plan"], "request": item["request_ref"],
                              "dispatch": action["request_ref"], "started_at": utc(),
                              "approval_policy": data["approval_policy"], "custom_id": item["custom_id"],
                              "shard_id": sid, "batch_action": action["action_id"]}
                    self.engine.ledger.append(session, "model.attempt.intended", intent)
                    self.engine.ledger.unresolved[attempt] = intent
                reservations += shard["reserved_input_tokens"]
            else:
                job = self._job(data["plan"], sid)
                if not job or not job.get("id"):
                    blocked.append({"shard_id": sid, "reason": "job_receipt_missing"})
                    continue
                if job.get("status") in TERMINAL:
                    reused.append(sid)
                    continue
                action = self._intent(session, data, shard, phase,
                                      {"method": "GET", "path": "/v1/batches/" + job["id"], "job_id": job["id"]})
            actions.append(action)
        receipts = self._send(session, actions)
        return self._result(session, data, {"phase": phase, "action_count": len(actions), "receipts": receipts,
            "blocked": blocked, "reused_shards": reused, "reserved_input_tokens": reservations,
            "remote_jobs_have_no_four_job_cap": True, "http_workers_max": 4})

    def _result(self, session: str, data: Json, result: Json) -> Json:
        value = {"plan": data["plan"], "approval_policy": data["approval_policy"], **result,
                 "production_enabled": False, "automatic_retries": 0, "memberships_changed": False}
        identifier = self.engine.ledger.record(session, "event_multibatch_result", str(uuid.uuid4()), value)
        return {"id": identifier, **value}

    def _collect(self, session: str, context: Context, data: Json, plan: Json,
                 shards: list[Json], contract: Contract) -> Json:
        results, blocked = [], []
        for shard in shards:
            sid = shard["shard_id"]
            job = self._job(data["plan"], sid)
            if not job or job.get("status") not in TERMINAL:
                blocked.append({"shard_id": sid, "reason": "provider_job_not_terminal"})
                continue
            # Validate identity before interpreting terminal state or file pointers.
            created = self._provider(data["plan"], sid, "create")
            upload = self._provider(data["plan"], sid, "upload")
            if (not created or not upload or job.get("id") != created.get("id")
                    or job.get("input_file_id") != upload.get("id") or job.get("endpoint") != ENDPOINT
                    or job.get("metadata") != {"plan": data["plan"], "shard_id": sid,
                                               "contract_sha256": plan["contract_sha256"]}):
                raise AuditError("batch_provider_job_identity_mismatch")
            downloads = []
            for name in ("output_file_id", "error_file_id"):
                if job.get(name):
                    phase = "download_" + name
                    history = self._history(data["plan"], sid, phase)
                    receipt = self._receipt(history[-1]) if history else None
                    if not receipt:
                        action = self._intent(session, data, shard, phase,
                            {"method": "GET", "path": "/v1/files/" + job[name] + "/content", "file_id": job[name]})
                        receipt = self._send(session, [action])[0]
                    if receipt["state"] != "received":
                        blocked.append({"shard_id": sid, "reason": "output_download_incomplete"})
                        break
                    downloads.append(receipt)
            else:
                expected = {item["custom_id"]: item for item in shard["requests"]}
                observed: dict[str, Json] = {}
                for receipt in downloads:
                    raw = self.engine.ledger.artifacts.read_bytes(receipt["raw_ref"])
                    for line in raw.splitlines():
                        if not line.strip():
                            continue
                        try:
                            row = json.loads(line)
                        except (ValueError, TypeError):
                            raise ResearchError("batch_output_malformed_jsonl") from None
                        if not isinstance(row, dict) or row.get("custom_id") not in expected:
                            raise ResearchError("batch_output_foreign_custom_id")
                        if row["custom_id"] in observed:
                            raise ResearchError("batch_output_duplicate_custom_id")
                        observed[row["custom_id"]] = row
                for custom_id, item in expected.items():
                    cached = self.engine.ledger.db.execute("SELECT result_id FROM attempts WHERE task_key=?", (item["task_key"],)).fetchone()
                    if cached:
                        results.append(self.engine.ledger.get(cached["result_id"], "event_multibatch_assessment"))
                        continue
                    intents = [v for v in self.engine.ledger.unresolved.values()
                               if v["task_key"] == item["task_key"] and v["batch"] == data["plan"]]
                    if len(intents) != 1:
                        raise AuditError("batch_missing_exact_model_intent")
                    intent = intents[0]
                    row = observed.get(custom_id)
                    response_ref = _save(self.engine, session, row) if row is not None else None
                    status, result, validation, error = "missing", None, {"status": "missing"}, None
                    body: Json = {}
                    if row is not None:
                        response = row.get("response")
                        if isinstance(response, dict) and isinstance(response.get("body"), dict):
                            body = response["body"]
                        try:
                            result, validation = parse_model_row(row, self.engine.ledger.artifacts.read(item["request_ref"]),
                                self.engine.ledger.artifacts.read(item["packet_ref"]), contract)
                            status = "valid"
                        except AuditError:
                            raise
                        except (ResearchError, ValueError, KeyError, TypeError) as failure:
                            status = "invalid"
                            error = str(failure) if isinstance(failure, ResearchError) else type(failure).__name__
                            validation = {"status": status, "reason_code": error}
                    value = {"custom_id": custom_id, "attempt": intent["attempt"], "task_key": item["task_key"],
                             "plan": data["plan"], "shard_id": sid, "provider_job_id": job["id"],
                             "request_ref": item["request_ref"], "packet_ref": item["packet_ref"],
                             "response_ref": response_ref, "status": status, "result": result, "validation": validation,
                             "observed_model": body.get("model"), "response_id": body.get("id"), "usage": body.get("usage"),
                             "request_id": row.get("response", {}).get("request_id") if row and isinstance(row.get("response"), dict) else None,
                             "versions": context.versions, "human_validated": False,
                             "layer": "provisional_model_interpretation_not_accepted"}
                    assessment = self.engine.ledger.record(session, "event_multibatch_assessment", intent["attempt"], value)

                    def project(event: int) -> None:
                        self.engine.ledger.db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)", (
                            intent["attempt"], item["task_key"], data["plan"], 1, item["request_ref"],
                            response_ref, status, assessment, error, event))

                    self.engine.ledger.append(session, "model.attempt.completed", {
                        "attempt": intent["attempt"], "status": status, "response": response_ref,
                        "assessment": assessment, "validation": validation, "ended_at": utc()}, project)
                    self.engine.ledger.unresolved.pop(intent["attempt"], None)
                    results.append(value)
        counts = {state: sum(row["status"] == state for row in results) for state in ("valid", "invalid", "missing")}
        return self._result(session, data, {"phase": "collect", "items": results, "counts": counts, "blocked": blocked,
            "expected": sum(len(shard["requests"]) for shard in shards),
            "pending": sum(len(shard["requests"]) for shard in shards) - len(results)})


class EventMultibatchResearch(Research):
    """Custom entry point preserves Research.execute preflight and operation audit."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.gateway = EventMultibatchGateway(self, self.gateway.provider)

    @audited_handler
    def _luna_group_validation(self, session: str, context: Context, data: Json) -> Json:
        if not isinstance(self.gateway, EventMultibatchGateway):
            raise AuditError("batch_gateway_extension_missing")
        return self.gateway.event_multibatch(session, context, data)
