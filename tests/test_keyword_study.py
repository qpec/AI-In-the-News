from dataclasses import replace
import json

import pytest

from newsresearch import keyword_study as ks
from newsresearch.common import AuditError


def setup(engine):
    bodies = {"protocol": {"method": ks.METHOD}, "question": {"text": "Synthetic"},
              "selection": {"rules": ks.manifest()}, "profile": {"mode": "exploratory"},
              "policy": {"method": ks.METHOD, "requests": ks.manifest()}}
    versions = {k: engine.execute("version", {"kind": k, "key": "test", "content": v},
                objective="Synthetic checks", actor="test")["id"] for k, v in bodies.items()}
    engine.config = replace(engine.config, offline=False)
    return lambda: engine.execute("keyword_study", {"execute": True, "limit": 1},
                objective="Synthetic checks", actor="test", versions=versions)


def test_balanced_manifest_and_disjoint_exact_windows():
    rows = ks.manifest()
    assert len(rows) == len({r["id"] for r in rows}) == 550
    assert len([r for r in rows if r["term"] != "control"]) == 500
    for term in ks.TERMS:
        for domain in ks.DOMAINS:
            cells = sorted([r for r in rows if r["term"] == term and r["domain"] == domain], key=lambda r: r["start"])
            assert len(cells) == 5 and cells[0]["start"] == "2023-10-15" and cells[-1]["stop"] == "2026-10-16"
            assert all(a["stop"] == b["start"] for a, b in zip(cells, cells[1:]))


def test_publication_boundaries_and_missingness():
    raw = b"<rss><channel><item><title>datalek Hackers - NOS</title><guid>x</guid><pubDate>Mon, 15 Jan 2024 23:00:00 GMT</pubDate><source url='https://nos.nl'>NOS</source></item><item><pubDate>bad</pubDate></item><item><pubDate>Tue, 16 Jan 2024 00:00:00 GMT</pubDate></item></channel></rss>"
    r = ks.parse(raw, {"start": "2024-01-15", "stop": "2024-01-16"})
    assert r["in_window"] == 1 and r["outside_window"] == 1 and r["missing_dates"] == 1
    assert r["items"][0]["title_words"] == ["datalek", "hackers"]
    with pytest.raises(ValueError):
        ks.parse(b"<html/>", {})


def test_audit_failure_before_dispatch(engine, monkeypatch):
    run = setup(engine)
    original = engine.ledger.record
    def fail(session, kind, *args, **kwargs):
        if kind == "keyword_reservation":
            raise AuditError("Synthetic failure")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", fail)
    monkeypatch.setattr(ks, "fetch", lambda _: pytest.fail("Dispatch forbidden"))
    with pytest.raises(AuditError):
        run()


def test_failed_html_is_not_successful_zero_and_no_retry(engine, monkeypatch):
    run = setup(engine)
    calls = []
    def fake(q):
        calls.append(q)
        return 200, b"<html/>"
    monkeypatch.setattr(ks, "fetch", fake)
    monkeypatch.setattr(ks.time, "sleep", lambda _: None)
    first = run()
    second = run()
    assert first["failed"] == 1 and first["completed"] == 0
    assert second["failed"] == 2 and calls[0] != calls[1]
    assert len(list(engine.ledger.db.execute("SELECT * FROM records WHERE kind='keyword_reservation'"))) == 2


def test_cap_and_title_dedup_sensitivity():
    raw = b"<rss><channel>" + b"<item><title>Hack</title><guid>x</guid><pubDate>Mon, 15 Jan 2024 00:00:00 GMT</pubDate></item>"*100 + b"</channel></rss>"
    p = ks.parse(raw, {"start": "2024-01-01", "stop": "2025-01-01"})
    q = ks.manifest()[0]
    r = {**p, "status": "completed", "query": q}
    a = ks.analyze([q], [r], [{}])
    assert a["possibly_capped"] == 1 and a["unique_records"] == 1
    assert a["heldout_strata"] == 0 and a["subsets"][0]["heldout"]["fraction"] is None
    assert json.dumps(a)
