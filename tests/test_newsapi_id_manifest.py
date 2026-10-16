from dataclasses import replace

import pytest

from newsresearch.common import AuditError, ResearchError
from newsresearch.newsapi_collection import collection_request
from newsresearch import newsapi_id_manifest as module


def test_id_query_preserves_original_predicates():
    old = collection_request(("2021-01-01", "2021-12-31"), 1)
    new = module.request("2021-01-01", "2021-12-31", 2)
    for key in ["keyword", "keywordOper", "keywordSearchMode", "keywordLoc", "lang", "dataType", "isDuplicateFilter", "dateStart", "dateEnd"]:
        assert new[key] == old[key]
    assert new["resultType"] == "uriWgtList" and new["uriWgtListCount"] == 1000
    assert "articlesCount" not in new and "includeArticleBody" not in new


def test_documented_uri_weights_and_unsupported_shape():
    assert module.parse_manifest({"uriWgtList": {"results": ["1:0.5", "2"], "totalResults": 2}}) == (["1", "2"], 2)
    with pytest.raises(ResearchError, match="totalResults"):
        module.parse_manifest({"uriWgtList": {"results": ["1"]}})
    with pytest.raises(ResearchError, match="entry format"):
        module.parse_manifest({"uriWgtList": {"results": [{"uri": "1"}], "totalResults": 1}})


def test_partial_processing_is_not_absence_and_complete_comparison_is_bidirectional():
    receipt = {"id": "r", "manifest_status": "valid", "parameters": {"uriWgtListPage": 1}, "normalized_ids": ["b", "c"], "provider_total": 1001}
    partial = module.compare_partition({"a", "b"}, [receipt])
    assert partial["saved_only_ids"] is None and not partial["complete"]
    assert partial["manifest_only_ids"] == ["c"]
    complete = module.compare_partition({"a", "b"}, [{**receipt, "provider_total": 2}])
    assert complete["complete"] and complete["manifest_only_ids"] == ["c"] and complete["saved_only_ids"] == ["a"]
    assert complete["saved_coverage_of_manifest_percent"] == 50


def test_unknown_charges_keep_reservations_and_unknown_dispatch_blocks():
    intents = [{"attempt": "a", "reserved_tokens": 50}, {"attempt": "b", "reserved_tokens": 50}]
    value = module.accounting(intents, [{"attempt": "a", "billed_tokens": 5, "outcome": "received"}])
    assert value["reported_tokens"] == 5 and value["conservative_accounted_tokens"] == 55
    assert value["unresolved_outcomes"] == value["unknown_individual_costs"] == ["b"]


def test_larger_phase_keeps_original_filters_and_never_mixes_offsets():
    small = module.request("2020-01-01", "2020-12-31", 1)
    large = module.request("2020-01-01", "2020-12-31", 1, 5000)
    assert {**small, "uriWgtListCount": 5000} == large
    receipts = [
        {"id": "calibration", "manifest_status": "valid", "parameters": small,
            "normalized_ids": ["a"], "provider_total": 1},
        {"id": "new-phase", "manifest_status": "valid", "parameters": large,
            "normalized_ids": ["a", "b"], "provider_total": 2},
    ]
    compared = module.compare_partition({"a", "b"}, receipts, page_size=5000)
    assert compared["complete"] and compared["manifest_ids_seen"] == 2
    assert compared["manifest_receipts"] == ["new-phase"]
    assert compared["duplicate_id_occurrences"] == 0


def test_budget_is_cumulative_across_page_sizes_and_missing_usage_costs():
    intents = [{"attempt": "small", "reserved_tokens": 50},
        {"attempt": "large", "reserved_tokens": 250}, {"attempt": "usage", "reserved_tokens": 5}]
    receipts = [{"attempt": "small", "outcome": "received", "billed_tokens": 5},
        {"attempt": "large", "outcome": "received", "billed_tokens": 5},
        {"attempt": "usage", "outcome": "received", "billed_tokens": None}]
    budget = module.accounting(intents, receipts)
    assert budget["reported_tokens"] == 10 and budget["conservative_accounted_tokens"] == 15
    assert budget["unknown_individual_costs"] == ["usage"] and not budget["unresolved_outcomes"]


def setup(engine, monkeypatch):
    period = ["2024-01-01", "2024-12-31"]
    definitions = {"protocol": {"method": module.METHOD}, "question": {"text": "Synthetic capped ID test"},
        "selection": {"rules": "Synthetic fixture"}, "profile": {"mode": "exploratory"},
        "policy": {"method": module.METHOD, "authorization_id": module.AUTH_ID, "max_tokens": module.CAP,
            "baseline_audit": "synthetic", "periods": [period], "templates": [module.request(*period, 1)]}}
    versions = {kind: engine.execute("version", {"kind": kind, "key": "id-manifest-test", "content": content},
        objective="Validate capped ID test software", actor="test")["id"] for kind, content in definitions.items()}
    baseline = {"periods": [{"date_start": period[0], "date_end": period[1], "year": "2024"}],
                "query_parameters": collection_request(tuple(period), 1)}
    monkeypatch.setattr(module, "load_baseline", lambda *_: (baseline, {period[0]: {"uri_counts": {"a": 1, "b": 1}}}))
    monkeypatch.setenv("EVENTREGISTRY_API_KEY", "synthetic-transient-value")
    engine.config = replace(engine.config, offline=False)
    return lambda: engine.execute("newsapi_collection", {"action": "id_manifest_test", "execute": True, "requests": 1},
        objective="Validate capped ID test software", actor="test", versions=versions)


def test_durable_intent_failure_prevents_paid_request(engine, monkeypatch):
    run = setup(engine, monkeypatch)
    original = engine.ledger.record
    def record(session, kind, *args, **kwargs):
        if kind == "newsapi_id_intent":
            raise AuditError("Synthetic durable-intent failure")
        return original(session, kind, *args, **kwargs)
    monkeypatch.setattr(engine.ledger, "record", record)
    monkeypatch.setattr(module, "transport", lambda _: pytest.fail("No transport before intent"))
    with pytest.raises(AuditError):
        run()


def test_account_ceiling_stops_search_before_dispatch(engine, monkeypatch):
    import json
    run = setup(engine, monkeypatch)
    calls = []
    def transport(params):
        calls.append(params)
        return 200, {"req-tokens": "0"}, json.dumps({"usedTokens": 4990, "availableTokens": 5000}).encode()
    monkeypatch.setattr(module, "transport", transport)
    result = run()
    assert result["stop_reason"] == "budget_limit" and result["budget"]["reported_tokens"] == 0
    assert all(p == {"endpointVariant": "usage"} for p in calls)
    assert result["years"][0]["saved_only_ids"] is None


@pytest.mark.parametrize("archive,complete", [(None, False), ("0", False), ("1", True)])
def test_archive_confirmation_required_for_accepting_manifest(engine, monkeypatch, archive, complete):
    import json
    run = setup(engine, monkeypatch)
    def transport(params):
        if params == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, json.dumps({"usedTokens": 4400, "availableTokens": 5000}).encode()
        headers = {"req-tokens": "5"}
        if archive is not None:
            headers["req-archive"] = archive
        return 200, headers, json.dumps({"uriWgtList": {"totalResults": 2, "results": ["a:1", "b:1"]}}).encode()
    monkeypatch.setattr(module, "transport", transport)
    result = run()
    assert result["years"][0]["complete"] is complete
    assert result["budget"]["reported_tokens"] == 5
    assert result["years"][0]["saved_only_ids"] == ([] if complete else None)
