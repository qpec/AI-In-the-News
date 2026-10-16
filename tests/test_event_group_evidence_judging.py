"""Synthetic approval, request-binding and original-gateway checks only."""
from datetime import datetime, timedelta, timezone
from itertools import combinations
import sys
from typing import Any

import pytest

from newsresearch import event_group_evidence_judging as judge
from newsresearch.common import AuditError, ResearchError, digest
from test_event_pair_experiment import fake_provider, planned as _planned

planned = _planned


@pytest.fixture
def ready(planned: Any, monkeypatch: Any) -> Any:
    engine, plan = planned
    metadata = engine.ledger.artifacts.read(plan["metadata_artifact"])
    chosen = sorted(metadata)[:3]
    tasks = [{"pair_id": digest([a, b]), "left": a, "right": b} for a, b in combinations(chosen, 2)]
    selected = [{"candidate_id": "constructed-candidate", "article_members": chosen,
                 "pair_task_ids": [row["pair_id"] for row in tasks]}]
    config = judge.original._config(engine, {"codex_model": "synthetic-model", "codex_executable": sys.executable})

    def setup(session: str, context: Any, data: Any) -> Any:
        packets = []
        for task in tasks:
            request = judge.original._request(engine, session, task, metadata, plan["versions"])
            reference = judge.preparation.links.base._save(engine, session, request, "Constructed future judgment packet")
            packets.append({**task, "status": "prepared", "task_key": "planning-" + task["pair_id"], "request_ref": reference})
        for n in range(55):
            engine.ledger.append(session, "model.attempt.intended", {"attempt": f"old-{n}", "task_key": f"old-key-{n}",
                "event_pair_study": plan["study_key"], "event_pair_retry": n == 54,
                "reserved_pair_attempts": 1, "reserved_article_exposures": 2})
            engine.ledger.append(session, "model.attempt.completed", {"attempt": f"old-{n}", "status": "invalid"})
        return packets, judge.preparation._budget(engine, session, plan)

    monkeypatch.setattr(engine, "_status", setup)
    packets, budget = engine.execute("status", objective="Prepare source-free future-judgment fixture", actor="test:software")
    prepared = {"manifest": "constructed-preparation", "versions": plan["versions"], "config": config,
                "exports": {"packets": {"artifact": "constructed-packets"}}, "budget": budget,
                "reused_reference_pairs_in_queue": 0, "known_reference_conflict_proposals": 0}
    frozen = {"artifact": "constructed-queue"}
    queue = {"tasks": tasks, "selected": selected}
    monkeypatch.setattr(judge, "_load", lambda *args: (prepared, frozen, queue, packets, plan, metadata))
    approval = {"method": "cross-window-event-review-run-approval-v1", "prepared_result": "constructed-result",
        "study_key": "constructed-judging", "original_study_key": plan["study_key"],
        "prepared_binding": judge.approval_binding("constructed-result", prepared, frozen),
        "authorized": True, "external_processing_authorized": True, "codex_account_execution_authorized": True,
        "max_pair_attempts": 100, "max_article_exposures": 200, "max_primary_pairs": 90,
        "max_known_invalid_retries": 10, "queue_primary_tasks": 3,
        "remaining_primary_ceiling": 36, "remaining_retry_ceiling": 9,
        "authorization_key": "constructed-fresh-approval", "approved_by": "test:operator",
        "instruction": "Constructed authorization fixture, not permission for real research",
        "approval_source": "human_reply_in_current_codex_chat", "observed_chat_timestamp": None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    data = {"prepared_result": "constructed-result", "study_key": "constructed-judging",
            "run_approval": approval, "reuse_cache": True, "workers": 1}
    return engine, data, prepared, queue, packets


def run(ready: Any, **changes: Any) -> Any:
    return ready[0].execute("judge_cross_window_event_review", {**ready[1], **changes}, objective="Test frozen judgment execution", actor="test:software")


def test_missing_expired_changed_approval_never_dispatches(ready: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    for approval in (None, {**ready[1]["run_approval"], "expires_at": "2000-01-01T00:00:00Z"},
                     {**ready[1]["run_approval"], "prepared_binding": "changed"},
                     {**ready[1]["run_approval"], "max_pair_attempts": 101}):
        with pytest.raises(ResearchError):
            run(ready, run_approval=approval)
    assert seen == []
    attestation = {key: ready[1]["run_approval"][key] for key in (
        "authorization_key", "approved_by", "instruction", "expires_at", "authorized", "external_processing_authorized",
        "codex_account_execution_authorized", "approval_source", "observed_chat_timestamp")}
    with pytest.raises(ResearchError, match="Choose"):
        run(ready, human_authorization=attestation)
    with pytest.raises(ResearchError):
        run(ready, run_approval=None, human_authorization={**attestation, "authorized": False})
    assert seen == []
    last = ready[3]["tasks"].pop()
    with pytest.raises(AuditError, match="coverage"):
        run(ready)
    ready[3]["tasks"].append(last)
    assert seen == []


def test_original_phase_budget_exact_requests_resume_and_no_reset(ready: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    attestation = {key: ready[1]["run_approval"][key] for key in (
        "authorization_key", "approved_by", "instruction", "expires_at", "authorized", "external_processing_authorized",
        "codex_account_execution_authorized", "approval_source", "observed_chat_timestamp")}
    result = run(ready, run_approval=None, human_authorization=attestation)
    assert len(seen) == result["new_model_attempts"] == 3
    assert result["budget_after"]["spent_attempts"] == 58
    assert result["budget_after"]["spent_primary"] == 57 and result["budget_after"]["spent_retries"] == 1
    assert result["proposal_status_counts"] == {"uncertain": 1}
    assert result["presentation"]["markdown"] == judge.render(result)
    assert result["actual_group_merges"] == result["accepted_dossiers"] == 0
    assert run(ready)["new_model_attempts"] == 0 and len(seen) == 3
    with pytest.raises(ResearchError, match="already has"):
        run(ready, study_key="reset", run_approval={**ready[1]["run_approval"], "study_key": "reset"})
    original_request = judge.original._request
    monkeypatch.setattr(judge.original, "_request", lambda *args: {**original_request(*args), "instructions": "changed"})
    with pytest.raises(AuditError, match="request"):
        run(ready)
    assert len(seen) == 3 and ready[0].ledger.verify()["status"] == "verified"


def test_every_union_pair_required_and_missing_processing_stays_incomplete():
    members = ["a", "b", "c"]
    pairs = [digest(list(pair)) for pair in combinations(members, 2)]
    proposal = {"article_members": members, "pair_task_ids": pairs}
    same = {key: {"status": "completed", "label": "same_event"} for key in pairs}
    assert judge.classify([proposal], same)[0]["review_status"] == "provisional_pairwise_support_requires_cluster_review"
    changed = {**same, pairs[0]: {"status": "completed", "label": "different_event"}}
    assert judge.classify([proposal], changed)[0]["review_status"] == "conflicting_model_references"
    del changed[pairs[-1]]
    incomplete = judge.classify([proposal], changed)[0]
    assert incomplete["review_status"] == "incomplete" and incomplete["has_different_event_reference"]
    with pytest.raises(AuditError, match="every union"):
        judge.classify([{**proposal, "pair_task_ids": pairs[:-1]}], same)
