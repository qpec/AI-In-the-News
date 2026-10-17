from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from newsresearch import newsapi_event_matching_run as module
from newsresearch import newsapi_id_manifest_proof
from newsresearch.common import AuditError, Context, ResearchError, canonical, digest
from newsresearch.newsapi_metadata_repair import observe, pack, repair_article, summarize_collection, unpack


def fixture(monkeypatch, tmp_path):
    artifacts, records, events = {}, {}, []
    def put(raw):
        ref = hashlib.sha256(raw).hexdigest()
        artifacts[ref] = raw
        return ref
    def make(uri, event, body):
        article = {"uri": uri, "eventUri": event, "date": "2020-01-01", "title": "Synthetic news example",
            "url": f"https://example.invalid/{uri}", "body": body}
        observation = observe(article, {"id": "receipt-" + uri, "completed_at": "2026-10-17T00:00:00Z"}, [0], 1, "test")
        return repair_article(article, observation, [])
    one = " ".join("synthetic institution reports an unusual network failure" for _ in range(20)) + "\u2028continuation"
    two = " ".join("synthetic city museum exhibition closes to visitors" for _ in range(20))
    rows = [make("a", "event-1", one), make("b", "event-2", two), make("target", None, one)]
    summary = summarize_collection(rows)
    source = pack({"manifest.json": canonical({"summary": summary}).encode(),
        "articles/articles-2020.jsonl": ("\n".join(canonical(row) for row in rows) + "\n").encode()})
    source_ref = put(source)
    records.update({"protocol": {"content": {"method": module.METHOD, "matching_policy": copy.deepcopy(module.POLICY)}},
        "selection": {"content": {"rules": {"repair_id": "repair"}}}, "question": {}, "profile": {},
        "repair": {"collection_artifact": source_ref, "proof_artifact": put(b"synthetic proof placeholder"), "summary": summary}})
    def record(session, kind, key, value):
        ref = digest(value)
        records[ref] = copy.deepcopy(value)
        return ref
    engine = SimpleNamespace(ledger=SimpleNamespace(root=tmp_path,
        get=lambda ref, kind: copy.deepcopy(records[ref]), append=lambda *args: events.append(args), record=record,
        artifacts=SimpleNamespace(read_bytes=lambda ref: artifacts[ref], put_bytes=put)),
        config=SimpleNamespace(offline=True), _active={"session"}, _require=lambda *args: None,
        identity=lambda: {"synthetic": True})
    balance = {"reported_tokens": 431, "conservative_accounted_tokens": 561, "limit": 583}
    monkeypatch.setattr(module, "budget", lambda engine: copy.deepcopy(balance))
    monkeypatch.setattr(newsapi_id_manifest_proof, "verify_proof_bytes", lambda raw: {"status": "verified", "synthetic_fixture": True})
    context = Context("Test saved event-ID matching", "test:actor", {key: key for key in ("protocol", "question", "selection", "profile")})
    return engine, context, records, artifacts, events, rows


def test_offline_adapter_replays_preserves_sources_exports_and_reuses(monkeypatch, tmp_path):
    engine, context, records, artifacts, events, rows = fixture(monkeypatch, tmp_path)
    source_before = copy.deepcopy(records["repair"])
    result = module.run(engine, "session", context, {"repair_id": "repair"})
    assert result["summary"]["target_articles"] == 1
    assert result["summary"]["status_counts"]["proposed_same_text"] == 1
    assert result["network_calls"] == result["newsapi_tokens"] == result["model_calls"] == 0
    assert result["automatic_assignments"] == 0 and result["deterministic_replay"] == "verified"
    assert records["repair"] == source_before
    assert result["budget"]["conservative_accounted_tokens"] == 561
    bundle = unpack(artifacts[result["bundle_artifact"]])
    candidate = json.loads(bundle["candidates.jsonl"])
    assert candidate["proposed_event_uri"] == "event-1" and candidate["original_event_state"] == "null"
    source = module.load_rows(artifacts[source_before["collection_artifact"]], source_before["summary"])
    assert source == rows and source[-1]["article"]["eventUri"] is None
    assert json.loads((tmp_path / "event-matching-audit.json").read_text())["id"] == result["id"]
    assert any(item[1] == "newsapi.event_matching.inspection.intended" for item in events)
    overview = runpy.run_path(str(Path(__file__).parents[1] / "scripts" / "match_nl_cyber_event_ids.py"))["overview"]
    text = overview(result, tmp_path)
    assert "1 direct/text proposals" in text and "0 new NewsAPI tokens" in text
    assert "unreviewed" in text and "seven" in text
    reused = module.run(engine, "session", context, {"repair_id": "repair", "reuse_result": result["id"]})
    assert reused["reused"]
    records[result["id"]]["versions"]["profile"] = "changed"
    with pytest.raises(ResearchError, match="exact original"):
        module.run(engine, "session", context, {"repair_id": "repair", "reuse_result": result["id"]})


def test_policy_offline_and_source_identity_fail_closed(monkeypatch, tmp_path):
    engine, context, records, artifacts, _, _ = fixture(monkeypatch, tmp_path)
    for payload in ({"repair_id": "other"}, {"repair_id": "repair"}):
        if payload["repair_id"] == "repair":
            engine.config.offline = False
        with pytest.raises(ResearchError, match="Register"):
            module.run(engine, "session", context, payload)
    engine.config.offline = True
    records["protocol"]["content"]["matching_policy"]["maximum_publication_gap_days"] = 100
    with pytest.raises(ResearchError, match="Register"):
        module.run(engine, "session", context, {"repair_id": "repair"})
    records["protocol"]["content"]["matching_policy"] = copy.deepcopy(module.POLICY)
    artifacts[records["repair"]["collection_artifact"]] += b"tamper"
    with pytest.raises(AuditError, match="Collection bytes"):
        module.run(engine, "session", context, {"repair_id": "repair"})
    assert not list(tmp_path.glob("*.zip"))


def test_audit_failure_stops_before_matching_and_no_dropped_targets(monkeypatch, tmp_path):
    engine, context, _, _, _, rows = fixture(monkeypatch, tmp_path)
    engine.ledger.append = lambda *args: (_ for _ in ()).throw(AuditError("storage failed"))
    with pytest.raises(AuditError, match="storage failed"):
        module.run(engine, "session", context, {"repair_id": "repair"})
    with pytest.raises(AuditError, match="every unassigned"):
        module.validate_output(rows, {"candidates": []})
    assert not list(tmp_path.glob("*.zip"))
