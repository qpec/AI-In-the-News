"""Real temporary Research ledger, fictional articles and synthetic HTTP only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any

import pytest

import test_lean_luna_batch as fixture_module
import lean_luna_runtime as module
from newsresearch.common import AuditError


def setup(tmp_path: Path, *, count: int = 2, missing_hold_field: bool = False) -> tuple[Path, Path]:
    runner = fixture_module.fixture(tmp_path, [fixture_module.record(i) for i in range(count)])
    snapshot = {key: runner.meta[key] for key in ("version", "source_owner", "plan_id", "authorization_id", "deadline_epoch", "plan", "corpora")}
    snapshot.update(blockers=[], budget={**runner.meta["budget"], **runner.totals(), "frozen": False,
        "entries": {row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM budget_entries")}},
        requests={row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM requests")},
        counts={row["custom_id"]: json.loads(row["payload"]) for row in runner.db.execute("SELECT * FROM counts")})
    snapshot["snapshot_id"] = module.digest(snapshot)
    runner.db.execute("UPDATE meta SET value=? WHERE key='snapshot_id'", (json.dumps(snapshot["snapshot_id"]),))
    if missing_hold_field:
        runner.db.execute("DELETE FROM meta WHERE key='imported_unknown_entry_hashes'")
    database = runner.database
    runner.close()
    path = tmp_path / "snapshot.json"
    path.write_text(module.canonical(snapshot), encoding="utf-8")
    return database, path


def execute(engine: module.LeanResearch, database: Path, snapshot: Path | None, **data: Any) -> dict[str, Any]:
    return engine.execute("status", {"state": str(database), "import_snapshot": str(snapshot) if snapshot else None, **data},
        objective="Test synthetic lean audited runtime without production access", actor="test:lean-runtime")


def test_offline_exact_prompt_baseline_hold_upgrade_and_restart(tmp_path: Path) -> None:
    database, snapshot = setup(tmp_path, missing_hold_field=True)
    fake = fixture_module.FakeTransport()
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    try:
        result = execute(engine, database, snapshot)
        assert result["http_calls"] == 0 and fake.calls == []
        assert result["prompt"]["requests"] == 2 and result["prompt"]["physical_copies"] == 2
        assert result["reserved_nanousd"] == 1402432 and result["new_inference_authorized"] is False
        assert engine.ledger.artifacts.read_bytes(result["prompt"]["jsonl_ref"]) == Path(result["prompt"]["local_path"]).read_bytes()
        assert engine.ledger.get(result["baseline"], module.BASELINE)["new_inference_authorized"] is False
        resumed = execute(engine, database, None)
        assert resumed["baseline"] == result["baseline"] and resumed["prompt"] == result["prompt"]
        with sqlite3.connect(database) as connection:
            held = json.loads(connection.execute("SELECT value FROM meta WHERE key='imported_unknown_entry_hashes'").fetchone()[0])
        assert set(held) == {"old-held"}
    finally:
        engine.close()


@pytest.mark.parametrize("change", ["spent", "hold", "cost_column", "deadline", "snapshot_hash"])
def test_baseline_rejects_changed_import(tmp_path: Path, change: str) -> None:
    database, snapshot = setup(tmp_path)
    with sqlite3.connect(database) as connection:
        if change == "spent":
            connection.execute("UPDATE requests SET submitted=1")
        elif change == "hold":
            connection.execute("UPDATE budget_entries SET payload=json_set(payload,'$.reserved_nanousd',0)")
        elif change == "cost_column":
            connection.execute("UPDATE budget_entries SET reserved_nanousd=0")
        elif change == "deadline":
            connection.execute("UPDATE meta SET value='2000' WHERE key='deadline_epoch'")
        else:
            snapshot.write_text(snapshot.read_text().replace('"frozen":false', '"frozen":true'))
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        with pytest.raises(AuditError):
            execute(engine, database, snapshot)
        assert engine.transport.calls == []
    finally:
        engine.close()


def run_one_file(runner: module.batch.LeanBatch, **_: Any) -> dict[str, Any]:
    runner.allow_network = True
    manifest = runner.log_next()
    assert manifest
    runner.count_file(manifest)
    assert runner.reserve(manifest) is None
    raw = runner.raw(manifest)
    with ThreadPoolExecutor(max_workers=2) as pool:
        runner.start_remote(pool, "upload", manifest, {"method": "POST", "path": "/v1/files", "purpose": "batch",
            "filename": manifest["id"] + ".jsonl", "content_sha256": manifest["sha256"]}, raw)
        while runner.remote:
            runner.pump(pool)
            time.sleep(0.005)
    return {"mode": "synthetic_single_file", **runner.summary()}


def test_synthetic_count_upload_create_intents_before_http_one_writer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path)
    fake = fixture_module.FakeTransport()
    fake.database = database
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    writer = threading.get_ident()
    original_record = engine.ledger.record
    original_perform = fake.perform
    def checked_record(*args: Any, **kwargs: Any) -> str:
        assert threading.get_ident() == writer
        return original_record(*args, **kwargs)
    def checked_perform(request: dict[str, Any], body: bytes | None, identifier: str) -> module.BatchReceipt:
        assert threading.get_ident() != writer
        handle = engine.gateway.handles[identifier]
        with sqlite3.connect(engine.ledger.root / "research.sqlite3") as connection:
            assert connection.execute("SELECT 1 FROM records WHERE id=? AND kind=?", (handle.intent_ref, module.INTENT)).fetchone()
        return original_perform(request, body, identifier)
    monkeypatch.setattr(engine.ledger, "record", checked_record)
    monkeypatch.setattr(fake, "perform", checked_perform)
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    try:
        result = execute(engine, database, snapshot, allow_paid_execution=True)
        assert result["submitted"] == 2 and result["pending_jobs"] == 1 and result["http_calls"] == 4
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.INTENT,)).fetchone()[0] == 3
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.RECEIPT,)).fetchone()[0] == 3
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT reserved_nanousd FROM budget_entries WHERE custom_id='old-held'").fetchone()[0] == 1402432
        with pytest.raises(AuditError, match="active_writer"):
            engine.gateway.assert_active()
    finally:
        engine.close()


def test_unknown_receipt_retained_and_restart_never_retries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path)
    fake = fixture_module.FakeTransport()
    fake.create_unknown = True
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    try:
        result = execute(engine, database, snapshot, allow_paid_execution=True)
        assert result["submitted"] == 2 and result["reserved_nanousd"] > 1402432
        calls = len(fake.calls)
        with pytest.raises(AuditError, match="prior_failed_gateway"):
            execute(engine, database, None, allow_paid_execution=True)
        assert len(fake.calls) == calls
    finally:
        engine.close()


@pytest.mark.parametrize("change", ["count", "cap", "reservation", "deadline", "foreign_file"])
def test_create_gate_independently_rejects_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str) -> None:
    database, snapshot = setup(tmp_path)
    fake = fixture_module.FakeTransport()
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    original = module.LeanGateway.validate_create
    def tamper(gateway: module.LeanGateway, manifest: dict[str, Any], body: bytes) -> None:
        runner = gateway.runner
        assert runner
        if change == "count":
            runner.db.execute("UPDATE counts SET input_tokens=1")
        elif change == "cap":
            runner.db.execute("UPDATE budget_entries SET payload=json_set(payload,'$.request.max_output_tokens',99999) WHERE status='reserved'")
        elif change == "reservation":
            runner.db.execute("UPDATE budget_entries SET reserved_nanousd=0 WHERE status='reserved'")
        elif change == "deadline":
            runner.clock = lambda: 1001
        else:
            value = json.loads(body)
            value["input_file_id"] = "file-foreign"
            body = module.canonical(value).encode()
        original(gateway, manifest, body)
    monkeypatch.setattr(module.LeanGateway, "validate_create", tamper)
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    try:
        with pytest.raises(AuditError):
            execute(engine, database, snapshot, allow_paid_execution=True)
        assert not any(call["path"] == "/v1/batches" for call in fake.calls)
    finally:
        engine.close()


def test_real_transport_permission_is_not_implied_by_import(tmp_path: Path) -> None:
    database, snapshot = setup(tmp_path)
    fake = fixture_module.FakeTransport()
    fake.synthetic = False
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    try:
        with pytest.raises(AuditError, match="resume_permission"):
            execute(engine, database, snapshot, allow_paid_execution=True)
        assert fake.calls == []
    finally:
        engine.close()


def test_credential_receipt_stops_before_projection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path)
    fake = fixture_module.FakeTransport()
    original = fake.perform
    def unsafe(request: dict[str, Any], body: bytes | None, identifier: str) -> module.BatchReceipt:
        receipt = original(request, body, identifier)
        return module.BatchReceipt(b'{"api_key":"forbidden"}', 200) if request == module.batch.COUNT_ROUTE else receipt
    monkeypatch.setattr(fake, "perform", unsafe)
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    try:
        with pytest.raises(module.state.StateError, match="count_failed"):
            execute(engine, database, snapshot, allow_paid_execution=True)
        rows = engine.ledger.db.execute("SELECT id FROM records WHERE kind=?", (module.RECEIPT,)).fetchall()
        assert len(rows) == 1
        receipt = engine.ledger.get(rows[0][0], module.RECEIPT)
        assert all(row["retention_error"] == "credential_guard" and "raw_body_utf8" not in row for row in receipt["members"])
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 0
    finally:
        engine.close()


def test_restart_rejects_external_state_rewrite(tmp_path: Path) -> None:
    database, snapshot = setup(tmp_path)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        execute(engine, database, snapshot)
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE budget_entries SET reserved_nanousd=0")
        with pytest.raises(AuditError, match="unfinished_requires_reconciliation"):
            execute(engine, database, None)
    finally:
        engine.close()


def test_imported_cache_preserves_actual_action_and_receipt_identity(tmp_path: Path) -> None:
    runner = fixture_module.fixture(tmp_path, [fixture_module.record(1)])
    try:
        manifest = runner.log_next()
        assert manifest
        request = json.loads(runner.raw(manifest).splitlines()[0])
        raw = module.canonical(module.count_request_body(request["body"])).encode()
        logical = module.digest({"request": module.batch.COUNT_ROUTE, "body_sha256": module.sha(raw)})
        def save(raw: bytes) -> str:
            reference = module.sha(raw)
            (runner.owner / "objects" / reference).write_bytes(raw)
            return reference
        exact = save(module.canonical({"original_body_ref": save(raw)}).encode())
        receipt = {"id": "original-receipt", "status": 200, "unknown": False,
            "body_ref": save(b'{"input_tokens":100}'), "provider_request_id": "original-request"}
        runner.meta["count_action_cache"][logical] = {"action_id": "actual-original-action", "exact_request_ref": exact, "receipt": receipt}
        runner.allow_network = True
        runner.count_file(manifest)
        count = json.loads(runner.db.execute("SELECT payload FROM counts").fetchone()[0])
        assert count["origin_action_id"] == "actual-original-action"
        assert count["logical_count_hash"] == logical and count["exact_request_ref"] == exact
        assert count["origin_receipt_id"] == "original-receipt" and runner.transport.calls == []
    finally:
        runner.close()


def test_gateway_forbids_second_dispatch_of_same_prepared_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path, count=1)
    fake = fixture_module.FakeTransport()
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    def only_count(runner: module.batch.LeanBatch, **_: Any) -> dict[str, Any]:
        runner.allow_network = True
        manifest = runner.log_next()
        assert manifest
        runner.count_file(manifest)
        handle = next(iter(runner.gateway.handles.values()))
        with pytest.raises(AuditError, match="used_http_permit"):
            runner.gateway.perform_prepared(handle)
        return runner.summary()
    monkeypatch.setattr(module.batch.LeanBatch, "run", only_count)
    try:
        result = execute(engine, database, snapshot, allow_paid_execution=True)
        assert result["http_calls"] == 1
    finally:
        engine.close()


def test_import_count_token_column_must_match_retained_payload(tmp_path: Path) -> None:
    database, path = setup(tmp_path, count=1)
    snapshot = json.loads(path.read_text())
    custom = next(iter(snapshot["requests"]))
    count = {"input_tokens": 100, "origin_action_id": "retained-count"}
    snapshot["counts"] = {custom: count}
    snapshot["snapshot_id"] = module.digest({key: value for key, value in snapshot.items() if key != "snapshot_id"})
    path.write_text(module.canonical(snapshot))
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO counts VALUES(?,?,?)", (custom, 1, module.canonical(count)))
        connection.execute("UPDATE meta SET value=? WHERE key='snapshot_id'", (json.dumps(snapshot["snapshot_id"]),))
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        with pytest.raises(AuditError, match="count_projection_changed"):
            execute(engine, database, path)
        assert engine.transport.calls == []
    finally:
        engine.close()


def test_imported_count_cannot_underreserve_with_consistent_changed_columns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path, count=1)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    original = module.LeanGateway.validate_create
    def tamper(gateway: module.LeanGateway, manifest: dict[str, Any], body: bytes) -> None:
        runner = gateway.runner
        assert runner
        custom = manifest["request_ids"][0]
        evidence = json.loads(runner.db.execute("SELECT payload FROM counts WHERE custom_id=?", (custom,)).fetchone()[0])
        gateway.imported_counts[custom] = evidence
        del gateway.receipts[evidence["origin_action_id"]]
        runner.db.execute("UPDATE counts SET input_tokens=1 WHERE custom_id=?", (custom,))
        value = json.loads(runner.db.execute("SELECT payload FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()[0])
        value["request"]["input_count"]["input_tokens"] = 1
        value["reserved_nanousd"] = module.state.cost(runner.price, 1, 4096)
        runner.db.execute("UPDATE budget_entries SET reserved_nanousd=?,payload=? WHERE custom_id=?",
            (value["reserved_nanousd"], module.canonical(value), custom))
        original(gateway, manifest, body)
    monkeypatch.setattr(module.LeanGateway, "validate_create", tamper)
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    try:
        with pytest.raises(AuditError, match="count_or_reservation_changed"):
            execute(engine, database, snapshot, allow_paid_execution=True)
        assert not any(call["path"] == "/v1/batches" for call in engine.transport.calls)
    finally:
        engine.close()


def test_malformed_utf8_receipt_retained_exactly_before_parse_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path, count=1)
    fake = fixture_module.FakeTransport()
    raw = b'{"input_tokens":\xff}'
    monkeypatch.setattr(fake, "perform", lambda *args: module.BatchReceipt(raw, 200))
    monkeypatch.setattr(module.batch.LeanBatch, "run", run_one_file)
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    try:
        with pytest.raises(module.state.StateError, match="count_failed"):
            execute(engine, database, snapshot, allow_paid_execution=True)
        record = engine.ledger.db.execute("SELECT id FROM records WHERE kind=?", (module.RECEIPT,)).fetchone()
        receipt = engine.ledger.get(record[0], module.RECEIPT)["members"][0]
        assert engine.ledger.artifacts.read_bytes(receipt["raw_body_ref"]) == raw
        assert receipt["body_sha256"] == module.sha(raw)
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 0
            assert connection.execute("SELECT status FROM actions").fetchone()[0] == "unknown"
    finally:
        engine.close()


def test_failed_concurrent_transfer_drains_and_retains_all_count_permits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database, snapshot = setup(tmp_path, count=3)
    fake = fixture_module.FakeTransport()
    released = threading.Event()
    original = fake.perform
    def delayed(request: dict[str, Any], body: bytes | None, identifier: str) -> module.BatchReceipt:
        if request == module.batch.COUNT_ROUTE:
            assert released.wait(timeout=5)
        return original(request, body, identifier)
    monkeypatch.setattr(fake, "perform", delayed)
    monkeypatch.setattr(module.batch, "COUNT_WORKERS", 1)
    engine = module.LeanResearch(tmp_path / "audit", transport=fake, clock=lambda: 10)
    def counts_with_failed_transfer(runner: module.batch.LeanBatch, **_: Any) -> dict[str, Any]:
        runner.allow_network = True
        manifest = runner.log_next()
        assert manifest
        raw = runner.raw(manifest)
        upload = {"action_id": "failed-upload", "request": {"method": "POST", "path": "/v1/files", "purpose": "batch",
            "filename": manifest["id"] + ".jsonl", "content_sha256": manifest["sha256"]}, "body": raw, "admission": True}
        gateway = runner.gateway
        handle = gateway.prepare_many([upload], manifest={**manifest, "raw_jsonl": raw})[0]
        with ThreadPoolExecutor(max_workers=1) as pool:
            observed = pool.submit(gateway.perform_prepared, handle).result()
        failed = module.PreparedReceipt(handle, module.BatchReceipt(None, None, error_type="TimeoutError", unknown=True), observed.completed_at)
        def tick() -> None:
            gateway.retain_many([failed])
            released.set()
            raise RuntimeError("concurrent transfer failed")
        runner.count_file(manifest, tick)
        raise AssertionError("failed transfer must stop")
    monkeypatch.setattr(module.batch.LeanBatch, "run", counts_with_failed_transfer)
    try:
        with pytest.raises(RuntimeError, match="concurrent transfer failed"):
            execute(engine, database, snapshot, allow_paid_execution=True)
        receipts = [engine.ledger.get(row[0], module.RECEIPT) for row in engine.ledger.db.execute("SELECT id FROM records WHERE kind=?", (module.RECEIPT,))]
        count_bundle = next(value for value in receipts if len(value["members"]) == 3)
        assert len(count_bundle["members"]) == 3
        assert sum(row["error_type"] == "gateway_stopped_before_send" for row in count_bundle["members"]) == 2
        assert sum(row["status"] == 200 for row in count_bundle["members"]) == 1
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT COUNT(*) FROM actions WHERE receipt_json IS NOT NULL").fetchone()[0] == 3
        assert sum(call == module.batch.COUNT_ROUTE for call in fake.calls) == 1
    finally:
        released.set()
        engine.close()


def change_code(monkeypatch: pytest.MonkeyPatch, digit: str = "1") -> None:
    original = module.implementation()
    original["lean_luna_runtime.py"] = digit * 64
    monkeypatch.setattr(module, "implementation", lambda: original)


@pytest.mark.parametrize("legacy_baseline", [False, True])
def test_explicit_code_amendment_preserves_state_and_permission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_baseline: bool) -> None:
    database, snapshot = setup(tmp_path)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    original_record = engine.ledger.record
    def legacy_record(session: str, kind: str, key: str, payload: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        if kind == module.BASELINE and not args and not kwargs.get("supersedes"):
            payload = {key: value for key, value in payload.items() if key != "versions"}
        return original_record(session, kind, key, payload, *args, **kwargs)
    if legacy_baseline:
        monkeypatch.setattr(engine.ledger, "record", legacy_record)
    try:
        first = execute(engine, database, snapshot)
        old = engine.ledger.get(first["baseline"], module.BASELINE)
        with sqlite3.connect(database) as connection:
            before = connection.serialize()
        change_code(monkeypatch)
        with pytest.raises(AuditError, match="explicit_code_amendment_required"):
            execute(engine, database, None)
        amended = execute(engine, database, None, amend_baseline=first["baseline"], amend_reason="Reviewed count and receipt integrity fixes")
        value = engine.ledger.get(amended["baseline"], module.BASELINE)
        assert value["previous_baseline"] == first["baseline"] and amended["baseline"] != first["baseline"]
        assert value["new_inference_authorized"] is False and amended["http_calls"] == 0
        assert value["initial_totals"] == old["initial_totals"] and value["held_hashes"] == old["held_hashes"]
        assert value["deadline_epoch"] == old["deadline_epoch"]
        assert engine.ledger.get(first["baseline"], module.BASELINE) == old
        assert engine.ledger.db.execute("SELECT supersedes FROM records WHERE id=?", (amended["baseline"],)).fetchone()[0] == first["baseline"]
        with sqlite3.connect(database) as connection:
            assert connection.serialize() == before
        resumed = execute(engine, database, None)
        assert resumed["baseline"] == amended["baseline"] and engine.transport.calls == []
        change_code(monkeypatch, "2")
        with pytest.raises(AuditError, match="exact_latest_baseline"):
            execute(engine, database, None, amend_baseline=first["baseline"], amend_reason="Stale parent")
    finally:
        engine.close()


@pytest.mark.parametrize("wrong", ["id", "reason", "no_change"])
def test_code_amendment_requires_exact_parent_reason_and_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, wrong: str) -> None:
    database, snapshot = setup(tmp_path)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        first = execute(engine, database, snapshot)
        if wrong != "no_change":
            change_code(monkeypatch)
        with pytest.raises(AuditError, match="amendment"):
            execute(engine, database, None, amend_baseline="wrong" if wrong == "id" else first["baseline"],
                amend_reason=" " if wrong == "reason" else "Reviewed code changes")
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.BASELINE,)).fetchone()[0] == 1
        assert engine.transport.calls == []
    finally:
        engine.close()


@pytest.mark.parametrize("mutation", ["budget", "spent", "deadline", "hold"])
def test_code_amendment_cannot_adopt_changed_operational_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    database, snapshot = setup(tmp_path)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        first = execute(engine, database, snapshot)
        change_code(monkeypatch)
        with sqlite3.connect(database) as connection:
            if mutation == "budget":
                connection.execute("UPDATE budget_entries SET charged_nanousd=0,reserved_nanousd=0")
            elif mutation == "spent":
                connection.execute("UPDATE requests SET submitted=1")
            elif mutation == "deadline":
                connection.execute("UPDATE meta SET value='2000' WHERE key='deadline_epoch'")
            else:
                connection.execute("UPDATE meta SET value='{}' WHERE key='imported_unknown_entry_hashes'")
        with pytest.raises(AuditError, match="requires_reconciliation"):
            execute(engine, database, None, amend_baseline=first["baseline"], amend_reason="Cannot bless changed state")
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.BASELINE,)).fetchone()[0] == 1
    finally:
        engine.close()


@pytest.mark.parametrize("kind", ["protocol", "question", "profile"])
def test_code_amendment_rejects_semantic_method_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    database, snapshot = setup(tmp_path)
    engine = module.LeanResearch(tmp_path / "audit", transport=fixture_module.FakeTransport(), clock=lambda: 10)
    try:
        first = execute(engine, database, snapshot)
        change_code(monkeypatch)
        original = engine._version
        def changed(session: str, context: Any, data: dict[str, Any]) -> dict[str, Any]:
            if data["kind"] == kind:
                data = {**data, "content": {**data["content"], "additional_scientific_rule": "changed scope"}}
            return original(session, context, data)
        monkeypatch.setattr(engine, "_version", changed)
        with pytest.raises(AuditError, match="only_implementation_hashes"):
            execute(engine, database, None, amend_baseline=first["baseline"], amend_reason="Code changes only claimed")
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind=?", (module.BASELINE,)).fetchone()[0] == 1
    finally:
        engine.close()
