"""Synthetic label blinding, immutable references and agreement accounting."""
from copy import deepcopy
import json

import pytest

from newsresearch.common import AuditError, Config, ResearchError

import test_luna_incident_screening as fixture
import run_luna_incident_screening_v2 as screening
import validate_luna_incident_screening as validation
import inspect_luna_screening_validation as inspection


def test_label_independent_sampling_and_precise_error_denominators():
    frame = [{"custom_id": str(n), "request": str(n * 17), "label": "keep"} for n in range(101)]
    first = validation.sample(frame, 100)
    changed = [{**r, "label": "exclude"} for r in reversed(frame)]
    assert [r["custom_id"] for r in first] == [r["custom_id"] for r in validation.sample(changed, 100)]
    assert len({r["custom_id"] for r in first}) == 100
    with pytest.raises(ResearchError):
        validation.sample(frame + [frame[0]], 100)
    with pytest.raises(ResearchError):
        validation.sample(frame, 101)
    values = [("single_event", "yes", "single_event", "yes"),
              ("single_event", "no", "single_event", "yes"),
              ("single_event", "yes", "no_event", "no"),
              ("single_event", "yes", "uncertain", "yes"),
              ("uncertain", "uncertain", "single_event", "yes")]
    rows = [{"reference": {"event_scope": a, "ai_incident": b},
             "luna": validation.core.parse_response(fixture.response(c, d))} for a, b, c, d in values]
    result = validation.compare(rows)
    route = result["routing"]
    assert route["supported_keeps"] == 1
    assert route["false_keeps_against_clear_references"] == 1
    assert route["keeps_with_uncertain_references"] == 1
    assert route["false_exclusions_against_clear_references"] == 1
    assert route["reference_keeps_routed_for_review"] == 1
    assert route["keep_precision_on_clear_references"] == .5
    assert route["keep_recall_against_clear_references"] == pytest.approx(1 / 3)
    assert route["supported_fraction_of_all_luna_keeps"] == pytest.approx(1 / 3)
    assert validation.compare([])["routing"]["keep_precision_on_clear_references"] is None


def test_full_blinded_review_quote_and_freeze_lifecycle(tmp_path, monkeypatch):
    fixture.parents(tmp_path)
    fixture.Fake.calls, fixture.Fake.mode = [], "valid"
    monkeypatch.setattr(screening.transport, "DecisionsTransport", fixture.Fake)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    parent = screening.Study(tmp_path / "pilot", config=Config(offline=False))
    try:
        fixture.call(parent, "prepare", base=str(tmp_path), count=8)
        fixture.call(parent, "run", allow_paid_execution=True)
        fixture.call(parent, "report")
    finally:
        parent.close()
    reviewer = validation.Study(tmp_path / "review", config=Config(offline=True))
    try:
        plan = fixture.call(reviewer, "prepare", source_owner=str(tmp_path / "pilot"), count=8)
        assert plan["selected"] == 8 and plan["labels_blinded"]
        reviewer.close()
        inspector = inspection.Inspection(tmp_path / "review", config=Config(offline=True))
        try:
            with pytest.raises(AuditError, match="references_frozen"):
                fixture.call(inspector, "inspect_frozen_comparison")
        finally:
            inspector.close()
        reviewer = validation.Study(tmp_path / "review", config=Config(offline=True))
        with pytest.raises(AuditError, match="handoff"):
            fixture.call(reviewer, "read", start=1, end=2)
        fixture.call(reviewer, "dispatch")
        with pytest.raises(AuditError, match="already_frozen"):
            fixture.call(reviewer, "dispatch")
        packet = fixture.call(reviewer, "read", start=1, end=2)
        assert len(packet["articles"]) == 2
        assert all(set(r) == {"ordinal", "title", "body"} for r in packet["articles"])
        status = fixture.call(reviewer, "status")
        assert not status["unblinded"] and status["reviewed"] == 0
        items = reviewer.ledger.artifacts.read(reviewer.one("screen_validation_plan")["items"])
        classes = [("single_event", "yes"), ("single_event", "no"), ("uncertain", "uncertain"),
                   ("multiple_events", "yes"), ("single_event", "yes"), ("no_event", "no"),
                   ("single_event", "yes"), ("single_event", "yes")]
        replies = [{"ordinal": r["ordinal"], "event_scope": labels[0], "ai_incident": labels[1],
                    "scope_rationale": "Synthetic scope reference for workflow testing only.",
                    "incident_rationale": "Synthetic incident reference for workflow testing only.",
                    "scope_quote": r["title"], "incident_quote": r["body"][:70]}
                   for r, labels in zip(items, classes, strict=True)]
        draft = reviewer.ledger.root / "synthetic-review-block.json"

        def submit(block):
            draft.write_text(json.dumps(block), encoding="utf-8")
            return fixture.call(reviewer, "submit", input=str(draft))

        with pytest.raises(AuditError, match="unread"):
            submit(replies[:3])
        wrong = deepcopy(replies[:2])
        wrong[0]["scope_quote"] = "This sentence is absent from the source."
        with pytest.raises(AuditError, match="quote_not_exact"):
            submit(wrong)
        assert not reviewer.rows("screen_validation_reference")
        result = submit(replies[:2])
        assert result["reviewed"] == 2 and result["luna_labels_still_blinded"]
        with pytest.raises(AuditError, match="references_frozen"):
            fixture.call(reviewer, "report")
        with pytest.raises(AuditError, match="duplicate"):
            submit(replies[:1])
        fixture.call(reviewer, "read", start=3, end=8)
        result = submit(replies[2:])
        assert result["references_frozen"] and not reviewer.ledger.unresolved
        with pytest.raises(AuditError, match="already_frozen"):
            submit(replies[:1])
        report = fixture.call(reviewer, "report")
        assert report["sample_size"] == 8 and report["new_api_calls"] == 0
        assert report["metrics"]["routing"]["supported_keeps"] == 4
        assert report["metrics"]["routing"]["false_keeps_against_clear_references"] == 3
        assert report["metrics"]["routing"]["keeps_with_uncertain_references"] == 1
        assert report["metrics"]["routing"]["keep_precision_on_clear_references"] == pytest.approx(4 / 7)
        assert report["metrics"]["routing"]["keep_recall_against_clear_references"] == 1
        assert len(fixture.Fake.calls) == 8  # The reviewer made no additional API requests.
        assert fixture.call(reviewer, "status")["unblinded"]
    finally:
        reviewer.close()
    inspector = inspection.Inspection(tmp_path / "review", config=Config(offline=True))
    try:
        before = inspector.rows("screen_validation_reference")
        detail = fixture.call(inspector, "inspect_frozen_comparison")
        assert detail["report"] == report["id"]
        assert len(detail["disagreements"]) == 4
        assert detail["new_model_calls"] == detail["changed_references"] == 0
        assert inspector.rows("screen_validation_reference") == before
        assert len(inspector.rows("screen_validation_report")) == 1
        assert len(fixture.Fake.calls) == 8
    finally:
        inspector.close()
