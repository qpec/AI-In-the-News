"""Audited synthetic executor integration; no original owner or external calls."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_budget import PricePolicy
from newsresearch.event_batch_live_gateway import ACTION_KIND, BUDGET_KIND
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import execute_luna_budget_batch as runner
finally:
    sys.path.pop(0)


class SyntheticTransport:
    synthetic = True
    max_retries = 0

    def __init__(self, failure=None):
        self.calls, self.files, self.jobs = [], {}, {}
        self.failure = failure

    def perform(self, request, body, client_request_id):
        self.calls.append((request, body, client_request_id))
        path = request["path"]
        if self.failure == "count_unknown" and path == "/v1/responses/input_tokens":
            return BatchReceipt(None, None, error_type="SyntheticTimeout", unknown=True)
        if self.failure == "count_bad_json" and path == "/v1/responses/input_tokens":
            return BatchReceipt(b"not-json", 200)
        if self.failure == "retention" and path == "/v1/responses/input_tokens":
            return BatchReceipt(None, 200, retention_error="credential_guard")
        if self.failure == "create_unknown" and path == "/v1/batches":
            return BatchReceipt(None, None, error_type="SyntheticTimeout", unknown=True)
        if self.failure == "create_rejected" and path == "/v1/batches":
            return BatchReceipt(b'{"error":{"code":"synthetic_queue_full"}}', 429, error_type="http_error")
        if path == "/v1/responses/input_tokens":
            payload = {"input_tokens": 123}
        elif path == "/v1/files":
            identifier = "file-" + str(len(self.files) + 1)
            self.files[identifier] = body
            payload = {"id": identifier, "purpose": "batch", "bytes": len(body)}
        elif path == "/v1/batches":
            create = json.loads(body)
            identifier = "batch_" + str(len(self.jobs) + 1)
            self.jobs[identifier] = create
            payload = {"id": identifier, **create, "status": "validating"}
        else:
            raise AssertionError("Unexpected synthetic route")
        raw = canonical(payload).encode()
        return BatchReceipt(raw, 200, "synthetic-" + str(len(self.calls)), body_sha256=hashlib.sha256(raw).hexdigest())


class FixtureResearch(runner.ExecutionResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] != "fixture":
            return super()._status(session, context, data)
        tasks = []
        for corpus in ("incident-reports", "cybercrime"):
            for index in range(data.get("per_corpus", 8)):
                custom = f"synthetic-{corpus}-{index}"
                body = {"model": "gpt-6-luna", "instructions": "Synthetic test: return fictional JSON only",
                    "input": "Fictional article " + custom, "max_output_tokens": 512,
                    "text": {"format": {"type": "json_schema", "name": "fictional", "strict": True,
                        "schema": {"type": "object", "properties": {}, "additionalProperties": False}}}}
                body_ref = runner.save(self, session, body, "Synthetic request body")
                request = {"custom_id": custom, "method": "POST", "url": "/v1/responses", "body": body}
                request_ref = runner.save(self, session, request, "Synthetic Batch row")
                tasks.append({"custom_id": custom, "corpus_id": corpus, "request_body_ref": body_ref,
                              "request_ref": request_ref, "descriptor": {"synthetic": True}})
        price = PricePolicy("gpt-6-luna", 100_000_000, 125_000_000, 500_000_000,
                            (1, 2), (11, 10), (2, 1), (3, 2), 272_000,
                            "https://example.invalid/synthetic-price", "2026-10-17T00:00:00Z")
        plan = {"authorization_id": runner.STUDY, "price_policy": asdict(price), "canary_tasks": tasks}
        plan_id = self.ledger.record(session, runner.PLAN_KIND, "synthetic-plan", plan)
        return {"plan": plan_id}


def execute(engine, phase, plan=None, **extra):
    return engine.execute("status", {"phase": phase, "plan": plan, "allow_paid_execution": True, **extra},
                          objective="Synthetic integration of audited budget Batch executor", actor="test:synthetic")


def engine_at(tmp_path, failure=None):
    project = tmp_path / "project"
    project.mkdir(exist_ok=True)
    transport = SyntheticTransport(failure)
    engine = FixtureResearch(tmp_path / "protected", project=project, config=Config(offline=False), transport=transport)
    return engine, transport


def test_audited_canary_submission_partitions_two_files_and_resume_sends_nothing(tmp_path):
    engine, transport = engine_at(tmp_path)
    try:
        plan = execute(engine, "fixture")["plan"]
        result = execute(engine, "submit", plan)
        assert result["obstacle"] is None
        assert result["counts"] == {"prepared": 16, "submitted": 16, "valid": 0, "invalid": 0, "pending": 16,
            "unknown_create_requests": 0, "rejected_create_requests": 0, "unsubmitted": 0,
            "new_embeddings": 0, "automatic_retries": 0}
        assert len(transport.calls) == 20  # 16 exact counts, two uploads, two creates.
        assert result["reserved_usd"] > 0 and result["charged_estimate_usd"] == 0
        assert len(transport.files) == 2
        for raw in transport.files.values():
            rows = [json.loads(line) for line in raw.splitlines()]
            assert len(rows) == 8
            assert len({row["custom_id"].split("-")[1] for row in rows}) == 1
        second = execute(engine, "submit", plan)
        assert second["counts"] == result["counts"]
        assert len(transport.calls) == 20 and second["budget_state"] == result["budget_state"]
        assert len(engine.ledger.unresolved) == 16
    finally:
        engine.close()


def test_new_runtime_resumes_same_provider_jobs_without_count_upload_or_create(tmp_path):
    engine, transport = engine_at(tmp_path)
    try:
        plan = execute(engine, "fixture")["plan"]
        first = execute(engine, "submit", plan)
    finally:
        engine.close()
    resumed = FixtureResearch(tmp_path / "protected", project=tmp_path / "project",
                              config=Config(offline=False), transport=SyntheticTransport())
    try:
        result = execute(resumed, "submit", plan)
        assert resumed.transport.calls == []
        assert result["jobs"] == first["jobs"]
        assert result["budget_state"] == first["budget_state"]
        assert len(resumed.ledger.unresolved) == 16
    finally:
        resumed.close()


@pytest.mark.parametrize("failure,obstacle", [("count_unknown", "unknown_no_retry"),
                                               ("count_bad_json", "json_invalid")])
def test_count_failure_never_dispatches_models_and_cannot_reissue_count(tmp_path, failure, obstacle):
    engine, transport = engine_at(tmp_path, failure)
    try:
        plan = execute(engine, "fixture")["plan"]
        result = execute(engine, "submit", plan)
        assert obstacle in result["obstacle"]
        assert len(transport.calls) == 1 and transport.jobs == {}
        assert result["counts"]["unsubmitted"] == 16
        assert result["reserved_usd"] == 0 and not engine.ledger.unresolved
        if failure == "count_unknown":
            with pytest.raises(AuditError, match="unknown_action_no_retry"):
                execute(engine, "submit", plan)
        else:
            assert execute(engine, "submit", plan)["obstacle"] == result["obstacle"]
        assert len(transport.calls) == 1
    finally:
        engine.close()


@pytest.mark.parametrize("failure,unknown,rejected", [("create_unknown", 8, 0), ("create_rejected", 0, 8)])
def test_create_failures_preserve_full_budget_and_report_unknown_or_rejected_coverage(tmp_path, failure, unknown, rejected):
    engine, transport = engine_at(tmp_path, failure)
    try:
        plan = execute(engine, "fixture")["plan"]
        result = execute(engine, "submit", plan)
        assert result["counts"]["submitted"] == 0
        assert result["counts"]["unknown_create_requests"] == unknown
        assert result["counts"]["rejected_create_requests"] == rejected
        assert result["counts"]["unsubmitted"] == 8
        assert result["reserved_usd"] > 0 and len(engine.ledger.unresolved) == 8
        assert len(transport.calls) == 10
        if failure == "create_unknown":
            with pytest.raises(AuditError, match="unknown_action_no_retry"):
                execute(engine, "submit", plan)
        else:
            again = execute(engine, "submit", plan)
            assert again["counts"] == result["counts"]
            assert again["reserved_usd"] == result["reserved_usd"]
        assert len(transport.calls) == 10
    finally:
        engine.close()


def test_retention_failure_stops_immediately_and_is_not_caught_as_recoverable_progress(tmp_path):
    engine, transport = engine_at(tmp_path, "retention")
    try:
        plan = execute(engine, "fixture")["plan"]
        with pytest.raises(AuditError, match="response_retention_failed"):
            execute(engine, "submit", plan)
        assert len(transport.calls) == 1
        with pytest.raises(AuditError, match="authorization_stopped"):
            execute(engine, "submit", plan)
        assert len(transport.calls) == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='luna_budget_execution_obstacle'").fetchone()[0] == 0
    finally:
        engine.close()


def test_wrong_canary_count_rejected_before_http(tmp_path):
    engine, transport = engine_at(tmp_path)
    try:
        plan = execute(engine, "fixture", per_corpus=7)["plan"]
        with pytest.raises(AuditError, match="exact_canary_count"):
            execute(engine, "submit", plan)
        assert transport.calls == []
    finally:
        engine.close()


def test_budget_and_model_intents_persist_before_first_paid_create(tmp_path):
    engine, transport = engine_at(tmp_path)
    try:
        plan = execute(engine, "fixture")["plan"]
        execute(engine, "submit", plan)
        budget_rows = list(engine.ledger.db.execute("SELECT created_event FROM records WHERE kind=?", (BUDGET_KIND,)))
        assert len(budget_rows) == 3
        create_actions = [json.loads(row["payload"]) for row in engine.ledger.db.execute("SELECT payload FROM records WHERE kind=?", (ACTION_KIND,))
                          if json.loads(row["payload"])["phase"] == "create"]
        assert len(create_actions) == 2
        for action in create_actions:
            persisted = engine.ledger.get(action["budget_state_id"], BUDGET_KIND)
            assert persisted["reserved_nanousd"] > 0
            for attempt in action["attempt_ids"]:
                assert attempt in engine.ledger.unresolved
    finally:
        engine.close()
