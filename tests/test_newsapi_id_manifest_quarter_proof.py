from dataclasses import replace
import hashlib
import io
import json
from types import SimpleNamespace
import zipfile

import pytest

from newsresearch import newsapi_id_manifest as source
from newsresearch import newsapi_id_manifest_quarter_proof as module
from newsresearch import newsapi_collection as collection
from newsresearch import newsapi_id_manifest_proof as annual
from newsresearch.common import Context, ResearchError, canonical


def quarter_receipts():
    receipts = []
    for index, parameters in enumerate(module.templates()):
        start = parameters["dateStart"]
        quarter = (int(start[5:7])-1)//3+1
        ids = [f"{start[:4]}-Q{quarter}"]
        if start == "2026-10-01":
            ids.append("2026-new")
        if not parameters["uriWgtListSortByAsc"]:
            ids.reverse()
        receipts.append({"id": f"r{index}", "parameters": parameters, "outcome": "received", "http_status": 200,
            "headers": {"req-archive": "1", "req-tokens": "5"}, "billed_tokens": 5,
            "response": {"uriWgtList": {"results": [f"{uri}:1" for uri in ids], "totalResults": len(ids)}}})
    return receipts


def old_frames():
    baseline = {"periods": []}
    frames, years, identities = {}, [], {}
    for year in map(str, range(2020, 2027)):
        ids = {f"{year}-Q{q}" for q in range(1, 5)}
        first, reverse = set(ids), set(ids)
        if year == "2020":
            first.remove("2020-Q1")
            first.add("annual-sort-instability")
        if year == "2026":
            reverse.add("2026-new")
        start = f"{year}-01-01"
        end = f"{year}-12-31" if year != "2026" else "2026-10-15"
        baseline["periods"].append({"year": year, "date_start": start, "date_end": end})
        frames[start] = {"year": year, "saved": ids, "ascending": first, "reverse": reverse}
        identities[start] = {"uri_counts": dict.fromkeys(ids, 1)}
        years.append({"year": year, "saved_ids": len(ids), "ascending_ids": len(first), "reverse_ids": len(reverse),
            "complete": True, "ascending_reverse_equal": first == reverse, "manifest_only_ids": sorted(reverse-ids),
            "saved_only_ids": sorted(ids-reverse), "common_ids": len(ids & reverse), "saved_equals_reverse": ids == reverse})
    return baseline, identities, {"years": years}, frames


def test_quarter_templates_preserve_predicates_and_exact_nonoverlapping_dates():
    templates = module.templates()
    assert len(templates) == 16
    assert len(module.WINDOWS) == 8
    assert module.WINDOWS[3] == ("2020-10-01", "2020-12-31")
    assert module.WINDOWS[-1] == ("2026-10-01", "2026-10-15")
    for parameters in templates:
        old = source.request(parameters["dateStart"], parameters["dateEnd"], 1, 5000)
        assert {**parameters, "uriWgtListSortByAsc": True} == old
        assert parameters["uriWgtListCount"] == 5000 and parameters["uriWgtListPage"] == 1


def test_quarters_resolve_annual_sort_difference_and_reuse_five_stable_years():
    baseline, identities, old, frames = old_frames()
    result, selected = module.compare_quarters(baseline, identities, old, frames, quarter_receipts())
    assert result["complete"] and result["ascending_reverse_equal"]
    assert len([y for y in result["years"] if y["verification_method"] == "reused_matching_annual_orders"]) == 5
    year2020 = next(y for y in result["years"] if y["year"] == "2020")
    assert year2020["old_ascending_only_vs_quarters"] == ["annual-sort-instability"]
    assert year2020["quarters_only_vs_old_ascending"] == ["2020-Q1"]
    assert year2020["saved_equals_reverse"] and year2020["saved_coverage_of_reverse_percent"] == 100
    year2026 = next(y for y in result["years"] if y["year"] == "2026")
    assert year2026["manifest_only_ids"] == ["2026-new"]
    assert year2026["saved_coverage_of_reverse_percent"] == 80
    assert selected["2020-01-01"]["ascending"] == selected["2020-01-01"]["reverse"]
    assert all(r["parameters"]["dateStart"][:4] in ("2020", "2026") for r in quarter_receipts())


@pytest.mark.parametrize("failure", ["multipage", "archive", "duplicate", "partial", "missing", "repeated"])
def test_failed_or_missing_single_page_never_establishes_completeness(failure):
    receipts = quarter_receipts()
    response = receipts[0]["response"]["uriWgtList"]
    if failure == "multipage":
        response["totalResults"] = 5001
        response["results"] = [str(n) for n in range(5000)]
    elif failure == "archive":
        receipts[0]["headers"]["req-archive"] = "0"
    elif failure == "duplicate":
        response.update(totalResults=2, results=["a:1", "a:2"])
    elif failure == "partial":
        response["totalResults"] = 2
    elif failure == "missing":
        receipts.pop(0)
    else:
        receipts.append({**receipts[0], "id": "repeated"})
    baseline, identities, old, frames = old_frames()
    result, _ = module.compare_quarters(baseline, identities, old, frames, receipts)
    assert not result["complete"]
    row = next(y for y in result["years"] if y["year"] == "2020")
    assert row["saved_only_ids"] is None and row["saved_coverage_of_reverse_percent"] is None


def test_pair_order_disagreement_is_explicit_and_not_complete():
    receipts = quarter_receipts()
    receipts[1]["response"]["uriWgtList"]["results"] = ["different-id:1"]
    baseline, identities, old, frames = old_frames()
    result, _ = module.compare_quarters(baseline, identities, old, frames, receipts)
    assert result["all_windows_enumerated"]
    assert not result["complete"] and result["ascending_reverse_equal"] is False
    assert result["windows"][0]["ascending_reverse_equal"] is False


def test_overlap_between_quarters_is_not_counted_twice_as_success():
    receipts = quarter_receipts()
    for index in (2, 3):
        receipts[index]["response"]["uriWgtList"]["results"] = ["2020-Q1:1"]
    baseline, identities, old, frames = old_frames()
    result, _ = module.compare_quarters(baseline, identities, old, frames, receipts)
    assert not result["complete"]
    row = next(y for y in result["years"] if y["year"] == "2020")
    assert row["cross_quarter_duplicate_occurrences"] == {"ascending": 1, "reverse": 1}


def test_zero_result_quarter_can_be_exhaustively_confirmed():
    receipts = quarter_receipts()
    for index in (0, 1):
        receipts[index]["response"]["uriWgtList"].update(totalResults=0, results=[])
    windows = module.inspect_windows(receipts)
    assert windows[0]["complete"] and windows[0]["ascending_reverse_equal"]
    assert windows[0]["ascending"]["ids"] == []


def test_only_previously_matching_years_may_be_reused():
    baseline, identities, old, frames = old_frames()
    next(y for y in old["years"] if y["year"] == "2022")["ascending_reverse_equal"] = False
    with pytest.raises(ResearchError, match="five previously matching"):
        module.compare_quarters(baseline, identities, old, frames, quarter_receipts())


def test_shared_budget_failure_retains_missing_metadata_without_new_authorization(monkeypatch):
    result = {"baseline_audit": "baseline", "complete": True, "ascending_reverse_equal": True,
        "years": [{"year": "2026", "manifest_only_ids": ["new"], "saved_only_ids": []}]}
    monkeypatch.setattr(module, "records", lambda *_: [])
    calls = []
    def dispatch(engine, session, context, parameters, purpose):
        calls.append(parameters)
        raise ResearchError("ID-manifest authorization budget reached")
    monkeypatch.setattr(module, "dispatch", dispatch)
    count = module._metadata(SimpleNamespace(), "session", Context("Synthetic budget test", "test"), result, {}, {"allow_metadata": True}, True)
    assert count == 0 and len(calls) == 1
    assert result["metadata_status"] == "budget_or_unresolved_charge"
    assert result["unavailable_metadata"] == 1 and result["differences"][0]["metadata"] is None
    assert module.AUTH_ID == source.AUTH_ID and module.CAP == 583


def test_metadata_cap_fetches_first_ten_and_preserves_remaining_pending_ids(monkeypatch):
    ids = [f"new-{n:02}" for n in range(12)]
    result = {"baseline_audit": "baseline", "complete": True, "ascending_reverse_equal": True,
        "years": [{"year": "2026", "manifest_only_ids": ids, "saved_only_ids": []}]}
    monkeypatch.setattr(module, "records", lambda *_: [])
    requests = []
    def dispatch(engine, session, context, parameters, purpose):
        requests.append(parameters)
        return {"id": "metadata-receipt", "http_status": 200, "response": {
            uri: {"info": {"uri": uri, "title": "Synthetic title"}} for uri in parameters["articleUri"]}}
    monkeypatch.setattr(module, "dispatch", dispatch)
    count = module._metadata(SimpleNamespace(), "session", Context("Synthetic metadata cap test", "test"), result, {}, {"allow_metadata": True}, True)
    assert count == 1 and requests[0]["articleUri"] == ids[:10]
    assert result["metadata_pending_ids"] == ids[10:]
    assert result["unavailable_metadata"] == 2
    assert result["differences"][-1]["metadata"] is None


def test_full_audited_quarter_run_replays_raw_evidence_and_counts_all_phase_costs(engine, monkeypatch):
    """Real audited runtime/dispatch/artifacts, with only provider transport synthetic."""
    def bootstrap(engine, session, context, data):
        definitions = {"protocol": {"method": module.QUARTER_METHOD},
            "question": {"text": "Synthetic audited quarter proof integration"},
            "selection": {"rules": "Synthetic saved eight-interval exact-keyword frame"},
            "profile": {"mode": "exploratory"}}
        versions = {kind: engine.ledger.record(session, kind, "quarter-integration", {"content": content})
            for kind, content in definitions.items()}
        baseline, identities, _, frames = old_frames()
        baseline["periods"] = [p for p in baseline["periods"] if p["year"] != "2023"]
        frames.pop("2023-01-01")
        identities.pop("2023-01-01")
        for start, end, uri in [("2023-01-01", "2023-10-14", "2023-first"),
                                ("2023-10-15", "2023-12-31", "2023-second")]:
            baseline["periods"].append({"year": "2023", "date_start": start, "date_end": end})
            frames[start] = {"year": "2023", "saved": {uri}, "ascending": {uri}, "reverse": {uri}}
            identities[start] = {"uri_counts": {uri: 1}, "identifiers": []}
        baseline["periods"].sort(key=lambda p: p["date_start"])
        ref = engine.ledger.artifacts.put(identities)
        engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": ref})
        baseline["identity_manifest"] = ref
        for period in baseline["periods"]:
            start, end = period["date_start"], period["date_end"]
            original = engine.ledger.record(session, "newsapi_collection_receipt", start, {
                "parameters": collection.collection_request((start, end), 1), "raw_response": None,
                "raw_sha256": "a"*64, "response": {"articles": {"results": []}}})
            period.update(receipt_ids=[original], page_details=[{"receipt": original}])
        audit = engine.ledger.record(session, "newsapi_retrieval_audit", "quarter-integration", baseline)
        def save_receipt(attempt, parameters, response, purpose, ids=None):
            cost = 0 if purpose.startswith("usage") else 5
            intent = {"attempt": attempt, "authorization_id": source.AUTH_ID, "reserved_tokens": 5 if cost == 0 else 250,
                "parameters": parameters, "purpose": purpose, "versions": dict(versions)}
            engine.ledger.record(session, "newsapi_id_intent", attempt, intent)
            raw = canonical(response).encode()
            raw_ref = engine.ledger.artifacts.put_bytes(raw)
            engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": raw_ref})
            payload = {**intent, "outcome": "received", "http_status": 200, "billed_tokens": cost,
                "headers": {"req-tokens": str(cost), "req-archive": "1"}, "response": response,
                "raw_response": raw_ref, "raw_sha256": hashlib.sha256(raw).hexdigest()}
            if ids is not None:
                payload.update(manifest_status="valid", normalized_ids=ids, provider_total=len(ids))
            identifier = engine.ledger.record(session, "newsapi_id_receipt", attempt, payload)
            return {"id": identifier, **payload}
        save_receipt("initial-usage", {"endpointVariant": "usage"}, {"usedTokens": 4420, "availableTokens": 5000}, "usage_initial")
        asc, reverse = [], []
        for period in baseline["periods"]:
            start, end = period["date_start"], period["date_end"]
            for direction, ascending, target in (("ascending", True, asc), ("reverse", False, reverse)):
                ids = sorted(frames[start][direction], reverse=not ascending)
                parameters = {**source.request(start, end, 1, 5000), "uriWgtListSortByAsc": ascending}
                target.append(save_receipt(f"{start}-{direction}", parameters,
                    {"uriWgtList": {"totalResults": len(ids), "results": [f"{uri}:1" for uri in ids]}}, "manifest", ids))
        first = {"authorization_id": source.AUTH_ID, "versions": dict(versions), "page_size": 5000, "baseline_audit": audit,
            "periods": [{"complete": True, "manifest_receipts": [r["id"]]} for r in asc]}
        first_id = engine.ledger.record(session, "newsapi_id_manifest_test", "quarter-integration", first)
        comparison, _ = annual.compare_frames(baseline, identities, asc, reverse)
        proof = {**comparison, "authorization_id": source.AUTH_ID, "versions": dict(versions),
            "baseline_audit": audit, "confirmation_source": first_id, "reverse_receipt_ids": [r["id"] for r in reverse],
            "budget": {"reported_tokens": 80}}
        proof_id = engine.ledger.record(session, "newsapi_id_manifest_proof", "quarter-integration", proof)
        policy = {"method": source.METHOD, "quarter_method": module.QUARTER_METHOD,
            "quarter_source": proof_id, "quarter_templates": module.templates(), "baseline_audit": audit,
            "authorization_id": source.AUTH_ID, "max_tokens": source.CAP, "allow_metadata": True, "metadata_max_ids": 10}
        versions["policy"] = engine.ledger.record(session, "policy", "quarter-integration", {"content": policy})
        return versions

    monkeypatch.setattr(collection, "run", bootstrap)
    versions = engine.execute("newsapi_collection", {}, objective="Prepare synthetic audited integration", actor="test")
    monkeypatch.setattr(collection, "run", module.run)
    engine.config = replace(engine.config, offline=False)
    monkeypatch.setenv("EVENTREGISTRY_API_KEY", "synthetic-transient-value")
    expected = {canonical(r["parameters"]): r["response"] for r in quarter_receipts()}
    calls = []
    account_used = 4500
    def transport(parameters):
        nonlocal account_used
        calls.append(parameters)
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, canonical({"usedTokens": account_used, "availableTokens": 5000}).encode()
        account_used += 5
        if parameters.get("endpointVariant") == "article_info":
            assert parameters["articleUri"] == ["2026-new"]
            assert parameters["includeArticleBody"] is False
            response = {"2026-new": {"info": {"uri": "2026-new", "title": "Synthetic new article",
                "url": "https://example.test/new", "date": "2026-10-15", "lang": "nld"}}}
        else:
            response = expected[canonical(parameters)]
        return 200, {"req-tokens": "5", "req-archive": "1"}, canonical(response).encode()
    monkeypatch.setattr(source, "transport", transport)
    result = engine.execute("newsapi_collection", {"execute": True, "requests": 16},
        objective="Validate full synthetic quarter retrieval proof", actor="test", versions=versions)
    assert result["complete"] and result["ascending_reverse_equal"]
    year2020 = next(y for y in result["years"] if y["year"] == "2020")
    year2026 = next(y for y in result["years"] if y["year"] == "2026")
    assert year2020["manifest_only_ids"] == [] and year2020["saved_only_ids"] == []
    assert year2026["manifest_only_ids"] == ["2026-new"]
    assert len([p for p in calls if p.get("resultType") == "uriWgtList"]) == 16
    assert result["quarter_reported_tokens"] == 80 and result["additional_metadata_tokens"] == 5
    assert result["budget"]["reported_tokens"] == result["observed_account_delta"] == 165
    assert result["proof_self_check"]["status"] == "verified"
    assert result["proof_self_check"]["quarter_pairs_checked"] == 8
    raw = engine.ledger.artifacts.read_bytes(result["proof_artifact"])
    assert annual.verify_proof_bytes(raw)["complete_year_comparisons"] == 7
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert "source-reverse-proof.json" in archive.namelist()
        assert json.loads(archive.read("quarter-verification.json"))["windows"] == result["windows"]
        hashes = json.loads(archive.read("file-sha256.json"))["files"]
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == value["sha256"] for name, value in hashes.items())
