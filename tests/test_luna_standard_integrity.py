"""Concurrent-owner snapshots and artifact corruption checks using fixtures."""
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
import test_luna_speed_workflow as prior
from test_luna_standard_corpus import FixtureCorpus

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
try:
    import check_luna_standard_integrity as check
finally:
    sys.path.pop(0)


class BoundFixture(FixtureCorpus):
    def read_inputs(self, session, data):
        values = super().read_inputs(session, data)
        packet, _ = check.contract.fictional_example()
        for queue in values[0].values():
            for descriptor in queue:
                descriptor["retained_body_sha256"] = packet["source_map"]["source_fields"]["body"]["sha256"]
        return values


def test_incremental_mechanical_replay_and_corrupt_artifact_fails(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    prior.mock_runner(monkeypatch)
    source = BoundFixture(tmp_path / "source", config=Config(offline=True))
    verifier = check.IntegrityResearch(tmp_path / "check", config=Config(offline=True))
    try:
        plan = prior.call(source, "status", {"phase": "prepare"})
        source.config = replace(source.config, offline=False)
        prior.call(source, "status", {"phase": "run", "plan": plan["id"], "authorization_text": "Synthetic full corpus"})
        inputs = {"source_owner": str(source.ledger.root), "plan": plan["id"]}
        # Source runtime stays open and locked: independent checker uses one
        # read-only SQLite snapshot, not a competing Research writer.
        first = prior.call(verifier, "status", inputs)
        assert first["integrity_passed"] and first["new_results_verified"] == 12
        assert first["unattempted"] == 0 and not first["semantic_accuracy_confirmed"]
        repeated = prior.call(verifier, "status", inputs)
        assert repeated["new_results_verified"] == repeated["new_events_verified"] == 0
        assert repeated["head_hash"] == first["head_hash"]
        row = source.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_standard_assessment' LIMIT 1").fetchone()
        value = json.loads(row[0])
        artifact = source.ledger.artifacts.root / value["response"]
        original = artifact.read_bytes()
        artifact.write_bytes(original + b" ")
        fresh = check.IntegrityResearch(tmp_path / "fresh-check", config=Config(offline=True))
        try:
            with pytest.raises((AuditError, check.state.StateError), match="hash_mismatch"):
                prior.call(fresh, "status", inputs)
            assert fresh.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='luna_integrity_checkpoint'").fetchone()[0] == 0
        finally:
            fresh.close()
            artifact.write_bytes(original)
    finally:
        verifier.close()
        source.close()
