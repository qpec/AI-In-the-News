"""Synthetic, audited Standard continuation: no paid/network calls."""
import json
import sqlite3

import pytest

import test_luna_batch_parallel as fixture
import luna_standard_api as module
import check_luna_batch_remainder as checker
from newsresearch.common import AuditError, Config


class Clock:
    def __init__(self):
        self.value = 30.0

    def __call__(self):
        return self.value


class Transport(fixture.fixture.Transport):
    def __init__(self, failure=None):
        super().__init__()
        self.failure = failure
        self.standard_ids = []

    def perform(self, request, body, identifier):
        if request != module.ROUTE:
            return super().perform(request, body, identifier)
        self.calls.append(request)
        assert identifier not in self.standard_ids
        self.standard_ids.append(identifier)
        assert json.loads(module.prepare_standard(body, identifier).body)["service_tier"] == "default"
        headers = {"x-ratelimit-limit-tokens": "1000000", "x-ratelimit-limit-requests": "4000"}
        if self.failure == "malformed":
            return module.http.BatchReceipt(b'{"duplicate":1,"duplicate":2}', 200, headers=headers)
        if self.failure == "429":
            return module.http.BatchReceipt(b'{"error":{"type":"rate_limit_exceeded"}}', 429, headers=headers, error_type="http_error")
        value = {"id": "response-test", "model": "gpt-6-luna", "status": "completed", "error": None,
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "output": [{"type": "message", "role": "assistant", "status": "completed",
                "content": [{"type": "output_text", "text": "{}"}]}]}
        return module.http.BatchReceipt(module.canonical(value).encode(), 200, headers=headers)


def setup(tmp_path, monkeypatch, failure=None):
    monkeypatch.setattr(module.parent, "QUEUE_TOKENS", 250)
    monkeypatch.setattr(module.batch, "QUEUE_TOKENS", 250)
    plan, prior = fixture.prepare(tmp_path, monkeypatch)
    fake = Transport(failure)
    engine = module.parallel.PackingResearch(tmp_path / "parallel", transport=fake, clock=lambda: 21)
    try:
        before = fixture.fixture.execute(engine, {"phase": "run", "plan": plan["id"],
            "amendment": prior["id"], "test_stop_after_submissions": 1})
        assert before["new_submitted"] == 2 and before["new_returned"] == 0
    finally:
        engine.close()
    (tmp_path / "parallel" / "STOP").write_text("Synthetic Standard route handoff")
    integrity = checker.BatchIntegrity(tmp_path / "parallel-check")
    try:
        fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "parallel"), "plan": plan["id"]})
    finally:
        integrity.close()
    migrate = module.StandardMigration(tmp_path / "standard-migration")
    try:
        fixture.fixture.execute(migrate, {"source_owner": str(tmp_path / "parallel"), "destination": str(tmp_path / "standard"),
            "plan": plan["id"], "integrity_report": str(tmp_path / "parallel-check/latest-integrity.json"),
            "authorization_text": module.AUTHORIZATION})
    finally:
        migrate.close()
    amendment = json.loads((tmp_path / "standard/standard-api-plan.json").read_text())
    return plan, amendment, fake


def test_standard_once_sealed_wal_migration_batch_collection_and_restart(tmp_path, monkeypatch):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    original = (tmp_path / "parallel/state.sqlite3").read_bytes()
    fake.terminal = True
    clock = Clock()
    engine = module.StandardResearch(tmp_path / "standard", transport=fake, clock=clock, config=Config(offline=True))
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"], "test_stop_after": 1}
    try:
        first = fixture.fixture.execute(engine, run)
        assert first["standard_submitted"] == first["standard_saved"] == 1
        assert first["new_returned"] == 3 and first["pending_jobs"] == 0
        assert first["standard_control"]["tpm"] == 1000000
        assert first["standard_control"]["rpm"] == 4000
        assert first["reserved_nanousd"] == 1402432
        count_calls = fake.calls.count(module.batch.COUNT_ROUTE)
        clock.value = 95
        second = fixture.fixture.execute(engine, run)
        assert second["new_returned"] == 4 and second["standard_saved"] == 2
        third = fixture.fixture.execute(engine, {**run, "test_stop_after": None})
        assert third["reason"] == "queue_exhausted" and third["new_returned"] == 4
        assert len(fake.standard_ids) == 2 and len(fake.jobs) == 1
        assert fake.calls.count(module.batch.COUNT_ROUTE) == count_calls == 4
        assert original == (tmp_path / "parallel/state.sqlite3").read_bytes()
        assert amendment["deadline_epoch"] == plan["deadline_epoch"]
        assert (tmp_path / "parallel/STOP").exists()
        with sqlite3.connect(tmp_path / "standard/state.sqlite3") as db:
            costs = [json.loads(r[0]) for r in db.execute("SELECT payload FROM budget_entries WHERE status='settled'")]
        standard = [c for c in costs if c.get("processing_route") == "standard_responses"]
        batch = [c for c in costs if c.get("processing_route") != "standard_responses" and c.get("settlement", {}).get("input_tokens") == 100]
        assert len(standard) == 2 and len(batch) == 2
        assert standard[0]["charged_nanousd"] == batch[0]["charged_nanousd"] * 2
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "standard-check")
    try:
        result = fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "standard"), "plan": plan["id"]})
        assert result["integrity_passed"] and result["new_results_replayed"] == 4
        assert result["created_article_intents"] == 4 and result["unresolved_including_inflight"] == 0
        assert result["operational_state_matches_latest_checkpoint"]
    finally:
        integrity.close()


@pytest.mark.parametrize("failure", ["429", "malformed"])
def test_failure_retained_once_cost_held_and_no_restart(tmp_path, monkeypatch, failure):
    plan, amendment, fake = setup(tmp_path, monkeypatch, failure)
    fake.terminal = True
    engine = module.StandardResearch(tmp_path / "standard", transport=fake, clock=lambda: 30)
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"], "test_stop_after": 1}
    try:
        result = fixture.fixture.execute(engine, run)
        assert result["standard_saved"] == 1 and result["unknown_cost_holds"] == 2
        assert result["reserved_nanousd"] > 1402432
        with pytest.raises((AuditError, module.state.StateError)):
            fixture.fixture.execute(engine, run)
        assert len(fake.standard_ids) == 1
    finally:
        engine.close()
    integrity = checker.BatchIntegrity(tmp_path / "failure-check")
    try:
        result = fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "standard"), "plan": plan["id"]})
        assert result["integrity_passed"] and result["created_article_intents"] == 3
    finally:
        integrity.close()


def test_persisted_rolling_reservations_and_single_article_limit(tmp_path, monkeypatch):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    clock = Clock()
    engine = module.StandardResearch(tmp_path / "standard", transport=fake, clock=clock)
    runner = module.StandardBatch(tmp_path / "standard/state.sqlite3", plan=plan, plan_id=plan["id"],
        amendment=amendment, engine=engine, transport=fake, clock=clock)
    try:
        runner.initialize_standard()
        runner.db.execute("INSERT INTO standard_attempts VALUES('fictional','fictional',29,1999000,'saved')")
        assert not runner.rate_ready(4196)
        clock.value = 90
        assert runner.rate_ready(4196)
        runner.update_control("next_admission", 120)
        assert not runner.rate_ready(4196)
        runner.update_control("tpm", 3000)
        assert not runner.rate_ready(4196) and runner.stop_reason == "single_request_exceeds_observed_tpm"
    finally:
        runner.close()
        engine.close()


@pytest.mark.parametrize("block", ["STOP", "deadline"])
def test_stop_and_deadline_forbid_new_standard_intents(tmp_path, monkeypatch, block):
    plan, amendment, fake = setup(tmp_path, monkeypatch)
    fake.terminal = True
    if block == "STOP":
        (tmp_path / "standard/STOP").write_text("User stop")
    engine = module.StandardResearch(tmp_path / "standard", transport=fake,
        clock=lambda: plan["deadline_epoch"] + 1 if block == "deadline" else 30)
    try:
        run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]}
        if block == "STOP":
            with pytest.raises(module.state.StateError, match="user_stop"):
                fixture.fixture.execute(engine, run)
        else:
            result = fixture.fixture.execute(engine, run)
            assert result["new_returned"] == 2 and result["standard_saved"] == 0
        assert not fake.standard_ids and len(fake.jobs) == 1
    finally:
        engine.close()
