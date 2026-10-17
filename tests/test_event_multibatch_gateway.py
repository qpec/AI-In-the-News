"""Synthetic lifecycle checks: no key, network, corpus or scientific findings."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import threading
import time

import pytest

from newsresearch.common import AuditError, Config, ResearchError, canonical, digest
from newsresearch.event_multibatch_gateway import (
    ENDPOINT, METHOD, MODEL, PRODUCTION_ENABLED, EventMultibatchResearch, Receipt,
)
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_event_contract_v2 as contract
finally:
    sys.path.pop(0)


def wire_body(packet):
    return {"model": MODEL, "reasoning": {"effort": "none"}, "store": False, "max_output_tokens": 4096,
            "instructions": packet["model_input"]["instructions"],
            "input": [{"role": "user", "content": [{"type": "input_text", "text": canonical(
                {k: v for k, v in packet["model_input"].items() if k != "instructions"})}]}],
            "text": {"format": {"type": "json_schema", "name": "luna_event_v2", "strict": True,
                                "schema": contract.load_schema()}}}


class FixtureContract:
    contract_digest = staticmethod(contract.contract_digest)
    validate_packet = staticmethod(contract.validate_packet)
    validate_response = staticmethod(contract.validate_output)

    @staticmethod
    def request_matches_packet(request, packet):
        return request["body"] == wire_body(packet)


class FixtureResearch(EventMultibatchResearch):
    @audited_handler
    def _status(self, session, context, data):
        corpus = data.get("corpus", "fictional-incident")
        partition = digest(corpus)
        packet, _ = contract.fictional_example()
        shards = []
        for i in range(data.get("shards", 1)):
            items, lines = [], []
            for j in range(2):
                custom_id = f"fictional_{corpus}_{i}_{j}"
                request = {"custom_id": custom_id, "method": "POST", "url": ENDPOINT, "body": wire_body(packet)}
                items.append({"custom_id": custom_id,
                    "task_key": digest({"request": request, "packet": packet, "corpus_id": corpus,
                                       "manifest_sha256": partition, "contract_sha256": contract.contract_digest()}),
                    "request_ref": self.ledger.artifacts.put(request), "packet_ref": self.ledger.artifacts.put(packet)})
                lines.append((canonical(request) + "\n").encode())
            shards.append({"shard_id": f"fictional_{corpus}_shard_{i}", "corpus_id": corpus,
                           "manifest_sha256": partition, "requests": items,
                           "jsonl_ref": self.ledger.artifacts.put_bytes(b"".join(lines)),
                           "reserved_input_tokens": 100, "reserved_cost_usd": "0.01"})
        value = {"method": METHOD, "synthetic": data.get("synthetic", True),
                 "upload_ready": data.get("upload_ready", True), "source_material_retained": True,
                 "contract_sha256": contract.contract_digest(), "versions": {}, "model": MODEL,
                 "corpus_id": corpus, "manifest_sha256": partition,
                 "request_count": len(shards) * 2, "shards": shards}
        if data.get("partition_mismatch"):
            value["shards"][0]["corpus_id"] = "wrong"
        if data.get("jsonl_mismatch"):
            value["shards"][0]["jsonl_ref"] = self.ledger.artifacts.put_bytes(b"{}\n")
        if data.get("wire_mismatch"):
            request = self.ledger.artifacts.read(value["shards"][0]["requests"][0]["request_ref"])
            request["body"]["instructions"] = "Wrong exact instructions"
            value["shards"][0]["requests"][0]["request_ref"] = self.ledger.artifacts.put(request)
        plan_id = self.ledger.record(session, "event_multibatch_execution_plan", corpus, value)
        policy = {"method": METHOD + ":approval", "plan": plan_id, "corpus_id": corpus,
                  "manifest_sha256": partition, "request_count": len(shards) * 2,
                  "max_estimated_cost_usd": "1.00", "queue_token_allowance": data.get("capacity", 1000),
                  "external_reserved_tokens": data.get("external_reserved_tokens", 0),
                  "queue_allowance_scope": "one fictional provider project and model",
                  "queue_scope_id": "fictional-shared-project-luna",
                  "queue_allowance_observed_at": "2026-10-17T00:00:00+00:00",
                  "allow_external_processing": True, "allow_paid_inference": True,
                  "approved_by": "test:synthetic", "instruction": "Exercise injected fixtures only",
                  "expires_at": "2099-01-01T00:00:00+00:00"}
        policy.update(data.get("policy_override", {}))
        policy_id = self._version(session, context, {"kind": "policy", "key": corpus, "content": policy})["id"]
        return {"plan": plan_id, "approval_policy": policy_id, "shards": [s["shard_id"] for s in shards]}


class FakeTransport:
    synthetic = True

    def __init__(self):
        self.files, self.jobs, self.outputs = {}, {}, {}
        self.calls, self.thread_ids = [], set()
        self.lock = threading.Lock()
        self.active = self.max_active = 0
        self.fail_create = self.missing = self.invalid = self.duplicate = self.foreign = False
        self.bad_poll_identity = self.malformed_download = self.retention_failure = False
        self.complete = False

    def perform(self, request, body, client_request_id):
        with self.lock:
            self.calls.append(deepcopy(request))
            self.thread_ids.add(threading.get_ident())
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(.003)
            path = request["path"]
            if path == "/v1/files":
                file_id = "file-" + client_request_id
                self.files[file_id] = body
                result = {"id": file_id, "purpose": "batch", "bytes": len(body)}
            elif path == "/v1/batches":
                if self.fail_create:
                    raise TimeoutError("Synthetic ambiguous send; no text is persisted")
                sent = json.loads(body)
                job_id = "batch-" + client_request_id
                result = {"id": job_id, **sent, "status": "in_progress", "output_file_id": None, "error_file_id": None}
                self.jobs[job_id] = result
            elif path.startswith("/v1/batches/"):
                job_id = request["job_id"]
                result = deepcopy(self.jobs[job_id])
                if self.bad_poll_identity:
                    result["metadata"]["plan"] = "foreign-plan"
                    result["status"] = "completed"
                elif self.complete:
                    output_id = "output-" + job_id
                    result.update(status="completed", output_file_id=output_id)
                    rows = []
                    original = [json.loads(line) for line in self.files[result["input_file_id"]].splitlines()]
                    for item in original[:-1] if self.missing else original:
                        _, answer = contract.fictional_example()
                        if self.invalid:
                            answer["event"]["participants"][0]["surface"] = "Not present in the fictional source"
                        model_response = {"model": MODEL, "status": "completed", "id": "response-" + item["custom_id"],
                            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                            "output": [{"type": "message", "content": [{"type": "output_text", "text": canonical(answer)}]}]}
                        rows.append({"custom_id": item["custom_id"], "error": None,
                                     "response": {"status_code": 200, "request_id": "request-fictional", "body": model_response}})
                    if self.duplicate:
                        rows.append(deepcopy(rows[0]))
                    if self.foreign:
                        rows[0]["custom_id"] = "foreign-custom-id"
                    self.outputs[output_id] = b"".join((canonical(row) + "\n").encode() for row in reversed(rows))
                self.jobs[job_id] = deepcopy(result)
            else:
                raw = self.outputs[request["file_id"]]
                if self.malformed_download:
                    raw = b"not-json\n"
                if self.retention_failure:
                    raw = b'{"fictional":"Bearer' + b' placeholder"}'
                return Receipt(raw, 200, "fictional-http-request")
            return Receipt(canonical(result).encode(), 200, "fictional-http-request")
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def fixture(tmp_path):
    engine = FixtureResearch(tmp_path / "synthetic-batch", config=Config(offline=False))
    engine.event_batch_transport = FakeTransport()
    engine.event_batch_contract = FixtureContract()
    try:
        yield engine
    finally:
        engine.close()


def prepare(engine, **kwargs):
    return engine.execute("status", kwargs, objective="Prepare source-free Batch fixture", actor="test:synthetic")


def action(engine, prepared, phase, **kwargs):
    return engine.execute("luna_group_validation", {"plan": prepared["plan"],
        "approval_policy": prepared["approval_policy"], "phase": phase, **kwargs},
        objective="Exercise audited source-free Batch lifecycle", actor="test:synthetic")


def finish(engine, prepared):
    action(engine, prepared, "upload")
    action(engine, prepared, "create")
    engine.event_batch_transport.complete = True
    action(engine, prepared, "poll")
    return action(engine, prepared, "collect")


def test_real_v2_full_packets_roundtrip_out_of_order_single_writer_and_exact_resume(fixture):
    prepared = prepare(fixture, shards=6)
    writer_threads = set()
    append = fixture.ledger.append

    def observed_append(*args, **kwargs):
        writer_threads.add(threading.get_ident())
        return append(*args, **kwargs)

    fixture.ledger.append = observed_append
    result = finish(fixture, prepared)
    assert result["counts"] == {"valid": 12, "invalid": 0, "missing": 0}
    assert result["pending"] == 0 and not result["memberships_changed"]
    assert not result["production_enabled"] and not PRODUCTION_ENABLED
    assert len(fixture.event_batch_transport.jobs) == 6  # No four-remote-job cap.
    assert 1 < fixture.event_batch_transport.max_active <= 4
    assert writer_threads == {threading.get_ident()}
    assert not fixture.event_batch_transport.thread_ids & writer_threads
    assert all(row["human_validated"] is False for row in result["items"])
    assert all(row["observed_model"] == MODEL and row["usage"]["output_tokens"] == 20 for row in result["items"])
    calls = len(fixture.event_batch_transport.calls)
    for phase in ("upload", "create", "poll", "collect"):
        action(fixture, prepared, phase)
    assert len(fixture.event_batch_transport.calls) == calls
    assert fixture.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 12
    assert not fixture.ledger.verify()["unresolved_model_attempts"]


def test_unknown_create_is_spent_and_never_submitted_again_after_preflight(fixture):
    prepared = prepare(fixture)
    action(fixture, prepared, "upload")
    fixture.event_batch_transport.fail_create = True
    result = action(fixture, prepared, "create")
    assert result["receipts"][0]["state"] == "unknown"
    assert len(fixture.ledger.verify()["unresolved_model_attempts"]) == 2
    calls = len(fixture.event_batch_transport.calls)
    result = action(fixture, prepared, "create")
    assert result["blocked"][0]["reason"] == "prior_mutation_no_usable_receipt_no_retry"
    assert len(fixture.event_batch_transport.calls) == calls
    assert len(fixture.ledger.unresolved) == 2


def test_shared_queue_scope_counts_both_corpora_and_refills_after_retained_terminal(fixture):
    incident = prepare(fixture, corpus="fictional-incident", capacity=100)
    cyber = prepare(fixture, corpus="fictional-cyber", capacity=100)
    action(fixture, incident, "upload")
    action(fixture, cyber, "upload")
    assert action(fixture, incident, "create")["action_count"] == 1
    blocked = action(fixture, cyber, "create")
    assert blocked["action_count"] == 0 and blocked["reserved_input_tokens"] == 100
    assert blocked["blocked"][0]["reason"] == "queue_capacity_reserved"
    fixture.event_batch_transport.complete = True
    action(fixture, incident, "poll")
    assert action(fixture, cyber, "create")["action_count"] == 1


def test_bad_terminal_receipt_cannot_release_capacity(fixture):
    first = prepare(fixture, corpus="fictional-a", capacity=100)
    second = prepare(fixture, corpus="fictional-b", capacity=100)
    action(fixture, first, "upload")
    action(fixture, second, "upload")
    action(fixture, first, "create")
    fixture.event_batch_transport.bad_poll_identity = True
    result = action(fixture, first, "poll")
    assert result["receipts"][0]["state"] == "unknown"
    assert action(fixture, second, "create")["action_count"] == 0


@pytest.mark.parametrize("mode,counts", [
    ("missing", {"valid": 1, "invalid": 0, "missing": 1}),
    ("invalid", {"valid": 0, "invalid": 2, "missing": 0}),
])
def test_missing_and_literal_failures_are_explicit_null_not_negative(fixture, mode, counts):
    prepared = prepare(fixture)
    setattr(fixture.event_batch_transport, mode, True)
    result = finish(fixture, prepared)
    assert result["counts"] == counts
    assert all(row["result"] is None for row in result["items"] if row["status"] != "valid")
    assert not fixture.ledger.verify()["unresolved_model_attempts"]


@pytest.mark.parametrize("mode,reason", [
    ("duplicate", "duplicate_custom_id"), ("foreign", "foreign_custom_id"),
    ("malformed_download", "malformed_jsonl"),
])
def test_malformed_duplicate_or_foreign_output_leaves_attempts_unresolved(fixture, mode, reason):
    prepared = prepare(fixture)
    setattr(fixture.event_batch_transport, mode, True)
    with pytest.raises(ResearchError, match=reason):
        finish(fixture, prepared)
    assert len(fixture.ledger.verify()["unresolved_model_attempts"]) == 2
    assert fixture.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


@pytest.mark.parametrize("kwargs,reason", [
    ({"synthetic": False}, "production_lifecycle_not_enabled"),
    ({"upload_ready": False}, "requires_exact_materialized_plan"),
    ({"capacity": None}, "known_queue_allowance"),
    ({"partition_mismatch": True}, "partition_mismatch"),
    ({"jsonl_mismatch": True}, "jsonl_manifest_mismatch"),
    ({"wire_mismatch": True}, "materialized_request_mismatch"),
    ({"policy_override": {"max_estimated_cost_usd": "0.001"}}, "exceeds_approved_cost"),
    ({"policy_override": {"allow_paid_inference": False}}, "exact_plan_approval"),
    ({"policy_override": {"expires_at": "2000-01-01T00:00:00+00:00"}}, "approval_expired"),
])
def test_guards_block_before_transport(fixture, kwargs, reason):
    prepared = prepare(fixture, **kwargs)
    with pytest.raises(ResearchError, match=reason):
        action(fixture, prepared, "upload")
    assert not fixture.event_batch_transport.calls


def test_active_operation_and_offline_gates(fixture):
    prepared = prepare(fixture)
    with pytest.raises(AuditError, match="active audited"):
        fixture.gateway.event_multibatch("not-active", None, {})
    fixture.config = Config()
    with pytest.raises(ResearchError, match="explicit_online"):
        action(fixture, prepared, "upload")
    assert not fixture.event_batch_transport.calls


def test_retention_failure_stops_without_accepting_or_clearing_intents(fixture):
    prepared = prepare(fixture)
    fixture.event_batch_transport.retention_failure = True
    with pytest.raises(ResearchError, match="Credential-like"):
        finish(fixture, prepared)
    assert len(fixture.ledger.verify()["unresolved_model_attempts"]) == 2
    assert fixture.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_audit_failure_is_never_downgraded_to_invalid_model_output(fixture):
    prepared = prepare(fixture)

    def fail_audit(result, packet):
        raise AuditError("Synthetic required audit failure")

    fixture.event_batch_contract.validate_response = fail_audit
    with pytest.raises(AuditError, match="required audit failure"):
        finish(fixture, prepared)
    assert len(fixture.ledger.verify()["unresolved_model_attempts"]) == 2
    assert fixture.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_unknown_mutation_survives_real_workspace_reopen(tmp_path):
    workspace = tmp_path / "fictional-reopen"
    engine = FixtureResearch(workspace, config=Config(offline=False))
    engine.event_batch_contract = FixtureContract()
    engine.event_batch_transport = FakeTransport()
    try:
        prepared = prepare(engine)
        action(engine, prepared, "upload")
        engine.event_batch_transport.fail_create = True
        action(engine, prepared, "create")
    finally:
        engine.close()
    reopened = FixtureResearch(workspace, config=Config(offline=False))
    reopened.event_batch_contract = FixtureContract()
    reopened.event_batch_transport = FakeTransport()
    try:
        result = action(reopened, prepared, "create")
        assert result["action_count"] == 0 and result["blocked"]
        assert not reopened.event_batch_transport.calls
        assert len(reopened.ledger.unresolved) == 2
    finally:
        reopened.close()
