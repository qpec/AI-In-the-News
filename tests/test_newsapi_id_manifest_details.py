import pytest

from newsresearch.common import ResearchError
from newsresearch.newsapi_id_manifest_details import extract_info, info_request


def test_metadata_request_is_bounded_and_suppresses_article_body():
    request = info_request(["a", "b"])
    assert request["articleUri"] == ["a", "b"]
    assert request["includeArticleBody"] is False
    assert request["articleBodyLen"] == request["infoArticleBodyLen"] == 0
    assert request["action"] == "getArticle" and "keyword" not in request
    for ids in [[], ["a", "a"], [str(n) for n in range(11)]]:
        with pytest.raises(ResearchError):
            info_request(ids)


def test_metadata_is_matched_by_exact_id_and_unavailable_stays_explicit():
    response = {"a": {"info": {"uri": "a", "title": "Example", "url": "https://example.test/a", "body": "unselected"}},
        "b": {"info": {"uri": "wrong", "title": "Unrelated"}}}
    result = extract_info(response, ["a", "b", "c"])
    assert result["a"]["status"] == "available" and result["a"]["title"] == "Example"
    assert "body" not in result["a"] and "uri" not in result["a"]
    assert result["b"]["status"] == result["c"]["status"] == "unavailable"


@pytest.mark.parametrize("unexpected_body", [False, True])
def test_full_audited_metadata_flow_and_exact_result_reuse(engine, monkeypatch, unexpected_body):
    from dataclasses import replace
    import json

    from newsresearch.common import digest
    from newsresearch import newsapi_id_manifest as manifest
    from newsresearch import newsapi_id_manifest_details as details

    definitions = {"protocol": {"method": manifest.METHOD}, "question": {"text": "Synthetic exact-ID metadata test"},
        "selection": {"rules": "Synthetic unchanged frame"}, "profile": {"mode": "exploratory"},
        "policy": {"method": manifest.METHOD, "authorization_id": manifest.AUTH_ID, "max_tokens": manifest.CAP,
            "details_method": details.DETAILS_METHOD, "metadata_max_ids": 10, "baseline_audit": "synthetic"}}
    versions = {kind: engine.execute("version", {"kind": kind, "key": "metadata-test", "content": content},
        objective="Validate metadata-only software", actor="test")["id"] for kind, content in definitions.items()}
    comparison = {"id": "comparison", "authorization_id": manifest.AUTH_ID, "versions": versions,
        "baseline_audit": "synthetic", "prior_phase_receipts": ["calibration"], "periods": [{"pages": 1}],
        "years": [{"year": "2020", "complete": True, "saved_ids": 2, "manifest_ids_seen": 2, "common_ids": 1,
            "manifest_only_ids": ["new"], "saved_only_ids": ["old"]}]}
    original = {"uri": "old", "title": "Saved article", "url": "https://example.test/old", "body": "Existing protected text"}
    locator = {"uri": "old", "receipt": "original", "index": 0, "record_hash": digest(original)}
    monkeypatch.setattr(details, "load_baseline", lambda *_: ({}, {"2020-01-01": {"identifiers": [locator]}}))
    real_records = details.records
    monkeypatch.setattr(details, "records", lambda e, kind: [comparison] if kind == "newsapi_id_manifest_test" else real_records(e, kind))
    original_get = engine.ledger.get
    monkeypatch.setattr(engine.ledger, "get", lambda identifier, kind: {"response": {"articles": {"results": [original]}}}
        if identifier == "original" else original_get(identifier, kind))
    monkeypatch.setenv("EVENTREGISTRY_API_KEY", "synthetic-metadata-transient")
    engine.config = replace(engine.config, offline=False)
    calls = []
    def transport(parameters):
        calls.append(parameters)
        assert engine.ledger.db.execute("SELECT COUNT(*) FROM records WHERE kind='newsapi_id_manifest_details_plan'").fetchone()[0] == 1
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, json.dumps({"usedTokens": 4400, "availableTokens": 5000}).encode()
        assert parameters["articleUri"] == ["new"] and parameters["includeArticleBody"] is False
        info = {"uri": "new", "title": "Current article", "url": "https://example.test/new"}
        if unexpected_body:
            info["body"] = "Unexpected body that must not be retained"
        return 200, {"req-tokens": "1"}, json.dumps({"new": {"info": info}}).encode()
    monkeypatch.setattr(manifest, "transport", transport)
    def run(data):
        return engine.execute("newsapi_collection", data, objective="Validate metadata-only software", actor="test", versions=versions)
    result = run({"action": "id_manifest_details", "execute": True})
    assert result["budget"]["reported_tokens"] == 1 and result["unavailable_metadata"] == int(unexpected_body)
    assert result["differences"][1]["metadata"]["title"] == "Saved article"
    assert "body" not in result["differences"][1]["metadata"]
    receipt = engine.ledger.get(result["metadata_receipt"], "newsapi_id_receipt")
    assert (receipt["raw_response"] is None) is unexpected_body
    if unexpected_body:
        assert receipt["response"] is None and result["budget"]["unresolved_outcomes"]
    reused = run({"action": "id_manifest_details", "reuse_result": result["id"]})
    assert reused["id"] == result["id"] and reused["reused"]
    assert len(calls) == 3
