"""Fictional human-reference records through the real audited runtime only."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from newsresearch.common import ResearchError
from test_event_eval_workflow import setup_study as setup_study


def run(engine, action, plan, *, actor="human:fictional-reviewer", **data):
    return engine.execute("luna_group_validation", {"phase": "review_template" if action == "template" else "import_reviews", "plan": plan["id"], **data},
                          objective="Synthetic human-reference integration check", actor=actor)


def write_reviews(engine, document, name="fictional-human-reviews.json"):
    path = engine.ledger.root / name
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)
    return path


def assert_exact(engine, result):
    presentation = result["presentation"]
    assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode()
    assert presentation["versions"] == result["versions"]
    assert presentation["results"][0]["id"] == result["id"]
    assert presentation["ui_delivery_verified"] is False


def test_blinded_template_partial_human_import_and_append_only_correction(setup_study):
    engine, old, plan, policy, execution = setup_study()
    template = run(engine, "template", plan)
    document = engine.ledger.artifacts.read(template["template_artifact"])
    assert len(document["reviews"]) == len(plan["design"]["selected_pairs"]) == 6
    assert {row["pair_id"] for row in document["reviews"]}.isdisjoint(
        task["pair_id"] for task in plan["tasks"] if task["phase"] == "canary")
    for row in document["reviews"]:
        assert set(row) == {"pair_id", "request_hash", "articles", "evidence", "label", "support_span_ids", "reason"}
        assert row["label"] is None and row["support_span_ids"] == [] and row["reason"] == ""
        assert row["request_hash"] in {task["request"] for task in plan["tasks"]}
        assert len(row["articles"]) == 2
    assert template["human_reviews_created"] == template["model_calls"] == 0
    assert_exact(engine, template)
    document["reviews"][0].update(label="same_event", support_span_ids=["A1", "B1"],
                                  reason="Synthetic annotation for this fictional fixture only.")
    path = write_reviews(engine, document)
    first = run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    assert first["metrics"]["reference_kind"] == "human"
    assert first["reviewed_pairs"] == 1 and first["pending_pairs"] == 5
    assert first["identity_assurance"] == "self_asserted"
    assert first["independent_human_gold_validated"] is False and first["model_calls"] == 0
    assert first["metrics"]["counts"]["pending"] == 5
    assert engine.ledger.artifacts.read_bytes(first["import_artifact"]) == path.read_bytes()
    first_review = next(iter(first["reviews"].values()))
    assert first_review["request"] == document["reviews"][0]["request_hash"]
    assert_exact(engine, first)
    replay = run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    assert replay["reviewed_pairs"] == 1
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_eval_review'").fetchone()[0] == 1
    document["reviews"][0]["label"] = "different_event"
    path = write_reviews(engine, document)
    with pytest.raises(ResearchError, match="correction_requires_latest_supersedes"):
        run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    document["reviews"][0]["supersedes"] = first_review["review"]
    path = write_reviews(engine, document)
    corrected = run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    latest = next(iter(corrected["reviews"].values()))
    assert latest["answer"]["label"] == "different_event"
    assert engine.ledger.get(first_review["review"], "event_pair_eval_review")["answer"]["label"] == "same_event"
    assert engine.ledger.get(old["old_result"], "luna_group_validation_result") == old["old_value"]
    assert engine.ledger.db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0
    assert_exact(engine, corrected)
    engine.ledger.verify()


def test_actor_retained_bytes_and_edited_evidence_rejected(setup_study):
    engine, old, plan, policy, execution = setup_study()
    template = run(engine, "template", plan)
    document = engine.ledger.artifacts.read(template["template_artifact"])
    path = write_reviews(engine, document)
    with pytest.raises(ResearchError, match="identified_human_reviewer_required"):
        run(engine, "import", plan, actor="agent:fictional", reviewer="Fictional reviewer", reviews_file=str(path))
    changed = deepcopy(document)
    changed["reviews"][0]["evidence"][0]["text"] += " Modified supporting text."
    changed["reviews"][0].update(label="same_event", support_span_ids=["A1", "B1"], reason="Fictional annotation.")
    path = write_reviews(engine, changed)
    with pytest.raises(ResearchError, match="evidence_or_request_changed"):
        run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    bad_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert engine.ledger.artifacts.read_bytes(bad_hash) == path.read_bytes()
    path.write_bytes(b"This is not JSON; retain these exact permitted bytes before parsing.")
    path.chmod(0o600)
    with pytest.raises(json.JSONDecodeError):
        run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    raw_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    assert engine.ledger.artifacts.read_bytes(raw_hash) == path.read_bytes()
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_eval_review'").fetchone()[0] == 0
    engine.ledger.verify()


def test_unavailable_source_cannot_be_filled_and_external_review_path_rejected(setup_study, tmp_path):
    engine, old, plan, policy, execution = setup_study(unknown_source=True)
    template = run(engine, "template", plan)
    document = engine.ledger.artifacts.read(template["template_artifact"])
    unavailable = next(row for row in document["reviews"] if row["request_hash"] is None)
    assert unavailable["evidence"] == unavailable["articles"] == []
    unavailable.update(label="different_event", support_span_ids=[], reason="Fictional unsupported annotation.")
    path = write_reviews(engine, document)
    with pytest.raises(ResearchError, match="unavailable_source_cannot_be_judged"):
        run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(path))
    outside = tmp_path / "outside-store.json"
    outside.write_text(json.dumps(document), encoding="utf-8")
    outside.chmod(0o600)
    with pytest.raises(ResearchError, match="inside_own_workspace"):
        run(engine, "import", plan, reviewer="Fictional reviewer", reviews_file=str(outside))
    engine.ledger.verify()
