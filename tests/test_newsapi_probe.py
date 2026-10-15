from dataclasses import replace
import json

import pytest

from newsresearch import newsapi_probe
from newsresearch.common import AuditError, ResearchError


def setup(engine, method="newsapi-probe-approval-v1"):
    parameters = {"action": "getArticles", "resultType": "articles", "dateStart": "2023-10-15",
                  "dateEnd": "2026-10-15", "articlesPage": 1, "articlesCount": 100,
                  "includeArticleBody": False}
    requests = [{**parameters, "keyword": str(i)} for i in range(20)]
    versions = {}
    bodies = {"protocol": {"method": "test"}, "question": {"text": "test"},
              "selection": {"rules": requests}, "profile": {"mode": "exploratory"},
              "policy": {"method": method, "authorization_id": newsapi_probe.AUTHORIZATION,
                         "budget_accounting": "confirmed-costs-plus-unresolved-reservations-v1",
                         "max_tokens": 200, "requests": requests}}
    for kind, content in bodies.items():
        versions[kind] = engine.execute("version", {"kind": kind, "key": "test", "content": content},
                                       objective="Synthetic transport boundary checks", actor="test")["id"]
    engine.config = replace(engine.config, offline=False)
    def run(p):
        return engine.execute("newsapi_probe", {"execute": True, "parameters": p},
                              objective="Synthetic transport boundary checks", actor="test", versions=versions)
    return run, requests


def test_budget_and_no_retry_on_failed_request(engine, monkeypatch):
    run, requests = setup(engine)
    calls = []
    def fake(parameters):
        calls.append(parameters)
        return 403, {}, b""
    monkeypatch.setattr(newsapi_probe, "transport", fake)
    for p in requests[:10]:
        assert run(p)["status"] == "failed"
    with pytest.raises(ResearchError, match="exhausted"):
        run(requests[10])
    with pytest.raises(ResearchError, match="already reserved"):
        run(requests[0])
    assert len(calls) == 10


def test_offline_and_audit_failure_prevent_dispatch(engine, monkeypatch):
    run, requests = setup(engine)
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: pytest.fail("Unexpected dispatch"))
    engine.config = replace(engine.config, offline=True)
    with pytest.raises(ResearchError, match="authorization"):
        run(requests[0])
    engine.config = replace(engine.config, offline=False)
    engine.ledger.fail_event = "operation.intended"
    with pytest.raises(AuditError):
        run(requests[0])


def test_success_and_unknown_outcome(engine, monkeypatch):
    run, requests = setup(engine)
    raw = json.dumps({"articles": {"totalResults": 201, "results": [{"uri": "synthetic"}]}}).encode()
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: (200, {}, raw))
    result = run(requests[0])
    assert result["provider_total"] == 201 and result["returned"] == 1
    def failure(_):
        raise ResearchError("Synthetic network failure")
    monkeypatch.setattr(newsapi_probe, "transport", failure)
    with pytest.raises(ResearchError, match="network failure"):
        run(requests[1])
    with pytest.raises(ResearchError, match="already reserved"):
        run(requests[1])


def test_reservation_write_failure_prevents_dispatch(engine, monkeypatch):
    run, requests = setup(engine)
    original = engine.ledger.record
    def fail_reservation(session, kind, *args, **kwargs):
        if kind == "newsapi_reservation":
            raise AuditError("Synthetic reservation storage failure")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", fail_reservation)
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: pytest.fail("Unexpected dispatch"))
    with pytest.raises(AuditError, match="reservation storage failure"):
        run(requests[0])


def test_non_json_error_is_preserved(engine, monkeypatch):
    run, requests = setup(engine)
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: (400, {}, b"Invalid query conditions"))
    result = run(requests[0])
    assert result["status"] == "failed"
    assert result["provider_notes"]["error_text"] == "Invalid query conditions"
    with pytest.raises(ResearchError, match="already reserved"):
        run(requests[0])


def test_receipt_reconciliation_preserves_every_unknown_charge(engine, monkeypatch):
    run, requests = setup(engine, method="newsapi-probe-approval-v2")
    count = 0
    def fake(_):
        nonlocal count
        count += 1
        return (200, {"req-tokens": "1.000"}, b'{"articles":{"results":[],"totalResults":0}}') if count <= 5 else (403, {}, b"")
    monkeypatch.setattr(newsapi_probe, "transport", fake)
    for p in requests[:14]:
        run(p)
    with pytest.raises(ResearchError, match="exhausted"):
        run(requests[14])
    assert count == 14  # five confirmed tokens + nine unknown 20-token reservations


def test_unexpected_price_stops_further_dispatch(engine, monkeypatch):
    run, requests = setup(engine, method="newsapi-probe-approval-v2")
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: (200, {"req-tokens": "25"}, b'{"articles":{"results":[],"totalResults":0}}'))
    run(requests[0])
    monkeypatch.setattr(newsapi_probe, "transport", lambda _: pytest.fail("Unexpected second dispatch"))
    with pytest.raises(ResearchError, match="exceeded its documented reservation"):
        run(requests[1])
