"""Synthetic exact-count collision diagnosis and audited-store smoke test."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config, canonical, digest
from newsresearch.event_batch_budget import BudgetBook, PricePolicy
from newsresearch.event_batch_live_gateway import EventBatchLiveGateway
from newsresearch.runtime import audited_handler

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import diagnose_luna_batch_capacity as runner
finally:
    sys.path.pop(0)


def fixture():
    artifacts = {}
    def put(value):
        reference = digest(value)
        artifacts[reference] = canonical(value).encode()
        return reference
    body = {"model": "gpt-6-luna", "instructions": "synthetic", "input": "synthetic input",
            "text": {}, "max_output_tokens": 4096}
    body_ref = put(body)
    count_ref = put(runner.count_request_body(body))
    logical = digest({"request": runner.COUNT_REQUEST, "body_sha256": count_ref})
    exact_ref = put({"original_body_ref": count_ref, "logical_request": runner.COUNT_REQUEST})
    answer = put({"input_tokens": 55})
    action_id = digest({"authorization_id": runner.STUDY, "action_key": "count:old"})
    rows = {"actions": [{"id": "action-record", "action_id": action_id, "phase": "count", "plan_id": "plan",
        "authorization_id": runner.STUDY, "action_key": "count:old", "logical_hash": logical, "exact_request_ref": exact_ref}],
        "identities": [{"id": "identity-record", "authorization_id": runner.STUDY, "action_id": action_id,
                        "logical_hash": logical, "exact_request_ref": exact_ref}],
        "receipts": [{"id": "receipt-record", "authorization_id": runner.STUDY, "action_id": action_id,
            "plan_id": "plan", "phase": "count", "unknown": False, "status": 200, "body_ref": answer, "body_sha256": answer}]}
    task = {"custom_id": "new", "corpus_id": "incident-reports", "manifest": "manifest", "request_body_ref": body_ref}
    return artifacts, rows, task


def test_identical_count_changed_key_is_collision_without_new_dispatch():
    artifacts, rows, task = fixture()
    result = runner.diagnose_counts("plan", [task], rows, artifacts.__getitem__)[0]
    assert result["changed_key_collision"] and result["gateway_dispatch_intent_absent"]
    assert result["successful_exact_count_available"]
    assert result["candidates"][0]["input_tokens"] == 55
    assert result["candidates"][0]["receipt_record"] == "receipt-record"
    assert "synthetic input" not in canonical(result)


@pytest.mark.parametrize("fault", ["unknown", "http_error", "missing_action", "wrong_plan"])
def test_unsafe_or_unproven_receipt_never_becomes_successful_count(fault):
    artifacts, rows, task = fixture()
    if fault == "unknown":
        rows["receipts"][0]["unknown"] = True
    elif fault == "http_error":
        rows["receipts"][0]["status"] = 500
    elif fault == "missing_action":
        rows["actions"] = []
    else:
        rows["actions"][0]["plan_id"] = "other"
    result = runner.diagnose_counts("plan", [task], rows, artifacts.__getitem__)[0]
    assert result["changed_key_collision"]
    assert not result["successful_exact_count_available"]


def test_task_hash_drift_fails_closed():
    artifacts, rows, task = fixture()
    artifacts[task["request_body_ref"]] += b" "
    with pytest.raises(AuditError, match="body_hash_mismatch"):
        runner.diagnose_counts("plan", [task], rows, artifacts.__getitem__)


class SeededCapacityResearch(runner.CapacityResearch):
    @audited_handler
    def _status(self, session, context, data):
        if not data.get("seed"):
            return super()._status(session, context, data)
        protocol = self._version(session, context, {"kind": "protocol", "key": "capacity-test",
            "content": {"method": "synthetic-capacity-fixture", "rules": "Synthetic only; no network/model calls"}})["id"]
        plan = {"authorization_id": runner.STUDY, "contract_sha256": runner.contract_digest(),
                "versions": {"protocol": protocol}, "corpora": {"incident-reports": {"summary": {"eligible_requests": 5}}}}
        plan_id = self.ledger.record(session, "luna_budget_execution_plan", "synthetic", plan)
        artifacts, rows, task = fixture()
        for ref, raw in artifacts.items():
            assert self.ledger.artifacts.put_bytes(raw) == ref
        task.pop("manifest")
        self.ledger.record(session, runner.KINDS["manifests"], "manifest", {"plan": plan_id,
            "corpus_id": "incident-reports", "tasks": [task], "attempt_ids": ["synthetic-never-dispatched"]})
        for name in ("actions", "identities", "receipts"):
            for row in deepcopy(rows[name]):
                row.pop("id")
                if "plan_id" in row:
                    row["plan_id"] = plan_id
                self.ledger.record(session, runner.KINDS[name], row["action_id"], row)
        price = PricePolicy("gpt-6-luna", 100000000, 125000000, 500000000,
            (1, 2), (1, 1), (2, 1), (3, 2), 272000, "https://example.test/synthetic", "2026-01-01T00:00:00Z")
        book = BudgetBook(price, runner.STUDY, operational_limit_nanousd=120_000_000_000)
        EventBatchLiveGateway(self, self.gateway.provider).save_book(session, book)
        return {"plan": plan_id}


def test_real_audited_store_diagnostic_runs_without_dispatch(tmp_path, monkeypatch):
    owner = tmp_path / "capacity-synthetic-owner"
    monkeypatch.setattr(runner, "OWNER", owner)
    engine = SeededCapacityResearch(owner, config=Config(offline=True))
    try:
        seeded = engine.execute("status", {"seed": True}, objective="Seed synthetic count records", actor="test:software")
        result = engine.execute("status", seeded, objective="Diagnose synthetic collision", actor="test:software")
        assert result["count_summary"] == {"changed_key_collision": 1}
        assert result["staging"]["incident-reports"]["never_reserved_staged"] == 1
        assert result["count_diagnostics"][0]["unresolved_paid_intent"] is False
        assert result["successful_count_candidates"] == 1
        assert result["charged_estimate_usd"] == result["reserved_usd"] == 0
        assert result["new_provider_calls"] == result["new_models"] == 0
        assert "synthetic input" not in canonical(result)
        assert engine.ledger.artifacts.read_bytes(result["presentation"]).decode() == result["markdown"]
    finally:
        engine.close()
