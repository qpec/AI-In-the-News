from dataclasses import replace
import json

import pytest

from newsresearch import newsapi_collection as nc
from newsresearch.common import AuditError, ResearchError


def setup(engine, monkeypatch, used=1307, historical=False):
    content = {"protocol": {"method": nc.METHOD}, "question": {"text": "Synthetic"},
        "selection": {"rules": {"periods": nc.PERIODS}}, "profile": {"mode": "exploratory"},
        "policy": {"method": nc.METHOD, "total_account_target": 4000, "monthly_allowance": 5000,
                   "words": nc.WORDS, "periods": [list(p) for p in nc.PERIODS]}}
    versions = {k: engine.execute("version", {"kind": k, "key": "test", "content": v}, objective="Synthetic boundary checks", actor="test")["id"] for k, v in content.items()}
    engine.config = replace(engine.config, offline=False)
    calls = []
    def transport(p):
        calls.append(p)
        if p == {"endpointVariant": "usage"}:
            return 200, {}, json.dumps({"usedTokens": used, "availableTokens": 5000}).encode()
        items = [{"date": "2024-01-01", "title": "Synthetic", "url": "https://example.test"}] if historical else []
        return 200, {"req-tokens": "5", "req-archive": "1" if historical else "0"}, json.dumps({"articles": {"results": items, "totalResults": len(items)}}).encode()
    monkeypatch.setattr(nc, "transport", transport)
    return lambda: engine.execute("newsapi_collection", {"execute": True, "action": "check"}, objective="Synthetic boundary checks", actor="test", versions=versions), calls


def test_archive_zero_stops_collection_and_preserves_actual_cost(engine, monkeypatch):
    run, calls = setup(engine, monkeypatch)
    result = run()
    assert result["archive_access"] == "not_verified" and result["collected_keyword_articles"] == 0
    assert result["archive_reported_cost"] == 5 and result["account_observed_delta"] == 0
    assert len(calls) == 3
    with pytest.raises(ResearchError, match="already recorded"):
        run()
    assert len(calls) == 3


def test_historical_dates_verify_archive_not_quota_alone(engine, monkeypatch):
    run, _ = setup(engine, monkeypatch, historical=True)
    assert run()["archive_access"] == "verified_by_historical_articles"


def test_current_total_budget_blocks_search(engine, monkeypatch):
    run, calls = setup(engine, monkeypatch, used=3998)
    with pytest.raises(ResearchError, match="4000 total"):
        run()
    assert calls == [{"endpointVariant": "usage"}]


def test_reservation_failure_prevents_network(engine, monkeypatch):
    run, calls = setup(engine, monkeypatch)
    original = engine.ledger.record
    def fail(session, kind, *args, **kwargs):
        if kind == "newsapi_collection_intent":
            raise AuditError("Synthetic audit failure")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", fail)
    with pytest.raises(AuditError):
        run()
    assert calls == []
