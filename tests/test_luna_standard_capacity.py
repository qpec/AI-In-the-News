"""Capacity amendment preserves spent identities and guards measured selection."""
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import Config, ResearchError
from newsresearch.runtime import audited_handler
import test_luna_speed_workflow as prior
from test_luna_standard_integrity import BoundFixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import luna_standard_capacity as capacity
    import check_luna_standard_integrity as integrity
finally:
    sys.path.pop(0)


class FixtureCapacity(capacity.CapacityResearch, BoundFixture):
    packets = BoundFixture.packets


def metric(width, rate=30, raw=.65, derived=.8, latency=8, clean=True):
    return {"workers": width, "returned": 100, "derived_per_minute": rate,
        "raw_fraction": raw, "derived_fraction": derived, "p95_seconds": latency, "clean": clean}


@pytest.mark.parametrize("candidate,expected", [
    (metric(6, rate=40), 6), (metric(6, rate=34), 4),
    (metric(6, rate=40, raw=.59), 4), (metric(6, rate=40, derived=.74), 4),
    (metric(6, rate=40, latency=16), 4), (metric(6, rate=40, clean=False), 4)])
def test_conservative_selection(candidate, expected):
    assert capacity.select_width([metric(4), candidate]) == expected


def test_seven_only_wins_with_more_valid_outputs():
    assert capacity.select_width([metric(4), metric(6, 42), metric(7, 41)]) == 6
    assert capacity.select_width([metric(4), metric(6, 42), metric(7, 48)]) == 7


def test_packet_interleaving_preserves_each_corpus_order(monkeypatch):
    def packets(self, session, plan, remaining):
        for key, rows in remaining.items():
            for row in rows:
                yield key, row
    monkeypatch.setattr(capacity.base.CorpusResearch, "packets", packets)
    instance = object.__new__(capacity.CapacityResearch)
    assert list(instance.packets("synthetic", {}, {"cybercrime": [1, 2], "incident-reports": [3, 4, 5]})) == [
        ("cybercrime", 1), ("incident-reports", 3), ("cybercrime", 2), ("incident-reports", 4), ("incident-reports", 5)]


def test_amendment_preserves_old_unknown_and_never_redispatches(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    old = BoundFixture(tmp_path / "source", config=Config(offline=True))
    old_seen = prior.mock_runner(monkeypatch, unknown=True)
    prepared = prior.call(old, "status", {"phase": "prepare"})
    old.config = replace(old.config, offline=False)
    stopped = prior.call(old, "status", {"phase": "run", "plan": prepared["id"], "authorization_text": "Original synthetic full queues"})
    assert 0 < stopped["reserved"] < 12
    old.close()
    monkeypatch.undo()
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    new_seen = prior.mock_runner(monkeypatch)
    engine = FixtureCapacity(tmp_path / "source", config=Config(offline=True))
    verifier = integrity.IntegrityResearch(tmp_path / "check", config=Config(offline=True))
    try:
        amendment = prior.call(engine, "status", {"phase": "amend", "plan": prepared["id"], "authorization_text": "Test two and three additional workers"})
        parent = engine.ledger.get(prepared["id"], "luna_standard_plan")
        amended = engine.ledger.get(amendment["id"], "luna_standard_plan")
        assert amended["queues"] == parent["queues"] and amended["max_attempts"] == parent["max_attempts"]
        assert amended["capacity_lineage"] == [prepared["id"]]
        engine.config = replace(engine.config, offline=False)
        payload = {"phase": "run", "plan": amendment["id"], "authorization_text": "Synthetic full queues plus capacity test"}
        result = prior.call(engine, "status", payload)
        assert result["reserved"] == 12 and len(old_seen) + len(new_seen) == 12
        assert result["unknown_holds"] == stopped["unknown_holds"]
        report = prior.call(verifier, "status", {"source_owner": str(engine.ledger.root), "plan": amendment["id"]})
        assert report["integrity_passed"] and report["reserved"] == 12 and report["unattempted"] == 0
        prior.call(engine, "status", payload)
        assert len(old_seen) + len(new_seen) == 12
        with pytest.raises(ResearchError, match="already_exists"):
            prior.call(engine, "status", {"phase": "amend", "plan": prepared["id"], "authorization_text": "same"})
        engine.ledger.verify()
    finally:
        verifier.close()
        engine.close()


def test_each_stage_once_and_incomplete_stage_not_replayed(tmp_path):
    class StageHarness(capacity.CapacityResearch):
        @audited_handler
        def _status(self, session, context, data):
            stage, width, seconds = self.next_stage(session, "synthetic")
            if data.get("finish") and stage:
                self.ledger.record(session, "luna_capacity_stage_result", stage, {
                    "plan": "synthetic", "stage_id": stage, **metric(width, rate={4: 30, 6: 42, 7: 41}[width])})
            return {"stage": stage, "workers": width, "seconds": seconds}
    engine = StageHarness(tmp_path / "stages", config=Config(offline=True))
    try:
        for width in (4, 6, 7):
            value = prior.call(engine, "status", {"finish": True})
            assert value["workers"] == width and value["seconds"] == 180
        value = prior.call(engine, "status", {})
        assert value == {"stage": None, "workers": 6, "seconds": 600}
        intents = [json.loads(row[0]) for row in engine.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_capacity_stage_intent'")]
        assert len(intents) == 3
    finally:
        engine.close()
    partial = StageHarness(tmp_path / "partial", config=Config(offline=True))
    try:
        assert prior.call(partial, "status", {})["workers"] == 4
        assert prior.call(partial, "status", {}) == {"stage": None, "workers": 4, "seconds": 600}
    finally:
        partial.close()
