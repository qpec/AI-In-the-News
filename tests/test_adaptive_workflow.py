"""Synthetic bounded-workflow checks, never research validation evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any

import pytest

from newsresearch.codex_provider import CodexCLIProvider
from newsresearch.adaptive_math import FrameItem, sample_round, split_frame
from newsresearch.common import AuditError, Context, ResearchError
from newsresearch.gateway import ProviderResponse
from test_similarity_tags import prepared_query as _prepared_query, score
from test_similarity_tags import indexed as _indexed, embedding_plan as _embedding_plan

prepared_query = _prepared_query
indexed = _indexed
embedding_plan = _embedding_plan


def authorization(maximum: int = 17) -> dict[str, Any]:
    return {
        "approved_by": "synthetic:test",
        "instruction": "Execute the concrete synthetic Codex workflow under its registered test profile.",
        "allow_codex_account": True,
        "allow_external_processing": True,
        "max_article_attempts": maximum,
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    }


class SyntheticCodex(CodexCLIProvider):
    """Use real packet construction but an explicitly synthetic model return."""

    def __init__(self, workspace: Any, engine: Any, expected: dict[str, float]) -> None:
        super().__init__(workspace, model="synthetic-fixture")
        self.engine = engine
        self.expected = expected
        self.cutoff = sorted(expected.values())[len(expected) // 2]
        self.calls: list[dict[str, Any]] = []
        self.unknown = False
        self.invalid = False
        self.database = engine.ledger.db.execute("PRAGMA database_list").fetchone()[2]

    def complete_prepared(self, prepared: Any) -> ProviderResponse:
        # This checks the actual dispatch boundary, not merely final records.
        assert self.engine._active
        with sqlite3.connect(self.database) as inspection:
            latest = inspection.execute(
                "SELECT seq,payload FROM events WHERE kind='model.attempt.intended' "
                "AND json_extract(payload,'$.source_version')=? ORDER BY seq DESC LIMIT 1",
                (prepared.request["source_version"],),
            ).fetchone()
            assert latest is not None
            intent = json.loads(latest[1])
            batch = inspection.execute(
                "SELECT created_event,payload FROM records WHERE id=? AND kind='codex_batch_manifest'",
                (intent["batch"],),
            ).fetchone()
            assert batch is not None and batch[0] < latest[0]
            round_record = inspection.execute(
                "SELECT created_event FROM records WHERE id=? AND kind='adaptive_round_manifest'",
                (intent["round"],),
            ).fetchone()
            assert round_record is not None and round_record[0] < batch[0]
        assert intent.get("request")
        stored_request = self.engine.ledger.artifacts.read(intent["request"])
        assert stored_request
        packet = json.loads(prepared.stdin)
        assert packet["inclusion"]["sha256"] == hashlib.sha256(
            packet["inclusion"]["instruction"].encode()
        ).hexdigest()
        assert not {"score", "cutoff", "prior_label", "rank", "probability", "split"}.intersection(packet)
        evidence = prepared.request["evidence"]
        source_id = prepared.request["source_version"]
        result = {
            "label": "yes" if self.expected[source_id] >= self.cutoff else "no",
            "rationale": "Synthetic score oracle for software checks only.",
            "criterion_ids": [packet["inclusion"]["criterion_ids"][0]],
            "claims": [{"passage_id": evidence[0]["id"], "quote": evidence[0]["text"]}],
            "inspected_passage_ids": [item["id"] for item in evidence],
        }
        self.calls.append({"source_id": source_id, "packet": packet, "intent": intent})
        if self.invalid:
            result["inspected_passage_ids"] = []
        raw = {
            **prepared.manifest(),
            "stdout": json.dumps(result),
            "failure": "synthetic_unknown_outcome" if self.unknown else None,
            "unknown_outcome": self.unknown,
            "observed_model": "synthetic-fixture",
        }
        return ProviderResponse(
            None if self.unknown else result,
            "codex-cli", "synthetic-fixture", None,
            {"input_tokens": 10, "output_tokens": 10}, raw,
        )


@pytest.fixture
def workflow(prepared_query: Any, monkeypatch: Any, tmp_path: Any) -> dict[str, Any]:
    from newsresearch import adaptive_cutoff

    engine, _, _, _, expected, _, run = prepared_query
    scored = score(prepared_query)
    for filename in ("adaptive-llm-cutoff-v1.json", "adaptive-llm-cutoff-v2.json"):
        engine.execute(
            "version", json.loads((engine.project / "methods" / filename).read_text(encoding="utf-8")),
            objective="Register source-free method predecessor for synthetic integration checks",
            actor="codex:method-design",
        )
    engine.config = replace(engine.config, offline=False)
    profile = {
        "initial_uniform_draws": 8,
        "adaptive_rounds": 1,
        "draws_per_adaptive_round": 4,
        "held_out_articles": 3,
        "reserve_article_attempts": 2,
        "max_article_attempts": 17,
        "max_unique_articles": 15,
        "window_sizes": [4],
    }
    monkeypatch.setitem(adaptive_cutoff.PROFILES, "compact_100", profile)
    for key, value in {
        "min_positive": 1,
        "min_negative": 1,
        "max_recall_interval_width": 1.0,
        "max_unknown_fraction": 1.0,
    }.items():
        monkeypatch.setitem(adaptive_cutoff.RULES, key, value)
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_BASE", "CODEX_BASE_URL"):
        monkeypatch.delenv(variable, raising=False)
    provider = SyntheticCodex(tmp_path / "workers", engine, expected)
    monkeypatch.setattr(adaptive_cutoff, "provider_factory", lambda research, data: provider)
    original_frame = adaptive_cutoff._frame

    def independent_synthetic_frame(*args: Any, **kwargs: Any) -> tuple[Any, Any]:
        # The indexing fixture repeats the same synthetic body. These workflow
        # tests stipulate independent groups to exercise later execution paths;
        # the original grouping is retained in its SQL snapshot and separately
        # tested below. Production grouping is never changed.
        frame, rows = original_frame(*args, **kwargs)
        return [FrameItem(item.source_id, item.score, item.source_id) for item in frame], rows

    monkeypatch.setattr(adaptive_cutoff, "_frame", independent_synthetic_frame)
    # Synthetic source IDs include fixture retrieval times. Pick a deterministic
    # test seed with both scripted classes in development and holdout, so this
    # software branch test cannot fluctuate with those IDs. This purposive
    # fixture is explicitly not a scientific evaluation sample.
    synthetic_frame = [FrameItem(source, value, source) for source, value in expected.items()]
    synthetic_by_id = {item.source_id: item for item in synthetic_frame}
    seed = 20261015
    for seed in range(20261015, 20262015):
        split = split_frame(synthetic_frame, 3, seed)
        initial = sample_round(
            [synthetic_by_id[source] for source in split["development_ids"]], 8, seed, 0,
            rng_state=split["rng_state_after"],
        )
        initial_classes = {expected[draw["source_id"]] >= provider.cutoff for draw in initial["draws"]}
        heldout_classes = {expected[source] >= provider.cutoff for source in split["heldout_ids"]}
        if len(initial_classes) == len(heldout_classes) == 2:
            break
    else:
        raise AssertionError("Could not construct both-class synthetic branch fixture")
    return {
        "engine": engine,
        "scored": scored,
        "expected": expected,
        "run": run,
        "provider": provider,
        "module": adaptive_cutoff,
        "original_frame": original_frame,
        "data": {
            "scores": scored["id"], "key": "synthetic-calibration",
            "run_approval": authorization(), "budget": "compact_100",
            "seed": seed, "execute": True, "codex_model": "synthetic-fixture",
        },
    }


def test_direct_handler_cannot_bypass_audited_runtime(workflow: dict[str, Any]) -> None:
    engine = workflow["engine"]
    with pytest.raises(AuditError, match="active audited"):
        workflow["module"].execute(engine, "invalid", Context("Direct bypass", "test"), workflow["data"])
    assert not workflow["provider"].calls


def test_original_duplicate_groups_exclude_all_development_and_prevent_dispatch(
    workflow: dict[str, Any], monkeypatch: Any,
) -> None:
    monkeypatch.setattr(workflow["module"], "_frame", workflow["original_frame"])
    with pytest.raises(ValueError, match="leave no development"):
        workflow["run"]("adaptive_cutoff", workflow["data"])
    assert not workflow["provider"].calls


@pytest.mark.parametrize("field", ["allow_codex_account", "allow_external_processing"])
def test_execution_requires_explicit_concrete_authorization(workflow: dict[str, Any], field: str) -> None:
    data = {**workflow["data"], "run_approval": {**authorization(), field: False}}
    with pytest.raises(ResearchError):
        workflow["run"]("adaptive_cutoff", data)
    assert not workflow["provider"].calls


def test_expired_authorization_never_dispatches(workflow: dict[str, Any]) -> None:
    permission = authorization()
    permission["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with pytest.raises(ResearchError):
        workflow["run"]("adaptive_cutoff", {**workflow["data"], "run_approval": permission})
    assert not workflow["provider"].calls


def test_authorized_attempt_cap_cannot_be_smaller_than_frozen_workflow(workflow: dict[str, Any]) -> None:
    with pytest.raises(ResearchError):
        workflow["run"]("adaptive_cutoff", {**workflow["data"], "run_approval": authorization(1)})
    assert not workflow["provider"].calls


def test_failed_durable_attempt_intent_stops_before_any_model_dispatch(workflow: dict[str, Any]) -> None:
    engine = workflow["engine"]
    engine.ledger.fail_event = "model.attempt.intended"
    with pytest.raises(AuditError):
        workflow["run"]("adaptive_cutoff", workflow["data"])
    assert not workflow["provider"].calls


def test_plan_only_never_dispatches_or_creates_model_attempt(workflow: dict[str, Any]) -> None:
    engine = workflow["engine"]
    before = engine.ledger.db.execute(
        "SELECT count(*) FROM events WHERE kind='model.attempt.intended'"
    ).fetchone()[0]
    report = workflow["run"]("adaptive_cutoff", {**workflow["data"], "execute": False})
    assert report
    assert not workflow["provider"].calls
    assert engine.ledger.db.execute(
        "SELECT count(*) FROM events WHERE kind='model.attempt.intended'"
    ).fetchone()[0] == before
    assert engine.ledger.verify()["status"] == "verified"


def test_offline_default_requires_explicit_local_online_configuration(workflow: dict[str, Any]) -> None:
    engine = workflow["engine"]
    engine.config = replace(engine.config, offline=True)
    with pytest.raises(ResearchError, match="online configuration"):
        workflow["run"]("adaptive_cutoff", workflow["data"])
    assert not workflow["provider"].calls


def test_concrete_run_requires_a_pinned_configured_model(workflow: dict[str, Any]) -> None:
    data = {key: value for key, value in workflow["data"].items() if key != "codex_model"}
    with pytest.raises(ResearchError, match="configured Codex model"):
        workflow["run"]("adaptive_cutoff", data)
    assert not workflow["provider"].calls


def test_completed_workflow_freezes_candidate_before_holdout_and_audits_results(workflow: dict[str, Any]) -> None:
    engine = workflow["engine"]
    report = workflow["run"]("adaptive_cutoff", workflow["data"])
    provider = workflow["provider"]
    assert report["candidate_cutoff"] in workflow["expected"].values()
    assert report["development"]["draw_count"] == 12
    assert report["article_attempts"] == len(provider.calls) <= 17
    assert report["unique_articles_offered"] == len({call["source_id"] for call in provider.calls})
    assert report["heldout"]["heldout_size"] == 3
    assert report["new_embedding_calls"] == report["direct_openai_api_requests"] == 0
    assert report["provider_billing"] is None
    assert report["human_validated"] is False
    assert report["expected_articles"] == 11 and report["scored_articles"] == 9
    assert report["unprocessed_articles"] == 2
    plan = engine.ledger.get(report["plan"], "adaptive_cutoff_plan")
    heldout = set(plan["split"]["heldout_ids"])
    frozen = engine.ledger.get(report["frozen_candidate"], "adaptive_frozen_candidate")
    assert not heldout.intersection(frozen["labels"])
    assert not heldout.intersection(draw["source_id"] for draw in frozen["draws"])
    frozen_event = engine.ledger.db.execute(
        "SELECT created_event FROM records WHERE id=?", (report["frozen_candidate"],)
    ).fetchone()[0]
    for call in provider.calls:
        if call["source_id"] in heldout:
            event = engine.ledger.db.execute(
                "SELECT seq FROM events WHERE kind='model.attempt.intended' "
                "AND json_extract(payload,'$.attempt')=?", (call["intent"]["attempt"],)
            ).fetchone()[0]
            assert event > frozen_event
        assert call["packet"]["inclusion"]["instruction"] == plan["canonical_inclusion"]
        assert call["packet"]["inclusion"]["sha256"] == report["inclusion_text_sha256"]
    assert engine.ledger.db.execute("SELECT count(*) FROM accepted").fetchone()[0] == 0
    presentation = report["presentation"]
    assert presentation["results"] == [{"kind": "adaptive_cutoff_result", "id": report["id"]}]
    assert engine.ledger.artifacts.read_bytes(presentation["content_artifact"]) == presentation["markdown"].encode()
    assert "Kandidaat-cutoff" in presentation["markdown"]
    assert not presentation["ui_delivery_verified"]
    assert engine.ledger.verify()["status"] == "verified"


def test_successful_model_reference_tags_preserve_original_scores_and_missing_nulls(workflow: dict[str, Any]) -> None:
    report = workflow["run"]("adaptive_cutoff", workflow["data"])
    assert report["status"] == "passed_model_reference"
    assert report["applied"] is not None
    old = workflow["run"]("article_query_rows", {"run": workflow["scored"]["run"]})["rows"]
    rows = workflow["run"]("article_query_rows", {"run": report["applied"]["run"]})["rows"]
    previous = {row["source_version"]: row for row in old}
    assert len(rows) == 11 and sum(row["answer"] is None for row in rows) == 2
    for row in rows:
        assert row["score"] == previous[row["source_version"]]["score"]
        assert row["parent_result"] == previous[row["source_version"]]["result_id"]
        assert row["threshold"] == report["candidate_cutoff"]
        if row["score"] is not None:
            assert row["answer"] == ("yes" if row["score"] >= report["candidate_cutoff"] else "no")
        else:
            assert row["answer"] is None
    assert all(row["answer"] is None for row in old)
    counts = report["applied"]["answer_counts"]
    assert counts.get("yes", 0) + counts.get("no", 0) == 9 and counts["None"] == 2
    assert "| Onverwerkt | 2 |" in report["presentation"]["markdown"]


def test_invalid_full_article_coverage_stays_missing_and_does_not_open_holdout(workflow: dict[str, Any]) -> None:
    provider = workflow["provider"]
    provider.invalid = True
    report = workflow["run"]("adaptive_cutoff", workflow["data"])
    assert report["status"] == "partial"
    assert report["reference_counts"] == {"missing": 1}
    assert report["candidate_cutoff"] is None
    assert report["heldout"] is None and report["applied"] is None
    assert report["article_attempts"] == len(provider.calls) == 1
    assert not workflow["engine"].ledger.db.execute(
        "SELECT 1 FROM records WHERE kind='codex_article_assessment'"
    ).fetchone()
    assert not workflow["engine"].ledger.db.execute(
        "SELECT 1 FROM events WHERE kind='adaptive.holdout.opened'"
    ).fetchone()
    assert "partial" in report["presentation"]["markdown"]


def test_unknown_outcome_retains_spent_attempt_and_blocks_automatic_retry(workflow: dict[str, Any]) -> None:
    provider = workflow["provider"]
    provider.unknown = True
    first = workflow["run"]("adaptive_cutoff", workflow["data"])
    assert first["status"] == "partial" and first["article_attempts"] == 1
    assert first["reference_counts"] == {"missing": 1}
    assert len(workflow["engine"].ledger.unresolved) == 1
    with pytest.raises(ResearchError, match="Unknown Codex outcome"):
        workflow["run"]("adaptive_cutoff", {**workflow["data"], "reuse_cache": True})
    assert len(provider.calls) == 1


def test_explicit_resume_reuses_exact_primary_labels_without_new_article_attempts(workflow: dict[str, Any]) -> None:
    first = workflow["run"]("adaptive_cutoff", workflow["data"])
    count = len(workflow["provider"].calls)
    repeated = workflow["run"]("adaptive_cutoff", {**workflow["data"], "reuse_cache": True})
    assert repeated["candidate_cutoff"] == first["candidate_cutoff"]
    assert repeated["article_attempts"] == first["article_attempts"] == count
    assert len(workflow["provider"].calls) == count
    assert workflow["engine"].ledger.db.execute(
        "SELECT count(*) FROM events WHERE kind='model.cache_reused'"
    ).fetchone()[0] > 0


def test_previous_run_cache_reuse_requires_explicit_opt_in(workflow: dict[str, Any]) -> None:
    workflow["run"]("adaptive_cutoff", workflow["data"])
    count = len(workflow["provider"].calls)
    with pytest.raises(ResearchError, match="reuse_cache"):
        workflow["run"]("adaptive_cutoff", workflow["data"])
    assert len(workflow["provider"].calls) == count


def test_article_attempt_limit_remains_spent_across_failed_resume_operations(
    workflow: dict[str, Any], monkeypatch: Any,
) -> None:
    profile = {**workflow["module"].PROFILES["compact_100"], "max_article_attempts": 2}
    monkeypatch.setitem(workflow["module"].PROFILES, "compact_100", profile)
    data = {**workflow["data"], "run_approval": authorization(2), "reuse_cache": True}
    provider = workflow["provider"]
    provider.invalid = True
    first = workflow["run"]("adaptive_cutoff", data)
    second = workflow["run"]("adaptive_cutoff", data)
    assert first["article_attempts"] == 1 and second["article_attempts"] == 2
    with pytest.raises(ResearchError, match="budget exhausted"):
        workflow["run"]("adaptive_cutoff", data)
    assert len(provider.calls) == 2
    assert len({call["source_id"] for call in provider.calls}) == 1
