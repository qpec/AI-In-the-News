"""Fill scheduling, exact migration/resume and projection reads on fictional data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from newsresearch.common import AuditError, Config, Context, Json, canonical, digest
from newsresearch.event_batch_budget import BudgetBook
from newsresearch.runtime import Research, audited_handler

import test_luna_budget_scheduler_handoff as fixture
import test_run_luna_budget_throughput as previous
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import run_luna_budget_fill as runner
finally:
    sys.path.pop(0)


class FictionalFill(runner.FillResearch):
    # Only old fixture canary/history projection and presentation are incomplete.
    # Migration, current budget, future provider receipts, scheduler and gate are real.
    current = previous.FixtureThroughput.current

    def report(self, session: str, plan_id: str, plan: Json, view: Json, book: BudgetBook,
               state: str, *, reason: str | None = None) -> Json:
        return {**previous.FixtureThroughput.report(self, session, plan_id, plan, view, book, state, reason=reason),
            "migration_ref": self.migration_ref}


def prepared_handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Json, Any, Json, Json]:
    seed, plan, transport, initial, policy = fixture.prepared_cache_owner(tmp_path, monkeypatch)
    owner = seed.ledger.root
    seed.close()
    inspector = runner.handoff.HandoffResearch(tmp_path / "metadata", project=tmp_path, config=Config(offline=True))
    fixture.FakeWorker.calls, fixture.FakeWorker.mode = [], "clear"
    monkeypatch.setattr(inspector, "process_factory", fixture.FakeWorker)
    try:
        handoff = inspector.execute("status", {"plan": plan["id"], "policy_ref": policy["policy_ref"],
            "production_workspace": str(owner), "allow_process_handoff": True, "stop_when_quiescent": True},
            objective="Confirm fictional safe predecessor handoff", actor="test:software")
    finally:
        inspector.close()
    assert handoff["worker_terminated"] and handoff["quiescent"]
    return owner, plan, transport, initial, {"plan": plan["id"], "policy_ref": policy["policy_ref"],
        "handoff_workspace": str(tmp_path / "metadata"), "handoff_ref": handoff["id"], "allow_paid_execution": True}


@pytest.mark.parametrize("mode,reason", [("truncation", "complete"), ("unknown", "technical_stop"),
                                         ("deadline", "deadline")])
def test_actual_fill_controller_migration_resume_no_nested_preflight_or_historical_replay(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, reason: str) -> None:
    owner, plan, transport, initial, arguments = prepared_handoff(tmp_path, monkeypatch)
    transport.future_mode = mode
    monkeypatch.setattr(runner, "offline_tokenizer", previous.wave.fixture_module.SyntheticEncoder)
    def forbidden_history(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("registered proof must not recursively replay baseline")
    monkeypatch.setattr(runner.truncation.chain.held, "verify_history", forbidden_history)
    clock = [10_000_000_000.0 if mode == "deadline" else 0.0]
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: clock[0], perf_counter=lambda: clock[0],
        sleep=lambda delay: clock.__setitem__(0, clock[0] + delay)))
    engine = FictionalFill(owner, config=Config(offline=False), transport=transport)
    calls_before, jobs_before = len(transport.calls), len(transport.jobs)
    preflights = [0]
    verify = engine.ledger.verify
    def counted_verify() -> Json:
        preflights[0] += 1
        return verify()
    monkeypatch.setattr(engine.ledger, "verify", counted_verify)
    try:
        result = engine.execute("status", arguments, objective="Test fictional fill controller", actor="test:software")
        assert result["finished_reason"] == reason and preflights == [1]
        book = BudgetBook.from_dict(result["book"])
        assert book.entry(initial["held"]["custom_id"]) == initial["held"]["entry"]
        assert book.ceiling_nanousd == 150_000_000_000 and book.operational_limit_nanousd == 120_000_000_000
        run = engine.ledger.get(result["run"], runner.RUN_KIND)
        finish = engine.ledger.get(result["finish_ref"], runner.FINISH_KIND)
        assert run["migration_ref"] == finish["migration_ref"] == result["migration_ref"]
        assert run["deadline_epoch"] == initial["ack"]["deadline_epoch"]
        assert run["count_workers"] == 16 and run["queue_token_cap"] == 20_000_000
        if mode == "deadline":
            assert len(transport.calls) == calls_before
        else:
            assert len(transport.jobs) == jobs_before + 2
            assert all(json.loads(line)["body"]["max_output_tokens"] == 4096
                for raw in transport.files.values() for line in raw.splitlines())
        if mode == "unknown":
            assert book.reserved_nanousd > 1_402_432 and "held_cost_new_or_changed_unknown_blocks" in finish["blockers"]
        else:
            before_resume = len(transport.calls)
            migration_count = engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_budget_scheduler_migration'").fetchone()[0]
            resumed = engine.execute("status", {"plan": plan["id"], "policy_ref": arguments["policy_ref"],
                "migration_ref": result["migration_ref"], "allow_paid_execution": True},
                objective="Resume exact fictional migration after legitimate successor progress", actor="test:software")
            assert resumed["run"] == result["run"] and resumed["finish_ref"] == result["finish_ref"]
            assert len(transport.calls) == before_resume and preflights == [2]
            assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_budget_scheduler_migration'").fetchone()[0] == migration_count
    finally:
        engine.close()


class MigrationChecks(FictionalFill):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        migration = runner.handoff.register_migration(self, session, context, {**data,
            "successor_method": runner.METHOD, "successor_implementation": runner.implementation_hashes()})
        arguments = [self, session, data["plan"], data["policy_ref"], migration["id"], runner.METHOD, runner.implementation_hashes()]
        assert runner.handoff.load_migration(*arguments)["id"] == migration["id"]
        for position, wrong in ((2, "different-plan"), (3, "different-policy"), (5, "changed-method"), (6, {})):
            changed = list(arguments)
            changed[position] = wrong
            with pytest.raises(AuditError, match="exact_registered_migration"):
                runner.handoff.load_migration(*changed)
        return {"migration_ref": migration["id"]}


@pytest.mark.parametrize("bad_anchor", [False, True])
def test_migration_exact_binding_and_metadata_journal_anchor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           bad_anchor: bool) -> None:
    owner, _, transport, _, arguments = prepared_handoff(tmp_path, monkeypatch)
    before = len(transport.calls)
    if bad_anchor:
        # Deliberately corrupt only fictional metadata's record projection; the
        # event chain remains intact, so the explicit anchor check must catch it.
        connection = sqlite3.connect(Path(arguments["handoff_workspace"]) / "research.sqlite3")
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='records'"):
            connection.execute('DROP TRIGGER "' + row[0].replace('"', '""') + '"')
        connection.execute("UPDATE records SET created_event=1 WHERE id=?", (arguments["handoff_ref"],))
        connection.commit()
        connection.close()
    engine = MigrationChecks(owner, config=Config(offline=False), transport=transport)
    try:
        if bad_anchor:
            with pytest.raises(AuditError, match="metadata_record_not_journal_anchored"):
                engine.execute("status", arguments, objective="Reject fictional unanchored handoff", actor="test:software")
        else:
            assert engine.execute("status", arguments, objective="Check exact fictional migration identity", actor="test:software")["migration_ref"]
        assert len(transport.calls) == before
    finally:
        engine.close()


def projected(value: Any) -> Json:
    payload = canonical(value)
    row = {"kind": runner.ACTION_KIND, "logical_key": "synthetic", "payload": payload,
        "artifact": hashlib.sha256(payload.encode()).hexdigest(), "supersedes": None, "created_event": 1}
    row["id"] = digest({"kind": row["kind"], "key": row["logical_key"], "payload": row["artifact"], "supersedes": None})
    return row


@pytest.mark.parametrize("field,value", [("payload", "{}"), ("artifact", "0" * 64), ("id", "0" * 64),
    ("kind", "unknown-kind"), ("kind", runner.RECEIPT_KIND), ("created_event", True), ("logical_key", None)])
def test_projection_exact_bytes_kind_identity_and_type(field: str, value: Any) -> None:
    row = projected({2: "two", 10: "ten"})
    assert runner.projection_value(row) == {"2": "two", "10": "ten"}
    row[field] = value
    with pytest.raises(AuditError, match="projection"):
        runner.projection_value(row)
    with pytest.raises(AuditError, match="not_object"):
        runner.projection_value(projected([]))


class IndexHarness(Research):
    @audited_handler
    def _status(self, session: str, context: Context, data: Json) -> Json:
        if data.get("seed"):
            return {"id": self.ledger.record(session, runner.ACTION_KIND, "old", {"plan_id": "plan", "value": "old"})}
        index = runner.IncrementalIndex()
        read, read_bytes, get = self.ledger.artifacts.read, self.ledger.artifacts.read_bytes, self.ledger.get
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("index must use exact projection after full preflight")
        try:
            self.ledger.artifacts.read = forbidden
            self.ledger.artifacts.read_bytes = forbidden
            self.ledger.get = forbidden
            index.refresh(self, session, "plan")
            assert len(index.rows(runner.ACTION_KIND)) == 1
            index.refresh(self, session, "plan")
            assert len(index.rows(runner.ACTION_KIND)) == 1
        finally:
            self.ledger.artifacts.read, self.ledger.artifacts.read_bytes, self.ledger.get = read, read_bytes, get
        self.ledger.record(session, runner.ACTION_KIND, "new", {"plan_id": "plan", "value": "new"})
        index.refresh(self, session, "plan")
        return {"values": [row["value"] for row in index.rows(runner.ACTION_KIND)]}


def test_index_reuses_preflight_verified_projection_without_artifact_reads(tmp_path: Path) -> None:
    engine = IndexHarness(tmp_path / "index", project=tmp_path)
    try:
        engine.execute("status", {"seed": True}, objective="Seed fictional index", actor="test:software")
        result = engine.execute("status", {}, objective="Test exact incremental projection", actor="test:software")
        assert result["values"] == ["old", "new"]
        with pytest.raises(AuditError):
            runner.IncrementalIndex().refresh(engine, "inactive", "plan")
    finally:
        engine.close()


def test_predecessor_large_manifest_uses_unchanged_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def validate(*args: Any) -> bytes:
        calls.append(args)
        return b"exact-old-file"
    monkeypatch.setattr(runner.predecessor, "validate_large_manifest", validate)
    manifest = {"throughput_method": runner.predecessor.METHOD}
    assert runner.validate_large_manifest(None, "session", "plan", {}, manifest, runner.fast.core.load_contract_snapshot()) == b"exact-old-file"
    assert calls[0][4] is manifest


def test_new_fill_1000_row_manifest_uses_complete_original_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(previous, "runner", runner)
    previous.test_exact_1000_fulltext_file_validated_with_unchanged_contract_and_partition(tmp_path, monkeypatch)


@pytest.mark.parametrize("path", ["/v1/files", "/v1/batches"])
def test_fill_each_provider_write_rechecks_current_state(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    def current(*args: Any) -> tuple[Json, None, str]:
        calls.append("current")
        return {}, None, "state"
    def gate(*args: Any) -> list[str]:
        calls.append("gate")
        return ["new_unknown"]
    engine: Any = SimpleNamespace(deadline=100.0, plan={}, current=current, gate=gate)
    monkeypatch.setattr(runner, "time", SimpleNamespace(time=lambda: 1.0))
    with pytest.raises(runner.ResearchError, match="admission_blocked:new_unknown"):
        runner.FillResearch.action(engine, "session", "plan", "policy", "key", {"method": "POST", "path": path})
    assert calls == ["current", "gate"]
