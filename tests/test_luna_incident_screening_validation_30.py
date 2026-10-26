"""New sample identity and full source-review lifecycle, using synthetic articles."""
from copy import deepcopy
import json

import pytest

from newsresearch.common import AuditError, Config, ResearchError
import test_luna_incident_screening as fixture
import run_luna_incident_screening_v2 as screening
import validate_luna_incident_screening as previous
import validate_luna_incident_screening_30 as validation


def test_new_seed_without_label_selection():
    frame = [{"custom_id": str(n), "request": str(n * 17), "label": "keep"} for n in range(101)]
    selected = validation.sample(frame, 30)
    changed = [{**r, "label": "exclude"} for r in reversed(frame)]
    assert [r["custom_id"] for r in selected] == [r["custom_id"] for r in validation.sample(changed, 30)]
    assert len({r["custom_id"] for r in selected}) == 30
    assert selected != previous.sample(frame, 30)
    with pytest.raises(ResearchError):
        validation.sample(frame, 31)
    with pytest.raises(ResearchError):
        validation.sample(frame + [frame[0]], 30)


def test_blind_review_freezes_before_comparison(tmp_path, monkeypatch):
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
        fixture.call(reviewer, "dispatch")
        packet = fixture.call(reviewer, "read", start=1, end=8)
        assert all(set(r) == {"ordinal", "title", "body"} for r in packet["articles"])
        with pytest.raises(AuditError, match="references_frozen"):
            fixture.call(reviewer, "report")
        classes = [("single_event", "yes")] * 4 + [("no_event", "no")] * 3 + [("uncertain", "uncertain")]
        replies = [{"ordinal": r["ordinal"], "event_scope": labels[0], "ai_incident": labels[1],
                    "scope_rationale": "Synthetic source scope judgment for lifecycle testing.",
                    "incident_rationale": "Synthetic source harm judgment for lifecycle testing.",
                    "scope_quote": r["title"], "incident_quote": r["body"][:70]}
                   for r, labels in zip(packet["articles"], classes, strict=True)]
        draft = reviewer.ledger.root / "synthetic-reviews.json"

        def submit(values):
            draft.write_text(json.dumps(values), encoding="utf-8")
            return fixture.call(reviewer, "submit", input=str(draft))

        wrong = deepcopy(replies)
        wrong[0]["incident_quote"] = "Not an actual source substring."
        with pytest.raises(AuditError, match="quote_not_exact"):
            submit(wrong)
        assert not reviewer.rows("screen_validation_reference")
        assert submit(replies)["references_frozen"]
        with pytest.raises(AuditError, match="already_frozen"):
            submit(replies)
        report = fixture.call(reviewer, "report")
        assert report["sample_size"] == len(report["cases"]) == 8
        assert report["metrics"]["routing"]["supported_keeps"] == 4
        assert report["metrics"]["routing"]["false_keeps_against_clear_references"] == 3
        assert report["metrics"]["routing"]["keeps_with_uncertain_references"] == 1
        assert report["prior_review_overlap"] == []
        assert report["new_api_calls"] == 0 and len(fixture.Fake.calls) == 8
        with pytest.raises(AuditError, match="already_frozen"):
            fixture.call(reviewer, "report")
    finally:
        reviewer.close()
