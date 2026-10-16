import copy
import io
from types import SimpleNamespace
import zipfile

import pytest

from newsresearch import newsapi_id_manifest as source
from newsresearch import newsapi_id_manifest_minimal_recovery as module
from newsresearch.common import AuditError, Context, ResearchError, canonical
from newsresearch.newsapi_id_manifest_resolution import minimal_enumeration, validate_enumeration
from newsresearch.newsapi_id_manifest_resolution_run import _reconcile
from test_newsapi_id_manifest_resolution import IDS, CONTROL, listing
from test_newsapi_id_manifest_resolution_run import package


def test_minimal_metadata_is_explicit_and_never_silently_accepted_as_original_method():
    parameters = minimal_enumeration(1)
    assert parameters["includeArticleTitle"] is True
    assert parameters["includeArticleUrl"] is parameters["includeArticleImage"] is parameters["includeArticleBody"] is False
    assert minimal_enumeration(1, False)["includeArticleTitle"] is False
    row = {"id": "minimal", "outcome": "received", "http_status": 200, "headers": {"req-archive": "1"},
        "parameters": parameters, "response": listing([CONTROL])}
    assert not validate_enumeration([row], [CONTROL])["complete"]
    assert validate_enumeration([row], [CONTROL], allow_minimal=True)["complete"]


def test_minimal_reservation_is_exactly_registered_and_preserves_unknown_budget(monkeypatch):
    parameters = minimal_enumeration(1)
    policy = {"resolution_method": "nl-cyber-id-manifest-resolution-v1", "authorization_id": source.AUTH_ID, "max_tokens": 583,
        "minimal_metadata_method": module.METHOD, "minimal_metadata_templates": [parameters], "minimal_metadata_reservation": 25}
    engine = SimpleNamespace(_active={"session"}, ledger=SimpleNamespace(get=lambda *args: {"content": policy}))
    context = Context("Validate admission", "test", {"policy": "p"})
    monkeypatch.setattr(source, "records", lambda engine, kind: [{"attempt": "reserved", "reserved_tokens": 558}] if kind == "newsapi_id_intent" else [])
    with pytest.raises(ResearchError, match="Unresolved"):
        source.dispatch(engine, "session", context, parameters, "resolution_minimal_page_1_title_True")
    monkeypatch.setattr(source, "records", lambda engine, kind: [{"attempt": "reserved", "reserved_tokens": 559}] if kind == "newsapi_id_intent" else [])
    with pytest.raises(ResearchError, match="budget"):
        source.dispatch(engine, "session", context, parameters, "resolution_minimal_page_1_title_True")
    policy["minimal_metadata_reservation"] = 24
    with pytest.raises(ResearchError, match="empirical reservation"):
        source.dispatch(engine, "session", context, parameters, "resolution_minimal_page_1_title_True")


def test_minimal_raw_replay_recovers_exact_candidate_ids_without_changing_historical_result():
    docs, archive_type, old = package()
    prepared = {"id": "minimal-prep", "metadata_ids": IDS, "source": "source"}
    parameters = minimal_enumeration(1)
    response = listing([CONTROL, *IDS])
    row = {"id": "minimal", "parameters": parameters, "outcome": "received", "http_status": 200,
        "headers": {"req-archive": "1"}, "response": response, "raw_response": "raw"}
    docs["receipts/minimal.json"] = row
    docs["responses/minimal.json"] = response
    docs["minimal-metadata-recovery.json"] = {"preparation": prepared, "pages": ["minimal"]}
    policy = docs["versions/policy.json"]["content"]
    policy.update(minimal_metadata_method=module.METHOD, minimal_metadata_reservation=25,
        minimal_metadata_templates=[minimal_enumeration(page, title) for page in range(1, 31) for title in (True, False)],
        minimal_metadata_preparation="minimal-prep")
    enumeration = validate_enumeration([row], [CONTROL], allow_minimal=True)
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("years/2026/saved-ids.txt", docs["years/2026/saved-ids.txt"])
        archive.writestr("source-block-proof.json", canonical(docs["source-block-proof.json"]))
    historical = copy.deepcopy(old["resolution_summary"])
    expected = _reconcile({"_proof_bytes": inner.getvalue()}, prepared, historical["controls"], enumeration)
    comparison = {"resolution_summary": historical, "minimal_recovery_summary": expected}
    checked = module.verify_package(archive_type(docs), comparison)
    assert checked["complete"] and checked["records"] == 7
    assert expected["retrievable_2026_missing_saved_ids"] == IDS
    assert all(r["classification"] == "metadata_retrievable" for r in expected["candidate_resolution"]["rows"])
    assert comparison["resolution_summary"] == historical
    docs["responses/minimal.json"]["articles"]["results"][0]["lang"] = "eng"
    with pytest.raises(AuditError, match="reproduce"):
        module.verify_package(archive_type(docs), comparison)
