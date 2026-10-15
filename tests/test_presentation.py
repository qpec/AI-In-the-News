from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any

import pytest

from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.presentation import record


def presentation(run: Any, query: str = "outage") -> dict[str, Any]:
    found = run("search", {"query": query, "limit": 1})
    return {"results": [{"kind": "search", "id": found["id"]}],
            "markdown": f"Zoekactie: {query}\n\n{len(found['hits'])} passage(s) getoond; limiet 1.\n",
            "destination": "codex_chat"}


def test_presentation_preserves_exact_bytes_versions_and_distinct_events(prepared: Any) -> None:
    engine, versions, run = prepared
    data = presentation(run)
    result = run("record_presentation", data)
    raw = data["markdown"].encode("utf-8")
    assert engine.ledger.artifacts.read_bytes(result["content_artifact"]) == raw
    assert result["content_sha256"] == hashlib.sha256(raw).hexdigest()
    saved = engine.ledger.get(result["id"], "result_presentation")
    assert saved["markdown"] == data["markdown"] and saved["results"] == data["results"]
    assert saved["versions"] == versions and saved["actor"] == "reviewer:test"
    assert datetime.fromisoformat(saved["recorded_at"]).utcoffset() is not None
    assert saved["status"] == "prepared_for_delivery" and saved["delivery_report"] is None
    assert not saved["ui_delivery_verified"] and not saved["human_reading_observed"]
    assert saved["network_calls"] == saved["model_calls"] == 0
    repeated = run("record_presentation", data)
    assert repeated["id"] != result["id"]
    assert repeated["content_artifact"] == result["content_artifact"]
    assert engine.ledger.verify()["status"] == "verified"


def test_zero_hits_can_be_presented_without_inventing_results(prepared: Any) -> None:
    engine, versions, run = prepared
    data = presentation(run, "nonexistentword")
    result = run("record_presentation", data)
    assert "0 passage(s)" in result["markdown"]
    assert engine.ledger.get(data["results"][0]["id"], "search")["hits"] == []


def test_retrospective_delivery_keeps_unavailable_time_explicit(prepared: Any) -> None:
    engine, versions, run = prepared
    data = {**presentation(run), "status": "delivery_reported",
            "delivery_report": {"occurred_at": None,
                                "unavailable_reason": "Chat message timestamp was not available"}}
    result = run("record_presentation", data)
    assert result["delivery_report"]["occurred_at"] is None
    assert result["delivery_basis"] == "caller_attestation"
    assert not result["ui_delivery_verified"]


@pytest.mark.parametrize("change", [
    {"status": "user_read"},
    {"status": "delivery_reported"},
    {"status": "delivery_reported", "delivery_report": {"occurred_at": None, "unavailable_reason": None}},
    {"status": "delivery_reported", "delivery_report": {"occurred_at": "2026-01-01T00:00:00", "unavailable_reason": None}},
    {"status": "delivery_reported", "delivery_report": {"occurred_at": "2999-01-01T00:00:00Z", "unavailable_reason": None}},
    {"delivery_report": {"occurred_at": None, "unavailable_reason": "not sent"}},
    {"markdown": " "}, {"results": []},
])
def test_unobservable_or_incomplete_presentation_claims_are_rejected(prepared: Any, change: Any) -> None:
    engine, versions, run = prepared
    with pytest.raises(ResearchError):
        run("record_presentation", {**presentation(run), **change})
    assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='result_presentation'").fetchone()


def test_wrong_result_kind_and_version_bindings_are_rejected(prepared: Any) -> None:
    engine, versions, run = prepared
    data = presentation(run)
    with pytest.raises(AuditError, match="wrong version type"):
        run("record_presentation", {**data, "results": [{"kind": "article_query_overview", "id": data["results"][0]["id"]}]})
    with pytest.raises(ResearchError, match="exact original"):
        engine.execute("record_presentation", data, objective="Check incorrect presentation bindings", actor="test")
    assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='result_presentation'").fetchone()


def test_presentation_storage_failure_stops_success(prepared: Any) -> None:
    engine, versions, run = prepared
    data = presentation(run)
    engine.ledger.fail_event = "presentation.artifact.saved"
    with pytest.raises(AuditError):
        run("record_presentation", data)
    engine.ledger.fail_event = None
    assert not engine.ledger.db.execute("SELECT 1 FROM records WHERE kind='result_presentation'").fetchone()
    assert engine.ledger.verify()["status"] == "verified"


def test_missing_presentation_bytes_fail_preflight(prepared: Any) -> None:
    engine, versions, run = prepared
    result = run("record_presentation", presentation(run))
    (engine.ledger.artifacts.root / result["content_artifact"]).unlink()
    with pytest.raises(AuditError, match="artifact is missing"):
        engine.ledger.verify()


def test_presentation_requires_runtime(prepared: Any) -> None:
    with pytest.raises(AuditError):
        record(prepared[0], "invalid", Context("test", "test"), {})
