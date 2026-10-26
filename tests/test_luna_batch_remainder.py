"""Synthetic Research handoff, HTTP, preserved money and restart boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import luna_batch_remainder as module
import test_lean_luna_batch as fixture
from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root


class SeedResearch(Research):
    @audited_handler
    def _status(self, session, context, data):
        if data["kind"] == "source":
            queues = {corpus: self.ledger.artifacts.put(rows) for corpus, rows in data["queues"].items()}
            plan = self.ledger.record(session, "luna_standard_plan", "fictional", {
                "queues": queues, "max_attempts": sum(map(len, data["queues"].values())), "capacity_lineage": []})
            for custom in data["spent"]:
                self.ledger.append(session, "model.attempt.intended", {"plan": plan, "custom_id": custom})
            return {"plan": plan}
        return {"id": self.ledger.record(session, "lean_luna_checkpoint", data["key"], data["checkpoint"])}


def seed(tmp_path):
    parent = fixture.fixture(tmp_path, [])
    database = parent.database
    meta = deepcopy(parent.meta)
    meta["budget"]["frozen"] = False
    meta["corpora"] = {k: {"partition": {}} for k in ("cybercrime", "incident-reports")}
    with parent.db:
        for key in ("budget", "corpora"):
            parent.db.execute("UPDATE meta SET value=? WHERE key=?", (module.canonical(meta[key]), key))
    checkpoint = {"state_sha256": module.state_hash(parent.db), "baseline": "prior-baseline", "totals": parent.totals(), "summary": parent.summary()}
    parent.close()
    protected_database = prepare_root(tmp_path / "protected-lean") / "state.sqlite3"
    protected_database.write_bytes(database.read_bytes())
    database = protected_database
    runtime = SeedResearch(database.parent / "runtime")
    try:
        runtime.execute("status", {"kind": "checkpoint", "key": meta["snapshot_id"], "checkpoint": checkpoint}, objective="Seed a synthetic checkpoint", actor="test:remainder")
    finally:
        runtime.close()
    records = [fixture.record(901, "cybercrime"), fixture.record(902, "incident-reports"), fixture.record(903, "incident-reports")]
    spent = records[-1]["descriptor"]["custom_id"]
    source_owner = tmp_path / "codex"
    source = SeedResearch(source_owner)
    try:
        result = source.execute("status", {"kind": "source", "queues": {
            "cybercrime": [records[0]["descriptor"]], "incident-reports": [r["descriptor"] for r in records[1:]]}, "spent": [spent]},
            objective="Seed a fictional drained Codex queue", actor="test:remainder")
        head = list(source.ledger.db.execute("SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1").fetchone())
    finally:
        source.close()
    (source_owner / "STOP").write_text("Synthetic user stop")
    (source_owner / "progress.json").write_text(json.dumps({"state": "user_stop", "in_flight": 0, "reserved": 1}))
    integrity = tmp_path / "integrity.json"
    integrity.write_text(json.dumps({"integrity_passed": True, "plan": result["plan"], "head_seq": head[0], "head_hash": head[1], "checked_at": "1970-01-01T00:00:10+00:00"}))
    data = {"phase": "prepare", "codex_owner": str(source_owner), "codex_plan": result["plan"], "parent_state": str(database),
        "integrity_report": str(integrity), "authorization_text": module.AUTHORIZATION}
    return data, records


class Transport(fixture.FakeTransport):
    def __init__(self):
        super().__init__()
        self.files, self.jobs = {}, {}
        self.terminal = False

    def perform(self, request, body, identifier):
        if request == module.batch.COUNT_ROUTE:
            return super().perform(request, body, identifier)
        self.calls.append(request)
        if request["path"] == "/v1/files":
            ref = "file-" + hashlib.sha256(body).hexdigest()
            self.files[ref] = body
            answer = {"id": ref, "purpose": "batch", "bytes": len(body)}
        elif request["path"] == "/v1/batches":
            if self.create_unknown:
                return module.lean.BatchReceipt(None, None, error_type="TimeoutError", unknown=True)
            value = json.loads(body)
            ref = "batch_" + value["input_file_id"][5:]
            answer = {"id": ref, **value, "status": "in_progress"}
            self.jobs[ref] = answer
        elif request["path"].startswith("/v1/batches/"):
            answer = {**self.jobs[request["path"].split("/")[-1]]}
            if self.terminal:
                answer.update(status="completed", output_file_id="file-output-" + answer["id"], error_file_id=None)
        elif request["path"].startswith("/v1/files/file-output-"):
            ref = request["path"].split("/")[-2].removeprefix("file-output-")
            rows = []
            for raw in self.files[self.jobs[ref]["input_file_id"]].splitlines():
                custom = json.loads(raw)["custom_id"]
                # A known content-invalid output still has complete settled usage.
                rows.append({"custom_id": custom, "error": None, "response": {"status_code": 200, "body": {
                    "id": "response-test", "model": "gpt-6-luna", "status": "completed", "error": None,
                    "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
                    "output": [{"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "output_text", "text": "{}"}]}]}}})
            return module.lean.BatchReceipt("".join(module.canonical(r) + "\n" for r in rows).encode(), 200)
        else:
            raise AssertionError(request)
        return module.lean.BatchReceipt(module.canonical(answer).encode(), 200)


def execute(engine, data):
    return engine.execute("status", data, objective="Test the synthetic same-budget remainder handoff", actor="test:remainder")


def setup(tmp_path, monkeypatch):
    data, records = seed(tmp_path)
    fake = Transport()
    engine = module.RemainderResearch(tmp_path / "remainder", transport=fake, clock=lambda: 20, config=Config(offline=True))
    result = execute(engine, data)
    by_id = {r["descriptor"]["custom_id"]: r for r in records}
    monkeypatch.setattr(module.RemainderBatch, "materialize", lambda self, rows, partition: [by_id[d["custom_id"]] for d in rows])
    return engine, fake, result, data


def test_handoff_parallel_jobs_restart_collection_preserve_spend_and_original_deadline(tmp_path, monkeypatch):
    engine, fake, plan, data = setup(tmp_path, monkeypatch)
    original = Path(data["parent_state"]).read_bytes()
    try:
        assert plan["count_cap"] == 2 and plan["prior_codex_spent"] == 1 and plan["original_deadline_epoch"] == 1000
        assert plan["deadline_epoch"] == 20 + 86400 and plan["http_calls"] == 0
        first = execute(engine, {"phase": "run", "plan": plan["id"], "test_stop_after_submissions": 2})
        assert first["pending_jobs"] == 2 and first["new_submitted"] == 2 and first["new_returned"] == 0
        assert set(first["corpora"]) == {"cybercrime", "incident-reports"}
        posts = sum(r["method"] == "POST" for r in fake.calls)
        fake.terminal = True
        second = execute(engine, {"phase": "run", "plan": plan["id"]})
        assert second["reason"] == "queue_exhausted" and second["new_returned"] == 2 and second["pending_jobs"] == 0
        assert second["reserved_nanousd"] == 1402432 and second["charged_nanousd"] > 0
        assert sum(r["method"] == "POST" for r in fake.calls) == posts
        assert Path(data["parent_state"]).read_bytes() == original
        assert (Path(data["codex_owner"]) / "STOP").exists()
    finally:
        engine.close()


@pytest.mark.parametrize("failure", ["unknown_create", "state_mutation", "codex_resumed", "stop"])
def test_resume_never_spends_again_after_ambiguous_write_or_tampering(tmp_path, monkeypatch, failure):
    engine, fake, plan, data = setup(tmp_path, monkeypatch)
    try:
        if failure == "unknown_create":
            fake.create_unknown = True
            first = execute(engine, {"phase": "run", "plan": plan["id"], "test_stop_after_submissions": 1})
            assert first["new_submitted"] == 1 and first["reserved_nanousd"] > 1402432
        elif failure == "state_mutation":
            with sqlite3.connect(engine.ledger.root / "state.sqlite3") as db:
                db.execute("UPDATE budget_entries SET reserved_nanousd=0")
        elif failure == "codex_resumed":
            (Path(data["codex_owner"]) / "STOP").unlink()
        else:
            (engine.ledger.root / "STOP").write_text("Synthetic stop")
        before = len(fake.calls)
        with pytest.raises((AuditError, module.state.StateError)):
            execute(engine, {"phase": "run", "plan": plan["id"]})
        assert len(fake.calls) == before
    finally:
        engine.close()


def test_expired_renewal_collects_without_new_submission(tmp_path, monkeypatch):
    engine, fake, plan, _ = setup(tmp_path, monkeypatch)
    try:
        execute(engine, {"phase": "run", "plan": plan["id"], "test_stop_after_submissions": 1})
        fake.terminal = True
        engine.clock = lambda: plan["deadline_epoch"] + 1
        posts = sum(r["method"] == "POST" for r in fake.calls)
        result = execute(engine, {"phase": "run", "plan": plan["id"]})
        assert result["reason"] == "deadline" and result["new_returned"] == 1 and result["new_submitted"] == 1
        assert sum(r["method"] == "POST" for r in fake.calls) == posts
    finally:
        engine.close()
