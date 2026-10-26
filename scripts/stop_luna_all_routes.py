"""Audited administration only: observe/cancel known Batch jobs after user STOP.

Never starts research, changes the source owner, settles costs, downloads article
outputs, or repeats a cancellation intent. Uses a separate protected audit owner.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import urllib.error
import urllib.request
import uuid

from newsresearch.common import AuditError, Config, canonical, require_active, utc
from newsresearch.event_batch_transport import (
    BatchReceipt, NoBatchRedirect, OpenAIBatchTransport, _OVERRIDES, _safe_raw,
)
from newsresearch.gateway import Gateway, MockProvider
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import check_permissions

METHOD = "luna-explicit-user-stop-administration-v1"
OWNER = Path("C:/Users/ynhan/AppData/Local/AI-In-the-News/luna-all-routes-20261019-v1")
PLAN = "1498d6c42acdd922e7016431b0bda10c538a4c3d642be6c8d5f68956d5d904a0"
ACTIVE = {"validating", "in_progress", "finalizing"}
TERMINAL = {"completed", "failed", "expired", "cancelled"}


def require(condition, message):
    if not condition:
        raise AuditError(message)


def route(job_id, cancel=False):
    require(isinstance(job_id, str) and re.fullmatch(r"batch_[A-Za-z0-9_-]{1,128}", job_id), "invalid_job_id")
    return {"method": "POST" if cancel else "GET", "path": "/v1/batches/" + job_id + ("/cancel" if cancel else "")}


class StopTransport:
    """Only retrieve and cancel; no inference/upload/count/create endpoints."""

    def perform(self, request, body, request_id):
        require(body is None, "stop_request_body_forbidden")
        path = request.get("path", "")
        cancel = request.get("method") == "POST"
        job = path.removeprefix("/v1/batches/").removesuffix("/cancel")
        require(request == route(job, cancel), "stop_route_forbidden")
        if not cancel:
            return OpenAIBatchTransport(timeout_seconds=30).perform(request, None, request_id)
        require(not any(os.environ.get(name) for name in _OVERRIDES), "environment_override_forbidden")
        key = os.environ.get("OPENAI_API_KEY")
        require(key and key.strip() == key and "\r" not in key and "\n" not in key, "credential_unavailable")
        wire = urllib.request.Request("https://api.openai.com" + path, data=b"", method="POST",
            headers={"Authorization": "Bearer " + key, "X-Client-Request-Id": request_id})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoBatchRedirect())
        try:
            response = opener.open(wire, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        except Exception as error:
            return BatchReceipt(None, None, error_type=type(error).__name__, unknown=True)
        status = getattr(response, "status", None) or getattr(response, "code", None)
        try:
            raw = response.read(2_000_001)
            require(len(raw) <= 2_000_000, "receipt_size_limit")
            _safe_raw(raw)
            return BatchReceipt(raw, status, error_type=None if status is not None and 200 <= status < 300 else "http_error",
                unknown=status is None or status >= 500, body_sha256=hashlib.sha256(raw).hexdigest())
        except Exception as error:
            return BatchReceipt(None, status, error_type=type(error).__name__, unknown=True, retention_error="receipt_not_retained")
        finally:
            response.close()


class StopGateway(Gateway):
    def __init__(self, engine, transport):
        super().__init__(engine, MockProvider())
        self.transport = transport

    def exchange(self, session, protocol, job, *, cancel=False):
        require_active(self.engine, session)
        ledger = self.engine.ledger
        job_id = job["job_id"]
        request = route(job_id, cancel)
        if cancel:
            require(not ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_stop_cancel_intent' AND logical_key=?", (job_id,)).fetchone(), "cancellation_already_intended_no_retry")
        identifier = str(uuid.uuid4())
        intent = ledger.record(session, "luna_stop_cancel_intent" if cancel else "luna_stop_poll_intent", job_id,
            {"protocol": protocol, "job_binding": job, "request": request, "request_id": identifier, "at": utc()})
        receipt = self.transport.perform(request, None, identifier)
        saved = {key: value for key, value in asdict(receipt).items() if key != "body"}
        saved.update(intent=intent, job_id=job_id, at=utc(), body_ref=ledger.artifacts.put_bytes(receipt.body) if receipt.body is not None else None)
        ledger.record(session, "luna_stop_http_receipt", identifier, saved)
        if receipt.body is None or receipt.unknown or receipt.retention_error or receipt.status is None or not 200 <= receipt.status < 300:
            return {"job_id": job_id, "observed_status": "unconfirmed", "http_status": receipt.status, "error_type": receipt.error_type}
        try:
            answer = json.loads(receipt.body)
        except (ValueError, UnicodeError):
            return {"job_id": job_id, "observed_status": "unconfirmed", "error_type": "invalid_receipt_json"}
        require(answer.get("id") == job_id and answer.get("endpoint") == "/v1/responses", "remote_job_binding_changed")
        if job.get("input_file_id"):
            require(answer.get("input_file_id") == job["input_file_id"], "remote_file_binding_changed")
        return {"job_id": job_id, "corpus": job["corpus"], "observed_status": answer.get("status"),
            "request_counts": answer.get("request_counts"), "output_file_id": answer.get("output_file_id"),
            "error_file_id": answer.get("error_file_id"), "http_status": receipt.status}


class StopResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        protocol = context.versions["protocol"]
        method = self.ledger.get(protocol, "protocol")["content"]
        require(method["method"] == METHOD and method["implementation_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "stop_method_binding_changed")
        require(data.get("action") in {"status", "stop"}, "unknown_stop_action")
        require((OWNER / "STOP").is_file(), "source_STOP_required")
        check_permissions(OWNER, root=True)
        check_permissions(OWNER / "state.sqlite3")
        plan = json.loads((OWNER / "plan.json").read_text(encoding="utf-8-sig"))
        require(plan["id"] == PLAN, "source_plan_changed")
        source = sqlite3.connect((OWNER / "state.sqlite3").as_uri() + "?mode=ro", uri=True, isolation_level=None)
        try:
            source.execute("PRAGMA query_only=ON")
            source.execute("BEGIN")
            source.execute("SELECT COUNT(*) FROM jobs").fetchone()
            before = hashlib.sha256(source.serialize()).hexdigest()
            jobs = []
            for job_id, payload in source.execute("SELECT job_id,payload FROM jobs WHERE reconciled=0 ORDER BY job_id"):
                value = json.loads(payload)
                require(value["job_id"] == job_id, "local_job_binding_changed")
                create = value.get("provider_create_response", {})
                jobs.append({"job_id": job_id, "corpus": value["corpus_id"],
                    "input_file_id": create.get("input_file_id"), "request_count": len(value["request_ids"])})
        finally:
            source.close()
        self.ledger.record(session, "luna_stop_selection", str(OWNER), {"plan": PLAN, "source_state_sha256": before, "jobs": jobs, "protocol": protocol})
        gateway = self.gateway
        rows = []
        for job in jobs:
            observed = gateway.exchange(session, protocol, job)
            observed["local_request_count"] = job["request_count"]
            rows.append(observed)
            print(canonical(observed), flush=True)
            if data["action"] == "stop" and observed["observed_status"] in ACTIVE:
                prior = self.ledger.db.execute("SELECT 1 FROM records WHERE kind='luna_stop_cancel_intent' AND logical_key=?", (job["job_id"],)).fetchone()
                if prior:
                    observed["cancel"] = {"observed_status": "prior_cancellation_preserved_no_retry"}
                else:
                    observed["cancel"] = gateway.exchange(session, protocol, job, cancel=True)
                print(canonical({"cancellation": observed["cancel"]}), flush=True)
        source = sqlite3.connect((OWNER / "state.sqlite3").as_uri() + "?mode=ro", uri=True)
        try:
            require(hashlib.sha256(source.serialize()).hexdigest() == before, "source_state_changed_during_admin")
        finally:
            source.close()
        states = Counter(row.get("cancel", row)["observed_status"] for row in rows)
        result = {"checked_at": utc(), "action": data["action"], "protocol": protocol, "source_owner": str(OWNER),
            "jobs": rows, "states": dict(states), "source_state_unchanged": True,
            "new_article_requests": 0, "costs_and_holds_unchanged": True,
            "all_remote_jobs_terminal": all(row.get("cancel", row)["observed_status"] in TERMINAL for row in rows)}
        self.ledger.record(session, "luna_stop_result", data["action"], result)
        (self.ledger.root / "latest-stop-status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--action", choices=("status", "stop"), default="status")
    args = parser.parse_args()
    engine = StopResearch(args.workspace, config=Config(offline=False))
    engine.gateway = StopGateway(engine, StopTransport())
    try:
        protocol = engine.execute("version", {"kind": "protocol", "key": METHOD, "amend_latest": True,
            "reason": "Explicit user instruction: Stop all; then report pipeline status",
            "content": {"method": METHOD, "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "source_owner": str(OWNER), "plan": PLAN, "user_instruction": "Stop all",
                "rules": "Read only source state; exact known jobs only; one cancellation intent per job; no new research or retries; preserve STOP, results, costs and holds; retain every HTTP intent and receipt."}},
            objective="Register user-requested shutdown administration", actor="codex:stop-all")["id"]
        result = engine.execute("status", {"action": args.action}, objective="Observe and stop outstanding Batch jobs after explicit user stop",
            actor="codex:stop-all", versions={"protocol": protocol})
        print(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
