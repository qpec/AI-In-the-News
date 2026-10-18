"""Fictional packets and fake HTTP only; no production owner or inference."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lean_luna_batch as module
import lean_luna_state as state

Json = dict[str, Any]
SNAPSHOT = module.core.load_contract_snapshot()
PRICE = {"model": "gpt-6-luna", "input_nanousd_per_million": 100_000_000,
    "cache_write_nanousd_per_million": 125_000_000, "output_nanousd_per_million": 500_000_000,
    "batch_multiplier": [1, 2], "regional_multiplier": [11, 10], "long_input_multiplier": [2, 1],
    "long_output_multiplier": [3, 2], "long_context_threshold": 272000}


def record(number: int = 1, corpus: str = "incident-reports") -> Json:
    article = {"title": f"Fictional agency event {number}", "body": f"Fictional event {number}.\r\n\r\n"
        + "Complete retained paragraph é 😀. " * 20 + "\nFinal paragraph. ",
        "date": "2026-10-01", "lang": "eng", "source": {"uri": "fictional.example"}}
    return module.core.build_request_record(article, corpus_id=corpus, manifest_sha256=state.digest(corpus),
        source_locator={"archive_path": corpus + ".zip", "line": number}, source_sha256=state.digest(article),
        count_tokens=len, contract_snapshot=SNAPSHOT)


class FakeTransport:
    synthetic = True
    max_retries = 0

    def __init__(self) -> None:
        self.calls: list[Json] = []
        self.lock = threading.Lock()
        self.barrier: threading.Barrier | None = None
        self.database: Path | None = None
        self.create_unknown = False
        self.fail_count = False

    def perform(self, request: Json, body: bytes | None, identifier: str) -> module.BatchReceipt:
        with self.lock:
            self.calls.append(request)
        if request == module.COUNT_ROUTE:
            if self.database is not None:
                with sqlite3.connect(self.database) as connection:
                    assert connection.execute("SELECT status FROM actions WHERE action_id=?", (identifier,)).fetchone()[0] == "started"
            if self.barrier:
                self.barrier.wait(timeout=10)
            if self.fail_count:
                return module.BatchReceipt(b'{"error":"rate_limited"}', 429)
            assert body is not None
            parsed = json.loads(body)
            assert set(parsed) == {"model", "instructions", "input", "text"}
            return module.BatchReceipt(b'{"input_tokens":100,"model":"gpt-6-luna"}', 200)
        if request["path"] == "/v1/files":
            assert body is not None
            return module.BatchReceipt(state.canonical({"id": "file-test", "purpose": "batch", "bytes": len(body)}).encode(), 200)
        if request["path"] == "/v1/batches":
            if self.create_unknown:
                return module.BatchReceipt(None, None, error_type="TimeoutError", unknown=True)
            assert body is not None
            return module.BatchReceipt(state.canonical({"id": "batch_test", **json.loads(body)}).encode(), 200)
        raise AssertionError("unexpected fake route")


def fixture(tmp_path: Path, records: list[Json] | None = None, *, transport: Any = None,
            gateway: Any = None) -> module.LeanBatch:
    records = records if records is not None else [record()]
    owner = tmp_path / "legacy"
    objects = owner / "objects"
    objects.mkdir(parents=True)
    destination = tmp_path / "lean" / "state.sqlite3"
    destination.parent.mkdir()
    connection = sqlite3.connect(destination)
    connection.executescript(state.SCHEMA)
    def artifact(value: Any) -> str:
        raw = state.canonical(value).encode()
        reference = hashlib.sha256(raw).hexdigest()
        (objects / reference).write_bytes(raw)
        return reference
    hold = {"request": {"request_id": "old-held", "plan_id": "plan", "input_count": {"input_tokens": 4015}},
        "status": "unknown", "charged_nanousd": 0, "reserved_nanousd": 1402432}
    metadata = {"version": state.VERSION, "blockers": [], "source_execution_stopped_attested_by_importer": True,
        "source_owner": str(owner), "snapshot_id": "synthetic", "plan_id": "plan", "authorization_id": "auth",
        "plan": {"contract_sha256": SNAPSHOT.contract_sha256}, "count_action_cache": {}, "corpora": {},
        "deadline_epoch": 1000, "imported_unknown_entry_hashes": {"old-held": state.digest(hold)},
        "budget": {"unknown_request_ids": ["old-held"], "config": {"ceiling_nanousd": state.HARD_CAP,
            "operational_limit_nanousd": state.OPERATING_CAP, "price_policy": PRICE}}}
    for key, value in metadata.items():
        connection.execute("INSERT INTO meta VALUES(?,?)", (key, state.canonical(value)))
    connection.execute("INSERT INTO budget_entries VALUES('old-held','unknown',0,1402432,?)", (state.canonical(hold),))
    if records:
        corpus = records[0]["descriptor"]["corpus_id"]
        manifest = {"id": "legacy-staged", "corpus_id": corpus, "request_ids": [row["request"]["custom_id"] for row in records], "submitted": False}
        connection.execute("INSERT INTO manifests VALUES(?,?,?)", (manifest["id"], corpus, state.canonical(manifest)))
        for row in records:
            task = {"custom_id": row["request"]["custom_id"], "corpus_id": corpus, "manifest_id": manifest["id"],
                "submitted": False, "status": "staged", "request_body_ref": row["descriptor"]["request_body_sha256"],
                "request_ref": artifact(row["request"]), "descriptor": row["descriptor"]}
            connection.execute("INSERT INTO requests VALUES(?,?,?,0,'staged',?)", (task["custom_id"], corpus, manifest["id"], state.canonical(task)))
    connection.commit()
    connection.close()
    engine = module.LeanBatch(destination, transport=transport or FakeTransport(), gateway=gateway, clock=lambda: 10)
    return engine


def counted(engine: module.LeanBatch) -> Json:
    manifest = engine.log_next()
    assert manifest is not None
    engine.allow_network = True
    engine.count_file(manifest)
    return manifest


def test_1000_full_packets_exact_prompt_log_and_restart(tmp_path: Path) -> None:
    records = [record(number) for number in range(1000)]
    engine = fixture(tmp_path, records)
    try:
        before = engine.totals()
        started = time.perf_counter()
        result = engine.run()
        elapsed = time.perf_counter() - started
        manifest = result["prompt"]
        assert engine.raw(manifest) == b"".join(row["jsonl_line"] for row in records)
        assert len(manifest["request_ids"]) == len(set(manifest["request_ids"])) == 1000
        assert result["http_calls"] == len(engine.transport.calls) == 0
        assert engine.totals() == before and manifest["bytes"] < module.MAX_BYTES
        assert engine.run()["prompt"] == manifest
        print(f"SYNTHETIC 1000 full packets: {elapsed:.3f}s, {manifest['bytes']} exact bytes, zero HTTP")
    finally:
        engine.close()


@pytest.mark.parametrize("mode", ["partition", "duplicate", "body"])
def test_prompt_file_rejects_changed_or_mixed_scope(tmp_path: Path, mode: str) -> None:
    value = record()
    rows = [value]
    if mode == "partition":
        rows.append(record(2, "cybercrime"))
    elif mode == "duplicate":
        rows.append(value)
    else:
        value["request"]["body"]["max_output_tokens"] = 20
    with pytest.raises(state.StateError):
        module.prompt_file(tmp_path, "incident-reports", rows, SNAPSHOT)


def test_exact_staged_conversion_skipped_after_restart_and_ambiguous_mapping_rejected(tmp_path: Path) -> None:
    engine = fixture(tmp_path, [record(1), record(2)])
    try:
        manifest = engine.log_next()
        assert manifest
        engine.db.execute("UPDATE requests SET submitted=1,status='submitted'")
        # Iterating past legacy manifests reaches the absent synthetic corpus;
        # no old request is yielded or re-read, and no mixed-submitted error.
        with pytest.raises(KeyError, match="cybercrime"):
            next(engine.preparations())
        engine.db.execute("UPDATE requests SET manifest_id='unrelated' WHERE custom_id=?", (manifest["request_ids"][0],))
        with pytest.raises(state.StateError, match="converted_manifest_membership_changed"):
            next(engine.preparations())
    finally:
        engine.close()


@pytest.mark.parametrize("pressure", ["budget", "queue", "deadline"])
def test_atomic_file_admission_never_changes_money_on_pressure(tmp_path: Path, pressure: str, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = fixture(tmp_path, [record(1), record(2)])
    try:
        manifest = counted(engine)
        if pressure == "budget":
            engine.db.execute("INSERT INTO budget_entries VALUES('spent','settled',?,0,'{}')", (state.OPERATING_CAP - 1402432,))
        elif pressure == "queue":
            monkeypatch.setattr(engine, "queued_tokens", lambda: module.QUEUE_TOKENS)
        else:
            engine.clock = lambda: 1000
        before = engine.totals()
        assert engine.reserve(manifest) == pressure
        assert engine.totals() == before
        assert {row[0] for row in engine.db.execute("SELECT status FROM requests")} == {"logged"}
        assert engine.db.execute("SELECT COUNT(*) FROM budget_entries WHERE status='reserved'").fetchone()[0] == 0
    finally:
        engine.close()


def test_sixteen_count_workers_durable_intents_single_writer_and_error_drain(tmp_path: Path) -> None:
    fake = FakeTransport()
    fake.barrier = threading.Barrier(16)
    engine = fixture(tmp_path, [record(number) for number in range(16)], transport=fake)
    fake.database = engine.database
    try:
        manifest = engine.log_next()
        assert manifest
        engine.allow_network = True
        def failed_transfer() -> None:
            raise state.StateError("synthetic_transfer_failure")
        with pytest.raises(state.StateError, match="synthetic_transfer_failure"):
            engine.count_file(manifest, failed_transfer)
        assert len(fake.calls) == 16
        assert engine.db.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 16
        assert engine.db.execute("SELECT COUNT(*) FROM actions WHERE status='complete'").fetchone()[0] == 16
        assert engine.totals()["reserved_nanousd"] == 1402432
    finally:
        engine.close()


def test_failed_count_is_retained_and_not_retried(tmp_path: Path) -> None:
    fake = FakeTransport()
    fake.fail_count = True
    engine = fixture(tmp_path, transport=fake)
    try:
        manifest = engine.log_next()
        assert manifest
        engine.allow_network = True
        with pytest.raises(state.StateError, match="count_failed"):
            engine.count_file(manifest)
        with pytest.raises(state.StateError, match="prior_count_not_retryable"):
            engine.count_file(manifest)
        assert len(fake.calls) == 1 and engine.db.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 0
    finally:
        engine.close()


def drain(engine: module.LeanBatch, pool: ThreadPoolExecutor) -> None:
    while engine.remote:
        engine.pump(pool)
        time.sleep(0.001)


def test_ambiguous_create_holds_entire_cost_and_never_resubmits(tmp_path: Path) -> None:
    fake = FakeTransport()
    fake.create_unknown = True
    engine = fixture(tmp_path, transport=fake)
    try:
        manifest = counted(engine)
        assert engine.reserve(manifest) is None
        before = engine.totals()
        manifest["file_id"] = "file-test"
        request = {"method": "POST", "path": "/v1/batches"}
        body = state.canonical({"input_file_id": "file-test", "endpoint": "/v1/responses", "completion_window": "24h"}).encode()
        with ThreadPoolExecutor(max_workers=4) as pool:
            engine.start_remote(pool, "create", manifest, request, body)
            drain(engine, pool)
            with pytest.raises(state.StateError, match="duplicate_create"):
                engine.start_remote(pool, "create", manifest, request, body)
        assert engine.totals() == before
        assert engine.db.execute("SELECT submitted,status FROM requests").fetchone()[:] == (1, "unknown_create")
        with pytest.raises(state.StateError, match="not_retryable"):
            engine.run(allow_paid_execution=True)
        assert len([call for call in fake.calls if call["path"] == "/v1/batches"]) == 1
    finally:
        engine.close()


def test_no_post_after_deadline_or_restart_of_upload_only_admission(tmp_path: Path) -> None:
    engine = fixture(tmp_path)
    try:
        manifest = counted(engine)
        assert engine.reserve(manifest) is None
        with pytest.raises(state.StateError, match="requires_reconciliation"):
            engine.run(allow_paid_execution=True)
        engine.clock = lambda: 1000
        with ThreadPoolExecutor(max_workers=4) as pool, pytest.raises(state.StateError, match="deadline"):
            engine.start_remote(pool, "upload", manifest, {"method": "POST", "path": "/v1/files"}, engine.raw(manifest))
        assert len(engine.transport.calls) == 1
    finally:
        engine.close()


@pytest.mark.parametrize("mode", ["invalid", "truncation", "unknown", "wrong_model", "refusal"])
def test_settlement_preserves_failures_and_only_cap_truncations_continue(tmp_path: Path, mode: str) -> None:
    engine = fixture(tmp_path)
    try:
        manifest = counted(engine)
        assert engine.reserve(manifest) is None
        custom = manifest["request_ids"][0]
        engine.db.execute("INSERT INTO jobs VALUES('batch_test',?,0,?)", (manifest["id"], state.canonical({"request_ids": [custom]})))
        item: Json = {"custom_id": custom, "status": "invalid" if mode == "invalid" else "error",
            "technical_failure": mode != "invalid", "usage_complete": mode != "unknown",
            "observed_model": "other" if mode == "wrong_model" else "gpt-6-luna",
            "usage": None if mode == "unknown" else {"input_tokens": 100, "output_tokens": 4096 if mode == "truncation" else 20},
            "errors": ["response:not_completed"] if mode == "truncation" else ["test"]}
        raw = {"error": None, "response": {"status_code": 200, "body": {"model": "gpt-6-luna",
            "status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}}}
        item["lean_qualifying_truncation"] = module.qualifying_truncation(item, raw)
        engine.settle("batch_test", [item])
        saved = engine.db.execute("SELECT status,reserved_nanousd FROM budget_entries WHERE custom_id=?", (custom,)).fetchone()
        assert engine.db.execute("SELECT status FROM results WHERE custom_id=?", (custom,)).fetchone()[0] == item["status"]
        assert engine.db.execute("SELECT reserved_nanousd FROM budget_entries WHERE custom_id='old-held'").fetchone()[0] == 1402432
        if mode in {"invalid", "truncation"}:
            assert tuple(saved) == ("settled", 0) and engine.stop_reason is None
            engine.admission_checks()
        else:
            assert engine.stop_reason
            with pytest.raises(state.StateError):
                engine.admission_checks()
    finally:
        engine.close()


@pytest.mark.parametrize("mutation", ["payload", "column"])
def test_mutated_imported_hold_blocks_admission(tmp_path: Path, mutation: str) -> None:
    engine = fixture(tmp_path)
    try:
        engine.admission_checks()
        if mutation == "payload":
            entry = json.loads(engine.db.execute("SELECT payload FROM budget_entries").fetchone()[0])
            entry["reserved_nanousd"] -= 1
            engine.db.execute("UPDATE budget_entries SET payload=?", (state.canonical(entry),))
        else:
            engine.db.execute("UPDATE budget_entries SET reserved_nanousd=0")
        with pytest.raises(state.StateError, match="hold_changed"):
            engine.admission_checks()
    finally:
        engine.close()


def test_real_transport_cannot_execute_or_prepare_without_runtime(tmp_path: Path) -> None:
    engine = fixture(tmp_path)
    try:
        engine.transport = module.OpenAIBatchTransport()
        with pytest.raises(state.StateError, match="shared_gateway_required"):
            engine.run()
        engine.allow_network = True
        with pytest.raises(state.StateError, match="shared_gateway_required"):
            engine.send(module.COUNT_ROUTE, b"{}", "blocked")
    finally:
        engine.close()


class FakeGateway:
    def __init__(self) -> None:
        self.writer = threading.get_ident()
        self.fake = FakeTransport()
        self.phases: list[str] = []
        self.manifests: list[Json] = []

    def assert_active(self) -> None:
        assert threading.get_ident() == self.writer

    def prepare_many(self, actions: list[Json], *, manifest: Json | None = None) -> list[Json]:
        self.assert_active()
        self.phases.append("prepare")
        if manifest is not None:
            assert hashlib.sha256(manifest["raw_jsonl"]).hexdigest() == manifest["sha256"]
            self.manifests.append(manifest)
        return actions

    def perform_prepared(self, action: Json) -> module.BatchReceipt:
        assert threading.get_ident() != self.writer
        self.phases.append("perform")
        return self.fake.perform(action["request"], action["body"], action["action_id"])

    def retain_many(self, receipts: list[module.BatchReceipt]) -> list[module.BatchReceipt]:
        self.assert_active()
        self.phases.append("retain")
        return receipts


def test_gateway_writer_worker_receipt_order_and_exact_manifest(tmp_path: Path) -> None:
    gateway = FakeGateway()
    engine = fixture(tmp_path, gateway=gateway)
    try:
        manifest = counted(engine)
        assert gateway.phases == ["prepare", "perform", "retain"]
        assert gateway.manifests[0]["request_ids"] == manifest["request_ids"]
        assert engine.db.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 1
        assert not engine.transport.calls
    finally:
        engine.close()


def test_truncation_exception_requires_exact_raw_reason_and_usage() -> None:
    item = {"errors": ["response:not_completed"], "usage_complete": True, "usage": {"output_tokens": 4096}}
    row: Json = {"response": {"status_code": 200, "body": {"model": "gpt-6-luna", "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"}}}}
    assert module.qualifying_truncation(item, row)
    changed = deepcopy(row)
    changed["response"]["body"]["incomplete_details"]["reason"] = "content_filter"
    assert not module.qualifying_truncation(item, changed)
    assert not module.qualifying_truncation({**item, "usage": {"output_tokens": 4095}}, row)


def test_count_worker_failure_retains_other_completed_receipts(tmp_path: Path) -> None:
    class FailingGateway(FakeGateway):
        def perform_prepared(self, action: Json) -> module.BatchReceipt:
            if json.loads(action["body"])["input"][0]["content"][0]["text"].find("Fictional agency event 1") >= 0:
                raise RuntimeError("synthetic worker failed")
            return super().perform_prepared(action)
    gateway = FailingGateway()
    engine = fixture(tmp_path, [record(number) for number in (1, 2, 3)], gateway=gateway)
    try:
        manifest = engine.log_next()
        assert manifest
        engine.allow_network = True
        with pytest.raises(RuntimeError, match="synthetic worker failed"):
            engine.count_file(manifest)
        assert engine.db.execute("SELECT COUNT(*) FROM counts").fetchone()[0] == 2
        assert engine.db.execute("SELECT COUNT(*) FROM actions WHERE status='complete'").fetchone()[0] == 2
        assert engine.db.execute("SELECT COUNT(*) FROM actions WHERE status='started' AND receipt_json IS NULL").fetchone()[0] == 1
        assert gateway.phases[-1] == "retain"
    finally:
        engine.close()


def test_reservation_rejects_changed_count_column_before_charging(tmp_path: Path) -> None:
    engine = fixture(tmp_path)
    try:
        manifest = counted(engine)
        before = engine.totals()
        engine.db.execute("UPDATE counts SET input_tokens=1")
        with pytest.raises(module.StateError, match="count_projection_changed"):
            engine.reserve(manifest)
        assert engine.totals() == before
    finally:
        engine.close()
