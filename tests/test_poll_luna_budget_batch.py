"""Real audited runtime, fictional packets and synthetic HTTP only."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import audited_handler

import test_execute_luna_budget_batch as submit_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import execute_luna_budget_batch as submit
    import poll_luna_budget_batch as poll
    import luna_event_contract_v2 as contract
finally:
    sys.path.pop(0)


class ResultTransport(submit_fixture.SyntheticTransport):
    def __init__(self, mode="valid"):
        super().__init__()
        self.mode = mode

    def result_bytes(self, job_id):
        file_id = self.jobs[job_id]["input_file_id"]
        requests = [json.loads(line) for line in self.files[file_id].splitlines()]
        _, example = contract.fictional_example()
        rows = []
        for index, request in enumerate(requests):
            first = job_id == "batch_1" and index == 0
            if self.mode == "missing" and first:
                continue
            output = deepcopy(example)
            if self.mode == "invalid" and first:
                output["event"]["action"]["surface"] = "not in fictional evidence"
            usage = {"input_tokens": 123, "output_tokens": 100, "total_tokens": 223}
            if self.mode == "usage_missing" and first:
                usage = None
            elif self.mode == "usage_bad_total" and first:
                usage["total_tokens"] = 999
            body = {"id": "response-" + request["custom_id"], "model": "gpt-6-luna",
                "status": "completed", "error": None, "incomplete_details": None, "usage": usage,
                "output": [{"type": "message", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": canonical(output)}]}]}
            if self.mode == "wrong_model" and first:
                body["model"] = "fictional-wrong-model"
            custom = "foreign-id" if self.mode == "foreign" and first else request["custom_id"]
            rows.append({"id": "batch-row-" + custom, "custom_id": custom, "error": None,
                "response": {"status_code": 200, "request_id": "provider-" + custom, "body": body}})
        return b"".join(canonical(row).encode() + b"\n" for row in rows)

    def perform(self, request, body, client_request_id):
        if request["method"] == "POST":
            return super().perform(request, body, client_request_id)
        self.calls.append((request, body, client_request_id))
        path = request["path"]
        if path.startswith("/v1/batches/"):
            identifier = path.rsplit("/", 1)[1]
            created = self.jobs[identifier]
            status = "in_progress" if self.mode == "pending" else "completed"
            answer = {"id": identifier, **created, "status": status,
                      "request_counts": {"total": 8, "completed": 8 if status == "completed" else 0, "failed": 0},
                      "output_file_id": "file-output-" + identifier, "error_file_id": None}
            if self.mode == "wrong_identity":
                answer["input_file_id"] = "file-unrelated"
            raw = canonical(answer).encode()
        elif path.startswith("/v1/files/file-output-"):
            identifier = path.removeprefix("/v1/files/file-output-").removesuffix("/content")
            raw = self.result_bytes(identifier)
        else:
            raise AssertionError("Unexpected synthetic GET")
        return BatchReceipt(raw, 200, "synthetic-read-" + str(len(self.calls)),
                            body_sha256=hashlib.sha256(raw).hexdigest())


class FixtureResearch(poll.ReconciliationResearch):
    @audited_handler
    def _status(self, session, context, data):
        if data["phase"] == "fixture":
            return submit_fixture.FixtureResearch._status(self, session, context, data)
        if data["phase"] == "submit":
            return submit.ExecutionResearch._status(self, session, context, data)
        return super()._status(session, context, data)


def prepared(tmp_path, mode="valid"):
    project = tmp_path / "project"
    project.mkdir()
    transport = ResultTransport(mode)
    engine = FixtureResearch(tmp_path / "protected", project=project, config=Config(offline=False), transport=transport)
    plan = submit_fixture.execute(engine, "fixture")["plan"]
    submitted = submit_fixture.execute(engine, "submit", plan)
    assert submitted["counts"]["submitted"] == 16
    return engine, transport, plan, submitted


def reconcile(engine, plan):
    return submit_fixture.execute(engine, "poll", plan)


def test_completed_outputs_settle_exactly_once_and_resume_without_http(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path)
    try:
        result = reconcile(engine, plan)
        assert result["obstacles"] == []
        assert result["status_counts"] == {"valid": 16, "invalid": 0, "error": 0, "unknown": 0}
        assert result["pending"] == 0 and result["observed_response_rows"] == 16
        assert result["charged_estimate_usd"] > 0 and result["reserved_usd"] == 0
        assert not engine.ledger.unresolved and len(transport.calls) == 24
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 16
        again = reconcile(engine, plan)
        assert again["budget_state"] == result["budget_state"]
        assert again["charged_estimate_usd"] == result["charged_estimate_usd"]
        assert len(transport.calls) == 24
    finally:
        engine.close()


def test_content_invalid_response_still_settles_observed_usage(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path, "invalid")
    try:
        result = reconcile(engine, plan)
        assert result["status_counts"] == {"valid": 15, "invalid": 1, "error": 0, "unknown": 0}
        assert result["charged_estimate_usd"] > 0 and result["reserved_usd"] == 0
        assert not result["budget_frozen"] and not engine.ledger.unresolved
    finally:
        engine.close()


@pytest.mark.parametrize("mode", ["usage_missing", "usage_bad_total"])
def test_unusable_usage_retains_full_reservation_even_with_returned_response(tmp_path, mode):
    engine, transport, plan, submitted = prepared(tmp_path, mode)
    try:
        result = reconcile(engine, plan)
        assert result["status_counts"] == {"valid": 15, "invalid": 0, "error": 1, "unknown": 0}
        assert result["reserved_usd"] > 0 and result["charged_estimate_usd"] > 0
        assert result["observed_response_rows"] == 16 and result["pending"] == 0
        assert not engine.ledger.unresolved
    finally:
        engine.close()


def test_missing_custom_id_stays_unknown_pending_and_reserved(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path, "missing")
    try:
        result = reconcile(engine, plan)
        assert result["status_counts"] == {"valid": 15, "invalid": 0, "error": 0, "unknown": 1}
        assert result["missing_response_rows"] == 1 and result["observed_response_rows"] == 15
        assert result["pending"] == 1 and result["reserved_usd"] > 0
        assert len(engine.ledger.unresolved) == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts WHERE status='unknown'").fetchone()[0] == 1
        assert reconcile(engine, plan)["pending"] == 1 and len(transport.calls) == 24
    finally:
        engine.close()


def test_wrong_model_freezes_budget_and_preserves_its_reservation(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path, "wrong_model")
    try:
        result = reconcile(engine, plan)
        assert result["budget_frozen"] and result["reserved_usd"] > 0
        assert result["status_counts"]["error"] == 1
    finally:
        engine.close()


def test_foreign_output_id_rejects_join_without_settling_that_file(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path, "foreign")
    try:
        result = reconcile(engine, plan)
        assert len(result["obstacles"]) == 1
        assert result["obstacles"][0]["reason"] == "batch_result_foreign_custom_id"
        assert result["status_counts"]["valid"] == 8 and result["pending"] == 8
        assert result["reserved_usd"] > 0 and len(engine.ledger.unresolved) == 8
    finally:
        engine.close()


@pytest.mark.parametrize("mode,obstacles", [("pending", 0), ("wrong_identity", 2)])
def test_unfinished_or_wrong_identity_jobs_never_download_or_settle(tmp_path, mode, obstacles):
    engine, transport, plan, submitted = prepared(tmp_path, mode)
    try:
        result = reconcile(engine, plan)
        assert len(result["obstacles"]) == obstacles
        assert result["pending"] == 16 and result["assessments"] == 0
        assert result["reserved_usd"] == submitted["reserved_usd"]
        assert result["charged_estimate_usd"] == 0 and len(transport.calls) == 22
    finally:
        engine.close()


def test_crash_after_assessment_before_attempt_projection_recovers_without_duplicate_charge(tmp_path):
    engine, transport, plan, submitted = prepared(tmp_path)
    original_append = engine.ledger.append
    crashed = False
    def fail_one_completion(session, kind, value, *args, **kwargs):
        nonlocal crashed
        if kind == "model.attempt.completed" and not crashed:
            crashed = True
            raise AuditError("synthetic_crash_after_assessment")
        return original_append(session, kind, value, *args, **kwargs)
    engine.ledger.append = fail_one_completion
    try:
        with pytest.raises(AuditError, match="synthetic_crash"):
            reconcile(engine, plan)
        assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind=?", (poll.ASSESSMENT_KIND,)).fetchone()[0] == 1
        assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
        assert len(transport.calls) == 22
    finally:
        engine.ledger.append = original_append
        engine.close()
    resumed = FixtureResearch(tmp_path / "protected", project=tmp_path / "project",
                              config=Config(offline=False), transport=transport)
    try:
        result = reconcile(resumed, plan)
        assert result["status_counts"]["valid"] == 16 and result["reserved_usd"] == 0
        assert resumed.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 16
        assert not resumed.ledger.unresolved and len(transport.calls) == 24
        assert reconcile(resumed, plan)["budget_state"] == result["budget_state"]
        assert len(transport.calls) == 24
    finally:
        resumed.close()
