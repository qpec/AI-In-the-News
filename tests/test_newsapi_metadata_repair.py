from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from newsresearch import newsapi_metadata_repair as module
from newsresearch import newsapi_id_manifest_proof as proof_module
from newsresearch.common import AuditError, Context, ResearchError, canonical, digest
from newsresearch.newsapi_event_coverage import observation


def fixture(monkeypatch, tmp_path):
    artifacts, events, records = {}, [], {}
    def put_bytes(raw):
        ref = hashlib.sha256(raw).hexdigest()
        artifacts[ref] = raw
        return ref
    def receipt(identifier, items, sequence, raw=True):
        response = {"articles": {"results": items}}
        ref = put_bytes(canonical(response).encode()) if raw else None
        return {"id": identifier, "response": response, "raw_response": ref, "raw_sha256": ref,
            "http_status": 200, "outcome": "received", "completed_at": f"2026-10-17T00:00:{sequence:02d}Z"}
    original = [
        {"uri": "a", "date": "2025-01-01", "body": "Original body\u2028Unicode separator\u0085still one JSON record", "eventUri": "old-event"},
        {"uri": "q", "date": "2026-01-01", "quarantined": True},
        {"uri": "b", "date": "2026-01-02", "body": "Another body", "eventUri": None},
    ]
    fresh_items = [
        {"uri": "a", "date": "2025-01-01", "eventUri": None},
        {"uri": "q", "date": "2026-01-01", "eventUri": "recovered-event"},
        {"uri": "new", "date": "2026-01-03", "eventUri": None},
    ]
    old = receipt("original", original, 1, False)
    fresh = receipt("fresh", fresh_items, 2)
    rows = [observation(item, "original", i, "original_saved") for i, item in enumerate(original)]
    rows.append(observation(fresh_items[-1], "fresh", 2, "fresh_minimal_metadata"))
    enumeration = {"receipt_ids": ["fresh"], "observed_added_ids": ["new"]}
    baseline = {"2025-01-01": {"identifiers": [{"uri": row["article_uri"], **{k: row[k] for k in ("receipt", "index", "record_hash")}} for row in rows[:-1]]}}
    parent = module.pack({"record-references.json": canonical([{"id": "original", "created_event": 1}, {"id": "fresh", "created_event": 2}]).encode(),
        "receipts/fresh.json": canonical(fresh).encode(), "responses/fresh.json": artifacts[fresh["raw_response"]],
        "baseline-identity-manifest.json": canonical(baseline).encode(),
        "comparison.json": canonical({"minimal_recovery_summary": {"enumeration": enumeration}}).encode()})
    parent_ref = put_bytes(parent)
    coverage_ref = put_bytes(canonical({"rows": rows}).encode())
    records.update({"protocol": {"content": {"method": module.METHOD}},
        "selection": {"content": {"rules": {"diagnosis_id": "diagnosis"}}},
        "question": {}, "profile": {}, "diagnosis": {"coverage_id": "coverage"},
        "coverage": {"proof_artifact": coverage_ref, "recovery_id": "recovery"},
        "recovery": {"proof_artifact": parent_ref, "minimal_recovery_summary": {"enumeration": enumeration}},
        "original": old, "fresh": fresh})
    def record(session, kind, key, value):
        ref = digest(value)
        records[ref] = copy.deepcopy(value)
        return ref
    ledger = SimpleNamespace(root=tmp_path, get=lambda ref, kind: copy.deepcopy(records[ref]),
        artifacts=SimpleNamespace(read_bytes=lambda ref: artifacts[ref], put_bytes=put_bytes),
        append=lambda *args: events.append(args), record=record)
    engine = SimpleNamespace(ledger=ledger, _active={"session"}, _require=lambda *args: None, identity=lambda: {"synthetic": True})
    context = Context("Test offline repair", "test", {kind: kind for kind in ("protocol", "question", "selection", "profile")})
    budget = {"limit": 583, "reported_tokens": 431, "conservative_accounted_tokens": 561}
    monkeypatch.setattr(module, "budget", lambda engine: copy.deepcopy(budget))
    real_verify = proof_module.verify_proof_bytes
    monkeypatch.setattr(proof_module, "verify_proof_bytes", lambda raw: {"status": "verified", "synthetic_parent": True} if raw == parent else real_verify(raw))
    return engine, context, records, artifacts, events, real_verify


def test_repair_run_preserves_bodies_history_quarantine_costs_and_replays(monkeypatch, tmp_path):
    engine, context, records, artifacts, events, verify = fixture(monkeypatch, tmp_path)
    before = copy.deepcopy(records)
    result = module.run(engine, "session", context, {"diagnosis_id": "diagnosis"})
    assert result["summary"]["event_states"] == {"absent": 0, "null": 3, "empty": 0, "invalid_type": 0, "populated": 1}
    assert result["summary"]["articles_with_any_saved_event_id"] == 2
    assert result["summary"]["changed_event_fields"] == {"populated_to_null": 1, "absent_to_populated": 1}
    assert result["summary"]["missing_body"] == 2
    assert result["network_calls"] == result["model_calls"] == result["newsapi_tokens"] == 0
    assert result["budget"]["conservative_accounted_tokens"] == 561
    for key in before:
        assert before[key] == records[key]
    assert verify(artifacts[result["proof_artifact"]])["articles_checked"] == 4
    content = module.unpack(artifacts[result["collection_artifact"]])
    articles = [json.loads(line) for name, raw in content.items() if name.startswith("articles/") for line in raw.splitlines()]
    q = next(row for row in articles if row["article"]["uri"] == "q")
    assert q["article"] == {"uri": "q", "date": "2026-01-01", "quarantined": True, "eventUri": "recovered-event"}
    assert q["event_metadata"]["observations"][0]["field_present"] is False
    assert any(event[1] == "export.write_intended" for event in events)
    assert json.loads((tmp_path / "cybercrime-nl-collection-latest.json").read_text())["result_id"] == result["id"]
    reused = module.run(engine, "session", context, {"diagnosis_id": "diagnosis", "reuse_result": result["id"]})
    assert reused["reused"]
    records[result["id"]]["versions"]["profile"] = "other"
    with pytest.raises(ResearchError, match="exact original versions"):
        module.run(engine, "session", context, {"diagnosis_id": "diagnosis", "reuse_result": result["id"]})


@pytest.mark.parametrize("change", ["event", "body", "year_summary", "wrong_year"])
def test_replay_detects_record_and_year_tampering_after_rehash(monkeypatch, tmp_path, change):
    engine, context, _, artifacts, _, _ = fixture(monkeypatch, tmp_path)
    result = module.run(engine, "session", context, {"diagnosis_id": "diagnosis"})
    outer = module.unpack(artifacts[result["proof_artifact"]])
    collection = module.unpack(outer["collection.zip"])
    if change in {"event", "body"}:
        row = json.loads(collection["articles/articles-2025.jsonl"])
        row["article"]["eventUri" if change == "event" else "body"] = "invented"
        row["source_hash"] = digest(row["article"])
        collection["articles/articles-2025.jsonl"] = (canonical(row) + "\n").encode()
    elif change == "year_summary":
        inner = json.loads(collection["manifest.json"])
        inner["years"][0]["articles"] = 123
        collection["manifest.json"] = canonical(inner).encode()
    else:
        collection["articles/articles-2026.jsonl"] += collection["articles/articles-2025.jsonl"]
        collection["articles/articles-2025.jsonl"] = b""
    outer["collection.zip"] = module.pack(collection)
    manifest = json.loads(outer[module.MARKER])
    manifest["collection_sha256"] = hashlib.sha256(outer["collection.zip"]).hexdigest()
    outer[module.MARKER] = canonical(manifest).encode()
    with pytest.raises(AuditError):
        module.verify_repaired_proof(module.pack(outer))


def test_raw_parsed_mismatch_and_wrong_source_stop_before_export(monkeypatch, tmp_path):
    engine, context, records, artifacts, _, _ = fixture(monkeypatch, tmp_path)
    with pytest.raises(ResearchError, match="Register"):
        module.run(engine, "session", context, {"diagnosis_id": "other"})
    parent = module.unpack(artifacts[records["recovery"]["proof_artifact"]])
    receipt = json.loads(parent["receipts/fresh.json"])
    receipt["response"]["articles"]["results"][1]["eventUri"] = "invented"
    parent["receipts/fresh.json"] = canonical(receipt).encode()
    with pytest.raises(AuditError, match="retained raw"):
        module.parent_sources(module.pack(parent))
    engine.ledger.append = lambda *args: (_ for _ in ()).throw(AuditError("audit unavailable"))
    with pytest.raises(AuditError, match="audit unavailable"):
        module.run(engine, "session", context, {"diagnosis_id": "diagnosis"})
    assert not list(tmp_path.glob("*.zip"))


def test_absence_cannot_erase_assignment_and_conflicts_are_rejected():
    article = {"uri": "a", "eventUri": "event"}
    receipt = {"id": "base", "completed_at": "2026-10-17T00:00:00Z"}
    base = module.observe(article, receipt, [0], 1, "test")
    absent = module.observe({"uri": "a"}, {**receipt, "id": "later"}, [0], 2, "test")
    assert module.repair_article(article, base, [absent])["article"]["eventUri"] == "event"
    conflict = {**base, "receipt": "conflict", "event_value": "different"}
    with pytest.raises(ResearchError, match="Conflicting"):
        module.repair_article(article, base, [conflict])
    with pytest.raises(ResearchError, match="another article"):
        module.repair_article(article, base, [{**base, "article_uri": "other"}])
