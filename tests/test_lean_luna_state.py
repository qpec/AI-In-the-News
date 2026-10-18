"""Small operational snapshots only; no Research, provider or production owner."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

import pytest

spec = importlib.util.spec_from_file_location("lean_luna_state", Path(__file__).resolve().parents[1] / "scripts/lean_luna_state.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    owner = tmp_path / "legacy"
    objects = owner / "objects"
    objects.mkdir(parents=True)
    connection = sqlite3.connect(owner / "research.sqlite3")
    connection.execute("CREATE TABLE records(id TEXT PRIMARY KEY,kind TEXT,logical_key TEXT,payload TEXT,artifact TEXT,supersedes TEXT,created_event INTEGER)")
    def artifact(value: Any) -> str:
        raw = value if isinstance(value, bytes) else module.canonical(value).encode()
        reference = hashlib.sha256(raw).hexdigest()
        (objects / reference).write_bytes(raw)
        return reference
    sequence = 0
    def record(kind: str, key: str, value: dict[str, Any]) -> str:
        nonlocal sequence
        sequence += 1
        reference = artifact(value)
        identifier = module.digest({"kind": kind, "key": key, "payload": reference, "supersedes": None})
        connection.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, kind, key, module.canonical(value), reference, None, sequence))
        return identifier
    price = {"model": "gpt-6-luna", "input_nanousd_per_million": 100_000_000,
        "cache_write_nanousd_per_million": 125_000_000, "output_nanousd_per_million": 500_000_000,
        "batch_multiplier": [1, 2], "regional_multiplier": [11, 10], "long_input_multiplier": [2, 1],
        "long_output_multiplier": [3, 2], "long_context_threshold": 272000,
        "source_url": "https://example.invalid/synthetic", "observed_at": "2026-10-18T00:00:00Z"}
    bodies = {custom: {"model": "gpt-6-luna", "instructions": "Fictional extraction", "input": custom,
        "max_output_tokens": 4096} for custom in ("r1", "r2", "r3")}
    body_refs = {custom: artifact(body) for custom, body in bodies.items()}
    corpora = {}
    for corpus, ids in (("incident-reports", ["r1", "r3", "future1"]), ("cybercrime", ["r2", "future2"])):
        corpora[corpus] = {"manifest_sha256": module.digest(corpus),
            "queue_ref": artifact({"corpus_id": corpus, "manifest_sha256": module.digest(corpus), "items": [{"custom_id": key} for key in ids]}),
            "preparation_export_ref": artifact({"synthetic_export": corpus}), "partition": {"corpus_id": corpus}}
    auth = "synthetic-authorization"
    plan = record("luna_budget_execution_plan", "plan", {"authorization_id": auth, "corpora": corpora,
        "price_policy": price, "price_fingerprint": module.digest(price), "versions": {}})
    policy = record("policy", "policy", {"content": {"authorization_id": auth, "plan_ids": [plan],
        "ceiling_nanousd": module.HARD_CAP, "operational_limit_nanousd": module.OPERATING_CAP}})
    record("luna_budget_throughput_run", "run", {"plan": plan, "authorization_id": auth, "deadline_epoch": 1000})
    manifests = {}
    tasks = {}
    for custom, corpus in (("r1", "incident-reports"), ("r2", "cybercrime"), ("r3", "incident-reports")):
        request = {"custom_id": custom, "method": "POST", "url": "/v1/responses", "body": bodies[custom]}
        task = {"custom_id": custom, "corpus_id": corpus, "row_id": "row-" + custom,
            "request_body_ref": body_refs[custom], "request_ref": artifact(request), "packet_ref": artifact({"synthetic_packet": custom}), "descriptor": {}}
        tasks[custom] = task
        manifests[custom] = record(module.MANIFEST, "manifest-" + custom, {"plan": plan, "authorization_id": auth,
            "corpus_id": corpus, "phase": "bulk", "tasks": [task], "attempt_ids": ["attempt-" + custom],
            "jsonl_ref": artifact(module.canonical(request).encode() + b"\n")})
    def action(identifier: str, phase: str, response: dict[str, Any], request: dict[str, Any], *, reserved: list[str] | None = None) -> str:
        exact = artifact({"logical_request": request, "original_body_ref": count_body if phase == "count" else None})
        record(module.ACTION, identifier, {"authorization_id": auth, "plan_id": plan, "policy_id": policy,
            "action_id": identifier, "phase": phase, "reserved_request_ids": reserved or [],
            "logical_hash": module.digest(identifier), "exact_request_ref": exact})
        ref = artifact(response)
        return record(module.RECEIPT, identifier, {"authorization_id": auth, "plan_id": plan,
            "action_id": identifier, "phase": phase, "unknown": False, "status": 200, "error_type": None,
            "body_ref": ref, "body_sha256": ref, "received_at": "2026-10-18T00:00:00Z"})
    count_body = artifact({key: bodies["r3"][key] for key in ("model", "instructions", "input")})
    for custom, started, ended in (("r1", 100, 130), ("r2", 200, 260)):
        job = "batch-" + custom
        receipt = action("create-" + custom, "create", {"id": job, "created_at": started, "status": "validating"},
            {"method": "POST", "path": "/v1/batches"}, reserved=[custom])
        record(module.JOB, manifests[custom], {"plan": plan, "manifest": manifests[custom], "corpus_id": tasks[custom]["corpus_id"],
            "job_id": job, "receipt": receipt, "request_count": 1})
        record("luna_budget_job_reconciled", manifests[custom], {"plan": plan, "manifest": manifests[custom], "reconciled": True})
        action("poll-" + custom, "poll", {"id": job, "created_at": started, "completed_at": ended, "status": "completed"},
            {"method": "GET", "path": "/v1/batches/" + job})
        record(module.ASSESSMENT, custom, {"plan": plan, "custom_id": custom, "corpus_id": tasks[custom]["corpus_id"],
            "manifest": manifests[custom], "request": body_refs[custom], "status": "valid" if custom == "r1" else "error",
            "response": artifact({"synthetic_result": custom}), "accepted": False})
    count_receipt = action("count-r3", "count", {"input_tokens": 77}, {"method": "POST", "path": "/v1/responses/input_tokens"})
    record("luna_batch_count_consumer", "r3", {"authorization_id": auth, "plan_id": plan, "custom_id": "r3",
        "corpus_id": "incident-reports", "request_body_ref": body_refs["r3"], "count_body_ref": count_body,
        "origin_action_id": "count-r3", "origin_receipt_id": count_receipt,
        "provider_count_body_sha256": artifact({"input_tokens": 77}), "input_tokens": 77})
    events = []
    for custom, tokens in (("r1", 100), ("r2", 4015), ("r3", 77)):
        events.append({"action": "reserve", "value": {"request_id": custom, "task_id": custom,
            "corpus_id": tasks[custom]["corpus_id"], "plan_id": plan, "request_sha256": body_refs[custom],
            "max_output_tokens": 4096, "price_fingerprint": module.digest(price), "input_count": {
                "model": "gpt-6-luna", "input_tokens": tokens, "method": "provider_responses_input_tokens",
                "request_sha256": body_refs[custom], "receipt_sha256": artifact({"input_tokens": tokens})}}})
    events.extend([{"action": "settle", "value": {"request_id": "r1", "usage": {"complete": True,
        "input_tokens": 100, "output_tokens": 20, "model": "gpt-6-luna", "request_sha256": body_refs["r1"]}}},
        {"action": "settle", "value": {"request_id": "r2", "usage": None}}])
    state = {"config": {"method": "event-batch-shared-budget-v1", "authorization_id": auth, "price_policy": price,
        "ceiling_nanousd": module.HARD_CAP, "operational_limit_nanousd": module.OPERATING_CAP}, "events": events}
    budget_summary = {"authorization_id": auth, "state_ref": artifact(state), "price_fingerprint": module.digest(price),
        "charged_nanousd": 12375, "reserved_nanousd": 2534126, "committed_nanousd": 2546501, "frozen": False}
    record(module.BUDGET, auth, budget_summary)
    connection.commit()
    connection.close()
    return owner, {"plan": plan, "authorization": auth, "state": state, "budget_summary": budget_summary, "bodies": body_refs}


def inspect(owner: Path, data: dict[str, Any]) -> dict[str, Any]:
    return module.inspect_legacy(owner, plan_id=data["plan"], authorization_id=data["authorization"], expected_deadline_epoch=1000)


def append(owner: Path, kind: str, value: dict[str, Any], key: str = "extra") -> None:
    connection = sqlite3.connect(owner / "research.sqlite3")
    ref = module.digest(value)
    identifier = module.digest({"kind": kind, "key": key, "payload": ref, "supersedes": None})
    connection.execute("INSERT INTO records VALUES (?,?,?,?,?,?,9999)", (identifier, kind, key, module.canonical(value), ref, None))
    connection.commit()
    connection.close()


def test_read_only_snapshot_current_costs_ids_corpora_and_provider_timing(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    before = (owner / "research.sqlite3").read_bytes()
    snapshot = inspect(owner, data)
    assert snapshot["blockers"] == []
    assert snapshot["summary"]["submitted_requests"] == snapshot["summary"]["assessed_requests"] == 2
    assert snapshot["summary"]["staged_requests"] == snapshot["summary"]["counted_staged_requests"] == 1
    assert snapshot["budget"]["charged_nanousd"] == 12375
    assert snapshot["budget"]["entries"]["r2"]["status"] == "unknown"
    assert snapshot["budget"]["entries"]["r2"]["reserved_nanousd"] == 1402432
    assert snapshot["summary"]["provider_turnaround"]["median_seconds"] == 45
    assert snapshot["summary"]["provider_turnaround"]["p90_nearest_rank_seconds"] == 60
    assert snapshot["results"]["r2"]["accepted"] is False
    assert set(snapshot["corpora"]) == module.CORPORA and snapshot["deadline_epoch"] == 1000
    assert (owner / "research.sqlite3").read_bytes() == before
    connection = module.read_only_database(owner)
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM records")
    connection.close()


def test_equal_action_receipt_counts_do_not_hide_missing_and_duplicate_identities(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    connection = sqlite3.connect(owner / "research.sqlite3")
    row = json.loads(connection.execute("SELECT payload FROM records WHERE kind=? AND logical_key='count-r3'", (module.RECEIPT,)).fetchone()[0])
    connection.execute("DELETE FROM records WHERE kind=? AND logical_key='count-r3'", (module.RECEIPT,))
    connection.commit()
    connection.close()
    row["action_id"] = "poll-r1"
    append(owner, module.RECEIPT, row)
    # The staged consumer cannot be safely reconstructed when its receipt vanished.
    with pytest.raises((module.StateError, KeyError)):
        inspect(owner, data)


@pytest.mark.parametrize("mode", ["orphan", "unknown", "gateway_stop"])
def test_operational_uncertainty_remains_blocking(tmp_path: Path, mode: str) -> None:
    owner, data = fixture(tmp_path)
    if mode == "gateway_stop":
        append(owner, "event_batch_live_stop", {"authorization_id": data["authorization"], "reason": "synthetic"})
    else:
        append(owner, module.RECEIPT, {"authorization_id": data["authorization"], "plan_id": data["plan"],
            "action_id": "not-dispatched", "phase": "poll", "status": 200, "unknown": mode == "unknown",
            "body_ref": module.digest({}), "body_sha256": module.digest({}), "error_type": None})
    assert inspect(owner, data)["blockers"]


@pytest.mark.parametrize("change", ["total", "cap", "price", "duplicate_reserve", "wrong_plan"])
def test_current_budget_conversion_rejects_changes(tmp_path: Path, change: str) -> None:
    _, data = fixture(tmp_path)
    state, summary = deepcopy(data["state"]), deepcopy(data["budget_summary"])
    if change == "total":
        summary["reserved_nanousd"] = 0
    elif change == "cap":
        state["config"]["operational_limit_nanousd"] = module.OPERATING_CAP + 1
    elif change == "price":
        state["config"]["price_policy"]["output_nanousd_per_million"] = 1
    elif change == "duplicate_reserve":
        state["events"].append(state["events"][0])
    else:
        state["events"][0]["value"]["plan_id"] = "different"
    with pytest.raises(module.StateError):
        module.fold_budget(state, summary, data["plan"], data["authorization"])


def test_selected_staged_artifact_tamper_rejected(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    (owner / "objects" / data["bodies"]["r3"]).write_bytes(b"changed")
    with pytest.raises(module.StateError, match="artifact_hash"):
        inspect(owner, data)


def test_duplicate_paid_custom_id_rejected(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    append(owner, module.ACTION, {"authorization_id": data["authorization"], "plan_id": data["plan"], "phase": "create",
        "action_id": "second-paid-attempt", "reserved_request_ids": ["r1"]})
    with pytest.raises(module.StateError, match="duplicate_or_empty_paid"):
        inspect(owner, data)


def test_import_is_once_owned_and_never_resets_progress(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    snapshot = inspect(owner, data)
    target = tmp_path / "lean" / "state.sqlite3"
    with pytest.raises(module.StateError, match="stopped_required"):
        module.import_snapshot(snapshot, target)
    with pytest.raises(module.StateError, match="legacy_owner"):
        module.import_snapshot(snapshot, owner / "new.sqlite3", source_execution_stopped=True)
    with module.StateLock(target):
        with pytest.raises(module.StateError, match="already_owned"):
            module.import_snapshot(snapshot, target, source_execution_stopped=True)
    result = module.import_snapshot(snapshot, target, source_execution_stopped=True)
    with sqlite3.connect(target) as connection:
        held = json.loads(connection.execute("SELECT value FROM meta WHERE key='imported_unknown_entry_hashes'").fetchone()[0])
    assert held == {"r2": module.digest(snapshot["budget"]["entries"]["r2"])}
    assert result["new_inference_authorized"] is False
    connection = sqlite3.connect(target)
    assert connection.execute("SELECT reserved_nanousd FROM budget_entries WHERE custom_id='r2'").fetchone()[0] == 1402432
    assert connection.execute("SELECT SUM(submitted) FROM requests").fetchone()[0] == 2
    connection.execute("UPDATE requests SET status='future-progress' WHERE custom_id='r3'")
    connection.commit()
    assert module.import_snapshot(snapshot, target, source_execution_stopped=True)["reused"] is True
    assert connection.execute("SELECT status FROM requests WHERE custom_id='r3'").fetchone()[0] == "future-progress"
    changed = {**snapshot, "inspected_at": "different"}
    changed["snapshot_id"] = module.digest({key: value for key, value in changed.items() if key != "snapshot_id"})
    with pytest.raises(module.StateError, match="different_snapshot"):
        module.import_snapshot(changed, target, source_execution_stopped=True)
    connection.close()


def test_deadline_cannot_be_reset(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    with pytest.raises(module.StateError, match="deadline_mismatch"):
        module.inspect_legacy(owner, plan_id=data["plan"], authorization_id=data["authorization"], expected_deadline_epoch=2000)


def append_budget(owner: Path, data: dict[str, Any], state: dict[str, Any], *, charged: int, reserved: int) -> None:
    reference = module.digest(state)
    (owner / "objects" / reference).write_text(module.canonical(state), encoding="utf-8")
    summary = {**data["budget_summary"], "state_ref": reference, "charged_nanousd": charged,
        "reserved_nanousd": reserved, "committed_nanousd": charged + reserved}
    append(owner, module.BUDGET, summary, data["authorization"])


def test_submitted_request_cannot_lose_its_budget_entry(tmp_path: Path) -> None:
    owner, data = fixture(tmp_path)
    state = deepcopy(data["state"])
    state["events"] = [event for event in state["events"] if event["value"]["request_id"] != "r1"]
    append_budget(owner, data, state, charged=0, reserved=2534126)
    with pytest.raises(module.StateError, match="submitted_request_without_budget_entry"):
        inspect(owner, data)


@pytest.mark.parametrize("status", ["settled", "unknown", "confirmed_unprocessed"])
def test_unsubmitted_request_cannot_have_nonreserved_budget_status(tmp_path: Path, status: str) -> None:
    owner, data = fixture(tmp_path)
    state = deepcopy(data["state"])
    charged, reserved = 12375, 2534126
    if status == "confirmed_unprocessed":
        state["events"].append({"action": "confirm_unprocessed", "value": {"request_id": "r3",
            "confirmed_unprocessed": True, "confirmation_sha256": "a" * 64, "provider_request_id": "fictional"}})
        reserved -= 1131694
    else:
        usage = None
        if status == "settled":
            usage = {"complete": True, "model": "gpt-6-luna", "input_tokens": 77, "output_tokens": 20,
                "request_sha256": data["bodies"]["r3"]}
            charged += 10794
            reserved -= 1131694
        state["events"].append({"action": "settle", "value": {"request_id": "r3", "usage": usage}})
    append_budget(owner, data, state, charged=charged, reserved=reserved)
    with pytest.raises(module.StateError, match="nonreserved_budget_entry_without_submitted_create"):
        inspect(owner, data)
