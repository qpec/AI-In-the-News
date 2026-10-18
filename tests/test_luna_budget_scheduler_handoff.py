"""Synthetic suspend/finally/RO-snapshot tests; never controls a real process."""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
from typing import Any

import pytest

from newsresearch.common import AuditError, Config, Context, Json, canonical, digest
from newsresearch.runtime import audited_handler

import test_luna_budget_truncation_policy as policy_fixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_budget_scheduler_handoff as module
finally:
    sys.path.pop(0)


def source_fixture(path: Path, *, mode: str = "clear") -> tuple[str, str]:
    path.mkdir()
    connection = sqlite3.connect(path / "research.sqlite3")
    connection.executescript("CREATE TABLE records(id TEXT,kind TEXT,logical_key TEXT,payload TEXT,artifact TEXT,supersedes TEXT,created_event INTEGER); CREATE TABLE events(seq INTEGER,event_hash TEXT);")
    seq = 0
    def record(kind: str, key: str, value: Json) -> str:
        nonlocal seq
        seq += 1
        artifact = digest(value)
        reference = digest({"kind": kind, "key": key, "payload": artifact, "supersedes": None})
        connection.execute("INSERT INTO records VALUES(?,?,?,?,?,?,?)", (reference, kind, key, canonical(value), artifact, None, seq))
        return reference
    policy_ref = record(module.policy.POLICY_KIND, "policy", {"plan": "plan"})
    record(module.predecessor.RUN_KIND, "plan:" + policy_ref + ":throughput-v1", {"plan": "plan", "policy_ref": policy_ref,
        "authorization_id": module.STUDY, "implementation": module.predecessor.implementation_hashes(), "protocol": "protocol", "deadline_epoch": 100})
    record(module.BUDGET_KIND, module.STUDY, {"state_ref": "held-book", "committed_nanousd": 1402432,
        "charged_nanousd": 0, "reserved_nanousd": 1402432, "frozen": False, "price_fingerprint": "price"})
    action = {"authorization_id": module.STUDY, "plan_id": "plan", "action_id": "action", "phase": "create" if mode == "unbound_create" else "count"}
    record(module.ACTION_IDENTITY_KIND, "identity", {"authorization_id": module.STUDY, "action_id": "orphan" if mode == "orphan" else "action"})
    record(module.ACTION_KIND, "action", action)
    if mode != "missing":
        receipt = {"authorization_id": module.STUDY, "action_id": "action", "unknown": mode == "unknown",
            "body_ref": "retained-body", "status": 429 if mode == "http_error" else 200}
        record(module.RECEIPT_KIND, "action", receipt)
        if mode == "duplicate":
            record(module.RECEIPT_KIND, "action", {**receipt, "observed": "different"})
    if mode == "gateway_stop":
        record(module.STOP_KIND, module.STUDY, {"reason": "retained-stop"})
    connection.execute("INSERT INTO events VALUES(?,?)", (seq, "head-hash"))
    connection.commit()
    connection.close()
    return "plan", policy_ref


class FakeWorker:
    synthetic = True
    calls: list[str] = []
    mode = "clear"

    def __init__(self, data: Json) -> None:
        self.data = data

    def identity(self) -> Json:
        self.calls.append("identity")
        if self.mode == "reused_pid":
            raise AuditError("synthetic PID creation mismatch")
        return {"worker_pid": 17, "worker_created_100ns": 99, "parent_pid": 3}

    def suspend(self) -> None:
        self.calls.append("suspend")

    def resume(self) -> None:
        self.calls.append("resume")

    def terminate(self) -> None:
        self.calls.append("terminate")
        if self.mode == "terminate_error":
            raise AuditError("synthetic terminate failure")

    def close(self) -> None:
        self.calls.append("close")


def inspector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str = "clear") -> tuple[Any, Json]:
    plan, policy_ref = source_fixture(tmp_path / "source", mode=mode)
    engine = module.HandoffResearch(tmp_path / "metadata", project=tmp_path, config=Config(offline=True))
    FakeWorker.calls, FakeWorker.mode = [], "clear"
    monkeypatch.setattr(engine, "process_factory", FakeWorker)
    return engine, {"production_workspace": str(tmp_path / "source"), "plan": plan, "policy_ref": policy_ref,
        "allow_process_handoff": True, "stop_when_quiescent": True}


@pytest.mark.parametrize("mode", ["clear", "missing", "unknown", "http_error", "duplicate", "orphan", "unbound_create", "gateway_stop"])
def test_stop_only_quiescent_snapshot_otherwise_resume_exact_worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    engine, data = inspector(tmp_path, monkeypatch, mode)
    database = tmp_path / "source/research.sqlite3"
    before = database.read_bytes()
    try:
        result = engine.execute("status", data, objective="Test fictional frozen-worker metadata only", actor="test:software")
        stopped = mode == "clear"
        assert result["worker_terminated"] is stopped and result["worker_resumed"] is not stopped
        assert ("terminate" in FakeWorker.calls) is stopped and ("resume" in FakeWorker.calls) is not stopped
        assert FakeWorker.calls[-1] == "close" and result["old_finish_fabricated"] is False
        assert result["budget_metadata"]["reserved_nanousd"] == 1402432
        assert database.read_bytes() == before and not result["article_text_read"]
    finally:
        engine.close()


@pytest.mark.parametrize("failure", ["reused_pid", "corrupt_snapshot", "audit_after_suspend", "terminate_error"])
def test_failures_resume_without_termination_or_handoff_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    engine, data = inspector(tmp_path, monkeypatch)
    if failure in {"reused_pid", "terminate_error"}:
        FakeWorker.mode = failure
    elif failure == "audit_after_suspend":
        engine.ledger.fail_event = "scheduler.operational_snapshot.intended"
    else:
        connection = sqlite3.connect(tmp_path / "source/research.sqlite3")
        connection.execute("UPDATE records SET payload='{}' WHERE kind=?", (module.ACTION_KIND,))
        connection.commit()
        connection.close()
    try:
        with pytest.raises(AuditError):
            engine.execute("status", data, objective="Test failure-safe synthetic interruption", actor="test:software")
        assert ("resume" in FakeWorker.calls) is (failure != "reused_pid")
        assert FakeWorker.calls[-1] == "close"
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.HANDOFF_KIND,)).fetchone()[0] == 0
    finally:
        engine.close()


def test_no_stop_permission_resumes_after_clear_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, data = inspector(tmp_path, monkeypatch)
    try:
        result = engine.execute("status", {**data, "stop_when_quiescent": False}, objective="Inspect without terminating fictional worker", actor="test:software")
        assert result["quiescent"] and result["worker_resumed"] and "terminate" not in FakeWorker.calls
    finally:
        engine.close()


def test_snapshot_is_one_read_transaction_and_never_writable(tmp_path: Path) -> None:
    plan, policy_ref = source_fixture(tmp_path / "source")
    connection = sqlite3.connect((tmp_path / "source/research.sqlite3").as_uri() + "?mode=ro", uri=True, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        assert module.snapshot(connection, plan, policy_ref)["quiescent"]
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM records")
        connection.execute("ROLLBACK")
    finally:
        connection.close()


class CacheHarness(policy_fixture.PolicyHarness):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        result = super()._status(session, context, data)
        value = self.ledger.get(result["policy_ref"], module.policy.POLICY_KIND)
        self.ledger.record(session, module.predecessor.RUN_KIND,
            data["plan"] + ":" + result["policy_ref"] + ":throughput-v1", {
                "plan": data["plan"], "policy_ref": result["policy_ref"], "authorization_id": module.STUDY,
                "implementation": module.predecessor.implementation_hashes(), "baseline_ack_ref": value["baseline_ack_ref"],
                "protocol": value["protocol"], "deadline_epoch": value["deadline_epoch"]})
        before = self.historical_replays
        original = self.saved_verified
        verified = module.load_registered_policy_cache(self, session, data["plan"], result["policy_ref"])
        assert verified is not original and verified.value == original.value
        assert self.historical_replays == before
        book, _ = self.gateway.load_book(session, module.STUDY)
        assert module.policy.classify_failures(self, session, verified, self.view(session, data["plan"])["assessments"], book)["unqualified_failures"] == []
        return result


def prepared_cache_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Json, Any, Json, Json]:
    owner, plan, transport, initial, baseline = policy_fixture.prepared_policy_owner(tmp_path, monkeypatch)
    engine = CacheHarness(owner, config=Config(offline=False), transport=transport)
    engine.synthetic_history, engine.raw_proof_reads = initial["history"], []
    ack = baseline["ack"]
    arguments = {key: ack[key] for key in ("plan", "prior_ack_ref", "stop_result_ref", "diagnostic_ref")}
    arguments["assessment_ids"] = ack["new_assessment_ids"]
    result = engine.execute("status", arguments, objective="Test real retained baseline proof cache without recursive replay", actor="test:software")
    return engine, plan, transport, initial, result


def test_real_registered_cache_creates_fresh_seal_without_replaying_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine, _, _, _, result = prepared_cache_owner(tmp_path, monkeypatch)
    try:
        assert result["policy_ref"] and result["held"]["reserved_nanousd"] == 1_402_432
    finally:
        engine.close()
