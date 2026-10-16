from dataclasses import replace
import hashlib
import io
import json
import zipfile

import pytest

from newsresearch import newsapi_collection as collection
from newsresearch import newsapi_id_manifest as source
from newsresearch import newsapi_id_manifest_proof as module
from newsresearch.common import AuditError, ResearchError, canonical


def receipt(identifier, ids, total, ascending=True, page=1, count=5000):
    parameters = {**source.request("2020-01-01", "2020-12-31", page, count),
        "uriWgtListSortByAsc": ascending}
    return {"id": identifier, "parameters": parameters, "manifest_status": "valid",
        "normalized_ids": ids, "provider_total": total}


def frames():
    baseline = {"periods": [{"year": "2020", "date_start": "2020-01-01", "date_end": "2020-12-31"}]}
    return baseline, {"2020-01-01": {"uri_counts": {"a": 1, "b": 1, "lost": 1}}}


def test_reverse_confirmation_never_counts_ascending_or_calibration_pages():
    baseline, identities = frames()
    asc = receipt("ascending", ["a", "b", "new"], 3)
    small = receipt("calibration", ["a"], 1, ascending=False, count=1000)
    result, _ = module.compare_frames(baseline, identities, [asc], [asc, small])
    assert not result["complete"]
    assert result["years"][0]["reverse_ids"] == 0
    assert result["years"][0]["saved_only_ids"] is None
    assert result["ascending_reverse_equal"] is None


def test_complete_reverse_equality_and_saved_difference_are_separate():
    baseline, identities = frames()
    asc = receipt("ascending", ["a", "b", "new"], 3)
    reverse = receipt("reverse", ["new", "b", "a"], 3, ascending=False)
    result, _ = module.compare_frames(baseline, identities, [asc], [reverse])
    row = result["years"][0]
    assert result["complete"] and result["ascending_reverse_equal"]
    assert result["returned_order_differs_all_partitions"]
    assert row["manifest_only_ids"] == ["new"] and row["saved_only_ids"] == ["lost"]
    assert not result["saved_equals_reverse"]
    assert row["saved_coverage_of_manifest_percent"] == pytest.approx(200/3)


def test_descending_overlap_or_total_drift_cannot_establish_completion():
    baseline, identities = frames()
    asc_ids = [str(n) for n in range(5001)]
    asc = [receipt("a1", asc_ids[:5000], 5001), receipt("a2", asc_ids[5000:], 5001, page=2)]
    overlap = [receipt("r1", asc_ids[:5000], 5001, ascending=False),
        receipt("r2", asc_ids[:1], 5001, ascending=False, page=2)]
    result, _ = module.compare_frames(baseline, identities, asc, overlap)
    assert not result["complete"] and result["periods"][0]["duplicate_id_occurrences"] == 1
    overlap[1]["provider_total"] = 5002
    result, _ = module.compare_frames(baseline, identities, asc, overlap)
    assert not result["complete"] and result["periods"][0]["positive_total_drift"]


def test_first_frame_must_itself_be_complete_and_have_exact_keywords():
    baseline, identities = frames()
    asc = receipt("a", ["a"], 5001)
    with pytest.raises(ResearchError, match="ascending source"):
        module.compare_frames(baseline, identities, [asc], [])
    asc = receipt("a", ["a"], 1)
    asc["parameters"]["keyword"] = ["changed"]
    with pytest.raises(ResearchError, match="ascending source"):
        module.compare_frames(baseline, identities, [asc], [])


def prepared(engine, monkeypatch):
    def bootstrap(engine, session, context, data):
        definitions = {"protocol": {"method": source.METHOD}, "question": {"text": "Synthetic ID proof"},
            "selection": {"rules": "Synthetic same-keyword fixture"}, "profile": {"mode": "exploratory"}}
        versions = {kind: engine.ledger.record(session, kind, "proof-fixture", {"content": content})
            for kind, content in definitions.items()}
        manifest = {"2020-01-01": {"uri_counts": {"a": 1, "b": 1, "lost": 1}}}
        ref = engine.ledger.artifacts.put(manifest)
        engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": ref})
        original = engine.ledger.record(session, "newsapi_collection_receipt", "original", {
            "attempt": "original", "parameters": collection.collection_request(("2020-01-01", "2020-12-31"), 1),
            "raw_response": None, "raw_sha256": "a"*64,
            "response": {"articles": {"results": [{"body": "SYNTHETIC FULL TEXT MUST NOT ENTER PROOF"}]}}})
        baseline, _ = frames()
        baseline.update(identity_manifest=ref)
        baseline["periods"][0].update(page_details=[{"receipt": original}], receipt_ids=[original])
        audit = engine.ledger.record(session, "newsapi_retrieval_audit", "fixture", baseline)
        asc = receipt("ascending", ["a", "b", "new"], 3)
        intent = {"attempt": "ascending", "authorization_id": source.AUTH_ID, "reserved_tokens": 250,
            "parameters": asc["parameters"], "purpose": "manifest", "versions": versions}
        engine.ledger.record(session, "newsapi_id_intent", "ascending", intent)
        raw = canonical({"uriWgtList": {"totalResults": 3, "results": ["a:1", "b:1", "new:1"]}}).encode()
        raw_ref = engine.ledger.artifacts.put_bytes(raw)
        engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": raw_ref})
        asc.pop("id")
        asc.update(**intent, outcome="received", http_status=200, billed_tokens=5,
            headers={"req-tokens": "5", "req-archive": "1"}, response=json.loads(raw), raw_response=raw_ref,
            raw_sha256=hashlib.sha256(raw).hexdigest())
        asc_id = engine.ledger.record(session, "newsapi_id_receipt", "ascending", asc)
        first = {"authorization_id": source.AUTH_ID, "versions": versions, "page_size": 5000, "baseline_audit": audit,
            "periods": [{"complete": True, "manifest_receipts": [asc_id]}]}
        first_id = engine.ledger.record(session, "newsapi_id_manifest_test", "ascending", first)
        policy = {"method": source.METHOD, "authorization_id": source.AUTH_ID, "max_tokens": source.CAP,
            "confirmation_method": module.CONFIRM_METHOD, "confirmation_source": first_id,
            "baseline_audit": audit, "periods": [["2020-01-01", "2020-12-31"]],
            "confirmation_templates": [module.reverse_request("2020-01-01", "2020-12-31", 1)]}
        versions["policy"] = engine.ledger.record(session, "policy", "proof-policy", {"content": policy})
        return versions

    monkeypatch.setattr(collection, "run", bootstrap)
    versions = engine.execute("newsapi_collection", {}, objective="Prepare synthetic software test", actor="test")
    monkeypatch.setattr(collection, "run", module.run)
    monkeypatch.setenv("EVENTREGISTRY_API_KEY", "synthetic-transient-value")
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    engine.config = replace(engine.config, offline=False)
    calls = []
    def transport(parameters):
        calls.append(parameters)
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, canonical({"usedTokens": 4500, "availableTokens": 5000}).encode()
        assert parameters["uriWgtListSortByAsc"] is False
        return 200, {"req-tokens": "5", "req-archive": "1"}, canonical({"uriWgtList": {
            "totalResults": 3, "results": ["new:1", "b:1", "a:1"]}}).encode()
    monkeypatch.setattr(source, "transport", transport)
    def run(**kwargs):
        return engine.execute("newsapi_collection", {"execute": True, "requests": 1, **kwargs},
            objective="Validate synthetic reverse ID proof software", actor="test", versions=versions)
    return run, calls


def test_audited_confirmation_builds_self_checking_proof_without_original_text(engine, monkeypatch):
    run, calls = prepared(engine, monkeypatch)
    result = run()
    assert result["complete"] and result["ascending_reverse_equal"]
    assert result["budget"]["reported_tokens"] == 10
    assert len(calls) == 3 and result["reverse_reported_tokens"] == 5
    raw = engine.ledger.artifacts.read_bytes(result["proof_artifact"])
    assert hashlib.sha256(raw).hexdigest() == result["evidence_zip"]
    assert result["proof_self_check"]["status"] == module.verify_proof_bytes(raw)["status"] == "verified"
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        hashes = json.loads(archive.read("file-sha256.json"))["files"]
        assert set(hashes) == set(archive.namelist())-{"file-sha256.json"}
        for name, identity in hashes.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == identity["sha256"]
        assert archive.read("years/2020/ascending-ids.txt") == archive.read("years/2020/reverse-ids.txt")
        assert b"SYNTHETIC FULL TEXT MUST NOT ENTER PROOF" not in b"".join(archive.read(n) for n in archive.namelist())
        assert "original-collection-references.json" in hashes and "session-provenance.json" in hashes
    modified = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as original, zipfile.ZipFile(modified, "w") as changed:
        for name in original.namelist():
            changed.writestr(name, b"tampered" if name == "years/2020/reverse-ids.txt" else original.read(name))
    with pytest.raises(AuditError):
        module.verify_proof_bytes(modified.getvalue())
    reused = run()
    assert reused["id"] == result["id"] and reused["reused"] and reused["new_api_calls"] == 0
    assert len(calls) == 3


def test_missing_page_produces_pending_evidence_not_zero_missing(engine, monkeypatch):
    run, _ = prepared(engine, monkeypatch)
    def transport(parameters):
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, canonical({"usedTokens": 4500, "availableTokens": 5000}).encode()
        return 200, {"req-tokens": "5", "req-archive": "1"}, canonical({"uriWgtList": {
            "totalResults": 5001, "results": [str(n) for n in range(5000)]}}).encode()
    monkeypatch.setattr(source, "transport", transport)
    result = run()
    assert not result["complete"] and result["proof_artifact"] is None
    assert result["periods"][0]["pending_pages"] == [2]
    assert result["years"][0]["saved_only_ids"] is None


def test_audit_storage_failure_prevents_confirmation_search(engine, monkeypatch):
    run, calls = prepared(engine, monkeypatch)
    original = engine.ledger.record
    def record(session, kind, *args, **kwargs):
        if kind == "newsapi_id_intent":
            raise AuditError("Synthetic durable-intent failure")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", record)
    with pytest.raises(AuditError):
        run()
    assert not calls


def test_original_authorization_budget_includes_previous_phase(engine, monkeypatch):
    run, calls = prepared(engine, monkeypatch)
    original = module.accounting
    def used(intents, receipts):
        result = original(intents, receipts)
        result["unresolved_outcomes"] = ["synthetic-prior-unknown"]
        return result
    monkeypatch.setattr(module, "accounting", used)
    result = run()
    assert not result["complete"] and result["stop_reason"] == "unknown_or_excessive_charge"
    assert all(p == {"endpointVariant": "usage"} for p in calls)
