"""Synthetic capacity and provenance checks. No model or corpus access."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from newsresearch.common import AuditError, Config, ResearchError, digest
from newsresearch.gateway import ProviderResponse
from newsresearch.luna_fast_gateway import FastGateway, improvement
from newsresearch.runtime import Research, audited_handler
from newsresearch.storage import prepare_root

import test_luna_speed_workflow as prior
from test_luna_speed_gateway import Harness

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_fast_iteration as fast
finally:
    sys.path.pop(0)


def clean():
    return ProviderResponse({"valid": True}, "synthetic", None, raw_response={
        "transport_status": "returned", "failure": None, "unknown_outcome": False})


class FixtureFast(fast.FastResearch, prior.FixtureResearch):
    def batch_exclusions(self, session, database):
        self.cross_lane_snapshot = {"body_hashes": [], "synthetic": True}
        return self.cross_lane_snapshot


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    engine = FixtureFast(tmp_path / "protected", config=Config(offline=True))
    fixture = prior.call(engine, "status", {"fixture": "build"})
    monkeypatch.setattr(fast, "ORIGINAL_RESULT", fixture["original_result"])
    monkeypatch.setattr(fast, "STOPPED_PLAN", fixture["stopped_plan"])
    monkeypatch.setattr(fast, "load_frame", lambda *args: {"metadata": fixture["metadata"], "frame": fixture["frame"]})
    partition = {"corpus_id": "incident-reports",
                 "file_sha256": {"corpora/incident-reports/manifest.json": "b" * 64},
                 "manifests": {"incident-reports": {"bundles": [{"path": "fictional.zip", "sha256": "a" * 64}]},
                               "cybercrime": {"bundles": []}}}
    monkeypatch.setattr(fast, "partition_binding", lambda path: partition)
    plan = prior.call(engine, "luna_group_validation", {"phase": "prepare", "queue_limit": 6,
                      "data_root": str(tmp_path / "fictional"), "batch_state": "synthetic"})
    try:
        yield engine, plan
    finally:
        engine.close()


def test_full_fast_workflow_binds_tier_records_results_and_forbids_restart(prepared, monkeypatch):
    engine, plan = prepared
    seen = prior.mock_runner(monkeypatch)
    assert plan["model_calls"] == 0 and len(plan["tasks"]) == 6
    assert plan["limits"]["service_tier"] == "fast"
    with pytest.raises(ResearchError, match="plan_exists"):
        prior.call(engine, "luna_group_validation", {"phase": "prepare", "queue_limit": 6,
                   "data_root": "synthetic", "batch_state": "synthetic"})
    engine.config = replace(engine.config, offline=False)
    payload = {"phase": "run", "plan": plan["id"], "batch_state": "synthetic",
               "authorization_text": "Run the synthetic Fast fixture only"}
    result = prior.call(engine, "luna_group_validation", payload)
    assert result["counts"] == {"valid": 6}
    assert result["pending"] == 0 and len(seen) == 6
    for row in engine.ledger.db.execute("SELECT payload FROM events WHERE kind='model.attempt.intended'"):
        intended = json.loads(row[0])
        manifest = engine.ledger.artifacts.read(intended["dispatch"])
        assert manifest["configured_service_tier"] == "fast"
        assert 'service_tier="fast"' in manifest["command"]
        assert "features.fast_mode=true" in manifest["command"]
        assert manifest["provider_output_token_cap"] is None
    assert all(r["observed_service_tiers"] == [] for r in result["outcomes"])
    report = prior.call(engine, "luna_group_validation", {"phase": "report", "result": result["id"]})
    assert report["markdown"] == result["markdown"] and len(seen) == 6
    with pytest.raises(ResearchError, match="spent_no_restart"):
        prior.call(engine, "luna_group_validation", payload)
    engine.ledger.verify()


def test_unknown_canary_stops_and_remains_spent(prepared, monkeypatch):
    engine, plan = prepared
    seen = prior.mock_runner(monkeypatch, unknown=True)
    engine.config = replace(engine.config, offline=False)
    result = prior.call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
                      "batch_state": "synthetic", "authorization_text": "Synthetic unknown fixture"})
    assert len(seen) == 1 and result["counts"] == {"unknown": 1}
    assert result["pending"] == 5 and result["timing"]["stop_reason"] == "transport_or_unknown_stop"
    assert len(engine.ledger.unresolved) == 1


def test_failed_response_storage_does_not_dispatch_more_work(prepared, monkeypatch):
    engine, plan = prepared
    seen = prior.mock_runner(monkeypatch)
    saved = fast.save

    def fail_response(engine, session, value, purpose):
        if purpose == "Exact permitted Codex response before validation":
            raise AuditError("synthetic_disk_failure")
        return saved(engine, session, value, purpose)

    monkeypatch.setattr(fast, "save", fail_response)
    engine.config = replace(engine.config, offline=False)
    with pytest.raises(AuditError, match="synthetic_disk_failure"):
        prior.call(engine, "luna_group_validation", {"phase": "run", "plan": plan["id"],
                   "batch_state": "synthetic", "authorization_text": "Synthetic storage failure fixture"})
    assert len(seen) == 1 and len(engine.ledger.unresolved) == 1


def test_batch_hash_exclusion_and_body_deduplication():
    inputs = list(prior.selection_inputs())
    result = fast.freeze_selection(*inputs, 2000, prior_batch={"eligible_b"})
    assert result["selected"] == ["eligible_a"]
    assert result["exclusions"]["eligible_b"] == "prior_batch_reserved_or_attempted"
    inputs[1]["eligible_b"]["body_sha256"] = inputs[1]["eligible_a"]["body_sha256"]
    result = fast.freeze_selection(*inputs, 2000)
    assert len(result["selected"]) == 1
    assert result["exclusion_counts"]["duplicate_body_in_queue"] == 1
    result = fast.freeze_selection(*inputs, 2000, prior_speed={"eligible_a"})
    assert result["selected"] == []
    assert result["exclusion_counts"]["prior_speed_attempt"] == 2


def test_eight_workers_overlap_after_two_sequential_canaries():
    lock, release = threading.Lock(), threading.Event()
    active = peak = 0
    completed = []

    def complete(call):
        nonlocal active, peak
        index = call.request["index"]
        with lock:
            if index < 2:
                assert len(completed) == index and active == 0
            else:
                assert {0, 1} <= set(completed)
            active += 1
            peak = max(peak, active)
            if active == 8:
                release.set()
        if index >= 2:
            assert release.wait(timeout=3)
        with lock:
            active -= 1
            completed.append(index)
        return clean()

    harness = Harness(count=18, provider=SimpleNamespace(complete_prepared=complete))
    harness.gateway = FastGateway(harness.engine, harness.gateway.provider)
    result = harness.run(widths=(8,), cap=18)
    assert peak == result["peak_in_flight"] == 8
    assert len(set(completed)) == 18 and result["canaries_returned"] == 2


def test_deadline_stops_admission_and_retains_late_success():
    def complete(call):
        time.sleep(.08)
        return clean()
    harness = Harness(count=3, provider=SimpleNamespace(complete_prepared=complete))
    harness.gateway = FastGateway(harness.engine, harness.gateway.provider)
    result = harness.run(seconds=.03, drain_seconds=.15, widths=(1,), canaries=0)
    assert result["submitted"] == 1 and result["stop_reason"] == "admission_deadline"
    assert result["observations"][0]["mechanically_valid"]
    assert not result["observations"][0]["valid_persisted_within_window"]
    assert result["elapsed_seconds"] >= .08


def test_ramp_attributes_each_dispatch_and_requires_useful_gain():
    def complete(call):
        time.sleep(.01)
        return clean()
    harness = Harness(count=8, provider=SimpleNamespace(complete_prepared=complete))
    harness.gateway = FastGateway(harness.engine, harness.gateway.provider)
    result = harness.run(widths=(1, 2), canaries=0, stage_seconds=.005, min_returns=1)
    assert [s["workers"] for s in result["stages"][:2]] == [1, 2]
    assert result["peak_in_flight"] <= 2 and result["submitted"] == 8
    assert all(r["stage"] >= 0 for r in result["observations"])
    base = {"valid_per_minute": 20., "valid_fraction": .8, "p95_seconds": 1.}
    assert improvement({**base, "valid_per_minute": 24.}, base)
    assert not improvement({**base, "valid_per_minute": 22.}, base)
    assert not improvement({**base, "valid_per_minute": 40., "valid_fraction": .7}, base)
    assert not improvement({**base, "valid_per_minute": 40., "p95_seconds": 2.}, base)


class RecordFixture(Research):
    @audited_handler
    def _status(self, session, context, data):
        return self.ledger.record(session, data["kind"], data["key"], data["value"])


class CrossLaneFixture(fast.FastResearch):
    @audited_handler
    def _status(self, session, context, data):
        self._version(session, context, {"kind": "protocol", "key": "synthetic-cross-lane",
                      "content": {"method": "synthetic-cross-lane-exclusion"}})
        return self.batch_exclusions(session, data["state"])


def test_locked_checkpoint_and_legacy_manifest_exclusions(tmp_path):
    owner, lean = tmp_path / "legacy", tmp_path / "lean"
    with_owner = RecordFixture(owner, config=Config(offline=True))
    try:
        prior.call(with_owner, "status", {"kind": "luna_budget_dispatch_manifest", "key": "synthetic",
                   "value": {"tasks": [{"descriptor": {"retained_body_sha256": "a" * 64}}]}})
    finally:
        with_owner.close()
    prepare_root(lean)
    state = lean / "state.sqlite3"
    db = sqlite3.connect(state)
    db.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT); CREATE TABLE requests(payload TEXT);")
    for key, value in {"source_owner": str(owner), "snapshot_id": "synthetic", "blockers": [],
                       "uncertain_action_ids": [], "deadline_epoch": 1234}.items():
        db.execute("INSERT INTO meta VALUES (?,?)", (key, json.dumps(value)))
    db.execute("INSERT INTO requests VALUES (?)", (json.dumps({"descriptor": {"retained_body_sha256": "b" * 64}}),))
    db.commit()
    state_hash = hashlib.sha256(db.serialize()).hexdigest()
    db.close()
    runtime = RecordFixture(lean / "runtime", config=Config(offline=True))
    try:
        prior.call(runtime, "status", {"kind": "lean_luna_checkpoint", "key": "synthetic",
                   "value": {"state_sha256": state_hash}})
    finally:
        runtime.close()
    engine = CrossLaneFixture(tmp_path / "new", config=Config(offline=True))
    try:
        result = prior.call(engine, "status", {"state": str(state)})
        assert result["body_hashes"] == ["a" * 64, "b" * 64]
        assert result["batch_deadline_epoch_preserved"] == 1234
        assert result["legacy_full_history_replayed"] is False
    finally:
        engine.close()
    db = sqlite3.connect(state)
    db.execute("INSERT INTO requests VALUES (?)", (json.dumps({"descriptor": {"retained_body_sha256": digest('changed')}}),))
    db.commit()
    db.close()
    engine = CrossLaneFixture(tmp_path / "second", config=Config(offline=True))
    try:
        with pytest.raises(AuditError, match="not_at_verified_checkpoint"):
            prior.call(engine, "status", {"state": str(state)})
    finally:
        engine.close()
