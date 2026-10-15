"""Executable synthetic runtime checks; no actual corpus or model calls."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import hashlib
from itertools import combinations
import sys
from typing import Any

import pytest

from newsresearch import event_pair_experiment as experiment
from newsresearch.codex_provider import CodexCLIProvider
from newsresearch.common import AuditError, Context, ResearchError, digest, utc
from newsresearch.gateway import ProviderResponse
from newsresearch.runtime import Research


@pytest.fixture
def planned(tmp_path: Any, monkeypatch: Any) -> Any:
    # Planner behavior has separate integration tests. Supply its pure frozen
    # contract here with eight DISTINCT constructed bodies so dispatch branches
    # are exercised independently of embedding fixtures/near-neighbor geometry.
    engine = Research(tmp_path / "research")
    versions = {}
    for kind, content in (("protocol", {"method": "synthetic-pair-runner-fixture"}),
                          ("selection", {"rules": "Eight source-free constructed articles"})):
        versions[kind] = engine.execute("version", {"kind": kind, "key": "fixture", "content": content},
            objective="Register synthetic runner fixture", actor="test")["id"]
    dataset = engine.execute("ingest", {"articles": [{"source_key": str(n), "body": f"Constructed article number {n}.",
        "retention": "permitted", "synthetic": True, "title": f"Fixture {n}", "url": f"https://example.test/{n}"}
        for n in range(8)], "retrieval": {"source": "synthetic-fixture", "retrieved_at": utc(), "parameters": {}}},
        versions=versions, objective="Store constructed runner sources", actor="test")
    versions["dataset"] = dataset["id"]
    ids = engine.ledger.get(dataset["id"], "dataset")["source_versions"]
    metadata = {}
    for row in engine.ledger.db.execute("SELECT id,payload FROM sources"):
        source = json.loads(row["payload"])
        metadata[row["id"]] = {"source_version": row["id"], "body_sha256": hashlib.sha256(source["body"].encode()).hexdigest(),
            "title": source.get("title"), "published_at": source.get("published_at"), "url": source.get("url")}
    rows = []
    for fold, chosen in (("development", ids[:4]), ("validation", ids[4:])):
        rows += [{"pair_id": digest([left, right]), "left": left, "right": right, "distance": .1 + n * .04,
            "fold": fold, "inclusion_probability": 1., "weight": 1.} for n, (left, right) in enumerate(combinations(chosen, 2))]
    frame = {"rows": rows, "frame_hash": digest(rows)}
    development = {"rows": [row for row in rows if row["fold"] == "development"]}
    def setup(session: str, context: Any, data: Any) -> Any:
        reference = engine.ledger.artifacts.put(metadata)
        engine.ledger.append(session, "preparation.artifact.saved", {"artifact": reference, "purpose": "Synthetic source metadata"})
        plan = {"versions": versions, "study_key": "synthetic-pair-study", "study_binding": "synthetic-binding",
            "criterion_hash": digest(experiment.CRITERION), "seed": "synthetic-pair-seed", "metadata_artifact": reference,
            "development_pairs": len(development["rows"])}
        return {"id": engine.ledger.record(session, "event_pair_plan", "synthetic-pair-study", plan), **plan}
    monkeypatch.setattr(engine, "_status", setup)
    plan = engine.execute("status", objective="Freeze constructed runner plan", actor="test")
    monkeypatch.undo()
    monkeypatch.setattr(experiment, "load_plan", lambda *args: (plan, frame, development))
    engine.config = replace(engine.config, offline=False)
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    try:
        yield engine, plan
    finally:
        engine.close()


def approved(plan: Any) -> Any:
    return {"method": "event-pair-run-approval-v1", "plan": plan["id"], "study_key": plan["study_key"],
        "criterion_hash": plan["criterion_hash"], "authorization_key": "synthetic-pair-approval",
        "authorized": True, "external_processing_authorized": True, "codex_account_execution_authorized": True,
        "max_pair_attempts": 100, "max_article_exposures": 200, "max_primary_pairs": 90,
        "max_known_invalid_retries": 10, "approved_by": "test:synthetic-operator",
        "instruction": "Synthetic approval fixture; not a human authorization for actual research",
        "approval_source": "human_reply_in_current_codex_chat", "observed_chat_timestamp": None,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}


def run(planned: Any, approval: Any = None, **extra: Any) -> Any:
    engine, plan = planned
    return engine.execute("event_pair_experiment", {"plan": plan["id"], "run_approval": approval or approved(plan),
        "codex_model": "synthetic-model", "codex_executable": sys.executable, **extra},
        versions=plan["versions"], objective="Verify bounded pair experiment using synthetic fixtures", actor="test:software")


def uncertain(request: Any) -> Any:
    return {"label": "uncertain", "rationale": "The constructed fixture supplies no identifiable focal event.",
        "events": [{"source_version": article["source_version"], "description": "unknown", "action": "unknown",
                    "actors": [], "event_date": "unknown", "location": "unknown", "multiple_events": False}
                   for article in request["articles"]],
        "claims": [], "inspected_passage_ids": [p["id"] for p in request["evidence"]]}


def fake_provider(monkeypatch: Any, responder: Any = None) -> list[Any]:
    seen = []
    def complete(self: Any, prepared: Any) -> Any:
        seen.append(prepared)
        if responder:
            return responder(prepared, len(seen))
        return ProviderResponse(uncertain(prepared.request), "codex-cli", "synthetic-model",
                                raw_response={"unknown_outcome": False})
    monkeypatch.setattr(CodexCLIProvider, "complete_prepared", complete)
    return seen


def test_full_audited_runtime_no_acceptance_and_exact_presentation(planned: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    result = run(planned)
    engine, plan = planned
    assert len(seen) == result["pair_attempts"] == plan["development_pairs"]
    assert result["article_exposures"] == 2 * len(seen)
    assert result["candidate_cutoff"] is None and result["validation_pairs"] == 0
    assert result["counts"]["uncertain"] == len(seen)
    assert result["accepted_dossiers"] == result["new_embedding_requests"] == result["applied_tags"] == 0
    assert result["presentation"]["markdown"] == experiment.render(result)
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    assert engine.ledger.get(result["versions"]["model_profile"], "model_profile")["content"] == result["config"]
    assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_holdout_opened'").fetchone()[0] == 0
    for invocation in seen:
        packet = json.loads(invocation.stdin)
        assert {p["source_id"] for p in packet["evidence"]} == {a["source_version"] for a in packet["articles"]}
        assert not {"score", "distance", "fold", "stratum", "weight"} & set(packet)
    assert engine.ledger.verify()["status"] == "verified"


@pytest.mark.parametrize("field,value", [("max_pair_attempts", 101), ("max_article_exposures", 201),
    ("max_primary_pairs", True), ("external_processing_authorized", False), ("codex_account_execution_authorized", False),
    ("criterion_hash", "other"), ("plan", "other"), ("observed_chat_timestamp", "invented"),
    ("expires_at", "2000-01-01T00:00:00Z"), ("expires_at", "2099-01-01T00:00:00")])
def test_invalid_fresh_approval_never_dispatches(planned: Any, monkeypatch: Any, field: str, value: Any) -> None:
    seen = fake_provider(monkeypatch)
    approval = approved(planned[1])
    approval[field] = value
    with pytest.raises(ResearchError):
        run(planned, approval)
    assert seen == []


def test_offline_and_missing_approval_block(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    seen = fake_provider(monkeypatch)
    with pytest.raises(ResearchError, match="fresh concrete"):
        engine.execute("event_pair_experiment", {"plan": plan["id"]}, versions=plan["versions"],
                       objective="Reject missing synthetic approval", actor="test")
    engine.config = replace(engine.config, offline=True)
    with pytest.raises(ResearchError, match="online configuration"):
        run(planned)
    assert seen == []


def test_resume_requires_exact_approval_and_explicit_cache(planned: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    approval = approved(planned[1])
    result = run(planned, approval)
    with pytest.raises(ResearchError, match="reuse_cache"):
        run(planned, approval)
    resumed = run(planned, approval, reuse_cache=True)
    assert resumed["pair_attempts"] == result["pair_attempts"] == len(seen)
    changed = {**approval, "authorization_key": "changed-new-budget"}
    with pytest.raises(ResearchError, match="immutable"):
        run(planned, changed, reuse_cache=True)
    assert len(seen) == result["pair_attempts"]
    assert run(planned, approval, reuse_cache=True)["pair_attempts"] == result["pair_attempts"]


def test_unknown_stops_after_current_block_and_never_retries(planned: Any, monkeypatch: Any) -> None:
    def response(prepared: Any, n: int) -> Any:
        return ProviderResponse(None if n == 1 else uncertain(prepared.request), "codex-cli", None,
            raw_response={"unknown_outcome": n == 1})
    seen = fake_provider(monkeypatch, response)
    approval = approved(planned[1])
    result = run(planned, approval, workers=2)
    assert result["pair_attempts"] == len(seen) == 2
    assert len(result["unresolved_attempts"]) == 1 and result["status"] == "partial"
    resumed = run(planned, approval, workers=2, reuse_cache=True)
    assert resumed["pair_attempts"] == 2 and len(seen) == 2


def test_only_returned_invalid_payload_can_retry_once(planned: Any, monkeypatch: Any) -> None:
    counts = {}
    def response(prepared: Any, n: int) -> Any:
        sources = tuple(a["source_version"] for a in prepared.request["articles"])
        counts[sources] = counts.get(sources, 0) + 1
        payload = {"bad_schema": True} if counts[sources] == 1 else uncertain(prepared.request)
        return ProviderResponse(payload, "codex-cli", None, raw_response={"unknown_outcome": False})
    fake_provider(monkeypatch, response)
    result = run(planned)
    assert 0 < result["retry_attempts"] <= 10
    assert all(value <= 2 for value in counts.values())
    assert result["pair_attempts"] <= 100 and result["article_exposures"] <= 200


def test_observed_failure_without_payload_is_not_retried(planned: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch, lambda *args: ProviderResponse(None, "codex-cli", None,
                                                                  raw_response={"unknown_outcome": False}))
    result = run(planned)
    assert result["pair_attempts"] == len(seen) == planned[1]["development_pairs"]
    assert result["retry_attempts"] == 0 and result["failed_pairs"] == len(seen)


def test_durable_primary_budget_prevents_fresh_dispatch(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    def reserve(session: str, context: Any, data: Any) -> Any:
        for n in range(90):
            attempt = f"synthetic-spent-{n}"
            engine.ledger.append(session, "model.attempt.intended", {"attempt": attempt, "task_key": attempt,
                "event_pair_study": plan["study_key"], "event_pair_retry": False,
                "reserved_pair_attempts": 1, "reserved_article_exposures": 2})
            engine.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "status": "invalid"})
        return {"synthetic_attempts": 90}
    original = engine._status
    monkeypatch.setattr(engine, "_status", reserve)
    engine.execute("status", objective="Construct prior spent-attempt budget fixture", actor="test:software")
    monkeypatch.setattr(engine, "_status", original)
    seen = fake_provider(monkeypatch)
    result = run(planned)
    assert result["pair_attempts"] == 90 and result["article_exposures"] == 180
    assert result["pending_pairs"] == plan["development_pairs"] and seen == []


def test_holdout_candidate_is_durable_before_validation_dispatch(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    fake_provider(monkeypatch)
    monkeypatch.setattr(experiment.sampling, "evaluate_grid", lambda *args: {
        "candidate_cutoff": .2, "grid": [], "status": "candidate_frozen"})
    original = experiment._phase
    observed = []
    def phase(*args: Any, **kwargs: Any) -> Any:
        rows = args[2]
        if rows and rows[0]["fold"] == "validation":
            observed.append(True)
            assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_candidate'").fetchone()[0] == 1
            assert engine.ledger.db.execute("SELECT count(*) FROM records WHERE kind='event_pair_holdout_opened'").fetchone()[0] == 1
        return original(*args, **kwargs)
    monkeypatch.setattr(experiment, "_phase", phase)
    result = run(planned)
    assert observed and result["candidate_cutoff"] == .2 and result["validation_pairs"] > 0
    assert result["validation"]["human_validated"] is False


def test_audit_intent_failure_stops_before_dispatch(planned: Any, monkeypatch: Any) -> None:
    engine, _ = planned
    seen = fake_provider(monkeypatch)
    engine.ledger.fail_event = "model.attempt.intended"
    with pytest.raises(AuditError, match="Injected audit failure"):
        run(planned)
    assert seen == []


def test_resume_retains_opened_holdout_after_unknown(planned: Any, monkeypatch: Any) -> None:
    def response(prepared: Any, n: int) -> Any:
        return ProviderResponse(None if n == 8 else uncertain(prepared.request), "codex-cli", None,
            raw_response={"unknown_outcome": n == 8})
    seen = fake_provider(monkeypatch, response)
    monkeypatch.setattr(experiment.sampling, "evaluate_grid", lambda *args: {
        "candidate_cutoff": .2, "grid": [], "status": "candidate_frozen"})
    approval = approved(planned[1])
    first = run(planned, approval, workers=1)
    resumed = run(planned, approval, workers=1, reuse_cache=True)
    assert first["validation_pairs"] == resumed["validation_pairs"] > 0
    assert first["counts"] == resumed["counts"]
    assert first["pair_attempts"] == resumed["pair_attempts"] == len(seen) == 8
    assert resumed["unknown_pairs"] == 1 and resumed["validation"] is not None
    assert "No held-out labels opened" not in resumed["presentation"]["markdown"]


def test_expiry_between_blocks_keeps_partial_results(planned: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    original = experiment._expiry
    checks = []
    def expiry(approval: Any) -> None:
        checks.append(True)
        if len(checks) >= 3:
            raise ResearchError("Event-pair approval expired")
        original(approval)
    monkeypatch.setattr(experiment, "_expiry", expiry)
    result = run(planned, workers=1)
    assert result["status"] == "partial" and result["pair_attempts"] == len(seen) == 1
    assert result["pending_pairs"] == planned[1]["development_pairs"] - 1


def test_unavailable_pair_input_remains_failed_without_dispatch(planned: Any, monkeypatch: Any) -> None:
    seen = fake_provider(monkeypatch)
    original = experiment._request
    prepared = []
    def request(*args: Any) -> Any:
        prepared.append(True)
        if len(prepared) == 1:
            raise ResearchError("event_pair_incomplete_source_coverage")
        return original(*args)
    monkeypatch.setattr(experiment, "_request", request)
    result = run(planned)
    assert result["failed_pairs"] == 1
    assert result["pair_attempts"] == len(seen) == planned[1]["development_pairs"] - 1
    assert result["candidate_cutoff"] is None and result["validation_pairs"] == 0


def test_exhausted_retry_reserve_preserves_observed_invalid(planned: Any, monkeypatch: Any) -> None:
    engine, plan = planned
    original = engine._status
    def reserve(session: str, context: Any, data: Any) -> Any:
        for n in range(10):
            attempt = f"synthetic-spent-retry-{n}"
            engine.ledger.append(session, "model.attempt.intended", {"attempt": attempt, "task_key": attempt,
                "event_pair_study": plan["study_key"], "event_pair_retry": True,
                "reserved_pair_attempts": 1, "reserved_article_exposures": 2})
            engine.ledger.append(session, "model.attempt.completed", {"attempt": attempt, "status": "invalid"})
        return {"synthetic_attempts": 10}
    monkeypatch.setattr(engine, "_status", reserve)
    engine.execute("status", objective="Construct spent retry-reserve fixture", actor="test:software")
    monkeypatch.setattr(engine, "_status", original)
    fake_provider(monkeypatch, lambda *args: ProviderResponse({"bad_schema": True}, "codex-cli", None,
                                                           raw_response={"unknown_outcome": False}))
    result = run(planned)
    assert result["failed_pairs"] == plan["development_pairs"] and result["pending_pairs"] == 0
    assert result["retry_attempts"] == 10
    assert all(value["retry_pending"] for value in result["development_judgements"].values())


def test_direct_handler_requires_active_runtime(planned: Any) -> None:
    with pytest.raises(AuditError, match="active audited"):
        experiment.execute(planned[0], "not-active", Context("Reject bypass", "test"), {})
