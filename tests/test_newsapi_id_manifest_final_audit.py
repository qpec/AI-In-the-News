import copy
import hashlib
import io
import json
import zipfile

import pytest

from newsresearch import newsapi_collection as collection
from newsresearch import newsapi_id_manifest as source
from newsresearch import newsapi_id_manifest_final_audit as module
from newsresearch import newsapi_id_manifest_proof as proof
from newsresearch.common import AuditError, canonical
from test_newsapi_id_manifest_block_proof import (
    prepared_frames, block_receipts,
    test_full_audited_block_run_uses_guarded_reservations_and_replays_all_evidence as prepare_block,
)
from newsresearch import newsapi_id_manifest_block_proof as block


def unsettled():
    baseline, identities, previous, annual, frames = prepared_frames()
    result, frames = block._compare(baseline, identities, previous, annual, frames, block_receipts())
    result["windows"][-1]["reverse"]["ids"].append("final-new")
    result["windows"][-1]["reverse"]["provider_total"] += 1
    result["windows"][-1].update(complete=False, ascending_reverse_equal=False)
    row = next(y for y in result["years"] if y["year"] == "2026")
    row.update(complete=False, ascending_reverse_equal=False, reverse_ids=6,
        manifest_only_ids=["2026-new", "final-new"], saved_only_ids=None)
    frames["2026-01-01"]["reverse"].add("final-new")
    return result, frames


@pytest.mark.parametrize("stamp,lang,expected", [
    ("2026-10-16", "nld", "excluded"), ("2019-12-31", "nld", "excluded"),
    ("2026-10-15", "eng", "excluded"), ("2026-10-15", "nld", "eligible"),
    ("bad-date", "nld", "unknown"), (None, None, "unknown"),
])
def test_scope_uses_only_available_exact_reported_date_and_language(stamp, lang, expected):
    assert module.decide(["new"], {"new": {"status": "available", "date": stamp, "lang": lang}})[0]["decision"] == expected
    assert module.decide(["new"], {"new": {"status": "unavailable", "date": "2026-10-16", "lang": "eng"}})[0]["decision"] == "unknown"


@pytest.mark.parametrize("status,stamp,complete", [("available", "2026-10-16", True),
    ("available", "2026-10-15", False), ("unavailable", None, False)])
def test_only_proven_outside_scope_difference_resolves_pair(status, stamp, complete):
    previous, frames = unsettled()
    decisions = module.decide(["2026-new", "final-new"], {
        "2026-new": {"status": "available", "date": "2026-10-15", "lang": "nld"},
        "final-new": {"status": status, "date": stamp, "lang": "nld"}})
    result, selected, _ = module.apply_scope(previous, frames, decisions)
    assert result["complete"] is complete
    row = next(y for y in result["years"] if y["year"] == "2026")
    assert row["raw_reverse_ids"] == 6
    assert row["saved_only_ids"] == ([] if complete else None)
    assert ("final-new" not in selected["2026-01-01"]["reverse"]) is complete


def test_missing_raw_direction_and_cross_block_overlap_cannot_be_repaired_by_metadata():
    previous, frames = unsettled()
    decisions = module.decide(["final-new"], {"final-new": {"status": "available", "date": "2026-10-16", "lang": "nld"}})
    previous["windows"][0]["ascending"]["complete"] = False
    assert not module.apply_scope(previous, frames, decisions)[0]["complete"]
    previous["windows"][0]["ascending"]["complete"] = True
    for direction in ("ascending", "reverse"):
        previous["windows"][1][direction]["ids"].append(previous["windows"][0][direction]["ids"][0])
    assert not module.apply_scope(previous, frames, decisions)[0]["complete"]


@pytest.mark.parametrize("metadata_case", ["outside", "inside", "missing"])
def test_full_audited_metadata_only_final_proof_replays_raw_scope(engine, monkeypatch, metadata_case):
    prepare_block(engine, monkeypatch)
    prior = source.records(engine, "newsapi_id_manifest_block_proof")[-1]
    def evolve(engine, session, context, data):
        previous = copy.deepcopy(prior)
        raw_zip = engine.ledger.artifacts.read_bytes(previous["proof_artifact"])
        baseline, _ = source.load_baseline(engine, previous["baseline_audit"])
        first = {"id": previous["confirmation_source"], **engine.ledger.get(previous["confirmation_source"], "newsapi_id_manifest_test")}
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as archive:
            frames = {p["date_start"]: {"year": p["year"], **{d: set(archive.read(f"partitions/{p['date_start']}/{d}-ids.txt").decode().splitlines())
                for d in ("saved", "ascending", "reverse")}} for p in baseline["periods"]}
            quarters = json.loads(archive.read("quarter-verification.json"))
        receipt = copy.deepcopy(engine.ledger.get(previous["windows"][-1]["reverse"]["attempts"][0], "newsapi_id_receipt"))
        ids = sorted(set(receipt["normalized_ids"]) | {"final-new"})
        receipt.update(attempt="synthetic-provider-change", purpose="synthetic_retained_block", versions=context.versions)
        receipt["response"] = {"uriWgtList": {"totalResults": len(ids), "results": [f"{uri}:1" for uri in ids]}}
        receipt.update(normalized_ids=ids, provider_total=len(ids), billed_tokens=5, reserved_tokens=50)
        engine.ledger.record(session, "newsapi_id_intent", receipt["attempt"], {k: receipt[k] for k in
            ("attempt", "authorization_id", "reserved_tokens", "parameters", "purpose", "versions")})
        raw = canonical(receipt["response"]).encode()
        ref = engine.ledger.artifacts.put_bytes(raw)
        engine.ledger.append(session, "retrieval.artifact.saved", {"artifact": ref})
        receipt.update(raw_response=ref, raw_sha256=hashlib.sha256(raw).hexdigest())
        identifier = engine.ledger.record(session, "newsapi_id_receipt", receipt["attempt"], receipt)
        direction = previous["windows"][-1]["reverse"]
        direction.update(ids=ids, provider_total=len(ids), attempts=[identifier], receipt=identifier)
        previous["windows"][-1].update(complete=False, ascending_reverse_equal=False)
        row = next(y for y in previous["years"] if y["year"] == "2026")
        row.update(complete=False, ascending_reverse_equal=False, reverse_ids=6, reverse_ids_seen=6,
            manifest_ids_seen=6, manifest_only_ids=["2026-new", "final-new"], reverse_only_vs_saved_ids=["2026-new", "final-new"],
            saved_only_ids=None, saved_only_vs_reverse_ids=None, saved_coverage_of_reverse_percent=None)
        previous.update(complete=False, ascending_reverse_equal=False,
            observed_missing_candidates=[{"article_uri": uri, "year": "2026"} for uri in ("2026-new", "final-new")],
            budget=source.accounting(source.records(engine, "newsapi_id_intent"), source.records(engine, "newsapi_id_receipt")))
        frames["2026-01-01"]["reverse"].add("final-new")
        previous.pop("id", None)
        ref = proof.evidence_zip(engine, session, context, baseline, first, previous, frames,
            extra_json={"quarter-verification.json": quarters, "block-verification.json": {"windows": previous["windows"]}}, method=block.BLOCK_METHOD)
        previous.update(proof_artifact=ref, versions=context.versions)
        proof.verify_proof_bytes(engine.ledger.artifacts.read_bytes(ref))
        identifier = engine.ledger.record(session, "newsapi_id_manifest_block_proof", "synthetic-provider-change", previous)
        return {"id": identifier, **previous}
    monkeypatch.setattr(collection, "run", evolve)
    previous = engine.execute("newsapi_collection", {}, objective="Retain synthetic provider ID change", actor="test", versions=prior["versions"])
    monkeypatch.setattr(collection, "run", module.source)
    diagnostic = engine.execute("newsapi_collection", {}, objective="Diagnose synthetic exact-ID difference", actor="test", versions=prior["versions"])
    assert diagnostic["metadata_ids"] == ["2026-new", "final-new"] and diagnostic["new_api_calls"] == 0
    def register(engine, session, context, data):
        policy = {"method": source.METHOD, "final_method": module.FINAL_METHOD, "final_source": previous["id"],
            "final_source_diagnostic": diagnostic["id"], "final_metadata_ids": diagnostic["metadata_ids"],
            "allow_metadata_scope_filter": True, "authorization_id": source.AUTH_ID, "max_tokens": 583,
            "baseline_audit": previous["baseline_audit"]}
        identifier = engine.ledger.record(session, "policy", "synthetic-final", {"content": policy})
        return {**context.versions, "policy": identifier}
    monkeypatch.setattr(collection, "run", register)
    versions = engine.execute("newsapi_collection", {}, objective="Register synthetic final metadata scope policy", actor="test", versions=prior["versions"])
    calls = []
    account = 4620
    def transport(parameters):
        nonlocal account
        calls.append(parameters)
        if parameters == {"endpointVariant": "usage"}:
            return 200, {"req-tokens": "0"}, canonical({"usedTokens": account, "availableTokens": 5000}).encode()
        assert parameters["endpointVariant"] == "article_info" and parameters["articleUri"] == ["final-new"]
        assert parameters["includeArticleBody"] is False and parameters["articleBodyLen"] == 0
        account += 5
        response = {} if metadata_case == "missing" else {"final-new": {"info": {"uri": "final-new", "date":
            "2026-10-16" if metadata_case == "outside" else "2026-10-15", "lang": "nld", "title": "Synthetic candidate", "url": "https://example.test/final"}}}
        return 200, {"req-tokens": "5"}, canonical(response).encode()
    monkeypatch.setattr(source, "transport", transport)
    monkeypatch.setattr(collection, "run", module.run)
    result = engine.execute("newsapi_collection", {"execute": True}, objective="Audit synthetic metadata-only final scope", actor="test", versions=versions)
    assert result["complete"] is (metadata_case == "outside")
    assert result["prior_reported_tokens"] == 200 and result["additional_metadata_tokens"] == 5
    assert result["budget"]["reported_tokens"] == result["observed_account_delta"] == 205
    assert len(calls) == 3 and not any(p.get("resultType") == "uriWgtList" for p in calls)
    assert len(result["differences"]) == 2
    checks = result["proof_self_check"]
    assert checks["archive_block_pairs_checked"] == 3 and checks["quarter_pairs_checked"] == 8
    assert checks["final_scope_verification"]["metadata_scope_checks"] == 2
    assert checks["final_scope_verification"]["unknown_metadata"] == (metadata_case == "missing")
    raw = engine.ledger.artifacts.read_bytes(result["proof_artifact"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    document = json.loads(files["final-scope-verification.json"])
    document["excluded_ids"] = ["2026-new"]
    files["final-scope-verification.json"] = canonical(document).encode()
    class ChangedArchive:
        def read(self, name):
            return files[name]
    with pytest.raises(AuditError, match="exclusions"):
        module.verify_scope_package(ChangedArchive(), result)
