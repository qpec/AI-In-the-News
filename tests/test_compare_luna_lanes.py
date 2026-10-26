"""Synthetic offline comparisons, including immutable-source binding failures."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.storage import prepare_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import compare_luna_lanes as comparison
    import lean_luna_state as state
    import luna_event_contract_v2 as contract
finally:
    sys.path.pop(0)


def test_uniform_projection_preserves_raw_and_separates_denominators():
    packet, valid = contract.fictional_example()
    recoverable = deepcopy(valid)
    recoverable["event"]["action"]["refs"] = ["p1", "p2"]
    original = deepcopy(recoverable)
    rows = []
    for identity, output, status, complete, technical in (
        ("good", valid, "valid", True, False),
        ("refs", recoverable, "invalid", True, False),
        ("unknown", valid, "unknown", False, True),
    ):
        check = comparison.assess_output(packet, output, completed=complete,
            technical_failure=technical, saved_status=status, saved_errors=[])
        rows.append(comparison.comparison_row({"_record_id": identity, "status": status,
            "human_validated": False, "accepted": False}, packet, output, check,
            lane="synthetic", identity=identity, packet_ref="packet", response_ref="response"))
    result = comparison.summarize(rows)
    assert result["raw_statuses"] == {"valid": 1, "invalid": 1, "unknown": 1}
    assert result["derived_statuses"] == {"valid": 2, "unknown": 1}
    assert result["raw_pass_percent_all_attempts"] == 33.3333
    assert result["raw_pass_percent_content_evaluable"] == 50
    assert result["derived_pass_percent_all_attempts"] == 66.6667
    assert result["recovered_by_projection"] == 1 and result["human_validated"] == 0
    assert recoverable == original


def test_transport_failure_cannot_pass_even_if_saved_valid():
    packet, output = contract.fictional_example()
    check = comparison.assess_output(packet, output, completed=False, technical_failure=True,
        saved_status="valid", saved_errors=["response:transport_not_completed"])
    assert check["raw_status"] == check["derived_status"] == "error"
    assert not check["status_matches_saved"] and check["projection"] is None


def make_fixture(tmp_path):
    packet, output = contract.fictional_example()
    dbs = []
    def store(name):
        owner = tmp_path / name
        prepare_root(owner)
        (owner / "objects").mkdir()
        db = sqlite3.connect(owner / "research.sqlite3")
        dbs.append(db)
        db.execute("CREATE TABLE records(id TEXT,kind TEXT,logical_key TEXT,payload TEXT,artifact TEXT,supersedes TEXT,created_event INTEGER)")
        def artifact(value):
            raw = state.canonical(value).encode()
            ref = hashlib.sha256(raw).hexdigest()
            (owner / "objects" / ref).write_bytes(raw)
            return ref
        def record(kind, key, value):
            ref = artifact(value)
            identifier = state.digest({"kind": kind, "key": key, "payload": ref, "supersedes": None})
            db.execute("INSERT INTO records VALUES (?,?,?,?,?,?,?)", (identifier, kind, key, state.canonical(value), ref, None, 1))
            return {**value, "_record_id": identifier, "_logical_key": key}
        return owner, artifact, record
    batch, artifact, record = store("batch")
    rows, requests = [], []
    for corpus in ("incident-reports", "cybercrime"):
        packet_ref = artifact(packet)
        body_ref = artifact({"model": "gpt-6-luna", "reasoning": {"effort": "none"}, "max_output_tokens": 4096,
            "instructions": contract.load_prompt(), "input": [{"content": [{"text": state.canonical({
                k: v for k, v in packet["model_input"].items() if k != "instructions"})}]}],
            "text": {"format": {"schema": contract.load_schema()}}})
        response_ref = artifact({"packet_ref": packet_ref if corpus == "incident-reports" else None, "custom_id": corpus, "status": "valid", "result": output,
            "provider_status": "completed", "technical_failure": False})
        manifest = record("luna_budget_dispatch_manifest", corpus, {"plan": "batch-plan", "tasks": [{
            "custom_id": corpus, "corpus_id": corpus, "packet_ref": packet_ref, "request_body_ref": body_ref}]})["_record_id"]
        rows.append(record("luna_budget_assessment", corpus, {"plan": "batch-plan", "corpus_id": corpus,
            "custom_id": corpus, "status": "valid", "packet_ref": packet_ref, "request": body_ref,
            "response": response_ref, "manifest": manifest, "errors": [], "human_validated": False, "accepted": False}))
        requests.append({"custom_id": corpus, "corpus_id": corpus, "packet_ref": packet_ref,
            "request_body_ref": body_ref, "descriptor": {"contract_sha256": contract.contract_digest(),
                "retained_body_sha256": packet["source_map"]["source_fields"]["body"]["sha256"]}})
    codex, artifact, record = store("codex")
    packet_ref = artifact({"packet": packet, "source_version": "source", "body_sha256": packet["source_map"]["source_fields"]["body"]["sha256"]})
    plan = record("luna_fast_plan", "plan", {"config": {}, "tasks": [{"task_key": "task", "packet": packet_ref}]})["_record_id"]
    response_ref = artifact({"payload": output, "provider": "synthetic", "model": "gpt-6-luna",
        "raw_response": {"packet": packet, "transport_status": "returned", "events": [{"type": "turn.completed"}]}})
    request_ref = artifact({"packet": packet, "schema": contract.load_schema(), "contract_digest": contract.contract_digest()})
    assessment = record("luna_fast_assessment", "attempt", {"plan": plan, "task_key": "task", "source_version": "source",
        "attempt": "attempt", "status": "valid", "request": request_ref, "response": response_ref, "errors": [],
        "human_validated": False, "accepted": False})
    result = record("luna_fast_result", "result", {"plan": plan, "counts": {"valid": 1},
        "outcomes": [{**{k: v for k, v in assessment.items() if not k.startswith("_")}, "assessment": assessment["_record_id"]}]})["_record_id"]
    lean = tmp_path / "lean"
    prepare_root(lean)
    database = lean / "state.sqlite3"
    db = sqlite3.connect(database)
    db.executescript(state.SCHEMA)
    for key, value in {"snapshot_id": "snapshot", "source_owner": str(batch), "plan_id": "batch-plan"}.items():
        db.execute("INSERT INTO meta VALUES (?,?)", (key, state.canonical(value)))
    for request, row in zip(requests, rows, strict=True):
        db.execute("INSERT INTO requests VALUES (?,?,?,?,?,?)", (row["custom_id"], row["corpus_id"], "manifest", 1, "valid", state.canonical(request)))
        db.execute("INSERT INTO results VALUES (?,?,?)", (row["custom_id"], "valid", state.canonical(row)))
    db.commit()
    digest = hashlib.sha256(db.serialize()).hexdigest()
    db.close()
    _, _, checkpoint_record = store("lean/runtime")
    checkpoint_record("lean_luna_checkpoint", "snapshot", {"state_sha256": digest})
    for db in dbs:
        db.commit()
        db.close()
    return {"phase": "compare", "batch_state": str(database), "codex_owner": str(codex), "codex_result": result}, batch, response_ref


@pytest.mark.parametrize("corruption", [None, "checkpoint", "artifact"])
def test_registered_comparison_and_provenance_rejection(tmp_path, corruption, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    payload, batch, _ = make_fixture(tmp_path)
    if corruption == "checkpoint":
        with sqlite3.connect(payload["batch_state"]) as db:
            db.execute("UPDATE results SET status='invalid'")
    if corruption == "artifact":
        path = next((batch / "objects").iterdir())
        path.write_bytes(path.read_bytes() + b" ")
    before = (batch / "research.sqlite3").read_bytes()
    engine = comparison.ComparisonResearch(tmp_path / "comparison", config=Config(offline=True))
    try:
        if corruption:
            with pytest.raises((AuditError, state.StateError)):
                engine.execute("status", payload, objective="Synthetic comparison failure", actor="test")
        else:
            result = engine.execute("status", payload, objective="Synthetic retained comparison", actor="test")
            assert result["lanes"]["codex-incident-reports"]["raw_statuses"] == {"valid": 1}
            assert result["overlap"]["incident-reports"]["shared_exact_body_hashes"] == 1
            assert result["model_calls"] == 0 and not result["semantic_accuracy_confirmed"]
            assert result["batch_parsed_packet_refs_missing"] == 1
            assert Path(result["report_path"]).is_file()
            assert json.loads(engine.ledger.artifacts.read_bytes(result["details_artifact"]))["originals_unchanged"]
    finally:
        engine.close()
    assert (batch / "research.sqlite3").read_bytes() == before
