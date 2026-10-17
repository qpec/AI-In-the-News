import copy
from types import SimpleNamespace

import pytest

from newsresearch import newsapi_event_diagnosis as module
from newsresearch.common import Context, ResearchError, canonical, digest
from newsresearch.newsapi_event_coverage import observation, summarize


def fixture(monkeypatch):
    artifacts = {}
    def put(value):
        reference = digest(value)
        artifacts[reference] = canonical(value).encode()
        return reference
    def receipt(items, raw=True):
        response = {"articles": {"results": items}}
        reference = put(response) if raw else None
        return {"parameters": {}, "response": response, "raw_response": reference, "raw_sha256": reference}
    a = {"uri": "a", "date": "2026-01-01", "eventUri": "event-1", "isDuplicate": False}
    b = {"uri": "b", "date": "2026-01-01", "eventUri": None, "isDuplicate": True}
    q = {"uri": "q", "date": "2026-01-01", "quarantined": True}
    n = {"uri": "new", "date": "2026-01-01", "eventUri": None}
    first = receipt([a, b])
    quarantine = receipt([q], False)
    fresh = receipt([a, {**b, "eventUri": "event-2"}, n])
    old = [observation(a, "first", 0, "original_saved"), observation(b, "first", 1, "original_saved"), observation(q, "quarantine", 0, "original_saved")]
    newer = [observation(item, "fresh", i, "fresh_minimal_metadata") for i, item in enumerate(fresh["response"]["articles"]["results"])]
    rows = [*old, newer[-1]]
    proof = {"rows": rows, "fresh_comparison_rows": newer}
    data = {
        "protocol": {"content": {"method": module.METHOD}},
        "selection": {"content": {"rules": {"coverage_id": "coverage"}}},
        "coverage": {"combined": summarize(rows), "proof_artifact": put(proof), "recovery_id": "recovery",
            "supplement": summarize([newer[-1]]), "fresh_metadata_window": summarize(newer)},
        "first": first, "quarantine": quarantine, "fresh": fresh,
        "recovery": {"minimal_recovery_summary": {"enumeration": {"articles": {k: {"uri": k} for k in ["a", "b", "new"]}}}},
    }
    events = []
    ledger = SimpleNamespace(get=lambda key, kind: data[key],
        artifacts=SimpleNamespace(read=lambda ref: __import__('json').loads(artifacts[ref]), read_bytes=lambda ref: artifacts[ref], put=put),
        append=lambda *args: events.append(args), record=lambda *args: "result")
    engine = SimpleNamespace(ledger=ledger, _active={"session"}, _require=lambda *args: None)
    monkeypatch.setattr(module, "records", lambda *args: [])
    monkeypatch.setattr(module, "budget", lambda *args: {"limit": 583, "reported_tokens": 431, "conservative_accounted_tokens": 561})
    context = Context("Offline diagnosis", "test:operator", {"protocol": "protocol", "selection": "selection", "question": "question", "profile": "profile"})
    return engine, context, data, events


def test_diagnosis_preserves_changes_quarantine_and_projection_loss(monkeypatch):
    engine, context, _, events = fixture(monkeypatch)
    result = module.run(engine, "session", context, {"coverage_id": "coverage"})
    assert result["raw_rows"] == {"verified_rows": 3, "raw_bytes_unavailable_rows": 1}
    assert result["original_mixed_null_populated_pages"] == 1
    assert result["absent_nonquarantined"] == 0
    assert result["paired_transitions"] == {"populated_same_id": 1, "null_to_populated": 1, "new_metadata_record": 1}
    assert result["derived_projection_transitions"] == {"populated_to_absent": 2, "null_to_absent": 1}
    assert result["remaining_conservative_tokens"] == 22
    assert result["network_calls"] == result["newsapi_tokens"] == 0
    assert events[-1][1] == "newsapi.event_diagnosis.proof.saved"


def test_diagnosis_rejects_receipt_mutation_and_wrong_source(monkeypatch):
    engine, context, data, _ = fixture(monkeypatch)
    with pytest.raises(ResearchError, match="Register"):
        module.run(engine, "session", context, {"coverage_id": "other"})
    data["first"] = copy.deepcopy(data["first"])
    data["first"]["response"]["articles"]["results"][1]["eventUri"] = "invented"
    with pytest.raises(ResearchError, match="differs from retained provider"):
        module.run(engine, "session", context, {"coverage_id": "coverage"})


def test_reuse_requires_exact_versions_and_does_not_rescan_sources(monkeypatch):
    engine, context, data, events = fixture(monkeypatch)
    data["saved"] = {"versions": context.versions.copy(), "coverage_id": "coverage"}
    result = module.run(engine, "session", context, {"coverage_id": "coverage", "reuse_result": "saved"})
    assert result["reused"] and not events
    data["saved"]["versions"]["profile"] = "other"
    with pytest.raises(ResearchError, match="exact original versions"):
        module.run(engine, "session", context, {"coverage_id": "coverage", "reuse_result": "saved"})
