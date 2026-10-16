from dataclasses import replace
import json

import pytest

from newsresearch import newsapi_collection as nc
from newsresearch.common import AuditError, ResearchError


def setup(engine, monkeypatch, used=1307, historical=False, diagnose=False):
    content = {"protocol": {"method": nc.METHOD}, "question": {"text": "Synthetic"},
        "selection": {"rules": {"periods": nc.PERIODS}}, "profile": {"mode": "exploratory"},
        "policy": {"method": nc.METHOD, "total_account_target": 4000, "monthly_allowance": 5000,
                   "words": nc.WORDS, "periods": [list(p) for p in nc.PERIODS]}}
    if diagnose:
        content["policy"]["diagnostic_requests"] = nc.diagnostics()
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
    return lambda: engine.execute("newsapi_collection", {"execute": True, "action": "diagnose" if diagnose else "check"}, objective="Synthetic boundary checks", actor="test", versions=versions), calls


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


def test_diagnostic_routes_reconcile_both_requests(engine, monkeypatch):
    run, calls = setup(engine, monkeypatch, diagnose=True)
    result = run()
    assert len(calls) == 5  # balance, REST, balance, complex SDK, balance
    assert len(result["diagnostics"]) == 2
    assert result["diagnostics"][0]["request"]["endpointVariant"] == "rest"
    assert "query" in result["diagnostics"][1]["request"]
    assert result["archive_access"] == "not_verified"


def test_unknown_dispatch_blocks_after_version_amendment(engine, monkeypatch):
    run, _ = setup(engine, monkeypatch)
    monkeypatch.setattr(nc, "transport", lambda _: (_ for _ in ()).throw(RuntimeError("Synthetic interruption")))
    with pytest.raises(RuntimeError):
        run()
    versions = {kind: row[0] for kind in ["protocol", "question", "selection", "profile", "policy"]
                if (row := engine.ledger.db.execute("SELECT id FROM records WHERE kind=? ORDER BY created_event DESC LIMIT 1", (kind,)).fetchone())}
    old = versions["protocol"]
    versions["protocol"] = engine.execute("version", {"kind": "protocol", "key": "amended",
        "content": {"method": "Synthetic amendment"}, "supersedes": old, "reason": "Test global unknown-outcome guard"},
        objective="Synthetic boundary checks", actor="test")["id"]
    monkeypatch.setattr(nc, "transport", lambda _: pytest.fail("Unknown dispatch must block across versions"))
    with pytest.raises(ResearchError, match="Unknown account dispatch"):
        engine.execute("newsapi_collection", {"action": "check", "execute": True},
                       objective="Synthetic boundary checks", actor="test", versions=versions)


def collection_setup(engine, monkeypatch, used=1322):
    run, _ = setup(engine, monkeypatch, historical=True)
    proof = run()
    versions = proof["versions"]
    previous = engine.ledger.get(versions["policy"], "policy")["content"]
    versions["policy"] = engine.execute("version", {"kind": "policy", "key": "synthetic-collection",
        "content": {**previous, "collection_enabled": True, "archive_check": proof["id"],
                    "templates": [nc.collection_request(p, 1) for p in nc.PERIODS]}},
        objective="Synthetic collection checks", actor="test")["id"]
    totals, calls = [used], []
    def transport(p):
        calls.append(p)
        if p == {"endpointVariant": "usage"}:
            return 200, {}, json.dumps({"usedTokens": totals[0], "availableTokens": 5000}).encode()
        totals[0] += 5
        year = p["dateStart"][:4]
        article = {"uri": year, "title": "Synthetic cyber report", "date": p["dateStart"], "lang": "nld", "body": "Synthetic source text", "url": "https://example.test/" + year}
        return 200, {"req-tokens": "5", "req-archive": "1"}, json.dumps({"articles": {"results": [article], "totalResults": 1, "pages": 1}}).encode()
    monkeypatch.setattr(nc, "transport", transport)
    monkeypatch.setattr(nc.time, "sleep", lambda _: None)
    return lambda: engine.execute("newsapi_collection", {"action": "collect", "execute": True, "pages": 20},
        objective="Synthetic collection checks", actor="test", versions=versions), calls, transport


def test_round_robin_exhaustion_fulltext_and_exact_cost(engine, monkeypatch):
    run, calls, _ = collection_setup(engine, monkeypatch)
    result = run()
    assert [p["dateStart"][:4] for p in calls if "dateStart" in p] == ["2023", "2024", "2025", "2026"]
    assert result["unique_articles"] == 4 and all(y["exhausted"] for y in result["years"])
    assert result["reported_collection_cost"] == 20 and result["final_observed_used"] == 1342
    assert result["stop_reason"] == "query_exhausted" and result["missing_body"] == 0


def test_collection_uses_account_total_not_additional_budget(engine, monkeypatch):
    run, calls, _ = collection_setup(engine, monkeypatch, used=3998)
    result = run()
    assert result["stop_reason"] == "budget_target" and result["unique_articles"] == 0
    assert all(p == {"endpointVariant": "usage"} for p in calls)


def test_2020_backfill_requires_authorization_and_keeps_original_scope_separate(engine, monkeypatch):
    run, calls, _ = collection_setup(engine, monkeypatch)
    original = run()
    versions = dict(original["versions"])
    content = engine.ledger.get(versions["policy"], "policy")["content"]
    content.update(periods=nc.BACKFILL_PERIODS, templates=[nc.collection_request(p, 1) for p in nc.BACKFILL_PERIODS])
    def policy(value):
        return engine.execute("version", {"kind": "policy", "key": "backfill-test", "content": value},
            objective="Synthetic extension scope and authorization check", actor="test")["id"]
    versions["policy"] = policy(content)
    before = len(calls)
    with pytest.raises(ResearchError, match="Explicit 2020"):
        engine.execute("newsapi_collection", {"action": "backfill", "execute": True},
            objective="Synthetic extension scope and authorization check", actor="test", versions=versions)
    assert len(calls) == before
    versions["policy"] = policy({**content, "user_authorized_backfill_2020": True})
    extended = engine.execute("newsapi_collection", {"action": "backfill", "execute": True},
        objective="Synthetic extension scope and authorization check", actor="test", versions=versions)
    assert extended["unique_articles"] == 4 and extended["stop_reason"] == "query_exhausted"
    assert [p["dateStart"] for p in calls[before:] if "dateStart" in p] == [p[0] for p in nc.BACKFILL_PERIODS]
    assert nc.collection_state(engine)["returned_articles"] == 4
    assert nc.collection_state(engine, nc.BACKFILL_PERIODS)["returned_articles"] == 4
    assert len(set(original["receipt_ids"]) & set(extended["receipt_ids"])) == 0


@pytest.mark.parametrize("used,expected,stop", [(3998, 4, "query_exhausted"), (4998, 0, "budget_target")])
def test_backfill_completes_above_soft_target_but_respects_allowance(engine, monkeypatch, used, expected, stop):
    run, calls, _ = collection_setup(engine, monkeypatch, used=used)
    original = run()
    versions = dict(original["versions"])
    content = engine.ledger.get(versions["policy"], "policy")["content"]
    versions["policy"] = engine.execute("version", {"kind": "policy", "key": "backfill-budget-test", "content": {
        **content, "periods": nc.BACKFILL_PERIODS, "templates": [nc.collection_request(p, 1) for p in nc.BACKFILL_PERIODS],
        "user_authorized_backfill_2020": True, "complete_requested_history_within_allowance": True}},
        objective="Synthetic shared account ceiling check", actor="test")["id"]
    result = engine.execute("newsapi_collection", {"action": "backfill", "execute": True},
        objective="Synthetic shared account ceiling check", actor="test", versions=versions)
    assert result["returned_articles"] == expected and result["stop_reason"] == stop
    assert result["account_ceiling"] == 5000
    if expected == 0:
        assert all(p == {"endpointVariant": "usage"} for p in calls)


def test_credential_pattern_quarantine_preserves_membership_without_secret(engine, monkeypatch):
    run, _, original = collection_setup(engine, monkeypatch)
    matched = "sk-" + "x"*30
    def transport(p):
        status, headers, raw = original(p)
        if "dateStart" in p:
            body = json.loads(raw)
            body["articles"]["results"][0]["body"] = matched
            body["articles"]["results"][0]["url"] = "https://example.test/" + matched
            raw = json.dumps(body).encode()
        return status, headers, raw
    monkeypatch.setattr(nc, "transport", transport)
    result = run()
    assert result["unique_articles"] == result["quarantined"] == result["missing_body"] == 4
    for receipt in nc.saved(engine, "newsapi_collection_receipt", None):
        if receipt["purpose"].startswith("collect_"):
            assert receipt["raw_response"] is None
            assert matched not in json.dumps(receipt)
            assert receipt["response"]["articles"]["results"][0]["unavailable_locator_fields"] == ["url"]


def test_explicit_recovery_preserves_unknown_cost_and_allows_audited_retry(engine, monkeypatch):
    run, _, original = collection_setup(engine, monkeypatch)
    def interrupted(p):
        if "dateStart" in p:
            raise RuntimeError("Synthetic interruption after dispatch")
        return original(p)
    monkeypatch.setattr(nc, "transport", interrupted)
    with pytest.raises(RuntimeError):
        run()
    intent = json.loads(engine.ledger.db.execute("SELECT payload FROM records WHERE kind='newsapi_collection_intent' ORDER BY created_event DESC LIMIT 1").fetchone()[0])
    versions = intent["versions"]
    policy = engine.ledger.get(versions["policy"], "policy")["content"]
    versions["policy"] = engine.execute("version", {"kind": "policy", "key": "explicit-recovery",
        "content": {**policy, "recovery_reason": "Synthetic retained interruption resolution and one explicit retry"}},
        objective="Synthetic recovery check", actor="test")["id"]
    monkeypatch.setattr(nc, "transport", original)
    recovered = engine.execute("newsapi_collection", {"execute": True, "action": "recover"},
        objective="Synthetic recovery check", actor="test", versions=versions)
    assert recovered["unavailable_costs"] == 1 and recovered["failed_pages"] == 1
    completed = engine.execute("newsapi_collection", {"execute": True, "action": "collect", "pages": 20},
        objective="Synthetic recovery check", actor="test", versions=versions)
    assert completed["unique_articles"] == 4 and completed["unavailable_costs"] == 1
    assert completed["failed_pages"] == 1 and all(y["exhausted"] for y in completed["years"])


def test_private_bundles_preserve_source_versions_and_receipt_lineage(engine, monkeypatch):
    import zipfile
    from pathlib import Path
    from newsresearch.newsapi_materialize import METHOD

    run, _, _ = collection_setup(engine, monkeypatch)
    completed = run()
    versions = completed["versions"]
    versions["retrieval_profile"] = engine.execute("version", {"kind": "retrieval_profile", "key": "private-bundle-test",
        "content": {"method": METHOD}}, objective="Synthetic private bundle checks", actor="test")["id"]
    result = engine.execute("newsapi_collection", {"action": "materialize"},
        objective="Synthetic private bundle checks", actor="test", versions=versions)
    assert result["network_calls"] == 0 and len(result["bundles"]) == 4
    for bundle in result["bundles"]:
        assert engine.ledger.artifacts.read_bytes(bundle["artifact"]) == Path(bundle["path"]).read_bytes()
        with zipfile.ZipFile(bundle["path"]) as archive:
            row = json.loads(archive.read("artikelen.jsonl"))
            manifest = json.loads(archive.read("manifest.json"))
        source = engine.ledger.get(row["receipt_id"], "newsapi_collection_receipt")
        assert row["article"]["body"] == "Synthetic source text"
        assert row["original_response_sha256"] == source["raw_sha256"]
        assert manifest["records"] == 1 and manifest["collection_result"] == completed["id"]
