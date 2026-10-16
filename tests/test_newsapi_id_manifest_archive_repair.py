import copy

import pytest

from newsresearch import newsapi_id_manifest_archive_repair as module
from newsresearch.newsapi_id_manifest import accounting
from newsresearch.common import AuditError, canonical
from test_newsapi_id_manifest_resolution import IDS, CONTROL, listing


def prepared():
    return {"id": "prep", "metadata_ids": IDS, "controls": [CONTROL, "numeric"],
        "parameters": {"articleUri": [*IDS, CONTROL, "numeric"], "dateStart": "2026-01-01"},
        "prior_lookup_receipts": {"sdk": "sdk", "list": "list"}}


@pytest.mark.parametrize("stamp,language,decision", [("2026-09-01", "nld", "eligible"), ("2026-10-16", "nld", "excluded"), ("2026-09-01", "eng", "excluded")])
def test_archive_metadata_scope_never_guesses_uris_or_provider_completeness(stamp, language, decision):
    response = listing([*IDS, CONTROL, "numeric"])
    for row in response["articles"]["results"]:
        row.update(date=stamp, lang=language)
    result = module.summarize({"outcome": "received", "http_status": 200, "headers": {"req-archive": "1"}, "response": response},
        prepared(), {CONTROL, "numeric"}, {"sdk": {"req-archive": "0"}})
    assert result["all_six_metadata_recovered"]
    assert all(r["decision"] == decision for r in result["rows"])
    assert result["archive_header"] == "1" and not result["provider_population_completeness_proven"]
    assert len(result["eligible_missing_from_original_saved_ids"]) == (6 if decision == "eligible" else 0)
    response["articles"]["results"][0]["uri"] = "unregistered-alias"
    result = module.summarize({"outcome": "received", "http_status": 200, "response": response}, prepared(), {CONTROL}, {})
    assert len(result["unknown_ids"]) == 6


def test_received_response_reconciliation_preserves_cost_and_does_not_resolve_transport_unknown():
    intent = {"attempt": "attempt", "reserved_tokens": 50}
    receipt = {"id": "receipt", "attempt": "attempt", "outcome": "unknown", "http_status": 200,
        "error_type": "ResearchError", "raw_response": None, "raw_sha256": "a"*64, "billed_tokens": 5}
    note = {"attempt": "attempt", "receipt": "receipt", "resolution": "http_response_received_retention_rejected", "raw_sha256": "a"*64, "billed_tokens": 5}
    before = accounting([intent], [receipt])
    after = accounting([intent], [receipt], [note])
    assert before["reported_tokens"] == after["reported_tokens"] == 5
    assert before["conservative_accounted_tokens"] == after["conservative_accounted_tokens"] == 5
    assert before["unresolved_outcomes"] == ["attempt"] and after["unresolved_outcomes"] == []
    assert receipt["outcome"] == "unknown"
    for key, value in (("http_status", None), ("error_type", "TransportError"), ("billed_tokens", None)):
        changed = {**receipt, key: value}
        assert accounting([intent], [changed], [note])["unresolved_outcomes"] == ["attempt"]


def test_archive_package_replays_raw_metadata_and_budget():
    plan = prepared()
    response = listing([*IDS, CONTROL, "numeric"])
    receipt = {"id": "new", "attempt": "new-attempt", "parameters": plan["parameters"], "outcome": "received", "http_status": 200,
        "headers": {"req-archive": "1"}, "response": {}, "raw_response": "raw", "billed_tokens": 5}
    intent = {"attempt": "new-attempt", "reserved_tokens": 50}
    observed = {**receipt, "response": response}
    summary = module.summarize(observed, plan, {CONTROL, "numeric"}, {"sdk": {"req-archive": "0"}, "list": {"req-archive": "0"}})
    docs = {"archive-uri-repair.json": {"preparation": plan, "receipt": "new", "response_reconciliations": []},
        "versions/policy.json": {"content": {"archive_repair_method": module.METHOD, "archive_repair_preparation": "prep", "resolution_extension_templates": [plan["parameters"]]}},
        "receipts/new.json": receipt, "responses/new.json": response, "intents/new.json": intent,
        "receipts/sdk.json": {"id": "sdk", "attempt": "sdk", "headers": {"req-archive": "0"}},
        "receipts/list.json": {"id": "list", "attempt": "list", "headers": {"req-archive": "0"}},
        "years/2026/saved-ids.txt": f"{CONTROL}\nnumeric"}
    class Archive:
        def read(self, name):
            return docs[name].encode() if isinstance(docs[name], str) else canonical(docs[name]).encode()
        def namelist(self):
            return list(docs)
    comparison = {"archive_repair_summary": summary, "budget": accounting([intent], [receipt])}
    assert module.verify_package(Archive(), comparison)["metadata_recovered"] == 6
    changed = copy.deepcopy(response)
    changed["articles"]["results"][0]["date"] = "2026-10-16"
    docs["responses/new.json"] = changed
    with pytest.raises(AuditError, match="reproduce"):
        module.verify_package(Archive(), comparison)
