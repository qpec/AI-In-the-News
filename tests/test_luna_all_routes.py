"""Three simultaneous audited routes with disjoint articles and one budget."""
import json
import sqlite3
import threading
import time


import test_luna_batch_parallel as fixture
from test_luna_standard_api import Transport
import luna_all_routes as module
import check_luna_batch_remainder as checker
from newsresearch.common import Config


class Clock:
    def __init__(self):
        self.value = 30.

    def __call__(self):
        self.value += .05
        return self.value


class Codex(module.StandardProvider):
    synthetic = True

    def __init__(self, *args, fail=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.seen, self.active, self.peak, self.fail = set(), 0, 0, fail
        self.mutex = threading.Lock()

    def complete_prepared(self, invocation):
        self._check_auth_environment()
        self._validate_prepared(invocation)
        with self.mutex:
            assert invocation.request["attempt"] not in self.seen
            self.seen.add(invocation.request["attempt"])
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(.1)
        with self.mutex:
            self.active -= 1
        if self.fail:
            return module.ProviderResponse(None, "codex-cli", None, raw_response={
                "unknown_outcome": True, "failure": "synthetic_transport_failure"})
        return module.ProviderResponse({}, "codex-cli", "gpt-6-luna", usage={"input_tokens": 100, "output_tokens": 20},
            raw_response={"unknown_outcome": False, "transport_status": "returned", "failure": None,
                "events": [{"type": "turn.completed"}], "configured_service_tier": "standard", "fast_mode": False})


def setup(tmp_path, monkeypatch, fail=False):
    monkeypatch.setattr(module.parent, "QUEUE_TOKENS", 800)
    monkeypatch.setattr(module.batch, "QUEUE_TOKENS", 800)
    monkeypatch.setattr(module.batch, "MAX_REQUESTS", 8)
    monkeypatch.setattr(module, "ROUTE_SIZES", {"codex": 5, "standard": 5, "batch": 5})
    plan, prior = fixture.prepare(tmp_path, monkeypatch, record_count=31)
    # Migration of a real WAL checkpoint with one accepted Batch job.
    fake = Transport()
    engine = module.parallel.PackingResearch(tmp_path / "parallel", transport=fake, clock=lambda: 21)
    try:
        fixture.fixture.execute(engine, {"phase": "run", "plan": plan["id"],
            "amendment": prior["id"], "test_stop_after_submissions": 1})
    finally:
        engine.close()
    monkeypatch.setattr(module.batch, "MAX_REQUESTS", 1000)
    (tmp_path / "parallel/STOP").write_text("Synthetic three-route handoff")
    integrity = checker.BatchIntegrity(tmp_path / "parent-check")
    try:
        fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "parallel"), "plan": plan["id"]})
    finally:
        integrity.close()
    executable = tmp_path / "fake-codex.exe"
    executable.write_bytes(b"Synthetic binary; never executed")
    migration = module.CombinedMigration(tmp_path / "combined-migration")
    try:
        fixture.fixture.execute(migration, {"source_owner": str(tmp_path / "parallel"), "destination": str(tmp_path / "combined"),
            "integrity_report": str(tmp_path / "parent-check/latest-integrity.json"), "plan": plan["id"],
            "authorization_text": module.AUTHORIZATION, "codex_executable": str(executable)})
    finally:
        migration.close()
    amendment = json.loads((tmp_path / "combined/all-routes-plan.json").read_text())
    provider = Codex(tmp_path / "combined/workers", executable=str(executable), fail=fail,
        max_input_bytes=1_000_000, max_output_bytes=262144)
    fake.terminal = True
    return plan, amendment, fake, provider


def test_all_routes_share_identity_budget_and_collect_without_retries(tmp_path, monkeypatch):
    plan, amendment, fake, provider = setup(tmp_path, monkeypatch)
    engine = module.CombinedResearch(tmp_path / "combined", transport=fake, codex_provider=provider, clock=Clock(), config=Config(offline=True))
    run = {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]}
    try:
        result = fixture.fixture.execute(engine, run)
        assert result["reason"] == "queue_exhausted" and result["new_returned"] == plan["count_cap"] == 30
        assert result["codex_saved"] > 0 and result["standard_saved"] > 0 and len(fake.jobs) > 1
        assert 1 < provider.peak <= 5
        before = len(provider.seen), len(fake.standard_ids), len(fake.jobs)
        repeated = fixture.fixture.execute(engine, run)
        assert repeated["new_returned"] == 30
        assert before == (len(provider.seen), len(fake.standard_ids), len(fake.jobs))
        assert result["reserved_nanousd"] == 1402432 and result["unknown_cost_holds"] == 1
    finally:
        engine.close()
    with sqlite3.connect(tmp_path / "combined/state.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM requests WHERE submitted=1 AND custom_id IN (SELECT custom_id FROM codex_attempts)").fetchone()[0] == result["codex_saved"]
        assert db.execute("SELECT COUNT(*) FROM codex_attempts c JOIN standard_attempts s USING(custom_id)").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM codex_attempts c JOIN budget_entries b USING(custom_id)").fetchone()[0] == 0
    integrity = checker.BatchIntegrity(tmp_path / "combined-check")
    try:
        checked = fixture.fixture.execute(integrity, {"source_owner": str(tmp_path / "combined"), "plan": plan["id"]})
        assert checked["integrity_passed"] and checked["new_results_replayed"] == 30
        assert checked["created_article_intents"] == 30 and checked["operational_state_matches_latest_checkpoint"]
    finally:
        integrity.close()


def test_codex_unknowns_preserved_while_api_routes_finish_their_claims(tmp_path, monkeypatch):
    plan, amendment, fake, provider = setup(tmp_path, monkeypatch, fail=True)
    engine = module.CombinedResearch(tmp_path / "combined", transport=fake, codex_provider=provider, clock=Clock())
    try:
        result = fixture.fixture.execute(engine, {"phase": "run", "plan": plan["id"], "amendment": amendment["id"]})
        assert result["codex_saved_unknowns"] > 0 and result["codex_control"]["paused"]
        assert result["standard_saved"] > 0 and result["pending_jobs"] == 0
        assert result["unknown_cost_holds"] == 1
        assert len(engine.ledger.unresolved) == result["codex_saved_unknowns"]
    finally:
        engine.close()


def test_private_key_transport_does_not_export_key_to_codex_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    observations = []
    class Response:
        status = 200
        headers = {}
        def read(self, limit):
            return b'{"model":"gpt-6-luna","input_tokens":1}'
        def close(self):
            pass
    class Opener:
        def open(self, request, timeout):
            module.StandardProvider._check_auth_environment()
            observations.append(request.get_header("Authorization") == "Bearer synthetic-test-value")
            return Response()
    transport = module.PrivateKeyTransport("synthetic-test-value", opener=Opener())
    source = fixture.fixture.fixture.record(123, "cybercrime")["request"]["body"]
    receipt = transport.perform(module.batch.COUNT_ROUTE, module.canonical(module.http.count_request_body(source)).encode(), "f" * 64)
    assert receipt.status == 200 and observations == [True]
    module.StandardProvider._check_auth_environment()
