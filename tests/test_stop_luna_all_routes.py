"""Synthetic shutdown checks; no provider calls or production storage."""
import json
import hashlib
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.event_batch_transport import BatchReceipt
from newsresearch.runtime import Research, audited_handler
sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from stop_luna_all_routes import StopGateway, StopTransport, route  # noqa: E402
import stop_luna_all_routes as module  # noqa: E402
from newsresearch.storage import prepare_root


def test_fixed_routes_only():
    assert route("batch_abc") == {"method": "GET", "path": "/v1/batches/batch_abc"}
    assert route("batch_abc", True)["path"].endswith("/cancel")
    with pytest.raises(AuditError):
        route("batch_abc/../../responses")
    with pytest.raises(AuditError):
        StopTransport().perform({"method": "POST", "path": "/v1/batches"}, None, "test")


@pytest.mark.parametrize("unknown", [False, True])
def test_durable_cancel_no_retries_even_after_unknown(tmp_path, unknown):
    class TestResearch(Research):
        @audited_handler
        def _status(self, session, context, data):
            return self.gateway.exchange(session, "synthetic", {"job_id": "batch_abc", "corpus": "synthetic"}, cancel=True)

    class Transport:
        calls = 0

        def perform(self, request, body, request_id):
            self.calls += 1
            assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_stop_cancel_intent'").fetchone()[0] == 1
            if unknown:
                return BatchReceipt(None, None, unknown=True, error_type="timeout")
            return BatchReceipt(json.dumps({"id": "batch_abc", "endpoint": "/v1/responses", "status": "cancelling"}).encode(), 200)

    engine = TestResearch(tmp_path / "private", config=Config(offline=True))
    transport = Transport()
    engine.gateway = StopGateway(engine, transport)
    try:
        result = engine.execute("status", {}, objective="Synthetic cancellation test", actor="test")
        assert result["observed_status"] == ("unconfirmed" if unknown else "cancelling")
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_stop_http_receipt'").fetchone()[0] == 1
        with pytest.raises(AuditError, match="already_intended"):
            engine.execute("status", {}, objective="Prove duplicate cancellation blocked", actor="test")
        assert transport.calls == 1
        engine.ledger.verify()
    finally:
        engine.close()


def test_complete_admin_flow_preserves_source(tmp_path, monkeypatch):
    owner = prepare_root(tmp_path / "source")
    (owner / "STOP").write_text("User stop", encoding="utf-8")
    (owner / "plan.json").write_text(json.dumps({"id": module.PLAN}), encoding="utf-8")
    db = sqlite3.connect(owner / "state.sqlite3")
    db.execute("CREATE TABLE jobs(job_id TEXT, reconciled INTEGER, payload TEXT)")
    for suffix in ("active", "done"):
        job_id = "batch_" + suffix
        db.execute("INSERT INTO jobs VALUES(?,0,?)", (job_id, json.dumps({"job_id": job_id, "corpus_id": "synthetic", "request_ids": [suffix]})))
    db.commit()
    db.close()
    before = (owner / "state.sqlite3").read_bytes()
    monkeypatch.setattr(module, "OWNER", owner)

    class Transport:
        calls = []

        def perform(self, request, body, request_id):
            self.calls.append(request)
            job_id = request["path"].split("/")[3]
            status = "completed" if job_id.endswith("done") else ("cancelling" if request["method"] == "POST" else "in_progress")
            return BatchReceipt(json.dumps({"id": job_id, "endpoint": "/v1/responses", "status": status}).encode(), 200)

    engine = module.StopResearch(tmp_path / "audit", config=Config(offline=True))
    transport = Transport()
    engine.gateway = StopGateway(engine, transport)
    try:
        protocol = engine.execute("version", {"kind": "protocol", "key": module.METHOD,
            "content": {"method": module.METHOD, "implementation_sha256": hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(), "user_instruction": "Stop all"}},
            objective="Register synthetic administrative shutdown", actor="test")["id"]
        result = engine.execute("status", {"action": "stop"}, objective="Test shutdown", actor="test", versions={"protocol": protocol})
        assert result["states"] == {"cancelling": 1, "completed": 1}
        assert len(transport.calls) == 3
        assert (owner / "state.sqlite3").read_bytes() == before
        engine.ledger.verify()
    finally:
        engine.close()
