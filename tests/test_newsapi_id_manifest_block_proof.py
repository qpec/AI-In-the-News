from dataclasses import replace
import io
import json
import zipfile

import pytest

from newsresearch import newsapi_collection as collection
from newsresearch import newsapi_id_manifest as source
from newsresearch import newsapi_id_manifest_block_proof as module
from newsresearch import newsapi_id_manifest_quarter_proof as quarter
from newsresearch.common import ResearchError, canonical
from test_newsapi_id_manifest_quarter_proof import (
    old_frames, quarter_receipts,
    test_full_audited_quarter_run_replays_raw_evidence_and_counts_all_phase_costs as prepare_quarter_integration,
)


def block_receipts():
    groups = [["2026-Q1", "2026-Q2"], ["2026-Q3"], ["2026-Q4", "2026-new"]]
    output = []
    for index, parameters in enumerate(module.templates()):
        ids = sorted(groups[index//2], reverse=not parameters["uriWgtListSortByAsc"])
        output.append({"id": f"block-{index}", "parameters": parameters, "outcome": "received", "http_status": 200,
            "headers": {"req-archive": "1", "req-tokens": "5"}, "billed_tokens": 5,
            "response": {"uriWgtList": {"totalResults": len(ids), "results": [f"{uri}:1" for uri in ids]}}})
    return output


def prepared_frames():
    baseline, identities, annual, frames = old_frames()
    previous, quarter_frames = quarter.compare_quarters(baseline, identities, annual, frames, quarter_receipts())
    annual["years"] = [dict(y) for y in previous["years"]]
    frames["2020-01-01"] = quarter_frames["2020-01-01"]
    return baseline, identities, previous, annual, frames


def test_exact_archive_block_templates_do_not_refetch_other_years():
    assert module.WINDOWS == [("2026-01-01", "2026-04-30"), ("2026-05-01", "2026-08-31"), ("2026-09-01", "2026-10-15")]
    assert len(module.templates()) == 6
    for parameters in module.templates():
        assert parameters["uriWgtListPage"] == 1 and parameters["uriWgtListCount"] == 5000
        assert {**parameters, "uriWgtListSortByAsc": True} == source.request(parameters["dateStart"], parameters["dateEnd"], 1, 5000)


def test_block_sets_reuse_settled_2020_and_report_2026_missing_id():
    baseline, identities, previous, annual, frames = prepared_frames()
    result, selected = module._compare(baseline, identities, previous, annual, frames, block_receipts())
    assert result["complete"] and result["ascending_reverse_equal"]
    year2020 = next(y for y in result["years"] if y["year"] == "2020")
    year2026 = next(y for y in result["years"] if y["year"] == "2026")
    assert year2020["verification_method"] == "reused_matching_2020_quarters"
    assert year2026["manifest_only_ids"] == ["2026-new"] and year2026["saved_coverage_of_reverse_percent"] == 80
    assert year2026["expected_pages"] == 6
    assert selected["2020-01-01"] == frames["2020-01-01"]


@pytest.mark.parametrize("failure", ["recent_backend", "missing", "multipage", "pair_disagreement", "overlap"])
def test_archive_block_failures_remain_unsettled_with_prior_missing_candidates(failure):
    receipts = block_receipts()
    if failure == "recent_backend":
        receipts[0]["headers"]["req-archive"] = "0"
    elif failure == "missing":
        receipts.pop(0)
    elif failure == "multipage":
        receipts[0]["response"]["uriWgtList"].update(totalResults=5001, results=[str(n) for n in range(5000)])
    elif failure == "pair_disagreement":
        receipts[0]["response"]["uriWgtList"].update(totalResults=2, results=["different:1", "2026-Q2:1"])
    else:
        for index in (2, 3):
            receipts[index]["response"]["uriWgtList"].update(totalResults=1, results=["2026-Q1:1"])
    baseline, identities, previous, annual, frames = prepared_frames()
    result, _ = module._compare(baseline, identities, previous, annual, frames, receipts)
    assert not result["complete"]
    row = next(y for y in result["years"] if y["year"] == "2026")
    assert row["saved_only_ids"] is None and row["saved_coverage_of_reverse_percent"] is None
    assert result["observed_missing_candidate_count"] >= 1
    assert "2026-new" in {r["article_uri"] for r in result["observed_missing_candidates"]}
    assert all(r["confirmed_in_settled_blocks"] is None for r in result["observed_missing_candidates"])


def test_full_audited_block_run_uses_guarded_reservations_and_replays_all_evidence(engine, monkeypatch):
    # This audited fixture builds eight original partitions, differing annual
    # orders, sixteen quarter receipts, metadata and an anchored quarter proof.
    prepare_quarter_integration(engine, monkeypatch, recent_q4=False)
    previous = source.records(engine, "newsapi_id_manifest_quarter_proof")[-1]
    quarter_versions = previous["versions"]
    monkeypatch.setattr(collection, "run", module.source)
    diagnostic = engine.execute("newsapi_collection", {}, objective="Audit synthetic block source", actor="test", versions=quarter_versions)
    assert diagnostic["source_id"] == previous["id"] and diagnostic["new_api_calls"] == 0
    assert len(diagnostic["diagnostics"]) == 8
    def register(engine, session, context, data):
        policy = {"method": source.METHOD, "block_method": module.BLOCK_METHOD, "block_source": previous["id"],
            "block_source_diagnostic": diagnostic["id"], "block_templates": module.templates(), "block_reservation": 50,
            "baseline_audit": previous["baseline_audit"], "authorization_id": source.AUTH_ID, "max_tokens": source.CAP,
            "allow_metadata": True, "metadata_max_ids": 10}
        identifier = engine.ledger.record(session, "policy", "synthetic-blocks", {"content": policy})
        return {**context.versions, "policy": identifier}
    monkeypatch.setattr(collection, "run", register)
    versions = engine.execute("newsapi_collection", {}, objective="Register synthetic archive blocks", actor="test", versions=quarter_versions)
    monkeypatch.setattr(collection, "run", module.run)
    engine.config = replace(engine.config, offline=False)
    expected = {canonical(r["parameters"]): r["response"] for r in block_receipts()}
    calls = []
    account_used = 4585
    def transport(parameters):
        nonlocal account_used
        calls.append(parameters)
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, canonical({"usedTokens": account_used, "availableTokens": 5000}).encode()
        assert parameters.get("endpointVariant") != "article_info", "Previously available exact-ID metadata must be reused"
        account_used += 5
        return 200, {"req-tokens": "5", "req-archive": "1"}, canonical(expected[canonical(parameters)]).encode()
    monkeypatch.setattr(source, "transport", transport)
    result = engine.execute("newsapi_collection", {"execute": True, "requests": 6},
        objective="Validate full synthetic archive block proof", actor="test", versions=versions)
    assert result["complete"] and result["ascending_reverse_equal"]
    assert result["prior_reported_tokens"] == 165 and result["block_reported_tokens"] == 30
    assert result["additional_metadata_tokens"] == 0
    assert result["budget"]["reported_tokens"] == result["observed_account_delta"] == 195
    assert len([p for p in calls if p.get("resultType") == "uriWgtList"]) == 6
    assert result["proof_self_check"]["archive_block_pairs_checked"] == 3
    assert result["proof_self_check"]["quarter_pairs_checked"] == 8
    intents = source.records(engine, "newsapi_id_intent")
    assert [r["reserved_tokens"] for r in intents if r["purpose"] == "archive_block_confirmation"] == [50]*6
    assert all(r["reserved_tokens"] == 250 for r in intents if r["purpose"] == "quarter_confirmation")
    assert result["differences"][0]["metadata"]["status"] == "available"
    raw = engine.ledger.artifacts.read_bytes(result["proof_artifact"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert json.loads(archive.read("block-verification.json"))["windows"] == result["windows"]
        assert "source-quarter-proof.json" in archive.namelist()
        assert "source-reverse-proof.json" in archive.namelist()
    # A registered block policy cannot turn an unrelated request into a cheaper
    # reservation. This executes the real durable handler boundary and guard.
    def outside(engine, session, context, data):
        return source.dispatch(engine, session, context, source.request("2025-01-01", "2025-12-31", 1, 5000),
            "synthetic-forbidden-override", reserve_override=50)
    monkeypatch.setattr(collection, "run", outside)
    count = len(calls)
    with pytest.raises(ResearchError):
        engine.execute("newsapi_collection", {}, objective="Validate reservation scope guard", actor="test", versions=versions)
    assert len(calls) == count
    monkeypatch.setattr(collection, "run", module.run)
    reused = engine.execute("newsapi_collection", {"execute": True, "requests": 6},
        objective="Reuse exact synthetic block proof", actor="test", versions=versions)
    assert reused["reused"] and reused["new_api_calls"] == 0 and len(calls) == count
