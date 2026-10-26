"""Synthetic keep-census lineage, freeze gates and review-routing accounting."""
import json

import pytest

from newsresearch.common import AuditError, Config

import test_luna_incident_screening as fixture
import run_luna_incident_screening_v2 as screening
import validate_luna_incident_screening as validation
import review_luna_screening_keeps as review


def test_safeguard_retains_positives_without_creating_keeps():
    values = [("single_event", "yes", "no_event", "yes"),
              ("single_event", "yes", "single_event", "uncertain"),
              ("no_event", "no", "multiple_events", "yes"),
              ("single_event", "uncertain", "single_event", "no"),
              ("single_event", "yes", "single_event", "yes")]
    rows = [{"ordinal": n, "reference": {"event_scope": a, "ai_incident": b},
             "luna": validation.core.parse_response(fixture.response(c, d))}
            for n, (a, b, c, d) in enumerate(values, 1)]
    result = review.routing_experiment(rows)
    assert result["original"]["reference_keeps_retained_or_reviewed"] == 2
    assert result["safeguard"]["reference_keeps_retained_or_reviewed"] == 3
    assert result["safeguard"]["reference_keeps_auto_kept"] == 1
    assert result["safeguard"]["clear_reference_exclusions_sent_to_review"] == 1
    assert result["safeguard"]["uncertain_reference_routes_excluded"] == 1
    assert [r["ordinal"] for r in result["changes"]] == [1, 3]
    assert result["production_routes_changed"] is False


def submit_synthetic(engine, count, action):
    packet = fixture.call(engine, "read", start=1, end=count)
    replies = [{"ordinal": r["ordinal"], "event_scope": "single_event",
                "ai_incident": "yes" if r["ordinal"] < count else "uncertain",
                "scope_rationale": "Synthetic scope judgment for software verification.",
                "incident_rationale": "Synthetic incident judgment for software verification.",
                "scope_quote": r["title"], "incident_quote": r["body"][:70]}
               for r in packet["articles"]]
    draft = engine.ledger.root / "synthetic-replies.json"
    draft.write_text(json.dumps(replies), encoding="utf-8")
    return fixture.call(engine, action, input=str(draft))


def test_full_census_preserves_originals_and_reuses_frozen_validation(tmp_path, monkeypatch):
    fixture.parents(tmp_path)
    fixture.Fake.calls, fixture.Fake.mode = [], "valid"
    monkeypatch.setattr(screening.transport, "DecisionsTransport", fixture.Fake)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    parent = screening.Study(tmp_path / "pilot", config=Config(offline=False))
    try:
        fixture.call(parent, "prepare", base=str(tmp_path), count=8)
        fixture.call(parent, "run", allow_paid_execution=True)
        fixture.call(parent, "report")
        parent_records = parent.rows("incident_screen_decision")
    finally:
        parent.close()
    prior = validation.Study(tmp_path / "validation", config=Config(offline=True))
    try:
        fixture.call(prior, "prepare", source_owner=str(tmp_path / "pilot"), count=8)
        fixture.call(prior, "dispatch")
        submit_synthetic(prior, 8, "submit")
        prior_report = fixture.call(prior, "report")
        references = prior.rows("screen_validation_reference")
    finally:
        prior.close()
    engine = review.Study(tmp_path / "keeps", config=Config(offline=True))
    try:
        plan = fixture.call(engine, "prepare", source_owner=str(tmp_path / "pilot"),
                            validation_owner=str(tmp_path / "validation"), count=8)
        assert plan["selected"] == 8 and plan["selection_aware"]
        assert plan["labels_blinded"] is False and plan["prior_sample_overlap"] == 8
        with pytest.raises(AuditError, match="handoff"):
            fixture.call(engine, "read", start=1, end=8)
        fixture.call(engine, "dispatch")
        with pytest.raises(AuditError, match="already_frozen"):
            fixture.call(engine, "dispatch")
        with pytest.raises(AuditError, match="references_frozen"):
            fixture.call(engine, "report")
        result = submit_synthetic(engine, 8, "submit")
        assert result["references_frozen"] and not engine.ledger.unresolved
        with pytest.raises(AuditError, match="already_frozen"):
            submit_synthetic(engine, 8, "submit")
        report = fixture.call(engine, "report")
        assert report["sample_size"] == 8
        assert report["metrics"]["routing"]["supported_keeps"] == 7
        assert report["metrics"]["routing"]["keeps_with_uncertain_references"] == 1
        assert report["metrics"]["routing"]["keep_recall_against_clear_references"] is None
        assert report["full_pilot_workload"]["changed"] == 0
        assert report["new_api_calls"] == 0 and len(fixture.Fake.calls) == 8
        with pytest.raises(AuditError, match="already_frozen"):
            fixture.call(engine, "report")
    finally:
        engine.close()
    prior = validation.Study(tmp_path / "validation", config=Config(offline=True))
    try:
        assert prior.rows("screen_validation_reference") == references
        assert prior.one("screen_validation_report")["_record_id"] == prior_report["id"]
    finally:
        prior.close()
    parent = screening.Study(tmp_path / "pilot", config=Config(offline=True))
    try:
        assert parent.rows("incident_screen_decision") == parent_records
    finally:
        parent.close()
