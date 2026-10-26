"""Synthetic exact-body/corpus joins, read-only inspection and review provenance."""
from dataclasses import replace
from pathlib import Path
import sys

import pytest

from newsresearch.common import AuditError, Config
from newsresearch.runtime import Research, audited_handler
import test_luna_speed_workflow as prior
from test_luna_standard_integrity import BoundFixture

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import inspect_luna_pair_features as scan


class Seed(Research):
    @audited_handler
    def _status(self, session, context, data):
        value = data["value"]
        if data["kind"] == "luna_lane_comparison":
            value = {"details_artifact": self.ledger.artifacts.put({"rows": {}})}
        return self.ledger.record(session, data["kind"], "synthetic", value)


def test_exact_join_coverage_handoff_and_corruption(tmp_path, monkeypatch):
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(key, raising=False)
    prior.mock_runner(monkeypatch)
    source = BoundFixture(tmp_path / "luna-standard-full-corpus-20261018-v2", config=Config(offline=True))
    review = scan.Inspection(tmp_path / "review", config=Config(offline=True))
    try:
        plan = prior.call(source, "status", {"phase": "prepare"})
        source.config = replace(source.config, offline=False)
        prior.call(source, "status", {"phase": "run", "plan": plan["id"], "authorization_text": "Synthetic fixture"})
        packet, _ = scan.contract.fictional_example()
        body = packet["source_map"]["source_fields"]["body"]["text"]
        def article(text):
            return {"body": text, "title": "Synthetic event", "published": None}
        pairs = [
            {"pair": 1, "corpus": "incident-reports", "article_ids": ["a", "b"], "articles": [article(body), article(body + " ")]},
            {"pair": 2, "corpus": "cybercrime", "article_ids": ["c", "d"], "articles": [article(body), article("")]},
        ]
        for directory, kind, value, constant in (
            ("provider-event-label-check-20261019-v1", "provider_label_plan", {"pairs": pairs}, "PAIR_PLAN"),
            ("engineering/luna-lane-quality-20261018-v1", "luna_lane_comparison", {}, "COMPARISON"),
        ):
            seed = Seed(tmp_path / directory, config=Config(offline=True))
            try:
                identifier = prior.call(seed, "status", {"kind": kind, "value": value})
                monkeypatch.setattr(scan, constant, identifier)
            finally:
                seed.close()
        head = source.ledger.db.execute("SELECT MAX(seq) FROM events").fetchone()[0]
        result = prior.call(review, "status", {"action": "inspect", "base": str(tmp_path)})
        assert result["summary"]["matched_articles"] == 2
        assert result["summary"]["matched_outputs_by_lane"] == {"standard": 12}
        assert result["summary"]["pairs_with_both_outputs"] == []
        read = prior.call(review, "status", {"action": "read", "pairs": [1, 2]})
        assert all(not p["articles"][1]["outputs"] for p in read["pairs"])
        assert source.ledger.db.execute("SELECT MAX(seq) FROM events").fetchone()[0] == head
        with pytest.raises(AuditError, match="inspection_frozen"):
            prior.call(review, "status", {"action": "inspect", "base": str(tmp_path)})
        conclusion = review.ledger.root / "draft.txt"
        conclusion.write_text("Synthetic proposal; no accuracy claim.", encoding="utf-8")
        prior.call(review, "status", {"action": "conclude", "input": str(conclusion)})
        assert not review.ledger.unresolved
        assert review.ledger.verify()["unresolved_model_attempts"] == []
        # A source artifact altered after its original write cannot be inspected.
        row = source.ledger.db.execute("SELECT payload FROM records WHERE kind='luna_standard_assessment' LIMIT 1").fetchone()
        import json
        artifact = source.ledger.artifacts.root / json.loads(row[0])["response"]
        original = artifact.read_bytes()
        fresh = scan.Inspection(tmp_path / "fresh-review", config=Config(offline=True))
        try:
            artifact.write_bytes(original + b" ")
            with pytest.raises(scan.state.StateError, match="hash_mismatch"):
                prior.call(fresh, "status", {"action": "inspect", "base": str(tmp_path)})
            assert not fresh.ledger.unresolved
        finally:
            artifact.write_bytes(original)
            fresh.close()
    finally:
        review.close()
        source.close()
